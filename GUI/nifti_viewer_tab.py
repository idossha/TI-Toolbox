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
        # Start by looking in current directory
        current_dir = os.getcwd()
        
        # Try to find BIDS directory
        potential_dirs = [
            "/mnt/BIDS_test",  # As seen in the user's example
            os.path.join(current_dir, "BIDS"),
            os.path.join(current_dir, "data"),
            os.path.dirname(current_dir)  # One level up
        ]
        
        for dir_path in potential_dirs:
            if os.path.isdir(dir_path):
                return dir_path
                
        # If no special directory found, just use current dir
        return current_dir
        
    def setup_ui(self):
        """Set up the user interface for the NIfTI viewer tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create subject selection area
        subject_group = QtWidgets.QGroupBox("Subject Selection")
        subject_layout = QtWidgets.QHBoxLayout(subject_group)
        
        # Subject dropdown
        subject_layout.addWidget(QtWidgets.QLabel("Subject:"))
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.setMinimumWidth(120)
        subject_layout.addWidget(self.subject_combo)
        
        # Space selection (Subject or MNI)
        subject_layout.addWidget(QtWidgets.QLabel("Space:"))
        self.space_combo = QtWidgets.QComboBox()
        self.space_combo.addItems(["Subject", "MNI"])
        subject_layout.addWidget(self.space_combo)
        
        # Refresh button for subject list
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_subjects)
        subject_layout.addWidget(self.refresh_btn)
        
        subject_layout.addStretch(1)
        main_layout.addWidget(subject_group)
        
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
        
        # Remove view options button and add help button
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.clicked.connect(self.show_help)
        toolbar_layout.addWidget(self.help_btn)
        
        # Status label
        self.status_label = QtWidgets.QLabel("Ready to load NIfTI files")
        toolbar_layout.addWidget(self.status_label)
        
        main_layout.addWidget(toolbar_group)
        
        # Create a central widget to display information
        self.info_area = QtWidgets.QTextEdit()
        self.info_area.setReadOnly(True)
        self.info_area.setMinimumHeight(150)
        self.info_area.setText(
            "NIfTI Viewer using Freeview\n\n"
            "1. Select a subject from the dropdown\n"
            "2. Choose between Subject space or MNI space\n"
            "3. Click 'Load Subject Data' to view subject's data\n"
            "4. Freeview will launch to display the files\n\n"
            "Note: Freeview must be installed on your system."
        )
        main_layout.addWidget(self.info_area)
        
        # Create a frame to hold the freeview command info
        self.cmd_frame = QtWidgets.QGroupBox("Freeview Command")
        cmd_layout = QtWidgets.QVBoxLayout(self.cmd_frame)
        
        self.cmd_label = QtWidgets.QLabel("No command executed yet")
        # Enable word wrap for the command label
        self.cmd_label.setWordWrap(True)
        cmd_layout.addWidget(self.cmd_label)
        
        main_layout.addWidget(self.cmd_frame)
        
        # Add a reload button at the bottom
        self.reload_btn = QtWidgets.QPushButton("Reload Current View")
        self.reload_btn.clicked.connect(self.reload_current_view)
        self.reload_btn.setEnabled(False)
        main_layout.addWidget(self.reload_btn)
        
        # Check if Freeview is available
        self.check_freeview()
        
        # Populate the subject list
        self.refresh_subjects()
    
    def check_freeview(self):
        """Check if Freeview is available on the system."""
        try:
            # Try to run freeview with --version flag
            result = subprocess.run(['freeview', '--version'], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  timeout=2)
            
            if result.returncode == 0:
                self.status_label.setText("Ready - Freeview detected")
                version_info = result.stdout.decode('utf-8').strip()
                self.info_area.append(f"\nFreeview detected: {version_info}")
                return True
            else:
                self.status_label.setText("Error - Freeview not working properly")
                self.show_freeview_error()
                return False
        except (subprocess.SubprocessError, FileNotFoundError):
            self.status_label.setText("Error - Freeview not found")
            self.show_freeview_error()
            return False
    
    def show_freeview_error(self):
        """Show error message about Freeview not being available."""
        self.info_area.clear()
        self.info_area.setStyleSheet("color: red;")
        self.info_area.setText(
            "ERROR: Freeview not found or not working properly\n\n"
            "Freeview is required for this NIfTI viewer. Please ensure that:\n"
            "1. FreeSurfer is installed on your system\n"
            "2. The FreeSurfer environment is properly set up\n"
            "3. The 'freeview' command is available in your PATH\n\n"
            "Installation instructions:\n"
            "- Visit https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall\n"
            "- Follow the installation instructions for your platform\n"
            "- Set up the environment variables as described in the documentation"
        )
    
    def refresh_subjects(self):
        """Scan for available subjects and update the dropdown."""
        self.subject_combo.clear()
        
        # Look for subject directories in the base directory
        try:
            # Try directories with SimNIBS folders
            subject_dirs = [d for d in os.listdir(self.base_dir) 
                          if os.path.isdir(os.path.join(self.base_dir, d, "SimNIBS"))]
            
            if subject_dirs:
                self.subject_combo.addItems(sorted(subject_dirs))
                self.status_label.setText(f"Found {len(subject_dirs)} subjects")
                self.info_area.append(f"\nFound {len(subject_dirs)} subjects in {self.base_dir}")
            else:
                self.status_label.setText("No subjects found")
                # Add a message to the info area
                self.info_area.append("\nNo subjects found in " + self.base_dir)
                self.info_area.append("To set a custom data directory, modify the paths in the code.")
        except Exception as e:
            self.status_label.setText(f"Error scanning for subjects: {str(e)}")
            self.info_area.append(f"\nError scanning for subjects: {str(e)}")
    
    def load_subject_data(self):
        """Load the selected subject's data in Freeview."""
        if self.subject_combo.count() == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "No subjects available")
            return
        
        subject_id = self.subject_combo.currentText()
        space = "MNI" if self.space_combo.currentText() == "MNI" else "Subject"
        
        # Construct paths for the T1 and simulation results
        subject_dir = os.path.join(self.base_dir, subject_id)
        
        # Clear the info area and set color to black
        self.info_area.clear()
        self.info_area.setStyleSheet("color: black;")
        self.info_area.append(f"Loading data for subject {subject_id} in {space} space...\n")
        
        # T1 path - use the correct directory structure with m2m_{subjectID}
        m2m_dir = os.path.join(subject_dir, "SimNIBS", f"m2m_{subject_id}")
        
        if space == "MNI":
            t1_path = os.path.join(m2m_dir, f"T1_{subject_id}_MNI.nii.gz")
        else:
            t1_path = os.path.join(m2m_dir, "T1.nii.gz")
        
        # Simulation results paths
        sim_prefix = "" if space == "Subject" else "MNI_"
        sim_dir = os.path.join(subject_dir, "SimNIBS", "Simulations", "L_Insula", "TI", "niftis")
        
        grey_path = os.path.join(sim_dir, f"grey_{subject_id}_L_Insula_{sim_prefix}TI_max.nii.gz")
        result_path = os.path.join(sim_dir, f"{subject_id}_L_Insula_{sim_prefix}TI_max.nii.gz")
        
        # Check if files exist
        files_to_load = []
        file_paths = []  # To store the actual file paths without options
        missing_files = []
        
        if os.path.exists(t1_path):
            # Add T1 file with visible=1
            files_to_load.append(f"{t1_path}:visible=1")
            file_paths.append(t1_path)
            self.info_area.append(f"Found T1 file: {os.path.basename(t1_path)}")
        else:
            missing_files.append(f"T1 file not found: {t1_path}")
            self.info_area.append(f"❌ T1 file not found: {t1_path}")
        
        if os.path.exists(grey_path):
            # Add grey matter with heat colormap, 95-99.9% percentile threshold, visible=1
            files_to_load.append(f"{grey_path}:colormap=heat:heatscale=95,99.9:percentile=1:opacity=0.7:visible=1")
            file_paths.append(grey_path)
            self.info_area.append(f"Found grey matter file: {os.path.basename(grey_path)}")
        else:
            missing_files.append(f"Grey matter file not found: {grey_path}")
            self.info_area.append(f"❌ Grey matter file not found: {grey_path}")
        
        if os.path.exists(result_path):
            # Add result with heat colormap, 95-99.9% percentile threshold, visible=0 (unchecked)
            files_to_load.append(f"{result_path}:colormap=heat:heatscale=95,99.9:percentile=1:opacity=0.7:visible=0")
            file_paths.append(result_path)
            self.info_area.append(f"Found result file: {os.path.basename(result_path)}")
        else:
            missing_files.append(f"Result file not found: {result_path}")
            self.info_area.append(f"❌ Result file not found: {result_path}")
        
        if not files_to_load:
            QtWidgets.QMessageBox.critical(
                self, "Error", 
                "No files found for the selected subject and space.\n\n"
                f"Missing files:\n- " + "\n- ".join(missing_files)
            )
            return
        
        # Add information about default visualization settings
        self.info_area.append("\n📊 Visualization Settings:")
        self.info_area.append("- T1: Displayed as grayscale, visible by default")
        self.info_area.append("- Grey matter: 'Heat' colormap showing 95-99.9 percentile, visible by default")
        self.info_area.append("- Result: 'Heat' colormap showing 95-99.9 percentile, initially hidden")
        self.info_area.append("  (Click the checkbox next to the result to display)")
        self.info_area.append("- Use the 'View Options' button to adjust display settings")
        
        # Launch Freeview with the selected files
        self.info_area.append("\nLaunching Freeview with the found files...")
        self.launch_freeview_with_files(files_to_load, file_paths)
    
    def load_custom_nifti(self):
        """Open a file dialog to select a custom NIfTI file."""
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Load NIfTI Files", "", "NIfTI Files (*.nii *.nii.gz);;All Files (*)"
        )
        
        if filenames:
            # For custom files, we pass the same files for display and file paths
            self.launch_freeview_with_files(filenames, filenames)
    
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
            self.current_paths = file_paths if file_paths else file_specs
            
            # Construct the command
            base_command = ['freeview'] + file_specs
            
            # Launch Freeview
            self.freeview_process = subprocess.Popen(
                base_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Update UI
            self.status_label.setText(f"Viewing {len(file_specs)} files")
            
            # Format the command for better display by breaking it into lines
            formatted_cmd = "freeview \\\n"
            for spec in file_specs:
                formatted_cmd += f"  {spec} \\\n"
            formatted_cmd = formatted_cmd.rstrip(" \\\n")
            
            self.cmd_label.setText(formatted_cmd)
            self.reload_btn.setEnabled(True)
            
            # Update info area with file details
            self.info_area.append("\nCurrently viewing:")
            
            # Use original paths for display if provided
            display_paths = file_paths if file_paths else file_specs
            
            for i, file_path in enumerate(display_paths):
                try:
                    file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
                    basename = os.path.basename(file_path)
                    self.info_area.append(f"{i+1}. {basename} ({file_size:.2f} MB)")
                except (OSError, ValueError) as e:
                    # If there's an error getting file size (e.g., due to options in the path)
                    basename = os.path.basename(file_path.split(':')[0])
                    self.info_area.append(f"{i+1}. {basename}")
            
            self.info_area.append("\nFreeview is now running. Use its interface to navigate the volumes.")
            self.info_area.append("💡 Tip: Click and drag to rotate. Mouse wheel to zoom.")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Freeview: {str(e)}")
    
    def reload_current_view(self):
        """Reload the current view in Freeview."""
        if hasattr(self, 'current_files') and self.current_files:
            file_paths = self.current_paths if hasattr(self, 'current_paths') else []
            self.launch_freeview_with_files(self.current_files, file_paths)
        else:
            QtWidgets.QMessageBox.warning(self, "Warning", "No files currently loaded")
    
    def show_options(self):
        """Show a dialog with additional Freeview options."""
        if not hasattr(self, 'current_files') or not self.current_files:
            return
            
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Freeview Options")
        dialog.setMinimumWidth(400)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # File selection for options
        layout.addWidget(QtWidgets.QLabel("Select file to modify:"))
        file_combo = QtWidgets.QComboBox()
        
        # Use current_paths for display if available
        display_paths = self.current_paths if hasattr(self, 'current_paths') else self.current_files
        
        for i, file_path in enumerate(display_paths):
            # Get just the filename for display
            filename = os.path.basename(file_path.split(':')[0] if ':' in file_path else file_path)
            file_combo.addItem(filename, userData=i)  # Store index as user data
        
        layout.addWidget(file_combo)
        
        # Add visibility toggle
        visibility_chk = QtWidgets.QCheckBox("Visible")
        visibility_chk.setChecked(True)
        layout.addWidget(visibility_chk)
        
        # Add colormap options
        layout.addWidget(QtWidgets.QLabel("Colormap:"))
        colormap_combo = QtWidgets.QComboBox()
        colormap_combo.addItems(["grayscale", "heat", "jet", "gecolor", "nih", "surface"])
        colormap_combo.setCurrentText("heat")  # Default to heat
        layout.addWidget(colormap_combo)
        
        # Add opacity slider
        layout.addWidget(QtWidgets.QLabel("Opacity:"))
        opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        opacity_slider.setRange(0, 100)
        opacity_slider.setValue(70)  # Default to 0.7
        opacity_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        opacity_slider.setTickInterval(10)
        layout.addWidget(opacity_slider)
        
        # Add percentile mode checkbox
        percentile_chk = QtWidgets.QCheckBox("Use Percentile Mode for Thresholds")
        percentile_chk.setChecked(True)  # Default to percentile mode
        layout.addWidget(percentile_chk)
        
        # Add threshold options
        layout.addWidget(QtWidgets.QLabel("Threshold (%):"))
        threshold_layout = QtWidgets.QHBoxLayout()
        min_threshold = QtWidgets.QDoubleSpinBox()
        min_threshold.setRange(0, 100)
        min_threshold.setValue(95)  # Default to 95%
        min_threshold.setDecimals(1)  # Allow decimal values
        
        max_threshold = QtWidgets.QDoubleSpinBox()
        max_threshold.setRange(0, 100)
        max_threshold.setValue(99.9)  # Default to 99.9%
        max_threshold.setDecimals(1)  # Allow decimal values
        
        threshold_layout.addWidget(min_threshold)
        threshold_layout.addWidget(QtWidgets.QLabel("to"))
        threshold_layout.addWidget(max_threshold)
        layout.addLayout(threshold_layout)
        
        # Help text
        help_text = QtWidgets.QLabel(
            "Percentile mode shows thresholds based on data distribution.\n"
            "Example: 95-99.9% shows only the top 5% of values."
        )
        help_text.setStyleSheet("font-size: 10px; color: gray; font-style: italic;")
        layout.addWidget(help_text)
        
        # Add buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # Execute dialog
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Get the selected options
            file_index = file_combo.currentData()
            visible = 1 if visibility_chk.isChecked() else 0
            colormap = colormap_combo.currentText()
            opacity = opacity_slider.value() / 100.0
            min_val = min_threshold.value()
            max_val = max_threshold.value()
            use_percentile = percentile_chk.isChecked()
            
            # Update the file options
            file_path = self.current_files[file_index].split(':')[0]  # Get just the file path
            
            # Build the updated specification with or without percentile mode
            if use_percentile:
                updated_spec = f"{file_path}:colormap={colormap}:heatscale={min_val},{max_val}:percentile=1:opacity={opacity}:visible={visible}"
            else:
                updated_spec = f"{file_path}:colormap={colormap}:heatscale={min_val},{max_val}:opacity={opacity}:visible={visible}"
            
            # Create a new list with the updated specification
            updated_files = list(self.current_files)
            updated_files[file_index] = updated_spec
            
            # Relaunch Freeview with the updated options
            self.launch_freeview_with_options(updated_files)
    
    def launch_freeview_with_options(self, file_specs):
        """Launch Freeview with specified file options."""
        if not file_specs:
            return
        
        try:
            # Close any existing Freeview process
            if self.freeview_process is not None:
                self.terminate_freeview()
            
            # Update the current files with the new options
            self.current_files = file_specs
            
            # Construct the command
            base_command = ['freeview'] + file_specs
            
            # Launch Freeview
            self.freeview_process = subprocess.Popen(
                base_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Update UI with formatted command for better readability
            formatted_cmd = "freeview \\\n"
            for spec in file_specs:
                formatted_cmd += f"  {spec} \\\n"
            formatted_cmd = formatted_cmd.rstrip(" \\\n")
            
            self.cmd_label.setText(formatted_cmd)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", 
                f"Failed to launch Freeview with options: {str(e)}"
            )
    
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
    
    def show_help(self):
        """Show help dialog with detailed information about the NIfTI viewer."""
        help_dialog = QtWidgets.QDialog(self)
        help_dialog.setWindowTitle("NIfTI Viewer Help")
        help_dialog.setMinimumWidth(600)
        help_dialog.setMinimumHeight(500)
        
        layout = QtWidgets.QVBoxLayout(help_dialog)
        
        # Create a scroll area for the help text
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        # Create a widget to hold the help content
        help_widget = QtWidgets.QWidget()
        help_layout = QtWidgets.QVBoxLayout(help_widget)
        
        # Help text sections
        sections = [
            {
                "title": "What are NIfTI Files?",
                "content": (
                    "NIfTI (Neuroimaging Informatics Technology Initiative) files are a standard format "
                    "for storing neuroimaging data. They typically have .nii or .nii.gz extensions and "
                    "contain 3D or 4D volumetric brain data from MRI, fMRI, or simulation results."
                )
            },
            {
                "title": "Interface Overview",
                "content": (
                    "<b>Subject Selection:</b><br>"
                    "- Choose a subject ID from the dropdown<br>"
                    "- Select between Subject space (native) or MNI space (standardized)<br>"
                    "- Click 'Refresh' to update the subject list<br><br>"
                    
                    "<b>Actions:</b><br>"
                    "- <b>Load Subject Data:</b> Loads the selected subject's anatomical (T1) and simulation results<br>"
                    "- <b>Load Custom NIfTI:</b> Opens a file dialog to select your own NIfTI files<br>"
                    "- <b>Reload Current View:</b> Reopens the current files in Freeview<br><br>"
                    
                    "<b>Information Area:</b><br>"
                    "- Displays details about loaded files and settings<br>"
                    "- Shows file paths, sizes, and visualization parameters<br><br>"
                    
                    "<b>Freeview Command:</b><br>"
                    "- Shows the actual command used to launch Freeview<br>"
                    "- Displays visualization parameters for each file"
                )
            },
            {
                "title": "Default Visualization Settings",
                "content": (
                    "When loading subject data, the following default settings are applied:<br><br>"
                    
                    "<b>T1 Anatomical:</b><br>"
                    "- Displayed with grayscale colormap<br>"
                    "- Visible by default<br><br>"
                    
                    "<b>Grey Matter Results:</b><br>"
                    "- 'Heat' colormap showing values between 95-99.9 percentile<br>"
                    "- 70% opacity<br>"
                    "- Visible by default<br><br>"
                    
                    "<b>Full Results:</b><br>"
                    "- 'Heat' colormap showing values between 95-99.9 percentile<br>"
                    "- 70% opacity<br>"
                    "- Hidden by default (must be enabled in Freeview)<br><br>"
                    
                    "<b>Note on Percentile Mode:</b><br>"
                    "The default threshold (95-99.9%) means only the top 5% of values are displayed, "
                    "focusing on the most significant results. This helps identify important areas "
                    "while filtering out noise."
                )
            },
            {
                "title": "Using Freeview Controls",
                "content": (
                    "<b>Basic Navigation:</b><br>"
                    "- Left-click and drag: Rotate 3D view<br>"
                    "- Right-click and drag: Pan<br>"
                    "- Mouse wheel: Zoom in/out<br>"
                    "- Middle-click and drag: Adjust brightness/contrast<br><br>"
                    
                    "<b>Volume Controls:</b><br>"
                    "- Check/uncheck volumes in the left panel to toggle visibility<br>"
                    "- Click volume name to make it the active volume<br>"
                    "- Use sliders to navigate through slices<br>"
                    "- Use toolbar at top for additional view options<br><br>"
                    
                    "<b>Adjusting Display:</b><br>"
                    "- Click on a volume name to select it<br>"
                    "- Right-click on a volume name for additional options<br>"
                    "- Adjust colormap, threshold, and opacity through Freeview's interface<br>"
                    "- Use the 'Configure' button in Freeview for advanced options"
                )
            },
            {
                "title": "Tips for Visualizing Simulation Results",
                "content": (
                    "- View both grey matter and full results for a complete picture<br>"
                    "- Toggle between different overlays to compare results<br>"
                    "- Use the percentile mode for thresholds to focus on significant areas<br>"
                    "- Try different colormaps (heat, jet) for different visualization effects<br>"
                    "- Adjust opacity to see underlying anatomy through the results<br>"
                    "- Save screenshots using Freeview's File > Save Screenshot option"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            # Section title
            title_label = QtWidgets.QLabel(f"<h2>{section['title']}</h2>")
            title_label.setTextFormat(QtCore.Qt.RichText)
            help_layout.addWidget(title_label)
            
            # Section content
            content_label = QtWidgets.QLabel(section['content'])
            content_label.setTextFormat(QtCore.Qt.RichText)
            content_label.setWordWrap(True)
            help_layout.addWidget(content_label)
            
            # Add separator
            separator = QtWidgets.QFrame()
            separator.setFrameShape(QtWidgets.QFrame.HLine)
            separator.setFrameShadow(QtWidgets.QFrame.Sunken)
            help_layout.addWidget(separator)
        
        # Set the help widget as the scroll area's widget
        scroll_area.setWidget(help_widget)
        layout.addWidget(scroll_area)
        
        # Add OK button
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        button_box.accepted.connect(help_dialog.accept)
        layout.addWidget(button_box)
        
        # Show the dialog
        help_dialog.exec_() 