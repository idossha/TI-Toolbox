"""tit.plotting.slices: one orientation convention for every report panel.

Pins (2026-09-28, ARCHITECTURE.md §14): on a RAS voxel grid, panels are neurological —
subject left on image left, anterior up in axial panels, superior up in coronal and sagittal
panels, anterior on the right in sagittal panels; slice choice never lands on a (nearly) empty
slice; mosaics centre tiles in equal cells. Expected positions come from where the markers were
planted, not from the code under test. Reordering LAS / PSR grids to RAS (``canonical``) needs
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


def test_box_crops_before_orienting():
    box = [(1, 11), (5, 25), (0, 40)]
    panel = sl.oriented(_marker(2, 20, 10), 2, 10, box)
    assert panel.shape == (20, 10)
    assert _where(panel) == (25 - 1 - 20, 2 - 1)


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


def test_brain_box_margin_and_cord_cut():
    brain = np.zeros(SHAPE, bool)
    brain[5:15, 10:20, 2:30] = True
    z_coord = np.broadcast_to(np.arange(40, dtype=float) * 4 - 60, SHAPE)  # z index 1 is -56, 0 is -60
    box = sl.brain_box(brain, z_coord, z_min=-50, margin=(1, 2))
    assert box[0] == (4, 16) and box[1] == (9, 21)
    assert box[2][0] == 3 - 1  # indices with z <= -50 (0..2) are cut before the margin


def test_mosaic_centres_tiles():
    tiles = [np.ones((4, 6)), np.ones((2, 2))]
    out, tile = sl.mosaic(tiles, cols=2, gap=1)
    assert tile == (4, 6) and out.shape == (4, 13)
    assert out[1:3, 9:11].all() and not out[0, 7:13].any()
