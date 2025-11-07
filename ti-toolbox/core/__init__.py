#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

# Import main components for easy access
from . import constants
from .paths import (
    PathManager,
    get_path_manager,
    reset_path_manager,
    get_project_dir,
    get_subject_dir,
    get_m2m_dir,
    get_simnibs_dir,
    get_simulation_dir,
    get_freesurfer_subject_dir,
    get_freesurfer_mri_dir,
    list_subjects,
    list_simulations,
    validate_subject
)

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
    'get_simnibs_dir',
    'get_simulation_dir',
    'get_freesurfer_subject_dir',
    'get_freesurfer_mri_dir',
    'list_subjects',
    'list_simulations',
    'validate_subject',
]

