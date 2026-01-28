"""
Report assembler for combining reportlets into complete HTML reports.

The ReportAssembler class provides a high-level interface for building
reports from individual reportlets organized into sections.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .protocols import ReportMetadata, ReportSection
from .templates import get_html_template


class ReportAssembler:
    """
    Assembles reportlets into a complete HTML report.

    The assembler manages sections, handles ordering, generates
    the table of contents, and renders the final HTML document.
    """

    def __init__(
        self,
        metadata: Optional[ReportMetadata] = None,
        title: Optional[str] = None,
    ):
        """
        Initialize the report assembler.

        Args:
            metadata: Report metadata (title, subject, etc.)
            title: Report title (overrides metadata.title if provided)
        """
        self.metadata = metadata or ReportMetadata(title=title or "Report")
        if title:
            self.metadata.title = title

        self.sections: List[ReportSection] = []
        self._custom_css: str = ""
        self._custom_js: str = ""

    def add_section(
        self,
        section_id: str,
        title: str,
        description: Optional[str] = None,
        collapsed: bool = False,
        order: Optional[int] = None,
    ) -> ReportSection:
        """
        Add a new section to the report.

        Args:
            section_id: Unique identifier for the section
            title: Section title
            description: Optional section description
            collapsed: Whether section starts collapsed
            order: Sort order (lower = earlier in report)

        Returns:
            The created ReportSection object
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

    def get_section(self, section_id: str) -> Optional[ReportSection]:
        """
        Get a section by its ID.

        Args:
            section_id: The section identifier

        Returns:
            The ReportSection or None if not found
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
        section_title: Optional[str] = None,
    ) -> None:
        """
        Add a reportlet to a specific section.

        Args:
            section_id: The section identifier
            reportlet: The reportlet to add
            create_if_missing: Create section if it doesn't exist
            section_title: Title for new section (if created)
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
        """
        Render the table of contents as HTML.

        Returns:
            HTML string for the table of contents
        """
        sorted_sections = sorted(self.sections, key=lambda s: s.order)

        links = []
        for section in sorted_sections:
            links.append(
                f'<li><a href="#{section.section_id}">{section.title}</a></li>'
            )

        return f'<ul class="toc-list">{"".join(links)}</ul>'

    def render_metadata(self) -> str:
        """
        Render the header metadata as HTML.

        Returns:
            HTML string for the header metadata
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
        """
        Render all sections as HTML.

        Returns:
            HTML string for all sections
        """
        sorted_sections = sorted(self.sections, key=lambda s: s.order)
        return "\n".join(section.render_html() for section in sorted_sections)

    def render_html(self) -> str:
        """
        Render the complete report as HTML.

        Returns:
            Complete HTML document as a string
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
        output_path: Union[str, Path],
        create_dirs: bool = True,
    ) -> Path:
        """
        Save the report to a file.

        Args:
            output_path: Path to save the HTML file
            create_dirs: Create parent directories if needed

        Returns:
            Path to the saved file
        """
        output_path = Path(output_path)

        if create_dirs:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        html_content = self.render_html()
        output_path.write_text(html_content, encoding="utf-8")

        return output_path

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the report to a dictionary representation.

        Returns:
            Dictionary containing all report data
        """
        return {
            "metadata": self.metadata.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportAssembler":
        """
        Create a ReportAssembler from a dictionary.

        Args:
            data: Dictionary containing report data

        Returns:
            Reconstructed ReportAssembler instance

        Note:
            This reconstructs the structure but not the reportlet instances.
            Use this for loading report metadata, not for full reconstruction.
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
