from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from tit import logger as logging_util
from tit.plotting.responder_ml import (
    create_weight_map_visualizations,
    plot_intensity_response_fig5,
    plot_model_diagnostics_from_predictions_csv,
    plot_top_coefficients,
)

from .config import default_glasser_atlas_path, default_glasser_labels_path
from .dataset import is_sham_condition, load_efield_images, load_subject_table
from .features import _ensure_3d_data, parse_voxel_feature_names
from tit.tools.extract_labels import label_ids_in_nifti, load_labels_tsv


@dataclass(frozen=True)
class ExplainArtifacts:
    output_dir: Path
    roi_weights_csv: Path
    weight_maps: List[Path]
    figures: List[Path] = field(default_factory=list)


def _atlas_sidecar_tsv_path(atlas_path: Path) -> Path:
    """
    Sidecar labels convention: same basename as atlas NIfTI, but `.tsv`.

    Important: for `.nii.gz`, `Path.with_suffix()` only replaces the last suffix
    (i.e., `.gz`), which would yield `*.nii.tsv`. We want `*.tsv`.
    """
    name = atlas_path.name
    if name.lower().endswith(".nii.gz"):
        return atlas_path.with_name(name[: -len(".nii.gz")] + ".tsv")
    if name.lower().endswith(".nii"):
        return atlas_path.with_name(name[: -len(".nii")] + ".tsv")
    return atlas_path.with_suffix(".tsv")


def _resolve_labels_tsv(
    *, atlas_path: Path, labels_path: Optional[Path]
) -> Optional[Path]:
    """
    Resolve labels TSV path.

    Default convention:
    - labels file sits next to the atlas NIfTI and shares its basename:
      `<atlas_basename>.tsv`
    """
    if labels_path is not None:
        return Path(labels_path)

    # 1) Prefer sidecar TSV next to the atlas, sharing basename.
    sidecar = _atlas_sidecar_tsv_path(atlas_path)
    if sidecar.is_file():
        return sidecar

    # 2) Fallback: default Glasser TSV (repo resources).
    p = default_glasser_labels_path()
    if p is not None and p.is_file():
        return p
    return None


def _load_labels_map(
    *, atlas_path: Path, labels_path: Optional[Path]
) -> Dict[int, str]:
    """
    Load label map from TSV and validate 1:1 agreement with atlas NIfTI IDs.

    Rules:
    - Only `.tsv` is accepted.
    - TSV must contain at least `number` and `label` columns (RGB optional).
    - TSV IDs must match the atlas label IDs (excluding 0) exactly.
    """
    p = _resolve_labels_tsv(atlas_path=atlas_path, labels_path=labels_path)
    if p is None:
        raise FileNotFoundError(
            "Labels TSV not found. Expected sidecar labels file next to the atlas: "
            f"{atlas_path.with_suffix('.tsv')} (or pass --atlas-labels-path)."
        )
    if p.suffix.lower() != ".tsv":
        raise ValueError(f"Labels file must be a .tsv: {p}")

    mapping = load_labels_tsv(p)
    atlas_ids = set(label_ids_in_nifti(atlas_path, exclude=(0,)))
    tsv_ids = set(mapping.keys())
    if atlas_ids != tsv_ids:
        missing = sorted(atlas_ids - tsv_ids)
        extra = sorted(tsv_ids - atlas_ids)
        msg = "Atlas/labels mismatch (must be 1:1).\n"
        if missing:
            msg += f"- Missing in TSV (first 25): {missing[:25]}\n"
        if extra:
            msg += f"- Extra in TSV (first 25): {extra[:25]}\n"
        msg += f"Atlas: {atlas_path}\nLabels: {p}"
        raise RuntimeError(msg)
    return mapping


