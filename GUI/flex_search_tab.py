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
from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite

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
        """Initialize the flex search tab."""
        super(FlexSearchTab, self).__init__(parent)
        self.parent = parent
        self.optimization_running = False
        self.optimization_process = None
        
        # Initialize data structures
        self.subjects = []
        self.eeg_nets = {}
        self.atlases = {}
        
        # Initialize all widgets that might be referenced before setup_ui
        self.subject_combo = QtWidgets.QComboBox()
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
        
        self.refresh_eeg_nets_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_eeg_nets_btn.setMaximumWidth(100)
        
        self.refresh_atlases_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_atlases_btn.setMaximumWidth(100)
        
        # Initialize labels
        self.subject_label = QtWidgets.QLabel("Subject(s):")
        self.goal_label = QtWidgets.QLabel("Optimization Goal:")
        self.postproc_label = QtWidgets.QLabel("Post-processing Method:")
        self.roi_method_label = QtWidgets.QLabel("ROI Definition Method:")
        self.radius_label = QtWidgets.QLabel("Electrode Radius (mm):")
        self.current_label = QtWidgets.QLabel("Electrode Current (mA):")
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
        self.run_optimized_simulation_checkbox = QtWidgets.QCheckBox("✓ Run simulation with optimized electrodes")
        self.run_optimized_simulation_checkbox.setChecked(False)
        
        self.enable_mapping_checkbox = QtWidgets.QCheckBox("✓ Enable electrode mapping to EEG net positions")
        self.enable_mapping_checkbox.setChecked(False)
        
        self.run_mapped_simulation_checkbox = QtWidgets.QCheckBox("Run simulation with mapped electrodes")
        self.run_mapped_simulation_checkbox.setChecked(False)
        
        self.conservative_mode_checkbox = QtWidgets.QCheckBox("✓ Enable conservative mode")
        self.conservative_mode_checkbox.setChecked(False)
        
        self.quiet_mode_checkbox = QtWidgets.QCheckBox("✓ Hide optimization steps")
        self.quiet_mode_checkbox.setChecked(True)
        
        # Initialize radio buttons
        self.roi_method_spherical = QtWidgets.QRadioButton("Spherical (coordinates and radius)")
        self.roi_method_cortical = QtWidgets.QRadioButton("Cortical (atlas-based parcellation)")
        self.roi_method_spherical.setChecked(True)
        
        # Initialize spinboxes and line edits
        self.radius_input = QtWidgets.QDoubleSpinBox()
        self.radius_input.setRange(1, 30); self.radius_input.setValue(10); self.radius_input.setDecimals(1)
        
        self.current_input = QtWidgets.QDoubleSpinBox()
        self.current_input.setRange(0.1, 100); self.current_input.setValue(2); self.current_input.setDecimals(1)
        
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
        
        self.roi_x_input = QtWidgets.QDoubleSpinBox(); self.roi_x_input.setRange(-150, 150); self.roi_x_input.setValue(0); self.roi_x_input.setDecimals(1)
        self.roi_y_input = QtWidgets.QDoubleSpinBox(); self.roi_y_input.setRange(-150, 150); self.roi_y_input.setValue(0); self.roi_y_input.setDecimals(1)
        self.roi_z_input = QtWidgets.QDoubleSpinBox(); self.roi_z_input.setRange(-150, 150); self.roi_z_input.setValue(0); self.roi_z_input.setDecimals(1)
        self.roi_radius_input = QtWidgets.QDoubleSpinBox(); self.roi_radius_input.setRange(1, 50); self.roi_radius_input.setValue(10); self.roi_radius_input.setDecimals(1)
        
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
        
        self.nonroi_method_combo = QtWidgets.QComboBox()
        self.nonroi_method_combo.addItem("Everything Else (default)", "everything_else")
        self.nonroi_method_combo.addItem("Specific Region", "specific")
        
        # Non-ROI inputs (spherical)
        self.nonroi_x_input = QtWidgets.QDoubleSpinBox(); self.nonroi_x_input.setRange(-150,150); self.nonroi_x_input.setDecimals(1)
        self.nonroi_y_input = QtWidgets.QDoubleSpinBox(); self.nonroi_y_input.setRange(-150,150); self.nonroi_y_input.setDecimals(1)
        self.nonroi_z_input = QtWidgets.QDoubleSpinBox(); self.nonroi_z_input.setRange(-150,150); self.nonroi_z_input.setDecimals(1)
        self.nonroi_radius_input = QtWidgets.QDoubleSpinBox(); self.nonroi_radius_input.setRange(1,50); self.nonroi_radius_input.setDecimals(1)
        
        # Non-ROI inputs (atlas)
        self.nonroi_hemi_combo = QtWidgets.QComboBox(); self.nonroi_hemi_combo.addItems(["Left (lh)", "Right (rh)"])
        self.nonroi_label_input = QtWidgets.QSpinBox(); self.nonroi_label_input.setRange(1,10000)
        self.list_nonroi_regions_btn = QtWidgets.QPushButton("List Regions")
        self.list_nonroi_regions_btn.setMaximumWidth(120)
        
        # ROI hemisphere combo and list regions button (for cortical ROI)
        self.roi_hemi_combo = QtWidgets.QComboBox(); self.roi_hemi_combo.addItems(["Left (lh)", "Right (rh)"])
        self.list_roi_regions_btn = QtWidgets.QPushButton("List Regions")
        self.list_roi_regions_btn.setMaximumWidth(120)

        # Set up the UI
        self.setup_ui()
        
        # Connect signals after UI setup (critical widgets must exist)
        self.refresh_subjects_btn.clicked.connect(self.find_available_subjects)
        self.refresh_eeg_nets_btn.clicked.connect(self.find_available_eeg_nets)
        self.refresh_atlases_btn.clicked.connect(self.find_available_atlases)
        self.list_roi_regions_btn.clicked.connect(self._list_roi_regions)
        self.list_nonroi_regions_btn.clicked.connect(self._list_nonroi_regions)

        self.goal_combo.currentIndexChanged.connect(self._update_focality_visibility)
        self.enable_mapping_checkbox.toggled.connect(self._update_mapping_options)
        self.subject_combo.currentIndexChanged.connect(self.on_subject_changed)
        self.nonroi_method_combo.currentIndexChanged.connect(self._update_nonroi_stacked)
        self.roi_method_spherical.toggled.connect(self.update_roi_method)
        self.roi_method_spherical.toggled.connect(self._update_nonroi_stacked)
        
        # Find available subjects (which will trigger finding EEG nets and atlases)
        self.find_available_subjects()

    def setup_ui(self):
        """Set up the user interface for the flex-search tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        title_label = QtWidgets.QLabel("Flex Search Electrode Optimization")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        description_label = QtWidgets.QLabel(
            "Find optimal electrode positions for temporal interference stimulation targeting a specific ROI."
        )
        description_label.setWordWrap(True)
        scroll_layout.addWidget(title_label)
        scroll_layout.addWidget(description_label)
        scroll_layout.addWidget(QtWidgets.QLabel(""))

        top_row_layout = QtWidgets.QHBoxLayout()

        basic_params_group = QtWidgets.QGroupBox("Basic Parameters")
        basic_params_layout = QtWidgets.QFormLayout(basic_params_group)
        
        subject_controls_widget = QtWidgets.QWidget()
        subject_controls_inner_layout = QtWidgets.QHBoxLayout(subject_controls_widget)
        subject_controls_inner_layout.addWidget(self.subject_combo)
        subject_controls_inner_layout.addWidget(self.refresh_subjects_btn)
        subject_controls_inner_layout.addStretch()
        basic_params_layout.addRow(self.subject_label, subject_controls_widget)
        
        self.goal_combo.setMaximumWidth(350)
        basic_params_layout.addRow(self.goal_label, self.goal_combo)
        
        self.postproc_combo.setMaximumWidth(350)
        basic_params_layout.addRow(self.postproc_label, self.postproc_combo)

        basic_params_layout.addRow(self.run_optimized_simulation_checkbox)
        top_row_layout.addWidget(basic_params_group, 1)

        self.electrode_params_group = QtWidgets.QGroupBox("Electrode Parameters")
        electrode_params_layout = QtWidgets.QFormLayout(self.electrode_params_group)
        electrode_params_layout.addRow(self.radius_label, self.radius_input)
        electrode_params_layout.addRow(self.current_label, self.current_input)
        top_row_layout.addWidget(self.electrode_params_group, 1)
        
        scroll_layout.addLayout(top_row_layout)

        self.mapping_group = QtWidgets.QGroupBox("Electrode Mapping Options (Optional)")
        mapping_layout = QtWidgets.QFormLayout(self.mapping_group)
        
        mapping_help_label = QtWidgets.QLabel(
            "⚠️ Electrode mapping finds the nearest EEG net electrodes to the optimized positions.\n"
            "This feature is DISABLED by default as it may increase computation time and memory usage."
        )
        mapping_help_label.setStyleSheet("font-size: 11px; color: #666666; font-style: italic; padding: 5px; background-color: #f5f5f5; border-radius: 3px;")
        mapping_help_label.setWordWrap(True)
        mapping_layout.addRow(mapping_help_label)
        
        mapping_layout.addRow(self.enable_mapping_checkbox)

        eeg_net_controls_inner_layout = QtWidgets.QHBoxLayout()
        eeg_net_controls_inner_layout.addWidget(self.eeg_net_combo)
        eeg_net_controls_inner_layout.addWidget(self.refresh_eeg_nets_btn)
        eeg_net_controls_inner_layout.addStretch()
        self.eeg_net_widget.setLayout(eeg_net_controls_inner_layout)
        self.eeg_net_widget.setVisible(False)
        self.eeg_net_label.setVisible(False)
        mapping_layout.addRow(self.eeg_net_label, self.eeg_net_widget)
        
        self.run_mapped_simulation_checkbox.setVisible(False)
        mapping_layout.addRow(self.run_mapped_simulation_checkbox)
        scroll_layout.addWidget(self.mapping_group)

        self.roi_method_group = QtWidgets.QGroupBox("ROI Definition")
        roi_method_layout_main = QtWidgets.QVBoxLayout(self.roi_method_group)
        
        roi_method_radio_container = QtWidgets.QWidget()
        roi_method_radio_layout = QtWidgets.QHBoxLayout(roi_method_radio_container)
        roi_method_radio_layout.addWidget(self.roi_method_spherical)
        roi_method_radio_layout.addWidget(self.roi_method_cortical)
        roi_method_radio_layout.addStretch()
        
        roi_method_layout_main.addWidget(self.roi_method_label)
        roi_method_layout_main.addWidget(roi_method_radio_container)
        
        # Spherical ROI inputs
        self.spherical_roi_widget = QtWidgets.QWidget()
        spherical_roi_layout = QtWidgets.QFormLayout(self.spherical_roi_widget)
        
        roi_coords_controls_widget = QtWidgets.QWidget()
        roi_coords_controls_layout = QtWidgets.QHBoxLayout(roi_coords_controls_widget)
        roi_coords_controls_layout.addWidget(QtWidgets.QLabel("X:"))
        roi_coords_controls_layout.addWidget(self.roi_x_input)
        roi_coords_controls_layout.addWidget(QtWidgets.QLabel("Y:"))
        roi_coords_controls_layout.addWidget(self.roi_y_input)
        roi_coords_controls_layout.addWidget(QtWidgets.QLabel("Z:"))
        roi_coords_controls_layout.addWidget(self.roi_z_input)
        spherical_roi_layout.addRow(self.roi_coords_label, roi_coords_controls_widget)
        spherical_roi_layout.addRow(self.roi_radius_label, self.roi_radius_input)
        self.roi_stacked_widget.addWidget(self.spherical_roi_widget)
        
        # Cortical ROI inputs
        self.cortical_roi_widget = QtWidgets.QWidget()
        cortical_roi_layout = QtWidgets.QFormLayout(self.cortical_roi_widget)
        
        atlas_controls_widget = QtWidgets.QWidget()
        atlas_controls_inner_layout = QtWidgets.QHBoxLayout(atlas_controls_widget)
        self.atlas_combo.setMaximumWidth(350)
        atlas_controls_inner_layout.addWidget(self.atlas_combo)
        atlas_controls_inner_layout.addWidget(self.roi_hemi_label)
        atlas_controls_inner_layout.addWidget(self.roi_hemi_combo)
        atlas_controls_inner_layout.addWidget(self.refresh_atlases_btn)
        atlas_controls_inner_layout.addWidget(self.list_roi_regions_btn)
        atlas_controls_inner_layout.addStretch()
        cortical_roi_layout.addRow(self.atlas_label, atlas_controls_widget)
        cortical_roi_layout.addRow(self.label_value_label, self.label_value_input)
        self.roi_stacked_widget.addWidget(self.cortical_roi_widget)
        
        roi_method_layout_main.addWidget(self.roi_stacked_widget)
        scroll_layout.addWidget(self.roi_method_group)

        # Focality Options group
        focality_layout = QtWidgets.QFormLayout(self.focality_group)
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
        self.nonroi_atlas_combo.setMaximumWidth(350)
        nonroi_atlas_controls_inner_layout.addWidget(self.nonroi_atlas_combo)
        nonroi_atlas_controls_inner_layout.addWidget(self.nonroi_hemi_label)
        nonroi_atlas_controls_inner_layout.addWidget(self.nonroi_hemi_combo)
        nonroi_atlas_controls_inner_layout.addWidget(self.list_nonroi_regions_btn)
        nonroi_atlas_controls_inner_layout.addStretch()
        nonroi_atlas_layout.addRow(self.nonroi_atlas_label, nonroi_atlas_controls_widget)
        nonroi_atlas_layout.addRow(self.nonroi_label_value_label, self.nonroi_label_input)
        self.nonroi_stacked.addWidget(self.nonroi_atlas_widget)
        
        focality_layout.addRow(QtWidgets.QLabel("Non-ROI Region (if 'Specific'):"), self.nonroi_stacked)
        scroll_layout.addWidget(self.focality_group)

        self.stability_group = QtWidgets.QGroupBox("Stability & Memory Options")
        stability_layout = QtWidgets.QFormLayout(self.stability_group)
        stability_help_label = QtWidgets.QLabel(
            "⚙️ These options help prevent crashes, manage resource usage, and control optimization speed.\n"
            "• Conservative mode: Uses minimal resources (if supported by backend). Not currently passed.\n"
            "• Max iterations: Lower = faster but potentially less optimal results.\n"
            "• Population size: Lower = less memory, potentially slower convergence. Higher = more memory, potentially faster convergence.\n"
            "• Number of CPUs: More CPUs can speed up parallelizable parts of the optimization.\n"
            "• Hide steps: Reduces output verbosity during optimization."
        )
        stability_help_label.setStyleSheet("font-size: 11px; color: #666666; font-style: italic; padding: 5px; background-color: #f5f5f5; border-radius: 3px;")
        stability_help_label.setWordWrap(True)
        stability_layout.addRow(stability_help_label) 
        stability_layout.addRow(self.conservative_mode_checkbox) 
        stability_layout.addRow(self.max_iterations_label, self.max_iterations_input)
        stability_layout.addRow(self.population_size_label, self.population_size_input)
        stability_layout.addRow(self.cpus_label, self.cpus_input)
        stability_layout.addRow(self.quiet_mode_checkbox) 
        scroll_layout.addWidget(self.stability_group)

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Console output section
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        self.output_text = QtWidgets.QTextEdit()
        self.output_text.setReadOnly(True); self.output_text.setMinimumHeight(200)
        self.output_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e; color: #f0f0f0;
                font-family: 'Consolas', 'Courier New', monospace; font-size: 13px;
                border: 1px solid #3c3c3c; border-radius: 5px; padding: 8px;
            }""")
        self.output_text.setAcceptRichText(True)
        
        console_layout = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(output_label)
        header_layout.addStretch()
        
        console_buttons_layout = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Run Optimization")
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
        self.stop_btn = QtWidgets.QPushButton("Stop Optimization")
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
        clear_btn = QtWidgets.QPushButton("Clear Console")
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
        
        console_buttons_layout.addWidget(self.run_btn); console_buttons_layout.addWidget(self.stop_btn)
        console_buttons_layout.addWidget(clear_btn)
        header_layout.addLayout(console_buttons_layout)
        console_layout.addLayout(header_layout)
        console_layout.addWidget(self.output_text)
        main_layout.addLayout(console_layout)

        # Connect run/stop/clear buttons
        self.run_btn.clicked.connect(self.run_optimization)
        self.stop_btn.clicked.connect(self.stop_optimization)
        clear_btn.clicked.connect(self.clear_console)
        
        # Initialize ROI method display and focality visibility
        self.update_roi_method(self.roi_method_spherical.isChecked())
        self._update_focality_visibility()
        self._update_nonroi_stacked()

    def find_available_subjects(self):
        self.subjects = []
        self.subject_combo.clear()
        self.output_text.clear()
        
        # Get project directory name from environment variable
        project_dir_name = os.environ.get('PROJECT_DIR_NAME')
        if not project_dir_name:
            self.output_text.append("Error: PROJECT_DIR_NAME environment variable is not set")
            self.output_text.append("Please set PROJECT_DIR_NAME to your project directory name")
            return
            
        # Construct project directory path
        project_dir = f"/mnt/{project_dir_name}"
        
        # Set PROJECT_DIR for other components that might need it
        os.environ['PROJECT_DIR'] = project_dir
        
        self.output_text.append(f"Looking for subjects in: {project_dir}")
        
        # Look in derivatives/SimNIBS directory for subjects
        simnibs_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS')
        if not os.path.isdir(simnibs_dir):
            self.output_text.append(f"Error: SimNIBS directory not found at: {simnibs_dir}")
            return
            
        # Look for subject directories with m2m_ prefix (matching shell script behavior)
        for subject_path in glob.glob(os.path.join(simnibs_dir, 'sub-*', 'm2m_*')):
            if os.path.isdir(subject_path):
                subject_id = os.path.basename(subject_path).replace('m2m_', '')
                self.subjects.append(subject_id)
                self.subject_combo.addItem(subject_id)
                
        # Console output: subjects found
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
                    self.output_text.append(f"Found {len(unique_atlases)} unique atlases for subject {subject_id}.")
                else:
                    self.output_text.append(f"No atlas files found for subject {subject_id}.")
            else:
                self.output_text.append(f"Segmentation directory not found for subject {subject_id}.")
        except Exception as e:
            self.output_text.append(f"Error scanning for atlas files: {str(e)}")
        # Also update non-ROI atlas combo
        self._update_nonroi_atlas_combo()

    def update_roi_method(self, checked):
        """Update the ROI method inputs based on selection."""
        if self.roi_method_spherical.isChecked():
            self.roi_stacked_widget.setCurrentIndex(0)
        else:
            self.roi_stacked_widget.setCurrentIndex(1)
    
    def run_optimization(self):
        """Run the flex-search optimization."""
        if self.optimization_running:
            self.update_output("Optimization already running. Please wait or stop the current run.")
            return
            
        # Validate inputs
        if not self.subject_combo.currentText():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a subject.")
            return
            
        if not self.eeg_net_combo.currentText():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select an EEG net.")
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
        else:  # cortical ROI
            if not self.atlas_combo.currentText():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select an atlas for ROI.")
                return
            if not self.label_value_input.value():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a region for ROI.")
                return
                
            roi_params = {
                'method': 'cortical',
                'atlas': self.atlas_combo.currentText(),
                'region': str(self.label_value_input.value())
            }
            
        # Get optimization parameters for easier access and clarity
        subject_id = self.subject_combo.currentText()
        goal = self.goal_combo.currentData()
        postproc = self.postproc_combo.currentData()
        eeg_net = self.eeg_net_combo.currentText()
        electrode_radius = self.radius_input.value()
        electrode_current = self.current_input.value()

        # Construct optimization output directory path (RESTORED)
        project_dir_for_opt_path = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_test')}" # Use a consistent way to get project_dir for this
        bids_subject_id = f"sub-{subject_id}"
        
        if roi_params['method'] == 'spherical':
            roi_coords_str = f"{roi_params['center'][0]:.1f}x{roi_params['center'][1]:.1f}y{roi_params['center'][2]:.1f}z_{roi_params['radius']:.1f}mm"
            opt_dir = os.path.join(project_dir_for_opt_path, 'derivatives', 'SimNIBS', bids_subject_id, 
                                 'flex-search', f'{roi_coords_str}_{goal}')
        else: # cortical
            atlas_name_for_dir = roi_params['atlas'] # This should be display name as per original logic for dir name
            region_id_for_dir = roi_params['region']
            opt_dir = os.path.join(project_dir_for_opt_path, 'derivatives', 'SimNIBS', bids_subject_id, 
                                 'flex-search', f'cortical_{atlas_name_for_dir}_{region_id_for_dir}_{goal}')
        
        # Check if directory exists and confirm overwrite (RESTORED)
        if os.path.exists(opt_dir):
            if not confirm_overwrite(self, opt_dir, "optimization output directory"):
                self.optimization_finished_early_due_to_error() # Ensure UI resets
                return

        # Show confirmation dialog (details string construction from previous step is mostly fine)
        # ... (details string should be built here, incorporating all relevant params including stability)
        details = (f"This will run flex-search optimization with the following parameters:\n\n" +
                   f"• Subject: {subject_id}\n" +
                   f"• EEG Net: {eeg_net}\n" +
                   f"• Optimization Goal: {self.goal_combo.currentText()} ({goal})\n" +
                   f"• Post-processing: {self.postproc_combo.currentText()} ({postproc})\n" +
                   f"• Electrode Radius: {electrode_radius} mm\n" +
                   f"• Electrode Current: {electrode_current} mA\n" +
                   f"• ROI Method: {'Spherical' if roi_params['method'] == 'spherical' else 'Cortical'}\n")
        if roi_params['method'] == 'spherical':
            details += (f"• ROI Center: ({roi_params['center'][0]}, {roi_params['center'][1]}, {roi_params['center'][2]}) mm\n" +
                        f"• ROI Radius: {roi_params['radius']} mm\n")
        else:
            details += (f"• ROI Atlas: {roi_params['atlas']}\n" +
                        f"• ROI Region: {roi_params['region']}\n")
        if self.enable_mapping_checkbox.isChecked():
            details += f"• Electrode Mapping: ✓ ENABLED\n"
            if self.run_mapped_simulation_checkbox.isChecked():
                details += f"• Mapping Simulation: ✓ ENABLED (runs additional simulation with mapped electrodes)\n"
            else:
                details += f"• Mapping Simulation: ✗ DISABLED (analysis only for mapped)\n"
        else:
            details += f"• Electrode Mapping: ✗ DISABLED (continuous optimization)\n"
        if self.run_optimized_simulation_checkbox.isChecked():
             details += f"• Post-Optimized Simulation: ✓ ENABLED (runs simulation with optimized continuous positions)\n"

        details += f"\nStability & Memory:\n"
        if self.conservative_mode_checkbox.isChecked():
            # details += f"• Conservative mode: ✓ ENABLED (Note: Not currently passed to backend)\n"
            pass # Not passed for now
        details += f"• Max Iterations: {self.max_iterations_input.value()}\n"
        details += f"• Population Size: {self.population_size_input.value()}\n"
        details += f"• Number of CPUs: {self.cpus_input.value()}\n"
        if self.quiet_mode_checkbox.isChecked():
            details += f"• Hide optimization steps: ✓ ENABLED\n"

        if not ConfirmationDialog.confirm(self, title="Confirm Optimization", message="Are you sure you want to start?", details=details):
            self.optimization_finished_early_due_to_error()
            return
            
        self.optimization_running = True
        self.run_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.disable_controls()

        # Prepare environment variables ( reinstated and verified)
        env = os.environ.copy()
        # Determine project_dir for env - this should be the actual SimNIBS project root for the scripts
        # The GUI's PROJECT_DIR_NAME might point to the BIDS root or similar, SimNIBS scripts often need PROJECT_DIR to be the SimNIBS output folder itself for the subject
        # Let's use the `project_dir_for_opt_path` as a base, assuming it correctly points to the parent of 'derivatives'
        # However, the original find_available_subjects set os.environ['PROJECT_DIR'] = /mnt/PROJECT_DIR_NAME.
        # This suggests flex-search.py expects PROJECT_DIR to be the root of the BIDS dataset.
        
        # Let's stick to the original logic for what PROJECT_DIR env var should be:
        gui_project_dir_name = os.environ.get('PROJECT_DIR_NAME') # From GUI launch env
        if gui_project_dir_name:
            env['PROJECT_DIR'] = f"/mnt/{gui_project_dir_name}" 
        else:
            # Fallback if not set - this was the previous robust finding logic
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
                env['PROJECT_DIR'] = "/mnt/BIDS_test" # Default if all else fails

        # Actual project_dir used for constructing atlas paths, etc. inside this function:
        # This should be the one derived for opt_dir, i.e., where 'derivatives' is a subfolder.
        # The env['PROJECT_DIR'] is for flex-search.py script's internal use.
        # Let's ensure `script_project_dir` refers to the one for path construction here.
        script_project_dir = env['PROJECT_DIR'] # Use the determined PROJECT_DIR for internal path construction

        env['SUBJECT_ID'] = subject_id
        if roi_params['method'] == "spherical":
            env['ROI_X'] = str(roi_params['center'][0])
            env['ROI_Y'] = str(roi_params['center'][1])
            env['ROI_Z'] = str(roi_params['center'][2])
            env['ROI_RADIUS'] = str(roi_params['radius'])
        else: # cortical
            atlas_display_for_env = roi_params['atlas']
            atlas_name_for_env = self.atlas_display_map.get(atlas_display_for_env, atlas_display_for_env)
            hemi_for_env = "lh" if self.roi_hemi_combo.currentIndex() == 0 else "rh"
            seg_dir_for_env = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
            atlas_path_for_env = os.path.join(seg_dir_for_env, f'{hemi_for_env}.{atlas_name_for_env}.annot')
            env['ATLAS_PATH'] = atlas_path_for_env
            env['SELECTED_HEMISPHERE'] = hemi_for_env
            env['ROI_LABEL'] = str(roi_params['region'])
        
        # Build the command
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        flex_search_py = os.path.join(script_dir, "flex-search", "flex-search.py")
        # ... (flex-search.py path verification - from previous, assumed correct)
        if not os.path.isfile(flex_search_py): # Simplified for brevity, original was more robust
            self.output_text.append(f"Error: flex-search.py not found at {flex_search_py}. Optimization cannot continue.")
            self.optimization_finished_early_due_to_error()
            return

        cmd = [
            "simnibs_python", flex_search_py,
            "--subject", subject_id,
            "--goal", goal, 
            "--postproc", postproc,
            "--eeg-net", eeg_net,
            "--radius", str(electrode_radius),
            "--current", str(electrode_current),
            "--roi-method", roi_params['method']
        ]

        # Mapping options
        if self.enable_mapping_checkbox.isChecked():
            cmd.append("--enable-mapping")
            if not self.run_mapped_simulation_checkbox.isChecked():
                cmd.append("--disable-mapping-simulation")
        
        # Independent option for running simulation with optimized (continuous) electrodes (RESTORED LOGIC)
        if self.run_optimized_simulation_checkbox.isChecked():
            cmd.append("--run-optimized-simulation")

        # Focality options (ensure using `goal` variable)
        if goal == "focality":
            thresholds = self.threshold_input.text().strip()
            nonroi_method = self.nonroi_method_combo.currentData()
            if not thresholds:
                self.output_text.append("Error: Please enter threshold(s) for focality.")
                self.optimization_finished_early_due_to_error()
                return
            cmd += ["--non-roi-method", nonroi_method, "--thresholds", thresholds]
            if nonroi_method == "specific":
                if roi_params['method'] == "spherical":
                    cmd += ["--non-roi-x", str(self.nonroi_x_input.value()), "--non-roi-y", str(self.nonroi_y_input.value()),
                            "--non-roi-z", str(self.nonroi_z_input.value()), "--non-roi-radius", str(self.nonroi_radius_input.value())]
                else: # atlas for non-ROI
                    nonroi_atlas_display = self.nonroi_atlas_combo.currentText()
                    nonroi_atlas_name = self.atlas_display_map.get(nonroi_atlas_display, nonroi_atlas_display)
                    nonroi_hemi = "lh" if self.nonroi_hemi_combo.currentIndex() == 0 else "rh"
                    nonroi_label_val = self.nonroi_label_input.value()
                    # Path for non-ROI atlas for the command line arg
                    nonroi_atlas_path_arg = os.path.join(script_project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                                     f'm2m_{subject_id}', 'segmentation', f'{nonroi_hemi}.{nonroi_atlas_name}.annot')
                    cmd += ["--non-roi-atlas", nonroi_atlas_path_arg, "--non-roi-hemisphere", nonroi_hemi, "--non-roi-label", str(nonroi_label_val)]
        
        # Stability and Memory options
        if self.quiet_mode_checkbox.isChecked(): cmd.append("--quiet")
        cmd.extend(["--max-iterations", str(self.max_iterations_input.value())])
        cmd.extend(["--population-size", str(self.population_size_input.value())])
        cmd.extend(["--cpus", str(self.cpus_input.value())])

        self.clear_console()
        self.output_text.append("Running optimization (this may take a while)...")
        self.output_text.append("Command: " + " ".join(cmd))
        self.output_text.append("Environment for subprocess will include:")
        for k, v in env.items():
            if k.startswith("ROI") or k in ['PROJECT_DIR', 'SUBJECT_ID', 'ATLAS_PATH', 'SELECTED_HEMISPHERE']:
                self.output_text.append(f"  {k}: {v}")

        if hasattr(self, 'parent') and self.parent: self.parent.set_tab_busy(self, True, stop_btn=self.stop_btn)
        
        self.optimization_process = FlexSearchThread(cmd, env)
        self.optimization_process.output_signal.connect(self.update_output)
        self.optimization_process.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
        self.optimization_process.finished.connect(self.optimization_finished)
        self.optimization_process.start()
    
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
        self.output_text.append(formatted_text)
        self.output_text.ensureCursorVisible()
        QtWidgets.QApplication.processEvents()
    
    def optimization_finished(self):
        """Handle the completion of the optimization process."""
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls()  # Re-enable all controls
        self.output_text.append("\nOptimization process completed.")
    
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
        
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    
    def on_subject_changed(self, index):
        """Handle subject selection change."""
        if index >= 0:
            self.find_available_eeg_nets()
            self.find_available_atlases()
    
    def _update_mapping_options(self):
        """Update visibility of mapping simulation options based on mapping checkbox."""
        is_mapping_enabled = self.enable_mapping_checkbox.isChecked()
        self.eeg_net_widget.setVisible(is_mapping_enabled)
        self.eeg_net_label.setVisible(is_mapping_enabled)
        self.run_mapped_simulation_checkbox.setVisible(is_mapping_enabled)
        if not is_mapping_enabled:
            self.run_mapped_simulation_checkbox.setChecked(False)

    def _update_focality_visibility(self):
        is_focality = self.goal_combo.currentData() == "focality"
        self.focality_group.setVisible(is_focality)
        # Default to 'everything_else' and collapse non-ROI region
        if is_focality:
            self.nonroi_method_combo.setCurrentIndex(0)
            self.nonroi_stacked.setVisible(False)

    def _update_nonroi_stacked(self):
        if self.nonroi_method_combo.currentData() == "everything_else":
            self.nonroi_stacked.setVisible(False)
        else:
            self.nonroi_stacked.setVisible(True)
            if self.roi_method_spherical.isChecked():
                self.nonroi_stacked.setCurrentIndex(0)
            else:
                self.nonroi_stacked.setCurrentIndex(1)

    def _update_nonroi_atlas_combo(self):
        self.nonroi_atlas_combo.clear()
        for i in range(self.atlas_combo.count()):
            self.nonroi_atlas_combo.addItem(self.atlas_combo.itemText(i))

    def _list_roi_regions(self):
        atlas = self.atlas_combo.currentText()
        hemi = "lh" if self.roi_hemi_combo.currentIndex() == 0 else "rh"
        self._show_atlas_regions_dialog(atlas, hemi)

    def _list_nonroi_regions(self):
        atlas = self.nonroi_atlas_combo.currentText()
        hemi = "lh" if self.nonroi_hemi_combo.currentIndex() == 0 else "rh"
        self._show_atlas_regions_dialog(atlas, hemi)

    def _show_atlas_regions_dialog(self, atlas_display, hemi):
        # Find the atlas file path
        subject_id = self.subject_combo.currentText()
        project_dir = os.environ.get('PROJECT_DIR', '/mnt/BIDS_test')
        seg_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}', 'segmentation')
        if not atlas_display:
            QtWidgets.QMessageBox.warning(self, "No Atlas Selected", "Please select an atlas.")
            return
        # Map display name back to full atlas name
        atlas_full = self.atlas_display_map.get(atlas_display, atlas_display)
        annot_file = os.path.join(seg_dir, f"{hemi}.{atlas_full}.annot")
        if not os.path.isfile(annot_file):
            QtWidgets.QMessageBox.warning(self, "Atlas File Not Found", f"Could not find atlas file: {annot_file}")
            return
        # Run read_annot.py and show output
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        utils_dir = os.path.join(script_dir, "utils")
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

    def disable_controls(self):
        """Disable all input controls during optimization."""
        # Disable subject selection
        self.subject_combo.setEnabled(False)
        self.refresh_subjects_btn.setEnabled(False)
        
        # Disable optimization parameters
        self.goal_combo.setEnabled(False)
        self.postproc_combo.setEnabled(False)
        self.eeg_net_combo.setEnabled(False)
        self.refresh_eeg_nets_btn.setEnabled(False)
        
        # Disable electrode parameters
        self.radius_input.setEnabled(False)
        self.current_input.setEnabled(False)
        
        # Disable mapping options
        self.enable_mapping_checkbox.setEnabled(False)
        self.run_mapped_simulation_checkbox.setEnabled(False)
        self.run_optimized_simulation_checkbox.setEnabled(False)
        
        # Disable ROI method selection
        self.roi_method_spherical.setEnabled(False)
        self.roi_method_cortical.setEnabled(False)
        
        # Disable ROI inputs based on method
        if self.roi_method_spherical.isChecked():
            self.roi_x_input.setEnabled(False)
            self.roi_y_input.setEnabled(False)
            self.roi_z_input.setEnabled(False)
            self.roi_radius_input.setEnabled(False)
        else:
            self.atlas_combo.setEnabled(False)
            self.roi_hemi_combo.setEnabled(False)
            self.refresh_atlases_btn.setEnabled(False)
            self.list_roi_regions_btn.setEnabled(False)
            self.label_value_input.setEnabled(False)
        
        # Disable focality options if visible
        if self.focality_group.isVisible():
            self.threshold_input.setEnabled(False)
            self.nonroi_method_combo.setEnabled(False)
            if self.nonroi_method_combo.currentData() == "specific":
                if self.roi_method_spherical.isChecked():
                    self.nonroi_x_input.setEnabled(False)
                    self.nonroi_y_input.setEnabled(False)
                    self.nonroi_z_input.setEnabled(False)
                    self.nonroi_radius_input.setEnabled(False)
                else:
                    self.nonroi_atlas_combo.setEnabled(False)
                    self.nonroi_hemi_combo.setEnabled(False)
                    self.list_nonroi_regions_btn.setEnabled(False)
                    self.nonroi_label_input.setEnabled(False)

        self.max_iterations_input.setEnabled(False)
        self.population_size_input.setEnabled(False)
        self.cpus_input.setEnabled(False)
        self.quiet_mode_checkbox.setEnabled(False)
        self.conservative_mode_checkbox.setEnabled(False)

    def enable_controls(self):
        """Enable all input controls after optimization."""
        # Enable subject selection
        self.subject_combo.setEnabled(True)
        self.refresh_subjects_btn.setEnabled(True)
        
        # Enable optimization parameters
        self.goal_combo.setEnabled(True)
        self.postproc_combo.setEnabled(True)
        self.eeg_net_combo.setEnabled(True)
        self.refresh_eeg_nets_btn.setEnabled(True)
        
        # Enable electrode parameters
        self.radius_input.setEnabled(True)
        self.current_input.setEnabled(True)
        
        # Enable mapping options
        self.enable_mapping_checkbox.setEnabled(True)
        self.run_mapped_simulation_checkbox.setEnabled(True)
        self.run_optimized_simulation_checkbox.setEnabled(True)
        
        # Enable ROI method selection
        self.roi_method_spherical.setEnabled(True)
        self.roi_method_cortical.setEnabled(True)
        
        # Enable ROI inputs based on method
        if self.roi_method_spherical.isChecked():
            self.roi_x_input.setEnabled(True)
            self.roi_y_input.setEnabled(True)
            self.roi_z_input.setEnabled(True)
            self.roi_radius_input.setEnabled(True)
        else:
            self.atlas_combo.setEnabled(True)
            self.roi_hemi_combo.setEnabled(True)
            self.refresh_atlases_btn.setEnabled(True)
            self.list_roi_regions_btn.setEnabled(True)
            self.label_value_input.setEnabled(True)
        
        # Enable focality options if visible
        if self.focality_group.isVisible():
            self.threshold_input.setEnabled(True)
            self.nonroi_method_combo.setEnabled(True)
            if self.nonroi_method_combo.currentData() == "specific":
                if self.roi_method_spherical.isChecked():
                    self.nonroi_x_input.setEnabled(True)
                    self.nonroi_y_input.setEnabled(True)
                    self.nonroi_z_input.setEnabled(True)
                    self.nonroi_radius_input.setEnabled(True)
                else:
                    self.nonroi_atlas_combo.setEnabled(True)
                    self.nonroi_hemi_combo.setEnabled(True)
                    self.list_nonroi_regions_btn.setEnabled(True)
                    self.nonroi_label_input.setEnabled(True)

        self.max_iterations_input.setEnabled(True)
        self.population_size_input.setEnabled(True)
        self.cpus_input.setEnabled(True)
        self.quiet_mode_checkbox.setEnabled(True)
        self.conservative_mode_checkbox.setEnabled(True)

    def optimization_finished_early_due_to_error(self):
        """Resets UI controls if optimization cannot start due to an error."""
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls() # Re-enable all controls
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
