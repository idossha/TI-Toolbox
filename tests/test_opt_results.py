"""Tests for tit/opt/ex/results.py -- additional coverage for generate_plots and process_and_save."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.config import ExConfig
from tit.opt.ex.results import (
    generate_plots,
    process_and_save,
)


def _make_results(n=3, roi="region"):
    results = {}
    for i in range(n):
        mesh_name = f"TI_field_E{i}_E{i+1}_and_E{i+2}_E{i+3}.msh"
        results[mesh_name] = {
            f"{roi}_TImax_ROI": 0.5 + i * 0.1,
            f"{roi}_TImean_ROI": 0.3 + i * 0.05,
            f"{roi}_TImean_GM": 0.2 + i * 0.02,
            f"{roi}_Focality": 0.8 - i * 0.1,
            "current_ch1_mA": 1.0,
            "current_ch2_mA": 1.0,
        }
    return results


def _make_config(roi="region"):
    """Build a real ExConfig for testing process_and_save."""
    return ExConfig(
        subject_id="001",
        leadfield_hdf="/lf.hdf5",
        roi_name=roi,
        electrodes=ExConfig.PoolElectrodes(electrodes=["E1", "E2", "E3", "E4"]),
        total_current=2.0,
        current_step=0.5,
        run_name="test_run",
    )


@pytest.mark.unit
class TestGeneratePlots:
    @patch("tit.plotting.ti_metrics.plot_intensity_vs_focality")
    @patch("tit.plotting.ti_metrics.plot_electrode_score_heatmap")
    @patch("tit.plotting.ti_metrics.plot_montage_score_map")
    @patch("tit.plotting.ti_metrics.plot_montage_distributions")
    def test_generates_two_plots(
        self, mock_hist, mock_score_map, mock_heatmap, mock_scatter, tmp_path
    ):
        mock_hist.return_value = str(tmp_path / "hist.png")
        mock_scatter.return_value = str(tmp_path / "scatter.png")

        results = _make_results()
        logger = MagicMock()
        timax = [0.5, 0.6, 0.7]
        timean = [0.3, 0.35, 0.4]
        foc = [0.8, 0.7, 0.6]

        paths = generate_plots(
            results, "region", str(tmp_path), logger, timax, timean, foc
        )
        assert len(paths) == 2
        mock_hist.assert_called_once()
        mock_scatter.assert_called_once()
        mock_score_map.assert_not_called()
        mock_heatmap.assert_not_called()

    @patch("tit.plotting.ti_metrics.plot_intensity_vs_focality")
    @patch("tit.plotting.ti_metrics.plot_electrode_score_heatmap")
    @patch("tit.plotting.ti_metrics.plot_montage_score_map")
    @patch("tit.plotting.ti_metrics.plot_montage_distributions")
    def test_generates_montage_score_plots(
        self, mock_hist, mock_score_map, mock_heatmap, mock_scatter, tmp_path
    ):
        mock_hist.return_value = str(tmp_path / "hist.png")
        mock_scatter.return_value = str(tmp_path / "scatter.png")
        mock_score_map.side_effect = [
            str(tmp_path / "map.png"),
            str(tmp_path / "strength.png"),
            str(tmp_path / "focality.png"),
        ]
        mock_heatmap.return_value = str(tmp_path / "heat.png")

        paths = generate_plots(
            _make_results(),
            "region",
            str(tmp_path),
            MagicMock(),
            [0.5],
            [0.3],
            [0.8],
            eeg_positions_csv=str(tmp_path / "cap.csv"),
        )

        assert str(tmp_path / "map.png") in paths
        assert str(tmp_path / "strength.png") in paths
        assert str(tmp_path / "focality.png") in paths
        assert str(tmp_path / "heat.png") in paths
        assert mock_score_map.call_count == 3
        metric_keys = [
            call.kwargs.get("metric_key", "composite")
            for call in mock_score_map.call_args_list
        ]
        assert metric_keys == ["composite", "timean", "focality"]
        assert [call.kwargs["top_n"] for call in mock_score_map.call_args_list] == [
            150,
            150,
            150,
        ]
        mock_heatmap.assert_called_once()

    def test_empty_values_returns_empty(self, tmp_path):
        logger = MagicMock()
        paths = generate_plots({}, "region", str(tmp_path), logger, [], [], [])
        assert paths == []


@pytest.mark.unit
class TestProcessAndSave:
    @patch("tit.opt.ex.results.generate_plots")
    def test_full_pipeline(self, mock_plots, tmp_path):
        mock_plots.return_value = [str(tmp_path / "plot.png")]

        # ExConfig.__post_init__ appends .csv, so roi_name becomes "region.csv"
        results = _make_results(2, "region.csv")
        config = _make_config("region")
        logger = MagicMock()

        output = process_and_save(results, config, str(tmp_path), logger)

        assert "config_json_path" in output
        assert "csv_path" in output
        assert "best_composite_csv" in output
        assert "visualization_paths" in output
        assert "summary_stats" in output
        assert os.path.exists(output["best_composite_csv"])
        assert output["summary_stats"]["total_montages"] == 2
        assert output["summary_stats"]["timax_range"] is not None
        assert output["summary_stats"]["timean_range"] is not None
        assert output["summary_stats"]["focality_range"] is not None
        assert output["summary_stats"]["composite_range"] is not None

    @patch("tit.opt.ex.results.generate_plots")
    def test_empty_results(self, mock_plots, tmp_path):
        mock_plots.return_value = []

        config = _make_config("region")
        output = process_and_save({}, config, str(tmp_path), MagicMock())

        assert output["summary_stats"]["total_montages"] == 0
        assert output["summary_stats"]["timax_range"] is None
        assert output["best_composite_csv"] is None
