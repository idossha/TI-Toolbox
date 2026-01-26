"""
Report generators for TI-Toolbox modules.

This module provides specialized report generators for different
TI-Toolbox pipelines.
"""

from .base_generator import BaseReportGenerator, REPORTS_BASE_DIR, BIDS_VERSION

from .simulation import SimulationReportGenerator

from .flex_search import FlexSearchReportGenerator, create_flex_search_report

from .preprocessing import PreprocessingReportGenerator, create_preprocessing_report

__all__ = [
    # Base
    "BaseReportGenerator",
    "REPORTS_BASE_DIR",
    "BIDS_VERSION",
    # Simulation
    "SimulationReportGenerator",
    # Flex-search
    "FlexSearchReportGenerator",
    "create_flex_search_report",
    # Preprocessing
    "PreprocessingReportGenerator",
    "create_preprocessing_report",
]
