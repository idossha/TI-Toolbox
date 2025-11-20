#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Pre-Process Tab
This module provides a GUI interface for the pre-processing functionality.
Thread-safe version with deadlock prevention.
"""

import os
import sys
import json
import re
import subprocess
import glob
import threading
import time
from pathlib import Path
import tempfile
import shutil
import datetime
import multiprocessing

# Add project root to path for tools import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite, is_verbose_message, is_important_message
from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons
from core import get_path_manager
from tools.report_util import get_preprocessing_report_generator

class PreProcessThread(QtCore.QThread):
    """Thread to run pre-processing in background to prevent GUI freezing."""
    
    # Signals for thread-safe communication
    output_signal = QtCore.pyqtSignal(str, str)  # text, message_type
    error_signal = QtCore.pyqtSignal(str)        # error message
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(PreProcessThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        self.last_step = "initialization"  # Track last successful step
        self.has_failures = False  # Track if any subjects failed
        self.expecting_failed_subjects = False  # Track when we're expecting failed subject list
        
    def run(self):
        """Run the pre-processing command in a separate thread."""
        try:
            # Get list of subjects from environment
            subjects = self.env.get('SUBJECTS', '').split(',')
            subjects = [s.strip() for s in subjects if s.strip()]  # Clean up subjects list
            
            # Always call the script once with all subjects - let the script handle parallelization
            self.output_signal.emit(f"Starting processing for {len(subjects)} subjects: {', '.join(subjects)}", 'info')
            
            # Use the command as-is (subject directories already added in run_preprocessing)
            current_cmd = self.cmd
            
            self.output_signal.emit(f"Command: {' '.join(current_cmd)}", 'info')
            
            # Set the environment variables for the current process
            current_env = self.env.copy()
            
            # Set PYTHONUNBUFFERED to ensure Python scripts don't buffer output
            current_env['PYTHONUNBUFFERED'] = '1'
            
            self.process = subprocess.Popen(
                current_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                universal_newlines=True,
                bufsize=0,  # Unbuffered
                env=current_env
            )
            
            # Real-time output display
            for line in iter(self.process.stdout.readline, ''):
                if self.terminated:
                    break
                if line:
                    # Determine message type based on content
                    line_stripped = line.strip()
                    
                    # Track the last successful step and detect failures for better error reporting
                    if 'Starting processing for' in line_stripped:
                        self.last_step = "processing initialization"
                    elif 'Starting DICOM to NIfTI conversion' in line_stripped:
                        self.last_step = "DICOM to NIfTI conversion"
                    elif 'DICOM conversion completed' in line_stripped:
                        self.last_step = "DICOM conversion completed"
                    elif 'Starting SimNIBS charm' in line_stripped:
                        self.last_step = "SimNIBS charm processing"
                    elif 'SimNIBS charm completed' in line_stripped:
                        self.last_step = "SimNIBS charm completed"
                    elif 'Starting FreeSurfer recon-all' in line_stripped or 'Running FreeSurfer recon-all' in line_stripped:
                        self.last_step = "FreeSurfer recon-all processing"
                    elif 'FreeSurfer recon-all completed' in line_stripped:
                        self.last_step = "FreeSurfer recon-all completed"
                    elif 'Starting skull bone analysis' in line_stripped or 'BONE ANALYSIS' in line_stripped:
                        self.last_step = "tissue analysis"
                    elif 'Skull bone analysis completed' in line_stripped or 'Bone analysis: ✓ Complete' in line_stripped or 'TISSUE ANALYSIS SUMMARY' in line_stripped:
                        self.last_step = "tissue analysis completed"
                    elif 'Atlas' in line_stripped and '✓ Complete' in line_stripped:
                        self.last_step = "atlas segmentation completed"
                    
                    # Detect actual failures from the shell scripts
                    elif 'Warning:' in line_stripped and 'failed for subject' in line_stripped:
                        self.has_failures = True
                    elif 'The following subjects had failures:' in line_stripped:
                        self.has_failures = True
                        self.expecting_failed_subjects = True  # Flag to expect subject list next
                    elif hasattr(self, 'expecting_failed_subjects') and self.expecting_failed_subjects:
                        # Check if this line is a simple subject ID (part of the failed subjects list)
                        if len(line_stripped) <= 6 and line_stripped.isalnum():
                            # This is likely a failed subject ID, ensure it's shown as important
                            message_type = 'warning'  # Mark as warning so it gets shown
                        elif 'Please check the logs' in line_stripped:
                            self.expecting_failed_subjects = False  # End of failed subjects list
                    
                    # Simplified error detection - only flag critical system-level errors
                    # Let the process return code handle actual preprocessing failures
                    # First check if it's a normal FreeSurfer computational message
                    is_freesurfer_computational = any(pattern in line_stripped.upper() for pattern in [
                        'DT:', 'RMS RADIAL ERROR=', 'AVGS=', 'FINAL DISTANCE ERROR',
                        'DISTANCE ERROR %', '/300:', 'SURFACE RECONSTRUCTION',
                        'IFLAG=', 'LINE SEARCH', 'MCSRCH', 'QUASINEWTONEMA'
                    ])
                    
                    if not is_freesurfer_computational and any(keyword in line_stripped.lower() for keyword in [
                        'segmentation fault', 'bus error', 'killed', 'aborted',
                        'illegal instruction', 'permission denied', 'no such file or directory',
                        'command not found', 'cannot execute', 'bad interpreter'
                    ]):
                        message_type = 'error'
                    elif any(keyword in line_stripped.lower() for keyword in ['warning', 'warn']):
                        message_type = 'warning'
                    elif any(keyword in line_stripped.lower() for keyword in ['success', 'completed', 'finished']):
                        message_type = 'success'
                    elif any(keyword in line_stripped.lower() for keyword in ['debug']):
                        message_type = 'debug'
                    elif any(keyword in line_stripped.lower() for keyword in ['running', 'executing', 'processing']):
                        message_type = 'info'
                    else:
                        message_type = 'default'
                        
                    self.output_signal.emit(line_stripped, message_type)
            
            # Check for errors - rely primarily on process return code
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    # Provide specific error message based on last successful step and return code
                    if self.last_step.endswith("completed"):
                        # If last step was completed, the error occurred in the next step
                        error_msg = f"Preprocessing failed after {self.last_step}."
                    else:
                        # Error occurred during the current step
                        error_msg = f"Preprocessing failed during {self.last_step}."
                    
                    # Add return code interpretation
                    if returncode == 1:
                        error_msg += f" Check the output above for specific error details."
                    elif returncode == 2:
                        error_msg += f" Invalid arguments or configuration error."
                    elif returncode == 126:
                        error_msg += f" Permission denied or command not executable."
                    elif returncode == 127:
                        error_msg += f" Command not found or missing dependency."
                    elif returncode == 130:
                        error_msg += f" Process interrupted by user (Ctrl+C)."
                    elif returncode < 0:
                        error_msg += f" Process terminated by signal {abs(returncode)}."
                    else:
                        error_msg += f" Process returned exit code {returncode}."
                    
                    self.error_signal.emit(error_msg)
                else:
                    # Only show success message if no failures were detected and in debug mode
                    if not self.has_failures:
                        # Only show in debug mode - summary system handles completion messages
                        pass
                    else:
                        self.output_signal.emit(f"Pre-processing completed with failures. Check the output above for details.", 'warning')
                
        except Exception as e:
            self.error_signal.emit(f"Error running pre-processing: {str(e)}")
    
    def terminate_process(self):
        """Terminate the running process."""
        if self.process and self.process.poll() is None:  # Process is still running
            self.terminated = True
            if os.name == 'nt':  # Windows
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:  # Unix/Linux/Mac
                import signal
                # Try to terminate child processes too
                try:
                    parent_pid = self.process.pid
                    ps_output = subprocess.check_output(f"ps -o pid --ppid {parent_pid} --noheaders", shell=True)
                    child_pids = [int(pid) for pid in ps_output.decode().strip().split('\n') if pid]
                    for pid in child_pids:
                        os.kill(pid, signal.SIGTERM)
                except (subprocess.CalledProcessError, OSError, ValueError):
                    pass  # Ignore errors in finding child processes
                
                # Kill the main process
                self.process.terminate()
                try:
                    # Wait for a short time for graceful termination
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    self.process.kill()
            
            return True
        return False

class PreProcessTab(QtWidgets.QWidget):
    """Tab for pre-processing functionality."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize path manager
        self.pm = get_path_manager()
        
        # Get the project directory using PathManager
        self.project_dir = self.pm.get_project_dir()
        if not self.project_dir:
            raise RuntimeError("Could not detect project directory. Please ensure the environment is properly set up.")
            
        self.processing_running = False
        self.processing_thread = None
        self.report_generators = {}  # Store report generators for each subject
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
        self.status_label.setStyleSheet("""
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
        """)
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
        options_widget.setFixedWidth(402)  # Fixed width for options (increased by 15% from 350)
        options_layout = QtWidgets.QVBoxLayout(options_widget)
        options_layout.setContentsMargins(10, 23, 10, 10)  # Add top margin to align with subject selection label
        
        # Pre-processing options group
        self.options_group = QtWidgets.QGroupBox("Processing Options")
        self.options_group.setStyleSheet("""
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
        """)
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
        parallel_comment = QtWidgets.QLabel(f"   {available_cores} cores available on this system")
        parallel_comment.setStyleSheet("color: #888888; font-size: 10px;")
        options_group_layout.addWidget(parallel_comment)
        
        # Enable spinbox based on checkbox
        self.parallel_cb.toggled.connect(lambda checked: self.cores_spin.setEnabled(checked))
        self.cores_spin.setEnabled(self.parallel_cb.isChecked())
        
        self.create_m2m_cb = QtWidgets.QCheckBox("Create SimNIBS m2m folder")
        self.create_m2m_cb.setChecked(True)
        self.create_m2m_cb.setToolTip("SimNIBS charm processes run one at a time (sequential) to prevent PETSC conflicts, but each uses full CPU power")
        options_group_layout.addWidget(self.create_m2m_cb)
        
        self.create_atlas_cb = QtWidgets.QCheckBox("Create atlas segmentation")
        self.create_atlas_cb.setChecked(True)
        options_group_layout.addWidget(self.create_atlas_cb)

        # Tissue analyzer option
        self.run_tissue_analyzer_cb = QtWidgets.QCheckBox("Run Tissue Analyzer")
        self.run_tissue_analyzer_cb.setChecked(False)
        self.run_tissue_analyzer_cb.setToolTip("Analyze tissue volume and thickness using tissue analyzer and generate figures alongside preprocessing")
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
        self.action_buttons = RunStopButtons(self, run_text="Run Pre-processing", stop_text="Stop Pre-processing")
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
            custom_buttons=[self.run_btn, self.stop_btn]
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
        Use self.pm.get_project_dir() instead.
        """
        return self.pm.get_project_dir()

    def update_available_subjects(self):
        """Update the list of available subjects."""
        self.subject_list.clear()
        
        # First check sourcedata directory for new subjects
        sourcedata_dir = self.pm.get_sourcedata_dir()
        
        if sourcedata_dir and os.path.exists(sourcedata_dir):
            for subj_dir in glob.glob(os.path.join(sourcedata_dir, "sub-*")):
                if os.path.isdir(subj_dir):
                    # Check for both BIDS structure and compressed format
                    t1w_dir = os.path.join(subj_dir, "T1w")
                    t2w_dir = os.path.join(subj_dir, "T2w")
                    
                    # Check if T1w or T2w directories exist and have any files or subdirectories
                    has_valid_structure = (
                        (os.path.exists(t1w_dir) and (
                            any(os.path.isdir(os.path.join(t1w_dir, d)) for d in os.listdir(t1w_dir)) or
                            any(f.endswith(('.tgz', '.json', '.nii', '.nii.gz')) for f in os.listdir(t1w_dir))
                        )) or
                        (os.path.exists(t2w_dir) and (
                            any(os.path.isdir(os.path.join(t2w_dir, d)) for d in os.listdir(t2w_dir)) or
                            any(f.endswith(('.tgz', '.json', '.nii', '.nii.gz')) for f in os.listdir(t2w_dir))
                        )) or
                        any(f.endswith('.tgz') for f in os.listdir(subj_dir))
                    )
                    
                    if has_valid_structure:
                        subject_id = os.path.basename(subj_dir).replace("sub-", "")
                        self.subject_list.addItem(subject_id)
        
        # Also check root directory for BIDS-compliant subjects (like example data)
        for subj_dir in glob.glob(os.path.join(self.project_dir, "sub-*")):
            if os.path.isdir(subj_dir):
                subject_id = os.path.basename(subj_dir).replace("sub-", "")
                
                # Skip if already added from sourcedata
                if any(self.subject_list.item(i).text() == subject_id for i in range(self.subject_list.count())):
                    continue
                
                # Check if this subject has BIDS-compliant anatomical data
                anat_dir = os.path.join(subj_dir, "anat")
                if os.path.exists(anat_dir):
                    # Look for T1w or T2w NIfTI files
                    has_nifti = any(
                        f.endswith(('.nii', '.nii.gz')) and ('T1w' in f or 'T2w' in f)
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
                f"  Compressed: {os.path.join(self.project_dir, 'sourcedata', 'sub-{subjectID}', '*.tgz')}"
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
        self.create_atlas_cb.setEnabled(not is_processing)
        self.run_tissue_analyzer_cb.setEnabled(not is_processing)
        
        # Keep debug checkbox enabled during processing
        if hasattr(self, 'console_widget') and hasattr(self.console_widget, 'debug_checkbox'):
            self.console_widget.debug_checkbox.setEnabled(True)
        
        # Update status label
        if is_processing:
            self.status_label.setText("Processing... Stop button and Debug Mode are available")
            self.status_label.show()
        else:
            self.status_label.hide()

    def run_preprocessing(self):
        """Run the preprocessing pipeline."""
        if self.processing_running:
            self.update_output("Preprocessing already running. Please wait or stop the current run.", 'warning')
            return
        
        if not self.project_dir:
            QtWidgets.QMessageBox.warning(
                self, "Error", 
                "Project directory is not set."
            )
            return
        
        # Get selected subjects
        selected_subjects = []
        for item in self.subject_list.selectedItems():
            selected_subjects.append(item.text())
        
        if not selected_subjects:
            QtWidgets.QMessageBox.warning(
                self, "Error", 
                "Please select at least one subject."
            )
            return
        
        # Validate options
        if self.parallel_cb.isChecked() and not self.run_recon_cb.isChecked():
            QtWidgets.QMessageBox.warning(
                self, "Invalid Options",
                "Parallel mode requires recon-all to be enabled."
            )
            return
        
        # Check if atlas creation is requested but m2m creation is not enabled
        if self.create_atlas_cb.isChecked() and not self.create_m2m_cb.isChecked():
            # Check if m2m folders already exist for selected subjects
            missing_m2m_subjects = []
            for subject_id in selected_subjects:
                bids_subject_id = f"sub-{subject_id}"
                m2m_dir = os.path.join(self.project_dir, "derivatives", "SimNIBS", bids_subject_id, f"m2m_{subject_id}")
                if not os.path.exists(m2m_dir):
                    missing_m2m_subjects.append(subject_id)
            
            if missing_m2m_subjects:
                QtWidgets.QMessageBox.warning(
                    self, "Missing m2m Folders",
                    f"Atlas creation requires m2m folders, but the following subjects don't have them:\n"
                    f"{', '.join(missing_m2m_subjects)}\n\n"
                    f"Please either:\n"
                    f"1. Enable 'Create SimNIBS m2m folder' option, or\n"
                    f"2. Run m2m creation for these subjects first, or\n"
                    f"3. Disable 'Create atlas segmentation' option"
                )
                return

        # Check if tissue analyzer is enabled but m2m folders are missing
        if self.run_tissue_analyzer_cb.isChecked() and not self.create_m2m_cb.isChecked():
            # Check if m2m folders already exist for selected subjects
            missing_m2m_subjects = []
            for subject_id in selected_subjects:
                bids_subject_id = f"sub-{subject_id}"
                m2m_dir = os.path.join(self.project_dir, "derivatives", "SimNIBS", bids_subject_id, f"m2m_{subject_id}")
                if not os.path.exists(m2m_dir):
                    missing_m2m_subjects.append(subject_id)
            
            if missing_m2m_subjects:
                QtWidgets.QMessageBox.warning(
                    self, "Missing m2m Folders",
                    f"Tissue analyzer requires m2m folders, but the following subjects don't have them:\n"
                    f"{', '.join(missing_m2m_subjects)}\n\n"
                    f"Please either:\n"
                    f"1. Enable 'Create SimNIBS m2m folder' option, or\n"
                    f"2. Run m2m creation for these subjects first, or\n"
                    f"3. Disable 'Run tissue analyzer' option"
                )
                return

        # Check for existing output directories and confirm overwrite
        for subject_id in selected_subjects:
            bids_subject_id = f"sub-{subject_id}"
            
            # Check NIfTI output directory if DICOM conversion is enabled
            if self.convert_dicom_cb.isChecked():
                nifti_dir = os.path.join(self.project_dir, bids_subject_id, "anat")
                if os.path.exists(nifti_dir):
                    if not confirm_overwrite(self, nifti_dir, "NIfTI output directory"):
                        return
            
            # Check FreeSurfer output directory if recon-all is enabled
            if self.run_recon_cb.isChecked():
                freesurfer_dir = os.path.join(self.project_dir, "derivatives", "freesurfer", bids_subject_id)
                if os.path.exists(freesurfer_dir):
                    if not confirm_overwrite(self, freesurfer_dir, "FreeSurfer output directory"):
                        return
            
            # Check m2m output directory if m2m creation is enabled
            if self.create_m2m_cb.isChecked():
                m2m_dir = os.path.join(self.project_dir, "derivatives", "SimNIBS", bids_subject_id, f"m2m_{subject_id}")
                if os.path.exists(m2m_dir):
                    if not confirm_overwrite(self, m2m_dir, "m2m output directory"):
                        return

        # Show confirmation dialog
        details = (f"This will process {len(selected_subjects)} subject(s) with the following options:\n\n" +
                   f"- Convert DICOM: {'Yes (auto-detects T1w/T2w)' if self.convert_dicom_cb.isChecked() else 'No'}\n" +
                   f"- Run recon-all: {'Yes' if self.run_recon_cb.isChecked() else 'No'}\n" +
                   f"- Parallel processing: {'Yes' if self.parallel_cb.isChecked() else 'No'}\n" +
                   f"- Create m2m folder: {'Yes' if self.create_m2m_cb.isChecked() else 'No'}\n" +
                   f"- Create atlas segmentation: {'Yes' if self.create_atlas_cb.isChecked() else 'No'}\n" +
                   f"- Run tissue analyzer: {'Yes' if self.run_tissue_analyzer_cb.isChecked() else 'No'}\n" +
                   f"- Debug mode: {'Yes' if self.debug_mode else 'No'}")
        
        if not ConfirmationDialog.confirm(
            self,
            title="Confirm Pre-processing",
            message="Are you sure you want to start pre-processing?",
            details=details
        ):
            return
        
        # Initialize report generators for selected subjects
        for subject_id in selected_subjects:
            self.report_generators[subject_id] = get_preprocessing_report_generator(self.project_dir, subject_id)
            
            # Add processing parameters to report
            parameters = {
                'convert_dicom': self.convert_dicom_cb.isChecked(),
                'run_recon_all': self.run_recon_cb.isChecked(),
                'parallel_processing': self.parallel_cb.isChecked(),
                'create_m2m': self.create_m2m_cb.isChecked(),
                'create_atlas': self.create_atlas_cb.isChecked(),
                'run_tissue_analyzer': self.run_tissue_analyzer_cb.isChecked(),
                'debug_mode': self.debug_mode
            }
            self.report_generators[subject_id].report_data['parameters'] = parameters
        
        # Set processing state
        self.set_processing_state(True)
        
        # Prepare environment variables
        env = os.environ.copy()
        env['DIRECT_MODE'] = 'true'
        env['PROJECT_DIR'] = self.project_dir
        env['SUBJECTS'] = ','.join(selected_subjects)
        env['CONVERT_DICOM'] = str(self.convert_dicom_cb.isChecked()).lower()
        env['RUN_RECON'] = str(self.run_recon_cb.isChecked()).lower()
        env['PARALLEL_RECON'] = str(self.parallel_cb.isChecked()).lower()
        env['CREATE_M2M'] = str(self.create_m2m_cb.isChecked()).lower()
        env['RUN_TISSUE_ANALYZER'] = str(self.run_tissue_analyzer_cb.isChecked()).lower()
        
        # Pass debug mode setting to control summary output
        env['DEBUG_MODE'] = 'true' if self.debug_mode else 'false'
        
        # Build command exactly like CLI does - subject directories first, then flags
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [os.path.join(script_dir, 'pre', 'structural.sh')]
        
        # Add subject directories as individual arguments (like CLI does)
        for subject_id in selected_subjects:
            bids_subject_id = f"sub-{subject_id}"
            subject_dir = os.path.join(self.project_dir, bids_subject_id)
            cmd.append(subject_dir)
        
        # Add optional flags based on checkbox states (like CLI does)
        if self.run_recon_cb.isChecked():
            cmd.append("recon-all")

        if self.parallel_cb.isChecked():
            cmd.append("--parallel")
            cmd.append("--cores")
            cmd.append(str(self.cores_spin.value()))

        if self.convert_dicom_cb.isChecked():
            cmd.append("--convert-dicom")

        if self.create_m2m_cb.isChecked():
            cmd.append("--create-m2m")

        # Note: Quiet mode has been removed - all output is now shown
        
        # Debug output (only show in debug mode)
        self.update_output(f"Running pre-processing from GUI", 'debug')
        self.update_output(f"Command: {' '.join(cmd)}", 'debug')
        self.update_output(f"Options:", 'debug')
        self.update_output(f"- Subjects: {', '.join(selected_subjects)}", 'debug')
        self.update_output(f"- Convert DICOM: {env['CONVERT_DICOM']}", 'debug')
        self.update_output(f"- Run recon-all: {env['RUN_RECON']}", 'debug')
        self.update_output(f"- Parallel processing: {env['PARALLEL_RECON']}", 'debug')
        self.update_output(f"- Create m2m folder: {env['CREATE_M2M']}", 'debug')
        self.update_output(f"- Create atlas segmentation: {str(self.create_atlas_cb.isChecked()).lower()}", 'debug')
        self.update_output(f"- Run tissue analyzer: {env['RUN_TISSUE_ANALYZER']}", 'debug')
        self.update_output(f"- Debug mode: {env['DEBUG_MODE']}", 'debug')
        
        # Create and start the thread
        self.processing_thread = PreProcessThread(cmd, env)
        self.processing_thread.output_signal.connect(self.update_output)
        self.processing_thread.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
        self.processing_thread.finished.connect(self.preprocessing_finished)
        self.processing_thread.start()

    def preprocessing_finished(self):
        """Handle the completion of the preprocessing process."""
        self.set_processing_state(False)
        
        # Add completion information to reports
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        for subject_id in selected_subjects:
            if subject_id in self.report_generators:
                # Add main processing steps based on what was enabled
                if self.convert_dicom_cb.isChecked():
                    self.report_generators[subject_id].add_processing_step(
                        'DICOM Conversion',
                        'Converted DICOM files to NIfTI format with automatic T1w/T2w detection',
                        {'tool': 'dcm2niix', 'auto_detect': True},
                        'completed'
                    )
                
                if self.run_recon_cb.isChecked():
                    self.report_generators[subject_id].add_processing_step(
                        'FreeSurfer Reconstruction',
                        'Performed cortical surface reconstruction and tissue segmentation',
                        {'tool': 'recon-all', 'parallel': self.parallel_cb.isChecked()},
                        'completed'
                    )
                
                if self.create_m2m_cb.isChecked():
                    self.report_generators[subject_id].add_processing_step(
                        'SimNIBS m2m Creation',
                        'Created head model for electromagnetic field simulations',
                        {'tool': 'charm', 'segmentation_method': 'charm'},
                        'completed'
                    )
                
                if self.run_tissue_analyzer_cb.isChecked():
                    self.report_generators[subject_id].add_processing_step(
                        'Tissue Analysis',
                        'Analyzed tissue volume and thickness using unified tissue analyzer',
                        {'tools': ['tissue-analyzer.sh'], 'tissue_types': ['multiple']},
                        'completed'
                    )

        # --- Atlas Segmentation: Run if requested ---
        if self.create_atlas_cb.isChecked():
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            
            self.update_output("\n=== Starting atlas segmentation ===", 'debug')
            self.update_output("Running atlas segmentation for all selected subjects and all atlases...", 'debug')
            
            # Run atlas segmentation for each subject
            for subject_id in selected_subjects:
                bids_subject_id = f"sub-{subject_id}"
                m2m_folder = os.path.join(self.project_dir, "derivatives", "SimNIBS", bids_subject_id, f"m2m_{subject_id}")
                if not os.path.isdir(m2m_folder):
                    self.update_output(f"[Atlas] {subject_id}: m2m_{subject_id} folder not found at {m2m_folder}. Please create m2m folder first using 'Create m2m folder' option, then run atlas segmentation.", 'warning')
                    continue
                
                output_dir = os.path.join(m2m_folder, 'segmentation')
                os.makedirs(output_dir, exist_ok=True)
                
                # Check if output_dir is actually a directory and not a file
                if os.path.exists(output_dir) and not os.path.isdir(output_dir):
                    self.update_output(f"[Atlas] {subject_id}: Error - segmentation path exists but is not a directory: {output_dir}", 'error')
                    continue
                
                for atlas in ["a2009s", "DK40", "HCP_MMP1"]:
                    # Check for potential file conflicts before running
                    expected_files = [
                        os.path.join(output_dir, f"lh.{subject_id}_{atlas}.annot"),
                        os.path.join(output_dir, f"rh.{subject_id}_{atlas}.annot")
                    ]
                    
                    # Check if any expected file exists as a directory (conflict)
                    conflict_found = False
                    for expected_file in expected_files:
                        if os.path.exists(expected_file) and os.path.isdir(expected_file):
                            self.update_output(f"[Atlas] {subject_id}: Error - expected file path is a directory: {expected_file}", 'error')
                            conflict_found = True
                    
                    if conflict_found:
                        continue
                    
                    cmd = ["subject_atlas", "-m", m2m_folder, "-a", atlas, "-o", output_dir]
                    self.update_output(f"├─ Atlas {atlas}: Started", 'info')
                    try:
                        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if proc.returncode == 0:
                            # Verify that the expected .annot files were actually created
                            created_files = []
                            for expected_file in expected_files:
                                if os.path.exists(expected_file) and os.path.isfile(expected_file):
                                    created_files.append(os.path.basename(expected_file))
                            
                            if len(created_files) == 2:
                                self.update_output(f"├─ Atlas {atlas}: ✓ Complete", 'success')
                            else:
                                self.update_output(f"[Atlas] {subject_id}: Atlas {atlas} segmentation completed but some files missing. Created: {', '.join(created_files)}", 'warning')
                        else:
                            self.update_output(f"[Atlas] {subject_id}: Atlas {atlas} segmentation failed.\n{proc.stderr}", 'error')
                            if subject_id in self.report_generators:
                                self.report_generators[subject_id].add_error(f"Atlas {atlas} segmentation failed: {proc.stderr}", 'Atlas Segmentation')
                    except Exception as e:
                        self.update_output(f"[Atlas] {subject_id}: Error running subject_atlas: {e}", 'error')
                        if subject_id in self.report_generators:
                            self.report_generators[subject_id].add_error(f"Error running subject_atlas for {atlas}: {e}", 'Atlas Segmentation')
            
            # Add atlas segmentation step to report if it was requested
            if self.create_atlas_cb.isChecked():
                for subject_id in selected_subjects:
                    if subject_id in self.report_generators:
                                                 self.report_generators[subject_id].add_processing_step(
                             'Atlas Segmentation',
                             'Created cortical parcellation using multiple atlases (a2009s, DK40, HCP_MMP1)',
                             {'atlases': ['a2009s', 'DK40', 'HCP_MMP1'], 'tool': 'subject_atlas'},
                             'completed'
                         )
        
        # Automatically generate reports for all processed subjects
        self.auto_generate_reports()

    def stop_preprocessing(self):
        """Stop the running preprocessing process."""
        if not self.processing_running:
            return
        
        self.update_output("Stopping preprocessing...", 'warning')
        if self.processing_thread:
            if self.processing_thread.terminate_process():
                self.update_output("Preprocessing stopped.", 'info')
            else:
                self.update_output("Failed to stop preprocessing.", 'error')
        
        self.set_processing_state(False)

    def clear_console(self):
        """Clear the output console."""
        self.output_text.clear()
    
    def auto_generate_reports(self):
        """Automatically generate HTML reports for all processed subjects."""
        if not self.report_generators:
            return
        
        self.update_output("\n=== Generating preprocessing reports ===", 'debug')
        
        generated_reports = []
        failed_reports = []
        
        for subject_id, generator in self.report_generators.items():
            try:
                self.update_output(f"Generating report for {subject_id}...", 'debug')
                report_path = generator.generate_html_report()
                generated_reports.append((subject_id, report_path))
                self.update_output(f"Report generated: {os.path.basename(report_path)}", 'debug')
            except Exception as e:
                failed_reports.append((subject_id, str(e)))
                self.update_output(f"Failed to generate report for {subject_id}: {e}", 'error')
        
        # Summary of report generation
        if generated_reports:
            reports_dir = os.path.join(self.project_dir, "derivatives", "reports")
            self.update_output(f"\nSuccessfully generated {len(generated_reports)} preprocessing report(s)", 'debug')
            self.update_output(f"Reports location: {reports_dir}", 'debug')
            
            for subject_id, report_path in generated_reports:
                self.update_output(f"   - {os.path.basename(report_path)}", 'debug')
            
            self.update_output(f"\nOpen the HTML files in your web browser to view detailed preprocessing reports.", 'debug')
        
        if failed_reports:
            self.update_output(f"\nFailed to generate {len(failed_reports)} report(s):", 'error')
            for subject_id, error in failed_reports:
                self.update_output(f"  - {subject_id}: {error}", 'error')
        
        # Only show report generation message in debug mode (summary system handles this)
        if self.debug_mode:
            if generated_reports:
                self.update_output("Report generation completed", 'success')
            else:
                self.update_output("Report generation completed", 'info')
    

    
    def update_output(self, text, message_type='default'):
        """Update the console output with colored text."""
        if not text.strip():
            return
        
        # Filter messages based on debug mode
        if not self.debug_mode:
            # In non-debug mode, only show important messages
            if not is_important_message(text, message_type, 'preprocess'):
                return
            # Debounce exact duplicates
            if text == self._last_plain_output_line:
                return
            # Colorize summary lines: blue for starts, white for completes, green for final
            lower = text.lower()
            is_final = lower.startswith('└─') or 'completed successfully' in lower
            # Treat "Beginning ...", ": Started", and "├─ ...: Started" as task starts
            is_start = (lower.startswith('beginning ') or 
                       ': started' in lower or 
                       lower.startswith('├─ ') and 'started' in lower)
            # Treat ✓ Complete, saved/results lines as completes
            is_complete = ('✓ complete' in lower) or ('results available in:' in lower) or ('saved to' in lower)
            color = '#55ff55' if is_final else ('#55aaff' if is_start else '#ffffff')
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
        if message_type == 'error':
            formatted_text = f'<span style="color: #ff5555;"><b>{text}</b></span>'
        elif message_type == 'warning':
            formatted_text = f'<span style="color: #ffff55;">{text}</span>'
        elif message_type == 'debug':
            formatted_text = f'<span style="color: #7f7f7f;">{text}</span>'
        elif message_type == 'command':
            formatted_text = f'<span style="color: #55aaff;">{text}</span>'
        elif message_type == 'success':
            formatted_text = f'<span style="color: #55ff55;"><b>{text}</b></span>'
        elif message_type == 'info':
            formatted_text = f'<span style="color: #55ffff;">{text}</span>'
        else:
            # Fallback to content-based formatting for backward compatibility
            if "Processing... Only the Stop button is available" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #ffff55; font-weight: bold;">{text}</span></div>'
            elif text.strip().startswith("-"):
                # Indented list items
                formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
            else:
                formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        
        # Check if user is at the bottom of the console before appending
        scrollbar = self.output_text.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5  # Allow small tolerance
        
        # Append to the console with HTML formatting
        self.output_text.append(formatted_text)
        
        # Only auto-scroll if user was already at the bottom
        if at_bottom:
            self.output_text.ensureCursorVisible()
        
        QtWidgets.QApplication.processEvents()

    # ------- Summary helpers -------
    def _format_duration_plain(self, start_time):
        if not start_time:
            return '0s'
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
                self.update_output("\n=== Debug mode enabled - showing detailed output ===", 'info')
            else:
                self.update_output("\n=== Debug mode disabled - showing summary only ===", 'info')

    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()

    def select_no_subjects(self):
        """Select no subjects in the subject list."""
        self.subject_list.clearSelection()
