#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""EEG source-forward and fsaverage field-mapping extension.

Two independent pipelines, shown side by side as two boxes on one tab and each
dispatched to ``simnibs_python -m tit.source`` in a background thread:

* **Build forward solution** -- per-subject MNE forward/source-space/morph from
  the SimNIBS head model and a chosen EEG net.
* **Map fields to fsaverage** -- project a simulation's TI_max / TI_normal / |E|
  onto an fsaverage template.

See Also
--------
tit.source.forward.prepare_forward : Forward backend.
tit.source.fsaverage.project_fields_to_fsaverage : Field-map backend.
tit.gui.components.base_thread.BaseProcessThread : Subprocess thread base.
"""

import json
import os
import tempfile

from PyQt5 import QtCore, QtWidgets

from tit.gui.components.base_thread import BaseProcessThread
from tit.gui.components.console import ConsoleWidget
from tit.gui.style import COLOR_ERROR, COLOR_ERROR_DARK, COLOR_ERROR_DARKER
from tit.gui.utils import confirm_overwrite
from tit.paths import get_path_manager

# Extension metadata (required)
EXTENSION_NAME = "Source"
EXTENSION_DESCRIPTION = (
    "Build EEG forward solutions and map simulation fields to fsaverage."
)


class SourceThread(BaseProcessThread):
    """Background thread that runs ``tit.source`` via subprocess."""

    def __init__(self, cmd, env=None, cwd=None):
        super().__init__(cmd=cmd, env=env, cwd=cwd)

    def run(self):
        self.execute_process()


class SourceWidget(QtWidgets.QWidget):
    """Configure and launch the source-forward / fsaverage-map pipelines."""

    source_completed = QtCore.pyqtSignal(str)  # mode

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

        # Subjects (shared by both pipelines)
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

        # Pipelines, side by side.
        pipelines = QtWidgets.QHBoxLayout()

        # Build forward solution
        self.forward_box = QtWidgets.QGroupBox("Build forward solution")
        fwd_form = QtWidgets.QFormLayout(self.forward_box)
        self.net_combo = QtWidgets.QComboBox()
        fwd_form.addRow("EEG net:", self.net_combo)
        self.fwd_spacing = QtWidgets.QComboBox()
        self.fwd_spacing.addItems(["5", "6", "7"])
        fwd_form.addRow("fsaverage spacing:", self.fwd_spacing)
        self.forward_run_button = QtWidgets.QPushButton("Build forward")
        self.forward_run_button.clicked.connect(self._run_forward)
        fwd_form.addRow(self.forward_run_button)
        pipelines.addWidget(self.forward_box)

        # Map fields to fsaverage
        self.fsavg_box = QtWidgets.QGroupBox("Map fields to fsaverage")
        fsavg_form = QtWidgets.QFormLayout(self.fsavg_box)
        self.sim_combo = QtWidgets.QComboBox()
        fsavg_form.addRow("Simulation:", self.sim_combo)
        fields_widget = QtWidgets.QWidget()
        fields_layout = QtWidgets.QHBoxLayout(fields_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        self.field_ti_max = QtWidgets.QCheckBox("TI_max")
        self.field_ti_normal = QtWidgets.QCheckBox("TI_normal")
        self.field_magnitude = QtWidgets.QCheckBox("magnitude")
        self.field_ti_max.setChecked(True)
        self.field_ti_normal.setChecked(True)
        for cb in (self.field_ti_max, self.field_ti_normal, self.field_magnitude):
            fields_layout.addWidget(cb)
        fields_layout.addStretch()
        fsavg_form.addRow("Fields:", fields_widget)
        self.fsavg_spacing = QtWidgets.QComboBox()
        self.fsavg_spacing.addItems(["5", "6", "7"])
        fsavg_form.addRow("fsaverage spacing:", self.fsavg_spacing)
        self.fsavg_run_button = QtWidgets.QPushButton("Map to fsaverage")
        self.fsavg_run_button.clicked.connect(self._run_fsavg)
        fsavg_form.addRow(self.fsavg_run_button)
        pipelines.addWidget(self.fsavg_box)

        layout.addLayout(pipelines)

        # Stop button -- disabled while idle, enabled during a run. Lives in the
        # console header like the Run/Stop controls on the core tabs.
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

        # Shared console (same component as the core tabs)
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            console_label="Output:",
            min_height=200,
            custom_buttons=[self.stop_button],
        )
        layout.addWidget(self.console_widget)

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
        current_net = self.net_combo.currentText()
        self.net_combo.clear()
        nets = [c[:-4] for c in self.pm.list_eeg_caps(first) if c.endswith(".csv")]
        self.net_combo.addItems(nets)
        if current_net in nets:
            self.net_combo.setCurrentText(current_net)

        current_sim = self.sim_combo.currentText()
        self.sim_combo.clear()
        sims = self.pm.list_simulations(first)
        self.sim_combo.addItems(sims)
        if current_sim in sims:
            self.sim_combo.setCurrentText(current_sim)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _selected_fields(self):
        fields = []
        if self.field_ti_max.isChecked():
            fields.append("TI_max")
        if self.field_ti_normal.isChecked():
            fields.append("TI_normal")
        if self.field_magnitude.isChecked():
            fields.append("magnitude")
        return fields

    def _confirm_overwrite(self, paths):
        """Return ``True`` if it is safe to proceed for *paths*.

        Mirrors the rest of the GUI: if any target output already exists, ask
        the user to confirm overwriting before continuing. Returns ``True`` when
        nothing exists yet (no prompt needed) or the user confirmed.
        """
        existing = [p for p in paths if os.path.isdir(p) and os.listdir(p)]
        if not existing:
            return True
        return confirm_overwrite(self, existing[0], "output")

    def _run_forward(self):
        subjects = self._selected_subjects()
        if not subjects:
            self.update_output("Select at least one subject.", "error")
            return
        net = self.net_combo.currentText()
        if not net:
            self.update_output("No EEG net available for the selected subject.", "error")
            return
        if not self._confirm_overwrite([self.pm.forward(sid) for sid in subjects]):
            return
        config = {
            "mode": "forward",
            "subject_ids": subjects,
            "eeg_net": net,
            "fsaverage_spacing": int(self.fwd_spacing.currentText()),
            "cpus": 1,
            "overwrite": True,
        }
        self._launch(config)

    def _run_fsavg(self):
        subjects = self._selected_subjects()
        if not subjects:
            self.update_output("Select at least one subject.", "error")
            return
        sim = self.sim_combo.currentText()
        if not sim:
            self.update_output("No simulation available for the selected subject.", "error")
            return
        fields = self._selected_fields()
        if not fields:
            self.update_output("Select at least one field to project.", "error")
            return
        if not self._confirm_overwrite(
            [self.pm.forward_fsaverage(sid) for sid in subjects]
        ):
            return
        config = {
            "mode": "fsavg_map",
            "pairs": [{"subject_id": sid, "simulation": sim} for sid in subjects],
            "fields": fields,
            "fsaverage_spacing": int(self.fsavg_spacing.currentText()),
            "workers": 1,
            "overwrite": True,
        }
        self._launch(config)

    def _launch(self, config):
        if self.thread is not None and self.thread.isRunning():
            self.update_output("A run is already in progress.", "warning")
            return
        self._stopping = False
        config["project_dir"] = self.pm.project_dir

        fd, config_path = tempfile.mkstemp(suffix=".json", prefix="source_config_")
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)

        cmd = ["simnibs_python", "-m", "tit.source", config_path]
        self.console_widget.clear_console()
        self.update_output(f"Launching: {' '.join(cmd)}", "command")
        self._set_running(True)

        self.thread = SourceThread(cmd)
        self.thread.output_signal.connect(self.update_output)
        self.thread.error_signal.connect(lambda msg: self.update_output(msg, "error"))
        self.thread.process_finished.connect(
            lambda success, rc, mode=config["mode"]: self._on_finished(
                success, rc, mode
            )
        )
        self.thread.start()

    def _set_running(self, running):
        self.forward_run_button.setEnabled(not running)
        self.fsavg_run_button.setEnabled(not running)
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
            self.source_completed.emit(mode)
        else:
            self.update_output(f"Failed (exit code {returncode}).", "error")

    def update_output(self, text, message_type="default"):
        """Append to the shared console (delegates to ConsoleWidget)."""
        self.console_widget.update_console(text, message_type)


class SourceWindow(QtWidgets.QDialog):
    """Non-modal dialog wrapper for the Source widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Source")
        self.setMinimumSize(900, 700)
        self.setWindowFlag(QtCore.Qt.Window)  # Make it a proper window, not modal

        self.widget = SourceWidget(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)


def main(parent=None):
    """Launch the Source extension as a floating window."""
    window = SourceWindow(parent)
    window.show()
    return window


def run(parent=None):
    """Alternative entry point."""
    return main(parent)
