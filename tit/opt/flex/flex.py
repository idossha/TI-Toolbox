"""Flex-search optimization for TI stimulation.

Thin orchestrator -- all SimNIBS coupling lives in ``builder.py``.

Public API: ``run_flex_search(config, logger=None) -> FlexResult``
"""

from __future__ import annotations

import logging
import os
import shutil
import time

import numpy as np

from tit.opt.config import (
    AtlasROI,
    FlexConfig,
    FlexResult,
    SphericalROI,
    SubcorticalROI,
)

from . import builder, flex_log, multi_start

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_flex_search(config: FlexConfig, logger=None) -> FlexResult:
    """Run flex-search optimization from a typed FlexConfig.

    Args:
        config: A :class:`FlexConfig` instance with all parameters.
        logger: Optional stdlib logger; one is created automatically if *None*.

    Returns:
        A :class:`FlexResult` instance describing the outcome.
    """
    from tit.core import get_path_manager

    get_path_manager().project_dir = config.project_dir

    start_time = time.time()
    n_multistart = config.n_multistart
    optim_funvalue_list = np.zeros(n_multistart)

    # Build a throwaway opt to resolve the output folder path
    opt_base = builder.build_optimization(config)
    base_output_folder = config.output_folder or opt_base.output_folder

    if logger is None:
        logger = logging.getLogger(__name__)

    # Derive ROI method tag for logging
    roi_method = {
        SphericalROI: "spherical",
        AtlasROI: "atlas",
        SubcorticalROI: "subcortical",
    }.get(type(config.roi), "unknown")

    output_folder_list = [
        os.path.join(base_output_folder, f"{i:02d}") for i in range(n_multistart)
    ]

    label = f"Flex-search ({config.subject_id})"
    logger.info(f"{label}: Started")
    logger.info(
        f"Goal={config.goal}, postproc={config.postproc}, roi={roi_method}, "
        f"runs={n_multistart}"
    )

    # -- Run optimizations ---------------------------------------------------
    for i_opt in range(n_multistart):
        run_start = time.time()
        step = (
            f"Optimization run {i_opt + 1}/{n_multistart}"
            if n_multistart > 1
            else "Optimization"
        )
        try:
            opt = builder.build_optimization(config)
            opt.output_folder = output_folder_list[i_opt]
            os.makedirs(opt.output_folder, exist_ok=True)

            if i_opt == 0:
                flex_log.log_optimization_config(config, n_multistart, logger)

            builder.configure_optimizer_options(opt, config, logger)
            logger.info(f"├─ {step}: Started")

            cpus = config.cpus if config.cpus is not None else None
            t0 = time.time()
            optim_funvalue_list[i_opt] = multi_start.run_single_optimization(
                opt, cpus, logger
            )
            opt_dur = time.time() - t0

            if optim_funvalue_list[i_opt] != float("inf"):
                flex_log.log_run_details(
                    i_opt,
                    n_multistart,
                    opt.output_folder,
                    opt,
                    opt_dur,
                    time.time() - run_start,
                    logger,
                )
                logger.info(f"├─ {step}: Complete")
                if config.run_final_electrode_simulation:
                    logger.info("├─ Final electrode simulation: Started")
                    logger.info("├─ Final electrode simulation: Complete")
            else:
                logger.error(f"├─ {step}: Failed - See logs for details")

        except Exception as exc:
            logger.error(
                f"Unexpected error in run {i_opt + 1} "
                f"after {time.time() - run_start:.1f}s: {exc}"
            )
            optim_funvalue_list[i_opt] = float("inf")
            logger.error(f"├─ {step}: Failed - Unexpected error: {type(exc).__name__}")

    # -- Post-processing -----------------------------------------------------
    best_opt_idx = _postprocess(
        config,
        n_multistart,
        optim_funvalue_list,
        output_folder_list,
        base_output_folder,
        start_time,
        logger,
    )

    total_duration = time.time() - start_time
    flex_log.log_session_footer(config.subject_id, n_multistart, total_duration, logger)
    builder.generate_report(
        config,
        n_multistart,
        optim_funvalue_list,
        best_opt_idx,
        base_output_folder,
        logger,
    )

    success = best_opt_idx != -1
    return FlexResult(
        success=success,
        output_folder=base_output_folder,
        function_values=optim_funvalue_list.tolist(),
        best_value=(
            float(optim_funvalue_list[best_opt_idx]) if success else float("inf")
        ),
        best_run_index=best_opt_idx,
    )


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


