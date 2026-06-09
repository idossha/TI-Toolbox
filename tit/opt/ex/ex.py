"""Exhaustive search optimization for TI stimulation.

Public API: ``run_ex_search(config) -> ExResult``
"""

import logging
import os
import time
from pathlib import Path

from tit.opt.config import ExConfig, ExResult
from tit.paths import get_path_manager
from tit.logger import add_file_handler

from .engine import ExSearchEngine
from .buckets import build_electrode_mirror_map, canonical_template_coord_path
from .logic import generate_current_ratios
from .results import process_and_save


def run_ex_search(config: ExConfig) -> ExResult:
    """Run exhaustive search from a typed config object."""
    from tit.telemetry import track_operation
    from tit import constants as const

    with track_operation(const.TELEMETRY_OP_EX_SEARCH):
        return _run_ex_search_inner(config)


def _run_ex_search_inner(config: ExConfig) -> ExResult:
    """Inner implementation of :func:`run_ex_search` (unwrapped)."""
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

    roi_path = Path(config.roi_name)
    roi_file = str(
        roi_path
        if roi_path.is_file()
        else Path(pm.rois(config.subject_id)) / config.roi_name
    )

    if isinstance(config.electrodes, ExConfig.PoolElectrodes):
        pool = config.electrodes.electrodes
        e1_plus = e1_minus = e2_plus = e2_minus = pool
        all_combinations = True
        symmetry_mirror_map = None
    else:
        e1_plus = config.electrodes.e1_plus
        e1_minus = config.electrodes.e1_minus
        e2_plus = config.electrodes.e2_plus
        e2_minus = config.electrodes.e2_minus
        all_combinations = False
        symmetry_mirror_map = _build_symmetry_mirror_map(config, pm, logger)

    leadfield_path = os.path.join(
        pm.leadfields(config.subject_id), config.leadfield_hdf
    )

    engine = ExSearchEngine(leadfield_path, roi_file, config.roi_name, logger)
    engine.initialize(roi_radius=config.roi_radius)

    ratios = generate_current_ratios(
        config.total_current,
        config.current_step,
        config.channel_limit or config.total_current - config.current_step,
    )

    logger.info(f"Generated {len(ratios)} current ratio combinations")

    results = engine.run(
        e1_plus,
        e1_minus,
        e2_plus,
        e2_minus,
        ratios,
        all_combinations,
        output_dir,
        symmetry_mirror_map=symmetry_mirror_map,
        symmetry_layout=config.symmetry_layout,
    )

    output_info = process_and_save(results, config, output_dir, logger)
    logger.info(f"Config: {output_info['config_json_path']}")
    logger.info(f"CSV: {output_info['csv_path']}")
    if output_info.get("best_composite_csv"):
        logger.info(f"Best composite: {output_info['best_composite_csv']}")

    return ExResult(
        success=True,
        output_dir=output_dir,
        n_combinations=len(results),
        results_csv=output_info.get("csv_path"),
        best_composite_csv=output_info.get("best_composite_csv"),
        config_json=output_info.get("config_json_path"),
    )


def _infer_symmetry_eeg_csv(config: ExConfig, pm) -> Path | None:
    """Infer the EEG-position CSV from the leadfield name when possible."""
    leadfield_name = Path(config.leadfield_hdf).name
    net_name = leadfield_name.removesuffix(".hdf5").removesuffix("_leadfield")
    if not net_name:
        return None
    canonical = canonical_template_coord_path(net_name)
    if canonical is not None:
        return canonical
    candidate = Path(pm.eeg_positions(config.subject_id)) / f"{net_name}.csv"
    return candidate if candidate.is_file() else None


def _build_symmetry_mirror_map(config: ExConfig, pm, logger) -> dict[str, str] | None:
    """Return an electrode mirror map for symmetric bucket mode, if enabled."""
    if not config.symmetric_bucket:
        return None

    eeg_csv = Path(config.symmetry_eeg_csv) if config.symmetry_eeg_csv else None
    if eeg_csv is None or not eeg_csv.is_file():
        eeg_csv = _infer_symmetry_eeg_csv(config, pm)
    if eeg_csv is None or not eeg_csv.is_file():
        raise ValueError(
            "symmetric_bucket requires a valid symmetry_eeg_csv or an inferable "
            "EEG-position CSV from the selected leadfield."
        )

    mirror_map = build_electrode_mirror_map(eeg_csv)
    logger.info(f"Symmetric bucket mode: using EEG mirror map from {eeg_csv}")
    return mirror_map
