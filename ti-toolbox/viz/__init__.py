#!/usr/bin/env python3
"""
TI-Toolbox Visualization Package
Provides tools for creating publication-ready visualizations of electric field distributions.
"""

# Package version
__version__ = "1.0.0"

# Import main functions for easy access
from .img_slices import create_pdf_entry_point
from .html_report import create_html_entry_point

__all__ = [
    'create_pdf_entry_point',
    'create_html_entry_point',
]
