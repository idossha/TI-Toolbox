#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox error handling module (core/errors.py)
"""

import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys
import os

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from core import errors
from core.errors import (
    TIToolboxError,
    ProcessError,
    ValidationError,
    FileNotFoundError,
    ConfigurationError,
    SubjectError,
    SimulationError,
    AnalysisError,
    MeshError,
    handle_error,
    show_error_dialog,
    validate_file_exists,
    validate_montage_config,
)


class TestTIToolboxError:
    """Test base TIToolboxError class"""

    def test_basic_error_creation(self):
        """Test creating a basic error"""
        error = TIToolboxError("Test error message")
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.error_code is None
        assert error.details == {}

    def test_error_with_code(self):
        """Test error with error code"""
        error = TIToolboxError("Test error", error_code="TEST_ERR")
        assert str(error) == "[TEST_ERR] Test error"
        assert error.error_code == "TEST_ERR"

    def test_error_with_details(self):
        """Test error with details dictionary"""
        details = {"field": "test_field", "value": 123}
        error = TIToolboxError("Test error", details=details)
        assert error.details == details

    def test_error_to_dict(self):
        """Test converting error to dictionary"""
        error = TIToolboxError(
            "Test error", error_code="TEST_ERR", details={"key": "value"}
        )
        error_dict = error.to_dict()

        assert error_dict["type"] == "TIToolboxError"
        assert error_dict["message"] == "Test error"
        assert error_dict["error_code"] == "TEST_ERR"
        assert error_dict["details"] == {"key": "value"}


class TestProcessError:
    """Test ProcessError class"""

    def test_process_error_basic(self):
        """Test basic process error"""
        error = ProcessError("Process failed")
        assert error.message == "Process failed"
        assert error.error_code == "PROCESS_ERROR"

    def test_process_error_with_return_code(self):
        """Test process error with return code"""
        error = ProcessError("Process failed", return_code=1)
        assert error.details["return_code"] == 1

    def test_process_error_with_stderr(self):
        """Test process error with stderr"""
        stderr_output = "Error: file not found"
        error = ProcessError("Process failed", stderr=stderr_output)
        assert error.details["stderr"] == stderr_output

    def test_process_error_with_command(self):
        """Test process error with command"""
        command = "simnibs_python script.py"
        error = ProcessError("Process failed", command=command)
        assert error.details["command"] == command

    def test_process_error_complete(self):
        """Test process error with all parameters"""
        error = ProcessError(
            "Process failed",
            return_code=127,
            stderr="Command not found",
            command="nonexistent_command",
        )
        assert error.details["return_code"] == 127
        assert error.details["stderr"] == "Command not found"
        assert error.details["command"] == "nonexistent_command"


class TestValidationError:
    """Test ValidationError class"""

    def test_validation_error_basic(self):
        """Test basic validation error"""
        error = ValidationError("Invalid input")
        assert error.message == "Invalid input"
        assert error.error_code == "VALIDATION_ERROR"

    def test_validation_error_with_field(self):
        """Test validation error with field name"""
        error = ValidationError("Invalid value", field="intensity")
        assert error.details["field"] == "intensity"

    def test_validation_error_with_value(self):
        """Test validation error with invalid value"""
        error = ValidationError("Invalid value", field="radius", value=-5)
        assert error.details["field"] == "radius"
        assert error.details["value"] == -5


class TestFileNotFoundError:
    """Test FileNotFoundError class"""

    def test_file_not_found_basic(self):
        """Test basic file not found error"""
        error = FileNotFoundError("File missing")
        assert error.message == "File missing"
        assert error.error_code == "FILE_NOT_FOUND"

    def test_file_not_found_with_path(self):
        """Test file not found error with path"""
        path = "/path/to/missing/file.msh"
        error = FileNotFoundError("Mesh file not found", file_path=path)
        assert error.details["file_path"] == path

    def test_file_not_found_with_type(self):
        """Test file not found error with file type"""
        error = FileNotFoundError(
            "Missing file", file_path="/path/file.nii.gz", file_type="nifti"
        )
        assert error.details["file_type"] == "nifti"
        assert error.details["file_path"] == "/path/file.nii.gz"


class TestConfigurationError:
    """Test ConfigurationError class"""

    def test_config_error_basic(self):
        """Test basic configuration error"""
        error = ConfigurationError("Invalid configuration")
        assert error.message == "Invalid configuration"
        assert error.error_code == "CONFIGURATION_ERROR"

    def test_config_error_with_key(self):
        """Test configuration error with config key"""
        error = ConfigurationError("Missing key", config_key="electrode_positions")
        assert error.details["config_key"] == "electrode_positions"

    def test_config_error_with_expected(self):
        """Test configuration error with expected value"""
        error = ConfigurationError(
            "Invalid format", config_key="intensities", expected="list of floats"
        )
        assert error.details["config_key"] == "intensities"
        assert error.details["expected"] == "list of floats"


class TestSubjectError:
    """Test SubjectError class"""

    def test_subject_error_basic(self):
        """Test basic subject error"""
        error = SubjectError("Subject not found")
        assert error.message == "Subject not found"
        assert error.error_code == "SUBJECT_ERROR"

    def test_subject_error_with_id(self):
        """Test subject error with subject ID"""
        error = SubjectError("Subject invalid", subject_id="001")
        assert error.details["subject_id"] == "001"

    def test_subject_error_with_required_files(self):
        """Test subject error with missing files"""
        required = ["T1.nii.gz", "T2.nii.gz"]
        error = SubjectError("Missing files", subject_id="002", required_files=required)
        assert error.details["subject_id"] == "002"
        assert error.details["required_files"] == required


class TestSimulationError:
    """Test SimulationError class"""

    def test_simulation_error_basic(self):
        """Test basic simulation error"""
        error = SimulationError("Simulation failed")
        assert error.message == "Simulation failed"
        assert error.error_code == "SIMULATION_ERROR"

    def test_simulation_error_with_type(self):
        """Test simulation error with simulation type"""
        error = SimulationError("Failed", simulation_type="TI")
        assert error.details["simulation_type"] == "TI"

    def test_simulation_error_with_montage(self):
        """Test simulation error with montage"""
        error = SimulationError(
            "Electrode positioning failed", simulation_type="mTI", montage="4x1_montage"
        )
        assert error.details["simulation_type"] == "mTI"
        assert error.details["montage"] == "4x1_montage"


class TestAnalysisError:
    """Test AnalysisError class"""

    def test_analysis_error_basic(self):
        """Test basic analysis error"""
        error = AnalysisError("Analysis failed")
        assert error.message == "Analysis failed"
        assert error.error_code == "ANALYSIS_ERROR"

    def test_analysis_error_with_type(self):
        """Test analysis error with analysis type"""
        error = AnalysisError("Failed", analysis_type="mesh")
        assert error.details["analysis_type"] == "mesh"

    def test_analysis_error_with_field(self):
        """Test analysis error with field name"""
        error = AnalysisError("Invalid field", analysis_type="voxel", field="normE")
        assert error.details["analysis_type"] == "voxel"
        assert error.details["field"] == "normE"


class TestMeshError:
    """Test MeshError class"""

    def test_mesh_error_basic(self):
        """Test basic mesh error"""
        error = MeshError("Mesh loading failed")
        assert error.message == "Mesh loading failed"
        assert error.error_code == "MESH_ERROR"

    def test_mesh_error_with_file(self):
        """Test mesh error with mesh file path"""
        error = MeshError("Invalid mesh", mesh_file="/path/to/mesh.msh")
        assert error.details["mesh_file"] == "/path/to/mesh.msh"

    def test_mesh_error_with_element_count(self):
        """Test mesh error with element count"""
        error = MeshError("Too few elements", mesh_file="field.msh", element_count=100)
        assert error.details["mesh_file"] == "field.msh"
        assert error.details["element_count"] == 100


class TestHandleError:
    """Test handle_error utility function"""

    def test_handle_error_with_logger(self):
        """Test error handling with logger"""
        mock_logger = Mock(spec=logging.Logger)
        error = TIToolboxError("Test error", error_code="TEST")

        handle_error(error, logger=mock_logger)

        mock_logger.error.assert_called_once()

    def test_handle_error_with_callback(self):
        """Test error handling with GUI callback"""
        mock_callback = Mock()
        error = ProcessError("Process failed", return_code=1)

        handle_error(error, gui_callback=mock_callback)

        mock_callback.assert_called_once()
        args = mock_callback.call_args[0]
        assert "Process failed" in args[0]

    def test_handle_error_non_titoolbox_error(self):
        """Test handling of standard Python exceptions"""
        mock_logger = Mock(spec=logging.Logger)
        error = ValueError("Standard Python error")

        handle_error(error, logger=mock_logger)

        mock_logger.error.assert_called_once()

    def test_handle_error_callback_failure(self):
        """Test that callback failures are handled gracefully"""
        mock_logger = Mock(spec=logging.Logger)
        mock_callback = Mock(side_effect=Exception("Callback error"))
        error = TIToolboxError("Test error")

        # Should not raise exception
        handle_error(error, logger=mock_logger, gui_callback=mock_callback)

        # Should have logged the callback error
        assert mock_logger.error.call_count == 2  # Original error + callback error


class TestValidateFileExists:
    """Test validate_file_exists utility function"""

    def test_validate_file_exists_valid(self, tmp_path):
        """Test validation with existing file"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Should not raise exception
        validate_file_exists(str(test_file), "text")

    def test_validate_file_exists_missing(self):
        """Test validation with missing file"""
        with pytest.raises(FileNotFoundError) as exc_info:
            validate_file_exists("/nonexistent/path/file.txt", "mesh")

        assert "mesh" in str(exc_info.value)
        assert "/nonexistent/path/file.txt" in str(exc_info.value)
        assert exc_info.value.details["file_path"] == "/nonexistent/path/file.txt"
        assert exc_info.value.details["file_type"] == "mesh"


