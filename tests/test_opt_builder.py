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

# Ensure simnibs submodules needed by builder.py (and by the lazy imports in
# objectives.py) are mocked
for mod_name in (
    "simnibs.opt_struct",
    "simnibs.optimization",
    "simnibs.optimization.tes_flex_optimization",
    "simnibs.optimization.tes_flex_optimization.electrode_layout",
    "simnibs.optimization.tes_flex_optimization.measures",
    "simnibs.optimization.tes_flex_optimization.tes_flex_optimization",
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
    def test_threshold_free_focality_wires_callable_goal(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        import types

        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(goal="focality_tf", non_roi_method="everything_else")
        result = build_optimization(config)

        # goal is a single-element list holding a plain function (SimNIBS's
        # callable-goal path requires isinstance(goal[0], types.FunctionType)).
        assert isinstance(result.goal, list) and len(result.goal) == 1
        assert isinstance(result.goal[0], types.FunctionType)

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_threshold_free_goal_scores_roi_against_non_roi(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization
        from tit.opt.flex.objectives import threshold_free_focality

        config = _make_config(goal="focality_tf", non_roi_method="everything_else")
        goal_fn = build_optimization(config).goal[0]

        # e_pp[channel][roi_index]; index 0 = ROI, 1 = non-ROI.
        e_pp = [[np.full(8, 0.5), np.full(8, 0.1)]]
        assert goal_fn(e_pp) == pytest.approx(
            -threshold_free_focality(np.full(8, 0.5), np.full(8, 0.1))
        )
        # A stronger off-target field must score worse (larger, since the
        # solver minimizes).
        assert goal_fn([[np.full(8, 0.5), np.full(8, 0.4)]]) > goal_fn(e_pp)

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_threshold_free_goal_forwards_intensity_weight(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization
        from tit.opt.flex.objectives import threshold_free_focality

        config = _make_config(
            goal="focality_tf",
            non_roi_method="everything_else",
            intensity_weight=0.75,
        )
        goal_fn = build_optimization(config).goal[0]

        e_pp = [[np.full(8, 0.5), np.full(8, 0.1)]]
        assert goal_fn(e_pp) == pytest.approx(
            -threshold_free_focality(np.full(8, 0.5), np.full(8, 0.1), 0.75)
        )

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_ratio_search_off_leaves_goal_fun_untouched(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        import types

        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(_make_config())
        assert not isinstance(result.goal_fun, types.FunctionType)

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_ratio_search_installs_goal_fun_wrapper(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        import types

        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        result = build_optimization(_make_config(optimize_current_ratio=True))

        # SimNIBS's own goal_fun is replaced by the plain-function wrapper that
        # scores placement and current split together.
        assert isinstance(result.goal_fun, types.FunctionType)
        assert callable(result.goal_fun)
        # The declared goal is left in place so SimNIBS's own prepare()
        # validation still runs before the wrapper takes over scoring.
        assert result.goal == "mean"

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_ratio_search_with_roc_focality_keeps_thresholds(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        import types

        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            thresholds="0.02,0.08",
            optimize_current_ratio=True,
        )
        result = build_optimization(config)

        assert result.goal == "focality"
        assert result.threshold == [0.02, 0.08]
        assert isinstance(result.goal_fun, types.FunctionType)

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_ratio_search_with_threshold_free_goal(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        import types

        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        from tit.opt.flex.builder import build_optimization

        config = _make_config(
            goal="focality_tf",
            non_roi_method="everything_else",
            optimize_current_ratio=True,
            ratio_levels=5,
        )
        result = build_optimization(config)

        # Both hooks are wired: the callable goal for SimNIBS's own path and
        # the goal_fun wrapper that actually scores each candidate.
        assert isinstance(result.goal, list)
        assert isinstance(result.goal[0], types.FunctionType)
        assert isinstance(result.goal_fun, types.FunctionType)

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_ratio_search_defaults_total_to_twice_current(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        import tit.opt.flex.objectives as objectives_mod
        from tit.opt.flex.builder import build_optimization

        with patch.object(
            objectives_mod, "install_ratio_search", MagicMock()
        ) as install:
            build_optimization(
                _make_config(current_mA=3.0, optimize_current_ratio=True)
            )

        ratios = install.call_args.kwargs["ratios"]
        assert install.call_args.kwargs["base_mA"] == 3.0
        assert len(ratios) == 21
        # total = 2 * current_mA = 6.0 mA, spanning 1:3 .. 3:1
        assert ratios[0] == pytest.approx((1.5, 4.5))
        assert ratios[-1] == pytest.approx((4.5, 1.5))

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_ratio_search_honours_explicit_total(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm, _ = builder_env
        mock_gpm.return_value = pm
        import tit.opt.flex.objectives as objectives_mod
        from tit.opt.flex.builder import build_optimization

        with patch.object(
            objectives_mod, "install_ratio_search", MagicMock()
        ) as install:
            build_optimization(
                _make_config(
                    current_mA=2.0,
                    optimize_current_ratio=True,
                    ratio_total_mA=8.0,
                    ratio_levels=3,
                )
            )

        ratios = install.call_args.kwargs["ratios"]
        assert ratios == pytest.approx([(2.0, 6.0), (4.0, 4.0), (6.0, 2.0)])

    @patch("tit.opt.flex.builder.os.makedirs")
    @patch("tit.opt.flex.builder.utils.configure_roi")
    @patch("tit.paths.get_path_manager")
    def test_even_ratio_levels_still_include_the_balanced_split(
        self, mock_gpm, mock_roi, mock_mkdirs, builder_env
    ):
        _, pm = builder_env[0], builder_env[1]
        mock_gpm.return_value = pm
        import tit.opt.flex.objectives as objectives_mod
        from tit.opt.flex.builder import build_optimization

        with patch.object(
            objectives_mod, "install_ratio_search", MagicMock()
        ) as install:
            build_optimization(
                _make_config(
                    current_mA=2.0, optimize_current_ratio=True, ratio_levels=20
                )
            )

        # ratio_levels rounds up to the next odd count, so the 1:1 split the
        # search would otherwise fall back on stays inside the sweep.
        ratios = install.call_args.kwargs["ratios"]
        assert len(ratios) == 21
        assert any(pair == pytest.approx((2.0, 2.0)) for pair in ratios)

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

    def test_generate_report_records_ratio_settings(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            config = _make_config(
                goal="focality_tf",
                non_roi_method="everything_else",
                intensity_weight=0.5,
                optimize_current_ratio=True,
                ratio_total_mA=6.0,
                ratio_levels=9,
            )
            generate_report(
                config, 1, np.array([-0.025]), 0, str(tmp_path), MagicMock()
            )

            kwargs = mock_gen.set_configuration.call_args.kwargs
            assert kwargs["intensity_weight"] == 0.5
            assert kwargs["optimize_current_ratio"] is True
            assert kwargs["ratio_total_mA"] == 6.0
            assert kwargs["ratio_levels"] == 9

    def test_generate_report_ratio_settings_default_off(self, tmp_path):
        patcher, mock_gen = self._patch_report_gen()
        with patcher, patch("tit.paths.get_path_manager") as mock_gpm:
            mock_gpm.return_value = MagicMock(project_dir="/proj")
            from tit.opt.flex.builder import generate_report

            generate_report(
                _make_config(), 1, np.array([-0.025]), 0, str(tmp_path), MagicMock()
            )

            kwargs = mock_gen.set_configuration.call_args.kwargs
            assert kwargs["intensity_weight"] == 0.0
            assert kwargs["optimize_current_ratio"] is False
            assert kwargs["ratio_total_mA"] is None
            assert kwargs["ratio_levels"] == 21

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
