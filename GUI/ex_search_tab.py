#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Ex-Search Tab
This module provides a GUI interface for the ex-search optimization functionality.
"""

import os
import json
import re
import subprocess
import csv
import time
import logging
from PyQt5 import QtWidgets, QtCore, QtGui
from confirmation_dialog import ConfirmationDialog
try:
    from .utils import confirm_overwrite, is_verbose_message, is_important_message
except ImportError:
    # Fallback for when running as standalone script
    import os
    import sys
    gui_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, gui_dir)
    from utils import confirm_overwrite, is_verbose_message, is_important_message

class ExSearchThread(QtCore.QThread):
    """Thread to run ex-search optimization in background to prevent GUI freezing."""
    
    # Signal to emit output text with message type
    output_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None):
        """Initialize the thread with the command to run and environment variables."""
        super(ExSearchThread, self).__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False
        self.input_data = None
        
    def set_input_data(self, input_data):
        """Set input data to be passed to the process."""
        self.input_data = input_data
        
    def run(self):
        """Run the ex-search command in a separate thread."""
        try:
            # Debug: show command and environment highlights
            try:
                dbg_env = {k: self.env.get(k) for k in ["PROJECT_DIR_NAME", "SUBJECT_NAME", "SELECTED_EEG_NET", "TI_LOG_FILE", "LEADFIELD_HDF", "ROI_NAME"]}
                self.output_signal.emit(f"[DEBUG] Launching process: {' '.join(self.cmd)}", 'debug')
                self.output_signal.emit(f"[DEBUG] Env highlights: {dbg_env}", 'debug')
            except Exception:
                pass
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,  # Combine stderr with stdout to prevent blocking
                stdin=subprocess.PIPE if self.input_data else None,
                universal_newlines=True,
                bufsize=1,
                env=self.env
            )
            try:
                self.output_signal.emit(f"[DEBUG] Spawned PID: {self.process.pid}", 'debug')
            except Exception:
                pass
            
            # If input data is provided, send it to the process
            if self.input_data:
                self.output_signal.emit("[DEBUG] Sending stdin to child process", 'debug')
                for line in self.input_data:
                    if self.terminated:
                        break
                    self.process.stdin.write(line + '\n')
                    self.process.stdin.flush()
                self.process.stdin.close()
            
            # Real-time output display with message type detection
            for line in iter(self.process.stdout.readline, ''):
                if self.terminated:
                    break
                if line:
                    # Detect message type based on content
                    line_stripped = line.strip()
                    if any(keyword in line_stripped.lower() for keyword in ['error:', 'critical:', 'failed', 'exception']):
                        message_type = 'error'
                    elif any(keyword in line_stripped.lower() for keyword in ['warning:', 'warn']):
                        message_type = 'warning'
                    elif any(keyword in line_stripped.lower() for keyword in ['debug:']):
                        message_type = 'debug'
                    elif any(keyword in line_stripped.lower() for keyword in ['executing:', 'running', 'command']):
                        message_type = 'command'
                    elif any(keyword in line_stripped.lower() for keyword in ['completed successfully', 'completed.', 'successfully', 'completed:']):
                        message_type = 'success'
                    elif any(keyword in line_stripped.lower() for keyword in ['processing', 'starting']):
                        message_type = 'info'
                    else:
                        message_type = 'default'
                    
                    self.output_signal.emit(line_stripped, message_type)
            
            # Check process completion
            if not self.terminated:
                returncode = self.process.wait()
                self.output_signal.emit(f"[DEBUG] Process exited with code {returncode}", 'debug')
                if returncode != 0:
                    self.error_signal.emit(f"Process returned non-zero exit code: {returncode}")
                    
        except Exception as e:
            try:
                import traceback
                tb = traceback.format_exc()
                self.error_signal.emit(f"Error running process: {str(e)}\n{tb}")
                self.output_signal.emit(f"[DEBUG] Exception in ExSearchThread.run: {str(e)}", 'debug')
            except Exception:
                self.error_signal.emit(f"Error running process: {str(e)}")
        finally:
            # Ensure process is cleaned up
            if self.process:
                try:
                    self.process.stdout.close()
                    if self.process.stdin:
                        self.process.stdin.close()
                except:
                    pass
    
    def terminate_process(self):
        """Terminate the running process."""
        if self.process and self.process.poll() is None:
            self.terminated = True
            if os.name == 'nt':  # Windows
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:  # Unix/Linux/Mac
                import signal
                try:
                    parent_pid = self.process.pid
                    ps_output = subprocess.check_output(f"ps -o pid --ppid {parent_pid} --noheaders", shell=True)
                    child_pids = [int(pid) for pid in ps_output.decode().strip().split('\n') if pid]
                    for pid in child_pids:
                        os.kill(pid, signal.SIGTERM)
                except:
                    pass
                
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            
            return True
        return False

class ExSearchTab(QtWidgets.QWidget):
    """Tab for ex-search optimization functionality."""
    
    def __init__(self, parent=None):
        super(ExSearchTab, self).__init__(parent)
        self.parent = parent
        self.optimization_running = False
        self.optimization_process = None
        # Initialize debug mode (default to False)
        self.debug_mode = False
        
        # Summary mode variables
        self.SUMMARY_MODE = True  # Default to summary mode
        self.EXSEARCH_START_TIME = None
        self.ROI_START_TIMES = {}
        self.STEP_START_TIMES = {}
        
        self.setup_ui()
        
        # Initialize with available subjects and check leadfields
        QtCore.QTimer.singleShot(500, self.initial_setup)
    
    def set_summary_mode(self, enabled):
        """Enable or disable summary mode."""
        self.SUMMARY_MODE = enabled
    
    def format_duration(self, start_time):
        """Format duration from start time to now."""
        if not start_time:
            return "0s"
        duration = time.time() - start_time
        if duration < 60:
            return f"{int(duration)}s"
        elif duration < 3600:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    def log_exsearch_start(self, subject_id, roi_count):
        """Log the start of ex-search optimization."""
        if not self.SUMMARY_MODE:
            return
        
        self.EXSEARCH_START_TIME = time.time()
        self.ROI_START_TIMES = {}
        self.STEP_START_TIMES = {}
        
        self.update_output(f"Beginning ex-search optimization for subject: {subject_id} ({roi_count} ROI(s))", 'info')
    
    def log_roi_start(self, roi_index, total_rois, roi_name):
        """Log the start of ROI processing."""
        if not self.SUMMARY_MODE:
            return
        
        roi_key = f"roi_{roi_index}"
        self.ROI_START_TIMES[roi_key] = time.time()
        
        self.update_output(f"├─ Processing ROI {roi_index + 1}/{total_rois}: {roi_name}", 'info')
    
    def log_step_start(self, step_name):
        """Log the start of a processing step."""
        if not self.SUMMARY_MODE:
            return
        
        step_key = step_name.lower().replace(' ', '_')
        self.STEP_START_TIMES[step_key] = time.time()
    
    def log_step_complete(self, step_name, success=True):
        """Log the completion of a processing step."""
        if not self.SUMMARY_MODE:
            return
        
        step_key = step_name.lower().replace(' ', '_')
        start_time = self.STEP_START_TIMES.get(step_key)
        
        if start_time:
            duration = self.format_duration(start_time)
            status = "✓ Complete" if success else "✗ Failed"
            self.update_output(f"├─ {step_name}: {status} ({duration})", 'success' if success else 'error')
        else:
            status = "✓ Complete" if success else "✗ Failed"
            self.update_output(f"├─ {step_name}: {status}", 'success' if success else 'error')
    
    def log_roi_complete(self, roi_index, total_rois, roi_name):
        """Log the completion of ROI processing."""
        if not self.SUMMARY_MODE:
            return
        
        roi_key = f"roi_{roi_index}"
        start_time = self.ROI_START_TIMES.get(roi_key)
        
        if start_time:
            duration = self.format_duration(start_time)
            self.update_output(f"├─ ROI {roi_index + 1}/{total_rois} ({roi_name}): ✓ Complete ({duration})", 'success')
        else:
            self.update_output(f"├─ ROI {roi_index + 1}/{total_rois} ({roi_name}): ✓ Complete", 'success')
    
    def log_optimization_run_start(self, run_number, total_runs):
        """Log the start of an optimization run."""
        if not self.SUMMARY_MODE:
            return
        
        self.update_output(f"├─ Optimization run {run_number}/{total_runs}: Starting...", 'info')
    
    def log_optimization_run_complete(self, run_number, total_runs, duration):
        """Log the completion of an optimization run."""
        if not self.SUMMARY_MODE:
            return
        
        self.update_output(f"├─ Optimization run {run_number}/{total_runs}: ✓ Complete ({duration})", 'success')
    
    def log_exsearch_complete(self, subject_id, total_rois, output_dir):
        """Log the completion of ex-search optimization."""
        if not self.SUMMARY_MODE:
            return
        
        if self.EXSEARCH_START_TIME:
            total_duration = self.format_duration(self.EXSEARCH_START_TIME)
            self.update_output(f"└─ Ex-search optimization completed successfully for subject: {subject_id} ({total_rois} ROI(s), Total: {total_duration})", 'success')
            self.update_output(f"   Results available in: {output_dir}", 'success')
        else:
            self.update_output(f"└─ Ex-search optimization completed successfully for subject: {subject_id} ({total_rois} ROI(s))", 'success')
            self.update_output(f"   Results available in: {output_dir}", 'success')
    
    def create_log_file_env(self, process_name, subject_id):
        """Create log file environment variable for processes."""
        try:
            # Create timestamp for log file
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            
            # Get project directory structure
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            derivatives_dir = os.path.join(project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'logs', f'sub-{subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file path
            log_file = os.path.join(log_dir, f'{process_name}_{time_stamp}.log')
            
            return log_file
            
        except Exception as e:
            self.update_output(f"Warning: Could not create log file: {str(e)}", 'warning')
            return None
    
    def log_pipeline_configuration(self, subject_id, project_dir, selected_net_name, selected_hdf5_path, env):
        """Log comprehensive pipeline configuration to the ex-search log file."""
        try:
            
            # Get the log file from environment
            log_file = env.get("TI_LOG_FILE")
            if not log_file:
                return
                
            # Create a file-only logger for configuration details (no console output)
            config_logger = logging.getLogger('Ex-Search-Config-File-Only')
            config_logger.setLevel(logging.INFO)
            config_logger.propagate = False
            
            # Remove any existing handlers
            for handler in list(config_logger.handlers):
                config_logger.removeHandler(handler)
            
            # Add only file handler (no console handler)
            file_handler = logging.FileHandler(log_file, mode='a')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(
                '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            config_logger.addHandler(file_handler)
            
            # Log header
            config_logger.info("="*80)
            config_logger.info("EX-SEARCH PIPELINE CONFIGURATION")
            config_logger.info("="*80)
            
            # Subject and project information
            config_logger.info(f"Subject ID: {subject_id}")
            config_logger.info(f"Project Directory: {project_dir}")
            config_logger.info(f"Project Name: {os.environ.get('PROJECT_DIR_NAME', 'Unknown')}")
            
            # Leadfield information
            config_logger.info(f"Selected EEG Net: {selected_net_name}")
            config_logger.info(f"Leadfield HDF5 Path: {selected_hdf5_path}")
            try:
                file_size = os.path.getsize(selected_hdf5_path) / (1024**3)  # GB
                config_logger.info(f"Leadfield File Size: {file_size:.2f} GB")
            except:
                config_logger.info("Leadfield File Size: Unable to determine")
            
            # ROI information
            roi_count = len(self.roi_processing_queue)
            config_logger.info(f"Number of ROIs to process: {roi_count}")
            config_logger.info(f"ROI files: {', '.join(self.roi_processing_queue)}")
            
            # Electrode configuration
            config_logger.info("Electrode Configuration:")
            config_logger.info(f"  E1+ electrodes: {', '.join(self.e1_plus)}")
            config_logger.info(f"  E1- electrodes: {', '.join(self.e1_minus)}")
            config_logger.info(f"  E2+ electrodes: {', '.join(self.e2_plus)}")
            config_logger.info(f"  E2- electrodes: {', '.join(self.e2_minus)}")
            config_logger.info(f"  Total electrode combinations: {len(self.e1_plus)} per category")
            
            # Environment variables (important ones)
            config_logger.info("Key Environment Variables:")
            important_vars = [
                'PROJECT_DIR_NAME', 'PROJECT_DIR', 'SUBJECT_NAME', 'SUBJECTS_DIR',
                'LEADFIELD_HDF', 'SELECTED_EEG_NET', 'TI_LOG_FILE'
            ]
            for var in important_vars:
                value = env.get(var, 'Not set')
                config_logger.info(f"  {var}: {value}")
            
            # System information
            import platform
            import time
            config_logger.info("System Information:")
            config_logger.info(f"  Platform: {platform.system()} {platform.release()}")
            config_logger.info(f"  Python Version: {platform.python_version()}")
            config_logger.info(f"  Start Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Pipeline steps
            config_logger.info("Pipeline Steps:")
            config_logger.info("  1. TI Simulation (ti_sim.py)")
            config_logger.info("  2. ROI Analysis (roi-analyzer.py)")
            config_logger.info("  3. Mesh Processing (mesh_field_analyzer.py)")
            
            config_logger.info("="*80)
            
        except Exception as e:
            self.update_output(f"Warning: Could not log configuration details: {str(e)}", 'warning')
    
    def log_roi_configuration(self, current_roi, roi_name, x, y, z, env):
        """Log ROI-specific configuration details."""
        try:
            
            # Get the log file from environment
            log_file = env.get("TI_LOG_FILE")
            if not log_file:
                return
                
            # Create a file-only logger for ROI details (no console output)
            roi_logger = logging.getLogger('Ex-Search-ROI-File-Only')
            roi_logger.setLevel(logging.INFO)
            roi_logger.propagate = False
            
            # Remove any existing handlers
            for handler in list(roi_logger.handlers):
                roi_logger.removeHandler(handler)
            
            # Add only file handler (no console handler)
            file_handler = logging.FileHandler(log_file, mode='a')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(
                '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            roi_logger.addHandler(file_handler)
            
            # Log ROI processing details
            roi_index = self.current_roi_index + 1
            total_rois = len(self.roi_processing_queue)
            
            roi_logger.info("-" * 60)
            roi_logger.info(f"PROCESSING ROI {roi_index}/{total_rois}: {current_roi}")
            roi_logger.info("-" * 60)
            roi_logger.info(f"ROI File: {current_roi}")
            roi_logger.info(f"ROI Name (clean): {roi_name}")
            roi_logger.info(f"ROI Coordinates (RAS): x={x}, y={y}, z={z}")
            roi_logger.info(f"Output Directory: {roi_name}_{env.get('SELECTED_EEG_NET', 'unknown')}")
            
            # Log ROI-specific environment variables
            roi_specific_vars = ['ROI_NAME', 'ROI_COORDINATES', 'SELECTED_ROI_FILE', 'ROI_DIR']
            for var in roi_specific_vars:
                value = env.get(var, 'Not set')
                roi_logger.info(f"  {var}: {value}")
            
            roi_logger.info(f"Processing steps for this ROI:")
            roi_logger.info(f"  1. TI Simulation → {roi_name}_{env.get('SELECTED_EEG_NET', 'unknown')}/")
            roi_logger.info(f"  2. ROI Analysis → Extract TImax/TImean at coordinates")
            roi_logger.info(f"  3. Mesh Processing → Generate final analysis CSV")
            roi_logger.info("-" * 60)
            
        except Exception as e:
            self.update_output(f"Warning: Could not log ROI configuration: {str(e)}", 'warning')
    
    def log_pipeline_completion(self):
        """Log pipeline completion summary."""
        try:
            import time
            
            # Try to get log file from the last environment
            # This is a bit tricky since env might not be available, so we'll reconstruct it
            subject_id = self.subject_combo.currentText()
            if not subject_id:
                return
                
            # Create log file path same way as before
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            derivatives_dir = os.path.join(project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'logs', f'sub-{subject_id}')
            
            # Find the most recent ex_search log file
            if os.path.exists(log_dir):
                ex_search_logs = [f for f in os.listdir(log_dir) if f.startswith('ex_search_') and f.endswith('.log')]
                if ex_search_logs:
                    # Use the most recent log file
                    latest_log = os.path.join(log_dir, sorted(ex_search_logs)[-1])
                    
                    # Create a file-only logger for completion details (no console output)
                    completion_logger = logging.getLogger('Ex-Search-Completion-File-Only')
                    completion_logger.setLevel(logging.INFO)
                    completion_logger.propagate = False
                    
                    # Remove any existing handlers
                    for handler in list(completion_logger.handlers):
                        completion_logger.removeHandler(handler)
                    
                    # Add only file handler (no console handler)
                    file_handler = logging.FileHandler(latest_log, mode='a')
                    file_handler.setLevel(logging.INFO)
                    file_handler.setFormatter(logging.Formatter(
                        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S'
                    ))
                    completion_logger.addHandler(file_handler)
                    
                    # Log completion summary
                    completion_logger.info("="*80)
                    completion_logger.info("EX-SEARCH PIPELINE COMPLETION SUMMARY")
                    completion_logger.info("="*80)
                    completion_logger.info(f"End Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    completion_logger.info(f"Subject: {subject_id}")
                    completion_logger.info(f"Total ROIs Processed: {len(self.roi_processing_queue)}")
                    
                    # List all processed ROIs and their output directories
                    if hasattr(self, 'roi_processing_queue'):
                        completion_logger.info("Processed ROIs:")
                        for i, roi_file in enumerate(self.roi_processing_queue):
                            roi_name = roi_file.replace('.csv', '')
                            # Try to get EEG net name (might be stored in environment or reconstruct)
                            try:
                                selected_items = self.leadfield_list.selectedItems()
                                if selected_items and selected_items[0].data(QtCore.Qt.UserRole):
                                    eeg_net = selected_items[0].data(QtCore.Qt.UserRole)["net_name"]
                                    output_dir = f"{roi_name}_{eeg_net}"
                                    completion_logger.info(f"  {i+1}. {roi_file} → ex-search/{output_dir}/")
                                else:
                                    completion_logger.info(f"  {i+1}. {roi_file}")
                            except:
                                completion_logger.info(f"  {i+1}. {roi_file}")
                    
                    # Log electrode configuration summary
                    if hasattr(self, 'e1_plus') and hasattr(self, 'e1_minus'):
                        completion_logger.info("Electrode Configuration:")
                        completion_logger.info(f"  Total electrode combinations per ROI: {len(self.e1_plus)}")
                        completion_logger.info(f"  Total simulations completed: {len(self.roi_processing_queue) * len(self.e1_plus)}")
                    
                    # Note where results can be found
                    completion_logger.info("Output Location:")
                    completion_logger.info(f"  Results stored in: {project_dir}/derivatives/SimNIBS/sub-{subject_id}/ex-search/")
                    completion_logger.info("  Each ROI has its own directory with analysis results")
                    completion_logger.info("  Look for final_output.csv in each ROI's analysis/ subdirectory")
                    
                    completion_logger.info("="*80)
                    completion_logger.info("Ex-search pipeline completed successfully!")
                    completion_logger.info("="*80)
            
        except Exception as e:
            self.update_output(f"Warning: Could not log completion summary: {str(e)}", 'warning')
        
    def setup_ui(self):
        """Set up the user interface for the ex-search tab."""
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
                min-height: 10px;
                max-height: 10px;
            }
        """)
        self.status_label.setAlignment(QtCore.Qt.AlignVCenter)
        self.status_label.hide()  # Initially hidden
        main_layout.addWidget(self.status_label)
        
        # Create a scroll area for the form (matching other tabs)
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        scroll_layout.setSpacing(10)
        
        # Main horizontal layout to separate left and right
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        main_horizontal_layout.setSpacing(15)  # Add some spacing between left and right sides
        
        # Left side layout for Subject + Leadfield Management
        left_layout = QtWidgets.QVBoxLayout()
        
        # Subject selection
        subject_container = QtWidgets.QGroupBox("Subject Selection")
        subject_container.setFixedHeight(100)  # Fixed height for balance
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        subject_layout.setContentsMargins(10, 10, 10, 10)
        subject_layout.setSpacing(8)
        
        # Combo box for subject selection
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.setFixedHeight(30)
        subject_layout.addWidget(self.subject_combo)
        
        # Subject control buttons
        subject_button_layout = QtWidgets.QHBoxLayout()
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.setFixedHeight(25)
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        self.clear_subject_selection_btn = QtWidgets.QPushButton("Clear")
        self.clear_subject_selection_btn.setFixedHeight(25)
        self.clear_subject_selection_btn.clicked.connect(self.clear_subject_selection)
        
        subject_button_layout.addWidget(self.list_subjects_btn)
        subject_button_layout.addWidget(self.clear_subject_selection_btn)
        subject_layout.addLayout(subject_button_layout)
        
        # Add subject container to left layout
        left_layout.addWidget(subject_container)
        
        # Leadfield Management (moved from right to left under subject)
        leadfield_container = QtWidgets.QGroupBox("Leadfield Management")
        leadfield_container.setFixedHeight(240)  # Fixed height for balance
        leadfield_layout = QtWidgets.QVBoxLayout(leadfield_container)
        leadfield_layout.setContentsMargins(10, 10, 10, 10)
        leadfield_layout.setSpacing(8)
        
        # Available leadfields section
        available_label = QtWidgets.QLabel("Available Leadfields:")
        available_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        leadfield_layout.addWidget(available_label)
        
        # Leadfield list
        self.leadfield_list = QtWidgets.QListWidget()
        self.leadfield_list.setFixedHeight(140)  # Fixed height to control layout
        self.leadfield_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        leadfield_layout.addWidget(self.leadfield_list)
        
        # Selected leadfield info
        self.selected_leadfield_label = QtWidgets.QLabel("Selected: None")
        self.selected_leadfield_label.setStyleSheet("color: #666; font-style: italic; margin: 5px 0;")
        leadfield_layout.addWidget(self.selected_leadfield_label)
        
        # Leadfield action buttons
        leadfield_buttons_layout = QtWidgets.QHBoxLayout()
        
        self.refresh_leadfields_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_leadfields_btn.setFixedHeight(25)
        self.refresh_leadfields_btn.clicked.connect(self.refresh_leadfields)
        leadfield_buttons_layout.addWidget(self.refresh_leadfields_btn)
        
        self.show_electrodes_leadfield_btn = QtWidgets.QPushButton("Show Electrodes")
        self.show_electrodes_leadfield_btn.setFixedHeight(25)
        self.show_electrodes_leadfield_btn.setEnabled(False)  # Initially disabled
        self.show_electrodes_leadfield_btn.clicked.connect(self.show_electrodes_for_selected_leadfield)
        leadfield_buttons_layout.addWidget(self.show_electrodes_leadfield_btn)
        
        self.create_leadfield_btn = QtWidgets.QPushButton("Create New")
        self.create_leadfield_btn.setFixedHeight(25)
        self.create_leadfield_btn.clicked.connect(self.show_create_leadfield_dialog)
        leadfield_buttons_layout.addWidget(self.create_leadfield_btn)
        
        leadfield_layout.addLayout(leadfield_buttons_layout)
        
        # Connect leadfield selection
        self.leadfield_list.itemSelectionChanged.connect(self.on_leadfield_selection_changed)
        
        # Add leadfield container to left layout
        left_layout.addWidget(leadfield_container)
        
        # Right side layout for Electrodes + ROI
        right_layout = QtWidgets.QVBoxLayout()
        
        # Electrode selection
        electrode_container = QtWidgets.QGroupBox("Electrode Selection")
        electrode_container.setFixedHeight(180)  # Fixed height for balance
        electrode_layout = QtWidgets.QFormLayout(electrode_container)
        electrode_layout.setContentsMargins(10, 10, 10, 10)
        electrode_layout.setSpacing(8)
        
        # Create input fields for each electrode category
        self.e1_plus_input = QtWidgets.QLineEdit()
        self.e1_minus_input = QtWidgets.QLineEdit()
        self.e2_plus_input = QtWidgets.QLineEdit()
        self.e2_minus_input = QtWidgets.QLineEdit()
        
        # Set fixed height for input fields
        for input_field in [self.e1_plus_input, self.e1_minus_input, self.e2_plus_input, self.e2_minus_input]:
            input_field.setFixedHeight(30)
        
        # Set placeholders
        self.e1_plus_input.setPlaceholderText("E.g., O1, F7")
        self.e1_minus_input.setPlaceholderText("E.g., Fp1, T7")
        self.e2_plus_input.setPlaceholderText("E.g., T8, P4")
        self.e2_minus_input.setPlaceholderText("E.g., Fz, Cz")
        
        # Add input fields to layout with labels
        electrode_layout.addRow("E1+ electrodes:", self.e1_plus_input)
        electrode_layout.addRow("E1- electrodes:", self.e1_minus_input)
        electrode_layout.addRow("E2+ electrodes:", self.e2_plus_input)
        electrode_layout.addRow("E2- electrodes:", self.e2_minus_input)
        
        # Add help text
        help_label = QtWidgets.QLabel("Enter electrode names separated by commas. All categories must have the same number of electrodes.")
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        electrode_layout.addRow(help_label)
        
        # Add electrode container to right layout
        right_layout.addWidget(electrode_container)
        
        # ROI selection (moved from left to right under electrodes)
        roi_container = QtWidgets.QGroupBox("ROI Selection")
        roi_container.setFixedHeight(160)  # Fixed height for balance (total = 340 to match left side)
        roi_layout = QtWidgets.QVBoxLayout(roi_container)
        roi_layout.setContentsMargins(10, 10, 10, 10)
        roi_layout.setSpacing(8)
        
        # List widget for ROI selection
        self.roi_list = QtWidgets.QListWidget()
        self.roi_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.roi_list.setFixedHeight(80)  # Adjusted to fit within ROI container
        roi_layout.addWidget(self.roi_list)
        
        # ROI control buttons
        roi_button_layout = QtWidgets.QHBoxLayout()
        self.add_roi_btn = QtWidgets.QPushButton("Add ROI")
        self.add_roi_btn.setFixedHeight(25)
        self.add_roi_btn.clicked.connect(self.show_add_roi_dialog)
        self.remove_roi_btn = QtWidgets.QPushButton("Remove ROI")
        self.remove_roi_btn.setFixedHeight(25)
        self.remove_roi_btn.clicked.connect(self.remove_selected_roi)
        self.list_rois_btn = QtWidgets.QPushButton("Refresh List")
        self.list_rois_btn.setFixedHeight(25)
        self.list_rois_btn.clicked.connect(self.update_roi_list)
        
        roi_button_layout.addWidget(self.add_roi_btn)
        roi_button_layout.addWidget(self.remove_roi_btn)
        roi_button_layout.addWidget(self.list_rois_btn)
        roi_layout.addLayout(roi_button_layout)
        
        # Add ROI container to right layout
        right_layout.addWidget(roi_container)
        
        # Add left and right layouts to main horizontal layout with equal widths
        main_horizontal_layout.addLayout(left_layout, 1)    # 50% width
        main_horizontal_layout.addLayout(right_layout, 1)   # 50% width
        
        # Add main horizontal layout to scroll layout
        scroll_layout.addLayout(main_horizontal_layout)
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # --- Console and Buttons Section ---
        output_label = QtWidgets.QLabel("Output:")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        
        # Console buttons layout
        console_buttons_layout = QtWidgets.QHBoxLayout()
        
        # Run button
        self.run_btn = QtWidgets.QPushButton("Run Ex-Search")
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
        console_buttons_layout.addWidget(self.run_btn)
        self.run_btn.clicked.connect(self.run_optimization)
        
        # Stop button
        self.stop_btn = QtWidgets.QPushButton("Stop Ex-Search")
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
        self.stop_btn.setEnabled(False)
        console_buttons_layout.addWidget(self.stop_btn)
        self.stop_btn.clicked.connect(self.stop_optimization)
        
        # Clear console button
        self.clear_console_btn = QtWidgets.QPushButton("Clear Console")
        self.clear_console_btn.setStyleSheet("""
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
        # Add debug mode checkbox next to console buttons
        self.debug_mode_checkbox = QtWidgets.QCheckBox("Debug Mode")
        self.debug_mode_checkbox.setChecked(self.debug_mode)
        self.debug_mode_checkbox.setToolTip(
            "Toggle debug mode:\n"
            "• ON: Show all detailed logging information\n"
            "• OFF: Show only key operational steps"
        )
        self.debug_mode_checkbox.toggled.connect(self.set_debug_mode)
        
        # Style the debug mode checkbox
        self.debug_mode_checkbox.setStyleSheet("""
            QCheckBox {
                font-weight: bold;
                color: #333333;
                padding: 5px;
                margin-left: 10px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #cccccc;
                background-color: white;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #4CAF50;
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        
        console_buttons_layout.addWidget(self.clear_console_btn)
        console_buttons_layout.addWidget(self.debug_mode_checkbox)
        self.clear_console_btn.clicked.connect(self.clear_console)
        
        # Console header layout (label + buttons)
        console_header_layout = QtWidgets.QHBoxLayout()
        console_header_layout.addWidget(output_label)
        console_header_layout.addStretch()
        console_header_layout.addLayout(console_buttons_layout)
        
        # Console output
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
        
        # After self.subject_combo is created and added:
        self.subject_combo.currentTextChanged.connect(self.on_subject_selection_changed)
    
    def initial_setup(self):
        """Initial setup when the tab is first loaded."""
        self.list_subjects()
        if self.debug_mode:
            self.update_output("Welcome to Ex-Search Optimization!")
            self.update_output("\nChecking available subjects and leadfields...")
        
        try:
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            simnibs_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
            
            # Count subjects and leadfields with new naming scheme
            subject_count = 0
            total_leadfields = 0
            subjects_with_leadfields = {}
            
            for item in os.listdir(simnibs_dir):
                if item.startswith("sub-"):
                    subject_id = item[4:]  # Remove 'sub-' prefix
                    subject_count += 1
                    subject_dir = os.path.join(simnibs_dir, item)
                    
                    # Look for leadfield directories with new pattern: leadfield_vol_*
                    subject_leadfields = []
                    for subdir in os.listdir(subject_dir):
                        if subdir.startswith("leadfield_vol_"):
                            leadfield_path = os.path.join(subject_dir, subdir)
                            # Check if leadfield.hdf5 exists
                            hdf5_file = os.path.join(leadfield_path, "leadfield.hdf5")
                            if os.path.exists(hdf5_file):
                                net_name = subdir[len("leadfield_vol_"):]
                                subject_leadfields.append(net_name)
                                total_leadfields += 1
                    
                    if subject_leadfields:
                        subjects_with_leadfields[subject_id] = subject_leadfields
            
            # Display summary only in debug mode
            if self.debug_mode:
                self.update_output(f"\nFound {subject_count} subject(s):")
                self.update_output(f"- Total leadfield matrices: {total_leadfields}")
                self.update_output(f"- Subjects with leadfields: {len(subjects_with_leadfields)}")
                
                for subject_id, nets in subjects_with_leadfields.items():
                    self.update_output(f"  {subject_id}: {', '.join(nets)}")
                
                subjects_without_leadfield = [sid for sid in range(1, subject_count+1) 
                                            if str(sid) not in subjects_with_leadfields]
                if subjects_without_leadfield:
                    self.update_output(f"- Subjects without leadfields: {', '.join(map(str, subjects_without_leadfield))}")
                
                self.update_output("\nTo start optimization:")
                self.update_output("1. Select a subject")
                self.update_output("2. Select or create ROI(s)")
                self.update_output("3. Enter electrodes for each category (E1+, E1-, E2+, E2-)")
                self.update_output("4. Click 'Run Ex-Search'")
            
        except Exception as e:
            if self.debug_mode:
                self.update_output(f"Error during initial setup: {str(e)}")
    
    def refresh_leadfields(self):
        """Refresh the list of available leadfields for the selected subject."""
        subject_id = self.subject_combo.currentText()
        self.leadfield_list.clear()
        self.selected_leadfield_label.setText("Selected: None")
        self.show_electrodes_leadfield_btn.setEnabled(False)
        
        if not subject_id:
            return
        
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        subject_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}")
        
        try:
            # Look for leadfield directories with pattern: leadfield_vol_*
            leadfields = []
            if os.path.exists(subject_dir):
                for item in os.listdir(subject_dir):
                    if item.startswith("leadfield_vol_"):
                        leadfield_path = os.path.join(subject_dir, item)
                        # Check if leadfield.hdf5 exists
                        hdf5_file = os.path.join(leadfield_path, "leadfield.hdf5")
                        if os.path.exists(hdf5_file):
                            net_name = item[len("leadfield_vol_"):]
                            # Get file size for display
                            file_size = os.path.getsize(hdf5_file) / (1024**3)  # GB
                            leadfields.append((net_name, hdf5_file, file_size))
            
            # Populate the list
            for net_name, hdf5_path, file_size in sorted(leadfields):
                item_text = f"{net_name} ({file_size:.1f} GB)"
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(QtCore.Qt.UserRole, {"net_name": net_name, "hdf5_path": hdf5_path})
                self.leadfield_list.addItem(item)
            
            if not leadfields:
                no_leadfields_item = QtWidgets.QListWidgetItem("No leadfields found")
                no_leadfields_item.setFlags(QtCore.Qt.NoItemFlags)  # Make it non-selectable
                no_leadfields_item.setForeground(QtGui.QColor("#666"))
                self.leadfield_list.addItem(no_leadfields_item)
                
        except Exception as e:
            self.update_status(f"Error refreshing leadfields: {str(e)}", error=True)
    
    def on_leadfield_selection_changed(self):
        """Handle leadfield selection changes."""
        selected_items = self.leadfield_list.selectedItems()
        if selected_items and selected_items[0].data(QtCore.Qt.UserRole):
            data = selected_items[0].data(QtCore.Qt.UserRole)
            net_name = data["net_name"]
            self.selected_leadfield_label.setText(f"Selected: {net_name}")
            self.selected_leadfield_label.setStyleSheet("color: #4caf50; font-weight: bold;")
            self.show_electrodes_leadfield_btn.setEnabled(True)
        else:
            self.selected_leadfield_label.setText("Selected: None")
            self.selected_leadfield_label.setStyleSheet("color: #666; font-style: italic;")
            self.show_electrodes_leadfield_btn.setEnabled(False)
    
    def get_available_eeg_nets(self, subject_id):
        """Get available EEG nets for a subject."""
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        eeg_positions_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                        f"m2m_{subject_id}", "eeg_positions")
        
        eeg_nets = []
        if os.path.exists(eeg_positions_dir):
            for file in os.listdir(eeg_positions_dir):
                if file.endswith('.csv'):
                    eeg_nets.append(file)
        
        return sorted(eeg_nets)
    
    def show_create_leadfield_dialog(self):
        """Show dialog to select EEG net and create leadfield."""
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            self.update_status("Please select a subject first", error=True)
            return
        
        # Get available EEG nets
        eeg_nets = self.get_available_eeg_nets(subject_id)
        if not eeg_nets:
            QtWidgets.QMessageBox.warning(self, "No EEG Nets Found", 
                                        f"No EEG net files found for subject {subject_id}")
            return
        
        # Create selection dialog
        dialog = EEGNetSelectionDialog(eeg_nets, subject_id, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_net = dialog.get_selected_net()
            if selected_net:
                self.create_leadfield_with_net(subject_id, selected_net)
    
    def create_leadfield_with_net(self, subject_id, eeg_net_file):
        """Create leadfield with selected EEG net."""
        try:
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            m2m_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                  f"m2m_{subject_id}")
            eeg_cap_path = os.path.join(m2m_dir, "eeg_positions", eeg_net_file)
            net_name_clean = eeg_net_file.replace('.csv', '')
            
            # Prepare command with new leadfield.py arguments
            leadfield_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                          "ex-search", "leadfield.py")
            cmd = ["simnibs_python", leadfield_script, m2m_dir, eeg_cap_path, net_name_clean]
            
            # Set up environment variables with log file
            env = os.environ.copy()
            log_file = self.create_log_file_env('leadfield_creation', subject_id)
            if log_file:
                env["TI_LOG_FILE"] = log_file
                self.update_output(f"Log file: {log_file}")
            
            # Create and start thread
            self.optimization_process = ExSearchThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
            self.optimization_process.finished.connect(self.leadfield_creation_completed)
            self.optimization_process.start()
            
            # Update UI
            self.disable_controls()
            self.update_status(f"Creating leadfield for {net_name_clean}...")
            self.update_output(f"Creating leadfield for EEG net: {eeg_net_file}")
            
        except Exception as e:
            self.update_status(f"Error creating leadfield: {str(e)}", error=True)
            self.enable_controls()
    
    def show_electrodes_for_selected_leadfield(self):
        """Show electrodes for the currently selected leadfield."""
        # Get selected leadfield
        selected_items = self.leadfield_list.selectedItems()
        if not selected_items or not selected_items[0].data(QtCore.Qt.UserRole):
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a leadfield first")
            return
        
        # Get leadfield data
        leadfield_data = selected_items[0].data(QtCore.Qt.UserRole)
        net_name = leadfield_data["net_name"]
        subject_id = self.subject_combo.currentText()
        
        if not subject_id:
            QtWidgets.QMessageBox.warning(self, "No Subject", "Please select a subject first")
            return
        
        try:
            # Try to find the EEG cap file for this net
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            
            # First try the subject's eeg_positions directory
            eeg_cap_file = f"{net_name}.csv"
            eeg_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                  f"m2m_{subject_id}", "eeg_positions", eeg_cap_file)
            
            if not os.path.exists(eeg_path):
                # Fallback to assets directory
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                eeg_path = os.path.join(script_dir, "assets", "ElectrodeCaps_MNI", eeg_cap_file)
            
            if not os.path.exists(eeg_path):
                QtWidgets.QMessageBox.warning(self, "EEG File Not Found", 
                                            f"Could not find EEG cap file for {net_name}")
                return
            
            # Read electrode information - all files follow same format: Electrode,X,Y,Z,Label
            electrodes = []
            with open(eeg_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 5 and parts[0] == 'Electrode':
                        electrode_label = parts[4].strip()  # 5th column (index 4) is the label
                        if electrode_label and not electrode_label.replace('.', '').replace('-', '').isdigit():  # Skip numeric values
                            electrodes.append(electrode_label)
            
            if not electrodes:
                QtWidgets.QMessageBox.information(self, "No Electrodes", 
                                                f"No electrode labels found for {net_name}")
                return
            
            # Create and show electrode display dialog (non-modal)
            self.electrode_dialog = ElectrodeDisplayDialog(net_name, electrodes, self)
            self.electrode_dialog.show()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", 
                                         f"Error reading electrode information: {str(e)}")
    
    def list_subjects(self):
        """List available subjects in the combo box."""
        self.subject_combo.clear()
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        if not project_dir or not os.path.exists(project_dir):
            self.update_status("No project directory selected", error=True)
            return
            
        subjects_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
        if not os.path.exists(subjects_dir):
            self.update_status("No subjects directory found", error=True)
            return
            
        # Find all m2m_* directories
        subjects = []
        for item in os.listdir(subjects_dir):
            if item.startswith("sub-"):
                subject_path = os.path.join(subjects_dir, item)
                for m2m_dir in os.listdir(subject_path):
                    if m2m_dir.startswith("m2m_"):
                        subject_id = m2m_dir.replace("m2m_", "")
                        subjects.append(subject_id)
        
        if not subjects:
            self.update_status("No subjects found", error=True)
            return
            
        # Sort subjects naturally
        subjects.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', x)])
        self.subject_combo.addItems(subjects)
    
    def clear_subject_selection(self):
        """Clear the subject selection."""
        self.subject_combo.setCurrentIndex(-1)
        self.show_electrodes_leadfield_btn.setEnabled(False)
    
    def update_roi_list(self):
        """Update the list of available ROIs for the selected subject."""
        try:
            subject_id = self.subject_combo.currentText()
            if not subject_id:
                return
            
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                 f"m2m_{subject_id}", "ROIs")
            
            self.roi_list.clear()
            
            if os.path.exists(roi_dir):
                # Always scan directory for actual CSV files and sync roi_list.txt
                csv_files = [f for f in os.listdir(roi_dir) 
                           if f.endswith('.csv') and not f.startswith('.') 
                           and os.path.isfile(os.path.join(roi_dir, f))]
                
                # Sync roi_list.txt with actual CSV files
                roi_list_file = os.path.join(roi_dir, "roi_list.txt")
                with open(roi_list_file, 'w') as f:
                    for csv_file in sorted(csv_files):
                        f.write(f"{csv_file}\n")
                
                # Display ROIs with coordinates
                for roi_name in sorted(csv_files):
                    roi_path = os.path.join(roi_dir, roi_name)
                    coords = None
                    try:
                        with open(roi_path, 'r') as rf:
                            line = rf.readline().strip()
                            # Expect format: x, y, z
                            parts = [p.strip() for p in line.split(',')]
                            if len(parts) == 3:
                                coords = ', '.join(parts)
                    except Exception as e:
                        self.update_output(f"Warning: Could not read coordinates from {roi_name}: {e}", 'warning')
                    
                    display_name = roi_name.replace('.csv', '')
                    if coords:
                        self.roi_list.addItem(f"{display_name}: {coords}")
                    else:
                        self.roi_list.addItem(display_name)
                        
                if self.debug_mode:
                    self.update_output(f"Found and synced {len(csv_files)} ROI file(s)")
                    
                    # Debug: Show what's in roi_list.txt vs actual files
                    if csv_files:
                        self.update_output(f"ROI files: {', '.join(sorted(csv_files))}")
        except Exception as e:
            self.update_status(f"Error updating ROI list: {str(e)}", error=True)
    
    def show_add_roi_dialog(self):
        """Show dialog for adding a new ROI."""
        dialog = AddROIDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.update_roi_list()
    
    def remove_selected_roi(self):
        """Remove the selected ROI."""
        selected_items = self.roi_list.selectedItems()
        if not selected_items:
            self.update_status("Please select an ROI to remove", error=True)
            return
        
        # Get confirmation
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setText("Are you sure you want to remove the selected ROI(s)?")
        msg.setWindowTitle("Confirm ROI Removal")
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        
        if msg.exec_() == QtWidgets.QMessageBox.Yes:
            try:
                selected_subject = self.subject_combo.currentText()
                project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
                roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{selected_subject}",
                                     f"m2m_{selected_subject}", "ROIs")
                roi_list_file = os.path.join(roi_dir, "roi_list.txt")
                # Read existing ROIs
                if os.path.exists(roi_list_file):
                    with open(roi_list_file, 'r') as f:
                        rois = [line.strip() for line in f.readlines()]
                else:
                    rois = []
                # Remove selected ROIs
                for item in selected_items:
                    # Handle display format 'name: x, y, z' or just 'name'
                    roi_display = item.text()
                    roi_name = roi_display.split(':')[0].strip() + '.csv'
                    # Remove from roi_list.txt if present
                    if roi_name in rois:
                        rois.remove(roi_name)
                    # Remove the ROI file
                    roi_file = os.path.join(roi_dir, roi_name)
                    if os.path.exists(roi_file):
                        os.remove(roi_file)
                # Update roi_list.txt
                with open(roi_list_file, 'w') as f:
                    for roi in rois:
                        f.write(f"{roi}\n")
                self.update_roi_list()
                self.update_status("ROI(s) removed successfully")
            except Exception as e:
                self.update_status(f"Error removing ROI: {str(e)}", error=True)
    
    def parse_electrode_input(self, text):
        """Parse electrode input text into a list of electrodes."""
        # Split by comma and clean up whitespace
        electrodes = [e.strip() for e in text.split(',') if e.strip()]
        # Validate electrode format - support various naming conventions
        # E001, E1, Fp1, F3, C4, P3, O1, T7, Cz, etc.
        pattern = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')
        if not all(pattern.match(e) for e in electrodes):
            return None
        return electrodes
    
    def validate_inputs(self):
        """Validate all input fields before running optimization."""
        # Check if a subject is selected
        if self.subject_combo.currentText() == "":
            self.update_status("Please select a subject", error=True)
            return False
            
        # Check if a leadfield is selected
        selected_items = self.leadfield_list.selectedItems()
        if not selected_items or not selected_items[0].data(QtCore.Qt.UserRole):
            self.update_status("Please select a leadfield for simulation", error=True)
            return False
            
        # Check if ROIs are selected
        if self.roi_list.count() == 0:
            self.update_status("Please add at least one ROI", error=True)
            return False
            
        # Check if at least one ROI is selected
        selected_rois = self.roi_list.selectedItems()
        if not selected_rois:
            self.update_status("Please select at least one ROI from the list", error=True)
            return False
            
        # Validate electrode inputs
        e1_plus = self.parse_electrode_input(self.e1_plus_input.text())
        e1_minus = self.parse_electrode_input(self.e1_minus_input.text())
        e2_plus = self.parse_electrode_input(self.e2_plus_input.text())
        e2_minus = self.parse_electrode_input(self.e2_minus_input.text())
        
        if not all([e1_plus, e1_minus, e2_plus, e2_minus]):
            self.update_status("Please enter valid electrode names for all categories", error=True)
            return False
            
        if not (len(e1_plus) == len(e1_minus) == len(e2_plus) == len(e2_minus)):
            self.update_status("All electrode categories must have the same number of electrodes", error=True)
            return False
            
        return True
    
    def run_optimization(self):
        """Run the ex-search optimization for selected subjects."""
        if not self.validate_inputs():
            return
            
        subject_id = self.subject_combo.currentText()
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        ex_search_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "ex-search")
        
        # Create ex_search directory if it doesn't exist
        os.makedirs(ex_search_dir, exist_ok=True)
        
        # Get electrode configurations
        e1_plus = self.parse_electrode_input(self.e1_plus_input.text())
        e1_minus = self.parse_electrode_input(self.e1_minus_input.text())
        e2_plus = self.parse_electrode_input(self.e2_plus_input.text())
        e2_minus = self.parse_electrode_input(self.e2_minus_input.text())
        
        # Get selected ROI(s)
        selected_rois = self.roi_list.selectedItems()
        selected_roi_names = []
        for roi_item in selected_rois:
            # Extract ROI name from display format "name: x, y, z" or just "name"
            roi_display = roi_item.text()
            roi_name = roi_display.split(':')[0].strip()
            if not roi_name.endswith('.csv'):
                roi_name += '.csv'
            selected_roi_names.append(roi_name)
        
        if self.debug_mode:
            self.update_output(f"Selected ROI(s): {', '.join(selected_roi_names)}")
        
        # Set up environment variables
        env = os.environ.copy()
        env["SUBJECTS_DIR"] = project_dir
        
        # Disable controls and show status
        self.disable_controls()
        self.update_status(f"Running optimization for subject {subject_id}...")
        
        # Initialize ROI processing queue and start pipeline
        self.roi_processing_queue = selected_roi_names.copy()
        self.current_roi_index = 0
        self.e1_plus = e1_plus
        self.e1_minus = e1_minus
        self.e2_plus = e2_plus
        self.e2_minus = e2_minus
        
        # Log ex-search start
        self.log_exsearch_start(subject_id, len(selected_roi_names))
        
        # Run the pipeline for the first ROI
        self.run_roi_pipeline(subject_id, project_dir, ex_search_dir, env)
    
    def run_roi_pipeline(self, subject_id, project_dir, ex_search_dir, env):
        """Run the ex-search pipeline for the current ROI in the queue."""
        # Check if we have more ROIs to process
        if self.current_roi_index >= len(self.roi_processing_queue):
            self.pipeline_completed()
            return
            
        # Get current ROI
        current_roi = self.roi_processing_queue[self.current_roi_index]
        roi_name = current_roi.replace('.csv', '')  # Remove .csv extension
        
        # Log ROI start
        self.log_roi_start(self.current_roi_index, len(self.roi_processing_queue), roi_name)
        
        # Update output for debug mode
        if self.debug_mode:
            self.update_output(f"\n=== Processing ROI {self.current_roi_index + 1}/{len(self.roi_processing_queue)}: {current_roi} ===")
            self.update_output(f"[DEBUG] Subject: {subject_id} | Project: {project_dir}", 'debug')
            self.update_output(f"[DEBUG] ex_search_dir: {ex_search_dir}", 'debug')
        
        # Get the script directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ex_search_scripts_dir = os.path.join(script_dir, "ex-search")
        
        # Get selected leadfield information
        selected_items = self.leadfield_list.selectedItems()
        if not selected_items or not selected_items[0].data(QtCore.Qt.UserRole):
            self.update_status("No leadfield selected", error=True)
            self.enable_controls()
            return
            
        leadfield_data = selected_items[0].data(QtCore.Qt.UserRole)
        selected_net_name = leadfield_data["net_name"]
        selected_hdf5_path = leadfield_data["hdf5_path"]
        
        # Get ROI coordinates for environment variables
        roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                              f"m2m_{subject_id}", "ROIs")
        roi_file = os.path.join(roi_dir, current_roi)
        
        try:
            with open(roi_file, 'r') as f:
                coordinates = f.readline().strip()
            x, y, z = [float(coord.strip()) for coord in coordinates.split(',')]
            roi_name = current_roi.replace('.csv', '')  # Remove .csv extension
            if self.debug_mode:
                self.update_output(f"[DEBUG] ROI file: {roi_file}", 'debug')
                self.update_output(f"[DEBUG] Parsed ROI coords: {(x, y, z)}", 'debug')
        except Exception as e:
            self.update_output(f"Error reading ROI file {current_roi}: {str(e)}", 'error')
            # Move to next ROI
            self.current_roi_index += 1
            self.run_roi_pipeline(subject_id, project_dir, ex_search_dir, env)
            return
        
        # Set up complete environment variables including ROI information
        env = os.environ.copy()
        env["PROJECT_DIR_NAME"] = os.path.basename(project_dir)
        env["PROJECT_DIR"] = project_dir
        env["SUBJECT_NAME"] = subject_id
        env["SUBJECTS_DIR"] = project_dir
        env["LEADFIELD_HDF"] = selected_hdf5_path
        env["SELECTED_EEG_NET"] = selected_net_name
        env["ROI_NAME"] = roi_name
        env["ROI_COORDINATES"] = f"{x},{y},{z}"
        env["SELECTED_ROI_FILE"] = current_roi
        env["ROI_DIR"] = roi_dir
        
        # Create shared log file for the entire ex-search pipeline (only on first ROI)
        if self.current_roi_index == 0:
            log_file = self.create_log_file_env('ex_search', subject_id)
            if log_file:
                env["TI_LOG_FILE"] = log_file
                self._shared_log_file = log_file  # Store for subsequent ROI processing
                if self.debug_mode:
                    self.update_output(f"Ex-search log file: {log_file}")
        
            # Log comprehensive configuration details
            if self.debug_mode:
                self.update_output(f"Using leadfield: {selected_net_name}")
                self.update_output(f"HDF5 file: {selected_hdf5_path}")
            self.log_pipeline_configuration(subject_id, project_dir, selected_net_name, selected_hdf5_path, env)
        else:
            # Ensure log file is passed to subsequent ROI processing
            if hasattr(self, '_shared_log_file'):
                env["TI_LOG_FILE"] = self._shared_log_file
        
        if self.debug_mode:
            self.update_output(f"ROI coordinates: {x}, {y}, {z}")
            self.update_output(f"[DEBUG] Step 1 command: simnibs_python {os.path.join(ex_search_scripts_dir, 'ti_sim.py')}", 'debug')
            self.update_output(f"[DEBUG] Env highlights: {{'LEADFIELD_HDF': env.get('LEADFIELD_HDF'), 'SELECTED_EEG_NET': env.get('SELECTED_EEG_NET'), 'TI_LOG_FILE': env.get('TI_LOG_FILE'), 'ROI_NAME': env.get('ROI_NAME')}}", 'debug')
        
        # Log ROI-specific configuration
        self.log_roi_configuration(current_roi, roi_name, x, y, z, env)
        
        # Step 1: Run the TI simulation for this specific ROI
        self.log_step_start("TI simulation")
        if self.debug_mode:
            self.update_output("Step 1: Running TI simulation...")
        ti_sim_script = os.path.join(ex_search_scripts_dir, "ti_sim.py")
        
        # Prepare input data for the script
        input_data = [
            " ".join(self.e1_plus),
            " ".join(self.e1_minus),
            " ".join(self.e2_plus),
            " ".join(self.e2_minus),
            ""   # Use default 1mA (empty input will use default)
        ]
        
        # Command to run ti_sim.py
        cmd = ["simnibs_python", ti_sim_script]
        
        # Create and start thread for step 1
        self.optimization_process = ExSearchThread(cmd, env)
        self.optimization_process.set_input_data(input_data)
        self.optimization_process.output_signal.connect(self.update_output)
        self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
        
        # Connect the finished signal to the mesh processing step for this ROI
        self.optimization_process.finished.connect(
            lambda: self.ti_simulation_completed(subject_id, project_dir, ex_search_dir, env)
        )
        
        self.optimization_process.start()
    
    def ti_simulation_completed(self, subject_id, project_dir, ex_search_dir, env):
        """Handle completion of TI simulation step."""
        # Log step completion
        self.log_step_complete("TI simulation", success=True)
        
        # Continue to ROI analysis
        self.run_current_roi_analysis(subject_id, project_dir, ex_search_dir, env)
    
    def run_current_roi_analysis(self, subject_id, project_dir, ex_search_dir, env):
        """Run ROI analysis for the current ROI."""
        current_roi = self.roi_processing_queue[self.current_roi_index]
        roi_name = current_roi.replace('.csv', '')
        eeg_net_name = env.get("SELECTED_EEG_NET", "unknown_net")
        
        # Log ROI analysis step start
        self.log_step_start("ROI analysis")
        if self.debug_mode:
            self.update_output("\nStep 2: Running ROI analysis...")
            self.update_output(f"[DEBUG] ROI analyzer script will run with ROI_LIST_FILE limited to: {current_roi}", 'debug')
        
        # Create directory name: roi_leadfield format  
        output_dir_name = f"{roi_name}_{eeg_net_name}"
        mesh_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                               "ex-search", output_dir_name)
        
        # Create temporary roi_list.txt with just the current ROI for roi-analyzer.py
        roi_dir = env.get("ROI_DIR")
        temp_roi_list = os.path.join(roi_dir, "temp_roi_list.txt")
        
        try:
            with open(temp_roi_list, 'w') as f:
                f.write(f"{current_roi}\n")
            
            # Run ROI analyzer script
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ex_search_scripts_dir = os.path.join(script_dir, "ex-search")
            roi_analyzer_script = os.path.join(ex_search_scripts_dir, "roi-analyzer.py")
            
            # Update environment variables for ROI analyzer
            roi_env = env.copy()
            roi_env["MESH_DIR"] = mesh_dir
            roi_env["ROI_LIST_FILE"] = temp_roi_list
            
            cmd = ["python3", roi_analyzer_script, roi_dir]
            if self.debug_mode:
                self.update_output(f"[DEBUG] Step 2 command: {' '.join(cmd)}", 'debug')
                dbg_env = {k: roi_env.get(k) for k in ["PROJECT_DIR", "SUBJECT_NAME", "SELECTED_EEG_NET", "TI_LOG_FILE", "MESH_DIR", "ROI_LIST_FILE"]}
                self.update_output(f"[DEBUG] Step 2 env: {dbg_env}", 'debug')
            
            self.optimization_process = ExSearchThread(cmd, roi_env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
            
            # Connect the finished signal to mesh processing
            self.optimization_process.finished.connect(
                lambda: self.roi_analysis_completed(subject_id, project_dir, ex_search_dir, env, temp_roi_list)
            )
            
            self.optimization_process.start()
            
        except Exception as e:
            self.update_output(f"Error setting up ROI analysis: {str(e)}", 'error')
            # Skip to mesh processing
            self.run_current_roi_mesh_processing(subject_id, project_dir, ex_search_dir, env)
    
    def roi_analysis_completed(self, subject_id, project_dir, ex_search_dir, env, temp_roi_list):
        """Handle completion of ROI analysis step."""
        # Log step completion
        self.log_step_complete("ROI analysis", success=True)
        
        # Clean up and continue to mesh processing
        self.cleanup_and_run_mesh_processing(subject_id, project_dir, ex_search_dir, env, temp_roi_list)
    
    def cleanup_and_run_mesh_processing(self, subject_id, project_dir, ex_search_dir, env, temp_roi_list):
        """Clean up temporary files and run mesh processing."""
        # Clean up temporary roi_list.txt
        try:
            if self.debug_mode:
                self.update_output(f"[DEBUG] Removing temp ROI list: {temp_roi_list}", 'debug')
            if os.path.exists(temp_roi_list):
                os.remove(temp_roi_list)
        except Exception as e:
            self.update_output(f"Warning: Could not remove temporary file {temp_roi_list}: {str(e)}", 'warning')
        
        # Continue to mesh processing
        self.run_current_roi_mesh_processing(subject_id, project_dir, ex_search_dir, env)
    
    def run_current_roi_mesh_processing(self, subject_id, project_dir, ex_search_dir, env):
        """Run mesh processing for the current ROI."""
        current_roi = self.roi_processing_queue[self.current_roi_index]
        roi_name = current_roi.replace('.csv', '')
        eeg_net_name = env.get("SELECTED_EEG_NET", "unknown_net")
        
        # Create directory name: roi_leadfield format
        output_dir_name = f"{roi_name}_{eeg_net_name}"
        mesh_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                               "ex-search", output_dir_name)
        
        # Log mesh processing step start
        self.log_step_start("Mesh processing")
        if self.debug_mode:
            self.update_output("\nStep 3: Running mesh processing...")
            self.update_output(f"Output directory: ex-search/{output_dir_name}/")
        
        # Run Python mesh processing
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ex_search_scripts_dir = os.path.join(script_dir, "ex-search")
        mesh_processing_script = os.path.join(ex_search_scripts_dir, "mesh_field_analyzer.py")
        
        # Update environment variables for mesh processing
        env["MESH_DIR"] = mesh_dir
        
        cmd = ["simnibs_python", mesh_processing_script, mesh_dir]
        if self.debug_mode:
            self.update_output(f"[DEBUG] Step 3 command: {' '.join(cmd)}", 'debug')
            dbg_env = {k: env.get(k) for k in ["PROJECT_DIR", "SUBJECT_NAME", "SELECTED_EEG_NET", "TI_LOG_FILE", "MESH_DIR", "ROI_NAME"]}
            self.update_output(f"[DEBUG] Step 3 env: {dbg_env}", 'debug')
        
        self.optimization_process = ExSearchThread(cmd, env)
        self.optimization_process.output_signal.connect(self.update_output)
        self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
        
        # Connect the finished signal to move to the next ROI
        self.optimization_process.finished.connect(
            lambda: self.mesh_processing_completed(subject_id, project_dir, ex_search_dir, env)
        )
        
        self.optimization_process.start()
    
    def mesh_processing_completed(self, subject_id, project_dir, ex_search_dir, env):
        """Handle completion of mesh processing step."""
        # Log step completion
        self.log_step_complete("Mesh processing", success=True)
        
        # Continue to next ROI
        self.current_roi_completed(subject_id, project_dir, ex_search_dir, env)
    
    def current_roi_completed(self, subject_id, project_dir, ex_search_dir, env):
        """Handle completion of current ROI and move to the next."""
        # Log ROI completion
        current_roi = self.roi_processing_queue[self.current_roi_index]
        roi_name = current_roi.replace('.csv', '')
        self.log_roi_complete(self.current_roi_index, len(self.roi_processing_queue), roi_name)
        
        # Increment ROI index
        self.current_roi_index += 1
        
        # Process the next ROI if available
        self.run_roi_pipeline(subject_id, project_dir, ex_search_dir, env)
    
    def run_roi_analyzer(self, subject_id, project_dir, ex_search_dir, selected_roi_names, env):
        """Run the ROI analyzer step - SKIPPED in new workflow."""
        # NOTE: ROI analysis is now integrated into the mesh processing step
        # to ensure each selected ROI gets its own analysis directory
        
        if self.debug_mode:
            self.update_output("\nStep 2: ROI analyzer skipped (integrated into mesh processing)")
        
        # Skip directly to mesh processing
        roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                              f"m2m_{subject_id}", "ROIs")
        self.run_mesh_processing(subject_id, project_dir, ex_search_dir, roi_dir, selected_roi_names, env)
    
    def run_mesh_processing(self, subject_id, project_dir, ex_search_dir, roi_dir, selected_roi_names, env):
        """Run the mesh processing step."""
        # Step 2: Run mesh processing (ROI analysis integrated)
        if self.debug_mode:
            self.update_output("\nStep 2: Running mesh processing and ROI analysis...")
        
        try:
            # Process all selected ROIs individually
            if not selected_roi_names:
                raise ValueError("No ROI selected for processing")
            
            if self.debug_mode:
                self.update_output(f"Processing {len(selected_roi_names)} ROI(s)...")
            
            # Store the ROI processing queue and start with the first one
            self.roi_processing_queue = selected_roi_names.copy()
            self.current_roi_index = 0
            
            # Start processing the first ROI
            self.process_next_roi(subject_id, project_dir, ex_search_dir, roi_dir, env)
            
        except Exception as e:
            self.update_output(f"Error in mesh processing: {str(e)}", 'error')
            self.enable_controls()
    
    def process_next_roi(self, subject_id, project_dir, ex_search_dir, roi_dir, env):
        """Process the next ROI in the queue."""
        try:
            if self.current_roi_index >= len(self.roi_processing_queue):
                # All ROIs processed
                self.pipeline_completed()
                return
                
            selected_roi = self.roi_processing_queue[self.current_roi_index]
            if self.debug_mode:
                self.update_output(f"\n--- Processing ROI {self.current_roi_index + 1}/{len(self.roi_processing_queue)}: {selected_roi} ---")
            
            # Get ROI coordinates from the selected ROI file
            roi_file = os.path.join(roi_dir, selected_roi)
            if not os.path.exists(roi_file):
                raise FileNotFoundError(f"ROI file not found: {roi_file}")
                
            with open(roi_file, 'r') as f:
                coordinates = f.readline().strip()
            
            # Parse coordinates (still needed for the analysis)
            x, y, z = [float(coord.strip()) for coord in coordinates.split(',')]
            x_int, y_int, z_int = int(x), int(y), int(z)
            
            # Get ROI name and EEG net for directory naming
            roi_name = selected_roi.replace('.csv', '')  # Remove .csv extension
            eeg_net_name = env.get("SELECTED_EEG_NET", "unknown_net")
            
            # Create directory name: roi_leadfield format
            output_dir_name = f"{roi_name}_{eeg_net_name}"
            mesh_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", 
                                   "ex-search", output_dir_name)
            
            # Create output directory if it doesn't exist
            os.makedirs(mesh_dir, exist_ok=True)
            
            if self.debug_mode:
                self.update_output(f"Output directory: ex-search/{output_dir_name}/")
                self.update_output(f"ROI coordinates: {x}, {y}, {z}")
            
            # Run Python mesh processing (replaces MATLAB version)
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ex_search_scripts_dir = os.path.join(script_dir, "ex-search")
            mesh_processing_script = os.path.join(ex_search_scripts_dir, "mesh_field_analyzer.py")
            
            # Update environment variables for mesh processing
            env["PROJECT_DIR"] = project_dir
            env["SUBJECT_NAME"] = subject_id
            env["MESH_DIR"] = mesh_dir
            env["ROI_NAME"] = roi_name
            env["ROI_COORDINATES"] = f"{x},{y},{z}"
            env["SELECTED_ROI_FILE"] = selected_roi
            env["ROI_DIR"] = roi_dir
            
            cmd = ["simnibs_python", mesh_processing_script, mesh_dir]
            
            self.optimization_process = ExSearchThread(cmd, env)
            self.optimization_process.output_signal.connect(self.update_output)
            self.optimization_process.error_signal.connect(lambda msg: self.handle_process_error(msg))
            
            # Connect the finished signal to process the next ROI
            self.optimization_process.finished.connect(
                lambda: self.roi_processing_completed(subject_id, project_dir, ex_search_dir, roi_dir, env)
            )
            
            self.optimization_process.start()
            
        except Exception as e:
            self.update_output(f"Error processing ROI {selected_roi}: {str(e)}", 'error')
            # Move to next ROI even if this one failed
            self.current_roi_index += 1
            self.process_next_roi(subject_id, project_dir, ex_search_dir, roi_dir, env)
    
    def roi_processing_completed(self, subject_id, project_dir, ex_search_dir, roi_dir, env):
        """Handle completion of one ROI and move to the next."""
        self.current_roi_index += 1
        
        if self.current_roi_index < len(self.roi_processing_queue):
            # Process the next ROI
            self.process_next_roi(subject_id, project_dir, ex_search_dir, roi_dir, env)
        else:
            # All ROIs completed
            self.pipeline_completed()
    
    def handle_process_error(self, error_msg):
        """Handle process errors with proper GUI state management."""
        self.update_output(error_msg, 'error')
        self.enable_controls()
        self.update_status("Process failed - see console for details", error=True)
    
    def leadfield_creation_completed(self):
        """Handle leadfield creation completion."""
        self.enable_controls()
        self.refresh_leadfields()
        self.update_status("Leadfield creation completed")
    
    def pipeline_completed(self):
        """Handle the completion of the pipeline."""
        # Log completion summary
        self.log_pipeline_completion()
        
        # Log final completion with summary
        subject_id = self.subject_combo.currentText()
        total_rois = len(self.roi_processing_queue)
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        ex_search_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "ex-search")
        
        self.log_exsearch_complete(subject_id, total_rois, ex_search_dir)
        
        # Final message for debug mode
        if self.debug_mode:
            self.update_output("\nOptimization process completed!")
        
        self.enable_controls()
        self.update_status("Ex-search optimization completed successfully")
    
    def stop_optimization(self):
        """Stop the running optimization process."""
        if self.optimization_process and self.optimization_process.terminate_process():
            self.update_status("Optimization stopped by user")
            self.update_output("Process terminated by user", 'warning')
            self.enable_controls()
        else:
            self.update_output("No running process to stop", 'warning')
    
    def clear_console(self):
        """Clear the console output."""
        self.console_output.clear()
    
    def update_output(self, text, message_type='default'):
        """Update the console output with colored text."""
        if not text.strip():
            return
        
        # Filter messages based on debug mode
        if not self.debug_mode:
            # In non-debug mode, only show important messages
            if not is_important_message(text, message_type, 'exsearch'):
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
        scrollbar = self.console_output.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5  # Allow small tolerance
        
        # Append to the console with HTML formatting
        self.console_output.append(formatted_text)
        
        # Only auto-scroll if user was already at the bottom
        if at_bottom:
            self.console_output.ensureCursorVisible()
        
        QtWidgets.QApplication.processEvents()

    def set_debug_mode(self, debug_mode):
        """Set debug mode for output filtering."""
        self.debug_mode = debug_mode
        # Set summary mode to opposite of debug mode
        self.set_summary_mode(not debug_mode)
    
    def update_status(self, message, error=False):
        """Update the status label with a message."""
        self.status_label.setText(message)
        if error:
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #ffebee;
                    color: #f44336;
                    padding: 5px 10px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        else:
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f5e9;
                    color: #4caf50;
                    padding: 5px 10px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        self.status_label.show()
    
    def disable_controls(self):
        """Disable controls during optimization."""
        self.subject_combo.setEnabled(False)
        self.roi_list.setEnabled(False)
        self.e1_plus_input.setEnabled(False)
        self.e1_minus_input.setEnabled(False)
        self.e2_plus_input.setEnabled(False)
        self.e2_minus_input.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.list_subjects_btn.setEnabled(False)
        self.clear_subject_selection_btn.setEnabled(False)
        self.add_roi_btn.setEnabled(False)
        self.remove_roi_btn.setEnabled(False)
        self.list_rois_btn.setEnabled(False)
        self.leadfield_list.setEnabled(False)
        self.refresh_leadfields_btn.setEnabled(False)
        self.show_electrodes_leadfield_btn.setEnabled(False)
        self.create_leadfield_btn.setEnabled(False)
    
    def enable_controls(self):
        """Enable controls after optimization."""
        self.subject_combo.setEnabled(True)
        self.roi_list.setEnabled(True)
        self.e1_plus_input.setEnabled(True)
        self.e1_minus_input.setEnabled(True)
        self.e2_plus_input.setEnabled(True)
        self.e2_minus_input.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.list_subjects_btn.setEnabled(True)
        self.clear_subject_selection_btn.setEnabled(True)
        self.add_roi_btn.setEnabled(True)
        self.remove_roi_btn.setEnabled(True)
        self.list_rois_btn.setEnabled(True)
        self.leadfield_list.setEnabled(True)
        self.refresh_leadfields_btn.setEnabled(True)
        self.create_leadfield_btn.setEnabled(True)
        
        # Show Electrodes button should only be enabled if a leadfield is selected
        selected_items = self.leadfield_list.selectedItems()
        if selected_items and selected_items[0].data(QtCore.Qt.UserRole):
            self.show_electrodes_leadfield_btn.setEnabled(True)
        else:
            self.show_electrodes_leadfield_btn.setEnabled(False)
    
    def on_subject_selection_changed(self):
        """Handle subject selection changes."""
        self.refresh_leadfields()
        self.update_roi_list()

