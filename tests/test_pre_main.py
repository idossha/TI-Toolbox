"""Tests for tit.pre.__main__ — entry point."""

import json
from unittest.mock import MagicMock, patch, mock_open

import pytest

MODULE = "tit.pre.__main__"


class TestMain:
    """Tests for the main entry point."""

    @patch(f"{MODULE}.sys.exit")
    @patch(f"{MODULE}.run_pipeline", return_value=0)
    @patch("tit.logger.add_stream_handler")
    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    def test_success(self, mock_handler, mock_pipeline, mock_exit):
        config = {
            "project_dir": "/proj",
            "subject_ids": ["001"],
        }
        with patch("builtins.open", mock_open(read_data=json.dumps(config))):
            from tit.pre.__main__ import main

            main()

        mock_pipeline.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch(f"{MODULE}.sys.exit")
    @patch(f"{MODULE}.run_pipeline", return_value=1)
    @patch("tit.logger.add_stream_handler")
    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    def test_failure_exit_code(self, mock_handler, mock_pipeline, mock_exit):
        config = {
            "project_dir": "/proj",
            "subject_ids": ["001"],
        }
        with patch("builtins.open", mock_open(read_data=json.dumps(config))):
            from tit.pre.__main__ import main

            main()

        mock_exit.assert_called_once_with(1)

    @patch(f"{MODULE}.sys.exit")
    @patch(f"{MODULE}.run_pipeline", return_value=0)
    @patch("tit.logger.add_stream_handler")
    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    def test_all_config_options(self, mock_handler, mock_pipeline, mock_exit):
        config = {
            "project_dir": "/proj",
            "subject_ids": ["001", "002"],
            "convert_dicom": True,
            "run_recon": True,
            "parallel_recon": True,
            "parallel_cores": 4,
            "create_m2m": True,
            "run_tissue_analysis": True,
            "run_qsiprep": True,
            "run_qsirecon": True,
            "qsiprep_config": {"key": "val"},
            "qsi_recon_config": {"specs": ["dki"]},
            "extract_dti": True,
            "run_subcortical_segmentations": True,
        }
        with patch("builtins.open", mock_open(read_data=json.dumps(config))):
            from tit.pre.__main__ import main

            main()

        call_kwargs = mock_pipeline.call_args
        assert call_kwargs.kwargs["convert_dicom"] is True
        assert call_kwargs.kwargs["run_recon"] is True
        assert call_kwargs.kwargs["parallel_recon"] is True
        assert call_kwargs.kwargs["create_m2m"] is True

    @patch(f"{MODULE}.sys.exit")
    @patch(f"{MODULE}.run_pipeline", return_value=0)
    @patch("tit.logger.add_stream_handler")
    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    def test_optional_defaults(self, mock_handler, mock_pipeline, mock_exit):
        """Missing optional keys default to False/None."""
        config = {
            "project_dir": "/proj",
            "subject_ids": ["001"],
        }
        with patch("builtins.open", mock_open(read_data=json.dumps(config))):
            from tit.pre.__main__ import main

            main()

        call_kwargs = mock_pipeline.call_args
        assert call_kwargs.kwargs["convert_dicom"] is False
        assert call_kwargs.kwargs["run_recon"] is False
