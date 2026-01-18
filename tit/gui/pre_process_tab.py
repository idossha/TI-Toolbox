#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Pre-Process Tab
This module provides a GUI interface for the pre-processing functionality.
Thread-safe version with deadlock prevention.
"""

import os
import glob
import threading
import time
import multiprocessing

from PyQt5 import QtWidgets, QtCore
from tit.gui.confirmation_dialog import ConfirmationDialog
from tit.gui.utils import confirm_overwrite, is_important_message
from tit.gui.components.console import ConsoleWidget
from tit.gui.components.action_buttons import RunStopButtons
from tit.core import get_path_manager
from tit.pre.structural import run_pipeline
from tit.pre.common import CommandRunner, PreprocessCancelled


class PreProcessThread(QtCore.QThread):
    """Thread to run pre-processing in background to prevent GUI freezing."""

    output_signal = QtCore.pyqtSignal(str, str)  # text, message_type
    error_signal = QtCore.pyqtSignal(str)  # error message

    def __init__(
        self,
        project_dir: str,
        subjects: list[str],
        *,
        convert_dicom: bool,
        run_recon: bool,
        parallel_recon: bool,
        parallel_cores: int,
        create_m2m: bool,
        create_atlas: bool,
        run_tissue_analysis: bool,
        debug_mode: bool,
        overwrite_outputs: bool,
    ):
        super().__init__()
        self.project_dir = project_dir
        self.subjects = subjects
        self.convert_dicom = convert_dicom
        self.run_recon = run_recon
        self.parallel_recon = parallel_recon
        self.parallel_cores = parallel_cores
        self.create_m2m = create_m2m
        self.create_atlas = create_atlas
        self.run_tissue_analysis = run_tissue_analysis
        self.debug_mode = debug_mode
        self.overwrite_outputs = overwrite_outputs
        self.stop_event = threading.Event()
        self.runner = CommandRunner(stop_event=self.stop_event)

    def run(self):
        try:
            self.output_signal.emit(
                f"Starting processing for {len(self.subjects)} subjects: {', '.join(self.subjects)}",
                "info",
            )

            def callback(message: str, msg_type: str) -> None:
                self.output_signal.emit(message, msg_type)

            exit_code = run_pipeline(
                self.project_dir,
                self.subjects,
                convert_dicom=self.convert_dicom,
                run_recon=self.run_recon,
                parallel_recon=self.parallel_recon,
                parallel_cores=self.parallel_cores,
                create_m2m=self.create_m2m,
                create_atlas=self.create_atlas,
                run_tissue_analysis=self.run_tissue_analysis,
                debug=self.debug_mode,
                overwrite=self.overwrite_outputs,
                prompt_overwrite=False,
                stop_event=self.stop_event,
                logger_callback=callback,
                runner=self.runner,
            )

            if exit_code != 0:
                self.error_signal.emit(
                    "Pre-processing completed with errors. Check logs for details."
                )
        except PreprocessCancelled:
            self.output_signal.emit("Pre-processing stopped by user.", "warning")
        except Exception as e:
            self.error_signal.emit(f"Error running pre-processing: {str(e)}")

    def terminate_process(self):
        self.stop_event.set()
        if self.runner:
            self.runner.request_stop()
        return True


class PreProcessTab(QtWidgets.QWidget):
    """Tab for pre-processing functionality."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Initialize path manager
        self.pm = get_path_manager()

        # Get the project directory using PathManager
        self.project_dir = self.pm.project_dir
        if not self.project_dir:
            raise RuntimeError(
                "Could not detect project directory. Please ensure the environment is properly set up."
            )

        self.processing_running = False
        self.processing_thread = None
        # Initialize debug mode (default to False)
        self.debug_mode = False
        # Initialize summary mode state and timers for non-debug summaries
        self.SUMMARY_MODE = True
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
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)

        # Add status label at the top
        self.status_label = QtWidgets.QLabel()
        self.status_label.setText("Processing... Only the Stop button is available")
        self.status_label.setStyleSheet(
            """
            QLabel {
                background-color: white;
                color: #f44336;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
                min-height: 15px;
                max-height: 15px;
            }
        """
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
        subject_main_layout = QtWidgets.QVBoxLayout(subject_widget)
        subject_main_layout.setContentsMargins(10, 0, 10, 10)  # Removed top margin

        subject_label = QtWidgets.QLabel("Available Subjects:")
        subject_label.setStyleSheet("font-weight: bold;")
        subject_main_layout.addWidget(subject_label)

        # Subject list with selection
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QListWidget.ExtendedSelection)
        self.subject_list.setFixedHeight(235)  # Fixed height for the list
        subject_main_layout.addWidget(self.subject_list)

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
        options_widget.setFixedWidth(
            402
        )  # Fixed width for options (increased by 15% from 350)
        options_layout = QtWidgets.QVBoxLayout(options_widget)
        options_layout.setContentsMargins(
            10, 23, 10, 10
        )  # Add top margin to align with subject selection label

        # Pre-processing options group
        self.options_group = QtWidgets.QGroupBox("Processing Options")
        self.options_group.setStyleSheet(
            """
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 0px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """
        )
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
        parallel_comment.setStyleSheet("color: #888888; font-size: 10px;")
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

        # Other options section (currently empty)

        # Add options group to options layout
        options_layout.addWidget(self.options_group)
        options_layout.addStretch()

        # Add options widget to content layout
        content_layout.addWidget(options_widget)

        # Add content layout to scroll layout
        scroll_layout.addLayout(content_layout)

        # Add scroll content to scroll area
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

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
            show_debug_checkbox=True,
            console_label="Output:",
            min_height=180,
            max_height=None,
            custom_buttons=[self.run_btn, self.stop_btn],
        )
        main_layout.addWidget(self.console_widget)

        # Connect the debug checkbox to set_debug_mode method
        self.console_widget.debug_checkbox.toggled.connect(self.set_debug_mode)

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

        # First check sourcedata directory for new subjects
        sourcedata_dir = self.pm.path_optional("sourcedata")

        if sourcedata_dir and os.path.exists(sourcedata_dir):
            for subj_dir in glob.glob(os.path.join(sourcedata_dir, "sub-*")):
                if os.path.isdir(subj_dir):
                    # Check for both BIDS structure and compressed format
                    t1w_dir = os.path.join(subj_dir, "T1w")
                    t2w_dir = os.path.join(subj_dir, "T2w")

                    # Check if T1w or T2w directories exist and have any files or subdirectories
                    has_valid_structure = (
                        (
                            os.path.exists(t1w_dir)
                            and (
                                any(
                                    os.path.isdir(os.path.join(t1w_dir, d))
                                    for d in os.listdir(t1w_dir)
                                )
                                or any(
                                    f.endswith((".tgz", ".json", ".nii", ".nii.gz"))
                                    for f in os.listdir(t1w_dir)
                                )
                            )
                        )
                        or (
                            os.path.exists(t2w_dir)
                            and (
                                any(
                                    os.path.isdir(os.path.join(t2w_dir, d))
                                    for d in os.listdir(t2w_dir)
                                )
                                or any(
                                    f.endswith((".tgz", ".json", ".nii", ".nii.gz"))
                                    for f in os.listdir(t2w_dir)
                                )
                            )
                        )
                        or any(f.endswith(".tgz") for f in os.listdir(subj_dir))
                    )

                    if has_valid_structure:
                        subject_id = os.path.basename(subj_dir).replace("sub-", "")
                        self.subject_list.addItem(subject_id)

        # Also check root directory for BIDS-compliant subjects (like example data)
        for subj_dir in glob.glob(os.path.join(self.project_dir, "sub-*")):
            if os.path.isdir(subj_dir):
                subject_id = os.path.basename(subj_dir).replace("sub-", "")

                # Skip if already added from sourcedata
                if any(
                    self.subject_list.item(i).text() == subject_id
                    for i in range(self.subject_list.count())
                ):
                    continue

                # Check if this subject has BIDS-compliant anatomical data
                anat_dir = os.path.join(subj_dir, "anat")
                if os.path.exists(anat_dir):
                    # Look for T1w or T2w NIfTI files
                    has_nifti = any(
                        f.endswith((".nii", ".nii.gz")) and ("T1w" in f or "T2w" in f)
                        for f in os.listdir(anat_dir)
                    )
                    if has_nifti:
                        self.subject_list.addItem(subject_id)

        if self.subject_list.count() == 0:
            QtWidgets.QMessageBox.warning(
                self,
                "No Subjects Found",
                "No subjects found in the project directory.\n\n"
                "Please ensure your subjects follow one of these structures:\n"
                f"  BIDS: {os.path.join(self.project_dir, 'sourcedata', 'sub-{subjectID}', 'T1w', '{any_subdirectory_or_files}')}\n"
                f"  Compressed: {os.path.join(self.project_dir, 'sourcedata', 'sub-{subjectID}', '*.tgz')}",
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

        # Keep debug checkbox enabled during processing
        if hasattr(self, "console_widget") and hasattr(
            self.console_widget, "debug_checkbox"
        ):
            self.console_widget.debug_checkbox.setEnabled(True)

        # Update status label
        if is_processing:
            self.status_label.setText(
                "Processing... Stop button and Debug Mode are available"
            )
            self.status_label.show()
        else:
            self.status_label.hide()

    def run_preprocessing(self):
        """Run the preprocessing pipeline."""
        if self.processing_running:
            self.update_output(
                "Preprocessing already running. Please wait or stop the current run.",
                "warning",
            )
            return

        if not self.project_dir:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Project directory is not set."
            )
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
            missing_m2m_subjects = []
            for subject_id in selected_subjects:
                bids_subject_id = f"sub-{subject_id}"
                m2m_dir = os.path.join(
                    self.project_dir,
                    "derivatives",
                    "SimNIBS",
                    bids_subject_id,
                    f"m2m_{subject_id}",
                )
                if not os.path.exists(m2m_dir):
                    missing_m2m_subjects.append(subject_id)

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

        # Check for existing output directories and confirm overwrite
        overwrite_outputs = False
        for subject_id in selected_subjects:
            bids_subject_id = f"sub-{subject_id}"

            # Check NIfTI output directory if DICOM conversion is enabled
            if self.convert_dicom_cb.isChecked():
                nifti_dir = os.path.join(self.project_dir, bids_subject_id, "anat")
                if os.path.exists(nifti_dir):
                    if not confirm_overwrite(self, nifti_dir, "NIfTI output directory"):
                        return
                    overwrite_outputs = True

            # Check FreeSurfer output directory if recon-all is enabled
            if self.run_recon_cb.isChecked():
                freesurfer_dir = os.path.join(
                    self.project_dir, "derivatives", "freesurfer", bids_subject_id
                )
                if os.path.exists(freesurfer_dir):
                    if not confirm_overwrite(
                        self, freesurfer_dir, "FreeSurfer output directory"
                    ):
                        return
                    overwrite_outputs = True

            # Check m2m output directory if m2m creation is enabled
            if self.create_m2m_cb.isChecked():
                m2m_dir = os.path.join(
                    self.project_dir,
                    "derivatives",
                    "SimNIBS",
                    bids_subject_id,
                    f"m2m_{subject_id}",
                )
                if os.path.exists(m2m_dir):
                    if not confirm_overwrite(self, m2m_dir, "m2m output directory"):
                        return
                    overwrite_outputs = True

        # Show confirmation dialog
        details = (
            f"This will process {len(selected_subjects)} subject(s) with the following options:\n\n"
            + f"- Convert DICOM: {'Yes (auto-detects T1w/T2w)' if self.convert_dicom_cb.isChecked() else 'No'}\n"
            + f"- Run recon-all: {'Yes' if self.run_recon_cb.isChecked() else 'No'}\n"
            + f"- Parallel processing: {'Yes' if self.parallel_cb.isChecked() else 'No'}\n"
            + f"- Create m2m folder: {'Yes' if self.create_m2m_cb.isChecked() else 'No'}\n"
            + f"- Run tissue analyzer: {'Yes' if self.run_tissue_analyzer_cb.isChecked() else 'No'}\n"
            + f"- Debug mode: {'Yes' if self.debug_mode else 'No'}"
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
        self.update_output(f"- Debug mode: {self.debug_mode}", "debug")

        # Create and start the thread
        self.processing_thread = PreProcessThread(
            self.project_dir,
            selected_subjects,
            convert_dicom=self.convert_dicom_cb.isChecked(),
            run_recon=self.run_recon_cb.isChecked(),
            parallel_recon=self.parallel_cb.isChecked(),
            parallel_cores=self.cores_spin.value(),
            create_m2m=self.create_m2m_cb.isChecked(),
            create_atlas=False,
            run_tissue_analysis=self.run_tissue_analyzer_cb.isChecked(),
            debug_mode=self.debug_mode,
            overwrite_outputs=overwrite_outputs,
        )
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

        # Filter messages based on debug mode
        if not self.debug_mode:
            # In non-debug mode, only show important messages
            if not is_important_message(text, message_type, "preprocess"):
                return
            # Debounce exact duplicates
            if text == self._last_plain_output_line:
                return
            # Colorize summary lines: blue for starts, white for completes, green for final
            lower = text.lower()
            is_final = lower.startswith("└─") or "completed successfully" in lower
            # Treat "Beginning ...", ": Started", and "├─ ...: Started" as task starts
            is_start = (
                lower.startswith("beginning ")
                or ": started" in lower
                or lower.startswith("├─ ")
                and "started" in lower
            )
            # Treat ✓ Complete, saved/results lines as completes
            is_complete = (
                ("✓ complete" in lower)
                or ("results available in:" in lower)
                or ("saved to" in lower)
            )
            color = "#55ff55" if is_final else ("#55aaff" if is_start else "#ffffff")
            formatted_text = f'<span style="color: {color};">{text}</span>'
            scrollbar = self.output_text.verticalScrollBar()
            at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
            self.output_text.append(formatted_text)
            if at_bottom:
                self.output_text.ensureCursorVisible()
            self._last_plain_output_line = text
            QtWidgets.QApplication.processEvents()
            return

        # Format the output based on message type from thread
        if message_type == "error":
            formatted_text = f'<span style="color: #ff5555;"><b>{text}</b></span>'
        elif message_type == "warning":
            formatted_text = f'<span style="color: #ffff55;">{text}</span>'
        elif message_type == "debug":
            formatted_text = f'<span style="color: #7f7f7f;">{text}</span>'
        elif message_type == "command":
            formatted_text = f'<span style="color: #55aaff;">{text}</span>'
        elif message_type == "success":
            formatted_text = f'<span style="color: #55ff55;"><b>{text}</b></span>'
        elif message_type == "info":
            formatted_text = f'<span style="color: #55ffff;">{text}</span>'
        else:
            # Fallback to content-based formatting for backward compatibility
            if "Processing... Only the Stop button is available" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #ffff55; font-weight: bold;">{text}</span></div>'
            elif text.strip().startswith("-"):
                # Indented list items
                formatted_text = (
                    f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
                )
            else:
                formatted_text = f'<span style="color: #ffffff;">{text}</span>'

        # Check if user is at the bottom of the console before appending
        scrollbar = self.output_text.verticalScrollBar()
        at_bottom = (
            scrollbar.value() >= scrollbar.maximum() - 5
        )  # Allow small tolerance

        # Append to the console with HTML formatting
        self.output_text.append(formatted_text)

        # Only auto-scroll if user was already at the bottom
        if at_bottom:
            self.output_text.ensureCursorVisible()

        QtWidgets.QApplication.processEvents()

    # ------- Summary helpers -------
    def _format_duration_plain(self, start_time):
        if not start_time:
            return "0s"
        elapsed = time.time() - start_time
        if elapsed < 60:
            return f"{int(elapsed)}s"
        return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

    def set_debug_mode(self, debug_mode):
        """Set debug mode for output filtering."""
        old_debug_mode = self.debug_mode
        self.debug_mode = debug_mode
        self.SUMMARY_MODE = not debug_mode

        # Notify user about the mode change if processing is running
        if self.processing_running and old_debug_mode != debug_mode:
            if debug_mode:
                self.update_output(
                    "\n=== Debug mode enabled - showing detailed output ===", "info"
                )
            else:
                self.update_output(
                    "\n=== Debug mode disabled - showing summary only ===", "info"
                )

    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()

    def select_no_subjects(self):
        """Select no subjects in the subject list."""
        self.subject_list.clearSelection()
