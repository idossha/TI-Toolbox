"""Flex-search optimization for TI stimulation.

Orchestrates multi-start differential-evolution runs, selects the best
result, and writes a manifest + HTML report.

Public API
----------
run_flex_search
    Run differential-evolution electrode placement optimization.

See Also
--------
tit.opt.config.FlexConfig : Input configuration.
tit.opt.config.FlexResult : Output result container.
tit.opt.flex.builder : SimNIBS object construction used internally.
"""

import logging
import os
import shutil
import time

import numpy as np

from tit.opt.config import FlexConfig, FlexResult
from tit.logger import add_file_handler
from tit.paths import get_path_manager
from . import builder


def run_flex_search(config: FlexConfig) -> FlexResult:
    """Run differential-evolution electrode placement optimization.

    Uses ``scipy.optimize.differential_evolution`` (via SimNIBS
    ``TesFlexOptimization``) to find electrode positions that maximize
    field strength, peak intensity, or focality in a target ROI.

    Multiple independent restarts (controlled by
    ``config.n_multistart``) are executed sequentially; the best run's
    output is promoted to the base output folder.

    Parameters
    ----------
    config : FlexConfig
        Fully specified optimization configuration including subject,
        ROI definition, electrode geometry, and DE hyperparameters.

    Returns
    -------
    FlexResult
        Optimization outcomes including best montage, objective value,
        and convergence diagnostics.

    See Also
    --------
    FlexConfig : Configuration dataclass for flex-search.
    FlexResult : Result container with per-restart function values.
    tit.opt.ex.ex.run_ex_search : Alternative exhaustive grid search.
    """

    from .manifest import write_manifest
    from .utils import generate_label, generate_run_dirname

    pm = get_path_manager()

    # Set up file logging — capture both tit and simnibs output
    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(
        logs_dir, f'flex_search_{time.strftime("%Y%m%d_%H%M%S")}.log'
    )
    logger_name = f"tit.opt.flex.{config.subject_id}"
    add_file_handler(log_file, logger_name=logger_name)
    add_file_handler(log_file, logger_name="simnibs")
    logger = logging.getLogger(logger_name)

    n = config.n_multistart

    # Resolve base output folder
    if config.output_folder:
        base_folder = config.output_folder
    else:
        flex_root = pm.flex_search(config.subject_id)
        os.makedirs(flex_root, exist_ok=True)
        dirname = generate_run_dirname(flex_root)
        base_folder = os.path.join(flex_root, dirname)

    os.makedirs(base_folder, exist_ok=True)
    fvals = np.full(n, float("inf"))

    folders = [os.path.join(base_folder, f"{i:02d}") for i in range(n)]

    # -- Run optimizations --
    for i in range(n):
        opt = builder.build_optimization(config)
        opt.output_folder = folders[i]
        os.makedirs(opt.output_folder, exist_ok=True)
        builder.configure_optimizer_options(opt, config, logger)

        opt.run(cpus=config.cpus)
        fvals[i] = opt.optim_funvalue

    # -- Select best --
    valid_mask = fvals < float("inf")
    if not valid_mask.any():
        logger.error("All optimization runs failed")
        result = FlexResult(
            success=False,
            output_folder=base_folder,
            function_values=fvals.tolist(),
            best_value=float("inf"),
            best_run_index=-1,
        )
        label = generate_label(config)
        write_manifest(base_folder, config, result, label)
        return result

    best_idx = int(np.argmin(fvals))
    logger.info(f"Best run: #{best_idx + 1} (value={fvals[best_idx]:.6f})")

    # -- Promote best to base folder --
    best_folder = folders[best_idx]
    for item in os.listdir(best_folder):
        src = os.path.join(best_folder, item)
        dst = os.path.join(base_folder, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # -- Cleanup temp subdirs --
    for folder in folders:
        if os.path.isdir(folder):
            shutil.rmtree(folder)

    # -- Report --
    builder.generate_report(config, n, fvals, best_idx, base_folder, logger)

    result = FlexResult(
        success=True,
        output_folder=base_folder,
        function_values=fvals.tolist(),
        best_value=float(fvals[best_idx]),
        best_run_index=best_idx,
    )

    # -- Write manifest --
    label = generate_label(config)
    write_manifest(base_folder, config, result, label)

    return result
