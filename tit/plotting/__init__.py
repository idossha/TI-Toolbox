"""Plotting utilities for TI-Toolbox.

Non-Blender visualization and figure-generation helpers including
intensity-vs-focality scatter plots, permutation null distributions, static
overlay images, and montage distribution plots.

Most functions use lazy imports so ``import tit.plotting`` does not pull
in matplotlib unless a plot function is actually called.
"""

from ._common import SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close
from .static_overlay import generate_static_overlay_images
from .stats import (
    plot_cluster_size_mass_correlation,
    plot_permutation_null_distribution,
)
from .ti_metrics import (
    plot_electrode_score_heatmap,
    plot_intensity_vs_focality,
    plot_montage_distributions,
    plot_montage_score_map,
)

__all__ = [
    "SaveFigOptions",
    "ensure_headless_matplotlib_backend",
    "savefig_close",
    "generate_static_overlay_images",
    "plot_permutation_null_distribution",
    "plot_cluster_size_mass_correlation",
    "plot_montage_distributions",
    "plot_intensity_vs_focality",
    "plot_montage_score_map",
    "plot_electrode_score_heatmap",
]
