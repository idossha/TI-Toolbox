"""Tests for tit/opt/flex/flex.py -- run_flex_search orchestrator."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.config import FlexConfig, FlexResult

# Convenience aliases for nested types
SphericalROI = FlexConfig.SphericalROI
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
        n_multistart=1,
    )
    defaults.update(overrides)
    return FlexConfig(**defaults)


# ---------------------------------------------------------------------------
# run_flex_search
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunFlexSearch:
    @patch("tit.opt.flex.manifest.write_manifest")
    @patch("tit.opt.flex.utils.generate_label", return_value="test_label")
    @patch("tit.opt.flex.utils.generate_run_dirname", return_value="20260309_120000")
    @patch("tit.opt.flex.flex.builder")
    @patch("tit.opt.flex.flex.get_path_manager")
    def test_single_run_success(
        self, mock_gpm, mock_builder, mock_dirname, mock_label, mock_manifest, tmp_path
    ):
        pm = MagicMock()
        pm.flex_search.return_value = str(tmp_path / "flex")
        mock_gpm.return_value = pm

        opt_mock = MagicMock()
        opt_mock.optim_funvalue = -0.025
        mock_builder.build_optimization.return_value = opt_mock

        from tit.opt.flex.flex import run_flex_search

        config = _make_config(output_folder=str(tmp_path / "output"))
        result = run_flex_search(config)

        assert result.success is True
        assert result.best_value == -0.025
        assert result.best_run_index == 0
        assert len(result.function_values) == 1
        mock_builder.generate_report.assert_called_once()

    @patch("tit.opt.flex.manifest.write_manifest")
    @patch("tit.opt.flex.utils.generate_label", return_value="test_label")
    @patch("tit.opt.flex.utils.generate_run_dirname", return_value="20260309_120000")
    @patch("tit.opt.flex.flex.builder")
    @patch("tit.opt.flex.flex.get_path_manager")
    def test_multistart_picks_best(
        self, mock_gpm, mock_builder, mock_dirname, mock_label, mock_manifest, tmp_path
    ):
        pm = MagicMock()
        pm.flex_search.return_value = str(tmp_path / "flex")
        mock_gpm.return_value = pm

        values = [-0.020, -0.035, -0.015]
        call_idx = [0]

        def side_effect(config):
            opt = MagicMock()
            opt.optim_funvalue = values[call_idx[0]]
            call_idx[0] += 1
            return opt

        mock_builder.build_optimization.side_effect = side_effect

        from tit.opt.flex.flex import run_flex_search

        config = _make_config(n_multistart=3, output_folder=str(tmp_path / "output"))

        for i in range(3):
            os.makedirs(tmp_path / "output" / f"{i:02d}", exist_ok=True)

        result = run_flex_search(config)

        assert result.success is True
        assert result.best_value == -0.035
        assert result.best_run_index == 1

    @patch("tit.opt.flex.manifest.write_manifest")
    @patch("tit.opt.flex.utils.generate_label", return_value="test_label")
    @patch("tit.opt.flex.utils.generate_run_dirname", return_value="20260309_120000")
    @patch("tit.opt.flex.flex.builder")
    @patch("tit.opt.flex.flex.get_path_manager")
    def test_all_runs_fail(
        self, mock_gpm, mock_builder, mock_dirname, mock_label, mock_manifest, tmp_path
    ):
        pm = MagicMock()
        pm.flex_search.return_value = str(tmp_path / "flex")
        mock_gpm.return_value = pm

        opt_mock = MagicMock()
        opt_mock.optim_funvalue = float("inf")
        mock_builder.build_optimization.return_value = opt_mock

        from tit.opt.flex.flex import run_flex_search

        config = _make_config(n_multistart=2, output_folder=str(tmp_path / "output"))
        result = run_flex_search(config)

        assert result.success is False
        assert result.best_value == float("inf")
        assert result.best_run_index == -1

    @patch("tit.opt.flex.manifest.write_manifest")
    @patch("tit.opt.flex.utils.generate_label", return_value="test_label")
    @patch("tit.opt.flex.utils.generate_run_dirname", return_value="20260309_120000")
    @patch("tit.opt.flex.flex.builder")
    @patch("tit.opt.flex.flex.get_path_manager")
    def test_auto_output_folder(
        self, mock_gpm, mock_builder, mock_dirname, mock_label, mock_manifest, tmp_path
    ):
        pm = MagicMock()
        pm.flex_search.return_value = str(tmp_path / "flex")
        mock_gpm.return_value = pm

        opt_mock = MagicMock()
        opt_mock.optim_funvalue = -0.01
        mock_builder.build_optimization.return_value = opt_mock

        from tit.opt.flex.flex import run_flex_search

        config = _make_config(output_folder=None)
        result = run_flex_search(config)
        assert result.success is True
        assert "20260309_120000" in result.output_folder
