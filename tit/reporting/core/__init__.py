"""
Core infrastructure for TI-Toolbox reporting system.

This module provides the foundational components for building
modular, self-contained HTML reports.
"""

from .protocols import (
    ReportletType,
    ReportMetadata,
    ReportSection,
    Reportlet,
    SeverityLevel,
    StatusType,
)

from .base import (
    BaseReportlet,
    MetadataReportlet,
    ImageReportlet,
    TableReportlet,
    TextReportlet,
    ErrorReportlet,
    ReferencesReportlet,
)

from .assembler import ReportAssembler

from .templates import (
    DEFAULT_CSS_STYLES,
    DEFAULT_JS_SCRIPTS,
    get_html_template,
)

__all__ = [
    # Protocols and types
    "ReportletType",
    "ReportMetadata",
    "ReportSection",
    "Reportlet",
    "SeverityLevel",
    "StatusType",
    # Base reportlets
    "BaseReportlet",
    "MetadataReportlet",
    "ImageReportlet",
    "TableReportlet",
    "TextReportlet",
    "ErrorReportlet",
    "ReferencesReportlet",
    # Assembler
    "ReportAssembler",
    # Templates
    "DEFAULT_CSS_STYLES",
    "DEFAULT_JS_SCRIPTS",
    "get_html_template",
]
