"""Ranking and heatmap arithmetic of the ex-search electrode maps (tit.plotting.ti_metrics).

What this pins (2026-10-22, package p13, task montage-ranking-edge-cases):

* ``_rank_plottable_montages`` drops records whose metric is NaN or infinite (a non-finite
  value has no rank and makes the colour scale meaningless), orders strictly by the metric,
  keeps input order on ties (a stable sort), returns everything when ``top_n`` exceeds the
  record count, ranks 8-electrode mTI records beside 4-electrode ones, and rejects a record
  with an odd number of labels as malformed instead of drawing its first pair.
* ``plot_electrode_score_heatmap`` gives each electrode the sum of the composite indices of
  the montages it appears in and its number of appearances.
* the montage map's colour scale spans the ranked values and stays valid when they are all
  equal.

Expected values are worked out by hand from those definitions in each test (no call into the
code under test computes them). matplotlib is a host mock (tests/conftest.py); the drawing
calls are read back from fresh mock axes.

Reproduce: ``.venv/bin/python -m pytest tests/test_montage_ranking.py -q``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tit.plotting.ti_metrics import _rank_plottable_montages

POSITIONS = {label: (float(i), float(-i)) for i, label in enumerate("ABCDEFGHIJKL")}


def _rec(name: str, electrodes: str, composite) -> dict:
    return {"name": name, "electrodes": list(electrodes), "composite": composite}


def _names(ranked: list[dict]) -> list[str]:
    return [item["name"] for item in ranked]


def _rank(records, top_n=50):
    return _rank_plottable_montages(
        montage_scores=records, positions=POSITIONS, metric_key="composite", top_n=top_n
    )


def test_non_finite_metrics_are_not_ranked():
    records = [
        _rec("nan", "ABCD", math.nan),
        _rec("low", "ABCE", 0.2),
        _rec("inf", "ABCF", math.inf),
        _rec("high", "ABCG", 0.7),
        _rec("ninf", "ABCH", -math.inf),
        _rec("text-nan", "ABCI", "nan"),
    ]
    assert _names(_rank(records)) == ["high", "low"]


def test_order_is_descending_and_ties_keep_input_order():
    records = [
        _rec("a", "ABCD", 0.5),
        _rec("b", "ABCE", 0.9),
        _rec("c", "ABCF", 0.5),
        _rec("d", "ABCG", 0.7),
        _rec("e", "ABCH", 0.5),
    ]
    # By hand: 0.9 > 0.7 > 0.5 = 0.5 = 0.5, the three 0.5s in the order given.
    assert _names(_rank(records)) == ["b", "d", "a", "c", "e"]
    assert _names(_rank(records, top_n=3)) == ["b", "d", "a"]


def test_top_n_larger_than_the_records_returns_them_all():
    records = [_rec("x", "ABCD", 0.1), _rec("y", "EFGH", 0.3)]
    assert _names(_rank(records, top_n=100)) == ["y", "x"]


def test_eight_electrode_records_rank_beside_four_electrode_ones():
    records = [
        _rec("four", "ABCD", 0.4),
        _rec("eight", "ABCDEFGH", 0.6),
        {
            "name": "legacy",
            "e1_plus": "I",
            "e1_minus": "J",
            "e2_plus": "K",
            "e2_minus": "L",
            "composite": 0.5,
        },
    ]
    assert _names(_rank(records)) == ["eight", "legacy", "four"]


def test_an_odd_number_of_labels_is_malformed():
    records = [
        _rec("three", "ABC", 5.0),
        _rec("five", "ABCDE", 4.0),
        _rec("ok", "ABCD", 0.1),
    ]
    assert _names(_rank(records)) == ["ok"]


def test_unknown_labels_and_missing_metrics_are_not_ranked():
    records = [
        _rec("unknown", "ABCZ", 9.0),
        {"name": "no-metric", "electrodes": list("ABCD")},
        _rec("ok", "ABCD", 0.1),
    ]
    assert _names(_rank(records)) == ["ok"]


# ── Drawing (mock axes) ──────────────────────────────────────────────────────────────


@pytest.fixture
def axes(monkeypatch):
    """One fresh mock Axes per ``plt.subplots`` call, and a recording Normalize."""
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    for name in ("matplotlib.image", "matplotlib.patches", "matplotlib.path"):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, MagicMock())
    made: list[MagicMock] = []

    def subplots(*args, **kwargs):
        made.append(MagicMock())
        return MagicMock(), made[-1]

    monkeypatch.setattr(plt, "subplots", subplots)
    monkeypatch.setattr(mpl.colors, "Normalize", MagicMock(name="Normalize"))
    return made


def _net(tmp_path: Path) -> str:
    """An unknown net (no template): the heatmap draws the CSV's own x/y."""
    path = tmp_path / "net.csv"
    path.write_text(
        "".join(
            f"Electrode,{x},{y},50,{label}\n" for label, (x, y) in POSITIONS.items()
        )
    )
    return str(path)


