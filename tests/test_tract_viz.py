"""Tract visuals: the array layer, the Blender bundle, the web payload and the figure helpers.

What this pins (2026-11-04)
    - :mod:`tit.blender.tract_data` slices, measures, thins and samples concatenated
      streamlines correctly; its colour map is monotone in lightness (CIE L*).
    - :func:`tit.blender.tract_publication.export_scene` passes world coordinates through
      unchanged and writes per-vertex attributes of the right shape and range; a highlighted
      deep region (the thalami) is lit at 0.4, the approved turntable's level (2026-11-05).
    - :func:`tit.plotting.tract_web.viewer_payload` round-trips positions to 0.005 mm and field
      values to one uint16 step, and a 15 000-streamline page stays under 12 MB.
    - The connectome helpers order hemispheres and pick the top edges.
    - ``TractVisualConfig``'s quality and thalamocortical sequence options: refused when they
      cannot run, carried into the manifest, and the sequence's two networks share one TI_max
      window (p99 over both, the approved render's; 2026-11-05).
    - A run writes one figure per colour and ``network.json``'s metrics, and leaves another colour
      alone (2026-11-05).

Where the expectations come from
    Closed forms (a straight line's arc length and tangent, a helix's), a plain Python loop
    re-deriving each vectorised result, and the CIE 1976 L* formula applied to the sRGB stops.
    Nothing compares a function with itself.

What is deliberately elsewhere
    Reading TRX with trx-python, the endpoint-patch KD-tree and the matplotlib figure need the
    real libraries: ``tests/numerical/test_tract_viz_real.py``. Blender renders are checked by
    eye from ``dev/tract_synthetic.py`` data (see ``docs/dev/TESTING.md``).

Run: .venv/bin/python -m pytest tests/test_tract_viz.py -q
"""

from __future__ import annotations

import os
from pathlib import Path

import base64
import json
import os

import numpy as np
import pytest

from tit.blender import tract_data as td


def _helix(
    n: int,
    turns: float = 1.0,
    radius: float = 10.0,
    pitch: float = 5.0,
    shift=(0, 0, 0),
):
    a = np.linspace(0, 2 * np.pi * turns, n)
    return np.stack([radius * np.cos(a), radius * np.sin(a), pitch * a], 1) + shift


def _tracts(lines, **dps) -> td.Tracts:
    points = np.concatenate(lines).astype(np.float32)
    offsets = np.r_[0, np.cumsum([len(l) for l in lines])].astype(np.int64)
    p = points.astype(np.float64)
    ti_max = 0.05 + 0.3 * np.exp(-((p - [10, 0, 0]) ** 2).sum(1) / 200.0)
    dpv = {
        "ti_max": ti_max.astype(np.float32),
        "ti_along": (0.7 * ti_max).astype(np.float32),
    }
    dps.setdefault("edge_id", np.arange(len(lines)) % 3 - 1)
    return td.Tracts(points, offsets, dpv, {k: np.asarray(v) for k, v in dps.items()})


@pytest.fixture
def three():
    straight = np.stack([np.arange(11.0), np.zeros(11), np.zeros(11)], 1)
    return _tracts([straight, _helix(40), _helix(25, shift=(30, 0, 0))])


# -- array layer --------------------------------------------------------------------------------


def test_select_returns_each_streamline_with_its_own_vertices(three):
    picked = td.select(three, [2, 0])
    for new, old in enumerate([2, 0]):
        a, b = three.offsets[old], three.offsets[old + 1]
        c, d = picked.offsets[new], picked.offsets[new + 1]
        np.testing.assert_array_equal(picked.points[c:d], three.points[a:b])
        np.testing.assert_array_equal(
            picked.dpv["ti_max"][c:d], three.dpv["ti_max"][a:b]
        )
    assert list(picked.dps["edge_id"]) == [
        three.dps["edge_id"][2],
        three.dps["edge_id"][0],
    ]


def test_arc_length_of_a_straight_line_is_its_coordinate(three):
    s = td.arc_length(three)
    np.testing.assert_allclose(s[:11], np.arange(11.0), atol=1e-6)
    assert s[11] == 0.0 and s[11 + 40] == 0.0  # every streamline restarts at zero


def test_arc_length_of_a_helix_matches_the_closed_form(three):
    s = td.arc_length(three)[11 : 11 + 40]
    exact = 2 * np.pi * np.hypot(10.0, 5.0)  # one turn of radius 10, pitch 5 per radian
    assert s[-1] == pytest.approx(exact, rel=2e-3)  # chord sum on 39 segments


def test_decimate_keeps_both_ends_and_thins_to_the_step(three):
    thin = td.decimate(three, 3.0)
    for i in range(three.n):
        a, b = three.offsets[i], three.offsets[i + 1]
        c, d = thin.offsets[i], thin.offsets[i + 1]
        np.testing.assert_array_equal(thin.points[c], three.points[a])
        np.testing.assert_array_equal(thin.points[d - 1], three.points[b - 1])
    gaps = np.linalg.norm(np.diff(thin.points[:4], axis=0), axis=1)
    np.testing.assert_allclose(gaps, 3.0)  # the straight line: 0, 3, 6, 9 then the end


def test_tangents_of_a_straight_line_are_its_axis(three):
    np.testing.assert_allclose(td.tangents(three)[:11], [[1, 0, 0]] * 11, atol=1e-7)


def test_peak_vertex_matches_a_python_loop(three):
    values = three.dpv["ti_along"]
    expected = [
        int(
            three.offsets[i]
            + np.argmax(values[three.offsets[i] : three.offsets[i + 1]])
        )
        for i in range(three.n)
    ]
    assert list(td.peak_vertex(three, values)) == expected


def test_ratio_metric_guards_zero_ti_max(three):
    three.dpv["ti_max"][0] = 0.0
    ratio = td.vertex_metric(three, "ti_ratio")
    assert ratio[0] == 0.0
    np.testing.assert_allclose(ratio[1:], 0.7, rtol=1e-6)
    with pytest.raises(ValueError):
        td.vertex_metric(three, "direction")


