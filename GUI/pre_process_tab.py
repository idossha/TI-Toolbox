#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Pre-Process Tab
This module provides a GUI interface for the pre-processing functionality.
"""

import os
import sys
import json
import re
import subprocess
import glob
from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog

class PreProcessThread(QtCore.QThread):
    """Thread to run pre-processing in background to prevent GUI freezing."""
    
    # Signal to emit output text
    output_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(PreProcessThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        
    def run(self):
        """Run the pre-processing command in a separate thread."""
        try:
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                env=self.env
            )
            
            # Real-time output display
            for line in iter(self.process.stdout.readline, ''):
                if self.terminated:
                    break
                if line:
                    self.output_signal.emit(line.strip())
            
            # Check for errors
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    error = self.process.stderr.read()
                    self.output_signal.emit("Error: Process returned non-zero exit code")
                    if error:
                        self.output_signal.emit(error)
                    
        except Exception as e:
            self.output_signal.emit(f"Error running pre-processing: {str(e)}")
    
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
        self.convert_dicom_cb = QtWidgets.QCheckBox("Convert DICOM files to NIfTI")
        self.convert_dicom_cb.setChecked(True)
        options_group_layout.addWidget(self.convert_dicom_cb)
        
        # T1w/T2w selection
        self.dicom_type_group = QtWidgets.QGroupBox("DICOM Data Type")
        self.dicom_type_group.setStyleSheet("""
            QGroupBox {
                font-weight: normal;
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
        dicom_type_layout = QtWidgets.QHBoxLayout(self.dicom_type_group)
        self.t1_only_rb = QtWidgets.QRadioButton("T1w only")
        self.t1_t2_rb = QtWidgets.QRadioButton("T1w + T2w")
        self.t1_only_rb.setChecked(True)
        dicom_type_layout.addWidget(self.t1_only_rb)
        dicom_type_layout.addWidget(self.t1_t2_rb)
        dicom_type_layout.addStretch()
        options_group_layout.addWidget(self.dicom_type_group)
        
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
        options_group_layout.addWidget(self.create_m2m_cb)
        
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
        
        # Add buttons to console buttons layout in the desired order
        console_buttons_layout.addWidget(self.run_btn)
        console_buttons_layout.addWidget(self.stop_btn)
        console_buttons_layout.addWidget(clear_btn)
        
        # Add console buttons layout to header layout
        header_layout.addLayout(console_buttons_layout)
        
        console_layout.addLayout(header_layout)
        console_layout.addWidget(self.output_text)
        
        main_layout.addLayout(console_layout)
        
        # Enable/disable DICOM type selection based on DICOM conversion checkbox
        self.convert_dicom_cb.toggled.connect(self.dicom_type_group.setEnabled)
        self.dicom_type_group.setEnabled(self.convert_dicom_cb.isChecked())
        
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
        if not self.project_dir or not os.path.isdir(self.project_dir):
            self.update_output("Project directory not found or not accessible.", 'error')
            return
            
        self.subject_list.clear()
        
        # First check sourcedata directory for new subjects
        sourcedata_dir = os.path.join(self.project_dir, "sourcedata")
        if os.path.isdir(sourcedata_dir):
            for item in os.listdir(sourcedata_dir):
                if (os.path.isdir(os.path.join(sourcedata_dir, item)) and 
                    item.startswith('sub-') and 
                    os.path.isdir(os.path.join(sourcedata_dir, item, "T1w", "dicom"))):
                    # Extract subject ID without 'sub-' prefix
                    subject_id = item[4:]
                    self.subject_list.addItem(subject_id)
        
        # If no subjects found in sourcedata, check root directory for legacy structure
        if self.subject_list.count() == 0:
            for item in os.listdir(self.project_dir):
                if os.path.isdir(os.path.join(self.project_dir, item)) and item.startswith('sub-'):
                    # Extract subject ID without 'sub-' prefix
                    subject_id = item[4:]
                    self.subject_list.addItem(subject_id)
                    
        # Update the environment variable for other tools
        os.environ['PROJECT_DIR'] = self.project_dir
        
        # Show status message
        if self.subject_list.count() == 0:
            self.update_output("No subjects found. Please ensure your data follows the BIDS structure:", 'warning')
            self.update_output(f"  {self.project_dir}/sourcedata/sub-{{subjectID}}/T1w/dicom/", 'info')
        else:
            self.update_output(f"Found {self.subject_list.count()} subject(s) in {self.project_dir}", 'success')

    def process_next_subject(self, subjects, index):
        """Process the next subject in the queue."""
        if index >= len(subjects):
            # All subjects have been processed
            self.preprocessing_finished()
            self.update_output("All subjects have been processed.", 'success')
            return
            
        subject_id = subjects[index]
        bids_subject_id = f"sub-{subject_id}"
        subject_dir = os.path.join(self.project_dir, bids_subject_id)
        
        # Display status
        self.update_output(f"\n{'='*50}", 'info')
        self.update_output(f"Processing subject {index+1}/{len(subjects)}: {subject_id}", 'info')
        self.update_output(f"{'='*50}\n", 'info')
        
        # Create required directories
        os.makedirs(os.path.join(self.project_dir, "sourcedata", bids_subject_id, "T1w", "dicom"), exist_ok=True)
        if self.t1_t2_rb.isChecked():
            os.makedirs(os.path.join(self.project_dir, "sourcedata", bids_subject_id, "T2w", "dicom"), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, bids_subject_id, "anat"), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "derivatives", "freesurfer", bids_subject_id), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "derivatives", "SimNIBS", bids_subject_id), exist_ok=True)
        
        # Build the command
        cmd = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pre-process", "structural.sh")]
        
        # Add required arguments
        cmd.append(subject_dir)
        
        # Add optional flags
        if self.run_recon_cb.isChecked():
            cmd.append("recon-all")
        
        if self.parallel_cb.isChecked():
            cmd.append("--parallel")
        
        if self.quiet_cb.isChecked():
            cmd.append("--quiet")
        
        if self.convert_dicom_cb.isChecked():
            cmd.append("--convert-dicom")
            
        if self.create_m2m_cb.isChecked():
            cmd.append("--create-m2m")
        
        # Run the command
        self.update_output(f"Running command: {' '.join(cmd)}", 'info')
        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                preexec_fn=os.setsid  # Create new process group
            )
            
            # Read output in real-time
            while True:
                if not self.processing_running:
                    break
                    
                line = self.current_process.stdout.readline()
                if not line and self.current_process.poll() is not None:
                    break
                    
                if line:
                    # Determine message type based on content
                    msg_type = 'default'
                    line = line.strip()
                    if any(error_text in line.lower() for error_text in ['error', 'failed', 'not found']):
                        msg_type = 'error'
                    elif any(warning_text in line.lower() for warning_text in ['warning', 'skip']):
                        msg_type = 'warning'
                    elif any(success_text in line.lower() for success_text in ['complete', 'success', 'finished']):
                        msg_type = 'success'
                    elif any(info_text in line.lower() for info_text in ['running', 'processing', 'creating']):
                        msg_type = 'info'
                    
                    self.update_output(line, msg_type)
                    QtWidgets.QApplication.processEvents()
            
            if self.processing_running:  # Only proceed if we weren't stopped
                if self.current_process.returncode == 0:
                    self.update_output(f"Successfully processed subject: {subject_id}", 'success')
                    # Process next subject
                    self.process_next_subject(subjects, index + 1)
                else:
                    self.update_output(f"Error processing subject: {subject_id}", 'error')
                    self.set_processing_state(False)
                    
        except Exception as e:
            self.update_output(f"Error running command: {str(e)}", 'error')
            self.set_processing_state(False)
        finally:
            self.current_process = None

    def toggle_recon_only(self, checked):
        """Enable/disable recon-only checkbox based on run_recon state."""
        self.recon_only_cb.setEnabled(checked)
        if not checked:
            self.recon_only_cb.setChecked(False)
    
    def toggle_parallel(self, checked):
        """Enable/disable parallel checkbox based on run_recon state."""
        self.parallel_cb.setEnabled(checked)
        if not checked:
            self.parallel_cb.setChecked(False)
    
    def toggle_dependent_options(self):
        """Handle interdependent options."""
        # When recon-all is not checked, disable parallel processing
        if not self.run_recon_cb.isChecked():
            self.parallel_cb.setEnabled(False)
            self.parallel_cb.setChecked(False)
        else:
            self.parallel_cb.setEnabled(True)
    
    def browse_project_dir(self):
        """Open file dialog to browse for project directory."""
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Project Directory", 
            self.project_dir or os.path.expanduser("~")
        )
        
        if dir_path:
            self.project_dir = dir_path
            self.update_available_subjects()
    
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
        self.dicom_type_group.setEnabled(not is_processing and self.convert_dicom_cb.isChecked())
        self.run_recon_cb.setEnabled(not is_processing)
        self.parallel_cb.setEnabled(not is_processing and self.run_recon_cb.isChecked())
        self.create_m2m_cb.setEnabled(not is_processing)
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
            self.update_output("Preprocessing already running. Please wait or stop the current run.")
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

        # Show confirmation dialog
        details = (f"This will process {len(selected_subjects)} subject(s) with the following options:\n\n" +
                  f"• Convert DICOM: {'Yes' if self.convert_dicom_cb.isChecked() else 'No'}\n" +
                  f"• DICOM Type: {'T1w + T2w' if self.t1_t2_rb.isChecked() else 'T1w only'}\n" +
                  f"• Run recon-all: {'Yes' if self.run_recon_cb.isChecked() else 'No'}\n" +
                  f"• Parallel processing: {'Yes' if self.parallel_cb.isChecked() else 'No'}\n" +
                  f"• Create m2m folder: {'Yes' if self.create_m2m_cb.isChecked() else 'No'}\n" +
                  f"• Quiet mode: {'Yes' if self.quiet_cb.isChecked() else 'No'}")
        
        if not ConfirmationDialog.confirm(
            self,
            title="Confirm Pre-processing",
            message="Are you sure you want to start pre-processing?",
            details=details
        ):
            return
        
        # Set processing state
        self.set_processing_state(True)
        
        # Process each subject
        for subject_id in selected_subjects:
            # Build the command for each subject
            cmd = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pre-process", "structural.sh")]
            
            # Add subject directory as first argument
            subject_dir = os.path.join(self.project_dir, f"sub-{subject_id}")
            cmd.append(subject_dir)
            
            # Add optional flags
            if self.run_recon_cb.isChecked():
                cmd.append("recon-all")
            
            if self.parallel_cb.isChecked():
                cmd.append("--parallel")
            
            if self.quiet_cb.isChecked():
                cmd.append("--quiet")
            
            if self.convert_dicom_cb.isChecked():
                cmd.append("--convert-dicom")
                
            if self.create_m2m_cb.isChecked():
                cmd.append("--create-m2m")
            
            # Set up environment
            env = os.environ.copy()
            env['PROJECT_DIR'] = self.project_dir
            
            # Create and start the thread
            self.processing_thread = PreProcessThread(cmd, env)
            self.processing_thread.output_signal.connect(self.update_output)
            self.processing_thread.finished.connect(self.preprocessing_finished)
            self.processing_thread.start()
            
            # Wait for the current subject to finish before processing the next one
            while self.processing_running and self.processing_thread.isRunning():
                QtWidgets.QApplication.processEvents()
                QtCore.QThread.msleep(100)  # Small delay to prevent UI freezing

    def preprocessing_finished(self):
        """Handle the completion of the preprocessing process."""
        self.set_processing_state(False)
        self.update_output("\nPreprocessing completed.")

        # --- Atlas Segmentation: Automatically run after m2m creation ---
        if self.create_m2m_cb.isChecked():
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            for subject_id in selected_subjects:
                bids_subject_id = f"sub-{subject_id}"
                m2m_folder = os.path.join(self.project_dir, "derivatives", "SimNIBS", bids_subject_id, f"m2m_{subject_id}")
                if not os.path.isdir(m2m_folder):
                    self.update_output(f"[Atlas] {subject_id}: m2m folder not found, skipping atlas segmentation.", 'warning')
                    continue
                output_dir = os.path.join(m2m_folder, 'segmentation')
                os.makedirs(output_dir, exist_ok=True)
                for atlas in ["a2009s", "DK40", "HCP_MMP1"]:
                    cmd = ["subject_atlas", "-m", m2m_folder, "-a", atlas, "-o", output_dir]
                    self.update_output(f"[Atlas] {subject_id}: Running {' '.join(cmd)}", 'info')
                    try:
                        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if proc.returncode == 0:
                            self.update_output(f"[Atlas] {subject_id}: Atlas {atlas} segmentation complete.", 'success')
                        else:
                            self.update_output(f"[Atlas] {subject_id}: Atlas {atlas} segmentation failed.\n{proc.stderr}", 'error')
                    except Exception as e:
                        self.update_output(f"[Atlas] {subject_id}: Error running subject_atlas: {e}", 'error')

    def stop_preprocessing(self):
        """Stop the running preprocessing process."""
        if not self.processing_running:
            return
        
        self.update_output("Stopping preprocessing...")
        if self.processing_thread:
            if self.processing_thread.terminate_process():
                self.update_output("Preprocessing stopped.")
            else:
                self.update_output("Failed to stop preprocessing.")
        
        self.set_processing_state(False)

    def clear_console(self):
        """Clear the output console."""
        self.output_text.clear()
    
    def update_output(self, text, message_type='default'):
        """Update the console output with colored text."""
        self.output_text.append(text)
        self.output_text.ensureCursorVisible()
        QtWidgets.QApplication.processEvents()

    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()

    def select_no_subjects(self):
        """Select no subjects in the subject list."""
        self.subject_list.clearSelection()

    def run_atlas_segmentation(self):
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        if not selected_subjects:
            QtWidgets.QMessageBox.warning(self, "Error", "Please select at least one subject.")
            return
        self.output_text.append("\n=== Starting atlas segmentation. This may take a few moments... ===")
        QtWidgets.QApplication.processEvents()
        self.output_text.append("Running atlas segmentation for all selected subjects and all atlases...")
        QtWidgets.QApplication.processEvents()
        for subject_id in selected_subjects:
            m2m_folder = os.path.join(self.project_dir, subject_id, 'SimNIBS', f'm2m_{subject_id}')
            if not os.path.isdir(m2m_folder):
                self.output_text.append(f"[Atlas] {subject_id}: m2m folder not found, skipping.")
                QtWidgets.QApplication.processEvents()
                continue
            output_dir = os.path.join(m2m_folder, 'segmentation')
            os.makedirs(output_dir, exist_ok=True)
            for atlas in ["a2009s", "DK40", "HCP_MMP1"]:
                cmd = ["subject_atlas", "-m", m2m_folder, "-a", atlas, "-o", output_dir]
                self.output_text.append(f"[Atlas] {subject_id}: Running {' '.join(cmd)}")
                QtWidgets.QApplication.processEvents()
                try:
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if proc.returncode == 0:
                        self.output_text.append(f"[Atlas] {subject_id}: Atlas {atlas} segmentation complete.")
                    else:
                        self.output_text.append(f"[Atlas] {subject_id}: Atlas {atlas} segmentation failed.\n{proc.stderr}")
                except Exception as e:
                    self.output_text.append(f"[Atlas] {subject_id}: Error running subject_atlas: {e}")
                QtWidgets.QApplication.processEvents()

    def update_atlas_btn_state(self):
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        if not selected_subjects or not self.project_dir:
            self.atlas_btn.setEnabled(False)
            return
        for subject_id in selected_subjects:
            m2m_folder = os.path.join(self.project_dir, subject_id, 'SimNIBS', f'm2m_{subject_id}')
            if not os.path.isdir(m2m_folder):
                self.atlas_btn.setEnabled(False)
                return
        self.atlas_btn.setEnabled(True) 