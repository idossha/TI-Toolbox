#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Simulator Tab
This module provides a GUI interface for the simulator functionality.
"""

import os
import json
import re
import subprocess
import signal
import sys
import time
from pathlib import Path
import datetime
import tempfile
import shutil

from PyQt5 import QtWidgets, QtCore, QtGui
from tit.gui.confirmation_dialog import ConfirmationDialog
from tit.gui.utils import is_important_message
from tit.gui.components.console import ConsoleWidget
from tit.gui.components.action_buttons import RunStopButtons
from tit.gui.components.base_thread import detect_message_type_from_content
from tit.core import get_path_manager, constants as const
from tit.reporting import SimulationReportGenerator
from tit.gui.style import FONT_MD, FONT_SUBHEADING, _gfx_tokens  # graphics tokens

# Import the refactored simulation dataclasses
from tit.sim import (
    SimulationConfig,
    ElectrodeConfig,
    IntensityConfig,
    MontageConfig,
    ConductivityType,
    ParallelConfig,
)

# Utility: strip ANSI/VT100 escape sequences from text (e.g., "\x1b[0;32m")
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color/control sequences from a string."""
    if not text:
        return text
    # Remove standard CSI sequences
    cleaned = ANSI_ESCAPE_PATTERN.sub("", text)
    # Remove any stray ESC characters that might remain
    cleaned = cleaned.replace("\x1b", "")
    return cleaned


