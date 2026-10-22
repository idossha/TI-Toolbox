"""Vector-field arrows point along the field, with the documented length and colours (2026-10-22).

What this pins, with real trimesh and scipy (the image):

* ``create_arrow`` in linear mode builds an arrow whose extent along the unit field direction d
  is ``length_scale * magnitude * vector_scale`` -- hand formula: the shaft is 0.8 L and the head
  0.2 L of ``L = length_scale * magnitude`` (the function's linear mode), all scaled by
  ``vector_scale``. A ``tail`` anchor puts the arrow's minimum projection onto d at the position,
  a ``head`` anchor its maximum. A zero direction points along +z. The anti-parallel direction
  -z must point down (the +z -> d rotation axis is degenerate there).
* ``write_ply_arrows`` declares ``uchar red, green, blue, alpha`` -- what Blender imports as the
  ``Col`` attribute (docs/wiki/blender.md, "Setting Color to the 'Col' Attribute") -- and writes
  arrows x per-arrow vertices, each vertex carrying its arrow's colour.
* ``_map_magnitude_to_colors_magscale``: the magnitudes AT the blue/green/red percentiles of the
  full set map to pure blue, green and red, and the hue never rises with magnitude.
* ``_filter_and_sample``: ``top_percent=10`` keeps the magnitudes >= the 90th percentile, a seed
  reproduces the sample, and asking for more than remain returns all of them.

Where the expected values come from: hand formulas above, ``numpy.percentile`` and
``colorsys`` (independent of the exporter), and the PLY bytes read back with ``trimesh.load``.

Run (the toolbox image):
    simnibs_python -m pytest tests/numerical/test_vector_export_geometry.py -q -p no:cacheprovider
"""

from __future__ import annotations

import colorsys
import importlib
import sys

import numpy as np
import pytest

_REAL = ("trimesh",)


@pytest.fixture(scope="module")
def vfe():
    """``tit.blender.vector_field_exporter`` bound to real trimesh and scipy.

    The host conftest mocks trimesh for the whole session and tests/numerical/conftest.py only
    swaps scipy/nibabel/matplotlib back, so trimesh is swapped here and the module reloaded.
    """
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] in _REAL
    }
    try:
        importlib.import_module("trimesh")
    except Exception:
        sys.modules.update(saved)
        print("skipping: real trimesh is not importable (run in the toolbox image)")
        pytest.skip("real trimesh is not importable; run in the toolbox image")
    import tit.blender.vector_field_exporter as module

    module = importlib.reload(module)
    yield module
    for k in [k for k in sys.modules if k.split(".")[0] in _REAL]:
        del sys.modules[k]
    sys.modules.update(saved)
    importlib.reload(module)


def _projections(arrow, direction):
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    return np.asarray(arrow.vertices) @ d


RNG = np.random.default_rng(20261022)
CASES = [
    (RNG.normal(size=3) * 10, RNG.normal(size=3), float(RNG.uniform(0.05, 2.0)))
    for _ in range(12)
]


@pytest.mark.parametrize("position, direction, magnitude", CASES)
@pytest.mark.parametrize("vector_scale, length_scale", [(1.0, 10.0), (0.4, 3.0)])
def test_arrow_extent_and_anchors_follow_the_field(
    vfe, position, direction, magnitude, vector_scale, length_scale
):
    common = dict(
        vector_scale=vector_scale,
        shaft_width=0.1,
        length_mode="linear",
        length_scale=length_scale,
    )
    tail = vfe.create_arrow(position, direction, magnitude, anchor="tail", **common)
    head = vfe.create_arrow(position, direction, magnitude, anchor="head", **common)
    expected = length_scale * magnitude * vector_scale
    d = np.asarray(direction) / np.linalg.norm(direction)
    at = float(np.dot(position, d))

    p = _projections(tail, direction)
    assert p.max() - p.min() == pytest.approx(expected, rel=1e-6)
    assert p.min() == pytest.approx(at, abs=1e-6)  # the tail sits on the surface point

    p = _projections(head, direction)
    assert p.max() - p.min() == pytest.approx(expected, rel=1e-6)
    assert p.max() == pytest.approx(at, abs=1e-6)  # the tip sits on the surface point

    # The arrow is a body of revolution about d: every vertex is within the head radius of
    # the axis through the position.
    offsets = np.asarray(tail.vertices) - position
    radial = np.linalg.norm(offsets - np.outer(offsets @ d, d), axis=1)
    assert radial.max() <= 0.1 * 1.5 * vector_scale + 1e-9


def test_zero_direction_points_up(vfe):
    arrow = vfe.create_arrow(np.zeros(3), np.zeros(3), 1.0, length_scale=2.0)
    z = np.asarray(arrow.vertices)[:, 2]
    assert z.min() == pytest.approx(0.0, abs=1e-9)
    assert z.max() == pytest.approx(2.0 * 0.4, rel=1e-9)  # default vector_scale 0.4