class AddROIDialog(QtWidgets.QDialog):
    """Dialog for adding a new ROI."""
    
    def __init__(self, parent=None):
        super(AddROIDialog, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Add New ROI")
        layout = QtWidgets.QVBoxLayout(self)
        
        # ROI coordinates
        coord_group = QtWidgets.QGroupBox("ROI Coordinates (subject space, RAS)")
        coord_layout = QtWidgets.QFormLayout()
        
        self.x_coord = QtWidgets.QDoubleSpinBox()
        self.x_coord.setRange(-1000, 1000)
        self.x_coord.setDecimals(2)  # Allow 2 decimal places
        self.y_coord = QtWidgets.QDoubleSpinBox()
        self.y_coord.setRange(-1000, 1000)
        self.y_coord.setDecimals(2)  # Allow 2 decimal places
        self.z_coord = QtWidgets.QDoubleSpinBox()
        self.z_coord.setRange(-1000, 1000)
        self.z_coord.setDecimals(2)  # Allow 2 decimal places
        
        coord_layout.addRow("X:", self.x_coord)
        coord_layout.addRow("Y:", self.y_coord)
        coord_layout.addRow("Z:", self.z_coord)
        
        coord_group.setLayout(coord_layout)
        layout.addWidget(coord_group)
        
        # ROI name
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("ROI Name:"))
        self.roi_name = QtWidgets.QLineEdit()
        name_layout.addWidget(self.roi_name)
        layout.addLayout(name_layout)
        
        # Add button to load T1 NIfTI in Freeview
        self.load_t1_btn = QtWidgets.QPushButton("View T1 in Freeview")
        self.load_t1_btn.clicked.connect(self.load_t1_in_freeview)
        layout.addWidget(self.load_t1_btn)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_t1_in_freeview(self):
        """Load the subject's T1 NIfTI file in Freeview."""
        try:
            subject_id = self.parent.subject_combo.currentText()
            if not subject_id:
                QtWidgets.QMessageBox.warning(self, "Error", "Please select a subject first")
                return
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            t1_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", f"m2m_{subject_id}", "T1.nii.gz")
            if not os.path.exists(t1_path):
                QtWidgets.QMessageBox.warning(self, "Error", f"T1 NIfTI file not found: {t1_path}")
                return
            import subprocess
            subprocess.Popen(["freeview", t1_path])
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to launch Freeview: {str(e)}")
    
    def accept(self):
        """Handle dialog acceptance."""
        try:
            # Get selected subject
            subject_id = self.parent.subject_combo.currentText()
            if not subject_id:
                QtWidgets.QMessageBox.warning(self, "Error", "Please select a subject first")
                return
            
            # Validate ROI name
            roi_name = self.roi_name.text().strip()
            if not roi_name:
                QtWidgets.QMessageBox.warning(self, "Error", "Please enter a ROI name")
                return
                
            # Add .csv extension if not present
            if not roi_name.endswith('.csv'):
                roi_name += '.csv'
            
            # Create ROI file
            project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
            roi_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}",
                                 f"m2m_{subject_id}", "ROIs")
            
            os.makedirs(roi_dir, exist_ok=True)
            
            # Write coordinates to ROI file as three comma-separated columns
            roi_file = os.path.join(roi_dir, roi_name)
            with open(roi_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([self.x_coord.value(), self.y_coord.value(), self.z_coord.value()])
            
            # Update roi_list.txt
            roi_list_file = os.path.join(roi_dir, "roi_list.txt")
            with open(roi_list_file, 'a+') as f:
                f.seek(0)
                existing_rois = [line.strip() for line in f.readlines()]
                if roi_name not in existing_rois:
                    f.write(f"{roi_name}\n")
            
            super().accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to create ROI: {str(e)}")


class EEGNetSelectionDialog(QtWidgets.QDialog):
    """Dialog for selecting EEG net for leadfield creation with electrode viewing capability."""
    
    def __init__(self, eeg_nets, subject_id=None, parent=None):
        super(EEGNetSelectionDialog, self).__init__(parent)
        self.eeg_nets = eeg_nets
        self.subject_id = subject_id
        self.parent = parent
        self.selected_net = None
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Select EEG Net")
        self.setModal(True)
        self.resize(500, 400)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title and description
        title_label = QtWidgets.QLabel("Select EEG Net for Leadfield Creation")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        desc_label = QtWidgets.QLabel("Choose an EEG net configuration for the new leadfield matrix:")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 15px;")
        layout.addWidget(desc_label)
        
        # EEG net list
        self.net_list = QtWidgets.QListWidget()
        self.net_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        
        # Find default (GSN-HydroCel-185.csv) and populate list
        default_item = None
        for net in self.eeg_nets:
            item = QtWidgets.QListWidgetItem(net)
            self.net_list.addItem(item)
            if net == "GSN-HydroCel-185.csv":
                default_item = item
        
        # Select default if available
        if default_item:
            default_item.setSelected(True)
            self.net_list.setCurrentItem(default_item)
            
        layout.addWidget(self.net_list)
        
        # Default info
        if default_item:
            default_info = QtWidgets.QLabel("Default: GSN-HydroCel-185.csv is pre-selected")
            default_info.setStyleSheet("color: #4caf50; font-style: italic; margin: 5px 0;")
            layout.addWidget(default_info)
        
        # Show Electrodes button
        self.show_electrodes_btn = QtWidgets.QPushButton("Show Electrodes")
        self.show_electrodes_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
                margin: 5px 0;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.show_electrodes_btn.clicked.connect(self.show_electrodes)
        layout.addWidget(self.show_electrodes_btn)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Connect double-click to accept
        self.net_list.itemDoubleClicked.connect(self.accept)
    
    def show_electrodes(self):
        """Show available electrodes for the selected EEG net."""
        selected_items = self.net_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select an EEG net first")
            return
        
        selected_net = selected_items[0].text()
        
        try:
            # Get path to EEG net file
            if self.subject_id:
                project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
                eeg_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{self.subject_id}",
                                      f"m2m_{self.subject_id}", "eeg_positions", selected_net)
            else:
                # Fallback to assets directory
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                eeg_path = os.path.join(script_dir, "assets", "ElectrodeCaps_MNI", selected_net)
            
            if not os.path.exists(eeg_path):
                QtWidgets.QMessageBox.warning(self, "File Not Found", 
                                            f"EEG net file not found: {eeg_path}")
                return
            
            # Read electrode information - all files follow same format: Electrode,X,Y,Z,Label
            electrodes = []
            with open(eeg_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 5 and parts[0] == 'Electrode':
                        electrode_label = parts[4].strip()  # 5th column (index 4) is the label
                        if electrode_label and not electrode_label.replace('.', '').replace('-', '').isdigit():  # Skip numeric values
                            electrodes.append(electrode_label)
            
            if not electrodes:
                QtWidgets.QMessageBox.information(self, "No Electrodes", 
                                                "No electrode labels found in the selected EEG net file")
                return
            
            # Create and show electrode display dialog (non-modal)
            self.electrode_dialog = ElectrodeDisplayDialog(selected_net, electrodes, self)
            self.electrode_dialog.show()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", 
                                         f"Error reading EEG net file: {str(e)}")
    
    def get_selected_net(self):
        """Get the selected EEG net."""
        selected_items = self.net_list.selectedItems()
        if selected_items:
            return selected_items[0].text()
        return None
    
    def accept(self):
        """Handle dialog acceptance."""
        if not self.net_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select an EEG net")
            return
        
        super().accept()


