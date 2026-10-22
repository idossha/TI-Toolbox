"""SimNIBS warps a 3-vector volume with an inverse deformation and rotates it (2026-10-21).

Pins the path TI-Toolbox's removed ``patch_nan_to_num.py`` broke: under NumPy 2 its
``nan_to_num(np.gradient(...), copy=False)`` raised "Unable to avoid copy" for every
vector volume warped with an inverse field (``subject2mni``/``mni2subject`` of E or J,
``run_simnibs`` with ``map_to_MNI``), while scalar warps kept working.

The expected values are authored, not read back from SimNIBS: the deformation is the
mirror x -> -x, so the inverse field's Jacobian is diag(-1, 1, 1) and a constant vector
(1, 2, 3) must come out as (-1, 2, 3) with its length kept. A NaN in the input is the
case ``nifti_transform``'s own ``nan_to_num`` exists for.

Run with real SimNIBS (the toolbox container)::

    simnibs_python -m pytest tests/numerical/test_simnibs_vector_warp.py -q
"""

import importlib
import sys

import numpy as np
import pytest


@pytest.fixture(scope="module", autouse=True)
def real_simnibs():
    """Swap the host conftest's ``simnibs`` mock for the real package, if any."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "simnibs"
    }
    try:
        importlib.import_module("simnibs.utils.transformations")
    except Exception:
        sys.modules.update(saved)
        pytest.skip("real SimNIBS is unavailable; run in the toolbox container")
    yield
    for k in list(sys.modules):
        if k.split(".")[0] == "simnibs":
            del sys.modules[k]
    sys.modules.update(saved)


def test_vector_volume_is_mirrored_through_the_inverse_warp(tmp_path):
    import nibabel as nib
    from simnibs.utils.transformations import nifti_transform

    affine = np.eye(4)
    affine[:3, 3] = -6.0  # voxel (6, 6, 6) is the world origin
    ijk = np.moveaxis(np.indices((13, 13, 13)).astype(np.float64), 0, -1)
    mirror = nib.affines.apply_affine(affine, ijk) * [-1.0, 1.0, 1.0]
    nib.save(nib.Nifti1Image(mirror, affine), tmp_path / "warp.nii")
    nib.save(nib.Nifti1Image(np.zeros((13, 13, 13)), affine), tmp_path / "ref.nii")

    vectors = np.zeros((13, 13, 13, 3))
    vectors[...] = [1.0, 2.0, 3.0]
    vectors[0, 0, 0, 0] = np.nan  # a corner voxel, outside the asserted interior

    img = nifti_transform(
        (vectors, affine),
        str(tmp_path / "warp.nii"),
        str(tmp_path / "ref.nii"),
        inverse_warp=str(tmp_path / "warp.nii"),
    )

    out = np.asanyarray(img.dataobj)[2:-2, 2:-2, 2:-2]
    np.testing.assert_allclose(out, np.broadcast_to([-1.0, 2.0, 3.0], out.shape))