class TestValidateMontageConfig:
    """Test validate_montage_config utility function"""

    def test_validate_montage_valid(self):
        """Test validation with valid montage config"""
        config = {
            "electrodes": ["E1", "E2", "E3", "E4"],
            "intensities": [0.001, -0.001, 0.001, -0.001],
        }

        # Should not raise exception
        validate_montage_config(config)

    def test_validate_montage_missing_electrodes(self):
        """Test validation with missing electrodes key"""
        config = {"intensities": [0.001, -0.001]}

        with pytest.raises(ValidationError) as exc_info:
            validate_montage_config(config)

        assert "electrodes" in str(exc_info.value)
        assert exc_info.value.details["field"] == "electrodes"

    def test_validate_montage_missing_intensities(self):
        """Test validation with missing intensities key"""
        config = {"electrodes": ["E1", "E2"]}

        with pytest.raises(ValidationError) as exc_info:
            validate_montage_config(config)

        assert "intensities" in str(exc_info.value)
        assert exc_info.value.details["field"] == "intensities"

    def test_validate_montage_mismatched_lengths(self):
        """Test validation with mismatched electrode/intensity counts"""
        config = {
            "electrodes": ["E1", "E2", "E3"],
            "intensities": [0.001, -0.001],  # Only 2 intensities for 3 electrodes
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_montage_config(config)

        assert "must match" in str(exc_info.value).lower()
        assert exc_info.value.details["field"] == "electrodes/intensities"


class TestShowErrorDialog:
    """Test show_error_dialog utility function"""

    @patch("core.errors.QtWidgets.QMessageBox")
    def test_show_error_dialog_titoolbox_error(self, mock_messagebox):
        """Test showing dialog for TIToolbox error"""
        error = TIToolboxError(
            "Test error", error_code="TEST", details={"key": "value"}
        )

        mock_box = MagicMock()
        mock_messagebox.return_value = mock_box

        show_error_dialog(error)

        mock_box.setText.assert_called_once_with("Test error")
        mock_box.setDetailedText.assert_called_once()
        mock_box.exec_.assert_called_once()

    @patch("core.errors.QtWidgets.QMessageBox")
    def test_show_error_dialog_standard_error(self, mock_messagebox):
        """Test showing dialog for standard Python exception"""
        error = ValueError("Standard error")

        mock_box = MagicMock()
        mock_messagebox.return_value = mock_box

        show_error_dialog(error)

        mock_box.setText.assert_called_once_with("Standard error")
        mock_box.exec_.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
