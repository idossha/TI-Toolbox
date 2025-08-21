#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Pre-Process Tab
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

from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog
try:
    from .utils import confirm_overwrite, is_verbose_message, is_important_message
except ImportError:
    # Fallback for when running as standalone script
    import os
    import sys
    gui_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, gui_dir)
    from utils import confirm_overwrite, is_verbose_message, is_important_message

# Add the utils directory to the path
utils_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'utils')
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)

# Import from utils with error handling
try:
    from report_util import get_preprocessing_report_generator
except ImportError as e:
    print(f"Warning: Could not import report utilities: {e}")
    # Define a fallback function
    def get_preprocessing_report_generator(*args, **kwargs):
        print("Warning: Report generation not available")
        return None

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
            
            self.process = subprocess.Popen(
                current_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                universal_newlines=True,
                bufsize=1,
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
                    elif 'Starting skull bone analysis' in line_stripped:
                        self.last_step = "skull bone analysis"
                    elif 'Skull bone analysis completed' in line_stripped:
                        self.last_step = "skull bone analysis completed"
                    
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
                except:
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
        
        # Get the project directory from environment or detect it
        self.project_dir = self.detect_project_dir()
        if not self.project_dir:
            raise RuntimeError("Could not detect project directory. Please ensure the environment is properly set up.")
            
        self.processing_running = False
        self.processing_thread = None
        self.report_generators = {}  # Store report generators for each subject
        # Initialize debug mode (default to False)
        self.debug_mode = False
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface for the pre-process tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create a scroll area for the form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Title and description
        title_label = QtWidgets.QLabel("Pre-processing Pipeline")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        description_label = QtWidgets.QLabel(
            "Convert DICOM files to NIfTI format, run FreeSurfer reconstruction, "
            "and create SimNIBS m2m folders for selected subjects."
        )
        description_label.setWordWrap(True)
        
        scroll_layout.addWidget(title_label)
        scroll_layout.addWidget(description_label)
        scroll_layout.addSpacing(10)  # Reduced spacing after description
        
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
        options_widget.setFixedWidth(350)  # Fixed width for options
        options_layout = QtWidgets.QVBoxLayout(options_widget)
        options_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
        
        # Add some top margin to move options up
        options_layout.setContentsMargins(10, 0, 10, 10)  # Remove top margin
        
        # Pre-processing options group
        self.options_group = QtWidgets.QGroupBox("Processing Options")
        self.options_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
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
        self.convert_dicom_cb = QtWidgets.QCheckBox("Convert DICOM files to NIfTI)")
        self.convert_dicom_cb.setChecked(True)
        options_group_layout.addWidget(self.convert_dicom_cb)
        
        # FreeSurfer options
        self.run_recon_cb = QtWidgets.QCheckBox("Run FreeSurfer recon-all")
        self.run_recon_cb.setChecked(True)
        options_group_layout.addWidget(self.run_recon_cb)
        
        self.parallel_cb = QtWidgets.QCheckBox("Run FreeSurfer reconstruction in parallel")
        self.parallel_cb.setEnabled(True)
        options_group_layout.addWidget(self.parallel_cb)
        
        # SimNIBS options
        self.create_m2m_cb = QtWidgets.QCheckBox("Create SimNIBS m2m folder")
        self.create_m2m_cb.setChecked(True)
        self.create_m2m_cb.setToolTip("SimNIBS charm processes run one at a time (sequential) to prevent PETSC conflicts, but each uses full CPU power")
        options_group_layout.addWidget(self.create_m2m_cb)
        
        self.create_atlas_cb = QtWidgets.QCheckBox("Create atlas segmentation")
        self.create_atlas_cb.setChecked(True)
        options_group_layout.addWidget(self.create_atlas_cb)

        # Bone analyzer option (publication-ready skull bone analysis)
        self.run_bone_analyzer_cb = QtWidgets.QCheckBox("Run skull bone analyzer (publication-ready figures)")
        self.run_bone_analyzer_cb.setChecked(False)
        self.run_bone_analyzer_cb.setToolTip("Analyze skull bone volume/thickness and generate GxP-ready figures alongside preprocessing")
        options_group_layout.addWidget(self.run_bone_analyzer_cb)
        
        # Other options
        self.quiet_cb = QtWidgets.QCheckBox("Run in quiet mode")
        self.quiet_cb.setChecked(False)
        options_group_layout.addWidget(self.quiet_cb)
        
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
        
        # Console output
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        
        self.output_text = QtWidgets.QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        self.output_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #f0f0f0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        self.output_text.setAcceptRichText(True)
        
        # Console layout
        console_layout = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(output_label)
        header_layout.addStretch()
        
        # Create button layout for console controls
        console_buttons_layout = QtWidgets.QHBoxLayout()
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Run Pre-processing")
        self.run_btn.clicked.connect(self.run_preprocessing)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        
        # Stop button (initially disabled)
        self.stop_btn = QtWidgets.QPushButton("Stop Pre-processing")
        self.stop_btn.clicked.connect(self.stop_preprocessing)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.stop_btn.setEnabled(False)  # Initially disabled
        
        # Clear console button
        clear_btn = QtWidgets.QPushButton("Clear Console")
        clear_btn.clicked.connect(self.clear_console)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        
        # Add debug mode checkbox next to console buttons
        self.debug_mode_checkbox = QtWidgets.QCheckBox("Debug Mode")
        self.debug_mode_checkbox.setChecked(self.debug_mode)
        self.debug_mode_checkbox.setToolTip(
            "Toggle debug mode:\n"
            "• ON: Show all detailed logging information\n"
            "• OFF: Show only key operational steps"
        )
        self.debug_mode_checkbox.toggled.connect(self.set_debug_mode)
        
        # Style the debug mode checkbox
        self.debug_mode_checkbox.setStyleSheet("""
            QCheckBox {
                font-weight: bold;
                color: #333333;
                padding: 5px;
                margin-left: 10px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #cccccc;
                background-color: white;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #4CAF50;
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        
        # Add buttons to console buttons layout in the desired order
        console_buttons_layout.addWidget(self.run_btn)
        console_buttons_layout.addWidget(self.stop_btn)
        console_buttons_layout.addWidget(clear_btn)
        console_buttons_layout.addWidget(self.debug_mode_checkbox)
        
        # Add console buttons layout to header layout
        header_layout.addLayout(console_buttons_layout)
        
        console_layout.addLayout(header_layout)
        console_layout.addWidget(self.output_text)
        
        main_layout.addLayout(console_layout)
        
        # No longer need to manage DICOM type selection as it's auto-detected
        
        # Update available subjects initially
        self.update_available_subjects()

    def detect_project_dir(self):
        """Detect the project directory using the same logic as the CLI."""
        # First try to get from environment variable
        project_dir = os.environ.get('PROJECT_DIR')
        if project_dir and os.path.isdir(project_dir):
            return project_dir
            
        # If we're in a Docker container, check /mnt for mounted directories
        if os.path.isdir("/mnt"):
            # Look for directories under /mnt that contain our expected structure
            for dir_name in os.listdir("/mnt"):
                dir_path = os.path.join("/mnt", dir_name)
                if os.path.isdir(dir_path):
                    # Check if this looks like a valid project directory
                    if os.path.isdir(os.path.join(dir_path, "sourcedata")) or \
                       os.path.isdir(os.path.join(dir_path, "derivatives")):
                        return dir_path
                    # If no BIDS structure found yet, just take the first directory
                    return dir_path
        
        # If not in Docker, try to find the project directory relative to the script
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        potential_dirs = [
            script_dir,  # The directory containing the script
            os.path.dirname(script_dir),  # Parent directory
            os.getcwd(),  # Current working directory
        ]
        
        for dir_path in potential_dirs:
            if os.path.isdir(dir_path):
                return dir_path
        
        return None

    def update_available_subjects(self):
        """Update the list of available subjects."""
        self.subject_list.clear()
        
        # First check sourcedata directory for new subjects
        sourcedata_dir = os.path.join(self.project_dir, "sourcedata")
        if os.path.exists(sourcedata_dir):
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
        
        # If no subjects found in sourcedata, check root directory for legacy structure
        if self.subject_list.count() == 0:
            for subj_dir in glob.glob(os.path.join(self.project_dir, "sub-*")):
                if os.path.isdir(subj_dir):
                    subject_id = os.path.basename(subj_dir).replace("sub-", "")
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
        self.run_bone_analyzer_cb.setEnabled(not is_processing)
        self.quiet_cb.setEnabled(not is_processing)
        
        # Update status label
        if is_processing:
            self.status_label.setText("Processing... Only the Stop button is available")
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
                  f"- Quiet mode: {'Yes (overridden by debug mode)' if self.quiet_cb.isChecked() and self.debug_mode else 'Yes' if self.quiet_cb.isChecked() else 'No'}")
        
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
                'quiet_mode': self.quiet_cb.isChecked()
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
        env['QUIET'] = str(self.quiet_cb.isChecked()).lower()
        env['RUN_BONE_ANALYZER'] = str(self.run_bone_analyzer_cb.isChecked()).lower()
        
        # Pass debug mode setting to control summary output
        env['DEBUG_MODE'] = 'true' if self.debug_mode else 'false'
        
        # Build command exactly like CLI does - subject directories first, then flags
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [os.path.join(script_dir, 'pre-process', 'structural.sh')]
        
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

        if self.convert_dicom_cb.isChecked():
            cmd.append("--convert-dicom")

        if self.create_m2m_cb.isChecked():
            cmd.append("--create-m2m")

        # Only add --quiet flag when NOT in debug mode
        # Debug mode should always show detailed output
        if self.quiet_cb.isChecked() and not self.debug_mode:
            cmd.append("--quiet")
        
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
        self.update_output(f"- Run bone analyzer: {env['RUN_BONE_ANALYZER']}", 'debug')
        self.update_output(f"- Quiet mode: {env['QUIET']}", 'debug')
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
                    self.update_output(f"[Atlas] {subject_id}: m2m folder not found, skipping atlas segmentation.", 'warning')
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
                    self.update_output(f"[Atlas] {subject_id}: Running {' '.join(cmd)}", 'debug')
                    try:
                        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if proc.returncode == 0:
                            # Verify that the expected .annot files were actually created
                            created_files = []
                            for expected_file in expected_files:
                                if os.path.exists(expected_file) and os.path.isfile(expected_file):
                                    created_files.append(os.path.basename(expected_file))
                            
                            if len(created_files) == 2:
                                self.update_output(f"[Atlas] {subject_id}: Atlas {atlas} segmentation complete. Created: {', '.join(created_files)}", 'success')
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

        # If requested, run bone analyzer on each subject's segmentation
        if self.run_bone_analyzer_cb.isChecked():
            self.update_output("\n=== Running skull bone analyzer ===", 'debug')
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            for subject_id in selected_subjects:
                try:
                    bids_subject_id = f"sub-{subject_id}"
                    # Use SimNIBS segmentation NIfTI as input if available
                    m2m_dir = os.path.join(self.project_dir, "derivatives", "SimNIBS", bids_subject_id, f"m2m_{subject_id}")
                    label_nii = os.path.join(m2m_dir, "segmentation", "Labeling.nii.gz")
                    if not os.path.exists(label_nii):
                        self.update_output(f"[Bone] {subject_id}: Labeling.nii.gz not found, skipping bone analysis.", 'warning')
                        continue
                    out_dir = os.path.join(self.project_dir, "derivatives", "ti-toolbox", "bone_analysis", bids_subject_id)
                    os.makedirs(out_dir, exist_ok=True)
                    cmd_bone = [sys.executable, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pre-process', 'bone_analyzer.py'), label_nii, '-o', out_dir]
                    self.update_output(f"[Bone] {subject_id}: Running {' '.join(cmd_bone)}", 'debug')
                    proc = subprocess.run(cmd_bone, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    if proc.returncode == 0:
                        self.update_output(f"[Bone] {subject_id}: Bone analysis completed.", 'success')
                    else:
                        self.update_output(f"[Bone] {subject_id}: Bone analysis failed.\n{proc.stdout}", 'error')
                except Exception as e:
                    self.update_output(f"[Bone] {subject_id}: Error running bone analyzer: {e}", 'error')

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

    def set_debug_mode(self, debug_mode):
        """Set debug mode for output filtering."""
        self.debug_mode = debug_mode

    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()

    def select_no_subjects(self):
        """Select no subjects in the subject list."""
        self.subject_list.clearSelection()