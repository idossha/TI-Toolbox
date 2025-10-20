#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import traceback
import numpy as np
from pathlib import Path

# Add the parent directory to the path to access utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import external dependencies with error handling
try:
    from simnibs import opt_struct, mni2subject_coords
    from simnibs.mesh_tools.mesh_io import ElementTags
except ImportError:
    opt_struct = None
    mni2subject_coords = None
    ElementTags = None
    print("Warning: simnibs not available. Flex-search functionality will be limited.")
from tools.logging_util import get_logger, configure_external_loggers

# -----------------------------------------------------------------------------
# Summary logging system for non-debug mode
# -----------------------------------------------------------------------------

# Global variables for summary logging
SUMMARY_MODE = False
OPTIMIZATION_START_TIME = None
STEP_START_TIMES = {}

def set_summary_mode(enabled=True):
    """Enable or disable summary mode for console output."""
    global SUMMARY_MODE
    SUMMARY_MODE = enabled

def format_duration(seconds):
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.0f}m {seconds % 60:.0f}s"
    else:
        hours = seconds / 3600
        minutes = (seconds % 3600) / 60
        return f"{hours:.0f}h {minutes:.0f}m"

def log_optimization_start(subject_id, goal, postproc, roi_method, n_multistart):
    """Log the start of optimization for a subject."""
    global OPTIMIZATION_START_TIME
    OPTIMIZATION_START_TIME = time.time()
    
    if SUMMARY_MODE:
        print(f"Beginning flex-search optimization for subject: {subject_id} ({goal}, {postproc}, {roi_method})")
        if n_multistart > 1:
            print(f"├─ Multi-start optimization: {n_multistart} runs")
        else:
            print("├─ Single optimization run")
    else:
        logger.info(f"Beginning flex-search optimization for subject: {subject_id}")

def log_optimization_step_start(step_name):
    """Log the start of an optimization step."""
    global STEP_START_TIMES
    STEP_START_TIMES[step_name] = time.time()
    
    if SUMMARY_MODE:
        print(f"├─ {step_name}: Starting...")
    else:
        logger.info(f"Starting {step_name}...")

def log_optimization_step_complete(step_name, additional_info=""):
    """Log the completion of an optimization step."""
    global STEP_START_TIMES
    
    if step_name in STEP_START_TIMES:
        duration = time.time() - STEP_START_TIMES[step_name]
        duration_str = format_duration(duration)
        
        if SUMMARY_MODE:
            if additional_info:
                print(f"├─ {step_name}: ✓ Complete ({duration_str}) - {additional_info}")
            else:
                print(f"├─ {step_name}: ✓ Complete ({duration_str})")
        else:
            logger.info(f"{step_name} completed in {duration_str}")
        
        # Clean up timing
        del STEP_START_TIMES[step_name]
    else:
        if SUMMARY_MODE:
            if additional_info:
                print(f"├─ {step_name}: ✓ Complete - {additional_info}")
            else:
                print(f"├─ {step_name}: ✓ Complete")
        else:
            logger.info(f"{step_name} completed")

def log_optimization_step_failed(step_name, error_msg=""):
    """Log the failure of an optimization step."""
    global STEP_START_TIMES
    
    if step_name in STEP_START_TIMES:
        duration = time.time() - STEP_START_TIMES[step_name]
        duration_str = format_duration(duration)
        
        if SUMMARY_MODE:
            if error_msg:
                print(f"├─ {step_name}: ✗ Failed ({duration_str}) - {error_msg}")
            else:
                print(f"├─ {step_name}: ✗ Failed ({duration_str})")
        else:
            logger.error(f"{step_name} failed after {duration_str}")
        
        # Clean up timing
        del STEP_START_TIMES[step_name]
    else:
        if SUMMARY_MODE:
            if error_msg:
                print(f"├─ {step_name}: ✗ Failed - {error_msg}")
            else:
                print(f"├─ {step_name}: ✗ Failed")
        else:
            logger.error(f"{step_name} failed")

def log_optimization_complete(subject_id, success=True, output_path="", n_multistart=1, best_run=None):
    """Log the completion of optimization for a subject."""
    global OPTIMIZATION_START_TIME
    
    if OPTIMIZATION_START_TIME:
        total_duration = time.time() - OPTIMIZATION_START_TIME
        duration_str = format_duration(total_duration)
        
        if SUMMARY_MODE:
            if success:
                if n_multistart > 1 and best_run:
                    print(f"└─ Flex-search optimization completed successfully for subject: {subject_id} (best run: {best_run}, Total: {duration_str})")
                else:
                    print(f"└─ Flex-search optimization completed successfully for subject: {subject_id} (Total: {duration_str})")
                if output_path:
                    print(f"   Results saved to: {output_path}")
            else:
                print(f"└─ Flex-search optimization failed for subject: {subject_id} (Total: {duration_str})")
        else:
            if success:
                logger.info(f"Flex-search optimization completed successfully for subject: {subject_id} in {duration_str}")
                if output_path:
                    logger.info(f"Results saved to: {output_path}")
            else:
                logger.error(f"Flex-search optimization failed for subject: {subject_id} after {duration_str}")
        
        # Reset timing
        OPTIMIZATION_START_TIME = None
    else:
        if SUMMARY_MODE:
            if success:
                print(f"└─ Flex-search optimization completed successfully for subject: {subject_id}")
            else:
                print(f"└─ Flex-search optimization failed for subject: {subject_id}")
        else:
            if success:
                logger.info(f"Flex-search optimization completed successfully for subject: {subject_id}")
            else:
                logger.error(f"Flex-search optimization failed for subject: {subject_id}")

