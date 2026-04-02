#!/usr/bin/env simnibs_python
"""Nilearn-based plotting helpers for TI-Toolbox.

This package provides neuroimaging visualization utilities built on
`nilearn <https://nilearn.github.io/>`_, including multi-slice PDF
exports, glass-brain PNG exports, and interactive HTML surface views.

Public API
----------
NilearnVisualizer
    High-level class combining PDF, HTML, and glass-brain workflows.
create_pdf_entry_point / create_pdf_entry_point_group
    CLI-oriented helpers for multi-slice PDF generation.
create_glass_brain_entry_point / create_glass_brain_entry_point_group
    CLI-oriented helpers for glass-brain PNG generation.
create_html_entry_point
    CLI-oriented helper for interactive HTML surface reports.

See Also
--------
tit.plotting.ti_metrics : TI-specific metric plots (histograms, scatter).
tit.blender : Blender-based 3-D visualizations.
"""

# Package version
__version__ = "1.0.0"

# Import main functions for easy access
from .visualizer import NilearnVisualizer
from .img_slices import create_pdf_entry_point, create_pdf_entry_point_group
from .img_glass import (
    create_glass_brain_entry_point,
    create_glass_brain_entry_point_group,
)
from .html_report import create_html_entry_point

__all__ = [
    "NilearnVisualizer",
    "create_pdf_entry_point",
    "create_pdf_entry_point_group",
    "create_glass_brain_entry_point",
    "create_glass_brain_entry_point_group",
    "create_html_entry_point",
]
