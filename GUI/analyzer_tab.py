#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Analyzer Tab
This module provides a GUI interface for the analyzer functionality.
"""

import os
import json
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite

class AnalysisThread(QtCore.QThread):
    """Thread to run analysis in background to prevent GUI freezing."""
    
    # Signal to emit output text
    output_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(AnalysisThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        
    def _strip_ansi_codes(self, text):
        """Remove ANSI color codes from text."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
        
    def run(self):
        """Run the analysis command in a separate thread."""
        try:
            # Set up Python unbuffered output
            self.env['PYTHONUNBUFFERED'] = '1'
            
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                env=self.env
            )
            
            # Real-time output display for both stdout and stderr
            while True:
                # Read stdout
                stdout_line = self.process.stdout.readline()
                if stdout_line:
                    self.output_signal.emit(self._strip_ansi_codes(stdout_line.strip()))
                
                # Read stderr
                stderr_line = self.process.stderr.readline()
                if stderr_line:
                    line = self._strip_ansi_codes(stderr_line.strip())
                    # Only prefix with Error: if it's actually an error message
                    if "ERROR:" in line or "CRITICAL:" in line:
                        self.output_signal.emit(f"Error: {line}")
                    else:
                        self.output_signal.emit(line)
                
                # Check if process has finished
                if self.terminated:
                    break
                    
                # Check if both stdout and stderr are empty and process has finished
                if not stdout_line and not stderr_line and self.process.poll() is not None:
                    break
            
            # Check for errors
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    self.output_signal.emit("Error: Process returned non-zero exit code")
                    
        except Exception as e:
            self.output_signal.emit(f"Error running analysis: {str(e)}")
    
    def terminate_process(self):
        """Terminate the running process."""
        if self.process and self.process.poll() is None:  # Process is still running
            self.terminated = True
            if os.name == 'nt':  # Windows
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:  # Unix/Linux/Mac
                import signal
                # Try to terminate child processes too
                try:
                    parent_pid = self.process.pid
                    ps_output = subprocess.check_output(f"ps -o pid --ppid {parent_pid} --noheaders", shell=True)
                    child_pids = [int(pid) for pid in ps_output.decode().strip().split('\n') if pid]
                    for pid in child_pids:
                        os.kill(pid, signal.SIGTERM)
                except:
                    pass  # Ignore errors in finding child processes
                
                # Kill the main process
                self.process.terminate()
                try:
                    # Wait for a short time for graceful termination
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    self.process.kill()
            
            return True
        return False

