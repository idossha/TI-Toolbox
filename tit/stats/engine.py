"""Core statistical computation engine for cluster-based permutation testing.

Functions:
- Voxelwise t-tests (paired / unpaired)
- Voxelwise correlations (Pearson / Spearman / weighted)
- Cluster-based permutation correction
- Cluster analysis (connected components + MNI mapping)
- P-value computation (MNE-style)

All orchestration functions accept an optional ``logger``.
If *None* the module-level logger (``tit.stats.engine``) is used.
"""

import gc
import logging
import multiprocessing

import numpy as np
from joblib import Parallel, delayed
from scipy import stats as sp_stats
from scipy.ndimage import label, sum as ndimage_sum
from scipy.stats import rankdata

logger = logging.getLogger(__name__)


# ─── p-value computation (MNE-style) ─────────────────────────────────────


def pval_from_histogram(observed_stats, null_distribution, tail=0):
    """Compute per-cluster p-values from a null distribution.

    Reference: Maris & Oostenveld (2007), MNE-Python implementation.
    """
    observed_stats = np.atleast_1d(observed_stats)
    null_distribution = np.asarray(null_distribution)

    if tail == -1:
        p_values = np.array(
            [np.mean(null_distribution <= obs) for obs in observed_stats]
        )
    elif tail == 1:
        p_values = np.array(
            [np.mean(null_distribution >= obs) for obs in observed_stats]
        )
    else:
        p_values = np.array(
            [
                np.mean(np.abs(null_distribution) >= np.abs(obs))
                for obs in observed_stats
            ]
        )
    return p_values


# ─── correlation (vectorised) ─────────────────────────────────────────────


def correlation(
    voxel_data,
    effect_sizes,
    correlation_type="pearson",
    weights=None,
    voxel_data_preranked=False,
):
    """Vectorised correlation for all voxels at once.

    Returns (r_values, t_values, p_values) – each shape ``(n_voxels,)``.
    """
    n_voxels, n_subjects = voxel_data.shape

    if correlation_type == "spearman":
        if not voxel_data_preranked:
            voxel_data = np.apply_along_axis(rankdata, 1, voxel_data)
        effect_sizes = rankdata(effect_sizes)

    if weights is None:
        x_mean = np.mean(voxel_data, axis=1, keepdims=True)
        y_mean = np.mean(effect_sizes)
        x_centered = voxel_data - x_mean
        y_centered = effect_sizes - y_mean
        cov_xy = np.sum(x_centered * y_centered, axis=1) / (n_subjects - 1)
        std_x = np.std(voxel_data, axis=1, ddof=1)
        std_y = np.std(effect_sizes, ddof=1)
    else:
        weights = np.asarray(weights, dtype=np.float64)
        weight_sum = np.sum(weights)
        x_mean = np.sum(weights * voxel_data, axis=1, keepdims=True) / weight_sum
        y_mean = np.sum(weights * effect_sizes) / weight_sum
        x_centered = voxel_data - x_mean
        y_centered = effect_sizes - y_mean
        cov_xy = np.sum(weights * x_centered * y_centered, axis=1) / weight_sum
        var_x = np.sum(weights * (x_centered**2), axis=1) / weight_sum
        var_y = np.sum(weights * (y_centered**2)) / weight_sum
        std_x = np.sqrt(var_x)
        std_y = np.sqrt(var_y)

    denom = std_x * std_y
    valid_mask = denom > 1e-10

    r_values = np.zeros(n_voxels)
    r_values[valid_mask] = cov_xy[valid_mask] / denom[valid_mask]
    r_values = np.clip(r_values, -1.0, 1.0)

    df = n_subjects - 2
    r_squared = r_values**2
    denom_t = 1 - r_squared
    denom_t[denom_t < 1e-10] = 1e-10
    t_values = r_values * np.sqrt(df / denom_t)
    p_values = 2 * sp_stats.t.sf(np.abs(t_values), df)

    return r_values, t_values, p_values


