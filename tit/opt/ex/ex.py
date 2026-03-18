"""Exhaustive search optimization for TI stimulation.

Public API: ``run_ex_search(config) -> ExResult``
"""

import logging
import os
import time

from tit.opt.config import ExConfig, ExResult
from tit.paths import get_path_manager
from tit.logger import add_file_handler

from .engine import ExSearchEngine
from .logic import generate_current_ratios
from .results import process_and_save


def run_ex_search(config: ExConfig) -> ExResult:
    """Run exhaustive search from a typed config object."""

    pm = get_path_manager()

    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, f'ex_search_{time.strftime("%Y%m%d_%H%M%S")}.log')
    logger_name = f"tit.opt.ex_search.{config.subject_id}"
    add_file_handler(log_file, logger_name=logger_name)
    add_file_handler(log_file, logger_name="simnibs")
    logger = logging.getLogger(logger_name)

    logger.info(f"{'=' * 60}\nTI Exhaustive Search\n{'=' * 60}")
    logger.info(f"Project: {pm.project_dir}")
    logger.info(f"Subject: {config.subject_id}")

    run_name = config.run_name or time.strftime("%Y%m%d_%H%M%S")
    output_dir = pm.ex_search_run(config.subject_id, run_name)
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Output: {output_dir}")

    roi_file = os.path.join(pm.rois(config.subject_id), config.roi_name)

    if isinstance(config.electrodes, ExConfig.PoolElectrodes):
        pool = config.electrodes.electrodes
        e1_plus = e1_minus = e2_plus = e2_minus = pool
        all_combinations = True
    else:
        e1_plus = config.electrodes.e1_plus
        e1_minus = config.electrodes.e1_minus
        e2_plus = config.electrodes.e2_plus
        e2_minus = config.electrodes.e2_minus
        all_combinations = False

    leadfield_path = os.path.join(pm.leadfields(config.subject_id), config.leadfield_hdf)

    engine = ExSearchEngine(leadfield_path, roi_file, config.roi_name, logger)
    engine.initialize(roi_radius=config.roi_radius)

    ratios = generate_current_ratios(
        config.total_current,
        config.current_step,
        config.channel_limit or config.total_current - config.current_step,
    )

    logger.info(f"Generated {len(ratios)} current ratio combinations")

    results = engine.run(
        e1_plus, e1_minus, e2_plus, e2_minus, ratios, all_combinations, output_dir
    )

    output_info = process_and_save(results, config, output_dir, logger)
    logger.info(f"Config: {output_info['config_json_path']}")
    logger.info(f"CSV: {output_info['csv_path']}")

    return ExResult(
        success=True,
        output_dir=output_dir,
        n_combinations=len(results),
        results_csv=output_info.get("csv_path"),
        config_json=output_info.get("config_json_path"),
    )
