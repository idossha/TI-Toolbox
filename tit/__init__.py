#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox
"""

__version__ = "2.3.0"
__author__ = "TI-Toolbox Team"

from . import paths, constants

from .logger import setup_logging, add_file_handler, add_stream_handler
from .paths import get_path_manager

__all__ = [
    "setup_logging",
    "add_file_handler",
    "add_stream_handler",
    "get_path_manager",
    "paths",
    "constants",
]