# -----------------------------------------------------------------------------
# Logger setup
# -----------------------------------------------------------------------------
def setup_logger(output_folder: str, subject_id: str) -> None:
    """Initialize logger with console and file output.
    
    Args:
        output_folder: Path to the directory where logs should be stored
        subject_id: Subject identifier for naming the log file
    """
    global logger
    # Get project directory from environment
    proj_dir = os.getenv("PROJECT_DIR")
    if not proj_dir:
        raise SystemExit("[flex-search] PROJECT_DIR env-var is missing")
    
    # Create logs directory in project derivatives
    logs_dir = os.path.join(proj_dir, "derivatives", "ti-toolbox", "logs", f"sub-{subject_id}")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Set proper permissions for logs directory
    try:
        os.chmod(logs_dir, 0o777)
    except OSError as e:
        if not SUMMARY_MODE:
            print(f"Warning: Could not set permissions for logs directory: {e}")
    
    # Create timestamped log file
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(logs_dir, f'flex_search_{subject_id}_{time_stamp}.log')
    logger = get_logger('flex-search', log_file, overwrite=True)
    
    # Log session header
    if not SUMMARY_MODE:
        logger.info("="*80)
        logger.info(f"FLEX-SEARCH OPTIMIZATION SESSION STARTED")
        logger.info(f"Subject: {subject_id}")
        logger.info(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Output folder: {output_folder}")
        logger.info("="*80)

def _create_multistart_summary_file(
    summary_file: str, 
    args: argparse.Namespace, 
    n_multistart: int, 
    optim_funvalue_list: np.ndarray, 
    best_opt_idx: int, 
    valid_runs: list, 
    failed_runs: list,
    start_time: float
) -> None:
    """Create a detailed summary file for multi-start optimization results.
    
    Args:
        summary_file: Path to the summary file to create
        args: Parsed command line arguments
        n_multistart: Number of optimization runs
        optim_funvalue_list: Array of function values for each run
        best_opt_idx: Index of the best optimization run
        valid_runs: List of (run_number, function_value) tuples for valid runs
        failed_runs: List of run numbers that failed
        start_time: Session start time
    """
    total_duration = time.time() - start_time
    
    with open(summary_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("MULTI-START OPTIMIZATION SUMMARY\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Subject: {args.subject}\n")
        f.write(f"Total session duration: {total_duration:.1f} seconds\n")
        f.write("\n")
        
        # Environment variables
        f.write("ENVIRONMENT VARIABLES:\n")
        f.write("-" * 40 + "\n")
        f.write(f"PROJECT_DIR: {os.getenv('PROJECT_DIR', 'N/A')}\n")
        f.write(f"SUBJECT_ID: {os.getenv('SUBJECT_ID', args.subject)}\n")
        f.write("\n")
        
        # Optimization configuration
        f.write("OPTIMIZATION CONFIGURATION:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Goal: {args.goal}\n")
        f.write(f"Post-processing: {args.postproc}\n")
        f.write(f"ROI Method: {args.roi_method}\n")
        f.write(f"EEG Net: {args.eeg_net}\n")
        f.write(f"Electrode Radius: {args.radius}mm\n")
        f.write(f"Electrode Current: {args.current}mA\n")
        run_final_sim = args.run_final_electrode_simulation and not args.skip_final_electrode_simulation
        f.write(f"Run Final Electrode Simulation: {run_final_sim}\n")
        f.write("\n")
        
        # ROI-specific details
        f.write("ROI CONFIGURATION:\n")
        f.write("-" * 40 + "\n")
        if args.roi_method == "spherical":
            roi_coords = f"({os.getenv('ROI_X')}, {os.getenv('ROI_Y')}, {os.getenv('ROI_Z')})"
            roi_radius = os.getenv("ROI_RADIUS")
            use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
            coord_space = "MNI" if use_mni_coords else "subject"
            f.write(f"ROI Center ({coord_space} space): {roi_coords}\n")
            f.write(f"ROI Radius: {roi_radius}mm\n")
            if use_mni_coords:
                f.write("Note: MNI coordinates transformed to subject space\n")
        elif args.roi_method == "atlas":
            atlas_path = os.getenv("ATLAS_PATH")
            roi_label = os.getenv("ROI_LABEL")
            hemisphere = os.getenv("SELECTED_HEMISPHERE")
            f.write(f"Surface Atlas File: {os.path.basename(atlas_path) if atlas_path else 'N/A'}\n")
            f.write(f"Surface Atlas Path: {atlas_path if atlas_path else 'N/A'}\n")
            f.write(f"ROI Label: {roi_label}\n")
            f.write(f"Hemisphere: {hemisphere}\n")
        elif args.roi_method == "subcortical":
            volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH")
            volume_roi_label = os.getenv("VOLUME_ROI_LABEL")
            f.write(f"Volume Atlas File: {os.path.basename(volume_atlas_path) if volume_atlas_path else 'N/A'}\n")
            f.write(f"Volume Atlas Path: {volume_atlas_path if volume_atlas_path else 'N/A'}\n")
            f.write(f"Volume ROI Label: {volume_roi_label}\n")
        
        # Focality-specific parameters
        if args.goal == "focality":
            f.write("\nNON-ROI CONFIGURATION (Focality):\n")
            f.write("-" * 40 + "\n")
            f.write(f"Non-ROI Method: {args.non_roi_method}\n")
            f.write(f"Threshold Values: {args.thresholds}\n")
            # Include non-ROI details
            if args.roi_method == "spherical":
                if args.non_roi_method == "everything_else":
                    f.write("Non-ROI: Everything else (complement of ROI)\n")
                else:
                    non_roi_coords = f"({os.getenv('NON_ROI_X', 'N/A')}, {os.getenv('NON_ROI_Y', 'N/A')}, {os.getenv('NON_ROI_Z', 'N/A')})"
                    non_roi_radius = os.getenv("NON_ROI_RADIUS", "N/A")
                    f.write(f"Non-ROI Center: {non_roi_coords}\n")
                    f.write(f"Non-ROI Radius: {non_roi_radius}mm\n")
            elif args.roi_method == "atlas":
                if args.non_roi_method == "everything_else":
                    f.write("Non-ROI: Everything else (complement of ROI)\n")
                else:
                    non_roi_atlas_path = os.getenv("NON_ROI_ATLAS_PATH")
                    non_roi_label = os.getenv("NON_ROI_LABEL")
                    f.write(f"Non-ROI Atlas File: {os.path.basename(non_roi_atlas_path) if non_roi_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Atlas Path: {non_roi_atlas_path if non_roi_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Label: {non_roi_label}\n")
            elif args.roi_method == "subcortical":
                if args.non_roi_method == "everything_else":
                    f.write("Non-ROI: Everything else (complement of ROI)\n")
                else:
                    non_roi_volume_atlas_path = os.getenv("VOLUME_NON_ROI_ATLAS_PATH")
                    non_roi_volume_label = os.getenv("VOLUME_NON_ROI_LABEL")
                    f.write(f"Non-ROI Volume Atlas File: {os.path.basename(non_roi_volume_atlas_path) if non_roi_volume_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Volume Atlas Path: {non_roi_volume_atlas_path if non_roi_volume_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Volume Label: {non_roi_volume_label}\n")
        
        f.write("\n")
        f.write(f"Electrode Mapping: {args.enable_mapping}\n")
        if args.enable_mapping:
            f.write(f"Run Mapped Simulation: {not args.disable_mapping_simulation}\n")
        
        # Algorithm parameters
        f.write("\nALGORITHM PARAMETERS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Number of Runs (Multi-start): {n_multistart}\n")
        f.write(f"Max Iterations: {args.max_iterations if args.max_iterations is not None else 'Default'}\n")
        f.write(f"Population Size: {args.population_size if args.population_size is not None else 'Default'}\n")
        f.write(f"CPU Cores: {args.cpus if args.cpus is not None else 'Default'}\n")
        f.write(f"Quiet Mode: {args.quiet}\n")
        f.write("\n")
        
        # Multi-start results
        f.write("MULTI-START OPTIMIZATION RESULTS:\n")
        f.write("=" * 50 + "\n")
        f.write(f"Total runs attempted: {n_multistart}\n")
        f.write(f"Valid runs: {len(valid_runs)}\n")
        f.write(f"Failed runs: {len(failed_runs)}\n")
        f.write("\n")
        
        # Detailed run results
        f.write("DETAILED RUN RESULTS:\n")
        f.write("-" * 30 + "\n")
        f.write(f"{'Run #':<6} {'Status':<10} {'Function Value':<15} {'Notes'}\n")
        f.write("-" * 60 + "\n")
        
        for i_opt, func_val in enumerate(optim_funvalue_list):
            run_number = i_opt + 1
            if func_val == float('inf'):
                status = "FAILED"
                func_val_str = "N/A"
                notes = "Optimization failed - see logs for details"
            else:
                if i_opt == best_opt_idx:
                    status = "BEST"
                    notes = "Selected as final solution"
                else:
                    status = "VALID"
                    notes = "Discarded (higher function value)"
                func_val_str = f"{func_val:.6f}"
            
            f.write(f"{run_number:<6} {status:<10} {func_val_str:<15} {notes}\n")
        
        f.write("\n")
        
        # Statistics for valid runs
        if len(valid_runs) > 1:
            valid_func_values = [val for _, val in valid_runs]
            best_value = min(valid_func_values)
            worst_value = max(valid_func_values)
            mean_value = np.mean(valid_func_values)
            std_value = np.std(valid_func_values)
            improvement = ((worst_value - best_value) / abs(worst_value)) * 100 if worst_value != 0 else 0
            
            f.write("STATISTICAL ANALYSIS (Valid Runs Only):\n")
            f.write("-" * 40 + "\n")
            f.write(f"Best function value: {best_value:.6f}\n")
            f.write(f"Worst function value: {worst_value:.6f}\n")
            f.write(f"Mean function value: {mean_value:.6f}\n")
            f.write(f"Standard deviation: {std_value:.6f}\n")
            f.write(f"Improvement over worst: {improvement:.2f}%\n")
            f.write(f"Function value range: {worst_value - best_value:.6f}\n")
            f.write("\n")
        
        # Best solution details
        f.write("SELECTED SOLUTION:\n")
        f.write("-" * 20 + "\n")
        f.write(f"Run number: {best_opt_idx + 1}\n")
        f.write(f"Function value: {optim_funvalue_list[best_opt_idx]:.6f}\n")
        f.write(f"Output folder: {os.path.basename(os.path.dirname(summary_file))}\n")
        f.write("\n")
        
        # Failed runs details
        if failed_runs:
            f.write("FAILED RUNS ANALYSIS:\n")
            f.write("-" * 25 + "\n")
            f.write(f"Failed run numbers: {failed_runs}\n")
            f.write("Common causes of failure:\n")
            f.write("- Optimization convergence issues\n")
            f.write("- Numerical instabilities\n")
            f.write("- Memory or computational resource limits\n")
            f.write("- ROI or mesh processing errors\n")
            f.write("Check the main log file for specific error details.\n")
            f.write("\n")
        
        # Recommendations
        f.write("RECOMMENDATIONS:\n")
        f.write("-" * 15 + "\n")
        if len(valid_runs) < n_multistart:
            failure_rate = len(failed_runs) / n_multistart * 100
            f.write(f"• {failure_rate:.1f}% of runs failed. Consider:\n")
            f.write("  - Adjusting optimization parameters (population size, iterations)\n")
            f.write("  - Checking ROI definition and mesh quality\n")
            f.write("  - Reducing computational complexity\n")
        
        if len(valid_runs) > 1:
            cv = std_value / abs(mean_value) if mean_value != 0 else 0
            if cv > 0.1:  # High variability
                f.write(f"• High variability in results (CV={cv:.3f}). Consider:\n")
                f.write("  - Increasing number of optimization runs\n")
                f.write("  - Adjusting optimization algorithm parameters\n")
                f.write("  - Verifying problem setup and constraints\n")
            else:
                f.write(f"• Good consistency across runs (CV={cv:.3f})\n")
                f.write("  - Results appear reliable\n")
                f.write("  - Consider using fewer runs for similar problems\n")
        
        f.write("\n")
        f.write("For detailed optimization logs, refer to the main log file.\n")
        f.write("For visualization and analysis, use the generated field maps and summary files.\n")
        f.write("=" * 80 + "\n")


def _create_single_optimization_summary_file(
    summary_file: str, 
    args: argparse.Namespace, 
    function_value: float,
    start_time: float
) -> None:
    """Create a summary file for single optimization results.
    
    Args:
        summary_file: Path to the summary file to create
        args: Parsed command line arguments
        function_value: Final function value
        start_time: Session start time
    """
    total_duration = time.time() - start_time
    
    with open(summary_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("OPTIMIZATION SUMMARY\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Subject: {args.subject}\n")
        f.write(f"Total optimization duration: {total_duration:.1f} seconds\n")
        f.write("\n")
        
        # Environment variables
        f.write("ENVIRONMENT VARIABLES:\n")
        f.write("-" * 40 + "\n")
        f.write(f"PROJECT_DIR: {os.getenv('PROJECT_DIR', 'N/A')}\n")
        f.write(f"SUBJECT_ID: {os.getenv('SUBJECT_ID', args.subject)}\n")
        f.write("\n")
        
        # Optimization configuration
        f.write("OPTIMIZATION CONFIGURATION:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Goal: {args.goal}\n")
        f.write(f"Post-processing: {args.postproc}\n")
        f.write(f"ROI Method: {args.roi_method}\n")
        f.write(f"EEG Net: {args.eeg_net}\n")
        f.write(f"Electrode Radius: {args.radius}mm\n")
        f.write(f"Electrode Current: {args.current}mA\n")
        run_final_sim = args.run_final_electrode_simulation and not args.skip_final_electrode_simulation
        f.write(f"Run Final Electrode Simulation: {run_final_sim}\n")
        f.write("\n")
        
        # ROI-specific details
        f.write("ROI CONFIGURATION:\n")
        f.write("-" * 40 + "\n")
        if args.roi_method == "spherical":
            roi_coords = f"({os.getenv('ROI_X')}, {os.getenv('ROI_Y')}, {os.getenv('ROI_Z')})"
            roi_radius = os.getenv("ROI_RADIUS")
            use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
            coord_space = "MNI" if use_mni_coords else "subject"
            f.write(f"ROI Center ({coord_space} space): {roi_coords}\n")
            f.write(f"ROI Radius: {roi_radius}mm\n")
            if use_mni_coords:
                f.write("Note: MNI coordinates transformed to subject space\n")
        elif args.roi_method == "atlas":
            atlas_path = os.getenv("ATLAS_PATH")
            roi_label = os.getenv("ROI_LABEL")
            hemisphere = os.getenv("SELECTED_HEMISPHERE")
            f.write(f"Surface Atlas File: {os.path.basename(atlas_path) if atlas_path else 'N/A'}\n")
            f.write(f"Surface Atlas Path: {atlas_path if atlas_path else 'N/A'}\n")
            f.write(f"ROI Label: {roi_label}\n")
            f.write(f"Hemisphere: {hemisphere}\n")
        elif args.roi_method == "subcortical":
            volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH")
            volume_roi_label = os.getenv("VOLUME_ROI_LABEL")
            f.write(f"Volume Atlas File: {os.path.basename(volume_atlas_path) if volume_atlas_path else 'N/A'}\n")
            f.write(f"Volume Atlas Path: {volume_atlas_path if volume_atlas_path else 'N/A'}\n")
            f.write(f"Volume ROI Label: {volume_roi_label}\n")
        
        # Focality-specific parameters
        if args.goal == "focality":
            f.write("\nNON-ROI CONFIGURATION (Focality):\n")
            f.write("-" * 40 + "\n")
            f.write(f"Non-ROI Method: {args.non_roi_method}\n")
            f.write(f"Threshold Values: {args.thresholds}\n")
            # Include non-ROI details
            if args.roi_method == "spherical":
                if args.non_roi_method == "everything_else":
                    f.write("Non-ROI: Everything else (complement of ROI)\n")
                else:
                    non_roi_coords = f"({os.getenv('NON_ROI_X', 'N/A')}, {os.getenv('NON_ROI_Y', 'N/A')}, {os.getenv('NON_ROI_Z', 'N/A')})"
                    non_roi_radius = os.getenv("NON_ROI_RADIUS", "N/A")
                    f.write(f"Non-ROI Center: {non_roi_coords}\n")
                    f.write(f"Non-ROI Radius: {non_roi_radius}mm\n")
            elif args.roi_method == "atlas":
                if args.non_roi_method == "everything_else":
                    f.write("Non-ROI: Everything else (complement of ROI)\n")
                else:
                    non_roi_atlas_path = os.getenv("NON_ROI_ATLAS_PATH")
                    non_roi_label = os.getenv("NON_ROI_LABEL")
                    f.write(f"Non-ROI Atlas File: {os.path.basename(non_roi_atlas_path) if non_roi_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Atlas Path: {non_roi_atlas_path if non_roi_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Label: {non_roi_label}\n")
            elif args.roi_method == "subcortical":
                if args.non_roi_method == "everything_else":
                    f.write("Non-ROI: Everything else (complement of ROI)\n")
                else:
                    non_roi_volume_atlas_path = os.getenv("VOLUME_NON_ROI_ATLAS_PATH")
                    non_roi_volume_label = os.getenv("VOLUME_NON_ROI_LABEL")
                    f.write(f"Non-ROI Volume Atlas File: {os.path.basename(non_roi_volume_atlas_path) if non_roi_volume_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Volume Atlas Path: {non_roi_volume_atlas_path if non_roi_volume_atlas_path else 'N/A'}\n")
                    f.write(f"Non-ROI Volume Label: {non_roi_volume_label}\n")
        
        f.write("\n")
        f.write(f"Electrode Mapping: {args.enable_mapping}\n")
        if args.enable_mapping:
            f.write(f"Run Mapped Simulation: {not args.disable_mapping_simulation}\n")
        
        # Algorithm parameters
        f.write("\nALGORITHM PARAMETERS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Max Iterations: {args.max_iterations if args.max_iterations is not None else 'Default'}\n")
        f.write(f"Population Size: {args.population_size if args.population_size is not None else 'Default'}\n")
        f.write(f"CPU Cores: {args.cpus if args.cpus is not None else 'Default'}\n")
        f.write(f"Quiet Mode: {args.quiet}\n")
        f.write("\n")
        
        # Optimization result
        f.write("OPTIMIZATION RESULT:\n")
        f.write("-" * 20 + "\n")
        f.write(f"Final function value: {function_value:.6f}\n")
        f.write(f"Optimization type: Single run (no multi-start)\n")
        f.write("\n")
        
        f.write("For detailed optimization logs, refer to the main log file.\n")
        f.write("For visualization and analysis, use the generated field maps and summary files.\n")
        f.write("=" * 80 + "\n")


# -----------------------------------------------------------------------------
# Argument parsing (mapping is OFF by default)
# -----------------------------------------------------------------------------

def parse_arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="flex-search",
        description="Optimise TI stimulation and (optionally) map final "
                    "electrodes to the nearest EEG-net nodes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # core parameters
    p.add_argument("--subject", required=True)
    p.add_argument("--goal", choices=["mean", "max", "focality"], required=True)
    p.add_argument("--postproc", choices=["max_TI", "dir_TI_normal", "dir_TI_tangential"], required=True)
    p.add_argument("--eeg-net", required=True, help="CSV filename in eeg_positions (without .csv)")
    p.add_argument("--radius", type=float, required=True)
    p.add_argument("--current", type=float, required=True)
    p.add_argument("--roi-method", choices=["spherical", "atlas", "subcortical"], required=True)

    # focality-specific arguments
    p.add_argument("--thresholds", help="single value or two comma-separated values")
    p.add_argument("--non-roi-method", choices=["everything_else", "specific"], help="When goal=focality")

    # mapping (disabled by default)
    p.add_argument("--enable-mapping", action="store_true", help="Map to nearest EEG-net nodes")
    p.add_argument("--disable-mapping-simulation", action="store_true", help="Skip extra simulation with mapped electrodes")

    # output control
    p.add_argument("--quiet", action="store_true", help="Suppress optimization step output")
    p.add_argument("--run-final-electrode-simulation", action="store_true", default=True, help="Run final simulation with optimal electrodes (default: True)")
    p.add_argument("--skip-final-electrode-simulation", action="store_true", help="Skip final simulation with optimal electrodes")

    # Stability and Performance arguments
    p.add_argument("--n-multistart", type=int, default=1, help="Number of optimization runs (multi-start). Best result will be kept.")
    p.add_argument("--max-iterations", type=int, help="Maximum optimization iterations for differential_evolution.")
    p.add_argument("--population-size", type=int, help="Population size for differential_evolution.")
    p.add_argument("--cpus", type=int, help="Number of CPU cores to utilize.")

    return p.parse_args()

# -----------------------------------------------------------------------------
# Helper: simple ROI directory name
# -----------------------------------------------------------------------------

def roi_dirname(args: argparse.Namespace) -> str:
    """Generate output directory name following the naming convention:
    - Atlas: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
    - Spherical: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
    - Subcortical: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
    """
    # Convert postproc to shorter format
    postproc_map = {
        "max_TI": "maxTI",
        "dir_TI_normal": "normalTI", 
        "dir_TI_tangential": "tangentialTI"
    }
    postproc_short = postproc_map.get(args.postproc, args.postproc)
    
    if args.roi_method == "spherical":
        # Format: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
        roi_x = os.getenv('ROI_X', '0')
        roi_y = os.getenv('ROI_Y', '0') 
        roi_z = os.getenv('ROI_Z', '0')
        roi_radius = os.getenv('ROI_RADIUS', '10')
        base = f"sphere_x{roi_x}y{roi_y}z{roi_z}r{roi_radius}"
    elif args.roi_method == "atlas":
        # Format: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
        atlas_path = os.getenv("ATLAS_PATH", "")
        hemisphere = os.getenv("SELECTED_HEMISPHERE", "lh")
        roi_label = os.getenv("ROI_LABEL", "0")
        
        # Extract atlas name from path (e.g., lh.101_DK40.annot -> DK40)
        if atlas_path:
            atlas_filename = os.path.basename(atlas_path)
            # Remove hemisphere prefix and .annot suffix, then extract atlas name
            # e.g., lh.101_DK40.annot -> 101_DK40 -> DK40
            atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(".annot", "")
            atlas_name = atlas_with_subject.split("_", 1)[-1] if "_" in atlas_with_subject else atlas_with_subject
        else:
            atlas_name = "atlas"
        
        base = f"{hemisphere}_{atlas_name}_{roi_label}"
    else:  # subcortical
        # Format: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
        volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
        roi_label = os.getenv("VOLUME_ROI_LABEL", "0")
        
        if volume_atlas_path:
            volume_atlas = os.path.basename(volume_atlas_path)
            # Remove file extensions
            if volume_atlas.endswith('.nii.gz'):
                volume_atlas = volume_atlas[:-7]
            elif volume_atlas.endswith('.mgz'):
                volume_atlas = volume_atlas[:-4]
            elif volume_atlas.endswith('.nii'):
                volume_atlas = volume_atlas[:-4]
        else:
            volume_atlas = "volume"
        
        base = f"subcortical_{volume_atlas}_{roi_label}"
    
    return f"{base}_{args.goal}_{postproc_short}"

# -----------------------------------------------------------------------------
# Set-up optimisation object
# -----------------------------------------------------------------------------

def build_optimisation(args: argparse.Namespace) -> opt_struct.TesFlexOptimization:
    opt = opt_struct.TesFlexOptimization()

    proj_dir = os.getenv("PROJECT_DIR")
    if not proj_dir:
        raise SystemExit("[flex-search] PROJECT_DIR env-var is missing")

    opt.subpath = os.path.join(proj_dir, "derivatives", "SimNIBS", f"sub-{args.subject}", f"m2m_{args.subject}")
    opt.output_folder = os.path.join(proj_dir, "derivatives", "SimNIBS", f"sub-{args.subject}", "flex-search", roi_dirname(args))
    os.makedirs(opt.output_folder, exist_ok=True)

    # goals / thresholds -------------------------------------------------------
    opt.goal = args.goal
    if args.goal == "focality":
        if not args.thresholds:
            raise SystemExit("--thresholds required for focality goal")
        vals = [float(v) for v in args.thresholds.split(",")]
        opt.threshold = vals if len(vals) > 1 else vals[0]
        if not args.non_roi_method:
            raise SystemExit("--non-roi-method required for focality goal")

    opt.e_postproc = args.postproc
    opt.open_in_gmsh = False  # never auto-launch GUI
    
    # final electrode simulation control ------------------------------------
    opt.run_final_electrode_simulation = args.run_final_electrode_simulation and not args.skip_final_electrode_simulation

    # mapping --------------------------------------------------------------
    if args.enable_mapping:
        opt.map_to_net_electrodes = True
        opt.net_electrode_file = os.path.join(opt.subpath, "eeg_positions", f"{args.eeg_net}.csv")
        if not os.path.isfile(opt.net_electrode_file):
            raise SystemExit(f"EEG net file not found: {opt.net_electrode_file}")
        if hasattr(opt, "run_mapped_electrodes_simulation") and not args.disable_mapping_simulation:
            opt.run_mapped_electrodes_simulation = True
    else:
        # Initialize electrode_mapping to None when mapping is disabled
        # This prevents AttributeError in SimNIBS logging code that checks for this attribute
        opt.electrode_mapping = None


    # electrodes -----------------------------------------------------------
    r_m = args.radius
    c_A = args.current / 1000.0  # mA → A
    for _ in range(2):  # two pairs for TI
        el = opt.add_electrode_layout("ElectrodeArrayPair")
        el.radius = [r_m]
        el.current = [c_A, -c_A]

    # ROI ------------------------------------------------------------------
    if args.roi_method == "spherical":
        _roi_spherical(opt, args)
    elif args.roi_method == "atlas":
        _roi_atlas(opt, args)
    else:  # subcortical
        _roi_subcortical(opt, args)

    return opt

# -----------------------------------------------------------------------------
# ROI helpers
# -----------------------------------------------------------------------------

def _roi_spherical(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.roi_sphere_center_space = "subject"
    
    # Get coordinates from environment variables with proper defaults
    roi_x = float(os.getenv("ROI_X", "0"))
    roi_y = float(os.getenv("ROI_Y", "0"))
    roi_z = float(os.getenv("ROI_Z", "0"))
    radius = float(os.getenv("ROI_RADIUS", "10"))
    
    # Check if MNI coordinates should be used (for multiple subjects)
    use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
    
    if use_mni_coords:
        # Transform MNI coordinates to subject space
        print(f"[flex-search] Transforming MNI coordinates [{roi_x}, {roi_y}, {roi_z}] to subject space")
        try:
            # Use simnibs.mni2subject_coords to transform coordinates
            m2m_path = opt.subpath
            subject_coords = mni2subject_coords([roi_x, roi_y, roi_z], m2m_path)
            roi.roi_sphere_center = subject_coords
            print(f"[flex-search] Transformed coordinates: {subject_coords}")
        except Exception as e:
            print(f"[flex-search] ERROR: Failed to transform MNI coordinates to subject space: {e}")
            raise SystemExit(f"MNI coordinate transformation failed: {e}")
    else:
        # Use coordinates as-is (subject space)
        roi.roi_sphere_center = [roi_x, roi_y, roi_z]
    
    roi.roi_sphere_radius = radius

    # Add non-ROI if focality optimisation is requested
    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if args.non_roi_method == "everything_else":
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = roi.roi_sphere_center
            non_roi.roi_sphere_radius = radius
            non_roi.roi_sphere_operator = ["difference"]
            non_roi.weight = -1
        else:  # specific non-ROI defined via env vars
            # Get non-ROI coordinates with proper defaults
            nx = float(os.getenv("NON_ROI_X", "0"))
            ny = float(os.getenv("NON_ROI_Y", "0"))
            nz = float(os.getenv("NON_ROI_Z", "0"))
            nr = float(os.getenv("NON_ROI_RADIUS", "10"))
            
            # Check if non-ROI coordinates are also MNI
            use_mni_coords_non_roi = os.getenv("USE_MNI_COORDS_NON_ROI", "false").lower() == "true"
            
            if use_mni_coords_non_roi:
                # Transform non-ROI MNI coordinates to subject space
                print(f"[flex-search] Transforming non-ROI MNI coordinates [{nx}, {ny}, {nz}] to subject space")
                try:
                    m2m_path = opt.subpath
                    non_roi_subject_coords = mni2subject_coords([nx, ny, nz], m2m_path)
                    non_roi.roi_sphere_center = non_roi_subject_coords
                    print(f"[flex-search] Transformed non-ROI coordinates: {non_roi_subject_coords}")
                except Exception as e:
                    print(f"[flex-search] ERROR: Failed to transform non-ROI MNI coordinates to subject space: {e}")
                    raise SystemExit(f"Non-ROI MNI coordinate transformation failed: {e}")
            else:
                # Use non-ROI coordinates as-is (subject space)
                non_roi.roi_sphere_center = [nx, ny, nz]
            
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_radius = nr
            non_roi.weight = -1

def _roi_atlas(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    hemi = os.getenv("SELECTED_HEMISPHERE", "lh")
    roi.mask_space = [f"subject_{hemi}"]
    roi.mask_path = [os.getenv("ATLAS_PATH", "")]
    label_val = int(os.getenv("ROI_LABEL", "1"))
    roi.mask_value = [label_val]

    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if args.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
        else:
            non_roi_label = int(os.getenv("NON_ROI_LABEL", "1"))
            non_roi_atlas_path = os.getenv("NON_ROI_ATLAS_PATH", "")
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = [non_roi_atlas_path]
            non_roi.mask_value = [non_roi_label]
            non_roi.weight = -1

def _roi_subcortical(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
    label_val = int(os.getenv("VOLUME_ROI_LABEL", "10"))
    
    # Validate that the volume atlas file exists
    if not volume_atlas_path or not os.path.isfile(volume_atlas_path):
        raise SystemExit(f"Volume atlas file not found: {volume_atlas_path}")
    
    # Note: logger not available during optimization setup, will log later
    
    roi = opt.add_roi()
    roi.method = "volume"
    roi.mask_space = ["subject"]
    roi.mask_path = [volume_atlas_path]
    roi.mask_value = [label_val]
    
    # Add some additional properties that might help with volume ROI processing
    roi.tissues = [ElementTags.GM]  # Gray matter tissue for volume ROI

    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "volume"

        if args.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
            non_roi.tissues = [ElementTags.GM]  # Gray matter
        else:
            non_roi_label = int(os.getenv("VOLUME_NON_ROI_LABEL", "10"))
            non_roi_atlas_path = os.getenv("VOLUME_NON_ROI_ATLAS_PATH", "")
            if not non_roi_atlas_path or not os.path.isfile(non_roi_atlas_path):
                raise SystemExit(f"Non-ROI volume atlas file not found: {non_roi_atlas_path}")
            non_roi.mask_space = ["subject"]
            non_roi.mask_path = [non_roi_atlas_path]
            non_roi.mask_value = [non_roi_label]
            non_roi.weight = -1
            non_roi.tissues = [ElementTags.GM]  # Gray matter

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    args = parse_arguments()
    
    # Enable summary mode if quiet flag is set OR if not in debug mode
    # When DEBUG_MODE=true, show detailed output (SUMMARY_MODE=false)
    # When DEBUG_MODE=false, show summary output (SUMMARY_MODE=true)
    debug_mode = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    if args.quiet or not debug_mode:
        set_summary_mode(True)
    
    # Track total session time
    start_time = time.time()
    
    # Multi-start optimization logic
    n_multistart = args.n_multistart
    optim_funvalue_list = np.zeros(n_multistart)
    
    # First build optimization to get the base output folder structure
    try:
        opt_base = build_optimisation(args)
        base_output_folder = opt_base.output_folder
        
        # Setup logger after base output folder is created
        setup_logger(base_output_folder, args.subject)
        
        # Configure SimNIBS related loggers to use our logging setup (needed for both modes)
        configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct', 'opt_struct'], logger)
        
        if not SUMMARY_MODE:
            logger.info(f"Base output directory: {base_output_folder}")
            
            # Log the command that was called
            command = " ".join(sys.argv)
            logger.info(f"Command: {command}")
            
            # Log multi-start parameters
            if n_multistart > 1:
                logger.info(f"Running multi-start optimization with {n_multistart} runs")
            else:
                logger.info("Running single optimization")
            
    except Exception as exc:
        print(f"ERROR during setup: {exc}", file=sys.stderr)
        return 1

    # Create output folder list for each run
    output_folder_list = [
        os.path.join(base_output_folder, f"{i_opt:02d}") for i_opt in range(n_multistart)
    ]
    
    # Log optimization start with summary
    log_optimization_start(args.subject, args.goal, args.postproc, args.roi_method, n_multistart)
    
    # Run multiple optimizations
    for i_opt in range(n_multistart):
        run_start_time = time.time()
        
        # Enhanced logging for each optimization run
        if not SUMMARY_MODE:
            logger.info("-" * 60)
            if n_multistart > 1:
                logger.info(f"OPTIMIZATION RUN {i_opt + 1}/{n_multistart}")
                logger.info(f"Run output folder: {output_folder_list[i_opt]}")
            else:
                logger.info("SINGLE OPTIMIZATION RUN")
            logger.info("-" * 60)
        
        try:
            # Build optimization for this specific run
            opt = build_optimisation(args)
            
            # Override output folder to numbered subfolder
            opt.output_folder = output_folder_list[i_opt]
            os.makedirs(opt.output_folder, exist_ok=True)
            
            # Handle run_final_electrode_simulation parameter
            run_final_sim = args.run_final_electrode_simulation and not args.skip_final_electrode_simulation
            
            # Log optimization parameters (only for first run to avoid repetition)
            if i_opt == 0:
                if not SUMMARY_MODE:
                    logger.info("OPTIMIZATION CONFIGURATION:")
                    logger.info(f"  Subject: {args.subject}")
                    logger.info(f"  Goal: {args.goal}")
                    logger.info(f"  Post-processing: {args.postproc}")
                    logger.info(f"  ROI Method: {args.roi_method}")
                    logger.info(f"  EEG Net: {args.eeg_net}")
                    logger.info(f"  Electrode Radius: {args.radius}mm")
                    logger.info(f"  Electrode Current: {args.current}mA")
                    logger.info(f"  Run Final Electrode Simulation: {run_final_sim}")
                    
                    # Log ROI-specific details
                    if args.roi_method == "subcortical":
                        volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH")
                        volume_roi_label = os.getenv("VOLUME_ROI_LABEL")
                        logger.info(f"  Volume Atlas: {volume_atlas_path}")
                        logger.info(f"  Volume ROI Label: {volume_roi_label}")
                    elif args.roi_method == "atlas":
                        atlas_path = os.getenv("ATLAS_PATH")
                        roi_label = os.getenv("ROI_LABEL")
                        hemisphere = os.getenv("SELECTED_HEMISPHERE")
                        logger.info(f"  Surface Atlas: {os.path.basename(atlas_path) if atlas_path else 'N/A'}")
                        logger.info(f"  ROI Label: {roi_label}")
                        logger.info(f"  Hemisphere: {hemisphere}")
                    elif args.roi_method == "spherical":
                        roi_coords = f"({os.getenv('ROI_X')}, {os.getenv('ROI_Y')}, {os.getenv('ROI_Z')})"
                        roi_radius = os.getenv("ROI_RADIUS")
                        use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
                        coord_space = "MNI" if use_mni_coords else "subject"
                        logger.info(f"  ROI Center ({coord_space} space): {roi_coords}")
                        logger.info(f"  ROI Radius: {roi_radius}mm")
                        if use_mni_coords:
                            logger.info(f"  Note: MNI coordinates will be transformed to subject space")
                    
                    # Log focality-specific parameters
                    if args.goal == "focality":
                        logger.info(f"  Non-ROI Method: {args.non_roi_method}")
                        logger.info(f"  Threshold Values: {args.thresholds}")
                    
                    logger.info(f"  Electrode Mapping: {args.enable_mapping}")
                    if args.enable_mapping:
                        logger.info(f"  Run Mapped Simulation: {not args.disable_mapping_simulation}")
                        
                    # Log optimization algorithm parameters
                    logger.info("OPTIMIZATION ALGORITHM SETTINGS:")
                    logger.info(f"  Max Iterations: {args.max_iterations if args.max_iterations is not None else 'Default'}")
                    logger.info(f"  Population Size: {args.population_size if args.population_size is not None else 'Default'}")
                    logger.info(f"  CPU Cores: {args.cpus if args.cpus is not None else 'Default'}")
                    logger.info(f"  Quiet Mode: {args.quiet}")
                    
                    if n_multistart > 1:
                        logger.info(f"  Multi-start Runs: {n_multistart}")
                        logger.info(f"  Note: Best result will be automatically selected based on function value")
            
            # Set optimizer display option based on quiet mode
            if args.quiet:
                if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
                    opt._optimizer_options_std["disp"] = False
                elif not SUMMARY_MODE:
                    logger.warning("opt._optimizer_options_std not found or not a dict, cannot set disp for quiet mode.")

            # Apply max_iterations and population_size if provided
            if args.max_iterations is not None:
                if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
                    opt._optimizer_options_std["maxiter"] = args.max_iterations
                    if not SUMMARY_MODE:
                        logger.debug(f"Set max iterations to {args.max_iterations}")
                elif not SUMMARY_MODE:
                    logger.warning("opt._optimizer_options_std not found or not a dict, cannot set maxiter.")
            
            if args.population_size is not None:
                if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
                    opt._optimizer_options_std["popsize"] = args.population_size
                    if not SUMMARY_MODE:
                        logger.debug(f"Set population size to {args.population_size}")
                elif not SUMMARY_MODE:
                    logger.warning("opt._optimizer_options_std not found or not a dict, cannot set popsize.")
            
            # Log run start
            cpus_to_pass = args.cpus if args.cpus is not None else None
            if not SUMMARY_MODE:
                if n_multistart > 1:
                    logger.info(f"Starting optimization run {i_opt + 1}/{n_multistart}...")
                else:
                    logger.info("Starting optimization...")
            
            # Log optimization step start for summary
            if n_multistart > 1:
                log_optimization_step_start(f"Optimization run {i_opt + 1}/{n_multistart}")
            else:
                log_optimization_step_start("Optimization")
            
            # Run optimization
            optimization_start_time = time.time()
            opt.run(cpus=cpus_to_pass)
            optimization_end_time = time.time()
            
            # Store the optimization function value
            optim_funvalue_list[i_opt] = opt.optim_funvalue
            
            # Only log detailed results in non-summary mode
            if not SUMMARY_MODE:
                optimization_duration = optimization_end_time - optimization_start_time
                run_duration = time.time() - run_start_time
                logger.info("OPTIMIZATION RUN COMPLETED:")
                logger.info(f"  Function Value: {opt.optim_funvalue:.6f}")
                logger.info(f"  Optimization Duration: {optimization_duration:.1f} seconds")
                logger.info(f"  Total Run Duration: {run_duration:.1f} seconds")
                if hasattr(opt, 'optim_result') and hasattr(opt.optim_result, 'nfev'):
                    logger.info(f"  Function Evaluations: {opt.optim_result.nfev}")
                if hasattr(opt, 'optim_result') and hasattr(opt.optim_result, 'success'):
                    logger.info(f"  Optimization Success: {opt.optim_result.success}")
            
            # Log optimization step complete for summary
            if n_multistart > 1:
                log_optimization_step_complete(f"Optimization run {i_opt + 1}/{n_multistart}")
            else:
                log_optimization_step_complete("Optimization")
            
            # Log final electrode simulation if enabled
            if run_final_sim:
                log_optimization_step_start("Final electrode simulation")
                # Note: The actual simulation happens during the optimization run
                # We'll mark it as complete here since it's part of the optimization process
                log_optimization_step_complete("Final electrode simulation")
                
        except IndexError as exc:
            # Special handling for the index error we're seeing
            if not SUMMARY_MODE:
                logger.error(f"IndexError in run {i_opt + 1} (likely in post-processing): {exc}")
                logger.info("This error may occur during final analysis but optimization itself likely completed")
                logger.warning(f"Setting penalty value for run {i_opt + 1} due to IndexError")
            # Set a high penalty value for this run so it won't be selected as best
            optim_funvalue_list[i_opt] = float('inf')
            
            # Log failure for summary
            if n_multistart > 1:
                log_optimization_step_failed(f"Optimization run {i_opt + 1}/{n_multistart}", "IndexError in post-processing")
            else:
                log_optimization_step_failed("Optimization", "IndexError in post-processing")
        except Exception as exc:
            run_duration = time.time() - run_start_time
            if not SUMMARY_MODE:
                logger.error(f"ERROR in optimization run {i_opt + 1} after {run_duration:.1f} seconds:")
                logger.error(f"  Error type: {type(exc).__name__}")
                logger.error(f"  Error message: {str(exc)}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                logger.warning(f"Setting penalty value for run {i_opt + 1} due to error")
            # Set a high penalty value for this run so it won't be selected as best
            optim_funvalue_list[i_opt] = float('inf')
            
            # Log failure for summary
            if n_multistart > 1:
                log_optimization_step_failed(f"Optimization run {i_opt + 1}/{n_multistart}", f"{type(exc).__name__}: {str(exc)}")
            else:
                log_optimization_step_failed("Optimization", f"{type(exc).__name__}: {str(exc)}")
    
    # Multi-start post-processing: find best solution and clean up
    if n_multistart > 1:
        if not SUMMARY_MODE:
            logger.info("=" * 80)
            logger.info("MULTI-START OPTIMIZATION POST-PROCESSING")
            logger.info("=" * 80)
        
        # Log post-processing step start for summary
        log_optimization_step_start("Post-processing")
        
        # Log all function values with detailed breakdown
        if not SUMMARY_MODE:
            logger.info("OPTIMIZATION RESULTS SUMMARY:")
            valid_runs = []
            failed_runs = []
            
            for i_opt, func_val in enumerate(optim_funvalue_list):
                run_number = i_opt + 1
                if func_val == float('inf'):
                    logger.info(f"  Run {run_number:2d}: FAILED")
                    failed_runs.append(run_number)
                else:
                    logger.info(f"  Run {run_number:2d}: {func_val:.6f}")
                    valid_runs.append((run_number, func_val))
            
            logger.info(f"Valid runs: {len(valid_runs)}/{n_multistart}")
            if failed_runs:
                logger.warning(f"Failed runs: {failed_runs}")
        else:
            # In summary mode, just track valid/failed runs without logging
            valid_runs = []
            failed_runs = []
            for i_opt, func_val in enumerate(optim_funvalue_list):
                if func_val != float('inf'):
                    valid_runs.append((i_opt, func_val))
        
        if not valid_runs:
            if not SUMMARY_MODE:
                logger.error("No valid optimization results found - all runs failed")
                logger.error("Check individual run logs above for specific error details")
            
            # Log failure for summary
            log_optimization_step_failed("Post-processing", "No valid optimization results found")
            log_optimization_complete(args.subject, success=False, n_multistart=n_multistart)
            return 1
        
        # Find best solution (minimum function value among valid runs)
        best_opt_idx = np.argmin(optim_funvalue_list)
        best_funvalue = optim_funvalue_list[best_opt_idx]
        best_run_number = best_opt_idx + 1
        
        if not SUMMARY_MODE:
            logger.info(f"BEST SOLUTION SELECTION:")
            logger.info(f"  Best run: #{best_run_number}")
            logger.info(f"  Best function value: {best_funvalue:.6f}")
            
            # Find improvement statistics
            if len(valid_runs) > 1:
                valid_func_values = [val for _, val in valid_runs]
                worst_value = max(valid_func_values)
                improvement = ((worst_value - best_funvalue) / abs(worst_value)) * 100 if worst_value != 0 else 0
                logger.info(f"  Improvement over worst: {improvement:.2f}%")
                logger.info(f"  Function value range: {min(valid_func_values):.6f} to {max(valid_func_values):.6f}")
        
        # Copy best solution to base output folder and remove numbered subfolders
        best_folder = output_folder_list[best_opt_idx]
        
        if not SUMMARY_MODE:
            logger.info("FINALIZING RESULTS:")
            if os.path.exists(best_folder) and best_funvalue != float('inf'):
                logger.info(f"Copying best solution from: {best_folder}")
                logger.info(f"Copying best solution to: {base_output_folder}")
                
                # Copy contents of best solution to main output directory
                try:
                    for item in os.listdir(best_folder):
                        src = os.path.join(best_folder, item)
                        dst = os.path.join(base_output_folder, item)
                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            if os.path.exists(dst):
                                os.remove(dst)
                            shutil.copy2(src, dst)
                    logger.info("✓ Best solution successfully copied to final output directory")
                except Exception as exc:
                    logger.error(f"✗ Failed to copy best solution: {exc}")
                    
                    # Log failure for summary
                    log_optimization_step_failed("Post-processing", f"Failed to copy best solution: {exc}")
                    log_optimization_complete(args.subject, success=False, n_multistart=n_multistart)
                    return 1
            else:
                logger.error("✗ Best solution folder not found or invalid")
                
                # Log failure for summary
                log_optimization_step_failed("Post-processing", "Best solution folder not found or invalid")
                log_optimization_complete(args.subject, success=False, n_multistart=n_multistart)
                return 1
        else:
            # In summary mode, still need to copy the best solution
            if os.path.exists(best_folder) and best_funvalue != float('inf'):
                try:
                    for item in os.listdir(best_folder):
                        src = os.path.join(best_folder, item)
                        dst = os.path.join(base_output_folder, item)
                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            if os.path.exists(dst):
                                os.remove(dst)
                            shutil.copy2(src, dst)
                except Exception as exc:
                    # Log failure for summary
                    log_optimization_step_failed("Post-processing", f"Failed to copy best solution: {exc}")
                    log_optimization_complete(args.subject, success=False, n_multistart=n_multistart)
                    return 1
            else:
                # Log failure for summary
                log_optimization_step_failed("Post-processing", "Best solution folder not found or invalid")
                log_optimization_complete(args.subject, success=False, n_multistart=n_multistart)
                return 1
        
        # Create detailed multi-start summary file after copying
        multistart_summary_file = os.path.join(base_output_folder, "multistart_optimization_summary.txt")
        try:
            _create_multistart_summary_file(
                multistart_summary_file, 
                args, 
                n_multistart, 
                optim_funvalue_list, 
                int(best_opt_idx), 
                valid_runs, 
                failed_runs,
                start_time
            )
            if not SUMMARY_MODE:
                logger.info(f"Multi-start summary saved to: {multistart_summary_file}")
        except Exception as e:
            if not SUMMARY_MODE:
                logger.warning(f"Failed to create multi-start summary file: {e}")
        
        # Brief pause to ensure all file operations complete
        time.sleep(0.1)
        
        # Clean up numbered subdirectories with retry
        if not SUMMARY_MODE:
            logger.info("CLEANING UP TEMPORARY DIRECTORIES:")
        cleanup_success = True
        for i_opt in range(n_multistart):
            folder_to_remove = output_folder_list[i_opt]
            run_number = i_opt + 1
            
            # Try cleanup with one retry
            for attempt in range(2):
                try:
                    if os.path.exists(folder_to_remove):
                        shutil.rmtree(folder_to_remove)
                    if not SUMMARY_MODE:
                        logger.debug(f"✓ Removed temporary directory for run {run_number}")
                    break
                except Exception as exc:
                    if attempt == 0:  # First attempt failed, wait and retry
                        time.sleep(0.2)
                        continue
                    else:  # Second attempt failed
                        if not SUMMARY_MODE:
                            logger.warning(f"✗ Failed to remove temporary directory for run {run_number}: {folder_to_remove} - {exc}")
                        cleanup_success = False
        
        if cleanup_success:
            if not SUMMARY_MODE:
                logger.info("✓ All temporary directories cleaned up successfully")
        else:
            if not SUMMARY_MODE:
                logger.warning("⚠ Some temporary directories could not be removed (results still valid)")
        
        if not SUMMARY_MODE:
            logger.info("MULTI-START OPTIMIZATION COMPLETED SUCCESSFULLY")
            logger.info(f"Final results available in: {base_output_folder}")
        
        # Log post-processing complete for summary
        log_optimization_step_complete("Post-processing", f"{len(valid_runs)}/{n_multistart} runs successful")
        
    else:
        # Single optimization run
        if optim_funvalue_list[0] == float('inf'):
            if not SUMMARY_MODE:
                logger.error("Single optimization run failed")
            
            # Log failure for summary
            log_optimization_complete(args.subject, success=False)
            return 1
        else:
            # Only log in non-summary mode
            if not SUMMARY_MODE:
                logger.info("SINGLE OPTIMIZATION COMPLETED SUCCESSFULLY")
                logger.info(f"Final function value: {optim_funvalue_list[0]:.6f}")
            
            # For single optimization, also copy from 00 subdirectory to base and clean up
            # This ensures consistent structure with multi-start optimization
            single_run_folder = output_folder_list[0]  # The 00 subdirectory
            
            if not SUMMARY_MODE:
                logger.info("FINALIZING RESULTS:")
                logger.info(f"Moving results from: {single_run_folder}")
                logger.info(f"Moving results to: {base_output_folder}")
            
            # Copy contents from 00 subdirectory to main output directory
            if os.path.exists(single_run_folder):
                try:
                    for item in os.listdir(single_run_folder):
                        src = os.path.join(single_run_folder, item)
                        dst = os.path.join(base_output_folder, item)
                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            if os.path.exists(dst):
                                os.remove(dst)
                            shutil.copy2(src, dst)
                    
                    if not SUMMARY_MODE:
                        logger.info("✓ Results successfully moved to final output directory")
                        
                    # Create a simple summary file for single optimization
                    single_summary_file = os.path.join(base_output_folder, "optimization_summary.txt")
                    try:
                        _create_single_optimization_summary_file(single_summary_file, args, optim_funvalue_list[0], start_time)
                        if not SUMMARY_MODE:
                            logger.info(f"Optimization summary saved to: {single_summary_file}")
                    except Exception as e:
                        if not SUMMARY_MODE:
                            logger.warning(f"Failed to create optimization summary file: {e}")
                    
                    # Brief pause to ensure all file operations complete
                    time.sleep(0.1)
                    
                    # Clean up the 00 subdirectory
                    if not SUMMARY_MODE:
                        logger.info("CLEANING UP TEMPORARY DIRECTORY:")
                    
                    # Try cleanup with one retry
                    for attempt in range(2):
                        try:
                            if os.path.exists(single_run_folder):
                                shutil.rmtree(single_run_folder)
                            if not SUMMARY_MODE:
                                logger.info("✓ Removed temporary directory")
                            break
                        except Exception as exc:
                            if attempt == 0:  # First attempt failed, wait and retry
                                time.sleep(0.2)
                                continue
                            else:  # Second attempt failed
                                if not SUMMARY_MODE:
                                    logger.warning(f"✗ Failed to remove temporary directory: {single_run_folder} - {exc}")
                                    logger.warning("⚠ Temporary directory could not be removed (results still valid)")
                    
                    if not SUMMARY_MODE:
                        logger.info(f"Results available in: {base_output_folder}")
                        
                except Exception as exc:
                    if not SUMMARY_MODE:
                        logger.error(f"Failed to move results: {exc}")
                    # Log failure for summary
                    log_optimization_complete(args.subject, success=False)
                    return 1
            else:
                if not SUMMARY_MODE:
                    logger.error("Single run folder not found")
                # Log failure for summary
                log_optimization_complete(args.subject, success=False)
                return 1
    
    # Log session footer
    total_duration = time.time() - start_time if 'start_time' in locals() else 0
    if not SUMMARY_MODE:
        logger.info("=" * 80)
        logger.info("FLEX-SEARCH SESSION COMPLETED")
        logger.info(f"Total session duration: {total_duration:.1f} seconds")
        logger.info(f"Subject: {args.subject}")
        logger.info(f"Optimization runs: {n_multistart}")
        logger.info("=" * 80)
    
    # Log final completion for summary
    if n_multistart > 1:
        log_optimization_complete(args.subject, success=True, output_path=base_output_folder, n_multistart=n_multistart, best_run=best_run_number if 'best_run_number' in locals() else None)
    else:
        log_optimization_complete(args.subject, success=True, output_path=base_output_folder, n_multistart=n_multistart)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
