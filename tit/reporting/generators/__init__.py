"""Report generators for TI-Toolbox modules.

Each generator inherits from :class:`BaseReportGenerator` and produces
an HTML report using reportlets from ``tit.reporting.reportlets``.

Public API
----------
BaseReportGenerator
    Abstract base class defining the generator interface.
REPORTS_BASE_DIR
    Default BIDS-relative directory for reports.
BIDS_VERSION
    BIDS version string used in dataset descriptions.
SimulationReportGenerator
    Report for TI / mTI simulation runs.
FlexSearchReportGenerator / create_flex_search_report
    Report (and convenience function) for flex-search optimization.
PreprocessingReportGenerator / create_preprocessing_report
    Report (and convenience function) for preprocessing pipelines.
DTIQCReportGenerator / create_dti_qc_report
    QC report (and convenience function) for DTI tensor extraction.

See Also
--------
tit.reporting.reportlets : Reusable HTML fragments consumed by generators.
tit.reporting.assembler : :class:`ReportAssembler` that stitches reportlets
    into a final HTML document.
"""

from .base_generator import BaseReportGenerator, REPORTS_BASE_DIR, BIDS_VERSION

from .simulation import SimulationReportGenerator

from .flex_search import FlexSearchReportGenerator, create_flex_search_report

from .preprocessing import PreprocessingReportGenerator, create_preprocessing_report

from .dti_qc import DTIQCReportGenerator, create_dti_qc_report

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
    # DTI QC
    "DTIQCReportGenerator",
    "create_dti_qc_report",
]
