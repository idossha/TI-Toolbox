from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import time

from tit import logger as logging_util

from .config import ResponderMLConfig, default_output_dir, default_glasser_atlas_path
from .dataset import (
    SubjectRow,
    is_sham_condition,
    load_efield_images,
    load_subject_table,
)
from .features import (
    FeatureMatrix,
    extract_features,
    extract_voxel_features_by_coords,
    select_fregression_voxel_coords,
    select_ttest_voxel_coords,
)


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


def _safe_splits_regression(n_samples: int, desired: int) -> int:
    if n_samples < 4:
        return 2
    return max(2, min(desired, n_samples))


def _ref_image_shape_and_affine(img: Any) -> Tuple[Tuple[int, int, int], List[List[float]]]:
    data = np.asanyarray(img.dataobj)
    if data.ndim == 4:
        data = data[..., 0] if data.shape[-1] == 1 else data[..., -1]
    if data.ndim != 3:
        raise ValueError(f"Unexpected ref image shape: {data.shape}")
    shape = tuple(int(x) for x in data.shape)
    affine = np.asarray(getattr(img, "affine", np.eye(4)), dtype=float)
    return shape, affine.tolist()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def _collect_env_info() -> Dict[str, Any]:
    info = {
        "python_version": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "numpy_version": np.__version__,
    }
    try:
        import sklearn  # type: ignore

        info["sklearn_version"] = sklearn.__version__
    except Exception:
        info["sklearn_version"] = "not_installed"
    try:
        import nibabel  # type: ignore

        info["nibabel_version"] = nibabel.__version__
    except Exception:
        info["nibabel_version"] = "not_installed"
    try:
        import nilearn  # type: ignore

        info["nilearn_version"] = nilearn.__version__
    except Exception:
        info["nilearn_version"] = "not_installed"
    return info


def _outer_cv_proba_classification(
    *,
    y_arr: np.ndarray,
    X: Optional[np.ndarray],
    outer_cv,
    inner_cv,
    pipe,
    param_grid: Any,
    cfg: ResponderMLConfig,
    efield_imgs: Sequence[Any],
    active_indices: Sequence[Optional[int]],
    logger,
    log_progress: bool = True,
    n_jobs_override: Optional[int] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]], Optional[List[int]]]:
    from sklearn.model_selection import GridSearchCV

    use_cv_selection = (
        cfg.feature_reduction_approach == "stats_ttest"
        and cfg.ttest_cv_feature_selection
    )
    proba = np.full(shape=(len(y_arr),), fill_value=np.nan, dtype=float)
    best_params_per_fold: List[Dict[str, Any]] = []
    n_selected_per_fold: List[int] = []

    for fold_idx, (train_idx, test_idx) in enumerate(
        outer_cv.split(np.zeros_like(y_arr), y_arr), start=1
    ):
        if log_progress and cfg.verbose:
            logger.info(
                f"Outer fold {fold_idx}/{outer_cv.n_splits}: tuning hyperparameters…"
            )
        if use_cv_selection:
            train_active_indices = [
                active_indices[i]
                for i in train_idx
                if active_indices[i] is not None
            ]
            train_active_indices = [int(i) for i in train_active_indices]
            train_active_imgs = [efield_imgs[i] for i in train_active_indices]
            train_active_y = [
                int(y_arr[i]) for i in train_idx if active_indices[i] is not None
            ]
            if len(train_active_imgs) < 4:
                raise ValueError(
                    "CV-based t-test feature selection requires at least 4 active training subjects."
                )
            voxel_coords, ref_img, _shape = select_ttest_voxel_coords(
                train_active_imgs,
                train_active_y,
                p_threshold=cfg.ttest_p_threshold,
            )
            n_selected_per_fold.append(len(voxel_coords))

            test_active_indices = [
                active_indices[i]
                for i in test_idx
                if active_indices[i] is not None
            ]
            test_active_indices = [int(i) for i in test_active_indices]
            test_active_imgs = [efield_imgs[i] for i in test_active_indices]

            fm_train = extract_voxel_features_by_coords(
                train_active_imgs, voxel_coords, ref_img=ref_img
            )
            fm_test = extract_voxel_features_by_coords(
                test_active_imgs, voxel_coords, ref_img=ref_img
            )
            n_features = fm_train.X.shape[1]
            X_tr = np.zeros((len(train_idx), n_features), dtype=float)
            X_te = np.zeros((len(test_idx), n_features), dtype=float)

            train_map = {
                idx: fm_train.X[i] for i, idx in enumerate(train_active_indices)
            }
            test_map = {idx: fm_test.X[i] for i, idx in enumerate(test_active_indices)}

            for pos, idx in enumerate(train_idx):
                active_idx = active_indices[idx]
                if active_idx is None:
                    continue
                X_tr[pos, :] = train_map[int(active_idx)]
            for pos, idx in enumerate(test_idx):
                active_idx = active_indices[idx]
                if active_idx is None:
                    continue
                X_te[pos, :] = test_map[int(active_idx)]
        else:
            if X is None:
                raise RuntimeError("X is required when CV feature selection is disabled")
            X_tr, X_te = X[train_idx], X[test_idx]

        y_tr = y_arr[train_idx]
        gs = GridSearchCV(
            pipe,
            param_grid=param_grid,
            scoring="roc_auc",
            cv=inner_cv,
            n_jobs=int(n_jobs_override) if n_jobs_override is not None else int(cfg.n_jobs),
            refit=True,
            verbose=(1 if cfg.verbose and log_progress else 0),
        )
        gs.fit(X_tr, y_tr)
        best_params_per_fold.append(dict(gs.best_params_))

        p_te = gs.predict_proba(X_te)[:, 1]
        proba[test_idx] = p_te
        if log_progress and cfg.verbose:
            logger.info(
                f"Outer fold {fold_idx}/{outer_cv.n_splits}: done. best={gs.best_params_}"
            )

    if np.isnan(proba).any():
        raise RuntimeError("Internal error: some CV predictions were not generated")
    return proba, best_params_per_fold, (n_selected_per_fold or None)


