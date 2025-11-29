#!/usr/bin/env simnibs_python
"""Main flex-search script for TI stimulation optimization.

This script orchestrates the flexible search optimization process for
temporal interference (TI) stimulation. It supports:
- Multiple ROI methods (spherical, atlas-based, subcortical)
- Multiple optimization goals (mean, max, focality)
- Multi-start optimization for robust results
- Optional electrode mapping to EEG cap positions
"""

from __future__ import annotations

import os
import sys
import time
import shutil

import numpy as np

# Add ti-toolbox directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))  # opt/flex/
opt_dir = os.path.dirname(script_dir)  # opt/
toolbox_dir = os.path.dirname(opt_dir)  # ti-toolbox/
if toolbox_dir not in sys.path:
    sys.path.insert(0, toolbox_dir)

# Local imports
from tools.logging_util import configure_external_loggers

# Import flex_search modules using relative imports
from . import flex_config, flex_log, multi_start


def main() -> int:
    """Main entry point for flex-search optimization.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Parse arguments
    args = flex_config.parse_arguments()
    
    # Track total session time
    start_time = time.time()
    
    # Multi-start optimization setup
    n_multistart = args.n_multistart
    optim_funvalue_list = np.zeros(n_multistart)
    
    # Build base optimization to get the output folder structure

    opt_base = flex_config.build_optimization(args)
    base_output_folder = opt_base.output_folder
    
    # Setup logger
    logger = flex_log.setup_logger(base_output_folder, args.subject)
    
    # Configure SimNIBS related loggers
    configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct', 'opt_struct'], logger)
    
    logger.debug(f"Base output directory: {base_output_folder}")
    logger.debug(f"Command: {' '.join(sys.argv)}")
    
    if n_multistart > 1:
        logger.debug(f"Running multi-start optimization with {n_multistart} runs")
    else:
        logger.debug("Running single optimization")

    # Create output folder list for each run
    output_folder_list = [
        os.path.join(base_output_folder, f"{i_opt:02d}") 
        for i_opt in range(n_multistart)
    ]
    
    # Log optimization start
    flex_log.log_optimization_start(
        args.subject, args.goal, args.postproc, 
        args.roi_method, n_multistart, logger
    )
    
    # Run multiple optimizations
    for i_opt in range(n_multistart):
        run_start_time = time.time()
        
        try:
            # Build optimization for this specific run
            opt = flex_config.build_optimization(args)
            opt.output_folder = output_folder_list[i_opt]
            os.makedirs(opt.output_folder, exist_ok=True)
            
            # Log optimization parameters (only for first run)
            if i_opt == 0:
                flex_log.log_optimization_config(args, n_multistart, logger)
            
            # Configure optimizer options
            flex_config.configure_optimizer_options(opt, args, logger)
            
            # Log run start
            cpus_to_pass = args.cpus if args.cpus is not None else None
            if n_multistart > 1:
                logger.debug(f"Starting optimization run {i_opt + 1}/{n_multistart}...")
            else:
                logger.debug("Starting optimization...")

            # Define step name for logging
            step_name = f"Optimization run {i_opt + 1}/{n_multistart}" if n_multistart > 1 else "Optimization"
            flex_log.log_optimization_step_start(step_name, logger)
            
            # Run optimization
            optimization_start_time = time.time()
            optim_funvalue_list[i_opt] = multi_start.run_single_optimization(
                opt, cpus_to_pass, logger
            )
            optimization_end_time = time.time()
            
            # Log results
            if optim_funvalue_list[i_opt] != float('inf'):
                optimization_duration = optimization_end_time - optimization_start_time
                run_duration = time.time() - run_start_time
                flex_log.log_run_details(
                    i_opt, n_multistart, opt.output_folder, opt,
                    optimization_duration, run_duration, logger
                )
                flex_log.log_optimization_step_complete(step_name, "", logger)
                
                # Log final electrode simulation if enabled
                run_final_sim = (
                    args.run_final_electrode_simulation and 
                    not args.skip_final_electrode_simulation
                )
                if run_final_sim:
                    flex_log.log_optimization_step_start("Final electrode simulation", logger)
                    flex_log.log_optimization_step_complete("Final electrode simulation", "", logger)
            else:
                # Optimization failed
                flex_log.log_optimization_step_failed(step_name, "See logs for details", logger)
                    
        except Exception as exc:
            # Unexpected error
            run_duration = time.time() - run_start_time
            logger.error(f"Unexpected error in run {i_opt + 1} after {run_duration:.1f} seconds: {exc}")
            optim_funvalue_list[i_opt] = float('inf')
            flex_log.log_optimization_step_failed(
                step_name, f"Unexpected error: {type(exc).__name__}", logger
            )
    
    # Post-processing
    if n_multistart > 1:
        logger.debug("=" * 80)
        logger.debug("MULTI-START OPTIMIZATION POST-PROCESSING")
        logger.debug("=" * 80)
        
        flex_log.log_optimization_step_start("Post-processing", logger)
        
        # Select best solution
        best_opt_idx, valid_runs, failed_runs = multi_start.select_best_solution(
            optim_funvalue_list, n_multistart, logger
        )
        
        if best_opt_idx == -1:
            flex_log.log_optimization_step_failed(
                "Post-processing", "No valid optimization results found", logger
            )
            flex_log.log_optimization_complete(
                args.subject, success=False, n_multistart=n_multistart, logger=logger
            )
            return 1
        
        best_run_number = best_opt_idx + 1
        best_folder = output_folder_list[best_opt_idx]
        
        # Copy best solution
        if not multi_start.copy_best_solution(best_folder, base_output_folder, logger):
            flex_log.log_optimization_step_failed(
                "Post-processing", "Failed to copy best solution", logger
            )
            flex_log.log_optimization_complete(
                args.subject, success=False, n_multistart=n_multistart, logger=logger
            )
            return 1
        
        # Create summary file
        multistart_summary_file = os.path.join(base_output_folder, "multistart_optimization_summary.txt")
        try:
            multi_start.create_multistart_summary_file(
                multistart_summary_file, args, n_multistart, 
                optim_funvalue_list, best_opt_idx, valid_runs, 
                failed_runs, start_time
            )
            logger.debug(f"Multi-start summary saved to: {multistart_summary_file}")
        except Exception as e:
            logger.warning(f"Failed to create multi-start summary file: {e}")
        
        # Clean up
        multi_start.cleanup_temporary_directories(
            output_folder_list, n_multistart, logger
        )
        
        logger.debug("MULTI-START OPTIMIZATION COMPLETED SUCCESSFULLY")
        logger.debug(f"Final results available in: {base_output_folder}")
        
        flex_log.log_optimization_step_complete(
            "Post-processing", 
            f"{len(valid_runs)}/{n_multistart} runs successful", 
            logger
        )
        
        flex_log.log_optimization_complete(
            args.subject, success=True, output_path=base_output_folder,
            n_multistart=n_multistart, best_run=best_run_number, logger=logger
        )
        
    else:
        # Single optimization run
        if optim_funvalue_list[0] == float('inf'):
            logger.error("Single optimization run failed")
            flex_log.log_optimization_complete(
                args.subject, success=False, logger=logger
            )
            return 1
        else:
            logger.debug("SINGLE OPTIMIZATION COMPLETED SUCCESSFULLY")
            logger.debug(f"Final function value: {optim_funvalue_list[0]:.6f}")
            
            single_run_folder = output_folder_list[0]
            
            logger.debug("FINALIZING RESULTS:")
            logger.debug(f"Moving results from: {single_run_folder}")
            logger.debug(f"Moving results to: {base_output_folder}")
            
            # Copy results
            if not multi_start.copy_best_solution(single_run_folder, base_output_folder, logger):
                flex_log.log_optimization_complete(
                    args.subject, success=False, logger=logger
                )
                return 1
            
            # Create summary file
            single_summary_file = os.path.join(base_output_folder, "optimization_summary.txt")
            try:
                multi_start.create_single_optimization_summary_file(
                    single_summary_file, args, optim_funvalue_list[0], start_time
                )
                logger.debug(f"Optimization summary saved to: {single_summary_file}")
            except Exception as e:
                logger.warning(f"Failed to create optimization summary file: {e}")
            
            # Clean up
            time.sleep(0.1)
            logger.debug("CLEANING UP TEMPORARY DIRECTORY:")
            
            for attempt in range(2):
                try:
                    if os.path.exists(single_run_folder):
                        shutil.rmtree(single_run_folder)
                    logger.debug("✓ Removed temporary directory")
                    break
                except Exception as exc:
                    if attempt == 0:
                        time.sleep(0.2)
                        continue
                    else:
                        logger.warning(f"✗ Failed to remove temporary directory: {single_run_folder} - {exc}")
                        logger.warning("⚠ Temporary directory could not be removed (results still valid)")
            
            logger.debug(f"Results available in: {base_output_folder}")
            
            flex_log.log_optimization_complete(
                args.subject, success=True, output_path=base_output_folder,
                n_multistart=n_multistart, logger=logger
            )
    
    # Log session footer
    total_duration = time.time() - start_time
    flex_log.log_session_footer(args.subject, n_multistart, total_duration, logger)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
