"""Tests for tit/opt/flex/pareto.py -- Pareto sweep grid, validation, and output."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.flex.pareto import (
    ParetoSweepConfig,
    ParetoSweepResult,
    SweepPoint,
    build_focality_config,
    build_pareto_manifest_data,
    compute_sweep_grid,
    generate_pareto_plot,
    generate_summary_text,
    save_results,
    validate_grid,
    _promote_best_run,
)
from tit.opt.config import FlexConfig, FlexElectrodeConfig, SphericalROI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flex_config(**overrides):
    defaults = dict(
        subject_id="001",
        project_dir="/proj",
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexElectrodeConfig(),
        roi=SphericalROI(x=0, y=0, z=0),
    )
    defaults.update(overrides)
    return FlexConfig(**defaults)


def _make_sweep_result(roi_pcts=None, nonroi_pcts=None, achievable=0.1, base="/tmp/sweep"):
    roi_pcts = roi_pcts or [80.0, 60.0]
    nonroi_pcts = nonroi_pcts or [20.0, 40.0]
    config = ParetoSweepConfig(
        roi_pcts=roi_pcts,
        nonroi_pcts=nonroi_pcts,
        achievable_roi_mean=achievable,
        base_output_folder=base,
    )
    points = compute_sweep_grid(roi_pcts, nonroi_pcts, achievable, base)
    return ParetoSweepResult(config=config, points=points)


# ---------------------------------------------------------------------------
# SweepPoint dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSweepPoint:
    def test_defaults(self):
        sp = SweepPoint(
            roi_pct=80.0,
            nonroi_pct=20.0,
            roi_threshold=0.08,
            nonroi_threshold=0.02,
            run_index=0,
            output_folder="/tmp/01",
        )
        assert sp.focality_score is None
        assert sp.status == "pending"

    def test_with_score(self):
        sp = SweepPoint(
            roi_pct=80.0,
            nonroi_pct=20.0,
            roi_threshold=0.08,
            nonroi_threshold=0.02,
            run_index=0,
            output_folder="/tmp/01",
            focality_score=-0.042,
            status="done",
        )
        assert sp.focality_score == -0.042
        assert sp.status == "done"


# ---------------------------------------------------------------------------
# compute_sweep_grid
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeSweepGrid:
    def test_correct_count(self):
        points = compute_sweep_grid([80, 60], [20, 40], 0.1, "/tmp")
        assert len(points) == 4  # 2x2

    def test_single_combination(self):
        points = compute_sweep_grid([80], [20], 0.1, "/tmp")
        assert len(points) == 1
        p = points[0]
        assert p.roi_pct == 80.0
        assert p.nonroi_pct == 20.0
        assert abs(p.roi_threshold - 0.08) < 1e-9
        assert abs(p.nonroi_threshold - 0.02) < 1e-9
        assert p.run_index == 0

    def test_folder_naming(self):
        points = compute_sweep_grid([80], [20], 0.1, "/base")
        assert points[0].output_folder == "/base/01_roi80_nonroi20"

    def test_ordering_roi_outer_nonroi_inner(self):
        points = compute_sweep_grid([80, 60], [20, 30], 0.1, "/tmp")
        assert points[0].roi_pct == 80.0 and points[0].nonroi_pct == 20.0
        assert points[1].roi_pct == 80.0 and points[1].nonroi_pct == 30.0
        assert points[2].roi_pct == 60.0 and points[2].nonroi_pct == 20.0
        assert points[3].roi_pct == 60.0 and points[3].nonroi_pct == 30.0

    def test_threshold_calculation(self):
        achievable = 0.25
        points = compute_sweep_grid([100], [50], achievable, "/tmp")
        p = points[0]
        assert abs(p.roi_threshold - 0.25) < 1e-9
        assert abs(p.nonroi_threshold - 0.125) < 1e-9

    def test_run_indices_sequential(self):
        points = compute_sweep_grid([80, 70, 60], [20, 30], 0.1, "/tmp")
        for i, p in enumerate(points):
            assert p.run_index == i


# ---------------------------------------------------------------------------
# validate_grid
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateGrid:
    def test_valid_grid_passes(self):
        validate_grid([80, 70], [20, 30])  # no exception

    def test_invalid_nonroi_gte_roi(self):
        with pytest.raises(ValueError, match="Invalid pairs"):
            validate_grid([50], [50])

    def test_invalid_nonroi_gt_roi(self):
        with pytest.raises(ValueError, match="Invalid pairs"):
            validate_grid([30], [50])

    def test_mixed_valid_and_invalid(self):
        with pytest.raises(ValueError, match="Invalid pairs"):
            validate_grid([80, 30], [20, 40])

    def test_all_valid_no_error(self):
        validate_grid([90, 80, 70], [10, 20, 30])


# ---------------------------------------------------------------------------
# build_focality_config
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildFocalityConfig:
    def test_sets_goal_and_thresholds(self):
        base = _make_flex_config()
        point = SweepPoint(
            roi_pct=80, nonroi_pct=20,
            roi_threshold=0.08, nonroi_threshold=0.02,
            run_index=0, output_folder="/out",
        )
        cfg = build_focality_config(base, point)
        assert cfg.goal == "focality"
        assert "0.0200" in cfg.thresholds
        assert "0.0800" in cfg.thresholds
        assert cfg.output_folder == "/out"

    def test_does_not_mutate_base(self):
        base = _make_flex_config()
        original_goal = base.goal
        point = SweepPoint(
            roi_pct=80, nonroi_pct=20,
            roi_threshold=0.08, nonroi_threshold=0.02,
            run_index=0, output_folder="/out",
        )
        build_focality_config(base, point)
        assert base.goal == original_goal


# ---------------------------------------------------------------------------
# build_pareto_manifest_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildParetoManifestData:
    def test_no_done_points(self):
        result = _make_sweep_result()
        data = build_pareto_manifest_data(result)
        assert data["best_point"] is None
        assert len(data["points"]) == 4

    def test_with_done_points(self):
        result = _make_sweep_result()
        result.points[0].status = "done"
        result.points[0].focality_score = -0.05
        result.points[1].status = "done"
        result.points[1].focality_score = -0.03
        data = build_pareto_manifest_data(result)
        assert data["best_point"] is not None
        assert data["best_point"]["focality_score"] == -0.05  # min
        assert data["best_point"]["roi_pct"] == result.points[0].roi_pct

    def test_manifest_data_structure(self):
        result = _make_sweep_result()
        result.points[0].status = "done"
        result.points[0].focality_score = -0.04
        data = build_pareto_manifest_data(result)
        assert "roi_pcts" in data
        assert "nonroi_pcts" in data
        assert "achievable_roi_mean_vm" in data
        assert "points" in data
        for pt in data["points"]:
            assert "roi_pct" in pt
            assert "nonroi_pct" in pt
            assert "status" in pt


# ---------------------------------------------------------------------------
# generate_pareto_plot
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateParetoPlot:
    def test_creates_plot(self, tmp_path):
        result = _make_sweep_result()
        result.points[0].status = "done"
        result.points[0].focality_score = -0.05
        result.points[1].status = "done"
        result.points[1].focality_score = -0.03
        out = str(tmp_path / "plot.png")

        fig_mock = MagicMock()
        ax_mock = MagicMock()
        with patch("tit.opt.flex.pareto.plt") as mock_plt:
            mock_plt.subplots.return_value = (fig_mock, ax_mock)
            mock_plt.cm.tab10.colors = [(1, 0, 0)] * 10
            generate_pareto_plot(result, out)
            fig_mock.savefig.assert_called_once_with(out, dpi=150)
            mock_plt.close.assert_called_once_with(fig_mock)

    def test_no_done_points_still_plots(self, tmp_path):
        result = _make_sweep_result()
        out = str(tmp_path / "plot.png")

        fig_mock = MagicMock()
        ax_mock = MagicMock()
        with patch("tit.opt.flex.pareto.plt") as mock_plt:
            mock_plt.subplots.return_value = (fig_mock, ax_mock)
            mock_plt.cm.tab10.colors = [(1, 0, 0)] * 10
            generate_pareto_plot(result, out)
            fig_mock.savefig.assert_called_once()
            # No plot lines since no done points
            ax_mock.plot.assert_not_called()


# ---------------------------------------------------------------------------
# generate_summary_text
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateSummaryText:
    def test_output_has_header(self):
        result = _make_sweep_result()
        text = generate_summary_text(result)
        assert "ROI%" in text
        assert "NonROI%" in text

    def test_output_includes_all_points(self):
        result = _make_sweep_result()
        text = generate_summary_text(result)
        lines = text.strip().split("\n")
        # 3 header lines (sep, header, sep) + 4 data + 1 trailing sep = 8
        assert len(lines) == 8

    def test_done_point_shows_score(self):
        result = _make_sweep_result()
        result.points[0].status = "done"
        result.points[0].focality_score = -0.042
        text = generate_summary_text(result)
        assert "-0.042" in text

    def test_pending_point_shows_dash(self):
        result = _make_sweep_result()
        text = generate_summary_text(result)
        assert "\u2014" in text  # em dash for None score


# ---------------------------------------------------------------------------
# _promote_best_run
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPromoteBestRun:
    def test_promotes_best_files(self, tmp_path):
        base = str(tmp_path / "sweep")
        os.makedirs(base)
        result = _make_sweep_result(base=base)

        # Create best run output folder with a file
        best_folder = result.points[0].output_folder
        os.makedirs(best_folder)
        (Path(best_folder) / "result.txt").write_text("best")

        result.points[0].status = "done"
        result.points[0].focality_score = -0.05

        promoted = _promote_best_run(result, base)
        assert promoted == best_folder
        assert (Path(base) / "result.txt").read_text() == "best"

    def test_no_done_returns_none(self, tmp_path):
        result = _make_sweep_result(base=str(tmp_path))
        promoted = _promote_best_run(result, str(tmp_path))
        assert promoted is None

    def test_cleans_up_subdirs(self, tmp_path):
        base = str(tmp_path / "sweep")
        os.makedirs(base)
        result = _make_sweep_result(base=base)

        for p in result.points:
            os.makedirs(p.output_folder, exist_ok=True)

        _promote_best_run(result, base)
        for p in result.points:
            assert not os.path.isdir(p.output_folder)

    def test_promotes_directories(self, tmp_path):
        base = str(tmp_path / "sweep")
        os.makedirs(base)
        result = _make_sweep_result(base=base)

        best_folder = result.points[0].output_folder
        os.makedirs(best_folder)
        subdir = Path(best_folder) / "subdir"
        subdir.mkdir()
        (subdir / "data.txt").write_text("nested")

        result.points[0].status = "done"
        result.points[0].focality_score = -0.05

        _promote_best_run(result, base)
        assert (Path(base) / "subdir" / "data.txt").read_text() == "nested"


# ---------------------------------------------------------------------------
# save_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveResults:
    @patch("tit.opt.flex.pareto.generate_pareto_plot")
    def test_saves_json_and_plot(self, mock_plot, tmp_path):
        out = str(tmp_path / "output")
        result = _make_sweep_result(base=out)
        result.points[0].status = "done"
        result.points[0].focality_score = -0.04

        json_path, plot_path = save_results(result, out)
        assert os.path.isfile(json_path)
        assert json_path.endswith("pareto_results.json")
        assert plot_path.endswith("pareto_sweep_plot.png")
        mock_plot.assert_called_once()

    @patch("tit.opt.flex.pareto.generate_pareto_plot")
    def test_json_content(self, mock_plot, tmp_path):
        out = str(tmp_path / "output")
        result = _make_sweep_result(base=out)
        result.points[0].status = "done"
        result.points[0].focality_score = -0.04

        json_path, _ = save_results(result, out)
        with open(json_path) as f:
            data = json.load(f)
        assert "achievable_roi_mean_vm" in data
        assert "points" in data
        assert data["best_run"]["focality_score"] == -0.04

    @patch("tit.opt.flex.pareto.generate_pareto_plot")
    def test_no_done_points_no_best_run(self, mock_plot, tmp_path):
        out = str(tmp_path / "output")
        result = _make_sweep_result(base=out)

        json_path, _ = save_results(result, out)
        with open(json_path) as f:
            data = json.load(f)
        assert data["best_run"] is None
