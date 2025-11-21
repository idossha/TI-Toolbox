#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: NIfTI Group Averaging
Compute group averages and differences for NIfTI files organized by groups.
"""

import sys
import os
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui
import json
import numpy as np
import nibabel as nib
import gc

# Extension metadata (required)
EXTENSION_NAME = "NIfTI Group Averaging"
EXTENSION_DESCRIPTION = "Compute group averages of NIfTI files"


# Add TI-Toolbox to path
ti_toolbox_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ti_toolbox_path))

# Add GUI path for components
gui_path = Path(__file__).parent.parent
sys.path.insert(0, str(gui_path))

from core import get_path_manager
from core import constants as const
from core import nifti

from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons


class SubjectRow(QtWidgets.QWidget):
    """Widget for a single subject configuration row"""
    
    remove_requested = QtCore.pyqtSignal(object)  # Signal to remove this row
    
    def __init__(self, parent=None, subjects_list=None, simulations_dict=None, groups_list=None):
        super(SubjectRow, self).__init__(parent)
        self.subjects_list = subjects_list or []
        self.simulations_dict = simulations_dict or {}
        self.groups_list = groups_list or []
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the subject row UI"""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Subject selection
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.addItems(self.subjects_list)
        self.subject_combo.currentTextChanged.connect(self.on_subject_changed)
        layout.addWidget(self.subject_combo, 2)
        
        # Simulation selection
        self.simulation_combo = QtWidgets.QComboBox()
        layout.addWidget(self.simulation_combo, 3)
        
        # Group assignment
        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.setEditable(True)  # Allow custom group names
        if self.groups_list:
            self.group_combo.addItems(self.groups_list)
        else:
            self.group_combo.addItems(['Group1', 'Group2'])
        layout.addWidget(self.group_combo, 2)
        
        # Remove button
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setFixedWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(remove_btn)
        
        # Initialize simulations
        self.on_subject_changed(self.subject_combo.currentText())
    
    def on_subject_changed(self, subject_id):
        """Update simulations when subject changes"""
        self.simulation_combo.clear()
        if subject_id in self.simulations_dict:
            self.simulation_combo.addItems(self.simulations_dict[subject_id])
    
    def get_config(self):
        """Get the configuration for this subject"""
        return {
            'subject_id': self.subject_combo.currentText(),
            'simulation_name': self.simulation_combo.currentText(),
            'group': self.group_combo.currentText()
        }
    
    def set_config(self, config):
        """Set the configuration for this subject"""
        idx = self.subject_combo.findText(config['subject_id'])
        if idx >= 0:
            self.subject_combo.setCurrentIndex(idx)
        
        idx = self.simulation_combo.findText(config['simulation_name'])
        if idx >= 0:
            self.simulation_combo.setCurrentIndex(idx)
        
        # Set or add group
        group = config.get('group', 'Group1')
        idx = self.group_combo.findText(group)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)
        else:
            self.group_combo.addItem(group)
            self.group_combo.setCurrentText(group)


