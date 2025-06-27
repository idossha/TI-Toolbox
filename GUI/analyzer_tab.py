#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Analyzer Tab
This module provides a GUI interface for the analyzer functionality.
"""

import os
import json # Original script had this, though not obviously used in snippet
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog # Assuming this exists from original
from utils import confirm_overwrite # Assuming this exists from original
import traceback # For more detailed error logging if needed

class AnalysisThread(QtCore.QThread):
    """Thread to run analysis in background to prevent GUI freezing."""
    
    # Signal to emit output text
    output_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(AnalysisThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False # Flag to indicate if termination was requested
        
    def _strip_ansi_codes(self, text):
        """Remove ANSI color codes from text."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
        
    def run(self):
        """Run the analysis command in a separate thread."""
        try:
            # Set up Python unbuffered output
            self.env['PYTHONUNBUFFERED'] = '1'
            
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True, # Use text mode
                bufsize=1, # Line buffered
                env=self.env
            )
            
            # Real-time output display for both stdout and stderr
            while True:
                # Read stdout
                stdout_line = self.process.stdout.readline()
                if stdout_line:
                    self.output_signal.emit(self._strip_ansi_codes(stdout_line.strip()))
                
                # Read stderr
                stderr_line = self.process.stderr.readline()
                if stderr_line:
                    line = self._strip_ansi_codes(stderr_line.strip())
                    # Simple check for error-like messages
                    if "ERROR:" in line or "CRITICAL:" in line or "Failed" in line.upper():
                        self.output_signal.emit(f"Error: {line}")
                    else:
                        self.output_signal.emit(line)
                
                # Check if process has finished
                if self.terminated: # If terminate_process was called
                    break 
                    
                # Check if both stdout and stderr are empty and process has finished
                if not stdout_line and not stderr_line and self.process.poll() is not None:
                    break
            
            # Check for errors if not manually terminated
            if not self.terminated:
                returncode = self.process.wait() # Ensure process is waited for if not polled yet
                if returncode != 0:
                    # Emit a generic error if no specific stderr was captured before
                    self.output_signal.emit(f"Error: Process returned non-zero exit code {returncode}")
                    
        except Exception as e:
            self.output_signal.emit(f"Error running analysis: {str(e)}")

    
    def terminate_process(self):
        """Terminate the running process."""
        if self.process and self.process.poll() is None:  # Process is still running
            self.terminated = True # Set flag
            if os.name == 'nt':  # Windows
                # Terminate the entire process tree
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:  # Unix/Linux/Mac
                import signal
                # Try to terminate child processes too (best effort)
                try:
                    parent_pid = self.process.pid
                    # Using psutil would be more robust if available, but sticking to standard library
                    ps_output = subprocess.check_output(f"ps -o pid --ppid {parent_pid} --noheaders", shell=True)
                    child_pids = [int(pid_str) for pid_str in ps_output.decode().strip().split('\n') if pid_str]
                    for pid_val in child_pids:
                        try:
                            os.kill(pid_val, signal.SIGTERM)
                        except OSError:
                            pass # Process might have already exited
                except Exception: # pylint: disable=broad-except
                    # print("Note: Could not find/terminate child processes.")
                    pass # Ignore errors in finding/killing child processes
                
                # Kill the main process
                self.process.terminate() # Send SIGTERM
                try:
                    # Wait for a short time for graceful termination
                    self.process.wait(timeout=2) # seconds
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    self.process.kill() # Send SIGKILL
            
            return True # Termination was attempted
        return False # Process was not running or already finished

