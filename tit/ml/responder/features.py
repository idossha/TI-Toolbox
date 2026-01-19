from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import logging

from .config import default_glasser_atlas_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureMatrix:
    X: np.ndarray  # shape: (n_subjects, n_features)
    feature_names: List[str]
    atlas_path: Optional[Path]


def _ensure_3d_data(data: np.ndarray) -> np.ndarray:
    if data.ndim == 4:
        if data.shape[-1] == 1:
            return data[..., 0]
        return data[..., -1]
    if data.ndim > 4:
        raise ValueError(f"Cannot handle {data.ndim}D images, expected 3D or 4D")
    return data


def _prepare_efield_arrays(
    efield_imgs: Sequence[Any], *, ref_img: Optional[Any] = None
) -> Tuple[np.ndarray, Any, Tuple[int, int, int]]:
    import nibabel as nib  # type: ignore
    import nilearn.image as nii_img  # type: ignore

    if not efield_imgs:
        raise ValueError("No E-field images provided")

    ref = ref_img or efield_imgs[0]
    aligned_imgs: List[nib.Nifti1Image] = []
    for img in efield_imgs:
        aligned_imgs.append(
            nii_img.resample_to_img(img, ref, interpolation="continuous")
        )

    img_arrays = []
    for img in aligned_imgs:
        data = np.asanyarray(img.dataobj)
        data_3d = _ensure_3d_data(data)
        img_arrays.append(np.asarray(data_3d, dtype=np.float32).ravel())

    img_data = np.asarray(img_arrays, dtype=np.float32)
    ref_data = np.asanyarray(ref.dataobj)
    ref_data_3d = _ensure_3d_data(ref_data)
    img_shape_3d = ref_data_3d.shape
    return img_data, ref, img_shape_3d


def parse_voxel_feature_names(feature_names: Iterable[str]) -> List[Tuple[int, int, int]]:
    coords: List[Tuple[int, int, int]] = []
    for name in feature_names:
        if not name.startswith("voxel_"):
            continue
        parts = name.split("_")
        if len(parts) != 4:
            continue
        try:
            x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError:
            continue
        coords.append((x, y, z))
    return coords


def extract_voxel_features_by_coords(
    efield_imgs: Sequence[Any],
    voxel_coords: Sequence[Tuple[int, int, int]],
    *,
    ref_img: Optional[Any] = None,
) -> FeatureMatrix:
    if not voxel_coords:
        raise ValueError("No voxel coordinates provided")

    img_data, ref, img_shape_3d = _prepare_efield_arrays(
        efield_imgs, ref_img=ref_img
    )
    flat_indices = [
        np.ravel_multi_index(coord, img_shape_3d) for coord in voxel_coords
    ]
    X = img_data[:, flat_indices]
    feature_names = [f"voxel_{x}_{y}_{z}" for x, y, z in voxel_coords]
    return FeatureMatrix(X=X, feature_names=feature_names, atlas_path=None)


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


