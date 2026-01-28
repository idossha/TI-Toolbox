"""
Protocols and type definitions for the TI-Toolbox reporting system.

This module defines the core interfaces and enums used by reportlets
and report generators.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class ReportletType(Enum):
    """Enumeration of reportlet types."""

    METADATA = auto()
    IMAGE = auto()
    TABLE = auto()
    TEXT = auto()
    ERROR = auto()
    REFERENCES = auto()


class SeverityLevel(Enum):
    """Severity levels for errors and warnings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StatusType(Enum):
    """Status types for processing steps."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@runtime_checkable
class Reportlet(Protocol):
    """Protocol defining the interface for all reportlets."""

    @property
    def reportlet_type(self) -> ReportletType:
        """Return the type of this reportlet."""
        ...

    @property
    def reportlet_id(self) -> str:
        """Return a unique identifier for this reportlet."""
        ...

    def render_html(self) -> str:
        """Render the reportlet as HTML."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Convert the reportlet to a dictionary representation."""
        ...


@dataclass
class ReportMetadata:
    """Metadata for a generated report."""

    title: str
    subject_id: Optional[str] = None
    session_id: Optional[str] = None
    report_type: str = "general"
    generation_time: datetime = field(default_factory=datetime.now)
    software_versions: Dict[str, str] = field(default_factory=dict)
    project_dir: Optional[str] = None

    # BIDS-related fields
    bids_version: str = "1.8.0"
    dataset_type: str = "derivative"

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
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
    """A section within a report containing multiple reportlets."""

    section_id: str
    title: str
    reportlets: List[Any] = field(default_factory=list)
    description: Optional[str] = None
    collapsed: bool = False
    order: int = 0

    def add_reportlet(self, reportlet: Any) -> None:
        """Add a reportlet to this section."""
        self.reportlets.append(reportlet)

    def render_html(self) -> str:
        """Render the section and all its reportlets as HTML."""
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert section to dictionary."""
        return {
            "section_id": self.section_id,
            "title": self.title,
            "description": self.description,
            "collapsed": self.collapsed,
            "order": self.order,
            "reportlets": [r.to_dict() for r in self.reportlets],
        }
