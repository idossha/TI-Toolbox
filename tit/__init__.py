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


def init(level: str = "INFO") -> None:
    """One-call setup for scripts: configure logging and enable terminal output.

    Equivalent to::

        setup_logging(level)
        add_stream_handler("tit", level)

    Call this at the top of any script that uses the ``tit`` package
    to get sensible defaults with no extra boilerplate.
    """
    setup_logging(level)
    add_stream_handler("tit", level)


__all__ = [
    "init",
    "setup_logging",
    "add_file_handler",
    "add_stream_handler",
    "get_path_manager",
    "paths",
    "constants",
]