def test_smoothing_keeps_constants_and_never_crosses_streamlines():
    a = np.stack([np.arange(20.0), np.zeros(20), np.zeros(20)], 1)
    b = a + [0, 5, 0]
    t = _tracts([a, b])
    values = np.r_[np.full(20, 1.0), np.full(20, 3.0)]
    np.testing.assert_allclose(td.smooth_along(t, values, 3.0), values, rtol=1e-6)
    zigzag = np.r_[np.tile([0.0, 2.0], 10), np.tile([0.0, 2.0], 10)]
    smooth = td.smooth_along(t, zigzag, 3.0)
    assert smooth[5:15].std() < 0.2 * zigzag[5:15].std()  # 1 mm jitter averaged out
    np.testing.assert_allclose(smooth[5:15].mean(), 1.0, atol=0.15)


def test_subsample_keeps_everything_under_budget():
    assert list(td.subsample(np.ones(5), 10)) == [0, 1, 2, 3, 4]


def test_subsample_favours_high_field_but_keeps_context():
    rng = np.random.default_rng(1)
    weight = np.r_[np.full(900, 0.01), np.full(100, 1.0)] * (
        1 + 0.01 * rng.random(1000)
    )
    picked = td.subsample(weight, 200, seed=3)
    assert len(picked) == 200 == len(np.unique(picked))
    assert np.all(np.diff(picked) > 0)
    hot = (picked >= 900).sum()
    assert hot > 60  # 10 % of the population, well over 30 % of the sample
    assert hot < 200  # and the low-field context is still represented


def _lightness(rgb):
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    y = lin @ [0.2126, 0.7152, 0.0722]
    return np.where(y > (6 / 29) ** 3, 116 * np.cbrt(y) - 16, y * (29 / 3) ** 3)


def test_colour_map_rises_monotonically_in_lightness():
    colours = td.colormap(np.linspace(0, 1, 257))
    assert np.all(np.diff(_lightness(colours)) > 0)
    np.testing.assert_allclose(
        td.colormap(np.array([0.0, 1.0])), [td.PLASMA_SRGB[0], td.PLASMA_SRGB[-1]]
    )
    np.testing.assert_allclose(
        td.colormap(np.array([-1.0, 2.0])), td.colormap(np.array([0.0, 1.0]))
    )


def test_edges_json_reads_as_a_mapping_or_a_list(tmp_path):
    record = {"region_a": "lh.a", "region_b": "rh.b", "n_streamlines": 3}
    (tmp_path / "a.json").write_text(json.dumps({"4": record}))
    (tmp_path / "b.json").write_text(json.dumps([{**record, "edge_id": 4}]))
    assert td.read_edges(str(tmp_path / "a.json"))[4]["region_a"] == "lh.a"
    assert td.read_edges(str(tmp_path / "b.json"))[4]["region_b"] == "rh.b"
    assert td.read_edges(str(tmp_path / "missing.json")) == {}
    assert td.edge_name(record) == "lh.a – rh.b"


def test_connectome_with_mismatched_labels_is_refused(tmp_path):
    np.savez(tmp_path / "c.npz", matrix=np.zeros((3, 3)), labels=np.array(["a", "b"]))
    with pytest.raises(ValueError, match="does not match"):
        td.read_connectome(str(tmp_path / "c.npz"))


# -- Blender bundle -----------------------------------------------------------------------------


def _sphere(n=12):
    """A closed triangulated UV sphere of radius 60 mm about the origin."""
    u, v = np.meshgrid(
        np.linspace(0, 2 * np.pi, n, endpoint=False), np.linspace(0.2, np.pi - 0.2, n)
    )
    pts = (
        np.stack([np.cos(u) * np.sin(v), np.sin(u) * np.sin(v), np.cos(v)], -1).reshape(
            -1, 3
        )
        * 60
    )
    tris = []
    for r in range(n - 1):
        for c in range(n):
            a, b, d, e = (
                r * n + c,
                r * n + (c + 1) % n,
                (r + 1) * n + c,
                (r + 1) * n + (c + 1) % n,
            )
            tris += [(a, b, d), (b, e, d)]
    return pts, np.asarray(tris)


def test_export_scene_draws_whole_fibres_and_lights_their_regions(tmp_path, three):
    from tit.blender import tract_publication as tp
    from tit.blender.config import TractVisualConfig

    cfg = TractVisualConfig(
        subject_id="x", simulation_name="s", roi_center_mm=[1, 2, 3]
    )
    electrodes = [{"name": "F7", "xyz": [-60.0, 30.0, 10.0], "channel": 0}]
    sphere = _sphere()
    edges = {
        -1: {
            "region_a": "lh.c",
            "region_b": "lh.c",
        },  # both ends in one region: n counts 1
        0: {"region_a": "lh.a", "region_b": "Left-B"},
        1: {"region_a": "lh.a", "region_b": "lh.c"},
    }
    cortical = {"lh.a": np.arange(0, 20), "lh.c": np.arange(40, 50)}
    blob = (
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32),
        np.array([[0, 1, 2]]),
    )
    tp.export_scene(
        cfg,
        three,
        (*sphere, len(sphere[0])),
        None,
        electrodes,
        str(tmp_path / "b"),
        title="t",
        synthetic=True,
        context=three,
        edges=edges,
        regions=(cortical, {"Left-B": blob}),
    )
    manifest = json.loads((tmp_path / "b" / "manifest.json").read_text())
    assert manifest["n_drawn"] == 3
    assert manifest["roi"] == {"center": [1, 2, 3], "radius": 10.0}
    assert manifest["panels"] == ["lateral", "superior", "anterior", "posterior"]
    assert not {"labels", "views"} & set(manifest)
    with np.load(tmp_path / "b" / "tracts.npz") as t:
        offsets = t["offsets"]
        np.testing.assert_array_equal(
            t["points"][offsets[:-1]], three.points[three.offsets[:-1]]
        )
        np.testing.assert_array_equal(
            t["points"][offsets[1:] - 1], three.points[three.offsets[1:] - 1]
        )
        for a, b in zip(offsets[:-1], offsets[1:]):
            assert np.ptp(t["r"][a:b]) == 0  # one width along the whole fibre
        assert 0.0 <= t["v"].min() and t["v"].max() <= 1.0
        assert t["tangent"].shape == (len(t["points"]), 3)
    with np.load(tmp_path / "b" / "glass.npz") as g:
        assert (g["lit"] > 0).any() and g["lit"].max() == pytest.approx(1.0)
        assert len(g["lit"]) == len(g["vertices"])
    with np.load(tmp_path / "b" / "regions.npz") as r:
        assert r["vertices"].shape == (3, 3) and (r["lit"] > 0).all()
    assert (tmp_path / "b" / "context.npz").is_file()
    assert manifest["vmax"] == pytest.approx(
        np.percentile(td.smooth_along(three, three.dpv["ti_along"]), 99.5), rel=1e-5
    )


