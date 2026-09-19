"""Custom NIfTI mask validation and subject-space preparation."""

import contextlib
import gzip
import logging
import os
import shutil
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def validate_mask(path: str):
    """Read a finite, nonempty 3D NIfTI mask; positive voxels are selected."""
    import nibabel as nib
    import numpy as np

    from tit.atlas.manifest import check_shipped

    check_shipped(path)
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
    path: str,
    space: str,
    m2m: str,
    output_dir: str,
    *,
    binary: bool = False,
    cache_dir: str | None = None,
) -> str:
    """Use subject geometry unchanged; resample MNI masks with m2m registration.

    Nearest-neighbour interpolation preserves labels. The conformation affine
    alone is not an MNI registration. Derived files never overwrite the source.

    An MNI mask is warped by :func:`warp_mni_to_subject`, which computes the
    same voxels SimNIBS's ``mni_mask_to_sub`` does but only inside the block of
    the subject grid the mask can land in, and keeps the result in *cache_dir*
    (by default the project's ``cache/masks/sub-<id>/mni-warp/``) so the ROI
    confirmation and the run that follows it warp each label once.  The file
    returned is always a fresh copy inside *output_dir*.
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
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if space == "mni":
        if cache_dir is None:
            cache_dir = default_warp_cache_dir(m2m)
        cached = _cached_warp_path(image, m2m, cache_dir)
        if cached is not None and cached.is_file():
            destination = output / f"mask-{cached.stem.split('.')[0]}.nii.gz"
            partial = _fresh_name(output, ".nii.gz.part")
            shutil.copyfile(cached, partial)
            os.replace(partial, destination)
            log.info(
                "Reusing the cached subject-space mask %s (no MNI warp needed)",
                cached.name,
            )
            image = nib.load(str(destination))
            if not (np.asanyarray(image.dataobj) > 0).any():
                raise ValueError(
                    "MNI mask does not overlap the subject after transformation"
                )
            return str(destination)
        image = warp_mni_to_subject(image, m2m)
        if not (np.asanyarray(image.dataobj) > 0).any():
            raise ValueError(
                "MNI mask does not overlap the subject after transformation"
            )
        # Named after the content so a later step keyed on the file (the
        # island cleanup) can reuse its own work across runs too.
        destination = (
            output / f"mask-{cached.stem.split('.')[0]}.nii.gz"
            if cached is not None
            else _fresh_name(output, ".nii.gz")
        )
        partial = _fresh_name(output, ".nii.gz.part")
        _save_nii_gz(image, partial)
        os.replace(partial, destination)
        if cached is not None:
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                partial = cached.with_name(cached.name + f".{os.getpid()}.part")
                shutil.copyfile(destination, partial)
                os.replace(partial, cached)
            except OSError as exc:  # a read-only or full cache is not an error
                log.debug("Subject-space mask not cached at %s: %s", cached, exc)
        return str(destination)
    destination = _fresh_name(output, ".nii")
    try:
        nib.save(image, str(destination))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return str(destination)


def _fresh_name(output: Path, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(
        prefix="mask-", suffix=suffix, dir=output, delete=False
    ) as handle:
        return Path(handle.name)


def _save_nii_gz(image, destination: Path) -> None:
    """Write *image* gzipped with the standard library.

    nibabel's own ``.nii.gz`` writer seeks backwards in the file it writes,
    which fails on a bind-mounted project inside the container.
    """
    import nibabel as nib

    plain = destination.with_name(destination.name + ".nii")
    try:
        nib.save(image, str(plain))
        with (
            open(plain, "rb") as source,
            gzip.open(str(destination), "wb", compresslevel=1) as out,
        ):
            shutil.copyfileobj(source, out, 16 * 1024 * 1024)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        plain.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# The MNI -> subject warp
# ---------------------------------------------------------------------------
#
# SimNIBS's ``mni_mask_to_sub`` resamples the *whole* non-linear deformation
# field (``toMNI/Conform2MNI_nonl.nii.gz``, 240x512x512x3 on Ernie-sized data)
# onto the subject's 0.5 mm grid with trilinear interpolation -- three
# ``map_coordinates`` passes over 100 million voxels -- and only then samples
# the mask.  cProfile on sub-101 (Dataset 000, one cerebellum label, under
# emulation): 87 s, of which 56 s is that resampling, 8.5 s
# ``_fix_boundary_zeros`` (a ``binary_fill_holes`` of the field), 7.7 s the
# gzip decode of the field and 3.6 s writing an 800 MB float64 result.
#
# A mask a few centimetres across can only land in a small block of the
# subject grid.  The field itself says where: every field voxel whose MNI
# coordinate falls inside the mask's (padded) MNI bounding box.  Only that block
# of the target grid is put through the exact SimNIBS arithmetic (same affine
# chain, same trilinear sampling of the field with ``cval=inf``, same
# nearest-neighbour sampling of the mask), and everything outside it is zero --
# which is what the full computation gives there too.  If a positive voxel
# touches the block's face the block is grown and recomputed, so a structure
# cannot be clipped.

_FIELD_CACHE: dict = {}
_FIELD_KEEP = 0


@contextlib.contextmanager
def keep_deformation_field():
    """Hold the deformation field in memory across several warps.

    Loading ``Conform2MNI_nonl.nii.gz`` is most of what a warp costs once the
    resampling is confined to the mask's block.  Wrap a loop that warps several
    labels of one subject in this so the field is decoded once; it is released
    when the outermost block exits.
    """
    global _FIELD_KEEP
    _FIELD_KEEP += 1
    try:
        yield
    finally:
        _FIELD_KEEP -= 1
        if _FIELD_KEEP == 0:
            _FIELD_CACHE.clear()


def _deformation_field(path: str):
    """``(data float32 (nx,ny,nz,3), affine)`` of a SimNIBS deformation field."""
    import nibabel as nib
    import numpy as np

    stat = os.stat(path)
    key = (stat.st_size, stat.st_mtime_ns)
    hit = _FIELD_CACHE.get(path)
    if hit is not None and hit[0] == key:
        return hit[1], hit[2]
    image = nib.load(path)
    data = image.get_fdata(dtype=np.float32)
    if data.ndim > 4:
        data = data.squeeze()
    if data.ndim != 4 or data.shape[3] != 3:
        raise ValueError(f"{path} is not a (x, y, z, 3) deformation field")
    if _FIELD_KEEP:
        _FIELD_CACHE[path] = (key, data, image.affine)
    return data, image.affine


def _subject_files(m2m: str):
    from simnibs.utils.file_finder import SubjectFiles

    files = SubjectFiles(subpath=m2m)
    if os.path.isfile(files.T1_upsampled):
        target = files.T1_upsampled
    elif os.path.isfile(files.reference_volume):
        target = files.reference_volume
    else:
        raise ValueError(
            "Subject folder does not contain a T1 image for the MNI transformation"
        )
    return target, files.conf2mni_nonl


def default_warp_cache_dir(m2m: str) -> str | None:
    """``<project>/.ti-toolbox/cache/masks/sub-<id>/mni-warp/`` for this m2m.

    ``None`` when there is no project (a script outside a run, a unit test) or
    the directory is not an ``m2m_<id>``; the warp then runs uncached.
    """
    name = os.path.basename(os.path.normpath(m2m))
    if not name.startswith("m2m_") or len(name) <= 4:
        return None
    try:
        from tit.paths import get_path_manager

        return get_path_manager().ensure_cache("masks", f"sub-{name[4:]}", "mni-warp")
    except Exception:  # noqa: BLE001 - no project, invalid id, unwritable cache
        return None


def _cached_warp_path(image, m2m: str, cache_dir: str | None):
    """Where the subject-space copy of *image* lives, or ``None`` if uncacheable.

    The name is a digest of the mask's voxels and affine, the target grid and
    the deformation field's identity (path, size, mtime), so a re-run head model
    or a different label never reads a stale mask.
    """
    import hashlib
    import nibabel as nib
    import numpy as np

    if not cache_dir:
        return None
    try:
        target_path, field_path = _subject_files(m2m)
        target = nib.load(target_path)
        field_stat = os.stat(field_path)
    except (OSError, ValueError):
        return None
    data = np.ascontiguousarray(np.squeeze(np.asanyarray(image.dataobj)))
    digest = hashlib.sha256()
    digest.update(b"tit-mni-warp-v1|")
    digest.update(str(data.dtype).encode() + b"|" + str(data.shape).encode())
    digest.update(data.tobytes())
    digest.update(np.asarray(image.affine, dtype=np.float64).tobytes())
    digest.update(str(tuple(target.shape[:3])).encode())
    digest.update(np.asarray(target.affine, dtype=np.float64).tobytes())
    digest.update(
        f"|{os.path.realpath(field_path)}|{field_stat.st_size}|"
        f"{field_stat.st_mtime_ns}".encode()
    )
    return Path(cache_dir) / f"{digest.hexdigest()[:24]}.nii.gz"


#: Millimetres added around the mask's MNI bounding box before asking the field
#: which subject voxels can land in it (trilinear interpolation of a smooth
#: field cannot stray further than this between neighbouring field voxels).
_BOX_PAD_MM = 3.0
#: Target voxels added around the block, and the growth step when a positive
#: voxel touches the block's face.
_BLOCK_MARGIN = 2
_BLOCK_GROW = 16


def warp_mni_to_subject(image, m2m: str):
    """*image* (MNI space) on the subject's grid, as SimNIBS's ``mni_mask_to_sub``.

    Same target grid (``T1_upsampled`` if present, else the reference T1), same
    deformation field, same arithmetic, restricted to the block of target voxels
    the mask can land in.  Values are copied by nearest neighbour, so a binary
    mask stays binary and a label volume keeps its labels; the returned data has
    the input's dtype.
    """
    import nibabel as nib
    import numpy as np

    target_path, field_path = _subject_files(m2m)
    target = nib.load(target_path)
    tshape = tuple(int(n) for n in target.shape[:3])
    taff = np.asarray(target.affine, dtype=np.float64)
    data = np.squeeze(np.asanyarray(image.dataobj))
    if data.ndim != 3:
        raise ValueError("Mask must be a three-dimensional NIfTI volume")
    im_affine = np.asarray(image.affine, dtype=np.float64)
    field, df_affine = _deformation_field(field_path)

    out = np.zeros(tshape, dtype=data.dtype)
    nonzero = np.argwhere(data != 0)
    if not len(nonzero):
        return nib.Nifti1Image(out, taff)

    # MNI bounding box of the mask: voxel centres +- one voxel (nearest
    # neighbour rounds within half a voxel) +- a safety pad, in world mm.
    lo_v = nonzero.min(axis=0) - 1
    hi_v = nonzero.max(axis=0) + 1
    world = _corners_world(lo_v, hi_v, im_affine)
    wmin = world.min(axis=0) - _BOX_PAD_MM
    wmax = world.max(axis=0) + _BOX_PAD_MM
    if (wmin <= 0).all() and (wmax >= 0).all():
        # A field voxel that is (0, 0, 0) would sample the mask at the MNI
        # origin; SimNIBS turns such voxels outside the head into inf first.
        field = _boundary_fixed(field_path, field)

    inside = np.all((field >= wmin) & (field <= wmax), axis=3)
    if not inside.any():
        return nib.Nifti1Image(out, taff)
    fshape = np.asarray(field.shape[:3])
    f_lo = np.array(
        [int(np.flatnonzero(inside.any(axis=ax))[0]) for ax in ((1, 2), (0, 2), (0, 1))]
    )
    f_hi = np.array(
        [
            int(np.flatnonzero(inside.any(axis=ax))[-1])
            for ax in ((1, 2), (0, 2), (0, 1))
        ]
    )
    del inside
    same_grid = tshape == tuple(int(n) for n in fshape) and np.allclose(taff, df_affine)
    if same_grid:
        lo = np.maximum(f_lo - _BLOCK_MARGIN, 0)
        hi = np.minimum(f_hi + _BLOCK_MARGIN, fshape - 1)
    else:
        world = _corners_world(f_lo - 1, f_hi + 1, df_affine)
        tvox = nib.affines.apply_affine(np.linalg.inv(taff), world)
        lo = np.maximum(np.floor(tvox.min(axis=0)).astype(int) - _BLOCK_MARGIN, 0)
        hi = np.minimum(
            np.ceil(tvox.max(axis=0)).astype(int) + _BLOCK_MARGIN,
            np.asarray(tshape) - 1,
        )

    for _attempt in range(4):
        block, field = _warp_block(
            data, im_affine, field, field_path, df_affine, taff, lo, hi, same_grid
        )
        out[lo[0] : hi[0] + 1, lo[1] : hi[1] + 1, lo[2] : hi[2] + 1] = block
        grow_lo = np.array(
            [block[0].any(), block[:, 0].any(), block[:, :, 0].any()]
        ) & (lo > 0)
        grow_hi = np.array(
            [block[-1].any(), block[:, -1].any(), block[:, :, -1].any()]
        ) & (hi < np.asarray(tshape) - 1)
        if not (grow_lo.any() or grow_hi.any()):
            break
        lo = np.where(grow_lo, np.maximum(lo - _BLOCK_GROW, 0), lo)
        hi = np.where(grow_hi, np.minimum(hi + _BLOCK_GROW, np.asarray(tshape) - 1), hi)
    return nib.Nifti1Image(out, taff)


def _corners_world(lo, hi, affine):
    import itertools
    import nibabel as nib
    import numpy as np

    corners = np.array(list(itertools.product(*zip(lo, hi))), dtype=np.float64)
    return nib.affines.apply_affine(affine, corners)


def _boundary_fixed(field_path: str, field):
    """*field* with SimNIBS's ``_fix_boundary_zeros`` applied (once per load)."""
    from simnibs.utils.transformations import _fix_boundary_zeros

    hit = _FIELD_CACHE.get(field_path)
    if hit is not None and len(hit) > 3 and hit[3]:
        return hit[1]
    field = _fix_boundary_zeros(field)
    if hit is not None:
        _FIELD_CACHE[field_path] = (hit[0], field, hit[2], True)
    return field