class AnalyzerTab(QtWidgets.QWidget):
    """Tab for analyzer functionality."""
    
    # Add signal for analysis completion
    analysis_completed = QtCore.pyqtSignal(str, str, str)  # subject_id, simulation_name, analysis_type
    
    def __init__(self, parent=None):
        super(AnalyzerTab, self).__init__(parent)
        self.parent = parent
        self.analysis_running = False
        self.analysis_process = None
        self.setup_ui()
        
        # Initialize with available subjects
        QtCore.QTimer.singleShot(500, self.list_subjects)
    
    def setup_ui(self):
        """Set up the user interface for the analyzer tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Add status label at the top
        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #f44336;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
                min-height: 30px;
                max-height: 30px;
            }
        """)
        self.status_label.setAlignment(QtCore.Qt.AlignVCenter)
        self.status_label.hide()  # Initially hidden
        main_layout.addWidget(self.status_label)
        
        # Create a scroll area for the form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Main horizontal layout to separate left and right
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        
        # Left side layout for subjects and field selection
        left_layout = QtWidgets.QVBoxLayout()
        
        # Subject selection
        subject_container = QtWidgets.QGroupBox("Subject")
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        
        # List widget for subject selection
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.subject_list.setMinimumHeight(100)
        subject_layout.addWidget(self.subject_list)
        
        # Subject control buttons
        subject_button_layout = QtWidgets.QHBoxLayout()
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        self.clear_subject_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_subject_selection_btn.clicked.connect(self.clear_subject_selection)
        
        subject_button_layout.addWidget(self.list_subjects_btn)
        subject_button_layout.addWidget(self.clear_subject_selection_btn)
        subject_layout.addLayout(subject_button_layout)
        
        # Add subject container to left layout
        left_layout.addWidget(subject_container)
        
        # Montage selection
        simulation_container = QtWidgets.QGroupBox("Montage")
        simulation_layout = QtWidgets.QVBoxLayout(simulation_container)
        
        # Montage combobox
        self.simulation_combo = QtWidgets.QComboBox()
        self.simulation_combo.addItem("Select montage...")
        self.simulation_combo.setCurrentIndex(0)
        simulation_layout.addWidget(self.simulation_combo)
        
        # Add montage container to left layout
        left_layout.addWidget(simulation_container)
        
        # Field selection
        field_container = QtWidgets.QGroupBox("Field Selection")
        field_layout = QtWidgets.QVBoxLayout(field_container)
        
        # Field selection combo with browse button
        field_combo_layout = QtWidgets.QHBoxLayout()
        self.field_combo = QtWidgets.QComboBox()
        
        # Add browse button with folder icon
        self.browse_field_btn = QtWidgets.QPushButton()
        self.browse_field_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self.browse_field_btn.setToolTip("Browse for field file")
        self.browse_field_btn.clicked.connect(self.browse_field)
        self.browse_field_btn.setMaximumWidth(40)  # Make the button compact
        
        field_combo_layout.addWidget(self.field_combo)
        field_combo_layout.addWidget(self.browse_field_btn)
        field_layout.addLayout(field_combo_layout)
        
        # Field name input (for mesh analysis)
        field_name_layout = QtWidgets.QHBoxLayout()
        self.field_name_label = QtWidgets.QLabel("Field Name:")
        self.field_name_input = QtWidgets.QLineEdit()
        self.field_name_input.setPlaceholderText("e.g., TI_max")
        field_name_layout.addWidget(self.field_name_label)
        field_name_layout.addWidget(self.field_name_input)
        field_layout.addLayout(field_name_layout)
        
        # Add field container to left layout
        left_layout.addWidget(field_container)
        
        # Right side layout for analysis parameters
        right_layout = QtWidgets.QVBoxLayout()
        
        # Analysis parameters group
        analysis_params_container = QtWidgets.QGroupBox("Analysis Configuration")
        analysis_params_layout = QtWidgets.QVBoxLayout(analysis_params_container)
        
        # Space selection (Mesh/Voxel)
        space_layout = QtWidgets.QHBoxLayout()
        self.space_label = QtWidgets.QLabel("Analysis Space:")
        self.space_mesh = QtWidgets.QRadioButton("Mesh")
        self.space_voxel = QtWidgets.QRadioButton("Voxel")
        self.space_mesh.setChecked(True)  # Default to mesh
        
        # Create button group for space selection
        self.space_group = QtWidgets.QButtonGroup(self)
        self.space_group.addButton(self.space_mesh)
        self.space_group.addButton(self.space_voxel)
        
        space_layout.addWidget(self.space_label)
        space_layout.addWidget(self.space_mesh)
        space_layout.addWidget(self.space_voxel)
        analysis_params_layout.addLayout(space_layout)
        
        # Analysis type (Spherical/Cortical)
        type_layout = QtWidgets.QHBoxLayout()
        self.type_label = QtWidgets.QLabel("Analysis Type:")
        self.type_spherical = QtWidgets.QRadioButton("Spherical")
        self.type_cortical = QtWidgets.QRadioButton("Cortical")
        self.type_spherical.setChecked(True)  # Default to spherical
        
        # Create button group for analysis type selection
        self.type_group = QtWidgets.QButtonGroup(self)
        self.type_group.addButton(self.type_spherical)
        self.type_group.addButton(self.type_cortical)
        
        type_layout.addWidget(self.type_label)
        type_layout.addWidget(self.type_spherical)
        type_layout.addWidget(self.type_cortical)
        analysis_params_layout.addLayout(type_layout)
        
        # Create stacked widget for different analysis types
        self.analysis_stack = QtWidgets.QStackedWidget()
        
        # Spherical analysis widget
        spherical_widget = QtWidgets.QWidget()
        spherical_layout = QtWidgets.QVBoxLayout(spherical_widget)
        
        # Coordinates input
        coordinates_layout = QtWidgets.QHBoxLayout()
        self.coordinates_label = QtWidgets.QLabel("RAS Coordinates (x,y,z):")
        self.coord_x = QtWidgets.QLineEdit()
        self.coord_y = QtWidgets.QLineEdit()
        self.coord_z = QtWidgets.QLineEdit()
        for coord in [self.coord_x, self.coord_y, self.coord_z]:
            coord.setMaximumWidth(60)
            coord.setPlaceholderText("0.0")
        coordinates_layout.addWidget(self.coordinates_label)
        coordinates_layout.addWidget(self.coord_x)
        coordinates_layout.addWidget(self.coord_y)
        coordinates_layout.addWidget(self.coord_z)

        # Add View in Freeview button
        self.view_in_freeview_btn = QtWidgets.QPushButton("View in Freeview")
        self.view_in_freeview_btn.setToolTip("View T1 in Freeview to help find coordinates")
        self.view_in_freeview_btn.clicked.connect(self.load_t1_in_freeview)
        coordinates_layout.addWidget(self.view_in_freeview_btn)

        spherical_layout.addLayout(coordinates_layout)
        
        # Radius input
        radius_layout = QtWidgets.QHBoxLayout()
        self.radius_label = QtWidgets.QLabel("Radius (mm):")
        self.radius_input = QtWidgets.QLineEdit()
        self.radius_input.setPlaceholderText("5.0")
        radius_layout.addWidget(self.radius_label)
        radius_layout.addWidget(self.radius_input)
        spherical_layout.addLayout(radius_layout)
        
        # Cortical analysis widget
        cortical_widget = QtWidgets.QWidget()
        cortical_layout = QtWidgets.QVBoxLayout(cortical_widget)
        
        # Mesh atlas layout - create a container widget for mesh atlas options
        self.mesh_atlas_widget = QtWidgets.QWidget()
        mesh_atlas_layout = QtWidgets.QHBoxLayout(self.mesh_atlas_widget)
        self.mesh_atlas_label = QtWidgets.QLabel("Atlas Name:")
        self.atlas_name_combo = QtWidgets.QComboBox()
        self.atlas_name_combo.addItems(["DK40", "HCP_MMP1", "a2009s"])  # Add more as needed
        self.atlas_name_combo.setCurrentText("DK40")  # Set default selection
        mesh_atlas_layout.addWidget(self.mesh_atlas_label)
        mesh_atlas_layout.addWidget(self.atlas_name_combo)
        mesh_atlas_layout.addStretch(1)  # Add stretch to push elements to the left
        
        # Voxel atlas layout - create a container widget for voxel atlas options
        self.voxel_atlas_widget = QtWidgets.QWidget()
        voxel_atlas_layout = QtWidgets.QHBoxLayout(self.voxel_atlas_widget)
        self.voxel_atlas_label = QtWidgets.QLabel("Atlas File:")
        
        # Create a combo box for atlas selection (non-editable)
        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.setEditable(False)
        self.atlas_combo.setMinimumWidth(300)  # Make the combo box wider
        
        voxel_atlas_layout.addWidget(self.voxel_atlas_label)
        voxel_atlas_layout.addWidget(self.atlas_combo)
        voxel_atlas_layout.addStretch(1)  # Add stretch to push elements to the left
        
        # Add both atlas widgets to cortical layout
        cortical_layout.addWidget(self.mesh_atlas_widget)
        cortical_layout.addWidget(self.voxel_atlas_widget)
        
        # Region selection
        region_layout = QtWidgets.QHBoxLayout()
        self.region_label = QtWidgets.QLabel("Region:")
        self.region_input = QtWidgets.QLineEdit()
        self.region_input.setPlaceholderText("e.g., superiorfrontal")
        
        # Change the region info button to a regular button with text
        self.show_regions_btn = QtWidgets.QPushButton("List Regions")
        self.show_regions_btn.setToolTip("Show available regions in the selected atlas")
        self.show_regions_btn.clicked.connect(self.show_available_regions)
        self.show_regions_btn.setEnabled(False)  # Initially disabled
        
        # Make the region input wider relative to the button
        self.region_input.setMinimumWidth(200)
        self.show_regions_btn.setMaximumWidth(100)
        
        region_layout.addWidget(self.region_label)
        region_layout.addWidget(self.region_input)
        region_layout.addWidget(self.show_regions_btn)
        cortical_layout.addLayout(region_layout)
        
        # Whole head checkbox
        self.whole_head_check = QtWidgets.QCheckBox("Analyze Whole Head")
        self.whole_head_check.stateChanged.connect(self.toggle_region_input)
        cortical_layout.addWidget(self.whole_head_check)
        
        # Add widgets to stacked widget
        self.analysis_stack.addWidget(spherical_widget)
        self.analysis_stack.addWidget(cortical_widget)
        
        # Connect radio buttons to stack widget
        self.type_spherical.toggled.connect(lambda checked: self.analysis_stack.setCurrentIndex(0) if checked else None)
        self.type_cortical.toggled.connect(lambda checked: self.analysis_stack.setCurrentIndex(1) if checked else None)
        
        # Connect both space and type changes to update atlas visibility
        self.space_mesh.toggled.connect(self.update_atlas_visibility)
        self.space_voxel.toggled.connect(self.update_atlas_visibility)
        self.type_spherical.toggled.connect(self.update_atlas_visibility)
        self.type_cortical.toggled.connect(self.update_atlas_visibility)
        
        # Set initial state
        self.update_atlas_visibility()
        
        # Add stacked widget to analysis parameters
        analysis_params_layout.addWidget(self.analysis_stack)
        
        # Add analysis parameters to right layout
        right_layout.addWidget(analysis_params_container)
        
        # Visualization checkbox
        visualization_container = QtWidgets.QGroupBox("Visualization")
        visualization_layout = QtWidgets.QVBoxLayout(visualization_container)
        self.visualize_check = QtWidgets.QCheckBox("Generate Visualizations")
        self.visualize_check.setChecked(True)  # Default to checked
        visualization_layout.addWidget(self.visualize_check)
        
        # Mesh Visualization with Gmsh
        mesh_viz_layout = QtWidgets.QVBoxLayout()
        mesh_viz_label = QtWidgets.QLabel("View Mesh in Gmsh:")
        mesh_viz_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        mesh_viz_layout.addWidget(mesh_viz_label)
        
        # Mesh file dropdown and launch button
        mesh_controls_layout = QtWidgets.QHBoxLayout()
        self.mesh_combo = QtWidgets.QComboBox()
        self.mesh_combo.setMinimumWidth(200)
        self.mesh_combo.addItem("Select mesh file...")
        
        self.launch_gmsh_btn = QtWidgets.QPushButton("Launch Gmsh")
        self.launch_gmsh_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.launch_gmsh_btn.clicked.connect(self.launch_gmsh)
        self.launch_gmsh_btn.setEnabled(False)  # Initially disabled
        
        mesh_controls_layout.addWidget(self.mesh_combo)
        mesh_controls_layout.addWidget(self.launch_gmsh_btn)
        mesh_viz_layout.addLayout(mesh_controls_layout)
        
        visualization_layout.addLayout(mesh_viz_layout)
        
        # Add visualization container to right layout
        right_layout.addWidget(visualization_container)
        
        # Add left and right layouts to main horizontal layout
        main_horizontal_layout.addLayout(left_layout, 1)  # 1:2 ratio
        main_horizontal_layout.addLayout(right_layout, 2)
        
        # Add main horizontal layout to scroll layout
        scroll_layout.addLayout(main_horizontal_layout)
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Output console
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        
        self.output_console = QtWidgets.QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setMinimumHeight(200)
        self.output_console.setStyleSheet("""
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
        self.output_console.setAcceptRichText(True)
        
        # Console layout
        console_layout = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(output_label)
        header_layout.addStretch()
        
        # Create button layout for console controls
        console_buttons_layout = QtWidgets.QHBoxLayout()
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Run Analysis")
        self.run_btn.clicked.connect(self.run_analysis)
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
        self.stop_btn = QtWidgets.QPushButton("Stop Analysis")
        self.stop_btn.clicked.connect(self.stop_analysis)
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
                background-color: #555;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        
        # Add buttons to console buttons layout
        console_buttons_layout.addWidget(self.run_btn)
        console_buttons_layout.addWidget(self.stop_btn)
        console_buttons_layout.addWidget(clear_btn)
        
        # Add console buttons layout to header layout
        header_layout.addLayout(console_buttons_layout)
        
        console_layout.addLayout(header_layout)
        console_layout.addWidget(self.output_console)
        
        main_layout.addLayout(console_layout)
        
        # Connect signals
        self.subject_list.itemSelectionChanged.connect(self.update_simulations)
        self.simulation_combo.currentTextChanged.connect(self.update_field_files)
        self.space_mesh.toggled.connect(self.update_field_files)
        self.space_voxel.toggled.connect(self.update_field_files)
        
        # Connect subject list selection change signal
        self.subject_list.itemSelectionChanged.connect(self.subject_list_selection_changed)
        
        # Connect mesh visualization signals
        self.subject_list.itemSelectionChanged.connect(self.update_mesh_files)
        self.simulation_combo.currentTextChanged.connect(self.update_mesh_files)
        self.mesh_combo.currentTextChanged.connect(self.update_gmsh_button_state)
    
    def list_subjects(self):
        """List available subjects in the project directory."""
        try:
            # Get project directory from environment variable
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            if not project_dir:
                return
            
            # Clear existing items
            self.subject_list.clear()
            
            # Look for subjects in the derivatives/SimNIBS directory
            simnibs_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS')
            if not os.path.exists(simnibs_dir):
                return
            
            # Find all subject directories that have m2m_ directories
            subjects = []
            for subject_dir in os.listdir(simnibs_dir):
                if subject_dir.startswith('sub-'):
                    subject_id = subject_dir[4:]  # Remove 'sub-' prefix
                    m2m_dir = os.path.join(simnibs_dir, subject_dir, f'm2m_{subject_id}')
                    if os.path.isdir(m2m_dir):
                        subjects.append(subject_id)
            
            # Sort subjects using natural sorting
            def natural_sort_key(s):
                import re
                return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]
            
            subjects.sort(key=natural_sort_key)
            
            # Add subjects to list widget
            for subject in subjects:
                self.subject_list.addItem(subject)
            
        except Exception as e:
            print(f"Error listing subjects: {str(e)}")
    
    def clear_subject_selection(self):
        """Clear the selection in the subject list."""
        self.subject_list.clearSelection()
    
    def get_m2m_dir_for_subject(self, subject_id):
        """Get the m2m directory for the selected subject."""
        project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
        return os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}')

    def browse_field(self):
        """Open file browser to select a field file."""
        if self.space_mesh.isChecked():
            file_filter = "Mesh Files (*.msh);;All Files (*)"
        else:
            file_filter = "NIfTI Files (*.nii *.nii.gz);;MGZ Files (*.mgz);;All Files (*)"
            
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Field File",
            "",
            file_filter
        )
        
        if file_name:
            # Validate file extension
            is_mesh = file_name.endswith('.msh') and not file_name.endswith('.msh.opt')
            is_nifti = file_name.endswith('.nii') or file_name.endswith('.nii.gz')
            is_mgz = file_name.endswith('.mgz')
            
            if not ((is_mesh and self.space_mesh.isChecked()) or 
                   ((is_nifti or is_mgz) and not self.space_mesh.isChecked())):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid File Type",
                    "Please select a valid field file:\n" +
                    "- For mesh analysis: .msh files\n" +
                    "- For voxel analysis: .nii, .nii.gz, or .mgz files"
                )
                return
            
            # Add the file to the combo box
            file_basename = os.path.basename(file_name)
            
            # Check if file already exists in combo box
            found = False
            for i in range(self.field_combo.count()):
                if self.field_combo.itemData(i) == file_name:
                    self.field_combo.setCurrentIndex(i)
                    found = True
                    break
            
            if not found:
                self.field_combo.addItem(file_basename, file_name)
                self.field_combo.setCurrentIndex(self.field_combo.count() - 1)
            
            # Enable/disable field name input based on file type
            self.field_name_input.setEnabled(is_mesh)
            self.field_name_label.setEnabled(is_mesh)

    def get_available_atlas_files(self, subject_id):
        """Get available atlas files from the subject's segmentation directory."""
        atlas_files = []
        if subject_id:
            # Check SimNIBS segmentation directory
            m2m_dir = self.get_m2m_dir_for_subject(subject_id)
            segmentation_dir = os.path.join(m2m_dir, 'segmentation')
            
            # Check FreeSurfer mri directory
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", "BIDS_new"))
            freesurfer_dir = os.path.join(project_dir, "derivatives", "freesurfer", f"sub-{subject_id}", f"{subject_id}", "mri")
            
            # Define available atlases
            atlases = ['aparc.DKTatlas+aseg.mgz', 'aparc.a2009s+aseg.mgz']
            
            # Check both directories for each atlas
            for atlas in atlases:
                if os.path.exists(segmentation_dir) and os.path.exists(os.path.join(segmentation_dir, atlas)):
                    atlas_files.append((atlas, os.path.join(segmentation_dir, atlas)))
                elif os.path.exists(freesurfer_dir) and os.path.exists(os.path.join(freesurfer_dir, atlas)):
                    atlas_files.append((atlas, os.path.join(freesurfer_dir, atlas)))
            
            # If no atlases found, add warning message
            if not atlas_files:
                atlas_files.append("⚠️ FreeSurfer recon-all preprocessing required for atlas generation")
        return atlas_files

    def update_atlas_combo(self):
        """Update the atlas combo box with available files."""
        self.atlas_combo.clear()
        
        # Get selected subject
        selected_items = self.subject_list.selectedItems()
        if selected_items:
            subject_id = selected_items[0].text()
            
            # Get available atlas files
            atlas_files = self.get_available_atlas_files(subject_id)
            
            # Only show warnings if we're in voxel and cortical mode
            should_show_warnings = not self.space_mesh.isChecked() and self.type_cortical.isChecked()
            
            if not atlas_files:
                if should_show_warnings:
                    self.update_output("⚠️ Warning: No atlas files found in any directory.")
            elif isinstance(atlas_files[0], str) and atlas_files[0].startswith('⚠️'):
                if should_show_warnings:
                    self.update_output("⚠️ Warning: " + atlas_files[0].replace('⚠️ ', ''))
            
            for file in atlas_files:
                if isinstance(file, str) and file.startswith('⚠️'):
                    # Add the warning message as a non-selectable item
                    self.atlas_combo.addItem(file)
                    self.atlas_combo.model().item(self.atlas_combo.count() - 1).setEnabled(False)
                    self.show_regions_btn.setEnabled(False)
                else:
                    # Add the atlas file with its display name and full path
                    display_name, full_path = file
                    self.atlas_combo.addItem(display_name, full_path)
                    # Enable the List Regions button if we have a valid atlas
                    self.show_regions_btn.setEnabled(True)
            
            # If no valid atlas found, disable the combo box
            has_valid_atlas = len(atlas_files) > 0 and not (isinstance(atlas_files[0], str) and atlas_files[0].startswith('⚠️'))
            self.atlas_combo.setEnabled(has_valid_atlas)
            self.show_regions_btn.setEnabled(has_valid_atlas and not self.whole_head_check.isChecked())
        else:
            # If no subject selected, add placeholder and disable
            self.atlas_combo.addItem("Select a subject first")
            self.atlas_combo.setEnabled(False)
            self.show_regions_btn.setEnabled(False)

    def browse_atlas(self):
        """Open file browser to select an atlas file for voxel analysis."""
        # Try to get the m2m directory for the selected subject as initial dir
        initial_dir = ""
        if self.subject_list.selectedItems():
            subject_id = self.subject_list.selectedItems()[0].text()
            m2m_dir = self.get_m2m_dir_for_subject(subject_id)
            if os.path.exists(m2m_dir):
                initial_dir = os.path.join(m2m_dir, 'segmentation')
        
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Atlas File",
            initial_dir,
            "Atlas Files (*.nii *.nii.gz *.mgz);;All Files (*)"
        )
        
        if file_name:
            self.atlas_combo.setEditText(file_name)

    def update_atlas_visibility(self):
        """Update visibility of atlas selection based on space type and analysis type."""
        is_mesh = self.space_mesh.isChecked()
        is_cortical = self.type_cortical.isChecked()
        
        # Only show atlas controls if cortical analysis is selected
        # Also select the appropriate atlas interface based on space type
        self.mesh_atlas_widget.setVisible(is_mesh and is_cortical)
        self.voxel_atlas_widget.setVisible(not is_mesh and is_cortical)
        
        # Update field name visibility based on space
        self.field_name_input.setEnabled(is_mesh)
        self.field_name_label.setEnabled(is_mesh)
        
        # For region inputs (common to both mesh and voxel)
        # Always enable these if cortical analysis is selected
        region_enabled = is_cortical and not self.whole_head_check.isChecked()
        self.region_label.setEnabled(region_enabled)
        self.region_input.setEnabled(region_enabled)
        self.show_regions_btn.setEnabled(is_cortical)  # Enable whenever cortical is selected
        
        # Ensure the widgets are enabled/disabled appropriately
        self.mesh_atlas_widget.setEnabled(is_mesh and is_cortical)
        self.voxel_atlas_widget.setEnabled(not is_mesh and is_cortical)
        
        # Force an update of the layout
        self.mesh_atlas_widget.update()
        self.voxel_atlas_widget.update()
    
    def toggle_region_input(self, state):
        """Enable/disable region input based on whole head checkbox."""
        self.region_input.setEnabled(not state)
        self.region_label.setEnabled(not state)
        # Also disable the List Regions button if whole head is checked
        self.show_regions_btn.setEnabled(not state and self.atlas_combo.isEnabled())
    
    def validate_inputs(self):
        """Validate all input parameters before running the analysis."""
        # Check if a subject is selected
        if not self.subject_list.selectedItems() or len(self.subject_list.selectedItems()) != 1:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select one subject.")
            return False
        
        # Check if a montage is selected
        if self.simulation_combo.currentIndex() == 0:  # If placeholder is selected
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a montage.")
            return False
        
        # Check if a field file is selected
        if self.field_combo.currentIndex() == 0:  # If placeholder is selected
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a field file.")
            return False
        
        # Validate field name for mesh analysis
        if self.space_mesh.isChecked() and not self.field_name_input.text():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a field name for mesh analysis.")
            return False
        
        # Validate analysis-specific parameters
        if self.type_spherical.isChecked():
            # Validate coordinates
            try:
                x = float(self.coord_x.text() or "0")
                y = float(self.coord_y.text() or "0")
                z = float(self.coord_z.text() or "0")
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid numeric coordinates.")
                return False
            
            # Validate radius
            try:
                radius = float(self.radius_input.text() or "0")
                if radius <= 0:
                    raise ValueError
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a valid positive radius.")
                return False
        else:  # cortical
            if self.space_mesh.isChecked():
                if not self.atlas_name_combo.currentText():
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select an atlas.")
                    return False
            else:
                if not self.atlas_combo.currentText() or self.atlas_combo.currentText() == "Select atlas file...":
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select an atlas file.")
                    return False
            
            if not self.whole_head_check.isChecked() and not self.region_input.text():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a region name or select whole head analysis.")
                return False
        
        return True
    
    def run_analysis(self):
        """Run the analysis with the selected parameters."""
        if self.analysis_running:
            self.update_output("Analysis already running. Please wait or stop the current run.")
            return
        
        # Validate inputs
        if not self.validate_inputs():
            return
        
        # Show confirmation dialog
        details = self.get_analysis_details()
        if not ConfirmationDialog.confirm(
            self,
            title="Confirm Analysis",
            message="Are you sure you want to start the analysis?",
            details=details
        ):
            return
        
        # Set processing state
        self.analysis_running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # Disable all other controls
        self.disable_controls()
        
        try:
            # Get selected subjects
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            subject_id = selected_subjects[0]
            
            # Get project directory from environment
            project_dir = os.path.join('/mnt', os.environ.get('PROJECT_DIR_NAME', 'BIDS_new'))
            
            # Get simulation name from the field file path
            field_path = self.get_selected_field_path()
            simulation_name = field_path.split('/Simulations/')[1].split('/')[0]
            
            # Get target information
            if self.type_spherical.isChecked():
                target_info = f"sphere_x{self.coord_x.text() or '0'}_y{self.coord_y.text() or '0'}_z{self.coord_z.text() or '0'}_r{self.radius_input.text() or '5'}"
            else:  # cortical
                if self.whole_head_check.isChecked():
                    # For whole head analysis, include the atlas type in the directory name
                    if self.space_mesh.isChecked():
                        atlas_info = self.atlas_name_combo.currentText()
                        target_info = f"whole_head_{atlas_info}"
                    else:
                        # Get the full atlas path from the combo box's data
                        atlas_path = self.atlas_combo.currentData()
                        if not atlas_path:
                            raise ValueError("No valid atlas path found")
                        atlas_name = os.path.basename(atlas_path).split('.')[0]
                        target_info = f"whole_head_{atlas_name}"
                else:
                    target_info = f"region_{self.region_input.text()}"
            
            # Get field name
            if self.space_mesh.isChecked():
                field_name = self.field_name_input.text()
            else:
                # Extract field name from the NIfTI file name
                field_name = os.path.basename(field_path).split('_')[-1].split('.')[0]
            
            # Create organized output directory structure
            subject_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}')
            analyses_dir = os.path.join(subject_dir,'Simulations', simulation_name, 'Analyses')
            
            # Directory structure: Simulations > Simulation > Analyses > (Mesh or Voxel) > analysis_output
            analysis_type_dir = os.path.join(analyses_dir, 'Mesh' if self.space_mesh.isChecked() else 'Voxel')
            
            # Set output directory (without field name)
            output_dir = os.path.join(analysis_type_dir, target_info)
            
            # Check if output directory exists and confirm overwrite
            if os.path.exists(output_dir):
                if not confirm_overwrite(self, output_dir, "analysis directory"):
                    self.update_output("Analysis cancelled: Output directory already exists.")
                    self.analysis_finished()
                    return
            
            # Create output directory
            os.makedirs(output_dir, exist_ok=True)
            
            # Build command
            cmd = [
                'simnibs_python',
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'analyzer', 'main_analyzer.py'),
                '--m2m_subject_path', os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', f'm2m_{subject_id}'),
                '--field_path', field_path,
                '--space', 'mesh' if self.space_mesh.isChecked() else 'voxel',
                '--analysis_type', 'spherical' if self.type_spherical.isChecked() else 'cortical'
            ]
            
            # Add command line arguments based on analysis type
            if self.type_spherical.isChecked():
                cmd.extend([
                    '--coordinates', self.coord_x.text() or '0', self.coord_y.text() or '0', self.coord_z.text() or '0',
                    '--radius', self.radius_input.text() or '5'
                ])
            else:  # cortical
                # For mesh-based cortical analysis, always include atlas_name first
                if self.space_mesh.isChecked():
                    cmd.extend(['--atlas_name', self.atlas_name_combo.currentText()])
                else:
                    # Get the full atlas path from the combo box's data
                    atlas_path = self.atlas_combo.currentData()
                    if not atlas_path:
                        raise ValueError("No valid atlas path found")
                    cmd.extend(['--atlas_path', atlas_path])
                
                # Then add region or whole_head flag
                if self.whole_head_check.isChecked():
                    cmd.append('--whole_head')
                else:
                    cmd.extend(['--region', self.region_input.text()])
            
            # Add field name for mesh analysis
            if self.space_mesh.isChecked():
                cmd.extend(['--field_name', field_name])
            
            # Add output directory
            cmd.extend(['--output_dir', output_dir])
            
            # Add visualization flag if checked
            if self.visualize_check.isChecked():
                cmd.append('--visualize')
            
            # Set environment variables
            env = os.environ.copy()
            env['PROJECT_DIR'] = project_dir
            env['SUBJECT_ID'] = subject_id
            
            # Update UI
            self.disable_controls()
            self.update_output("Running analysis...")
            self.update_output(f"Analysis Type: {'Spherical' if self.type_spherical.isChecked() else 'Cortical'}")
            self.update_output(f"Space Type: {'Mesh' if self.space_mesh.isChecked() else 'Voxel'}")
            if self.type_cortical.isChecked():
                if self.space_mesh.isChecked():
                    self.update_output(f"Atlas Name: {self.atlas_name_combo.currentText()}")
                else:
                    atlas_path = self.atlas_combo.currentData()
                    if atlas_path:
                        self.update_output(f"Atlas Name: {os.path.basename(atlas_path)}")
            self.update_output(f"Command: {' '.join(cmd)}")
            
            # Create and start thread
            self.optimization_process = AnalysisThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.finished.connect(self.analysis_finished)
            self.optimization_process.start()
            
        except Exception as e:
            self.update_output(f"Error running analysis: {str(e)}")
            self.analysis_finished()
    
    def get_analysis_details(self):
        """Get formatted analysis details for confirmation dialog."""
        details = (
            f"This will run an analysis with the following parameters:\n\n"
            f"• Subject: {self.subject_list.selectedItems()[0].text()}\n"
            f"• Space: {'Mesh' if self.space_mesh.isChecked() else 'Voxel'}\n"
            f"• Analysis Type: {'Spherical' if self.type_spherical.isChecked() else 'Cortical'}\n"
            f"• Montage: {self.simulation_combo.currentText()}\n"
            f"• Field File: {self.field_combo.currentText()}\n"
        )
        
        if self.space_mesh.isChecked():
            details += f"• Field Name: {self.field_name_input.text()}\n"
        
        if self.type_spherical.isChecked():
            details += (
                f"• Coordinates: ({self.coord_x.text() or '0'}, {self.coord_y.text() or '0'}, {self.coord_z.text() or '0'})\n"
                f"• Radius: {self.radius_input.text() or '5'} mm\n"
            )
        else:
            if self.space_mesh.isChecked():
                details += f"• Atlas: {self.atlas_name_combo.currentText()}\n"
            else:
                details += f"• Atlas File: {self.atlas_combo.currentText()}\n"
            
            if self.whole_head_check.isChecked():
                details += "• Analysis: Whole Head\n"
            else:
                details += f"• Region: {self.region_input.text()}\n"
        
        details += f"• Generate Visualizations: {'Yes' if self.visualize_check.isChecked() else 'No'}"
        
        return details
    
    def analysis_finished(self):
        """Handle analysis completion."""
        # Guard against recursive calls
        if hasattr(self, '_processing_analysis_finished') and self._processing_analysis_finished:
            return
        
        self._processing_analysis_finished = True
        try:
            # Don't show completion message if the last line indicates analysis failed
            last_line = self.output_console.toPlainText().strip().split('\n')[-1]
            if "WARNING: Analysis Failed" in last_line:
                # Just reset the UI state without showing completion message
                self.analysis_running = False
                self.run_btn.setEnabled(True)
                self.run_btn.setText("Run Analysis")
                self.stop_btn.setEnabled(False)
                self.enable_controls()
                return

            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">✅ Analysis process completed ✅</span></div>')
            self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')
            
            # Get current analysis information
            subject_id = self.subject_list.selectedItems()[0].text()
            simulation_name = self.simulation_combo.currentText()
            analysis_type = 'Mesh' if self.space_mesh.isChecked() else 'Voxel'
            
            # Emit signal to notify other tabs
            self.analysis_completed.emit(subject_id, simulation_name, analysis_type)
            
            self.analysis_running = False
            self.run_btn.setEnabled(True)
            self.run_btn.setText("Run Analysis")
            self.stop_btn.setEnabled(False)
            
            # Re-enable all controls
            self.enable_controls()
        finally:
            self._processing_analysis_finished = False
    
    def stop_analysis(self):
        """Stop the running analysis."""
        if hasattr(self, 'analysis_process') and self.analysis_process:
            # Show stopping message
            self.update_output("Stopping analysis...")
            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">⚠️ Analysis terminated by user ⚠️</span></div>')
            
            # Terminate the process
            if self.analysis_process.terminate_process():
                self.update_output("Analysis process terminated successfully.")
            else:
                self.update_output("Failed to terminate analysis process or process already completed.")
            
            # Reset UI state
            self.analysis_running = False
            self.run_btn.setEnabled(True)
            self.run_btn.setText("Run Analysis")
            self.stop_btn.setEnabled(False)
            
            # Re-enable all controls
            self.enable_controls()
    
    def clear_console(self):
        """Clear the output console."""
        self.output_console.clear()
    
    def update_output(self, text):
        """Update the console output with colored text."""
        if not text.strip():
            return
            
        # Format the output based on content type
        if "Processing... Only the Stop button is available" in text:
            formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #ffff55; font-weight: bold;">{text}</span></div>'
        elif "Error:" in text or "CRITICAL:" in text or "Failed" in text:
            formatted_text = f'<span style="color: #ff5555;"><b>{text}</b></span>'
        elif "Warning:" in text or "YELLOW" in text:
            formatted_text = f'<span style="color: #ffff55;">{text}</span>'
        elif "DEBUG:" in text:
            formatted_text = f'<span style="color: #7f7f7f;">{text}</span>'
        elif "Executing:" in text or "Running" in text or "Command" in text:
            formatted_text = f'<span style="color: #55aaff;">{text}</span>'
        elif "completed successfully" in text or "completed." in text or "Successfully" in text or "completed:" in text:
            formatted_text = f'<span style="color: #55ff55;"><b>{text}</b></span>'
        elif "Processing" in text or "Starting" in text:
            formatted_text = f'<span style="color: #55ffff;">{text}</span>'
        elif "Analysis Results Summary:" in text:
            formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #55ff55; font-weight: bold; font-size: 14px;">{text}</span></div>'
        elif any(value_type in text for value_type in ["Mean Value:", "Max Value:", "Min Value:"]):
            # Extract the value type and the numeric value
            parts = text.split(":")
            if len(parts) == 2:
                value_type, value = parts
                formatted_text = f'<div style="margin: 5px 20px;"><span style="color: #aaaaaa;">{value_type}:</span> <span style="color: #55ffff; font-weight: bold;">{value}</span></div>'
            else:
                formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        elif text.strip().startswith("-"):
            # Indented list items
            formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
        else:
            formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        
        # Append to the console with HTML formatting
        self.output_console.append(formatted_text)
        self.output_console.ensureCursorVisible()
        # Removed QtWidgets.QApplication.processEvents() to prevent recursion issues
    
    def disable_controls(self):
        """Disable all controls except the stop button."""
        # Disable all buttons
        self.list_subjects_btn.setEnabled(False)
        self.clear_subject_selection_btn.setEnabled(False)
        self.browse_field_btn.setEnabled(False)
        self.show_regions_btn.setEnabled(False)
        
        # Disable all inputs
        self.subject_list.setEnabled(False)
        self.simulation_combo.setEnabled(False)
        self.field_combo.setEnabled(False)
        self.field_name_input.setEnabled(False)
        self.space_mesh.setEnabled(False)
        self.space_voxel.setEnabled(False)
        self.type_spherical.setEnabled(False)
        self.type_cortical.setEnabled(False)
        self.coord_x.setEnabled(False)
        self.coord_y.setEnabled(False)
        self.coord_z.setEnabled(False)
        self.radius_input.setEnabled(False)
        self.atlas_name_combo.setEnabled(False)
        self.atlas_combo.setEnabled(False)
        self.region_input.setEnabled(False)
        self.whole_head_check.setEnabled(False)
        self.visualize_check.setEnabled(False)
        
        # Show processing message in status label
        self.status_label.setText("Processing... Only the Stop button is available")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #f44336;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
                min-height: 15px;
                max-height: 15px;
            }
        """)
        self.status_label.setAlignment(QtCore.Qt.AlignVCenter)
        self.status_label.show()
    
    def enable_controls(self):
        """Re-enable all controls."""
        # Enable all buttons
        self.list_subjects_btn.setEnabled(True)
        self.clear_subject_selection_btn.setEnabled(True)
        self.browse_field_btn.setEnabled(True)
        self.show_regions_btn.setEnabled(True)
        
        # Enable all inputs
        self.subject_list.setEnabled(True)
        self.simulation_combo.setEnabled(True)
        self.field_combo.setEnabled(True)
        self.field_name_input.setEnabled(True)
        self.space_mesh.setEnabled(True)
        self.space_voxel.setEnabled(True)
        self.type_spherical.setEnabled(True)
        self.type_cortical.setEnabled(True)
        self.coord_x.setEnabled(True)
        self.coord_y.setEnabled(True)
        self.coord_z.setEnabled(True)
        self.radius_input.setEnabled(True)
        self.atlas_name_combo.setEnabled(True)
        self.atlas_combo.setEnabled(True)
        self.region_input.setEnabled(True)
        self.whole_head_check.setEnabled(True)
        self.visualize_check.setEnabled(True)
        
        # Hide processing message
        self.status_label.hide()

    def update_simulations(self):
        """Update the montage list based on selected subject."""
        self.simulation_combo.clear()
        self.field_combo.clear()
        
        # Add placeholder items
        self.simulation_combo.addItem("Select montage...")
        self.field_combo.addItem("Select field file...")
        
        selected_items = self.subject_list.selectedItems()
        if not selected_items:
            return
            
        subject_id = selected_items[0].text()
        project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
        simulations_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 'Simulations')
        
        if not os.path.exists(simulations_dir):
            return
            
        # List all montage directories
        simulations = [d for d in os.listdir(simulations_dir) 
                      if os.path.isdir(os.path.join(simulations_dir, d))]
        
        # Add montages to combo box
        self.simulation_combo.addItems(sorted(simulations))

    def update_field_files(self):
        """Update the field files list based on selected montage and analysis type."""
        current_text = self.field_combo.currentText()
        self.field_combo.clear()
        
        # Add placeholder
        self.field_combo.addItem("Select field file...")
        
        # Get selected items
        selected_items = self.subject_list.selectedItems()
        
        # Function to add placeholder and return
        def add_placeholder():
            if self.field_combo.findText("Select field file...") == -1:  # Only add if not already present
                self.field_combo.addItem("Select field file...")
                self.field_combo.setCurrentIndex(0)
        
        # If no montage is selected, just show the placeholder
        if not selected_items or self.simulation_combo.currentIndex() == 0:
            add_placeholder()
            return
            
        subject_id = selected_items[0].text()
        simulation_name = self.simulation_combo.currentText()
        project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
        simulation_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', 
                                    f'sub-{subject_id}', 'Simulations', simulation_name)
        
        # Determine the search path based on analysis type
        if self.space_mesh.isChecked():
            search_dir = os.path.join(simulation_dir, 'TI', 'mesh')
        else:  # voxel
            search_dir = os.path.join(simulation_dir, 'TI', 'niftis')
        
        if not os.path.exists(search_dir):
            add_placeholder()
            return
            
        # List all files in directory
        try:
            all_files = os.listdir(search_dir)
        except Exception as e:
            print(f"Error reading directory {search_dir}: {str(e)}")
            add_placeholder()
            return
            
        # Filter files based on space type
        if self.space_mesh.isChecked():
            # Show all .msh files except .msh.opt
            field_files = [f for f in all_files if f.endswith('.msh') and not f.endswith('.msh.opt')]
        else:
            # Show all nifti and mgz files
            field_files = [f for f in all_files if any(f.endswith(ext) for ext in ['.nii', '.nii.gz', '.mgz'])]
        
        # Add placeholder only if no files found
        if not field_files:
            add_placeholder()
            return
            
        # Sort files and separate 'grey_' prefixed files
        grey_files = [f for f in field_files if f.startswith('grey_')]
        other_files = [f for f in field_files if not f.startswith('grey_')]
        
        # For voxel analysis, further separate grey files into MNI and non-MNI
        if not self.space_mesh.isChecked():
            grey_mni_files = [f for f in grey_files if '_MNI_' in f]
            grey_non_mni_files = [f for f in grey_files if '_MNI_' not in f]
            # Add files to combo box with full paths, non-MNI grey files first, then MNI grey files
            for file in sorted(grey_non_mni_files):
                self.field_combo.addItem(file, os.path.join(search_dir, file))
            for file in sorted(grey_mni_files):
                self.field_combo.addItem(file, os.path.join(search_dir, file))
            for file in sorted(other_files):
                self.field_combo.addItem(file, os.path.join(search_dir, file))
            
            # Set default selection for voxel analysis
            if grey_non_mni_files:  # If we have non-MNI grey files
                self.field_combo.setCurrentIndex(1)  # Select first non-MNI grey file
            elif current_text != "Select field file...":  # Try to restore previous selection
                index = self.field_combo.findText(current_text)
                if index >= 0:
                    self.field_combo.setCurrentIndex(index)
        else:
            # For mesh analysis, add all grey files together
            for file in sorted(grey_files):
                self.field_combo.addItem(file, os.path.join(search_dir, file))
            for file in sorted(other_files):
                self.field_combo.addItem(file, os.path.join(search_dir, file))
            
            # Set default selection for mesh analysis
            if current_text != "Select field file...":  # Try to restore previous selection
                index = self.field_combo.findText(current_text)
                if index >= 0:
                    self.field_combo.setCurrentIndex(index)
            elif grey_files:  # If we have grey files, select the first one
                self.field_combo.setCurrentIndex(1)

    def get_selected_field_path(self):
        """Get the full path of the selected field file."""
        if self.field_combo.currentIndex() == 0:  # If placeholder is selected
            return None
        return self.field_combo.currentData()
    
    def show_available_regions(self):
        """Show a dialog with available regions for the selected atlas."""
        try:
            # Check if a subject is selected
            if not self.subject_list.selectedItems():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a subject first.")
                return

            # Create a progress dialog to show loading status
            progress_dialog = QtWidgets.QProgressDialog("Loading atlas regions...", "Cancel", 0, 100, self)
            progress_dialog.setWindowTitle("Loading Atlas")
            progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
            progress_dialog.setMinimumDuration(500)  # Only show if operation takes more than 500ms
            progress_dialog.setValue(10)
            
            # Get the appropriate atlas information based on the analysis type (mesh or voxel)
            if self.space_mesh.isChecked():
                # For mesh analysis
                if not self.atlas_name_combo.currentText():
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select an atlas first.")
                    return
                
                atlas_type = self.atlas_name_combo.currentText()
                subject_id = self.subject_list.selectedItems()[0].text()
                m2m_dir = self.get_m2m_dir_for_subject(subject_id)
                
                progress_dialog.setValue(30)
                QtWidgets.QApplication.processEvents()
                
                # Load the atlas using simnibs
                import simnibs
                try:
                    self.update_output(f"Loading {atlas_type} atlas...")
                    progress_dialog.setValue(50)
                    QtWidgets.QApplication.processEvents()
                    
                    atlas = simnibs.subject_atlas(atlas_type, m2m_dir)
                    regions = sorted(atlas.keys())
                    
                    progress_dialog.setValue(80)
                    QtWidgets.QApplication.processEvents()
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load atlas: {str(e)}")
                    return
            else:
                # For voxel analysis with MGZ/NIfTI atlas
                if not self.atlas_combo.currentText() or self.atlas_combo.currentText().startswith('⚠️'):
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select an atlas file first.")
                    return
                
                # Get the full path from the combo box's data
                atlas_file = self.atlas_combo.currentData()  # Use currentData() instead of currentText()
                if not atlas_file:
                    QtWidgets.QMessageBox.warning(self, "Warning", "No valid atlas file path found.")
                    return
                
                # Get atlas type from filename
                atlas_basename = os.path.basename(atlas_file).lower()
                if 'dk' in atlas_basename or 'desikan' in atlas_basename:
                    atlas_type = "DK Atlas"
                elif 'aseg' in atlas_basename:
                    atlas_type = "Aseg Atlas"
                elif 'hcp' in atlas_basename or 'mmp' in atlas_basename:
                    atlas_type = "HCP-MMP Atlas"
                elif 'a2009s' in atlas_basename or 'destrieux' in atlas_basename:
                    atlas_type = "Destrieux Atlas"
                else:
                    atlas_type = os.path.basename(atlas_file)
                
                progress_dialog.setValue(30)
                QtWidgets.QApplication.processEvents()
                
                # Get the segmentation directory (parent directory of the atlas file)
                segmentation_dir = os.path.dirname(atlas_file)
                
                # Define the output file path in the segmentation directory
                atlas_name = os.path.splitext(os.path.basename(atlas_file))[0]
                if atlas_name.endswith('.nii'):  # Handle .nii.gz case
                    atlas_name = os.path.splitext(atlas_name)[0]
                output_file = os.path.join(segmentation_dir, f"{atlas_name}_labels.txt")
                
                # Extract region information using FreeSurfer's tools
                try:
                    # Check if we already have the labels file
                    if os.path.exists(output_file):
                        self.update_output(f"Using existing labels file: {output_file}")
                        progress_dialog.setValue(70)
                    else:
                        self.update_output(f"Generating labels file: {output_file}")
                        # Use mri_segstats to get atlas information
                        cmd = [
                            'mri_segstats',
                            '--seg', atlas_file,
                            '--excludeid', '0',  # Exclude background
                            '--ctab-default',    # Use default color table
                            '--sum', output_file
                        ]
                        
                        self.update_output(f"Running: {' '.join(cmd)}")
                        progress_dialog.setValue(50)
                        
                        # We'll use QProcess to run the command asynchronously
                        process = QtCore.QProcess()
                        process.start(cmd[0], cmd[1:])
                        
                        # Wait for the process to finish with updates to the progress dialog
                        while process.state() != QtCore.QProcess.NotRunning:
                            QtWidgets.QApplication.processEvents()
                            if progress_dialog.wasCanceled():
                                process.kill()
                                return
                            
                            # Increment progress slowly
                            current_progress = progress_dialog.value()
                            if current_progress < 70:
                                progress_dialog.setValue(current_progress + 1)
                            QtWidgets.QApplication.processEvents()
                            QtCore.QThread.msleep(100)  # Sleep to avoid high CPU usage
                        
                        # Check if process finished successfully
                        if process.exitCode() != 0:
                            error = process.readAllStandardError().data().decode()
                            raise Exception(f"Error running mri_segstats: {error}")
                    
                    progress_dialog.setValue(75)
                    QtWidgets.QApplication.processEvents()
                    
                    # Parse the output file to extract region information
                    regions = []
                    with open(output_file, 'r') as f:
                        in_header = True
                        for line in f:
                            # Skip header lines
                            if in_header and not line.startswith('#'):
                                in_header = False
                            
                            # Process data lines (non-header)
                            if not in_header and line.strip():
                                parts = line.strip().split()
                                if len(parts) >= 5:
                                    # Structure name can contain spaces, so join the remaining parts
                                    region_name = ' '.join(parts[4:])
                                    region_id = parts[1]  # SegId is the second column
                                    regions.append(f"{region_name} (ID: {region_id})")
                    
                    # Sort regions
                    regions = sorted(regions)
                    
                    progress_dialog.setValue(90)
                    QtWidgets.QApplication.processEvents()
                    
                    if not regions:
                        raise Exception("No regions found in atlas file")
                        
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Failed to extract regions from atlas: {str(e)}")
                    return

            progress_dialog.setValue(95)
            QtWidgets.QApplication.processEvents()
            
            # Create and show the dialog
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle(f"Available Regions - {atlas_type}")
            dialog.setMinimumWidth(400)
            dialog.setMinimumHeight(500)

            # Create layout
            layout = QtWidgets.QVBoxLayout(dialog)

            # Add search box
            search_layout = QtWidgets.QHBoxLayout()
            search_label = QtWidgets.QLabel("Search:")
            search_input = QtWidgets.QLineEdit()
            search_layout.addWidget(search_label)
            search_layout.addWidget(search_input)
            layout.addLayout(search_layout)

            # Add list widget
            list_widget = QtWidgets.QListWidget()
            list_widget.addItems(regions)
            layout.addWidget(list_widget)

            # Add copy button
            button_layout = QtWidgets.QHBoxLayout()
            copy_btn = QtWidgets.QPushButton("Copy Selected")
            close_btn = QtWidgets.QPushButton("Close")
            button_layout.addWidget(copy_btn)
            button_layout.addWidget(close_btn)
            layout.addLayout(button_layout)

            # Close the progress dialog
            progress_dialog.setValue(100)
            progress_dialog.close()

            # Connect signals
            def filter_regions(text):
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    item.setHidden(text.lower() not in item.text().lower())

            def copy_selected():
                if list_widget.currentItem():
                    selected_text = list_widget.currentItem().text()
                    
                    # For voxel analysis with ID in parentheses, extract just the region name
                    if not self.space_mesh.isChecked() and " (ID: " in selected_text:
                        # Extract just the region name
                        region_name = selected_text.split(" (ID: ")[0]
                        self.region_input.setText(region_name)
                    else:
                        self.region_input.setText(selected_text)
                    
                    dialog.accept()

            search_input.textChanged.connect(filter_regions)
            copy_btn.clicked.connect(copy_selected)
            close_btn.clicked.connect(dialog.reject)
            list_widget.itemDoubleClicked.connect(lambda item: (
                copy_selected()
            ))

            # Show the dialog
            dialog.exec_()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to get regions: {str(e)}")
            import traceback
            self.update_output(f"Error details: {traceback.format_exc()}")

    def load_t1_in_freeview(self):
        """Load the subject's T1 NIfTI file in Freeview."""
        try:
            # Check if a subject is selected
            if not self.subject_list.selectedItems():
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a subject first")
                return
            
            subject_id = self.subject_list.selectedItems()[0].text()
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            t1_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                                  f"m2m_{subject_id}", "T1.nii.gz")
            
            if not os.path.exists(t1_path):
                QtWidgets.QMessageBox.warning(self, "Error", f"T1 NIfTI file not found: {t1_path}")
                return
            
            # Launch Freeview with the T1 image
            subprocess.Popen(["freeview", t1_path])
            self.update_output(f"Launched Freeview with T1 image: {t1_path}")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Freeview: {str(e)}")
            self.update_output(f"Error launching Freeview: {str(e)}")

    def subject_list_selection_changed(self):
        """Handle subject selection changes."""
        self.update_simulations()
        self.update_atlas_combo()

    def update_mesh_files(self):
        """Update the mesh files dropdown based on selected subject and montage."""
        try:
            # Clear existing items
            self.mesh_combo.clear()
            self.mesh_combo.addItem("Select mesh file...")
            
            # Check if subject and montage are selected
            if not self.subject_list.selectedItems():
                return
                
            subject_id = self.subject_list.selectedItems()[0].text()
            simulation = self.simulation_combo.currentText()
            
            if not simulation or simulation == "Select montage...":
                return
            
            project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
            mesh_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                                   "Simulations", simulation, "Analyses", "Mesh")
            
            if not os.path.exists(mesh_dir):
                self.update_output(f"Mesh directory not found: {mesh_dir}")
                return
            
            # Find all .msh files recursively
            mesh_files = []
            for root, dirs, files in os.walk(mesh_dir):
                for file in files:
                    if file.endswith('.msh'):
                        full_path = os.path.join(root, file)
                        # Store relative path from mesh_dir for cleaner display
                        rel_path = os.path.relpath(full_path, mesh_dir)
                        mesh_files.append((rel_path, full_path))
            
            # Sort mesh files by name
            mesh_files.sort(key=lambda x: x[0])
            
            # Add mesh files to combo box
            for rel_path, full_path in mesh_files:
                # Extract just the filename without extension for cleaner display
                display_name = os.path.splitext(os.path.basename(rel_path))[0]
                self.mesh_combo.addItem(display_name, full_path)
            
            if mesh_files:
                self.update_output(f"Found {len(mesh_files)} mesh file(s) for {subject_id}/{simulation}")
            else:
                self.update_output(f"No mesh files found for {subject_id}/{simulation}")
                
        except Exception as e:
            self.update_output(f"Error updating mesh files: {str(e)}")

    def launch_gmsh(self):
        """Launch Gmsh with the selected mesh file."""
        try:
            if self.mesh_combo.currentText() == "Select mesh file...":
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a mesh file first")
                return
            
            # Get the full path to the selected mesh file
            mesh_file_path = self.mesh_combo.currentData()
            
            if not mesh_file_path or not os.path.exists(mesh_file_path):
                QtWidgets.QMessageBox.warning(self, "Error", "Selected mesh file not found")
                return
            
            # Create a temporary Gmsh script to set display options
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.geo', delete=False) as script_file:
                script_content = f'''// Gmsh script to load mesh with all mesh elements hidden
// Hide all mesh elements for clean visualization
Mesh.SurfaceFaces = 0;  // Hide 2D surface faces
Mesh.VolumeFaces = 0;   // Hide 3D volume faces  
Mesh.SurfaceEdges = 0;  // Hide 2D element edges
Mesh.VolumeEdges = 0;   // Hide 3D element edges
Mesh.Points = 0;        // Hide mesh points
Mesh.Lines = 0;         // Hide 1D elements/lines

// Open the mesh file
Merge "{mesh_file_path.replace(chr(92), '/')}";

// Set some additional display options for better visualization
General.Trackball = 1;
General.RotationX = 0;
General.RotationY = 0;
General.RotationZ = 0;
'''
                script_file.write(script_content)
                script_file_path = script_file.name
            
            # Launch Gmsh with the script
            subprocess.Popen(["gmsh", script_file_path])
            self.update_output(f"Launched Gmsh with mesh file: {mesh_file_path}")
            self.update_output("Gmsh display: 2D faces hidden, wireframe edges visible")
            
            # Clean up the temporary script file after a delay
            import threading
            def cleanup_script():
                import time
                time.sleep(5)  # Wait 5 seconds for Gmsh to load
                try:
                    os.unlink(script_file_path)
                except:
                    pass  # Ignore cleanup errors
            
            threading.Thread(target=cleanup_script, daemon=True).start()
            
        except FileNotFoundError:
            QtWidgets.QMessageBox.critical(self, "Error", 
                "Gmsh not found. Please ensure Gmsh is installed and available in PATH.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Gmsh: {str(e)}")
            self.update_output(f"Error launching Gmsh: {str(e)}")

    def update_gmsh_button_state(self):
        """Enable/disable the Launch Gmsh button based on selected mesh file."""
        self.launch_gmsh_btn.setEnabled(bool(self.mesh_combo.currentText()) and self.mesh_combo.currentText() != "Select mesh file...")