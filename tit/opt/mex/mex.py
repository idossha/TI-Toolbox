"""Multipolar (4-pair) exhaustive search optimization.

Public API: ``run_m_ex_search(config) -> MExResult``
"""

import csv
import logging
import os
import time
from pathlib import Path


from tit.logger import add_file_handler
from tit.opt.config import MExConfig, MExResult
from tit.opt.ex.results import process_and_save
from tit.opt.ex.roi import atlas_roi_entries, mni_roi_files_to_subject_space
from tit.opt.ex.symmetry import build_symmetry_mirror_map
from tit.paths import get_path_manager

from .engine import MExSearchEngine
from .logic import count_multipolar_combinations, explain_zero_multipolar_combinations


def run_m_ex_search(config: MExConfig) -> MExResult:
    """Run multipolar exhaustive search from a typed config object."""
    return _run_m_ex_search_inner(config)


def _run_m_ex_search_inner(config: MExConfig) -> MExResult:
    pm = get_path_manager()

    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(
        logs_dir, f'm_ex_search_{time.strftime("%Y%m%d_%H%M%S")}.log'
    )
    logger_name = f"tit.opt.m_ex_search.{config.subject_id}"
    add_file_handler(log_file, logger_name=logger_name)
    add_file_handler(log_file, logger_name="simnibs")
    logger = logging.getLogger(logger_name)

    logger.info("%s\nmTI Multipolar Exhaustive Search\n%s", "=" * 60, "=" * 60)
    logger.info("Project: %s", pm.project_dir)
    logger.info("Subject: %s", config.subject_id)

    run_name = config.run_name or time.strftime("%Y%m%d_%H%M%S")
    output_dir = pm.m_ex_search_run(config.subject_id, run_name)

    if isinstance(config.electrodes, MExConfig.PoolElectrodes):
        buckets_or_pool = config.electrodes.electrodes
        all_combinations = True
        symmetry_mirror_map = None
    else:
        buckets_or_pool = {
            "e1_plus": config.electrodes.e1_plus,
            "e1_minus": config.electrodes.e1_minus,
            "e2_plus": config.electrodes.e2_plus,
            "e2_minus": config.electrodes.e2_minus,
            "e3_plus": config.electrodes.e3_plus,
            "e3_minus": config.electrodes.e3_minus,
            "e4_plus": config.electrodes.e4_plus,
            "e4_minus": config.electrodes.e4_minus,
        }
        all_combinations = False
        symmetry_mirror_map = build_symmetry_mirror_map(config, pm, logger)

    # Enumeration is cheap and independent of the leadfield: fail before
    # loading it (and before creating the run directory) when there is
    # nothing to evaluate.
    n_candidates = count_multipolar_combinations(
        buckets_or_pool,
        all_combinations=all_combinations,
        symmetry_mirror_map=symmetry_mirror_map,
        symmetry_pairing=config.symmetry_pairing,
    )
    if n_candidates == 0:
        reason = explain_zero_multipolar_combinations(
            buckets_or_pool,
            all_combinations=all_combinations,
            symmetry_mirror_map=symmetry_mirror_map,
            symmetry_pairing=config.symmetry_pairing,
        )
        raise ValueError(
            f"m-ex-search has no candidate montages to evaluate: {reason}"
        )
    logger.info("Candidate montages: %d", n_candidates)

    os.makedirs(output_dir, exist_ok=True)
    logger.info("Output: %s", output_dir)

    # Mirrors tit/opt/ex/ex.py. roi_names=[] means "no spherical centers",
    # which is how an atlas-only target is expressed -- roi_name is then just
    # the naming label and no CSV is read.
    roi_names = config.roi_names if config.roi_names is not None else [config.roi_name]
    roi_dir = pm.rois(config.subject_id)
    if roi_names and config.roi_coordinate_space == "mni":
        roi_files = mni_roi_files_to_subject_space(
            roi_names, roi_dir, pm.m2m(config.subject_id), output_dir, logger
        )
    else:
        roi_files = [os.path.join(roi_dir, name) for name in roi_names]
    if len(roi_files) > 1:
        logger.info("Combining %d ROIs into one target: %s", len(roi_files), roi_names)

    atlas_entries = atlas_roi_entries(config)
    if atlas_entries:
        logger.info("Adding %d atlas ROI target(s)", len(atlas_entries))
        roi_files = roi_files + atlas_entries
    roi_target = roi_files

    leadfield_path = os.path.join(
        pm.leadfields(config.subject_id), config.leadfield_hdf
    )

    engine = MExSearchEngine(
        leadfield_path, roi_target, config.roi_name, logger
    )
    engine.initialize(roi_radius=config.roi_radius)
    results = engine.run(
        buckets_or_pool,
        all_combinations,
        output_dir,
        current_mA=config.current_mA,
        symmetry_mirror_map=symmetry_mirror_map,
        symmetry_pairing=config.symmetry_pairing,
        n_jobs=config.n_jobs,
    )

    output_info = process_and_save(results, config, output_dir, logger)
    logger.info("Config: %s", output_info["config_json_path"])
    logger.info("CSV: %s", output_info["csv_path"])

    return MExResult(
        success=True,
        output_dir=output_dir,
        n_combinations=len(results),
        results_csv=output_info.get("csv_path"),
        config_json=output_info.get("config_json_path"),
    )