def test_highlighted_deep_regions_glow_softly_and_parcels_by_count(
    tmp_path, three, monkeypatch
):
    """A highlighted thalamus is exported at 0.4, the level of the sub-CHN turntable the user
    approved (HIGHLIGHT_LEVEL at c5312a3c); previews v1-v3 had 1.0."""
    from tit.blender import tract_publication as tp
    from tit.blender.config import TractVisualConfig

    class NearestTree:  # scipy is mocked on the host; the fibre-to-thalamus distance is unused
        def __init__(self, reference):
            self.reference = np.asarray(reference)

        def query(self, points):
            d = np.linalg.norm(points[:, None] - self.reference[None], axis=-1)
            return d.min(1), d.argmin(1)

    monkeypatch.setattr("scipy.spatial.cKDTree", NearestTree)
    sphere = _sphere()
    edges = {
        -1: {"region_a": "lh.c", "region_b": "lh.c"},
        0: {"region_a": "lh.a", "region_b": "Left-B"},
        1: {"region_a": "lh.a", "region_b": "lh.c"},
    }
    blob = (
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32),
        np.array([[0, 1, 2]]),
    )
    tp.export_scene(
        TractVisualConfig(subject_id="x", simulation_name="s"),
        three,
        (*sphere, len(sphere[0])),
        None,
        [],
        str(tmp_path / "b"),
        title="t",
        synthetic=True,
        edges=edges,
        regions=(
            {"lh.a": np.arange(0, 20), "lh.c": np.arange(40, 50)},
            {"Left-B": blob},
        ),
        highlight=["Left-B"],
    )
    with np.load(tmp_path / "b" / "regions.npz") as r:
        np.testing.assert_allclose(r["lit"], 0.4)
    with np.load(tmp_path / "b" / "glass.npz") as g:
        # lh.a and lh.c each hold 2 streamlines, the most of any parcel: both at full level
        assert g["lit"].max() == pytest.approx(1.0)


def test_align_index_colours_diverge_about_one():
    """1 sits mid-map, half and double sit at the ends (log2 window of one octave)."""
    v = td.colour_position(np.array([0.25, 0.5, 1.0, 2.0, 4.0]), "align_index", 2.0)
    np.testing.assert_allclose(v, [0.0, 0.0, 0.5, 1.0, 1.0])
    mid = td.colormap(np.array([0.5]), td.COOLWARM_SRGB)[0]
    assert np.ptp(mid) < 0.02  # neutral grey at 1
    blue, warm = td.colormap(np.array([0.0, 1.0]), td.COOLWARM_SRGB)
    assert blue[2] > blue[0] and warm[0] > warm[2]


def test_align_index_is_the_ratio_of_averaged_along_and_random_direction_field(three):
    three.dpv["ti_avg"] = (three.dpv["ti_max"] * 0.5).astype(np.float32)
    ratio = td.display_metric(three, "align_index")
    np.testing.assert_allclose(
        ratio, 0.7 / 0.5, rtol=1e-5
    )  # ti_along = 0.7 ti_max throughout


def test_concat_keeps_order_and_shared_keys(three):
    both = td.concat([three, td.select(three, [0])])
    assert both.n == 4 and both.offsets[-1] == len(both.points)
    np.testing.assert_array_equal(
        both.points[both.offsets[3] :], three.points[: three.offsets[1]]
    )
    assert set(both.dpv) == set(three.dpv)


def test_resolve_tractogram_prefers_all_then_the_only_one(tmp_path):
    from tit.blender.tract_publication import resolve_tractogram

    (tmp_path / "cst.trx").write_bytes(b"")
    assert resolve_tractogram(str(tmp_path), "").endswith("cst.trx")
    (tmp_path / "af.trx").write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="exactly one"):
        resolve_tractogram(str(tmp_path), "")
    (tmp_path / "all.trx").write_bytes(b"")
    assert resolve_tractogram(str(tmp_path), "").endswith("all.trx")
    assert resolve_tractogram(str(tmp_path), "af.trx").endswith("af.trx")
    with pytest.raises(FileNotFoundError):
        resolve_tractogram(str(tmp_path), "nope.trx")


def test_simulation_electrodes_pairs_names_with_coordinates(tmp_path):
    from tit.blender.tract_publication import simulation_electrodes

    (tmp_path / "documentation").mkdir()
    record = {
        "electrode_pairs": [["F7", "TP7"], ["FT7", "P7"]],
        "electrode_coordinates": [[1, 2, 3]] * 4,
    }
    (tmp_path / "documentation" / "config.json").write_text(json.dumps(record))
    got = simulation_electrodes(str(tmp_path))
    assert [(e["name"], e["channel"]) for e in got] == [
        ("F7", 0),
        ("TP7", 0),
        ("FT7", 1),
        ("P7", 1),
    ]
    assert simulation_electrodes(str(tmp_path / "none")) == []


def test_tract_config_validates_and_round_trips():
    from tit.blender.config import TractVisualConfig
    from tit.config_io import deserialize_config, serialize_config

    cfg = TractVisualConfig(
        subject_id="ernie", simulation_name="L_Insula", metric="ti_ratio"
    )
    assert cfg.metric is TractVisualConfig.Metric.TI_RATIO
    data = serialize_config(cfg)
    assert data["_type"] == "TractVisualConfig"
    assert deserialize_config(TractVisualConfig, data) == cfg
    assert (
        TractVisualConfig(
            subject_id="e", simulation_name="s", vmax_v_per_m=0.3
        ).vmax_v_per_m
        == 0.3
    )
    for bad in (
        {"vmax_v_per_m": 0.0},
        {"max_streamlines": 0},
        {"roi_center_mm": [1, 2]},
        {"metric": "fa"},
        {"width": 10},
    ):
        with pytest.raises(ValueError):
            TractVisualConfig(subject_id="e", simulation_name="s", **bad)


