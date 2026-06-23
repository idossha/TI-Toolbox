#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Microscale (field -> neuron) coupling extension.

Drives NEURON multicompartment neuron models with a completed simulation's
TI/mTI field and reports how the neurons respond -- accounting for field
intensity *and* orientation.  Dispatches to ``simnibs_python -m tit.microscale``
in a background thread.

Two modes:

* **Response** -- drive each target with the kHz carriers; report somatic spike
  counts and per-cell polarization maps.
* **Threshold** -- bisect the field amplitude to each target's firing threshold.

See Also
--------
tit.microscale.coupling : Coupling/run backend.
tit.gui.components.base_thread.BaseProcessThread : Subprocess thread base.
"""

import json
import os
import tempfile

from PyQt5 import QtCore, QtWidgets

from tit.gui.components.base_thread import BaseProcessThread
from tit.gui.components.console import ConsoleWidget
from tit.gui.style import COLOR_ERROR, COLOR_ERROR_DARK, COLOR_ERROR_DARKER
from tit.paths import get_path_manager

# Extension metadata (required)
EXTENSION_NAME = "Microscale"
EXTENSION_DESCRIPTION = (
    "Drive NEURON neuron models with a simulation's TI field (intensity + "
    "orientation)."
)


class MicroscaleThread(BaseProcessThread):
    """Background thread that runs ``tit.microscale`` via subprocess."""

    def __init__(self, cmd, env=None, cwd=None):
        super().__init__(cmd=cmd, env=env, cwd=cwd)

    def run(self):
        self.execute_process()


class MicroscaleWidget(QtWidgets.QWidget):
    """Configure and launch the microscale response / threshold pipeline."""

    microscale_completed = QtCore.pyqtSignal(str)  # mode

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.pm = get_path_manager()
        self.thread = None
        self._stopping = False
        self._build_ui()
        self.refresh_subjects()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Subjects
        subj_box = QtWidgets.QGroupBox("Subjects")
        subj_layout = QtWidgets.QVBoxLayout(subj_box)
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.subject_list.itemSelectionChanged.connect(self._on_subjects_changed)
        subj_layout.addWidget(self.subject_list)
        self.refresh_button = QtWidgets.QPushButton("Refresh subjects")
        self.refresh_button.clicked.connect(self.refresh_subjects)
        subj_layout.addWidget(self.refresh_button)
        layout.addWidget(subj_box)

        # Parameters
        param_box = QtWidgets.QGroupBox("Neuron coupling")
        form = QtWidgets.QFormLayout(param_box)

        self.sim_combo = QtWidgets.QComboBox()
        form.addRow("Simulation:", self.sim_combo)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(self._available_models())
        form.addRow("Neuron model:", self.model_combo)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["response", "threshold"])
        form.addRow("Mode:", self.mode_combo)

        carriers = QtWidgets.QWidget()
        carriers_layout = QtWidgets.QHBoxLayout(carriers)
        carriers_layout.setContentsMargins(0, 0, 0, 0)
        self.f1_spin = QtWidgets.QDoubleSpinBox()
        self.f1_spin.setRange(1.0, 100000.0)
        self.f1_spin.setValue(2000.0)
        self.f1_spin.setSuffix(" Hz")
        self.f2_spin = QtWidgets.QDoubleSpinBox()
        self.f2_spin.setRange(1.0, 100000.0)
        self.f2_spin.setValue(2010.0)
        self.f2_spin.setSuffix(" Hz")
        carriers_layout.addWidget(self.f1_spin)
        carriers_layout.addWidget(self.f2_spin)
        form.addRow("Carriers (f1, f2):", carriers)

        self.duration_spin = QtWidgets.QDoubleSpinBox()
        self.duration_spin.setRange(1.0, 10000.0)
        self.duration_spin.setValue(100.0)
        self.duration_spin.setSuffix(" ms")
        form.addRow("Duration:", self.duration_spin)

        self.targets_edit = QtWidgets.QPlainTextEdit()
        self.targets_edit.setPlaceholderText(
            "One target per line: x,y,z  (mm, SimNIBS subject space)"
        )
        self.targets_edit.setMaximumHeight(100)
        form.addRow("Targets:", self.targets_edit)

        self.run_button = QtWidgets.QPushButton("Run")
        self.run_button.clicked.connect(self._run)
        form.addRow(self.run_button)
        layout.addWidget(param_box)

        # Stop button (lives in console header like the core tabs)
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ERROR};
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
            }}
            QPushButton:hover {{ background-color: {COLOR_ERROR_DARK}; }}
            QPushButton:pressed {{ background-color: {COLOR_ERROR_DARKER}; }}
            QPushButton:disabled {{ background-color: #cccccc; color: #888888; }}
        """)

        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            console_label="Output:",
            min_height=200,
            custom_buttons=[self.stop_button],
        )
        layout.addWidget(self.console_widget)

    @staticmethod
    def _available_models():
        from tit.microscale.models import list_models

        return list_models()

    # ------------------------------------------------------------------
    # Population / refresh
    # ------------------------------------------------------------------

    def refresh_subjects(self):
        self.subject_list.clear()
        for sid in self.pm.list_simnibs_subjects():
            self.subject_list.addItem(sid)

    def _selected_subjects(self):
        return [item.text() for item in self.subject_list.selectedItems()]

    def _on_subjects_changed(self):
        subjects = self._selected_subjects()
        if not subjects:
            return
        first = subjects[0]
        current_sim = self.sim_combo.currentText()
        self.sim_combo.clear()
        sims = self.pm.list_simulations(first)
        self.sim_combo.addItems(sims)
        if current_sim in sims:
            self.sim_combo.setCurrentText(current_sim)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _parse_targets(self):
        """Parse the targets text box into a list of (x, y, z) tuples."""
        targets = []
        for line in self.targets_edit.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p for p in line.replace(",", " ").split() if p]
            if len(parts) != 3:
                raise ValueError(f"target must be 'x,y,z': {line!r}")
            targets.append([float(p) for p in parts])
        return targets

    def _run(self):
        subjects = self._selected_subjects()
        if not subjects:
            self.update_output("Select at least one subject.", "error")
            return
        sim = self.sim_combo.currentText()
        if not sim:
            self.update_output("No simulation available for the subject.", "error")
            return
        try:
            targets = self._parse_targets()
        except ValueError as exc:
            self.update_output(str(exc), "error")
            return
        if not targets:
            self.update_output("Enter at least one target coordinate.", "error")
            return

        config = {
            "mode": self.mode_combo.currentText(),
            "subject_ids": subjects,
            "sim_name": sim,
            "model": self.model_combo.currentText(),
            "targets": targets,
            "carrier_freqs": [self.f1_spin.value(), self.f2_spin.value()],
            "duration": self.duration_spin.value(),
            "overwrite": True,
        }
        self._launch(config)

    def _launch(self, config):
        if self.thread is not None and self.thread.isRunning():
            self.update_output("A run is already in progress.", "warning")
            return
        self._stopping = False
        config["project_dir"] = self.pm.project_dir

        fd, config_path = tempfile.mkstemp(suffix=".json", prefix="microscale_config_")
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)

        cmd = ["simnibs_python", "-m", "tit.microscale", config_path]
        self.console_widget.clear_console()
        self.update_output(f"Launching: {' '.join(cmd)}", "command")
        self._set_running(True)

        self.thread = MicroscaleThread(cmd)
        self.thread.output_signal.connect(self.update_output)
        self.thread.error_signal.connect(lambda msg: self.update_output(msg, "error"))
        self.thread.process_finished.connect(
            lambda success, rc, mode=config["mode"]: self._on_finished(
                success, rc, mode
            )
        )
        self.thread.start()

    def _set_running(self, running):
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _stop(self):
        if self.thread is None or not self.thread.isRunning():
            return
        self._stopping = True
        self.update_output("Stopping...", "warning")
        if self.thread.terminate_process():
            self.update_output("Stopped.", "info")
        else:
            self.update_output("Failed to stop.", "error")

    def _on_finished(self, success, returncode, mode):
        self._set_running(False)
        if self._stopping:
            self._stopping = False
            return
        if success:
            self.update_output("Done.", "success")
            self.microscale_completed.emit(mode)
        else:
            self.update_output(f"Failed (exit code {returncode}).", "error")

    def update_output(self, text, message_type="default"):
        """Append to the shared console (delegates to ConsoleWidget)."""
        self.console_widget.update_console(text, message_type)


class MicroscaleWindow(QtWidgets.QDialog):
    """Non-modal dialog wrapper for the Microscale widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Microscale")
        self.setMinimumSize(900, 700)
        self.setWindowFlag(QtCore.Qt.Window)

        self.widget = MicroscaleWidget(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)


def main(parent=None):
    """Launch the Microscale extension as a floating window."""
    window = MicroscaleWindow(parent)
    window.show()
    return window


def run(parent=None):
    """Alternative entry point."""
    return main(parent)
