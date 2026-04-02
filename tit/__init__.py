#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""TI-Toolbox: Temporal Interference Brain Stimulation Platform.

A neuroscience research platform for simulating, optimizing, and analyzing
temporal interference (TI) stimulation of the brain. Built on top of
SimNIBS for finite-element modeling and FreeSurfer for cortical reconstruction.

Modules
-------
sim
    TI/mTI simulation engine (electrode montages, field computation).
opt
    Optimization of electrode placements (flex-search, exhaustive).
analyzer
    Field analysis, ROI statistics, and visualization.
stats
    Permutation testing and group-level comparisons.
pre
    Preprocessing pipelines (DICOM conversion, FreeSurfer, CHARM).
gui
    PyQt5 desktop interface (runs inside Docker with X11).
cli
    Command-line tools built on a shared ``BaseCLI`` base class.
reporting
    HTML report generation with composable reportlets.

Public API
----------
get_path_manager
    Return the global :class:`~tit.paths.PathManager` singleton.
setup_logging
    Configure the package-wide logging level.
add_file_handler
    Attach a file handler to a named logger.
add_stream_handler
    Attach a console handler to a named logger.
paths
    BIDS-compliant path resolution module.
constants
    Project-wide constants and configuration values.

Examples
--------
>>> from tit import get_path_manager
>>> pm = get_path_manager("/data/project")
>>> from tit.sim import SimulationConfig, run_simulation

Notes
-----
Importing this package auto-initializes logging (with stream output at
INFO level) and exposes ``get_path_manager`` for BIDS path resolution.
No additional setup is required for typical usage.
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