def _postprocess(config, n_multistart, fvals, folders, base, t0, log) -> int:
    """Post-process results. Returns best run index (-1 on failure)."""
    label = f"Flex-search ({config.subject_id})"

    if n_multistart > 1:
        return _post_multi(config, n_multistart, fvals, folders, base, t0, log, label)
    return _post_single(config, fvals, folders, base, t0, log, label)


def _post_multi(config, n, fvals, folders, base, t0, log, label) -> int:
    log.debug("=" * 80)
    log.debug("MULTI-START OPTIMIZATION POST-PROCESSING")
    log.debug("=" * 80)
    log.info("├─ Post-processing: Started")

    best_idx, valid, failed = multi_start.select_best_solution(fvals, n, log)

    if best_idx == -1:
        log.error("├─ Post-processing: Failed - No valid optimization results found")
        log.info(f"{label}: Complete")
        return -1

    if not multi_start.copy_best_solution(folders[best_idx], base, log):
        log.error("├─ Post-processing: Failed - Failed to copy best solution")
        log.info(f"{label}: Complete")
        return -1

    summary = os.path.join(base, "multistart_optimization_summary.txt")
    try:
        multi_start.create_summary_file(
            summary,
            config,
            t0,
            is_multistart=True,
            n_multistart=n,
            optim_funvalue_list=fvals,
            best_opt_idx=best_idx,
            valid_runs=valid,
            failed_runs=failed,
        )
        log.debug(f"Multi-start summary saved to: {summary}")
    except Exception as e:
        log.warning(f"Failed to create multi-start summary file: {e}")

    multi_start.cleanup_temporary_directories(folders, n, log)
    log.debug("MULTI-START OPTIMIZATION COMPLETED SUCCESSFULLY")
    log.debug(f"Final results available in: {base}")
    log.info("├─ Post-processing: Complete")
    log.info(f"{label}: Complete")
    return best_idx


def _post_single(config, fvals, folders, base, t0, log, label) -> int:
    if fvals[0] == float("inf"):
        log.error("Single optimization run failed")
        log.info(f"{label}: Complete")
        return -1

    log.debug("SINGLE OPTIMIZATION COMPLETED SUCCESSFULLY")
    log.debug(f"Final function value: {fvals[0]:.6f}")

    src = folders[0]
    log.debug(f"FINALIZING RESULTS: {src} -> {base}")

    if not multi_start.copy_best_solution(src, base, log):
        log.info(f"{label}: Complete")
        return -1

    summary = os.path.join(base, "optimization_summary.txt")
    try:
        multi_start.create_summary_file(
            summary,
            config,
            t0,
            is_multistart=False,
            function_value=fvals[0],
        )
        log.debug(f"Optimization summary saved to: {summary}")
    except Exception as e:
        log.warning(f"Failed to create optimization summary file: {e}")

    # Clean up temporary directory
    time.sleep(0.1)
    for attempt in range(2):
        try:
            if os.path.exists(src):
                shutil.rmtree(src)
            log.debug("Removed temporary directory")
            break
        except Exception as exc:
            if attempt == 0:
                time.sleep(0.2)
            else:
                log.warning(f"Failed to remove temp dir: {src} - {exc}")

    log.debug(f"Results available in: {base}")
    log.info(f"{label}: Complete")
    return 0
