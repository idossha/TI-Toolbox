#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Pre-Process Tab
This module provides a GUI interface for the pre-processing functionality.
Thread-safe version with deadlock prevention.
"""

import json
import os
import glob
import tempfile
import time
import multiprocessing

from PyQt5 import QtWidgets, QtCore, QtGui
from tit.gui.confirmation_dialog import ConfirmationDialog
from tit.gui.components.console import (
    ConsoleWidget,
    format_message,
    append_with_autoscroll,
)
from tit.gui.components.action_buttons import RunStopButtons
from tit.gui.components.base_thread import BaseProcessThread
from tit.paths import get_path_manager
from tit import constants as const
from tit.pre import discover_subjects, check_m2m_exists
from tit.gui.style import FONT_SM, FONT_HELP, FONT_SUBHEADING
from tit.gui.components.qsi_config_dialogs import (
    QSIPrepConfigDialog,
    QSIReconConfigDialog,
)


class PreProcessThread(BaseProcessThread):
    """Run tit.pre via subprocess, streaming output to the GUI."""

    def __init__(self, cmd, env=None):
        super().__init__(cmd=cmd, env=env)

    def run(self):
        self.execute_process()


class PreProcessTab(QtWidgets.QWidget):
    """Tab for pre-processing functionality."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Initialize path manager
        self.pm = get_path_manager()

        # Get the project directory using PathManager
        self.project_dir = self.pm.project_dir

        self.processing_running = False
        self.processing_thread = None
        self.PROC_START_TIME = None
        self.STEP_START_TIMES = {}
        self._preproc_had_failures = False
        self._summary_started = False
        self._summary_finished = False
        self._last_plain_output_line = None
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface for the pre-process tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # Create a scroll area for the form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(200)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)

        # Add status label at the top
        self.status_label = QtWidgets.QLabel()
        self.status_label.setText("Processing... Only the Stop button is available")
        self.status_label.setStyleSheet(
            f"QLabel {{ background-color: white; color: #f44336;"
            f" padding: 4px 8px; border-radius: 3px;"
            f" font-weight: bold; font-size: {FONT_SUBHEADING}; }}"
        )
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.hide()  # Initially hidden
        scroll_layout.addWidget(self.status_label)

        # Create a horizontal layout for subject selection and options
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(20)  # Set consistent spacing
        content_layout.setContentsMargins(20, 0, 20, 20)  # Removed top margin

        # Subject selection section
        subject_widget = QtWidgets.QWidget()
        subject_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        subject_main_layout = QtWidgets.QVBoxLayout(subject_widget)
        subject_main_layout.setContentsMargins(10, 0, 10, 10)  # Removed top margin

        subject_label = QtWidgets.QLabel("Available Subjects:")
        subject_label.setStyleSheet("font-weight: bold;")
        subject_main_layout.addWidget(subject_label)

        # Subject list with selection
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QListWidget.ExtendedSelection)
        self.subject_list.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        subject_main_layout.addWidget(self.subject_list, 1)

        # Selection buttons frame
        button_frame = QtWidgets.QFrame()
        selection_buttons_layout = QtWidgets.QHBoxLayout(button_frame)
        selection_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.select_all_btn = QtWidgets.QPushButton("Select All")
        self.select_none_btn = QtWidgets.QPushButton("Select None")
        self.refresh_subjects_btn = QtWidgets.QPushButton("Refresh")

        self.select_all_btn.clicked.connect(self.select_all_subjects)
        self.select_none_btn.clicked.connect(self.select_no_subjects)
        self.refresh_subjects_btn.clicked.connect(self.update_available_subjects)

        selection_buttons_layout.addWidget(self.select_all_btn)
        selection_buttons_layout.addWidget(self.select_none_btn)
        selection_buttons_layout.addWidget(self.refresh_subjects_btn)
        selection_buttons_layout.addStretch()
        subject_main_layout.addWidget(button_frame)

        # Add subject widget to content layout with stretch
        content_layout.addWidget(subject_widget, 1)  # Add stretch factor to fill space

        # Options section
        options_widget = QtWidgets.QWidget()
        options_widget.setMinimumWidth(336)
        options_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
        )
        options_layout = QtWidgets.QVBoxLayout(options_widget)
        options_layout.setContentsMargins(10, 10, 10, 10)

        # Pre-processing options group
        self.options_group = QtWidgets.QGroupBox("Processing Options")
        options_group_layout = QtWidgets.QVBoxLayout(self.options_group)
        options_group_layout.setSpacing(10)  # Consistent spacing between options

        # DICOM conversion options
        self.convert_dicom_cb = QtWidgets.QCheckBox("Convert DICOM files to NIfTI")
        self.convert_dicom_cb.setChecked(True)
        options_group_layout.addWidget(self.convert_dicom_cb)

        # FreeSurfer options
        self.run_recon_cb = QtWidgets.QCheckBox("Run FreeSurfer recon-all")
        self.run_recon_cb.setChecked(True)
        options_group_layout.addWidget(self.run_recon_cb)

        # Parallel processing with checkbox and cores input on same line
        parallel_layout = QtWidgets.QHBoxLayout()
        self.parallel_cb = QtWidgets.QCheckBox("Run recon-all in parallel")
        self.parallel_cb.setEnabled(True)
        parallel_layout.addWidget(self.parallel_cb, 0)

        available_cores = multiprocessing.cpu_count()
        self.cores_spin = QtWidgets.QSpinBox()
        self.cores_spin.setRange(1, available_cores)
        self.cores_spin.setValue(available_cores)
        self.cores_spin.setFixedWidth(60)
        parallel_layout.addWidget(self.cores_spin, 0)
        parallel_layout.addStretch(1)
        options_group_layout.addLayout(parallel_layout)

        # Add small comment below
        parallel_comment = QtWidgets.QLabel(
            f"   {available_cores} cores available on this system"
        )
        parallel_comment.setStyleSheet(f"color: #888888; font-size: {FONT_SM};")
        options_group_layout.addWidget(parallel_comment)

        # Enable spinbox based on checkbox
        self.parallel_cb.toggled.connect(
            lambda checked: self.cores_spin.setEnabled(checked)
        )
        self.cores_spin.setEnabled(self.parallel_cb.isChecked())

        self.create_m2m_cb = QtWidgets.QCheckBox("Create SimNIBS m2m folder")
        self.create_m2m_cb.setChecked(True)
        self.create_m2m_cb.setToolTip(
            "SimNIBS charm processes run one at a time (sequential) to prevent PETSC conflicts, but each uses full CPU power"
        )
        options_group_layout.addWidget(self.create_m2m_cb)

        # Tissue analyzer option
        self.run_tissue_analyzer_cb = QtWidgets.QCheckBox("Run Tissue Analyzer")
        self.run_tissue_analyzer_cb.setChecked(False)
        self.run_tissue_analyzer_cb.setToolTip(
            "Analyze tissue volume and thickness using tissue analyzer and generate figures alongside preprocessing"
        )
        options_group_layout.addWidget(self.run_tissue_analyzer_cb)

        # Separator for DWI section
        dwi_separator = QtWidgets.QFrame()
        dwi_separator.setFrameShape(QtWidgets.QFrame.HLine)
        dwi_separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        options_group_layout.addWidget(dwi_separator)

        dwi_label = QtWidgets.QLabel("DWI Processing (Docker)")
        dwi_label.setStyleSheet(
            f"color: #888888; font-size: {FONT_SM}; font-weight: normal;"
        )
        options_group_layout.addWidget(dwi_label)

        # QSIPrep option with gear button
        qsiprep_layout = QtWidgets.QHBoxLayout()
        self.run_qsiprep_cb = QtWidgets.QCheckBox("Run QSIPrep")
        self.run_qsiprep_cb.setChecked(False)
        self.run_qsiprep_cb.setToolTip(
            "Run QSIPrep DWI preprocessing via Docker (requires Docker socket access)"
        )
        qsiprep_layout.addWidget(self.run_qsiprep_cb)

        self.qsiprep_config_btn = QtWidgets.QPushButton()
        self.qsiprep_config_btn.setIcon(
            self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView)
        )
        self.qsiprep_config_btn.setFixedSize(24, 24)
        self.qsiprep_config_btn.setToolTip("Configure QSIPrep parameters")
        self.qsiprep_config_btn.clicked.connect(self.open_qsiprep_config)
        qsiprep_layout.addWidget(self.qsiprep_config_btn)
        qsiprep_layout.addStretch()
        options_group_layout.addLayout(qsiprep_layout)

        # QSIRecon option with gear button
        qsirecon_layout = QtWidgets.QHBoxLayout()
        self.run_qsirecon_cb = QtWidgets.QCheckBox("Run QSIRecon")
        self.run_qsirecon_cb.setChecked(False)
        self.run_qsirecon_cb.setToolTip(
            "Run QSIRecon reconstruction via Docker (requires QSIPrep output)"
        )
        qsirecon_layout.addWidget(self.run_qsirecon_cb)

        self.qsirecon_config_btn = QtWidgets.QPushButton()
        self.qsirecon_config_btn.setIcon(
            self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView)
        )
        self.qsirecon_config_btn.setFixedSize(24, 24)
        self.qsirecon_config_btn.setToolTip("Configure QSIRecon parameters")
        self.qsirecon_config_btn.clicked.connect(self.open_qsirecon_config)
        qsirecon_layout.addWidget(self.qsirecon_config_btn)
        qsirecon_layout.addStretch()
        options_group_layout.addLayout(qsirecon_layout)

        # Extract DTI tensor option
        self.extract_dti_cb = QtWidgets.QCheckBox("Extract DTI tensor for SimNIBS")
        self.extract_dti_cb.setChecked(False)
        self.extract_dti_cb.setToolTip(
            "Extract DTI tensor from QSIRecon output for SimNIBS anisotropic conductivity"
        )
        options_group_layout.addWidget(self.extract_dti_cb)

        # Initialize QSI configurations
        self.qsiprep_config = {}
        self.qsirecon_config = {}

        # Add options group to options layout
        options_layout.addWidget(self.options_group)
        options_layout.addStretch()

        # Add options widget to content layout
        content_layout.addWidget(options_widget)

        # Add content layout to scroll layout
        scroll_layout.addLayout(content_layout)

        # Add scroll content to scroll area
        scroll_area.setWidget(scroll_content)

        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(
            self, run_text="Run Pre-processing", stop_text="Stop Pre-processing"
        )
        self.action_buttons.connect_run(self.run_preprocessing)
        self.action_buttons.connect_stop(self.stop_preprocessing)

        # Keep references for backward compatibility
        self.run_btn = self.action_buttons.get_run_button()
        self.stop_btn = self.action_buttons.get_stop_button()

        # Console widget component with Run/Stop buttons integrated
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            console_label="Output:",
            min_height=200,
            custom_buttons=[self.run_btn, self.stop_btn],
        )

        # Vertical splitter: config panel (top) | console (bottom)
        _v_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        _v_splitter.setChildrenCollapsible(False)
        _v_splitter.addWidget(scroll_area)
        _v_splitter.addWidget(self.console_widget)
        _v_splitter.setSizes([600, 400])
        main_layout.addWidget(_v_splitter)

        # Reference to underlying console for backward compatibility
        self.output_text = self.console_widget.get_console_widget()

        # No longer need to manage DICOM type selection as it's auto-detected

        # Update available subjects initially
        self.update_available_subjects()

    def detect_project_dir(self):
        """Detect the project directory using PathManager.

        Note: This method is deprecated and kept for backward compatibility.
        Use self.pm.project_dir instead.
        """
        return self.pm.project_dir

    def update_available_subjects(self):
        """Update the list of available subjects."""
        self.subject_list.clear()
        subjects = discover_subjects(self.project_dir)
        for subject_id in subjects:
            self.subject_list.addItem(subject_id)
        if self.subject_list.count() == 0:
            QtWidgets.QMessageBox.warning(
                self,
                "No Subjects Found",
                "No subjects found in the project directory.\n\n"
                "Please ensure your subjects follow one of these structures:\n"
                f"  BIDS: {os.path.join(self.project_dir, 'sourcedata', 'sub-{{subjectID}}', 'T1w', '{{any_subdirectory_or_files}}')}\n"
                f"  Compressed: {os.path.join(self.project_dir, 'sourcedata', 'sub-{{subjectID}}', '*.tgz')}",
            )

    def set_processing_state(self, is_processing):
        """Update UI state based on processing state."""
        self.processing_running = is_processing
        self.run_btn.setEnabled(not is_processing)
        self.stop_btn.setEnabled(is_processing)
        self.subject_list.setEnabled(not is_processing)
        self.select_all_btn.setEnabled(not is_processing)
        self.select_none_btn.setEnabled(not is_processing)
        self.refresh_subjects_btn.setEnabled(not is_processing)
        self.convert_dicom_cb.setEnabled(not is_processing)
        self.run_recon_cb.setEnabled(not is_processing)
        self.parallel_cb.setEnabled(not is_processing and self.run_recon_cb.isChecked())
        self.create_m2m_cb.setEnabled(not is_processing)
        self.run_tissue_analyzer_cb.setEnabled(not is_processing)

        # QSI options
        self.run_qsiprep_cb.setEnabled(not is_processing)
        self.qsiprep_config_btn.setEnabled(not is_processing)
        self.run_qsirecon_cb.setEnabled(not is_processing)
        self.qsirecon_config_btn.setEnabled(not is_processing)
        self.extract_dti_cb.setEnabled(not is_processing)

        # Update status label
        if is_processing:
            self.status_label.setText("Preprocessing...")
            self.status_label.show()
        else:
            self.status_label.hide()

    def run_preprocessing(self):
        """Run the preprocessing pipeline."""
        if self.processing_running:
            return

        # Get selected subjects
        selected_subjects = []
        for item in self.subject_list.selectedItems():
            selected_subjects.append(item.text())

        if not selected_subjects:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Please select at least one subject."
            )
            return

        # Validate options
        if self.parallel_cb.isChecked() and not self.run_recon_cb.isChecked():
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Options",
                "Parallel mode requires recon-all to be enabled.",
            )
            return

        # Check if tissue analyzer is enabled but m2m folders are missing
        if (
            self.run_tissue_analyzer_cb.isChecked()
            and not self.create_m2m_cb.isChecked()
        ):
            # Check if m2m folders already exist for selected subjects
            missing_m2m_subjects = [
                sid
                for sid in selected_subjects
                if not check_m2m_exists(self.project_dir, sid)
            ]

            if missing_m2m_subjects:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Missing m2m Folders",
                    f"Tissue analyzer requires m2m folders, but the following subjects don't have them:\n"
                    f"{', '.join(missing_m2m_subjects)}\n\n"
                    f"Please either:\n"
                    f"1. Enable 'Create SimNIBS m2m folder' option, or\n"
                    f"2. Run m2m creation for these subjects first, or\n"
                    f"3. Disable 'Run tissue analyzer' option",
                )
                return

        # Show confirmation dialog
        details = (
            f"This will process {len(selected_subjects)} subject(s) with the following options:\n\n"
            + f"- Convert DICOM: {'Yes (auto-detects T1w/T2w)' if self.convert_dicom_cb.isChecked() else 'No'}\n"
            + f"- Run recon-all: {'Yes' if self.run_recon_cb.isChecked() else 'No'}\n"
            + f"- Parallel processing: {'Yes' if self.parallel_cb.isChecked() else 'No'}\n"
            + f"- Create m2m folder: {'Yes' if self.create_m2m_cb.isChecked() else 'No'}\n"
            + f"- Run tissue analyzer: {'Yes' if self.run_tissue_analyzer_cb.isChecked() else 'No'}\n"
            + f"- Run QSIPrep: {'Yes' if self.run_qsiprep_cb.isChecked() else 'No'}\n"
            + f"- Run QSIRecon: {'Yes' if self.run_qsirecon_cb.isChecked() else 'No'}\n"
            + f"- Extract DTI tensor: {'Yes' if self.extract_dti_cb.isChecked() else 'No'}"
        )

        if not ConfirmationDialog.confirm(
            self,
            title="Confirm Pre-processing",
            message="Are you sure you want to start pre-processing?",
            details=details,
        ):
            return

        # Set processing state
        self.set_processing_state(True)

        # Debug output (only show in debug mode)
        self.update_output("Running pre-processing from GUI", "debug")
        self.update_output(f"- Subjects: {', '.join(selected_subjects)}", "debug")
        self.update_output(
            f"- Convert DICOM: {self.convert_dicom_cb.isChecked()}", "debug"
        )
        self.update_output(f"- Run recon-all: {self.run_recon_cb.isChecked()}", "debug")
        self.update_output(
            f"- Parallel processing: {self.parallel_cb.isChecked()}", "debug"
        )
        self.update_output(
            f"- Create m2m folder: {self.create_m2m_cb.isChecked()}", "debug"
        )
        self.update_output(
            f"- Run tissue analyzer: {self.run_tissue_analyzer_cb.isChecked()}", "debug"
        )
        self.update_output(f"- Run QSIPrep: {self.run_qsiprep_cb.isChecked()}", "debug")
        self.update_output(
            f"- Run QSIRecon: {self.run_qsirecon_cb.isChecked()}", "debug"
        )
        self.update_output(f"- Extract DTI: {self.extract_dti_cb.isChecked()}", "debug")

        # Get QSI recon config
        qsi_recon_config = None
        if self.run_qsirecon_cb.isChecked() and self.qsirecon_config:
            qsi_recon_config = self.qsirecon_config

        # Get QSIPrep config
        qsiprep_config = None
        if self.run_qsiprep_cb.isChecked() and self.qsiprep_config:
            qsiprep_config = self.qsiprep_config

        # Serialize config to JSON and launch subprocess
        config_data = {
            "project_dir": self.project_dir,
            "subject_ids": selected_subjects,
            "convert_dicom": self.convert_dicom_cb.isChecked(),
            "run_recon": self.run_recon_cb.isChecked(),
            "parallel_recon": self.parallel_cb.isChecked(),
            "parallel_cores": self.cores_spin.value(),
            "create_m2m": self.create_m2m_cb.isChecked(),
            "run_tissue_analysis": self.run_tissue_analyzer_cb.isChecked(),
            "run_qsiprep": self.run_qsiprep_cb.isChecked(),
            "run_qsirecon": self.run_qsirecon_cb.isChecked(),
            "qsiprep_config": qsiprep_config,
            "qsi_recon_config": qsi_recon_config,
            "extract_dti": self.extract_dti_cb.isChecked(),
        }
        fd, config_path = tempfile.mkstemp(prefix="pre_", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(config_data, f, indent=2)

        cmd = ["simnibs_python", "-m", "tit.pre", config_path]

        self.processing_thread = PreProcessThread(cmd)
        self.processing_thread.output_signal.connect(self.update_output)
        self.processing_thread.error_signal.connect(
            lambda msg: self.update_output(msg, "error")
        )
        self.processing_thread.finished.connect(self.preprocessing_finished)
        self.processing_thread.start()

    def preprocessing_finished(self):
        """Handle the completion of the preprocessing process."""
        self.set_processing_state(False)

    def stop_preprocessing(self):
        """Stop the running preprocessing process."""
        if not self.processing_running:
            return

        self.update_output("Stopping preprocessing...", "warning")
        if self.processing_thread:
            if self.processing_thread.terminate_process():
                self.update_output("Preprocessing stopped.", "info")
            else:
                self.update_output("Failed to stop preprocessing.", "error")

        self.set_processing_state(False)

    def clear_console(self):
        """Clear the output console."""
        self.output_text.clear()

    def update_output(self, text, message_type="default"):
        """Update the console output with colored text."""
        if not text.strip():
            return

        # Use shared color mapping for known message types
        if message_type in ("error", "warning", "debug", "command", "success", "info"):
            formatted_text = format_message(text, message_type)
        else:
            # Fallback to content-based formatting for backward compatibility
            if "Processing... Only the Stop button is available" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #ffff55; font-weight: bold;">{text}</span></div>'
            elif text.strip().startswith("-"):
                formatted_text = (
                    f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
                )
            else:
                formatted_text = format_message(text, "default")

        append_with_autoscroll(self.output_text, formatted_text)

    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()

    def select_no_subjects(self):
        """Select no subjects in the subject list."""
        self.subject_list.clearSelection()

    def open_qsiprep_config(self):
        """Open QSIPrep configuration dialog."""
        dialog = QSIPrepConfigDialog(self, self.qsiprep_config)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.qsiprep_config = dialog.get_config()

    def open_qsirecon_config(self):
        """Open QSIRecon configuration dialog."""
        dialog = QSIReconConfigDialog(self, self.qsirecon_config)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.qsirecon_config = dialog.get_config()
