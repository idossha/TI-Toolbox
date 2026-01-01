#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: Nilearn Visuals
Create Nilearn visualizations for high-quality images.
"""

# Standard library imports
import os
import traceback
from datetime import datetime
from pathlib import Path

# Third-party imports
import nibabel as nib
import numpy as np
from nilearn import datasets
from PyQt5 import QtWidgets, QtCore

from tit.core import get_path_manager
from tit.core.nifti import load_group_data_ti_toolbox
from tit.plotting.nilearn.img_slices import create_pdf_entry_point_group
from tit.plotting.nilearn.img_glass import create_glass_brain_entry_point_group
from tit.gui.components.console import ConsoleWidget
from tit.gui.components.action_buttons import RunStopButtons

# Extension metadata (required)
EXTENSION_NAME = "Nilearn Visuals"
EXTENSION_DESCRIPTION = "Create Nilearn high resolution visualizations."


class PublicationImageWorker(QtCore.QThread):
    """Worker thread for running nilearn slices image generation."""
    output_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(int)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, subject_simulation_pairs, min_cutoff, max_cutoff, atlas_name, selected_regions=None, subdir_name="nilearn_visuals", use_percentiles=False, create_glass_brain=False, glass_brain_cmap='hot'):
        super().__init__()
        self.subject_simulation_pairs = subject_simulation_pairs  # List of dicts with 'subject_id' and 'simulation_name'
        self.min_cutoff = min_cutoff
        self.max_cutoff = max_cutoff
        self.atlas_name = atlas_name
        self.selected_regions = selected_regions
        self.subdir_name = subdir_name
        self.use_percentiles = use_percentiles
        self.create_glass_brain = create_glass_brain
        self.glass_brain_cmap = glass_brain_cmap

    def run(self):
        try:
            # Define output callback to emit signals
            def output_callback(text):
                self.output_signal.emit(text)

            # Prepare subject configs for averaging
            subject_configs = []
            for pair in self.subject_simulation_pairs:
                subject_configs.append({
                    'subject_id': pair['subject_id'],
                    'simulation_name': pair['simulation_name']
                })

            self.output_signal.emit(f"\nProcessing {len(subject_configs)} subject-simulation pairs")
            self.output_signal.emit(f"Cutoff range: {self.min_cutoff:.2f} - {self.max_cutoff:.2f} V/m, Atlas: {self.atlas_name}")

            # Load and average the data using core/nifti.py
            self.output_signal.emit("Loading and averaging NIfTI data...")
            try:
                data_4d, template_img, subject_ids = load_group_data_ti_toolbox(
                    subject_configs,
                    nifti_file_pattern="grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
                    dtype=float
                )

                # Compute mean across subjects
                averaged_data = np.mean(data_4d, axis=-1)

                # Create averaged NIfTI image
                averaged_img = nib.Nifti1Image(averaged_data, template_img.affine, template_img.header)

                self.output_signal.emit(f"Successfully loaded and averaged data from {len(subject_ids)} subjects")

                # Convert percentiles to absolute values if needed
                actual_min_cutoff = self.min_cutoff
                actual_max_cutoff = self.max_cutoff

                if self.use_percentiles:
                    # Calculate percentiles from the averaged data
                    data_nonzero = averaged_data[averaged_data > 0]
                    if len(data_nonzero) == 0:
                        self.error_signal.emit("No non-zero field values found for percentile calculation")
                        return

                    actual_min_cutoff = np.percentile(data_nonzero, self.min_cutoff)
                    actual_max_cutoff = np.percentile(data_nonzero, self.max_cutoff)

                    self.output_signal.emit("Converted percentiles to absolute values:")
                    self.output_signal.emit(f"  {self.min_cutoff:.1f}% → {actual_min_cutoff:.2f} V/m (min cutoff)")
                    self.output_signal.emit(f"  {self.max_cutoff:.1f}% → {actual_max_cutoff:.2f} V/m (max cutoff)")

            except Exception as e:
                self.error_signal.emit(f"Failed to load/average NIfTI data: {str(e)}")
                return

            # Create output directory: derivatives/ti-toolbox/[subdir_name]/
            pm = get_path_manager()
            project_dir = pm.project_dir

            output_base_dir = os.path.join(project_dir, "derivatives", "ti-toolbox", "nilearn_visuals", self.subdir_name)
            os.makedirs(output_base_dir, exist_ok=True)

            # Generate base filename without timestamp
            base_filename = f"group_averaged_{len(subject_ids)}_subjects"

            # Save averaged NIfTI file
            nifti_filename = f"{base_filename}.nii.gz"
            nifti_filepath = os.path.join(output_base_dir, nifti_filename)
            nib.save(averaged_img, nifti_filepath)
            self.output_signal.emit(f"Saved averaged NIfTI: {nifti_filepath}")

            # Save parameters .txt file
            txt_filename = f"{base_filename}_parameters.txt"
            txt_filepath = os.path.join(output_base_dir, txt_filename)

            with open(txt_filepath, 'w') as f:
                f.write("TI-Toolbox Publication Visuals - Group Averaged Data\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("SUBJECTS AND SIMULATIONS:\n")
                f.write("-" * 30 + "\n")
                for i, config in enumerate(subject_configs, 1):
                    f.write(f"{i}. Subject: {config['subject_id']}, Simulation: {config['simulation_name']}\n")
                f.write("\n")
                f.write("PARAMETERS:\n")
                f.write("-" * 12 + "\n")
                if self.use_percentiles:
                    f.write(f"Minimum Cutoff: {self.min_cutoff:.1f}% ({actual_min_cutoff:.2f} V/m)\n")
                    f.write(f"Maximum Cutoff: {self.max_cutoff:.1f}% ({actual_max_cutoff:.2f} V/m)\n")
                else:
                    f.write(f"Minimum Cutoff: {self.min_cutoff:.2f} V/m\n")
                    f.write(f"Maximum Cutoff: {self.max_cutoff:.2f} V/m\n")
                f.write(f"Atlas: {self.atlas_name}\n")

                # Add max value and percentile info
                max_value = np.max(averaged_data)
                f.write(f"Data Maximum: {max_value:.2f} V/m\n")

                # Add percentile information
                data_nonzero = averaged_data[averaged_data > 0]
                if len(data_nonzero) > 0:
                    # Show some key percentiles
                    p50 = np.percentile(data_nonzero, 50)
                    p75 = np.percentile(data_nonzero, 75)
                    p90 = np.percentile(data_nonzero, 90)
                    p95 = np.percentile(data_nonzero, 95)
                    p99 = np.percentile(data_nonzero, 99)
                    f.write(f"Data Percentiles: 50th={p50:.2f}, 75th={p75:.2f}, 90th={p90:.2f}, 95th={p95:.2f}, 99th={p99:.2f} V/m\n")
                if self.selected_regions:
                    f.write(f"Selected Regions: {', '.join(map(str, self.selected_regions))}\n")
                else:
                    f.write("Selected Regions: All regions\n")
                f.write("\n")
                f.write("OUTPUT FILES:\n")
                f.write("-" * 13 + "\n")
                f.write(f"Averaged NIfTI: {nifti_filename}\n")
                f.write(f"Parameters: {txt_filename}\n")
                f.write(f"PDF: {base_filename}_multiple_views.pdf\n")
                if self.create_glass_brain:
                    f.write(f"Glass Brain PDF: {base_filename}_glass_brain.pdf\n")

            self.output_signal.emit(f"Saved parameters file: {txt_filepath}")

            # Call the visualization function with averaged data
            # We'll need to modify the viz function to accept averaged data
            result = create_pdf_entry_point_group(
                averaged_img,
                base_filename,
                output_base_dir,
                actual_min_cutoff,
                actual_max_cutoff,
                self.atlas_name,
                self.selected_regions,
                output_callback=output_callback
            )

            # Create glass brain visualization if enabled
            glass_brain_result = None
            if self.create_glass_brain:
                output_callback("Creating glass brain visualization...")
                glass_brain_result = create_glass_brain_entry_point_group(
                    averaged_img,
                    base_filename,
                    output_base_dir,
                    actual_min_cutoff,
                    actual_max_cutoff,
                    self.glass_brain_cmap,
                    output_callback=output_callback
                )

            if result or glass_brain_result:
                # Update the .txt file with additional statistics
                self._update_txt_file_with_stats(txt_filepath, averaged_img, self.use_percentiles,
                                              self.min_cutoff, self.max_cutoff,
                                              actual_min_cutoff, actual_max_cutoff)
                self.finished_signal.emit(0)
            else:
                self.error_signal.emit("Visualization failed - check console output above")

        except Exception as e:
            self.error_signal.emit(f"Error during visualization: {str(e)}\n\n{traceback.format_exc()}")

    def terminate_and_wait(self):
        """Terminate the worker thread."""
        self.requestInterruption()
        if not self.wait(5000):  # Wait up to 5 seconds
            self.terminate()

    def _update_txt_file_with_stats(self, txt_filepath, averaged_img, use_percentiles,
                                  original_min_cutoff, original_max_cutoff,
                                  actual_min_cutoff, actual_max_cutoff):
        """Update the .txt file with additional data statistics."""
        # Read existing content
        with open(txt_filepath, 'r') as f:
            existing_content = f.read()

        # Calculate statistics from the averaged image
        data = averaged_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            return  # No data to report

        max_value = np.max(data)
        percentile_999 = np.percentile(data_nonzero, 99.9)
        min_value = np.min(data_nonzero)

        # Add statistics section
        stats_section = "\nDATA STATISTICS:\n"
        stats_section += "-" * 15 + "\n"
        stats_section += f"Absolute maximum: {max_value:.2f} V/m\n"
        stats_section += f"99.9th percentile: {percentile_999:.2f} V/m\n"
        stats_section += f"Minimum (non-zero): {min_value:.2f} V/m\n"

        if use_percentiles:
            stats_section += "\nPERCENTILE MODE:\n"
            stats_section += "-" * 15 + "\n"
            stats_section += f"Requested minimum: {original_min_cutoff:.1f}% → {actual_min_cutoff:.2f} V/m\n"
            stats_section += f"Requested maximum: {original_max_cutoff:.1f}% → {actual_max_cutoff:.2f} V/m\n"
        else:
            stats_section += "\nABSOLUTE VALUE MODE:\n"
            stats_section += "-" * 20 + "\n"
            stats_section += f"Minimum cutoff: {actual_min_cutoff:.2f} V/m\n"
            stats_section += f"Maximum cutoff: {actual_max_cutoff:.2f} V/m\n"

        # Check if default 99.9th percentile was used for max cutoff
        used_default_max = (actual_max_cutoff == percentile_999)
        if used_default_max:
            stats_section += "\nNOTE: Maximum cutoff was automatically set to 99.9th percentile\n"

        stats_section += "\n"

        # Append to existing content
        updated_content = existing_content + stats_section

        # Write back to file
        with open(txt_filepath, 'w') as f:
            f.write(updated_content)


class PublicationImageDialog(QtWidgets.QDialog):
    """Dialog for generating publication-ready images."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Publication Image Generator")
        self.setMinimumSize(700, 600)
        self.parent_window = parent
        self.pm = get_path_manager() if get_path_manager else None

        self.subjects_list = []
        self.simulations_dict = {}

        self.worker = None

        self._setup_ui()
        self._load_subjects()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QtWidgets.QVBoxLayout(self)

        # Description
        description = QtWidgets.QLabel(
            "Generate publication-ready PDF visualizations with multiple views and atlas contours."
        )
        description.setWordWrap(True)
        description.setStyleSheet("margin-bottom: 15px;")
        layout.addWidget(description)



        # Subject-Simulation selection
        self.group_selection_widget = QtWidgets.QGroupBox("Subject-Simulation Selection")
        group_layout = QtWidgets.QVBoxLayout(self.group_selection_widget)

        # Subject-Simulation Pairs List
        pairs_label = QtWidgets.QLabel("Subject-Simulation Pairs:")
        pairs_label.setStyleSheet("font-weight: bold;")
        group_layout.addWidget(pairs_label)

        # Table for pairs
        self.pairs_table = QtWidgets.QTableWidget()
        self.pairs_table.setColumnCount(3)
        self.pairs_table.setHorizontalHeaderLabels(["Subject", "Simulation", ""])
        self.pairs_table.horizontalHeader().setStretchLastSection(False)
        self.pairs_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.pairs_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.pairs_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.pairs_table.setColumnWidth(2, 50)
        self.pairs_table.setMaximumHeight(200)
        group_layout.addWidget(self.pairs_table)

        # Buttons for managing pairs
        pair_buttons_layout = QtWidgets.QHBoxLayout()

        self.add_pair_btn = QtWidgets.QPushButton("+ Add Pair")
        self.add_pair_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.add_pair_btn.clicked.connect(self.add_pair_row)
        pair_buttons_layout.addWidget(self.add_pair_btn)

        self.quick_add_btn = QtWidgets.QPushButton("Quick Add")
        self.quick_add_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.quick_add_btn.setToolTip("Add the same simulation to multiple subjects at once")
        self.quick_add_btn.clicked.connect(self.quick_add_pairs)
        pair_buttons_layout.addWidget(self.quick_add_btn)

        self.clear_pairs_btn = QtWidgets.QPushButton("Clear All")
        self.clear_pairs_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.clear_pairs_btn.clicked.connect(self.clear_all_pairs)
        pair_buttons_layout.addWidget(self.clear_pairs_btn)

        pair_buttons_layout.addStretch()
        group_layout.addLayout(pair_buttons_layout)

        layout.addWidget(self.group_selection_widget)

        # Separator line
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator)

        # Output sub-directory input
        output_layout = QtWidgets.QGridLayout()

        subdir_label = QtWidgets.QLabel("Sub-directory name:")
        self.subdir_edit = QtWidgets.QLineEdit()
        self.subdir_edit.setPlaceholderText("enter name for directory /derivatives/ti-toolbox/nilearn_visuals/{name}")
        self.subdir_edit.setToolTip("Files will be saved in derivatives/ti-toolbox/nilearn_visuals/[sub-directory]/")

        output_layout.addWidget(subdir_label, 0, 0)
        output_layout.addWidget(self.subdir_edit, 0, 1)

        # Set column stretch
        output_layout.setColumnStretch(1, 1)

        layout.addLayout(output_layout)

        # Separator line
        separator2 = QtWidgets.QFrame()
        separator2.setFrameShape(QtWidgets.QFrame.HLine)
        separator2.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator2)

        # Visualization parameters label
        viz_label = QtWidgets.QLabel("Visualization Parameters:")
        viz_label.setStyleSheet("font-weight: bold; margin-top: 10px; margin-bottom: 5px;")
        layout.addWidget(viz_label)

        # Percentile mode checkbox
        self.percentile_checkbox = QtWidgets.QCheckBox("Use percentile cutoffs")
        self.percentile_checkbox.setToolTip("When checked, cutoff values are treated as percentiles (0-100%) from maximum field value")
        self.percentile_checkbox.stateChanged.connect(self._on_percentile_mode_changed)
        layout.addWidget(self.percentile_checkbox)


        # Visualization parameters grid
        param_layout = QtWidgets.QGridLayout()

        # Row 1: Minimum cutoff | Atlas selection
        min_cutoff_label = QtWidgets.QLabel("Minimum Cutoff:")
        self.min_cutoff_spin = QtWidgets.QDoubleSpinBox()
        self.min_cutoff_spin.setRange(0.0, 10.0)
        self.min_cutoff_spin.setValue(0.3)
        self.min_cutoff_spin.setSingleStep(0.1)
        self.min_cutoff_spin.setSuffix(" V/m")

        atlas_label = QtWidgets.QLabel("Atlas Selection:")
        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.addItems([
            "harvard_oxford_sub",
            "harvard_oxford",
            "aal",
            "schaefer_2018"
        ])
        self.atlas_combo.setCurrentText("harvard_oxford_sub")
        self.atlas_combo.currentTextChanged.connect(self._on_atlas_changed)

        param_layout.addWidget(min_cutoff_label, 0, 0)
        param_layout.addWidget(self.min_cutoff_spin, 0, 1)
        param_layout.addWidget(atlas_label, 0, 2)
        param_layout.addWidget(self.atlas_combo, 0, 3)

        # Row 2: Maximum cutoff | Region selection
        max_cutoff_label = QtWidgets.QLabel("Maximum Cutoff:")
        self.max_cutoff_spin = QtWidgets.QDoubleSpinBox()
        self.max_cutoff_spin.setRange(0.0, 50.0)
        self.max_cutoff_spin.setValue(5.0)
        self.max_cutoff_spin.setSingleStep(0.5)
        self.max_cutoff_spin.setSuffix(" V/m")

        region_label = QtWidgets.QLabel("Region Selection:")
        self.region_combo = QtWidgets.QComboBox()
        self.region_combo.addItem("All Regions", None)  # None means all regions

        param_layout.addWidget(max_cutoff_label, 1, 0)
        param_layout.addWidget(self.max_cutoff_spin, 1, 1)
        param_layout.addWidget(region_label, 1, 2)
        param_layout.addWidget(self.region_combo, 1, 3)

        # Set column stretches for better alignment
        param_layout.setColumnStretch(1, 1)
        param_layout.setColumnStretch(3, 1)

        layout.addLayout(param_layout)

        # Console with Run/Stop buttons
        self.action_buttons = RunStopButtons(self, run_text="Generate Images", stop_text="Stop")
        self.action_buttons.connect_run(self._run_visualization)
        self.action_buttons.connect_stop(self._stop_visualization)

        self.console = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            show_debug_checkbox=False,
            console_label="Output:",
            min_height=200,
            max_height=None,
            custom_buttons=[self.action_buttons.get_run_button(), self.action_buttons.get_stop_button()]
        )
        layout.addWidget(self.console)


        # Set stretch factors
        layout.setStretchFactor(self.console, 1)

    def _load_subjects(self):
        """Load available subjects from the project."""
        if not self.pm:
            self.console.update_console("PathManager not available", 'error')
            return

        try:
            subjects = self.pm.list_subjects()
            self.subjects_list = subjects

            if not subjects:
                self.console.update_console("No subjects found in project", 'warning')

        except Exception as e:
            self.console.update_console(f"Error loading subjects: {str(e)}", 'error')


    def _on_subject_changed(self, subject_id):
        """Handle subject selection change."""
        if not subject_id or subject_id not in self.subjects_list:
            return

        try:
            simulations = self.pm.list_simulations(subject_id)
            self.simulations_dict[subject_id] = simulations
            self.sim_combo.clear()
            self.sim_combo.addItems(simulations)

            if simulations:
                sim_count = len(simulations)
                self.console.update_console(f"Found {sim_count} simulation(s) for subject {subject_id}", 'info')
            else:
                self.console.update_console(f"No simulations found for subject {subject_id}", 'warning')

        except Exception as e:
            self.console.update_console(f"Error loading simulations for {subject_id}: {str(e)}", 'error')

    def get_simulations_for_subject(self, subject_id):
        """Get list of available simulations for a subject."""
        try:
            return self.pm.list_simulations(subject_id)
        except Exception as e:
            self.console.update_console(f"Error getting simulations for subject {subject_id}: {str(e)}", 'error')
            return []

    def add_pair_row(self):
        """Add a new row for subject-simulation pair selection."""
        row = self.pairs_table.rowCount()
        self.pairs_table.insertRow(row)

        # Subject combo
        subject_combo = QtWidgets.QComboBox()
        subjects = []
        if self.pm:
            try:
                subjects = self.pm.list_subjects()
            except Exception as e:
                self.console.update_console(f"Error getting subjects: {str(e)}", 'error')
        subject_combo.addItems(subjects)
        subject_combo.currentTextChanged.connect(lambda: self.update_sim_combo_in_row(row))
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
        subjects = []
        if self.pm:
            try:
                subjects = self.pm.list_subjects()
            except Exception as e:
                self.console.update_console(f"Error getting subjects: {str(e)}", 'error')
                subjects = []
        for subject in subjects:
            all_sims.update(self.get_simulations_for_subject(subject))
        sim_combo.addItems(sorted(all_sims))
        sim_layout.addWidget(sim_combo)
        layout.addLayout(sim_layout)

        # Subject list
        layout.addWidget(QtWidgets.QLabel("Select Subjects:"))
        subject_list = QtWidgets.QListWidget()
        subject_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        all_subjects = []
        if self.pm:
            try:
                all_subjects = self.pm.list_subjects()
            except Exception as e:
                self.console.update_console(f"Error getting subjects: {str(e)}", 'error')
                all_subjects = []
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
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one subject")
                return

            # Add pairs for each selected subject
            added_count = 0
            for item in selected_items:
                subject_id = item.text()

                # Check if this subject has the selected simulation
                available_sims = self.get_simulations_for_subject(subject_id)
                if selected_simulation not in available_sims:
                    self.console.update_console(f"Warning: Subject {subject_id} does not have simulation {selected_simulation}")
                    continue

                # Check for duplicates
                duplicate = False
                for row in range(self.pairs_table.rowCount()):
                    existing_subject = self.pairs_table.cellWidget(row, 0).currentText()
                    existing_sim = self.pairs_table.cellWidget(row, 1).currentText()
                    if existing_subject == subject_id and existing_sim == selected_simulation:
                        duplicate = True
                        break

                if duplicate:
                    continue

                # Add new row
                row = self.pairs_table.rowCount()
                self.pairs_table.insertRow(row)

                # Subject combo
                subject_combo_widget = QtWidgets.QComboBox()
                subject_combo_widget.addItems(all_subjects)
                subject_combo_widget.setCurrentText(subject_id)
                subject_combo_widget.currentTextChanged.connect(lambda: self.update_sim_combo_in_row(row))
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

            self.console.update_console(f"Added {added_count} subject-simulation pairs")

    def _on_percentile_mode_changed(self, state):
        """Handle percentile mode checkbox state change."""
        is_percentile = state == QtCore.Qt.Checked

        if is_percentile:
            # Switch to percentile mode
            self.min_cutoff_spin.setRange(0.0, 99.9)
            self.min_cutoff_spin.setValue(95.0)
            self.min_cutoff_spin.setSingleStep(0.1)
            self.min_cutoff_spin.setSuffix(" %")

            self.max_cutoff_spin.setRange(95.0, 100.0)
            self.max_cutoff_spin.setValue(99.9)
            self.max_cutoff_spin.setSingleStep(0.1)
            self.max_cutoff_spin.setSuffix(" %")
        else:
            # Switch to absolute value mode
            self.min_cutoff_spin.setRange(0.0, 10.0)
            self.min_cutoff_spin.setValue(0.3)
            self.min_cutoff_spin.setSingleStep(0.1)
            self.min_cutoff_spin.setSuffix(" V/m")

            self.max_cutoff_spin.setRange(0.0, 50.0)
            self.max_cutoff_spin.setValue(5.0)
            self.max_cutoff_spin.setSingleStep(0.5)
            self.max_cutoff_spin.setSuffix(" V/m")


    def _on_atlas_changed(self, atlas_name):
        """Handle atlas selection change and populate region combo."""
        if not atlas_name:
            return

        try:
            # Get atlas regions based on selected atlas
            atlas_configs = {
                'harvard_oxford': {
                    'function': lambda: datasets.fetch_atlas_harvard_oxford("cort-maxprob-thr25-2mm"),
                    'labels_key': 'labels'
                },
                'harvard_oxford_sub': {
                    'function': lambda: datasets.fetch_atlas_harvard_oxford("sub-maxprob-thr25-2mm"),
                    'labels_key': 'labels'
                },
                'aal': {
                    'function': lambda: datasets.fetch_atlas_aal(),
                    'labels_key': 'labels'
                },
                'schaefer_2018': {
                    'function': lambda: datasets.fetch_atlas_schaefer_2018(n_rois=100),
                    'labels_key': 'labels'
                }
            }

            if atlas_name in atlas_configs:
                config = atlas_configs[atlas_name]
                atlas_data = config['function']()
                labels = atlas_data[config['labels_key']]

                # Clear and repopulate region combo
                self.region_combo.clear()
                self.region_combo.addItem("All Regions", None)

                # Add individual regions (skip background/unknown regions)
                for i, label in enumerate(labels):
                    if label and label.lower() not in ['background', 'unknown', '']:
                        self.region_combo.addItem(label, i)  # Regions are 0-indexed in atlas data

        except Exception as e:
            self.console.update_console(f"Error loading atlas regions: {str(e)}", 'warning')
            # Reset to "All Regions" only
            self.region_combo.clear()
            self.region_combo.addItem("All Regions", None)

    def _run_visualization(self):
        """Run the publication image generation."""
        min_cutoff = self.min_cutoff_spin.value()
        max_cutoff = self.max_cutoff_spin.value()
        atlas_name = self.atlas_combo.currentText()
        selected_region_data = self.region_combo.currentData()
        selected_regions = [selected_region_data] if selected_region_data is not None else None

        # Check if worker is already running
        if self.worker and self.worker.isRunning():
            self.console.update_console("Visualization is already running", 'warning')
            return

        self.console.clear_console()
        self.console.update_console("Starting publication image generation...", 'info')

        subject_simulation_pairs = []

        # Collect pairs from table
        for row in range(self.pairs_table.rowCount()):
            subject_combo = self.pairs_table.cellWidget(row, 0)
            sim_combo = self.pairs_table.cellWidget(row, 1)

            if subject_combo and sim_combo:
                subject_id = subject_combo.currentText()
                simulation_name = sim_combo.currentText()

                if subject_id and simulation_name:
                    subject_simulation_pairs.append({
                        "subject_id": subject_id,
                        "simulation_name": simulation_name
                    })

        if not subject_simulation_pairs:
            self.console.update_console("Please add at least one subject-simulation pair", 'error')
            return

        # Display information based on number of pairs
        if len(subject_simulation_pairs) == 1:
            pair = subject_simulation_pairs[0]
            self.console.update_console("Using single subject-simulation:", 'info')
            self.console.update_console(f"Subject: {pair['subject_id']}", 'info')
            self.console.update_console(f"Simulation: {pair['simulation_name']}", 'info')
        else:
            self.console.update_console(f"Averaging {len(subject_simulation_pairs)} subject-simulation pairs:", 'info')
            for i, pair in enumerate(subject_simulation_pairs, 1):
                self.console.update_console(f"  {i}. Subject: {pair['subject_id']}, Simulation: {pair['simulation_name']}", 'info')

        # Get output parameters
        subdir_name = self.subdir_edit.text().strip()
        if not subdir_name:
            QtWidgets.QMessageBox.warning(self, "Missing Output Directory",
                                         "Please enter a sub-directory name for the output files.")
            return
        use_percentiles = self.percentile_checkbox.isChecked()

        if use_percentiles:
            self.console.update_console(f"Cutoff percentiles: {min_cutoff:.1f}% - {max_cutoff:.1f}%", 'info')
        else:
            self.console.update_console(f"Cutoff range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m", 'info')

        self.console.update_console(f"Output sub-directory: nilearn_visuals/{subdir_name}", 'info')
        self.console.update_console(f"Atlas: {atlas_name}", 'info')
        if selected_regions:
            region_name = self.region_combo.currentText()
            self.console.update_console(f"Selected region: {region_name}", 'info')
        else:
            self.console.update_console("Selected regions: All regions", 'info')

        # Glass brain visualization (always enabled with 'hot' colormap)
        create_glass_brain = True
        glass_brain_cmap = 'hot'
        self.console.update_console("Glass brain visualization: Enabled (colormap: hot)", 'info')

        # Disable run button and enable stop button
        self.action_buttons.enable_stop()

        # Get output parameters
        subdir_name = self.subdir_edit.text().strip()
        if not subdir_name:
            QtWidgets.QMessageBox.warning(self, "Missing Output Directory",
                                         "Please enter a sub-directory name for the output files.")
            return
        use_percentiles = self.percentile_checkbox.isChecked()

        # Start worker thread
        self.worker = PublicationImageWorker(subject_simulation_pairs, min_cutoff, max_cutoff, atlas_name, selected_regions, subdir_name, use_percentiles, create_glass_brain, glass_brain_cmap)
        self.worker.output_signal.connect(lambda text: self.console.update_console(text, 'default'))
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.error_signal.connect(self._on_worker_error)
        self.worker.start()

    def _stop_visualization(self):
        """Stop the current visualization process."""
        if self.worker and self.worker.isRunning():
            self.console.update_console("Stopping visualization...", 'warning')
            self.worker.terminate_and_wait()
            self._reset_buttons()

    def _on_worker_finished(self, exit_code):
        """Handle worker thread completion."""
        self._reset_buttons()
        if exit_code == 0:
            self.console.update_console("Publication image generation completed successfully!", 'success')
        else:
            self.console.update_console(f"Publication image generation failed with exit code {exit_code}", 'error')

    def _on_worker_error(self, error_msg):
        """Handle worker thread errors."""
        self._reset_buttons()
        self.console.update_console(f"Error during visualization: {error_msg}", 'error')

    def _reset_buttons(self):
        """Reset action buttons to initial state."""
        self.action_buttons.enable_run()

    def reject(self):
        """Handle dialog close/reject event."""
        if self.worker and self.worker.isRunning():
            # Ask user if they want to cancel the running process
            reply = QtWidgets.QMessageBox.question(
                self,
                "Cancel Operation",
                "A visualization is currently running. Do you want to cancel it and close?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )

            if reply == QtWidgets.QMessageBox.Yes:
                self.worker.terminate_and_wait()
                super().reject()
            # If No, don't close the dialog
        else:
            super().reject()

def main(parent=None):
    """
    Main entry point for the extension.
    This function is called when the extension is launched.
    """
    dialog = PublicationImageDialog(parent)
    dialog.exec_()


# Alternative entry point (for flexibility)
def run(parent=None):
    """Alternative entry point."""
    main(parent)