def test_heatmap_sums_composites_and_counts_appearances(tmp_path, axes):
    from tit.plotting.ti_metrics import plot_electrode_score_heatmap

    records = [
        _rec("m1", "ABCD", 0.6),
        _rec("m2", "AEFG", 0.3),
        _rec("m3", "HIJK", 0.1),
        _rec("bad", "ABCD", math.nan),  # must not poison A..D
    ]
    plot_electrode_score_heatmap(
        eeg_positions_csv=_net(tmp_path),
        montage_scores=records,
        output_file=str(tmp_path / "h.png"),
    )
    (ax,) = axes
    (scatter,) = [c for c in ax.scatter.call_args_list if "c" in c.kwargs]
    by_xy = {xy: label for label, xy in POSITIONS.items()}
    labels = [by_xy[xy] for xy in zip(scatter.args[0], scatter.args[1])]
    scores = dict(zip(labels, scatter.kwargs["c"]))
    # Hand sums: A is in m1 and m2; B-D only m1; E-G only m2; H-K only m3; L in none.
    expected = {"A": 0.9, "B": 0.6, "C": 0.6, "D": 0.6, "E": 0.3, "F": 0.3, "G": 0.3}
    expected |= {"H": 0.1, "I": 0.1, "J": 0.1, "K": 0.1}
    assert scores == pytest.approx(expected)
    # Marker size is 60 + 22 x count on a plain x/y layout.
    counts = {label: (s - 60) / 22 for label, s in zip(labels, scatter.kwargs["s"])}
    assert counts == {label: (2 if label == "A" else 1) for label in expected}
    footnote = [c.args[2] for c in ax.text.call_args_list if c.args[:2] == (0.02, 0.02)]
    assert footnote and footnote[0].endswith("(1-2 of 3).")
    assert "Top 3 Montages" in ax.set_title.call_args.args[0]


def _norm_bounds() -> tuple[float, float]:
    import matplotlib as mpl

    kwargs = mpl.colors.Normalize.call_args.kwargs
    return kwargs["vmin"], kwargs["vmax"]


def test_map_colour_scale_spans_the_ranked_values(tmp_path, axes):
    from tit.plotting.ti_metrics import plot_montage_score_map

    records = [
        _rec("m1", "ABCD", 0.9),
        _rec("m2", "EFGH", 0.2),
        _rec("m3", "IJKL", 0.5),
        _rec("nan", "ABCE", math.nan),
        _rec("inf", "ABCF", math.inf),
    ]
    plot_montage_score_map(
        eeg_positions_csv=_net(tmp_path),
        montage_scores=records,
        output_file=str(tmp_path / "m.png"),
    )
    assert _norm_bounds() == (0.2, 0.9)
    (ax,) = axes
    assert ax.set_title.call_args.args[0].startswith("Top 3 ")
    assert [c.args[2] for c in ax.text.call_args_list] == list("ABCD")


@pytest.mark.parametrize("value", [0.25, 3.0])
def test_equal_values_still_give_a_valid_colour_scale(tmp_path, axes, value):
    from tit.plotting.ti_metrics import plot_montage_score_map

    records = [_rec("m1", "ABCD", value), _rec("m2", "EFGH", value)]
    plot_montage_score_map(
        eeg_positions_csv=_net(tmp_path),
        montage_scores=records,
        output_file=str(tmp_path / "m.png"),
    )
    vmin, vmax = _norm_bounds()
    assert vmin == value and vmax > vmin
