from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import time

from tit.cli import utils as cli_utils

from .config import ResponderMLConfig, default_output_dir, default_glasser_atlas_path
from .dataset import SubjectRow, load_efield_images, load_subject_table
from .features import FeatureMatrix, extract_roi_features_from_efield


@dataclass(frozen=True)
class TrainArtifacts:
    output_dir: Path
    model_path: Path
    metrics_path: Path
    predictions_csv: Path
    feature_names_json: Path


def _safe_splits(y: Sequence[int], desired: int) -> int:
    y = list(y)
    if len(y) < 4:
        return 2
    pos = sum(1 for v in y if v == 1)
    neg = sum(1 for v in y if v == 0)
    max_splits = max(2, min(desired, pos, neg))
    return max_splits


def train_from_csv(cfg: ResponderMLConfig) -> TrainArtifacts:
    """
    End-to-end training:
    - load subjects.csv
    - load E-field NIfTIs
    - extract Glasser ROI features (mean/max/top10 mean)
    - nested CV for unbiased estimate
    - fit final model on all data and save artifacts
    """
    from sklearn.linear_model import ElasticNet, LogisticRegression
    from sklearn.metrics import (
        average_precision_score,
        mean_absolute_error,
        mean_squared_error,
        r2_score,
        roc_auc_score,
    )
    from sklearn.model_selection import GridSearchCV, KFold, StratifiedKFold
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    import joblib

    t0 = time.perf_counter()
    if cfg.verbose:
        cli_utils.echo_info(f"Loading CSV: {cfg.csv_path}")
    subjects = load_subject_table(
        cfg.csv_path, task=cfg.task, target_col=cfg.target_col, require_target=True
    )
    if cfg.verbose:
        cli_utils.echo_info(f"Loaded {len(subjects)} rows. Loading E-field NIfTIs…")
    efield_imgs, y, kept = load_efield_images(
        subjects, efield_filename_pattern=cfg.efield_filename_pattern
    )
    if cfg.verbose:
        cli_utils.echo_info(f"Loaded {len(kept)} NIfTIs. Resolving atlas…")

    atlas_path = cfg.atlas_path
    if atlas_path is None:
        atlas_path = default_glasser_atlas_path()
    if cfg.verbose:
        cli_utils.echo_info(f"Atlas: {atlas_path}")
        cli_utils.echo_info("Extracting ROI features (mean/top10mean)…")
    fm = extract_roi_features_from_efield(efield_imgs, atlas_path=atlas_path)
    X = fm.X
    if any(v is None for v in y):
        raise ValueError(
            f"Missing target values in column {cfg.target_col!r}. Training requires targets for all subjects."
        )

    if cfg.task == "classification":
        y_arr = np.asarray([int(v) for v in y], dtype=int)
        if cfg.verbose:
            cli_utils.echo_info(
                f"Feature matrix: X={X.shape}, y={y_arr.shape} (pos={(y_arr==1).sum()}, neg={(y_arr==0).sum()})"
            )

        outer_splits = _safe_splits(y_arr.tolist(), cfg.outer_splits)
        inner_splits = _safe_splits(y_arr.tolist(), cfg.inner_splits)
        if cfg.verbose:
            cli_utils.echo_info(
                f"Nested CV: outer={outer_splits} folds, inner={inner_splits} folds, n_jobs={cfg.n_jobs}"
            )

        outer_cv = StratifiedKFold(
            n_splits=outer_splits, shuffle=True, random_state=cfg.random_state
        )
        inner_cv = StratifiedKFold(
            n_splits=inner_splits, shuffle=True, random_state=cfg.random_state + 1
        )

        pipe = Pipeline(
            steps=[
                ("scaler", StandardScaler(with_mean=True, with_std=True)),
                (
                    "clf",
                    LogisticRegression(
                        penalty="elasticnet",
                        solver="saga",
                        class_weight="balanced",
                        max_iter=5000,
                        random_state=cfg.random_state,
                    ),
                ),
            ]
        )
        param_grid = {
            "clf__C": [0.01, 0.1, 1.0, 10.0],
            "clf__l1_ratio": [0.0, 0.5, 1.0],
        }

        # Outer loop predictions
        proba = np.full(shape=(len(y_arr),), fill_value=np.nan, dtype=float)
        best_params_per_fold: List[Dict[str, Any]] = []

        for fold_idx, (train_idx, test_idx) in enumerate(
            outer_cv.split(X, y_arr), start=1
        ):
            if cfg.verbose:
                cli_utils.echo_info(
                    f"Outer fold {fold_idx}/{outer_splits}: tuning hyperparameters…"
                )
            X_tr, X_te = X[train_idx], X[test_idx]
            y_tr = y_arr[train_idx]

            gs = GridSearchCV(
                pipe,
                param_grid=param_grid,
                scoring="roc_auc",
                cv=inner_cv,
                n_jobs=int(cfg.n_jobs),
                refit=True,
                verbose=(1 if cfg.verbose else 0),
            )
            gs.fit(X_tr, y_tr)
            best_params_per_fold.append(dict(gs.best_params_))

            p_te = gs.predict_proba(X_te)[:, 1]
            proba[test_idx] = p_te
            if cfg.verbose:
                cli_utils.echo_info(
                    f"Outer fold {fold_idx}/{outer_splits}: done. best={gs.best_params_}"
                )

        if np.isnan(proba).any():
            raise RuntimeError("Internal error: some CV predictions were not generated")

        metrics: Dict[str, Any] = {
            "task": "classification",
            "target_col": str(cfg.target_col),
            "n_subjects_total": len(subjects),
            "n_subjects_used": int(len(kept)),
            "outer_splits": int(outer_splits),
            "inner_splits": int(inner_splits),
            "roc_auc": float(roc_auc_score(y_arr, proba)),
            "pr_auc": float(average_precision_score(y_arr, proba)),
            "pos_count": int((y_arr == 1).sum()),
            "neg_count": int((y_arr == 0).sum()),
            "best_params_per_fold": best_params_per_fold,
        }

        # Fit final model on all data (inner CV for hyperparams)
        gs_final = GridSearchCV(
            pipe,
            param_grid=param_grid,
            scoring="roc_auc",
            cv=inner_cv,
            n_jobs=int(cfg.n_jobs),
            refit=True,
            verbose=(1 if cfg.verbose else 0),
        )
        if cfg.verbose:
            cli_utils.echo_info("Fitting final model on all data (inner CV)…")
        gs_final.fit(X, y_arr)
        best_est = gs_final.best_estimator_
        best_params_final: Dict[str, Any] = dict(gs_final.best_params_ or {})
        metrics["best_params_final"] = best_params_final

        # Output paths
        run_name = cfg.run_name
        out_dir = cfg.output_dir or default_output_dir(run_name=run_name)
        out_dir.mkdir(parents=True, exist_ok=True)
        if cfg.verbose:
            cli_utils.echo_info(f"Output dir: {out_dir}")

        model_path = out_dir / "model.joblib"
        metrics_path = out_dir / "metrics.json"
        preds_path = out_dir / "cv_predictions.csv"
        feat_names_path = out_dir / "feature_names.json"

        joblib.dump(
            {
                "model": best_est,
                "feature_names": fm.feature_names,
                "atlas_path": str(fm.atlas_path),
                "config": asdict(cfg),
            },
            model_path,
        )

        # Optional bootstrap stability for coefficients (classification only, off by default).
        if int(getattr(cfg, "bootstrap_samples", 0)) > 0:
            rng = np.random.default_rng(int(cfg.random_state))
            B = int(cfg.bootstrap_samples)
            coef_mat = np.zeros((B, len(fm.feature_names)), dtype=float)
            for b in range(B):
                idx = rng.integers(0, len(y_arr), size=len(y_arr))
                Xb = X[idx]
                yb = y_arr[idx]
                est_b = Pipeline(
                    steps=[
                        ("scaler", StandardScaler(with_mean=True, with_std=True)),
                        (
                            "clf",
                            LogisticRegression(
                                penalty="elasticnet",
                                solver="saga",
                                class_weight="balanced",
                                max_iter=5000,
                                random_state=cfg.random_state + b + 100,
                                C=float(best_params_final.get("clf__C", 1.0)),
                                l1_ratio=float(
                                    best_params_final.get("clf__l1_ratio", 0.5)
                                ),
                            ),
                        ),
                    ]
                )
                est_b.fit(Xb, yb)
                coef_mat[b, :] = np.asarray(
                    est_b.named_steps["clf"].coef_[0], dtype=float
                )

            coef_mean = coef_mat.mean(axis=0)
            coef_std = coef_mat.std(axis=0)
            sign_consistency = np.mean(
                np.sign(coef_mat) == np.sign(coef_mean[None, :]), axis=0
            )
            stab_path = out_dir / "coef_stability.csv"
            lines = ["feature,coef_mean,coef_std,sign_consistency"]
            for name, m, s, sc in zip(
                fm.feature_names,
                coef_mean.tolist(),
                coef_std.tolist(),
                sign_consistency.tolist(),
            ):
                lines.append(f"{name},{float(m)},{float(s)},{float(sc)}")
            stab_path.write_text("\n".join(lines) + "\n")
            cli_utils.echo_success(f"Saved coefficient stability: {stab_path}")

        metrics_path.write_text(json.dumps(metrics, indent=2))
        feat_names_path.write_text(json.dumps(fm.feature_names, indent=2))

        # Write per-subject predictions
        lines = ["subject_id,simulation_name,response,proba"]
        for s, yy, pp in zip(kept, y_arr.tolist(), proba.tolist()):
            lines.append(f"{s.subject_id},{s.simulation_name},{int(yy)},{float(pp)}")
        preds_path.write_text("\n".join(lines) + "\n")

        cli_utils.echo_success(f"Saved model: {model_path}")
        cli_utils.echo_success(f"Saved metrics: {metrics_path}")
        if cfg.verbose:
            cli_utils.echo_info(f"Done in {time.perf_counter() - t0:.1f}s")

        return TrainArtifacts(
            output_dir=out_dir,
            model_path=model_path,
            metrics_path=metrics_path,
            predictions_csv=preds_path,
            feature_names_json=feat_names_path,
        )

    # -----------------------------
    # Regression (continuous target)
    # -----------------------------

    y_arr_f = np.asarray([float(v) for v in y], dtype=float)
    if cfg.verbose:
        cli_utils.echo_info(
            f"Feature matrix: X={X.shape}, y={y_arr_f.shape} (task=regression)"
        )

    def _safe_splits_regression(n: int, desired: int) -> int:
        if n < 4:
            return 2
        return max(2, min(int(desired), int(n)))

    outer_splits = _safe_splits_regression(len(y_arr_f), cfg.outer_splits)
    inner_splits = _safe_splits_regression(len(y_arr_f), cfg.inner_splits)
    if cfg.verbose:
        cli_utils.echo_info(
            f"Nested CV: outer={outer_splits} folds, inner={inner_splits} folds, n_jobs={cfg.n_jobs}"
        )

    outer_cv = KFold(n_splits=outer_splits, shuffle=True, random_state=cfg.random_state)
    inner_cv = KFold(
        n_splits=inner_splits, shuffle=True, random_state=cfg.random_state + 1
    )

    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            ("reg", ElasticNet(max_iter=10000)),
        ]
    )
    param_grid = {
        "reg__alpha": [0.001, 0.01, 0.1, 1.0, 10.0],
        "reg__l1_ratio": [0.0, 0.5, 1.0],
    }

    pred = np.full(shape=(len(y_arr_f),), fill_value=np.nan, dtype=float)
    best_params_per_fold: List[Dict[str, Any]] = []

    for fold_idx, (train_idx, test_idx) in enumerate(outer_cv.split(X), start=1):
        if cfg.verbose:
            cli_utils.echo_info(
                f"Outer fold {fold_idx}/{outer_splits}: tuning hyperparameters…"
            )
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr = y_arr_f[train_idx]

        gs = GridSearchCV(
            pipe,
            param_grid=param_grid,
            scoring="neg_mean_absolute_error",
            cv=inner_cv,
            n_jobs=int(cfg.n_jobs),
            refit=True,
            verbose=(1 if cfg.verbose else 0),
        )
        gs.fit(X_tr, y_tr)
        best_params_per_fold.append(dict(gs.best_params_))

        pred_te = gs.predict(X_te)
        pred[test_idx] = np.asarray(pred_te, dtype=float)
        if cfg.verbose:
            cli_utils.echo_info(
                f"Outer fold {fold_idx}/{outer_splits}: done. best={gs.best_params_}"
            )

    if np.isnan(pred).any():
        raise RuntimeError("Internal error: some CV predictions were not generated")

    mae = float(mean_absolute_error(y_arr_f, pred))
    # Compatibility: some sklearn versions don't support `squared=False`.
    rmse = float(np.sqrt(mean_squared_error(y_arr_f, pred)))
    r2 = float(r2_score(y_arr_f, pred))

    metrics = {
        "task": "regression",
        "target_col": str(cfg.target_col),
        "n_subjects_total": len(subjects),
        "n_subjects_used": int(len(kept)),
        "outer_splits": int(outer_splits),
        "inner_splits": int(inner_splits),
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "best_params_per_fold": best_params_per_fold,
    }

    gs_final = GridSearchCV(
        pipe,
        param_grid=param_grid,
        scoring="neg_mean_absolute_error",
        cv=inner_cv,
        n_jobs=int(cfg.n_jobs),
        refit=True,
        verbose=(1 if cfg.verbose else 0),
    )
    if cfg.verbose:
        cli_utils.echo_info("Fitting final model on all data (inner CV)…")
    gs_final.fit(X, y_arr_f)
    best_est = gs_final.best_estimator_
    best_params_final: Dict[str, Any] = dict(gs_final.best_params_ or {})
    metrics["best_params_final"] = best_params_final

    run_name = cfg.run_name
    out_dir = cfg.output_dir or default_output_dir(run_name=run_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    if cfg.verbose:
        cli_utils.echo_info(f"Output dir: {out_dir}")

    model_path = out_dir / "model.joblib"
    metrics_path = out_dir / "metrics.json"
    preds_path = out_dir / "cv_predictions.csv"
    feat_names_path = out_dir / "feature_names.json"

    joblib.dump(
        {
            "model": best_est,
            "feature_names": fm.feature_names,
            "atlas_path": str(fm.atlas_path),
            "config": asdict(cfg),
        },
        model_path,
    )

    metrics_path.write_text(json.dumps(metrics, indent=2))
    feat_names_path.write_text(json.dumps(fm.feature_names, indent=2))

    # Write per-subject predictions (continuous)
    lines = [f"subject_id,simulation_name,{cfg.target_col},pred"]
    for s, yy, pp in zip(kept, y_arr_f.tolist(), pred.tolist()):
        lines.append(f"{s.subject_id},{s.simulation_name},{float(yy)},{float(pp)}")
    preds_path.write_text("\n".join(lines) + "\n")

    cli_utils.echo_success(f"Saved model: {model_path}")
    cli_utils.echo_success(f"Saved metrics: {metrics_path}")
    if cfg.verbose:
        cli_utils.echo_info(f"Done in {time.perf_counter() - t0:.1f}s")

    return TrainArtifacts(
        output_dir=out_dir,
        model_path=model_path,
        metrics_path=metrics_path,
        predictions_csv=preds_path,
        feature_names_json=feat_names_path,
    )
