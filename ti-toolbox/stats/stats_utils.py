"""
Statistical analysis utilities for neuroimaging

This module contains functions for:
- T-tests (paired and unpaired)
- Cluster-based permutation correction
- Cluster analysis
"""

import numpy as np
from scipy import stats
from scipy.ndimage import label
from tqdm import tqdm

from joblib import Parallel, delayed
import multiprocessing
import gc


def vectorized_ttest_ind(test_data, n_resp, n_non_resp, alternative='two-sided'):
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
    resp_data = test_data[:, :n_resp]      # Shape: (n_voxels, n_resp)
    non_resp_data = test_data[:, n_resp:]  # Shape: (n_voxels, n_non_resp)

    # Compute means and variances for all voxels at once
    resp_means = np.mean(resp_data, axis=1)      # Shape: (n_voxels,)
    non_resp_means = np.mean(non_resp_data, axis=1)
    resp_vars = np.var(resp_data, axis=1, ddof=1)
    non_resp_vars = np.var(non_resp_data, axis=1, ddof=1)

    # Vectorized pooled variance calculation
    numerator = ((n_resp-1) * resp_vars + (n_non_resp-1) * non_resp_vars)
    denominator = n_resp + n_non_resp - 2
    pooled_vars = numerator / denominator

    # Standard error of the difference
    se_diff = np.sqrt(pooled_vars * (1/n_resp + 1/n_non_resp))

    # Avoid division by zero
    valid_voxels = se_diff > 0
    t_stats = np.zeros(test_data.shape[0])

    # Vectorized t-statistic computation
    mean_diff = resp_means - non_resp_means
    t_stats[valid_voxels] = mean_diff[valid_voxels] / se_diff[valid_voxels]

    # Vectorized p-value computation
    df = n_resp + n_non_resp - 2

    if alternative == 'two-sided':
        p_values = 2 * stats.t.sf(np.abs(t_stats), df)
    elif alternative == 'greater':
        p_values = stats.t.sf(t_stats, df)
    elif alternative == 'less':
        p_values = stats.t.sf(-t_stats, df)
    else:
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def _vectorized_ttest_rel(test_data, n_resp, alternative='two-sided'):
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

    if alternative == 'two-sided':
        p_values = 2 * stats.t.sf(np.abs(t_stats), df)
    elif alternative == 'greater':
        p_values = stats.t.sf(t_stats, df)
    elif alternative == 'less':
        p_values = stats.t.sf(-t_stats, df)
    else:
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def vectorized_ttest_rel(test_data, n_resp, alternative='two-sided'):
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

    if alternative == 'two-sided':
        p_values = 2 * stats.t.sf(np.abs(t_stats), df)
    elif alternative == 'greater':
        p_values = stats.t.sf(t_stats, df)
    elif alternative == 'less':
        p_values = stats.t.sf(-t_stats, df)
    else:
        raise ValueError("alternative must be 'two-sided', 'greater', or 'less'")

    return t_stats, p_values


def ttest_voxelwise(responders, non_responders, test_type='unpaired', alternative='two-sided', verbose=True):
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
        test_name = "Paired" if test_type == 'paired' else "Unpaired (Independent Samples)"
        alt_text = ""
        if alternative == 'greater':
            alt_text = " (one-sided: responders > non-responders)"
        elif alternative == 'less':
            alt_text = " (one-sided: responders < non-responders)"
        print(f"\nPerforming voxelwise {test_name} t-tests{alt_text} (vectorized)...")

    # Validate test type
    if test_type not in ['paired', 'unpaired']:
        raise ValueError("test_type must be 'paired' or 'unpaired'")

    # For paired test, check that sample sizes match
    if test_type == 'paired':
        if responders.shape[-1] != non_responders.shape[-1]:
            raise ValueError(f"Paired t-test requires equal sample sizes. "
                           f"Got {responders.shape[-1]} vs {non_responders.shape[-1]} subjects")

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

    # Pre-extract voxel data for faster computation
    voxel_data = np.zeros((n_valid, n_resp + n_non_resp), dtype=np.float32)
    for idx, coord in enumerate(valid_coords):
        i, j, k = coord
        voxel_data[idx, :n_resp] = responders[i, j, k, :].astype(np.float32)
        voxel_data[idx, n_resp:] = non_responders[i, j, k, :].astype(np.float32)

    # Use vectorized t-test functions
    if test_type == 'paired':
        t_stats_1d, p_values_1d = vectorized_ttest_rel(
            voxel_data, n_resp, alternative=alternative
        )
    else:
        t_stats_1d, p_values_1d = vectorized_ttest_ind(
            voxel_data, n_resp, n_non_resp, alternative=alternative
        )

    # Map results back to 3D volume coordinates
    for idx, coord in enumerate(valid_coords):
        i, j, k = coord
        t_statistics[i, j, k] = t_stats_1d[idx]
        p_values[i, j, k] = p_values_1d[idx]

    return p_values, t_statistics, valid_mask


