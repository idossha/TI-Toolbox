#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Solver Parameters Widget

Self-contained widget for differential evolution hyper-parameters:
multi-start count, iterations, population, tolerance, mutation,
recombination, CPU count, and optional diagnostics.
"""

import os

from PyQt5 import QtWidgets


class SolverParamsWidget(QtWidgets.QGroupBox):
    """Hyper-parameters for differential evolution optimizer."""

    def __init__(self, parent=None, title="Hyper Parameters"):
        super().__init__(title, parent)

        # ── Left-column widgets ──────────────────────────────────────────

        self.n_multistart_input = QtWidgets.QSpinBox()
        self.n_multistart_input.setRange(1, 20)
        self.n_multistart_input.setValue(1)
        self.n_multistart_input.setToolTip(
            "Number of optimization runs to perform. Higher values increase "
            "chances of finding global optimum but take longer."
        )

        self.max_iterations_input = QtWidgets.QSpinBox()
        self.max_iterations_input.setRange(50, 2000)
        self.max_iterations_input.setValue(500)
        self.max_iterations_input.setToolTip(
            "Maximum number of optimization iterations."
        )

        self.population_size_input = QtWidgets.QSpinBox()
        self.population_size_input.setRange(4, 100)
        self.population_size_input.setValue(13)
        self.population_size_input.setToolTip(
            "Number of individuals in the population for optimization."
        )

        self.cpus_input = QtWidgets.QSpinBox()
        self.cpus_input.setRange(1, os.cpu_count() or 16)
        self.cpus_input.setValue(1)
        self.cpus_input.setToolTip(
            "Number of CPU cores to use for parallel processing during " "optimization."
        )

        # ── Right-column widgets ─────────────────────────────────────────

        self.tolerance_input = QtWidgets.QDoubleSpinBox()
        self.tolerance_input.setRange(0.0001, 1.0)
        self.tolerance_input.setValue(0.1)
        self.tolerance_input.setDecimals(4)
        self.tolerance_input.setSingleStep(0.01)
        self.tolerance_input.setToolTip(
            "Convergence tolerance for differential evolution optimizer "
            "(default: 0.1)"
        )

        self.mutation_min_input = QtWidgets.QDoubleSpinBox()
        self.mutation_min_input.setRange(0.0, 2.0)
        self.mutation_min_input.setValue(0.01)
        self.mutation_min_input.setDecimals(3)
        self.mutation_min_input.setSingleStep(0.01)
        self.mutation_min_input.setToolTip("Minimum mutation factor (default: 0.01)")

        self.mutation_max_input = QtWidgets.QDoubleSpinBox()
        self.mutation_max_input.setRange(0.0, 2.0)
        self.mutation_max_input.setValue(0.5)
        self.mutation_max_input.setDecimals(3)
        self.mutation_max_input.setSingleStep(0.01)
        self.mutation_max_input.setToolTip("Maximum mutation factor (default: 0.5)")

        self.recombination_input = QtWidgets.QDoubleSpinBox()
        self.recombination_input.setRange(0.0, 1.0)
        self.recombination_input.setValue(0.7)
        self.recombination_input.setDecimals(2)
        self.recombination_input.setSingleStep(0.05)
        self.recombination_input.setToolTip(
            "Recombination probability for differential evolution " "(default: 0.7)"
        )

        # ── Diagnostic options ───────────────────────────────────────────

        self.detailed_results_checkbox = QtWidgets.QCheckBox(
            "Enable detailed results output"
        )
        self.detailed_results_checkbox.setChecked(False)
        self.detailed_results_checkbox.setToolTip(
            "Enable detailed results output (creates additional "
            "visualization and debug files)"
        )

        self.visualize_skin_checkbox = QtWidgets.QCheckBox(
            "Visualize valid skin region"
        )
        self.visualize_skin_checkbox.setChecked(False)
        self.visualize_skin_checkbox.setToolTip(
            "Create 2D visualizations of valid skin region for electrode "
            "placement (requires detailed results)"
        )
        self.visualize_skin_checkbox.setEnabled(False)

        self.skin_net_combo = QtWidgets.QComboBox()
        self.skin_net_combo.setEnabled(False)
        self.skin_net_combo.setToolTip(
            "Select EEG net to visualize electrode positions on skin surface"
        )

        # ── Layout (QGridLayout, 2 logical columns) ─────────────────────

        grid = QtWidgets.QGridLayout(self)

        # Left column
        row = 0
        grid.addWidget(QtWidgets.QLabel("Number of Optimization Runs:"), row, 0)
        grid.addWidget(self.n_multistart_input, row, 1)

        row += 1
        grid.addWidget(QtWidgets.QLabel("Max Optimization Iterations:"), row, 0)
        grid.addWidget(self.max_iterations_input, row, 1)

        row += 1
        grid.addWidget(QtWidgets.QLabel("Population Size:"), row, 0)
        grid.addWidget(self.population_size_input, row, 1)

        row += 1
        grid.addWidget(QtWidgets.QLabel("Number of CPUs:"), row, 0)
        grid.addWidget(self.cpus_input, row, 1)

        # Right column
        row = 0
        grid.addWidget(QtWidgets.QLabel("Tolerance:"), row, 2)
        grid.addWidget(self.tolerance_input, row, 3)

        row += 1
        grid.addWidget(QtWidgets.QLabel("Mutation (min, max):"), row, 2)
        mutation_layout = QtWidgets.QHBoxLayout()
        mutation_layout.addWidget(self.mutation_min_input)
        mutation_layout.addWidget(QtWidgets.QLabel("to"))
        mutation_layout.addWidget(self.mutation_max_input)
        mutation_layout.setContentsMargins(0, 0, 0, 0)
        mutation_widget = QtWidgets.QWidget()
        mutation_widget.setLayout(mutation_layout)
        grid.addWidget(mutation_widget, row, 3)

        row += 1
        grid.addWidget(QtWidgets.QLabel("Recombination:"), row, 2)
        grid.addWidget(self.recombination_input, row, 3)

        row += 1
        grid.addWidget(self.detailed_results_checkbox, row, 2, 1, 2)

        row += 1
        grid.addWidget(self.visualize_skin_checkbox, row, 2, 1, 2)

        row += 1
        grid.addWidget(QtWidgets.QLabel("Visualization EEG Net:"), row, 2)
        grid.addWidget(self.skin_net_combo, row, 3)

        # Column sizing
        grid.setColumnMinimumWidth(1, 120)
        grid.setColumnMinimumWidth(3, 120)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setHorizontalSpacing(20)

        # ── Internal signals ─────────────────────────────────────────────

        self.detailed_results_checkbox.toggled.connect(
            self._on_detailed_results_toggled
        )
        self.visualize_skin_checkbox.toggled.connect(self._on_visualize_skin_toggled)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_params(self) -> dict:
        """Return dict of solver params for ``FlexConfig`` construction.

        Keys: ``n_multistart``, ``max_iterations``, ``population_size``,
        ``tolerance``, ``mutation`` (str ``"min,max"``), ``recombination``,
        ``cpus``, ``detailed_results``, ``visualize_valid_skin_region``.
        """
        mutation_str = (
            f"{self.mutation_min_input.value()}," f"{self.mutation_max_input.value()}"
        )
        return {
            "n_multistart": self.n_multistart_input.value(),
            "max_iterations": self.max_iterations_input.value(),
            "population_size": self.population_size_input.value(),
            "tolerance": self.tolerance_input.value(),
            "mutation": mutation_str,
            "recombination": self.recombination_input.value(),
            "cpus": self.cpus_input.value(),
            "detailed_results": self.detailed_results_checkbox.isChecked(),
            "visualize_valid_skin_region": (self.visualize_skin_checkbox.isChecked()),
        }

    def get_skin_net_combo(self) -> QtWidgets.QComboBox:
        """Return reference to ``skin_net_combo`` for external population."""
        return self.skin_net_combo

    def setEnabled(self, enabled: bool):
        """Enable or disable all child widgets."""
        super().setEnabled(enabled)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_detailed_results_toggled(self):
        """Handle detailed results checkbox state change."""
        checked = self.detailed_results_checkbox.isChecked()
        self.visualize_skin_checkbox.setEnabled(checked)
        if not checked:
            self.visualize_skin_checkbox.setChecked(False)
            self.skin_net_combo.setEnabled(False)

    def _on_visualize_skin_toggled(self):
        """Handle visualize skin checkbox state change."""
        checked = self.visualize_skin_checkbox.isChecked()
        self.skin_net_combo.setEnabled(checked)
        if not checked:
            self.skin_net_combo.setCurrentIndex(-1)
