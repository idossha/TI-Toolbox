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

try:
    from PyQt5 import QtWidgets, QtCore, QtGui
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    print("Warning: PyQt5 not available")
    # Create dummy classes to prevent import errors
    class QtWidgets:
        class QWidget:
            pass
    class QtCore:
        pass
    class QtGui:
        pass

try:
    from .utils import is_verbose_message, is_important_message
except ImportError:
    import os
    import sys
    gui_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, gui_dir)
    from utils import is_verbose_message, is_important_message

# Add parent directory to path for utils
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import logging utility using absolute path to avoid conflict with GUI/utils.py
try:
    utils_dir = os.path.join(parent_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    import logging_util
    LOGGER_AVAILABLE = True
except ImportError as e:
    LOGGER_AVAILABLE = False
    print(f"Warning: logging_util not available: {e}")
    print(f"  Utils dir: {utils_dir}")
    print(f"  File exists: {os.path.exists(os.path.join(utils_dir, 'logging_util.py'))}")

# Add MOVEA directory to path
movea_dir = os.path.join(parent_dir, 'MOVEA')
if movea_dir not in sys.path:
    sys.path.insert(0, movea_dir)


class LeadfieldGenerationThread(QtCore.QThread):
    """Thread to run leadfield generation in background."""
    
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
        
    def run(self):
        """Run leadfield generation."""
        try:
            self.output_signal.emit("Initializing leadfield generation...", 'info')
            
            # Import MOVEA modules
            try:
                from MOVEA import LeadfieldGenerator
                # logging_util already imported at module level
            except ImportError as e:
                self.error_signal.emit(f"Failed to import MOVEA modules: {str(e)}")
                self.finished_signal.emit(False, "", "")
                return
            
            # Setup subject-specific log file
            if LOGGER_AVAILABLE:
                import time
                time_stamp = time.strftime('%Y%m%d_%H%M%S')
                derivatives_dir = os.path.join(self.project_dir, 'derivatives')
                log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{self.subject_id}')
                os.makedirs(log_dir, exist_ok=True)
                log_file = os.path.join(log_dir, f'MOVEA_leadfield_{time_stamp}.log')
                
                # Set environment variable for external scripts
                os.environ['TI_LOG_FILE'] = log_file
                
                # Create logger
                logger = logging_util.get_logger('MOVEA_Leadfield', log_file, overwrite=False)
                
                # Remove console handler to prevent terminal output (GUI only shows via signals)
                import logging
                for handler in logger.handlers[:]:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                        logger.removeHandler(handler)
                
                # Configure external loggers (they will inherit only file handler, no console)
                logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct'], logger)
                
                self.output_signal.emit(f"Log file: {log_file}", 'info')
            
            # Setup paths
            m2m_dir = os.path.join(self.project_dir, "derivatives", "SimNIBS", 
                                   f"sub-{self.subject_id}", f"m2m_{self.subject_id}")
            
            if not os.path.exists(m2m_dir):
                self.error_signal.emit(f"m2m directory not found: {m2m_dir}")
                self.finished_signal.emit(False, "", "")
                return
            
            # Check if target leadfield already exists
            subject_derivatives = os.path.join(self.project_dir, "derivatives", "SimNIBS", f"sub-{self.subject_id}")
            movea_leadfield_dir = os.path.join(subject_derivatives, 'MOVEA', 'leadfields')
            net_name = self.eeg_net_file.replace('.csv', '')
            lfm_filename = f"{net_name}_leadfield.npy"
            pos_filename = f"{net_name}_positions.npy"
            lfm_path = os.path.join(movea_leadfield_dir, lfm_filename)
            pos_path = os.path.join(movea_leadfield_dir, pos_filename)
            
            if os.path.exists(lfm_path) and os.path.exists(pos_path):
                self.error_signal.emit(f"Leadfield already exists: {lfm_filename}")
                self.error_signal.emit(f"Delete existing files first or choose a different EEG net")
                self.finished_signal.emit(False, "", "")
                return
            
            self.output_signal.emit(f"Subject: {self.subject_id}", 'info')
            self.output_signal.emit(f"EEG Net: {self.eeg_net_file}", 'info')
            self.output_signal.emit(f"m2m directory: {m2m_dir}", 'info')
            
            # Clean up any existing SimNIBS simulation files in m2m directory
            self.output_signal.emit("Checking for old simulation files...", 'info')
            import glob
            import shutil
            old_sim_files = glob.glob(os.path.join(m2m_dir, "simnibs_simulation*.mat"))
            if old_sim_files:
                self.output_signal.emit(f"  Found {len(old_sim_files)} old simulation file(s), cleaning up...", 'info')
                for sim_file in old_sim_files:
                    try:
                        os.remove(sim_file)
                        self.output_signal.emit(f"  Removed: {os.path.basename(sim_file)}", 'info')
                    except Exception as e:
                        self.output_signal.emit(f"  Warning: Could not remove {os.path.basename(sim_file)}: {e}", 'warning')
            
            # Also clean up temporary leadfield directory if it exists in m2m
            temp_leadfield_dir = os.path.join(m2m_dir, 'leadfield')
            if os.path.exists(temp_leadfield_dir):
                self.output_signal.emit("  Removing old temporary leadfield directory...", 'info')
                try:
                    shutil.rmtree(temp_leadfield_dir)
                    self.output_signal.emit("  Removed: leadfield/", 'info')
                except Exception as e:
                    self.output_signal.emit(f"  Warning: Could not remove leadfield directory: {e}", 'warning')
            
            if self.terminated:
                return
            
            # Create leadfield generator with progress callback
            def progress_callback(message, msg_type='info'):
                self.output_signal.emit(message, msg_type)
            
            gen = LeadfieldGenerator(m2m_dir, progress_callback=progress_callback)
            
            # Generate leadfield using SimNIBS
            self.output_signal.emit("", 'default')
            self.output_signal.emit("Generating leadfield with SimNIBS...", 'info')
            self.output_signal.emit("This may take 5-15 minutes depending on mesh size and electrode count", 'info')
            
            try:
                # Ensure MOVEA/leadfields directory exists
                os.makedirs(movea_leadfield_dir, exist_ok=True)
                
                self.output_signal.emit(f"Output directory: {movea_leadfield_dir}", 'info')
                
                # Get EEG cap path
                eeg_cap_path = os.path.join(m2m_dir, 'eeg_positions', self.eeg_net_file)
                if not os.path.exists(eeg_cap_path):
                    self.error_signal.emit(f"EEG cap file not found: {eeg_cap_path}")
                    self.finished_signal.emit(False, "", "")
                    return
                
                # Generate to m2m first (SimNIBS requirement)
                self.output_signal.emit(f"Using EEG cap: {self.eeg_net_file}", 'info')
                hdf5_file = gen.generate_leadfield(output_dir=m2m_dir, tissues=[1, 2], eeg_cap_path=eeg_cap_path)
                
                if self.terminated:
                    return
                
                self.output_signal.emit(f"Leadfield generated: {os.path.basename(hdf5_file)}", 'success')
                
                # Load from HDF5
                self.output_signal.emit("Loading and converting leadfield...", 'info')
                lfm, positions = gen.load_from_hdf5(hdf5_file, compute_centroids=True)
                
                if self.terminated:
                    return
                
                # Save as numpy files to MOVEA/leadfields
                self.output_signal.emit("Saving numpy files...", 'info')
                import numpy as np
                np.save(lfm_path, lfm)
                np.save(pos_path, positions)
                
                # Clean up intermediate files
                self.output_signal.emit("Cleaning up intermediate files...", 'info')
                try:
                    # Remove HDF5 file from m2m directory
                    if os.path.exists(hdf5_file):
                        os.remove(hdf5_file)
                        self.output_signal.emit(f"  Removed: {os.path.basename(hdf5_file)}", 'info')
                    
                    # Clean up any other leadfield files in m2m directory
                    hdf5_dir = os.path.dirname(hdf5_file)
                    if os.path.exists(hdf5_dir) and os.path.basename(hdf5_dir) == 'leadfield':
                        # Remove the entire leadfield directory from m2m
                        import shutil
                        shutil.rmtree(hdf5_dir)
                        self.output_signal.emit(f"  Removed temporary directory: leadfield/", 'info')
                except Exception as cleanup_err:
                    self.output_signal.emit(f"  Warning: Cleanup failed: {str(cleanup_err)}", 'warning')
                
                self.output_signal.emit("", 'default')
                self.output_signal.emit("Leadfield generation complete!", 'success')
                self.output_signal.emit(f"Saved: {lfm_filename}", 'success')
                self.output_signal.emit(f"Saved: {pos_filename}", 'success')
                self.output_signal.emit(f"Electrodes: {lfm.shape[0]}", 'info')
                self.output_signal.emit(f"Voxels: {lfm.shape[1]}", 'info')
                
                self.finished_signal.emit(True, lfm_path, pos_path)
                
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                self.error_signal.emit(f"Leadfield generation failed: {str(e)}\n{tb}")
                self.finished_signal.emit(False, "", "")
                
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.error_signal.emit(f"Error during leadfield generation: {str(e)}\n{tb}")
            self.finished_signal.emit(False, "", "")
    
    def terminate_process(self):
        """Terminate the generation."""
        self.terminated = True


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
                from MOVEA import TIOptimizer, LeadfieldGenerator, MontageFormatter, MOVEAVisualizer
                import numpy as np
                # logging_util already imported at module level
            except ImportError as e:
                self.error_signal.emit(f"Failed to import MOVEA modules: {str(e)}")
                self.finished_signal.emit(False)
                return
            
            # Setup subject-specific log file
            if LOGGER_AVAILABLE:
                import time
                time_stamp = time.strftime('%Y%m%d_%H%M%S')
                subject_id = self.config['subject_id']
                project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
                derivatives_dir = os.path.join(project_dir, 'derivatives')
                log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
                os.makedirs(log_dir, exist_ok=True)
                log_file = os.path.join(log_dir, f'MOVEA_{time_stamp}.log')
                
                # Set environment variable for external scripts
                os.environ['TI_LOG_FILE'] = log_file
                
                # Create logger
                logger = logging_util.get_logger('MOVEA', log_file, overwrite=False)
                
                # Remove console handler to prevent terminal output (GUI only shows via signals)
                import logging
                for handler in logger.handlers[:]:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                        logger.removeHandler(handler)
                
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
                
                # 3. Try to create NIfTI field visualization if reference available
                try:
                    # Look for m2m.nii.gz in subject directory
                    subject_dir = os.path.dirname(os.path.dirname(output_dir))
                    possible_refs = [
                        os.path.join(subject_dir, 'm2m.nii.gz'),
                        os.path.join(subject_dir, 'm2m', 'm2m.nii.gz'),
                        os.path.join(os.path.dirname(subject_dir), 'm2m', self.config['subject_id'] + '.nii.gz'),
                    ]
                    
                    reference_nifti = None
                    for ref in possible_refs:
                        if os.path.exists(ref):
                            reference_nifti = ref
                            break
                    
                    if reference_nifti:
                        # Calculate full brain field
                        from MOVEA.utils import calculate_ti_field
                        e1, e2, e3, e4 = result['electrodes']
                        stim1 = np.zeros(num_electrodes)
                        stim1[e1] = 1
                        stim1[e2] = -1
                        stim2 = np.zeros(num_electrodes)
                        stim2[e3] = 1
                        stim2[e4] = -1
                        
                        field_values = calculate_ti_field(lfm, stim1, stim2, target_indices=None)
                        
                        # Create NIfTI
                        nifti_path = os.path.join(output_dir, 'ti_field.nii.gz')
                        visualizer.create_field_nifti(
                            field_values, positions, reference_nifti, 
                            nifti_path, interpolate=True
                        )
                        self.output_signal.emit(f"  ✓ Field NIfTI: {os.path.basename(nifti_path)}", 'success')
                        
                        # Create brain visualization
                        brain_viz_path = os.path.join(output_dir, 'brain_field.png')
                        visualizer.visualize_field_on_brain(
                            nifti_path, reference_nifti, target, brain_viz_path
                        )
                        self.output_signal.emit(f"  ✓ Brain visualization: {os.path.basename(brain_viz_path)}", 'success')
                    else:
                        self.output_signal.emit("  ⓘ Reference NIfTI not found, skipping field visualization", 'info')
                
                except Exception as viz_err:
                    self.output_signal.emit(f"  ⓘ Could not create field visualization: {str(viz_err)}", 'info')
                
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
                'ti_field.nii.gz', 
                'brain_field.png'
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
        
        # Logger will be created per-operation with subject-specific paths
        self.logger = None
            
        # Load ROI presets
        self.load_presets()
        
        if PYQT5_AVAILABLE:
            self.setup_ui()
            # Initialize with available subjects
            QtCore.QTimer.singleShot(500, self.initial_setup)
        else:
            layout = QtWidgets.QVBoxLayout()
            self.setLayout(layout)
    
    def load_presets(self):
        """Load ROI presets from MOVEA/presets.json"""
        try:
            presets_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                       'MOVEA', 'presets.json')
            if os.path.exists(presets_file):
                with open(presets_file, 'r') as f:
                    data = json.load(f)
                    self.presets = data.get('regions', {})
                    print(f"✓ Loaded {len(self.presets)} ROI presets from presets.json")
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
        
        right_layout.addWidget(target_container)
        
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
        
        # Add left and right to main horizontal layout
        main_horizontal_layout.addLayout(left_layout, 1)
        main_horizontal_layout.addLayout(right_layout, 1)
        
        scroll_layout.addLayout(main_horizontal_layout)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)
        
        # Console header with all controls in single horizontal line
        console_header_layout = QtWidgets.QHBoxLayout()
        
        # Console Output label
        console_label = QtWidgets.QLabel("Console Output:")
        console_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        console_header_layout.addWidget(console_label)
        
        # Add spacing
        console_header_layout.addSpacing(20)
        
        # Run button
        self.run_button = QtWidgets.QPushButton("Run MOVEA")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.run_button.clicked.connect(self.run_optimization)
        console_header_layout.addWidget(self.run_button)
        
        # Stop button
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_optimization)
        console_header_layout.addWidget(self.stop_button)
        
        # Clear console button
        self.clear_console_btn = QtWidgets.QPushButton("Clear")
        self.clear_console_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        self.clear_console_btn.clicked.connect(lambda: self.console.clear())
        console_header_layout.addWidget(self.clear_console_btn)
        
        # Debug mode checkbox
        self.debug_checkbox = QtWidgets.QCheckBox("Debug Mode")
        self.debug_checkbox.setChecked(False)
        self.debug_checkbox.setToolTip(
            "Toggle debug mode:\n"
            "• ON: Show all detailed logging information\n"
            "• OFF: Show only key operational steps"
        )
        self.debug_checkbox.toggled.connect(self.toggle_debug_mode)
        self.debug_checkbox.setStyleSheet("""
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
        console_header_layout.addWidget(self.debug_checkbox)
        
        # Add stretch to push everything to the left
        console_header_layout.addStretch()
        
        main_layout.addLayout(console_header_layout)
        
        # Console output with dark theme (matching ex_search_tab)
        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(200)
        self.console.setMaximumHeight(300)
        self.console.setStyleSheet("""
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
        main_layout.addWidget(self.console)
    
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
        self.debug_mode = self.debug_checkbox.isChecked()
        if self.debug_mode:
            self.update_console("Debug mode enabled - showing all messages", 'info')
            if hasattr(self, 'logger') and self.logger is not None:
                import logging
                self.logger.setLevel(logging.DEBUG)
        else:
            self.update_console("Debug mode disabled - showing important messages only", 'info')
            if hasattr(self, 'logger') and self.logger is not None:
                import logging
                self.logger.setLevel(logging.INFO)
    
    def list_subjects(self):
        """List available subjects in the combo box."""
        self.subject_combo.clear()
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        
        if not project_dir or not os.path.exists(project_dir):
            self.update_console("No project directory found", 'error')
            return
        
        subjects_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
        if not os.path.exists(subjects_dir):
            self.update_console("No subjects directory found", 'error')
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
            self.update_console("No subjects found", 'error')
            return
        
        # Sort subjects naturally
        subjects.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', x)])
        self.subject_combo.addItems(subjects)
        
        self.update_console(f"Found {len(subjects)} subject(s)", 'success')
    
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
        
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        subject_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}")
        
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
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        m2m_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", f"m2m_{subject_id}")
        eeg_positions_dir = os.path.join(m2m_dir, "eeg_positions")
        
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
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
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
        project_dir = os.path.join("/mnt", os.environ.get("PROJECT_DIR_NAME", ""))
        output_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "MOVEA", timestamp)
        
        # Find electrode coordinates CSV file
        # NEW Path structure:
        # Leadfield: /mnt/projectID/derivatives/SimNIBS/sub-101/MOVEA/leadfields/EEG10-10_Cutini_2011_leadfield.npy
        # Electrode: /mnt/projectID/derivatives/SimNIBS/sub-101/m2m_101/eeg_positions/EEG10-10_Cutini_2011.csv
        
        electrode_csv = None
        leadfield_path = lf_info['leadfield_path']
        
        # Extract electrode name from leadfield filename
        # EEG10-10_Cutini_2011_leadfield.npy -> EEG10-10_Cutini_2011
        leadfield_basename = os.path.basename(leadfield_path)
        eeg_name = leadfield_basename.replace('_leadfield.npy', '').replace('_leadfield', '')
        
        # Navigate from leadfield to m2m directory
        # /mnt/.../sub-101/MOVEA/leadfields/xxx.npy -> /mnt/.../sub-101/m2m_101/eeg_positions/
        leadfield_dir = os.path.dirname(leadfield_path)  # .../MOVEA/leadfields
        movea_dir = os.path.dirname(leadfield_dir)  # .../MOVEA
        subject_dir = os.path.dirname(movea_dir)  # .../sub-101
        
        # Look for m2m_* directory
        m2m_dir = None
        try:
            for item in os.listdir(subject_dir):
                if item.startswith('m2m_'):
                    candidate = os.path.join(subject_dir, item)
                    if os.path.isdir(candidate):
                        m2m_dir = candidate
                        break
        except:
            pass
        
        if m2m_dir:
            eeg_positions_dir = os.path.join(m2m_dir, 'eeg_positions')
            
            if os.path.exists(eeg_positions_dir):
                # Look for matching CSV
                possible_csv = os.path.join(eeg_positions_dir, f'{eeg_name}.csv')
                if os.path.exists(possible_csv):
                    electrode_csv = possible_csv
                else:
                    # Fallback: try any CSV file in directory
                    try:
                        csv_files = [f for f in os.listdir(eeg_positions_dir) if f.endswith('.csv')]
                        if csv_files:
                            electrode_csv = os.path.join(eeg_positions_dir, csv_files[0])
                    except:
                        pass
        
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
        
        reply = QtWidgets.QMessageBox.question(
            self, 'Stop Process',
            f"Are you sure you want to stop the {process_name}?",
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
    
    def update_console(self, message, msg_type='default'):
        """Update console output with colored messages (respects debug mode)."""
        # ALWAYS log to file first, regardless of debug mode
        if LOGGER_AVAILABLE:
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
        if not self.debug_mode:
            # In normal mode, skip verbose messages in GUI (but they're already logged to file)
            if is_verbose_message(message, tab_type='movea') and msg_type not in ['error', 'warning', 'success']:
                return
        
        # Dark theme colors matching ex_search_tab
        colors = {
            'default': '#f0f0f0',
            'info': '#66b3ff',
            'success': '#00ff00',
            'warning': '#ffaa00',
            'error': '#ff5555',
            'debug': '#888888'
        }
        
        color = colors.get(msg_type, colors['default'])
        
        # Append with color
        self.console.append(f'<span style="color: {color};">{message}</span>')
        
        # Scroll to bottom
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum()
        )
    
    def handle_error(self, error_message):
        """Handle error messages."""
        self.update_console(f"ERROR: {error_message}", 'error')


# Standalone testing
if __name__ == '__main__':
    if PYQT5_AVAILABLE:
        import sys
        app = QtWidgets.QApplication(sys.argv)
        tab = MOVEATab()
        tab.show()
        sys.exit(app.exec_())
    else:
        print("PyQt5 not available. Cannot run GUI.")