class ElectrodeDisplayDialog(QtWidgets.QDialog):
    """Dialog to display available electrodes for a selected EEG net."""
    
    def __init__(self, eeg_net_name, electrodes, parent=None):
        super(ElectrodeDisplayDialog, self).__init__(parent)
        self.eeg_net_name = eeg_net_name
        self.electrodes = electrodes
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the electrode display dialog UI."""
        self.setWindowTitle(f"Electrodes for {self.eeg_net_name}")
        # Make dialog non-modal so user can interact with main GUI
        self.setModal(False)
        # Set window flags to make it a tool window that stays on top but allows main GUI interaction
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self.resize(400, 500)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_label = QtWidgets.QLabel(f"Available Electrodes ({len(self.electrodes)} total)")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # EEG net info
        net_info = QtWidgets.QLabel(f"EEG Net: {self.eeg_net_name}")
        net_info.setStyleSheet("color: #666; margin-bottom: 15px;")
        layout.addWidget(net_info)
        
        # Search box
        search_layout = QtWidgets.QHBoxLayout()
        search_label = QtWidgets.QLabel("Search:")
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Filter electrodes (e.g., E1, E10)")
        self.search_input.textChanged.connect(self.filter_electrodes)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Electrode list
        self.electrode_list = QtWidgets.QListWidget()
        self.electrode_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        
        # Populate electrode list
        for electrode in sorted(self.electrodes, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0):
            self.electrode_list.addItem(electrode)
        
        layout.addWidget(self.electrode_list)
        
        # Selection info
        self.selection_info = QtWidgets.QLabel("Tip: You can select multiple electrodes and copy them")
        self.selection_info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.selection_info)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.copy_selected_btn = QtWidgets.QPushButton("Copy Selected")
        self.copy_selected_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.copy_selected_btn.clicked.connect(self.copy_selected_electrodes)
        button_layout.addWidget(self.copy_selected_btn)
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def filter_electrodes(self):
        """Filter electrode list based on search input."""
        search_text = self.search_input.text().lower()
        
        for i in range(self.electrode_list.count()):
            item = self.electrode_list.item(i)
            item.setHidden(search_text not in item.text().lower())
    
    def copy_selected_electrodes(self):
        """Copy selected electrodes to clipboard."""
        selected_items = self.electrode_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select electrodes to copy")
            return
        
        electrode_list = [item.text() for item in selected_items]
        electrode_text = ", ".join(electrode_list)
        
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(electrode_text)
        
        QtWidgets.QMessageBox.information(self, "Copied", 
                                        f"Copied {len(electrode_list)} electrodes to clipboard:\n{electrode_text}")
    
    def accept(self):
        """Handle dialog acceptance."""
        super().accept() 