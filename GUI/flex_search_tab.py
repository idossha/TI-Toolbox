#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Flex Search Tab
This module provides a GUI interface for the flex-search optimization tool.
"""

import os
import json
import glob
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui

class FlexSearchThread(QtCore.QThread):
    """Thread to run flex-search in background to prevent GUI freezing."""
    
    # Signal to emit output text
    output_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(FlexSearchThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        
    def run(self):
        """Run the flex-search command in a separate thread."""
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
            self.output_signal.emit(f"Error running flex-search: {str(e)}")
    
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

class FlexSearchTab(QtWidgets.QWidget):
    """Tab for flex-search electrode optimization."""
    
    def __init__(self, parent=None):
        super(FlexSearchTab, self).__init__(parent)
        self.parent = parent
        self.optimization_running = False
        self.optimization_process = None
        self.subjects = []
        self.eeg_nets = {}
        self.atlases = {}
        self.setup_ui()
        self.find_available_subjects()
        
    def setup_ui(self):
        """Set up the user interface for the flex-search tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create a scroll area for the form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Title and description
        title_label = QtWidgets.QLabel("Flex Search Electrode Optimization")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        description_label = QtWidgets.QLabel(
            "Find optimal electrode positions for temporal interference stimulation "
            "targeting a specific ROI."
        )
        description_label.setWordWrap(True)
        
        scroll_layout.addWidget(title_label)
        scroll_layout.addWidget(description_label)
        scroll_layout.addWidget(QtWidgets.QLabel(""))  # Spacer
        
        # Form layout for flex-search options
        form_widget = QtWidgets.QWidget()
        form_layout = QtWidgets.QFormLayout(form_widget)
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        
        # Subject selection
        self.subject_label = QtWidgets.QLabel("Subject(s):")
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.setMaximumWidth(200)
        self.refresh_subjects_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_subjects_btn.setMaximumWidth(100)
        self.refresh_subjects_btn.clicked.connect(self.find_available_subjects)
        
        subject_layout = QtWidgets.QHBoxLayout()
        subject_layout.addWidget(self.subject_combo)
        subject_layout.addWidget(self.refresh_subjects_btn)
        subject_layout.addStretch()
        
        form_layout.addRow(self.subject_label, subject_layout)
        
        # Optimization Goal
        self.goal_label = QtWidgets.QLabel("Optimization Goal:")
        self.goal_combo = QtWidgets.QComboBox()
        self.goal_combo.addItem("Maximize field in target ROI", "mean")
        self.goal_combo.addItem("Maximize normal component of field in ROI", "normal")
        self.goal_combo.addItem("Maximize focality", "focality")
        self.goal_combo.setMaximumWidth(350)
        form_layout.addRow(self.goal_label, self.goal_combo)
        
        # Post-processing Method
        self.postproc_label = QtWidgets.QLabel("Post-processing Method:")
        self.postproc_combo = QtWidgets.QComboBox()
        self.postproc_combo.addItem("Maximum TI field (max_TI)", "max_TI")
        self.postproc_combo.addItem("TI field normal to surface (dir_TI_normal)", "dir_TI_normal")
        self.postproc_combo.addItem("TI field tangential to surface (dir_TI_tangential)", "dir_TI_tangential")
        self.postproc_combo.setMaximumWidth(350)
        form_layout.addRow(self.postproc_label, self.postproc_combo)
        
        # EEG Net
        self.eeg_net_label = QtWidgets.QLabel("EEG Net Template:")
        self.eeg_net_combo = QtWidgets.QComboBox()
        self.refresh_eeg_nets_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_eeg_nets_btn.setMaximumWidth(100)
        self.refresh_eeg_nets_btn.clicked.connect(self.find_available_eeg_nets)
        
        eeg_net_layout = QtWidgets.QHBoxLayout()
        eeg_net_layout.addWidget(self.eeg_net_combo)
        eeg_net_layout.addWidget(self.refresh_eeg_nets_btn)
        eeg_net_layout.addStretch()
        
        form_layout.addRow(self.eeg_net_label, eeg_net_layout)
        
        # Electrode Parameters group
        self.electrode_params_group = QtWidgets.QGroupBox("Electrode Parameters")
        electrode_params_layout = QtWidgets.QFormLayout(self.electrode_params_group)
        
        # Electrode radius
        self.radius_label = QtWidgets.QLabel("Electrode Radius (mm):")
        self.radius_input = QtWidgets.QDoubleSpinBox()
        self.radius_input.setRange(1, 30)
        self.radius_input.setValue(10)
        self.radius_input.setDecimals(1)
        electrode_params_layout.addRow(self.radius_label, self.radius_input)
        
        # Electrode current
        self.current_label = QtWidgets.QLabel("Electrode Current (mA):")
        self.current_input = QtWidgets.QDoubleSpinBox()
        self.current_input.setRange(0.1, 5)
        self.current_input.setValue(2)
        self.current_input.setDecimals(1)
        electrode_params_layout.addRow(self.current_label, self.current_input)
        
        form_layout.addRow(self.electrode_params_group)
        
        # ROI Method group
        self.roi_method_group = QtWidgets.QGroupBox("ROI Definition")
        roi_method_layout = QtWidgets.QVBoxLayout(self.roi_method_group)
        
        # ROI Method radio buttons
        self.roi_method_label = QtWidgets.QLabel("ROI Definition Method:")
        self.roi_method_spherical = QtWidgets.QRadioButton("Spherical (coordinates and radius)")
        self.roi_method_cortical = QtWidgets.QRadioButton("Cortical (atlas-based parcellation)")
        self.roi_method_spherical.setChecked(True)
        
        roi_method_radio_layout = QtWidgets.QHBoxLayout()
        roi_method_radio_layout.addWidget(self.roi_method_spherical)
        roi_method_radio_layout.addWidget(self.roi_method_cortical)
        roi_method_radio_layout.addStretch()
        
        roi_method_layout.addWidget(self.roi_method_label)
        roi_method_layout.addLayout(roi_method_radio_layout)
        
        # Create a stacked widget to switch between spherical and cortical ROI inputs
        self.roi_stacked_widget = QtWidgets.QStackedWidget()
        
        # Spherical ROI inputs
        self.spherical_roi_widget = QtWidgets.QWidget()
        spherical_roi_layout = QtWidgets.QFormLayout(self.spherical_roi_widget)
        
        # ROI coordinates
        self.roi_coords_label = QtWidgets.QLabel("ROI Center Coordinates (mm):")
        
        coords_layout = QtWidgets.QHBoxLayout()
        self.roi_x_label = QtWidgets.QLabel("X:")
        self.roi_x_input = QtWidgets.QDoubleSpinBox()
        self.roi_x_input.setRange(-150, 150)
        self.roi_x_input.setValue(0)
        self.roi_x_input.setDecimals(1)
        
        self.roi_y_label = QtWidgets.QLabel("Y:")
        self.roi_y_input = QtWidgets.QDoubleSpinBox()
        self.roi_y_input.setRange(-150, 150)
        self.roi_y_input.setValue(0)
        self.roi_y_input.setDecimals(1)
        
        self.roi_z_label = QtWidgets.QLabel("Z:")
        self.roi_z_input = QtWidgets.QDoubleSpinBox()
        self.roi_z_input.setRange(-150, 150)
        self.roi_z_input.setValue(0)
        self.roi_z_input.setDecimals(1)
        
        coords_layout.addWidget(self.roi_x_label)
        coords_layout.addWidget(self.roi_x_input)
        coords_layout.addWidget(self.roi_y_label)
        coords_layout.addWidget(self.roi_y_input)
        coords_layout.addWidget(self.roi_z_label)
        coords_layout.addWidget(self.roi_z_input)
        
        spherical_roi_layout.addRow(self.roi_coords_label, coords_layout)
        
        # ROI radius
        self.roi_radius_label = QtWidgets.QLabel("ROI Radius (mm):")
        self.roi_radius_input = QtWidgets.QDoubleSpinBox()
        self.roi_radius_input.setRange(1, 50)
        self.roi_radius_input.setValue(10)
        self.roi_radius_input.setDecimals(1)
        
        spherical_roi_layout.addRow(self.roi_radius_label, self.roi_radius_input)
        
        # Add spherical widget to stacked widget
        self.roi_stacked_widget.addWidget(self.spherical_roi_widget)
        
        # Cortical ROI inputs
        self.cortical_roi_widget = QtWidgets.QWidget()
        cortical_roi_layout = QtWidgets.QFormLayout(self.cortical_roi_widget)
        
        # Atlas selection
        self.atlas_label = QtWidgets.QLabel("Atlas:")
        self.atlas_combo = QtWidgets.QComboBox()
        self.refresh_atlases_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_atlases_btn.setMaximumWidth(100)
        self.refresh_atlases_btn.clicked.connect(self.find_available_atlases)
        
        atlas_layout = QtWidgets.QHBoxLayout()
        atlas_layout.addWidget(self.atlas_combo)
        atlas_layout.addWidget(self.refresh_atlases_btn)
        atlas_layout.addStretch()
        
        cortical_roi_layout.addRow(self.atlas_label, atlas_layout)
        
        # Region label value
        self.label_value_label = QtWidgets.QLabel("Region Label Value:")
        self.label_value_input = QtWidgets.QSpinBox()
        self.label_value_input.setRange(1, 10000)
        self.label_value_input.setValue(1)
        
        cortical_roi_layout.addRow(self.label_value_label, self.label_value_input)
        
        # Add cortical widget to stacked widget
        self.roi_stacked_widget.addWidget(self.cortical_roi_widget)
        
        # Connect radio buttons to stacked widget
        self.roi_method_spherical.toggled.connect(self.update_roi_method)
        
        # Add stacked widget to the layout
        roi_method_layout.addWidget(self.roi_stacked_widget)
        
        form_layout.addRow(self.roi_method_group)
        
        # Connect subject change to update EEG nets and atlases
        self.subject_combo.currentIndexChanged.connect(self.on_subject_changed)
        
        # Add form to scroll layout
        scroll_layout.addWidget(form_widget)
        
        # Action buttons
        buttons_layout = QtWidgets.QHBoxLayout()
        
        self.run_btn = QtWidgets.QPushButton("Run Optimization")
        self.run_btn.clicked.connect(self.run_optimization)
        self.run_btn.setMinimumWidth(150)
        
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_optimization)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumWidth(80)
        
        self.clear_btn = QtWidgets.QPushButton("Clear Console")
        self.clear_btn.clicked.connect(self.clear_console)
        self.clear_btn.setMinimumWidth(100)
        
        buttons_layout.addWidget(self.run_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addWidget(self.clear_btn)
        buttons_layout.addStretch()
        
        scroll_layout.addLayout(buttons_layout)
        
        # Add scroll content to scroll area
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Output console
        self.output_group = QtWidgets.QGroupBox("Output")
        output_layout = QtWidgets.QVBoxLayout(self.output_group)
        
        self.output_text = QtWidgets.QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        self.output_text.setStyleSheet("font-family: monospace;")
        
        output_layout.addWidget(self.output_text)
        
        main_layout.addWidget(self.output_group)
        
        # Initialize ROI method display
        self.update_roi_method(True)
    
    def find_available_subjects(self):
        """Scan directories to find available subjects."""
        self.subjects = []
        self.subject_combo.clear()
        
        # Base directory where subjects are located
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        
        # Search for subject directories that have SimNIBS folders
        self.output_text.append("Scanning for subjects...")
        
        try:
            for subject_dir in glob.glob(os.path.join(project_dir, '*')):
                if os.path.isdir(subject_dir):
                    subject_id = os.path.basename(subject_dir)
                    m2m_dir = os.path.join(subject_dir, 'SimNIBS', f'm2m_{subject_id}')
                    
                    if os.path.isdir(m2m_dir):
                        self.subjects.append(subject_id)
                        self.subject_combo.addItem(subject_id)
            
            if self.subjects:
                self.output_text.append(f"Found {len(self.subjects)} subjects.")
                # Trigger EEG net refresh for the first subject
                self.find_available_eeg_nets()
                self.find_available_atlases()
            else:
                self.output_text.append("No subjects found with SimNIBS data.")
        
        except Exception as e:
            self.output_text.append(f"Error scanning for subjects: {str(e)}")
    
    def find_available_eeg_nets(self):
        """Find available EEG net templates for the selected subject."""
        if not self.subjects:
            return
        
        self.eeg_nets = {}
        self.eeg_net_combo.clear()
        
        # Get the selected subject
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            return
        
        # Base directory where subjects are located
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        
        # EEG positions directory
        eeg_dir = os.path.join(project_dir, subject_id, 'SimNIBS', f'm2m_{subject_id}', 'eeg_positions')
        
        try:
            if os.path.isdir(eeg_dir):
                # Find all CSV files in the directory
                for eeg_file in glob.glob(os.path.join(eeg_dir, '*.csv')):
                    net_name = os.path.splitext(os.path.basename(eeg_file))[0]
                    self.eeg_nets[net_name] = eeg_file
                    self.eeg_net_combo.addItem(net_name)
                
                if self.eeg_nets:
                    self.output_text.append(f"Found {len(self.eeg_nets)} EEG net templates for subject {subject_id}.")
                else:
                    self.output_text.append(f"No EEG net templates found for subject {subject_id}.")
                    self.eeg_net_combo.addItem("EGI_256")  # Default option
            else:
                self.output_text.append(f"EEG positions directory not found for subject {subject_id}.")
                self.eeg_net_combo.addItem("EGI_256")  # Default option
        
        except Exception as e:
            self.output_text.append(f"Error scanning for EEG nets: {str(e)}")
            self.eeg_net_combo.addItem("EGI_256")  # Default option
    
    def find_available_atlases(self):
        """Find available atlas files for the selected subject."""
        if not self.subjects:
            return
        
        self.atlases = {}
        self.atlas_combo.clear()
        
        # Get the selected subject
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            return
        
        # Base directory where subjects are located
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        
        # Label directory containing atlas files
        label_dir = os.path.join(project_dir, subject_id, 'SimNIBS', f'm2m_{subject_id}', 'label')
        
        try:
            if os.path.isdir(label_dir):
                # Find all .annot files in the directory
                for atlas_file in glob.glob(os.path.join(label_dir, '*.annot')):
                    atlas_name = os.path.basename(atlas_file)
                    self.atlases[atlas_name] = atlas_file
                    self.atlas_combo.addItem(atlas_name)
                
                if self.atlases:
                    self.output_text.append(f"Found {len(self.atlases)} atlas files for subject {subject_id}.")
                else:
                    self.output_text.append(f"No atlas files found for subject {subject_id}.")
            else:
                self.output_text.append(f"Label directory not found for subject {subject_id}.")
        
        except Exception as e:
            self.output_text.append(f"Error scanning for atlas files: {str(e)}")
    
    def update_roi_method(self, checked):
        """Update the ROI method inputs based on selection."""
        if self.roi_method_spherical.isChecked():
            self.roi_stacked_widget.setCurrentIndex(0)
        else:
            self.roi_stacked_widget.setCurrentIndex(1)
    
    def run_optimization(self):
        """Prepare and run the flex-search optimization."""
        if self.optimization_running:
            self.output_text.append("Optimization already running. Please wait or stop the current run.")
            return
        
        # Get the selected subject
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            self.output_text.append("Error: No subject selected.")
            return
        
        # Get optimization parameters
        goal = self.goal_combo.currentData()
        postproc = self.postproc_combo.currentData()
        eeg_net = self.eeg_net_combo.currentText()
        radius = self.radius_input.value()
        current = self.current_input.value()
        
        # Determine ROI method and parameters
        if self.roi_method_spherical.isChecked():
            roi_method = "spherical"
            roi_x = self.roi_x_input.value()
            roi_y = self.roi_y_input.value()
            roi_z = self.roi_z_input.value()
            roi_radius = self.roi_radius_input.value()
        else:
            roi_method = "cortical"
            atlas_name = self.atlas_combo.currentText()
            label_value = self.label_value_input.value()
        
        # Prepare environment variables
        env = os.environ.copy()
        
        # Ensure PROJECT_DIR is set - this is critical for flex-search to work
        project_dir = env.get('PROJECT_DIR', '/mnt/BIDS_test')
        
        # If the project directory doesn't exist or isn't accessible, try to find a suitable alternative
        if not os.path.isdir(project_dir):
            # Try to determine project directory from the current working directory
            cwd = os.getcwd()
            potential_dirs = [
                os.path.dirname(cwd),  # Parent of current directory
                os.path.join(cwd, ".."),  # Go up one level
                os.path.abspath(os.path.join(cwd, "..")),  # Absolute path one level up
                os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # Parent of the script directory
            ]
            
            for potential_dir in potential_dirs:
                if os.path.isdir(potential_dir) and os.path.isdir(os.path.join(potential_dir, subject_id)):
                    project_dir = potential_dir
                    self.output_text.append(f"Setting PROJECT_DIR to: {project_dir}")
                    break
        
        # Set the environment variables
        env['PROJECT_DIR'] = project_dir
        env['SUBJECT_ID'] = subject_id
        
        if roi_method == "spherical":
            env['ROI_X'] = str(roi_x)
            env['ROI_Y'] = str(roi_y)
            env['ROI_Z'] = str(roi_z)
            env['ROI_RADIUS'] = str(roi_radius)
        else:
            env['ATLAS_PATH'] = atlas_name
            env['ROI_LABEL'] = str(label_value)
        
        # Build the command using the python script directly
        # Find the project root directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        flex_search_dir = os.path.join(script_dir, "flex-search")
        flex_search_py = os.path.join(flex_search_dir, "flex-search.py")
        
        # Verify the flex-search.py exists
        if not os.path.isfile(flex_search_py):
            self.output_text.append(f"Error: flex-search.py not found at {flex_search_py}")
            # Try to locate it in other potential locations
            for search_dir in [script_dir, os.getcwd(), os.path.join(os.getcwd(), "flex-search")]:
                test_path = os.path.join(search_dir, "flex-search.py")
                if os.path.isfile(test_path):
                    flex_search_py = test_path
                    self.output_text.append(f"Found flex-search.py at: {flex_search_py}")
                    break
                
                test_path = os.path.join(search_dir, "flex-search", "flex-search.py")
                if os.path.isfile(test_path):
                    flex_search_py = test_path
                    self.output_text.append(f"Found flex-search.py at: {flex_search_py}")
                    break
            
            if not os.path.isfile(flex_search_py):
                self.output_text.append("Error: Could not find flex-search.py. Optimization cannot continue.")
                return
        
        # Build the command
        cmd = [
            "simnibs_python", flex_search_py,
            "--subject", subject_id,
            "--goal", goal,
            "--postproc", postproc,
            "--eeg-net", eeg_net,
            "--radius", str(radius),
            "--current", str(current),
            "--roi-method", roi_method
        ]
        
        # Start optimization in a separate thread
        self.output_text.append("\n" + "="*50)
        self.output_text.append("Starting flex-search optimization with parameters:")
        self.output_text.append(f"Subject: {subject_id}")
        self.output_text.append(f"Goal: {goal}")
        self.output_text.append(f"Post-processing: {postproc}")
        self.output_text.append(f"EEG Net: {eeg_net}")
        self.output_text.append(f"Electrode radius: {radius} mm")
        self.output_text.append(f"Electrode current: {current} mA")
        self.output_text.append(f"ROI method: {roi_method}")
        
        if roi_method == "spherical":
            self.output_text.append(f"ROI center: [{roi_x}, {roi_y}, {roi_z}] mm")
            self.output_text.append(f"ROI radius: {roi_radius} mm")
        else:
            self.output_text.append(f"Atlas: {atlas_name}")
            self.output_text.append(f"Label value: {label_value}")
        
        self.output_text.append("="*50)
        self.output_text.append(f"Using project directory: {project_dir}")
        self.output_text.append("Running optimization (this may take a while)...")
        self.output_text.append("Command: " + " ".join(cmd))
        
        # Disable UI controls during optimization
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.optimization_running = True
        
        # Create and start the thread
        self.optimization_process = FlexSearchThread(cmd, env)
        self.optimization_process.output_signal.connect(self.update_output)
        self.optimization_process.finished.connect(self.optimization_finished)
        self.optimization_process.start()
    
    def update_output(self, text):
        """Update the output console with text from the optimization process."""
        self.output_text.append(text)
        # Scroll to bottom
        cursor = self.output_text.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.output_text.setTextCursor(cursor)
    
    def optimization_finished(self):
        """Handle the completion of the optimization process."""
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.output_text.append("\nOptimization process completed.")
    
    def clear_console(self):
        """Clear the output console."""
        self.output_text.clear()
    
    def stop_optimization(self):
        """Stop the running optimization process."""
        if not self.optimization_running:
            return
        
        self.output_text.append("Stopping optimization...")
        if self.optimization_process:
            if self.optimization_process.terminate_process():
                self.output_text.append("Optimization stopped.")
            else:
                self.output_text.append("Failed to stop optimization.")
        
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    
    def on_subject_changed(self, index):
        """Handle subject selection change."""
        if index >= 0:
            self.find_available_eeg_nets()
            self.find_available_atlases() 