def test_antiparallel_direction_points_down(vfe):
    arrow = vfe.create_arrow(
        np.zeros(3), np.array([0.0, 0.0, -3.0]), 1.0, length_scale=2.0
    )
    z = np.asarray(arrow.vertices)[:, 2]
    # Tail at the origin, body below it: an arrow left pointing up would span [0, 0.8].
    assert z.max() == pytest.approx(0.0, abs=1e-9)
    assert z.min() == pytest.approx(-0.8, rel=1e-9)


def test_ply_declares_rgba_and_one_block_of_vertices_per_arrow(vfe, tmp_path):
    import trimesh

    positions = np.array([[0.0, 0, 0], [10, 0, 0], [0, 10, 0]])
    vectors = np.array([[0.0, 0, 1], [1, 0, 0], [0, 1, 1]])
    colors = np.array([[255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]], np.uint8)
    out = tmp_path / "arrows.ply"
    vfe.write_ply_arrows(out, positions, vectors, np.ones(3), colors, length_scale=5.0)

    text = out.read_text()
    header = text.split("end_header\n")[0].splitlines()
    for channel in ("red", "green", "blue", "alpha"):
        assert f"property uchar {channel}" in header
    per_arrow = len(
        vfe.create_arrow(positions[0], vectors[0], 1.0, length_scale=5.0).vertices
    )
    assert f"element vertex {3 * per_arrow}" in header

    mesh = trimesh.load(out, process=False)
    assert len(mesh.vertices) == 3 * per_arrow
    rgba = np.asarray(mesh.visual.vertex_colors)
    for i in range(3):
        block = rgba[i * per_arrow : (i + 1) * per_arrow]
        assert (block == colors[i]).all()


def test_magscale_ramp_hits_its_three_anchor_colours_and_never_turns_back(vfe):
    full = np.random.default_rng(3).gamma(2.0, 0.1, size=2000)
    blue, green, red = np.percentile(full, [30, 60, 90])
    colors = vfe._map_magnitude_to_colors_magscale(
        np.array([blue, green, red]),
        all_magnitudes_full=full,
        blue_pct=30,
        green_pct=60,
        red_pct=90,
    )
    assert colors[:, :3].tolist() == [[0, 0, 255], [0, 255, 0], [255, 0, 0]]

    ramp = np.linspace(full.min(), full.max(), 400)
    rgb = vfe._map_magnitude_to_colors_magscale(
        ramp, all_magnitudes_full=full, blue_pct=30, green_pct=60, red_pct=90
    )[:, :3]
    hues = np.array([colorsys.rgb_to_hsv(*(c / 255.0))[0] for c in rgb])
    # Blue (2/3) -> green (1/3) -> red (0): never rising (one uint8 step of slack).
    assert np.all(np.diff(hues) <= 1.0 / 255.0)
    assert hues[0] == pytest.approx(2 / 3) and hues[-1] == pytest.approx(0.0)


def _fields(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    ti = rng.normal(size=(n, 3))
    return {
        "positions": rng.normal(size=(n, 3)),
        "E1": rng.normal(size=(n, 3)),
        "E2": rng.normal(size=(n, 3)),
        "TI": ti,
        "E_sum": None,
        "TI_normal": None,
    }


def test_top_percent_keeps_the_strongest_tenth(vfe):
    from tit.blender.config import VectorConfig

    fields = _fields(1000)
    mags = np.linalg.norm(fields["TI"], axis=1)
    cfg = VectorConfig(
        subject_id="1", simulation_name="s", top_percent=10, all_nodes=True
    )
    out = vfe._filter_and_sample(cfg, fields)
    kept = np.linalg.norm(out["TI"], axis=1)
    assert len(kept) == 100  # the top tenth of 1000 distinct magnitudes
    assert sorted(kept) == sorted(mags[mags >= np.percentile(mags, 90)])
    assert kept.min() > np.sort(mags)[899]  # nothing from below the cut


def test_sampling_is_seeded_and_never_invents_rows(vfe):
    from tit.blender.config import VectorConfig

    fields = _fields(300)
    a = vfe._filter_and_sample(VectorConfig("1", "s", count=50, seed=9), fields)
    b = vfe._filter_and_sample(VectorConfig("1", "s", count=50, seed=9), fields)
    c = vfe._filter_and_sample(VectorConfig("1", "s", count=50, seed=10), fields)
    np.testing.assert_array_equal(a["positions"], b["positions"])
    assert not np.array_equal(a["positions"], c["positions"])
    everything = vfe._filter_and_sample(VectorConfig("1", "s", count=10_000), fields)
    assert len(everything["positions"]) == 300
    assert {tuple(r) for r in everything["positions"]} == {
        tuple(r) for r in fields["positions"]
    }
