#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 NIfTI Viewer Tab
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
        
    def setup_ui(self):
        """Set up the user interface for the NIfTI viewer tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create subject selection area
        subject_group = QtWidgets.QGroupBox("Subject Selection")
        subject_layout = QtWidgets.QHBoxLayout(subject_group)
        # Subject
        subject_layout.addWidget(QtWidgets.QLabel("Subject:"))
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.setMinimumWidth(120)
        subject_layout.addWidget(self.subject_combo)
        # Space
        subject_layout.addWidget(QtWidgets.QLabel("Space:"))
        self.space_combo = QtWidgets.QComboBox()
        self.space_combo.addItems(["Subject", "MNI"])
        self.space_combo.setEnabled(False)  # Initially disabled until we check for MNI files
        subject_layout.addWidget(self.space_combo)
        # Simulation(s)
        subject_layout.addWidget(QtWidgets.QLabel("Simulation(s):"))
        self.sim_list = QtWidgets.QListWidget()
        self.sim_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.sim_list.setMaximumHeight(200)
        self.sim_list.setMinimumWidth(120)
        subject_layout.addWidget(self.sim_list)
        # Refresh
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_subjects)
        subject_layout.addWidget(self.refresh_btn)
        subject_layout.addStretch(1)
        main_layout.addWidget(subject_group)
        
        # Visualization options panel
        vis_group = QtWidgets.QGroupBox("Visualization Options")
        vis_layout = QtWidgets.QHBoxLayout(vis_group)
        vis_layout.setSpacing(12)
        vis_layout.setContentsMargins(10, 5, 10, 5)
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
        self.opacity_slider.setFixedWidth(80)
        vis_layout.addWidget(self.opacity_slider)
        self.opacity_label = QtWidgets.QLabel("0.70")
        vis_layout.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v/100:.2f}"))
        # Percentile mode
        self.percentile_chk = QtWidgets.QCheckBox("Percentile Mode")
        self.percentile_chk.setChecked(True)
        vis_layout.addWidget(self.percentile_chk)
        # Thresholds
        vis_layout.addWidget(QtWidgets.QLabel("Threshold (%):"))
        self.min_threshold = QtWidgets.QDoubleSpinBox()
        self.min_threshold.setRange(0, 100)
        self.min_threshold.setValue(95)
        self.min_threshold.setDecimals(1)
        self.min_threshold.setFixedWidth(60)
        vis_layout.addWidget(self.min_threshold)
        vis_layout.addWidget(QtWidgets.QLabel("to"))
        self.max_threshold = QtWidgets.QDoubleSpinBox()
        self.max_threshold.setRange(0, 100)
        self.max_threshold.setValue(99.9)
        self.max_threshold.setDecimals(1)
        self.max_threshold.setFixedWidth(60)
        vis_layout.addWidget(self.max_threshold)
        # Visibility
        self.visibility_chk = QtWidgets.QCheckBox("Visible")
        self.visibility_chk.setChecked(True)
        vis_layout.addWidget(self.visibility_chk)
        vis_layout.addStretch(1)
        main_layout.addWidget(vis_group)
        
        # Create toolbar for actions
        toolbar_group = QtWidgets.QGroupBox("Actions")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_group)
        # Load button
        self.load_btn = QtWidgets.QPushButton("Load Subject Data")
        self.load_btn.clicked.connect(self.load_subject_data)
        toolbar_layout.addWidget(self.load_btn)
        # Custom load button
        self.custom_load_btn = QtWidgets.QPushButton("Load Custom NIfTI")
        self.custom_load_btn.clicked.connect(self.load_custom_nifti)
        toolbar_layout.addWidget(self.custom_load_btn)
        # Status label
        self.status_label = QtWidgets.QLabel("Ready to load NIfTI files")
        toolbar_layout.addWidget(self.status_label)
        main_layout.addWidget(toolbar_group)
        
        # Info area (console)
        self.info_area = QtWidgets.QTextEdit()
        self.info_area.setReadOnly(True)
        self.info_area.setMinimumHeight(300)
        self.info_area.setText(
            "NIfTI Viewer using Freeview\n\n"
            "1. Select a subject from the dropdown\n"
            "2. Choose between Subject space or MNI space\n"
            "3. Select one or more simulations from the list\n"
            "4. Set visualization options\n"
            "5. Click 'Load Subject Data' to view subject's data\n"
            "6. Freeview will launch to display the files\n\n"
            "Note: Freeview must be installed on your system."
        )
        main_layout.addWidget(self.info_area)
        
        # Create a frame to hold the freeview command info
        self.cmd_frame = QtWidgets.QGroupBox("Freeview Command")
        cmd_layout = QtWidgets.QVBoxLayout(self.cmd_frame)
        self.cmd_label = QtWidgets.QLabel("No command executed yet")
        self.cmd_label.setWordWrap(True)
        cmd_layout.addWidget(self.cmd_label)
        main_layout.addWidget(self.cmd_frame)
        
        # Add help and reload buttons at the bottom
        bottom_button_layout = QtWidgets.QHBoxLayout()
        bottom_button_layout.addStretch()
        reload_btn = QtWidgets.QPushButton("Reload Current View")
        reload_btn.clicked.connect(self.reload_current_view)
        bottom_button_layout.addWidget(reload_btn)
        clear_console_btn = QtWidgets.QPushButton("Clear Console")
        clear_console_btn.clicked.connect(self.clear_console)
        bottom_button_layout.addWidget(clear_console_btn)
        main_layout.addLayout(bottom_button_layout)
        
        # Populate the subject list
        self.refresh_subjects()
        self.subject_combo.currentIndexChanged.connect(self.refresh_simulations)
        self.refresh_simulations()
    
    def refresh_subjects(self):
        """Scan for available subjects and update the dropdown."""
        self.subject_combo.clear()
        
        # Look for subject directories in the derivatives/SimNIBS directory
        try:
            derivatives_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS")
            if not os.path.isdir(derivatives_dir):
                self.status_label.setText("No derivatives/SimNIBS directory found")
                self.info_area.append(f"\nNo derivatives/SimNIBS directory found in {self.base_dir}")
                return
            
            # Look for sub-* directories
            subject_dirs = [d for d in os.listdir(derivatives_dir) 
                          if os.path.isdir(os.path.join(derivatives_dir, d)) and d.startswith('sub-')]
            
            if subject_dirs:
                # Remove 'sub-' prefix for display
                subject_ids = [d[4:] for d in subject_dirs]  # Remove 'sub-' prefix
                self.subject_combo.addItems(sorted(subject_ids))
                self.status_label.setText(f"Found {len(subject_dirs)} subjects")
                self.info_area.append(f"\nFound {len(subject_dirs)} subjects in {derivatives_dir}")
            else:
                self.status_label.setText("No subjects found")
                self.info_area.append(f"\nNo subjects found in {derivatives_dir}")
                self.info_area.append("Make sure subjects are in BIDS format (sub-XXX)")
        except Exception as e:
            self.status_label.setText(f"Error scanning for subjects: {str(e)}")
            self.info_area.append(f"\nError scanning for subjects: {str(e)}")
    
    def refresh_simulations(self):
        """Populate the simulation list for the selected subject."""
        self.sim_list.clear()
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
                self.sim_list.addItem(sim_name)
        
        # Check if MNI space files exist for this subject
        has_mni_files = False
        for sim_name in os.listdir(sim_base):
            sim_path = os.path.join(sim_base, sim_name, "TI", "niftis")
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
    
    def load_subject_data(self):
        """Load the selected subject's data in Freeview."""
        self.info_area.clear()  # Clear console before printing output
        if self.subject_combo.count() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "No subjects available")
            return
        
        subject_id = self.subject_combo.currentText()
        is_mni_space = self.space_combo.currentText() == "MNI"
        selected_sims = [item.text() for item in self.sim_list.selectedItems()]
        
        if not selected_sims:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one simulation")
            return
        
        # Construct paths using BIDS structure
        derivatives_dir = os.path.join(self.base_dir, "derivatives", "SimNIBS")
        subject_dir = os.path.join(derivatives_dir, f"sub-{subject_id}")
        m2m_dir = os.path.join(subject_dir, f"m2m_{subject_id}")
        simulations_dir = os.path.join(subject_dir, "Simulations")
        analyses_dir = os.path.join(subject_dir, "Analyses")
        
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
        
        # Add simulation results and related analysis files
        for sim_name in selected_sims:
            sim_dir = os.path.join(simulations_dir, sim_name)
            
            # Look for NIfTI files in the TI/niftis directory
            nifti_dir = os.path.join(sim_dir, "TI", "niftis")
            if os.path.exists(nifti_dir):
                # First, add the TI_max files
                for nifti_file in glob.glob(os.path.join(nifti_dir, "*.nii*")):
                    basename = os.path.basename(nifti_file)
                    
                    # Only include TI_max files and exclude TDCS files
                    if "TI_max" not in basename or "TDCS" in basename:
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
                
                # Then, add related analysis files from the Analyses directory
                if not is_mni_space:  # Only load analysis files in subject space
                    # Look for matching analysis directory
                    analysis_sim_dir = os.path.join(analyses_dir, sim_name)
                    if os.path.exists(analysis_sim_dir):
                        # Look for Voxel analysis files
                        voxel_dir = os.path.join(analysis_sim_dir, "Voxel")
                        if os.path.exists(voxel_dir):
                            # Look for region directories
                            for region_dir in os.listdir(voxel_dir):
                                region_path = os.path.join(voxel_dir, region_dir)
                                if os.path.isdir(region_path):
                                    # Look for cortex_visuals directory
                                    cortex_vis_dir = os.path.join(region_path, "cortex_visuals")
                                    if os.path.exists(cortex_vis_dir):
                                        # Add any NIfTI files found
                                        for nifti_file in glob.glob(os.path.join(cortex_vis_dir, "*.nii*")):
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
            
            # Format the command for better display by breaking it into lines
            formatted_cmd = "freeview \\n"
            for arg in freeview_args:
                formatted_cmd += f"  {arg} \\\n"
            formatted_cmd = formatted_cmd.rstrip(" \\\n")
            
            self.cmd_label.setText(formatted_cmd)
            
            # Update info area with file details
            self.info_area.append("\nCurrently viewing:")
            
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