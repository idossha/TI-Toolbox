#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Secondary exhaustive search GUI.

Starts from a fixed TI base simulation and searches one added carrier block
using a precomputed leadfield.
"""

import os
import re
import json

from PyQt5 import QtCore, QtWidgets

from tit.gui.components.console import ConsoleWidget
from tit.opt import (
    BucketElectrodes,
    PoolElectrodes,
    SecondaryExConfig,
    run_secondary_ex_search,
)
from tit.opt.leadfield import LeadfieldGenerator
from tit.opt.secondary import load_base_montage
from tit.paths import get_path_manager
from tit.sim.utils import ensure_montage_file


class SecondaryExSearchThread(QtCore.QThread):
    finished_signal = QtCore.pyqtSignal(bool, object, str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

    def run(self):
        try:
            result = run_secondary_ex_search(self.config)
            self.finished_signal.emit(True, result, "")
        except Exception as exc:
            self.finished_signal.emit(False, None, str(exc))


class SecondaryExSearchTab(QtWidgets.QWidget):
    """Tab for secondary exhaustive search from a fixed TI base montage."""

    def __init__(self, parent=None):
        super(SecondaryExSearchTab, self).__init__(parent)
        self.parent = parent
        self.pm = get_path_manager()
        self.thread = None
        self.setup_ui()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QLabel(
            "2nd Ex-Search starts from one saved unipolar TI montage with two fixed "
            "pairs, rebuilds its fields from the selected leadfield, and searches one "
            "added carrier block."
        )
        info.setWordWrap(True)
        main_layout.addWidget(info)

        form_group = QtWidgets.QGroupBox("Configuration")
        form = QtWidgets.QFormLayout(form_group)

        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.currentIndexChanged.connect(self._refresh_subject_dependent_combos)
        form.addRow("Subject:", self.subject_combo)

        self.leadfield_combo = QtWidgets.QComboBox()
        self.leadfield_combo.currentIndexChanged.connect(self._refresh_montages_from_leadfield)
        form.addRow("Leadfield:", self.leadfield_combo)

        self.base_montage_combo = QtWidgets.QComboBox()
        self.base_montage_combo.currentIndexChanged.connect(self.update_summary)
        form.addRow("Base TI Montage:", self.base_montage_combo)

        self.roi_combo = QtWidgets.QComboBox()
        form.addRow("ROI:", self.roi_combo)

        self.metric_combo = QtWidgets.QComboBox()
        self.metric_combo.addItem("Recursive TI (TI_Max)", "recursive_ti")
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
        form.addRow("mTI Metric:", self.metric_combo)

        self.rb_all_combinations = QtWidgets.QRadioButton("All-Combinations")
        self.rb_bucketed = QtWidgets.QRadioButton("Bucketed")
        self.rb_all_combinations.setChecked(True)
        self.rb_all_combinations.toggled.connect(self._update_electrode_mode_visibility)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.addWidget(self.rb_all_combinations)
        mode_row.addWidget(self.rb_bucketed)
        mode_row.addStretch()
        form.addRow("Electrode Mode:", mode_row)

        self.all_electrodes_widget = QtWidgets.QWidget()
        all_electrodes_layout = QtWidgets.QVBoxLayout(self.all_electrodes_widget)
        all_electrodes_layout.setContentsMargins(0, 0, 0, 0)
        self.electrode_pool_input = QtWidgets.QLineEdit()
        self.electrode_pool_input.setPlaceholderText("e.g. E001, E010, E085, E120")
        all_electrodes_layout.addWidget(self.electrode_pool_input)
        form.addRow("Added Carrier Pool:", self.all_electrodes_widget)

        self.bucketed_widget = QtWidgets.QWidget()
        bucketed_layout = QtWidgets.QFormLayout(self.bucketed_widget)
        bucketed_layout.setContentsMargins(0, 0, 0, 0)
        self.e3_plus_input = QtWidgets.QLineEdit()
        self.e3_plus_input.setPlaceholderText("e.g. E001, E010")
        self.e3_minus_input = QtWidgets.QLineEdit()
        self.e3_minus_input.setPlaceholderText("e.g. E020, E030")
        self.e4_plus_input = QtWidgets.QLineEdit()
        self.e4_plus_input.setPlaceholderText("e.g. E040, E050")
        self.e4_minus_input = QtWidgets.QLineEdit()
        self.e4_minus_input.setPlaceholderText("e.g. E060, E070")
        bucketed_layout.addRow("E3+:", self.e3_plus_input)
        bucketed_layout.addRow("E3-:", self.e3_minus_input)
        bucketed_layout.addRow("E4+:", self.e4_plus_input)
        bucketed_layout.addRow("E4-:", self.e4_minus_input)
        form.addRow("Bucketed Inputs:", self.bucketed_widget)

        self.current_spin = QtWidgets.QDoubleSpinBox()
        self.current_spin.setRange(0.1, 20.0)
        self.current_spin.setValue(1.0)
        self.current_spin.setSuffix(" mA")
        form.addRow("Current per Pair:", self.current_spin)

        self.roi_radius_spin = QtWidgets.QDoubleSpinBox()
        self.roi_radius_spin.setRange(1.0, 20.0)
        self.roi_radius_spin.setValue(3.0)
        self.roi_radius_spin.setSuffix(" mm")
        form.addRow("ROI Radius:", self.roi_radius_spin)

        self.summary = QtWidgets.QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(140)
        form.addRow("Summary:", self.summary)

        main_layout.addWidget(form_group)

        button_row = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_subjects)
        button_row.addWidget(self.refresh_btn)

        self.run_btn = QtWidgets.QPushButton("Run 2nd Ex-Search")
        self.run_btn.clicked.connect(self.run_search)
        button_row.addWidget(self.run_btn)
        button_row.addStretch()
        main_layout.addLayout(button_row)

        self.console = ConsoleWidget()
        main_layout.addWidget(self.console)

        self._update_electrode_mode_visibility()
        self.refresh_subjects()

    def refresh_subjects(self):
        self.subject_combo.blockSignals(True)
        current_subject = self.subject_combo.currentText().strip()
        self.subject_combo.clear()
        for subject_id in self.pm.list_subjects():
            self.subject_combo.addItem(subject_id)
        if current_subject:
            idx = self.subject_combo.findText(current_subject)
            if idx >= 0:
                self.subject_combo.setCurrentIndex(idx)
        self.subject_combo.blockSignals(False)
        self._refresh_all_subject_data()

    def _refresh_subject_dependent_combos(self):
        self.refresh_leadfields()
        self.refresh_montages()
        self.refresh_rois()
        self.summary.clear()

    def _refresh_all_subject_data(self):
        self._refresh_subject_dependent_combos()
        self.update_summary()

    def refresh_leadfields(self):
        self.leadfield_combo.blockSignals(True)
        current_net = self.leadfield_combo.currentText().strip()
        self.leadfield_combo.clear()
        subject_id = self.subject_combo.currentText().strip()
        if not subject_id:
            self.leadfield_combo.blockSignals(False)
            return
        try:
            gen = LeadfieldGenerator(subject_id)
            for net_name, hdf5_path, _size in gen.list_leadfields(subject_id):
                self.leadfield_combo.addItem(net_name, hdf5_path)
        except Exception:
            pass
        if current_net:
            idx = self.leadfield_combo.findText(current_net)
            if idx >= 0:
                self.leadfield_combo.setCurrentIndex(idx)
        self.leadfield_combo.blockSignals(False)

    def _selected_eeg_net(self):
        net = self.leadfield_combo.currentText().strip()
        if net and not net.endswith(".csv"):
            return f"{net}.csv"
        return net

    def _refresh_montages_from_leadfield(self):
        self.refresh_montages()
        self.update_summary()

    def refresh_montages(self):
        current_data = self.base_montage_combo.currentData()
        self.base_montage_combo.blockSignals(True)
        self.base_montage_combo.clear()
        eeg_net = self._selected_eeg_net()
        if not eeg_net:
            self.base_montage_combo.blockSignals(False)
            return
        entries = self._get_montage_entries_for_params(eeg_net, "U")
        self.console.update_console(
            f"2nd Ex-Search montage lookup: net='{eeg_net}', matches={len(entries)}",
            "info",
        )
        for montage_name, pairs in entries:
            self.base_montage_combo.addItem(
                self._format_montage_display(montage_name, pairs),
                {"name": montage_name, "eeg_net": eeg_net},
            )
        if current_data:
            current_name = current_data.get("name") if isinstance(current_data, dict) else current_data
            current_net = current_data.get("eeg_net") if isinstance(current_data, dict) else eeg_net
            for idx in range(self.base_montage_combo.count()):
                item_data = self.base_montage_combo.itemData(idx)
                if (
                    isinstance(item_data, dict)
                    and item_data.get("name") == current_name
                    and item_data.get("eeg_net") == current_net
                ):
                    self.base_montage_combo.setCurrentIndex(idx)
                    break
        elif self.base_montage_combo.count() > 0:
            self.base_montage_combo.setCurrentIndex(0)
        self.base_montage_combo.blockSignals(False)

    def _get_montage_entries_for_params(self, eeg_net, sim_mode):
        try:
            project_dir = self.pm.project_dir
            if not project_dir:
                return []
            montage_file = ensure_montage_file(project_dir)
            with open(montage_file, "r") as f:
                montage_data = json.load(f)
            net_type = (
                "uni_polar_montages" if sim_mode == "U" else "multi_polar_montages"
            )
            nets = montage_data.get("nets", {})
            net_key = None
            candidates = [eeg_net]
            if eeg_net.endswith(".csv"):
                candidates.append(eeg_net[:-4])
            else:
                candidates.append(f"{eeg_net}.csv")
            for candidate in candidates:
                if candidate in nets:
                    net_key = candidate
                    break
            if net_key is None:
                return []
            montages = nets[net_key].get(net_type, {})
            return [(name, pairs) for name, pairs in montages.items()]
        except (OSError, json.JSONDecodeError, KeyError):
            return []

    @staticmethod
    def _format_montage_display(name, pairs):
        if not pairs:
            return name
        ch_parts = [f"ch{i + 1}{{{p[0]},{p[1]}}}" for i, p in enumerate(pairs)]
        return f"{name}: {', '.join(ch_parts)}"

    def refresh_rois(self):
        self.roi_combo.clear()
        subject_id = self.subject_combo.currentText().strip()
        if not subject_id:
            return
        roi_dir = self.pm.rois(subject_id)
        if roi_dir and os.path.isdir(roi_dir):
            for name in sorted(os.listdir(roi_dir)):
                if name.endswith(".csv"):
                    self.roi_combo.addItem(name)

    def parse_electrode_input(self, text):
        parts = re.split(r"[,\s;]+", text.strip())
        return [p for p in parts if p]

    def _update_electrode_mode_visibility(self):
        all_combinations = self.rb_all_combinations.isChecked()
        self.all_electrodes_widget.setVisible(all_combinations)
        self.bucketed_widget.setVisible(not all_combinations)

    def update_summary(self):
        self.summary.clear()
        subject_id = self.subject_combo.currentText().strip()
        selected = self.base_montage_combo.currentData() or {}
        montage_name = selected.get("name") if isinstance(selected, dict) else self.base_montage_combo.currentText().strip()
        eeg_net = selected.get("eeg_net") if isinstance(selected, dict) else self._selected_eeg_net()
        if not subject_id or not montage_name or not eeg_net:
            return
        try:
            base = load_base_montage(subject_id, montage_name, eeg_net, project_dir=self.pm.project_dir)
            lines = [
                f"Montage: {montage_name}",
                f"EEG net: {eeg_net}",
                "Base pairs: " + ", ".join(f"{a}-{b}" for a, b in base.electrode_pairs),
            ]
            if base.base_electrode_labels:
                lines.append(
                    "Base electrodes: " + ", ".join(base.base_electrode_labels)
                )
        except Exception as exc:
            lines = [f"Could not load base montage: {exc}"]
        if self.leadfield_combo.count() == 0:
            lines.append("No leadfield available yet for this subject.")
        self.summary.setPlainText("\n".join(lines))

    def _validate_against_base_montage(self, base, added_electrodes):
        base_labels = set(base.base_electrode_labels)
        if not base_labels:
            return
        overlap = sorted(set(added_electrodes) & base_labels)
        if overlap:
            raise ValueError(
                "The added carrier reuses electrodes from the base montage: "
                + ", ".join(overlap)
            )

    def _build_config(self):
        subject_id = self.subject_combo.currentText().strip()
        selected = self.base_montage_combo.currentData() or {}
        base_montage = selected.get("name") if isinstance(selected, dict) else self.base_montage_combo.currentText().strip()
        base_eeg_net = selected.get("eeg_net") if isinstance(selected, dict) else self._selected_eeg_net()
        leadfield_hdf = self.leadfield_combo.currentData()
        roi_name = self.roi_combo.currentText().strip()
        metric = self.metric_combo.currentData()

        if not subject_id:
            raise ValueError("Please select a subject.")
        if not base_montage:
            raise ValueError("Please select a base TI montage.")
        if not base_eeg_net:
            raise ValueError("Please select a leadfield/EEG net.")
        if not leadfield_hdf:
            raise ValueError("Please select a leadfield.")
        if not roi_name:
            raise ValueError("Please select an ROI.")

        base = load_base_montage(
            subject_id,
            base_montage,
            base_eeg_net,
            project_dir=self.pm.project_dir,
        )

        if self.rb_all_combinations.isChecked():
            electrodes = self.parse_electrode_input(self.electrode_pool_input.text())
            if len(electrodes) < 4:
                raise ValueError(
                    "Please enter at least 4 distinct electrodes for the added carrier pool."
                )
            if len(set(electrodes)) != len(electrodes):
                raise ValueError("The added carrier pool contains duplicate electrodes.")
            self._validate_against_base_montage(base, electrodes)
            electrode_spec = PoolElectrodes(electrodes=electrodes)
        else:
            e3_plus = self.parse_electrode_input(self.e3_plus_input.text())
            e3_minus = self.parse_electrode_input(self.e3_minus_input.text())
            e4_plus = self.parse_electrode_input(self.e4_plus_input.text())
            e4_minus = self.parse_electrode_input(self.e4_minus_input.text())
            if not all([e3_plus, e3_minus, e4_plus, e4_minus]):
                raise ValueError(
                    "Please enter at least one valid electrode in each bucketed category."
                )
            all_added = e3_plus + e3_minus + e4_plus + e4_minus
            if len(set(all_added)) != len(all_added):
                raise ValueError(
                    "Bucketed added-carrier inputs contain duplicate electrodes."
                )
            self._validate_against_base_montage(base, all_added)
            electrode_spec = BucketElectrodes(
                e1_plus=e3_plus,
                e1_minus=e3_minus,
                e2_plus=e4_plus,
                e2_minus=e4_minus,
            )

        return SecondaryExConfig(
            subject_id=subject_id,
            project_dir=self.pm.project_dir,
            base_montage=base_montage,
            base_eeg_net=base_eeg_net,
            leadfield_hdf=leadfield_hdf,
            roi_name=roi_name,
            metric=metric,
            electrodes=electrode_spec,
            current_mA=self.current_spin.value(),
            roi_radius=self.roi_radius_spin.value(),
            eeg_net=base_eeg_net,
        )

    def run_search(self):
        self.console.clear_console()
        try:
            config = self._build_config()
        except Exception as exc:
            self.console.update_console(str(exc), "error")
            return

        self.console.update_console("=== 2nd Ex-Search ===", "info")
        self.console.update_console(f"Subject: {config.subject_id}", "info")
        self.console.update_console(f"Base montage: {config.base_montage}", "info")
        self.console.update_console(f"Leadfield: {os.path.basename(config.leadfield_hdf)}", "info")
        self.console.update_console(f"ROI: {config.roi_name}", "info")
        self.console.update_console(f"Metric: {config.metric}", "info")
        self.console.update_console(
            f"Current per pair: {config.current_mA:.1f} mA",
            "info",
        )
        if isinstance(config.electrodes, PoolElectrodes):
            self.console.update_console(
                f"Added carrier pool size: {len(config.electrodes.electrodes)}", "info"
            )
        else:
            self.console.update_console(
                "Added carrier mode: bucketed inputs", "info"
            )

        self.run_btn.setEnabled(False)
        self.thread = SecondaryExSearchThread(config, self)
        self.thread.finished_signal.connect(self._on_finished)
        self.thread.start()

    def _on_finished(self, success, result, error_text):
        self.run_btn.setEnabled(True)
        if success:
            self.console.update_console(
                f"Secondary search finished. Tested {result.n_combinations} combinations.",
                "success",
            )
            self.console.update_console(f"Output: {result.output_dir}", "info")
            if result.results_csv:
                self.console.update_console(f"CSV: {result.results_csv}", "info")
            if result.best_composite_csv:
                self.console.update_console(
                    f"Best composite: {result.best_composite_csv}", "info"
                )
            if result.scatter_png:
                self.console.update_console(
                    f"Scatter plot: {result.scatter_png}", "info"
                )
            if result.montage_distribution_png:
                self.console.update_console(
                    f"Montage distribution: {result.montage_distribution_png}",
                    "info",
                )
        else:
            self.console.update_console(
                f"Secondary search failed: {error_text}",
                "error",
            )