def test_render_and_runner_tract_configs_carry_distinct_type_tags():
    """The render config and tit.tract's runner config once both tagged ``"TractConfig"``."""
    from tit.blender.config import TractVisualConfig
    from tit.config_io import _discriminator_for
    from tit.server.routes.validate import AMBIGUOUS_KIND_CLASSES
    from tit.tract.config import TractConfig

    assert _discriminator_for(TractVisualConfig) == "TractVisualConfig"
    assert _discriminator_for(TractConfig) == "TractConfig"
    # A tit.tract runner config posted as a blender job must not resolve to a render.
    assert "TractConfig" not in AMBIGUOUS_KIND_CLASSES["blender"]


# -- web viewer ---------------------------------------------------------------------------------


def _decode(text, dtype):
    return np.frombuffer(base64.b64decode(text), dtype=dtype)


def test_viewer_payload_round_trips_positions_and_values(three):
    from tit.plotting.tract_web import viewer_payload

    edges = {
        0: {
            "region_a": "lh.a",
            "region_b": "lh.b",
            "n_streamlines": 40,
            "ti_along_mean": {"median": 0.01},
        },
        1: {
            "region_a": "rh.a",
            "region_b": "rh.b",
            "n_streamlines": 7,
            "ti_along_mean": {"median": 0.2},
        },
    }
    electrode = {"name": "F7", "xyz": [-60.0, 30.0, 10.0], "channel": 1}
    sphere = _sphere()
    sphere = (
        sphere[0].astype(np.float32),
        sphere[1],
    )  # SimNIBS surfaces arrive as float32
    payload = viewer_payload(three, sphere, [electrode], edges, title="t")
    json.dumps(payload)  # every number a plain float, so the page can embed it
    assert (
        "ti_avg" not in payload["values"]
    )  # no ti_avg in the TRX: no align_index channel
    centre = np.asarray(payload["centre"])
    np.testing.assert_allclose(
        np.asarray(payload["electrodes"][0]["xyz"]) + centre,
        electrode["xyz"],
        atol=1e-4,
    )
    pos = (
        _decode(payload["positions"], "<i2").reshape(-1, 3) / payload["scale"] + centre
    )
    offsets = _decode(payload["offsets"], "<u4")
    assert offsets[-1] == len(pos) and len(offsets) == three.n + 1
    np.testing.assert_allclose(
        pos[offsets[:-1]], three.points[three.offsets[:-1]], atol=0.005 + 1e-6
    )
    along = (
        _decode(payload["values"]["ti_along"], "<u2")
        * payload["value_scale"]["ti_along"]
        / 65535
    )
    first = along[offsets[:-1]]
    np.testing.assert_allclose(
        first,
        td.smooth_along(three, three.dpv["ti_along"])[three.offsets[:-1]],
        atol=payload["value_scale"]["ti_along"] / 65535,
    )
    assert [(e["id"], e["name"], e["n"]) for e in payload["edges"]] == [
        (
            1,
            "rh.a – rh.b",
            7,
        ),  # the higher edges.json median first, its tractogram count
        (0, "lh.a – lh.b", 40),
        (-1, "unassigned", 1),  # last, counted in the shown subset
    ]


def test_viewer_page_is_self_contained_pinned_and_small(tmp_path):
    from tit.plotting.tract_web import THREE_VERSION, write_viewer

    rng = np.random.default_rng(0)
    lines = [
        _helix(
            int(rng.integers(60, 200)), turns=rng.random(), shift=rng.normal(0, 20, 3)
        )
        for _ in range(15_000)
    ]
    big = _tracts(lines, ti_along_max=rng.random(15_000))
    path = write_viewer(
        str(tmp_path / "v.html"), big, _sphere(40), [], {}, title="a</script>b"
    )
    page = (tmp_path / "v.html").read_text()
    assert path.endswith("v.html")
    assert (
        f"three@{THREE_VERSION}/build/three.module.js" in page
        and THREE_VERSION == "0.160.0"
    )
    assert (tmp_path / "v.html").stat().st_size < 12 * 1024 * 1024
    assert page.count("</script>") == 3  # importmap, data, module; none from the title
    assert "prefers-color-scheme: dark" in page and "max-width: 720px" in page


# -- connectome helpers -------------------------------------------------------------------------


def test_hemisphere_order_puts_left_then_right_then_the_rest():
    from tit.plotting.tract_connectome import hemisphere_order

    labels = ["rh.a", "Left-Thalamus", "brainstem", "lh.b", "ctx-rh-c", "lh.a"]
    assert [labels[i] for i in hemisphere_order(labels)] == [
        "Left-Thalamus",
        "lh.b",
        "lh.a",
        "rh.a",
        "ctx-rh-c",
        "brainstem",
    ]


def test_top_edges_are_the_largest_upper_triangle_entries():
    from tit.plotting.tract_connectome import metric_units, top_edges

    m = np.array([[9.0, 0.2, 0.0], [0.2, 9.0, np.nan], [0.0, np.nan, 9.0]])
    m[0, 2] = m[2, 0] = 0.5
    assert top_edges(m, ["a", "b", "c"], k=5) == [("a", "c", 0.5), ("a", "b", 0.2)]
    counts = np.array([[0, 30, 2], [30, 0, 0], [2, 0, 0]])
    assert top_edges(m, ["a", "b", "c"], 5, counts, min_count=10) == [("a", "b", 0.2)]
    assert metric_units("ti_along_max") == "V/m"
    assert metric_units("count") == "streamlines"
    assert metric_units("ti_ratio_mean") == "1"


# -- TRX reading (the reference reader is checked in tests/numerical) ----------------------------


