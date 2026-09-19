"""The block-restricted MNI -> subject warp gives SimNIBS's voxels, once per label.

Run with real nibabel/scipy/SimNIBS:
``simnibs_python -m pytest tests/numerical/test_mni_warp.py``.  The reference is
SimNIBS's own ``mni_mask_to_sub`` on the same synthetic head model, not a
re-statement of the implementation; the deformation field is a smooth
non-linear map with a non-trivial affine so the resampling branch, the
integer-shift of the trilinear sampling and the block growth all run.
"""

import gzip
import importlib
import sys

import numpy as np
import pytest

pytest.importorskip("scipy.ndimage")


@pytest.fixture(scope="module", autouse=True)
def real_simnibs():
    """Swap the host conftest's ``simnibs`` mock for the real package, if any."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "simnibs"
    }
    try:
        importlib.import_module("simnibs.utils.region_of_interest")
    except Exception:
        sys.modules.update(saved)
        pytest.skip("real SimNIBS is unavailable; run in the toolbox container")
    yield
    for k in list(sys.modules):
        if k.split(".")[0] == "simnibs":
            del sys.modules[k]
    sys.modules.update(saved)


def _save(image, path):
    import nibabel as nib

    plain = str(path).removesuffix(".gz")
    nib.save(image, plain)
    if str(path).endswith(".gz"):
        with open(plain, "rb") as source, gzip.open(path, "wb") as target:
            target.write(source.read())


def _head_model(root, *, upsampled=True, exterior_zeros=False):
    """A synthetic ``m2m_s`` with a smooth non-linear conform->MNI field."""
    import nibabel as nib

    m2m = root / "m2m_s"
    (m2m / "toMNI").mkdir(parents=True)
    (m2m / "label_prep").mkdir()
    fshape = (12, 14, 16)
    faff = np.array(
        [
            [0.9, 0.0, 0.0, -5.0],
            [0.0, 1.1, 0.0, -7.0],
            [0.0, 0.0, 1.0, -8.0],
            [0, 0, 0, 1],
        ]
    )
    ijk = np.moveaxis(np.indices(fshape).astype(np.float64), 0, -1)
    world = nib.affines.apply_affine(faff, ijk)
    field = world + 0.6 * np.sin(world / 3.0)[..., ::-1]  # smooth, not affine
    if exterior_zeros:
        field[0, :, :, :] = 0.0  # a slab of (0,0,0) at one face, as charm leaves
    _save(
        nib.Nifti1Image(field.astype(np.float32), faff),
        m2m / "toMNI" / "Conform2MNI_nonl.nii.gz",
    )
    _save(nib.Nifti1Image(np.zeros(fshape, dtype=np.float32), faff), m2m / "T1.nii.gz")
    if upsampled:
        taff = faff.copy()
        taff[:3, :3] /= 2.0
        taff[:3, 3] += np.array([0.1, -0.2, 0.3])
        tshape = tuple(2 * n for n in fshape)
        _save(
            nib.Nifti1Image(np.zeros(tshape, dtype=np.float32), taff),
            m2m / "label_prep" / "T1_upsampled.nii.gz",
        )
    return m2m


def _mni_image(kind="blob"):
    import nibabel as nib

    shape = (18, 20, 22)
    affine = np.array(
        [
            [1.0, 0.0, 0.0, -6.0],
            [0.0, 1.0, 0.0, -8.0],
            [0.0, 0.0, 1.0, -9.0],
            [0, 0, 0, 1],
        ]
    )
    data = np.zeros(shape, dtype=np.uint8)
    if kind == "blob":
        data[5:9, 6:11, 7:12] = 1
    elif kind == "labels":
        data[3:8, 4:9, 5:10] = 3
        data[9:14, 10:15, 11:16] = 7
        data[12, 3, 4] = 9  # a detached voxel
    elif kind == "origin":  # contains the MNI origin (voxel (6, 8, 9))
        data[4:9, 6:11, 7:12] = 1
    return nib.Nifti1Image(data, affine)


def _reference(image, m2m):
    import warnings

    from simnibs.utils.file_finder import SubjectFiles
    from simnibs.utils.region_of_interest import mni_mask_to_sub

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return mni_mask_to_sub(image, SubjectFiles(subpath=str(m2m)))


@pytest.mark.parametrize(
    "kind,upsampled,exterior_zeros",
    [
        ("blob", True, False),
        ("blob", False, False),  # target grid is the field's own grid
        ("labels", True, False),  # a label volume keeps its labels
        ("origin", True, True),  # mask holds the MNI origin; boundary zeros
        ("blob", True, True),
    ],
)
def test_block_warp_matches_simnibs_voxel_for_voxel(
    tmp_path, kind, upsampled, exterior_zeros
):
    from tit.opt.masks import warp_mni_to_subject

    m2m = _head_model(tmp_path, upsampled=upsampled, exterior_zeros=exterior_zeros)
    image = _mni_image(kind)
    expected = _reference(image, m2m)
    got = warp_mni_to_subject(image, str(m2m))
    a = np.asarray(expected.dataobj)
    b = np.asarray(got.dataobj)
    assert a.shape == b.shape
    np.testing.assert_allclose(got.affine, expected.affine)
    assert (a != 0).sum() > 0, "the synthetic case must land inside the subject"
    assert np.array_equal(a, b), f"{int((a != b).sum())} voxels differ"


def test_prepare_mask_warps_once_then_serves_the_cache(tmp_path, monkeypatch):
    import nibabel as nib

    from tit.opt import masks

    m2m = _head_model(tmp_path)
    source = tmp_path / "mni.nii"
    nib.save(_mni_image("blob"), str(source))
    cache = tmp_path / "cache"
    first = masks.prepare_mask(
        str(source),
        "mni",
        str(m2m),
        str(tmp_path / "run-a"),
        binary=True,
        cache_dir=str(cache),
    )
    assert list(cache.glob("*.nii.gz")), "the warped mask was not cached"

    def _no_field(path):
        raise AssertionError("the deformation field was loaded again")

    monkeypatch.setattr(masks, "_deformation_field", _no_field)
    second = masks.prepare_mask(
        str(source),
        "mni",
        str(m2m),
        str(tmp_path / "run-b"),
        binary=True,
        cache_dir=str(cache),
    )
    assert second.startswith(str(tmp_path / "run-b"))
    assert np.array_equal(
        np.asarray(nib.load(first).dataobj), np.asarray(nib.load(second).dataobj)
    )
    expected = np.asarray(_reference(_mni_image("blob"), m2m).dataobj)
    assert np.array_equal(np.asarray(nib.load(second).dataobj) > 0, expected > 0)


def test_keep_deformation_field_decodes_the_field_once(tmp_path, monkeypatch):
    from tit.opt import masks

    m2m = _head_model(tmp_path)
    loads = []
    import nibabel as nib

    original_load = nib.load

    def counting_load(path, *a, **k):
        if "Conform2MNI" in str(path):
            loads.append(path)
        return original_load(path, *a, **k)

    monkeypatch.setattr(nib, "load", counting_load)
    with masks.keep_deformation_field():
        masks.warp_mni_to_subject(_mni_image("blob"), str(m2m))
        masks.warp_mni_to_subject(_mni_image("labels"), str(m2m))
    assert len(loads) == 1
    masks.warp_mni_to_subject(_mni_image("blob"), str(m2m))
    assert len(loads) == 2  # released on exit
