"""Atlas overlap analysis for significant voxel clusters."""

from __future__ import annotations

import os
from typing import Dict, List, Optional


def check_and_resample_atlas(atlas_img, reference_img, atlas_name: str, verbose: bool = True):
    """Check if atlas dimensions match reference, resample if needed.

    Args:
        atlas_img: nibabel image of the atlas.
        reference_img: nibabel image of the reference (subject data).
        atlas_name: Name of atlas for logging.
        verbose: Print information.

    Returns:
        Atlas data as integer ndarray in correct dimensions.
    """
    import numpy as np
    from nibabel.processing import resample_from_to
    import nibabel as nib

    atlas_shape = atlas_img.shape
    ref_shape = reference_img.shape

    if verbose:
        print(f"  Atlas shape: {atlas_shape}")
        print(f"  Reference shape: {ref_shape[:3]}")

    if atlas_shape[:3] != ref_shape[:3]:
        if verbose:
            print(f"  Dimensions don't match. Resampling atlas...")

        if len(ref_shape) > 3:
            ref_data_3d = reference_img.get_fdata()[:, :, :, 0]
        else:
            ref_data_3d = reference_img.get_fdata()

        ref_img_3d = nib.Nifti1Image(
            ref_data_3d.astype(np.float32),
            reference_img.affine[:4, :4],
            None,
        )

        atlas_data_raw = atlas_img.get_fdata()
        if len(atlas_data_raw.shape) > 3:
            atlas_data_raw = atlas_data_raw[:, :, :, 0]

        atlas_img_3d = nib.Nifti1Image(
            atlas_data_raw.astype(np.float32),
            atlas_img.affine[:4, :4],
            None,
        )

        resampled_atlas = resample_from_to(atlas_img_3d, ref_img_3d, order=0)
        atlas_data = resampled_atlas.get_fdata().astype(int)
        if verbose:
            print(f"  Resampled to: {atlas_data.shape}")
    else:
        if verbose:
            print(f"  Dimensions match.")
        atlas_data = atlas_img.get_fdata().astype(int)
        if len(atlas_data.shape) > 3:
            atlas_data = atlas_data[:, :, :, 0]

    return atlas_data


def atlas_overlap_analysis(
    sig_mask,
    atlas_files: List[str],
    data_dir: str,
    reference_img=None,
    verbose: bool = True,
) -> Dict[str, list]:
    """Analyze overlap between significant voxels and atlas regions.

    Args:
        sig_mask: Binary ndarray (x, y, z) of significant voxels.
        atlas_files: List of atlas file names.
        data_dir: Directory containing atlas files.
        reference_img: nibabel image for resampling (optional).
        verbose: Print progress information.

    Returns:
        Dict mapping atlas names to lists of region overlap dicts.
    """
    import numpy as np
    import nibabel as nib

    if verbose:
        print("\n" + "=" * 60)
        print("ATLAS OVERLAP ANALYSIS")
        print("=" * 60)

    results: Dict[str, list] = {}

    for atlas_file in atlas_files:
        atlas_path = os.path.join(data_dir, atlas_file)
        if not os.path.exists(atlas_path):
            if verbose:
                print(f"Warning: Atlas file not found - {atlas_file}")
            continue

        if verbose:
            print(f"\n--- {atlas_file} ---")
        atlas_img = nib.load(atlas_path)

        if reference_img is not None:
            atlas_data = check_and_resample_atlas(
                atlas_img, reference_img, atlas_file, verbose
            )
        else:
            atlas_data = atlas_img.get_fdata().astype(int)

        regions = np.unique(atlas_data[atlas_data > 0])

        region_counts = []
        for region_id in regions:
            region_mask = atlas_data == region_id
            overlap = np.sum(sig_mask & region_mask)

            if overlap > 0:
                region_counts.append(
                    {
                        "region_id": int(region_id),
                        "overlap_voxels": int(overlap),
                        "region_size": int(np.sum(region_mask)),
                    }
                )

        region_counts = sorted(
            region_counts, key=lambda x: x["overlap_voxels"], reverse=True
        )

        if verbose:
            print(f"\nTop regions by significant voxel count:")
            for i, r in enumerate(region_counts[:15], 1):
                pct = 100 * r["overlap_voxels"] / r["region_size"]
                print(
                    f"{i:2d}. Region {r['region_id']:3d}: {r['overlap_voxels']:4d} sig. voxels "
                    f"({pct:.1f}% of region)"
                )

        results[atlas_file] = region_counts

    return results
