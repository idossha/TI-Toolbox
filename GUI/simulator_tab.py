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
        
        # Subject selection
        self.subject_label = QtWidgets.QLabel("Subject(s):")
        self.subject_input = QtWidgets.QLineEdit()
        self.list_subjects_btn = QtWidgets.QPushButton("List Available Subjects")
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        subject_layout = QtWidgets.QHBoxLayout()
        subject_layout.addWidget(self.subject_input)
        subject_layout.addWidget(self.list_subjects_btn)
        form_layout.addRow(self.subject_label, subject_layout)
        
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
        form_layout.addRow(self.sim_mode_label, self.sim_mode_layout)
        
        # Montages
        self.montage_label = QtWidgets.QLabel("Montage:")
        self.montage_input = QtWidgets.QLineEdit()
        self.montage_browse_btn = QtWidgets.QPushButton("Browse")
        self.montage_browse_btn.clicked.connect(self.browse_montage)
        self.list_montages_btn = QtWidgets.QPushButton("List Available Montages")
        self.list_montages_btn.clicked.connect(self.list_montages)
        montage_layout = QtWidgets.QHBoxLayout()
        montage_layout.addWidget(self.montage_input)
        montage_layout.addWidget(self.montage_browse_btn)
        montage_layout.addWidget(self.list_montages_btn)
        form_layout.addRow(self.montage_label, montage_layout)
        
        # Simulation Parameters group
        self.sim_params_group = QtWidgets.QGroupBox("Simulation Parameters")
        sim_params_layout = QtWidgets.QVBoxLayout(self.sim_params_group)
        
        # Current value
        current_layout = QtWidgets.QHBoxLayout()
        self.current_label = QtWidgets.QLabel("Current Value (mA):")
        self.current_input = QtWidgets.QLineEdit()
        self.current_input.setPlaceholderText("2.0")
        self.current_input.setText("2.0")  # Default value
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
        electrode_geometry_layout.addRow(self.electrode_shape_label, self.electrode_shape_combo)
        
        # Electrode dimensions
        self.dimensions_label = QtWidgets.QLabel("Dimensions (mm, x,y):")
        self.dimensions_input = QtWidgets.QLineEdit()
        self.dimensions_input.setPlaceholderText("50,50")
        self.dimensions_input.setText("50,50")  # Default value
        electrode_geometry_layout.addRow(self.dimensions_label, self.dimensions_input)
        
        # Electrode thickness
        self.thickness_label = QtWidgets.QLabel("Thickness (mm):")
        self.thickness_input = QtWidgets.QLineEdit()
        self.thickness_input.setPlaceholderText("5")
        self.thickness_input.setText("5")  # Default value
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
        self.run_btn.setMinimumHeight(50)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                padding: 10px;
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
        
        # Stop button (initially hidden)
        self.stop_btn = QtWidgets.QPushButton("Stop Simulation")
        self.stop_btn.clicked.connect(self.stop_simulation)
        self.stop_btn.setMinimumHeight(50)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                padding: 10px;
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
        self.stop_btn.setVisible(False)
        
        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.run_btn)
        button_layout.addWidget(self.stop_btn)
        
        # Add icons to buttons for better visual appearance
        if QtGui.QIcon.hasThemeIcon("document-save"):
            self.run_btn.setIcon(QtGui.QIcon.fromTheme("media-playback-start"))
            self.stop_btn.setIcon(QtGui.QIcon.fromTheme("media-playback-stop"))
            self.list_subjects_btn.setIcon(QtGui.QIcon.fromTheme("view-list"))
            self.list_montages_btn.setIcon(QtGui.QIcon.fromTheme("view-list"))
            self.montage_browse_btn.setIcon(QtGui.QIcon.fromTheme("document-open"))
            self.add_montage_btn.setIcon(QtGui.QIcon.fromTheme("list-add"))
        
        # Add form layout to scroll layout
        scroll_layout.addLayout(form_layout)
        scroll_layout.addLayout(button_layout)
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Output console
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        
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
        
        # Clear console button
        clear_btn = QtWidgets.QPushButton("Clear Console")
        clear_btn.clicked.connect(self.clear_console)
        clear_btn.setStyleSheet("background-color: #555; color: white;")
        
        # Console layout
        console_layout = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(output_label)
        header_layout.addStretch()
        header_layout.addWidget(clear_btn)
        console_layout.addLayout(header_layout)
        console_layout.addWidget(self.output_console)
        
        main_layout.addLayout(console_layout)
        
    def list_subjects(self):
        """List available subjects and display them."""
        try:
            # Get the base directory
            script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
            
            # Use environment variable for project directory like simulator.sh does
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', '')
            project_dir = f"/mnt/{project_dir_name}" if project_dir_name else "/mnt"
            
            self.update_output("Listing available subjects...")
            self.update_output(f"Looking in project directory: {project_dir}")
            
            # Execute the find command to list only main subject directories
            cmd = f'find "{project_dir}" -maxdepth 3 -type d -path "*/SimNIBS/m2m_*" | sed "s/.*m2m_//" | cut -d"/" -f1 | sort -u'
            self.update_output(f"Command: {cmd}")
            
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = process.communicate()
            
            if process.returncode == 0:
                subjects = out.decode().strip().split('\n')
                # Filter out empty entries
                subjects = [s for s in subjects if s]
                
                if subjects:
                    self.output_console.append('<div style="background-color: #2a2a2a; border: 1px solid #444; border-radius: 5px; padding: 10px; margin: 10px 0;">')
                    self.output_console.append('<span style="color: #55ffff; font-weight: bold;">📋 Available Subjects:</span>')
                    self.output_console.append('<div style="display: grid; grid-template-columns: repeat(3, 1fr); grid-gap: 5px; margin-top: 5px;">')
                    
                    for i, subject in enumerate(subjects, 1):
                        self.output_console.append(f'<div style="color: #ffffff; padding: 3px 8px; background-color: #333; border-radius: 3px;">{i}. {subject}</div>')
                    
                    self.output_console.append('</div></div>')
                    
                    # Update the subject input field with comma-separated subject list
                    self.subject_input.setText(",".join(subjects))
                    
                    self.update_output(f"Found {len(subjects)} subjects. Input field updated.")
                else:
                    self.update_output("No subjects found in the project directory.")
            else:
                self.update_output("Error finding subjects: " + err.decode())
            
        except Exception as e:
            self.update_output(f"Error: {str(e)}")
    
    def list_montages(self):
        """List available montages from montage_list.json."""
        try:
            # Use environment variable for project directory like simulator.sh does
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
            project_dir = f"/mnt/{project_dir_name}"
            utils_dir = os.path.join(project_dir, "utils")
            montage_file = os.path.join(utils_dir, "montage_list.json")
            
            self.update_output(f"Looking for montages in: {montage_file}")
            
            if os.path.exists(montage_file):
                with open(montage_file, 'r') as f:
                    montage_data = json.load(f)
                
                # Create expected structure if needed
                if not isinstance(montage_data, dict):
                    self.update_output(f"Warning: Unexpected data type in montage file: {type(montage_data).__name__}. Creating new structure.")
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
                self.update_output(f"Montage file not found at {montage_file}")
                self.update_output("Create a new montage using the form below.")
        except Exception as e:
            self.update_output(f"Error listing montages: {str(e)}")
    
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
            self.montage_input.setText(file_name)
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
            
            # Update the montage field with the newly added montage
            self.montage_input.setText(montage_name)
            
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
        """Run the simulation with the provided parameters."""
        try:
            # Clear console at the start of a new simulation
            if not self.simulation_running:
                self.clear_console()
            
            # Display header
            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ffff; font-size: 16px; font-weight: bold;">🧠 TI-CSC-2.0 SIMULATION 🧠</span></div>')
            self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
            
            # Get parameters from UI
            subjects = self.subject_input.text().strip()
            conductivity = self.sim_type_combo.currentData()
            
            sim_mode = "U" if self.sim_mode_unipolar.isChecked() else "M"
            montage = self.montage_input.text().strip()
            
            # Get parameters from Simulation Parameters section
            current = self.current_input.text().strip()
            if not current or not self.validate_current(current):
                self.update_output("Error: Invalid current value (should be a number)")
                return
                
            electrode_shape = self.electrode_shape_combo.currentData()
            dimensions = self.dimensions_input.text().strip()
            thickness = self.thickness_input.text().strip()
            
            # Validate the dimensions and thickness
            if not dimensions or not re.match(r'^\d+,\d+$', dimensions):
                self.update_output("Error: Invalid dimensions format (should be x,y)")
                return
                
            if not thickness or not re.match(r'^\d+(\.\d+)?$', thickness):
                self.update_output("Error: Invalid thickness value (should be a number)")
                return
                
            # Validate inputs
            if not subjects:
                self.update_output("Error: Please select at least one subject")
                return
                
            if not montage:
                self.update_output("Error: Please select a montage")
                return
            
            # Get path to simulator.sh (the CLI entry point)
            script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
            simulator_script = os.path.join(script_dir, "simulator.sh")
            
            self.update_output(f"Using simulator script at: {simulator_script}")
            
            # Get project directory information
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
            project_dir = f"/mnt/{project_dir_name}"
            self.update_output(f"Project directory: {project_dir}")
            
            # Debug path information for a selected subject
            if "," in subjects:
                subject_list = subjects.split(",")
                first_subject = subject_list[0].strip()
            else:
                first_subject = subjects.strip()
                
            subject_dir = f"{project_dir}/{first_subject}"
            m2m_dir = f"{subject_dir}/SimNIBS/m2m_{first_subject}"
            self.update_output(f"Example subject directory: {subject_dir}")
            self.update_output(f"Expected m2m directory: {m2m_dir}")
            
            # Display simulation configuration summary
            self.output_console.append('<div style="background-color: #2a2a2a; border: 1px solid #444; border-radius: 5px; padding: 10px; margin: 10px 0;">')
            self.output_console.append('<span style="color: #55ffff; font-weight: bold;">📋 Simulation Configuration:</span>')
            self.output_console.append(f'<div style="margin-left: 20px; color: #dddddd;">')
            self.output_console.append(f'<p>• <b>Subjects:</b> {subjects}</p>')
            self.output_console.append(f'<p>• <b>Simulation Type:</b> {self.sim_type_combo.currentText()}</p>')
            self.output_console.append(f'<p>• <b>Mode:</b> {"Unipolar" if sim_mode == "U" else "Multipolar"}</p>')
            self.output_console.append(f'<p>• <b>Montage:</b> {montage}</p>')
            self.output_console.append(f'<p>• <b>Current:</b> {current} mA</p>')
            self.output_console.append(f'<p>• <b>Electrode Shape:</b> {self.electrode_shape_combo.currentText()}</p>')
            self.output_console.append(f'<p>• <b>Dimensions:</b> {dimensions} mm</p>')
            self.output_console.append(f'<p>• <b>Thickness:</b> {thickness} mm</p>')
            self.output_console.append('</div>')
            self.output_console.append('</div>')
            
            # Prepare environment variables to bypass prompts in simulator.sh
            env = os.environ.copy()
            
            # Set all required environment variables for direct execution
            env["SUBJECTS"] = subjects
            env["CONDUCTIVITY"] = conductivity
            env["SIM_MODE"] = sim_mode
            env["SELECTED_MONTAGES"] = montage
            env["CURRENT"] = current
            env["ELECTRODE_SHAPE"] = electrode_shape
            env["DIMENSIONS"] = dimensions
            env["THICKNESS"] = thickness
            env["NON_INTERACTIVE"] = "true"  # Skip prompts
            env["DIRECT_MODE"] = "true"  # Indicate direct execution mode
            
            # Make sure TI scripts can find their utils directory
            env["UTILS_DIR"] = f"{subject_dir}/utils"
            self.update_output(f"Setting UTILS_DIR to: {env['UTILS_DIR']}")
            
            # Explicitly set project directory
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
            env["PROJECT_DIR_NAME"] = project_dir_name
            env["PROJECT_DIR"] = f"/mnt/{project_dir_name}"
            
            # Ensure the run-direct flag is recognized
            cmd = [
                "bash", 
                simulator_script,
                "--run-direct"  # Custom flag to indicate direct execution
            ]
            
            # Display environment variables in output console
            self.update_output("\nEnvironment variables for simulation:")
            for key in ["SUBJECTS", "CONDUCTIVITY", "SIM_MODE", "SELECTED_MONTAGES", 
                       "CURRENT", "ELECTRODE_SHAPE", "DIMENSIONS", "THICKNESS"]:
                self.update_output(f"  - {key}: {env.get(key, 'Not set')}")
            
            # Display command in output console
            cmd_str = " ".join(cmd)
            self.update_output("\nRunning simulation with command:")
            self.update_output(cmd_str)
            
            # Execute the command using a separate thread to prevent GUI freezing
            self.update_output("\nStarting simulation. This may take a while...")
            
            # Update UI to show progress
            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ff55;">⏳ Simulation in progress... ⏳</span></div>')
            
            # Create and start the worker thread
            self.simulation_thread = SimulationThread(cmd, env)
            self.simulation_thread.output_signal.connect(self.update_output)
            self.simulation_thread.finished.connect(self.simulation_finished)
            self.simulation_thread.start()
            
            # Update UI for running state
            self.simulation_running = True
            self.run_btn.setEnabled(False)
            self.run_btn.setText("Simulation Running...")
            self.stop_btn.setVisible(True)
            
        except Exception as e:
            self.update_output(f"Error: {str(e)}")
            
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
        self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">✅ Simulation process completed ✅</span></div>')
        self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
        
        self.simulation_running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run Simulation")
        self.stop_btn.setVisible(False)
    
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
        if hasattr(self, 'simulation_thread') and self.simulation_thread:
            # Show stopping message
            self.update_output("Stopping simulation...")
            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">⚠️ Simulation terminated by user ⚠️</span></div>')
            
            # Terminate the process
            if self.simulation_thread.terminate_process():
                self.update_output("Simulation process terminated successfully.")
            else:
                self.update_output("Failed to terminate simulation process or process already completed.")
            
            # Reset UI state
            self.simulation_running = False
            self.run_btn.setEnabled(True)
            self.run_btn.setText("Run Simulation")
            self.stop_btn.setVisible(False)
            
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