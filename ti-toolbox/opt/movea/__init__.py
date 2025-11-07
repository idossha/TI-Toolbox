"""
MOVEA: Multi-Objective Optimization via Evolutionary Algorithm
Integrated into TI-Toolbox for TI electrode optimization
"""

from .montage_formatter import MontageFormatter
from .optimizer import TIOptimizer
from .visualizer import MOVEAVisualizer, visualize_complete_results

__all__ = [
    'TIOptimizer',  # Scipy-based optimizer with Pareto front support
    'MontageFormatter',
    'MOVEAVisualizer',
    'visualize_complete_results',
]

