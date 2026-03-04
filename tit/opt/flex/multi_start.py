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
import shutil
import time
import traceback
from logging import Logger
from typing import Optional

import numpy as np

from tit.opt.config import (
    AtlasROI,
    FlexConfig,
    SphericalROI,
    SubcorticalROI,
)

# ---------------------------------------------------------------------------
# ROI description helper
# ---------------------------------------------------------------------------


def describe_roi(roi) -> dict:
    """Return a flat dictionary describing an ROI specification.

    Works with the unified ``ROISpec`` types (``SphericalROI``,
    ``AtlasROI``, ``SubcorticalROI``).  The returned dict always
    contains a ``"method"`` key (``"spherical"``, ``"atlas"``, or
    ``"subcortical"``).

    Args:
        roi: An ``ROISpec`` instance (``SphericalROI``, ``AtlasROI``,
            or ``SubcorticalROI``).

    Returns:
        Dictionary with method-specific description keys.

    Raises:
        ValueError: If ``roi`` is not a recognised ROI type.
    """
    if isinstance(roi, SphericalROI):
        coord_space = "MNI" if roi.use_mni else "subject"
        return {
            "method": "spherical",
            "coord_space": coord_space,
            "center": (roi.x, roi.y, roi.z),
            "radius": roi.radius,
            "use_mni": roi.use_mni,
        }
    elif isinstance(roi, AtlasROI):
        atlas_basename = os.path.basename(roi.atlas_path) if roi.atlas_path else "N/A"
        return {
            "method": "atlas",
            "atlas_basename": atlas_basename,
            "atlas_path": roi.atlas_path or "N/A",
            "label": roi.label,
            "hemisphere": roi.hemisphere,
        }
    elif isinstance(roi, SubcorticalROI):
        atlas_basename = os.path.basename(roi.atlas_path) if roi.atlas_path else "N/A"
        return {
            "method": "subcortical",
            "atlas_basename": atlas_basename,
            "atlas_path": roi.atlas_path or "N/A",
            "label": roi.label,
        }
    else:
        raise ValueError(f"Unknown ROI type: {type(roi)}")


# ---------------------------------------------------------------------------
# Core multi-start helpers (unchanged)
# ---------------------------------------------------------------------------