def correlation_voxelwise(
    subject_data,
    effect_sizes,
    weights=None,
    correlation_type="pearson",
    log=None,
):
    """Voxelwise correlation between E-field and continuous outcome (ACES-style).

    Returns (r_values, t_statistics, p_values, valid_mask) – each ``(x, y, z)``.
    """
    _log = log or logger
    n_subjects = subject_data.shape[-1]
    if len(effect_sizes) != n_subjects:
        raise ValueError(
            f"effect_sizes length ({len(effect_sizes)}) != n_subjects ({n_subjects})"
        )
    if weights is not None and len(weights) != n_subjects:
        raise ValueError(
            f"weights length ({len(weights)}) != n_subjects ({n_subjects})"
        )
    if n_subjects < 3:
        raise ValueError(f"Need >= 3 subjects for correlation, got {n_subjects}")

    effect_sizes = np.asarray(effect_sizes, dtype=np.float64)

    weight_str = " (weighted)" if weights is not None else ""
    _log.info(
        "Voxelwise %s correlation%s – %d subjects",
        correlation_type.capitalize(),
        weight_str,
        n_subjects,
    )

    shape = subject_data.shape[:3]
    r_values = np.zeros(shape)
    t_statistics = np.zeros(shape)
    p_values = np.ones(shape)

    valid_mask = np.any(subject_data > 0, axis=-1)
    valid_coords = np.argwhere(valid_mask)
    n_valid = len(valid_coords)
    _log.info("Valid voxels: %d", n_valid)

    voxel_data = np.zeros((n_valid, n_subjects), dtype=np.float64)
    for idx, (i, j, k) in enumerate(valid_coords):
        voxel_data[idx, :] = subject_data[i, j, k, :]

    r_1d, t_1d, p_1d = correlation(
        voxel_data, effect_sizes, correlation_type=correlation_type, weights=weights
    )

    for idx, (i, j, k) in enumerate(valid_coords):
        r_values[i, j, k] = r_1d[idx]
        t_statistics[i, j, k] = t_1d[idx]
        p_values[i, j, k] = p_1d[idx]

    _log.info(
        "r range [%.4f, %.4f], mean |r| %.4f",
        np.min(r_values[valid_mask]),
        np.max(r_values[valid_mask]),
        np.mean(np.abs(r_values[valid_mask])),
    )
    _log.info(
        "Uncorrected p<0.05: %d,  p<0.01: %d",
        np.sum((p_values < 0.05) & valid_mask),
        np.sum((p_values < 0.01) & valid_mask),
    )

    return r_values, t_statistics, p_values, valid_mask


# ─── t-tests (vectorised) ────────────────────────────────────────────────


def ttest_ind(test_data, n_resp, n_non_resp, alternative="two-sided"):
    """Vectorised independent-samples t-test. Returns (t_stats, p_values)."""
    resp_data = test_data[:, :n_resp]
    non_resp_data = test_data[:, n_resp:]

    resp_means = np.mean(resp_data, axis=1)
    non_resp_means = np.mean(non_resp_data, axis=1)
    resp_vars = np.var(resp_data, axis=1, ddof=1)
    non_resp_vars = np.var(non_resp_data, axis=1, ddof=1)

    numerator = (n_resp - 1) * resp_vars + (n_non_resp - 1) * non_resp_vars
    denominator = n_resp + n_non_resp - 2
    pooled_vars = numerator / denominator

    se_diff = np.sqrt(pooled_vars * (1 / n_resp + 1 / n_non_resp))
    valid = se_diff > 0
    t_stats = np.zeros(test_data.shape[0])
    t_stats[valid] = (resp_means[valid] - non_resp_means[valid]) / se_diff[valid]

    df = n_resp + n_non_resp - 2
    if alternative == "two-sided":
        p_values = 2 * sp_stats.t.sf(np.abs(t_stats), df)
    elif alternative == "greater":
        p_values = sp_stats.t.sf(t_stats, df)
    elif alternative == "less":
        p_values = sp_stats.t.sf(-t_stats, df)
    else:
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def ttest_rel(test_data, n_resp, alternative="two-sided"):
    """Vectorised paired-samples t-test. Returns (t_stats, p_values)."""
    resp_data = test_data[:, :n_resp]
    non_resp_data = test_data[:, n_resp:]

    diff = resp_data - non_resp_data
    diff_means = np.mean(diff, axis=1)
    diff_stds = np.std(diff, axis=1, ddof=1)

    valid = diff_stds > 0
    t_stats = np.zeros(test_data.shape[0])
    se = diff_stds / np.sqrt(n_resp)
    t_stats[valid] = diff_means[valid] / se[valid]

    df = n_resp - 1
    if alternative == "two-sided":
        p_values = 2 * sp_stats.t.sf(np.abs(t_stats), df)
    elif alternative == "greater":
        p_values = sp_stats.t.sf(t_stats, df)
    elif alternative == "less":
        p_values = sp_stats.t.sf(-t_stats, df)
    else:
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def ttest_voxelwise(
    responders,
    non_responders,
    test_type="unpaired",
    alternative="two-sided",
    log=None,
):
    """Voxelwise t-test. Returns (p_values, t_statistics, valid_mask)."""
    _log = log or logger

    if test_type not in ("paired", "unpaired"):
        raise ValueError("test_type must be 'paired' or 'unpaired'")

    if test_type == "paired" and responders.shape[-1] != non_responders.shape[-1]:
        raise ValueError(
            f"Paired test requires equal sample sizes: "
            f"{responders.shape[-1]} vs {non_responders.shape[-1]}"
        )

    test_name = "Paired" if test_type == "paired" else "Unpaired"
    _log.info("Voxelwise %s t-test (alternative=%s)", test_name, alternative)

    shape = responders.shape[:3]
    p_values = np.ones(shape)
    t_statistics = np.zeros(shape)

    valid_mask = np.any(responders > 0, axis=-1) | np.any(non_responders > 0, axis=-1)
    valid_coords = np.argwhere(valid_mask)
    _log.info("Valid voxels: %d", len(valid_coords))

    n_resp = responders.shape[-1]
    n_non_resp = non_responders.shape[-1]

    idx_i, idx_j, idx_k = valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]
    resp_extracted = responders[idx_i, idx_j, idx_k, :].astype(np.float32)
    non_resp_extracted = non_responders[idx_i, idx_j, idx_k, :].astype(np.float32)
    voxel_data = np.concatenate([resp_extracted, non_resp_extracted], axis=1)

    if test_type == "paired":
        t_1d, p_1d = ttest_rel(voxel_data, n_resp, alternative=alternative)
    else:
        t_1d, p_1d = ttest_ind(voxel_data, n_resp, n_non_resp, alternative=alternative)

    t_statistics[idx_i, idx_j, idx_k] = t_1d
    p_values[idx_i, idx_j, idx_k] = p_1d

    return p_values, t_statistics, valid_mask


