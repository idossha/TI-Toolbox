#!/usr/bin/env simnibs_python
"""Multi-start optimization module for flex-search.

This module handles multi-start optimization logic, including:
- Running multiple optimization iterations
- Tracking and comparing results across runs
- Selecting the best solution
- Generating detailed summary reports
"""

from __future__ import annotations

import os
import sys
import shutil
import time
import traceback
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    import argparse
    from simnibs import opt_struct
    from logging import Logger

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def run_single_optimization(
    opt: opt_struct.TesFlexOptimization,
    cpus: Optional[int],
    logger: Logger
) -> float:
    """Run a single optimization and return the function value.
    
    Args:
        opt: SimNIBS optimization object
        cpus: Number of CPU cores to use (None for default)
        logger: Logger instance for output
        
    Returns:
        Function value from optimization (inf if failed)
    """
    try:
        opt.run(cpus=cpus)
        return opt.optim_funvalue
    except IndexError as exc:
        # Special handling for the index error that can occur in post-processing
        logger.error(f"IndexError (likely in post-processing): {exc}")
        logger.info("This error may occur during final analysis but optimization itself likely completed")
        return float('inf')
    except Exception as exc:
        logger.error(f"ERROR in optimization:")
        logger.error(f"  Error type: {type(exc).__name__}")
        logger.error(f"  Error message: {str(exc)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return float('inf')


def select_best_solution(
    optim_funvalue_list: np.ndarray,
    n_multistart: int,
    logger: Logger
) -> tuple[int, list, list]:
    """Analyze optimization results and select the best solution.
    
    Args:
        optim_funvalue_list: Array of function values for each run
        n_multistart: Number of optimization runs
        logger: Logger instance for output
        
    Returns:
        Tuple of (best_opt_idx, valid_runs, failed_runs)
        where valid_runs is list of (run_number, func_val) tuples
        and failed_runs is list of run numbers
    """
    logger.debug("OPTIMIZATION RESULTS SUMMARY:")
    
    valid_runs = []
    failed_runs = []
    
    for i_opt, func_val in enumerate(optim_funvalue_list):
        run_number = i_opt + 1
        if func_val == float('inf'):
            logger.debug(f"  Run {run_number:2d}: FAILED")
            failed_runs.append(run_number)
        else:
            logger.debug(f"  Run {run_number:2d}: {func_val:.6f}")
            valid_runs.append((run_number, func_val))
    
    logger.debug(f"Valid runs: {len(valid_runs)}/{n_multistart}")
    if failed_runs:
        logger.warning(f"Failed runs: {failed_runs}")
    
    if not valid_runs:
        logger.error("No valid optimization results found - all runs failed")
        logger.error("Check individual run logs above for specific error details")
        return -1, valid_runs, failed_runs
    
    # Find best solution (minimum function value among valid runs)
    best_opt_idx = int(np.argmin(optim_funvalue_list))
    best_funvalue = optim_funvalue_list[best_opt_idx]
    best_run_number = best_opt_idx + 1
    
    logger.debug("BEST SOLUTION SELECTION:")
    logger.debug(f"  Best run: #{best_run_number}")
    logger.debug(f"  Best function value: {best_funvalue:.6f}")
    
    # Find improvement statistics
    if len(valid_runs) > 1:
        valid_func_values = [val for _, val in valid_runs]
        worst_value = max(valid_func_values)
        improvement = ((worst_value - best_funvalue) / abs(worst_value)) * 100 if worst_value != 0 else 0
        logger.debug(f"  Improvement over worst: {improvement:.2f}%")
        logger.debug(f"  Function value range: {min(valid_func_values):.6f} to {max(valid_func_values):.6f}")
    
    return best_opt_idx, valid_runs, failed_runs


def copy_best_solution(
    best_folder: str,
    base_output_folder: str,
    logger: Logger
) -> bool:
    """Copy the best solution to the base output folder.
    
    Args:
        best_folder: Path to the best solution folder
        base_output_folder: Path to the base output folder
        logger: Logger instance for output
        
    Returns:
        True if successful, False otherwise
    """
    logger.debug("FINALIZING RESULTS:")
    logger.debug(f"Copying best solution from: {best_folder}")
    logger.debug(f"Copying best solution to: {base_output_folder}")
    
    if not os.path.exists(best_folder):
        logger.error("✗ Best solution folder not found")
        return False
    
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
        
        logger.debug("✓ Best solution successfully copied to final output directory")
        return True
    except Exception as exc:
        logger.error(f"✗ Failed to copy best solution: {exc}")
        return False


def cleanup_temporary_directories(
    output_folder_list: list[str],
    n_multistart: int,
    logger: Logger
) -> bool:
    """Clean up temporary numbered subdirectories.
    
    Args:
        output_folder_list: List of temporary folder paths
        n_multistart: Number of optimization runs
        logger: Logger instance for output
        
    Returns:
        True if all cleanups successful, False if any failed
    """
    logger.debug("CLEANING UP TEMPORARY DIRECTORIES:")
    
    # Brief pause to ensure all file operations complete
    time.sleep(0.1)
    
    cleanup_success = True
    for i_opt in range(n_multistart):
        folder_to_remove = output_folder_list[i_opt]
        run_number = i_opt + 1
        
        # Try cleanup with one retry
        for attempt in range(2):
            try:
                if os.path.exists(folder_to_remove):
                    shutil.rmtree(folder_to_remove)
                logger.debug(f"✓ Removed temporary directory for run {run_number}")
                break
            except Exception as exc:
                if attempt == 0:  # First attempt failed, wait and retry
                    time.sleep(0.2)
                    continue
                else:  # Second attempt failed
                    logger.warning(f"✗ Failed to remove temporary directory for run {run_number}: {folder_to_remove} - {exc}")
                    cleanup_success = False
    
    if cleanup_success:
        logger.debug("✓ All temporary directories cleaned up successfully")
    else:
        logger.warning("⚠ Some temporary directories could not be removed (results still valid)")
    
    return cleanup_success


def create_multistart_summary_file(
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
        f.write(f"Electrode Shape: {args.electrode_shape}\n")
        f.write(f"Electrode Dimensions: {args.dimensions}mm\n")
        f.write(f"Electrode Thickness: {args.thickness}mm\n")
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


def create_single_optimization_summary_file(
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
        f.write(f"Electrode Shape: {args.electrode_shape}\n")
        f.write(f"Electrode Dimensions: {args.dimensions}mm\n")
        f.write(f"Electrode Thickness: {args.thickness}mm\n")
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

