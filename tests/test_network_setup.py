"""A named network's automatic render setup, its presets, names and sidecar numbers (2026-11-05).

What this pins
    Each rule of ``tit.blender.network_setup.resolve_network_setup`` from counts written here,
    ``tit.tract.presets`` on a synthetic network, the file names that let networks coexist, the
    figure's panels and scale, and ``network.json``'s medians against what the assess stage reports.

Where the numbers come from
    Counts per edge are authored in this file. The posterior figures in
    ``test_the_reference_network_keeps_its_approved_look`` are the sub-CHN edge table of
    2026-11-05 proof-of-concept run on that subject: 756 + 24 from the left thalamus, 167 + 651
    from the right, 1,598 in all. Arc-length means are worked by hand from the trapezoid rule and
    checked against ``tit.tract.geometry.streamline_stats``, the assess stage's own statistic.

Reproduce: ``.venv/bin/python -m pytest tests/test_network_setup.py -q``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from tit.blender import tract_data as td
from tit.blender.config import TractVisualConfig
from tit.blender.network_setup import (
    PANELS,
    REFERENCE_STREAMLINES,
    SHELL_MIN_STREAMLINES,
    STREAMLINE_BUDGET,
    TUBE_MAX_WIDENING,
    TUBE_RADIUS_MM,
    region_hemi,
    resolve_network_setup,
)
from tit.blender.tract_publication import (
    bundle_folder,
    image_metrics,
    montage_record,
    network_medians,
    network_output_dir,
    network_slug,
    planned_outputs,
    region_counts,
    replaced_outputs,
    sequence_caption,
)
from tit.tract import geometry
from tit.tract.config import Selection
from tit.tract.presets import PRESETS, resolve_preset

THALAMI = ["Left-Thalamus-Proper", "Right-Thalamus-Proper"]


def net(pairs, seeds=(), name="net") -> Selection:
    return Selection(
        name=name, kind="edges", regions=list(seeds), pairs=[list(p) for p in pairs]
    )


def setup(counts, seeds=(), overrides=None, name="net"):
    return resolve_network_setup(net(counts, seeds, name), counts, overrides)


def test_the_reference_network_keeps_its_approved_look() -> None:
    # Report 1e, split evenly over one parcel per side: what matters is who holds the ends.
    counts = {
        ("Left-Thalamus-Proper", "lh.postcentral"): 756,
        ("Left-Thalamus-Proper", "rh.postcentral"): 24,
        ("Right-Thalamus-Proper", "lh.postcentral"): 167,
        ("Right-Thalamus-Proper", "rh.postcentral"): 651,
    }
    out = setup(counts, THALAMI, name="posterior_thalamocortical")
    values = out["values"]
    assert out["n_streamlines"] == out["n_drawn"] == REFERENCE_STREAMLINES
    assert values["highlight_regions"] == THALAMI
    assert values["iso_shell_percentile"] == 95.0
    assert values["lateral_side"] == -1  # bilateral
    assert values["tube_radius_mm"] == TUBE_RADIUS_MM
    assert values["vmax_v_per_m"] is None


def test_the_side_shown_is_the_side_holding_more_ends() -> None:
    assert (
        setup({("lh.insula", "lh.precuneus"): 9, ("rh.insula", "Brain-Stem"): 3})[
            "values"
        ]["lateral_side"]
        == -1
    )
    assert (
        setup({("rh.insula", "rh.precuneus"): 9, ("lh.insula", "Brain-Stem"): 3})[
            "values"
        ]["lateral_side"]
        == 1
    )


def test_a_tie_shows_the_left_side_whatever_order_the_pairs_came_in() -> None:
    assert setup({("lh.insula", "rh.insula"): 5})["values"]["lateral_side"] == -1


def test_a_bilateral_network_shows_the_left_even_with_more_ends_on_the_right() -> None:
    # 100 ends: 25 left and 75 right is bilateral, 24 and 76 is not.
    both = {("lh.a", "rh.b"): 25, ("rh.a", "rh.b"): 25}
    assert setup(both)["values"]["lateral_side"] == -1
    one = {("lh.a", "rh.b"): 24, ("rh.a", "rh.b"): 26}
    assert setup(one)["values"]["lateral_side"] == 1


def test_a_midline_network_counts_as_bilateral() -> None:
    assert setup({("Brain-Stem", "Brain-Stem"): 5})["values"]["lateral_side"] == -1


def test_seeds_are_highlighted_only_when_they_hold_streamlines() -> None:
    counts = {("Left-Hippocampus", "lh.entorhinal"): 40}
    values = setup(counts, ["Left-Hippocampus", "Right-Hippocampus"])["values"]
    assert values["highlight_regions"] == ["Left-Hippocampus"]


def test_without_a_seed_the_busiest_ends_are_highlighted_and_the_tie_is_by_name() -> (
    None
):
    counts = {
        ("lh.a", "lh.b"): 10,
        ("lh.a", "lh.c"): 5,
        ("lh.b", "lh.c"): 1,
        ("lh.d", "lh.e"): 2,
    }
    # ends: a 15, b 11, c 6, d 2, e 2
    assert setup(counts)["values"]["highlight_regions"] == ["lh.a", "lh.b"]
    tied = {("lh.z", "lh.y"): 3}
    assert setup(tied)["values"]["highlight_regions"] == ["lh.y", "lh.z"]


def test_a_dense_network_is_sampled_down_and_says_how_many() -> None:
    out = setup({("lh.a", "lh.b"): STREAMLINE_BUDGET + 1})
    assert out["n_streamlines"] == STREAMLINE_BUDGET + 1
    assert out["n_drawn"] == STREAMLINE_BUDGET


def test_thin_networks_get_wider_tubes_up_to_a_limit() -> None:
    n = REFERENCE_STREAMLINES // 4
    expected = TUBE_RADIUS_MM * (REFERENCE_STREAMLINES / n) ** 0.5
    assert setup({("lh.a", "lh.b"): n})["values"]["tube_radius_mm"] == pytest.approx(
        expected
    )
    assert setup({("lh.a", "lh.b"): 1})["values"]["tube_radius_mm"] == pytest.approx(
        TUBE_RADIUS_MM * TUBE_MAX_WIDENING
    )


def test_the_shell_goes_off_only_under_its_stated_count() -> None:
    assert (
        setup({("lh.a", "lh.b"): SHELL_MIN_STREAMLINES})["values"][
            "iso_shell_percentile"
        ]
        == 95.0
    )
    below = setup({("lh.a", "lh.b"): SHELL_MIN_STREAMLINES - 1})
    assert below["values"]["iso_shell_percentile"] is None
    assert str(SHELL_MIN_STREAMLINES) in below["reasons"]["iso_shell_percentile"]


def test_every_automatic_value_says_why_and_an_override_replaces_it() -> None:
    counts = {("lh.a", "lh.b"): 100}
    auto = setup(counts)
    assert set(auto["reasons"]) == set(auto["values"])
    assert auto["overridden"] == []

    out = setup(
        counts,
        overrides={
            "lateral_side": 1,
            "iso_shell_percentile": None,
            "max_streamlines": 10,
        },
    )
    assert out["overridden"] == [
        "iso_shell_percentile",
        "lateral_side",
        "max_streamlines",
    ]
    assert out["values"]["lateral_side"] == 1
    assert out["values"]["iso_shell_percentile"] is None
    assert out["n_drawn"] == 10
    assert "lateral_side" not in out["reasons"]


def test_the_answer_does_not_depend_on_the_order_of_the_pairs() -> None:
    counts = {("lh.a", "rh.b"): 7, ("lh.c", "rh.d"): 7, ("Brain-Stem", "lh.a"): 1}
    forward = setup(counts)
    backward = resolve_network_setup(
        net(list(reversed(list(counts)))), dict(reversed(list(counts.items())))
    )
    assert forward == backward


def test_an_edge_counted_the_other_way_round_is_the_same_edge() -> None:
    assert (
        resolve_network_setup(net([["a", "b"]]), {("b", "a"): 4})["n_streamlines"] == 4
    )


@pytest.mark.parametrize(
    ("name", "hemi"),
    [
        ("lh.insula", -1),
        ("rh.insula", 1),
        ("Left-Thalamus-Proper", -1),
        ("Right-Hippocampus", 1),
        ("ctx-lh-insula", -1),
        ("Brain-Stem", 0),
    ],
)
def test_region_hemisphere(name: str, hemi: int) -> None:
    assert region_hemi(name) == hemi


# ---- config -----------------------------------------------------------------------------------


def config(**fields) -> TractVisualConfig:
    return TractVisualConfig("CHN", "sim", **fields)


def test_a_selection_draws_pairs_and_is_the_only_network() -> None:
    with pytest.raises(ValueError, match="kind must be 'edges'"):
        config(selection=Selection(name="x", kind="from", regions=["a"]))
    for clash in (
        {"network_from": ["a"], "network_to": ["b"]},
        {"network_bundle": "cst_lh"},
    ):
        with pytest.raises(ValueError, match="selection is the network"):
            config(selection=net([["a", "b"]]), **clash)


@pytest.mark.parametrize(
    "overrides",
    [
        {"nonsense": 1},
        {"views": ["lateral"]},
        {"title": "Mine"},
        {"caption": "Mine"},
        {"region_labels": True},
        {"lateral_side": 0},
        {"max_streamlines": 0},
        {"tube_radius_mm": -1},
        {"vmax_v_per_m": 0},
        {"iso_shell_percentile": 100},
    ],
)
def test_an_override_no_render_can_use_is_refused(overrides) -> None:
    with pytest.raises(ValueError, match="overrides"):
        config(selection=net([["a", "b"]]), overrides=overrides)


def test_overrides_need_a_selection() -> None:
    with pytest.raises(ValueError, match="adjust a selection"):
        config(overrides={"lateral_side": 1})


def test_a_blend_needs_a_render_and_stays_out_of_the_sequence() -> None:
    assert config(export_blend=True, stills=False, turntable=True).export_blend
    with pytest.raises(ValueError, match="export_blend"):
        config(export_blend=True, stills=False)
    with pytest.raises(ValueError, match="runs alone"):
        config(thalamocortical_sequence=True, stills=False, export_blend=True)


# ---- names: networks of one simulation coexist ----------------------------------------------


def test_each_network_has_a_folder_and_each_colour_its_own_bundle() -> None:
    a = config(selection=net([["a", "b"]], name="alpha"), metric="ti_max")
    b = config(selection=net([["a", "b"]], name="beta"), metric="direction")
    assert network_output_dir(a, "/x/sim") == "/x/sim/networks/alpha"
    assert network_output_dir(b, "/x/sim") == "/x/sim/networks/beta"
    assert bundle_folder(a) == "bundle_ti_max"
    assert bundle_folder(b) == "bundle_direction"


def test_a_render_of_the_whole_tractogram_is_the_network_called_all() -> None:
    assert network_output_dir(config(), "/x/sim") == "/x/sim/networks/all"


def test_the_config_can_name_its_own_folder() -> None:
    cfg = config(selection=net([["a", "b"]]), output_dir="/elsewhere")
    assert network_output_dir(cfg, "/x/sim") == "/elsewhere"


def test_a_bundle_and_a_display_name_become_a_safe_folder() -> None:
    assert network_slug(config(network_bundle="cst_lh")) == "cst_lh"
    named = config(
        network_from=["a"], network_to=["b"], network_name="Posterior TC (L)"
    )
    assert network_slug(named) == "Posterior_TC__L_"


def test_the_plan_replaces_exactly_this_colours_figure(tmp_path: Path) -> None:
    cfg = config(selection=net([["a", "b"]], name="alpha"), metric="ti_max", web=False)
    # An older folder's stills are neither planned nor replaced.
    for name in ("ti_max.png", "ti_max_posterior.png", "direction.png"):
        (tmp_path / name).touch()
    assert planned_outputs(cfg) == ["ti_max.png"]
    assert replaced_outputs(cfg, str(tmp_path)) == ["ti_max.png"]
    other = config(selection=net([["a", "b"]]), metric="direction", web=False)
    assert replaced_outputs(other, str(tmp_path)) == ["direction.png"]
    third = config(selection=net([["a", "b"]]), metric="align_index", web=False)
    assert replaced_outputs(third, str(tmp_path)) == []


def test_a_blend_is_planned_and_replaced_only_when_asked_for(tmp_path: Path) -> None:
    (tmp_path / "network.blend").touch()
    assert replaced_outputs(config(web=False, stills=True), str(tmp_path)) == []
    asked = config(web=False, stills=True, export_blend=True)
    assert planned_outputs(asked) == ["ti_along.png", "network.blend"]
    assert replaced_outputs(asked, str(tmp_path)) == ["network.blend"]


def test_a_video_is_replaced_only_when_a_video_is_asked_for(tmp_path: Path) -> None:
    (tmp_path / "ti_along_turntable.mp4").touch()
    assert replaced_outputs(config(web=False), str(tmp_path)) == []
    asked = config(web=False, stills=False, turntable=True)
    assert replaced_outputs(asked, str(tmp_path)) == ["ti_along_turntable.mp4"]


# ---- labels -----------------------------------------------------------------------------------


def _scene_module():
    path = Path(__file__).resolve().parents[1] / "tit" / "blender" / "tract_scene.py"
    spec = importlib.util.spec_from_file_location("tract_scene_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_panels_are_anatomical_views_in_a_fixed_order() -> None:
    scene = _scene_module()
    assert PANELS == ("lateral", "superior", "anterior", "posterior")
    views = scene.panel_views(-1)
    assert set(views) == set(PANELS)

    def screen(view: str):
        _forward, right, up = scene._axes(*views[view])
        return right.tolist(), up.tolist()

    # World axes are +x subject right, +y anterior, +z up.
    assert screen("lateral") == ([0, -1, 0], [0, 0, 1])  # from the left, the nose to the left
    assert screen("superior") == ([1, 0, 0], [0, 1, 0])  # from above, anterior at the top
    assert screen("anterior") == ([-1, 0, 0], [0, 0, 1])  # facing it: its left on our right
    assert screen("posterior") == ([1, 0, 0], [0, 0, 1])  # behind it: its right on our right
    assert scene._axes(*scene.panel_views(1)["lateral"])[1].tolist() == [0, 1, 0]


def test_every_panel_has_one_scale_the_widest_view_sets() -> None:
    scene = _scene_module()
    box = np.array(
        [[x, y, z] for x in (-50, 50) for y in (-100, 100) for z in (0, 150)], float
    )
    views = list(scene.panel_views(-1).values())
    # 200 mm anterior to posterior, the widest of 100, 200 and 150.
    assert scene.figure_scale(box, views, (640, 640)) == pytest.approx(
        200 / scene.PANEL_FILL
    )
    # A panel twice as wide as tall: 200 mm must fit its height, half its width.
    assert scene.figure_scale(box, views, (800, 400)) == pytest.approx(
        400 / scene.PANEL_FILL
    )


def test_panels_tile_left_to_right_and_top_to_bottom_in_a_bottom_first_buffer() -> None:
    scene = _scene_module()
    panels = [np.full((3, 4, 4), float(k), np.float32) for k in range(4)]
    tiled = scene.tile_panels(panels)
    assert tiled.shape == (6, 8, 4)
    # Blender's row 0 is the image's bottom row.
    assert tiled[-1, 0, 0] == 0  # top left: lateral
    assert tiled[-1, -1, 0] == 1  # top right: superior
    assert tiled[0, 0, 0] == 2  # bottom left: anterior
    assert tiled[0, -1, 0] == 3  # bottom right: posterior


# ---- network.json's numbers and the assess stage ----------------------------------------------


def _line(values: list[float]) -> td.Tracts:
    points = np.column_stack(
        [np.arange(len(values)), np.zeros(len(values)), np.zeros(len(values))]
    )
    return td.Tracts(
        points=points.astype(np.float32),
        offsets=np.array([0, len(values)], dtype=np.int64),
        dpv={
            "ti_along": np.array(values, dtype=np.float32),
            "ti_max": np.array(values, dtype=np.float32),
        },
        dps={},
    )


def test_the_arc_length_mean_weighs_the_two_ends_by_half() -> None:
    # (0/2 + 1 + 4/2) / 2 by the trapezoid rule; a plain point mean gives 5/3.
    assert td.arc_length_mean(_line([0.0, 1.0, 4.0]), [0.0, 1.0, 4.0]) == pytest.approx(
        [1.5]
    )


def test_the_arc_length_mean_is_the_statistic_the_assess_stage_reports() -> None:
    rng = np.random.default_rng(3)
    lengths = [5, 2, 40]
    offsets = np.r_[0, np.cumsum(lengths)].astype(np.int64)
    n = int(offsets[-1])
    tracts = td.Tracts(
        points=rng.normal(size=(n, 3)).astype(np.float32),
        offsets=offsets,
        dpv={},
        dps={},
    )
    values = rng.random(n)
    # Uneven h per streamline, even inside one: what geometry.resample writes.
    h = np.array([0.5, 0.25, 0.49])
    assert td.arc_length_mean(tracts, values) == pytest.approx(
        geometry.streamline_stats(values, offsets, h)["mean"]
    )


def test_the_medians_are_the_arc_length_means_and_say_when_a_tractogram_has_no_ti_avg() -> None:
    tracts = _line([0.0, 1.0, 4.0])
    assert network_medians(tracts) == {
        "median_ti_max_v_per_m": 1.5,
        "median_ti_along_v_per_m": 1.5,
        "median_align_index": None,
    }
    # ti_along over ti_avg, each an arc-length mean: 1.5 over 3.
    tracts.dpv["ti_avg"] = np.array([0.0, 2.0, 8.0], np.float32)
    assert network_medians(tracts)["median_align_index"] == 0.5


def test_a_streamline_counts_once_per_region_it_ends_in() -> None:
    tracts = td.Tracts(
        points=np.zeros((6, 3), np.float32) + np.arange(6)[:, None],
        offsets=np.array([0, 2, 4, 6], dtype=np.int64),
        dpv={},
        dps={"edge_id": np.array([0, 0, 1])},
    )
    edges = {
        0: {"region_a": "lh.a", "region_b": "lh.b"},
        1: {"region_a": "lh.a", "region_b": "lh.a"},
    }
    assert list(region_counts(tracts, edges).items()) == [("lh.a", 3), ("lh.b", 2)]


def test_a_montage_keeps_its_labels_and_rounds_coordinates_named_after_themselves() -> None:
    raw = [73.97953796386719, -18.586177825927734, 38.58809280395508]
    assert montage_record(
        [
            {"name": str(raw), "xyz": raw, "channel": 0},
            {"name": "F7", "xyz": [-60.04, 30.0, 10.0], "channel": 1},
        ]
    ) == [
        {"channel": 0, "label": None, "xyz_mm": [74.0, -18.6, 38.6]},
        {"channel": 1, "label": "F7", "xyz_mm": [-60.0, 30.0, 10.0]},
    ]


MANIFEST = {
    "metric": "ti_max",
    "label": "TI_max at the fibre",
    "units": "V/m",
    "vmin": 0.0,
    "vmax": 0.75219,
    "diverging": False,
    "smoothing_mm": 3.0,
    "n_drawn": 552,
    "shell_record": None,
    "lateral_side": 1,
}


def test_an_image_says_how_to_read_its_colours() -> None:
    scale = image_metrics(MANIFEST)
    assert scale["colour_scale"]["range"] == [0.0, 0.7522]
    assert scale["colour_scale"]["colour_map"] == "plasma"
    assert scale["streamlines_drawn"] == 552
    assert scale["lateral_side"] == "right"
    assert "colour_key" not in scale
    key = image_metrics({**MANIFEST, "metric": "direction"})
    assert key["colour_key"] == {
        "red": "left – right",
        "green": "anterior – posterior",
        "blue": "superior – inferior",
    }
    assert "colour_scale" not in key
    log2 = image_metrics(
        {**MANIFEST, "metric": "align_index", "vmin": 0.25, "vmax": 4.0, "diverging": True}
    )
    assert log2["colour_scale"]["colour_map"] == "coolwarm, log2 about 1"


def test_no_metric_is_called_preferred_anywhere_in_a_record() -> None:
    words = str(image_metrics(MANIFEST)) + str(network_medians(_line([1.0, 2.0])))
    for word in ("preferred", "recommended", "compliance", "best"):
        assert word not in words


def test_the_sequence_keeps_the_line_its_video_splits_on() -> None:
    # tract_scene.render_sequence splits on " · n=": what is before names the subject, after the count.
    assert sequence_caption("sub-x", 3, 3) == "sub-x · n=3 streamlines (all drawn)"
    assert sequence_caption("sub-x", 3, 2) == "sub-x · n=3 streamlines (2 drawn, evenly sampled)"


def test_crossing_twice_counts_only_kept_fibres_past_the_margin() -> None:
    from tit.blender.tract_publication import MIDLINE_MARGIN_MM, crossing_twice

    edges = {
        0: {"region_a": "Left-Thalamus-Proper", "region_b": "lh.lingual"},
        1: {"region_a": "Right-Thalamus-Proper", "region_b": "rh.lingual"},
        2: {"region_a": "Brain-Stem", "region_b": "lh.lingual"},
    }
    far = -MIDLINE_MARGIN_MM - 0.5
    near = -MIDLINE_MARGIN_MM + 0.5
    # x along each, midline at 2: left streamlines live below it, right above.
    lines = [
        [
            -10.0,
            2.0 - far,
            -10.0,
        ],  # left, swings past the plane by more than the margin: counted
        [-10.0, 2.0 - near, -10.0],  # left, stays inside the margin
        [10.0, 2.0 + far, 10.0],  # right, swings past: counted
        [10.0, 2.0 + near, 10.0],  # right, stays inside
        [
            -10.0,
            2.0 - far,
            -10.0,
        ],  # one side is midline: no side to cross from, not counted
    ]
    points = np.array([[x, 0.0, 0.0] for line in lines for x in line], dtype=np.float32)
    tracts = td.Tracts(
        points=points,
        offsets=np.arange(0, 16, 3, dtype=np.int64),
        dpv={},
        dps={"edge_id": np.array([0, 0, 1, 1, 2])},
    )
    # Brain-Stem has hemi 0 and lh.lingual -1: its fibres are one-sided by label, and this one counts.
    assert crossing_twice(tracts, edges, 2.0) == 3


# ---- presets ----------------------------------------------------------------------------------


NAMES = [
    "Left-Thalamus-Proper",
    "Right-Thalamus-Proper",
    "lh.postcentral",
    "rh.postcentral",
    "lh.superiorfrontal",
    "Left-Hippocampus",
    "Brain-Stem",
    "lh.precentral",
]
PAIRS = np.array([[0, 2], [1, 2], [1, 3], [0, 4], [5, 2], [6, 7], [2, 3]])
COUNTS = np.array([10, 2, 7, 5, 3, 4, 8])


def preset(preset_id: str) -> dict:
    found = next(p for p in PRESETS if p.id == preset_id)
    return resolve_preset(found, NAMES, PAIRS, COUNTS)


def test_a_thalamocortical_preset_keeps_same_side_edges_and_reports_the_rest() -> None:
    # PAIRS above: L-thal/lh.post 10, R-thal/lh.post 2 (crossed), R-thal/rh.post 7.
    out = preset("posterior_thalamocortical")
    assert out["same_side"] is True
    assert out["pairs"] == [
        ["Left-Thalamus-Proper", "lh.postcentral"],
        ["Right-Thalamus-Proper", "rh.postcentral"],
    ]
    assert out["opposite_pairs"] == [["Right-Thalamus-Proper", "lh.postcentral"]]
    assert out["n_edges"] == 2
    assert out["n_streamlines"] == 17
    assert out["n_opposite"] == 2
    assert out["right_thalamus_to_left_cortex"] == 2
    assert out["left_thalamus_to_right_cortex"] == 0
    assert out["seeds"] == ["Left-Thalamus-Proper", "Right-Thalamus-Proper"]
    assert out["reason"] is None
    assert "lh.superiorparietal" in out["missing"]


def test_the_direction_of_a_crossed_edge_is_read_from_its_labels_either_way_round() -> (
    None
):
    names = [
        "lh.lingual",
        "Left-Thalamus-Proper",
        "Right-Thalamus-Proper",
        "rh.lingual",
    ]
    # Index order puts the cortex first on one edge and the thalamus first on the other two.
    pairs = np.array([[0, 2], [1, 3], [1, 0], [2, 3]])
    counts = np.array([167, 24, 756, 651])
    found = next(p for p in PRESETS if p.id == "posterior_thalamocortical")
    out = resolve_preset(found, names, pairs, counts)
    assert out["n_streamlines"] == 1407
    assert out["n_opposite"] == 191
    assert out["right_thalamus_to_left_cortex"] == 167
    assert out["left_thalamus_to_right_cortex"] == 24
    from tit.tract.presets import opposite_removed

    assert opposite_removed(out, out["pairs"]) == {
        "n_kept": 1407,
        "n_with_opposite": 1598,
        "n_removed": 191,
        "right_thalamus_to_left_cortex": 167,
        "left_thalamus_to_right_cortex": 24,
    }


def test_asking_for_the_opposite_edges_removes_nothing() -> None:
    from tit.tract.presets import opposite_removed

    out = preset("posterior_thalamocortical")
    assert opposite_removed(out, out["pairs"] + out["opposite_pairs"]) is None


def test_only_thalamocortical_presets_are_same_side() -> None:
    assert {p.id for p in PRESETS if p.same_side} == {
        "frontal_thalamocortical",
        "posterior_thalamocortical",
        "temporal_thalamocortical",
    }


def test_other_presets_keep_crossed_edges() -> None:
    names = ["Left-Hippocampus", "lh.lingual", "rh.lingual"]
    pairs = np.array([[0, 1], [0, 2], [1, 2]])
    counts = np.array([5, 3, 9])
    hippocampal = next(p for p in PRESETS if p.id == "hippocampal_cortical")
    out = resolve_preset(hippocampal, names, pairs, counts)
    assert out["n_streamlines"] == 8
    assert out["opposite_pairs"] == []
    commissural = next(p for p in PRESETS if p.id == "interhemispheric_cortical")
    assert resolve_preset(commissural, names, pairs, counts)["pairs"] == [
        ["lh.lingual", "rh.lingual"]
    ]
    from tit.tract.presets import opposite_removed

    assert opposite_removed(out, out["pairs"]) is None


def test_a_preset_works_whichever_way_round_the_edge_is_stored() -> None:
    assert preset("precentral_brainstem")["pairs"] == [["Brain-Stem", "lh.precentral"]]


def test_a_preset_with_labels_but_no_streamline_says_so() -> None:
    names = [*NAMES, "Left-Amygdala"]
    found = next(p for p in PRESETS if p.id == "amygdala_cortical")
    out = resolve_preset(found, names, PAIRS, COUNTS)
    assert out["n_streamlines"] == 0
    assert out["reason"] == "0 streamlines join these regions in this network."


def test_a_preset_whose_side_is_not_in_the_network_names_the_labels() -> None:
    out = preset("cingulate_cortical")
    assert out["pairs"] == []
    assert out["reason"].startswith("These labels are not in this network: ")
    assert "lh.caudalanteriorcingulate" in out["reason"]


def test_preset_ids_can_name_files_and_never_repeat() -> None:
    ids = [p.id for p in PRESETS]
    assert len(set(ids)) == len(ids)
    for preset_id in ids:
        Selection(name=preset_id)  # the name rule


def test_the_posterior_preset_is_the_set_the_thalamocortical_sequence_draws() -> None:
    from tit.blender.tract_publication import THALAMI as sequence_thalami
    from tit.blender.tract_publication import THALAMOCORTICAL

    found = next(p for p in PRESETS if p.id == "posterior_thalamocortical")
    assert (
        list(found.seeds) == sequence_thalami or tuple(found.seeds) == sequence_thalami
    )
    parcels = {
        f"{h}.{parcel}"
        for h in ("lh", "rh")
        for parcel in THALAMOCORTICAL["posterior"][1]
    }
    assert set(found.targets) == parcels
    assert len(parcels) == 18
