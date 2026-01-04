"""
Reporting utilities for TI-Toolbox (HTML report generation, report helpers).
"""

from .report_util import (
    REPORTS_BASE_DIR,
    PREPROCESSING_REPORT_PREFIX,
    SIMULATION_REPORT_PREFIX,
    create_preprocessing_report,
    create_simulation_report,
    get_preprocessing_report_generator,
    get_simulation_report_generator,
    get_latest_report,
    list_reports,
)

__all__ = [
    "REPORTS_BASE_DIR",
    "PREPROCESSING_REPORT_PREFIX",
    "SIMULATION_REPORT_PREFIX",
    "create_preprocessing_report",
    "create_simulation_report",
    "get_preprocessing_report_generator",
    "get_simulation_report_generator",
    "get_latest_report",
    "list_reports",
]




