#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox
"""

__version__ = "2.2.3"
__author__ = "TI-Toolbox Team"

# Logging utilities
from . import logger as log

# For backward compatibility, also expose individual functions
from .logger import (
    CallbackHandler,
    FlushingFileHandler,
    FlushingStreamHandler,
    HostTimestampFormatter,
    add_callback_handler,
    configure_external_loggers,
    get_file_only_logger,
    get_logger,
    suppress_console_output,
)

__all__ = [
    "log",
    "CallbackHandler",
    "FlushingFileHandler",
    "FlushingStreamHandler",
    "HostTimestampFormatter",
    "add_callback_handler",
    "configure_external_loggers",
    "get_file_only_logger",
    "get_logger",
    "suppress_console_output",
]
