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

# Define a variable for compatibility with main.py imports
# This tab doesn't actually use NiBabel, but we need this for compatibility
NIBABEL_AVAILABLE = True

class NiftiViewerTab(QtWidgets.QWidget):
    """Tab for NIfTI visualization using Freeview."""
    
    def __init__(self, parent=None):
        super(NiftiViewerTab, self).__init__(parent)
        self.parent = parent
        self.freeview_process = None
        self.current_file = None
        self.base_dir = self.find_base_dir()
        self.setup_ui()
        
    def find_base_dir(self):
        """Find the base directory for data (look for BIDS-format data)."""
        # Get project directory from environment variable
        project_dir_name = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
        base_dir = f"/mnt/{project_dir_name}"
        
        # Check if the directory exists
        if os.path.isdir(base_dir):
            return base_dir
                
        # If not found, try some fallback directories
        potential_dirs = [
            "/mnt/BIDS_test",
            "/mnt/BIDS",
            os.getcwd(),  # Current directory as last resort
        ]
        
        for dir_path in potential_dirs:
            if os.path.isdir(dir_path):
                return dir_path
                
        # If no special directory found, just use current dir
        return os.getcwd()
        
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
        
        # Top section: Configuration
        config_section = QtWidgets.QWidget()
        config_layout = QtWidgets.QHBoxLayout(config_section)
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
        
        # Space selection
        subject_block_layout.addWidget(QtWidgets.QLabel("Space:"), 1, 0)
        self.space_combo = QtWidgets.QComboBox()
        self.space_combo.addItems(["Subject", "MNI"])
        self.space_combo.setEnabled(False)
        subject_block_layout.addWidget(self.space_combo, 1, 1, 1, 2)
        
        # Atlas selection
        subject_block_layout.addWidget(QtWidgets.QLabel("Atlas:"), 2, 0)
        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.setEnabled(False)
        subject_block_layout.addWidget(self.atlas_combo, 2, 1, 1, 2)
        
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
        subject_block_layout.addLayout(atlas_controls, 3, 0, 1, 3)
        
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
        main_layout.addWidget(config_section)
        
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
            "1. Select a subject from the dropdown\n"
            "2. Choose between Subject space or MNI space\n"
            "3. Select a simulation\n"
            "4. Set visualization options\n"
            "5. Click 'Load Subject Data' to view subject's data\n"
            "6. Freeview will launch to display the files"
        )
        main_layout.addWidget(self.info_area)
        
        # Connect signals
        self.subject_combo.currentIndexChanged.connect(self.on_subject_changed)
        self.sim_combo.currentIndexChanged.connect(self.update_available_analyses)
        self.space_combo.currentIndexChanged.connect(self.update_space_dependent_controls)
        
        # Initial refresh
        self.refresh_subjects()
    
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
        
        # Check if MNI space files exist for this subject
        has_mni_files = False
        for sim_name in os.listdir(sim_base):
            # Check for mTI or TI niftis
            mti_path = os.path.join(sim_base, sim_name, "mTI", "niftis")
            ti_path = os.path.join(sim_base, sim_name, "TI", "niftis")
            
            # Use mTI path if it exists, otherwise TI path
            sim_path = mti_path if os.path.exists(mti_path) else ti_path
            
            if os.path.exists(sim_path):
                for nifti_file in glob.glob(os.path.join(sim_path, "*.nii*")):
                    if "_MNI" in os.path.basename(nifti_file):
                        has_mni_files = True
                        break
            if has_mni_files:
                break
        
        # Enable/disable MNI space option based on file availability
        self.space_combo.setEnabled(has_mni_files)
        if not has_mni_files:
            self.space_combo.setCurrentText("Subject")
            self.info_area.append("\nNote: No MNI space files found. Only subject space is available.")
        
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
    
    def load_subject_data(self):
        """Load the selected subject's data in Freeview."""
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
            self.info_area.append("\nNote: Atlas and analysis options are only available in Subject space") 