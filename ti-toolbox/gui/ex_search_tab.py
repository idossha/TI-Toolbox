#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 Ex-Search Tab
This module provides a GUI interface for the ex-search optimization functionality.
"""

import os
import json
import re
import subprocess
import csv
import time
import logging
import sys
from pathlib import Path

# Add project root to path for tools import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt5 import QtWidgets, QtCore, QtGui

from confirmation_dialog import ConfirmationDialog
from utils import confirm_overwrite, is_verbose_message, is_important_message
from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons
from core import get_path_manager
from tools import logging_util


def _get_and_display_electrodes(subject_id, cap_name, parent_widget, path_manager=None):
    """
    Helper function to get electrode names from a cap and display them.
    
    Args:
        subject_id: Subject ID
        cap_name: EEG cap name (e.g., 'GSN-256', 'EEG10-10')
        parent_widget: Parent widget for the dialog
        path_manager: Optional PathManager instance (will use get_path_manager() if not provided)
    
    Returns:
        bool: True if electrodes were displayed successfully, False otherwise
    """
    if not subject_id:
        QtWidgets.QMessageBox.warning(parent_widget, "No Subject", "Please select a subject first")
        return False
    
    if not cap_name:
        QtWidgets.QMessageBox.warning(parent_widget, "No Cap Name", "No EEG cap name provided")
        return False
    
    try:
        # Get path manager
        pm = path_manager if path_manager is not None else get_path_manager()
        m2m_dir = pm.get_m2m_dir(subject_id)
        
        if not m2m_dir or not os.path.exists(m2m_dir):
            QtWidgets.QMessageBox.warning(parent_widget, "Directory Not Found",
                                         f"m2m directory not found for subject {subject_id}")
            return False
        
        # Create LeadfieldGenerator and get electrode names
        from opt.leadfield import LeadfieldGenerator
        gen = LeadfieldGenerator(m2m_dir)
        
        # Clean cap name (remove .csv extension if present)
        clean_cap_name = cap_name.replace('.csv', '') if cap_name.endswith('.csv') else cap_name
        
        # Get electrodes using get_electrode_names_from_cap
        try:
            electrodes = gen.get_electrode_names_from_cap(cap_name=clean_cap_name)
        except FileNotFoundError as e:
            QtWidgets.QMessageBox.warning(parent_widget, "EEG File Not Found",
                                         f"Could not find EEG cap file for {clean_cap_name}.\n\n"
                                         f"Details: {str(e)}")
            return False
        
        if not electrodes:
            QtWidgets.QMessageBox.information(parent_widget, "No Electrodes",
                                             f"No electrode labels found for {clean_cap_name}")
            return False
        
        # Create and show electrode display dialog (non-modal)
        electrode_dialog = ElectrodeDisplayDialog(clean_cap_name, electrodes, parent_widget)
        electrode_dialog.show()
        return True
        
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent_widget, "Error", 
                                     f"Error reading electrode information: {str(e)}")
        return False


class LeadfieldGenerationThread(QtCore.QThread):
    """Thread to run leadfield generation for Ex-Search (generates both HDF5 and NPY files)."""
    
    # Signals
    output_signal = QtCore.pyqtSignal(str, str)  # message, type
    error_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(bool, str)  # success, hdf5_path
    
    def __init__(self, subject_id, eeg_net_file, project_dir, parent=None):
        super(LeadfieldGenerationThread, self).__init__(parent)
        self.subject_id = subject_id
        self.eeg_net_file = eeg_net_file
        self.project_dir = project_dir
        self.terminated = False
        self.generator = None
        
    def run(self):
        """Run leadfield generation using LeadfieldGenerator (generates both HDF5 and NPY files)."""
        try:
            self.output_signal.emit("Initializing leadfield generation...", 'info')
            
            pm = get_path_manager()
            m2m_dir = pm.get_m2m_dir(self.subject_id)
            
            if not m2m_dir or not os.path.exists(m2m_dir):
                self.error_signal.emit(f"m2m directory not found for subject {self.subject_id}")
                self.finished_signal.emit(False, "")
                return
            
            # Setup log file
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            derivatives_dir = os.path.join(self.project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{self.subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f'exsearch_leadfield_{time_stamp}.log')
            
            self.output_signal.emit(f"Log file: {log_file}", 'info')
            self.output_signal.emit(f"Subject: {self.subject_id}", 'info')
            self.output_signal.emit(f"EEG Net: {self.eeg_net_file}", 'info')
            self.output_signal.emit(f"m2m directory: {m2m_dir}", 'info')
            
            # Get leadfield output directory
            subject_dir = f"sub-{self.subject_id}"
            leadfield_dir = os.path.join(self.project_dir, 'derivatives', 'SimNIBS', subject_dir, 'leadfields')
            os.makedirs(leadfield_dir, exist_ok=True)
            
            # Clean net name (remove .csv extension)
            net_name = self.eeg_net_file.replace('.csv', '') if self.eeg_net_file.endswith('.csv') else self.eeg_net_file
            
            # Check if leadfield already exists
            hdf5_filename = f"{net_name}_leadfield.hdf5"
            hdf5_path = os.path.join(leadfield_dir, hdf5_filename)
            
            if os.path.exists(hdf5_path):
                self.error_signal.emit(f"Leadfield already exists: {hdf5_filename}")
                self.error_signal.emit("Delete existing file first or choose a different EEG net")
                self.finished_signal.emit(False, "")
                return
            
            # Progress callback to emit signals
            def progress_callback(message, msg_type='info'):
                self.output_signal.emit(message, msg_type)
                
            # Termination check callback
            def termination_check():
                return self.terminated
            
            # Create leadfield generator
            self.output_signal.emit("", 'default')
            self.output_signal.emit("Creating leadfield generator...", 'info')
            
            try:
                from opt.leadfield import LeadfieldGenerator
                self.generator = LeadfieldGenerator(
                    m2m_dir, 
                    electrode_cap=net_name,
                    progress_callback=progress_callback,
                    termination_flag=termination_check
                )
                
                # Generate leadfield (creates both HDF5 and NPY files)
                self.output_signal.emit("Starting leadfield generation...", 'info')
                result = self.generator.generate_leadfield(
                    output_dir=leadfield_dir,
                    tissues=[1, 2],
                    eeg_cap_path=os.path.join(m2m_dir, "eeg_positions", self.eeg_net_file)
                )
                
                if self.terminated:
                    self.output_signal.emit("Leadfield generation was terminated", 'warning')
                    self.finished_signal.emit(False, "")
                    return
                
                # Check if HDF5 file was generated successfully
                if result['hdf5']:
                    hdf5_path = result['hdf5']
                    self.output_signal.emit("", 'default')
                    self.output_signal.emit(f"Leadfield HDF5 saved: {os.path.basename(hdf5_path)}", 'success')
                    self.finished_signal.emit(True, hdf5_path)
                else:
                    self.error_signal.emit("Failed to generate HDF5 file")
                    self.finished_signal.emit(False, "")
                    
            except Exception as e:
                import traceback
                self.error_signal.emit(f"Error during leadfield generation: {str(e)}")
                self.error_signal.emit(traceback.format_exc())
                self.finished_signal.emit(False, "")
                
        except Exception as e:
            import traceback
            self.error_signal.emit(f"Error initializing leadfield generation: {str(e)}")
            self.error_signal.emit(traceback.format_exc())
            self.finished_signal.emit(False, "")
    
    def terminate_process(self):
        """Terminate the leadfield generation."""
        self.terminated = True
        if self.generator:
            # The generator checks termination_flag during generation
            pass


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
                    line_stripped = line.strip()

                    # Detect message type based on content
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
                except (OSError, AttributeError):
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
                except (subprocess.CalledProcessError, OSError, ValueError):
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
        self.leadfield_generating = False
        self.leadfield_thread = None
        # Initialize debug mode (default to False)
        self.debug_mode = False
        # Initialize summary mode and timing trackers for non-debug summaries
        self.SUMMARY_MODE = True
        self.EXSEARCH_START_TIME = None
        self.ROI_START_TIMES = {}
        self.STEP_START_TIMES = {}
        
        # Initialize path manager
        self.pm = get_path_manager()
        
        # Load ROI presets
        self.presets = {}
        self.load_presets()
        
        self.setup_ui()
        
        # Initialize with available subjects and check leadfields
        QtCore.QTimer.singleShot(500, self.initial_setup)
    
    def load_presets(self):
        """Load ROI presets from resources/roi_presets.json"""
        try:
            # Get path to resources directory (project root / resources)
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ti-toolbox/gui -> ti-toolbox
            project_root = os.path.dirname(script_dir)  # ti-toolbox -> project root
            presets_file = os.path.join(project_root, 'resources', 'roi_presets.json')
            
            if os.path.exists(presets_file):
                with open(presets_file, 'r') as f:
                    data = json.load(f)
                    self.presets = data.get('regions', {})
            else:
                # Fallback to opt directory (old location for backward compatibility)
                presets_file = os.path.join(script_dir, 'opt', 'roi_presets.json')
                if os.path.exists(presets_file):
                    with open(presets_file, 'r') as f:
                        data = json.load(f)
                        self.presets = data.get('regions', {})
                else:
                    print(f"Warning: roi_presets.json not found in resources or opt directories")
                    self.presets = {}
        except Exception as e:
            print(f"Error loading ROI presets: {e}")
            self.presets = {}
    
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
        
        self.update_output(f"├─ Optimization run {run_number}/{total_runs}: Started", 'info')
    
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
            self.update_output(f"Results available in: {output_dir}", 'success')
        else:
            self.update_output(f"└─ Ex-search optimization completed successfully for subject: {subject_id} ({total_rois} ROI(s))", 'success')
            self.update_output(f"Results available in: {output_dir}", 'success')
    
    def create_log_file_env(self, process_name, subject_id):
        """Create log file environment variable for processes."""
        try:
            # Create timestamp for log file
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            
            # Get project directory structure
            project_dir = self.pm.get_project_dir() if hasattr(self, 'pm') else get_path_manager().get_project_dir()
            derivatives_dir = os.path.join(project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
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
            config_logger = logging_util.get_file_only_logger('Ex-Search-Config-File-Only', log_file)
            
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
            except OSError:
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
            config_logger.info("  2. ROI Analysis (ex_analyzer.py with integrated field analysis)")
            
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
            roi_logger = logging_util.get_file_only_logger('Ex-Search-ROI-File-Only', log_file)
            
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
            roi_logger.info(f"  2. ROI Analysis → Extract TImax/TImean and generate final CSV")
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
            project_dir = self.pm.get_project_dir() if hasattr(self, 'pm') else get_path_manager().get_project_dir()
            derivatives_dir = os.path.join(project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
            
            # Find the most recent ex_search log file
            if os.path.exists(log_dir):
                ex_search_logs = [f for f in os.listdir(log_dir) if f.startswith('ex_search_') and f.endswith('.log')]
                if ex_search_logs:
                    # Use the most recent log file
                    latest_log = os.path.join(log_dir, sorted(ex_search_logs)[-1])
                    
                    # Create a file-only logger for completion details (no console output)
                    completion_logger = logging_util.get_file_only_logger('Ex-Search-Completion-File-Only', latest_log)
                    
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
                                    completion_logger.info(f"  {i+1}. {roi_file} → derivatives/{output_dir}/")
                                else:
                                    completion_logger.info(f"  {i+1}. {roi_file}")
                            except (KeyError, AttributeError, RuntimeError):
                                completion_logger.info(f"  {i+1}. {roi_file}")
                    
                    # Log electrode configuration summary
                    if hasattr(self, 'e1_plus') and hasattr(self, 'e1_minus'):
                        completion_logger.info("Electrode Configuration:")
                        completion_logger.info(f"  Total electrode combinations per ROI: {len(self.e1_plus)}")
                        completion_logger.info(f"  Total simulations completed: {len(self.roi_processing_queue) * len(self.e1_plus)}")
                    
                    # Note where results can be found
                    completion_logger.info("Output Location:")
                    completion_logger.info(f"  Results stored in: {project_dir}/derivatives/SimNIBS/sub-{subject_id}/derivatives/")
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
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.hide()  # Initially hidden
        main_layout.addWidget(self.status_label)
        
        # Create a scroll area for the form (matching other tabs)
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        scroll_layout.setSpacing(10)
        
        # Main grid layout for organized component placement
        main_grid_layout = QtWidgets.QGridLayout()
        main_grid_layout.setSpacing(15)  # Add spacing between components
        
        # ============================================================
        # ROW 0, COLUMN 0: Subject Selection
        # ============================================================
        subject_container = QtWidgets.QGroupBox("Subject Selection")
        subject_container.setFixedHeight(180)  # Match electrode selection height
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
        
        # Add stretch to push content to top
        subject_layout.addStretch()
        
        # Add subject container to grid - Row 0, Column 0
        main_grid_layout.addWidget(subject_container, 0, 0)
        
        # ============================================================
        # ROW 0, COLUMN 1: Electrode Selection
        # ============================================================
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
        
        # Add electrode container to grid - Row 0, Column 1
        main_grid_layout.addWidget(electrode_container, 0, 1)
        
        # ============================================================
        # ROW 1, COLUMN 0: ROI Selection
        # ============================================================
        roi_container = QtWidgets.QGroupBox("ROI Selection")
        roi_container.setFixedHeight(190)  # Fixed height for balance (includes radius control)
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
        
        # ROI radius parameter
        radius_layout = QtWidgets.QHBoxLayout()
        radius_label = QtWidgets.QLabel("ROI Radius (mm):")
        radius_label.setFixedWidth(100)
        self.roi_radius_spinbox = QtWidgets.QDoubleSpinBox()
        self.roi_radius_spinbox.setRange(1.0, 10.0)
        self.roi_radius_spinbox.setValue(3.0)  # Default 3mm
        self.roi_radius_spinbox.setSingleStep(0.5)
        self.roi_radius_spinbox.setDecimals(1)
        self.roi_radius_spinbox.setToolTip("Radius of spherical ROI for field extraction (default: 3.0mm)")
        radius_layout.addWidget(radius_label)
        radius_layout.addWidget(self.roi_radius_spinbox)
        radius_layout.addStretch()
        roi_layout.addLayout(radius_layout)
        
        # Add ROI container to grid - Row 1, Column 0
        main_grid_layout.addWidget(roi_container, 1, 0)
        
        # ============================================================
        # ROW 1, COLUMN 1: Current Configuration
        # ============================================================
        current_container = QtWidgets.QGroupBox("Current Configuration")
        current_container.setFixedHeight(190)  # Match ROI selection height
        current_layout = QtWidgets.QVBoxLayout(current_container)
        current_layout.setContentsMargins(10, 10, 10, 10)
        current_layout.setSpacing(8)

        # Total current input
        total_current_layout = QtWidgets.QHBoxLayout()
        total_current_label = QtWidgets.QLabel("Total Current (mA):")
        total_current_label.setFixedWidth(120)
        self.total_current_spinbox = QtWidgets.QDoubleSpinBox()
        self.total_current_spinbox.setRange(0.1, 10.0)
        self.total_current_spinbox.setValue(2.0)  # Default 2mA (per user example)
        self.total_current_spinbox.setSingleStep(0.1)
        self.total_current_spinbox.setDecimals(1)
        self.total_current_spinbox.setToolTip("Total current to distribute between channels")
        total_current_layout.addWidget(total_current_label)
        total_current_layout.addWidget(self.total_current_spinbox)
        total_current_layout.addStretch()
        current_layout.addLayout(total_current_layout)

        # Current step size input
        current_step_layout = QtWidgets.QHBoxLayout()
        current_step_label = QtWidgets.QLabel("Current Step (mA):")
        current_step_label.setFixedWidth(120)
        self.current_step_spinbox = QtWidgets.QDoubleSpinBox()
        self.current_step_spinbox.setRange(0.01, 2.0)
        self.current_step_spinbox.setValue(0.2)  # Default 0.2mA (per user example)
        self.current_step_spinbox.setSingleStep(0.01)
        self.current_step_spinbox.setDecimals(2)
        self.current_step_spinbox.setToolTip("Step size for current ratio iterations")
        current_step_layout.addWidget(current_step_label)
        current_step_layout.addWidget(self.current_step_spinbox)
        current_step_layout.addStretch()
        current_layout.addLayout(current_step_layout)

        # Channel limit input
        channel_limit_layout = QtWidgets.QHBoxLayout()
        channel_limit_label = QtWidgets.QLabel("Channel Limit (mA):")
        channel_limit_label.setFixedWidth(120)
        self.channel_limit_spinbox = QtWidgets.QDoubleSpinBox()
        self.channel_limit_spinbox.setRange(0.1, 10.0)
        self.channel_limit_spinbox.setValue(1.6)  # Default 1.6mA (per user example)
        self.channel_limit_spinbox.setSingleStep(0.1)
        self.channel_limit_spinbox.setDecimals(1)
        self.channel_limit_spinbox.setToolTip("Maximum current per channel (must be ≤ total current)")
        channel_limit_layout.addWidget(channel_limit_label)
        channel_limit_layout.addWidget(self.channel_limit_spinbox)
        channel_limit_layout.addStretch()
        current_layout.addLayout(channel_limit_layout)
        
        # Add stretch to push content to top
        current_layout.addStretch()

        # Add current container to grid - Row 1, Column 1
        main_grid_layout.addWidget(current_container, 1, 1)
        
        # ============================================================
        # ROW 2, COLUMN 0-1: Leadfield Management (spanning both columns)
        # ============================================================
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
        
        # Add leadfield container to grid - Row 2, Column 0-1 (spanning both columns)
        main_grid_layout.addWidget(leadfield_container, 2, 0, 1, 2)
        
        # Add grid layout to scroll layout
        scroll_layout.addLayout(main_grid_layout)
        
        # Set scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(self, run_text="Run Ex-Search", stop_text="Stop Ex-Search")
        self.action_buttons.connect_run(self.run_optimization)
        self.action_buttons.connect_stop(self.stop_optimization)
        
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
        self.console_output = self.console_widget.get_console_widget()
        
        # After self.subject_combo is created and added:
        self.subject_combo.currentTextChanged.connect(self.on_subject_selection_changed)
    
    def initial_setup(self):
        """Initial setup when the tab is first loaded."""
        self.list_subjects()
        if self.debug_mode:
            self.update_output("Welcome to Ex-Search Optimization!")
            self.update_output("\nChecking available subjects and leadfields...")
        
        try:
            from opt.leadfield import LeadfieldGenerator
            
            pm = self.pm if hasattr(self, 'pm') else get_path_manager()
            
            # Get list of subjects
            subjects = []
            simnibs_dir = pm.get_simnibs_dir()
            if os.path.exists(simnibs_dir):
                for item in os.listdir(simnibs_dir):
                    if item.startswith("sub-"):
                        subject_id = item[4:]  # Remove 'sub-' prefix
                        subjects.append(subject_id)
            
            subject_count = len(subjects)
            total_leadfields = 0
            subjects_with_leadfields = {}
            
            # Use LeadfieldGenerator to count leadfields for each subject
            for subject_id in subjects:
                try:
                    m2m_dir = pm.get_m2m_dir(subject_id)
                    if m2m_dir and os.path.exists(m2m_dir):
                        gen = LeadfieldGenerator(m2m_dir)
                        leadfields = gen.list_available_leadfields_hdf5(subject_id)
                        
                        if leadfields:
                            # Extract net names from leadfield list
                            net_names = [net_name for net_name, _, _ in leadfields]
                            subjects_with_leadfields[subject_id] = net_names
                            total_leadfields += len(leadfields)
                except Exception:
                    # Skip subjects with errors
                    pass
            
            # Display summary only in debug mode
            if self.debug_mode:
                self.update_output(f"\nFound {subject_count} subject(s):")
                self.update_output(f"- Total leadfield matrices: {total_leadfields}")
                self.update_output(f"- Subjects with leadfields: {len(subjects_with_leadfields)}")
                
                for subject_id, nets in subjects_with_leadfields.items():
                    self.update_output(f"  {subject_id}: {', '.join(nets)}")
                
                subjects_without_leadfield = [sid for sid in subjects 
                                            if sid not in subjects_with_leadfields]
                if subjects_without_leadfield:
                    self.update_output(f"- Subjects without leadfields: {', '.join(subjects_without_leadfield)}")
                
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

        try:
            # Get subject's m2m directory for LeadfieldGenerator
            pm = self.pm if hasattr(self, 'pm') else get_path_manager()
            m2m_dir = pm.get_m2m_dir(subject_id)

            # Use LeadfieldGenerator to list available leadfields
            from opt.leadfield import LeadfieldGenerator
            gen = LeadfieldGenerator(m2m_dir)
            leadfields = gen.list_available_leadfields_hdf5(subject_id)

            # Populate the list
            for net_name, hdf5_path, file_size in leadfields:
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
        pm = self.pm if hasattr(self, 'pm') else get_path_manager()
        eeg_positions_dir = pm.get_eeg_positions_dir(subject_id)
        
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
        """Create leadfield with selected EEG net using thread-based approach."""
        if self.leadfield_generating:
            QtWidgets.QMessageBox.warning(self, "Already Running", "Leadfield generation is already running")
            return
        
        # Get project directory
        project_dir = self.pm.get_project_dir()
        if not project_dir or not os.path.exists(project_dir):
            QtWidgets.QMessageBox.warning(self, "No Project", "Project directory not found")
            return
        
        # Clean net name
        net_name_clean = eeg_net_file.replace('.csv', '')
        
        # Show confirmation dialog
        reply = QtWidgets.QMessageBox.question(
            self,
            "Leadfield Generation",
            f"Generate leadfield for {eeg_net_file}?\n\n"
            f"This process may take 5-15 minutes depending on mesh size and electrode count.\n\n"
            f"Files will be saved to: derivatives/SimNIBS/sub-{subject_id}/leadfields/\n\n"
            "Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Clear console and start generation
        self.console_output.clear()
        self.update_output("="*60, 'default')
        self.update_output("LEADFIELD GENERATION", 'info')
        self.update_output("="*60, 'default')
        
        # Set UI state
        self.leadfield_generating = True
        self.disable_controls()
        
        # Start generation thread
        self.leadfield_thread = LeadfieldGenerationThread(subject_id, eeg_net_file, project_dir, self)
        self.leadfield_thread.output_signal.connect(self.update_output)
        self.leadfield_thread.error_signal.connect(lambda msg: self.update_output(msg, 'error'))
        self.leadfield_thread.finished_signal.connect(self.leadfield_generation_finished)
        self.leadfield_thread.start()
    
    def leadfield_generation_finished(self, success, hdf5_path):
        """Handle leadfield generation completion."""
        self.leadfield_generating = False
        self.enable_controls()
        
        if success:
            self.update_output("", 'default')
            self.update_output("="*60, 'default')
            self.update_output("Leadfield generation completed successfully!", 'success')
            self.update_output("="*60, 'default')
            
            # Refresh the leadfield list to show the new leadfield
            self.refresh_leadfields()
            
            # Show success message
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                "Leadfield generation completed!\n\n"
                f"File saved:\n"
                f"• {os.path.basename(hdf5_path)}"
            )
        else:
            self.update_output("Leadfield generation failed or was cancelled", 'error')
    
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
        
        # Use consolidated helper function
        pm = self.pm if hasattr(self, 'pm') else None
        _get_and_display_electrodes(subject_id, net_name, self, path_manager=pm)
    
    def list_subjects(self):
        """List available subjects in the combo box."""
        self.subject_combo.clear()
        project_dir = self.pm.get_project_dir() if hasattr(self, 'pm') else get_path_manager().get_project_dir()
        if not project_dir or not os.path.exists(project_dir):
            self.update_status("No project directory selected", error=True)
            return
            
        subjects_dir = self.pm.get_simnibs_dir() if hasattr(self, 'pm') else get_path_manager().get_simnibs_dir()
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
            
            pm = self.pm if hasattr(self, 'pm') else get_path_manager()
            m2m_dir = pm.get_m2m_dir(subject_id)
            roi_dir = os.path.join(m2m_dir, "ROIs") if m2m_dir else None
            
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
                pm = get_path_manager()
                m2m_dir = pm.get_m2m_dir(selected_subject)
                roi_dir = os.path.join(m2m_dir, "ROIs") if m2m_dir else None
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
        project_dir = self.pm.get_project_dir() if hasattr(self, 'pm') else get_path_manager().get_project_dir()
        pm = self.pm if hasattr(self, 'pm') else get_path_manager()
        ex_search_dir = pm.get_ex_search_dir(subject_id)
        
        # Show confirmation dialog
        selected_rois = self.roi_list.selectedItems()
        roi_names = [item.text().split(':')[0].strip() for item in selected_rois]
        details = f"Subject: {subject_id}\nROIs: {', '.join(roi_names)}\nNumber of ROIs: {len(roi_names)}"
        
        if not ConfirmationDialog.confirm(
            self,
            title="Confirm Ex-Search Optimization",
            message="Are you sure you want to start the ex-search optimization?",
            details=details
        ):
            return
        
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
        ex_search_scripts_dir = os.path.join(script_dir, "opt", "ex")
        
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
        pm = self.pm if hasattr(self, 'pm') else get_path_manager()
        m2m_dir = pm.get_m2m_dir(subject_id)
        roi_dir = os.path.join(m2m_dir, "ROIs") if m2m_dir else None
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
        env["ROI_RADIUS"] = str(self.roi_radius_spinbox.value())  # Get radius from UI
        env["TOTAL_CURRENT"] = str(self.total_current_spinbox.value())  # Total current from UI
        env["CURRENT_STEP"] = str(self.current_step_spinbox.value())    # Current step from UI
        env["CHANNEL_LIMIT"] = str(self.channel_limit_spinbox.value())  # Channel limit from UI
        
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
        
        # Check for existing ROI-specific output directory and confirm overwrite
        output_dir_name = f"{roi_name}_{selected_net_name}"
        roi_output_dir = os.path.join(ex_search_dir, output_dir_name)
        
        if os.path.exists(roi_output_dir) and os.listdir(roi_output_dir):
            if not confirm_overwrite(self, roi_output_dir, f"ROI search directory '{output_dir_name}'"):
                # Skip to next ROI
                self.current_roi_index += 1
                self.run_roi_pipeline(subject_id, project_dir, ex_search_dir, env)
                return
            else:
                # User confirmed overwrite - remove existing directory
                import shutil
                try:
                    shutil.rmtree(roi_output_dir)
                    self.update_output(f"Removed existing directory: {output_dir_name}")
                except Exception as e:
                    self.update_output(f"Error removing existing directory: {str(e)}", 'error')
        
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
            str(self.total_current_spinbox.value()),  # Total current
            str(self.current_step_spinbox.value()),   # Current step
            str(self.channel_limit_spinbox.value())   # Channel limit
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
        pm = self.pm if hasattr(self, 'pm') else get_path_manager()
        ex_search_dir = pm.get_ex_search_dir(subject_id)
        mesh_dir = os.path.join(ex_search_dir, output_dir_name) if ex_search_dir else None
        
        # Create temporary roi_list.txt with just the current ROI for ex_analyzer.py
        roi_dir = env.get("ROI_DIR")
        temp_roi_list = os.path.join(roi_dir, "temp_roi_list.txt")
        
        try:
            with open(temp_roi_list, 'w') as f:
                f.write(f"{current_roi}\n")
            
            # Run ROI analyzer script
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ex_search_scripts_dir = os.path.join(script_dir, "opt", "ex")
            roi_analyzer_script = os.path.join(ex_search_scripts_dir, "ex_analyzer.py")
            
            # Update environment variables for ROI analyzer
            roi_env = env.copy()
            roi_env["MESH_DIR"] = mesh_dir
            roi_env["ROI_LIST_FILE"] = temp_roi_list
            
            cmd = ["simnibs_python", roi_analyzer_script, roi_dir]
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
        """Handle completion of mesh processing (integrated into ROI analysis).
        
        Note: Step 3 (mesh_field_analyzer.py) has been integrated into Step 2 (ex_analyzer.py).
        The new ex_analyzer.py uses the unified analyzer module which handles all field analysis.
        This method now just logs completion and moves to the next ROI.
        """
        current_roi = self.roi_processing_queue[self.current_roi_index]
        roi_name = current_roi.replace('.csv', '')
        eeg_net_name = env.get("SELECTED_EEG_NET", "unknown_net")
        
        # Log mesh processing step completion (already done in ROI analysis)
        self.log_step_start("Mesh processing")
        if self.debug_mode:
            self.update_output("\nStep 3: Mesh processing integrated into ROI analysis", 'info')
            output_dir_name = f"{roi_name}_{eeg_net_name}"
            self.update_output(f"Output directory: derivatives/{output_dir_name}/", 'info')
        
        self.log_step_complete("Mesh processing", success=True)
        
        # Move to next ROI
        self.current_roi_completed(subject_id, project_dir, ex_search_dir, env)
    
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
    
    
    def handle_process_error(self, error_msg):
        """Handle process errors with proper GUI state management."""
        self.update_output(error_msg, 'error')
        self.enable_controls()
        self.update_status("Process failed - see console for details", error=True)
    
    def pipeline_completed(self):
        """Handle the completion of the pipeline."""
        # Log completion summary
        self.log_pipeline_completion()
        
        # Log final completion with summary
        subject_id = self.subject_combo.currentText()
        total_rois = len(self.roi_processing_queue)
        project_dir = self.pm.get_project_dir() if hasattr(self, 'pm') else get_path_manager().get_project_dir()
        pm = self.pm if hasattr(self, 'pm') else get_path_manager()
        ex_search_dir = pm.get_ex_search_dir(subject_id)
        
        self.log_exsearch_complete(subject_id, total_rois, ex_search_dir)
        
        # Final message for debug mode
        if self.debug_mode:
            self.update_output("\nOptimization process completed!")
        
        self.enable_controls()
        self.update_status("Ex-search optimization completed successfully")
    
    def stop_optimization(self):
        """Stop the running optimization or leadfield generation process."""
        # Check if leadfield generation is running
        if self.leadfield_generating and self.leadfield_thread:
            self.leadfield_thread.terminate_process()
            self.leadfield_thread.wait()
            self.leadfield_generating = False
            self.update_status("Leadfield generation stopped by user")
            self.update_output("Leadfield generation terminated by user", 'warning')
            self.enable_controls()
            return
        
        # Otherwise check for optimization process
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
            # Colorize summary lines: blue for starts, white for completes, green for final
            lower = text.lower()
            is_final = lower.startswith('└─') or 'completed successfully' in lower
            is_start = lower.startswith('beginning ') or ': starting' in lower
            is_complete = ('✓ complete' in lower) or ('results available in:' in lower) or ('saved to' in lower)
            color = '#55ff55' if is_final else ('#55aaff' if is_start else '#ffffff')
            formatted_text = f'<span style="color: {color};">{text}</span>'
            scrollbar = self.console_output.verticalScrollBar()
            at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
            self.console_output.append(formatted_text)
            if at_bottom:
                self.console_output.ensureCursorVisible()
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
        # Only update status during processing
        # Don't show status for completion messages
        if "completed" in message.lower() or "finished" in message.lower():
            self.status_label.hide()
            return
            
        self.status_label.setText(message)
        if error:
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
        else:
            # Use same red color for processing status as other tabs
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
        self.status_label.show()
    
    def disable_controls(self):
        """Disable controls during optimization or leadfield generation."""
        self.subject_combo.setEnabled(False)
        self.roi_list.setEnabled(False)
        self.roi_radius_spinbox.setEnabled(False)
        self.e1_plus_input.setEnabled(False)
        self.e1_minus_input.setEnabled(False)
        self.e2_plus_input.setEnabled(False)
        self.e2_minus_input.setEnabled(False)
        self.total_current_spinbox.setEnabled(False)
        self.current_step_spinbox.setEnabled(False)
        self.channel_limit_spinbox.setEnabled(False)
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
        
        # Keep debug checkbox enabled during processing
        if hasattr(self, 'console_widget') and hasattr(self.console_widget, 'debug_checkbox'):
            self.console_widget.debug_checkbox.setEnabled(True)
        
        # Show status label when processing starts
        if self.leadfield_generating:
            self.status_label.setText("Generating leadfield... Stop button and Debug Mode are available")
        else:
            self.status_label.setText("Processing... Stop button and Debug Mode are available")
        self.status_label.show()
    
    def enable_controls(self):
        """Enable controls after optimization."""
        self.subject_combo.setEnabled(True)
        self.roi_list.setEnabled(True)
        self.roi_radius_spinbox.setEnabled(True)
        self.e1_plus_input.setEnabled(True)
        self.e1_minus_input.setEnabled(True)
        self.e2_plus_input.setEnabled(True)
        self.e2_minus_input.setEnabled(True)
        self.total_current_spinbox.setEnabled(True)
        self.current_step_spinbox.setEnabled(True)
        self.channel_limit_spinbox.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.list_subjects_btn.setEnabled(True)
        self.clear_subject_selection_btn.setEnabled(True)
        self.add_roi_btn.setEnabled(True)
        self.remove_roi_btn.setEnabled(True)
        self.list_rois_btn.setEnabled(True)
        self.leadfield_list.setEnabled(True)
        self.status_label.hide()  # Hide status label when processing ends
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
    """Dialog for adding a new ROI with preset or custom coordinates."""
    
    def __init__(self, parent=None):
        super(AddROIDialog, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Add New ROI")
        layout = QtWidgets.QVBoxLayout(self)
        
        # ROI type selection (Preset or Custom)
        type_group = QtWidgets.QGroupBox("ROI Source")
        type_layout = QtWidgets.QVBoxLayout()
        
        self.preset_radio = QtWidgets.QRadioButton("Use Preset (MNI coordinates)")
        self.preset_radio.setChecked(True)
        self.preset_radio.toggled.connect(self.toggle_roi_source)
        self.custom_radio = QtWidgets.QRadioButton("Custom Coordinates (Subject space)")
        
        type_layout.addWidget(self.preset_radio)
        type_layout.addWidget(self.custom_radio)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Preset selection
        self.preset_group = QtWidgets.QGroupBox("Select Preset ROI")
        preset_layout = QtWidgets.QVBoxLayout()
        
        self.preset_combo = QtWidgets.QComboBox()
        if hasattr(self.parent, 'presets') and self.parent.presets:
            for preset_key in sorted(self.parent.presets.keys()):
                preset_data = self.parent.presets[preset_key]
                display_name = f"{preset_data['name']} ({preset_key})"
                self.preset_combo.addItem(display_name, preset_key)
        else:
            self.preset_combo.addItem("No presets available")
            self.preset_combo.setEnabled(False)
        
        preset_layout.addWidget(self.preset_combo)
        self.preset_group.setLayout(preset_layout)
        layout.addWidget(self.preset_group)
        
        # Custom coordinates
        self.coord_group = QtWidgets.QGroupBox("Custom ROI Coordinates (subject space, RAS)")
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
        
        self.coord_group.setLayout(coord_layout)
        layout.addWidget(self.coord_group)
        
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
        
        # Initial visibility
        self.toggle_roi_source()
    
    def toggle_roi_source(self):
        """Toggle between preset and custom coordinate input."""
        is_preset = self.preset_radio.isChecked()
        self.preset_group.setVisible(is_preset)
        self.coord_group.setVisible(not is_preset)
    
    def load_t1_in_freeview(self):
        """Load the subject's T1 NIfTI file in Freeview."""
        try:
            subject_id = self.parent.subject_combo.currentText()
            if not subject_id:
                QtWidgets.QMessageBox.warning(self, "Error", "Please select a subject first")
                return
            project_dir = self.pm.get_project_dir() if hasattr(self, 'pm') else get_path_manager().get_project_dir()
            pm = self.pm if hasattr(self, 'pm') else get_path_manager()
            t1_path = pm.get_t1_path(subject_id)
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
            pm = self.pm if hasattr(self, 'pm') else get_path_manager()
            m2m_dir = pm.get_m2m_dir(subject_id)
            roi_dir = os.path.join(m2m_dir, "ROIs") if m2m_dir else None
            
            os.makedirs(roi_dir, exist_ok=True)
            
            # Get coordinates based on selection type
            if self.preset_radio.isChecked():
                # Using preset - need to transform MNI to subject space
                preset_key = self.preset_combo.currentData()
                if not preset_key or preset_key not in self.parent.presets:
                    QtWidgets.QMessageBox.warning(self, "Error", "Invalid preset selection")
                    return
                
                mni_coords = self.parent.presets[preset_key]['mni']
                
                # Transform MNI coordinates to subject space
                try:
                    from opt.roi import ROICoordinateHelper
                    subject_coords = ROICoordinateHelper.transform_mni_to_subject(mni_coords, m2m_dir)
                    x, y, z = subject_coords[0], subject_coords[1], subject_coords[2]
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", 
                        f"Failed to transform MNI coordinates to subject space:\n{str(e)}\n\n"
                        f"Make sure SimNIBS is properly installed.")
                    return
            else:
                # Using custom coordinates (already in subject space)
                x = self.x_coord.value()
                y = self.y_coord.value()
                z = self.z_coord.value()
            
            # Format coordinates to two decimal places
            x = round(x, 2)
            y = round(y, 2)
            z = round(z, 2)

            # Write coordinates to ROI file as three comma-separated columns
            roi_file = os.path.join(roi_dir, roi_name)
            with open(roi_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([x, y, z])
            
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
        
        # Use consolidated helper function
        # Get path manager from parent if available, otherwise use default
        pm = None
        if self.parent and hasattr(self.parent, 'pm'):
            pm = self.parent.pm
        _get_and_display_electrodes(self.subject_id, selected_net, self, path_manager=pm)
    
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
        # Include WindowCloseButtonHint to ensure the X button is visible and functional
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.WindowCloseButtonHint)
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