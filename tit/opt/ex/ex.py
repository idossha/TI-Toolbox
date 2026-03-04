"""Exhaustive search optimization for TI stimulation.

Public API: ``run_ex_search(config, logger=None) -> ExResult``
"""

from __future__ import annotations

import os
import time
from typing import Optional
from logging import Logger

from tit.opt.config import (
    ExConfig,
    ExResult,
    BucketElectrodes,
    PoolElectrodes,
)


def run_ex_search(config: ExConfig, logger: Optional[Logger] = None) -> ExResult:
    """Run exhaustive search from a typed config object.

    Orchestrates: LeadfieldProcessor -> CurrentRatioGenerator ->
    MontageGenerator -> SimulationRunner -> ResultsManager.

    Args:
        config: ExConfig describing all search parameters.
        logger: Optional logger; a default file logger is created if None.

    Returns:
        ExResult with success flag and output paths.
    """
    from tit.core import get_path_manager

    pm = get_path_manager()
    pm.project_dir = config.project_dir

    # Setup logger
    if logger is None:
        import logging
        from tit.logger import add_file_handler

        logs_dir = pm.logs(config.subject_id)
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(
            logs_dir, f'ex_search_{time.strftime("%Y%m%d_%H%M%S")}.log'
        )
        logger_name = f"tit.opt.ex_search.{config.subject_id}"
        add_file_handler(log_file, logger_name=logger_name)
        logger = logging.getLogger(logger_name)

    logger.info("=" * 80)
    logger.info("TI Exhaustive Search")
    logger.info("=" * 80)
    logger.info(f"Project: {config.project_dir}")
    logger.info(f"Subject: {config.subject_id}")
    logger.info("")

    output_dir = ""
    try:
        # -- Resolve output directory --------------------------------------
        roi_name = config.roi_name
        roi_csv = roi_name if roi_name.endswith(".csv") else f"{roi_name}.csv"
        net = (config.eeg_net or "unknown_net").strip() or "unknown_net"
        run_name = f"{roi_csv}_{net}"
        output_dir = pm.ex_search_run(config.subject_id, run_name)
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Output directory: {output_dir}")

        # -- Resolve electrode lists ---------------------------------------
        if isinstance(config.electrodes, PoolElectrodes):
            pool = config.electrodes.electrodes
            e1_plus = e1_minus = e2_plus = e2_minus = pool
            all_combinations = True
        else:
            e1_plus = config.electrodes.e1_plus
            e1_minus = config.electrodes.e1_minus
            e2_plus = config.electrodes.e2_plus
            e2_minus = config.electrodes.e2_minus
            all_combinations = False

        # -- Initialize processors -----------------------------------------
        from .runner import (
            LeadfieldProcessor,
            CurrentRatioGenerator,
            MontageGenerator,
            SimulationRunner,
        )
        from .results import ResultsManager

        roi_dir = pm.rois(config.subject_id)
        roi_file = os.path.join(roi_dir, roi_csv)

        # -- Step 1: Load leadfield & ROI ----------------------------------
        logger.info("Step 1/5: Loading leadfield and ROI data")
        leadfield_processor = LeadfieldProcessor(
            config.leadfield_hdf, roi_file, roi_name, logger
        )
        leadfield_processor.initialize(roi_radius=config.roi_radius)

        # -- Step 2: Generate current ratios -------------------------------
        logger.info("Step 2/5: Generating current ratios")
        current_generator = CurrentRatioGenerator(
            config.currents.total,
            config.currents.step,
            config.currents.channel_limit,
            logger,
        )
        current_ratios = current_generator.generate_ratios()
        logger.info(f"Generated {len(current_ratios)} current ratio combinations")

        # -- Step 3: Generate montages -------------------------------------
        logger.info("Step 3/5: Preparing montage combinations")
        montage_generator = MontageGenerator(
            e1_plus,
            e1_minus,
            e2_plus,
            e2_minus,
            current_ratios,
            all_combinations,
            logger,
        )

        # -- Step 4: Run simulation loop -----------------------------------
        logger.info("Step 4/5: Running TI simulation loop")
        simulator = SimulationRunner(
            leadfield_processor, montage_generator, output_dir, logger
        )
        results = simulator.run_simulation()

        if not results:
            logger.error(
                "Simulation produced no results -- check electrode/ROI settings"
            )
            return ExResult(success=False, output_dir=output_dir, n_combinations=0)

        # -- Step 5: Save results ------------------------------------------
        logger.info("Step 5/5: Processing and saving results")
        results_manager = ResultsManager(results, output_dir, roi_name, logger)
        output_info = results_manager.process_and_save_results()

        logger.info("Ex-search completed successfully!")
        logger.info(f"Results: {output_info['json_path']}")
        logger.info(f"Summary: {output_info['csv_path']}")
        if output_info["visualization_paths"]:
            logger.info(
                f"Visualizations: {len(output_info['visualization_paths'])} files generated"
            )

        return ExResult(
            success=True,
            output_dir=output_dir,
            n_combinations=len(results),
            results_csv=output_info.get("csv_path"),
            results_json=output_info.get("json_path"),
        )

    except Exception as exc:
        logger.error(f"Exhaustive search failed: {exc}", exc_info=True)
        return ExResult(
            success=False,
            output_dir=output_dir,
            n_combinations=0,
        )
