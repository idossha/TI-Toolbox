"""Tests for:
- run_single_optimization ValueError handling (empty ROI + generic ValueError)
- pareto_sweep.compute_sweep_grid Cartesian product
- pareto_sweep.validate_grid rejection of nonroi_pct >= roi_pct
- pareto_sweep.generate_summary_text output formatting
- pareto_sweep.parse_sweep_line log-line extraction
"""

from __future__ import annotations

from itertools import product
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# run_single_optimization — ValueError handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_single_optimization_empty_roi_returns_inf():
    """zero-size array ValueError => float("inf") with an actionable log message."""
    from tit.opt.flex.multi_start import run_single_optimization

    opt = MagicMock()
    opt.run.side_effect = ValueError(
        "zero-size array to reduction operation maximum which has no identity"
    )

    logger = MagicMock()
    result = run_single_optimization(opt, cpus=1, logger=logger)

    assert result == float("inf")

    all_logged = " ".join(
        str(arg)
        for call in logger.error.call_args_list
        for arg in call.args
    )
    assert (
        "zero-size array" in all_logged
        or "ROI contains no mesh points" in all_logged
        or "Empty ROI" in all_logged
    )


@pytest.mark.unit
def test_run_single_optimization_empty_roi_logs_error():
    """The empty-ROI error path must call logger.error at least once."""
    from tit.opt.flex.multi_start import run_single_optimization

    opt = MagicMock()
    opt.run.side_effect = ValueError(
        "zero-size array to reduction operation maximum which has no identity"
    )

    logger = MagicMock()
    run_single_optimization(opt, cpus=None, logger=logger)

    assert logger.error.called


@pytest.mark.unit
def test_run_single_optimization_generic_valueerror_returns_inf():
    """A ValueError unrelated to empty ROI is also caught and returns inf."""
    from tit.opt.flex.multi_start import run_single_optimization

    opt = MagicMock()
    opt.run.side_effect = ValueError("some other unexpected value error")

    logger = MagicMock()
    result = run_single_optimization(opt, cpus=2, logger=logger)

    assert result == float("inf")
    assert logger.error.called


@pytest.mark.unit
def test_run_single_optimization_success_returns_funvalue():
    """When opt.run() succeeds, the optim_funvalue is returned unchanged."""
    from tit.opt.flex.multi_start import run_single_optimization

    opt = MagicMock()
    opt.run.return_value = None
    opt.optim_funvalue = -37.5

    logger = MagicMock()
    result = run_single_optimization(opt, cpus=4, logger=logger)

    assert result == -37.5
    logger.error.assert_not_called()


# ---------------------------------------------------------------------------
# pareto_sweep.compute_sweep_grid — Cartesian product
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_sweep_grid_cartesian_product():
    """Grid size equals len(roi_pcts) * len(nonroi_pcts)."""
    from tit.opt.flex.pareto_sweep import compute_sweep_grid

    roi_pcts = [80.0, 70.0]
    nonroi_pcts = [20.0, 30.0, 40.0]
    points = compute_sweep_grid(
        roi_pcts, nonroi_pcts, achievable_roi_mean=2.0, base_output_folder="/tmp/sweep"
    )

    assert len(points) == len(roi_pcts) * len(nonroi_pcts)


@pytest.mark.unit
def test_compute_sweep_grid_ordering():
    """roi_pcts is the outer loop; nonroi_pcts is the inner loop."""
    from tit.opt.flex.pareto_sweep import compute_sweep_grid

    roi_pcts = [90.0, 80.0]
    nonroi_pcts = [10.0, 20.0]
    points = compute_sweep_grid(
        roi_pcts, nonroi_pcts, achievable_roi_mean=1.0, base_output_folder="/tmp/sweep"
    )

    expected = list(product(roi_pcts, nonroi_pcts))
    actual = [(p.roi_pct, p.nonroi_pct) for p in points]
    assert actual == expected


@pytest.mark.unit
def test_compute_sweep_grid_threshold_values():
    """Thresholds are correctly scaled from percentages."""
    from tit.opt.flex.pareto_sweep import compute_sweep_grid

    achievable = 2.0
    points = compute_sweep_grid(
        [80.0], [20.0], achievable_roi_mean=achievable, base_output_folder="/tmp/sweep"
    )

    p = points[0]
    assert abs(p.roi_threshold - 0.80 * achievable) < 1e-9
    assert abs(p.nonroi_threshold - 0.20 * achievable) < 1e-9


@pytest.mark.unit
def test_compute_sweep_grid_run_indices():
    """run_index values are consecutive starting from 0."""
    from tit.opt.flex.pareto_sweep import compute_sweep_grid

    points = compute_sweep_grid(
        [80.0, 70.0], [20.0, 30.0], achievable_roi_mean=1.5, base_output_folder="/tmp/sweep"
    )

    indices = [p.run_index for p in points]
    assert indices == list(range(len(points)))


@pytest.mark.unit
def test_compute_sweep_grid_default_status():
    """All generated points start with status 'pending'."""
    from tit.opt.flex.pareto_sweep import compute_sweep_grid

    points = compute_sweep_grid(
        [80.0], [20.0], achievable_roi_mean=1.0, base_output_folder="/tmp/sweep"
    )

    assert all(p.status == "pending" for p in points)


