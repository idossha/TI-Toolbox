#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox Error Handling Module
Centralized error handling and custom exceptions for the entire TI-Toolbox codebase.
"""

import logging
from typing import Optional, Dict, Any
from PyQt5 import QtWidgets


class TIToolboxError(Exception):
    """
    Base exception for all TI-Toolbox errors.

    Args:
        message: Human-readable error message
        error_code: Optional error code for categorization
        details: Optional dictionary with additional error details
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


class ProcessError(TIToolboxError):
    """
    Raised when a subprocess fails.

    Args:
        message: Error message
        return_code: Process exit code
        stderr: Standard error output
        command: The command that was executed
    """

    def __init__(
        self,
        message: str,
        return_code: Optional[int] = None,
        stderr: Optional[str] = None,
        command: Optional[str] = None,
    ):
        details = {}
        if return_code is not None:
            details["return_code"] = return_code
        if stderr:
            details["stderr"] = stderr
        if command:
            details["command"] = command
        super().__init__(message, error_code="PROCESS_ERROR", details=details)


class ValidationError(TIToolboxError):
    """
    Raised when input validation fails.

    Args:
        message: Error message
        field: Name of the field that failed validation
        value: The invalid value
    """

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = value
        super().__init__(message, error_code="VALIDATION_ERROR", details=details)


class FileNotFoundError(TIToolboxError):
    """
    Raised when a required file is not found.

    Args:
        message: Error message
        file_path: Path to the missing file
        file_type: Type of file (e.g., 'mesh', 'nifti', 'config')
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        file_type: Optional[str] = None,
    ):
        details = {}
        if file_path:
            details["file_path"] = file_path
        if file_type:
            details["file_type"] = file_type
        super().__init__(message, error_code="FILE_NOT_FOUND", details=details)


class ConfigurationError(TIToolboxError):
    """
    Raised when there's a configuration error.

    Args:
        message: Error message
        config_key: Configuration key that caused the error
        expected: Expected value or format
    """

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        expected: Optional[str] = None,
    ):
        details = {}
        if config_key:
            details["config_key"] = config_key
        if expected:
            details["expected"] = expected
        super().__init__(message, error_code="CONFIGURATION_ERROR", details=details)


class SubjectError(TIToolboxError):
    """
    Raised when there's an error related to a subject.

    Args:
        message: Error message
        subject_id: Subject identifier
        required_files: List of required files that are missing
    """

    def __init__(
        self,
        message: str,
        subject_id: Optional[str] = None,
        required_files: Optional[list] = None,
    ):
        details = {}
        if subject_id:
            details["subject_id"] = subject_id
        if required_files:
            details["required_files"] = required_files
        super().__init__(message, error_code="SUBJECT_ERROR", details=details)


class SimulationError(TIToolboxError):
    """
    Raised when a simulation fails.

    Args:
        message: Error message
        simulation_type: Type of simulation (TI, mTI, etc.)
        montage: Montage configuration that failed
    """

    def __init__(
        self,
        message: str,
        simulation_type: Optional[str] = None,
        montage: Optional[str] = None,
    ):
        details = {}
        if simulation_type:
            details["simulation_type"] = simulation_type
        if montage:
            details["montage"] = montage
        super().__init__(message, error_code="SIMULATION_ERROR", details=details)


class AnalysisError(TIToolboxError):
    """
    Raised when an analysis fails.

    Args:
        message: Error message
        analysis_type: Type of analysis (mesh, voxel, group)
        field: Field being analyzed (TImax, normE, etc.)
    """

    def __init__(
        self,
        message: str,
        analysis_type: Optional[str] = None,
        field: Optional[str] = None,
    ):
        details = {}
        if analysis_type:
            details["analysis_type"] = analysis_type
        if field:
            details["field"] = field
        super().__init__(message, error_code="ANALYSIS_ERROR", details=details)


class MeshError(TIToolboxError):
    """
    Raised when there's an error with mesh operations.

    Args:
        message: Error message
        mesh_file: Path to the mesh file
        element_count: Number of elements in mesh (if applicable)
    """

    def __init__(
        self,
        message: str,
        mesh_file: Optional[str] = None,
        element_count: Optional[int] = None,
    ):
        details = {}
        if mesh_file:
            details["mesh_file"] = mesh_file
        if element_count is not None:
            details["element_count"] = element_count
        super().__init__(message, error_code="MESH_ERROR", details=details)


# Error handling utilities


def handle_error(
    error: Exception,
    logger: Optional[logging.Logger] = None,
    gui_callback: Optional[callable] = None,
    show_dialog: bool = False,
    parent_widget: Optional[QtWidgets.QWidget] = None,
) -> None:
    """
    Centralized error handling with logging and optional GUI notification.

    Args:
        error: The exception to handle
        logger: Logger instance for error logging
        gui_callback: Optional callback function for GUI updates
        show_dialog: Whether to show a GUI error dialog
        parent_widget: Parent widget for error dialog
    """
    # Log the error
    if logger:
        if isinstance(error, TIToolboxError):
            logger.error(f"{error.error_code}: {error.message}", extra=error.details)
        else:
            logger.error(f"Unexpected error: {str(error)}", exc_info=True)

    # Call GUI callback if provided
    if gui_callback:
        try:
            gui_callback(str(error))
        except Exception as e:
            if logger:
                logger.error(f"Error in GUI callback: {e}")

    # Show error dialog if requested
    if show_dialog:
        show_error_dialog(error, parent_widget)


def show_error_dialog(
    error: Exception, parent: Optional[QtWidgets.QWidget] = None, title: str = "Error"
) -> None:
    """
    Show a GUI error dialog.

    Args:
        error: The exception to display
        parent: Parent widget for the dialog
        title: Dialog title
    """
    msg_box = QtWidgets.QMessageBox(parent)
    msg_box.setIcon(QtWidgets.QMessageBox.Critical)
    msg_box.setWindowTitle(title)

    if isinstance(error, TIToolboxError):
        msg_box.setText(error.message)

        # Add detailed information if available
        if error.details:
            details_text = "\n".join([f"{k}: {v}" for k, v in error.details.items()])
            msg_box.setDetailedText(details_text)
    else:
        msg_box.setText(str(error))

    msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
    msg_box.exec_()


def validate_file_exists(file_path: str, file_type: str = "file") -> None:
    """
    Validate that a file exists, raise FileNotFoundError if not.

    Args:
        file_path: Path to the file
        file_type: Type of file for error message

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    from pathlib import Path

    if not Path(file_path).exists():
        raise FileNotFoundError(
            f"Required {file_type} not found: {file_path}",
            file_path=file_path,
            file_type=file_type,
        )


