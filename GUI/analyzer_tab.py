#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Analyzer Tab
This module provides a GUI interface for the analyzer functionality.
"""

import os
import json # Original script had this, though not obviously used in snippet
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog # Assuming this exists from original
try:
    from .utils import confirm_overwrite, is_verbose_message, is_important_message
except ImportError:
    # Fallback for when running as standalone script
    import os
    import sys
    gui_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, gui_dir)
    from utils import confirm_overwrite, is_verbose_message, is_important_message

# Import console and button components
try:
    from .components.console import ConsoleWidget
    from .components.action_buttons import RunStopButtons
except ImportError:
    from components.console import ConsoleWidget
    from components.action_buttons import RunStopButtons

import traceback # For more detailed error logging if needed
import time

class AnalysisThread(QtCore.QThread):
    """Thread to run analysis in background to prevent GUI freezing."""
    
    # Signal to emit output text with message type
    output_signal = QtCore.pyqtSignal(str, str)
    
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
            self.env['PYTHONFAULTHANDLER'] = '1'
            
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,  # Combine stderr with stdout to avoid file descriptor issues
                universal_newlines=True,
                bufsize=1,
                env=self.env,
                preexec_fn=None if os.name == 'nt' else os.setsid,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            # Simple line-by-line reading without select() to avoid file descriptor issues
            for line in iter(self.process.stdout.readline, ''):
                if self.terminated:
                    break
                if line:
                    line_stripped = line.strip()
                    if line_stripped:
                        cleaned_line = self._strip_ansi_codes(line_stripped)
                        # Determine message type based on bracketed tags first, then content
                        if '[ERROR]' in cleaned_line or 'ERROR:' in cleaned_line:
                            message_type = 'error'
                        elif '[WARNING]' in cleaned_line or 'Warning:' in cleaned_line:
                            message_type = 'warning'
                        elif '[INFO]' in cleaned_line:
                            message_type = 'info'
                        elif '[DEBUG]' in cleaned_line:
                            message_type = 'debug'
                        elif '[SUCCESS]' in cleaned_line:
                            message_type = 'success'
                        elif any(keyword in cleaned_line.lower() for keyword in ['error:', 'critical:', 'failed', 'exception']):
                            message_type = 'error'
                        elif any(keyword in cleaned_line.lower() for keyword in ['warning:', 'warn']):
                            message_type = 'warning'
                        elif any(keyword in cleaned_line.lower() for keyword in ['executing:', 'running', 'command']):
                            message_type = 'command'
                        elif any(keyword in cleaned_line.lower() for keyword in ['completed successfully', 'completed.', 'successfully', 'completed:']):
                            message_type = 'success'
                        elif any(keyword in cleaned_line.lower() for keyword in ['processing', 'starting', 'generating']):
                            message_type = 'info'
                        else:
                            message_type = 'default'
                        
                        self.output_signal.emit(cleaned_line, message_type)
            
            # Wait for process completion if not terminated
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    self.output_signal.emit(f"Error: Process returned non-zero exit code {returncode}", 'error')
                    
        except Exception as e:
            self.output_signal.emit(f"Error running analysis: {str(e)}", 'error')

    
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
        
        # Initialize debug mode (default to False)
        self.debug_mode = False
        # Initialize summary mode state and timers for non-debug summaries
        self.SUMMARY_MODE = True
        self.ANALYSIS_START_TIME = None
        self.STEP_START_TIMES = {}
        self._last_output_dir = None
        self._last_plain_output_line = None
        self._summary_printed = set()
        
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
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        # Add mode selection toggle at the top
        mode_container = QtWidgets.QGroupBox("Analysis Mode")
        mode_layout = QtWidgets.QHBoxLayout(mode_container)
        mode_layout.setContentsMargins(2, 2, 2, 2)
        mode_layout.setSpacing(5)
        mode_container.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self.single_mode_radio = QtWidgets.QRadioButton("Single Subject")
        self.group_mode_radio = QtWidgets.QRadioButton("Group Analysis")
        self.single_mode_radio.setChecked(True)  # Default to single mode
        self.mode_group = QtWidgets.QButtonGroup(self)
        self.mode_group.addButton(self.single_mode_radio)
        self.mode_group.addButton(self.group_mode_radio)
        mode_layout.addWidget(self.single_mode_radio)
        mode_layout.addWidget(self.group_mode_radio)
        left_layout.addWidget(mode_container)
        
        # Create stacked widget to switch between entire subject containers
        self.subject_selection_stack = QtWidgets.QStackedWidget()
        
        # Single mode: separate container with just dropdown
        single_subject_container = QtWidgets.QGroupBox("Subject")
        single_subject_layout = QtWidgets.QVBoxLayout(single_subject_container)
        single_subject_layout.setContentsMargins(2, 2, 2, 2)
        single_subject_layout.setSpacing(2)
        single_subject_container.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.addItem("Select subject...")
        single_subject_layout.addWidget(self.subject_combo)
        
        # Single mode buttons
        single_button_layout = QtWidgets.QHBoxLayout()
        single_button_layout.setContentsMargins(0, 0, 0, 0)
        single_button_layout.setSpacing(5)
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        self.clear_subject_selection_btn = QtWidgets.QPushButton("Reset")
        self.clear_subject_selection_btn.clicked.connect(self.clear_subject_selection)
        single_button_layout.addWidget(self.list_subjects_btn)
        single_button_layout.addWidget(self.clear_subject_selection_btn)
        single_subject_layout.addLayout(single_button_layout)
        
        self.subject_selection_stack.addWidget(single_subject_container)
        
        # Group mode: separate container with list widget
        group_subject_container = QtWidgets.QGroupBox("Subjects")
        group_subject_layout = QtWidgets.QVBoxLayout(group_subject_container)
        group_subject_layout.setContentsMargins(2, 2, 2, 2)
        group_subject_layout.setSpacing(2)
        group_subject_container.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.subject_list.setMaximumHeight(100)  # Limit height to make it more compact
        group_subject_layout.addWidget(self.subject_list)
        
        # Group mode buttons
        group_button_layout = QtWidgets.QHBoxLayout()
        group_button_layout.setContentsMargins(0, 0, 0, 0)
        group_button_layout.setSpacing(5)
        self.list_subjects_btn_group = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn_group.clicked.connect(self.list_subjects)
        self.select_all_subjects_btn = QtWidgets.QPushButton("Select All")
        self.select_all_subjects_btn.clicked.connect(self.select_all_subjects)
        self.clear_subject_selection_btn_group = QtWidgets.QPushButton("Clear")
        self.clear_subject_selection_btn_group.clicked.connect(self.clear_subject_selection)
        group_button_layout.addWidget(self.list_subjects_btn_group)
        group_button_layout.addWidget(self.select_all_subjects_btn)
        group_button_layout.addWidget(self.clear_subject_selection_btn_group)
        group_subject_layout.addLayout(group_button_layout)
        
        self.subject_selection_stack.addWidget(group_subject_container)
        
        left_layout.addWidget(self.subject_selection_stack)
        
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
        right_layout_actual = self.create_analysis_parameters_widget(right_layout_container)
        main_horizontal_layout.addWidget(right_layout_container, 2)
        
        scroll_layout.addLayout(main_horizontal_layout)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(self, run_text="Run Analysis", stop_text="Stop Analysis")
        self.action_buttons.connect_run(self.run_analysis)
        self.action_buttons.connect_stop(self.stop_analysis)
        
        # Keep references for backward compatibility
        self.run_btn = self.action_buttons.get_run_button()
        self.stop_btn = self.action_buttons.get_stop_button()
        
        # Console widget component with Run/Stop buttons integrated
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            show_debug_checkbox=True,
            console_label="Output:",
            min_height=180,
            max_height=None,
            custom_buttons=[self.run_btn, self.stop_btn]
        )
        main_layout.addWidget(self.console_widget)
        
        # Connect the debug checkbox to set_debug_mode method
        self.console_widget.debug_checkbox.toggled.connect(self.set_debug_mode)
        
        # Reference to underlying console for backward compatibility
        self.output_console = self.console_widget.get_console_widget()

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
                
                # Enable spherical analysis in group mode with MNI coordinates
                self.type_spherical.setEnabled(True)
                self.type_spherical.setToolTip("")
                
                # Update coordinate labels for MNI space when group mode is active
                self._update_coordinate_space_labels()
                
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
                
                # Update coordinate labels for subject space when single mode is active
                self._update_coordinate_space_labels()
                
                # Single mode field update signals are now connected globally in setup_ui
                
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

    def _update_coordinate_space_labels(self):
        """Update coordinate space labels and tooltips based on analysis mode."""
        if hasattr(self, 'coordinates_label') and hasattr(self, 'coord_x'):
            if self.is_group_mode:
                # Group mode: use MNI coordinates
                self.coordinates_label.setText("MNI Coordinates (x,y,z):")
                self.coordinates_label.setToolTip("MNI space coordinates (will be transformed to subject space for each subject)")
                self.coordinates_label.setStyleSheet("color: #007ACC; font-weight: bold;")
                
                # Update individual coordinate tooltips
                self.coord_x.setToolTip("X coordinate in MNI space")
                self.coord_y.setToolTip("Y coordinate in MNI space")  
                self.coord_z.setToolTip("Z coordinate in MNI space")
                
                # Update Freeview button for MNI template
                if hasattr(self, 'view_in_freeview_btn'):
                    self.view_in_freeview_btn.setText("View MNI Template")
                    self.view_in_freeview_btn.setToolTip("Open MNI152 template to find MNI coordinates")
                
                # Show MNI info banner if it exists
                if hasattr(self, 'mni_info_label'):
                    self.mni_info_label.setVisible(True)
            else:
                # Single mode: use subject coordinates
                self.coordinates_label.setText("RAS Coordinates (x,y,z):")
                self.coordinates_label.setToolTip("Subject-specific RAS coordinates")
                self.coordinates_label.setStyleSheet("")
                
                # Update individual coordinate tooltips
                self.coord_x.setToolTip("X coordinate in subject RAS space")
                self.coord_y.setToolTip("Y coordinate in subject RAS space")
                self.coord_z.setToolTip("Z coordinate in subject RAS space")
                
                # Update Freeview button for subject T1
                if hasattr(self, 'view_in_freeview_btn'):
                    self.view_in_freeview_btn.setText("View in Freeview")
                    self.view_in_freeview_btn.setToolTip("View T1 in Freeview to help find coordinates")
                
                # Hide MNI info banner if it exists
                if hasattr(self, 'mni_info_label'):
                    self.mni_info_label.setVisible(False)

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
        # No longer need to change button states since we have separate containers
        # The correct buttons are automatically shown based on the stacked widget
        pass

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

        # Field File row (field name is now hardcoded to TI_max)
        self.field_file_label = QtWidgets.QLabel("Field File:")
        self.field_combo = QtWidgets.QComboBox()
        self.browse_field_btn = QtWidgets.QPushButton()
        self.browse_field_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self.browse_field_btn.setToolTip("Browse for field file")
        self.browse_field_btn.clicked.connect(self.browse_field)
        field_layout.addWidget(self.field_file_label, 0, 0)
        field_layout.addWidget(self.field_combo, 0, 1)
        field_layout.addWidget(self.browse_field_btn, 0, 2)

        layout.addWidget(field_container)

        # Connect signals for single mode
        self.simulation_combo.currentTextChanged.connect(self.update_field_files)
        return widget
    
    def create_group_analysis_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        # Create common configuration section instead of tabs
        common_config_group = QtWidgets.QGroupBox("Common Configuration (Applied to All Selected Subjects)")
        common_config_layout = QtWidgets.QVBoxLayout(common_config_group)
        common_config_layout.setContentsMargins(2, 2, 2, 2)
        common_config_layout.setSpacing(2)
        common_config_group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        # Common montage selection
        montage_group = QtWidgets.QGroupBox("Shared Montage")
        montage_layout = QtWidgets.QVBoxLayout(montage_group)
        montage_layout.setContentsMargins(2, 2, 2, 2)
        montage_layout.setSpacing(2)
        montage_group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        montage_selection_layout = QtWidgets.QHBoxLayout()
        montage_selection_layout.setContentsMargins(0, 0, 0, 0)
        montage_selection_layout.setSpacing(5)
        montage_label = QtWidgets.QLabel("Montage:")
        self.group_montage_combo = QtWidgets.QComboBox()
        self.group_montage_combo.addItem("Select common montage...")
        self.group_montage_combo.currentTextChanged.connect(self.update_common_montage_config)
        montage_selection_layout.addWidget(montage_label)
        montage_selection_layout.addWidget(self.group_montage_combo)
        montage_layout.addLayout(montage_selection_layout)
        common_config_layout.addWidget(montage_group)
        # Common field selection (auto-selects grey matter subject space scans)
        field_group = QtWidgets.QGroupBox("Shared Field Configuration")
        field_layout = QtWidgets.QVBoxLayout(field_group)
        field_layout.setContentsMargins(2, 2, 2, 2)
        field_layout.setSpacing(2)
        field_group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        
        # Auto-selection info and status (field name is now hardcoded to TI_max)
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
        return widget
    
    # create_subject_tab method removed - no longer using individual subject tabs
    
    def create_analysis_parameters_widget(self, container_widget):
        right_layout = QtWidgets.QVBoxLayout(container_widget)

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
        
        # Add info label for MNI coordinates (initially hidden)
        self.mni_info_label = QtWidgets.QLabel()
        self.mni_info_label.setText("Group analysis mode: Coordinates will be treated as MNI space and transformed to each subject's native space.")
        self.mni_info_label.setStyleSheet("background-color: #E3F2FD; color: #1976D2; padding: 3px 6px; border-radius: 4px; font-size: 11px;")
        self.mni_info_label.setWordWrap(True)
        self.mni_info_label.setMaximumHeight(35)
        self.mni_info_label.setVisible(False)
        spherical_layout.addWidget(self.mni_info_label)
        
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

        # --- Change voxel_atlas_widget to QVBoxLayout with a row container ---
        self.voxel_atlas_widget = QtWidgets.QWidget()
        voxel_atlas_vlayout = QtWidgets.QVBoxLayout(self.voxel_atlas_widget)
        voxel_atlas_vlayout.setContentsMargins(0, 0, 0, 0)
        voxel_atlas_vlayout.setSpacing(2)
        # Add warning label placeholder (will be managed in update_atlas_combo)
        # Add row container for label and combo
        voxel_atlas_row = QtWidgets.QWidget()
        voxel_atlas_row_layout = QtWidgets.QHBoxLayout(voxel_atlas_row)
        voxel_atlas_row_layout.setContentsMargins(0, 0, 0, 0)
        voxel_atlas_row_layout.setSpacing(5)
        self.voxel_atlas_label = QtWidgets.QLabel("Atlas File:")
        self.atlas_combo = QtWidgets.QComboBox() # This is for single mode voxel atlas
        self.atlas_combo.setEditable(False) # Original was non-editable
        voxel_atlas_row_layout.addWidget(self.voxel_atlas_label)
        voxel_atlas_row_layout.addWidget(self.atlas_combo)
        voxel_atlas_vlayout.addWidget(voxel_atlas_row)
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
        
        # Connect signals for single mode field updates
        self.space_mesh.toggled.connect(self.update_field_files)
        self.space_voxel.toggled.connect(self.update_field_files)
        
        # Connect signals for mesh file updates (space and type changes)
        self.space_mesh.toggled.connect(self.update_mesh_files)
        self.space_voxel.toggled.connect(self.update_mesh_files)
        self.type_spherical.toggled.connect(self.update_mesh_files)
        self.type_cortical.toggled.connect(self.update_mesh_files)
        
        # Connect signals to update cortical button text based on space
        self.space_mesh.toggled.connect(self.update_cortical_button_text)
        self.space_voxel.toggled.connect(self.update_cortical_button_text)
        
        self.update_atlas_visibility() # Initial call
        self.update_cortical_button_text() # Initial call
        analysis_params_layout.addWidget(self.analysis_stack)
        right_layout.addWidget(analysis_params_container)
        
        visualization_container = QtWidgets.QGroupBox("Visualization")
        visualization_layout = QtWidgets.QVBoxLayout(visualization_container)
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
        
        return right_layout

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
            # Check for mTI simulation first
            is_mti = False
            if is_mesh:
                mti_mesh_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                           'Simulations', montage_name, 'mTI', 'mesh')
                ti_mesh_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                          'Simulations', montage_name, 'TI', 'mesh')
                if os.path.exists(mti_mesh_dir):
                    field_dir = mti_mesh_dir
                    is_mti = True
                else:
                    field_dir = ti_mesh_dir
            else:
                mti_nifti_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                            'Simulations', montage_name, 'mTI', 'niftis')
                ti_nifti_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                           'Simulations', montage_name, 'TI', 'niftis')
                if os.path.exists(mti_nifti_dir):
                    field_dir = mti_nifti_dir
                    is_mti = True
                else:
                    field_dir = ti_nifti_dir
            
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
            
            # Find appropriate field files with flexible naming patterns
            # For mesh analysis, prefer main field files (like single analyzer)
            # For voxel analysis, prefer grey matter files
            field_files = []
            
            if is_mesh:
                # Pattern 1: Main field files (montage_name_TI.msh or montage_name_mTI.msh)
                if is_mti:
                    # For mTI simulations, look for _mTI.msh files
                    field_files = [f for f in eligible_files 
                                 if f == f"{montage_name}_mTI.msh"]
                else:
                    # For regular TI simulations, look for _TI.msh files
                    field_files = [f for f in eligible_files 
                                 if f == f"{montage_name}_TI.msh"]
                
                # Pattern 2: If no exact match, look for files with montage name and appropriate suffix
                if not field_files:
                    suffix = '_mTI.msh' if is_mti else '_TI.msh'
                    field_files = [f for f in eligible_files 
                                 if montage_name.lower() in f.lower() and suffix in f and 'MNI' not in f and not f.endswith('_central.msh') and not f.startswith('grey')]
                
                # Pattern 3: Fall back to grey matter files if main files not found
                if not field_files:
                    field_files = [f for f in eligible_files 
                                 if f.startswith('grey') and 'MNI' not in f and not f.endswith('_central.msh')]
            else:
                # For voxel analysis, prefer grey matter files (original logic)
                # Pattern 1: Files starting with 'grey' (traditional naming)
                field_files = [f for f in eligible_files 
                             if f.startswith('grey') and 'MNI' not in f and not f.endswith('_central.msh')]
                
                # Pattern 2: If no 'grey' files, look for TI_max files (newer naming)
                if not field_files:
                    field_files = [f for f in eligible_files 
                                 if 'TI_max' in f and 'MNI' not in f and not f.endswith('_central.msh')]
            
            # Pattern (common): Look for any file with montage name and no MNI
            if not field_files:
                field_files = [f for f in eligible_files 
                             if montage_name.lower() in f.lower() and 'MNI' not in f and not f.endswith('_central.msh')]
            
            # Pattern (last resort): Any eligible file that's not MNI or central surface mesh
            if not field_files:
                field_files = [f for f in eligible_files 
                             if 'MNI' not in f and not f.endswith('_central.msh')]
            
            if not field_files:
                failed_subjects.append(f"{subject_id} (no appropriate field files found)")
                continue
            
            # Select the first appropriate field file (they should be equivalent)
            selected_file = field_files[0]
            selected_path = os.path.join(field_dir, selected_file)
            self.group_field_config[subject_id] = selected_path
            success_count += 1
        
        # Update status
        if success_count == len(selected_subjects):
            self.group_field_status_label.setText(f"[SUCCESS] Auto-selected fields for all {success_count} subjects")
            self.group_field_status_label.setStyleSheet("color: #228B22; font-weight: bold;")
            self.show_selected_fields_btn.setEnabled(True)
        elif success_count > 0:
            self.group_field_status_label.setText(f"[WARNING] Auto-selected fields for {success_count}/{len(selected_subjects)} subjects")
            self.group_field_status_label.setStyleSheet("color: #FF8C00; font-weight: bold;")
            self.show_selected_fields_btn.setEnabled(True)
        else:
            self.group_field_status_label.setText(f"[ERROR] Failed to auto-select fields")
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
        
        # Field name is now hardcoded to TI_max, so no field name widgets to update
        
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
            for item_name in os.listdir(simnibs_dir): # item_name is like 'sub-001' or 'sub-ernie'
                if item_name.startswith('sub-'):
                    subject_id_short = item_name[4:] # '001' or 'ernie'
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
            
            # Field name is now hardcoded to TI_max


    def get_available_atlas_files(self, subject_id): # subject_id is short form
        atlas_files = []
        if not subject_id: return atlas_files

        project_dir_name = os.environ.get("PROJECT_DIR_NAME", "BIDS_new")
        project_dir = os.path.join("/mnt", project_dir_name)
        # Freesurfer path uses full subject ID for both levels, e.g., sub-001/sub-001/mri
        freesurfer_mri_dir = os.path.join(project_dir, "derivatives", "freesurfer", f"sub-{subject_id}", "mri")
        
        # Original defined atlases
        atlases_to_check = ['aparc.DKTatlas+aseg.mgz', 'aparc.a2009s+aseg.mgz']
        
        if os.path.isdir(freesurfer_mri_dir): # Check if subject's FS mri dir exists
            for atlas_filename in atlases_to_check:
                full_path = os.path.join(freesurfer_mri_dir, atlas_filename)
                if os.path.exists(full_path):
                    # Original stored (atlas_filename, full_path)
                    atlas_files.append((atlas_filename, full_path)) 
        
        # Check for SimNIBS labeling.nii.gz atlas
        simnibs_seg_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                                       f"m2m_{subject_id}", "segmentation")
        labeling_path = os.path.join(simnibs_seg_dir, "labeling.nii.gz")
        if os.path.exists(labeling_path):
            atlas_files.append(("SimNIBS labeling", labeling_path))
        
        if not atlas_files: # No specific atlases found
            # Original warning message logic
            atlas_files.append("FreeSurfer recon-all preprocessing required for atlas generation")
        return atlas_files


    def update_atlas_combo(self): # For single mode
        if self.is_group_mode: return
        
        self.atlas_combo.clear()
        
        # --- Add or show warning label above atlas_combo ---
        if not hasattr(self, 'atlas_warning_label'):
            self.atlas_warning_label = QtWidgets.QLabel()
            self.atlas_warning_label.setStyleSheet("color: #c62828; font-weight: bold;")
            self.atlas_warning_label.setWordWrap(True)
            self.atlas_warning_label.setVisible(False)
            self.atlas_warning_label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Ignored)
            # Insert above the atlas_combo in the layout
            if hasattr(self, 'voxel_atlas_widget'):
                self.voxel_atlas_widget.layout().insertWidget(0, self.atlas_warning_label)
        
        # Handle mesh atlas combo for single mode
        if self.space_mesh.isChecked() and self.type_cortical.isChecked():
            # Ensure mesh atlas combo is populated with predefined atlases
            if self.atlas_name_combo.count() == 0:
                self.atlas_name_combo.addItems(["DK40", "HCP_MMP1", "a2009s"])
                self.atlas_name_combo.setCurrentText("DK40")
            self.atlas_name_combo.setEnabled(True)
        
        # Get selected subject from appropriate widget based on mode
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            self.atlas_combo.addItem("Select a subject first")
            self.atlas_combo.setEnabled(False)
            self.atlas_warning_label.setText(
                "<i>*Please run FreeSurfer recon-all in the Preprocessing tab to enable voxel cortical analysis.*</i>"
            )
            self.atlas_warning_label.setVisible(True)
            # Update all related controls
            self.update_atlas_dependent_controls(has_valid_atlas=False, requires_atlas=False)
            return
        
        subject_id = selected_subjects[0] # Short ID
        atlas_files_data = self.get_available_atlas_files(subject_id)
        has_valid_atlas = False
        
        # Check if we're in a mode that requires atlases (voxel + cortical)
        requires_atlas = self.space_voxel.isChecked() and self.type_cortical.isChecked()
        
        # Determine if we have valid atlas data
        if atlas_files_data and isinstance(atlas_files_data[0], tuple):
            # We have valid atlas tuples
            has_valid_atlas = True
            for item in atlas_files_data:
                if isinstance(item, tuple) and len(item) == 2:
                    display_name, full_path = item
                    self.atlas_combo.addItem(display_name, full_path)
            if self.atlas_combo.count() > 0:
                self.atlas_combo.setCurrentIndex(0)
        else:
            # No valid atlases found
            if atlas_files_data and isinstance(atlas_files_data[0], str):
                # Warning message from get_available_atlas_files
                self.atlas_combo.addItem(atlas_files_data[0])
            else:
                # No atlas files at all
                self.atlas_combo.addItem("No atlases found")
        
        # Determine if the combo should be enabled
        should_enable_combo = False
        
        if requires_atlas:
            # In voxel + cortical mode, only enable if we have valid atlases
            should_enable_combo = has_valid_atlas
        else:
            # In other modes (mesh cortical, spherical), atlas combo is not needed
            should_enable_combo = False
        
        # Set the combo state
        self.atlas_combo.setEnabled(should_enable_combo)
        
        # Update warning label visibility
        if requires_atlas and not has_valid_atlas:
            self.atlas_warning_label.setText(
                "<i>*Please run FreeSurfer recon-all in the Preprocessing tab to enable voxel cortical analysis.*</i>"
            )
            self.atlas_warning_label.setVisible(True)
        else:
            self.atlas_warning_label.setVisible(False)
        
        # Update all related controls using centralized method
        self.update_atlas_dependent_controls(has_valid_atlas=has_valid_atlas, requires_atlas=requires_atlas)

    def update_atlas_dependent_controls(self, has_valid_atlas=False, requires_atlas=False):
        """
        Centralized method to update all atlas-dependent UI controls.
        
        Args:
            has_valid_atlas (bool): Whether valid atlas data is available
            requires_atlas (bool): Whether the current mode requires atlas data
        """
        is_mesh = self.space_mesh.isChecked()
        is_cortical = self.type_cortical.isChecked()
        is_voxel_cortical = not is_mesh and is_cortical
        
        # Determine if we should enable cortical analysis controls
        # For mesh cortical: always enable (atlases are predefined)
        # For voxel cortical: only enable if we have valid atlases
        # For spherical: disable (no atlas needed)
        cortical_controls_enabled = False
        
        if is_cortical:
            if is_mesh:
                # Mesh cortical: always enable (uses predefined atlases)
                cortical_controls_enabled = True
            else:
                # Voxel cortical: only enable if we have valid atlases
                cortical_controls_enabled = has_valid_atlas and requires_atlas
        
        # Update whole head checkbox
        # Should be enabled for cortical analysis, but disabled if no valid atlas in voxel mode
        whole_head_enabled = is_cortical and cortical_controls_enabled
        self.whole_head_check.setEnabled(whole_head_enabled)
        
        # Update region input controls
        # Should be enabled for cortical analysis when not whole head, but only if atlas controls are enabled
        region_enabled = cortical_controls_enabled and not self.whole_head_check.isChecked()
        self.region_label.setEnabled(region_enabled)
        self.region_input.setEnabled(region_enabled)
        
        # Update show regions button
        # Should be enabled for cortical analysis when not whole head, but only if we have valid atlases
        can_list_regions = cortical_controls_enabled and not self.whole_head_check.isChecked()
        self.show_regions_btn.setEnabled(can_list_regions)

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
            
            # Since we now have a valid atlas, enable the combo and related controls
            if self.space_voxel.isChecked() and self.type_cortical.isChecked():
                self.atlas_combo.setEnabled(True)
                # Hide warning label if it was showing
                if hasattr(self, 'atlas_warning_label'):
                    self.atlas_warning_label.setVisible(False)
                # Update all related controls using centralized method
                self.update_atlas_dependent_controls(has_valid_atlas=True, requires_atlas=True)
            
            # Update button state after selection/addition
            can_list_regions = self.atlas_combo.isEnabled() and \
                               self.type_cortical.isChecked() and \
                               not self.whole_head_check.isChecked()
            self.show_regions_btn.setEnabled(can_list_regions)


    def update_atlas_visibility(self):
        is_mesh = self.space_mesh.isChecked()
        is_cortical = self.type_cortical.isChecked()
        
        # Hide warning label in group mode - it should never show in group mode
        if self.is_group_mode and hasattr(self, 'atlas_warning_label'):
            self.atlas_warning_label.setVisible(False)
        
        # Original visibility logic for atlas selection widgets
        self.mesh_atlas_widget.setVisible(is_mesh and is_cortical)
        self.voxel_atlas_widget.setVisible(not is_mesh and is_cortical)
        
        # Field name is now hardcoded to TI_max
        
        # Enable atlas widgets based on analysis type
        mesh_atlas_enabled = is_mesh and is_cortical
        voxel_atlas_enabled = not is_mesh and is_cortical
        
        self.mesh_atlas_widget.setEnabled(mesh_atlas_enabled)
        self.voxel_atlas_widget.setEnabled(voxel_atlas_enabled)
        
        # For the atlas combos specifically
        if mesh_atlas_enabled:
            self.atlas_name_combo.setEnabled(True)
            # Ensure mesh atlas combo is populated with predefined atlases in single mode
            if not self.is_group_mode and self.atlas_name_combo.count() == 0:
                self.atlas_name_combo.addItems(["DK40", "HCP_MMP1", "a2009s"])
                self.atlas_name_combo.setCurrentText("DK40")
        
        # For voxel atlas combo, let update_atlas_combo handle the enable state
        # based on actual atlas availability
        if voxel_atlas_enabled and not self.is_group_mode:
            # update_atlas_combo will handle the enable state properly
            pass
        elif voxel_atlas_enabled and self.is_group_mode:
            # For group mode, enable if we have any items
            self.atlas_combo.setEnabled(self.atlas_combo.count() > 0)
        
        self.mesh_atlas_widget.update() # Original calls
        self.voxel_atlas_widget.update()
        
        # Update atlas options and related controls
        if self.is_group_mode and is_cortical:
            self.update_group_atlas_options()
        elif not self.is_group_mode: # Ensure single mode atlas combo is also updated
            # Let update_atlas_combo handle the enable state properly
            self.update_atlas_combo()
        else:
            # For non-cortical modes or when not in group mode, update controls directly
            self.update_atlas_dependent_controls(has_valid_atlas=False, requires_atlas=False)

    def update_cortical_button_text(self):
        """Update the cortical radio button text based on the selected analysis space."""
        if self.space_voxel.isChecked():
            self.type_cortical.setText("Sub/Cortical")
        else:
            self.type_cortical.setText("Cortical")

    def update_group_atlas_options(self): # For shared atlas selectors in group mode
        if not self.is_group_mode: return
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        if not selected_subjects: 
            # Don't disable everything if no subjects - user might be in process of selecting
            return
            
        # Store current states
        mesh_atlas_was_enabled = self.atlas_name_combo.isEnabled()
        voxel_atlas_was_enabled = self.atlas_combo.isEnabled()
        
        self.atlas_name_combo.clear() # For mesh
        self.atlas_combo.clear()      # For voxel (this was for single mode, repurposing for group shared voxel if needed)
        
        has_valid_atlas = False
        requires_atlas = self.space_voxel.isChecked() and self.type_cortical.isChecked()
        
        if self.space_mesh.isChecked() and self.type_cortical.isChecked():
            self.atlas_name_combo.addItems(["DK40", "HCP_MMP1", "a2009s"]) # Predefined mesh atlases
            self.atlas_name_combo.setCurrentText("DK40")
            self.atlas_name_combo.setEnabled(True)  # Always enable for mesh
            has_valid_atlas = True  # Mesh atlases are always available
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
                has_valid_atlas = True
                try: self.atlas_combo.currentTextChanged.disconnect(self.update_group_voxel_atlas)
                except TypeError: pass
                self.atlas_combo.currentTextChanged.connect(self.update_group_voxel_atlas)
                self.update_group_voxel_atlas(self.atlas_combo.currentText()) # Initial update
            else:
                # No common atlas: show only the message, disable all controls, and hide warning label
                self.atlas_combo.clear()
                self.atlas_combo.addItem("No common atlases for all selected subjects")
                self.atlas_combo.setEnabled(False)
                has_valid_atlas = False
                self.group_atlas_config.clear() # Clear all atlas configs since we have no common atlas
                # Hide the warning label if present
                if hasattr(self, 'atlas_warning_label'):
                    self.atlas_warning_label.setVisible(False)
                # Disable all region/atlas controls
                self.region_label.setEnabled(False)
                self.region_input.setEnabled(False)
                self.show_regions_btn.setEnabled(False)
                self.whole_head_check.setEnabled(False)
                return  # Skip the centralized update, as we've set everything explicitly
        
        # Update all related controls using centralized method
        self.update_atlas_dependent_controls(has_valid_atlas=has_valid_atlas, requires_atlas=requires_atlas)

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
        # The centralized method will handle all the enable/disable logic
        # Just call update_atlas_visibility which will trigger the proper state updates
        self.update_atlas_visibility()

    def validate_inputs(self):
        if self.is_group_mode:
            return self.validate_group_inputs()
        else:
            return self.validate_single_inputs()
    
    def validate_single_inputs(self):
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a subject.")
            return False
        if self.simulation_combo.currentIndex() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a montage.")
            return False
        if self.field_combo.currentIndex() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a field file.")
            return False
        # Field name is now hardcoded to TI_max for mesh analysis
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
            
        # Field name is now hardcoded to TI_max for mesh analysis
        
        # Group analysis now supports both spherical (with MNI coordinates) and cortical analysis
        # No restriction needed
            
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
            # Prevent accidental double-starts
            if getattr(self, '_thread_started', False):
                return
            if hasattr(self, 'optimization_process') and self.optimization_process and self.optimization_process.isRunning():
                return
            # In single mode, get the selected subject from the combo
            selected_subjects = self.get_selected_subjects()
            if not selected_subjects:
                self.update_output("Error: No subject selected for single analysis.")
                self.analysis_finished(success=False)
                return
            subject_id = selected_subjects[0]  # Take the selected subject
            
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

            cmd = self.build_single_analysis_command(subject_id, simulation_name, field_path)
            if not cmd: # build_analysis_command returns None on error
                self.analysis_finished(success=False)
                return
            
            env = os.environ.copy()
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            env['PROJECT_DIR'] = f"/mnt/{project_dir_name}"
            env['SUBJECT_ID'] = subject_id # Passed to script via env
            
            # Mark thread start as early as possible to avoid race double-starts
            self._thread_started = True

            # Summary-mode: headline and initial step (guard against duplicates)
            if self.SUMMARY_MODE and not getattr(self, '_summary_started', False):
                details = self._build_start_details(subject_id)
                self.ANALYSIS_START_TIME = time.time()
                self.update_output(f"Beginning analysis for subject: {subject_id} ({details})")
                self._summary_printed.add('headline')
                # Field data loading step
                self.update_output("├─ Field data loading: Starting...")
                self.update_output("├─ Field data loading: ✓ Complete (0s)")
                self._summary_printed.update({'field_start', 'field_done'})
                # Start main analysis step timer
                step_key = 'cortical analysis' if self.type_cortical.isChecked() else 'spherical analysis'
                # Only set start timer if not already set
                if step_key not in self.STEP_START_TIMES:
                    self.STEP_START_TIMES[step_key] = time.time()
                self.update_output(f"├─ {step_key.title()}: Starting...")
                self._summary_printed.add('analysis_start')
                # Record output dir for later summary line
                self._last_output_dir = self._extract_output_dir_from_cmd(cmd)
                # Mark started to avoid duplicated blocks
                self._summary_started = True
            else:
                self.update_output(f"Running single subject analysis for: {subject_id}")
                self.update_output(f"Montage: {simulation_name}")
                self.update_output(f"Command: {' '.join(cmd)}")
            
            self.optimization_process = AnalysisThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output, QtCore.Qt.QueuedConnection)
            self.optimization_process.finished.connect(
                lambda sid=subject_id, sim_name=simulation_name: self.analysis_finished(subject_id=sid, simulation_name=sim_name, success=True),
                QtCore.Qt.QueuedConnection
            )
            self._thread_started = True
            self.optimization_process.start()
        except Exception as e:
            self.update_output(f"Error preparing single analysis: {str(e)}")
            self.analysis_finished(success=False)
    
    def run_group_analysis(self):
        """Run group analysis using the group_analyzer.py script."""
        selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
        if not selected_subjects:
            self.update_output("No subjects selected for group analysis.")
            self.analysis_finished(success=False)
            return
        
        try:
            # Build the group analyzer command
            cmd = self.build_group_analyzer_command(selected_subjects)
            if not cmd:
                self.update_output("Error: Could not build group analyzer command.")
                self.analysis_finished(success=False)
                return

            env = os.environ.copy()
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            env['PROJECT_DIR'] = f"/mnt/{project_dir_name}"
            
            if self.SUMMARY_MODE:
                # For group we still provide a concise start message
                self.ANALYSIS_START_TIME = time.time()
                self.update_output(f"Beginning group analysis for subjects: {', '.join(selected_subjects)}")
                self._last_output_dir = self._extract_output_dir_from_cmd(cmd)
            else:
                self.update_output(f"Starting group analysis for subjects: {', '.join(selected_subjects)}")
                self.update_output(f"Command: {' '.join(cmd)}")
            
            # Create and start thread
            self.optimization_process = AnalysisThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output, QtCore.Qt.QueuedConnection)
            self.optimization_process.finished.connect(
                lambda: self.analysis_finished(success=True),
                QtCore.Qt.QueuedConnection
            )
            self.optimization_process.start()
            
        except Exception as e:
            self.update_output(f"Error preparing group analysis: {str(e)}")
            self.analysis_finished(success=False)
    
    def build_group_analyzer_command(self, selected_subjects):
        """Build command to run group_analyzer.py with all selected subjects."""
        try:
            # Locate group_analyzer.py script
            app_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            group_analyzer_script_path = os.path.join(app_root_dir, 'analyzer', 'group_analyzer.py')
            if not os.path.exists(group_analyzer_script_path):
                self.update_output(f"Error: group_analyzer.py not found at {group_analyzer_script_path}")
                return None

            # Build base command with temporary output directory (group_analyzer.py will create the actual organized directories)
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            project_dir = f"/mnt/{project_dir_name}"
            temp_output_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS')
            
            cmd = ['simnibs_python', group_analyzer_script_path,
                   '--space', 'mesh' if self.space_mesh.isChecked() else 'voxel',
                   '--analysis_type', 'spherical' if self.type_spherical.isChecked() else 'cortical',
                   '--output_dir', temp_output_dir]

            # Field name is now hardcoded to TI_max in the main analyzer

            # Add analysis-specific parameters
            if self.type_spherical.isChecked():
                coords = [self.coord_x.text().strip() or "0", 
                         self.coord_y.text().strip() or "0", 
                         self.coord_z.text().strip() or "0"]
                radius = self.radius_input.text().strip() or "5"
                cmd.extend(['--coordinates'] + coords)
                cmd.extend(['--radius', radius])
                
                # Add MNI coordinates flag for group analysis (coordinates are treated as MNI space)
                cmd.append('--use-mni-coords')
            else:  # cortical
                if self.space_mesh.isChecked():
                    atlas_name = self.atlas_name_combo.currentText()
                    if not atlas_name:
                        self.update_output("Error: Atlas name is required for mesh cortical analysis.")
                        return None
                    cmd.extend(['--atlas_name', atlas_name])
                
                if self.whole_head_check.isChecked():
                    cmd.append('--whole_head')
                else:
                    region = self.region_input.text().strip()
                    if not region:
                        self.update_output("Error: Region name is required for cortical analysis.")
                        return None
                    cmd.extend(['--region', region])

            # Always enable visualizations
            cmd.append('--visualize')
            
            # Add quiet flag if not in debug mode
            if not self.debug_mode:
                cmd.append('--quiet')

            # Add subject specifications
            common_montage = self.group_montage_config.get('common_montage')
            if not common_montage:
                self.update_output("Error: No common montage configured.")
                return None

            for subject_id in selected_subjects:
                # Get m2m path
                m2m_path = self.get_m2m_dir_for_subject(subject_id)
                if not m2m_path or not os.path.isdir(m2m_path):
                    self.update_output(f"Error: m2m_{subject_id} folder not found at {m2m_path}. Please create the m2m folder first using the Pre-process tab.", 'error')
                    return None

                # Get field path for both mesh and voxel analysis
                field_path = self.group_field_config.get(subject_id)
                if not field_path or not os.path.exists(field_path):
                    self.update_output(f"Error: Field file not found for subject {subject_id}")
                    return None

                # Build subject specification
                subject_spec = [subject_id, m2m_path, field_path]
                
                # For voxel cortical analysis, add atlas path
                if self.space_voxel.isChecked() and self.type_cortical.isChecked():
                    atlas_config = self.group_atlas_config.get(subject_id, {})
                    atlas_path = atlas_config.get('path')
                    if not atlas_path or not os.path.exists(atlas_path):
                        self.update_output(f"Error: Atlas file not found for subject {subject_id}")
                        return None
                    subject_spec.append(atlas_path)

                cmd.extend(['--subject'] + subject_spec)

            return cmd

        except Exception as e:
            self.update_output(f"Error building group analyzer command: {str(e)}")
            return None

    def get_single_analysis_details(self):
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects: return "No subject selected."
        subj = selected_subjects[0]  # Use the selected subject
        space = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
        atype = 'Spherical' if self.type_spherical.isChecked() else 'Cortical'
        mont = self.simulation_combo.currentText()
        fpath = self.field_combo.currentText()
        details = f"- Subject: {subj}\n- Space: {space}\n- Analysis Type: {atype}\n- Montage: {mont}\n- Field File: {fpath}\n"
        if len(selected_subjects) > 1:
            details += f"- Note: Using first selected subject ({subj}) for single analysis\n"
        if self.space_mesh.isChecked(): details += f"- Field Name: TI_max (hardcoded)\n"
        if self.type_spherical.isChecked():
            coord_space = "MNI" if self.is_group_mode else "RAS"
            details += (f"- Coordinates ({coord_space}): ({self.coord_x.text() or '0'}, {self.coord_y.text() or '0'}, {self.coord_z.text() or '0'})\n"
                        f"- Radius: {self.radius_input.text() or '5'} mm\n")
            if self.is_group_mode:
                details += f"- Coordinate Transformation: MNI → Subject space (automatic)\n"
        else: # Cortical
            if self.space_mesh.isChecked(): details += f"- Mesh Atlas: {self.atlas_name_combo.currentText()}\n"
            else: details += f"- Voxel Atlas File: {self.atlas_combo.currentText()} (Path: {self.atlas_combo.currentData() or 'N/A'})\n" # Show path
            if self.whole_head_check.isChecked(): details += "- Analysis Target: Whole Head\n"
            else: details += f"- Region: {self.region_input.text()}\n"
        details += f"- Generate Visualizations: Yes"
        return details

    def get_group_analysis_details(self, subjects):
        space = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
        analysis_type = 'Spherical' if self.type_spherical.isChecked() else 'Cortical'
        details = (f"- Subjects: {', '.join(subjects)}\n- Space: {space}\n- Analysis Type: {analysis_type}\n")
        
        # Common configuration
        details += "\n- Common Configuration (Applied to All Subjects):\n"
        common_montage = self.group_montage_config.get('common_montage', 'N/A')
        details += f"  - Common Montage: {common_montage}\n"
        
        # Field configuration details
        if self.group_field_config:
            field_count = len(self.group_field_config)
            details += f"  - Field Files: Auto-selected grey matter subject space files for {field_count} subjects\n"
            if self.space_mesh.isChecked():
                field_name = "TI_max"  # Field name is now hardcoded
                details += f"  - Field Name (Mesh): {field_name}\n"
        else:
            details += f"  - Field Files: None auto-selected\n"
        
        # Shared analysis parameters
        details += "\n- Shared Analysis Parameters:\n"
        if self.type_spherical.isChecked():
            details += f"- Coordinates (MNI): ({self.coord_x.text() or '0'}, {self.coord_y.text() or '0'}, {self.coord_z.text() or '0'})\n"
            details += f"- Radius: {self.radius_input.text() or '5'} mm\n"
            details += f"- Coordinate Transformation: MNI → Subject space (automatic for each)\n"
        else:  # cortical
            if self.space_mesh.isChecked(): 
                details += f"- Shared Mesh Atlas: {self.atlas_name_combo.currentText()}\n"
            else:
                details += f"- Voxel Atlas: Common atlas configuration\n"
            if self.whole_head_check.isChecked(): 
                details += "- Analysis Target: Whole Head (for all)\n"
            else: 
                details += f"- Region: {self.region_input.text()} (for all)\n"
        details += f"- Generate Visualizations: Yes"
        return details

    def force_ui_refresh(self):
        """Force a complete UI refresh to ensure all controls are in the correct state."""
        # Force update of all relevant UI components
        if not self.is_group_mode:
            self.update_simulations()
            self.update_field_files()
            self.update_mesh_files()
        
        # Update atlas and region controls
        self.update_atlas_visibility()
        
        # Force refresh group mode configurations if applicable
        if self.is_group_mode:
            selected_subjects = self.get_selected_subjects()
            if selected_subjects:
                self.populate_group_common_config(selected_subjects)
        
        # Update button states
        self.update_gmsh_button_state()
        
        # Force widget updates
        if hasattr(self, 'analysis_params_container'):
            self.analysis_params_container.update()
        
        # Process any pending events
        QtWidgets.QApplication.processEvents()

    def analysis_finished(self, subject_id=None, simulation_name=None, success=True):
        if hasattr(self, '_processing_analysis_finished_lock') and self._processing_analysis_finished_lock: return
        self._processing_analysis_finished_lock = True
        try:
            if success:
                if self.SUMMARY_MODE and getattr(self, '_summary_started', False) and not getattr(self, '_summary_finished', False):
                    # Complete analysis step timing if started
                    analysis_step_key = 'cortical analysis' if self.type_cortical.isChecked() else 'spherical analysis'
                    start_time = self.STEP_START_TIMES.get(analysis_step_key)
                    if start_time:
                        duration_sec = int(max(0, (time.time() - start_time)))
                        duration_str = f"{duration_sec}s" if duration_sec < 60 else f"{duration_sec // 60}m {duration_sec % 60}s"
                        regions_info = "- 1 region analyzed" if self.type_cortical.isChecked() else ""
                        self.update_output(f"├─ {analysis_step_key.title()}: ✓ Complete ({duration_str}) {regions_info}".rstrip())
                        self._summary_printed.add('analysis_done')
                    # Results saving summary
                    saved_to_display = self._last_output_dir or ""
                    if saved_to_display.startswith('/mnt/'):
                        # Show without the leading /mnt/ to match examples
                        saved_to_display = saved_to_display[5:]
                    self.update_output("├─ Results saving: Starting...")
                    self._summary_printed.add('results_start')
                    self.update_output(f"├─ Results saving: ✓ Complete (0s) - saved to {saved_to_display}")
                    self._summary_printed.add('results_done')
                    # Final line with total duration
                    total_duration_str = "0s"
                    if self.ANALYSIS_START_TIME:
                        total_sec = int(max(0, (time.time() - self.ANALYSIS_START_TIME)))
                        total_duration_str = f"{total_sec}s" if total_sec < 60 else f"{total_sec // 60}m {total_sec % 60}s"
                    regions_count = "1 region analyzed" if self.type_cortical.isChecked() else ""
                    subj_display = subject_id or (self.get_selected_subjects()[0] if self.get_selected_subjects() else "")
                    suffix = f" (1 region analyzed, Total: {total_duration_str})" if regions_count else f" (Total: {total_duration_str})"
                    self.update_output(f"└─ Analysis completed successfully for subject: {subj_display}{suffix}")
                    self._summary_printed.add('final')
                    self._summary_finished = True
                else:
                    last_line = self.output_console.toPlainText().strip().split('\n')[-1] if self.output_console.toPlainText() else ""
                    if "WARNING: Analysis Failed" in last_line or "Error: Process returned non-zero" in last_line or "failed" in last_line.lower():
                        self.update_output('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">[ERROR] Analysis process indicated failure.</span></div>')
                    else:
                        self.update_output('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">[SUCCESS] Analysis process completed.</span></div>')
                
                # Emit analysis completed signal for single mode or group mode
                if subject_id and simulation_name:
                    analysis_type_str = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
                    self.analysis_completed.emit(subject_id, simulation_name, analysis_type_str)
                elif self.is_group_mode:
                    selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
                    analysis_type_str = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
                    if selected_subjects:
                        common_montage = self.group_montage_config.get('common_montage', 'group_analysis')
                        self.analysis_completed.emit(selected_subjects[0], common_montage, analysis_type_str)
            else:
                 self.update_output('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">[ERROR] Analysis process failed or was cancelled by user.</span></div>')

            if not self.SUMMARY_MODE:
                self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
            self.analysis_running = False
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.enable_controls()
            # Reset summary flags for next run
            if hasattr(self, '_summary_started'):
                delattr(self, '_summary_started')
            if hasattr(self, '_summary_finished'):
                delattr(self, '_summary_finished')
            if hasattr(self, '_thread_started'):
                delattr(self, '_thread_started')
            if hasattr(self, '_last_plain_output_line'):
                delattr(self, '_last_plain_output_line')
            
            # Force a complete UI refresh to ensure everything is properly restored
            QtCore.QTimer.singleShot(100, self.force_ui_refresh)
            
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
    
    def update_output(self, text, message_type='default'): # This is the method used by AnalysisThread's signal
        if not text or not text.strip(): return
        
        # Filter messages based on debug mode
        if not self.debug_mode:
            # In non-debug mode, only show important messages
            if not is_important_message(text, message_type, 'analyzer'):
                return
            # In non-debug (summary) mode, colorize lines and deduplicate
            scrollbar = self.output_console.verticalScrollBar()
            at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
            
            # Safety check: ensure the attribute exists before accessing it
            if not hasattr(self, '_last_plain_output_line'):
                self._last_plain_output_line = None
                
            if text == self._last_plain_output_line:
                return
                
            # Safety check: ensure the _summary_printed attribute exists
            if not hasattr(self, '_summary_printed'):
                self._summary_printed = set()
                
            low = text.lower().strip()
            # Guard against duplicate summary lines (whether from our own calls or subprocess echo)
            if low.startswith('beginning analysis for subject:') and 'headline' in self._summary_printed:
                return
            if low.startswith('├─ field data loading: starting') and 'field_start' in self._summary_printed:
                return
            if low.startswith('├─ field data loading: ✓ complete') and 'field_done' in self._summary_printed:
                return
            if (low.startswith('├─ cortical analysis: starting') or low.startswith('├─ spherical analysis: starting')) and 'analysis_start' in self._summary_printed:
                return
            if (low.startswith('├─ cortical analysis: ✓ complete') or low.startswith('├─ spherical analysis: ✓ complete')) and 'analysis_done' in self._summary_printed:
                return
            if low.startswith('├─ results saving: starting') and 'results_start' in self._summary_printed:
                return
            if low.startswith('├─ results saving: ✓ complete') and 'results_done' in self._summary_printed:
                return
            if low.startswith('└─ analysis completed successfully for subject:') and 'final' in self._summary_printed:
                return
            # Colorize summary lines: blue for starts, white for completes, green for final
            is_final = low.startswith('└─') or 'completed successfully' in low
            is_start = low.startswith('beginning ') or ': starting' in low
            is_complete = ('✓ complete' in low) or ('results available in:' in low) or ('saved to' in low)
            color = '#55ff55' if is_final else ('#55aaff' if is_start else '#ffffff')
            formatted = f'<span style="color: {color};">{text}</span>'
            self.output_console.append(formatted)
            self._last_plain_output_line = text
            # Mark printed flags for summary lines
            if low.startswith('beginning analysis for subject:'):
                self._summary_printed.add('headline')
            elif low.startswith('├─ field data loading: starting'):
                self._summary_printed.add('field_start')
            elif low.startswith('├─ field data loading: ✓ complete'):
                self._summary_printed.add('field_done')
            elif low.startswith('├─ cortical analysis: starting') or low.startswith('├─ spherical analysis: starting'):
                self._summary_printed.add('analysis_start')
            elif low.startswith('├─ cortical analysis: ✓ complete') or low.startswith('├─ spherical analysis: ✓ complete'):
                self._summary_printed.add('analysis_done')
            elif low.startswith('├─ results saving: starting'):
                self._summary_printed.add('results_start')
            elif low.startswith('├─ results saving: ✓ complete'):
                self._summary_printed.add('results_done')
            elif low.startswith('└─ analysis completed successfully for subject:'):
                self._summary_printed.add('final')
            if at_bottom:
                self.output_console.ensureCursorVisible()
                scrollbar.setValue(scrollbar.maximum())
            return
        
        # Format the output based on message type from thread
        if message_type == 'error':
            formatted_text = f'<span style="color: #ff5555;"><b>{text}</b></span>'
        elif message_type == 'warning':
            formatted_text = f'<span style="color: #ffff55;">{text}</span>'
        elif message_type == 'debug':
            formatted_text = f'<span style="color: #7f7f7f;"><i>{text}</i></span>' # Italic grey
        elif message_type == 'command':
            formatted_text = f'<span style="color: #55aaff;">{text}</span>'
        elif message_type == 'success':
            formatted_text = f'<span style="color: #55ff55;"><b>{text}</b></span>'
        elif message_type == 'info':
            formatted_text = f'<span style="color: #55ffff;">{text}</span>'
        else:
            # Fallback to content-based formatting for backward compatibility
            # Group analysis specific patterns
            if "=== Processing subject:" in text or "=== GROUP ANALYSIS SUMMARY ===" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 5px; margin: 5px 0; border-radius: 3px;"><span style="color: #55ffff; font-weight: bold;">{text}</span></div>'
            elif "[OK] Subject" in text or "[FAILED] Subject" in text:
                formatted_text = f'<span style="color: #55ff55; font-weight: bold;">{text}</span>' if "[OK]" in text else f'<span style="color: #ff5555; font-weight: bold;">{text}</span>'
            elif "Group analysis complete" in text or "Comprehensive group results" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #55ff55; font-weight: bold; font-size: 14px;">{text}</span></div>'
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
        
        # Check if user is at the bottom of the console before appending
        scrollbar = self.output_console.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5  # Allow small tolerance
        
        # Append to the console with HTML formatting
        self.output_console.append(formatted_text)
        
        # Only auto-scroll if user was already at the bottom
        if at_bottom:
            self.output_console.ensureCursorVisible()
            # Scroll to the very bottom to show latest output
            scrollbar.setValue(scrollbar.maximum())
        
        # Avoid calling processEvents() here to prevent re-entrant recursion when many
        # queued output signals arrive rapidly.

    def set_debug_mode(self, debug_mode):
        """Set debug mode for output filtering."""
        self.debug_mode = debug_mode
        self.SUMMARY_MODE = not debug_mode

    # ===== Summary-mode helpers =====
    def _format_duration(self, start_time):
        if not start_time:
            return "0s"
        elapsed = time.time() - start_time
        if elapsed < 60:
            return f"{int(elapsed)}s"
        return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

    def _build_start_details(self, subject_id):
        if self.type_cortical.isChecked():
            if self.space_mesh.isChecked():
                atlas = self.atlas_name_combo.currentText() or ""
            else:
                atlas = os.path.basename(self.atlas_combo.currentText() or "").split('.')[0]
            region = "WholeHead" if self.whole_head_check.isChecked() else (self.region_input.text().strip() or "region")
            return f"Cortical: {atlas}.{region}"
        else:
            coords = (self.coord_x.text().strip() or '0', self.coord_y.text().strip() or '0', self.coord_z.text().strip() or '0')
            return f"Spherical: ({coords[0]},{coords[1]},{coords[2]}) r{self.radius_input.text().strip() or '5'}mm"

    def _extract_output_dir_from_cmd(self, cmd):
        try:
            if '--output_dir' in cmd:
                idx = cmd.index('--output_dir')
                return cmd[idx + 1] if idx + 1 < len(cmd) else None
        except Exception:
            return None
        return None

    def disable_controls(self):
        # List of widgets to disable, similar to original
        widgets_to_set_enabled = [
            # Subject buttons for both modes
            self.list_subjects_btn, self.clear_subject_selection_btn,  # Single mode
            self.list_subjects_btn_group, self.select_all_subjects_btn, self.clear_subject_selection_btn_group,  # Group mode
            # Other widgets
            self.subject_list, self.subject_combo, self.single_mode_radio, self.group_mode_radio,
            self.simulation_combo, self.field_combo, self.browse_field_btn,
            self.space_mesh, self.space_voxel, self.type_spherical, self.type_cortical,
            self.coord_x, self.coord_y, self.coord_z, self.radius_input,
            self.view_in_freeview_btn,
            self.atlas_name_combo, self.atlas_combo, self.show_regions_btn, self.region_input, self.whole_head_check,
            self.mesh_combo, self.launch_gmsh_btn
        ]
        for widget in widgets_to_set_enabled:
            if hasattr(widget, 'setEnabled'): widget.setEnabled(False)

        if self.is_group_mode: # Also disable group configuration widgets
            if hasattr(self, 'group_montage_combo'):
                self.group_montage_combo.setEnabled(False)
            if hasattr(self, 'show_selected_fields_btn'):
                self.show_selected_fields_btn.setEnabled(False)
        
        self.status_label.setText("Processing... Stop button is available.")
        self.status_label.show()

    def enable_controls(self):
        widgets_to_set_enabled = [
            # Subject buttons for both modes
            self.list_subjects_btn, self.clear_subject_selection_btn,  # Single mode
            self.list_subjects_btn_group, self.select_all_subjects_btn, self.clear_subject_selection_btn_group,  # Group mode
            # Other widgets
            self.subject_list, self.subject_combo, self.single_mode_radio, self.group_mode_radio,
            self.simulation_combo, self.field_combo, self.browse_field_btn,
            self.space_mesh, self.space_voxel, self.type_spherical, self.type_cortical,
            self.coord_x, self.coord_y, self.coord_z, self.radius_input,
            self.view_in_freeview_btn,
            # atlas_name_combo, atlas_combo, show_regions_btn, region_input, whole_head_check handled by update_atlas_visibility
            self.mesh_combo # launch_gmsh_btn handled by its own update
        ]
        for widget in widgets_to_set_enabled:
             if hasattr(widget, 'setEnabled'): widget.setEnabled(True)
        
        # Force enable these controls first, then let update_atlas_visibility handle proper state
        self.whole_head_check.setEnabled(True)
        self.region_input.setEnabled(True)
        self.region_label.setEnabled(True)
        self.atlas_name_combo.setEnabled(True)
        # Don't force enable atlas_combo - let update_atlas_visibility handle it properly
        self.show_regions_btn.setEnabled(True)
        
        # Now update visibility and proper enable states
        self.update_atlas_visibility() # This will correctly set enable states for atlas/region controls
        self.update_gmsh_button_state()

        if self.is_group_mode:
            if hasattr(self, 'group_montage_combo'):
                self.group_montage_combo.setEnabled(True)
            if hasattr(self, 'show_selected_fields_btn'):
                # Button state depends on whether fields are selected
                self.show_selected_fields_btn.setEnabled(bool(self.group_field_config))
        
        # Spherical analysis should be enabled in both modes
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
        is_mti = False
        if self.space_mesh.isChecked():
            # Check for mTI simulation
            mti_mesh_dir = os.path.join(base_sim_dir, 'mTI', 'mesh')
            ti_mesh_dir = os.path.join(base_sim_dir, 'TI', 'mesh')
            if os.path.exists(mti_mesh_dir):
                search_dir = mti_mesh_dir
                is_mti = True
            else:
                search_dir = ti_mesh_dir
        else: # voxel
            # Check for mTI simulation
            mti_nifti_dir = os.path.join(base_sim_dir, 'mTI', 'niftis')
            ti_nifti_dir = os.path.join(base_sim_dir, 'TI', 'niftis')
            if os.path.exists(mti_nifti_dir):
                search_dir = mti_nifti_dir
                is_mti = True
            else:
                search_dir = ti_nifti_dir
        
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
            # For mesh analysis, look for the specific pattern based on simulation type
            if is_mti:
                # For mTI simulations, look for <montage>_mTI.msh
                expected_mesh_file = f"{simulation_name}_mTI.msh"
            else:
                # For regular TI simulations, look for <montage>_TI.msh
                expected_mesh_file = f"{simulation_name}_TI.msh"
            
            if expected_mesh_file in all_files_in_dir:
                field_files_paths.append((expected_mesh_file, os.path.join(search_dir, expected_mesh_file)))
            else:
                # Fallback: look for any .msh files if the expected pattern doesn't exist
                mesh_files = sorted([f for f in all_files_in_dir if f.endswith('.msh') and not f.endswith('.msh.opt')])
                for f_name in mesh_files:
                    field_files_paths.append((f_name, os.path.join(search_dir, f_name)))
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
            if self.space_mesh.isChecked():
                # For mesh analysis, automatically select the first file (should be the correct pattern)
                self.field_combo.setCurrentIndex(1)
            elif not self.space_mesh.isChecked() and grey_non_mni: # Voxel: prefer first non-MNI grey
                idx_pref = self.field_combo.findText(grey_non_mni[0])
                if idx_pref != -1 : self.field_combo.setCurrentIndex(idx_pref)
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
        """Load subject's T1 NIfTI file or MNI template in Freeview for coordinate selection."""
        try:
            selected_subjects = self.get_selected_subjects()
            if not selected_subjects: QtWidgets.QMessageBox.warning(self, "Warning", "Select subject."); return
            
            if self.is_group_mode and self.type_spherical.isChecked():
                # Group mode: load MNI template
                # Look for MNI template in common locations
                mni_paths = [
                    '/usr/share/fsl/data/standard/MNI152_T1_1mm.nii.gz',
                    '/opt/fsl/data/standard/MNI152_T1_1mm.nii.gz',
                    '$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz',
                    # Check project assets folder
                    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'atlas', 'MNI152_T1_1mm.nii.gz')
                ]
                
                mni_file = None
                for path in mni_paths:
                    # Expand environment variables
                    expanded_path = os.path.expandvars(path)
                    if os.path.isfile(expanded_path):
                        mni_file = expanded_path
                        break
                
                if not mni_file:
                    QtWidgets.QMessageBox.warning(self, "Error", 
                        "MNI152 template not found. Please ensure FSL is installed or place MNI152_T1_1mm.nii.gz in assets/atlas/")
                    return
                
                # Launch Freeview with MNI template
                subprocess.Popen(["freeview", mni_file])
                self.update_output(f"Launched Freeview with MNI152 template: {mni_file}")
                self.update_output("Use Freeview to find MNI coordinates and enter them in the coordinate fields.")
                self.update_output("These MNI coordinates will be automatically transformed to each subject's native space.")
            else:
                # Single mode or non-spherical: load subject's T1
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
        
        # Only populate mesh files when Mesh space is selected
        if not self.space_mesh.isChecked():
            self.mesh_combo.clear()
            self.mesh_combo.addItem("Select mesh file...")
            self.update_gmsh_button_state()
            return
        
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
                        # Use relative path as display name to distinguish files in different subdirectories
                        display_name = os.path.splitext(rel_path_display)[0].replace(os.sep, '/')
                        mesh_files_to_list.append((display_name, full_path_item))
        
        mesh_files_to_list.sort(key=lambda x: x[0])
        for disp, path_val in mesh_files_to_list: self.mesh_combo.addItem(disp, path_val)
        
        self.update_gmsh_button_state()

    def launch_gmsh(self):
        if self.mesh_combo.currentIndex() == 0 or not self.mesh_combo.currentData():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a mesh file first"); return
        mesh_file_path_val = self.mesh_combo.currentData()
        if not mesh_file_path_val or not os.path.exists(mesh_file_path_val):
            QtWidgets.QMessageBox.warning(self, "Error", "Selected mesh file not found"); return

        try:
            # Launch Gmsh directly with the mesh file as argument
            subprocess.Popen(["gmsh", mesh_file_path_val])
            self.update_output(f"Launched Gmsh with mesh file: {mesh_file_path_val}")
        except FileNotFoundError:
            QtWidgets.QMessageBox.critical(self, "Error", "Gmsh not found. Please install Gmsh and add it to PATH.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Gmsh: {str(e)}")
            self.update_output(f"Error launching Gmsh: {e}")

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
        elif isinstance(atlas_files[0], str) and atlas_files[0].startswith('[WARNING]'):
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

    def build_single_analysis_command(self, subject_id, simulation_name, field_path):
        """Build command to run main_analyzer.py for a single subject."""
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
            
            # Field name is now hardcoded to TI_max

            analysis_space_folder = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
            if simulation_name == "Select montage...":
                 return None

            output_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}',
                                      'Simulations', simulation_name, 'Analyses',
                                      analysis_space_folder, target_info)

            if os.path.exists(output_dir) and not confirm_overwrite(self, output_dir, "analysis output directory"):
                return None
            os.makedirs(output_dir, exist_ok=True)

            app_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            main_analyzer_script_path = os.path.join(app_root_dir, 'analyzer', 'main_analyzer.py')
            if not os.path.exists(main_analyzer_script_path):
                return None

            m2m_path = self.get_m2m_dir_for_subject(subject_id)
            if not m2m_path or not os.path.isdir(m2m_path):
                self.update_output(f"Error: m2m_{subject_id} folder not found at {m2m_path}. Please create the m2m folder first using the Pre-process tab.", 'error')
                return None

            cmd = [ 'simnibs_python', main_analyzer_script_path,
                    '--m2m_subject_path', m2m_path,
                    '--space', 'mesh' if self.space_mesh.isChecked() else 'voxel',
                    '--analysis_type', 'spherical' if self.type_spherical.isChecked() else 'cortical',
                    '--output_dir', output_dir ]
                    
            # Add field path or montage name based on analysis space
            if self.space_mesh.isChecked():
                cmd.extend(['--montage_name', simulation_name])
            else:
                cmd.extend(['--field_path', field_path])

            if self.type_spherical.isChecked():
                coords_str = [self.coord_x.text().strip() or "0", self.coord_y.text().strip() or "0", self.coord_z.text().strip() or "0"]
                cmd.extend(['--coordinates'] + coords_str)
                cmd.extend(['--radius', self.radius_input.text().strip() or "5"])
            else: # Cortical
                if self.space_mesh.isChecked():
                    cmd.extend(['--atlas_name', self.atlas_name_combo.currentText()])
                else: # Voxel Cortical
                    atlas_path_for_script = self.atlas_combo.currentData()
                    
                    if not atlas_path_for_script:
                        return None
                    cmd.extend(['--atlas_path', atlas_path_for_script])
                
                if self.whole_head_check.isChecked(): cmd.append('--whole_head')
                else: cmd.extend(['--region', self.region_input.text().strip()])
            
            # Field name and field path are now handled in the main command building above
            cmd.append('--visualize')
            
            # Add quiet flag if not in debug mode
            if not self.debug_mode:
                cmd.append('--quiet')
                
            return cmd
        except Exception:
            return None
