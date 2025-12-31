#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: Cluster-Based Permutation Testing
Statistical analysis to identify brain regions with significantly different 
current intensity between responders and non-responders.
"""

import sys
import os
import logging
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui
import json

# Extension metadata (required)
EXTENSION_NAME = "Permutation Analysis"
EXTENSION_DESCRIPTION = "unified cluster-based permutation testing for group comparisons and correlations."


# Add TI-Toolbox to path
ti_toolbox_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ti_toolbox_path))

# Add GUI path for components
gui_path = Path(__file__).parent.parent
sys.path.insert(0, str(gui_path))

from core import get_path_manager
from core import constants as const
from tools import logging_util

from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons


class SubjectRow(QtWidgets.QWidget):
    """Widget for a single subject configuration row"""

    remove_requested = QtCore.pyqtSignal(object)  # Signal to remove this row

    def __init__(self, parent=None, subjects_list=None, simulations_dict=None, mode='classification'):
        super(SubjectRow, self).__init__(parent)
        self.subjects_list = subjects_list or []
        self.simulations_dict = simulations_dict or {}
        self.mode = mode
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

        # Mode-specific input (classification vs correlation)
        if self.mode == 'classification':
            self.response_combo = QtWidgets.QComboBox()
            self.response_combo.addItems(['Responder', 'Non-Responder'])
            layout.addWidget(self.response_combo, 2)
        else:  # correlation
            self.effect_size_edit = QtWidgets.QLineEdit()
            self.effect_size_edit.setPlaceholderText("e.g., 0.85")
            self.effect_size_edit.setValidator(QtGui.QDoubleValidator())
            layout.addWidget(self.effect_size_edit, 2)

        # Remove button
        self.remove_btn = QtWidgets.QPushButton("✕")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.setStyleSheet("""
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
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.remove_btn)

        # Initialize simulations
        self.on_subject_changed(self.subject_combo.currentText())
    
    def on_subject_changed(self, subject_id):
        """Update simulations when subject changes"""
        self.simulation_combo.clear()
        if subject_id in self.simulations_dict:
            self.simulation_combo.addItems(self.simulations_dict[subject_id])
    
    def get_config(self):
        """Get the configuration for this subject"""
        config = {
            'subject_id': self.subject_combo.currentText(),
            'simulation_name': self.simulation_combo.currentText()
        }

        if self.mode == 'classification':
            config['response'] = 1 if self.response_combo.currentText() == 'Responder' else 0
        else:  # correlation
            try:
                config['effect_size'] = float(self.effect_size_edit.text())
            except ValueError:
                config['effect_size'] = 0.0

        return config
    
    def set_config(self, config):
        """Set the configuration for this subject"""
        idx = self.subject_combo.findText(config['subject_id'])
        if idx >= 0:
            self.subject_combo.setCurrentIndex(idx)

        idx = self.simulation_combo.findText(config['simulation_name'])
        if idx >= 0:
            self.simulation_combo.setCurrentIndex(idx)

        if self.mode == 'classification':
            self.response_combo.setCurrentIndex(0 if config['response'] == 1 else 1)
        else:  # correlation
            self.effect_size_edit.setText(str(config.get('effect_size', 0.0)))

