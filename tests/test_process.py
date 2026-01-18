#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox process management module (core/process.py)
"""

import pytest
import subprocess
import sys
import os
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt5 import QtCore

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from core.process import (
    strip_ansi_codes,
    MessageParser,
    ProcessRunner,
    SimulatorMessageParser,
    AnalyzerMessageParser,
    PreprocessMessageParser,
)


class TestStripAnsiCodes:
    """Test strip_ansi_codes function"""

    def test_strip_basic_colors(self):
        """Test stripping basic ANSI color codes"""
        text_with_codes = "\x1b[31mRed text\x1b[0m"
        cleaned = strip_ansi_codes(text_with_codes)
        assert cleaned == "Red text"

    def test_strip_complex_codes(self):
        """Test stripping complex ANSI sequences"""
        text_with_codes = "\x1b[1;32mBold Green\x1b[0m"
        cleaned = strip_ansi_codes(text_with_codes)
        assert cleaned == "Bold Green"

    def test_strip_multiple_codes(self):
        """Test stripping text with multiple ANSI codes"""
        text = "\x1b[31mRed\x1b[0m and \x1b[32mGreen\x1b[0m"
        cleaned = strip_ansi_codes(text)
        assert cleaned == "Red and Green"

    def test_plain_text_unchanged(self):
        """Test that plain text without codes is unchanged"""
        text = "Plain text without codes"
        cleaned = strip_ansi_codes(text)
        assert cleaned == text

    def test_empty_string(self):
        """Test handling of empty string"""
        cleaned = strip_ansi_codes("")
        assert cleaned == ""


class TestMessageParser:
    """Test MessageParser base class"""

    def setup_method(self):
        """Setup before each test method"""
        self.parser = MessageParser()

    def test_parse_plain_text(self):
        """Test parsing plain text"""
        line = "This is a normal log line"
        cleaned, msg_type = self.parser.parse(line)
        assert cleaned == line
        assert msg_type == "default"

    def test_parse_error_message(self):
        """Test parsing error messages"""
        test_cases = [
            "ERROR: Something went wrong",
            "[ERROR] Failed to process",
            "error: file not found",
            "Critical: System failure",
        ]
        for line in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type == "error", f"Failed for: {line}"

    def test_parse_warning_message(self):
        """Test parsing warning messages"""
        test_cases = [
            "WARNING: Deprecated function",
            "[WARNING] Low memory",
            "warn: performance issue",
        ]
        for line in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type == "warning", f"Failed for: {line}"

    def test_parse_info_message(self):
        """Test parsing info messages"""
        test_cases = [
            "[INFO] Processing started",
            "Processing data...",
            "Starting simulation...",
            "Loading mesh file...",
        ]
        for line in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type in ["info", "default"], f"Failed for: {line}"

    def test_parse_success_message(self):
        """Test parsing success messages"""
        test_cases = [
            "[SUCCESS] Operation completed",
            "Completed successfully",
            "✓ Complete",
        ]
        for line in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type == "success", f"Failed for: {line}"

    def test_parse_command_message(self):
        """Test parsing command messages"""
        test_cases = [
            "Executing: simnibs_python script.py",
            "Running command: msh2cortex",
            "command: analyze",
        ]
        for line in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type == "command", f"Failed for: {line}"

    def test_parse_with_ansi_codes(self):
        """Test parsing removes ANSI codes"""
        line = "\x1b[31mERROR: Red error message\x1b[0m"
        cleaned, msg_type = self.parser.parse(line)
        assert "\x1b" not in cleaned
        assert msg_type == "error"

    def test_parse_empty_line(self):
        """Test parsing empty lines"""
        cleaned, msg_type = self.parser.parse("")
        assert cleaned == ""
        assert msg_type == "default"

    def test_parse_whitespace_only(self):
        """Test parsing whitespace-only lines"""
        cleaned, msg_type = self.parser.parse("   \t   ")
        assert cleaned == ""
        assert msg_type == "default"


class TestSimulatorMessageParser:
    """Test SimulatorMessageParser class"""

    def setup_method(self):
        """Setup before each test method"""
        self.parser = SimulatorMessageParser()

    def test_simulator_specific_patterns(self):
        """Test simulator-specific message patterns"""
        test_cases = [
            ("Beginning simulation for montage1", "info"),
            ("Montage visualization: /path/to/image.png", "info"),
            ("SimNIBS simulation: Starting", "info"),
            ("Field extraction: Complete", "info"),
            ("NIfTI transformation: In progress", "info"),
            ("Results processing: Done", "info"),
        ]
        for line, expected_type in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type == expected_type, f"Failed for: {line}"

    def test_fallback_to_base_parser(self):
        """Test that non-simulator messages use base parser"""
        line = "ERROR: General error"
        cleaned, msg_type = self.parser.parse(line)
        assert msg_type == "error"


class TestAnalyzerMessageParser:
    """Test AnalyzerMessageParser class"""

    def setup_method(self):
        """Setup before each test method"""
        self.parser = AnalyzerMessageParser()

    def test_analyzer_specific_patterns(self):
        """Test analyzer-specific message patterns"""
        test_cases = [
            ("Beginning analysis for subject 001", "info"),
            ("Field data loading: Complete", "info"),
            ("Cortical analysis: Processing ROI", "info"),
            ("Spherical analysis: Computing stats", "info"),
            ("Results saving: /path/to/results.csv", "info"),
            # "completed successfully" is matched by the base MessageParser as 'success'
            ("Analysis completed successfully", "success"),
        ]
        for line, expected_type in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type == expected_type, f"Failed for: {line}"


class TestPreprocessMessageParser:
    """Test PreprocessMessageParser class"""

    def setup_method(self):
        """Setup before each test method"""
        self.parser = PreprocessMessageParser()

    def test_preprocess_specific_patterns(self):
        """Test preprocessing-specific message patterns"""
        test_cases = [
            ("Beginning pre-processing for subject 001", "info"),
            ("DICOM conversion: Started", "info"),
            # "running" is matched by base MessageParser as 'command' before preprocess parser sees it
            ("SimNIBS CHARM: Running", "command"),
            ("FreeSurfer recon-all: In progress", "info"),
            # "processing" is matched by base MessageParser as 'info'
            ("Tissue analysis: Processing", "info"),
            ("DICOM conversion: started", "info"),
            ("Pre-processing completed", "info"),
        ]
        for line, expected_type in test_cases:
            cleaned, msg_type = self.parser.parse(line)
            assert msg_type == expected_type, f"Failed for: {line}"

    def test_preprocess_failure_detection(self):
        """Test detection of preprocessing failures"""
        line = "DICOM conversion: ✗ failed"
        cleaned, msg_type = self.parser.parse(line)
        assert msg_type == "error"


class TestProcessRunner:
    """Test ProcessRunner class"""

    def setup_method(self):
        """Setup before each test method"""
        # Create a Qt application for testing
        if not QtCore.QCoreApplication.instance():
            self.app = QtCore.QCoreApplication([])

    def test_runner_initialization(self):
        """Test ProcessRunner initialization"""
        cmd = ["echo", "test"]
        runner = ProcessRunner(cmd)

        assert runner.cmd == cmd
        assert runner.process is None
        assert runner.terminated is False
        assert runner.stdin_data is None

    def test_runner_with_custom_env(self):
        """Test ProcessRunner with custom environment"""
        cmd = ["echo", "test"]
        env = {"TEST_VAR": "test_value"}
        runner = ProcessRunner(cmd, env=env)

        assert runner.env["TEST_VAR"] == "test_value"

    def test_runner_with_stdin_data(self):
        """Test ProcessRunner with stdin data"""
        cmd = ["cat"]
        stdin_data = ["line1", "line2", "line3"]
        runner = ProcessRunner(cmd, stdin_data=stdin_data)

        assert runner.stdin_data == stdin_data

    def test_runner_with_custom_parser(self):
        """Test ProcessRunner with custom message parser"""
        cmd = ["echo", "test"]
        parser = SimulatorMessageParser()
        runner = ProcessRunner(cmd, message_parser=parser)

        assert isinstance(runner.message_parser, SimulatorMessageParser)

    def test_runner_with_cwd(self):
        """Test ProcessRunner with custom working directory"""
        cmd = ["pwd"]
        cwd = "/tmp"
        runner = ProcessRunner(cmd, cwd=cwd)

        assert runner.cwd == cwd

    @patch("subprocess.Popen")
    def test_runner_execution_simple_command(self, mock_popen):
        """Test ProcessRunner execution with simple command"""
        # Setup mock process
        mock_process = MagicMock()
        mock_process.stdout = iter(["test output\n"])
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        cmd = ["echo", "test"]
        runner = ProcessRunner(cmd)

        # Collect output
        outputs = []
        runner.output_signal.connect(lambda msg, typ: outputs.append((msg, typ)))

        # Run in current thread for testing
        runner.run()

        # Verify process was created correctly
        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args[1]
        assert "PYTHONUNBUFFERED" in call_kwargs["env"]
        assert call_kwargs["env"]["PYTHONUNBUFFERED"] == "1"

    def test_runner_terminate_when_not_running(self):
        """Test terminating when process is not running"""
        runner = ProcessRunner(["echo", "test"])
        result = runner.terminate_process()
        assert result is False  # Should return False when no process running

    @patch("subprocess.Popen")
    def test_runner_terminate_running_process(self, mock_popen):
        """Test terminating a running process"""
        # Setup mock process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process still running
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        runner = ProcessRunner(["sleep", "100"])
        runner.process = mock_process

        result = runner.terminate_process()

        assert result is True
        assert runner.terminated is True
        mock_process.terminate.assert_called()


class TestProcessRunnerSignals:
    """Test ProcessRunner signal emissions"""

    def setup_method(self):
        """Setup before each test method"""
        if not QtCore.QCoreApplication.instance():
            self.app = QtCore.QCoreApplication([])

    def test_output_signal_emission(self):
        """Test that output signal is emitted correctly"""
        runner = ProcessRunner(["echo", "test"])
        outputs = []

        runner.output_signal.connect(lambda msg, typ: outputs.append((msg, typ)))

        # Manually emit signal for testing
        runner.output_signal.emit("Test message", "info")

        assert len(outputs) == 1
        assert outputs[0] == ("Test message", "info")

    def test_finished_signal_emission(self):
        """Test that finished signal is emitted correctly"""
        runner = ProcessRunner(["echo", "test"])
        exit_codes = []

        runner.finished_signal.connect(lambda code: exit_codes.append(code))

        # Manually emit signal for testing
        runner.finished_signal.emit(0)

        assert len(exit_codes) == 1
        assert exit_codes[0] == 0

    def test_error_signal_emission(self):
        """Test that error signal is emitted correctly"""
        runner = ProcessRunner(["echo", "test"])
        errors = []

        runner.error_signal.connect(lambda msg: errors.append(msg))

        # Manually emit signal for testing
        runner.error_signal.emit("Test error")

        assert len(errors) == 1
        assert errors[0] == "Test error"

    def test_progress_signal_emission(self):
        """Test that progress signal is emitted correctly"""
        runner = ProcessRunner(["echo", "test"])
        progress_values = []

        runner.progress_signal.connect(lambda val: progress_values.append(val))

        # Manually emit signal for testing
        runner.progress_signal.emit(50)

        assert len(progress_values) == 1
        assert progress_values[0] == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
