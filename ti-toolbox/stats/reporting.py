"""
Report generation utilities for neuroimaging analysis

This module contains functions for:
- Generating comprehensive summary reports
"""

import numpy as np


def generate_summary(responders, non_responders, sig_mask, correction_threshold, 
                    clusters, atlas_results, output_file, 
                    correction_method="cluster",
                    params=None,
                    group1_name="Responders",
                    group2_name="Non-Responders",
                    value_metric="Current Intensity",
                    test_type="unpaired",
                    observed_cluster_sizes=None):
    """
    Generate comprehensive summary report
    
    Parameters:
    -----------
    responders : ndarray
        Responder data (group 1)
    non_responders : ndarray
        Non-responder data (group 2)
    sig_mask : ndarray
        Binary mask of significant voxels
    correction_threshold : float
        Threshold used for multiple comparison correction
    clusters : list
        List of cluster dictionaries
    atlas_results : dict
        Atlas overlap results
    output_file : str
        Path to output summary file
    correction_method : str
        Method used: 'cluster' or 'fdr'
    params : dict, optional
        Dictionary of analysis parameters (cluster_threshold, n_permutations, alpha, etc.)
        If None, uses defaults
    group1_name : str
        Name for first group (default: "Responders")
    group2_name : str
        Name for second group (default: "Non-Responders")
    value_metric : str
        Name of the metric being compared (default: "Current Intensity")
    test_type : str
        Type of t-test used: 'paired' or 'unpaired' (default: "unpaired")
    observed_cluster_sizes : list, optional
        List of observed cluster sizes (before permutation correction) sorted largest to smallest
    """
    # Set default parameters if not provided
    if params is None:
        params = {
            'cluster_threshold': 0.01,
            'n_permutations': 500,
            'alpha': 0.05
        }
    
    # Extract parameters with defaults
    cluster_threshold_param = params.get('cluster_threshold', 0.01)
    n_permutations = params.get('n_permutations', 500)
    alpha = params.get('alpha', 0.05)
    cluster_stat = params.get('cluster_stat', 'size')
    
    with open(output_file, 'w') as f:
        f.write("="*70 + "\n")
        f.write("VOXELWISE STATISTICAL ANALYSIS SUMMARY\n")
        f.write("="*70 + "\n\n")
        
        f.write("ANALYSIS DETAILS:\n")
        f.write("-" * 70 + "\n")
        test_name = "Paired t-test" if test_type == "paired" else "Unpaired (Independent Samples) t-test"
        f.write(f"Statistical Test: {test_name}\n")
        
        if correction_method == "cluster":
            f.write(f"Multiple Comparison Correction: Cluster-based Permutation\n")
            cluster_stat_name = "Cluster Size" if cluster_stat == 'size' else "Cluster Mass"
            f.write(f"Cluster statistic: {cluster_stat_name}\n")
            f.write(f"Cluster-forming threshold: p < {cluster_threshold_param} (uncorrected)\n")
            f.write(f"Number of permutations: {n_permutations}\n")
            f.write(f"Cluster-level alpha: {alpha}\n")
            
            if cluster_stat == 'size':
                f.write(f"Cluster size threshold: {correction_threshold:.1f} voxels\n")
            else:
                f.write(f"Cluster mass threshold: {correction_threshold:.2f}\n")
            if 'n_jobs' in params:
                n_jobs = params['n_jobs']
                if n_jobs == -1:
                    import multiprocessing
                    n_jobs_actual = multiprocessing.cpu_count()
                    f.write(f"Parallel processing: {n_jobs_actual} cores\n")
                elif n_jobs == 1:
                    f.write(f"Parallel processing: Sequential (1 core)\n")
                else:
                    f.write(f"Parallel processing: {n_jobs} cores\n")
            f.write("\n")
        else:
            f.write(f"Multiple Comparison Correction: FDR (False Discovery Rate)\n")
            f.write(f"Significance Level: alpha = {alpha}\n")
            f.write(f"FDR-corrected p-value threshold: {correction_threshold:.6f}\n\n")
        
        # Add observed clusters information if provided
        if observed_cluster_sizes is not None and len(observed_cluster_sizes) > 0:
            f.write("OBSERVED CLUSTERS (BEFORE PERMUTATION CORRECTION):\n")
            f.write("-" * 70 + "\n")
            f.write(f"Total clusters at p < {cluster_threshold_param}: {len(observed_cluster_sizes)}\n")
            f.write(f"Largest observed cluster: {observed_cluster_sizes[0]} voxels\n")
            f.write(f"Total voxels in all clusters: {sum(observed_cluster_sizes)}\n\n")
            
            f.write("Top 10 Largest Observed Clusters:\n")
            for i, size in enumerate(observed_cluster_sizes[:10], 1):
                f.write(f"  {i:2d}. {size:6d} voxels\n")
            f.write("\n")
        
        f.write("SAMPLE INFORMATION:\n")
        f.write("-" * 70 + "\n")
        f.write(f"Number of {group1_name}: {responders.shape[-1]}\n")
        f.write(f"Number of {group2_name}: {non_responders.shape[-1]}\n")
        f.write(f"Total Subjects: {responders.shape[-1] + non_responders.shape[-1]}\n\n")
        
        f.write("RESULTS:\n")
        f.write("-" * 70 + "\n")
        n_sig = np.sum(sig_mask)
        f.write(f"Number of Significant Voxels: {n_sig}\n")
        
        if n_sig > 0:
            # Calculate mean values in significant voxels
            sig_bool = sig_mask.astype(bool)
            group1_mean = np.mean(responders[sig_bool, :])
            group2_mean = np.mean(non_responders[sig_bool, :])
            
            f.write(f"\nMean {value_metric} in Significant Voxels:\n")
            f.write(f"  {group1_name}: {group1_mean:.4f}\n")
            f.write(f"  {group2_name}: {group2_mean:.4f}\n")
            f.write(f"  Difference ({group1_name} - {group2_name}): {group1_mean - group2_mean:.4f}\n")
        
        f.write(f"\nNumber of Clusters: {len(clusters)}\n\n")
        
        if clusters:
            sort_label = "by statistic" if cluster_stat == 'mass' else "by size"
            f.write(f"TOP 10 CLUSTERS ({sort_label}):\n")
            f.write("-" * 70 + "\n")
            for i, c in enumerate(clusters[:10], 1):
                f.write(f"{i}. Cluster {c['cluster_id']}: {c['size']} voxels")
                if cluster_stat == 'mass' and 'stat_value' in c:
                    f.write(f", mass = {c['stat_value']:.2f}")
                f.write("\n")
                f.write(f"   MNI Center: ({c['center_mni'][0]:.1f}, "
                       f"{c['center_mni'][1]:.1f}, {c['center_mni'][2]:.1f})\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("ATLAS OVERLAP ANALYSIS\n")
        f.write("="*70 + "\n\n")
        
        for atlas_name, region_counts in atlas_results.items():
            f.write(f"\n{atlas_name}\n")
            f.write("-" * 70 + "\n")
            
            if region_counts:
                f.write(f"Number of regions with significant voxels: {len(region_counts)}\n\n")
                f.write("Top 20 regions:\n")
                for i, r in enumerate(region_counts[:20], 1):
                    pct = 100 * r['overlap_voxels'] / r['region_size']
                    f.write(f"{i:2d}. Region {r['region_id']:3d}: "
                           f"{r['overlap_voxels']:4d} voxels ({pct:5.1f}% of region)\n")
            else:
                f.write("No overlapping regions found.\n")
    
    print(f"\nSummary written to: {output_file}")

