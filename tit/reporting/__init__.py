"""
TI-Toolbox Reportlet-Based Reporting System.

A modular, NiPreps-inspired reporting system for TI-Toolbox that generates
self-contained HTML reports across preprocessing, simulation, and flex-search modules.
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
    MultiViewBrainReportlet,
    # Metadata reportlets
    ConductivityTableReportlet,
    ProcessingStepReportlet,
    SummaryCardsReportlet,
    ParameterListReportlet,
    DEFAULT_CONDUCTIVITIES,
    # Text reportlets
    MethodsBoilerplateReportlet,
    DescriptionReportlet,
    CommandLogReportlet,
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
    # Preprocessing
    PreprocessingReportGenerator,
    create_preprocessing_report,
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
    "MultiViewBrainReportlet",
    "ConductivityTableReportlet",
    "ProcessingStepReportlet",
    "SummaryCardsReportlet",
    "ParameterListReportlet",
    "DEFAULT_CONDUCTIVITIES",
    "MethodsBoilerplateReportlet",
    "DescriptionReportlet",
    "CommandLogReportlet",
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
    "PreprocessingReportGenerator",
    "create_preprocessing_report",
]
