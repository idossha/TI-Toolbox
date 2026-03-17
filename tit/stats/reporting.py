"""
Report generation utilities for neuroimaging analysis

This module contains functions for:
- Generating comprehensive summary reports
"""

import numpy as np


def generate_summary(
    config,
    responders,
    non_responders,
    sig_mask,
    correction_threshold,
    clusters,
    atlas_results,
    output_file,
):
    """Generate comprehensive summary report for group comparison.

    Parameters
    ----------
    config : GroupComparisonConfig
        Fully specified group-comparison configuration.
    responders : ndarray
        Responder data (group 1).
    non_responders : ndarray
        Non-responder data (group 2).
    sig_mask : ndarray
        Binary mask of significant voxels.
    correction_threshold : float
        Threshold used for multiple comparison correction.
    clusters : list
        List of cluster dictionaries.
    atlas_results : dict
        Atlas overlap results.
    output_file : str
        Path to output summary file.
    """
    cluster_stat = config.cluster_stat.value
    cluster_stat_name = "Cluster Size" if cluster_stat == "size" else "Cluster Mass"

    with open(output_file, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("VOXELWISE STATISTICAL ANALYSIS SUMMARY\n")
        f.write("=" * 70 + "\n\n")

        f.write("ANALYSIS DETAILS:\n")
        f.write("-" * 70 + "\n")
        test_name = (
            "Paired t-test"
            if config.test_type.value == "paired"
            else "Unpaired (Independent Samples) t-test"
        )
        f.write(f"Statistical Test: {test_name}\n")

        f.write("Multiple Comparison Correction: Cluster-based Permutation\n")
        f.write(f"Cluster statistic: {cluster_stat_name}\n")
        f.write(
            f"Cluster-forming threshold: p < {config.cluster_threshold} (uncorrected)\n"
        )
        f.write(f"Number of permutations: {config.n_permutations}\n")
        f.write(f"Cluster-level alpha: {config.alpha}\n")

        if cluster_stat == "size":
            f.write(f"Cluster size threshold: {correction_threshold:.1f} voxels\n")
        else:
            f.write(f"Cluster mass threshold: {correction_threshold:.2f}\n")

        n_jobs = config.n_jobs
        if n_jobs == -1:
            import multiprocessing

            n_jobs_actual = multiprocessing.cpu_count()
            f.write(f"Parallel processing: {n_jobs_actual} cores\n")
        elif n_jobs == 1:
            f.write("Parallel processing: Sequential (1 core)\n")
        else:
            f.write(f"Parallel processing: {n_jobs} cores\n")
        f.write("\n")

        f.write("SAMPLE INFORMATION:\n")
        f.write("-" * 70 + "\n")
        f.write(f"Number of {config.group1_name}: {responders.shape[-1]}\n")
        f.write(f"Number of {config.group2_name}: {non_responders.shape[-1]}\n")
        f.write(
            f"Total Subjects: {responders.shape[-1] + non_responders.shape[-1]}\n\n"
        )

        f.write("RESULTS:\n")
        f.write("-" * 70 + "\n")
        n_sig = np.sum(sig_mask)
        f.write(f"Number of Significant Voxels: {n_sig}\n")

        if n_sig > 0:
            # Calculate mean values in significant voxels
            sig_bool = sig_mask.astype(bool)
            group1_mean = np.mean(responders[sig_bool, :])
            group2_mean = np.mean(non_responders[sig_bool, :])

            f.write(f"\nMean {config.value_metric} in Significant Voxels:\n")
            f.write(f"  {config.group1_name}: {group1_mean:.4f}\n")
            f.write(f"  {config.group2_name}: {group2_mean:.4f}\n")
            f.write(
                f"  Difference ({config.group1_name} - {config.group2_name}): "
                f"{group1_mean - group2_mean:.4f}\n"
            )

        f.write(f"\nNumber of Clusters: {len(clusters)}\n\n")

        if clusters:
            sort_label = "by statistic" if cluster_stat == "mass" else "by size"
            f.write(f"TOP 10 CLUSTERS ({sort_label}):\n")
            f.write("-" * 70 + "\n")
            for i, c in enumerate(clusters[:10], 1):
                f.write(f"{i}. Cluster {c['cluster_id']}: {c['size']} voxels")
                if cluster_stat == "mass" and "stat_value" in c:
                    f.write(f", mass = {c['stat_value']:.2f}")
                f.write("\n")
                f.write(
                    f"   MNI Center: ({c['center_mni'][0]:.1f}, "
                    f"{c['center_mni'][1]:.1f}, {c['center_mni'][2]:.1f})\n"
                )

        f.write("\n" + "=" * 70 + "\n")
        f.write("ATLAS OVERLAP ANALYSIS\n")
        f.write("=" * 70 + "\n\n")

        for atlas_name, region_counts in atlas_results.items():
            f.write(f"\n{atlas_name}\n")
            f.write("-" * 70 + "\n")

            if region_counts:
                f.write(
                    f"Number of regions with significant voxels: "
                    f"{len(region_counts)}\n\n"
                )
                f.write("Top 20 regions:\n")
                for i, r in enumerate(region_counts[:20], 1):
                    pct = 100 * r["overlap_voxels"] / r["region_size"]
                    f.write(
                        f"{i:2d}. Region {r['region_id']:3d}: "
                        f"{r['overlap_voxels']:4d} voxels ({pct:5.1f}% of region)\n"
                    )
            else:
                f.write("No overlapping regions found.\n")


def generate_correlation_summary(
    config,
    subject_data,
    effect_sizes,
    r_values,
    sig_mask,
    cluster_threshold,
    clusters,
    atlas_results,
    output_file,
    *,
    subject_ids=None,
    weights=None,
):
    """Generate comprehensive summary report for correlation analysis.

    Parameters
    ----------
    config : CorrelationConfig
        Fully specified correlation configuration.
    subject_data : ndarray (x, y, z, n_subjects)
        Electric field magnitude data.
    effect_sizes : ndarray (n_subjects,)
        Continuous outcome measures.
    r_values : ndarray (x, y, z)
        Correlation map.
    sig_mask : ndarray (x, y, z)
        Binary mask of significant voxels.
    cluster_threshold : float
        Cluster statistic threshold from permutation.
    clusters : list
        List of cluster dictionaries.
    atlas_results : dict
        Atlas overlap results.
    output_file : str
        Path to output summary file.
    subject_ids : list, optional
        List of subject IDs.
    weights : ndarray, optional
        Subject weights (if used).
    """
    cluster_stat = config.cluster_stat.value
    cluster_stat_name = "Cluster Size" if cluster_stat == "size" else "Cluster Mass"
    n_subjects = len(effect_sizes)

    with open(output_file, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("CORRELATION-BASED CLUSTER PERMUTATION ANALYSIS SUMMARY\n")
        f.write("(ACES-style analysis for continuous outcomes)\n")
        f.write("=" * 70 + "\n\n")

        f.write("ANALYSIS DETAILS:\n")
        f.write("-" * 70 + "\n")
        corr_type = config.correlation_type.value.capitalize()
        weighted_str = " (Weighted)" if weights is not None else ""
        f.write(f"Correlation Type: {corr_type}{weighted_str}\n")
        f.write(f"Outcome Measure: {config.effect_metric}\n")

        f.write(f"Cluster Statistic: {cluster_stat_name}\n")
        f.write(
            f"Cluster-forming threshold: p < {config.cluster_threshold}\n"
        )
        f.write(f"Number of permutations: {config.n_permutations}\n")
        f.write(f"Cluster-level alpha: {config.alpha}\n")

        if cluster_stat == "size":
            f.write(f"Cluster size threshold: {cluster_threshold:.1f} voxels\n")
        else:
            f.write(f"Cluster mass threshold: {cluster_threshold:.2f}\n")
        f.write("\n")

        f.write("SAMPLE INFORMATION:\n")
        f.write("-" * 70 + "\n")
        f.write(f"Number of Subjects: {n_subjects}\n")
        if subject_ids:
            f.write(f"Subject IDs: {', '.join(str(s) for s in subject_ids)}\n")
        f.write("\n")

        f.write("EFFECT SIZE DISTRIBUTION:\n")
        f.write("-" * 70 + "\n")
        f.write(f"Mean: {np.mean(effect_sizes):.4f}\n")
        f.write(f"Std:  {np.std(effect_sizes):.4f}\n")
        f.write(f"Min:  {np.min(effect_sizes):.4f}\n")
        f.write(f"Max:  {np.max(effect_sizes):.4f}\n")
        f.write(f"Range: {np.max(effect_sizes) - np.min(effect_sizes):.4f}\n")

        if subject_ids:
            f.write("\nPer-Subject Effect Sizes:\n")
            for sid, es in zip(subject_ids, effect_sizes):
                weight_str = ""
                if weights is not None:
                    idx = list(subject_ids).index(sid)
                    weight_str = f", weight={weights[idx]:.2f}"
                f.write(f"  {sid}: {es:.4f}{weight_str}\n")
        f.write("\n")

        if weights is not None:
            f.write("WEIGHT DISTRIBUTION:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean weight: {np.mean(weights):.4f}\n")
            f.write(f"Min weight:  {np.min(weights):.4f}\n")
            f.write(f"Max weight:  {np.max(weights):.4f}\n\n")

        f.write("RESULTS:\n")
        f.write("-" * 70 + "\n")
        n_sig = np.sum(sig_mask)
        f.write(f"Number of Significant Voxels: {n_sig}\n")
        f.write(f"Number of Significant Clusters: {len(clusters)}\n\n")

        if n_sig > 0:
            sig_bool = sig_mask.astype(bool)
            mean_r = np.mean(r_values[sig_bool])
            max_r = np.max(r_values[sig_bool])
            min_r = np.min(r_values[sig_bool])

            f.write("CORRELATION STATISTICS IN SIGNIFICANT VOXELS:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean r: {mean_r:.4f}\n")
            f.write(f"Peak r: {max_r:.4f}\n")
            f.write(f"Min r:  {min_r:.4f}\n\n")

            # E-field statistics in significant voxels
            mean_efield = np.mean(subject_data[sig_bool, :])
            max_efield = np.max(subject_data[sig_bool, :])
            f.write("E-FIELD STATISTICS IN SIGNIFICANT VOXELS:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean E-field: {mean_efield:.6f}\n")
            f.write(f"Max E-field:  {max_efield:.6f}\n\n")

        if clusters:
            f.write("SIGNIFICANT CLUSTERS:\n")
            f.write("-" * 70 + "\n")
            for i, c in enumerate(clusters[:20], 1):
                f.write(f"\n{i}. Cluster {c['cluster_id']}: {c['size']} voxels\n")
                f.write(
                    f"   MNI Center: ({c['center_mni'][0]:.1f}, "
                    f"{c['center_mni'][1]:.1f}, {c['center_mni'][2]:.1f})\n"
                )
                if "mean_r" in c:
                    f.write(f"   Mean r: {c['mean_r']:.4f}\n")
                if "peak_r" in c:
                    f.write(f"   Peak r: {c['peak_r']:.4f}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("ATLAS OVERLAP ANALYSIS\n")
        f.write("=" * 70 + "\n")

        for atlas_name, region_counts in atlas_results.items():
            f.write(f"\n{atlas_name}\n")
            f.write("-" * 70 + "\n")

            if region_counts:
                f.write(
                    f"Number of regions with significant voxels: {len(region_counts)}\n\n"
                )
                f.write("Top 20 regions:\n")
                for i, r in enumerate(region_counts[:20], 1):
                    pct = 100 * r["overlap_voxels"] / r["region_size"]
                    f.write(
                        f"{i:2d}. Region {r['region_id']:3d}: "
                        f"{r['overlap_voxels']:4d} voxels ({pct:5.1f}% of region)\n"
                    )
            else:
                f.write("No overlapping regions found.\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("INTERPRETATION NOTES\n")
        f.write("=" * 70 + "\n\n")
        f.write(
            "This analysis identifies brain regions where electric field magnitude\n"
        )
        f.write(f"correlates with {config.effect_metric}.\n\n")
        f.write("Positive correlations (r > 0):\n")
        f.write(f"  Higher E-field → Higher {config.effect_metric}\n\n")
        f.write("Note: This analysis tests positive correlations only (as per ACES).\n")
        f.write(
            "To find regions with negative correlations, invert your effect sizes\n"
        )
        f.write("(multiply by -1) and re-run the analysis.\n\n")

        f.write("References:\n")
        f.write("  - Wischnewski et al. (2021) - ACES approach\n")
        f.write("  - Maris & Oostenveld (2007) - Cluster-based permutation\n")

