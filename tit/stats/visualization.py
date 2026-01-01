"""
Stats visualization entry points.

The concrete plotting implementations live in `tit.plotting.matplotlib.stats`.
"""

from tit.plotting.matplotlib.stats import (
    plot_cluster_size_mass_correlation,
    plot_permutation_null_distribution,
)

__all__ = [
    "plot_permutation_null_distribution",
    "plot_cluster_size_mass_correlation",
]


