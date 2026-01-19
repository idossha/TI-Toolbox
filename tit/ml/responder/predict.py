from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import joblib
import sklearn

from tit import logger as logging_util

from .config import DEFAULT_EFIELD_FILENAME_PATTERN
from .dataset import is_sham_condition, load_efield_images, load_subject_table
from .features import (
    extract_features,
    extract_voxel_features_by_coords,
    parse_voxel_feature_names,
    FeatureMatrix,
)


@dataclass(frozen=True)
class PredictArtifacts:
    output_csv: Path


def predict_from_csv(
    *,
    model_path: Path,
    csv_path: Path,
    output_csv: Optional[Path] = None,
) -> PredictArtifacts:
    """
    Predict for subjects in a CSV using a trained model bundle.

    The target column is optional at prediction time.
    - Writes probability (`proba`)
    """
    out = output_csv or (model_path.parent / "predictions.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    log_path = out.parent / "responder_ml.log"

    logger = logging_util.get_logger(
        "tit.ml.responder.predict",
        log_file=str(log_path),
        overwrite=False,
        console=True,
    )

    try:
        if not model_path.is_file():
            raise FileNotFoundError(f"Model not found: {model_path}")

        bundle = joblib.load(model_path)
        est = bundle.get("model")
        atlas_path = bundle.get("atlas_path")
        feature_names = list(bundle.get("feature_names") or [])
        cfg: Dict[str, Any] = dict(bundle.get("config") or {})
        if "voxel_ref_shape" not in cfg and "voxel_ref_shape" in bundle:
            cfg["voxel_ref_shape"] = bundle.get("voxel_ref_shape")
        if "voxel_ref_affine" not in cfg and "voxel_ref_affine" in bundle:
            cfg["voxel_ref_affine"] = bundle.get("voxel_ref_affine")
        target_col = str(cfg.get("target_col") or "response")
        task = str(cfg.get("task") or "classification")
        efield_filename_pattern = str(
            cfg.get("efield_filename_pattern") or DEFAULT_EFIELD_FILENAME_PATTERN
        )
        condition_col = cfg.get("condition_col")
        sham_value = str(cfg.get("sham_value") or "sham")
        feature_reduction_approach = str(
            cfg.get("feature_reduction_approach") or "atlas_roi"
        )
        ttest_p_threshold = float(cfg.get("ttest_p_threshold") or 0.001)

        logger.info(f"Model: {model_path}")
        logger.info(f"CSV: {csv_path}")
        logger.info(f"Output: {out}")

        subjects = load_subject_table(
            csv_path,
            target_col=target_col,
            condition_col=str(condition_col) if condition_col else None,
            sham_value=sham_value,
            require_target=False,
        )

        use_condition = bool(condition_col)
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
            logger.info(
                f"Subjects: total={len(subjects)}, active={len(active_subjects)}, sham={len(sham_subjects)}"
            )
        else:
            sham_subjects = []
            active_subjects = list(subjects)
            logger.info(f"Subjects: total={len(subjects)}")

        imgs, y_active, kept_active = load_efield_images(
            active_subjects,
            efield_filename_pattern=efield_filename_pattern,
            logger=logger,
        )

        if feature_reduction_approach in ("stats_ttest", "stats_fregression"):
            # For stats_ttest models, use the pre-selected voxel features from training
            ref_shape = cfg.get("voxel_ref_shape")
            ref_affine = cfg.get("voxel_ref_affine")
            ref_img = None
            if ref_shape is not None and ref_affine is not None:
                try:
                    import nibabel as nib  # type: ignore

                    ref_img = nib.Nifti1Image(
                        np.zeros(tuple(ref_shape), dtype=np.float32),
                        np.asarray(ref_affine, dtype=float),
                    )
                except Exception:
                    ref_img = None
            fm = _extract_voxel_features_for_prediction(
                imgs, feature_names, ref_img=ref_img
            )
        else:
            # For atlas_roi models, use the standard atlas-based extraction
            fm = extract_features(
                imgs,
                y=None,  # Not needed for atlas_roi
                feature_reduction_approach=feature_reduction_approach,
                atlas_path=Path(atlas_path) if atlas_path else None,
                ttest_p_threshold=ttest_p_threshold,
            )
        if feature_names and fm.feature_names != feature_names:
            raise RuntimeError(
                "Feature ordering mismatch between model bundle and newly extracted features. "
                "Ensure the same atlas and feature definition are used."
            )

        n_features = fm.X.shape[1]
        active_map = {
            (s.subject_id, s.simulation_name): fm.X[i, :]
            for i, s in enumerate(kept_active)
        }
        kept = []
        y = []
        X_rows = []
        for s in subjects:
            k = (s.subject_id, s.simulation_name)
            if use_condition and is_sham_condition(s.condition, sham_value=sham_value):
                kept.append(s)
                y.append(s.target)
                X_rows.append(np.zeros((n_features,), dtype=float))
                continue
            if k not in active_map:
                continue
            kept.append(s)
            y.append(s.target)
            X_rows.append(np.asarray(active_map[k], dtype=float))
        if not kept:
            raise FileNotFoundError(
                "No subjects could be used for prediction (no active NIfTIs and/or no sham rows)."
            )
        X = np.vstack(X_rows).astype(float)

        if task == "classification":
            proba = est.predict_proba(X)[:, 1]
            lines = [f"subject_id,simulation_name,{target_col},proba"]
            for s, yy, pp in zip(kept, y, proba.tolist()):
                tgt = "" if yy is None else int(float(yy))
                lines.append(f"{s.subject_id},{s.simulation_name},{tgt},{float(pp)}")
        elif task == "regression":
            preds = est.predict(X)
            lines = [f"subject_id,simulation_name,{target_col},prediction"]
            for s, yy, pp in zip(kept, y, preds.tolist()):
                tgt = "" if yy is None else float(yy)
                lines.append(f"{s.subject_id},{s.simulation_name},{tgt},{float(pp)}")
        else:
            raise RuntimeError(f"Unknown task type: {task}")

        out.write_text("\n".join(lines) + "\n")
        logger.info(f"Saved predictions: {out}")
        return PredictArtifacts(output_csv=out)
    except Exception:
        logger.exception("Responder ML predict failed.")
        raise


def _extract_voxel_features_for_prediction(
    efield_imgs: Any,
    feature_names: list[str],
    *,
    ref_img: Optional[Any] = None,
) -> FeatureMatrix:
    """
    Extract voxel features for prediction using pre-selected voxel coordinates.

    For stats_ttest models, the feature_names contain voxel coordinates like "voxel_X_Y_Z".
    During prediction, we extract the E-field values at these specific coordinates.
    """
    if not feature_names:
        raise RuntimeError("No feature names available from trained model")

    voxel_coords = parse_voxel_feature_names(feature_names)
    if not voxel_coords:
        raise RuntimeError(
            f"No valid voxel coordinates found in feature names: {feature_names[:5]}..."
        )

    fm = extract_voxel_features_by_coords(efield_imgs, voxel_coords, ref_img=ref_img)
    return FeatureMatrix(X=fm.X, feature_names=feature_names, atlas_path=None)
