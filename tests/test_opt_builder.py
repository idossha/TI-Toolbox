"""Tests for tit/opt/flex/builder.py -- SimNIBS optimization object construction."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure simnibs submodules needed by builder.py are mocked
for mod_name in (
    "simnibs.opt_struct",
    "simnibs.optimization",
    "simnibs.optimization.tes_flex_optimization",
    "simnibs.optimization.tes_flex_optimization.electrode_layout",
):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

from tit.opt.config import FlexConfig

# Convenience aliases for nested types
SphericalROI = FlexConfig.SphericalROI
AtlasROI = FlexConfig.AtlasROI
SubcorticalROI = FlexConfig.SubcorticalROI
FlexElectrodeConfig = FlexConfig.ElectrodeConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    defaults = dict(
        subject_id="001",
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexElectrodeConfig(),
        roi=SphericalROI(x=-42, y=-20, z=55, radius=10),
    )
    defaults.update(overrides)
    return FlexConfig(**defaults)


@pytest.fixture
def builder_env():
    """Set up mocks for build_optimization tests."""
    import simnibs
    from simnibs.optimization.tes_flex_optimization.electrode_layout import (
        ElectrodeArrayPair,
    )

    opt_mock = MagicMock()
    simnibs.opt_struct.TesFlexOptimization.return_value = opt_mock
    ElectrodeArrayPair.return_value = MagicMock()
    ElectrodeArrayPair.reset_mock()

    pm = MagicMock()
    pm.m2m.return_value = "/m2m/001"
    pm.flex_search.return_value = "/flex"
    pm.eeg_positions.return_value = "/eeg"

    return opt_mock, pm, ElectrodeArrayPair


# ---------------------------------------------------------------------------
# build_optimization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildOptimization:
    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_basic_mean_config(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        opt_mock, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(_make_config())
        assert result.goal == "mean"
        assert result.open_in_gmsh is False
        mock_roi.assert_called_once()

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_focality_with_thresholds(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(
            goal="focality", non_roi_method="everything_else", thresholds="0.02,0.08"
        )
        result = build_optimization(config)
        assert result.goal == "focality"
        assert result.threshold == [0.02, 0.08]

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_single_threshold_value(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(
            goal="focality", non_roi_method="everything_else", thresholds="0.5"
        )
        result = build_optimization(config)
        assert result.threshold == 0.5

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_output_folder_from_config(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(_make_config(output_folder="/custom/output"))
        assert result.output_folder == "/custom/output"

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_ellipse_electrode_shape(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, eap = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(
            electrode=FlexElectrodeConfig(shape="ellipse", dimensions=[10.0, 8.0])
        )
        build_optimization(config)
        assert eap.call_count >= 2

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_rectangle_electrode_shape(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(
            electrode=FlexElectrodeConfig(shape="rect", dimensions=[12.0, 8.0])
        )
        build_optimization(config)

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_mapping_enabled(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        opt_mock, pm, _ = builder_env
        opt_mock.run_mapped_electrodes_simulation = False
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(enable_mapping=True, eeg_net="EEG10-10")
        result = build_optimization(config)
        assert result.map_to_net_electrodes is True
        assert result.net_electrode_file == "/eeg/EEG10-10.csv"

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_mapping_accepts_eeg_net_csv_suffix(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        opt_mock, pm, _ = builder_env
        opt_mock.run_mapped_electrodes_simulation = False
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(
            _make_config(enable_mapping=True, eeg_net="EEG10-10.csv")
        )
        assert result.net_electrode_file == "/eeg/EEG10-10.csv"

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_detailed_results(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(_make_config(detailed_results=True))
        assert result.detailed_results is True

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_skin_visualization(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(_make_config(visualize_valid_skin_region=False))
        assert result.visualize_valid_skin_region is True

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_skin_visualization_net(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(
            _make_config(skin_visualization_net="/path/to/net.csv")
        )
        assert result.skin_visualization_net_file == "/path/to/net.csv"

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_skin_region_margin_controls(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(
            _make_config(
                skin_region_margin_mm=20.0,
                avoid_landmark_regions=True,
            )
        )
        assert result.skin_region_margin_mm == 20.0
        assert result.avoid_landmark_regions is True

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_mapping_disabled(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(_make_config(enable_mapping=False))
        assert result.electrode_mapping is None

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_current_conversion(self, mock_gpm, mock_roi, mock_mkdirs, builder_env):
        _, pm, eap = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        pair_mock = MagicMock()
        eap.return_value = pair_mock

        config = _make_config(current_mA=4.0)
        build_optimization(config)

        # current should be 4.0/1000 = 0.004 A
        assert pair_mock.current == [0.004, -0.004]

    @pytest.mark.parametrize(
        "goal_str", ["integral_focality", "auc_focality", "ratio_focality"]
    )
    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_custom_focality_goal_wires_a_callable(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env, goal_str
    ):
        """Regression guard for F5: new goals must bypass SimNIBS' 2-point
        ROC evaluation by becoming a plain Python callable on opt.goal."""
        opt_mock, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(goal=goal_str, non_roi_method="everything_else")
        result = build_optimization(config)

        assert callable(result.goal)
        assert not isinstance(result.goal, str)

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_existing_goals_stay_plain_strings(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        """Byte-identical regression guard: mean/max/focality must remain
        the plain SimNIBS string goal, never routed through the new
        callable path added for F5."""
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        assert build_optimization(_make_config(goal="mean")).goal == "mean"
        assert build_optimization(_make_config(goal="max")).goal == "max"
        assert (
            build_optimization(
                _make_config(goal="focality", non_roi_method="everything_else")
            ).goal
            == "focality"
        )


# ---------------------------------------------------------------------------
# Custom threshold-free focality goals (F5)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCustomFocalityGoalFn:
    """Tests for _make_focality_goal_fn / _ratio_focality / the <2.0 bound."""

    def _opt_with_vol(self, v1=10.0, v2=1000.0):
        opt = MagicMock()
        opt._vol = [v1, v2]
        return opt

    def test_integral_focality_calls_simnibs_measure(self):
        from tit.opt.flex.builder import _make_focality_goal_fn
        from tit.opt.config import FlexConfig

        opt = self._opt_with_vol(v1=10.0, v2=1000.0)
        measures = MagicMock()
        measures.integral_focality.return_value = 0.02

        goal_fn = _make_focality_goal_fn(
            FlexConfig.OptGoal.INTEGRAL_FOCALITY, opt, measures
        )
        e1 = np.array([0.3, 0.35, 0.32])
        e2 = np.array([0.05, 0.06, 0.04])
        value = goal_fn([[e1, e2]])

        measures.integral_focality.assert_called_once()
        kwargs = measures.integral_focality.call_args.kwargs
        assert kwargs["v1"] == 10.0
        assert kwargs["v2"] == 1000.0
        np.testing.assert_allclose(kwargs["e1"], e1)
        np.testing.assert_allclose(kwargs["e2"], e2)
        assert value == pytest.approx(-0.02)

    def test_auc_focality_calls_simnibs_measure(self):
        from tit.opt.flex.builder import _make_focality_goal_fn
        from tit.opt.config import FlexConfig

        opt = self._opt_with_vol()
        measures = MagicMock()
        measures.AUC.return_value = 0.83

        goal_fn = _make_focality_goal_fn(FlexConfig.OptGoal.AUC_FOCALITY, opt, measures)
        e1 = np.array([0.3, 0.35])
        e2 = np.array([0.05, 0.06])
        value = goal_fn([[e1, e2]])

        measures.AUC.assert_called_once()
        assert value == pytest.approx(-0.83)

    def test_ratio_focality_does_not_touch_simnibs_measures(self):
        from tit.opt.flex.builder import _make_focality_goal_fn
        from tit.opt.config import FlexConfig

        opt = self._opt_with_vol(v1=10.0, v2=10.0)
        measures = MagicMock()

        goal_fn = _make_focality_goal_fn(
            FlexConfig.OptGoal.RATIO_FOCALITY, opt, measures
        )
        e1 = np.array([0.4, 0.4])  # mean 0.4
        e2 = np.array([0.1, 0.1])  # mean 0.1
        value = goal_fn([[e1, e2]])

        measures.integral_focality.assert_not_called()
        measures.AUC.assert_not_called()
        # v1 == v2 == 10 -> reduces to the plain mean ratio, negated: -4.0
        assert value == pytest.approx(-4.0)

    @pytest.mark.parametrize(
        "goal, raw_score",
        [
            ("integral_focality", 50.0),  # deliberately huge, unrealistic score
            ("auc_focality", 1.0),  # AUC's theoretical maximum
            ("ratio_focality", 1e6),  # denominator near zero
        ],
    )
    def test_custom_goal_values_stay_below_invalid_penalty(self, goal, raw_score):
        """SimNIBS returns a flat 2.0 for overlapping/invalid placements
        without running a FEM solve. A custom goal that can reach >= 2.0
        for a *valid* montage would make differential evolution prefer
        invalid, overlapping electrode placements -- this must never
        happen, however extreme the underlying score."""
        from tit.opt.flex.builder import _make_focality_goal_fn
        from tit.opt.config import FlexConfig

        opt = self._opt_with_vol(v1=1.0, v2=1.0)
        measures = MagicMock()
        measures.integral_focality.return_value = raw_score
        measures.AUC.return_value = raw_score

        goal_fn = _make_focality_goal_fn(FlexConfig.OptGoal(goal), opt, measures)
        e1 = np.array([raw_score, raw_score])
        e2 = np.array([1.0, 1.0])
        value = goal_fn([[e1, e2]])

        assert value < 2.0

    def test_ratio_focality_guards_against_zero_denominator(self):
        from tit.opt.flex.builder import _ratio_focality

        # non-ROI mean field is exactly zero -> must not raise ZeroDivisionError
        result = _ratio_focality(
            e1=np.array([0.3, 0.3]), e2=np.array([0.0, 0.0]), v1=1.0, v2=1.0
        )
        assert np.isfinite(result)
        assert result > 0

    def test_bound_below_invalid_penalty(self):
        from tit.opt.flex.builder import _bound_below_invalid_penalty

        assert _bound_below_invalid_penalty(-5.0) == -5.0
        assert _bound_below_invalid_penalty(0.0) == 0.0
        assert _bound_below_invalid_penalty(1.95) < 2.0
        assert _bound_below_invalid_penalty(1_000_000.0) < 2.0


# ---------------------------------------------------------------------------
# F5 evidence: FOCALITY goes flat at deep targets, RATIO_FOCALITY does not
# ---------------------------------------------------------------------------


def _mirrors_simnibs_roc_focality(e1: np.ndarray, e2: np.ndarray, t_nonroi, t_roi):
    """Byte-for-byte mirror of ``measures.ROC(e1, e2, [t_nonroi, t_roi],
    focal=True)`` composed with ``compute_goal``'s ``-100*(sqrt(2)-ROCval)``
    transform (see F5, ``tracks/active/mti-focality-core.md``).

    SimNIBS is not installed on the host test environment (only inside the
    Docker container -- see ``memory/feedback_verify_in_container.md``), so
    this test-only helper reproduces the well-defined, ~15-line 2-point ROC
    formula locally rather than importing the real
    ``simnibs.optimization.tes_flex_optimization.measures`` module. It was
    transcribed from and cross-checked against the vendored SimNIBS source
    at ``resources/map-electrodes/tes_flex_optimization.py`` /
    ``.../measures.py`` inside the container image. Production code
    (``tit.opt.flex.builder``) never uses this helper -- it always calls the
    real SimNIBS module at runtime.
    """
    threshold_array = np.array([t_nonroi, t_roi], dtype=float)
    sensitivity = np.array([np.sum(e1 >= t) / len(e1) for t in threshold_array])
    specificity_inv = np.array([np.sum(e2 >= t) / len(e2) for t in threshold_array])

    sens_thresh = sensitivity[1]  # threshold_array is already sorted
    spec_inv_thresh = specificity_inv[0]

    roc_val = float(np.linalg.norm([spec_inv_thresh, sens_thresh - 1]))
    return -100 * (np.sqrt(2) - roc_val)


@pytest.mark.unit
class TestF5FlatObjectiveEvidence:
    """Demonstrates the F5 defect and its fix with synthetic e_pp arrays --
    no FEM solve required (see the track's Phase 3 acceptance criteria)."""

    def test_focality_flat_ratio_focality_not_flat(self):
        from tit.opt.flex.builder import _ratio_focality

        rng = np.random.default_rng(42)
        t_roi, t_nonroi = 0.2, 0.1
        n_placements = 25

        focality_values = []
        ratio_values = []
        for _ in range(n_placements):
            # Deep-target ROI (e.g. thalamus): achievable envelope is
            # 0.1-0.7 V/m, but here always < t_ROI=0.2 -- reproducing the
            # jointly-infeasible regime F5 describes.
            e1 = rng.uniform(0.10, 0.19, size=200)
            # "everything_else" non-ROI (whole cortex): always >= t_nonROI
            # =0.1, dominated by near-electrode superficial cortex.
            e2 = rng.uniform(0.10, 0.90, size=2000)

            focality_values.append(
                _mirrors_simnibs_roc_focality(e1, e2, t_nonroi, t_roi)
            )
            # v1 == v2 so this is directly the Bruno-2026-comparable ratio.
            ratio_values.append(-_ratio_focality(e1, e2, v1=1.0, v2=1.0))

        focality_std = float(np.std(focality_values))
        ratio_std = float(np.std(ratio_values))

        # Built-in "focality" collapses to a bit-identical constant once
        # both thresholds are jointly infeasible: no gradient for DE.
        assert focality_std < 1e-9
        # RATIO_FOCALITY keeps tracking the underlying field difference
        # between placements.
        assert ratio_std > 1e-3


# ---------------------------------------------------------------------------
# configure_optimizer_options
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigureOptimizerOptions:
    def test_sets_max_iterations(self):
        from tit.opt.flex.builder import configure_optimizer_options

        opt = MagicMock()
        opt._optimizer_options_std = {}
        configure_optimizer_options(opt, _make_config(max_iterations=200), MagicMock())
        assert opt._optimizer_options_std["maxiter"] == 200

    def test_sets_population_size(self):
        from tit.opt.flex.builder import configure_optimizer_options

        opt = MagicMock()
        opt._optimizer_options_std = {}
        configure_optimizer_options(opt, _make_config(population_size=30), MagicMock())
        assert opt._optimizer_options_std["popsize"] == 30

    def test_sets_tolerance(self):
        from tit.opt.flex.builder import configure_optimizer_options

        opt = MagicMock()
        opt._optimizer_options_std = {}
        configure_optimizer_options(opt, _make_config(tolerance=0.001), MagicMock())
        assert opt._optimizer_options_std["tol"] == 0.001

    def test_sets_mutation_single(self):
        from tit.opt.flex.builder import configure_optimizer_options

        opt = MagicMock()
        opt._optimizer_options_std = {}
        configure_optimizer_options(opt, _make_config(mutation="0.7"), MagicMock())
        assert opt._optimizer_options_std["mutation"] == 0.7

    def test_sets_mutation_tuple(self):
        from tit.opt.flex.builder import configure_optimizer_options

        opt = MagicMock()
        opt._optimizer_options_std = {}
        configure_optimizer_options(opt, _make_config(mutation="0.5, 1.0"), MagicMock())
        assert opt._optimizer_options_std["mutation"] == [0.5, 1.0]

    def test_sets_recombination(self):
        from tit.opt.flex.builder import configure_optimizer_options

        opt = MagicMock()
        opt._optimizer_options_std = {}
        configure_optimizer_options(opt, _make_config(recombination=0.9), MagicMock())
        assert opt._optimizer_options_std["recombination"] == 0.9

    def test_skips_none_values(self):
        from tit.opt.flex.builder import configure_optimizer_options

        opt = MagicMock()
        opt._optimizer_options_std = {}
        configure_optimizer_options(opt, _make_config(), MagicMock())
        assert opt._optimizer_options_std == {}


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateReport:
    def _patch_report_gen(self):
        """Context manager that patches FlexSearchReportGenerator at the import site."""
        mock_gen = MagicMock()
        mock_gen.generate.return_value = "/fake/report.html"
        mock_cls = MagicMock(return_value=mock_gen)
        # Patch at the module that the function imports from
        import tit.reporting as reporting_mod

        return (
            patch.object(
                reporting_mod, "FlexSearchReportGenerator", mock_cls, create=True
            ),
            mock_gen,
        )

    def test_generate_report_basic(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            pos_path = tmp_path / "electrode_positions.json"
            pos_path.write_text(
                json.dumps(
                    {
                        "optimized_positions": [[1, 2, 3]],
                        "channel_array_indices": [0, 1],
                    }
                )
            )

            generate_report(
                _make_config(),
                2,
                np.array([-0.025, -0.030]),
                1,
                str(tmp_path),
                MagicMock(),
            )
            mock_gen.set_configuration.assert_called_once()
            mock_gen.set_roi_info.assert_called_once()
            mock_gen.generate.assert_called_once()

    def test_generate_report_single_run(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            generate_report(
                _make_config(), 1, np.array([-0.025]), 0, str(tmp_path), MagicMock()
            )
            mock_gen.set_best_solution.assert_called_once()

    def test_generate_report_all_failed(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            generate_report(
                _make_config(),
                2,
                np.array([float("inf"), float("inf")]),
                -1,
                str(tmp_path),
                MagicMock(),
            )
            mock_gen.set_best_solution.assert_not_called()

    def test_generate_report_atlas_roi(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            config = _make_config(
                roi=AtlasROI(atlas_path="/path/to/lh.aparc.annot", label=1001)
            )
            generate_report(config, 1, np.array([-0.01]), 0, str(tmp_path), MagicMock())
            mock_gen.set_roi_info.assert_called_once()

    def test_generate_report_subcortical_roi(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            config = _make_config(
                roi=SubcorticalROI(atlas_path="/path/to/aseg.nii.gz", label=11)
            )
            generate_report(config, 1, np.array([-0.01]), 0, str(tmp_path), MagicMock())
            mock_gen.set_roi_info.assert_called_once()

    def test_generate_report_focality_with_non_roi(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            config = _make_config(
                goal="focality",
                non_roi_method="specific",
                non_roi=SphericalROI(x=10, y=10, z=10),
            )
            generate_report(config, 1, np.array([-0.01]), 0, str(tmp_path), MagicMock())
            roi_kwargs = mock_gen.set_roi_info.call_args
            assert "non_roi_method" in str(roi_kwargs)


# ---------------------------------------------------------------------------
# atlas_name_from_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAtlasNameFromPath:
    def test_standard_annot_path(self):
        from tit.opt.flex.builder import _atlas_name_from_path as atlas_name_from_path

        assert atlas_name_from_path("/path/to/lh.aparc.annot", "lh") == "aparc"

    def test_with_subject_prefix(self):
        from tit.opt.flex.builder import _atlas_name_from_path as atlas_name_from_path

        assert atlas_name_from_path("/path/to/lh.001_aparc.annot", "lh") == "aparc"

    def test_no_underscore(self):
        from tit.opt.flex.builder import _atlas_name_from_path as atlas_name_from_path

        assert atlas_name_from_path("/path/to/lh.myatlas.annot", "lh") == "myatlas"

    def test_rh_hemisphere(self):
        from tit.opt.flex.builder import _atlas_name_from_path as atlas_name_from_path

        assert atlas_name_from_path("/path/to/rh.Destrieux.annot", "rh") == "Destrieux"


# ---------------------------------------------------------------------------
# Report field helpers for combined (union) ROIs
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReportUnionFields:
    def test_join_single_returns_scalar(self):
        from tit.opt.flex.builder import _join

        # Byte-identical single-region reports: a bare scalar, not a list.
        assert _join(1001) == 1001
        assert _join([1001]) == 1001

    def test_join_multi_returns_plus_joined_string(self):
        from tit.opt.flex.builder import _join

        assert _join([17, 53]) == "17+53"
        assert "[" not in _join([17, 53])

    def test_sphere_report_fields_single_flat(self):
        from tit.opt.flex.builder import _sphere_report_fields

        coords, radius = _sphere_report_fields(
            SphericalROI(x=10, y=20, z=30, radius=15)
        )
        assert coords == [10, 20, 30]
        assert radius == 15

    def test_sphere_report_fields_multi_nested(self):
        from tit.opt.flex.builder import _sphere_report_fields

        coords, radius = _sphere_report_fields(
            SphericalROI(x=[10, -10], y=[20, -20], z=[30, -30], radius=8)
        )
        assert coords == [[10, 20, 30], [-10, -20, -30]]
        assert radius == [8, 8]