class NiftiGroupAverageWidget(QtWidgets.QWidget):
    """Main widget for NIfTI group averaging"""

    def __init__(self, parent=None):
        super(NiftiGroupAverageWidget, self).__init__(parent)
        self.parent_window = parent

        # Get path manager
        self.pm = get_path_manager() if get_path_manager else None

        # Data
        self.subjects_list = []
        self.simulations_dict = {}
        self.subject_rows = []

        # Setup UI
        self.setup_ui()

        # Load subjects
        self.load_subjects()
    
    def setup_ui(self):
        """Set up the main UI"""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Header
        header_label = QtWidgets.QLabel("<h2>NIfTI Group Averaging</h2>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        desc_label = QtWidgets.QLabel(
            "Compute group averages of NIfTI files and calculate differences between groups."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; padding: 5px;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # === Subject Configuration ===
        subjects_group = QtWidgets.QGroupBox("Subject Configuration")
        subjects_layout = QtWidgets.QVBoxLayout(subjects_group)
        
        # Toolbar
        toolbar_layout = QtWidgets.QHBoxLayout()
        
        add_subject_btn = QtWidgets.QPushButton("+ Add Subject")
        add_subject_btn.clicked.connect(self.add_subject_row)
        toolbar_layout.addWidget(add_subject_btn)
        
        import_csv_btn = QtWidgets.QPushButton("Import CSV")
        import_csv_btn.clicked.connect(self.import_from_csv)
        toolbar_layout.addWidget(import_csv_btn)
        
        export_csv_btn = QtWidgets.QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self.export_to_csv)
        toolbar_layout.addWidget(export_csv_btn)
        
        toolbar_layout.addStretch()
        subjects_layout.addLayout(toolbar_layout)
        
        # Subject list header
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(QtWidgets.QLabel("<b>Subject</b>"), 2)
        header_layout.addWidget(QtWidgets.QLabel("<b>Simulation</b>"), 3)
        header_layout.addWidget(QtWidgets.QLabel("<b>Group</b>"), 2)
        header_layout.addWidget(QtWidgets.QLabel(""), 0)  # For remove button
        header_widget = QtWidgets.QWidget()
        header_widget.setLayout(header_layout)
        subjects_layout.addWidget(header_widget)
        
        # Scrollable subject list
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(200)
        
        self.subjects_container = QtWidgets.QWidget()
        self.subjects_container_layout = QtWidgets.QVBoxLayout(self.subjects_container)
        self.subjects_container_layout.addStretch()
        
        scroll_area.setWidget(self.subjects_container)
        subjects_layout.addWidget(scroll_area)
        
        layout.addWidget(subjects_group)
        
        # === Analysis Configuration ===
        config_group = QtWidgets.QGroupBox("Analysis Configuration")
        config_layout = QtWidgets.QGridLayout(config_group)
        
        row = 0
        
        # Analysis name (spans both columns)
        config_layout.addWidget(QtWidgets.QLabel("Analysis Name:"), row, 0)
        self.analysis_name_edit = QtWidgets.QLineEdit()
        self.analysis_name_edit.setPlaceholderText("e.g., hippocampus_group_comparison")
        config_layout.addWidget(self.analysis_name_edit, row, 1, 1, 3)
        row += 1
        
        # NIfTI file pattern (spans both columns)
        config_layout.addWidget(QtWidgets.QLabel("NIfTI Pattern:"), row, 0)
        self.nifti_pattern_edit = QtWidgets.QLineEdit()
        self.nifti_pattern_edit.setText("grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz")
        self.nifti_pattern_edit.setToolTip("Use {simulation_name} as a variable (subject is in directory path)")
        config_layout.addWidget(self.nifti_pattern_edit, row, 1, 1, 3)
        row += 1
        
        # Group difference pairs
        config_layout.addWidget(QtWidgets.QLabel("Group Differences:"), row, 0)
        self.diff_pairs_edit = QtWidgets.QLineEdit()
        self.diff_pairs_edit.setPlaceholderText("e.g., Group1-Group2, Group1-Group3 (optional)")
        self.diff_pairs_edit.setToolTip("Comma-separated pairs in format: GroupA-GroupB\nLeave empty to compute all possible differences")
        config_layout.addWidget(self.diff_pairs_edit, row, 1, 1, 3)
        row += 1
        
        layout.addWidget(config_group)
        
        # === Output Console (using reusable component) ===
        if ConsoleWidget and RunStopButtons:
            # Create action buttons for the console
            self.action_buttons = RunStopButtons(
                parent=self,
                run_text="Run Analysis",
                stop_text="Stop"
            )
            self.action_buttons.connect_run(self.run_analysis)
            self.action_buttons.connect_stop(self.stop_analysis)
            
            # Create console with action buttons
            self.console_widget = ConsoleWidget(
                parent=self,
                show_clear_button=True,
                show_debug_checkbox=True,
                console_label="Output:",
                min_height=150,
                max_height=150,
                custom_buttons=[self.action_buttons.get_run_button(), self.action_buttons.get_stop_button()]
            )
            layout.addWidget(self.console_widget)
        else:
            # Fallback if component not available
            output_group = QtWidgets.QGroupBox("Output")
            output_layout = QtWidgets.QVBoxLayout(output_group)
            
            self.output_text = QtWidgets.QTextEdit()
            self.output_text.setReadOnly(True)
            self.output_text.setMaximumHeight(150)
            self.output_text.setStyleSheet("background-color: #f5f5f5; font-family: monospace;")
            output_layout.addWidget(self.output_text)
            
            layout.addWidget(output_group)
            
            # Fallback action buttons
            button_layout = QtWidgets.QHBoxLayout()
            
            self.run_btn = QtWidgets.QPushButton("Run Analysis")
            self.run_btn.clicked.connect(self.run_analysis)
            button_layout.addWidget(self.run_btn)
            
            layout.addLayout(button_layout)
    
    def update_output(self, message, msg_type='default'):
        """Update output console with message"""
        if hasattr(self, 'console_widget') and self.console_widget:
            self.console_widget.update_console(message, msg_type)
        elif hasattr(self, 'output_text') and self.output_text:
            self.output_text.append(message)
    
    def load_subjects(self):
        """Load available subjects and their simulations"""
        if not self.pm:
            self.update_output("Warning: Path manager not available", 'warning')
            return
        
        try:
            self.subjects_list = self.pm.list_subjects()
            
            # Load simulations for each subject
            for subject_id in self.subjects_list:
                simulations = self.pm.list_simulations(subject_id)
                # Filter for only Simulations directory contents
                sim_dir = self.pm.get_subject_dir(subject_id)
                if sim_dir:
                    sim_path = os.path.join(sim_dir, "Simulations")
                    if os.path.exists(sim_path):
                        sims = [d for d in os.listdir(sim_path) 
                               if os.path.isdir(os.path.join(sim_path, d))]
                        self.simulations_dict[subject_id] = sorted(sims)
                    else:
                        self.simulations_dict[subject_id] = []
            
            self.update_output(f"Loaded {len(self.subjects_list)} subjects", 'info')
            
        except Exception as e:
            self.update_output(f"Error loading subjects: {str(e)}", 'error')
    
    def add_subject_row(self):
        """Add a new subject configuration row"""
        # Get unique groups from existing rows
        groups_set = set()
        for row in self.subject_rows:
            groups_set.add(row.group_combo.currentText())
        groups_list = sorted(list(groups_set)) if groups_set else ['Group1', 'Group2']
        
        row = SubjectRow(parent=self, subjects_list=self.subjects_list, 
                        simulations_dict=self.simulations_dict, groups_list=groups_list)
        row.remove_requested.connect(self.remove_subject_row)
        
        # Insert before the stretch
        self.subjects_container_layout.insertWidget(
            len(self.subject_rows), row
        )
        self.subject_rows.append(row)
    
    def remove_subject_row(self, row):
        """Remove a subject configuration row"""
        if row in self.subject_rows:
            self.subject_rows.remove(row)
            row.deleteLater()
    
    def import_from_csv(self):
        """Import subject configurations from CSV"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Subject Configuration",
            "",
            "CSV Files (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            import csv
            
            # Clear existing rows
            for row in self.subject_rows[:]:
                self.remove_subject_row(row)
            
            # Collect unique groups for dropdown
            groups_set = set()
            configs = []
            
            # Read CSV
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                for row_data in reader:
                    config = {
                        'subject_id': row_data['subject_id'].replace('sub-', ''),
                        'simulation_name': row_data['simulation_name'],
                        'group': row_data.get('group', 'Group1')
                    }
                    configs.append(config)
                    groups_set.add(config['group'])
            
            groups_list = sorted(list(groups_set))
            
            # Create rows
            for config in configs:
                row = SubjectRow(parent=self, subjects_list=self.subjects_list,
                               simulations_dict=self.simulations_dict, groups_list=groups_list)
                row.remove_requested.connect(self.remove_subject_row)
                row.set_config(config)
                
                # Add to layout
                self.subjects_container_layout.insertWidget(
                    len(self.subject_rows), row
                )
                self.subject_rows.append(row)
            
            self.update_output(f"Imported {len(self.subject_rows)} subjects from CSV", 'success')
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import CSV: {str(e)}"
            )
    
    def export_to_csv(self):
        """Export subject configurations to CSV"""
        if not self.subject_rows:
            QtWidgets.QMessageBox.warning(
                self,
                "No Data",
                "No subjects configured to export."
            )
            return
        
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Subject Configuration",
            "",
            "CSV Files (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            import csv
            
            with open(file_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['subject_id', 'simulation_name', 'group'])
                writer.writeheader()
                
                for row in self.subject_rows:
                    config = row.get_config()
                    writer.writerow(config)
            
            self.update_output(f"Exported {len(self.subject_rows)} subjects to CSV", 'success')
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export CSV: {str(e)}"
            )
    
    def run_analysis(self):
        """Run the group averaging analysis"""
        # Validate inputs
        if not self.analysis_name_edit.text().strip():
            QtWidgets.QMessageBox.warning(
                self,
                "Missing Input",
                "Please enter an analysis name."
            )
            return
        
        if len(self.subject_rows) < 2:
            QtWidgets.QMessageBox.warning(
                self,
                "Insufficient Data",
                "Please add at least 2 subjects."
            )
            return
        
        # Collect subject configurations
        subject_configs = []
        groups_dict = {}
        
        for row in self.subject_rows:
            config = row.get_config()
            subject_configs.append(config)
            
            group = config['group']
            if group not in groups_dict:
                groups_dict[group] = 0
            groups_dict[group] += 1
        
        if len(groups_dict) < 1:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Configuration",
                "You need at least one group with subjects."
            )
            return
        
        # Build configuration
        config = {
            'nifti_file_pattern': self.nifti_pattern_edit.text(),
            'diff_pairs': self.diff_pairs_edit.text().strip()
        }
        
        analysis_name = self.analysis_name_edit.text().strip()
        
        # Show summary
        groups_summary = "\n".join([f"  • {group}: {count} subjects" for group, count in groups_dict.items()])
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Run Analysis",
            f"Run group averaging with:\n\n"
            f"Groups:\n{groups_summary}\n\n"
            f"Analysis name: {analysis_name}\n\n"
            f"Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Disable run button, enable stop button
        if hasattr(self, 'action_buttons'):
            self.action_buttons.enable_stop()
        elif hasattr(self, 'run_btn'):
            self.run_btn.setEnabled(False)
        
        # Clear console
        if hasattr(self, 'console_widget') and self.console_widget:
            self.console_widget.clear_console()
        elif hasattr(self, 'output_text') and self.output_text:
            self.output_text.clear()
        self.update_output("Starting analysis...", 'info')
        
        # Run in thread
        self.worker_thread = AnalysisThread(subject_configs, analysis_name, config)
        self.worker_thread.output_signal.connect(self.on_output)
        self.worker_thread.finished_signal.connect(self.on_finished)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.start()
    
    def stop_analysis(self):
        """Stop the running analysis."""
        if hasattr(self, 'worker_thread') and self.worker_thread and self.worker_thread.isRunning():
            self.update_output("\nStopping analysis...", 'warning')
            self.worker_thread.terminate()
            self.worker_thread.wait()
            self.update_output("Analysis stopped by user.", 'warning')
            
            # Re-enable run button
            if hasattr(self, 'action_buttons'):
                self.action_buttons.enable_run()
            elif hasattr(self, 'run_btn'):
                self.run_btn.setEnabled(True)
    
    def on_output(self, message):
        """Handle output from analysis thread"""
        self.update_output(message, 'default')
    
    def on_finished(self, results):
        """Handle analysis completion"""
        # Re-enable run button
        if hasattr(self, 'action_buttons'):
            self.action_buttons.enable_run()
        elif hasattr(self, 'run_btn'):
            self.run_btn.setEnabled(True)
        
        self.update_output("\n" + "="*50, 'success')
        self.update_output("ANALYSIS COMPLETE!", 'success')
        self.update_output("="*50, 'success')
        self.update_output(f"Output directory: {results['output_dir']}", 'info')
        self.update_output(f"Groups processed: {', '.join(results['groups'])}", 'info')
        self.update_output(f"Differences computed: {len(results['differences'])}", 'info')
        
        QtWidgets.QMessageBox.information(
            self,
            "Analysis Complete",
            f"Analysis completed successfully!\n\n"
            f"Groups processed: {len(results['groups'])}\n"
            f"Differences computed: {len(results['differences'])}\n\n"
            f"Results saved to:\n{results['output_dir']}"
        )
    
    def on_error(self, error_msg):
        """Handle analysis error"""
        # Re-enable run button
        if hasattr(self, 'action_buttons'):
            self.action_buttons.enable_run()
        elif hasattr(self, 'run_btn'):
            self.run_btn.setEnabled(True)
        
        self.update_output("\n" + "="*50, 'error')
        self.update_output("ERROR!", 'error')
        self.update_output("="*50, 'error')
        self.update_output(error_msg, 'error')
        
        QtWidgets.QMessageBox.critical(
            self,
            "Analysis Error",
            f"An error occurred during analysis:\n\n{error_msg}"
        )


class AnalysisThread(QtCore.QThread):
    """Thread for running analysis in background"""
    
    output_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(dict)
    error_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, subject_configs, analysis_name, config):
        super(AnalysisThread, self).__init__()
        self.subject_configs = subject_configs
        self.analysis_name = analysis_name
        self.config = config
    
    def run(self):
        """Run the analysis"""
        try:
            import time
            start_time = time.time()
            
            # Get path manager
            pm = get_path_manager() if get_path_manager else None
            if not pm:
                raise ValueError("Path manager not available")
            
            project_dir = pm.get_project_dir()
            if not project_dir:
                raise ValueError("Project directory not found")
            
            # Create output directory
            output_base = os.path.join(
                project_dir,
                const.DIR_DERIVATIVES,
                const.DIR_TI_TOOLBOX,
                "nifti_average"
            )
            os.makedirs(output_base, exist_ok=True)
            
            output_dir = os.path.join(output_base, self.analysis_name)
            os.makedirs(output_dir, exist_ok=True)
            
            self.output_signal.emit(f"Output directory: {output_dir}")
            
            # Load subjects organized by groups using core nifti function
            self.output_signal.emit(f"\nLoading subject data...")
            groups_data, template_img, groups_ids = nifti.load_grouped_subjects_ti_toolbox(
                self.subject_configs,
                nifti_file_pattern=self.config['nifti_file_pattern'],
                dtype=np.float32
            )

            self.output_signal.emit(f"\nFound {len(groups_data)} groups:")
            for group_name, data_4d in groups_data.items():
                subject_ids = groups_ids[group_name]
                self.output_signal.emit(f"  • {group_name}: {data_4d.shape[-1]} subjects ({', '.join(subject_ids)})")

            # Compute averages for each group
            group_averages = {}
            group_images = {}

            for group_name, data_4d in groups_data.items():
                self.output_signal.emit(f"\nProcessing group: {group_name}")

                # Compute average
                avg_data = np.mean(data_4d, axis=-1).astype(np.float32)
                group_averages[group_name] = avg_data
                group_images[group_name] = template_img

                # Save group average
                output_filename = f"average_{group_name}.nii.gz"
                output_path = os.path.join(output_dir, output_filename)
                # Save NIfTI file
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                img = nib.Nifti1Image(avg_data, template_img.affine, template_img.header)
                nib.save(img, output_path)
                self.output_signal.emit(f"  ✓ Saved: {output_filename}")

                # Clean up
                del data_4d
                gc.collect()
            
            # Compute differences between groups
            self.output_signal.emit("\nComputing group differences...")
            
            diff_pairs_str = self.config.get('diff_pairs', '').strip()
            differences = []
            
            if diff_pairs_str:
                # Parse user-specified pairs
                pairs = [p.strip() for p in diff_pairs_str.split(',') if p.strip()]
                for pair in pairs:
                    if '-' not in pair:
                        self.output_signal.emit(f"  Warning: Invalid pair format: {pair}")
                        continue
                    
                    parts = pair.split('-')
                    if len(parts) != 2:
                        self.output_signal.emit(f"  Warning: Invalid pair format: {pair}")
                        continue
                    
                    group1, group2 = parts[0].strip(), parts[1].strip()
                    
                    if group1 not in group_averages:
                        self.output_signal.emit(f"  Warning: Group not found: {group1}")
                        continue
                    if group2 not in group_averages:
                        self.output_signal.emit(f"  Warning: Group not found: {group2}")
                        continue
                    
                    # Compute difference
                    diff_data = (group_averages[group1] - group_averages[group2]).astype(np.float32)
                    
                    # Save difference
                    output_filename = f"difference_{group1}_minus_{group2}.nii.gz"
                    output_path = os.path.join(output_dir, output_filename)
                    # Save NIfTI file
                    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                    img = nib.Nifti1Image(diff_data, group_images[group1].affine, group_images[group1].header)
                    nib.save(img, output_path)
                    differences.append(f"{group1} - {group2}")
                    self.output_signal.emit(f"  ✓ Saved: {output_filename}")
            else:
                # Compute all pairwise differences
                group_names = sorted(group_averages.keys())
                for i, group1 in enumerate(group_names):
                    for group2 in group_names[i+1:]:
                        # Compute difference
                        diff_data = (group_averages[group1] - group_averages[group2]).astype(np.float32)
                        
                        # Save difference
                        output_filename = f"difference_{group1}_minus_{group2}.nii.gz"
                        output_path = os.path.join(output_dir, output_filename)
                        # Save NIfTI file
                        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                        img = nib.Nifti1Image(diff_data, group_images[group1].affine, group_images[group1].header)
                        nib.save(img, output_path)
                        differences.append(f"{group1} - {group2}")
                        self.output_signal.emit(f"  ✓ Saved: {output_filename}")
            
            # Save configuration
            config_path = os.path.join(output_dir, "config.json")
            with open(config_path, 'w') as f:
                json.dump({
                    'analysis_name': self.analysis_name,
                    'nifti_pattern': self.config['nifti_file_pattern'],
                    'groups': {group: groups_ids[group] for group in groups_data.keys()},
                    'differences': differences
                }, f, indent=2)
            self.output_signal.emit(f"\n✓ Configuration saved: config.json")
            
            elapsed_time = time.time() - start_time
            
            results = {
                'output_dir': output_dir,
                'groups': list(group_averages.keys()),
                'differences': differences,
                'analysis_time': elapsed_time
            }
            
            self.finished_signal.emit(results)
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
            self.error_signal.emit(error_msg)


class NiftiGroupAverageWindow(QtWidgets.QDialog):
    """Dialog wrapper for the NIfTI group averaging widget (for floating windows)"""

    def __init__(self, parent=None):
        super(NiftiGroupAverageWindow, self).__init__(parent)
        self.setWindowTitle("NIfTI Group Averaging")
        self.setMinimumSize(900, 700)
        self.setWindowFlag(QtCore.Qt.Window)  # Make it a proper window, not modal

        # Create the main widget
        self.widget = NiftiGroupAverageWidget(self)

        # Set up dialog layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)


def main(parent=None):
    """
    Main entry point for the extension.
    This function is called when the extension is launched.
    """
    window = NiftiGroupAverageWindow(parent)
    window.show()
    return window


# Alternative entry point (for flexibility)
def run(parent=None):
    """Alternative entry point."""
    return main(parent)

