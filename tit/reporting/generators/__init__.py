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
FlexSearchReportGenerator / create_flex_search_report
    Report (and convenience function) for flex-search optimization.

The DTI QC and simulator reports (``dti_qc``, ``simulation``) are built on ``tit.reporting.html``
and not imported here, so ``python -m tit.reporting.generators.<name>`` runs without a runpy warning.

See Also
--------
tit.reporting.reportlets : Reusable HTML fragments consumed by generators.
tit.reporting.assembler : :class:`ReportAssembler` that stitches reportlets
    into a final HTML document.
"""

from .base_generator import BaseReportGenerator, REPORTS_BASE_DIR, BIDS_VERSION

from .flex_search import FlexSearchReportGenerator, create_flex_search_report

__all__ = [
    # Base
    "BaseReportGenerator",
    "REPORTS_BASE_DIR",
    "BIDS_VERSION",
    # Flex-search
    "FlexSearchReportGenerator",
    "create_flex_search_report",
]