def test_load_trx_reads_zip_and_directory_and_drops_one_point_streamlines(
    tmp_path, three
):
    import importlib.util
    import zipfile
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "tract_synthetic", Path(__file__).parents[1] / "dev" / "tract_synthetic.py"
    )
    synthetic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(synthetic)
    lone = np.array([[1.0, 2.0, 3.0]], np.float32)
    points = np.concatenate([three.points, lone])
    offsets = np.r_[three.offsets, len(points)]
    dpv = {k: np.r_[v, 0.5] for k, v in three.dpv.items()}
    dps = {"edge_id": np.r_[three.dps["edge_id"], 7].astype(np.int32)}
    synthetic.write_trx(str(tmp_path / "a.trx"), points, offsets, dpv, dps)
    with zipfile.ZipFile(tmp_path / "a.trx") as archive:
        archive.extractall(tmp_path / "d.trx")
    for path in (tmp_path / "a.trx", tmp_path / "d.trx"):
        got = td.load_trx(str(path))
        assert got.n == 3  # the one-point streamline has no tube and is dropped
        np.testing.assert_array_equal(got.points, three.points)
        np.testing.assert_array_equal(got.offsets, three.offsets)
        np.testing.assert_array_equal(got.dpv["ti_along"], three.dpv["ti_along"])
        assert list(got.dps["edge_id"]) == list(three.dps["edge_id"])


def test_ranking_winners_and_montage_labels():
    from tit.plotting.tract_connectome import montage_label, ranking_winners

    rows = [
        {
            "montage": ["T8", "CP5", "C3", "C4"],
            "rank_by_ti_max": 5,
            "rank_by_ti_along": 1,
        },
        {
            "montage": ["T8", "C3", "C4", "CP5"],
            "rank_by_ti_max": 1,
            "rank_by_ti_along": 9,
        },
        {
            "montage": ["F8", "CP5", "P8", "C3"],
            "rank_by_ti_max": 2,
            "rank_by_ti_along": 2,
        },
    ]
    by_max, by_along = ranking_winners(rows)
    assert montage_label(by_max["montage"]) == "T8–C3 + C4–CP5"
    assert montage_label(by_along["montage"]) == "T8–CP5 + C3–C4"


# -- named networks (thalamocortical renders) -----------------------------------------------------


def test_edges_between_matches_either_orientation():
    from tit.blender.tract_publication import edges_between

    edges = {
        1: {"region_a": "Left-Thalamus-Proper", "region_b": "lh.superiorfrontal"},
        2: {"region_a": "rh.precuneus", "region_b": "Right-Thalamus-Proper"},
        3: {"region_a": "lh.superiorfrontal", "region_b": "rh.precuneus"},
        4: {"region_a": "Left-Thalamus-Proper", "region_b": "Left-Thalamus-Proper"},
    }
    thal = ["Left-Thalamus-Proper", "Right-Thalamus-Proper"]
    assert edges_between(edges, thal, ["lh.superiorfrontal"]) == {1}
    assert edges_between(edges, thal, ["rh.precuneus", "lh.superiorfrontal"]) == {1, 2}


def test_network_medians_are_over_the_streamlines(three):
    from tit.blender.tract_publication import network_medians

    three.dpv["ti_avg"] = (three.dpv["ti_max"] * 0.5).astype(np.float32)
    medians = network_medians(three)
    per = td.arc_length_mean(three, three.dpv["ti_max"])
    assert medians["median_ti_max_v_per_m"] == pytest.approx(np.median(per), abs=1e-4)
    assert medians["median_align_index"] == pytest.approx(
        1.4
    )  # ti_along 0.7 ti_max over ti_avg 0.5 ti_max


def test_network_config_validation():
    from tit.blender.config import TractVisualConfig

    for bad in (
        {"network_from": ["a"]},
        {"lateral_side": 2},
        {"iso_shell_percentile": 100.0},
        {"turntable_crossfade": True, "metric": "direction"},
    ):
        with pytest.raises(ValueError):
            TractVisualConfig(subject_id="e", simulation_name="s", **bad)


def test_prune_keeps_the_top_fraction_by_mean_ti_max():
    from tit.blender.tract_publication import prune_by_ti_max

    lines = [
        np.stack([np.arange(5.0), np.full(5, float(i)), np.zeros(5)], 1)
        for i in range(10)
    ]
    t = _tracts(lines)
    t.dpv["ti_max"] = np.repeat(
        np.arange(10, dtype=np.float32) / 10, 5
    )  # mean = i / 10
    rank, kept, cut, rank_cut = prune_by_ti_max(t, 0.2)
    assert list(np.flatnonzero(kept)) == [8, 9]  # the two highest means
    assert cut == pytest.approx(0.8)  # the weakest kept streamline's mean
    np.testing.assert_allclose(rank, np.arange(10) / 9)
    assert rank_cut == pytest.approx(8 / 9)
    assert (rank[kept] >= rank_cut).all() and (rank[~kept] < rank_cut).all()


def test_region_words_name_dk40_parcels_with_hemisphere():
    from tit.blender.tract_publication import region_words

    assert region_words("lh.superiorfrontal") == "L superior frontal"
    assert region_words("rh.precuneus") == "R precuneus"
    assert region_words("Left-Thalamus-Proper") == "Left-Thalamus-Proper"


# -- figure, quality, the thalamocortical sequence (the Visual exporter's Networks tab) ------------


def test_render_options_are_refused_when_they_cannot_run():
    from tit.blender.config import TractVisualConfig

    base = dict(subject_id="x", simulation_name="s")
    with pytest.raises(ValueError):
        TractVisualConfig(**base, quality="draft")
    with pytest.raises(ValueError, match="runs alone"):
        TractVisualConfig(**base, thalamocortical_sequence=True)  # stills default on
    alone = dict(base, thalamocortical_sequence=True, stills=False)
    TractVisualConfig(**alone)
    for clash in (dict(turntable=True), dict(network_bundle="cst_lh")):
        with pytest.raises(ValueError, match="runs alone"):
            TractVisualConfig(**alone, **clash)


