#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Simulator Tab
This module provides a GUI interface for the simulator functionality.
"""

import os
import json
import re
import subprocess
import sys
import time
import threading
from pathlib import Path
import datetime
import tempfile
import shutil

# Add project root to path for tools import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite, is_verbose_message, is_important_message
from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons
from core import get_path_manager, constants as const
from tools.report_util import get_simulation_report_generator

# Utility: strip ANSI/VT100 escape sequences from text (e.g., "\x1b[0;32m")
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color/control sequences from a string."""
    if not text:
        return text
    # Remove standard CSI sequences
    cleaned = ANSI_ESCAPE_PATTERN.sub('', text)
    # Remove any stray ESC characters that might remain
    cleaned = cleaned.replace('\x1b', '')
    return cleaned

class SimulationThread(QtCore.QThread):
    """Thread to run simulation in background to prevent GUI freezing."""
    
    # Signal to emit output text with message type
    output_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(SimulationThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        
    def run(self):
        """Run the simulation command in a separate thread."""
        try:
            # Create process in its own process group for proper termination
            if os.name == 'nt':  # Windows
                self.process = subprocess.Popen(
                    self.cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    env=self.env
                )
            else:  # Unix/Linux/Mac
                self.process = subprocess.Popen(
                    self.cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                    preexec_fn=os.setsid,  # Create new process group
                    env=self.env
                )
            
            # Real-time output display with message type detection
            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ''):
                    if self.terminated:
                        break
                    if line:
                        # Strip ANSI escape sequences and detect message type based on content
                        raw_line = line.rstrip('\n')
                        line_clean = strip_ansi_codes(raw_line)
                        line_stripped = line_clean.strip()
                        lowered = line_stripped.lower()
                        # Detect error messages from bracketed message types (including timestamped format)
                        # Format: [2025-08-18 18:32:19] [main-TI] [ERROR] Message...
                        is_error_tag = (
                            '[ERROR]' in line_stripped or 
                            'ERROR:' in line_stripped
                        )
                        if is_error_tag:
                            message_type = 'error'
                        elif ('[WARNING]' in line_stripped) or ('Warning:' in line_stripped):
                            message_type = 'warning'
                        elif '[INFO]' in line_stripped:
                            message_type = 'info'
                        elif '[DEBUG]' in line_stripped:
                            message_type = 'debug'
                        elif any(keyword in lowered for keyword in ['executing:', 'running', 'command']):
                            message_type = 'command'
                        # Be conservative about success: allow explicit [SUCCESS] or clear non-debug "completed successfully"
                        elif line_stripped.startswith('[SUCCESS]') or ('completed successfully' in lowered and 'debug' not in lowered):
                            message_type = 'success'
                        elif any(keyword in lowered for keyword in ['processing', 'starting']):
                            message_type = 'info'
                        else:
                            message_type = 'default'
                        
                        self.output_signal.emit(line_stripped, message_type)
            
            # Check process completion
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    self.error_signal.emit(f"Process returned non-zero exit code ({returncode})")
                    
        except Exception as e:
            self.error_signal.emit(f"Error running simulation: {str(e)}")
    
    def terminate_process(self):
        """Terminate the running process and all its children."""
        if self.process and self.process.poll() is None:  # Process is still running
            self.terminated = True
            import signal
            
            if os.name == 'nt':  # Windows
                # Use taskkill with /T flag to kill entire process tree
                try:
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], 
                                    stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                except:
                    pass
            else:  # Unix/Linux/Mac
                try:
                    # Kill the entire process group using SIGTERM first
                    pgid = os.getpgid(self.process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    
                    # Wait briefly for graceful termination
                    try:
                        self.process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        # If still running, force kill with SIGKILL
                        try:
                            os.killpg(pgid, signal.SIGKILL)
                        except:
                            pass
                        # Force kill the main process as backup
                        try:
                            self.process.kill()
                        except:
                            pass
                except Exception as e:
                    # Fallback: try to kill the main process directly
                    try:
                        self.process.kill()
                    except:
                        pass
            
            # Final cleanup - ensure process is terminated
            try:
                self.process.wait(timeout=1)
            except:
                pass
            
            return True
        return False

    def _parse_flex_search_name(self, search_name, electrode_type):
        """
        Parse flex-search name and create proper naming format.
        
        Args:
            search_name: Search directory name with format:
                        - Atlas: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
                        - Spherical: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
                        - Subcortical: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
                        - Legacy cortical: {hemisphere}.{region}_{atlas}_{goal}_{postprocess}
            electrode_type: 'mapped' or 'optimized'
            
        Returns:
            str: Formatted name following flex_{hemisphere}_{atlas}_{region}_{goal}_{postproc}_{electrode_type}
        """
        try:
            # Clean the search name first
            search_name = search_name.strip()
            
            # Handle new naming convention first
            
            # Handle spherical search names: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
            if search_name.startswith('sphere_'):
                parts = search_name.split('_')
                if len(parts) >= 3:
                    hemisphere = 'spherical'
                    # Extract coordinate part (e.g., x10y-5z20r5)
                    coords_part = parts[1] if len(parts) > 1 else 'coords'
                    goal = parts[-2] if len(parts) >= 3 else 'optimization'
                    post_proc = parts[-1] if len(parts) >= 3 else 'maxTI'
                    
                    return f"flex_{hemisphere}_{coords_part}_{goal}_{post_proc}_{electrode_type}"
            
            # Handle subcortical search names: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
            elif search_name.startswith('subcortical_'):
                parts = search_name.split('_')
                if len(parts) >= 5:
                    hemisphere = 'subcortical'
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = parts[4]
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Handle cortical search names: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
            elif '_' in search_name and len(search_name.split('_')) >= 5:
                parts = search_name.split('_')
                if len(parts) >= 5 and parts[0] in ['lh', 'rh']:
                    hemisphere = parts[0]
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = parts[4]
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Fallback: Handle legacy formats for backward compatibility
            
            # Legacy cortical search names: lh.101_DK40_14_mean
            elif search_name.startswith(('lh.', 'rh.')):
                parts = search_name.split('_')
                if len(parts) >= 3:
                    hemisphere_region = parts[0]  # e.g., 'lh.101'
                    atlas = parts[1]  # e.g., 'DK40'
                    goal_postproc = '_'.join(parts[2:])  # e.g., '14_mean'
                    
                    # Extract hemisphere and region
                    if '.' in hemisphere_region:
                        hemisphere, region = hemisphere_region.split('.', 1)
                    else:
                        hemisphere = 'unknown'
                        region = hemisphere_region
                    
                    # Split goal and postProc if possible
                    if '_' in goal_postproc:
                        goal_parts = goal_postproc.split('_')
                        region = goal_parts[0]  # First part is actually the region
                        goal = goal_parts[1] if len(goal_parts) > 1 else 'optimization'
                        post_proc = '_'.join(goal_parts[2:]) if len(goal_parts) > 2 else 'maxTI'
                    else:
                        goal = goal_postproc
                        post_proc = 'maxTI'
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Legacy subcortical search names: subcortical_atlas_region_goal
            elif search_name.startswith('subcortical_') and len(search_name.split('_')) == 4:
                parts = search_name.split('_')
                if len(parts) >= 4:
                    hemisphere = 'subcortical'
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = 'maxTI'  # Default for legacy
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Legacy spherical coordinates: assume any other format with underscores
            elif '_' in search_name:
                parts = search_name.split('_')
                hemisphere = 'spherical'
                atlas = 'coordinates'
                region = '_'.join(parts[:-1]) if len(parts) > 1 else search_name
                goal = parts[-1] if parts else 'optimization'
                post_proc = 'maxTI'
                
                return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Fallback for unrecognized formats
            else:
                return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"
                
        except Exception as e:
            self.update_output(f"Warning: Could not parse flex search name '{search_name}': {e}", 'warning')
            return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"
            
    def cleanup_old_simulation_directories(self, subject_id):
        """
        Clean up old simulation directories that might interfere with flex-search discovery.
        Only removes directories that don't have recent simulation results.
        """
        try:
            # Get simulation directory using path manager
            simulation_dir = self.pm.get_simulation_dir(subject_id, 'Simulations')
            
            if not simulation_dir or not os.path.exists(simulation_dir):
                return
            
            # Get current time
            current_time = time.time()
            cutoff_time = current_time - (24 * 60 * 60)  # 24 hours ago
            
            for item in os.listdir(simulation_dir):
                item_path = os.path.join(simulation_dir, item)
                
                # Skip tmp directory and files
                if not os.path.isdir(item_path) or item == 'tmp':
                    continue
                
                # Check if directory is old and potentially stale
                try:
                    dir_mtime = os.path.getmtime(item_path)
                    
                    # If directory is older than cutoff and doesn't have recent TI results, consider removing
                    if dir_mtime < cutoff_time:
                        ti_mesh_path = os.path.join(item_path, 'TI', 'mesh')
                        
                        # Check if it has valid TI results
                        has_valid_results = False
                        if os.path.exists(ti_mesh_path):
                            for file in os.listdir(ti_mesh_path):
                                if file.endswith('_TI.msh') and os.path.getmtime(os.path.join(ti_mesh_path, file)) > cutoff_time:
                                    has_valid_results = True
                                    break
                        
                        # If no valid recent results, ask user if they want to clean up
                        if not has_valid_results:
                            self.update_output(f"Found old simulation directory: {item} (last modified: {datetime.datetime.fromtimestamp(dir_mtime).strftime('%Y-%m-%d %H:%M')})", 'info')
                            # For now, just warn - in the future could add cleanup logic
                            
                except Exception as e:
                    self.update_output(f"Warning: Could not check directory {item}: {e}", 'warning')
                    
        except Exception as e:
            self.update_output(f"Warning: Could not clean up old directories: {e}", 'warning')

class SimulatorTab(QtWidgets.QWidget):
    """Tab for simulator functionality."""
    
    def __init__(self, parent=None):
        super(SimulatorTab, self).__init__(parent)
        self.parent = parent
        self.simulation_running = False
        self.simulation_process = None
        self.custom_conductivities = {}  # keys: int tissue number, values: float
        self.report_generator = None
        self.simulation_session_id = None
        self._had_errors_during_run = False
        self._aborting_due_to_error = False
        self._current_run_subjects = []
        self._current_run_is_montage = True
        self._current_run_montages = []
        self._run_start_time = None
        self._project_dir_path_current = None
        # Initialize debug mode (default to False)
        self.debug_mode = False
        # Initialize path manager
        self.pm = get_path_manager()
        self.setup_ui()
        
        # Initialize with available subjects and montages
        QtCore.QTimer.singleShot(500, self.list_subjects)
        QtCore.QTimer.singleShot(700, self.update_montage_list)
        QtCore.QTimer.singleShot(900, self.refresh_flex_search_list)
        QtCore.QTimer.singleShot(1000, self.initialize_ui_state)  # Initialize UI state silently
        
    def setup_ui(self):
        """Set up the user interface for the simulator tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create a scroll area for the form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Main horizontal layout to separate left and right
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        
        # Left side layout for subjects and montages
        left_layout = QtWidgets.QVBoxLayout()
        
        # Subject selection
        subject_container = QtWidgets.QGroupBox("Subject(s)")
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        
        # Create horizontal layout for list and buttons side by side
        subject_content_layout = QtWidgets.QHBoxLayout()
        
        # List widget for subject selection
        self.subject_list = QtWidgets.QListWidget()
        self.subject_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.subject_list.setMinimumHeight(90)  # Reduced by 10% (100 * 0.9 = 90)
        self.subject_list.itemSelectionChanged.connect(self.refresh_flex_search_list)  # Refresh flex-search when subjects change
        self.subject_list.itemSelectionChanged.connect(self.update_freehand_configs)  # Refresh free-hand configs when subjects change
        self.subject_list.itemSelectionChanged.connect(self.populate_flex_eeg_nets)  # Populate flex EEG nets when subjects change
        subject_content_layout.addWidget(self.subject_list)
        
        # Subject control buttons in vertical layout on the right
        subject_button_layout = QtWidgets.QVBoxLayout()
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        self.select_all_subjects_btn = QtWidgets.QPushButton("Select All")
        self.select_all_subjects_btn.clicked.connect(self.select_all_subjects)
        self.clear_subject_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_subject_selection_btn.clicked.connect(self.clear_subject_selection)
        
        subject_button_layout.addWidget(self.list_subjects_btn)
        subject_button_layout.addWidget(self.select_all_subjects_btn)
        subject_button_layout.addWidget(self.clear_subject_selection_btn)
        subject_button_layout.addStretch()  # Push buttons to the top
        
        subject_content_layout.addLayout(subject_button_layout)
        subject_layout.addLayout(subject_content_layout)
        
        # Add subject container to left layout
        left_layout.addWidget(subject_container)
        
        # Montage selection - now placed below subjects on left side
        montage_container = QtWidgets.QGroupBox("Montage(s)")
        montage_container.setMinimumHeight(202)  # Reduced by 10% (224 * 0.9 = 202)
        montage_container.setMaximumHeight(202)  # Set maximum height for consistency
        montage_container.setMinimumWidth(450)   # Reduced by 10% (500 * 0.9 = 450)
        montage_container.setMaximumWidth(450)   # Set maximum width for consistency
        montage_layout = QtWidgets.QVBoxLayout(montage_container)
        
        # Create horizontal layout for list and buttons side by side
        montage_content_layout = QtWidgets.QHBoxLayout()
        
        # List widget for montage selection
        self.montage_list = QtWidgets.QListWidget()
        self.montage_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        # No height constraints - let it fill the available vertical space
        montage_content_layout.addWidget(self.montage_list)
        
        # Montage control buttons in vertical layout on the right
        montage_button_layout = QtWidgets.QVBoxLayout()
        # Add New Montage button
        self.add_new_montage_btn = QtWidgets.QPushButton("Add New")
        self.add_new_montage_btn.clicked.connect(self.show_add_montage_dialog)
        # Remove Montage button
        self.remove_montage_btn = QtWidgets.QPushButton("Remove")
        self.remove_montage_btn.clicked.connect(self.remove_selected_montage)
        # Other montage buttons
        self.list_montages_btn = QtWidgets.QPushButton("Refresh List")
        self.list_montages_btn.clicked.connect(self.update_montage_list)
        self.clear_montage_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_montage_selection_btn.clicked.connect(self.clear_montage_selection)
        
        montage_button_layout.addWidget(self.add_new_montage_btn)
        montage_button_layout.addWidget(self.remove_montage_btn)
        montage_button_layout.addWidget(self.list_montages_btn)
        montage_button_layout.addWidget(self.clear_montage_selection_btn)
        montage_button_layout.addStretch()  # Push buttons to the top
        
        montage_content_layout.addLayout(montage_button_layout)
        montage_layout.addLayout(montage_content_layout)
        
        # Add montage container to left layout
        self.montage_container = montage_container  # Store reference for visibility control
        left_layout.addWidget(montage_container)
        
        # Flex-search outputs selection
        flex_search_container = QtWidgets.QGroupBox("Flex-Search Outputs")
        flex_search_container.setMinimumHeight(202)  # Reduced by 10% (224 * 0.9 = 202)
        flex_search_container.setMaximumHeight(202)  # Set maximum height for consistency
        flex_search_container.setMinimumWidth(450)   # Reduced by 10% (500 * 0.9 = 450)
        flex_search_container.setMaximumWidth(450)   # Set maximum width for consistency
        flex_search_layout = QtWidgets.QVBoxLayout(flex_search_container)
        
        # Create horizontal layout for list and buttons side by side
        flex_content_layout = QtWidgets.QHBoxLayout()
        
        # Create vertical layout for list and options on the left
        flex_list_and_options = QtWidgets.QVBoxLayout()
        
        # List widget for flex-search output selection
        self.flex_search_list = QtWidgets.QListWidget()
        self.flex_search_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        # No height constraints - let it fill the available vertical space
        flex_list_and_options.addWidget(self.flex_search_list)
        
        # Flex-search options
        flex_options_layout = QtWidgets.QVBoxLayout()

        # Electrode type checkboxes
        electrode_type_layout = QtWidgets.QHBoxLayout()
        self.flex_use_mapped = QtWidgets.QCheckBox("Use Mapped")
        self.flex_use_optimized = QtWidgets.QCheckBox("Use Optimized")
        self.flex_use_mapped.setChecked(True)  # Default to mapped

        # Connect to update EEG net visibility
        self.flex_use_mapped.stateChanged.connect(self.on_flex_mapped_changed)

        electrode_type_layout.addWidget(QtWidgets.QLabel("Type:"))
        electrode_type_layout.addWidget(self.flex_use_mapped)
        electrode_type_layout.addWidget(self.flex_use_optimized)
        electrode_type_layout.addStretch()
        flex_options_layout.addLayout(electrode_type_layout)

        # EEG net selection for flex-mapped mode
        flex_eeg_net_layout = QtWidgets.QHBoxLayout()
        self.flex_eeg_net_label = QtWidgets.QLabel("EEG Net:")
        self.flex_eeg_net_combo = QtWidgets.QComboBox()
        self.flex_eeg_net_combo.setMinimumWidth(200)
        flex_eeg_net_layout.addWidget(self.flex_eeg_net_label)
        flex_eeg_net_layout.addWidget(self.flex_eeg_net_combo)
        flex_eeg_net_layout.addStretch()
        flex_options_layout.addLayout(flex_eeg_net_layout)

        flex_list_and_options.addLayout(flex_options_layout)
        
        flex_content_layout.addLayout(flex_list_and_options)
        
        # Flex-search control buttons in vertical layout on the right
        flex_button_layout = QtWidgets.QVBoxLayout()
        self.refresh_flex_btn = QtWidgets.QPushButton("Refresh List")
        self.refresh_flex_btn.clicked.connect(self.refresh_flex_search_list)
        self.clear_flex_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_flex_selection_btn.clicked.connect(self.clear_flex_search_selection)
        
        flex_button_layout.addWidget(self.refresh_flex_btn)
        flex_button_layout.addWidget(self.clear_flex_selection_btn)
        flex_button_layout.addStretch()  # Push buttons to the top
        
        flex_content_layout.addLayout(flex_button_layout)
        flex_search_layout.addLayout(flex_content_layout)
        
        # Add flex-search container to left layout
        left_layout.addWidget(flex_search_container)
        
        # Store containers for show/hide functionality
        self.montage_container = montage_container
        self.flex_search_container = flex_search_container
        
        # Right side layout for simulation parameters
        right_layout = QtWidgets.QVBoxLayout()
        
        # Simulation parameters group
        sim_params_container = QtWidgets.QGroupBox("Simulation Configuration")
        sim_params_layout = QtWidgets.QVBoxLayout(sim_params_container)
        
        # Simulation type (Isotropic/Anisotropic)
        sim_type_layout = QtWidgets.QHBoxLayout()
        self.sim_type_label = QtWidgets.QLabel("Anisotropy:")
        self.sim_type_combo = QtWidgets.QComboBox()
        self.sim_type_combo.addItem("Isotropic", "scalar")
        self.sim_type_combo.addItem("Anisotropic (vn)", "vn")
        self.sim_type_combo.addItem("Anisotropic (dir)", "dir")
        self.sim_type_combo.addItem("Anisotropic (mc)", "mc")
        
        # Add help button
        self.sim_type_help_btn = QtWidgets.QPushButton("?")
        self.sim_type_help_btn.setFixedWidth(20)
        self.sim_type_help_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        self.sim_type_help_btn.clicked.connect(self.show_sim_type_help)
        
        sim_type_layout.addWidget(self.sim_type_label)
        sim_type_layout.addWidget(self.sim_type_combo)
        sim_type_layout.addWidget(self.sim_type_help_btn)
        
        # Add conductivity editor button on the same line
        self.conductivity_editor_btn = QtWidgets.QPushButton("Change Default Cond.")
        self.conductivity_editor_btn.clicked.connect(self.show_conductivity_editor)
        sim_type_layout.addWidget(self.conductivity_editor_btn)
        sim_type_layout.addStretch()  # Push everything to the left
        
        sim_params_layout.addLayout(sim_type_layout)
        
        # EEG Net selection - aligned with Brain Anisotropy dropdown
        eeg_net_layout = QtWidgets.QHBoxLayout()
        self.eeg_net_label = QtWidgets.QLabel("EEG Net:")
        # Set minimum width to match "Brain Anisotropy:" label
        self.eeg_net_label.setMinimumWidth(self.sim_type_label.sizeHint().width())
        self.eeg_net_combo = QtWidgets.QComboBox()
        eeg_net_layout.addWidget(self.eeg_net_label)
        eeg_net_layout.addWidget(self.eeg_net_combo)
        eeg_net_layout.addStretch()
        sim_params_layout.addLayout(eeg_net_layout)

        # Connect EEG net selection change to montage list update
        self.eeg_net_combo.currentTextChanged.connect(self.update_montage_list)

        # Simulation Type Selection (Montage vs Flex vs Free-hand)
        sim_type_selection_layout = QtWidgets.QHBoxLayout()
        self.sim_type_selection_label = QtWidgets.QLabel("Montage Source:")
        self.sim_type_montage = QtWidgets.QRadioButton("Montage List")
        self.sim_type_flex = QtWidgets.QRadioButton("Flex-Search")
        self.sim_type_freehand = QtWidgets.QRadioButton("Free-hand")
        self.sim_type_montage.setChecked(True)  # Default to montage simulation
        
        # Create button group for mutual exclusion
        self.sim_type_group = QtWidgets.QButtonGroup()
        self.sim_type_group.addButton(self.sim_type_montage, 1)
        self.sim_type_group.addButton(self.sim_type_flex, 2)
        self.sim_type_group.addButton(self.sim_type_freehand, 3)
        
        # Add help button for montage source
        self.montage_source_help_btn = QtWidgets.QPushButton("?")
        self.montage_source_help_btn.setFixedWidth(20)
        self.montage_source_help_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        self.montage_source_help_btn.clicked.connect(self.show_montage_source_help)
        
        sim_type_selection_layout.addWidget(self.sim_type_selection_label)
        sim_type_selection_layout.addWidget(self.sim_type_montage)
        sim_type_selection_layout.addWidget(self.sim_type_flex)
        sim_type_selection_layout.addWidget(self.sim_type_freehand)
        sim_type_selection_layout.addWidget(self.montage_source_help_btn)
        sim_type_selection_layout.addStretch()
        sim_params_layout.addLayout(sim_type_selection_layout)
        
        # Connect to mode change handler - use clicked to avoid double signals
        self.sim_type_montage.clicked.connect(self.on_simulation_type_changed)
        self.sim_type_flex.clicked.connect(self.on_simulation_type_changed)
        self.sim_type_freehand.clicked.connect(self.on_simulation_type_changed)

        # Simulation mode (Unipolar/Multipolar) - only for montage simulation
        sim_mode_layout = QtWidgets.QHBoxLayout()
        self.sim_mode_label = QtWidgets.QLabel("Simulation Mode:")
        # Set minimum width to match "Montage Source:" label
        self.sim_mode_label.setMinimumWidth(self.sim_type_selection_label.sizeHint().width())
        self.sim_mode_unipolar = QtWidgets.QRadioButton("Unipolar")
        self.sim_mode_multipolar = QtWidgets.QRadioButton("Multipolar")
        self.sim_mode_unipolar.setChecked(True)
        sim_mode_layout.addWidget(self.sim_mode_label)
        sim_mode_layout.addWidget(self.sim_mode_unipolar)
        sim_mode_layout.addWidget(self.sim_mode_multipolar)
        sim_mode_layout.addStretch()
        # Connect mode radio buttons to update montage list and current inputs
        self.sim_mode_unipolar.toggled.connect(self.update_montage_list)
        self.sim_mode_multipolar.toggled.connect(self.update_montage_list)
        self.sim_mode_unipolar.toggled.connect(self.update_current_inputs_visibility)
        self.sim_mode_multipolar.toggled.connect(self.update_current_inputs_visibility)
        sim_params_layout.addLayout(sim_mode_layout)
        
        # Store the sim_mode_layout for show/hide
        self.sim_mode_layout_widgets = [self.sim_mode_label, self.sim_mode_unipolar, self.sim_mode_multipolar]
        
        # Electrode parameters group
        self.electrode_params_group = QtWidgets.QGroupBox("Electrode Parameters")
        electrode_params_layout = QtWidgets.QVBoxLayout(self.electrode_params_group)
        
        # Current value (four fields for multipolar support)
        self.current_layout = QtWidgets.QVBoxLayout()
        
        # First row: Channel 1 and 2
        current_row1 = QtWidgets.QHBoxLayout()
        self.current_label_1 = QtWidgets.QLabel("Current Ch1 (mA):")
        self.current_input_1 = QtWidgets.QLineEdit()
        self.current_input_1.setPlaceholderText("1.0")
        self.current_input_1.setText("1.0")  # Default to 1.0 mA
        self.current_label_2 = QtWidgets.QLabel("Current Ch2 (mA):")
        self.current_input_2 = QtWidgets.QLineEdit()
        self.current_input_2.setPlaceholderText("1.0")
        self.current_input_2.setText("1.0")  # Default to 1.0 mA
        current_row1.addWidget(self.current_label_1)
        current_row1.addWidget(self.current_input_1)
        current_row1.addSpacing(10)
        current_row1.addWidget(self.current_label_2)
        current_row1.addWidget(self.current_input_2)
        self.current_layout.addLayout(current_row1)
        
        # Second row: Channel 3 and 4 (for multipolar mode)
        current_row2 = QtWidgets.QHBoxLayout()
        self.current_label_3 = QtWidgets.QLabel("Current Ch3 (mA):")
        self.current_input_3 = QtWidgets.QLineEdit()
        self.current_input_3.setPlaceholderText("1.0")
        self.current_input_3.setText("1.0")  # Default to 1.0 mA
        self.current_label_4 = QtWidgets.QLabel("Current Ch4 (mA):")
        self.current_input_4 = QtWidgets.QLineEdit()
        self.current_input_4.setPlaceholderText("1.0")
        self.current_input_4.setText("1.0")  # Default to 1.0 mA
        current_row2.addWidget(self.current_label_3)
        current_row2.addWidget(self.current_input_3)
        current_row2.addSpacing(10)
        current_row2.addWidget(self.current_label_4)
        current_row2.addWidget(self.current_input_4)
        self.current_layout.addLayout(current_row2)
        
        # Store widgets for show/hide functionality
        self.multipolar_current_widgets = [self.current_label_3, self.current_input_3, self.current_label_4, self.current_input_4]
        
        # Initially hide channels 3 and 4
        for widget in self.multipolar_current_widgets:
            widget.setVisible(False)
        electrode_params_layout.addLayout(self.current_layout)
        
        # Initialize current inputs visibility (after widgets are created)
        self.update_current_inputs_visibility()
        
        # Electrode shape
        shape_layout = QtWidgets.QHBoxLayout()
        self.electrode_shape_label = QtWidgets.QLabel("Electrode Shape:")
        self.electrode_shape_rect = QtWidgets.QRadioButton("Rectangle")
        self.electrode_shape_rect.setProperty("value", "rect")
        self.electrode_shape_ellipse = QtWidgets.QRadioButton("Ellipse")
        self.electrode_shape_ellipse.setProperty("value", "ellipse")
        self.electrode_shape_ellipse.setChecked(True)  # Set default to Ellipse
        shape_layout.addWidget(self.electrode_shape_label)
        shape_layout.addWidget(self.electrode_shape_rect)
        shape_layout.addWidget(self.electrode_shape_ellipse)
        electrode_params_layout.addLayout(shape_layout)
        
        # Electrode dimensions
        dimensions_layout = QtWidgets.QHBoxLayout()
        self.dimensions_label = QtWidgets.QLabel("Dimensions (mm, x,y):")
        self.dimensions_input = QtWidgets.QLineEdit()
        self.dimensions_input.setPlaceholderText("8,8")
        self.dimensions_input.setText("8,8")  # Set default to 8,8
        dimensions_layout.addWidget(self.dimensions_label)
        dimensions_layout.addWidget(self.dimensions_input)
        electrode_params_layout.addLayout(dimensions_layout)
        
        # Electrode thickness
        thickness_layout = QtWidgets.QHBoxLayout()
        self.thickness_label = QtWidgets.QLabel("Thickness (mm):")
        self.thickness_input = QtWidgets.QLineEdit()
        self.thickness_input.setPlaceholderText("4")
        self.thickness_input.setText("4")  # Set default to 4mm
        thickness_layout.addWidget(self.thickness_label)
        thickness_layout.addWidget(self.thickness_input)
        electrode_params_layout.addLayout(thickness_layout)
        
        # Add electrode params group to simulation params
        sim_params_layout.addWidget(self.electrode_params_group)
        
        # Add simulation parameters to right layout
        right_layout.addWidget(sim_params_container)
        
        # Add left and right layouts to main horizontal layout
        main_horizontal_layout.addLayout(left_layout, 1)  # 1:2 ratio
        main_horizontal_layout.addLayout(right_layout, 2)
        
        # Add main horizontal layout to scroll layout
        scroll_layout.addLayout(main_horizontal_layout)
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(self, run_text="Run Simulation", stop_text="Stop Simulation")
        self.action_buttons.connect_run(self.run_simulation)
        self.action_buttons.connect_stop(self.stop_simulation)
        
        # Keep references for backward compatibility
        self.run_btn = self.action_buttons.get_run_button()
        self.stop_btn = self.action_buttons.get_stop_button()
        
        # Console widget component with Run/Stop buttons integrated
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            show_debug_checkbox=True,
            console_label="Output:",
            min_height=180,
            max_height=None,
            custom_buttons=[self.run_btn, self.stop_btn]
        )
        main_layout.addWidget(self.console_widget)
        
        # Connect the debug checkbox to set_debug_mode method
        self.console_widget.debug_checkbox.toggled.connect(self.set_debug_mode)
        
        # Reference to underlying console for backward compatibility
        self.output_console = self.console_widget.get_console_widget()
        
        # We'll keep the old montage group but hide it since we're moving this functionality
        # to a dialog. It will be referenced by the dialog.
        self.montage_group = QtWidgets.QGroupBox("Add New Montage")
        self.montage_group.setVisible(False)
        self.montage_content = QtWidgets.QWidget()
        
        # Create the electrode stacked widget for reference in the dialog
        self.electrode_stacked_widget = QtWidgets.QStackedWidget()
        
        # Unipolar electrode pairs (two pairs)
        self.uni_electrode_widget = QtWidgets.QWidget()
        uni_electrode_layout = QtWidgets.QVBoxLayout(self.uni_electrode_widget)
        
        # Pair 1
        uni_pair1_layout = QtWidgets.QHBoxLayout()
        self.uni_pair1_label = QtWidgets.QLabel("Pair 1:")
        self.uni_pair1_e1 = QtWidgets.QLineEdit()
        self.uni_pair1_e1.setPlaceholderText("E10")
        self.uni_pair1_e2 = QtWidgets.QLineEdit()
        self.uni_pair1_e2.setPlaceholderText("E11")
        uni_pair1_layout.addWidget(self.uni_pair1_label)
        uni_pair1_layout.addWidget(self.uni_pair1_e1)
        uni_pair1_layout.addWidget(QtWidgets.QLabel("→"))
        uni_pair1_layout.addWidget(self.uni_pair1_e2)
        uni_electrode_layout.addLayout(uni_pair1_layout)
        
        # Pair 2
        uni_pair2_layout = QtWidgets.QHBoxLayout()
        self.uni_pair2_label = QtWidgets.QLabel("Pair 2:")
        self.uni_pair2_e1 = QtWidgets.QLineEdit()
        self.uni_pair2_e1.setPlaceholderText("E12")
        self.uni_pair2_e2 = QtWidgets.QLineEdit()
        self.uni_pair2_e2.setPlaceholderText("E13")
        uni_pair2_layout.addWidget(self.uni_pair2_label)
        uni_pair2_layout.addWidget(self.uni_pair2_e1)
        uni_pair2_layout.addWidget(QtWidgets.QLabel("→"))
        uni_pair2_layout.addWidget(self.uni_pair2_e2)
        uni_electrode_layout.addLayout(uni_pair2_layout)
        
        # Multipolar electrode pairs (four pairs)
        self.multi_electrode_widget = QtWidgets.QWidget()
        multi_electrode_layout = QtWidgets.QVBoxLayout(self.multi_electrode_widget)
        
        # Pair 1-4 for multipolar
        for i in range(1, 5):
            pair_layout = QtWidgets.QHBoxLayout()
            pair_label = QtWidgets.QLabel(f"Pair {i}:")
            
            # Create electrode inputs and save references
            e1 = QtWidgets.QLineEdit()
            e1.setPlaceholderText(f"E{10+2*(i-1)}")
            e2 = QtWidgets.QLineEdit()
            e2.setPlaceholderText(f"E{11+2*(i-1)}")
            
            # Store references for later access
            setattr(self, f"multi_pair{i}_e1", e1)
            setattr(self, f"multi_pair{i}_e2", e2)
            
            pair_layout.addWidget(pair_label)
            pair_layout.addWidget(e1)
            pair_layout.addWidget(QtWidgets.QLabel("→"))
            pair_layout.addWidget(e2)
            multi_electrode_layout.addLayout(pair_layout)
        
        # Add the widgets to the stacked widget
        self.electrode_stacked_widget.addWidget(self.uni_electrode_widget)
        self.electrode_stacked_widget.addWidget(self.multi_electrode_widget)
    
    def list_subjects(self):
        """List available subjects in the project directory."""
        try:
            # Clear existing items
            self.subject_list.clear()
            self.eeg_net_combo.clear()
            
            # Get subjects using path manager (already sorted naturally)
            subjects = self.pm.list_subjects()
            
            # Add subjects to list widget
            for subject_id in subjects:
                self.subject_list.addItem(subject_id)
                
                # Check for EEG nets in eeg_positions directory
                eeg_caps = self.pm.list_eeg_caps(subject_id)
                for net_file in eeg_caps:
                    if net_file not in [self.eeg_net_combo.itemText(i) for i in range(self.eeg_net_combo.count())]:
                        self.eeg_net_combo.addItem(net_file)
            
            # If no nets found, add default
            if self.eeg_net_combo.count() == 0:
                self.eeg_net_combo.addItem("EGI_template.csv")
            
        except Exception as e:
            print(f"Error listing subjects: {str(e)}")
    
    def select_all_subjects(self):
        """Select all subjects in the subject list."""
        self.subject_list.selectAll()
    
    def clear_subject_selection(self):
        """Clear the selection in the subject list."""
        self.subject_list.clearSelection()
    
    def clear_montage_selection(self):
        """Clear the selection in the montage list."""
        self.montage_list.clearSelection()
    
    def update_freehand_configs(self):
        """Update the list of available free-hand electrode configurations."""
        try:
            # Only populate when Free-hand mode is selected
            if not self.sim_type_freehand.isChecked():
                return
            # Clear existing items first
            self.montage_list.clear()
            
            # Require exactly one subject to view subject-specific free-hand configs
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            if len(selected_subjects) != 1:
                placeholder = QtWidgets.QListWidgetItem("Select exactly one subject to view free-hand configurations")
                placeholder.setFlags(placeholder.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.montage_list.addItem(placeholder)
                return
            current_subject = selected_subjects[0]
            
            # Get stim_configs directory
            m2m_dir = self.pm.get_m2m_dir(current_subject)
            if not m2m_dir:
                placeholder = QtWidgets.QListWidgetItem("No subject m2m directory found")
                placeholder.setFlags(placeholder.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.montage_list.addItem(placeholder)
                return
            
            stim_configs_dir = os.path.join(m2m_dir, "stim_configs")
            if not os.path.exists(stim_configs_dir):
                placeholder = QtWidgets.QListWidgetItem("No free-hand configurations found")
                placeholder.setFlags(placeholder.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.montage_list.addItem(placeholder)
                return
            
            config_files = [f for f in os.listdir(stim_configs_dir) if f.endswith('.json')]
            if not config_files:
                placeholder = QtWidgets.QListWidgetItem("No free-hand configurations found")
                placeholder.setFlags(placeholder.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.montage_list.addItem(placeholder)
                return
            
            # Populate list with configs
            for config_file in sorted(config_files):
                config_path = os.path.join(stim_configs_dir, config_file)
                try:
                    with open(config_path, 'r') as f:
                        config_data = json.load(f)
                    name = config_data.get('name', config_file.replace('.json', ''))
                    stim_type = config_data.get('type', 'U')
                    electrode_positions = config_data.get('electrode_positions', {})
                    type_label = "Unipolar" if stim_type == 'U' else "Multipolar"
                    label_html = f"<b>{name}</b> ({type_label}, {len(electrode_positions)} electrodes)"
                    
                    item = QtWidgets.QListWidgetItem()
                    item.setData(QtCore.Qt.UserRole, name)
                    payload = dict(config_data)
                    payload['subject_id'] = current_subject
                    item.setData(QtCore.Qt.UserRole + 1, payload)
                    self.montage_list.addItem(item)
                    
                    label_widget = QtWidgets.QLabel()
                    label_widget.setTextFormat(QtCore.Qt.RichText)
                    label_widget.setText(label_html)
                    label_widget.setStyleSheet("QLabel { padding: 2px 4px; font-size: 13px; }")
                    self.montage_list.setItemWidget(item, label_widget)
                    item.setSizeHint(label_widget.sizeHint())
                except Exception as e:
                    print(f"Error loading config {config_file}: {e}")
                    continue
        except Exception as e:
            self.update_output(f"Error loading free-hand configs: {e}", 'error')
    
    def refresh_flex_search_list(self):
        """Refresh the list of available flex-search outputs based on selected subjects."""
        try:
            self.flex_search_list.clear()
            
            # Get selected subjects to filter flex-search outputs
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            
            # Only show flex-search outputs if subjects are selected (similar to montage behavior)
            if not selected_subjects:
                return
            
            # Get simnibs directory using path manager
            simnibs_dir = self.pm.get_simnibs_dir()
            
            if os.path.exists(simnibs_dir):
                # Iterate through selected subject directories only
                for subject_id in selected_subjects:
                    subject_dir = f"sub-{subject_id}"
                    subject_path = os.path.join(simnibs_dir, subject_dir)
                    
                    if os.path.exists(subject_path):
                        flex_search_dir = os.path.join(subject_path, const.DIR_FLEX_SEARCH)

                        if os.path.exists(flex_search_dir):
                            # Look for search directories
                            for search_name in os.listdir(flex_search_dir):
                                search_dir = os.path.join(flex_search_dir, search_name)
                                positions_file = os.path.join(search_dir, 'electrode_positions.json')

                                if os.path.isdir(search_dir) and os.path.exists(positions_file):
                                    # Read the positions file to get details
                                    try:
                                        with open(positions_file, 'r') as f:
                                            positions_data = json.load(f)

                                        # Create display label (no EEG net shown until mapped)
                                        label = f"{subject_id} | {search_name}"

                                        # Add item to list
                                        item = QtWidgets.QListWidgetItem(label)
                                        item.setData(QtCore.Qt.UserRole, {
                                            'subject_id': subject_id,
                                            'search_name': search_name,
                                            'positions_file': positions_file,
                                            'positions_data': positions_data
                                        })
                                        self.flex_search_list.addItem(item)

                                    except Exception as e:
                                        print(f"Error reading flex-search positions file {positions_file}: {e}")
                                        
        except Exception as e:
            print(f"Error refreshing flex-search list: {str(e)}")
    
    def clear_flex_search_selection(self):
        """Clear all flex-search selections."""
        self.flex_search_list.clearSelection()

    def populate_flex_eeg_nets(self):
        """Populate the flex EEG net dropdown with available EEG nets from selected subjects."""
        try:
            self.flex_eeg_net_combo.clear()

            # Get selected subjects
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]

            if not selected_subjects:
                return

            # Collect unique EEG nets from all selected subjects
            unique_nets = set()
            for subject_id in selected_subjects:
                eeg_caps = self.pm.list_eeg_caps(subject_id)
                for net_file in eeg_caps:
                    unique_nets.add(net_file)

            # Add sorted nets to combo box
            for net in sorted(unique_nets):
                self.flex_eeg_net_combo.addItem(net)

            # If no nets found, add default
            if self.flex_eeg_net_combo.count() == 0:
                self.flex_eeg_net_combo.addItem("EGI_template.csv")

        except Exception as e:
            print(f"Error populating flex EEG nets: {str(e)}")

    def on_flex_mapped_changed(self):
        """Handle changes to the 'Use Mapped' checkbox."""
        # Show/hide EEG net selection based on checkbox state
        is_mapped = self.flex_use_mapped.isChecked()
        self.flex_eeg_net_label.setVisible(is_mapped)
        self.flex_eeg_net_combo.setVisible(is_mapped)

        # Populate EEG nets when checkbox is enabled
        if is_mapped:
            self.populate_flex_eeg_nets()

    def on_simulation_type_changed(self):
        """Handle changes between Montage, Flex, and Free-hand simulation modes."""
        is_montage_mode = self.sim_type_montage.isChecked()
        is_flex_mode = self.sim_type_flex.isChecked()
        is_freehand_mode = self.sim_type_freehand.isChecked()
        
        # Show/hide montage-related UI elements
        self.montage_container.setVisible(is_montage_mode or is_freehand_mode)
        
        # Enable/disable (grey out) simulation mode and EEG net controls
        for widget in self.sim_mode_layout_widgets:
            widget.setEnabled(is_montage_mode)
        self.eeg_net_combo.setEnabled(is_montage_mode)
        self.eeg_net_label.setEnabled(is_montage_mode)
        
        # Show/hide flex-search-related UI elements
        self.flex_search_container.setVisible(is_flex_mode)
        
        # Update window title or status and refresh lists
        if is_montage_mode:
            self.update_output("Switched to Montage Simulation mode", 'info')
            self.update_montage_list()  # Refresh montage list
        elif is_flex_mode:
            self.update_output("Switched to Flex-Search Simulation mode", 'info')
            self.refresh_flex_search_list()  # Refresh flex-search list
            self.populate_flex_eeg_nets()  # Populate EEG nets for flex-mapped mode
        elif is_freehand_mode:
            self.update_output("Switched to Free-hand Simulation mode", 'info')
            self.update_freehand_configs()  # Refresh free-hand configs

    def initialize_ui_state(self):
        """Initialize UI state without printing messages."""
        is_montage_mode = self.sim_type_montage.isChecked()

        # Show/hide montage-related UI elements
        self.montage_container.setVisible(is_montage_mode)

        # Enable/disable (grey out) simulation mode and EEG net controls instead of hiding
        for widget in self.sim_mode_layout_widgets:
            widget.setEnabled(is_montage_mode)
        self.eeg_net_combo.setEnabled(is_montage_mode)
        self.eeg_net_label.setEnabled(is_montage_mode)

        # Show/hide flex-search-related UI elements
        self.flex_search_container.setVisible(not is_montage_mode)

        # Initialize flex EEG net dropdown visibility based on checkbox state
        is_mapped = self.flex_use_mapped.isChecked()
        self.flex_eeg_net_label.setVisible(is_mapped)
        self.flex_eeg_net_combo.setVisible(is_mapped)

    def ensure_montage_file_exists(self, project_dir):
        """Ensure the montage file exists with proper structure."""
        ti_csc_dir = os.path.join(project_dir, 'code', 'ti-toolbox')
        config_dir = os.path.join(ti_csc_dir, 'config')
        montage_file = os.path.join(config_dir, 'montage_list.json')
        
        # Create directories if they don't exist
        os.makedirs(config_dir, exist_ok=True)
        
        # Set directory permissions
        os.chmod(ti_csc_dir, 0o777)
        os.chmod(config_dir, 0o777)
        
        # Create montage file if it doesn't exist
        if not os.path.exists(montage_file):
            initial_content = {
                "nets": {
                    "EGI_template.csv": {
                        "uni_polar_montages": {},
                        "multi_polar_montages": {}
                    }
                }
            }
            with open(montage_file, 'w') as f:
                json.dump(initial_content, f, indent=4)
            os.chmod(montage_file, 0o777)
        else:
            # Ensure correct permissions
            os.chmod(montage_file, 0o777)
        
        return montage_file

    def update_montage_list(self, checked=None):
        """Update the list of available montages."""
        try:
            # Get project directory using path manager
            project_dir = self.pm.get_project_dir()
            if not project_dir:
                return
            # Clear existing items
            self.montage_list.clear()
            # Ensure montage file exists and get its path
            montage_file = self.ensure_montage_file_exists(project_dir)
            # Load montages from montage_list.json
            with open(montage_file, 'r') as f:
                montage_data = json.load(f)
            # Get the current EEG net
            current_net = self.eeg_net_combo.currentText() or "EGI_template.csv"
            # Get montages for the current net
            if "nets" in montage_data and current_net in montage_data["nets"]:
                net_montages = montage_data["nets"][current_net]
                # Add unipolar montages if in unipolar mode
                if self.sim_mode_unipolar.isChecked() and "uni_polar_montages" in net_montages:
                    for montage_name, pairs in net_montages["uni_polar_montages"].items():
                        label_html = self._format_montage_label_html(montage_name, pairs, is_unipolar=True)
                        item = QtWidgets.QListWidgetItem()
                        item.setData(QtCore.Qt.UserRole, montage_name)  # Store the real name for selection logic
                        self.montage_list.addItem(item)
                        label_widget = QtWidgets.QLabel()
                        label_widget.setTextFormat(QtCore.Qt.RichText)
                        label_widget.setText(label_html)
                        label_widget.setStyleSheet("QLabel { padding: 2px 4px; font-size: 13px; }")
                        self.montage_list.setItemWidget(item, label_widget)
                        item.setSizeHint(label_widget.sizeHint())
                # Add multipolar montages if in multipolar mode
                if self.sim_mode_multipolar.isChecked() and "multi_polar_montages" in net_montages:
                    for montage_name, pairs in net_montages["multi_polar_montages"].items():
                        label_html = self._format_montage_label_html(montage_name, pairs, is_unipolar=False)
                        item = QtWidgets.QListWidgetItem()
                        item.setData(QtCore.Qt.UserRole, montage_name)
                        self.montage_list.addItem(item)
                        label_widget = QtWidgets.QLabel()
                        label_widget.setTextFormat(QtCore.Qt.RichText)
                        label_widget.setText(label_html)
                        label_widget.setStyleSheet("QLabel { padding: 2px 4px; font-size: 13px; }")
                        self.montage_list.setItemWidget(item, label_widget)
                        item.setSizeHint(label_widget.sizeHint())
        except Exception as e:
            print(f"Error updating montage list: {str(e)}")
        # Update the electrode inputs view
        if checked is not None:
            if checked:  # Unipolar selected
                self.electrode_stacked_widget.setCurrentIndex(0)
            else:  # Multipolar selected
                self.electrode_stacked_widget.setCurrentIndex(1)
    
    def _format_montage_label_html(self, montage_name, pairs, is_unipolar=True):
        """Format montage label for the list widget using HTML for a professional look."""
        if not pairs or not isinstance(pairs, list):
            return f"<b>{montage_name}</b>"
        channel_labels = []
        for idx, pair in enumerate(pairs):
            if isinstance(pair, list) and len(pair) == 2:
                ch_num = f"ch{idx+1}:"
                e1 = f"<span style='color:#55aaff;'>{pair[0]}</span>"
                e2 = f"<span style='color:#ff5555;'>{pair[1]}</span>"
                channel = f"{ch_num} {e1} <b>↔</b> {e2}"
                channel_labels.append(channel)
        return f"<b>{montage_name}</b>  |  " + "   +   ".join(channel_labels)
    
    def list_montages(self):
        """List available montages from montage_list.json."""
        try:
            # Get project directory using path manager
            project_dir = self.pm.get_project_dir()
            if not project_dir:
                return
            # Ensure and use the new location under code/ti-toolbox/config
            montage_file = self.ensure_montage_file_exists(project_dir)

            self.update_output(f"Looking for montages in: {montage_file}")

            if os.path.exists(montage_file):
                with open(montage_file, 'r') as f:
                    montage_data = json.load(f)

                # Determine current EEG net
                current_net = self.eeg_net_combo.currentText() or "EGI_template.csv"
                # Get montages for the selected mode from the new nested structure
                is_unipolar = self.sim_mode_unipolar.isChecked()
                montage_type = "uni_polar_montages" if is_unipolar else "multi_polar_montages"
                mode_text = "Unipolar" if is_unipolar else "Multipolar"

                self.output_console.append('<div style="background-color: #2a2a2a; border: 1px solid #444; border-radius: 5px; padding: 10px; margin: 10px 0;">')
                self.output_console.append(f'<span style="color: #55ffff; font-weight: bold;">📋 Available {mode_text} Montages:</span>')

                net_montages = {}
                if isinstance(montage_data, dict) and "nets" in montage_data and current_net in montage_data["nets"]:
                    net_montages = montage_data["nets"].get(current_net, {})

                montages = net_montages.get(montage_type, {}) if isinstance(net_montages, dict) else {}

                if isinstance(montages, dict) and montages:
                    # Display montages with formatted electrode pairs
                    self.output_console.append('<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">')
                    self.output_console.append('<tr style="background-color: #333; color: white;">')
                    self.output_console.append('<th style="padding: 5px; text-align: left; border-bottom: 1px solid #555;">Name</th>')
                    self.output_console.append('<th style="padding: 5px; text-align: left; border-bottom: 1px solid #555;">Electrode Pairs</th>')
                    self.output_console.append('</tr>')

                    found_montages = False
                    row_num = 0

                    for name, details in montages.items():
                        row_style = 'background-color: #2d2d2d;' if row_num % 2 == 0 else 'background-color: #333;'
                        row_num += 1
                        found_montages = True

                        if isinstance(details, list) and len(details) >= 1:
                            pairs_str = self._format_electrode_pairs(details)
                            self.output_console.append(f'<tr style="{row_style}">')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{name}</td>')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{pairs_str}</td>')
                            self.output_console.append('</tr>')
                        elif isinstance(details, dict) and 'pair' in details:
                            pair = details.get('pair', '')
                            current = details.get('current', '')
                            self.output_console.append(f'<tr style="{row_style}">')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{name}</td>')
                            self.output_console.append(f'<td style="padding: 5px; border-bottom: 1px solid #444;">{pair}, {current}mA</td>')
                            self.output_console.append('</tr>')

                    self.output_console.append('</table>')

                    if not found_montages:
                        self.output_console.append(f'<div style="color: #ffff55; padding: 10px;">No {mode_text.lower()} montages found.</div>')
                else:
                    self.output_console.append(f'<div style="color: #ffff55; padding: 10px;">No {mode_text.lower()} montages found.</div>')

                self.output_console.append('</div>')
            else:
                self.update_output(f"Montage file not found at {montage_file}")
                self.update_output("Create a new montage using the form below.")
        except Exception as e:
            self.update_output(f"Error listing montages: {str(e)}")
    
    def _format_electrode_pairs(self, pairs):
        """Format electrode pairs for display in a clean way."""
        if not pairs:
            return "No electrode pairs"
        
        formatted_pairs = []
        for pair in pairs:
            if isinstance(pair, list) and len(pair) >= 2:
                formatted_pair = f'<span style="color: #55aaff;">{pair[0]}</span><span style="color: #aaaaaa;">→</span><span style="color: #ff5555;">{pair[1]}</span>'
                formatted_pairs.append(formatted_pair)
        
        return ", ".join(formatted_pairs)
    
    def browse_montage(self):
        """Open file browser to select a montage file."""
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Montage File", "", "JSON Files (*.json);;All Files (*)"
        )
        
        if file_name:
            self.montage_list.addItem(file_name)
            self.output_console.append(f"Selected montage file: {file_name}")
    
    def run_simulation(self):
        """Run the simulation with the selected parameters."""
        
        try:
            # Get selected subjects
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            if not selected_subjects:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one subject.")
                return
            
            # Clean up old directories for flex-search mode
            if not self.sim_type_montage.isChecked():
                for subject_id in selected_subjects:
                    self.cleanup_old_simulation_directories(subject_id)
            
            # Get project directory using path manager
            project_dir = self.pm.get_project_dir()
            
            # Check simulation mode and validate selections
            is_montage_mode = self.sim_type_montage.isChecked()
            is_freehand_mode = self.sim_type_freehand.isChecked()
            
            if is_montage_mode:
                # Montage simulation mode
                selected_montages = [item.data(QtCore.Qt.UserRole) for item in self.montage_list.selectedItems()]
                if not selected_montages:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one montage.")
                    return
                selected_flex_searches = []  # No flex-search in montage mode
                flex_montage_configs = []
                freehand_configs = []
            elif is_freehand_mode:
                # Free-hand simulation mode
                selected_freehand = [item for item in self.montage_list.selectedItems()]
                if not selected_freehand:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one free-hand configuration.")
                    return
                
                # Get the free-hand config data
                freehand_configs = []
                for item in selected_freehand:
                    config_data = item.data(QtCore.Qt.UserRole + 1)
                    if config_data:
                        freehand_configs.append(config_data)
                
                selected_montages = []
                selected_flex_searches = []
                flex_montage_configs = []
            else:
                # Flex-search simulation mode
                selected_flex_searches = [item.data(QtCore.Qt.UserRole) for item in self.flex_search_list.selectedItems()]
                if not selected_flex_searches:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one flex-search output.")
                    return
                selected_montages = []  # No regular montages in flex mode
                
                # Process flex-search outputs into individual montage configurations
                flex_montage_configs = []  # List of individual subject-montage configurations
                
                # Check which electrode types are selected
                use_mapped = self.flex_use_mapped.isChecked()
                use_optimized = self.flex_use_optimized.isChecked()
                
                # Validate that at least one option is selected
                if not use_mapped and not use_optimized:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one electrode type (Mapped or Optimized).")
                    return
                
                for flex_data in selected_flex_searches:
                    subject_id = flex_data['subject_id']
                    search_name = flex_data['search_name']
                    positions_data = flex_data['positions_data']

                    # Create individual montage configurations based on selection
                    if use_mapped:
                        # Get selected EEG net
                        eeg_net = self.flex_eeg_net_combo.currentText()
                        if not eeg_net:
                            self.update_output(f"Error: No EEG net selected for mapping", 'error')
                            continue

                        # Get paths
                        flex_search_dir = self.pm.get_flex_search_dir(subject_id, search_name)
                        positions_file = os.path.join(flex_search_dir, 'electrode_positions.json')
                        m2m_dir = self.pm.get_m2m_dir(subject_id)

                        # Get EEG net CSV path
                        eeg_positions_dir = os.path.join(m2m_dir, const.DIR_EEG_POSITIONS)
                        eeg_net_path = os.path.join(eeg_positions_dir, eeg_net)

                        if not os.path.exists(eeg_net_path):
                            self.update_output(f"Error: EEG net file not found: {eeg_net_path}", 'error')
                            continue

                        # Create temporary mapping file path
                        mapping_file = os.path.join(flex_search_dir, f'electrode_mapping_{eeg_net.replace(".csv", "")}.json')

                        # Run map_electrodes.py to generate mapping
                        self.update_output(f"Mapping electrodes for {subject_id} | {search_name} to {eeg_net}...", 'info')

                        try:
                            # Get path to map_electrodes.py
                            map_electrodes_path = os.path.join(
                                os.path.dirname(os.path.dirname(__file__)),
                                'tools', 'map_electrodes.py'
                            )

                            # Run map_electrodes.py
                            result = subprocess.run(
                                ['simnibs_python', map_electrodes_path,
                                 '-i', positions_file,
                                 '-n', eeg_net_path,
                                 '-o', mapping_file],
                                capture_output=True,
                                text=True,
                                check=True
                            )

                            self.update_output(f"Electrode mapping completed for {search_name}", 'info')

                        except subprocess.CalledProcessError as e:
                            self.update_output(f"Error running map_electrodes.py: {e.stderr}", 'error')
                            continue
                        except Exception as e:
                            self.update_output(f"Error during electrode mapping: {str(e)}", 'error')
                            continue

                        # Read the generated mapping file
                        if not os.path.exists(mapping_file):
                            self.update_output(f"Error: Mapping file was not created: {mapping_file}", 'error')
                            continue

                        with open(mapping_file, 'r') as f:
                            mapping_data_from_file = json.load(f)

                        if 'mapped_positions' not in mapping_data_from_file or 'mapped_labels' not in mapping_data_from_file:
                            self.update_output(f"Error: Invalid electrode mapping file format: {mapping_file}", 'error')
                            continue

                        mapped_positions = mapping_data_from_file['mapped_positions']
                        mapped_labels = mapping_data_from_file['mapped_labels']

                        # Create individual montage configuration for mapped electrodes
                        if len(mapped_positions) >= 4 and len(mapped_labels) >= 4:  # Need at least 4 electrodes for TI
                            # Parse search_name to extract components for new naming format
                            montage_name = self._parse_flex_search_name(search_name, 'mapped')

                            # Use the first 4 electrode labels for TI simulation
                            electrodes_for_ti = mapped_labels[:4]

                            # Validate montage name doesn't conflict with existing directories
                            if montage_name.startswith('flex_'):
                                # Create individual configuration for this subject-montage combination
                                config = {
                                    'subject_id': subject_id,
                                    'eeg_net': eeg_net,
                                    'montage': {
                                        'name': montage_name,
                                        'type': 'flex_mapped',
                                        'search_name': search_name,
                                        'eeg_net': eeg_net,
                                        'electrode_labels': electrodes_for_ti,
                                        'pairs': [[electrodes_for_ti[0], electrodes_for_ti[1]], [electrodes_for_ti[2], electrodes_for_ti[3]]]
                                    }
                                }
                                flex_montage_configs.append(config)
                                # Configuration created (verbose output reduced)
                            else:
                                self.update_output(f"Warning: Generated invalid montage name '{montage_name}' for search '{search_name}'", 'warning')
                        else:
                            self.update_output(f"Error: Not enough electrodes for TI simulation in {search_name} (need at least 4)", 'error')
                    
                    if use_optimized:
                        optimized_positions = positions_data['optimized_positions']

                        # Create individual montage configuration for optimized electrodes
                        if len(optimized_positions) >= 4:  # Need at least 4 electrodes for TI
                            # Parse search_name to extract components for new naming format
                            montage_name = self._parse_flex_search_name(search_name, 'optimized')

                            # Use the first 4 electrode positions for TI simulation
                            positions_for_ti = optimized_positions[:4]

                            # Validate montage name doesn't conflict with existing directories
                            if montage_name.startswith('flex_'):
                                # Create individual configuration for this subject-montage combination
                                config = {
                                    'subject_id': subject_id,
                                    'eeg_net': 'optimized_coords',  # No specific EEG net needed for optimized coordinates
                                    'montage': {
                                        'name': montage_name,
                                        'type': 'flex_optimized',
                                        'search_name': search_name,
                                        'electrode_positions': positions_for_ti,
                                        'pairs': [[positions_for_ti[0], positions_for_ti[1]],
                                                 [positions_for_ti[2], positions_for_ti[3]]]
                                    }
                                }
                                flex_montage_configs.append(config)
                                # Optimized configuration created (verbose output reduced)
                            else:
                                self.update_output(f"Warning: Generated invalid montage name '{montage_name}' for search '{search_name}'", 'warning')
                        else:
                            self.update_output(f"Error: Not enough electrodes for TI simulation in {search_name} (need at least 4)", 'error')
            
            # Skip directory existence check for now - let the simulation scripts handle it
            
            # Get simulation parameters
            conductivity = self.sim_type_combo.currentData()  # Get conductivity from combo box
            
            # Determine sim mode (U/M) for all frameworks; pipeline selection is handled elsewhere
            sim_mode = "U" if self.sim_mode_unipolar.isChecked() else "M"
            if is_montage_mode:
                eeg_net = self.eeg_net_combo.currentText()
            elif is_freehand_mode:
                eeg_net = "freehand"
            else:
                eeg_net = "flex_mode"
            
            # Get current values and convert to Amperes (from mA)
            try:
                current_ma_1 = float(self.current_input_1.text() or "1.0")
                current_ma_2 = float(self.current_input_2.text() or "1.0")
                
                # For multipolar mode, also get channels 3 and 4
                if self.sim_mode_multipolar.isChecked():
                    current_ma_3 = float(self.current_input_3.text() or "1.0")
                    current_ma_4 = float(self.current_input_4.text() or "1.0")
                    if current_ma_1 <= 0 or current_ma_2 <= 0 or current_ma_3 <= 0 or current_ma_4 <= 0:
                        QtWidgets.QMessageBox.warning(self, "Warning", "All current values must be greater than 0 mA.")
                        return
                    current = f"{current_ma_1/1000.0},{current_ma_2/1000.0},{current_ma_3/1000.0},{current_ma_4/1000.0}"
                else:
                    if current_ma_1 <= 0 or current_ma_2 <= 0:
                        QtWidgets.QMessageBox.warning(self, "Warning", "Current values must be greater than 0 mA.")
                        return
                    current = f"{current_ma_1/1000.0},{current_ma_2/1000.0}"
            except ValueError:
                channels_text = "all channels" if self.sim_mode_multipolar.isChecked() else "both channels"
                QtWidgets.QMessageBox.warning(self, "Warning", f"Please enter valid current values in mA for {channels_text}.")
                return
            
            electrode_shape = "rect" if self.electrode_shape_rect.isChecked() else "ellipse"
            dimensions = self.dimensions_input.text() or "8,8"  # Default to 8,8 if empty
            thickness = self.thickness_input.text() or "4"  # Default to 4 if empty
            
            # Validate parameters
            if not all([conductivity, sim_mode, eeg_net]):
                QtWidgets.QMessageBox.warning(self, "Warning", "Please fill in all required simulation parameters.")
                return
            
            # Validate numeric inputs
            try:
                dim_parts = dimensions.split(',')
                if len(dim_parts) != 2 or not all(dim_parts):
                    raise ValueError("Invalid dimensions format")
                float(dim_parts[0])
                float(dim_parts[1])
                float(thickness)
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid numeric values for dimensions and thickness.")
                return
            
            # Show confirmation dialog with details
            if is_montage_mode:
                current_details = f"• Current Channel 1: {current_ma_1} mA\n• Current Channel 2: {current_ma_2} mA\n"
                if self.sim_mode_multipolar.isChecked():
                    current_details += f"• Current Channel 3: {current_ma_3} mA\n• Current Channel 4: {current_ma_4} mA\n"
                
                details = (f"This will run MONTAGE simulations for:\n\n"
                          f"• {len(selected_subjects)} subject(s)\n"
                          f"• {len(selected_montages)} montage(s)\n\n"
                          f"Parameters:\n"
                          f"• Simulation type: {conductivity}\n"
                          f"• Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}\n"
                          f"• EEG Net: {eeg_net}\n"
                          f"{current_details}"
                          f"• Electrode shape: {electrode_shape}\n"
                          f"• Dimensions: {dimensions} mm\n"
                          f"• Thickness: {thickness} mm")
            elif is_freehand_mode:
                details = (f"This will run FREE-HAND simulations for:\n\n"
                          f"• {len(selected_subjects)} subject(s)\n"
                          f"• {len(freehand_configs)} configuration(s)\n\n"
                          f"Parameters:\n"
                          f"• Simulation type: {conductivity}\n"
                          f"• Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}\n"
                          f"• Electrode shape: {electrode_shape}\n"
                          f"• Dimensions: {dimensions} mm\n"
                          f"• Thickness: {thickness} mm")
            else:
                details = (f"This will run FLEX-SEARCH simulations for:\n\n"
                          f"• {len(selected_subjects)} subject(s)\n"
                          f"• {len(flex_montage_configs)} flex-search montage(s)\n")
                
                # Show which electrode types are selected
                if use_mapped and use_optimized:
                    details += "• Using both mapped electrode positions and optimized XYZ coordinates\n"
                elif use_mapped:
                    details += "• Using mapped electrode positions (will use EEG net from optimization)\n"
                elif use_optimized:
                    details += "• Using optimized XYZ coordinates (no EEG net required)\n"
                
                current_details = f"• Current Channel 1: {current_ma_1} mA\n• Current Channel 2: {current_ma_2} mA\n"
                if self.sim_mode_multipolar.isChecked():
                    current_details += f"• Current Channel 3: {current_ma_3} mA\n• Current Channel 4: {current_ma_4} mA\n"
                
                details += (f"\nParameters:\n"
                          f"• Simulation type: {conductivity}\n"
                          f"{current_details}"
                          f"• Electrode shape: {electrode_shape}\n"
                          f"• Dimensions: {dimensions} mm\n"
                          f"• Thickness: {thickness} mm")
            
            if not ConfirmationDialog.confirm(
                self,
                title="Confirm Simulation",
                message="Are you sure you want to start the simulation?",
                details=details
            ):
                return
            
            # Check for existing simulation directories and ask for overwrite confirmation
            existing_dirs = []
            for subject_id in selected_subjects:
                if is_montage_mode:
                    montages_to_check = selected_montages
                elif is_freehand_mode:
                    montages_to_check = [cfg.get('name') for cfg in freehand_configs if cfg]
                else:
                    montages_to_check = [cfg['montage']['name'] for cfg in flex_montage_configs if cfg['subject_id'] == subject_id]
                
                for montage_name in montages_to_check:
                    # Get the subject's Simulations directory
                    subject_dir = self.pm.get_subject_dir(subject_id)
                    if subject_dir:
                        simulations_dir = os.path.join(subject_dir, 'Simulations')
                        montage_dir = os.path.join(simulations_dir, montage_name)
                        if os.path.exists(montage_dir):
                            existing_dirs.append(f"{subject_id}/{montage_name}")
            
            # If any directories exist, ask for confirmation to overwrite
            if existing_dirs:
                existing_list = "\n".join([f"  • {d}" for d in existing_dirs[:10]])  # Show max 10
                if len(existing_dirs) > 10:
                    existing_list += f"\n  ... and {len(existing_dirs) - 10} more"
                
                if not ConfirmationDialog.confirm(
                    self,
                    title="Overwrite Existing Simulations?",
                    message=f"The following simulation directories already exist and will be overwritten:",
                    details=f"{existing_list}\n\nDo you want to continue and overwrite these simulations?"
                ):
                    return
                
                # User confirmed - delete the existing directories to avoid SimNIBS errors
                self.update_output("Removing existing simulation directories...")
                for subject_id in selected_subjects:
                    if is_montage_mode:
                        montages_to_delete = selected_montages
                    elif is_freehand_mode:
                        montages_to_delete = [cfg.get('name') for cfg in freehand_configs if cfg]
                    else:
                        montages_to_delete = [cfg['montage']['name'] for cfg in flex_montage_configs if cfg['subject_id'] == subject_id]
                    
                    for montage_name in montages_to_delete:
                        # Get the subject's Simulations directory
                        subject_dir = self.pm.get_subject_dir(subject_id)
                        if subject_dir:
                            simulations_dir = os.path.join(subject_dir, 'Simulations')
                            montage_dir = os.path.join(simulations_dir, montage_name)
                            if os.path.exists(montage_dir):
                                try:
                                    shutil.rmtree(montage_dir)
                                    self.update_output(f"  Removed: {subject_id}/{montage_name}")
                                except Exception as e:
                                    self.update_output(f"  Warning: Could not remove {subject_id}/{montage_name}: {str(e)}", 'warning')
            
            # Prepare environment variables
            env = os.environ.copy()
            env['DIRECT_MODE'] = 'true'
            env['PROJECT_DIR_NAME'] = os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')
            
            # Build command
            cmd = [
                'bash',
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cli', 'simulator.sh'),
                '--run-direct'
            ]
            
            
            
            # Set environment variables for simulator.sh (match CLI script expectations)
            env['SUBJECT_CHOICES'] = ','.join(selected_subjects)  # CLI expects SUBJECT_CHOICES
            env['SIM_TYPE'] = 'TI'  # CLI expects SIM_TYPE (always TI for this GUI)
            env['CONDUCTIVITY'] = conductivity
            env['SIM_MODE'] = sim_mode
            env['EEG_NET'] = eeg_net
            
            # Pass debug mode setting to control summary output
            env['DEBUG_MODE'] = 'true' if self.debug_mode else 'false'
            
            # For montage mode with multiple subjects, provide EEG_NETS (comma-separated)
            if is_montage_mode:
                # For now, use the same EEG net for all subjects
                # In the future, this could be made more sophisticated to support different nets per subject
                eeg_nets_list = [eeg_net] * len(selected_subjects)
                env['EEG_NETS'] = ','.join(eeg_nets_list)
            env['CURRENT'] = current  # Now in Amperes, comma-separated for two channels
            env['ELECTRODE_SHAPE'] = electrode_shape
            env['DIMENSIONS'] = dimensions
            env['THICKNESS'] = thickness
            
            if is_montage_mode:
                # Montage simulation mode
                env['SELECTED_MONTAGES'] = ','.join(selected_montages)  # Use comma-separated for CLI parsing
                env['SIMULATION_FRAMEWORK'] = 'montage'  # CLI expects SIMULATION_FRAMEWORK
            elif is_freehand_mode:
                # Free-hand simulation mode
                env['SELECTED_MONTAGES'] = ''  # No regular montages
                # Use dedicated free-hand framework
                env['SIMULATION_FRAMEWORK'] = 'freehand'
                
                # Create temporary JSON files for free-hand configs
                import tempfile
                temp_files = []
                freehand_file_list = []  # List of temp file paths in processing order
                
                for config_data in freehand_configs:
                    config_name = config_data.get('name', 'unnamed')
                    stim_type = config_data.get('type', 'U')
                    electrode_positions = config_data.get('electrode_positions', {})
                    
                    # For each subject, create a config
                    for subject_id in selected_subjects:
                        with tempfile.NamedTemporaryFile(mode='w', suffix=f'_{subject_id}_{config_name}.json', delete=False) as tf:
                            # Map dict to list of 4 XYZ coordinates in TI-expected order
                            # Prefer E1+, E1-, E2+, E2-; otherwise take first 4 by sorted name
                            ordered_keys = ['E1+', 'E1-', 'E2+', 'E2-']
                            coords = []
                            try:
                                for k in ordered_keys:
                                    if k in electrode_positions:
                                        coords.append(electrode_positions[k])
                                if len(coords) < 4:
                                    # Fallback to first 4 entries sorted by key
                                    for k in sorted(electrode_positions.keys()):
                                        if k not in ordered_keys and len(coords) < 4:
                                            coords.append(electrode_positions.get(k))
                            except Exception:
                                coords = []
                            
                            if len(coords) < 4:
                                # Not enough electrodes; skip creating this file
                                continue
                            
                            # Create config for free-hand pipeline
                            freehand_config = {
                                'subject_id': subject_id,
                                'montage': {
                                    'name': config_name,
                                    'type': 'freehand_xyz',
                                    'electrode_positions': coords[:4]
                                }
                            }
                            json.dump(freehand_config, tf, indent=2)
                            temp_file_path = tf.name
                            temp_files.append(temp_file_path)
                            freehand_file_list.append({
                                'file_path': temp_file_path,
                                'subject_id': subject_id,
                                'montage_name': config_name,
                                'eeg_net': 'freehand'
                            })
                
                # Store the freehand file list for CLI to use
                env['FREEHAND_MONTAGE_FILES'] = json.dumps(freehand_file_list)
                self.update_output(f"--- Prepared {len(temp_files)} free-hand simulations for processing ---")
                
                # Store temp files for cleanup later
                self.temp_flex_files = temp_files
            else:
                # Flex-search simulation mode
                env['SELECTED_MONTAGES'] = ''  # No regular montages
                env['SIMULATION_FRAMEWORK'] = 'flex'  # CLI expects SIMULATION_FRAMEWORK
                
                # Create separate temporary JSON files for each subject-montage combination
                import tempfile
                temp_files = []
                montage_file_list = []  # List of temp file paths in processing order
                
                for config in flex_montage_configs:
                    subject_id = config['subject_id']
                    montage_name = config['montage']['name']
                    
                    # Create unique temp file for this subject-montage combination
                    with tempfile.NamedTemporaryFile(mode='w', suffix=f'_{subject_id}_{montage_name}.json', delete=False) as tf:
                        json.dump(config, tf, indent=2)
                        temp_file_path = tf.name
                        temp_files.append(temp_file_path)
                        montage_file_list.append({
                            'file_path': temp_file_path,
                            'subject_id': subject_id,
                            'montage_name': montage_name,
                            'eeg_net': config['eeg_net']
                        })
                        # Temp file created (verbose output reduced)
                
                # Store the montage file list for CLI to use (sequential processing)
                env['FLEX_MONTAGE_FILES'] = json.dumps(montage_file_list)
                self.update_output(f"--- Prepared {len(temp_files)} flex simulations for processing ---")
                
                # Store temp files for cleanup later
                self.temp_flex_files = temp_files
            
            # Persist run context for cleanup/termination decisions
            self._current_run_subjects = selected_subjects[:]
            self._current_run_is_montage = is_montage_mode
            if is_montage_mode:
                self._current_run_montages = selected_montages[:]
            elif is_freehand_mode:
                self._current_run_montages = [cfg.get('name') for cfg in freehand_configs if cfg]
            else:
                self._current_run_montages = [cfg['montage']['name'] for cfg in flex_montage_configs]
            self._run_start_time = time.time()
            self._project_dir_path_current = self.pm.get_project_dir()

            # Display simulation configuration
            self.update_output("--- SIMULATION CONFIGURATION ---")
            self.update_output(f"Subjects: {env['SUBJECT_CHOICES']}")
            self.update_output(f"Simulation type: {env['CONDUCTIVITY']}")
            
            if is_montage_mode:
                self.update_output(f"Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}")
                self.update_output(f"EEG Net: {env['EEG_NET']}")
                self.update_output(f"Montages: {', '.join(selected_montages)}")
            elif is_freehand_mode:
                # Free-hand configuration display
                config_names = [config_data.get('name', 'unnamed') for config_data in freehand_configs]
                self.update_output(f"Free-hand configurations: {', '.join(config_names)}")
                for config_data in freehand_configs:
                    config_name = config_data.get('name', 'unnamed')
                    stim_type = config_data.get('type', 'U')
                    electrode_positions = config_data.get('electrode_positions', {})
                    mode_text = 'Unipolar' if stim_type == 'U' else 'Multipolar'
                    self.update_output(f"  {config_name}: {mode_text}, {len(electrode_positions)} electrodes")
            else:
                self.update_output(f"Flex-search montages: {', '.join([config['montage']['name'] for config in flex_montage_configs])}")
                
                # Determine electrode types based on checkboxes
                electrode_types = []
                if self.flex_use_mapped.isChecked():
                    electrode_types.append("mapped")
                if self.flex_use_optimized.isChecked():
                    electrode_types.append("optimized")
                electrode_type_text = ", ".join(electrode_types) if electrode_types else "none"
                
                self.update_output(f"Electrode type: {electrode_type_text}")
            
            if self.sim_mode_multipolar.isChecked():
                self.update_output(f"Current Ch1/Ch2/Ch3/Ch4: {current_ma_1}/{current_ma_2}/{current_ma_3}/{current_ma_4} mA")
            else:
                self.update_output(f"Current Ch1/Ch2: {current_ma_1}/{current_ma_2} mA")
            self.update_output(f"Electrode: {electrode_shape} ({dimensions} mm, {thickness} mm thick)")
            self.update_output("--- STARTING SIMULATION ---")
            
            # Initialize report generator for this simulation session
            self.simulation_session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            project_dir_path = self.pm.get_project_dir()

            self.report_generator = get_simulation_report_generator(project_dir_path, self.simulation_session_id)

            # Add simulation parameters to report (including custom conductivities)
            if self.report_generator:
                self.report_generator.add_simulation_parameters(
                    conductivity_type=conductivity,
                    simulation_mode=sim_mode,
                    eeg_net=eeg_net,
                    intensity_ch1=current_ma_1,
                    intensity_ch2=current_ma_2,
                    quiet_mode=False,
                    conductivities=self._get_conductivities_for_report()
                )

                # Add electrode parameters to report
                dim_parts = dimensions.split(',')
                self.report_generator.add_electrode_parameters(
                    shape=electrode_shape,
                    dimensions=[float(dim_parts[0]), float(dim_parts[1])],
                    thickness=float(thickness)
                )

                # Add subjects to report
                for subject_id in selected_subjects:
                    bids_subject_id = f"sub-{subject_id}"
                    m2m_path = os.path.join(project_dir_path, 'derivatives', 'SimNIBS',
                                          bids_subject_id, f'm2m_{subject_id}')
                    self.report_generator.add_subject(subject_id, m2m_path, 'processing')

                # Add montages to report
                montage_type = 'unipolar' if sim_mode == 'U' else 'multipolar'

                # Load actual electrode pairs from montage file
                montage_file = self.ensure_montage_file_exists(project_dir_path)
                try:
                    with open(montage_file, 'r') as f:
                        montage_data = json.load(f)
                except Exception:
                    montage_data = {"nets": {}}

                for montage_name in selected_montages:
                    # Try to get actual electrode pairs from the montage file
                    electrode_pairs = [['E1', 'E2']]  # Default fallback

                    # Look for the montage in the appropriate net and type
                    net_type = "uni_polar_montages" if sim_mode == 'U' else "multi_polar_montages"

                    if ("nets" in montage_data and
                        eeg_net in montage_data["nets"] and
                        net_type in montage_data["nets"][eeg_net] and
                        montage_name in montage_data["nets"][eeg_net][net_type]):
                        electrode_pairs = montage_data["nets"][eeg_net][net_type][montage_name]

                    # Use keyword arguments for consistency with updated method signature
                    self.report_generator.add_montage(
                        name=montage_name,  # Use 'name' keyword argument for consistency
                        electrode_pairs=electrode_pairs,
                        montage_type=montage_type
                    )

            # Disable UI controls during simulation and set button states
            self.disable_controls()
            self.action_buttons.set_running(True)

            # Set tab as busy (with stop_btn parameter for proper state management)
            if hasattr(self, 'parent') and self.parent:
                self.parent.set_tab_busy(self, True, stop_btn=self.stop_btn, keep_enabled=[self.console_widget.debug_checkbox])

            self.simulation_running = True
            
            # Create and start the thread
            self.simulation_process = SimulationThread(cmd, env)
            self._had_errors_during_run = False
            self._simulation_finished_called = False  # Reset flag for new simulation
            self.simulation_process.output_signal.connect(self._handle_thread_output)
            self.simulation_process.error_signal.connect(lambda msg: self._handle_thread_output(msg, 'error'))
            self.simulation_process.finished.connect(lambda: self.simulation_finished() if not getattr(self, '_simulation_finished_called', False) else None)
            self.simulation_process.start()
            
        except Exception as e:
            self.update_output(f"Error starting simulation: {str(e)}")
            self.simulation_finished()
    
    def simulation_finished(self):
        """Handle simulation completion."""
        # Prevent double calling
        if hasattr(self, '_simulation_finished_called') and self._simulation_finished_called:
            return

        self._simulation_finished_called = True

        if self.debug_mode:
            if self._had_errors_during_run:
                self.output_console.append('<div style="margin: 10px 0;"><span style="color: #ff5555; font-size: 16px; font-weight: bold;">--- SIMULATION PROCESS COMPLETED WITH ERRORS ---</span></div>')
                if hasattr(self, '_first_error_line') and getattr(self, '_first_error_line', None):
                    safe_err = strip_ansi_codes(self._first_error_line)
                    self.update_output(f"First error detected: {safe_err}", 'error')
            else:
                self.output_console.append('<div style="margin: 10px 0;"><span style="color: #55ff55; font-size: 16px; font-weight: bold;">--- SIMULATION PROCESS COMPLETED ---</span></div>')
            self.output_console.append('<div style="border-bottom: 1px solid #555; margin-bottom: 10px;"></div>')

        # Only auto-generate simulation report if there were no errors; else cleanup partial outputs and inform user
        if not self._had_errors_during_run:
            self.auto_generate_simulation_report()
        else:
            self.update_output("[INFO] Skipping automatic report generation due to errors during simulation.", 'warning')
            try:
                self._cleanup_partial_outputs()
            except Exception as cleanup_exc:
                self.update_output(f"[WARNING] Cleanup encountered an issue: {cleanup_exc}", 'warning')

        # Clean up temporary completion files
        self.cleanup_temporary_files()

        # Clean up any remaining temporary flex montage files (CLI should have cleaned most)
        if hasattr(self, 'temp_flex_files'):
            remaining_files = 0
            for temp_file in self.temp_flex_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        remaining_files += 1
                        self.update_output(f"[CLEANUP] Removed temp file: {temp_file}")
                except Exception as e:
                    self.update_output(f"[WARNING] Could not clean up flex file {temp_file}: {str(e)}", 'warning')
            if remaining_files > 0:
                self.update_output(f"[CLEANUP] Removed {remaining_files} remaining temp files")
            delattr(self, 'temp_flex_files')

        self.simulation_running = False
        self._aborting_due_to_error = False

        # Reset button states using centralized method
        self.run_btn.setText("Run Simulation")
        self.action_buttons.set_running(False)

        # Clear parent tab's busy state (with stop_btn parameter for proper state management)
        if hasattr(self, 'parent') and self.parent:
            self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

        # Re-enable all controls
        self.enable_controls()
    
    def auto_generate_simulation_report(self):
        """Auto-generate individual simulation reports for each subject-montage combination."""
        try:
            # Get project directory using path manager
            project_dir = self.pm.get_project_dir()
            
            # Get selected subjects and montages
            selected_subjects = [item.text() for item in self.subject_list.selectedItems()]
            if not selected_subjects:
                self.update_output("Error: No subjects selected", 'error')
                return

            # Get selected montages based on simulation type
            if self.sim_type_montage.isChecked():
                selected_montages = [item.data(QtCore.Qt.UserRole) for item in self.montage_list.selectedItems()]
                if not selected_montages:
                    self.update_output("Error: No montages selected", 'error')
                    return
                simulation_mode = "montage"
            else:
                # For flex-search, get montages from flex-search list
                selected_flex_data = [item.data(QtCore.Qt.UserRole) for item in self.flex_search_list.selectedItems()]
                if not selected_flex_data:
                    self.update_output("Error: No flex-search outputs selected", 'error')
                    return
                simulation_mode = "flex"

            # Generate individual reports for each subject-montage combination
            total_reports = 0
            successful_reports = 0
            
            for subject_id in selected_subjects:
                if simulation_mode == "montage":
                    # Regular montage mode
                    montages_to_process = selected_montages
                    eeg_net = self.eeg_net_combo.currentText()
                else:
                    # Flex-search mode - filter by subject
                    subject_flex_data = [data for data in selected_flex_data if data.get('subject_id') == subject_id]
                    montages_to_process = []
                    
                    # Process flex montages for this subject
                    for flex_data in subject_flex_data:
                        search_name = flex_data['search_name']
                        
                        # Check which electrode types are selected
                        if self.flex_use_mapped.isChecked():
                            montages_to_process.append(self._parse_flex_search_name(search_name, 'mapped'))
                        if self.flex_use_optimized.isChecked():
                            montages_to_process.append(self._parse_flex_search_name(search_name, 'optimized'))
                    
                    # Get EEG net from first flex data for this subject
                    if subject_flex_data:
                        try:
                            search_name = subject_flex_data[0]['search_name']
                            flex_search_dir = self.pm.get_flex_search_dir(subject_id, search_name)
                            mapping_file = os.path.join(flex_search_dir, 'electrode_mapping.json') if flex_search_dir else None
                            
                            if mapping_file and os.path.exists(mapping_file):
                                with open(mapping_file, 'r') as f:
                                    mapping_data = json.load(f)
                                    eeg_net = mapping_data.get('eeg_net', 'EGI_template.csv')
                            else:
                                eeg_net = 'EGI_template.csv'
                        except Exception:
                            eeg_net = 'EGI_template.csv'
                    else:
                        eeg_net = 'EGI_template.csv'
                
                # Generate individual report for each montage for this subject
                for montage_name in montages_to_process:
                    total_reports += 1
                    
                    try:
                        # Create unique session ID for each report
                        individual_session_id = f"{self.simulation_session_id}_{subject_id}_{montage_name}"
                        report_generator = get_simulation_report_generator(project_dir, individual_session_id)
                        
                        if not report_generator:
                            self.update_output(f"[WARNING] Report generator not available for {subject_id}-{montage_name}", 'warning')
                            continue
                        
                        # Add simulation parameters
                        report_generator.add_simulation_parameters(
                            conductivity_type=self.sim_type_combo.currentData(),
                            simulation_mode='U' if self.sim_mode_unipolar.isChecked() else 'M',
                            eeg_net=eeg_net,
                            intensity_ch1=float(self.current_input_1.text() or "5.0"),
                            intensity_ch2=float(self.current_input_2.text() or "5.0"),
                            quiet_mode=True,
                            conductivities=self._get_conductivities_for_report()
                        )
                        
                        # Add electrode parameters
                        dim_parts = (self.dimensions_input.text() or "8,8").split(',')
                        report_generator.add_electrode_parameters(
                            shape="rect" if self.electrode_shape_rect.isChecked() else "ellipse",
                            dimensions=[float(dim_parts[0]), float(dim_parts[1])],
                            thickness=float(self.thickness_input.text() or "4")
                        )
                        
                        # Add this specific subject
                        bids_subject_id = f"sub-{subject_id}"
                        m2m_path = self.pm.get_m2m_dir(subject_id)
                        report_generator.add_subject(subject_id, m2m_path, 'completed')
                        
                        # Add this specific montage
                        report_generator.add_montage(
                            name=montage_name,
                            electrode_pairs=[['E1', 'E2']],  # Default pairs
                            montage_type='unipolar' if self.sim_mode_unipolar.isChecked() else 'multipolar'
                        )
                        
                        # Get expected output files for this specific combination
                        simulations_dir = self.pm.get_simulation_dir(subject_id, f'Simulations/{montage_name}')
                        ti_dir = os.path.join(simulations_dir, 'TI') if simulations_dir else None
                        nifti_dir = os.path.join(ti_dir, 'niftis')
                        
                        output_files = {'TI': [], 'niftis': []}
                        if os.path.exists(nifti_dir):
                            nifti_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii.gz')]
                            output_files['niftis'] = [os.path.join(nifti_dir, f) for f in nifti_files]
                            ti_files = [f for f in nifti_files if 'TI_max' in f]
                            output_files['TI'] = [os.path.join(nifti_dir, f) for f in ti_files]
                        
                        # Add simulation result for this specific combination
                        report_generator.add_simulation_result(
                            subject_id=subject_id,
                            montage_name=montage_name,
                            output_files=output_files,
                            duration=None,
                            status='completed'
                        )
                        
                        # Generate individual report
                        report_path = report_generator.generate_report()
                        successful_reports += 1
                        self.update_output(f"[SUCCESS] Individual report generated for {subject_id}-{montage_name}: {os.path.basename(report_path)}")
                        
                    except Exception as e:
                        self.update_output(f"[ERROR] Error generating report for {subject_id}-{montage_name}: {str(e)}", 'error')
            
            # Summary
            self.update_output(f"--- Generated {successful_reports}/{total_reports} individual simulation reports ---")
            
            if successful_reports > 0:
                reports_dir = self.pm.get_reports_dir()
                self.update_output(f"[INFO] Reports saved in: {reports_dir}")
                
                # Open the reports directory instead of individual files
                self._open_directory_safely(reports_dir)

        except Exception as e:
            self.update_output(f"[ERROR] Error generating simulation reports: {str(e)}", 'error')
            import traceback
            self.update_output(f"Traceback: {traceback.format_exc()}", 'error')

    def disable_controls(self):
        """Disable all controls except the stop button."""
        # Disable all buttons
        self.list_subjects_btn.setEnabled(False)
        self.select_all_subjects_btn.setEnabled(False)
        self.clear_subject_selection_btn.setEnabled(False)
        self.list_montages_btn.setEnabled(False)
        self.clear_montage_selection_btn.setEnabled(False)
        self.add_new_montage_btn.setEnabled(False)
        self.remove_montage_btn.setEnabled(False)
        
        # Disable all inputs
        self.sim_type_combo.setEnabled(False)
        self.sim_type_montage.setEnabled(False)
        self.sim_type_flex.setEnabled(False)
        self.eeg_net_combo.setEnabled(False)
        self.sim_mode_unipolar.setEnabled(False)
        self.sim_mode_multipolar.setEnabled(False)
        self.current_input_1.setEnabled(False)
        self.current_input_2.setEnabled(False)
        self.current_input_3.setEnabled(False)
        self.current_input_4.setEnabled(False)
        self.electrode_shape_rect.setEnabled(False)
        self.electrode_shape_ellipse.setEnabled(False)
        self.dimensions_input.setEnabled(False)
        self.thickness_input.setEnabled(False)
        
        # Disable list widgets
        self.subject_list.setEnabled(False)
        self.montage_list.setEnabled(False)
        self.flex_search_list.setEnabled(False)
        
        # Disable flex-search controls
        self.refresh_flex_btn.setEnabled(False)
        self.clear_flex_selection_btn.setEnabled(False)
        self.flex_use_mapped.setEnabled(False)
        self.flex_use_optimized.setEnabled(False)
    
    def enable_controls(self):
        """Re-enable all controls."""
        # Enable all buttons
        self.list_subjects_btn.setEnabled(True)
        self.select_all_subjects_btn.setEnabled(True)
        self.clear_subject_selection_btn.setEnabled(True)
        self.list_montages_btn.setEnabled(True)
        self.clear_montage_selection_btn.setEnabled(True)
        self.add_new_montage_btn.setEnabled(True)
        self.remove_montage_btn.setEnabled(True)
        
        # Enable all inputs
        self.sim_type_combo.setEnabled(True)
        self.sim_type_montage.setEnabled(True)
        self.sim_type_flex.setEnabled(True)
        self.eeg_net_combo.setEnabled(True)
        self.sim_mode_unipolar.setEnabled(True)
        self.sim_mode_multipolar.setEnabled(True)
        self.current_input_1.setEnabled(True)
        self.current_input_2.setEnabled(True)
        self.current_input_3.setEnabled(True)
        self.current_input_4.setEnabled(True)
        self.electrode_shape_rect.setEnabled(True)
        self.electrode_shape_ellipse.setEnabled(True)
        self.dimensions_input.setEnabled(True)
        self.thickness_input.setEnabled(True)
        
        # Enable list widgets
        self.subject_list.setEnabled(True)
        self.montage_list.setEnabled(True)
        self.flex_search_list.setEnabled(True)
        
        # Enable flex-search controls
        self.refresh_flex_btn.setEnabled(True)
        self.clear_flex_selection_btn.setEnabled(True)
        self.flex_use_mapped.setEnabled(True)
        self.flex_use_optimized.setEnabled(True)
    
    def update_current_inputs_visibility(self):
        """Update the visibility of current input channels based on simulation mode."""
        is_multipolar = self.sim_mode_multipolar.isChecked()
        
        # Show/hide channels 3 and 4 based on multipolar mode
        for widget in self.multipolar_current_widgets:
            widget.setVisible(is_multipolar)
    
    def update_electrode_inputs(self, checked):
        """Update the electrode input form based on the selected simulation mode.
        This only affects which montages are shown in the list."""
        self.update_montage_list(checked)
    
    def clear_console(self):
        """Clear the output console."""
        self.output_console.clear()
    
    def stop_simulation(self):
        """Stop the running simulation."""
        if hasattr(self, 'simulation_process') and self.simulation_process:
            # Show stopping message
            self.update_output("Stopping simulation...")
            self.output_console.append('<div style="margin: 10px 0;"><span style="color: #ff5555; font-weight: bold;">--- SIMULATION TERMINATED BY USER ---</span></div>')

            # Terminate the process
            if self.simulation_process.terminate_process():
                self.update_output("Simulation process terminated successfully.")
            else:
                self.update_output("Failed to terminate simulation process or process already completed.")

            # Reset UI state
            self.simulation_running = False
            self.run_btn.setText("Run Simulation")
            self.action_buttons.set_running(False)

            # Clear parent tab's busy state (with stop_btn parameter for proper state management)
            if hasattr(self, 'parent') and self.parent:
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

            # Clean up temporary flex montage files
            if hasattr(self, 'temp_flex_files'):
                remaining_files = 0
                for temp_file in self.temp_flex_files:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                            remaining_files += 1
                            self.update_output(f"[CLEANUP] Removed temp file: {temp_file}")
                    except Exception as e:
                        self.update_output(f"[WARNING] Could not clean up flex file {temp_file}: {str(e)}", 'warning')
                if remaining_files > 0:
                    self.update_output(f"[CLEANUP] Removed {remaining_files} temp files after stop")
                delattr(self, 'temp_flex_files')

            # Re-enable all controls
            self.enable_controls()
    
    def validate_electrode(self, electrode):
        """Validate electrode name is not empty."""
        return bool(electrode and electrode.strip())
    
    def validate_current(self, current):
        """Validate current value is a number."""
        try:
            float(current)
            return True
        except ValueError:
            return False

    def update_output(self, text, message_type='default'):
        """Update the console output with colored text."""
        if not text.strip():
            return

        # Strip ANSI escape sequences before any formatting
        text = strip_ansi_codes(text)
        
        # Filter messages based on debug mode
        if not self.debug_mode:
            # In non-debug mode, only show important messages
            if not is_important_message(text, message_type, 'simulator'):
                return
            # Colorize summary lines: blue for starts, white for completes, green for final
            lower = text.lower()
            is_final = lower.startswith('└─') or 'completed successfully' in lower
            is_start = lower.startswith('beginning ') or ': starting' in lower
            is_complete = ('✓ complete' in lower) or ('results saved to' in lower) or ('saved to' in lower)
            color = '#55ff55' if is_final else ('#55aaff' if is_start else '#ffffff')
            formatted_text = f'<span style="color: {color};">{text}</span>'
            scrollbar = self.output_console.verticalScrollBar()
            at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
            self.output_console.append(formatted_text)
            if at_bottom:
                self.output_console.ensureCursorVisible()
            QtWidgets.QApplication.processEvents()
            return
            
        # Format the output based on message type from thread
        if message_type == 'error':
            formatted_text = f'<span style="color: #ff5555;"><b>{text}</b></span>'
        elif message_type == 'warning':
            formatted_text = f'<span style="color: #ffff55;">{text}</span>'
        elif message_type == 'debug':
            formatted_text = f'<span style="color: #7f7f7f;">{text}</span>'
        elif message_type == 'command':
            formatted_text = f'<span style="color: #55aaff;">{text}</span>'
        elif message_type == 'success':
            formatted_text = f'<span style="color: #55ff55;"><b>{text}</b></span>'
        elif message_type == 'info':
            formatted_text = f'<span style="color: #55ffff;">{text}</span>'
        else:
            # Fallback to content-based formatting for backward compatibility
            if "Processing... Only the Stop button is available" in text:
                formatted_text = f'<div style="background-color: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px;"><span style="color: #ffff55; font-weight: bold;">{text}</span></div>'
            elif text.strip().startswith("-"):
                # Indented list items
                formatted_text = f'<span style="color: #aaaaaa; margin-left: 20px;">  {text}</span>'
            else:
                formatted_text = f'<span style="color: #ffffff;">{text}</span>'
        
        # Check if user is at the bottom of the console before appending
        scrollbar = self.output_console.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5  # Allow small tolerance
        
        # Append to the console with HTML formatting
        self.output_console.append(formatted_text)
        
        # Only auto-scroll if user was already at the bottom
        if at_bottom:
            self.output_console.ensureCursorVisible()
        
        QtWidgets.QApplication.processEvents()

    def set_debug_mode(self, debug_mode):
        """Set debug mode for output filtering."""
        self.debug_mode = debug_mode
        # Sync with console widget's internal state if it exists
        if hasattr(self, 'console_widget'):
            self.console_widget.debug_mode = debug_mode

    def _open_file_safely(self, file_path):
        """Safely open a file in the default application, with fallbacks for different environments."""
        import webbrowser
        import platform
        
        try:
            # First try webbrowser (works on most systems)
            webbrowser.open('file://' + os.path.abspath(file_path))
            self.update_output("[INFO] File opened in default application")
        except Exception as e:
            # Fallback: try platform-specific commands
            try:
                system = platform.system().lower()
                if system == "linux":
                    # Try xdg-open first, then common browsers
                    try:
                        subprocess.run(['xdg-open', file_path], check=True)
                        self.update_output("[INFO] File opened with xdg-open")
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        # Try common browsers as fallback
                        browsers = ['firefox', 'chromium', 'google-chrome', 'chrome']
                        opened = False
                        for browser in browsers:
                            try:
                                subprocess.run([browser, file_path], check=True)
                                self.update_output(f"[INFO] File opened with {browser}")
                                opened = True
                                break
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                continue
                        if not opened:
                            self.update_output(f"[WARNING] File generated but couldn't open automatically: {file_path}")
                elif system == "darwin":  # macOS
                    subprocess.run(['open', file_path], check=True)
                    self.update_output("[INFO] File opened with macOS open command")
                elif system == "windows":
                    os.startfile(file_path)
                    self.update_output("[INFO] File opened with Windows startfile")
                else:
                    self.update_output(f"[WARNING] File generated but couldn't open automatically: {file_path}")
            except Exception as e2:
                self.update_output(f"[WARNING] File generated but couldn't open automatically: {file_path}")
                self.update_output(f"[DEBUG] Open error: {str(e2)}")

    def _open_directory_safely(self, dir_path):
        """Safely open a directory in the file manager, with fallbacks for different environments."""
        import platform
        
        try:
            system = platform.system().lower()
            if system == "linux":
                # Try xdg-open first, then common file managers
                try:
                    subprocess.run(['xdg-open', dir_path], check=True)
                    self.update_output("[INFO] Directory opened with xdg-open")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # Try common file managers as fallback
                    file_managers = ['nautilus', 'dolphin', 'thunar', 'pcmanfm', 'nemo']
                    opened = False
                    for fm in file_managers:
                        try:
                            subprocess.run([fm, dir_path], check=True)
                            self.update_output(f"[INFO] Directory opened with {fm}")
                            opened = True
                            break
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            continue
                    if not opened:
                        self.update_output(f"[WARNING] Directory available but couldn't open file manager: {dir_path}")
            elif system == "darwin":  # macOS
                subprocess.run(['open', dir_path], check=True)
                self.update_output("[INFO] Directory opened with macOS open command")
            elif system == "windows":
                os.startfile(dir_path)
                self.update_output("[INFO] Directory opened with Windows Explorer")
            else:
                self.update_output(f"[WARNING] Directory available but couldn't open file manager: {dir_path}")
        except Exception as e:
            self.update_output(f"[WARNING] Directory available but couldn't open file manager: {dir_path}")
            self.update_output(f"[DEBUG] Open error: {str(e)}")

    def _handle_thread_output(self, text, message_type='default'):
        """Internal handler to track errors and forward to UI update."""
        if message_type == 'error':
            # Allow process to continue, but mark that there were errors
            self._had_errors_during_run = True
            # Remember the first triggering error line for reporting
            if not hasattr(self, '_first_error_line') or not getattr(self, '_first_error_line', None):
                self._first_error_line = text
            # Abort immediately on first error
            if not self._aborting_due_to_error and getattr(self, 'simulation_process', None):
                self._aborting_due_to_error = True
                self.update_output("[ERROR] Error detected. Aborting simulation and cleaning up partial outputs...", 'error')
                # Terminate the running process
                try:
                    self.simulation_process.terminate_process()
                except Exception:
                    pass
                # Perform cleanup of outputs generated so far
                try:
                    self._cleanup_partial_outputs()
                except Exception as cleanup_exc:
                    self.update_output(f"[WARNING] Cleanup encountered an issue: {cleanup_exc}", 'warning')
                # Explicitly finish simulation to reset UI state immediately
                self.simulation_finished()
        self.update_output(text, message_type)

    def _cleanup_partial_outputs(self):
        """Remove files/directories created during a failed simulation run."""
        for subject_id in (self._current_run_subjects or []):
            sub_root = self.pm.get_subject_dir(subject_id)
            sim_root = os.path.join(sub_root, 'Simulations') if sub_root else None
            if not sim_root:
                continue
            # Remove tmp directory entirely
            tmp_dir = os.path.join(sim_root, 'tmp')
            if os.path.isdir(tmp_dir):
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    self.update_output(f"[CLEANUP] Removed temporary directory: {tmp_dir}")
                except Exception:
                    pass
            # Remove montage-specific output directories that may have been created
            for montage_name in (self._current_run_montages or []):
                montage_dir = os.path.join(sim_root, montage_name)
                if os.path.isdir(montage_dir):
                    try:
                        shutil.rmtree(montage_dir, ignore_errors=True)
                        self.update_output(f"[CLEANUP] Removed partial montage outputs: {montage_dir}")
                    except Exception:
                        pass
            # Mark log files created during this failed run as errored by renaming them
            logs_dir = self.pm.get_logs_dir(subject_id)
            if os.path.isdir(logs_dir):
                try:
                    for fname in list(os.listdir(logs_dir)):
                        fpath = os.path.join(logs_dir, fname)
                        # Heuristic: rename simulator logs created after run start
                        try:
                            if os.path.isfile(fpath) and fname.startswith('simulator_') and not fname.startswith('simulator_errored_'):
                                if self._run_start_time is None or os.path.getmtime(fpath) >= self._run_start_time - 1:
                                    suffix = fname[len('simulator_'):]
                                    new_name = f"simulator_errored_{suffix}"
                                    new_path = os.path.join(logs_dir, new_name)
                                    try:
                                        os.rename(fpath, new_path)
                                        self.update_output(f"[CLEANUP] Marked errored log: {fname} -> {new_name}")
                                    except Exception:
                                        # If rename fails (e.g., file locked), skip silently
                                        pass
                        except Exception:
                            continue
                except Exception:
                    pass

    def show_add_montage_dialog(self):
        """Show the dialog for adding a new montage."""
        dialog = AddMontageDialog(self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Get data from dialog
            montage_data = dialog.get_montage_data()
            
            # Validate the montage data
            if not montage_data["name"]:
                self.update_output("Error: Montage name is required")
                return
                
            if not montage_data["electrode_pairs"]:
                self.update_output("Error: At least one electrode pair is required")
                return
                
            # Validate electrode formats
            for pair in montage_data["electrode_pairs"]:
                if not self.validate_electrode(pair[0]) or not self.validate_electrode(pair[1]):
                    self.update_output("Error: Invalid electrode format (should be E1, E2)")
                    return
            
            # Get project directory using path manager
            project_dir = self.pm.get_project_dir()
            
            # Ensure montage file exists and get its path
            montage_file = self.ensure_montage_file_exists(project_dir)
            
            # Load existing montage data
            with open(montage_file, 'r') as f:
                montage_data_file = json.load(f)
            
            # Ensure the target net exists in the structure
            target_net = montage_data["target_net"]
            if "nets" not in montage_data_file:
                montage_data_file["nets"] = {}
            if target_net not in montage_data_file["nets"]:
                montage_data_file["nets"][target_net] = {
                    "uni_polar_montages": {},
                    "multi_polar_montages": {}
                }
            
            # Add the new montage to the appropriate section
            montage_type = "uni_polar_montages" if montage_data["is_unipolar"] else "multi_polar_montages"
            
            # Store the montage under the correct net and type
            montage_data_file["nets"][target_net][montage_type][montage_data["name"]] = montage_data["electrode_pairs"]
            
            # Save the updated montage data
            with open(montage_file, 'w') as f:
                json.dump(montage_data_file, f, indent=4)
            
            # Format pairs for display
            pairs_text = ", ".join([f"{pair[0]}↔{pair[1]}" for pair in montage_data["electrode_pairs"]])
            
            self.update_output(f"Added {montage_type.split('_')[0]} montage '{montage_data['name']}' for net {target_net} with pairs: {pairs_text}")
            self.update_output(f"Montage saved to: {montage_file}")
            
            # Refresh the list of montages
            self.update_montage_list()

    def remove_selected_montage(self):
        """Remove the selected montage from the montage list file."""
        try:
            # Get selected montage
            selected_items = self.montage_list.selectedItems()
            if not selected_items:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please select a montage to remove.")
                return
            
            # Get the montage name from UserRole data
            montage_name = selected_items[0].data(QtCore.Qt.UserRole)
            if not montage_name:
                QtWidgets.QMessageBox.warning(self, "Warning", "Invalid montage selection.")
                return
            
            # Confirm deletion
            reply = QtWidgets.QMessageBox.question(
                self, 
                "Confirm Deletion",
                f"Are you sure you want to delete the montage '{montage_name}'?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # Get project directory using path manager
                project_dir = self.pm.get_project_dir()
                
                # Ensure montage file exists and get its path
                montage_file = self.ensure_montage_file_exists(project_dir)
                
                # Load existing montage data
                with open(montage_file, 'r') as f:
                    montage_data = json.load(f)
                
                # Get current net and mode
                current_net = self.eeg_net_combo.currentText()
                montage_type = "uni_polar_montages" if self.sim_mode_unipolar.isChecked() else "multi_polar_montages"
                
                # Remove the montage if it exists
                if (current_net in montage_data["nets"] and 
                    montage_type in montage_data["nets"][current_net] and 
                    montage_name in montage_data["nets"][current_net][montage_type]):
                    
                    del montage_data["nets"][current_net][montage_type][montage_name]
                    
                    # Save the updated montage data
                    with open(montage_file, 'w') as f:
                        json.dump(montage_data, f, indent=4)
                    
                    self.update_output(f"Removed montage '{montage_name}' from {montage_type}")
                    
                    # Remove the item from the list widget
                    self.montage_list.takeItem(self.montage_list.row(selected_items[0]))
                else:
                    QtWidgets.QMessageBox.warning(self, "Warning", f"Montage '{montage_name}' not found.")
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Error removing montage: {str(e)}")
            print(f"Detailed error: {str(e)}")  # For debugging

    def show_sim_type_help(self):
        """Show help information about simulation types."""
        help_text = """
        <h3>Simulation Types (Anisotropy Types)</h3>
        
        <b>Isotropic (scalar):</b><br>
        - Uses uniform conductivity values for all tissue types<br>
        - Faster computation but less accurate for anisotropic tissues<br>
        - Recommended for initial testing and quick results<br>
        - Default option for basic simulations<br><br>
        
        <b>Anisotropic (vn):</b><br>
        - Uses volume-normalized anisotropic conductivities<br>
        - Tensors are normalized to have the same trace and re-scaled according to their respective tissue conductivity<br>
        - Recommended for simulations with anisotropic conductivities<br>
        - Based on Opitz et al., 2011<br><br>
        
        <b>Anisotropic (dir):</b><br>
        - Uses direct anisotropic conductivity<br>
        - Does not normalize individual tensors<br>
        - Re-scales tensors according to the mean gray and white matter conductivities<br>
        - Based on Opitz et al., 2011<br><br>
        
        <b>Anisotropic (mc):</b><br>
        - Uses isotropic, varying conductivities<br>
        - Assigns to each voxel a conductivity value related to the volume of the tensors<br>
        - Obtained from the direct approach<br>
        - Based on Opitz et al., 2011<br><br>
        
        <i>Note: All options other than 'scalar' require conductivity tensors acquired from diffusion weighted images and processed with dwi2cond.</i><br><br>
        
        For full documentation, see the SimNIBS website.
        """
        
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Simulation Type Help")
        msg.setTextFormat(QtCore.Qt.RichText)
        msg.setText(help_text)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2a2a2a;
                color: white;
            }
            QLabel {
                min-width: 600px;
                max-width: 800px;
                color: white;
            }
        """)
        
        # Set the message box to be resizable
        msg.setWindowFlags(msg.windowFlags() | QtCore.Qt.WindowMaximizeButtonHint)
        
        # Set a larger default size
        msg.setMinimumSize(700, 600)
        
        # Enable text wrapping for the label
        for child in msg.findChildren(QtWidgets.QLabel):
            child.setWordWrap(True)
        
        # Adjust the size to fit content
        msg.adjustSize()
        
        msg.exec_()

    def show_montage_source_help(self):
        """Show help information about montage source options."""
        help_text = """
        <h3>Montage Source Options</h3>
        <br>
        <br>
        <b>Montage List:</b><br>
        - Manually define electrode montages using the "Add New" button<br>
        - Each montage is associated with a specific EEG net template<br>
        - Ideal for testing specific montage configurations or traditional TES protocols<br>
        <br>
        <b>Flex-Search:</b><br>
        - Uses results from a previously completed Flex-Search optimization<br>
        - Automatically loads optimized electrode configurations from Flex-Search output<br>
        - <b>Prerequisites:</b> You must have completed a Flex-Search optimization for the selected subject(s)<br>
        - <b>Two simulation options available:</b><br>
        &nbsp;&nbsp;&nbsp;1. <b>Mapped Electrodes:</b> If electrode mapping was enabled during Flex-Search, uses the optimized electrodes mapped to EEG net positions<br>
        &nbsp;&nbsp;&nbsp;2. <b>Optimized Electrodes:</b> Uses the raw optimized electrode positions (not associated with any EEG net template)<br>
        - The choice between mapped/optimized is automatically determined by your Flex-Search settings<br><br>
        
        """
        
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Montage Source Help")
        msg.setTextFormat(QtCore.Qt.RichText)
        msg.setText(help_text)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2a2a2a;
                color: white;
            }
            QLabel {
                min-width: 600px;
                max-width: 800px;
                color: white;
            }
        """)
        
        # Set the message box to be resizable
        msg.setWindowFlags(msg.windowFlags() | QtCore.Qt.WindowMaximizeButtonHint)
        
        # Set a larger default size
        msg.setMinimumSize(700, 500)
        
        # Enable text wrapping for the label
        for child in msg.findChildren(QtWidgets.QLabel):
            child.setWordWrap(True)
        
        # Adjust the size to fit content
        msg.adjustSize()
        
        msg.exec_()

    def validate_inputs(self):
        """Validate all input parameters before running the simulation."""
        # Check if any subjects are selected
        if not self.subject_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one subject.")
            return False
            
        # Check if any montages are selected
        if not self.montage_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select at least one montage.")
            return False
            
        # Validate current values
        try:
            current_1 = float(self.current_input_1.text() or "1.0")
            current_2 = float(self.current_input_2.text() or "1.0")
            
            if self.sim_mode_multipolar.isChecked():
                current_3 = float(self.current_input_3.text() or "1.0")
                current_4 = float(self.current_input_4.text() or "1.0")
                if current_1 <= 0 or current_2 <= 0 or current_3 <= 0 or current_4 <= 0:
                    QtWidgets.QMessageBox.warning(self, "Warning", "All current values must be greater than 0 mA.")
                    return False
            else:
                if current_1 <= 0 or current_2 <= 0:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Current values must be greater than 0 mA.")
                    return False
        except ValueError:
            channels_text = "all channels" if self.sim_mode_multipolar.isChecked() else "both channels"
            QtWidgets.QMessageBox.warning(self, "Warning", f"Please enter valid current values in mA for {channels_text}.")
            return False
            
        # Validate dimensions
        try:
            dimensions = self.dimensions_input.text() or "8,8"
            dim_parts = dimensions.split(',')
            if len(dim_parts) != 2:
                raise ValueError("Invalid dimensions format")
            float(dim_parts[0])
            float(dim_parts[1])
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter valid dimensions in format 'x,y' (e.g., '8,8').")
            return False
            
        # Validate thickness
        try:
            thickness = float(self.thickness_input.text() or "4")
            if thickness <= 0:
                QtWidgets.QMessageBox.warning(self, "Warning", "Thickness must be greater than 0 mm.")
                return False
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please enter a valid thickness value in mm.")
            return False
            
        # Validate EEG net selection
        if not self.eeg_net_combo.currentText():
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select an EEG net.")
            return False
            
        return True

    def show_conductivity_editor(self):
        """Show the conductivity editor dialog."""
        dialog = ConductivityEditorDialog(self, self.custom_conductivities)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.custom_conductivities = dialog.get_conductivities()
    
    def _get_conductivities_for_report(self):
        """Get conductivity values formatted for the simulation report."""
        # Start with default values
        temp_gen = get_simulation_report_generator("", "")
        
        if not temp_gen:
            # Fallback to manual conductivity dict if report generator not available
            conductivities = {
                1: {'name': 'White Matter', 'conductivity': 0.126, 'reference': 'Wagner et al., 2004'},
                2: {'name': 'Gray Matter', 'conductivity': 0.275, 'reference': 'Wagner et al., 2004'},
                3: {'name': 'CSF', 'conductivity': 1.654, 'reference': 'Wagner et al., 2004'},
                4: {'name': 'Bone', 'conductivity': 0.01, 'reference': 'Wagner et al., 2004'},
                5: {'name': 'Scalp', 'conductivity': 0.465, 'reference': 'Wagner et al., 2004'},
            }
        else:
            conductivities = temp_gen._get_default_conductivities()
        
        # Override with any custom values
        for tissue_num, custom_value in self.custom_conductivities.items():
            if tissue_num in conductivities:
                conductivities[tissue_num]['conductivity'] = custom_value
                conductivities[tissue_num]['reference'] = 'Custom (User Modified)'
            else:
                # Add new custom tissue
                conductivities[tissue_num] = {
                    'name': f'Custom Tissue {tissue_num}',
                    'conductivity': custom_value,
                    'reference': 'Custom (User Defined)'
                }
        
        return conductivities

    def cleanup_temporary_files(self):
        """Clean up temporary simulation completion files after processing."""
        try:
            # Get project directory using path manager
            project_dir = self.pm.get_project_dir()
            derivatives_dir = self.pm.get_derivatives_dir()
            temp_dir = os.path.join(derivatives_dir, 'temp') if derivatives_dir else None
            if not temp_dir:
                return
            
            if not os.path.exists(temp_dir):
                return
            
            # Find and clean up completion files
            cleaned_count = 0
            for filename in os.listdir(temp_dir):
                if filename.startswith('simulation_completion_') and filename.endswith('.json'):
                    file_path = os.path.join(temp_dir, filename)
                    try:
                        # Check if file is older than 5 minutes to avoid cleaning files from concurrent simulations
                        file_mtime = os.path.getmtime(file_path)
                        current_time = time.time()
                        if current_time - file_mtime > 300:  # 5 minutes
                            os.remove(file_path)
                            cleaned_count += 1
                            self.update_output(f"[CLEANUP] Removed temporary file: {filename}")
                        else:
                            # If it's our session, clean it up immediately
                            if (hasattr(self, 'simulation_session_id') and 
                                self.simulation_session_id and 
                                self.simulation_session_id in filename):
                                os.remove(file_path)
                                cleaned_count += 1
                                self.update_output(f"[CLEANUP] Removed session file: {filename}")
                    except Exception as e:
                        self.update_output(f"[WARNING] Could not clean up {filename}: {str(e)}", 'warning')
            
            if cleaned_count > 0:
                self.update_output(f"[CLEANUP] Removed {cleaned_count} temporary completion file(s)")
            
            # Also try to remove the temp directory if it's empty
            try:
                if not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
                    self.update_output("[CLEANUP] Removed empty temp directory")
            except OSError:
                pass  # Directory not empty or permission issue, ignore
                
        except Exception as e:
            self.update_output(f"[ERROR] Error during cleanup: {str(e)}", 'warning')

    def _format_montage_label(self, montage_name, pairs, is_unipolar=True):
        """Format montage label for the list widget: montage_name: ch1:X<->Y + ch2:A<->B (+ ch3/ch4...)"""
        if not pairs or not isinstance(pairs, list):
            return montage_name
        channel_labels = []
        for idx, pair in enumerate(pairs):
            if isinstance(pair, list) and len(pair) == 2:
                channel = f"ch{idx+1}:{pair[0]}<-> {pair[1]}"
                channel_labels.append(channel)
        return f"{montage_name}: " + " + ".join(channel_labels)

    def check_simulation_completion_reports(self):
        """Check for simulation completion reports and update the report generator."""
        if not self.report_generator:
            return
        
        try:
            derivatives_dir = self.pm.get_derivatives_dir()
            temp_dir = os.path.join(derivatives_dir, 'temp') if derivatives_dir else None
            if not temp_dir:
                return
            
            if not os.path.exists(temp_dir):
                return
            
            # Look for completion report files
            completion_files = [f for f in os.listdir(temp_dir) if f.startswith('simulation_completion_') and f.endswith('.json')]
            
            for completion_file in completion_files:
                completion_path = os.path.join(temp_dir, completion_file)
                try:
                    with open(completion_path, 'r') as f:
                        completion_data = json.load(f)
                    
                    # Check if this completion report matches our session
                    if completion_data.get('session_id') == self.simulation_session_id:
                        self.update_output(f"Processing completion report for session {self.simulation_session_id}")
                        
                        # Add simulation results for each completed simulation
                        for sim in completion_data.get('completed_simulations', []):
                            subject_id = completion_data['subject_id']
                            montage_name = sim['montage_name']
                            
                            # Determine final output files after main-TI.sh processing
                            final_output_files = self._get_expected_output_files(
                                completion_data['project_dir'], 
                                subject_id, 
                                montage_name
                            )
                            
                            # Add the simulation result
                            self.report_generator.add_simulation_result(
                                subject_id=subject_id,
                                montage_name=montage_name,
                                output_files=final_output_files,
                                duration=None,  # Duration not tracked yet
                                status='completed'
                            )
                            
                            self.update_output(f"Recorded simulation result for {subject_id} - {montage_name}")
                        
                        # Update subject status to completed
                        self.report_generator.update_subject_status(completion_data['subject_id'], 'completed')
                        
                        # Clean up the completion report file
                        os.remove(completion_path)
                        self.update_output(f"Processed and removed completion report: {completion_file}")
                        
                except json.JSONDecodeError:
                    self.update_output(f"Error: Invalid JSON in completion report {completion_file}")
                except Exception as e:
                    self.update_output(f"Error processing completion report {completion_file}: {str(e)}")
                    
        except Exception as e:
            self.update_output(f"Error checking completion reports: {str(e)}")
    
    def _get_expected_output_files(self, project_dir, subject_id, montage_name):
        """Get expected output files for a simulation."""
        simulations_dir = self.pm.get_simulation_dir(subject_id, f"Simulations/{montage_name}")
        ti_dir = os.path.join(simulations_dir, "TI")
        nifti_dir = os.path.join(ti_dir, "niftis")
        
        output_files = {'TI': [], 'niftis': []}
        if os.path.exists(nifti_dir):
            # Add all NIfTI files
            nifti_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii.gz')]
            output_files['niftis'] = [os.path.join(nifti_dir, f) for f in nifti_files]
            
            # Add TI files specifically
            ti_files = [f for f in nifti_files if 'TI_max' in f]
            output_files['TI'] = [os.path.join(nifti_dir, f) for f in ti_files]
        
        return output_files

    def on_worker_finished(self, worker_id, output):
        """Handle completion of simulation worker."""
        try:
            # Set tab as not busy
            if hasattr(self, 'parent') and self.parent:
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)
            
            # Update subjects status
            if not self.report_generator:
                self.update_output("Warning: No report generator available")
                return
            
            # Check for completion reports and update simulation results
            self.check_simulation_completion_reports()
            
            # Generate individual simulation report
            self.update_output("Generating simulation report...")
            report_path = self.report_generator.generate_report()
            self.update_output(f"[SUCCESS] Simulation report generated: {report_path}")
            
            # Open report in browser
            self._open_file_safely(report_path)
            
        except Exception as e:
            self.update_output(f"[ERROR] Error in simulation completion: {str(e)}")
            # Still set tab as not busy even if there's an error
            if hasattr(self, 'parent') and self.parent:
                self.parent.set_tab_busy(self, False, stop_btn=self.stop_btn)

    def _parse_flex_search_name(self, search_name, electrode_type):
        """
        Parse flex-search name and create proper naming format.
        
        Args:
            search_name: Search directory name with format:
                        - Atlas: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
                        - Spherical: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
                        - Subcortical: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
                        - Legacy cortical: {hemisphere}.{region}_{atlas}_{goal}_{postprocess}
            electrode_type: 'mapped' or 'optimized'
            
        Returns:
            str: Formatted name following flex_{hemisphere}_{atlas}_{region}_{goal}_{postproc}_{electrode_type}
        """
        try:
            # Clean the search name first
            search_name = search_name.strip()
            # Handle new naming convention first
            
            # Handle spherical search names: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
            if search_name.startswith('sphere_'):
                parts = search_name.split('_')
                if len(parts) >= 3:
                    hemisphere = 'spherical'
                    # Extract coordinate part (e.g., x10y-5z20r5)
                    coords_part = parts[1] if len(parts) > 1 else 'coords'
                    goal = parts[-2] if len(parts) >= 3 else 'optimization'
                    post_proc = parts[-1] if len(parts) >= 3 else 'maxTI'
                    
                    return f"flex_{hemisphere}_{coords_part}_{goal}_{post_proc}_{electrode_type}"
            
            # Handle subcortical search names: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
            elif search_name.startswith('subcortical_'):
                parts = search_name.split('_')
                if len(parts) >= 5:
                    hemisphere = 'subcortical'
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = parts[4]
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Handle cortical search names: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
            elif '_' in search_name and len(search_name.split('_')) >= 5:
                parts = search_name.split('_')
                if len(parts) >= 5 and parts[0] in ['lh', 'rh']:
                    hemisphere = parts[0]
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = parts[4]
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Fallback: Handle legacy formats for backward compatibility
            
            # Legacy cortical search names: lh.101_DK40_14_mean
            elif search_name.startswith(('lh.', 'rh.')):
                parts = search_name.split('_')
                if len(parts) >= 3:
                    hemisphere_region = parts[0]  # e.g., 'lh.101'
                    atlas = parts[1]  # e.g., 'DK40'
                    goal_postproc = '_'.join(parts[2:])  # e.g., '14_mean'
                    
                    # Extract hemisphere and region
                    if '.' in hemisphere_region:
                        hemisphere, region = hemisphere_region.split('.', 1)
                    else:
                        hemisphere = 'unknown'
                        region = hemisphere_region
                    
                    # Split goal and postProc if possible
                    if '_' in goal_postproc:
                        goal_parts = goal_postproc.split('_')
                        region = goal_parts[0]  # First part is actually the region
                        goal = goal_parts[1] if len(goal_parts) > 1 else 'optimization'
                        post_proc = '_'.join(goal_parts[2:]) if len(goal_parts) > 2 else 'maxTI'
                    else:
                        goal = goal_postproc
                        post_proc = 'maxTI'
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Legacy subcortical search names: subcortical_atlas_region_goal
            elif search_name.startswith('subcortical_') and len(search_name.split('_')) == 4:
                parts = search_name.split('_')
                if len(parts) >= 4:
                    hemisphere = 'subcortical'
                    atlas = parts[1]
                    region = parts[2]
                    goal = parts[3]
                    post_proc = 'maxTI'  # Default for legacy
                    
                    return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Legacy spherical coordinates: assume any other format with underscores
            elif '_' in search_name:
                parts = search_name.split('_')
                hemisphere = 'spherical'
                atlas = 'coordinates'
                region = '_'.join(parts[:-1]) if len(parts) > 1 else search_name
                goal = parts[-1] if parts else 'optimization'
                post_proc = 'maxTI'
                
                return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
            
            # Fallback for unrecognized formats
            else:
                return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"
                
        except Exception as e:
            self.update_output(f"Warning: Could not parse flex search name '{search_name}': {e}", 'warning')
            return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"


    def cleanup_old_simulation_directories(self, subject_id):
        """
        Clean up old simulation directories that might interfere with flex-search discovery.
        Only removes directories that don't have recent simulation results.
        """
        try:
            # Get simulation directory using path manager
            simulation_dir = self.pm.get_simulation_dir(subject_id, 'Simulations')
            
            if not os.path.exists(simulation_dir):
                return
            
            # Get current time
            current_time = time.time()
            cutoff_time = current_time - (24 * 60 * 60)  # 24 hours ago
            
            for item in os.listdir(simulation_dir):
                item_path = os.path.join(simulation_dir, item)
                
                # Skip tmp directory and files
                if not os.path.isdir(item_path) or item == 'tmp':
                    continue
                
                # Check if directory is old and potentially stale
                try:
                    dir_mtime = os.path.getmtime(item_path)
                    
                    # If directory is older than cutoff and doesn't have recent TI results, consider removing
                    if dir_mtime < cutoff_time:
                        ti_mesh_path = os.path.join(item_path, 'TI', 'mesh')
                        
                        # Check if it has valid TI results
                        has_valid_results = False
                        if os.path.exists(ti_mesh_path):
                            for file in os.listdir(ti_mesh_path):
                                if file.endswith('_TI.msh') and os.path.getmtime(os.path.join(ti_mesh_path, file)) > cutoff_time:
                                    has_valid_results = True
                                    break
                        
                        # If no valid recent results, ask user if they want to clean up
                        if not has_valid_results:
                            self.update_output(f"Found old simulation directory: {item} (last modified: {datetime.datetime.fromtimestamp(dir_mtime).strftime('%Y-%m-%d %H:%M')})", 'info')
                            # For now, just warn - in the future could add cleanup logic
                            
                except Exception as e:
                    self.update_output(f"Warning: Could not check directory {item}: {e}", 'warning')
                    
        except Exception as e:
            self.update_output(f"Warning: Could not clean up old directories: {e}", 'warning')

class AddMontageDialog(QtWidgets.QDialog):
    """Dialog for adding new montages."""
    
    def __init__(self, parent=None):
        super(AddMontageDialog, self).__init__(parent)
        self.parent = parent
        # Get path manager from parent if available
        if parent and hasattr(parent, 'pm'):
            self.pm = parent.pm
        else:
            self.pm = get_path_manager()
        self.setup_ui()
        
        # Connect radio buttons to update electrode inputs
        self.mode_unipolar.toggled.connect(self.update_electrode_inputs)
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Add New Montage")
        self.setModal(True)
        self.resize(800, 500)  # Made wider to accommodate the side panel
        
        # Create main horizontal layout
        main_layout = QtWidgets.QHBoxLayout(self)
        
        # Left side (original form)
        left_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(left_widget)
        
        # Create form layout for better organization
        form_layout = QtWidgets.QFormLayout()
        
        # Montage name
        self.name_input = QtWidgets.QLineEdit()
        form_layout.addRow("Montage Name:", self.name_input)
        
        # Target EEG Net selection with Show Electrodes button
        net_layout = QtWidgets.QHBoxLayout()
        self.net_combo = QtWidgets.QComboBox()
        # Copy items from parent's EEG net combo
        if self.parent and hasattr(self.parent, 'eeg_net_combo'):
            for i in range(self.parent.eeg_net_combo.count()):
                self.net_combo.addItem(self.parent.eeg_net_combo.itemText(i))
        # Set current net to match parent's selection
        if self.parent and hasattr(self.parent, 'eeg_net_combo'):
            current_net = self.parent.eeg_net_combo.currentText()
            index = self.net_combo.findText(current_net)
            if index >= 0:
                self.net_combo.setCurrentIndex(index)
        
        self.show_electrodes_btn = QtWidgets.QPushButton("Show Electrodes")
        self.show_electrodes_btn.clicked.connect(self.toggle_electrode_list)
        net_layout.addWidget(self.net_combo)
        net_layout.addWidget(self.show_electrodes_btn)
        form_layout.addRow("Target EEG Net:", net_layout)
        
        # Add form layout to main layout
        layout.addLayout(form_layout)
        
        # Simulation mode (Unipolar/Multipolar)
        mode_group = QtWidgets.QGroupBox("Montage Type")
        mode_layout = QtWidgets.QHBoxLayout(mode_group)
        self.mode_unipolar = QtWidgets.QRadioButton("Unipolar")
        self.mode_multipolar = QtWidgets.QRadioButton("Multipolar")
        self.mode_unipolar.setChecked(True)  # Default to unipolar
        mode_layout.addWidget(self.mode_unipolar)
        mode_layout.addWidget(self.mode_multipolar)
        layout.addWidget(mode_group)
        
        # Create a stacked widget for electrode inputs
        self.electrode_stack = QtWidgets.QStackedWidget()
        
        # Unipolar electrode pairs (two pairs)
        uni_widget = QtWidgets.QWidget()
        uni_layout = QtWidgets.QVBoxLayout(uni_widget)
        
        # Add a label for the unipolar electrode section
        uni_label = QtWidgets.QLabel("Unipolar Electrode Pairs:")
        uni_label.setStyleSheet("font-weight: bold;")
        uni_layout.addWidget(uni_label)
        
        # Pair 1
        uni_pair1_layout = QtWidgets.QHBoxLayout()
        self.uni_pair1_label = QtWidgets.QLabel("Pair 1:")
        self.uni_pair1_e1 = QtWidgets.QLineEdit()
        self.uni_pair1_e1.setPlaceholderText("E10")
        self.uni_pair1_e2 = QtWidgets.QLineEdit()
        self.uni_pair1_e2.setPlaceholderText("E11")
        uni_pair1_layout.addWidget(self.uni_pair1_label)
        uni_pair1_layout.addWidget(self.uni_pair1_e1)
        uni_pair1_layout.addWidget(QtWidgets.QLabel("↔"))
        uni_pair1_layout.addWidget(self.uni_pair1_e2)
        uni_layout.addLayout(uni_pair1_layout)
        
        # Pair 2
        uni_pair2_layout = QtWidgets.QHBoxLayout()
        self.uni_pair2_label = QtWidgets.QLabel("Pair 2:")
        self.uni_pair2_e1 = QtWidgets.QLineEdit()
        self.uni_pair2_e1.setPlaceholderText("E12")
        self.uni_pair2_e2 = QtWidgets.QLineEdit()
        self.uni_pair2_e2.setPlaceholderText("E13")
        uni_pair2_layout.addWidget(self.uni_pair2_label)
        uni_pair2_layout.addWidget(self.uni_pair2_e1)
        uni_pair2_layout.addWidget(QtWidgets.QLabel("↔"))
        uni_pair2_layout.addWidget(self.uni_pair2_e2)
        uni_layout.addLayout(uni_pair2_layout)
        
        # Multipolar electrode pairs (four pairs)
        multi_widget = QtWidgets.QWidget()
        multi_layout = QtWidgets.QVBoxLayout(multi_widget)
        
        # Add a label for the multipolar electrode section
        multi_label = QtWidgets.QLabel("Multipolar Electrode Pairs:")
        multi_label.setStyleSheet("font-weight: bold;")
        multi_layout.addWidget(multi_label)
        
        # Create pairs for multipolar mode
        self.multi_pairs = []
        for i in range(1, 5):
            pair_layout = QtWidgets.QHBoxLayout()
            pair_label = QtWidgets.QLabel(f"Pair {i}:")
            e1 = QtWidgets.QLineEdit()
            e1.setPlaceholderText(f"E{10+2*(i-1)}")
            e2 = QtWidgets.QLineEdit()
            e2.setPlaceholderText(f"E{11+2*(i-1)}")
            
            pair_layout.addWidget(pair_label)
            pair_layout.addWidget(e1)
            pair_layout.addWidget(QtWidgets.QLabel("↔"))
            pair_layout.addWidget(e2)
            multi_layout.addLayout(pair_layout)
            
            # Store references
            self.multi_pairs.append((e1, e2))
        
        # Add the widgets to the stacked widget
        self.electrode_stack.addWidget(uni_widget)
        self.electrode_stack.addWidget(multi_widget)
        layout.addWidget(self.electrode_stack)
        
        # Add some spacing
        layout.addSpacing(10)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Add left widget to main layout
        main_layout.addWidget(left_widget)
        
        # Right side (electrode list panel)
        self.right_widget = QtWidgets.QWidget()
        self.right_widget.setVisible(False)  # Initially hidden
        right_layout = QtWidgets.QVBoxLayout(self.right_widget)
        
        # Add title for electrode list
        electrode_title = QtWidgets.QLabel("Available Electrodes")
        electrode_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(electrode_title)
        
        # Add search box
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search electrodes...")
        self.search_box.textChanged.connect(self.filter_electrodes)
        right_layout.addWidget(self.search_box)
        
        # Add electrode list widget
        self.electrode_list = QtWidgets.QListWidget()
        self.electrode_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.electrode_list.setStyleSheet("""
            QListWidget {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #eee;
            }
        """)
        right_layout.addWidget(self.electrode_list)
        
        # Add right widget to main layout
        main_layout.addWidget(self.right_widget)
        
        # Connect net selection change to update electrode list
        self.net_combo.currentTextChanged.connect(self.update_electrode_list)
    
    def toggle_electrode_list(self):
        """Toggle the visibility of the electrode list panel."""
        if self.right_widget.isVisible():
            self.right_widget.setVisible(False)
            self.show_electrodes_btn.setText("Show Electrodes")
            self.resize(500, self.height())  # Return to original width
        else:
            self.right_widget.setVisible(True)
            self.show_electrodes_btn.setText("Hide Electrodes")
            self.resize(800, self.height())  # Expand width
            self.update_electrode_list()
    
    def update_electrode_list(self):
        """Update the list of available electrodes based on the selected net."""
        try:
            self.electrode_list.clear()
            net_file = self.net_combo.currentText()
            
            # Get SimNIBS directory using path manager
            simnibs_dir = self.pm.get_simnibs_dir()
            if not simnibs_dir:
                return
            subject_found = False
            
            # Look through all subject directories
            for subject_dir in os.listdir(simnibs_dir):
                if subject_dir.startswith('sub-'):
                    subject_id = subject_dir[4:]  # Remove 'sub-' prefix
                    m2m_dir = self.pm.get_m2m_dir(subject_id)
                    if m2m_dir and os.path.isdir(m2m_dir):
                        eeg_file = os.path.join(m2m_dir, 'eeg_positions', net_file)
                        if os.path.exists(eeg_file):
                            subject_found = True
                            # Read the CSV file
                            with open(eeg_file, 'r') as f:
                                lines = f.readlines()
                                electrodes = []
                                for line in lines:
                                    parts = line.strip().split(',')
                                    if len(parts) >= 5:  # Ensure we have enough columns
                                        electrode_type = parts[0]
                                        electrode_name = parts[4]
                                        if electrode_type in ["Electrode", "ReferenceElectrode"]:
                                            electrodes.append(electrode_name)
                            
                            # Sort electrodes alphabetically
                            electrodes.sort()
                            
                            # Add to list widget
                            for electrode in electrodes:
                                self.electrode_list.addItem(electrode)
                            break
            
            if not subject_found:
                self.electrode_list.addItem("No electrode positions found")
        
        except Exception as e:
            self.electrode_list.addItem(f"Error loading electrodes: {str(e)}")
    
    def filter_electrodes(self, text):
        """Filter the electrode list based on search text."""
        for i in range(self.electrode_list.count()):
            item = self.electrode_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())
    
    def get_montage_data(self):
        """Get montage data entered in the dialog."""
        name = self.name_input.text().strip()
        is_unipolar = self.mode_unipolar.isChecked()
        target_net = self.net_combo.currentText()
        
        electrode_pairs = []
        
        if is_unipolar:
            # Get unipolar pairs
            pair1_e1 = self.uni_pair1_e1.text().strip()
            pair1_e2 = self.uni_pair1_e2.text().strip()
            pair2_e1 = self.uni_pair2_e1.text().strip()
            pair2_e2 = self.uni_pair2_e2.text().strip()
            
            if pair1_e1 and pair1_e2:
                electrode_pairs.append([pair1_e1, pair1_e2])
            if pair2_e1 and pair2_e2:
                electrode_pairs.append([pair2_e1, pair2_e2])
        else:
            # Get multipolar pairs
            for e1, e2 in self.multi_pairs:
                e1_text = e1.text().strip()
                e2_text = e2.text().strip()
                if e1_text and e2_text:
                    electrode_pairs.append([e1_text, e2_text])
        
        return {
            "name": name,
            "is_unipolar": is_unipolar,
            "target_net": target_net,
            "electrode_pairs": electrode_pairs
        }

    def update_electrode_inputs(self, checked):
        """Update the electrode input view based on the selected mode."""
        if checked:  # Unipolar selected
            self.electrode_stack.setCurrentIndex(0)
        else:  # Multipolar selected
            self.electrode_stack.setCurrentIndex(1) 

class ConductivityEditorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, custom_conductivities=None):
        super(ConductivityEditorDialog, self).__init__(parent)
        self.setWindowTitle("Tissue Conductivity Editor")
        # Use integer keys for tissue numbers
        self.custom_conductivities = {int(k): v for k, v in (custom_conductivities or {}).items()}
        self.setup_ui()
        
    def setup_ui(self):
        # Remove fixed size, use resize and minimum size for flexibility
        self.resize(900, 480)
        self.setMinimumSize(800, 400)
        
        # Main layout, no margins or spacing
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Info label
        info_label = QtWidgets.QLabel("Double-click on a value in the 'Value (S/m)' column to edit it.")
        info_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                color: #333;
                padding: 4px 8px 4px 8px;
                border-bottom: 1px solid #ddd;
                font-style: italic;
            }
        """)
        layout.addWidget(info_label)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Tissue Number", "Tissue Name", "Value (S/m)", "Reference"])
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        
        self.tissue_data = [
            (1, "White Matter", 0.126, "Wagner et al., 2004"),
            (2, "Gray Matter", 0.275, "Wagner et al., 2004"),
            (3, "CSF", 1.654, "Wagner et al., 2004"),
            (4, "Bone", 0.01, "Wagner et al., 2004"),
            (5, "Scalp", 0.465, "Wagner et al., 2004"),
            (6, "Eye balls", 0.5, "Opitz et al., 2015"),
            (7, "Compact Bone", 0.008, "Opitz et al., 2015"),
            (8, "Spongy Bone", 0.025, "Opitz et al., 2015"),
            (9, "Blood", 0.6, "Gabriel et al., 2009"),
            (10, "Muscle", 0.16, "Gabriel et al., 2009"),
            (100, "Silicone Rubber", 29.4, "NeuroConn electrodes: Wacker Elastosil R 570/60 RUSS"),
            (500, "Saline", 1.0, "Saturnino et al., 2015")
        ]
        self.table.setRowCount(len(self.tissue_data))
        for row, (number, name, value, ref) in enumerate(self.tissue_data):
            item = QtWidgets.QTableWidgetItem(str(number))
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(name)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 1, item)
            item = QtWidgets.QTableWidgetItem(str(value))
            item.setBackground(QtGui.QColor("#f0f8ff"))
            self.table.setItem(row, 2, item)
            item = QtWidgets.QTableWidgetItem(ref)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 3, item)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f5f5f5;
                selection-background-color: #2196F3;
                selection-color: white;
                gridline-color: #e0e0e0;
                border: none;
            }
            QHeaderView::section {
                background-color: #4a4a4a;
                color: white;
                padding: 4px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 1px;
                font-size: 11px;
            }
        """)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(28)
        layout.addWidget(self.table)
        
        # Button container
        button_container = QtWidgets.QWidget()
        button_container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        button_container.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                border-top: 1px solid #ddd;
            }
            QPushButton {
                min-width: 100px;
                padding: 6px 12px;
                margin: 6px;
                background-color: #ffffff;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
            }
        """)
        button_layout = QtWidgets.QHBoxLayout(button_container)
        button_layout.setContentsMargins(10, 0, 10, 0)
        button_layout.setSpacing(0)
        save_btn = QtWidgets.QPushButton("Save")
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(cancel_btn)
        save_btn.clicked.connect(self.save_conductivities)
        reset_btn.clicked.connect(self.reset_to_defaults)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(button_container)

        # After populating the table, override values with custom_conductivities if present
        for row, (number, name, value, ref) in enumerate(self.tissue_data):
            if self.custom_conductivities.get(number) is not None:
                self.table.item(row, 2).setText(str(self.custom_conductivities[number]))

    def save_conductivities(self):
        """Save the modified conductivity values."""
        modified_values = {}
        for row in range(self.table.rowCount()):
            tissue_num = int(self.table.item(row, 0).text())
            try:
                value = float(self.table.item(row, 2).text())
                if value <= 0:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Invalid Value",
                        f"Conductivity value for tissue {tissue_num} must be positive."
                    )
                    return
                modified_values[tissue_num] = value
                os.environ[f"TISSUE_COND_{tissue_num}"] = str(value)
            except ValueError:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Value",
                    f"Invalid conductivity value for tissue {tissue_num}. Please enter a valid number."
                )
                return
        self.custom_conductivities = modified_values
        self.accept()
    
    def reset_to_defaults(self):
        """Reset all values to their defaults."""
        for row, (number, _, value, _) in enumerate(self.tissue_data):
            self.table.item(row, 2).setText(str(value))

    def get_conductivities(self):
        return self.custom_conductivities.copy() 
