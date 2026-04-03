"""Flex-search optimization for TI stimulation.

Public API: ``run_flex_search(config) -> FlexResult``
"""

from __future__ import annotations

import concurrent.futures
import logging
import multiprocessing
import os
import shutil
import traceback

import numpy as np

from tit.opt.config import FlexConfig, FlexResult
from tit.paths import get_path_manager
from . import builder


def _run_single_flex_start(
    config: FlexConfig,
    run_idx: int,
    output_folder: str,
    per_run_cpus: int | None,
) -> tuple[int, float, str | None]:
    """Execute one flex-search multistart in an isolated process."""
    logger = logging.getLogger(__name__)
    try:
        opt = builder.build_optimization(config)
        opt.output_folder = output_folder
        os.makedirs(opt.output_folder, exist_ok=True)
        builder.configure_optimizer_options(opt, config, logger)
        opt.run(cpus=per_run_cpus)
        return run_idx, float(opt.optim_funvalue), None
    except Exception:
        return run_idx, float("inf"), traceback.format_exc()


def run_flex_search(config: FlexConfig) -> FlexResult:
    """Run flex-search optimization from a typed FlexConfig."""

    from .manifest import write_manifest
    from .utils import generate_label, generate_run_dirname

    pm = get_path_manager(config.project_dir)

    logger = logging.getLogger(__name__)

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

    logger.info(
        f"Flex-search ({config.subject_id}): "
        f"goal={config.goal}, postproc={config.postproc}, runs={n}"
    )

    folders = [os.path.join(base_folder, f"{i:02d}") for i in range(n)]
    total_cpus = max(1, int(config.cpus or 1))

    # -- Run optimizations --
    if n > 1 and total_cpus > 1:
        parallel_runs = min(n, total_cpus)
        per_run_cpus = max(1, total_cpus // parallel_runs)
        logger.info(
            "├─ Parallel multistart: %d concurrent runs, %d CPU(s) per run",
            parallel_runs,
            per_run_cpus,
        )
        ctx = multiprocessing.get_context("spawn")
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=parallel_runs,
            mp_context=ctx,
        ) as executor:
            futures = []
            for i in range(n):
                step = f"Run {i + 1}/{n}"
                logger.info(f"├─ {step}: queued")
                futures.append(
                    executor.submit(
                        _run_single_flex_start,
                        config,
                        i,
                        folders[i],
                        per_run_cpus,
                    )
                )

            for future in concurrent.futures.as_completed(futures):
                run_idx, funvalue, error_text = future.result()
                fvals[run_idx] = funvalue
                step = f"Run {run_idx + 1}/{n}"
                if error_text is not None:
                    logger.error(f"├─ {step}: failed\n%s", error_text)
                else:
                    logger.info(f"├─ {step}: value={fvals[run_idx]:.6f}")
    else:
        for i in range(n):
            opt = builder.build_optimization(config)
            opt.output_folder = folders[i]
            os.makedirs(opt.output_folder, exist_ok=True)
            builder.configure_optimizer_options(opt, config, logger)

            step = f"Run {i + 1}/{n}" if n > 1 else "Optimization"
            logger.info(f"├─ {step}: started")

            opt.run(cpus=config.cpus)
            fvals[i] = opt.optim_funvalue
            logger.info(f"├─ {step}: value={fvals[i]:.6f}")

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
