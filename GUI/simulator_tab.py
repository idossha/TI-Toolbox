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
import sys
import time
import threading
from pathlib import Path
import datetime
import tempfile
import shutil

from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite

# Add the utils directory to the path
import sys
import os
utils_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'utils')
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)

# Now import from utils
try:
    from report_util import get_simulation_report_generator
except ImportError as e:
    print(f"Warning: Could not import report utilities: {e}")
    # Define a fallback function
    def get_simulation_report_generator(*args, **kwargs):
        print("Warning: Report generation not available")
        return None

class SimulationThread(QtCore.QThread):
    """Thread to run simulation in background to prevent GUI freezing."""
    
    # Signal to emit output text with message type
    output_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)
    
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
                stderr=subprocess.STDOUT,  # Combine stderr with stdout to prevent blocking
                universal_newlines=True,
                bufsize=1,
                env=self.env
            )
            
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
                    self.error_signal.emit("Process returned non-zero exit code")
                    
        except Exception as e:
            self.error_signal.emit(f"Error running simulation: {str(e)}")
    
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
        self.custom_conductivities = {}  # keys: int tissue number, values: float
        self.report_generator = None
        self.simulation_session_id = None
        self.setup_ui()
        
        # Initialize with available subjects and montages
        QtCore.QTimer.singleShot(500, self.list_subjects)
        QtCore.QTimer.singleShot(700, self.update_montage_list)
        QtCore.QTimer.singleShot(900, self.refresh_flex_search_list)
        QtCore.QTimer.singleShot(1000, self.initialize_ui_state)  # Initialize UI state silently
        
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
        self.subject_list.setMinimumHeight(90)  # Reduced by 10% (100 * 0.9 = 90)
        self.subject_list.itemSelectionChanged.connect(self.refresh_flex_search_list)  # Refresh flex-search when subjects change
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
        montage_container.setMinimumHeight(202)  # Reduced by 10% (224 * 0.9 = 202)
        montage_container.setMaximumHeight(202)  # Set maximum height for consistency
        montage_container.setMinimumWidth(450)   # Reduced by 10% (500 * 0.9 = 450)
        montage_container.setMaximumWidth(450)   # Set maximum width for consistency
        montage_layout = QtWidgets.QVBoxLayout(montage_container)
        
        # List widget for montage selection
        self.montage_list = QtWidgets.QListWidget()
        self.montage_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.montage_list.setMinimumHeight(86)   # Reduced by 10% (96 * 0.9 = 86)
        self.montage_list.setMaximumHeight(86)   # Fixed height for consistency
        montage_layout.addWidget(self.montage_list)
        
        # Montage control buttons
        montage_button_layout = QtWidgets.QHBoxLayout()
        # Add New Montage button
        self.add_new_montage_btn = QtWidgets.QPushButton("Add New Montage")
        self.add_new_montage_btn.clicked.connect(self.show_add_montage_dialog)
        # Remove Montage button
        self.remove_montage_btn = QtWidgets.QPushButton("Remove Montage")
        self.remove_montage_btn.clicked.connect(self.remove_selected_montage)
        # Other montage buttons
        self.list_montages_btn = QtWidgets.QPushButton("Refresh List")
        self.list_montages_btn.clicked.connect(self.update_montage_list)
        self.clear_montage_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_montage_selection_btn.clicked.connect(self.clear_montage_selection)
        
        montage_button_layout.addWidget(self.add_new_montage_btn)
        montage_button_layout.addWidget(self.remove_montage_btn)
        montage_button_layout.addWidget(self.list_montages_btn)
        montage_button_layout.addWidget(self.clear_montage_selection_btn)
        montage_layout.addLayout(montage_button_layout)
        
        # Add montage container to left layout
        left_layout.addWidget(montage_container)
        
        # Flex-search outputs selection
        flex_search_container = QtWidgets.QGroupBox("Flex-Search Outputs")
        flex_search_container.setMinimumHeight(202)  # Reduced by 10% (224 * 0.9 = 202)
        flex_search_container.setMaximumHeight(202)  # Set maximum height for consistency
        flex_search_container.setMinimumWidth(450)   # Reduced by 10% (500 * 0.9 = 450)
        flex_search_container.setMaximumWidth(450)   # Set maximum width for consistency
        flex_search_layout = QtWidgets.QVBoxLayout(flex_search_container)
        
        # List widget for flex-search output selection
        self.flex_search_list = QtWidgets.QListWidget()
        self.flex_search_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.flex_search_list.setMinimumHeight(86)   # Reduced by 10% (96 * 0.9 = 86)
        self.flex_search_list.setMaximumHeight(86)   # Fixed height for consistency
        flex_search_layout.addWidget(self.flex_search_list)
        
        # Flex-search options
        flex_options_layout = QtWidgets.QHBoxLayout()
        self.flex_use_mapped = QtWidgets.QCheckBox("Use Mapped")
        self.flex_use_optimized = QtWidgets.QCheckBox("Use Optimized")
        self.flex_use_mapped.setChecked(True)  # Default to mapped
        
        # No button group - checkboxes are independent
        
        flex_options_layout.addWidget(QtWidgets.QLabel("Electrode Type:"))
        flex_options_layout.addWidget(self.flex_use_mapped)
        flex_options_layout.addWidget(self.flex_use_optimized)
        flex_options_layout.addStretch()
        flex_search_layout.addLayout(flex_options_layout)
        
        # Flex-search control buttons
        flex_button_layout = QtWidgets.QHBoxLayout()
        self.refresh_flex_btn = QtWidgets.QPushButton("Refresh List")
        self.refresh_flex_btn.clicked.connect(self.refresh_flex_search_list)
        self.clear_flex_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_flex_selection_btn.clicked.connect(self.clear_flex_search_selection)
        
        flex_button_layout.addWidget(self.refresh_flex_btn)
        flex_button_layout.addWidget(self.clear_flex_selection_btn)
        flex_search_layout.addLayout(flex_button_layout)
        
        # Add flex-search container to left layout
        left_layout.addWidget(flex_search_container)
        
        # Store containers for show/hide functionality
        self.montage_container = montage_container
        self.flex_search_container = flex_search_container
        
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
        
        # Add help button
        self.sim_type_help_btn = QtWidgets.QPushButton("?")
        self.sim_type_help_btn.setFixedWidth(20)
        self.sim_type_help_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        self.sim_type_help_btn.clicked.connect(self.show_sim_type_help)
        
        sim_type_layout.addWidget(self.sim_type_label)
        sim_type_layout.addWidget(self.sim_type_combo)
        sim_type_layout.addWidget(self.sim_type_help_btn)
        sim_params_layout.addLayout(sim_type_layout)
        
        # Add conductivity editor button with simple styling
        self.conductivity_editor_btn = QtWidgets.QPushButton("Change Default Conductivities")
        sim_params_layout.addWidget(self.conductivity_editor_btn)
        self.conductivity_editor_btn.clicked.connect(self.show_conductivity_editor)
        
        # EEG Net selection
        eeg_net_layout = QtWidgets.QHBoxLayout()
        self.eeg_net_label = QtWidgets.QLabel("EEG Net:")
        self.eeg_net_combo = QtWidgets.QComboBox()
        eeg_net_layout.addWidget(self.eeg_net_label)
        eeg_net_layout.addWidget(self.eeg_net_combo)
        sim_params_layout.addLayout(eeg_net_layout)

        # Connect EEG net selection change to montage list update
        self.eeg_net_combo.currentTextChanged.connect(self.update_montage_list)

        # Simulation Type Selection (Montage vs Flex)
        sim_type_selection_layout = QtWidgets.QHBoxLayout()
        self.sim_type_selection_label = QtWidgets.QLabel("Simulation Type:")
        self.sim_type_montage = QtWidgets.QRadioButton("Montage Simulation")
        self.sim_type_flex = QtWidgets.QRadioButton("Flex-Search Simulation")
        self.sim_type_montage.setChecked(True)  # Default to montage simulation
        
        # Create button group for mutual exclusion
        self.sim_type_group = QtWidgets.QButtonGroup()
        self.sim_type_group.addButton(self.sim_type_montage, 1)
        self.sim_type_group.addButton(self.sim_type_flex, 2)
        
        sim_type_selection_layout.addWidget(self.sim_type_selection_label)
        sim_type_selection_layout.addWidget(self.sim_type_montage)
        sim_type_selection_layout.addWidget(self.sim_type_flex)
        sim_type_selection_layout.addStretch()
        sim_params_layout.addLayout(sim_type_selection_layout)
        
        # Connect to mode change handler - use clicked to avoid double signals
        self.sim_type_montage.clicked.connect(self.on_simulation_type_changed)
        self.sim_type_flex.clicked.connect(self.on_simulation_type_changed)

        # Simulation mode (Unipolar/Multipolar) - only for montage simulation
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
        
        # Store the sim_mode_layout for show/hide
        self.sim_mode_layout_widgets = [self.sim_mode_label, self.sim_mode_unipolar, self.sim_mode_multipolar]
        
        # Electrode parameters group
        self.electrode_params_group = QtWidgets.QGroupBox("Electrode Parameters")
        electrode_params_layout = QtWidgets.QVBoxLayout(self.electrode_params_group)
        
        # Current value (now two fields)
        current_layout = QtWidgets.QHBoxLayout()
        self.current_label_1 = QtWidgets.QLabel("Current Ch1 (mA):")
        self.current_input_1 = QtWidgets.QLineEdit()
        self.current_input_1.setPlaceholderText("1.0")
        self.current_input_1.setText("1.0")  # Default to 1.0 mA
        self.current_label_2 = QtWidgets.QLabel("Current Ch2 (mA):")
        self.current_input_2 = QtWidgets.QLineEdit()
        self.current_input_2.setPlaceholderText("1.0")
        self.current_input_2.setText("1.0")  # Default to 1.0 mA
        current_layout.addWidget(self.current_label_1)
        current_layout.addWidget(self.current_input_1)
        current_layout.addSpacing(10)
        current_layout.addWidget(self.current_label_2)
        current_layout.addWidget(self.current_input_2)
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
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Output console
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        
        self.output_console = QtWidgets.QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setMinimumHeight(180)  # Reduced by 10% (200 * 0.9 = 180)
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
        
        # Console layout
        console_layout = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(output_label)
        header_layout.addStretch()
        
        # Create button layout for console controls
        console_buttons_layout = QtWidgets.QHBoxLayout()
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Run Simulation")
        self.run_btn.clicked.connect(self.run_simulation)
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
        self.stop_btn = QtWidgets.QPushButton("Stop Simulation")
        self.stop_btn.clicked.connect(self.stop_simulation)
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
        """List available subjects in the project directory."""
        try:
            # Get project directory from environment variable
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            if not project_dir:
                return
            
            # Clear existing items
            self.subject_list.clear()
            self.eeg_net_combo.clear()  # Clear existing EEG nets
            
            # Look for subjects in the derivatives/SimNIBS directory
            simnibs_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS')
            if not os.path.exists(simnibs_dir):
                return
            
            # Find all subject directories that have m2m_ directories
            subjects = []
            for subject_dir in os.listdir(simnibs_dir):
                if subject_dir.startswith('sub-'):
                    subject_id = subject_dir[4:]  # Remove 'sub-' prefix
                    m2m_dir = os.path.join(simnibs_dir, subject_dir, f'm2m_{subject_id}')
                    if os.path.isdir(m2m_dir):
                        subjects.append(subject_id)
                        
                        # Check for EEG nets in eeg_positions directory
                        eeg_dir = os.path.join(m2m_dir, 'eeg_positions')
                        if os.path.isdir(eeg_dir):
                            for net_file in os.listdir(eeg_dir):
                                if net_file.endswith('.csv'):
                                    if net_file not in [self.eeg_net_combo.itemText(i) for i in range(self.eeg_net_combo.count())]:
                                        self.eeg_net_combo.addItem(net_file)
            
            # Sort subjects using natural sorting
            def natural_sort_key(s):
                # Split the string into parts: numbers and non-numbers
                import re
                return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]
            
            subjects.sort(key=natural_sort_key)
            
            # Add subjects to list widget
            for subject in subjects:
                self.subject_list.addItem(subject)
            
            # If no nets found, add default
            if self.eeg_net_combo.count() == 0:
                self.eeg_net_combo.addItem("EGI_template.csv")
            
        except Exception as e:
            print(f"Error listing subjects: {str(e)}")
    
    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()
    
    def clear_subject_selection(self):
        """Clear the selection in the subject list."""
        self.subject_list.clearSelection()
    
    def clear_montage_selection(self):
        """Clear the selection in the montage list."""
        self.montage_list.clearSelection()
    
    def refresh_flex_search_list(self):
        """Refresh the list of available flex-search outputs based on selected subjects."""
        try:
            self.flex_search_list.clear()
            
            # Get project directory
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            if not project_dir:
                return
            
            # Get selected subjects to filter flex-search outputs
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            
            # Only show flex-search outputs if subjects are selected (similar to montage behavior)
            if not selected_subjects:
                return
            
            # Search for flex-search outputs
            simnibs_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS')
            
            if os.path.exists(simnibs_dir):
                # Iterate through selected subject directories only
                for subject_id in selected_subjects:
                    subject_dir = f"sub-{subject_id}"
                    subject_path = os.path.join(simnibs_dir, subject_dir)
                    
                    if os.path.exists(subject_path):
                        flex_search_dir = os.path.join(subject_path, 'flex-search')
                        
                        if os.path.exists(flex_search_dir):
                            # Look for search directories
                            for search_name in os.listdir(flex_search_dir):
                                search_dir = os.path.join(flex_search_dir, search_name)
                                mapping_file = os.path.join(search_dir, 'electrode_mapping.json')
                                
                                if os.path.isdir(search_dir) and os.path.exists(mapping_file):
                                    # Read the mapping file to get details
                                    try:
                                        with open(mapping_file, 'r') as f:
                                            mapping_data = json.load(f)
                                        
                                        # Get EEG net if available
                                        eeg_net = mapping_data.get('eeg_net', 'Unknown Net')
                                        n_electrodes = len(mapping_data.get('optimized_positions', []))
                                        
                                        # Create display label
                                        label = f"{subject_id} | {search_name} | {n_electrodes} electrodes | {eeg_net}"
                                        
                                        # Add item to list
                                        item = QtWidgets.QListWidgetItem(label)
                                        item.setData(QtCore.Qt.UserRole, {
                                            'subject_id': subject_id,
                                            'search_name': search_name,
                                            'mapping_file': mapping_file,
                                            'mapping_data': mapping_data
                                        })
                                        self.flex_search_list.addItem(item)
                                        
                                    except Exception as e:
                                        print(f"Error reading flex-search mapping file {mapping_file}: {e}")
                                        
        except Exception as e:
            print(f"Error refreshing flex-search list: {str(e)}")
    
    def clear_flex_search_selection(self):
        """Clear all flex-search selections."""
        self.flex_search_list.clearSelection()
    
    def on_simulation_type_changed(self):
        """Handle changes between Montage and Flex simulation modes."""
        is_montage_mode = self.sim_type_montage.isChecked()
        
        # Show/hide montage-related UI elements
        self.montage_container.setVisible(is_montage_mode)
        
        # Enable/disable (grey out) simulation mode and EEG net controls instead of hiding
        for widget in self.sim_mode_layout_widgets:
            widget.setEnabled(is_montage_mode)
        self.eeg_net_combo.setEnabled(is_montage_mode)
        self.eeg_net_label.setEnabled(is_montage_mode)
        
        # Show/hide flex-search-related UI elements
        self.flex_search_container.setVisible(not is_montage_mode)
        
        # Update window title or status
        if is_montage_mode:
            self.update_output("Switched to Montage Simulation mode", 'info')
            self.update_montage_list()  # Refresh montage list
        else:
            self.update_output("Switched to Flex-Search Simulation mode", 'info')
            self.refresh_flex_search_list()  # Refresh flex-search list

    def initialize_ui_state(self):
        """Initialize UI state without printing messages."""
        is_montage_mode = self.sim_type_montage.isChecked()
        
        # Show/hide montage-related UI elements
        self.montage_container.setVisible(is_montage_mode)
        
        # Enable/disable (grey out) simulation mode and EEG net controls instead of hiding
        for widget in self.sim_mode_layout_widgets:
            widget.setEnabled(is_montage_mode)
        self.eeg_net_combo.setEnabled(is_montage_mode)
        self.eeg_net_label.setEnabled(is_montage_mode)
        
        # Show/hide flex-search-related UI elements
        self.flex_search_container.setVisible(not is_montage_mode)

    def ensure_montage_file_exists(self, project_dir):
        """Ensure the montage file exists with proper structure."""
        ti_csc_dir = os.path.join(project_dir, 'ti-csc')
        config_dir = os.path.join(ti_csc_dir, 'config')
        montage_file = os.path.join(config_dir, 'montage_list.json')
        
        # Create directories if they don't exist
        os.makedirs(config_dir, exist_ok=True)
        
        # Set directory permissions
        os.chmod(ti_csc_dir, 0o777)
        os.chmod(config_dir, 0o777)
        
        # Create montage file if it doesn't exist
        if not os.path.exists(montage_file):
            initial_content = {
                "nets": {
                    "EGI_template.csv": {
                        "uni_polar_montages": {},
                        "multi_polar_montages": {}
                    }
                }
            }
            with open(montage_file, 'w') as f:
                json.dump(initial_content, f, indent=4)
            os.chmod(montage_file, 0o777)
        else:
            # Ensure correct permissions
            os.chmod(montage_file, 0o777)
        
        return montage_file

    def update_montage_list(self, checked=None):
        """Update the list of available montages."""
        try:
            # Get project directory from environment variable
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            if not project_dir:
                return
            # Clear existing items
            self.montage_list.clear()
            # Ensure montage file exists and get its path
            montage_file = self.ensure_montage_file_exists(project_dir)
            # Load montages from montage_list.json
            with open(montage_file, 'r') as f:
                montage_data = json.load(f)
            # Get the current EEG net
            current_net = self.eeg_net_combo.currentText() or "EGI_template.csv"
            # Get montages for the current net
            if "nets" in montage_data and current_net in montage_data["nets"]:
                net_montages = montage_data["nets"][current_net]
                # Add unipolar montages if in unipolar mode
                if self.sim_mode_unipolar.isChecked() and "uni_polar_montages" in net_montages:
                    for montage_name, pairs in net_montages["uni_polar_montages"].items():
                        label_html = self._format_montage_label_html(montage_name, pairs, is_unipolar=True)
                        item = QtWidgets.QListWidgetItem()
                        item.setData(QtCore.Qt.UserRole, montage_name)  # Store the real name for selection logic
                        self.montage_list.addItem(item)
                        label_widget = QtWidgets.QLabel()
                        label_widget.setTextFormat(QtCore.Qt.RichText)
                        label_widget.setText(label_html)
                        label_widget.setStyleSheet("QLabel { padding: 2px 4px; font-size: 13px; }")
                        self.montage_list.setItemWidget(item, label_widget)
                        item.setSizeHint(label_widget.sizeHint())
                # Add multipolar montages if in multipolar mode
                if self.sim_mode_multipolar.isChecked() and "multi_polar_montages" in net_montages:
                    for montage_name, pairs in net_montages["multi_polar_montages"].items():
                        label_html = self._format_montage_label_html(montage_name, pairs, is_unipolar=False)
                        item = QtWidgets.QListWidgetItem()
                        item.setData(QtCore.Qt.UserRole, montage_name)
                        self.montage_list.addItem(item)
                        label_widget = QtWidgets.QLabel()
                        label_widget.setTextFormat(QtCore.Qt.RichText)
                        label_widget.setText(label_html)
                        label_widget.setStyleSheet("QLabel { padding: 2px 4px; font-size: 13px; }")
                        self.montage_list.setItemWidget(item, label_widget)
                        item.setSizeHint(label_widget.sizeHint())
        except Exception as e:
            print(f"Error updating montage list: {str(e)}")
        # Update the electrode inputs view
        if checked is not None:
            if checked:  # Unipolar selected
                self.electrode_stacked_widget.setCurrentIndex(0)
            else:  # Multipolar selected
                self.electrode_stacked_widget.setCurrentIndex(1)
    
    def _format_montage_label_html(self, montage_name, pairs, is_unipolar=True):
        """Format montage label for the list widget using HTML for a professional look."""
        if not pairs or not isinstance(pairs, list):
            return f"<b>{montage_name}</b>"
        channel_labels = []
        for idx, pair in enumerate(pairs):
            if isinstance(pair, list) and len(pair) == 2:
                ch_num = f"ch{idx+1}:"
                e1 = f"<span style='color:#55aaff;'>{pair[0]}</span>"
                e2 = f"<span style='color:#ff5555;'>{pair[1]}</span>"
                channel = f"{ch_num} {e1} <b>↔</b> {e2}"
                channel_labels.append(channel)
        return f"<b>{montage_name}</b>  |  " + "   +   ".join(channel_labels)
    
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
        
        try:
            # Get selected subjects
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            if not selected_subjects:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one subject.")
                return
            
            # Check simulation mode and validate selections
            is_montage_mode = self.sim_type_montage.isChecked()
            
            if is_montage_mode:
                # Montage simulation mode
                selected_montages = [item.data(QtCore.Qt.UserRole) for item in self.montage_list.selectedItems()]
                if not selected_montages:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one montage.")
                    return
                selected_flex_searches = []  # No flex-search in montage mode
                flex_montages = []
            else:
                # Flex-search simulation mode
                selected_flex_searches = [item.data(QtCore.Qt.UserRole) for item in self.flex_search_list.selectedItems()]
                if not selected_flex_searches:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one flex-search output.")
                    return
                selected_montages = []  # No regular montages in flex mode
                
                # Process flex-search outputs into montage format
                flex_montages = []
                flex_montages_by_subject = {}  # Store flex montages by subject
                
                # Check which electrode types are selected
                use_mapped = self.flex_use_mapped.isChecked()
                use_optimized = self.flex_use_optimized.isChecked()
                
                # Validate that at least one option is selected
                if not use_mapped and not use_optimized:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one electrode type (Mapped or Optimized).")
                    return
                
                for flex_data in selected_flex_searches:
                    subject_id = flex_data['subject_id']
                    search_name = flex_data['search_name']
                    mapping_data = flex_data['mapping_data']
                    
                    # Initialize subject list if needed
                    if subject_id not in flex_montages_by_subject:
                        flex_montages_by_subject[subject_id] = []
                    
                    # Create montage entries based on selection
                    if use_mapped:
                        mapped_positions = mapping_data['mapped_positions']
                        mapped_labels = mapping_data['mapped_labels']
                        eeg_net_from_json = mapping_data.get('eeg_net', 'EGI_template.csv')
                        
                        # Create montage structure for mapped electrodes
                        if len(mapped_positions) >= 4:  # Need at least 4 electrodes for TI
                            montage_name = f"flex_{search_name}_mapped"
                            # TI requires 2 pairs of electrodes
                            montage_data = {
                                'name': montage_name,
                                'type': 'flex_mapped',
                                'subject_id': subject_id,
                                'eeg_net': eeg_net_from_json,  # Use the EEG net from the JSON
                                'electrode_labels': mapped_labels[:4],
                                'pairs': [[mapped_labels[0], mapped_labels[1]], [mapped_labels[2], mapped_labels[3]]]
                            }
                            flex_montages.append(montage_data)
                            flex_montages_by_subject[subject_id].append(montage_data)
                    
                    if use_optimized:
                        optimized_positions = mapping_data['optimized_positions']
                        
                        # Create montage structure for optimized electrodes
                        if len(optimized_positions) >= 4:  # Need at least 4 electrodes for TI
                            montage_name = f"flex_{search_name}_optimized"
                            # TI requires 2 pairs of electrodes (using XYZ coordinates)
                            montage_data = {
                                'name': montage_name,
                                'type': 'flex_optimized',
                                'subject_id': subject_id,
                                'electrode_positions': optimized_positions[:4],
                                'pairs': [[optimized_positions[0], optimized_positions[1]], 
                                         [optimized_positions[2], optimized_positions[3]]]
                            }
                            flex_montages.append(montage_data)
                            flex_montages_by_subject[subject_id].append(montage_data)
            
            # Check if simulation directories already exist
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            for subject_id in selected_subjects:
                bids_subject_id = f"sub-{subject_id}"
                for montage_name in selected_montages:
                    # Get montage name without path if it's a file path
                    montage_base = os.path.splitext(os.path.basename(montage_name))[0]
                    sim_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', 
                                         bids_subject_id, 'Simulations', montage_base)
                    if os.path.exists(sim_dir):
                        if not confirm_overwrite(self, sim_dir, "simulation output directory"):
                            self.update_output("Simulation cancelled: Output directory already exists.")
                            return
            
            # Get simulation parameters
            conductivity = self.sim_type_combo.currentData()  # Get conductivity from combo box
            
            if is_montage_mode:
                sim_mode = "U" if self.sim_mode_unipolar.isChecked() else "M"
                eeg_net = self.eeg_net_combo.currentText()
            else:
                # For flex mode, always use TI pipeline (main-TI.sh) since we're doing temporal interference
                sim_mode = "FLEX_TI"  # Special mode for flex-search TI simulations
                eeg_net = "flex_mode"  # Placeholder since EEG net is determined per montage
            
            # Get current values and convert to Amperes (from mA)
            try:
                current_ma_1 = float(self.current_input_1.text() or "1.0")
                current_ma_2 = float(self.current_input_2.text() or "1.0")
                if current_ma_1 <= 0 or current_ma_2 <= 0:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Current values must be greater than 0 mA.")
                    return
                current = f"{current_ma_1/1000.0},{current_ma_2/1000.0}"
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid current values in mA for both channels.")
                return
            
            electrode_shape = "rect" if self.electrode_shape_rect.isChecked() else "ellipse"
            dimensions = self.dimensions_input.text() or "8,8"  # Default to 8,8 if empty
            thickness = self.thickness_input.text() or "8"  # Default to 8 if empty
            
            # Validate parameters
            if not all([conductivity, sim_mode, eeg_net]):
                QtWidgets.QMessageBox.warning(self, "Warning", "Please fill in all required simulation parameters.")
                return
            
            # Validate numeric inputs
            try:
                dim_parts = dimensions.split(',')
                if len(dim_parts) != 2 or not all(dim_parts):
                    raise ValueError("Invalid dimensions format")
                float(dim_parts[0])
                float(dim_parts[1])
                float(thickness)
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid numeric values for dimensions and thickness.")
                return
            
            # Show confirmation dialog with details
            if is_montage_mode:
                details = (f"This will run MONTAGE simulations for:\n\n"
                          f"• {len(selected_subjects)} subject(s)\n"
                          f"• {len(selected_montages)} montage(s)\n\n"
                          f"Parameters:\n"
                          f"• Simulation type: {conductivity}\n"
                          f"• Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}\n"
                          f"• EEG Net: {eeg_net}\n"
                          f"• Current Channel 1: {current_ma_1} mA\n"
                          f"• Current Channel 2: {current_ma_2} mA\n"
                          f"• Electrode shape: {electrode_shape}\n"
                          f"• Dimensions: {dimensions} mm\n"
                          f"• Thickness: {thickness} mm")
            else:
                details = (f"This will run FLEX-SEARCH simulations for:\n\n"
                          f"• {len(selected_subjects)} subject(s)\n"
                          f"• {len(flex_montages)} flex-search montage(s)\n")
                
                # Show which electrode types are selected
                if use_mapped and use_optimized:
                    details += "• Using both mapped electrode positions and optimized XYZ coordinates\n"
                elif use_mapped:
                    details += "• Using mapped electrode positions (will use EEG net from optimization)\n"
                elif use_optimized:
                    details += "• Using optimized XYZ coordinates (no EEG net required)\n"
                
                details += (f"\nParameters:\n"
                          f"• Simulation type: {conductivity}\n"
                          f"• Current Channel 1: {current_ma_1} mA\n"
                          f"• Current Channel 2: {current_ma_2} mA\n"
                          f"• Electrode shape: {electrode_shape}\n"
                          f"• Dimensions: {dimensions} mm\n"
                          f"• Thickness: {thickness} mm")
            
            if not ConfirmationDialog.confirm(
                self,
                title="Confirm Simulation",
                message="Are you sure you want to start the simulation?",
                details=details
            ):
                return
            
            # Prepare environment variables
            env = os.environ.copy()
            env['DIRECT_MODE'] = 'true'
            env['PROJECT_DIR_NAME'] = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            
            # Build command
            cmd = [
                'bash',
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'CLI', 'simulator.sh'),
                '--run-direct'
            ]
            
            # Set environment variables for simulator.sh (match CLI script expectations)
            env['SUBJECT_CHOICES'] = ','.join(selected_subjects)  # CLI expects SUBJECT_CHOICES
            env['SIM_TYPE'] = 'TI'  # CLI expects SIM_TYPE (always TI for this GUI)
            env['CONDUCTIVITY'] = conductivity
            env['SIM_MODE'] = sim_mode
            env['EEG_NET'] = eeg_net
            
            # For montage mode with multiple subjects, provide EEG_NETS (comma-separated)
            if is_montage_mode:
                # For now, use the same EEG net for all subjects
                # In the future, this could be made more sophisticated to support different nets per subject
                eeg_nets_list = [eeg_net] * len(selected_subjects)
                env['EEG_NETS'] = ','.join(eeg_nets_list)
            env['CURRENT'] = current  # Now in Amperes, comma-separated for two channels
            env['ELECTRODE_SHAPE'] = electrode_shape
            env['DIMENSIONS'] = dimensions
            env['THICKNESS'] = thickness
            
            if is_montage_mode:
                # Montage simulation mode
                env['SELECTED_MONTAGES'] = ' '.join(selected_montages)
                env['SIMULATION_FRAMEWORK'] = 'montage'  # CLI expects SIMULATION_FRAMEWORK
            else:
                # Flex-search simulation mode
                env['SELECTED_MONTAGES'] = ''  # No regular montages
                env['SIMULATION_FRAMEWORK'] = 'flex'  # CLI expects SIMULATION_FRAMEWORK
                
                # Create a temporary JSON file with flex montage data
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
                    json.dump(flex_montages, tf)
                    env['FLEX_MONTAGES_FILE'] = tf.name
            
            # Debug output
            self.update_output(f"Running in direct execution mode from GUI")
            self.update_output(f"Running {env['SIMULATION_FRAMEWORK']} simulation with:")
            self.update_output(f"- Subjects: {env['SUBJECT_CHOICES']}")
            self.update_output(f"- Simulation type: {env['CONDUCTIVITY']}")
            
            if is_montage_mode:
                self.update_output(f"- Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}")
                self.update_output(f"- EEG Net: {env['EEG_NET']}")
                self.update_output(f"- Montages: {', '.join(selected_montages)}")
            else:
                self.update_output(f"- Flex-search montages: {', '.join([fm['name'] for fm in flex_montages])}")
                
                # Determine electrode types based on checkboxes
                electrode_types = []
                if self.flex_use_mapped.isChecked():
                    electrode_types.append("mapped")
                if self.flex_use_optimized.isChecked():
                    electrode_types.append("optimized")
                electrode_type_text = ", ".join(electrode_types) if electrode_types else "none"
                
                self.update_output(f"- Electrode type: {electrode_type_text}")
            
            self.update_output(f"- Current Channel 1: {current_ma_1} mA")
            self.update_output(f"- Current Channel 2: {current_ma_2} mA")
            self.update_output(f"- Electrode shape: {electrode_shape}")
            self.update_output(f"- Dimensions: {dimensions} mm")
            self.update_output(f"- Thickness: {thickness} mm")
            
            # Set tab as busy
            if hasattr(self, 'parent') and self.parent:
                self.parent.set_tab_busy(self, True, stop_btn=self.stop_btn)
            
            # Initialize report generator for this simulation session
            self.simulation_session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            project_dir_path = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            self.report_generator = get_simulation_report_generator(project_dir_path, self.simulation_session_id)
            
            # Add simulation parameters to report (including custom conductivities)
            self.report_generator.add_simulation_parameters(
                conductivity, sim_mode, eeg_net, current_ma_1, current_ma_2, False, 
                conductivities=self._get_conductivities_for_report()
            )
            
            # Add electrode parameters to report
            dim_parts = dimensions.split(',')
            self.report_generator.add_electrode_parameters(
                electrode_shape, [float(dim_parts[0]), float(dim_parts[1])], float(thickness)
            )
            
            # Add subjects to report
            for subject_id in selected_subjects:
                bids_subject_id = f"sub-{subject_id}"
                m2m_path = os.path.join(project_dir_path, 'derivatives', 'SimNIBS', 
                                      bids_subject_id, f'm2m_{subject_id}')
                self.report_generator.add_subject(subject_id, m2m_path, 'processing')
            
            # Add montages to report
            montage_type = 'unipolar' if sim_mode == 'U' else 'multipolar'
            
            # Load actual electrode pairs from montage file
            montage_file = self.ensure_montage_file_exists(project_dir_path)
            try:
                with open(montage_file, 'r') as f:
                    montage_data = json.load(f)
            except:
                montage_data = {"nets": {}}
            
            for montage_name in selected_montages:
                # Try to get actual electrode pairs from the montage file
                electrode_pairs = [['E1', 'E2']]  # Default fallback
                
                # Look for the montage in the appropriate net and type
                net_type = "uni_polar_montages" if sim_mode == 'U' else "multi_polar_montages"
                
                if ("nets" in montage_data and 
                    eeg_net in montage_data["nets"] and 
                    net_type in montage_data["nets"][eeg_net] and 
                    montage_name in montage_data["nets"][eeg_net][net_type]):
                    electrode_pairs = montage_data["nets"][eeg_net][net_type][montage_name]
                
                # Use keyword arguments for consistency with updated method signature
                self.report_generator.add_montage(
                    name=montage_name,  # Use 'name' keyword argument for consistency
                    electrode_pairs=electrode_pairs,
                    montage_type=montage_type
                )
            
            # Disable UI controls during simulation
            self.disable_controls()
            self.run_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.simulation_running = True
            
            # Create and start the thread
            self.simulation_process = SimulationThread(cmd, env)
            self.simulation_process.output_signal.connect(self.update_output)
            self.simulation_process.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
            self.simulation_process.finished.connect(self.simulation_finished)
            self.simulation_process.start()
            
        except Exception as e:
            self.update_output(f"Error starting simulation: {str(e)}")
            self.simulation_finished()
    
    def simulation_finished(self):
        """Handle simulation completion."""
        # Clear parent tab's busy state
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False)
        
        self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">✅ Simulation process completed ✅</span></div>')
        self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
        
        # Automatically generate simulation report
        self.auto_generate_simulation_report()
        
        self.simulation_running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run Simulation")
        self.stop_btn.setEnabled(False)
        
        # Re-enable all controls
        self.enable_controls()
    
    def auto_generate_simulation_report(self):
        """Automatically generate simulation report after completion."""
        if not self.report_generator:
            return
        
        try:
            self.update_output("Generating simulation report...", 'info')
            
            # Update subject statuses to completed
            for subject in self.report_generator.report_data['subjects']:
                self.report_generator.update_subject_status(subject['subject_id'], 'completed')
            
            # Generate the report
            report_path = self.report_generator.generate_report()
            
            if report_path and os.path.exists(report_path):
                self.update_output(f"✅ Simulation report generated: {report_path}", 'success')
                
                # Report generated successfully - no automatic browser opening
                self.update_output("📊 Open the report file in your browser to view detailed results", 'info')
            else:
                self.update_output("⚠️ Report generation completed but file not found", 'warning')
                
        except Exception as e:
            self.update_output(f"❌ Error generating simulation report: {str(e)}", 'error')
    
    def disable_controls(self):
        """Disable all controls except the stop button."""
        # Disable all buttons
        self.list_subjects_btn.setEnabled(False)
        self.select_all_subjects_btn.setEnabled(False)
        self.clear_subject_selection_btn.setEnabled(False)
        self.list_montages_btn.setEnabled(False)
        self.clear_montage_selection_btn.setEnabled(False)
        self.add_new_montage_btn.setEnabled(False)
        self.remove_montage_btn.setEnabled(False)
        
        # Disable all inputs
        self.sim_type_combo.setEnabled(False)
        self.sim_type_montage.setEnabled(False)
        self.sim_type_flex.setEnabled(False)
        self.eeg_net_combo.setEnabled(False)
        self.sim_mode_unipolar.setEnabled(False)
        self.sim_mode_multipolar.setEnabled(False)
        self.current_input_1.setEnabled(False)
        self.current_input_2.setEnabled(False)
        self.electrode_shape_rect.setEnabled(False)
        self.electrode_shape_ellipse.setEnabled(False)
        self.dimensions_input.setEnabled(False)
        self.thickness_input.setEnabled(False)
        
        # Disable list widgets
        self.subject_list.setEnabled(False)
        self.montage_list.setEnabled(False)
        self.flex_search_list.setEnabled(False)
        
        # Disable flex-search controls
        self.refresh_flex_btn.setEnabled(False)
        self.clear_flex_selection_btn.setEnabled(False)
        self.flex_use_mapped.setEnabled(False)
        self.flex_use_optimized.setEnabled(False)
    
    def enable_controls(self):
        """Re-enable all controls."""
        # Enable all buttons
        self.list_subjects_btn.setEnabled(True)
        self.select_all_subjects_btn.setEnabled(True)
        self.clear_subject_selection_btn.setEnabled(True)
        self.list_montages_btn.setEnabled(True)
        self.clear_montage_selection_btn.setEnabled(True)
        self.add_new_montage_btn.setEnabled(True)
        self.remove_montage_btn.setEnabled(True)
        
        # Enable all inputs
        self.sim_type_combo.setEnabled(True)
        self.sim_type_montage.setEnabled(True)
        self.sim_type_flex.setEnabled(True)
        self.eeg_net_combo.setEnabled(True)
        self.sim_mode_unipolar.setEnabled(True)
        self.sim_mode_multipolar.setEnabled(True)
        self.current_input_1.setEnabled(True)
        self.current_input_2.setEnabled(True)
        self.electrode_shape_rect.setEnabled(True)
        self.electrode_shape_ellipse.setEnabled(True)
        self.dimensions_input.setEnabled(True)
        self.thickness_input.setEnabled(True)
        
        # Enable list widgets
        self.subject_list.setEnabled(True)
        self.montage_list.setEnabled(True)
        self.flex_search_list.setEnabled(True)
        
        # Enable flex-search controls
        self.refresh_flex_btn.setEnabled(True)
        self.clear_flex_selection_btn.setEnabled(True)
        self.flex_use_mapped.setEnabled(True)
        self.flex_use_optimized.setEnabled(True)
    
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
            
            # Clear parent tab's busy state
            if hasattr(self, 'parent') and self.parent:
                self.parent.set_tab_busy(self, False)
            
            # Re-enable all controls
            self.enable_controls()
    
    def validate_electrode(self, electrode):
        """Validate electrode name is not empty."""
        return bool(electrode and electrode.strip())
    
    def validate_current(self, current):
        """Validate current value is a number."""
        try:
            float(current)
            return True
        except ValueError:
            return False

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
        self.output_console.append(formatted_text)
        self.output_console.ensureCursorVisible()
        QtWidgets.QApplication.processEvents()

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
            
            # Get project directory
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            
            # Ensure montage file exists and get its path
            montage_file = self.ensure_montage_file_exists(project_dir)
            
            # Load existing montage data
            with open(montage_file, 'r') as f:
                montage_data_file = json.load(f)
            
            # Ensure the target net exists in the structure
            target_net = montage_data["target_net"]
            if "nets" not in montage_data_file:
                montage_data_file["nets"] = {}
            if target_net not in montage_data_file["nets"]:
                montage_data_file["nets"][target_net] = {
                    "uni_polar_montages": {},
                    "multi_polar_montages": {}
                }
            
            # Add the new montage to the appropriate section
            montage_type = "uni_polar_montages" if montage_data["is_unipolar"] else "multi_polar_montages"
            
            # Store the montage under the correct net and type
            montage_data_file["nets"][target_net][montage_type][montage_data["name"]] = montage_data["electrode_pairs"]
            
            # Save the updated montage data
            with open(montage_file, 'w') as f:
                json.dump(montage_data_file, f, indent=4)
            
            # Format pairs for display
            pairs_text = ", ".join([f"{pair[0]}↔{pair[1]}" for pair in montage_data["electrode_pairs"]])
            
            self.update_output(f"Added {montage_type.split('_')[0]} montage '{montage_data['name']}' for net {target_net} with pairs: {pairs_text}")
            self.update_output(f"Montage saved to: {montage_file}")
            
            # Refresh the list of montages
            self.update_montage_list()

    def remove_selected_montage(self):
        """Remove the selected montage from the montage list file."""
        try:
            # Get selected montage
            selected_items = self.montage_list.selectedItems()
            if not selected_items:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a montage to remove.")
                return
            
            # Get the montage name
            montage_name = selected_items[0].text()
            
            # Confirm deletion
            reply = QtWidgets.QMessageBox.question(
                self, 
                "Confirm Deletion",
                f"Are you sure you want to delete the montage '{montage_name}'?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # Get project directory
                project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
                
                # Ensure montage file exists and get its path
                montage_file = self.ensure_montage_file_exists(project_dir)
                
                # Load existing montage data
                with open(montage_file, 'r') as f:
                    montage_data = json.load(f)
                
                # Get current net and mode
                current_net = self.eeg_net_combo.currentText()
                montage_type = "uni_polar_montages" if self.sim_mode_unipolar.isChecked() else "multi_polar_montages"
                
                # Remove the montage if it exists
                if (current_net in montage_data["nets"] and 
                    montage_type in montage_data["nets"][current_net] and 
                    montage_name in montage_data["nets"][current_net][montage_type]):
                    
                    del montage_data["nets"][current_net][montage_type][montage_name]
                    
                    # Save the updated montage data
                    with open(montage_file, 'w') as f:
                        json.dump(montage_data, f, indent=4)
                    
                    self.update_output(f"Removed montage '{montage_name}' from {montage_type}")
                    self.update_montage_list()
                else:
                    QtWidgets.QMessageBox.warning(self, "Warning", f"Montage '{montage_name}' not found.")
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Error removing montage: {str(e)}")
            print(f"Detailed error: {str(e)}")  # For debugging

    def show_sim_type_help(self):
        """Show help information about simulation types."""
        help_text = """
        <h3>Simulation Types (Anisotropy Types)</h3>
        
        <b>Isotropic (scalar):</b><br>
        - Uses uniform conductivity values for all tissue types<br>
        - Faster computation but less accurate for anisotropic tissues<br>
        - Recommended for initial testing and quick results<br>
        - Default option for basic simulations<br><br>
        
        <b>Anisotropic (vn):</b><br>
        - Uses volume-normalized anisotropic conductivities<br>
        - Tensors are normalized to have the same trace and re-scaled according to their respective tissue conductivity<br>
        - Recommended for simulations with anisotropic conductivities<br>
        - Based on Opitz et al., 2011<br><br>
        
        <b>Anisotropic (dir):</b><br>
        - Uses direct anisotropic conductivity<br>
        - Does not normalize individual tensors<br>
        - Re-scales tensors according to the mean gray and white matter conductivities<br>
        - Based on Opitz et al., 2011<br><br>
        
        <b>Anisotropic (mc):</b><br>
        - Uses isotropic, varying conductivities<br>
        - Assigns to each voxel a conductivity value related to the volume of the tensors<br>
        - Obtained from the direct approach<br>
        - Based on Opitz et al., 2011<br><br>
        
        <i>Note: All options other than 'scalar' require conductivity tensors acquired from diffusion weighted images and processed with dwi2cond.</i><br><br>
        
        For full documentation, see the SimNIBS website.
        """
        
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Simulation Type Help")
        msg.setTextFormat(QtCore.Qt.RichText)
        msg.setText(help_text)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2a2a2a;
                color: white;
            }
            QLabel {
                min-width: 600px;
                max-width: 800px;
                color: white;
            }
        """)
        
        # Set the message box to be resizable
        msg.setWindowFlags(msg.windowFlags() | QtCore.Qt.WindowMaximizeButtonHint)
        
        # Set a larger default size
        msg.setMinimumSize(700, 600)
        
        # Enable text wrapping for the label
        for child in msg.findChildren(QtWidgets.QLabel):
            child.setWordWrap(True)
        
        # Adjust the size to fit content
        msg.adjustSize()
        
        msg.exec_()

    def validate_inputs(self):
        """Validate all input parameters before running the simulation."""
        # Check if any subjects are selected
        if not self.subject_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one subject.")
            return False
            
        # Check if any montages are selected
        if not self.montage_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one montage.")
            return False
            
        # Validate current values
        try:
            current_1 = float(self.current_input_1.text() or "1.0")
            current_2 = float(self.current_input_2.text() or "1.0")
            if current_1 <= 0 or current_2 <= 0:
                QtWidgets.QMessageBox.warning(self, "Warning", "Current values must be greater than 0 mA.")
                return False
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid current values in mA for both channels.")
            return False
            
        # Validate dimensions
        try:
            dimensions = self.dimensions_input.text() or "8,8"
            dim_parts = dimensions.split(',')
            if len(dim_parts) != 2:
                raise ValueError("Invalid dimensions format")
            float(dim_parts[0])
            float(dim_parts[1])
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid dimensions in format 'x,y' (e.g., '8,8').")
            return False
            
        # Validate thickness
        try:
            thickness = float(self.thickness_input.text() or "8")
            if thickness <= 0:
                QtWidgets.QMessageBox.warning(self, "Warning", "Thickness must be greater than 0 mm.")
                return False
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a valid thickness value in mm.")
            return False
            
        # Validate EEG net selection
        if not self.eeg_net_combo.currentText():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select an EEG net.")
            return False
            
        return True

    def show_conductivity_editor(self):
        """Show the conductivity editor dialog."""
        dialog = ConductivityEditorDialog(self, self.custom_conductivities)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.custom_conductivities = dialog.get_conductivities()
    
    def _get_conductivities_for_report(self):
        """Get conductivity values formatted for the simulation report."""
        # Start with default values
        temp_gen = get_simulation_report_generator("", "")
        conductivities = temp_gen._get_default_conductivities()
        
        # Override with any custom values
        for tissue_num, custom_value in self.custom_conductivities.items():
            if tissue_num in conductivities:
                conductivities[tissue_num]['conductivity'] = custom_value
                conductivities[tissue_num]['reference'] = 'Custom (User Modified)'
            else:
                # Add new custom tissue
                conductivities[tissue_num] = {
                    'name': f'Custom Tissue {tissue_num}',
                    'conductivity': custom_value,
                    'reference': 'Custom (User Defined)'
                }
        
        return conductivities

    def _format_montage_label(self, montage_name, pairs, is_unipolar=True):
        """Format montage label for the list widget: montage_name: ch1:X<->Y + ch2:A<->B (+ ch3/ch4...)"""
        if not pairs or not isinstance(pairs, list):
            return montage_name
        channel_labels = []
        for idx, pair in enumerate(pairs):
            if isinstance(pair, list) and len(pair) == 2:
                channel = f"ch{idx+1}:{pair[0]}<-> {pair[1]}"
                channel_labels.append(channel)
        return f"{montage_name}: " + " + ".join(channel_labels)

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
        self.resize(800, 500)  # Made wider to accommodate the side panel
        
        # Create main horizontal layout
        main_layout = QtWidgets.QHBoxLayout(self)
        
        # Left side (original form)
        left_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(left_widget)
        
        # Create form layout for better organization
        form_layout = QtWidgets.QFormLayout()
        
        # Montage name
        self.name_input = QtWidgets.QLineEdit()
        form_layout.addRow("Montage Name:", self.name_input)
        
        # Target EEG Net selection with Show Electrodes button
        net_layout = QtWidgets.QHBoxLayout()
        self.net_combo = QtWidgets.QComboBox()
        # Copy items from parent's EEG net combo
        if self.parent and hasattr(self.parent, 'eeg_net_combo'):
            for i in range(self.parent.eeg_net_combo.count()):
                self.net_combo.addItem(self.parent.eeg_net_combo.itemText(i))
        # Set current net to match parent's selection
        if self.parent and hasattr(self.parent, 'eeg_net_combo'):
            current_net = self.parent.eeg_net_combo.currentText()
            index = self.net_combo.findText(current_net)
            if index >= 0:
                self.net_combo.setCurrentIndex(index)
        
        self.show_electrodes_btn = QtWidgets.QPushButton("Show Electrodes")
        self.show_electrodes_btn.clicked.connect(self.toggle_electrode_list)
        net_layout.addWidget(self.net_combo)
        net_layout.addWidget(self.show_electrodes_btn)
        form_layout.addRow("Target EEG Net:", net_layout)
        
        # Add form layout to main layout
        layout.addLayout(form_layout)
        
        # Simulation mode (Unipolar/Multipolar)
        mode_group = QtWidgets.QGroupBox("Montage Type")
        mode_layout = QtWidgets.QHBoxLayout(mode_group)
        self.mode_unipolar = QtWidgets.QRadioButton("Unipolar")
        self.mode_multipolar = QtWidgets.QRadioButton("Multipolar")
        self.mode_unipolar.setChecked(True)  # Default to unipolar
        mode_layout.addWidget(self.mode_unipolar)
        mode_layout.addWidget(self.mode_multipolar)
        layout.addWidget(mode_group)
        
        # Create a stacked widget for electrode inputs
        self.electrode_stack = QtWidgets.QStackedWidget()
        
        # Unipolar electrode pairs (two pairs)
        uni_widget = QtWidgets.QWidget()
        uni_layout = QtWidgets.QVBoxLayout(uni_widget)
        
        # Add a label for the unipolar electrode section
        uni_label = QtWidgets.QLabel("Unipolar Electrode Pairs:")
        uni_label.setStyleSheet("font-weight: bold;")
        uni_layout.addWidget(uni_label)
        
        # Pair 1
        uni_pair1_layout = QtWidgets.QHBoxLayout()
        self.uni_pair1_label = QtWidgets.QLabel("Pair 1:")
        self.uni_pair1_e1 = QtWidgets.QLineEdit()
        self.uni_pair1_e1.setPlaceholderText("E10")
        self.uni_pair1_e2 = QtWidgets.QLineEdit()
        self.uni_pair1_e2.setPlaceholderText("E11")
        uni_pair1_layout.addWidget(self.uni_pair1_label)
        uni_pair1_layout.addWidget(self.uni_pair1_e1)
        uni_pair1_layout.addWidget(QtWidgets.QLabel("↔"))
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
        uni_pair2_layout.addWidget(QtWidgets.QLabel("↔"))
        uni_pair2_layout.addWidget(self.uni_pair2_e2)
        uni_layout.addLayout(uni_pair2_layout)
        
        # Multipolar electrode pairs (four pairs)
        multi_widget = QtWidgets.QWidget()
        multi_layout = QtWidgets.QVBoxLayout(multi_widget)
        
        # Add a label for the multipolar electrode section
        multi_label = QtWidgets.QLabel("Multipolar Electrode Pairs:")
        multi_label.setStyleSheet("font-weight: bold;")
        multi_layout.addWidget(multi_label)
        
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
            pair_layout.addWidget(QtWidgets.QLabel("↔"))
            pair_layout.addWidget(e2)
            multi_layout.addLayout(pair_layout)
            
            # Store references
            self.multi_pairs.append((e1, e2))
        
        # Add the widgets to the stacked widget
        self.electrode_stack.addWidget(uni_widget)
        self.electrode_stack.addWidget(multi_widget)
        layout.addWidget(self.electrode_stack)
        
        # Add some spacing
        layout.addSpacing(10)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Add left widget to main layout
        main_layout.addWidget(left_widget)
        
        # Right side (electrode list panel)
        self.right_widget = QtWidgets.QWidget()
        self.right_widget.setVisible(False)  # Initially hidden
        right_layout = QtWidgets.QVBoxLayout(self.right_widget)
        
        # Add title for electrode list
        electrode_title = QtWidgets.QLabel("Available Electrodes")
        electrode_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(electrode_title)
        
        # Add search box
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search electrodes...")
        self.search_box.textChanged.connect(self.filter_electrodes)
        right_layout.addWidget(self.search_box)
        
        # Add electrode list widget
        self.electrode_list = QtWidgets.QListWidget()
        self.electrode_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.electrode_list.setStyleSheet("""
            QListWidget {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #eee;
            }
        """)
        right_layout.addWidget(self.electrode_list)
        
        # Add right widget to main layout
        main_layout.addWidget(self.right_widget)
        
        # Connect net selection change to update electrode list
        self.net_combo.currentTextChanged.connect(self.update_electrode_list)
    
    def toggle_electrode_list(self):
        """Toggle the visibility of the electrode list panel."""
        if self.right_widget.isVisible():
            self.right_widget.setVisible(False)
            self.show_electrodes_btn.setText("Show Electrodes")
            self.resize(500, self.height())  # Return to original width
        else:
            self.right_widget.setVisible(True)
            self.show_electrodes_btn.setText("Hide Electrodes")
            self.resize(800, self.height())  # Expand width
            self.update_electrode_list()
    
    def update_electrode_list(self):
        """Update the list of available electrodes based on the selected net."""
        try:
            self.electrode_list.clear()
            net_file = self.net_combo.currentText()
            
            # Get project directory from environment variable
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            if not project_dir:
                return
            
            # Look in derivatives/SimNIBS for subjects
            simnibs_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS')
            subject_found = False
            
            # Look through all subject directories
            for subject_dir in os.listdir(simnibs_dir):
                if subject_dir.startswith('sub-'):
                    subject_id = subject_dir[4:]  # Remove 'sub-' prefix
                    m2m_dir = os.path.join(simnibs_dir, subject_dir, f'm2m_{subject_id}')
                    if os.path.isdir(m2m_dir):
                        eeg_file = os.path.join(m2m_dir, 'eeg_positions', net_file)
                        if os.path.exists(eeg_file):
                            subject_found = True
                            # Read the CSV file
                            with open(eeg_file, 'r') as f:
                                lines = f.readlines()
                                electrodes = []
                                for line in lines:
                                    parts = line.strip().split(',')
                                    if len(parts) >= 5:  # Ensure we have enough columns
                                        electrode_type = parts[0]
                                        electrode_name = parts[4]
                                        if electrode_type in ["Electrode", "ReferenceElectrode"]:
                                            electrodes.append(electrode_name)
                            
                            # Sort electrodes alphabetically
                            electrodes.sort()
                            
                            # Add to list widget
                            for electrode in electrodes:
                                self.electrode_list.addItem(electrode)
                            break
            
            if not subject_found:
                self.electrode_list.addItem("No electrode positions found")
        
        except Exception as e:
            self.electrode_list.addItem(f"Error loading electrodes: {str(e)}")
    
    def filter_electrodes(self, text):
        """Filter the electrode list based on search text."""
        for i in range(self.electrode_list.count()):
            item = self.electrode_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())
    
    def get_montage_data(self):
        """Get montage data entered in the dialog."""
        name = self.name_input.text().strip()
        is_unipolar = self.mode_unipolar.isChecked()
        target_net = self.net_combo.currentText()
        
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
            "target_net": target_net,
            "electrode_pairs": electrode_pairs
        }

    def update_electrode_inputs(self, checked):
        """Update the electrode input view based on the selected mode."""
        if checked:  # Unipolar selected
            self.electrode_stack.setCurrentIndex(0)
        else:  # Multipolar selected
            self.electrode_stack.setCurrentIndex(1) 

class ConductivityEditorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, custom_conductivities=None):
        super(ConductivityEditorDialog, self).__init__(parent)
        self.setWindowTitle("Tissue Conductivity Editor")
        # Use integer keys for tissue numbers
        self.custom_conductivities = {int(k): v for k, v in (custom_conductivities or {}).items()}
        self.setup_ui()
        
    def setup_ui(self):
        # Remove fixed size, use resize and minimum size for flexibility
        self.resize(900, 480)
        self.setMinimumSize(800, 400)
        
        # Main layout, no margins or spacing
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Info label
        info_label = QtWidgets.QLabel("Double-click on a value in the 'Value (S/m)' column to edit it.")
        info_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                color: #333;
                padding: 4px 8px 4px 8px;
                border-bottom: 1px solid #ddd;
                font-style: italic;
            }
        """)
        layout.addWidget(info_label)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Tissue Number", "Tissue Name", "Value (S/m)", "Reference"])
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        
        self.tissue_data = [
            (1, "White Matter", 0.126, "Wagner et al., 2004"),
            (2, "Gray Matter", 0.275, "Wagner et al., 2004"),
            (3, "CSF", 1.654, "Wagner et al., 2004"),
            (4, "Bone", 0.01, "Wagner et al., 2004"),
            (5, "Scalp", 0.465, "Wagner et al., 2004"),
            (6, "Eye balls", 0.5, "Opitz et al., 2015"),
            (7, "Compact Bone", 0.008, "Opitz et al., 2015"),
            (8, "Spongy Bone", 0.025, "Opitz et al., 2015"),
            (9, "Blood", 0.6, "Gabriel et al., 2009"),
            (10, "Muscle", 0.16, "Gabriel et al., 2009"),
            (100, "Silicone Rubber", 29.4, "NeuroConn electrodes: Wacker Elastosil R 570/60 RUSS"),
            (500, "Saline", 1.0, "Saturnino et al., 2015")
        ]
        self.table.setRowCount(len(self.tissue_data))
        for row, (number, name, value, ref) in enumerate(self.tissue_data):
            item = QtWidgets.QTableWidgetItem(str(number))
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(name)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 1, item)
            item = QtWidgets.QTableWidgetItem(str(value))
            item.setBackground(QtGui.QColor("#f0f8ff"))
            self.table.setItem(row, 2, item)
            item = QtWidgets.QTableWidgetItem(ref)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 3, item)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f5f5f5;
                selection-background-color: #2196F3;
                selection-color: white;
                gridline-color: #e0e0e0;
                border: none;
            }
            QHeaderView::section {
                background-color: #4a4a4a;
                color: white;
                padding: 4px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 1px;
                font-size: 11px;
            }
        """)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(28)
        layout.addWidget(self.table)
        
        # Button container
        button_container = QtWidgets.QWidget()
        button_container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        button_container.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                border-top: 1px solid #ddd;
            }
            QPushButton {
                min-width: 100px;
                padding: 6px 12px;
                margin: 6px;
                background-color: #ffffff;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
            }
        """)
        button_layout = QtWidgets.QHBoxLayout(button_container)
        button_layout.setContentsMargins(10, 0, 10, 0)
        button_layout.setSpacing(0)
        save_btn = QtWidgets.QPushButton("Save")
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(cancel_btn)
        save_btn.clicked.connect(self.save_conductivities)
        reset_btn.clicked.connect(self.reset_to_defaults)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(button_container)

        # After populating the table, override values with custom_conductivities if present
        for row, (number, name, value, ref) in enumerate(self.tissue_data):
            if self.custom_conductivities.get(number) is not None:
                self.table.item(row, 2).setText(str(self.custom_conductivities[number]))

    def save_conductivities(self):
        """Save the modified conductivity values."""
        modified_values = {}
        for row in range(self.table.rowCount()):
            tissue_num = int(self.table.item(row, 0).text())
            try:
                value = float(self.table.item(row, 2).text())
                if value <= 0:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Invalid Value",
                        f"Conductivity value for tissue {tissue_num} must be positive."
                    )
                    return
                modified_values[tissue_num] = value
                os.environ[f"TISSUE_COND_{tissue_num}"] = str(value)
            except ValueError:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Value",
                    f"Invalid conductivity value for tissue {tissue_num}. Please enter a valid number."
                )
                return
        self.custom_conductivities = modified_values
        self.accept()
    
    def reset_to_defaults(self):
        """Reset all values to their defaults."""
        for row, (number, _, value, _) in enumerate(self.tissue_data):
            self.table.item(row, 2).setText(str(value))

    def get_conductivities(self):
        return self.custom_conductivities.copy() 