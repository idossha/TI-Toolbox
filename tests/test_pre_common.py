#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox pre-processing common utilities (pre/common.py)
"""

import json
import logging
import os
import pytest
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from pre.common import (
    PreprocessError,
    PreprocessCancelled,
    ensure_subject_dirs,
    ensure_dataset_descriptions,
    build_logger,
    should_overwrite_path,
    CommandRunner,
    _terminate_process,
    DATASET_TEMPLATES,
)


class TestPreprocessExceptions:
    """Test custom exception classes"""

    def test_preprocess_error_creation(self):
        """Test PreprocessError exception creation"""
        error = PreprocessError("Test error message")
        assert isinstance(error, RuntimeError)
        assert str(error) == "Test error message"

    def test_preprocess_error_raise(self):
        """Test PreprocessError can be raised and caught"""
        with pytest.raises(PreprocessError) as exc_info:
            raise PreprocessError("Something failed")
        assert "Something failed" in str(exc_info.value)

    def test_preprocess_cancelled_creation(self):
        """Test PreprocessCancelled exception creation"""
        error = PreprocessCancelled("Cancelled by user")
        assert isinstance(error, RuntimeError)
        assert str(error) == "Cancelled by user"

    def test_preprocess_cancelled_raise(self):
        """Test PreprocessCancelled can be raised and caught"""
        with pytest.raises(PreprocessCancelled) as exc_info:
            raise PreprocessCancelled("User stopped process")
        assert "User stopped process" in str(exc_info.value)


class TestEnsureSubjectDirs:
    """Test ensure_subject_dirs function"""

    @patch("pre.common.get_path_manager")
    def test_ensure_subject_dirs_creates_all_directories(self, mock_get_pm):
        """Test that all required subject directories are created"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        project_dir = "/test/project"
        subject_id = "001"

        ensure_subject_dirs(project_dir, subject_id)

        # Verify project_dir was set
        assert mock_pm.project_dir == project_dir

        # Verify all modalities and directories were created
        calls = mock_pm.ensure_dir.call_args_list
        assert (
            len(calls) == 6
        )  # T1w, T2w, bids_anat, freesurfer_subject, simnibs_subject, ti_toolbox

        # Check sourcedata_dicom for both modalities
        assert call("sourcedata_dicom", subject_id=subject_id, modality="T1w") in calls
        assert call("sourcedata_dicom", subject_id=subject_id, modality="T2w") in calls

        # Check other directories
        assert call("bids_anat", subject_id=subject_id) in calls
        assert call("freesurfer_subject", subject_id=subject_id) in calls
        assert call("simnibs_subject", subject_id=subject_id) in calls
        assert call("ti_toolbox") in calls

    @patch("pre.common.get_path_manager")
    def test_ensure_subject_dirs_different_subjects(self, mock_get_pm):
        """Test creating directories for different subjects"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        project_dir = "/test/project"

        ensure_subject_dirs(project_dir, "001")
        ensure_subject_dirs(project_dir, "002")

        # Should have been called for both subjects
        calls = mock_pm.ensure_dir.call_args_list
        assert call("sourcedata_dicom", subject_id="001", modality="T1w") in calls
        assert call("sourcedata_dicom", subject_id="002", modality="T1w") in calls


class TestDatasetDescriptions:
    """Test dataset description file creation"""

    def test_dataset_templates_constant(self):
        """Test DATASET_TEMPLATES contains expected datasets"""
        assert "freesurfer" in DATASET_TEMPLATES
        assert "simnibs" in DATASET_TEMPLATES
        assert "ti-toolbox" in DATASET_TEMPLATES
        assert DATASET_TEMPLATES["freesurfer"] == "freesurfer.dataset_description.json"
        assert DATASET_TEMPLATES["simnibs"] == "simnibs.dataset_description.json"
        assert DATASET_TEMPLATES["ti-toolbox"] == "ti-toolbox.dataset_description.json"

    def test_ensure_dataset_descriptions_creates_files(self):
        """Test dataset description files are created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir
            datasets = ["freesurfer", "simnibs", "ti-toolbox"]

            ensure_dataset_descriptions(project_dir, datasets)

            # Check that files were created
            fs_file = (
                Path(project_dir)
                / "derivatives"
                / "freesurfer"
                / "dataset_description.json"
            )
            simnibs_file = (
                Path(project_dir)
                / "derivatives"
                / "SimNIBS"
                / "dataset_description.json"
            )
            tit_file = (
                Path(project_dir)
                / "derivatives"
                / "ti-toolbox"
                / "dataset_description.json"
            )

            assert fs_file.exists()
            assert simnibs_file.exists()
            assert tit_file.exists()

            # Verify JSON structure
            for file in [fs_file, simnibs_file, tit_file]:
                data = json.loads(file.read_text())
                assert "Name" in data
                assert "BIDSVersion" in data
                assert "DatasetType" in data
                assert data["DatasetType"] == "derivative"

    def test_ensure_dataset_descriptions_updates_uri(self):
        """Test that URI is updated in existing files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir
            project_name = Path(project_dir).name

            # Create initial file with empty URI
            fs_dir = Path(project_dir) / "derivatives" / "freesurfer"
            fs_dir.mkdir(parents=True, exist_ok=True)
            fs_file = fs_dir / "dataset_description.json"
            initial_data = {
                "Name": "FreeSurfer derivatives",
                "BIDSVersion": "1.10.0",
                "DatasetType": "derivative",
                "SourceDatasets": [{"URI": ""}],
                "DatasetLinks": {},
            }
            fs_file.write_text(json.dumps(initial_data, indent=2))

            # Run ensure_dataset_descriptions
            ensure_dataset_descriptions(project_dir, ["freesurfer"])

            # Check that URI was updated
            updated_data = json.loads(fs_file.read_text())
            assert updated_data["SourceDatasets"][0]["URI"] != ""
            assert project_name in updated_data["SourceDatasets"][0]["URI"]
            assert "bids:" in updated_data["SourceDatasets"][0]["URI"]

    def test_ensure_dataset_descriptions_updates_dataset_links(self):
        """Test that DatasetLinks is updated"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir
            project_name = Path(project_dir).name

            ensure_dataset_descriptions(project_dir, ["simnibs"])

            simnibs_file = (
                Path(project_dir)
                / "derivatives"
                / "SimNIBS"
                / "dataset_description.json"
            )
            data = json.loads(simnibs_file.read_text())

            assert "DatasetLinks" in data
            assert project_name in data["DatasetLinks"]
            assert data["DatasetLinks"][project_name] == "../../"

    def test_ensure_dataset_descriptions_handles_unknown_dataset(self):
        """Test that unknown datasets are skipped"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir

            # Should not raise an error
            ensure_dataset_descriptions(project_dir, ["unknown_dataset"])

            # No files should be created for unknown dataset
            unknown_dir = Path(project_dir) / "derivatives" / "unknown_dataset"
            assert not unknown_dir.exists()

    def test_ensure_dataset_descriptions_handles_corrupted_json(self):
        """Test that corrupted JSON files are handled gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir

            # Create corrupted JSON file
            fs_dir = Path(project_dir) / "derivatives" / "freesurfer"
            fs_dir.mkdir(parents=True, exist_ok=True)
            fs_file = fs_dir / "dataset_description.json"
            fs_file.write_text("{invalid json")

            # Should not raise an error
            ensure_dataset_descriptions(project_dir, ["freesurfer"])

            # File should still exist (not overwritten due to JSON parse error)
            assert fs_file.exists()