# ─── single permutation workers (called in parallel) ─────────────────────


def _run_single_permutation(
    test_data,
    test_coords,
    n_resp,
    n_total,
    cluster_threshold,
    valid_mask,
    p_values_shape,
    test_type="unpaired",
    alternative="two-sided",
    cluster_stat="size",
    seed=None,
    return_indices=False,
):
    if seed is not None:
        np.random.seed(seed)

    perm_idx = None

    if test_type == "paired":
        perm_test_data = test_data.copy()
        resp_data = test_data[:, :n_resp]
        non_resp_data = test_data[:, n_resp:]
        sign_flips = np.random.choice([-1, 1], size=n_resp)
        if return_indices:
            perm_idx = sign_flips
        n_voxels = test_data.shape[0]
        for i in range(n_voxels):
            mean_pair = (resp_data[i, :] + non_resp_data[i, :]) / 2
            diff_pair = (resp_data[i, :] - non_resp_data[i, :]) / 2
            perm_test_data[i, :n_resp] = mean_pair + sign_flips * diff_pair
            perm_test_data[i, n_resp:] = mean_pair - sign_flips * diff_pair
    else:
        perm_indices = np.random.permutation(n_total)
        if return_indices:
            perm_idx = perm_indices
        perm_test_data = test_data[:, perm_indices]

    perm_p = np.ones(p_values_shape)
    perm_t = np.zeros(p_values_shape)

    if test_type == "paired":
        t_1d, p_1d = ttest_rel(perm_test_data, n_resp, alternative=alternative)
    else:
        t_1d, p_1d = ttest_ind(
            perm_test_data, n_resp, n_total - n_resp, alternative=alternative
        )

    idx_i, idx_j, idx_k = test_coords[:, 0], test_coords[:, 1], test_coords[:, 2]
    perm_t[idx_i, idx_j, idx_k] = t_1d
    perm_p[idx_i, idx_j, idx_k] = p_1d

    perm_mask = (perm_p < cluster_threshold) & valid_mask
    perm_labeled, perm_n = label(perm_mask)

    max_cluster_stat = max_cluster_size = max_cluster_mass = 0
    if perm_n > 0:
        sizes = np.bincount(perm_labeled.ravel(), minlength=perm_n + 1)[1:]
        masses = ndimage_sum(perm_t, perm_labeled, index=np.arange(1, perm_n + 1))
        multi = sizes > 1
        if np.any(multi):
            max_cluster_size = int(sizes[multi].max())
            max_cluster_mass = float(np.asarray(masses)[multi].max())
            max_cluster_stat = (
                max_cluster_size if cluster_stat == "size" else max_cluster_mass
            )

    if return_indices:
        return max_cluster_stat, perm_idx, max_cluster_size, max_cluster_mass
    return max_cluster_stat, max_cluster_size, max_cluster_mass


