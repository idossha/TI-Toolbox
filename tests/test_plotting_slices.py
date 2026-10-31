"""tit.plotting.slices: one orientation convention for every report panel.

Pins (2026-09-28, ARCHITECTURE.md §14): on a RAS voxel grid, panels are neurological —
subject left on image left, anterior up in axial panels, superior up in coronal and sagittal
panels, anterior on the right in sagittal panels; slice choice never lands on a (nearly) empty
slice; mosaics centre tiles in equal cells. Panels are never cropped (2026-10-31): every panel
is the whole slice, and every mosaic cell frames it in ``MARGIN`` black voxels, so a head that fills
its grid still has a margin. Expected positions come from where the markers were planted, not from
the code under test. Reordering LAS / PSR grids to RAS (``canonical``) needs
the real nibabel and is pinned in tests/numerical/test_dti_advisories.py.
"""

import numpy as np
import pytest

from tit.plotting import slices as sl

SHAPE = (20, 30, 40)  # x (L->R), y (P->A), z (I->S): asymmetric so an axis mix-up is loud


def _marker(x, y, z) -> np.ndarray:
    vol = np.zeros(SHAPE)
    vol[x, y, z] = 1
    return vol


def _where(panel: np.ndarray) -> tuple[int, int]:
    r, c = np.argwhere(panel)[0]
    return int(r), int(c)


def test_axial_left_on_left_anterior_up():
    panel = sl.oriented(_marker(2, 27, 10), 2, 10)
    assert panel.shape == (30, 20)
    row, col = _where(panel)
    assert col < 10 and row < 15  # left voxel -> left half; anterior voxel -> top half


def test_coronal_left_on_left_superior_up():
    panel = sl.oriented(_marker(2, 5, 36), 1, 5)
    assert panel.shape == (40, 20)
    row, col = _where(panel)
    assert col < 10 and row < 20


def test_sagittal_anterior_right_superior_up():
    panel = sl.oriented(_marker(4, 27, 36), 0, 4)
    assert panel.shape == (40, 30)
    row, col = _where(panel)
    assert col > 15 and row < 20


def test_trailing_channels_kept():
    rgb = np.zeros(SHAPE + (3,))
    assert sl.oriented(rgb, 2, 3).shape == (30, 20, 3)


def test_pick_slice_skips_empty_slices_and_uses_the_coordinate():
    mask = np.zeros(SHAPE, bool)
    mask[:, :, 5:35] = True
    mask[:, :, 20] = False  # the slice nearest the target is empty: never chosen
    z_coord = np.broadcast_to(np.arange(40, dtype=float) - 20, SHAPE)  # z index 20 is coordinate 0
    assert sl.pick_slice(2, 0.0, z_coord, mask) in (19, 21)
    assert sl.pick_slice(2, 100.0, z_coord, mask) == 34


def test_pick_slice_raises_when_nothing_qualifies():
    with pytest.raises(ValueError):
        sl.pick_slice(2, 0.0, np.zeros(SHAPE), np.zeros(SHAPE, bool))


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_a_head_filling_its_grid_is_whole_and_framed_in_every_orientation(axis):
    # Nonzero to the grid's faces: the bounding box is the whole volume, as for a head at the edge.
    head = np.ones(SHAPE)
    i = SHAPE[axis] // 2
    out, (h, w) = sl.mosaic([sl.oriented(head, axis, i)], cols=1)
    face = [s for a, s in enumerate(SHAPE) if a != axis]  # the slice's two extents
    m = sl.MARGIN
    assert m > 0 and out.shape == (h, w)
    assert out.sum() == np.prod(face)  # every voxel of the slice is drawn
    inner = out[m : h - m, m : w - m]
    assert sorted(inner.shape) == sorted(face) and inner.all()
    ring = out.copy()
    ring[m : h - m, m : w - m] = 0
    assert not ring.any()  # a black margin on all four sides


def test_mosaic_centres_tiles():
    tiles = [np.ones((4, 6)), np.ones((2, 2))]
    out, tile = sl.mosaic(tiles, cols=2, gap=1, margin=0)
    assert tile == (4, 6) and out.shape == (4, 13)
    assert out[1:3, 9:11].all() and not out[0, 7:13].any()