# ---------------------------------------------------------------------------
# pareto_sweep.validate_grid — rejection of bad combinations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_grid_rejects_equal_pcts():
    """nonroi_pct == roi_pct must be rejected."""
    from tit.opt.flex.pareto_sweep import validate_grid

    with pytest.raises(ValueError, match=r"(?i)invalid"):
        validate_grid([50.0], [50.0])


@pytest.mark.unit
def test_validate_grid_rejects_nonroi_greater_than_roi():
    """nonroi_pct > roi_pct must be rejected."""
    from tit.opt.flex.pareto_sweep import validate_grid

    with pytest.raises(ValueError):
        validate_grid([40.0], [60.0])


@pytest.mark.unit
def test_validate_grid_accepts_valid_combinations():
    """All nonroi_pct strictly less than roi_pct passes without exception."""
    from tit.opt.flex.pareto_sweep import validate_grid

    validate_grid([80.0, 70.0], [10.0, 20.0, 30.0])


@pytest.mark.unit
def test_validate_grid_partial_invalid_raises():
    """Even a single invalid pair in a larger grid triggers rejection."""
    from tit.opt.flex.pareto_sweep import validate_grid

    with pytest.raises(ValueError):
        validate_grid([80.0, 70.0], [20.0, 80.0])


# ---------------------------------------------------------------------------
# pareto_sweep.generate_summary_text — formatted output
# ---------------------------------------------------------------------------


def _make_result(roi_pcts=None, nonroi_pcts=None, achievable=2.0):
    """Build a minimal ParetoSweepResult for summary tests."""
    from tit.opt.flex.pareto_sweep import (
        ParetoSweepConfig,
        ParetoSweepResult,
        compute_sweep_grid,
    )

    roi_pcts = roi_pcts or [80.0]
    nonroi_pcts = nonroi_pcts or [20.0]
    config = ParetoSweepConfig(
        roi_pcts=roi_pcts,
        nonroi_pcts=nonroi_pcts,
        achievable_roi_mean=achievable,
        base_output_folder="/tmp/sweep",
    )
    points = compute_sweep_grid(roi_pcts, nonroi_pcts, achievable, "/tmp/sweep")
    return ParetoSweepResult(config=config, points=points)


@pytest.mark.unit
def test_generate_summary_text_contains_header_columns():
    """The summary contains the expected column labels."""
    from tit.opt.flex.pareto_sweep import generate_summary_text

    result = _make_result()
    text = generate_summary_text(result)

    assert "ROI%" in text
    assert "NonROI%" in text
    assert "Score" in text
    assert "Status" in text


@pytest.mark.unit
def test_generate_summary_text_contains_all_points():
    """Each sweep point's roi_pct and nonroi_pct appears in the output."""
    from tit.opt.flex.pareto_sweep import generate_summary_text

    result = _make_result(roi_pcts=[80.0, 70.0], nonroi_pcts=[20.0, 30.0])
    text = generate_summary_text(result)

    for p in result.points:
        assert str(int(p.roi_pct)) in text
        assert str(int(p.nonroi_pct)) in text


@pytest.mark.unit
def test_generate_summary_text_shows_score_when_done():
    """A completed point's focality_score appears as a decimal in the output."""
    from tit.opt.flex.pareto_sweep import generate_summary_text

    result = _make_result()
    result.points[0].focality_score = -12.345
    result.points[0].status = "done"
    text = generate_summary_text(result)

    assert "-12.345" in text


@pytest.mark.unit
def test_generate_summary_text_shows_placeholder_when_no_score():
    """A pending point with no score shows an em-dash placeholder."""
    from tit.opt.flex.pareto_sweep import generate_summary_text

    result = _make_result()
    text = generate_summary_text(result)

    assert "\u2014" in text or "None" in text


# ---------------------------------------------------------------------------
# pareto_sweep.parse_sweep_line — log-line extraction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_sweep_line_primary_pattern():
    """Primary "Final goal function value:" pattern is extracted correctly."""
    from tit.opt.flex.pareto_sweep import parse_sweep_line

    line = "Final goal function value:   -42.123"
    val = parse_sweep_line(line, postproc_key="max_TI")
    assert val == pytest.approx(-42.123)


@pytest.mark.unit
def test_parse_sweep_line_fallback_pattern():
    """Fallback "Goal function value:" pattern is also recognised."""
    from tit.opt.flex.pareto_sweep import parse_sweep_line

    line = "Goal function value at iteration 5:  -7.89"
    val = parse_sweep_line(line, postproc_key="max_TI")
    assert val == pytest.approx(-7.89)


@pytest.mark.unit
def test_parse_sweep_line_returns_none_for_unrelated_line():
    """Lines that do not match either pattern return None."""
    from tit.opt.flex.pareto_sweep import parse_sweep_line

    val = parse_sweep_line("INFO: starting simulation ...", postproc_key="max_TI")
    assert val is None


@pytest.mark.unit
def test_parse_sweep_line_handles_positive_value():
    """Positive function values are parsed correctly."""
    from tit.opt.flex.pareto_sweep import parse_sweep_line

    line = "Final goal function value: +3.14e-2"
    val = parse_sweep_line(line, postproc_key="max_TI")
    assert val == pytest.approx(3.14e-2)


@pytest.mark.unit
def test_parse_sweep_line_case_insensitive():
    """Pattern matching is case-insensitive."""
    from tit.opt.flex.pareto_sweep import parse_sweep_line

    line = "FINAL GOAL FUNCTION VALUE: -99.0"
    val = parse_sweep_line(line, postproc_key="max_TI")
    assert val == pytest.approx(-99.0)
