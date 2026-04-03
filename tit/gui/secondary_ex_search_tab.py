#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Secondary Ex-Search Tab
This module provides a placeholder GUI for exhaustive secondary search,
which augments an existing simulation by adding one extra carrier block.
"""

import os

from PyQt5 import QtWidgets

from tit.gui.components.console import ConsoleWidget
from tit.paths import get_path_manager


class SecondaryExSearchTab(QtWidgets.QWidget):
    """Placeholder tab for secondary exhaustive search."""

    def __init__(self, parent=None):
        super(SecondaryExSearchTab, self).__init__(parent)
        self.parent = parent
        self.pm = get_path_manager()
        self.setup_ui()
        self.refresh_subjects()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QLabel(
            "Secondary Ex-Search augments an existing TI or mTI simulation by "
            "adding one extra carrier block and scoring the combined field."
        )
        info.setWordWrap(True)
        main_layout.addWidget(info)

        form_group = QtWidgets.QGroupBox("Base Simulation")
        form_layout = QtWidgets.QFormLayout(form_group)

        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.currentIndexChanged.connect(self.refresh_simulations)
        form_layout.addRow("Subject:", self.subject_combo)

        sim_row = QtWidgets.QHBoxLayout()
        self.simulation_combo = QtWidgets.QComboBox()
        self.simulation_combo.currentIndexChanged.connect(self.update_summary)
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_subjects)
        sim_row.addWidget(self.simulation_combo)
        sim_row.addWidget(self.refresh_btn)
        form_layout.addRow("Base Simulation:", sim_row)

        self.metric_combo = QtWidgets.QComboBox()
        self.metric_combo.addItem("recursive_ti (TI_Max)", "recursive_ti")
        self.metric_combo.addItem(
            "Botzanowski (Magnitude AM, TI_Max)", "botzanowski_magnitude_am"
        )
        self.metric_combo.addItem(
            "Botzanowski (Directional AM, TI_Max)", "botzanowski_directional_am"
        )
        self.metric_combo.addItem(
            "Botzanowski (Directional AM, TI_Avg)", "botzanowski_directional_am_ti_avg"
        )
        self.metric_combo.addItem(
            "Grossman Ext (Directional AM, TI_Max)", "grossman_ext_directional_am"
        )
        self.metric_combo.addItem(
            "Grossman Ext (Directional AM, TI_Avg)", "grossman_ext_directional_am_ti_avg"
        )
        form_layout.addRow("mTI Metric:", self.metric_combo)

        self.summary = QtWidgets.QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(140)
        self.summary.setPlaceholderText(
            "Selected base simulation summary will appear here."
        )
        form_layout.addRow("Summary:", self.summary)

        main_layout.addWidget(form_group)

        self.run_btn = QtWidgets.QPushButton("Run 2nd Ex-Search")
        self.run_btn.clicked.connect(self.run_placeholder)
        main_layout.addWidget(self.run_btn)

        self.console = ConsoleWidget()
        main_layout.addWidget(self.console)

    def refresh_subjects(self):
        self.subject_combo.blockSignals(True)
        self.subject_combo.clear()
        for subject_id in self.pm.list_subjects():
            self.subject_combo.addItem(subject_id)
        self.subject_combo.blockSignals(False)
        self.refresh_simulations()

    def refresh_simulations(self):
        self.simulation_combo.clear()
        self.summary.clear()
        subject_id = self.subject_combo.currentText().strip()
        if not subject_id:
            return
        for simulation_name in self.pm.list_simulations(subject_id):
            self.simulation_combo.addItem(simulation_name)
        self.update_summary()

    def update_summary(self):
        self.summary.clear()
        subject_id = self.subject_combo.currentText().strip()
        simulation_name = self.simulation_combo.currentText().strip()
        if not subject_id or not simulation_name:
            return
        sim_dir = self.pm.simulation(subject_id, simulation_name)
        hf_mesh_dir = os.path.join(sim_dir, "high_Frequency", "mesh")
        shared_fields_dir = os.path.join(sim_dir, "shared_fields")
        summary_lines = [
            f"Simulation: {simulation_name}",
            f"HF pair fields: {'ready' if os.path.isdir(hf_mesh_dir) and os.listdir(hf_mesh_dir) else 'missing'}",
        ]
        if os.path.isdir(shared_fields_dir):
            summary_lines.append("Shared fields present")
        self.summary.setPlainText("\n".join(summary_lines))

    def run_placeholder(self):
        subject_id = self.subject_combo.currentText().strip()
        simulation_name = self.simulation_combo.currentText().strip()
        metric = self.metric_combo.currentData()
        self.console.clear_console()
        self.console.update_console("=== 2nd Ex-Search ===", "info")
        self.console.update_console(f"Subject: {subject_id}", "info")
        self.console.update_console(f"Base simulation: {simulation_name}", "info")
        self.console.update_console(f"Metric: {metric}", "info")
        self.console.update_console(
            "This tab is now the home for secondary search. The search backend still needs to be implemented.",
            "warning",
        )
