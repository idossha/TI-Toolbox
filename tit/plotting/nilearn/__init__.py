#!/usr/bin/env simnibs_python
"""
TI-Toolbox Nilearn plotting helpers.

This package contains "basic" neuroimaging plotting utilities (non-blender), including:
- Slice PDF exports
- Glass brain exports
- Interactive HTML views
"""

# Package version
__version__ = "1.0.0"

# Import main functions for easy access
from .visualizer import NilearnVisualizer
from .img_slices import create_pdf_entry_point, create_pdf_entry_point_group
from .img_glass import create_glass_brain_entry_point, create_glass_brain_entry_point_group
from .html_report import create_html_entry_point

__all__ = [
    'NilearnVisualizer',
    'create_pdf_entry_point',
    'create_pdf_entry_point_group',
    'create_glass_brain_entry_point',
    'create_glass_brain_entry_point_group',
    'create_html_entry_point',
]
