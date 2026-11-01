"""Voxel tissue masks and ROI grids with real nibabel: the right voxels, or a refusal (2026-10-31).

What this pins
    1. ``Analyzer._voxel_tissue_mask`` for ``BOTH`` is the union of the analysed field's
       ``grey_`` and ``white_`` NIfTIs, and refuses (``FileNotFoundError``) when either is
       missing. It used to skip a missing one with a warning, so a "both" run whose white NIfTI
       was never written measured grey matter only (half the voxels here) under a GM+WM label.
    2. ``tit.roi_confirmation._on_grid`` resamples a volume whose shape equals the target's but
       whose affine does not. It compared shapes only, so a mask one voxel off in world space
       was used unmoved.

Where the numbers come from: authored volumes. A 10 x 10 x 10 identity grid; grey is the
slab i < 5 (500 voxels), white the slab i >= 5 (500), so the union is all 1000. For
``_on_grid`` the source is the target grid shifted +1 mm in x, so nearest-neighbour sampling
moves the single marked voxel from index 4 to index 5 -- read off the authored affines.

Needs only real numpy/nibabel (``host_numerical``); the host suite mocks nibabel.

Reproduce:
  host:      ``.venv/bin/python -m pytest tests/numerical/test_tissue_mask_and_grid_real.py -q -m host_numerical``
  container: ``simnibs_python -m pytest tests/numerical/test_tissue_mask_and_grid_real.py -q``
Deliberately elsewhere: that a "both" analysis asks for the grey and white NIfTIs
(``tests/test_analyzer_on_demand.py``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

SHAPE = (10, 10, 10)
WHOLE = "M1_TI_subject_TI_max.nii.gz"


def _save(path: Path, data: np.ndarray, affine=np.eye(4)) -> None:
    import nibabel as nib

    nib.save(nib.Nifti1Image(data.astype(np.float32), affine), str(path))


def _both_analyzer(folder: Path):
    from tit.analyzer.analyzer import Analyzer

    analyzer = object.__new__(Analyzer)
    analyzer.tissue_type = "BOTH"
    analyzer.field_path = folder / WHOLE
    _save(analyzer.field_path, np.ones(SHAPE))
    return analyzer


def _slab(lo: int, hi: int) -> np.ndarray:
    data = np.zeros(SHAPE)
    data[lo:hi] = 1.0
    return data


def test_both_is_the_union_of_grey_and_white(tmp_path: Path) -> None:
    analyzer = _both_analyzer(tmp_path)
    _save(tmp_path / f"grey_{WHOLE}", _slab(0, 5))
    _save(tmp_path / f"white_{WHOLE}", _slab(5, 10))
    assert int(analyzer._voxel_tissue_mask(SHAPE, np.eye(4)).sum()) == 1000


def test_both_without_its_white_nifti_is_refused_not_grey_only(tmp_path: Path) -> None:
    analyzer = _both_analyzer(tmp_path)
    _save(tmp_path / f"grey_{WHOLE}", _slab(0, 5))
    with pytest.raises(FileNotFoundError, match=f"white_{WHOLE}"):
        analyzer._voxel_tissue_mask(SHAPE, np.eye(4))


def test_on_grid_resamples_an_equal_shape_on_another_affine() -> None:
    import nibabel as nib

    from tit.roi_confirmation import _on_grid

    data = np.zeros(SHAPE, np.uint8)
    data[4, 4, 4] = 1
    shifted = np.eye(4)
    shifted[0, 3] = 1.0  # source voxel i sits at world x = i + 1
    got = _on_grid(nib.Nifti1Image(data, shifted), SHAPE, np.eye(4))
    # World x = 5 is target voxel 5.
    assert np.argwhere(got).tolist() == [[5, 4, 4]]
    # Same grid: returned as it is.
    same = _on_grid(nib.Nifti1Image(data, np.eye(4)), SHAPE, np.eye(4))
    assert np.argwhere(same).tolist() == [[4, 4, 4]]
