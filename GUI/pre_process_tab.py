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
        main_container_layout = QtWidgets.QVBoxLayout(self)
        
        # Subject selection section
        subject_widget = QtWidgets.QWidget()
        subject_main_layout = QtWidgets.QVBoxLayout(subject_widget)
        subject_main_layout.setContentsMargins(0, 0, 0, 0)
        
        subject_label = QtWidgets.QLabel("Available Subjects:")
        subject_main_layout.addWidget(subject_label)
        
        # Subject list with selection
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QListWidget.ExtendedSelection)
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
        
        main_container_layout.addWidget(subject_widget)
        
        # Options and control buttons section with consistent layout
        options_buttons_widget = QtWidgets.QWidget()
        options_buttons_layout = QtWidgets.QHBoxLayout(options_buttons_widget)
        options_buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # Pre-processing options group
        self.options_group = QtWidgets.QGroupBox("Processing Options")
        options_layout = QtWidgets.QHBoxLayout(self.options_group)  # Changed to QHBoxLayout for side-by-side layout
        
        # Left column - DICOM conversion options
        left_column = QtWidgets.QVBoxLayout()
        
        # DICOM to NIfTI conversion
        self.convert_dicom_cb = QtWidgets.QCheckBox("Convert DICOM files to NIfTI")
        self.convert_dicom_cb.setChecked(True)
        left_column.addWidget(self.convert_dicom_cb)
        
        # T1w/T2w selection
        self.dicom_type_group = QtWidgets.QGroupBox("DICOM Data Type")
        dicom_type_layout = QtWidgets.QVBoxLayout(self.dicom_type_group)
        self.t1_only_rb = QtWidgets.QRadioButton("T1w only")
        self.t1_t2_rb = QtWidgets.QRadioButton("T1w + T2w")
        self.t1_only_rb.setChecked(True)
        dicom_type_layout.addWidget(self.t1_only_rb)
        dicom_type_layout.addWidget(self.t1_t2_rb)
        left_column.addWidget(self.dicom_type_group)
        
        left_column.addStretch()  # Add stretch to align with right column
        options_layout.addLayout(left_column)
        
        # Add some spacing between columns
        options_layout.addSpacing(20)
        
        # Right column - Other options
        right_column = QtWidgets.QVBoxLayout()
        
        # FreeSurfer recon-all
        self.run_recon_cb = QtWidgets.QCheckBox("Run FreeSurfer recon-all")
        self.run_recon_cb.setChecked(True)
        right_column.addWidget(self.run_recon_cb)
        
        # Parallel processing
        self.parallel_cb = QtWidgets.QCheckBox("Run FreeSurfer reconstruction in parallel")
        self.parallel_cb.setEnabled(True)
        right_column.addWidget(self.parallel_cb)
        
        # Create m2m folder
        self.create_m2m_cb = QtWidgets.QCheckBox("Create SimNIBS m2m folder")
        self.create_m2m_cb.setChecked(True)
        right_column.addWidget(self.create_m2m_cb)
        
        # Quiet mode
        self.quiet_cb = QtWidgets.QCheckBox("Run in quiet mode")
        self.quiet_cb.setChecked(False)
        right_column.addWidget(self.quiet_cb)
        
        right_column.addStretch()  # Add stretch to align with left column
        options_layout.addLayout(right_column)
        
        options_buttons_layout.addWidget(self.options_group)
        main_container_layout.addWidget(options_buttons_widget)

        # Status label (hidden by default)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("""
            QLabel {
                color: #d9534f;
                font-size: 14px;
                font-weight: bold;
                padding: 4px 0;
                margin-bottom: 8px;
            }
        """)
        self.status_label.hide()
        main_container_layout.addWidget(self.status_label)

        # Control buttons - Moved above console
        control_widget = QtWidgets.QWidget()
        control_layout = QtWidgets.QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        # Start/Stop buttons
        self.start_btn = QtWidgets.QPushButton("Start Pre-processing")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #cccccc;
                color: #888888;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:enabled {
                background-color: #f44336;
                color: white;
            }
            QPushButton:enabled:hover {
                background-color: #da190b;
            }
        """)
        
        self.start_btn.clicked.connect(self.run_preprocessing)
        self.stop_btn.clicked.connect(self.stop_preprocessing)
        
        control_layout.addStretch()
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addStretch()
        
        main_container_layout.addWidget(control_widget)
        
        # Restore original console and button layout
        # Output label
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        main_container_layout.addWidget(output_label)

        # Console layout with buttons
        console_layout = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(output_label)
        header_layout.addStretch()
        self.clear_console_btn = QtWidgets.QPushButton("Clear Console")
        self.clear_console_btn.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 8px; border: none; border-radius: 4px;")
        self.clear_console_btn.clicked.connect(self.clear_console)
        header_layout.addWidget(self.clear_console_btn)
        console_layout.addLayout(header_layout)

        # Console output
        self.console_output = QtWidgets.QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMinimumHeight(200)
        self.console_output.setStyleSheet("""
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
        self.console_output.setAcceptRichText(True)
        console_layout.addWidget(self.console_output)
        main_container_layout.addLayout(console_layout)

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
        self.start_btn.setEnabled(not is_processing)
        self.stop_btn.setEnabled(is_processing)
        self.subject_list.setEnabled(not is_processing)
        self.select_all_btn.setEnabled(not is_processing)
        self.select_none_btn.setEnabled(not is_processing)
        self.refresh_subjects_btn.setEnabled(not is_processing)
        self.convert_dicom_cb.setEnabled(not is_processing)
        self.run_recon_cb.setEnabled(not is_processing)
        self.parallel_cb.setEnabled(not is_processing and self.run_recon_cb.isChecked())
        self.create_m2m_cb.setEnabled(not is_processing)
        self.quiet_cb.setEnabled(not is_processing)
        
        # Update status label
        if is_processing:
            self.status_label.setText("⚡ Processing... Only the Stop button is available")
            self.status_label.show()
            self.stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #da190b;
                }
            """)
        else:
            self.status_label.hide()
            self.stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc;
                    color: #888888;
                    font-weight: bold;
                    padding: 8px;
                    border: none;
                    border-radius: 4px;
                }
            """)

    def run_preprocessing(self):
        """Start the pre-processing operation with the selected options."""
        if self.processing_running:
            QtWidgets.QMessageBox.warning(
                self, "Process Running",
                "A pre-processing operation is already running."
            )
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
        
        # Confirmation dialog
        msg = "The following pre-processing operation will be executed:\n\n"
        msg += f"Selected Subjects ({len(selected_subjects)}):\n"
        msg += ", ".join(selected_subjects) + "\n\n"
        msg += f"Convert DICOM: {'Yes' if self.convert_dicom_cb.isChecked() else 'No'}\n"
        msg += f"Run recon-all: {'Yes' if self.run_recon_cb.isChecked() else 'No'}\n"
        msg += f"Parallel mode: {'Yes' if self.parallel_cb.isChecked() else 'No'}\n"
        msg += f"Create SimNIBS m2m folder: {'Yes' if self.create_m2m_cb.isChecked() else 'No'}\n"
        msg += f"Quiet mode: {'Yes' if self.quiet_cb.isChecked() else 'No'}\n\n"
        msg += "Do you want to proceed?"
        
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Pre-processing",
            msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Set processing state
        self.set_processing_state(True)
        
        # Process subjects sequentially
        self.update_output(f"Starting pre-processing for {len(selected_subjects)} subjects...", 'info')
        
        # Process each subject sequentially
        self.process_next_subject(selected_subjects, 0)
    
    def preprocessing_finished(self):
        """Handle completion of all pre-processing operations."""
        try:
            if hasattr(self, 'parent') and isinstance(self.parent, QtWidgets.QWidget) and hasattr(self.parent, 'set_tab_busy'):
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
        except Exception as e:
            self.update_output(f"Warning: Could not reset tab busy state: {str(e)}", 'warning')
            
        self.set_processing_state(False)
        self.update_output("\nPre-processing operations completed for all subjects.", 'success')

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
        """Stop the running pre-processing operation."""
        if not self.processing_running:
            return
            
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Termination",
            "Are you sure you want to stop the running pre-processing operation?\n\nThis might leave files in an inconsistent state.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.update_output("Terminating pre-processing operation...", 'warning')
            
            # Kill all running processes
            try:
                # Get the process group ID
                if hasattr(self, 'current_process') and self.current_process:
                    import signal
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                    self.current_process = None
            except Exception as e:
                self.update_output(f"Error terminating process: {str(e)}", 'error')
            
            # Reset UI state
            self.set_processing_state(False)
            self.update_output("Pre-processing operation terminated.", 'warning')
    
    def clear_console(self):
        """Clear the output console."""
        self.console_output.clear()
    
    def update_output(self, text, message_type='default'):
        """Update the console output with colored text."""
        self.console_output.append(text)
        self.console_output.ensureCursorVisible()
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
        self.console_output.append("\n=== Starting atlas segmentation. This may take a few moments... ===")
        QtWidgets.QApplication.processEvents()
        self.console_output.append("Running atlas segmentation for all selected subjects and all atlases...")
        QtWidgets.QApplication.processEvents()
        for subject_id in selected_subjects:
            m2m_folder = os.path.join(self.project_dir, subject_id, 'SimNIBS', f'm2m_{subject_id}')
            if not os.path.isdir(m2m_folder):
                self.console_output.append(f"[Atlas] {subject_id}: m2m folder not found, skipping.")
                QtWidgets.QApplication.processEvents()
                continue
            output_dir = os.path.join(m2m_folder, 'segmentation')
            os.makedirs(output_dir, exist_ok=True)
            for atlas in ["a2009s", "DK40", "HCP_MMP1"]:
                cmd = ["subject_atlas", "-m", m2m_folder, "-a", atlas, "-o", output_dir]
                self.console_output.append(f"[Atlas] {subject_id}: Running {' '.join(cmd)}")
                QtWidgets.QApplication.processEvents()
                try:
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if proc.returncode == 0:
                        self.console_output.append(f"[Atlas] {subject_id}: Atlas {atlas} segmentation complete.")
                    else:
                        self.console_output.append(f"[Atlas] {subject_id}: Atlas {atlas} segmentation failed.\n{proc.stderr}")
                except Exception as e:
                    self.console_output.append(f"[Atlas] {subject_id}: Error running subject_atlas: {e}")
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