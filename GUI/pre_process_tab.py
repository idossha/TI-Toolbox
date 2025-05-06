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
        super(PreProcessTab, self).__init__(parent)
        self.parent = parent
        self.processing_running = False
        self.processing_thread = None
        self.setup_ui()
        
        # Initialize project directory
        self.project_dir = self.detect_project_dir()
        if self.project_dir:
            self.update_available_subjects()
        
    def setup_ui(self):
        """Set up the user interface for the pre-process tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create a scroll area for the form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Main container with consistent width
        main_container = QtWidgets.QWidget()
        main_container_layout = QtWidgets.QVBoxLayout(main_container)
        main_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Project directory section
        project_dir_widget = QtWidgets.QWidget()
        project_dir_layout = QtWidgets.QHBoxLayout(project_dir_widget)
        project_dir_layout.setContentsMargins(0, 0, 0, 0)
        
        self.project_dir_label = QtWidgets.QLabel("Project Directory:")
        project_dir_layout.addWidget(self.project_dir_label)
        
        self.project_dir_input = QtWidgets.QLineEdit()
        self.project_dir_input.setReadOnly(True)
        project_dir_layout.addWidget(self.project_dir_input)
        
        self.browse_project_btn = QtWidgets.QPushButton("Browse")
        self.browse_project_btn.clicked.connect(self.browse_project_dir)
        self.browse_project_btn.setFixedWidth(120)
        project_dir_layout.addWidget(self.browse_project_btn)
        
        main_container_layout.addWidget(project_dir_widget)
        
        # Subject selection section
        subject_widget = QtWidgets.QWidget()
        subject_layout = QtWidgets.QHBoxLayout(subject_widget)
        subject_layout.setContentsMargins(0, 0, 0, 0)
        
        self.subject_label = QtWidgets.QLabel("Subjects:")
        subject_layout.addWidget(self.subject_label)
        
        # Create list widget for multiple subject selection
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.subject_list.setMinimumHeight(150)
        subject_layout.addWidget(self.subject_list)
        
        # Subject selection buttons
        button_frame = QtWidgets.QFrame()
        button_frame.setFrameStyle(QtWidgets.QFrame.NoFrame)
        button_frame.setFixedWidth(120)  # Same width as browse button
        
        selection_buttons_layout = QtWidgets.QVBoxLayout(button_frame)
        selection_buttons_layout.setContentsMargins(0, 0, 0, 0)
        selection_buttons_layout.setSpacing(8)
        selection_buttons_layout.setAlignment(QtCore.Qt.AlignTop)
        
        # Create buttons with consistent styling
        button_style = """
            QPushButton {
                padding: 5px;
                background-color: #f0f0f0;
                border: 1px solid #c0c0c0;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """
        
        self.select_all_btn = QtWidgets.QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_subjects)
        self.select_all_btn.setStyleSheet(button_style)
        selection_buttons_layout.addWidget(self.select_all_btn)
        
        self.clear_selection_btn = QtWidgets.QPushButton("Clear Selection")
        self.clear_selection_btn.clicked.connect(self.clear_subject_selection)
        self.clear_selection_btn.setStyleSheet(button_style)
        selection_buttons_layout.addWidget(self.clear_selection_btn)
        
        self.refresh_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.refresh_subjects_btn.clicked.connect(self.update_available_subjects)
        self.refresh_subjects_btn.setStyleSheet(button_style)
        selection_buttons_layout.addWidget(self.refresh_subjects_btn)
        
        selection_buttons_layout.addStretch()
        subject_layout.addWidget(button_frame)
        
        main_container_layout.addWidget(subject_widget)
        
        # Options and control buttons section with consistent layout
        options_buttons_widget = QtWidgets.QWidget()
        options_buttons_layout = QtWidgets.QHBoxLayout(options_buttons_widget)
        options_buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # Pre-processing options group
        self.options_group = QtWidgets.QGroupBox("Processing Options")
        options_layout = QtWidgets.QVBoxLayout(self.options_group)
        
        # DICOM to NIfTI conversion
        self.convert_dicom_cb = QtWidgets.QCheckBox("Convert DICOM files to NIfTI")
        self.convert_dicom_cb.setChecked(True)
        options_layout.addWidget(self.convert_dicom_cb)
        
        # FreeSurfer recon-all
        self.run_recon_cb = QtWidgets.QCheckBox("Run FreeSurfer recon-all")
        self.run_recon_cb.setChecked(True)
        options_layout.addWidget(self.run_recon_cb)
        
        # Parallel processing
        self.parallel_cb = QtWidgets.QCheckBox("Run FreeSurfer reconstruction in parallel (requires GNU Parallel)")
        self.parallel_cb.setEnabled(True)
        options_layout.addWidget(self.parallel_cb)
        self.run_recon_cb.toggled.connect(self.toggle_dependent_options)
        
        # Create SimNIBS m2m folder
        self.create_m2m_cb = QtWidgets.QCheckBox("Create SimNIBS m2m folder")
        self.create_m2m_cb.setChecked(True)
        options_layout.addWidget(self.create_m2m_cb)
        
        # Small Atlas Segmentation Button inside options group
        self.atlas_btn = QtWidgets.QPushButton("Run Atlas Segmentation (selected)")
        self.atlas_btn.setFixedWidth(200)
        self.atlas_btn.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        self.atlas_btn.clicked.connect(self.run_atlas_segmentation)
        options_layout.addWidget(self.atlas_btn)
        
        # Quiet mode
        self.quiet_cb = QtWidgets.QCheckBox("Run in quiet mode (suppress output)")
        options_layout.addWidget(self.quiet_cb)
        
        options_buttons_layout.addWidget(self.options_group)
        
        # Control buttons - same width as subject selection buttons
        control_button_frame = QtWidgets.QFrame()
        control_button_frame.setFrameStyle(QtWidgets.QFrame.NoFrame)
        control_button_frame.setFixedWidth(160)  # Match previous button width
        
        control_buttons_layout = QtWidgets.QVBoxLayout(control_button_frame)
        control_buttons_layout.setContentsMargins(0, 22, 0, 0)  # Top margin to align with options box header
        control_buttons_layout.setSpacing(10)
        control_buttons_layout.setAlignment(QtCore.Qt.AlignTop)
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Run Pre-process")
        self.run_btn.clicked.connect(self.run_preprocessing)
        self.run_btn.setMinimumWidth(160)
        self.run_btn.setMinimumHeight(40)
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px; padding: 8px;")
        control_buttons_layout.addWidget(self.run_btn)
        
        # Stop button
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_preprocessing)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background-color: #cccccc; color: #888888; font-weight: bold; padding: 8px;")
        control_buttons_layout.addWidget(self.stop_btn)
        
        # Clear button
        self.clear_btn = QtWidgets.QPushButton("Clear Console")
        self.clear_btn.clicked.connect(self.clear_console)
        control_buttons_layout.addWidget(self.clear_btn)
        
        options_buttons_layout.addWidget(control_button_frame)
        
        main_container_layout.addWidget(options_buttons_widget)
        
        # Add main container to scroll layout
        scroll_layout.addWidget(main_container)
        scroll_layout.addStretch()
        
        # Finish scroll area setup
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Console output
        output_label = QtWidgets.QLabel("Console Output")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        main_layout.addWidget(output_label)
        self.console_output = QtWidgets.QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self.console_output.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; background-color: #1e1e1e; color: #f0f0f0; font-size: 13px; border: 1px solid #3c3c3c; border-radius: 5px; padding: 8px;")
        main_layout.addWidget(self.console_output)
        
        # Connect signals for dependent options
        self.run_recon_cb.toggled.connect(self.toggle_dependent_options)

        # Connect subject selection change to atlas button enable logic
        self.subject_list.itemSelectionChanged.connect(self.update_atlas_btn_state)
        # Also call after project dir/subject list update
        self.update_atlas_btn_state()
    
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
    
    def detect_project_dir(self):
        """Try to automatically detect the project directory."""
        # First check if we're in a docker environment with /mnt mounted
        if os.path.isdir("/mnt"):
            # Look for directories under /mnt
            for dir_name in os.listdir("/mnt"):
                dir_path = os.path.join("/mnt", dir_name)
                if os.path.isdir(dir_path):
                    return dir_path
        
        # If not in docker, try some common paths
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        potential_dirs = [
            script_dir,  # Current directory
            os.path.join(script_dir, "BIDS_test")  # BIDS_test subdirectory
        ]
        
        for dir_path in potential_dirs:
            if os.path.isdir(dir_path):
                return dir_path
        
        return None
    
    def browse_project_dir(self):
        """Open file dialog to browse for project directory."""
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Project Directory", 
            self.project_dir or os.path.expanduser("~")
        )
        
        if dir_path:
            self.project_dir = dir_path
            self.project_dir_input.setText(dir_path)
            self.update_available_subjects()
            self.update_atlas_btn_state()
    
    def update_available_subjects(self):
        """Update the list of available subjects in the project directory."""
        if not self.project_dir or not os.path.isdir(self.project_dir):
            self.console_output.append("Error: Project directory not found.")
            return
        
        self.project_dir_input.setText(self.project_dir)
        self.subject_list.clear()
        self.console_output.clear()
        
        subjects = []
        project_dir = self.project_dir or os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        for subject_dir in glob.glob(os.path.join(project_dir, '*')):
            if os.path.isdir(subject_dir):
                subject_id = os.path.basename(subject_dir)
                subjects.append(subject_id)
                self.subject_list.addItem(subject_id)
        
        # Console output: subjects found
        self.console_output.append("=== Subjects Found ===")
        if not subjects:
            self.console_output.append("No subjects found.")
        for subject_id in subjects:
            dicom_dir = os.path.join(project_dir, subject_id, 'DICOM')
            dicom_found = False
            if os.path.isdir(dicom_dir):
                for root, dirs, files in os.walk(dicom_dir):
                    if any(f.lower().endswith('.dcm') for f in files):
                        dicom_found = True
                        break
            status = '[✓] DICOMs found' if dicom_found else '[✗] No DICOMs'
            self.console_output.append(f"{subject_id}: {status}")
        self.console_output.append("")
        self.update_atlas_btn_state()
    
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
        
        # Update UI state before processing
        self.console_output.clear()
        self.processing_running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px;")
        self.subject_list.setEnabled(False)
        self.select_all_btn.setEnabled(False)
        self.clear_selection_btn.setEnabled(False)
        self.refresh_subjects_btn.setEnabled(False)
        self.browse_project_btn.setEnabled(False)
        self.convert_dicom_cb.setEnabled(False)
        self.run_recon_cb.setEnabled(False)
        self.parallel_cb.setEnabled(False)
        self.create_m2m_cb.setEnabled(False)
        self.quiet_cb.setEnabled(False)
        
        # Process subjects sequentially
        self.console_output.append(f"Starting pre-processing for {len(selected_subjects)} subjects...")
        
        # Process each subject sequentially
        self.process_next_subject(selected_subjects, 0)
    
    def process_next_subject(self, subjects, index):
        """Process the next subject in the queue."""
        if index >= len(subjects):
            # All subjects have been processed
            self.preprocessing_finished()
            self.console_output.append("All subjects have been processed.")
            return
            
        subject_id = subjects[index]
        subject_dir = os.path.join(self.project_dir, subject_id)
        
        # Display status
        self.console_output.append(f"\n--- Processing subject {index+1}/{len(subjects)}: {subject_id} ---")
        
        # Check subject directory
        if not os.path.isdir(subject_dir):
            self.console_output.append(f"Error: Subject directory not found: {subject_dir}")
            # Continue with next subject
            self.process_next_subject(subjects, index + 1)
            return
        
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
        
        # Start pre-processing thread
        self.console_output.append(f"Running command: {' '.join(cmd)}")
        
        # Set up environment variables
        env = os.environ.copy()
        
        # Start pre-processing thread for this subject
        self.processing_thread = PreProcessThread(cmd, env)
        self.processing_thread.output_signal.connect(self.update_output)
        self.processing_thread.finished.connect(lambda: self.subject_finished(subjects, index))
        self.processing_thread.start()
    
    def subject_finished(self, subjects, index):
        """Handle completion of a subject and move to the next one."""
        current_subject = subjects[index]
        self.console_output.append(f"Completed processing for subject {current_subject}")
        
        # Process the next subject
        self.process_next_subject(subjects, index + 1)
    
    def preprocessing_finished(self):
        """Handle completion of all pre-processing operations."""
        self.console_output.append("Pre-processing operations completed for all subjects.")
        
        # Re-enable UI elements
        self.processing_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background-color: #cccccc; color: #888888; font-weight: bold; padding: 8px;")
        self.subject_list.setEnabled(True)
        self.select_all_btn.setEnabled(True)
        self.clear_selection_btn.setEnabled(True)
        self.refresh_subjects_btn.setEnabled(True)
        self.browse_project_btn.setEnabled(True)
        self.convert_dicom_cb.setEnabled(True)
        self.run_recon_cb.setEnabled(True)
        self.toggle_dependent_options()  # This will set the parallel checkbox correctly
        self.create_m2m_cb.setEnabled(True)
        self.quiet_cb.setEnabled(True)

        # --- Atlas Segmentation: Automatically run after m2m creation ---
        if self.create_m2m_cb.isChecked():
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            for subject_id in selected_subjects:
                m2m_folder = os.path.join(self.project_dir, subject_id, 'SimNIBS', f'm2m_{subject_id}')
                if not os.path.isdir(m2m_folder):
                    self.console_output.append(f"[Atlas] {subject_id}: m2m folder not found, skipping atlas segmentation.")
                    continue
                output_dir = os.path.join(m2m_folder, 'segmentation')
                os.makedirs(output_dir, exist_ok=True)
                for atlas in ["a2009s", "DK40", "HCP_MMP1"]:
                    cmd = ["subject_atlas", "-m", m2m_folder, "-a", atlas, "-o", output_dir]
                    self.console_output.append(f"[Atlas] {subject_id}: Running {' '.join(cmd)}")
                    try:
                        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if proc.returncode == 0:
                            self.console_output.append(f"[Atlas] {subject_id}: Atlas {atlas} segmentation complete.")
                        else:
                            self.console_output.append(f"[Atlas] {subject_id}: Atlas {atlas} segmentation failed.\n{proc.stderr}")
                    except Exception as e:
                        self.console_output.append(f"[Atlas] {subject_id}: Error running subject_atlas: {e}")
    
    def stop_preprocessing(self):
        """Stop the running pre-processing operation."""
        if not self.processing_running or not self.processing_thread:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Termination",
            "Are you sure you want to stop the running pre-processing operation?\n\nThis might leave files in an inconsistent state.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.console_output.append("Terminating pre-processing operation...")
            if self.processing_thread.terminate_process():
                self.console_output.append("Pre-processing operation terminated.")
                # Force clean up of UI
                self.preprocessing_finished()
                self.stop_btn.setStyleSheet("background-color: #cccccc; color: #888888; font-weight: bold; padding: 8px;")
            else:
                self.console_output.append("Failed to terminate the pre-processing operation.")
    
    def clear_console(self):
        """Clear the output console."""
        self.console_output.clear()
    
    def update_output(self, text):
        """Update the console output with text from the pre-processing thread."""
        self.console_output.append(text)
        # Auto-scroll to the bottom
        cursor = self.console_output.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.console_output.setTextCursor(cursor)
        QtWidgets.QApplication.processEvents()  # Update UI 

    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()

    def clear_subject_selection(self):
        """Clear the selected subjects in the subject list."""
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