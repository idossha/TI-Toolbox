"""
Statistical analysis utilities for neuroimaging

This module contains functions for:
- T-tests (paired and unpaired)
- Correlations (Pearson, Spearman, weighted)
- Cluster-based permutation correction
- Cluster analysis
"""

import numpy as np
from scipy import stats
from scipy.ndimage import label
from scipy.stats import rankdata
from tqdm import tqdm

from joblib import Parallel, delayed
import multiprocessing
import gc


# ==============================================================================
# P-VALUE COMPUTATION (MNE-style)
# ==============================================================================


def pval_from_histogram(observed_stats, null_distribution, tail=0):
    """
    Compute p-values from observed statistics given a null distribution.

    This follows MNE-Python's approach where p-values are computed as the
    proportion of null distribution values that are as extreme or more extreme
    than the observed statistic.

    Parameters:
    -----------
    observed_stats : array-like
        Observed cluster statistics (one per cluster)
    null_distribution : ndarray
        Null distribution of maximum cluster statistics from permutations
    tail : int
        Tail of the test:
        * 0: two-sided (default) - test |observed| >= |null|
        * 1: upper tail - test observed >= null (for positive effects)
        * -1: lower tail - test observed <= null (for negative effects)

    Returns:
    --------
    p_values : ndarray
        P-value for each observed statistic

    Notes:
    ------
    This is more accurate than using a single percentile threshold because
    it provides a p-value for each cluster rather than a binary decision.

    Reference: Maris & Oostenveld (2007), MNE-Python implementation
    """
    observed_stats = np.atleast_1d(observed_stats)
    null_distribution = np.asarray(null_distribution)

    if tail == -1:  # lower tail (negative effects)
        # Proportion of null values <= observed
        p_values = np.array(
            [np.mean(null_distribution <= obs) for obs in observed_stats]
        )
    elif tail == 1:  # upper tail (positive effects)
        # Proportion of null values >= observed
        p_values = np.array(
            [np.mean(null_distribution >= obs) for obs in observed_stats]
        )
    else:  # two-sided (tail == 0)
        # Proportion of |null| >= |observed|
        p_values = np.array(
            [
                np.mean(np.abs(null_distribution) >= np.abs(obs))
                for obs in observed_stats
            ]
        )

    return p_values


# ==============================================================================
# CORRELATION FUNCTIONS (for continuous outcome analysis)
# ==============================================================================


def correlation(
    voxel_data,
    effect_sizes,
    correlation_type="pearson",
    weights=None,
    voxel_data_preranked=False,
):
    """
    Vectorized computation of correlations for all voxels at once.

    Computes the correlation between electric field magnitude at each voxel
    and a continuous outcome measure (e.g., behavioral effect size).

    Parameters:
    -----------
    voxel_data : ndarray, shape (n_voxels, n_subjects)
        Electric field magnitude data for all voxels and subjects
    effect_sizes : ndarray, shape (n_subjects,)
        Continuous outcome measure for each subject
    correlation_type : {'pearson', 'spearman'}, optional
        Type of correlation to compute (default: 'pearson')
    weights : ndarray, shape (n_subjects,), optional
        Weights for each subject (e.g., sample size for meta-analysis)
        If None, all subjects are weighted equally
    voxel_data_preranked : bool, optional
        If True and correlation_type='spearman', assumes voxel_data is already ranked.
        This optimization is used during permutation testing where voxel_data doesn't change.
        (default: False)

    Returns:
    --------
    r_values : ndarray, shape (n_voxels,)
        Correlation coefficients for all voxels
    t_values : ndarray, shape (n_voxels,)
        Studentized correlation coefficients (t-statistics)
    p_values : ndarray, shape (n_voxels,)
        P-values for all voxels (two-sided)
    """
    n_voxels, n_subjects = voxel_data.shape

    # For Spearman, convert to ranks (skip if already pre-ranked)
    if correlation_type == "spearman":
        # Rank voxel data only if not already ranked
        if not voxel_data_preranked:
            # Rank data along subject dimension (with fractional ranking for ties)
            voxel_data = np.apply_along_axis(rankdata, 1, voxel_data)
        # Always rank effect sizes (they change in permutations)
        effect_sizes = rankdata(effect_sizes)

    if weights is None:
        # Unweighted Pearson correlation
        # Compute means
        x_mean = np.mean(voxel_data, axis=1, keepdims=True)  # (n_voxels, 1)
        y_mean = np.mean(effect_sizes)

        # Center data
        x_centered = voxel_data - x_mean  # (n_voxels, n_subjects)
        y_centered = effect_sizes - y_mean  # (n_subjects,)

        # Compute covariance and standard deviations
        cov_xy = np.sum(x_centered * y_centered, axis=1) / (
            n_subjects - 1
        )  # (n_voxels,)
        std_x = np.std(voxel_data, axis=1, ddof=1)  # (n_voxels,)
        std_y = np.std(effect_sizes, ddof=1)

    else:
        # Weighted Pearson correlation (as per ACES)
        # Normalize weights
        weights = np.asarray(weights, dtype=np.float64)
        weight_sum = np.sum(weights)

        # Weighted means: m(x; N) = sum(N_i * x_i) / sum(N_i)
        x_mean = (
            np.sum(weights * voxel_data, axis=1, keepdims=True) / weight_sum
        )  # (n_voxels, 1)
        y_mean = np.sum(weights * effect_sizes) / weight_sum

        # Center data
        x_centered = voxel_data - x_mean
        y_centered = effect_sizes - y_mean

        # Weighted covariance: cov(x,y; N) = sum(N_i * (x_i - m(x)) * (y_i - m(y))) / sum(N_i)
        cov_xy = (
            np.sum(weights * x_centered * y_centered, axis=1) / weight_sum
        )  # (n_voxels,)

        # Weighted variance for std computation
        var_x = np.sum(weights * (x_centered**2), axis=1) / weight_sum  # (n_voxels,)
        var_y = np.sum(weights * (y_centered**2)) / weight_sum

        std_x = np.sqrt(var_x)
        std_y = np.sqrt(var_y)

    # Compute correlation: r = cov(x,y) / (std_x * std_y)
    # Avoid division by zero
    denom = std_x * std_y
    valid_mask = denom > 1e-10

    r_values = np.zeros(n_voxels)
    r_values[valid_mask] = cov_xy[valid_mask] / denom[valid_mask]

    # Clip to [-1, 1] to handle numerical issues
    r_values = np.clip(r_values, -1.0, 1.0)

    # Compute studentized correlation coefficient (t-statistic)
    # t = r * sqrt((n-2) / (1-r^2))
    df = n_subjects - 2
    r_squared = r_values**2

    # Avoid division by zero when r = ±1
    denom_t = 1 - r_squared
    denom_t[denom_t < 1e-10] = 1e-10

    t_values = r_values * np.sqrt(df / denom_t)

    # Compute two-sided p-values from t-distribution
    p_values = 2 * stats.t.sf(np.abs(t_values), df)

    return r_values, t_values, p_values