def explain_model(
    *,
    model_path: Path,
    output_dir: Optional[Path] = None,
    atlas_path: Optional[Path] = None,
    atlas_labels_path: Optional[Path] = None,
) -> ExplainArtifacts:
    """
    Produce:
    - roi_weights.csv: per-ROI coefficients (for each feature stat)
    - weight_map_<stat>.nii.gz: voxel map where each ROI is filled with its coef
    - figures/feature_importance_top.png: top positive/negative coefficients
    - figures/model_diagnostics.png: standard evaluation plots if cv_predictions.csv is present
    """
    import joblib  # type: ignore
    import nibabel as nib  # type: ignore

    out_dir = output_dir or model_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "responder_ml.log"
    logger = logging_util.get_logger(
        "tit.ml.responder.explain",
        log_file=str(log_path),
        overwrite=False,
        console=True,
    )

    try:
        logger.info(f"Model: {model_path}")
        logger.info(f"Output dir: {out_dir}")

        if not model_path.is_file():
            raise FileNotFoundError(f"Model not found: {model_path}")

        bundle = joblib.load(model_path)
        est = bundle.get("model")
        feature_names: List[str] = list(bundle.get("feature_names") or [])
        atlas_from_model = bundle.get("atlas_path")
        config_from_model = dict(bundle.get("config", {}) or {})
        if "voxel_ref_shape" not in config_from_model and "voxel_ref_shape" in bundle:
            config_from_model["voxel_ref_shape"] = bundle.get("voxel_ref_shape")
        if "voxel_ref_affine" not in config_from_model and "voxel_ref_affine" in bundle:
            config_from_model["voxel_ref_affine"] = bundle.get("voxel_ref_affine")
        feature_reduction_approach = config_from_model.get(
            "feature_reduction_approach", "atlas_roi"
        )
        voxel_ref_shape = config_from_model.get("voxel_ref_shape")
        voxel_ref_affine = config_from_model.get("voxel_ref_affine")
        task = str(config_from_model.get("task") or "classification")
        target_col = str(config_from_model.get("target_col") or "response")
        csv_path_from_model = config_from_model.get("csv_path")

        if not feature_names:
            raise RuntimeError("Model bundle missing feature_names")

        # Handle different feature types based on approach
        if feature_reduction_approach in ("stats_ttest", "stats_fregression"):
            # For stats_* approaches, features are voxel coordinates like "voxel_X_Y_Z"
            artifacts = _explain_voxel_features(
                est=est,
                feature_names=feature_names,
                voxel_ref_shape=voxel_ref_shape,
                voxel_ref_affine=voxel_ref_affine,
                model_path=model_path,
                out_dir=out_dir,
                logger=logger,
            )
            _maybe_add_intensity_response_fig5(
                artifacts=artifacts,
                feature_reduction_approach=str(feature_reduction_approach),
                model_path=model_path,
                out_dir=out_dir,
                logger=logger,
                csv_path_from_model=csv_path_from_model,
                target_col=target_col,
                task=task,
                atlas_path=atlas_path,
                atlas_from_model=atlas_from_model,
                voxel_ref_shape=voxel_ref_shape,
                voxel_ref_affine=voxel_ref_affine,
                feature_names=feature_names,
                est=est,
            )
            return artifacts
        else:
            # For atlas_roi, features are ROI-based like "ROI_<id>__<stat>"
            pass  # Continue with existing ROI-based logic

            # Resolve atlas
            atlas_p: Optional[Path] = Path(atlas_from_model) if atlas_from_model else None
            if atlas_path is not None:
                atlas_p = Path(atlas_path)
            if atlas_p is None or not atlas_p.is_file():
                atlas_p = default_glasser_atlas_path()
            if atlas_p is None or not atlas_p.is_file():
                raise FileNotFoundError("Atlas not found. Provide --atlas-path.")
        
            # out_dir already resolved/created above
            figures_dir = out_dir / "figures"
            figures_dir.mkdir(parents=True, exist_ok=True)
        
            # Pull coefficients from pipeline (scaler + clf/reg) or bare estimator.
            core_est = est
            if hasattr(est, "named_steps"):
                if "clf" in est.named_steps:
                    core_est = est.named_steps["clf"]
                elif "reg" in est.named_steps:
                    core_est = est.named_steps["reg"]
            coef = getattr(core_est, "coef_", None)
            if coef is None:
                raise RuntimeError(
                    "Model does not expose coef_ (expected linear model such as logistic regression or elastic-net regression)"
                )
            coef = np.asarray(coef)
            if coef.ndim == 2:
                coef = coef[0]
            if coef.shape[0] != len(feature_names):
                raise RuntimeError("coef_ length does not match feature_names")
        
            # Parse ROI + stat from feature name: ROI_<id>__<stat>
            parsed: List[Tuple[int, str, float]] = []
            for name, w in zip(feature_names, coef.tolist()):
                roi_id = None
                stat = "unknown"
                if name.startswith("ROI_") and "__" in name:
                    left, stat = name.split("__", 1)
                    try:
                        roi_id = int(left.replace("ROI_", ""))
                    except ValueError:
                        roi_id = None
                if roi_id is None:
                    # Fallback: keep an artificial id (-1)
                    roi_id = -1
                parsed.append((roi_id, stat, float(w)))
        
            label_map = _load_labels_map(atlas_path=atlas_p, labels_path=atlas_labels_path)
        
            # Save ROI weights table
            roi_weights_csv = out_dir / "roi_weights.csv"
            lines = ["label_id,label_name,stat,coef"]
            for roi_id, stat, w in parsed:
                lines.append(f"{roi_id},{label_map.get(roi_id, f'ROI_{roi_id}')},{stat},{w}")
            roi_weights_csv.write_text("\n".join(lines) + "\n")
        
            # Build weight maps per stat
            atlas_img = nib.load(str(atlas_p))
            atlas_data = np.asanyarray(atlas_img.dataobj).astype(np.int32)
        
            stats = sorted({stat for _roi, stat, _w in parsed})
            weight_maps: List[Path] = []
            for stat in stats:
                weights_by_roi: Dict[int, float] = {roi: w for roi, s, w in parsed if s == stat}
                out_data = np.zeros_like(atlas_data, dtype=np.float32)
                for roi_id, w in weights_by_roi.items():
                    if roi_id <= 0:
                        continue
                    out_data[atlas_data == roi_id] = float(w)
                out_img = nib.Nifti1Image(
                    out_data, affine=atlas_img.affine, header=atlas_img.header
                )
                out_path = out_dir / f"weight_map_{stat}.nii.gz"
                nib.save(out_img, str(out_path))
                weight_maps.append(out_path)
        
            logger.info(f"Saved ROI weights: {roi_weights_csv}")
            for p in weight_maps:
                logger.info(f"Saved weight map: {p}")
        
            figures: List[Path] = []
        
            # --- Industry-standard visual 1: feature importance (top coefficients) ---
            feat_imp = figures_dir / "feature_importance_top.png"
            try:
                plot_top_coefficients(
                    parsed=parsed,
                    label_map=label_map,
                    out_path=feat_imp,
                    top_k=25,
                    title="Top linear coefficients (standardized features)",
                )
                figures.append(feat_imp)
                logger.info(f"Saved figure: {feat_imp}")
            except Exception as e:
                logger.warning(f"Could not generate feature importance figure: {e}")
        
            # --- Industry-standard visual 2: model diagnostics (classification or regression) ---
            diag = figures_dir / "model_diagnostics.png"
            pred_candidates = [
                model_path.parent / "cv_predictions.csv",
                model_path.parent / "predictions.csv",
            ]
            pred_path = next((p for p in pred_candidates if p.is_file()), None)
            if pred_path is not None:
                try:
                    plot_model_diagnostics_from_predictions_csv(
                        predictions_csv=pred_path,
                        out_path=diag,
                    )
                    figures.append(diag)
                    logger.info(f"Saved figure: {diag}")
                except Exception as e:
                    logger.warning(
                        f"Could not generate model diagnostics figure from {pred_path}: {e}"
                    )
            else:
                logger.warning(
                    "No predictions CSV found for diagnostics "
                    "(expected cv_predictions.csv or predictions.csv next to model)."
                )

            # --- Brain visualizations (PNG + HTML) for each weight map ---
            for weight_map in weight_maps:
                try:
                    viz_paths = create_weight_map_visualizations(
                        weight_map=weight_map,
                        out_dir=figures_dir,
                        title=f"Weight map: {weight_map.name}",
                    )
                    figures.extend(viz_paths)
                    for p in viz_paths:
                        logger.info(f"Saved brain visualization: {p}")
                except Exception as e:
                    logger.warning(
                        f"Could not generate brain visualization for {weight_map}: {e}"
                    )

            artifacts = ExplainArtifacts(
                output_dir=out_dir,
                roi_weights_csv=roi_weights_csv,
                weight_maps=weight_maps,
                figures=figures,
            )
            _maybe_add_intensity_response_fig5(
                artifacts=artifacts,
                feature_reduction_approach=str(feature_reduction_approach),
                model_path=model_path,
                out_dir=out_dir,
                logger=logger,
                csv_path_from_model=csv_path_from_model,
                target_col=target_col,
                task=task,
                atlas_path=atlas_path,
                atlas_from_model=atlas_from_model,
                voxel_ref_shape=voxel_ref_shape,
                voxel_ref_affine=voxel_ref_affine,
                feature_names=feature_names,
                est=est,
            )
        
            return artifacts
    except Exception:
        logger.exception("Responder ML explain failed.")
        raise


