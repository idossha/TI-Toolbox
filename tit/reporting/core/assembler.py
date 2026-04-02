"""Report assembler for combining reportlets into complete HTML reports.

The ``ReportAssembler`` class provides a high-level interface for building
reports from individual reportlets organized into sections.

Public API
----------
ReportAssembler
    Main assembler class that manages sections, renders the table of
    contents, and produces the final HTML document.

See Also
--------
tit.reporting.core.base : Base reportlet classes added to sections.
tit.reporting.core.templates : HTML/CSS/JS templates used during rendering.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Self

from .protocols import ReportMetadata, ReportSection
from .templates import get_html_template


class ReportAssembler:
    """Assemble reportlets into a complete HTML report.

    Manages sections, handles ordering, generates the table of contents,
    and renders the final HTML document.

    Parameters
    ----------
    metadata : ReportMetadata or None, optional
        Report metadata (title, subject, etc.).  A default is created
        when *None*.
    title : str or None, optional
        Report title.  Overrides ``metadata.title`` when provided.

    See Also
    --------
    ReportMetadata : Dataclass holding report-level metadata.
    ReportSection : Container for reportlets within a section.
    BaseReportGenerator : Abstract generator that wraps ``ReportAssembler``.
    """

    def __init__(
        self,
        metadata: ReportMetadata | None = None,
        title: str | None = None,
    ):
        self.metadata = metadata or ReportMetadata(title=title or "Report")
        if title:
            self.metadata.title = title

        self.sections: list[ReportSection] = []
        self._custom_css: str = ""
        self._custom_js: str = ""

    def add_section(
        self,
        section_id: str,
        title: str,
        description: str | None = None,
        collapsed: bool = False,
        order: int | None = None,
    ) -> ReportSection:
        """Add a new section to the report.

        Parameters
        ----------
        section_id : str
            Unique identifier for the section.
        title : str
            Section title displayed in the report.
        description : str or None, optional
            Optional section description shown below the title.
        collapsed : bool, optional
            Whether the section starts collapsed (default *False*).
        order : int or None, optional
            Sort order (lower = earlier in report).  Defaults to the
            current number of sections.

        Returns
        -------
        ReportSection
            The newly created section object.
        """
        if order is None:
            order = len(self.sections)

        section = ReportSection(
            section_id=section_id,
            title=title,
            description=description,
            collapsed=collapsed,
            order=order,
        )
        self.sections.append(section)
        return section

    def get_section(self, section_id: str) -> ReportSection | None:
        """Get a section by its ID.

        Parameters
        ----------
        section_id : str
            The section identifier.

        Returns
        -------
        ReportSection or None
            The matching section, or *None* if not found.
        """
        for section in self.sections:
            if section.section_id == section_id:
                return section
        return None

    def add_reportlet_to_section(
        self,
        section_id: str,
        reportlet: Any,
        create_if_missing: bool = True,
        section_title: str | None = None,
    ) -> None:
        """Add a reportlet to a specific section.

        Parameters
        ----------
        section_id : str
            The section identifier.
        reportlet : Reportlet
            The reportlet instance to add.
        create_if_missing : bool, optional
            Create the section if it does not exist (default *True*).
        section_title : str or None, optional
            Title for the new section when it is auto-created.

        Raises
        ------
        ValueError
            If the section is not found and *create_if_missing* is *False*.
        """
        section = self.get_section(section_id)

        if section is None:
            if create_if_missing:
                title = section_title or section_id.replace("_", " ").title()
                section = self.add_section(section_id, title)
            else:
                raise ValueError(f"Section '{section_id}' not found")

        section.add_reportlet(reportlet)

    def set_custom_css(self, css: str) -> None:
        """Add custom CSS styles to the report."""
        self._custom_css = css

    def set_custom_js(self, js: str) -> None:
        """Add custom JavaScript to the report."""
        self._custom_js = js

    def render_toc(self) -> str:
        """Render the table of contents as HTML.

        Returns
        -------
        str
            HTML string for the table of contents.
        """
        sorted_sections = sorted(self.sections, key=lambda s: s.order)

        links = []
        for section in sorted_sections:
            links.append(
                f'<li><a href="#{section.section_id}">{section.title}</a></li>'
            )

        return f'<ul class="toc-list">{"".join(links)}</ul>'

    def render_metadata(self) -> str:
        """Render the header metadata as HTML.

        Returns
        -------
        str
            HTML string for the header metadata.
        """
        parts = []

        if self.metadata.subject_id:
            parts.append(
                f"<span>Subject: <strong>{self.metadata.subject_id}</strong></span>"
            )

        if self.metadata.session_id:
            parts.append(
                f"<span>Session: <strong>{self.metadata.session_id}</strong></span>"
            )

        parts.append(
            f'<span>Generated: <strong>{self.metadata.generation_time.strftime("%Y-%m-%d %H:%M:%S")}</strong></span>'
        )

        return f'<div class="header-meta">{"".join(parts)}</div>'

    def render_sections(self) -> str:
        """Render all sections as HTML.

        Returns
        -------
        str
            HTML string for all sections.
        """
        sorted_sections = sorted(self.sections, key=lambda s: s.order)
        return "\n".join(section.render_html() for section in sorted_sections)

    def render_html(self) -> str:
        """Render the complete report as HTML.

        Returns
        -------
        str
            Complete HTML document as a string.
        """
        content = self.render_sections()
        toc_html = self.render_toc()
        metadata_html = self.render_metadata()

        return get_html_template(
            title=self.metadata.title,
            content=content,
            toc_html=toc_html,
            metadata_html=metadata_html,
            custom_css=self._custom_css,
            custom_js=self._custom_js,
        )

    def save(
        self,
        output_path: str | Path,
        create_dirs: bool = True,
    ) -> Path:
        """Save the report to a file.

        Parameters
        ----------
        output_path : str or pathlib.Path
            Path to save the HTML file.
        create_dirs : bool, optional
            Create parent directories if needed (default *True*).

        Returns
        -------
        pathlib.Path
            Path to the saved file.
        """
        output_path = Path(output_path)

        if create_dirs:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        html_content = self.render_html()
        output_path.write_text(html_content, encoding="utf-8")

        return output_path

    def to_dict(self) -> dict[str, Any]:
        """Convert the report to a dictionary representation.

        Returns
        -------
        dict
            Dictionary containing all report data.
        """
        return {
            "metadata": self.metadata.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a ReportAssembler from a dictionary.

        Reconstructs the structure but **not** the reportlet instances.
        Use this for loading report metadata, not for full reconstruction.

        Parameters
        ----------
        data : dict
            Dictionary containing report data (as produced by ``to_dict``).

        Returns
        -------
        ReportAssembler
            Reconstructed instance.
        """
        metadata_dict = data.get("metadata", {})
        metadata = ReportMetadata(
            title=metadata_dict.get("title", "Report"),
            subject_id=metadata_dict.get("subject_id"),
            session_id=metadata_dict.get("session_id"),
            report_type=metadata_dict.get("report_type", "general"),
            project_dir=metadata_dict.get("project_dir"),
        )

        assembler = cls(metadata=metadata)

        for section_data in data.get("sections", []):
            assembler.add_section(
                section_id=section_data["section_id"],
                title=section_data["title"],
                description=section_data.get("description"),
                collapsed=section_data.get("collapsed", False),
                order=section_data.get("order", 0),
            )

        return assembler
