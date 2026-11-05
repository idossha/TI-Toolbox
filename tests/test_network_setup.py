"""A named network's automatic render setup, its presets, names and arc-length caption (2026-11-05).

What this pins
    Each rule of ``tit.blender.network_setup.resolve_network_setup`` from counts written here,
    ``tit.tract.presets`` on a synthetic network, the file names that let networks coexist, the
    per-view label rule, and the caption's agreement with what the assess stage reports.

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
    BILATERAL_VIEWS,
    ONE_SIDE_VIEWS,
    REFERENCE_STREAMLINES,
    SHELL_MIN_STREAMLINES,
    STREAMLINE_BUDGET,
    TUBE_MAX_WIDENING,
    TUBE_RADIUS_MM,
    region_hemi,
    resolve_network_setup,
)
from tit.blender.tract_publication import (
    network_statement,
    output_stem,
    replaced_outputs,
    scene_folder,
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
    assert values["title"] == "Posterior thalamocortical network"
    assert values["highlight_regions"] == THALAMI
    assert values["iso_shell_percentile"] == 95.0
    assert values["lateral_side"] == -1  # 1,703 left ends against 1,493 right
    assert values["views"] == list(BILATERAL_VIEWS)
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


def test_a_network_on_one_side_skips_the_views_that_show_both() -> None:
    assert setup({("lh.insula", "lh.precuneus"): 90, ("lh.insula", "rh.insula"): 10})[
        "values"
    ]["views"] == list(ONE_SIDE_VIEWS)


def test_the_bilateral_rule_is_a_quarter_of_the_ends() -> None:
    # 100 ends: 75 left and 25 right is bilateral, 76 and 24 is not.
    both = {("lh.a", "lh.b"): 25, ("lh.a", "rh.b"): 25}
    assert setup(both)["values"]["views"] == list(BILATERAL_VIEWS)
    one = {("lh.a", "lh.b"): 26, ("lh.a", "rh.b"): 24}
    assert setup(one)["values"]["views"] == list(ONE_SIDE_VIEWS)


def test_a_midline_network_counts_as_bilateral() -> None:
    assert setup({("Brain-Stem", "Brain-Stem"): 5})["values"]["views"] == list(
        BILATERAL_VIEWS
    )


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


def test_regions_are_named_only_while_they_fit() -> None:
    six = {("lh.a", "lh.b"): 1, ("lh.c", "lh.d"): 1, ("lh.e", "lh.f"): 1}
    assert setup(six)["values"]["region_labels"] is True
    seven = {**six, ("lh.g", "lh.a"): 1}
    assert setup(seven)["values"]["region_labels"] is False


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


def test_two_regions_title_in_words_and_a_list_by_its_name() -> None:
    assert setup({("lh.frontalpole", "Brain-Stem"): 9})["values"]["title"] == (
        "Brain-Stem – L frontal pole"
    )
    three = {("lh.a", "lh.b"): 2, ("lh.b", "lh.c"): 1}
    assert setup(three, name="my_regions")["values"]["title"] == "My regions network"


def test_a_title_says_what_the_name_stands_for() -> None:
    long = {("lh.a", "lh.b"): 2, ("lh.b", "lh.c"): 1}
    assert setup(long, name="posterior_thalamocortical_with_opposite")["values"][
        "title"
    ] == ("Posterior thalamocortical network, with opposite-hemisphere connections")
    assert setup(long, name="lh_insula_to_3_regions")["values"]["title"] == (
        "L insula to 3 regions network"
    )
    assert setup(long, name="top_10_by_ti_max_mean")["values"]["title"] == (
        "Top 10 connections by ti_max_mean"
    )


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
            "views": ["posterior"],
            "max_streamlines": 10,
            "title": "Mine",
        },
    )
    assert out["overridden"] == [
        "iso_shell_percentile",
        "lateral_side",
        "max_streamlines",
        "title",
        "views",
    ]
    assert out["values"]["lateral_side"] == 1
    assert out["values"]["iso_shell_percentile"] is None
    assert out["values"]["views"] == ["posterior"]
    assert out["values"]["title"] == "Mine"
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
        {"views": []},
        {"views": ["frontal"]},
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
        config(overrides={"views": ["lateral"]})


def test_posterior_is_a_real_view_and_empty_views_keep_their_old_meaning() -> None:
    assert config(views=["posterior"]).views == ["posterior"]
    assert config().views == []


# ---- names: networks of one simulation coexist ----------------------------------------------


def test_two_networks_and_two_metrics_never_share_a_name() -> None:
    a = config(selection=net([["a", "b"]], name="alpha"), metric="ti_max")
    b = config(selection=net([["a", "b"]], name="beta"), metric="ti_max")
    c = config(selection=net([["a", "b"]], name="alpha"), metric="direction")
    assert output_stem(a) == "CHN_sim_alpha_tract_ti_max"
    assert len({output_stem(a), output_stem(b), output_stem(c)}) == 3
    assert scene_folder(a) == str(Path("tract_scene") / "alpha_ti_max")
    assert len({scene_folder(a), scene_folder(b), scene_folder(c)}) == 3


def test_a_render_of_the_whole_tractogram_keeps_its_old_names() -> None:
    cfg = config(metric="ti_max")
    assert output_stem(cfg) == "CHN_sim_tract_ti_max"
    assert scene_folder(cfg) == "tract_scene"


def test_a_bundle_and_a_display_name_reach_the_file_name_safely() -> None:
    assert output_stem(config(network_bundle="cst_lh", metric="direction")) == (
        "CHN_sim_cst_lh_tract_direction"
    )
    named = config(
        network_from=["a"], network_to=["b"], network_name="Posterior TC (L)"
    )
    assert output_stem(named) == "CHN_sim_Posterior_TC__L__tract_ti_along"


def test_only_this_networks_own_files_count_as_replaced(tmp_path: Path) -> None:
    (
        tmp_path / "CHN_sim_tract_ti_max_lateral.png"
    ).touch()  # a render with no network in its name
    (tmp_path / "CHN_sim_beta_tract_ti_max_lateral.png").touch()
    alpha = config(
        selection=net([["a", "b"]], name="alpha"), metric="ti_max", web=False
    )
    assert replaced_outputs(alpha, str(tmp_path)) == []

    (tmp_path / "CHN_sim_alpha_tract_ti_max_posterior.png").touch()
    assert replaced_outputs(alpha, str(tmp_path)) == [
        "CHN_sim_alpha_tract_ti_max_posterior.png"
    ]
    # Another metric of the same network replaces nothing.
    other = config(
        selection=net([["a", "b"]], name="alpha"), metric="direction", web=False
    )
    assert replaced_outputs(other, str(tmp_path)) == []


def test_a_video_is_replaced_only_when_a_video_is_asked_for(tmp_path: Path) -> None:
    (tmp_path / "CHN_sim_tract_ti_along_turntable.mp4").touch()
    assert replaced_outputs(config(web=False), str(tmp_path)) == []
    asked = config(web=False, stills=False, turntable=True)
    assert replaced_outputs(asked, str(tmp_path)) == [
        "CHN_sim_tract_ti_along_turntable.mp4"
    ]


# ---- labels -----------------------------------------------------------------------------------


def _scene_module():
    path = Path(__file__).resolve().parents[1] / "tit" / "blender" / "tract_scene.py"
    spec = importlib.util.spec_from_file_location("tract_scene_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_side_view_names_only_the_regions_it_faces() -> None:
    labels_for_view = _scene_module().labels_for_view
    left = {"name": "L postcentral", "hemi": -1}
    right = {"name": "R postcentral", "hemi": 1}
    midline = {"name": "Brain-Stem", "hemi": 0}
    unmarked = {"name": "an older bundle's label"}
    every = [left, right, midline, unmarked]
    assert labels_for_view(every, "lateral", 1) == [right, midline, unmarked]
    assert labels_for_view(every, "oblique", -1) == [left, midline, unmarked]
    assert labels_for_view(every, "superior", 1) == every
    assert labels_for_view(every, "posterior", -1) == every


# ---- the caption and the assess stage ---------------------------------------------------------


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


def test_the_caption_quotes_the_assess_statistic_and_states_what_is_drawn() -> None:
    tracts = _line([0.0, 1.0, 4.0])
    assert "median ti_along 1.500 V/m" in network_statement("x", tracts)
    assert "(all drawn)" in network_statement("x", tracts, 1)
    many = td.Tracts(
        points=np.zeros((6, 3), np.float32) + np.arange(6)[:, None],
        offsets=np.array([0, 2, 4, 6], dtype=np.int64),
        dpv={"ti_along": np.ones(6, np.float32), "ti_max": np.ones(6, np.float32)},
        dps={},
    )
    assert "n=3 streamlines (2 drawn, evenly sampled)" in network_statement(
        "x", many, 2
    )


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
    from tit.tract.presets import opposite_removed, removed_sentence

    removed = opposite_removed(out, out["pairs"])
    assert removed_sentence(removed) == (
        "1,407 of 1,598; 191 opposite-hemisphere removed "
        "(right thalamus to left cortex 167, left thalamus to right cortex 24)"
    )


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