def _run_single_correlation_permutation(
    voxel_data,
    effect_sizes,
    valid_coords,
    cluster_threshold,
    valid_mask,
    shape,
    correlation_type="pearson",
    weights=None,
    cluster_stat="mass",
    alternative="two-sided",
    seed=None,
    return_indices=False,
    voxel_data_preranked=False,
):
    if seed is not None:
        np.random.seed(seed)

    n_subjects = len(effect_sizes)
    perm_idx = np.random.permutation(n_subjects)
    perm_effect = effect_sizes[perm_idx]
    perm_weights = weights[perm_idx] if weights is not None else None

    perm_r, perm_t, perm_p = correlation(
        voxel_data,
        perm_effect,
        correlation_type=correlation_type,
        weights=perm_weights,
        voxel_data_preranked=voxel_data_preranked,
    )

    perm_p_vol = np.ones(shape)
    perm_t_vol = np.zeros(shape)
    idx_i, idx_j, idx_k = valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]
    perm_p_vol[idx_i, idx_j, idx_k] = perm_p
    perm_t_vol[idx_i, idx_j, idx_k] = perm_t

    if alternative == "greater":
        perm_mask = (perm_p_vol < cluster_threshold) & valid_mask & (perm_t_vol > 0)
    elif alternative == "less":
        perm_mask = (perm_p_vol < cluster_threshold) & valid_mask & (perm_t_vol < 0)
    else:
        perm_mask = (perm_p_vol < cluster_threshold) & valid_mask

    perm_labeled, perm_n = label(perm_mask)

    max_cluster_stat = max_cluster_size = max_cluster_mass = 0
    if perm_n > 0:
        sizes = np.bincount(perm_labeled.ravel(), minlength=perm_n + 1)[1:]
        masses = ndimage_sum(perm_t_vol, perm_labeled, index=np.arange(1, perm_n + 1))
        multi = sizes > 1
        if np.any(multi):
            max_cluster_size = int(sizes[multi].max())
            max_cluster_mass = float(np.asarray(masses)[multi].max())
            max_cluster_stat = (
                max_cluster_size if cluster_stat == "size" else max_cluster_mass
            )

    if return_indices:
        return max_cluster_stat, perm_idx, max_cluster_size, max_cluster_mass
    return max_cluster_stat, max_cluster_size, max_cluster_mass


# ─── cluster-based permutation correction (group comparison) ─────────────


