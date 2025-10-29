#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-Toolbox Core Module
Centralized constants and path management for the entire TI-Toolbox codebase.

This module provides:
- Constants: All hardcoded values, magic numbers, and configuration constants
- Paths: Professional path management system for BIDS-compliant directory structures

Usage:
    # Import constants
    from ti_toolbox.core import constants as const
    
    # Use constants
    simnibs_dir = os.path.join(derivatives_dir, const.DIR_SIMNIBS)
    subject_dir = os.path.join(simnibs_dir, f"{const.PREFIX_SUBJECT}{subject_id}")
    
    # Import path manager
    from ti_toolbox.core.paths import get_path_manager
    
    # Use path manager
    pm = get_path_manager()
    subjects = pm.list_subjects()
    m2m_dir = pm.get_m2m_dir("001")
    
    # Or use convenience functions
    from ti_toolbox.core.paths import get_project_dir, list_subjects
    
    project_dir = get_project_dir()
    subjects = list_subjects()
"""

# Import main components for easy access
from . import constants
from .paths import (
    PathManager,
    get_path_manager,
    reset_path_manager,
    get_project_dir,
    get_subject_dir,
    get_m2m_dir,
    list_subjects,
    validate_subject
)

# Version information
__version__ = "2.1.3"
__author__ = "TI-Toolbox Development Team"

# Define public API
__all__ = [
    # Constants module
    'constants',
    
    # Path management classes
    'PathManager',
    
    # Path management functions
    'get_path_manager',
    'reset_path_manager',
    
    # Convenience functions
    'get_project_dir',
    'get_subject_dir',
    'get_m2m_dir',
    'list_subjects',
    'validate_subject',
    
    # Version info
    '__version__',
    '__author__',
]

