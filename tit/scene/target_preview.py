"""Read-only targets on subject grids; MNI volume previews use a compact grid."""

from pathlib import Path
import tempfile
from typing import Any


def target_image(
    anatomy_path: str | Path,
    roi: Any,
    m2m: str | Path,
    output_dir: str | Path,
    source_path: str | Path | None = None,
    deformation_path: str | Path | None = None,
) -> Any:
    """Rasterize a target in subject RAS mm; labels use nearest-neighbour sampling.

    MNI spheres transform their centers, preserving their radius in millimetres,
    exactly as SimNIBS sphere ROIs do. MNI volumes use nonlinear registration.
    This displays geometric selection, without optimizer tissue/surface filtering.
    Without deformation_path, anatomy_path is the original subject T1. The route
    supplies cached display anatomy and its sampled subject-to-MNI deformation
    for MNI volumes only; these are approximate display samples, never analysis masks.
    """
    import nibabel as nib
    import numpy as np
    from nibabel.processing import resample_from_to

    anatomy = nib.load(str(anatomy_path))
    if len(anatomy.shape) != 3 or not np.isfinite(anatomy.affine).all():
        raise ValueError(
            "Subject T1 must be a three-dimensional volume with a finite affine"
        )
    if abs(np.linalg.det(anatomy.affine[:3, :3])) < 1e-12:
        raise ValueError("Subject T1 affine is singular")
    if np.prod(anatomy.shape, dtype=np.float64) > 128 * 1024 * 1024:
        raise ValueError("Subject T1 exceeds the preview voxel limit")
    if roi.kind == "spherical":
        centers = np.asarray([sphere.center for sphere in roi.spheres], dtype=float)
        if roi.space == "mni":
            from simnibs import mni2subject_coords

            centers = np.atleast_2d(mni2subject_coords(centers, str(m2m)))
        if centers.shape != (len(roi.spheres), 3) or not np.isfinite(centers).all():
            raise ValueError(
                "MNI sphere centers could not be transformed to subject space"
            )
        data = np.zeros(anatomy.shape, dtype=np.uint8)
        inverse = np.linalg.inv(anatomy.affine)
        # A world-space sphere maps to an ellipsoid: inverse row norms give
        # its exact voxel-axis extents, including rotated and sheared grids.
        for center, sphere in zip(centers, roi.spheres):
            voxel_center = nib.affines.apply_affine(inverse, center)
            extent = sphere.radius * np.linalg.norm(inverse[:3, :3], axis=1)
            lower = np.maximum(0, np.floor(voxel_center - extent)).astype(int)
            upper = np.minimum(
                anatomy.shape, np.ceil(voxel_center + extent) + 1
            ).astype(int)
            if np.any(lower >= upper):
                continue
            j, k = np.meshgrid(
                np.arange(lower[1], upper[1]),
                np.arange(lower[2], upper[2]),
                indexing="ij",
            )
            for i in range(lower[0], upper[0]):
                voxels = np.column_stack((np.full(j.size, i), j.ravel(), k.ravel()))
                points = nib.affines.apply_affine(anatomy.affine, voxels)
                selected = np.sum((points - center) ** 2, axis=1) <= sphere.radius**2
                data[i, lower[1] : upper[1], lower[2] : upper[2]] |= selected.reshape(
                    j.shape
                )
    else:
        from tit.opt.masks import prepare_mask

        with tempfile.TemporaryDirectory(dir=output_dir) as temporary:
            source = str(source_path)
            if roi.kind == "subcortical":
                image = nib.load(source)
                if len(image.shape) != 3:
                    raise ValueError("Atlas must be a three-dimensional volume")
                if np.prod(image.shape, dtype=np.float64) > 128 * 1024 * 1024:
                    raise ValueError("Atlas exceeds the preview voxel limit")
                values = image.get_fdata(dtype=np.float32)
                if not np.isfinite(values).all():
                    raise ValueError("Atlas contains non-finite values")
                selected = np.isin(values, roi.labels).astype(np.uint8)
                if not selected.any():
                    raise ValueError("Selected labels are absent from this atlas")
                source = str(Path(temporary) / "selected.nii")
                nib.save(nib.Nifti1Image(selected, image.affine), source)
            if deformation_path is not None:
                from tit.opt.masks import validate_mask
                from simnibs.utils.transformations import volumetric_nonlinear

                mask = validate_mask(source)
                deformation = nib.load(str(deformation_path))
                values = volumetric_nonlinear(
                    (
                        (mask.get_fdata(dtype=np.float32) > 0).astype(np.uint8),
                        mask.affine,
                    ),
                    (deformation.get_fdata(dtype=np.float32), deformation.affine),
                    intorder=0,
                )
                image = nib.Nifti1Image(values, deformation.affine)
            else:
                prepared = prepare_mask(
                    source, roi.space, str(m2m), temporary, binary=True
                )
                image = resample_from_to(
                    nib.load(prepared), (anatomy.shape, anatomy.affine), order=0
                )
            data = (image.get_fdata() > 0).astype(np.uint8)
    if not data.any() and deformation_path is not None:
        raise ValueError(
            "Target is outside the subject or too small for the lightweight preview grid; "
            "inspect the full-resolution mask in Viewer"
        )
    if not data.any():
        raise ValueError(
            "Target does not overlap the subject T1 grid; check target space and registration"
        )
    return nib.Nifti1Image(data, anatomy.affine)