def extract_stats_ttest_features(
    efield_imgs: Sequence[Any],
    y: Sequence[float],
    *,
    p_threshold: float = 0.001,
) -> FeatureMatrix:
    """
    Extract features using statistical voxel selection via mass univariate t-test.

    Runs a t-test comparing responders vs non-responders and selects voxels
    with p-value < threshold. Uses TImax values of significant voxels as features.

    The E-field maps are assumed to already be in MNI space and GM-masked.
    """
    # Import heavy deps lazily so the module can be imported in environments where
    # only SimNIBS' `simnibs_python` has these packages available.
    from scipy import stats  # type: ignore

    if len(efield_imgs) != len(y):
        raise ValueError(f"Mismatch: {len(efield_imgs)} images but {len(y)} targets")

    if len(efield_imgs) < 4:
        raise ValueError(f"Need at least 4 subjects for statistical testing, got {len(efield_imgs)}")

    # Convert targets to binary for t-test (0=non-responder, 1=responder)
    y_binary = np.asarray(y, dtype=int)
    if not all(v in (0, 1) for v in y_binary):
        raise ValueError("Statistical feature selection requires binary targets (0/1)")

    img_data, ref_img, img_shape_3d = _prepare_efield_arrays(efield_imgs)
    n_subjects, n_voxels = img_data.shape

    # Split data by group (responders vs non-responders)
    responder_mask = y_binary == 1
    non_responder_mask = y_binary == 0

    responder_data = img_data[responder_mask, :]
    non_responder_data = img_data[non_responder_mask, :]

    if responder_data.shape[0] < 2 or non_responder_data.shape[0] < 2:
        raise ValueError(
            f"Need at least 2 subjects per group. Responders: {responder_data.shape[0]}, "
            f"Non-responders: {non_responder_data.shape[0]}"
        )

    # Run mass univariate t-test
    t_stats, p_values = stats.ttest_ind(
        responder_data, non_responder_data, axis=0, equal_var=False
    )

    # Select significant voxels (handle NaN p-values from zero variance)
    significant_mask = (p_values < p_threshold) & (~np.isnan(p_values))

    if not np.any(significant_mask):
        raise ValueError(f"No voxels passed p < {p_threshold} threshold")

    # Get coordinates for significant voxels
    flat_indices = np.flatnonzero(significant_mask)
    voxel_coords = np.unravel_index(flat_indices, img_shape_3d)

    voxel_coords_list = list(zip(*voxel_coords))
    feature_names = [f"voxel_{x}_{y}_{z}" for x, y, z in voxel_coords_list]
    X = img_data[:, significant_mask]

    return FeatureMatrix(
        X=X,
        feature_names=feature_names,
        atlas_path=None  # No atlas used for statistical approach
    )


def extract_stats_fregression_features(
    efield_imgs: Sequence[Any],
    y: Sequence[float],
    *,
    p_threshold: float = 0.001,
) -> FeatureMatrix:
    """
    Extract features using univariate F-test for regression.

    Selects voxels whose univariate F-test p-values are below threshold.
    """
    from sklearn.feature_selection import f_regression  # type: ignore

    if len(efield_imgs) != len(y):
        raise ValueError(f"Mismatch: {len(efield_imgs)} images but {len(y)} targets")
    if len(efield_imgs) < 4:
        raise ValueError(
            f"Need at least 4 subjects for statistical testing, got {len(efield_imgs)}"
        )

    y_arr = np.asarray(y, dtype=float)
    if not np.isfinite(y_arr).all():
        raise ValueError("Targets contain NaN/inf values")
    if np.allclose(y_arr, y_arr[0]):
        raise ValueError("Targets are constant; regression feature selection is undefined")

    img_data, _ref_img, img_shape_3d = _prepare_efield_arrays(efield_imgs)

    # Univariate F-test for each voxel
    _f_stat, p_values = f_regression(img_data, y_arr)
    significant_mask = (p_values < p_threshold) & (~np.isnan(p_values))
    if not np.any(significant_mask):
        raise ValueError(f"No voxels passed p < {p_threshold} threshold")

    flat_indices = np.flatnonzero(significant_mask)
    voxel_coords = np.unravel_index(flat_indices, img_shape_3d)
    voxel_coords_list = list(zip(*voxel_coords))
    feature_names = [f"voxel_{x}_{y}_{z}" for x, y, z in voxel_coords_list]
    X = img_data[:, significant_mask]

    return FeatureMatrix(X=X, feature_names=feature_names, atlas_path=None)


def select_ttest_voxel_coords(
    efield_imgs: Sequence[Any],
    y: Sequence[float],
    *,
    p_threshold: float = 0.001,
    ref_img: Optional[Any] = None,
) -> Tuple[List[Tuple[int, int, int]], Any, Tuple[int, int, int]]:
    """
    Run mass univariate t-test and return selected voxel coordinates + reference image.
    """
    if len(efield_imgs) != len(y):
        raise ValueError(f"Mismatch: {len(efield_imgs)} images but {len(y)} targets")
    if len(efield_imgs) < 4:
        raise ValueError(f"Need at least 4 subjects for statistical testing, got {len(efield_imgs)}")

    y_binary = np.asarray(y, dtype=int)
    if not all(v in (0, 1) for v in y_binary):
        raise ValueError("Statistical feature selection requires binary targets (0/1)")

    img_data, ref, img_shape_3d = _prepare_efield_arrays(efield_imgs, ref_img=ref_img)

    responder_mask = y_binary == 1
    non_responder_mask = y_binary == 0
    responder_data = img_data[responder_mask, :]
    non_responder_data = img_data[non_responder_mask, :]

    if responder_data.shape[0] < 2 or non_responder_data.shape[0] < 2:
        raise ValueError(
            f"Need at least 2 subjects per group. Responders: {responder_data.shape[0]}, "
            f"Non-responders: {non_responder_data.shape[0]}"
        )

    from scipy import stats  # type: ignore

    _t, p_values = stats.ttest_ind(
        responder_data, non_responder_data, axis=0, equal_var=False
    )
    significant_mask = (p_values < p_threshold) & (~np.isnan(p_values))
    if not np.any(significant_mask):
        raise ValueError(f"No voxels passed p < {p_threshold} threshold")

    flat_indices = np.flatnonzero(significant_mask)
    voxel_coords = list(zip(*np.unravel_index(flat_indices, img_shape_3d)))
    return voxel_coords, ref, img_shape_3d


