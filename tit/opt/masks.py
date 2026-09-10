"""Custom NIfTI mask validation and subject-space preparation."""

from pathlib import Path
import tempfile


def validate_mask(path: str):
    """Read a finite, nonempty 3D NIfTI mask; positive voxels are selected."""
    import nibabel as nib
    import numpy as np

    try:
        image = nib.load(path)
    except nib.filebasedimages.ImageFileError as exc:
        raise ValueError("File is not a readable NIfTI image") from exc
    if len(image.shape) != 3:
        raise ValueError("Mask must be a three-dimensional NIfTI volume")
    if np.prod(image.shape, dtype=np.float64) > 128 * 1024 * 1024:
        raise ValueError("Mask exceeds 128 million voxels")
    if (
        not np.isfinite(image.affine).all()
        or abs(np.linalg.det(image.affine[:3, :3])) < 1e-12
    ):
        raise ValueError("Mask has an invalid voxel-to-world affine")
    data = image.get_fdata(dtype=np.float32)
    if not np.isfinite(data).all() or not (data > 0).any():
        raise ValueError(
            "Mask must contain finite values and at least one positive voxel"
        )
    return image


def prepare_mask(
    path: str, space: str, m2m: str, output_dir: str, *, binary: bool = False
) -> str:
    """Use subject geometry unchanged; resample MNI masks with m2m registration.

    Nearest-neighbour interpolation preserves labels. The conformation affine
    alone is not an MNI registration. Derived files never overwrite the source.
    """
    import nibabel as nib
    import numpy as np

    if space not in ("subject", "mni"):
        raise ValueError("Mask space must be subject or mni")
    image = validate_mask(path)
    if space == "subject" and not binary:
        return path
    if binary:
        image = nib.Nifti1Image((image.get_fdata() > 0).astype(np.uint8), image.affine)
    if space == "mni":
        from simnibs.utils.file_finder import SubjectFiles
        from simnibs.utils.region_of_interest import mni_mask_to_sub

        image = mni_mask_to_sub(image, SubjectFiles(subpath=m2m))
        if not (image.get_fdata() > 0).any():
            raise ValueError(
                "MNI mask does not overlap the subject after transformation"
            )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="mask-", suffix=".nii", dir=output, delete=False
    ) as handle:
        destination = Path(handle.name)
    try:
        nib.save(image, str(destination))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return str(destination)


def validate_mask_paths(config) -> None:
    """Check input accessibility before planning or loading expensive search data."""
    paths = [
        (f"roi_atlas[{i}].atlas_path", target.atlas_path)
        for i, target in enumerate(getattr(config, "roi_atlas", None) or [])
    ]
    for field in ("roi", "non_roi"):
        roi = getattr(config, field, None)
        if roi is not None and getattr(roi, "label", "") is None:
            paths.append((f"{field}.atlas_path", roi.atlas_path))
    for field, path in paths:
        if not Path(path).is_file():
            raise ValueError(
                f"{field}: mask is not accessible in the container: {path}. "
                "Import it through the NIfTI mask picker, "
                "or use an existing path inside the container."
            )