def correlation_voxelwise(
    subject_data, effect_sizes, weights=None, correlation_type="pearson", verbose=True
):
    """
    Perform vectorized correlation at each voxel between electric field
    magnitude and continuous outcome measure.

    This implements the ACES (Automated Correlation of Electric field
    strength and Stimulation effect) approach for continuous outcomes.

    Parameters:
    -----------
    subject_data : ndarray (x, y, z, n_subjects)
        Electric field magnitude data for all subjects
    effect_sizes : ndarray (n_subjects,)
        Continuous outcome measure for each subject (e.g., effect size,
        % improvement, behavioral score)
    weights : ndarray (n_subjects,), optional
        Weights for each subject (e.g., sample size for meta-analysis)
    correlation_type : {'pearson', 'spearman'}, optional
        Type of correlation (default: 'pearson')
    verbose : bool
        Print progress information

    Returns:
    --------
    r_values : ndarray (x, y, z)
        Correlation coefficient at each voxel
    t_statistics : ndarray (x, y, z)
        Studentized correlation (t-statistic) at each voxel
    p_values : ndarray (x, y, z)
        P-value at each voxel
    valid_mask : ndarray (x, y, z)
        Boolean mask of valid voxels
    """
    if verbose:
        weight_str = " (weighted)" if weights is not None else ""
        print(
            f"\nPerforming voxelwise {correlation_type.capitalize()} correlation{weight_str} (vectorized)..."
        )

    # Validate inputs
    n_subjects = subject_data.shape[-1]
    if len(effect_sizes) != n_subjects:
        raise ValueError(
            f"Number of effect sizes ({len(effect_sizes)}) must match "
            f"number of subjects ({n_subjects})"
        )

    if weights is not None and len(weights) != n_subjects:
        raise ValueError(
            f"Number of weights ({len(weights)}) must match "
            f"number of subjects ({n_subjects})"
        )

    if n_subjects < 3:
        raise ValueError(f"Need at least 3 subjects for correlation, got {n_subjects}")

    effect_sizes = np.asarray(effect_sizes, dtype=np.float64)

    shape = subject_data.shape[:3]
    r_values = np.zeros(shape)
    t_statistics = np.zeros(shape)
    p_values = np.ones(shape)

    # Create mask of valid voxels (non-zero in at least some subjects)
    valid_mask = np.any(subject_data > 0, axis=-1)
    total_voxels = np.sum(valid_mask)

    if verbose:
        print(f"Computing correlations for {total_voxels} valid voxels...")

    # Get coordinates of valid voxels
    valid_coords = np.argwhere(valid_mask)
    n_valid = len(valid_coords)

    # Pre-extract voxel data for vectorized computation
    voxel_data = np.zeros((n_valid, n_subjects), dtype=np.float64)
    for idx, coord in enumerate(valid_coords):
        i, j, k = coord
        voxel_data[idx, :] = subject_data[i, j, k, :]

    # Compute correlations for all voxels at once
    r_1d, t_1d, p_1d = correlation(
        voxel_data, effect_sizes, correlation_type=correlation_type, weights=weights
    )

    # Map results back to 3D volume
    for idx, coord in enumerate(valid_coords):
        i, j, k = coord
        r_values[i, j, k] = r_1d[idx]
        t_statistics[i, j, k] = t_1d[idx]
        p_values[i, j, k] = p_1d[idx]

    if verbose:
        print(
            f"Correlation range: [{np.min(r_values[valid_mask]):.4f}, {np.max(r_values[valid_mask]):.4f}]"
        )
        print(f"Mean |r|: {np.mean(np.abs(r_values[valid_mask])):.4f}")
        sig_05 = np.sum((p_values < 0.05) & valid_mask)
        sig_01 = np.sum((p_values < 0.01) & valid_mask)
        print(f"Voxels with p<0.05 (uncorrected): {sig_05}")
        print(f"Voxels with p<0.01 (uncorrected): {sig_01}")

    return r_values, t_statistics, p_values, valid_mask


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
    """
    Helper function to run a single correlation permutation (for parallel processing)

    Parameters:
    -----------
    voxel_data : ndarray, shape (n_voxels, n_subjects)
        Pre-extracted voxel data (may be pre-ranked if correlation_type='spearman')
    effect_sizes : ndarray, shape (n_subjects,)
        Continuous outcome measure
    valid_coords : ndarray
        Coordinates of valid voxels
    cluster_threshold : float
        P-value threshold for cluster formation
    valid_mask : ndarray
        Boolean mask of valid voxels
    shape : tuple
        Shape of 3D volume
    correlation_type : str
        'pearson' or 'spearman'
    weights : ndarray, optional
        Subject weights (weights are NOT shuffled - only effect sizes)
    cluster_stat : str
        'size' or 'mass'
    alternative : {'two-sided', 'greater', 'less'}, optional
        Alternative hypothesis for correlation testing
    seed : int, optional
        Random seed
    return_indices : bool
        If True, return permutation indices
    voxel_data_preranked : bool, optional
        If True and correlation_type='spearman', voxel_data is already ranked
        (optimization for permutation testing)

    Returns:
    --------
    max_cluster_stat : float
        Maximum cluster statistic in this permutation
    perm_idx : ndarray (only if return_indices=True)
        Permutation indices used
    max_cluster_size : float
        Maximum cluster size
    max_cluster_mass : float
        Maximum cluster mass
    """
    if seed is not None:
        np.random.seed(seed)

    n_subjects = len(effect_sizes)

    # CRITICAL: Shuffle effect sizes AND weights TOGETHER (as per ACES logic)
    # This breaks the E-field <-> effect_size association (what we're testing)
    # But MAINTAINS the effect_size <-> weight association (precision travels with measurement)
    perm_idx = np.random.permutation(n_subjects)
    perm_effect_sizes = effect_sizes[perm_idx]

    # Shuffle weights with same permutation indices to maintain pairing
    perm_weights = None
    if weights is not None:
        perm_weights = weights[perm_idx]

    # Compute correlations for permuted data
    perm_r, perm_t, perm_p = correlation(
        voxel_data,
        perm_effect_sizes,
        correlation_type=correlation_type,
        weights=perm_weights,
        voxel_data_preranked=voxel_data_preranked,
    )

    # Map back to 3D using advanced indexing (faster than loop)
    perm_p_values = np.ones(shape)
    perm_t_statistics = np.zeros(shape)

    idx_i, idx_j, idx_k = valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]
    perm_p_values[idx_i, idx_j, idx_k] = perm_p
    perm_t_statistics[idx_i, idx_j, idx_k] = perm_t

    # Form clusters based on alternative hypothesis
    if alternative == "greater":
        # Test positive correlations only
        perm_mask = (
            (perm_p_values < cluster_threshold) & valid_mask & (perm_t_statistics > 0)
        )
    elif alternative == "less":
        # Test negative correlations only
        perm_mask = (
            (perm_p_values < cluster_threshold) & valid_mask & (perm_t_statistics < 0)
        )
    else:
        # Two-sided: test all significant correlations
        perm_mask = (perm_p_values < cluster_threshold) & valid_mask

    perm_labeled, perm_n_clusters = label(perm_mask)

    # Calculate cluster statistics using optimized approach
    if perm_n_clusters > 0:
        from scipy.ndimage import sum as ndimage_sum

        # Get cluster sizes efficiently using bincount
        cluster_labels_flat = perm_labeled.ravel()
        cluster_sizes_all = np.bincount(
            cluster_labels_flat, minlength=perm_n_clusters + 1
        )[1:]

        # Get cluster masses using ndimage.sum (vectorized)
        cluster_ids = np.arange(1, perm_n_clusters + 1)
        cluster_masses_all = ndimage_sum(
            perm_t_statistics, perm_labeled, index=cluster_ids
        )

        # Filter to only multi-voxel clusters
        multi_voxel_mask = cluster_sizes_all > 1
        perm_cluster_sizes = cluster_sizes_all[multi_voxel_mask].tolist()
        perm_cluster_masses = cluster_masses_all[multi_voxel_mask].tolist()

        if perm_cluster_sizes:
            max_cluster_size = max(perm_cluster_sizes)
            max_cluster_mass = max(perm_cluster_masses)

            if cluster_stat == "size":
                max_cluster_stat = max_cluster_size
            else:
                max_cluster_stat = max_cluster_mass
        else:
            max_cluster_stat = 0
            max_cluster_size = 0
            max_cluster_mass = 0
    else:
        max_cluster_stat = 0
        max_cluster_size = 0
        max_cluster_mass = 0

    if return_indices:
        return max_cluster_stat, perm_idx, max_cluster_size, max_cluster_mass
    else:
        return max_cluster_stat, max_cluster_size, max_cluster_mass


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
    verbose=True,
    logger=None,
    save_permutation_log=False,
    permutation_log_file=None,
    subject_ids=None,
):
    """
    Apply cluster-based permutation correction for correlation analysis.

    This implements the ACES approach where effect sizes are shuffled to
    break the association between E-field magnitude and outcome.

    Parameters:
    -----------
    subject_data : ndarray (x, y, z, n_subjects)
        Electric field magnitude data
    effect_sizes : ndarray (n_subjects,)
        Continuous outcome measure
    r_values : ndarray (x, y, z)
        Correlation coefficients from initial test
    t_statistics : ndarray (x, y, z)
        T-statistics from initial test
    p_values : ndarray (x, y, z)
        P-values from initial test
    valid_mask : ndarray (x, y, z)
        Boolean mask of valid voxels
    weights : ndarray (n_subjects,), optional
        Subject weights for weighted correlation
    correlation_type : str
        'pearson' or 'spearman'
    cluster_threshold : float
        P-value threshold for cluster formation
    n_permutations : int
        Number of permutations
    alpha : float
        Significance level for cluster-level correction
    cluster_stat : str
        'size' or 'mass' (sum of t-values in cluster)
    alternative : {'two-sided', 'greater', 'less'}, optional
        Defines the alternative hypothesis (default: 'two-sided'):
        * 'two-sided': test both positive and negative correlations
        * 'greater': test positive correlations only (one-tailed, uses full alpha)
        * 'less': test negative correlations only (one-tailed, uses full alpha)
    n_jobs : int
        Number of parallel jobs (-1 = all cores)
    verbose : bool
        Print progress information
    logger : logging.Logger, optional
        Logger instance
    save_permutation_log : bool
        Save permutation details
    permutation_log_file : str, optional
        Path for permutation log
    subject_ids : list, optional
        Subject IDs for logging

    Returns:
    --------
    sig_mask : ndarray (x, y, z)
        Binary mask of significant voxels
    cluster_stat_threshold : float
        Cluster statistic threshold from null distribution
    sig_clusters : list of dict
        Information about significant clusters
    null_distribution : ndarray
        Maximum cluster statistics from permutations
    all_clusters : list
        All observed clusters
    correlation_data : dict
        Cluster size and mass data for analysis
    """
    try:
        from .io_utils import save_permutation_details
    except ImportError:
        from io_utils import save_permutation_details

    effect_sizes = np.asarray(effect_sizes, dtype=np.float64)
    n_subjects = len(effect_sizes)

    if verbose:
        header = (
            f"\n{'='*70}\nCORRELATION CLUSTER-BASED PERMUTATION CORRECTION\n{'='*70}"
        )
        if logger:
            logger.info(header)
        else:
            print(header)

        stat_name = "Cluster Size" if cluster_stat == "size" else "Cluster Mass"
        weight_str = " (weighted)" if weights is not None else ""
        alt_text = {
            "two-sided": "two-sided (tests both positive and negative correlations)",
            "greater": "one-sided (tests positive correlations only, full alpha)",
            "less": "one-sided (tests negative correlations only, full alpha)",
        }
        config_info = (
            f"Correlation type: {correlation_type.capitalize()}{weight_str}\n"
            f"Alternative hypothesis: {alt_text.get(alternative, alternative)}\n"
            f"Cluster statistic: {stat_name}\n"
            f"Cluster-forming threshold: p < {cluster_threshold}\n"
            f"Number of permutations: {n_permutations}\n"
            f"Cluster-level alpha: {alpha}"
        )
        if logger:
            for line in config_info.split("\n"):
                logger.info(line)
        else:
            print(config_info)

    # Form clusters based on initial threshold and alternative hypothesis
    if alternative == "greater":
        # Test positive correlations only
        initial_mask = (p_values < cluster_threshold) & valid_mask & (t_statistics > 0)
        corr_type_str = "positive correlations"
    elif alternative == "less":
        # Test negative correlations only
        initial_mask = (p_values < cluster_threshold) & valid_mask & (t_statistics < 0)
        corr_type_str = "negative correlations"
    else:
        # Two-sided: test all significant correlations
        initial_mask = (p_values < cluster_threshold) & valid_mask
        corr_type_str = "correlations (both positive and negative)"

    labeled_array, n_clusters = label(initial_mask)

    if verbose:
        msg = f"\nFound {n_clusters} clusters at p < {cluster_threshold} ({corr_type_str})"
        if logger:
            logger.info(msg)
        else:
            print(msg)

    if n_clusters == 0:
        if verbose:
            msg = "No clusters found. Try increasing cluster_threshold."
            if logger:
                logger.warning(msg)
            else:
                print(msg)
        empty_data = {"sizes": np.array([]), "masses": np.array([])}
        return np.zeros_like(p_values, dtype=int), 0, [], np.array([]), [], empty_data

    # Pre-extract voxel data
    valid_coords = np.argwhere(valid_mask)
    n_valid = len(valid_coords)

    voxel_data = np.zeros((n_valid, n_subjects), dtype=np.float64)
    for idx, coord in enumerate(valid_coords):
        i, j, k = coord
        voxel_data[idx, :] = subject_data[i, j, k, :]

    # OPTIMIZATION: For Spearman, pre-rank voxel data ONCE before permutations
    # This avoids re-ranking the same data in every permutation (huge speedup!)
    voxel_data_preranked = False
    if correlation_type == "spearman":
        if verbose:
            print(
                f"Pre-ranking voxel data for Spearman correlation (one-time operation)..."
            )
        voxel_data = np.apply_along_axis(rankdata, 1, voxel_data)
        voxel_data_preranked = True
        if verbose:
            print(f"  ✓ Voxel data pre-ranked ({n_valid} voxels)")

    if verbose:
        print(f"\nRunning {n_permutations} permutations...")

    # Determine number of jobs
    if n_jobs == -1:
        n_jobs = multiprocessing.cpu_count()

    # Generate seeds for reproducibility
    seeds = np.random.randint(0, 2**31, size=n_permutations)

    track_indices = save_permutation_log and subject_ids is not None

    if n_jobs == 1:
        # Sequential execution
        null_max_cluster_stats = []
        null_max_cluster_sizes = []
        null_max_cluster_masses = []
        permutation_indices = [] if track_indices else None

        iterator = (
            tqdm(range(n_permutations), desc="Permutations")
            if verbose
            else range(n_permutations)
        )
        for perm in iterator:
            result = _run_single_correlation_permutation(
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
                seed=seeds[perm],
                return_indices=track_indices,
                voxel_data_preranked=voxel_data_preranked,
            )
            if track_indices:
                max_stat, perm_idx, max_size, max_mass = result
                null_max_cluster_stats.append(max_stat)
                null_max_cluster_sizes.append(max_size)
                null_max_cluster_masses.append(max_mass)
                permutation_indices.append(perm_idx)
            else:
                max_stat, max_size, max_mass = result
                null_max_cluster_stats.append(max_stat)
                null_max_cluster_sizes.append(max_size)
                null_max_cluster_masses.append(max_mass)
    else:
        # Parallel execution
        if verbose:
            print(f"Using {n_jobs} parallel processes...")

        results = Parallel(n_jobs=n_jobs, verbose=10 if verbose else 0)(
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
                seed=seeds[perm],
                return_indices=track_indices,
                voxel_data_preranked=voxel_data_preranked,
            )
            for perm in range(n_permutations)
        )

        # Clean up parallel processing resources
        import gc

        gc.collect()

        if track_indices:
            null_max_cluster_stats = [r[0] for r in results]
            permutation_indices = [r[1] for r in results]
            null_max_cluster_sizes = [r[2] for r in results]
            null_max_cluster_masses = [r[3] for r in results]
        else:
            null_max_cluster_stats = [r[0] for r in results]
            null_max_cluster_sizes = [r[1] for r in results]
            null_max_cluster_masses = [r[2] for r in results]
            permutation_indices = None

    # Clean up
    del voxel_data
    gc.collect()

    # Determine threshold using discrete approach (consistent with exact p-values)
    null_max_cluster_stats = np.array(null_max_cluster_stats)

    # For p < alpha, we need (count >= observed) < alpha * n_permutations
    # The threshold is the value where exactly alpha * n_permutations values exceed it
    sorted_null = np.sort(null_max_cluster_stats)[::-1]  # Sort descending
    threshold_index = int(alpha * n_permutations)
    if threshold_index == 0:
        threshold_index = 1  # Need at least 1 for edge case
    if threshold_index > len(sorted_null):
        threshold_index = len(sorted_null)

    # Discrete threshold: the value where exactly alpha proportion exceeds it
    cluster_stat_threshold = sorted_null[threshold_index - 1]  # -1 for 0-indexing

    if verbose:
        stat_unit = "voxels" if cluster_stat == "size" else "mass units"
        msg = (
            f"\nDiscrete threshold for significance (p < {alpha}): "
            f"{cluster_stat_threshold:.2f} {stat_unit}\n"
            f"  (This is the {threshold_index}th largest value out of {n_permutations} permutations)\n"
            f"Null distribution: min={np.min(null_max_cluster_stats):.2f}, "
            f"mean={np.mean(null_max_cluster_stats):.2f}, "
            f"max={np.max(null_max_cluster_stats):.2f}"
        )
        if logger:
            logger.info(msg)
        else:
            print(msg)

    # Identify significant clusters using per-cluster p-values (MNE-style)
    sig_mask = np.zeros_like(p_values, dtype=int)
    sig_clusters = []

    # Safety limit to prevent memory issues with very large number of clusters
    max_clusters_to_check = min(n_clusters, 10000)

    if n_clusters > max_clusters_to_check and verbose:
        print(
            f"\nNote: Checking first {max_clusters_to_check} clusters for significance (out of {n_clusters} total)"
        )

    # First pass: collect cluster statistics WITHOUT storing full masks (memory efficient)
    # We only store the cluster_id and compute masks later for significant clusters only
    cluster_info_list = []
    all_cluster_stats = []

    # Use scipy.ndimage for efficient cluster statistics
    from scipy.ndimage import sum as ndimage_sum

    # Get cluster sizes efficiently using bincount
    cluster_labels_flat = labeled_array.ravel()
    cluster_sizes_all = np.bincount(cluster_labels_flat, minlength=n_clusters + 1)

    # Get cluster masses using ndimage.sum (vectorized) - only if needed
    cluster_ids_all = np.arange(1, n_clusters + 1)
    if cluster_stat == "mass":
        cluster_masses_all = ndimage_sum(
            t_statistics, labeled_array, index=cluster_ids_all
        )

    for cluster_id in range(1, max_clusters_to_check + 1):
        size = cluster_sizes_all[cluster_id]

        if size > 1:
            if cluster_stat == "size":
                stat_value = float(size)
            else:
                stat_value = float(cluster_masses_all[cluster_id - 1])

            # Don't store masks here - only store ID and stats
            cluster_info_list.append(
                {"id": cluster_id, "size": int(size), "stat_value": stat_value}
            )
            all_cluster_stats.append(stat_value)

    # Compute per-cluster p-values using MNE-style approach
    if all_cluster_stats:
        all_cluster_stats = np.array(all_cluster_stats)

        # Determine tail based on alternative hypothesis
        if alternative == "greater":
            tail = 1  # Test positive correlations (upper tail)
        elif alternative == "less":
            tail = -1  # Test negative correlations (lower tail)
        else:
            tail = 0  # Two-sided test

        cluster_pvalues = pval_from_histogram(
            all_cluster_stats, null_max_cluster_stats, tail=tail
        )

        # Log top 10 clusters with their p-values for transparency
        if verbose and len(cluster_info_list) > 0:
            msg = f"\nTop {min(10, len(cluster_info_list))} observed clusters with p-values:"
            if logger:
                logger.info(msg)
            else:
                print(msg)

            for i in range(min(10, len(cluster_info_list))):
                info = cluster_info_list[i]
                cluster_pv = cluster_pvalues[i]
                status = "SIGNIFICANT" if cluster_pv < alpha else "not significant"
                msg = (
                    f"  Cluster {info['id']}: mass={info['stat_value']:.2f}, "
                    f"size={info['size']}, p={cluster_pv:.4f} ({status})"
                )
                if logger:
                    logger.info(msg)
                else:
                    print(msg)

        # Collect top observed clusters for visualization (top 10 by cluster mass)
        all_observed_clusters = []
        for i, info in enumerate(cluster_info_list[: min(10, len(cluster_info_list))]):
            all_observed_clusters.append(
                {
                    "id": info["id"],
                    "size": info["size"],
                    "stat_value": info["stat_value"],
                    "p_value": cluster_pvalues[i],
                }
            )

        # Second pass: identify significant clusters and compute masks ONLY for those
        for i, info in enumerate(cluster_info_list):
            cluster_pv = cluster_pvalues[i]

            if cluster_pv < alpha:
                # Get cluster coordinates and set significant mask (memory efficient)
                cluster_coords = np.where(labeled_array == info["id"])
                sig_mask[cluster_coords] = 1

                # Compute additional stats only for significant clusters
                cluster_r_values = r_values[cluster_coords]
                peak_r = np.max(cluster_r_values)
                mean_r = np.mean(cluster_r_values)

                sig_clusters.append(
                    {
                        "id": info["id"],
                        "size": info["size"],
                        "stat_value": info["stat_value"],
                        "peak_r": peak_r,
                        "mean_r": mean_r,
                        "p_value": cluster_pv,
                    }
                )

    if verbose:
        msg = (
            f"\nSignificant clusters (p < {alpha}): {len(sig_clusters)}\n"
            f"Total significant voxels: {np.sum(sig_mask)}"
        )
        if logger:
            logger.info(msg)
        else:
            print(msg)

    correlation_data = {
        "sizes": np.array(null_max_cluster_sizes),
        "masses": np.array(null_max_cluster_masses),
    }

    return (
        sig_mask,
        cluster_stat_threshold,
        sig_clusters,
        null_max_cluster_stats,
        all_observed_clusters,
        correlation_data,
    )


