"""
Plotting utilities for TI-Toolbox.

This package contains non-blender visualization/plotting functionality.

Kept lightweight: most functions use lazy imports so importing `tit.plotting` does
not require matplotlib unless you actually call a plot function.
"""

from ._common import SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close
from .focality import plot_whole_head_roi_histogram
from .static_overlay import generate_static_overlay_images
from .stats import (
    plot_cluster_size_mass_correlation,
    plot_permutation_null_distribution,
)
from .ti_metrics import plot_intensity_vs_focality, plot_montage_distributions

__all__ = [
    "SaveFigOptions",
    "ensure_headless_matplotlib_backend",
    "savefig_close",
    "plot_whole_head_roi_histogram",
    "generate_static_overlay_images",
    "plot_permutation_null_distribution",
    "plot_cluster_size_mass_correlation",
    "plot_montage_distributions",
    "plot_intensity_vs_focality",
]
