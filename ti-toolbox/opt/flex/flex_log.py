#!/usr/bin/env simnibs_python
"""Logging utilities for flex-search optimization.

This module provides structured logging for the optimization process:
- Progress tracking with tree-style output
- Step timing and duration tracking
- Configuration logging
- Session management
"""

from __future__ import annotations

import os
import sys
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from logging import Logger

# Add parent directory to path for tools imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


# -----------------------------------------------------------------------------
# Progress tracking
# -----------------------------------------------------------------------------

# Global variables for progress tracking
OPTIMIZATION_START_TIME: Optional[float] = None
STEP_START_TIMES: dict[str, float] = {}


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string (e.g., "5s", "2m 30s", "1h 15m")
    """
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.0f}m {seconds % 60:.0f}s"
    else:
        hours = seconds / 3600
        minutes = (seconds % 3600) / 60
        return f"{hours:.0f}h {minutes:.0f}m"


def setup_logger(output_folder: str, subject_id: str) -> Logger:
    """Initialize logger with console and file output.
    
    Args:
        output_folder: Path to the directory where logs should be stored
        subject_id: Subject identifier for naming the log file
        
    Returns:
        Configured logger instance
        
    Raises:
        SystemExit: If PROJECT_DIR environment variable is not set
    """
    from tools.logging_util import get_logger
    
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
        print(f"Warning: Could not set permissions for logs directory: {e}")
    
    # Create timestamped log file
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(logs_dir, f'flex_search_{subject_id}_{time_stamp}.log')
    logger = get_logger('flex-search', log_file, overwrite=True)
    
    # Log session header
    logger.debug("=" * 80)
    logger.debug("FLEX-SEARCH OPTIMIZATION SESSION STARTED")
    logger.debug(f"Subject: {subject_id}")
    logger.debug(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.debug(f"Output folder: {output_folder}")
    logger.debug("=" * 80)
    
    return logger


def log_optimization_start(
    subject_id: str,
    goal: str,
    postproc: str,
    roi_method: str,
    n_multistart: int,
    logger: Logger
) -> None:
    """Log the start of optimization for a subject.
    
    Args:
        subject_id: Subject identifier
        goal: Optimization goal (mean, max, focality)
        postproc: Post-processing method
        roi_method: ROI method (spherical, atlas, subcortical)
        n_multistart: Number of multi-start runs
        logger: Logger instance
    """
    global OPTIMIZATION_START_TIME
    OPTIMIZATION_START_TIME = time.time()
    
    logger.info(f"Beginning flex-search optimization for subject: {subject_id} ({goal}, {postproc}, {roi_method})")
    if n_multistart > 1:
        logger.info(f"├─ Multi-start optimization: {n_multistart} runs")
    else:
        logger.info("├─ Single optimization run")


def log_optimization_step_start(step_name: str, logger: Logger) -> None:
    """Log the start of an optimization step.
    
    Args:
        step_name: Name of the optimization step
        logger: Logger instance
    """
    global STEP_START_TIMES
    STEP_START_TIMES[step_name] = time.time()
    logger.info(f"├─ {step_name}: Started")


def log_optimization_step_complete(
    step_name: str,
    additional_info: str = "",
    logger: Optional[Logger] = None
) -> None:
    """Log the completion of an optimization step.
    
    Args:
        step_name: Name of the optimization step
        additional_info: Additional information to include in log
        logger: Logger instance
    """
    global STEP_START_TIMES
    
    if step_name in STEP_START_TIMES:
        duration = time.time() - STEP_START_TIMES[step_name]
        duration_str = format_duration(duration)
        
        if logger:
            if additional_info:
                logger.info(f"├─ {step_name}: ✓ Complete ({duration_str}) - {additional_info}")
            else:
                logger.info(f"├─ {step_name}: ✓ Complete ({duration_str})")
        
        # Clean up timing
        del STEP_START_TIMES[step_name]
    else:
        if logger:
            if additional_info:
                logger.info(f"├─ {step_name}: ✓ Complete - {additional_info}")
            else:
                logger.info(f"├─ {step_name}: ✓ Complete")


def log_optimization_step_failed(
    step_name: str,
    error_msg: str = "",
    logger: Optional[Logger] = None
) -> None:
    """Log the failure of an optimization step.
    
    Args:
        step_name: Name of the optimization step
        error_msg: Error message to include in log
        logger: Logger instance
    """
    global STEP_START_TIMES
    
    if step_name in STEP_START_TIMES:
        duration = time.time() - STEP_START_TIMES[step_name]
        duration_str = format_duration(duration)
        
        if logger:
            if error_msg:
                logger.error(f"├─ {step_name}: ✗ Failed ({duration_str}) - {error_msg}")
            else:
                logger.error(f"├─ {step_name}: ✗ Failed ({duration_str})")
        
        # Clean up timing
        del STEP_START_TIMES[step_name]
    else:
        if logger:
            if error_msg:
                logger.error(f"├─ {step_name}: ✗ Failed - {error_msg}")
            else:
                logger.error(f"├─ {step_name}: ✗ Failed")


def log_optimization_complete(
    subject_id: str,
    success: bool,
    output_path: str = "",
    n_multistart: int = 1,
    best_run: Optional[int] = None,
    logger: Optional[Logger] = None
) -> None:
    """Log the completion of optimization for a subject.
    
    Args:
        subject_id: Subject identifier
        success: Whether optimization was successful
        output_path: Path to output results
        n_multistart: Number of multi-start runs
        best_run: Best run number (if multi-start)
        logger: Logger instance
    """
    global OPTIMIZATION_START_TIME
    
    if not logger:
        return
    
    if OPTIMIZATION_START_TIME:
        total_duration = time.time() - OPTIMIZATION_START_TIME
        duration_str = format_duration(total_duration)
        
        if success:
            if n_multistart > 1 and best_run:
                logger.info(f"└─ Flex-search optimization completed successfully for subject: {subject_id} (best run: {best_run}, Total: {duration_str})")
            else:
                logger.info(f"└─ Flex-search optimization completed successfully for subject: {subject_id} (Total: {duration_str})")
            if output_path:
                logger.info(f"   Results saved to: {output_path}")
        else:
            logger.error(f"└─ Flex-search optimization failed for subject: {subject_id} (Total: {duration_str})")
        
        # Reset timing
        OPTIMIZATION_START_TIME = None
    else:
        if success:
            logger.info(f"└─ Flex-search optimization completed successfully for subject: {subject_id}")
        else:
            logger.error(f"└─ Flex-search optimization failed for subject: {subject_id}")


def log_session_footer(
    subject_id: str,
    n_multistart: int,
    total_duration: float,
    logger: Logger
) -> None:
    """Log session footer with summary information.
    
    Args:
        subject_id: Subject identifier
        n_multistart: Number of multi-start runs
        total_duration: Total session duration in seconds
        logger: Logger instance
    """
    logger.debug("=" * 80)
    logger.debug("FLEX-SEARCH SESSION COMPLETED")
    logger.debug(f"Total session duration: {total_duration:.1f} seconds")
    logger.debug(f"Subject: {subject_id}")
    logger.debug(f"Optimization runs: {n_multistart}")
    logger.debug("=" * 80)


def log_optimization_config(
    args,
    n_multistart: int,
    logger: Logger
) -> None:
    """Log detailed optimization configuration (first run only).
    
    Args:
        args: Parsed command line arguments
        n_multistart: Number of multi-start runs
        logger: Logger instance
    """
    run_final_sim = args.run_final_electrode_simulation and not args.skip_final_electrode_simulation
    
    logger.debug("OPTIMIZATION CONFIGURATION:")
    logger.debug(f"  Subject: {args.subject}")
    logger.debug(f"  Goal: {args.goal}")
    logger.debug(f"  Post-processing: {args.postproc}")
    logger.debug(f"  ROI Method: {args.roi_method}")
    logger.debug(f"  EEG Net: {args.eeg_net}")
    logger.debug(f"  Electrode Shape: {args.electrode_shape}")
    logger.debug(f"  Electrode Dimensions: {args.dimensions}mm")
    logger.debug(f"  Electrode Thickness: {args.thickness}mm")
    logger.debug(f"  Electrode Current: {args.current}mA")
    logger.debug(f"  Run Final Electrode Simulation: {run_final_sim}")
    
    # Log ROI-specific details
    if args.roi_method == "subcortical":
        volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH")
        volume_roi_label = os.getenv("VOLUME_ROI_LABEL")
        logger.debug(f"  Volume Atlas: {volume_atlas_path}")
        logger.debug(f"  Volume ROI Label: {volume_roi_label}")
    elif args.roi_method == "atlas":
        atlas_path = os.getenv("ATLAS_PATH")
        roi_label = os.getenv("ROI_LABEL")
        hemisphere = os.getenv("SELECTED_HEMISPHERE")
        logger.debug(f"  Surface Atlas: {os.path.basename(atlas_path) if atlas_path else 'N/A'}")
        logger.debug(f"  ROI Label: {roi_label}")
        logger.debug(f"  Hemisphere: {hemisphere}")
    elif args.roi_method == "spherical":
        roi_coords = f"({os.getenv('ROI_X')}, {os.getenv('ROI_Y')}, {os.getenv('ROI_Z')})"
        roi_radius = os.getenv("ROI_RADIUS")
        use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
        coord_space = "MNI" if use_mni_coords else "subject"
        logger.debug(f"  ROI Center ({coord_space} space): {roi_coords}")
        logger.debug(f"  ROI Radius: {roi_radius}mm")
        if use_mni_coords:
            logger.debug("  Note: MNI coordinates will be transformed to subject space")
    
    # Log focality-specific parameters
    if args.goal == "focality":
        logger.debug(f"  Non-ROI Method: {args.non_roi_method}")
        logger.debug(f"  Threshold Values: {args.thresholds}")
    
    logger.debug(f"  Electrode Mapping: {args.enable_mapping}")
    if args.enable_mapping:
        logger.debug(f"  Run Mapped Simulation: {not args.disable_mapping_simulation}")
        
    # Log optimization algorithm parameters
    logger.debug("OPTIMIZATION ALGORITHM SETTINGS:")
    logger.debug(f"  Max Iterations: {args.max_iterations if args.max_iterations is not None else 'Default'}")
    logger.debug(f"  Population Size: {args.population_size if args.population_size is not None else 'Default'}")
    logger.debug(f"  CPU Cores: {args.cpus if args.cpus is not None else 'Default'}")
    
    if n_multistart > 1:
        logger.debug(f"  Multi-start Runs: {n_multistart}")
        logger.debug("  Note: Best result will be automatically selected based on function value")


def log_run_details(
    i_opt: int,
    n_multistart: int,
    output_folder: str,
    opt,
    optimization_duration: float,
    run_duration: float,
    logger: Logger
) -> None:
    """Log details for an optimization run.
    
    Args:
        i_opt: Run index (0-based)
        n_multistart: Total number of runs
        output_folder: Output folder for this run
        opt: SimNIBS optimization object with results
        optimization_duration: Duration of optimization phase
        run_duration: Total run duration
        logger: Logger instance
    """
    # Log run start
    logger.debug("-" * 60)
    if n_multistart > 1:
        logger.debug(f"OPTIMIZATION RUN {i_opt + 1}/{n_multistart}")
        logger.debug(f"Run output folder: {output_folder}")
    else:
        logger.debug("SINGLE OPTIMIZATION RUN")
    logger.debug("-" * 60)
    
    # Log run completion (if opt is complete)
    if hasattr(opt, 'optim_funvalue'):
        logger.debug("OPTIMIZATION RUN COMPLETED:")
        logger.debug(f"  Function Value: {opt.optim_funvalue:.6f}")
        logger.debug(f"  Optimization Duration: {optimization_duration:.1f} seconds")
        logger.debug(f"  Total Run Duration: {run_duration:.1f} seconds")
        if hasattr(opt, 'optim_result') and hasattr(opt.optim_result, 'nfev'):
            logger.debug(f"  Function Evaluations: {opt.optim_result.nfev}")
        if hasattr(opt, 'optim_result') and hasattr(opt.optim_result, 'success'):
            logger.debug(f"  Optimization Success: {opt.optim_result.success}")