def _run_single_permutation(test_data, test_coords, n_resp, n_total, cluster_threshold,
                           valid_mask, p_values_shape, test_type='unpaired',
                           alternative='two-sided', cluster_stat='size',
                           seed=None, return_indices=False):
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
    
    if test_type == 'paired':
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
    if test_type == 'paired':
        t_stats_1d, p_values_1d = vectorized_ttest_rel(
            perm_test_data, n_resp, alternative=alternative
        )
    else:
        t_stats_1d, p_values_1d = vectorized_ttest_ind(
            perm_test_data, n_resp, n_total - n_resp, alternative=alternative
        )

    # Map results back to 3D volume coordinates
    for idx, coord in enumerate(test_coords):
        i, j, k = coord[0], coord[1], coord[2]
        perm_t_statistics[i, j, k] = t_stats_1d[idx]
        perm_p_values[i, j, k] = p_values_1d[idx]
    
    # Find clusters in permuted data
    perm_mask = (perm_p_values < cluster_threshold) & valid_mask
    perm_labeled, perm_n_clusters = label(perm_mask)
    
    # Calculate both cluster size and mass for correlation analysis
    if perm_n_clusters > 0:
        # Always calculate both for correlation analysis
        # Filter out single voxel clusters
        perm_cluster_sizes = []
        perm_cluster_masses = []
        
        for cid in range(1, perm_n_clusters + 1):
            cluster_size = np.sum(perm_labeled == cid)
            # Only consider clusters with more than 1 voxel
            if cluster_size > 1:
                perm_cluster_sizes.append(cluster_size)
                perm_cluster_masses.append(np.sum(perm_t_statistics[perm_labeled == cid]))
        
        if perm_cluster_sizes:  # If we have any multi-voxel clusters
            max_cluster_size = max(perm_cluster_sizes)
            max_cluster_mass = max(perm_cluster_masses)
            
            # Select the statistic to return based on cluster_stat
            if cluster_stat == 'size':
                max_cluster_stat = max_cluster_size
            elif cluster_stat == 'mass':
                max_cluster_stat = max_cluster_mass
            else:
                raise ValueError(f"cluster_stat must be 'size' or 'mass', got '{cluster_stat}'")
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


