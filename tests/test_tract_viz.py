"""Tract visuals: the array layer, the Blender bundle, the web payload and the figure helpers.

What this pins (2026-11-04)
    - :mod:`tit.blender.tract_data` slices, measures, thins and samples concatenated
      streamlines correctly; its colour map is monotone in lightness (CIE L*).
    - :func:`tit.blender.tract_publication.export_scene` passes world coordinates through
      unchanged and writes per-vertex attributes of the right shape and range.
    - :func:`tit.plotting.tract_web.viewer_payload` round-trips positions to 0.005 mm and field
      values to one uint16 step, and a 15 000-streamline page stays under 12 MB.
    - The connectome helpers order hemispheres and pick the top edges.

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

import base64
import json

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


def test_export_scene_passes_coordinates_and_attributes_through(
    tmp_path, three, monkeypatch
):
    from tit.blender import tract_publication as tp
    from tit.blender.config import TractConfig

    seen = {}

    def patches(surface, tracts, start, end, gain, radius=5.0):
        seen["n"] = tracts.n
        return np.zeros(len(surface), np.float32), np.zeros(len(surface), np.float32)

    monkeypatch.setattr(tp, "endpoint_patches", patches)
    cfg = TractConfig(subject_id="x", simulation_name="s", roi_center_mm=[1, 2, 3])
    electrodes = [{"name": "F7", "xyz": [-60.0, 30.0, 10.0], "channel": 0}]
    manifest_path = tp.export_scene(
        cfg,
        three,
        99,
        _sphere(),
        None,
        electrodes,
        str(tmp_path / "b"),
        title="t",
        synthetic=True,
    )
    manifest = json.loads((tmp_path / "b" / "manifest.json").read_text())
    assert manifest_path.endswith("manifest.json")
    assert manifest["n_shown"] == 3 and manifest["n_total"] == 99
    assert manifest["units"] == "V/m" and manifest["electrodes"] == electrodes
    assert manifest["roi"] == {"center": [1, 2, 3], "radius": 10.0}
    assert seen["n"] == 2  # only the edge-assigned streamlines (edge_id -1, 0, 1)
    with np.load(tmp_path / "b" / "tracts.npz") as t:
        n = len(t["points"])
        for key in ("v", "d", "gain"):
            assert t[key].shape == (n,)
        assert t["tangent"].shape == (n, 3)
        assert 0.0 <= t["v"].min() and t["v"].max() <= 1.0
        # Decimation keeps both ends, so each streamline's endpoints are the input's exactly.
        np.testing.assert_array_equal(
            t["points"][t["offsets"][:-1]], three.points[three.offsets[:-1]]
        )
        np.testing.assert_array_equal(
            t["points"][t["offsets"][1:] - 1], three.points[three.offsets[1:] - 1]
        )
        # d is the arc distance from the streamline's ti_along maximum: zero there.
        assert (t["d"][: t["offsets"][1]] == 0).sum() >= 1
    assert manifest["vmax"] == pytest.approx(
        np.percentile(three.dpv["ti_along"], 99.5), rel=1e-5
    )


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
    from tit.blender.config import TractConfig
    from tit.config_io import deserialize_config, serialize_config

    cfg = TractConfig(subject_id="ernie", simulation_name="L_Insula", metric="ti_ratio")
    assert cfg.metric is TractConfig.Metric.TI_RATIO
    data = serialize_config(cfg)
    assert data["_type"] == "TractConfig"
    assert deserialize_config(TractConfig, data) == cfg
    for bad in (
        {"max_streamlines": 0},
        {"roi_center_mm": [1, 2]},
        {"metric": "fa"},
        {"width": 10},
    ):
        with pytest.raises(ValueError):
            TractConfig(subject_id="e", simulation_name="s", **bad)


# -- web viewer ---------------------------------------------------------------------------------


def _decode(text, dtype):
    return np.frombuffer(base64.b64decode(text), dtype=dtype)


def test_viewer_payload_round_trips_positions_and_values(three):
    from tit.plotting.tract_web import viewer_payload

    edges = {0: {"region_a": "lh.a", "region_b": "lh.b"}}
    electrode = {"name": "F7", "xyz": [-60.0, 30.0, 10.0], "channel": 1}
    sphere = _sphere()
    sphere = (
        sphere[0].astype(np.float32),
        sphere[1],
    )  # SimNIBS surfaces arrive as float32
    payload = viewer_payload(three, sphere, [electrode], edges, title="t")
    json.dumps(payload)  # every number a plain float, so the page can embed it
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
        three.dpv["ti_along"][three.offsets[:-1]],
        atol=payload["value_scale"]["ti_along"] / 65535,
    )
    names = {e["id"]: e["name"] for e in payload["edges"]}
    assert names == {-1: "unassigned", 0: "lh.a – lh.b", 1: "edge 1"}
    assert payload["edges"][-1]["id"] == -1  # unassigned listed last


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
    assert metric_units("ti_along_max") == "V/m"
    assert metric_units("count") == "streamlines"
    assert metric_units("ti_ratio_mean") == "1"


# -- TRX reading (the reference reader is checked in tests/numerical) ----------------------------


def test_load_trx_reads_zip_and_directory_and_drops_one_point_streamlines(tmp_path, three):
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
