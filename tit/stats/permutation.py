"""Cluster-based permutation testing for TI-Toolbox.

Entry points
------------
run_group_comparison(config) -> GroupComparisonResult
run_correlation(config)      -> CorrelationResult

Both accept an optional ``callback_handler`` (logging.Handler) for GUI
console integration.
"""

import gc
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import nibabel as nib
import numpy as np

from tit.logger import add_file_handler
from tit.paths import get_path_manager

from tit.atlas import atlas_overlap_analysis
from .config import (
    CorrelationConfig,
    CorrelationResult,
    GroupComparisonConfig,
    GroupComparisonResult,
)
from .engine import (
    PermutationEngine,
    cluster_analysis,
    correlation_voxelwise,
    ttest_voxelwise,
)
from .nifti import load_group_data_ti_toolbox
from .reporting import generate_correlation_summary, generate_summary
from .visualization import (
    plot_cluster_size_mass_correlation,
    plot_permutation_null_distribution,
)

_logger = logging.getLogger(__name__)

_ATLAS_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "atlas"


# ─── helpers ──────────────────────────────────────────────────────────────


def _setup_logger(output_dir: str, analysis_type: str, callback_handler=None):
    """Create a run-scoped file logger."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"{analysis_type}_analysis_{ts}.log")
    logger_name = f"tit.stats.{analysis_type}"
    log = logging.getLogger(logger_name)
    log.setLevel(logging.DEBUG)
    add_file_handler(log_file, level="DEBUG", logger_name=logger_name)
    if callback_handler:
        log.addHandler(callback_handler)
    return log, log_file


def _resolve_output_dir(analysis_type: str, analysis_name: str) -> str:
    pm = get_path_manager()
    return pm.ensure(pm.stats_output(analysis_type, analysis_name))


def _save_nifti(data, template_img, path):
    img = nib.Nifti1Image(data, template_img.affine, template_img.header)
    nib.save(img, path)


# ─── group comparison ────────────────────────────────────────────────────


def run_group_comparison(
    config: GroupComparisonConfig,
    callback_handler=None,
    stop_callback=None,
) -> GroupComparisonResult:
    """Run cluster-based permutation testing for group comparison.

    Parameters
    ----------
    config : GroupComparisonConfig
        Fully specified configuration.
    callback_handler : logging.Handler, optional
        GUI log handler.
    stop_callback : callable, optional
        Returns True to abort.
    """
    t0 = time.time()
    output_dir = _resolve_output_dir(
        "group_comparison",
        config.analysis_name,
    )
    log, log_file = _setup_logger(output_dir, "group_comparison", callback_handler)

    log.info("=" * 70)
    log.info("CLUSTER-BASED PERMUTATION TESTING — GROUP COMPARISON")
    log.info("=" * 70)
    log.info("Analysis: %s", config.analysis_name)
    log.info("Output:   %s", output_dir)
    log.info(
        "Config:   test=%s  alt=%s  stat=%s  threshold=%.3f  perms=%d  alpha=%.3f  jobs=%d",
        config.test_type.value,
        config.alternative.value,
        config.cluster_stat.value,
        config.cluster_threshold,
        config.n_permutations,
        config.alpha,
        config.n_jobs,
    )

    # ── 1. Load data ─────────────────────────────────────────────────────
    log.info("[1/8] Loading subject data")
    step = time.time()

    resp_configs = [
        {"subject_id": s.subject_id, "simulation_name": s.simulation_name}
        for s in config.subjects
        if s.response == 1
    ]
    non_resp_configs = [
        {"subject_id": s.subject_id, "simulation_name": s.simulation_name}
        for s in config.subjects
        if s.response == 0
    ]

    responders, template_img, resp_ids = load_group_data_ti_toolbox(
        resp_configs,
        nifti_file_pattern=config.nifti_file_pattern,
        dtype=np.float32,
    )
    non_responders, _, non_resp_ids = load_group_data_ti_toolbox(
        non_resp_configs,
        nifti_file_pattern=config.nifti_file_pattern,
        dtype=np.float32,
    )

    log.info(
        "Loaded %d %s: %s",
        len(resp_ids),
        config.group1_name,
        resp_ids,
    )
    log.info(
        "Loaded %d %s: %s",
        len(non_resp_ids),
        config.group2_name,
        non_resp_ids,
    )
    log.info("Image shape: %s  (%.1fs)", responders.shape[:3], time.time() - step)

    if stop_callback and stop_callback():
        raise KeyboardInterrupt("Stopped by user")

    # ── 2. Voxelwise t-test ──────────────────────────────────────────────
    log.info("[2/8] Voxelwise statistical tests")
    step = time.time()

    p_values, t_statistics, valid_mask = ttest_voxelwise(
        responders,
        non_responders,
        test_type=config.test_type.value,
        alternative=config.alternative.value,
        log=log,
    )

    log.info(
        "Min p=%.2e, p<0.05: %d  (%.1fs)",
        np.min(p_values[valid_mask]),
        np.sum((p_values < 0.05) & valid_mask),
        time.time() - step,
    )

    if stop_callback and stop_callback():
        raise KeyboardInterrupt("Stopped by user")

    # ── 3. Permutation correction ────────────────────────────────────────
    log.info(
        "[3/8] Cluster-based permutation correction (%d perms)", config.n_permutations
    )
    step = time.time()

    perm_log_file = os.path.join(output_dir, "permutation_details.txt")

    engine = PermutationEngine(
        cluster_threshold=config.cluster_threshold,
        n_permutations=config.n_permutations,
        alpha=config.alpha,
        cluster_stat=config.cluster_stat.value,
        alternative=config.alternative.value,
        n_jobs=config.n_jobs,
        log=log,
    )
    sig_mask, cluster_threshold, sig_clusters, null_dist, all_clusters, corr_data = (
        engine.correct_groups(
            responders,
            non_responders,
            p_values=p_values,
            t_statistics=t_statistics,
            valid_mask=valid_mask,
            test_type=config.test_type.value,
            perm_log_file=perm_log_file,
            subject_ids_resp=resp_ids,
            subject_ids_non_resp=non_resp_ids,
        )
    )

    log.info(
        "Significant clusters: %d, voxels: %d  (%.1fs)",
        len(sig_clusters),
        np.sum(sig_mask),
        time.time() - step,
    )

    # ── 4. Cluster analysis ──────────────────────────────────────────────
    log.info("[4/8] Cluster analysis")
    clusters = cluster_analysis(sig_mask, template_img.affine, log=log)

    # ── 5. Plots ─────────────────────────────────────────────────────────
    log.info("[5/8] Generating plots")
    perm_plot = os.path.join(output_dir, "permutation_null_distribution.pdf")
    plot_permutation_null_distribution(
        null_dist,
        cluster_threshold,
        all_clusters,
        perm_plot,
        alpha=config.alpha,
        cluster_stat=config.cluster_stat.value,
    )
    corr_plot = os.path.join(output_dir, "cluster_size_mass_correlation.pdf")
    plot_cluster_size_mass_correlation(
        corr_data["sizes"],
        corr_data["masses"],
        corr_plot,
    )

    # ── 6. Average maps ─────────────────────────────────────────────────
    log.info("[6/8] Average intensity maps")
    avg_resp = np.mean(responders, axis=-1).astype(np.float32)
    _save_nifti(
        avg_resp, template_img, os.path.join(output_dir, "average_responders.nii.gz")
    )

    avg_non = np.mean(non_responders, axis=-1).astype(np.float32)
    _save_nifti(
        avg_non, template_img, os.path.join(output_dir, "average_non_responders.nii.gz")
    )

    diff = (avg_resp - avg_non).astype(np.float32)
    _save_nifti(diff, template_img, os.path.join(output_dir, "difference_map.nii.gz"))

    # ── 7. Atlas overlap ─────────────────────────────────────────────────
    log.info("[7/8] Atlas overlap")
    atlas_results = {}
    if config.atlas_files:
        if _ATLAS_DIR.exists():
            atlas_results = atlas_overlap_analysis(
                sig_mask,
                config.atlas_files,
                str(_ATLAS_DIR),
                reference_img=template_img,
            )

    # ── 8. Save outputs ─────────────────────────────────────────────────
    log.info("[8/8] Saving results")
    _save_nifti(
        sig_mask.astype(np.uint8),
        template_img,
        os.path.join(output_dir, "significant_voxels_mask.nii.gz"),
    )

    log_p = -np.log10(p_values + 1e-10)
    log_p[~valid_mask] = 0
    _save_nifti(log_p, template_img, os.path.join(output_dir, "pvalues_map.nii.gz"))

    summary_path = os.path.join(output_dir, "analysis_summary.txt")
    generate_summary(
        config,
        responders,
        non_responders,
        sig_mask,
        cluster_threshold,
        clusters,
        atlas_results,
        summary_path,
    )

    total = time.time() - t0
    log.info(
        "COMPLETE in %.1fs — %d sig clusters, %d sig voxels",
        total,
        len(sig_clusters),
        np.sum(sig_mask),
    )

    # Cleanup
    del responders, non_responders, p_values, t_statistics
    gc.collect()
    for h in log.handlers[:]:
        h.close()
        log.removeHandler(h)

    return GroupComparisonResult(
        success=True,
        output_dir=output_dir,
        n_responders=len(resp_ids),
        n_non_responders=len(non_resp_ids),
        n_significant_voxels=int(np.sum(sig_mask)),
        n_significant_clusters=len(sig_clusters),
        cluster_threshold=float(cluster_threshold),
        analysis_time=total,
        clusters=clusters,
        log_file=log_file,
    )


# ─── correlation ─────────────────────────────────────────────────────────


def run_correlation(
    config: CorrelationConfig,
    callback_handler=None,
    stop_callback=None,
) -> CorrelationResult:
    """Run cluster-based permutation testing for correlation (ACES-style).

    Parameters
    ----------
    config : CorrelationConfig
        Fully specified configuration.
    callback_handler : logging.Handler, optional
        GUI log handler.
    stop_callback : callable, optional
        Returns True to abort.
    """
    t0 = time.time()
    output_dir = _resolve_output_dir(
        "correlation",
        config.analysis_name,
    )
    log, log_file = _setup_logger(output_dir, "correlation", callback_handler)

    log.info("=" * 70)
    log.info("CORRELATION-BASED CLUSTER PERMUTATION TESTING (ACES-style)")
    log.info("=" * 70)
    log.info("Analysis: %s", config.analysis_name)
    log.info("Output:   %s", output_dir)
    log.info(
        "Config:   corr=%s  stat=%s  threshold=%.3f  perms=%d  alpha=%.3f  jobs=%d",
        config.correlation_type.value,
        config.cluster_stat.value,
        config.cluster_threshold,
        config.n_permutations,
        config.alpha,
        config.n_jobs,
    )

    # ── 1. Load data ─────────────────────────────────────────────────────
    log.info("[1/7] Loading subject data")
    step = time.time()

    subject_dicts = [
        {"subject_id": s.subject_id, "simulation_name": s.simulation_name}
        for s in config.subjects
    ]
    subject_data, template_img, subject_ids = load_group_data_ti_toolbox(
        subject_dicts,
        nifti_file_pattern=config.nifti_file_pattern,
        dtype=np.float32,
    )

    # Build effect sizes / weights aligned with loaded subjects
    config_lookup = {s.subject_id: s for s in config.subjects}
    effect_sizes = np.array(
        [config_lookup[sid].effect_size for sid in subject_ids],
        dtype=np.float64,
    )
    weights = None
    if config.use_weights:
        weights = np.array(
            [config_lookup[sid].weight for sid in subject_ids],
            dtype=np.float64,
        )

    n_subjects = len(subject_ids)
    log.info("Loaded %d subjects: %s", n_subjects, subject_ids)
    log.info(
        "Effect sizes: mean=%.3f, std=%.3f, range=[%.3f, %.3f]",
        np.mean(effect_sizes),
        np.std(effect_sizes),
        np.min(effect_sizes),
        np.max(effect_sizes),
    )
    log.info("Data shape: %s  (%.1fs)", subject_data.shape[:3], time.time() - step)

    if stop_callback and stop_callback():
        raise KeyboardInterrupt("Stopped by user")

    # ── 2. Voxelwise correlation ─────────────────────────────────────────
    log.info("[2/7] Voxelwise correlation")
    step = time.time()

    r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
        subject_data,
        effect_sizes,
        weights=weights,
        correlation_type=config.correlation_type.value,
        log=log,
    )

    log.info("Correlation computed in %.1fs", time.time() - step)

    if stop_callback and stop_callback():
        raise KeyboardInterrupt("Stopped by user")

    # ── 3. Permutation correction ────────────────────────────────────────
    log.info(
        "[3/7] Cluster-based permutation correction (%d perms)", config.n_permutations
    )
    step = time.time()

    perm_log_file = os.path.join(output_dir, "permutation_details.txt")

    engine = PermutationEngine(
        cluster_threshold=config.cluster_threshold,
        n_permutations=config.n_permutations,
        alpha=config.alpha,
        cluster_stat=config.cluster_stat.value,
        alternative="two-sided",
        n_jobs=config.n_jobs,
        log=log,
    )
    sig_mask, cluster_threshold, sig_clusters, null_dist, all_clusters, corr_data = (
        engine.correct_correlation(
            subject_data,
            effect_sizes,
            r_values=r_values,
            t_statistics=t_statistics,
            p_values=p_values,
            valid_mask=valid_mask,
            correlation_type=config.correlation_type.value,
            weights=weights,
            perm_log_file=perm_log_file,
            subject_ids=subject_ids,
        )
    )

    log.info(
        "Significant clusters: %d, voxels: %d  (%.1fs)",
        len(sig_clusters),
        np.sum(sig_mask),
        time.time() - step,
    )

    # ── 4. Cluster analysis ──────────────────────────────────────────────
    log.info("[4/7] Cluster analysis")
    clusters = cluster_analysis(sig_mask, template_img.affine, log=log)

    # Annotate with correlation stats
    from scipy.ndimage import label as scipy_label

    labeled, _ = scipy_label(sig_mask)
    for c in clusters:
        c_mask = labeled == c["cluster_id"]
        c["mean_r"] = float(np.mean(r_values[c_mask]))
        c["peak_r"] = float(np.max(r_values[c_mask]))

    # ── 5. Plots ─────────────────────────────────────────────────────────
    log.info("[5/7] Generating plots")
    perm_plot = os.path.join(output_dir, "permutation_null_distribution.pdf")
    plot_permutation_null_distribution(
        null_dist,
        cluster_threshold,
        all_clusters,
        perm_plot,
        alpha=config.alpha,
        cluster_stat=config.cluster_stat.value,
    )
    if len(corr_data["sizes"]) > 0:
        corr_plot = os.path.join(output_dir, "cluster_size_mass_correlation.pdf")
        plot_cluster_size_mass_correlation(
            corr_data["sizes"],
            corr_data["masses"],
            corr_plot,
        )

    # ── 6. Atlas overlap ─────────────────────────────────────────────────
    log.info("[6/7] Atlas overlap")
    atlas_results = {}
    if config.atlas_files:
        if _ATLAS_DIR.exists():
            atlas_results = atlas_overlap_analysis(
                sig_mask,
                config.atlas_files,
                str(_ATLAS_DIR),
                reference_img=template_img,
            )

    # ── 7. Save outputs ──────────────────────────────────────────────────
    log.info("[7/7] Saving results")

    _save_nifti(
        sig_mask.astype(np.uint8),
        template_img,
        os.path.join(output_dir, "significant_voxels_mask.nii.gz"),
    )
    _save_nifti(
        r_values.astype(np.float32),
        template_img,
        os.path.join(output_dir, "correlation_map.nii.gz"),
    )
    _save_nifti(
        t_statistics.astype(np.float32),
        template_img,
        os.path.join(output_dir, "t_statistics_map.nii.gz"),
    )

    log_p = -np.log10(p_values + 1e-10)
    log_p[~valid_mask] = 0
    _save_nifti(log_p, template_img, os.path.join(output_dir, "pvalues_map.nii.gz"))

    r_thresh = r_values.copy()
    r_thresh[sig_mask == 0] = 0
    _save_nifti(
        r_thresh.astype(np.float32),
        template_img,
        os.path.join(output_dir, "correlation_map_thresholded.nii.gz"),
    )

    avg = np.mean(subject_data, axis=-1).astype(np.float32)
    _save_nifti(avg, template_img, os.path.join(output_dir, "average_efield.nii.gz"))

    summary_path = os.path.join(output_dir, "analysis_summary.txt")
    generate_correlation_summary(
        config,
        subject_data,
        effect_sizes,
        r_values,
        sig_mask,
        cluster_threshold,
        clusters,
        atlas_results,
        summary_path,
        subject_ids=subject_ids,
        weights=weights,
    )

    total = time.time() - t0
    log.info(
        "COMPLETE in %.1fs — %d sig clusters, %d sig voxels",
        total,
        len(sig_clusters),
        np.sum(sig_mask),
    )

    # Cleanup
    del subject_data, effect_sizes, weights, t_statistics, p_values
    gc.collect()
    for h in log.handlers[:]:
        h.close()
        log.removeHandler(h)

    return CorrelationResult(
        success=True,
        output_dir=output_dir,
        n_subjects=n_subjects,
        n_significant_voxels=int(np.sum(sig_mask)),
        n_significant_clusters=len(sig_clusters),
        cluster_threshold=float(cluster_threshold),
        analysis_time=total,
        clusters=clusters,
        log_file=log_file,
    )
