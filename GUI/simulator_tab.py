#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Simulator Tab
This module provides a GUI interface for the simulator functionality.
"""

import os
import json
import re
import subprocess
import glob
from PyQt5 import QtWidgets, QtCore, QtGui

class SimulationThread(QtCore.QThread):
    """Thread to run simulation in background to prevent GUI freezing."""
    
    # Signal to emit output text
    output_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(SimulationThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        
    def run(self):
        """Run the simulation command in a separate thread."""
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
            self.output_signal.emit(f"Error running simulation: {str(e)}")
    
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

class SimulatorTab(QtWidgets.QWidget):
    """Tab for simulator functionality."""
    
    def __init__(self, parent=None):
        super(SimulatorTab, self).__init__(parent)
        self.parent = parent
        self.simulation_running = False
        self.simulation_process = None
        self.setup_ui()
        
        # Initialize with available subjects and montages
        QtCore.QTimer.singleShot(500, self.list_subjects)
        QtCore.QTimer.singleShot(700, self.update_montage_list)
        
    def setup_ui(self):
        """Set up the user interface for the simulator tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create a scroll area for the form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Form layout for simulator options
        form_layout = QtWidgets.QFormLayout()
        
        # Create a horizontal layout for subject and montage selections
        subjects_montages_layout = QtWidgets.QHBoxLayout()
        
        # Left side - Subject selection
        subject_container = QtWidgets.QGroupBox("Subject(s)")
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        
        # List widget for subject selection
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.subject_list.setMinimumHeight(100)
        subject_layout.addWidget(self.subject_list)
        
        # Subject control buttons
        subject_button_layout = QtWidgets.QHBoxLayout()
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        self.select_all_subjects_btn = QtWidgets.QPushButton("Select All")
        self.select_all_subjects_btn.clicked.connect(self.select_all_subjects)
        self.clear_subject_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_subject_selection_btn.clicked.connect(self.clear_subject_selection)
        
        subject_button_layout.addWidget(self.list_subjects_btn)
        subject_button_layout.addWidget(self.select_all_subjects_btn)
        subject_button_layout.addWidget(self.clear_subject_selection_btn)
        subject_layout.addLayout(subject_button_layout)
        
        # Right side - Montage selection
        montage_container = QtWidgets.QGroupBox("Montage(s)")
        montage_layout = QtWidgets.QVBoxLayout(montage_container)
        
        # List widget for montage selection
        self.montage_list = QtWidgets.QListWidget()
        self.montage_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.montage_list.setMinimumHeight(100)
        montage_layout.addWidget(self.montage_list)
        
        # Montage control buttons
        montage_button_layout = QtWidgets.QHBoxLayout()
        self.list_montages_btn = QtWidgets.QPushButton("Refresh List")
        self.list_montages_btn.clicked.connect(self.update_montage_list)
        self.select_all_montages_btn = QtWidgets.QPushButton("Select All")
        self.select_all_montages_btn.clicked.connect(self.select_all_montages)
        self.clear_montage_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_montage_selection_btn.clicked.connect(self.clear_montage_selection)
        
        montage_button_layout.addWidget(self.list_montages_btn)
        montage_button_layout.addWidget(self.select_all_montages_btn)
        montage_button_layout.addWidget(self.clear_montage_selection_btn)
        montage_layout.addLayout(montage_button_layout)
        
        # Add subject and montage containers to the horizontal layout
        subjects_montages_layout.addWidget(subject_container)
        subjects_montages_layout.addWidget(montage_container)
        
        # Add the combined layout to the form
        form_layout.addRow(subjects_montages_layout)
        
        # Simulation type (Isotropic/Anisotropic)
        self.sim_type_label = QtWidgets.QLabel("Simulation Type:")
        self.sim_type_combo = QtWidgets.QComboBox()
        self.sim_type_combo.addItem("Isotropic", "scalar")
        self.sim_type_combo.addItem("Anisotropic (vn)", "vn")
        self.sim_type_combo.addItem("Anisotropic (dir)", "dir")
        self.sim_type_combo.addItem("Anisotropic (mc)", "mc")
        form_layout.addRow(self.sim_type_label, self.sim_type_combo)
        
        # Simulation mode (Unipolar/Multipolar)
        self.sim_mode_label = QtWidgets.QLabel("Simulation Mode:")
        self.sim_mode_layout = QtWidgets.QHBoxLayout()
        self.sim_mode_unipolar = QtWidgets.QRadioButton("Unipolar")
        self.sim_mode_multipolar = QtWidgets.QRadioButton("Multipolar")
        self.sim_mode_unipolar.setChecked(True)
        self.sim_mode_layout.addWidget(self.sim_mode_unipolar)
        self.sim_mode_layout.addWidget(self.sim_mode_multipolar)
        # Connect mode radio buttons to update montage list
        self.sim_mode_unipolar.toggled.connect(self.update_montage_list)
        self.sim_mode_multipolar.toggled.connect(self.update_montage_list)
        form_layout.addRow(self.sim_mode_label, self.sim_mode_layout)
        
        # Simulation Parameters group
        self.sim_params_group = QtWidgets.QGroupBox("Simulation Parameters")
        sim_params_layout = QtWidgets.QVBoxLayout(self.sim_params_group)
        
        # Current value
        current_layout = QtWidgets.QHBoxLayout()
        self.current_label = QtWidgets.QLabel("Current Value (mA):")
        self.current_input = QtWidgets.QLineEdit()
        self.current_input.setPlaceholderText("1.0")
        self.current_input.setText("1.0")  # Set default to 1.0 mA
        current_layout.addWidget(self.current_label)
        current_layout.addWidget(self.current_input)
        sim_params_layout.addLayout(current_layout)
        
        # Electrode geometry
        electrode_geometry_layout = QtWidgets.QFormLayout()
        
        # Electrode shape
        self.electrode_shape_label = QtWidgets.QLabel("Electrode Shape:")
        self.electrode_shape_combo = QtWidgets.QComboBox()
        self.electrode_shape_combo.addItem("Rectangle", "rect")
        self.electrode_shape_combo.addItem("Ellipse", "ellipse")
        self.electrode_shape_combo.setCurrentIndex(1)  # Set default to Ellipse
        electrode_geometry_layout.addRow(self.electrode_shape_label, self.electrode_shape_combo)
        
        # Electrode dimensions
        self.dimensions_label = QtWidgets.QLabel("Dimensions (mm, x,y):")
        self.dimensions_input = QtWidgets.QLineEdit()
        self.dimensions_input.setPlaceholderText("8,8")
        self.dimensions_input.setText("8,8")  # Set default to 8,8
        electrode_geometry_layout.addRow(self.dimensions_label, self.dimensions_input)
        
        # Electrode thickness
        self.thickness_label = QtWidgets.QLabel("Thickness (mm):")
        self.thickness_input = QtWidgets.QLineEdit()
        self.thickness_input.setPlaceholderText("8")
        self.thickness_input.setText("8")  # Set default to 8mm
        electrode_geometry_layout.addRow(self.thickness_label, self.thickness_input)
        
        sim_params_layout.addLayout(electrode_geometry_layout)
        form_layout.addRow(self.sim_params_group)
        
        # Add New Montage group (collapsible)
        self.montage_group = QtWidgets.QGroupBox("Add New Montage")
        self.montage_group.setCheckable(True)
        self.montage_group.setChecked(False)  # Start collapsed
        self.montage_group.toggled.connect(self.toggle_montage_group)
        montage_group_layout = QtWidgets.QVBoxLayout(self.montage_group)
        
        # Content container for montage inputs
        self.montage_content = QtWidgets.QWidget()
        montage_content_layout = QtWidgets.QVBoxLayout(self.montage_content)
        self.montage_content.setVisible(False)  # Start hidden
        
        # Add instructions for using the collapsed box
        instructions = QtWidgets.QLabel("Check this box to add a new montage")
        instructions.setStyleSheet("color: #666;")
        montage_group_layout.addWidget(instructions)
        
        # Montage name
        montage_name_layout = QtWidgets.QHBoxLayout()
        self.montage_name_label = QtWidgets.QLabel("Montage Name:")
        self.montage_name_input = QtWidgets.QLineEdit()
        montage_name_layout.addWidget(self.montage_name_label)
        montage_name_layout.addWidget(self.montage_name_input)
        montage_content_layout.addLayout(montage_name_layout)
        
        # Create a stacked widget to switch between unipolar and multipolar electrode inputs
        self.electrode_stacked_widget = QtWidgets.QStackedWidget()
        
        # Unipolar electrode pairs (two pairs)
        self.uni_electrode_widget = QtWidgets.QWidget()
        uni_electrode_layout = QtWidgets.QVBoxLayout(self.uni_electrode_widget)
        
        # Pair 1
        uni_pair1_layout = QtWidgets.QHBoxLayout()
        self.uni_pair1_label = QtWidgets.QLabel("Pair 1:")
        self.uni_pair1_e1 = QtWidgets.QLineEdit()
        self.uni_pair1_e1.setPlaceholderText("E10")
        self.uni_pair1_e2 = QtWidgets.QLineEdit()
        self.uni_pair1_e2.setPlaceholderText("E11")
        uni_pair1_layout.addWidget(self.uni_pair1_label)
        uni_pair1_layout.addWidget(self.uni_pair1_e1)
        uni_pair1_layout.addWidget(QtWidgets.QLabel("→"))
        uni_pair1_layout.addWidget(self.uni_pair1_e2)
        uni_electrode_layout.addLayout(uni_pair1_layout)
        
        # Pair 2
        uni_pair2_layout = QtWidgets.QHBoxLayout()
        self.uni_pair2_label = QtWidgets.QLabel("Pair 2:")
        self.uni_pair2_e1 = QtWidgets.QLineEdit()
        self.uni_pair2_e1.setPlaceholderText("E12")
        self.uni_pair2_e2 = QtWidgets.QLineEdit()
        self.uni_pair2_e2.setPlaceholderText("E13")
        uni_pair2_layout.addWidget(self.uni_pair2_label)
        uni_pair2_layout.addWidget(self.uni_pair2_e1)
        uni_pair2_layout.addWidget(QtWidgets.QLabel("→"))
        uni_pair2_layout.addWidget(self.uni_pair2_e2)
        uni_electrode_layout.addLayout(uni_pair2_layout)
        
        # Multipolar electrode pairs (four pairs)
        self.multi_electrode_widget = QtWidgets.QWidget()
        multi_electrode_layout = QtWidgets.QVBoxLayout(self.multi_electrode_widget)
        
        # Pair 1-4 for multipolar
        for i in range(1, 5):
            pair_layout = QtWidgets.QHBoxLayout()
            pair_label = QtWidgets.QLabel(f"Pair {i}:")
            
            # Create electrode inputs and save references
            e1 = QtWidgets.QLineEdit()
            e1.setPlaceholderText(f"E{10+2*(i-1)}")
            e2 = QtWidgets.QLineEdit()
            e2.setPlaceholderText(f"E{11+2*(i-1)}")
            
            # Store references for later access
            setattr(self, f"multi_pair{i}_e1", e1)
            setattr(self, f"multi_pair{i}_e2", e2)
            
            pair_layout.addWidget(pair_label)
            pair_layout.addWidget(e1)
            pair_layout.addWidget(QtWidgets.QLabel("→"))
            pair_layout.addWidget(e2)
            multi_electrode_layout.addLayout(pair_layout)
        
        # Add the widgets to the stacked widget
        self.electrode_stacked_widget.addWidget(self.uni_electrode_widget)
        self.electrode_stacked_widget.addWidget(self.multi_electrode_widget)
        
        # Add the stacked widget to the montage content
        montage_content_layout.addWidget(self.electrode_stacked_widget)
        
        # Connect radio buttons to change the stacked widget
        self.sim_mode_unipolar.toggled.connect(self.update_electrode_inputs)
        
        # Add montage button
        self.add_montage_btn = QtWidgets.QPushButton("Add Montage")
        self.add_montage_btn.clicked.connect(self.add_montage)
        montage_content_layout.addWidget(self.add_montage_btn)
        
        # Add the content container to the group layout
        montage_group_layout.addWidget(self.montage_content)
        
        form_layout.addRow(self.montage_group)
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Run Simulation")
        self.run_btn.clicked.connect(self.run_simulation)
        self.run_btn.setMinimumWidth(160)
        self.run_btn.setMinimumHeight(40)
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px; padding: 8px;")
        
        # Stop button
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_simulation)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setStyleSheet("background-color: #cccccc; color: #888888; font-weight: bold; font-size: 14px; padding: 8px;")
        
        # Clear button
        self.clear_btn = QtWidgets.QPushButton("Clear Console")
        self.clear_btn.clicked.connect(self.clear_console)
        self.clear_btn.setMinimumWidth(120)
        self.clear_btn.setMinimumHeight(40)
        self.clear_btn.setStyleSheet("background-color: #e0e0e0; color: #333; font-weight: bold; font-size: 14px; padding: 8px;")
        
        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.run_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        
        # Add form layout to scroll layout
        scroll_layout.addLayout(form_layout)
        scroll_layout.addLayout(button_layout)
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Output console
        output_label = QtWidgets.QLabel("Console Output")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        main_layout.addWidget(output_label)
        self.output_console = QtWidgets.QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setMinimumHeight(200)
        self.output_console.setStyleSheet("""
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
        self.output_console.setAcceptRichText(True)
        main_layout.addWidget(self.output_console)
        
    def list_subjects(self):
        """List available subjects and display them."""
        self.subject_list.clear()
        # ... existing code to find subjects ...
        self.output_console.clear()
        subjects = []
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        for subject_dir in glob.glob(os.path.join(project_dir, '*')):
            if os.path.isdir(subject_dir):
                subject_id = os.path.basename(subject_dir)
                subjects.append(subject_id)
                self.subject_list.addItem(subject_id)
        # Console output: subjects found
        self.output_console.append("=== Subjects Found ===")
        if not subjects:
            self.output_console.append("No subjects found.")
        for subject_id in subjects:
            m2m_dir = os.path.join(project_dir, subject_id, 'SimNIBS', f'm2m_{subject_id}')
            headmodel_found = os.path.isdir(m2m_dir)
            status = '[✓] Headmodel found' if headmodel_found else '[✗] No headmodel'
            self.output_console.append(f"{subject_id}: {status}")
        self.output_console.append("")
    
    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()
    
    def clear_subject_selection(self):
        """Clear the selection in the subject list."""
        self.subject_list.clearSelection()
    
    def select_all_montages(self):
        """Select all montages in the montage list."""
        self.montage_list.selectAll()
    
    def clear_montage_selection(self):
        """Clear the selection in the montage list."""
        self.montage_list.clearSelection()
    
    def update_montage_list(self, checked=None):
        """Update the montage list based on the selected simulation mode."""
        # Clear current list
        self.montage_list.clear()
        
        try:
            # Use environment variable for project directory like simulator.sh does
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
            project_dir = f"/mnt/{project_dir_name}"
            utils_dir = os.path.join(project_dir, "utils")
            montage_file = os.path.join(utils_dir, "montage_list.json")
            
            self.output_console.append(f"Looking for montages in: {montage_file}")
            
            if os.path.exists(montage_file):
                with open(montage_file, 'r') as f:
                    montage_data = json.load(f)
                
                # Create expected structure if needed
                if not isinstance(montage_data, dict):
                    self.output_console.append(f"Warning: Unexpected data type in montage file: {type(montage_data).__name__}. Creating new structure.")
                    montage_data = {"uni_polar_montages": {}, "multi_polar_montages": {}}
                
                # Ensure the required keys exist
                if "uni_polar_montages" not in montage_data:
                    montage_data["uni_polar_montages"] = {}
                if "multi_polar_montages" not in montage_data:
                    montage_data["multi_polar_montages"] = {}
                
                # Get montages for the selected mode
                is_unipolar = self.sim_mode_unipolar.isChecked()
                montage_type = "uni_polar_montages" if is_unipolar else "multi_polar_montages"
                mode_text = "Unipolar" if is_unipolar else "Multipolar"
                
                montages = montage_data[montage_type]
                
                if isinstance(montages, dict) and montages:
                    # Add montages to the list widget
                    for montage_name in montages.keys():
                        self.montage_list.addItem(montage_name)
                    
                    self.output_console.append(f"Found {len(montages)} {mode_text.lower()} montages.")
                else:
                    self.output_console.append(f"No {mode_text.lower()} montages found.")
            else:
                self.output_console.append(f"Montage file not found: {montage_file}")
                
        except Exception as e:
            self.output_console.append(f"Error updating montage list: {str(e)}")
            
        # Update the electrode inputs view
        if checked is not None:
            if checked:  # Unipolar selected
                self.electrode_stacked_widget.setCurrentIndex(0)
            else:  # Multipolar selected
                self.electrode_stacked_widget.setCurrentIndex(1)
                
    def list_montages(self):
        """List available montages from montage_list.json."""
        try:
            # Use environment variable for project directory like simulator.sh does
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
            project_dir = f"/mnt/{project_dir_name}"
            utils_dir = os.path.join(project_dir, "utils")
            montage_file = os.path.join(utils_dir, "montage_list.json")
            
            self.output_console.append(f"Looking for montages in: {montage_file}")
            
            if os.path.exists(montage_file):
                with open(montage_file, 'r') as f:
                    montage_data = json.load(f)
                
                # Create expected structure if needed
                if not isinstance(montage_data, dict):
                    self.output_console.append(f"Warning: Unexpected data type in montage file: {type(montage_data).__name__}. Creating new structure.")
                    montage_data = {"uni_polar_montages": {}, "multi_polar_montages": {}}
                
                # Ensure the required keys exist
                if "uni_polar_montages" not in montage_data:
                    montage_data["uni_polar_montages"] = {}
                if "multi_polar_montages" not in montage_data:
                    montage_data["multi_polar_montages"] = {}
                
                # Get montages for the selected mode
                is_unipolar = self.sim_mode_unipolar.isChecked()
                montage_type = "uni_polar_montages" if is_unipolar else "multi_polar_montages"
                mode_text = "Unipolar" if is_unipolar else "Multipolar"
                
                self.output_console.append('<div style="background-color: #2a2a2a; border: 1px solid #444; border-radius: 5px; padding: 10px; margin: 10px 0;">')
                self.output_console.append(f'<span style="color: #55ffff; font-weight: bold;">📋 Available {mode_text} Montages:</span>')
                
                montages = montage_data[montage_type]
                
                if isinstance(montages, dict) and montages:
                    # Display montages with formatted electrode pairs
                    self.output_console.append('<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">')
                    self.output_console.append('<tr style="background-color: #333; color: white;">')
                    self.output_console.append('<th style="padding: 5px; text-align: left; border-bottom: 1px solid #555;">Name</th>')
                    self.output_console.append('<th style="padding: 5px; text-align: left; border-bottom: 1px solid #555;">Electrode Pairs</th>')
                    self.output_console.append('</tr>')
                    
                    found_montages = False
                    row_num = 0
                    
                    for name, details in montages.items():
                        row_style = 'background-color: #2d2d2d;' if row_num % 2 == 0 else 'background-color: #333;'
                        row_num += 1
                        found_montages = True
                        
                        if isinstance(details, list) and len(details) >= 1:
                            pairs_str = self._format_electrode_pairs(details)
                            self.output_console.append(f'<tr style="{row_style}">')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{name}</td>')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{pairs_str}</td>')
                            self.output_console.append('</tr>')
                        elif isinstance(details, dict) and 'pair' in details:
                            pair = details.get('pair', '')
                            current = details.get('current', '')
                            self.output_console.append(f'<tr style="{row_style}">')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{name}</td>')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{pair}, {current}mA</td>')
                            self.output_console.append('</tr>')
                    
                    self.output_console.append('</table>')
                    
                    if not found_montages:
                        self.output_console.append(f'<div style="color: #ffff55; padding: 10px;">No {mode_text.lower()} montages found.</div>')
                else:
                    self.output_console.append(f'<div style="color: #ffff55; padding: 10px;">No {mode_text.lower()} montages found.</div>')
                
                self.output_console.append('</div>')
            else:
                self.output_console.append(f"Montage file not found at {montage_file}")
                self.output_console.append("Create a new montage using the form below.")
        except Exception as e:
            self.output_console.append(f"Error listing montages: {str(e)}")
    
    def _format_electrode_pairs(self, pairs):
        """Format electrode pairs for display in a clean way."""
        if not pairs:
            return "No electrode pairs"
        
        formatted_pairs = []
        for pair in pairs:
            if isinstance(pair, list) and len(pair) >= 2:
                formatted_pair = f'<span style="color: #55aaff;">{pair[0]}</span><span style="color: #aaaaaa;">→</span><span style="color: #ff5555;">{pair[1]}</span>'
                formatted_pairs.append(formatted_pair)
        
        return ", ".join(formatted_pairs)
    
    def browse_montage(self):
        """Open file browser to select a montage file."""
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Montage File", "", "JSON Files (*.json);;All Files (*)"
        )
        
        if file_name:
            self.montage_list.addItem(file_name)
            self.output_console.append(f"Selected montage file: {file_name}")
    
    def add_montage(self):
        """Add a new montage to the montage file."""
        try:
            montage_name = self.montage_name_input.text().strip()
            current_value = self.current_input.text().strip()
            
            if not montage_name:
                self.output_console.append("Error: Montage name is required")
                return
                
            if not current_value or not self.validate_current(current_value):
                self.output_console.append("Error: Invalid current value (should be a number)")
                return
            
            # Determine which mode we're in and collect electrode pairs
            is_unipolar = self.sim_mode_unipolar.isChecked()
            electrode_pairs = []
            
            if is_unipolar:
                # Collect unipolar electrode pairs
                pair1_e1 = self.uni_pair1_e1.text().strip()
                pair1_e2 = self.uni_pair1_e2.text().strip()
                pair2_e1 = self.uni_pair2_e1.text().strip()
                pair2_e2 = self.uni_pair2_e2.text().strip()
                
                # Validate electrode inputs
                if not pair1_e1 or not pair1_e2 or not self.validate_electrode(pair1_e1) or not self.validate_electrode(pair1_e2):
                    self.output_console.append("Error: Invalid electrode format for Pair 1 (should be E1, E2)")
                    return
                
                if not pair2_e1 or not pair2_e2 or not self.validate_electrode(pair2_e1) or not self.validate_electrode(pair2_e2):
                    self.output_console.append("Error: Invalid electrode format for Pair 2 (should be E1, E2)")
                    return
                
                # Add the pairs to the list
                electrode_pairs.append([pair1_e1, pair1_e2])
                electrode_pairs.append([pair2_e1, pair2_e2])
            else:
                # Collect multipolar electrode pairs (collect all 4 pairs)
                for i in range(1, 5):
                    e1 = getattr(self, f"multi_pair{i}_e1").text().strip()
                    e2 = getattr(self, f"multi_pair{i}_e2").text().strip()
                    
                    # Validate electrode inputs
                    if not e1 or not e2 or not self.validate_electrode(e1) or not self.validate_electrode(e2):
                        self.output_console.append(f"Error: Invalid electrode format for Pair {i} (should be E1, E2)")
                        return
                    
                    # Add the pair to the list
                    electrode_pairs.append([e1, e2])
            
            # Use environment variable for project directory like simulator.sh does
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
            project_dir = f"/mnt/{project_dir_name}"
            utils_dir = os.path.join(project_dir, "utils")
            montage_file = os.path.join(utils_dir, "montage_list.json")
            
            # Create utils directory if it doesn't exist
            if not os.path.exists(utils_dir):
                os.makedirs(utils_dir)
                self.output_console.append(f"Created utils directory at {utils_dir}")
            
            # Load existing montage data or create new if file doesn't exist
            montage_data = {"uni_polar_montages": {}, "multi_polar_montages": {}}
            if os.path.exists(montage_file):
                with open(montage_file, 'r') as f:
                    try:
                        loaded_data = json.load(f)
                        
                        # Handle different data structures - make sure we have a dictionary
                        if isinstance(loaded_data, list):
                            self.output_console.append("Warning: Montage file contains a list instead of a dictionary. Converting format.")
                            # Create a new dictionary from the list
                            for item in loaded_data:
                                if isinstance(item, dict) and "name" in item:
                                    # Try to categorize based on available info
                                    m_type = "uni_polar_montages"  # Default
                                    if "type" in item and item["type"].lower() == "multipolar":
                                        m_type = "multi_polar_montages"
                                    
                                    montage_data[m_type][item["name"]] = {
                                        "pair": item.get("pair", ""),
                                        "current": item.get("current", "")
                                    }
                        elif isinstance(loaded_data, dict):
                            montage_data = loaded_data
                            # Ensure the required keys exist
                            if "uni_polar_montages" not in montage_data:
                                montage_data["uni_polar_montages"] = {}
                            if "multi_polar_montages" not in montage_data:
                                montage_data["multi_polar_montages"] = {}
                        
                    except json.JSONDecodeError:
                        self.output_console.append(f"Warning: Couldn't parse {montage_file}. Creating new file.")
            
            # Add the new montage to the appropriate section
            montage_type = "uni_polar_montages" if is_unipolar else "multi_polar_montages"
            
            # Store in the format used by the underlying code
            montage_data[montage_type][montage_name] = electrode_pairs
            
            # Save the updated montage data
            with open(montage_file, 'w') as f:
                json.dump(montage_data, f, indent=2)
            
            # Format pairs for display
            pairs_text = ", ".join([f"{pair[0]}→{pair[1]}" for pair in electrode_pairs])
            
            self.output_console.append(f"Added {montage_type.split('_')[0]} montage '{montage_name}' with pairs: {pairs_text}")
            self.output_console.append(f"Montage saved to: {montage_file}")
            
            # Set file permissions to match simulator.sh behavior
            os.chmod(montage_file, 0o777)
            
            # Clear input fields
            self.montage_name_input.clear()
            
            if is_unipolar:
                self.uni_pair1_e1.clear()
                self.uni_pair1_e2.clear()
                self.uni_pair2_e1.clear()
                self.uni_pair2_e2.clear()
            else:
                for i in range(1, 5):
                    getattr(self, f"multi_pair{i}_e1").clear()
                    getattr(self, f"multi_pair{i}_e2").clear()
            
            # Update the montage list with the newly added montage
            self.montage_list.addItem(montage_name)
            
            # Refresh the list of montages
            self.list_montages()
            
        except Exception as e:
            self.output_console.append(f"Error adding montage: {str(e)}")
    
    def validate_electrode(self, electrode):
        """Validate single electrode format (e.g., E10)."""
        import re
        return bool(re.match(r'^E[0-9]+$', electrode))
    
    def validate_current(self, current):
        """Validate current value is a number."""
        try:
            float(current)
            return True
        except ValueError:
            return False
    
    def run_simulation(self):
        """Run the simulation with the selected parameters."""
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, True, stop_btn=self.stop_btn)
        if self.simulation_running:
            self.output_console.append("A simulation is already running.")
            return
        
        try:
            # Check if subjects and montages are selected
            selected_subjects = self.subject_list.selectedItems()
            if not selected_subjects:
                self.output_console.append("Error: No subjects selected.")
                return
            
            selected_montages = self.montage_list.selectedItems()
            if not selected_montages:
                self.output_console.append("Error: No montages selected.")
                return
            
            # Get simulation parameters from UI
            conductivity = self.sim_type_combo.currentData()
            sim_mode = "U" if self.sim_mode_unipolar.isChecked() else "M"
            
            # Get electrode parameters
            current = self.current_input.text().strip()
            if not self.validate_current(current):
                self.output_console.append("Error: Invalid current value. Please enter a valid number.")
                return
            
            shape = self.electrode_shape_combo.currentData()
            dimensions = self.dimensions_input.text().strip()
            thickness = self.thickness_input.text().strip()
            
            # Validation for dimensions
            dimension_match = re.match(r'^\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*$', dimensions)
            if not dimension_match:
                self.output_console.append("Error: Dimensions must be in format 'x,y' (e.g., '8,8').")
                return
            
            # Validation for thickness
            try:
                thickness_value = float(thickness)
                if thickness_value <= 0:
                    raise ValueError("Thickness must be positive")
            except ValueError:
                self.output_console.append("Error: Thickness must be a positive number.")
                return
            
            # Get path to simulator.sh in the root directory
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            simulator_path = os.path.join(script_dir, "CLI", "simulator.sh")
            
            # Create lists of subjects and montages
            subjects = [item.text() for item in selected_subjects]
            montages = [item.text() for item in selected_montages]
            
            # Format for display
            subjects_str = ", ".join(subjects)
            montages_str = ", ".join(montages)
            
            # Display simulation overview
            self.output_console.append("\nSimulation Overview:")
            self.output_console.append(f"- Subjects: {subjects_str}")
            self.output_console.append(f"- Montages: {montages_str}")
            self.output_console.append(f"- Simulation Type: {self.sim_type_combo.currentText()}")
            self.output_console.append(f"- Simulation Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}")
            self.output_console.append(f"- Current: {current} mA")
            self.output_console.append(f"- Electrode Shape: {self.electrode_shape_combo.currentText()}")
            self.output_console.append(f"- Dimensions: {dimensions} mm")
            self.output_console.append(f"- Thickness: {thickness} mm")
            
            # Calculate total number of simulations
            total_simulations = len(subjects)
            
            reply = QtWidgets.QMessageBox.question(
                self, 
                "Confirm Simulation",
                f"Run {total_simulations} simulation(s) with the following settings?\n\n"
                f"Subjects ({len(subjects)}): {subjects_str}\n"
                f"Montages ({len(montages)}): {montages_str}\n"
                f"Simulation Type: {self.sim_type_combo.currentText()}\n"
                f"Simulation Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}\n"
                f"Current: {current} mA\n"
                f"Electrode Shape: {self.electrode_shape_combo.currentText()}\n"
                f"Dimensions: {dimensions} mm\n"
                f"Thickness: {thickness} mm\n",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # Clear console
                self.clear_console()
                
                # Update UI state
                self.simulation_running = True
                self.run_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; font-size: 14px; padding: 8px;")
                
                # Process each subject separately
                # Process all subjects as a batch to match simulator.sh behavior
                selected_subjects_str = ",".join(subjects)
                
                # IMPORTANT: For montages, we need to pass them as space-separated values
                # to ensure simulator.sh treats them as separate montages
                selected_montages_str = " ".join(montages)
                
                # Basic command
                cmd = ["bash", simulator_path, "--run-direct"]
                
                # Set environment variables for simulator.sh in direct mode
                env = os.environ.copy()
                env["SUBJECTS"] = selected_subjects_str
                env["CONDUCTIVITY"] = conductivity
                env["SIM_MODE"] = sim_mode
                env["SELECTED_MONTAGES"] = selected_montages_str
                env["CURRENT"] = current
                env["ELECTRODE_SHAPE"] = shape
                env["DIMENSIONS"] = dimensions
                env["THICKNESS"] = thickness
                env["DIRECT_MODE"] = "true"
                env["NON_INTERACTIVE"] = "true"
                
                # Add project directory name if available
                project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
                env["PROJECT_DIR_NAME"] = project_dir_name
                env["PROJECT_DIR"] = f"/mnt/{project_dir_name}"
                
                # Start simulation
                self.output_console.append(f"\nStarting simulation batch with {len(subjects)} subject(s) and {len(montages)} montage(s)...")
                self.output_console.append(f"Command: {' '.join(cmd)}")
                
                # Start simulation thread
                self.simulation_process = SimulationThread(cmd, env)
                self.simulation_process.output_signal.connect(self.update_output)
                self.simulation_process.finished.connect(self.simulation_finished)
                self.simulation_process.start()
            
        except Exception as e:
            self.output_console.append(f"Error starting simulation: {str(e)}")
            self.simulation_running = False
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.stop_btn.setStyleSheet("background-color: #cccccc; color: #888888; font-weight: bold; font-size: 14px; padding: 8px;")
    
    def update_output(self, text):
        """Update the output console with text from the simulation thread."""
        if not text.strip():
            return
            
        # Format the output based on content type
        if "Error:" in text or "CRITICAL:" in text or "Failed" in text:
            formatted_text = f'<span style="color: #ff5555;"><b>❌ {text}</b></span>'
        elif "Warning:" in text or "YELLOW" in text:
            formatted_text = f'<span style="color: #ffff55;">⚠️ {text}</span>'
        elif "DEBUG:" in text:
            formatted_text = f'<span style="color: #7f7f7f;">🔍 {text}</span>'
        elif "Executing:" in text or "Running" in text or "Command" in text:
            formatted_text = f'<span style="color: #55aaff;">📋 {text}</span>'
        elif "completed successfully" in text or "completed." in text or "Successfully" in text or "completed:" in text:
            formatted_text = f'<span style="color: #55ff55;"><b>✅ {text}</b></span>'
        elif "Processing" in text or "Starting" in text:
            formatted_text = f'<span style="color: #55ffff;">🔄 {text}</span>'
        elif text.strip().startswith("-"):
            # Indented list items
            formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
        else:
            formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        
        # Add a timestamp
        timestamp = QtCore.QTime.currentTime().toString("hh:mm:ss")
        log_entry = f'<span style="color: #888888;">[{timestamp}]</span> {formatted_text}'
        
        # Append to the console with HTML formatting
        self.output_console.append(log_entry)
        
        # Ensure the latest output is visible
        self.output_console.ensureCursorVisible()
        
    def simulation_finished(self):
        """Handle simulation completion."""
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
        self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">✅ Simulation process completed ✅</span></div>')
        self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
        self.simulation_running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run Simulation")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background-color: #cccccc; color: #888888; font-weight: bold; font-size: 14px; padding: 8px;")
    
    def update_electrode_inputs(self, checked):
        """Update the electrode input form based on the selected simulation mode."""
        if checked:  # Unipolar selected
            self.electrode_stacked_widget.setCurrentIndex(0)
        else:  # Multipolar selected
            self.electrode_stacked_widget.setCurrentIndex(1)
    
    def toggle_montage_group(self, checked):
        """Show or hide the montage inputs based on the checkbox state."""
        self.montage_content.setVisible(checked)
    
    def clear_console(self):
        """Clear the output console."""
        self.output_console.clear()
    
    def stop_simulation(self):
        """Stop the running simulation."""
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
        if hasattr(self, 'simulation_process') and self.simulation_process:
            # Show stopping message
            self.output_console.append("Stopping simulation...")
            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">⚠️ Simulation terminated by user ⚠️</span></div>')
            
            # Terminate the process
            if self.simulation_process.terminate_process():
                self.output_console.append("Simulation process terminated successfully.")
            else:
                self.output_console.append("Failed to terminate simulation process or process already completed.")
            
            # Reset UI state
            self.simulation_running = False
            self.run_btn.setEnabled(True)
            self.run_btn.setText("Run Simulation")
            self.stop_btn.setEnabled(False)
            self.stop_btn.setStyleSheet("background-color: #cccccc; color: #888888; font-weight: bold; font-size: 14px; padding: 8px;")
            
    def update_output(self, text):
        """Update the output console with text from the simulation thread."""
        if not text.strip():
            return
            
        # Format the output based on content type
        if "Error:" in text or "CRITICAL:" in text or "Failed" in text:
            formatted_text = f'<span style="color: #ff5555;"><b>❌ {text}</b></span>'
        elif "Warning:" in text or "YELLOW" in text:
            formatted_text = f'<span style="color: #ffff55;">⚠️ {text}</span>'
        elif "DEBUG:" in text:
            formatted_text = f'<span style="color: #7f7f7f;">🔍 {text}</span>'
        elif "Executing:" in text or "Running" in text or "Command" in text:
            formatted_text = f'<span style="color: #55aaff;">📋 {text}</span>'
        elif "completed successfully" in text or "completed." in text or "Successfully" in text or "completed:" in text:
            formatted_text = f'<span style="color: #55ff55;"><b>✅ {text}</b></span>'
        elif "Processing" in text or "Starting" in text:
            formatted_text = f'<span style="color: #55ffff;">🔄 {text}</span>'
        elif text.strip().startswith("-"):
            # Indented list items
            formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
        else:
            formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        
        # Add a timestamp
        timestamp = QtCore.QTime.currentTime().toString("hh:mm:ss")
        log_entry = f'<span style="color: #888888;">[{timestamp}]</span> {formatted_text}'
        
        # Append to the console with HTML formatting
        self.output_console.append(log_entry)
        
        # Ensure the latest output is visible
        self.output_console.ensureCursorVisible() 