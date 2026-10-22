"""SimNIBS warps a 3-vector volume with an inverse deformation and rotates it (2026-10-21).

Pins the path TI-Toolbox's removed ``patch_nan_to_num.py`` broke: under NumPy 2 its
``nan_to_num(np.gradient(...), copy=False)`` raised "Unable to avoid copy" for every
vector volume warped with an inverse field (``subject2mni``/``mni2subject`` of E or J,
``run_simnibs`` with ``map_to_MNI``), while scalar warps kept working.

The expected values are authored, not read back from SimNIBS: the deformation is the
mirror x -> -x, so the inverse field's Jacobian is diag(-1, 1, 1) and a constant vector
(1, 2, 3) must come out as (-1, 2, 3) with its length kept. A NaN in the input is the
case ``nifti_transform``'s own ``nan_to_num`` exists for.

An image built before the patch was removed (idossha/ti-toolbox:v3.1.1 and older) still
carries it, so there the test is a strict expected failure, decided by reading the image's
own ``transformations.py`` (the patch rewrote ``nan_to_num(..., copy=None)`` to
``copy=False``), not by a version string: an old image is ``xfail``, an XPASS there is a
failure (the patch stopped mattering, or the check is wrong), and any image without the edit
-- every one built from this source -- runs it as an ordinary test.

Run with real SimNIBS (the toolbox container)::

    simnibs_python -m pytest tests/numerical/test_simnibs_vector_warp.py -q
"""

import importlib
import re
import sys
from pathlib import Path

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


#: The xfail reason on an image that still carries the patch; dev/check_junit.py allows exactly
#: this text on the numerical-image leg.
PATCHED_IMAGE = (
    "this image's SimNIBS carries the removed nan_to_num patch (copy=False in "
    "transformations.py); an image built from this source runs the test"
)


def _carries_the_nan_to_num_patch() -> bool:
    """Whether SimNIBS's ``transformations.py`` has resources/patches/patch_nan_to_num.py's edit.

    That script (deleted in 7403910d) replaced every ``copy=None`` in the file with
    ``copy=False``; SimNIBS 4.6's own file passes ``copy=None`` to ``nan_to_num``.
    """
    import simnibs.utils.transformations as transformations

    source = Path(transformations.__file__).read_text(encoding="utf-8")
    return re.search(r"nan_to_num\(.*copy=False", source) is not None


def test_vector_volume_is_mirrored_through_the_inverse_warp(tmp_path, request):
    if _carries_the_nan_to_num_patch():
        request.applymarker(
            pytest.mark.xfail(strict=True, raises=ValueError, reason=PATCHED_IMAGE)
        )
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