def select_fregression_voxel_coords(
    efield_imgs: Sequence[Any],
    y: Sequence[float],
    *,
    p_threshold: float = 0.001,
    ref_img: Optional[Any] = None,
) -> Tuple[List[Tuple[int, int, int]], Any, Tuple[int, int, int]]:
    """
    Run univariate F-tests and return selected voxel coordinates + reference image.
    """
    from sklearn.feature_selection import f_regression  # type: ignore

    if len(efield_imgs) != len(y):
        raise ValueError(f"Mismatch: {len(efield_imgs)} images but {len(y)} targets")
    if len(efield_imgs) < 4:
        raise ValueError(
            f"Need at least 4 subjects for statistical testing, got {len(efield_imgs)}"
        )

    y_arr = np.asarray(y, dtype=float)
    if not np.isfinite(y_arr).all():
        raise ValueError("Targets contain NaN/inf values")
    if np.allclose(y_arr, y_arr[0]):
        raise ValueError("Targets are constant; regression feature selection is undefined")

    img_data, ref, img_shape_3d = _prepare_efield_arrays(efield_imgs, ref_img=ref_img)

    _f_stat, p_values = f_regression(img_data, y_arr)
    significant_mask = (p_values < p_threshold) & (~np.isnan(p_values))
    if not np.any(significant_mask):
        raise ValueError(f"No voxels passed p < {p_threshold} threshold")

    flat_indices = np.flatnonzero(significant_mask)
    voxel_coords = list(zip(*np.unravel_index(flat_indices, img_shape_3d)))
    return voxel_coords, ref, img_shape_3d


def extract_features(
    efield_imgs: Sequence[Any],
    y: Optional[Sequence[float]] = None,
    *,
    feature_reduction_approach: str = "atlas_roi",
    atlas_path: Optional[Path] = None,
    include_mean: bool = True,
    include_max: bool = False,
    include_top10_mean: bool = True,
    top_percentile: float = 90.0,
    ttest_p_threshold: float = 0.001,
) -> FeatureMatrix:
    """
    Extract features using the specified approach.

    For atlas_roi approach: uses atlas-based ROI averaging.
    For stats_ttest approach: uses mass univariate t-test for voxel selection.
    For stats_fregression approach: uses univariate F-test for regression targets.
    """
    if feature_reduction_approach == "atlas_roi":
        return extract_roi_features_from_efield(
            efield_imgs,
            atlas_path=atlas_path,
            include_mean=include_mean,
            include_max=include_max,
            include_top10_mean=include_top10_mean,
            top_percentile=top_percentile,
        )
    elif feature_reduction_approach == "stats_ttest":
        if y is None:
            raise ValueError("y (targets) required for stats_ttest approach")
        return extract_stats_ttest_features(
            efield_imgs,
            y,
            p_threshold=ttest_p_threshold,
        )
    elif feature_reduction_approach == "stats_fregression":
        if y is None:
            raise ValueError("y (targets) required for stats_fregression approach")
        return extract_stats_fregression_features(
            efield_imgs,
            y,
            p_threshold=ttest_p_threshold,
        )
    else:
        raise ValueError(
            f"Unknown feature_reduction_approach: {feature_reduction_approach}. "
            "Must be 'atlas_roi', 'stats_ttest', or 'stats_fregression'"
        )
