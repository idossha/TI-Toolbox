"""Tests for tit/opt/flex/drivers.py -- adaptive focality and Pareto sweep drivers.

Focuses on the two audit-bug fixes this module exists to make impossible:

1. Achievable intensity comes from the mean-optimization run's own
   ``FlexResult``, never a filesystem scan for "the newest manifest with
   goal='mean'" (the legacy Qt fallback's bug -- see the module docstring).
2. A Pareto sweep is not driven by any multi-subject loop at all: one
   :class:`FlexConfig` (one ``subject_id``) in, one full sweep out.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.config import FlexConfig, FlexResult
from tit.opt.flex.drivers import run_adaptive_focality, run_pareto_sweep

SphericalROI = FlexConfig.SphericalROI
FlexElectrodeConfig = FlexConfig.ElectrodeConfig


def _make_config(**overrides):
    defaults = dict(
        subject_id="001",
        goal="focality",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexElectrodeConfig(),
        roi=SphericalROI(x=-42, y=-20, z=55, radius=10),
        n_multistart=1,
    )
    defaults.update(overrides)
    return FlexConfig(**defaults)


def _flex_result(best_value, success=True, output_folder="/out"):
    return FlexResult(
        success=success,
        output_folder=output_folder,
        function_values=[best_value],
        best_value=best_value,
        best_run_index=0,
    )


# ---------------------------------------------------------------------------
# run_adaptive_focality
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunAdaptiveFocality:
    def test_two_step_sequence_and_thresholds(self):
        config = _make_config(mode="flex_adaptive")
        assert config.adaptive == FlexConfig.AdaptiveFocalityConfig(
            roi_percentage=80.0, nonroi_percentage=20.0
        )

        mean_result = _flex_result(best_value=-4.0, output_folder="/mean_out")
        focality_result = _flex_result(best_value=-0.5, output_folder="/focality_out")

        with patch(
            "tit.opt.flex.flex.run_flex_search",
            side_effect=[mean_result, focality_result],
        ) as mock_run:
            result = run_adaptive_focality(config)

        assert result is focality_result
        assert mock_run.call_count == 2

        mean_call_config = mock_run.call_args_list[0].args[0]
        focality_call_config = mock_run.call_args_list[1].args[0]

        assert mean_call_config.goal is FlexConfig.OptGoal.MEAN
        assert focality_call_config.goal is FlexConfig.OptGoal.FOCALITY

        # achievable intensity = abs(mean best_value) = 4.0; thresholds are
        # "<nonroi>,<roi>" = 20%/80% of that.
        nonroi_str, roi_str = focality_call_config.thresholds.split(",")
        assert float(nonroi_str) == pytest.approx(0.8)
        assert float(roi_str) == pytest.approx(3.2)

    def test_custom_percentages_used(self):
        config = _make_config(
            mode="flex_adaptive",
            adaptive=FlexConfig.AdaptiveFocalityConfig(
                roi_percentage=90.0, nonroi_percentage=10.0
            ),
        )
        mean_result = _flex_result(best_value=-2.0)
        focality_result = _flex_result(best_value=-0.1)

        with patch(
            "tit.opt.flex.flex.run_flex_search",
            side_effect=[mean_result, focality_result],
        ) as mock_run:
            run_adaptive_focality(config)

        focality_call_config = mock_run.call_args_list[1].args[0]
        nonroi_str, roi_str = focality_call_config.thresholds.split(",")
        assert float(nonroi_str) == pytest.approx(0.2)
        assert float(roi_str) == pytest.approx(1.8)

    def test_mean_failure_short_circuits_before_focality_step(self):
        config = _make_config(mode="flex_adaptive")
        mean_result = _flex_result(best_value=0.0, success=False)

        with patch(
            "tit.opt.flex.flex.run_flex_search", return_value=mean_result
        ) as mock_run:
            result = run_adaptive_focality(config)

        assert result is mean_result
        assert mock_run.call_count == 1

    def test_zero_achievable_intensity_raises(self):
        config = _make_config(mode="flex_adaptive")
        mean_result = _flex_result(best_value=0.0, success=True)

        with patch("tit.opt.flex.flex.run_flex_search", return_value=mean_result):
            with pytest.raises(ValueError, match="achievable ROI intensity"):
                run_adaptive_focality(config)

    def test_never_reads_a_manifest_from_disk(self):
        """Regression test for audit bug #1: the legacy Qt orchestrator's
        fallback scanned the output directory for the newest goal='mean'
        manifest; this driver must never touch tit.opt.flex.manifest at all."""
        config = _make_config(mode="flex_adaptive")
        mean_result = _flex_result(best_value=-4.0)
        focality_result = _flex_result(best_value=-0.5)

        with (
            patch(
                "tit.opt.flex.flex.run_flex_search",
                side_effect=[mean_result, focality_result],
            ),
            patch("tit.opt.flex.manifest.read_manifest") as mock_read_manifest,
        ):
            run_adaptive_focality(config)

        mock_read_manifest.assert_not_called()


# ---------------------------------------------------------------------------
# run_pareto_sweep
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunParetoSweep:
    def _patched_pm(self, tmp_path):
        pm = type("FakePM", (), {"flex_search": lambda self, sid: str(tmp_path)})()
        return pm

    def test_runs_mean_plus_full_grid_and_picks_the_best_point(self, tmp_path):
        config = _make_config(
            mode="flex_pareto",
            output_folder=str(tmp_path / "sweep"),
            pareto=FlexConfig.ParetoSweepConfig(
                roi_pcts=[80.0, 60.0], nonroi_pcts=[20.0, 40.0]
            ),
        )
        mean_result = _flex_result(best_value=-4.0, output_folder="/mean_out")
        # 4 grid points (2 roi_pcts x 2 nonroi_pcts); scores are SimNIBS-style
        # negative goal-function values -- most negative wins.
        point_results = [
            _flex_result(best_value=-0.1),
            _flex_result(best_value=-0.9),  # best (most negative)
            _flex_result(best_value=-0.2),
            _flex_result(best_value=-0.3),
        ]

        with (
            patch(
                "tit.paths.get_path_manager", return_value=self._patched_pm(tmp_path)
            ),
            patch(
                "tit.opt.flex.flex.run_flex_search",
                side_effect=[mean_result, *point_results],
            ) as mock_run,
            patch(
                "tit.opt.flex.pareto.save_results",
                return_value=("/out/pareto_results.json", "/out/pareto_sweep_plot.png"),
            ),
        ):
            result = run_pareto_sweep(config)

        assert mock_run.call_count == 1 + 4
        # All 4 point calls used goal='focality' (tit.opt.flex.pareto.build_focality_config
        # sets the raw string "focality" via a shallow copy that skips __post_init__
        # coercion -- pre-existing, matching behaviour, not something this driver changes).
        for call in mock_run.call_args_list[1:]:
            assert call.args[0].goal in ("focality", FlexConfig.OptGoal.FOCALITY)

        assert result.success is True
        assert result.best_value == pytest.approx(-0.9)
        assert sorted(result.function_values) == pytest.approx(
            sorted(p.best_value for p in point_results)
        )

    def test_mean_failure_returns_immediately_without_running_the_grid(self, tmp_path):
        config = _make_config(mode="flex_pareto", output_folder=str(tmp_path / "sweep"))
        mean_result = _flex_result(best_value=0.0, success=False, output_folder="/mo")

        with (
            patch(
                "tit.paths.get_path_manager", return_value=self._patched_pm(tmp_path)
            ),
            patch(
                "tit.opt.flex.flex.run_flex_search", return_value=mean_result
            ) as mock_run,
        ):
            result = run_pareto_sweep(config)

        assert mock_run.call_count == 1
        assert result.success is False
        assert result.output_folder == "/mo"

    def test_every_point_failing_reports_overall_failure(self, tmp_path):
        config = _make_config(
            mode="flex_pareto",
            output_folder=str(tmp_path / "sweep"),
            pareto=FlexConfig.ParetoSweepConfig(roi_pcts=[80.0], nonroi_pcts=[20.0]),
        )
        mean_result = _flex_result(best_value=-4.0)
        failed_point = _flex_result(best_value=0.0, success=False)

        with (
            patch(
                "tit.paths.get_path_manager", return_value=self._patched_pm(tmp_path)
            ),
            patch(
                "tit.opt.flex.flex.run_flex_search",
                side_effect=[mean_result, failed_point],
            ),
            patch(
                "tit.opt.flex.pareto.save_results",
                return_value=("/out/pareto_results.json", "/out/pareto_sweep_plot.png"),
            ),
        ):
            result = run_pareto_sweep(config)

        assert result.success is False
        assert result.function_values == []
        assert result.best_run_index == -1

    def test_never_reads_a_manifest_from_disk(self, tmp_path):
        """Same regression coverage as the adaptive driver (audit bug #1)."""
        config = _make_config(
            mode="flex_pareto",
            output_folder=str(tmp_path / "sweep"),
            pareto=FlexConfig.ParetoSweepConfig(roi_pcts=[80.0], nonroi_pcts=[20.0]),
        )
        mean_result = _flex_result(best_value=-4.0)
        point_result = _flex_result(best_value=-0.5)

        with (
            patch(
                "tit.paths.get_path_manager", return_value=self._patched_pm(tmp_path)
            ),
            patch(
                "tit.opt.flex.flex.run_flex_search",
                side_effect=[mean_result, point_result],
            ),
            patch(
                "tit.opt.flex.pareto.save_results",
                return_value=("/out/pareto_results.json", "/out/pareto_sweep_plot.png"),
            ),
            patch("tit.opt.flex.manifest.read_manifest") as mock_read_manifest,
        ):
            run_pareto_sweep(config)

        mock_read_manifest.assert_not_called()
