"""Nilearn-based plotting helpers for TI-Toolbox.

The figures behind the desktop's Nilearn Visuals panel (run as
``simnibs_python -m tit.plotting.nilearn config.json``) and the fsaverage
surface maps of a cluster-permutation result.

Public API
----------
NilearnVisualizer
    Multi-slice PDF of a group-averaged field with atlas outlines.
create_pdf_entry_point_group
    The runner's entry point to that PDF.
create_glass_brain_entry_point_group
    Glass-brain PDF of a group-averaged field.
render_fsaverage_map / render_surface_stats_result
    fsaverage surface maps (a per-vertex array, or a ``surface_stats.msh``).

See Also
--------
tit.plotting.ti_metrics : TI-specific metric plots (histograms, scatter).
tit.blender : Blender-based 3-D visualizations.
"""

from .visualizer import NilearnVisualizer
from .img_slices import create_pdf_entry_point_group
from .img_glass import create_glass_brain_entry_point_group
from .surface import render_fsaverage_map, render_surface_stats_result

__all__ = [
    "NilearnVisualizer",
    "create_pdf_entry_point_group",
    "create_glass_brain_entry_point_group",
    "render_fsaverage_map",
    "render_surface_stats_result",
]
