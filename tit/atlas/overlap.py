"""
Atlas related functions for NIfTI operations

1. Identify overlaps (based on image dimensions)
2. Resample image to a reference if needed.

"""


import logging
import os

logger = logging.getLogger(__name__)


def check_and_resample_atlas(atlas_img, reference_img, atlas_name: str):
    """Check if atlas dimensions match reference, resample if needed.

    Args:
        atlas_img: nibabel image of the atlas.
        reference_img: nibabel image of the reference (subject data).
        atlas_name: Name of atlas for logging.

    Returns:
        Atlas data as integer ndarray in correct dimensions.
    """
    import numpy as np
    from nibabel.processing import resample_from_to
    import nibabel as nib

    atlas_shape = atlas_img.shape
    ref_shape = reference_img.shape

    logger.info("  Atlas shape: %s", atlas_shape)
    logger.info("  Reference shape: %s", ref_shape[:3])

    if atlas_shape[:3] != ref_shape[:3]:
        logger.info("  Dimensions don't match. Resampling atlas...")

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
        logger.info("  Resampled to: %s", atlas_data.shape)
    else:
        logger.info("  Dimensions match.")
        atlas_data = atlas_img.get_fdata().astype(int)
        if len(atlas_data.shape) > 3:
            atlas_data = atlas_data[:, :, :, 0]

    return atlas_data


def atlas_overlap_analysis(
    sig_mask,
    atlas_files: list[str],
    data_dir: str,
    reference_img=None,
) -> dict[str, list]:
    """Analyze overlap between significant voxels and atlas regions.

    Args:
        sig_mask: Binary ndarray (x, y, z) of significant voxels.
        atlas_files: List of atlas file names.
        data_dir: Directory containing atlas files.
        reference_img: nibabel image for resampling (optional).

    Returns:
        Dict mapping atlas names to lists of region overlap dicts.
    """
    import numpy as np
    import nibabel as nib

    logger.info("\n" + "=" * 60)
    logger.info("ATLAS OVERLAP ANALYSIS")
    logger.info("=" * 60)

    results: dict[str, list] = {}

    for atlas_file in atlas_files:
        atlas_path = os.path.join(data_dir, atlas_file)
        if not os.path.exists(atlas_path):
            logger.warning("Atlas file not found - %s", atlas_file)
            continue

        logger.info("\n--- %s ---", atlas_file)
        atlas_img = nib.load(atlas_path)

        if reference_img is not None:
            atlas_data = check_and_resample_atlas(atlas_img, reference_img, atlas_file)
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

        logger.info("\nTop regions by significant voxel count:")
        for i, r in enumerate(region_counts[:15], 1):
            pct = 100 * r["overlap_voxels"] / r["region_size"]
            logger.info(
                "%2d. Region %3d: %4d sig. voxels (%.1f%% of region)",
                i,
                r["region_id"],
                r["overlap_voxels"],
                pct,
            )

        results[atlas_file] = region_counts

    return results
