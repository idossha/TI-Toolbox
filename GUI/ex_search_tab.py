#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Ex-Search Tab
This module provides a GUI interface for the ex-search optimization functionality.
"""

import os
import json
import re
import subprocess
import csv
import time
from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite

class ExSearchThread(QtCore.QThread):
    """Thread to run ex-search optimization in background to prevent GUI freezing."""
    
    # Signal to emit output text with message type
    output_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(ExSearchThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        self.input_data = None
        
    def set_input_data(self, input_data):
        """Set input data to be passed to the process."""
        self.input_data = input_data
        
    def run(self):
        """Run the ex-search command in a separate thread."""
        try:
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,  # Combine stderr with stdout to prevent blocking
                stdin=subprocess.PIPE if self.input_data else None,
                universal_newlines=True,
                bufsize=1,
                env=self.env
            )
            
            # If input data is provided, send it to the process
            if self.input_data:
                for line in self.input_data:
                    if self.terminated:
                        break
                    self.process.stdin.write(line + '\n')
                    self.process.stdin.flush()
                self.process.stdin.close()
            
            # Real-time output display with message type detection
            for line in iter(self.process.stdout.readline, ''):
                if self.terminated:
                    break
                if line:
                    # Detect message type based on content
                    line_stripped = line.strip()
                    if any(keyword in line_stripped.lower() for keyword in ['error:', 'critical:', 'failed', 'exception']):
                        message_type = 'error'
                    elif any(keyword in line_stripped.lower() for keyword in ['warning:', 'warn']):
                        message_type = 'warning'
                    elif any(keyword in line_stripped.lower() for keyword in ['debug:']):
                        message_type = 'debug'
                    elif any(keyword in line_stripped.lower() for keyword in ['executing:', 'running', 'command']):
                        message_type = 'command'
                    elif any(keyword in line_stripped.lower() for keyword in ['completed successfully', 'completed.', 'successfully', 'completed:']):
                        message_type = 'success'
                    elif any(keyword in line_stripped.lower() for keyword in ['processing', 'starting']):
                        message_type = 'info'
                    else:
                        message_type = 'default'
                    
                    self.output_signal.emit(line_stripped, message_type)
            
            # Check process completion
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    self.error_signal.emit(f"Process returned non-zero exit code: {returncode}")
                    
        except Exception as e:
            self.error_signal.emit(f"Error running process: {str(e)}")
        finally:
            # Ensure process is cleaned up
            if self.process:
                try:
                    self.process.stdout.close()
                    if self.process.stdin:
                        self.process.stdin.close()
                except:
                    pass
    
    def terminate_process(self):
        """Terminate the running process."""
        if self.process and self.process.poll() is None:
            self.terminated = True
            if os.name == 'nt':  # Windows
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:  # Unix/Linux/Mac
                import signal
                try:
                    parent_pid = self.process.pid
                    ps_output = subprocess.check_output(f"ps -o pid --ppid {parent_pid} --noheaders", shell=True)
                    child_pids = [int(pid) for pid in ps_output.decode().strip().split('\n') if pid]
                    for pid in child_pids:
                        os.kill(pid, signal.SIGTERM)
                except:
                    pass
                
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            
            return True
        return False

class ExSearchTab(QtWidgets.QWidget):
    """Tab for ex-search optimization functionality."""
    
    def __init__(self, parent=None):
        super(ExSearchTab, self).__init__(parent)
        self.parent = parent
        self.optimization_running = False
        self.optimization_process = None
        self.setup_ui()
        
        # Initialize with available subjects and check leadfields
        QtCore.QTimer.singleShot(500, self.initial_setup)
    
    def create_log_file_env(self, process_name, subject_id):
        """Create log file environment variable for processes."""
        try:
            # Create timestamp for log file
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            
            # Get project directory structure
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            derivatives_dir = os.path.join(project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'logs', f'sub-{subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file path
            log_file = os.path.join(log_dir, f'{process_name}_{time_stamp}.log')
            
            return log_file
            
        except Exception as e:
            self.update_output(f"Warning: Could not create log file: {str(e)}", 'warning')
            return None
        
    def setup_ui(self):
        """Set up the user interface for the ex-search tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Add status label at the top
        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #f44336;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
                min-height: 10px;
                max-height: 10px;
            }
        """)
        self.status_label.setAlignment(QtCore.Qt.AlignVCenter)
        self.status_label.hide()  # Initially hidden
        main_layout.addWidget(self.status_label)
        
        # Create two main containers: controls and console
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        
        # Top container for controls
        controls_container = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(controls_container)
        
        # Create a scroll area for the controls
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Main horizontal layout to separate left and right
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        
        # Left side layout for subjects and ROIs
        left_layout = QtWidgets.QVBoxLayout()
        
        # Subject selection
        subject_container = QtWidgets.QGroupBox("Subject")
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        
        # Combo box for subject selection
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.setMinimumHeight(25)
        self.subject_combo.setMaximumHeight(25)
        subject_layout.addWidget(self.subject_combo)
        
        # Subject control buttons
        subject_button_layout = QtWidgets.QHBoxLayout()
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        self.clear_subject_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_subject_selection_btn.clicked.connect(self.clear_subject_selection)
        
        subject_button_layout.addWidget(self.list_subjects_btn)
        subject_button_layout.addWidget(self.clear_subject_selection_btn)
        subject_layout.addLayout(subject_button_layout)
        
        # Add subject container to left layout
        left_layout.addWidget(subject_container)
        
        # ROI selection
        roi_container = QtWidgets.QGroupBox("ROI(s)")
        roi_layout = QtWidgets.QVBoxLayout(roi_container)
        
        # List widget for ROI selection
        self.roi_list = QtWidgets.QListWidget()
        self.roi_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.roi_list.setMinimumHeight(80)  # Reduced from 100
        self.roi_list.setMaximumHeight(80)  # Added maximum height
        roi_layout.addWidget(self.roi_list)
        
        # ROI control buttons
        roi_button_layout = QtWidgets.QHBoxLayout()
        self.add_roi_btn = QtWidgets.QPushButton("Add ROI")
        self.add_roi_btn.clicked.connect(self.show_add_roi_dialog)
        self.remove_roi_btn = QtWidgets.QPushButton("Remove ROI")
        self.remove_roi_btn.clicked.connect(self.remove_selected_roi)
        self.list_rois_btn = QtWidgets.QPushButton("Refresh List")
        self.list_rois_btn.clicked.connect(self.update_roi_list)
        
        roi_button_layout.addWidget(self.add_roi_btn)
        roi_button_layout.addWidget(self.remove_roi_btn)
        roi_button_layout.addWidget(self.list_rois_btn)
        roi_layout.addLayout(roi_button_layout)
        
        # Add ROI container to left layout
        left_layout.addWidget(roi_container)
        
        # Right side layout for electrodes and controls
        right_layout = QtWidgets.QVBoxLayout()
        
        # Electrode selection
        electrode_container = QtWidgets.QGroupBox("Electrode Selection")
        electrode_layout = QtWidgets.QFormLayout(electrode_container)
        electrode_layout.setContentsMargins(10, 10, 10, 10)  # Reduced margins
        electrode_layout.setSpacing(5)  # Reduced spacing between elements
        
        # Create input fields for each electrode category
        self.e1_plus_input = QtWidgets.QLineEdit()
        self.e1_minus_input = QtWidgets.QLineEdit()
        self.e2_plus_input = QtWidgets.QLineEdit()
        self.e2_minus_input = QtWidgets.QLineEdit()
        
        # Set fixed height for input fields
        for input_field in [self.e1_plus_input, self.e1_minus_input, self.e2_plus_input, self.e2_minus_input]:
            input_field.setFixedHeight(25)
        
        # Set placeholders
        self.e1_plus_input.setPlaceholderText("E.g., E1, E2")
        self.e1_minus_input.setPlaceholderText("E.g., E3, E4")
        self.e2_plus_input.setPlaceholderText("E.g., E5, E6")
        self.e2_minus_input.setPlaceholderText("E.g., E7, E8")
        
        # Add input fields to layout with labels
        electrode_layout.addRow("E1+ electrodes:", self.e1_plus_input)
        electrode_layout.addRow("E1- electrodes:", self.e1_minus_input)
        electrode_layout.addRow("E2+ electrodes:", self.e2_plus_input)
        electrode_layout.addRow("E2- electrodes:", self.e2_minus_input)
        
        # Add help text
        help_label = QtWidgets.QLabel("Enter electrode names separated by commas. All categories must have the same number of electrodes.")
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        electrode_layout.addRow(help_label)
        
        # Add electrode container to right layout
        right_layout.addWidget(electrode_container)
        
        # Leadfield Management
        leadfield_container = QtWidgets.QGroupBox("Leadfield Management")
        leadfield_layout = QtWidgets.QVBoxLayout(leadfield_container)
        leadfield_layout.setContentsMargins(10, 10, 10, 10)
        leadfield_layout.setSpacing(8)
        
        # Available leadfields section
        available_label = QtWidgets.QLabel("Available Leadfields:")
        available_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        leadfield_layout.addWidget(available_label)
        
        # Leadfield list
        self.leadfield_list = QtWidgets.QListWidget()
        self.leadfield_list.setMaximumHeight(100)
        self.leadfield_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        leadfield_layout.addWidget(self.leadfield_list)
        
        # Selected leadfield info
        self.selected_leadfield_label = QtWidgets.QLabel("Selected: None")
        self.selected_leadfield_label.setStyleSheet("color: #666; font-style: italic; margin: 5px 0;")
        leadfield_layout.addWidget(self.selected_leadfield_label)
        
        # Leadfield action buttons
        leadfield_buttons_layout = QtWidgets.QHBoxLayout()
        
        self.refresh_leadfields_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_leadfields_btn.setFixedHeight(25)
        self.refresh_leadfields_btn.clicked.connect(self.refresh_leadfields)
        leadfield_buttons_layout.addWidget(self.refresh_leadfields_btn)
        
        self.show_electrodes_leadfield_btn = QtWidgets.QPushButton("Show Electrodes")
        self.show_electrodes_leadfield_btn.setFixedHeight(25)
        self.show_electrodes_leadfield_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.show_electrodes_leadfield_btn.setEnabled(False)  # Initially disabled
        self.show_electrodes_leadfield_btn.clicked.connect(self.show_electrodes_for_selected_leadfield)
        leadfield_buttons_layout.addWidget(self.show_electrodes_leadfield_btn)
        
        self.create_leadfield_btn = QtWidgets.QPushButton("Create New")
        self.create_leadfield_btn.setFixedHeight(25)
        self.create_leadfield_btn.clicked.connect(self.show_create_leadfield_dialog)
        leadfield_buttons_layout.addWidget(self.create_leadfield_btn)
        
        leadfield_layout.addLayout(leadfield_buttons_layout)
        
        # Connect leadfield selection
        self.leadfield_list.itemSelectionChanged.connect(self.on_leadfield_selection_changed)
        
        # Add leadfield container to right layout
        right_layout.addWidget(leadfield_container)
        
        # Add left and right layouts to main horizontal layout
        main_horizontal_layout.addLayout(left_layout)
        main_horizontal_layout.addLayout(right_layout)
        
        # Add main horizontal layout to scroll layout
        scroll_layout.addLayout(main_horizontal_layout)
        
        # Set the scroll content and add to controls layout
        scroll_area.setWidget(scroll_content)
        # Add the controls section to the main layout
        main_layout.addWidget(scroll_area)
        
        # Remove old splitter-based console container code (no longer needed)
        # --- Console and Buttons Section (MATCH OTHER TABS) ---
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        
        # Console buttons layout
        console_buttons_layout = QtWidgets.QHBoxLayout()
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Run Ex-Search")
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
        console_buttons_layout.addWidget(self.run_btn)
        self.run_btn.clicked.connect(self.run_optimization)
        
        # Stop button
        self.stop_btn = QtWidgets.QPushButton("Stop Ex-Search")
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
        self.stop_btn.setEnabled(False)
        console_buttons_layout.addWidget(self.stop_btn)
        self.stop_btn.clicked.connect(self.stop_optimization)
        
        # Clear console button
        self.clear_console_btn = QtWidgets.QPushButton("Clear Console")
        self.clear_console_btn.setStyleSheet("""
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
        console_buttons_layout.addWidget(self.clear_console_btn)
        self.clear_console_btn.clicked.connect(self.clear_console)
        
        # Console header layout (label + buttons)
        console_header_layout = QtWidgets.QHBoxLayout()
        console_header_layout.addWidget(output_label)
        console_header_layout.addStretch()
        console_header_layout.addLayout(console_buttons_layout)
        
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
        
        # Console layout
        console_layout = QtWidgets.QVBoxLayout()
        console_layout.addLayout(console_header_layout)
        console_layout.addWidget(self.console_output)
        
        # Add console layout to main layout
        main_layout.addLayout(console_layout)
        
        # After self.subject_combo is created and added:
        self.subject_combo.currentTextChanged.connect(self.on_subject_selection_changed)
    
    def initial_setup(self):
        """Initial setup when the tab is first loaded."""
        self.list_subjects()
        self.update_output("Welcome to Ex-Search Optimization!")
        self.update_output("\nChecking available subjects and leadfields...")
        
        try:
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            simnibs_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
            
            # Count subjects and leadfields with new naming scheme
            subject_count = 0
            total_leadfields = 0
            subjects_with_leadfields = {}
            
            for item in os.listdir(simnibs_dir):
                if item.startswith("sub-"):
                    subject_id = item[4:]  # Remove 'sub-' prefix
                    subject_count += 1
                    subject_dir = os.path.join(simnibs_dir, item)
                    
                    # Look for leadfield directories with new pattern: leadfield_vol_*
                    subject_leadfields = []
                    for subdir in os.listdir(subject_dir):
                        if subdir.startswith("leadfield_vol_"):
                            leadfield_path = os.path.join(subject_dir, subdir)
                            # Check if leadfield.hdf5 exists
                            hdf5_file = os.path.join(leadfield_path, "leadfield.hdf5")
                            if os.path.exists(hdf5_file):
                                net_name = subdir[len("leadfield_vol_"):]
                                subject_leadfields.append(net_name)
                                total_leadfields += 1
                    
                    if subject_leadfields:
                        subjects_with_leadfields[subject_id] = subject_leadfields
            
            # Display summary
            self.update_output(f"\nFound {subject_count} subject(s):")
            self.update_output(f"- Total leadfield matrices: {total_leadfields}")
            self.update_output(f"- Subjects with leadfields: {len(subjects_with_leadfields)}")
            
            for subject_id, nets in subjects_with_leadfields.items():
                self.update_output(f"  {subject_id}: {', '.join(nets)}")
            
            subjects_without_leadfield = [sid for sid in range(1, subject_count+1) 
                                        if str(sid) not in subjects_with_leadfields]
            if subjects_without_leadfield:
                self.update_output(f"- Subjects without leadfields: {', '.join(map(str, subjects_without_leadfield))}")
            
            self.update_output("\nTo start optimization:")
            self.update_output("1. Select a subject")
            self.update_output("2. Select or create ROI(s)")
            self.update_output("3. Enter electrodes for each category (E1+, E1-, E2+, E2-)")
            self.update_output("4. Click 'Run Ex-Search'")
            
        except Exception as e:
            self.update_output(f"Error during initial setup: {str(e)}")
    
    def refresh_leadfields(self):
        """Refresh the list of available leadfields for the selected subject."""
        subject_id = self.subject_combo.currentText()
        self.leadfield_list.clear()
        self.selected_leadfield_label.setText("Selected: None")
        self.show_electrodes_leadfield_btn.setEnabled(False)
        
        if not subject_id:
            return
        
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        subject_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}")
        
        try:
            # Look for leadfield directories with pattern: leadfield_vol_*
            leadfields = []
            if os.path.exists(subject_dir):
                for item in os.listdir(subject_dir):
                    if item.startswith("leadfield_vol_"):
                        leadfield_path = os.path.join(subject_dir, item)
                        # Check if leadfield.hdf5 exists
                        hdf5_file = os.path.join(leadfield_path, "leadfield.hdf5")
                        if os.path.exists(hdf5_file):
                            net_name = item[len("leadfield_vol_"):]
                            # Get file size for display
                            file_size = os.path.getsize(hdf5_file) / (1024**3)  # GB
                            leadfields.append((net_name, hdf5_file, file_size))
            
            # Populate the list
            for net_name, hdf5_path, file_size in sorted(leadfields):
                item_text = f"{net_name} ({file_size:.1f} GB)"
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(QtCore.Qt.UserRole, {"net_name": net_name, "hdf5_path": hdf5_path})
                self.leadfield_list.addItem(item)
            
            if not leadfields:
                no_leadfields_item = QtWidgets.QListWidgetItem("No leadfields found")
                no_leadfields_item.setFlags(QtCore.Qt.NoItemFlags)  # Make it non-selectable
                no_leadfields_item.setForeground(QtGui.QColor("#666"))
                self.leadfield_list.addItem(no_leadfields_item)
                
        except Exception as e:
            self.update_status(f"Error refreshing leadfields: {str(e)}", error=True)
    
    def on_leadfield_selection_changed(self):
        """Handle leadfield selection changes."""
        selected_items = self.leadfield_list.selectedItems()
        if selected_items and selected_items[0].data(QtCore.Qt.UserRole):
            data = selected_items[0].data(QtCore.Qt.UserRole)
            net_name = data["net_name"]
            self.selected_leadfield_label.setText(f"Selected: {net_name}")
            self.selected_leadfield_label.setStyleSheet("color: #4caf50; font-weight: bold;")
            self.show_electrodes_leadfield_btn.setEnabled(True)
        else:
            self.selected_leadfield_label.setText("Selected: None")
            self.selected_leadfield_label.setStyleSheet("color: #666; font-style: italic;")
            self.show_electrodes_leadfield_btn.setEnabled(False)
    
    def get_available_eeg_nets(self, subject_id):
        """Get available EEG nets for a subject."""
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        eeg_positions_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                        f"m2m_{subject_id}", "eeg_positions")
        
        eeg_nets = []
        if os.path.exists(eeg_positions_dir):
            for file in os.listdir(eeg_positions_dir):
                if file.endswith('.csv'):
                    eeg_nets.append(file)
        
        return sorted(eeg_nets)
    
    def show_create_leadfield_dialog(self):
        """Show dialog to select EEG net and create leadfield."""
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            self.update_status("Please select a subject first", error=True)
            return
        
        # Get available EEG nets
        eeg_nets = self.get_available_eeg_nets(subject_id)
        if not eeg_nets:
            QtWidgets.QMessageBox.warning(self, "No EEG Nets Found", 
                                        f"No EEG net files found for subject {subject_id}")
            return
        
        # Create selection dialog
        dialog = EEGNetSelectionDialog(eeg_nets, subject_id, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_net = dialog.get_selected_net()
            if selected_net:
                self.create_leadfield_with_net(subject_id, selected_net)
    
    def create_leadfield_with_net(self, subject_id, eeg_net_file):
        """Create leadfield with selected EEG net."""
        try:
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            m2m_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                  f"m2m_{subject_id}")
            eeg_cap_path = os.path.join(m2m_dir, "eeg_positions", eeg_net_file)
            net_name_clean = eeg_net_file.replace('.csv', '')
            
            # Prepare command with new leadfield.py arguments
            leadfield_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                          "ex-search", "leadfield.py")
            cmd = ["simnibs_python", leadfield_script, m2m_dir, eeg_cap_path, net_name_clean]
            
            # Set up environment variables with log file
            env = os.environ.copy()
            log_file = self.create_log_file_env('leadfield_creation', subject_id)
            if log_file:
                env["TI_LOG_FILE"] = log_file
                self.update_output(f"Log file: {log_file}")
            
            # Create and start thread
            self.optimization_process = ExSearchThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
            self.optimization_process.finished.connect(self.leadfield_creation_completed)
            self.optimization_process.start()
            
            # Update UI
            self.disable_controls()
            self.update_status(f"Creating leadfield for {net_name_clean}...")
            self.update_output(f"Creating leadfield for EEG net: {eeg_net_file}")
            
        except Exception as e:
            self.update_status(f"Error creating leadfield: {str(e)}", error=True)
            self.enable_controls()
    
    def show_electrodes_for_selected_leadfield(self):
        """Show electrodes for the currently selected leadfield."""
        # Get selected leadfield
        selected_items = self.leadfield_list.selectedItems()
        if not selected_items or not selected_items[0].data(QtCore.Qt.UserRole):
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a leadfield first")
            return
        
        # Get leadfield data
        leadfield_data = selected_items[0].data(QtCore.Qt.UserRole)
        net_name = leadfield_data["net_name"]
        subject_id = self.subject_combo.currentText()
        
        if not subject_id:
            QtWidgets.QMessageBox.warning(self, "No Subject", "Please select a subject first")
            return
        
        try:
            # Try to find the EEG cap file for this net
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            
            # First try the subject's eeg_positions directory
            eeg_cap_file = f"{net_name}.csv"
            eeg_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                  f"m2m_{subject_id}", "eeg_positions", eeg_cap_file)
            
            if not os.path.exists(eeg_path):
                # Fallback to assets directory
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                eeg_path = os.path.join(script_dir, "assets", "ElectrodeCaps_MNI", eeg_cap_file)
            
            if not os.path.exists(eeg_path):
                QtWidgets.QMessageBox.warning(self, "EEG File Not Found", 
                                            f"Could not find EEG cap file for {net_name}")
                return
            
            # Read electrode information - all files follow same format: Electrode,X,Y,Z,Label
            electrodes = []
            with open(eeg_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 5 and parts[0] == 'Electrode':
                        electrode_label = parts[4].strip()  # 5th column (index 4) is the label
                        if electrode_label and not electrode_label.replace('.', '').replace('-', '').isdigit():  # Skip numeric values
                            electrodes.append(electrode_label)
            
            if not electrodes:
                QtWidgets.QMessageBox.information(self, "No Electrodes", 
                                                f"No electrode labels found for {net_name}")
                return
            
            # Create and show electrode display dialog
            electrode_dialog = ElectrodeDisplayDialog(net_name, electrodes, self)
            electrode_dialog.exec_()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", 
                                         f"Error reading electrode information: {str(e)}")
    
    def list_subjects(self):
        """List available subjects in the combo box."""
        self.subject_combo.clear()
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        if not project_dir or not os.path.exists(project_dir):
            self.update_status("No project directory selected", error=True)
            return
            
        subjects_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
        if not os.path.exists(subjects_dir):
            self.update_status("No subjects directory found", error=True)
            return
            
        # Find all m2m_* directories
        subjects = []
        for item in os.listdir(subjects_dir):
            if item.startswith("sub-"):
                subject_path = os.path.join(subjects_dir, item)
                for m2m_dir in os.listdir(subject_path):
                    if m2m_dir.startswith("m2m_"):
                        subject_id = m2m_dir.replace("m2m_", "")
                        subjects.append(subject_id)
        
        if not subjects:
            self.update_status("No subjects found", error=True)
            return
            
        # Sort subjects naturally
        subjects.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', x)])
        self.subject_combo.addItems(subjects)
    
    def clear_subject_selection(self):
        """Clear the subject selection."""
        self.subject_combo.setCurrentIndex(-1)
        self.show_electrodes_leadfield_btn.setEnabled(False)
    
    def update_roi_list(self):
        """Update the list of available ROIs for the selected subject."""
        try:
            subject_id = self.subject_combo.currentText()
            if not subject_id:
                return
            
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                 f"m2m_{subject_id}", "ROIs")
            
            self.roi_list.clear()
            
            if os.path.exists(roi_dir):
                # First check for roi_list.txt
                roi_list_file = os.path.join(roi_dir, "roi_list.txt")
                if os.path.exists(roi_list_file):
                    with open(roi_list_file, 'r') as f:
                        rois = [line.strip() for line in f.readlines() if line.strip()]
                    # For each ROI, read coordinates and display as 'name: x, y, z'
                    for roi_name in rois:
                        roi_path = os.path.join(roi_dir, roi_name)
                        coords = None
                        if os.path.exists(roi_path):
                            with open(roi_path, 'r') as rf:
                                line = rf.readline().strip()
                                # Expect format: x, y, z
                                parts = [p.strip() for p in line.split(',')]
                                if len(parts) == 3:
                                    coords = ', '.join(parts)
                        display_name = roi_name.replace('.csv', '')
                        if coords:
                            self.roi_list.addItem(f"{display_name}: {coords}")
                        else:
                            self.roi_list.addItem(display_name)
                else:
                    # If roi_list.txt doesn't exist, look for all files in the ROIs directory
                    rois = [f for f in os.listdir(roi_dir) 
                           if not f.startswith('.') and f != 'roi_list.txt' 
                           and os.path.isfile(os.path.join(roi_dir, f))]
                    for roi_name in sorted(rois):
                        roi_path = os.path.join(roi_dir, roi_name)
                        coords = None
                        if os.path.exists(roi_path):
                            with open(roi_path, 'r') as rf:
                                line = rf.readline().strip()
                                parts = [p.strip() for p in line.split(',')]
                                if len(parts) == 3:
                                    coords = ', '.join(parts)
                        display_name = roi_name.replace('.csv', '')
                        if coords:
                            self.roi_list.addItem(f"{display_name}: {coords}")
                        else:
                            self.roi_list.addItem(display_name)
        except Exception as e:
            self.update_status(f"Error updating ROI list: {str(e)}", error=True)
    
    def show_add_roi_dialog(self):
        """Show dialog for adding a new ROI."""
        dialog = AddROIDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.update_roi_list()
    
    def remove_selected_roi(self):
        """Remove the selected ROI."""
        selected_items = self.roi_list.selectedItems()
        if not selected_items:
            self.update_status("Please select an ROI to remove", error=True)
            return
        
        # Get confirmation
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setText("Are you sure you want to remove the selected ROI(s)?")
        msg.setWindowTitle("Confirm ROI Removal")
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        
        if msg.exec_() == QtWidgets.QMessageBox.Yes:
            try:
                selected_subject = self.subject_combo.currentText()
                project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
                roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{selected_subject}",
                                     f"m2m_{selected_subject}", "ROIs")
                roi_list_file = os.path.join(roi_dir, "roi_list.txt")
                # Read existing ROIs
                if os.path.exists(roi_list_file):
                    with open(roi_list_file, 'r') as f:
                        rois = [line.strip() for line in f.readlines()]
                else:
                    rois = []
                # Remove selected ROIs
                for item in selected_items:
                    # Handle display format 'name: x, y, z' or just 'name'
                    roi_display = item.text()
                    roi_name = roi_display.split(':')[0].strip() + '.csv'
                    # Remove from roi_list.txt if present
                    if roi_name in rois:
                        rois.remove(roi_name)
                    # Remove the ROI file
                    roi_file = os.path.join(roi_dir, roi_name)
                    if os.path.exists(roi_file):
                        os.remove(roi_file)
                # Update roi_list.txt
                with open(roi_list_file, 'w') as f:
                    for roi in rois:
                        f.write(f"{roi}\n")
                self.update_roi_list()
                self.update_status("ROI(s) removed successfully")
            except Exception as e:
                self.update_status(f"Error removing ROI: {str(e)}", error=True)
    
    def parse_electrode_input(self, text):
        """Parse electrode input text into a list of electrodes."""
        # Split by comma and clean up whitespace
        electrodes = [e.strip() for e in text.split(',') if e.strip()]
        # Validate electrode format - support various naming conventions
        # E001, E1, Fp1, F3, C4, P3, O1, T7, Cz, etc.
        pattern = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')
        if not all(pattern.match(e) for e in electrodes):
            return None
        return electrodes
    
    def validate_inputs(self):
        """Validate all input fields before running optimization."""
        # Check if a subject is selected
        if self.subject_combo.currentText() == "":
            self.update_status("Please select a subject", error=True)
            return False
            
        # Check if a leadfield is selected
        selected_items = self.leadfield_list.selectedItems()
        if not selected_items or not selected_items[0].data(QtCore.Qt.UserRole):
            self.update_status("Please select a leadfield for simulation", error=True)
            return False
            
        # Check if ROIs are selected
        if self.roi_list.count() == 0:
            self.update_status("Please add at least one ROI", error=True)
            return False
            
        # Validate electrode inputs
        e1_plus = self.parse_electrode_input(self.e1_plus_input.text())
        e1_minus = self.parse_electrode_input(self.e1_minus_input.text())
        e2_plus = self.parse_electrode_input(self.e2_plus_input.text())
        e2_minus = self.parse_electrode_input(self.e2_minus_input.text())
        
        if not all([e1_plus, e1_minus, e2_plus, e2_minus]):
            self.update_status("Please enter valid electrode names for all categories", error=True)
            return False
            
        if not (len(e1_plus) == len(e1_minus) == len(e2_plus) == len(e2_minus)):
            self.update_status("All electrode categories must have the same number of electrodes", error=True)
            return False
            
        return True
    
    def run_optimization(self):
        """Run the ex-search optimization for selected subjects."""
        if not self.validate_inputs():
            return
            
        subject_id = self.subject_combo.currentText()
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        ex_search_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "ex-search")
        
        # Create ex_search directory if it doesn't exist
        os.makedirs(ex_search_dir, exist_ok=True)
        
        # Get electrode configurations
        e1_plus = self.parse_electrode_input(self.e1_plus_input.text())
        e1_minus = self.parse_electrode_input(self.e1_minus_input.text())
        e2_plus = self.parse_electrode_input(self.e2_plus_input.text())
        e2_minus = self.parse_electrode_input(self.e2_minus_input.text())
        
        # Set up environment variables
        env = os.environ.copy()
        env["SUBJECTS_DIR"] = project_dir
        
        # Disable controls and show status
        self.disable_controls()
        self.update_status(f"Running optimization for subject {subject_id}...")
        
        # Run the pipeline
        self.run_pipeline(subject_id, project_dir, ex_search_dir, e1_plus, e1_minus, e2_plus, e2_minus, env)
    
    def run_pipeline(self, subject_id, project_dir, ex_search_dir, e1_plus, e1_minus, e2_plus, e2_minus, env):
        """Run the ex-search pipeline steps sequentially."""
        # Get the script directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ex_search_scripts_dir = os.path.join(script_dir, "ex-search")
        
        # Get selected leadfield information
        selected_items = self.leadfield_list.selectedItems()
        if not selected_items or not selected_items[0].data(QtCore.Qt.UserRole):
            self.update_status("No leadfield selected", error=True)
            self.enable_controls()
            return
            
        leadfield_data = selected_items[0].data(QtCore.Qt.UserRole)
        selected_net_name = leadfield_data["net_name"]
        selected_hdf5_path = leadfield_data["hdf5_path"]
        
        # Set up base environment variables with log file
        env = os.environ.copy()
        env["PROJECT_DIR_NAME"] = os.path.basename(project_dir)
        env["PROJECT_DIR"] = project_dir
        env["SUBJECT_NAME"] = subject_id
        env["SUBJECTS_DIR"] = project_dir
        env["LEADFIELD_HDF"] = selected_hdf5_path
        env["SELECTED_EEG_NET"] = selected_net_name
        
        # Create shared log file for the entire ex-search pipeline
        log_file = self.create_log_file_env('ex_search', subject_id)
        if log_file:
            env["TI_LOG_FILE"] = log_file
            self.update_output(f"Ex-search log file: {log_file}")
        
        self.update_output(f"Using leadfield: {selected_net_name}")
        self.update_output(f"HDF5 file: {selected_hdf5_path}")
        
        # Step 1: Run the TI simulation (sequential, SimNIBS compatible)
        self.update_output("Step 1: Running TI simulation...")
        ti_sim_script = os.path.join(ex_search_scripts_dir, "ti_sim.py")
        
        # Prepare input data for the script
        input_data = [
            " ".join(e1_plus),
            " ".join(e1_minus),
            " ".join(e2_plus),
            " ".join(e2_minus),
            ""   # Use default 1mA (empty input will use default)
        ]
        
        # Command to run ti_sim.py (now with parallel processing)
        cmd = ["simnibs_python", ti_sim_script]
        
        # Create and start thread for step 1
        self.optimization_process = ExSearchThread(cmd, env)
        self.optimization_process.set_input_data(input_data)
        self.optimization_process.output_signal.connect(self.update_output)
        self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
        
        # Connect the finished signal to the next step
        self.optimization_process.finished.connect(
            lambda: self.run_roi_analyzer(subject_id, project_dir, ex_search_dir, env)
        )
        
        self.optimization_process.start()
    
    def run_roi_analyzer(self, subject_id, project_dir, ex_search_dir, env):
        """Run the ROI analyzer step."""
        # Step 2: Run ROI analyzer
        self.update_output("\nStep 2: Running ROI analysis...")
        roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                              f"m2m_{subject_id}", "ROIs")
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ex_search_scripts_dir = os.path.join(script_dir, "ex-search")
        roi_analyzer_script = os.path.join(ex_search_scripts_dir, "roi-analyzer.py")
        
        # Update environment variables for ROI analyzer
        env["PROJECT_DIR"] = project_dir
        env["SUBJECT_NAME"] = subject_id
        
        cmd = ["python3", roi_analyzer_script, roi_dir]
        
        self.optimization_process = ExSearchThread(cmd, env)
        self.optimization_process.output_signal.connect(self.update_output)
        self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
        
        # Connect the finished signal to the next step
        self.optimization_process.finished.connect(
            lambda: self.run_mesh_processing(subject_id, project_dir, ex_search_dir, roi_dir, env)
        )
        
        self.optimization_process.start()
    
    def run_mesh_processing(self, subject_id, project_dir, ex_search_dir, roi_dir, env):
        """Run the mesh processing step."""
        # Step 3: Run mesh processing
        self.update_output("\nStep 3: Running mesh processing...")
        
        try:
            # Get ROI coordinates from the first ROI file
            roi_list_file = os.path.join(roi_dir, "roi_list.txt")
            with open(roi_list_file, 'r') as f:
                first_roi = f.readline().strip()
            roi_file = os.path.join(roi_dir, first_roi)
            with open(roi_file, 'r') as f:
                coordinates = f.readline().strip()
            
            # Parse coordinates
            x, y, z = [float(coord.strip()) for coord in coordinates.split(',')]
            x_int, y_int, z_int = int(x), int(y), int(z)
            
            # Create directory name from coordinates
            coord_dir = f"xyz_{x_int}_{y_int}_{z_int}"
            mesh_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                                   "ex-search", coord_dir)
            
            # Create output directory if it doesn't exist
            os.makedirs(mesh_dir, exist_ok=True)
            
            # Run Python mesh processing (replaces MATLAB version)
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ex_search_scripts_dir = os.path.join(script_dir, "ex-search")
            mesh_processing_script = os.path.join(ex_search_scripts_dir, "mesh_field_analyzer.py")
            
            # Update environment variables for mesh processing
            env["PROJECT_DIR"] = project_dir
            env["SUBJECT_NAME"] = subject_id
            env["MESH_DIR"] = mesh_dir
            
            cmd = ["python3", mesh_processing_script, mesh_dir]
            
            self.optimization_process = ExSearchThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
            
            # Connect the finished signal to completion (final CSV is created by mesh processor)
            self.optimization_process.finished.connect(self.pipeline_completed)
            
            self.optimization_process.start()
        except Exception as e:
            self.update_output(f"Error in mesh processing: {str(e)}", 'error')
            self.enable_controls()
    

    def handle_process_error(self, error_msg):
        """Handle process errors with proper GUI state management."""
        self.update_output(error_msg, 'error')
        self.enable_controls()
        self.update_status("Process failed - see console for details", error=True)
    
    def leadfield_creation_completed(self):
        """Handle leadfield creation completion."""
        self.enable_controls()
        self.refresh_leadfields()
        self.update_status("Leadfield creation completed")
    
    def pipeline_completed(self):
        """Handle the completion of the pipeline."""
        # Final message
        self.update_output("\nOptimization process completed!")
        self.enable_controls()
        self.update_status("Ex-search optimization completed successfully")
    
    def stop_optimization(self):
        """Stop the running optimization process."""
        if self.optimization_process and self.optimization_process.terminate_process():
            self.update_status("Optimization stopped by user")
            self.update_output("Process terminated by user", 'warning')
            self.enable_controls()
        else:
            self.update_output("No running process to stop", 'warning')
    
    def clear_console(self):
        """Clear the console output."""
        self.console_output.clear()
    
    def update_output(self, text, message_type='default'):
        """Update the console output with colored text."""
        if not text.strip():
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
        
        # Append to the console with HTML formatting
        self.console_output.append(formatted_text)
        self.console_output.ensureCursorVisible()
        QtWidgets.QApplication.processEvents()
    
    def update_status(self, message, error=False):
        """Update the status label with a message."""
        self.status_label.setText(message)
        if error:
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #ffebee;
                    color: #f44336;
                    padding: 5px 10px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        else:
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f5e9;
                    color: #4caf50;
                    padding: 5px 10px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        self.status_label.show()
    
    def disable_controls(self):
        """Disable controls during optimization."""
        self.subject_combo.setEnabled(False)
        self.roi_list.setEnabled(False)
        self.e1_plus_input.setEnabled(False)
        self.e1_minus_input.setEnabled(False)
        self.e2_plus_input.setEnabled(False)
        self.e2_minus_input.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.list_subjects_btn.setEnabled(False)
        self.clear_subject_selection_btn.setEnabled(False)
        self.add_roi_btn.setEnabled(False)
        self.remove_roi_btn.setEnabled(False)
        self.list_rois_btn.setEnabled(False)
        self.leadfield_list.setEnabled(False)
        self.refresh_leadfields_btn.setEnabled(False)
        self.show_electrodes_leadfield_btn.setEnabled(False)
        self.create_leadfield_btn.setEnabled(False)
    
    def enable_controls(self):
        """Enable controls after optimization."""
        self.subject_combo.setEnabled(True)
        self.roi_list.setEnabled(True)
        self.e1_plus_input.setEnabled(True)
        self.e1_minus_input.setEnabled(True)
        self.e2_plus_input.setEnabled(True)
        self.e2_minus_input.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.list_subjects_btn.setEnabled(True)
        self.clear_subject_selection_btn.setEnabled(True)
        self.add_roi_btn.setEnabled(True)
        self.remove_roi_btn.setEnabled(True)
        self.list_rois_btn.setEnabled(True)
        self.leadfield_list.setEnabled(True)
        self.refresh_leadfields_btn.setEnabled(True)
        self.create_leadfield_btn.setEnabled(True)
        
        # Show Electrodes button should only be enabled if a leadfield is selected
        selected_items = self.leadfield_list.selectedItems()
        if selected_items and selected_items[0].data(QtCore.Qt.UserRole):
            self.show_electrodes_leadfield_btn.setEnabled(True)
        else:
            self.show_electrodes_leadfield_btn.setEnabled(False)
    
    def on_subject_selection_changed(self):
        """Handle subject selection changes."""
        self.refresh_leadfields()
        self.update_roi_list()

