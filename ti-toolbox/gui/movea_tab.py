#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox MOVEA Tab
GUI interface for MOVEA-based TI electrode optimization
"""

# Standard library imports
import json
import logging
import multiprocessing as mp
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

# Add project root to path for tools import
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Third-party imports
from PyQt5 import QtCore, QtGui, QtWidgets

# Local imports
from components.action_buttons import RunStopButtons
from components.console import ConsoleWidget
from core import get_path_manager
from tools import logging_util
from utils import is_important_message, is_verbose_message

# MOVEA imports - loaded at module level for thread safety
MOVEA_AVAILABLE = False
try:
    import numpy as np
    from opt.leadfield import LeadfieldGenerator
    from opt.movea import (
        MOVEAVisualizer,
        MontageFormatter,
        TIOptimizer,
    )
    MOVEA_AVAILABLE = True
except ImportError as e:
    # Will be handled in the thread if import fails
    MOVEA_IMPORT_ERROR = str(e)
    pass


class LeadfieldGenerationThread(QtCore.QThread):
    """Thread to run leadfield generation for MOVEA (generates both HDF5 and NPY files)."""
    
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
        self.generator = None
        
    def run(self):
        """Run leadfield generation using LeadfieldGenerator (generates both HDF5 and NPY files)."""
        try:
            self.output_signal.emit("Initializing leadfield generation...", 'info')
            
            pm = get_path_manager()
            m2m_dir = pm.get_m2m_dir(self.subject_id)
            
            if not m2m_dir or not os.path.exists(m2m_dir):
                self.error_signal.emit(f"m2m directory not found for subject {self.subject_id}")
                self.finished_signal.emit(False, "", "")
                return
            
            # Setup log file
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            derivatives_dir = os.path.join(self.project_dir, 'derivatives')
            log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{self.subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f'MOVEA_leadfield_{time_stamp}.log')
            
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
            lfm_filename = f"{net_name}_leadfield.npy"
            pos_filename = f"{net_name}_positions.npy"
            lfm_path = os.path.join(leadfield_dir, lfm_filename)
            pos_path = os.path.join(leadfield_dir, pos_filename)

            # Check if NPY files already exist - prevent duplicates
            if os.path.exists(lfm_path) and os.path.exists(pos_path):
                self.error_signal.emit(f"Leadfield NPY files already exist: {lfm_filename}")
                self.error_signal.emit("Delete existing NPY files first or choose a different EEG net")
                self.finished_signal.emit(False, "", "")
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
                    self.finished_signal.emit(False, "", "")
                    return
                
                # Check if NPY files were generated successfully
                if result['npy_leadfield'] and result['npy_positions']:
                    lfm_path = result['npy_leadfield']
                    pos_path = result['npy_positions']
                    
                    # Get shape info for logging
                    lfm_shape = self.generator.lfm.shape if self.generator.lfm is not None else None
                    
                    self.output_signal.emit("", 'default')
                    self.output_signal.emit("="*60, 'default')
                    self.output_signal.emit("LEADFIELD GENERATION COMPLETE!", 'success')
                    self.output_signal.emit("="*60, 'default')
                    self.output_signal.emit(f"Saved: {os.path.basename(lfm_path)}", 'success')
                    self.output_signal.emit(f"Saved: {os.path.basename(pos_path)}", 'success')
                    if lfm_shape:
                        self.output_signal.emit(f"Electrodes: {lfm_shape[0]}", 'info')
                        self.output_signal.emit(f"Voxels: {lfm_shape[1]}", 'info')
                    self.output_signal.emit("="*60, 'default')
                    
                    self.finished_signal.emit(True, lfm_path, pos_path)
                else:
                    self.error_signal.emit("Failed to generate NPY files")
                    self.finished_signal.emit(False, "", "")
                    
            except ImportError as e:
                self.error_signal.emit(f"Failed to import LeadfieldGenerator: {str(e)}")
                self.finished_signal.emit(False, "", "")
                
        except Exception as e:
            tb = traceback.format_exc()
            self.error_signal.emit(f"Error during leadfield generation: {str(e)}\n{tb}")
            self.finished_signal.emit(False, "", "")
    
    def terminate_process(self):
        """Terminate the leadfield generation (note: SimNIBS processes cannot be interrupted once started)."""
        self.terminated = True
        self.output_signal.emit("Termination requested. Note: SimNIBS processes cannot be interrupted mid-execution.", 'warning')
        return True


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
        
        # No need for multiprocessing setup anymore - we use threading
        
    def run(self):
        """Run MOVEA optimization."""
        try:
            self.output_signal.emit("Initializing MOVEA optimization...", 'info')
            
            # Check if MOVEA modules were imported successfully
            if not MOVEA_AVAILABLE:
                error_msg = f"Failed to import MOVEA modules: {MOVEA_IMPORT_ERROR if 'MOVEA_IMPORT_ERROR' in globals() else 'Unknown import error'}"
                self.error_signal.emit(error_msg)
                self.finished_signal.emit(False)
                return
            
            # Setup subject-specific log file
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
                    population_size=population
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
                visualizer = MOVEAVisualizer(output_dir, progress_callback=self.output_signal.emit)
                
                # 1. Generate Pareto front (like original MOVEA - OPTIONAL, can be slow)
                generate_pareto = self.config.get('generate_pareto', False)
                n_pareto_solutions = self.config.get('pareto_n_solutions', 20)
                pareto_max_iter = self.config.get('pareto_max_iter', 500)
                n_pareto_cores = self.config.get('pareto_n_cores', None)
                
                if generate_pareto:
                    try:
                        # Calculate generations for NSGA-II algorithm
                        approx_generations = max(10, pareto_max_iter // n_pareto_solutions)
                        total_evals = n_pareto_solutions * approx_generations
                        
                        # Estimate time (NSGA-II is more efficient than random search)
                        est_time = max(1, total_evals // 500)
                        self.output_signal.emit(f"  Generating Pareto front using NSGA-II algorithm", 'info')
                        self.output_signal.emit(f"  Population size: {n_pareto_solutions}, Generations: {approx_generations}", 'info')
                        if n_pareto_cores and n_pareto_cores > 1:
                            self.output_signal.emit(f"  Parallel threads: {n_pareto_cores}", 'info')
                        self.output_signal.emit(f"  Estimated evaluations: {total_evals:,} (est. {est_time} min)...", 'info')
                        
                        # Wrap in comprehensive error handling to prevent GUI crashes
                        try:
                            # Use new NSGA-II based multi-objective optimization
                            # Convert iterations to generations (roughly 1 generation = population_size evaluations)
                            approx_generations = max(10, pareto_max_iter // n_pareto_solutions)
                            
                            pareto_solutions = optimizer.generate_pareto_solutions(
                                n_solutions=n_pareto_solutions,
                                max_generations=approx_generations,
                                n_cores=n_pareto_cores
                            )
                        except Exception as pareto_gen_err:
                            # If Pareto generation fails completely, log but continue
                            self.output_signal.emit(f"  ⚠ Pareto generation failed: {str(pareto_gen_err)}", 'error')
                            self.output_signal.emit(f"  {traceback.format_exc()}", 'debug')
                            pareto_solutions = []
                        
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
                        self.output_signal.emit(f"  ⚠ Pareto front generation failed: {str(pareto_err)}", 'warning')
                        self.output_signal.emit(f"  {traceback.format_exc()}", 'debug')
                else:
                    self.output_signal.emit("  ⓘ Pareto front generation disabled (enable in GUI to generate)", 'info')

                # 2. Generate convergence plot for optimization results
                if hasattr(optimizer, 'optimization_results') and len(optimizer.optimization_results) > 0:
                    try:
                        conv_path = os.path.join(output_dir, 'convergence.png')
                        visualizer.plot_convergence(optimizer.optimization_results, save_path=conv_path)
                        self.output_signal.emit(f"  ✓ Convergence plot: {os.path.basename(conv_path)}", 'success')
                    except Exception as conv_err:
                        self.output_signal.emit(f"  ⚠ Convergence plot failed: {str(conv_err)}", 'warning')
                        self.output_signal.emit(f"  {traceback.format_exc()}", 'debug')
                
            except Exception as viz_error:
                self.output_signal.emit(f"Warning: Visualization failed: {str(viz_error)}", 'warning')
                # Continue even if visualization fails
            
            output_csv = os.path.join(output_dir, 'movea_montage.csv')

            formatter.save_montage_csv(montage, output_csv)
            
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
            
            # List visualization files
            viz_files = [
                'pareto_front.png',  # Like original MOVEA (optional)
                'pareto_solutions.csv',  # (optional)
                'convergence.png',  # Optimization progress (when multiple runs)
                'montage_summary.png',  # Single run montage visualization
            ]
            for viz_file in viz_files:
                viz_path = os.path.join(output_dir, viz_file)
                if os.path.exists(viz_path):
                    self.output_signal.emit(f"  • {viz_file}", 'default')
            
            self.output_signal.emit("="*60, 'default')
            
            self.finished_signal.emit(True)
            
        except Exception as e:
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
        """Load ROI presets from opt/roi_presets.json"""
        try:
            presets_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       'opt', 'roi_presets.json')
            if os.path.exists(presets_file):
                with open(presets_file, 'r') as f:
                    data = json.load(f)
                    self.presets = data.get('regions', {})

        except Exception as e:
            print(f"Error loading presets: {e}")
            self.presets = {}
    
    def initial_setup(self):
        """Initial setup after UI is created."""
        self.list_subjects()
    
    def setup_ui(self):
        """Set up the user interface."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Experimental warning label at top
        self.experimental_label = QtWidgets.QLabel()
        self.experimental_label.setText("⚠ EXPERIMENTAL INTEGRATION - Requires further validation")
        self.experimental_label.setStyleSheet("""
            QLabel {
                background-color: #fff3cd;
                color: #856404;
                border: 1px solid #ffeaa7;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                margin-bottom: 5px;
            }
        """)
        self.experimental_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(self.experimental_label)

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
        scroll_layout.setContentsMargins(5, 0, 5, 5)
        scroll_layout.setSpacing(5)

        # Main horizontal layout
        main_horizontal_layout = QtWidgets.QHBoxLayout()
        main_horizontal_layout.setSpacing(15)
        
        # Left side layout
        left_layout = QtWidgets.QVBoxLayout()
        
        # Subject selection
        subject_container = QtWidgets.QGroupBox("Subject Selection")
        subject_container.setStyleSheet("""
            QGroupBox {
                margin-top: 2px;
                padding-top: 2px;
            }
        """)
        subject_layout = QtWidgets.QVBoxLayout(subject_container)
        subject_layout.setContentsMargins(5, 0, 5, 0)
        subject_layout.setSpacing(2)
        
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.currentIndexChanged.connect(self.on_subject_changed)
        subject_layout.addWidget(self.subject_combo)

        subject_button_layout = QtWidgets.QHBoxLayout()
        self.list_subjects_btn = QtWidgets.QPushButton("Refresh List")
        self.list_subjects_btn.clicked.connect(self.list_subjects)
        subject_button_layout.addWidget(self.list_subjects_btn)
        
        subject_layout.addLayout(subject_button_layout)
        left_layout.addWidget(subject_container)
        
        # Target Configuration
        target_container = QtWidgets.QGroupBox("Target Configuration")
        target_layout = QtWidgets.QVBoxLayout(target_container)
        target_layout.setContentsMargins(5, 2, 5, 2)
        target_layout.setSpacing(2)

        # Create button group for mutually exclusive radio buttons
        self.target_button_group = QtWidgets.QButtonGroup()

        # Preset option
        preset_layout = QtWidgets.QHBoxLayout()
        self.preset_radio = QtWidgets.QRadioButton("Preset")
        self.preset_radio.setChecked(True)
        self.preset_radio.toggled.connect(self.toggle_target_type)
        self.target_button_group.addButton(self.preset_radio)
        preset_layout.addWidget(self.preset_radio)

        self.preset_combo = QtWidgets.QComboBox()
        for preset_key in sorted(self.presets.keys()):
            preset_data = self.presets[preset_key]
            display_name = f"{preset_data['name']} ({preset_key})"
            self.preset_combo.addItem(display_name, preset_key)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()
        self.preset_widget = QtWidgets.QWidget()
        self.preset_widget.setLayout(preset_layout)
        target_layout.addWidget(self.preset_widget)

        # Separator line
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        target_layout.addWidget(separator)

        # MNI coordinates option
        coordinate_layout = QtWidgets.QHBoxLayout()
        self.coordinate_radio = QtWidgets.QRadioButton("MNI Coordinates")
        self.coordinate_radio.toggled.connect(self.toggle_target_type)
        self.target_button_group.addButton(self.coordinate_radio)
        coordinate_layout.addWidget(self.coordinate_radio)

        self.coord_x = QtWidgets.QLineEdit()
        self.coord_x.setPlaceholderText("X")
        self.coord_x.setFixedWidth(60)
        self.coord_y = QtWidgets.QLineEdit()
        self.coord_y.setPlaceholderText("Y")
        self.coord_y.setFixedWidth(60)
        self.coord_z = QtWidgets.QLineEdit()
        self.coord_z.setPlaceholderText("Z")
        self.coord_z.setFixedWidth(60)

        coordinate_layout.addWidget(self.coord_x)
        coordinate_layout.addWidget(self.coord_y)
        coordinate_layout.addWidget(self.coord_z)

        self.roi_radius = QtWidgets.QSpinBox()
        self.roi_radius.setRange(5, 50)
        self.roi_radius.setValue(15)  # Standard for most brain regions
        self.roi_radius.setSuffix(" mm")
        self.roi_radius.setFixedWidth(80)
        self.roi_radius.setToolTip(
            "Target region radius for optimization\n"
            "10-15 mm: Focal stimulation (recommended)\n"
            "20-30 mm: Broader cortical areas\n"
            "Larger radius = less focal but more coverage"
        )
        coordinate_layout.addWidget(self.roi_radius)
        coordinate_layout.addStretch()

        self.coordinate_widget = QtWidgets.QWidget()
        self.coordinate_widget.setLayout(coordinate_layout)
        target_layout.addWidget(self.coordinate_widget)

        # Launch MNI button below coordinate selection
        button_layout = QtWidgets.QHBoxLayout()
        self.launch_mni_btn = QtWidgets.QPushButton("Launch MNI Nifti")
        self.launch_mni_btn.setToolTip("Open MNI152 T1 template in external viewer")
        self.launch_mni_btn.clicked.connect(self.launch_mni_nifti)
        button_layout.addWidget(self.launch_mni_btn)
        button_layout.addStretch()

        self.button_widget = QtWidgets.QWidget()
        self.button_widget.setLayout(button_layout)
        target_layout.addWidget(self.button_widget)

        # Initialize the toggle state (preset selected by default)
        self.toggle_target_type()

        left_layout.addWidget(target_container)
        
        # Leadfield Management
        leadfield_container = QtWidgets.QGroupBox("Leadfield Management")
        leadfield_container.setFixedHeight(192)
        leadfield_layout = QtWidgets.QVBoxLayout(leadfield_container)
        leadfield_layout.setContentsMargins(5, 2, 5, 2)
        leadfield_layout.setSpacing(2)
        
        available_label = QtWidgets.QLabel("Available Leadfields:")
        available_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        leadfield_layout.addWidget(available_label)
        
        self.leadfield_list = QtWidgets.QListWidget()
        self.leadfield_list.setFixedHeight(112)
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
        
        # Right side layout
        right_layout = QtWidgets.QVBoxLayout()
        
        # Optimization Parameters
        opt_container = QtWidgets.QGroupBox("Optimization Parameters")
        opt_layout = QtWidgets.QFormLayout(opt_container)
        opt_layout.setContentsMargins(5, 2, 5, 2)
        opt_layout.setSpacing(2)
        
        # Single-objective section
        single_obj_label = QtWidgets.QLabel("Single-Objective (Intensity Only):")
        single_obj_label.setStyleSheet("font-weight: bold;")
        opt_layout.addRow(single_obj_label)
        
        
        self.generations = QtWidgets.QSpinBox()
        self.generations.setRange(10, 1000)
        self.generations.setValue(100)  # Balanced speed vs quality
        self.generations.setToolTip(
            "Number of optimization iterations\n"
            "50-100: Quick optimization (5-10 min)\n"
            "200-500: Standard quality (15-30 min)\n"
            "500+: Publication quality (30+ min)"
        )
        opt_layout.addRow("  Generations:", self.generations)
        
        self.population = QtWidgets.QSpinBox()
        self.population.setRange(10, 200)
        self.population.setValue(50)  # Good exploration capability
        self.population.setToolTip(
            "Population size for evolutionary algorithm\n"
            "30-50: Standard (recommended)\n"
            "100+: Thorough exploration (slower)\n"
            "Larger populations find better solutions"
        )
        opt_layout.addRow("  Population:", self.population)

        # Add separator between single and multi-objective sections
        # Add spacing above separator
        spacer_above = QtWidgets.QWidget()
        spacer_above.setFixedHeight(5)
        opt_layout.addRow(spacer_above)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        opt_layout.addRow(separator)

        # Add spacing below separator
        spacer_below = QtWidgets.QWidget()
        spacer_below.setFixedHeight(5)
        opt_layout.addRow(spacer_below)

        # Pareto Front Generation (like original MOVEA)
        pareto_layout = QtWidgets.QHBoxLayout()
        self.pareto_label = QtWidgets.QLabel("Multi-Objective (Intensity + Focality):")
        self.pareto_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        pareto_layout.addWidget(self.pareto_label)

        self.enable_pareto = QtWidgets.QCheckBox("Generate Pareto front")
        self.enable_pareto.setChecked(False)  # Disabled by default for faster single-objective optimization
        self.enable_pareto.toggled.connect(self.toggle_pareto_options)
        self.enable_pareto.setToolTip("Enable to explore intensity vs focality trade-offs")
        pareto_layout.addWidget(self.enable_pareto)
        pareto_layout.addStretch()

        opt_layout.addRow(pareto_layout)

        self.pareto_solutions = QtWidgets.QSpinBox()
        self.pareto_solutions.setRange(5, 500)
        self.pareto_solutions.setValue(30)  # Good Pareto front coverage
        self.pareto_solutions.setEnabled(False)
        self.pareto_solutions.setToolTip(
            "Number of Pareto-optimal solutions to generate\n"
            "20-30: Quick exploration (recommended)\n"
            "50-100: Detailed analysis\n"
            "100+: Research/publication quality\n"
            "More solutions = better trade-off visualization"
        )
        opt_layout.addRow("  Solutions:", self.pareto_solutions)

        self.pareto_iterations = QtWidgets.QSpinBox()
        self.pareto_iterations.setRange(100, 2000)
        self.pareto_iterations.setValue(1000)  # Better quality solutions
        self.pareto_iterations.setEnabled(False)
        self.pareto_iterations.setToolTip(
            "Generations for multi-objective evolution\n"
            "500-1000: Quick results (recommended)\n"
            "1500+: High-quality Pareto front\n"
            "Higher values find better trade-offs"
        )
        opt_layout.addRow("  Iterations/Sol:", self.pareto_iterations)

        # CPU cores for parallelization
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

        # Leadfield Management (moved from left side)
        right_layout.addWidget(leadfield_container)
        
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
        
        # Set initial state for pareto options (checkbox is unchecked by default)
        self.toggle_pareto_options()
    
    def toggle_target_type(self):
        """Toggle between preset and coordinate target input."""
        is_preset = self.preset_radio.isChecked()

        # Enable/disable preset widgets (but not the radio button)
        self.preset_combo.setEnabled(is_preset)
        # Grey out only the combo box, not the radio button
        self.preset_combo.setStyleSheet("color: black;" if is_preset else "color: grey;")

        # Enable/disable coordinate widgets (but not the radio button)
        self.coord_x.setEnabled(not is_preset)
        self.coord_y.setEnabled(not is_preset)
        self.coord_z.setEnabled(not is_preset)
        self.roi_radius.setEnabled(not is_preset)
        self.button_widget.setEnabled(not is_preset)
        # Grey out only the input widgets, not the radio button
        coord_color = "color: black;" if not is_preset else "color: grey;"
        self.coord_x.setStyleSheet(coord_color)
        self.coord_y.setStyleSheet(coord_color)
        self.coord_z.setStyleSheet(coord_color)
        self.roi_radius.setStyleSheet(coord_color)

    def toggle_pareto_options(self):
        """Enable/disable Pareto solutions spinbox and cores based on checkbox."""
        enabled = self.enable_pareto.isChecked()
        
        # Enable/disable spinboxes
        self.pareto_solutions.setEnabled(enabled)
        self.pareto_iterations.setEnabled(enabled)
        self.pareto_cores.setEnabled(enabled)
        
        # Apply visual styling (grey out when disabled)
        if enabled:
            self.pareto_label.setStyleSheet("font-weight: bold; margin-top: 5px; color: black;")
            self.pareto_solutions.setStyleSheet("color: black;")
            self.pareto_iterations.setStyleSheet("color: black;")
            self.pareto_cores.setStyleSheet("color: black;")
        else:
            self.pareto_label.setStyleSheet("font-weight: bold; margin-top: 5px; color: grey;")
            self.pareto_solutions.setStyleSheet("color: grey;")
            self.pareto_iterations.setStyleSheet("color: grey;")
            self.pareto_cores.setStyleSheet("color: grey;")

    def toggle_debug_mode(self):
        """Toggle debug mode for verbose output."""
        # This is now handled by ConsoleWidget, but we still need to update logger levels
        self.debug_mode = self.console_widget.is_debug_mode()
        if self.debug_mode:
            if hasattr(self, 'logger') and self.logger is not None:
                self.logger.setLevel(logging.DEBUG)
        else:
            if hasattr(self, 'logger') and self.logger is not None:
                self.logger.setLevel(logging.INFO)
    
    def list_subjects(self):
        """List available subjects in the combo box."""
        self.subject_combo.clear()
        
        # Get subjects using path manager
        subjects = self.pm.list_subjects()
        self.subject_combo.addItems(subjects)

    def launch_mni_nifti(self):
        """Launch MNI152 T1 template in Freeview."""
        # Path to MNI template
        mni_path = '/ti-toolbox/resources/atlas/MNI152_T1_1mm.nii.gz'

        if not os.path.exists(mni_path):
            QtWidgets.QMessageBox.warning(self, "File Not Found",
                                        f"MNI template not found at: {mni_path}")
            return

        try:
            self.update_console("Launching MNI template with Freeview...", 'info')
            subprocess.run(['freeview', mni_path], check=True)
            self.update_console("MNI template launched successfully", 'info')
        except FileNotFoundError:
            QtWidgets.QMessageBox.warning(self, "Freeview Not Found",
                                        "Freeview (FreeSurfer) is not installed or not in PATH.\n\n"
                                        "Please install FreeSurfer to use this feature:\n"
                                        "https://surfer.nmr.mgh.harvard.edu/")
        except subprocess.CalledProcessError as e:
            QtWidgets.QMessageBox.warning(self, "Launch Failed",
                                        f"Failed to launch Freeview:\n{e}")

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

        # Use LeadfieldGenerator to list available NPY leadfields
        from opt.leadfield import LeadfieldGenerator
        m2m_dir = self.pm.get_m2m_dir(subject_id)
        if not m2m_dir or not os.path.exists(m2m_dir):
            self.update_console(f"No M2M directory found for {subject_id}", 'warning')
            return

        gen = LeadfieldGenerator(m2m_dir)
        leadfields = gen.list_available_leadfields_npy(subject_id)

        # Populate the list
        for net_name, npy_leadfield_path, npy_positions_path, file_size in leadfields:
            item_text = f"{net_name} ({file_size:.1f} GB)"
            item = QtWidgets.QListWidgetItem(item_text)
            lf_info = {
                'net_name': net_name,
                'leadfield_path': npy_leadfield_path,
                'positions_path': npy_positions_path,
                'display': item_text
            }
            item.setData(QtCore.Qt.UserRole, lf_info)
            self.leadfield_list.addItem(item)

        if leadfields:
            self.update_console(f"Found {len(leadfields)} leadfield(s) for {subject_id}", 'success')
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
            'opt_method': 'differential_evolution',
            'generations': self.generations.value(),
            'population': self.population.value(),
            'current_mA': 1.0,
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
        self.update_console("  Method: Differential Evolution", 'default')
        self.update_console(f"  Generations: {self.generations.value()}", 'default')
        self.update_console(f"  Population: {self.population.value()}", 'default')
        self.update_console("  Current: 1.0 mA", 'default')
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
        self.button_widget.setEnabled(enabled)
        self.generations.setEnabled(enabled)
        self.population.setEnabled(enabled)
        self.enable_pareto.setEnabled(enabled)
        
        # Respect checkbox state when re-enabling inputs
        if enabled:
            # Re-apply the pareto options toggle to ensure correct state and styling
            self.toggle_pareto_options()
        else:
            # When disabling, just disable everything
            self.pareto_solutions.setEnabled(False)
            self.pareto_iterations.setEnabled(False)
            self.pareto_cores.setEnabled(False)

        # Keep debug checkbox enabled during processing
        if hasattr(self, 'console_widget') and hasattr(self.console_widget, 'debug_checkbox'):
            self.console_widget.debug_checkbox.setEnabled(True)
    
    def update_console(self, message, msg_type='default'):
        """Update console output with colored messages (respects debug mode)."""
        # ALWAYS log to file first, regardless of debug mode
        try:
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
    app = QtWidgets.QApplication(sys.argv)
    tab = MOVEATab()
    tab.show()
    sys.exit(app.exec_())
