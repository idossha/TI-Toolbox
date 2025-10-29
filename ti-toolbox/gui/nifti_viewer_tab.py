#!/usr/bin/env python3
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

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core import get_path_manager

class NiftiViewerTab(QtWidgets.QWidget):
    """Tab for NIfTI visualization using Freeview."""
    
    def __init__(self, parent=None):
        super(NiftiViewerTab, self).__init__(parent)
        self.parent = parent
        self.freeview_process = None
        self.current_file = None
        self.base_dir = self.find_base_dir()
        self.subject_sim_pairs = []  # Store subject-simulation pairs for group mode
        self.visualization_mode = "single"  # "single" or "group"
        self.setup_ui()
        
    def find_base_dir(self):
        """Find the base directory for data (look for BIDS-format data)."""
        # Get project directory using path manager
        pm = get_path_manager()
        base_dir = pm.get_project_dir()
        
        # Check if the directory exists
        if base_dir and os.path.isdir(base_dir):
            return base_dir
           
    def detect_freesurfer_atlases(self, subject_id):
        """Detect available Freesurfer atlases for a subject.
        
        Args:
            subject_id: The subject ID without 'sub-' prefix
            
        Returns:
            List of available atlas files
        """
        freesurfer_dir = os.path.join(self.base_dir, "derivatives", "freesurfer", f"sub-{subject_id}", "mri")
        atlas_files = []
        
        if os.path.isdir(freesurfer_dir):
            # Look for common atlas files
            atlas_patterns = [
                "aparc.DKTatlas+aseg.mgz",
                "aparc.a2009s+aseg.mgz",
                "aparc+aseg.mgz",
                "aseg.mgz"
            ]
            
            for pattern in atlas_patterns:
                atlas_path = os.path.join(freesurfer_dir, pattern)
                if os.path.exists(atlas_path):
                    atlas_files.append(pattern)
        
        return atlas_files
    
    def detect_mni_atlases(self):
        """Detect available MNI atlases in the assets directory.
        
        Returns:
            List of available MNI atlas files
        """
        # Get the toolbox root directory (parent of GUI folder)
        if hasattr(self.parent, 'toolbox_root'):
            toolbox_root = self.parent.toolbox_root
        else:
            # Try to find it relative to current file
            current_file = os.path.abspath(__file__)
            toolbox_root = os.path.dirname(os.path.dirname(current_file))
        
        atlas_dir = os.path.join(toolbox_root, "assets", "atlas")
        atlas_files = []
        
        if os.path.isdir(atlas_dir):
            # Look for MNI atlas files
            atlas_patterns = [
                "MNI_Glasser_HCP_v1.0.nii.gz",
                "HarvardOxford-sub-maxprob-thr0-1mm.nii.gz",
                "HOS-thr0-1mm.nii.gz"
            ]
            
            for pattern in atlas_patterns:
                atlas_path = os.path.join(atlas_dir, pattern)
                if os.path.exists(atlas_path):
                    # Store full path for MNI atlases
                    atlas_files.append(atlas_path)
        
        return atlas_files
        
    def detect_voxel_analyses(self, subject_id, simulation_name):
        """Detect available voxel analyses for a subject and simulation.
        
        Args:
            subject_id: The subject ID without 'sub-' prefix
            simulation_name: Name of the simulation
            
        Returns:
            List of available region names
        """
        regions = []
        analyses_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS", 
                                  f"sub-{subject_id}", "Simulations", simulation_name, "Analyses")
        
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
        
        # Atlas controls in a horizontal layout
        atlas_controls = QtWidgets.QHBoxLayout()
        self.atlas_visibility_chk = QtWidgets.QCheckBox("Visible")
        self.atlas_visibility_chk.setChecked(True)
        self.atlas_visibility_chk.setEnabled(False)
        atlas_controls.addWidget(self.atlas_visibility_chk)
        
        atlas_controls.addWidget(QtWidgets.QLabel("Opacity:"))
        self.atlas_opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.atlas_opacity_slider.setRange(0, 100)
        self.atlas_opacity_slider.setValue(50)
        self.atlas_opacity_slider.setEnabled(False)
        atlas_controls.addWidget(self.atlas_opacity_slider)
        self.atlas_opacity_label = QtWidgets.QLabel("0.50")
        atlas_controls.addWidget(self.atlas_opacity_label)
        self.atlas_opacity_slider.valueChanged.connect(lambda v: self.atlas_opacity_label.setText(f"{v/100:.2f}"))
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
        self.analysis_opacity_slider.setValue(70)
        self.analysis_opacity_slider.setEnabled(False)
        analysis_controls.addWidget(self.analysis_opacity_slider)
        self.analysis_opacity_label = QtWidgets.QLabel("0.70")
        analysis_controls.addWidget(self.analysis_opacity_label)
        self.analysis_opacity_slider.valueChanged.connect(lambda v: self.analysis_opacity_label.setText(f"{v/100:.2f}"))
        sim_block_layout.addLayout(analysis_controls, 2, 0, 1, 4)
        
        # Add some spacing
        spacer = QtWidgets.QSpacerItem(20, 10, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sim_block_layout.addItem(spacer, 3, 0, 1, 4)
        
        # High frequency fields checkbox
        self.high_freq_chk = QtWidgets.QCheckBox("Load High Frequency Fields")
        self.high_freq_chk.setChecked(False)
        sim_block_layout.addWidget(self.high_freq_chk, 4, 0, 1, 4)
        
        # Refresh button
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
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
        
        self.quick_add_btn = QtWidgets.QPushButton("📋 Quick Add")
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
        
        # MNI Atlas Selection for Group Mode
        group_atlas_layout = QtWidgets.QHBoxLayout()
        group_atlas_layout.addWidget(QtWidgets.QLabel("MNI Atlas:"))
        self.group_atlas_combo = QtWidgets.QComboBox()
        self.group_atlas_combo.addItem("None")
        group_atlas_layout.addWidget(self.group_atlas_combo)
        
        self.group_atlas_visibility_chk = QtWidgets.QCheckBox("Visible")
        self.group_atlas_visibility_chk.setChecked(True)
        group_atlas_layout.addWidget(self.group_atlas_visibility_chk)
        
        group_atlas_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.group_atlas_opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.group_atlas_opacity_slider.setRange(0, 100)
        self.group_atlas_opacity_slider.setValue(50)
        group_atlas_layout.addWidget(self.group_atlas_opacity_slider)
        self.group_atlas_opacity_label = QtWidgets.QLabel("0.50")
        group_atlas_layout.addWidget(self.group_atlas_opacity_label)
        self.group_atlas_opacity_slider.valueChanged.connect(lambda v: self.group_atlas_opacity_label.setText(f"{v/100:.2f}"))
        
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
        self.colormap_combo.addItems(["grayscale", "heat", "jet", "gecolor", "nih", "surface"])
        self.colormap_combo.setCurrentText("heat")
        vis_layout.addWidget(self.colormap_combo)
        
        # Opacity
        vis_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(70)
        vis_layout.addWidget(self.opacity_slider)
        self.opacity_label = QtWidgets.QLabel("0.70")
        vis_layout.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v/100:.2f}"))
        
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
        self.load_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        self.load_btn.clicked.connect(self.load_subject_data)
        button_layout.addWidget(self.load_btn)
        
        load_additional_btn = QtWidgets.QPushButton("Load Additional NIfTIs")
        load_additional_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        load_additional_btn.clicked.connect(self.load_custom_nifti)
        button_layout.addWidget(load_additional_btn)
        
        reload_btn = QtWidgets.QPushButton("Reload Current View")
        reload_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        reload_btn.clicked.connect(self.reload_current_view)
        button_layout.addWidget(reload_btn)
        
        clear_console_btn = QtWidgets.QPushButton("Clear Console")
        clear_console_btn.setStyleSheet("QPushButton { padding: 5px 15px; }")
        clear_console_btn.clicked.connect(self.clear_console)
        button_layout.addWidget(clear_console_btn)
        
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        # Console
        self.info_area = QtWidgets.QTextEdit()
        self.info_area.setReadOnly(True)
        self.info_area.setMinimumHeight(200)
        self.info_area.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: Consolas, Monaco, monospace;
                border: none;
                padding: 8px;
            }
        """)
        self.info_area.setText(
            "NIfTI Viewer using Freeview\n\n"
            "Single Subject Mode:\n"
            "1. Select a subject from the dropdown\n"
            "2. Select a simulation and configure options\n"
            "3. Click 'Load Subject Data' to view in subject space\n\n"
            "Group Mode:\n"
            "1. Add subject-simulation pairs using '+ Add Pair' or '📋 Quick Add'\n"
            "2. Optionally select an MNI atlas overlay\n"
            "3. Configure visualization options\n"
            "4. Click 'Load Subject Data' to view group analysis in MNI space"
        )
        main_layout.addWidget(self.info_area)
        
        # Connect signals
        self.subject_combo.currentIndexChanged.connect(self.on_subject_changed)
        self.sim_combo.currentIndexChanged.connect(self.update_available_analyses)
        self.space_combo.currentIndexChanged.connect(self.update_space_dependent_controls)
        
        # Initial refresh
        self.refresh_subjects()
        
        # Load MNI atlases for group mode
        self.load_mni_atlases()
    
    def refresh_subjects(self):
        """Scan for available subjects and update the dropdown."""
        self.subject_combo.clear()
        
        # Look for subject directories in the derivatives/SimNIBS directory
        try:
            derivatives_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS")
            if not os.path.isdir(derivatives_dir):
                self.status_label.setText("No subjects found")
                return
            
            # Look for sub-* directories
            subject_dirs = [d for d in os.listdir(derivatives_dir) 
                          if os.path.isdir(os.path.join(derivatives_dir, d)) and d.startswith('sub-')]
            
            if subject_dirs:
                # Remove 'sub-' prefix for display
                subject_ids = [d[4:] for d in subject_dirs]  # Remove 'sub-' prefix
                self.subject_combo.addItems(sorted(subject_ids))
                self.status_label.setText(f"Found {len(subject_dirs)} subjects")
                
                # If subjects were found, select the first one and check for atlases
                if self.subject_combo.count() > 0:
                    self.subject_combo.setCurrentIndex(0)
                    self.check_freesurfer_atlases()
            else:
                self.status_label.setText("No subjects found")
        except Exception as e:
            self.status_label.setText("Error scanning for subjects")

    def check_freesurfer_atlases(self):
        """Check for available Freesurfer atlases for the current subject."""
        if self.subject_combo.count() == 0:
            return
            
        subject_id = self.subject_combo.currentText()
        available_atlases = self.detect_freesurfer_atlases(subject_id)
        
        self.atlas_combo.clear()
        if available_atlases:
            self.atlas_combo.addItems(available_atlases)
            self.atlas_combo.setEnabled(True)
            self.atlas_visibility_chk.setEnabled(True)
            self.atlas_opacity_slider.setEnabled(True)
        else:
            self.atlas_combo.setEnabled(False)
            self.atlas_visibility_chk.setEnabled(False)
            self.atlas_opacity_slider.setEnabled(False)

    def refresh_simulations(self):
        """Populate the simulation combo box for the selected subject."""
        self.sim_combo.clear()
        if self.subject_combo.count() == 0:
            return
            
        subject_id = self.subject_combo.currentText()
        sim_base = os.path.join(self.base_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "Simulations")
        
        if not os.path.isdir(sim_base):
            self.info_area.append(f"\nNo Simulations directory found at {sim_base}")
            return
            
        # List all subdirectories (simulations)
        for sim_name in sorted(os.listdir(sim_base)):
            sim_path = os.path.join(sim_base, sim_name)
            if os.path.isdir(sim_path):
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
        
        if regions:
            # Enable analysis controls
            self.analysis_region_combo.setEnabled(True)
            self.analysis_visibility_chk.setEnabled(True)
            self.analysis_opacity_slider.setEnabled(True)
            
            # Add available regions to combo box
            self.analysis_region_combo.addItems(regions)
            
            self.info_area.append(f"\nFound {len(regions)} voxel analysis regions for simulation {simulation_name}")
        else:
            self.info_area.append(f"\nNo voxel analyses found for simulation {simulation_name}")
    
    def on_mode_changed(self):
        """Handle mode change between Single Subject and Group."""
        if self.mode_single_radio.isChecked():
            self.visualization_mode = "single"
            # Show single subject configuration
            self.config_section.setVisible(True)
            self.group_section.setVisible(False)
            
            # Set to Subject space for single mode
            self.space_combo.setCurrentText("Subject")
            
        else:
            self.visualization_mode = "group"
            # Show group configuration
            self.config_section.setVisible(False)
            self.group_section.setVisible(True)
            
            # Set to MNI space for group mode
            self.space_combo.setCurrentText("MNI")
    
    def load_mni_atlases(self):
        """Load available MNI atlases into the group atlas combo."""
        mni_atlases = self.detect_mni_atlases()
        
        for atlas_path in mni_atlases:
            # Extract just the filename for display
            atlas_name = os.path.basename(atlas_path)
            # Store full path as item data
            self.group_atlas_combo.addItem(atlas_name, atlas_path)
    
    def get_all_subjects(self):
        """Get list of all available subjects."""
        subjects = []
        try:
            derivatives_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS")
            if os.path.isdir(derivatives_dir):
                subject_dirs = [d for d in os.listdir(derivatives_dir) 
                              if os.path.isdir(os.path.join(derivatives_dir, d)) and d.startswith('sub-')]
                subjects = sorted([d[4:] for d in subject_dirs])  # Remove 'sub-' prefix
        except Exception as e:
            self.info_area.append(f"\nError getting subjects: {str(e)}")
        
        return subjects
    
    def get_simulations_for_subject(self, subject_id):
        """Get list of available simulations for a subject."""
        simulations = []
        try:
            sim_base = os.path.join(self.base_dir, "derivatives", "SimNIBS", 
                                   f"sub-{subject_id}", "Simulations")
            if os.path.isdir(sim_base):
                simulations = sorted([d for d in os.listdir(sim_base) 
                                    if os.path.isdir(os.path.join(sim_base, d))])
        except Exception as e:
            self.info_area.append(f"\nError getting simulations for {subject_id}: {str(e)}")
        
        return simulations
    
    def add_pair_row(self):
        """Add a new row for subject-simulation pair selection."""
        row = self.pairs_table.rowCount()
        self.pairs_table.insertRow(row)
        
        # Subject combo
        subject_combo = QtWidgets.QComboBox()
        subjects = self.get_all_subjects()
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
        for subject in self.get_all_subjects():
            all_sims.update(self.get_simulations_for_subject(subject))
        sim_combo.addItems(sorted(all_sims))
        sim_layout.addWidget(sim_combo)
        layout.addLayout(sim_layout)
        
        # Subject list
        layout.addWidget(QtWidgets.QLabel("Select Subjects:"))
        subject_list = QtWidgets.QListWidget()
        subject_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        
        all_subjects = self.get_all_subjects()
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
                    self.info_area.append(f"\nWarning: Subject {subject_id} does not have simulation {selected_simulation}")
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
            
            self.info_area.append(f"\nAdded {added_count} subject-simulation pairs")
    
    def validate_pair(self, subject_id, simulation_name):
        """Validate that a subject-simulation pair has MNI files available.
        
        Args:
            subject_id: Subject ID without 'sub-' prefix
            simulation_name: Name of the simulation
            
        Returns:
            Tuple of (is_valid, nifti_path or error_message)
        """
        # Look for MNI NIfTI files
        sim_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS", 
                              f"sub-{subject_id}", "Simulations", simulation_name)
        
        # Check mTI and TI directories
        for sim_type in ["mTI", "TI"]:
            nifti_dir = os.path.join(sim_dir, sim_type, "niftis")
            if os.path.exists(nifti_dir):
                # Look for MNI files
                mni_files = glob.glob(os.path.join(nifti_dir, "*_MNI*.nii*"))
                if mni_files:
                    return True, nifti_dir
        
        return False, f"No MNI files found for subject {subject_id}, simulation {simulation_name}"
    
    def load_group_data(self):
        """Load group visualization with multiple subject-simulation pairs."""
        self.info_area.clear()
        
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
            QtWidgets.QMessageBox.warning(self, "Warning", "Please add at least one subject-simulation pair")
            return
        
        # Get visualization options
        colormap = self.colormap_combo.currentText()
        opacity = self.opacity_slider.value() / 100.0
        percentile = self.percentile_chk.isChecked()
        threshold_min = self.min_threshold.value()
        threshold_max = self.max_threshold.value()
        visible = 1 if self.visibility_chk.isChecked() else 0
        
        file_specs = []
        
        # Add MNI template first
        toolbox_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mni_template = os.path.join(toolbox_root, "assets", "atlas", "MNI152_T1_1mm.nii.gz")
        
        if os.path.exists(mni_template):
            file_specs.append({
                "path": mni_template,
                "type": "volume",
                "visible": 1,
                "colormap": "grayscale"
            })
            self.info_area.append("Loading MNI152 template")
        else:
            self.info_area.append(f"Warning: MNI template not found at {mni_template}")
        
        # Add MNI atlas if selected
        if self.group_atlas_combo.currentIndex() > 0:  # Skip "None"
            atlas_path = self.group_atlas_combo.currentData()
            if atlas_path and os.path.exists(atlas_path):
                atlas_visible = 1 if self.group_atlas_visibility_chk.isChecked() else 0
                atlas_opacity = self.group_atlas_opacity_slider.value() / 100.0
                
                atlas_spec = {
                    "path": atlas_path,
                    "type": "volume",
                    "visible": atlas_visible,
                    "colormap": "lut",
                    "opacity": atlas_opacity
                }
                
                # Check if this is the Glasser atlas and add the lookup table
                atlas_name = os.path.basename(atlas_path)
                if "Glasser" in atlas_name:
                    # Find the corresponding .txt file
                    lut_path = atlas_path.replace(".nii.gz", ".txt")
                    if os.path.exists(lut_path):
                        atlas_spec["lut_file"] = lut_path
                        self.info_area.append(f"Loading MNI atlas: {atlas_name} with lookup table")
                    else:
                        self.info_area.append(f"Loading MNI atlas: {atlas_name} (lookup table not found)")
                else:
                    self.info_area.append(f"Loading MNI atlas: {atlas_name}")
                
                file_specs.append(atlas_spec)
        
        # Add simulation files for each pair
        valid_pairs = 0
        for i, pair in enumerate(pairs):
            subject_id = pair["subject"]
            simulation_name = pair["simulation"]
            
            # Validate pair
            is_valid, result = self.validate_pair(subject_id, simulation_name)
            
            if not is_valid:
                self.info_area.append(f"\n{result}")
                continue
            
            nifti_dir = result
            
            # Find MNI TI_max files
            for nifti_file in glob.glob(os.path.join(nifti_dir, "*.nii*")):
                basename = os.path.basename(nifti_file)
                
                # Only include TI_max/TI_Max MNI files, exclude TDCS
                if "_MNI" not in basename:
                    continue
                if ("TI_max" not in basename and "TI_Max" not in basename) or "TDCS" in basename:
                    continue
                
                # Only load grey matter files by default for group
                if "grey_" not in basename:
                    continue
                
                # Adjust opacity based on number of subjects to avoid oversaturation
                adjusted_opacity = opacity * (1.0 / (1 + len(pairs) * 0.1))
                
                file_specs.append({
                    "path": nifti_file,
                    "type": "volume",
                    "colormap": colormap,
                    "opacity": adjusted_opacity,
                    "visible": visible,
                    "percentile": 1 if percentile else 0,
                    "threshold_min": threshold_min,
                    "threshold_max": threshold_max
                })
                
                self.info_area.append(f"Loading: sub-{subject_id}/{simulation_name} - {basename}")
            
            valid_pairs += 1
        
        if valid_pairs == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "No valid subject-simulation pairs with MNI files found")
            return
        
        self.info_area.append(f"\nLoaded {valid_pairs} subject-simulation pairs in MNI space")
        
        # Launch Freeview
        self.launch_freeview_with_files(file_specs)
    
    def load_subject_data(self):
        """Load the selected subject's data in Freeview."""
        # Route to appropriate loading function based on mode
        if self.visualization_mode == "group":
            self.load_group_data()
            return
        
        # Single subject mode
        self.info_area.clear()  # Clear console before printing output
        if self.subject_combo.count() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "No subjects available")
            return
        
        subject_id = self.subject_combo.currentText()
        is_mni_space = self.space_combo.currentText() == "MNI"
        simulation_name = self.sim_combo.currentText()
        
        if not simulation_name:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a simulation")
            return
        
        # Construct paths using BIDS structure
        derivatives_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS")
        subject_dir = os.path.join(derivatives_dir, f"sub-{subject_id}")
        m2m_dir = os.path.join(subject_dir, f"m2m_{subject_id}")
        simulations_dir = os.path.join(subject_dir, "Simulations")
        
        # Get visualization options
        colormap = self.colormap_combo.currentText()
        opacity = self.opacity_slider.value() / 100.0
        percentile = self.percentile_chk.isChecked()
        threshold_min = self.min_threshold.value()
        threshold_max = self.max_threshold.value()
        visible = 1 if self.visibility_chk.isChecked() else 0
        
        # Initialize file specifications for Freeview
        file_specs = []
        
        # Add T1 image based on selected space - always visible with grayscale colormap
        if is_mni_space:
            t1_file = os.path.join(m2m_dir, f"T1_{subject_id}_MNI.nii.gz")
        else:
            t1_file = os.path.join(m2m_dir, "T1.nii.gz")
        
        if os.path.exists(t1_file):
            file_specs.append({
                "path": t1_file,
                "type": "volume",
                "visible": 1,  # T1 is always visible
                "colormap": "grayscale"  # T1 uses grayscale colormap
            })
        else:
            self.info_area.append(f"\nWarning: T1 file not found at {t1_file}")

        # Add Freesurfer atlas if selected and available
        if self.atlas_combo.isEnabled() and self.atlas_combo.currentText():
            atlas_name = self.atlas_combo.currentText()
            atlas_file = os.path.join(self.base_dir, "derivatives", "freesurfer", 
                                    f"sub-{subject_id}", "mri", atlas_name)
            
            if os.path.exists(atlas_file):
                atlas_visible = 1 if self.atlas_visibility_chk.isChecked() else 0
                atlas_opacity = self.atlas_opacity_slider.value() / 100.0
                
                file_specs.append({
                    "path": atlas_file,
                    "type": "volume",
                    "visible": atlas_visible,
                    "colormap": "lut",  # Use lookup table colormap for segmentation
                    "opacity": atlas_opacity
                })
                self.info_area.append(f"\nLoading Freesurfer atlas: {atlas_name}")
            else:
                self.info_area.append(f"\nWarning: Atlas file not found at {atlas_file}")

        # Add voxel analysis if selected and available
        if self.analysis_region_combo.isEnabled() and self.analysis_region_combo.currentText():
            region_name = self.analysis_region_combo.currentText()
            
            # Look for the ROI file
            analysis_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS",
                                    f"sub-{subject_id}", "Simulations", simulation_name,
                                    "Analyses", "Voxel", region_name)
            
            if os.path.exists(analysis_dir):
                # First try to find the specific ROI file
                roi_file = os.path.join(analysis_dir, f"brain_with_{region_name}_ROI.nii.gz")
                if not os.path.exists(roi_file):
                    # If not found, take the first NIfTI file
                    nifti_files = glob.glob(os.path.join(analysis_dir, "*.nii*"))
                    if nifti_files:
                        roi_file = nifti_files[0]
                    else:
                        roi_file = None
                
                if roi_file and os.path.exists(roi_file):
                    analysis_visible = 1 if self.analysis_visibility_chk.isChecked() else 0
                    analysis_opacity = self.analysis_opacity_slider.value() / 100.0
                    
                    file_specs.append({
                        "path": roi_file,
                        "type": "volume",
                        "visible": analysis_visible,
                        "colormap": "jet",  # Use jet colormap for analysis files
                        "opacity": analysis_opacity
                    })
                    self.info_area.append(f"\nLoading voxel analysis: {os.path.basename(roi_file)}")
                else:
                    self.info_area.append(f"\nWarning: No analysis file found for region {region_name}")
            else:
                self.info_area.append(f"\nWarning: Analysis directory not found at {analysis_dir}")
        
        # Add simulation results
        sim_dir = os.path.join(simulations_dir, simulation_name)
        
        # Look for NIfTI files in the mTI/niftis or TI/niftis directory
        mti_nifti_dir = os.path.join(sim_dir, "mTI", "niftis")
        ti_nifti_dir = os.path.join(sim_dir, "TI", "niftis")
        
        # Check for mTI simulation first
        if os.path.exists(mti_nifti_dir):
            nifti_dir = mti_nifti_dir
        elif os.path.exists(ti_nifti_dir):
            nifti_dir = ti_nifti_dir
        else:
            nifti_dir = None
            
        if nifti_dir:
            # First, add the TI_max files
            for nifti_file in glob.glob(os.path.join(nifti_dir, "*.nii*")):
                basename = os.path.basename(nifti_file)
                
                # Only include TI_max/TI_Max files and exclude TDCS files
                # mTI uses TI_Max (capital M) while regular TI uses TI_max (lowercase m)
                if ("TI_max" not in basename and "TI_Max" not in basename) or "TDCS" in basename:
                    continue
                
                # Determine if this file should be visible by default
                # Only grey matter is visible by default
                is_visible = "grey_" in basename
                
                # Check if file matches the selected space
                if is_mni_space:
                    if "_MNI" not in basename:
                        continue
                else:
                    if "_MNI" in basename:
                        continue
                
                # Add the file with appropriate settings
                file_specs.append({
                    "path": nifti_file,
                    "type": "volume",
                    "colormap": colormap,
                    "opacity": opacity,
                    "visible": visible if is_visible else 0,
                    "percentile": 1 if percentile else 0,
                    "threshold_min": threshold_min,
                    "threshold_max": threshold_max
                })

            # Load high frequency fields if requested
            if self.high_freq_chk.isChecked():
                high_freq_dir = os.path.join(sim_dir, "high_Frequency", "niftis")
                if os.path.exists(high_freq_dir):
                    # Look for scalar_magnE files
                    for nifti_file in glob.glob(os.path.join(high_freq_dir, "*_scalar_magnE.nii.gz")):
                        basename = os.path.basename(nifti_file)
                        
                        file_specs.append({
                            "path": nifti_file,
                            "type": "volume",
                            "colormap": colormap,
                            "opacity": opacity * 0.8,  # Slightly lower opacity for high frequency fields
                            "visible": visible,
                            "percentile": 1 if percentile else 0,
                            "threshold_min": threshold_min,
                            "threshold_max": threshold_max
                        })
                        self.info_area.append(f"\nLoading high frequency field: {basename}")
                else:
                    self.info_area.append(f"\nWarning: High frequency directory not found at {high_freq_dir}")

            # Then, add related analysis files from the Analyses directory
            if not is_mni_space:  # Only load analysis files in subject space
                # Look for matching analysis directory
                analysis_sim_dir = os.path.join(derivatives_dir, simulation_name)
                if os.path.exists(analysis_sim_dir):
                    # Look for Voxel analysis files
                    voxel_dir = os.path.join(analysis_sim_dir, "Voxel")
                    if os.path.exists(voxel_dir):
                        # Look for region directories
                        for region_dir in os.listdir(voxel_dir):
                            region_path = os.path.join(voxel_dir, region_dir)
                            if os.path.isdir(region_path):
                                # Look for NIfTI files directly in the region directory
                                for nifti_file in glob.glob(os.path.join(region_path, "*.nii*")):
                                    file_specs.append({
                                        "path": nifti_file,
                                        "type": "volume",
                                        "colormap": "jet",  # Use different colormap for analysis files
                                        "opacity": opacity * 0.7,  # Slightly lower opacity
                                        "visible": 0,  # Not visible by default
                                        "percentile": 1 if percentile else 0,
                                        "threshold_min": threshold_min,
                                        "threshold_max": threshold_max
                                    })
        
        if not any(spec for spec in file_specs if spec["path"].endswith((".nii", ".nii.gz"))):
            QtWidgets.QMessageBox.warning(self, "Warning", 
                f"No NIfTI files found for the selected simulation(s) in {'MNI' if is_mni_space else 'Subject'} space")
            return
        
        # Launch Freeview with the files
        self.launch_freeview_with_files(file_specs)
    
    def load_custom_nifti(self):
        """Open a file dialog to select a custom NIfTI file."""
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Load NIfTI Files", "", "NIfTI Files (*.nii *.nii.gz);;All Files (*)"
        )
        
        if filenames:
            # Use visualization options for all custom files
            colormap = self.colormap_combo.currentText()
            opacity = self.opacity_slider.value() / 100.0
            percentile = self.percentile_chk.isChecked()
            threshold_min = self.min_threshold.value()
            threshold_max = self.max_threshold.value()
            visible = 1 if self.visibility_chk.isChecked() else 0
            file_specs = []
            for fname in filenames:
                file_specs.append({
                    "path": fname,
                    "type": "volume",
                    "colormap": colormap,
                    "opacity": opacity,
                    "visible": visible,
                    "percentile": 1 if percentile else 0,
                    "threshold_min": threshold_min,
                    "threshold_max": threshold_max
                })
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
            self.current_paths = file_paths if file_paths else [spec["path"] for spec in file_specs if isinstance(spec, dict)]
            
            # Construct the command arguments
            freeview_args = []
            for spec in file_specs:
                if isinstance(spec, dict):
                    # Convert dictionary spec to Freeview argument string
                    arg = spec["path"]
                    
                    # Add basic display options
                    if "colormap" in spec:
                        arg += f":colormap={spec['colormap']}"
                    
                    # Add lookup table if specified (for atlases)
                    if "lut_file" in spec:
                        arg += f":lut={spec['lut_file']}"
                    
                    if "opacity" in spec:
                        arg += f":opacity={spec['opacity']}"
                    if "visible" in spec:
                        arg += f":visible={spec['visible']}"
                        
                    # Add threshold options if present
                    if "percentile" in spec and spec["percentile"]:
                        arg += ":percentile=1"  # Enable percentile mode
                        if "threshold_min" in spec and "threshold_max" in spec:
                            arg += f":heatscale={spec['threshold_min']},{spec['threshold_max']}"
                    
                    freeview_args.append(arg)
                else:
                    # If it's already a string, use it as is
                    freeview_args.append(spec)
            
            # Construct the command
            base_command = ['freeview'] + freeview_args
            
            # Launch Freeview
            self.freeview_process = subprocess.Popen(
                base_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Update UI
            self.status_label.setText(f"Viewing {len(freeview_args)} files")
            
            # Update info area with file details
            self.info_area.clear()
            self.info_area.append("Currently viewing:")
            
            # Use original paths for display
            for i, file_path in enumerate(self.current_paths):
                try:
                    file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
                    basename = os.path.basename(file_path)
                    self.info_area.append(f"{i+1}. {basename} ({file_size:.2f} MB)")
                except (OSError, ValueError) as e:
                    # If there's an error getting file size (e.g., due to options in the path)
                    basename = os.path.basename(file_path.split(':')[0])
                    self.info_area.append(f"{i+1}. {basename}")
            
            self.info_area.append("\nFreeview is now running. Use its interface to navigate the volumes.")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Freeview: {str(e)}")
    
    def reload_current_view(self):
        """Reload the current view in Freeview."""
        if hasattr(self, 'current_files') and self.current_files:
            file_paths = self.current_paths if hasattr(self, 'current_paths') else []
            self.launch_freeview_with_files(self.current_files, file_paths)
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
    
    def clear_console(self):
        """Clear the info_area console output."""
        self.info_area.clear()

    def on_subject_changed(self):
        """Handle subject selection changes."""
        self.check_freesurfer_atlases()
        self.refresh_simulations()

    def update_space_dependent_controls(self):
        """Update controls that depend on the selected space."""
        is_subject_space = self.space_combo.currentText() == "Subject"
        
        # Update analysis controls
        self.analysis_region_combo.setEnabled(is_subject_space)
        self.analysis_visibility_chk.setEnabled(is_subject_space)
        self.analysis_opacity_slider.setEnabled(is_subject_space)
        
        # Update atlas controls
        self.atlas_combo.setEnabled(is_subject_space)
        self.atlas_visibility_chk.setEnabled(is_subject_space)
        self.atlas_opacity_slider.setEnabled(is_subject_space)
        
        if not is_subject_space:
            self.info_area.append("\nNote: analysis option is only available in Subject space") 