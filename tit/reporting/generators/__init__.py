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

The DTI QC, simulator and flex-search reports (``dti_qc``, ``simulation``, ``flex_search``) are built on ``tit.reporting.html``
and not imported here, so ``python -m tit.reporting.generators.<name>`` runs without a runpy warning.

See Also
--------
tit.reporting.reportlets : Reusable HTML fragments consumed by generators.
tit.reporting.assembler : :class:`ReportAssembler` that stitches reportlets
    into a final HTML document.
"""

from .base_generator import BaseReportGenerator, REPORTS_BASE_DIR, BIDS_VERSION

__all__ = [
    # Base
    "BaseReportGenerator",
    "REPORTS_BASE_DIR",
    "BIDS_VERSION",
]
