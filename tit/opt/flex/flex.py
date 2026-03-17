"""Flex-search optimization for TI stimulation.

Public API: ``run_flex_search(config) -> FlexResult``
"""


import logging
import os
import shutil

import numpy as np

from tit.opt.config import FlexConfig, FlexResult
from tit.paths import get_path_manager
from . import builder


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
