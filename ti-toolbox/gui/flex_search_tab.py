#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Flex Search Tab
This module provides a GUI interface for the flex-search optimization tool.
"""

import os
import json
import glob
import subprocess

from PyQt5 import QtWidgets, QtCore, QtGui

from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite, is_verbose_message, is_important_message
from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons

# Import path manager from core
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core import get_path_manager, constants as const



class FlexSearchThread(QtCore.QThread):
    """Thread to run flex-search in background to prevent GUI freezing."""
    
    # Signal to emit output text with message type
    output_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)
    
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
            self.error_signal.emit(f"Error running flex-search: {str(e)}")
    
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
                except (subprocess.CalledProcessError, OSError, ValueError):
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
        """Initialize the flex search tab."""
        super(FlexSearchTab, self).__init__(parent)
        self.parent = parent
        self.optimization_running = False
        self.optimization_process = None
        
        # Initialize data structures
        self.subjects = []
        self.eeg_nets = {}
        self.atlases = {}
        self.volume_atlases = {}
        
        # Initialize debug mode (default to False)
        self.debug_mode = False
        
        # Initialize all widgets that might be referenced before setup_ui
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.subject_list.setMaximumHeight(100)  # Reduced height (was 120)
        self.eeg_net_combo = QtWidgets.QComboBox()
        self.atlas_combo = QtWidgets.QComboBox()
        self.nonroi_atlas_combo = QtWidgets.QComboBox()
        
        # Initialize goal and postproc combo boxes
        self.goal_combo = QtWidgets.QComboBox()
        self.goal_combo.addItem("mean (maximize field in target ROI)", "mean")
        self.goal_combo.addItem("max (maximize peak field in target ROI)", "max")
        self.goal_combo.addItem("focality (maximize field in target ROI while minimizing field elsewhere)", "focality")
        
        self.postproc_combo = QtWidgets.QComboBox()
        self.postproc_combo.addItem("max_TI (maximum TI field)", "max_TI")
        self.postproc_combo.addItem("dir_TI_normal (TI field normal to surface)", "dir_TI_normal")
        self.postproc_combo.addItem("dir_TI_tangential (TI field tangential to surface)", "dir_TI_tangential")
        
        # Initialize buttons that might be referenced
        self.refresh_subjects_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_subjects_btn.setMaximumWidth(100)
        
        self.select_all_subjects_btn = QtWidgets.QPushButton("Select All")
        self.select_all_subjects_btn.setMaximumWidth(100)
        
        self.clear_subjects_btn = QtWidgets.QPushButton("Clear")
        self.clear_subjects_btn.setMaximumWidth(100)
        
        self.refresh_eeg_nets_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_eeg_nets_btn.setMaximumWidth(100)
        
        self.refresh_atlases_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_atlases_btn.setMaximumWidth(100)
        
        # Initialize labels
        self.subject_label = QtWidgets.QLabel("Subjects:")
        self.goal_label = QtWidgets.QLabel("Optimization Goal:")
        self.postproc_label = QtWidgets.QLabel("Post-processing Method:")
        self.roi_method_label = QtWidgets.QLabel("ROI Definition Method:")
        self.current_label = QtWidgets.QLabel("Electrode Current (mA):")
        self.electrode_shape_label = QtWidgets.QLabel("Electrode Shape:")
        self.dimensions_label = QtWidgets.QLabel("Dimensions (mm, x,y):")
        self.thickness_label = QtWidgets.QLabel("Thickness (mm):")
        self.eeg_net_label = QtWidgets.QLabel("EEG Net Template:")
        self.roi_hemi_label = QtWidgets.QLabel("Hemisphere:")
        self.nonroi_hemi_label = QtWidgets.QLabel("Hemisphere:")
        self.max_iterations_label = QtWidgets.QLabel("Max Optimization Iterations:")
        self.population_size_label = QtWidgets.QLabel("Population Size:")
        self.cpus_label = QtWidgets.QLabel("Number of CPUs:")
        self.threshold_label = QtWidgets.QLabel("Threshold(s) for E-field (V/m):")
        self.nonroi_method_label = QtWidgets.QLabel("Non-ROI Definition Method:")
        self.atlas_label = QtWidgets.QLabel("Atlas:")
        self.label_value_label = QtWidgets.QLabel("Region Label Value:")
        self.roi_coords_label = QtWidgets.QLabel("ROI Center RAS Coordinates (mm):")
        self.roi_radius_label = QtWidgets.QLabel("ROI Radius (mm):")
        self.nonroi_coords_label = QtWidgets.QLabel("Non-ROI Center (x,y,z,mm):")
        self.nonroi_radius_label = QtWidgets.QLabel("Non-ROI Radius (mm):")
        self.nonroi_atlas_label = QtWidgets.QLabel("Non-ROI Atlas:")
        self.nonroi_label_value_label = QtWidgets.QLabel("Non-ROI Label Value:")

        # Initialize checkboxes

        self.run_mapped_simulation_checkbox = QtWidgets.QCheckBox("Run simulation with mapped electrodes")
        self.run_mapped_simulation_checkbox.setChecked(False)
        
        self.run_final_electrode_simulation_checkbox = QtWidgets.QCheckBox("Run final electrode simulation")
        self.run_final_electrode_simulation_checkbox.setChecked(False)
        
        # Initialize radio buttons
        self.roi_method_spherical = QtWidgets.QRadioButton("Spherical (coordinates and radius)")
        self.roi_method_cortical = QtWidgets.QRadioButton("Cortical")
        self.roi_method_subcortical = QtWidgets.QRadioButton("Subcortical")
        self.roi_method_spherical.setChecked(True)

        # Initialize coordinate space radio buttons
        self.roi_space_subject = QtWidgets.QRadioButton("Subject Space")
        self.roi_space_mni = QtWidgets.QRadioButton("MNI Space")
        self.roi_space_subject.setChecked(True)  # Default to subject space
        
        # Initialize spinboxes and line edits
        
        self.current_input = QtWidgets.QDoubleSpinBox()
        self.current_input.setRange(0.1, 100); self.current_input.setValue(1.0); self.current_input.setDecimals(1)
        
        # Initialize Freeview button for spherical ROI
        self.view_t1_btn = QtWidgets.QPushButton("View T1 in Freeview")
        self.view_t1_btn.setMaximumWidth(150)
        self.view_t1_btn.setToolTip("Open subject's T1 scan in Freeview to find RAS coordinates")
        
        # Multi-start optimization control
        self.n_multistart_input = QtWidgets.QSpinBox()
        self.n_multistart_input.setRange(1, 20); self.n_multistart_input.setValue(1)
        self.n_multistart_input.setToolTip("Number of optimization runs to perform. Higher values increase chances of finding global optimum but take longer.")
        self.n_multistart_label = QtWidgets.QLabel("Number of Optimization Runs:")

        self.max_iterations_input = QtWidgets.QSpinBox()
        self.max_iterations_input.setRange(50, 2000); self.max_iterations_input.setValue(500)
        self.max_iterations_input.setToolTip("Maximum number of optimization iterations.")

        self.population_size_input = QtWidgets.QSpinBox()
        self.population_size_input.setRange(4, 100); self.population_size_input.setValue(13)
        self.population_size_input.setToolTip("Number of individuals in the population for optimization.")

        self.cpus_input = QtWidgets.QSpinBox()
        self.cpus_input.setRange(1, os.cpu_count() or 16)
        self.cpus_input.setValue(1)
        self.cpus_input.setToolTip("Number of CPU cores to use for parallel processing during optimization.")

        # Differential evolution optimizer parameters
        self.tolerance_input = QtWidgets.QDoubleSpinBox()
        self.tolerance_input.setRange(0.0001, 1.0); self.tolerance_input.setValue(0.1)
        self.tolerance_input.setDecimals(4); self.tolerance_input.setSingleStep(0.01)
        self.tolerance_input.setToolTip("Convergence tolerance for differential evolution optimizer (default: 0.1)")
        self.tolerance_label = QtWidgets.QLabel("Tolerance:")

        self.mutation_min_input = QtWidgets.QDoubleSpinBox()
        self.mutation_min_input.setRange(0.0, 2.0); self.mutation_min_input.setValue(0.01)
        self.mutation_min_input.setDecimals(3); self.mutation_min_input.setSingleStep(0.01)
        self.mutation_min_input.setToolTip("Minimum mutation factor (default: 0.01)")

        self.mutation_max_input = QtWidgets.QDoubleSpinBox()
        self.mutation_max_input.setRange(0.0, 2.0); self.mutation_max_input.setValue(0.5)
        self.mutation_max_input.setDecimals(3); self.mutation_max_input.setSingleStep(0.01)
        self.mutation_max_input.setToolTip("Maximum mutation factor (default: 0.5)")
        self.mutation_label = QtWidgets.QLabel("Mutation (min, max):")

        self.recombination_input = QtWidgets.QDoubleSpinBox()
        self.recombination_input.setRange(0.0, 1.0); self.recombination_input.setValue(0.7)
        self.recombination_input.setDecimals(2); self.recombination_input.setSingleStep(0.05)
        self.recombination_input.setToolTip("Recombination probability for differential evolution (default: 0.7)")
        self.recombination_label = QtWidgets.QLabel("Recombination:")

        # Detailed results checkbox
        self.detailed_results_checkbox = QtWidgets.QCheckBox("Enable detailed results output")
        self.detailed_results_checkbox.setChecked(False)
        self.detailed_results_checkbox.setToolTip("Enable detailed results output (creates additional visualization and debug files)")

        # Visualize valid skin region checkbox
        self.visualize_skin_checkbox = QtWidgets.QCheckBox("Visualize valid skin region")
        self.visualize_skin_checkbox.setChecked(False)
        self.visualize_skin_checkbox.setToolTip("Create 2D visualizations of valid skin region for electrode placement (requires detailed results)")
        self.visualize_skin_checkbox.setEnabled(False)  # Initially disabled until detailed results is checked

        # EEG net selection for skin visualization
        self.skin_net_combo = QtWidgets.QComboBox()
        self.skin_net_combo.setEnabled(False)  # Initially disabled until skin visualization is checked
        self.skin_net_combo.setToolTip("Select EEG net to visualize electrode positions on skin surface")
        self.skin_net_label = QtWidgets.QLabel("Visualization EEG Net:")
        
        self.roi_x_input = QtWidgets.QDoubleSpinBox(); self.roi_x_input.setRange(-150, 150); self.roi_x_input.setValue(0); self.roi_x_input.setDecimals(2)
        self.roi_y_input = QtWidgets.QDoubleSpinBox(); self.roi_y_input.setRange(-150, 150); self.roi_y_input.setValue(0); self.roi_y_input.setDecimals(2)
        self.roi_z_input = QtWidgets.QDoubleSpinBox(); self.roi_z_input.setRange(-150, 150); self.roi_z_input.setValue(0); self.roi_z_input.setDecimals(2)
        self.roi_radius_input = QtWidgets.QDoubleSpinBox(); self.roi_radius_input.setRange(1, 50); self.roi_radius_input.setValue(10); self.roi_radius_input.setDecimals(2)

        # Electrode shape, dimensions, and thickness
        self.electrode_shape_rect = QtWidgets.QRadioButton("Rectangle")
        self.electrode_shape_rect.setProperty("value", "rect")
        self.electrode_shape_ellipse = QtWidgets.QRadioButton("Ellipse")
        self.electrode_shape_ellipse.setProperty("value", "ellipse")
        self.electrode_shape_ellipse.setChecked(True)  # Set default to Ellipse
        self.dimensions_input = QtWidgets.QLineEdit()
        self.dimensions_input.setPlaceholderText("8,8")
        self.dimensions_input.setText("8,8")  # Set default to 8,8
        self.thickness_input = QtWidgets.QLineEdit()
        self.thickness_input.setPlaceholderText("4")
        self.thickness_input.setText("4")  # Set default to 4mm
        
        self.label_value_input = QtWidgets.QSpinBox(); self.label_value_input.setRange(1, 10000); self.label_value_input.setValue(1)
        
        # Initialize stacked widgets
        self.roi_stacked_widget = QtWidgets.QStackedWidget()
        self.nonroi_stacked = QtWidgets.QStackedWidget()

        # Initialize container widget for EEG net controls (used in _update_mapping_options)
        self.eeg_net_widget = QtWidgets.QWidget()
        
        # Initialize focality components
        self.focality_group = QtWidgets.QGroupBox("Focality Options")
        self.focality_group.setVisible(False)
        
        self.threshold_input = QtWidgets.QLineEdit()
        self.threshold_input.setPlaceholderText("e.g. 0.2 or 0.2,0.5")
        
        # Adaptive focality controls
        self.adaptive_focality_checkbox = QtWidgets.QCheckBox("Use Adaptive Thresholds")
        self.adaptive_focality_checkbox.setToolTip("Automatically determine thresholds based on achievable intensity from mean optimization")
        
        self.nonroi_percentage_input = QtWidgets.QDoubleSpinBox()
        self.nonroi_percentage_input.setRange(1, 99)
        self.nonroi_percentage_input.setValue(20)
        self.nonroi_percentage_input.setSuffix("%")
        self.nonroi_percentage_input.setToolTip("Percentage of achievable intensity for non-ROI threshold")
        
        self.roi_percentage_input = QtWidgets.QDoubleSpinBox()
        self.roi_percentage_input.setRange(1, 99)
        self.roi_percentage_input.setValue(80)
        self.roi_percentage_input.setSuffix("%")
        self.roi_percentage_input.setToolTip("Percentage of achievable intensity for ROI threshold")
        
        self.nonroi_method_combo = QtWidgets.QComboBox()
        self.nonroi_method_combo.addItem("Everything Else (default)", "everything_else")
        self.nonroi_method_combo.addItem("Specific Region", "specific")
        
        # Non-ROI inputs (spherical)
        self.nonroi_x_input = QtWidgets.QDoubleSpinBox(); self.nonroi_x_input.setRange(-150,150); self.nonroi_x_input.setDecimals(2)
        self.nonroi_y_input = QtWidgets.QDoubleSpinBox(); self.nonroi_y_input.setRange(-150,150); self.nonroi_y_input.setDecimals(2)
        self.nonroi_z_input = QtWidgets.QDoubleSpinBox(); self.nonroi_z_input.setRange(-150,150); self.nonroi_z_input.setDecimals(2)
        self.nonroi_radius_input = QtWidgets.QDoubleSpinBox(); self.nonroi_radius_input.setRange(1,50); self.nonroi_radius_input.setDecimals(2)
        
        # Non-ROI inputs (atlas)
        self.nonroi_hemi_combo = QtWidgets.QComboBox(); self.nonroi_hemi_combo.addItems(["Left (lh)", "Right (rh)"])
        self.nonroi_label_input = QtWidgets.QSpinBox(); self.nonroi_label_input.setRange(1,10000)
        self.list_nonroi_regions_btn = QtWidgets.QPushButton("List Regions")
        self.list_nonroi_regions_btn.setMaximumWidth(120)
        
        # Non-ROI inputs (volume)
        self.nonroi_volume_atlas_combo = QtWidgets.QComboBox()
        self.nonroi_volume_label_input = QtWidgets.QSpinBox(); self.nonroi_volume_label_input.setRange(1,10000)
        self.list_nonroi_volume_regions_btn = QtWidgets.QPushButton("List Regions")
        self.list_nonroi_volume_regions_btn.setMaximumWidth(120)
        
        # ROI hemisphere combo and list regions button (for cortical ROI)
        self.roi_hemi_combo = QtWidgets.QComboBox(); self.roi_hemi_combo.addItems(["Left (lh)", "Right (rh)"])
        self.list_roi_regions_btn = QtWidgets.QPushButton("List Regions")
        self.list_roi_regions_btn.setMaximumWidth(120)

        # Subcortical volume controls
        self.volume_atlas_combo = QtWidgets.QComboBox()
        self.refresh_volume_atlases_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_volume_atlases_btn.setMaximumWidth(100)
        self.volume_label_value_input = QtWidgets.QSpinBox(); self.volume_label_value_input.setRange(1, 10000); self.volume_label_value_input.setValue(10)
        self.volume_label_value_input.setToolTip("Common values: 10=Left-Thalamus, 49=Right-Thalamus, 17=Left-Hippocampus, 53=Right-Hippocampus")
        self.list_volume_regions_btn = QtWidgets.QPushButton("List Regions")
        self.list_volume_regions_btn.setMaximumWidth(120)
        
        # Labels for subcortical controls
        self.volume_atlas_label = QtWidgets.QLabel("Volume Atlas:")
        self.volume_label_value_label = QtWidgets.QLabel("Region Label Value:")

        # Set up the UI
        self.setup_ui()
        
        # Connect signals after UI setup (critical widgets must exist)
        self.refresh_subjects_btn.clicked.connect(self.find_available_subjects)
        self.select_all_subjects_btn.clicked.connect(self.select_all_subjects)
        self.clear_subjects_btn.clicked.connect(self.clear_subject_selection)
        self.refresh_eeg_nets_btn.clicked.connect(self.find_available_eeg_nets)
        self.refresh_atlases_btn.clicked.connect(self.find_available_atlases)
        self.refresh_volume_atlases_btn.clicked.connect(self.find_available_volume_atlases)
        self.list_roi_regions_btn.clicked.connect(self._list_roi_regions)
        self.list_nonroi_regions_btn.clicked.connect(self._list_nonroi_regions)
        self.list_volume_regions_btn.clicked.connect(self._list_volume_regions)
        self.list_nonroi_volume_regions_btn.clicked.connect(self._list_nonroi_volume_regions)

        self.goal_combo.currentIndexChanged.connect(self._update_focality_visibility)
        self.adaptive_focality_checkbox.toggled.connect(self._update_adaptive_focality_controls)
        self.run_mapped_simulation_checkbox.toggled.connect(self._update_mapping_options)
        self.subject_list.itemSelectionChanged.connect(self.on_subject_changed)
        self.detailed_results_checkbox.toggled.connect(self._on_detailed_results_toggled)
        self.visualize_skin_checkbox.toggled.connect(self._on_visualize_skin_toggled)
        self.nonroi_method_combo.currentIndexChanged.connect(self._update_nonroi_stacked)
        self.roi_method_spherical.toggled.connect(self.update_roi_method)
        self.roi_method_cortical.toggled.connect(self.update_roi_method)
        self.roi_method_subcortical.toggled.connect(self.update_roi_method)
        self.roi_method_spherical.toggled.connect(self._update_nonroi_stacked)
        self.roi_method_cortical.toggled.connect(self._update_nonroi_stacked)
        self.roi_method_subcortical.toggled.connect(self._update_nonroi_stacked)
        self.roi_space_subject.toggled.connect(self._update_coordinate_space_labels)
        self.roi_space_mni.toggled.connect(self._update_coordinate_space_labels)
        self.view_t1_btn.clicked.connect(self.load_t1_in_freeview)
        
        # Find available subjects (which will trigger finding EEG nets and atlases)
        self.find_available_subjects()

    def setup_ui(self):
        """Set up the user interface for the flex-search tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(8, 8, 8, 8)  # Reduce margins from default ~11 to 8
        
        top_row_layout = QtWidgets.QHBoxLayout()
        top_row_layout.setSpacing(6)  # Reduce spacing between columns from default ~10 to 6

        # Left column: Basic Parameters (expanded)
        basic_params_group = QtWidgets.QGroupBox("Basic Parameters")
        basic_params_layout = QtWidgets.QFormLayout(basic_params_group)
        
        subject_controls_widget = QtWidgets.QWidget()
        subject_controls_inner_layout = QtWidgets.QHBoxLayout(subject_controls_widget)
        subject_controls_inner_layout.addWidget(self.subject_list)
        
        # Create vertical layout for buttons
        subject_buttons_widget = QtWidgets.QWidget()
        subject_buttons_layout = QtWidgets.QVBoxLayout(subject_buttons_widget)
        subject_buttons_layout.setContentsMargins(0, 0, 0, 0)
        subject_buttons_layout.setSpacing(2)
        subject_buttons_layout.addWidget(self.refresh_subjects_btn)
        subject_buttons_layout.addWidget(self.select_all_subjects_btn)
        subject_buttons_layout.addWidget(self.clear_subjects_btn)
        
        subject_controls_inner_layout.addWidget(subject_buttons_widget)
        subject_controls_inner_layout.addStretch()
        basic_params_layout.addRow(self.subject_label, subject_controls_widget)
        
        self.goal_combo.setMaximumWidth(320)
        basic_params_layout.addRow(self.goal_label, self.goal_combo)
        
        self.postproc_combo.setMaximumWidth(320)
        basic_params_layout.addRow(self.postproc_label, self.postproc_combo)

        top_row_layout.addWidget(basic_params_group, 1)

        # Right column: Automatic Simulations (top) + Electrode Parameters (bottom)
        right_column_widget = QtWidgets.QWidget()
        right_column_layout = QtWidgets.QVBoxLayout(right_column_widget)
        right_column_layout.setContentsMargins(0, 0, 0, 0)

        # Automatic Simulations Options (formerly Electrode Mapping)
        self.mapping_group = QtWidgets.QGroupBox("Automatic Simulations (Optional)")
        self.mapping_group.setMaximumHeight(140)  # Increased height to accommodate both checkboxes
        mapping_layout = QtWidgets.QFormLayout(self.mapping_group)
        mapping_layout.setVerticalSpacing(2)  # Minimal vertical spacing between rows
        mapping_layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins
        mapping_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)  # Prevent fields from growing

        # Add final electrode simulation checkbox
        mapping_layout.addRow(self.run_final_electrode_simulation_checkbox)

        # Add mapped electrodes simulation checkbox
        mapping_layout.addRow(self.run_mapped_simulation_checkbox)

        # EEG net selection (only visible when run_mapped_simulation is checked)
        eeg_net_controls_inner_layout = QtWidgets.QHBoxLayout()
        eeg_net_controls_inner_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        self.eeg_net_combo.setFixedWidth(195)  # Force width to be 2.5x larger
        eeg_net_controls_inner_layout.addWidget(self.eeg_net_combo)
        eeg_net_controls_inner_layout.addStretch()
        self.eeg_net_widget.setLayout(eeg_net_controls_inner_layout)
        self.eeg_net_widget.setVisible(False)
        self.eeg_net_label.setVisible(False)
        mapping_layout.addRow(self.eeg_net_label, self.eeg_net_widget)

        right_column_layout.addWidget(self.mapping_group)
        
        # Electrode Parameters
        self.electrode_params_group = QtWidgets.QGroupBox("Electrode Parameters")
        electrode_params_layout = QtWidgets.QFormLayout(self.electrode_params_group)
        electrode_params_layout.addRow(self.current_label, self.current_input)

        # Electrode shape
        shape_layout = QtWidgets.QHBoxLayout()
        shape_layout.addWidget(self.electrode_shape_rect)
        shape_layout.addWidget(self.electrode_shape_ellipse)
        shape_layout.addStretch()
        electrode_params_layout.addRow(self.electrode_shape_label, shape_layout)

        # Dimensions and thickness
        electrode_params_layout.addRow(self.dimensions_label, self.dimensions_input)
        electrode_params_layout.addRow(self.thickness_label, self.thickness_input)

        right_column_layout.addWidget(self.electrode_params_group)
        
        top_row_layout.addWidget(right_column_widget, 1)
        
        scroll_layout.addLayout(top_row_layout)

        self.roi_method_group = QtWidgets.QGroupBox("ROI Definition")
        roi_method_layout_main = QtWidgets.QVBoxLayout(self.roi_method_group)
        roi_method_layout_main.setSpacing(5)  # Reduce vertical spacing
        roi_method_layout_main.setContentsMargins(10, 10, 10, 10)  # Reduce margins
        
        # Create horizontal layout for label and radio buttons on same line
        roi_method_header_container = QtWidgets.QWidget()
        roi_method_header_layout = QtWidgets.QHBoxLayout(roi_method_header_container)
        roi_method_header_layout.setContentsMargins(0, 0, 0, 0)
        roi_method_header_layout.addWidget(self.roi_method_label)
        roi_method_header_layout.addWidget(self.roi_method_spherical)
        roi_method_header_layout.addWidget(self.roi_method_cortical)
        roi_method_header_layout.addWidget(self.roi_method_subcortical)
        roi_method_header_layout.addStretch()
        
        roi_method_layout_main.addWidget(roi_method_header_container)
        
        # Spherical ROI inputs
        self.spherical_roi_widget = QtWidgets.QWidget()
        spherical_roi_layout = QtWidgets.QFormLayout(self.spherical_roi_widget)
        spherical_roi_layout.setVerticalSpacing(3)  # Reduce vertical spacing between form rows
        spherical_roi_layout.setContentsMargins(0, 5, 0, 5)  # Reduce top/bottom margins
        
        # Add coordinate space selection
        space_selection_widget = QtWidgets.QWidget()
        space_selection_layout = QtWidgets.QHBoxLayout(space_selection_widget)
        space_selection_layout.setContentsMargins(0, 0, 0, 0)
        space_selection_layout.addWidget(QtWidgets.QLabel("Coordinate Space:"))
        space_selection_layout.addWidget(self.roi_space_subject)
        space_selection_layout.addWidget(self.roi_space_mni)
        space_selection_layout.addStretch()
        spherical_roi_layout.addRow(space_selection_widget)

        # Add info label for MNI coordinates (initially hidden)
        self.mni_info_label = QtWidgets.QLabel()
        self.mni_info_label.setText("Coordinates will be treated as MNI space and transformed to each subject's native space.")
        self.mni_info_label.setStyleSheet("background-color: #E3F2FD; color: #1976D2; padding: 8px; border-radius: 4px; font-size: 11px;")
        self.mni_info_label.setWordWrap(True)
        self.mni_info_label.setVisible(False)
        spherical_roi_layout.addRow(self.mni_info_label)
        
        roi_coords_controls_widget = QtWidgets.QWidget()
        roi_coords_controls_layout = QtWidgets.QHBoxLayout(roi_coords_controls_widget)
        roi_coords_controls_layout.addWidget(QtWidgets.QLabel("X:"))
        roi_coords_controls_layout.addWidget(self.roi_x_input)
        roi_coords_controls_layout.addWidget(QtWidgets.QLabel("Y:"))
        roi_coords_controls_layout.addWidget(self.roi_y_input)
        roi_coords_controls_layout.addWidget(QtWidgets.QLabel("Z:"))
        roi_coords_controls_layout.addWidget(self.roi_z_input)
        roi_coords_controls_layout.addWidget(self.view_t1_btn)
        roi_coords_controls_layout.addStretch()
        spherical_roi_layout.addRow(self.roi_coords_label, roi_coords_controls_widget)
        spherical_roi_layout.addRow(self.roi_radius_label, self.roi_radius_input)
        self.roi_stacked_widget.addWidget(self.spherical_roi_widget)
        
        # Cortical ROI inputs
        self.cortical_roi_widget = QtWidgets.QWidget()
        cortical_roi_layout = QtWidgets.QFormLayout(self.cortical_roi_widget)
        cortical_roi_layout.setVerticalSpacing(3)  # Reduce vertical spacing
        cortical_roi_layout.setContentsMargins(0, 5, 0, 5)  # Reduce margins
        
        atlas_controls_widget = QtWidgets.QWidget()
        atlas_controls_inner_layout = QtWidgets.QHBoxLayout(atlas_controls_widget)
        self.atlas_combo.setMaximumWidth(320)
        atlas_controls_inner_layout.addWidget(self.atlas_combo)
        atlas_controls_inner_layout.addWidget(self.roi_hemi_label)
        atlas_controls_inner_layout.addWidget(self.roi_hemi_combo)
        atlas_controls_inner_layout.addWidget(self.refresh_atlases_btn)
        atlas_controls_inner_layout.addWidget(self.list_roi_regions_btn)
        atlas_controls_inner_layout.addStretch()
        cortical_roi_layout.addRow(self.atlas_label, atlas_controls_widget)
        cortical_roi_layout.addRow(self.label_value_label, self.label_value_input)
        self.roi_stacked_widget.addWidget(self.cortical_roi_widget)
        
        # Subcortical ROI inputs
        self.subcortical_roi_widget = QtWidgets.QWidget()
        subcortical_roi_layout = QtWidgets.QFormLayout(self.subcortical_roi_widget)
        subcortical_roi_layout.setVerticalSpacing(3)  # Reduce vertical spacing
        subcortical_roi_layout.setContentsMargins(0, 5, 0, 5)  # Reduce margins
        
        volume_controls_widget = QtWidgets.QWidget()
        volume_controls_inner_layout = QtWidgets.QHBoxLayout(volume_controls_widget)
        self.volume_atlas_combo.setMaximumWidth(320)
        volume_controls_inner_layout.addWidget(self.volume_atlas_combo)
        volume_controls_inner_layout.addWidget(self.refresh_volume_atlases_btn)
        volume_controls_inner_layout.addWidget(self.list_volume_regions_btn)
        volume_controls_inner_layout.addStretch()
        subcortical_roi_layout.addRow(self.volume_atlas_label, volume_controls_widget)
        subcortical_roi_layout.addRow(self.volume_label_value_label, self.volume_label_value_input)
        self.roi_stacked_widget.addWidget(self.subcortical_roi_widget)
        
        roi_method_layout_main.addWidget(self.roi_stacked_widget)
        scroll_layout.addWidget(self.roi_method_group)

        # Focality Options group
        focality_layout = QtWidgets.QFormLayout(self.focality_group)
        
        # Adaptive focality section
        focality_layout.addRow(self.adaptive_focality_checkbox)
        
        # Adaptive help text
        adaptive_help = QtWidgets.QLabel("Automatically determines thresholds by first running mean optimization to find achievable intensity.")
        adaptive_help.setStyleSheet("font-size: 10px; color: gray;")
        adaptive_help.setWordWrap(True)
        focality_layout.addRow(adaptive_help)
        
        # Adaptive percentage controls
        adaptive_percentages_widget = QtWidgets.QWidget()
        adaptive_percentages_layout = QtWidgets.QHBoxLayout(adaptive_percentages_widget)
        adaptive_percentages_layout.addWidget(QtWidgets.QLabel("Non-ROI:"))
        adaptive_percentages_layout.addWidget(self.nonroi_percentage_input)
        adaptive_percentages_layout.addWidget(QtWidgets.QLabel("ROI:"))
        adaptive_percentages_layout.addWidget(self.roi_percentage_input)
        adaptive_percentages_layout.addStretch()
        focality_layout.addRow(QtWidgets.QLabel("Adaptive Percentages:"), adaptive_percentages_widget)
        
        # Manual threshold input
        focality_layout.addRow(self.threshold_label, self.threshold_input)
        threshold_help = QtWidgets.QLabel("Single value: E-field < value in non-ROI, > value in ROI. Two values: non-ROI max, ROI min.")
        threshold_help.setStyleSheet("font-size: 10px; color: gray;")
        focality_layout.addRow(threshold_help)
        focality_layout.addRow(self.nonroi_method_label, self.nonroi_method_combo)

        # Non-ROI Spherical
        self.nonroi_sph_widget = QtWidgets.QWidget()
        nonroi_sph_layout = QtWidgets.QFormLayout(self.nonroi_sph_widget)
        nonroi_coords_controls_widget = QtWidgets.QWidget()
        nonroi_coords_controls_layout = QtWidgets.QHBoxLayout(nonroi_coords_controls_widget)
        nonroi_coords_controls_layout.addWidget(QtWidgets.QLabel("X:")); nonroi_coords_controls_layout.addWidget(self.nonroi_x_input)
        nonroi_coords_controls_layout.addWidget(QtWidgets.QLabel("Y:")); nonroi_coords_controls_layout.addWidget(self.nonroi_y_input)
        nonroi_coords_controls_layout.addWidget(QtWidgets.QLabel("Z:")); nonroi_coords_controls_layout.addWidget(self.nonroi_z_input)
        nonroi_sph_layout.addRow(self.nonroi_coords_label, nonroi_coords_controls_widget)
        nonroi_sph_layout.addRow(self.nonroi_radius_label, self.nonroi_radius_input)
        self.nonroi_stacked.addWidget(self.nonroi_sph_widget)

        # Non-ROI Atlas
        self.nonroi_atlas_widget = QtWidgets.QWidget()
        nonroi_atlas_layout = QtWidgets.QFormLayout(self.nonroi_atlas_widget)
        nonroi_atlas_controls_widget = QtWidgets.QWidget()
        nonroi_atlas_controls_inner_layout = QtWidgets.QHBoxLayout(nonroi_atlas_controls_widget)
        self.nonroi_atlas_combo.setMaximumWidth(320)
        nonroi_atlas_controls_inner_layout.addWidget(self.nonroi_atlas_combo)
        nonroi_atlas_controls_inner_layout.addWidget(self.nonroi_hemi_label)
        nonroi_atlas_controls_inner_layout.addWidget(self.nonroi_hemi_combo)
        nonroi_atlas_controls_inner_layout.addWidget(self.list_nonroi_regions_btn)
        nonroi_atlas_controls_inner_layout.addStretch()
        nonroi_atlas_layout.addRow(self.nonroi_atlas_label, nonroi_atlas_controls_widget)
        nonroi_atlas_layout.addRow(self.nonroi_label_value_label, self.nonroi_label_input)
        self.nonroi_stacked.addWidget(self.nonroi_atlas_widget)

        # Non-ROI Volume
        self.nonroi_volume_widget = QtWidgets.QWidget()
        nonroi_volume_layout = QtWidgets.QFormLayout(self.nonroi_volume_widget)
        nonroi_volume_controls_widget = QtWidgets.QWidget()
        nonroi_volume_controls_layout = QtWidgets.QHBoxLayout(nonroi_volume_controls_widget)
        self.nonroi_volume_atlas_combo.setMaximumWidth(320)
        nonroi_volume_controls_layout.addWidget(self.nonroi_volume_atlas_combo)
        nonroi_volume_controls_layout.addWidget(self.list_nonroi_volume_regions_btn)
        nonroi_volume_controls_layout.addStretch()
        nonroi_volume_layout.addRow(QtWidgets.QLabel("Non-ROI Volume Atlas:"), nonroi_volume_controls_widget)
        nonroi_volume_layout.addRow(QtWidgets.QLabel("Non-ROI Volume Label:"), self.nonroi_volume_label_input)
        self.nonroi_stacked.addWidget(self.nonroi_volume_widget)
        
        focality_layout.addRow(QtWidgets.QLabel("Non-ROI Region (if 'Specific'):"), self.nonroi_stacked)
        scroll_layout.addWidget(self.focality_group)

        self.stability_group = QtWidgets.QGroupBox("Hyper Parameters")
        stability_layout = QtWidgets.QGridLayout(self.stability_group)

        # Left column (General parameters)
        row = 0
        stability_layout.addWidget(self.n_multistart_label, row, 0)
        stability_layout.addWidget(self.n_multistart_input, row, 1)

        row += 1
        stability_layout.addWidget(self.max_iterations_label, row, 0)
        stability_layout.addWidget(self.max_iterations_input, row, 1)

        row += 1
        stability_layout.addWidget(self.population_size_label, row, 0)
        stability_layout.addWidget(self.population_size_input, row, 1)

        row += 1
        stability_layout.addWidget(self.cpus_label, row, 0)
        stability_layout.addWidget(self.cpus_input, row, 1)

        # Right column (Differential evolution parameters)
        row = 0
        stability_layout.addWidget(self.tolerance_label, row, 2)
        stability_layout.addWidget(self.tolerance_input, row, 3)

        row += 1
        stability_layout.addWidget(self.mutation_label, row, 2)
        # Create horizontal layout for mutation min/max inputs
        mutation_layout = QtWidgets.QHBoxLayout()
        mutation_layout.addWidget(self.mutation_min_input)
        mutation_layout.addWidget(QtWidgets.QLabel("to"))
        mutation_layout.addWidget(self.mutation_max_input)
        mutation_layout.setContentsMargins(0, 0, 0, 0)
        mutation_widget = QtWidgets.QWidget()
        mutation_widget.setLayout(mutation_layout)
        stability_layout.addWidget(mutation_widget, row, 3)

        row += 1
        stability_layout.addWidget(self.recombination_label, row, 2)
        stability_layout.addWidget(self.recombination_input, row, 3)

        # Detailed results checkbox in right column below recombination
        row += 1
        stability_layout.addWidget(self.detailed_results_checkbox, row, 2, 1, 2)

        # Visualize skin region checkbox
        row += 1
        stability_layout.addWidget(self.visualize_skin_checkbox, row, 2, 1, 2)

        # Skin net selection (only visible when skin visualization is enabled)
        row += 1
        stability_layout.addWidget(self.skin_net_label, row, 2)
        stability_layout.addWidget(self.skin_net_combo, row, 3)

        # Add some spacing between columns
        stability_layout.setColumnMinimumWidth(1, 120)
        stability_layout.setColumnMinimumWidth(3, 120)
        stability_layout.setColumnStretch(1, 1)
        stability_layout.setColumnStretch(3, 1)
        stability_layout.setHorizontalSpacing(20)

        scroll_layout.addWidget(self.stability_group)

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(self, run_text="Run Optimization", stop_text="Stop Optimization")
        self.action_buttons.connect_run(self.run_optimization)
        self.action_buttons.connect_stop(self.stop_optimization)
        
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
        self.output_text = self.console_widget.get_console_widget()
        
        # Initialize ROI method display and focality visibility
        self.update_roi_method(self.roi_method_spherical.isChecked())
        self._update_focality_visibility()
        self._update_nonroi_stacked()

    def find_available_subjects(self):
        self.subjects = []
        self.subject_list.clear()
        self.output_text.clear()
        
        # Use path_manager to find subjects
        pm = get_path_manager()
        project_dir = pm.get_project_dir()
        
        if not project_dir:
            self.output_text.append("Error: Could not detect project directory")
            self.output_text.append("Please ensure PROJECT_DIR or PROJECT_DIR_NAME environment variable is set")
            return
        
        # Set PROJECT_DIR for other components that might need it
        os.environ['PROJECT_DIR'] = project_dir
        
        # Only show subject discovery messages in debug mode
        if self.debug_mode:
            self.output_text.append(f"Looking for subjects in: {project_dir}")
        
        # Get subjects using path_manager
        self.subjects = pm.list_subjects()
        for subject_id in self.subjects:
            self.subject_list.addItem(subject_id)
                
        # Console output: subjects found (only in debug mode)
        if self.debug_mode:
            self.output_text.append("\n=== Subjects Found ===")
            if not self.subjects:
                self.output_text.append("No subjects found.")
            else:
                for subject_id in self.subjects:
                    self.output_text.append(f"- {subject_id}")
                
            self.output_text.append("")
        
        # Trigger EEG net refresh for the first subject
        if self.subjects:
            self.find_available_eeg_nets()
            self.find_available_atlases()
            self.find_available_volume_atlases()
    
    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        for i in range(self.subject_list.count()):
            item = self.subject_list.item(i)
            item.setSelected(True)
    
    def clear_subject_selection(self):
        """Clear all subject selections."""
        self.subject_list.clearSelection()
    
    def find_available_eeg_nets(self):
        """Find available EEG net templates for the selected subject."""
        if not self.subjects:
            return
        
        self.eeg_nets = {}
        self.eeg_net_combo.clear()
        self.skin_net_combo.clear()
        
        # Get the first selected subject (for consistency when multiple are selected)
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            return
        
        subject_id = selected_items[0].text()
        
        # Base directory where subjects are located
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        
        # EEG positions directory in new BIDS structure
        eeg_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                              f'm2m_{subject_id}', 'eeg_positions')
        
        try:
            if os.path.isdir(eeg_dir):
                # Find all CSV files in the directory
                for eeg_file in glob.glob(os.path.join(eeg_dir, '*.csv')):
                    net_name = os.path.splitext(os.path.basename(eeg_file))[0]
                    self.eeg_nets[net_name] = eeg_file
                    self.eeg_net_combo.addItem(net_name)
                    self.skin_net_combo.addItem(net_name)

                # Set default for skin visualization combo
                if "GSN-HydroCel-185" in self.eeg_nets:
                    # If GSN-HydroCel-185 exists, select it as default
                    index = self.skin_net_combo.findText("GSN-HydroCel-185")
                    if index >= 0:
                        self.skin_net_combo.setCurrentIndex(index)
                elif self.eeg_nets:
                    # If GSN-HydroCel-185 doesn't exist but other nets do, select first one
                    self.skin_net_combo.setCurrentIndex(0)
                else:
                    # No nets found, add default
                    if self.debug_mode:
                        self.output_text.append(f"No EEG net templates found for subject {subject_id}.")
                    self.eeg_net_combo.addItem("EGI_256")  # Default option
                    self.skin_net_combo.addItem("GSN-HydroCel-185")  # Default option for skin visualization
            else:
                if self.debug_mode:
                    self.output_text.append(f"EEG positions directory not found for subject {subject_id}.")
                self.eeg_net_combo.addItem("EGI_256")  # Default option
                self.skin_net_combo.addItem("GSN-HydroCel-185")  # Default option for skin visualization
        
        except Exception as e:
            self.output_text.append(f"Error scanning for EEG nets: {str(e)}")
            self.eeg_net_combo.addItem("EGI_256")  # Default option
    
    def find_available_atlases(self):
        """Find available atlas files for the selected subject."""
        if not self.subjects:
            return
        self.atlases = {}
        self.atlas_combo.clear()
        # Get the first selected subject (for consistency when multiple are selected)
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            return
        
        subject_id = selected_items[0].text()
        # Base directory where subjects are located
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        # Use segmentation directory for atlas files in new BIDS structure
        seg_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                              f'm2m_{subject_id}', 'segmentation')
        unique_atlases = set()
        self.atlas_display_map = {}  # Map display name to (subjectID, atlas_name)
        try:
            if os.path.isdir(seg_dir):
                # Find all .annot files in the directory
                for atlas_file in glob.glob(os.path.join(seg_dir, '*.annot')):
                    fname = os.path.basename(atlas_file)
                    # Expect format: lh.101_DK40.annot or rh.101_DK40.annot
                    parts = fname.split('.')
                    if len(parts) == 3 and parts[2] == 'annot':
                        atlas_full = parts[1]  # e.g., 101_DK40
                        # Remove subjectID prefix for display
                        atlas_display = atlas_full.split('_', 1)[-1] if '_' in atlas_full else atlas_full
                        unique_atlases.add(atlas_display)
                        self.atlas_display_map[atlas_display] = atlas_full
                        self.atlases[(parts[0], atlas_full)] = atlas_file
                for atlas_display in sorted(unique_atlases):
                    self.atlas_combo.addItem(atlas_display)
                if unique_atlases:
                    if self.debug_mode:
                        self.output_text.append(f"Found {len(unique_atlases)} unique atlases for subject {subject_id}.")
                else:
                    if self.debug_mode:
                        self.output_text.append(f"No atlas files found for subject {subject_id}.")
            else:
                if self.debug_mode:
                    self.output_text.append(f"Segmentation directory not found for subject {subject_id}.")
        except Exception as e:
            self.output_text.append(f"Error scanning for atlas files: {str(e)}")
        # Also update non-ROI atlas combo
        self._update_nonroi_atlas_combo()

    def find_available_volume_atlases(self):
        """Find available volume atlas files for the selected subject."""
        if not self.subjects:
            return
            
        self.volume_atlases = {}
        self.volume_atlas_combo.clear()
        
        # Get the first selected subject (for consistency when multiple are selected)
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            return
        
        subject_id = selected_items[0].text()
        
        # Base directory where subjects are located
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        
        # Check specifically for labeling.nii.gz in SimNIBS segmentation directory
        seg_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                              f'm2m_{subject_id}', 'segmentation')
        
        labeling_file = os.path.join(seg_dir, 'labeling.nii.gz')
        labeling_lut_file = os.path.join(seg_dir, 'labeling_LUT.txt')
        
        try:
            if os.path.isfile(labeling_file):
                self.volume_atlases['labeling.nii.gz'] = labeling_file
                self.volume_atlas_combo.addItem('labeling.nii.gz')
                
                # Check if LUT file exists
                if os.path.isfile(labeling_lut_file):
                    if self.debug_mode:
                        self.output_text.append(f"Found subcortical segmentation for subject {subject_id}: labeling.nii.gz with LUT file.")
                else:
                    if self.debug_mode:
                        self.output_text.append(f"Found subcortical segmentation for subject {subject_id}: labeling.nii.gz (warning: no LUT file found).")
            else:
                self.output_text.append(f"No subcortical segmentation found for subject {subject_id}. Expected: {labeling_file}")
                
        except Exception as e:
            self.output_text.append(f"Error scanning for subcortical segmentation: {str(e)}")

    def update_roi_method(self, checked):
        """Update the ROI method inputs based on selection."""
        if self.roi_method_spherical.isChecked():
            self.roi_stacked_widget.setCurrentIndex(0)
            self.view_t1_btn.setVisible(True)
        elif self.roi_method_cortical.isChecked():
            self.roi_stacked_widget.setCurrentIndex(1)
            self.view_t1_btn.setVisible(False)
        else:  # subcortical
            self.roi_stacked_widget.setCurrentIndex(2)
            self.view_t1_btn.setVisible(False)
        
        # Update coordinate space labels based on selection mode
        self._update_coordinate_space_labels()

    def _update_coordinate_space_labels(self):
        """Update coordinate space labels and tooltips based on space selection."""
        if self.roi_method_spherical.isChecked():
            if self.roi_space_mni.isChecked():
                # MNI space selected
                self.roi_coords_label.setText("ROI Center MNI Coordinates (mm):")
                self.roi_coords_label.setToolTip("MNI space coordinates (will be transformed to subject space for each subject)")
                self.roi_coords_label.setStyleSheet("color: #007ACC; font-weight: bold;")

                # Show MNI info label
                if hasattr(self, 'mni_info_label'):
                    self.mni_info_label.setVisible(True)

                # Update individual coordinate tooltips
                self.roi_x_input.setToolTip("X coordinate in MNI space")
                self.roi_y_input.setToolTip("Y coordinate in MNI space")
                self.roi_z_input.setToolTip("Z coordinate in MNI space")

                # Update Freeview button for MNI template
                self.view_t1_btn.setText("View MNI Template")
                self.view_t1_btn.setToolTip("Open MNI152 template to find MNI coordinates")
            else:
                # Subject space selected
                self.roi_coords_label.setText("ROI Center RAS Coordinates (mm):")
                self.roi_coords_label.setToolTip("Subject-specific RAS coordinates")
                self.roi_coords_label.setStyleSheet("")

                # Hide MNI info label
                if hasattr(self, 'mni_info_label'):
                    self.mni_info_label.setVisible(False)

                # Update individual coordinate tooltips
                self.roi_x_input.setToolTip("X coordinate in subject RAS space")
                self.roi_y_input.setToolTip("Y coordinate in subject RAS space")
                self.roi_z_input.setToolTip("Z coordinate in subject RAS space")

                # Update Freeview button for subject T1
                self.view_t1_btn.setText("View T1 in Freeview")
                self.view_t1_btn.setToolTip("Open subject's T1 scan in Freeview to find RAS coordinates")
        else:
            # Hide MNI info label for non-spherical ROI methods
            if hasattr(self, 'mni_info_label'):
                self.mni_info_label.setVisible(False)

    def _update_multiple_subject_restrictions(self):
        """Update UI restrictions when multiple subjects are selected."""
        selected_items = self.subject_list.selectedItems()
        multiple_subjects = len(selected_items) > 1
        
        # Update coordinate space labels when selection changes
        self._update_coordinate_space_labels()
        
        # No longer disable spherical ROI for multiple subjects
        # Instead, we'll use MNI coordinates for multiple subjects

    def run_optimization(self):
        """Run the flex-search optimization."""
        if self.optimization_running:
            self.update_output("Optimization already running. Please wait or stop the current run.")
            return
            
        # Validate inputs
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one subject.")
            return

        # Only require EEG net when mapping is enabled
        if self.run_mapped_simulation_checkbox.isChecked() and not self.eeg_net_combo.currentText():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select an EEG net.")
            return
        
        # Check if visualize skin region is enabled but no skin net is selected
        if self.visualize_skin_checkbox.isChecked() and not self.skin_net_combo.currentText():
            QtWidgets.QMessageBox.warning(
                self, "Warning",
                "Visualizing valid skin region requires selecting an EEG net for visualization.\n\n"
                "Please select a visualization EEG net."
            )
            return

        # Check coordinate space for spherical ROI with MNI space selected
        if self.roi_method_spherical.isChecked() and self.roi_space_mni.isChecked():
            # Show info about MNI coordinate usage
            reply = QtWidgets.QMessageBox.question(
                self, "MNI Coordinates",
                "You have selected MNI space for spherical ROI.\n\n"
                "The coordinates you entered will be treated as MNI space coordinates "
                "and will be automatically transformed to each subject's native space.\n\n"
                "Do you want to continue?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return
            
        # Get ROI parameters based on selected method
        if self.roi_method_spherical.isChecked():
            roi_params = {
                'method': 'spherical',
                'center': [
                    self.roi_x_input.value(),
                    self.roi_y_input.value(),
                    self.roi_z_input.value()
                ],
                'radius': self.roi_radius_input.value()
            }
        elif self.roi_method_cortical.isChecked():  # cortical ROI
            if not self.atlas_combo.currentText():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select an atlas for ROI.")
                return
            if not self.label_value_input.value():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a region for ROI.")
                return
                
            roi_params = {
                'method': 'atlas',
                'atlas': self.atlas_combo.currentText(),
                'region': str(self.label_value_input.value())
            }
        else:  # subcortical ROI
            if not self.volume_atlas_combo.currentText():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a volume atlas for subcortical ROI.")
                return
            if not self.volume_label_value_input.value():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a region label for subcortical ROI.")
                return
                
            roi_params = {
                'method': 'subcortical',
                'volume_atlas': self.volume_atlas_combo.currentText(),
                'volume_region': str(self.volume_label_value_input.value())
            }
            
        # Get optimization parameters for easier access and clarity
        selected_subjects = [item.text() for item in selected_items]
        goal = self.goal_combo.currentData()
        postproc = self.postproc_combo.currentData()
        eeg_net = self.eeg_net_combo.currentText()
        electrode_current = self.current_input.value()
        electrode_shape = "rect" if self.electrode_shape_rect.isChecked() else "ellipse"
        dimensions = self.dimensions_input.text() or "8,8"  # Default to 8,8 if empty
        thickness = self.thickness_input.text() or "4"  # Default to 4 if empty

        # Show confirmation dialog
        roi_description = ""
        if roi_params['method'] == 'spherical':
            roi_description = f"Spherical ROI at ({roi_params['center'][0]}, {roi_params['center'][1]}, {roi_params['center'][2]}) with radius {roi_params['radius']}mm"
        elif roi_params['method'] == 'atlas':
            roi_description = f"Cortical ROI: {roi_params['atlas']} region {roi_params['region']}"
        else:
            roi_description = f"Subcortical ROI: {roi_params['volume_atlas']} region {roi_params['volume_region']}"
            
        details = (f"Subjects: {', '.join(selected_subjects)}\n"
                  f"Number of subjects: {len(selected_subjects)}\n"
                  f"ROI: {roi_description}\n"
                  f"Goal: {goal}\n"
                  f"EEG Net: {eeg_net}\n"
                  f"Current: {electrode_current}mA\n"
                  f"Electrode shape: {electrode_shape}\n"
                  f"Dimensions: {dimensions}mm\n"
                  f"Thickness: {thickness}mm")
        
        if not ConfirmationDialog.confirm(
            self,
            title="Confirm Flex-Search Optimization",
            message="Are you sure you want to start the flex-search optimization?",
            details=details
        ):
            return

        # Show additional confirmation for multiple subjects if needed
        if len(selected_subjects) > 1:
            subject_list_str = ", ".join(selected_subjects)
            confirmation_msg = f"You are about to run optimization for {len(selected_subjects)} subjects: {subject_list_str}\n\nSubjects will be processed sequentially (one after another). Do you want to continue?"
            reply = QtWidgets.QMessageBox.question(self, "Multiple Subjects", confirmation_msg, 
                                                 QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if reply != QtWidgets.QMessageBox.Yes:
                return

        # Set up for sequential processing
        self.optimization_running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.disable_controls()
        
        # Initialize counters
        self.current_subject_index = 0
        self.selected_subjects = selected_subjects
        self.successful_runs = 0
        self.failed_runs = 0
        self.roi_params = roi_params
        self.goal = goal
        self.postproc = postproc
        self.eeg_net = eeg_net
        self.electrode_current = electrode_current
        self.electrode_shape = electrode_shape
        self.dimensions = dimensions
        self.thickness = thickness
        
        # Start processing the first subject
        self._process_next_subject()

    def _process_next_subject(self):
        """Process the next subject in the queue sequentially."""
        if self.current_subject_index >= len(self.selected_subjects):
            # All subjects processed, show summary
            self._finalize_multi_subject_optimization()
            return
            
        subject_id = self.selected_subjects[self.current_subject_index]
        
        if len(self.selected_subjects) > 1:
            self.update_output(f"\n=== Processing Subject {self.current_subject_index + 1}/{len(self.selected_subjects)}: {subject_id} ===")
        
        # Run optimization for this subject
        success = self._run_single_subject_optimization(
            subject_id, self.roi_params, self.goal, self.postproc,
            self.eeg_net, self.electrode_current,
            self.electrode_shape, self.dimensions, self.thickness
        )
        
        if not success:
            self.failed_runs += 1
            self.current_subject_index += 1
            # Continue with next subject even if current one failed
            self._process_next_subject()

    def _finalize_multi_subject_optimization(self):
        """Finalize the multi-subject optimization and show summary."""
        if len(self.selected_subjects) > 1:
            self.update_output(f"\n=== Optimization Summary ===")
            self.update_output(f"Successfully completed: {self.successful_runs}/{len(self.selected_subjects)} subjects")
            if self.failed_runs > 0:
                self.update_output(f"Failed: {self.failed_runs}/{len(self.selected_subjects)} subjects", 'error')
        
        # Clean up multi-subject state variables
        if hasattr(self, 'selected_subjects'):
            delattr(self, 'selected_subjects')
        if hasattr(self, 'current_subject_index'):
            delattr(self, 'current_subject_index')
        if hasattr(self, 'roi_params'):
            delattr(self, 'roi_params')
        if hasattr(self, 'goal'):
            delattr(self, 'goal')
        if hasattr(self, 'postproc'):
            delattr(self, 'postproc')
        if hasattr(self, 'eeg_net'):
            delattr(self, 'eeg_net')
        if hasattr(self, 'electrode_current'):
            delattr(self, 'electrode_current')
        if hasattr(self, 'electrode_shape'):
            delattr(self, 'electrode_shape')
        if hasattr(self, 'dimensions'):
            delattr(self, 'dimensions')
        if hasattr(self, 'thickness'):
            delattr(self, 'thickness')
        
        # Reset state
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls()
        
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

    def _run_single_subject_optimization(self, subject_id, roi_params, goal, postproc, eeg_net, electrode_current, electrode_shape, dimensions, thickness):
        """Run optimization for a single subject. Returns True if started successfully, False otherwise."""
        try:
            # Don't set optimization_running here - it's managed in run_optimization
            # Don't disable controls here - they're managed in run_optimization

            # Prepare environment variables
            env = os.environ.copy()
            gui_project_dir_name = os.environ.get('PROJECT_DIR_NAME')
            if gui_project_dir_name:
                env['PROJECT_DIR'] = f"/mnt/{gui_project_dir_name}" 
            else:
                # Fallback if not set
                cwd = os.getcwd()
                potential_dirs = [
                    os.path.dirname(cwd), os.path.join(cwd, ".."), os.path.abspath(os.path.join(cwd, "..")),
                    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
                ]
                found_project_dir = None
                for pd_candidate in potential_dirs:
                    if os.path.isdir(pd_candidate) and os.path.isdir(os.path.join(pd_candidate, 'derivatives', 'SimNIBS', f'sub-{subject_id}')):
                        found_project_dir = pd_candidate
                        self.output_text.append(f"PROJECT_DIR (for env) heuristically set to: {found_project_dir}")
                        break
                if found_project_dir:
                    env['PROJECT_DIR'] = found_project_dir
                else:
                    self.output_text.append("Warning: PROJECT_DIR_NAME not in env and heuristic search failed. Using default /mnt/BIDS_test for env['PROJECT_DIR']")
                    env['PROJECT_DIR'] = "/mnt/BIDS_test"

            script_project_dir = env['PROJECT_DIR']

            env['SUBJECT_ID'] = subject_id
            if roi_params['method'] == "spherical":
                env['ROI_X'] = str(roi_params['center'][0])
                env['ROI_Y'] = str(roi_params['center'][1])
                env['ROI_Z'] = str(roi_params['center'][2])
                env['ROI_RADIUS'] = str(roi_params['radius'])
                # Indicate if these are MNI coordinates based on user selection
                env['USE_MNI_COORDS'] = 'true' if self.roi_space_mni.isChecked() else 'false'
            elif roi_params['method'] == "atlas":
                atlas_display_for_env = roi_params['atlas']
                # Extract just the atlas type (e.g., "DK40") and construct subject-specific name
                # The atlas_display_map contains the full name from the first subject (e.g., "101_DK40")
                # but we need to construct the correct name for the current subject (e.g., "102_DK40")
                atlas_base_name = self.atlas_display_map.get(atlas_display_for_env, atlas_display_for_env)
                
                # Extract the atlas type by removing the subject prefix
                # e.g., "101_DK40" → "DK40"
                if '_' in atlas_base_name:
                    atlas_type = atlas_base_name.split('_', 1)[-1]  # Everything after first underscore
                else:
                    atlas_type = atlas_base_name  # Fallback if no underscore
                
                # Construct the correct subject-specific atlas name
                atlas_name_for_env = f"{subject_id}_{atlas_type}"
                
                hemi_for_env = "lh" if self.roi_hemi_combo.currentIndex() == 0 else "rh"
                seg_dir_for_env = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
                atlas_path_for_env = os.path.join(seg_dir_for_env, f'{hemi_for_env}.{atlas_name_for_env}.annot')
                env['ATLAS_PATH'] = atlas_path_for_env
                env['SELECTED_HEMISPHERE'] = hemi_for_env
                env['ROI_LABEL'] = str(roi_params['region'])
            else:  # subcortical
                volume_atlas_for_env = roi_params['volume_atlas']
                # Dynamically construct the volume atlas path for the current subject
                # (to avoid using the wrong subject's labeling.nii.gz in multi-subject runs)
                seg_dir_for_env = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
                volume_atlas_path_for_env = os.path.join(seg_dir_for_env, volume_atlas_for_env)
                if os.path.isfile(volume_atlas_path_for_env):
                    env['VOLUME_ATLAS_PATH'] = volume_atlas_path_for_env
                else:
                    self.output_text.append(f"Warning: Volume atlas not found for subject {subject_id}: {volume_atlas_path_for_env}")
                env['VOLUME_ROI_LABEL'] = str(roi_params['volume_region'])
            
            # Build the command
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            flex_module_path = os.path.join(script_dir, "opt", "flex")
            if not os.path.isdir(flex_module_path):
                self.output_text.append(f"Error: flex module not found at {flex_module_path}. Optimization cannot continue.")
                return False

            # Pass debug mode setting to control summary output
            env['DEBUG_MODE'] = 'true' if self.debug_mode else 'false'

            cmd = [
                "simnibs_python", "-m", "opt.flex",
                "--subject", subject_id,
                "--goal", goal,
                "--postproc", postproc,
                "--current", str(electrode_current),
                "--electrode-shape", electrode_shape,
                "--dimensions", dimensions,
                "--thickness", thickness,
                "--roi-method", roi_params['method']
            ]

            # Mapping options
            if self.run_mapped_simulation_checkbox.isChecked():
                cmd.extend(["--enable-mapping", "--eeg-net", eeg_net])
                # When run_mapped_simulation is checked, we always run the mapping simulation
                # (no need for --disable-mapping-simulation)

            # Focality options
            if goal == "focality":
                # Check if adaptive mode is enabled
                if self.adaptive_focality_checkbox.isChecked():
                    # Validate adaptive percentage values
                    nonroi_pct = self.nonroi_percentage_input.value()
                    roi_pct = self.roi_percentage_input.value()
                    
                    if nonroi_pct >= roi_pct:
                        self.output_text.append("Error: Non-ROI percentage must be less than ROI percentage for focality optimization.")
                        return False
                    
                    if nonroi_pct <= 0 or roi_pct <= 0:
                        self.output_text.append("Error: Percentage values must be greater than 0.")
                        return False
                    
                    if nonroi_pct >= 100 or roi_pct >= 100:
                        self.output_text.append("Error: Percentage values must be less than 100.")
                        return False
                    
                    # Run adaptive focality optimization
                    return self._run_adaptive_focality_optimization(
                        subject_id, roi_params, postproc, eeg_net,
                        electrode_current, electrode_shape, dimensions, thickness, env, cmd[:-1]  # Remove roi-method from base cmd
                    )
                else:
                    # Standard focality optimization
                    thresholds = self.threshold_input.text().strip()
                    nonroi_method = self.nonroi_method_combo.currentData()
                    if not thresholds:
                        self.output_text.append("Error: Please enter threshold(s) for focality.")
                        return False
                    cmd += ["--non-roi-method", nonroi_method, "--thresholds", thresholds]
                if nonroi_method == "specific":
                    if roi_params['method'] == "spherical":
                        env['NON_ROI_X'] = str(self.nonroi_x_input.value())
                        env['NON_ROI_Y'] = str(self.nonroi_y_input.value())
                        env['NON_ROI_Z'] = str(self.nonroi_z_input.value())
                        env['NON_ROI_RADIUS'] = str(self.nonroi_radius_input.value())
                        # Non-ROI also uses same coordinate space as ROI
                        env['USE_MNI_COORDS_NON_ROI'] = env.get('USE_MNI_COORDS', 'false')
                    elif roi_params['method'] == "atlas":
                        nonroi_atlas_display = self.nonroi_atlas_combo.currentText()
                        # Apply same multiple-subject fix for non-ROI atlas
                        nonroi_atlas_base_name = self.atlas_display_map.get(nonroi_atlas_display, nonroi_atlas_display)
                        
                        # Extract the atlas type by removing the subject prefix
                        if '_' in nonroi_atlas_base_name:
                            nonroi_atlas_type = nonroi_atlas_base_name.split('_', 1)[-1]
                        else:
                            nonroi_atlas_type = nonroi_atlas_base_name
                        
                        # Construct the correct subject-specific atlas name
                        nonroi_atlas_name = f"{subject_id}_{nonroi_atlas_type}"
                        
                        nonroi_hemi = "lh" if self.nonroi_hemi_combo.currentIndex() == 0 else "rh"
                        nonroi_label_val = self.nonroi_label_input.value()
                        nonroi_atlas_path_arg = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                                         f'm2m_{subject_id}', 'segmentation', f'{nonroi_hemi}.{nonroi_atlas_name}.annot')
                        env['NON_ROI_ATLAS_PATH'] = nonroi_atlas_path_arg
                        env['NON_ROI_HEMISPHERE'] = nonroi_hemi
                        env['NON_ROI_LABEL'] = str(nonroi_label_val)
                    else:  # subcortical volume for non-ROI
                        nonroi_volume_atlas = self.nonroi_volume_atlas_combo.currentText()
                        nonroi_volume_label_val = self.nonroi_volume_label_input.value()
                        # Dynamically construct the non-ROI volume atlas path for the current subject
                        seg_dir_for_env = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
                        nonroi_volume_atlas_path = os.path.join(seg_dir_for_env, nonroi_volume_atlas)
                        if os.path.isfile(nonroi_volume_atlas_path):
                            env['VOLUME_NON_ROI_ATLAS_PATH'] = nonroi_volume_atlas_path
                        else:
                            self.output_text.append(f"Warning: Non-ROI volume atlas not found for subject {subject_id}: {nonroi_volume_atlas_path}")
                        env['VOLUME_NON_ROI_LABEL'] = str(nonroi_volume_label_val)
            
            # Stability and Memory options
            if not self.run_final_electrode_simulation_checkbox.isChecked():
                cmd.append("--skip-final-electrode-simulation")
            cmd.extend(["--n-multistart", str(self.n_multistart_input.value())])
            cmd.extend(["--max-iterations", str(self.max_iterations_input.value())])
            cmd.extend(["--population-size", str(self.population_size_input.value())])
            cmd.extend(["--cpus", str(self.cpus_input.value())])

            # Differential evolution optimizer parameters
            cmd.extend(["--tolerance", str(self.tolerance_input.value())])

            # Mutation parameter as "min,max" string
            mutation_str = f"{self.mutation_min_input.value()},{self.mutation_max_input.value()}"
            cmd.extend(["--mutation", mutation_str])

            cmd.extend(["--recombination", str(self.recombination_input.value())])

            # Detailed results flag
            if self.detailed_results_checkbox.isChecked():
                cmd.append("--detailed-results")

            # Visualize valid skin region flag
            if self.visualize_skin_checkbox.isChecked():
                cmd.append("--visualize-valid-skin-region")
                # Add skin visualization net if selected
                skin_net = self.skin_net_combo.currentText()
                if skin_net:
                    skin_net_path = self.eeg_nets.get(skin_net)
                    if skin_net_path:
                        cmd.extend(["--skin-visualization-net", skin_net_path])
                    else:
                        # Fallback for default nets that don't have a file path
                        default_path = os.path.join(script_project_dir, 'derivatives', 'SimNIBS',
                                                  f'sub-{subject_id}', f'm2m_{subject_id}',
                                                  'eeg_positions', f'{skin_net}.csv')
                        cmd.extend(["--skin-visualization-net", default_path])

            # Only show setup messages in debug mode
            if self.debug_mode:
                self.output_text.append(f"Running optimization for subject {subject_id} (this may take a while)...")
                self.output_text.append("Command: " + " ".join(cmd))
                self.output_text.append("Environment for subprocess will include:")
                for k, v in env.items():
                    if k.startswith("ROI") or k.startswith("VOLUME") or k in ['PROJECT_DIR', 'SUBJECT_ID', 'ATLAS_PATH', 'SELECTED_HEMISPHERE']:
                        self.output_text.append(f"  {k}: {v}")

            # Only set parent busy state for single subjects (multi-subject is handled in run_optimization)
            if not hasattr(self, 'selected_subjects') or len(self.selected_subjects) == 1:
                if hasattr(self, 'parent') and self.parent:
                    keep_enabled_widgets = [self.console_widget.debug_checkbox] if hasattr(self, 'console_widget') else []
                    self.parent.set_tab_busy(self, True, stop_btn=self.stop_btn, keep_enabled=keep_enabled_widgets)
            
            self.optimization_process = FlexSearchThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
            self.optimization_process.finished.connect(self.optimization_finished)
            self.optimization_process.start()
            
            return True
            
        except Exception as e:
            self.update_output(f"Error executing optimization for subject {subject_id}: {str(e)}", 'error')
            return False

    def _build_confirmation_details(self, subject_id, roi_params, goal, postproc, eeg_net, electrode_current):
        """Build confirmation dialog details string."""
        details = (f"This will run flex-search optimization with the following parameters:\n\n" +
                   f"• Subject: {subject_id}\n" +
                   f"• EEG Net: {eeg_net}\n" +
                   f"• Optimization Goal: {self.goal_combo.currentText()} ({goal})\n" +
                   f"• Post-processing: {self.postproc_combo.currentText()} ({postproc})\n" +
                   f"• Electrode Current: {electrode_current} mA\n" +
                   f"• Electrode Shape: {electrode_shape}\n" +
                   f"• Dimensions: {dimensions} mm\n" +
                   f"• Thickness: {thickness} mm\n" +
                   f"• ROI Method: {'Spherical' if roi_params['method'] == 'spherical' else 'Cortical' if roi_params['method'] == 'atlas' else 'Subcortical'}\n")
        
        if roi_params['method'] == 'spherical':
            coord_space = "MNI" if hasattr(self, 'selected_subjects') and len(self.selected_subjects) > 1 else "RAS"
            details += (f"• ROI Center ({coord_space}): ({roi_params['center'][0]}, {roi_params['center'][1]}, {roi_params['center'][2]}) mm\n" +
                        f"• ROI Radius: {roi_params['radius']} mm\n")
            if coord_space == "MNI":
                details += f"• Coordinate Transformation: MNI → Subject space (automatic)\n"
        elif roi_params['method'] == 'atlas':
            details += (f"• ROI Atlas: {roi_params['atlas']}\n" +
                        f"• ROI Region: {roi_params['region']}\n")
        else:  # subcortical
            details += (f"• Volume Atlas: {roi_params['volume_atlas']}\n" +
                        f"• Volume Region Label: {roi_params['volume_region']}\n")
        
        if self.run_mapped_simulation_checkbox.isChecked():
            details += f"• Electrode Mapping & Simulation: ✓ ENABLED (runs simulation with mapped electrodes)\n"
        else:
            details += f"• Electrode Mapping: ✗ DISABLED (continuous optimization)\n"

        details += f"\nStability & Memory:\n"
        details += f"• Number of Optimization Runs: {self.n_multistart_input.value()}\n"
        details += f"• Max Iterations: {self.max_iterations_input.value()}\n"
        details += f"• Population Size: {self.population_size_input.value()}\n"
        details += f"• Number of CPUs: {self.cpus_input.value()}\n"

        details += f"\nDifferential Evolution Parameters:\n"
        details += f"• Tolerance: {self.tolerance_input.value()}\n"
        details += f"• Mutation: [{self.mutation_min_input.value()}, {self.mutation_max_input.value()}]\n"
        details += f"• Recombination: {self.recombination_input.value()}\n"

        if self.detailed_results_checkbox.isChecked():
            details += f"• Detailed Results: ✓ ENABLED (creates additional visualization files)\n"

        if self.n_multistart_input.value() > 1:
            details += f"\n Multi-Start Optimization: {self.n_multistart_input.value()} runs will be performed.\n"
            details += f"The best result (minimum objective function value) will be automatically selected and kept.\n"

        return details


    def update_output(self, text, message_type='default'):
        """Update the console output with colored text."""
        if not text.strip():
            return
        
        # Filter messages based on debug mode
        if not self.debug_mode:
            # In non-debug mode, only show important messages
            if not is_important_message(text, message_type, 'flexsearch'):
                return
            # Colorize summary lines: blue for starts, white for completes, green for final
            lower = text.lower()
            is_final = lower.startswith('└─') or 'completed successfully' in lower
            is_start = lower.startswith('beginning ') or ': starting' in lower
            is_complete = ('✓ complete' in lower) or ('results available in:' in lower) or ('saved to' in lower)
            color = '#55ff55' if is_final else ('#55aaff' if is_start else '#ffffff')
            formatted_text = f'<span style="color: {color};">{text}</span>'
            scrollbar = self.output_text.verticalScrollBar()
            at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
            self.output_text.append(formatted_text)
            if at_bottom:
                self.output_text.ensureCursorVisible()
            QtWidgets.QApplication.processEvents()
            return
            
            # Additional filtering for setup/configuration messages that shouldn't appear in non-debug mode
            setup_patterns = [
                "Looking for subjects in:",
                "=== Subjects Found ===",
                "Found ",  # This catches "Found 3 unique atlases", "Found 9 EEG net templates", etc.
                "EEG net templates for subject",
                "unique atlases for subject",
                "subcortical segmentation for subject",
                "Running optimization for subject",
                "Command: ",
                "Environment for subprocess will include:",
                "PROJECT_DIR:",
                "SUBJECT_ID:",
                "ROI_X:",
                "ROI_Y:",
                "ROI_Z:",
                "ROI_RADIUS:",
                "labeling.nii.gz with LUT file",  # Catches subcortical segmentation messages
                "with LUT file",  # Additional catch for LUT file messages
                "atlases for subject",  # More specific catch for atlas messages
                "segmentation for subject"  # More specific catch for segmentation messages
            ]
            
            if any(pattern in text for pattern in setup_patterns):
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
        
        # Check if user is at the bottom of the console before appending
        scrollbar = self.output_text.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5  # Allow small tolerance
        
        # Append to the console with HTML formatting
        self.output_text.append(formatted_text)
        
        # Only auto-scroll if user was already at the bottom
        if at_bottom:
            self.output_text.ensureCursorVisible()
        
        QtWidgets.QApplication.processEvents()

    def set_debug_mode(self, debug_mode):
        """Set debug mode for output filtering."""
        self.debug_mode = debug_mode
    
    def optimization_finished(self):
        """Handle the completion of the optimization process."""
        # Check if this was a successful completion
        if hasattr(self, 'optimization_process') and self.optimization_process:
            if self.optimization_process.process and self.optimization_process.process.returncode == 0:
                self.successful_runs += 1
            else:
                self.failed_runs += 1
        
        # Move to next subject if we're in multi-subject mode
        if hasattr(self, 'selected_subjects') and len(self.selected_subjects) > 1:
            self.current_subject_index += 1
            self.output_text.append(f"Subject {self.current_subject_index}/{len(self.selected_subjects)} completed.")
            
            # Process next subject or finalize
            self._process_next_subject()
        else:
            # Single subject mode or last subject in multi-subject mode
            if hasattr(self, 'parent') and self.parent:
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
            self.optimization_running = False
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.enable_controls()
            # Remove the unwanted completion message
            # self.output_text.append("\nOptimization process completed.")
    
    def clear_console(self):
        """Clear the output console."""
        self.output_text.clear()
    
    def stop_optimization(self):
        """Stop the running optimization process."""
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
        if not self.optimization_running:
            return
        
        self.output_text.append("Stopping optimization...")
        if self.optimization_process:
            if self.optimization_process.terminate_process():
                self.output_text.append("Optimization stopped.")
            else:
                self.output_text.append("Failed to stop optimization.")
        
        # Reset multi-subject state if applicable
        if hasattr(self, 'selected_subjects') and len(self.selected_subjects) > 1:
            self.output_text.append(f"Multi-subject optimization stopped at subject {self.current_subject_index + 1}/{len(self.selected_subjects)}.")
            # Clear multi-subject state
            if hasattr(self, 'selected_subjects'):
                delattr(self, 'selected_subjects')
            if hasattr(self, 'current_subject_index'):
                delattr(self, 'current_subject_index')
        
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls()

    def on_subject_changed(self):
        """Handle subject selection change."""
        # Refresh EEG nets and atlases for the new selection
        if self.subject_list.selectedItems():
            self.find_available_eeg_nets()
            self.find_available_atlases()
            self.find_available_volume_atlases()
        
        # Update multiple subject restrictions
        self._update_multiple_subject_restrictions()

    def load_t1_in_freeview(self):
        """Load the subject's T1 NIfTI file or MNI template in Freeview for coordinate selection."""
        try:
            selected_items = self.subject_list.selectedItems()
            if not selected_items:
                QtWidgets.QMessageBox.warning(self, "Error", "Please select a subject first")
                return
            
            multiple_subjects = len(selected_items) > 1
            
            if multiple_subjects and self.roi_method_spherical.isChecked():
                # Multiple subjects: load MNI template
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
                try:
                    subprocess.Popen(['freeview', mni_file])
                    self.output_text.append(f"Launched Freeview with MNI152 template: {mni_file}")
                    self.output_text.append("Use Freeview to find MNI coordinates and enter them in the ROI coordinates fields.")
                    self.output_text.append("These MNI coordinates will be automatically transformed to each subject's native space.")
                except FileNotFoundError:
                    QtWidgets.QMessageBox.warning(self, "Error", "Freeview not found. Please install FreeSurfer or ensure it's in your PATH")
                except Exception as e:
                    QtWidgets.QMessageBox.warning(self, "Error", f"Failed to launch Freeview: {str(e)}")
            else:
                # Single subject: load subject's T1
                subject_id = selected_items[0].text()
                # Base directory where subjects are located
                project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
                
                # Look for T1 NIfTI files in multiple locations
                t1_paths = [
                    # Native space T1 from SimNIBS
                    os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'T1.nii.gz'),
                    # Original BIDS T1
                    os.path.join(project_dir, f'sub-{subject_id}', 'anat', f'sub-{subject_id}_T1w.nii.gz'),
                    # Alternative naming
                    os.path.join(project_dir, f'sub-{subject_id}', 'anat', f'anat-T1w_acq-MPRAGE.nii.gz'),
                ]
                
                t1_file = None
                for path in t1_paths:
                    if os.path.isfile(path):
                        t1_file = path
                        break
                
                if not t1_file:
                    QtWidgets.QMessageBox.warning(self, "Error", f"T1 file not found for subject {subject_id}")
                    return
                
                # Launch Freeview
                try:
                    subprocess.Popen(['freeview', t1_file])
                    self.output_text.append(f"Launched Freeview with T1 for subject {subject_id}: {t1_file}")
                    self.output_text.append("Use Freeview to find RAS coordinates and enter them in the ROI coordinates fields.")
                except FileNotFoundError:
                    QtWidgets.QMessageBox.warning(self, "Error", "Freeview not found. Please install FreeSurfer or ensure it's in your PATH")
                except Exception as e:
                    QtWidgets.QMessageBox.warning(self, "Error", f"Failed to launch Freeview: {str(e)}")
                
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Error loading image in Freeview: {str(e)}")

    def _update_mapping_options(self):
        """Update visibility of EEG net selector based on mapped simulation checkbox."""
        is_mapping_enabled = self.run_mapped_simulation_checkbox.isChecked()
        self.eeg_net_widget.setVisible(is_mapping_enabled)
        self.eeg_net_label.setVisible(is_mapping_enabled)

    def _on_detailed_results_toggled(self):
        """Handle detailed results checkbox state change."""
        is_detailed_results = self.detailed_results_checkbox.isChecked()
        self.visualize_skin_checkbox.setEnabled(is_detailed_results)
        if not is_detailed_results:
            self.visualize_skin_checkbox.setChecked(False)
            # Also disable skin net combo when detailed results is disabled
            self.skin_net_combo.setEnabled(False)

    def _on_visualize_skin_toggled(self):
        """Handle visualize skin checkbox state change."""
        is_visualize_skin = self.visualize_skin_checkbox.isChecked()
        self.skin_net_combo.setEnabled(is_visualize_skin)
        # Clear selection if disabled
        if not is_visualize_skin:
            self.skin_net_combo.setCurrentIndex(-1)

    def _update_focality_visibility(self):
        is_focality = self.goal_combo.currentData() == "focality"
        self.focality_group.setVisible(is_focality)
        # Default to 'everything_else' and collapse non-ROI region
        if is_focality:
            self.nonroi_method_combo.setCurrentIndex(0)
            self.nonroi_stacked.setVisible(False)
            # Initialize adaptive controls visibility
            self._update_adaptive_focality_controls()
    
    def _update_adaptive_focality_controls(self):
        """Update visibility of adaptive vs manual threshold controls."""
        is_adaptive = self.adaptive_focality_checkbox.isChecked()
        
        # Show/hide controls based on adaptive mode
        self.threshold_input.setVisible(not is_adaptive)
        self.threshold_label.setVisible(not is_adaptive)
        
        # Enable/disable percentage inputs based on adaptive mode and optimization state
        adaptive_enabled = is_adaptive and not self.optimization_running
        self.nonroi_percentage_input.setEnabled(adaptive_enabled)
        self.roi_percentage_input.setEnabled(adaptive_enabled)
        
        # Update help text visibility based on mode
        for i in range(self.focality_group.layout().rowCount()):
            # Hide/show adaptive help text
            item = self.focality_group.layout().itemAt(i, QtWidgets.QFormLayout.SpanningRole)
            if item and item.widget() and isinstance(item.widget(), QtWidgets.QLabel):
                if "Automatically determines thresholds" in item.widget().text():
                    item.widget().setVisible(is_adaptive)
                elif "Single value:" in item.widget().text():
                    item.widget().setVisible(not is_adaptive)
            
            # Hide/show adaptive percentage controls
            item = self.focality_group.layout().itemAt(i, QtWidgets.QFormLayout.FieldRole)
            if item and item.widget():
                label_item = self.focality_group.layout().itemAt(i, QtWidgets.QFormLayout.LabelRole)
                if label_item and label_item.widget() and isinstance(label_item.widget(), QtWidgets.QLabel):
                    if "Adaptive Percentages:" in label_item.widget().text():
                        label_item.widget().setVisible(is_adaptive)
                        item.widget().setVisible(is_adaptive)

    def _update_nonroi_stacked(self):
        if self.nonroi_method_combo.currentData() == "everything_else":
            self.nonroi_stacked.setVisible(False)
        else:
            self.nonroi_stacked.setVisible(True)
            if self.roi_method_spherical.isChecked():
                self.nonroi_stacked.setCurrentIndex(0)  # Spherical non-ROI
            elif self.roi_method_cortical.isChecked():
                self.nonroi_stacked.setCurrentIndex(1)  # Atlas non-ROI
            else:  # subcortical
                self.nonroi_stacked.setCurrentIndex(2)  # Volume non-ROI

    def _update_nonroi_atlas_combo(self):
        self.nonroi_atlas_combo.clear()
        for i in range(self.atlas_combo.count()):
            self.nonroi_atlas_combo.addItem(self.atlas_combo.itemText(i))
            
        # Also update volume atlas combo for non-ROI
        self.nonroi_volume_atlas_combo.clear()
        for i in range(self.volume_atlas_combo.count()):
            self.nonroi_volume_atlas_combo.addItem(self.volume_atlas_combo.itemText(i))

    def _list_roi_regions(self):
        atlas = self.atlas_combo.currentText()
        hemi = "lh" if self.roi_hemi_combo.currentIndex() == 0 else "rh"
        self._show_atlas_regions_dialog(atlas, hemi)

    def _list_nonroi_regions(self):
        atlas = self.nonroi_atlas_combo.currentText()
        hemi = "lh" if self.nonroi_hemi_combo.currentIndex() == 0 else "rh"
        self._show_atlas_regions_dialog(atlas, hemi)

    def _list_volume_regions(self):
        volume_atlas = self.volume_atlas_combo.currentText()
        self._show_volume_regions_dialog(volume_atlas)

    def _list_nonroi_volume_regions(self):
        volume_atlas = self.nonroi_volume_atlas_combo.currentText()
        self._show_volume_regions_dialog(volume_atlas)

    def _show_atlas_regions_dialog(self, atlas_display, hemi):
        # Find the atlas file path
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "No Subject Selected", "Please select a subject.")
            return
            
        subject_id = selected_items[0].text()
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        seg_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
        
        # Get the full atlas name for this subject
        atlas_full = self.atlas_display_map.get(atlas_display, atlas_display)
        annot_file = os.path.join(seg_dir, f'{hemi}.{atlas_full}.annot')

        if not os.path.isfile(annot_file):
            QtWidgets.QMessageBox.warning(self, "Atlas File Not Found", f"Could not find atlas file: {annot_file}")
            return
        # Run read_annot.py and show output
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        utils_dir = os.path.join(script_dir, "tools")
        read_annot_py = os.path.join(utils_dir, "read_annot.py")
        if not os.path.isfile(read_annot_py):
            QtWidgets.QMessageBox.warning(self, "read_annot.py Not Found", f"Could not find read_annot.py at {read_annot_py}")
            return
        try:
            result = subprocess.run(["simnibs_python", read_annot_py, annot_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if result.returncode != 0:
                QtWidgets.QMessageBox.warning(self, "Error Listing Regions", result.stderr)
                return
            output = result.stdout
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error Listing Regions", str(e))
            return
        # Show output in a dialog with search
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Regions in {hemi}.{atlas_display}")
        dlg.setMinimumWidth(600)
        layout = QtWidgets.QVBoxLayout(dlg)
        # Search box
        search_box = QtWidgets.QLineEdit()
        search_box.setPlaceholderText("Search regions...")
        layout.addWidget(search_box)
        # Text area
        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setText(output)
        layout.addWidget(text)
        # Filter function
        def filter_regions():
            query = search_box.text().strip().lower()
            if not query:
                text.setText(output)
                return
            filtered = '\n'.join([line for line in output.splitlines() if query in line.lower()])
            text.setText(filtered)
        search_box.textChanged.connect(filter_regions)
        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()

    def _show_volume_regions_dialog(self, volume_atlas):
        """Show a dialog to browse and select volume atlas regions."""
        
        # Get the subject ID and construct LUT file path
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "No Subject Selected", "Please select a subject.")
            return
            
        subject_id = selected_items[0].text()
        if not subject_id:
            QtWidgets.QMessageBox.warning(self, "No Subject Selected", "Please select a subject.")
            return

        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        seg_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                              f'm2m_{subject_id}', 'segmentation')
        labeling_lut_file = os.path.join(seg_dir, 'labeling_LUT.txt')
        
        if not os.path.isfile(labeling_lut_file):
            QtWidgets.QMessageBox.warning(self, "LUT File Not Found", 
                                         f"Could not find labeling_LUT.txt file at: {labeling_lut_file}")
            return
        
        # Read and parse the LUT file
        try:
            output = "Subcortical Regions (labeling.nii.gz):\n"
            output += "=" * 50 + "\n"
            output += f"{'ID':<4} {'Structure Name':<35} {'RGB'}\n"
            output += "-" * 50 + "\n"
            
            with open(labeling_lut_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Split by tab first, then by whitespace to handle mixed separators
                        parts = line.split('\t')
                        if len(parts) >= 2:  # At least ID and Name
                            try:
                                label_id = parts[0].strip()
                                label_name = parts[1].strip()
                                
                                # The remaining parts might be R G B A separated by whitespace
                                # Join remaining parts and split by whitespace
                                remaining = '\t'.join(parts[2:]) if len(parts) > 2 else ""
                                rgb_parts = remaining.split()
                                
                                if len(rgb_parts) >= 3:  # We have R, G, B values
                                    r = rgb_parts[0]
                                    g = rgb_parts[1] 
                                    b = rgb_parts[2]
                                    output += f"{label_id:<4} {label_name:<35} ({r},{g},{b})\n"
                                else:
                                    # No RGB values found, just show ID and name
                                    output += f"{label_id:<4} {label_name:<35} (no color)\n"
                            except (ValueError, IndexError):
                                continue  # Skip malformed lines
                                
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error Reading LUT File", f"Error reading LUT file: {str(e)}")
            return
        
        # Show output in a dialog with search
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Subcortical Regions - {volume_atlas}")
        dlg.setMinimumWidth(700)
        layout = QtWidgets.QVBoxLayout(dlg)
        
        # Search box
        search_box = QtWidgets.QLineEdit()
        search_box.setPlaceholderText("Search regions (by ID or name)...")
        layout.addWidget(search_box)
        
        # Text area
        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setFont(QtGui.QFont("Consolas", 10))  # Use monospace font for better alignment
        text.setText(output)
        layout.addWidget(text)
        
        # Filter function
        def filter_regions():
            query = search_box.text().strip().lower()
            if not query:
                text.setText(output)
                return
            filtered_lines = []
            for line in output.splitlines():
                if query in line.lower():
                    filtered_lines.append(line)
            text.setText('\n'.join(filtered_lines))
        
        search_box.textChanged.connect(filter_regions)
        
        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()

    def disable_controls(self):
        """Disable all input controls during optimization."""
        # Disable subject selection
        self.subject_list.setEnabled(False)
        self.refresh_subjects_btn.setEnabled(False)
        self.select_all_subjects_btn.setEnabled(False)
        self.clear_subjects_btn.setEnabled(False)
        
        # Disable optimization parameters
        self.goal_combo.setEnabled(False)
        self.postproc_combo.setEnabled(False)
        self.eeg_net_combo.setEnabled(False)
        self.refresh_eeg_nets_btn.setEnabled(False)
        
        # Disable electrode parameters
        self.current_input.setEnabled(False)
        self.electrode_shape_rect.setEnabled(False)
        self.electrode_shape_ellipse.setEnabled(False)
        self.dimensions_input.setEnabled(False)
        self.thickness_input.setEnabled(False)
        
        # Disable simulation options
        self.run_final_electrode_simulation_checkbox.setEnabled(False)
        self.run_mapped_simulation_checkbox.setEnabled(False)
        
        # Disable ROI method selection
        self.roi_method_spherical.setEnabled(False)
        self.roi_method_cortical.setEnabled(False)
        self.roi_method_subcortical.setEnabled(False)
        
        # Disable ROI inputs based on method
        if self.roi_method_spherical.isChecked():
            self.roi_x_input.setEnabled(False)
            self.roi_y_input.setEnabled(False)
            self.roi_z_input.setEnabled(False)
            self.roi_radius_input.setEnabled(False)
            self.view_t1_btn.setEnabled(False)
        elif self.roi_method_cortical.isChecked():
            self.atlas_combo.setEnabled(False)
            self.roi_hemi_combo.setEnabled(False)
            self.refresh_atlases_btn.setEnabled(False)
            self.list_roi_regions_btn.setEnabled(False)
            self.label_value_input.setEnabled(False)
        else:  # subcortical
            self.volume_atlas_combo.setEnabled(False)
            self.refresh_volume_atlases_btn.setEnabled(False)
            self.list_volume_regions_btn.setEnabled(False)
            self.volume_label_value_input.setEnabled(False)
        
        # Disable focality options if visible
        if self.focality_group.isVisible():
            self.adaptive_focality_checkbox.setEnabled(False)
            self.nonroi_percentage_input.setEnabled(False)
            self.roi_percentage_input.setEnabled(False)
            self.threshold_input.setEnabled(False)
            self.nonroi_method_combo.setEnabled(False)
            if self.nonroi_method_combo.currentData() == "specific":
                if self.roi_method_spherical.isChecked():
                    self.nonroi_x_input.setEnabled(False)
                    self.nonroi_y_input.setEnabled(False)
                    self.nonroi_z_input.setEnabled(False)
                    self.nonroi_radius_input.setEnabled(False)
                elif self.roi_method_cortical.isChecked():
                    self.nonroi_atlas_combo.setEnabled(False)
                    self.nonroi_hemi_combo.setEnabled(False)
                    self.list_nonroi_regions_btn.setEnabled(False)
                    self.nonroi_label_input.setEnabled(False)
                else:  # subcortical
                    self.nonroi_volume_atlas_combo.setEnabled(False)
                    self.list_nonroi_volume_regions_btn.setEnabled(False)
                    self.nonroi_volume_label_input.setEnabled(False)

        self.n_multistart_input.setEnabled(False)
        self.max_iterations_input.setEnabled(False)
        self.population_size_input.setEnabled(False)
        self.cpus_input.setEnabled(False)
        self.tolerance_input.setEnabled(False)
        self.mutation_min_input.setEnabled(False)
        self.mutation_max_input.setEnabled(False)
        self.recombination_input.setEnabled(False)
        self.detailed_results_checkbox.setEnabled(False)
        self.visualize_skin_checkbox.setEnabled(False)
        
        # Keep debug checkbox enabled during processing
        if hasattr(self, 'console_widget') and hasattr(self.console_widget, 'debug_checkbox'):
            self.console_widget.debug_checkbox.setEnabled(True)

    def enable_controls(self):
        """Enable all input controls after optimization."""
        # Enable subject selection
        self.subject_list.setEnabled(True)
        self.refresh_subjects_btn.setEnabled(True)
        self.select_all_subjects_btn.setEnabled(True)
        self.clear_subjects_btn.setEnabled(True)
        
        # Enable optimization parameters
        self.goal_combo.setEnabled(True)
        self.postproc_combo.setEnabled(True)
        self.eeg_net_combo.setEnabled(True)
        self.refresh_eeg_nets_btn.setEnabled(True)
        
        # Enable electrode parameters
        self.current_input.setEnabled(True)
        self.electrode_shape_rect.setEnabled(True)
        self.electrode_shape_ellipse.setEnabled(True)
        self.dimensions_input.setEnabled(True)
        self.thickness_input.setEnabled(True)
        
        # Enable simulation options
        self.run_final_electrode_simulation_checkbox.setEnabled(True)
        self.run_mapped_simulation_checkbox.setEnabled(True)
        
        # Enable ROI method selection
        self.roi_method_spherical.setEnabled(True)
        self.roi_method_cortical.setEnabled(True)
        self.roi_method_subcortical.setEnabled(True)
        
        # Enable ROI inputs based on method
        if self.roi_method_spherical.isChecked():
            self.roi_x_input.setEnabled(True)
            self.roi_y_input.setEnabled(True)
            self.roi_z_input.setEnabled(True)
            self.roi_radius_input.setEnabled(True)
            self.view_t1_btn.setEnabled(True)
        elif self.roi_method_cortical.isChecked():
            self.atlas_combo.setEnabled(True)
            self.roi_hemi_combo.setEnabled(True)
            self.refresh_atlases_btn.setEnabled(True)
            self.list_roi_regions_btn.setEnabled(True)
            self.label_value_input.setEnabled(True)
        else:  # subcortical
            self.volume_atlas_combo.setEnabled(True)
            self.refresh_volume_atlases_btn.setEnabled(True)
            self.list_volume_regions_btn.setEnabled(True)
            self.volume_label_value_input.setEnabled(True)
        
        # Enable focality options if visible
        if self.focality_group.isVisible():
            self.adaptive_focality_checkbox.setEnabled(True)
            self.nonroi_percentage_input.setEnabled(True)
            self.roi_percentage_input.setEnabled(True)
            self.threshold_input.setEnabled(True)
            self.nonroi_method_combo.setEnabled(True)
            if self.nonroi_method_combo.currentData() == "specific":
                if self.roi_method_spherical.isChecked():
                    self.nonroi_x_input.setEnabled(True)
                    self.nonroi_y_input.setEnabled(True)
                    self.nonroi_z_input.setEnabled(True)
                    self.nonroi_radius_input.setEnabled(True)
                elif self.roi_method_cortical.isChecked():
                    self.nonroi_atlas_combo.setEnabled(True)
                    self.nonroi_hemi_combo.setEnabled(True)
                    self.list_nonroi_regions_btn.setEnabled(True)
                    self.nonroi_label_input.setEnabled(True)
                else:  # subcortical
                    self.nonroi_volume_atlas_combo.setEnabled(True)
                    self.list_nonroi_volume_regions_btn.setEnabled(True)
                    self.nonroi_volume_label_input.setEnabled(True)

        self.n_multistart_input.setEnabled(True)
        self.max_iterations_input.setEnabled(True)
        self.population_size_input.setEnabled(True)
        self.cpus_input.setEnabled(True)
        self.tolerance_input.setEnabled(True)
        self.mutation_min_input.setEnabled(True)
        self.mutation_max_input.setEnabled(True)
        self.recombination_input.setEnabled(True)
        self.detailed_results_checkbox.setEnabled(True)
        self.visualize_skin_checkbox.setEnabled(True)

    def optimization_finished_early_due_to_error(self):
        """Resets UI controls if optimization cannot start due to an error."""
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls() # Re-enable all controls
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

    def _run_adaptive_focality_optimization(self, subject_id, roi_params, postproc, eeg_net,
                                          electrode_current, electrode_shape, dimensions, thickness, env, base_cmd):
        """Run adaptive focality optimization: first run mean optimization to get achievable intensity,
        then calculate adaptive thresholds and run focality optimization."""
        
        try:
            # Step 1: Run mean optimization to get achievable intensity
            self.update_output("🔄 Running adaptive focality optimization...")
            self.update_output("📊 Step 1/2: Finding achievable intensity with mean optimization")
            
            # Store parameters for later use
            self.adaptive_params = {
                'subject_id': subject_id,
                'roi_params': roi_params,
                'postproc': postproc,
                'eeg_net': eeg_net,
            'electrode_current': electrode_current,
            'electrode_shape': electrode_shape,
            'dimensions': dimensions,
            'thickness': thickness,
            'env': env,
                'base_cmd': base_cmd
            }
            
            # Initialize achievable intensity tracking
            self.achievable_intensity = None
            
            # Build mean optimization command
            mean_cmd = base_cmd + [
                "--roi-method", roi_params['method'],
                "--goal", "mean",
                "--postproc", postproc
            ]
            
            # Add mapping options to mean command
            if self.run_mapped_simulation_checkbox.isChecked():
                mean_cmd.extend(["--enable-mapping", "--eeg-net", eeg_net])
                # When run_mapped_simulation is checked, we always run the mapping simulation
            
            # Run mean optimization with enhanced output monitoring
            self.optimization_thread = FlexSearchThread(mean_cmd, env)
            self.optimization_thread.output_signal.connect(self._process_mean_optimization_output)
            self.optimization_thread.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
            self.optimization_thread.finished.connect(self._on_mean_optimization_finished_enhanced)
            self.optimization_thread.start()
            
            return True
            
        except Exception as e:
            self.update_output(f"❌ Error in adaptive focality optimization: {str(e)}", 'error')
            return False
    
    def _process_mean_optimization_output(self, line, message_type):
        """Process mean optimization output to extract achievable intensity in real-time."""
        # Display the output normally
        self.update_output(line, message_type)
        
        # Look for the final goal function value which represents achievable intensity
        import re
        
        # Look for patterns that indicate the achievable intensity
        goal_value_match = re.search(r'Goal function value.*?:\s*([+-]?[\d\.-]+)', line)
        if goal_value_match:
            # The goal function value is negative (since we maximize by minimizing negative)
            goal_value = float(goal_value_match.group(1))
            self.achievable_intensity = -goal_value  # Convert back to positive
            self.update_output(f"🎯 Detected achievable intensity: {self.achievable_intensity:.3f} V/m", 'info')
        
        # Also look for final goal function value
        final_goal_match = re.search(r'Final goal function value:\s*([+-]?[\d\.-]+)', line)
        if final_goal_match:
            final_goal_value = float(final_goal_match.group(1))
            self.achievable_intensity = -final_goal_value  # Convert back to positive
            self.update_output(f"🎯 Final achievable intensity: {self.achievable_intensity:.3f} V/m", 'info')
        
        # Look for median fields per ROI which contains the achievable intensity
        # Pattern: |max_TI | 3.80e-01 |
        median_roi_match = re.search(r'\|max_TI\s+\|\s*([\d\.-]+)(?:e([+-]?\d+))?\s*\|', line)
        if median_roi_match:
            base_value = float(median_roi_match.group(1))
            exponent = int(median_roi_match.group(2)) if median_roi_match.group(2) else 0
            roi_intensity = base_value * (10 ** exponent)
            if roi_intensity > 0:  # Only use positive values
                self.achievable_intensity = roi_intensity
                self.update_output(f"🎯 ROI median intensity captured: {self.achievable_intensity:.3f} V/m", 'info')
        
        # Alternative pattern without table formatting
        alt_median_match = re.search(r'max_TI\s+\|\s*([\d\.-]+)(?:e([+-]?\d+))?', line)
        if alt_median_match and not median_roi_match:  # Only if main pattern didn't match
            base_value = float(alt_median_match.group(1))
            exponent = int(alt_median_match.group(2)) if alt_median_match.group(2) else 0
            roi_intensity = base_value * (10 ** exponent)
            if roi_intensity > 0:  # Only use positive values
                self.achievable_intensity = roi_intensity
                self.update_output(f"🎯 ROI intensity captured: {self.achievable_intensity:.3f} V/m", 'info')
    
    def _on_mean_optimization_finished_enhanced(self):
        """Enhanced handler for mean optimization completion using stored parameters."""
        
        try:
            # Get stored parameters
            params = self.adaptive_params
            subject_id = params['subject_id']
            roi_params = params['roi_params']
            postproc = params['postproc']
            eeg_net = params['eeg_net']
            electrode_current = params['electrode_current']
            electrode_shape = params['electrode_shape']
            dimensions = params['dimensions']
            thickness = params['thickness']
            env = params['env']
            base_cmd = params['base_cmd']
            
            # Check if we captured the achievable intensity
            if self.achievable_intensity is None or self.achievable_intensity <= 0:
                # Fallback: try to extract from files with corrected directory naming
                self.achievable_intensity = self._extract_achievable_intensity_from_files(subject_id, roi_params, postproc)
            
            if self.achievable_intensity is None or self.achievable_intensity <= 0:
                self.update_output("❌ Could not determine achievable intensity from mean optimization", 'error')
                self.optimization_finished()
                return
            
            self.update_output(f"✅ Mean optimization completed. Achievable intensity: {self.achievable_intensity:.3f} V/m")
            
            # Step 2: Calculate adaptive thresholds
            nonroi_percentage = self.nonroi_percentage_input.value() / 100.0
            roi_percentage = self.roi_percentage_input.value() / 100.0
            
            nonroi_threshold = nonroi_percentage * self.achievable_intensity
            roi_threshold = roi_percentage * self.achievable_intensity
            
            self.update_output(f"🎯 Step 2/2: Running focality optimization with adaptive thresholds")
            self.update_output(f"   Non-ROI threshold: {nonroi_threshold:.3f} V/m ({nonroi_percentage*100:.0f}%)")
            self.update_output(f"   ROI threshold: {roi_threshold:.3f} V/m ({roi_percentage*100:.0f}%)")
            
            # Build focality optimization command with adaptive thresholds
            adaptive_thresholds = f"{nonroi_threshold:.3f},{roi_threshold:.3f}"
            nonroi_method = self.nonroi_method_combo.currentData()
            
            focality_cmd = base_cmd + [
                "--roi-method", roi_params['method'],
                "--goal", "focality",
                "--postproc", postproc,
                "--non-roi-method", nonroi_method,
                "--thresholds", adaptive_thresholds
            ]
            
            # Add mapping options to focality command
            if self.run_mapped_simulation_checkbox.isChecked():
                focality_cmd.extend(["--enable-mapping", "--eeg-net", eeg_net])
                # When run_mapped_simulation is checked, we always run the mapping simulation
                    
            # Add non-ROI specific parameters if needed
            if nonroi_method == "specific":
                self._add_nonroi_parameters(env, roi_params, subject_id)
            
            # Run focality optimization with adaptive thresholds
            self.optimization_thread = FlexSearchThread(focality_cmd, env)
            self.optimization_thread.output_signal.connect(self.update_output)
            self.optimization_thread.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
            self.optimization_thread.finished.connect(self.optimization_finished)
            self.optimization_thread.start()
            
        except Exception as e:
            self.update_output(f"❌ Error calculating adaptive thresholds: {str(e)}", 'error')
            self.optimization_finished()
    
    def _add_nonroi_parameters(self, env, roi_params, subject_id):
        """Add non-ROI specific parameters to environment."""
        if roi_params['method'] == "spherical":
            env['NON_ROI_X'] = str(self.nonroi_x_input.value())
            env['NON_ROI_Y'] = str(self.nonroi_y_input.value())
            env['NON_ROI_Z'] = str(self.nonroi_z_input.value())
            env['NON_ROI_RADIUS'] = str(self.nonroi_radius_input.value())
            env['USE_MNI_COORDS_NON_ROI'] = env.get('USE_MNI_COORDS', 'false')
        elif roi_params['method'] == "atlas":
            nonroi_atlas_display = self.nonroi_atlas_combo.currentText()
            nonroi_atlas_base_name = self.atlas_display_map.get(nonroi_atlas_display, nonroi_atlas_display)
            
            if '_' in nonroi_atlas_base_name:
                nonroi_atlas_type = nonroi_atlas_base_name.split('_', 1)[-1]
            else:
                nonroi_atlas_type = nonroi_atlas_base_name
            
            nonroi_atlas_name_for_env = f"{subject_id}_{nonroi_atlas_type}"
            nonroi_hemi_for_env = "lh" if self.nonroi_hemi_combo.currentIndex() == 0 else "rh"
            
            script_project_dir = env['PROJECT_DIR']
            seg_dir_for_env = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
            nonroi_atlas_path_for_env = os.path.join(seg_dir_for_env, f'{nonroi_hemi_for_env}.{nonroi_atlas_name_for_env}.annot')
            
            env['NON_ROI_ATLAS_PATH'] = nonroi_atlas_path_for_env
            env['NON_ROI_HEMISPHERE'] = nonroi_hemi_for_env
            env['NON_ROI_LABEL'] = str(self.nonroi_label_input.value())
        elif roi_params['method'] == "subcortical":
            nonroi_volume_atlas_display = self.nonroi_volume_atlas_combo.currentText()
            nonroi_volume_atlas_base_name = self.volume_atlas_display_map.get(nonroi_volume_atlas_display, nonroi_volume_atlas_display)
            
            script_project_dir = env['PROJECT_DIR']
            atlas_dir_for_env = os.path.join(script_project_dir, 'assets', 'atlas')
            nonroi_volume_atlas_path_for_env = os.path.join(atlas_dir_for_env, nonroi_volume_atlas_base_name)
            
            env['VOLUME_NON_ROI_ATLAS_PATH'] = nonroi_volume_atlas_path_for_env
            env['VOLUME_NON_ROI_LABEL'] = str(self.nonroi_volume_label_input.value())
    
    def _on_mean_optimization_finished(self, subject_id, roi_params, postproc, eeg_net,
                                     electrode_current, electrode_shape, dimensions, thickness, env, base_cmd):
        """Handle completion of mean optimization and start focality optimization with adaptive thresholds."""
        
        try:
            # Extract achievable intensity from mean optimization results
            achievable_intensity = self._extract_achievable_intensity(subject_id, roi_params)
            
            if achievable_intensity is None:
                self.update_output("❌ Could not determine achievable intensity from mean optimization", 'error')
                self.optimization_finished()
                return
            
            self.update_output(f"✅ Mean optimization completed. Achievable intensity: {achievable_intensity:.3f} V/m")
            
            # Step 2: Calculate adaptive thresholds
            nonroi_percentage = self.nonroi_percentage_input.value() / 100.0
            roi_percentage = self.roi_percentage_input.value() / 100.0
            
            nonroi_threshold = nonroi_percentage * achievable_intensity
            roi_threshold = roi_percentage * achievable_intensity
            
            self.update_output(f"🎯 Step 2/2: Running focality optimization with adaptive thresholds")
            self.update_output(f"   Non-ROI threshold: {nonroi_threshold:.3f} V/m ({nonroi_percentage*100:.0f}%)")
            self.update_output(f"   ROI threshold: {roi_threshold:.3f} V/m ({roi_percentage*100:.0f}%)")
            
            # Build focality optimization command with adaptive thresholds
            adaptive_thresholds = f"{nonroi_threshold:.3f},{roi_threshold:.3f}"
            nonroi_method = self.nonroi_method_combo.currentData()
            
            focality_cmd = base_cmd + [
                "--roi-method", roi_params['method'],
                "--goal", "focality",
                "--postproc", postproc,
                "--non-roi-method", nonroi_method,
                "--thresholds", adaptive_thresholds
            ]
            
            # Add mapping options to focality command
            if self.run_mapped_simulation_checkbox.isChecked():
                focality_cmd.extend(["--enable-mapping", "--eeg-net", eeg_net])
                # When run_mapped_simulation is checked, we always run the mapping simulation
                    
            # Add non-ROI specific parameters if needed
            if nonroi_method == "specific":
                if roi_params['method'] == "spherical":
                    env['NON_ROI_X'] = str(self.nonroi_x_input.value())
                    env['NON_ROI_Y'] = str(self.nonroi_y_input.value())
                    env['NON_ROI_Z'] = str(self.nonroi_z_input.value())
                    env['NON_ROI_RADIUS'] = str(self.nonroi_radius_input.value())
                    env['USE_MNI_COORDS_NON_ROI'] = env.get('USE_MNI_COORDS', 'false')
                elif roi_params['method'] == "atlas":
                    nonroi_atlas_display = self.nonroi_atlas_combo.currentText()
                    nonroi_atlas_base_name = self.atlas_display_map.get(nonroi_atlas_display, nonroi_atlas_display)
                    
                    if '_' in nonroi_atlas_base_name:
                        nonroi_atlas_type = nonroi_atlas_base_name.split('_', 1)[-1]
                    else:
                        nonroi_atlas_type = nonroi_atlas_base_name
                    
                    nonroi_atlas_name_for_env = f"{subject_id}_{nonroi_atlas_type}"
                    nonroi_hemi_for_env = "lh" if self.nonroi_hemi_combo.currentIndex() == 0 else "rh"
                    
                    script_project_dir = env['PROJECT_DIR']
                    seg_dir_for_env = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
                    nonroi_atlas_path_for_env = os.path.join(seg_dir_for_env, f'{nonroi_hemi_for_env}.{nonroi_atlas_name_for_env}.annot')
                    
                    env['NON_ROI_ATLAS_PATH'] = nonroi_atlas_path_for_env
                    env['NON_ROI_HEMISPHERE'] = nonroi_hemi_for_env
                    env['NON_ROI_LABEL'] = str(self.nonroi_label_input.value())
                elif roi_params['method'] == "subcortical":
                    nonroi_volume_atlas_display = self.nonroi_volume_atlas_combo.currentText()
                    nonroi_volume_atlas_base_name = self.volume_atlas_display_map.get(nonroi_volume_atlas_display, nonroi_volume_atlas_display)
                    
                    script_project_dir = env['PROJECT_DIR']
                    atlas_dir_for_env = os.path.join(script_project_dir, 'assets', 'atlas')
                    nonroi_volume_atlas_path_for_env = os.path.join(atlas_dir_for_env, nonroi_volume_atlas_base_name)
                    
                    env['VOLUME_NON_ROI_ATLAS_PATH'] = nonroi_volume_atlas_path_for_env
                    env['VOLUME_NON_ROI_LABEL'] = str(self.nonroi_volume_label_input.value())
            
            # Run focality optimization with adaptive thresholds
            self.optimization_thread = FlexSearchThread(focality_cmd, env)
            self.optimization_thread.output_signal.connect(self.update_output)
            self.optimization_thread.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
            self.optimization_thread.finished.connect(self.optimization_finished)
            self.optimization_thread.start()
            
        except Exception as e:
            self.update_output(f"❌ Error calculating adaptive thresholds: {str(e)}", 'error')
            self.optimization_finished()
    
    def _extract_achievable_intensity_from_files(self, subject_id, roi_params, postproc):
        """Extract achievable intensity from mean optimization result files (fallback method)."""
        try:
            # Construct path to mean optimization results using correct naming convention
            project_dir = os.environ.get('PROJECT_DIR')
            if not project_dir:
                return None
            
            # Convert postproc to shorter format to match actual directory names
            postproc_map = {
                "max_TI": "maxTI",
                "dir_TI_normal": "normalTI", 
                "dir_TI_tangential": "tangentialTI"
            }
            postproc_short = postproc_map.get(postproc, postproc)
                
            # Build ROI directory name for mean optimization using correct convention
            if roi_params['method'] == "spherical":
                # Format: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
                x, y, z = roi_params['center']
                radius = roi_params['radius']
                roi_dirname = f"sphere_x{x}y{y}z{z}r{radius}_mean_{postproc_short}"
            elif roi_params['method'] == "atlas":
                atlas_name = roi_params['atlas'].split('_')[-1] if '_' in roi_params['atlas'] else roi_params['atlas']
                hemisphere = "lh" if self.roi_hemi_combo.currentIndex() == 0 else "rh"
                roi_dirname = f"{hemisphere}_{atlas_name}_{roi_params['region']}_mean_{postproc_short}"
            elif roi_params['method'] == "subcortical":
                volume_atlas_name = roi_params['volume_atlas'].replace('.nii.gz', '').replace('.nii', '')
                roi_dirname = f"subcortical_{volume_atlas_name}_{roi_params['volume_label']}_mean_{postproc_short}"
            else:
                return None
            
            # Look for optimization summary file
            results_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', const.DIR_FLEX_SEARCH, roi_dirname)
            summary_file = os.path.join(results_dir, 'optimization_summary.txt')
            
            self.update_output(f"🔍 Looking for summary file: {summary_file}", 'info')
            
            if not os.path.exists(summary_file):
                self.update_output(f"⚠️ Summary file not found, checking directory contents...", 'warning')
                
                # List directory contents to help debug
                if os.path.exists(results_dir):
                    files = os.listdir(results_dir)
                    self.update_output(f"📁 Directory contents: {files}", 'info')
                else:
                    parent_dir = os.path.dirname(results_dir)
                    if os.path.exists(parent_dir):
                        subdirs = [d for d in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, d))]
                        self.update_output(f"📁 Available subdirectories: {subdirs}", 'info')
                
                return None
            
            # Parse summary file to extract achievable intensity
            with open(summary_file, 'r') as f:
                content = f.read()
                
                # Look for the final function value which represents the achievable mean intensity
                import re
                match = re.search(r'Final function value:\s*([+-]?[\d\.-]+)', content)
                if match:
                    # The function value is negative (since we maximize by minimizing negative)
                    return -float(match.group(1))
                
                # Alternative patterns
                match = re.search(r'Optimization result:\s*([+-]?[\d\.-]+)', content)
                if match:
                    return -float(match.group(1))
                    
                match = re.search(r'Best objective value:\s*([+-]?[\d\.-]+)', content)
                if match:
                    return -float(match.group(1))
            
            return None
            
        except Exception as e:
            self.update_output(f"❌ Error extracting achievable intensity from files: {str(e)}", 'error')
            return None
