"""Tests for tit/opt/ex/__main__.py and tit/opt/flex/__main__.py."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# ---------------------------------------------------------------------------
# Ex __main__: electrode/ROI union rebuilding is now tit.config_io.deserialize_config's
# job (see tests/test_config_schema.py's round-trip coverage for
# ExConfig/FlexConfig), not a hand-rolled helper in __main__.py.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExMainFunction:
    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.ex.__main__.run_ex_search")
    @patch("tit.opt.ex.__main__._make_stdout_logger")
    def test_main_success(self, mock_logger, mock_run, mock_gpm, tmp_path):
        from tit.opt.config import ExResult

        mock_run.return_value = ExResult(
            success=True,
            output_dir="/out",
            n_combinations=10,
        )

        config_data = {
            "subject_id": "001",
            "project_dir": "/proj",
            "leadfield_hdf": "/lf.hdf5",
            "roi_name": "motor.csv",
            "electrodes": {
                "_type": "PoolElectrodes",
                "electrodes": ["E1", "E2", "E3", "E4"],
            },
            "total_current": 2.0,
            "current_step": 0.5,
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        from tit.opt.ex.__main__ import main

        with patch.object(sys, "argv", ["prog", str(config_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.ex.__main__.run_ex_search")
    @patch("tit.opt.ex.__main__._make_stdout_logger")
    def test_main_failure(self, mock_logger, mock_run, mock_gpm, tmp_path):
        from tit.opt.config import ExResult

        mock_run.return_value = ExResult(
            success=False,
            output_dir="/out",
            n_combinations=0,
        )

        config_data = {
            "subject_id": "001",
            "project_dir": "/proj",
            "leadfield_hdf": "/lf.hdf5",
            "roi_name": "motor.csv",
            "electrodes": {
                "_type": "PoolElectrodes",
                "electrodes": ["E1", "E2", "E3", "E4"],
            },
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        from tit.opt.ex.__main__ import main

        with patch.object(sys, "argv", ["prog", str(config_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.ex.__main__.run_ex_search")
    @patch("tit.opt.ex.__main__._make_stdout_logger")
    def test_main_no_currents(self, mock_logger, mock_run, mock_gpm, tmp_path):
        from tit.opt.config import ExResult

        mock_run.return_value = ExResult(
            success=True,
            output_dir="/out",
            n_combinations=5,
        )

        config_data = {
            "subject_id": "001",
            "project_dir": "/proj",
            "leadfield_hdf": "/lf.hdf5",
            "roi_name": "motor.csv",
            "electrodes": {
                "_type": "PoolElectrodes",
                "electrodes": ["E1", "E2", "E3", "E4"],
            },
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        from tit.opt.ex.__main__ import main

        with patch.object(sys, "argv", ["prog", str(config_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        # Verify default current fields used
        call_args = mock_run.call_args[0][0]
        assert call_args.total_current == 2.0
        assert call_args.current_step == 0.5


# ---------------------------------------------------------------------------
# Flex __main__ helpers
# ---------------------------------------------------------------------------


# ROI union rebuilding is now tit.config_io.deserialize_config's job (see
# tests/test_config_schema.py's round-trip coverage for FlexConfig), not a
# hand-rolled helper in __main__.py.


@pytest.mark.unit
class TestFlexMainFunction:
    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_success(self, mock_run, mock_gpm, tmp_path):
        from tit.opt.config import FlexResult

        mock_run.return_value = FlexResult(
            success=True,
            output_folder="/out",
            function_values=[-0.025],
            best_value=-0.025,
            best_run_index=0,
        )

        config_data = {
            "subject_id": "001",
            "project_dir": "/proj",
            "goal": "mean",
            "postproc": "max_TI",
            "current_mA": 2.0,
            "electrode": {
                "shape": "ellipse",
                "dimensions": [8.0, 8.0],
                "gel_thickness": 4.0,
            },
            "roi": {
                "_type": "SphericalROI",
                "x": -42.0,
                "y": -20.0,
                "z": 55.0,
            },
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        from tit.opt.flex.__main__ import main

        with patch("tit.logger.add_stream_handler"):
            with patch.object(sys, "argv", ["prog", str(config_path)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0

    def _dispatch_config_data(self, mode, extra=None):
        data = {
            "subject_id": "001",
            "project_dir": "/proj",
            "mode": mode,
            "goal": "focality",
            "postproc": "max_TI",
            "current_mA": 2.0,
            "electrode": {
                "shape": "ellipse",
                "dimensions": [8.0, 8.0],
                "gel_thickness": 4.0,
            },
            "roi": {
                "_type": "SphericalROI",
                "x": -42.0,
                "y": -20.0,
                "z": 55.0,
            },
        }
        data.update(extra or {})
        return data

    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.flex.__main__.run_pareto_sweep")
    @patch("tit.opt.flex.__main__.run_adaptive_focality")
    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_dispatches_to_run_flex_search_by_default(
        self, mock_flex, mock_adaptive, mock_pareto, mock_gpm, tmp_path
    ):
        """config.mode defaults to 'flex' -- the plain run_flex_search path."""
        from tit.opt.config import FlexResult
        from tit.opt.flex.__main__ import main

        mock_flex.return_value = FlexResult(
            success=True,
            output_folder="/out",
            function_values=[-0.01],
            best_value=-0.01,
            best_run_index=0,
        )
        config_data = self._dispatch_config_data("flex")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        with patch("tit.logger.add_stream_handler"):
            with patch.object(sys, "argv", ["prog", str(config_path)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 0
        mock_flex.assert_called_once()
        mock_adaptive.assert_not_called()
        mock_pareto.assert_not_called()

    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.flex.__main__.run_pareto_sweep")
    @patch("tit.opt.flex.__main__.run_adaptive_focality")
    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_dispatches_flex_adaptive_kind_to_the_adaptive_driver(
        self, mock_flex, mock_adaptive, mock_pareto, mock_gpm, tmp_path
    ):
        from tit.opt.config import FlexConfig, FlexResult
        from tit.opt.flex.__main__ import main

        mock_adaptive.return_value = FlexResult(
            success=True,
            output_folder="/out",
            function_values=[-0.01],
            best_value=-0.01,
            best_run_index=0,
        )
        config_data = self._dispatch_config_data("flex_adaptive")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        with patch("tit.logger.add_stream_handler"):
            with patch.object(sys, "argv", ["prog", str(config_path)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 0
        mock_adaptive.assert_called_once()
        mock_flex.assert_not_called()
        mock_pareto.assert_not_called()
        # The dispatched-to config really is the deserialized FlexConfig.
        dispatched_config = mock_adaptive.call_args.args[0]
        assert dispatched_config.mode is FlexConfig.Mode.FLEX_ADAPTIVE

    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.flex.__main__.run_pareto_sweep")
    @patch("tit.opt.flex.__main__.run_adaptive_focality")
    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_dispatches_flex_pareto_kind_to_the_pareto_driver(
        self, mock_flex, mock_adaptive, mock_pareto, mock_gpm, tmp_path
    ):
        from tit.opt.config import FlexResult
        from tit.opt.flex.__main__ import main

        mock_pareto.return_value = FlexResult(
            success=True,
            output_folder="/out",
            function_values=[-0.01],
            best_value=-0.01,
            best_run_index=0,
        )
        config_data = self._dispatch_config_data("flex_pareto")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        with patch("tit.logger.add_stream_handler"):
            with patch.object(sys, "argv", ["prog", str(config_path)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 0
        mock_pareto.assert_called_once()
        mock_flex.assert_not_called()
        mock_adaptive.assert_not_called()

    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_failure(self, mock_run, mock_gpm, tmp_path):
        from tit.opt.config import FlexResult

        mock_run.return_value = FlexResult(
            success=False,
            output_folder="/out",
            function_values=[float("inf")],
            best_value=float("inf"),
            best_run_index=-1,
        )

        config_data = {
            "subject_id": "001",
            "project_dir": "/proj",
            "goal": "mean",
            "postproc": "max_TI",
            "current_mA": 2.0,
            "electrode": {
                "shape": "ellipse",
                "dimensions": [8.0, 8.0],
                "gel_thickness": 4.0,
            },
            "roi": {
                "_type": "SphericalROI",
                "x": 0,
                "y": 0,
                "z": 0,
            },
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        from tit.opt.flex.__main__ import main

        with patch("tit.logger.add_stream_handler"):
            with patch.object(sys, "argv", ["prog", str(config_path)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

    @patch("tit.paths.get_path_manager")
    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_with_non_roi(self, mock_run, mock_gpm, tmp_path):
        from tit.opt.config import FlexResult

        mock_run.return_value = FlexResult(
            success=True,
            output_folder="/out",
            function_values=[-0.01],
            best_value=-0.01,
            best_run_index=0,
        )

        config_data = {
            "subject_id": "001",
            "project_dir": "/proj",
            "goal": "focality",
            "postproc": "max_TI",
            "current_mA": 2.0,
            "non_roi_method": "specific",
            "electrode": {
                "shape": "ellipse",
                "dimensions": [8.0, 8.0],
                "gel_thickness": 4.0,
            },
            "roi": {
                "_type": "SphericalROI",
                "x": -42.0,
                "y": -20.0,
                "z": 55.0,
            },
            "non_roi": {
                "_type": "SphericalROI",
                "x": 10.0,
                "y": 10.0,
                "z": 10.0,
            },
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        from tit.opt.flex.__main__ import main

        with patch("tit.logger.add_stream_handler"):
            with patch.object(sys, "argv", ["prog", str(config_path)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0