class ClusterPermutationWidget(QtWidgets.QWidget):
    """Main widget for cluster-based permutation testing"""

    def __init__(self, parent=None):
        super(ClusterPermutationWidget, self).__init__(parent)
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
        header_label = QtWidgets.QLabel("<h2>Cluster-Based Permutation Testing</h2>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        desc_label = QtWidgets.QLabel(
            "Identify brain regions with significant differences between groups "
            "using non-parametric cluster-based permutation correction."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; padding: 5px;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # === Subject Configuration ===
        self.subjects_group = QtWidgets.QGroupBox("Subject Configuration")
        subjects_layout = QtWidgets.QVBoxLayout(self.subjects_group)

        # Toolbar
        toolbar_layout = QtWidgets.QHBoxLayout()

        # Analysis mode selection
        self.mode_group = QtWidgets.QButtonGroup(self)
        self.classification_radio = QtWidgets.QRadioButton("Classification")
        self.correlation_radio = QtWidgets.QRadioButton("Correlation")
        self.mode_group.addButton(self.classification_radio)
        self.mode_group.addButton(self.correlation_radio)

        # Connect mode change signal (do this after UI setup to avoid triggering during init)
        # self.classification_radio.toggled.connect(self.on_mode_changed)
        # self.correlation_radio.toggled.connect(self.on_mode_changed)

        toolbar_layout.addWidget(self.classification_radio)
        toolbar_layout.addWidget(self.correlation_radio)
        toolbar_layout.addSpacing(20)  # Add some space between mode selection and buttons

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

        # Subject list header (will be updated based on mode)
        self.header_layout = QtWidgets.QHBoxLayout()
        self.update_subject_header()
        header_widget = QtWidgets.QWidget()
        header_widget.setLayout(self.header_layout)
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
        
        layout.addWidget(self.subjects_group)
        
        # === Analysis Configuration ===
        self.config_group = QtWidgets.QGroupBox("Analysis Configuration")
        self.config_layout = QtWidgets.QGridLayout(self.config_group)

        # Initialize UI components (will be populated based on mode)
        self.setup_config_ui()

        layout.addWidget(self.config_group)

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
                max_height=None,
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

        # Connect mode change signals after UI is fully set up
        self.classification_radio.toggled.connect(self.on_mode_changed)
        self.correlation_radio.toggled.connect(self.on_mode_changed)
        self.classification_radio.setChecked(True)  # Default to classification (after connecting signals)

    def update_output(self, message, msg_type='default'):
        """Update output console with message"""
        if hasattr(self, 'console_widget') and self.console_widget:
            self.console_widget.update_console(message, msg_type)
        elif hasattr(self, 'output_text') and self.output_text:
            self.output_text.append(message)
    
    def on_mode_changed(self):
        """Handle mode change between classification and correlation"""
        # Update header
        self.update_subject_header()

        # Update config UI
        self.setup_config_ui()

        # Convert existing subject rows to new mode
        for row in self.subject_rows[:]:  # Copy list to avoid issues during iteration
            # Remove and re-add row to update its UI
            self.subjects_container_layout.removeWidget(row)
            row.deleteLater()
            self.subject_rows.remove(row)

            # Create new row with updated mode
            new_row = SubjectRow(
                parent=self,
                subjects_list=self.subjects_list,
                simulations_dict=self.simulations_dict,
                mode=self.get_current_mode()
            )
            new_row.remove_requested.connect(self.remove_subject_row)

            # Insert at the end (before stretch)
            self.subjects_container_layout.insertWidget(
                len(self.subject_rows), new_row
            )
            self.subject_rows.append(new_row)

    def setup_config_ui(self):
        """Set up the analysis configuration UI based on current mode"""
        # Clear existing config layout
        while self.config_layout.count():
            item = self.config_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row = 0
        mode = self.get_current_mode()

        # Left column - Analysis name
        self.config_layout.addWidget(QtWidgets.QLabel("Analysis Name:"), row, 0)
        self.analysis_name_edit = QtWidgets.QLineEdit()
        if mode == 'classification':
            self.analysis_name_edit.setPlaceholderText("e.g., hippocampus_responders_vs_nonresponders")
        else:
            self.analysis_name_edit.setPlaceholderText("e.g., hippocampus_effect_size_correlation")
        self.config_layout.addWidget(self.analysis_name_edit, row, 1)

        # Right column - NIfTI file pattern
        self.config_layout.addWidget(QtWidgets.QLabel("NIfTI Pattern:"), row, 2)
        self.nifti_pattern_edit = QtWidgets.QLineEdit()
        self.nifti_pattern_edit.setText("grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz")
        self.nifti_pattern_edit.setToolTip("Use {simulation_name} as a variable (subject is in directory path)")
        self.config_layout.addWidget(self.nifti_pattern_edit, row, 3)
        row += 1

        if mode == 'classification':
            # Test type
            self.config_layout.addWidget(QtWidgets.QLabel("Test Type:"), row, 0)
            self.test_type_combo = QtWidgets.QComboBox()
            self.test_type_combo.addItems(['Unpaired', 'Paired'])
            self.config_layout.addWidget(self.test_type_combo, row, 1)

            # Alternative hypothesis
            self.config_layout.addWidget(QtWidgets.QLabel("Alternative:"), row, 2)
            self.alternative_combo = QtWidgets.QComboBox()
            self.alternative_combo.addItems(['Two-sided', 'Greater', 'Less'])
            self.alternative_combo.setToolTip("Two-sided: ≠, Greater: Resp > Non-Resp, Less: Resp < Non-Resp")
            self.config_layout.addWidget(self.alternative_combo, row, 3)
            row += 1
        else:  # correlation
            # Correlation type
            self.config_layout.addWidget(QtWidgets.QLabel("Correlation Type:"), row, 0)
            self.correlation_type_combo = QtWidgets.QComboBox()
            self.correlation_type_combo.addItems(['Pearson', 'Spearman'])
            self.config_layout.addWidget(self.correlation_type_combo, row, 1)

            # Use weights
            self.config_layout.addWidget(QtWidgets.QLabel("Use Weights:"), row, 2)
            self.use_weights_check = QtWidgets.QCheckBox()
            self.use_weights_check.setChecked(True)
            self.use_weights_check.setToolTip("Use weights from CSV if available")
            self.config_layout.addWidget(self.use_weights_check, row, 3)
            row += 1

            # Alternative hypothesis (for correlation)
            self.config_layout.addWidget(QtWidgets.QLabel("Alternative:"), row, 0)
            self.correlation_alternative_combo = QtWidgets.QComboBox()
            self.correlation_alternative_combo.addItems(['Two-sided', 'Greater (Positive)', 'Less (Negative)'])
            self.correlation_alternative_combo.setToolTip(
                "Two-sided: Test both positive and negative correlations\n"
                "Greater: Test positive correlations only (one-tailed, uses full alpha)\n"
                "Less: Test negative correlations only (one-tailed, uses full alpha)"
            )
            self.config_layout.addWidget(self.correlation_alternative_combo, row, 1, 1, 3)
            row += 1

        # Common configuration options for both modes
        # Left column - Cluster threshold
        self.config_layout.addWidget(QtWidgets.QLabel("Cluster Threshold:"), row, 0)
        self.cluster_threshold_spin = QtWidgets.QDoubleSpinBox()
        self.cluster_threshold_spin.setRange(0.001, 0.1)
        self.cluster_threshold_spin.setValue(0.05)
        self.cluster_threshold_spin.setSingleStep(0.01)
        self.cluster_threshold_spin.setDecimals(3)
        self.config_layout.addWidget(self.cluster_threshold_spin, row, 1)

        # Right column - Cluster statistic
        self.config_layout.addWidget(QtWidgets.QLabel("Cluster Statistic:"), row, 2)
        self.cluster_stat_combo = QtWidgets.QComboBox()
        self.cluster_stat_combo.addItems(['Mass', 'Size'])
        self.cluster_stat_combo.setToolTip("Mass: sum of t-values, Size: voxel count")
        self.config_layout.addWidget(self.cluster_stat_combo, row, 3)
        row += 1

        # Left column - Number of permutations
        self.config_layout.addWidget(QtWidgets.QLabel("Permutations:"), row, 0)
        self.n_permutations_spin = QtWidgets.QSpinBox()
        self.n_permutations_spin.setRange(10, 10000)
        self.n_permutations_spin.setValue(1000)
        self.config_layout.addWidget(self.n_permutations_spin, row, 1)

        # Right column - Alpha level
        self.config_layout.addWidget(QtWidgets.QLabel("Alpha Level:"), row, 2)
        self.alpha_spin = QtWidgets.QDoubleSpinBox()
        self.alpha_spin.setRange(0.001, 0.1)
        self.alpha_spin.setValue(0.05)
        self.alpha_spin.setSingleStep(0.01)
        self.alpha_spin.setDecimals(3)
        self.config_layout.addWidget(self.alpha_spin, row, 3)
        row += 1

        # Left column (full width for parallel jobs)
        self.config_layout.addWidget(QtWidgets.QLabel("Parallel Jobs:"), row, 0)
        self.n_jobs_edit = QtWidgets.QLineEdit()
        import multiprocessing
        max_cores = multiprocessing.cpu_count()
        self.n_jobs_edit.setPlaceholderText(f"available cores: 1 to {max_cores} (all cores)")
        # Set up input validation - only integers from 1 to max_cores
        self.n_jobs_edit.setValidator(QtGui.QIntValidator(1, max_cores, self.n_jobs_edit))
        self.n_jobs_edit.setToolTip(
            "Number of CPU cores to use for parallel processing.\n"
            f"Accepted input: 1 to {max_cores} (all cores)\n"
            "No characters or negative numbers accepted.\n\n"
            "Note: In Docker containers, this may be automatically limited\n"
            "to 75% of available cores to prevent memory exhaustion.\n"
            "Threading libraries are set to single-threaded mode per worker\n"
            "to avoid CPU oversubscription."
        )
        self.config_layout.addWidget(self.n_jobs_edit, row, 1, 1, 3)

    def update_subject_header(self):
        """Update the subject list header based on current mode"""
        # Clear existing header widgets
        while self.header_layout.count():
            item = self.header_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new header based on mode
        self.header_layout.addWidget(QtWidgets.QLabel("<b>Subject</b>"), 2)
        self.header_layout.addWidget(QtWidgets.QLabel("<b>Simulation</b>"), 3)

        if self.get_current_mode() == 'classification':
            self.header_layout.addWidget(QtWidgets.QLabel("<b>Classification</b>"), 2)
        else:  # correlation
            self.header_layout.addWidget(QtWidgets.QLabel("<b>Effect Size</b>"), 2)

        self.header_layout.addWidget(QtWidgets.QLabel(""), 0)  # For remove button

    def get_current_mode(self):
        """Get current analysis mode"""
        return 'correlation' if self.correlation_radio.isChecked() else 'classification'

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
        row = SubjectRow(parent=self, subjects_list=self.subjects_list,
                        simulations_dict=self.simulations_dict, mode=self.get_current_mode())
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
            
            # Read CSV
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                mode = self.get_current_mode()

                # Validate CSV format based on mode
                if mode == 'classification':
                    required_cols = ['subject_id', 'simulation_name', 'response']
                else:  # correlation
                    required_cols = ['subject_id', 'simulation_name', 'effect_size']

                missing_cols = [col for col in required_cols if col not in reader.fieldnames]
                if missing_cols:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Invalid CSV Format",
                        f"CSV file missing required columns for {mode} analysis: {', '.join(missing_cols)}"
                    )
                    return

                for row_data in reader:
                    # Create new row
                    row = SubjectRow(parent=self, subjects_list=self.subjects_list,
                                   simulations_dict=self.simulations_dict, mode=mode)
                    row.remove_requested.connect(self.remove_subject_row)

                    # Set configuration based on mode
                    if mode == 'classification':
                        config = {
                            'subject_id': row_data['subject_id'].replace('sub-', ''),
                            'simulation_name': row_data['simulation_name'],
                            'response': int(row_data['response'])
                        }
                    else:  # correlation
                        config = {
                            'subject_id': row_data['subject_id'].replace('sub-', ''),
                            'simulation_name': row_data['simulation_name'],
                            'effect_size': float(row_data['effect_size'])
                        }
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

            mode = self.get_current_mode()
            if mode == 'classification':
                fieldnames = ['subject_id', 'simulation_name', 'response']
            else:  # correlation
                fieldnames = ['subject_id', 'simulation_name', 'effect_size']

            with open(file_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
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
        """Run the cluster-based permutation analysis"""
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

        # Get current mode
        mode = self.get_current_mode()

        # Collect and validate subject configurations
        subject_configs = []
        if mode == 'classification':
            n_responders = 0
            n_non_responders = 0

            for row in self.subject_rows:
                config = row.get_config()
                subject_configs.append(config)
                if config['response'] == 1:
                    n_responders += 1
                else:
                    n_non_responders += 1

            if n_responders == 0 or n_non_responders == 0:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Configuration",
                    "You need at least one responder and one non-responder."
                )
                return
        else:  # correlation
            # Validate effect sizes are numeric and varied
            effect_sizes = []
            for row in self.subject_rows:
                config = row.get_config()
                subject_configs.append(config)
                effect_sizes.append(config['effect_size'])

            if len(set(effect_sizes)) < 2:  # All effect sizes are the same
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Configuration",
                    "Effect sizes must vary across subjects for correlation analysis."
                )
                return
        
        # Build configuration
        config = {
            'analysis_type': 'group_comparison' if mode == 'classification' else mode,
            'cluster_threshold': self.cluster_threshold_spin.value(),
            'cluster_stat': self.cluster_stat_combo.currentText().lower(),
            'n_permutations': self.n_permutations_spin.value(),
            'alpha': self.alpha_spin.value(),
            'n_jobs': int(self.n_jobs_edit.text()) if self.n_jobs_edit.text() else 1,
            'nifti_file_pattern': self.nifti_pattern_edit.text()
        }

        if mode == 'classification':
            config.update({
                'test_type': self.test_type_combo.currentText().lower(),
                'alternative': self.alternative_combo.currentText().lower(),  # 'two-sided', 'greater', or 'less'
            })
        else:  # correlation
            # Map GUI text to API values
            alt_text = self.correlation_alternative_combo.currentText()
            if 'Greater' in alt_text:
                alternative = 'greater'
            elif 'Less' in alt_text:
                alternative = 'less'
            else:
                alternative = 'two-sided'

            config.update({
                'correlation_type': self.correlation_type_combo.currentText().lower(),
                'use_weights': self.use_weights_check.isChecked(),
                'alternative': alternative,  # Add alternative hypothesis for correlation
            })
        
        analysis_name = self.analysis_name_edit.text().strip()
        
        # Show confirmation
        if mode == 'classification':
            subject_info = f"  • {len(subject_configs)} subjects ({n_responders} responders, {n_non_responders} non-responders)\n"
            analysis_info = f"  • Test type: {config['test_type']}\n"
            analysis_info += f"  • Alternative: {config['alternative']}\n"
        else:  # correlation
            subject_info = f"  • {len(subject_configs)} subjects\n"
            analysis_info = f"  • Correlation type: {config['correlation_type']}\n"
            analysis_info += f"  • Alternative: {config['alternative']}\n"
            analysis_info += f"  • Use weights: {config['use_weights']}\n"

        reply = QtWidgets.QMessageBox.question(
            self,
            "Run Analysis",
            f"Run {mode} analysis with:\n\n"
            f"{subject_info}"
            f"{analysis_info}"
            f"  • {config['n_permutations']} permutations\n"
            f"  • Analysis name: {analysis_name}\n\n"
            f"This may take several minutes. Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Disable run button, enable stop button
        if hasattr(self, 'action_buttons'):
            self.action_buttons.enable_stop()
        elif hasattr(self, 'run_btn'):
            self.run_btn.setEnabled(False)

        # Lock GUI interface during processing
        if hasattr(self, 'parent_window') and self.parent_window and hasattr(self.parent_window, 'set_tab_busy'):
            keep_enabled = []
            if hasattr(self, 'console_widget') and self.console_widget and hasattr(self.console_widget, 'debug_checkbox'):
                keep_enabled = [self.console_widget.debug_checkbox]
            stop_btn = getattr(self, 'action_buttons', None)
            if stop_btn:
                stop_btn = stop_btn.get_stop_button()
            self.parent_window.set_tab_busy(self, True, stop_btn=stop_btn, keep_enabled=keep_enabled)

        # Disable input controls (grey them out)
        self.disable_controls()

        # Clear console
        if hasattr(self, 'console_widget') and self.console_widget:
            self.console_widget.clear_console()
        elif hasattr(self, 'output_text') and self.output_text:
            self.output_text.clear()
        self.update_output("Starting analysis...", 'info')
        
        # Run in thread
        console_widget = getattr(self, 'console_widget', None)
        self.worker_thread = AnalysisThread(subject_configs, analysis_name, config, console_widget)
        self.worker_thread.output_signal.connect(self.on_output)
        self.worker_thread.finished_signal.connect(self.on_finished)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.start()
    
    def stop_analysis(self):
        """Stop the running analysis."""
        if hasattr(self, 'worker_thread') and self.worker_thread and self.worker_thread.isRunning():
            self.update_output("\nStopping analysis...", 'warning')
            self.worker_thread.request_stop()
            # Wait for thread to finish gracefully, but with a timeout
            if not self.worker_thread.wait(5000):  # 5 second timeout
                self.update_output("Force terminating analysis...", 'warning')
                self.worker_thread.terminate()
                self.worker_thread.wait()
            self.update_output("Analysis stopped by user.", 'warning')

            # Unlock GUI interface
            if hasattr(self, 'parent_window') and self.parent_window and hasattr(self.parent_window, 'set_tab_busy'):
                self.parent_window.set_tab_busy(self, False)

            # Re-enable input controls
            self.enable_controls()

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
        # Unlock GUI interface
        if hasattr(self, 'parent_window') and self.parent_window and hasattr(self.parent_window, 'set_tab_busy'):
            self.parent_window.set_tab_busy(self, False)

        # Re-enable input controls
        self.enable_controls()

        # Re-enable run button
        if hasattr(self, 'action_buttons'):
            self.action_buttons.enable_run()
        elif hasattr(self, 'run_btn'):
            self.run_btn.setEnabled(True)

        # Check if analysis was stopped by user
        if results.get('stopped_by_user', False):
            self.update_output("\n" + "="*50, 'warning')
            self.update_output("ANALYSIS STOPPED BY USER", 'warning')
            self.update_output("="*50, 'warning')
            return

        self.update_output("\n" + "="*50, 'success')
        self.update_output("ANALYSIS COMPLETE!", 'success')
        self.update_output("="*50, 'success')
        self.update_output(f"Output directory: {results['output_dir']}", 'info')
        self.update_output(f"Significant clusters: {results['n_significant_clusters']}", 'info')
        self.update_output(f"Significant voxels: {results['n_significant_voxels']}", 'info')
        self.update_output(f"Analysis time: {results['analysis_time']:.1f} seconds", 'info')

        QtWidgets.QMessageBox.information(
            self,
            "Analysis Complete",
            f"Analysis completed successfully!\n\n"
            f"Found {results['n_significant_clusters']} significant cluster(s)\n"
            f"with {results['n_significant_voxels']} significant voxels.\n\n"
            f"Results saved to:\n{results['output_dir']}"
        )
    
    def on_error(self, error_msg):
        """Handle analysis error"""
        # Unlock GUI interface
        if hasattr(self, 'parent_window') and self.parent_window and hasattr(self.parent_window, 'set_tab_busy'):
            self.parent_window.set_tab_busy(self, False)

        # Re-enable input controls
        self.enable_controls()

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

    def disable_controls(self):
        """Disable all input controls during analysis."""
        # Disable mode selection
        self.classification_radio.setEnabled(False)
        self.correlation_radio.setEnabled(False)

        # Disable analysis configuration inputs
        self.analysis_name_edit.setEnabled(False)
        self.nifti_pattern_edit.setEnabled(False)

        mode = self.get_current_mode()
        if mode == 'classification':
            self.test_type_combo.setEnabled(False)
            self.alternative_combo.setEnabled(False)
        else:  # correlation
            self.correlation_type_combo.setEnabled(False)
            self.correlation_alternative_combo.setEnabled(False)
            self.use_weights_check.setEnabled(False)

        self.cluster_threshold_spin.setEnabled(False)
        self.cluster_stat_combo.setEnabled(False)
        self.n_permutations_spin.setEnabled(False)
        self.alpha_spin.setEnabled(False)
        self.n_jobs_edit.setEnabled(False)

        # Disable subject-simulation combo boxes and remove buttons
        for row in self.subject_rows:
            row.subject_combo.setEnabled(False)
            row.simulation_combo.setEnabled(False)
            if hasattr(row, 'response_combo'):
                row.response_combo.setEnabled(False)
            if hasattr(row, 'effect_size_edit'):
                row.effect_size_edit.setEnabled(False)
            row.remove_btn.setEnabled(False)

        # Disable toolbar buttons (store references for re-enabling)
        if not hasattr(self, '_toolbar_buttons'):
            # Store button references on first call
            self._toolbar_buttons = []
            for i in range(self.subjects_group.layout().itemAt(0).layout().count()):
                item = self.subjects_group.layout().itemAt(0).layout().itemAt(i)
                if item and item.widget() and isinstance(item.widget(), QtWidgets.QPushButton):
                    self._toolbar_buttons.append(item.widget())

        # Disable toolbar buttons
        for btn in self._toolbar_buttons:
            btn.setEnabled(False)

    def enable_controls(self):
        """Enable all input controls after analysis."""
        # Enable mode selection
        self.classification_radio.setEnabled(True)
        self.correlation_radio.setEnabled(True)

        # Enable analysis configuration inputs
        self.analysis_name_edit.setEnabled(True)
        self.nifti_pattern_edit.setEnabled(True)

        mode = self.get_current_mode()
        if mode == 'classification':
            self.test_type_combo.setEnabled(True)
            self.alternative_combo.setEnabled(True)
        else:  # correlation
            self.correlation_type_combo.setEnabled(True)
            self.correlation_alternative_combo.setEnabled(True)
            self.use_weights_check.setEnabled(True)

        self.cluster_threshold_spin.setEnabled(True)
        self.cluster_stat_combo.setEnabled(True)
        self.n_permutations_spin.setEnabled(True)
        self.alpha_spin.setEnabled(True)
        self.n_jobs_edit.setEnabled(True)

        # Enable subject-simulation combo boxes and remove buttons
        for row in self.subject_rows:
            row.subject_combo.setEnabled(True)
            row.simulation_combo.setEnabled(True)
            if hasattr(row, 'response_combo'):
                row.response_combo.setEnabled(True)
            if hasattr(row, 'effect_size_edit'):
                row.effect_size_edit.setEnabled(True)
            row.remove_btn.setEnabled(True)

        # Enable toolbar buttons
        if hasattr(self, '_toolbar_buttons'):
            for btn in self._toolbar_buttons:
                btn.setEnabled(True)


class AnalysisThread(QtCore.QThread):
    """Thread for running analysis in background"""
    
    output_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(dict)
    error_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, subject_configs, analysis_name, config, console_widget=None):
        super(AnalysisThread, self).__init__()
        self.subject_configs = subject_configs
        self.analysis_name = analysis_name
        self.config = config
        self.console_widget = console_widget
        self.stop_requested = False

    def request_stop(self):
        """Request the analysis to stop gracefully."""
        self.stop_requested = True

    def run(self):
        """Run the analysis"""
        try:
            # Import unified permutation_analysis module
            from stats import permutation_analysis

            # Set up callback handler for GUI console integration
            callback_handler = None
            if logging_util:
                # Create a custom handler that emits signals to the main thread
                class GUILogHandler(logging.Handler):
                    def __init__(self, emit_signal_func):
                        super().__init__()
                        self.emit_signal = emit_signal_func
                        self._is_gui_handler = True  # Mark as GUI handler to skip copying

                    def emit(self, record):
                        try:
                            msg = self.format(record)
                            # Emit signal instead of directly calling GUI methods
                            self.emit_signal(msg)
                        except Exception:
                            self.handleError(record)

                def emit_output_signal(message):
                    self.output_signal.emit(message)

                callback_handler = GUILogHandler(emit_output_signal)

            # Ensure analysis type is set in config (default to group_comparison for backward compatibility)
            if 'analysis_type' not in self.config:
                self.config['analysis_type'] = 'group_comparison'

            # Run analysis with callback handler for logging integration
            results = permutation_analysis.run_analysis(
                subject_configs=self.subject_configs,
                analysis_name=self.analysis_name,
                config=self.config,
                callback_handler=callback_handler,
                stop_callback=lambda: self.stop_requested
            )

            self.finished_signal.emit(results)

        except KeyboardInterrupt:
            # Analysis was stopped by user - this is expected
            self.finished_signal.emit({
                'output_dir': None,
                'n_significant_clusters': 0,
                'n_significant_voxels': 0,
                'analysis_time': 0,
                'stopped_by_user': True
            })

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
            self.error_signal.emit(error_msg)


class ClusterPermutationWindow(QtWidgets.QDialog):
    """Dialog wrapper for the cluster-based permutation testing widget (for floating windows)"""

    def __init__(self, parent=None):
        super(ClusterPermutationWindow, self).__init__(parent)
        self.setWindowTitle("Cluster-Based Permutation Testing")
        self.setMinimumSize(900, 700)
        self.setWindowFlag(QtCore.Qt.Window)  # Make it a proper window, not modal

        # Create the main widget
        self.widget = ClusterPermutationWidget(self)

        # Set up dialog layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)


def main(parent=None):
    """
    Main entry point for the extension.
    This function is called when the extension is launched.
    """
    window = ClusterPermutationWindow(parent)
    window.show()
    return window


# Alternative entry point (for flexibility)
def run(parent=None):
    """Alternative entry point."""
    main(parent)

