"""
MOVEA: Multi-Objective Optimization via Evolutionary Algorithm
Integrated into TI-Toolbox for TI electrode optimization
"""

from .main import run_optimization
from .montage_formatter import MontageFormatter, quick_save
from .optimizer import TIOptimizer
from .visualizer import MOVEAVisualizer, visualize_complete_results

__all__ = [
    'run_optimization',  # Main MOVEA optimization workflow
    'TIOptimizer',  # Scipy-based optimizer with Pareto front support
    'MontageFormatter',
    'quick_save',
    'MOVEAVisualizer',
    'visualize_complete_results',
]