def _warp_block(data, im_affine, field, field_path, df_affine, taff, lo, hi, same_grid):
    """SimNIBS's ``volumetric_nonlinear`` arithmetic on one block of the target."""
    import numpy as np
    import scipy.ndimage

    if same_grid:
        sub = field[lo[0] : hi[0] + 1, lo[1] : hi[1] + 1, lo[2] : hi[2] + 1]
        if np.all(sub == 0, axis=3).any():
            field = _boundary_fixed(field_path, field)
            sub = field[lo[0] : hi[0] + 1, lo[1] : hi[1] + 1, lo[2] : hi[2] + 1]
        voxvals = sub.reshape(-1, 3).T
    else:
        xyzvox = np.array(
            np.meshgrid(
                np.arange(lo[0], hi[0] + 1, dtype=float),
                np.arange(lo[1], hi[1] + 1, dtype=float),
                np.arange(lo[2], hi[2] + 1, dtype=float),
                indexing="ij",
            )
        ).reshape(3, -1)
        iM = np.linalg.inv(df_affine).dot(taff)
        t = iM[:3, :3].dot(xyzvox) + iM[:3, 3, None]
        fshape = np.asarray(field.shape[:3])
        f_lo = np.maximum(np.floor(t.min(axis=1)).astype(int), 0)
        f_hi = np.minimum(np.ceil(t.max(axis=1)).astype(int), fshape - 1)
        if (f_hi < f_lo).any():
            voxvals = np.full((3, t.shape[1]), np.inf, dtype=np.float32)
        else:
            sub = field[
                f_lo[0] : f_hi[0] + 1, f_lo[1] : f_hi[1] + 1, f_lo[2] : f_hi[2] + 1
            ]
            if np.all(sub == 0, axis=3).any():
                field = _boundary_fixed(field_path, field)
                sub = field[
                    f_lo[0] : f_hi[0] + 1, f_lo[1] : f_hi[1] + 1, f_lo[2] : f_hi[2] + 1
                ]
            # An integer shift of the coordinates is exact in floating point,
            # so the trilinear weights are the ones the full grid would use.
            tt = t - f_lo[:, None].astype(np.float64)
            voxvals = np.array(
                [
                    scipy.ndimage.map_coordinates(
                        sub[..., i],
                        tt,
                        output=np.float32,
                        order=1,
                        mode="constant",
                        cval=np.inf,
                    )
                    for i in range(3)
                ]
            )
    iM = np.linalg.inv(im_affine)
    coords = iM[:3, :3].dot(voxvals) + iM[:3, 3, None]
    coords[np.isnan(coords)] = np.inf
    values = scipy.ndimage.map_coordinates(
        data, coords, output=data.dtype, order=0, mode="constant", cval=0
    )
    shape = tuple(int(n) for n in (hi - lo + 1))
    return values.reshape(shape), field


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
    from tit.atlas.manifest import not_shipped_message

    for field, path in paths:
        retired = not_shipped_message(path)
        if retired:
            raise ValueError(f"{field}: {retired}")
        if not Path(path).is_file():
            raise ValueError(
                f"{field}: mask is not accessible in the container: {path}. "
                "Import it through the NIfTI mask picker, "
                "or use an existing path inside the container."
            )
