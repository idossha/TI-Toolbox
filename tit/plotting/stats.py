"""
Matplotlib-based statistical plots.

These were previously implemented in `tit.stats.visualization` and are kept here to
encourage reuse across modules.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from ._common import SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close


def plot_permutation_null_distribution(
    null_distribution: np.ndarray,
    threshold: float,
    observed_clusters: Sequence[Mapping[str, float]],
    output_file: str,
    *,
    alpha: float = 0.05,
    cluster_stat: str = "size",
    dpi: int = 300,
) -> str:
    """
    Plot permutation null distribution with threshold and observed clusters.
    """
    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_style("whitegrid")
    sns.set_context("notebook", font_scale=1.0)

    fig, ax = plt.subplots(figsize=(10, 6))

    # Labels based on cluster statistic
    if cluster_stat == "size":
        x_label = "Maximum Cluster Size (voxels)"
        title = "Permutation Null Distribution of Maximum Cluster Sizes"
        threshold_label = f"Discrete Threshold (p<{alpha}): {threshold:.1f} voxels"
    else:
        x_label = "Maximum Cluster Mass (sum of t-statistics)"
        title = "Permutation Null Distribution of Maximum Cluster Mass"
        threshold_label = f"Discrete Threshold (p<{alpha}): {threshold:.2f}"

    # Histogram
    if sns is not None:
        sns.histplot(
            null_distribution,
            bins=200,
            alpha=0.7,
            color="gray",
            edgecolor="black",
            label="Null Distribution",
            ax=ax,
        )
    else:
        ax.hist(null_distribution, bins=200, alpha=0.7, color="gray", edgecolor="black", label="Null Distribution")

    # Threshold line
    ax.axvline(threshold, color="red", linestyle="--", linewidth=2, label=threshold_label)

    # Observed clusters
    sig_plotted = False
    nonsig_plotted = False
    for cluster in observed_clusters:
        stat_value = float(cluster["stat_value"])
        p_value = cluster.get("p_value", None)
        if p_value is not None:
            is_significant = float(p_value) < 0.05
        else:
            is_significant = stat_value > threshold

        color = "green" if is_significant else "orange"
        label = None
        if is_significant and not sig_plotted:
            label = "Significant Clusters (p<0.05)"
            sig_plotted = True
        elif (not is_significant) and (not nonsig_plotted):
            label = "Non-significant Clusters (p≥0.05)"
            nonsig_plotted = True

        ax.axvline(stat_value, color=color, linestyle="-", linewidth=2, alpha=0.7, label=label)

    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    return savefig_close(fig, output_file, fmt="pdf", opts=SaveFigOptions(dpi=dpi))


def plot_cluster_size_mass_correlation(
    cluster_sizes: np.ndarray,
    cluster_masses: np.ndarray,
    output_file: str,
    *,
    dpi: int = 300,
) -> str | None:
    """
    Plot correlation between cluster size and cluster mass from permutation null distribution.
    """
    from scipy.stats import pearsonr

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt

    import seaborn as sns

    sns.set_style("whitegrid")
    sns.set_context("notebook", font_scale=1.0)

    # Remove zeros
    mask = (cluster_sizes > 0) & (cluster_masses > 0)
    sizes_nonzero = cluster_sizes[mask]
    masses_nonzero = cluster_masses[mask]
    if len(sizes_nonzero) < 2:
        return None

    r_value, p_value = pearsonr(sizes_nonzero, masses_nonzero)

    fig, ax = plt.subplots(figsize=(10, 8))

    if sns is not None:
        sns.regplot(
            x=sizes_nonzero,
            y=masses_nonzero,
            ax=ax,
            scatter_kws={"alpha": 0.6, "s": 50, "color": "steelblue", "edgecolors": "black", "linewidths": 0.5},
            line_kws={"color": "red", "linewidth": 2},
        )
    else:
        ax.scatter(sizes_nonzero, masses_nonzero, alpha=0.6, s=50, c="steelblue", edgecolors="black", linewidths=0.5)
        z = np.polyfit(sizes_nonzero, masses_nonzero, 1)
        xs = np.linspace(float(np.min(sizes_nonzero)), float(np.max(sizes_nonzero)), 100)
        ax.plot(xs, z[0] * xs + z[1], color="red", linewidth=2)

    z = np.polyfit(sizes_nonzero, masses_nonzero, 1)
    ax.set_xlabel("Maximum Cluster Size (voxels)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Maximum Cluster Mass (sum of t-statistics)", fontsize=12, fontweight="bold")
    ax.set_title(
        f"Cluster Size vs Cluster Mass Correlation\nPearson r = {r_value:.3f} (p = {p_value:.2e})",
        fontsize=14,
        fontweight="bold",
    )

    textstr = (
        f"n = {len(sizes_nonzero)} permutations\n"
        f"r = {r_value:.3f}\n"
        f"p = {p_value:.2e}\n"
        f"Linear fit: y = {z[0]:.2f}x + {z[1]:.2f}"
    )
    props = dict(boxstyle="round", facecolor="wheat", alpha=0.8)
    ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=11, verticalalignment="top", bbox=props)

    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    return savefig_close(fig, output_file, fmt="pdf", opts=SaveFigOptions(dpi=dpi))


