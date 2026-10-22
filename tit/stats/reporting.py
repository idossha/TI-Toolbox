"""Plain-text report generators for voxelwise statistical analyses.

Writes human-readable summary files covering sample information,
cluster-based permutation results, and atlas overlap tables.

Public API
----------
generate_summary
    Summary report for a two-group comparison analysis.
generate_correlation_summary
    Summary report for a voxelwise correlation (ACES-style) analysis.

See Also
--------
tit.stats.permutation : The pipelines that call both generators.
"""

import numpy as np

#: Stands in for the cluster threshold when no permutation ran.
_NO_THRESHOLD = "no candidate clusters; threshold not computed"


def _write_threshold(f, cluster_stat, threshold):
    """The cluster threshold line, or why there is none (*threshold* is ``None``)."""
    label = (
        "Cluster size threshold" if cluster_stat == "size" else "Cluster mass threshold"
    )
    if threshold is None:
        f.write(f"{label}: {_NO_THRESHOLD}\n")
        f.write(
            "Null-distribution figure: not drawn (no cluster formed at the "
            "cluster-forming threshold, so no permutations ran)\n"
        )
    elif cluster_stat == "size":
        f.write(f"{label}: {threshold:.1f} voxels\n")
    else:
        f.write(f"{label}: {threshold:.2f}\n")


def _by_extremeness(clusters):
    """Clusters ordered by ``|stat_value|`` (size when absent), largest first."""
    return sorted(clusters, key=lambda c: -abs(c.get("stat_value", c["size"])))


def _sort_label(cluster_stat):
    if cluster_stat == "mass":
        return "by |cluster mass|, largest first"
    return "by cluster size, largest first"