class AnalyzerTab(QtWidgets.QWidget):
    """Tab for analyzer functionality."""
    
    analysis_completed = QtCore.pyqtSignal(str, str, str)
    
    def __init__(self, parent=None):
        super(AnalyzerTab, self).__init__(parent)
        self.parent = parent
        self.analysis_running = False
        # self.analysis_process = None # This was the QProcess in original, now AnalysisThread
        self.optimization_process = None # Using this name for the AnalysisThread instance
        self.is_group_mode = False
        
        self.group_montage_config = {}
        self.group_field_config = {}
        self.group_atlas_config = {}
        
        self.current_group_subjects = [] # For iterating group analysis

        self.setup_ui()
        
        QtCore.QTimer.singleShot(500, self.list_subjects) # Delay subject listing
    
    def setup_ui(self):
        """Set up the user interface for the analyzer tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create analysis space radio buttons early so they are available for all widgets
        self.space_mesh = QtWidgets.QRadioButton("Mesh")
        self.space_voxel = QtWidgets.QRadioButton("Voxel")
        self.space_mesh.setChecked(True)
        self.space_group = QtWidgets.QButtonGroup(self)
        self.space_group.addButton(self.space_mesh)
        self.space_group.addButton(self.space_voxel)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: white; color: #f44336; padding: 5px 10px;
                border-radius: 3px; font-weight: bold;
            }
        """)
        self.status_label.setAlignment(QtCore.Qt.AlignVCenter)
        self.status_label.hide()
        main_layout.addWidget(self.status_label)
        
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        
        # Create left container (for subjects)
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        
        # Add mode selection toggle at the top
        mode_container = QtWidgets.QGroupBox("Analysis Mode")
        mode_layout = QtWidgets.QHBoxLayout(mode_container)
        self.single_mode_radio = QtWidgets.QRadioButton("Single Subject")
        self.group_mode_radio = QtWidgets.QRadioButton("Group Analysis")
        self.single_mode_radio.setChecked(True)  # Default to single mode
        self.mode_group = QtWidgets.QButtonGroup(self)
        self.mode_group.addButton(self.single_mode_radio)
        self.mode_group.addButton(self.group_mode_radio)
        mode_layout.addWidget(self.single_mode_radio)
        mode_layout.addWidget(self.group_mode_radio)
        left_layout.addWidget(mode_container)
        
        subject_container = QtWidgets.QGroupBox("Subject(s)")
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        
        # Create stacked widget to switch between single and group subject selection
        self.subject_selection_stack = QtWidgets.QStackedWidget()
        
        # Single mode: dropdown
        single_subject_widget = QtWidgets.QWidget()
        single_subject_layout = QtWidgets.QVBoxLayout(single_subject_widget)
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.addItem("Select subject...")
        single_subject_layout.addWidget(self.subject_combo)
        single_subject_layout.addStretch()
        self.subject_selection_stack.addWidget(single_subject_widget)
        
        # Group mode: list widget (existing)
        group_subject_widget = QtWidgets.QWidget()
        group_subject_layout = QtWidgets.QVBoxLayout(group_subject_widget)
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        group_subject_layout.addWidget(self.subject_list)
        self.subject_selection_stack.addWidget(group_subject_widget)
        
        subject_layout.addWidget(self.subject_selection_stack)
        
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
        left_layout.addWidget(subject_container)
        
        self.analysis_mode_stack = QtWidgets.QStackedWidget()
        self.single_analysis_widget = self.create_single_analysis_widget()
        self.analysis_mode_stack.addWidget(self.single_analysis_widget)
        self.group_analysis_widget = self.create_group_analysis_widget()
        self.analysis_mode_stack.addWidget(self.group_analysis_widget)
        left_layout.addWidget(self.analysis_mode_stack)
        
        # Add left container (subjects) to the layout first
        main_horizontal_layout.addWidget(left_container, 1)
        
        # Create right container (for analysis configuration)
        right_layout_container = QtWidgets.QWidget()
        right_layout_actual = self.create_analysis_parameters_widget(right_layout_container) # Pass container
        main_horizontal_layout.addWidget(right_layout_container, 2) # Add the container widget
        
        scroll_layout.addLayout(main_horizontal_layout)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Create a container widget for the console_layout
        console_layout_container = QtWidgets.QWidget()
        console_layout_actual = self.create_console_widget(console_layout_container) # Pass container
        main_layout.addWidget(console_layout_container)

        # Connect signals after all widgets are created
        self.subject_list.itemSelectionChanged.connect(self.on_subject_selection_changed)
        self.subject_combo.currentTextChanged.connect(self.on_subject_selection_changed)
        
        # Connect mode toggle signals
        self.single_mode_radio.toggled.connect(self.on_mode_changed)
        self.group_mode_radio.toggled.connect(self.on_mode_changed)
        
        # Set initial UI state for single mode (default)
        self.subject_selection_stack.setCurrentIndex(0)  # Show combo for single mode
        self.update_subject_button_states()  # Set button states for single mode
        
        # After all widgets are created, set field name visibility and connect toggles (for single mode)
        # This needs to be robust if widgets aren't found (e.g., during initial setup)
        if hasattr(self, 'field_name_label') and hasattr(self, 'field_name_input') and \
           hasattr(self, 'space_mesh') and hasattr(self, 'space_voxel'):
            self.field_name_label.setVisible(self.space_mesh.isChecked())
            self.field_name_input.setVisible(self.space_mesh.isChecked())
            self.space_mesh.toggled.connect(lambda checked: self.field_name_label.setVisible(checked) if hasattr(self, 'field_name_label') else None)
            self.space_mesh.toggled.connect(lambda checked: self.field_name_input.setVisible(checked) if hasattr(self, 'field_name_input') else None)
            self.space_voxel.toggled.connect(lambda checked: self.field_name_label.setVisible(not checked) if hasattr(self, 'field_name_label') else None)
            self.space_voxel.toggled.connect(lambda checked: self.field_name_input.setVisible(not checked) if hasattr(self, 'field_name_input') else None)
    
    def on_mode_changed(self):
        """Handle mode toggle between single and group analysis."""
        was_group_mode = self.is_group_mode
        self.is_group_mode = self.group_mode_radio.isChecked()
        
        if self.is_group_mode != was_group_mode:
            # Switch subject selection widget based on mode
            if self.is_group_mode:
                # Switch to group mode
                self.subject_selection_stack.setCurrentIndex(1)  # Show list widget
                self.analysis_mode_stack.setCurrentIndex(1)
                self.update_output("Switched to Group Analysis mode")
                
                # Update button states for group mode
                self.update_subject_button_states()
                
                # Connect group-mode specific signals for space toggles
                try:
                    self.space_mesh.toggled.disconnect(self.update_group_field_widgets)
                    self.space_voxel.toggled.disconnect(self.update_group_field_widgets)
                except TypeError:
                    pass  # Not connected
                self.space_mesh.toggled.connect(self.update_group_field_widgets)
                self.space_voxel.toggled.connect(self.update_group_field_widgets)
                
                # Force cortical analysis in group mode (spherical not supported)
                if self.type_spherical.isChecked():
                    self.type_cortical.setChecked(True)
                self.type_spherical.setEnabled(False)
                self.type_spherical.setToolTip("Spherical analysis is not available in group analysis mode")
                
                # Populate group common configuration if subjects are selected
                selected_subjects = self.get_selected_subjects()
                self.populate_group_common_config(selected_subjects)
                    
                self.set_analysis_config_panel_size('group')
            else:
                # Switch to single mode
                self.subject_selection_stack.setCurrentIndex(0)  # Show combo widget
                self.analysis_mode_stack.setCurrentIndex(0)
                self.update_output("Switched to Single Analysis mode")
                
                # Update button states for single mode
                self.update_subject_button_states()
                
                # Disconnect group-specific signals
                try:
                    self.space_mesh.toggled.disconnect(self.update_group_field_widgets)
                    self.space_voxel.toggled.disconnect(self.update_group_field_widgets)
                except TypeError:
                    pass
                
                # Re-enable spherical analysis in single mode
                self.type_spherical.setEnabled(True)
                self.type_spherical.setToolTip("")
                
                # Connect single mode signals
                try:
                    self.space_mesh.toggled.disconnect(self.update_field_files)
                    self.space_voxel.toggled.disconnect(self.update_field_files)
                except TypeError:
                    pass
                self.space_mesh.toggled.connect(self.update_field_files)
                self.space_voxel.toggled.connect(self.update_field_files)
                
                # Update single mode widgets
                self.update_simulations()
                self.update_atlas_combo()
                self.update_mesh_files()
                
                self.restore_single_mode_sizes()
                self.set_analysis_config_panel_size('single')
            
            # Force layout recalculation
            if hasattr(self, 'analysis_params_container'):
                self.analysis_params_container.adjustSize()
                self.analysis_params_container.updateGeometry()
            
            # Always recheck for valid atlases when mode changes
            self.update_atlas_combo()
            if self.is_group_mode and self.type_cortical.isChecked():
                self.update_group_atlas_options()
            
            self.update_atlas_visibility()

    def get_selected_subjects(self):
        """Get selected subjects based on current mode."""
        if self.is_group_mode:
            return [item.text() for item in self.subject_list.selectedItems()]
        else:
            # Single mode: return selected subject from combo (if not placeholder)
            current_text = self.subject_combo.currentText()
            if current_text and current_text != "Select subject...":
                return [current_text]
            return []
    
    def update_subject_button_states(self):
        """Update button visibility/text based on current mode."""
        if self.is_group_mode:
            # Group mode: show all buttons
            self.select_all_subjects_btn.setVisible(True)
            self.clear_subject_selection_btn.setText("Clear")
        else:
            # Single mode: hide select all button, change clear to reset
            self.select_all_subjects_btn.setVisible(False)
            self.clear_subject_selection_btn.setText("Reset")

    def on_subject_selection_changed(self):
        """Handle subject selection changes - update UI based on current mode."""
        selected_subjects = self.get_selected_subjects()
        
        if self.is_group_mode:
            # In group mode, update the common configuration
            self.populate_group_common_config(selected_subjects)
            if not selected_subjects:
                # Clear configurations if no subjects selected
                self.group_montage_config = {}
                self.group_field_config = {}
                self.group_atlas_config = {}
        else:
            # In single mode, update single mode widgets
            self.update_simulations()
            self.update_atlas_combo()
            self.update_mesh_files()
        
        # Always recheck for valid atlases when subject selection changes
        self.update_atlas_combo()
        if self.is_group_mode and self.type_cortical.isChecked():
            self.update_group_atlas_options()
        
        self.update_atlas_visibility()

    def create_single_analysis_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        simulation_container = QtWidgets.QGroupBox("Montage")
        simulation_layout = QtWidgets.QVBoxLayout(simulation_container)
        self.simulation_combo = QtWidgets.QComboBox()
        self.simulation_combo.addItem("Select montage...")
        simulation_layout.addWidget(self.simulation_combo)
        layout.addWidget(simulation_container)
        
        field_container = QtWidgets.QGroupBox("Field Selection")
        field_layout = QtWidgets.QGridLayout(field_container)

        # Field Name row
        self.field_name_label = QtWidgets.QLabel("Field Name:")
        self.field_name_input = QtWidgets.QLineEdit()
        self.field_name_input.setPlaceholderText("e.g., TI_max")
        field_layout.addWidget(self.field_name_label, 0, 0)
        field_layout.addWidget(self.field_name_input, 0, 1, 1, 2)

        # Field File row
        self.field_file_label = QtWidgets.QLabel("Field File:")
        self.field_combo = QtWidgets.QComboBox()
        self.browse_field_btn = QtWidgets.QPushButton()
        self.browse_field_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self.browse_field_btn.setToolTip("Browse for field file")
        self.browse_field_btn.clicked.connect(self.browse_field)
        field_layout.addWidget(self.field_file_label, 1, 0)
        field_layout.addWidget(self.field_combo, 1, 1)
        field_layout.addWidget(self.browse_field_btn, 1, 2)

        layout.addWidget(field_container)

        # Show/hide field name row based on mesh/voxel
        def update_field_name_row():
            is_mesh = self.space_mesh.isChecked()
            self.field_name_label.setVisible(is_mesh)
            self.field_name_input.setVisible(is_mesh)
        self.space_mesh.toggled.connect(lambda checked: update_field_name_row())
        self.space_voxel.toggled.connect(lambda checked: update_field_name_row())
        update_field_name_row()

        # Connect signals for single mode
        self.simulation_combo.currentTextChanged.connect(self.update_field_files)
        return widget
    
    def create_group_analysis_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        # Create common configuration section instead of tabs
        common_config_group = QtWidgets.QGroupBox("Common Configuration (Applied to All Selected Subjects)")
        common_config_layout = QtWidgets.QVBoxLayout(common_config_group)
        
        # Common montage selection
        montage_group = QtWidgets.QGroupBox("Shared Montage")
        montage_layout = QtWidgets.QVBoxLayout(montage_group)
        montage_selection_layout = QtWidgets.QHBoxLayout()
        montage_label = QtWidgets.QLabel("Montage:")
        self.group_montage_combo = QtWidgets.QComboBox()
        self.group_montage_combo.addItem("Select common montage...")
        self.group_montage_combo.currentTextChanged.connect(self.update_common_montage_config)
        montage_selection_layout.addWidget(montage_label)
        montage_selection_layout.addWidget(self.group_montage_combo)
        montage_selection_layout.addStretch()
        montage_layout.addLayout(montage_selection_layout)
        common_config_layout.addWidget(montage_group)
        
        # Common field selection (auto-selects grey matter subject space scans)
        field_group = QtWidgets.QGroupBox("Shared Field Configuration")
        field_layout = QtWidgets.QVBoxLayout(field_group)
        
        # Field name input (only visible for mesh analysis)
        field_name_layout = QtWidgets.QHBoxLayout()
        self.group_field_name_label = QtWidgets.QLabel("Field Name:")
        self.group_field_name_input = QtWidgets.QLineEdit()
        self.group_field_name_input.setPlaceholderText("e.g., TI_max")
        field_name_layout.addWidget(self.group_field_name_label)
        field_name_layout.addWidget(self.group_field_name_input)
        field_name_layout.addStretch()
        field_layout.addLayout(field_name_layout)
        
        # Auto-selection info and status
        self.group_field_status_label = QtWidgets.QLabel("Field files will be auto-selected when montage is chosen...")
        self.group_field_status_label.setStyleSheet("color: #666666; font-style: italic;")
        field_layout.addWidget(self.group_field_status_label)
        
        # Show selected fields button
        self.show_selected_fields_btn = QtWidgets.QPushButton("Show Selected Field Files")
        self.show_selected_fields_btn.clicked.connect(self.show_selected_field_files)
        self.show_selected_fields_btn.setEnabled(False)
        field_layout.addWidget(self.show_selected_fields_btn)
        
        common_config_layout.addWidget(field_group)
        
        layout.addWidget(common_config_group)
        layout.addStretch()
        return widget
    
    # create_subject_tab method removed - no longer using individual subject tabs
    
    def create_analysis_parameters_widget(self, container_widget): # Accept container
        right_layout = QtWidgets.QVBoxLayout(container_widget) # Use container

        analysis_params_container = QtWidgets.QGroupBox("Analysis Configuration")
        self.analysis_params_container = analysis_params_container
        analysis_params_layout = QtWidgets.QVBoxLayout(analysis_params_container)
        
        space_layout = QtWidgets.QHBoxLayout()
        self.space_label = QtWidgets.QLabel("Analysis Space:")
        self.space_mesh = QtWidgets.QRadioButton("Mesh")
        self.space_voxel = QtWidgets.QRadioButton("Voxel")
        self.space_mesh.setChecked(True)
        self.space_group = QtWidgets.QButtonGroup(self) # Parent `self` is AnalyzerTab
        self.space_group.addButton(self.space_mesh)
        self.space_group.addButton(self.space_voxel)
        space_layout.addWidget(self.space_label)
        space_layout.addWidget(self.space_mesh)
        space_layout.addWidget(self.space_voxel)
        analysis_params_layout.addLayout(space_layout)
        
        type_layout = QtWidgets.QHBoxLayout()
        self.type_label = QtWidgets.QLabel("Analysis Type:")
        self.type_spherical = QtWidgets.QRadioButton("Spherical")
        self.type_cortical = QtWidgets.QRadioButton("Cortical")
        self.type_spherical.setChecked(True)
        self.type_group = QtWidgets.QButtonGroup(self) # Parent `self` is AnalyzerTab
        self.type_group.addButton(self.type_spherical)
        self.type_group.addButton(self.type_cortical)
        type_layout.addWidget(self.type_label)
        type_layout.addWidget(self.type_spherical)
        type_layout.addWidget(self.type_cortical)
        analysis_params_layout.addLayout(type_layout)
        
        self.analysis_stack = QtWidgets.QStackedWidget()
        spherical_widget = QtWidgets.QWidget()
        spherical_layout = QtWidgets.QVBoxLayout(spherical_widget)
        coordinates_layout = QtWidgets.QHBoxLayout()
        self.coordinates_label = QtWidgets.QLabel("RAS Coordinates (x,y,z):")
        self.coord_x = QtWidgets.QLineEdit()
        self.coord_y = QtWidgets.QLineEdit()
        self.coord_z = QtWidgets.QLineEdit()
        for coord_widget in [self.coord_x, self.coord_y, self.coord_z]: # Renamed variable
            coord_widget.setPlaceholderText("0.0")
        coordinates_layout.addWidget(self.coordinates_label)
        coordinates_layout.addWidget(self.coord_x)
        coordinates_layout.addWidget(self.coord_y)
        coordinates_layout.addWidget(self.coord_z)
        self.view_in_freeview_btn = QtWidgets.QPushButton("View in Freeview")
        self.view_in_freeview_btn.setToolTip("View T1 in Freeview to help find coordinates")
        self.view_in_freeview_btn.clicked.connect(self.load_t1_in_freeview)
        coordinates_layout.addWidget(self.view_in_freeview_btn)
        spherical_layout.addLayout(coordinates_layout)
        radius_layout = QtWidgets.QHBoxLayout()
        self.radius_label = QtWidgets.QLabel("Radius (mm):")
        self.radius_input = QtWidgets.QLineEdit()
        self.radius_input.setPlaceholderText("5.0")
        radius_layout.addWidget(self.radius_label)
        radius_layout.addWidget(self.radius_input)
        spherical_layout.addLayout(radius_layout)
        self.analysis_stack.addWidget(spherical_widget)
        
        cortical_widget = QtWidgets.QWidget()
        cortical_layout = QtWidgets.QVBoxLayout(cortical_widget)
        self.mesh_atlas_widget = QtWidgets.QWidget()
        mesh_atlas_layout = QtWidgets.QHBoxLayout(self.mesh_atlas_widget)
        self.mesh_atlas_label = QtWidgets.QLabel("Atlas Name:")
        self.atlas_name_combo = QtWidgets.QComboBox()
        self.atlas_name_combo.addItems(["DK40", "HCP_MMP1", "a2009s"])
        self.atlas_name_combo.setCurrentText("DK40")
        mesh_atlas_layout.addWidget(self.mesh_atlas_label)
        mesh_atlas_layout.addWidget(self.atlas_name_combo)
        self.voxel_atlas_widget = QtWidgets.QWidget()
        voxel_atlas_layout = QtWidgets.QHBoxLayout(self.voxel_atlas_widget)
        self.voxel_atlas_label = QtWidgets.QLabel("Atlas File:")
        self.atlas_combo = QtWidgets.QComboBox() # This is for single mode voxel atlas
        self.atlas_combo.setEditable(False) # Original was non-editable
        voxel_atlas_layout.addWidget(self.voxel_atlas_label)
        voxel_atlas_layout.addWidget(self.atlas_combo)
        cortical_layout.addWidget(self.mesh_atlas_widget)
        cortical_layout.addWidget(self.voxel_atlas_widget)
        region_layout = QtWidgets.QHBoxLayout()
        self.region_label = QtWidgets.QLabel("Region:")
        self.region_input = QtWidgets.QLineEdit()
        self.region_input.setPlaceholderText("e.g., superiorfrontal")
        self.show_regions_btn = QtWidgets.QPushButton("List Regions")
        self.show_regions_btn.setToolTip("Show available regions in the selected atlas")
        self.show_regions_btn.clicked.connect(self.show_available_regions)
        self.show_regions_btn.setEnabled(False)
        region_layout.addWidget(self.region_label)
        region_layout.addWidget(self.region_input)
        region_layout.addWidget(self.show_regions_btn)
        cortical_layout.addLayout(region_layout)
        self.whole_head_check = QtWidgets.QCheckBox("Analyze Whole Head")
        self.whole_head_check.stateChanged.connect(self.toggle_region_input)
        cortical_layout.addWidget(self.whole_head_check)
        self.analysis_stack.addWidget(cortical_widget)
        
        self.type_spherical.toggled.connect(lambda checked: self.analysis_stack.setCurrentIndex(0) if checked else None)
        self.type_cortical.toggled.connect(lambda checked: self.analysis_stack.setCurrentIndex(1) if checked else None)
        
        # Original connections from setup_ui for space/type changes
        self.space_mesh.toggled.connect(self.update_atlas_visibility)
        self.space_voxel.toggled.connect(self.update_atlas_visibility)
        self.type_spherical.toggled.connect(self.update_atlas_visibility)
        self.type_cortical.toggled.connect(self.update_atlas_visibility)
        
        # Connect signals for group field widget updates
        self.space_mesh.toggled.connect(self.update_group_field_widgets)
        self.space_voxel.toggled.connect(self.update_group_field_widgets)
        
        self.update_atlas_visibility() # Initial call
        analysis_params_layout.addWidget(self.analysis_stack)
        right_layout.addWidget(analysis_params_container)
        
        visualization_container = QtWidgets.QGroupBox("Visualization")
        visualization_layout = QtWidgets.QVBoxLayout(visualization_container)
        self.visualize_check = QtWidgets.QCheckBox("Generate Visualizations")
        self.visualize_check.setChecked(True)
        visualization_layout.addWidget(self.visualize_check)
        mesh_viz_layout = QtWidgets.QVBoxLayout()
        mesh_viz_label = QtWidgets.QLabel("View Mesh in Gmsh:")
        mesh_viz_label.setStyleSheet("font-weight: bold;")
        mesh_viz_layout.addWidget(mesh_viz_label)
        mesh_controls_layout = QtWidgets.QHBoxLayout()
        self.mesh_combo = QtWidgets.QComboBox() # For Gmsh
        self.mesh_combo.addItem("Select mesh file...")
        self.launch_gmsh_btn = QtWidgets.QPushButton("Launch Gmsh")
        self.launch_gmsh_btn.clicked.connect(self.launch_gmsh)
        self.launch_gmsh_btn.setEnabled(False)
        self.mesh_combo.currentTextChanged.connect(self.update_gmsh_button_state) # Connect here

        mesh_controls_layout.addWidget(self.mesh_combo)
        mesh_controls_layout.addWidget(self.launch_gmsh_btn)
        mesh_viz_layout.addLayout(mesh_controls_layout)
        visualization_layout.addLayout(mesh_viz_layout)
        right_layout.addWidget(visualization_container)
        
        return right_layout # Return the layout itself
    
    def create_console_widget(self, container_widget): # Accept container
        console_layout = QtWidgets.QVBoxLayout(container_widget) # Use container

        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold;")
        self.output_console = QtWidgets.QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setStyleSheet("""
            QTextEdit { background-color: #1e1e1e; color: #f0f0f0; font-family: 'Consolas', 'Courier New', monospace; }
        """)
        self.output_console.setAcceptRichText(True)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(output_label)
        header_layout.addStretch()
        
        console_buttons_layout = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Run Analysis")
        self.run_btn.clicked.connect(self.run_analysis)
        self.stop_btn = QtWidgets.QPushButton("Stop Analysis")
        self.stop_btn.clicked.connect(self.stop_analysis)
        self.stop_btn.setEnabled(False)
        clear_btn = QtWidgets.QPushButton("Clear Console")
        clear_btn.clicked.connect(self.clear_console)
        console_buttons_layout.addWidget(self.run_btn)
        console_buttons_layout.addWidget(self.stop_btn)
        console_buttons_layout.addWidget(clear_btn)
        header_layout.addLayout(console_buttons_layout)
        
        console_layout.addLayout(header_layout)
        console_layout.addWidget(self.output_console)
        return console_layout

    def select_all_subjects(self):
        if self.is_group_mode:
            self.subject_list.selectAll()
        # No select all for single mode (only one subject can be selected)
    
    def populate_group_common_config(self, selected_subjects):
        """Find common montages shared across all selected subjects and populate the group config."""
        self.group_montage_config = {}
        self.group_field_config = {}
        self.group_atlas_config = {}
        
        if not selected_subjects:
            self.group_montage_combo.clear()
            self.group_montage_combo.addItem("Select common montage...")
            return
            
        # Find common montages across all subjects
        common_montages = self.find_common_montages(selected_subjects)
        
        # Update the montage combo with common montages
        current_selection = self.group_montage_combo.currentText()
        self.group_montage_combo.clear()
        self.group_montage_combo.addItem("Select common montage...")
        
        if common_montages:
            self.group_montage_combo.addItems(sorted(common_montages))
            # Try to restore previous selection if it's still available
            if current_selection in common_montages:
                index = self.group_montage_combo.findText(current_selection)
                if index != -1:
                    self.group_montage_combo.setCurrentIndex(index)
        else:
            self.group_montage_combo.addItem("No common montages found")
            self.group_montage_combo.model().item(1).setEnabled(False)
    
    def find_common_montages(self, selected_subjects):
        """Find montages that exist for all selected subjects."""
        if not selected_subjects:
            return []
            
        project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
        project_dir = f"/mnt/{project_dir_name}"
        
        # Get montages for the first subject
        first_subject = selected_subjects[0]
        first_subject_simulations_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', 
                                                    f'sub-{first_subject}', 'Simulations')
        
        if not os.path.exists(first_subject_simulations_dir):
            return []
            
        # Start with all montages from first subject
        common_montages = set()
        try:
            common_montages = set([d for d in os.listdir(first_subject_simulations_dir) 
                                 if os.path.isdir(os.path.join(first_subject_simulations_dir, d))])
        except Exception:
            return []
        
        # Check remaining subjects and keep only common montages
        for subject_id in selected_subjects[1:]:
            subject_simulations_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', 
                                                  f'sub-{subject_id}', 'Simulations')
            
            if not os.path.exists(subject_simulations_dir):
                return []  # If any subject doesn't have simulations, no common montages
                
            try:
                subject_montages = set([d for d in os.listdir(subject_simulations_dir) 
                                      if os.path.isdir(os.path.join(subject_simulations_dir, d))])
                # Keep only montages that exist in both
                common_montages = common_montages.intersection(subject_montages)
            except Exception:
                return []
                
        return list(common_montages)
    
    def update_common_montage_config(self, montage_name):
        """Update the common montage configuration for all selected subjects."""
        if montage_name and montage_name != "Select common montage..." and not montage_name.startswith("No common"):
            # Store the common montage name - it will be applied to all subjects during analysis
            self.group_montage_config['common_montage'] = montage_name
            self.update_output(f"Set common montage: {montage_name} (will be applied to all selected subjects)")
            
            # Auto-select field files for all subjects when montage is selected
            self.auto_select_group_field_files(montage_name)
        else:
            self.group_montage_config.clear()
            self.group_field_config.clear()
            self.group_field_status_label.setText("Field files will be auto-selected when montage is chosen...")
            self.show_selected_fields_btn.setEnabled(False)
    
    def auto_select_group_field_files(self, montage_name):
        """Auto-select grey matter subject space field files for all selected subjects."""
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects or not montage_name:
            return
            
        project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
        project_dir = f"/mnt/{project_dir_name}"
        is_mesh = self.space_mesh.isChecked()
        
        # Clear previous field config
        self.group_field_config.clear()
        
        # Find field files for each subject
        failed_subjects = []
        success_count = 0
        
        for subject_id in selected_subjects:
            # Determine the correct directory based on analysis space
            if is_mesh:
                field_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                       'Simulations', montage_name, 'TI', 'mesh')
            else:
                field_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                       'Simulations', montage_name, 'TI', 'niftis')
            
            if not os.path.exists(field_dir):
                failed_subjects.append(f"{subject_id} (directory not found)")
                continue
                
            try:
                all_files = os.listdir(field_dir)
            except Exception:
                failed_subjects.append(f"{subject_id} (cannot read directory)")
                continue
            
            # Filter files based on criteria and analysis space
            if is_mesh:
                eligible_files = [f for f in all_files if f.endswith('.msh') and not f.endswith('.msh.opt')]
            else:
                eligible_files = [f for f in all_files if any(f.endswith(ext) for ext in ['.nii', '.nii.gz', '.mgz'])]
            
            # Find grey matter subject space files (prefix "grey", no "MNI" or "central")
            grey_subject_files = [f for f in eligible_files 
                                if f.startswith('grey') and 'MNI' not in f and 'central' not in f]
            
            if not grey_subject_files:
                failed_subjects.append(f"{subject_id} (no grey matter subject space files found)")
                continue
            
            # Select the first grey matter subject space file (they should be equivalent)
            selected_file = grey_subject_files[0]
            selected_path = os.path.join(field_dir, selected_file)
            self.group_field_config[subject_id] = selected_path
            success_count += 1
        
        # Update status
        if success_count == len(selected_subjects):
            self.group_field_status_label.setText(f"✅ Auto-selected fields for all {success_count} subjects")
            self.group_field_status_label.setStyleSheet("color: #228B22; font-weight: bold;")
            self.show_selected_fields_btn.setEnabled(True)
        elif success_count > 0:
            self.group_field_status_label.setText(f"⚠️ Auto-selected fields for {success_count}/{len(selected_subjects)} subjects")
            self.group_field_status_label.setStyleSheet("color: #FF8C00; font-weight: bold;")
            self.show_selected_fields_btn.setEnabled(True)
        else:
            self.group_field_status_label.setText(f"❌ Failed to auto-select fields")
            self.group_field_status_label.setStyleSheet("color: #DC143C; font-weight: bold;")
            self.show_selected_fields_btn.setEnabled(False)
        
        # Show details of failures if any
        if failed_subjects:
            failure_details = "\n".join(f"  - {failure}" for failure in failed_subjects)
            self.update_output(f"Field auto-selection completed. Failed subjects:\n{failure_details}")
    
    def show_selected_field_files(self):
        """Show a dialog with the selected field files for each subject."""
        if not self.group_field_config:
            QtWidgets.QMessageBox.information(self, "No Field Files", "No field files have been selected yet.")
            return
            
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Selected Field Files")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # Header
        header_label = QtWidgets.QLabel("Grey Matter Subject Space Field Files Selected:")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(header_label)
        
        # List widget to show files
        list_widget = QtWidgets.QListWidget()
        for subject_id, field_path in sorted(self.group_field_config.items()):
            file_name = os.path.basename(field_path)
            item_text = f"Subject {subject_id}: {file_name}"
            list_item = QtWidgets.QListWidgetItem(item_text)
            list_item.setData(QtCore.Qt.UserRole, field_path)  # Store full path
            list_item.setToolTip(f"Full path: {field_path}")
            list_widget.addItem(list_item)
        
        layout.addWidget(list_widget)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        dialog.exec_()
    
    def update_group_field_widgets(self): # Called when space_mesh/voxel toggled in group mode
        """Update field widgets in group mode when space type changes."""
        if not self.is_group_mode:
            return
        
        # Update field name visibility
        is_mesh = self.space_mesh.isChecked()
        self.group_field_name_label.setVisible(is_mesh)
        self.group_field_name_input.setVisible(is_mesh)
        
        # Re-run auto-selection if montage is already selected
        current_montage = self.group_montage_config.get('common_montage')
        if current_montage:
            self.auto_select_group_field_files(current_montage)

    def list_subjects(self):
        try:
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            if not project_dir_name:
                return
            
            project_dir = f"/mnt/{project_dir_name}"
            
            # Clear both widgets
            self.subject_list.clear()
            self.subject_combo.clear()
            self.subject_combo.addItem("Select subject...")
            
            simnibs_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS')
            
            if not os.path.exists(simnibs_dir):
                return
            
            subjects = []
            for item_name in os.listdir(simnibs_dir): # item_name is like 'sub-001'
                if item_name.startswith('sub-'):
                    subject_id_short = item_name[4:] # '001'
                    m2m_dir_to_check = os.path.join(simnibs_dir, item_name, f'm2m_{subject_id_short}')
                    if os.path.isdir(m2m_dir_to_check):
                        subjects.append(subject_id_short)
            
            def natural_sort_key(s):
                import re
                return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]
            subjects.sort(key=natural_sort_key)
            
            # Populate both widgets
            for subject in subjects:
                self.subject_list.addItem(subject)
                self.subject_combo.addItem(subject)
        except Exception as e:
            pass

    def clear_subject_selection(self):
        if self.is_group_mode:
            self.subject_list.clearSelection()
        else:
            # Reset to placeholder for single mode
            self.subject_combo.setCurrentIndex(0)

    def get_m2m_dir_for_subject(self, subject_id): # subject_id is short form like "001"
        project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
        project_dir = f"/mnt/{project_dir_name}"
        # Original logic for m2m dir path
        return os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}')


    def browse_field(self): # For single mode
        if self.space_mesh.isChecked():
            file_filter = "Mesh Files (*.msh);;All Files (*)"
        else:
            file_filter = "NIfTI Files (*.nii *.nii.gz);;MGZ Files (*.mgz);;All Files (*)"
            
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Field File", "", file_filter)
        
        if file_name:
            is_mesh_ext = file_name.endswith('.msh') and not file_name.endswith('.msh.opt')
            is_vol_ext = any(file_name.endswith(ext) for ext in ['.nii', '.nii.gz', '.mgz'])

            valid_type = (is_mesh_ext and self.space_mesh.isChecked()) or \
                         (is_vol_ext and not self.space_mesh.isChecked()) # Original logic: not self.space_mesh

            if not valid_type:
                QtWidgets.QMessageBox.warning(self, "Invalid File Type",
                    "Please select a valid field file:\n" +
                    "- For mesh analysis: .msh files\n" +
                    "- For voxel analysis: .nii, .nii.gz, or .mgz files")
                return
            
            file_basename = os.path.basename(file_name)
            # Check if file already exists in combo box (by data which is path)
            found = any(self.field_combo.itemData(i) == file_name for i in range(self.field_combo.count()))
            
            if not found:
                self.field_combo.addItem(file_basename, file_name) # Add with path as data
            
            # Select the item (either newly added or existing)
            for i in range(self.field_combo.count()): # Iterate to find and select
                if self.field_combo.itemData(i) == file_name:
                    self.field_combo.setCurrentIndex(i)
                    break
            
            # Original logic for field_name_input enablement
            self.field_name_input.setEnabled(is_mesh_ext) 
            self.field_name_label.setEnabled(is_mesh_ext)


    def get_available_atlas_files(self, subject_id): # subject_id is short form
        atlas_files = []
        if not subject_id: return atlas_files

        project_dir_name = os.environ.get("PROJECT_DIR_NAME", "BIDS_new")
        project_dir = os.path.join("/mnt", project_dir_name)
        # Freesurfer path uses full subject ID for both levels, e.g., sub-001/sub-001/mri
        freesurfer_mri_dir = os.path.join(project_dir, "derivatives", "freesurfer", f"sub-{subject_id}", f"{subject_id}", "mri") # Original used f"{subject_id}" twice
        
        # Original defined atlases
        atlases_to_check = ['aparc.DKTatlas+aseg.mgz', 'aparc.a2009s+aseg.mgz']
        
        if os.path.isdir(freesurfer_mri_dir): # Check if subject's FS mri dir exists
            for atlas_filename in atlases_to_check:
                full_path = os.path.join(freesurfer_mri_dir, atlas_filename)
                if os.path.exists(full_path):
                    # Original stored (atlas_filename, full_path)
                    atlas_files.append((atlas_filename, full_path)) 
        
        if not atlas_files: # No specific atlases found
            # Original warning message logic
            atlas_files.append("⚠️ FreeSurfer recon-all preprocessing required for atlas generation")
        return atlas_files


    def update_atlas_combo(self): # For single mode
        if self.is_group_mode: return
        self.atlas_combo.clear()
        
        # Get selected subject from appropriate widget based on mode
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            self.atlas_combo.addItem("Select a subject first")
            self.atlas_combo.setEnabled(False)
            self.show_regions_btn.setEnabled(False)
            return
        
        subject_id = selected_subjects[0] # Short ID
        atlas_files_data = self.get_available_atlas_files(subject_id)
        has_valid_atlas = False
        if not atlas_files_data:
            if self.type_cortical.isChecked() and not self.space_mesh.isChecked(): # Voxel Cortical
                pass
        elif isinstance(atlas_files_data[0], str) and atlas_files_data[0].startswith('⚠️'): # Warning message
            if self.type_cortical.isChecked() and not self.space_mesh.isChecked():
                pass
            self.atlas_combo.addItem(atlas_files_data[0])
            self.atlas_combo.model().item(self.atlas_combo.count() - 1).setEnabled(False)
            self.atlas_combo.setEnabled(False)
        else: # Has valid atlas tuples
            for display_name, full_path in atlas_files_data:
                self.atlas_combo.addItem(display_name, full_path)
            if self.atlas_combo.count() > 0:
                has_valid_atlas = True
                self.atlas_combo.setCurrentIndex(0)
            self.atlas_combo.setEnabled(has_valid_atlas)
        self.show_regions_btn.setEnabled(has_valid_atlas and not self.whole_head_check.isChecked() and self.type_cortical.isChecked())


    def browse_atlas(self): # For single mode voxel atlas browsing
        initial_dir = ""
        selected_subjects = self.get_selected_subjects()
        if selected_subjects:
            subject_id = selected_subjects[0]
            m2m_dir_path = self.get_m2m_dir_for_subject(subject_id)
            if m2m_dir_path and os.path.exists(m2m_dir_path): # Check existence
                initial_dir = os.path.join(m2m_dir_path, 'segmentation') 
        
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Atlas File", initial_dir,
            "Atlas Files (*.nii *.nii.gz *.mgz);;All Files (*)")
        
        if file_name:
            # Original code had self.atlas_combo.setEditText(file_name)
            # This implies atlas_combo might have been editable. Current setup is not.
            # We should add it as an item if not present, and select it.
            base_name = os.path.basename(file_name)
            existing_index = -1
            for i in range(self.atlas_combo.count()):
                if self.atlas_combo.itemData(i) == file_name: # Check by path
                    existing_index = i
                    break
            if existing_index != -1:
                self.atlas_combo.setCurrentIndex(existing_index)
            else:
                # Add the new browsed atlas file
                self.atlas_combo.addItem(base_name, file_name) # Use base_name for display, path for data
                self.atlas_combo.setCurrentIndex(self.atlas_combo.count() - 1) # Select newly added
            
            # Update button state after selection/addition
            can_list_regions = self.atlas_combo.isEnabled() and \
                               self.type_cortical.isChecked() and \
                               not self.whole_head_check.isChecked()
            self.show_regions_btn.setEnabled(can_list_regions)


    def update_atlas_visibility(self):
        is_mesh = self.space_mesh.isChecked()
        is_cortical = self.type_cortical.isChecked()
        
        # Original visibility logic for atlas selection widgets
        self.mesh_atlas_widget.setVisible(is_mesh and is_cortical)
        self.voxel_atlas_widget.setVisible(not is_mesh and is_cortical)
        
        # Original logic for field name input (single mode)
        if not self.is_group_mode: # Only for single mode
            if hasattr(self, 'field_name_input'): self.field_name_input.setEnabled(is_mesh)
            if hasattr(self, 'field_name_label'): self.field_name_label.setEnabled(is_mesh)
        
        # Original logic for region inputs
        region_enabled = is_cortical and not self.whole_head_check.isChecked()
        self.region_label.setEnabled(region_enabled)
        self.region_input.setEnabled(region_enabled)
        # self.show_regions_btn.setEnabled(is_cortical) # Original was simpler
        # More nuanced enablement for show_regions_btn:
        can_list_regions = is_cortical
        if not self.is_group_mode: # Single mode depends on atlas_combo state
            can_list_regions = can_list_regions and self.atlas_combo.isEnabled() and not self.whole_head_check.isChecked()
        else: # Group mode
            can_list_regions = can_list_regions and not self.whole_head_check.isChecked()
        self.show_regions_btn.setEnabled(can_list_regions)


        self.mesh_atlas_widget.setEnabled(is_mesh and is_cortical)
        self.voxel_atlas_widget.setEnabled(not is_mesh and is_cortical)
        
        self.mesh_atlas_widget.update() # Original calls
        self.voxel_atlas_widget.update()
        
        if self.is_group_mode and is_cortical:
            self.update_group_atlas_options()
        elif not self.is_group_mode: # Ensure single mode atlas combo is also updated
            self.update_atlas_combo()


    def update_group_atlas_options(self): # For shared atlas selectors in group mode
        if not self.is_group_mode: return
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        if not selected_subjects: return
        self.atlas_name_combo.clear() # For mesh
        self.atlas_combo.clear()      # For voxel (this was for single mode, repurposing for group shared voxel if needed)
        if self.space_mesh.isChecked() and self.type_cortical.isChecked():
            self.atlas_name_combo.addItems(["DK40", "HCP_MMP1", "a2009s"]) # Predefined mesh atlases
            self.atlas_name_combo.setCurrentText("DK40")
            self.atlas_name_combo.setEnabled(self.atlas_name_combo.count() > 0)
            try: self.atlas_name_combo.currentTextChanged.disconnect(self.update_group_mesh_atlas)
            except TypeError: pass
            self.atlas_name_combo.currentTextChanged.connect(self.update_group_mesh_atlas)
            self.update_group_mesh_atlas(self.atlas_name_combo.currentText()) # Initial update
        elif self.space_voxel.isChecked() and self.type_cortical.isChecked():
            # Get atlases for first subject to start with
            available_atlases_for_first_subject = self.get_available_atlas_files(selected_subjects[0])
            common_atlases_display = []
            
            # If first subject has valid atlases, check against other subjects
            if isinstance(available_atlases_for_first_subject, list) and \
               available_atlases_for_first_subject and \
               isinstance(available_atlases_for_first_subject[0], tuple):
                
                # Start with first subject's atlases
                first_subject_atlases = {disp_name: path_val for disp_name, path_val in available_atlases_for_first_subject}
                
                # Check each subsequent subject
                for subject_id in selected_subjects[1:]:
                    subject_atlases = self.get_available_atlas_files(subject_id)
                    if not isinstance(subject_atlases, list) or not subject_atlases or not isinstance(subject_atlases[0], tuple):
                        # If any subject has no valid atlases, clear common atlases
                        first_subject_atlases = {}
                        break
                    
                    # Keep only atlases that exist in both subjects
                    subject_atlas_names = {disp_name for disp_name, _ in subject_atlases}
                    first_subject_atlases = {name: path for name, path in first_subject_atlases.items() 
                                          if name in subject_atlas_names}
                
                # Add common atlases to combo
                for disp_name, path_val in first_subject_atlases.items():
                    self.atlas_combo.addItem(disp_name, path_val)
                    common_atlases_display.append(disp_name)
            
            if common_atlases_display:
                self.atlas_combo.setCurrentIndex(0)
                self.atlas_combo.setEnabled(True)
                try: self.atlas_combo.currentTextChanged.disconnect(self.update_group_voxel_atlas)
                except TypeError: pass
                self.atlas_combo.currentTextChanged.connect(self.update_group_voxel_atlas)
                self.update_group_voxel_atlas(self.atlas_combo.currentText()) # Initial update
            else:
                self.atlas_combo.addItem("No common atlases for all selected subjects")
                self.atlas_combo.setEnabled(False)
                self.group_atlas_config.clear() # Clear all atlas configs since we have no common atlas
    
    def update_group_mesh_atlas(self, atlas_name): # Called by shared mesh atlas_name_combo
        if not self.is_group_mode or not self.space_mesh.isChecked() or not self.type_cortical.isChecked(): return
            
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        for subject_id in selected_subjects:
            # For mesh, atlas name is sufficient, path is not needed from subject's dir for SimNIBS subject_atlas
            self.group_atlas_config[subject_id] = {'name': atlas_name, 'path': None, 'type': 'mesh'}

    def update_group_voxel_atlas(self, atlas_display_name_from_shared_combo): # Called by shared voxel atlas_combo
        if not self.is_group_mode or not self.space_voxel.isChecked() or not self.type_cortical.isChecked(): return
            
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        
        # The shared_combo's currentData() gives the path for the *first subject* or a representative.
        # We need to find the equivalent path for *each* subject.
        
        for subject_id in selected_subjects:
            subject_specific_atlases = self.get_available_atlas_files(subject_id)
            found_path_for_this_subject = None
            
            # Check if subject_specific_atlases is a list of tuples (valid atlases)
            if isinstance(subject_specific_atlases, list) and subject_specific_atlases and isinstance(subject_specific_atlases[0], tuple):
                for disp_name, subj_path in subject_specific_atlases:
                    # We match by display name, assuming they are consistent (e.g., "DKT Atlas + Aseg")
                    if disp_name == atlas_display_name_from_shared_combo:
                        found_path_for_this_subject = subj_path
                        break
            
            if found_path_for_this_subject:
                self.group_atlas_config[subject_id] = {
                    'name': atlas_display_name_from_shared_combo, # Store the display name
                    'path': found_path_for_this_subject,           # Store subject-specific path
                    'type': 'voxel'
                }
            else:
                self.group_atlas_config.pop(subject_id, None) # Atlas not found for this subject


    def toggle_region_input(self, state_int): # state is int from checkbox
        is_checked = bool(state_int)
        self.region_input.setEnabled(not is_checked and self.type_cortical.isChecked()) # Enable if not whole head & cortical
        self.region_label.setEnabled(not is_checked and self.type_cortical.isChecked())
        
        # Update "List Regions" button enablement based on original logic
        can_list_regions = self.type_cortical.isChecked() and (not is_checked)
        if not self.is_group_mode: # Single mode also depends on atlas_combo
            can_list_regions = can_list_regions and self.atlas_combo.isEnabled() 
        self.show_regions_btn.setEnabled(can_list_regions)
    
    def validate_inputs(self):
        if self.is_group_mode:
            return self.validate_group_inputs()
        else:
            return self.validate_single_inputs()
    
    def validate_single_inputs(self):
        if not self.subject_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a subject.")
            return False
        if self.simulation_combo.currentIndex() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a montage.")
            return False
        if self.field_combo.currentIndex() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a field file.")
            return False
        if self.space_mesh.isChecked() and not self.field_name_input.text().strip():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a field name for mesh analysis.")
            return False
        return self.validate_analysis_parameters()
    
    def validate_group_inputs(self):
        selected_subjects = self.get_selected_subjects()
        if len(selected_subjects) < 1:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select one or more subjects for group analysis.")
            return False
        
        # Check common montage selection
        if 'common_montage' not in self.group_montage_config or not self.group_montage_config['common_montage']:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a common montage for all subjects.")
            return False
            
        # Check field configuration
        if not self.group_field_config:
            QtWidgets.QMessageBox.warning(self, "Warning", "No field files have been auto-selected. Please select a montage to auto-select grey matter field files.")
            return False
            
        # Check that all selected subjects have field files
        missing_fields = [subj for subj in selected_subjects if subj not in self.group_field_config]
        if missing_fields:
            QtWidgets.QMessageBox.warning(self, "Warning", f"Missing field files for subjects: {', '.join(missing_fields)}")
            return False
            
        # Check field name for mesh analysis
        if self.space_mesh.isChecked():
            field_name = self.group_field_name_input.text().strip()
            if not field_name:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a field name for mesh analysis.")
                return False
        
        # Group analysis only supports cortical analysis
        if not self.type_cortical.isChecked():
            QtWidgets.QMessageBox.warning(self, "Warning", "Group analysis only supports cortical analysis. Spherical analysis is not available.")
            return False
            
        # Atlas validation for cortical analysis
        if self.space_mesh.isChecked():
            # Mesh cortical uses shared atlas name
            if not self.atlas_name_combo.currentText():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a shared mesh atlas name for cortical analysis.")
                return False
        else:
            # Voxel cortical - check if we have valid atlases for all subjects
            if not self.group_atlas_config:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please ensure valid atlases are available for all selected subjects (Voxel Cortical).")
                return False
                    
        return self.validate_analysis_parameters()
    
    def validate_analysis_parameters(self): # Shared parameters
        if self.type_spherical.isChecked():
            try:
                float(self.coord_x.text() or "0"); float(self.coord_y.text() or "0"); float(self.coord_z.text() or "0")
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid numeric coordinates.")
                return False
            try:
                radius = float(self.radius_input.text() or "0")
                if radius <= 0: raise ValueError("Radius must be positive")
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a valid positive radius.")
                return False
        elif self.type_cortical.isChecked():
            # Atlas selection for cortical is handled by validate_single/group_inputs
            if not self.whole_head_check.isChecked() and not self.region_input.text().strip():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a region name or select whole head analysis.")
                return False
        return True
    
    def run_analysis(self):
        if self.analysis_running:
            self.update_output("Analysis already running. Please wait or stop the current run.")
            return
        if not self.validate_inputs(): return

        details, title = "", ""
        if self.is_group_mode:
            selected_s = [item.text() for item in self.subject_list.selectedItems()]
            details = self.get_group_analysis_details(selected_s)
            title = f"Confirm Group Analysis ({len(selected_s)} subjects)"
        else:
            details = self.get_single_analysis_details()
            title = "Confirm Single Analysis"
        
        if not ConfirmationDialog.confirm(self, title=title, message="Are you sure you want to start the analysis?", details=details):
            self.update_output("Analysis cancelled by user.")
            return
        
        self.analysis_running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.disable_controls()
        
        if self.is_group_mode:
            self.run_group_analysis()
        else:
            self.run_single_analysis()
    
    def run_single_analysis(self):
        try:
            # In single mode, use the first selected subject (or the only one if validation passed)
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            subject_id = selected_subjects[0]  # Take first selected subject
            
            field_path = self.get_selected_field_path() # Uses currentData from field_combo
            if not field_path: # Should be caught by validation, but double check
                self.update_output("Error: Field path not selected for single analysis.")
                self.analysis_finished(success=False)
                return

            # Infer simulation_name from field_path (original had simulation_name from combo)
            # Let's use the combo for simulation_name as per original structure
            simulation_name = self.simulation_combo.currentText()
            if simulation_name == "Select montage...":
                 self.update_output("Error: Montage not selected for single analysis.")
                 self.analysis_finished(success=False)
                 return

            cmd = self.build_analysis_command(subject_id, simulation_name, field_path)
            if not cmd: # build_analysis_command returns None on error
                self.analysis_finished(success=False)
                return
            
            env = os.environ.copy()
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            env['PROJECT_DIR'] = f"/mnt/{project_dir_name}"
            env['SUBJECT_ID'] = subject_id # Passed to script via env
            
            self.update_output(f"Running single subject analysis for: {subject_id}")
            self.update_output(f"Montage: {simulation_name}")
            self.update_output(f"Command: {' '.join(cmd)}")
            
            self.optimization_process = AnalysisThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.finished.connect(
                lambda sid=subject_id, sim_name=simulation_name: self.analysis_finished(subject_id=sid, simulation_name=sim_name, success=True)
            )
            self.optimization_process.start()
        except Exception as e:
            self.update_output(f"Error preparing single analysis: {str(e)}")
            self.analysis_finished(success=False)
    
    def run_group_analysis(self):
        self.current_group_subjects = [item.text() for item in self.subject_list.selectedItems()]
        if not self.current_group_subjects:
            self.update_output("No subjects selected for group analysis.")
            self.analysis_finished(success=False)
            return
        
        self.update_output(f"Starting group analysis for subjects: {', '.join(self.current_group_subjects)}")
        self.run_next_subject_in_group()
    
    def run_next_subject_in_group(self):
        if not self.current_group_subjects:
            self.update_output("Group analysis batch completed.")
            self.analysis_finished(success=True) # Entire batch finished
            return

        subject_id = self.current_group_subjects.pop(0)
        
        try:
            # Use common montage for all subjects
            montage_name = self.group_montage_config.get('common_montage')
            # Use auto-selected field path for this subject
            field_path = self.group_field_config.get(subject_id)

            if not montage_name:
                self.update_output(f"Skipping subject {subject_id}: No common montage configured.")
                QtCore.QTimer.singleShot(0, self.run_next_subject_in_group) # Schedule next
                return
                
            if not field_path:
                self.update_output(f"Skipping subject {subject_id}: No auto-selected field file found.")
                QtCore.QTimer.singleShot(0, self.run_next_subject_in_group) # Schedule next
                return

            cmd = self.build_analysis_command(subject_id, montage_name, field_path)
            if not cmd:
                self.update_output(f"Skipping subject {subject_id}: Could not build command (check configurations).")
                QtCore.QTimer.singleShot(0, self.run_next_subject_in_group)
                return

            env = os.environ.copy()
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            env['PROJECT_DIR'] = f"/mnt/{project_dir_name}"
            env['SUBJECT_ID'] = subject_id
            
            self.update_output(f"\n{'='*15} Group Analysis: Subject {subject_id} ({len(self.current_group_subjects)} remaining) {'='*15}")
            self.update_output(f"Common Montage: {montage_name}")
            self.update_output(f"Command: {' '.join(cmd)}")
            
            # Create and start thread
            self.analysis_process = AnalysisThread(cmd, env)
            self.analysis_process.output_signal.connect(self.update_output)
            self.analysis_process.finished.connect(
                lambda sid=subject_id, mname=montage_name: self.on_group_subject_finished(sid, mname)
            )
            self.analysis_process.start()
            
        except Exception as e:
            self.update_output(f"Error running analysis for subject {subject_id}: {str(e)}")
            QtCore.QTimer.singleShot(0, self.run_next_subject_in_group) # Try next
    
    def on_group_subject_finished(self, subject_id, montage_name):
        # Called when one subject in the group finishes
        analysis_type_str = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
        self.analysis_completed.emit(subject_id, montage_name, analysis_type_str) # Emit for this subject
        self.update_output(f"Finished analysis for subject: {subject_id} (Montage: {montage_name})")
        self.run_next_subject_in_group() # Proceed to the next one
    
    def build_analysis_command(self, subject_id, simulation_name, field_path):
        try:
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            project_dir = f"/mnt/{project_dir_name}"
            
            target_info = ""
            if self.type_spherical.isChecked():
                coords = [c.text().strip() or "0" for c in [self.coord_x, self.coord_y, self.coord_z]]
                radius_val = self.radius_input.text().strip() or "5"
                target_info = f"sphere_x{coords[0]}_y{coords[1]}_z{coords[2]}_r{radius_val}"
            else: # Cortical
                atlas_name_cleaned = "unknown_atlas"
                if self.space_mesh.isChecked():
                    atlas_name_cleaned = self.atlas_name_combo.currentText().replace("+", "_").replace(".", "_")
                else: # Voxel
                    atlas_config_for_subj = {}
                    if self.is_group_mode:
                        atlas_config_for_subj = self.group_atlas_config.get(subject_id, {})
                    else: # Single mode voxel
                        atlas_config_for_subj = {'name': self.atlas_combo.currentText(), 'path': self.atlas_combo.currentData()}
                    
                    if atlas_config_for_subj.get('name'):
                        atlas_name_cleaned = atlas_config_for_subj['name'].split('+')[0].replace('.mgz','').replace('.nii.gz','').replace('.nii','')
                    else:
                        return None

                if self.whole_head_check.isChecked():
                    target_info = f"whole_head_{atlas_name_cleaned}"
                else:
                    region_val = self.region_input.text().strip()
                    if not region_val:
                        return None
                    target_info = f"region_{region_val}_{atlas_name_cleaned}"
            
            field_name_for_cmd = ""
            if self.space_mesh.isChecked():
                if self.is_group_mode:
                    # Use common field name for all subjects in group mode
                    field_name_for_cmd = self.group_field_name_input.text().strip()
                else: 
                    field_name_for_cmd = self.field_name_input.text().strip()
                if not field_name_for_cmd:
                     return None

            analysis_space_folder = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
            if simulation_name == "Select montage...":
                 return None

            output_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}',
                                      'Simulations', simulation_name, 'Analyses',
                                      analysis_space_folder, target_info)

            if not self.is_group_mode:
                if os.path.exists(output_dir) and not confirm_overwrite(self, output_dir, "analysis output directory"):
                    return None
            os.makedirs(output_dir, exist_ok=True)

            app_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            main_analyzer_script_path = os.path.join(app_root_dir, 'analyzer', 'main_analyzer.py')
            if not os.path.exists(main_analyzer_script_path):
                return None

            m2m_path = self.get_m2m_dir_for_subject(subject_id)
            if not m2m_path or not os.path.isdir(m2m_path):
                 return None

            cmd = [ 'simnibs_python', main_analyzer_script_path,
                    '--m2m_subject_path', m2m_path,
                    '--field_path', field_path,
                    '--space', 'mesh' if self.space_mesh.isChecked() else 'voxel',
                    '--analysis_type', 'spherical' if self.type_spherical.isChecked() else 'cortical',
                    '--output_dir', output_dir ]

            if self.type_spherical.isChecked():
                coords_str = [self.coord_x.text().strip() or "0", self.coord_y.text().strip() or "0", self.coord_z.text().strip() or "0"]
                cmd.extend(['--coordinates'] + coords_str)
                cmd.extend(['--radius', self.radius_input.text().strip() or "5"])
            else: # Cortical
                if self.space_mesh.isChecked():
                    cmd.extend(['--atlas_name', self.atlas_name_combo.currentText()])
                else: # Voxel Cortical
                    atlas_path_for_script = None
                    if self.is_group_mode:
                        atlas_cfg = self.group_atlas_config.get(subject_id)
                        if atlas_cfg: atlas_path_for_script = atlas_cfg.get('path')
                    else: # Single mode voxel
                        atlas_path_for_script = self.atlas_combo.currentData()
                    
                    if not atlas_path_for_script:
                        return None
                    cmd.extend(['--atlas_path', atlas_path_for_script])
                
                if self.whole_head_check.isChecked(): cmd.append('--whole_head')
                else: cmd.extend(['--region', self.region_input.text().strip()])
            
            if self.space_mesh.isChecked() and field_name_for_cmd:
                cmd.extend(['--field_name', field_name_for_cmd])
            if self.visualize_check.isChecked(): cmd.append('--visualize')
            return cmd
        except Exception:
            return None

    def get_single_analysis_details(self):
        if not self.subject_list.selectedItems(): return "No subject selected."
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        subj = selected_subjects[0]  # Use first selected subject
        space = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
        atype = 'Spherical' if self.type_spherical.isChecked() else 'Cortical'
        mont = self.simulation_combo.currentText()
        fpath = self.field_combo.currentText()
        details = f"• Subject: {subj}\n• Space: {space}\n• Analysis Type: {atype}\n• Montage: {mont}\n• Field File: {fpath}\n"
        if len(selected_subjects) > 1:
            details += f"• Note: Using first selected subject ({subj}) for single analysis\n"
        if self.space_mesh.isChecked(): details += f"• Field Name: {self.field_name_input.text()}\n"
        if self.type_spherical.isChecked():
            details += (f"• Coordinates: ({self.coord_x.text() or '0'}, {self.coord_y.text() or '0'}, {self.coord_z.text() or '0'})\n"
                        f"• Radius: {self.radius_input.text() or '5'} mm\n")
        else: # Cortical
            if self.space_mesh.isChecked(): details += f"• Mesh Atlas: {self.atlas_name_combo.currentText()}\n"
            else: details += f"• Voxel Atlas File: {self.atlas_combo.currentText()} (Path: {self.atlas_combo.currentData() or 'N/A'})\n" # Show path
            if self.whole_head_check.isChecked(): details += "• Analysis Target: Whole Head\n"
            else: details += f"• Region: {self.region_input.text()}\n"
        details += f"• Generate Visualizations: {'Yes' if self.visualize_check.isChecked() else 'No'}"
        return details

    def get_group_analysis_details(self, subjects):
        space = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
        details = (f"• Subjects: {', '.join(subjects)}\n• Space: {space}\n• Analysis Type: Cortical (only type supported in group mode)\n")
        
        # Common configuration
        details += "\n• Common Configuration (Applied to All Subjects):\n"
        common_montage = self.group_montage_config.get('common_montage', 'N/A')
        details += f"  - Common Montage: {common_montage}\n"
        
        # Field configuration details
        if self.group_field_config:
            field_count = len(self.group_field_config)
            details += f"  - Field Files: Auto-selected grey matter subject space files for {field_count} subjects\n"
            if self.space_mesh.isChecked():
                field_name = self.group_field_name_input.text().strip() or 'N/A'
                details += f"  - Field Name (Mesh): {field_name}\n"
        else:
            details += f"  - Field Files: None auto-selected\n"
        
        # Shared analysis parameters (cortical only)
        details += "\n• Shared Analysis Parameters:\n"
        if self.space_mesh.isChecked(): 
            details += f"• Shared Mesh Atlas: {self.atlas_name_combo.currentText()}\n"
        else:
            details += f"• Voxel Atlas: Common atlas configuration\n"
        if self.whole_head_check.isChecked(): 
            details += "• Analysis Target: Whole Head (for all)\n"
        else: 
            details += f"• Region: {self.region_input.text()} (for all)\n"
        details += f"• Generate Visualizations: {'Yes' if self.visualize_check.isChecked() else 'No'}"
        return details

    def analysis_finished(self, subject_id=None, simulation_name=None, success=True):
        if hasattr(self, '_processing_analysis_finished_lock') and self._processing_analysis_finished_lock: return
        self._processing_analysis_finished_lock = True
        try:
            if success:
                last_line = self.output_console.toPlainText().strip().split('\n')[-1] if self.output_console.toPlainText() else ""
                if "WARNING: Analysis Failed" in last_line or "Error: Process returned non-zero" in last_line or "failed" in last_line.lower():
                    self.update_output('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">❌ Analysis process indicated failure.</span></div>')
                else:
                    self.update_output('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">✅ Analysis process completed.</span></div>')
                
                if not self.is_group_mode or not self.current_group_subjects: # Single mode OR end of group batch
                    if subject_id and simulation_name: # From single analysis that just finished
                         analysis_type_str = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
                         self.analysis_completed.emit(subject_id, simulation_name, analysis_type_str)
            else:
                 self.update_output('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">❌ Analysis process failed or was cancelled by user.</span></div>')

            self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
            self.analysis_running = False
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.enable_controls()
        finally:
            self._processing_analysis_finished_lock = False

    def stop_analysis(self):
        if hasattr(self, 'optimization_process') and self.optimization_process and self.optimization_process.isRunning():
            self.update_output("Attempting to stop analysis...")
            if self.optimization_process.terminate_process(): # This sets self.terminated in thread
                self.update_output("Analysis process termination requested. Please wait...")
                # Thread will emit finished signal, which calls analysis_finished
            else: # Should not happen if isRunning is true
                self.update_output("Analysis process was not running or already terminated (unexpected).")
                self.analysis_finished(success=False) 
        else:
            self.update_output("No analysis process to stop.")
            # If UI was stuck in disabled state but no process, reset it
            if self.analysis_running: # If flag was true but no process
                self.analysis_finished(success=False)
            else: # Just ensure UI is enabled
                self.enable_controls()
        # Fallback UI reset in case thread doesn't signal quickly or gets stuck
        # This might be too aggressive if thread is just taking time to terminate
        # QtCore.QTimer.singleShot(3000, self._ensure_ui_reset_after_stop)

    # def _ensure_ui_reset_after_stop(self): # Helper for delayed UI reset
    #     if self.analysis_running: # If still marked as running after timeout
    #         print("Timeout: Forcing UI reset after stop request.")
    #         self.analysis_finished(success=False)


    def clear_console(self):
        self.output_console.clear()
    
    def update_output(self, text): # This is the method used by AnalysisThread's signal
        if not text or not text.strip(): return
        
        formatted_text = text
        # Basic coloring, can be expanded
        if "Error:" in text or "CRITICAL:" in text or "Failed" in text or "failed" in text or "ERROR:" in text:
            formatted_text = f'<span style="color: #ff5555;"><b>{text}</b></span>'
        elif "Warning:" in text or "WARNING:" in text:
            formatted_text = f'<span style="color: #ffff55;">{text}</span>'
        elif "DEBUG" in text: # For our new debug messages
            formatted_text = f'<span style="color: #7f7f7f;"><i>{text}</i></span>' # Italic grey
        elif "Command:" in text or "Running" in text or "Executing" in text:
            formatted_text = f'<span style="color: #55aaff;">{text}</span>'
        elif "completed successfully" in text or "completed." in text or "Successfully" in text or "completed:" in text:
            formatted_text = f'<span style="color: #55ff55;"><b>{text}</b></span>'
        elif "Processing" in text or "Starting" in text:
            formatted_text = f'<span style="color: #55ffff;">{text}</span>'
        elif "Analysis Results Summary:" in text:
            formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #55ff55; font-weight: bold; font-size: 14px;">{text}</span></div>'
        elif any(value_type in text for value_type in ["Mean Value:", "Max Value:", "Min Value:", "Focality:"]):
            # Extract the value type and the numeric value
            parts = text.split(":")
            if len(parts) == 2:
                value_type, value = parts
                formatted_text = f'<div style="margin: 5px 20px;"><span style="color: #aaaaaa;">{value_type}:</span> <span style="color: #55ffff; font-weight: bold;">{value}</span></div>'
            else:
                formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        elif text.strip().startswith("-"):
            # Indented list items
            formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
        else:
            formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        
        # Append to the console with HTML formatting
        self.output_console.append(formatted_text)
        self.output_console.ensureCursorVisible()
        # QtWidgets.QApplication.processEvents() # Generally avoid

    def disable_controls(self):
        # List of widgets to disable, similar to original
        widgets_to_set_enabled = [
            self.list_subjects_btn, self.select_all_subjects_btn, self.clear_subject_selection_btn,
            self.subject_list, self.subject_combo, self.single_mode_radio, self.group_mode_radio,
            self.simulation_combo, self.field_combo, self.browse_field_btn, self.field_name_input,
            self.space_mesh, self.space_voxel, self.type_spherical, self.type_cortical,
            self.coord_x, self.coord_y, self.coord_z, self.radius_input,
            self.view_in_freeview_btn,
            self.atlas_name_combo, self.atlas_combo, self.show_regions_btn, self.region_input, self.whole_head_check,
            self.visualize_check, self.mesh_combo, self.launch_gmsh_btn
        ]
        for widget in widgets_to_set_enabled:
            if hasattr(widget, 'setEnabled'): widget.setEnabled(False)

        if self.is_group_mode: # Also disable group configuration widgets
            if hasattr(self, 'group_montage_combo'):
                self.group_montage_combo.setEnabled(False)
            if hasattr(self, 'group_field_name_input'):
                self.group_field_name_input.setEnabled(False)
            if hasattr(self, 'show_selected_fields_btn'):
                self.show_selected_fields_btn.setEnabled(False)
            # Keep spherical analysis disabled in group mode
            self.type_spherical.setEnabled(False)
        
        self.status_label.setText("Processing... Stop button is available.")
        self.status_label.show()

    def enable_controls(self):
        widgets_to_set_enabled = [
            self.list_subjects_btn, self.select_all_subjects_btn, self.clear_subject_selection_btn,
            self.subject_list, self.subject_combo, self.single_mode_radio, self.group_mode_radio,
            self.simulation_combo, self.field_combo, self.browse_field_btn, # field_name_input handled by atlas_visibility
            self.space_mesh, self.space_voxel, self.type_spherical, self.type_cortical,
            self.coord_x, self.coord_y, self.coord_z, self.radius_input,
            self.view_in_freeview_btn,
            # atlas_name_combo, atlas_combo, show_regions_btn, region_input, whole_head_check handled by update_atlas_visibility
            self.visualize_check, self.mesh_combo # launch_gmsh_btn handled by its own update
        ]
        for widget in widgets_to_set_enabled:
             if hasattr(widget, 'setEnabled'): widget.setEnabled(True)
        
        self.update_atlas_visibility() # This will correctly set enable states for atlas/region and field_name_input
        self.update_gmsh_button_state()

        if self.is_group_mode:
            if hasattr(self, 'group_montage_combo'):
                self.group_montage_combo.setEnabled(True)
            if hasattr(self, 'group_field_name_input'):
                # Field name input should only be enabled for mesh analysis
                self.group_field_name_input.setEnabled(self.space_mesh.isChecked())
            if hasattr(self, 'show_selected_fields_btn'):
                # Button state depends on whether fields are selected
                self.show_selected_fields_btn.setEnabled(bool(self.group_field_config))
            # Keep spherical analysis disabled in group mode
            self.type_spherical.setEnabled(False)
        else:
            # In single mode, spherical analysis should be enabled
            self.type_spherical.setEnabled(True)

        self.status_label.hide()

    def update_simulations(self): # For single mode montage
        if self.is_group_mode: return
        
        current_sim_text = self.simulation_combo.currentText()
        self.simulation_combo.clear()
        self.simulation_combo.addItem("Select montage...")
        # self.field_combo.clear() # Field combo is updated by update_field_files
        # self.field_combo.addItem("Select field file...") # Placeholder added by update_field_files

        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            self.simulation_combo.setCurrentIndex(0)
            self.update_field_files() # Clear/reset field files
            return
            
        subject_id = selected_subjects[0]
        project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
        simulations_dir = os.path.join(f"/mnt/{project_dir_name}", 'derivatives', 'SimNIBS', f'sub-{subject_id}', 'Simulations')
        
        if not os.path.exists(simulations_dir):
            self.simulation_combo.setCurrentIndex(0)
            self.update_field_files()
            return
            
        simulations = sorted([d for d in os.listdir(simulations_dir) if os.path.isdir(os.path.join(simulations_dir, d))])
        self.simulation_combo.addItems(simulations)

        idx = self.simulation_combo.findText(current_sim_text)
        if idx != -1: self.simulation_combo.setCurrentIndex(idx)
        elif simulations: self.simulation_combo.setCurrentIndex(1) # Select first actual if previous not found
        else: self.simulation_combo.setCurrentIndex(0)
        # update_field_files is connected to currentTextChanged of simulation_combo

    def update_field_files(self): # For single mode fields
        if self.is_group_mode: return
        
        # Preserve current selection to try and restore it
        current_field_text = self.field_combo.currentText()
        current_field_data = self.field_combo.currentData() # Path

        self.field_combo.clear()
        self.field_combo.addItem("Select field file...")
        
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects or self.simulation_combo.currentIndex() == 0:
            self.field_combo.setCurrentIndex(0)
            return
            
        subject_id = selected_subjects[0]
        simulation_name = self.simulation_combo.currentText()
        project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
        
        base_sim_dir = os.path.join(f"/mnt/{project_dir_name}", 'derivatives', 'SimNIBS', 
                                    f'sub-{subject_id}', 'Simulations', simulation_name)
        search_dir = ""
        if self.space_mesh.isChecked():
            search_dir = os.path.join(base_sim_dir, 'TI', 'mesh')
        else: # voxel
            search_dir = os.path.join(base_sim_dir, 'TI', 'niftis')
        
        if not os.path.exists(search_dir):
            self.field_combo.setCurrentIndex(0)
            return
            
        try:
            all_files_in_dir = os.listdir(search_dir)
        except Exception as e:
            print(f"Error reading dir {search_dir}: {str(e)}")
            self.field_combo.setCurrentIndex(0)
            return
            
        # Original filtering and sorting logic for single mode
        field_files_paths = [] # Store (display_name, full_path)
        if self.space_mesh.isChecked():
            mesh_files = sorted([f for f in all_files_in_dir if f.endswith('.msh') and not f.endswith('.msh.opt')])
            for f_name in mesh_files: field_files_paths.append((f_name, os.path.join(search_dir, f_name)))
        else: # Voxel
            nifti_mgz_files = [f for f in all_files_in_dir if any(f.endswith(ext) for ext in ['.nii', '.nii.gz', '.mgz'])]
            grey_non_mni = sorted([f for f in nifti_mgz_files if f.startswith('grey_') and '_MNI_' not in f])
            grey_mni = sorted([f for f in nifti_mgz_files if f.startswith('grey_') and '_MNI_' in f])
            other_vol = sorted([f for f in nifti_mgz_files if not f.startswith('grey_')])
            
            for f_name in grey_non_mni: field_files_paths.append((f_name, os.path.join(search_dir, f_name)))
            for f_name in grey_mni: field_files_paths.append((f_name, os.path.join(search_dir, f_name)))
            for f_name in other_vol: field_files_paths.append((f_name, os.path.join(search_dir, f_name)))
        
        if not field_files_paths:
            self.field_combo.setCurrentIndex(0)
            return
        
        for display, path_val in field_files_paths:
            self.field_combo.addItem(display, path_val)

        # Attempt to restore previous selection
        restored_idx = -1
        if current_field_data: # Try by path first
            for i in range(self.field_combo.count()):
                if self.field_combo.itemData(i) == current_field_data:
                    restored_idx = i; break
        if restored_idx == -1 and current_field_text != "Select field file...": # Then by text
             restored_idx = self.field_combo.findText(current_field_text)

        if restored_idx != -1 and restored_idx !=0 :
            self.field_combo.setCurrentIndex(restored_idx)
        elif self.field_combo.count() > 1: # Default selection if not restored
            if not self.space_mesh.isChecked() and grey_non_mni: # Voxel: prefer first non-MNI grey
                idx_pref = self.field_combo.findText(grey_non_mni[0])
                if idx_pref != -1 : self.field_combo.setCurrentIndex(idx_pref)
                else: self.field_combo.setCurrentIndex(1)
            elif self.space_mesh.isChecked() and any(f.startswith('grey_') for f,p in field_files_paths): # Mesh: prefer first grey
                first_grey = next((f for f,p in field_files_paths if f.startswith('grey_')), None)
                if first_grey:
                    idx_pref = self.field_combo.findText(first_grey)
                    if idx_pref != -1: self.field_combo.setCurrentIndex(idx_pref)
                    else: self.field_combo.setCurrentIndex(1)
                else: self.field_combo.setCurrentIndex(1)
            else: # Fallback to first actual item
                self.field_combo.setCurrentIndex(1) 
        else: # Only placeholder left
             self.field_combo.setCurrentIndex(0)


    def get_selected_field_path(self): # For single mode
        if self.is_group_mode or self.field_combo.currentIndex() == 0:
            return None
        return self.field_combo.currentData() # Path stored in item data

    def show_available_regions(self): # For single mode "List Regions"
        try:
            selected_subjects = self.get_selected_subjects()
            if not selected_subjects:
                QtWidgets.QMessageBox.warning(self, "Selection Error", "Please select a subject first.")
                return

            progress_dialog = QtWidgets.QProgressDialog("Loading atlas regions...", "Cancel", 0, 100, self)
            progress_dialog.setWindowTitle("Loading Atlas Regions"); progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
            progress_dialog.setMinimumDuration(200); progress_dialog.setValue(0)

            atlas_type_display, regions = "", []
            subject_id = selected_subjects[0]

            if self.space_mesh.isChecked(): # Mesh Atlas
                atlas_name_simnibs = self.atlas_name_combo.currentText()
                if not atlas_name_simnibs: QtWidgets.QMessageBox.warning(self, "Atlas Error", "Select mesh atlas."); return
                atlas_type_display = atlas_name_simnibs
                m2m_dir = self.get_m2m_dir_for_subject(subject_id)
                if not m2m_dir: QtWidgets.QMessageBox.critical(self, "Error", f"m2m dir not found: {subject_id}."); return
                
                print(f"Loading {atlas_type_display} mesh regions for {subject_id} from {m2m_dir}...")
                progress_dialog.setValue(20); QtWidgets.QApplication.processEvents()
                try:
                    import simnibs
                    atlas = simnibs.subject_atlas(atlas_name_simnibs, m2m_dir)
                    regions = sorted(atlas.keys())
                    progress_dialog.setValue(80); QtWidgets.QApplication.processEvents()
                except ImportError: QtWidgets.QMessageBox.critical(self, "Import Error", "SimNIBS lib not found."); progress_dialog.cancel(); return
                except Exception as e: QtWidgets.QMessageBox.critical(self, "Load Error", f"Load mesh atlas fail: {e}"); progress_dialog.cancel(); print(traceback.format_exc()); return
            
            else: # Voxel Atlas
                atlas_path = self.atlas_combo.currentData() # Path from single mode combo
                if not atlas_path or not os.path.exists(atlas_path): QtWidgets.QMessageBox.warning(self, "Atlas Error", "Select valid voxel atlas."); return
                atlas_type_display = os.path.basename(atlas_path)
                print(f"Extracting regions from voxel atlas: {atlas_type_display}...")
                progress_dialog.setValue(20); QtWidgets.QApplication.processEvents()

                # Original mri_segstats logic
                seg_dir = os.path.dirname(atlas_path)
                atlas_bname = os.path.splitext(os.path.basename(atlas_path))[0]
                if atlas_bname.endswith('.nii'): atlas_bname = os.path.splitext(atlas_bname)[0]
                labels_file = os.path.join(seg_dir, f"{atlas_bname}_labels.txt") # Original name

                if not os.path.exists(labels_file): # Check for _labels.txt
                    cmd_mri_segstats = ['mri_segstats', '--seg', atlas_path, '--excludeid', '0', '--ctab-default', '--sum', labels_file]
                    print(f"Running: {' '.join(cmd_mri_segstats)}")
                    progress_dialog.setLabelText("Running mri_segstats...");
                    
                    qprocess = QtCore.QProcess(self) # Use QProcess for non-blocking with UI updates
                    qprocess.setProcessChannelMode(QtCore.QProcess.MergedChannels)
                    qprocess.start(cmd_mri_segstats[0], cmd_mri_segstats[1:])
                    
                    while qprocess.state() == QtCore.QProcess.Starting or qprocess.state() == QtCore.QProcess.Running:
                        if progress_dialog.wasCanceled(): qprocess.kill(); print("mri_segstats cancelled."); return
                        QtWidgets.QApplication.processEvents(); QtCore.QThread.msleep(50)
                        prog_val = progress_dialog.value(); 
                        if prog_val < 70: progress_dialog.setValue(prog_val + 1)

                    if qprocess.exitStatus() != QtCore.QProcess.NormalExit or qprocess.exitCode() != 0:
                        output_err = qprocess.readAll().data().decode(errors='ignore')
                        QtWidgets.QMessageBox.critical(self, "mri_segstats Error", f"mri_segstats failed:\n{output_err}"); progress_dialog.cancel(); return
                    print("mri_segstats completed.")
                else: print(f"Using existing labels file: {labels_file}")

                progress_dialog.setLabelText("Parsing regions..."); progress_dialog.setValue(75); QtWidgets.QApplication.processEvents()
                with open(labels_file, 'r') as f_in: lines = f_in.readlines()
                
                # Original parsing logic for mri_segstats --sum output
                in_header_flag = True
                for line in lines:
                    if in_header_flag and not line.startswith('#'): in_header_flag = False
                    if not in_header_flag and line.strip():
                        parts = line.strip().split()
                        if len(parts) >= 5: # StructName can have spaces
                            region_name_val = ' '.join(parts[4:]) # Original index
                            region_id_val = parts[1] # SegId original index
                            regions.append(f"{region_name_val} (ID: {region_id_val})")
                regions = sorted(list(set(regions)))
                progress_dialog.setValue(90)

            if not regions: QtWidgets.QMessageBox.information(self, "No Regions", f"No regions for: {atlas_type_display}"); progress_dialog.cancel(); return
            progress_dialog.setValue(95)
            
            # Dialog display logic (original)
            dialog = QtWidgets.QDialog(self); dialog.setWindowTitle(f"Available Regions - {atlas_type_display}")
            dialog.setMinimumWidth(400); dialog.setMinimumHeight(500)
            layout_diag = QtWidgets.QVBoxLayout(dialog)
            search_layout_diag = QtWidgets.QHBoxLayout(); search_label_diag = QtWidgets.QLabel("Search:")
            search_input_diag = QtWidgets.QLineEdit(); search_layout_diag.addWidget(search_label_diag); search_layout_diag.addWidget(search_input_diag)
            layout_diag.addLayout(search_layout_diag)
            list_widget_diag = QtWidgets.QListWidget(); list_widget_diag.addItems(regions); layout_diag.addWidget(list_widget_diag)
            button_layout_diag = QtWidgets.QHBoxLayout(); copy_btn_diag = QtWidgets.QPushButton("Copy Selected")
            close_btn_diag = QtWidgets.QPushButton("Close"); button_layout_diag.addWidget(copy_btn_diag); button_layout_diag.addWidget(close_btn_diag)
            layout_diag.addLayout(button_layout_diag)
            progress_dialog.setValue(100); progress_dialog.close()

            def filter_regions_local(text_filt): # Renamed
                for i in range(list_widget_diag.count()): list_widget_diag.item(i).setHidden(text_filt.lower() not in list_widget_diag.item(i).text().lower())
            def copy_selected_local(): # Renamed
                curr_item = list_widget_diag.currentItem()
                if curr_item:
                    sel_text = curr_item.text()
                    region_name_part = sel_text.split(" (ID:")[0] # Extract name before ID
                    self.region_input.setText(region_name_part)
                    dialog.accept()
            
            search_input_diag.textChanged.connect(filter_regions_local)
            copy_btn_diag.clicked.connect(copy_selected_local)
            close_btn_diag.clicked.connect(dialog.reject)
            list_widget_diag.itemDoubleClicked.connect(lambda item: copy_selected_local())
            dialog.exec_()
        except Exception as e_show_regions:
            if 'progress_dialog' in locals() and progress_dialog.isVisible(): progress_dialog.cancel()
            QtWidgets.QMessageBox.critical(self, "Error Showing Regions", f"Failed: {str(e_show_regions)}")
            print(traceback.format_exc())


    def load_t1_in_freeview(self):
        try:
            selected_subjects = self.get_selected_subjects()
            if not selected_subjects: QtWidgets.QMessageBox.warning(self, "Warning", "Select subject."); return
            subject_id = selected_subjects[0]
            m2m_dir_path = self.get_m2m_dir_for_subject(subject_id)
            if not m2m_dir_path: QtWidgets.QMessageBox.warning(self, "Error", f"m2m dir not found for {subject_id}."); return
            
            t1_nii_gz_path = os.path.join(m2m_dir_path, "T1.nii.gz")
            t1_mgz_path = os.path.join(m2m_dir_path, "T1.mgz") # Check for .mgz too

            final_t1_path = None
            if os.path.exists(t1_nii_gz_path): final_t1_path = t1_nii_gz_path
            elif os.path.exists(t1_mgz_path): final_t1_path = t1_mgz_path
            
            if not final_t1_path:
                QtWidgets.QMessageBox.warning(self, "Error", f"T1 image (T1.nii.gz or T1.mgz) not found in {m2m_dir_path}")
                return
            
            subprocess.Popen(["freeview", final_t1_path])
            self.update_output(f"Launched Freeview with T1 image: {final_t1_path}")
        except FileNotFoundError: QtWidgets.QMessageBox.critical(self, "Error", "Freeview not found. Ensure installed and in PATH.")
        except Exception as e: QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Freeview: {str(e)}"); self.update_output(f"Error: {e}")

    def update_mesh_files(self): # For single mode Gmsh dropdown
        if self.is_group_mode: return
        self.mesh_combo.clear(); self.mesh_combo.addItem("Select mesh file...")
        
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects or self.simulation_combo.currentIndex() == 0:
            self.update_gmsh_button_state(); return
            
        subject_id = selected_subjects[0]
        simulation_name = self.simulation_combo.currentText()
        project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
        
        mesh_dir_gmsh = os.path.join(f"/mnt/{project_dir_name}", "derivatives", "SimNIBS", f"sub-{subject_id}", 
                                   "Simulations", simulation_name, "Analyses", "Mesh")
        
        mesh_files_to_list = []
        if os.path.exists(mesh_dir_gmsh):
            for root, _, files in os.walk(mesh_dir_gmsh):
                for file_item in files:
                    if file_item.endswith('.msh'):
                        full_path_item = os.path.join(root, file_item)
                        rel_path_display = os.path.relpath(full_path_item, mesh_dir_gmsh)
                        mesh_files_to_list.append((os.path.splitext(os.path.basename(rel_path_display))[0], full_path_item))
        
        mesh_files_to_list.sort(key=lambda x: x[0])
        for disp, path_val in mesh_files_to_list: self.mesh_combo.addItem(disp, path_val)
        
        self.update_gmsh_button_state()

    def launch_gmsh(self):
        if self.mesh_combo.currentIndex() == 0 or not self.mesh_combo.currentData():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a mesh file first"); return
        mesh_file_path_val = self.mesh_combo.currentData()
        if not mesh_file_path_val or not os.path.exists(mesh_file_path_val):
            QtWidgets.QMessageBox.warning(self, "Error", "Selected mesh file not found"); return

        # Original Gmsh script content
        gmsh_script_content = f'''// Gmsh script to load mesh with all mesh elements hidden
Mesh.SurfaceFaces = 0; Mesh.VolumeFaces = 0; Mesh.SurfaceEdges = 0; Mesh.VolumeEdges = 0;
Mesh.Points = 0; Mesh.Lines = 0;
Merge "{mesh_file_path_val.replace(os.sep, '/')}"; // Ensure forward slashes
General.Trackball = 1; General.RotationX = 0; General.RotationY = 0; General.RotationZ = 0;'''
        
        tmp_script_file = None
        try:
            import tempfile
            delete_flag = os.name != 'nt' # Don't auto-delete on Windows for Popen
            tmp_script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.geo', delete=delete_flag)
            tmp_script_file.write(gmsh_script_content)
            tmp_script_file.flush() # Ensure write
            
            subprocess.Popen(["gmsh", tmp_script_file.name])
            self.update_output(f"Launched Gmsh with mesh file: {mesh_file_path_val}")
            self.update_output("Gmsh display: 2D faces hidden, wireframe edges visible") # This was original message

            if not delete_flag: # If not auto-deleted (Windows), schedule cleanup
                def cleanup_gmsh_script(path_to_clean):
                    import time; time.sleep(5) # Wait for Gmsh to load
                    try: os.unlink(path_to_clean)
                    except Exception as e_clean: print(f"Warning: Could not delete tmp Gmsh script {path_to_clean}: {e_clean}")
                
                import threading
                threading.Thread(target=cleanup_gmsh_script, args=(tmp_script_file.name,), daemon=True).start()

        except FileNotFoundError: QtWidgets.QMessageBox.critical(self, "Error", "Gmsh not found. Install/add to PATH.")
        except Exception as e: QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Gmsh: {str(e)}"); self.update_output(f"Error: {e}")
        finally:
            if tmp_script_file and delete_flag: # If auto-delete was true (non-Windows)
                tmp_script_file.close() # This triggers deletion

    def update_gmsh_button_state(self):
        self.launch_gmsh_btn.setEnabled(self.mesh_combo.currentIndex() > 0 and bool(self.mesh_combo.currentData()))

    # populate_subject_montages and populate_subject_fields methods removed - no longer using individual subject tabs

    
    def populate_subject_atlases(self, subject_id, atlas_combo): # For group tab's per-subject atlas (if used)
        # This was the original method, likely intended for per-tab atlas selectors if they existed.
        # Current group atlas logic uses shared combos.
        atlas_combo.clear()
        atlas_files = self.get_available_atlas_files(subject_id)
        if not atlas_files:
            atlas_combo.addItem("No atlases found"); atlas_combo.setEnabled(False)
        elif isinstance(atlas_files[0], str) and atlas_files[0].startswith('⚠️'):
            atlas_combo.addItem(atlas_files[0]); atlas_combo.setEnabled(False)
        else:
            atlas_combo.setEnabled(True)
            for disp_name, path_val in atlas_files: # Original used file[0] as display
                atlas_combo.addItem(disp_name, path_val) # Store path as data
            if atlas_combo.count() > 0: atlas_combo.setCurrentIndex(0) # Select first valid
    
    # Old tab-related configuration methods removed - using common configuration approach now

    # Old auto-select helper methods removed - no longer using individual subject tabs

    def restore_single_mode_sizes(self):
        # Simplified - let layout managers handle sizing naturally
        pass

    def set_analysis_config_panel_size(self, mode):
        # Simplified - let layout managers handle sizing naturally
        pass
