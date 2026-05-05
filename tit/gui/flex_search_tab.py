#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Flex-search optimisation tab for the TI-Toolbox GUI.

Provides a form-based interface for the differential-evolution electrode
placement optimiser (Weise et al. 2025).  Users select subjects, define
target ROIs (spherical, cortical atlas, or subcortical), set electrode
and solver hyper-parameters, and launch optimisations in a background
``QThread``.

See Also
--------
tit.opt.config.FlexConfig : Backend configuration dataclass.
tit.gui.components.roi_picker.ROIPickerWidget : ROI selection widget.
tit.gui.components.electrode_config.ElectrodeConfigWidget : Electrode parameters.
tit.gui.components.solver_params.SolverParamsWidget : Solver hyper-parameters.
"""

import os
import subprocess
from pathlib import Path

from PyQt5 import QtWidgets, QtCore, QtGui

from tit.gui.confirmation_dialog import ConfirmationDialog
from tit.gui.components.console import (
    ConsoleWidget,
    format_message,
    append_with_autoscroll,
)
from tit.gui.components.action_buttons import RunStopButtons
from tit.gui.components.base_thread import BaseProcessThread
from tit.gui.components.roi_picker import ROIPickerWidget
from tit.gui.components.electrode_config import ElectrodeConfigWidget
from tit.gui.components.solver_params import SolverParamsWidget

from tit.paths import get_path_manager
from tit import constants as const
from tit.gui.style import FONT_HELP
from tit.opt.config import FlexConfig

# Convenience aliases for nested types
OptGoal = FlexConfig.OptGoal
FieldPostproc = FlexConfig.FieldPostproc
NonROIMethod = FlexConfig.NonROIMethod
from tit.config_io import write_config_json


class FlexSearchThread(BaseProcessThread):
    """Background thread that runs ``tit.opt.flex`` via subprocess.

    See Also
    --------
    BaseProcessThread : Provides ``execute_process`` and ``terminate_process``.
    """

    def __init__(self, cmd, env=None):
        super().__init__(cmd=cmd, env=env)

    def run(self):
        """Run the flex-search command via BaseProcessThread.execute_process()."""
        self.execute_process()


class FlexSearchTab(QtWidgets.QWidget):
    """Flex-search electrode optimisation tab.

    Provides controls for differential-evolution optimisation of electrode
    placements.  Supports multi-subject batch runs, adaptive focality,
    Pareto sweep modes, and real-time console output.  Configuration is
    serialised to JSON and executed via ``simnibs_python -m tit.opt.flex``.

    See Also
    --------
    FlexSearchThread : Background execution thread.
    tit.opt.config.FlexConfig : Backend configuration dataclass.
    tit.gui.optimizer_tab.OptimizerTab : Parent container tab.
    """

    flex_search_completed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        """Initialize the flex search tab."""
        super(FlexSearchTab, self).__init__(parent)
        self.parent = parent
        self.optimization_running = False
        self.optimization_process = None

        # Multi-subject optimization state
        self.selected_subjects = None
        self.current_subject_index = 0
        self.successful_runs = 0
        self.failed_runs = 0
        self.roi_params = None
        self.goal = None
        self.postproc = None
        self.anisotropy_type_value = None
        self.eeg_net = None
        self.electrode_current = None
        self.electrode_shape = None
        self.dimensions = None
        self.thickness = None
        self.optimization_thread = None

        # Initialize data structures
        self.subjects = []
        self.eeg_nets = {}

        # Initialize all widgets that might be referenced before setup_ui
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.subject_list.setFixedHeight(80)
        self.eeg_net_combo = QtWidgets.QComboBox()

        # Initialize goal and postproc combo boxes
        self.goal_combo = QtWidgets.QComboBox()
        self.goal_combo.addItem("mean (maximize field in target ROI)", "mean")
        self.goal_combo.addItem("max (maximize peak field in target ROI)", "max")
        self.goal_combo.addItem(
            "focality (maximize field in target ROI while minimizing field elsewhere)",
            "focality",
        )

        self.postproc_combo = QtWidgets.QComboBox()
        self.postproc_combo.addItem("max_TI (maximum TI field)", "max_TI")
        self.postproc_combo.addItem(
            "dir_TI_normal (TI field normal to surface)", "dir_TI_normal"
        )
        self.postproc_combo.addItem(
            "dir_TI_tangential (TI field tangential to surface)", "dir_TI_tangential"
        )

        self.anisotropy_combo = QtWidgets.QComboBox()
        self.anisotropy_combo.addItem("Isotropic (scalar)", "scalar")
        self.anisotropy_combo.addItem("Volume-normalized (vn)", "vn")
        self.anisotropy_combo.addItem("Direct (dir)", "dir")
        self.anisotropy_combo.addItem("Multi-conductivity (mc)", "mc")

        self.anisotropy_label = QtWidgets.QLabel("Anisotropy Type:")

        # Initialize buttons that might be referenced
        self.refresh_subjects_btn = QtWidgets.QPushButton("Refresh")
        self.select_all_subjects_btn = QtWidgets.QPushButton("Select All")
        self.clear_subjects_btn = QtWidgets.QPushButton("Clear")
        self.refresh_eeg_nets_btn = QtWidgets.QPushButton("Refresh")

        # Initialize labels
        self.subject_label = QtWidgets.QLabel("Subjects:")
        self.goal_label = QtWidgets.QLabel("Optimization Goal:")
        self.postproc_label = QtWidgets.QLabel("Post-processing Method:")
        self.eeg_net_label = QtWidgets.QLabel("EEG Net Template:")

        # Initialize checkboxes
        self.run_mapped_simulation_checkbox = QtWidgets.QCheckBox(
            "Run simulation with mapped electrodes"
        )
        self.run_mapped_simulation_checkbox.setChecked(False)

        self.run_final_electrode_simulation_checkbox = QtWidgets.QCheckBox(
            "Run final electrode simulation"
        )
        self.run_final_electrode_simulation_checkbox.setChecked(False)

        # --- Component widgets (replace inline widget creation) ---
        self.roi_picker = ROIPickerWidget(
            label="ROI",
            enable_spherical=True,
            enable_atlas=True,
            enable_subcortical=True,
            enable_freeview_button=True,
            enable_mni_toggle=True,
        )
        self.nonroi_picker = ROIPickerWidget(
            label="Non-ROI",
            enable_spherical=True,
            enable_atlas=True,
            enable_subcortical=True,
            enable_freeview_button=False,
            enable_mni_toggle=False,
        )
        self.electrode_widget = ElectrodeConfigWidget()
        self.solver_widget = SolverParamsWidget()

        # Initialize container widget for EEG net controls (used in _update_mapping_options)
        self.eeg_net_widget = QtWidgets.QWidget()

        # Initialize focality components
        self.focality_group = QtWidgets.QGroupBox("Focality Options")
        self.focality_group.setVisible(False)

        self.threshold_input = QtWidgets.QLineEdit()
        self.threshold_input.setPlaceholderText("e.g. 0.2 or 0.2,0.5")

        # Focality mode selector (three-way: Manual / Adaptive / Pareto Sweep)
        self.mode_manual_radio = QtWidgets.QRadioButton("Manual Thresholds")
        self.mode_adaptive_radio = QtWidgets.QRadioButton("Adaptive (single run)")
        self.mode_pareto_radio = QtWidgets.QRadioButton("Pareto Sweep")
        self.focality_mode_group = QtWidgets.QButtonGroup()
        self.focality_mode_group.addButton(self.mode_manual_radio, 0)
        self.focality_mode_group.addButton(self.mode_adaptive_radio, 1)
        self.focality_mode_group.addButton(self.mode_pareto_radio, 2)
        self.mode_adaptive_radio.setChecked(True)  # default

        # Pareto sweep input widgets
        self.roi_pcts_input = QtWidgets.QLineEdit("80")
        self.roi_pcts_input.setPlaceholderText("e.g. 80 or 80,70")

        self.nonroi_pcts_input = QtWidgets.QLineEdit("20,30,40")
        self.nonroi_pcts_input.setPlaceholderText("e.g. 20,30,40")

        self.sweep_preview_label = QtWidgets.QLabel("\u2192 3 combinations will be run")
        self.sweep_preview_label.setStyleSheet("color: gray; font-style: italic;")

        # Focality orchestration state (shared by adaptive & pareto modes)
        self._focality_state = {}
        self.achievable_intensity = None
        # Pareto sweep state variables
        self._sweep_points = []
        self._sweep_queue = None  # deque, set before sweep starts
        self._sweep_result = None
        self._current_sweep_point = None

        self.nonroi_percentage_input = QtWidgets.QDoubleSpinBox()
        self.nonroi_percentage_input.setRange(1, 99)
        self.nonroi_percentage_input.setValue(20)
        self.nonroi_percentage_input.setSuffix("%")
        self.nonroi_percentage_input.setToolTip(
            "Percentage of achievable intensity for non-ROI threshold"
        )

        self.roi_percentage_input = QtWidgets.QDoubleSpinBox()
        self.roi_percentage_input.setRange(1, 99)
        self.roi_percentage_input.setValue(80)
        self.roi_percentage_input.setSuffix("%")
        self.roi_percentage_input.setToolTip(
            "Percentage of achievable intensity for ROI threshold"
        )

        self.nonroi_method_combo = QtWidgets.QComboBox()
        self.nonroi_method_combo.addItem("Everything Else (default)", "everything_else")
        self.nonroi_method_combo.addItem("Specific Region", "specific")

        self.nonroi_method_label = QtWidgets.QLabel("Non-ROI Definition Method:")

        # Set up the UI
        self.setup_ui()

        # Connect signals after UI setup (critical widgets must exist)
        self.refresh_subjects_btn.clicked.connect(self.find_available_subjects)
        self.select_all_subjects_btn.clicked.connect(self.select_all_subjects)
        self.clear_subjects_btn.clicked.connect(self.clear_subject_selection)
        self.refresh_eeg_nets_btn.clicked.connect(self.find_available_eeg_nets)

        self.goal_combo.currentIndexChanged.connect(self._update_focality_visibility)
        self.focality_mode_group.buttonClicked.connect(
            self._update_focality_mode_visibility
        )
        self.roi_pcts_input.textChanged.connect(self._update_sweep_preview)
        self.nonroi_pcts_input.textChanged.connect(self._update_sweep_preview)
        self.run_mapped_simulation_checkbox.toggled.connect(
            self._update_mapping_options
        )
        self.subject_list.itemSelectionChanged.connect(self.on_subject_changed)
        self.nonroi_method_combo.currentIndexChanged.connect(
            self._update_nonroi_stacked
        )
        # When the ROI picker mode changes, also update the nonroi picker page
        self.roi_picker.roi_changed.connect(self._sync_nonroi_mode)

        # Find available subjects (which will trigger finding EEG nets and atlases)
        self.find_available_subjects()

    def setup_ui(self):
        """Set up the user interface for the flex-search tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(200)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(
            8, 8, 8, 8
        )  # Reduce margins from default ~11 to 8

        top_row_layout = QtWidgets.QHBoxLayout()
        top_row_layout.setSpacing(
            6
        )  # Reduce spacing between columns from default ~10 to 6

        # Left column: Basic Parameters
        basic_params_group = QtWidgets.QGroupBox("Basic Parameters")
        basic_params_group.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum
        )
        basic_params_layout = QtWidgets.QFormLayout(basic_params_group)
        basic_params_layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.ExpandingFieldsGrow
        )

        subject_controls_widget = QtWidgets.QWidget()
        subject_controls_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
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

        for combo, label in (
            (self.goal_combo, self.goal_label),
            (self.postproc_combo, self.postproc_label),
            (self.anisotropy_combo, self.anisotropy_label),
        ):
            combo.setSizeAdjustPolicy(
                QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(24)
            combo.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
            )
            basic_params_layout.addRow(label, combo)

        top_row_layout.addWidget(basic_params_group, 11, QtCore.Qt.AlignTop)

        # Right column: Automatic Simulations (top) + Electrode Parameters (bottom)
        right_column_widget = QtWidgets.QWidget()
        right_column_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        right_column_layout = QtWidgets.QVBoxLayout(right_column_widget)
        right_column_layout.setContentsMargins(0, 0, 0, 0)

        # Automatic Simulations Options (formerly Electrode Mapping)
        self.mapping_group = QtWidgets.QGroupBox("Automatic Simulations (Optional)")
        mapping_layout = QtWidgets.QFormLayout(self.mapping_group)
        mapping_layout.setVerticalSpacing(2)
        mapping_layout.setContentsMargins(4, 4, 4, 4)
        mapping_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)

        # Add final electrode simulation checkbox
        mapping_layout.addRow(self.run_final_electrode_simulation_checkbox)

        # Add mapped electrodes simulation checkbox
        mapping_layout.addRow(self.run_mapped_simulation_checkbox)

        # EEG net selection (only visible when run_mapped_simulation is checked)
        eeg_net_controls_inner_layout = QtWidgets.QHBoxLayout()
        eeg_net_controls_inner_layout.setContentsMargins(0, 0, 0, 0)
        self.eeg_net_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        eeg_net_controls_inner_layout.addWidget(self.eeg_net_combo)
        self.eeg_net_widget.setLayout(eeg_net_controls_inner_layout)
        self.eeg_net_widget.setVisible(False)
        self.eeg_net_label.setVisible(False)
        mapping_layout.addRow(self.eeg_net_label, self.eeg_net_widget)

        right_column_layout.addWidget(self.mapping_group)

        # Electrode Parameters — use component widget; stretch to fill
        self.electrode_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
        )
        right_column_layout.addWidget(self.electrode_widget)

        top_row_layout.addWidget(right_column_widget, 9)

        scroll_layout.addLayout(top_row_layout)

        # ROI Definition — use component widget
        self.roi_method_group = QtWidgets.QGroupBox("ROI Definition")
        roi_layout = QtWidgets.QVBoxLayout(self.roi_method_group)
        roi_layout.addWidget(self.roi_picker)
        scroll_layout.addWidget(self.roi_method_group)

        # Focality Options group
        focality_layout = QtWidgets.QFormLayout(self.focality_group)

        # --- Mode selector row ---
        mode_selector_widget = QtWidgets.QWidget()
        mode_selector_layout = QtWidgets.QHBoxLayout(mode_selector_widget)
        mode_selector_layout.setContentsMargins(0, 0, 0, 0)
        mode_selector_layout.addWidget(self.mode_manual_radio)
        mode_selector_layout.addWidget(self.mode_adaptive_radio)
        mode_selector_layout.addWidget(self.mode_pareto_radio)
        mode_selector_layout.addStretch()
        focality_layout.addRow(QtWidgets.QLabel("Mode:"), mode_selector_widget)

        # --- Pareto sweep widget (shown only in Pareto mode) ---
        self.pareto_widget = QtWidgets.QWidget()
        pareto_layout = QtWidgets.QFormLayout(self.pareto_widget)
        pareto_layout.setContentsMargins(0, 4, 0, 4)
        pareto_layout.setVerticalSpacing(4)
        pareto_layout.addRow(
            QtWidgets.QLabel("ROI thresholds (%):"), self.roi_pcts_input
        )
        pareto_layout.addRow(
            QtWidgets.QLabel("Non-ROI thresholds (%):"), self.nonroi_pcts_input
        )
        pareto_layout.addRow(self.sweep_preview_label)
        focality_layout.addRow(self.pareto_widget)
        self.pareto_widget.setVisible(False)

        # --- Adaptive widget (shown only in Adaptive mode) ---
        self.adaptive_widget = QtWidgets.QWidget()
        adaptive_widget_layout = QtWidgets.QFormLayout(self.adaptive_widget)
        adaptive_widget_layout.setContentsMargins(0, 4, 0, 4)
        adaptive_widget_layout.setVerticalSpacing(4)

        adaptive_help = QtWidgets.QLabel(
            "Automatically determines thresholds by first running mean optimization to find achievable intensity."
        )
        adaptive_help.setStyleSheet(f"font-size: {FONT_HELP}; color: gray;")
        adaptive_help.setWordWrap(True)
        adaptive_widget_layout.addRow(adaptive_help)

        adaptive_percentages_widget = QtWidgets.QWidget()
        adaptive_percentages_layout = QtWidgets.QHBoxLayout(adaptive_percentages_widget)
        adaptive_percentages_layout.addWidget(QtWidgets.QLabel("Non-ROI:"))
        adaptive_percentages_layout.addWidget(self.nonroi_percentage_input)
        adaptive_percentages_layout.addWidget(QtWidgets.QLabel("ROI:"))
        adaptive_percentages_layout.addWidget(self.roi_percentage_input)
        adaptive_percentages_layout.addStretch()
        adaptive_widget_layout.addRow(
            QtWidgets.QLabel("Adaptive Percentages:"), adaptive_percentages_widget
        )
        focality_layout.addRow(self.adaptive_widget)
        self.adaptive_widget.setVisible(True)  # default mode is Adaptive

        # Manual threshold input (shown only in Manual mode)
        self.threshold_label = QtWidgets.QLabel("Threshold(s) for E-field (V/m):")
        focality_layout.addRow(self.threshold_label, self.threshold_input)
        self.threshold_help = QtWidgets.QLabel(
            "Single value: E-field < value in non-ROI, > value in ROI. Two values: non-ROI max, ROI min."
        )
        self.threshold_help.setStyleSheet(f"font-size: {FONT_HELP}; color: gray;")
        focality_layout.addRow(self.threshold_help)
        # Hide manual widgets by default (Adaptive is default)
        self.threshold_input.setVisible(False)
        self.threshold_label.setVisible(False)
        self.threshold_help.setVisible(False)

        focality_layout.addRow(self.nonroi_method_label, self.nonroi_method_combo)

        # Non-ROI region picker (if 'Specific')
        focality_layout.addRow(
            QtWidgets.QLabel("Non-ROI Region (if 'Specific'):"), self.nonroi_picker
        )
        self.nonroi_picker.setVisible(False)

        scroll_layout.addWidget(self.focality_group)

        # Solver hyper-parameters — use component widget
        scroll_layout.addWidget(self.solver_widget)

        # Absorb extra vertical space so groups keep their natural height
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_content)

        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(
            self, run_text="Run Optimization", stop_text="Stop Optimization"
        )
        self.action_buttons.connect_run(self.run_optimization)
        self.action_buttons.connect_stop(self.stop_optimization)

        # Keep references for backward compatibility
        self.run_btn = self.action_buttons.get_run_button()
        self.stop_btn = self.action_buttons.get_stop_button()

        # Console widget component with Run/Stop buttons integrated
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            console_label="Output:",
            min_height=200,
            custom_buttons=[self.run_btn, self.stop_btn],
        )

        # Vertical splitter: config panel (top) | console (bottom)
        _v_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        _v_splitter.setChildrenCollapsible(False)
        _v_splitter.addWidget(scroll_area)
        _v_splitter.addWidget(self.console_widget)
        _v_splitter.setSizes([600, 400])
        main_layout.addWidget(_v_splitter)

        # Reference to underlying console for backward compatibility
        self.output_text = self.console_widget.get_console_widget()

        # Initialize focality visibility
        self._update_focality_visibility()
        self._update_nonroi_stacked()

    # ------------------------------------------------------------------ #
    #  Subject / EEG net discovery                                        #
    # ------------------------------------------------------------------ #

    def find_available_subjects(self):
        self.subjects = []
        self.subject_list.clear()
        self.output_text.clear()

        # Use path_manager to find subjects
        pm = get_path_manager()
        project_dir = pm.project_dir

        # Set PROJECT_DIR for other components that might need it
        os.environ["PROJECT_DIR"] = project_dir

        # Get subjects using path_manager
        self.subjects = pm.list_simnibs_subjects()
        for subject_id in self.subjects:
            self.subject_list.addItem(subject_id)

        # Trigger EEG net refresh and atlas refresh for the first subject
        if self.subjects:
            self.find_available_eeg_nets()
            # Populate atlas combos via the picker widgets
            first_subject = self.subjects[0]
            self.roi_picker.set_subject(first_subject, project_dir)
            self.nonroi_picker.set_subject(first_subject, project_dir)

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

        # Get the first selected subject (for consistency when multiple are selected)
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            return

        subject_id = selected_items[0].text()

        pm = get_path_manager()
        project_dir = pm.project_dir

        eeg_dir = pm.eeg_positions(subject_id)

        if not (eeg_dir and Path(eeg_dir).is_dir()):
            return

        # Find all CSV files in the directory
        for eeg_file in Path(eeg_dir).glob("*.csv"):
            net_name = eeg_file.stem
            self.eeg_nets[net_name] = str(eeg_file)
            self.eeg_net_combo.addItem(net_name)

        # Also populate solver widget's skin net combo
        skin_combo = self.solver_widget.get_skin_net_combo()
        skin_combo.clear()
        for net_name in self.eeg_nets:
            skin_combo.addItem(net_name)

        # Set default for skin visualization combo
        if "GSN-HydroCel-185" in self.eeg_nets:
            index = skin_combo.findText("GSN-HydroCel-185")
            if index >= 0:
                skin_combo.setCurrentIndex(index)
        elif self.eeg_nets:
            skin_combo.setCurrentIndex(0)
        else:
            self.eeg_net_combo.addItem("GSN-HydroCel-185")
            skin_combo.addItem("GSN-HydroCel-185")

    def on_subject_changed(self):
        """Handle subject selection change."""
        if self.subject_list.selectedItems():
            subject_id = self.subject_list.selectedItems()[0].text()
            pm = get_path_manager()
            project_dir = pm.project_dir
            self.find_available_eeg_nets()
            self.roi_picker.set_subject(subject_id, project_dir)
            self.nonroi_picker.set_subject(subject_id, project_dir)

    def _sync_nonroi_mode(self):
        """Keep the nonroi_picker on the same page as the roi_picker."""
        roi_type = self.roi_picker.get_roi_type()
        page_map = {"spherical": 0, "atlas": 1, "subcortical": 2}
        idx = page_map.get(roi_type, 0)
        self.nonroi_picker.stacked.setCurrentIndex(idx)
        # Also check the matching radio if it exists
        if idx == 0 and self.nonroi_picker.radio_spherical:
            self.nonroi_picker.radio_spherical.setChecked(True)
        elif idx == 1 and self.nonroi_picker.radio_cortical:
            self.nonroi_picker.radio_cortical.setChecked(True)
        elif idx == 2 and self.nonroi_picker.radio_subcortical:
            self.nonroi_picker.radio_subcortical.setChecked(True)

    # ------------------------------------------------------------------ #
    #  Run optimization                                                   #
    # ------------------------------------------------------------------ #

    def run_optimization(self):
        """Run the flex-search optimization."""
        if self.optimization_running:
            self.update_output(
                "Optimization already running. Please wait or stop the current run."
            )
            return

        # Validate inputs
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(
                self, "Warning", "Please select at least one subject."
            )
            return

        # Only require EEG net when mapping is enabled
        if (
            self.run_mapped_simulation_checkbox.isChecked()
            and not self.eeg_net_combo.currentText()
        ):
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select an EEG net.")
            return

        # Check if visualize skin region is enabled but no skin net is selected
        solver_params = self.solver_widget.get_params()
        if (
            solver_params["visualize_valid_skin_region"]
            and not self.solver_widget.get_skin_net_combo().currentText()
        ):
            QtWidgets.QMessageBox.warning(
                self,
                "Warning",
                "Visualizing valid skin region requires selecting an EEG net for visualization.\n\n"
                "Please select a visualization EEG net.",
            )
            return

        # Validate ROI
        error = self.roi_picker.validate()
        if error:
            QtWidgets.QMessageBox.warning(self, "Warning", error)
            return

        # Check coordinate space for spherical ROI with MNI space selected
        if (
            self.roi_picker.get_roi_type() == "spherical"
            and self.roi_picker.is_mni_space()
        ):
            reply = QtWidgets.QMessageBox.question(
                self,
                "MNI Coordinates",
                "You have selected MNI space for spherical ROI.\n\n"
                "The coordinates you entered will be treated as MNI space coordinates "
                "and will be automatically transformed to each subject's native space.\n\n"
                "Do you want to continue?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

        # Get ROI parameters from picker
        roi_params = self.roi_picker.get_roi_params()

        # Get optimization parameters
        selected_subjects = [item.text() for item in selected_items]
        goal = self.goal_combo.currentData()
        postproc = self.postproc_combo.currentData()
        anisotropy_type = self.anisotropy_combo.currentData()
        eeg_net = self.eeg_net_combo.currentText()
        electrode_config, electrode_current = self.electrode_widget.get_config()
        electrode_shape = self.electrode_widget.get_shape()
        dimensions = self.electrode_widget.get_dimensions_text()
        thickness = self.electrode_widget.get_thickness_text()

        # Show confirmation dialog
        roi_description = ""
        if roi_params["method"] == "spherical":
            roi_description = f"Spherical ROI at ({roi_params['center'][0]}, {roi_params['center'][1]}, {roi_params['center'][2]}) with radius {roi_params['radius']}mm"
        elif roi_params["method"] == "atlas":
            roi_description = (
                f"Cortical ROI: {roi_params['atlas']} region {roi_params['region']}"
            )
        else:
            roi_description = f"Subcortical ROI: {roi_params['volume_atlas']} region {roi_params['volume_region']}"

        details = (
            f"Subjects: {', '.join(selected_subjects)}\n"
            f"Number of subjects: {len(selected_subjects)}\n"
            f"ROI: {roi_description}\n"
            f"Goal: {goal}\n"
            + (
                f"EEG Net: {eeg_net}\n"
                if self.run_mapped_simulation_checkbox.isChecked()
                else ""
            )
            + f"Current: {electrode_current}mA\n"
            f"Electrode shape: {electrode_shape}\n"
            f"Dimensions: {dimensions}mm\n"
            f"Thickness: {thickness}mm"
        )

        if not ConfirmationDialog.confirm(
            self,
            title="Confirm Flex-Search Optimization",
            message="Are you sure you want to start the flex-search optimization?",
            details=details,
        ):
            return

        # Show additional confirmation for multiple subjects if needed
        if len(selected_subjects) > 1:
            subject_list_str = ", ".join(selected_subjects)
            confirmation_msg = f"You are about to run optimization for {len(selected_subjects)} subjects: {subject_list_str}\n\nSubjects will be processed sequentially (one after another). Do you want to continue?"
            reply = QtWidgets.QMessageBox.question(
                self,
                "Multiple Subjects",
                confirmation_msg,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
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
        self.anisotropy_type_value = anisotropy_type
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
            self.update_output(
                f"\n=== Processing Subject {self.current_subject_index + 1}/{len(self.selected_subjects)}: {subject_id} ==="
            )

        # Run optimization for this subject
        success = self._run_single_subject_optimization(
            subject_id,
            self.roi_params,
            self.goal,
            self.postproc,
            self.eeg_net,
            self.electrode_current,
            self.electrode_shape,
            self.dimensions,
            self.thickness,
            anisotropy_type=self.anisotropy_type_value,
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
            self.update_output(
                f"Successfully completed: {self.successful_runs}/{len(self.selected_subjects)} subjects"
            )
            if self.failed_runs > 0:
                self.update_output(
                    f"Failed: {self.failed_runs}/{len(self.selected_subjects)} subjects",
                    "error",
                )

        # Clean up multi-subject state variables
        self.selected_subjects = None
        self.current_subject_index = 0
        self.roi_params = None
        self.goal = None
        self.postproc = None
        self.anisotropy_type_value = None
        self.eeg_net = None
        self.electrode_current = None
        self.electrode_shape = None
        self.dimensions = None
        self.thickness = None

        # Reset state
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls()

        if self.successful_runs > 0:
            self.flex_search_completed.emit()

        if self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

    # ── Config-building helpers ──────────────────────────────────────────

    def _build_roi_from_ui(self, subject_id: str, project_dir: str, roi_params: dict):
        """Build an ROI dataclass from the current UI state and roi_params dict."""
        return self.roi_picker.get_roi_spec(subject_id, project_dir)

    def _build_non_roi_from_ui(
        self, subject_id: str, project_dir: str, roi_params: dict
    ):
        """Build a non-ROI spec from the focality non-ROI widgets.

        Returns None if non-ROI method is 'everything_else'.
        """
        if self.nonroi_method_combo.currentData() != "specific":
            return None
        return self.nonroi_picker.get_roi_spec(subject_id, project_dir)

    def _build_electrode_config(
        self, electrode_shape: str, dimensions: str, thickness: str
    ) -> FlexConfig.ElectrodeConfig:
        """Build ElectrodeConfig from UI values."""
        config, _ = self.electrode_widget.get_config()
        return config

    def _build_flex_config(
        self,
        subject_id: str,
        roi_params: dict,
        goal: str,
        postproc: str,
        eeg_net: str,
        electrode_current: float,
        electrode_shape: str,
        dimensions: str,
        thickness: str,
        thresholds: str = None,
        output_folder: str = None,
        anisotropy_type: str = "scalar",
    ) -> FlexConfig:
        """Build a FlexConfig dataclass from UI widget values and parameters."""
        project_dir = get_path_manager().project_dir
        roi = self._build_roi_from_ui(subject_id, project_dir, roi_params)
        electrode = self._build_electrode_config(electrode_shape, dimensions, thickness)

        # Focality-specific fields
        non_roi_method = None
        non_roi = None
        if goal == "focality":
            nonroi_method_val = self.nonroi_method_combo.currentData()
            non_roi_method = (
                NonROIMethod(nonroi_method_val)
                if nonroi_method_val
                else NonROIMethod.EVERYTHING_ELSE
            )
            non_roi = self._build_non_roi_from_ui(subject_id, project_dir, roi_params)

        # EEG mapping
        enable_mapping = self.run_mapped_simulation_checkbox.isChecked()

        # Skin visualization net
        skin_net_path = None
        solver = self.solver_widget.get_params()
        if solver["visualize_valid_skin_region"]:
            skin_net = self.solver_widget.get_skin_net_combo().currentText()
            if skin_net:
                skin_net_path = self.eeg_nets.get(skin_net)
                if not skin_net_path:
                    pm = get_path_manager()
                    skin_net_path = os.path.join(
                        pm.eeg_positions(subject_id),
                        f"{skin_net}.csv",
                    )

        return FlexConfig(
            subject_id=subject_id,
            goal=OptGoal(goal),
            postproc=FieldPostproc(postproc),
            anisotropy_type=anisotropy_type,
            current_mA=electrode_current,
            electrode=electrode,
            roi=roi,
            non_roi_method=non_roi_method,
            non_roi=non_roi,
            thresholds=thresholds,
            eeg_net=eeg_net if enable_mapping else None,
            enable_mapping=enable_mapping,
            disable_mapping_simulation=False,
            output_folder=output_folder,
            run_final_electrode_simulation=self.run_final_electrode_simulation_checkbox.isChecked(),
            n_multistart=solver["n_multistart"],
            max_iterations=solver["max_iterations"],
            population_size=solver["population_size"],
            tolerance=solver["tolerance"],
            mutation=solver["mutation"],
            recombination=solver["recombination"],
            cpus=solver["cpus"],
            detailed_results=solver["detailed_results"],
            visualize_valid_skin_region=solver["visualize_valid_skin_region"],
            skin_visualization_net=skin_net_path,
            min_electrode_distance=self.electrode_widget.get_min_electrode_distance(),
        )

    def _launch_flex_config(self, config: FlexConfig, env=None):
        """Write config to JSON and return the subprocess command list."""
        config_path = write_config_json(config, prefix="flex")
        cmd = ["simnibs_python", "-m", "tit.opt.flex", config_path]
        return cmd, config_path

    # ── End config-building helpers ───────────────────────────────────────

    def _run_single_subject_optimization(
        self,
        subject_id,
        roi_params,
        goal,
        postproc,
        eeg_net,
        electrode_current,
        electrode_shape,
        dimensions,
        thickness,
        anisotropy_type="scalar",
    ):
        """Run optimization for a single subject. Returns True if started successfully, False otherwise."""
        pm = get_path_manager()
        project_dir = pm.project_dir

        # Focality options -- delegate to specialised orchestrators when needed
        if goal == "focality":
            if self._is_pareto_sweep_mode():
                # --- Pareto Sweep mode ---
                grid_inputs = self._validate_sweep_inputs()
                if grid_inputs is None:
                    return False
                roi_pcts, nonroi_pcts = grid_inputs
                nonroi_method = self.nonroi_method_combo.currentData()
                if not nonroi_method:
                    self.output_text.append(
                        "Error: Non-ROI method required for Pareto Sweep."
                    )
                    return False
                return self._start_mean_optimization(
                    subject_id,
                    roi_params,
                    postproc,
                    eeg_net,
                    electrode_current,
                    electrode_shape,
                    dimensions,
                    thickness,
                    mode="pareto",
                    roi_pcts=roi_pcts,
                    nonroi_pcts=nonroi_pcts,
                    anisotropy_type=anisotropy_type,
                )
            elif self.mode_adaptive_radio.isChecked():
                # --- Adaptive (single run) mode ---
                nonroi_pct = self.nonroi_percentage_input.value()
                roi_pct = self.roi_percentage_input.value()

                if nonroi_pct >= roi_pct:
                    self.output_text.append(
                        "Error: Non-ROI percentage must be less than ROI percentage for focality optimization."
                    )
                    return False

                if nonroi_pct <= 0 or roi_pct <= 0:
                    self.output_text.append(
                        "Error: Percentage values must be greater than 0."
                    )
                    return False

                if nonroi_pct >= 100 or roi_pct >= 100:
                    self.output_text.append(
                        "Error: Percentage values must be less than 100."
                    )
                    return False

                return self._start_mean_optimization(
                    subject_id,
                    roi_params,
                    postproc,
                    eeg_net,
                    electrode_current,
                    electrode_shape,
                    dimensions,
                    thickness,
                    mode="adaptive",
                    anisotropy_type=anisotropy_type,
                )
            else:
                # --- Manual threshold mode ---
                thresholds = self.threshold_input.text().strip()
                if not thresholds:
                    self.output_text.append(
                        "Error: Please enter threshold(s) for focality."
                    )
                    return False

        # Build FlexConfig from UI state
        thresholds_value = None
        if (
            goal == "focality"
            and not self._is_pareto_sweep_mode()
            and not self.mode_adaptive_radio.isChecked()
        ):
            thresholds_value = self.threshold_input.text().strip() or None

        config = self._build_flex_config(
            subject_id=subject_id,
            roi_params=roi_params,
            goal=goal,
            postproc=postproc,
            eeg_net=eeg_net,
            electrode_current=electrode_current,
            electrode_shape=electrode_shape,
            dimensions=dimensions,
            thickness=thickness,
            thresholds=thresholds_value,
            anisotropy_type=anisotropy_type,
        )

        cmd, config_path = self._launch_flex_config(config)

        # Only set parent busy state for single subjects
        if self.selected_subjects is None or len(self.selected_subjects) == 1:
            if self.parent:
                self.parent.set_tab_busy(
                    self,
                    True,
                    stop_btn=self.stop_btn,
                )

        self.optimization_thread = None
        self.optimization_process = FlexSearchThread(cmd)
        self.optimization_process.output_signal.connect(self.update_output)
        self.optimization_process.error_signal.connect(
            lambda msg: self.update_output(msg, "error")
        )
        self.optimization_process.finished.connect(self.optimization_finished)
        self.optimization_process.start()

        return True

    # ------------------------------------------------------------------ #
    #  Output and lifecycle                                               #
    # ------------------------------------------------------------------ #

    def update_output(self, text, message_type="default"):
        """Update the console output."""
        if not text.strip():
            return

        text_html = text.replace("\n", "<br>").replace(" ", "&nbsp;")
        formatted_text = format_message(text_html)
        append_with_autoscroll(self.output_text, formatted_text)

    def optimization_finished(self):
        """Handle the completion of the optimization process."""
        # Check if this was a successful completion
        current_success = False
        active_thread = self.optimization_process
        if self.optimization_thread and self.optimization_thread.process:
            active_thread = self.optimization_thread
        if active_thread:
            current_success = bool(
                active_thread.process and active_thread.process.returncode == 0
            )
            if current_success:
                self.successful_runs += 1
            else:
                self.failed_runs += 1

        # Move to next subject if we're in multi-subject mode
        if self.selected_subjects is not None and len(self.selected_subjects) > 1:
            self.current_subject_index += 1
            self.output_text.append(
                f"Subject {self.current_subject_index}/{len(self.selected_subjects)} completed."
            )

            # Process next subject or finalize
            self._process_next_subject()
        else:
            # Single subject mode or last subject in multi-subject mode
            if self.parent:
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
            self.optimization_running = False
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.enable_controls()
            if current_success:
                self.flex_search_completed.emit()

    def clear_console(self):
        """Clear the output console."""
        self.output_text.clear()

    def stop_optimization(self):
        """Stop the running optimization process."""
        if self.parent:
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
        if self.selected_subjects is not None and len(self.selected_subjects) > 1:
            self.output_text.append(
                f"Multi-subject optimization stopped at subject {self.current_subject_index + 1}/{len(self.selected_subjects)}."
            )
            # Clear multi-subject state
            self.selected_subjects = None
            self.current_subject_index = 0

        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls()

    # ------------------------------------------------------------------ #
    #  UI visibility helpers                                              #
    # ------------------------------------------------------------------ #

    def _update_mapping_options(self):
        """Update visibility of EEG net selector based on mapped simulation checkbox."""
        is_mapping_enabled = self.run_mapped_simulation_checkbox.isChecked()
        self.eeg_net_widget.setVisible(is_mapping_enabled)
        self.eeg_net_label.setVisible(is_mapping_enabled)

    def _update_focality_visibility(self):
        is_focality = self.goal_combo.currentData() == "focality"
        self.focality_group.setVisible(is_focality)
        # Default to 'everything_else' and collapse non-ROI region
        if is_focality:
            self.nonroi_method_combo.setCurrentIndex(0)
            self.nonroi_picker.setVisible(False)
            # Initialize mode-based controls visibility
            self._update_focality_mode_visibility()

    def _update_focality_mode_visibility(self):
        """Update visibility of Manual / Adaptive / Pareto Sweep controls."""
        is_manual = self.mode_manual_radio.isChecked()
        is_adaptive = self.mode_adaptive_radio.isChecked()
        is_pareto = self.mode_pareto_radio.isChecked()
        self.pareto_widget.setVisible(is_pareto)
        self.adaptive_widget.setVisible(is_adaptive)
        self.threshold_input.setVisible(is_manual)
        self.threshold_label.setVisible(is_manual)
        if self.threshold_help:
            self.threshold_help.setVisible(is_manual)

    def _update_nonroi_stacked(self):
        if self.nonroi_method_combo.currentData() == "everything_else":
            self.nonroi_picker.setVisible(False)
        else:
            self.nonroi_picker.setVisible(True)

    # ------------------------------------------------------------------ #
    #  Enable / disable controls                                          #
    # ------------------------------------------------------------------ #

    def _set_controls_enabled(self, enabled):
        """Enable or disable all input controls."""
        self.subject_list.setEnabled(enabled)
        self.refresh_subjects_btn.setEnabled(enabled)
        self.select_all_subjects_btn.setEnabled(enabled)
        self.clear_subjects_btn.setEnabled(enabled)
        self.goal_combo.setEnabled(enabled)
        self.postproc_combo.setEnabled(enabled)
        self.anisotropy_combo.setEnabled(enabled)
        self.eeg_net_combo.setEnabled(enabled)
        self.refresh_eeg_nets_btn.setEnabled(enabled)
        self.run_final_electrode_simulation_checkbox.setEnabled(enabled)
        self.run_mapped_simulation_checkbox.setEnabled(enabled)
        self.roi_picker.set_enabled(enabled)
        self.electrode_widget.setEnabled(enabled)
        self.solver_widget.setEnabled(enabled)
        if self.focality_group.isVisible():
            self.mode_manual_radio.setEnabled(enabled)
            self.mode_adaptive_radio.setEnabled(enabled)
            self.mode_pareto_radio.setEnabled(enabled)
            self.nonroi_percentage_input.setEnabled(enabled)
            self.roi_percentage_input.setEnabled(enabled)
            self.threshold_input.setEnabled(enabled)
            self.nonroi_method_combo.setEnabled(enabled)
            self.nonroi_picker.set_enabled(enabled)

    def disable_controls(self):
        """Disable all input controls during optimization."""
        self._set_controls_enabled(False)

    def enable_controls(self):
        """Enable all input controls after optimization."""
        self._set_controls_enabled(True)

    def optimization_finished_early_due_to_error(self):
        """Resets UI controls if optimization cannot start due to an error."""
        self.optimization_running = False
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.enable_controls()
        if self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

    # ------------------------------------------------------------------ #
    #  Pareto Sweep helpers                                               #
    # ------------------------------------------------------------------ #

    def _is_pareto_sweep_mode(self) -> bool:
        """Return True when the Pareto Sweep radio button is selected."""
        return self.mode_pareto_radio.isChecked()

    def _parse_pct_list(self, text: str) -> list:
        """Parse '80,70' -> [80.0, 70.0]. Raises ValueError on bad input."""
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if not parts:
            raise ValueError("Empty list")
        values = [float(p) for p in parts]
        for v in values:
            if not (0 < v < 100):
                raise ValueError(f"Value {v} out of range (0, 100)")
        return values

    def _update_sweep_preview(self):
        """Recomputes N combinations and updates self.sweep_preview_label."""
        try:
            roi_pcts = self._parse_pct_list(self.roi_pcts_input.text())
            nonroi_pcts = self._parse_pct_list(self.nonroi_pcts_input.text())
        except ValueError:
            self.sweep_preview_label.setText("")
            return
        n = len(roi_pcts) * len(nonroi_pcts)
        self.sweep_preview_label.setText(
            f"\u2192 {n} combination{'s' if n != 1 else ''} will be run"
        )
        self.sweep_preview_label.setStyleSheet("color: gray; font-style: italic;")

    def _validate_sweep_inputs(self):
        """Parse and validate ROI%/non-ROI% lists. Returns (roi_pcts, nonroi_pcts) or None."""
        from tit.opt.flex.pareto import validate_grid

        roi_pcts = self._parse_pct_list(self.roi_pcts_input.text())
        nonroi_pcts = self._parse_pct_list(self.nonroi_pcts_input.text())
        validate_grid(roi_pcts, nonroi_pcts)
        return roi_pcts, nonroi_pcts

    def _start_mean_optimization(
        self,
        subject_id,
        roi_params,
        postproc,
        eeg_net,
        electrode_current,
        electrode_shape,
        dimensions,
        thickness,
        mode,
        roi_pcts=None,
        nonroi_pcts=None,
        anisotropy_type="scalar",
    ):
        """
        Run mean optimization as step 1 of adaptive or pareto focality.

        *mode* must be ``"adaptive"`` or ``"pareto"``.
        For pareto mode, *roi_pcts* and *nonroi_pcts* are required.
        On completion, delegates to ``_on_mean_optimization_finished``.
        """
        from collections import deque

        pm = get_path_manager()
        project_dir = pm.project_dir

        # Store all parameters for step 2
        self._focality_state = {
            "mode": mode,
            "subject_id": subject_id,
            "roi_params": roi_params,
            "postproc": postproc,
            "anisotropy_type": anisotropy_type,
            "eeg_net": eeg_net,
            "electrode_current": electrode_current,
            "electrode_shape": electrode_shape,
            "dimensions": dimensions,
            "thickness": thickness,
            "roi_pcts": roi_pcts or [],
            "nonroi_pcts": nonroi_pcts or [],
        }
        self.achievable_intensity = None

        # Reset pareto sweep state for a fresh run
        self._sweep_points = []
        self._sweep_queue = deque()
        self._sweep_result = None
        self._current_sweep_point = None

        # Build mean FlexConfig for step 1
        mean_config = self._build_flex_config(
            subject_id=subject_id,
            roi_params=roi_params,
            goal="mean",
            postproc=postproc,
            eeg_net=eeg_net,
            electrode_current=electrode_current,
            electrode_shape=electrode_shape,
            dimensions=dimensions,
            thickness=thickness,
            anisotropy_type=anisotropy_type,
        )

        mean_cmd, _ = self._launch_flex_config(mean_config)

        label = "Pareto Sweep" if mode == "pareto" else "Adaptive Focality"
        self.update_output(
            f"Step 1/2 -- Finding achievable ROI intensity ({label}: mean optimization)"
        )

        self.optimization_thread = FlexSearchThread(mean_cmd)
        self.optimization_thread.output_signal.connect(
            self._process_mean_optimization_output
        )
        self.optimization_thread.error_signal.connect(
            lambda msg: self.update_output(msg, "error")
        )
        self.optimization_thread.finished.connect(self._on_mean_optimization_finished)
        self.optimization_thread.start()
        return True

    # ------------------------------------------------------------------ #
    #  Unified mean-optimization-finished dispatcher                      #
    # ------------------------------------------------------------------ #

    def _on_mean_optimization_finished(self):
        """Dispatch to adaptive or pareto step-2 handler based on mode."""
        state = self._focality_state

        # Fallback: read achievable intensity from the mean-opt manifest
        if self.achievable_intensity is None or self.achievable_intensity <= 0:
            self.achievable_intensity = self._read_mean_intensity_from_manifest(
                state["subject_id"]
            )

        if self.achievable_intensity is None or self.achievable_intensity <= 0:
            self.update_output(
                "Could not determine achievable intensity from mean optimization.",
                "error",
            )
            self.optimization_finished_early_due_to_error()
            return

        self.update_output(
            f"Mean optimization done. Achievable intensity: "
            f"{self.achievable_intensity:.3f} V/m"
        )

        mode = state["mode"]
        if mode == "adaptive":
            self._run_adaptive_focality_step2()
        elif mode == "pareto":
            self._run_pareto_sweep_step2()

    # ------------------------------------------------------------------ #
    #  Adaptive step 2                                                    #
    # ------------------------------------------------------------------ #

    def _run_adaptive_focality_step2(self):
        """Calculate adaptive thresholds and run focality optimization."""
        state = self._focality_state

        nonroi_percentage = self.nonroi_percentage_input.value() / 100.0
        roi_percentage = self.roi_percentage_input.value() / 100.0

        nonroi_threshold = nonroi_percentage * self.achievable_intensity
        roi_threshold = roi_percentage * self.achievable_intensity

        self.update_output(
            "Step 2/2: Running focality optimization with adaptive thresholds"
        )
        self.update_output(
            f"   Non-ROI threshold: {nonroi_threshold:.3f} V/m ({nonroi_percentage * 100:.0f}%)"
        )
        self.update_output(
            f"   ROI threshold: {roi_threshold:.3f} V/m ({roi_percentage * 100:.0f}%)"
        )

        adaptive_thresholds = f"{nonroi_threshold:.3f},{roi_threshold:.3f}"

        pm = get_path_manager()
        focality_config = self._build_flex_config(
            subject_id=state["subject_id"],
            roi_params=state["roi_params"],
            goal="focality",
            postproc=state["postproc"],
            eeg_net=state["eeg_net"],
            electrode_current=state["electrode_current"],
            electrode_shape=state["electrode_shape"],
            dimensions=state["dimensions"],
            thickness=state["thickness"],
            thresholds=adaptive_thresholds,
            anisotropy_type=state["anisotropy_type"],
        )

        focality_cmd, _ = self._launch_flex_config(focality_config)

        self.optimization_thread = FlexSearchThread(focality_cmd)
        self.optimization_thread.output_signal.connect(self.update_output)
        self.optimization_thread.error_signal.connect(
            lambda msg: self.update_output(msg, "error")
        )
        self.optimization_thread.finished.connect(self.optimization_finished)
        self.optimization_thread.start()

    # ------------------------------------------------------------------ #
    #  Pareto step 2                                                      #
    # ------------------------------------------------------------------ #

    def _run_pareto_sweep_step2(self):
        """Build sweep grid and start sequential focality runs."""
        from tit.opt.flex.pareto import (
            compute_sweep_grid,
            ParetoSweepConfig,
            ParetoSweepResult,
        )
        from collections import deque

        state = self._focality_state

        self.update_output("Step 2/2 -- Running focality sweep...")

        from tit.opt.flex.utils import generate_run_dirname

        pm = get_path_manager()
        flex_root = pm.flex_search(state["subject_id"])
        os.makedirs(flex_root, exist_ok=True)
        sweep_folder_name = generate_run_dirname(flex_root)
        base_folder = os.path.join(flex_root, sweep_folder_name)

        roi_pcts = state["roi_pcts"]
        nonroi_pcts = state["nonroi_pcts"]

        self._sweep_points = compute_sweep_grid(
            roi_pcts,
            nonroi_pcts,
            self.achievable_intensity,
            base_folder,
        )
        cfg = ParetoSweepConfig(
            roi_pcts=roi_pcts,
            nonroi_pcts=nonroi_pcts,
            achievable_roi_mean=self.achievable_intensity,
            base_output_folder=base_folder,
        )
        self._sweep_result = ParetoSweepResult(config=cfg, points=self._sweep_points)
        self._sweep_queue = deque(self._sweep_points)

        self._print_progress_table()
        self._run_next_sweep_point()

    def _run_next_sweep_point(self):
        """Pop the next SweepPoint from the queue and launch a focality run for it."""
        import os as _os

        if not self._sweep_queue:
            self._finalize_pareto_sweep()
            return

        point = self._sweep_queue.popleft()
        self._current_sweep_point = point
        point.status = "running"

        state = self._focality_state
        pm = get_path_manager()
        project_dir = pm.project_dir
        _os.makedirs(point.output_folder, exist_ok=True)

        # Build a focality FlexConfig for this sweep point
        sweep_thresholds = f"{point.nonroi_threshold:.3f},{point.roi_threshold:.3f}"

        sweep_config = self._build_flex_config(
            subject_id=state["subject_id"],
            roi_params=state["roi_params"],
            goal="focality",
            postproc=state["postproc"],
            eeg_net=state["eeg_net"],
            electrode_current=state["electrode_current"],
            electrode_shape=state["electrode_shape"],
            dimensions=state["dimensions"],
            thickness=state["thickness"],
            anisotropy_type=state["anisotropy_type"],
            thresholds=sweep_thresholds,
            output_folder=point.output_folder,
        )

        focality_cmd, _ = self._launch_flex_config(sweep_config)

        n_total = len(self._sweep_points)
        n_done = sum(1 for p in self._sweep_points if p.status in ("done", "failed"))
        self.update_output(
            f"\n\u25b6 Running combination {n_done + 1}/{n_total}: "
            f"ROI={int(point.roi_pct)}%, NonROI={int(point.nonroi_pct)}% "
            f"(thresholds: ROI={point.roi_threshold:.3f} V/m, "
            f"NonROI={point.nonroi_threshold:.3f} V/m)"
        )

        self.optimization_thread = FlexSearchThread(focality_cmd)
        self.optimization_thread.output_signal.connect(self._process_sweep_point_output)
        self.optimization_thread.error_signal.connect(
            lambda msg: self.update_output(msg, "error")
        )
        self.optimization_thread.finished.connect(self._on_sweep_point_finished)
        self.optimization_thread.start()

    def _process_sweep_point_output(self, line: str, message_type: str):
        """Forward output and extract focality_score when available."""
        from tit.opt.flex.utils import parse_optimization_output

        self.update_output(line, message_type)
        if self._current_sweep_point is not None:
            value = parse_optimization_output(line)
            if value is not None:
                self._current_sweep_point.focality_score = value

    def _on_sweep_point_finished(self):
        """Mark current sweep point done/failed, reprint table, start next."""
        if self._current_sweep_point is not None:
            if self._current_sweep_point.focality_score is not None:
                self._current_sweep_point.status = "done"
            else:
                self._current_sweep_point.status = "failed"
            self._current_sweep_point = None

        self._print_progress_table()
        self._run_next_sweep_point()

    def _print_progress_table(self):
        """Append the current sweep progress table to the output console."""
        from tit.opt.flex.pareto import generate_summary_text

        if self._sweep_result is None:
            return
        sep = "\u2500" * 72
        self.update_output(f"\n{sep}")
        self.update_output("  Pareto Sweep Progress")
        self.update_output(sep)
        self.update_output(generate_summary_text(self._sweep_result))
        self.update_output(sep)

    def _finalize_pareto_sweep(self):
        """Save results, print final summary, re-enable controls."""
        from tit.opt.flex.pareto import save_results

        done_count = sum(1 for p in self._sweep_points if p.status == "done")
        total_count = len(self._sweep_points)

        self.update_output(
            f"\n\u2705 Pareto Sweep complete: {done_count}/{total_count} runs succeeded."
        )

        if self._sweep_result is not None:
            base_folder = self._sweep_result.config.base_output_folder
            j, p = save_results(self._sweep_result, base_folder)
            self.update_output("\U0001f4ca Results saved:")
            self.update_output(f"   JSON:  {j}")
            self.update_output(f"   Plot:  {p}")
            self.update_output(f"   Dir:   {base_folder}")

        self.optimization_running = False
        self.enable_controls()
        if self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

    def _process_mean_optimization_output(self, line, message_type):
        """Process output from mean optimization step (real-time stdout parsing)."""
        self.update_output(line, message_type)

        from tit.opt.flex.utils import parse_optimization_output

        value = parse_optimization_output(line)
        if value is not None:
            # For goal function values (negative = minimization), negate to get intensity.
            # For table-row values (positive field magnitudes), use as-is.
            intensity = abs(value)
            if intensity > 0:
                self.achievable_intensity = intensity
                self.update_output(
                    f"ROI intensity captured: {self.achievable_intensity:.3f} V/m",
                    "info",
                )

    def _read_mean_intensity_from_manifest(self, subject_id):
        """Read achievable intensity from the most recent mean-opt manifest (fallback).

        Scans flex-search run folders (newest first) for a manifest with
        ``goal="mean"`` and returns ``abs(result.best_value)``.
        """
        from tit.opt.flex.manifest import read_manifest

        pm = get_path_manager()
        flex_root = pm.flex_search(subject_id)

        # Sort subdirs newest-first (datetime names sort lexicographically)
        entries = sorted(
            (
                e.name
                for e in os.scandir(flex_root)
                if e.is_dir() and not e.name.startswith(".")
            ),
            reverse=True,
        )

        for name in entries:
            meta = read_manifest(os.path.join(flex_root, name))
            if meta is None:
                continue
            if meta.get("goal") != "mean":
                continue
            best_val = meta.get("result", {}).get("best_value")
            if best_val is not None:
                intensity = abs(best_val)
                if intensity > 0:
                    self.update_output(
                        f"Read achievable intensity from manifest: {intensity:.3f} V/m",
                        "info",
                    )
                    return intensity

        return None