def cluster_based_correction(
    responders,
    non_responders,
    p_values,
    valid_mask,
    cluster_threshold=0.01,
    n_permutations=500,
    alpha=0.05,
    test_type="unpaired",
    alternative="two-sided",
    cluster_stat="mass",
    t_statistics=None,
    n_jobs=-1,
    log=None,
    save_permutation_log=False,
    permutation_log_file=None,
    subject_ids_resp=None,
    subject_ids_non_resp=None,
):
    """Cluster-based permutation correction for group comparison.

    Returns ``(sig_mask, threshold, sig_clusters, null_dist, observed_clusters,
    correlation_data)``.
    """
    from .io_utils import save_permutation_details

    _log = log or logger

    if cluster_stat == "mass" and t_statistics is None:
        raise ValueError("t_statistics required when cluster_stat='mass'")

    _log.info(
        "Cluster-based permutation correction (%s, %s)", cluster_stat, alternative
    )

    initial_mask = (p_values < cluster_threshold) & valid_mask
    labeled_array, n_clusters = label(initial_mask)
    _log.info("Clusters at p<%.3f (uncorrected): %d", cluster_threshold, n_clusters)

    empty = {"sizes": np.array([]), "masses": np.array([])}
    if n_clusters == 0:
        _log.warning("No clusters found. Consider increasing cluster_threshold.")
        return np.zeros_like(p_values, dtype=int), 0, [], np.array([]), [], empty

    # Pre-extract voxel data
    all_data = np.concatenate([responders, non_responders], axis=-1)
    n_resp = responders.shape[-1]
    n_total = n_resp + non_responders.shape[-1]

    test_coords = np.argwhere(valid_mask)
    n_test = len(test_coords)
    _log.info("Pre-extracting %d voxels, %d subjects", n_test, n_total)

    test_data = np.zeros((n_test, n_total), dtype=np.float32)
    for idx, (i, j, k) in enumerate(test_coords):
        test_data[idx, :] = all_data[i, j, k, :].astype(np.float32)
    del all_data
    gc.collect()

    _log.info("Test data: %.1f MB", test_data.nbytes / (1024**2))

    actual_jobs = multiprocessing.cpu_count() if n_jobs == -1 else n_jobs
    _log.info("Running %d permutations on %d cores", n_permutations, actual_jobs)

    seeds = np.random.randint(0, 2**31, size=n_permutations)
    track = (
        save_permutation_log
        and subject_ids_resp is not None
        and subject_ids_non_resp is not None
    )

    if actual_jobs == 1:
        results = [
            _run_single_permutation(
                test_data,
                test_coords,
                n_resp,
                n_total,
                cluster_threshold,
                valid_mask,
                p_values.shape,
                test_type=test_type,
                alternative=alternative,
                cluster_stat=cluster_stat,
                seed=seeds[i],
                return_indices=track,
            )
            for i in range(n_permutations)
        ]
    else:
        results = Parallel(n_jobs=actual_jobs, verbose=0)(
            delayed(_run_single_permutation)(
                test_data,
                test_coords,
                n_resp,
                n_total,
                cluster_threshold,
                valid_mask,
                p_values.shape,
                test_type=test_type,
                alternative=alternative,
                cluster_stat=cluster_stat,
                seed=seeds[i],
                return_indices=track,
            )
            for i in range(n_permutations)
        )
        gc.collect()

    del test_data
    gc.collect()

    if track:
        null_stats = np.array([r[0] for r in results])
        perm_indices = [r[1] for r in results]
        null_sizes = [r[2] for r in results]
        null_masses = [r[3] for r in results]
    else:
        null_stats = np.array([r[0] for r in results])
        perm_indices = None
        null_sizes = [r[1] for r in results]
        null_masses = [r[2] for r in results]

    # Determine threshold
    sorted_null = np.sort(null_stats)[::-1]
    ti = max(1, min(int(alpha * n_permutations), len(sorted_null)))
    cluster_stat_threshold = sorted_null[ti - 1]

    stat_unit = "voxels" if cluster_stat == "size" else "mass units"
    _log.info(
        "Threshold (p<%.3f): %.2f %s  " "(null min=%.2f, mean=%.2f, max=%.2f)",
        alpha,
        cluster_stat_threshold,
        stat_unit,
        np.min(null_stats),
        np.mean(null_stats),
        np.max(null_stats),
    )

    if save_permutation_log and perm_indices is not None:
        pf = permutation_log_file or "permutation_details.txt"
        info = [
            {
                "perm_num": i,
                "perm_idx": perm_indices[i],
                "max_cluster_size": null_stats[i],
            }
            for i in range(n_permutations)
        ]
        save_permutation_details(info, pf, subject_ids_resp, subject_ids_non_resp)
        _log.info("Permutation log saved: %s", pf)

    # Identify significant clusters (MNE-style per-cluster p-values)
    sig_mask, sig_clusters, all_observed = _identify_significant_clusters(
        labeled_array,
        n_clusters,
        t_statistics,
        null_stats,
        cluster_stat,
        alpha,
        alternative,
        _log,
    )

    _log.info(
        "Significant: %d clusters, %d voxels", len(sig_clusters), np.sum(sig_mask)
    )

    correlation_data = {
        "sizes": np.array(null_sizes),
        "masses": np.array(null_masses),
    }
    return (
        sig_mask,
        cluster_stat_threshold,
        sig_clusters,
        null_stats,
        all_observed,
        correlation_data,
    )


# ─── cluster-based permutation correction (correlation) ──────────────────