def _write_cluster_line(f, i, c, cluster_stat):
    """``i. Cluster <id>: <n> voxels[, mass = <signed>][, p = <p>]``."""
    f.write(f"{i}. Cluster {c['cluster_id']}: {c['size']} voxels")
    if cluster_stat == "mass" and "stat_value" in c:
        f.write(f", mass = {c['stat_value']:.2f}")
    if "p_value" in c:
        f.write(f", p = {c['p_value']:.4f}")
    f.write("\n")


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
    """Write a plain-text summary report for a two-group comparison.

    The report includes analysis parameters, sample sizes, significant
    voxel counts, the top-10 significant clusters (most extreme first, each
    with its signed mass and permutation p-value), and atlas overlap tables.

    Parameters
    ----------
    config : GroupComparisonConfig
        Fully specified group-comparison configuration.
    responders : numpy.ndarray
        Electric-field data for group 1, shape ``(X, Y, Z, n_group1)``.
    non_responders : numpy.ndarray
        Electric-field data for group 2, shape ``(X, Y, Z, n_group2)``.
    sig_mask : numpy.ndarray
        Binary mask of significant voxels, shape ``(X, Y, Z)``.
    correction_threshold : float or None
        Cluster-statistic threshold from the permutation distribution;
        ``None`` when no candidate cluster formed, so no permutation ran.
    clusters : list of dict
        The significant clusters
        (:func:`tit.stats.engine.significant_cluster_table`): at least
        ``'cluster_id'``, ``'size'`` and ``'center_mni'``, plus
        ``'stat_value'`` (signed mass, or size) and ``'p_value'``.
    atlas_results : dict
        Mapping of atlas name to list of region overlap dicts.
    output_file : str
        Destination path for the text report.
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
        _write_threshold(f, cluster_stat, correction_threshold)

        from tit.cpu import resolve_n_jobs

        n_jobs_actual = resolve_n_jobs(config.n_jobs)
        if n_jobs_actual == 1:
            f.write("Parallel processing: Sequential (1 core)\n")
        else:
            f.write(f"Parallel processing: {n_jobs_actual} cores\n")
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
            f.write(f"TOP 10 CLUSTERS ({_sort_label(cluster_stat)}):\n")
            f.write("-" * 70 + "\n")
            for i, c in enumerate(_by_extremeness(clusters)[:10], 1):
                _write_cluster_line(f, i, c, cluster_stat)
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
    alternative="two-sided",
):
    """Write a plain-text summary report for a correlation analysis.

    The report covers analysis parameters, effect-size distribution,
    per-subject details, correlation statistics in significant voxels,
    cluster listings, and atlas overlap tables.

    Parameters
    ----------
    config : CorrelationConfig
        Fully specified correlation configuration.
    subject_data : numpy.ndarray
        Electric-field magnitude data, shape ``(X, Y, Z, n_subjects)``.
    effect_sizes : numpy.ndarray
        Continuous outcome measures, shape ``(n_subjects,)``.
    r_values : numpy.ndarray
        Voxelwise correlation map, shape ``(X, Y, Z)``.
    sig_mask : numpy.ndarray
        Binary mask of significant voxels, shape ``(X, Y, Z)``.
    cluster_threshold : float or None
        Cluster-statistic threshold from the permutation distribution;
        ``None`` when no candidate cluster formed, so no permutation ran.
    clusters : list of dict
        Each dict contains ``'cluster_id'``, ``'size'``, ``'center_mni'``,
        and optionally ``'stat_value'``, ``'p_value'``, ``'mean_r'`` /
        ``'peak_r'`` (``peak_r`` is the ``r`` of largest magnitude, sign kept).
    atlas_results : dict
        Mapping of atlas name to list of region overlap dicts.
    output_file : str
        Destination path for the text report.
    subject_ids : list of str, optional
        Subject identifiers (printed per-row when provided).
    weights : numpy.ndarray or None, optional
        Per-subject weights, aligned with *effect_sizes*.  When provided the
        weight distribution is included in the report.
    alternative : str, optional
        The alternative hypothesis the permutation test ran with
        (``"two-sided"``, ``"greater"`` or ``"less"``); stated in the report.
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

        f.write(f"Alternative hypothesis: {alternative}\n")
        f.write(f"Cluster Statistic: {cluster_stat_name}\n")
        f.write(f"Cluster-forming threshold: p < {config.cluster_threshold}\n")
        f.write(f"Number of permutations: {config.n_permutations}\n")
        f.write(f"Cluster-level alpha: {config.alpha}\n")
        _write_threshold(f, cluster_stat, cluster_threshold)
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
            # By row: a subject id can repeat (two simulations of one person).
            f.write("\nPer-Subject Effect Sizes:\n")
            for i, (sid, es) in enumerate(zip(subject_ids, effect_sizes)):
                weight_str = "" if weights is None else f", weight={weights[i]:.2f}"
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
            sig_r = np.ravel(r_values[sig_bool])
            # Peak = largest |r|, sign kept: a negative cluster's peak is its most negative r.
            peak_r = sig_r[np.argmax(np.abs(sig_r))]

            f.write("CORRELATION STATISTICS IN SIGNIFICANT VOXELS:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean r: {np.mean(sig_r):.4f}\n")
            f.write(f"Peak r: {peak_r:.4f}\n")
            f.write(f"Min r:  {np.min(sig_r):.4f}\n")
            f.write(f"Max r:  {np.max(sig_r):.4f}\n\n")

            # E-field statistics in significant voxels
            mean_efield = np.mean(subject_data[sig_bool, :])
            max_efield = np.max(subject_data[sig_bool, :])
            f.write("E-FIELD STATISTICS IN SIGNIFICANT VOXELS:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean E-field: {mean_efield:.6f}\n")
            f.write(f"Max E-field:  {max_efield:.6f}\n\n")

        if clusters:
            f.write(f"SIGNIFICANT CLUSTERS ({_sort_label(cluster_stat)}):\n")
            f.write("-" * 70 + "\n")
            for i, c in enumerate(_by_extremeness(clusters)[:20], 1):
                f.write("\n")
                _write_cluster_line(f, i, c, cluster_stat)
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
        f.write(f"  Higher E-field → Higher {config.effect_metric}\n")
        f.write("Negative correlations (r < 0):\n")
        f.write(f"  Higher E-field → Lower {config.effect_metric}\n\n")
        if alternative == "two-sided":
            f.write(
                "Note: the test is two-sided. Clusters of positive and of negative r\n"
                "are formed separately and both are tested; the sign of a cluster's\n"
                "Mean r / Peak r says which direction it is.\n\n"
            )
        else:
            direction = "positive" if alternative == "greater" else "negative"
            f.write(
                f"Note: the test is one-sided ({alternative}): only {direction}\n"
                "correlations can form a cluster.\n\n"
            )

        f.write("References:\n")
        f.write("  - Wischnewski et al. (2021) - ACES approach\n")
        f.write("  - Maris & Oostenveld (2007) - Cluster-based permutation\n")
