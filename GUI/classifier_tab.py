#!/usr/bin/env python3
"""
Classifier Tab for TI-Toolbox GUI

Voxel-wise classification with threading and enhanced parameter control.
"""

import sys
import os
import traceback
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pandas as pd
from pathlib import Path
import joblib
import subprocess
import time

# Add classifier module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class ClassifierThread(QtCore.QThread):
    """Thread to run classifier training in background to prevent GUI freezing."""
    
    # Signal to emit output text with message type
    output_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(bool)  # success/failure
    
    def __init__(self, project_dir, csv_file, resolution, n_permutations, p_threshold, n_jobs, 
                 use_roi_features=False, atlas_name="HarvardOxford-cort-maxprob-thr0-1mm"):
        """Initialize the thread with training parameters."""
        super(ClassifierThread, self).__init__()
        self.project_dir = project_dir
        self.csv_file = csv_file
        self.resolution = resolution
        self.n_permutations = n_permutations
        self.p_threshold = p_threshold
        self.n_jobs = n_jobs
        self.use_roi_features = use_roi_features
        self.atlas_name = atlas_name
        self.process = None
        self.terminated = False
        
    def _strip_ansi_codes(self, text):
        """Remove ANSI color codes from text."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
        
    def run(self):
        """Run the classifier training in a separate thread."""
        try:
            # Import here to avoid issues with threading
            from classifier.ti_classifier import TIClassifier
            
            self.output_signal.emit("Initializing TI classifier...", "info")
            self.output_signal.emit(f"Using atlas: {self.atlas_name}", "info")
            
            # Initialize classifier with parameters
            classifier = TIClassifier(
                project_dir=str(self.project_dir),
                resolution_mm=self.resolution,
                p_value_threshold=self.p_threshold,
                n_jobs=self.n_jobs,
                use_roi_features=self.use_roi_features,
                atlas_name=self.atlas_name
            )
            
            if self.terminated:
                return
                
            self.output_signal.emit(f"Loading training data from: {self.csv_file}", "info")
            
            if self.terminated:
                return
            
            self.output_signal.emit("Training classifier...", "info")
            self.output_signal.emit("", "info")
            
            # Train the classifier (new modular approach handles everything)
            results = classifier.train(str(self.csv_file))
            
            if self.terminated:
                return
                
            if results:
                # Check if training was successful
                n_significant = results.get('significant_voxels', 0)  # Note: different key name
                
                # Display detailed results
                self.output_signal.emit("="*80, "info")
                self.output_signal.emit("TRAINING RESULTS", "info")
                self.output_signal.emit("="*80, "info")
                self.output_signal.emit("", "info")
                
                if n_significant == 0:
                    self.output_signal.emit("⚠️ ZERO SIGNIFICANT VOXELS FOUND", "error")
                    self.output_signal.emit("", "error")
                    self.output_signal.emit("Possible solutions:", "warning")
                    self.output_signal.emit("1. Try a less stringent p-value (0.01 instead of 0.001)", "warning")
                    self.output_signal.emit("2. Check if your response data has sufficient contrast", "warning")
                    self.output_signal.emit("3. Verify NIfTI files contain valid current density data", "warning")
                    self.output_signal.emit("4. Consider that TI fields are naturally very focal", "warning")
                    self.output_signal.emit("", "warning")
                
                # Performance metrics
                self.output_signal.emit("📊 Performance:", "info")
                
                # Get performance data from nested structure
                performance = results.get('performance', {})
                accuracy = performance.get('cv_accuracy', 0)
                accuracy_std = performance.get('cv_std', 0)
                roc_auc = performance.get('roc_auc', 0)
                best_c = performance.get('best_C', 'N/A')  # Note: capital C
                
                self.output_signal.emit(f"  • Accuracy: {accuracy:.1f}% ± {accuracy_std:.1f}%", "info")
                self.output_signal.emit(f"  • ROC-AUC: {roc_auc:.3f}", "info")
                self.output_signal.emit(f"  • Best C: {best_c}", "info")
                self.output_signal.emit("", "info")
                
                # Feature selection results
                n_significant = results.get('significant_voxels', 0)  # Note: different key name
                total_voxels = results.get('total_voxels', 0)
                percentage = (n_significant / max(total_voxels, 1)) * 100
                
                # Add warning for zero significant voxels
                if n_significant == 0:
                    self.output_signal.emit("⚠️ Warning: No significant voxels found!", "warning")
                    self.output_signal.emit("This may indicate:", "warning")
                    self.output_signal.emit("  • P-value threshold too stringent (try 0.01 instead of 0.001)", "warning")
                    self.output_signal.emit("  • Insufficient sample size or weak signal", "warning")
                    self.output_signal.emit("  • TI fields may be too focal for this analysis", "warning")
                    self.output_signal.emit("", "warning")
                
                self.output_signal.emit("🔬 Feature Selection:", "info")
                self.output_signal.emit(f"  • Total voxels: {total_voxels:,}", "info")
                self.output_signal.emit(f"  • Significant voxels: {n_significant:,}", "info")
                self.output_signal.emit(f"  • Percentage: {percentage:.2f}%", "info")
                self.output_signal.emit("", "info")
                
                # Top brain regions
                self.output_signal.emit("🧠 Top Brain Regions:", "info")
                
                if 'roi_contributions' in results:
                    roi_data = results['roi_contributions']
                    
                    # Check if we have the expected structure
                    if 'top_10_rois' in roi_data and roi_data['top_10_rois']:
                        top_rois = roi_data['top_10_rois']
                        try:
                            for i, (roi_name, roi_info) in enumerate(top_rois[:5], 1):
                                if isinstance(roi_info, dict) and 'contribution' in roi_info and 'type' in roi_info:
                                    contribution = roi_info['contribution']
                                    response_type = roi_info['type']
                                    self.output_signal.emit(f"  {i}. {roi_name}: {contribution:.2f}% ({response_type})", "info")
                                else:
                                    # Handle any other format
                                    self.output_signal.emit(f"  {i}. {roi_name}: {roi_info}", "info")
                        except Exception as e:
                            self.output_signal.emit(f"  Error displaying ROI data: {str(e)}", "warning")
                    else:
                        # Check if roi_contributions has direct ROI data
                        if isinstance(roi_data, dict) and 'roi_contributions' in roi_data:
                            roi_contribs = roi_data['roi_contributions']
                            if roi_contribs:
                                # Sort by contribution and take top 5
                                sorted_rois = sorted(roi_contribs.items(), key=lambda x: x[1]['contribution'], reverse=True)[:5]
                                for i, (roi_name, roi_info) in enumerate(sorted_rois, 1):
                                    contribution = roi_info['contribution']
                                    response_type = roi_info['type']
                                    self.output_signal.emit(f"  {i}. {roi_name}: {contribution:.2f}% ({response_type})", "info")
                            else:
                                self.output_signal.emit("  No ROI contributions found", "warning")
                        else:
                            self.output_signal.emit("  ROI analysis structure not recognized", "warning")
                else:
                    if n_significant == 0:
                        self.output_signal.emit("  No significant voxels found - no ROI analysis available", "warning")
                    else:
                        self.output_signal.emit("  ROI contributions not found in results", "warning")
                
                self.output_signal.emit("", "info")
                
                # Model save location - construct from results directory
                results_dir = self.project_dir / "derivatives" / "ti-toolbox" / "classifier" / "results"
                model_path = results_dir / "voxelwise_model.pkl"
                if model_path.exists():
                    self.output_signal.emit(f"✓ Model saved to: {model_path}", "success")
                else:
                    self.output_signal.emit("✓ Model saved to: {results_dir}/voxelwise_model.pkl", "success")
                self.output_signal.emit("", "info")
                
                # Generated files - list the standard files that should be created
                self.output_signal.emit("📁 Generated Files:", "info")
                
                self.output_signal.emit("  Model & Analysis:", "info")
                self.output_signal.emit("    • voxelwise_model.pkl", "info")
                self.output_signal.emit("    • roi_contributions.csv", "info")
                self.output_signal.emit("    • performance_metrics.csv", "info")
                
                self.output_signal.emit("  MNI Space NIfTI Maps:", "info")
                self.output_signal.emit("    • t_statistics_MNI.nii.gz", "info")
                self.output_signal.emit("    • p_values_MNI.nii.gz", "info")
                self.output_signal.emit("    • svm_weights_MNI.nii.gz", "info")
                self.output_signal.emit("    • significant_voxels_mask_MNI.nii.gz", "info")
                
                self.output_signal.emit("  Group Averages:", "info")
                self.output_signal.emit("    • average_responders_MNI.nii.gz", "info")
                self.output_signal.emit("    • average_nonresponders_MNI.nii.gz", "info")
                self.output_signal.emit("    • difference_resp_vs_nonresp_MNI.nii.gz", "info")
                
                self.output_signal.emit("", "info")
                self.finished_signal.emit(True)
            else:
                self.output_signal.emit("Training failed - no results returned", "error")
                self.finished_signal.emit(False)
                
        except Exception as e:
            if not self.terminated:
                error_msg = f"Error during training: {str(e)}"
                self.output_signal.emit(error_msg, "error")
                self.error_signal.emit(error_msg)
                self.finished_signal.emit(False)
    
    def stop(self):
        """Stop the classifier training."""
        self.terminated = True
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                if self.process:
                    self.process.kill()
        self.quit()
        self.wait()


class ClassifierTab(QtWidgets.QWidget):
    """GUI tab for voxel-wise TI classification with enhanced parameter control."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.project_dir = self._detect_project_dir()
        self.classifier = None
        self.trained_model_path = None
        self.training_thread = None
        self.training_running = False
        
        self.init_ui()
    
    def _detect_project_dir(self) -> Path:
        """Detect the project directory."""
        # Try environment variable first
        project_dir = os.environ.get('PROJECT_DIR')
        if project_dir and os.path.isdir(project_dir):
            return Path(project_dir)
        
        # Try Docker mount
        if os.path.isdir("/mnt"):
            for dir_name in os.listdir("/mnt"):
                dir_path = Path("/mnt") / dir_name
                if dir_path.is_dir():
                    # Check for BIDS structure
                    if (dir_path / "sourcedata").exists() or (dir_path / "derivatives").exists():
                        return dir_path
        
        # Try current directory
        return Path.cwd()
    
    def init_ui(self):
        """Initialize the user interface."""
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)
        
        # Add status label at the top (initially hidden)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setText("Processing... Only the Stop button is available")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: red;
                font-weight: bold;
                padding: 10px;
                margin: 5px;
                border: 2px solid red;
                border-radius: 5px;
            }
        """)
        self.status_label.hide()  # Initially hidden
        main_layout.addWidget(self.status_label)
        
        # Create scroll area for main content
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout()
        
        # Project info
        info_group = QtWidgets.QGroupBox("Project Information")
        info_layout = QtWidgets.QVBoxLayout()
        
        proj_layout = QtWidgets.QHBoxLayout()
        proj_layout.addWidget(QtWidgets.QLabel("Project:"))
        self.project_label = QtWidgets.QLabel(str(self.project_dir.name))
        self.project_label.setStyleSheet("font-weight: bold; color: #2E8B57;")
        proj_layout.addWidget(self.project_label, 1)
        info_layout.addLayout(proj_layout)
        
        # Data directory
        self.data_dir = self.project_dir / "derivatives" / "ti-toolbox" / "classifier" / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Results directory
        self.results_dir = self.project_dir / "derivatives" / "ti-toolbox" / "classifier" / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        info_group.setLayout(info_layout)
        scroll_layout.addWidget(info_group)
        
        # Training Section
        train_group = QtWidgets.QGroupBox("Training Data")
        train_layout = QtWidgets.QVBoxLayout()
        
        # Training file selection
        train_file_layout = QtWidgets.QHBoxLayout()
        train_file_layout.addWidget(QtWidgets.QLabel("Training CSV:"))
        self.train_combo = QtWidgets.QComboBox()
        self.train_combo.currentTextChanged.connect(self.on_train_file_changed)
        train_file_layout.addWidget(self.train_combo, 1)
        
        train_browse_btn = QtWidgets.QPushButton("Browse")
        train_browse_btn.clicked.connect(lambda: self.browse_csv_file("train"))
        train_file_layout.addWidget(train_browse_btn)
        
        train_layout.addLayout(train_file_layout)
        
        # Training info label
        self.train_info_label = QtWidgets.QLabel("No file selected")
        self.train_info_label.setStyleSheet("color: #666; padding: 5px;")
        train_layout.addWidget(self.train_info_label)
        
        train_group.setLayout(train_layout)
        scroll_layout.addWidget(train_group)
        
        # Advanced Settings
        advanced_group = QtWidgets.QGroupBox("Advanced Settings")
        advanced_layout = QtWidgets.QGridLayout()
        
        # Help button in top-right of advanced settings
        help_btn = QtWidgets.QPushButton("?")
        help_btn.setFixedSize(20, 20)
        help_btn.setToolTip("Click for help about voxel-wise classification and parameters")
        help_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: black;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #2196F3;
            }
        """)
        help_btn.clicked.connect(self.show_help)
        advanced_layout.addWidget(help_btn, 0, 4, QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
        
        # Resolution setting
        advanced_layout.addWidget(QtWidgets.QLabel("Resolution:"), 0, 0)
        self.resolution_combo = QtWidgets.QComboBox()
        self.resolution_combo.addItems(["1mm (original)", "2mm", "3mm", "4mm"])
        self.resolution_combo.setToolTip("Voxel resolution for analysis")
        advanced_layout.addWidget(self.resolution_combo, 0, 1)
        
        # Number of permutations
        advanced_layout.addWidget(QtWidgets.QLabel("Permutations:"), 0, 2)
        self.perm_spinbox = QtWidgets.QSpinBox()
        self.perm_spinbox.setRange(3, 20)
        self.perm_spinbox.setValue(10)
        self.perm_spinbox.setToolTip("Number of permutations for nested cross-validation (3-20)")
        advanced_layout.addWidget(self.perm_spinbox, 0, 3)
        
        # Atlas selection
        advanced_layout.addWidget(QtWidgets.QLabel("Atlas:"), 1, 0)
        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.addItems([
            "Harvard-Oxford Cortical (48 regions)",
            "Glasser HCP (360 regions)"
        ])
        self.atlas_combo.setToolTip("Brain atlas for ROI analysis")
        advanced_layout.addWidget(self.atlas_combo, 1, 1)
        
        # Feature selection p-value
        advanced_layout.addWidget(QtWidgets.QLabel("P-value threshold:"), 1, 2)
        self.pval_combo = QtWidgets.QComboBox()
        self.pval_combo.addItems(["0.05", "0.01", "0.005", "0.001"])
        self.pval_combo.setToolTip("P-value threshold for voxel-wise t-tests")
        advanced_layout.addWidget(self.pval_combo, 1, 3)
        
        # Number of folds
        advanced_layout.addWidget(QtWidgets.QLabel("CV Folds:"), 2, 0)
        self.folds_spinbox = QtWidgets.QSpinBox()
        self.folds_spinbox.setRange(3, 10)
        self.folds_spinbox.setValue(5)
        self.folds_spinbox.setToolTip("Number of folds for cross-validation (3-10)")
        advanced_layout.addWidget(self.folds_spinbox, 2, 1)
        
        # Analysis mode selection
        self.roi_features_cb = QtWidgets.QCheckBox("Use FSL ROI-averaged features")
        self.roi_features_cb.setToolTip(
            "Use FSL-based ROI averaging instead of voxel-wise features.\n"
            "Recommended for small samples (<50 subjects).\n"
            "Uses FSL tools for maximum accuracy.\n"
            "Requires native resolution (1mm)."
        )
        self.roi_features_cb.stateChanged.connect(self._on_roi_features_changed)
        advanced_layout.addWidget(self.roi_features_cb, 3, 0, 1, 4)
        
        # Parallel processing cores
        advanced_layout.addWidget(QtWidgets.QLabel("CPU Cores:"), 4, 0)
        self.cores_spinbox = QtWidgets.QSpinBox()
        import multiprocessing
        max_cores = multiprocessing.cpu_count()
        self.cores_spinbox.setRange(1, max_cores)
        self.cores_spinbox.setValue(max(1, max_cores - 1))  # Default: all cores except one
        self.cores_spinbox.setToolTip(f"Number of CPU cores to use (1-{max_cores})")
        advanced_layout.addWidget(self.cores_spinbox, 4, 1)
        
        advanced_group.setLayout(advanced_layout)
        scroll_layout.addWidget(advanced_group)
        
        # Set scroll content
        scroll_content.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Output console section
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        
        # Console buttons
        console_buttons_layout = QtWidgets.QHBoxLayout()
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Train Classifier")
        self.run_btn.clicked.connect(self.run_training)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        
        # Stop button (initially disabled)
        self.stop_btn = QtWidgets.QPushButton("Stop Training")
        self.stop_btn.clicked.connect(self.stop_training)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.stop_btn.setEnabled(False)  # Initially disabled
        
        # Clear console button
        clear_btn = QtWidgets.QPushButton("Clear Console")
        clear_btn.clicked.connect(self.clear_console)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        
        console_buttons_layout.addWidget(self.run_btn)
        console_buttons_layout.addWidget(self.stop_btn)
        console_buttons_layout.addWidget(clear_btn)
        
        # Freeview button
        self.freeview_btn = QtWidgets.QPushButton("View in Freeview")
        self.freeview_btn.clicked.connect(self.open_freeview)
        self.freeview_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.freeview_btn.setEnabled(False)  # Initially disabled
        
        console_buttons_layout.addWidget(self.freeview_btn)
        console_buttons_layout.addStretch()
        
        # Console header layout (label + buttons)
        console_header_layout = QtWidgets.QHBoxLayout()
        console_header_layout.addWidget(output_label)
        console_header_layout.addStretch()
        console_header_layout.addLayout(console_buttons_layout)
        
        # Console output with black background
        self.console_output = QtWidgets.QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMinimumHeight(200)
        self.console_output.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #f0f0f0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        self.console_output.setAcceptRichText(True)
        
        # Console layout
        console_layout = QtWidgets.QVBoxLayout()
        console_layout.addLayout(console_header_layout)
        console_layout.addWidget(self.console_output)
        
        # Add console layout to main layout
        main_layout.addLayout(console_layout)
        
        # Initialize UI state
        self.cleanup_hidden_files()  # Clean up problematic hidden files first
        self.refresh_csv_files()
        self.update_output("Welcome to Voxel-wise Classifier Training!", "info")
        self.update_output("Please select a training CSV file to begin.", "info")
    
    def refresh_csv_files(self):
        """Refresh the list of CSV files."""
        self.train_combo.clear()
        
        # Look for CSV files in data directory, excluding hidden files
        all_csv_files = list(self.data_dir.glob("*.csv"))
        
        # Filter out hidden files (starting with . or ._) and ensure they're accessible
        csv_files = []
        for csv_file in all_csv_files:
            # Skip hidden files (macOS metadata files like ._filename.csv)
            if csv_file.name.startswith('.') or csv_file.name.startswith('._'):
                continue
            
            # Test file accessibility
            try:
                csv_file.stat()  # This will raise PermissionError if not accessible
                csv_files.append(csv_file)
            except (PermissionError, OSError):
                # Skip files that can't be accessed
                continue
        
        if csv_files:
            for csv_file in csv_files:
                self.train_combo.addItem(csv_file.name, str(csv_file))
        else:
            self.train_combo.addItem("No CSV files found", None)
            self.create_example_files()
    
    def create_example_files(self):
        """Create example CSV files if none exist."""
        example_file = self.data_dir / "example_training_data.csv"
        
        if not example_file.exists():
            example_data = pd.DataFrame({
                'subject_id': ['sub-101', 'sub-102', 'sub-103', 'sub-104', 'sub-105', 'sub-106', 
                              'sub-107', 'sub-108', 'sub-109', 'sub-110'],
                'response': [1, 1, 1, 1, 1, -1, -1, -1, -1, -1],
                'simulation_name': ['sim1'] * 10
            })
            example_data.to_csv(example_file, index=False)
            self.update_output(f"Created example file: {example_file.name}", "info")
            self.refresh_csv_files()
    
    def browse_csv_file(self, file_type: str):
        """Browse for CSV file."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, f"Select {file_type.title()} CSV File", 
            str(self.data_dir), "CSV Files (*.csv)"
        )
        
        if file_path:
            # Copy file to data directory if not already there
            file_path = Path(file_path)
            if file_path.parent != self.data_dir:
                dest_path = self.data_dir / file_path.name
                import shutil
                shutil.copy2(file_path, dest_path)
                self.update_output(f"Copied {file_path.name} to data directory", "info")
            
            self.refresh_csv_files()
    
    def cleanup_hidden_files(self):
        """Clean up hidden macOS metadata files that can cause permission issues."""
        try:
            hidden_files = list(self.data_dir.glob("._*"))
            for hidden_file in hidden_files:
                try:
                    hidden_file.unlink()
                    self.update_output(f"Removed problematic hidden file: {hidden_file.name}", "info")
                except (PermissionError, OSError):
                    # If we can't delete it, just skip it
                    pass
        except Exception:
            # If anything goes wrong, just continue silently
            pass
    
    def on_train_file_changed(self):
        """Handle training file selection change."""
        current_data = self.train_combo.currentData()
        if current_data:
            try:
                # Check file accessibility first
                file_path = Path(current_data)
                if not file_path.exists():
                    self.train_info_label.setText("File not found")
                    self.train_info_label.setStyleSheet("color: #d32f2f; padding: 5px;")
                    return
                
                # Test file access permissions
                file_path.stat()
                
                # Try to read the CSV file
                df = pd.read_csv(current_data)
                n_subjects = len(df)
                n_responders = len(df[df['response'] == 1]) if 'response' in df.columns else 0
                n_nonresponders = len(df[df['response'] == -1]) if 'response' in df.columns else 0
                
                info_text = f"Subjects: {n_subjects}, Responders: {n_responders}, Non-responders: {n_nonresponders}"
                self.train_info_label.setText(info_text)
                self.train_info_label.setStyleSheet("color: #2E8B57; padding: 5px; font-weight: bold;")
                
            except PermissionError:
                self.train_info_label.setText("Permission denied - cannot access file")
                self.train_info_label.setStyleSheet("color: #d32f2f; padding: 5px;")
                # Refresh the file list to remove inaccessible files
                self.refresh_csv_files()
            except Exception as e:
                self.train_info_label.setText(f"Error reading file: {str(e)}")
                self.train_info_label.setStyleSheet("color: #d32f2f; padding: 5px;")
        else:
            self.train_info_label.setText("No file selected")
            self.train_info_label.setStyleSheet("color: #666; padding: 5px;")
    
    def run_training(self):
        """Start classifier training in background thread."""
        if self.training_running:
            return
        
        # Validate inputs
        csv_file = self.train_combo.currentData()
        if not csv_file or not Path(csv_file).exists():
            self.update_output("Please select a valid training CSV file", "error")
            return
        
        # Get parameters
        resolution_text = self.resolution_combo.currentText()
        resolution = int(resolution_text.split('mm')[0]) if 'mm' in resolution_text else 1
        
        n_permutations = self.perm_spinbox.value()
        p_threshold = float(self.pval_combo.currentText())
        n_folds = self.folds_spinbox.value()
        n_jobs = self.cores_spinbox.value()
        use_roi_features = self.roi_features_cb.isChecked()
        
        # Get selected atlas
        atlas_text = self.atlas_combo.currentText()
        if "Harvard-Oxford" in atlas_text:
            atlas_name = "HarvardOxford-cort-maxprob-thr0-1mm"
        elif "Glasser" in atlas_text:
            atlas_name = "MNI_Glasser_HCP_v1.0"
        else:
            atlas_name = "HarvardOxford-cort-maxprob-thr0-1mm"  # Default
        
        # Show advanced settings in console
        self.update_output("================================================================================", "info")
        self.update_output("TI-TOOLBOX CLASSIFIER v2.0 - TRAINING", "info")
        self.update_output("================================================================================", "info")
        self.update_output("", "info")
        self.update_output("Advanced Settings:", "info")
        self.update_output(f"• Resolution: {resolution}mm", "info")
        self.update_output(f"• Permutations: {n_permutations}", "info")
        self.update_output(f"• P-value threshold: {p_threshold}", "info")
        self.update_output(f"• CV Folds: {n_folds}", "info")
        self.update_output(f"• CPU cores: {n_jobs}", "info")
        atlas_display = atlas_text.split(' (')[0]  # Get just the atlas name
        self.update_output(f"• Feature type: {'FSL ROI-averaged' if use_roi_features else 'Voxel-wise'}", "info")
        self.update_output(f"• Atlas: {atlas_display}", "info")
        self.update_output("", "info")
        
        # Start training thread
        self.training_thread = ClassifierThread(
            self.project_dir, csv_file, resolution, n_permutations, 
            p_threshold, n_jobs, use_roi_features, atlas_name
        )
        
        # Connect signals
        self.training_thread.output_signal.connect(self.update_output)
        self.training_thread.error_signal.connect(self.on_training_error)
        self.training_thread.finished_signal.connect(self.on_training_finished)
        
        # Update UI state
        self.training_running = True
        self.disable_controls()
        
        # Start thread
        self.training_thread.start()
    
    def stop_training(self):
        """Stop the running training process."""
        if not self.training_running or not self.training_thread:
            return
        
        self.update_output("Stopping training...", "warning")
        self.training_thread.stop()
        self.training_running = False
        self.enable_controls()
    
    def on_training_error(self, error_msg):
        """Handle training error."""
        self.update_output(f"Training error: {error_msg}", "error")
    
    def on_training_finished(self, success):
        """Handle training completion."""
        self.training_running = False
        self.enable_controls()
        
        if success:
            self.update_output("Training completed successfully!", "success")
            # Enable freeview button after successful training
            self.freeview_btn.setEnabled(True)
        else:
            self.update_output("Training failed or was stopped", "error")
            self.freeview_btn.setEnabled(False)
    
    def disable_controls(self):
        """Disable controls during processing."""
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.train_combo.setEnabled(False)
        self.resolution_combo.setEnabled(False)
        self.atlas_combo.setEnabled(False)
        self.perm_spinbox.setEnabled(False)
        self.pval_combo.setEnabled(False)
        self.folds_spinbox.setEnabled(False)
        self.cores_spinbox.setEnabled(False)
        self.roi_features_cb.setEnabled(False)
        self.freeview_btn.setEnabled(False)
        
        # Show status label
        self.status_label.show()
    
    def enable_controls(self):
        """Enable controls after processing."""
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.train_combo.setEnabled(True)
        self.atlas_combo.setEnabled(True)
        self.perm_spinbox.setEnabled(True)
        self.folds_spinbox.setEnabled(True)
        self.cores_spinbox.setEnabled(True)
        
        # Enable ROI controls
        self.roi_features_cb.setEnabled(True)
        
        # Resolution depends on ROI features state
        use_roi_features = self.roi_features_cb.isChecked()
        self.resolution_combo.setEnabled(not use_roi_features)
        
        # P-value is always enabled
        self.pval_combo.setEnabled(True)
        # Note: freeview_btn is enabled separately in on_training_finished
        
        # Hide status label
        self.status_label.hide()
    
    def clear_console(self):
        """Clear the console output."""
        self.console_output.clear()
        self.update_output("Console cleared", "info")
    
    def update_output(self, text, message_type="default"):
        """Update the console output with colored text."""
        # Color mapping for different message types
        color_map = {
            'info': '#55ffff',      # Light blue
            'success': '#55ff55',   # Light green
            'warning': '#ffff55',   # Yellow
            'error': '#ff5555',     # Light red
            'command': '#ff55ff',   # Magenta
            'debug': '#888888',     # Gray
            'default': '#f0f0f0'    # Light gray
        }
        
        color = color_map.get(message_type, color_map['default'])
        
        # Format the text with color
        if message_type == 'error':
            formatted_text = f'<span style="color: {color}; font-weight: bold;">{text}</span>'
        elif message_type == 'success':
            formatted_text = f'<span style="color: {color}; font-weight: bold;">{text}</span>'
        elif message_type == 'warning':
            formatted_text = f'<span style="color: {color}; font-weight: bold;">{text}</span>'
        else:
            formatted_text = f'<span style="color: {color};">{text}</span>'
        
        # Add to console
        self.console_output.append(formatted_text)
        
        # Scroll to bottom
        scrollbar = self.console_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Process events to update GUI
        QtWidgets.QApplication.processEvents()
    
    def show_help(self):
        """Show help dialog with information about voxel-wise classification."""
        help_dialog = QtWidgets.QDialog(self)
        help_dialog.setWindowTitle("Voxel-wise Classifier Help")
        help_dialog.setMinimumSize(600, 500)
        help_dialog.setModal(True)
        
        layout = QtWidgets.QVBoxLayout()
        
        # Create scrollable text area
        text_area = QtWidgets.QTextEdit()
        text_area.setReadOnly(True)
        text_area.setHtml("""
        <h2>Voxel-wise Classifier</h2>
        
        <p>This tool implements a voxel-wise machine learning classifier based on the methodology from 
        <strong>Albizu et al. (2020)</strong> for predicting treatment response using brain stimulation field data.</p>
        
        <h3>What it does:</h3>
        <ul>
            <li>Analyzes current density maps from TI (Temporal Interference) stimulation</li>
            <li>Uses Support Vector Machine (SVM) to classify responders vs. non-responders</li>
            <li>Identifies brain regions that predict treatment response</li>
            <li>Generates statistical maps and ROI contribution analysis</li>
        </ul>
        
        <h3>Input Requirements:</h3>
        <ul>
            <li><strong>Training CSV:</strong> File with columns: subject_id, response, [simulation_name]</li>
            <li><strong>Response values:</strong> 1 = responder, -1 = non-responder</li>
            <li><strong>NIfTI files:</strong> Current density maps in project derivatives folder</li>
        </ul>
        
        <h3>Advanced Parameters:</h3>
        
        <h4>Resolution</h4>
        <p>Voxel size for analysis. Higher resolution (1mm) provides more detail but requires more memory and time. 
        Lower resolution (2-4mm) is faster but less precise.</p>
        
        <h4>Permutations</h4>
        <p>Number of cross-validation permutations (3-20). More permutations give more robust results but take longer. 
        Default: 10 (recommended for most analyses).</p>
        
        <h4>P-value Threshold</h4>
        <p>Statistical threshold for voxel-wise t-tests to select significant features:</p>
        <ul>
            <li><strong>0.01:</strong> Standard threshold (recommended)</li>
            <li><strong>0.005:</strong> More stringent, fewer voxels selected</li>
            <li><strong>0.001:</strong> Very stringent, may select too few voxels</li>
        </ul>
        
        <h4>CV Folds</h4>
        <p>Number of cross-validation folds (3-10). More folds provide better validation but increase computation time. 
        Default: 5 (good balance).</p>
        
        <h4>CPU Cores</h4>
        <p>Number of processor cores to use for parallel processing. More cores = faster processing, 
        but leave at least 1 core free for system operations.</p>
        
        <h3>Expected Results:</h3>
        <p><strong>For TI fields:</strong> Expect relatively few significant voxels (10s to 100s) because TI creates 
        focal interference patterns, unlike tDCS which affects larger brain areas.</p>
        
        <h3>Output Files:</h3>
        <ul>
            <li><strong>Model file:</strong> Trained classifier (.pkl)</li>
            <li><strong>Statistical maps:</strong> T-statistics, p-values, SVM weights (NIfTI)</li>
            <li><strong>ROI analysis:</strong> Brain region contributions (CSV)</li>
            <li><strong>Group averages:</strong> Responder vs. non-responder maps</li>
        </ul>
        
        <h3>Troubleshooting:</h3>
        <ul>
            <li><strong>Very few significant voxels:</strong> Normal for TI fields (they're focal by design)</li>
            <li><strong>Low accuracy:</strong> May need more subjects or different parameters</li>
            <li><strong>Memory errors:</strong> Try lower resolution or fewer CPU cores</li>
            <li><strong>File not found:</strong> Check that NIfTI files exist in derivatives folder</li>
        </ul>
        
        <p><em>Based on: Albizu, A., et al. (2020). Machine learning and individual variability in electric 
        field characteristics predict tDCS treatment response. Brain Stimulation, 13(6), 1753-1764.</em></p>
        """)
        
        layout.addWidget(text_area)
        
        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(help_dialog.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        help_dialog.setLayout(layout)
        
        # Show dialog
        help_dialog.exec_()
    
    def open_freeview(self):
        """
        Open results in Freeview for visualization.
        
        Layer order (bottom to top):
        1. MNI152_T1_1mm.nii.gz - Base anatomical layer
        2. significant_voxels_mask_MNI.nii.gz - Significant voxels
        3. significant_ROIs_binary_MNI.nii.gz - Significant ROIs with LUT
        4. difference_resp_vs_nonresp_MNI.nii.gz - Difference map
        """
        results_dir = self.project_dir / "derivatives" / "ti-toolbox" / "classifier" / "results"
        
        # Define file order and display properties
        overlay_files = [
            {
                'name': 'group_averages/difference_responders_vs_nonresponders_ROI_averaged_MNI.nii.gz',
                'colormap': 'heat',
                'opacity': 0.8,
                'description': 'ROI difference map (responders vs non-responders)'
            },
            {
                'name': 'group_averages/responders_ROI_averaged_MNI.nii.gz',
                'colormap': 'hot',
                'opacity': 0.6,
                'description': 'Responder ROI averages'
            },
            {
                'name': 'group_averages/nonresponders_ROI_averaged_MNI.nii.gz',
                'colormap': 'cool',
                'opacity': 0.6,
                'description': 'Non-responder ROI averages'
            }
        ]
        
        # Check for MNI template (base layer) in multiple locations
        possible_mni_paths = [
            # Docker paths
            Path("/ti-toolbox/assets/atlas/MNI152_T1_1mm.nii.gz"),
            Path("/ti-toolbox/assets/base-niftis/MNI152_T1_1mm.nii.gz"),
            # Local paths
            self.project_dir / "assets" / "atlas" / "MNI152_T1_1mm.nii.gz",
            self.project_dir / "assets" / "base-niftis" / "MNI152_T1_1mm.nii.gz",
            self.project_dir / "assets" / "MNI152_T1_1mm.nii.gz"
        ]
        
        mni_template = None
        for path in possible_mni_paths:
            if path.exists():
                mni_template = path
                break
        
        if mni_template is None:
            self.update_output("MNI152_T1_1mm.nii.gz template not found in any expected location", "error")
            self.update_output(f"Searched: {[str(p) for p in possible_mni_paths]}", "error")
            return
        
        # Check which overlay files exist
        existing_overlays = []
        for overlay in overlay_files:
            file_path = results_dir / overlay['name']
            if file_path.exists():
                existing_overlays.append((file_path, overlay))
                
        if not existing_overlays:
            self.update_output("No classifier result files found to display in Freeview", "error")
            return
        
        try:
            # Build freeview command in the correct layer order
            cmd = ["freeview"]
            
            # 1. Base layer: MNI template
            cmd.extend(["-v", str(mni_template)])
            self.update_output(f"Base layer: {mni_template.name}", "info")
            
            # 2-4. Add overlay files in order
            for file_path, overlay_config in existing_overlays:
                file_name = overlay_config['name']
                colormap = overlay_config['colormap']
                opacity = overlay_config['opacity']
                description = overlay_config['description']
                
                # Build overlay argument
                overlay_arg = f"{file_path}:colormap={colormap}:opacity={opacity}"
                
                # Add LUT if specified and exists
                if 'lut' in overlay_config:
                    lut_path = results_dir / overlay_config['lut']
                    if lut_path.exists():
                        overlay_arg += f":lut={lut_path}"
                        self.update_output(f"Overlay: {description} (with LUT)", "info")
                    else:
                        self.update_output(f"Overlay: {description} (no LUT found)", "info")
                else:
                    self.update_output(f"Overlay: {description}", "info")
                
                cmd.extend(["-v", overlay_arg])
            
            # Launch freeview
            self.update_output(f"Launching Freeview with {len(existing_overlays)} overlays on MNI template...", "info")
            self.update_output("Layer order: MNI template → Significant voxels → Significant ROIs → Difference map", "info")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        except FileNotFoundError:
            self.update_output("Freeview not found. Please ensure FreeSurfer is installed and in PATH.", "error")
        except Exception as e:
            self.update_output(f"Error launching Freeview: {str(e)}", "error")
    
    def _on_roi_features_changed(self, state):
        """Handle ROI features checkbox state change."""
        use_roi_features = state == 2  # Qt.Checked
        
        if use_roi_features:
            # ROI mode requires native resolution (1mm) for FSL accuracy
            self.resolution_combo.setCurrentText("1mm (original)")
            self.resolution_combo.setEnabled(False)
            self.resolution_combo.setToolTip("Resolution locked to 1mm for FSL ROI extraction accuracy")
            
            # P-value still available for ROI significance
            self.pval_combo.setEnabled(True)
            self.pval_combo.setToolTip("P-value threshold for ROI significance testing")
            
            self.update_output("FSL ROI-averaged features selected - Resolution locked to 1mm", "info")
            
        else:
            # Voxel mode - enable all controls
            self.resolution_combo.setEnabled(True)
            self.resolution_combo.setToolTip("Voxel resolution for analysis")
            
            self.pval_combo.setEnabled(True)
            self.pval_combo.setToolTip("P-value threshold for voxel-wise t-tests")
            
            self.update_output("Voxel-wise features selected - All controls enabled", "info")