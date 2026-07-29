"""
Static overlay image generation helpers (matplotlib).

This is shared plotting functionality used by reporting code to generate
small PNG slices (base64-encoded) for HTML reports.
"""

from typing import Any

# Maximum pixel size for the longest physical dimension of a display slice.
# Slices are resampled from voxel-space to this display grid using the NIfTI
# voxel sizes, so the same anatomy always produces the same pixel output
# regardless of acquisition resolution (following the nilearn / nireports
# pattern of affine-aware resampling before display).
_DISPLAY_MAX_PX = 256


def generate_static_overlay_images(
    *,
    t1_file: str,
    overlay_file: str,
    subject_id: str | None = None,
    montage_name: str | None = None,
    output_dir: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Generate static overlay images for axial, sagittal, and coronal views.

    Returns a dict with keys: 'axial', 'sagittal', 'coronal'. Each value is a list of dicts:
      - base64: base64-encoded PNG
      - slice_num: 1-based slice index within that orientation
      - overlay_voxels: number of non-zero overlay voxels in that slice
    """
    # Kept as a local import so importing tit.plotting doesn't require these deps.
    import base64
    import io

    import nibabel as nib
    import numpy as np
    import matplotlib.pyplot as plt
    from scipy.ndimage import zoom

    # Load NIfTI files
    t1_img = nib.load(t1_file)
    overlay_img = nib.load(overlay_file)

    # Get data arrays
    t1_data = t1_img.get_fdata()
    overlay_data = overlay_img.get_fdata()

    # Handle 4D arrays (take first volume)
    if len(overlay_data.shape) == 4:
        overlay_data = overlay_data[..., 0]

    # Check if dimensions match and adjust if needed
    if t1_data.shape != overlay_data.shape:
        # Resample overlay to match T1 dimensions
        zoom_factors = [t1_data.shape[i] / overlay_data.shape[i] for i in range(3)]
        overlay_data = zoom(overlay_data, zoom_factors, order=1)

    # Voxel sizes (mm) from the T1 header — used to resample slices to a
    # resolution-independent display grid.
    voxel_sizes = t1_img.header.get_zooms()[:3]

    # Normalize T1 data for display (robust normalization)
    nonzero = t1_data[t1_data > 0]
    if nonzero.size == 0:
        # Degenerate case; keep as-is
        t1_min, t1_max = float(np.min(t1_data)), float(np.max(t1_data))
    else:
        t1_min, t1_max = np.percentile(nonzero, [2, 98])
    denom = (t1_max - t1_min) if (t1_max - t1_min) != 0 else 1.0
    t1_normalized = np.clip((t1_data - t1_min) / denom, 0, 1)

    # Normalize overlay data
    overlay_max = float(np.max(overlay_data))
    if overlay_max > 0:
        overlay_normalized = overlay_data / overlay_max
    else:
        overlay_normalized = overlay_data

    # Create mask for non-zero overlay values
    overlay_mask = overlay_data > (overlay_max * 0.1)  # Show values above 10% of max

    # Get dimensions for slice planning
    dims = t1_data.shape

    # Define slice positions for each orientation (create 7 slices each)
    num_slices = 7

    def safe_slices(dim_size: int, n: int) -> np.ndarray:
        start = dim_size // 4
        end = min((dim_size * 3) // 4, dim_size - 1)
        return np.linspace(start, end, n).astype(int)

    slice_positions = {
        "axial": safe_slices(dims[2], num_slices),
        "sagittal": safe_slices(dims[0], num_slices),
        "coronal": safe_slices(dims[1], num_slices),
    }

    # Create colormap for overlay (hot colormap)
    cmap = plt.cm.hot
    cmap.set_bad(color=(0, 0, 0, 0))  # transparent for masked values

    # Per-orientation voxel-size mapping (row_vox, col_vox) AFTER rot90.
    # rot90(k=1) maps input (m, n) → output (n, m), so:
    #   axial   [:,:,z] shape (dx,dy) → rot90 → (dy,dx): row=vy, col=vx
    #   sagittal[x,:,:] shape (dy,dz) → rot90 → (dz,dy): row=vz, col=vy
    #   coronal [:, y,:] shape (dx,dz) → rot90 → (dz,dx): row=vz, col=vx
    vx, vy, vz = (float(v) for v in voxel_sizes)
    orientations = [
        ("axial", 2, vy, vx),
        ("sagittal", 0, vz, vy),
        ("coronal", 1, vz, vx),
    ]

    generated_images: dict[str, list[dict[str, Any]]] = {
        "axial": [],
        "sagittal": [],
        "coronal": [],
    }

    for orientation, axis, row_vox, col_vox in orientations:
        positions = slice_positions[orientation]

        # Compute display-grid zoom factors for this orientation (constant
        # across slices of the same orientation).
        sample_pos = positions[0]
        if orientation == "axial":
            sample_shape = t1_normalized[:, :, sample_pos].shape
        elif orientation == "sagittal":
            sample_shape = t1_normalized[sample_pos, :, :].shape
        else:
            sample_shape = t1_normalized[:, sample_pos, :].shape
        # After rot90 the shape flips
        nrows, ncols = sample_shape[1], sample_shape[0]
        phys_h = nrows * row_vox
        phys_w = ncols * col_vox
        scale = _DISPLAY_MAX_PX / max(phys_h, phys_w)
        target_h = max(1, round(phys_h * scale))
        target_w = max(1, round(phys_w * scale))
        zh = target_h / nrows
        zw = target_w / ncols

        for i, slice_pos in enumerate(positions):
            # Extract slice data based on orientation
            if orientation == "axial":
                t1_slice = t1_normalized[:, :, slice_pos]
                overlay_slice = overlay_normalized[:, :, slice_pos]
                mask_slice = overlay_mask[:, :, slice_pos]
            elif orientation == "sagittal":
                t1_slice = t1_normalized[slice_pos, :, :]
                overlay_slice = overlay_normalized[slice_pos, :, :]
                mask_slice = overlay_mask[slice_pos, :, :]
            else:  # coronal
                t1_slice = t1_normalized[:, slice_pos, :]
                overlay_slice = overlay_normalized[:, slice_pos, :]
                mask_slice = overlay_mask[:, slice_pos, :]

            # Orientation corrections
            t1_slice = np.rot90(t1_slice, k=1)
            overlay_slice = np.rot90(overlay_slice, k=1)
            mask_slice = np.rot90(mask_slice, k=1)
            if orientation == "coronal":
                # Flip for neurological convention
                t1_slice = np.fliplr(t1_slice)
                overlay_slice = np.fliplr(overlay_slice)
                mask_slice = np.fliplr(mask_slice)

            # Resample to resolution-independent display grid
            t1_slice = zoom(t1_slice, (zh, zw), order=1)
            overlay_slice = zoom(overlay_slice, (zh, zw), order=1)
            mask_slice = zoom(mask_slice.astype(np.float32), (zh, zw), order=0) > 0.5

            overlay_masked = np.ma.masked_where(~mask_slice, overlay_slice)

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

                overlay_voxels = int(np.sum(mask_slice))
                if overlay_voxels > 0:
                    ax.imshow(
                        overlay_masked,
                        cmap=cmap,
                        alpha=0.6,
                        aspect="equal",
                        vmin=0,
                        vmax=1,
                    )

                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_title(
                    f"{orientation.title()} {i+1}",
                    fontsize=12,
                    fontweight="bold",
                    pad=10,
                )

                # Compact orientation labels
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
                elif orientation == "sagittal":
                    ax.text(
                        0.05,
                        0.95,
                        "A",
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
                        "P",
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
                    "overlay_voxels": overlay_voxels,
                }
            )

    return generated_images
