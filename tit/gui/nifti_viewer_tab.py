#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 NIfTI Viewer Tab
This module provides a GUI interface for visualizing NIfTI (.nii) files using Freeview.
"""

import os
import sys
import glob
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui

from tit.paths import get_path_manager
from tit.atlas import MNI_ATLAS_DIR, MNI_TEMPLATE, DEFAULT_MNI_ATLAS, VoxelAtlasManager
from tit.gui.style import NIFTI_ATLAS_OPACITY, NIFTI_FIELD_OPACITY
from tit.gui.components.console import ConsoleWidget


class NiftiViewerTab(QtWidgets.QWidget):
    """Tab for NIfTI visualization using Freeview."""

    def __init__(self, parent=None):
        super(NiftiViewerTab, self).__init__(parent)
        self.parent = parent
        self.freeview_process = None
        self.current_file = None
        self.current_files = []
        self.current_paths = []
        self.pm = get_path_manager()
        self.base_dir = self.find_base_dir()
        self.subject_sim_pairs = []  # Store subject-simulation pairs for group mode
        self.visualization_mode = "single"  # "single" or "group"
        self.setup_ui()

    def find_base_dir(self):
        """Find the base directory for data (look for BIDS-format data)."""
        # Get project directory using path manager
        pm = get_path_manager()
        base_dir = pm.project_dir

        return base_dir

    def detect_freesurfer_atlases(self, subject_id):
        """Detect available voxel atlases for a subject.

        Uses the same canonical atlas list as the analyzer and flex tabs.

        Args:
            subject_id: The subject ID without 'sub-' prefix

        Returns:
            List of (display_name, full_path) tuples.
        """
        from tit.atlas import VoxelAtlasManager

        m2m_dir = self.pm.m2m(subject_id)
        mgr = VoxelAtlasManager(
            freesurfer_mri_dir=self.pm.freesurfer_mri(subject_id),
            seg_dir=str(os.path.join(m2m_dir, "segmentation")) if m2m_dir else "",
        )
        return mgr.list_atlases()

    def detect_mni_atlases(self):
        """Detect available MNI atlases in resources/atlas/."""
        return VoxelAtlasManager.detect_mni_atlases(MNI_ATLAS_DIR)

    def detect_voxel_analyses(self, subject_id, simulation_name):
        """Detect available voxel analyses for a subject and simulation.

        Args:
            subject_id: The subject ID without 'sub-' prefix
            simulation_name: Name of the simulation

        Returns:
            List of available region names
        """
        regions = []
        sim_dir = self.pm.simulation(subject_id, simulation_name)
        analyses_dir = os.path.join(sim_dir, "Analyses") if sim_dir else None

        if os.path.isdir(analyses_dir):
            # Look for Voxel analysis directory
            voxel_dir = os.path.join(analyses_dir, "Voxel")
            if os.path.isdir(voxel_dir):
                # Look for region directories
                for region_dir in os.listdir(voxel_dir):
                    region_path = os.path.join(voxel_dir, region_dir)
                    if os.path.isdir(region_path):
                        # Look for NIfTI files directly in the region directory
                        if glob.glob(os.path.join(region_path, "*.nii*")):
                            regions.append(region_dir)

        return sorted(regions)

    def setup_ui(self):
        """Set up the user interface for the NIfTI viewer tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Mode Selector
        mode_section = QtWidgets.QGroupBox("Visualization Mode")
        mode_section.setStyleSheet("QGroupBox { font-weight: bold; }")
        mode_layout = QtWidgets.QHBoxLayout(mode_section)

        self.mode_single_radio = QtWidgets.QRadioButton("Single Subject")
        self.mode_single_radio.setChecked(True)
        self.mode_single_radio.toggled.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_single_radio)

        self.mode_group_radio = QtWidgets.QRadioButton("Group")
        mode_layout.addWidget(self.mode_group_radio)

        mode_layout.addStretch()
        main_layout.addWidget(mode_section)

        # Top section: Configuration
        self.config_section = QtWidgets.QWidget()
        config_layout = QtWidgets.QHBoxLayout(self.config_section)
        config_layout.setSpacing(15)

        # Left side: Subject Configuration
        subject_block = QtWidgets.QGroupBox("Subject Configuration")
        subject_block.setStyleSheet("QGroupBox { font-weight: bold; }")
        subject_block_layout = QtWidgets.QGridLayout(subject_block)
        subject_block_layout.setSpacing(8)

        # Subject selection with status
        subject_block_layout.addWidget(QtWidgets.QLabel("Subject:"), 0, 0)
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.setMinimumWidth(120)
        subject_block_layout.addWidget(self.subject_combo, 0, 1)
        self.status_label = QtWidgets.QLabel("Ready")
        subject_block_layout.addWidget(self.status_label, 0, 2)

        # Space selection - hidden in single subject mode, but keep the widget for compatibility
        self.space_combo = QtWidgets.QComboBox()
        self.space_combo.addItems(["Subject", "MNI"])
        self.space_combo.setCurrentText("Subject")
        self.space_combo.setVisible(False)  # Hide in single subject mode

        # Atlas selection
        subject_block_layout.addWidget(QtWidgets.QLabel("Atlas:"), 1, 0)
        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.setEnabled(False)
        subject_block_layout.addWidget(self.atlas_combo, 1, 1, 1, 2)

        # Atlas controls
        atlas_controls = QtWidgets.QHBoxLayout()
        self.atlas_visibility_chk = QtWidgets.QCheckBox("Visible")
        self.atlas_visibility_chk.setChecked(True)
        self.atlas_visibility_chk.setEnabled(False)
        atlas_controls.addWidget(self.atlas_visibility_chk)
        subject_block_layout.addLayout(atlas_controls, 2, 0, 1, 3)

        config_layout.addWidget(subject_block)

        # Right side: Simulation Configuration
        sim_block = QtWidgets.QGroupBox("Simulation Configuration")
        sim_block.setStyleSheet("QGroupBox { font-weight: bold; }")
        sim_block_layout = QtWidgets.QGridLayout(sim_block)
        sim_block_layout.setSpacing(8)

        # Simulation selection
        sim_block_layout.addWidget(QtWidgets.QLabel("Simulation:"), 0, 0)
        self.sim_combo = QtWidgets.QComboBox()
        self.sim_combo.setMinimumWidth(200)
        sim_block_layout.addWidget(self.sim_combo, 0, 1, 1, 3)

        # Analysis selection
        sim_block_layout.addWidget(QtWidgets.QLabel("Analysis Region:"), 1, 0)
        self.analysis_region_combo = QtWidgets.QComboBox()
        self.analysis_region_combo.setEnabled(False)
        sim_block_layout.addWidget(self.analysis_region_combo, 1, 1, 1, 3)

        # Analysis controls in a horizontal layout
        analysis_controls = QtWidgets.QHBoxLayout()
        self.analysis_visibility_chk = QtWidgets.QCheckBox("Visible")
        self.analysis_visibility_chk.setChecked(True)
        self.analysis_visibility_chk.setEnabled(False)
        analysis_controls.addWidget(self.analysis_visibility_chk)

        analysis_controls.addWidget(QtWidgets.QLabel("Opacity:"))
        self.analysis_opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.analysis_opacity_slider.setRange(0, 100)
        self.analysis_opacity_slider.setValue(NIFTI_FIELD_OPACITY)
        self.analysis_opacity_slider.setEnabled(False)
        analysis_controls.addWidget(self.analysis_opacity_slider)
        self.analysis_opacity_label = QtWidgets.QLabel("0.70")
        analysis_controls.addWidget(self.analysis_opacity_label)
        self.analysis_opacity_slider.valueChanged.connect(
            lambda v: self.analysis_opacity_label.setText(f"{v/100:.2f}")
        )
        sim_block_layout.addLayout(analysis_controls, 2, 0, 1, 4)

        # Add some spacing
        spacer = QtWidgets.QSpacerItem(
            20, 10, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )
        sim_block_layout.addItem(spacer, 3, 0, 1, 4)

        # High frequency fields checkbox
        self.high_freq_chk = QtWidgets.QCheckBox("Load High Frequency Fields")
        self.high_freq_chk.setChecked(False)
        sim_block_layout.addWidget(self.high_freq_chk, 4, 0, 1, 4)

        # Refresh button
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_subjects)
        sim_block_layout.addWidget(self.refresh_btn, 5, 0, 1, 4)

        config_layout.addWidget(sim_block)
        main_layout.addWidget(self.config_section)

        # Group Mode Configuration (initially hidden)
        self.group_section = QtWidgets.QGroupBox("Group Configuration")
        self.group_section.setStyleSheet("QGroupBox { font-weight: bold; }")
        self.group_section.setVisible(False)
        group_layout = QtWidgets.QVBoxLayout(self.group_section)

        # Subject-Simulation Pairs List
        pairs_label = QtWidgets.QLabel("Subject-Simulation Pairs:")
        pairs_label.setStyleSheet("font-weight: bold;")
        group_layout.addWidget(pairs_label)

        # Table for pairs
        self.pairs_table = QtWidgets.QTableWidget()
        self.pairs_table.setColumnCount(3)
        self.pairs_table.setHorizontalHeaderLabels(["Subject", "Simulation", ""])
        self.pairs_table.horizontalHeader().setStretchLastSection(False)
        self.pairs_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self.pairs_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        self.pairs_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Fixed
        )
        self.pairs_table.setColumnWidth(2, 50)
        self.pairs_table.setMaximumHeight(200)
        group_layout.addWidget(self.pairs_table)

        # Buttons for managing pairs
        pair_buttons_layout = QtWidgets.QHBoxLayout()

        self.add_pair_btn = QtWidgets.QPushButton("+ Add Pair")
        self.add_pair_btn.clicked.connect(self.add_pair_row)
        pair_buttons_layout.addWidget(self.add_pair_btn)

        self.quick_add_btn = QtWidgets.QPushButton("Quick Add")
        self.quick_add_btn.setToolTip(
            "Add the same simulation to multiple subjects at once"
        )
        self.quick_add_btn.clicked.connect(self.quick_add_pairs)
        pair_buttons_layout.addWidget(self.quick_add_btn)

        self.clear_pairs_btn = QtWidgets.QPushButton("Clear All")
        self.clear_pairs_btn.clicked.connect(self.clear_all_pairs)
        pair_buttons_layout.addWidget(self.clear_pairs_btn)

        pair_buttons_layout.addStretch()
        group_layout.addLayout(pair_buttons_layout)

        # MNI Atlas Selection for Group Mode
        group_atlas_layout = QtWidgets.QHBoxLayout()
        group_atlas_layout.addWidget(QtWidgets.QLabel("MNI Atlas:"))
        self.group_atlas_combo = QtWidgets.QComboBox()
        group_atlas_layout.addWidget(self.group_atlas_combo)

        self.group_atlas_visibility_chk = QtWidgets.QCheckBox("Visible")
        self.group_atlas_visibility_chk.setChecked(True)
        group_atlas_layout.addWidget(self.group_atlas_visibility_chk)

        group_layout.addLayout(group_atlas_layout)

        main_layout.addWidget(self.group_section)

        # Visualization Options
        vis_group = QtWidgets.QGroupBox("Visualization Options")
        vis_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        vis_layout = QtWidgets.QHBoxLayout(vis_group)
        vis_layout.setSpacing(8)

        # Colormap
        vis_layout.addWidget(QtWidgets.QLabel("Colormap:"))
        self.colormap_combo = QtWidgets.QComboBox()
        self.colormap_combo.addItems(
            ["grayscale", "heat", "jet", "gecolor", "nih", "surface"]
        )
        self.colormap_combo.setCurrentText("heat")
        vis_layout.addWidget(self.colormap_combo)

        # Opacity
        vis_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(NIFTI_FIELD_OPACITY)
        vis_layout.addWidget(self.opacity_slider)
        self.opacity_label = QtWidgets.QLabel("0.70")
        vis_layout.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v/100:.2f}")
        )

        # Percentile Mode
        self.percentile_chk = QtWidgets.QCheckBox("Percentile Mode")
        self.percentile_chk.setChecked(True)
        vis_layout.addWidget(self.percentile_chk)

        # Thresholds
        vis_layout.addWidget(QtWidgets.QLabel("Threshold (%):"))
        self.min_threshold = QtWidgets.QDoubleSpinBox()
        self.min_threshold.setRange(0, 100)
        self.min_threshold.setValue(95)
        self.min_threshold.setDecimals(1)
        vis_layout.addWidget(self.min_threshold)
        vis_layout.addWidget(QtWidgets.QLabel("to"))
        self.max_threshold = QtWidgets.QDoubleSpinBox()
        self.max_threshold.setRange(0, 100)
        self.max_threshold.setValue(99.9)
        self.max_threshold.setDecimals(1)
        vis_layout.addWidget(self.max_threshold)

        # Visibility
        self.visibility_chk = QtWidgets.QCheckBox("Visible")
        self.visibility_chk.setChecked(True)
        vis_layout.addWidget(self.visibility_chk)

        main_layout.addWidget(vis_group)

        # Action Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)

        self.load_btn = QtWidgets.QPushButton("Load Subject Data")
        self.load_btn.clicked.connect(self.load_subject_data)
        button_layout.addWidget(self.load_btn)

        load_additional_btn = QtWidgets.QPushButton("Load Additional NIfTIs")
        load_additional_btn.clicked.connect(self.load_custom_nifti)
        button_layout.addWidget(load_additional_btn)

        reload_btn = QtWidgets.QPushButton("Reload Current View")
        reload_btn.clicked.connect(self.reload_current_view)
        button_layout.addWidget(reload_btn)

        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        # Console
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            console_label=None,
        )
        main_layout.addWidget(self.console_widget)

        # Connect signals
        self.subject_combo.currentIndexChanged.connect(self.on_subject_changed)
        self.sim_combo.currentIndexChanged.connect(self.update_available_analyses)
        self.space_combo.currentIndexChanged.connect(
            self.update_space_dependent_controls
        )

        # Initial refresh
        self.refresh_subjects()

        # Load MNI atlases for group mode
        self.load_mni_atlases()

    def refresh_subjects(self):
        """Scan for available subjects and update the dropdown."""
        self.subject_combo.clear()

        simnibs_dir = self.pm.simnibs()

        subject_dirs = [
            d
            for d in os.listdir(simnibs_dir)
            if os.path.isdir(os.path.join(simnibs_dir, d)) and d.startswith("sub-")
        ]

        subject_ids = sorted(d[4:] for d in subject_dirs)
        self.subject_combo.addItems(subject_ids)
        self.status_label.setText(f"Found {len(subject_dirs)} subjects")
        self.subject_combo.setCurrentIndex(0)
        self.check_freesurfer_atlases()

    def check_freesurfer_atlases(self):
        """Check for available Freesurfer atlases for the current subject."""

        subject_id = self.subject_combo.currentText()
        available_atlases = self.detect_freesurfer_atlases(subject_id)

        self.atlas_combo.clear()
        has_atlases = bool(available_atlases)
        self.atlas_combo.setEnabled(has_atlases)
        self.atlas_visibility_chk.setEnabled(has_atlases)

        for display_name, full_path in available_atlases:
            self.atlas_combo.addItem(display_name, full_path)

        labeling_idx = self.atlas_combo.findText("labeling.nii.gz")
        if labeling_idx >= 0:
            self.atlas_combo.setCurrentIndex(labeling_idx)

    def refresh_simulations(self):
        """Populate the simulation combo box for the selected subject."""
        self.sim_combo.clear()

        subject_id = self.subject_combo.currentText()
        simulations = self.pm.list_simulations(subject_id)

        # Add simulations to combo box
        for sim_name in simulations:
            self.sim_combo.addItem(sim_name)

        # If simulations were found, select the first one and update analyses
        if self.sim_combo.count() > 0:
            self.sim_combo.setCurrentIndex(0)
            self.update_available_analyses()

    def update_available_analyses(self):
        """Update the available analyses based on the selected simulation."""
        self.analysis_region_combo.clear()

        # Disable analysis controls by default
        self.analysis_region_combo.setEnabled(False)
        self.analysis_visibility_chk.setEnabled(False)
        self.analysis_opacity_slider.setEnabled(False)

        # Only enable analysis in Subject space
        if self.space_combo.currentText() != "Subject":
            return

        # Get selected subject and simulation
        if self.subject_combo.count() == 0 or not self.sim_combo.currentText():
            return

        subject_id = self.subject_combo.currentText()
        simulation_name = self.sim_combo.currentText()

        # Detect available analyses
        regions = self.detect_voxel_analyses(subject_id, simulation_name)

        if not regions:
            return

        self.analysis_region_combo.setEnabled(True)
        self.analysis_visibility_chk.setEnabled(True)
        self.analysis_opacity_slider.setEnabled(True)
        self.analysis_region_combo.addItems(regions)

    def on_mode_changed(self):
        """Handle mode change between Single Subject and Group."""
        is_single = self.mode_single_radio.isChecked()
        self.visualization_mode = "single" if is_single else "group"
        self.config_section.setVisible(is_single)
        self.group_section.setVisible(not is_single)
        self.space_combo.setCurrentText("Subject" if is_single else "MNI")

    def load_mni_atlases(self):
        """Load available MNI atlases into the group atlas combo."""
        default_idx = 0
        for atlas_path in self.detect_mni_atlases():
            atlas_name = os.path.basename(atlas_path)
            self.group_atlas_combo.addItem(atlas_name, atlas_path)
            if atlas_name == DEFAULT_MNI_ATLAS:
                default_idx = self.group_atlas_combo.count() - 1

        if self.group_atlas_combo.count() > 0:
            self.group_atlas_combo.setCurrentIndex(default_idx)

    def get_simulations_for_subject(self, subject_id):
        """Get list of available simulations for a subject."""
        return self.pm.list_simulations(subject_id)

    def add_pair_row(self):
        """Add a new row for subject-simulation pair selection."""
        row = self.pairs_table.rowCount()
        self.pairs_table.insertRow(row)

        # Subject combo
        subject_combo = QtWidgets.QComboBox()
        subjects = self.pm.list_simnibs_subjects()
        subject_combo.addItems(subjects)
        subject_combo.currentTextChanged.connect(
            lambda: self.update_sim_combo_in_row(row)
        )
        self.pairs_table.setCellWidget(row, 0, subject_combo)

        # Simulation combo
        sim_combo = QtWidgets.QComboBox()
        if subjects:
            sims = self.get_simulations_for_subject(subjects[0])
            sim_combo.addItems(sims)
        self.pairs_table.setCellWidget(row, 1, sim_combo)

        # Remove button
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setMaximumWidth(40)
        remove_btn.clicked.connect(lambda: self.remove_pair(row))
        self.pairs_table.setCellWidget(row, 2, remove_btn)

    def update_sim_combo_in_row(self, row):
        """Update the simulation combo box when subject changes in a row."""
        subject_combo = self.pairs_table.cellWidget(row, 0)
        sim_combo = self.pairs_table.cellWidget(row, 1)

        if subject_combo and sim_combo:
            subject_id = subject_combo.currentText()
            if subject_id:
                sims = self.get_simulations_for_subject(subject_id)
                sim_combo.clear()
                sim_combo.addItems(sims)

    def remove_pair(self, row):
        """Remove a subject-simulation pair row."""
        self.pairs_table.removeRow(row)

    def clear_all_pairs(self):
        """Clear all subject-simulation pairs."""
        self.pairs_table.setRowCount(0)

    def quick_add_pairs(self):
        """Open dialog to quickly add the same simulation to multiple subjects."""
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
        subjects = self.pm.list_simnibs_subjects()
        for subject in subjects:
            all_sims.update(self.get_simulations_for_subject(subject))
        sim_combo.addItems(sorted(all_sims))
        sim_layout.addWidget(sim_combo)
        layout.addLayout(sim_layout)

        # Subject list
        layout.addWidget(QtWidgets.QLabel("Select Subjects:"))
        subject_list = QtWidgets.QListWidget()
        subject_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        all_subjects = self.pm.list_simnibs_subjects()
        for subject in all_subjects:
            subject_list.addItem(subject)

        layout.addWidget(subject_list)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add Pairs")
        cancel_btn = QtWidgets.QPushButton("Cancel")

        add_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addWidget(add_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_simulation = sim_combo.currentText()
            selected_items = subject_list.selectedItems()

            if not selected_items:
                QtWidgets.QMessageBox.warning(
                    self, "Warning", "Please select at least one subject"
                )
                return

            # Add pairs for each selected subject
            added_count = 0
            for item in selected_items:
                subject_id = item.text()

                # Check if this subject has the selected simulation
                available_sims = self.get_simulations_for_subject(subject_id)
                if selected_simulation not in available_sims:
                    self.console_widget.update_console(
                        f"Warning: Subject {subject_id} does not have simulation {selected_simulation}",
                        "warning",
                    )
                    continue

                # Check for duplicates
                is_duplicate = any(
                    self.pairs_table.cellWidget(row, 0).currentText() == subject_id
                    and self.pairs_table.cellWidget(row, 1).currentText()
                    == selected_simulation
                    for row in range(self.pairs_table.rowCount())
                )
                if is_duplicate:
                    continue

                # Add new row
                row = self.pairs_table.rowCount()
                self.pairs_table.insertRow(row)

                # Subject combo
                subject_combo_widget = QtWidgets.QComboBox()
                subject_combo_widget.addItems(all_subjects)
                subject_combo_widget.setCurrentText(subject_id)
                subject_combo_widget.currentTextChanged.connect(
                    lambda: self.update_sim_combo_in_row(row)
                )
                self.pairs_table.setCellWidget(row, 0, subject_combo_widget)

                # Simulation combo
                sim_combo_widget = QtWidgets.QComboBox()
                sim_combo_widget.addItems(available_sims)
                sim_combo_widget.setCurrentText(selected_simulation)
                self.pairs_table.setCellWidget(row, 1, sim_combo_widget)

                # Remove button
                remove_btn = QtWidgets.QPushButton("✕")
                remove_btn.setMaximumWidth(40)
                remove_btn.clicked.connect(lambda checked, r=row: self.remove_pair(r))
                self.pairs_table.setCellWidget(row, 2, remove_btn)

                added_count += 1

            self.console_widget.update_console(
                f"Added {added_count} subject-simulation pairs", "success"
            )

    def load_group_data(self):
        """Load group visualization with multiple subject-simulation pairs."""
        self.console_widget.clear_console()

        # Get all pairs from the table
        pairs = []
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)

            if subject_combo and sim_combo:
                subject_id = subject_combo.currentText()
                simulation_name = sim_combo.currentText()

                if subject_id and simulation_name:
                    pairs.append({"subject": subject_id, "simulation": simulation_name})

        if not pairs:
            QtWidgets.QMessageBox.warning(
                self, "Warning", "Please add at least one subject-simulation pair"
            )
            return

        file_specs = []

        # Add MNI template as base layer
        mni_template = os.path.join(MNI_ATLAS_DIR, MNI_TEMPLATE)
        if os.path.exists(mni_template):
            file_specs.append(
                {
                    "path": mni_template,
                    "type": "volume",
                    "visible": 1,
                    "colormap": "grayscale",
                }
            )

        # Add MNI atlas
        atlas_path = self.group_atlas_combo.currentData()
        if atlas_path and os.path.exists(atlas_path):
            atlas_name = os.path.basename(atlas_path)
            atlas_spec = {
                "path": atlas_path,
                "type": "volume",
                "visible": int(self.group_atlas_visibility_chk.isChecked()),
                "colormap": "lut",
                "opacity": NIFTI_ATLAS_OPACITY / 100.0,
            }

            # Add lookup table if a matching .txt or _labels.txt exists
            stem = atlas_path.replace(".nii.gz", "")
            lut_path = next(
                (
                    p
                    for p in [
                        stem + ".txt",
                        stem + "_labels.txt",
                        os.path.join(
                            os.path.dirname(atlas_path),
                            os.path.basename(stem).split("-")[0] + "_labels.txt",
                        ),
                    ]
                    if os.path.exists(p)
                ),
                None,
            )
            if lut_path:
                atlas_spec["lut_file"] = lut_path

            self.console_widget.update_console(
                f"Loading MNI atlas: {atlas_name}", "info"
            )
            file_specs.append(atlas_spec)

        # Add simulation files for each pair
        opacity = self.opacity_slider.value() / 100.0
        adjusted_opacity = opacity * (1.0 / (1 + len(pairs) * 0.1))

        for pair in pairs:
            subject_id = pair["subject"]
            simulation_name = pair["simulation"]

            # Find the MNI nifti directory for this pair
            sim_dir = self.pm.simulation(subject_id, simulation_name)
            if not sim_dir:
                self.console_widget.update_console(
                    f"Simulation not found: sub-{subject_id}/{simulation_name}",
                    "warning",
                )
                continue

            nifti_dir = next(
                (
                    d
                    for d in [
                        os.path.join(sim_dir, "mTI", "niftis"),
                        os.path.join(sim_dir, "TI", "niftis"),
                    ]
                    if os.path.exists(d)
                ),
                None,
            )
            if not nifti_dir:
                self.console_widget.update_console(
                    f"No NIfTI dir for sub-{subject_id}/{simulation_name}", "warning"
                )
                continue

            for nifti_file in glob.glob(os.path.join(nifti_dir, "*.nii*")):
                basename = os.path.basename(nifti_file)

                if "_MNI" not in basename:
                    continue
                if (
                    "TI_max" not in basename and "TI_Max" not in basename
                ) or "TDCS" in basename:
                    continue
                if "grey_" not in basename:
                    continue

                file_specs.append(
                    self._vis_options(nifti_file, opacity=adjusted_opacity)
                )
                self.console_widget.update_console(
                    f"Loading: sub-{subject_id}/{simulation_name} - {basename}", "info"
                )

        self.launch_freeview_with_files(file_specs)

    def load_subject_data(self):
        """Load the selected subject's data in Freeview."""
        # Route to appropriate loading function based on mode
        if self.visualization_mode == "group":
            self.load_group_data()
            return

        # Single subject mode
        self.console_widget.clear_console()
        if self.subject_combo.count() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "No subjects available")
            return

        subject_id = self.subject_combo.currentText()
        is_mni_space = self.space_combo.currentText() == "MNI"
        simulation_name = self.sim_combo.currentText()

        if not simulation_name:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a simulation")
            return

        # Get paths using path manager
        subject_dir = self.pm.sub(subject_id)
        m2m_dir = self.pm.m2m(subject_id)
        simulations_dir = (
            os.path.join(subject_dir, "Simulations") if subject_dir else None
        )

        file_specs = []

        # Add T1 image based on selected space
        t1_name = f"T1_{subject_id}_MNI.nii.gz" if is_mni_space else "T1.nii.gz"
        t1_file = os.path.join(m2m_dir, t1_name)
        if os.path.exists(t1_file):
            file_specs.append(
                {
                    "path": t1_file,
                    "type": "volume",
                    "visible": 1,
                    "colormap": "grayscale",
                }
            )

        # Add atlas if selected and available
        atlas_file = (
            self.atlas_combo.currentData() if self.atlas_combo.isEnabled() else None
        )
        if atlas_file and os.path.exists(atlas_file):
            file_specs.append(
                {
                    "path": atlas_file,
                    "type": "volume",
                    "visible": int(self.atlas_visibility_chk.isChecked()),
                    "colormap": "lut",
                    "opacity": NIFTI_ATLAS_OPACITY / 100.0,
                }
            )
            self.console_widget.update_console(
                f"Loading atlas: {self.atlas_combo.currentText()}", "info"
            )

        # Add voxel analysis if selected and available
        self._load_analysis_overlay(file_specs, subject_id, simulation_name)

        # Add simulation results — prefer mTI over TI
        sim_dir = os.path.join(simulations_dir, simulation_name)
        nifti_dir = next(
            (
                d
                for d in [
                    os.path.join(sim_dir, "mTI", "niftis"),
                    os.path.join(sim_dir, "TI", "niftis"),
                ]
                if os.path.exists(d)
            ),
            None,
        )

        if nifti_dir:
            for nifti_file in glob.glob(os.path.join(nifti_dir, "*.nii*")):
                basename = os.path.basename(nifti_file)

                if (
                    "TI_max" not in basename and "TI_Max" not in basename
                ) or "TDCS" in basename:
                    continue
                if is_mni_space != ("_MNI" in basename):
                    continue

                vis = int(self.visibility_chk.isChecked()) if "grey_" in basename else 0
                file_specs.append(self._vis_options(nifti_file, visible=vis))

            # Load high frequency fields if requested
            if self.high_freq_chk.isChecked():
                high_freq_dir = os.path.join(sim_dir, "high_Frequency", "niftis")
                if not os.path.exists(high_freq_dir):
                    self.console_widget.update_console(
                        f"Warning: High frequency directory not found at {high_freq_dir}",
                        "warning",
                    )
                else:
                    for nifti_file in glob.glob(
                        os.path.join(high_freq_dir, "*_scalar_magnE.nii.gz")
                    ):
                        file_specs.append(
                            self._vis_options(
                                nifti_file,
                                opacity=self.opacity_slider.value() / 100.0 * 0.8,
                            )
                        )
                        self.console_widget.update_console(
                            f"Loading high frequency field: {os.path.basename(nifti_file)}",
                            "info",
                        )

        if not any(
            spec for spec in file_specs if spec["path"].endswith((".nii", ".nii.gz"))
        ):
            QtWidgets.QMessageBox.warning(
                self,
                "Warning",
                f"No NIfTI files found for the selected simulation(s) in {'MNI' if is_mni_space else 'Subject'} space",
            )
            return

        # Launch Freeview with the files
        self.launch_freeview_with_files(file_specs)

    def load_custom_nifti(self):
        """Open a file dialog to select a custom NIfTI file."""
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Load NIfTI Files", "", "NIfTI Files (*.nii *.nii.gz);;All Files (*)"
        )

        if not filenames:
            return

        file_specs = [self._vis_options(fname) for fname in filenames]
        self.launch_freeview_with_files(file_specs, filenames)

    def launch_freeview_with_files(self, file_specs, file_paths=[]):
        """Launch Freeview with multiple files.

        Args:
            file_specs: List of file specifications with options for Freeview
            file_paths: Optional list of original file paths (without options) for display
        """
        if not file_specs:
            return

        try:
            # Close any existing Freeview process
            if self.freeview_process is not None:
                self.terminate_freeview()

            # Store the current files for potential reload
            self.current_files = file_specs
            self.current_paths = (
                file_paths
                if file_paths
                else [spec["path"] for spec in file_specs if isinstance(spec, dict)]
            )

            # Construct the command arguments
            freeview_args = []
            for spec in file_specs:
                if not isinstance(spec, dict):
                    freeview_args.append(spec)
                    continue

                arg = spec["path"]
                for key in ("colormap", "lut_file", "opacity", "visible"):
                    if key in spec:
                        fv_key = "lut" if key == "lut_file" else key
                        arg += f":{fv_key}={spec[key]}"

                if spec.get("percentile"):
                    arg += ":percentile=1"
                    if "threshold_min" in spec and "threshold_max" in spec:
                        arg += f":heatscale={spec['threshold_min']},{spec['threshold_max']}"

                freeview_args.append(arg)

            # Construct the command
            base_command = ["freeview"] + freeview_args

            # Launch Freeview
            self.freeview_process = subprocess.Popen(
                base_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            # Update UI
            self.status_label.setText(f"Viewing {len(freeview_args)} files")

            # Update console with file details
            self.console_widget.clear_console()
            self.console_widget.update_console("Currently viewing:", "info")

            # Use original paths for display
            for i, file_path in enumerate(self.current_paths):
                try:
                    file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
                    basename = os.path.basename(file_path)
                    self.console_widget.update_console(
                        f"{i+1}. {basename} ({file_size:.2f} MB)"
                    )
                except (OSError, ValueError) as e:
                    # If there's an error getting file size (e.g., due to options in the path)
                    basename = os.path.basename(file_path.split(":")[0])
                    self.console_widget.update_console(f"{i+1}. {basename}")

            self.console_widget.update_console(
                "Freeview is now running. Use its interface to navigate the volumes.",
                "success",
            )

        except (OSError, subprocess.SubprocessError) as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to launch Freeview: {str(e)}"
            )

    def _load_analysis_overlay(self, file_specs, subject_id, simulation_name):
        """Add voxel analysis overlay to file_specs if selected."""
        if (
            not self.analysis_region_combo.isEnabled()
            or not self.analysis_region_combo.currentText()
        ):
            return

        region_name = self.analysis_region_combo.currentText()
        sim_dir = self.pm.simulation(subject_id, simulation_name)
        if not sim_dir:
            return

        analysis_dir = os.path.join(
            self.pm.analysis_dir(subject_id, simulation_name, "voxel"),
            region_name,
        )
        if not os.path.exists(analysis_dir):
            self.console_widget.update_console(
                f"Warning: Analysis directory not found at {analysis_dir}", "warning"
            )
            return

        # Try specific ROI file, then fall back to first NIfTI
        roi_file = os.path.join(analysis_dir, f"brain_with_{region_name}_ROI.nii.gz")
        if not os.path.exists(roi_file):
            nifti_files = glob.glob(os.path.join(analysis_dir, "*.nii*"))
            roi_file = nifti_files[0] if nifti_files else None

        if not roi_file or not os.path.exists(roi_file):
            self.console_widget.update_console(
                f"Warning: No analysis file found for region {region_name}", "warning"
            )
            return

        file_specs.append(
            {
                "path": roi_file,
                "type": "volume",
                "visible": int(self.analysis_visibility_chk.isChecked()),
                "colormap": "jet",
                "opacity": self.analysis_opacity_slider.value() / 100.0,
            }
        )
        self.console_widget.update_console(
            f"Loading voxel analysis: {os.path.basename(roi_file)}", "info"
        )

    def reload_current_view(self):
        """Reload the current view in Freeview."""
        if self.current_files:
            self.launch_freeview_with_files(self.current_files, self.current_paths)
        else:
            QtWidgets.QMessageBox.warning(self, "Warning", "No files currently loaded")

    def terminate_freeview(self):
        """Terminate the Freeview process."""
        if self.freeview_process is not None and self.freeview_process.poll() is None:
            try:
                self.freeview_process.terminate()
                self.freeview_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.freeview_process.kill()
            self.freeview_process = None

    def closeEvent(self, event):
        """Handle tab close event."""
        self.terminate_freeview()
        super(NiftiViewerTab, self).closeEvent(event)

    def on_subject_changed(self):
        """Handle subject selection changes."""
        self.check_freesurfer_atlases()
        self.refresh_simulations()

    def _vis_options(self, path, **overrides):
        """Build a file spec dict from the current visualization controls.

        Returns a dict with path, type, colormap, opacity, visible, percentile,
        and threshold values. Pass keyword overrides to replace any field.
        """
        spec = {
            "path": path,
            "type": "volume",
            "colormap": self.colormap_combo.currentText(),
            "opacity": self.opacity_slider.value() / 100.0,
            "visible": int(self.visibility_chk.isChecked()),
            "percentile": int(self.percentile_chk.isChecked()),
            "threshold_min": self.min_threshold.value(),
            "threshold_max": self.max_threshold.value(),
        }
        spec.update(overrides)
        return spec

    def update_space_dependent_controls(self):
        """Update controls that depend on the selected space."""
        is_subject_space = self.space_combo.currentText() == "Subject"

        for widget in (
            self.analysis_region_combo,
            self.analysis_visibility_chk,
            self.analysis_opacity_slider,
            self.atlas_combo,
            self.atlas_visibility_chk,
        ):
            widget.setEnabled(is_subject_space)

        if not is_subject_space:
            self.console_widget.update_console(
                "Note: analysis option is only available in Subject space", "info"
            )
