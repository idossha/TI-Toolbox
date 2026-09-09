"""Read-only volumetric target geometry on the subject T1 grid."""

from pathlib import Path
import tempfile
from typing import Any


def target_image(
    anatomy_path: str | Path,
    roi: Any,
    m2m: str | Path,
    output_dir: str | Path,
    source_path: str | Path | None = None,
) -> Any:
    """Rasterize a target in subject RAS mm; labels use nearest-neighbour sampling.

    MNI spheres transform their centers, preserving their radius in millimetres,
    exactly as SimNIBS sphere ROIs do. MNI volumes use nonlinear registration.
    This displays geometric selection, without optimizer tissue/surface filtering.
    """
    import nibabel as nib
    import numpy as np
    from nibabel.processing import resample_from_to
    from tit.opt.masks import prepare_mask

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
        # Slice-wise world coordinates bound memory for normal 256-cubed T1s.
        j, k = np.indices(anatomy.shape[1:])
        for i in range(anatomy.shape[0]):
            voxels = np.column_stack((np.full(j.size, i), j.ravel(), k.ravel()))
            points = nib.affines.apply_affine(anatomy.affine, voxels)
            selected = np.zeros(j.size, dtype=bool)
            for center, sphere in zip(centers, roi.spheres):
                selected |= np.sum((points - center) ** 2, axis=1) <= sphere.radius**2
            data[i] = selected.reshape(j.shape)
    else:
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
            prepared = prepare_mask(source, roi.space, str(m2m), temporary, binary=True)
            image = resample_from_to(
                nib.load(prepared), (anatomy.shape, anatomy.affine), order=0
            )
            data = (image.get_fdata() > 0).astype(np.uint8)
    if not data.any():
        raise ValueError(
            "Target does not overlap the subject T1 grid; check target space and registration"
        )
    return nib.Nifti1Image(data, anatomy.affine)