def _explain_voxel_features(
    est,
    feature_names: List[str],
    voxel_ref_shape: Optional[Sequence[int]],
    voxel_ref_affine: Optional[Sequence[Sequence[float]]],
    model_path: Path,
    out_dir: Path,
    logger,
) -> ExplainArtifacts:
    """
    Explain model with voxel-level features (from stats_ttest approach).
    """
    import matplotlib.pyplot as plt
    import nibabel as nib

    # Pull coefficients from pipeline
    core_est = est
    if hasattr(est, "named_steps"):
        if "clf" in est.named_steps:
            core_est = est.named_steps["clf"]
        elif "reg" in est.named_steps:
            core_est = est.named_steps["reg"]
    coef = getattr(core_est, "coef_", None)
    if coef is None:
        raise RuntimeError(
            "Model does not expose coef_ (expected linear model such as logistic regression or elastic-net regression)"
        )
    coef = np.asarray(coef)
    if coef.ndim == 2:
        coef = coef[0]
    if coef.shape[0] != len(feature_names):
        raise RuntimeError("coef_ length does not match feature_names")

    # Parse voxel coordinates from feature names: voxel_X_Y_Z
    voxel_data: List[Tuple[int, int, int, float]] = []
    for name, weight in zip(feature_names, coef.tolist()):
        if name.startswith("voxel_"):
            parts = name.split("_")
            if len(parts) == 4:  # voxel_X_Y_Z
                try:
                    x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
                    voxel_data.append((x, y, z, float(weight)))
                except ValueError:
                    logger.warning(f"Could not parse voxel coordinates from: {name}")
                    continue
        else:
            logger.warning(f"Unexpected voxel feature name format: {name}")

    if not voxel_data:
        raise RuntimeError("No valid voxel coordinates found in feature names")

    # Create voxel weight map in training reference space (if available).
    if voxel_ref_shape is None or voxel_ref_affine is None:
        raise RuntimeError(
            "Voxel reference shape/affine missing from model bundle. "
            "Re-train the model to include voxel reference metadata."
        )

    weights = np.array([w for x, y, z, w in voxel_data], dtype=float)
    shape = tuple(int(v) for v in voxel_ref_shape)
    if len(shape) != 3:
        raise RuntimeError(f"Invalid voxel_ref_shape: {shape}")
    weight_volume = np.zeros(shape, dtype=np.float32)

    dropped = 0
    for x, y, z, weight in voxel_data:
        if x < 0 or y < 0 or z < 0 or x >= shape[0] or y >= shape[1] or z >= shape[2]:
            dropped += 1
            continue
        weight_volume[int(x), int(y), int(z)] = float(weight)
    if dropped:
        logger.warning(
            f"Dropped {dropped} voxel weights outside reference shape {shape}"
        )

    affine = np.asarray(voxel_ref_affine, dtype=float)
    weight_img = nib.Nifti1Image(weight_volume, affine)

    # Save weight map
    weight_map_path = out_dir / "voxel_weight_map.nii.gz"
    nib.save(weight_img, str(weight_map_path))
    weight_maps = [weight_map_path]

    # Save voxel weights CSV
    voxel_weights_csv = out_dir / "voxel_weights.csv"
    lines = ["x,y,z,weight"]
    for x, y, z, weight in voxel_data:
        lines.append(f"{x},{y},{z},{weight}")
    voxel_weights_csv.write_text("\n".join(lines) + "\n")

    # Generate figures
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures = []

    # Skip glass brain plot for now - requires additional nilearn setup
    # Will add this in a future update

    # Feature importance plot (top positive/negative weights)
    try:
        feat_imp = figures_dir / "feature_importance_top.png"
        coords = [(x, y, z) for x, y, z, _w in voxel_data]
        # Sort by absolute weight
        sorted_indices = np.argsort(np.abs(weights))[::-1]
        top_n = min(20, len(weights))
        top_indices = sorted_indices[:top_n]

        import matplotlib.pyplot as plt  # type: ignore
        from tit.plotting import ensure_headless_matplotlib_backend, savefig_close

        ensure_headless_matplotlib_backend()
        fig, ax = plt.subplots(figsize=(10, 6))
        y_pos = np.arange(top_n)
        bars = ax.barh(y_pos, weights[top_indices])

        # Color bars based on sign
        for i, bar in enumerate(bars):
            if weights[top_indices[i]] > 0:
                bar.set_color("red")
            else:
                bar.set_color("blue")

        ax.set_yticks(y_pos)
        ax.set_yticklabels(
            [
                f"voxel_{coords[i][0]}_{coords[i][1]}_{coords[i][2]}"
                for i in top_indices
            ]
        )
        ax.set_xlabel("Weight")
        ax.set_title(f"Top {top_n} Voxel Weights")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        savefig_close(fig, str(feat_imp))
        figures.append(feat_imp)
        logger.info(f"Saved feature importance plot: {feat_imp}")
    except Exception as e:
        logger.warning(f"Could not generate feature importance plot: {e}")

    # Diagnostics from predictions CSV (if present)
    diag = figures_dir / "model_diagnostics.png"
    pred_candidates = [
        model_path.parent / "cv_predictions.csv",
        model_path.parent / "predictions.csv",
    ]
    pred_path = next((p for p in pred_candidates if p.is_file()), None)
    if pred_path is not None:
        try:
            plot_model_diagnostics_from_predictions_csv(
                predictions_csv=pred_path,
                out_path=diag,
            )
            figures.append(diag)
            logger.info(f"Saved figure: {diag}")
        except Exception as e:
            logger.warning(
                f"Could not generate model diagnostics figure from {pred_path}: {e}"
            )
    else:
        logger.warning(
            "No predictions CSV found for diagnostics "
            "(expected cv_predictions.csv or predictions.csv next to model)."
        )

    # Brain visualization (PNG + HTML)
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    try:
        viz_paths = create_weight_map_visualizations(
            weight_map=weight_map_path,
            out_dir=figures_dir,
            title="Voxel weight map",
        )
        figures.extend(viz_paths)
        for p in viz_paths:
            logger.info(f"Saved brain visualization: {p}")
    except Exception as e:
        logger.warning(f"Could not generate brain visualization: {e}")

    return ExplainArtifacts(
        output_dir=out_dir,
        roi_weights_csv=voxel_weights_csv,  # Use voxel weights CSV
        weight_maps=weight_maps,
        figures=figures,
    )


