from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from tit import logger as logging_util

from .config import default_glasser_atlas_path, default_glasser_labels_path
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
        config_from_model = bundle.get("config", {})
        feature_reduction_approach = config_from_model.get("feature_reduction_approach", "atlas_roi")

        if not feature_names:
            raise RuntimeError("Model bundle missing feature_names")

        # Handle different feature types based on approach
        if feature_reduction_approach == "stats_ttest":
            # For stats_ttest, features are voxel coordinates like "voxel_X_Y_Z"
            return _explain_voxel_features(
                est=est,
                feature_names=feature_names,
                out_dir=out_dir,
                logger=logger,
            )
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
                _plot_top_coefficients(
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
        
            # --- Industry-standard visual 2: model diagnostics (ROC/PR/Calib/Confusion or regression diagnostics) ---
            pred_path = model_path.parent / "cv_predictions.csv"
            diag = figures_dir / "model_diagnostics.png"
            if pred_path.is_file():
                try:
                    _plot_model_diagnostics_from_predictions_csv(
                        predictions_csv=pred_path,
                        out_path=diag,
                    )
                    figures.append(diag)
                    logger.info(f"Saved figure: {diag}")
                except Exception as e:
                    logger.warning(
                        f"Could not generate model diagnostics figure from {pred_path}: {e}"
                    )
        
            return ExplainArtifacts(
                output_dir=out_dir,
                roi_weights_csv=roi_weights_csv,
                weight_maps=weight_maps,
                figures=figures,
            )
    except Exception:
        logger.exception("Responder ML explain failed.")
        raise


def _explain_voxel_features(
    est,
    feature_names: List[str],
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

    # Create voxel weight map
    # Find the bounding box of significant voxels
    coords = np.array([(x, y, z) for x, y, z, w in voxel_data])
    weights = np.array([w for x, y, z, w in voxel_data])

    if len(coords) == 0:
        raise RuntimeError("No voxel coordinates to create weight map")

    # Create 3D weight volume
    min_coords = coords.min(axis=0)
    max_coords = coords.max(axis=0)
    shape = max_coords - min_coords + 1

    # Create weight volume
    weight_volume = np.zeros(shape, dtype=np.float32)
    for (x, y, z), weight in zip(coords, weights):
        local_x, local_y, local_z = x - min_coords[0], y - min_coords[1], z - min_coords[2]
        weight_volume[local_x, local_y, local_z] = weight

    # Create NIfTI image (using a dummy affine - this is for visualization only)
    affine = np.eye(4)
    affine[0, 0] = affine[1, 1] = affine[2, 2] = 2.0  # 2mm voxels (typical MNI)
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
        _mpl_pyplot()

        # Sort by absolute weight
        sorted_indices = np.argsort(np.abs(weights))[::-1]
        top_n = min(20, len(weights))
        top_indices = sorted_indices[:top_n]

        fig, ax = plt.subplots(figsize=(10, 6))
        y_pos = np.arange(top_n)
        bars = ax.barh(y_pos, weights[top_indices])

        # Color bars based on sign
        for i, bar in enumerate(bars):
            if weights[top_indices[i]] > 0:
                bar.set_color('red')
            else:
                bar.set_color('blue')

        ax.set_yticks(y_pos)
        ax.set_yticklabels([f"voxel_{coords[i][0]}_{coords[i][1]}_{coords[i][2]}" for i in top_indices])
        ax.set_xlabel('Weight')
        ax.set_title(f'Top {top_n} Voxel Weights')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(str(feat_imp), dpi=150, bbox_inches='tight')
        plt.close(fig)
        figures.append(feat_imp)
        logger.info(f"Saved feature importance plot: {feat_imp}")
    except Exception as e:
        logger.warning(f"Could not generate feature importance plot: {e}")

    return ExplainArtifacts(
        output_dir=out_dir,
        roi_weights_csv=voxel_weights_csv,  # Use voxel weights CSV
        weight_maps=weight_maps,
        figures=figures,
    )


def _mpl_pyplot():
    # Keep matplotlib optional at import-time for non-ML installs.
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt  # type: ignore

    return plt


def _plot_top_coefficients(
    *,
    parsed: Sequence[Tuple[int, str, float]],
    label_map: Dict[int, str],
    out_path: Path,
    top_k: int = 20,
    title: str = "Top coefficients",
) -> None:
    """
    Plot top +/- coefficients as a horizontal bar chart.
    This is a standard visual for linear models (log-reg / elastic-net).
    """
    plt = _mpl_pyplot()

    # Build labeled entries
    entries: List[Tuple[str, float]] = []
    for roi_id, stat, w in parsed:
        roi_name = label_map.get(roi_id, f"ROI_{roi_id}")
        entries.append((f"{roi_name}__{stat}", float(w)))
    if not entries:
        raise RuntimeError("No coefficients to plot")

    # Select most positive and most negative
    entries_sorted = sorted(entries, key=lambda t: t[1])
    neg = entries_sorted[: max(1, top_k // 2)]
    pos = entries_sorted[-max(1, top_k // 2) :]
    selected = neg + pos

    labels = [n for n, _w in selected]
    weights = np.asarray([w for _n, w in selected], dtype=float)
    colors = ["#d62728" if w > 0 else "#1f77b4" for w in weights]

    fig_h = max(4.0, 0.22 * len(labels) + 1.5)
    fig, ax = plt.subplots(figsize=(12, fig_h), dpi=150)
    y = np.arange(len(labels))
    ax.barh(y, weights, color=colors, alpha=0.9)
    ax.axvline(0.0, color="black", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Coefficient (from standardized features)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def _read_csv_as_rows(csv_path: Path) -> List[Dict[str, str]]:
    import csv

    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _as_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    ss = str(s).strip()
    if ss == "":
        return None
    try:
        return float(ss)
    except ValueError:
        return None


def _as_int(s: Optional[str]) -> Optional[int]:
    v = _as_float(s)
    if v is None:
        return None
    return int(v)


def _plot_model_diagnostics_from_predictions_csv(
    *, predictions_csv: Path, out_path: Path
) -> None:
    """
    Create a single multi-panel "industry standard" diagnostics figure:
    - ROC + PR + calibration + confusion matrix
    """
    rows = _read_csv_as_rows(predictions_csv)
    if not rows:
        raise RuntimeError(f"Empty predictions CSV: {predictions_csv}")

    cols = set(rows[0].keys())
    if "proba" not in cols:
        raise RuntimeError(
            f"Unrecognized predictions CSV format (expected 'proba' column): {sorted(cols)}"
        )

    plt = _mpl_pyplot()

    from sklearn.calibration import calibration_curve
    from sklearn.metrics import (
        ConfusionMatrixDisplay,
        average_precision_score,
        confusion_matrix,
        precision_recall_curve,
        roc_auc_score,
        roc_curve,
    )

    # Target column is usually "response" in current training output.
    target_col = (
        "response"
        if "response" in cols
        else next(
            (
                c
                for c in cols
                if c not in {"subject_id", "simulation_name", "proba"}
            ),
            None,
        )
    )
    if not target_col:
        raise RuntimeError("Could not infer target column in predictions CSV")

    y: List[int] = []
    p: List[float] = []
    for r in rows:
        yy = _as_int(r.get(target_col))
        pp = _as_float(r.get("proba"))
        if yy is None or pp is None:
            continue
        y.append(int(yy))
        p.append(float(pp))
    if len(y) < 2:
        raise RuntimeError("Not enough labeled prediction rows to plot diagnostics")

    y_arr = np.asarray(y, dtype=int)
    p_arr = np.asarray(p, dtype=float)

    fpr, tpr, _ = roc_curve(y_arr, p_arr)
    roc_auc = roc_auc_score(y_arr, p_arr)
    prec, rec, _ = precision_recall_curve(y_arr, p_arr)
    ap = average_precision_score(y_arr, p_arr)
    frac_pos, mean_pred = calibration_curve(
        y_arr, p_arr, n_bins=10, strategy="quantile"
    )

    # Confusion matrix at threshold 0.5 (standard) and also best-F1; display best-F1.
    thresholds = np.unique(np.clip(p_arr, 0.0, 1.0))
    best_thr = 0.5
    best_f1 = -1.0
    for thr in thresholds:
        y_hat = (p_arr >= thr).astype(int)
        tp = int(((y_hat == 1) & (y_arr == 1)).sum())
        fp = int(((y_hat == 1) & (y_arr == 0)).sum())
        fn = int(((y_hat == 0) & (y_arr == 1)).sum())
        denom = 2 * tp + fp + fn
        f1 = (2 * tp / denom) if denom > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_thr = float(thr)

    cm = confusion_matrix(y_arr, (p_arr >= best_thr).astype(int), labels=[0, 1])

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=150)
    ax_roc, ax_pr, ax_cal, ax_cm = axes.ravel()

    ax_roc.plot(fpr, tpr, color="#1f77b4", linewidth=2)
    ax_roc.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1)
    ax_roc.set_xlabel("False Positive Rate")
    ax_roc.set_ylabel("True Positive Rate")
    ax_roc.set_title(f"ROC (AUC={roc_auc:.3f})")
    ax_roc.grid(True, alpha=0.2)

    ax_pr.plot(rec, prec, color="#ff7f0e", linewidth=2)
    ax_pr.set_xlabel("Recall")
    ax_pr.set_ylabel("Precision")
    ax_pr.set_title(f"Precision-Recall (AP={ap:.3f})")
    ax_pr.grid(True, alpha=0.2)

    ax_cal.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1)
    ax_cal.plot(mean_pred, frac_pos, marker="o", linewidth=2, color="#2ca02c")
    ax_cal.set_xlabel("Mean predicted probability")
    ax_cal.set_ylabel("Fraction of positives")
    ax_cal.set_title("Calibration (reliability diagram)")
    ax_cal.grid(True, alpha=0.2)

    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=[0, 1])
    disp.plot(ax=ax_cm, cmap="Blues", colorbar=False, values_format="d")
    ax_cm.set_title(f"Confusion (thr={best_thr:.3f}, best F1={best_f1:.3f})")

    fig.suptitle("Model diagnostics (CV predictions)", y=0.99)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
