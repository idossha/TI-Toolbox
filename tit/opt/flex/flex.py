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

import numpy as np

import os
import shutil
import sys
import time
from pathlib import Path

from tit.logger import configure_external_loggers

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
    configure_external_loggers(
        ["simnibs", "mesh_io", "sim_struct", "opt_struct"], logger
    )

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
        args.subject, args.goal, args.postproc, args.roi_method, n_multistart, logger
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
            step_name = (
                f"Optimization run {i_opt + 1}/{n_multistart}"
                if n_multistart > 1
                else "Optimization"
            )
            flex_log.log_optimization_step_start(step_name, logger)

            # Run optimization
            optimization_start_time = time.time()
            optim_funvalue_list[i_opt] = multi_start.run_single_optimization(
                opt, cpus_to_pass, logger
            )
            optimization_end_time = time.time()

            # Log results
            if optim_funvalue_list[i_opt] != float("inf"):
                optimization_duration = optimization_end_time - optimization_start_time
                run_duration = time.time() - run_start_time
                flex_log.log_run_details(
                    i_opt,
                    n_multistart,
                    opt.output_folder,
                    opt,
                    optimization_duration,
                    run_duration,
                    logger,
                )
                flex_log.log_optimization_step_complete(step_name, "", logger)

                # Log final electrode simulation if enabled
                run_final_sim = (
                    args.run_final_electrode_simulation
                    and not args.skip_final_electrode_simulation
                )
                if run_final_sim:
                    flex_log.log_optimization_step_start(
                        "Final electrode simulation", logger
                    )
                    flex_log.log_optimization_step_complete(
                        "Final electrode simulation", "", logger
                    )
            else:
                # Optimization failed
                flex_log.log_optimization_step_failed(
                    step_name, "See logs for details", logger
                )

        except Exception as exc:
            # Unexpected error
            run_duration = time.time() - run_start_time
            logger.error(
                f"Unexpected error in run {i_opt + 1} after {run_duration:.1f} seconds: {exc}"
            )
            optim_funvalue_list[i_opt] = float("inf")
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
        multistart_summary_file = os.path.join(
            base_output_folder, "multistart_optimization_summary.txt"
        )
        try:
            multi_start.create_multistart_summary_file(
                multistart_summary_file,
                args,
                n_multistart,
                optim_funvalue_list,
                best_opt_idx,
                valid_runs,
                failed_runs,
                start_time,
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
            logger,
        )

        flex_log.log_optimization_complete(
            args.subject,
            success=True,
            output_path=base_output_folder,
            n_multistart=n_multistart,
            best_run=best_run_number,
            logger=logger,
        )

    else:
        # Single optimization run
        if optim_funvalue_list[0] == float("inf"):
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
            if not multi_start.copy_best_solution(
                single_run_folder, base_output_folder, logger
            ):
                flex_log.log_optimization_complete(
                    args.subject, success=False, logger=logger
                )
                return 1

            # Create summary file
            single_summary_file = os.path.join(
                base_output_folder, "optimization_summary.txt"
            )
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
                        logger.warning(
                            f"✗ Failed to remove temporary directory: {single_run_folder} - {exc}"
                        )
                        logger.warning(
                            "⚠ Temporary directory could not be removed (results still valid)"
                        )

            logger.debug(f"Results available in: {base_output_folder}")

            flex_log.log_optimization_complete(
                args.subject,
                success=True,
                output_path=base_output_folder,
                n_multistart=n_multistart,
                logger=logger,
            )

    # Log session footer
    total_duration = time.time() - start_time
    flex_log.log_session_footer(args.subject, n_multistart, total_duration, logger)

    # Generate HTML report
    try:
        from tit.core import constants as const
        from tit.core import get_path_manager
        from tit.reporting import FlexSearchReportGenerator

        def _resolve_project_dir(output_folder: str) -> str:
            pm = get_path_manager()
            project_dir = pm.project_dir if pm else None
            if not project_dir:
                project_dir = os.environ.get(const.ENV_PROJECT_DIR)
            if project_dir:
                return project_dir

            output_path = Path(output_folder).resolve()
            for parent in [output_path] + list(output_path.parents):
                if parent.name == const.DIR_DERIVATIVES:
                    return str(parent.parent)
            return str(output_path.parent)

        def _format_postproc(value: str) -> str:
            postproc_map = {
                "max_TI": "TImax",
                "dir_TI_normal": "normal",
                "dir_TI_tangential": "tangential",
            }
            return postproc_map.get(value, value)

        def _atlas_name_from_path(path_value: str, hemisphere: str) -> str:
            if not path_value:
                return ""
            atlas_filename = os.path.basename(path_value)
            atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(
                ".annot", ""
            )
            if "_" in atlas_with_subject:
                return atlas_with_subject.split("_", 1)[-1]
            return atlas_with_subject

        project_dir = _resolve_project_dir(base_output_folder)

        report_gen = FlexSearchReportGenerator(
            project_dir=project_dir,
            subject_id=args.subject,
        )

        # Set configuration
        report_gen.set_configuration(
            electrode_net=getattr(args, "eeg_net", None),
            optimization_goal=args.goal,
            post_processing=_format_postproc(args.postproc),
            n_candidates=n_multistart,
            n_starts=n_multistart,
            selection_method="best" if n_multistart > 1 else "single",
            electrode_shape=args.electrode_shape,
            electrode_dimensions_mm=args.dimensions,
            electrode_thickness_mm=args.thickness,
            electrode_current_mA=args.current,
            mapping_enabled=bool(getattr(args, "enable_mapping", False)),
            disable_mapping_simulation=bool(
                getattr(args, "disable_mapping_simulation", False)
            ),
            run_final_electrode_simulation=args.run_final_electrode_simulation,
            max_iterations=args.max_iterations,
            population_size=args.population_size,
            tolerance=args.tolerance,
            mutation=args.mutation,
            recombination=args.recombination,
            thresholds=args.thresholds,
            non_roi_method=args.non_roi_method,
            cpu_cores=args.cpus,
            detailed_results=args.detailed_results,
            visualize_valid_skin_region=args.visualize_valid_skin_region,
            skin_visualization_net=args.skin_visualization_net,
        )

        # Set ROI info
        roi_method = args.roi_method
        roi_name = os.getenv("ROI_NAME") or "Target ROI"
        roi_data = {
            "roi_name": roi_name,
            "roi_type": roi_method,
        }
        if args.goal == "focality" and args.non_roi_method:
            roi_data["non_roi_method"] = args.non_roi_method
        if roi_method == "spherical":
            roi_x = float(os.getenv("ROI_X", "0"))
            roi_y = float(os.getenv("ROI_Y", "0"))
            roi_z = float(os.getenv("ROI_Z", "0"))
            roi_radius = float(os.getenv("ROI_RADIUS", "10"))
            use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"

            roi_data.update(
                {
                    "coordinates": [roi_x, roi_y, roi_z],
                    "radius": roi_radius,
                    "coordinate_space": "MNI" if use_mni_coords else "subject",
                }
            )

            if args.goal == "focality" and args.non_roi_method == "specific":
                non_roi_coords = [
                    float(os.getenv("NON_ROI_X", "0")),
                    float(os.getenv("NON_ROI_Y", "0")),
                    float(os.getenv("NON_ROI_Z", "0")),
                ]
                non_roi_radius = float(os.getenv("NON_ROI_RADIUS", "10"))
                use_mni_coords_non_roi = (
                    os.getenv("USE_MNI_COORDS_NON_ROI", "false").lower() == "true"
                )
                roi_data.update(
                    {
                        "non_roi_method": args.non_roi_method,
                        "non_roi_coordinates": non_roi_coords,
                        "non_roi_radius": non_roi_radius,
                        "non_roi_coordinate_space": (
                            "MNI" if use_mni_coords_non_roi else "subject"
                        ),
                    }
                )
        elif roi_method == "atlas":
            hemisphere = os.getenv("SELECTED_HEMISPHERE", "lh")
            atlas_path = os.getenv("ATLAS_PATH", "")
            atlas_label = os.getenv("ROI_LABEL")
            roi_data.update(
                {
                    "hemisphere": hemisphere,
                    "atlas": _atlas_name_from_path(atlas_path, hemisphere)
                    or atlas_path,
                    "atlas_label": (
                        int(atlas_label) if atlas_label is not None else None
                    ),
                }
            )
            if args.goal == "focality" and args.non_roi_method == "specific":
                non_roi_label = os.getenv("NON_ROI_LABEL")
                non_roi_atlas_path = os.getenv("NON_ROI_ATLAS_PATH", "")
                roi_data.update(
                    {
                        "non_roi_atlas": (
                            os.path.basename(non_roi_atlas_path)
                            if non_roi_atlas_path
                            else None
                        ),
                        "non_roi_label": (
                            int(non_roi_label) if non_roi_label is not None else None
                        ),
                    }
                )
        else:  # subcortical
            volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
            volume_label = os.getenv("VOLUME_ROI_LABEL")
            roi_data.update(
                {
                    "volume_atlas": (
                        os.path.basename(volume_atlas_path)
                        if volume_atlas_path
                        else None
                    ),
                    "volume_label": (
                        int(volume_label) if volume_label is not None else None
                    ),
                }
            )
            if args.goal == "focality" and args.non_roi_method == "specific":
                non_roi_atlas_path = os.getenv("VOLUME_NON_ROI_ATLAS_PATH", "")
                non_roi_label = os.getenv("VOLUME_NON_ROI_LABEL")
                roi_data.update(
                    {
                        "non_roi_atlas": (
                            os.path.basename(non_roi_atlas_path)
                            if non_roi_atlas_path
                            else None
                        ),
                        "non_roi_label": (
                            int(non_roi_label) if non_roi_label is not None else None
                        ),
                    }
                )

        report_gen.set_roi_info(**roi_data)

        # Add search results
        for i, score in enumerate(optim_funvalue_list):
            if score != float("inf"):
                report_gen.add_search_result(
                    rank=i + 1,
                    electrode_1a="",  # Would need to parse from output
                    electrode_1b="",
                    electrode_2a="",
                    electrode_2b="",
                    score=float(score),
                )

        # Set best solution if available
        electrode_positions_path = Path(base_output_folder) / "electrode_positions.json"
        electrode_positions = None
        channel_array_indices = None
        if electrode_positions_path.exists():
            try:
                import json

                with open(electrode_positions_path) as f:
                    pos_data = json.load(f)
                electrode_positions = pos_data.get("optimized_positions")
                channel_array_indices = pos_data.get("channel_array_indices")
            except Exception as exc:
                logger.warning(f"Failed to parse electrode_positions.json: {exc}")

        if n_multistart > 1 and best_opt_idx != -1:
            report_gen.set_best_solution(
                electrode_pairs=[],  # Would need to parse from output
                score=float(optim_funvalue_list[best_opt_idx]),
                metrics={"run": best_opt_idx + 1},
                electrode_coordinates=electrode_positions,
                channel_array_indices=channel_array_indices,
            )
        elif n_multistart == 1 and optim_funvalue_list[0] != float("inf"):
            report_gen.set_best_solution(
                electrode_pairs=[],
                score=float(optim_funvalue_list[0]),
                metrics={},
                electrode_coordinates=electrode_positions,
                channel_array_indices=channel_array_indices,
            )

        report_path = report_gen.generate()
        logger.info(f"Report generated: {report_path}")

    except Exception as e:
        logger.warning(f"Could not generate HTML report: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