def correlation_cluster_correction(
    subject_data,
    effect_sizes,
    r_values,
    t_statistics,
    p_values,
    valid_mask,
    weights=None,
    correlation_type="pearson",
    cluster_threshold=0.05,
    n_permutations=1000,
    alpha=0.05,
    cluster_stat="mass",
    alternative="two-sided",
    n_jobs=-1,
    log=None,
    save_permutation_log=False,
    permutation_log_file=None,
    subject_ids=None,
):
    """Cluster-based permutation correction for correlation analysis (ACES-style).

    Returns ``(sig_mask, threshold, sig_clusters, null_dist, observed_clusters,
    correlation_data)``.
    """
    from .io_utils import save_permutation_details

    _log = log or logger
    effect_sizes = np.asarray(effect_sizes, dtype=np.float64)
    n_subjects = len(effect_sizes)

    _log.info(
        "Correlation cluster correction (%s, %s, %s)",
        correlation_type,
        cluster_stat,
        alternative,
    )

    # Form initial clusters based on alternative
    if alternative == "greater":
        initial_mask = (p_values < cluster_threshold) & valid_mask & (t_statistics > 0)
    elif alternative == "less":
        initial_mask = (p_values < cluster_threshold) & valid_mask & (t_statistics < 0)
    else:
        initial_mask = (p_values < cluster_threshold) & valid_mask

    labeled_array, n_clusters = label(initial_mask)
    _log.info("Clusters at p<%.3f: %d", cluster_threshold, n_clusters)

    empty = {"sizes": np.array([]), "masses": np.array([])}
    if n_clusters == 0:
        _log.warning("No clusters found.")
        return np.zeros_like(p_values, dtype=int), 0, [], np.array([]), [], empty

    # Pre-extract voxel data
    valid_coords = np.argwhere(valid_mask)
    n_valid = len(valid_coords)
    voxel_data = np.zeros((n_valid, n_subjects), dtype=np.float64)
    for idx, (i, j, k) in enumerate(valid_coords):
        voxel_data[idx, :] = subject_data[i, j, k, :]

    # Pre-rank for Spearman
    preranked = False
    if correlation_type == "spearman":
        _log.info("Pre-ranking voxel data for Spearman (%d voxels)", n_valid)
        voxel_data = np.apply_along_axis(rankdata, 1, voxel_data)
        preranked = True

    actual_jobs = multiprocessing.cpu_count() if n_jobs == -1 else n_jobs
    _log.info("Running %d permutations on %d cores", n_permutations, actual_jobs)

    seeds = np.random.randint(0, 2**31, size=n_permutations)
    track = save_permutation_log and subject_ids is not None

    if actual_jobs == 1:
        results = [
            _run_single_correlation_permutation(
                voxel_data,
                effect_sizes,
                valid_coords,
                cluster_threshold,
                valid_mask,
                p_values.shape,
                correlation_type=correlation_type,
                weights=weights,
                cluster_stat=cluster_stat,
                alternative=alternative,
                seed=seeds[i],
                return_indices=track,
                voxel_data_preranked=preranked,
            )
            for i in range(n_permutations)
        ]
    else:
        results = Parallel(n_jobs=actual_jobs, verbose=0)(
            delayed(_run_single_correlation_permutation)(
                voxel_data,
                effect_sizes,
                valid_coords,
                cluster_threshold,
                valid_mask,
                p_values.shape,
                correlation_type=correlation_type,
                weights=weights,
                cluster_stat=cluster_stat,
                alternative=alternative,
                seed=seeds[i],
                return_indices=track,
                voxel_data_preranked=preranked,
            )
            for i in range(n_permutations)
        )
        gc.collect()

    del voxel_data
    gc.collect()

    if track:
        null_stats = np.array([r[0] for r in results])
        null_sizes = [r[2] for r in results]
        null_masses = [r[3] for r in results]
    else:
        null_stats = np.array([r[0] for r in results])
        null_sizes = [r[1] for r in results]
        null_masses = [r[2] for r in results]

    sorted_null = np.sort(null_stats)[::-1]
    ti = max(1, min(int(alpha * n_permutations), len(sorted_null)))
    cluster_stat_threshold = sorted_null[ti - 1]

    stat_unit = "voxels" if cluster_stat == "size" else "mass units"
    _log.info(
        "Threshold (p<%.3f): %.2f %s  " "(null min=%.2f, mean=%.2f, max=%.2f)",
        alpha,
        cluster_stat_threshold,
        stat_unit,
        np.min(null_stats),
        np.mean(null_stats),
        np.max(null_stats),
    )

    # Identify significant clusters
    sig_mask, sig_clusters, all_observed = _identify_significant_clusters(
        labeled_array,
        n_clusters,
        t_statistics,
        null_stats,
        cluster_stat,
        alpha,
        alternative,
        _log,
        r_values=r_values,
    )

    _log.info(
        "Significant: %d clusters, %d voxels", len(sig_clusters), np.sum(sig_mask)
    )

    correlation_data = {
        "sizes": np.array(null_sizes),
        "masses": np.array(null_masses),
    }
    return (
        sig_mask,
        cluster_stat_threshold,
        sig_clusters,
        null_stats,
        all_observed,
        correlation_data,
    )


