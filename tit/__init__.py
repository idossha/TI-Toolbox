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

# Auto-initialize logging with terminal output on import.
# Scripts need no explicit setup — just ``from tit.sim import ...`` and go.
setup_logging("INFO")
add_stream_handler("tit", "INFO")

__all__ = [
    "setup_logging",
    "add_file_handler",
    "add_stream_handler",
    "get_path_manager",
    "paths",
    "constants",
]
