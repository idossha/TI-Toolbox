"""
DTI quality control image generation helpers.

Computes DTI QC metrics (FA, eigenvalues, positive-definiteness) and
generates color-coded FA direction maps overlaid on T1 for visual QC.
"""

from typing import Any


# Maximum pixel size for the longest physical dimension of a display slice.
# Slices are resampled from voxel-space to this display grid using the NIfTI
# voxel sizes, so the same anatomy always produces the same pixel output
# regardless of acquisition resolution (following the nilearn / nireports
# pattern of affine-aware resampling before display).
_DISPLAY_MAX_PX = 256


def compute_dti_qc_metrics(tensor_file: str) -> dict[str, Any]:
    """Compute DTI quality control metrics from a 6-component tensor NIfTI.

    Parameters
    ----------
    tensor_file : str
        Path to a 4D NIfTI with shape (X, Y, Z, 6) containing
        [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz].

    Returns
    -------
    dict
        Dictionary with voxel counts, eigenvalue statistics, FA statistics,
        and positive-definiteness percentage.
    """
    import nibabel as nib
    import numpy as np

    img = nib.load(tensor_file)
    data = img.get_fdata(dtype=np.float32)

    # Handle 4D with last dim == 6
    if data.ndim == 4 and data.shape[-1] == 6:
        pass
    else:
        raise ValueError(f"Expected shape (X,Y,Z,6), got {data.shape}")

    total_voxels = int(np.prod(data.shape[:3]))

    # Mask: voxels where at least one tensor component is non-zero
    nonzero_mask = np.any(data != 0, axis=-1)
    nonzero_voxels = int(np.count_nonzero(nonzero_mask))

    if nonzero_voxels == 0:
        return {
            "total_voxels": total_voxels,
            "nonzero_voxels": 0,
            "pct_nonzero": 0.0,
            "positive_definite_voxels": 0,
            "pct_positive_definite": 0.0,
            "eigenvalue_min": 0.0,
            "eigenvalue_max": 0.0,
            "eigenvalue_mean": 0.0,
            "fa_mean": 0.0,
            "fa_median": 0.0,
            "fa_max": 0.0,
        }

    # Extract non-zero voxels: (N, 6)
    voxels = data[nonzero_mask]

    # Reconstruct 3x3 symmetric tensors: (N, 3, 3)
    N = voxels.shape[0]
    tensors = np.zeros((N, 3, 3), dtype=np.float32)
    tensors[:, 0, 0] = voxels[:, 0]  # Dxx
    tensors[:, 0, 1] = voxels[:, 1]  # Dxy
    tensors[:, 0, 2] = voxels[:, 2]  # Dxz
    tensors[:, 1, 0] = voxels[:, 1]  # Dxy (symmetric)
    tensors[:, 1, 1] = voxels[:, 3]  # Dyy
    tensors[:, 1, 2] = voxels[:, 4]  # Dyz
    tensors[:, 2, 0] = voxels[:, 2]  # Dxz (symmetric)
    tensors[:, 2, 1] = voxels[:, 4]  # Dyz (symmetric)
    tensors[:, 2, 2] = voxels[:, 5]  # Dzz

    # Eigenvalues: (N, 3), sorted ascending
    eigenvalues = np.linalg.eigvalsh(tensors)

    # Positive-definiteness: all eigenvalues > 0
    pd_mask = np.all(eigenvalues > 0, axis=-1)
    pd_voxels = int(np.count_nonzero(pd_mask))

    # FA computation
    lam_mean = eigenvalues.mean(axis=-1, keepdims=True)  # (N, 1)
    lam_sq_sum = np.sum(eigenvalues**2, axis=-1)  # (N,)
    lam_diff_sq_sum = np.sum((eigenvalues - lam_mean) ** 2, axis=-1)  # (N,)

    denom = lam_sq_sum.copy()
    denom[denom == 0] = 1.0  # avoid division by zero
    fa = np.sqrt(1.5) * np.sqrt(lam_diff_sq_sum) / np.sqrt(denom)
    fa = np.clip(fa, 0.0, 1.0)

    return {
        "total_voxels": total_voxels,
        "nonzero_voxels": nonzero_voxels,
        "pct_nonzero": round(100.0 * nonzero_voxels / total_voxels, 2),
        "positive_definite_voxels": pd_voxels,
        "pct_positive_definite": round(100.0 * pd_voxels / nonzero_voxels, 2),
        "eigenvalue_min": round(float(eigenvalues.min()), 6),
        "eigenvalue_max": round(float(eigenvalues.max()), 6),
        "eigenvalue_mean": round(float(eigenvalues.mean()), 6),
        "fa_mean": round(float(fa.mean()), 4),
        "fa_median": round(float(np.median(fa)), 4),
        "fa_max": round(float(fa.max()), 4),
    }