def test_a_selection_exports_with_its_setup_under_its_own_name(tmp_path, three):
    from tit.blender import tract_publication as tp
    from tit.blender.config import TractVisualConfig
    from tit.blender.network_setup import resolve_network_setup
    from tit.tract.config import Selection

    selection = Selection(
        name="net", kind="edges", regions=["lh.a"], pairs=[["lh.a", "rh.b"]]
    )
    cfg = TractVisualConfig("x", "s", selection=selection, metric="ti_max")
    setup = resolve_network_setup(selection, {("lh.a", "rh.b"): 3})
    cortical = {"lh.a": np.arange(0, 20), "rh.b": np.arange(40, 50)}
    sphere = _sphere()
    out = tmp_path / "tract"
    tp.export_scene(
        cfg,
        three,
        (*sphere, len(sphere[0])),
        None,
        [],
        str(out / tp.bundle_folder(cfg)),
        title="t",
        synthetic=False,
        edges={
            -1: {"region_a": "lh.a", "region_b": "rh.b"},
            0: {"region_a": "lh.a", "region_b": "rh.b"},
            1: {"region_a": "lh.a", "region_b": "rh.b"},
        },
        regions=(cortical, {}),
        highlight=["lh.a"],
        setup=setup,
    )
    bundle = out / "bundle_ti_max"
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["stem"] == "ti_max"
    assert manifest["network"] is True
    assert manifest["setup"] == setup
    # The figure lands in the network's folder, one level up from the bundle.
    assert (bundle / manifest["output_dir"]).resolve() == out.resolve()
    # One tube radius, the setup's: a width that does not encode the field.
    radii = np.load(bundle / "tracts.npz")["r"]
    assert radii.max() == pytest.approx(setup["values"]["tube_radius_mm"])
    assert radii.min() == pytest.approx(setup["values"]["tube_radius_mm"])


def test_a_selection_lights_only_its_busiest_parcels(tmp_path, three, monkeypatch):
    from tit.blender import tract_publication as tp
    from tit.blender.config import TractVisualConfig
    from tit.tract.config import Selection

    monkeypatch.setattr(tp, "MAX_LIT_PARCELS", 1)
    selection = Selection(
        name="net", kind="edges", pairs=[["lh.a", "lh.b"], ["lh.a", "lh.c"]]
    )
    cfg = TractVisualConfig("x", "s", selection=selection, metric="ti_max")
    # Streamlines 0 and 1 end in lh.b, one in lh.c: lh.a is the seed, lh.b the busiest parcel.
    three.dps["edge_id"] = np.array([0, 0, 1])
    edges = {
        0: {"region_a": "lh.a", "region_b": "lh.b"},
        1: {"region_a": "lh.a", "region_b": "lh.c"},
    }
    cortical = {
        "lh.a": np.arange(0, 5),
        "lh.b": np.arange(10, 15),
        "lh.c": np.arange(20, 25),
    }
    sphere = _sphere()
    bundle = tmp_path / "b"
    tp.export_scene(
        cfg,
        three,
        (*sphere, len(sphere[0])),
        None,
        [],
        str(bundle),
        title="t",
        synthetic=False,
        edges=edges,
        regions=(cortical, {}),
        highlight=["lh.a"],
    )
    with np.load(bundle / "glass.npz") as glass:
        lit = glass["lit"]
    assert lit[10:15].min() > 0  # lh.b
    assert lit[20:25].max() == 0  # lh.c


def test_the_bundle_route_becomes_a_selection_of_the_edges_it_holds(three):
    from tit.blender import tract_publication as tp
    from tit.blender.config import TractVisualConfig

    edges = {
        0: {"region_a": "lh.a", "region_b": "lh.b"},
        1: {"region_a": "lh.a", "region_b": "lh.c"},
    }
    cfg = TractVisualConfig("x", "s", network_bundle="cst", network_top_edges=0)
    picked = tp._bundle_as_selection(cfg, three, edges)
    assert picked.selection.name == "cst"
    assert picked.network_bundle == ""
    assert sorted(map(tuple, picked.selection.pairs)) == [
        ("lh.a", "lh.b"),
        ("lh.a", "lh.c"),
    ]
    assert tp.network_slug(picked) == "cst"


