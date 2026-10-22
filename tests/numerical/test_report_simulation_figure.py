"""The simulation report's envelope figure with real nibabel, matplotlib and Pillow.

Pins (2026-10-22, package p03):

* through real reorientation of a non-RAS grid (PSR, as ernie's m2m grid is), the three panels pass
  through the grey-matter hot spot that holds the peak: their labels give the world coordinate of
  the blob centre placed by hand, not of white matter above the colour scale or of a second hot spot;
* every pixel of the composed image is finite and in [0, 1] for an ordinary envelope, a uniform one
  (median = 99.9th percentile divided zero by zero) and a constant T1 (zero contrast divided zero by
  zero, which turned the whole figure NaN);
* the hot spot is coloured at the top of the scale: some pixel is the inferno top colour at the
  overlay's 0.85 opacity over a grey value in [0, 1];
* the WebP is 2 px per voxel of the composed image.

Every expected number is placed by hand: the grid's affine maps voxel (i, j, k) to world
(k - 20, 30 - i, j - 10) mm, so the hot spot at voxel (12, 15, 30) is world (10, 18, 5).
The host suite (``tests/test_report_simulation_centre.py``) checks the centre rule on RAS grids
with nibabel and matplotlib stubbed.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np

SHAPE = (40, 30, 50)  # i: posterior, j: superior, k: right
AFFINE = np.array([[0.0, 0, 1, -20], [-1.0, 0, 0, 30], [0.0, 1, 0, -10], [0, 0, 0, 1]])
LABELS = ["axial z = +5 mm", "coronal y = +18 mm", "sagittal x = +10 mm"]
ALPHA = 0.85  # tit.plotting.slices.overlay's default opacity


def _sim(tmp_path: Path, grey, white, t1) -> tuple[dict, Path]:
    import nibabel as nib

    d = tmp_path / "Simulations" / "M"
    (d / "documentation").mkdir(parents=True)
    (d / "TI" / "niftis").mkdir(parents=True)
    (d / "documentation" / "config.json").write_text(
        json.dumps({"simulation_name": "M", "simulation_mode": "TI"})
    )
    for name, data in (
        ("TI/niftis/grey_M_TI_subject_TI_max.nii.gz", grey),
        ("TI/niftis/white_M_TI_subject_TI_max.nii.gz", white),
        ("T1.nii.gz", t1),
    ):
        nib.save(nib.Nifti1Image(np.asarray(data, np.float32), AFFINE), str(d / name))
    from tit.reporting.generators import simulation as sim

    return sim.collect(d), d / "T1.nii.gz"


def _volumes():
    grey = np.zeros(SHAPE, np.float32)
    grey[:, 5:25, :] = (
        0.1  # 40 * 20 * 50 = 40 000 grey voxels: the top 0.1 % is 40 voxels
    )
    grey[10:15, 13:18, 28:33] = 1.0  # 125 voxels around (12, 15, 30): the hot spot
    grey[28:31, 14:17, 8:11] = 0.5  # a weaker spot elsewhere
    white = np.zeros(SHAPE, np.float32)
    white[25:35, 2:6, 35:45] = 2.0  # above the colour scale, far from the hot spot
    t1 = np.broadcast_to(np.linspace(10, 200, SHAPE[2], dtype=np.float32), SHAPE).copy()
    return grey, white, t1


def _draw(monkeypatch, rec, t1_path):
    """field_images with the composed image kept (the real render still runs)."""
    from tit.plotting import slices
    from tit.reporting.generators import simulation as sim

    seen = []
    real = slices.render

    def render(img, contours=(), **kw):
        seen.append(np.array(img))
        return real(img, contours, **kw)

    monkeypatch.setattr(slices, "render", render)
    out = sim.field_images(rec, t1_path)
    assert out is not None and len(seen) == 1
    return out, seen[0]


def _has_top_colour(img: np.ndarray) -> bool:
    import matplotlib

    top = ALPHA * np.array(matplotlib.colormaps["inferno"](1.0)[:3])
    near = np.all((img >= top - 1e-6) & (img <= top + (1 - ALPHA) + 1e-6), axis=-1)
    return bool(near.any())


def _check_pixels(out: dict, img: np.ndarray) -> None:
    from PIL import Image

    assert np.isfinite(img).all()
    assert img.min() >= 0 and img.max() <= 1
    h, w = out["shape"][:2]
    width, height = Image.open(io.BytesIO(out["image"])).size
    assert (
        abs(width - 2 * w) <= 1 and abs(height - 2 * h) <= 1
    )  # figure inches round to pixels


def test_panels_cross_the_grey_hot_spot_through_real_reorientation(
    tmp_path, monkeypatch
):
    rec, t1 = _sim(tmp_path, *_volumes())
    out, img = _draw(monkeypatch, rec, t1)
    assert out["labels"] == LABELS
    _check_pixels(out, img)
    assert _has_top_colour(img)


def test_a_uniform_envelope_is_drawn_at_the_top_of_the_scale(tmp_path, monkeypatch):
    grey, white, t1 = _volumes()
    grey[grey > 0] = 0.4
    rec, t1_path = _sim(tmp_path, grey, np.zeros(SHAPE), t1)
    assert rec["envelope"]["median"] == rec["envelope"]["p99_9"]
    out, img = _draw(monkeypatch, rec, t1_path)
    _check_pixels(out, img)
    assert _has_top_colour(img)


def test_a_constant_t1_still_gives_a_finite_coloured_figure(tmp_path, monkeypatch):
    grey, white, _ = _volumes()
    rec, t1_path = _sim(tmp_path, grey, white, np.full(SHAPE, 50.0))
    out, img = _draw(monkeypatch, rec, t1_path)
    assert out["labels"] == LABELS
    _check_pixels(out, img)
    assert _has_top_colour(img)


def test_a_single_frame_4d_envelope_draws_like_3d(tmp_path, monkeypatch):
    grey, white, t1 = _volumes()
    rec, t1_path = _sim(tmp_path, grey[..., None], white[..., None], t1)
    out, img = _draw(monkeypatch, rec, t1_path)
    assert out["labels"] == LABELS
    _check_pixels(out, img)
