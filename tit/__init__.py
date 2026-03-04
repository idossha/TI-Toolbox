#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox
"""

__version__ = "2.2.4"
__author__ = "TI-Toolbox Team"

# Logging utilities
from . import logger as log
from . import paths, constants


from .logger import setup_logging, add_file_handler

__all__ = [
    "log",
    "setup_logging",
    "add_file_handler",
    "paths",
    "constants",
]