class SubprocessSimulationProcess(QtCore.QObject):
    """
    Run the simulation pipeline in a separate process (QProcess) so it can be hard-killed.

    Interface intentionally mirrors the old thread usage:
    - output_signal(str, str)
    - error_signal(str)
    - finished (Qt signal)
    - start()
    - terminate_simulation() / terminate_process()
    - get_results()
    """

    output_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()

    def __init__(self, payload: dict, parent_tab=None):
        super().__init__(parent_tab)
        self.parent_tab = parent_tab
        self.payload = payload

        self._temp_dir = tempfile.mkdtemp(prefix="ti_sim_qprocess_")
        self._config_path = os.path.join(self._temp_dir, "sim_config.json")
        self._results_path = os.path.join(self._temp_dir, "sim_results.json")

        self._results = []
        self._log_file = None
        self._terminated = False
        self._buffer = ""

        self.qprocess = QtCore.QProcess(self)
        self.qprocess.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.qprocess.readyReadStandardOutput.connect(self._on_ready_read)
        self.qprocess.errorOccurred.connect(self._on_error)
        self.qprocess.finished.connect(self._on_finished)

        # Ensure unbuffered python output for real-time GUI streaming
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONFAULTHANDLER", "1")
        self.qprocess.setProcessEnvironment(env)

    def start(self):
        """Start the subprocess simulation."""
        try:
            with open(self._config_path, "w") as f:
                json.dump(self.payload, f)

            program = "simnibs_python"
            args = [
                "-m",
                "tit.sim.subprocess_runner",
                "--config",
                self._config_path,
                "--results",
                self._results_path,
            ]
            self.qprocess.start(program, args)
        except Exception as e:
            self.error_signal.emit(f"Failed to start simulation subprocess: {e}")
            self.finished.emit()

    def _emit_line(self, line: str):
        line = strip_ansi_codes(line)
        if not line.strip():
            return
        msg_type = detect_message_type_from_content(line)
        self.output_signal.emit(line, msg_type)

    def _on_ready_read(self):
        try:
            data = bytes(self.qprocess.readAllStandardOutput()).decode(errors="replace")
        except Exception:
            data = ""
        if not data:
            return
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit_line(line)

    def _on_error(self, _err):
        try:
            msg = (
                f"Subprocess error occurred (state={self.qprocess.state()} code={_err})"
            )
        except Exception:
            msg = "Subprocess error occurred"
        self.error_signal.emit(msg)

    def _read_results_file(self):
        if not os.path.exists(self._results_path):
            return None
        try:
            with open(self._results_path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _cleanup_temp(self):
        # Use ignore_errors=True parameter - no need for try-except
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _on_finished(self, exit_code, exit_status):
        # Flush any remaining buffered output
        if self._buffer.strip():
            for line in self._buffer.splitlines():
                self._emit_line(line)
        self._buffer = ""

        payload = self._read_results_file() or {}
        self._log_file = payload.get("log_file")

        results = payload.get("results")
        if isinstance(results, list):
            self._results = results
        else:
            # Fall back to a single failed result if process ended unexpectedly
            if (
                exit_code != 0
                or exit_status != QtCore.QProcess.NormalExit
                or payload.get("status") == "failed"
            ):
                err = (
                    payload.get("error")
                    or f"Simulation subprocess failed (exit_code={exit_code})"
                )
                self._results = [
                    {"montage_name": "unknown", "status": "failed", "error": err}
                ]
            else:
                self._results = []

        # Clean temp files after parsing results
        self._cleanup_temp()
        self.finished.emit()

    def get_results(self):
        return self._results

    def get_log_file(self):
        return self._log_file

    def terminate_process(self):
        """Alias used by some error-abort code paths."""
        return self.terminate_simulation()

    def terminate_simulation(self):
        """
        Hard-stop the simulation.

        We SIGKILL the *process group* (Linux container), ensuring child workers die too.
        The runner sets its own pgid = pid, so killpg(pid) targets the full tree.
        """
        self._terminated = True
        try:
            pid = int(self.qprocess.processId())
        except Exception:
            pid = 0

        # Hard kill process group first (best-effort)
        if pid > 0 and os.name != "nt":
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass  # Process group may already be terminated

        # Also kill the main process
        try:
            if self.qprocess.state() != QtCore.QProcess.NotRunning:
                self.qprocess.kill()
        except (RuntimeError, OSError):
            pass  # QProcess may already be destroyed or process already dead
        return True


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
        self._had_errors_during_run = False
        self._aborting_due_to_error = False
        self._current_run_subjects = []
        self._current_run_is_montage = True
        self._current_run_montages = []
        # Job-based execution (simulation = subject × montage/config)
        self._job_queue = []
        self._active_processes = set()
        self._process_to_job = {}
        self._max_concurrent_jobs = 1
        self._run_start_time = None
        self._project_dir_path_current = None
        # Per-job selection state
        self._job_selections = {}   # row_index -> list[str] of selected item texts
        self._job_cards: list = []
        self._selected_card_idx: int = -1
        # Initialize debug mode (default to False)
        self.debug_mode = False
        # Initialize path manager
        self.pm = get_path_manager()
        self.setup_ui()

        # Populate subjects/EEG nets after UI is ready
        QtCore.QTimer.singleShot(500, self._load_available_subjects)

    def setup_ui(self):
        """Set up the user interface for the simulator tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # Scroll area for the top form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(200)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)

        # ── Section 1: Simulation Jobs ─────────────────────────────────────
        jobs_group = QtWidgets.QGroupBox("Simulation Jobs")
        jobs_outer = QtWidgets.QVBoxLayout(jobs_group)

        # Card-based job list inside a scroll area
        self.jobs_scroll = QtWidgets.QScrollArea()
        self.jobs_scroll.setWidgetResizable(True)
        self.jobs_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.jobs_scroll.setMinimumHeight(180)
        self.jobs_scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.jobs_container = QtWidgets.QWidget()
        self.jobs_layout = QtWidgets.QVBoxLayout(self.jobs_container)
        self.jobs_layout.setContentsMargins(4, 4, 4, 4)
        self.jobs_layout.setSpacing(4)
        self.jobs_layout.addStretch()   # keeps cards pushed to top
        self.jobs_scroll.setWidget(self.jobs_container)
        jobs_outer.addWidget(self.jobs_scroll)

        # Bottom button row
        jobs_footer = QtWidgets.QHBoxLayout()
        self.add_job_btn = QtWidgets.QPushButton("+ Add Job")
        self.add_job_btn.clicked.connect(lambda: self._add_job_row())
        self.remove_job_btn = QtWidgets.QPushButton("Remove Selected")
        self.remove_job_btn.clicked.connect(self._remove_selected_job_row)
        jobs_footer.addStretch()
        jobs_footer.addWidget(self.add_job_btn)
        jobs_footer.addWidget(self.remove_job_btn)
        jobs_outer.addLayout(jobs_footer)

        # ── Section 2: Selection panel ─────────────────────────────────────
        selection_group = QtWidgets.QGroupBox("Montage / Flex-Search Selection")
        selection_outer = QtWidgets.QVBoxLayout(selection_group)

        self.selection_label = QtWidgets.QLabel("Select a job row above")
        selection_outer.addWidget(self.selection_label)

        self.selection_list = QtWidgets.QListWidget()
        self.selection_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.selection_list.setMinimumHeight(120)
        self.selection_list.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.selection_list.itemSelectionChanged.connect(
            self._save_selection_for_current_row
        )
        selection_outer.addWidget(self.selection_list)

        sel_btn_row = QtWidgets.QHBoxLayout()
        self.refresh_selection_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_selection_btn.clicked.connect(self._refresh_selection_list)
        self.clear_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_selection_btn.clicked.connect(self._clear_selection)
        self.add_montage_sel_btn = QtWidgets.QPushButton("Add Montage")
        self.add_montage_sel_btn.clicked.connect(self.show_add_montage_dialog)
        self.remove_montage_sel_btn = QtWidgets.QPushButton("Remove Montage")
        self.remove_montage_sel_btn.clicked.connect(self.remove_selected_montage)
        sel_btn_row.addWidget(self.refresh_selection_btn)
        sel_btn_row.addWidget(self.clear_selection_btn)
        sel_btn_row.addSpacing(16)
        sel_btn_row.addWidget(self.add_montage_sel_btn)
        sel_btn_row.addWidget(self.remove_montage_sel_btn)
        sel_btn_row.addStretch()
        selection_outer.addLayout(sel_btn_row)

        # ── Section 3: Global Parameters ───────────────────────────────────
        global_group = QtWidgets.QGroupBox("Global Parameters")
        global_layout = QtWidgets.QVBoxLayout(global_group)
        global_layout.setContentsMargins(8, 4, 8, 4)
        global_layout.setSpacing(3)

        # Row 1: Anisotropy + conductivity editor
        row1 = QtWidgets.QHBoxLayout()
        self.sim_type_label = QtWidgets.QLabel("Anisotropy:")
        self.sim_type_combo = QtWidgets.QComboBox()
        self.sim_type_combo.addItem("Isotropic", "scalar")
        self.sim_type_combo.addItem("Anisotropic (vn)", "vn")
        self.sim_type_combo.addItem("Anisotropic (dir)", "dir")
        self.sim_type_combo.addItem("Anisotropic (mc)", "mc")
        self.conductivity_editor_btn = QtWidgets.QPushButton("Change Default Cond.")
        self.conductivity_editor_btn.clicked.connect(self.show_conductivity_editor)
        row1.addWidget(self.sim_type_label)
        row1.addWidget(self.sim_type_combo)
        row1.addSpacing(8)
        row1.addWidget(self.conductivity_editor_btn)
        row1.addStretch()
        global_layout.addLayout(row1)
        # Hidden master EEG net combo – keeps AddMontageDialog working
        self.eeg_net_combo = QtWidgets.QComboBox()
        self.eeg_net_combo.setVisible(False)

        # Row 2a: Electrode shape
        row2 = QtWidgets.QHBoxLayout()
        self.electrode_shape_label = QtWidgets.QLabel("Electrode Shape:")
        self.electrode_shape_rect = QtWidgets.QRadioButton("Rectangle")
        self.electrode_shape_rect.setProperty("value", "rect")
        self.electrode_shape_ellipse = QtWidgets.QRadioButton("Ellipse")
        self.electrode_shape_ellipse.setProperty("value", "ellipse")
        self.electrode_shape_ellipse.setChecked(True)
        row2.addWidget(self.electrode_shape_label)
        row2.addWidget(self.electrode_shape_rect)
        row2.addWidget(self.electrode_shape_ellipse)
        row2.addStretch()
        global_layout.addLayout(row2)

        # Row 2b: Dimensions + thickness
        row2b = QtWidgets.QHBoxLayout()
        self.dimensions_label = QtWidgets.QLabel("Dimensions (mm, x,y):")
        self.dimensions_input = QtWidgets.QLineEdit()
        self.dimensions_input.setPlaceholderText("8,8")
        self.dimensions_input.setText("8,8")
        self.dimensions_input.setMaximumWidth(60)
        self.thickness_label = QtWidgets.QLabel("Thickness (mm):")
        self.thickness_input = QtWidgets.QLineEdit()
        self.thickness_input.setPlaceholderText("4")
        self.thickness_input.setText("4")
        self.thickness_input.setMaximumWidth(44)
        row2b.addWidget(self.dimensions_label)
        row2b.addWidget(self.dimensions_input)
        row2b.addSpacing(8)
        row2b.addWidget(self.thickness_label)
        row2b.addWidget(self.thickness_input)
        row2b.addStretch()
        global_layout.addLayout(row2b)

        # Row 3: Parallel execution
        row3 = QtWidgets.QHBoxLayout()
        self.parallel_checkbox = QtWidgets.QCheckBox("Parallel Execution")
        self.parallel_checkbox.setToolTip(
            "Run multiple montage simulations in parallel using multiple CPU cores"
        )
        self.parallel_checkbox.setChecked(False)
        self.parallel_workers_label = QtWidgets.QLabel("Workers:")
        self.parallel_workers_label.setEnabled(False)

        import os as _os
        default_workers = max(1, (_os.cpu_count() or 4) // 2)
        self.parallel_workers_spin = QtWidgets.QSpinBox()
        self.parallel_workers_spin.setRange(1, _os.cpu_count() or 8)
        self.parallel_workers_spin.setValue(default_workers)
        self.parallel_workers_spin.setToolTip(
            f"Number of parallel workers (CPU cores: {_os.cpu_count() or 'unknown'})"
        )
        self.parallel_workers_spin.setEnabled(False)
        self.parallel_workers_spin.setMinimumWidth(52)
        self.parallel_workers_spin.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
        )
        self.parallel_checkbox.toggled.connect(
            lambda checked: (
                self.parallel_workers_label.setEnabled(checked),
                self.parallel_workers_spin.setEnabled(checked),
            )
        )
        row3.addWidget(self.parallel_checkbox)
        row3.addWidget(self.parallel_workers_label)
        row3.addWidget(self.parallel_workers_spin)
        row3.addStretch()
        global_layout.addLayout(row3)

        # ── Assemble 2-column layout ───────────────────────────────────────
        # Right panel: Montage/Flex selection on top, Global Parameters below
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(selection_group, 1)   # stretch=1: takes remaining height
        right_layout.addWidget(global_group, 0)      # stretch=0: compact, natural height

        # Outer horizontal splitter: Jobs (left, full height) | right panel
        outer_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        outer_splitter.setChildrenCollapsible(False)
        outer_splitter.addWidget(jobs_group)
        outer_splitter.addWidget(right_panel)
        outer_splitter.setStretchFactor(0, 3)
        outer_splitter.setStretchFactor(1, 1)
        outer_splitter.setMinimumHeight(340)
        scroll_layout.addWidget(outer_splitter)

        # Set scroll content
        scroll_area.setWidget(scroll_content)

        # Run/Stop buttons
        self.action_buttons = RunStopButtons(
            self, run_text="Run Simulation", stop_text="Stop Simulation"
        )
        self.action_buttons.connect_run(self.run_simulation)
        self.action_buttons.connect_stop(self.stop_simulation)
        self.run_btn = self.action_buttons.get_run_button()
        self.stop_btn = self.action_buttons.get_stop_button()

        # Console widget
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            show_debug_checkbox=True,
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
        self.console_widget.debug_checkbox.toggled.connect(self.set_debug_mode)
        self.output_console = self.console_widget.get_console_widget()

        # Hidden legacy group (AddMontageDialog compatibility)
        self.montage_group = QtWidgets.QGroupBox("Add New Montage")
        self.montage_group.setVisible(False)
        self.montage_content = QtWidgets.QWidget()

        # Stacked widget (used by AddMontageDialog reference)
        self.electrode_stacked_widget = QtWidgets.QStackedWidget()
        self.uni_electrode_widget = QtWidgets.QWidget()
        uni_electrode_layout = QtWidgets.QVBoxLayout(self.uni_electrode_widget)
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
        self.multi_electrode_widget = QtWidgets.QWidget()
        multi_electrode_layout = QtWidgets.QVBoxLayout(self.multi_electrode_widget)
        for i in range(1, 5):
            pair_layout = QtWidgets.QHBoxLayout()
            pair_label = QtWidgets.QLabel(f"Pair {i}:")
            e1 = QtWidgets.QLineEdit()
            e1.setPlaceholderText(f"E{10+2*(i-1)}")
            e2 = QtWidgets.QLineEdit()
            e2.setPlaceholderText(f"E{11+2*(i-1)}")
            setattr(self, f"multi_pair{i}_e1", e1)
            setattr(self, f"multi_pair{i}_e2", e2)
            pair_layout.addWidget(pair_label)
            pair_layout.addWidget(e1)
            pair_layout.addWidget(QtWidgets.QLabel("→"))
            pair_layout.addWidget(e2)
            multi_electrode_layout.addLayout(pair_layout)
        self.electrode_stacked_widget.addWidget(self.uni_electrode_widget)
        self.electrode_stacked_widget.addWidget(self.multi_electrode_widget)

    # ── Subject / EEG net loading ──────────────────────────────────────────

    def _load_available_subjects(self):
        """Load available subjects and EEG nets; populate any existing job rows."""
        try:
            self.eeg_net_combo.clear()
            subjects = self.pm.list_subjects()

            for subject_id in subjects:
                eeg_caps = self.pm.list_eeg_caps(subject_id)
                for net_file in eeg_caps:
                    if net_file not in [
                        self.eeg_net_combo.itemText(i)
                        for i in range(self.eeg_net_combo.count())
                    ]:
                        self.eeg_net_combo.addItem(net_file)

            if self.eeg_net_combo.count() == 0:
                self.eeg_net_combo.addItem("GSN-HydroCel-185.csv")

            # Refresh subject and EEG net combos in existing job cards
            eeg_nets = [self.eeg_net_combo.itemText(i) for i in range(self.eeg_net_combo.count())]
            for card in self._job_cards:
                current_subj = card.subject_combo.currentText()
                card.subject_combo.blockSignals(True)
                card.subject_combo.clear()
                card.subject_combo.addItems(subjects)
                idx = card.subject_combo.findText(current_subj)
                if idx >= 0:
                    card.subject_combo.setCurrentIndex(idx)
                card.subject_combo.blockSignals(False)

                current_net = card.eeg_net_combo.currentText()
                card.eeg_net_combo.blockSignals(True)
                card.eeg_net_combo.clear()
                card.eeg_net_combo.addItems(eeg_nets)
                idx = card.eeg_net_combo.findText(current_net)
                if idx >= 0:
                    card.eeg_net_combo.setCurrentIndex(idx)
                card.eeg_net_combo.blockSignals(False)

        except Exception as e:
            print(f"Error loading subjects: {e}")

    def _get_available_subjects(self):
        """Return sorted list of available subject IDs."""
        try:
            return self.pm.list_subjects()
        except Exception:
            return []

    # ── Job table management ────────────────────────────────────────────────

    def _add_job_row(self, subject=None, source="Montage", mode="U",
                     currents="1.0,1.0", eeg_net=None):
        """Append a new simulation job card to the list."""
        idx = len(self._job_cards)
        self._job_selections[idx] = []

        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.StyledPanel)
        card._card_idx = idx
        self._apply_card_style(card, selected=False)

        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(6, 3, 6, 3)
        card_layout.setSpacing(2)

        # ── Row 1: Subject | Source | Mode | ✕ ─────────────────────────
        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(4)

        subjects = self._get_available_subjects()
        card.subject_combo = QtWidgets.QComboBox()
        card.subject_combo.addItems(subjects)
        if subject and subject in subjects:
            card.subject_combo.setCurrentText(subject)
        elif subjects:
            card.subject_combo.setCurrentIndex(0)
        card.subject_combo.currentTextChanged.connect(self._on_row_subject_changed)
        row1.addWidget(card.subject_combo, 2)

        card.source_combo = QtWidgets.QComboBox()
        card.source_combo.addItems(["Montage", "Flex-Search", "Freehand"])
        if source in ["Montage", "Flex-Search", "Freehand"]:
            card.source_combo.setCurrentText(source)
        card.source_combo.currentTextChanged.connect(self._on_row_source_changed)
        row1.addWidget(card.source_combo, 1)

        card.mode_combo = QtWidgets.QComboBox()
        card.mode_combo.addItems(["U", "M"])
        if mode in ["U", "M"]:
            card.mode_combo.setCurrentText(mode)
        card.mode_combo.setFixedWidth(44)
        card.mode_combo.currentTextChanged.connect(self._on_row_mode_changed)
        row1.addWidget(card.mode_combo)

        card.del_btn = QtWidgets.QPushButton("×")
        card.del_btn.setFixedWidth(24)
        card.del_btn.setFixedHeight(22)
        card.del_btn.clicked.connect(self._remove_job_row_by_sender)
        row1.addWidget(card.del_btn)

        card_layout.addLayout(row1)

        # ── Row 2: mA | current box | Net | count ──────────────────────
        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(4)

        row2.addWidget(QtWidgets.QLabel("mA:"))

        ph = "1.0,1.0,1.0,1.0" if mode == "M" else "1.0,1.0"
        card.current_edit = QtWidgets.QLineEdit(currents)
        card.current_edit.setPlaceholderText(ph)
        card.current_edit.setMinimumWidth(80)
        row2.addWidget(card.current_edit, 3)

        row2.addWidget(QtWidgets.QLabel("Net:"))

        card.eeg_net_combo = QtWidgets.QComboBox()
        for i in range(self.eeg_net_combo.count()):
            card.eeg_net_combo.addItem(self.eeg_net_combo.itemText(i))
        if card.eeg_net_combo.count() == 0:
            card.eeg_net_combo.addItem("GSN-HydroCel-185.csv")
        if eeg_net and card.eeg_net_combo.findText(eeg_net) >= 0:
            card.eeg_net_combo.setCurrentText(eeg_net)
        card.eeg_net_combo.currentTextChanged.connect(self._on_row_eeg_net_changed)
        row2.addWidget(card.eeg_net_combo, 2)

        card.count_label = QtWidgets.QLabel("0 selected")
        row2.addWidget(card.count_label)

        card_layout.addLayout(row2)

        # Make the card clickable to select it
        card.mousePressEvent = lambda event, i=idx: self._select_card(i)

        # Insert before the trailing stretch
        insert_pos = self.jobs_layout.count() - 1
        self.jobs_layout.insertWidget(insert_pos, card)
        self._job_cards.append(card)

        # Auto-select the new card
        self._select_card(idx)

    def _apply_card_style(self, card, selected):
        """Apply normal or selected visual style to a job card."""
        if selected:
            card.setStyleSheet("QFrame { border: 2px solid #444; }")
        else:
            card.setStyleSheet("QFrame { border: 1px solid #ccc; }")

    def _select_card(self, idx):
        """Select the card at idx; deselect all others; refresh selection list."""
        self._selected_card_idx = idx
        for i, card in enumerate(self._job_cards):
            self._apply_card_style(card, selected=(i == idx))
        self._refresh_selection_list()

    def _remove_job_row(self, row):
        """Remove the job card at the given index."""
        if row < 0 or row >= len(self._job_cards):
            return
        card = self._job_cards.pop(row)
        self.jobs_layout.removeWidget(card)
        card.setParent(None)
        card.deleteLater()

        # Re-key _job_selections
        new_selections = {}
        for k, v in self._job_selections.items():
            if k < row:
                new_selections[k] = v
            elif k > row:
                new_selections[k - 1] = v
        self._job_selections = new_selections

        # Update stored card indices
        for i, c in enumerate(self._job_cards):
            c._card_idx = i
            c.mousePressEvent = lambda event, idx=i: self._select_card(idx)

        # Adjust selected index
        if self._selected_card_idx == row:
            new_idx = min(row, len(self._job_cards) - 1)
            self._selected_card_idx = new_idx
            self._refresh_selection_list()
            if new_idx >= 0:
                self._apply_card_style(self._job_cards[new_idx], selected=True)
        elif self._selected_card_idx > row:
            self._selected_card_idx -= 1

    def _remove_selected_job_row(self):
        """Remove the currently selected job card."""
        if self._selected_card_idx >= 0:
            self._remove_job_row(self._selected_card_idx)

    def _remove_job_row_by_sender(self):
        """Remove the card whose delete button was clicked."""
        btn = self.sender()
        for i, card in enumerate(self._job_cards):
            if card.del_btn is btn:
                self._remove_job_row(i)
                return

    def _on_row_subject_changed(self, text):
        """Reset selections when subject changes for a card."""
        combo = self.sender()
        for i, card in enumerate(self._job_cards):
            if card.subject_combo is combo:
                self._job_selections[i] = []
                self._update_count_cell(i)
                if i == self._selected_card_idx:
                    self._refresh_selection_list()
                break

    def _on_row_source_changed(self, text):
        """Reset selections when source type changes for a card."""
        combo = self.sender()
        for i, card in enumerate(self._job_cards):
            if card.source_combo is combo:
                self._job_selections[i] = []
                self._update_count_cell(i)
                if i == self._selected_card_idx:
                    self._refresh_selection_list()
                break

    def _on_row_eeg_net_changed(self, text):
        """Reset selections when EEG net changes for a card (montage list changes)."""
        combo = self.sender()
        for i, card in enumerate(self._job_cards):
            if card.eeg_net_combo is combo:
                self._job_selections[i] = []
                self._update_count_cell(i)
                if i == self._selected_card_idx:
                    self._refresh_selection_list()
                break

    def _on_row_mode_changed(self, text):
        """Update current input placeholder when U/M mode changes."""
        combo = self.sender()
        for card in self._job_cards:
            if card.mode_combo is combo:
                ph = "1.0,1.0,1.0,1.0" if text == "M" else "1.0,1.0"
                card.current_edit.setPlaceholderText(ph)
                break

    def _update_count_cell(self, row):
        """Update the count label on the job card for a given index."""
        if row < 0 or row >= len(self._job_cards):
            return
        selections = self._job_selections.get(row, [])
        n = len(selections)
        self._job_cards[row].count_label.setText(f"{n} selected")

    # ── Selection panel ─────────────────────────────────────────────────────

    def _refresh_selection_list(self):
        """Repopulate the selection list for the currently selected job card."""
        idx = self._selected_card_idx
        if idx < 0 or idx >= len(self._job_cards):
            self.selection_list.blockSignals(True)
            self.selection_list.clear()
            self.selection_list.blockSignals(False)
            self.selection_label.setText("Select a job card above")
            self._update_selection_panel_buttons(source=None)
            return

        card = self._job_cards[idx]
        subject = card.subject_combo.currentText()
        source = card.source_combo.currentText()   # "Montage" | "Flex-Search" | "Freehand"
        self.selection_label.setText(f"Selecting for: {subject} / {source}")
        self._update_selection_panel_buttons(source=source)

        # Build item list
        items = []
        if source == "Montage":
            eeg_net = card.eeg_net_combo.currentText() or "GSN-HydroCel-185.csv"
            sim_mode = card.mode_combo.currentText()   # "U" or "M"
            items = self._get_montage_names_for_params(eeg_net, sim_mode)
        elif source == "Flex-Search":
            items = self._get_flex_outputs_for_subject(subject)
        elif source == "Freehand":
            items = self._get_freehand_configs_for_subject(subject)

        saved = set(self._job_selections.get(idx, []))

        self.selection_list.blockSignals(True)
        self.selection_list.clear()
        for item_text in items:
            list_item = QtWidgets.QListWidgetItem(item_text)
            self.selection_list.addItem(list_item)
            if item_text in saved:
                list_item.setSelected(True)
        self.selection_list.blockSignals(False)

    def _save_selection_for_current_row(self):
        """Save the current selection list state to _job_selections."""
        idx = self._selected_card_idx
        if idx < 0 or idx >= len(self._job_cards):
            return
        selected_texts = [
            item.text() for item in self.selection_list.selectedItems()
        ]
        self._job_selections[idx] = selected_texts
        self._update_count_cell(idx)

    def _clear_selection(self):
        """Clear the selection in the selection list."""
        self.selection_list.clearSelection()
        self._save_selection_for_current_row()

    def _update_selection_panel_buttons(self, source):
        """Show/hide montage-specific buttons based on current source."""
        is_montage = (source == "Montage")
        self.add_montage_sel_btn.setVisible(is_montage)
        self.remove_montage_sel_btn.setVisible(is_montage)

    # ── Data helpers ────────────────────────────────────────────────────────

    def _get_montage_names_for_params(self, eeg_net, sim_mode):
        """Return list of montage names for given EEG net and sim mode (U/M)."""
        try:
            project_dir = self.pm.project_dir
            if not project_dir:
                return []
            montage_file = self.ensure_montage_file_exists(project_dir)
            with open(montage_file, "r") as f:
                montage_data = json.load(f)
            net_type = "uni_polar_montages" if sim_mode == "U" else "multi_polar_montages"
            nets = montage_data.get("nets", {})
            if eeg_net not in nets:
                return []
            return list(nets[eeg_net].get(net_type, {}).keys())
        except Exception as e:
            print(f"Error getting montage names: {e}")
            return []

    def _get_flex_outputs_for_subject(self, subject_id):
        """Return list of flex-search item strings for a subject (mapped + optimized).

        Always offers [mapped] for any run that has electrode_positions.json
        (actual EEG-cap mapping is done at simulation time). Also offers
        [optimized] when optimized_positions are stored in that file.
        """
        items = []
        try:
            # Use PathManager helper which already filters for electrode_positions.json
            run_names = self.pm.list_flex_search_runs(subject_id=subject_id)
            for search_name in run_names:
                # [mapped] is always available – mapping to EEG cap happens at sim time
                items.append(f"{search_name} [mapped]")
                # [optimized] only if the optimized_positions key is present
                positions_file = self.pm.path_optional(
                    "flex_electrode_positions", subject_id=subject_id, search_name=search_name
                )
                if positions_file and os.path.isfile(positions_file):
                    try:
                        with open(positions_file, "r") as f:
                            pos_data = json.load(f)
                        if pos_data.get("optimized_positions"):
                            items.append(f"{search_name} [optimized]")
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error getting flex outputs for {subject_id}: {e}")
        return items

    def _get_freehand_configs_for_subject(self, subject_id):
        """Return list of freehand config names for a subject."""
        items = []
        try:
            m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
            if not m2m_dir or not os.path.isdir(m2m_dir):
                return items
            stim_configs_dir = os.path.join(m2m_dir, "stim_configs")
            if not os.path.exists(stim_configs_dir):
                return items
            for config_file in sorted(os.listdir(stim_configs_dir)):
                if config_file.endswith(".json"):
                    config_path = os.path.join(stim_configs_dir, config_file)
                    try:
                        with open(config_path, "r") as f:
                            config_data = json.load(f)
                        name = config_data.get("name", config_file.replace(".json", ""))
                        items.append(name)
                    except Exception:
                        items.append(config_file.replace(".json", ""))
        except Exception as e:
            print(f"Error getting freehand configs for {subject_id}: {e}")
        return items

    # ── MontageConfig builders ──────────────────────────────────────────────

    def _build_montage_configs_for_row(self, subject, source, sim_mode, selected_items, eeg_net):
        """Build list of MontageConfig objects for a single job row."""
        configs = []
        if source == "montage":
            configs = self._build_montage_configs_from_names(selected_items, eeg_net, sim_mode)
        elif source == "flex-search":
            configs = self._build_montage_configs_from_flex(subject, selected_items, eeg_net)
        elif source == "freehand":
            configs = self._build_montage_configs_from_freehand(subject, selected_items)
        return configs

    def _build_montage_configs_from_names(self, montage_names, eeg_net, sim_mode):
        """Build MontageConfig list from montage names."""
        configs = []
        try:
            project_dir = self.pm.project_dir
            montage_file = self.ensure_montage_file_exists(project_dir)
            with open(montage_file, "r") as f:
                montage_data = json.load(f)
            net_type = "uni_polar_montages" if sim_mode == "U" else "multi_polar_montages"
            for montage_name in montage_names:
                electrode_pairs = None
                if (
                    "nets" in montage_data
                    and eeg_net in montage_data["nets"]
                    and net_type in montage_data["nets"][eeg_net]
                    and montage_name in montage_data["nets"][eeg_net][net_type]
                ):
                    electrode_pairs = montage_data["nets"][eeg_net][net_type][montage_name]
                if electrode_pairs:
                    pairs_as_tuples = [(pair[0], pair[1]) for pair in electrode_pairs]
                    configs.append(MontageConfig(
                        name=montage_name,
                        electrode_pairs=pairs_as_tuples,
                        is_xyz=False,
                        eeg_net=eeg_net,
                    ))
        except Exception as e:
            self.update_output(f"Error building montage configs: {e}", "error")
        return configs

    def _build_montage_configs_from_flex(self, subject_id, selected_items, eeg_net):
        """Build MontageConfig list from flex-search selection items."""
        configs = []
        for item_text in selected_items:
            try:
                # Parse "search_name [mapped]" or "search_name [optimized]"
                if item_text.endswith(" [mapped]"):
                    search_name = item_text[:-len(" [mapped]")]
                    electrode_type = "mapped"
                elif item_text.endswith(" [optimized]"):
                    search_name = item_text[:-len(" [optimized]")]
                    electrode_type = "optimized"
                else:
                    search_name = item_text
                    electrode_type = "mapped"

                flex_search_dir = self.pm.path_optional(
                    "flex_search_run", subject_id=subject_id, search_name=search_name
                )
                if not flex_search_dir:
                    self.update_output(
                        f"Flex-search folder not found for {subject_id} | {search_name}", "error"
                    )
                    continue

                positions_file = os.path.join(flex_search_dir, "electrode_positions.json")

                if electrode_type == "mapped":
                    # Need to map to EEG cap
                    eeg_positions_dir = self.pm.path_optional("eeg_positions", subject_id=subject_id)
                    eeg_net_path = os.path.join(eeg_positions_dir or "", eeg_net)
                    if not eeg_positions_dir or not os.path.isfile(eeg_net_path):
                        self.update_output(f"EEG net file not found: {eeg_net_path}", "error")
                        continue

                    # Run electrode mapping
                    mapping_file = os.path.join(
                        flex_search_dir,
                        f'electrode_mapping_{eeg_net.replace(".csv", "")}.json',
                    )
                    self.update_output(
                        f"Mapping electrodes for {subject_id} | {search_name} to {eeg_net}...", "info"
                    )
                    map_electrodes_path = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)), "tools", "map_electrodes.py"
                    )
                    try:
                        subprocess.run(
                            ["simnibs_python", map_electrodes_path, "-i", positions_file,
                             "-n", eeg_net_path, "-o", mapping_file],
                            capture_output=True, text=True, check=True,
                        )
                        self.update_output(f"Electrode mapping completed for {search_name}", "info")
                    except subprocess.CalledProcessError as e:
                        self.update_output(f"Error mapping electrodes: {e.stderr}", "error")
                        continue

                    if not os.path.exists(mapping_file):
                        self.update_output(f"Mapping file was not created: {mapping_file}", "error")
                        continue

                    with open(mapping_file, "r") as f:
                        mapping_data = json.load(f)
                    mapped_labels = mapping_data.get("mapped_labels", [])
                    if len(mapped_labels) < 4:
                        self.update_output(
                            f"Not enough electrodes for TI in {search_name} (need >=4)", "error"
                        )
                        continue

                    montage_name = self._parse_flex_search_name(search_name, "mapped")
                    if montage_name.startswith("flex_"):
                        electrodes = mapped_labels[:4]
                        configs.append(MontageConfig(
                            name=montage_name,
                            electrode_pairs=[(electrodes[0], electrodes[1]),
                                            (electrodes[2], electrodes[3])],
                            is_xyz=False,
                            eeg_net=eeg_net,
                        ))

                else:  # optimized
                    with open(positions_file, "r") as f:
                        pos_data = json.load(f)
                    optimized_positions = pos_data.get("optimized_positions", [])
                    if len(optimized_positions) < 4:
                        self.update_output(
                            f"Not enough optimized electrodes in {search_name}", "error"
                        )
                        continue
                    montage_name = self._parse_flex_search_name(search_name, "optimized")
                    if montage_name.startswith("flex_"):
                        positions = optimized_positions[:4]
                        configs.append(MontageConfig(
                            name=montage_name,
                            electrode_pairs=[(positions[0], positions[1]),
                                            (positions[2], positions[3])],
                            is_xyz=True,
                            eeg_net=None,
                        ))
            except Exception as e:
                self.update_output(f"Error processing flex item '{item_text}': {e}", "error")
        return configs

    def _build_montage_configs_from_freehand(self, subject_id, selected_names):
        """Build MontageConfig list from freehand config names."""
        configs = []
        try:
            m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
            if not m2m_dir:
                return configs
            stim_configs_dir = os.path.join(m2m_dir, "stim_configs")
            if not os.path.exists(stim_configs_dir):
                return configs

            for name in selected_names:
                # Find the matching config file
                for config_file in os.listdir(stim_configs_dir):
                    if not config_file.endswith(".json"):
                        continue
                    config_path = os.path.join(stim_configs_dir, config_file)
                    try:
                        with open(config_path, "r") as f:
                            config_data = json.load(f)
                        config_name = config_data.get("name", config_file.replace(".json", ""))
                        if config_name != name:
                            continue
                        electrode_positions = config_data.get("electrode_positions", {})
                        ordered_keys = ["E1+", "E1-", "E2+", "E2-"]
                        coords = []
                        for k in ordered_keys:
                            if k in electrode_positions:
                                coords.append(electrode_positions[k])
                        if len(coords) < 4:
                            for k in sorted(electrode_positions.keys()):
                                if k not in ordered_keys and len(coords) < 4:
                                    coords.append(electrode_positions.get(k))
                        if len(coords) >= 4:
                            configs.append(MontageConfig(
                                name=name,
                                electrode_pairs=[(coords[0], coords[1]), (coords[2], coords[3])],
                                is_xyz=True,
                                eeg_net="freehand",
                            ))
                        break
                    except Exception as e:
                        print(f"Error loading freehand config {config_file}: {e}")
        except Exception as e:
            self.update_output(f"Error building freehand configs: {e}", "error")
        return configs

    # ── Legacy compat stubs ─────────────────────────────────────────────────

    def ensure_montage_file_exists(self, project_dir):
        """Ensure the montage file exists with proper structure."""
        from tit.sim import utils as sim_utils
        return sim_utils.ensure_montage_file(project_dir)

    def update_montage_list(self, checked=None):
        """Refresh the selection list (called after adding montage)."""
        self._refresh_selection_list()

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

    def _format_electrode_pairs(self, pairs):
        """Format electrode pairs for display in a clean way."""
        if not pairs:
            return "No electrode pairs"
        formatted_pairs = []
        for pair in pairs:
            if isinstance(pair, list) and len(pair) >= 2:
                formatted_pair = (
                    f'<span style="color: #55aaff;">{pair[0]}</span>'
                    f'<span style="color: #aaaaaa;">-></span>'
                    f'<span style="color: #ff5555;">{pair[1]}</span>'
                )
                formatted_pairs.append(formatted_pair)
        return ", ".join(formatted_pairs)

    def run_simulation(self):
        """Run the simulation with the per-job table configuration."""
        try:
            # ── Collect jobs from table ────────────────────────────────────
            raw_jobs = []  # (subject_id, source, sim_mode, current_str, eeg_net, selected_items)
            for i, card in enumerate(self._job_cards):
                subject = card.subject_combo.currentText().strip()
                source = card.source_combo.currentText().lower()
                sim_mode = card.mode_combo.currentText()   # "U" or "M"
                row_eeg_net = card.eeg_net_combo.currentText() or "GSN-HydroCel-185.csv"
                selected = self._job_selections.get(i, [])
                if not selected:
                    continue
                raw = card.current_edit.text().strip() or (
                    "1.0,1.0,1.0,1.0" if sim_mode == "M" else "1.0,1.0"
                )
                current_str = raw
                raw_jobs.append((subject, source, sim_mode, current_str, row_eeg_net, selected))

            if not raw_jobs:
                QtWidgets.QMessageBox.warning(
                    self, "Warning",
                    "No jobs configured. Add rows with subjects and selected montages/configs."
                )
                return

            # ── Read global params ─────────────────────────────────────────
            project_dir = self.pm.project_dir
            conductivity = self.sim_type_combo.currentData()
            electrode_shape = "rect" if self.electrode_shape_rect.isChecked() else "ellipse"
            dimensions = self.dimensions_input.text() or "8,8"
            thickness = self.thickness_input.text() or "4"

            # Validate numeric inputs
            try:
                dim_parts = dimensions.split(",")
                if len(dim_parts) != 2 or not all(dim_parts):
                    raise ValueError("Invalid dimensions format")
                float(dim_parts[0])
                float(dim_parts[1])
                float(thickness)
            except ValueError:
                QtWidgets.QMessageBox.warning(
                    self, "Warning",
                    "Please enter valid numeric values for dimensions and thickness."
                )
                return

            # ── Build MontageConfig objects for each job row ───────────────
            jobs = []   # (subject_id, MontageConfig, current_str)
            for subject, source, sim_mode, current_str, row_eeg_net, selected in raw_jobs:
                montage_configs = self._build_montage_configs_for_row(
                    subject, source, sim_mode, selected, row_eeg_net
                )
                for mc in montage_configs:
                    jobs.append((subject, mc, current_str))

            if not jobs:
                QtWidgets.QMessageBox.warning(
                    self, "Warning",
                    "No valid simulations could be prepared. Check your selections."
                )
                return

            # ── Confirmation dialog ────────────────────────────────────────
            job_lines = []
            for subject, mc, current_str in jobs:
                job_lines.append(f"  * {subject} | {mc.name} | {mc.eeg_net} | {current_str} mA")
            details = (
                f"This will run {len(jobs)} simulation(s):\n\n"
                + "\n".join(job_lines[:15])
                + (f"\n  ... and {len(jobs)-15} more" if len(jobs) > 15 else "")
                + f"\n\nGlobal Parameters:\n"
                f"* Anisotropy: {conductivity}\n"
                f"* Electrode: {electrode_shape} ({dimensions} mm, {thickness} mm thick)"
            )
            if not ConfirmationDialog.confirm(
                self,
                title="Confirm Simulation",
                message="Are you sure you want to start the simulation?",
                details=details,
            ):
                return

            # ── Check for existing output directories ──────────────────────
            existing_dirs = []
            for subject_id, mc, _ in jobs:
                simulations_dir = self.pm.path_optional("simulations", subject_id=subject_id)
                montage_dir = os.path.join(simulations_dir or "", mc.name)
                if simulations_dir and os.path.exists(montage_dir):
                    existing_dirs.append(f"{subject_id}/{mc.name}")

            if existing_dirs:
                existing_list = "\n".join([f"  * {d}" for d in existing_dirs[:10]])
                if len(existing_dirs) > 10:
                    existing_list += f"\n  ... and {len(existing_dirs) - 10} more"
                if not ConfirmationDialog.confirm(
                    self,
                    title="Overwrite Existing Simulations?",
                    message="The following simulation directories already exist and will be overwritten:",
                    details=f"{existing_list}\n\nDo you want to continue?",
                ):
                    return

                self.update_output("Removing existing simulation directories...")
                for subject_id, mc, _ in jobs:
                    simulations_dir = self.pm.path_optional("simulations", subject_id=subject_id)
                    montage_dir = os.path.join(simulations_dir or "", mc.name)
                    if simulations_dir and os.path.exists(montage_dir):
                        try:
                            shutil.rmtree(montage_dir)
                            self.update_output(f"  Removed: {subject_id}/{mc.name}")
                        except Exception as e:
                            self.update_output(
                                f"  Warning: Could not remove {subject_id}/{mc.name}: {e}",
                                "warning"
                            )

            # ── Store run context ──────────────────────────────────────────
            unique_subjects = list(dict.fromkeys(s for s, _, _ in jobs))
            unique_montages = list(dict.fromkeys(mc.name for _, mc, _ in jobs))
            self._current_run_subjects = unique_subjects
            self._current_run_montages = unique_montages
            self._current_run_is_montage = True
            self._current_run_mode = "mixed"
            self._run_start_time = time.time()
            self._project_dir_path_current = project_dir

            # Store for report generation
            self._last_jobs = jobs[:]
            self._last_conductivity = conductivity
            self._last_electrode_shape = electrode_shape
            self._last_dimensions = dimensions
            self._last_thickness = thickness

            # ── Concurrency ────────────────────────────────────────────────
            total_simulations = len(jobs)
            if total_simulations >= 2:
                if self.parallel_checkbox.isChecked():
                    self._max_concurrent_jobs = max(1, int(self.parallel_workers_spin.value()))
                else:
                    self._max_concurrent_jobs = 2
            else:
                self._max_concurrent_jobs = 1

            self._job_queue = jobs[:]
            self._active_processes = set()
            self._process_to_job = {}

            # ── Console summary ────────────────────────────────────────────
            self.update_output("--- SIMULATION CONFIGURATION ---")
            self.update_output(f"Total jobs: {total_simulations}")
            self.update_output(f"Subjects: {', '.join(unique_subjects)}")
            self.update_output(f"Anisotropy: {conductivity}")
            self.update_output(f"Electrode: {electrode_shape} ({dimensions} mm, {thickness} mm thick)")
            self.update_output("--- STARTING SIMULATION (Subprocess) ---")

            # ── Report generator ───────────────────────────────────────────
            self.simulation_session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.report_generator = SimulationReportGenerator(
                project_dir=project_dir,
                simulation_session_id=self.simulation_session_id,
            )
            if self.report_generator:
                first_current = jobs[0][2] if jobs else "1.0,1.0"
                first_eeg_net = jobs[0][1].eeg_net if jobs else "GSN-HydroCel-185.csv"
                current_parts = first_current.split(",")
                self.report_generator.add_simulation_parameters(
                    conductivity_type=conductivity,
                    simulation_mode="U",
                    eeg_net=first_eeg_net,
                    intensity_ch1=float(current_parts[0]) if current_parts else 1.0,
                    intensity_ch2=float(current_parts[1]) if len(current_parts) > 1 else 1.0,
                    intensity_ch3=None,
                    intensity_ch4=None,
                    quiet_mode=False,
                    conductivities=self._get_conductivities_for_report(),
                )
                dim_p = dimensions.split(",")
                self.report_generator.add_electrode_parameters(
                    shape=electrode_shape,
                    dimensions=[float(dim_p[0]), float(dim_p[1])],
                    thickness=float(thickness),
                )
                for subject_id in unique_subjects:
                    m2m_path = self.pm.path_optional("m2m", subject_id=subject_id)
                    self.report_generator.add_subject(subject_id, m2m_path, "processing")

            # ── Enable stop button, disable controls ───────────────────────
            self.disable_controls()
            self.action_buttons.set_running(True)
            if hasattr(self, "parent") and self.parent:
                keep_enabled_widgets = []
                if hasattr(self, "console_widget"):
                    keep_enabled_widgets.append(self.console_widget.debug_checkbox)
                if hasattr(self, "console_widget") and hasattr(self.console_widget, "clear_btn"):
                    keep_enabled_widgets.append(self.console_widget.clear_btn)
                self.parent.set_tab_busy(
                    self, True,
                    message="A simulation is running...",
                    stop_btn=self.stop_btn,
                    keep_enabled=keep_enabled_widgets,
                )

            self.simulation_running = True
            self._had_errors_during_run = False
            self._simulation_finished_called = False

            # Store global sim params (used in _start_single_simulation_job)
            dim_parts2 = dimensions.split(",")
            electrode_dims = [float(dim_parts2[0]), float(dim_parts2[1])]
            self._sim_params = {
                "conductivity": conductivity,
                "current": jobs[0][2] if jobs else "1.0,1.0",  # fallback; per-job overrides used
                "electrode_shape": electrode_shape,
                "electrode_dims": electrode_dims,
                "thickness": float(thickness),
                "project_dir": project_dir,
                "parallel_enabled": self.parallel_checkbox.isChecked(),
                "parallel_workers": self.parallel_workers_spin.value(),
            }

            self._start_next_simulation_jobs()

        except Exception as e:
            self.update_output(f"Error starting simulation: {str(e)}", "error")
            import traceback
            self.update_output(traceback.format_exc(), "error")
            self.simulation_finished()

    def _start_next_simulation_jobs(self):
        """Start as many simulation jobs as allowed by the concurrency limit."""
        if not getattr(self, "simulation_running", False):
            return

        # Fill up to concurrency
        while (
            self._job_queue and len(self._active_processes) < self._max_concurrent_jobs
        ):
            subject_id, montage_cfg, current_str = self._job_queue.pop(0)
            self._start_single_simulation_job(subject_id, montage_cfg, current_str)

        # If nothing is running and queue is empty, we're done
        if not self._job_queue and not self._active_processes:
            self.simulation_finished()

    def _start_single_simulation_job(self, subject_id: str, montage_cfg: MontageConfig, current_str: str = None):
        """Start a single simulation job (one subject × one montage/config) in a subprocess."""
        try:
            run_mode = getattr(self, "_current_run_mode", "montage")
            mode_label = {
                "montage": "montage mode",
                "freehand": "freehand mode",
                "flex": "flex mode",
                "mixed": "simulation",
            }.get(run_mode, str(run_mode))
            self.update_output(
                f"Beginning simulation for subject: {subject_id} | Simulation: {montage_cfg.name} ({mode_label})",
                "info",
            )

            # Build SimulationConfig for this job
            config = SimulationConfig(
                subject_id=subject_id,
                project_dir=self._sim_params["project_dir"],
                conductivity_type=ConductivityType(self._sim_params["conductivity"]),
                intensities=IntensityConfig.from_string(
                    current_str if current_str else self._sim_params["current"]
                ),
                electrode=ElectrodeConfig(
                    shape=self._sim_params["electrode_shape"],
                    dimensions=self._sim_params["electrode_dims"],
                    thickness=self._sim_params["thickness"],
                ),
                eeg_net=montage_cfg.eeg_net,
                # IMPORTANT: now that we parallelize at the job level, we disable in-process montage parallelism.
                parallel=ParallelConfig(enabled=False, max_workers=0),
            )

            payload = {
                "debug": bool(getattr(self, "debug_mode", False)),
                "config": {
                    "subject_id": config.subject_id,
                    "project_dir": config.project_dir,
                    "conductivity_type": config.conductivity_type.value,
                    "intensities": {
                        "pair1": config.intensities.pair1,
                        "pair2": config.intensities.pair2,
                        "pair3": config.intensities.pair3,
                        "pair4": config.intensities.pair4,
                    },
                    "electrode": {
                        "shape": config.electrode.shape,
                        "dimensions": list(config.electrode.dimensions),
                        "thickness": config.electrode.thickness,
                        "sponge_thickness": config.electrode.sponge_thickness,
                    },
                    "eeg_net": config.eeg_net,
                    "parallel": {
                        "enabled": False,
                        "max_workers": 0,
                    },
                },
                "montages": [
                    {
                        "name": montage_cfg.name,
                        "electrode_pairs": [
                            list(p) for p in montage_cfg.electrode_pairs
                        ],
                        "is_xyz": bool(getattr(montage_cfg, "is_xyz", False)),
                        "eeg_net": montage_cfg.eeg_net,
                    }
                ],
            }

            proc = SubprocessSimulationProcess(
                payload=payload,
                parent_tab=self,
            )
            self._active_processes.add(proc)
            self._process_to_job[proc] = (subject_id, montage_cfg.name)

            # Announce job start (debug only to avoid spam)
            if getattr(self, "debug_mode", False):
                self.update_output(
                    f"[DEBUG] Starting job: sub-{subject_id} × {montage_cfg.name}",
                    "command",
                )

            proc.output_signal.connect(self._handle_thread_output)
            proc.error_signal.connect(
                lambda msg: self._handle_thread_output(msg, "error")
            )
            proc.finished.connect(lambda p=proc: self._on_simulation_job_finished(p))
            proc.start()

        except Exception as e:
            self.update_output(
                f"Error starting simulation job for {subject_id} - {montage_cfg.name}: {e}",
                "error",
            )
            self._had_errors_during_run = True

    def _on_simulation_job_finished(self, proc):
        """Handle completion of a single simulation job subprocess."""
        try:
            if proc in self._active_processes:
                self._active_processes.remove(proc)
            job = self._process_to_job.pop(proc, None)

            # If the run was aborted (user stop or error abort), do not continue.
            if not getattr(self, "simulation_running", False) or getattr(
                self, "_aborting_due_to_error", False
            ):
                return

            # Record whether job produced failures
            try:
                results = proc.get_results() or []
                for r in results:
                    if r.get("status") == "failed":
                        self._had_errors_during_run = True
                        break
            except Exception:
                self._had_errors_during_run = True

            # Continue scheduling
            self._start_next_simulation_jobs()

        except Exception:
            # If job completion handler fails, mark error and try to proceed.
            self._had_errors_during_run = True
            self._start_next_simulation_jobs()

    # NOTE: Old per-subject completion handler removed in favor of job-based scheduling.

    def simulation_finished(self):
        """Handle simulation completion."""
        # Prevent double calling
        if (
            hasattr(self, "_simulation_finished_called")
            and self._simulation_finished_called
        ):
            return

        self._simulation_finished_called = True

        if self.debug_mode:
            if self._had_errors_during_run:
                self.output_console.append(
                    '<div style="margin: 10px 0;"><span style="color: #ff5555; font-size: 16px; font-weight: bold;">--- SIMULATION PROCESS COMPLETED WITH ERRORS ---</span></div>'
                )
                if hasattr(self, "_first_error_line") and getattr(
                    self, "_first_error_line", None
                ):
                    safe_err = strip_ansi_codes(self._first_error_line)
                    self.update_output(f"First error detected: {safe_err}", "error")
            else:
                self.output_console.append(
                    '<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">--- SIMULATION PROCESS COMPLETED ---</span></div>'
                )
            self.output_console.append(
                '<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>'
            )

        # Only auto-generate simulation report if there were no errors; else cleanup partial outputs and inform user
        if not self._had_errors_during_run:
            self.auto_generate_simulation_report()
        else:
            self.update_output(
                "[INFO] Skipping automatic report generation due to errors during simulation.",
                "warning",
            )
            try:
                self._cleanup_partial_outputs()
            except Exception as cleanup_exc:
                self.update_output(
                    f"[WARNING] Cleanup encountered an issue: {cleanup_exc}", "warning"
                )

        # Clean up temporary completion files
        self.cleanup_temporary_files()

        # Clean up any remaining temporary flex montage files (CLI should have cleaned most)
        if hasattr(self, "temp_flex_files"):
            remaining_files = 0
            for temp_file in self.temp_flex_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        remaining_files += 1
                        self.update_output(f"[CLEANUP] Removed temp file: {temp_file}")
                except Exception as e:
                    self.update_output(
                        f"[WARNING] Could not clean up flex file {temp_file}: {str(e)}",
                        "warning",
                    )
            if remaining_files > 0:
                self.update_output(
                    f"[CLEANUP] Removed {remaining_files} remaining temp files"
                )
            delattr(self, "temp_flex_files")

        self.simulation_running = False
        self._aborting_due_to_error = False

        # Reset button states using centralized method
        self.run_btn.setText("Run Simulation")
        self.action_buttons.set_running(False)

        # Clear parent tab's busy state (with stop_btn parameter for proper state management)
        if hasattr(self, "parent") and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

        # Re-enable all controls
        self.enable_controls()

    def auto_generate_simulation_report(self):
        """Auto-generate individual simulation reports for each completed job."""
        try:
            project_dir = self.pm.project_dir
            conductivity = getattr(self, "_last_conductivity", self.sim_type_combo.currentData())
            electrode_shape = getattr(self, "_last_electrode_shape", "ellipse")
            dimensions = getattr(self, "_last_dimensions", "8,8")
            thickness = getattr(self, "_last_thickness", "4")

            # Build subject->[(montage_name, current_str, eeg_net)] mapping from completed jobs
            last_jobs = getattr(self, "_last_jobs", [])
            subject_montage_map = {}  # subject_id -> [(montage_name, current_str, eeg_net)]
            for subject_id, mc, current_str in last_jobs:
                if subject_id not in subject_montage_map:
                    subject_montage_map[subject_id] = []
                subject_montage_map[subject_id].append((mc.name, current_str, mc.eeg_net))

            if not subject_montage_map:
                self.update_output("No completed jobs to report on.", "warning")
                return

            total_reports = 0
            successful_reports = 0

            for subject_id, montage_list in subject_montage_map.items():
                montages_to_process = [name for name, _, _ in montage_list]
                currents_map = {name: cur for name, cur, _ in montage_list}
                eeg_net_map = {name: net for name, _, net in montage_list}

                # Generate individual report for each montage for this subject
                for montage_name in montages_to_process:
                    total_reports += 1

                    try:
                        # Create unique session ID for each report
                        individual_session_id = (
                            f"{self.simulation_session_id}_{subject_id}_{montage_name}"
                        )
                        report_generator = SimulationReportGenerator(
                            project_dir=project_dir,
                            simulation_session_id=individual_session_id,
                            subject_id=subject_id,
                        )

                        # Add simulation parameters
                        cur = currents_map.get(montage_name, "1.0,1.0")
                        cur_parts = cur.split(",")
                        intensity_ch1 = float(cur_parts[0]) if cur_parts else 1.0
                        intensity_ch2 = float(cur_parts[1]) if len(cur_parts) > 1 else 1.0
                        job_eeg_net = eeg_net_map.get(montage_name, "GSN-HydroCel-185.csv")
                        report_generator.add_simulation_parameters(
                            conductivity_type=conductivity,
                            simulation_mode="U",
                            eeg_net=job_eeg_net,
                            intensity_ch1=intensity_ch1,
                            intensity_ch2=intensity_ch2,
                            quiet_mode=True,
                            conductivities=self._get_conductivities_for_report(),
                        )

                        # Add electrode parameters
                        dim_parts = dimensions.split(",")
                        report_generator.add_electrode_parameters(
                            shape=electrode_shape,
                            dimensions=[float(dim_parts[0]), float(dim_parts[1])],
                            thickness=float(thickness),
                        )

                        # Add this specific subject
                        bids_subject_id = f"sub-{subject_id}"
                        m2m_path = self.pm.path_optional("m2m", subject_id=subject_id)
                        report_generator.add_subject(subject_id, m2m_path, "completed")

                        # Add this specific montage
                        report_generator.add_montage(
                            montage_name=montage_name,
                            electrode_pairs=[["E1", "E2"]],  # Default pairs
                            montage_type="unipolar",
                        )

                        # Get expected output files for this specific combination
                        simulations_dir = self.pm.path_optional(
                            "simulation",
                            subject_id=subject_id,
                            simulation_name=montage_name,
                        )
                        ti_dir = (
                            os.path.join(simulations_dir, "TI")
                            if simulations_dir
                            else None
                        )
                        nifti_dir = os.path.join(ti_dir, "niftis")

                        output_files = {"TI": [], "niftis": []}
                        if os.path.exists(nifti_dir):
                            nifti_files = [
                                f
                                for f in os.listdir(nifti_dir)
                                if f.endswith(".nii.gz")
                            ]
                            output_files["niftis"] = [
                                os.path.join(nifti_dir, f) for f in nifti_files
                            ]
                            ti_files = [f for f in nifti_files if "TI_max" in f]
                            output_files["TI"] = [
                                os.path.join(nifti_dir, f) for f in ti_files
                            ]

                        # Add simulation result for this specific combination
                        report_generator.add_simulation_result(
                            subject_id=subject_id,
                            montage_name=montage_name,
                            output_files=output_files,
                            duration=None,
                            status="completed",
                        )

                        # Generate individual report
                        report_path = report_generator.generate()
                        successful_reports += 1
                        self.update_output(
                            f"[SUCCESS] Individual report generated for {subject_id}-{montage_name}: {os.path.basename(report_path)}"
                        )

                    except Exception as e:
                        self.update_output(
                            f"[ERROR] Error generating report for {subject_id}-{montage_name}: {str(e)}",
                            "error",
                        )

            # Summary
            self.update_output(
                f"--- Generated {successful_reports}/{total_reports} individual simulation reports ---"
            )

            if successful_reports > 0:
                reports_dir = self.pm.path_optional("ti_reports")
                self.update_output(f"[INFO] Reports saved in: {reports_dir}")

                # Open the reports directory instead of individual files
                self._open_directory_safely(reports_dir)

        except Exception as e:
            self.update_output(
                f"[ERROR] Error generating simulation reports: {str(e)}", "error"
            )
            import traceback

            self.update_output(f"Traceback: {traceback.format_exc()}", "error")

    def disable_controls(self):
        """Disable all controls except the stop button."""
        self.add_job_btn.setEnabled(False)
        self.remove_job_btn.setEnabled(False)
        self.jobs_scroll.setEnabled(False)
        for card in self._job_cards:
            card.setEnabled(False)
        self.selection_list.setEnabled(False)
        self.refresh_selection_btn.setEnabled(False)
        self.clear_selection_btn.setEnabled(False)
        self.add_montage_sel_btn.setEnabled(False)
        self.remove_montage_sel_btn.setEnabled(False)
        self.sim_type_combo.setEnabled(False)
        self.conductivity_editor_btn.setEnabled(False)
        self.electrode_shape_rect.setEnabled(False)
        self.electrode_shape_ellipse.setEnabled(False)
        self.dimensions_input.setEnabled(False)
        self.thickness_input.setEnabled(False)
        self.parallel_checkbox.setEnabled(False)
        self.parallel_workers_spin.setEnabled(False)

    def enable_controls(self):
        """Re-enable all controls."""
        self.add_job_btn.setEnabled(True)
        self.remove_job_btn.setEnabled(True)
        self.jobs_scroll.setEnabled(True)
        for card in self._job_cards:
            card.setEnabled(True)
        self.selection_list.setEnabled(True)
        self.refresh_selection_btn.setEnabled(True)
        self.clear_selection_btn.setEnabled(True)
        self.add_montage_sel_btn.setEnabled(True)
        self.remove_montage_sel_btn.setEnabled(True)
        self.sim_type_combo.setEnabled(True)
        self.conductivity_editor_btn.setEnabled(True)
        self.electrode_shape_rect.setEnabled(True)
        self.electrode_shape_ellipse.setEnabled(True)
        self.dimensions_input.setEnabled(True)
        self.thickness_input.setEnabled(True)
        self.parallel_checkbox.setEnabled(True)
        self.parallel_workers_spin.setEnabled(self.parallel_checkbox.isChecked())

    def update_current_inputs_visibility(self):
        """No-op stub kept for backward compatibility."""
        pass

    def update_electrode_inputs(self, checked):
        """No-op stub kept for backward compatibility."""
        pass

    def clear_console(self):
        """Clear the output console."""
        self.output_console.clear()

    def stop_simulation(self):
        """Stop the running simulation."""
        # Mark as not running immediately to avoid triggering auto-abort logic from late output.
        self.simulation_running = False

        # Kill all active simulation subprocesses (hard stop)
        try:
            for proc in list(getattr(self, "_active_processes", set())):
                try:
                    proc.terminate_simulation()
                except (RuntimeError, OSError, AttributeError):
                    pass  # Process may already be terminated or object destroyed
            self._active_processes = set()
            self._process_to_job = {}
            self._job_queue = []
        except AttributeError:
            pass  # Attributes may not exist during early initialization or cleanup

        if hasattr(self, "simulation_process") and self.simulation_process:
            # Mark as not running immediately to avoid triggering auto-abort logic from late output.
            # Show stopping message
            self.update_output("Stopping simulation...")
            self.output_console.append(
                '<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">--- SIMULATION TERMINATED BY USER ---</span></div>'
            )

            # Terminate the simulation
            terminated = self.simulation_process.terminate_simulation()

            if terminated:
                self.update_output("Simulation process terminated successfully.")
            else:
                self.update_output(
                    "Failed to terminate simulation process or process already completed."
                )

            # Reset UI state
            self.run_btn.setText("Run Simulation")
            self.action_buttons.set_running(False)

            # Clear parent tab's busy state (with stop_btn parameter for proper state management)
            if hasattr(self, "parent") and self.parent:
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

            # Clean up temporary flex montage files
            if hasattr(self, "temp_flex_files"):
                remaining_files = 0
                for temp_file in self.temp_flex_files:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                            remaining_files += 1
                            self.update_output(
                                f"[CLEANUP] Removed temp file: {temp_file}"
                            )
                    except Exception as e:
                        self.update_output(
                            f"[WARNING] Could not clean up flex file {temp_file}: {str(e)}",
                            "warning",
                        )
                if remaining_files > 0:
                    self.update_output(
                        f"[CLEANUP] Removed {remaining_files} temp files after stop"
                    )
                delattr(self, "temp_flex_files")

            # Re-enable all controls
            self.enable_controls()
        else:
            # If we were using job-based processes only, still show stop UI feedback + reset.
            self.update_output("Stopping simulation...")
            self.output_console.append(
                '<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">--- SIMULATION TERMINATED BY USER ---</span></div>'
            )
            self.run_btn.setText("Run Simulation")
            self.action_buttons.set_running(False)
            if hasattr(self, "parent") and self.parent:
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
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

    def update_output(self, text, message_type="default"):
        """Update the console output with colored text, preserving original formatting."""
        if not text.strip():
            return

        # Strip ANSI escape sequences before any formatting
        text = strip_ansi_codes(text)

        # Filter messages based on debug mode
        if not self.debug_mode:
            # Format simulator progress output in a tree-like structure (Flex-Search-like).
            # This runs before filtering so the prefixed text still matches the important patterns.
            tree_step_prefixes = (
                "Montage visualization:",
                "SimNIBS simulation:",
                "Results processing:",
                "Field extraction:",
                "NIfTI transformation:",
            )
            if (
                text.startswith(tree_step_prefixes)
                and not text.startswith("├─")
                and not text.startswith("└─")
            ):
                text = f"├─ {text}"

            # Match Flex-Search behavior: in non-debug mode, only show messages that
            # utils.py classifies as important for the 'simulator' tab.
            if not is_important_message(text, message_type, "simulator"):
                return

            # Colorize summary lines: blue for starts, white for completes, green for final
            lower = text.lower()
            is_final = lower.startswith("└─") or "completed successfully" in lower
            is_start = lower.startswith("beginning ") or ": starting" in lower
            is_complete = (
                ("✓ complete" in lower)
                or ("results saved to" in lower)
                or ("saved to" in lower)
            )
            color = "#55ff55" if is_final else ("#55aaff" if is_start else "#ffffff")
            # Preserve line breaks and spacing by converting to HTML
            text_html = text.replace("\n", "<br>").replace(" ", "&nbsp;")
            formatted_text = f'<span style="color: {color};">{text_html}</span>'
            scrollbar = self.output_console.verticalScrollBar()
            at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
            self.output_console.append(formatted_text)
            if at_bottom:
                self.output_console.ensureCursorVisible()
            QtWidgets.QApplication.processEvents()
            return

        # Preserve line breaks and spacing in the text by converting to HTML
        # Replace newlines with <br> and spaces with &nbsp; to maintain formatting
        text_html = text.replace("\n", "<br>").replace(" ", "&nbsp;")

        # Format the output based on message type from thread
        if message_type == "error":
            formatted_text = f'<span style="color: #ff5555;"><b>{text_html}</b></span>'
        elif message_type == "warning":
            formatted_text = f'<span style="color: #ffff55;">{text_html}</span>'
        elif message_type == "debug":
            formatted_text = f'<span style="color: #7f7f7f;">{text_html}</span>'
        elif message_type == "command":
            formatted_text = f'<span style="color: #55aaff;">{text_html}</span>'
        elif message_type == "success":
            formatted_text = f'<span style="color: #55ff55;"><b>{text_html}</b></span>'
        elif message_type == "info":
            formatted_text = f'<span style="color: #55ffff;">{text_html}</span>'
        else:
            # Fallback to content-based formatting for backward compatibility
            if "Processing... Only the Stop button is available" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #ffff55; font-weight: bold;">{text_html}</span></div>'
            elif text.strip().startswith("-"):
                # Indented list items
                formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">&nbsp;&nbsp;{text_html}</span>'
            else:
                formatted_text = f'<span style="color: #ffffff;">{text_html}</span>'

        # Check if user is at the bottom of the console before appending
        scrollbar = self.output_console.verticalScrollBar()
        at_bottom = (
            scrollbar.value() >= scrollbar.maximum() - 5
        )  # Allow small tolerance

        # Append to the console with HTML formatting
        self.output_console.append(formatted_text)

        # Only auto-scroll if user was already at the bottom
        if at_bottom:
            self.output_console.ensureCursorVisible()

        QtWidgets.QApplication.processEvents()

    def set_debug_mode(self, debug_mode):
        """Set debug mode for output filtering."""
        self.debug_mode = debug_mode
        # Sync with console widget's internal state if it exists
        if hasattr(self, "console_widget"):
            self.console_widget.debug_mode = debug_mode

    def _open_file_safely(self, file_path):
        """Safely open a file in the default application, with fallbacks for different environments."""
        import webbrowser
        import platform

        try:
            # First try webbrowser (works on most systems)
            webbrowser.open("file://" + os.path.abspath(file_path))
            self.update_output("[INFO] File opened in default application")
        except Exception as e:
            # Fallback: try platform-specific commands
            try:
                system = platform.system().lower()
                if system == "linux":
                    # Try xdg-open first, then common browsers
                    try:
                        subprocess.run(["xdg-open", file_path], check=True)
                        self.update_output("[INFO] File opened with xdg-open")
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        # Try common browsers as fallback
                        browsers = ["firefox", "chromium", "google-chrome", "chrome"]
                        opened = False
                        for browser in browsers:
                            try:
                                subprocess.run([browser, file_path], check=True)
                                self.update_output(f"[INFO] File opened with {browser}")
                                opened = True
                                break
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                continue
                        if not opened:
                            self.update_output(
                                f"[WARNING] File generated but couldn't open automatically: {file_path}"
                            )
                elif system == "darwin":  # macOS
                    subprocess.run(["open", file_path], check=True)
                    self.update_output("[INFO] File opened with macOS open command")
                elif system == "windows":
                    os.startfile(file_path)
                    self.update_output("[INFO] File opened with Windows startfile")
                else:
                    self.update_output(
                        f"[WARNING] File generated but couldn't open automatically: {file_path}"
                    )
            except Exception as e2:
                self.update_output(
                    f"[WARNING] File generated but couldn't open automatically: {file_path}"
                )
                self.update_output(f"[DEBUG] Open error: {str(e2)}")

    def _open_directory_safely(self, dir_path):
        """Safely open a directory in the file manager, with fallbacks for different environments."""
        import platform

        try:
            system = platform.system().lower()
            if system == "linux":
                # Try xdg-open first, then common file managers
                try:
                    subprocess.run(["xdg-open", dir_path], check=True)
                    self.update_output("[INFO] Directory opened with xdg-open")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # Try common file managers as fallback
                    file_managers = ["nautilus", "dolphin", "thunar", "pcmanfm", "nemo"]
                    opened = False
                    for fm in file_managers:
                        try:
                            subprocess.run([fm, dir_path], check=True)
                            self.update_output(f"[INFO] Directory opened with {fm}")
                            opened = True
                            break
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            continue
                    if not opened:
                        self.update_output(
                            f"[WARNING] Directory available but couldn't open file manager: {dir_path}"
                        )
            elif system == "darwin":  # macOS
                subprocess.run(["open", dir_path], check=True)
                self.update_output("[INFO] Directory opened with macOS open command")
            elif system == "windows":
                os.startfile(dir_path)
                self.update_output("[INFO] Directory opened with Windows Explorer")
            else:
                self.update_output(
                    f"[WARNING] Directory available but couldn't open file manager: {dir_path}"
                )
        except Exception as e:
            self.update_output(
                f"[WARNING] Directory available but couldn't open file manager: {dir_path}"
            )
            self.update_output(f"[DEBUG] Open error: {str(e)}")

    def _handle_thread_output(self, text, message_type="default"):
        """Internal handler to track errors and forward to UI update."""
        # If user already stopped the run, don't trigger auto-abort or follow-up actions.
        if not getattr(self, "simulation_running", False):
            self.update_output(text, message_type)
            return

        if message_type == "error":
            # Allow process to continue, but mark that there were errors
            self._had_errors_during_run = True
            # Remember the first triggering error line for reporting
            if not hasattr(self, "_first_error_line") or not getattr(
                self, "_first_error_line", None
            ):
                self._first_error_line = text
            # Abort immediately on first error
            if not self._aborting_due_to_error:
                self._aborting_due_to_error = True
                self.update_output(
                    "[ERROR] Error detected. Aborting simulation and cleaning up partial outputs...",
                    "error",
                )
                # Terminate any running process(es)
                try:
                    # Job-based: kill all active procs and clear queue
                    for proc in list(getattr(self, "_active_processes", set())):
                        try:
                            proc.terminate_simulation()
                        except (RuntimeError, OSError, AttributeError):
                            pass  # Process may already be terminated or object destroyed
                    self._active_processes = set()
                    self._process_to_job = {}
                    self._job_queue = []
                except AttributeError:
                    pass  # Attributes may not exist during early initialization
                # Perform cleanup of outputs generated so far
                try:
                    self._cleanup_partial_outputs()
                except Exception as cleanup_exc:
                    self.update_output(
                        f"[WARNING] Cleanup encountered an issue: {cleanup_exc}",
                        "warning",
                    )
                # Explicitly finish simulation to reset UI state immediately
                self.simulation_finished()
        self.update_output(text, message_type)

    def _cleanup_partial_outputs(self):
        """Remove files/directories created during a failed simulation run."""
        for subject_id in self._current_run_subjects or []:
            sim_root = self.pm.path_optional("simulations", subject_id=subject_id)
            if not sim_root:
                continue
            # Remove tmp directory entirely
            tmp_dir = os.path.join(sim_root, "tmp")
            if os.path.isdir(tmp_dir):
                # Use ignore_errors=True - will silently skip if directory is inaccessible
                shutil.rmtree(tmp_dir, ignore_errors=True)
                self.update_output(f"[CLEANUP] Removed temporary directory: {tmp_dir}")
            # Remove montage-specific output directories that may have been created
            for montage_name in self._current_run_montages or []:
                montage_dir = os.path.join(sim_root, montage_name)
                if os.path.isdir(montage_dir):
                    # Use ignore_errors=True - will silently skip if directory is inaccessible
                    shutil.rmtree(montage_dir, ignore_errors=True)
                    self.update_output(
                        f"[CLEANUP] Removed partial montage outputs: {montage_dir}"
                    )
            # Mark log files created during this failed run as errored by renaming them
            logs_dir = self.pm.path("ti_logs", subject_id=subject_id)
            if os.path.isdir(logs_dir):
                try:
                    for fname in list(os.listdir(logs_dir)):
                        fpath = os.path.join(logs_dir, fname)
                        # Heuristic: rename simulator logs created after run start
                        try:
                            if (
                                os.path.isfile(fpath)
                                and fname.startswith("simulator_")
                                and not fname.startswith("simulator_errored_")
                            ):
                                if (
                                    self._run_start_time is None
                                    or os.path.getmtime(fpath)
                                    >= self._run_start_time - 1
                                ):
                                    suffix = fname[len("simulator_") :]
                                    new_name = f"simulator_errored_{suffix}"
                                    new_path = os.path.join(logs_dir, new_name)
                                    try:
                                        os.rename(fpath, new_path)
                                        self.update_output(
                                            f"[CLEANUP] Marked errored log: {fname} -> {new_name}"
                                        )
                                    except (OSError, PermissionError):
                                        pass  # If rename fails (e.g., file locked), skip silently
                        except (OSError, ValueError):
                            continue  # Skip files with access errors or invalid timestamps
                except (OSError, PermissionError):
                    pass  # Best-effort log cleanup - may fail if directory is inaccessible

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
                if not self.validate_electrode(pair[0]) or not self.validate_electrode(
                    pair[1]
                ):
                    self.update_output(
                        "Error: Invalid electrode format (should be E1, E2)"
                    )
                    return

            # Get project directory using path manager
            project_dir = self.pm.project_dir
            from tit.sim import utils as sim_utils

            # Persist montage via shared sim utils (reused by CLI + GUI)
            target_net = montage_data["target_net"]
            sim_utils.upsert_montage(
                project_dir=project_dir,
                eeg_net=target_net,
                montage_name=montage_data["name"],
                electrode_pairs=montage_data["electrode_pairs"],
                mode=("U" if montage_data["is_unipolar"] else "M"),
            )
            montage_file = sim_utils.montage_list_path(project_dir)

            # Format pairs for display
            pairs_text = ", ".join(
                [f"{pair[0]}↔{pair[1]}" for pair in montage_data["electrode_pairs"]]
            )

            montage_type = (
                "uni_polar_montages"
                if montage_data["is_unipolar"]
                else "multi_polar_montages"
            )
            self.update_output(
                f"Added {montage_type.split('_')[0]} montage '{montage_data['name']}' for net {target_net} with pairs: {pairs_text}"
            )
            self.update_output(f"Montage saved to: {montage_file}")

            # Refresh the list of montages
            self.update_montage_list()

    def remove_selected_montage(self):
        """Remove the selected montage from the montage list file."""
        try:
            # Get selected montage from the per-job selection list
            selected_items = self.selection_list.selectedItems()
            if not selected_items:
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "Please select a montage to remove."
                )
                return

            # Get the montage name as plain text
            montage_name = selected_items[0].text()
            if not montage_name:
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "Invalid montage selection."
                )
                return

            # Confirm deletion
            reply = QtWidgets.QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete the montage '{montage_name}'?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )

            if reply == QtWidgets.QMessageBox.Yes:
                # Get project directory using path manager
                project_dir = self.pm.project_dir

                # Ensure montage file exists and get its path
                montage_file = self.ensure_montage_file_exists(project_dir)

                # Load existing montage data
                with open(montage_file, "r") as f:
                    montage_data = json.load(f)

                # Get current net and mode from the active job row
                current_net = self.eeg_net_combo.currentText()
                row = self._selection_row
                mode_combo = self.jobs_table.cellWidget(row, 2) if row >= 0 else None
                mode_text = mode_combo.currentText() if mode_combo else "Unipolar"
                montage_type = (
                    "uni_polar_montages"
                    if mode_text == "Unipolar"
                    else "multi_polar_montages"
                )

                # Remove the montage if it exists
                if (
                    current_net in montage_data["nets"]
                    and montage_type in montage_data["nets"][current_net]
                    and montage_name in montage_data["nets"][current_net][montage_type]
                ):

                    del montage_data["nets"][current_net][montage_type][montage_name]

                    # Save the updated montage data
                    with open(montage_file, "w") as f:
                        json.dump(montage_data, f, indent=4)

                    self.update_output(
                        f"Removed montage '{montage_name}' from {montage_type}"
                    )

                    # Refresh the selection list to reflect the change
                    self._refresh_selection_list()
                else:
                    QtWidgets.QMessageBox.warning(
                        self, "Warning", f"Montage '{montage_name}' not found."
                    )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Error removing montage: {str(e)}"
            )
            print(f"Detailed error: {str(e)}")  # For debugging

    def show_conductivity_editor(self):
        """Show the conductivity editor dialog."""
        dialog = ConductivityEditorDialog(self, self.custom_conductivities)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.custom_conductivities = dialog.get_conductivities()

    def _get_conductivities_for_report(self):
        """Get conductivity values formatted for the simulation report."""
        # Default SimNIBS conductivity values
        conductivities = {
            1: {
                "name": "White Matter",
                "conductivity": 0.126,
                "reference": "SimNIBS default",
            },
            2: {
                "name": "Gray Matter",
                "conductivity": 0.275,
                "reference": "SimNIBS default",
            },
            3: {"name": "CSF", "conductivity": 1.654, "reference": "SimNIBS default"},
            4: {"name": "Bone", "conductivity": 0.01, "reference": "SimNIBS default"},
            5: {"name": "Scalp", "conductivity": 0.465, "reference": "SimNIBS default"},
            6: {
                "name": "Eye balls",
                "conductivity": 0.5,
                "reference": "SimNIBS default",
            },
            7: {
                "name": "Compact Bone",
                "conductivity": 0.008,
                "reference": "SimNIBS default",
            },
            8: {
                "name": "Spongy Bone",
                "conductivity": 0.025,
                "reference": "SimNIBS default",
            },
            9: {"name": "Blood", "conductivity": 0.6, "reference": "SimNIBS default"},
            10: {
                "name": "Muscle",
                "conductivity": 0.16,
                "reference": "SimNIBS default",
            },
        }

        # Override with any custom values
        for tissue_num, custom_value in self.custom_conductivities.items():
            if tissue_num in conductivities:
                conductivities[tissue_num]["conductivity"] = custom_value
                conductivities[tissue_num]["reference"] = "Custom (User Modified)"
            else:
                conductivities[tissue_num] = {
                    "name": f"Custom Tissue {tissue_num}",
                    "conductivity": custom_value,
                    "reference": "Custom (User Defined)",
                }

        return conductivities

    def cleanup_temporary_files(self):
        """Clean up temporary simulation completion files after processing."""
        try:
            # Get project directory using path manager
            project_dir = self.pm.project_dir
            derivatives_dir = self.pm.get_derivatives_dir()
            temp_dir = (
                os.path.join(derivatives_dir, "temp") if derivatives_dir else None
            )
            if not temp_dir:
                return

            if not os.path.exists(temp_dir):
                return

            # Find and clean up completion files
            cleaned_count = 0
            for filename in os.listdir(temp_dir):
                if filename.startswith("simulation_completion_") and filename.endswith(
                    ".json"
                ):
                    file_path = os.path.join(temp_dir, filename)
                    try:
                        # Check if file is older than 5 minutes to avoid cleaning files from concurrent simulations
                        file_mtime = os.path.getmtime(file_path)
                        current_time = time.time()
                        if current_time - file_mtime > 300:  # 5 minutes
                            os.remove(file_path)
                            cleaned_count += 1
                            self.update_output(
                                f"[CLEANUP] Removed temporary file: {filename}"
                            )
                        else:
                            # If it's our session, clean it up immediately
                            if (
                                hasattr(self, "simulation_session_id")
                                and self.simulation_session_id
                                and self.simulation_session_id in filename
                            ):
                                os.remove(file_path)
                                cleaned_count += 1
                                self.update_output(
                                    f"[CLEANUP] Removed session file: {filename}"
                                )
                    except Exception as e:
                        self.update_output(
                            f"[WARNING] Could not clean up {filename}: {str(e)}",
                            "warning",
                        )

            if cleaned_count > 0:
                self.update_output(
                    f"[CLEANUP] Removed {cleaned_count} temporary completion file(s)"
                )

            # Also try to remove the temp directory if it's empty
            try:
                if not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
                    self.update_output("[CLEANUP] Removed empty temp directory")
            except OSError:
                pass  # Directory not empty or permission issue, ignore

        except Exception as e:
            self.update_output(f"[ERROR] Error during cleanup: {str(e)}", "warning")

    def _parse_flex_search_name(self, search_name, electrode_type):
        """
        Parse flex-search name and create proper naming format.

        Args:
            search_name: Search directory name with format:
                        - Atlas: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
                        - Spherical: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
                        - Subcortical: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
                        - Legacy cortical: {hemisphere}.{region}_{atlas}_{goal}_{postprocess}
            electrode_type: 'mapped' or 'optimized'

        Returns:
            str: Formatted name following flex_{hemisphere}_{atlas}_{region}_{goal}_{postproc}_{electrode_type}
        """
        try:
            # Clean the search name first
            search_name = search_name.strip()
            # Handle new naming convention first

            # Handle spherical search names: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
            if search_name.startswith("sphere_"):
                parts = search_name.split("_")
                if len(parts) >= 3:
                    hemisphere = "spherical"
                    # Extract coordinate part (e.g., x10y-5z20r5)
                    coords_part = parts[1] if len(parts) > 1 else "coords"
                    goal = parts[-2] if len(parts) >= 3 else "optimization"
                    post_proc = parts[-1] if len(parts) >= 3 else "maxTI"

                    return f"flex_{hemisphere}_{coords_part}_{goal}_{post_proc}_{electrode_type}"

            # Handle subcortical search names: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
            elif search_name.startswith("subcortical_"):
                parts = search_name.split("_")
                if len(parts) >= 5:
                    hemisphere = "subcortical"
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = parts[4]

                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"

            # Handle cortical search names: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
            elif "_" in search_name and len(search_name.split("_")) >= 5:
                parts = search_name.split("_")
                if len(parts) >= 5 and parts[0] in ["lh", "rh"]:
                    hemisphere = parts[0]
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = parts[4]

                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"

            # Fallback: Handle legacy formats for backward compatibility

            # Legacy cortical search names: lh.101_DK40_14_mean
            elif search_name.startswith(("lh.", "rh.")):
                parts = search_name.split("_")
                if len(parts) >= 3:
                    hemisphere_region = parts[0]  # e.g., 'lh.101'
                    atlas = parts[1]  # e.g., 'DK40'
                    goal_postproc = "_".join(parts[2:])  # e.g., '14_mean'

                    # Extract hemisphere and region
                    if "." in hemisphere_region:
                        hemisphere, region = hemisphere_region.split(".", 1)
                    else:
                        hemisphere = "unknown"
                        region = hemisphere_region

                    # Split goal and postProc if possible
                    if "_" in goal_postproc:
                        goal_parts = goal_postproc.split("_")
                        region = goal_parts[0]  # First part is actually the region
                        goal = goal_parts[1] if len(goal_parts) > 1 else "optimization"
                        post_proc = (
                            "_".join(goal_parts[2:]) if len(goal_parts) > 2 else "maxTI"
                        )
                    else:
                        goal = goal_postproc
                        post_proc = "maxTI"

                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"

            # Legacy subcortical search names: subcortical_atlas_region_goal
            elif (
                search_name.startswith("subcortical_")
                and len(search_name.split("_")) == 4
            ):
                parts = search_name.split("_")
                if len(parts) >= 4:
                    hemisphere = "subcortical"
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = "maxTI"  # Default for legacy

                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"

            # Legacy spherical coordinates: assume any other format with underscores
            elif "_" in search_name:
                parts = search_name.split("_")
                hemisphere = "spherical"
                atlas = "coordinates"
                region = "_".join(parts[:-1]) if len(parts) > 1 else search_name
                goal = parts[-1] if parts else "optimization"
                post_proc = "maxTI"

                return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"

            # Fallback for unrecognized formats
            else:
                return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"

        except Exception as e:
            self.update_output(
                f"Warning: Could not parse flex search name '{search_name}': {e}",
                "warning",
            )
            return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"

    def cleanup_old_simulation_directories(self, subject_id):
        """
        Clean up old simulation directories that might interfere with flex-search discovery.
        Only removes directories that don't have recent simulation results.
        """
        try:
            # Get simulation directory using path manager
            simulation_dir = self.pm.path_optional("simulations", subject_id=subject_id)

            if not simulation_dir or not os.path.isdir(simulation_dir):
                return

            # Get current time
            current_time = time.time()
            cutoff_time = current_time - (24 * 60 * 60)  # 24 hours ago

            for item in os.listdir(simulation_dir):
                item_path = os.path.join(simulation_dir, item)

                # Skip tmp directory and files
                if not os.path.isdir(item_path) or item == "tmp":
                    continue

                # Check if directory is old and potentially stale
                try:
                    dir_mtime = os.path.getmtime(item_path)

                    # If directory is older than cutoff and doesn't have recent TI results, consider removing
                    if dir_mtime < cutoff_time:
                        ti_mesh_path = os.path.join(item_path, "TI", "mesh")

                        # Check if it has valid TI results
                        has_valid_results = False
                        if os.path.exists(ti_mesh_path):
                            for file in os.listdir(ti_mesh_path):
                                if (
                                    file.endswith("_TI.msh")
                                    and os.path.getmtime(
                                        os.path.join(ti_mesh_path, file)
                                    )
                                    > cutoff_time
                                ):
                                    has_valid_results = True
                                    break

                        # If no valid recent results, ask user if they want to clean up
                        if not has_valid_results:
                            self.update_output(
                                f"Found old simulation directory: {item} (last modified: {datetime.datetime.fromtimestamp(dir_mtime).strftime('%Y-%m-%d %H:%M')})",
                                "info",
                            )
                            # For now, just warn - in the future could add cleanup logic

                except Exception as e:
                    self.update_output(
                        f"Warning: Could not check directory {item}: {e}", "warning"
                    )

        except Exception as e:
            self.update_output(
                f"Warning: Could not clean up old directories: {e}", "warning"
            )


class AddMontageDialog(QtWidgets.QDialog):
    """Dialog for adding new montages."""

    def __init__(self, parent=None):
        super(AddMontageDialog, self).__init__(parent)
        self.parent = parent
        # Get path manager from parent if available
        if parent and hasattr(parent, "pm"):
            self.pm = parent.pm
        else:
            self.pm = get_path_manager()
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
        if self.parent and hasattr(self.parent, "eeg_net_combo"):
            for i in range(self.parent.eeg_net_combo.count()):
                self.net_combo.addItem(self.parent.eeg_net_combo.itemText(i))
        # Set current net to match parent's selection
        if self.parent and hasattr(self.parent, "eeg_net_combo"):
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
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
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
        electrode_title.setStyleSheet(f"font-weight: bold; font-size: {FONT_SUBHEADING};")
        right_layout.addWidget(electrode_title)

        # Add search box
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search electrodes...")
        self.search_box.textChanged.connect(self.filter_electrodes)
        right_layout.addWidget(self.search_box)

        # Add electrode list widget
        self.electrode_list = QtWidgets.QListWidget()
        self.electrode_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.electrode_list.setStyleSheet(
            """
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
        """
        )
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

            if not net_file:
                return

            # Get SimNIBS directory using path manager
            simnibs_dir = self.pm.path_optional("simnibs")
            if not simnibs_dir or not os.path.isdir(simnibs_dir):
                return

            subject_found = False

            # Look through all subject directories
            for subject_dir in os.listdir(simnibs_dir):
                if subject_dir.startswith("sub-"):
                    subject_id = subject_dir[4:]  # Remove 'sub-' prefix
                    m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
                    if m2m_dir and os.path.isdir(m2m_dir):
                        # Use LeadfieldGenerator to get electrode names (handles both formats)
                        try:
                            from tit.opt.leadfield import LeadfieldGenerator

                            gen = LeadfieldGenerator(m2m_dir)

                            # Clean net file name (remove .csv extension if present)
                            clean_net_name = (
                                net_file.replace(".csv", "")
                                if net_file.endswith(".csv")
                                else net_file
                            )

                            # Get electrodes using the fixed method
                            electrodes = gen.get_electrode_names_from_cap(
                                cap_name=clean_net_name
                            )

                            if electrodes:
                                subject_found = True
                                # Add to list widget (already sorted by get_electrode_names_from_cap)
                                for electrode in electrodes:
                                    self.electrode_list.addItem(electrode)
                                break
                        except (FileNotFoundError, ValueError):
                            # Try next subject
                            continue

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
            "electrode_pairs": electrode_pairs,
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
        self.custom_conductivities = {
            int(k): v for k, v in (custom_conductivities or {}).items()
        }
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
        info_label = QtWidgets.QLabel(
            "Double-click on a value in the 'Value (S/m)' column to edit it."
        )
        info_label.setStyleSheet(
            """
            QLabel {
                background-color: #f0f0f0;
                color: #333;
                padding: 4px 8px 4px 8px;
                border-bottom: 1px solid #ddd;
                font-style: italic;
            }
        """
        )
        layout.addWidget(info_label)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Tissue Number", "Tissue Name", "Value (S/m)", "Reference"]
        )
        self.table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

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
            (
                100,
                "Silicone Rubber",
                29.4,
                "NeuroConn electrodes: Wacker Elastosil R 570/60 RUSS",
            ),
            (500, "Saline", 1.0, "Saturnino et al., 2015"),
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
        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: white;
                alternate-background-color: #f5f5f5;
                selection-background-color: #2196F3;
                selection-color: white;
                gridline-color: #e0e0e0;
                border: none;
            }}
            QHeaderView::section {{
                background-color: #4a4a4a;
                color: white;
                padding: 4px;
                border: none;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 1px;
                font-size: {FONT_MD};
            }}
        """
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(28)
        layout.addWidget(self.table)

        # Button container
        button_container = QtWidgets.QWidget()
        button_container.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        button_container.setStyleSheet(
            """
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
        """
        )
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
                        f"Conductivity value for tissue {tissue_num} must be positive.",
                    )
                    return
                modified_values[tissue_num] = value
                os.environ[f"TISSUE_COND_{tissue_num}"] = str(value)
            except ValueError:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Value",
                    f"Invalid conductivity value for tissue {tissue_num}. Please enter a valid number.",
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
