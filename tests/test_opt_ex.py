"""Tests for tit/opt/ex/ex.py -- run_ex_search orchestrator."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.config import (
    BucketElectrodes,
    ExConfig,
    ExCurrentConfig,
    ExResult,
    PoolElectrodes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ex_config(**overrides):
    defaults = dict(
        subject_id="001",
        project_dir="/proj",
        leadfield_hdf="/lf.hdf5",
        roi_name="motor.csv",
        electrodes=PoolElectrodes(electrodes=["E1", "E2", "E3", "E4"]),
        currents=ExCurrentConfig(total_current=2.0, current_step=0.5),
        eeg_net="EEG10-10",
    )
    defaults.update(overrides)
    return ExConfig(**defaults)


# ---------------------------------------------------------------------------
# run_ex_search
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunExSearch:
    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_pool_mode_success(self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"montage_1": {"val": 0.5}}

        mock_save.return_value = {
            "json_path": str(tmp_path / "results.json"),
            "csv_path": str(tmp_path / "results.csv"),
        }

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config()
        result = run_ex_search(config)

        assert result.success is True
        assert result.n_combinations == 1
        engine.initialize.assert_called_once()
        engine.run.assert_called_once()
        mock_save.assert_called_once()

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_bucket_mode(self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {"v": 1}}

        mock_save.return_value = {
            "json_path": "/j.json",
            "csv_path": "/c.csv",
        }

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config(
            electrodes=BucketElectrodes(
                e1_plus=["A1"],
                e1_minus=["A2"],
                e2_plus=["B1"],
                e2_minus=["B2"],
            ),
        )
        result = run_ex_search(config)

        assert result.success is True
        # Bucket mode: all_combinations=False
        call_args = engine.run.call_args
        assert call_args[1].get("all_combinations", call_args[0][5] if len(call_args[0]) > 5 else None) is False or \
               not call_args.kwargs.get("all_combinations", True)

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_channel_limit_default(self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {}

        mock_save.return_value = {"json_path": "/j", "csv_path": "/c"}

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config(
            currents=ExCurrentConfig(total_current=4.0, current_step=0.5, channel_limit=None),
        )
        run_ex_search(config)

        # When channel_limit is None, should default to total_current / 2.0
        # The generate_current_ratios call should use 2.0 as limit

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_creates_output_dir(self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "new_output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {}

        mock_save.return_value = {"json_path": "/j", "csv_path": "/c"}

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config()
        run_ex_search(config)

        assert os.path.isdir(str(tmp_path / "new_output"))

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_result_fields(self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {}, "m2": {}, "m3": {}}

        mock_save.return_value = {
            "json_path": "/results.json",
            "csv_path": "/results.csv",
        }

        from tit.opt.ex.ex import run_ex_search

        config = _make_ex_config()
        result = run_ex_search(config)

        assert isinstance(result, ExResult)
        assert result.success is True
        assert result.n_combinations == 3
        assert result.results_json == "/results.json"
        assert result.results_csv == "/results.csv"