class TestBuildLogger:
    """Test build_logger function"""

    @patch("pre.common.get_path_manager")
    @patch("pre.common.logging_util.get_logger")
    def test_build_logger_creates_logger(self, mock_get_logger, mock_get_pm):
        """Test that logger is created with correct parameters"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm
        mock_pm.path.return_value = "/test/logs"

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.handlers = []

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = build_logger(
                step_name="test_step",
                subject_id="001",
                project_dir=tmpdir,
                debug=False,
                console=True,
            )

            # Verify PathManager was used
            assert mock_pm.project_dir == tmpdir
            mock_pm.path.assert_called_with("ti_logs", subject_id="001")

            # Verify logger was created
            mock_get_logger.assert_called_once()
            call_kwargs = mock_get_logger.call_args[1]
            assert call_kwargs["name"] == "pre.test_step.001"
            assert call_kwargs["console"] is True
            assert call_kwargs["overwrite"] is False

    @patch("pre.common.get_path_manager")
    @patch("pre.common.logging_util.get_logger")
    def test_build_logger_with_custom_log_file(self, mock_get_logger, mock_get_pm):
        """Test logger with custom log file path"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm
        mock_pm.path.return_value = "/test/logs"

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.handlers = []

        custom_log_file = "/custom/path/test.log"

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = build_logger(
                step_name="test_step",
                subject_id="001",
                project_dir=tmpdir,
                log_file=custom_log_file,
            )

            # Verify custom log file was used
            call_kwargs = mock_get_logger.call_args[1]
            assert call_kwargs["log_file"] == custom_log_file

    @patch("pre.common.get_path_manager")
    @patch("pre.common.logging_util.get_logger")
    def test_build_logger_debug_mode(self, mock_get_logger, mock_get_pm):
        """Test logger in debug mode"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm
        mock_pm.path.return_value = "/test/logs"

        mock_logger = MagicMock()
        mock_stream_handler = MagicMock(spec=logging.StreamHandler)
        mock_logger.handlers = [mock_stream_handler]
        mock_get_logger.return_value = mock_logger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = build_logger(
                step_name="test_step", subject_id="001", project_dir=tmpdir, debug=True
            )

            # Verify debug level was set on stream handler
            mock_stream_handler.setLevel.assert_called_with(logging.DEBUG)


class TestShouldOverwritePath:
    """Test should_overwrite_path wrapper function"""

    @patch("pre.common.core_should_overwrite_path")
    def test_should_overwrite_path_delegates_to_core(self, mock_core_should_overwrite):
        """Test that function delegates to core implementation"""
        from tit.core.overwrite import OverwritePolicy

        mock_core_should_overwrite.return_value = True

        path = Path("/test/path")
        policy = OverwritePolicy(overwrite=True, prompt=False)
        logger = MagicMock()
        label = "test_label"

        result = should_overwrite_path(path, policy=policy, logger=logger, label=label)

        mock_core_should_overwrite.assert_called_once_with(
            path, policy=policy, logger=logger, label=label
        )
        assert result is True


class TestCommandRunner:
    """Test CommandRunner class"""

    def test_command_runner_initialization(self):
        """Test CommandRunner initialization"""
        runner = CommandRunner()

        assert isinstance(runner.stop_event, threading.Event)
        assert not runner.stop_event.is_set()
        assert isinstance(runner._processes, set)
        assert len(runner._processes) == 0

    def test_command_runner_with_custom_stop_event(self):
        """Test CommandRunner with custom stop event"""
        stop_event = threading.Event()
        runner = CommandRunner(stop_event=stop_event)

        assert runner.stop_event is stop_event

    def test_request_stop_sets_event(self):
        """Test request_stop sets the stop event"""
        runner = CommandRunner()
        assert not runner.stop_event.is_set()

        runner.request_stop()

        assert runner.stop_event.is_set()

    @patch("pre.common._terminate_process")
    def test_request_stop_terminates_processes(self, mock_terminate):
        """Test request_stop terminates running processes"""
        runner = CommandRunner()

        # Add mock processes
        mock_proc1 = MagicMock()
        mock_proc2 = MagicMock()
        runner._processes.add(mock_proc1)
        runner._processes.add(mock_proc2)

        runner.request_stop()

        # Verify terminate was called for both processes
        assert mock_terminate.call_count == 2

    @patch("pre.common._terminate_process")
    def test_terminate_all(self, mock_terminate):
        """Test terminate_all terminates all processes"""
        runner = CommandRunner()

        mock_proc1 = MagicMock()
        mock_proc2 = MagicMock()
        runner._processes.add(mock_proc1)
        runner._processes.add(mock_proc2)

        runner.terminate_all()

        assert mock_terminate.call_count == 2

    def test_run_with_stop_event_already_set(self):
        """Test run raises PreprocessCancelled if stop_event is already set"""
        runner = CommandRunner()
        runner.stop_event.set()

        logger = MagicMock()

        with pytest.raises(PreprocessCancelled) as exc_info:
            runner.run(["echo", "test"], logger=logger)

        assert "cancelled before command start" in str(exc_info.value).lower()

    def test_run_with_empty_command(self):
        """Test run raises ValueError with empty command"""
        runner = CommandRunner()
        logger = MagicMock()

        with pytest.raises(ValueError) as exc_info:
            runner.run([], logger=logger)

        assert "empty" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_run_executes_command(self, mock_popen):
        """Test run executes command correctly"""
        runner = CommandRunner()
        logger = MagicMock()

        # Mock process with file-like stdout
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = ["line1\n", "line2\n", ""]
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        cmd = ["echo", "test"]
        exit_code = runner.run(cmd, logger=logger)

        # Verify command was executed
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0]
        assert call_args[0] == cmd

        # Verify exit code
        assert exit_code == 0

        # Verify logger was called
        assert logger.debug.called
        assert logger.info.call_count == 2  # Two lines of output

    @patch("subprocess.Popen")
    def test_run_logs_output(self, mock_popen):
        """Test run logs command output"""
        runner = CommandRunner()
        logger = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = [
            "output line 1\n",
            "output line 2\n",
            "output line 3\n",
            "",
        ]
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        runner.run(["test_cmd"], logger=logger)

        # Verify all output lines were logged
        info_calls = [call[0][0] for call in logger.info.call_args_list]
        assert "output line 1" in info_calls
        assert "output line 2" in info_calls
        assert "output line 3" in info_calls

    @patch("subprocess.Popen")
    def test_run_with_custom_cwd(self, mock_popen):
        """Test run with custom working directory"""
        runner = CommandRunner()
        logger = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = ""
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        cwd = "/custom/directory"
        runner.run(["test_cmd"], logger=logger, cwd=cwd)

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["cwd"] == cwd

    @patch("subprocess.Popen")
    def test_run_with_custom_env(self, mock_popen):
        """Test run with custom environment"""
        runner = CommandRunner()
        logger = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = ""
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        env = {"TEST_VAR": "test_value"}
        runner.run(["test_cmd"], logger=logger, env=env)

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["env"] == env

    @patch("subprocess.Popen")
    @patch("pre.common._terminate_process")
    def test_run_handles_stop_event_during_execution(self, mock_terminate, mock_popen):
        """Test run detects stop_event during command execution"""
        runner = CommandRunner()
        logger = MagicMock()

        # Mock stdout that yields lines, then sets stop event
        mock_stdout = MagicMock()
        call_count = 0

        def readline_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "line1\n"
            elif call_count == 2:
                runner.stop_event.set()  # Set stop event after first line
                return "line2\n"
            else:
                return ""

        mock_stdout.readline.side_effect = readline_side_effect
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_popen.return_value = mock_process

        with pytest.raises(PreprocessCancelled) as exc_info:
            runner.run(["test_cmd"], logger=logger)

        assert "cancelled" in str(exc_info.value).lower()
        mock_terminate.assert_called_once_with(mock_process)

    @patch("subprocess.Popen")
    def test_run_strips_whitespace_from_output(self, mock_popen):
        """Test run strips trailing whitespace from output lines"""
        runner = CommandRunner()
        logger = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = [
            "  line with spaces  \n",
            "\tline with tabs\t\n",
            "",
        ]
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        runner.run(["test_cmd"], logger=logger)

        # Verify whitespace was stripped
        info_calls = [call[0][0] for call in logger.info.call_args_list]
        assert "line with spaces" in info_calls
        assert "line with tabs" in info_calls

    @patch("subprocess.Popen")
    def test_run_skips_empty_lines(self, mock_popen):
        """Test run skips empty output lines"""
        runner = CommandRunner()
        logger = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = ["line1\n", "\n", "   \n", "line2\n", ""]
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        runner.run(["test_cmd"], logger=logger)

        # Verify only non-empty lines were logged
        info_calls = [call[0][0] for call in logger.info.call_args_list]
        assert len(info_calls) == 2
        assert "line1" in info_calls
        assert "line2" in info_calls

    @patch("subprocess.Popen")
    def test_run_returns_nonzero_exit_code(self, mock_popen):
        """Test run returns non-zero exit code on failure"""
        runner = CommandRunner()
        logger = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = ""
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 1
        mock_popen.return_value = mock_process

        exit_code = runner.run(["failing_cmd"], logger=logger)

        assert exit_code == 1

    @patch("subprocess.Popen")
    def test_run_cleans_up_process_from_set(self, mock_popen):
        """Test run removes process from _processes set after completion"""
        runner = CommandRunner()
        logger = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = ""
        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        assert len(runner._processes) == 0

        runner.run(["test_cmd"], logger=logger)

        # Process should be removed after completion
        assert len(runner._processes) == 0


class TestTerminateProcess:
    """Test _terminate_process function"""

    @patch("os.killpg")
    def test_terminate_process_unix(self, mock_killpg):
        """Test process termination on Unix systems"""
        if os.name == "nt":
            pytest.skip("Unix-specific test")

        mock_process = MagicMock()
        mock_process.pid = 12345

        _terminate_process(mock_process)

        # Verify killpg was called with SIGTERM
        import signal

        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)

    @patch("os.name", "nt")
    def test_terminate_process_windows(self):
        """Test process termination on Windows"""
        mock_process = MagicMock()

        _terminate_process(mock_process)

        # Verify terminate was called
        mock_process.terminate.assert_called_once()

    @patch("os.killpg", side_effect=Exception("killpg failed"))
    def test_terminate_process_fallback_on_error(self, mock_killpg):
        """Test terminate fallback when killpg fails"""
        if os.name == "nt":
            pytest.skip("Unix-specific test")

        mock_process = MagicMock()
        mock_process.pid = 12345

        # Should not raise exception
        _terminate_process(mock_process)

        # Verify fallback to terminate was called
        mock_process.terminate.assert_called_once()

    @patch("os.killpg", side_effect=Exception("killpg failed"))
    def test_terminate_process_handles_all_failures(self, mock_killpg):
        """Test terminate handles all failures gracefully"""
        if os.name == "nt":
            pytest.skip("Unix-specific test")

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.terminate.side_effect = Exception("terminate failed")

        # Should not raise exception even if both methods fail
        _terminate_process(mock_process)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
