"""A network mask with real DIPY, nibabel and the TRX reader (image numerical leg).

Pins (2026-11-05), on a toy T1 grid and streamlines written here:

* :func:`write_mask_with_sidecar`: the voxels of a straight bundle along x are exactly the ones its
  points fall in (the expectation is ``np.rint`` of the known coordinates through the known affine,
  not DIPY); ``min_count`` drops a voxel one streamline crosses when two are required; the volume is
  voxels times the affine's voxel size; an empty result is refused and leaves nothing behind.

Needs DIPY, so it skips on a host without it.
Reproduce: ``docker run ... simnibs_python -m pytest tests/numerical/test_tract_mask.py -q``.
"""

import json

import numpy as np
import pytest

pytest.importorskip("dipy")


class _Pm:
    def __init__(self, root):
        self.root = root

    def masks(self, sid):
        return str(self.root / "masks")

    def t1(self, sid):
        return str(self.root / "T1.nii.gz")

    def tractography(self, sid):
        return str(self.root / "tractography")


def _bundle(y):
    return np.column_stack(
        [np.arange(2.0, 8.0, 0.5), np.full(12, float(y)), np.full(12, 5.0)]
    ).astype(np.float32)


@pytest.fixture
def pm(tmp_path):
    import nibabel as nib

    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    nib.save(
        nib.Nifti1Image(np.zeros((8, 8, 8), np.int16), affine), tmp_path / "T1.nii.gz"
    )
    (tmp_path / "tractography").mkdir()
    return _Pm(tmp_path)


def _read(path):
    import nibabel as nib

    return np.asanyarray(nib.load(path).dataobj)


def test_mask_voxels_are_those_the_points_fall_in(pm):
    from tit.tract.config import Selection
    from tit.tract.target import write_mask_with_sidecar

    sel = Selection(name="net", kind="edges", pairs=[["a", "b"]])
    record = write_mask_with_sidecar(pm, "x", sel, [_bundle(4.0), _bundle(8.0)], 1)
    mask = _read(record["path"])
    expected = np.zeros(mask.shape, bool)
    for line in (_bundle(4.0), _bundle(8.0)):
        i, j, k = np.rint(line / 2.0).astype(int).T
        expected[i, j, k] = True
    assert (mask > 0).tolist() == expected.tolist()
    assert record["n_voxels"] == expected.sum()
    assert record["volume_mm3"] == pytest.approx(expected.sum() * 8.0)
    assert record["n_streamlines"] == 2
    sidecar = json.loads((pm.root / "masks" / "tract-net.json").read_text())
    assert sidecar["selection"]["pairs"] == [["a", "b"]]
    assert sidecar["fingerprint"]


def test_min_count_drops_a_voxel_too_few_streamlines_cross(pm):
    from tit.tract.config import Selection
    from tit.tract.target import write_mask_with_sidecar

    sel = Selection(name="net", kind="edges", pairs=[["a", "b"]])
    record = write_mask_with_sidecar(
        pm, "x", sel, [_bundle(4.0), _bundle(4.0), _bundle(8.0)], 2
    )
    mask = _read(record["path"])
    assert mask[:, 2, :].sum() > 0 and mask[:, 4, :].sum() == 0


def test_an_empty_mask_is_refused_and_writes_nothing(pm):
    from tit.tract.config import Selection
    from tit.tract.target import write_mask_with_sidecar

    sel = Selection(name="net", kind="edges", pairs=[["a", "b"]])
    with pytest.raises(ValueError, match="No voxel"):
        write_mask_with_sidecar(pm, "x", sel, [_bundle(4.0)], 5)
    assert list((pm.root / "masks").glob("*")) == []
