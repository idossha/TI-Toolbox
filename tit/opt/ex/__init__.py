"""
TI Exhaustive Search Module

A streamlined implementation for TI exhaustive search simulations.
"""

import os

from .config import get_full_config
from .logic import generate_current_ratios, calculate_total_combinations, generate_montage_combinations
from .runner import LeadfieldProcessor, CurrentRatioGenerator, MontageGenerator, SimulationRunner
from .results import ResultsProcessor, ResultsVisualizer, ResultsManager
from .main import main

__version__ = "5.0.0"
__all__ = [
    # Configuration
    'get_full_config',

    # Algorithms
    'generate_current_ratios',
    'calculate_total_combinations',
    'generate_montage_combinations',

    # Processing
    'LeadfieldProcessor',
    'CurrentRatioGenerator',
    'MontageGenerator',
    'SimulationRunner',

    # Results
    'ResultsProcessor',
    'ResultsVisualizer',
    'ResultsManager',

    # Main entry point
    'main'
]
