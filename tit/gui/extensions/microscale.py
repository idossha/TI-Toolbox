#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Microscale coupling extension: cortical polarization map.

Computes the **subthreshold cortical polarization map** a completed simulation's
TI/mTI field induces -- the per-vertex somatic ΔVm (intensity *and* orientation
aware) -- over the TI central surface, plus a NEURON-refined distribution on a
subsample.  Dispatches to ``simnibs_python -m tit.microscale`` (mode
``polarization``) in a background thread.

Outputs land under ``derivatives/SimNIBS/sub-<id>/microscale/<sim>/``:
the ΔVm map as a ``.msh``/GIFTI surface overlay, a ``_summary.csv`` table, the
full ``_polarization.npz``, and a two-panel ``_polarization.png`` figure.

See Also
--------
tit.microscale.population : ``run_population`` -- the pipeline backend.
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
    "Map a simulation's TI field to cortical neuron polarization (ΔVm; "
    "intensity + orientation)."
)


class MicroscaleThread(BaseProcessThread):
    """Background thread that runs ``tit.microscale`` via subprocess."""

    def __init__(self, cmd, env=None, cwd=None):
        super().__init__(cmd=cmd, env=env, cwd=cwd)

    def run(self):
        self.execute_process()


class MicroscaleWidget(QtWidgets.QWidget):
    """Configure and launch the polarization-map pipeline."""

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

        # Polarization-map parameters
        param_box = QtWidgets.QGroupBox("Polarization map")
        form = QtWidgets.QFormLayout(param_box)

        self.sim_combo = QtWidgets.QComboBox()
        form.addRow("Simulation:", self.sim_combo)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(self._available_models())
        form.addRow("Neuron model:", self.model_combo)

        self.coupling_spin = QtWidgets.QDoubleSpinBox()
        self.coupling_spin.setDecimals(3)
        self.coupling_spin.setRange(0.0, 5.0)
        self.coupling_spin.setSingleStep(0.01)
        self.coupling_spin.setValue(0.27)
        self.coupling_spin.setSuffix(" mV/(V/m)")
        self.coupling_spin.setToolTip(
            "First-order somatic coupling (Radman et al. 2009: 0.27 for L5 PC)."
        )
        form.addRow("Coupling:", self.coupling_spin)

        # Cluster threshold on TI_normal (optional; 0 = whole surface).
        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setRange(0.0, 100.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setValue(0.0)
        self.threshold_spin.setSuffix(" V/m")
        self.threshold_spin.setToolTip(
            "Keep cluster vertices with TI_normal ≥ this. 0 = whole surface."
        )
        form.addRow("Cluster threshold:", self.threshold_spin)

        # NEURON refinement (subsample / clones / azimuths). 0 subsample = analytic only.
        refine = QtWidgets.QWidget()
        refine_layout = QtWidgets.QHBoxLayout(refine)
        refine_layout.setContentsMargins(0, 0, 0, 0)
        self.subsample_spin = QtWidgets.QSpinBox()
        self.subsample_spin.setRange(0, 1000)
        self.subsample_spin.setValue(50)
        self.subsample_spin.setPrefix("subsample ")
        self.clones_spin = QtWidgets.QSpinBox()
        self.clones_spin.setRange(1, 50)
        self.clones_spin.setValue(5)
        self.clones_spin.setPrefix("clones ")
        self.azimuth_spin = QtWidgets.QSpinBox()
        self.azimuth_spin.setRange(1, 36)
        self.azimuth_spin.setValue(6)
        self.azimuth_spin.setPrefix("azimuths ")
        refine_layout.addWidget(self.subsample_spin)
        refine_layout.addWidget(self.clones_spin)
        refine_layout.addWidget(self.azimuth_spin)
        form.addRow("NEURON refine:", refine)

        self.run_button = QtWidgets.QPushButton("Run polarization map")
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

    def _run(self):
        subjects = self._selected_subjects()
        if not subjects:
            self.update_output("Select at least one subject.", "error")
            return
        sim = self.sim_combo.currentText()
        if not sim:
            self.update_output("No simulation available for the subject.", "error")
            return

        threshold = self.threshold_spin.value()
        config = {
            "mode": "polarization",
            "subject_ids": subjects,
            "sim_name": sim,
            "model": self.model_combo.currentText(),
            "polarization_coupling": self.coupling_spin.value(),
            "cluster_threshold": threshold if threshold > 0 else None,
            "n_subsample": self.subsample_spin.value(),
            "n_clones": self.clones_spin.value(),
            "n_azimuth": self.azimuth_spin.value(),
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