def _read_predictions_proba_map(predictions_csv: Path) -> Dict[Tuple[str, str], float]:
    """
    Read a responder predictions CSV and map (subject_id, simulation_name) -> proba.
    """
    import csv

    if not predictions_csv.is_file():
        return {}
    with predictions_csv.open("r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}
        if "proba" not in set(reader.fieldnames):
            return {}
        out: Dict[Tuple[str, str], float] = {}
        for r in reader:
            sid = (r.get("subject_id") or "").strip()
            sim = (r.get("simulation_name") or "").strip()
            pp = (r.get("proba") or "").strip()
            if not sid or pp == "":
                continue
            try:
                out[(sid, sim)] = float(pp)
            except ValueError:
                continue
    return out


def _roi_ids_from_coef(
    *, feature_names: Sequence[str], coef: np.ndarray, stat: str
) -> Dict[int, float]:
    """
    Return ROI -> coefficient for features matching `ROI_<id>__<stat>`.
    """
    coef = np.asarray(coef, dtype=float).ravel()
    if coef.shape[0] != len(feature_names):
        raise ValueError("coef length does not match feature_names")

    out: Dict[int, float] = {}
    for name, w in zip(feature_names, coef.tolist()):
        if not name.startswith("ROI_") or "__" not in name:
            continue
        left, st = name.split("__", 1)
        if st != stat:
            continue
        try:
            roi_id = int(left.replace("ROI_", ""))
        except ValueError:
            continue
        out[int(roi_id)] = float(w)
    return out


def _pick_top_roi_ids(
    *, roi_to_coef: Dict[int, float], top_k: int = 5, prefer_positive: bool = True
) -> List[int]:
    items = list(roi_to_coef.items())
    if prefer_positive:
        pos = [(roi, w) for roi, w in items if w > 0]
        if pos:
            items = pos
    items_sorted = sorted(items, key=lambda t: abs(t[1]), reverse=True)
    return [int(roi) for roi, _w in items_sorted[: int(max(1, top_k))]]


def _maybe_add_intensity_response_fig5(
    *,
    artifacts: ExplainArtifacts,
    feature_reduction_approach: str,
    model_path: Path,
    out_dir: Path,
    logger,
    csv_path_from_model: Optional[str],
    target_col: str,
    task: str,
    atlas_path: Optional[Path],
    atlas_from_model: Optional[str],
    voxel_ref_shape: Optional[Sequence[int]],
    voxel_ref_affine: Optional[Sequence[Sequence[float]]],
    feature_names: Sequence[str],
    est,
) -> None:
    """
    Best-effort: create an Albizu Fig.5-style intensity↔response figure and append it
    to `artifacts.figures`.

    Supports:
    - atlas_roi: picks top-K positive-weight ROIs (top10mean preferred)
    - stats_ttest / stats_fregression: uses the selected voxel coordinates

    Behavior/response on the scatter plot:
    - regression: y = target
    - classification: y = out-of-fold `proba` from cv_predictions.csv if available, else y = target (0/1)
    """
    try:
        if not csv_path_from_model:
            logger.warning("Fig5 skipped: model bundle missing csv_path")
            return
        csv_path = Path(str(csv_path_from_model))
        if not csv_path.is_file():
            logger.warning(f"Fig5 skipped: csv_path not found: {csv_path}")
            return
        # Use bundle config if available (preferred), but fall back to defaults.
        condition_col = None
        sham_value = "sham"
        efield_pat = None
        try:
            import joblib  # type: ignore

            bundle = joblib.load(model_path)
            cfg = dict(bundle.get("config") or {})
            condition_col = cfg.get("condition_col")
            sham_value = str(cfg.get("sham_value") or "sham")
            efield_pat = str(cfg.get("efield_filename_pattern") or "").strip() or None
        except Exception:
            pass

        subjects = load_subject_table(
            csv_path,
            target_col=target_col,
            condition_col=str(condition_col) if condition_col else None,
            sham_value=sham_value,
            task=("classification" if str(task) == "classification" else "regression"),
            require_target=True,
        )

        use_condition = bool(condition_col)
        active_subjects = [
            s
            for s in subjects
            if not (use_condition and is_sham_condition(s.condition, sham_value=sham_value))
        ]
        if len(active_subjects) < 4:
            logger.warning("Fig5 skipped: not enough active subjects with labels")
            return

        # Load E-field NIfTIs for active subjects.
        from .config import DEFAULT_EFIELD_FILENAME_PATTERN

        efield_pat = efield_pat or DEFAULT_EFIELD_FILENAME_PATTERN

        imgs, y_active, kept_active = load_efield_images(
            active_subjects,
            efield_filename_pattern=efield_pat,
            logger=logger,
        )

        # Build y for scatter (behavior proxy)
        proba_map = _read_predictions_proba_map(model_path.parent / "cv_predictions.csv")
        subj_behavior: List[float] = []
        subj_label: List[int] = []
        subj_median_intensity: List[float] = []
        subj_rows: List[str] = []
        voxel_r: List[np.ndarray] = []
        voxel_n: List[np.ndarray] = []

        # Determine feature mask / indices.
        import nibabel as nib  # type: ignore
        import nilearn.image as nii_img  # type: ignore

        if feature_reduction_approach == "atlas_roi":
            # Resolve atlas
            atlas_p: Optional[Path] = Path(atlas_from_model) if atlas_from_model else None
            if atlas_path is not None:
                atlas_p = Path(atlas_path)
            if atlas_p is None or not atlas_p.is_file():
                atlas_p = default_glasser_atlas_path()
            if atlas_p is None or not atlas_p.is_file():
                logger.warning("Fig5 skipped: atlas not found")
                return

            atlas_img = nib.load(str(atlas_p))
            atlas_data = np.asanyarray(atlas_img.dataobj).astype(np.int32)

            # Pull coef and pick stats
            core_est = est
            if hasattr(est, "named_steps"):
                if "clf" in est.named_steps:
                    core_est = est.named_steps["clf"]
                elif "reg" in est.named_steps:
                    core_est = est.named_steps["reg"]
            coef = getattr(core_est, "coef_", None)
            if coef is None:
                logger.warning("Fig5 skipped: model has no coef_")
                return
            coef = np.asarray(coef)
            if coef.ndim == 2:
                coef = coef[0]

            stats = sorted(
                {n.split("__", 1)[1] for n in feature_names if n.startswith("ROI_") and "__" in n}
            )
            stat_pref = "top10mean" if "top10mean" in stats else ("mean" if "mean" in stats else (stats[0] if stats else "top10mean"))
            roi_to_coef = _roi_ids_from_coef(feature_names=feature_names, coef=coef, stat=stat_pref)
            if not roi_to_coef:
                logger.warning(f"Fig5 skipped: no ROI coefficients found for stat={stat_pref!r}")
                return
            roi_ids = _pick_top_roi_ids(roi_to_coef=roi_to_coef, top_k=5, prefer_positive=True)
            mask = np.isin(atlas_data, np.asarray(roi_ids, dtype=np.int32))
            flat_idx = np.flatnonzero(mask.ravel())
            if flat_idx.size == 0:
                logger.warning(f"Fig5 skipped: selected ROI IDs had no voxels: {roi_ids}")
                return

            # Iterate subjects and extract voxel values
            # Precompute median split threshold for regression grouping if needed.
            y_vals = [float(v) for v in y_active if v is not None]
            y_med = float(np.median(np.asarray(y_vals, dtype=float))) if y_vals else 0.0

            for img, s, yy in zip(imgs, kept_active, y_active):
                if yy is None:
                    continue
                aligned = nii_img.resample_to_img(img, atlas_img, interpolation="continuous")
                data = np.asanyarray(aligned.dataobj)
                data3 = _ensure_3d_data(data).astype(np.float32, copy=False).ravel()
                vals = data3[flat_idx]
                vals = vals[np.isfinite(vals)]
                if vals.size == 0:
                    continue
                med = float(np.median(vals))

                # y for scatter
                if str(task) == "classification":
                    y_scatter = float(proba_map.get((s.subject_id, s.simulation_name), float(yy)))
                    lab = int(float(yy))
                else:
                    y_scatter = float(yy)
                    lab = 1 if float(yy) >= y_med else 0

                (voxel_r if lab == 1 else voxel_n).append(vals)
                subj_behavior.append(y_scatter)
                subj_label.append(lab)
                subj_median_intensity.append(med)
                subj_rows.append(f"{s.subject_id},{s.simulation_name},{lab},{y_scatter},{med}")

            fig_title = f"Intensity vs response (atlas_roi; ROIs={roi_ids}, stat={stat_pref})"
            fig_name = f"fig5_intensity_response__atlas_roi__stat-{stat_pref}__top{len(roi_ids)}.png"

        else:
            # stats_*: use selected voxel coordinates from feature names
            coords = parse_voxel_feature_names(feature_names)
            if not coords:
                logger.warning("Fig5 skipped: no voxel coords parsed from feature names")
                return
            if voxel_ref_shape is None or voxel_ref_affine is None:
                logger.warning("Fig5 skipped: voxel_ref_shape/affine missing from bundle")
                return
            shape = tuple(int(v) for v in voxel_ref_shape)
            if len(shape) != 3:
                logger.warning(f"Fig5 skipped: invalid voxel_ref_shape: {shape}")
                return

            # Build a reference image for resampling.
            ref_img = nib.Nifti1Image(np.zeros(shape, dtype=np.float32), np.asarray(voxel_ref_affine, dtype=float))

            # Convert coords to flat indices (drop out-of-bounds).
            kept_coords: List[Tuple[int, int, int]] = []
            flat_indices: List[int] = []
            dropped = 0
            for x, y, z in coords:
                if x < 0 or y < 0 or z < 0 or x >= shape[0] or y >= shape[1] or z >= shape[2]:
                    dropped += 1
                    continue
                kept_coords.append((x, y, z))
                flat_indices.append(int(np.ravel_multi_index((x, y, z), shape)))
            if dropped:
                logger.info(f"Fig5: dropped {dropped} voxel coords outside ref shape {shape}")
            if not flat_indices:
                logger.warning("Fig5 skipped: all voxel coords were out of bounds")
                return
            flat_idx_arr = np.asarray(flat_indices, dtype=int)

            # Precompute median split threshold for regression grouping if needed.
            y_vals = [float(v) for v in y_active if v is not None]
            y_med = float(np.median(np.asarray(y_vals, dtype=float))) if y_vals else 0.0

            for img, s, yy in zip(imgs, kept_active, y_active):
                if yy is None:
                    continue
                aligned = nii_img.resample_to_img(img, ref_img, interpolation="continuous")
                data = np.asanyarray(aligned.dataobj)
                data3 = _ensure_3d_data(data).astype(np.float32, copy=False).ravel()
                vals = data3[flat_idx_arr]
                vals = vals[np.isfinite(vals)]
                if vals.size == 0:
                    continue
                med = float(np.median(vals))

                if str(task) == "classification":
                    y_scatter = float(proba_map.get((s.subject_id, s.simulation_name), float(yy)))
                    lab = int(float(yy))
                else:
                    y_scatter = float(yy)
                    lab = 1 if float(yy) >= y_med else 0

                (voxel_r if lab == 1 else voxel_n).append(vals)
                subj_behavior.append(y_scatter)
                subj_label.append(lab)
                subj_median_intensity.append(med)
                subj_rows.append(f"{s.subject_id},{s.simulation_name},{lab},{y_scatter},{med}")

            fig_title = f"Intensity vs response ({feature_reduction_approach}; n_voxels={len(flat_idx_arr)})"
            fig_name = f"fig5_intensity_response__{feature_reduction_approach}__nvox-{len(flat_idx_arr)}.png"

        if len(subj_label) < 4 or (np.sum(np.asarray(subj_label) == 1) < 2) or (np.sum(np.asarray(subj_label) == 0) < 2):
            logger.warning("Fig5 skipped: need at least 2 subjects per group after filtering")
            return

        figures_dir = out_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        fig_path = figures_dir / fig_name
        summary_csv = out_dir / "intensity_response_summary.csv"
        summary_csv.write_text(
            "subject_id,simulation_name,group_label,scatter_y,median_intensity\n"
            + "\n".join(subj_rows)
            + "\n"
        )

        plot_intensity_response_fig5(
            voxel_values_responder=np.concatenate(voxel_r, axis=0) if voxel_r else np.array([], dtype=float),
            voxel_values_non_responder=np.concatenate(voxel_n, axis=0) if voxel_n else np.array([], dtype=float),
            subj_median_intensity=np.asarray(subj_median_intensity, dtype=float),
            subj_behavior=np.asarray(subj_behavior, dtype=float),
            subj_label=np.asarray(subj_label, dtype=int),
            out_path=fig_path,
            title=fig_title,
        )
        artifacts.figures.append(fig_path)
        logger.info(f"Saved Fig5-style intensity/response figure: {fig_path}")
        logger.info(f"Saved intensity/response summary CSV: {summary_csv}")
    except Exception as e:
        logger.warning(f"Fig5 generation skipped/failed (non-fatal): {e}")
