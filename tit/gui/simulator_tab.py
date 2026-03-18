#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Simulator Tab
This module provides a GUI interface for the simulator functionality.
"""

import logging
import os
import json
import re
import subprocess
import time
import datetime
import shutil

logger = logging.getLogger(__name__)

from PyQt5 import QtWidgets, QtCore
from tit.gui.confirmation_dialog import ConfirmationDialog
from tit.gui.components.console import (
    ConsoleWidget,
    format_message,
    append_with_autoscroll,
)
from tit.gui.components.action_buttons import RunStopButtons
from tit.gui.components.add_montage_dialog import AddMontageDialog
from tit.gui.components.conductivity_dialog import ConductivityEditorDialog
from tit.gui.utils import strip_ansi_codes, open_file, open_directory
from tit.gui.components.base_thread import BaseProcessThread
from tit.paths import get_path_manager
from tit.config_io import serialize_config
from tit.reporting import SimulationReportGenerator

from tit.sim import (
    SimulationConfig,
    Montage,
    parse_intensities,
)
from tit.sim.utils import (
    list_montage_names,
    load_montages,
    load_montage_data,
    save_montage_data,
    ensure_montage_file,
    upsert_montage,
)


class SimulationThread(BaseProcessThread):
    """Run tit.sim via subprocess, streaming output to the GUI."""

    def __init__(self, cmd, env=None):
        super().__init__(cmd=cmd, env=env)

    def run(self):
        self.execute_process()

    def terminate_simulation(self):
        self.terminate_process()


class SimulatorTab(QtWidgets.QWidget):
    """Tab for simulator functionality."""

    def __init__(self, parent=None):
        super(SimulatorTab, self).__init__(parent)
        self.parent = parent
        self.simulation_running = False
        self.sim_thread = None
        self.custom_conductivities = {}  # keys: int tissue number, values: float
        self.report_generator = None
        self.simulation_session_id = None
        self._had_errors_during_run = False
        self._simulation_finished_called = False
        self._current_run_subjects = []
        self._current_run_is_montage = True
        self._current_run_montages = []
        self._run_start_time = None
        self._project_dir_path_current = None
        # Per-job selection state
        self._job_selections = {}  # row_index -> list[str] of selected item texts
        self._job_cards: list = []
        self._selected_card_idx: int = -1
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
        self.jobs_layout.addStretch()  # keeps cards pushed to top
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
        self.thickness_label = QtWidgets.QLabel("Gel Thickness (mm):")
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

        # ── Assemble 2-column layout ───────────────────────────────────────
        # Right panel: Montage/Flex selection on top, Global Parameters below
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(selection_group, 1)  # stretch=1: takes remaining height
        right_layout.addWidget(global_group, 0)  # stretch=0: compact, natural height

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
            subjects = self.pm.list_simnibs_subjects()

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
            eeg_nets = [
                self.eeg_net_combo.itemText(i)
                for i in range(self.eeg_net_combo.count())
            ]
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

        except OSError as e:
            logger.error(f"Error loading subjects: {e}")

    def _get_available_subjects(self):
        """Return sorted list of available subject IDs."""
        try:
            return self.pm.list_simnibs_subjects()
        except OSError:
            return []

    # ── Job table management ────────────────────────────────────────────────

    def _add_job_row(
        self, subject=None, source="Montage", mode="U", currents="1.0,1.0", eeg_net=None
    ):
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
        """Reset selections and refresh montage list when U/M mode changes."""
        combo = self.sender()
        for i, card in enumerate(self._job_cards):
            if card.mode_combo is combo:
                ph = "1.0,1.0,1.0,1.0" if text == "M" else "1.0,1.0"
                card.current_edit.setPlaceholderText(ph)
                self._job_selections[i] = []
                self._update_count_cell(i)
                if i == self._selected_card_idx:
                    self._refresh_selection_list()
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
        source = (
            card.source_combo.currentText()
        )  # "Montage" | "Flex-Search" | "Freehand"
        self.selection_label.setText(f"Selecting for: {subject} / {source}")
        self._update_selection_panel_buttons(source=source)

        saved = set(self._job_selections.get(idx, []))

        self.selection_list.blockSignals(True)
        self.selection_list.clear()

        if source == "Montage":
            eeg_net = card.eeg_net_combo.currentText() or "GSN-HydroCel-185.csv"
            sim_mode = card.mode_combo.currentText()  # "U" or "M"
            montage_entries = self._get_montage_entries_for_params(eeg_net, sim_mode)
            for raw_name, pairs in montage_entries:
                display_text = self._format_montage_display(raw_name, pairs)
                list_item = QtWidgets.QListWidgetItem(display_text)
                list_item.setData(QtCore.Qt.UserRole, raw_name)
                self.selection_list.addItem(list_item)
                if raw_name in saved:
                    list_item.setSelected(True)
        else:
            if source == "Flex-Search":
                items = self._get_flex_outputs_for_subject(subject)
            elif source == "Freehand":
                items = self._get_freehand_configs_for_subject(subject)
            else:
                items = []
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
            item.data(QtCore.Qt.UserRole) or item.text()
            for item in self.selection_list.selectedItems()
        ]
        self._job_selections[idx] = selected_texts
        self._update_count_cell(idx)

    def _clear_selection(self):
        """Clear the selection in the selection list."""
        self.selection_list.clearSelection()
        self._save_selection_for_current_row()

    def _update_selection_panel_buttons(self, source):
        """Show/hide montage-specific buttons based on current source."""
        is_montage = source == "Montage"
        self.add_montage_sel_btn.setVisible(is_montage)
        self.remove_montage_sel_btn.setVisible(is_montage)

    # ── Data helpers ────────────────────────────────────────────────────────

    def _get_montage_names_for_params(self, eeg_net, sim_mode):
        """Return list of montage names for given EEG net and sim mode (U/M)."""
        try:
            project_dir = self.pm.project_dir
            if not project_dir:
                return []
            return list_montage_names(eeg_net, mode=sim_mode)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error getting montage names: {e}")
            return []

    def _get_montage_entries_for_params(self, eeg_net, sim_mode):
        """Return list of (name, pairs) tuples for montages matching the given EEG net and mode."""
        try:
            project_dir = self.pm.project_dir
            if not project_dir:
                return []
            montage_file = self.ensure_montage_file_exists()
            with open(montage_file, "r") as f:
                montage_data = json.load(f)
            net_type = (
                "uni_polar_montages" if sim_mode == "U" else "multi_polar_montages"
            )
            nets = montage_data.get("nets", {})
            if eeg_net not in nets:
                return []
            montages = nets[eeg_net].get(net_type, {})
            return [(name, pairs) for name, pairs in montages.items()]
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error getting montage entries: {e}")
            return []

    @staticmethod
    def _format_montage_display(name, pairs):
        """Format a montage name + electrode pairs as a display string.

        Example: "my_montage: ch1{E1,E2}, ch2{E3,E4}"
        """
        if not pairs:
            return name
        ch_parts = [f"ch{i + 1}{{{p[0]},{p[1]}}}" for i, p in enumerate(pairs)]
        return f"{name}: {', '.join(ch_parts)}"

    def _get_flex_outputs_for_subject(self, subject_id):
        """Return list of flex-search item strings for a subject (mapped + optimized).

        Reads flex_meta.json from each run folder for display labels.
        Falls back to folder name if manifest is missing.
        """
        from tit.opt.flex.manifest import read_manifest

        items = []
        try:
            run_names = self.pm.list_flex_search_runs(subject_id)
            for run_name in run_names:
                run_dir = self.pm.flex_search_run(subject_id, run_name)
                meta = read_manifest(run_dir)
                label = meta.get("label", run_name) if meta else run_name
                display = f"{run_name} | {label}"

                # [mapped] is always available
                items.append(f"{display} [mapped]")

                # [optimized] only if optimized_positions key is present
                positions_file = self.pm.flex_electrode_positions(subject_id, run_name)
                if positions_file and os.path.isfile(positions_file):
                    try:
                        with open(positions_file, "r") as f:
                            pos_data = json.load(f)
                        if pos_data.get("optimized_positions"):
                            items.append(f"{display} [optimized]")
                    except (OSError, json.JSONDecodeError):
                        pass
        except OSError as e:
            logger.error(f"Error getting flex outputs for {subject_id}: {e}")
        return items

    def _get_freehand_configs_for_subject(self, subject_id):
        """Return list of freehand config names for a subject."""
        items = []
        try:
            m2m_dir = self.pm.m2m(subject_id)
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
                    except (OSError, json.JSONDecodeError):
                        items.append(config_file.replace(".json", ""))
        except OSError as e:
            logger.error(f"Error getting freehand configs for {subject_id}: {e}")
        return items

    # ── Montage builders ──────────────────────────────────────────────

    def _build_montage_configs_for_row(
        self, subject, source, sim_mode, selected_items, eeg_net
    ):
        """Build list of Montage objects for a single job row."""
        configs = []
        if source == "montage":
            configs = self._build_montage_configs_from_names(
                selected_items, eeg_net, sim_mode
            )
        elif source == "flex-search":
            configs = self._build_montage_configs_from_flex(
                subject, selected_items, eeg_net
            )
        elif source == "freehand":
            configs = self._build_montage_configs_from_freehand(subject, selected_items)
        return configs

    def _build_montage_configs_from_names(self, montage_names, eeg_net, sim_mode):
        """Build Montage list from montage names."""
        try:
            project_dir = self.pm.project_dir
            return load_montages(
                montage_names, eeg_net, include_flex=False
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            self.update_output(f"Error building montage configs: {e}", "error")
            return []

    def _build_montage_configs_from_flex(self, subject_id, selected_items, eeg_net):
        """Build Montage list from flex-search selection items."""
        from tit.opt.flex.manifest import read_manifest

        configs = []
        for item_text in selected_items:
            try:
                # Extract run_name from "run_name | label [type]" format
                item_stripped = item_text.strip()
                if " [mapped]" in item_stripped:
                    electrode_type = "mapped"
                    name_part = item_stripped.replace(" [mapped]", "")
                elif " [optimized]" in item_stripped:
                    electrode_type = "optimized"
                    name_part = item_stripped.replace(" [optimized]", "")
                else:
                    electrode_type = "mapped"
                    name_part = item_stripped

                # Extract the run_name (before the " | " separator)
                if " | " in name_part:
                    search_name = name_part.split(" | ", 1)[0].strip()
                else:
                    search_name = name_part.strip()

                flex_search_dir = self.pm.flex_search_run(subject_id, search_name)
                if not flex_search_dir:
                    self.update_output(
                        f"Flex-search folder not found for {subject_id} | {search_name}",
                        "error",
                    )
                    continue

                positions_file = os.path.join(
                    flex_search_dir, "electrode_positions.json"
                )

                # Build montage name from manifest
                run_dir = self.pm.flex_search_run(subject_id, search_name)
                meta = read_manifest(run_dir)
                if meta:
                    goal = meta.get("goal", "opt")
                    postproc = meta.get("postproc", "maxTI")
                    montage_name = f"flex_{goal}_{postproc}_{electrode_type}"
                else:
                    montage_name = f"flex_{search_name}_{electrode_type}"

                if electrode_type == "mapped":
                    # Need to map to EEG cap
                    eeg_positions_dir = self.pm.eeg_positions(subject_id)
                    eeg_net_path = os.path.join(eeg_positions_dir or "", eeg_net)
                    if not eeg_positions_dir or not os.path.isfile(eeg_net_path):
                        self.update_output(
                            f"EEG net file not found: {eeg_net_path}", "error"
                        )
                        continue

                    # Run electrode mapping
                    mapping_file = os.path.join(
                        flex_search_dir,
                        f'electrode_mapping_{eeg_net.replace(".csv", "")}.json',
                    )
                    self.update_output(
                        f"Mapping electrodes for {subject_id} | {search_name} to {eeg_net}...",
                        "info",
                    )
                    try:
                        from tit.tools.map_electrodes import (
                            load_electrode_positions_json,
                            map_electrodes_to_net,
                            read_csv_positions,
                            save_mapping_result,
                        )

                        opt_pos, ch_arr_idx = load_electrode_positions_json(
                            positions_file
                        )
                        net_pos, net_labels = read_csv_positions(eeg_net_path)
                        result = map_electrodes_to_net(
                            opt_pos, net_pos, net_labels, ch_arr_idx
                        )
                        save_mapping_result(
                            result,
                            mapping_file,
                            eeg_net_name=os.path.basename(eeg_net_path),
                        )
                        self.update_output(
                            f"Electrode mapping completed for {search_name}", "info"
                        )
                    except Exception as e:
                        self.update_output(f"Error mapping electrodes: {e}", "error")
                        continue

                    if not os.path.exists(mapping_file):
                        self.update_output(
                            f"Mapping file was not created: {mapping_file}", "error"
                        )
                        continue

                    with open(mapping_file, "r") as f:
                        mapping_data = json.load(f)
                    mapped_labels = mapping_data.get("mapped_labels", [])
                    if len(mapped_labels) < 4:
                        self.update_output(
                            f"Not enough electrodes for TI in {search_name} (need >=4)",
                            "error",
                        )
                        continue

                    electrodes = mapped_labels[:4]
                    configs.append(
                        Montage(
                            name=montage_name,
                            mode=Montage.Mode.FLEX_MAPPED,
                            electrode_pairs=[
                                (electrodes[0], electrodes[1]),
                                (electrodes[2], electrodes[3]),
                            ],
                            eeg_net=eeg_net,
                        )
                    )

                else:  # optimized
                    with open(positions_file, "r") as f:
                        pos_data = json.load(f)
                    optimized_positions = pos_data.get("optimized_positions", [])
                    if len(optimized_positions) < 4:
                        self.update_output(
                            f"Not enough optimized electrodes in {search_name}",
                            "error",
                        )
                        continue
                    positions = optimized_positions[:4]
                    configs.append(
                        Montage(
                            name=montage_name,
                            mode=Montage.Mode.FLEX_FREE,
                            electrode_pairs=[
                                (positions[0], positions[1]),
                                (positions[2], positions[3]),
                            ],
                        )
                    )
            except (ValueError, IndexError, KeyError) as e:
                self.update_output(
                    f"Error processing flex item '{item_text}': {e}", "error"
                )
        return configs

    def _build_montage_configs_from_freehand(self, subject_id, selected_names):
        """Build Montage list from freehand config names."""
        configs = []
        try:
            m2m_dir = self.pm.m2m(subject_id)
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
                        config_name = config_data.get(
                            "name", config_file.replace(".json", "")
                        )
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
                            configs.append(
                                Montage(
                                    name=name,
                                    mode=Montage.Mode.FREEHAND,
                                    electrode_pairs=[
                                        (coords[0], coords[1]),
                                        (coords[2], coords[3]),
                                    ],
                                    eeg_net="freehand",
                                )
                            )
                        break
                    except (OSError, json.JSONDecodeError, KeyError) as e:
                        logger.error(
                            f"Error loading freehand config {config_file}: {e}"
                        )
        except OSError as e:
            self.update_output(f"Error building freehand configs: {e}", "error")
        return configs

    # ── Legacy compat stubs ─────────────────────────────────────────────────

    def ensure_montage_file_exists(self):
        """Ensure the montage file exists with proper structure."""
        return ensure_montage_file()

    def update_montage_list(self, checked=None):
        """Refresh the selection list (called after adding montage)."""
        self._refresh_selection_list()

    def run_simulation(self):
        """Run the simulation with the per-job table configuration."""
        try:
            # ── Collect jobs from table ────────────────────────────────────
            raw_jobs = (
                []
            )  # (subject_id, source, sim_mode, current_str, eeg_net, selected_items)
            for i, card in enumerate(self._job_cards):
                subject = card.subject_combo.currentText().strip()
                source = card.source_combo.currentText().lower()
                sim_mode = card.mode_combo.currentText()  # "U" or "M"
                row_eeg_net = card.eeg_net_combo.currentText() or "GSN-HydroCel-185.csv"
                selected = self._job_selections.get(i, [])
                if not selected:
                    continue
                raw = card.current_edit.text().strip() or (
                    "1.0,1.0,1.0,1.0" if sim_mode == "M" else "1.0,1.0"
                )
                current_str = raw
                raw_jobs.append(
                    (subject, source, sim_mode, current_str, row_eeg_net, selected)
                )

            if not raw_jobs:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "No jobs configured. Add rows with subjects and selected montages/configs.",
                )
                return

            # ── Read global params ─────────────────────────────────────────
            project_dir = self.pm.project_dir
            conductivity = self.sim_type_combo.currentData()
            electrode_shape = (
                "rect" if self.electrode_shape_rect.isChecked() else "ellipse"
            )
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
                    self,
                    "Warning",
                    "Please enter valid numeric values for dimensions and thickness.",
                )
                return

            # ── Build Montage objects for each job row ───────────────
            jobs = []  # (subject_id, Montage, current_str)
            for (
                subject,
                source,
                sim_mode,
                current_str,
                row_eeg_net,
                selected,
            ) in raw_jobs:
                montage_configs = self._build_montage_configs_for_row(
                    subject, source, sim_mode, selected, row_eeg_net
                )
                for mc in montage_configs:
                    jobs.append((subject, mc, current_str))

            if not jobs:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "No valid simulations could be prepared. Check your selections.",
                )
                return

            # ── Confirmation dialog ────────────────────────────────────────
            job_lines = []
            for subject, mc, current_str in jobs:
                job_lines.append(
                    f"  * {subject} | {mc.name} | {mc.eeg_net} | {current_str} mA"
                )
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
                simulations_dir = self.pm.simulations(subject_id)
                montage_dir = os.path.join(simulations_dir or "", mc.name)
                if simulations_dir and os.path.exists(montage_dir):
                    existing_dirs.append(f"{subject_id}/{mc.name}")

            if existing_dirs:
                existing_list = "\n".join([f"  * {d}" for d in existing_dirs[:10]])
                if len(existing_dirs) > 10:
                    existing_list += f"\n  ... and {len(existing_dirs) - 10} more"
                self.update_output(
                    "Simulation directories already exist:\n"
                    + existing_list
                    + "\n\nPlease delete them manually before re-running.",
                    "error",
                )
                return

            # ── Store run context ──────────────────────────────────────────
            unique_subjects = list(dict.fromkeys(s for s, _, _ in jobs))
            unique_montages = list(dict.fromkeys(mc.name for _, mc, _ in jobs))
            self._current_run_subjects = unique_subjects
            self._current_run_montages = unique_montages
            self._current_run_is_montage = True
            self._run_start_time = time.time()
            self._project_dir_path_current = project_dir

            # Store for report generation
            self._last_jobs = jobs[:]
            self._last_conductivity = conductivity
            self._last_electrode_shape = electrode_shape
            self._last_dimensions = dimensions
            self._last_thickness = thickness

            # ── Console summary ────────────────────────────────────────────
            total_simulations = len(jobs)
            self.update_output("--- SIMULATION CONFIGURATION ---")
            self.update_output(f"Total jobs: {total_simulations}")
            self.update_output(f"Subjects: {', '.join(unique_subjects)}")
            self.update_output(f"Anisotropy: {conductivity}")
            self.update_output(
                f"Electrode: {electrode_shape} ({dimensions} mm, {thickness} mm thick)"
            )

            # ── Report generator ───────────────────────────────────────────
            self.simulation_session_id = datetime.datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
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
                    intensity_ch2=(
                        float(current_parts[1]) if len(current_parts) > 1 else 1.0
                    ),
                    intensity_ch3=None,
                    intensity_ch4=None,
                    quiet_mode=False,
                    conductivities=self._get_conductivities_for_report(),
                )
                dim_p = dimensions.split(",")
                self.report_generator.add_electrode_parameters(
                    shape=electrode_shape,
                    dimensions=[float(dim_p[0]), float(dim_p[1])],
                    gel_thickness=float(thickness),
                )
                for subject_id in unique_subjects:
                    m2m_path = self.pm.m2m(subject_id)
                    self.report_generator.add_subject(
                        subject_id, m2m_path, "processing"
                    )

            # ── Enable stop button, disable controls ───────────────────────
            self.disable_controls()
            self.action_buttons.set_running(True)
            if self.parent:
                keep_enabled_widgets = [
                    self.console_widget.clear_btn,
                ]
                self.parent.set_tab_busy(
                    self,
                    True,
                    message="A simulation is running...",
                    stop_btn=self.stop_btn,
                    keep_enabled=keep_enabled_widgets,
                )

            self.simulation_running = True
            self._had_errors_during_run = False
            self._simulation_finished_called = False

            # ── Build SimulationConfig and Montage list ──────────────
            dim_parts2 = dimensions.split(",")
            electrode_dims = [float(dim_parts2[0]), float(dim_parts2[1])]

            # All jobs share the same config (intensities differ per job but run_simulation
            # accepts per-montage overrides; here we handle each unique subject+current
            # combination by grouping and launching one thread per unique (subject, current).
            # For simplicity (matching old one-job-at-a-time semantic), we run all jobs

            # Use the first job's subject_id/current for the top-level config;
            # each Montage carries its own eeg_net. run_simulation() accepts a
            # list of montages and iterates over them using config for shared params.
            first_subject, first_mc, first_current = jobs[0]
            montage_list = [mc for _, mc, _ in jobs]
            sim_config = SimulationConfig(
                subject_id=first_subject,
                montages=montage_list,
                conductivity=conductivity,
                intensities=parse_intensities(first_current),
                electrode_shape=electrode_shape,
                electrode_dimensions=electrode_dims,
                gel_thickness=float(thickness),
            )

            # ── Serialize config to JSON ──────────────────────────────────
            import tempfile

            config_data = serialize_config(sim_config)
            fd, config_path = tempfile.mkstemp(prefix="sim_", suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(config_data, f, indent=2)

            cmd = ["simnibs_python", "-m", "tit.sim", config_path]

            # ── Launch SimulationThread ─────────────────────────────────────
            self.sim_thread = SimulationThread(cmd)
            self.sim_thread.output_signal.connect(self._handle_thread_output)
            self.sim_thread.error_signal.connect(self._handle_process_error)
            self.sim_thread.finished.connect(self._on_simulation_done)
            self.sim_thread.start()

        except (OSError, ValueError, KeyError, RuntimeError) as e:
            self.update_output(f"Error starting simulation: {str(e)}", "error")
            import traceback

            self.update_output(traceback.format_exc(), "error")
            self.simulation_finished()

    def _handle_process_error(self, msg):
        """Handle error_signal from the subprocess (non-zero exit code)."""
        self._had_errors_during_run = True
        self.update_output(msg, "error")

    def _on_simulation_done(self):
        """Handle completion of the SimulationThread."""
        if not getattr(self, "simulation_running", False):
            return

        self.simulation_finished()

    def simulation_finished(self):
        """Handle simulation completion."""
        # Prevent double calling
        if self._simulation_finished_called:
            return

        self._simulation_finished_called = True

        # Only auto-generate simulation report if there were no errors
        if not self._had_errors_during_run:
            self.auto_generate_simulation_report()
        else:
            self.update_output(
                "[INFO] Skipping automatic report generation due to errors during simulation.",
                "warning",
            )
            try:
                self._cleanup_partial_outputs()
            except OSError as cleanup_exc:
                self.update_output(
                    f"[WARNING] Cleanup encountered an issue: {cleanup_exc}", "warning"
                )

        # Clean up temporary completion files
        self.cleanup_temporary_files()

        self.simulation_running = False

        # Reset button states using centralized method
        self.run_btn.setText("Run Simulation")
        self.action_buttons.set_running(False)

        # Clear parent tab's busy state (with stop_btn parameter for proper state management)
        if self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

        # Re-enable all controls
        self.enable_controls()

    def auto_generate_simulation_report(self):
        """Auto-generate individual simulation reports for each completed job."""
        try:
            project_dir = self.pm.project_dir
            conductivity = getattr(
                self, "_last_conductivity", self.sim_type_combo.currentData()
            )
            electrode_shape = getattr(self, "_last_electrode_shape", "ellipse")
            dimensions = getattr(self, "_last_dimensions", "8,8")
            thickness = getattr(self, "_last_thickness", "4")

            # Build subject->[(montage_name, current_str, eeg_net)] mapping from completed jobs
            last_jobs = getattr(self, "_last_jobs", [])
            subject_montage_map = (
                {}
            )  # subject_id -> [(montage_name, current_str, eeg_net)]
            for subject_id, mc, current_str in last_jobs:
                if subject_id not in subject_montage_map:
                    subject_montage_map[subject_id] = []
                subject_montage_map[subject_id].append(
                    (mc.name, current_str, mc.eeg_net)
                )

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
                        intensity_ch2 = (
                            float(cur_parts[1]) if len(cur_parts) > 1 else 1.0
                        )
                        job_eeg_net = eeg_net_map.get(
                            montage_name, "GSN-HydroCel-185.csv"
                        )
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
                            gel_thickness=float(thickness),
                        )

                        # Add this specific subject
                        bids_subject_id = f"sub-{subject_id}"
                        m2m_path = self.pm.m2m(subject_id)
                        report_generator.add_subject(subject_id, m2m_path, "completed")

                        # Add this specific montage
                        report_generator.add_montage(
                            montage_name=montage_name,
                            electrode_pairs=[["E1", "E2"]],  # Default pairs
                            montage_type="unipolar",
                        )

                        # Get expected output files for this specific combination
                        simulations_dir = self.pm.simulation(subject_id, montage_name)
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

                    except (OSError, ValueError, RuntimeError) as e:
                        self.update_output(
                            f"[ERROR] Error generating report for {subject_id}-{montage_name}: {str(e)}",
                            "error",
                        )

            if successful_reports > 0:
                reports_dir = self.pm.reports()
                self._open_directory_safely(reports_dir)

        except (OSError, ValueError, RuntimeError) as e:
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

    def clear_console(self):
        """Clear the output console."""
        self.output_console.clear()

    def stop_simulation(self):
        """Stop the running simulation."""
        # Mark as not running immediately to avoid triggering auto-abort logic from late output.
        self.simulation_running = False

        # Terminate the background simulation thread (hard stop)
        if self.sim_thread and self.sim_thread.isRunning():
            self.sim_thread.terminate_simulation()

        # Show stopping message
        self.update_output("Stopping simulation...")
        self.output_console.append(
            '<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">--- SIMULATION TERMINATED BY USER ---</span></div>'
        )

        # Reset UI state
        self.run_btn.setText("Run Simulation")
        self.action_buttons.set_running(False)
        if self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
        self.enable_controls()

    def validate_electrode(self, electrode):
        """Validate electrode name is not empty."""
        return bool(electrode and electrode.strip())

    def update_output(self, text, message_type="default"):
        """Update the console output with colored text, preserving original formatting."""
        if not text.strip():
            return

        # Strip ANSI escape sequences before any formatting
        text = strip_ansi_codes(text)

        # Preserve line breaks and spacing in the text by converting to HTML
        text_html = text.replace("\n", "<br>").replace(" ", "&nbsp;")

        # Use shared color mapping for known message types
        if message_type in ("error", "warning", "debug", "command", "success", "info"):
            formatted_text = format_message(text_html, message_type)
        else:
            # Fallback to content-based formatting for backward compatibility
            if "Processing... Only the Stop button is available" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #ffff55; font-weight: bold;">{text_html}</span></div>'
            elif text.strip().startswith("-"):
                formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">&nbsp;&nbsp;{text_html}</span>'
            else:
                formatted_text = format_message(text_html, "default")

        append_with_autoscroll(self.output_console, formatted_text)

    def _open_file_safely(self, file_path):
        """Safely open a file in the default application."""
        try:
            open_file(file_path)
            self.update_output("[INFO] File opened in default application")
        except OSError:
            self.update_output(
                f"[WARNING] File generated but couldn't open automatically: {file_path}"
            )

    def _open_directory_safely(self, dir_path):
        """Safely open a directory in the file manager."""
        try:
            open_directory(dir_path)
        except OSError:
            pass

    def _handle_thread_output(self, text, message_type="default"):
        """Forward subprocess output to the GUI console."""
        self.update_output(text, message_type)

    def _cleanup_partial_outputs(self):
        """Remove files/directories created during a failed simulation run."""
        for subject_id in self._current_run_subjects or []:
            sim_root = self.pm.simulations(subject_id)
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
            logs_dir = self.pm.logs(subject_id)
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

            # Persist montage via shared sim utils (reused by CLI + GUI)
            target_net = montage_data["target_net"]
            upsert_montage(
                eeg_net=target_net,
                montage_name=montage_data["name"],
                electrode_pairs=montage_data["electrode_pairs"],
                mode=("U" if montage_data["is_unipolar"] else "M"),
            )
            montage_file = ensure_montage_file()

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

            # Get the raw montage name (stored in UserRole to avoid formatted display text)
            montage_name = (
                selected_items[0].data(QtCore.Qt.UserRole) or selected_items[0].text()
            )
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

                # Get current net and mode from the active job card
                card_idx = self._selected_card_idx
                if card_idx >= 0 and card_idx < len(self._job_cards):
                    active_card = self._job_cards[card_idx]
                    current_net = active_card.eeg_net_combo.currentText()
                    mode_text = active_card.mode_combo.currentText()  # "U" or "M"
                else:
                    current_net = self.eeg_net_combo.currentText()
                    mode_text = "U"
                montage_type = (
                    "uni_polar_montages" if mode_text == "U" else "multi_polar_montages"
                )

                # Load, mutate, save via the shared API
                montage_data = load_montage_data()

                # Remove the montage if it exists
                if (
                    current_net in montage_data.get("nets", {})
                    and montage_type in montage_data["nets"][current_net]
                    and montage_name in montage_data["nets"][current_net][montage_type]
                ):
                    del montage_data["nets"][current_net][montage_type][montage_name]
                    save_montage_data(montage_data)

                    self.update_output(
                        f"Removed montage '{montage_name}' from {montage_type}"
                    )

                    # Refresh the selection list to reflect the change
                    self._refresh_selection_list()
                else:
                    QtWidgets.QMessageBox.warning(
                        self, "Warning", f"Montage '{montage_name}' not found."
                    )

        except (OSError, json.JSONDecodeError, KeyError) as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Error removing montage: {str(e)}"
            )
            logger.error(f"Detailed error: {str(e)}")

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
            derivatives_dir = self.pm.derivatives()
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
                                self.simulation_session_id
                                and self.simulation_session_id in filename
                            ):
                                os.remove(file_path)
                                cleaned_count += 1
                                self.update_output(
                                    f"[CLEANUP] Removed session file: {filename}"
                                )
                    except OSError as e:
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

        except OSError as e:
            self.update_output(f"[ERROR] Error during cleanup: {str(e)}", "warning")
