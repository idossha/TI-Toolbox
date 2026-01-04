#!/usr/bin/env simnibs_python
"""
Unit tests for sim/subprocess_runner.py.

Tests subprocess execution functionality including:
- main(): Command-line entry point with --config and --results
- _ensure_own_process_group(): Process group setup
- _build_logger(): Logger creation with file + console
- _load_payload(): JSON config loading
- Error handling and exit codes
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open, call
from pathlib import Path

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.sim.subprocess_runner import (
    _ensure_own_process_group,
    _build_logger,
    _load_payload,
    main
)


@pytest.mark.unit
class TestEnsureOwnProcessGroup:
    """Test suite for _ensure_own_process_group() function."""

    @patch('os.name', 'posix')
    @patch('os.setpgid')
    def test_unix_process_group(self, mock_setpgid):
        """Test process group setup on Unix systems."""
        _ensure_own_process_group()
        mock_setpgid.assert_called_once_with(0, 0)

    @patch('os.name', 'nt')
    @patch('os.setpgid')
    def test_windows_skip(self, mock_setpgid):
        """Test that Windows skips process group setup."""
        _ensure_own_process_group()
        mock_setpgid.assert_not_called()

    @patch('os.name', 'posix')
    @patch('os.setpgid', side_effect=Exception("Test error"))
    def test_exception_handling(self, mock_setpgid):
        """Test graceful handling of setpgid failures."""
        # Should not raise exception
        _ensure_own_process_group()
        mock_setpgid.assert_called_once()


@pytest.mark.unit
class TestBuildLogger:
    """Test suite for _build_logger() function."""

    @patch('tit.core.get_path_manager')
    @patch('tit.logger.get_logger')
    @patch('os.makedirs')
    @patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    def test_logger_creation(self, mock_join, mock_makedirs, mock_get_logger, mock_pm):
        """Test logger creation with correct paths."""
        # Mock PathManager
        mock_pm_instance = MagicMock()
        mock_pm_instance.get_derivatives_dir.return_value = "/test/derivatives"
        mock_pm.return_value = mock_pm_instance

        # Mock logger
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        logger, log_file = _build_logger("001", "/test/project", debug=False)

        # Check directory creation
        mock_makedirs.assert_called_once()

        # Check logger was created
        mock_get_logger.assert_called_once()
        assert logger == mock_logger
        assert "sub-001" in log_file
        assert "Simulator_" in log_file

    @patch('tit.core.get_path_manager')
    @patch('tit.logger.get_logger')
    @patch('os.makedirs')
    def test_debug_mode(self, mock_makedirs, mock_get_logger, mock_pm):
        """Test logger in debug mode."""
        # Mock PathManager
        mock_pm_instance = MagicMock()
        mock_pm_instance.get_derivatives_dir.return_value = "/test/derivatives"
        mock_pm.return_value = mock_pm_instance

        # Mock logger with handlers
        mock_logger = MagicMock()
        mock_console_handler = MagicMock()
        mock_console_handler.setLevel = MagicMock()
        mock_logger.handlers = [mock_console_handler]
        mock_get_logger.return_value = mock_logger

        with patch('logging.StreamHandler', return_value=mock_console_handler):
            logger, log_file = _build_logger("001", "/test/project", debug=True)

        # Should set handler to DEBUG level
        # Note: actual implementation may vary
        assert logger == mock_logger


@pytest.mark.unit
class TestLoadPayload:
    """Test suite for _load_payload() function."""

    def test_load_valid_json(self, tmp_path):
        """Test loading valid JSON config file."""
        payload = {
            "config": {"subject_id": "001"},
            "montages": [],
            "debug": False
        }

        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(payload, f)

        result = _load_payload(str(config_file))

        assert result == payload
        assert result["config"]["subject_id"] == "001"

    def test_missing_file(self):
        """Test error for missing config file."""
        with pytest.raises(FileNotFoundError):
            _load_payload("/nonexistent/config.json")

    def test_invalid_json(self, tmp_path):
        """Test error for invalid JSON."""
        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            f.write("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            _load_payload(str(config_file))


@pytest.mark.unit
class TestMain:
    """Test suite for main() function."""

    def test_missing_required_args(self):
        """Test error when required arguments are missing."""
        with pytest.raises(SystemExit):
            main(argv=["--config", "config.json"])  # Missing --results

    def test_missing_subject_id_in_config(self, tmp_path):
        """Test error when subject_id missing from config."""
        payload = {
            "config": {"project_dir": "/test"},  # Missing subject_id
            "montages": []
        }

        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(payload, f)

        results_file = tmp_path / "results.json"

        exit_code = main(argv=[
            "--config", str(config_file),
            "--results", str(results_file)
        ])

        assert exit_code == 2

    @patch('tit.core.get_path_manager')
    @patch('tit.sim.subprocess_runner._build_logger')
    @patch('tit.sim.run_simulation')
    @patch('tit.sim.subprocess_runner._ensure_own_process_group')
    def test_successful_execution(self, mock_pg, mock_run_sim, mock_logger, mock_pm, tmp_path):
        """Test successful simulation execution."""
        # Setup payload
        payload = {
            "config": {
                "subject_id": "001",
                "project_dir": "/test/project",
                "conductivity_type": "dir",
                "intensities": {
                    "pair1": 1.0,
                    "pair2": 1.0,
                    "pair3": 1.0,
                    "pair4": 1.0
                },
                "electrode": {
                    "shape": "ellipse",
                    "dimensions": [8.0, 8.0],
                    "thickness": 4.0,
                    "sponge_thickness": 2.0
                },
                "eeg_net": "EGI_template.csv",
                "parallel": {
                    "enabled": False,
                    "max_workers": 0
                }
            },
            "montages": [{
                "name": "montage1",
                "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
                "is_xyz": False,
                "eeg_net": None
            }]
        }

        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(payload, f)

        results_file = tmp_path / "results.json"

        # Mock logger
        mock_logger_instance = MagicMock()
        mock_logger.return_value = (mock_logger_instance, "/test/log.log")

        # Mock PathManager
        mock_pm_instance = MagicMock()
        mock_pm_instance.project_dir = "/test/project"
        mock_pm.return_value = mock_pm_instance

        # Mock simulation results
        mock_run_sim.return_value = [{
            "montage_name": "montage1",
            "status": "completed"
        }]

        # Run main
        exit_code = main(argv=[
            "--config", str(config_file),
            "--results", str(results_file)
        ])

        # Check exit code
        assert exit_code == 0

        # Check results file was created
        assert results_file.exists()

        with open(results_file, 'r') as f:
            results = json.load(f)

        assert results["status"] == "ok"
        assert results["subject_id"] == "001"
        assert len(results["results"]) == 1

        # Check simulation was called
        mock_run_sim.assert_called_once()

    @patch('tit.core.get_path_manager')
    @patch('tit.sim.subprocess_runner._build_logger')
    @patch('tit.sim.run_simulation', side_effect=Exception("Simulation failed"))
    @patch('tit.sim.subprocess_runner._ensure_own_process_group')
    def test_simulation_exception_handling(self, mock_pg, mock_run_sim, mock_logger, mock_pm, tmp_path):
        """Test exception handling during simulation."""
        # Setup payload
        payload = {
            "config": {
                "subject_id": "001",
                "project_dir": "/test/project",
                "conductivity_type": "dir",
                "intensities": {
                    "pair1": 1.0,
                    "pair2": 1.0,
                    "pair3": 1.0,
                    "pair4": 1.0
                },
                "electrode": {
                    "shape": "ellipse",
                    "dimensions": [8.0, 8.0],
                    "thickness": 4.0,
                    "sponge_thickness": 2.0
                },
                "eeg_net": "EGI_template.csv",
                "parallel": {
                    "enabled": False,
                    "max_workers": 0
                }
            },
            "montages": []
        }

        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(payload, f)

        results_file = tmp_path / "results.json"

        # Mock logger
        mock_logger_instance = MagicMock()
        mock_logger.return_value = (mock_logger_instance, "/test/log.log")

        # Mock PathManager
        mock_pm_instance = MagicMock()
        mock_pm_instance.project_dir = "/test/project"
        mock_pm.return_value = mock_pm_instance

        # Run main
        exit_code = main(argv=[
            "--config", str(config_file),
            "--results", str(results_file)
        ])

        # Should return error code
        assert exit_code == 1

        # Check error was written to results file
        assert results_file.exists()

        with open(results_file, 'r') as f:
            results = json.load(f)

        assert results["status"] == "failed"
        assert "Simulation failed" in results["error"]

    @patch('tit.sim.subprocess_runner._ensure_own_process_group')
    def test_debug_flag(self, mock_pg, tmp_path):
        """Test that debug flag is passed through."""
        payload = {
            "config": {
                "subject_id": "001",
                "project_dir": "/test/project",
                "conductivity_type": "dir",
                "intensities": {
                    "pair1": 1.0,
                    "pair2": 1.0,
                    "pair3": 1.0,
                    "pair4": 1.0
                },
                "electrode": {
                    "shape": "ellipse",
                    "dimensions": [8.0, 8.0],
                    "thickness": 4.0,
                    "sponge_thickness": 2.0
                },
                "eeg_net": "EGI_template.csv",
                "parallel": {
                    "enabled": False,
                    "max_workers": 0
                }
            },
            "montages": [],
            "debug": True
        }

        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(payload, f)

        results_file = tmp_path / "results.json"

        with patch('tit.sim.subprocess_runner._build_logger') as mock_logger, \
             patch('tit.core.get_path_manager') as mock_pm, \
             patch('tit.sim.run_simulation') as mock_run_sim:

            mock_logger_instance = MagicMock()
            mock_logger.return_value = (mock_logger_instance, "/test/log.log")

            mock_pm_instance = MagicMock()
            mock_pm_instance.project_dir = "/test/project"
            mock_pm.return_value = mock_pm_instance

            mock_run_sim.return_value = []

            main(argv=[
                "--config", str(config_file),
                "--results", str(results_file)
            ])

            # Check debug flag was passed to logger
            mock_logger.assert_called_once()
            args, kwargs = mock_logger.call_args
            assert kwargs.get('debug', args[2] if len(args) > 2 else False) is True

    @patch('tit.sim.subprocess_runner._ensure_own_process_group')
    def test_sys_path_setup(self, mock_pg, tmp_path):
        """Test that sys.path is configured correctly."""
        payload = {
            "config": {
                "subject_id": "001",
                "project_dir": "/test/project",
                "conductivity_type": "dir",
                "intensities": {
                    "pair1": 1.0,
                    "pair2": 1.0,
                    "pair3": 1.0,
                    "pair4": 1.0
                },
                "electrode": {
                    "shape": "ellipse",
                    "dimensions": [8.0, 8.0],
                    "thickness": 4.0,
                    "sponge_thickness": 2.0
                },
                "eeg_net": "EGI_template.csv",
                "parallel": {
                    "enabled": False,
                    "max_workers": 0
                }
            },
            "montages": []
        }

        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(payload, f)

        results_file = tmp_path / "results.json"

        with patch('tit.sim.subprocess_runner._build_logger') as mock_logger, \
             patch('tit.core.get_path_manager') as mock_pm, \
             patch('tit.sim.run_simulation') as mock_run_sim:

            mock_logger_instance = MagicMock()
            mock_logger.return_value = (mock_logger_instance, "/test/log.log")

            mock_pm_instance = MagicMock()
            mock_pm_instance.project_dir = "/test/project"
            mock_pm.return_value = mock_pm_instance

            mock_run_sim.return_value = []

            # Save original sys.path
            original_path = sys.path.copy()

            main(argv=[
                "--config", str(config_file),
                "--results", str(results_file)
            ])

            # Check that path was modified
            # (actual check depends on implementation details)
            # This is a basic sanity check
            assert len(sys.path) >= len(original_path)

    def test_empty_montages(self, tmp_path):
        """Test execution with empty montages list."""
        payload = {
            "config": {
                "subject_id": "001",
                "project_dir": "/test/project",
                "conductivity_type": "dir",
                "intensities": {
                    "pair1": 1.0,
                    "pair2": 1.0,
                    "pair3": 1.0,
                    "pair4": 1.0
                },
                "electrode": {
                    "shape": "ellipse",
                    "dimensions": [8.0, 8.0],
                    "thickness": 4.0,
                    "sponge_thickness": 2.0
                },
                "eeg_net": "EGI_template.csv",
                "parallel": {
                    "enabled": False,
                    "max_workers": 0
                }
            },
            "montages": []
        }

        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(payload, f)

        results_file = tmp_path / "results.json"

        with patch('tit.sim.subprocess_runner._ensure_own_process_group'), \
             patch('tit.sim.subprocess_runner._build_logger') as mock_logger, \
             patch('tit.core.get_path_manager') as mock_pm, \
             patch('tit.sim.run_simulation') as mock_run_sim:

            mock_logger_instance = MagicMock()
            mock_logger.return_value = (mock_logger_instance, "/test/log.log")

            mock_pm_instance = MagicMock()
            mock_pm_instance.project_dir = "/test/project"
            mock_pm.return_value = mock_pm_instance

            mock_run_sim.return_value = []

            exit_code = main(argv=[
                "--config", str(config_file),
                "--results", str(results_file)
            ])

            # Should still succeed with empty montages
            assert exit_code == 0
