"""Reportlet-based reporting system for TI-Toolbox.

A modular, NiPreps-inspired reporting system that generates self-contained
HTML reports for simulation and flex-search.
Reports follow a section/reportlet architecture: each ``ReportSection``
contains one or more ``BaseReportlet`` subclasses, and the
``ReportAssembler`` renders them into a single HTML document.

Public API
----------
Core types
    ReportletType, ReportMetadata, ReportSection, SeverityLevel, StatusType
Base reportlets
    BaseReportlet, MetadataReportlet, ImageReportlet, TableReportlet,
    TextReportlet, ErrorReportlet, ReferencesReportlet
Assembler
    ReportAssembler
Specialized reportlets
    SliceSeriesReportlet, MontageImageReportlet,
    ConductivityTableReportlet,
    SummaryCardsReportlet, ParameterListReportlet,
    MethodsBoilerplateReportlet,
    TIToolboxReferencesReportlet
Generators
    BaseReportGenerator, SimulationReportGenerator,
    FlexSearchReportGenerator
Convenience functions
    create_flex_search_report,
    get_default_references, get_reference_by_key

See Also
--------
tit.plotting : Visualization utilities used by report generators.
tit.analyzer : Field analysis whose results feed into reports.
"""

# Core infrastructure
from .core import (
    # Protocols and types
    ReportletType,
    ReportMetadata,
    ReportSection,
    SeverityLevel,
    StatusType,
    # Base reportlets
    BaseReportlet,
    MetadataReportlet,
    ImageReportlet,
    TableReportlet,
    TextReportlet,
    ErrorReportlet,
    ReferencesReportlet,
    # Assembler
    ReportAssembler,
)

# Specialized reportlets
from .reportlets import (
    # Image reportlets
    SliceSeriesReportlet,
    MontageImageReportlet,
    # Metadata reportlets
    ConductivityTableReportlet,
    SummaryCardsReportlet,
    ParameterListReportlet,
    DEFAULT_CONDUCTIVITIES,
    # Text reportlets
    SimulationMethodsBuilder,
    MethodsBoilerplateReportlet,
    # References
    TIToolboxReferencesReportlet,
    DEFAULT_REFERENCES,
    get_default_references,
    get_reference_by_key,
)

# Report generators
from .generators import (
    # Base
    BaseReportGenerator,
    BIDS_VERSION,
    REPORTS_BASE_DIR,
    # Simulation
    SimulationReportGenerator,
    # Flex-search
    FlexSearchReportGenerator,
    create_flex_search_report,
)

__all__ = [
    # Core types
    "ReportletType",
    "ReportMetadata",
    "ReportSection",
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
    # Specialized reportlets
    "SliceSeriesReportlet",
    "MontageImageReportlet",
    "ConductivityTableReportlet",
    "SummaryCardsReportlet",
    "ParameterListReportlet",
    "DEFAULT_CONDUCTIVITIES",
    "SimulationMethodsBuilder",
    "MethodsBoilerplateReportlet",
    "TIToolboxReferencesReportlet",
    "DEFAULT_REFERENCES",
    "get_default_references",
    "get_reference_by_key",
    # Generators
    "BaseReportGenerator",
    "BIDS_VERSION",
    "REPORTS_BASE_DIR",
    "SimulationReportGenerator",
    "FlexSearchReportGenerator",
    "create_flex_search_report",
]
