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
# Ex __main__ helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExMainBuildElectrodes:
    def test_pool_from_type(self):
        from tit.opt.ex.__main__ import _build_electrodes
        from tit.opt.config import PoolElectrodes

        result = _build_electrodes(
            {
                "_type": "PoolElectrodes",
                "electrodes": ["E1", "E2", "E3"],
            }
        )
        assert isinstance(result, PoolElectrodes)
        assert result.electrodes == ["E1", "E2", "E3"]

    def test_bucket_from_type(self):
        from tit.opt.ex.__main__ import _build_electrodes
        from tit.opt.config import BucketElectrodes

        result = _build_electrodes(
            {
                "_type": "BucketElectrodes",
                "e1_plus": ["A1"],
                "e1_minus": ["A2"],
                "e2_plus": ["B1"],
                "e2_minus": ["B2"],
            }
        )
        assert isinstance(result, BucketElectrodes)
        assert result.e1_plus == ["A1"]

    def test_pool_inferred_from_electrodes_key(self):
        from tit.opt.ex.__main__ import _build_electrodes
        from tit.opt.config import PoolElectrodes

        result = _build_electrodes(
            {
                "electrodes": ["E1", "E2"],
            }
        )
        assert isinstance(result, PoolElectrodes)

    def test_bucket_inferred_from_bucket_keys(self):
        from tit.opt.ex.__main__ import _build_electrodes
        from tit.opt.config import BucketElectrodes

        result = _build_electrodes(
            {
                "e1_plus": ["A1"],
                "e1_minus": ["A2"],
                "e2_plus": ["B1"],
                "e2_minus": ["B2"],
            }
        )
        assert isinstance(result, BucketElectrodes)

    def test_unknown_type_with_electrodes(self):
        from tit.opt.ex.__main__ import _build_electrodes
        from tit.opt.config import PoolElectrodes

        result = _build_electrodes(
            {
                "_type": "UnknownType",
                "electrodes": ["E1"],
            }
        )
        assert isinstance(result, PoolElectrodes)


@pytest.mark.unit
class TestExMainFunction:
    @patch("tit.opt.ex.__main__.run_ex_search")
    @patch("tit.opt.ex.__main__._make_stdout_logger")
    def test_main_success(self, mock_logger, mock_run, tmp_path):
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
            "currents": {
                "total_current": 2.0,
                "current_step": 0.5,
            },
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        from tit.opt.ex.__main__ import main

        with patch.object(sys, "argv", ["prog", str(config_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    @patch("tit.opt.ex.__main__.run_ex_search")
    @patch("tit.opt.ex.__main__._make_stdout_logger")
    def test_main_failure(self, mock_logger, mock_run, tmp_path):
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

    @patch("tit.opt.ex.__main__.run_ex_search")
    @patch("tit.opt.ex.__main__._make_stdout_logger")
    def test_main_no_currents(self, mock_logger, mock_run, tmp_path):
        from tit.opt.config import ExResult, ExCurrentConfig

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

        # Verify default currents used
        call_args = mock_run.call_args[0][0]
        assert isinstance(call_args.currents, ExCurrentConfig)


# ---------------------------------------------------------------------------
# Flex __main__ helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexMainBuildROI:
    def test_build_spherical_roi(self):
        from tit.opt.flex.__main__ import _build_roi
        from tit.opt.config import SphericalROI

        result = _build_roi(
            {
                "_type": "SphericalROI",
                "x": -42.0,
                "y": -20.0,
                "z": 55.0,
                "radius": 10.0,
            }
        )
        assert isinstance(result, SphericalROI)
        assert result.x == -42.0

    def test_build_atlas_roi(self):
        from tit.opt.flex.__main__ import _build_roi
        from tit.opt.config import AtlasROI

        result = _build_roi(
            {
                "_type": "AtlasROI",
                "atlas_path": "/path/to/annot",
                "label": 1001,
                "hemisphere": "lh",
            }
        )
        assert isinstance(result, AtlasROI)
        assert result.label == 1001

    def test_build_subcortical_roi(self):
        from tit.opt.flex.__main__ import _build_roi
        from tit.opt.config import SubcorticalROI

        result = _build_roi(
            {
                "_type": "SubcorticalROI",
                "atlas_path": "/path/to/aseg.nii.gz",
                "label": 11,
            }
        )
        assert isinstance(result, SubcorticalROI)

    def test_build_none_roi(self):
        from tit.opt.flex.__main__ import _build_roi

        result = _build_roi(None)
        assert result is None


@pytest.mark.unit
class TestFlexMainFunction:
    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_success(self, mock_run, tmp_path):
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

    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_failure(self, mock_run, tmp_path):
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

    @patch("tit.opt.flex.__main__.run_flex_search")
    def test_main_with_non_roi(self, mock_run, tmp_path):
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
