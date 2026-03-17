#!/usr/bin/env python3
"""
Tests for tit/analyzer/group.py — multi-subject group analysis.

Covers: _resolve_output_dir (lines 126-128), _generate_comparison_plot
(lines 155-206), _add_std_lines (lines 211-221), _build_summary_df,
run_group_analysis, and GroupResult.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

# Ensure repo root is on sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.analyzer.analyzer import AnalysisResult
from tit.analyzer.group import (
    GroupResult,
    _build_summary_df,
    _generate_comparison_plot,
    _resolve_output_dir,
    _add_std_lines,
    _NUMERIC_COLS,
    run_group_analysis,
)


# ---------------------------------------------------------------------------
# Helper: build a fake AnalysisResult
# ---------------------------------------------------------------------------


def _make_result(
    roi_mean=0.5,
    roi_max=1.0,
    roi_min=0.1,
    roi_focality=0.8,
    gm_mean=0.6,
    gm_max=1.2,
    normal_mean=0.3,
    normal_max=0.7,
    normal_focality=0.5,
):
    return AnalysisResult(
        field_name="TI_max",
        region_name="test_roi",
        space="mesh",
        analysis_type="spherical",
        roi_mean=roi_mean,
        roi_max=roi_max,
        roi_min=roi_min,
        roi_focality=roi_focality,
        gm_mean=gm_mean,
        gm_max=gm_max,
        normal_mean=normal_mean,
        normal_max=normal_max,
        normal_focality=normal_focality,
        n_elements=100,
        total_area_or_volume=50.0,
    )


# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.unit
class TestGroupResult:
    """GroupResult dataclass."""

    def test_construction(self, tmp_path):
        gr = GroupResult(
            subject_results={"001": _make_result()},
            summary_csv_path=tmp_path / "summary.csv",
            comparison_plot_path=tmp_path / "plot.pdf",
        )
        assert "001" in gr.subject_results
        assert gr.summary_csv_path == tmp_path / "summary.csv"
        assert gr.comparison_plot_path == tmp_path / "plot.pdf"

    def test_none_plot_path(self):
        gr = GroupResult(
            subject_results={},
            summary_csv_path=Path("/fake/summary.csv"),
            comparison_plot_path=None,
        )
        assert gr.comparison_plot_path is None


@pytest.mark.unit
class TestResolveOutputDir:
    """Lines 126-128: _resolve_output_dir resolves via PathManager."""

    @patch("tit.analyzer.group.get_path_manager")
    def test_uses_explicit_output_dir(self, mock_gpm, tmp_path):
        pm = MagicMock()
        mock_gpm.return_value = pm
        out_dir = tmp_path / "custom_out"
        pm.ensure.return_value = str(out_dir)

        result = _resolve_output_dir(str(out_dir))

        assert result == Path(str(out_dir))
        pm.ensure.assert_called_once_with(str(out_dir))

    @patch("tit.analyzer.group.get_path_manager")
    def test_uses_pm_logs_group_when_none(self, mock_gpm, tmp_path):
        pm = MagicMock()
        mock_gpm.return_value = pm
        log_group_path = str(tmp_path / "logs" / "group")
        pm.logs_group.return_value = log_group_path
        pm.ensure.return_value = log_group_path

        result = _resolve_output_dir(None)

        pm.logs_group.assert_called_once()
        pm.ensure.assert_called_once_with(log_group_path)
        assert result == Path(log_group_path)

    @patch("tit.analyzer.group.get_path_manager")
    def test_returns_path_object(self, mock_gpm):
        pm = MagicMock()
        mock_gpm.return_value = pm
        pm.ensure.return_value = "/some/dir"

        result = _resolve_output_dir("/some/dir")
        assert isinstance(result, Path)


@pytest.mark.unit
class TestBuildSummaryDf:
    """_build_summary_df builds a DataFrame with AVERAGE row.

    NOTE: pandas is mocked in conftest, so _build_summary_df returns a
    MagicMock. We test the function is callable and returns something.
    For the actual DataFrame logic, see the pandas-dependent integration tests.
    """

    def test_returns_value(self):
        results = {"001": _make_result(roi_mean=2.0, roi_max=4.0, roi_min=1.0)}
        df = _build_summary_df(results)
        # pandas is mocked, so df is a MagicMock — just ensure no exception
        assert df is not None

    def test_multiple_subjects_returns_value(self):
        results = {
            "001": _make_result(roi_mean=2.0, gm_mean=1.0),
            "002": _make_result(roi_mean=4.0, gm_mean=3.0),
        }
        df = _build_summary_df(results)
        assert df is not None

    def test_none_normal_values_handled(self):
        """None normal values are coerced to 0.0 in the row dict."""
        r = _make_result()
        r.normal_mean = None
        r.normal_max = None
        r.normal_focality = None
        results = {"001": r}
        # Should not raise even with None values
        df = _build_summary_df(results)
        assert df is not None

    def test_numeric_cols_constant(self):
        """_NUMERIC_COLS contains expected column names."""
        assert "ROI_Mean" in _NUMERIC_COLS
        assert "ROI_Max" in _NUMERIC_COLS
        assert "GM_Mean" in _NUMERIC_COLS


@pytest.mark.unit
class TestGenerateComparisonPlot:
    """Lines 155-206: _generate_comparison_plot creates a 2x2 bar chart.

    Since both pandas and matplotlib are mocked, we test via patching
    to verify the function calls the right APIs.
    """

    def test_returns_plot_path(self, tmp_path):
        """Plot path is output_dir / group_comparison.pdf."""
        import matplotlib.pyplot as plt
        # Reset any leaked side_effect from other test files
        plt.savefig.side_effect = None
        plt.savefig.reset_mock()

        mock_fig = MagicMock()
        mock_axes = np.array([[MagicMock(), MagicMock()], [MagicMock(), MagicMock()]])
        plt.subplots.return_value = (mock_fig, mock_axes)

        # Create a minimal mock DataFrame
        mock_df = MagicMock()
        subject_df = MagicMock()
        mock_df.__getitem__ = MagicMock(side_effect=lambda k: subject_df)
        subject_df.__ne__ = MagicMock(return_value=MagicMock())

        plot_path = _generate_comparison_plot(mock_df, tmp_path)
        assert plot_path == tmp_path / "group_comparison.pdf"


@pytest.mark.unit
class TestAddStdLines:
    """Lines 211-221: _add_std_lines draws reference lines on axis."""

    def test_no_lines_when_std_zero(self):
        ax = MagicMock()
        _add_std_lines(ax, mean_val=5.0, std_val=0.0)
        ax.axhline.assert_not_called()

    def test_no_lines_when_std_negative(self):
        ax = MagicMock()
        _add_std_lines(ax, mean_val=5.0, std_val=-1.0)
        ax.axhline.assert_not_called()

    def test_draws_four_lines_for_positive_std(self):
        ax = MagicMock()
        _add_std_lines(ax, mean_val=10.0, std_val=2.0)

        # Should draw 4 lines: +1 sigma, -1 sigma, +2 sigma, -2 sigma
        assert ax.axhline.call_count == 4

        # Verify the y-values of the horizontal lines
        y_values = [c.kwargs["y"] for c in ax.axhline.call_args_list]
        assert pytest.approx(12.0) in y_values  # mean + 1*std
        assert pytest.approx(8.0) in y_values   # mean - 1*std
        assert pytest.approx(14.0) in y_values  # mean + 2*std
        assert pytest.approx(6.0) in y_values   # mean - 2*std

    def test_correct_colors_for_lines(self):
        ax = MagicMock()
        _add_std_lines(ax, mean_val=5.0, std_val=1.0)

        colors = [c.kwargs["color"] for c in ax.axhline.call_args_list]
        # First two lines (1 sigma) are gray, next two (2 sigma) are red
        assert colors[0] == "gray"
        assert colors[1] == "gray"
        assert colors[2] == "red"
        assert colors[3] == "red"


@pytest.mark.unit
class TestRunGroupAnalysis:
    """Integration: run_group_analysis orchestrates per-subject analysis."""

    @patch("tit.analyzer.group._generate_comparison_plot")
    @patch("tit.analyzer.group._build_summary_df")
    @patch("tit.analyzer.group.Analyzer")
    @patch("tit.analyzer.group.add_file_handler")
    @patch("tit.analyzer.group._resolve_output_dir")
    def test_spherical_dispatches_to_analyze_sphere(
        self,
        mock_resolve,
        mock_add_fh,
        mock_analyzer_cls,
        mock_build_df,
        mock_gen_plot,
        tmp_path,
    ):
        mock_resolve.return_value = tmp_path

        fake_result = _make_result()
        mock_instance = MagicMock()
        mock_instance.analyze_sphere.return_value = fake_result
        mock_analyzer_cls.return_value = mock_instance

        mock_df = MagicMock()
        mock_build_df.return_value = mock_df
        mock_gen_plot.return_value = tmp_path / "plot.pdf"

        gr = run_group_analysis(
            subject_ids=["001", "002"],
            simulation="sim1",
            space="mesh",
            analysis_type="spherical",
            center=(10.0, 20.0, 30.0),
            radius=5.0,
            coordinate_space="subject",
        )

        assert isinstance(gr, GroupResult)
        assert len(gr.subject_results) == 2
        assert "001" in gr.subject_results
        assert "002" in gr.subject_results
        assert mock_instance.analyze_sphere.call_count == 2

    @patch("tit.analyzer.group._generate_comparison_plot")
    @patch("tit.analyzer.group._build_summary_df")
    @patch("tit.analyzer.group.Analyzer")
    @patch("tit.analyzer.group.add_file_handler")
    @patch("tit.analyzer.group._resolve_output_dir")
    def test_cortical_dispatches_to_analyze_cortex(
        self,
        mock_resolve,
        mock_add_fh,
        mock_analyzer_cls,
        mock_build_df,
        mock_gen_plot,
        tmp_path,
    ):
        mock_resolve.return_value = tmp_path

        fake_result = _make_result()
        mock_instance = MagicMock()
        mock_instance.analyze_cortex.return_value = fake_result
        mock_analyzer_cls.return_value = mock_instance

        mock_df = MagicMock()
        mock_build_df.return_value = mock_df
        mock_gen_plot.return_value = tmp_path / "plot.pdf"

        gr = run_group_analysis(
            subject_ids=["001"],
            simulation="sim1",
            analysis_type="cortical",
            atlas="DK40",
            region="V1",
        )

        assert isinstance(gr, GroupResult)
        mock_instance.analyze_cortex.assert_called_once()

    @patch("tit.analyzer.group._generate_comparison_plot")
    @patch("tit.analyzer.group._build_summary_df")
    @patch("tit.analyzer.group.Analyzer")
    @patch("tit.analyzer.group.add_file_handler")
    @patch("tit.analyzer.group._resolve_output_dir")
    def test_writes_csv(
        self,
        mock_resolve,
        mock_add_fh,
        mock_analyzer_cls,
        mock_build_df,
        mock_gen_plot,
        tmp_path,
    ):
        mock_resolve.return_value = tmp_path

        fake_result = _make_result()
        mock_instance = MagicMock()
        mock_instance.analyze_sphere.return_value = fake_result
        mock_analyzer_cls.return_value = mock_instance

        mock_df = MagicMock()
        mock_build_df.return_value = mock_df
        mock_gen_plot.return_value = tmp_path / "plot.pdf"

        gr = run_group_analysis(
            subject_ids=["001"],
            simulation="sim1",
            analysis_type="spherical",
            center=(0, 0, 0),
            radius=10.0,
        )

        # CSV should have been written
        assert gr.summary_csv_path == tmp_path / "group_summary.csv"
        mock_df.to_csv.assert_called_once()

    @patch("tit.analyzer.group._generate_comparison_plot")
    @patch("tit.analyzer.group._build_summary_df")
    @patch("tit.analyzer.group.Analyzer")
    @patch("tit.analyzer.group.add_file_handler")
    @patch("tit.analyzer.group._resolve_output_dir")
    def test_uses_custom_output_dir(
        self,
        mock_resolve,
        mock_add_fh,
        mock_analyzer_cls,
        mock_build_df,
        mock_gen_plot,
        tmp_path,
    ):
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        mock_resolve.return_value = custom_dir

        fake_result = _make_result()
        mock_instance = MagicMock()
        mock_instance.analyze_sphere.return_value = fake_result
        mock_analyzer_cls.return_value = mock_instance

        mock_df = MagicMock()
        mock_build_df.return_value = mock_df
        mock_gen_plot.return_value = custom_dir / "plot.pdf"

        gr = run_group_analysis(
            subject_ids=["001"],
            simulation="sim1",
            analysis_type="spherical",
            center=(0, 0, 0),
            radius=5.0,
            output_dir=str(custom_dir),
        )

        assert gr.summary_csv_path == custom_dir / "group_summary.csv"


@pytest.mark.unit
class TestNumericCols:
    """Verify _NUMERIC_COLS constant is complete."""

    def test_all_numeric_cols_present(self):
        expected = {
            "ROI_Mean", "ROI_Max", "ROI_Min", "ROI_Focality",
            "GM_Mean", "GM_Max",
            "Normal_Mean", "Normal_Max", "Normal_Focality",
        }
        assert set(_NUMERIC_COLS) == expected
