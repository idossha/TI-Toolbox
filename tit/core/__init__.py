#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

# Import main components for easy access
from . import constants
from . import utils
from .paths import (
    PathManager,
    get_path_manager,
    reset_path_manager,
)

# Define public API
__all__ = [
    # Constants module
    'constants',

    # Utils module
    'utils',
    
    # Path management classes
    'PathManager',
    
    # Path management functions
    'get_path_manager',
    'reset_path_manager',
]

