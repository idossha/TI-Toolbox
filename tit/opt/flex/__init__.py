"""Flex-search optimization package for TI stimulation.

This package provides flexible optimization for temporal interference (TI)
stimulation with support for different ROI definitions and optimization goals.

Modules:
    flex_config: Configuration and optimization setup
    flex_log: Logging utilities and progress tracking
    multi_start: Multi-start optimization logic and result management
    flex: Main optimization orchestration script
    pareto_sweep: Pareto threshold-grid sweep for focality optimization

Note:
    roi module is now located at core.roi (shared across optimization approaches)
"""

try:
    from . import flex_config
    from . import flex_log
    from . import multi_start
except ImportError:
    # SimNIBS not available (e.g. during testing outside the container).
    pass

from .pareto_sweep import (
    ParetoSweepConfig,
    ParetoSweepResult,
    SweepPoint,
    build_focality_cmd,
    compute_sweep_grid,
    generate_summary_text,
    parse_sweep_line,
    save_results,
    validate_grid,
)

__all__ = [
    "flex_config",
    "flex_log",
    "multi_start",
    "ParetoSweepConfig",
    "ParetoSweepResult",
    "SweepPoint",
    "build_focality_cmd",
    "compute_sweep_grid",
    "generate_summary_text",
    "parse_sweep_line",
    "save_results",
    "validate_grid",
]
