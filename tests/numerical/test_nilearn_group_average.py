"""The Nilearn Visuals runner averages each pair's own field file, TI or mTI, on one grid.

Pins, 2026-10-21: ``tit.plotting.nilearn.__main__._average_fields`` returns the voxelwise
mean of the files :func:`tit.plotting.nilearn.visualizer.field_nifti` names -- a two-pair
run's ``TI_max`` and an mTI run's ``mTI_max`` side by side -- and refuses a pair on a
different grid, naming it. The expected mean is ``numpy.mean`` over the arrays this test
writes, read back by nibabel; nothing is retyped from a run.

Real nibabel (the host suite mocks it); runs in the container's numerical leg:
``docker exec -w /ti-toolbox <c> simnibs_python -m pytest tests/numerical/test_nilearn_group_average.py -q``
"""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.unit

AFFINE = np.diag([2.0, 2.0, 2.0, 1.0])
AFFINE[:3, 3] = [-90.0, -126.0, -72.0]


def _write(path, data, affine=AFFINE):
    import nibabel as nib

    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(data, affine), str(path))


@pytest.fixture
def runner(init_pm):
    # Reload so the module's `nib` is the real nibabel this directory swaps in.
    return importlib.reload(importlib.import_module("tit.plotting.nilearn.__main__"))


def _pair(sid, sim):
    from tit.plotting.nilearn.config import NilearnSubjectSimulation

    return NilearnSubjectSimulation(sid, sim)


def test_a_ti_run_and_an_mti_run_average_voxelwise(init_pm, runner):
    rng = np.random.default_rng(20261021)
    ti = rng.random((5, 6, 7))
    mti = rng.random((5, 6, 7))

    ti_sim = Path(init_pm.simulation("001", "Insula"))
    _write(ti_sim / "TI/niftis/grey_Insula_TI_MNI_MNI_TI_max.nii.gz", ti)
    mti_sim = Path(init_pm.simulation("001", "Deep"))
    (mti_sim / "mTI" / "mesh").mkdir(parents=True)
    _write(mti_sim / "mTI/niftis/grey_Deep_mTI_MNI_MNI_mTI_max.nii.gz", mti)

    img = runner._average_fields([_pair("001", "Insula"), _pair("001", "Deep")])

    np.testing.assert_allclose(img.get_fdata(), np.mean([ti, mti], axis=0), rtol=1e-6)
    np.testing.assert_allclose(img.affine, AFFINE)


def test_a_pair_on_another_grid_is_refused_by_name(init_pm, runner):
    shifted = AFFINE.copy()
    shifted[:3, 3] += [0.0, 4.0, 0.0]
    for sim, affine in (("A", AFFINE), ("B", shifted)):
        _write(
            Path(init_pm.simulation("001", sim))
            / f"TI/niftis/grey_{sim}_TI_MNI_MNI_TI_max.nii.gz",
            np.ones((5, 6, 7)),
            affine,
        )
    with pytest.raises(ValueError, match="grey_B_TI_MNI_MNI_TI_max"):
        runner._average_fields([_pair("001", "A"), _pair("001", "B")])


def test_a_missing_file_names_the_pair_and_the_fix(init_pm, runner):
    with pytest.raises(FileNotFoundError, match="sub-001 / Gone.*MNI NIfTI"):
        runner._average_fields([_pair("001", "Gone")])