def _outer_cv_pred_regression(
    *,
    y_arr: np.ndarray,
    X: Optional[np.ndarray],
    outer_cv,
    inner_cv,
    pipe,
    param_grid: Any,
    cfg: ResponderMLConfig,
    efield_imgs: Sequence[Any],
    active_indices: Sequence[Optional[int]],
    logger,
    log_progress: bool = True,
    n_jobs_override: Optional[int] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]], Optional[List[int]]]:
    from sklearn.model_selection import GridSearchCV

    use_cv_selection = (
        cfg.feature_reduction_approach in ("stats_ttest", "stats_fregression")
        and cfg.ttest_cv_feature_selection
    )
    preds = np.full(shape=(len(y_arr),), fill_value=np.nan, dtype=float)
    best_params_per_fold: List[Dict[str, Any]] = []
    n_selected_per_fold: List[int] = []

    for fold_idx, (train_idx, test_idx) in enumerate(outer_cv.split(y_arr), start=1):
        if log_progress and cfg.verbose:
            logger.info(
                f"Outer fold {fold_idx}/{outer_cv.n_splits}: tuning hyperparameters…"
            )
        if use_cv_selection:
            train_active_indices = [
                active_indices[i]
                for i in train_idx
                if active_indices[i] is not None
            ]
            train_active_indices = [int(i) for i in train_active_indices]
            train_active_imgs = [efield_imgs[i] for i in train_active_indices]
            train_active_y = [
                float(y_arr[i]) for i in train_idx if active_indices[i] is not None
            ]
            if len(train_active_imgs) < 4:
                raise ValueError(
                    "CV-based feature selection requires at least 4 active training subjects."
                )
            if cfg.feature_reduction_approach == "stats_ttest":
                voxel_coords, ref_img, _shape = select_ttest_voxel_coords(
                    train_active_imgs,
                    train_active_y,
                    p_threshold=cfg.ttest_p_threshold,
                )
            else:
                voxel_coords, ref_img, _shape = select_fregression_voxel_coords(
                    train_active_imgs,
                    train_active_y,
                    p_threshold=cfg.ttest_p_threshold,
                )
            n_selected_per_fold.append(len(voxel_coords))

            test_active_indices = [
                active_indices[i]
                for i in test_idx
                if active_indices[i] is not None
            ]
            test_active_indices = [int(i) for i in test_active_indices]
            test_active_imgs = [efield_imgs[i] for i in test_active_indices]

            fm_train = extract_voxel_features_by_coords(
                train_active_imgs, voxel_coords, ref_img=ref_img
            )
            fm_test = extract_voxel_features_by_coords(
                test_active_imgs, voxel_coords, ref_img=ref_img
            )
            n_features = fm_train.X.shape[1]
            X_tr = np.zeros((len(train_idx), n_features), dtype=float)
            X_te = np.zeros((len(test_idx), n_features), dtype=float)

            train_map = {
                idx: fm_train.X[i] for i, idx in enumerate(train_active_indices)
            }
            test_map = {idx: fm_test.X[i] for i, idx in enumerate(test_active_indices)}

            for pos, idx in enumerate(train_idx):
                active_idx = active_indices[idx]
                if active_idx is None:
                    continue
                X_tr[pos, :] = train_map[int(active_idx)]
            for pos, idx in enumerate(test_idx):
                active_idx = active_indices[idx]
                if active_idx is None:
                    continue
                X_te[pos, :] = test_map[int(active_idx)]
        else:
            if X is None:
                raise RuntimeError("X is required when CV feature selection is disabled")
            X_tr, X_te = X[train_idx], X[test_idx]

        y_tr = y_arr[train_idx]
        gs = GridSearchCV(
            pipe,
            param_grid=param_grid,
            scoring="neg_mean_squared_error",
            cv=inner_cv,
            n_jobs=int(n_jobs_override) if n_jobs_override is not None else int(cfg.n_jobs),
            refit=True,
            verbose=(1 if cfg.verbose and log_progress else 0),
        )
        gs.fit(X_tr, y_tr)
        best_params_per_fold.append(dict(gs.best_params_))

        preds[test_idx] = gs.predict(X_te)
        if log_progress and cfg.verbose:
            logger.info(
                f"Outer fold {fold_idx}/{outer_cv.n_splits}: done. best={gs.best_params_}"
            )

    if np.isnan(preds).any():
        raise RuntimeError("Internal error: some CV predictions were not generated")
    return preds, best_params_per_fold, (n_selected_per_fold or None)


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
    run_name = cfg.run_name
    out_dir = cfg.output_dir or default_output_dir(run_name=run_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "responder_ml.log"
    logger = logging_util.get_logger(
        "tit.ml.responder.train",
        log_file=str(log_path),
        overwrite=True,
        console=True,
    )

    try:
        logger.info(f"Command line: {' '.join(sys.argv)}")
        cfg_payload = _json_safe(asdict(cfg))
        logger.info("Run config:\n%s", json.dumps(cfg_payload, indent=2, sort_keys=True))
        logger.info(
            "Environment:\n%s",
            json.dumps(_collect_env_info(), indent=2, sort_keys=True),
        )
        logger.info(f"Output dir: {out_dir}")
        logger.info(f"Loading CSV: {cfg.csv_path}")
        subjects = load_subject_table(
            cfg.csv_path,
            target_col=cfg.target_col,
            condition_col=cfg.condition_col,
            sham_value=cfg.sham_value,
            task=cfg.task,
            require_target=True,
        )

        atlas_path = cfg.atlas_path
        if atlas_path is None:
            atlas_path = default_glasser_atlas_path()
        logger.info(f"Atlas: {atlas_path}")

    # Condition-aware loading:
    # - sham subjects (condition == sham_value) are kept even if they have no NIfTI;
    #   their ROI features are set to 0.
    # - active subjects must have NIfTIs; missing files are skipped (as before).
        use_condition = bool(cfg.condition_col)
        sham_value = str(cfg.sham_value or "sham")

        if use_condition:
            sham_subjects = [
                s
                for s in subjects
                if is_sham_condition(s.condition, sham_value=sham_value)
            ]
            active_subjects = [
                s
                for s in subjects
                if not is_sham_condition(s.condition, sham_value=sham_value)
            ]
        else:
            sham_subjects = []
            active_subjects = list(subjects)

        if use_condition:
            logger.info(
                f"Loaded {len(subjects)} rows. Active={len(active_subjects)}, sham={len(sham_subjects)}. Loading E-field NIfTIs for active…"
            )
        else:
            logger.info(f"Loaded {len(subjects)} rows. Loading E-field NIfTIs…")

    # Load E-field NIfTIs only for active subjects.
        efield_imgs, y_active, kept_active = load_efield_images(
            active_subjects,
            efield_filename_pattern=cfg.efield_filename_pattern,
            logger=logger,
        )
        logger.info(f"Loaded {len(kept_active)} active NIfTIs.")

        # Assemble full subject list (kept order) and map active subjects to image indices.
        active_index_map = {
            (s.subject_id, s.simulation_name): i for i, s in enumerate(kept_active)
        }
        kept: List[SubjectRow] = []
        y: List[Optional[float]] = []
        active_indices: List[Optional[int]] = []
        for s in subjects:
            k = (s.subject_id, s.simulation_name)
            if use_condition and is_sham_condition(s.condition, sham_value=sham_value):
                kept.append(s)
                y.append(s.target)
                active_indices.append(None)
                continue
            if k not in active_index_map:
                continue
            kept.append(s)
            y.append(s.target)
            active_indices.append(int(active_index_map[k]))

        if not kept:
            raise FileNotFoundError(
                "No subjects could be used (no active NIfTIs and/or no sham rows)."
            )

        # Extract features for non-CV selection paths.
        if cfg.task == "classification" and cfg.feature_reduction_approach == "stats_fregression":
            raise ValueError("stats_fregression is only valid for regression tasks")
        if cfg.task == "regression" and cfg.feature_reduction_approach == "stats_ttest":
            raise ValueError("stats_ttest is only valid for classification tasks")

        use_cv_selection = (
            cfg.feature_reduction_approach in ("stats_ttest", "stats_fregression")
            and cfg.ttest_cv_feature_selection
        )
        fm: Optional[FeatureMatrix] = None
        feature_names: List[str] = []
        X: Optional[np.ndarray] = None

        if use_cv_selection:
            logger.info(
                "CV-based voxel selection enabled: statistical feature selection will run within each outer fold."
            )
        else:
            approach_desc = (
                "ROI features (mean/top10mean)"
                if cfg.feature_reduction_approach == "atlas_roi"
                else f"statistical features (p<{cfg.ttest_p_threshold})"
            )
            logger.info(f"Extracting {approach_desc}…")
            fm = extract_features(
                efield_imgs,
                y=y_active,
                feature_reduction_approach=cfg.feature_reduction_approach,
                atlas_path=atlas_path,
                ttest_p_threshold=cfg.ttest_p_threshold,
            )
            feature_names = fm.feature_names
            n_features = len(feature_names)
            key_active = [(s.subject_id, s.simulation_name) for s in kept_active]
            active_map = {k: fm.X[i, :] for i, k in enumerate(key_active)}
            X_rows: List[np.ndarray] = []
            for s, active_idx in zip(kept, active_indices):
                if active_idx is None:
                    X_rows.append(np.zeros((n_features,), dtype=float))
                else:
                    k = (s.subject_id, s.simulation_name)
                    X_rows.append(np.asarray(active_map[k], dtype=float))
            X = np.vstack(X_rows).astype(float)

        if any(v is None for v in y):
            raise ValueError(
                f"Missing target values in column {cfg.target_col!r}. Training requires targets for all subjects."
            )
    except Exception:
        logger.exception("Responder ML training failed.")
        raise

    if cfg.task == "classification":
        y_arr = np.asarray([int(v) for v in y], dtype=int)
    else:
        y_arr = np.asarray([float(v) for v in y], dtype=float)
    if cfg.verbose:
        if cfg.task == "classification":
            if X is not None:
                logger.info(
                    f"Feature matrix: X={X.shape}, y={y_arr.shape} (pos={(y_arr==1).sum()}, neg={(y_arr==0).sum()})"
                )
            else:
                logger.info(
                    f"Feature matrix: y={y_arr.shape} (pos={(y_arr==1).sum()}, neg={(y_arr==0).sum()})"
                )
        else:
            if X is not None:
                logger.info(f"Feature matrix: X={X.shape}, y={y_arr.shape}")
            else:
                logger.info(f"Feature matrix: y={y_arr.shape}")

    if cfg.task == "classification":
        outer_splits = _safe_splits(y_arr.tolist(), cfg.outer_splits)
        inner_splits = _safe_splits(y_arr.tolist(), cfg.inner_splits)
    else:
        outer_splits = _safe_splits_regression(len(y_arr), cfg.outer_splits)
        inner_splits = _safe_splits_regression(len(y_arr), cfg.inner_splits)
    if cfg.verbose:
        logger.info(
            f"Nested CV: outer={outer_splits} folds, inner={inner_splits} folds, n_jobs={cfg.n_jobs}"
        )

    if cfg.task == "classification":
        outer_cv = StratifiedKFold(
            n_splits=outer_splits, shuffle=True, random_state=cfg.random_state
        )
        inner_cv = StratifiedKFold(
            n_splits=inner_splits, shuffle=True, random_state=cfg.random_state + 1
        )
    else:
        outer_cv = KFold(
            n_splits=outer_splits, shuffle=True, random_state=cfg.random_state
        )
        inner_cv = KFold(
            n_splits=inner_splits, shuffle=True, random_state=cfg.random_state + 1
        )

    if cfg.task == "classification":
        pipe = Pipeline(
            steps=[
                ("scaler", StandardScaler(with_mean=True, with_std=True)),
                (
                    "clf",
                    LogisticRegression(
                        penalty="elasticnet",
                        solver="saga",
                        class_weight="balanced",
                        max_iter=int(cfg.max_iter),
                        tol=float(cfg.tol),
                        random_state=cfg.random_state,
                    ),
                ),
            ]
        )
        # Expanded hyperparameter grid (best-practice: explore C on log scale, penalties, class weights)
        C_grid = np.logspace(-3, 3, 7).tolist()
        param_grid = [
            {
                "clf__penalty": ["l2"],
                "clf__C": C_grid,
                "clf__class_weight": [None, "balanced"],
            },
            {
                "clf__penalty": ["l1"],
                "clf__C": C_grid,
                "clf__class_weight": [None, "balanced"],
            },
            {
                "clf__penalty": ["elasticnet"],
                "clf__C": C_grid,
                "clf__l1_ratio": [0.1, 0.3, 0.5, 0.7, 0.9],
                "clf__class_weight": [None, "balanced"],
            },
        ]

        proba, best_params_per_fold, n_selected_per_fold = _outer_cv_proba_classification(
            y_arr=y_arr,
            X=X,
            outer_cv=outer_cv,
            inner_cv=inner_cv,
            pipe=pipe,
            param_grid=param_grid,
            cfg=cfg,
            efield_imgs=efield_imgs,
            active_indices=active_indices,
            logger=logger,
            log_progress=True,
        )
    else:
        pipe = Pipeline(
            steps=[
                ("scaler", StandardScaler(with_mean=True, with_std=True)),
                (
                    "reg",
                    ElasticNet(
                        alpha=1.0,
                        l1_ratio=0.5,
                        max_iter=int(cfg.max_iter),
                        tol=float(cfg.tol),
                    ),
                ),
            ]
        )
        alpha_grid = np.logspace(-4, 1, 6).tolist()
        param_grid = {
            "reg__alpha": alpha_grid,
            "reg__l1_ratio": [0.1, 0.3, 0.5, 0.7, 0.9],
        }

        preds, best_params_per_fold, n_selected_per_fold = _outer_cv_pred_regression(
            y_arr=y_arr,
            X=X,
            outer_cv=outer_cv,
            inner_cv=inner_cv,
            pipe=pipe,
            param_grid=param_grid,
            cfg=cfg,
            efield_imgs=efield_imgs,
            active_indices=active_indices,
            logger=logger,
            log_progress=True,
        )

    metrics: Dict[str, Any] = {
        "task": cfg.task,
        "target_col": str(cfg.target_col),
        "n_subjects_total": len(subjects),
        "n_subjects_used": int(len(kept)),
        "outer_splits": int(outer_splits),
        "inner_splits": int(inner_splits),
        "best_params_per_fold": best_params_per_fold,
    }
    if cfg.task == "classification":
        metrics.update(
            {
                "roc_auc": float(roc_auc_score(y_arr, proba)),
                "pr_auc": float(average_precision_score(y_arr, proba)),
                "pos_count": int((y_arr == 1).sum()),
                "neg_count": int((y_arr == 0).sum()),
            }
        )
    else:
        mse = float(mean_squared_error(y_arr, preds))
        rmse = float(np.sqrt(mse))
        metrics.update(
            {
                "r2": float(r2_score(y_arr, preds)),
                "rmse": rmse,
                "mae": float(mean_absolute_error(y_arr, preds)),
            }
        )
    if n_selected_per_fold is not None:
        metrics["n_selected_per_fold"] = n_selected_per_fold

    # Fit final model on all data (inner CV for hyperparams)
    if X is None:
        logger.info("Extracting final feature set on all data for model fitting…")
        fm = extract_features(
            efield_imgs,
            y=y_active,
            feature_reduction_approach=cfg.feature_reduction_approach,
            atlas_path=atlas_path,
            ttest_p_threshold=cfg.ttest_p_threshold,
        )
        feature_names = fm.feature_names
        n_features = len(feature_names)
        key_active = [(s.subject_id, s.simulation_name) for s in kept_active]
        active_map = {k: fm.X[i, :] for i, k in enumerate(key_active)}
        X_rows: List[np.ndarray] = []
        for s, active_idx in zip(kept, active_indices):
            if active_idx is None:
                X_rows.append(np.zeros((n_features,), dtype=float))
            else:
                k = (s.subject_id, s.simulation_name)
                X_rows.append(np.asarray(active_map[k], dtype=float))
        X = np.vstack(X_rows).astype(float)

    if cfg.feature_reduction_approach in ("stats_ttest", "stats_fregression"):
        n_selected = len(feature_names)
        logger.warning(
            f"WARNING: Statistical feature selection selected {n_selected} features from {efield_imgs[0].shape[0] * efield_imgs[0].shape[1] * efield_imgs[0].shape[2]} total voxels."
        )
        if cfg.ttest_cv_feature_selection:
            logger.info(
                "CV-based feature selection used for CV; final model uses selection on all training data."
            )
        else:
            logger.warning(
                "WARNING: Feature selection is performed on ALL training data before CV. "
                "This may give optimistic performance estimates. Consider --ttest-cv-feature-selection for better generalization."
            )
        logger.warning(f"Small sample size (n={len(y_active)}) increases overfitting risk.")
        if n_selected < 10:
            logger.warning("WARNING: Very few features selected - high risk of overfitting!")
        elif n_selected > len(y_active) // 2:
            logger.warning("WARNING: Many features selected relative to sample size - consider more conservative threshold.")
    gs_final = GridSearchCV(
        pipe,
        param_grid=param_grid,
        scoring=("roc_auc" if cfg.task == "classification" else "neg_mean_squared_error"),
        cv=inner_cv,
        n_jobs=int(cfg.n_jobs),
        refit=True,
        verbose=(1 if cfg.verbose else 0),
    )
    if cfg.verbose:
        logger.info("Fitting final model on all data (inner CV)…")
    gs_final.fit(X, y_arr)
    best_est = gs_final.best_estimator_
    best_params_final: Dict[str, Any] = dict(gs_final.best_params_ or {})
    metrics["best_params_final"] = best_params_final

    model_path = out_dir / "model.joblib"
    metrics_path = out_dir / "metrics.json"
    preds_path = out_dir / "cv_predictions.csv"
    feat_names_path = out_dir / "feature_names.json"

    if int(getattr(cfg, "permutation_tests", 0)) > 0:
        rng = np.random.default_rng(int(cfg.random_state) + 1000)
        n_perm = int(getattr(cfg, "permutation_tests", 0))
        logger.info(f"Running permutation tests (n={n_perm})…")
        y_perms = [rng.permutation(y_arr) for _ in range(n_perm)]

        def _perm_score(y_perm: np.ndarray) -> float:
            if cfg.task == "classification":
                perm_proba, _bp, _sel = _outer_cv_proba_classification(
                    y_arr=y_perm,
                    X=X,
                    outer_cv=outer_cv,
                    inner_cv=inner_cv,
                    pipe=pipe,
                    param_grid=param_grid,
                    cfg=cfg,
                    efield_imgs=efield_imgs,
                    active_indices=active_indices,
                    logger=logger,
                    log_progress=False,
                    n_jobs_override=1 if int(cfg.n_jobs) > 1 else None,
                )
                return float(roc_auc_score(y_perm, perm_proba))
            perm_preds, _bp, _sel = _outer_cv_pred_regression(
                y_arr=y_perm,
                X=X,
                outer_cv=outer_cv,
                inner_cv=inner_cv,
                pipe=pipe,
                param_grid=param_grid,
                cfg=cfg,
                efield_imgs=efield_imgs,
                active_indices=active_indices,
                logger=logger,
                log_progress=False,
                n_jobs_override=1 if int(cfg.n_jobs) > 1 else None,
            )
            return float(r2_score(y_perm, perm_preds))

        if int(cfg.n_jobs) > 1:
            from joblib import Parallel, delayed

            # Use threads to avoid heavy process memory overhead on large NIfTIs.
            perm_scores = Parallel(n_jobs=int(cfg.n_jobs), prefer="threads")(
                delayed(_perm_score)(y_perm) for y_perm in y_perms
            )
        else:
            perm_scores = [_perm_score(y_perm) for y_perm in y_perms]
        perm_scores_arr = np.asarray(perm_scores, dtype=float)
        if cfg.task == "classification":
            obs = float(metrics["roc_auc"])
            p_val = float(
                (np.sum(perm_scores_arr >= obs) + 1.0) / (len(perm_scores_arr) + 1.0)
            )
            metrics["permutation"] = {
                "n_permutations": int(n_perm),
                "roc_auc_observed": obs,
                "roc_auc_mean": float(perm_scores_arr.mean()),
                "roc_auc_std": float(perm_scores_arr.std()),
                "roc_auc_p_value": p_val,
            }
        else:
            obs = float(metrics["r2"])
            p_val = float(
                (np.sum(perm_scores_arr >= obs) + 1.0) / (len(perm_scores_arr) + 1.0)
            )
            metrics["permutation"] = {
                "n_permutations": int(n_perm),
                "r2_observed": obs,
                "r2_mean": float(perm_scores_arr.mean()),
                "r2_std": float(perm_scores_arr.std()),
                "r2_p_value": p_val,
            }

    bundle: Dict[str, Any] = {
        "model": best_est,
        "feature_names": fm.feature_names,
        "atlas_path": str(fm.atlas_path),
        "config": asdict(cfg),
    }
    if cfg.feature_reduction_approach in ("stats_ttest", "stats_fregression"):
        ref_shape, ref_affine = _ref_image_shape_and_affine(efield_imgs[0])
        bundle["voxel_ref_shape"] = ref_shape
        bundle["voxel_ref_affine"] = ref_affine

    joblib.dump(bundle, model_path)

    # Optional bootstrap stability for coefficients (off by default).
    if int(getattr(cfg, "bootstrap_samples", 0)) > 0:
        rng = np.random.default_rng(int(cfg.random_state))
        B = int(cfg.bootstrap_samples)
        coef_mat = np.zeros((B, len(fm.feature_names)), dtype=float)
        for b in range(B):
            idx = rng.integers(0, len(y_arr), size=len(y_arr))
            Xb = X[idx]
            yb = y_arr[idx]
            if cfg.task == "classification":
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
                                l1_ratio=float(best_params_final.get("clf__l1_ratio", 0.5)),
                            ),
                        ),
                    ]
                )
            else:
                est_b = Pipeline(
                    steps=[
                        ("scaler", StandardScaler(with_mean=True, with_std=True)),
                        (
                            "reg",
                            ElasticNet(
                                max_iter=5000,
                                alpha=float(best_params_final.get("reg__alpha", 1.0)),
                                l1_ratio=float(best_params_final.get("reg__l1_ratio", 0.5)),
                            ),
                        ),
                    ]
                )
            est_b.fit(Xb, yb)
            if cfg.task == "classification":
                coef_mat[b, :] = np.asarray(
                    est_b.named_steps["clf"].coef_[0], dtype=float
                )
            else:
                coef_mat[b, :] = np.asarray(est_b.named_steps["reg"].coef_, dtype=float)

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
        logger.info(f"Saved coefficient stability: {stab_path}")

    metrics_path.write_text(json.dumps(metrics, indent=2))
    feat_names_path.write_text(json.dumps(fm.feature_names, indent=2))

    # Write per-subject predictions
    if cfg.task == "classification":
        lines = [f"subject_id,simulation_name,{cfg.target_col},proba"]
        for s, yy, pp in zip(kept, y_arr.tolist(), proba.tolist()):
            lines.append(f"{s.subject_id},{s.simulation_name},{int(yy)},{float(pp)}")
    else:
        lines = [f"subject_id,simulation_name,{cfg.target_col},prediction"]
        for s, yy, pp in zip(kept, y_arr.tolist(), preds.tolist()):
            lines.append(f"{s.subject_id},{s.simulation_name},{float(yy)},{float(pp)}")
    preds_path.write_text("\n".join(lines) + "\n")

    logger.info(f"Saved model: {model_path}")
    logger.info(f"Saved metrics: {metrics_path}")
    if cfg.verbose:
        logger.info(f"Done in {time.perf_counter() - t0:.1f}s")

    return TrainArtifacts(
        output_dir=out_dir,
        model_path=model_path,
        metrics_path=metrics_path,
        predictions_csv=preds_path,
        feature_names_json=feat_names_path,
    )
