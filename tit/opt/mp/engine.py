"""Multi-polar leadfield DE search orchestrator.

Public API: ``run_mp_search(config) -> MultiPolarResult``
"""

import logging
import os
import time

from tit.opt.config import MultiPolarConfig, MultiPolarResult
from tit.logger import add_file_handler

log = logging.getLogger(__name__)


def run_mp_search(config: MultiPolarConfig) -> MultiPolarResult:
    """Run multi-polar leadfield-based DE optimization."""
    from simnibs.utils import TI_utils as TI

    from tit.opt.fast_eval import FastTIEvaluator
    from tit.opt.mp.optimizer import run_de_search
    from tit.opt.roi import ROIResolver
    from tit.paths import get_path_manager

    pm = get_path_manager()

    # ── Logging ──────────────────────────────────────────────────────────
    logger_name = f"tit.opt.mp.{config.subject_id}"
    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, f'mp_search_{time.strftime("%Y%m%d_%H%M%S")}.log')
    add_file_handler(log_file, logger_name=logger_name)
    logger = logging.getLogger(logger_name)

    # ── Output directory ─────────────────────────────────────────────────
    if config.output_dir:
        output_dir = config.output_dir
    else:
        flex_root = pm.flex_search(config.subject_id)
        os.makedirs(flex_root, exist_ok=True)
        dirname = f'mp_search_{time.strftime("%Y%m%d_%H%M%S")}'
        output_dir = os.path.join(flex_root, dirname)
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Multi-polar DE search: {config.n_pairs} pairs")
    logger.info(f"Leadfield: {config.leadfield_hdf}")
    logger.info(f"Output: {output_dir}")

    # ── Load leadfield ───────────────────────────────────────────────────
    logger.info("Loading leadfield...")
    t0 = time.time()
    lf, mesh, idx_lf = TI.load_leadfield(config.leadfield_hdf)
    logger.info(f"Leadfield loaded in {time.time() - t0:.1f}s")

    # ── Create evaluator ─────────────────────────────────────────────────
    evaluator = FastTIEvaluator(lf, mesh, idx_lf)

    # ── Resolve ROI ──────────────────────────────────────────────────────
    m2m_path = pm.m2m(config.subject_id)
    resolver = ROIResolver(mesh, m2m_path)

    roi_idx, roi_vol = resolver.resolve_roi(config.roi)
    logger.info(f"ROI: {len(roi_idx)} elements")

    nonroi_idx, nonroi_vol = resolver.resolve_nonroi(
        roi_idx, config.non_roi_method, config.non_roi
    )
    logger.info(f"Non-ROI: {len(nonroi_idx)} elements")

    evaluator.setup_evaluation(roi_idx, roi_vol, nonroi_idx, nonroi_vol)

    # ── Search-time non-ROI subsampling (finding F10) ──────────────────────
    # The DE objective only needs roi_mean/nonroi_mean, not the correct
    # (expensive) N>2 envelope on every non-ROI element. The winning
    # montage is always rescored on the full mesh (see run_de_search), so
    # this only trades search speed for search-time ranking noise.
    evaluator.setup_search_subsample(n_nonroi_samples=config.search_nonroi_samples)
    logger.info(
        f"Search subsample: {config.search_nonroi_samples} non-ROI elements "
        f"(of {len(nonroi_idx)})"
    )

    # ── Build valid electrode list ───────────────────────────────────────
    valid_electrodes = [(name, idx) for name, idx in idx_lf.items() if idx is not None]
    logger.info(f"Valid electrodes: {len(valid_electrodes)}")

    # ── Run DE search ────────────────────────────────────────────────────
    t0 = time.time()
    de_result = run_de_search(evaluator, valid_electrodes, config, logger)
    elapsed = time.time() - t0
    logger.info(f"DE search completed in {elapsed:.1f}s ({elapsed / 60:.1f} min)")

    # ── Save results ─────────────────────────────────────────────────────
    from tit.opt.mp.results import save_results

    save_results(de_result, config, output_dir, logger)

    # ── Return result ────────────────────────────────────────────────────
    return MultiPolarResult(
        success=de_result["convergence_success"],
        output_dir=output_dir,
        best_focality=de_result["best_focality"],
        best_montage=de_result["best_montage"],
        n_iterations_run=de_result["n_iterations"],
    )