def ttest_ind(test_data, n_resp, n_non_resp, alternative="two-sided"):
    """
    Vectorized computation of independent samples t-tests for all voxels at once.

    Parameters:
    -----------
    test_data : ndarray, shape (n_voxels, n_total_subjects)
        Data for all test voxels and subjects
    n_resp : int
        Number of responders
    n_non_resp : int
        Number of non-responders
    alternative : {'two-sided', 'greater', 'less'}, optional
        Alternative hypothesis

    Returns:
    --------
    t_stats : ndarray, shape (n_voxels,)
        T-statistics for all voxels
    p_values : ndarray, shape (n_voxels,)
        P-values for all voxels
    """
    # Split data into groups
    resp_data = test_data[:, :n_resp]  # Shape: (n_voxels, n_resp)
    non_resp_data = test_data[:, n_resp:]  # Shape: (n_voxels, n_non_resp)

    # Compute means and variances for all voxels at once
    resp_means = np.mean(resp_data, axis=1)  # Shape: (n_voxels,)
    non_resp_means = np.mean(non_resp_data, axis=1)
    resp_vars = np.var(resp_data, axis=1, ddof=1)
    non_resp_vars = np.var(non_resp_data, axis=1, ddof=1)

    # Vectorized pooled variance calculation
    numerator = (n_resp - 1) * resp_vars + (n_non_resp - 1) * non_resp_vars
    denominator = n_resp + n_non_resp - 2
    pooled_vars = numerator / denominator

    # Standard error of the difference
    se_diff = np.sqrt(pooled_vars * (1 / n_resp + 1 / n_non_resp))

    # Avoid division by zero
    valid_voxels = se_diff > 0
    t_stats = np.zeros(test_data.shape[0])

    # Vectorized t-statistic computation
    mean_diff = resp_means - non_resp_means
    t_stats[valid_voxels] = mean_diff[valid_voxels] / se_diff[valid_voxels]

    # Vectorized p-value computation
    df = n_resp + n_non_resp - 2

    if alternative == "two-sided":
        p_values = 2 * stats.t.sf(np.abs(t_stats), df)
    elif alternative == "greater":
        p_values = stats.t.sf(t_stats, df)
    elif alternative == "less":
        p_values = stats.t.sf(-t_stats, df)
    else:
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def ttest_rel(test_data, n_resp, alternative="two-sided"):
    """
    Vectorized computation of paired samples t-tests for all voxels at once.

    Parameters:
    -----------
    test_data : ndarray, shape (n_voxels, n_total_subjects)
        Data for all test voxels and subjects (paired)
    n_resp : int
        Number of pairs (same as n_non_resp for paired test)
    alternative : {'two-sided', 'greater', 'less'}, optional
        Alternative hypothesis

    Returns:
    --------
    t_stats : ndarray, shape (n_voxels,)
        T-statistics for all voxels
    p_values : ndarray, shape (n_voxels,)
        P-values for all voxels
    """
    # For paired tests, data is already paired
    resp_data = test_data[:, :n_resp]
    non_resp_data = test_data[:, n_resp:]

    # Compute differences for all voxels at once
    diff_data = resp_data - non_resp_data  # Shape: (n_voxels, n_pairs)

    # Compute means and std of differences for all voxels
    diff_means = np.mean(diff_data, axis=1)  # Shape: (n_voxels,)
    diff_stds = np.std(diff_data, axis=1, ddof=1)

    # Avoid division by zero
    valid_voxels = diff_stds > 0
    t_stats = np.zeros(test_data.shape[0])

    # Vectorized t-statistic computation
    se_diff = diff_stds / np.sqrt(n_resp)
    t_stats[valid_voxels] = diff_means[valid_voxels] / se_diff[valid_voxels]

    # Vectorized p-value computation
    df = n_resp - 1

    if alternative == "two-sided":
        p_values = 2 * stats.t.sf(np.abs(t_stats), df)
    elif alternative == "greater":
        p_values = stats.t.sf(t_stats, df)
    elif alternative == "less":
        p_values = stats.t.sf(-t_stats, df)
    else:
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def ttest_voxelwise(
    responders,
    non_responders,
    test_type="unpaired",
    alternative="two-sided",
    verbose=True,
):
    """
    Perform vectorized t-test (paired or unpaired) at each voxel.

    Uses vectorized computation for optimal performance.

    Parameters:
    -----------
    responders : ndarray (x, y, z, n_subjects)
        Responder data (group 1)
    non_responders : ndarray (x, y, z, n_subjects)
        Non-responder data (group 2)
    test_type : str
        Either 'paired' or 'unpaired' t-test
    alternative : {'two-sided', 'greater', 'less'}, optional
        Defines the alternative hypothesis (default: 'two-sided'):
        * 'two-sided': means are different (responders ≠ non-responders)
        * 'greater': responders have higher values (responders > non-responders)
        * 'less': responders have lower values (responders < non-responders)
    verbose : bool
        Print progress information

    Returns:
    --------
    p_values : ndarray (x, y, z)
        P-value at each voxel
    t_statistics : ndarray (x, y, z)
        T-statistic at each voxel
    valid_mask : ndarray (x, y, z)
        Boolean mask of valid voxels
    """
    if verbose:
        test_name = (
            "Paired" if test_type == "paired" else "Unpaired (Independent Samples)"
        )
        alt_text = ""
        if alternative == "greater":
            alt_text = " (one-sided: responders > non-responders)"
        elif alternative == "less":
            alt_text = " (one-sided: responders < non-responders)"
        print(f"\nPerforming voxelwise {test_name} t-tests{alt_text} (vectorized)...")

    # Validate test type
    if test_type not in ["paired", "unpaired"]:
        raise ValueError("test_type must be 'paired' or 'unpaired'")

    # For paired test, check that sample sizes match
    if test_type == "paired":
        if responders.shape[-1] != non_responders.shape[-1]:
            raise ValueError(
                f"Paired t-test requires equal sample sizes. "
                f"Got {responders.shape[-1]} vs {non_responders.shape[-1]} subjects"
            )

    shape = responders.shape[:3]
    p_values = np.ones(shape)
    t_statistics = np.zeros(shape)

    # Create mask of valid voxels (non-zero in at least some subjects)
    responder_mask = np.any(responders > 0, axis=-1)
    non_responder_mask = np.any(non_responders > 0, axis=-1)
    valid_mask = responder_mask | non_responder_mask

    total_voxels = np.sum(valid_mask)
    if verbose:
        print(f"Testing {total_voxels} valid voxels using vectorized approach...")

    # Get coordinates of valid voxels
    valid_coords = np.argwhere(valid_mask)

    # Vectorized approach: compute all tests at once
    n_valid = len(valid_coords)
    n_resp = responders.shape[-1]
    n_non_resp = non_responders.shape[-1]

    # Pre-extract voxel data using advanced indexing (faster than loop)
    # This avoids Python loop overhead by using NumPy's optimized indexing
    idx_i, idx_j, idx_k = valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]

    # Extract all valid voxels at once using fancy indexing
    resp_extracted = responders[idx_i, idx_j, idx_k, :].astype(
        np.float32
    )  # (n_valid, n_resp)
    non_resp_extracted = non_responders[idx_i, idx_j, idx_k, :].astype(
        np.float32
    )  # (n_valid, n_non_resp)

    # Concatenate horizontally
    voxel_data = np.concatenate([resp_extracted, non_resp_extracted], axis=1)

    # Use vectorized t-test functions
    if test_type == "paired":
        t_stats_1d, p_values_1d = ttest_rel(voxel_data, n_resp, alternative=alternative)
    else:
        t_stats_1d, p_values_1d = ttest_ind(
            voxel_data, n_resp, n_non_resp, alternative=alternative
        )

    # Map results back to 3D volume coordinates using advanced indexing (faster than loop)
    t_statistics[idx_i, idx_j, idx_k] = t_stats_1d
    p_values[idx_i, idx_j, idx_k] = p_values_1d

    return p_values, t_statistics, valid_mask


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
    """
    Helper function to run a single permutation (for parallel processing)

    Parameters:
    -----------
    test_data : ndarray
        Pre-extracted test voxel data
    test_coords : ndarray
        Coordinates of test voxels
    n_resp : int
        Number of responders
    n_total : int
        Total number of subjects
    cluster_threshold : float
        P-value threshold for cluster formation
    valid_mask : ndarray
        Boolean mask of valid voxels
    p_values_shape : tuple
        Shape of p_values array
    test_type : str
        Either 'paired' or 'unpaired' t-test
    alternative : {'two-sided', 'greater', 'less'}, optional
        Alternative hypothesis (default: 'two-sided')
    cluster_stat : {'size', 'mass'}, optional
        Cluster statistic to use (default: 'size'):
        * 'size': count of contiguous significant voxels
        * 'mass': sum of t-statistics in contiguous significant voxels
    seed : int, optional
        Random seed for reproducibility
    return_indices : bool, optional
        If True, return permutation indices along with max cluster statistic

    Returns:
    --------
    max_cluster_stat : float
        Maximum cluster statistic (size or mass) in this permutation
    perm_idx : ndarray (only if return_indices=True)
        Permutation indices used
    """
    if seed is not None:
        np.random.seed(seed)

    perm_idx = None

    if test_type == "paired":
        # For paired test, randomly flip signs of differences
        # This preserves the pairing structure
        perm_test_data = test_data.copy()
        n_voxels = test_data.shape[0]

        # Split back into groups
        resp_data = test_data[:, :n_resp]
        non_resp_data = test_data[:, n_resp:]

        # Randomly flip signs for each pair
        sign_flips = np.random.choice([-1, 1], size=n_resp)
        if return_indices:
            perm_idx = sign_flips  # For paired, store sign flips

        # Create permuted data by flipping differences
        for i in range(n_voxels):
            mean_pair = (resp_data[i, :] + non_resp_data[i, :]) / 2
            diff_pair = (resp_data[i, :] - non_resp_data[i, :]) / 2
            perm_test_data[i, :n_resp] = mean_pair + sign_flips * diff_pair
            perm_test_data[i, n_resp:] = mean_pair - sign_flips * diff_pair

        perm_resp_data = perm_test_data[:, :n_resp]
        perm_non_resp_data = perm_test_data[:, n_resp:]
    else:
        # For unpaired test, randomly shuffle group labels
        perm_indices = np.random.permutation(n_total)
        if return_indices:
            perm_idx = perm_indices
        perm_test_data = test_data[:, perm_indices]

        # Split into groups
        perm_resp_data = perm_test_data[:, :n_resp]
        perm_non_resp_data = perm_test_data[:, n_resp:]

    # Compute permuted p-values and t-statistics
    perm_p_values = np.ones(p_values_shape)
    perm_t_statistics = np.zeros(p_values_shape)

    # Use vectorized t-test computation for all voxels at once
    if test_type == "paired":
        t_stats_1d, p_values_1d = ttest_rel(
            perm_test_data, n_resp, alternative=alternative
        )
    else:
        t_stats_1d, p_values_1d = ttest_ind(
            perm_test_data, n_resp, n_total - n_resp, alternative=alternative
        )

    # Map results back to 3D volume coordinates using advanced indexing (faster than loop)
    idx_i, idx_j, idx_k = test_coords[:, 0], test_coords[:, 1], test_coords[:, 2]
    perm_t_statistics[idx_i, idx_j, idx_k] = t_stats_1d
    perm_p_values[idx_i, idx_j, idx_k] = p_values_1d

    # Find clusters in permuted data
    perm_mask = (perm_p_values < cluster_threshold) & valid_mask
    perm_labeled, perm_n_clusters = label(perm_mask)

    # Calculate both cluster size and mass for correlation analysis
    # Use scipy.ndimage for efficient cluster statistics (faster than Python loop)
    if perm_n_clusters > 0:
        from scipy.ndimage import sum as ndimage_sum

        # Get cluster sizes efficiently using bincount
        cluster_labels_flat = perm_labeled.ravel()
        cluster_sizes_all = np.bincount(
            cluster_labels_flat, minlength=perm_n_clusters + 1
        )[1:]

        # Get cluster masses using ndimage.sum (vectorized)
        cluster_ids = np.arange(1, perm_n_clusters + 1)
        cluster_masses_all = ndimage_sum(
            perm_t_statistics, perm_labeled, index=cluster_ids
        )

        # Filter to only multi-voxel clusters
        multi_voxel_mask = cluster_sizes_all > 1
        perm_cluster_sizes = cluster_sizes_all[multi_voxel_mask].tolist()
        perm_cluster_masses = cluster_masses_all[multi_voxel_mask].tolist()

        if perm_cluster_sizes:  # If we have any multi-voxel clusters
            max_cluster_size = max(perm_cluster_sizes)
            max_cluster_mass = max(perm_cluster_masses)

            # Select the statistic to return based on cluster_stat
            if cluster_stat == "size":
                max_cluster_stat = max_cluster_size
            elif cluster_stat == "mass":
                max_cluster_stat = max_cluster_mass
            else:
                raise ValueError(
                    f"cluster_stat must be 'size' or 'mass', got '{cluster_stat}'"
                )
        else:
            # All clusters were single voxels, treat as no clusters
            max_cluster_stat = 0
            max_cluster_size = 0
            max_cluster_mass = 0
    else:
        max_cluster_stat = 0
        max_cluster_size = 0
        max_cluster_mass = 0

    # Return results with both size and mass for correlation analysis
    if return_indices:
        return max_cluster_stat, perm_idx, max_cluster_size, max_cluster_mass
    else:
        return max_cluster_stat, max_cluster_size, max_cluster_mass


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
    cluster_stat="size",
    t_statistics=None,
    n_jobs=-1,
    verbose=True,
    logger=None,
    save_permutation_log=False,
    permutation_log_file=None,
    subject_ids_resp=None,
    subject_ids_non_resp=None,
):
    """
    Apply cluster-based permutation correction for multiple comparisons

    This implements the cluster-based approach commonly used in neuroimaging.
    Tests all valid voxels in permutations and uses parallel processing for speed.

    Parameters:
    -----------
    responders : ndarray (x, y, z, n_subjects)
        Responder data
    non_responders : ndarray (x, y, z, n_subjects)
        Non-responder data
    p_values : ndarray (x, y, z)
        Uncorrected p-values from initial test
    valid_mask : ndarray (x, y, z)
        Boolean mask of valid voxels
    cluster_threshold : float
        Initial p-value threshold for cluster formation (uncorrected)
    n_permutations : int
        Number of permutations for null distribution (500-1000 recommended)
    alpha : float
        Significance level for cluster-level correction
    test_type : str
        Either 'paired' or 'unpaired' t-test for permutations
    alternative : {'two-sided', 'greater', 'less'}, optional
        Alternative hypothesis (default: 'two-sided')
    cluster_stat : {'size', 'mass'}, optional
        Cluster statistic to use (default: 'size'):
        * 'size': count of contiguous significant voxels
        * 'mass': sum of t-statistics in contiguous significant voxels
    t_statistics : ndarray (x, y, z), optional
        T-statistics from initial test (required if cluster_stat='mass')
    n_jobs : int
        Number of parallel jobs. -1 uses all available CPU cores. 1 disables parallelization.
    verbose : bool
        Print progress information
    logger : logging.Logger, optional
        Logger instance for output (default: None)
    save_permutation_log : bool, optional
        If True, save detailed permutation information to file (default: False)
    permutation_log_file : str, optional
        Path to save permutation log. If None and save_permutation_log=True,
        will use default name
    subject_ids_resp : list, optional
        List of responder subject IDs (for logging)
    subject_ids_non_resp : list, optional
        List of non-responder subject IDs (for logging)

    Returns:
    --------
    sig_mask : ndarray (x, y, z)
        Binary mask of significant voxels
    cluster_stat_threshold : float
        Cluster statistic threshold from permutation distribution
    sig_clusters : list of dict
        Information about significant clusters
    null_max_cluster_stats : ndarray
        Maximum cluster statistics from permutation null distribution
    cluster_stats : list of dict
        All clusters from observed data (for plotting)
    correlation_data : dict
        Dictionary with 'sizes' and 'masses' arrays for correlation analysis
    """
    try:
        from .io_utils import save_permutation_details
    except ImportError:
        from io_utils import save_permutation_details

    # Validate cluster_stat parameter
    if cluster_stat not in ["size", "mass"]:
        raise ValueError(f"cluster_stat must be 'size' or 'mass', got '{cluster_stat}'")

    # Check that t_statistics is provided if using cluster mass
    if cluster_stat == "mass" and t_statistics is None:
        raise ValueError("t_statistics must be provided when cluster_stat='mass'")

    if verbose:
        header = f"\n{'='*70}\nCLUSTER-BASED PERMUTATION CORRECTION\n{'='*70}"
        if logger:
            logger.info(header)
        else:
            print(header)
        cluster_stat_name = "Cluster Size" if cluster_stat == "size" else "Cluster Mass"
        config_info = f"Cluster statistic: {cluster_stat_name}\nCluster-forming threshold: p < {cluster_threshold}\nNumber of permutations: {n_permutations}\nCluster-level alpha: {alpha}"
        if logger:
            for line in config_info.split("\n"):
                logger.info(line)
        else:
            print(config_info)

    # Step 1: Form clusters based on initial threshold
    initial_mask = (p_values < cluster_threshold) & valid_mask
    labeled_array, n_clusters = label(initial_mask)

    if verbose:
        msg = f"\nFound {n_clusters} clusters at p < {cluster_threshold} (uncorrected)"
        if logger:
            logger.info(msg)
        else:
            print(msg)

    if n_clusters == 0:
        if verbose:
            msg = "No clusters found. Try increasing cluster_threshold (e.g., 0.05)"
            if logger:
                logger.warning(msg)
            else:
                print(msg)
        # Return all 6 expected values with empty/default data
        empty_correlation_data = {"sizes": np.array([]), "masses": np.array([])}
        return (
            np.zeros_like(p_values, dtype=int),
            cluster_threshold,
            [],
            np.array([]),
            [],
            empty_correlation_data,
        )

    # Calculate cluster statistics efficiently without storing all clusters
    if n_clusters > 1000 and verbose:
        warning_msg = f"\nWARNING: Found {n_clusters} clusters! This is unusually high.\nConsider:\n  1. Using a stricter cluster_threshold (e.g., 0.01 instead of 0.05)\n  2. Checking if your data is properly masked\n  3. Verifying your p-values are computed correctly"
        if logger:
            logger.warning(warning_msg)
        else:
            print(warning_msg)

    # Find top clusters for display without storing all in memory
    if verbose:
        msg = f"\nFinding largest clusters for summary..."
        if logger:
            logger.info(msg)
        else:
            print(msg)
        top_clusters = []

        # Find top 10 clusters by their statistic
        for cluster_id in range(1, n_clusters + 1):
            cluster_mask = labeled_array == cluster_id
            size = np.sum(cluster_mask)

            if size > 1:  # Only multi-voxel clusters
                if cluster_stat == "size":
                    stat_value = float(size)
                elif cluster_stat == "mass":
                    stat_value = float(np.sum(t_statistics[cluster_mask]))

                # Keep only top 10
                if len(top_clusters) < 10:
                    top_clusters.append((cluster_id, size, stat_value))
                    top_clusters.sort(key=lambda x: x[2], reverse=True)
                elif stat_value > top_clusters[-1][2]:
                    top_clusters[-1] = (cluster_id, size, stat_value)
                    top_clusters.sort(key=lambda x: x[2], reverse=True)

        if top_clusters:
            # Show summary of top clusters
            if cluster_stat == "size":
                msg = f"\nTop {len(top_clusters)} clusters (largest: {top_clusters[0][2]:.0f} voxels)"
            else:
                msg = f"\nTop {len(top_clusters)} clusters (largest mass: {top_clusters[0][2]:.2f})"

            if logger:
                logger.info(msg)
            else:
                print(msg)

            for i, (cid, size, stat_value) in enumerate(top_clusters[:5], 1):
                if cluster_stat == "size":
                    msg = f"  {i}. Cluster {cid}: {size} voxels"
                else:
                    msg = (
                        f"  {i}. Cluster {cid}: {size} voxels, mass = {stat_value:.2f}"
                    )
                if logger:
                    logger.info(msg)
                else:
                    print(msg)
        else:
            msg = f"\nNo multi-voxel clusters found"
            if logger:
                logger.info(msg)
            else:
                print(msg)

    # Step 2: Test all valid voxels in permutations
    test_mask = valid_mask
    test_coords = np.argwhere(test_mask)
    n_test_voxels = len(test_coords)

    if verbose:
        msg = f"\nTesting all {n_test_voxels} valid voxels in permutations"
        if logger:
            logger.info(msg)
        else:
            print(msg)

    # Step 3: Permutation testing
    if verbose:
        msg = f"\nRunning {n_permutations} permutations..."
        if logger:
            logger.info(msg)
        else:
            print(msg)

    # Combine all subjects
    all_data = np.concatenate([responders, non_responders], axis=-1)
    n_resp = responders.shape[-1]
    n_non_resp = non_responders.shape[-1]
    n_total = n_resp + n_non_resp

    # Pre-extract data for test voxels
    if verbose:
        msg = f"Pre-extracting voxel data for faster permutations...\n  Test voxels: {n_test_voxels:,}\n  Total subjects: {n_total}"
        if logger:
            logger.info(msg)
        else:
            print(msg)

    # Use float32 to save memory
    test_data = np.zeros((n_test_voxels, n_total), dtype=np.float32)
    for idx, coord in enumerate(test_coords):
        i, j, k = coord[0], coord[1], coord[2]
        test_data[idx, :] = all_data[i, j, k, :].astype(np.float32)

    # Free the original combined data array
    del all_data
    import gc

    gc.collect()

    # Report memory usage
    if verbose:
        test_data_mb = test_data.nbytes / (1024**2)
        msg = f"  Test data size: {test_data_mb:.1f} MB"
        if logger:
            logger.info(msg)
        else:
            print(msg)

    # Determine number of jobs
    if n_jobs == -1:
        n_jobs = multiprocessing.cpu_count()
        if verbose:
            print(f"Auto-detected {n_jobs} CPU cores")

    if verbose:
        if n_jobs == 1:
            print("Running permutations sequentially (1 core)...")
        else:
            print(f"Running permutations in parallel using {n_jobs} cores...")

    # Run permutations in parallel
    # Use seeds for reproducibility
    seeds = np.random.randint(0, 2**31, size=n_permutations)

    # Determine if we need to track permutation indices
    track_indices = (
        save_permutation_log
        and subject_ids_resp is not None
        and subject_ids_non_resp is not None
    )

    if n_jobs == 1:
        # Sequential execution with progress bar
        null_max_cluster_stats = []
        null_max_cluster_sizes = []
        null_max_cluster_masses = []
        permutation_indices = [] if track_indices else None
        iterator = (
            tqdm(range(n_permutations), desc="Permutations")
            if verbose
            else range(n_permutations)
        )
        for perm in iterator:
            result = _run_single_permutation(
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
                seed=seeds[perm],
                return_indices=track_indices,
            )
            if track_indices:
                max_stat, perm_idx, max_size, max_mass = result
                null_max_cluster_stats.append(max_stat)
                null_max_cluster_sizes.append(max_size)
                null_max_cluster_masses.append(max_mass)
                permutation_indices.append(perm_idx)
            else:
                max_stat, max_size, max_mass = result
                null_max_cluster_stats.append(max_stat)
                null_max_cluster_sizes.append(max_size)
                null_max_cluster_masses.append(max_mass)
    else:
        # Parallel execution using joblib - same as local implementation
        if verbose:
            print(f"Using joblib with {n_jobs} processes...")

        # Run permutations with joblib
        results = Parallel(n_jobs=n_jobs, verbose=10 if verbose else 0)(
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
                seed=seeds[perm],
                return_indices=track_indices,
            )
            for perm in range(n_permutations)
        )

        # Clean up parallel processing resources
        import gc

        gc.collect()

        if verbose:
            print(f"All {n_permutations} permutations completed")

        if track_indices:
            null_max_cluster_stats = [r[0] for r in results]
            permutation_indices = [r[1] for r in results]
            null_max_cluster_sizes = [r[2] for r in results]
            null_max_cluster_masses = [r[3] for r in results]
        else:
            null_max_cluster_stats = [r[0] for r in results]
            null_max_cluster_sizes = [r[1] for r in results]
            null_max_cluster_masses = [r[2] for r in results]
            permutation_indices = None

    # Explicitly free memory from test_data and other large arrays
    del test_data
    del test_coords
    gc.collect()

    # Step 4: Determine cluster statistic threshold using discrete approach
    null_max_cluster_stats = np.array(null_max_cluster_stats)

    # For p < alpha, we need (count >= observed) < alpha * n_permutations
    # The threshold is the value where exactly alpha * n_permutations values exceed it
    sorted_null = np.sort(null_max_cluster_stats)[::-1]  # Sort descending
    threshold_index = int(alpha * n_permutations)
    if threshold_index == 0:
        threshold_index = 1  # Need at least 1 for edge case
    if threshold_index > len(sorted_null):
        threshold_index = len(sorted_null)

    # Discrete threshold: the value where exactly alpha proportion exceeds it
    cluster_stat_threshold = sorted_null[threshold_index - 1]  # -1 for 0-indexing

    if verbose:
        stat_unit = "voxels" if cluster_stat == "size" else "mass units"
        msg = f"\nDiscrete threshold for significance (p < {alpha}): {cluster_stat_threshold:.2f} {stat_unit}\n  (This is the {threshold_index}th largest value out of {n_permutations} permutations)\nNull distribution stats: min={np.min(null_max_cluster_stats):.2f}, mean={np.mean(null_max_cluster_stats):.2f}, max={np.max(null_max_cluster_stats):.2f}"
        if logger:
            logger.info(msg)
        else:
            print(msg)

    # Save permutation details if requested
    if save_permutation_log and permutation_indices is not None:
        if permutation_log_file is None:
            permutation_log_file = "permutation_details.txt"

        # Prepare permutation info
        permutation_info = []
        for perm_num in range(n_permutations):
            permutation_info.append(
                {
                    "perm_num": perm_num,
                    "perm_idx": permutation_indices[perm_num],
                    "max_cluster_size": null_max_cluster_stats[perm_num],
                }
            )

        save_permutation_details(
            permutation_info,
            permutation_log_file,
            subject_ids_resp,
            subject_ids_non_resp,
        )

        if verbose:
            print(f"Saved permutation details to: {permutation_log_file}")

    # Step 5: Identify significant clusters using per-cluster p-values (MNE-style)
    # Include observed max in null distribution for proper p-value computation
    # Reference: Maris & Oostenveld (2007), MNE-Python implementation
    sig_mask = np.zeros_like(p_values, dtype=int)
    sig_clusters = []
    all_cluster_stats = []  # Store all cluster statistics for p-value computation

    # First pass: collect all cluster statistics
    max_clusters_to_check = min(n_clusters, 10000)  # Safety limit

    if n_clusters > max_clusters_to_check and verbose:
        print(
            f"\nNote: Checking first {max_clusters_to_check} clusters for significance (out of {n_clusters} total)"
        )

    cluster_info_list = []
    for cluster_id in range(1, max_clusters_to_check + 1):
        # Get cluster coordinates without creating full boolean mask
        cluster_coords = np.where(labeled_array == cluster_id)
        size = len(cluster_coords[0])

        if size > 1:  # Only multi-voxel clusters
            if cluster_stat == "size":
                stat_value = float(size)
            elif cluster_stat == "mass":
                stat_value = float(np.sum(t_statistics[cluster_coords]))

            cluster_info_list.append(
                {
                    "id": cluster_id,
                    "size": size,
                    "stat_value": stat_value,
                    "coords": cluster_coords,
                }
            )
            all_cluster_stats.append(stat_value)

    # Compute per-cluster p-values using MNE-style approach
    # Add observed max to null distribution for proper family-wise error control
    if all_cluster_stats:
        all_cluster_stats = np.array(all_cluster_stats)

        # Determine tail based on alternative hypothesis
        if alternative == "greater":
            tail = 1
        elif alternative == "less":
            tail = -1
        else:
            tail = 0

        # Compute p-values for each cluster
        cluster_pvalues = pval_from_histogram(
            all_cluster_stats, null_max_cluster_stats, tail=tail
        )

        # Log top 10 clusters with their p-values for transparency
        if verbose and len(cluster_info_list) > 0:
            msg = f"\nTop {min(10, len(cluster_info_list))} observed clusters with p-values:"
            if logger:
                logger.info(msg)
            else:
                print(msg)

            for i in range(min(10, len(cluster_info_list))):
                info = cluster_info_list[i]
                cluster_pv = cluster_pvalues[i]
                status = "SIGNIFICANT" if cluster_pv < alpha else "not significant"
                if cluster_stat == "size":
                    msg = (
                        f"  Cluster {info['id']}: {info['size']} voxels, "
                        f"p={cluster_pv:.4f} ({status})"
                    )
                else:
                    msg = (
                        f"  Cluster {info['id']}: mass={info['stat_value']:.2f}, "
                        f"size={info['size']}, p={cluster_pv:.4f} ({status})"
                    )
                if logger:
                    logger.info(msg)
                else:
                    print(msg)

        # Collect top observed clusters for visualization (top 10 by cluster statistic)
        all_observed_clusters = []
        for i, info in enumerate(cluster_info_list[: min(10, len(cluster_info_list))]):
            all_observed_clusters.append(
                {
                    "id": info["id"],
                    "size": info["size"],
                    "stat_value": info["stat_value"],
                    "p_value": cluster_pvalues[i],
                }
            )

        # Second pass: identify significant clusters
        for i, info in enumerate(cluster_info_list):
            cluster_pv = cluster_pvalues[i]

            # Check if significant using per-cluster p-value
            if cluster_pv < alpha:
                sig_mask[info["coords"]] = 1
                sig_clusters.append(
                    {
                        "id": info["id"],
                        "size": info["size"],
                        "stat_value": info["stat_value"],
                        "p_value": cluster_pv,
                    }
                )

    if verbose:
        msg = f"\nSignificant clusters (p < {alpha}): {len(sig_clusters)}\nTotal significant voxels: {np.sum(sig_mask)}"
        if logger:
            logger.info(msg)
        else:
            print(msg)

    # Prepare correlation data
    correlation_data = {
        "sizes": np.array(null_max_cluster_sizes),
        "masses": np.array(null_max_cluster_masses),
    }

    return (
        sig_mask,
        cluster_stat_threshold,
        sig_clusters,
        null_max_cluster_stats,
        all_observed_clusters,
        correlation_data,
    )