class AddROIDialog(QtWidgets.QDialog):
    """Dialog for adding a new ROI."""
    
    def __init__(self, parent=None):
        super(AddROIDialog, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Add New ROI")
        layout = QtWidgets.QVBoxLayout(self)
        
        # ROI coordinates
        coord_group = QtWidgets.QGroupBox("ROI Coordinates (subject space, RAS)")
        coord_layout = QtWidgets.QFormLayout()
        
        self.x_coord = QtWidgets.QDoubleSpinBox()
        self.x_coord.setRange(-1000, 1000)
        self.x_coord.setDecimals(2)  # Allow 2 decimal places
        self.y_coord = QtWidgets.QDoubleSpinBox()
        self.y_coord.setRange(-1000, 1000)
        self.y_coord.setDecimals(2)  # Allow 2 decimal places
        self.z_coord = QtWidgets.QDoubleSpinBox()
        self.z_coord.setRange(-1000, 1000)
        self.z_coord.setDecimals(2)  # Allow 2 decimal places
        
        coord_layout.addRow("X:", self.x_coord)
        coord_layout.addRow("Y:", self.y_coord)
        coord_layout.addRow("Z:", self.z_coord)
        
        coord_group.setLayout(coord_layout)
        layout.addWidget(coord_group)
        
        # ROI name
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("ROI Name:"))
        self.roi_name = QtWidgets.QLineEdit()
        name_layout.addWidget(self.roi_name)
        layout.addLayout(name_layout)
        
        # Add button to load T1 NIfTI in Freeview
        self.load_t1_btn = QtWidgets.QPushButton("View T1 in Freeview")
        self.load_t1_btn.clicked.connect(self.load_t1_in_freeview)
        layout.addWidget(self.load_t1_btn)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_t1_in_freeview(self):
        """Load the subject's T1 NIfTI file in Freeview."""
        try:
            subject_id = self.parent.subject_combo.currentText()
            if not subject_id:
                QtWidgets.QMessageBox.warning(self, "Error", "Please select a subject first")
                return
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            t1_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", f"m2m_{subject_id}", "T1.nii.gz")
            if not os.path.exists(t1_path):
                QtWidgets.QMessageBox.warning(self, "Error", f"T1 NIfTI file not found: {t1_path}")
                return
            import subprocess
            subprocess.Popen(["freeview", t1_path])
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Freeview: {str(e)}")
    
    def accept(self):
        """Handle dialog acceptance."""
        try:
            # Get selected subject
            subject_id = self.parent.subject_combo.currentText()
            if not subject_id:
                QtWidgets.QMessageBox.warning(self, "Error", "Please select a subject first")
                return
            
            # Validate ROI name
            roi_name = self.roi_name.text().strip()
            if not roi_name:
                QtWidgets.QMessageBox.warning(self, "Error", "Please enter a ROI name")
                return
                
            # Add .csv extension if not present
            if not roi_name.endswith('.csv'):
                roi_name += '.csv'
            
            # Create ROI file
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                 f"m2m_{subject_id}", "ROIs")
            
            os.makedirs(roi_dir, exist_ok=True)
            
            # Write coordinates to ROI file as three comma-separated columns
            roi_file = os.path.join(roi_dir, roi_name)
            with open(roi_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([self.x_coord.value(), self.y_coord.value(), self.z_coord.value()])
            
            # Update roi_list.txt
            roi_list_file = os.path.join(roi_dir, "roi_list.txt")
            with open(roi_list_file, 'a+') as f:
                f.seek(0)
                existing_rois = [line.strip() for line in f.readlines()]
                if roi_name not in existing_rois:
                    f.write(f"{roi_name}\n")
            
            super().accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to create ROI: {str(e)}")


class EEGNetSelectionDialog(QtWidgets.QDialog):
    """Dialog for selecting EEG net for leadfield creation with electrode viewing capability."""
    
    def __init__(self, eeg_nets, subject_id=None, parent=None):
        super(EEGNetSelectionDialog, self).__init__(parent)
        self.eeg_nets = eeg_nets
        self.subject_id = subject_id
        self.parent = parent
        self.selected_net = None
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Select EEG Net")
        self.setModal(True)
        self.resize(500, 400)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title and description
        title_label = QtWidgets.QLabel("Select EEG Net for Leadfield Creation")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        desc_label = QtWidgets.QLabel("Choose an EEG net configuration for the new leadfield matrix:")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 15px;")
        layout.addWidget(desc_label)
        
        # EEG net list
        self.net_list = QtWidgets.QListWidget()
        self.net_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        
        # Find default (GSN-HydroCel-185.csv) and populate list
        default_item = None
        for net in self.eeg_nets:
            item = QtWidgets.QListWidgetItem(net)
            self.net_list.addItem(item)
            if net == "GSN-HydroCel-185.csv":
                default_item = item
        
        # Select default if available
        if default_item:
            default_item.setSelected(True)
            self.net_list.setCurrentItem(default_item)
            
        layout.addWidget(self.net_list)
        
        # Default info
        if default_item:
            default_info = QtWidgets.QLabel("Default: GSN-HydroCel-185.csv is pre-selected")
            default_info.setStyleSheet("color: #4caf50; font-style: italic; margin: 5px 0;")
            layout.addWidget(default_info)
        
        # Show Electrodes button
        self.show_electrodes_btn = QtWidgets.QPushButton("Show Electrodes")
        self.show_electrodes_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
                margin: 5px 0;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.show_electrodes_btn.clicked.connect(self.show_electrodes)
        layout.addWidget(self.show_electrodes_btn)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Connect double-click to accept
        self.net_list.itemDoubleClicked.connect(self.accept)
    
    def show_electrodes(self):
        """Show available electrodes for the selected EEG net."""
        selected_items = self.net_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select an EEG net first")
            return
        
        selected_net = selected_items[0].text()
        
        try:
            # Get path to EEG net file
            if self.subject_id:
                project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
                eeg_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{self.subject_id}",
                                      f"m2m_{self.subject_id}", "eeg_positions", selected_net)
            else:
                # Fallback to assets directory
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                eeg_path = os.path.join(script_dir, "assets", "ElectrodeCaps_MNI", selected_net)
            
            if not os.path.exists(eeg_path):
                QtWidgets.QMessageBox.warning(self, "File Not Found", 
                                            f"EEG net file not found: {eeg_path}")
                return
            
            # Read electrode information - all files follow same format: Electrode,X,Y,Z,Label
            electrodes = []
            with open(eeg_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 5 and parts[0] == 'Electrode':
                        electrode_label = parts[4].strip()  # 5th column (index 4) is the label
                        if electrode_label and not electrode_label.replace('.', '').replace('-', '').isdigit():  # Skip numeric values
                            electrodes.append(electrode_label)
            
            if not electrodes:
                QtWidgets.QMessageBox.information(self, "No Electrodes", 
                                                "No electrode labels found in the selected EEG net file")
                return
            
            # Create and show electrode display dialog
            electrode_dialog = ElectrodeDisplayDialog(selected_net, electrodes, self)
            electrode_dialog.exec_()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", 
                                         f"Error reading EEG net file: {str(e)}")
    
    def get_selected_net(self):
        """Get the selected EEG net."""
        selected_items = self.net_list.selectedItems()
        if selected_items:
            return selected_items[0].text()
        return None
    
    def accept(self):
        """Handle dialog acceptance."""
        if not self.net_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select an EEG net")
            return
        
        super().accept()