def validate_subject(subject_id: str, project_dir: str) -> None:
    """
    Validate that a subject exists and has required files.

    Args:
        subject_id: Subject identifier
        project_dir: Project directory path

    Raises:
        SubjectError: If subject doesn't exist or is invalid
    """
    from pathlib import Path
    from . import constants

    subject_dir = Path(project_dir) / subject_id

    if not subject_dir.exists():
        raise SubjectError(
            f"Subject directory not found: {subject_id}", subject_id=subject_id
        )

    # Check for required files
    required_files = []
    for req_file in constants.REQUIRED_SUBJECT_FILES:
        anat_dir = subject_dir / "anat"
        if not (anat_dir / req_file).exists():
            required_files.append(req_file)

    if required_files:
        raise SubjectError(
            f"Subject {subject_id} is missing required files",
            subject_id=subject_id,
            required_files=required_files,
        )


def validate_montage_config(montage_config: dict) -> None:
    """
    Validate montage configuration.

    Args:
        montage_config: Montage configuration dictionary

    Raises:
        ValidationError: If configuration is invalid
    """
    required_keys = ["electrodes", "intensities"]

    for key in required_keys:
        if key not in montage_config:
            raise ValidationError(
                f"Missing required key in montage configuration: {key}", field=key
            )

    # Validate electrode count matches intensity count
    if len(montage_config["electrodes"]) != len(montage_config["intensities"]):
        raise ValidationError(
            "Number of electrodes must match number of intensities",
            field="electrodes/intensities",
            value=f"electrodes={len(montage_config['electrodes'])}, intensities={len(montage_config['intensities'])}",
        )


# Export all error classes and utilities
__all__ = [
    "TIToolboxError",
    "ProcessError",
    "ValidationError",
    "FileNotFoundError",
    "ConfigurationError",
    "SubjectError",
    "SimulationError",
    "AnalysisError",
    "MeshError",
    "handle_error",
    "show_error_dialog",
    "validate_file_exists",
    "validate_subject",
    "validate_montage_config",
]
