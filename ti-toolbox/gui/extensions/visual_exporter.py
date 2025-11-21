#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: 3D Visual Exporter
Export STL/PLY cortical regions & vector clouds of simulation results.
"""

import os
import sys
import shutil
import subprocess
import tempfile
import glob
from pathlib import Path
from PyQt5 import QtWidgets, QtCore

# Extension metadata (required)
EXTENSION_NAME = "3D Visual Exporter"
EXTENSION_DESCRIPTION = "Export STL/PLY cortical regions & vector clouds of simulations"

# Add TI-Toolbox to path
ti_toolbox_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ti_toolbox_path))

# Add GUI path for components
gui_path = Path(__file__).parent.parent
sys.path.insert(0, str(gui_path))

from core import get_path_manager
from core import constants as const

from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons


class Mode:
    STL = "STL"
    PLY = "PLY"
    VECTORS = "VECTORS"


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
            pass


class VisualExporterWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.pm = get_path_manager() if get_path_manager else None

        self.subjects_list = []
        self.simulations_dict = {}

        self._setup_ui()
        self._load_subjects()

    # UI setup
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        header_label = QtWidgets.QLabel("<h2>3D Visual Exporter</h2>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)

        desc = QtWidgets.QLabel(
            "Export cortical regions to STL/PLY and vector clouds (TI/mTI) for Blender visualization."
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
        self.rb_stl.setChecked(True)
        # Help buttons for modes
        self.btn_help_stl = QtWidgets.QToolButton()
        self.btn_help_stl.setText("?")
        self.btn_help_stl.setAutoRaise(True)
        self.btn_help_stl.setToolTip(
            "Export cortical ROI surfaces from a SimNIBS mesh to STL/PLY using the selected atlas.\n"
            "Select specific regions and optionally include the whole GM surface."
        )
        self.btn_help_vec = QtWidgets.QToolButton()
        self.btn_help_vec.setText("?")
        self.btn_help_vec.setAutoRaise(True)
        self.btn_help_vec.setToolTip(
            "Export TI/mTI vector arrows to PLY from TDCS field meshes.\n"
            "Supports sampling, scaling, width, anchor, and optional SUM/TI_normal."
        )

        # Row: [Cortical Regions] [?]   [Field Vectors] [?]
        radio_layout.addWidget(self.rb_stl)
        radio_layout.addWidget(self.btn_help_stl)
        radio_layout.addSpacing(12)
        radio_layout.addWidget(self.rb_vec)
        radio_layout.addWidget(self.btn_help_vec)
        radio_layout.addStretch()
        mvl.addLayout(radio_layout)

        self.stack = QtWidgets.QStackedWidget()
        mvl.addWidget(self.stack)
        layout.addWidget(mode_group)

        self._build_stl_panel()
        self._build_vectors_panel()

        self.rb_stl.toggled.connect(lambda v: self._on_mode_changed())
        self.rb_vec.toggled.connect(lambda v: self._on_mode_changed())
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
        btns.addStretch()
        rb_layout.addLayout(btns)
        self.cort_regions_list = QtWidgets.QListWidget()
        self.cort_regions_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        rb_layout.addWidget(self.cort_regions_list)
        self.cort_whole_gm = QtWidgets.QCheckBox("Include Whole GM")
        self.cort_whole_gm.setChecked(True)
        rb_layout.addWidget(self.cort_whole_gm)
        gl.addWidget(regions_box, r, 0, 1, 4)
        r += 1
        # Output format
        fmt_box = QtWidgets.QGroupBox("Output formats")
        fmt_layout = QtWidgets.QHBoxLayout(fmt_box)
        self.cort_fmt_stl = QtWidgets.QCheckBox("STL")
        self.cort_fmt_ply = QtWidgets.QCheckBox("PLY")
        # Default to both formats enabled
        self.cort_fmt_stl.setChecked(True)
        self.cort_fmt_ply.setChecked(True)
        fmt_layout.addWidget(self.cort_fmt_stl)
        fmt_layout.addWidget(self.cort_fmt_ply)
        gl.addWidget(fmt_box, r, 0, 1, 4)
        r += 1
        # Wire buttons
        self.btn_regions_sel_all.clicked.connect(lambda: self._regions_select_all(True))
        self.btn_regions_clear.clicked.connect(lambda: self._regions_select_all(False))
        # Keep meshes option (applies if supported by backend)
        self.stl_keep_meshes = QtWidgets.QCheckBox("Keep ROI meshes (.msh)")
        gl.addWidget(self.stl_keep_meshes, r, 0)
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
                sim_dir = self.pm.get_subject_dir(subject_id)
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
            # Populate list
            self.cort_regions_list.clear()
            for name in names:
                item = QtWidgets.QListWidgetItem(name)
                self.cort_regions_list.addItem(item)
        except Exception:
            pass

    def _browse_tdcs_into(self, line_edit: QtWidgets.QLineEdit):
        # Default to current simulation directory
        subject_id = self.subject_combo.currentText().strip()
        simulation_name = self.simulation_combo.currentText().strip()
        init_dir = self._simulation_dir(subject_id, simulation_name) or ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select TDCS mesh", init_dir, "Mesh Files (*.msh)")
        if path:
            line_edit.setText(path)

    # Mode switching
    def _on_mode_changed(self):
        if self.rb_stl.isChecked():
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)

    # Paths
    def _get_project_dir(self):
        if not self.pm:
            return None
        return self.pm.get_project_dir()

    def _simulation_dir(self, subject_id: str, simulation_name: str):
        if not self.pm:
            return None
        return self.pm.get_simulation_dir(subject_id, simulation_name)

    def _visual_exports_dir(self, subject_id: str, simulation_name: str):
        project_dir = self._get_project_dir()
        if not project_dir:
            return None
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
        return self.pm.get_m2m_dir(subject_id)

    # Surface mesh ensuring and caching
    def _ensure_central_surface(self, subject_id: str, simulation_name: str) -> str:
        m2m_dir = self._m2m_dir(subject_id)
        if not m2m_dir:
            raise ValueError("m2m directory not found")
        # Paths from PathManager
        if not self.pm or not hasattr(self.pm, 'get_ti_central_surface_path') or not hasattr(self.pm, 'get_ti_mesh_path'):
            raise ValueError("PathManager does not provide TI mesh path helpers")
        central_path = self.pm.get_ti_central_surface_path(subject_id, simulation_name)
        ti_mesh_path = self.pm.get_ti_mesh_path(subject_id, simulation_name)
        if not central_path or not ti_mesh_path:
            raise ValueError("Unable to resolve TI mesh paths from PathManager")
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
                pass
        return central_path if os.path.exists(central_path) else produced

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
        if not subject_id or not simulation_name:
            QtWidgets.QMessageBox.warning(self, "Missing Input", "Please select subject and simulation.")
            return
        project_dir = self._get_project_dir()
        if not project_dir:
            QtWidgets.QMessageBox.warning(self, "Missing Project", "Project directory not found.")
            return

        out_base = self._visual_exports_dir(subject_id, simulation_name)
        if not out_base:
            QtWidgets.QMessageBox.warning(self, "Output Error", "Could not create output directory.")
            return

        try:
            commands = []

            if self.rb_stl.isChecked():
                atlas = self.stl_atlas_combo.currentText().strip() if hasattr(self, 'stl_atlas_combo') else const.ATLAS_DK40
                field = self.stl_field_edit.text().strip() or "TI_max"
                central_surface = self._ensure_central_surface(subject_id, simulation_name)
                # Build commands for selected formats (STL/PLY)
                self._prune_infos = []
                # Store selected region names once
                selected = [self.cort_regions_list.item(i).text() for i in range(self.cort_regions_list.count()) if self.cort_regions_list.item(i).isSelected()]
                self._selected_regions = selected
                include_whole = self.cort_whole_gm.isChecked()
                if self.cort_fmt_stl.isChecked():
                    stl_dir = os.path.join(out_base, "stl")
                    os.makedirs(stl_dir, exist_ok=True)
                    cmd_stl = [
                        "simnibs_python",
                        str(ti_toolbox_path / "3d_exporter" / "cortical_regions_to_stl.py"),
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
                    # Whole GM handling
                    if not include_whole:
                        cmd_stl.append("--skip-whole-gm")
                    if self.stl_keep_meshes.isChecked():
                        cmd_stl.append("--keep-meshes")
                    commands.append((cmd_stl, None))
                    self._prune_infos.append({
                        'format': 'stl',
                        'mode_dir': stl_dir,
                        'include_whole': self.cort_whole_gm.isChecked(),
                        'simulation': simulation_name,
                    })
                if self.cort_fmt_ply.isChecked():
                    ply_dir = os.path.join(out_base, "ply")
                    os.makedirs(ply_dir, exist_ok=True)
                    cmd_ply = [
                        "simnibs_python",
                        str(ti_toolbox_path / "3d_exporter" / "cortical_regions_to_ply.py"),
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
                    # Whole GM handling
                    if not include_whole:
                        cmd_ply.append("--skip-whole-gm")
                    if self.stl_keep_meshes.isChecked():
                        cmd_ply.append("--keep-meshes")
                    commands.append((cmd_ply, None))
                    self._prune_infos.append({
                        'format': 'ply',
                        'mode_dir': ply_dir,
                        'include_whole': self.cort_whole_gm.isChecked(),
                        'simulation': simulation_name,
                    })
                
            

            else:
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
                    str(ti_toolbox_path / "3d_exporter" / "vector_ply.py"),
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

            # Run
            self._start_worker(commands)
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
                                    except Exception:
                                        pass
                    if not info.get('include_whole'):
                        try:
                            os.remove(os.path.join(info['mode_dir'], 'cortical_stls', 'whole_gm.stl'))
                        except Exception:
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
                                    except Exception:
                                        pass
                    if not info.get('include_whole'):
                        try:
                            os.remove(os.path.join(info['mode_dir'], 'cortical_plys', 'whole_gm.ply'))
                        except Exception:
                            pass
        except Exception:
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