def cluster_based_correction(responders, non_responders, p_values, valid_mask,
                            cluster_threshold=0.01, n_permutations=500, alpha=0.05,
                            test_type='unpaired', alternative='two-sided', cluster_stat='size',
                            t_statistics=None, n_jobs=-1, verbose=True,
                            logger=None, save_permutation_log=False, permutation_log_file=None,
                            subject_ids_resp=None, subject_ids_non_resp=None):
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
    if cluster_stat not in ['size', 'mass']:
        raise ValueError(f"cluster_stat must be 'size' or 'mass', got '{cluster_stat}'")
    
    # Check that t_statistics is provided if using cluster mass
    if cluster_stat == 'mass' and t_statistics is None:
        raise ValueError("t_statistics must be provided when cluster_stat='mass'")
    
    if verbose:
        header = f"\n{'='*70}\nCLUSTER-BASED PERMUTATION CORRECTION\n{'='*70}"
        if logger:
            logger.info(header)
        else:
            print(header)
        cluster_stat_name = "Cluster Size" if cluster_stat == 'size' else "Cluster Mass"
        config_info = f"Cluster statistic: {cluster_stat_name}\nCluster-forming threshold: p < {cluster_threshold}\nNumber of permutations: {n_permutations}\nCluster-level alpha: {alpha}"
        if logger:
            for line in config_info.split('\n'):
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
        empty_correlation_data = {
            'sizes': np.array([]),
            'masses': np.array([])
        }
        return np.zeros_like(p_values, dtype=int), cluster_threshold, [], np.array([]), [], empty_correlation_data
    
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
            cluster_mask = (labeled_array == cluster_id)
            size = np.sum(cluster_mask)
            
            if size > 1:  # Only multi-voxel clusters
                if cluster_stat == 'size':
                    stat_value = float(size)
                elif cluster_stat == 'mass':
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
            if cluster_stat == 'size':
                msg = f"\nTop {len(top_clusters)} clusters (largest: {top_clusters[0][2]:.0f} voxels)"
            else:
                msg = f"\nTop {len(top_clusters)} clusters (largest mass: {top_clusters[0][2]:.2f})"

            if logger:
                logger.info(msg)
            else:
                print(msg)

            for i, (cid, size, stat_value) in enumerate(top_clusters[:5], 1):
                if cluster_stat == 'size':
                    msg = f"  {i}. Cluster {cid}: {size} voxels"
                else:
                    msg = f"  {i}. Cluster {cid}: {size} voxels, mass = {stat_value:.2f}"
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
    track_indices = save_permutation_log and subject_ids_resp is not None and subject_ids_non_resp is not None
    
    if n_jobs == 1:
        # Sequential execution with progress bar
        null_max_cluster_stats = []
        null_max_cluster_sizes = []
        null_max_cluster_masses = []
        permutation_indices = [] if track_indices else None
        iterator = tqdm(range(n_permutations), desc="Permutations") if verbose else range(n_permutations)
        for perm in iterator:
            result = _run_single_permutation(
                test_data, test_coords, n_resp, n_total,
                cluster_threshold, valid_mask, p_values.shape,
                test_type=test_type,
                alternative=alternative,
                cluster_stat=cluster_stat,
                seed=seeds[perm],
                return_indices=track_indices
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
                test_data, test_coords, n_resp, n_total,
                cluster_threshold, valid_mask, p_values.shape,
                test_type=test_type,
                alternative=alternative,
                cluster_stat=cluster_stat,
                seed=seeds[perm],
                return_indices=track_indices
            ) for perm in range(n_permutations)
        )
        
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
    
    # Step 4: Determine cluster statistic threshold
    null_max_cluster_stats = np.array(null_max_cluster_stats)
    cluster_stat_threshold = np.percentile(null_max_cluster_stats, 100 * (1 - alpha))
    
    if verbose:
        stat_unit = "voxels" if cluster_stat == 'size' else "mass units"
        msg = f"\n{100*(1-alpha)}th percentile of null distribution: {cluster_stat_threshold:.2f} {stat_unit}\nNull distribution stats: min={np.min(null_max_cluster_stats):.2f}, mean={np.mean(null_max_cluster_stats):.2f}, max={np.max(null_max_cluster_stats):.2f}"
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
            permutation_info.append({
                'perm_num': perm_num,
                'perm_idx': permutation_indices[perm_num],
                'max_cluster_size': null_max_cluster_stats[perm_num]
            })
        
        save_permutation_details(permutation_info, permutation_log_file, 
                                subject_ids_resp, subject_ids_non_resp)
        
        if verbose:
            print(f"Saved permutation details to: {permutation_log_file}")
    
    # Step 5: Identify significant clusters
    sig_mask = np.zeros_like(p_values, dtype=int)
    sig_clusters = []
    
    # Process clusters and build significant mask directly from labeled array
    n_sig_printed = 0
    max_clusters_to_check = min(n_clusters, 10000)  # Safety limit
    
    if n_clusters > max_clusters_to_check and verbose:
        print(f"\nNote: Checking first {max_clusters_to_check} clusters for significance (out of {n_clusters} total)")
    
    for cluster_id in range(1, max_clusters_to_check + 1):
        # Find cluster size/mass efficiently
        cluster_mask = (labeled_array == cluster_id)
        size = np.sum(cluster_mask)
        
        if size > 1:  # Only multi-voxel clusters
            if cluster_stat == 'size':
                stat_value = float(size)
            elif cluster_stat == 'mass':
                stat_value = float(np.sum(t_statistics[cluster_mask]))
            
            # Check if significant
            if stat_value > cluster_stat_threshold:
                sig_mask[cluster_mask] = 1
                sig_clusters.append({
                    'id': cluster_id,
                    'size': size,
                    'stat_value': stat_value
                })
                if verbose and n_sig_printed < 10:  # Limit output for many clusters
                    if cluster_stat == 'size':
                        print(f"  ✓ Cluster {cluster_id} is SIGNIFICANT "
                              f"({size} voxels > {cluster_stat_threshold:.1f})")
                    else:
                        print(f"  ✓ Cluster {cluster_id} is SIGNIFICANT "
                              f"(mass = {stat_value:.2f} > {cluster_stat_threshold:.2f}, {size} voxels)")
                    n_sig_printed += 1
    
    if verbose:
        msg = f"\nNumber of significant clusters: {len(sig_clusters)}\nTotal significant voxels: {np.sum(sig_mask)}"
        if logger:
            logger.info(msg)
        else:
            print(msg)
    
    # Prepare correlation data
    correlation_data = {
        'sizes': np.array(null_max_cluster_sizes),
        'masses': np.array(null_max_cluster_masses)
    }
    
    # Return empty list for cluster_stats since we don't store all clusters anymore
    return sig_mask, cluster_stat_threshold, sig_clusters, null_max_cluster_stats, [], correlation_data


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
        cluster_mask = (labeled_array == cluster_id)
        cluster_size = np.sum(cluster_mask)
        
        # Get center of mass in voxel coordinates
        coords = np.argwhere(cluster_mask)
        com_voxel = np.mean(coords, axis=0)
        
        # Convert to MNI coordinates
        com_mni = nib.affines.apply_affine(affine, com_voxel)
        
        clusters.append({
            'cluster_id': cluster_id,
            'size': cluster_size,
            'center_voxel': com_voxel,
            'center_mni': com_mni
        })
    
    # Sort by size
    clusters = sorted(clusters, key=lambda x: x['size'], reverse=True)
    
    if verbose:
        print(f"Found {num_clusters} clusters")
        for c in clusters[:10]:  # Show top 10
            print(f"  Cluster {c['cluster_id']}: {c['size']} voxels, "
                  f"MNI center: ({c['center_mni'][0]:.1f}, {c['center_mni'][1]:.1f}, {c['center_mni'][2]:.1f})")
    
    return clusters

