#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Analyzer Tab
This module provides a GUI interface for the analyzer functionality.
"""

import traceback 
import time
import os
import subprocess

from PyQt5 import QtWidgets, QtCore, QtGui

from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite, is_verbose_message, is_important_message
from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons

# Import path manager from core
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core import get_path_manager, get_simnibs_dir, get_freesurfer_mri_dir, get_simulation_dir, get_m2m_dir

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
    
    @property
    def is_group_mode(self):
        """Determine if we're in group mode based on number of selected pairs."""
        if hasattr(self, 'pairs_table') and self.pairs_table:
            return self.pairs_table.rowCount() > 1
        return False

    def on_pairs_changed(self):
        """Handle changes to subject-simulation pairs - update UI accordingly."""
        try:
            # Update coordinate space labels based on new mode
            if hasattr(self, '_update_coordinate_space_labels'):
                self._update_coordinate_space_labels()
            # Update atlas visibility and options
            if hasattr(self, 'update_atlas_combo'):
                self.update_atlas_combo()
            if self.is_group_mode and hasattr(self, 'type_cortical') and self.type_cortical.isChecked():
                if hasattr(self, 'update_group_atlas_options'):
                    self.update_group_atlas_options()
            if hasattr(self, 'update_atlas_visibility'):
                self.update_atlas_visibility()
            # Update gmsh subjects when pairs change
            if hasattr(self, 'update_gmsh_subjects'):
                self.update_gmsh_subjects()
        except Exception as e:
            # Silently ignore errors during UI setup
            pass

    def __init__(self, parent=None):
        super(AnalyzerTab, self).__init__(parent)
        self.parent = parent
        self.analysis_running = False
        self.optimization_process = None

        self.group_atlas_config = {}

        # Initialize PathManager
        self.pm = get_path_manager()

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
        left_container.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(5, 0, 5, 0)  # Match margins with right container
        left_layout.setSpacing(2)
        
        # Subject-simulation pairs selection (always shown)
        self.pairs_widget = self.create_pairs_widget()
        left_layout.addWidget(self.pairs_widget)
        
        # Add left container (subjects) to the layout first
        # Use stretch factor 1 for equal sizing
        main_horizontal_layout.addWidget(left_container, 1)
        
        # Create right container (for analysis configuration)
        self.right_layout_container = QtWidgets.QWidget()
        self.right_layout_container.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        right_layout_actual = self.create_analysis_parameters_widget(self.right_layout_container)
        # Use stretch factor 1 for equal sizing with left container
        main_horizontal_layout.addWidget(self.right_layout_container, 1)
        
        # Set stretch factors explicitly to ensure equal sizing
        main_horizontal_layout.setStretchFactor(left_container, 1)
        main_horizontal_layout.setStretchFactor(self.right_layout_container, 1)
        
        # Store reference to scroll content for resize calculations
        self.scroll_content = scroll_content
        
        scroll_layout.addLayout(main_horizontal_layout)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Initial call to set input widths after UI is created
        QtCore.QTimer.singleShot(100, self._update_input_widths)
        
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
        
        # After all widgets are created, set field name visibility and connect toggles
        # This needs to be robust if widgets aren't found (e.g., during initial setup)
        if hasattr(self, 'field_name_label') and hasattr(self, 'field_name_input') and \
           hasattr(self, 'space_mesh') and hasattr(self, 'space_voxel'):
            self.field_name_label.setVisible(self.space_mesh.isChecked())
            self.field_name_input.setVisible(self.space_mesh.isChecked())
            self.space_mesh.toggled.connect(lambda checked: self.field_name_label.setVisible(checked) if hasattr(self, 'field_name_label') else None)
            self.space_mesh.toggled.connect(lambda checked: self.field_name_input.setVisible(checked) if hasattr(self, 'field_name_input') else None)
            self.space_voxel.toggled.connect(lambda checked: self.field_name_label.setVisible(not checked) if hasattr(self, 'field_name_label') else None)
            self.space_voxel.toggled.connect(lambda checked: self.field_name_input.setVisible(not checked) if hasattr(self, 'field_name_input') else None)
    

    def _update_coordinate_space_labels(self):
        """Update coordinate space labels and tooltips based on analysis mode."""
        if hasattr(self, 'coordinates_label') and hasattr(self, 'coord_x'):
            if self.is_group_mode:
                # Group mode: use MNI coordinates
                self.coordinates_label.setText("MNI RAS (x,y,z):")
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
            else:
                # Single mode: use subject coordinates
                self.coordinates_label.setText("Subject RAS (x,y,z):")
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

    def get_selected_subjects(self):
        """Get selected subjects from pairs table."""
        subjects = set()
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            if subject_combo:
                subject_id = subject_combo.currentText()
                if subject_id:
                    subjects.add(subject_id)
        return list(subjects)
    

    def on_subject_selection_changed(self):
        """Handle subject selection changes - update UI accordingly."""
        selected_subjects = self.get_selected_subjects()

        if self.is_group_mode:
            if not selected_subjects:
                # Clear configurations if no subjects selected
                self.group_atlas_config = {}
        else:
            # In single mode, update widgets
            self.update_atlas_combo()

        # Always recheck for valid atlases when subject selection changes
        self.update_atlas_combo()
        if self.is_group_mode and self.type_cortical.isChecked():
            self.update_group_atlas_options()

        self.update_atlas_visibility()

    
    def create_pairs_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Table for subject-simulation pairs
        pairs_group = QtWidgets.QGroupBox("Subject-Simulation Pairs")
        pairs_layout = QtWidgets.QVBoxLayout(pairs_group)

        self.pairs_table = QtWidgets.QTableWidget()
        self.pairs_table.setColumnCount(3)
        self.pairs_table.setHorizontalHeaderLabels(["Subject", "Simulation", ""])
        self.pairs_table.horizontalHeader().setStretchLastSection(False)
        self.pairs_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.pairs_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.pairs_table.setColumnWidth(2, 50)
        self.pairs_table.setMaximumHeight(250)
        pairs_layout.addWidget(self.pairs_table)

        # Buttons for managing pairs
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(5)

        self.add_pair_btn = QtWidgets.QPushButton("+ Add Pair")
        self.add_pair_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.add_pair_btn.clicked.connect(self.add_pair_row)
        buttons_layout.addWidget(self.add_pair_btn)

        self.quick_add_btn = QtWidgets.QPushButton("Quick Add")
        self.quick_add_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.quick_add_btn.setToolTip("Add the same simulation to multiple subjects at once")
        self.quick_add_btn.clicked.connect(self.quick_add_pairs)
        buttons_layout.addWidget(self.quick_add_btn)

        self.clear_pairs_btn = QtWidgets.QPushButton("Clear All")
        self.clear_pairs_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.clear_pairs_btn.clicked.connect(self.clear_all_pairs)
        buttons_layout.addWidget(self.clear_pairs_btn)

        self.refresh_pairs_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_pairs_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.refresh_pairs_btn.clicked.connect(self.refresh_pairs)
        buttons_layout.addWidget(self.refresh_pairs_btn)

        buttons_layout.addStretch()
        pairs_layout.addLayout(buttons_layout)
        layout.addWidget(pairs_group)
        

        # Add one empty row by default so the UI isn't completely empty
        self.add_pair_row()

        return widget

    def add_pair_row(self):
        """Add a new row for subject-simulation pair selection."""
        row = self.pairs_table.rowCount()
        self.pairs_table.insertRow(row)

        # Subject combo
        subject_combo = QtWidgets.QComboBox()
        subjects = self.get_all_subjects()
        subject_combo.addItems(subjects)
        subject_combo.currentTextChanged.connect(lambda: self.update_sim_combo_in_row(row))
        self.pairs_table.setCellWidget(row, 0, subject_combo)

        # Simulation combo
        sim_combo = QtWidgets.QComboBox()
        if subjects:
            sims = self.pm.list_simulations(subjects[0])
            sim_combo.addItems(sims)
        self.pairs_table.setCellWidget(row, 1, sim_combo)

        # Remove button
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setMaximumWidth(40)
        remove_btn.clicked.connect(lambda: self.remove_pair(row))
        self.pairs_table.setCellWidget(row, 2, remove_btn)

        # Update UI after adding pair
        self.on_pairs_changed()

    def update_sim_combo_in_row(self, row):
        """Update the simulation combo box when subject changes in a row."""
        subject_combo = self.pairs_table.cellWidget(row, 0)
        sim_combo = self.pairs_table.cellWidget(row, 1)

        if subject_combo and sim_combo:
            subject_id = subject_combo.currentText()
            if subject_id:
                sims = self.pm.list_simulations(subject_id)
                sim_combo.clear()
                sim_combo.addItems(sims)

    def remove_pair(self, row):
        """Remove a subject-simulation pair row."""
        self.pairs_table.removeRow(row)
        self.on_pairs_changed()

    def clear_all_pairs(self):
        """Clear all subject-simulation pairs."""
        self.pairs_table.setRowCount(0)
        self.on_pairs_changed()

    def refresh_pairs(self):
        """Refresh all subject and simulation combos in the pairs table."""
        all_subjects = self.get_all_subjects()
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)

            if subject_combo:
                current_subject = subject_combo.currentText()
                subject_combo.clear()
                subject_combo.addItems(all_subjects)
                if current_subject in all_subjects:
                    subject_combo.setCurrentText(current_subject)
                elif all_subjects:
                    subject_combo.setCurrentText(all_subjects[0])

            if sim_combo and subject_combo:
                subject_id = subject_combo.currentText()
                if subject_id:
                    sims = self.pm.list_simulations(subject_id)
                    current_sim = sim_combo.currentText()
                    sim_combo.clear()
                    sim_combo.addItems(sims)
                    if current_sim in sims:
                        sim_combo.setCurrentText(current_sim)

    def quick_add_pairs(self):
        """Open dialog to quickly add the same simulation to all subjects."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Quick Add Subject-Simulation Pairs")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Simulation selection
        sim_layout = QtWidgets.QHBoxLayout()
        sim_layout.addWidget(QtWidgets.QLabel("Simulation:"))
        sim_combo = QtWidgets.QComboBox()

        # Get all unique simulations across all subjects
        all_sims = set()
        all_subjects = self.get_all_subjects()
        for subject in all_subjects:
            all_sims.update(self.pm.list_simulations(subject))
        sim_combo.addItems(sorted(all_sims))
        sim_layout.addWidget(sim_combo)
        layout.addLayout(sim_layout)

        # Info label
        info_label = QtWidgets.QLabel("This will add the selected simulation for all subjects that have it.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-style: italic; padding: 10px;")
        layout.addWidget(info_label)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add All")
        cancel_btn = QtWidgets.QPushButton("Cancel")

        add_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addWidget(add_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_simulation = sim_combo.currentText()

            # Add pairs for all subjects that have this simulation
            added_count = 0
            skipped_count = 0
            for subject_id in all_subjects:
                # Check if this subject has the selected simulation
                available_sims = self.pm.list_simulations(subject_id)
                if selected_simulation not in available_sims:
                    continue

                # Check for duplicates
                duplicate = False
                for row in range(self.pairs_table.rowCount()):
                    existing_subject = self.pairs_table.cellWidget(row, 0).currentText()
                    existing_sim = self.pairs_table.cellWidget(row, 1).currentText()
                    if existing_subject == subject_id and existing_sim == selected_simulation:
                        duplicate = True
                        break

                if duplicate:
                    skipped_count += 1
                    continue

                # Add new row
                row = self.pairs_table.rowCount()
                self.pairs_table.insertRow(row)

                # Subject combo
                subject_combo_widget = QtWidgets.QComboBox()
                subject_combo_widget.addItems(all_subjects)
                subject_combo_widget.setCurrentText(subject_id)
                subject_combo_widget.currentTextChanged.connect(lambda: self.update_sim_combo_in_row(row))
                self.pairs_table.setCellWidget(row, 0, subject_combo_widget)

                # Simulation combo
                sim_combo_widget = QtWidgets.QComboBox()
                sim_combo_widget.addItems(available_sims)
                sim_combo_widget.setCurrentText(selected_simulation)
                self.pairs_table.setCellWidget(row, 1, sim_combo_widget)

                # Remove button
                remove_btn = QtWidgets.QPushButton("✕")
                remove_btn.setMaximumWidth(40)
                remove_btn.clicked.connect(lambda checked, r=row: self.remove_pair(r))
                self.pairs_table.setCellWidget(row, 2, remove_btn)

                added_count += 1

            message = f"\nAdded {added_count} subject-simulation pairs"
            if skipped_count > 0:
                message += f" ({skipped_count} skipped - already exist)"
            self.update_output(message)

            # Update UI after adding pairs
            self.on_pairs_changed()

    def get_all_subjects(self):
        """Get all available subjects."""
        from core import list_subjects
        try:
            return list_subjects()
        except Exception:
            return []

    
    def create_analysis_parameters_widget(self, container_widget):
        right_layout = QtWidgets.QVBoxLayout(container_widget)
        right_layout.setContentsMargins(5, 0, 5, 0)  # Reduce side margins

        analysis_params_container = QtWidgets.QGroupBox("Analysis Configuration")
        self.analysis_params_container = analysis_params_container
        analysis_params_layout = QtWidgets.QVBoxLayout(analysis_params_container)
        analysis_params_layout.setSpacing(8)
        
        # Space selection row - distribute evenly across width
        space_layout = QtWidgets.QHBoxLayout()
        space_layout.setSpacing(10)
        self.space_label = QtWidgets.QLabel("Space:")
        self.space_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.space_mesh = QtWidgets.QRadioButton("Mesh")
        self.space_voxel = QtWidgets.QRadioButton("Voxel")
        self.space_mesh.setChecked(True)
        self.space_group = QtWidgets.QButtonGroup(self)
        self.space_group.addButton(self.space_mesh)
        self.space_group.addButton(self.space_voxel)
        
        space_layout.addWidget(self.space_label)
        space_layout.addWidget(self.space_mesh)
        space_layout.addWidget(self.space_voxel)
        space_layout.addStretch()  # Keep stretch to push radio buttons to left
        analysis_params_layout.addLayout(space_layout)
        
        # Type selection row (separate from Space) - distribute evenly across width
        type_layout = QtWidgets.QHBoxLayout()
        type_layout.setSpacing(10)
        self.type_label = QtWidgets.QLabel("Type:")
        self.type_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.type_spherical = QtWidgets.QRadioButton("Spherical")
        self.type_cortical = QtWidgets.QRadioButton("Cortical")
        self.type_spherical.setChecked(True)
        self.type_group = QtWidgets.QButtonGroup(self)
        self.type_group.addButton(self.type_spherical)
        self.type_group.addButton(self.type_cortical)
        
        type_layout.addWidget(self.type_label)
        type_layout.addWidget(self.type_spherical)
        type_layout.addWidget(self.type_cortical)
        type_layout.addStretch()  # Keep stretch to push radio buttons to left
        analysis_params_layout.addLayout(type_layout)

        # Region, Atlas, and Spherical parameters - organized into multiple rows
        # Row 1: Region input, All checkbox, and List Regions button
        region_row = QtWidgets.QHBoxLayout()
        region_row.setSpacing(10)
        self.region_label = QtWidgets.QLabel("Region:")
        self.region_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.region_input = QtWidgets.QLineEdit()
        self.region_input.setPlaceholderText("e.g., superiorfrontal")
        self.region_input.setMinimumWidth(100)
        self.region_input.setMaximumWidth(200)  # Allow some expansion
        
        self.whole_head_check = QtWidgets.QCheckBox("All")
        self.whole_head_check.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.whole_head_check.stateChanged.connect(self.toggle_region_input)
        
        self.show_regions_btn = QtWidgets.QPushButton("List Regions")
        self.show_regions_btn.setToolTip("Show available regions in the selected atlas")
        self.show_regions_btn.clicked.connect(self.show_available_regions)
        self.show_regions_btn.setEnabled(False)
        self.show_regions_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        
        region_row.addWidget(self.region_label)
        region_row.addWidget(self.region_input)
        region_row.addSpacing(5)
        region_row.addWidget(self.whole_head_check)
        region_row.addSpacing(5)
        region_row.addWidget(self.show_regions_btn)
        region_row.addStretch()
        analysis_params_layout.addLayout(region_row)
        
        # Row 2: Atlas selection (single widget that shows mesh or voxel based on space)
        atlas_row = QtWidgets.QHBoxLayout()
        atlas_row.setSpacing(10)
        
        # Atlas widgets - always visible, just enabled/disabled
        self.mesh_atlas_widget = QtWidgets.QWidget()
        mesh_atlas_layout = QtWidgets.QHBoxLayout(self.mesh_atlas_widget)
        mesh_atlas_layout.setContentsMargins(0, 0, 0, 0)
        mesh_atlas_layout.setSpacing(5)
        self.mesh_atlas_label = QtWidgets.QLabel("Atlas:")
        self.mesh_atlas_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.atlas_name_combo = QtWidgets.QComboBox()
        self.atlas_name_combo.addItems(["DK40", "HCP_MMP1", "a2009s"])
        self.atlas_name_combo.setCurrentText("DK40")
        self.atlas_name_combo.setMinimumWidth(100)
        self.atlas_name_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        mesh_atlas_layout.addWidget(self.mesh_atlas_label)
        mesh_atlas_layout.addWidget(self.atlas_name_combo)

        self.voxel_atlas_widget = QtWidgets.QWidget()
        voxel_atlas_vlayout = QtWidgets.QVBoxLayout(self.voxel_atlas_widget)
        voxel_atlas_vlayout.setContentsMargins(0, 0, 0, 0)
        voxel_atlas_vlayout.setSpacing(0)
        voxel_atlas_row = QtWidgets.QWidget()
        voxel_atlas_row_layout = QtWidgets.QHBoxLayout(voxel_atlas_row)
        voxel_atlas_row_layout.setContentsMargins(0, 0, 0, 0)
        voxel_atlas_row_layout.setSpacing(5)
        self.voxel_atlas_label = QtWidgets.QLabel("Atlas:")
        self.voxel_atlas_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.setEditable(False)
        self.atlas_combo.setMinimumWidth(100)
        self.atlas_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        voxel_atlas_row_layout.addWidget(self.voxel_atlas_label)
        voxel_atlas_row_layout.addWidget(self.atlas_combo)
        voxel_atlas_vlayout.addWidget(voxel_atlas_row)
        
        # Only add the appropriate atlas widget based on current space
        # Both will be in the layout, but only one enabled/visible at a time
        atlas_row.addWidget(self.mesh_atlas_widget)
        atlas_row.addWidget(self.voxel_atlas_widget)
        atlas_row.addStretch()
        analysis_params_layout.addLayout(atlas_row)

        # Spherical analysis parameters - split into separate rows
        
        # Row 3: Coordinates
        coordinates_row = QtWidgets.QHBoxLayout()
        coordinates_row.setSpacing(10)
        self.coordinates_label = QtWidgets.QLabel("Coordinates (x,y,z):")
        self.coordinates_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.coord_x = QtWidgets.QLineEdit()
        self.coord_y = QtWidgets.QLineEdit()
        self.coord_z = QtWidgets.QLineEdit()
        for coord_widget in [self.coord_x, self.coord_y, self.coord_z]:
            coord_widget.setPlaceholderText("0.0")
            coord_widget.setMinimumWidth(60)
            coord_widget.setMaximumWidth(100)  # Allow some expansion
            coord_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        coordinates_row.addWidget(self.coordinates_label)
        coordinates_row.addWidget(self.coord_x)
        coordinates_row.addWidget(self.coord_y)
        coordinates_row.addWidget(self.coord_z)
        coordinates_row.addStretch()
        analysis_params_layout.addLayout(coordinates_row)
        
        # Row 4: Radius and View in Freeview button
        radius_row = QtWidgets.QHBoxLayout()
        radius_row.setSpacing(10)
        self.radius_label = QtWidgets.QLabel("Radius:")
        self.radius_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.radius_input = QtWidgets.QLineEdit()
        self.radius_input.setPlaceholderText("5.0")
        self.radius_input.setMinimumWidth(60)
        self.radius_input.setMaximumWidth(100)  # Allow some expansion
        self.radius_input.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        radius_row.addWidget(self.radius_label)
        radius_row.addWidget(self.radius_input)
        
        self.view_in_freeview_btn = QtWidgets.QPushButton("View in Freeview")
        self.view_in_freeview_btn.setToolTip("View T1 in Freeview to help find coordinates")
        self.view_in_freeview_btn.clicked.connect(self.load_t1_in_freeview)
        self.view_in_freeview_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        radius_row.addSpacing(10)
        radius_row.addWidget(self.view_in_freeview_btn)
        radius_row.addStretch()
        analysis_params_layout.addLayout(radius_row)
        
        # Remove the stacked widget approach - coordinates/radius are always visible
        # Instead, we'll enable/disable them based on mode
        
        # Original connections from setup_ui for space/type changes
        self.space_mesh.toggled.connect(self.update_atlas_visibility)
        self.space_voxel.toggled.connect(self.update_atlas_visibility)
        self.type_spherical.toggled.connect(self.update_atlas_visibility)
        self.type_cortical.toggled.connect(self.update_atlas_visibility)
        
        
        
        # Connect signals to update cortical button text based on space
        self.space_mesh.toggled.connect(self.update_cortical_button_text)
        self.space_voxel.toggled.connect(self.update_cortical_button_text)

        self.update_atlas_visibility() # Initial call
        self.update_cortical_button_text() # Initial call
        right_layout.addWidget(analysis_params_container)

        # Compact Gmsh visualization - using space more efficiently
        visualization_container = QtWidgets.QGroupBox("Gmsh Visualization")
        visualization_layout = QtWidgets.QVBoxLayout(visualization_container)
        visualization_layout.setSpacing(8)

        # Top row: Subject and Simulation - evenly distribute space
        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(10)
        subject_label = QtWidgets.QLabel("Subject:")
        subject_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        top_row.addWidget(subject_label)
        self.gmsh_subject_combo = QtWidgets.QComboBox()
        self.gmsh_subject_combo.setMinimumWidth(120)
        self.gmsh_subject_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        top_row.addWidget(self.gmsh_subject_combo)
        top_row.addSpacing(15)
        simulation_label = QtWidgets.QLabel("Simulation:")
        simulation_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        top_row.addWidget(simulation_label)
        self.gmsh_sim_combo = QtWidgets.QComboBox()
        self.gmsh_sim_combo.setMinimumWidth(120)
        self.gmsh_sim_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        top_row.addWidget(self.gmsh_sim_combo)
        visualization_layout.addLayout(top_row)

        # Bottom row: Analysis and Launch button - evenly distribute space
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setSpacing(10)
        analysis_label = QtWidgets.QLabel("Analysis:")
        analysis_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        bottom_row.addWidget(analysis_label)
        self.gmsh_analysis_combo = QtWidgets.QComboBox()
        self.gmsh_analysis_combo.setMinimumWidth(120)
        self.gmsh_analysis_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        bottom_row.addWidget(self.gmsh_analysis_combo)
        bottom_row.addSpacing(15)
        self.launch_gmsh_btn = QtWidgets.QPushButton("Launch Gmsh")
        self.launch_gmsh_btn.clicked.connect(self.launch_gmsh_simple)
        self.launch_gmsh_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        bottom_row.addWidget(self.launch_gmsh_btn)
        bottom_row.addStretch()
        visualization_layout.addLayout(bottom_row)

        right_layout.addWidget(visualization_container)

        # Connect gmsh dropdown signals after widgets are created
        self.gmsh_subject_combo.currentTextChanged.connect(self.update_gmsh_simulations)
        self.gmsh_sim_combo.currentTextChanged.connect(self.update_gmsh_analyses)

        # Initial update for gmsh
        self.update_gmsh_subjects()

        return right_layout


    def get_available_atlas_files(self, subject_id):
        atlas_files = []
        if not subject_id: return atlas_files

        # Freesurfer path uses full subject ID for both levels, e.g., sub-001/sub-001/mri
        freesurfer_mri_dir = get_freesurfer_mri_dir(subject_id)

        atlases_to_check = ['aparc.DKTatlas+aseg.mgz', 'aparc.a2009s+aseg.mgz']

        if freesurfer_mri_dir and os.path.isdir(freesurfer_mri_dir): # Check if subject's FS mri dir exists
            for atlas_filename in atlases_to_check:
                full_path = os.path.join(freesurfer_mri_dir, atlas_filename)
                if os.path.exists(full_path):
                    atlas_files.append((atlas_filename, full_path))

        # Check for SimNIBS labeling.nii.gz atlas
        m2m_dir = get_m2m_dir(subject_id)
        if m2m_dir:
            labeling_path = os.path.join(m2m_dir, "segmentation", "labeling.nii.gz")
            if os.path.exists(labeling_path):
                atlas_files.append(("SimNIBS labeling", labeling_path))
        
        if not atlas_files:
            atlas_files.append("FreeSurfer recon-all preprocessing required for atlas generation")
        return atlas_files


    def update_atlas_combo(self):
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

    def browse_atlas(self):
        initial_dir = ""
        selected_subjects = self.get_selected_subjects()
        if selected_subjects:
            subject_id = selected_subjects[0]
            m2m_dir_path = self.pm.get_m2m_dir(subject_id)
            if m2m_dir_path and os.path.exists(m2m_dir_path): # Check existence
                initial_dir = os.path.join(m2m_dir_path, 'segmentation') 
        
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Atlas File", initial_dir,
            "Atlas Files (*.nii *.nii.gz *.mgz);;All Files (*)")
        
        if file_name:
            base_name = os.path.basename(file_name)
            existing_index = -1
            for i in range(self.atlas_combo.count()):
                if self.atlas_combo.itemData(i) == file_name: # Check by path
                    existing_index = i
                    break
            if existing_index != -1:
                self.atlas_combo.setCurrentIndex(existing_index)
            else:
                self.atlas_combo.addItem(base_name, file_name)
                self.atlas_combo.setCurrentIndex(self.atlas_combo.count() - 1)
            
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
        is_spherical = self.type_spherical.isChecked()
        
        # Hide warning label in group mode - it should never show in group mode
        if self.is_group_mode and hasattr(self, 'atlas_warning_label'):
            self.atlas_warning_label.setVisible(False)
        
        # Atlas widgets - show only the relevant one based on space, enabled when cortical
        mesh_atlas_visible = is_mesh
        voxel_atlas_visible = not is_mesh
        mesh_atlas_enabled = is_mesh and is_cortical
        voxel_atlas_enabled = not is_mesh and is_cortical
        
        # Show only the relevant atlas widget based on space selection
        self.mesh_atlas_widget.setVisible(mesh_atlas_visible)
        self.voxel_atlas_widget.setVisible(voxel_atlas_visible)
        
        # Enable only when both space matches and cortical mode is selected
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
        
        # Coordinates and radius are always visible, enabled only in spherical mode
        coordinates_enabled = is_spherical
        if hasattr(self, 'coordinates_label'):
            self.coordinates_label.setEnabled(coordinates_enabled)
        if hasattr(self, 'coord_x'):
            self.coord_x.setEnabled(coordinates_enabled)
            self.coord_y.setEnabled(coordinates_enabled)
            self.coord_z.setEnabled(coordinates_enabled)
        if hasattr(self, 'view_in_freeview_btn'):
            self.view_in_freeview_btn.setEnabled(coordinates_enabled)
        
        if hasattr(self, 'radius_label'):
            self.radius_label.setEnabled(coordinates_enabled)
        if hasattr(self, 'radius_input'):
            self.radius_input.setEnabled(coordinates_enabled)
        
        self.mesh_atlas_widget.update()
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

    def update_group_atlas_options(self):
        if not self.is_group_mode: return
        selected_subjects = self.get_selected_subjects()
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

    def update_group_mesh_atlas(self, atlas_name):
        if not self.is_group_mode or not self.space_mesh.isChecked() or not self.type_cortical.isChecked(): return

        selected_subjects = self.get_selected_subjects()
        for subject_id in selected_subjects:
            # For mesh, atlas name is sufficient, path is not needed from subject's dir for SimNIBS subject_atlas
            self.group_atlas_config[subject_id] = {'name': atlas_name, 'path': None, 'type': 'mesh'}

    def update_group_voxel_atlas(self, atlas_display_name_from_shared_combo):
        if not self.is_group_mode or not self.space_voxel.isChecked() or not self.type_cortical.isChecked(): return

        selected_subjects = self.get_selected_subjects()
        
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


    def toggle_region_input(self, state_int):
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
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one subject-simulation pair.")
            return False
        if self.pairs_table.rowCount() != 1:
            # For group mode, validate that all pairs have subjects and simulations
            for row in range(self.pairs_table.rowCount()):
                subject_combo = self.pairs_table.cellWidget(row, 0)
                sim_combo = self.pairs_table.cellWidget(row, 1)
                if not subject_combo or not sim_combo:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please complete all subject-simulation pairs.")
                    return False
                if not subject_combo.currentText() or not sim_combo.currentText():
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select both subject and simulation for all pairs.")
                    return False
        else:
            # For single mode, check the single pair
            subject_combo = self.pairs_table.cellWidget(0, 0)
            sim_combo = self.pairs_table.cellWidget(0, 1)
            if not subject_combo or not sim_combo or not subject_combo.currentText() or not sim_combo.currentText():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select both subject and simulation.")
                return False
        return self.validate_analysis_parameters()
    
    def validate_group_inputs(self):
        # Check that we have at least one subject-simulation pair
        if self.pairs_table.rowCount() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please add at least one subject-simulation pair for group analysis.")
            return False

        # Validate each pair in the table
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)

            if subject_combo and sim_combo:
                subject_id = subject_combo.currentText()
                simulation_name = sim_combo.currentText()

                if not subject_id or not simulation_name:
                    QtWidgets.QMessageBox.warning(self, "Warning", f"Please complete the subject-simulation pair in row {row + 1}.")
                    return False
            else:
                QtWidgets.QMessageBox.warning(self, "Warning", f"Invalid subject-simulation pair in row {row + 1}.")
                return False
            
        
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
            details = self.get_group_analysis_details([])
            title = f"Confirm Group Analysis ({self.pairs_table.rowCount()} subject-simulation pairs)"
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
            # In single mode, get the subject and simulation from the single pair
            if self.pairs_table.rowCount() != 1:
                self.update_output("Error: Single analysis requires exactly one subject-simulation pair.")
                self.analysis_finished(success=False)
                return

            subject_combo = self.pairs_table.cellWidget(0, 0)
            sim_combo = self.pairs_table.cellWidget(0, 1)

            if not subject_combo or not sim_combo:
                self.update_output("Error: Subject-simulation pair not properly configured.")
                self.analysis_finished(success=False)
                return

            subject_id = subject_combo.currentText()
            simulation_name = sim_combo.currentText()

            if not subject_id or not simulation_name:
                self.update_output("Error: Subject or simulation not selected.")
                self.analysis_finished(success=False)
                return

            cmd = self.build_single_analysis_command(subject_id, simulation_name)
            if not cmd: # build_analysis_command returns None on error
                self.analysis_finished(success=False)
                return
            
            env = os.environ.copy()
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            env['PROJECT_DIR'] = f"/mnt/{project_dir_name}"
            env['SUBJECT_ID'] = subject_id # Passed to script via env
            
            # Mark thread start as early as possible to avoid race double-starts
            self._thread_started = True

            # Clear summary printed set at start of new analysis to ensure summary output shows
            if hasattr(self, '_summary_printed'):
                self._summary_printed.clear()
            else:
                self._summary_printed = set()

            # Summary-mode: headline and initial step (guard against duplicates)
            if self.SUMMARY_MODE and not getattr(self, '_summary_started', False):
                # Record output dir for later summary line
                self._last_output_dir = self._extract_output_dir_from_cmd(cmd)
                # Mark started to avoid duplicated blocks
                # Note: The analyzer process will print all the step messages via its logging functions
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
        try:
            # Build the group analyzer command
            cmd = self.build_group_analyzer_command()
            if not cmd:
                self.update_output("Error: Could not build group analyzer command.")
                self.analysis_finished(success=False)
                return

            env = os.environ.copy()
            project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            env['PROJECT_DIR'] = f"/mnt/{project_dir_name}"
            
            # Clear summary printed set at start of new analysis to ensure summary output shows
            if hasattr(self, '_summary_printed'):
                self._summary_printed.clear()
            else:
                self._summary_printed = set()
            
            if self.SUMMARY_MODE:
                # For group we still provide a concise start message
                pairs_summary = []
                for row in range(self.pairs_table.rowCount()):
                    subject_combo = self.pairs_table.cellWidget(row, 0)
                    sim_combo = self.pairs_table.cellWidget(row, 1)
                    if subject_combo and sim_combo:
                        subject_id = subject_combo.currentText()
                        simulation_name = sim_combo.currentText()
                        if subject_id and simulation_name:
                            pairs_summary.append(f"{subject_id}({simulation_name})")
                self.ANALYSIS_START_TIME = time.time()
                self.update_output(f"Beginning group analysis for pairs: {', '.join(pairs_summary)}")
                self._last_output_dir = self._extract_output_dir_from_cmd(cmd)
            else:
                pairs_summary = []
                for row in range(self.pairs_table.rowCount()):
                    subject_combo = self.pairs_table.cellWidget(row, 0)
                    sim_combo = self.pairs_table.cellWidget(row, 1)
                    if subject_combo and sim_combo:
                        subject_id = subject_combo.currentText()
                        simulation_name = sim_combo.currentText()
                        if subject_id and simulation_name:
                            pairs_summary.append(f"{subject_id}({simulation_name})")
                self.update_output(f"Starting group analysis for pairs: {', '.join(pairs_summary)}")
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
    
    def build_group_analyzer_command(self):
        """Build command to run group_analyzer.py with all selected subjects."""
        try:
            # Locate group_analyzer.py script
            app_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            group_analyzer_script_path = os.path.join(app_root_dir, 'analyzer', 'group_analyzer.py')
            if not os.path.exists(group_analyzer_script_path):
                self.update_output(f"Error: group_analyzer.py not found at {group_analyzer_script_path}")
                return None

            # Build base command with temporary output directory (group_analyzer.py will create the actual organized directories)
            project_dir = self.pm.get_project_dir()
            if not project_dir:
                self.update_output("Error: Could not determine project directory")
                return None
            temp_output_dir = self.pm.get_simnibs_dir()
            
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

            # Add subject specifications from pairs table
            for row in range(self.pairs_table.rowCount()):
                subject_combo = self.pairs_table.cellWidget(row, 0)
                sim_combo = self.pairs_table.cellWidget(row, 1)

                if subject_combo and sim_combo:
                    subject_id = subject_combo.currentText()
                    simulation_name = sim_combo.currentText()

                    if not subject_id or not simulation_name:
                        self.update_output(f"Error: Incomplete subject-simulation pair in row {row + 1}")
                        return None
                else:
                    self.update_output(f"Error: Invalid subject-simulation pair in row {row + 1}")
                    return None
                # Get m2m path
                m2m_path = self.pm.get_m2m_dir(subject_id)
                if not m2m_path or not os.path.isdir(m2m_path):
                    self.update_output(f"Error: m2m_{subject_id} folder not found at {m2m_path}. Please create the m2m folder first using the Pre-process tab.", 'error')
                    return None

                # Construct field path or montage name based on analysis space
                if self.space_mesh.isChecked():
                    # For mesh analysis, use montage name (same as single subject analysis)
                    field_path = simulation_name  # This will be treated as montage name by group_analyzer.py
                else:
                    # For voxel analysis, look for appropriate NIfTI file
                    base_sim_dir = self.pm.get_simulation_dir(subject_id, simulation_name)
                    nifti_dir = os.path.join(base_sim_dir, 'mTI', 'niftis') if os.path.exists(os.path.join(base_sim_dir, 'mTI', 'niftis')) else os.path.join(base_sim_dir, 'TI', 'niftis')
                    # Prefer grey matter files, then any other file
                    grey_files = [f for f in os.listdir(nifti_dir) if f.startswith('grey_') and not f.endswith('_MNI.nii.gz')] if os.path.exists(nifti_dir) else []
                    if grey_files:
                        field_path = os.path.join(nifti_dir, grey_files[0])
                    else:
                        # Fallback to any NIfTI file
                        nii_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii') or f.endswith('.nii.gz')] if os.path.exists(nifti_dir) else []
                        if nii_files:
                            field_path = os.path.join(nifti_dir, nii_files[0])
                        else:
                            field_path = None

                    if not field_path or not os.path.exists(field_path):
                        self.update_output(f"Error: Field file not found for subject {subject_id}, simulation {simulation_name} (expected: {field_path})")
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
        if self.pairs_table.rowCount() != 1:
            return "Single analysis requires exactly one subject-simulation pair."

        subject_combo = self.pairs_table.cellWidget(0, 0)
        sim_combo = self.pairs_table.cellWidget(0, 1)

        if not subject_combo or not sim_combo:
            return "Subject-simulation pair not properly configured."

        subj = subject_combo.currentText()
        mont = sim_combo.currentText()

        if not subj or not mont:
            return "Subject or simulation not selected."

        space = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
        atype = 'Spherical' if self.type_spherical.isChecked() else 'Cortical'
        details = f"- Subject: {subj}\n- Space: {space}\n- Analysis Type: {atype}\n- Simulation: {mont}\n"
        if self.space_mesh.isChecked():
            details += f"- Field File: {mont}.msh (auto-selected)\n"
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

        # Collect subject-simulation pairs
        pairs_info = []
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)
            if subject_combo and sim_combo:
                subject_id = subject_combo.currentText()
                simulation_name = sim_combo.currentText()
                if subject_id and simulation_name:
                    pairs_info.append(f"{subject_id}({simulation_name})")

        details = (f"- Subject-Simulation Pairs: {', '.join(pairs_info)}\n- Space: {space}\n- Analysis Type: {analysis_type}\n")
        
        
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
        self.update_atlas_visibility()

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
                    # Note: The analyzer process already prints all step completion messages via its logging functions.
                    # We just need to mark that the summary is finished to avoid duplicate processing.
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
                    analysis_type_str = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
                    # For group mode, emit with first subject and 'group_analysis' as simulation name
                    if self.pairs_table.rowCount() > 0:
                        first_subject_combo = self.pairs_table.cellWidget(0, 0)
                        if first_subject_combo:
                            first_subject = first_subject_combo.currentText()
                            self.analysis_completed.emit(first_subject, 'group_analysis', analysis_type_str)
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
            # Clear the summary printed set to allow summary output on next run
            if hasattr(self, '_summary_printed'):
                self._summary_printed.clear()
            
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
            if low.startswith('├─ field data loading: started') and 'field_start' in self._summary_printed:
                return
            if low.startswith('├─ field data loading: ✓ complete') and 'field_done' in self._summary_printed:
                return
            if (low.startswith('├─ cortical analysis: started') or low.startswith('├─ spherical analysis: started')) and 'analysis_start' in self._summary_printed:
                return
            if (low.startswith('├─ cortical analysis: ✓ complete') or low.startswith('├─ spherical analysis: ✓ complete')) and 'analysis_done' in self._summary_printed:
                return
            if low.startswith('├─ results saving: started') and 'results_start' in self._summary_printed:
                return
            if low.startswith('├─ results saving: ✓ complete') and 'results_done' in self._summary_printed:
                return
            if low.startswith('└─ analysis completed successfully for subject:') and 'final' in self._summary_printed:
                return
            # Colorize summary lines: blue for starts, green for completes, bright green for final
            is_final = low.startswith('└─') or 'completed successfully' in low
            is_start = (low.startswith('beginning ') or ': started' in low or
                       ': starting' in low or 'starting...' in low)
            is_complete = ('✓ complete' in low) or ('results available in:' in low) or ('saved to' in low)
            color = '#55ff55' if is_final else ('#55aaff' if is_start else ('#88ff88' if is_complete else '#ffffff'))
            formatted = f'<span style="color: {color};">{text}</span>'
            self.output_console.append(formatted)
            self._last_plain_output_line = text
            # Mark printed flags for summary lines
            if low.startswith('beginning analysis for subject:'):
                self._summary_printed.add('headline')
            elif low.startswith('├─ field data loading: started'):
                self._summary_printed.add('field_start')
            elif low.startswith('├─ field data loading: ✓ complete'):
                self._summary_printed.add('field_done')
            elif low.startswith('├─ cortical analysis: started') or low.startswith('├─ spherical analysis: started'):
                self._summary_printed.add('analysis_start')
            elif low.startswith('├─ cortical analysis: ✓ complete') or low.startswith('├─ spherical analysis: ✓ complete'):
                self._summary_printed.add('analysis_done')
            elif low.startswith('├─ results saving: started'):
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
            # Pair management buttons
            self.add_pair_btn, self.quick_add_btn, self.clear_pairs_btn, self.refresh_pairs_btn,
            # Other widgets
            self.space_mesh, self.space_voxel, self.type_spherical, self.type_cortical,
            self.coord_x, self.coord_y, self.coord_z, self.radius_input,
            self.view_in_freeview_btn,
            self.atlas_name_combo, self.atlas_combo, self.show_regions_btn, self.region_input, self.whole_head_check
        ]
        for widget in widgets_to_set_enabled:
            if hasattr(widget, 'setEnabled'): widget.setEnabled(False)

        
        # Keep debug checkbox enabled during processing
        if hasattr(self, 'console_widget') and hasattr(self.console_widget, 'debug_checkbox'):
            self.console_widget.debug_checkbox.setEnabled(True)
        
        self.status_label.setText("Processing... Stop button and Debug Mode are available.")
        self.status_label.show()

    def enable_controls(self):
        widgets_to_set_enabled = [
            # Pair management buttons
            self.add_pair_btn, self.quick_add_btn, self.clear_pairs_btn, self.refresh_pairs_btn,
            # Other widgets
            self.space_mesh, self.space_voxel, self.type_spherical, self.type_cortical,
            self.coord_x, self.coord_y, self.coord_z, self.radius_input,
            self.view_in_freeview_btn,
            # atlas_name_combo, atlas_combo, show_regions_btn, region_input, whole_head_check handled by update_atlas_visibility
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

        
        # Spherical analysis should be enabled in both modes
        self.type_spherical.setEnabled(True)

        self.status_label.hide()



    def show_available_regions(self):
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
                m2m_dir = self.pm.get_m2m_dir(subject_id)
                if not m2m_dir: QtWidgets.QMessageBox.critical(self, "Error", f"m2m dir not found: {subject_id}."); return
                
                progress_dialog.setValue(20); QtWidgets.QApplication.processEvents()
                try:
                    import simnibs
                    atlas = simnibs.subject_atlas(atlas_name_simnibs, m2m_dir)
                    regions = sorted(atlas.keys())
                    progress_dialog.setValue(80); QtWidgets.QApplication.processEvents()
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

            def filter_regions_local(text_filt):
                for i in range(list_widget_diag.count()): list_widget_diag.item(i).setHidden(text_filt.lower() not in list_widget_diag.item(i).text().lower())
            def copy_selected_local():
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
                        "MNI152 template not found. Please ensure FSL is installed or place MNI152_T1_1mm.nii.gz in resources/atlas/")
                    return
                
                # Launch Freeview with MNI template
                subprocess.Popen(["freeview", mni_file])
                self.update_output(f"Launched Freeview with MNI152 template: {mni_file}")
                self.update_output("Use Freeview to find MNI coordinates and enter them in the coordinate fields.")
                self.update_output("These MNI coordinates will be automatically transformed to each subject's native space.")
            else:
                # Single mode or non-spherical: load subject's T1
                subject_id = selected_subjects[0]
                m2m_dir_path = self.pm.get_m2m_dir(subject_id)
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


    def update_field_files(self, analyzed_subject_id=None, analyzed_simulation_name=None):
        """Update field files list after analysis completion.

        This method is called from main.py after analysis completion.
        Refreshes the gmsh visualization dropdowns to show newly available meshes.
        
        Parameters
        ----------
        analyzed_subject_id : str, optional
            The subject ID that was just analyzed. If provided, the gmsh dropdowns
            will be set to this subject/simulation and the analyses list will be refreshed.
        analyzed_simulation_name : str, optional
            The simulation name that was just analyzed. If provided along with subject_id,
            the gmsh dropdowns will be set to this subject/simulation.
        """
        # Refresh gmsh visualization dropdowns to show newly created mesh analyses
        if hasattr(self, 'gmsh_subject_combo') and hasattr(self, 'gmsh_sim_combo'):
            # Refresh subjects list (in case new subjects were added)
            self.update_gmsh_subjects()
            
            # If we have the analyzed subject/simulation, set the dropdowns to match
            if analyzed_subject_id:
                index = self.gmsh_subject_combo.findText(analyzed_subject_id)
                if index >= 0:
                    self.gmsh_subject_combo.setCurrentIndex(index)
                    # This will trigger update_gmsh_simulations() via signal connection
                    # Use a small delay to ensure simulations are updated first
                    if analyzed_simulation_name:
                        QtCore.QTimer.singleShot(50, lambda: self._set_gmsh_simulation(analyzed_simulation_name))
                    else:
                        # Just update simulations for the selected subject
                        self.update_gmsh_simulations()
                else:
                    # Subject not found, just update simulations for first subject if available
                    if self.gmsh_subject_combo.count() > 0:
                        self.update_gmsh_simulations()
            else:
                # No analyzed subject provided, preserve current selection if possible
                current_subject = self.gmsh_subject_combo.currentText()
                current_sim = self.gmsh_sim_combo.currentText()
                
                if current_subject:
                    index = self.gmsh_subject_combo.findText(current_subject)
                    if index >= 0:
                        self.gmsh_subject_combo.setCurrentIndex(index)
                        if current_sim:
                            QtCore.QTimer.singleShot(50, lambda: self._restore_gmsh_selection(current_sim))
                    else:
                        # Subject no longer exists, just update simulations for first subject
                        self.update_gmsh_simulations()
                else:
                    # No subject was selected, just update simulations for first subject if available
                    if self.gmsh_subject_combo.count() > 0:
                        self.update_gmsh_simulations()
    
    def _set_gmsh_simulation(self, simulation_name):
        """Helper method to set gmsh simulation selection and refresh analyses."""
        if hasattr(self, 'gmsh_sim_combo'):
            index = self.gmsh_sim_combo.findText(simulation_name)
            if index >= 0:
                self.gmsh_sim_combo.setCurrentIndex(index)
                # This will trigger update_gmsh_analyses() via signal connection
            else:
                # Simulation not found, just update analyses for first simulation
                self.update_gmsh_analyses()
    
    def _restore_gmsh_selection(self, simulation_name):
        """Helper method to restore gmsh simulation selection after refresh."""
        if hasattr(self, 'gmsh_sim_combo'):
            index = self.gmsh_sim_combo.findText(simulation_name)
            if index >= 0:
                self.gmsh_sim_combo.setCurrentIndex(index)
                # This will trigger update_gmsh_analyses() via signal connection
            else:
                # Simulation no longer exists, just update analyses for first simulation
                self.update_gmsh_analyses()

    def update_gmsh_subjects(self):
        """Update the gmsh subject dropdown with available subjects."""
        self.gmsh_subject_combo.clear()
        # Use path_manager to find subjects via m2m_dir
        subjects = self.pm.list_subjects()
        if subjects:
            self.gmsh_subject_combo.addItems(subjects)
            if len(subjects) == 1:
                self.gmsh_subject_combo.setCurrentIndex(0)
                self.update_gmsh_simulations()

    def update_gmsh_simulations(self):
        """Update the gmsh simulation dropdown based on selected subject."""
        self.gmsh_sim_combo.clear()
        subject_id = self.gmsh_subject_combo.currentText()
        if not subject_id:
            return

        # Use sim_dir to find simulations via path_manager
        simulations = self.pm.list_simulations(subject_id)
        if simulations:
            self.gmsh_sim_combo.addItems(simulations)
            if len(simulations) == 1:
                self.gmsh_sim_combo.setCurrentIndex(0)
                self.update_gmsh_analyses()

    def update_gmsh_analyses(self):
        """Update the gmsh analysis dropdown based on selected subject and simulation."""
        self.gmsh_analysis_combo.clear()
        subject_id = self.gmsh_subject_combo.currentText()
        simulation_name = self.gmsh_sim_combo.currentText()

        if not subject_id or not simulation_name:
            return

        # Look specifically in Analyses/Mesh/ for mesh analysis folders
        sim_dir = self.pm.get_simulation_dir(subject_id, simulation_name)
        mesh_dir = os.path.join(sim_dir, "Analyses", "Mesh") if sim_dir else None

        if not mesh_dir or not os.path.exists(mesh_dir):
            return

        try:
            # Look for mesh analysis folders in Analyses/Mesh/
            mesh_analyses = []
            for item in os.listdir(mesh_dir):
                item_path = os.path.join(mesh_dir, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    # Check if this analysis folder contains any .msh files
                    has_meshes = False
                    for root, _, files in os.walk(item_path):
                        if any(f.endswith('.msh') for f in files):
                            has_meshes = True
                            break
                    if has_meshes:
                        mesh_analyses.append(item)

            if mesh_analyses:
                self.gmsh_analysis_combo.addItems(sorted(mesh_analyses))
                if len(mesh_analyses) == 1:
                    self.gmsh_analysis_combo.setCurrentIndex(0)
        except Exception as e:
            self.update_output(f"Error listing mesh analyses: {e}")

    def launch_gmsh_simple(self):
        """Launch Gmsh with the selected subject, simulation, and analysis."""
        subject_id = self.gmsh_subject_combo.currentText()
        simulation_name = self.gmsh_sim_combo.currentText()
        analysis_name = self.gmsh_analysis_combo.currentText()

        if not subject_id or not simulation_name or not analysis_name:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select subject, simulation, and analysis first")
            return

        # Find the analysis directory in Analyses/Mesh/ and look for .msh files
        sim_dir = self.pm.get_simulation_dir(subject_id, simulation_name)
        analysis_dir = os.path.join(sim_dir, "Analyses", "Mesh", analysis_name) if sim_dir else None

        if not analysis_dir or not os.path.exists(analysis_dir):
            QtWidgets.QMessageBox.critical(self, "Error", f"Analysis directory not found: {analysis_dir}")
            return

        # Find .msh files in the analysis directory
        msh_files = []
        for root, _, files in os.walk(analysis_dir):
            for file_item in files:
                if file_item.endswith('.msh'):
                    msh_files.append(os.path.join(root, file_item))

        if not msh_files:
            QtWidgets.QMessageBox.critical(self, "Error", f"No mesh files found in analysis: {analysis_name}")
            return

        # If multiple mesh files, use the first one (or could show selection dialog)
        msh_file = msh_files[0]

        try:
            # Launch Gmsh directly with the mesh file as argument
            subprocess.Popen(["gmsh", msh_file])
            self.update_output(f"Launched Gmsh with mesh file: {msh_file}")
        except FileNotFoundError:
            QtWidgets.QMessageBox.critical(self, "Error", "Gmsh not found. Please install Gmsh and add it to PATH.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Gmsh: {str(e)}")
            self.update_output(f"Error launching Gmsh: {e}")


    # populate_subject_montages and populate_subject_fields methods removed - no longer using individual subject tabs

    

    def build_single_analysis_command(self, subject_id, simulation_name):
        """Build command to run main_analyzer.py for a single subject."""
        try:
            project_dir = self.pm.get_project_dir()
            if not project_dir:
                self.update_output("Error: Could not determine project directory")
                return None
            
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

            # Build output directory using PathManager
            sim_dir = self.pm.get_simulation_dir(subject_id, simulation_name)
            if not sim_dir:
                self.update_output(f"Error: Could not find simulation directory for {subject_id}, {simulation_name}")
                return None
            output_dir = os.path.join(sim_dir, 'Analyses', analysis_space_folder, target_info)

            if os.path.exists(output_dir) and not confirm_overwrite(self, output_dir, "analysis output directory"):
                return None
            os.makedirs(output_dir, exist_ok=True)

            app_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            main_analyzer_script_path = os.path.join(app_root_dir, 'analyzer', 'main_analyzer.py')
            if not os.path.exists(main_analyzer_script_path):
                return None

            m2m_path = self.pm.get_m2m_dir(subject_id)
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
                # For voxel analysis, automatically construct field path
                base_sim_dir = get_simulation_dir(subject_id, simulation_name)
                nifti_dir = os.path.join(base_sim_dir, 'mTI', 'niftis') if os.path.exists(os.path.join(base_sim_dir, 'mTI', 'niftis')) else os.path.join(base_sim_dir, 'TI', 'niftis')
                # Prefer grey matter files
                grey_files = [f for f in os.listdir(nifti_dir) if f.startswith('grey_') and not f.endswith('_MNI.nii.gz')] if os.path.exists(nifti_dir) else []
                if grey_files:
                    voxel_field_path = os.path.join(nifti_dir, grey_files[0])
                else:
                    # Fallback to any NIfTI file
                    nii_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii') or f.endswith('.nii.gz')] if os.path.exists(nifti_dir) else []
                    voxel_field_path = os.path.join(nifti_dir, nii_files[0]) if nii_files else None

                if not voxel_field_path or not os.path.exists(voxel_field_path):
                    self.update_output(f"Error: Field file not found for subject {subject_id} (expected in {nifti_dir})")
                    return None
                cmd.extend(['--field_path', voxel_field_path])

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
    
    def resizeEvent(self, event):
        """Handle resize events to dynamically adjust input box widths."""
        super().resizeEvent(event)
        self._update_input_widths()
    
    def _update_input_widths(self):
        """Update maximum widths of input boxes based on container size.
        
        Note: Many widgets now use QSizePolicy.Expanding, so they will automatically
        expand to fill available space. This method only adjusts widgets that still
        need dynamic width constraints.
        """
        if not hasattr(self, 'right_layout_container'):
            return
        
        # Get the width of the right container (analysis configuration panel)
        container_width = self.right_layout_container.width()
        
        # If container hasn't been sized yet, use a default calculation
        if container_width <= 0:
            # Estimate based on window size
            window_width = self.width()
            if window_width > 0:
                # Right container is roughly half the window (with margins)
                container_width = max(300, (window_width - 50) // 2)
            else:
                container_width = 400  # Default fallback
        
        # Calculate dynamic maximum widths as percentages of container width
        # These percentages allow growth while preventing overflow
        # Region input uses Preferred policy, so it will expand up to max
        if hasattr(self, 'region_input'):
            # Allow expansion up to a reasonable max based on container size
            max_region_width = max(200, min(300, int(container_width * 0.40)))
            if self.region_input.maximumWidth() != max_region_width:
                self.region_input.setMaximumWidth(max_region_width)
        
        # Coordinate inputs use Preferred policy, allow reasonable expansion
        if hasattr(self, 'coord_x') and hasattr(self, 'coord_y') and hasattr(self, 'coord_z'):
            coord_max = max(100, min(150, int(container_width * 0.15)))
            for coord_widget in [self.coord_x, self.coord_y, self.coord_z]:
                if coord_widget.maximumWidth() != coord_max:
                    coord_widget.setMaximumWidth(coord_max)
        
        # Radius input uses Preferred policy
        if hasattr(self, 'radius_input'):
            radius_max = max(100, min(150, int(container_width * 0.20)))
            if self.radius_input.maximumWidth() != radius_max:
                self.radius_input.setMaximumWidth(radius_max)
        
        # Buttons use Fixed policy - no dynamic adjustment needed
        # Atlas and Gmsh combo boxes use Expanding policy - they automatically fill space
