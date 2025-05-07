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
        
        # Main horizontal layout to separate left and right
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        
        # Left side layout for subjects and montages
        left_layout = QtWidgets.QVBoxLayout()
        
        # Subject selection
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
        
        # Add subject container to left layout
        left_layout.addWidget(subject_container)
        
        # Montage selection - now placed below subjects on left side
        montage_container = QtWidgets.QGroupBox("Montage(s)")
        montage_layout = QtWidgets.QVBoxLayout(montage_container)
        
        # List widget for montage selection
        self.montage_list = QtWidgets.QListWidget()
        self.montage_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.montage_list.setMinimumHeight(100)
        montage_layout.addWidget(self.montage_list)
        
        # Montage control buttons
        montage_button_layout = QtWidgets.QHBoxLayout()
        # Add New Montage button
        self.add_new_montage_btn = QtWidgets.QPushButton("Add New Montage")
        self.add_new_montage_btn.clicked.connect(self.show_add_montage_dialog)
        # Other montage buttons
        self.list_montages_btn = QtWidgets.QPushButton("Refresh List")
        self.list_montages_btn.clicked.connect(self.update_montage_list)
        self.select_all_montages_btn = QtWidgets.QPushButton("Select All")
        self.select_all_montages_btn.clicked.connect(self.select_all_montages)
        self.clear_montage_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_montage_selection_btn.clicked.connect(self.clear_montage_selection)
        
        montage_button_layout.addWidget(self.add_new_montage_btn)
        montage_button_layout.addWidget(self.list_montages_btn)
        montage_button_layout.addWidget(self.select_all_montages_btn)
        montage_button_layout.addWidget(self.clear_montage_selection_btn)
        montage_layout.addLayout(montage_button_layout)
        
        # Add montage container to left layout
        left_layout.addWidget(montage_container)
        
        # Right side layout for simulation parameters
        right_layout = QtWidgets.QVBoxLayout()
        
        # Simulation parameters group
        sim_params_container = QtWidgets.QGroupBox("Simulation Configuration")
        sim_params_layout = QtWidgets.QVBoxLayout(sim_params_container)
        
        # Simulation type (Isotropic/Anisotropic)
        sim_type_layout = QtWidgets.QHBoxLayout()
        self.sim_type_label = QtWidgets.QLabel("Simulation Type:")
        self.sim_type_combo = QtWidgets.QComboBox()
        self.sim_type_combo.addItem("Isotropic", "scalar")
        self.sim_type_combo.addItem("Anisotropic (vn)", "vn")
        self.sim_type_combo.addItem("Anisotropic (dir)", "dir")
        self.sim_type_combo.addItem("Anisotropic (mc)", "mc")
        sim_type_layout.addWidget(self.sim_type_label)
        sim_type_layout.addWidget(self.sim_type_combo)
        sim_params_layout.addLayout(sim_type_layout)
        
        # Simulation mode (Unipolar/Multipolar)
        sim_mode_layout = QtWidgets.QHBoxLayout()
        self.sim_mode_label = QtWidgets.QLabel("Simulation Mode:")
        self.sim_mode_unipolar = QtWidgets.QRadioButton("Unipolar")
        self.sim_mode_multipolar = QtWidgets.QRadioButton("Multipolar")
        self.sim_mode_unipolar.setChecked(True)
        sim_mode_layout.addWidget(self.sim_mode_label)
        sim_mode_layout.addWidget(self.sim_mode_unipolar)
        sim_mode_layout.addWidget(self.sim_mode_multipolar)
        # Connect mode radio buttons to update montage list
        self.sim_mode_unipolar.toggled.connect(self.update_montage_list)
        self.sim_mode_multipolar.toggled.connect(self.update_montage_list)
        sim_params_layout.addLayout(sim_mode_layout)
        
        # Electrode parameters group
        self.electrode_params_group = QtWidgets.QGroupBox("Electrode Parameters")
        electrode_params_layout = QtWidgets.QVBoxLayout(self.electrode_params_group)
        
        # Current value
        current_layout = QtWidgets.QHBoxLayout()
        self.current_label = QtWidgets.QLabel("Current Value (mA):")
        self.current_input = QtWidgets.QLineEdit()
        self.current_input.setPlaceholderText("1.0")
        self.current_input.setText("1.0")  # Set default to 1.0 mA
        current_layout.addWidget(self.current_label)
        current_layout.addWidget(self.current_input)
        electrode_params_layout.addLayout(current_layout)
        
        # Electrode shape
        shape_layout = QtWidgets.QHBoxLayout()
        self.electrode_shape_label = QtWidgets.QLabel("Electrode Shape:")
        self.electrode_shape_rect = QtWidgets.QRadioButton("Rectangle")
        self.electrode_shape_rect.setProperty("value", "rect")
        self.electrode_shape_ellipse = QtWidgets.QRadioButton("Ellipse")
        self.electrode_shape_ellipse.setProperty("value", "ellipse")
        self.electrode_shape_ellipse.setChecked(True)  # Set default to Ellipse
        shape_layout.addWidget(self.electrode_shape_label)
        shape_layout.addWidget(self.electrode_shape_rect)
        shape_layout.addWidget(self.electrode_shape_ellipse)
        electrode_params_layout.addLayout(shape_layout)
        
        # Electrode dimensions
        dimensions_layout = QtWidgets.QHBoxLayout()
        self.dimensions_label = QtWidgets.QLabel("Dimensions (mm, x,y):")
        self.dimensions_input = QtWidgets.QLineEdit()
        self.dimensions_input.setPlaceholderText("8,8")
        self.dimensions_input.setText("8,8")  # Set default to 8,8
        dimensions_layout.addWidget(self.dimensions_label)
        dimensions_layout.addWidget(self.dimensions_input)
        electrode_params_layout.addLayout(dimensions_layout)
        
        # Electrode thickness
        thickness_layout = QtWidgets.QHBoxLayout()
        self.thickness_label = QtWidgets.QLabel("Thickness (mm):")
        self.thickness_input = QtWidgets.QLineEdit()
        self.thickness_input.setPlaceholderText("8")
        self.thickness_input.setText("8")  # Set default to 8mm
        thickness_layout.addWidget(self.thickness_label)
        thickness_layout.addWidget(self.thickness_input)
        electrode_params_layout.addLayout(thickness_layout)
        
        # Add electrode params group to simulation params
        sim_params_layout.addWidget(self.electrode_params_group)
        
        # Add simulation parameters to right layout
        right_layout.addWidget(sim_params_container)
        
        # Add left and right layouts to main horizontal layout
        main_horizontal_layout.addLayout(left_layout, 1)  # 1:2 ratio
        main_horizontal_layout.addLayout(right_layout, 2)
        
        # Add main horizontal layout to scroll layout
        scroll_layout.addLayout(main_horizontal_layout)
        
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
        
        # Stop button (initially disabled)
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
        self.stop_btn.setEnabled(False)  # Initially disabled
        
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
            self.clear_subject_selection_btn.setIcon(QtGui.QIcon.fromTheme("view-list"))
            self.select_all_subjects_btn.setIcon(QtGui.QIcon.fromTheme("view-list"))
            self.clear_montage_selection_btn.setIcon(QtGui.QIcon.fromTheme("view-list"))
            self.add_new_montage_btn.setIcon(QtGui.QIcon.fromTheme("list-add"))
        
        # Add the button layout to scroll layout
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
        
        # We'll keep the old montage group but hide it since we're moving this functionality
        # to a dialog. It will be referenced by the dialog.
        self.montage_group = QtWidgets.QGroupBox("Add New Montage")
        self.montage_group.setVisible(False)
        self.montage_content = QtWidgets.QWidget()
        
        # Create the electrode stacked widget for reference in the dialog
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
    
    def list_subjects(self):
        """List available subjects and display them."""
        try:
            # Clear current list
            self.subject_list.clear()
            
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
                    
                    # Update the subject list with the available subjects
                    self.subject_list.addItems(subjects)
                    
                    self.update_output(f"Found {len(subjects)} subjects. Subject list updated.")
                else:
                    self.update_output("No subjects found in the project directory.")
            else:
                self.update_output("Error finding subjects: " + err.decode())
            
        except Exception as e:
            self.update_output(f"Error: {str(e)}")
    
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
                
                montages = montage_data[montage_type]
                
                if isinstance(montages, dict) and montages:
                    # Add montages to the list widget
                    for montage_name in montages.keys():
                        self.montage_list.addItem(montage_name)
                    
                    self.update_output(f"Found {len(montages)} {mode_text.lower()} montages.")
                else:
                    self.update_output(f"No {mode_text.lower()} montages found.")
            else:
                self.update_output(f"Montage file not found: {montage_file}")
                
        except Exception as e:
            self.update_output(f"Error updating montage list: {str(e)}")
            
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
            self.montage_list.addItem(file_name)
            self.output_console.append(f"Selected montage file: {file_name}")
    
    def run_simulation(self):
        """Run the simulation with the selected parameters."""
        if self.simulation_running:
            self.output_console.append("A simulation is already running.")
            return
        
        try:
            # Check if subjects and montages are selected
            selected_subjects = self.subject_list.selectedItems()
            if not selected_subjects:
                self.update_output("Error: No subjects selected.")
                return
            
            selected_montages = self.montage_list.selectedItems()
            if not selected_montages:
                self.update_output("Error: No montages selected.")
                return
            
            # Get simulation parameters from UI
            conductivity = self.sim_type_combo.currentData()
            sim_mode = "U" if self.sim_mode_unipolar.isChecked() else "M"
            
            # Get electrode parameters
            current = self.current_input.text().strip()
            if not self.validate_current(current):
                self.update_output("Error: Invalid current value. Please enter a valid number.")
                return
            
            # Get shape value from radio buttons
            shape_value = "rect" if self.electrode_shape_rect.isChecked() else "ellipse"
            dimensions = self.dimensions_input.text().strip()
            thickness = self.thickness_input.text().strip()
            
            # Validation for dimensions
            dimension_match = re.match(r'^\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*$', dimensions)
            if not dimension_match:
                self.update_output("Error: Dimensions must be in format 'x,y' (e.g., '8,8').")
                return
            
            # Validation for thickness
            try:
                thickness_value = float(thickness)
                if thickness_value <= 0:
                    raise ValueError("Thickness must be positive")
            except ValueError:
                self.update_output("Error: Thickness must be a positive number.")
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
            self.update_output("\nSimulation Overview:")
            self.update_output(f"- Subjects: {subjects_str}")
            self.update_output(f"- Montages: {montages_str}")
            self.update_output(f"- Simulation Type: {self.sim_type_combo.currentText()}")
            self.update_output(f"- Simulation Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}")
            self.update_output(f"- Current: {current} mA")
            self.update_output(f"- Electrode Shape: {self.electrode_shape_rect.text() if self.electrode_shape_rect.isChecked() else self.electrode_shape_ellipse.text()}")
            self.update_output(f"- Dimensions: {dimensions} mm")
            self.update_output(f"- Thickness: {thickness} mm")
            
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
                f"Electrode Shape: {self.electrode_shape_rect.text() if self.electrode_shape_rect.isChecked() else self.electrode_shape_ellipse.text()}\n"
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
                env["ELECTRODE_SHAPE"] = shape_value
                env["DIMENSIONS"] = dimensions
                env["THICKNESS"] = thickness
                env["DIRECT_MODE"] = "true"
                env["NON_INTERACTIVE"] = "true"
                
                # Add project directory name if available
                project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')
                env["PROJECT_DIR_NAME"] = project_dir_name
                env["PROJECT_DIR"] = f"/mnt/{project_dir_name}"
                
                # Start simulation
                self.update_output(f"\nStarting simulation batch with {len(subjects)} subject(s) and {len(montages)} montage(s)...")
                self.update_output(f"Command: {' '.join(cmd)}")
                
                # Start simulation thread
                self.simulation_process = SimulationThread(cmd, env)
                self.simulation_process.output_signal.connect(self.update_output)
                self.simulation_process.finished.connect(self.simulation_finished)
                self.simulation_process.start()
            
        except Exception as e:
            self.update_output(f"Error starting simulation: {str(e)}")
            self.simulation_running = False
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
    
    def simulation_finished(self):
        """Handle simulation completion."""
        self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">✅ Simulation process completed ✅</span></div>')
        self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
        
        self.simulation_running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run Simulation")
        self.stop_btn.setEnabled(False)
    
    def update_electrode_inputs(self, checked):
        """Update the electrode input form based on the selected simulation mode.
        This only affects which montages are shown in the list."""
        self.update_montage_list(checked)
    
    def clear_console(self):
        """Clear the output console."""
        self.output_console.clear()
    
    def stop_simulation(self):
        """Stop the running simulation."""
        if hasattr(self, 'simulation_process') and self.simulation_process:
            # Show stopping message
            self.update_output("Stopping simulation...")
            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">⚠️ Simulation terminated by user ⚠️</span></div>')
            
            # Terminate the process
            if self.simulation_process.terminate_process():
                self.update_output("Simulation process terminated successfully.")
            else:
                self.update_output("Failed to terminate simulation process or process already completed.")
            
            # Reset UI state
            self.simulation_running = False
            self.run_btn.setEnabled(True)
            self.run_btn.setText("Run Simulation")
            self.stop_btn.setEnabled(False)
            
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

    def show_add_montage_dialog(self):
        """Show the dialog for adding a new montage."""
        dialog = AddMontageDialog(self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Get data from dialog
            montage_data = dialog.get_montage_data()
            
            # Validate the montage data
            if not montage_data["name"]:
                self.update_output("Error: Montage name is required")
                return
                
            if not montage_data["electrode_pairs"]:
                self.update_output("Error: At least one electrode pair is required")
                return
                
            # Validate electrode formats
            for pair in montage_data["electrode_pairs"]:
                if not self.validate_electrode(pair[0]) or not self.validate_electrode(pair[1]):
                    self.update_output("Error: Invalid electrode format (should be E1, E2)")
                    return
            
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
            montage_data_file = {"uni_polar_montages": {}, "multi_polar_montages": {}}
            if os.path.exists(montage_file):
                with open(montage_file, 'r') as f:
                    try:
                        loaded_data = json.load(f)
                        
                        # Handle different data structures - make sure we have a dictionary
                        if isinstance(loaded_data, dict):
                            montage_data_file = loaded_data
                            # Ensure the required keys exist
                            if "uni_polar_montages" not in montage_data_file:
                                montage_data_file["uni_polar_montages"] = {}
                            if "multi_polar_montages" not in montage_data_file:
                                montage_data_file["multi_polar_montages"] = {}
                    except json.JSONDecodeError:
                        self.output_console.append(f"Warning: Couldn't parse {montage_file}. Creating new file.")
            
            # Add the new montage to the appropriate section
            montage_type = "uni_polar_montages" if montage_data["is_unipolar"] else "multi_polar_montages"
            
            # Store the montage
            montage_data_file[montage_type][montage_data["name"]] = montage_data["electrode_pairs"]
            
            # Save the updated montage data
            with open(montage_file, 'w') as f:
                json.dump(montage_data_file, f, indent=2)
            
            # Format pairs for display
            pairs_text = ", ".join([f"{pair[0]}→{pair[1]}" for pair in montage_data["electrode_pairs"]])
            
            self.update_output(f"Added {montage_type.split('_')[0]} montage '{montage_data['name']}' with pairs: {pairs_text}")
            self.update_output(f"Montage saved to: {montage_file}")
            
            # Set file permissions to match simulator.sh behavior
            os.chmod(montage_file, 0o777)
            
            # Update the montage list with the newly added montage
            self.montage_list.addItem(montage_data["name"])
            
            # Refresh the list of montages
            self.update_montage_list()

class AddMontageDialog(QtWidgets.QDialog):
    """Dialog for adding new montages."""
    
    def __init__(self, parent=None):
        super(AddMontageDialog, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
        # Connect radio buttons to update electrode inputs
        self.mode_unipolar.toggled.connect(self.update_electrode_inputs)
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Add New Montage")
        self.setModal(True)
        self.resize(500, 400)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Montage name
        name_layout = QtWidgets.QHBoxLayout()
        self.name_label = QtWidgets.QLabel("Montage Name:")
        self.name_input = QtWidgets.QLineEdit()
        name_layout.addWidget(self.name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Simulation mode (Unipolar/Multipolar)
        mode_layout = QtWidgets.QHBoxLayout()
        self.mode_label = QtWidgets.QLabel("Montage Type:")
        self.mode_unipolar = QtWidgets.QRadioButton("Unipolar")
        self.mode_multipolar = QtWidgets.QRadioButton("Multipolar")
        self.mode_unipolar.setChecked(True)  # Default to unipolar
        mode_layout.addWidget(self.mode_label)
        mode_layout.addWidget(self.mode_unipolar)
        mode_layout.addWidget(self.mode_multipolar)
        layout.addLayout(mode_layout)
        
        # Create a stacked widget for electrode inputs
        self.electrode_stack = QtWidgets.QStackedWidget()
        
        # Unipolar electrode pairs (two pairs)
        uni_widget = QtWidgets.QWidget()
        uni_layout = QtWidgets.QVBoxLayout(uni_widget)
        
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
        uni_layout.addLayout(uni_pair1_layout)
        
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
        uni_layout.addLayout(uni_pair2_layout)
        
        # Multipolar electrode pairs (four pairs)
        multi_widget = QtWidgets.QWidget()
        multi_layout = QtWidgets.QVBoxLayout(multi_widget)
        
        # Create pairs for multipolar mode
        self.multi_pairs = []
        for i in range(1, 5):
            pair_layout = QtWidgets.QHBoxLayout()
            pair_label = QtWidgets.QLabel(f"Pair {i}:")
            e1 = QtWidgets.QLineEdit()
            e1.setPlaceholderText(f"E{10+2*(i-1)}")
            e2 = QtWidgets.QLineEdit()
            e2.setPlaceholderText(f"E{11+2*(i-1)}")
            
            pair_layout.addWidget(pair_label)
            pair_layout.addWidget(e1)
            pair_layout.addWidget(QtWidgets.QLabel("→"))
            pair_layout.addWidget(e2)
            multi_layout.addLayout(pair_layout)
            
            # Store references
            self.multi_pairs.append((e1, e2))
        
        # Add the widgets to the stacked widget
        self.electrode_stack.addWidget(uni_widget)
        self.electrode_stack.addWidget(multi_widget)
        layout.addWidget(self.electrode_stack)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def update_electrode_inputs(self, checked):
        """Update the electrode input view based on the selected mode."""
        if checked:  # Unipolar selected
            self.electrode_stack.setCurrentIndex(0)
        else:  # Multipolar selected
            self.electrode_stack.setCurrentIndex(1)
    
    def get_montage_data(self):
        """Get montage data entered in the dialog."""
        name = self.name_input.text().strip()
        is_unipolar = self.mode_unipolar.isChecked()
        
        electrode_pairs = []
        
        if is_unipolar:
            # Get unipolar pairs
            pair1_e1 = self.uni_pair1_e1.text().strip()
            pair1_e2 = self.uni_pair1_e2.text().strip()
            pair2_e1 = self.uni_pair2_e1.text().strip()
            pair2_e2 = self.uni_pair2_e2.text().strip()
            
            if pair1_e1 and pair1_e2:
                electrode_pairs.append([pair1_e1, pair1_e2])
            if pair2_e1 and pair2_e2:
                electrode_pairs.append([pair2_e1, pair2_e2])
        else:
            # Get multipolar pairs
            for e1, e2 in self.multi_pairs:
                e1_text = e1.text().strip()
                e2_text = e2.text().strip()
                if e1_text and e2_text:
                    electrode_pairs.append([e1_text, e2_text])
        
        return {
            "name": name,
            "is_unipolar": is_unipolar,
            "electrode_pairs": electrode_pairs
        } 