# ─── shared: identify significant clusters ───────────────────────────────


def _identify_significant_clusters(
    labeled_array,
    n_clusters,
    t_statistics,
    null_stats,
    cluster_stat,
    alpha,
    alternative,
    _log,
    r_values=None,
):
    """Post-permutation cluster identification (shared by both workflows)."""
    max_check = min(n_clusters, 10000)

    cluster_labels_flat = labeled_array.ravel()
    sizes_all = np.bincount(cluster_labels_flat, minlength=n_clusters + 1)

    if cluster_stat == "mass":
        masses_all = ndimage_sum(
            t_statistics, labeled_array, index=np.arange(1, n_clusters + 1)
        )

    cluster_info = []
    stat_values = []

    for cid in range(1, max_check + 1):
        size = int(sizes_all[cid])
        if size <= 1:
            continue
        if cluster_stat == "size":
            sv = float(size)
        else:
            sv = float(masses_all[cid - 1])
        cluster_info.append({"id": cid, "size": size, "stat_value": sv})
        stat_values.append(sv)

    sig_mask = np.zeros(labeled_array.shape, dtype=int)
    sig_clusters = []
    all_observed = []

    if stat_values:
        stat_values = np.array(stat_values)
        tail = {"greater": 1, "less": -1}.get(alternative, 0)
        pvals = pval_from_histogram(stat_values, null_stats, tail=tail)

        for i, info in enumerate(cluster_info[:10]):
            all_observed.append(
                {
                    "id": info["id"],
                    "size": info["size"],
                    "stat_value": info["stat_value"],
                    "p_value": float(pvals[i]),
                }
            )

        _log.info("Top clusters:")
        for obs in all_observed[:5]:
            status = "SIG" if obs["p_value"] < alpha else "ns"
            _log.info(
                "  Cluster %d: %s=%.2f, size=%d, p=%.4f (%s)",
                obs["id"],
                cluster_stat,
                obs["stat_value"],
                obs["size"],
                obs["p_value"],
                status,
            )

        for i, info in enumerate(cluster_info):
            if pvals[i] < alpha:
                coords = np.where(labeled_array == info["id"])
                sig_mask[coords] = 1
                entry = {
                    "id": info["id"],
                    "size": info["size"],
                    "stat_value": info["stat_value"],
                    "p_value": float(pvals[i]),
                }
                if r_values is not None:
                    entry["peak_r"] = float(np.max(r_values[coords]))
                    entry["mean_r"] = float(np.mean(r_values[coords]))
                sig_clusters.append(entry)

    return sig_mask, sig_clusters, all_observed


# ─── cluster analysis ────────────────────────────────────────────────────


def cluster_analysis(sig_mask, affine, log=None):
    """Connected-component analysis with MNI coordinate mapping.

    Returns a list of cluster dicts sorted by size (descending).
    """
    import nibabel as nib

    _log = log or logger
    labeled_array, num_clusters = label(sig_mask)

    if num_clusters == 0:
        _log.info("No clusters found in significance mask")
        return []

    clusters = []
    for cid in range(1, num_clusters + 1):
        coords = np.argwhere(labeled_array == cid)
        com_voxel = np.mean(coords, axis=0)
        com_mni = nib.affines.apply_affine(affine, com_voxel)
        clusters.append(
            {
                "cluster_id": cid,
                "size": len(coords),
                "center_voxel": com_voxel,
                "center_mni": com_mni,
            }
        )

    clusters.sort(key=lambda c: c["size"], reverse=True)

    _log.info("Found %d clusters", num_clusters)
    for c in clusters[:10]:
        _log.info(
            "  Cluster %d: %d voxels, MNI (%.1f, %.1f, %.1f)",
            c["cluster_id"],
            c["size"],
            c["center_mni"][0],
            c["center_mni"][1],
            c["center_mni"][2],
        )

    return clusters
