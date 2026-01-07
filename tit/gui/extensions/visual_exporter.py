#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: 3D Visual Exporter
Export STL/PLY cortical regions & vector clouds of simulation results.
"""

import os
import shutil
import subprocess
import tempfile
import glob
import io
from pathlib import Path
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
from PyQt5 import QtWidgets, QtCore

# Extension metadata (required)
EXTENSION_NAME = "3D Visual Exporter"
EXTENSION_DESCRIPTION = "Export STL/PLY cortical regions, vector clouds, and electrode placements for 3D visualization"

from tit.core import get_path_manager
from tit.core import constants as const
from tit.gui.components.console import ConsoleWidget
from tit.gui.components.action_buttons import RunStopButtons
from tit.logger import get_logger
from tit.tools.extract_labels import extract_labels_from_nifti
from tit.tools.nifti_to_mesh import nifti_to_mesh
from tit.blender.electrode_placement import ElectrodePlacer, ElectrodePlacementConfig


class Mode:
    STL = "STL"
    PLY = "PLY"
    VECTORS = "VECTORS"
    ELECTRODES = "ELECTRODES"
    SUBCORTICAL = "SUBCORTICAL"


class WorkerThread(QtCore.QThread):
    output_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(int)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, commands):
        super().__init__()
        self.commands = commands  # list of (cmd:list[str], cwd: Optional[str]) to run sequentially
        self._process = None

    def run(self):
        try:
            for cmd, cwd in self.commands:
                self.output_signal.emit(f"\n$ {' '.join(cmd)}")
                self._process = subprocess.Popen(
                    cmd,
                    cwd=cwd or None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )
                assert self._process.stdout is not None
                for line in self._process.stdout:
                    self.output_signal.emit(line.rstrip("\n"))
                ret = self._process.wait()
                if ret != 0:
                    self.error_signal.emit(f"Command failed with exit code {ret}")
                    return
            self.finished_signal.emit(0)
        except Exception as e:
            import traceback
            self.error_signal.emit(f"{str(e)}\n\n{traceback.format_exc()}")

    def terminate_and_wait(self):
        try:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
        except Exception:
            # Process cleanup may fail if already terminated
            pass


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
            "Export cortical regions to STL/PLY, vector clouds (TI/mTI), and electrode placements for 3D visualization.\n"
            "Electrode placement uses scalp surface extracted from subject mesh files."
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
        row += 1

        # Mesh selection is automatic via PathManager (no manual controls)

        layout.addWidget(config_group)

        # Radio tabs (QRadioButtons + QStackedWidget)
        mode_group = QtWidgets.QGroupBox("Mode")
        mvl = QtWidgets.QVBoxLayout(mode_group)
        radio_layout = QtWidgets.QHBoxLayout()
        self.rb_stl = QtWidgets.QRadioButton("Cortical Regions")
        self.rb_vec = QtWidgets.QRadioButton("Field Vectors")
        self.rb_electrodes = QtWidgets.QRadioButton("Electrode Placement")
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
        self.action_buttons = RunStopButtons(self, run_text="Run Export", stop_text="Stop")
        self.action_buttons.connect_run(self._run)
        self.action_buttons.connect_stop(self._stop)

        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            show_debug_checkbox=True,
            console_label="Output:",
            min_height=150,
            max_height=None,
            custom_buttons=[self.action_buttons.get_run_button(), self.action_buttons.get_stop_button()],
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
        self.stl_atlas_combo.currentTextChanged.connect(lambda _: self._refresh_regions())
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
        self.cort_regions_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
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
            for wdg in [self.lbl_blue, self.spn_blue, self.lbl_green, self.spn_green, self.lbl_red, self.spn_red]:
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
            for wdg in [self.lbl_m1, self.lbl_m2, self.lbl_m3, self.lbl_m4,
                        self.vec_m1, self.vec_m2, self.vec_m3, self.vec_m4,
                        b1, b2, b3, b4]:
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

        # Electrode Configuration
        config_group = QtWidgets.QGroupBox("Electrode Configuration")
        config = QtWidgets.QGridLayout(config_group)
        r = 0

        # Net selection
        config.addWidget(QtWidgets.QLabel("EEG Net:"), r, 0)
        self.electrode_net_combo = QtWidgets.QComboBox()
        self.electrode_net_combo.setMinimumWidth(200)
        config.addWidget(self.electrode_net_combo, r, 1, 1, 2)
        r += 1


        # Electrode placement parameters
        config.addWidget(QtWidgets.QLabel("Electrode Size:"), r, 0)
        self.electrode_size_spin = QtWidgets.QDoubleSpinBox()
        self.electrode_size_spin.setRange(1.0, 1000.0)
        self.electrode_size_spin.setValue(50.0)
        config.addWidget(self.electrode_size_spin, r, 1)

        config.addWidget(QtWidgets.QLabel("Offset Distance:"), r, 2)
        self.offset_distance_spin = QtWidgets.QDoubleSpinBox()
        self.offset_distance_spin.setRange(0.1, 10.0)
        self.offset_distance_spin.setValue(3.25)
        config.addWidget(self.offset_distance_spin, r, 3)
        r += 1

        config.addWidget(QtWidgets.QLabel("Text Offset:"), r, 0)
        self.text_offset_spin = QtWidgets.QDoubleSpinBox()
        self.text_offset_spin.setRange(0.01, 1.0)
        self.text_offset_spin.setValue(0.090)
        config.addWidget(self.text_offset_spin, r, 1)

        config.addWidget(QtWidgets.QLabel("Scale Factor:"), r, 2)
        self.scale_factor_spin = QtWidgets.QDoubleSpinBox()
        self.scale_factor_spin.setRange(0.001, 10.0)
        self.scale_factor_spin.setValue(1.0)
        config.addWidget(self.scale_factor_spin, r, 3)

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
        self.subcort_labels_edit.setPlaceholderText("Optional: e.g., 10,49 (comma-separated)")
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
    def _update_output(self, message, msg_type='default'):
        if hasattr(self, 'console_widget') and self.console_widget:
            self.console_widget.update_console(message, msg_type)

    # Data loading
    def _load_subjects(self):
        if not self.pm:
            self._update_output("Warning: Path manager not available", 'warning')
            return
        try:
            self.subjects_list = self.pm.list_subjects()
            for subject_id in self.subjects_list:
                sim_dir = self.pm.path_optional("simnibs_subject", subject_id=subject_id)
                if sim_dir:
                    s = self.pm.list_simulations(subject_id)
                    self.simulations_dict[subject_id] = s
            self.subject_combo.clear()
            self.subject_combo.addItems(self.subjects_list)
            if self.subjects_list:
                self._on_subject_changed(self.subjects_list[0])
            self._update_output(f"Loaded {len(self.subjects_list)} subjects", 'info')
        except Exception as e:
            self._update_output(f"Error loading subjects: {str(e)}", 'error')

    def _on_subject_changed(self, subject_id):
        self.simulation_combo.clear()
        sims = self.simulations_dict.get(subject_id, [])
        self.simulation_combo.addItems(sims)
        self._refresh_regions()
        self._refresh_electrode_nets(subject_id)
        # Set default sub-cortical NIfTI path
        if self.pm and subject_id and hasattr(self, 'subcort_nifti_edit'):
            m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
            if m2m_dir and os.path.isdir(m2m_dir):
                default_path = str(Path(m2m_dir) / "segmentation" / "labeling.nii.gz")
                self.subcort_nifti_edit.setText(default_path)
                self.subcort_nifti_edit.setPlaceholderText(default_path)

    # Browsers
    def _browse_gm_mesh(self):
        pass

    def _browse_file_into(self, line_edit: QtWidgets.QLineEdit, filters):
        filter_str = ";;".join(filters) if filters else "All Files (*)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file", "", filter_str)
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
            if not hasattr(self, '_all_regions'):
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
            atlas = self.stl_atlas_combo.currentText().strip() if hasattr(self, 'stl_atlas_combo') else const.ATLAS_DK40
            m2m = self._m2m_dir(subject_id)
            if not subject_id or not atlas or not m2m:
                return
            # Prefer simnibs.subject_atlas if available
            try:
                import simnibs
                atlas_map = simnibs.subject_atlas(atlas, m2m)
            except Exception:
                try:
                    from simnibs.utils.transformations import subject_atlas as subj_atlas
                    atlas_map = subj_atlas(atlas, m2m)
                except Exception:
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

    def _refresh_electrode_nets(self, subject_id):
        """Refresh the electrode net combo box based on selected subject."""
        try:
            self.electrode_net_combo.clear()
            if not self.pm:
                return
            nets = self.pm.list_eeg_caps(subject_id)
            self.electrode_net_combo.addItems(nets)
            if not nets:
                self._update_output(f"Warning: No EEG nets found for subject {subject_id}", 'warning')
        except Exception as e:
            self._update_output(f"Error loading electrode nets: {str(e)}", 'error')

    def _browse_tdcs_into(self, line_edit: QtWidgets.QLineEdit):
        # Default to current simulation directory
        subject_id = self.subject_combo.currentText().strip()
        simulation_name = self.simulation_combo.currentText().strip()
        init_dir = self._simulation_dir(subject_id, simulation_name) or ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select TDCS mesh", init_dir, "Mesh Files (*.msh)")
        if path:
            line_edit.setText(path)

    def _browse_subcort_nifti(self):
        # Default to m2m segmentation directory
        subject_id = self.subject_combo.currentText().strip()
        if self.pm and subject_id:
            m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
            if m2m_dir and os.path.isdir(m2m_dir):
                init_dir = str(Path(m2m_dir) / "segmentation")
            else:
                init_dir = ""
        else:
            init_dir = ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select NIfTI file", init_dir, "NIfTI Files (*.nii *.nii.gz)")
        if path:
            self.subcort_nifti_edit.setText(path)

    def _show_lut_table(self):
        """Show a popup dialog with the labeling lookup table."""
        # Close any existing LUT dialog
        if hasattr(self, '_lut_dialog') and self._lut_dialog:
            self._lut_dialog.close()

        subject_id = self.subject_combo.currentText().strip()
        if not subject_id:
            QtWidgets.QMessageBox.warning(self, "No Subject Selected",
                                        "Please select a subject first.")
            return

        # Find the labeling_LUT.txt file
        lut_path = None
        if self.pm:
            m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
            if m2m_dir and os.path.isdir(m2m_dir):
                potential_path = Path(m2m_dir) / "segmentation" / "labeling_LUT.txt"
                if potential_path.exists():
                    lut_path = potential_path

        if not lut_path:
            QtWidgets.QMessageBox.warning(self, "LUT File Not Found",
                                        f"Could not find labeling_LUT.txt for subject {subject_id}.\n"
                                        f"Expected location: {potential_path if 'potential_path' in locals() else 'm2m/segmentation/labeling_LUT.txt'}")
            return

        # Load and parse the LUT file
        label_data = []
        try:
            with open(lut_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            try:
                                label_id = int(parts[0].strip())
                                label_name = parts[1].strip()
                                # Clean up the label name - extract only the name part before any numbers
                                import re
                                # Split on whitespace and take only the non-numeric parts at the beginning
                                name_parts = re.split(r'\s+', label_name)
                                clean_parts = []
                                for part in name_parts:
                                    # Stop when we hit a number
                                    if re.match(r'^\d+$', part):
                                        break
                                    clean_parts.append(part)
                                label_name = ' '.join(clean_parts).rstrip(':')
                                label_data.append((label_id, label_name))
                            except (ValueError, IndexError):
                                continue
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error Loading LUT",
                                         f"Failed to load labeling_LUT.txt: {str(e)}")
            return

        if not label_data:
            QtWidgets.QMessageBox.warning(self, "Empty LUT",
                                        "The labeling_LUT.txt file appears to be empty or malformed.")
            return

        # Create popup dialog
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"Label Lookup Table - {subject_id}")
        dialog.setMinimumSize(500, 400)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Add header
        header = QtWidgets.QLabel(f"<h3>Label Lookup Table</h3><p>Subject: {subject_id}</p>")
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
        dialog.finished.connect(lambda: setattr(self, '_lut_dialog', None))


    # Mode switching
    def _on_mode_changed(self):
        if self.rb_stl.isChecked():
            self.stack.setCurrentIndex(0)
        elif self.rb_vec.isChecked():
            self.stack.setCurrentIndex(1)
        elif self.rb_electrodes.isChecked():
            self.stack.setCurrentIndex(2)
        elif self.rb_subcortical.isChecked():
            self.stack.setCurrentIndex(3)

    # Paths
    def _get_project_dir(self):
        if not self.pm:
            return None
        return self.pm.project_dir

    def _simulation_dir(self, subject_id: str, simulation_name: str):
        if not self.pm:
            return None
        return self.pm.path_optional("simulation", subject_id=subject_id, simulation_name=simulation_name)

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

    def _electrode_exports_dir(self, subject_id: str):
        """Create electrode exports directory for a subject."""
        project_dir = self._get_project_dir()
        if not project_dir:
            return None
        out_base = os.path.join(
            project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            "visual_exports/",
            f"{const.PREFIX_SUBJECT}{subject_id}/electrode_exports",
        )
        os.makedirs(out_base, exist_ok=True)
        return out_base

    def _m2m_dir(self, subject_id: str):
        if not self.pm:
            return None
        return self.pm.path_optional("m2m", subject_id=subject_id)

    # Surface mesh ensuring and caching
    def _ensure_central_surface(self, subject_id: str, simulation_name: str) -> str:
        m2m_dir = self._m2m_dir(subject_id)
        if not m2m_dir:
            raise ValueError("m2m directory not found")
        # Paths from PathManager
        if not self.pm:
            raise ValueError("PathManager not available")
        central_path = self.pm.path("ti_central_surface", subject_id=subject_id, simulation_name=simulation_name)
        ti_mesh_path = self.pm.path("ti_mesh", subject_id=subject_id, simulation_name=simulation_name)
        surfaces_dir = os.path.dirname(central_path)
        os.makedirs(surfaces_dir, exist_ok=True)
        if os.path.exists(central_path):
            return central_path
        if not os.path.exists(ti_mesh_path):
            raise ValueError("Volumetric TI mesh not found; expected at: " + ti_mesh_path)
        # Generate central surface in the simulation's surfaces dir
        cmd = ["msh2cortex", "-i", ti_mesh_path, "-m", self._m2m_dir(subject_id), "-o", surfaces_dir]
        self._update_output("Generating cortical surface via msh2cortex…", 'info')
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self._update_output(completed.stdout or "", 'debug')
        if completed.returncode != 0:
            raise RuntimeError("msh2cortex failed to generate surface mesh")
        # Find any *_central.msh and rename to canonical if necessary
        produced = None
        for p in Path(surfaces_dir).glob("*_central.msh"):
            produced = str(p)
            break
        if not produced or not os.path.exists(produced):
            raise FileNotFoundError("Central surface not found after msh2cortex")
        if os.path.abspath(produced) != os.path.abspath(central_path):
            try:
                shutil.copyfile(produced, central_path)
            except Exception:
                # File copy may fail if destination already exists or permissions issue
                pass
        return central_path if os.path.exists(central_path) else produced

    # Electrode placement
    def _place_electrodes(self, subject_id: str, net_name: str, 
                          use_existing_stl: bool = False) -> None:
        """Place electrodes on scalp using ElectrodePlacer class.
        
        Args:
            subject_id: Subject identifier
            net_name: EEG net CSV filename
            use_existing_stl: If True, use existing scalp.stl; otherwise extract from .msh
        """
        # Build paths
        eeg_pos_dir = self.pm.get_eeg_positions_dir(subject_id)
        csv_path = os.path.join(eeg_pos_dir, net_name)
        electrode_blend_path = os.path.join(ti_toolbox_path, "blender", "Electrode.blend")
        output_dir = self._electrode_exports_dir(subject_id)
        
        m2m_dir = self._m2m_dir(subject_id)
        
        # Determine scalp source
        subject_msh_path = None
        scalp_stl_path = None
        
        if use_existing_stl:
            # Try to use existing scalp.stl
            existing_stl = os.path.join(m2m_dir, "scalp.stl")
            if os.path.exists(existing_stl):
                scalp_stl_path = existing_stl
                self._update_output(f"Using existing scalp STL: {existing_stl}", 'info')
            else:
                # Fall back to MSH extraction
                self._update_output("No existing scalp.stl found, extracting from MSH...", 'info')
                subject_msh_path = os.path.join(m2m_dir, f"{subject_id}.msh")
        else:
            # Extract from MSH file
            subject_msh_path = os.path.join(m2m_dir, f"{subject_id}.msh")
        
        # Validate source exists
        if subject_msh_path and not os.path.exists(subject_msh_path):
            raise FileNotFoundError(f"Subject mesh not found: {subject_msh_path}")

        # Create configuration
        config = ElectrodePlacementConfig(
            subject_id=subject_id,
            electrode_csv_path=csv_path,
            electrode_blend_path=electrode_blend_path,
            output_dir=output_dir,
            subject_msh_path=subject_msh_path,
            scalp_stl_path=scalp_stl_path,
            scale_factor=self.scale_factor_spin.value(),
            electrode_size=self.electrode_size_spin.value(),
            offset_distance=self.offset_distance_spin.value(),
            text_offset=self.text_offset_spin.value()
        )

        # Create placer and execute
        try:
            placer = ElectrodePlacer(config, logger=self.logger)
            self._update_output(f"Placing electrodes using {net_name}…", 'info')

            success, message = placer.place_electrodes()

            if success:
                self._update_output(f"\n✓ Electrode placement saved to:", 'success')
                self._update_output(f"  {output_dir}", 'info')
            else:
                raise RuntimeError(message)

        except Exception as e:
            if self.logger:
                self.logger.error(f"Electrode placement failed: {e}")
            raise

    # Vector mesh autodetect
    def _autodetect_tdcs_pair(self, subject_id: str, simulation_name: str):
        sim_dir = self._simulation_dir(subject_id, simulation_name)
        if not sim_dir or not os.path.exists(sim_dir):
            return None, None
        patterns = ["*_TDCS_1_scalar.msh", "*_TDCS_2_scalar.msh", "*_TDCS_1_*.msh", "*_TDCS_2_*.msh"]
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

        # Simulation is only required for STL and vectors modes
        if self.rb_electrodes.isChecked() or self.rb_subcortical.isChecked():
            if not subject_id:
                QtWidgets.QMessageBox.warning(self, "Missing Input", "Please select subject.")
                return
        else:
            if not subject_id or not simulation_name:
                QtWidgets.QMessageBox.warning(self, "Missing Input", "Please select subject and simulation.")
                return
        project_dir = self._get_project_dir()
        if not project_dir:
            QtWidgets.QMessageBox.warning(self, "Missing Project", "Project directory not found.")
            return

        # For electrode and sub-cortical modes, use subject directory instead of simulation-specific directory
        if self.rb_electrodes.isChecked() or self.rb_subcortical.isChecked():
            if self.rb_electrodes.isChecked():
                out_base = self._electrode_exports_dir(subject_id)
            else:  # sub-cortical
                out_base = self._visual_exports_dir(subject_id, None)  # No simulation for sub-cortical
        else:
            out_base = self._visual_exports_dir(subject_id, simulation_name)

        if not out_base:
            QtWidgets.QMessageBox.warning(self, "Output Error", "Could not create output directory.")
            return

        # Setup logger with timestamp - follows project convention: logs/sub-{subject_id}/
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = os.path.join(project_dir, const.DIR_DERIVATIVES, const.DIR_TI_TOOLBOX, "logs", f"sub-{subject_id}")
        os.makedirs(log_dir, exist_ok=True)

        if self.rb_electrodes.isChecked():
            log_file = os.path.join(log_dir, f"electrode_placement_{timestamp}.log")
        elif self.rb_subcortical.isChecked():
            log_file = os.path.join(log_dir, f"subcortical_export_{timestamp}.log")
        else:
            log_file = os.path.join(log_dir, f"visual_exporter_{simulation_name}_{timestamp}.log")

        # Create logger that only writes to file (no console output)
        self.logger = get_logger("visual_exporter", log_file=log_file, overwrite=True, console=False)

        # Show log file location in GUI
        self._update_output(f"Log file: {log_file}", 'info')

        self.logger.info(f"=== 3D Visual Exporter - {EXTENSION_NAME} ===")
        self.logger.info(f"Timestamp: {timestamp}")
        self.logger.info(f"Subject: {subject_id}")
        if simulation_name:
            self.logger.info(f"Simulation: {simulation_name}")
        self.logger.info(f"Output directory: {out_base}")
        self.logger.info(f"Log file: {log_file}")
        self.logger.info("")

        try:
            commands = []

            if self.rb_stl.isChecked():
                atlas = self.stl_atlas_combo.currentText().strip() if hasattr(self, 'stl_atlas_combo') else const.ATLAS_DK40
                field = self.stl_field_edit.text().strip() or "TI_max"
                central_surface = self._ensure_central_surface(subject_id, simulation_name)
                # Build commands for all formats (STL/PLY/MSH)
                self._prune_infos = []
                # Store selected region names once
                selected = [self.cort_regions_list.item(i).text() for i in range(self.cort_regions_list.count()) if self.cort_regions_list.item(i).isSelected()]
                self._selected_regions = selected
                # Always include whole GM
                include_whole = True

                # Always export STL
                stl_dir = os.path.join(out_base, "stl")
                os.makedirs(stl_dir, exist_ok=True)
                cmd_stl = [
                    "simnibs_python",
                    str(ti_toolbox_path / "blender" / "region_stl_exporter.py"),
                    "--mesh", central_surface,
                    "--m2m", self._m2m_dir(subject_id),
                    "--output-dir", stl_dir,
                    "--atlas", atlas,
                    "--field", field,
                ]
                # Region selection handling
                if selected:
                    cmd_stl.extend(["--regions", ",".join(selected)])
                else:
                    cmd_stl.append("--skip-regions")
                # Always keep meshes for MSH format
                cmd_stl.append("--keep-meshes")
                commands.append((cmd_stl, None))
                self._prune_infos.append({
                    'format': 'stl',
                    'mode_dir': stl_dir,
                    'include_whole': True,
                    'simulation': simulation_name,
                })

                # Always export PLY
                ply_dir = os.path.join(out_base, "ply")
                os.makedirs(ply_dir, exist_ok=True)
                cmd_ply = [
                    "simnibs_python",
                    str(ti_toolbox_path / "blender" / "region_ply_exporter.py"),
                    "--mesh", central_surface,
                    "--m2m", self._m2m_dir(subject_id),
                    "--output-dir", ply_dir,
                    "--atlas", atlas,
                    "--field", field,
                ]
                # Region selection handling
                if selected:
                    cmd_ply.extend(["--regions", ",".join(selected)])
                else:
                    cmd_ply.append("--skip-regions")
                # Always keep meshes for MSH format
                cmd_ply.append("--keep-meshes")
                commands.append((cmd_ply, None))
                self._prune_infos.append({
                    'format': 'ply',
                    'mode_dir': ply_dir,
                    'include_whole': True,
                    'simulation': simulation_name,
                })
                


            elif self.rb_vec.isChecked():
                mode_dir = os.path.join(out_base, "vectors")
                os.makedirs(mode_dir, exist_ok=True)
                # Auto-detect if not supplied
                m1 = self.vec_m1.text().strip()
                m2 = self.vec_m2.text().strip()
                if not m1 or not m2:
                    ad1, ad2 = self._autodetect_tdcs_pair(subject_id, simulation_name)
                    if not m1 and ad1:
                        m1 = ad1
                    if not m2 and ad2:
                        m2 = ad2
                if not m1 or not m2 or not os.path.exists(m1) or not os.path.exists(m2):
                    raise ValueError("TDCS meshes 1 and 2 not found. Provide files or ensure simulation outputs exist.")

                # Get central surface (required)
                try:
                    central_surface = self._ensure_central_surface(subject_id, simulation_name)
                    if not central_surface or not os.path.exists(central_surface):
                        raise ValueError("Central surface mesh is required but could not be generated")
                except Exception as e:
                    raise ValueError(f"Failed to get central surface: {e}")
                
                # Use output directory as prefix (vectors will be named TI.ply, CH1.ply, etc.)
                cmd = [
                    "simnibs_python",
                    str(ti_toolbox_path / "blender" / "vector_field_exporter.py"),
                    m1,
                    m2,
                    mode_dir,  # Output directory
                    "--central-surface", central_surface,
                ]
                
                if self.vec_enable_mti.isChecked():
                    m3 = self.vec_m3.text().strip()
                    m4 = self.vec_m4.text().strip()
                    if not (m3 and m4 and os.path.exists(m3) and os.path.exists(m4)):
                        raise ValueError("mTI enabled: TDCS meshes 3 and 4 required.")
                    cmd.extend(["--mti", m3, m4])
                
                # Export CH1/CH2 if requested
                if self.vec_export_ch1_ch2.isChecked():
                    cmd.append("--export-ch1-ch2")
                
                if self.vec_do_sum.isChecked():
                    cmd.append("--sum")
                if self.vec_do_ti_normal.isChecked():
                    cmd.append("--ti-normal")
                # Color scale
                color_mode = self.vec_color_mode.currentText().strip()
                if color_mode:
                    cmd.extend(["--color", color_mode])
                    if color_mode == "magscale":
                        cmd.extend(["--blue-percentile", str(self.spn_blue.value())])
                        cmd.extend(["--green-percentile", str(self.spn_green.value())])
                        cmd.extend(["--red-percentile", str(self.spn_red.value())])
                if getattr(self, 'vec_all_nodes', None) and self.vec_all_nodes.isChecked():
                    cmd.append("--all-nodes")
                else:
                    cmd.extend(["--count", str(self.vec_count.value())])
                cmd.extend(["--seed", str(self.vec_seed.value())])
                cmd.extend(["--length-scale", str(self.vec_length_scale.value())])
                # Hidden defaults for normalized visuals
                cmd.extend(["--vector-scale", "1.0"])
                cmd.extend(["--vector-width", str(self.vec_vector_width.value())])
                cmd.extend(["--vector-length", "1.0"])
                cmd.extend(["--anchor", self.vec_anchor.currentText()])
                commands.append((cmd, None))

            elif self.rb_electrodes.isChecked():
                # Electrode placement mode - runs synchronously (not via worker thread)
                self.logger.info("=== Electrode Placement Mode ===")
                
                # Check if Blender is available
                blender_available = any(shutil.which(cmd) for cmd in ["blender", "simnibs_blender"])
                if not blender_available:
                    raise ValueError(
                        "Blender is not installed by default. Electrode placement feature requires Blender.\n"
                        "Install Blender by running: bash tit/blender/install_blender_docker.sh\n"
                    )
                
                net_name = self.electrode_net_combo.currentText().strip()

                if not net_name:
                    raise ValueError("Please select an EEG net")

                self.logger.info(f"EEG Net: {net_name}")

                # Place electrodes (always extract fresh scalp STL from MSH)
                self.logger.info("Placing electrodes...")
                # Suppress stdout/stderr during electrode placement to avoid Blender output
                import sys
                import io
                from contextlib import redirect_stdout, redirect_stderr

                # Capture stdout and stderr
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()

                try:
                    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                        self._place_electrodes(subject_id, net_name, use_existing_stl=False)
                finally:
                    # Log any captured output to the file logger (not console)
                    stdout_content = stdout_capture.getvalue()
                    stderr_content = stderr_capture.getvalue()
                    if stdout_content.strip():
                        self.logger.debug(f"Electrode placement stdout: {stdout_content}")
                    if stderr_content.strip():
                        self.logger.debug(f"Electrode placement stderr: {stderr_content}")

                # Electrode mode completes immediately (no worker thread needed)
                self.logger.info("")
                self.logger.info("========================================")
                self.logger.info("EXPORT COMPLETE")
                self.logger.info("========================================")
                self._update_output("\n========================================", 'success')
                self._update_output("EXPORT COMPLETE", 'success')
                self._update_output("========================================", 'success')
                return  # Exit early for electrode mode

            elif self.rb_subcortical.isChecked():
                # Sub-cortical mesh export mode - runs synchronously using Python functions
                self.logger.info("=== Sub-cortical Mesh Export Mode ===")

                # Get NIfTI file path
                nifti_path = self.subcort_nifti_edit.text().strip()
                if not nifti_path:
                    # Use default path
                    if self.pm:
                        m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
                        if m2m_dir and os.path.isdir(m2m_dir):
                            nifti_path = str(Path(m2m_dir) / "segmentation" / "labeling.nii.gz")
                        else:
                            raise ValueError("Could not determine default NIfTI path. Please specify manually.")
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
                        extracted_path = extract_labels_from_nifti(nifti_path, labels, temp_nifti)
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
                        clean_threshold=0.1
                    )
                    self.logger.info(f"STL created: {stl_result['output_file']} "
                                   f"({stl_result['vertices']} vertices, {stl_result['faces']} faces)")
                    if stl_result['removed_components'] > 0:
                        self.logger.info(f"Removed {stl_result['removed_components']} small components")

                    # Export MSH
                    msh_output = os.path.join(output_dir, f"subcortical_{suffix}.msh")
                    self.logger.info("Generating MSH mesh...")
                    msh_result = nifti_to_mesh(
                        input_file,
                        msh_output,
                        clean_components=clean_components,
                        clean_threshold=0.1
                    )
                    self.logger.info(f"MSH created: {msh_result['output_file']} "
                                   f"({msh_result['vertices']} vertices, {msh_result['faces']} faces)")
                    if msh_result['removed_components'] > 0:
                        self.logger.info(f"Removed {msh_result['removed_components']} small components")

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
                self._update_output("\n========================================", 'success')
                self._update_output("EXPORT COMPLETE", 'success')
                self._update_output("========================================", 'success')
                return  # Exit early for sub-cortical mode

            # Run worker thread for STL/Vector modes
            if commands:
                self.logger.info(f"Starting worker thread with {len(commands)} command(s)...")
                self._start_worker(commands)
            else:
                self.logger.warning("No commands to execute")
                self._update_output("No export operations selected", 'warning')
        except Exception as e:
            self._update_output(str(e), 'error')
            QtWidgets.QMessageBox.critical(self, "Run Error", str(e))

    def _start_worker(self, commands):
        if hasattr(self, 'console_widget') and self.console_widget:
            self.console_widget.clear_console()
        self._update_output("Starting export…", 'info')
        self.action_buttons.enable_stop()
        self.worker_thread = WorkerThread(commands)
        self.worker_thread.output_signal.connect(lambda m: self._update_output(m, 'default'))
        self.worker_thread.finished_signal.connect(self._on_finished)
        self.worker_thread.error_signal.connect(self._on_error)
        self.worker_thread.start()

    def _stop(self):
        if hasattr(self, 'worker_thread') and self.worker_thread and self.worker_thread.isRunning():
            self._update_output("\nStopping…", 'warning')
            try:
                self.worker_thread.terminate_and_wait()
            finally:
                self.worker_thread.terminate()
                self.worker_thread.wait()
            self._update_output("Stopped by user.", 'warning')
            self.action_buttons.enable_run()

    def _on_finished(self, code):
        self.action_buttons.enable_run()
        self._update_output("\n========================================", 'success')
        self._update_output("EXPORT COMPLETE", 'success')
        self._update_output("========================================", 'success')
        # Post-process: keep only selected cortical regions for each generated format
        try:
            infos = getattr(self, '_prune_infos', []) or []
            sel_list = getattr(self, '_selected_regions', None)
            if not sel_list:
                return
            sel = set(sel_list)
            for info in infos:
                if info['format'] == 'stl':
                    regions_dir = os.path.join(info['mode_dir'], 'cortical_stls', 'regions')
                    if os.path.isdir(regions_dir):
                        for f in os.listdir(regions_dir):
                            if f.lower().endswith('.stl'):
                                name = os.path.splitext(f)[0]
                                if name not in sel:
                                    try:
                                        os.remove(os.path.join(regions_dir, f))
                                    except OSError:
                                        # File may be in use or already deleted
                                        pass
                else:
                    regions_dir = os.path.join(info['mode_dir'], 'cortical_plys', 'regions')
                    if os.path.isdir(regions_dir):
                        for f in os.listdir(regions_dir):
                            if f.lower().endswith('.ply'):
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
        self._update_output("\n========================================", 'error')
        self._update_output("ERROR", 'error')
        self._update_output("========================================", 'error')
        self._update_output(err, 'error')
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