def _run_tract_project(tmp_path, monkeypatch, three, render):
    """A sub-x simulation with an assessed bundle, and run_tract's anatomy and Blender stubbed."""
    from tit.blender import tract_publication as tp
    from tit.paths import get_path_manager

    (tmp_path / "project").mkdir()
    pm = get_path_manager(str(tmp_path / "project"))
    tract = Path(pm.simulation("x", "s"), "tract")
    tract.mkdir(parents=True)
    three.dps["edge_id"] = np.array([0, 0, 0])
    (tract / "edges.json").write_text(
        json.dumps({"0": {"region_a": "lh.a", "region_b": "rh.b", "n_streamlines": 3}})
    )
    monkeypatch.setattr(tp.td, "load_trx", lambda path: three)
    (tract / "net.trx").touch()
    sphere = _sphere()
    monkeypatch.setattr(tp, "glass_surface", lambda m2m: (*sphere, 72))
    monkeypatch.setattr(tp, "label_volume", lambda pm, sid: None)
    monkeypatch.setattr(tp, "region_geometry", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(tp, "simulation_electrodes", lambda d: [])
    monkeypatch.setattr(
        tp, "ti_iso_shell", lambda *a, **k: (*map(np.asarray, sphere), 0.3)
    )
    monkeypatch.setattr(tp, "render", render)
    return pm


def _selection_config(**fields):
    from tit.blender.config import TractVisualConfig
    from tit.tract.config import Selection

    return TractVisualConfig(
        "x",
        "s",
        selection=Selection(
            name="net", kind="edges", regions=["lh.a"], pairs=[["lh.a", "rh.b"]]
        ),
        metric="ti_max",
        web=False,
        connectome=False,
        **fields,
    )


def _still_writer(manifest_path, *rest):
    """What Blender does with a bundle: write the figure and, if asked, the scene beside it."""
    manifest = json.loads(Path(manifest_path).read_text())
    base = Path(manifest_path).parent / manifest["output_dir"]
    (base / f"{manifest['stem']}.png").write_bytes(b"png")
    if manifest["export_blend"]:
        (base / "network.blend").write_bytes(b"blend" * 10)


def test_a_run_leaves_one_figure_and_network_json_and_can_be_run_again_from_it(
    tmp_path, monkeypatch, three
):
    from tit.blender import tract_publication as tp
    from tit.blender.config import TractVisualConfig
    from tit.config_io import deserialize_config

    _run_tract_project(tmp_path, monkeypatch, three, _still_writer)
    out = Path(tp.run_tract(_selection_config()))
    assert out.parts[-3:] == ("s", "networks", "net")
    assert sorted(p.name for p in out.iterdir()) == ["network.json", "ti_max.png"]
    record = json.loads((out / "network.json").read_text())
    assert record["network"] == "net"
    assert record["selection"]["pairs"] == [["lh.a", "rh.b"]]
    assert record["code_version"]
    entry = record["colours"]["ti_max"]
    assert entry["files"] == ["ti_max.png"]
    assert entry["setup"]["n_streamlines"] == 3
    assert entry["setup"]["n_drawn"] == 3
    metrics = record["metrics"]
    assert metrics["streamlines_total"] == 3
    assert metrics["streamlines_per_region"] == {"lh.a": 3, "rh.b": 3}
    assert metrics["median_ti_max_v_per_m"] > 0
    image = metrics["images"]["ti_max.png"]
    assert image["panels"] == ["lateral", "superior", "anterior", "posterior"]
    assert image["streamlines_drawn"] == 3
    assert image["sampling"] == "all drawn"
    assert image["lateral_side"] == "left"
    assert image["colour_scale"]["units"] == "V/m"
    assert image["shell"] is None  # under 10 streamlines, which a shell would hide
    assert record["blend"] is None

    # Re-render: what network.json holds is a config, the same one, and it runs.
    (out / "ti_max.png").unlink()
    config = dict(entry["config"])
    config.pop("project_dir")
    again = deserialize_config(TractVisualConfig, config)
    assert again.selection == _selection_config().selection
    tp.run_tract(again)
    assert (out / "ti_max.png").exists()


def test_a_shell_is_recorded_with_its_level_and_how_it_was_chosen(
    tmp_path, monkeypatch, three
):
    from tit.blender import tract_publication as tp

    _run_tract_project(tmp_path, monkeypatch, three, _still_writer)
    out = Path(
        tp.run_tract(_selection_config(overrides={"iso_shell_percentile": 90.0}))
    )
    record = json.loads((out / "network.json").read_text())
    shell = record["metrics"]["images"]["ti_max.png"]["shell"]
    assert shell["level_v_per_m"] == 0.3  # _run_tract_project's stub
    assert shell["percentile"] == 90.0
    assert "volume-weighted" in shell["chosen_by"]


def test_rendering_another_colour_keeps_the_first_in_network_json(
    tmp_path, monkeypatch, three
):
    from dataclasses import replace

    from tit.blender import tract_publication as tp

    _run_tract_project(tmp_path, monkeypatch, three, _still_writer)
    cfg = _selection_config()
    out = Path(tp.run_tract(cfg))
    tp.run_tract(replace(cfg, metric="direction"))
    record = json.loads((out / "network.json").read_text())
    assert set(record["colours"]) == {"ti_max", "direction"}
    assert (out / "ti_max.png").exists() and (out / "direction.png").exists()
    # Each image keeps how to read it, whichever colour was rendered last.
    images = record["metrics"]["images"]
    assert images["ti_max.png"]["colour_scale"]["label"]
    assert images["direction.png"]["colour_key"]["red"] == "left – right"


def test_a_colour_rendered_again_replaces_only_its_own_record(
    tmp_path, monkeypatch, three
):
    from dataclasses import replace

    from tit.blender import tract_publication as tp

    _run_tract_project(tmp_path, monkeypatch, three, _still_writer)
    cfg = _selection_config()
    out = Path(tp.run_tract(cfg))
    tp.run_tract(replace(cfg, metric="direction"))
    first = json.loads((out / "network.json").read_text())
    tp.run_tract(replace(cfg, overrides={"max_streamlines": 2}))
    again = json.loads((out / "network.json").read_text())
    assert again["colours"]["direction"] == first["colours"]["direction"]
    images = again["metrics"]["images"]
    assert images["ti_max.png"]["streamlines_drawn"] == 2
    assert images["ti_max.png"]["sampling"] == "even sample"
    assert images["direction.png"]["streamlines_drawn"] == 3


def test_a_blend_is_recorded_with_its_colour_and_size_and_survives_a_plain_render(
    tmp_path, monkeypatch, three
):
    from dataclasses import replace

    from tit.blender import tract_publication as tp

    _run_tract_project(tmp_path, monkeypatch, three, _still_writer)
    cfg = _selection_config(export_blend=True)
    out = Path(tp.run_tract(cfg))
    # A blend outlives the bundle, which a successful render deletes.
    assert not (out / "bundle_ti_max").exists()
    record = json.loads((out / "network.json").read_text())
    assert record["blend"]["file"] == "network.blend"
    assert record["blend"]["colour"] == "ti_max"
    assert record["blend"]["bytes"] == 50
    assert "network.blend" not in record["colours"]["ti_max"]["files"]
    tp.run_tract(replace(cfg, metric="direction", export_blend=False))
    kept = json.loads((out / "network.json").read_text())
    assert kept["blend"] == record["blend"]
    tp.run_tract(replace(cfg, metric="direction"))
    assert json.loads((out / "network.json").read_text())["blend"]["colour"] == "direction"


def test_a_turntable_after_a_figure_keeps_the_figures_record(
    tmp_path, monkeypatch, three
):
    from dataclasses import replace

    from tit.blender import tract_publication as tp

    def writer(manifest_path, *rest):
        manifest = json.loads(Path(manifest_path).read_text())
        base = Path(manifest_path).parent / manifest["output_dir"]
        if manifest["stills"]:
            (base / "ti_max.png").write_bytes(b"png")
        if manifest["turntable"]:
            (base / "ti_max_turntable.mp4").write_bytes(b"mp4")

    _run_tract_project(tmp_path, monkeypatch, three, writer)
    cfg = _selection_config()
    out = Path(tp.run_tract(cfg))
    tp.run_tract(replace(cfg, stills=False, turntable=True))
    record = json.loads((out / "network.json").read_text())
    assert record["colours"]["ti_max"]["files"] == [
        "ti_max.png",
        "ti_max_turntable.mp4",
    ]
    assert set(record["metrics"]["images"]) == {"ti_max.png", "ti_max_turntable.mp4"}
    # A file gone from the folder leaves the record with the next render.
    (out / "ti_max_turntable.mp4").unlink()
    tp.run_tract(cfg)
    record = json.loads((out / "network.json").read_text())
    assert record["colours"]["ti_max"]["files"] == ["ti_max.png"]
    assert set(record["metrics"]["images"]) == {"ti_max.png"}


def test_a_turntable_opening_in_direction_colours_carries_both_keys(
    tmp_path, monkeypatch, three
):
    from tit.blender import tract_publication as tp

    def writer(manifest_path, *rest):
        _still_writer(manifest_path)
        base = Path(manifest_path).parent / ".."
        (base / "ti_max_turntable.mp4").write_bytes(b"mp4")

    _run_tract_project(tmp_path, monkeypatch, three, writer)
    out = Path(tp.run_tract(_selection_config(turntable=True, turntable_crossfade=True)))
    images = json.loads((out / "network.json").read_text())["metrics"]["images"]
    video = images["ti_max_turntable.mp4"]
    assert video["colour_key"]["green"] == "anterior – posterior"
    assert video["colour_scale"]["units"] == "V/m"
    assert "panels" not in video
    assert "colour_key" not in images["ti_max.png"]


def test_a_bundle_is_kept_when_asked_for(tmp_path, monkeypatch, three):
    from tit.blender import tract_publication as tp

    _run_tract_project(tmp_path, monkeypatch, three, _still_writer)
    out = Path(tp.run_tract(_selection_config(keep_bundle=True)))
    assert (out / "bundle_ti_max" / "manifest.json").exists()


def test_a_failed_render_keeps_its_bundle_and_writes_no_record(
    tmp_path, monkeypatch, three
):
    from tit.blender import tract_publication as tp

    def failing(*args):
        raise RuntimeError("Blender died")

    pm = _run_tract_project(tmp_path, monkeypatch, three, failing)
    with pytest.raises(RuntimeError, match="Blender died"):
        tp.run_tract(_selection_config())
    out = Path(pm.ti_toolbox(), "visual_exports", "sub-x", "s", "networks", "net")
    assert (out / "bundle_ti_max" / "manifest.json").exists()
    assert not (out / "network.json").exists()


def test_a_movie_being_written_is_never_in_the_output_folder(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[1] / "tit" / "blender" / "tract_scene.py"
    spec = importlib.util.spec_from_file_location("tract_scene_movie_test", path)
    scene_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scene_module)
    seen = {}
    monkeypatch.setattr(
        scene_module, "video_output", lambda scene, stem, fps: seen.update(stem=stem)
    )

    def renders(fail):
        def render(animation=True):
            # Blender names the movie after the stem and the frame range.
            Path(seen["stem"] + "0001-0096.mp4").write_bytes(b"movie")
            assert os.listdir(tmp_path) == []
            if fail:
                raise RuntimeError("killed mid-movie")

        return SimpleNamespace(
            ops=SimpleNamespace(render=SimpleNamespace(render=render))
        )

    monkeypatch.setitem(sys.modules, "bpy", renders(True))
    with pytest.raises(RuntimeError):
        scene_module._render_movie(None, str(tmp_path), "ti_max_turntable")
    assert os.listdir(tmp_path) == []
    assert not os.path.exists(os.path.dirname(seen["stem"]))

    monkeypatch.setitem(sys.modules, "bpy", renders(False))
    final = scene_module._render_movie(None, str(tmp_path), "ti_max_turntable")
    assert os.listdir(tmp_path) == ["ti_max_turntable.mp4"]
    assert Path(final).read_bytes() == b"movie"


def test_a_network_drawn_in_part_is_an_even_sample_that_says_so(three):
    from tit.blender import tract_publication as tp

    three.dps["edge_id"] = np.zeros(3, dtype=np.int64)
    edges = {0: {"region_a": "lh.a", "region_b": "lh.b"}}
    picks = tp._picked(three, tp._edge_ids(edges, [["lh.b", "lh.a"]]))
    assert picks.tolist() == [0, 1, 2]  # either way round
    assert "(1 drawn, evenly sampled)" in tp.sequence_caption("n", three.n, 1)


def test_absent_options_keep_the_final_figure_and_no_scene():
    from tit.blender.config import TractVisualConfig

    cfg = TractVisualConfig(subject_id="x", simulation_name="s")
    assert (
        cfg.quality == "final"
        and cfg.stills
        and not cfg.export_blend
        and not cfg.thalamocortical_sequence
    )


def test_sequence_networks_share_one_window_over_both(three):
    from tit.blender.config import TractVisualConfig
    from tit.blender.tract_publication import HIGHLIGHT_LEVEL, sequence_configs

    # Streamline 0 ends in a frontal parcel, 1 in a posterior one, 2 joins neither network.
    three.dps["edge_id"] = np.array([10, 20, 30])
    three.dpv["ti_max"] = np.arange(len(three.points), dtype=np.float32)
    edges = {
        10: {"region_a": "Left-Thalamus-Proper", "region_b": "lh.superiorfrontal"},
        20: {"region_a": "rh.precuneus", "region_b": "Right-Thalamus-Proper"},
        30: {"region_a": "lh.superiorfrontal", "region_b": "rh.precuneus"},
    }
    cfg = TractVisualConfig(
        subject_id="x",
        simulation_name="s",
        thalamocortical_sequence=True,
        stills=False,
        quality="preview",
    )
    nets = sequence_configs(cfg, three, edges)

    assert list(nets) == ["frontal", "posterior"]  # the order the video plays them in
    in_network = three.offsets[
        2
    ]  # streamlines 0 and 1, whose ti_max is 0 .. in_network - 1
    expected = np.percentile(np.arange(in_network, dtype=np.float32), 99)
    for key, net in nets.items():
        assert net.vmax_v_per_m == pytest.approx(expected)
        assert net.highlight_regions == net.network_from
        assert net.prune_keep_fraction == 0.15 and net.turntable_crossfade
        assert net.metric == "ti_max" and net.quality == "preview"
    assert "lh.superiorfrontal" in nets["frontal"].network_to
    assert "rh.precuneus" in nets["posterior"].network_to
    assert not set(nets["frontal"].network_to) & set(nets["posterior"].network_to)
    assert HIGHLIGHT_LEVEL == 0.4  # the approved glow (8db67690)


def test_sequence_without_a_thalamocortical_edge_says_so(three):
    from tit.blender.config import TractVisualConfig
    from tit.blender.tract_publication import sequence_configs

    three.dps["edge_id"] = np.array([1, 1, 1])
    edges = {1: {"region_a": "lh.superiorfrontal", "region_b": "rh.precuneus"}}
    cfg = TractVisualConfig(
        subject_id="x", simulation_name="s", thalamocortical_sequence=True, stills=False
    )
    with pytest.raises(ValueError, match="no streamline joins the thalami"):
        sequence_configs(cfg, three, edges)
