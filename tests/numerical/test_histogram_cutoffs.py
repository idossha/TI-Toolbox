"""The analyzer histogram draws its cutoffs where results.csv measures them, in the field's unit (2026-10-22).

What this pins
    1. ``save_histogram``'s four focality cutoffs sit at 50/75/90/95 % of the **area-weighted**
       99.9th percentile -- the one ``results.csv`` reports and measures ``focality_*_area``
       against (wiki analyzer.md, "Histogram"). The input has one huge-area low-value node, so
       the weighted and the unweighted 99.9th percentiles differ: before the fix the lines were
       drawn at 50 % ... of ``np.percentile(values, 99.9)`` and missed the table's numbers.
    2. The histogram (x axis, cutoff legend) and the analysis scene's colour bar carry the unit
       ``tit.constants.FIELD_REGISTRY`` gives the field: ``hf_power_density`` is W/m^3,
       ``TI_max`` is V/m.

Where the numbers come from
    A hand calculation. Values ``0.5`` (area 1000) and ``1, 2, ..., 10`` (area 1 each), total
    area 1010: the cumulative area first reaches 99.9 % of 1010 (1008.99) at value 9
    (1000 + 9 = 1009), so the weighted 99.9th percentile is 9 and the cutoffs are 4.5, 6.75,
    8.1 and 8.55. ``np.percentile`` of the same eleven values gives 9.99. The same 9 must come
    out of :meth:`Analyzer._compute_focality_metrics` (the results.csv path). Units: the
    registry's ``units`` strings, ``^3`` shown as a superscript.

Run (in the image; matplotlib is real there)::

    simnibs_python -m pytest tests/numerical/test_histogram_cutoffs.py -q -p no:cacheprovider

Deliberately elsewhere
    The desktop's labels for the same numbers: desktop/tests/unit/results-analysis-view-p33.test.ts.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

VALUES = np.array([0.5, *range(1, 11)], dtype=float)
AREAS = np.array([1000.0, *([1.0] * 10)])
HAND_P999 = 9.0  # see the module docstring
FRACTIONS = (0.5, 0.75, 0.9, 0.95)


@pytest.fixture
def drawn(monkeypatch):
    """Run ``save_histogram`` and hand back the figure it saved (still open)."""
    import tit.plotting._common as common

    figures = []

    def keep(fig, output_file, **kw):
        figures.append(fig)
        fig.savefig(output_file, format=kw.get("fmt"))
        return output_file

    monkeypatch.setattr(common, "savefig_close", keep)

    def run(tmp_path, **kwargs):
        from tit.analyzer.visualizer import save_histogram

        out = save_histogram(
            whole_head_values=VALUES,
            roi_values=VALUES[6:],
            output_dir=tmp_path,
            whole_head_weights=AREAS,
            roi_weights=AREAS[6:],
            **kwargs,
        )
        assert out is not None and out.is_file() and out.stat().st_size > 0
        return figures[-1]

    yield run
    import matplotlib.pyplot as plt

    for fig in figures:
        plt.close(fig)


def _cutoff_xs(fig) -> list[float]:
    ax = fig.axes[0]
    xs = []
    for line in ax.lines:
        x = np.asarray(line.get_xdata(), dtype=float)
        assert x.min() == x.max(), "a cutoff is a vertical line"
        xs.append(float(x[0]))
    return sorted(xs)


def test_the_hand_case_separates_weighted_from_unweighted() -> None:
    assert np.percentile(VALUES, 99.9) > HAND_P999 + 0.5


def test_cutoffs_sit_at_fractions_of_the_weighted_999th_percentile(
    drawn, tmp_path
) -> None:
    fig = drawn(tmp_path)
    expected = [f * HAND_P999 for f in FRACTIONS]
    assert _cutoff_xs(fig) == pytest.approx(expected, abs=1e-12)


def test_cutoffs_match_the_percentile_results_csv_reports(drawn, tmp_path) -> None:
    from tit.analyzer.analyzer import Analyzer

    reported = Analyzer._compute_focality_metrics(None, VALUES, AREAS)
    assert reported["percentile_99_9"] == pytest.approx(HAND_P999)
    fig = drawn(tmp_path)
    assert _cutoff_xs(fig) == pytest.approx(
        [f * reported["percentile_99_9"] for f in FRACTIONS], abs=1e-12
    )


def test_hf_power_density_histogram_is_labelled_in_watts_per_cubic_metre(
    drawn, tmp_path
) -> None:
    fig = drawn(tmp_path, field_name="hf_power_density")
    ax = fig.axes[0]
    assert ax.get_xlabel() == "hf_power_density (W/m³)"
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert len(labels) == 4
    assert all("W/m³," in label for label in labels), labels


def test_ti_max_histogram_stays_in_volts_per_metre(drawn, tmp_path) -> None:
    fig = drawn(tmp_path, field_name="TI_max")
    assert fig.axes[0].get_xlabel() == "TI_max (V/m)"


@pytest.mark.parametrize(
    "field, unit",
    [("hf_power_density", "W/m³"), ("hf_rms", "V/m"), ("TI_max", "V/m"), ("hf_peak", "V/m")],
)
def test_scene_colour_bar_unit_is_the_fields(field, unit) -> None:
    from tit import constants as const
    from tit.analyzer.scene import _meta

    # The registry is the spec: its "^3" is what the superscript shows.
    assert const.get_field_spec(field).units.replace("^3", "³") == unit
    plan = SimpleNamespace(cursor_ras=(1.0, 2.0, 3.0), rule="test", as_dict=dict)
    meta = _meta({}, plan, field, np.array([0.0, 0.2, 0.4]), 0.08, 0.4, "voxels")
    assert meta["field"]["unit"] == unit
    assert meta["field"]["name"] == field
