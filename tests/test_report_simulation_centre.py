"""The simulation report's envelope figure is centred on the grey-matter hot spot it names.

Pins (2026-10-22, package p03):

* ``hotspot_centre`` picks a voxel inside the grey-matter hot spot that holds the peak: the
  face-connected grey voxels at or above the 99.9th percentile that contain the grey maximum, and of
  those the one nearest their centroid. So the field at the centre is at least the colouring top
  (``hi``) and the slices cross the hot spot the caption names.
* Before, the centre was the mean position of every grey *or white* voxel at or above ``hi``. On
  Dataset 000 it lay 9-17 voxels from any hot voxel on 4 of 6 simulations, and for sub-ernie
  AF3_PO10_and_AF4_Oz the field there (0.160 V/m) was below even the colouring floor (0.169 V/m).
  With two hot spots it fell between them; white matter above ``hi`` pulled it away.
* ``field_images`` labels its three panels with the centre's world coordinate, so the labels show
  where the slices are.

Fixtures are hand-built volumes on a RAS grid; every expected voxel is the blob centre placed by
hand. Real nibabel reorientation and real pixels are checked in
``tests/numerical/test_report_simulation_figure.py``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tests.test_report_simulation_modes import NET, write_run
from tit.reporting.generators import simulation as sim
from tit.sim.config import Montage, MontageMode

SHAPE = (60, 30, 30)
#: RAS grid, 1 mm voxels, voxel (30, 15, 15) at the origin: world = voxel - (30, 15, 15).
AFFINE = np.array([[1.0, 0, 0, -30], [0, 1.0, 0, -15], [0, 0, 1.0, -15], [0, 0, 0, 1]])


def cube(
    vol: np.ndarray, centre: tuple[int, int, int], half: int, value: float
) -> None:
    i, j, k = centre
    vol[i - half : i + half + 1, j - half : j + half + 1, k - half : k + half + 1] = (
        value
    )


def cortex() -> np.ndarray:
    """A grey-matter slab at 0.1 V/m: 60 x 30 x 20 = 36 000 voxels, so the top 0.1 % is 36 voxels."""
    g = np.zeros(SHAPE, np.float32)
    g[:, :, 5:25] = 0.1
    return g


# ── the centre rule on its own ───────────────────────────────────────────


def test_two_hot_spots_centre_on_the_one_holding_the_peak():
    g = cortex()
    cube(g, (10, 15, 15), 2, 1.0)  # the peak
    cube(g, (50, 15, 15), 2, 0.9)  # a second hot spot, also above hi
    centre = sim.hotspot_centre(g, hi=0.85)
    assert centre == (
        10,
        15,
        15,
    )  # the old all-hot-voxel mean was (30, 15, 15), between them
    assert g[centre] >= 0.85


def test_a_single_hot_spot_centres_on_its_middle_voxel():
    g = cortex()
    cube(g, (22, 9, 17), 1, 0.8)
    assert sim.hotspot_centre(g, hi=0.5) == (22, 9, 17)


def test_the_centre_is_a_hot_voxel_even_when_the_hot_spot_is_a_ring():
    # A square ring in one axial plane: its centroid (20, 15, 15) is the cold hole in the middle.
    g = cortex()
    g[16:25, 11:20, 15] = 0.9
    g[17:24, 12:19, 15] = 0.1
    centre = sim.hotspot_centre(g, hi=0.5)
    assert g[centre] >= 0.5
    # the ring voxels nearest the hole's centre are the four edge midpoints, 4 voxels away
    assert centre in {(16, 15, 15), (24, 15, 15), (20, 11, 15), (20, 19, 15)}


def test_nan_voxels_are_neither_peak_nor_hot():
    g = cortex()
    g[0, 0, 5] = np.nan
    cube(g, (40, 20, 12), 1, 0.7)
    assert sim.hotspot_centre(g, hi=0.6) == (40, 20, 12)


# ── the figure ───────────────────────────────────────────────────────────


@pytest.fixture
def drawn(monkeypatch):
    """The slice helpers that need nibabel/matplotlib (mocked on the host) replaced by recorders:
    the volumes here are already RAS, so ``canonical`` is the identity. Returns what ``overlay``
    was given, per panel."""
    from tit.plotting import slices

    calls = []

    def overlay(grey, field, lo, hi, *a, **k):
        calls.append(SimpleNamespace(grey=grey, field=field, lo=lo, hi=hi))
        return np.repeat(np.asarray(grey, float)[..., None], 3, axis=-1)

    monkeypatch.setattr(
        slices, "canonical", lambda data, affine: (np.asarray(data), np.asarray(affine))
    )
    monkeypatch.setattr(slices, "overlay", overlay)
    monkeypatch.setattr(slices, "render", lambda img, contours=(), **k: b"webp")
    monkeypatch.setattr(slices, "colour_stops", lambda *a, **k: ["#000", "#fff"])
    return calls


def t1_gradient() -> np.ndarray:
    return np.broadcast_to(
        np.arange(SHAPE[0], dtype=np.float32)[:, None, None], SHAPE
    ).copy()


def figure(tmp_path: Path, grey, white=None, t1=None, affine=AFFINE):
    """``collect`` then ``field_images`` on a simulation folder holding these subject volumes."""
    montage = Montage(
        name="M",
        mode=MontageMode.NET,
        electrode_pairs=NET,
        eeg_net="EEG10-10_UI_Jurak_2007.csv",
    )
    d = write_run(tmp_path, montage)
    nd = d / "TI" / "niftis"
    nd.mkdir(parents=True)
    vols = {"grey_M_TI_subject_TI_max.nii.gz": grey}
    if white is not None:
        vols["white_M_TI_subject_TI_max.nii.gz"] = white
    for name in vols:
        (nd / name).touch()
    vols["T1.nii.gz"] = t1_gradient() if t1 is None else t1
    imgs = {n: SimpleNamespace(dataobj=v, affine=affine) for n, v in vols.items()}
    with patch("nibabel.load", side_effect=lambda p: imgs[Path(p).name]):
        rec = sim.collect(d)
        return rec, sim.field_images(rec, tmp_path / "T1.nii.gz")


def test_white_matter_above_hi_does_not_move_the_centre(tmp_path, drawn):
    g = cortex()
    cube(
        g, (10, 15, 15), 2, 1.0
    )  # 125 voxels: the grey top 0.1 % (36 voxels) is all 1.0
    w = np.zeros(SHAPE, np.float32)
    cube(
        w, (48, 6, 15), 4, 2.0
    )  # 729 white voxels at 2 V/m, far from the grey hot spot
    rec, out = figure(tmp_path, g, w)
    assert rec["envelope"]["p99_9"] == 1.0 and rec["envelope"][
        "median"
    ] == pytest.approx(0.1)
    # voxel (10, 15, 15) is world (-20, 0, 0)
    assert out["labels"] == [
        "axial z = +0 mm",
        "coronal y = +0 mm",
        "sagittal x = -20 mm",
    ]
    # the panels still colour white matter: the field drawn is max(grey, white)
    assert max(float(c.field.max()) for c in drawn) == 2.0


def test_labels_follow_the_affine(tmp_path, drawn):
    # 2 mm voxels with an offset: voxel (40, 20, 12) is world (2*40 - 7, 2*20 + 3, 2*12 - 50)
    g = cortex()
    cube(g, (40, 20, 12), 2, 0.9)
    affine = np.array([[2.0, 0, 0, -7], [0, 2.0, 0, 3], [0, 0, 2.0, -50], [0, 0, 0, 1]])
    _, out = figure(tmp_path, g, affine=affine)
    assert out["labels"] == [
        "axial z = -26 mm",
        "coronal y = +43 mm",
        "sagittal x = +73 mm",
    ]
