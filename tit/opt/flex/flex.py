"""Flex-search optimization for TI stimulation.

Public API: ``run_flex_search(config) -> FlexResult``
"""

from __future__ import annotations

import logging
import os
import shutil

import numpy as np

from tit.opt.config import FlexConfig, FlexResult
from . import builder
import tit.paths


def run_flex_search(config: FlexConfig, logger=None) -> FlexResult:
    """Run flex-search optimization from a typed FlexConfig."""
    
    paths.project_dir = config.project_dir

    logger = logging.getLogger(__name__)

    n = config.n_multistart
    fvals = np.full(n, float("inf"))

    # Resolve base output folder from a throwaway opt build
    opt_base = builder.build_optimization(config)
    base_folder = config.output_folder or opt_base.output_folder

    folders = [os.path.join(base_folder, f"{i:02d}") for i in range(n)]

    logger.info(
        f"Flex-search ({config.subject_id}): "
        f"goal={config.goal}, postproc={config.postproc}, runs={n}"
    )

    # -- Run optimizations --
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
        return FlexResult(
            success=False,
            output_folder=base_folder,
            function_values=fvals.tolist(),
            best_value=float("inf"),
            best_run_index=-1,
        )

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

    return FlexResult(
        success=True,
        output_folder=base_folder,
        function_values=fvals.tolist(),
        best_value=float(fvals[best_idx]),
        best_run_index=best_idx,
    )
