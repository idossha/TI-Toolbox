"""
Specialized reportlets for TI-Toolbox reports.

This module provides domain-specific reportlets for brain imaging,
simulation parameters, and analysis results.
"""

from .images import (
    SliceSeriesReportlet,
    MontageImageReportlet,
    MultiViewBrainReportlet,
)

from .metadata import (
    ConductivityTableReportlet,
    ProcessingStepReportlet,
    SummaryCardsReportlet,
    ParameterListReportlet,
    DEFAULT_CONDUCTIVITIES,
)

from .text import (
    MethodsBoilerplateReportlet,
    DescriptionReportlet,
    CommandLogReportlet,
)

from .references import (
    TIToolboxReferencesReportlet,
    DEFAULT_REFERENCES,
    get_default_references,
    get_reference_by_key,
)

__all__ = [
    # Image reportlets
    "SliceSeriesReportlet",
    "MontageImageReportlet",
    "MultiViewBrainReportlet",
    # Metadata reportlets
    "ConductivityTableReportlet",
    "ProcessingStepReportlet",
    "SummaryCardsReportlet",
    "ParameterListReportlet",
    "DEFAULT_CONDUCTIVITIES",
    # Text reportlets
    "MethodsBoilerplateReportlet",
    "DescriptionReportlet",
    "CommandLogReportlet",
    # References
    "TIToolboxReferencesReportlet",
    "DEFAULT_REFERENCES",
    "get_default_references",
    "get_reference_by_key",
]