def cluster_analysis(sig_mask, affine, verbose=True):
    """
    Perform cluster analysis on significant voxels

    Parameters:
    -----------
    sig_mask : ndarray (x, y, z)
        Binary mask of significant voxels
    affine : ndarray
        Affine transformation matrix
    verbose : bool
        Print progress information

    Returns:
    --------
    clusters : list of dict
        Cluster information including size, center of mass in voxel and MNI coordinates
    """
    import nibabel as nib

    if verbose:
        print("\nPerforming cluster analysis...")

    # Find connected clusters
    labeled_array, num_clusters = label(sig_mask)

    if num_clusters == 0:
        if verbose:
            print("No clusters found")
        return []

    clusters = []
    for cluster_id in range(1, num_clusters + 1):
        cluster_mask = labeled_array == cluster_id
        cluster_size = np.sum(cluster_mask)

        # Get center of mass in voxel coordinates
        coords = np.argwhere(cluster_mask)
        com_voxel = np.mean(coords, axis=0)

        # Convert to MNI coordinates
        com_mni = nib.affines.apply_affine(affine, com_voxel)

        clusters.append(
            {
                "cluster_id": cluster_id,
                "size": cluster_size,
                "center_voxel": com_voxel,
                "center_mni": com_mni,
            }
        )

    # Sort by size
    clusters = sorted(clusters, key=lambda x: x["size"], reverse=True)

    if verbose:
        print(f"Found {num_clusters} clusters")
        for c in clusters[:10]:  # Show top 10
            print(
                f"  Cluster {c['cluster_id']}: {c['size']} voxels, "
                f"MNI center: ({c['center_mni'][0]:.1f}, {c['center_mni'][1]:.1f}, {c['center_mni'][2]:.1f})"
            )

    return clusters
