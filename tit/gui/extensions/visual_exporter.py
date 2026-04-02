#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: 3D Visual Exporter
Export STL/PLY cortical regions & vector clouds of simulation results.
"""

import os
import shutil
import glob
import logging
from pathlib import Path
from datetime import datetime
from PyQt5 import QtWidgets, QtCore

# Extension metadata (required)
EXTENSION_NAME = "3D Visual Exporter"
EXTENSION_DESCRIPTION = "Export STL/PLY cortical regions, vector clouds, and montage visualizations for 3D visualization"

from tit.paths import get_path_manager
from tit import constants as const
from tit.gui.components.console import ConsoleWidget
from tit.gui.components.action_buttons import RunStopButtons
from tit.gui.components.base_thread import BaseProcessThread
import logging as _std_logging
from tit.gui.style import FONT_NOTE  # graphics tokens
from tit.tools.extract_labels import extract_labels
from tit.tools.nifti_to_mesh import nifti_to_mesh
from tit.config_io import write_config_json
from tit.blender.config import (
    MontageConfig,
    VectorConfig,
    RegionConfig,
)


class Mode:
    STL = "STL"
    PLY = "PLY"
    VECTORS = "VECTORS"
    ELECTRODES = "ELECTRODES"
    SUBCORTICAL = "SUBCORTICAL"


class BlenderExportThread(BaseProcessThread):
    """Thread to run blender export commands in background.

    Supports sequential execution of multiple commands (e.g. STL + PLY region
    exports).  For a single command, pass a one-element list.
    """

    # Extra signal to indicate all commands finished (carries exit-code 0)
    finished_signal = QtCore.pyqtSignal(int)

    def __init__(self, commands):
        """
        Args:
            commands: list of (cmd: list[str], cwd: str | None) tuples.
        """
        super().__init__(parent=None)
        self.commands = commands

    def run(self):
        """Execute each command sequentially via BaseProcessThread machinery."""
        for cmd, cwd in self.commands:
            if self.terminated:
                break
            self.cmd = cmd
            self.cwd = cwd
            self.output_signal.emit(f"$ {' '.join(cmd)}", "command")
            self.execute_process()
            # Check if the subprocess failed
            if (
                self.process
                and self.process.returncode is not None
                and self.process.returncode != 0
            ):
                return  # error_signal already emitted by execute_process
        if not self.terminated:
            self.finished_signal.emit(0)


class VisualExporterWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.pm = get_path_manager() if get_path_manager else None

        self.subjects_list = []
        self.simulations_dict = {}

        # Initialize logger (will be configured when export runs)
        self.logger = None

        self._setup_ui()
        self._load_subjects()

    # UI setup
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        header_label = QtWidgets.QLabel("<h2>3D Visual Exporter</h2>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)

        desc = QtWidgets.QLabel(
            "Export cortical regions to STL/PLY, vector clouds (TI/mTI), and montage visualizations for 3D visualization.\n"
            "Montage visualizer creates publication-ready Blender scenes with electrodes from simulation config."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; padding: 5px;")
        desc.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(desc)

        # Subject/Simulation selector
        config_group = QtWidgets.QGroupBox("Selection")
        config_layout = QtWidgets.QGridLayout(config_group)

        row = 0
        config_layout.addWidget(QtWidgets.QLabel("Subject:"), row, 0)
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.currentTextChanged.connect(self._on_subject_changed)
        config_layout.addWidget(self.subject_combo, row, 1)

        config_layout.addWidget(QtWidgets.QLabel("Simulation:"), row, 2)
        self.simulation_combo = QtWidgets.QComboBox()
        config_layout.addWidget(self.simulation_combo, row, 3)

        # Refresh button
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh subjects, simulations, and regions lists")
        self.refresh_btn.clicked.connect(self._refresh_all)
        self.refresh_btn.setMaximumWidth(80)
        config_layout.addWidget(self.refresh_btn, row, 4)
        row += 1

        # Mesh selection is automatic via PathManager (no manual controls)

        layout.addWidget(config_group)

        # Radio tabs (QRadioButtons + QStackedWidget)
        mode_group = QtWidgets.QGroupBox("Mode")
        mvl = QtWidgets.QVBoxLayout(mode_group)
        radio_layout = QtWidgets.QHBoxLayout()
        self.rb_stl = QtWidgets.QRadioButton("Cortical Regions")
        self.rb_vec = QtWidgets.QRadioButton("Field Vectors")
        self.rb_electrodes = QtWidgets.QRadioButton("Montage Visualizer")
        self.rb_subcortical = QtWidgets.QRadioButton("Sub-cortical")
        self.rb_stl.setChecked(True)

        radio_layout.addWidget(self.rb_stl)
        radio_layout.addSpacing(12)
        radio_layout.addWidget(self.rb_vec)
        radio_layout.addSpacing(12)
        radio_layout.addWidget(self.rb_electrodes)
        radio_layout.addSpacing(12)
        radio_layout.addWidget(self.rb_subcortical)
        radio_layout.addStretch()
        mvl.addLayout(radio_layout)

        self.stack = QtWidgets.QStackedWidget()
        mvl.addWidget(self.stack)
        layout.addWidget(mode_group)

        self._build_stl_panel()
        self._build_vectors_panel()
        self._build_electrodes_panel()
        self._build_subcortical_panel()

        self.rb_stl.toggled.connect(lambda v: self._on_mode_changed())
        self.rb_vec.toggled.connect(lambda v: self._on_mode_changed())
        self.rb_electrodes.toggled.connect(lambda v: self._on_mode_changed())
        self.rb_subcortical.toggled.connect(lambda v: self._on_mode_changed())
        self._on_mode_changed()

        # Console with Run/Stop
        self.action_buttons = RunStopButtons(
            self, run_text="Run Export", stop_text="Stop"
        )
        self.action_buttons.connect_run(self._run)
        self.action_buttons.connect_stop(self._stop)

        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            console_label="Output:",
            min_height=150,
            max_height=None,
            custom_buttons=[
                self.action_buttons.get_run_button(),
                self.action_buttons.get_stop_button(),
            ],
        )
        layout.addWidget(self.console_widget)

    def _build_stl_panel(self):
        w = QtWidgets.QWidget()
        gl = QtWidgets.QGridLayout(w)
        r = 0
        gl.addWidget(QtWidgets.QLabel("Atlas:"), r, 0)
        self.stl_atlas_combo = QtWidgets.QComboBox()
        # Available atlases
        self.stl_atlas_combo.addItems([const.ATLAS_DK40, const.ATLAS_A2009S])
        self.stl_atlas_combo.setCurrentText(const.ATLAS_DK40)
        self.stl_atlas_combo.currentTextChanged.connect(
            lambda _: self._refresh_regions()
        )
        gl.addWidget(self.stl_atlas_combo, r, 1)
        gl.addWidget(QtWidgets.QLabel("Field:"), r, 2)
        self.stl_field_edit = QtWidgets.QLineEdit("TI_max")
        gl.addWidget(self.stl_field_edit, r, 3)
        r += 1
        # Regions selector
        regions_box = QtWidgets.QGroupBox("Cortical regions")
        rb_layout = QtWidgets.QVBoxLayout(regions_box)

        btns = QtWidgets.QHBoxLayout()
        self.btn_regions_sel_all = QtWidgets.QPushButton("Select all")
        self.btn_regions_clear = QtWidgets.QPushButton("Clear")
        btns.addWidget(self.btn_regions_sel_all)
        btns.addWidget(self.btn_regions_clear)
        # Search input
        btns.addWidget(QtWidgets.QLabel("Search:"))
        self.cort_regions_search = QtWidgets.QLineEdit()
        self.cort_regions_search.setPlaceholderText("Filter regions...")
        self.cort_regions_search.textChanged.connect(self._filter_regions)
        btns.addWidget(self.cort_regions_search)
        rb_layout.addLayout(btns)
        self.cort_regions_list = QtWidgets.QListWidget()
        self.cort_regions_list.setSelectionMode(
            QtWidgets.QAbstractItemView.MultiSelection
        )
        # Increase height of the regions list
        self.cort_regions_list.setMinimumHeight(200)
        rb_layout.addWidget(self.cort_regions_list)
        gl.addWidget(regions_box, r, 0, 1, 4)
        r += 1
        # Wire buttons
        self.btn_regions_sel_all.clicked.connect(lambda: self._regions_select_all(True))
        self.btn_regions_clear.clicked.connect(lambda: self._regions_select_all(False))
        self.stack.addWidget(w)

    def _build_ply_panel(self):
        # Deprecated panel (unused)
        pass

    def _build_vectors_panel(self):
        w = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(w)

        # Vector Customization
        cust_group = QtWidgets.QGroupBox("Vector Customization")
        cust = QtWidgets.QGridLayout(cust_group)
        r = 0
        cust.addWidget(QtWidgets.QLabel("Vector length:"), r, 0)
        self.vec_length_scale = QtWidgets.QDoubleSpinBox()
        self.vec_length_scale.setDecimals(2)
        self.vec_length_scale.setRange(0.0, 1000.0)
        self.vec_length_scale.setValue(1.0)
        cust.addWidget(self.vec_length_scale, r, 1)
        cust.addWidget(QtWidgets.QLabel("Vector width:"), r, 2)
        self.vec_vector_width = QtWidgets.QDoubleSpinBox()
        self.vec_vector_width.setRange(0.001, 100.0)
        self.vec_vector_width.setValue(1.0)
        cust.addWidget(self.vec_vector_width, r, 3)
        r += 1
        cust.addWidget(QtWidgets.QLabel("Anchor:"), r, 0)
        self.vec_anchor = QtWidgets.QComboBox()
        self.vec_anchor.addItems(["tail", "head"])
        cust.addWidget(self.vec_anchor, r, 1)
        cust.addWidget(QtWidgets.QLabel("Color scale:"), r, 2)
        self.vec_color_mode = QtWidgets.QComboBox()
        self.vec_color_mode.addItems(["rgb", "magscale"])
        cust.addWidget(self.vec_color_mode, r, 3)
        r += 1
        # Magscale options
        self.mag_row = r
        self.lbl_blue = QtWidgets.QLabel("Blue %:")
        self.spn_blue = QtWidgets.QDoubleSpinBox()
        self.spn_blue.setRange(0.0, 100.0)
        self.spn_blue.setValue(50.0)
        self.lbl_green = QtWidgets.QLabel("Green %:")
        self.spn_green = QtWidgets.QDoubleSpinBox()
        self.spn_green.setRange(0.0, 100.0)
        self.spn_green.setValue(80.0)
        self.lbl_red = QtWidgets.QLabel("Red %:")
        self.spn_red = QtWidgets.QDoubleSpinBox()
        self.spn_red.setRange(0.0, 100.0)
        self.spn_red.setValue(95.0)
        cust.addWidget(self.lbl_blue, r, 0)
        cust.addWidget(self.spn_blue, r, 1)
        cust.addWidget(self.lbl_green, r, 2)
        cust.addWidget(self.spn_green, r, 3)
        r += 1
        cust.addWidget(self.lbl_red, r, 0)
        cust.addWidget(self.spn_red, r, 1)

        # Initially hide magscale controls unless selected
        def _toggle_magscale():
            is_mag = self.vec_color_mode.currentText() == "magscale"
            for wdg in [
                self.lbl_blue,
                self.spn_blue,
                self.lbl_green,
                self.spn_green,
                self.lbl_red,
                self.spn_red,
            ]:
                wdg.setVisible(is_mag)

        self.vec_color_mode.currentTextChanged.connect(lambda _: _toggle_magscale())
        _toggle_magscale()
        outer.addWidget(cust_group)

        # Processing Options (balanced left/right)
        proc_group = QtWidgets.QGroupBox("Processing Options")
        proc = QtWidgets.QGridLayout(proc_group)
        # Row 0: left seed, right Export TI_sum
        rowp = 0
        proc.addWidget(QtWidgets.QLabel("Seed:"), rowp, 0)
        self.vec_seed = QtWidgets.QSpinBox()
        self.vec_seed.setRange(0, 1_000_000)
        self.vec_seed.setValue(42)
        proc.addWidget(self.vec_seed, rowp, 1)
        self.vec_do_sum = QtWidgets.QCheckBox("Export TI_sum vector")
        proc.addWidget(self.vec_do_sum, rowp, 3, 1, 3)
        rowp += 1
        # Row 1: left sample count + use maximum, right Export TI_normal
        proc.addWidget(QtWidgets.QLabel("Sample count:"), rowp, 0)
        self.vec_count = QtWidgets.QSpinBox()
        self.vec_count.setRange(1, 2_000_000)
        self.vec_count.setValue(10000)
        proc.addWidget(self.vec_count, rowp, 1)
        self.vec_all_nodes = QtWidgets.QCheckBox("Use maximum (all nodes)")
        proc.addWidget(self.vec_all_nodes, rowp, 2)
        self.vec_do_ti_normal = QtWidgets.QCheckBox("Export TI_normal vector")
        proc.addWidget(self.vec_do_ti_normal, rowp, 3, 1, 3)
        rowp += 1
        # Row 2: left Export CH1/CH2 checkbox, right Enable mTI
        self.vec_export_ch1_ch2 = QtWidgets.QCheckBox("Export CH1 and CH2 vectors")
        proc.addWidget(self.vec_export_ch1_ch2, rowp, 0, 1, 2)
        self.vec_enable_mti = QtWidgets.QCheckBox("Enable mTI (4 meshes)")
        proc.addWidget(self.vec_enable_mti, rowp, 3, 1, 3)
        rowp += 1
        # MTI pickers spanning full width
        self.lbl_m1 = QtWidgets.QLabel("TDCS mesh 1:")
        proc.addWidget(self.lbl_m1, rowp, 0)
        self.vec_m1 = QtWidgets.QLineEdit()
        b1 = QtWidgets.QPushButton("Browse…")
        b1.clicked.connect(lambda: self._browse_tdcs_into(self.vec_m1))
        proc.addWidget(self.vec_m1, rowp, 1, 1, 4)
        proc.addWidget(b1, rowp, 5)
        rowp += 1
        self.lbl_m2 = QtWidgets.QLabel("TDCS mesh 2:")
        proc.addWidget(self.lbl_m2, rowp, 0)
        self.vec_m2 = QtWidgets.QLineEdit()
        b2 = QtWidgets.QPushButton("Browse…")
        b2.clicked.connect(lambda: self._browse_tdcs_into(self.vec_m2))
        proc.addWidget(self.vec_m2, rowp, 1, 1, 4)
        proc.addWidget(b2, rowp, 5)
        rowp += 1
        self.lbl_m3 = QtWidgets.QLabel("TDCS mesh 3 (mTI):")
        proc.addWidget(self.lbl_m3, rowp, 0)
        self.vec_m3 = QtWidgets.QLineEdit()
        b3 = QtWidgets.QPushButton("Browse…")
        b3.clicked.connect(lambda: self._browse_tdcs_into(self.vec_m3))
        proc.addWidget(self.vec_m3, rowp, 1, 1, 4)
        proc.addWidget(b3, rowp, 5)
        rowp += 1
        self.lbl_m4 = QtWidgets.QLabel("TDCS mesh 4 (mTI):")
        proc.addWidget(self.lbl_m4, rowp, 0)
        self.vec_m4 = QtWidgets.QLineEdit()
        b4 = QtWidgets.QPushButton("Browse…")
        b4.clicked.connect(lambda: self._browse_tdcs_into(self.vec_m4))
        proc.addWidget(self.vec_m4, rowp, 1, 1, 4)
        proc.addWidget(b4, rowp, 5)

        def _toggle_mti():
            show = self.vec_enable_mti.isChecked()
            # Show/hide all four pickers and their labels/buttons
            for wdg in [
                self.lbl_m1,
                self.lbl_m2,
                self.lbl_m3,
                self.lbl_m4,
                self.vec_m1,
                self.vec_m2,
                self.vec_m3,
                self.vec_m4,
                b1,
                b2,
                b3,
                b4,
            ]:
                wdg.setVisible(show)

        self.vec_enable_mti.toggled.connect(lambda _: _toggle_mti())
        _toggle_mti()

        # Disable sample count when using maximum
        def _toggle_all_nodes():
            self.vec_count.setEnabled(not self.vec_all_nodes.isChecked())

        self.vec_all_nodes.toggled.connect(lambda _: _toggle_all_nodes())
        _toggle_all_nodes()

        outer.addWidget(cust_group)
        outer.addWidget(proc_group)
        outer.addStretch()

        # Wrap vectors panel in a scroll area to avoid squishing when options expand
        sa = QtWidgets.QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QtWidgets.QFrame.NoFrame)
        sa.setWidget(w)
        self.stack.addWidget(sa)

    def _build_electrodes_panel(self):
        w = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(w)

        # Montage Visualizer Configuration
        config_group = QtWidgets.QGroupBox("Montage Visualizer Configuration")
        config = QtWidgets.QGridLayout(config_group)
        r = 0

        # Montage-only checkbox
        self.montage_only_checkbox = QtWidgets.QCheckBox(
            "Show only montage electrodes (from config.json)"
        )
        self.montage_only_checkbox.setChecked(False)
        config.addWidget(self.montage_only_checkbox, r, 0, 1, 4)
        r += 1

        # Electrode parameters
        config.addWidget(QtWidgets.QLabel("Electrode Diameter (mm):"), r, 0)
        self.electrode_diameter_spin = QtWidgets.QDoubleSpinBox()
        self.electrode_diameter_spin.setRange(1.0, 100.0)
        self.electrode_diameter_spin.setValue(10.0)
        self.electrode_diameter_spin.setDecimals(1)
        config.addWidget(self.electrode_diameter_spin, r, 1)

        config.addWidget(QtWidgets.QLabel("Electrode Height (mm):"), r, 2)
        self.electrode_height_spin = QtWidgets.QDoubleSpinBox()
        self.electrode_height_spin.setRange(1.0, 50.0)
        self.electrode_height_spin.setValue(6.0)
        self.electrode_height_spin.setDecimals(1)
        config.addWidget(self.electrode_height_spin, r, 3)
        r += 1

        # GLB is always exported alongside .blend files

        # Info label
        info_label = QtWidgets.QLabel(
            "This mode creates a publication-ready Blender scene (.blend) with:\n"
            "• Scalp and gray matter surfaces\n"
            "• Electrode placements from simulation config.json\n"
            "• Optimized render settings\n\n"
            "Output directory: derivatives/ti-toolbox/visual_exports/sub-{subject_id}/montage_publication/"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            f"color: #555; font-size: {FONT_NOTE}; padding: 10px; background-color: #f0f0f0; border-radius: 5px;"
        )
        config.addWidget(info_label, r, 0, 1, 4)

        outer.addWidget(config_group)
        outer.addStretch()

        self.stack.addWidget(w)

    def _build_subcortical_panel(self):
        w = QtWidgets.QWidget()
        gl = QtWidgets.QGridLayout(w)
        r = 0

        # NIfTI file selection
        gl.addWidget(QtWidgets.QLabel("NIfTI File:"), r, 0)
        nifti_layout = QtWidgets.QHBoxLayout()
        self.subcort_nifti_edit = QtWidgets.QLineEdit()
        self.subcort_nifti_edit.setPlaceholderText("Auto-populated per subject")
        nifti_layout.addWidget(self.subcort_nifti_edit)
        self.subcort_nifti_browse = QtWidgets.QPushButton("Browse...")
        self.subcort_nifti_browse.clicked.connect(self._browse_subcort_nifti)
        nifti_layout.addWidget(self.subcort_nifti_browse)
        gl.addLayout(nifti_layout, r, 1, 1, 3)
        r += 1

        # Label masking (optional)
        gl.addWidget(QtWidgets.QLabel("Labels to extract:"), r, 0)
        self.subcort_labels_edit = QtWidgets.QLineEdit()
        self.subcort_labels_edit.setPlaceholderText(
            "Optional: e.g., 10,49 (comma-separated)"
        )
        gl.addWidget(self.subcort_labels_edit, r, 1, 1, 3)
        r += 1

        # Clean components option
        self.subcort_clean = QtWidgets.QCheckBox("Remove small disconnected components")
        gl.addWidget(self.subcort_clean, r, 0, 1, 2)
        r += 1

        # Label lookup table button
        self.subcort_lut_button = QtWidgets.QPushButton("Show Label Lookup Table")
        self.subcort_lut_button.clicked.connect(self._show_lut_table)
        gl.addWidget(self.subcort_lut_button, r, 0, 1, 2)
        r += 1

        # Note: Always exports both STL and MSH formats

        self.stack.addWidget(w)

    # Console helper
    def _update_output(self, message, msg_type="default"):
        if hasattr(self, "console_widget") and self.console_widget:
            self.console_widget.update_console(message, msg_type)

    # Data loading
    def _load_subjects(self):
        if not self.pm:
            self._update_output("Warning: Path manager not available", "warning")
            return
        try:
            self.subjects_list = self.pm.list_simnibs_subjects()
            for subject_id in self.subjects_list:
                sim_dir = self.pm.sub(subject_id)
                if sim_dir:
                    s = self.pm.list_simulations(subject_id)
                    self.simulations_dict[subject_id] = s
            self.subject_combo.clear()
            self.subject_combo.addItems(self.subjects_list)
            if self.subjects_list:
                self._on_subject_changed(self.subjects_list[0])
            self._update_output(f"Loaded {len(self.subjects_list)} subjects", "info")
        except Exception as e:
            self._update_output(f"Error loading subjects: {str(e)}", "error")

    def _refresh_all(self):
        """Refresh all dynamic content (subjects, simulations, regions)"""
        if not self.pm:
            self._update_output("Warning: Path manager not available", "warning")
            return

        try:
            # Store current selections
            current_subject = self.subject_combo.currentText()
            current_simulation = self.simulation_combo.currentText()

            # Reload subjects and simulations
            self._update_output("Refreshing data...", "info")
            self.subjects_list = []
            self.simulations_dict = {}

            self.subjects_list = self.pm.list_simnibs_subjects()
            for subject_id in self.subjects_list:
                sim_dir = self.pm.sub(subject_id)
                if sim_dir:
                    s = self.pm.list_simulations(subject_id)
                    self.simulations_dict[subject_id] = s

            # Update subject combo
            self.subject_combo.blockSignals(True)  # Prevent triggering changed signal
            self.subject_combo.clear()
            self.subject_combo.addItems(self.subjects_list)

            # Restore previous subject selection if still exists
            if current_subject and current_subject in self.subjects_list:
                self.subject_combo.setCurrentText(current_subject)
            elif self.subjects_list:
                self.subject_combo.setCurrentIndex(0)
                current_subject = self.subjects_list[0]

            self.subject_combo.blockSignals(False)

            # Update simulation combo
            if current_subject:
                self.simulation_combo.clear()
                sims = self.simulations_dict.get(current_subject, [])
                self.simulation_combo.addItems(sims)

                # Restore previous simulation selection if still exists
                if current_simulation and current_simulation in sims:
                    self.simulation_combo.setCurrentText(current_simulation)
                elif sims:
                    self.simulation_combo.setCurrentIndex(0)

            # Refresh regions list for STL mode
            self._refresh_regions()

            # Update sub-cortical NIfTI path
            if current_subject and hasattr(self, "subcort_nifti_edit"):
                m2m_dir = self.pm.m2m(current_subject)
                if m2m_dir and os.path.isdir(m2m_dir):
                    default_path = str(
                        Path(m2m_dir) / "segmentation" / "labeling.nii.gz"
                    )
                    self.subcort_nifti_edit.setText(default_path)
                    self.subcort_nifti_edit.setPlaceholderText(default_path)

            self._update_output(
                f"Refreshed: {len(self.subjects_list)} subjects loaded", "success"
            )

        except Exception as e:
            self._update_output(f"Error refreshing data: {str(e)}", "error")

    def _on_subject_changed(self, subject_id):
        self.simulation_combo.clear()
        sims = self.simulations_dict.get(subject_id, [])
        self.simulation_combo.addItems(sims)
        self._refresh_regions()
        # Set default sub-cortical NIfTI path
        if self.pm and subject_id and hasattr(self, "subcort_nifti_edit"):
            m2m_dir = self.pm.m2m(subject_id)
            if m2m_dir and os.path.isdir(m2m_dir):
                default_path = str(Path(m2m_dir) / "segmentation" / "labeling.nii.gz")
                self.subcort_nifti_edit.setText(default_path)
                self.subcort_nifti_edit.setPlaceholderText(default_path)

    # Browsers
    def _browse_gm_mesh(self):
        pass

    def _browse_file_into(self, line_edit: QtWidgets.QLineEdit, filters):
        filter_str = ";;".join(filters) if filters else "All Files (*)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select file", "", filter_str
        )
        if path:
            line_edit.setText(path)

    def _regions_select_all(self, select_all: bool):
        # Select or deselect all items in the regions list
        try:
            for i in range(self.cort_regions_list.count()):
                item = self.cort_regions_list.item(i)
                item.setSelected(select_all)
        except Exception:
            # GUI operations may fail during widget destruction
            pass

    def _filter_regions(self, text: str):
        # Filter regions list based on search text
        try:
            if not hasattr(self, "_all_regions"):
                return
            self.cort_regions_list.clear()
            filter_text = text.lower().strip()
            for name in self._all_regions:
                if not filter_text or filter_text in name.lower():
                    item = QtWidgets.QListWidgetItem(name)
                    self.cort_regions_list.addItem(item)
        except Exception:
            # GUI operations may fail during widget destruction
            pass

    def _refresh_regions(self):
        # Load region names for current atlas and subject m2m
        try:
            subject_id = self.subject_combo.currentText().strip()
            atlas = self.stl_atlas_combo.currentText().strip() or const.ATLAS_DK40
            m2m = self._m2m_dir(subject_id)
            if not subject_id or not atlas or not m2m:
                return
            try:
                from simnibs.utils.transformations import atlas2subject

                atlas_map = {}
                for hemi_dict in atlas2subject(m2m, atlas, split_labels=True).values():
                    atlas_map.update(hemi_dict)
            except (ImportError, OSError, ValueError):
                atlas_map = None
            if not atlas_map:
                return
            names = sorted(list(atlas_map.keys()))
            # Store all regions for filtering
            self._all_regions = names
            # Populate list
            self.cort_regions_list.clear()
            for name in names:
                item = QtWidgets.QListWidgetItem(name)
                self.cort_regions_list.addItem(item)
        except Exception:
            # GUI operations may fail during widget destruction
            pass

    def _browse_tdcs_into(self, line_edit: QtWidgets.QLineEdit):
        # Default to current simulation directory
        subject_id = self.subject_combo.currentText().strip()
        simulation_name = self.simulation_combo.currentText().strip()
        init_dir = self._simulation_dir(subject_id, simulation_name) or ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select TDCS mesh", init_dir, "Mesh Files (*.msh)"
        )
        if path:
            line_edit.setText(path)

    def _browse_subcort_nifti(self):
        # Default to m2m segmentation directory
        subject_id = self.subject_combo.currentText().strip()
        if self.pm and subject_id:
            m2m_dir = self.pm.m2m(subject_id)
            if m2m_dir and os.path.isdir(m2m_dir):
                init_dir = str(Path(m2m_dir) / "segmentation")
            else:
                init_dir = ""
        else:
            init_dir = ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select NIfTI file", init_dir, "NIfTI Files (*.nii *.nii.gz)"
        )
        if path:
            self.subcort_nifti_edit.setText(path)

    def _show_lut_table(self):
        """Show a popup dialog with the labeling lookup table."""
        # Close any existing LUT dialog
        if hasattr(self, "_lut_dialog") and self._lut_dialog:
            self._lut_dialog.close()

        subject_id = self.subject_combo.currentText().strip()
        if not subject_id:
            QtWidgets.QMessageBox.warning(
                self, "No Subject Selected", "Please select a subject first."
            )
            return

        # Find the labeling_LUT.txt file
        lut_path = None
        if self.pm:
            m2m_dir = self.pm.m2m(subject_id)
            if m2m_dir and os.path.isdir(m2m_dir):
                potential_path = Path(m2m_dir) / "segmentation" / "labeling_LUT.txt"
                if potential_path.exists():
                    lut_path = potential_path

        if not lut_path:
            QtWidgets.QMessageBox.warning(
                self,
                "LUT File Not Found",
                f"Could not find labeling_LUT.txt for subject {subject_id}.\n"
                f"Expected location: {potential_path if 'potential_path' in locals() else 'm2m/segmentation/labeling_LUT.txt'}",
            )
            return

        # Load and parse the LUT file
        label_data = []
        try:
            with open(lut_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            try:
                                label_id = int(parts[0].strip())
                                label_name = parts[1].strip()
                                # Clean up the label name - extract only the name part before any numbers
                                import re

                                # Split on whitespace and take only the non-numeric parts at the beginning
                                name_parts = re.split(r"\s+", label_name)
                                clean_parts = []
                                for part in name_parts:
                                    # Stop when we hit a number
                                    if re.match(r"^\d+$", part):
                                        break
                                    clean_parts.append(part)
                                label_name = " ".join(clean_parts).rstrip(":")
                                label_data.append((label_id, label_name))
                            except (ValueError, IndexError):
                                continue
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error Loading LUT", f"Failed to load labeling_LUT.txt: {str(e)}"
            )
            return

        if not label_data:
            QtWidgets.QMessageBox.warning(
                self,
                "Empty LUT",
                "The labeling_LUT.txt file appears to be empty or malformed.",
            )
            return

        # Create popup dialog
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"Label Lookup Table - {subject_id}")
        dialog.setMinimumSize(500, 400)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Add header
        header = QtWidgets.QLabel(
            f"<h3>Label Lookup Table</h3><p>Subject: {subject_id}</p>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Create table
        table = QtWidgets.QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Label ID", "Label Name"])
        table.setRowCount(len(label_data))

        # Sort by label ID
        label_data.sort(key=lambda x: x[0])

        for row, (label_id, label_name) in enumerate(label_data):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(label_id)))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(label_name))

        # Configure table
        table.resizeColumnsToContents()
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        layout.addWidget(table)

        # Add close button
        button_box = QtWidgets.QHBoxLayout()
        button_box.addStretch()
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(dialog.close)
        button_box.addWidget(close_button)
        layout.addLayout(button_box)

        # Make dialog non-modal so user can interact with main GUI
        dialog.setModal(False)
        dialog.show()

        # Keep reference to prevent garbage collection and clean up when closed
        self._lut_dialog = dialog
        dialog.finished.connect(lambda: setattr(self, "_lut_dialog", None))

    # Mode switching
    def _on_mode_changed(self):
        mode_index = {
            self.rb_stl: 0,
            self.rb_vec: 1,
            self.rb_electrodes: 2,
            self.rb_subcortical: 3,
        }
        for rb, idx in mode_index.items():
            if rb.isChecked():
                self.stack.setCurrentIndex(idx)
                break

    # Paths
    def _get_project_dir(self):
        if not self.pm:
            return None
        return self.pm.project_dir

    def _simulation_dir(self, subject_id: str, simulation_name: str):
        if not self.pm:
            return None
        return self.pm.simulation(subject_id, simulation_name)

    def _visual_exports_dir(self, subject_id: str, simulation_name: str):
        project_dir = self._get_project_dir()
        if not project_dir:
            return None
        if simulation_name is None:
            # Sub-cortical mode - no simulation
            out_base = os.path.join(
                project_dir,
                const.DIR_DERIVATIVES,
                const.DIR_TI_TOOLBOX,
                "visual_exports",
                f"{const.PREFIX_SUBJECT}{subject_id}",
                "sub-cortical",
            )
        else:
            # Regular mode with simulation
            out_base = os.path.join(
                project_dir,
                const.DIR_DERIVATIVES,
                const.DIR_TI_TOOLBOX,
                "visual_exports",
                f"{const.PREFIX_SUBJECT}{subject_id}",
                simulation_name,
            )
        os.makedirs(out_base, exist_ok=True)
        return out_base

    def _m2m_dir(self, subject_id: str):
        if not self.pm:
            return None
        return self.pm.m2m(subject_id)

    # Vector mesh autodetect
    def _autodetect_tdcs_pair(self, subject_id: str, simulation_name: str):
        sim_dir = self._simulation_dir(subject_id, simulation_name)
        if not sim_dir or not os.path.exists(sim_dir):
            return None, None
        patterns = [
            "*_TDCS_1_scalar.msh",
            "*_TDCS_2_scalar.msh",
            "*_TDCS_1_*.msh",
            "*_TDCS_2_*.msh",
        ]
        found = []
        for pat in patterns:
            found.extend(glob.glob(os.path.join(sim_dir, "**", pat), recursive=True))
        m1 = next((f for f in found if "TDCS_1" in os.path.basename(f)), None)
        m2 = next((f for f in found if "TDCS_2" in os.path.basename(f)), None)
        return m1, m2

    # Run/Stop
    def _run(self):
        subject_id = self.subject_combo.currentText().strip()
        simulation_name = self.simulation_combo.currentText().strip()

        # Input validation:
        # - Sub-cortical export: subject only
        # - Montage visualizer: subject + simulation (needs config.json under the simulation)
        # - STL / vectors: subject + simulation
        if self.rb_subcortical.isChecked():
            if not subject_id:
                QtWidgets.QMessageBox.warning(
                    self, "Missing Input", "Please select subject."
                )
                return
        elif self.rb_electrodes.isChecked():
            if not subject_id or not simulation_name:
                QtWidgets.QMessageBox.warning(
                    self, "Missing Input", "Please select subject and simulation."
                )
                return
        else:
            if not subject_id or not simulation_name:
                QtWidgets.QMessageBox.warning(
                    self, "Missing Input", "Please select subject and simulation."
                )
                return
        project_dir = self._get_project_dir()
        if not project_dir:
            QtWidgets.QMessageBox.warning(
                self, "Missing Project", "Project directory not found."
            )
            return

        # For sub-cortical mode, use subject directory instead of simulation-specific directory
        if self.rb_subcortical.isChecked():
            out_base = self._visual_exports_dir(
                subject_id, None
            )  # No simulation for sub-cortical
            if not out_base:
                QtWidgets.QMessageBox.warning(
                    self, "Output Error", "Could not create output directory."
                )
                return
        elif not self.rb_electrodes.isChecked():
            out_base = self._visual_exports_dir(subject_id, simulation_name)
            if not out_base:
                QtWidgets.QMessageBox.warning(
                    self, "Output Error", "Could not create output directory."
                )
                return
        else:
            # Montage visualizer mode - output directory handled by montage_publication
            out_base = None

        # Setup logger with timestamp - follows project convention: log/sub-{subject_id}/
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = os.path.join(
            project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            const.DIR_LOGS,
            f"sub-{subject_id}",
        )
        os.makedirs(log_dir, exist_ok=True)

        if self.rb_electrodes.isChecked():
            log_file = os.path.join(log_dir, f"is_blender_montage_{timestamp}.log")
        elif self.rb_subcortical.isChecked():
            log_file = os.path.join(log_dir, f"is_blender_subcortical_{timestamp}.log")
        else:
            log_file = os.path.join(
                log_dir, f"is_blender_{simulation_name}_{timestamp}.log"
            )

        # Create logger with file handler and GUI console callback handler
        from tit.logger import add_file_handler

        # Create base logger with file output only
        self.logger = _std_logging.getLogger("visual_exporter")
        self.logger.setLevel(_std_logging.DEBUG)
        if log_file:
            add_file_handler(log_file, level="DEBUG", logger_name="visual_exporter")

        # Add GUI console callback handler for real-time output in GUI
        class _CallbackHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self._callback = callback

            def emit(self, record):
                try:
                    self._callback(self.format(record))
                except Exception:
                    pass

        gui_handler = _CallbackHandler(self._update_output)
        gui_handler.setLevel(logging.INFO)  # Show INFO and above in GUI console
        # Use simple format for GUI (no timestamp/level prefix - that's added by console widget)
        gui_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(gui_handler)

        # Log header (in file only, not in GUI console)
        # Use debug level so it doesn't appear in GUI console
        self.logger.debug(f"=== 3D Visual Exporter - {EXTENSION_NAME} ===")
        self.logger.debug(f"Timestamp: {timestamp}")
        self.logger.debug(f"Log file: {log_file}")
        self.logger.debug("")

        try:
            commands = []

            if self.rb_stl.isChecked():
                atlas = self.stl_atlas_combo.currentText().strip() or const.ATLAS_DK40
                field = self.stl_field_edit.text().strip() or "TI_max"
                if not self.pm:
                    raise ValueError("PathManager not available")
                central_surface = self.pm.ti_central_surface(
                    subject_id, simulation_name
                )
                # Build commands for all formats (STL/PLY/MSH)
                self._prune_infos = []
                # Store selected region names once
                selected = [
                    self.cort_regions_list.item(i).text()
                    for i in range(self.cort_regions_list.count())
                    if self.cort_regions_list.item(i).isSelected()
                ]
                self._selected_regions = selected

                # Always export STL via config dataclass
                stl_config = RegionConfig(
                    subject_id=subject_id,
                    simulation_name=simulation_name,
                    format=RegionConfig.Format.STL,
                    atlas=atlas,
                    field_name=field,
                    skip_regions=not bool(selected),
                    regions=selected,
                    keep_meshes=True,
                )
                stl_config_path = write_config_json(
                    stl_config, prefix="blender_region_stl"
                )
                commands.append(
                    (["simnibs_python", "-m", "tit.blender", stl_config_path], None)
                )
                stl_dir = os.path.join(out_base, "stl")
                self._prune_infos.append(
                    {
                        "format": "stl",
                        "mode_dir": stl_dir,
                        "include_whole": True,
                        "simulation": simulation_name,
                    }
                )

                # Always export PLY via config dataclass
                ply_config = RegionConfig(
                    subject_id=subject_id,
                    simulation_name=simulation_name,
                    format=RegionConfig.Format.PLY,
                    atlas=atlas,
                    field_name=field,
                    skip_regions=not bool(selected),
                    regions=selected,
                    keep_meshes=True,
                )
                ply_config_path = write_config_json(
                    ply_config, prefix="blender_region_ply"
                )
                commands.append(
                    (["simnibs_python", "-m", "tit.blender", ply_config_path], None)
                )
                ply_dir = os.path.join(out_base, "ply")
                self._prune_infos.append(
                    {
                        "format": "ply",
                        "mode_dir": ply_dir,
                        "include_whole": True,
                        "simulation": simulation_name,
                    }
                )

            elif self.rb_vec.isChecked():
                # Build VectorConfig — paths resolved by PathManager
                vec_config = VectorConfig(
                    subject_id=subject_id,
                    simulation_name=simulation_name,
                    export_ch1_ch2=self.vec_export_ch1_ch2.isChecked(),
                    export_sum=self.vec_do_sum.isChecked(),
                    export_ti_normal=self.vec_do_ti_normal.isChecked(),
                    count=self.vec_count.value(),
                    all_nodes=(
                        self.vec_all_nodes.isChecked()
                        if getattr(self, "vec_all_nodes", None)
                        else False
                    ),
                    seed=self.vec_seed.value(),
                    length_scale=self.vec_length_scale.value(),
                    vector_scale=1.0,
                    vector_width=self.vec_vector_width.value(),
                    vector_length=1.0,
                    anchor=VectorConfig.Anchor(self.vec_anchor.currentText()),
                    color=VectorConfig.Color(
                        self.vec_color_mode.currentText().strip() or "rgb"
                    ),
                    blue_percentile=self.spn_blue.value(),
                    green_percentile=self.spn_green.value(),
                    red_percentile=self.spn_red.value(),
                )
                vec_config_path = write_config_json(vec_config, prefix="blender_vector")
                commands.append(
                    (["simnibs_python", "-m", "tit.blender", vec_config_path], None)
                )

            elif self.rb_electrodes.isChecked():
                # Montage Visualizer mode via config dataclass + JSON dispatch
                self.logger.info("=== Montage Visualizer Mode ===")

                montage_config = MontageConfig(
                    subject_id=subject_id,
                    simulation_name=simulation_name,
                    show_full_net=not self.montage_only_checkbox.isChecked(),
                    electrode_diameter_mm=self.electrode_diameter_spin.value(),
                    electrode_height_mm=self.electrode_height_spin.value(),
                )
                montage_config_path = write_config_json(
                    montage_config, prefix="blender_montage"
                )
                cmd = ["simnibs_python", "-m", "tit.blender", montage_config_path]

                self.logger.info("Starting montage visualizer subprocess...")
                self.logger.debug("Config: %s", montage_config_path)
                commands.append((cmd, None))

            elif self.rb_subcortical.isChecked():
                # Sub-cortical mesh export mode - runs synchronously using Python functions
                self.logger.info("=== Sub-cortical Mesh Export Mode ===")

                # Get NIfTI file path
                nifti_path = self.subcort_nifti_edit.text().strip()
                if not nifti_path:
                    # Use default path
                    if self.pm:
                        m2m_dir = self.pm.m2m(subject_id)
                        if m2m_dir and os.path.isdir(m2m_dir):
                            nifti_path = str(
                                Path(m2m_dir) / "segmentation" / "labeling.nii.gz"
                            )
                        else:
                            raise ValueError(
                                "Could not determine default NIfTI path. Please specify manually."
                            )
                    else:
                        raise ValueError("Please specify a NIfTI file path.")

                if not os.path.exists(nifti_path):
                    raise ValueError(f"NIfTI file not found: {nifti_path}")

                self.logger.info(f"NIfTI file: {nifti_path}")

                # Use the automatically determined output directory
                output_dir = out_base
                self.logger.info(f"Output directory: {output_dir}")

                # Parse labels if specified
                labels_text = self.subcort_labels_edit.text().strip()
                labels = None
                if labels_text:
                    try:
                        labels = [int(l.strip()) for l in labels_text.split(",")]
                        self.logger.info(f"Extracting labels: {labels}")
                    except ValueError as e:
                        raise ValueError(f"Invalid label format: {e}")

                # Determine clean options
                clean_components = self.subcort_clean.isChecked()
                if clean_components:
                    self.logger.info("Will remove small disconnected components")

                # Process the NIfTI file
                try:
                    # If labels specified, extract them first
                    if labels is not None:
                        temp_nifti = os.path.join(output_dir, "temp_extracted.nii.gz")
                        extracted_path = extract_labels(nifti_path, labels, temp_nifti)
                        input_file = extracted_path
                        self.logger.info(f"Extracted labels to: {extracted_path}")
                    else:
                        input_file = nifti_path

                    # Generate unique filename suffix based on labels and clean setting
                    suffix_parts = []
                    if labels is not None:
                        # Sort labels and create a compact string
                        label_str = "_".join(map(str, sorted(labels)))
                        suffix_parts.append(f"labels_{label_str}")
                    else:
                        suffix_parts.append("full")

                    # Add clean/raw indicator
                    if clean_components:
                        suffix_parts.append("clean")
                    else:
                        suffix_parts.append("raw")

                    suffix = "_".join(suffix_parts)

                    # Export STL
                    stl_output = os.path.join(output_dir, f"subcortical_{suffix}.stl")
                    self.logger.info("Generating STL mesh...")
                    stl_result = nifti_to_mesh(
                        input_file,
                        stl_output,
                        clean_components=clean_components,
                        clean_threshold=0.1,
                    )
                    self.logger.info(
                        f"STL created: {stl_result['output_file']} "
                        f"({stl_result['vertices']} vertices, {stl_result['faces']} faces)"
                    )
                    if stl_result["removed_components"] > 0:
                        self.logger.info(
                            f"Removed {stl_result['removed_components']} small components"
                        )

                    # Export MSH
                    msh_output = os.path.join(output_dir, f"subcortical_{suffix}.msh")
                    self.logger.info("Generating MSH mesh...")
                    msh_result = nifti_to_mesh(
                        input_file,
                        msh_output,
                        clean_components=clean_components,
                        clean_threshold=0.1,
                    )
                    self.logger.info(
                        f"MSH created: {msh_result['output_file']} "
                        f"({msh_result['vertices']} vertices, {msh_result['faces']} faces)"
                    )
                    if msh_result["removed_components"] > 0:
                        self.logger.info(
                            f"Removed {msh_result['removed_components']} small components"
                        )

                    # Save the NIfTI file used for mesh generation
                    nifti_filename = f"subcortical_{suffix}.nii.gz"
                    nifti_copy_path = os.path.join(output_dir, nifti_filename)
                    shutil.copy2(input_file, nifti_copy_path)
                    self.logger.info(f"Saved NIfTI file: {nifti_copy_path}")

                    # Clean up temp file if created
                    if labels is not None and os.path.exists(temp_nifti):
                        os.remove(temp_nifti)

                except Exception as e:
                    # Clean up temp file on error
                    if labels is not None and os.path.exists(temp_nifti):
                        try:
                            os.remove(temp_nifti)
                        except OSError:
                            # Temp file cleanup may fail
                            pass
                    raise

                # Sub-cortical mode completes immediately (no worker thread needed)
                self.logger.info("")
                self.logger.info("========================================")
                self.logger.info("EXPORT COMPLETE")
                self.logger.info("========================================")
                self._update_output(
                    "\n========================================", "success"
                )
                self._update_output("EXPORT COMPLETE", "success")
                self._update_output(
                    "========================================", "success"
                )
                return  # Exit early for sub-cortical mode

            # Run worker thread for STL/Vector modes
            if commands:
                self.logger.info(
                    f"Starting worker thread with {len(commands)} command(s)..."
                )
                self._start_worker(commands)
            else:
                self.logger.warning("No commands to execute")
                self._update_output("No export operations selected", "warning")
        except Exception as e:
            # Error already logged by the specific mode handler
            # Just show error dialog
            QtWidgets.QMessageBox.critical(
                self, "Export Error", f"{str(e)}\n\nSee log file for details."
            )

    def _start_worker(self, commands):
        if hasattr(self, "console_widget") and self.console_widget:
            self.console_widget.clear_console()
        self._update_output("Starting export…", "info")
        self.action_buttons.enable_stop()
        self.worker_thread = BlenderExportThread(commands)
        # BaseProcessThread.output_signal emits (message, type)
        self.worker_thread.output_signal.connect(
            lambda msg, typ: self._update_output(msg, typ)
        )
        self.worker_thread.finished_signal.connect(self._on_finished)
        self.worker_thread.error_signal.connect(self._on_error)
        self.worker_thread.start()

    def _stop(self):
        if (
            hasattr(self, "worker_thread")
            and self.worker_thread
            and self.worker_thread.isRunning()
        ):
            self._update_output("\nStopping…", "warning")
            # terminate_process() kills the subprocess (with timeout) inside the thread.
            # Don't call .terminate()/.wait() on the QThread itself — that blocks the GUI.
            # The finished_signal handler (_on_finished) re-enables the run button.
            self.worker_thread.terminate_process()
            self._update_output("Stopped by user.", "warning")
            self.action_buttons.enable_run()

    def _on_finished(self, code):
        self.action_buttons.enable_run()
        self._update_output("\n========================================", "success")
        self._update_output("EXPORT COMPLETE", "success")
        self._update_output("========================================", "success")
        # Post-process: keep only selected cortical regions for each generated format
        try:
            infos = getattr(self, "_prune_infos", []) or []
            sel_list = getattr(self, "_selected_regions", None)
            if not sel_list:
                return
            sel = set(sel_list)
            for info in infos:
                if info["format"] == "stl":
                    regions_dir = os.path.join(
                        info["mode_dir"], "cortical_stls", "regions"
                    )
                    if os.path.isdir(regions_dir):
                        for f in os.listdir(regions_dir):
                            if f.lower().endswith(".stl"):
                                name = os.path.splitext(f)[0]
                                if name not in sel:
                                    try:
                                        os.remove(os.path.join(regions_dir, f))
                                    except OSError:
                                        # File may be in use or already deleted
                                        pass
                else:
                    regions_dir = os.path.join(
                        info["mode_dir"], "cortical_plys", "regions"
                    )
                    if os.path.isdir(regions_dir):
                        for f in os.listdir(regions_dir):
                            if f.lower().endswith(".ply"):
                                name = os.path.splitext(f)[0]
                                if name not in sel:
                                    try:
                                        os.remove(os.path.join(regions_dir, f))
                                    except OSError:
                                        # File may be in use or already deleted
                                        pass
        except Exception:
            # Directory cleanup may fail if files are in use
            pass

    def _on_error(self, err):
        self.action_buttons.enable_run()
        self._update_output("\n========================================", "error")
        self._update_output("ERROR", "error")
        self._update_output("========================================", "error")
        self._update_output(err, "error")
        QtWidgets.QMessageBox.critical(self, "Export Error", err)


class VisualExporterWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Visual Exporter")
        self.setMinimumSize(900, 700)
        self.setWindowFlag(QtCore.Qt.Window)
        self.widget = VisualExporterWidget(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)


def main(parent=None):
    window = VisualExporterWindow(parent)
    window.show()
    return window


def run(parent=None):
    return main(parent)
