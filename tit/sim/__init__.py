#!/usr/bin/env simnibs_python
"""
Temporal Interference (TI) Simulation Module

This module provides a unified interface for running TI and mTI simulations.
It automatically detects the simulation type based on montage configuration.
"""

from .simulator import (
    run_simulation,
    setup_montage_directories,
    run_montage_visualization,
)
from .config import (
    SimulationConfig,
    ElectrodeConfig,
    IntensityConfig,
    MontageConfig,
    SimulationMode,
    ConductivityType,
    ParallelConfig,
)
from .montage_loader import load_montages
from .post_processor import PostProcessor
from .session_builder import SessionBuilder

__all__ = [
    # Main entry point
    "run_simulation",
    "setup_montage_directories",
    "run_montage_visualization",
    # Configuration classes
    "SimulationConfig",
    "ElectrodeConfig",
    "IntensityConfig",
    "MontageConfig",
    "SimulationMode",
    "ConductivityType",
    "ParallelConfig",
    # Utilities
    "load_montages",
    "PostProcessor",
    "SessionBuilder",
]
