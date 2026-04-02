"""Protocols and type definitions for the TI-Toolbox reporting system.

Defines the core interfaces and enums used by reportlets and report
generators.

Public API
----------
ReportletType
    Enumeration of reportlet types (METADATA, IMAGE, TABLE, ...).
SeverityLevel
    Severity levels for errors and warnings.
StatusType
    Status types for processing steps.
Reportlet
    Runtime-checkable protocol every reportlet must satisfy.
ReportMetadata
    Dataclass holding report-level metadata (title, subject, etc.).
ReportSection
    Dataclass representing a section that holds multiple reportlets.

See Also
--------
tit.reporting.core.base : Concrete base reportlet implementations.
tit.reporting.core.assembler : Assembler that organizes sections into a report.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Protocol, runtime_checkable


class ReportletType(Enum):
    """Enumeration of reportlet types.

    Each member corresponds to a rendering strategy in the base reportlet
    classes.
    """

    METADATA = auto()
    IMAGE = auto()
    TABLE = auto()
    TEXT = auto()
    ERROR = auto()
    REFERENCES = auto()


class SeverityLevel(Enum):
    """Severity levels for errors and warnings.

    Used by ``ErrorReportlet`` to control icon and colour styling.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StatusType(Enum):
    """Status types for processing steps.

    Used by ``ProcessingStepReportlet`` to display step progress.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@runtime_checkable
class Reportlet(Protocol):
    """Protocol defining the interface for all reportlets.

    Any object satisfying this protocol can be added to a
    ``ReportSection``.
    """

    @property
    def reportlet_type(self) -> ReportletType:
        """Return the type of this reportlet."""
        ...

    @property
    def reportlet_id(self) -> str:
        """Return a unique identifier for this reportlet."""
        ...

    def render_html(self) -> str:
        """Render the reportlet as an HTML fragment."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert the reportlet to a dictionary representation."""
        ...


@dataclass
class ReportMetadata:
    """Metadata for a generated report.

    Attributes
    ----------
    title : str
        Report title shown in the header.
    subject_id : str or None
        BIDS subject identifier (without ``sub-`` prefix).
    session_id : str or None
        Session or run identifier.
    report_type : str
        Type tag (e.g. ``"simulation"``, ``"preprocessing"``).
    generation_time : datetime.datetime
        Timestamp when the report was generated.
    software_versions : dict[str, str]
        Mapping of tool name to version string.
    project_dir : str or None
        BIDS project root directory.
    bids_version : str
        BIDS specification version.
    dataset_type : str
        BIDS dataset type (always ``"derivative"``).
    """

    title: str
    subject_id: str | None = None
    session_id: str | None = None
    report_type: str = "general"
    generation_time: datetime = field(default_factory=datetime.now)
    software_versions: dict[str, str] = field(default_factory=dict)
    project_dir: str | None = None

    # BIDS-related fields
    bids_version: str = "1.8.0"
    dataset_type: str = "derivative"

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to a JSON-serialisable dictionary.

        Returns
        -------
        dict
            All metadata fields with ``generation_time`` as ISO-8601 string.
        """
        return {
            "title": self.title,
            "subject_id": self.subject_id,
            "session_id": self.session_id,
            "report_type": self.report_type,
            "generation_time": self.generation_time.isoformat(),
            "software_versions": self.software_versions,
            "project_dir": self.project_dir,
            "bids_version": self.bids_version,
            "dataset_type": self.dataset_type,
        }


@dataclass
class ReportSection:
    """A section within a report containing multiple reportlets.

    Attributes
    ----------
    section_id : str
        Unique identifier used as the HTML ``id`` attribute.
    title : str
        Human-readable section title.
    reportlets : list
        Ordered list of reportlet instances.
    description : str or None
        Optional description displayed below the title.
    collapsed : bool
        Whether the section is initially collapsed.
    order : int
        Sort order (lower values appear first).
    """

    section_id: str
    title: str
    reportlets: list[Any] = field(default_factory=list)
    description: str | None = None
    collapsed: bool = False
    order: int = 0

    def add_reportlet(self, reportlet: Any) -> None:
        """Add a reportlet to this section."""
        self.reportlets.append(reportlet)

    def render_html(self) -> str:
        """Render the section and all its reportlets as HTML.

        Returns
        -------
        str
            HTML fragment for the complete section.
        """
        collapse_class = "collapsible" if self.collapsed else ""
        content_parts = []

        for reportlet in self.reportlets:
            content_parts.append(reportlet.render_html())

        content = "\n".join(content_parts)

        description_html = ""
        if self.description:
            description_html = f'<p class="section-description">{self.description}</p>'

        return f"""
        <section id="{self.section_id}" class="report-section {collapse_class}">
            <h2 class="section-title">{self.title}</h2>
            {description_html}
            <div class="section-content">
                {content}
            </div>
        </section>
        """

    def to_dict(self) -> dict[str, Any]:
        """Convert section to a JSON-serialisable dictionary.

        Returns
        -------
        dict
            Section metadata plus serialised reportlets.
        """
        return {
            "section_id": self.section_id,
            "title": self.title,
            "description": self.description,
            "collapsed": self.collapsed,
            "order": self.order,
            "reportlets": [r.to_dict() for r in self.reportlets],
        }