def preview_anatomy(anatomy_path: str | Path) -> Any:
    """Sample display-only anatomy with at most 192 voxels along each axis.

    Striding preserves the original sample centers in subject RAS mm, including
    oblique/sheared affines. Only MNI volume previews share this compact grid;
    spheres and subject-space masks retain their original T1 sampling.
    """
    import nibabel as nib
    import numpy as np

    image = nib.load(str(anatomy_path))
    if len(image.shape) != 3:
        raise ValueError("Subject T1 must be a three-dimensional volume")
    if (
        not np.isfinite(image.affine).all()
        or abs(np.linalg.det(image.affine[:3, :3])) < 1e-12
    ):
        raise ValueError("Subject T1 affine is invalid")
    if np.prod(image.shape, dtype=np.float64) > 128 * 1024 * 1024:
        raise ValueError("Subject T1 exceeds the preview voxel limit")
    steps = np.maximum(1, np.ceil(np.asarray(image.shape) / 192).astype(int))
    # Inflate compressed inputs once: proxy slicing may seek through gzip again.
    data = np.asarray(image.dataobj)[tuple(slice(None, None, int(s)) for s in steps)]
    affine = image.affine @ np.diag([*steps, 1])
    return nib.Nifti1Image(np.asarray(data, dtype=np.float32), affine)


def crop_target(image: Any) -> Any:
    """Remove empty outer voxels without changing any selected world coordinate."""
    import nibabel as nib
    import numpy as np

    data = np.asarray(image.dataobj)
    occupied = np.nonzero(data)
    if not occupied[0].size:
        raise ValueError("Target preview is empty")
    # One zero voxel borders the selected region where the source grid allows it.
    lower = np.maximum(0, [int(axis.min()) - 1 for axis in occupied])
    upper = np.minimum(data.shape, [int(axis.max()) + 2 for axis in occupied])
    cropped = data[tuple(slice(int(a), int(b)) for a, b in zip(lower, upper))]
    affine = image.affine.copy()
    affine[:3, 3] = nib.affines.apply_affine(image.affine, lower)
    return nib.Nifti1Image(cropped, affine)


def preview_deformation(m2m: str | Path, anatomy_path: str | Path) -> Any:
    """Cache subject-to-MNI world coordinates on the display grid, not science data.

    SimNIBS handles zero-boundary conventions; linear deformation sampling and
    nearest-neighbour label lookup use its existing nonlinear-transform semantics.
    """
    import nibabel as nib
    import numpy as np
    from nibabel.processing import resample_from_to
    from simnibs.utils.file_finder import SubjectFiles
    from simnibs.utils.transformations import _fix_boundary_zeros

    anatomy = nib.load(str(anatomy_path))
    deformation = nib.load(SubjectFiles(subpath=str(m2m)).conf2mni_nonl)
    values = _fix_boundary_zeros(deformation.get_fdata(dtype=np.float32))
    components = []
    for axis in range(3):
        image = nib.Nifti1Image(values[..., axis], deformation.affine)
        sampled = resample_from_to(
            image, (anatomy.shape, anatomy.affine), order=1, cval=np.inf
        )
        components.append(np.asarray(sampled.dataobj, dtype=np.float32))
    return nib.Nifti1Image(np.stack(components, axis=3), anatomy.affine)
