#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Analyzer Tab
This module provides a GUI interface for the analyzer functionality.
"""

import traceback
import time
import os
import json
import tempfile
import subprocess

from PyQt5 import QtWidgets, QtCore, QtGui

from tit.gui.confirmation_dialog import ConfirmationDialog
from tit.gui.utils import confirm_overwrite
from tit.gui.components.console import (
    ConsoleWidget,
    format_message,
    append_with_autoscroll,
)
from tit.gui.components.action_buttons import RunStopButtons
from tit.gui.components.base_thread import BaseProcessThread
from tit.atlas.constants import BUILTIN_ATLASES
from tit.paths import get_path_manager


class AnalysisThread(BaseProcessThread):
    """Thread to run analysis in background to prevent GUI freezing."""

    def __init__(self, cmd, env=None, cwd=None):
        super().__init__(cmd=cmd, env=env, cwd=cwd)

    def run(self):
        """Run the analysis command via BaseProcessThread.execute_process()."""
        self.execute_process()


class AnalyzerTab(QtWidgets.QWidget):
    """Tab for analyzer functionality."""

    analysis_completed = QtCore.pyqtSignal(str, str, str)

    @property
    def is_group_mode(self):
        """Determine if we're in group mode based on number of selected pairs."""
        if self.pairs_table:
            return self.pairs_table.rowCount() > 1
        return False

    def on_pairs_changed(self):
        """Handle changes to subject-simulation pairs - update UI accordingly."""
        # Guard: skip if UI is not fully initialized yet
        if not hasattr(self, "type_cortical"):
            return
        # Update coordinate space labels based on new mode
        self._update_coordinate_space_labels()
        # Update atlas visibility and options
        self.update_atlas_combo()
        if self.is_group_mode and self.type_cortical.isChecked():
            self.update_group_atlas_options()
        self.update_atlas_visibility()
        # Update gmsh subjects when pairs change
        self.update_gmsh_subjects()

    def __init__(self, parent=None):
        super(AnalyzerTab, self).__init__(parent)
        self.parent = parent
        self.analysis_running = False
        self.optimization_process = None

        self.group_atlas_config = {}

        # Initialize PathManager
        self.pm = get_path_manager()

        self.ANALYSIS_START_TIME = None
        self.STEP_START_TIMES = {}
        self._last_output_dir = None
        self._last_plain_output_line = None
        self._summary_printed = set()

        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface for the analyzer tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # Create analysis space radio buttons early so they are available for all widgets
        self.space_mesh = QtWidgets.QRadioButton("Mesh")
        self.space_voxel = QtWidgets.QRadioButton("Voxel")
        self.space_mesh.setChecked(True)
        self.space_group = QtWidgets.QButtonGroup(self)
        self.space_group.addButton(self.space_mesh)
        self.space_group.addButton(self.space_voxel)

        # Tissue type selector
        self.tissue_combo = QtWidgets.QComboBox()
        self.tissue_combo.addItem("Gray Matter (GM)", "GM")
        self.tissue_combo.addItem("White Matter (WM)", "WM")
        self.tissue_combo.addItem("GM + WM (both)", "both")

        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: white; color: #f44336; padding: 5px 10px;
                border-radius: 3px; font-weight: bold;
            }
        """)
        self.status_label.setAlignment(QtCore.Qt.AlignVCenter)
        self.status_label.hide()
        main_layout.addWidget(self.status_label)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)

        main_horizontal_layout = QtWidgets.QHBoxLayout()

        # Create left container (for subjects)
        left_container = QtWidgets.QWidget()
        left_container.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred
        )
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(5, 0, 5, 0)  # Match margins with right container
        left_layout.setSpacing(2)

        # Subject-simulation pairs selection (always shown)
        self.pairs_widget = self.create_pairs_widget()
        left_layout.addWidget(self.pairs_widget)

        # Add left container (subjects) to the layout first
        # Use stretch factor 1 for equal sizing
        main_horizontal_layout.addWidget(left_container, 1)

        # Create right container (for analysis configuration)
        self.right_layout_container = QtWidgets.QWidget()
        self.right_layout_container.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred
        )
        right_layout_actual = self.create_analysis_parameters_widget(
            self.right_layout_container
        )
        # Use stretch factor 1 for equal sizing with left container
        main_horizontal_layout.addWidget(self.right_layout_container, 1)

        # Set stretch factors explicitly to ensure equal sizing
        main_horizontal_layout.setStretchFactor(left_container, 1)
        main_horizontal_layout.setStretchFactor(self.right_layout_container, 1)

        # Store reference to scroll content for resize calculations
        self.scroll_content = scroll_content

        scroll_layout.addLayout(main_horizontal_layout)
        scroll_area.setWidget(scroll_content)

        # Initial call to set input widths after UI is created
        QtCore.QTimer.singleShot(100, self._update_input_widths)

        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(
            self, run_text="Run Analysis", stop_text="Stop Analysis"
        )
        self.action_buttons.connect_run(self.run_analysis)
        self.action_buttons.connect_stop(self.stop_analysis)

        # Keep references for backward compatibility
        self.run_btn = self.action_buttons.get_run_button()
        self.stop_btn = self.action_buttons.get_stop_button()

        # Console widget component with Run/Stop buttons integrated
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

        # Reference to underlying console for backward compatibility
        self.output_console = self.console_widget.get_console_widget()

        # Connect signals after all widgets are created

        # After all widgets are created, set field name visibility and connect toggles
        # This needs to be robust if widgets aren't found (e.g., during initial setup)
        if (
            hasattr(self, "field_name_label")
            and hasattr(self, "field_name_input")
            and hasattr(self, "space_mesh")
            and hasattr(self, "space_voxel")
        ):
            self.field_name_label.setVisible(self.space_mesh.isChecked())
            self.field_name_input.setVisible(self.space_mesh.isChecked())
            self.space_mesh.toggled.connect(
                lambda checked: (
                    self.field_name_label.setVisible(checked)
                    if hasattr(self, "field_name_label")
                    else None
                )
            )
            self.space_mesh.toggled.connect(
                lambda checked: (
                    self.field_name_input.setVisible(checked)
                    if hasattr(self, "field_name_input")
                    else None
                )
            )
            self.space_voxel.toggled.connect(
                lambda checked: (
                    self.field_name_label.setVisible(not checked)
                    if hasattr(self, "field_name_label")
                    else None
                )
            )
            self.space_voxel.toggled.connect(
                lambda checked: (
                    self.field_name_input.setVisible(not checked)
                    if hasattr(self, "field_name_input")
                    else None
                )
            )

    def _update_coordinate_space_labels(self):
        """Update coordinate space labels and tooltips based on space selection."""
        if hasattr(self, "coordinates_label") and hasattr(self, "coords_radius_input"):
            if self.coord_space_mni.isChecked():
                # MNI space selected
                self.coordinates_label.setText("MNI RAS (x,y,z,r):")
                self.coordinates_label.setToolTip(
                    "MNI space coordinates (will be transformed to subject space for each subject)"
                )
                self.coordinates_label.setStyleSheet(
                    "color: #007ACC; font-weight: bold;"
                )
                self.coords_radius_input.setToolTip("x,y,z,radius in MNI space")

                # Update Freeview button for MNI template
                if hasattr(self, "view_in_freeview_btn"):
                    self.view_in_freeview_btn.setText("View MNI Template")
                    self.view_in_freeview_btn.setToolTip(
                        "Open MNI152 template to find MNI coordinates"
                    )
            else:
                # Subject space selected
                self.coordinates_label.setText("Subject RAS (x,y,z,r):")
                self.coordinates_label.setToolTip("Subject-specific RAS coordinates")
                self.coordinates_label.setStyleSheet("")
                self.coords_radius_input.setToolTip("x,y,z,radius in subject RAS space")

                # Update Freeview button for subject T1
                if hasattr(self, "view_in_freeview_btn"):
                    self.view_in_freeview_btn.setText("View in Freeview")
                    self.view_in_freeview_btn.setToolTip(
                        "View T1 in Freeview to help find coordinates"
                    )

    def get_selected_subjects(self):
        """Get selected subjects from pairs table."""
        subjects = set()
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            if subject_combo:
                subject_id = subject_combo.currentText()
                if subject_id:
                    subjects.add(subject_id)
        return list(subjects)

    def on_subject_selection_changed(self):
        """Handle subject selection changes - update UI accordingly."""
        selected_subjects = self.get_selected_subjects()

        if self.is_group_mode:
            if not selected_subjects:
                # Clear configurations if no subjects selected
                self.group_atlas_config = {}
        else:
            # In single mode, update widgets
            self.update_atlas_combo()

        # Always recheck for valid atlases when subject selection changes
        self.update_atlas_combo()
        if self.is_group_mode and self.type_cortical.isChecked():
            self.update_group_atlas_options()

        self.update_atlas_visibility()

    def create_pairs_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Table for subject-simulation pairs
        pairs_group = QtWidgets.QGroupBox("Subject-Simulation Pairs")
        pairs_layout = QtWidgets.QVBoxLayout(pairs_group)

        self.pairs_table = QtWidgets.QTableWidget()
        self.pairs_table.setColumnCount(3)
        self.pairs_table.setHorizontalHeaderLabels(["Subject", "Simulation", ""])
        self.pairs_table.horizontalHeader().setStretchLastSection(False)
        self.pairs_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Fixed
        )
        self.pairs_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        self.pairs_table.setColumnWidth(0, 100)
        self.pairs_table.setColumnWidth(2, 50)
        self.pairs_table.setMinimumHeight(80)
        self.pairs_table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        pairs_layout.addWidget(self.pairs_table)

        # Buttons for managing pairs
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(5)

        self.add_pair_btn = QtWidgets.QPushButton("+ Add Pair")
        self.add_pair_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.add_pair_btn.clicked.connect(self.add_pair_row)
        buttons_layout.addWidget(self.add_pair_btn)

        self.quick_add_btn = QtWidgets.QPushButton("Quick Add")
        self.quick_add_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.quick_add_btn.setToolTip(
            "Add the same simulation to multiple subjects at once"
        )
        self.quick_add_btn.clicked.connect(self.quick_add_pairs)
        buttons_layout.addWidget(self.quick_add_btn)

        self.clear_pairs_btn = QtWidgets.QPushButton("Clear All")
        self.clear_pairs_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.clear_pairs_btn.clicked.connect(self.clear_all_pairs)
        buttons_layout.addWidget(self.clear_pairs_btn)

        self.refresh_pairs_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_pairs_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.refresh_pairs_btn.clicked.connect(self.refresh_pairs)
        buttons_layout.addWidget(self.refresh_pairs_btn)

        buttons_layout.addStretch()
        pairs_layout.addLayout(buttons_layout)
        layout.addWidget(pairs_group)

        # Add one empty row by default so the UI isn't completely empty
        self.add_pair_row()

        return widget

    def add_pair_row(self):
        """Add a new row for subject-simulation pair selection."""
        row = self.pairs_table.rowCount()
        self.pairs_table.insertRow(row)

        # Subject combo
        subject_combo = QtWidgets.QComboBox()
        subjects = self.pm.list_subjects()
        subject_combo.addItems(subjects)
        subject_combo.currentTextChanged.connect(
            lambda: self.update_sim_combo_in_row(row)
        )
        self.pairs_table.setCellWidget(row, 0, subject_combo)

        # Simulation combo
        sim_combo = QtWidgets.QComboBox()
        if subjects:
            sims = self.pm.list_simulations(subjects[0])
            sim_combo.addItems(sims)
        self.pairs_table.setCellWidget(row, 1, sim_combo)

        # Remove button
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setFixedWidth(32)
        remove_btn.clicked.connect(lambda: self.remove_pair(row))
        self.pairs_table.setCellWidget(row, 2, remove_btn)

        # Update UI after adding pair
        self.on_pairs_changed()

    def update_sim_combo_in_row(self, row):
        """Update the simulation combo box when subject changes in a row."""
        subject_combo = self.pairs_table.cellWidget(row, 0)
        sim_combo = self.pairs_table.cellWidget(row, 1)

        if subject_combo and sim_combo:
            subject_id = subject_combo.currentText()
            if subject_id:
                sims = self.pm.list_simulations(subject_id)
                sim_combo.clear()
                sim_combo.addItems(sims)

    def remove_pair(self, row):
        """Remove a subject-simulation pair row."""
        self.pairs_table.removeRow(row)
        self.on_pairs_changed()

    def clear_all_pairs(self):
        """Clear all subject-simulation pairs."""
        self.pairs_table.setRowCount(0)
        self.on_pairs_changed()

    def refresh_pairs(self):
        """Refresh all subject and simulation combos in the pairs table."""
        all_subjects = self.pm.list_subjects()
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)

            if subject_combo:
                current_subject = subject_combo.currentText()
                subject_combo.clear()
                subject_combo.addItems(all_subjects)
                if current_subject in all_subjects:
                    subject_combo.setCurrentText(current_subject)
                elif all_subjects:
                    subject_combo.setCurrentText(all_subjects[0])

            if sim_combo and subject_combo:
                subject_id = subject_combo.currentText()
                if subject_id:
                    sims = self.pm.list_simulations(subject_id)
                    current_sim = sim_combo.currentText()
                    sim_combo.clear()
                    sim_combo.addItems(sims)
                    if current_sim in sims:
                        sim_combo.setCurrentText(current_sim)

    def quick_add_pairs(self):
        """Open dialog to quickly add the same simulation to all subjects."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Quick Add Subject-Simulation Pairs")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Simulation selection
        sim_layout = QtWidgets.QHBoxLayout()
        sim_layout.addWidget(QtWidgets.QLabel("Simulation:"))
        sim_combo = QtWidgets.QComboBox()

        # Get all unique simulations across all subjects
        all_sims = set()
        all_subjects = self.pm.list_subjects()
        for subject in all_subjects:
            all_sims.update(self.pm.list_simulations(subject))
        sim_combo.addItems(sorted(all_sims))
        sim_layout.addWidget(sim_combo)
        layout.addLayout(sim_layout)

        # Info label
        info_label = QtWidgets.QLabel(
            "This will add the selected simulation for all subjects that have it."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-style: italic; padding: 10px;")
        layout.addWidget(info_label)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add All")
        cancel_btn = QtWidgets.QPushButton("Cancel")

        add_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addWidget(add_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_simulation = sim_combo.currentText()

            # Add pairs for all subjects that have this simulation
            added_count = 0
            skipped_count = 0
            for subject_id in all_subjects:
                # Check if this subject has the selected simulation
                available_sims = self.pm.list_simulations(subject_id)
                if selected_simulation not in available_sims:
                    continue

                # Check for duplicates
                duplicate = False
                for row in range(self.pairs_table.rowCount()):
                    existing_subject = self.pairs_table.cellWidget(row, 0).currentText()
                    existing_sim = self.pairs_table.cellWidget(row, 1).currentText()
                    if (
                        existing_subject == subject_id
                        and existing_sim == selected_simulation
                    ):
                        duplicate = True
                        break

                if duplicate:
                    skipped_count += 1
                    continue

                # Add new row
                row = self.pairs_table.rowCount()
                self.pairs_table.insertRow(row)

                # Subject combo
                subject_combo_widget = QtWidgets.QComboBox()
                subject_combo_widget.setMaxVisibleItems(
                    10
                )  # Show max 10 items before scrollbar appears
                subject_combo_widget.setStyleSheet(
                    "QComboBox { combobox-popup: 0; } QComboBox QAbstractItemView { max-height: 1000px; }"
                )
                subject_combo_widget.addItems(all_subjects)
                subject_combo_widget.setCurrentText(subject_id)
                subject_combo_widget.currentTextChanged.connect(
                    lambda: self.update_sim_combo_in_row(row)
                )
                self.pairs_table.setCellWidget(row, 0, subject_combo_widget)

                # Simulation combo
                sim_combo_widget = QtWidgets.QComboBox()
                sim_combo_widget.setMaxVisibleItems(
                    10
                )  # Show max 10 items before scrollbar appears
                sim_combo_widget.setStyleSheet(
                    "QComboBox { combobox-popup: 0; } QComboBox QAbstractItemView { max-height: 1000px; }"
                )
                sim_combo_widget.addItems(available_sims)
                sim_combo_widget.setCurrentText(selected_simulation)
                self.pairs_table.setCellWidget(row, 1, sim_combo_widget)

                # Remove button
                remove_btn = QtWidgets.QPushButton("✕")
                remove_btn.setFixedWidth(32)
                remove_btn.clicked.connect(lambda checked, r=row: self.remove_pair(r))
                self.pairs_table.setCellWidget(row, 2, remove_btn)

                added_count += 1

            message = f"\nAdded {added_count} subject-simulation pairs"
            if skipped_count > 0:
                message += f" ({skipped_count} skipped - already exist)"
            self.update_output(message)

            # Update UI after adding pairs
            self.on_pairs_changed()

    def create_analysis_parameters_widget(self, container_widget):
        right_layout = QtWidgets.QVBoxLayout(container_widget)
        right_layout.setContentsMargins(5, 0, 5, 0)  # Reduce side margins

        analysis_params_container = QtWidgets.QGroupBox("Analysis Configuration")
        self.analysis_params_container = analysis_params_container
        analysis_params_layout = QtWidgets.QVBoxLayout(analysis_params_container)
        analysis_params_layout.setSpacing(8)

        # Space selection row - distribute evenly across width
        space_layout = QtWidgets.QHBoxLayout()
        space_layout.setSpacing(10)
        self.space_label = QtWidgets.QLabel("Space:")
        self.space_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.space_mesh = QtWidgets.QRadioButton("Mesh")
        self.space_voxel = QtWidgets.QRadioButton("Voxel")
        self.space_mesh.setChecked(True)
        self.space_group = QtWidgets.QButtonGroup(self)
        self.space_group.addButton(self.space_mesh)
        self.space_group.addButton(self.space_voxel)

        space_layout.addWidget(self.space_label)
        space_layout.addWidget(self.space_mesh)
        space_layout.addWidget(self.space_voxel)
        space_layout.addStretch()  # Keep stretch to push radio buttons to left
        analysis_params_layout.addLayout(space_layout)

        # Tissue type row
        tissue_layout = QtWidgets.QHBoxLayout()
        tissue_layout.setSpacing(10)
        tissue_label = QtWidgets.QLabel("Tissue:")
        tissue_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        tissue_layout.addWidget(tissue_label)
        tissue_layout.addWidget(self.tissue_combo)
        tissue_layout.addStretch()
        analysis_params_layout.addLayout(tissue_layout)

        # Type selection row (separate from Space) - distribute evenly across width
        type_layout = QtWidgets.QHBoxLayout()
        type_layout.setSpacing(10)
        self.type_label = QtWidgets.QLabel("Type:")
        self.type_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.type_spherical = QtWidgets.QRadioButton("Spherical")
        self.type_cortical = QtWidgets.QRadioButton("Cortical")
        self.type_spherical.setChecked(True)
        self.type_group = QtWidgets.QButtonGroup(self)

        # Coordinate space radio buttons (for spherical analysis)
        self.coord_space_subject = QtWidgets.QRadioButton("Subject Space")
        self.coord_space_mni = QtWidgets.QRadioButton("MNI Space")
        self.coord_space_subject.setChecked(True)  # Default to subject space
        self.type_group.addButton(self.type_spherical)
        self.type_group.addButton(self.type_cortical)

        type_layout.addWidget(self.type_label)
        type_layout.addWidget(self.type_spherical)
        type_layout.addWidget(self.type_cortical)
        type_layout.addStretch()  # Keep stretch to push radio buttons to left
        analysis_params_layout.addLayout(type_layout)

        # (Removed) Analysis mode selection row (surface vs volumetric). Analyzer is surface-only.

        # Region, Atlas, and Spherical parameters - organized into multiple rows
        # Row 1: Region input line edit + Add button + List Regions button
        region_row = QtWidgets.QHBoxLayout()
        region_row.setSpacing(10)
        self.region_label = QtWidgets.QLabel("Region:")
        self.region_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.region_input = QtWidgets.QLineEdit()
        self.region_input.setPlaceholderText("e.g., superiorfrontal")
        self.region_input.setMinimumWidth(100)
        self.region_input.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )

        self.add_region_btn = QtWidgets.QPushButton("Add")
        self.add_region_btn.setToolTip("Add region to the list")
        self.add_region_btn.clicked.connect(self._add_region)
        self.add_region_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.region_input.returnPressed.connect(self._add_region)

        self.show_regions_btn = QtWidgets.QPushButton("List Regions")
        self.show_regions_btn.setToolTip("Show available regions in the selected atlas")
        self.show_regions_btn.clicked.connect(self.show_available_regions)
        self.show_regions_btn.setEnabled(False)
        self.show_regions_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )

        region_row.addWidget(self.region_label)
        region_row.addWidget(self.region_input)
        region_row.addSpacing(5)
        region_row.addWidget(self.add_region_btn)
        region_row.addSpacing(5)
        region_row.addWidget(self.show_regions_btn)
        region_row.addStretch()
        analysis_params_layout.addLayout(region_row)

        # Row 1b: Region list widget + Remove button
        region_list_row = QtWidgets.QHBoxLayout()
        region_list_row.setSpacing(10)
        self.region_list = QtWidgets.QListWidget()
        self.region_list.setMaximumHeight(80)
        self.region_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.region_list.setToolTip("Selected regions for combined ROI analysis")
        self.remove_region_btn = QtWidgets.QPushButton("Remove")
        self.remove_region_btn.setToolTip("Remove selected region from the list")
        self.remove_region_btn.clicked.connect(self._remove_region)
        self.remove_region_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        region_list_row.addWidget(self.region_list)
        region_list_row.addWidget(self.remove_region_btn)
        analysis_params_layout.addLayout(region_list_row)

        # Row 2: Atlas selection (single widget that shows mesh or voxel based on space)
        atlas_row = QtWidgets.QHBoxLayout()
        atlas_row.setSpacing(10)

        # Atlas widgets - always visible, just enabled/disabled
        self.mesh_atlas_widget = QtWidgets.QWidget()
        mesh_atlas_layout = QtWidgets.QHBoxLayout(self.mesh_atlas_widget)
        mesh_atlas_layout.setContentsMargins(0, 0, 0, 0)
        mesh_atlas_layout.setSpacing(5)
        self.mesh_atlas_label = QtWidgets.QLabel("Atlas:")
        self.mesh_atlas_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.atlas_name_combo = QtWidgets.QComboBox()
        self.atlas_name_combo.addItems(BUILTIN_ATLASES)
        self.atlas_name_combo.setCurrentText("DK40")
        self.atlas_name_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        mesh_atlas_layout.addWidget(self.mesh_atlas_label)
        mesh_atlas_layout.addWidget(self.atlas_name_combo)

        self.voxel_atlas_widget = QtWidgets.QWidget()
        voxel_atlas_vlayout = QtWidgets.QVBoxLayout(self.voxel_atlas_widget)
        voxel_atlas_vlayout.setContentsMargins(0, 0, 0, 0)
        voxel_atlas_vlayout.setSpacing(0)
        voxel_atlas_row = QtWidgets.QWidget()
        voxel_atlas_row_layout = QtWidgets.QHBoxLayout(voxel_atlas_row)
        voxel_atlas_row_layout.setContentsMargins(0, 0, 0, 0)
        voxel_atlas_row_layout.setSpacing(5)
        self.voxel_atlas_label = QtWidgets.QLabel("Atlas:")
        self.voxel_atlas_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.setEditable(False)
        self.atlas_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        voxel_atlas_row_layout.addWidget(self.voxel_atlas_label)
        voxel_atlas_row_layout.addWidget(self.atlas_combo)
        voxel_atlas_vlayout.addWidget(voxel_atlas_row)

        # Only add the appropriate atlas widget based on current space
        # Both will be in the layout, but only one enabled/visible at a time
        atlas_row.addWidget(self.mesh_atlas_widget)
        atlas_row.addWidget(self.voxel_atlas_widget)
        atlas_row.addStretch()
        analysis_params_layout.addLayout(atlas_row)

        # Spherical analysis parameters - split into separate rows

        # Row 2.5: Coordinate space selection (for spherical analysis)
        coord_space_row = QtWidgets.QHBoxLayout()
        coord_space_row.setSpacing(10)
        self.coord_space_label = QtWidgets.QLabel("Coordinate Space:")
        self.coord_space_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        coord_space_row.addWidget(self.coord_space_label)
        coord_space_row.addWidget(self.coord_space_subject)
        coord_space_row.addWidget(self.coord_space_mni)
        coord_space_row.addStretch()
        analysis_params_layout.addLayout(coord_space_row)

        # Row 3: Coordinates & Radius (single input: x,y,z,r)
        coords_row = QtWidgets.QHBoxLayout()
        coords_row.setSpacing(10)
        self.coordinates_label = QtWidgets.QLabel("Coordinates (x,y,z,r):")
        self.coordinates_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.coords_radius_input = QtWidgets.QLineEdit()
        self.coords_radius_input.setPlaceholderText("x,y,z,r")
        self.coords_radius_input.setMinimumWidth(180)
        self.coords_radius_input.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
        )
        coords_row.addWidget(self.coordinates_label)
        coords_row.addWidget(self.coords_radius_input)

        self.view_in_freeview_btn = QtWidgets.QPushButton("View in Freeview")
        self.view_in_freeview_btn.setToolTip(
            "View T1 in Freeview to help find coordinates"
        )
        self.view_in_freeview_btn.clicked.connect(self.load_t1_in_freeview)
        self.view_in_freeview_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        coords_row.addSpacing(10)
        coords_row.addWidget(self.view_in_freeview_btn)
        coords_row.addStretch()
        analysis_params_layout.addLayout(coords_row)

        # Remove the stacked widget approach - coordinates/radius are always visible
        # Instead, we'll enable/disable them based on mode

        # Original connections from setup_ui for space/type changes
        self.space_mesh.toggled.connect(self.update_atlas_visibility)
        self.space_voxel.toggled.connect(self.update_atlas_visibility)
        self.type_spherical.toggled.connect(self.update_atlas_visibility)
        self.type_cortical.toggled.connect(self.update_atlas_visibility)

        # Connect signals to update cortical button text based on space
        self.space_mesh.toggled.connect(self.update_cortical_button_text)
        self.space_voxel.toggled.connect(self.update_cortical_button_text)

        # (Removed) Analysis mode defaults (surface vs volumetric). Analyzer is surface-only.

        # Connect coordinate space radio buttons
        self.coord_space_subject.toggled.connect(self._update_coordinate_space_labels)
        self.coord_space_mni.toggled.connect(self._update_coordinate_space_labels)

        self.update_atlas_visibility()  # Initial call
        self.update_cortical_button_text()  # Initial call
        analysis_params_container.setFixedHeight(250)
        right_layout.addWidget(analysis_params_container)

        # Compact Gmsh visualization - using space more efficiently
        visualization_container = QtWidgets.QGroupBox("Gmsh Visualization")
        visualization_layout = QtWidgets.QVBoxLayout(visualization_container)
        visualization_layout.setSpacing(8)

        # Top row: Subject and Simulation - evenly distribute space
        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(10)
        subject_label = QtWidgets.QLabel("Subject:")
        subject_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        top_row.addWidget(subject_label)
        self.gmsh_subject_combo = QtWidgets.QComboBox()
        self.gmsh_subject_combo.setMaxVisibleItems(
            10
        )  # Show max 10 items before scrollbar appears
        self.gmsh_subject_combo.setStyleSheet(
            "QComboBox { combobox-popup: 0; } QComboBox QAbstractItemView { max-height: 1000px; }"
        )
        self.gmsh_subject_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        top_row.addWidget(self.gmsh_subject_combo)
        top_row.addSpacing(15)
        simulation_label = QtWidgets.QLabel("Simulation:")
        simulation_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        top_row.addWidget(simulation_label)
        self.gmsh_sim_combo = QtWidgets.QComboBox()
        self.gmsh_sim_combo.setMaxVisibleItems(
            10
        )  # Show max 10 items before scrollbar appears
        self.gmsh_sim_combo.setStyleSheet(
            "QComboBox { combobox-popup: 0; } QComboBox QAbstractItemView { max-height: 1000px; }"
        )
        self.gmsh_sim_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        top_row.addWidget(self.gmsh_sim_combo)
        visualization_layout.addLayout(top_row)

        # Bottom row: Analysis and Launch button - evenly distribute space
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setSpacing(10)
        analysis_label = QtWidgets.QLabel("Analysis:")
        analysis_label.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        bottom_row.addWidget(analysis_label)
        self.gmsh_analysis_combo = QtWidgets.QComboBox()
        self.gmsh_analysis_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        bottom_row.addWidget(self.gmsh_analysis_combo)
        bottom_row.addSpacing(15)
        self.launch_gmsh_btn = QtWidgets.QPushButton("Launch Gmsh")
        self.launch_gmsh_btn.clicked.connect(self.launch_gmsh_simple)
        self.launch_gmsh_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        bottom_row.addWidget(self.launch_gmsh_btn)
        bottom_row.addStretch()
        visualization_layout.addLayout(bottom_row)

        visualization_container.setFixedHeight(100)
        right_layout.addWidget(visualization_container)

        # Connect gmsh dropdown signals after widgets are created
        self.gmsh_subject_combo.currentTextChanged.connect(self.update_gmsh_simulations)
        self.gmsh_sim_combo.currentTextChanged.connect(self.update_gmsh_analyses)

        # Initial update for gmsh
        self.update_gmsh_subjects()

        return right_layout

    def get_available_atlas_files(self, subject_id):
        """Discover available voxel atlas files for a subject."""
        if not subject_id:
            return []

        from tit.atlas import VoxelAtlasManager

        mgr = VoxelAtlasManager(
            freesurfer_mri_dir=self.pm.freesurfer_mri(subject_id),
            seg_dir=self.pm.segmentation(subject_id),
        )
        results = mgr.list_atlases()
        if not results:
            return ["FreeSurfer recon-all preprocessing required for atlas generation"]
        return results

    def update_atlas_combo(self):
        if self.is_group_mode:
            return
        if not hasattr(self, "atlas_combo"):
            return

        self.atlas_combo.clear()

        # --- Add or show warning label above atlas_combo ---
        if not hasattr(self, "atlas_warning_label"):
            self.atlas_warning_label = QtWidgets.QLabel()
            self.atlas_warning_label.setStyleSheet("color: #c62828; font-weight: bold;")
            self.atlas_warning_label.setWordWrap(True)
            self.atlas_warning_label.setVisible(False)
            self.atlas_warning_label.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Ignored
            )
            # Insert above the atlas_combo in the layout
            if hasattr(self, "voxel_atlas_widget"):
                self.voxel_atlas_widget.layout().insertWidget(
                    0, self.atlas_warning_label
                )

        # Handle mesh atlas combo for single mode
        if self.space_mesh.isChecked() and self.type_cortical.isChecked():
            # Ensure mesh atlas combo is populated with predefined atlases
            if self.atlas_name_combo.count() == 0:
                self.atlas_name_combo.addItems(BUILTIN_ATLASES)
                self.atlas_name_combo.setCurrentText("DK40")
            self.atlas_name_combo.setEnabled(True)

        # Get selected subject from appropriate widget based on mode
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            self.atlas_combo.addItem("Select a subject first")
            self.atlas_combo.setEnabled(False)
            self.atlas_warning_label.setText(
                "<i>*Please run FreeSurfer recon-all in the Preprocessing tab to enable voxel cortical analysis.*</i>"
            )
            self.atlas_warning_label.setVisible(True)
            # Update all related controls
            self.update_atlas_dependent_controls(
                has_valid_atlas=False, requires_atlas=False
            )
            return

        subject_id = selected_subjects[0]  # Short ID
        atlas_files_data = self.get_available_atlas_files(subject_id)
        has_valid_atlas = False

        # Check if we're in a mode that requires atlases (voxel + cortical)
        requires_atlas = self.space_voxel.isChecked() and self.type_cortical.isChecked()

        # Determine if we have valid atlas data
        if atlas_files_data and isinstance(atlas_files_data[0], tuple):
            # We have valid atlas tuples
            has_valid_atlas = True
            for item in atlas_files_data:
                if isinstance(item, tuple) and len(item) == 2:
                    display_name, full_path = item
                    self.atlas_combo.addItem(display_name, full_path)
            if self.atlas_combo.count() > 0:
                self.atlas_combo.setCurrentIndex(0)
        else:
            # No valid atlases found
            if atlas_files_data and isinstance(atlas_files_data[0], str):
                # Warning message from get_available_atlas_files
                self.atlas_combo.addItem(atlas_files_data[0])
            else:
                # No atlas files at all
                self.atlas_combo.addItem("No atlases found")

        # Determine if the combo should be enabled
        should_enable_combo = False

        if requires_atlas:
            # In voxel + cortical mode, only enable if we have valid atlases
            should_enable_combo = has_valid_atlas
        else:
            # In other modes (mesh cortical, spherical), atlas combo is not needed
            should_enable_combo = False

        # Set the combo state
        self.atlas_combo.setEnabled(should_enable_combo)

        # Update warning label visibility
        if requires_atlas and not has_valid_atlas:
            self.atlas_warning_label.setText(
                "<i>*Please run FreeSurfer recon-all in the Preprocessing tab to enable voxel cortical analysis.*</i>"
            )
            self.atlas_warning_label.setVisible(True)
        else:
            self.atlas_warning_label.setVisible(False)

        # Update all related controls using centralized method
        self.update_atlas_dependent_controls(
            has_valid_atlas=has_valid_atlas, requires_atlas=requires_atlas
        )

    def update_atlas_dependent_controls(
        self, has_valid_atlas=False, requires_atlas=False
    ):
        """
        Centralized method to update all atlas-dependent UI controls.

        Args:
            has_valid_atlas (bool): Whether valid atlas data is available
            requires_atlas (bool): Whether the current mode requires atlas data
        """
        is_mesh = self.space_mesh.isChecked()
        is_cortical = self.type_cortical.isChecked()
        is_voxel_cortical = not is_mesh and is_cortical

        # Determine if we should enable cortical analysis controls
        # For mesh cortical: always enable (atlases are predefined)
        # For voxel cortical: only enable if we have valid atlases
        # For spherical: disable (no atlas needed)
        cortical_controls_enabled = False

        if is_cortical:
            if is_mesh:
                # Mesh cortical: always enable (uses predefined atlases)
                cortical_controls_enabled = True
            else:
                # Voxel cortical: only enable if we have valid atlases
                cortical_controls_enabled = has_valid_atlas and requires_atlas

        # Update region input controls
        # Should be enabled for cortical analysis, but only if atlas controls are enabled
        region_enabled = cortical_controls_enabled
        self.region_label.setEnabled(region_enabled)
        self.region_input.setEnabled(region_enabled)
        self.region_list.setEnabled(region_enabled)
        self.add_region_btn.setEnabled(region_enabled)
        self.remove_region_btn.setEnabled(region_enabled)

        # Update show regions button
        # Should be enabled for cortical analysis, but only if we have valid atlases
        can_list_regions = cortical_controls_enabled
        self.show_regions_btn.setEnabled(can_list_regions)

    def browse_atlas(self):
        initial_dir = ""
        selected_subjects = self.get_selected_subjects()
        if selected_subjects:
            subject_id = selected_subjects[0]
            m2m_dir_path = self.pm.m2m(subject_id)
            if m2m_dir_path and os.path.isdir(m2m_dir_path):  # Check existence
                initial_dir = os.path.join(m2m_dir_path, "segmentation")

        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Atlas File",
            initial_dir,
            "Atlas Files (*.nii *.nii.gz *.mgz);;All Files (*)",
        )

        if file_name:
            base_name = os.path.basename(file_name)
            existing_index = -1
            for i in range(self.atlas_combo.count()):
                if self.atlas_combo.itemData(i) == file_name:  # Check by path
                    existing_index = i
                    break
            if existing_index != -1:
                self.atlas_combo.setCurrentIndex(existing_index)
            else:
                self.atlas_combo.addItem(base_name, file_name)
                self.atlas_combo.setCurrentIndex(self.atlas_combo.count() - 1)

            # Since we now have a valid atlas, enable the combo and related controls
            if self.space_voxel.isChecked() and self.type_cortical.isChecked():
                self.atlas_combo.setEnabled(True)
                # Hide warning label if it was showing
                if hasattr(self, "atlas_warning_label"):
                    self.atlas_warning_label.setVisible(False)
                # Update all related controls using centralized method
                self.update_atlas_dependent_controls(
                    has_valid_atlas=True, requires_atlas=True
                )

            # Update button state after selection/addition
            can_list_regions = (
                self.atlas_combo.isEnabled() and self.type_cortical.isChecked()
            )
            self.show_regions_btn.setEnabled(can_list_regions)

    def update_atlas_visibility(self):
        is_mesh = self.space_mesh.isChecked()
        is_cortical = self.type_cortical.isChecked()
        is_spherical = self.type_spherical.isChecked()

        # Tissue selection only applies to voxel space
        self.tissue_combo.setEnabled(not is_mesh)
        if is_mesh:
            self.tissue_combo.setCurrentIndex(0)  # Force GM

        # Hide warning label in group mode - it should never show in group mode
        if self.is_group_mode and hasattr(self, "atlas_warning_label"):
            self.atlas_warning_label.setVisible(False)

        # Atlas widgets - show only the relevant one based on space, enabled when cortical
        mesh_atlas_visible = is_mesh
        voxel_atlas_visible = not is_mesh
        mesh_atlas_enabled = is_mesh and is_cortical
        voxel_atlas_enabled = not is_mesh and is_cortical

        # Show only the relevant atlas widget based on space selection
        self.mesh_atlas_widget.setVisible(mesh_atlas_visible)
        self.voxel_atlas_widget.setVisible(voxel_atlas_visible)

        # Enable only when both space matches and cortical mode is selected
        self.mesh_atlas_widget.setEnabled(mesh_atlas_enabled)
        self.voxel_atlas_widget.setEnabled(voxel_atlas_enabled)

        # For the atlas combos specifically
        if mesh_atlas_enabled:
            self.atlas_name_combo.setEnabled(True)
            # Ensure mesh atlas combo is populated with predefined atlases in single mode
            if not self.is_group_mode and self.atlas_name_combo.count() == 0:
                self.atlas_name_combo.addItems(BUILTIN_ATLASES)
                self.atlas_name_combo.setCurrentText("DK40")

        # For voxel atlas combo, let update_atlas_combo handle the enable state
        # based on actual atlas availability
        if voxel_atlas_enabled and not self.is_group_mode:
            # update_atlas_combo will handle the enable state properly
            pass
        elif voxel_atlas_enabled and self.is_group_mode:
            # For group mode, enable if we have any items
            self.atlas_combo.setEnabled(self.atlas_combo.count() > 0)

        # Coordinates and radius are always visible, enabled only in spherical mode
        coordinates_enabled = is_spherical
        if hasattr(self, "coordinates_label"):
            self.coordinates_label.setEnabled(coordinates_enabled)
        if hasattr(self, "coords_radius_input"):
            self.coords_radius_input.setEnabled(coordinates_enabled)
        if hasattr(self, "view_in_freeview_btn"):
            self.view_in_freeview_btn.setEnabled(coordinates_enabled)

        # Coordinate space selection disabled (not hidden) for non-spherical
        if hasattr(self, "coord_space_subject"):
            self.coord_space_subject.setEnabled(coordinates_enabled)
            self.coord_space_mni.setEnabled(coordinates_enabled)
        if hasattr(self, "coord_space_label"):
            self.coord_space_label.setEnabled(coordinates_enabled)

        self.mesh_atlas_widget.update()
        self.voxel_atlas_widget.update()

        # Update atlas options and related controls
        if self.is_group_mode and is_cortical:
            self.update_group_atlas_options()
        elif not self.is_group_mode:  # Ensure single mode atlas combo is also updated
            # Let update_atlas_combo handle the enable state properly
            self.update_atlas_combo()
        else:
            # For non-cortical modes or when not in group mode, update controls directly
            self.update_atlas_dependent_controls(
                has_valid_atlas=False, requires_atlas=False
            )

    def update_cortical_button_text(self):
        """Update the cortical radio button text based on the selected analysis space."""
        if self.space_voxel.isChecked():
            self.type_cortical.setText("Sub/Cortical")
        else:
            self.type_cortical.setText("Cortical")

    # (Removed) update_analysis_mode_defaults (surface vs volumetric). Analyzer is surface-only.

    def update_group_atlas_options(self):
        if not self.is_group_mode:
            return
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            # Don't disable everything if no subjects - user might be in process of selecting
            return

        # Store current states
        mesh_atlas_was_enabled = self.atlas_name_combo.isEnabled()
        voxel_atlas_was_enabled = self.atlas_combo.isEnabled()

        self.atlas_name_combo.clear()  # For mesh
        self.atlas_combo.clear()  # For voxel (this was for single mode, repurposing for group shared voxel if needed)

        has_valid_atlas = False
        requires_atlas = self.space_voxel.isChecked() and self.type_cortical.isChecked()

        if self.space_mesh.isChecked() and self.type_cortical.isChecked():
            self.atlas_name_combo.addItems(BUILTIN_ATLASES)  # Predefined mesh atlases
            self.atlas_name_combo.setCurrentText("DK40")
            self.atlas_name_combo.setEnabled(True)  # Always enable for mesh
            has_valid_atlas = True  # Mesh atlases are always available
            try:
                self.atlas_name_combo.currentTextChanged.disconnect(
                    self.update_group_mesh_atlas
                )
            except TypeError:
                # Signal may not be connected - this is expected
                pass
            self.atlas_name_combo.currentTextChanged.connect(
                self.update_group_mesh_atlas
            )
            self.update_group_mesh_atlas(
                self.atlas_name_combo.currentText()
            )  # Initial update
        elif self.space_voxel.isChecked() and self.type_cortical.isChecked():
            # Get atlases for first subject to start with
            available_atlases_for_first_subject = self.get_available_atlas_files(
                selected_subjects[0]
            )
            common_atlases_display = []

            # If first subject has valid atlases, check against other subjects
            if (
                isinstance(available_atlases_for_first_subject, list)
                and available_atlases_for_first_subject
                and isinstance(available_atlases_for_first_subject[0], tuple)
            ):

                # Start with first subject's atlases
                first_subject_atlases = {
                    disp_name: path_val
                    for disp_name, path_val in available_atlases_for_first_subject
                }

                # Check each subsequent subject
                for subject_id in selected_subjects[1:]:
                    subject_atlases = self.get_available_atlas_files(subject_id)
                    if (
                        not isinstance(subject_atlases, list)
                        or not subject_atlases
                        or not isinstance(subject_atlases[0], tuple)
                    ):
                        # If any subject has no valid atlases, clear common atlases
                        first_subject_atlases = {}
                        break

                    # Keep only atlases that exist in both subjects
                    subject_atlas_names = {
                        disp_name for disp_name, _ in subject_atlases
                    }
                    first_subject_atlases = {
                        name: path
                        for name, path in first_subject_atlases.items()
                        if name in subject_atlas_names
                    }

                # Add common atlases to combo
                for disp_name, path_val in first_subject_atlases.items():
                    self.atlas_combo.addItem(disp_name, path_val)
                    common_atlases_display.append(disp_name)

            if common_atlases_display:
                self.atlas_combo.setCurrentIndex(0)
                self.atlas_combo.setEnabled(True)
                has_valid_atlas = True
                try:
                    self.atlas_combo.currentTextChanged.disconnect(
                        self.update_group_voxel_atlas
                    )
                except TypeError:
                    # Signal may not be connected - this is expected
                    pass
                self.atlas_combo.currentTextChanged.connect(
                    self.update_group_voxel_atlas
                )
                self.update_group_voxel_atlas(
                    self.atlas_combo.currentText()
                )  # Initial update
            else:
                # No common atlas: show only the message, disable all controls, and hide warning label
                self.atlas_combo.clear()
                self.atlas_combo.addItem("No common atlases for all selected subjects")
                self.atlas_combo.setEnabled(False)
                has_valid_atlas = False
                self.group_atlas_config.clear()  # Clear all atlas configs since we have no common atlas
                # Hide the warning label if present
                if hasattr(self, "atlas_warning_label"):
                    self.atlas_warning_label.setVisible(False)
                # Disable all region/atlas controls
                self.region_label.setEnabled(False)
                self.region_input.setEnabled(False)
                self.region_list.setEnabled(False)
                self.add_region_btn.setEnabled(False)
                self.remove_region_btn.setEnabled(False)
                self.show_regions_btn.setEnabled(False)
                return  # Skip the centralized update, as we've set everything explicitly

        # Update all related controls using centralized method
        self.update_atlas_dependent_controls(
            has_valid_atlas=has_valid_atlas, requires_atlas=requires_atlas
        )

    def update_group_mesh_atlas(self, atlas_name):
        if (
            not self.is_group_mode
            or not self.space_mesh.isChecked()
            or not self.type_cortical.isChecked()
        ):
            return

        selected_subjects = self.get_selected_subjects()
        for subject_id in selected_subjects:
            # For mesh, atlas name is sufficient, path is not needed from subject's dir for SimNIBS subject_atlas
            self.group_atlas_config[subject_id] = {
                "name": atlas_name,
                "path": None,
                "type": "mesh",
            }

    def update_group_voxel_atlas(self, atlas_display_name_from_shared_combo):
        if (
            not self.is_group_mode
            or not self.space_voxel.isChecked()
            or not self.type_cortical.isChecked()
        ):
            return

        selected_subjects = self.get_selected_subjects()

        # The shared_combo's currentData() gives the path for the *first subject* or a representative.
        # We need to find the equivalent path for *each* subject.

        for subject_id in selected_subjects:
            subject_specific_atlases = self.get_available_atlas_files(subject_id)
            found_path_for_this_subject = None

            # Check if subject_specific_atlases is a list of tuples (valid atlases)
            if (
                isinstance(subject_specific_atlases, list)
                and subject_specific_atlases
                and isinstance(subject_specific_atlases[0], tuple)
            ):
                for disp_name, subj_path in subject_specific_atlases:
                    # We match by display name, assuming they are consistent (e.g., "DKT Atlas + Aseg")
                    if disp_name == atlas_display_name_from_shared_combo:
                        found_path_for_this_subject = subj_path
                        break

            if found_path_for_this_subject:
                self.group_atlas_config[subject_id] = {
                    "name": atlas_display_name_from_shared_combo,  # Store the display name
                    "path": found_path_for_this_subject,  # Store subject-specific path
                    "type": "voxel",
                }
            else:
                self.group_atlas_config.pop(
                    subject_id, None
                )  # Atlas not found for this subject

    def toggle_region_input(self, state_int):
        is_checked = bool(state_int)
        # The centralized method will handle all the enable/disable logic
        # Just call update_atlas_visibility which will trigger the proper state updates
        self.update_atlas_visibility()

    def validate_inputs(self):
        if self.is_group_mode:
            return self.validate_group_inputs()
        else:
            return self.validate_single_inputs()

    def validate_single_inputs(self):
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            QtWidgets.QMessageBox.warning(
                self, "Warning", "Please select at least one subject-simulation pair."
            )
            return False
        if self.pairs_table.rowCount() != 1:
            # For group mode, validate that all pairs have subjects and simulations
            for row in range(self.pairs_table.rowCount()):
                subject_combo = self.pairs_table.cellWidget(row, 0)
                sim_combo = self.pairs_table.cellWidget(row, 1)
                if not subject_combo or not sim_combo:
                    QtWidgets.QMessageBox.warning(
                        self, "Warning", "Please complete all subject-simulation pairs."
                    )
                    return False
                if not subject_combo.currentText() or not sim_combo.currentText():
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Warning",
                        "Please select both subject and simulation for all pairs.",
                    )
                    return False
        else:
            # For single mode, check the single pair
            subject_combo = self.pairs_table.cellWidget(0, 0)
            sim_combo = self.pairs_table.cellWidget(0, 1)
            if (
                not subject_combo
                or not sim_combo
                or not subject_combo.currentText()
                or not sim_combo.currentText()
            ):
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "Please select both subject and simulation."
                )
                return False
        return self.validate_analysis_parameters()

    def validate_group_inputs(self):
        # Check that we have at least one subject-simulation pair
        if self.pairs_table.rowCount() == 0:
            QtWidgets.QMessageBox.warning(
                self,
                "Warning",
                "Please add at least one subject-simulation pair for group analysis.",
            )
            return False

        # Validate each pair in the table
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)

            if subject_combo and sim_combo:
                subject_id = subject_combo.currentText()
                simulation_name = sim_combo.currentText()

                if not subject_id or not simulation_name:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Warning",
                        f"Please complete the subject-simulation pair in row {row + 1}.",
                    )
                    return False
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    f"Invalid subject-simulation pair in row {row + 1}.",
                )
                return False

        # Group analysis now supports both spherical (with MNI coordinates) and cortical analysis
        # No restriction needed

        # Atlas validation for cortical analysis
        if self.space_mesh.isChecked():
            # Mesh cortical uses shared atlas name
            if not self.atlas_name_combo.currentText():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "Please select a shared mesh atlas name for cortical analysis.",
                )
                return False
        else:
            # Voxel cortical - check if we have valid atlases for all subjects
            if not self.group_atlas_config:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "Please ensure valid atlases are available for all selected subjects (Voxel Cortical).",
                )
                return False

        return self.validate_analysis_parameters()

    def _parse_coords_radius(self, show_warning=True):
        """Parse 'x,y,z,r' from the single input field. Returns (x,y,z,r) or None."""
        text = self.coords_radius_input.text().strip()
        if not text:
            if show_warning:
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "Please enter coordinates and radius as x,y,z,r."
                )
            return None
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 4:
            if show_warning:
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "Enter exactly 4 values: x,y,z,r."
                )
            return None
        try:
            x, y, z, r = (
                float(parts[0]),
                float(parts[1]),
                float(parts[2]),
                float(parts[3]),
            )
        except ValueError:
            if show_warning:
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "All values must be numeric: x,y,z,r."
                )
            return None
        if r <= 0:
            if show_warning:
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "Radius must be positive."
                )
            return None
        return (x, y, z, r)

    def validate_analysis_parameters(self):  # Shared parameters
        if self.type_spherical.isChecked():
            parsed = self._parse_coords_radius()
            if parsed is None:
                return False
        elif self.type_cortical.isChecked():
            # Atlas selection for cortical is handled by validate_single/group_inputs
            if not self._get_regions() and not self.region_input.text().strip():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "Please add at least one region for cortical analysis.",
                )
                return False
        return True

    def run_analysis(self):
        if self.analysis_running:
            self.update_output(
                "Analysis already running. Please wait or stop the current run."
            )
            return
        if not self.validate_inputs():
            return

        details, title = "", ""
        if self.is_group_mode:
            details = self.get_group_analysis_details([])
            title = f"Confirm Group Analysis ({self.pairs_table.rowCount()} subject-simulation pairs)"
        else:
            details = self.get_single_analysis_details()
            title = "Confirm Single Analysis"

        if not ConfirmationDialog.confirm(
            self,
            title=title,
            message="Are you sure you want to start the analysis?",
            details=details,
        ):
            self.update_output("Analysis cancelled by user.")
            return

        self.analysis_running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.disable_controls()

        if self.is_group_mode:
            self.run_group_analysis()
        else:
            self.run_single_analysis()

    def run_single_analysis(self):
        try:
            # Prevent accidental double-starts
            if getattr(self, "_thread_started", False):
                return
            if (
                hasattr(self, "optimization_process")
                and self.optimization_process
                and self.optimization_process.isRunning()
            ):
                return
            # In single mode, get the subject and simulation from the single pair
            if self.pairs_table.rowCount() != 1:
                self.update_output(
                    "Error: Single analysis requires exactly one subject-simulation pair."
                )
                self.analysis_finished(success=False)
                return

            subject_combo = self.pairs_table.cellWidget(0, 0)
            sim_combo = self.pairs_table.cellWidget(0, 1)

            if not subject_combo or not sim_combo:
                self.update_output(
                    "Error: Subject-simulation pair not properly configured."
                )
                self.analysis_finished(success=False)
                return

            subject_id = subject_combo.currentText()
            simulation_name = sim_combo.currentText()

            if not subject_id or not simulation_name:
                self.update_output("Error: Subject or simulation not selected.")
                self.analysis_finished(success=False)
                return

            cmd = self.build_single_analysis_command(subject_id, simulation_name)
            if not cmd:  # build_analysis_command returns None on error
                self.analysis_finished(success=False)
                return

            env = os.environ.copy()
            env["PROJECT_DIR"] = self.pm.project_dir
            env["SUBJECT_ID"] = subject_id  # Passed to script via env

            # Ensure the analyzer runs against the repo sources even when launched from the GUI.
            # When executing `-m tit...`, Python needs the repo root on sys.path.
            gui_app_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )  # .../tit
            repo_root = os.path.dirname(gui_app_root)  # .../ (ti-toolbox)
            env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")

            # Mark thread start as early as possible to avoid race double-starts
            self._thread_started = True

            # Clear summary printed set at start of new analysis to ensure summary output shows
            if hasattr(self, "_summary_printed"):
                self._summary_printed.clear()
            else:
                self._summary_printed = set()

            # Record output dir for later summary line (guard against duplicates)
            if not getattr(self, "_summary_started", False):
                self._last_output_dir = self._extract_output_dir_from_cmd(cmd)
                # Mark started to avoid duplicated blocks
                # Note: The analyzer process will print all the step messages via its logging functions
                self._summary_started = True

            self.optimization_process = AnalysisThread(cmd, env, cwd=repo_root)
            self.optimization_process.output_signal.connect(
                self.update_output, QtCore.Qt.QueuedConnection
            )
            self.optimization_process.finished.connect(
                lambda sid=subject_id, sim_name=simulation_name: self.analysis_finished(
                    subject_id=sid, simulation_name=sim_name, success=True
                ),
                QtCore.Qt.QueuedConnection,
            )
            self._thread_started = True
            self.optimization_process.start()
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            self.update_output(f"Error preparing single analysis: {str(e)}")
            self.analysis_finished(success=False)

    def run_group_analysis(self):
        """Run group analysis using the Analyzer API."""
        try:
            # Build the group analyzer command
            cmd = self.build_group_analyzer_command()
            if not cmd:
                self.update_output("Error: Could not build group analyzer command.")
                self.analysis_finished(success=False)
                return

            env = os.environ.copy()
            env["PROJECT_DIR"] = self.pm.project_dir

            # Ensure group analyzer also runs against repo sources.
            gui_app_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )  # .../tit
            repo_root = os.path.dirname(gui_app_root)  # .../ (ti-toolbox)
            env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")

            # Clear summary printed set at start of new analysis to ensure summary output shows
            if hasattr(self, "_summary_printed"):
                self._summary_printed.clear()
            else:
                self._summary_printed = set()

            # Provide a concise start message
            pairs_summary = []
            for row in range(self.pairs_table.rowCount()):
                subject_combo = self.pairs_table.cellWidget(row, 0)
                sim_combo = self.pairs_table.cellWidget(row, 1)
                if subject_combo and sim_combo:
                    subject_id = subject_combo.currentText()
                    simulation_name = sim_combo.currentText()
                    if subject_id and simulation_name:
                        pairs_summary.append(f"{subject_id}({simulation_name})")
            self.ANALYSIS_START_TIME = time.time()
            self.update_output(
                f"Beginning group analysis for pairs: {', '.join(pairs_summary)}"
            )
            self._last_output_dir = self._extract_output_dir_from_cmd(cmd)

            # Create and start thread
            self.optimization_process = AnalysisThread(cmd, env, cwd=repo_root)
            self.optimization_process.output_signal.connect(
                self.update_output, QtCore.Qt.QueuedConnection
            )
            self.optimization_process.finished.connect(
                lambda: self.analysis_finished(success=True), QtCore.Qt.QueuedConnection
            )
            self.optimization_process.start()

        except (OSError, ValueError, KeyError, RuntimeError) as e:
            self.update_output(f"Error preparing group analysis: {str(e)}")
            self.analysis_finished(success=False)

    def build_group_analyzer_command(self):
        """Build command to run group analysis using the new Analyzer API via subprocess."""
        try:
            project_dir = self.pm.project_dir
            if not project_dir:
                self.update_output("Error: Could not determine project directory")
                return None

            space = "mesh" if self.space_mesh.isChecked() else "voxel"
            analysis_type = (
                "spherical" if self.type_spherical.isChecked() else "cortical"
            )

            # Collect subject-simulation pairs and validate m2m directories
            subject_ids = []
            simulation_names = []
            for row in range(self.pairs_table.rowCount()):
                subject_combo = self.pairs_table.cellWidget(row, 0)
                sim_combo = self.pairs_table.cellWidget(row, 1)

                if subject_combo and sim_combo:
                    subject_id = subject_combo.currentText()
                    simulation_name = sim_combo.currentText()

                    if not subject_id or not simulation_name:
                        self.update_output(
                            f"Error: Incomplete subject-simulation pair in row {row + 1}"
                        )
                        return None
                else:
                    self.update_output(
                        f"Error: Invalid subject-simulation pair in row {row + 1}"
                    )
                    return None

                m2m_path = self.pm.m2m(subject_id)
                if not m2m_path or not os.path.isdir(m2m_path):
                    self.update_output(
                        f"Error: m2m_{subject_id} folder not found at {m2m_path}. Please create the m2m folder first using the Pre-process tab.",
                        "error",
                    )
                    return None

                subject_ids.append(subject_id)
                simulation_names.append(simulation_name)

            # Verify all simulations are the same (required by run_group_analysis API)
            unique_sims = set(simulation_names)
            if len(unique_sims) != 1:
                self.update_output(
                    "Error: Group analysis requires all subjects to use the same simulation/montage. "
                    f"Found: {', '.join(sorted(unique_sims))}"
                )
                return None
            simulation = simulation_names[0]

            # Build analysis-specific kwargs for the script
            if analysis_type == "spherical":
                x, y, z, radius = self._parse_coords_radius()
                coord_space = "MNI" if self.coord_space_mni.isChecked() else "subject"

                analysis_kwargs = (
                    f"    center=({x}, {y}, {z}),\n"
                    f"    radius={radius},\n"
                    f"    coordinate_space={coord_space!r},\n"
                )
            else:  # cortical
                if self.space_mesh.isChecked():
                    atlas_name = self.atlas_name_combo.currentText()
                    if not atlas_name:
                        self.update_output(
                            "Error: Atlas name is required for mesh cortical analysis."
                        )
                        return None
                else:
                    atlas_name = self.atlas_combo.currentText()
                    if not atlas_name:
                        self.update_output(
                            "Error: Atlas is required for cortical analysis."
                        )
                        return None
                    # Strip file extension for voxel atlas name
                    for ext in (".mgz", ".nii.gz", ".nii"):
                        if atlas_name.endswith(ext):
                            atlas_name = atlas_name[: -len(ext)]
                            break

                regions = self._get_regions()
                if not regions:
                    self.update_output(
                        "Error: At least one region is required for cortical analysis."
                    )
                    return None

                if len(regions) == 1:
                    region = regions[0]
                    analysis_kwargs = (
                        f"    atlas={atlas_name!r},\n" f"    region={region!r},\n"
                    )
                else:
                    analysis_kwargs = (
                        f"    atlas={atlas_name!r},\n" f"    regions={regions!r},\n"
                    )

            temp_output_dir = self.pm.simnibs()

            # Build JSON config for the group analysis
            config = {
                "mode": "group",
                "project_dir": project_dir,
                "subject_ids": subject_ids,
                "simulation": simulation,
                "space": space,
                "tissue_type": self.tissue_combo.currentData(),
                "analysis_type": analysis_type,
                "visualize": True,
                "output_dir": temp_output_dir,
            }

            if analysis_type == "spherical":
                config["center"] = [coords[0], coords[1], coords[2]]
                config["radius"] = radius
                config["coordinate_space"] = coord_space
            else:  # cortical
                config["atlas"] = atlas_name
                if len(regions) == 1:
                    config["region"] = regions[0]
                else:
                    config["regions"] = regions

            fd, config_path = tempfile.mkstemp(
                suffix=".json", prefix="analysis_config_"
            )
            with os.fdopen(fd, "w") as f:
                json.dump(config, f, indent=2)

            cmd = ["simnibs_python", "-m", "tit.analyzer", config_path]
            return cmd

        except (OSError, ValueError, KeyError) as e:
            self.update_output(f"Error building group analyzer command: {str(e)}")
            return None

    def get_single_analysis_details(self):
        if self.pairs_table.rowCount() != 1:
            return "Single analysis requires exactly one subject-simulation pair."

        subject_combo = self.pairs_table.cellWidget(0, 0)
        sim_combo = self.pairs_table.cellWidget(0, 1)

        if not subject_combo or not sim_combo:
            return "Subject-simulation pair not properly configured."

        subj = subject_combo.currentText()
        mont = sim_combo.currentText()

        if not subj or not mont:
            return "Subject or simulation not selected."

        space = "Mesh" if self.space_mesh.isChecked() else "Voxel"
        atype = "Spherical" if self.type_spherical.isChecked() else "Cortical"
        details = f"- Subject: {subj}\n- Space: {space}\n- Analysis Type: {atype}\n- Simulation: {mont}\n"
        if self.space_voxel.isChecked():
            details += f"- Tissue: {self.tissue_combo.currentText()}\n"
        if self.space_mesh.isChecked():
            details += f"- Field File: {mont}.msh (auto-selected)\n"
        if self.type_spherical.isChecked():
            coord_space = "MNI" if self.coord_space_mni.isChecked() else "RAS"
            parsed = self._parse_coords_radius()
            if parsed:
                x, y, z, r = parsed
                details += f"- Coordinates ({coord_space}): ({x}, {y}, {z})\n- Radius: {r} mm\n"
            else:
                details += f"- Coordinates: {self.coords_radius_input.text()}\n"
            if self.coord_space_mni.isChecked():
                details += (
                    f"- Coordinate Transformation: MNI → Subject space (automatic)\n"
                )
        else:  # Cortical
            if self.space_mesh.isChecked():
                details += f"- Mesh Atlas: {self.atlas_name_combo.currentText()}\n"
            else:
                details += f"- Voxel Atlas File: {self.atlas_combo.currentText()} (Path: {self.atlas_combo.currentData() or 'N/A'})\n"  # Show path
            regions = self._get_regions()
            details += f"- Region(s): {', '.join(regions) if regions else self.region_input.text()}\n"
        details += f"- Generate Visualizations: Yes"
        return details

    def get_group_analysis_details(self, subjects):
        space = "Mesh" if self.space_mesh.isChecked() else "Voxel"
        analysis_type = "Spherical" if self.type_spherical.isChecked() else "Cortical"

        # Collect subject-simulation pairs
        pairs_info = []
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)
            if subject_combo and sim_combo:
                subject_id = subject_combo.currentText()
                simulation_name = sim_combo.currentText()
                if subject_id and simulation_name:
                    pairs_info.append(f"{subject_id}({simulation_name})")

        details = f"- Subject-Simulation Pairs: {', '.join(pairs_info)}\n- Space: {space}\n- Analysis Type: {analysis_type}\n"
        if self.space_voxel.isChecked():
            details += f"- Tissue: {self.tissue_combo.currentText()}\n"

        # Shared analysis parameters
        details += "\n- Shared Analysis Parameters:\n"
        if self.type_spherical.isChecked():
            coord_space = "MNI" if self.coord_space_mni.isChecked() else "Subject RAS"
            parsed = self._parse_coords_radius()
            if parsed:
                x, y, z, r = parsed
                details += f"- Coordinates ({coord_space}): ({x}, {y}, {z})\n- Radius: {r} mm\n"
            else:
                details += f"- Coordinates: {self.coords_radius_input.text()}\n"
            if self.coord_space_mni.isChecked():
                details += f"- Coordinate Transformation: MNI → Subject space (automatic for each)\n"
        else:  # cortical
            if self.space_mesh.isChecked():
                details += (
                    f"- Shared Mesh Atlas: {self.atlas_name_combo.currentText()}\n"
                )
            else:
                details += f"- Voxel Atlas: Common atlas configuration\n"
            regions = self._get_regions()
            details += f"- Region(s): {', '.join(regions) if regions else self.region_input.text()} (for all)\n"
        details += f"- Generate Visualizations: Yes"
        return details

    def force_ui_refresh(self):
        """Force a complete UI refresh to ensure all controls are in the correct state."""
        # Force update of all relevant UI components
        self.update_atlas_visibility()

        # Force widget updates
        if hasattr(self, "analysis_params_container"):
            self.analysis_params_container.update()

        # Process any pending events
        QtWidgets.QApplication.processEvents()

    def analysis_finished(self, subject_id=None, simulation_name=None, success=True):
        if (
            hasattr(self, "_processing_analysis_finished_lock")
            and self._processing_analysis_finished_lock
        ):
            return
        self._processing_analysis_finished_lock = True
        try:
            if success:
                if getattr(self, "_summary_started", False) and not getattr(
                    self, "_summary_finished", False
                ):
                    # Note: The analyzer process already prints all step completion messages via its logging functions.
                    # We just need to mark that the summary is finished to avoid duplicate processing.
                    self._summary_finished = True
                else:
                    last_line = (
                        self.output_console.toPlainText().strip().split("\n")[-1]
                        if self.output_console.toPlainText()
                        else ""
                    )
                    if (
                        "WARNING: Analysis Failed" in last_line
                        or "Error: Process returned non-zero" in last_line
                        or "failed" in last_line.lower()
                    ):
                        self.update_output(
                            '<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">[ERROR] Analysis process indicated failure.</span></div>'
                        )
                    else:
                        self.update_output(
                            '<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">[SUCCESS] Analysis process completed.</span></div>'
                        )

                # Emit analysis completed signal for single mode or group mode
                if subject_id and simulation_name:
                    analysis_type_str = (
                        "Mesh" if self.space_mesh.isChecked() else "Voxel"
                    )
                    self.analysis_completed.emit(
                        subject_id, simulation_name, analysis_type_str
                    )
                elif self.is_group_mode:
                    analysis_type_str = (
                        "Mesh" if self.space_mesh.isChecked() else "Voxel"
                    )
                    # For group mode, emit with first subject and 'group_analysis' as simulation name
                    if self.pairs_table.rowCount() > 0:
                        first_subject_combo = self.pairs_table.cellWidget(0, 0)
                        if first_subject_combo:
                            first_subject = first_subject_combo.currentText()
                            self.analysis_completed.emit(
                                first_subject, "group_analysis", analysis_type_str
                            )
            else:
                self.update_output(
                    '<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">[ERROR] Analysis process failed or was cancelled by user.</span></div>'
                )

            self.analysis_running = False
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.enable_controls()
            # Reset summary flags for next run
            if hasattr(self, "_summary_started"):
                delattr(self, "_summary_started")
            if hasattr(self, "_summary_finished"):
                delattr(self, "_summary_finished")
            if hasattr(self, "_thread_started"):
                delattr(self, "_thread_started")
            if hasattr(self, "_last_plain_output_line"):
                delattr(self, "_last_plain_output_line")
            # Clear the summary printed set to allow summary output on next run
            if hasattr(self, "_summary_printed"):
                self._summary_printed.clear()

            # Force a complete UI refresh to ensure everything is properly restored
            QtCore.QTimer.singleShot(100, self.force_ui_refresh)

        finally:
            self._processing_analysis_finished_lock = False

    def stop_analysis(self):
        if (
            hasattr(self, "optimization_process")
            and self.optimization_process
            and self.optimization_process.isRunning()
        ):
            self.update_output("Attempting to stop analysis...")
            if (
                self.optimization_process.terminate_process()
            ):  # This sets self.terminated in thread
                self.update_output(
                    "Analysis process termination requested. Please wait..."
                )
                # Thread will emit finished signal, which calls analysis_finished
            else:  # Should not happen if isRunning is true
                self.update_output(
                    "Analysis process was not running or already terminated (unexpected)."
                )
                self.analysis_finished(success=False)
        else:
            self.update_output("No analysis process to stop.")
            # If UI was stuck in disabled state but no process, reset it
            if self.analysis_running:  # If flag was true but no process
                self.analysis_finished(success=False)
            else:  # Just ensure UI is enabled
                self.enable_controls()
        # Fallback UI reset in case thread doesn't signal quickly or gets stuck
        # This might be too aggressive if thread is just taking time to terminate
        # QtCore.QTimer.singleShot(3000, self._ensure_ui_reset_after_stop)

    # def _ensure_ui_reset_after_stop(self): # Helper for delayed UI reset
    #     if self.analysis_running: # If still marked as running after timeout
    #         print("Timeout: Forcing UI reset after stop request.")
    #         self.analysis_finished(success=False)

    def clear_console(self):
        self.output_console.clear()

    def update_output(
        self, text, message_type="default"
    ):  # This is the method used by AnalysisThread's signal
        if not text or not text.strip():
            return

        # Use shared color mapping for known message types
        if message_type == "debug":
            # Analyzer uses italic for debug messages
            formatted_text = f'<span style="color: #7f7f7f;"><i>{text}</i></span>'
        elif message_type in ("error", "warning", "command", "success", "info"):
            formatted_text = format_message(text, message_type)
        else:
            # Fallback to content-based formatting for backward compatibility
            # Group analysis specific patterns
            if (
                "=== Processing subject:" in text
                or "=== GROUP ANALYSIS SUMMARY ===" in text
            ):
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 5px; margin: 5px 0; border-radius: 3px;"><span style="color: #55ffff; font-weight: bold;">{text}</span></div>'
            elif "[OK] Subject" in text or "[FAILED] Subject" in text:
                formatted_text = (
                    f'<span style="color: #55ff55; font-weight: bold;">{text}</span>'
                    if "[OK]" in text
                    else f'<span style="color: #ff5555; font-weight: bold;">{text}</span>'
                )
            elif (
                "Group analysis complete" in text
                or "Comprehensive group results" in text
            ):
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #55ff55; font-weight: bold; font-size: 14px;">{text}</span></div>'
            elif "Analysis Results Summary:" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #55ff55; font-weight: bold; font-size: 14px;">{text}</span></div>'
            elif any(
                value_type in text
                for value_type in [
                    "Mean Value:",
                    "Max Value:",
                    "Min Value:",
                    "Focality:",
                ]
            ):
                parts = text.split(":")
                if len(parts) == 2:
                    value_type, value = parts
                    formatted_text = f'<div style="margin: 5px 20px;"><span style="color: #aaaaaa;">{value_type}:</span> <span style="color: #55ffff; font-weight: bold;">{value}</span></div>'
                else:
                    formatted_text = format_message(text, "default")
            elif text.strip().startswith("-"):
                formatted_text = (
                    f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
                )
            else:
                formatted_text = format_message(text, "default")

        # Append with autoscroll; no processEvents to prevent re-entrant recursion
        append_with_autoscroll(
            self.output_console, formatted_text, process_events=False
        )

    # ===== Summary-mode helpers =====
    def _build_start_details(self, subject_id):
        if self.type_cortical.isChecked():
            if self.space_mesh.isChecked():
                atlas = self.atlas_name_combo.currentText() or ""
            else:
                atlas = os.path.basename(self.atlas_combo.currentText() or "").split(
                    "."
                )[0]
            regions = self._get_regions()
            region_str = (
                "+".join(regions)
                if regions
                else self.region_input.text().strip() or "region"
            )
            return f"Cortical: {atlas}.{region_str}"
        else:
            parsed = self._parse_coords_radius()
            if parsed:
                x, y, z, r = parsed
                return f"Spherical: ({x},{y},{z}) r{r}mm"
            return f"Spherical: {self.coords_radius_input.text()}"

    def _extract_output_dir_from_cmd(self, cmd):
        try:
            if "--output_dir" in cmd:
                idx = cmd.index("--output_dir")
                return cmd[idx + 1] if idx + 1 < len(cmd) else None
            # For inline -c scripts, try to extract output_dir from the script text
            if "-c" in cmd:
                idx = cmd.index("-c")
                if idx + 1 < len(cmd):
                    import re

                    m = re.search(r"output_dir=['\"]([^'\"]+)['\"]", cmd[idx + 1])
                    if m:
                        return m.group(1)
        except (ValueError, IndexError, AttributeError):
            return None
        return None

    def disable_controls(self):
        # List of widgets to disable, similar to original
        widgets_to_set_enabled = [
            # Pair management buttons
            self.add_pair_btn,
            self.quick_add_btn,
            self.clear_pairs_btn,
            self.refresh_pairs_btn,
            # Other widgets
            self.space_mesh,
            self.space_voxel,
            self.type_spherical,
            self.type_cortical,
            self.coords_radius_input,
            self.view_in_freeview_btn,
            self.atlas_name_combo,
            self.atlas_combo,
            self.show_regions_btn,
            self.region_input,
        ]
        for widget in widgets_to_set_enabled:
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(False)

        self.status_label.setText("Processing... Stop button is available.")
        self.status_label.show()

    def enable_controls(self):
        widgets_to_set_enabled = [
            # Pair management buttons
            self.add_pair_btn,
            self.quick_add_btn,
            self.clear_pairs_btn,
            self.refresh_pairs_btn,
            # Other widgets
            self.space_mesh,
            self.space_voxel,
            self.type_spherical,
            self.type_cortical,
            self.coords_radius_input,
            self.view_in_freeview_btn,
            # atlas_name_combo, atlas_combo, show_regions_btn, region_input handled by update_atlas_visibility
        ]
        for widget in widgets_to_set_enabled:
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(True)

        # Force enable these controls first, then let update_atlas_visibility handle proper state
        self.region_input.setEnabled(True)
        self.region_label.setEnabled(True)
        self.region_list.setEnabled(True)
        self.add_region_btn.setEnabled(True)
        self.remove_region_btn.setEnabled(True)
        self.atlas_name_combo.setEnabled(True)
        # Don't force enable atlas_combo - let update_atlas_visibility handle it properly
        self.show_regions_btn.setEnabled(True)

        # Now update visibility and proper enable states
        self.update_atlas_visibility()  # This will correctly set enable states for atlas/region controls

        # Spherical analysis should be enabled in both modes
        self.type_spherical.setEnabled(True)

        self.status_label.hide()

    @staticmethod
    def _list_annot_regions(seg_dir, atlas_name):
        """Read region names from .annot files in the segmentation directory."""
        from tit.atlas import MeshAtlasManager

        return MeshAtlasManager(seg_dir).list_regions(atlas_name)

    def _add_region(self):
        """Add the typed region name to the region list."""
        text = self.region_input.text().strip()
        if text and not self._region_list_contains(text):
            self.region_list.addItem(text)
            self.region_input.clear()

    def _remove_region(self):
        """Remove the selected region from the region list."""
        for item in self.region_list.selectedItems():
            self.region_list.takeItem(self.region_list.row(item))

    def _region_list_contains(self, text: str) -> bool:
        """Check if a region name is already in the list."""
        for i in range(self.region_list.count()):
            if self.region_list.item(i).text() == text:
                return True
        return False

    def _get_regions(self) -> list:
        """Return list of selected regions."""
        return [
            self.region_list.item(i).text() for i in range(self.region_list.count())
        ]

    def show_available_regions(self):
        """Show a searchable dialog of available regions for the selected atlas."""
        selected_subjects = self.get_selected_subjects()
        if not selected_subjects:
            QtWidgets.QMessageBox.warning(
                self, "Selection Error", "Please select a subject first."
            )
            return

        progress_dialog = QtWidgets.QProgressDialog(
            "Loading atlas regions...", "Cancel", 0, 100, self
        )
        progress_dialog.setWindowTitle("Loading Atlas Regions")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(200)
        progress_dialog.setValue(0)

        atlas_type_display, regions = "", []
        subject_id = selected_subjects[0]

        if self.space_mesh.isChecked():
            atlas_name = self.atlas_name_combo.currentText()
            if not atlas_name:
                QtWidgets.QMessageBox.warning(self, "Atlas Error", "Select mesh atlas.")
                return
            atlas_type_display = atlas_name
            m2m_dir = self.pm.m2m(subject_id)
            if not os.path.isdir(m2m_dir):
                QtWidgets.QMessageBox.critical(
                    self, "Error", f"m2m dir not found: {subject_id}."
                )
                return

            progress_dialog.setValue(20)
            QtWidgets.QApplication.processEvents()
            seg_dir = os.path.join(m2m_dir, "segmentation")
            regions = self._list_annot_regions(seg_dir, atlas_name)
            progress_dialog.setValue(80)
            QtWidgets.QApplication.processEvents()

        else:  # Voxel atlas
            atlas_path = self.atlas_combo.currentData()
            if not atlas_path or not os.path.isfile(atlas_path):
                QtWidgets.QMessageBox.warning(
                    self, "Atlas Error", "Select valid voxel atlas."
                )
                return
            atlas_type_display = os.path.basename(atlas_path)
            progress_dialog.setLabelText("Extracting voxel regions...")
            progress_dialog.setValue(20)
            QtWidgets.QApplication.processEvents()

            from tit.atlas import VoxelAtlasManager

            regions = VoxelAtlasManager().list_regions(atlas_path)
            progress_dialog.setValue(90)

        if not regions:
            QtWidgets.QMessageBox.information(
                self, "No Regions", f"No regions for: {atlas_type_display}"
            )
            progress_dialog.cancel()
            return
        progress_dialog.setValue(100)
        progress_dialog.close()

        # Show searchable region dialog
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"Available Regions - {atlas_type_display}")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(500)
        layout = QtWidgets.QVBoxLayout(dialog)

        search_input = QtWidgets.QLineEdit()
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("Search:"))
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)

        list_widget = QtWidgets.QListWidget()
        list_widget.addItems(regions)
        layout.addWidget(list_widget)

        def filter_regions(text):
            for i in range(list_widget.count()):
                list_widget.item(i).setHidden(
                    text.lower() not in list_widget.item(i).text().lower()
                )

        def select_region():
            item = list_widget.currentItem()
            if item:
                region_text = item.text().split(" (ID:")[0]
                if not self._region_list_contains(region_text):
                    self.region_list.addItem(region_text)
                dialog.accept()

        search_input.textChanged.connect(filter_regions)
        list_widget.itemDoubleClicked.connect(lambda: select_region())

        btn_layout = QtWidgets.QHBoxLayout()
        copy_btn = QtWidgets.QPushButton("Add Selected")
        close_btn = QtWidgets.QPushButton("Close")
        copy_btn.clicked.connect(select_region)
        close_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.exec_()

    def load_t1_in_freeview(self):
        """Load subject's T1 NIfTI file or MNI template in Freeview for coordinate selection."""
        try:
            selected_subjects = self.get_selected_subjects()
            if not selected_subjects:
                QtWidgets.QMessageBox.warning(self, "Warning", "Select subject.")
                return

            if self.coord_space_mni.isChecked() and self.type_spherical.isChecked():
                # MNI space selected: load MNI template
                # Look for MNI template in common locations
                mni_paths = [
                    "/usr/share/fsl/data/standard/MNI152_T1_1mm.nii.gz",
                    "/opt/fsl/data/standard/MNI152_T1_1mm.nii.gz",
                    "$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz",
                    # Check project assets folder
                    os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets",
                        "atlas",
                        "MNI152_T1_1mm.nii.gz",
                    ),
                ]

                mni_file = None
                for path in mni_paths:
                    # Expand environment variables
                    expanded_path = os.path.expandvars(path)
                    if os.path.isfile(expanded_path):
                        mni_file = expanded_path
                        break

                if not mni_file:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        "MNI152 template not found. Please ensure FSL is installed or place MNI152_T1_1mm.nii.gz in resources/atlas/",
                    )
                    return

                # Launch Freeview with MNI template
                subprocess.Popen(["freeview", mni_file])
                self.update_output(
                    f"Launched Freeview with MNI152 template: {mni_file}"
                )
                self.update_output(
                    "Use Freeview to find MNI coordinates and enter them in the coordinate fields."
                )
                self.update_output(
                    "These MNI coordinates will be automatically transformed to each subject's native space."
                )
            else:
                # Single mode or non-spherical: load subject's T1
                subject_id = selected_subjects[0]
                m2m_dir_path = self.pm.m2m(subject_id)
                if not m2m_dir_path or not os.path.isdir(m2m_dir_path):
                    QtWidgets.QMessageBox.warning(
                        self, "Error", f"m2m dir not found for {subject_id}."
                    )
                    return

                t1_nii_gz_path = os.path.join(m2m_dir_path, "T1.nii.gz")
                t1_mgz_path = os.path.join(m2m_dir_path, "T1.mgz")  # Check for .mgz too

                final_t1_path = None
                if os.path.exists(t1_nii_gz_path):
                    final_t1_path = t1_nii_gz_path
                elif os.path.exists(t1_mgz_path):
                    final_t1_path = t1_mgz_path

                if not final_t1_path:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        f"T1 image (T1.nii.gz or T1.mgz) not found in {m2m_dir_path}",
                    )
                    return

                subprocess.Popen(["freeview", final_t1_path])
                self.update_output(f"Launched Freeview with T1 image: {final_t1_path}")

        except FileNotFoundError:
            QtWidgets.QMessageBox.critical(
                self, "Error", "Freeview not found. Ensure installed and in PATH."
            )
        except (OSError, subprocess.SubprocessError) as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to launch Freeview: {str(e)}"
            )
            self.update_output(f"Error: {e}")

    def update_field_files(
        self, analyzed_subject_id=None, analyzed_simulation_name=None
    ):
        """Update field files list after analysis completion.

        This method is called from main.py after analysis completion.
        Refreshes the gmsh visualization dropdowns to show newly available meshes.

        Parameters
        ----------
        analyzed_subject_id : str, optional
            The subject ID that was just analyzed. If provided, the gmsh dropdowns
            will be set to this subject/simulation and the analyses list will be refreshed.
        analyzed_simulation_name : str, optional
            The simulation name that was just analyzed. If provided along with subject_id,
            the gmsh dropdowns will be set to this subject/simulation.
        """
        # Refresh gmsh visualization dropdowns to show newly created mesh analyses
        if hasattr(self, "gmsh_subject_combo") and hasattr(self, "gmsh_sim_combo"):
            # Refresh subjects list (in case new subjects were added)
            self.update_gmsh_subjects()

            # If we have the analyzed subject/simulation, set the dropdowns to match
            if analyzed_subject_id:
                index = self.gmsh_subject_combo.findText(analyzed_subject_id)
                if index >= 0:
                    self.gmsh_subject_combo.setCurrentIndex(index)
                    # This will trigger update_gmsh_simulations() via signal connection
                    # Use a small delay to ensure simulations are updated first
                    if analyzed_simulation_name:
                        QtCore.QTimer.singleShot(
                            50,
                            lambda: self._set_gmsh_simulation(analyzed_simulation_name),
                        )
                    else:
                        # Just update simulations for the selected subject
                        self.update_gmsh_simulations()
                else:
                    # Subject not found, just update simulations for first subject if available
                    if self.gmsh_subject_combo.count() > 0:
                        self.update_gmsh_simulations()
            else:
                # No analyzed subject provided, preserve current selection if possible
                current_subject = self.gmsh_subject_combo.currentText()
                current_sim = self.gmsh_sim_combo.currentText()

                if current_subject:
                    index = self.gmsh_subject_combo.findText(current_subject)
                    if index >= 0:
                        self.gmsh_subject_combo.setCurrentIndex(index)
                        if current_sim:
                            QtCore.QTimer.singleShot(
                                50, lambda: self._restore_gmsh_selection(current_sim)
                            )
                    else:
                        # Subject no longer exists, just update simulations for first subject
                        self.update_gmsh_simulations()
                else:
                    # No subject was selected, just update simulations for first subject if available
                    if self.gmsh_subject_combo.count() > 0:
                        self.update_gmsh_simulations()

    def _set_gmsh_simulation(self, simulation_name):
        """Helper method to set gmsh simulation selection and refresh analyses."""
        if hasattr(self, "gmsh_sim_combo"):
            index = self.gmsh_sim_combo.findText(simulation_name)
            if index >= 0:
                self.gmsh_sim_combo.setCurrentIndex(index)
                # This will trigger update_gmsh_analyses() via signal connection
            else:
                # Simulation not found, just update analyses for first simulation
                self.update_gmsh_analyses()

    def _restore_gmsh_selection(self, simulation_name):
        """Helper method to restore gmsh simulation selection after refresh."""
        if hasattr(self, "gmsh_sim_combo"):
            index = self.gmsh_sim_combo.findText(simulation_name)
            if index >= 0:
                self.gmsh_sim_combo.setCurrentIndex(index)
                # This will trigger update_gmsh_analyses() via signal connection
            else:
                # Simulation no longer exists, just update analyses for first simulation
                self.update_gmsh_analyses()

    def update_gmsh_subjects(self):
        """Update the gmsh subject dropdown with available subjects."""
        self.gmsh_subject_combo.clear()
        # Use path_manager to find subjects via m2m_dir
        subjects = self.pm.list_subjects()
        if subjects:
            self.gmsh_subject_combo.addItems(subjects)
            if len(subjects) == 1:
                self.gmsh_subject_combo.setCurrentIndex(0)
                self.update_gmsh_simulations()

    def update_gmsh_simulations(self):
        """Update the gmsh simulation dropdown based on selected subject."""
        self.gmsh_sim_combo.clear()
        subject_id = self.gmsh_subject_combo.currentText()
        if not subject_id:
            return

        # Use sim_dir to find simulations via path_manager
        simulations = self.pm.list_simulations(subject_id)
        if simulations:
            self.gmsh_sim_combo.addItems(simulations)
            if len(simulations) == 1:
                self.gmsh_sim_combo.setCurrentIndex(0)
                self.update_gmsh_analyses()

    def update_gmsh_analyses(self):
        """Update the gmsh analysis dropdown based on selected subject and simulation."""
        self.gmsh_analysis_combo.clear()
        subject_id = self.gmsh_subject_combo.currentText()
        simulation_name = self.gmsh_sim_combo.currentText()

        if not subject_id or not simulation_name:
            return

        # Look specifically in Analyses/Mesh/ for mesh analysis folders (centralized via PathManager)
        mesh_dir = self.pm.analysis_dir(subject_id, simulation_name, "mesh")

        if not mesh_dir or not os.path.exists(mesh_dir):
            return

        try:
            # Look for mesh analysis folders in Analyses/Mesh/
            mesh_analyses = []
            for item in os.listdir(mesh_dir):
                item_path = os.path.join(mesh_dir, item)
                if os.path.isdir(item_path) and not item.startswith("."):
                    # Check if this analysis folder contains any .msh files
                    has_meshes = False
                    for root, _, files in os.walk(item_path):
                        if any(f.endswith(".msh") for f in files):
                            has_meshes = True
                            break
                    if has_meshes:
                        mesh_analyses.append(item)

            if mesh_analyses:
                self.gmsh_analysis_combo.addItems(sorted(mesh_analyses))
                if len(mesh_analyses) == 1:
                    self.gmsh_analysis_combo.setCurrentIndex(0)
        except OSError as e:
            self.update_output(f"Error listing mesh analyses: {e}")

    def launch_gmsh_simple(self):
        """Launch Gmsh with the selected subject, simulation, and analysis."""
        subject_id = self.gmsh_subject_combo.currentText()
        simulation_name = self.gmsh_sim_combo.currentText()
        analysis_name = self.gmsh_analysis_combo.currentText()

        if not subject_id or not simulation_name or not analysis_name:
            QtWidgets.QMessageBox.warning(
                self, "Warning", "Please select subject, simulation, and analysis first"
            )
            return

        # Find the analysis directory in Analyses/Mesh/ and look for .msh files
        mesh_dir = self.pm.analysis_dir(subject_id, simulation_name, "mesh")
        analysis_dir = os.path.join(mesh_dir, analysis_name) if mesh_dir else None

        if not analysis_dir or not os.path.exists(analysis_dir):
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Analysis directory not found: {analysis_dir}"
            )
            return

        # Find .msh files in the analysis directory
        msh_files = []
        for root, _, files in os.walk(analysis_dir):
            for file_item in files:
                if file_item.endswith(".msh"):
                    msh_files.append(os.path.join(root, file_item))

        if not msh_files:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"No mesh files found in analysis: {analysis_name}"
            )
            return

        # If multiple mesh files, use the first one (or could show selection dialog)
        msh_file = msh_files[0]

        try:
            # Launch Gmsh directly with the mesh file as argument
            subprocess.Popen(["gmsh", msh_file])
            self.update_output(f"Launched Gmsh with mesh file: {msh_file}")
        except FileNotFoundError:
            QtWidgets.QMessageBox.critical(
                self, "Error", "Gmsh not found. Please install Gmsh and add it to PATH."
            )
        except (OSError, subprocess.SubprocessError) as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to launch Gmsh: {str(e)}"
            )
            self.update_output(f"Error launching Gmsh: {e}")

    def build_single_analysis_command(self, subject_id, simulation_name):
        """Build command to run single-subject analysis using the new Analyzer API via subprocess."""
        try:
            project_dir = self.pm.project_dir
            if not project_dir:
                self.update_output("Error: Could not determine project directory")
                return None

            space = "mesh" if self.space_mesh.isChecked() else "voxel"
            analysis_type = (
                "spherical" if self.type_spherical.isChecked() else "cortical"
            )

            if simulation_name == "Select montage...":
                return None

            # Validate m2m directory exists
            m2m_path = self.pm.m2m(subject_id)
            if not m2m_path or not os.path.isdir(m2m_path):
                self.update_output(
                    f"Error: m2m_{subject_id} folder not found at {m2m_path}. Please create the m2m folder first using the Pre-process tab.",
                    "error",
                )
                return None

            # Build output directory using PathManager for overwrite confirmation
            if analysis_type == "spherical":
                x, y, z, radius_val = self._parse_coords_radius()
                coords = [x, y, z]
                coord_space = "MNI" if self.coord_space_mni.isChecked() else "subject"
            else:
                coords = None
                radius_val = None
                coord_space = "subject"

            if analysis_type == "cortical":
                if self.space_mesh.isChecked():
                    atlas_name = self.atlas_name_combo.currentText()
                    atlas_path = None
                else:
                    atlas_name = self.atlas_combo.currentText()
                    atlas_path = self.atlas_combo.currentData()
                    if not atlas_name and not atlas_path:
                        return None

                regions = self._get_regions()
                if not regions:
                    self.update_output(
                        "Error: At least one region is required for cortical analysis."
                    )
                    return None
            else:
                atlas_name = None
                atlas_path = None
                regions = None

            output_dir = self.pm.analysis_output_dir(
                sid=subject_id,
                sim=simulation_name,
                space=space,
                analysis_type=analysis_type,
                tissue_type=self.tissue_combo.currentData(),
                coordinates=coords,
                radius=radius_val,
                coordinate_space=coord_space,
                region=("+".join(regions) if regions else None),
                atlas_name=(atlas_name if analysis_type == "cortical" else None),
                atlas_path=(
                    atlas_path
                    if analysis_type == "cortical" and not self.space_mesh.isChecked()
                    else None
                ),
            )

            if not output_dir:
                return None

            if os.path.exists(output_dir) and not confirm_overwrite(
                self, output_dir, "analysis output directory"
            ):
                return None
            os.makedirs(output_dir, exist_ok=True)

            # Build JSON config for the single-subject analysis
            config = {
                "mode": "single",
                "project_dir": project_dir,
                "subject_id": subject_id,
                "simulation": simulation_name,
                "space": space,
                "tissue_type": self.tissue_combo.currentData(),
                "analysis_type": analysis_type,
                "visualize": True,
                "output_dir": output_dir,
            }

            if analysis_type == "spherical":
                config["center"] = [coords[0], coords[1], coords[2]]
                config["radius"] = radius_val
                config["coordinate_space"] = coord_space
            else:  # cortical
                # For voxel atlas, strip extension to get atlas name for the API
                atlas_for_api = atlas_name
                if atlas_for_api and not self.space_mesh.isChecked():
                    for ext in (".mgz", ".nii.gz", ".nii"):
                        if atlas_for_api.endswith(ext):
                            atlas_for_api = atlas_for_api[: -len(ext)]
                            break
                config["atlas"] = atlas_for_api
                if len(regions) == 1:
                    config["region"] = regions[0]
                else:
                    config["regions"] = regions

            fd, config_path = tempfile.mkstemp(
                suffix=".json", prefix="analysis_config_"
            )
            with os.fdopen(fd, "w") as f:
                json.dump(config, f, indent=2)

            cmd = ["simnibs_python", "-m", "tit.analyzer", config_path]
            return cmd
        except (OSError, ValueError, KeyError):
            return None

    def resizeEvent(self, event):
        """Handle resize events to dynamically adjust input box widths."""
        super().resizeEvent(event)
        self._update_input_widths()

    def _update_input_widths(self):
        """Update maximum widths of input boxes based on container size.

        Note: Many widgets now use QSizePolicy.Expanding, so they will automatically
        expand to fill available space. This method only adjusts widgets that still
        need dynamic width constraints.
        """
        if not hasattr(self, "right_layout_container"):
            return

        # Get the width of the right container (analysis configuration panel)
        container_width = self.right_layout_container.width()

        # If container hasn't been sized yet, use a default calculation
        if container_width <= 0:
            # Estimate based on window size
            window_width = self.width()
            if window_width > 0:
                # Right container is roughly half the window (with margins)
                container_width = max(300, (window_width - 50) // 2)
            else:
                container_width = 400  # Default fallback

        # Calculate dynamic maximum widths as percentages of container width
        # These percentages allow growth while preventing overflow
        # Region input uses Preferred policy, so it will expand up to max
        if hasattr(self, "region_input"):
            # Allow expansion up to a reasonable max based on container size
            max_region_width = max(200, min(300, int(container_width * 0.40)))
            if self.region_input.maximumWidth() != max_region_width:
                self.region_input.setMaximumWidth(max_region_width)
            if hasattr(self, "region_list"):
                self.region_list.setMaximumWidth(max_region_width)

        # Coordinates+radius input uses Preferred policy
        if hasattr(self, "coords_radius_input"):
            coords_max = max(200, min(300, int(container_width * 0.30)))
            if self.coords_radius_input.maximumWidth() != coords_max:
                self.coords_radius_input.setMaximumWidth(coords_max)

        # Buttons use Fixed policy - no dynamic adjustment needed
        # Atlas and Gmsh combo boxes use Expanding policy - they automatically fill space