def run_single_optimization(opt, cpus: Optional[int], logger: Logger) -> float:
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
        logger.info(
            "This error may occur during final analysis but optimization itself likely completed"
        )
        return float("inf")
    except ValueError as exc:
        exc_str = str(exc)
        if "zero-size array" in exc_str:
            logger.error("ERROR in optimization:")
            logger.error("  Error type: ValueError (Empty ROI)")
            logger.error(
                "  The ROI contains no mesh points. This usually means the "
                "ROI sphere/volume does not intersect with the brain mesh. "
                "Please check: (1) ROI coordinates are inside the brain, "
                "(2) coordinate space is correct (subject vs MNI), "
                "(3) ROI radius is large enough."
            )
            logger.error(f"  Original SimNIBS error: {exc_str}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
        else:
            logger.error("ERROR in optimization:")
            logger.error(f"  Error type: {type(exc).__name__}")
            logger.error(f"  Error message: {exc_str}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return float("inf")
    except Exception as exc:
        logger.error("ERROR in optimization:")
        logger.error(f"  Error type: {type(exc).__name__}")
        logger.error(f"  Error message: {str(exc)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return float("inf")


def select_best_solution(
    optim_funvalue_list: np.ndarray, n_multistart: int, logger: Logger
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
        if func_val == float("inf"):
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
        improvement = (
            ((worst_value - best_funvalue) / abs(worst_value)) * 100
            if worst_value != 0
            else 0
        )
        logger.debug(f"  Improvement over worst: {improvement:.2f}%")
        logger.debug(
            f"  Function value range: {min(valid_func_values):.6f} to {max(valid_func_values):.6f}"
        )

    return best_opt_idx, valid_runs, failed_runs


def copy_best_solution(
    best_folder: str, base_output_folder: str, logger: Logger
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
        logger.error("Best solution folder not found")
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

        logger.debug("Best solution successfully copied to final output directory")
        return True
    except Exception as exc:
        logger.error(f"Failed to copy best solution: {exc}")
        return False


def cleanup_temporary_directories(
    output_folder_list: list[str], n_multistart: int, logger: Logger
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
                logger.debug(f"Removed temporary directory for run {run_number}")
                break
            except Exception as exc:
                if attempt == 0:  # First attempt failed, wait and retry
                    time.sleep(0.2)
                    continue
                else:  # Second attempt failed
                    logger.warning(
                        f"Failed to remove temporary directory for run {run_number}: {folder_to_remove} - {exc}"
                    )
                    cleanup_success = False

    if cleanup_success:
        logger.debug("All temporary directories cleaned up successfully")
    else:
        logger.warning(
            "Some temporary directories could not be removed (results still valid)"
        )

    return cleanup_success


# ---------------------------------------------------------------------------
# Summary file generation
# ---------------------------------------------------------------------------


def _format_config_section(config: FlexConfig) -> str:
    """Format the shared configuration section for summary files.

    Covers optimization parameters, electrode settings, ROI/non-ROI
    descriptions, and mapping configuration.

    Args:
        config: FlexConfig instance.

    Returns:
        Multi-line string with the formatted configuration section.
    """
    lines: list[str] = []

    # Optimization configuration
    lines.append("OPTIMIZATION CONFIGURATION:")
    lines.append("-" * 40)

    roi_info = describe_roi(config.roi)
    lines.append(f"Goal: {config.goal}")
    lines.append(f"Post-processing: {config.postproc}")
    lines.append(f"ROI Method: {roi_info['method']}")
    lines.append(f"EEG Net: {config.eeg_net}")
    lines.append(f"Electrode Shape: {config.electrode.shape}")
    lines.append(f"Electrode Dimensions: {config.electrode.dimensions}mm")
    lines.append(f"Electrode Thickness: {config.electrode.thickness}mm")
    lines.append(f"Electrode Current: {config.current_mA}mA")
    lines.append(
        f"Run Final Electrode Simulation: {config.run_final_electrode_simulation}"
    )
    lines.append("")

    # ROI details
    lines.append("ROI CONFIGURATION:")
    lines.append("-" * 40)

    if roi_info["method"] == "spherical":
        coord_space = roi_info["coord_space"]
        cx, cy, cz = roi_info["center"]
        lines.append(f"ROI Center ({coord_space} space): ({cx}, {cy}, {cz})")
        lines.append(f"ROI Radius: {roi_info['radius']}mm")
        if roi_info["use_mni"]:
            lines.append("Note: MNI coordinates transformed to subject space")
    elif roi_info["method"] == "atlas":
        lines.append(f"Surface Atlas File: {roi_info['atlas_basename']}")
        lines.append(f"Surface Atlas Path: {roi_info['atlas_path']}")
        lines.append(f"ROI Label: {roi_info['label']}")
        lines.append(f"Hemisphere: {roi_info['hemisphere']}")
    elif roi_info["method"] == "subcortical":
        lines.append(f"Volume Atlas File: {roi_info['atlas_basename']}")
        lines.append(f"Volume Atlas Path: {roi_info['atlas_path']}")
        lines.append(f"Volume ROI Label: {roi_info['label']}")

    # Focality-specific non-ROI parameters
    if config.goal == "focality":
        lines.append("")
        lines.append("NON-ROI CONFIGURATION (Focality):")
        lines.append("-" * 40)
        lines.append(f"Non-ROI Method: {config.non_roi_method}")
        lines.append(f"Threshold Values: {config.thresholds}")

        if config.non_roi_method == "everything_else":
            lines.append("Non-ROI: Everything else (complement of ROI)")
        elif config.non_roi is not None:
            nr_info = describe_roi(config.non_roi)
            if nr_info["method"] == "spherical":
                cx, cy, cz = nr_info["center"]
                lines.append(f"Non-ROI Center: ({cx}, {cy}, {cz})")
                lines.append(f"Non-ROI Radius: {nr_info['radius']}mm")
            elif nr_info["method"] == "atlas":
                lines.append(f"Non-ROI Atlas File: {nr_info['atlas_basename']}")
                lines.append(f"Non-ROI Atlas Path: {nr_info['atlas_path']}")
                lines.append(f"Non-ROI Label: {nr_info['label']}")
            elif nr_info["method"] == "subcortical":
                lines.append(f"Non-ROI Volume Atlas File: {nr_info['atlas_basename']}")
                lines.append(f"Non-ROI Volume Atlas Path: {nr_info['atlas_path']}")
                lines.append(f"Non-ROI Volume Label: {nr_info['label']}")

    lines.append("")
    lines.append(f"Electrode Mapping: {config.enable_mapping}")
    if config.enable_mapping:
        lines.append(f"Run Mapped Simulation: {not config.disable_mapping_simulation}")

    return "\n".join(lines)


def create_summary_file(
    summary_file: str,
    config: FlexConfig,
    start_time: float,
    *,
    is_multistart: bool = False,
    n_multistart: int = 1,
    optim_funvalue_list: Optional[np.ndarray] = None,
    best_opt_idx: int = 0,
    valid_runs: Optional[list] = None,
    failed_runs: Optional[list] = None,
    function_value: Optional[float] = None,
) -> None:
    """Create a detailed summary file for optimization results.

    This unified function handles both single-run and multi-start
    summaries.  For a single run, pass ``is_multistart=False`` and
    supply ``function_value``.  For multi-start, pass
    ``is_multistart=True`` with the run-level arrays.

    Args:
        summary_file: Path to the summary file to create.
        config: FlexConfig instance.
        start_time: Session start time (``time.time()`` epoch).
        is_multistart: Whether this is a multi-start summary.
        n_multistart: Number of optimization runs (multi-start only).
        optim_funvalue_list: Array of function values per run
            (multi-start only).
        best_opt_idx: Index of the best optimisation run
            (multi-start only).
        valid_runs: List of ``(run_number, function_value)`` tuples
            (multi-start only).
        failed_runs: List of failed run numbers (multi-start only).
        function_value: Final function value (single-run only).
    """
    total_duration = time.time() - start_time
    title = (
        "MULTI-START OPTIMIZATION SUMMARY" if is_multistart else "OPTIMIZATION SUMMARY"
    )
    duration_label = (
        "Total session duration" if is_multistart else "Total optimization duration"
    )

    with open(summary_file, "w") as f:
        f.write("=" * 80 + "\n")
        f.write(f"{title}\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Subject: {config.subject_id}\n")
        f.write(f"Project: {config.project_dir}\n")
        f.write(f"{duration_label}: {total_duration:.1f} seconds\n")
        f.write("\n")

        # Shared configuration section
        f.write(_format_config_section(config))
        f.write("\n")

        # Algorithm parameters
        f.write("\nALGORITHM PARAMETERS:\n")
        f.write("-" * 40 + "\n")
        if is_multistart:
            f.write(f"Number of Runs (Multi-start): {n_multistart}\n")
        f.write(
            f"Max Iterations: {config.max_iterations if config.max_iterations is not None else 'Default'}\n"
        )
        f.write(
            f"Population Size: {config.population_size if config.population_size is not None else 'Default'}\n"
        )
        f.write(f"CPU Cores: {config.cpus if config.cpus is not None else 'Default'}\n")
        f.write("\n")

        if is_multistart:
            _write_multistart_results(
                f,
                n_multistart,
                optim_funvalue_list,
                best_opt_idx,
                valid_runs or [],
                failed_runs or [],
                summary_file,
            )
        else:
            # Single-run result
            fv = function_value if function_value is not None else 0.0
            f.write("OPTIMIZATION RESULT:\n")
            f.write("-" * 20 + "\n")
            f.write(f"Final function value: {fv:.6f}\n")
            f.write("Optimization type: Single run (no multi-start)\n")
            f.write("\n")

        f.write("For detailed optimization logs, refer to the main log file.\n")
        f.write(
            "For visualization and analysis, use the generated field maps and summary files.\n"
        )
        f.write("=" * 80 + "\n")


def _write_multistart_results(
    f,
    n_multistart: int,
    optim_funvalue_list: np.ndarray,
    best_opt_idx: int,
    valid_runs: list,
    failed_runs: list,
    summary_file: str,
) -> None:
    """Write the multi-start specific results section.

    Args:
        f: Open file handle.
        n_multistart: Number of runs.
        optim_funvalue_list: Array of function values.
        best_opt_idx: Index of the best run.
        valid_runs: Valid run tuples.
        failed_runs: Failed run numbers.
        summary_file: Path to the summary file (for folder name).
    """
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
        if func_val == float("inf"):
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
        improvement = (
            ((worst_value - best_value) / abs(worst_value)) * 100
            if worst_value != 0
            else 0
        )

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
        f.write(f"- {failure_rate:.1f}% of runs failed. Consider:\n")
        f.write("  - Adjusting optimization parameters (population size, iterations)\n")
        f.write("  - Checking ROI definition and mesh quality\n")
        f.write("  - Reducing computational complexity\n")

    if len(valid_runs) > 1:
        valid_func_values = [val for _, val in valid_runs]
        mean_value = np.mean(valid_func_values)
        std_value = np.std(valid_func_values)
        cv = std_value / abs(mean_value) if mean_value != 0 else 0
        if cv > 0.1:  # High variability
            f.write(f"- High variability in results (CV={cv:.3f}). Consider:\n")
            f.write("  - Increasing number of optimization runs\n")
            f.write("  - Adjusting optimization algorithm parameters\n")
            f.write("  - Verifying problem setup and constraints\n")
        else:
            f.write(f"- Good consistency across runs (CV={cv:.3f})\n")
            f.write("  - Results appear reliable\n")
            f.write("  - Consider using fewer runs for similar problems\n")

    f.write("\n")
