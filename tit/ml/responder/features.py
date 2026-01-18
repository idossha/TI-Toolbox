from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import default_glasser_atlas_path


@dataclass(frozen=True)
class FeatureMatrix:
    X: np.ndarray  # shape: (n_subjects, n_features)
    feature_names: List[str]
    atlas_path: Path


def _load_atlas(atlas_path: Optional[Path]) -> Path:
    if atlas_path is not None:
        p = Path(atlas_path)
        if not p.is_file():
            raise FileNotFoundError(f"Atlas not found: {p}")
        return p
    p = default_glasser_atlas_path()
    if p is None:
        raise FileNotFoundError(
            "Default Glasser atlas not found. Expected resources/atlas/MNI_Glasser_HCP_v1.0.nii.gz. "
            "Provide --atlas-path explicitly."
        )
    return p


def extract_roi_features_from_efield(
    efield_imgs: Sequence[Any],
    *,
    atlas_path: Optional[Path] = None,
    include_mean: bool = True,
    include_max: bool = False,
    include_top10_mean: bool = True,
    top_percentile: float = 90.0,
) -> FeatureMatrix:
    """
    Extract atlas ROI features from E-field NIfTIs.

    The E-field maps are assumed to already be in MNI space and GM-masked.
    """
    # Import heavy deps lazily so the module can be imported in environments where
    # only SimNIBS' `simnibs_python` has these packages available.
    import nibabel as nib  # type: ignore
    import nilearn.image as nii_img  # type: ignore
    import nilearn.maskers as nii_maskers  # type: ignore

    atlas_p = _load_atlas(atlas_path)
    atlas_img = nib.load(str(atlas_p))

    # Ensure all subjects are aligned to atlas grid (best-effort).
    # If they're already in the exact atlas space, this is a no-op.
    aligned_imgs: List[nib.Nifti1Image] = []
    for img in efield_imgs:
        aligned_imgs.append(
            nii_img.resample_to_img(img, atlas_img, interpolation="continuous")
        )

    if not any([include_mean, include_max, include_top10_mean]):
        raise ValueError("At least one feature type must be enabled")

    # Determine label set from atlas (exclude background 0).
    atlas_data = np.asanyarray(atlas_img.dataobj).astype(np.int32)
    labels = np.unique(atlas_data)
    labels = labels[labels != 0]
    labels_sorted = sorted(int(x) for x in labels.tolist())

    feats: List[np.ndarray] = []
    names: List[str] = []

    if include_mean:
        masker_mean = nii_maskers.NiftiLabelsMasker(
            labels_img=atlas_img, strategy="mean", standardize=False
        )
        X_mean = masker_mean.fit_transform(aligned_imgs)
        feats.append(np.asarray(X_mean, dtype=float))
        names.extend([f"ROI_{l}__mean" for l in labels_sorted])

    if include_max:
        # Nilearn uses "maximum" (not "max") for the max-reduction strategy.
        masker_max = nii_maskers.NiftiLabelsMasker(
            labels_img=atlas_img, strategy="maximum", standardize=False
        )
        X_max = masker_max.fit_transform(aligned_imgs)
        feats.append(np.asarray(X_max, dtype=float))
        names.extend([f"ROI_{l}__max" for l in labels_sorted])

    if include_top10_mean:
        # Precompute ROI voxel indices once.
        roi_indices: Dict[int, np.ndarray] = {}
        flat_labels = atlas_data.ravel()
        for l in labels_sorted:
            roi_indices[l] = np.flatnonzero(flat_labels == l)

        X_top = np.zeros((len(aligned_imgs), len(labels_sorted)), dtype=float)
        for i, img in enumerate(aligned_imgs):
            data = np.asanyarray(img.dataobj).astype(np.float32).ravel()
            for j, l in enumerate(labels_sorted):
                idx = roi_indices[l]
                if idx.size == 0:
                    X_top[i, j] = 0.0
                    continue
                vals = data[idx]
                # Avoid NaNs from empty / all-zero ROIs.
                if vals.size == 0:
                    X_top[i, j] = 0.0
                    continue
                thr = np.percentile(vals, top_percentile)
                sel = vals[vals >= thr]
                X_top[i, j] = float(sel.mean()) if sel.size else float(vals.mean())
        feats.append(X_top)
        names.extend([f"ROI_{l}__top10mean" for l in labels_sorted])

    X = np.concatenate(feats, axis=1) if len(feats) > 1 else feats[0]
    return FeatureMatrix(X=X, feature_names=names, atlas_path=atlas_p)