def generate_color_fa_image(
    tensor_file: str, t1_file: str
) -> dict[str, list[dict[str, Any]]]:
    """Generate color-coded FA direction maps overlaid on T1.

    Standard DTI color convention:
      R = |V1_x| * FA  (left-right)
      G = |V1_y| * FA  (anterior-posterior)
      B = |V1_z| * FA  (superior-inferior)

    Parameters
    ----------
    tensor_file : str
        Path to a 4D NIfTI (X, Y, Z, 6) tensor file.
    t1_file : str
        Path to a 3D T1-weighted NIfTI.

    Returns
    -------
    dict
        ``{"axial": [...], "coronal": [...]}`` where each list contains
        dicts with ``"base64"`` and ``"slice_num"`` keys.
    """
    import base64
    import io

    import matplotlib.pyplot as plt
    import nibabel as nib
    import numpy as np
    from scipy.ndimage import zoom

    # Load data
    t1_img = nib.load(t1_file)
    t1_data = t1_img.get_fdata()
    tensor_img = nib.load(tensor_file)
    tensor_data = tensor_img.get_fdata(dtype=np.float32)

    # Build RGB color-FA volume -----------------------------------------------
    spatial = tensor_data.shape[:3]
    rgb = np.zeros((*spatial, 3), dtype=np.float32)

    nonzero_mask = np.any(tensor_data != 0, axis=-1)
    voxels = tensor_data[nonzero_mask]  # (N, 6)

    N = voxels.shape[0]
    tensors = np.zeros((N, 3, 3), dtype=np.float32)
    tensors[:, 0, 0] = voxels[:, 0]
    tensors[:, 0, 1] = voxels[:, 1]
    tensors[:, 0, 2] = voxels[:, 2]
    tensors[:, 1, 0] = voxels[:, 1]
    tensors[:, 1, 1] = voxels[:, 3]
    tensors[:, 1, 2] = voxels[:, 4]
    tensors[:, 2, 0] = voxels[:, 2]
    tensors[:, 2, 1] = voxels[:, 4]
    tensors[:, 2, 2] = voxels[:, 5]

    eigenvalues, eigenvectors = np.linalg.eigh(tensors)
    # V1 = eigenvector corresponding to largest eigenvalue (last column)
    v1 = eigenvectors[:, :, -1]  # (N, 3)

    # FA
    lam_mean = eigenvalues.mean(axis=-1, keepdims=True)
    lam_sq_sum = np.sum(eigenvalues**2, axis=-1)
    lam_diff_sq_sum = np.sum((eigenvalues - lam_mean) ** 2, axis=-1)
    denom = lam_sq_sum.copy()
    denom[denom == 0] = 1.0
    fa = np.sqrt(1.5) * np.sqrt(lam_diff_sq_sum) / np.sqrt(denom)
    fa = np.clip(fa, 0.0, 1.0)

    # RGB = |V1| * FA
    rgb_vals = np.abs(v1) * fa[:, np.newaxis]
    rgb[nonzero_mask] = rgb_vals

    # Resample RGB to T1 shape if needed
    if spatial != t1_data.shape:
        zoom_factors = [t1_data.shape[i] / spatial[i] for i in range(3)]
        rgb = np.stack(
            [zoom(rgb[..., c], zoom_factors, order=1) for c in range(3)],
            axis=-1,
        )

    # Also build a scalar FA volume for masking
    fa_vol = np.zeros(spatial, dtype=np.float32)
    fa_vol[nonzero_mask] = fa
    if spatial != t1_data.shape:
        fa_vol = zoom(fa_vol, zoom_factors, order=1)

    # Normalize T1 for display (same pattern as static_overlay.py)
    nonzero_t1 = t1_data[t1_data > 0]
    if nonzero_t1.size == 0:
        t1_min, t1_max = float(np.min(t1_data)), float(np.max(t1_data))
    else:
        t1_min, t1_max = np.percentile(nonzero_t1, [2, 98])
    denom_t1 = (t1_max - t1_min) if (t1_max - t1_min) != 0 else 1.0
    t1_normalized = np.clip((t1_data - t1_min) / denom_t1, 0, 1)

    # Voxel sizes (mm) — used to resample slices to a resolution-independent
    # display grid so that the same anatomy produces the same pixel output
    # regardless of acquisition resolution.
    voxel_sizes = t1_img.header.get_zooms()[:3]
    vx, vy, vz = (float(v) for v in voxel_sizes)

    # Slice positions
    dims = t1_data.shape
    num_slices = 7

    def safe_slices(dim_size: int, n: int) -> np.ndarray:
        start = dim_size // 4
        end = min((dim_size * 3) // 4, dim_size - 1)
        return np.linspace(start, end, n).astype(int)

    slice_positions = {
        "axial": safe_slices(dims[2], num_slices),
        "coronal": safe_slices(dims[1], num_slices),
    }

    generated_images: dict[str, list[dict[str, Any]]] = {
        "axial": [],
        "coronal": [],
    }

    # Per-orientation voxel-size mapping (row_vox, col_vox) AFTER rot90.
    #   axial   [:,:,z] shape (dx,dy) → rot90 → (dy,dx): row=vy, col=vx
    #   coronal [:, y,:] shape (dx,dz) → rot90 → (dz,dx): row=vz, col=vx
    orientations = [
        ("axial", 2, vy, vx),
        ("coronal", 1, vz, vx),
    ]

    for orientation, axis, row_vox, col_vox in orientations:
        positions = slice_positions[orientation]

        # Compute display-grid zoom factors for this orientation (constant
        # across slices of the same orientation).
        if orientation == "axial":
            sample_shape = t1_normalized[:, :, positions[0]].shape
        else:
            sample_shape = t1_normalized[:, positions[0], :].shape
        nrows, ncols = sample_shape[1], sample_shape[0]
        phys_h = nrows * row_vox
        phys_w = ncols * col_vox
        scale = _DISPLAY_MAX_PX / max(phys_h, phys_w)
        target_h = max(1, round(phys_h * scale))
        target_w = max(1, round(phys_w * scale))
        zh = target_h / nrows
        zw = target_w / ncols

        for i, slice_pos in enumerate(positions):
            if orientation == "axial":
                t1_slice = t1_normalized[:, :, slice_pos]
                rgb_slice = rgb[:, :, slice_pos, :]
                fa_slice = fa_vol[:, :, slice_pos]
            else:  # coronal
                t1_slice = t1_normalized[:, slice_pos, :]
                rgb_slice = rgb[:, slice_pos, :, :]
                fa_slice = fa_vol[:, slice_pos, :]

            # Orientation corrections (same as static_overlay.py)
            t1_slice = np.rot90(t1_slice, k=1)
            rgb_slice = np.rot90(rgb_slice, k=1)
            fa_slice = np.rot90(fa_slice, k=1)
            if orientation == "coronal":
                t1_slice = np.fliplr(t1_slice)
                rgb_slice = np.fliplr(rgb_slice)
                fa_slice = np.fliplr(fa_slice)

            # Resample to resolution-independent display grid
            t1_slice = zoom(t1_slice, (zh, zw), order=1)
            rgb_slice = np.stack(
                [zoom(rgb_slice[..., c], (zh, zw), order=1) for c in range(3)],
                axis=-1,
            )
            fa_slice = zoom(fa_slice, (zh, zw), order=1)

            # Normalize RGB slice to [0,1] for display
            rgb_max = rgb_slice.max()
            if rgb_max > 0:
                rgb_display = rgb_slice / rgb_max
            else:
                rgb_display = rgb_slice

            # Build RGBA overlay with alpha from FA
            rgba = np.zeros((*rgb_display.shape[:2], 4), dtype=np.float32)
            rgba[..., :3] = rgb_display
            rgba[..., 3] = np.where(fa_slice > 0.05, 0.6, 0.0)

            # Figure sized to the resampled pixel grid
            dpi = 100
            fig_w = target_w / dpi + 0.3
            fig_h = target_h / dpi + 0.5
            fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=dpi)
            try:
                ax.imshow(
                    t1_slice,
                    cmap="gray",
                    alpha=1.0,
                    aspect="equal",
                    vmin=0,
                    vmax=1,
                )
                ax.imshow(rgba, aspect="equal")

                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_title(
                    f"{orientation.title()} {i + 1}",
                    fontsize=12,
                    fontweight="bold",
                    pad=10,
                )

                # Orientation labels
                if orientation == "axial":
                    ax.text(
                        0.05,
                        0.95,
                        "L",
                        transform=ax.transAxes,
                        fontsize=10,
                        fontweight="bold",
                        color="white",
                        va="top",
                        ha="left",
                    )
                    ax.text(
                        0.95,
                        0.95,
                        "R",
                        transform=ax.transAxes,
                        fontsize=10,
                        fontweight="bold",
                        color="white",
                        va="top",
                        ha="right",
                    )
                else:  # coronal
                    ax.text(
                        0.05,
                        0.95,
                        "R",
                        transform=ax.transAxes,
                        fontsize=10,
                        fontweight="bold",
                        color="white",
                        va="top",
                        ha="left",
                    )
                    ax.text(
                        0.95,
                        0.95,
                        "L",
                        transform=ax.transAxes,
                        fontsize=10,
                        fontweight="bold",
                        color="white",
                        va="top",
                        ha="right",
                    )

                buf = io.BytesIO()
                plt.savefig(
                    buf,
                    dpi=dpi,
                    bbox_inches="tight",
                    facecolor="white",
                    edgecolor="none",
                    format="png",
                )
                buf.seek(0)
                image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            finally:
                plt.close(fig)

            generated_images[orientation].append(
                {
                    "base64": image_base64,
                    "slice_num": i + 1,
                }
            )

    return generated_images
