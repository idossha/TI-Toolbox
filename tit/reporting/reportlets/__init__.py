"""
Specialized reportlets for TI-Toolbox reports.

This module provides domain-specific reportlets for brain imaging,
simulation parameters, and analysis results.
"""

from .images import (
    SliceSeriesReportlet,
    MontageImageReportlet,
)

from .metadata import (
    ConductivityTableReportlet,
    SummaryCardsReportlet,
    ParameterListReportlet,
    DEFAULT_CONDUCTIVITIES,
)

from .text import (
    SimulationMethodsBuilder,
    MethodsBoilerplateReportlet,
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
    # Metadata reportlets
    "ConductivityTableReportlet",
    "SummaryCardsReportlet",
    "ParameterListReportlet",
    "DEFAULT_CONDUCTIVITIES",
    # Text reportlets
    "SimulationMethodsBuilder",
    "MethodsBoilerplateReportlet",
    # References
    "TIToolboxReferencesReportlet",
    "DEFAULT_REFERENCES",
    "get_default_references",
    "get_reference_by_key",
]
