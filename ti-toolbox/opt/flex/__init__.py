"""Flex-search optimization package for TI stimulation.

This package provides flexible optimization for temporal interference (TI)
stimulation with support for different ROI definitions and optimization goals.

Modules:
    flex_config: Configuration and optimization setup
    flex_log: Logging utilities and progress tracking
    multi_start: Multi-start optimization logic and result management
    flex: Main optimization orchestration script

Note:
    roi module is now located at core.roi (shared across optimization approaches)
"""

from . import flex_config
from . import flex_log
from . import multi_start

__all__ = ['flex_config', 'flex_log', 'multi_start']