class ElectrodeDisplayDialog(QtWidgets.QDialog):
    """Dialog to display available electrodes for a selected EEG net."""
    
    def __init__(self, eeg_net_name, electrodes, parent=None):
        super(ElectrodeDisplayDialog, self).__init__(parent)
        self.eeg_net_name = eeg_net_name
        self.electrodes = electrodes
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the electrode display dialog UI."""
        self.setWindowTitle(f"Electrodes for {self.eeg_net_name}")
        self.setModal(True)
        self.resize(400, 500)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_label = QtWidgets.QLabel(f"Available Electrodes ({len(self.electrodes)} total)")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # EEG net info
        net_info = QtWidgets.QLabel(f"EEG Net: {self.eeg_net_name}")
        net_info.setStyleSheet("color: #666; margin-bottom: 15px;")
        layout.addWidget(net_info)
        
        # Search box
        search_layout = QtWidgets.QHBoxLayout()
        search_label = QtWidgets.QLabel("Search:")
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Filter electrodes (e.g., E1, E10)")
        self.search_input.textChanged.connect(self.filter_electrodes)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Electrode list
        self.electrode_list = QtWidgets.QListWidget()
        self.electrode_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        
        # Populate electrode list
        for electrode in sorted(self.electrodes, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0):
            self.electrode_list.addItem(electrode)
        
        layout.addWidget(self.electrode_list)
        
        # Selection info
        self.selection_info = QtWidgets.QLabel("Tip: You can select multiple electrodes and copy them")
        self.selection_info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.selection_info)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.copy_selected_btn = QtWidgets.QPushButton("Copy Selected")
        self.copy_selected_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.copy_selected_btn.clicked.connect(self.copy_selected_electrodes)
        button_layout.addWidget(self.copy_selected_btn)
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def filter_electrodes(self):
        """Filter electrode list based on search input."""
        search_text = self.search_input.text().lower()
        
        for i in range(self.electrode_list.count()):
            item = self.electrode_list.item(i)
            item.setHidden(search_text not in item.text().lower())
    
    def copy_selected_electrodes(self):
        """Copy selected electrodes to clipboard."""
        selected_items = self.electrode_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select electrodes to copy")
            return
        
        electrode_list = [item.text() for item in selected_items]
        electrode_text = ", ".join(electrode_list)
        
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(electrode_text)
        
        QtWidgets.QMessageBox.information(self, "Copied", 
                                        f"Copied {len(electrode_list)} electrodes to clipboard:\n{electrode_text}")
    
    def accept(self):
        """Handle dialog acceptance."""
        super().accept() 