#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-Toolbox MOVEA Tab
GUI interface for MOVEA-based TI electrode optimization
"""

import os
import sys
import json
import re
import subprocess
import time
import logging
from pathlib import Path

# Add project root to path for tools import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt5 import QtWidgets, QtCore, QtGui
from utils import is_verbose_message, is_important_message
from components.console import ConsoleWidget
from components.action_buttons import RunStopButtons
from core import get_path_manager
from tools import logging_util


class LeadfieldGenerationThread(QtCore.QThread):
    """Thread to run leadfield generation as subprocess (like ex-search for instant termination)."""
    
    # Signals
    output_signal = QtCore.pyqtSignal(str, str)  # message, type
    error_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(bool, str, str)  # success, lfm_path, pos_path
    
    def __init__(self, subject_id, eeg_net_file, project_dir, parent=None):
        super(LeadfieldGenerationThread, self).__init__(parent)
        self.subject_id = subject_id
        self.eeg_net_file = eeg_net_file
        self.project_dir = project_dir
        self.terminated = False
        self.process = None
        
    def run(self):
        """Run leadfield generation as subprocess for instant termination."""
        try:
            self.output_signal.emit("Initializing leadfield generation...", 'info')
            
            # Prepare command to run leadfield script as subprocess
            leadfield_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          'opt', 'movea', 'leadfield_script.py')
            
            pm = get_path_manager()
            m2m_dir = pm.get_m2m_dir(self.subject_id)
            
            if not m2m_dir or not os.path.exists(m2m_dir):
                self.error_signal.emit(f"m2m directory not found for subject {self.subject_id}")
                self.finished_signal.emit(False, "", "")
                return
            
            # Setup environment and log file
            import time
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            derivatives_dir = os.path.join(self.project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{self.subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f'MOVEA_leadfield_{time_stamp}.log')
            
            env = os.environ.copy()
            env['TI_LOG_FILE'] = log_file
            
            self.output_signal.emit(f"Log file: {log_file}", 'info')
            self.output_signal.emit(f"Subject: {self.subject_id}", 'info')
            self.output_signal.emit(f"EEG Net: {self.eeg_net_file}", 'info')
            self.output_signal.emit(f"m2m directory: {m2m_dir}", 'info')
            
            # Prepare command to run as subprocess
            cmd = ["simnibs_python", leadfield_script, m2m_dir, self.eeg_net_file, self.project_dir]
            
            self.output_signal.emit("", 'default')
            self.output_signal.emit("Starting leadfield generation subprocess...", 'info')
            
            # Run as subprocess (like ex-search does for instant termination)
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                env=env
            )
            
            # Track paths for success
            lfm_path = ""
            pos_path = ""
            
            # Real-time output display
            for line in iter(self.process.stdout.readline, ''):
                if self.terminated:
                    break
                if line:
                    line_stripped = line.strip()
                    
                    # Capture output paths from script
                    if line_stripped.startswith("LFM_PATH:"):
                        lfm_path = line_stripped.replace("LFM_PATH:", "")
                        continue
                    elif line_stripped.startswith("POS_PATH:"):
                        pos_path = line_stripped.replace("POS_PATH:", "")
                        continue
                    
                    # Detect message type
                    if any(keyword in line_stripped.lower() for keyword in ['error:', 'failed', 'exception']):
                        message_type = 'error'
                    elif any(keyword in line_stripped.lower() for keyword in ['warning:', 'warn']):
                        message_type = 'warning'
                    elif any(keyword in line_stripped.lower() for keyword in ['complete!', 'success', 'saved:']):
                        message_type = 'success'
                    else:
                        message_type = 'default'
                    
                    self.output_signal.emit(line_stripped, message_type)
            
            # Check process completion
            if not self.terminated:
                returncode = self.process.wait()
                if returncode == 0 and lfm_path and pos_path:
                    self.finished_signal.emit(True, lfm_path, pos_path)
                else:
                    self.error_signal.emit(f"Process returned exit code: {returncode}")
                    self.finished_signal.emit(False, "", "")
            else:
                self.output_signal.emit("Leadfield generation was terminated", 'warning')
                self.finished_signal.emit(False, "", "")
            
            # Clean up process
            if self.process:
                try:
                    self.process.stdout.close()
                except (OSError, AttributeError):
                    pass
                
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.error_signal.emit(f"Error during leadfield generation: {str(e)}\n{tb}")
            self.finished_signal.emit(False, "", "")
        finally:
            # Ensure process is cleaned up
            if self.process:
                try:
                    self.process.stdout.close()
                except (OSError, AttributeError):
                    pass
    
    def terminate_process(self):
        """Terminate the leadfield generation subprocess."""
        if self.process and self.process.poll() is None:
            self.terminated = True
            if os.name == 'nt':  # Windows
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:  # Unix/Linux/Mac
                import signal
                try:
                    # Kill child processes first (SimNIBS spawns MPI processes)
                    parent_pid = self.process.pid
                    ps_output = subprocess.check_output(f"ps -o pid --ppid {parent_pid} --noheaders", shell=True)
                    child_pids = [int(pid) for pid in ps_output.decode().strip().split('\n') if pid]
                    for pid in child_pids:
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except OSError:
                            pass
                except (subprocess.CalledProcessError, OSError, ValueError):
                    pass
                
                # Terminate main process
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            
            return True
        else:
            self.terminated = True
            return False


class MOVEAOptimizationThread(QtCore.QThread):
    """Thread to run MOVEA optimization in background to prevent GUI freezing."""
    
    # Signals
    output_signal = QtCore.pyqtSignal(str, str)  # message, type
    error_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(bool)  # success
    
    def __init__(self, config, parent=None):
        super(MOVEAOptimizationThread, self).__init__(parent)
        self.config = config
        self.terminated = False
        
    def run(self):
        """Run MOVEA optimization."""
        try:
            self.output_signal.emit("Initializing MOVEA optimization...", 'info')
            
            # Import MOVEA modules
            try:
                from movea import TIOptimizer, LeadfieldGenerator, MontageFormatter, MOVEAVisualizer
                import numpy as np
                # logging_util already imported at module level
            except ImportError as e:
                self.error_signal.emit(f"Failed to import MOVEA modules: {str(e)}")
                self.finished_signal.emit(False)
                return
            
            # Setup subject-specific log file
            import time
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            subject_id = self.config['subject_id']
            pm = get_path_manager()
            log_dir = pm.get_logs_dir(subject_id)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f'MOVEA_{time_stamp}.log')
            
            # Set environment variable for external scripts
            os.environ['TI_LOG_FILE'] = log_file
            
            # Create logger
            logger = logging_util.get_logger('MOVEA', log_file, overwrite=False)
            
            # Remove console handler to prevent terminal output (GUI only shows via signals)
            logging_util.suppress_console_output(logger)
            
            # Configure external loggers (they will inherit only file handler, no console)
            logging_util.configure_external_loggers(['simnibs', 'scipy', 'mesh_io', 'sim_struct'], logger)
            
            self.output_signal.emit(f"Log file: {log_file}", 'info')
            
            # Load leadfield
            start_time = time.time()
            lfm_path = self.config['leadfield_path']
            pos_path = self.config['positions_path']
            
            if not os.path.exists(lfm_path):
                self.error_signal.emit(f"Leadfield file not found: {lfm_path}")
                self.finished_signal.emit(False)
                return
            
            if not os.path.exists(pos_path):
                self.error_signal.emit(f"Positions file not found: {pos_path}")
                self.finished_signal.emit(False)
                return
            
            self.output_signal.emit(f"Loading leadfield from: {os.path.basename(lfm_path)}", 'info')
            lfm = np.load(lfm_path)
            positions = np.load(pos_path)
            
            load_time = time.time() - start_time
            self.output_signal.emit(f"Leadfield loaded ({load_time:.1f}s): {lfm.shape[0]} electrodes, {lfm.shape[1]} voxels", 'success')
            
            if self.terminated:
                return
            
            # Create optimizer with progress callback
            self.output_signal.emit("Initializing optimizer...", 'info')
            num_electrodes = lfm.shape[0]
            
            # Create callback to redirect optimizer output to GUI
            def progress_callback(message, msg_type='info'):
                self.output_signal.emit(message, msg_type)
            
            optimizer = TIOptimizer(lfm, positions, num_electrodes, progress_callback=progress_callback)
            
            # Set target
            target = self.config['target']
            roi_radius = self.config['roi_radius_mm']
            
            if isinstance(target, list):
                target_str = f"[{', '.join(map(str, target))}]"
            else:
                target_str = target
                
            self.output_signal.emit(f"Target: {target_str} (ROI radius: {roi_radius}mm)", 'info')
            
            try:
                optimizer.set_target(target, roi_radius)
            except Exception as e:
                self.error_signal.emit(f"Failed to set target: {str(e)}")
                self.finished_signal.emit(False)
                return
            
            if self.terminated:
                return
            
            # Run optimization
            opt_method = self.config.get('opt_method', 'differential_evolution')
            generations = self.config['generations']
            population = self.config['population']
            
            self.output_signal.emit(f"Starting optimization (Method: {opt_method}, Generations: {generations}, Population: {population})...", 'info')
            self.output_signal.emit("This may take several minutes. Please wait...", 'info')
            
            opt_start = time.time()
            
            try:
                result = optimizer.optimize(
                    max_generations=generations,
                    population_size=population,
                    method=opt_method
                )
            except Exception as e:
                self.error_signal.emit(f"Optimization failed: {str(e)}")
                self.finished_signal.emit(False)
                return
            
            if self.terminated:
                return
            
            opt_time = time.time() - opt_start
            self.output_signal.emit(f"Optimization completed ({opt_time:.1f}s)", 'success')
            
            # Format results
            self.output_signal.emit("Formatting results...", 'info')
            
            # Load electrode coordinates if available
            electrode_csv = self.config.get('electrode_coords_file')
            
            # Create callback to redirect formatter output to GUI
            def progress_callback(message, msg_type='info'):
                self.output_signal.emit(message, msg_type)
            
            formatter = MontageFormatter(electrode_csv, progress_callback=progress_callback)
            
            # Check if names were loaded
            if formatter.electrode_names:
                self.output_signal.emit(f"✓ Loaded {len(formatter.electrode_names)} electrode names", 'success')
            else:
                self.output_signal.emit("⚠ Using generic electrode names (E0, E1, ...)", 'warning')
            
            montage = formatter.format_ti_montage(result, self.config['current_mA'])
            
            # Save outputs
            output_dir = self.config['output_dir']
            os.makedirs(output_dir, exist_ok=True)
            
            # Create visualizations
            self.output_signal.emit("Creating visualizations...", 'info')
            try:
                visualizer = MOVEAVisualizer(output_dir)
                
                # 1. Generate Pareto front (like original MOVEA - OPTIONAL, can be slow)
                generate_pareto = self.config.get('generate_pareto', False)
                n_pareto_solutions = self.config.get('pareto_n_solutions', 20)
                pareto_max_iter = self.config.get('pareto_max_iter', 500)
                n_pareto_cores = self.config.get('pareto_n_cores', None)
                
                if generate_pareto:
                    try:
                        # Estimate time based on cores and iterations
                        total_evals = n_pareto_solutions * pareto_max_iter
                        if n_pareto_cores and n_pareto_cores > 1:
                            est_time = max(1, (n_pareto_solutions * pareto_max_iter) // (n_pareto_cores * 250))
                            self.output_signal.emit(f"  Generating {n_pareto_solutions} Pareto solutions ({pareto_max_iter} iters each, {n_pareto_cores} cores)", 'info')
                            self.output_signal.emit(f"  Total evaluations: {total_evals:,} (est. {est_time} min)...", 'info')
                        else:
                            est_time = (n_pareto_solutions * pareto_max_iter) // 250
                            self.output_signal.emit(f"  Generating {n_pareto_solutions} Pareto solutions ({pareto_max_iter} iters each, serial)", 'info')
                            self.output_signal.emit(f"  Total evaluations: {total_evals:,} (est. {est_time} min)...", 'info')
                        
                        pareto_solutions = optimizer.generate_pareto_solutions(
                            n_solutions=n_pareto_solutions,
                            max_iter_per_solution=pareto_max_iter,
                            n_cores=n_pareto_cores
                        )
                        
                        # Only create visualizations if we got valid solutions
                        if pareto_solutions and len(pareto_solutions) > 0:
                            # Plot Pareto front
                            pareto_path = os.path.join(output_dir, 'pareto_front.png')
                            target_name = self.config.get('target_name', 'ROI')
                            visualizer.plot_pareto_front(pareto_solutions, save_path=pareto_path, target_name=target_name)
                            self.output_signal.emit(f"  ✓ Pareto front plot: {os.path.basename(pareto_path)}", 'success')
                            
                            # Save Pareto solutions to CSV with electrode names and focality ratio
                            pareto_csv = os.path.join(output_dir, 'pareto_solutions.csv')
                            with open(pareto_csv, 'w') as f:
                                f.write("Solution,Electrode1,Electrode2,Electrode3,Electrode4,ROI_Field_Vm,WholeBrain_Field_Vm,Focality_Ratio\n")
                                for i, sol in enumerate(pareto_solutions):
                                    # Get electrode names if available
                                    e_indices = sol['electrodes']
                                    if formatter.electrode_names and len(formatter.electrode_names) > max(e_indices):
                                        e_names = [formatter.electrode_names[idx] for idx in e_indices]
                                    else:
                                        e_names = [f"E{idx}" for idx in e_indices]
                                    
                                    # Calculate focality ratio (ROI field / Whole brain field)
                                    focality_ratio = sol['intensity_field'] / sol['focality'] if sol['focality'] > 0 else 0
                                    
                                    f.write(f"{i+1},{e_names[0]},{e_names[1]},{e_names[2]},{e_names[3]},{sol['intensity_field']:.6f},{sol['focality']:.6f},{focality_ratio:.4f}\n")
                            self.output_signal.emit(f"  ✓ Pareto solutions: {os.path.basename(pareto_csv)}", 'success')
                        else:
                            self.output_signal.emit(f"  ⚠ Pareto generation returned no valid solutions", 'warning')
                        
                    except Exception as pareto_err:
                        import traceback
                        self.output_signal.emit(f"  ⚠ Pareto front generation failed: {str(pareto_err)}", 'warning')
                        self.output_signal.emit(f"  {traceback.format_exc()}", 'debug')
                else:
                    self.output_signal.emit("  ⓘ Pareto front generation disabled (enable in GUI to generate)", 'info')
                
            except Exception as viz_error:
                self.output_signal.emit(f"Warning: Visualization failed: {str(viz_error)}", 'warning')
                # Continue even if visualization fails
            
            output_csv = os.path.join(output_dir, 'movea_montage.csv')
            output_txt = os.path.join(output_dir, 'movea_montage.txt')
            
            formatter.save_montage_csv(montage, output_csv)
            formatter.save_montage_simnibs(montage, output_txt)
            
            # Print summary
            self.output_signal.emit("", 'default')
            self.output_signal.emit("="*60, 'default')
            self.output_signal.emit("MOVEA OPTIMIZATION COMPLETE", 'success')
            self.output_signal.emit("="*60, 'default')
            
            pair1 = montage['pair1']
            pair2 = montage['pair2']
            opt_info = montage['optimization']
            
            self.output_signal.emit(f"Pair 1: {pair1['anode']['name']} (+{pair1['current_mA']}mA) ↔ {pair1['cathode']['name']} (-{pair1['current_mA']}mA)", 'default')
            self.output_signal.emit(f"Pair 2: {pair2['anode']['name']} (+{pair2['current_mA']}mA) ↔ {pair2['cathode']['name']} (-{pair2['current_mA']}mA)", 'default')
            self.output_signal.emit(f"Field Strength: {opt_info['field_strength_V/m']:.6f} V/m", 'default')
            self.output_signal.emit(f"Optimization Cost: {opt_info['cost']:.6f}", 'default')
            self.output_signal.emit("="*60, 'default')
            self.output_signal.emit(f"Results saved to: {output_dir}", 'success')
            self.output_signal.emit(f"  • {os.path.basename(output_csv)}", 'default')
            self.output_signal.emit(f"  • {os.path.basename(output_txt)}", 'default')
            
            # List visualization files
            viz_files = [
                'pareto_front.png',  # Like original MOVEA (optional)
                'pareto_solutions.csv',  # (optional)
            ]
            for viz_file in viz_files:
                viz_path = os.path.join(output_dir, viz_file)
                if os.path.exists(viz_path):
                    self.output_signal.emit(f"  • {viz_file}", 'default')
            
            self.output_signal.emit("="*60, 'default')
            
            self.finished_signal.emit(True)
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.error_signal.emit(f"Error during optimization: {str(e)}\n{tb}")
            self.finished_signal.emit(False)
    
    def terminate_process(self):
        """Terminate the optimization."""
        self.terminated = True


class MOVEATab(QtWidgets.QWidget):
    """Tab for MOVEA optimization functionality."""
    
    def __init__(self, parent=None):
        super(MOVEATab, self).__init__(parent)
        self.parent = parent
        self.optimization_thread = None
        self.optimization_running = False
        self.leadfield_thread = None
        self.leadfield_generating = False
        self.debug_mode = False
        self.presets = {}
        
        # Initialize path manager
        self.pm = get_path_manager()
        
        # Logger will be created per-operation with subject-specific paths
        self.logger = None
            
        # Load ROI presets
        self.load_presets()
        
        self.setup_ui()
        # Initialize with available subjects
        QtCore.QTimer.singleShot(500, self.initial_setup)
    
    def load_presets(self):
        """Load ROI presets from opt/movea/presets.json"""
        try:
            presets_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                       'opt', 'movea', 'presets.json')
            if os.path.exists(presets_file):
                with open(presets_file, 'r') as f:
                    data = json.load(f)
                    self.presets = data.get('regions', {})
            else:
                # Fallback to hardcoded presets
                self.presets = {
                    'motor': {'name': 'Motor Cortex', 'mni': [47, -13, 52]},
                    'dlpfc': {'name': 'DLPFC', 'mni': [-39, 34, 37]},
                    'hippocampus': {'name': 'Hippocampus', 'mni': [-31, -20, -14]},
                }
                print(f"Warning: presets.json not found, using defaults")
        except Exception as e:
            print(f"Error loading presets: {e}")
            self.presets = {}
    
    def initial_setup(self):
        """Initial setup after UI is created."""
        self.list_subjects()
    
    def setup_ui(self):
        """Set up the user interface."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Status label at top (hidden initially)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setText("Optimizing... Only the Stop button is available")
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
        self.status_label.hide()
        main_layout.addWidget(self.status_label)
        
        # Create scroll area for form
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        scroll_layout.setSpacing(10)
        
        # Main horizontal layout
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        main_horizontal_layout.setSpacing(15)
        
        # Left side layout
        left_layout = QtWidgets.QVBoxLayout()
        
        # Subject selection
        subject_container = QtWidgets.QGroupBox("Subject Selection")
        subject_container.setFixedHeight(100)
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        subject_layout.setContentsMargins(10, 10, 10, 10)
        subject_layout.setSpacing(8)
        
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.setFixedHeight(30)
        self.subject_combo.currentIndexChanged.connect(self.on_subject_changed)
        subject_layout.addWidget(self.subject_combo)
        
        subject_button_layout = QtWidgets.QHBoxLayout()
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.setFixedHeight(25)
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        subject_button_layout.addWidget(self.list_subjects_btn)
        
        subject_layout.addLayout(subject_button_layout)
        left_layout.addWidget(subject_container)
        
        # Target Configuration
        target_container = QtWidgets.QGroupBox("Target Configuration")
        target_container.setFixedHeight(180)
        target_layout = QtWidgets.QVBoxLayout(target_container)
        target_layout.setContentsMargins(10, 10, 10, 10)
        target_layout.setSpacing(8)
        
        # Target type selection
        target_type_layout = QtWidgets.QHBoxLayout()
        self.preset_radio = QtWidgets.QRadioButton("Preset")
        self.preset_radio.setChecked(True)
        self.preset_radio.toggled.connect(self.toggle_target_type)
        self.coordinate_radio = QtWidgets.QRadioButton("MNI Coordinates")
        target_type_layout.addWidget(self.preset_radio)
        target_type_layout.addWidget(self.coordinate_radio)
        target_type_layout.addStretch()
        target_layout.addLayout(target_type_layout)
        
        # Preset target (loaded from presets.json)
        self.preset_combo = QtWidgets.QComboBox()
        for preset_key in sorted(self.presets.keys()):
            preset_data = self.presets[preset_key]
            display_name = f"{preset_data['name']} ({preset_key})"
            self.preset_combo.addItem(display_name, preset_key)
        target_layout.addWidget(self.preset_combo)
        
        # MNI coordinates
        coordinate_layout = QtWidgets.QHBoxLayout()
        self.coord_x = QtWidgets.QLineEdit()
        self.coord_x.setPlaceholderText("X")
        self.coord_y = QtWidgets.QLineEdit()
        self.coord_y.setPlaceholderText("Y")
        self.coord_z = QtWidgets.QLineEdit()
        self.coord_z.setPlaceholderText("Z")
        coordinate_layout.addWidget(QtWidgets.QLabel("X:"))
        coordinate_layout.addWidget(self.coord_x)
        coordinate_layout.addWidget(QtWidgets.QLabel("Y:"))
        coordinate_layout.addWidget(self.coord_y)
        coordinate_layout.addWidget(QtWidgets.QLabel("Z:"))
        coordinate_layout.addWidget(self.coord_z)
        self.coordinate_widget = QtWidgets.QWidget()
        self.coordinate_widget.setLayout(coordinate_layout)
        self.coordinate_widget.setVisible(False)
        target_layout.addWidget(self.coordinate_widget)
        
        # ROI radius
        radius_layout = QtWidgets.QHBoxLayout()
        radius_layout.addWidget(QtWidgets.QLabel("ROI Radius:"))
        self.roi_radius = QtWidgets.QSpinBox()
        self.roi_radius.setRange(5, 50)
        self.roi_radius.setValue(10)
        self.roi_radius.setSuffix(" mm")
        radius_layout.addWidget(self.roi_radius)
        radius_layout.addStretch()
        target_layout.addLayout(radius_layout)
        
        left_layout.addWidget(target_container)
        
        # Leadfield Management
        leadfield_container = QtWidgets.QGroupBox("Leadfield Management")
        leadfield_container.setFixedHeight(240)
        leadfield_layout = QtWidgets.QVBoxLayout(leadfield_container)
        leadfield_layout.setContentsMargins(10, 10, 10, 10)
        leadfield_layout.setSpacing(8)
        
        available_label = QtWidgets.QLabel("Available Leadfields:")
        available_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        leadfield_layout.addWidget(available_label)
        
        self.leadfield_list = QtWidgets.QListWidget()
        self.leadfield_list.setFixedHeight(140)
        self.leadfield_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.leadfield_list.itemSelectionChanged.connect(self.on_leadfield_selection_changed)
        leadfield_layout.addWidget(self.leadfield_list)
        
        self.selected_leadfield_label = QtWidgets.QLabel("Selected: None")
        self.selected_leadfield_label.setStyleSheet("color: #666; font-style: italic; margin: 5px 0;")
        leadfield_layout.addWidget(self.selected_leadfield_label)
        
        leadfield_buttons_layout = QtWidgets.QHBoxLayout()
        self.refresh_leadfields_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_leadfields_btn.setFixedHeight(25)
        self.refresh_leadfields_btn.clicked.connect(self.refresh_leadfields)
        leadfield_buttons_layout.addWidget(self.refresh_leadfields_btn)
        
        self.create_leadfield_btn = QtWidgets.QPushButton("Create New")
        self.create_leadfield_btn.setFixedHeight(25)
        self.create_leadfield_btn.clicked.connect(self.show_create_leadfield_dialog)
        leadfield_buttons_layout.addWidget(self.create_leadfield_btn)
        
        leadfield_layout.addLayout(leadfield_buttons_layout)
        left_layout.addWidget(leadfield_container)
        
        # Right side layout
        right_layout = QtWidgets.QVBoxLayout()
        
        # Optimization Parameters
        opt_container = QtWidgets.QGroupBox("Optimization Parameters")
        opt_container.setFixedHeight(340)
        opt_layout = QtWidgets.QFormLayout(opt_container)
        opt_layout.setContentsMargins(10, 10, 10, 10)
        opt_layout.setSpacing(8)
        
        # Single-objective section
        single_obj_label = QtWidgets.QLabel("Single-Objective (Intensity Only):")
        single_obj_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        opt_layout.addRow(single_obj_label)
        
        self.opt_method = QtWidgets.QComboBox()
        self.opt_method.addItem("Differential Evolution (recommended)", "differential_evolution")
        self.opt_method.addItem("Dual Annealing", "dual_annealing")
        self.opt_method.addItem("Basin Hopping", "basinhopping")
        self.opt_method.setToolTip(
            "Differential Evolution: Best for discrete electrode selection\n"
            "Dual Annealing: Alternative global optimizer\n"
            "Basin Hopping: Local search with random jumps"
        )
        opt_layout.addRow("  Method:", self.opt_method)
        
        self.generations = QtWidgets.QSpinBox()
        self.generations.setRange(10, 1000)
        self.generations.setValue(50)
        self.generations.setToolTip("Number of optimization iterations (more = better but slower)")
        opt_layout.addRow("  Generations:", self.generations)
        
        self.population = QtWidgets.QSpinBox()
        self.population.setRange(10, 200)
        self.population.setValue(30)
        self.population.setToolTip("Population size (more = better exploration but slower)")
        opt_layout.addRow("  Population:", self.population)
        
        self.current = QtWidgets.QDoubleSpinBox()
        self.current.setRange(0.5, 4.0)
        self.current.setValue(1.0)
        self.current.setSingleStep(0.1)
        self.current.setSuffix(" mA")
        self.current.setToolTip("Stimulation current magnitude")
        opt_layout.addRow("  Current:", self.current)
        
        # Pareto Front Generation (like original MOVEA)
        pareto_label = QtWidgets.QLabel("Multi-Objective (Intensity + Focality):")
        pareto_label.setStyleSheet("font-weight: bold; margin-top: 5px; color: #FF9800;")
        opt_layout.addRow(pareto_label)
        
        self.enable_pareto = QtWidgets.QCheckBox("Generate Pareto front")
        self.enable_pareto.setChecked(False)
        self.enable_pareto.toggled.connect(self.toggle_pareto_options)
        self.enable_pareto.setToolTip("Enable to explore intensity vs focality trade-offs")
        opt_layout.addRow("", self.enable_pareto)
        
        self.pareto_solutions = QtWidgets.QSpinBox()
        self.pareto_solutions.setRange(5, 500)
        self.pareto_solutions.setValue(20)
        self.pareto_solutions.setEnabled(False)
        self.pareto_solutions.setToolTip(
            "Number of Pareto-optimal solutions to generate\n"
            "20 = quick exploration, 100-200 = research quality"
        )
        opt_layout.addRow("  Solutions:", self.pareto_solutions)
        
        self.pareto_iterations = QtWidgets.QSpinBox()
        self.pareto_iterations.setRange(100, 2000)
        self.pareto_iterations.setValue(500)
        self.pareto_iterations.setEnabled(False)
        self.pareto_iterations.setToolTip(
            "Random search iterations per solution\n"
            "More iterations = better quality solutions but slower"
        )
        opt_layout.addRow("  Iterations/Sol:", self.pareto_iterations)
        
        # CPU cores for parallelization
        import multiprocessing as mp
        max_cores = mp.cpu_count()
        self.pareto_cores = QtWidgets.QSpinBox()
        self.pareto_cores.setRange(1, max_cores)
        self.pareto_cores.setValue(max(1, max_cores - 1))  # Default: leave 1 core free
        self.pareto_cores.setEnabled(False)
        self.pareto_cores.setToolTip(
            f"Number of CPU cores for parallel processing\n"
            f"Available: {max_cores} cores\n"
            f"Recommended: {max(1, max_cores - 1)} (leave 1 free)"
        )
        opt_layout.addRow("  CPU Cores:", self.pareto_cores)
        
        right_layout.addWidget(opt_container)
        right_layout.addStretch()  # Push optimization parameters to top
        
        # Add left and right to main horizontal layout
        main_horizontal_layout.addLayout(left_layout, 1)
        main_horizontal_layout.addLayout(right_layout, 1)
        
        scroll_layout.addLayout(main_horizontal_layout)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)
        
        # Create Run/Stop buttons using component
        self.action_buttons = RunStopButtons(self, run_text="Run MOVEA", stop_text="Stop")
        self.action_buttons.connect_run(self.run_optimization)
        self.action_buttons.connect_stop(self.stop_optimization)
        
        # Keep references for backward compatibility
        self.run_button = self.action_buttons.get_run_button()
        self.stop_button = self.action_buttons.get_stop_button()
        
        # Console widget component with Run/Stop buttons integrated
        self.console_widget = ConsoleWidget(
            parent=self,
            show_clear_button=True,
            show_debug_checkbox=True,
            console_label="Console Output:",
            min_height=180,
            max_height=None,
            custom_buttons=[self.run_button, self.stop_button]
        )
        main_layout.addWidget(self.console_widget)
        
        # Connect the debug checkbox to our custom toggle method (for logger adjustments)
        self.console_widget.debug_checkbox.toggled.connect(self.toggle_debug_mode)
        
        # Reference to underlying console for backward compatibility
        self.console = self.console_widget.get_console_widget()
    
    def toggle_target_type(self):
        """Toggle between preset and coordinate target input."""
        is_preset = self.preset_radio.isChecked()
        self.preset_combo.setVisible(is_preset)
        self.coordinate_widget.setVisible(not is_preset)
    
    def toggle_pareto_options(self):
        """Enable/disable Pareto solutions spinbox and cores based on checkbox."""
        enabled = self.enable_pareto.isChecked()
        self.pareto_solutions.setEnabled(enabled)
        self.pareto_iterations.setEnabled(enabled)
        self.pareto_cores.setEnabled(enabled)
    
    def toggle_debug_mode(self):
        """Toggle debug mode for verbose output."""
        # This is now handled by ConsoleWidget, but we still need to update logger levels
        self.debug_mode = self.console_widget.is_debug_mode()
        if self.debug_mode:
            if hasattr(self, 'logger') and self.logger is not None:
                import logging
                self.logger.setLevel(logging.DEBUG)
        else:
            if hasattr(self, 'logger') and self.logger is not None:
                import logging
                self.logger.setLevel(logging.INFO)
    
    def list_subjects(self):
        """List available subjects in the combo box."""
        self.subject_combo.clear()
        
        # Get subjects using path manager
        subjects = self.pm.list_subjects()
        self.subject_combo.addItems(subjects)
    
    def on_subject_changed(self):
        """Handle subject selection change."""
        subject_id = self.subject_combo.currentText()
        if subject_id:
            self.update_console(f"Selected subject: {subject_id}", 'info')
            self.refresh_leadfields()
    
    def refresh_leadfields(self):
        """Refresh the list of available leadfields."""
        self.leadfield_list.clear()
        
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            return
        
        subject_dir = self.pm.get_subject_dir(subject_id)
        
        # NEW: Search in MOVEA/leadfields directory
        movea_leadfield_dir = os.path.join(subject_dir, "MOVEA", "leadfields")
        
        # Check for existing leadfield NPY files
        leadfield_files = []
        if os.path.exists(movea_leadfield_dir):
            for file in os.listdir(movea_leadfield_dir):
                if file.endswith('_leadfield.npy'):
                    leadfield_path = os.path.join(movea_leadfield_dir, file)
                    # Look for corresponding positions file
                    pos_file = file.replace('_leadfield.npy', '_positions.npy')
                    pos_path = os.path.join(movea_leadfield_dir, pos_file)
                    
                    if os.path.exists(pos_path):
                        net_name = file.replace('_leadfield.npy', '')
                        leadfield_files.append({
                            'net_name': net_name,
                            'leadfield_path': leadfield_path,
                            'positions_path': pos_path,
                            'display': f"{net_name} (leadfield + positions)"
                        })
        
        # Add items to list
        for lf_info in leadfield_files:
            item = QtWidgets.QListWidgetItem(lf_info['display'])
            item.setData(QtCore.Qt.UserRole, lf_info)
            self.leadfield_list.addItem(item)
        
        if leadfield_files:
            self.update_console(f"Found {len(leadfield_files)} leadfield(s) for {subject_id}", 'success')
        else:
            self.update_console(f"No leadfields found for {subject_id}. Click 'Create New' to generate.", 'warning')
    
    def on_leadfield_selection_changed(self):
        """Handle leadfield selection change."""
        selected_items = self.leadfield_list.selectedItems()
        if selected_items:
            lf_info = selected_items[0].data(QtCore.Qt.UserRole)
            self.selected_leadfield_label.setText(f"Selected: {lf_info['net_name']}")
            self.update_console(f"Selected leadfield: {lf_info['net_name']}", 'info')
        else:
            self.selected_leadfield_label.setText("Selected: None")
    
    def show_create_leadfield_dialog(self):
        """Show dialog to create a new leadfield."""
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            QtWidgets.QMessageBox.warning(self, "No Subject", "Please select a subject first")
            return
        
        # Get available EEG nets
        eeg_positions_dir = self.pm.get_eeg_positions_dir(subject_id)
        
        eeg_nets = []
        if os.path.exists(eeg_positions_dir):
            for file in os.listdir(eeg_positions_dir):
                if file.endswith('.csv'):
                    eeg_nets.append(file)
        
        if not eeg_nets:
            QtWidgets.QMessageBox.warning(self, "No EEG Nets", f"No EEG net files found for subject {subject_id}")
            return
        
        # Show selection dialog
        net_name, ok = QtWidgets.QInputDialog.getItem(
            self, "Select EEG Net", 
            "Choose an EEG net for leadfield generation:",
            eeg_nets, 0, False
        )
        
        if ok and net_name:
            self.create_leadfield(subject_id, net_name)
    
    def create_leadfield(self, subject_id, eeg_net_file):
        """Create leadfield for selected EEG net."""
        if self.leadfield_generating:
            QtWidgets.QMessageBox.warning(self, "Already Running", "Leadfield generation is already running")
            return
        
        # Get project directory
        project_dir = self.pm.get_project_dir()
        if not project_dir or not os.path.exists(project_dir):
            QtWidgets.QMessageBox.warning(self, "No Project", "Project directory not found")
            return
        
        # Show info dialog
        reply = QtWidgets.QMessageBox.question(
            self,
            "Leadfield Generation",
            f"Generate leadfield for {eeg_net_file}?\n\n"
            f"This process may take 5-15 minutes depending on mesh size and electrode count.\n\n"
            f"Files will be saved to: derivatives/SimNIBS/sub-{subject_id}/MOVEA/leadfields/\n\n"
            "Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Clear console and start generation
        self.console.clear()
        self.update_console("="*60, 'default')
        self.update_console("LEADFIELD GENERATION", 'info')
        self.update_console("="*60, 'default')
        
        # Set UI state
        self.leadfield_generating = True
        self.create_leadfield_btn.setEnabled(False)
        self.refresh_leadfields_btn.setEnabled(False)
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.set_inputs_enabled(False)
        
        # Start generation thread
        self.leadfield_thread = LeadfieldGenerationThread(subject_id, eeg_net_file, project_dir, self)
        self.leadfield_thread.output_signal.connect(self.update_console)
        self.leadfield_thread.error_signal.connect(self.handle_error)
        self.leadfield_thread.finished_signal.connect(self.leadfield_generation_finished)
        self.leadfield_thread.start()
    
    def leadfield_generation_finished(self, success, lfm_path, pos_path):
        """Handle leadfield generation completion."""
        self.leadfield_generating = False
        self.create_leadfield_btn.setEnabled(True)
        self.refresh_leadfields_btn.setEnabled(True)
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.set_inputs_enabled(True)
        
        if success:
            self.update_console("", 'default')
            self.update_console("="*60, 'default')
            self.update_console("Leadfield generation completed successfully!", 'success')
            self.update_console("="*60, 'default')
            
            # Refresh the leadfield list to show the new leadfield
            self.refresh_leadfields()
            
            # Show success message
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                "Leadfield generation completed!\n\n"
                f"Files saved:\n"
                f"• {os.path.basename(lfm_path)}\n"
                f"• {os.path.basename(pos_path)}"
            )
        else:
            self.update_console("Leadfield generation failed or was cancelled", 'error')
    
    def validate_inputs(self):
        """Validate user inputs before running optimization."""
        subject_id = self.subject_combo.currentText()
        if not subject_id:
            QtWidgets.QMessageBox.warning(self, "No Subject", "Please select a subject")
            return False
        
        selected_items = self.leadfield_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "No Leadfield", "Please select a leadfield")
            return False
        
        if self.coordinate_radio.isChecked():
            try:
                float(self.coord_x.text())
                float(self.coord_y.text())
                float(self.coord_z.text())
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Invalid Coordinates", "Please enter valid MNI coordinates (X, Y, Z)")
                return False
        
        return True
    
    def run_optimization(self):
        """Run MOVEA optimization."""
        if not self.validate_inputs():
            return
        
        if self.optimization_running:
            QtWidgets.QMessageBox.warning(self, "Already Running", "Optimization is already running")
            return
        
        # Warn about very large Pareto computations
        if self.enable_pareto.isChecked():
            n_solutions = self.pareto_solutions.value()
            n_iters = self.pareto_iterations.value()
            total_evals = n_solutions * n_iters
            
            # Warn if total evaluations exceed 100,000
            if total_evals > 100000:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Large Computation Warning",
                    f"Pareto front generation will perform {total_evals:,} evaluations.\n\n"
                    f"This may take 20-60+ minutes depending on mesh size.\n\n"
                    f"Consider reducing:\n"
                    f"  • Solutions: {n_solutions} → 50-100\n"
                    f"  • Iterations/solution: {n_iters} → 200-300\n\n"
                    f"Continue with current settings?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No
                )
                if reply != QtWidgets.QMessageBox.Yes:
                    return
        
        # Get configuration
        subject_id = self.subject_combo.currentText()
        selected_items = self.leadfield_list.selectedItems()
        lf_info = selected_items[0].data(QtCore.Qt.UserRole)
        
        # Get target
        if self.preset_radio.isChecked():
            # Get preset key from combo box data
            preset_key = self.preset_combo.currentData()
            if preset_key and preset_key in self.presets:
                target = self.presets[preset_key]['mni']
                target_name = self.presets[preset_key]['name']
            else:
                # Fallback to old behavior
                target = self.preset_combo.currentText()
                target_name = target
        else:
            target = [
                float(self.coord_x.text()),
                float(self.coord_y.text()),
                float(self.coord_z.text())
            ]
            target_name = f"Custom {target}"
        
        # Set output directory with timestamp to avoid overwriting
        import time
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        subject_dir = self.pm.get_subject_dir(subject_id)
        output_dir = os.path.join(subject_dir, "MOVEA", timestamp) if subject_dir else None
        if not output_dir:
            QtWidgets.QMessageBox.warning(self, "Error", "Could not determine output directory")
            return
        
        # Find electrode coordinates CSV file using path_manager
        electrode_csv = None
        leadfield_path = lf_info['leadfield_path']
        
        # Extract electrode name from leadfield filename
        # EEG10-10_Cutini_2011_leadfield.npy -> EEG10-10_Cutini_2011
        leadfield_basename = os.path.basename(leadfield_path)
        eeg_name = leadfield_basename.replace('_leadfield.npy', '').replace('_leadfield', '')
        
        # Use path_manager to get eeg_positions directory
        eeg_positions_dir = self.pm.get_eeg_positions_dir(subject_id)
        
        if eeg_positions_dir and os.path.exists(eeg_positions_dir):
            # Look for matching CSV
            possible_csv = os.path.join(eeg_positions_dir, f'{eeg_name}.csv')
            if os.path.exists(possible_csv):
                electrode_csv = possible_csv
            else:
                # Fallback: try any CSV file in directory
                csv_files = [f for f in os.listdir(eeg_positions_dir) if f.endswith('.csv')]
                if csv_files:
                    electrode_csv = os.path.join(eeg_positions_dir, csv_files[0])
        
        config = {
            'subject_id': subject_id,
            'leadfield_path': lf_info['leadfield_path'],
            'positions_path': lf_info['positions_path'],
            'target': target,
            'roi_radius_mm': self.roi_radius.value(),
            'opt_method': self.opt_method.currentData(),
            'generations': self.generations.value(),
            'population': self.population.value(),
            'current_mA': self.current.value(),
            'output_dir': output_dir,
            'electrode_coords_file': electrode_csv,
            'generate_pareto': self.enable_pareto.isChecked(),
            'pareto_n_solutions': self.pareto_solutions.value(),
            'pareto_max_iter': self.pareto_iterations.value(),
            'pareto_n_cores': self.pareto_cores.value(),
            'target_name': target_name,
            'debug_mode': self.debug_mode
        }
        
        # Clear console
        self.console.clear()
        self.update_console("="*60, 'default')
        self.update_console("MOVEA TI ELECTRODE OPTIMIZATION", 'info')
        self.update_console("="*60, 'default')
        self.update_console(f"Subject: {subject_id}", 'info')
        self.update_console(f"Leadfield: {lf_info['net_name']}", 'info')
        if isinstance(target, list):
            self.update_console(f"Target: [{', '.join(map(str, target))}] ({target_name})", 'info')
        else:
            self.update_console(f"Target: {target}", 'info')
        self.update_console(f"ROI Radius: {self.roi_radius.value()} mm", 'info')
        if electrode_csv:
            self.update_console(f"Electrode names: {os.path.basename(electrode_csv)}", 'info')
        self.update_console("", 'default')
        self.update_console("Optimization Configuration:", 'info')
        self.update_console(f"  Method: {self.opt_method.currentText()}", 'default')
        self.update_console(f"  Generations: {self.generations.value()}", 'default')
        self.update_console(f"  Population: {self.population.value()}", 'default')
        self.update_console(f"  Current: {self.current.value()} mA", 'default')
        if self.enable_pareto.isChecked():
            self.update_console("", 'default')
            self.update_console("Pareto Front Generation:", 'info')
            self.update_console(f"  Solutions: {self.pareto_solutions.value()}", 'default')
            self.update_console(f"  Iterations/solution: {self.pareto_iterations.value()}", 'default')
            self.update_console(f"  CPU Cores: {self.pareto_cores.value()}", 'default')
            total_evals = self.pareto_solutions.value() * self.pareto_iterations.value()
            self.update_console(f"  Total evaluations: {total_evals:,}", 'default')
        self.update_console("", 'default')
        self.update_console(f"Output: {output_dir}", 'info')
        self.update_console("="*60, 'default')
        
        # Set UI state
        self.optimization_running = True
        self.status_label.show()
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.set_inputs_enabled(False)
        
        # Start optimization thread
        self.optimization_thread = MOVEAOptimizationThread(config, self)
        self.optimization_thread.output_signal.connect(self.update_console)
        self.optimization_thread.error_signal.connect(self.handle_error)
        self.optimization_thread.finished_signal.connect(self.optimization_finished)
        self.optimization_thread.start()
    
    def stop_optimization(self):
        """Stop running optimization or leadfield generation."""
        # Check what's running
        opt_running = self.optimization_thread and self.optimization_thread.isRunning()
        lf_running = self.leadfield_thread and self.leadfield_thread.isRunning()
        
        if not opt_running and not lf_running:
            return
        
        # Determine what to stop
        if opt_running and lf_running:
            process_name = "optimization and leadfield generation"
        elif opt_running:
            process_name = "optimization"
        else:
            process_name = "leadfield generation"
        
        # Simple confirmation
        warning_msg = f"Are you sure you want to stop the {process_name}?"
        
        reply = QtWidgets.QMessageBox.question(
            self, 'Stop Process',
            warning_msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # Stop optimization if running
            if opt_running:
                self.update_console("Stopping optimization...", 'warning')
                self.optimization_thread.terminate_process()
                self.optimization_thread.wait()
                self.optimization_finished(False)
            
            # Stop leadfield generation if running
            if lf_running:
                self.update_console("Stopping leadfield generation...", 'warning')
                self.leadfield_thread.terminate_process()
                self.leadfield_thread.wait()
                self.leadfield_generation_finished(False, "", "")
    
    def optimization_finished(self, success):
        """Handle optimization completion."""
        self.optimization_running = False
        self.status_label.hide()
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.set_inputs_enabled(True)
        
        if success:
            self.update_console("Optimization completed successfully!", 'success')
        else:
            self.update_console("Optimization stopped or failed", 'error')
    
    def set_inputs_enabled(self, enabled):
        """Enable or disable input widgets."""
        self.subject_combo.setEnabled(enabled)
        self.list_subjects_btn.setEnabled(enabled)
        self.leadfield_list.setEnabled(enabled)
        self.refresh_leadfields_btn.setEnabled(enabled)
        self.create_leadfield_btn.setEnabled(enabled)
        self.preset_radio.setEnabled(enabled)
        self.coordinate_radio.setEnabled(enabled)
        self.preset_combo.setEnabled(enabled)
        self.coord_x.setEnabled(enabled)
        self.coord_y.setEnabled(enabled)
        self.coord_z.setEnabled(enabled)
        self.roi_radius.setEnabled(enabled)
        self.opt_method.setEnabled(enabled)
        self.generations.setEnabled(enabled)
        self.population.setEnabled(enabled)
        self.current.setEnabled(enabled)
        self.enable_pareto.setEnabled(enabled)
        # Pareto options are controlled by toggle_pareto_options, not directly here
        if enabled and self.enable_pareto.isChecked():
            self.pareto_solutions.setEnabled(True)
            self.pareto_iterations.setEnabled(True)
            self.pareto_cores.setEnabled(True)
        
        # Keep debug checkbox enabled during processing
        if hasattr(self, 'console_widget') and hasattr(self.console_widget, 'debug_checkbox'):
            self.console_widget.debug_checkbox.setEnabled(True)
    
    def update_console(self, message, msg_type='default'):
        """Update console output with colored messages (respects debug mode)."""
        # ALWAYS log to file first, regardless of debug mode
        try:
            import logging
            # Try to get the active logger (either MOVEA or MOVEA_Leadfield)
            logger = logging.getLogger('MOVEA')
            if not logger.handlers:  # If MOVEA not initialized, try MOVEA_Leadfield
                logger = logging.getLogger('MOVEA_Leadfield')
            
            # Only log if the logger has handlers (meaning it was initialized by a thread)
            if logger.handlers:
                if msg_type == 'error':
                    logger.error(message)
                elif msg_type == 'warning':
                    logger.warning(message)
                elif msg_type == 'debug' or 'DEBUG' in message:
                    logger.debug(message)
                else:
                    logger.info(message)
        except Exception:
            pass  # Fail silently if logging fails
        
        # THEN filter for GUI display based on debug mode
        if not self.console_widget.is_debug_mode():
            # In normal mode, skip verbose messages in GUI (but they're already logged to file)
            if is_verbose_message(message, tab_type='movea') and msg_type not in ['error', 'warning', 'success']:
                return
        
        # Use the console widget's update_console method
        self.console_widget.update_console(message, msg_type)
    
    def handle_error(self, error_message):
        """Handle error messages."""
        self.update_console(f"ERROR: {error_message}", 'error')


# Standalone testing
if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    tab = MOVEATab()
    tab.show()
    sys.exit(app.exec_())
