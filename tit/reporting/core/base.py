"""Base reportlet classes for the TI-Toolbox reporting system.

Provides the foundational reportlet implementations that can be used
directly or extended for domain-specific purposes.

Public API
----------
BaseReportlet
    Abstract base class for all reportlets.
MetadataReportlet
    Key-value metadata display (table or card grid).
ImageReportlet
    Inline image display (base64-embedded).
TableReportlet
    Tabular data display.
TextReportlet
    Text content display with optional copy-to-clipboard.
ErrorReportlet
    Error and warning message display.
ReferencesReportlet
    Citation and reference list display.

See Also
--------
tit.reporting.reportlets : Domain-specific reportlet subclasses.
tit.reporting.core.protocols : Protocol and enum definitions.
"""

import base64
import io
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .protocols import ReportletType, SeverityLevel, StatusType


class BaseReportlet(ABC):
    """Abstract base class for all reportlets.

    Subclasses must implement ``reportlet_type``, ``render_html``, and
    ``to_dict``.

    Parameters
    ----------
    title : str or None, optional
        Optional title displayed above the reportlet content.

    See Also
    --------
    MetadataReportlet : Key-value pair display.
    ImageReportlet : Inline image display.
    TableReportlet : Tabular data display.
    """

    def __init__(self, title: str | None = None):
        self._title = title
        self._id = str(uuid.uuid4())[:8]

    @property
    @abstractmethod
    def reportlet_type(self) -> ReportletType:
        """Return the type of this reportlet."""
        pass

    @property
    def reportlet_id(self) -> str:
        """Return a unique identifier for this reportlet."""
        return f"{self.reportlet_type.name.lower()}-{self._id}"

    @property
    def title(self) -> str | None:
        """Return the title of this reportlet."""
        return self._title

    @abstractmethod
    def render_html(self) -> str:
        """Render the reportlet as an HTML fragment."""
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert the reportlet to a dictionary representation."""
        pass


class MetadataReportlet(BaseReportlet):
    """
    Reportlet for displaying metadata as key-value pairs.

    Supports two display modes:
    - 'table': Traditional table layout
    - 'cards': Modern card grid layout
    """

    def __init__(
        self,
        data: dict[str, Any],
        title: str | None = None,
        display_mode: str = "table",
        columns: int = 2,
    ):
        super().__init__(title)
        self.data = data
        self.display_mode = display_mode
        self.columns = columns

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.METADATA

    def render_html(self) -> str:
        """Render metadata as HTML table or cards."""
        if self.display_mode == "cards":
            return self._render_cards()
        return self._render_table()

    def _render_table(self) -> str:
        """Render as a two-column table."""
        rows = []
        for key, value in self.data.items():
            formatted_key = self._format_key(key)
            formatted_value = self._format_value(value)
            rows.append(
                f"<tr><td class='key-cell'>{formatted_key}</td>"
                f"<td class='value-cell'>{formatted_value}</td></tr>"
            )

        title_html = f"<h3>{self._title}</h3>" if self._title else ""
        return f"""
        <div class="reportlet metadata-reportlet table-mode" id="{self.reportlet_id}">
            {title_html}
            <table class="metadata-table">
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </div>
        """

    def _render_cards(self) -> str:
        """Render as card grid."""
        cards = []
        for key, value in self.data.items():
            formatted_key = self._format_key(key)
            formatted_value = self._format_value(value)
            cards.append(f"""
                <div class="metadata-card">
                    <div class="card-label">{formatted_key}</div>
                    <div class="card-value">{formatted_value}</div>
                </div>
                """)

        title_html = f"<h3>{self._title}</h3>" if self._title else ""
        return f"""
        <div class="reportlet metadata-reportlet card-mode" id="{self.reportlet_id}">
            {title_html}
            <div class="card-grid columns-{self.columns}">
                {"".join(cards)}
            </div>
        </div>
        """

    def _format_key(self, key: Any) -> str:
        """Format common metadata keys for display."""
        key_text = str(key)
        special_labels = {
            "ti_toolbox": "TI-Toolbox",
            "simnibs": "SimNIBS",
            "dcm2niix": "dcm2niix",
            "freesurfer": "FreeSurfer",
            "qsiprep": "QSIPrep",
        }
        return special_labels.get(key_text.lower(), key_text.replace("_", " ").title())

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if value is None:
            return "<em>N/A</em>"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        if isinstance(value, dict):
            items = [f"{k}: {v}" for k, v in value.items()]
            return "<br>".join(items)
        return str(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "data": self.data,
            "display_mode": self.display_mode,
            "columns": self.columns,
        }


class ImageReportlet(BaseReportlet):
    """
    Reportlet for displaying images.

    Supports embedding images as base64 or referencing external paths.
    Images can be loaded from file paths, PIL Images, or raw bytes.
    """

    def __init__(
        self,
        image_source: str | Path | bytes | Any | None = None,
        title: str | None = None,
        caption: str | None = None,
        alt_text: str | None = None,
        width: str | None = None,
        height: str | None = None,
    ):
        super().__init__(title)
        self.caption = caption
        self.alt_text = alt_text or title or "Image"
        self.width = width
        self.height = height
        self._base64_data: str | None = None
        self._mime_type: str = "image/png"

        if image_source is not None:
            self._load_image(image_source)

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.IMAGE

    def _load_image(self, source: str | Path | bytes | Any) -> None:
        """Load image from various sources and convert to base64."""
        if isinstance(source, (str, Path)):
            path = Path(source)
            if path.exists():
                self._mime_type = self._get_mime_type(path)
                with open(path, "rb") as f:
                    self._base64_data = base64.b64encode(f.read()).decode("utf-8")
        elif isinstance(source, bytes):
            self._base64_data = base64.b64encode(source).decode("utf-8")
        else:
            # Assume PIL Image
            try:
                buffer = io.BytesIO()
                source.save(buffer, format="PNG")
                self._base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            except (AttributeError, ValueError):
                pass

    def _get_mime_type(self, path: Path) -> str:
        """Determine MIME type from file extension."""
        suffix = path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
        }
        return mime_types.get(suffix, "image/png")

    def set_base64_data(self, data: str, mime_type: str = "image/png") -> None:
        """Directly set base64 encoded image data."""
        self._base64_data = data
        self._mime_type = mime_type

    def render_html(self) -> str:
        """Render image as HTML."""
        if not self._base64_data:
            return f"""
            <div class="reportlet image-reportlet" id="{self.reportlet_id}">
                <div class="image-placeholder">
                    <em>No image available</em>
                </div>
            </div>
            """

        style_parts = []
        if self.width:
            style_parts.append(f"max-width: {self.width}")
        if self.height:
            style_parts.append(f"max-height: {self.height}")
        style = "; ".join(style_parts) if style_parts else ""

        title_html = f"<h3>{self._title}</h3>" if self._title else ""
        caption_html = (
            f'<figcaption class="image-caption">{self.caption}</figcaption>'
            if self.caption
            else ""
        )

        return f"""
        <div class="reportlet image-reportlet" id="{self.reportlet_id}">
            {title_html}
            <figure class="image-figure">
                <img src="data:{self._mime_type};base64,{self._base64_data}"
                     alt="{self.alt_text}"
                     style="{style}"
                     class="report-image" />
                {caption_html}
            </figure>
        </div>
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "caption": self.caption,
            "alt_text": self.alt_text,
            "has_image": self._base64_data is not None,
        }


class TableReportlet(BaseReportlet):
    """
    Reportlet for displaying tabular data.

    Supports various input formats including lists of dicts,
    lists of lists, and pandas DataFrames.
    """

    def __init__(
        self,
        data: list[dict] | list[list] | Any,
        title: str | None = None,
        headers: list[str] | None = None,
        sortable: bool = False,
        striped: bool = True,
        compact: bool = False,
    ):
        super().__init__(title)
        self.headers: list[str] = []
        self.rows: list[list[Any]] = []
        self.sortable = sortable
        self.striped = striped
        self.compact = compact

        self._process_data(data, headers)

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.TABLE

    def _process_data(
        self, data: list[dict] | list[list] | Any, headers: list[str] | None
    ) -> None:
        """Process input data into headers and rows."""
        # Handle pandas DataFrame
        if hasattr(data, "to_dict") and hasattr(data, "columns"):
            self.headers = list(data.columns)
            self.rows = data.values.tolist()
            return

        if not data:
            return

        # Handle list of dicts
        if isinstance(data[0], dict):
            if headers:
                self.headers = headers
            else:
                self.headers = list(data[0].keys())
            self.rows = [[row.get(h, "") for h in self.headers] for row in data]
            return

        # Handle list of lists
        if isinstance(data[0], (list, tuple)):
            if headers:
                self.headers = headers
            self.rows = [list(row) for row in data]
            return

    def render_html(self) -> str:
        """Render table as HTML."""
        if not self.rows and not self.headers:
            return f"""
            <div class="reportlet table-reportlet" id="{self.reportlet_id}">
                <em>No data available</em>
            </div>
            """

        classes = ["data-table"]
        if self.striped:
            classes.append("striped")
        if self.compact:
            classes.append("compact")
        if self.sortable:
            classes.append("sortable")

        header_html = ""
        if self.headers:
            header_cells = "".join(f"<th>{h}</th>" for h in self.headers)
            header_html = f"<thead><tr>{header_cells}</tr></thead>"

        body_rows = []
        for row in self.rows:
            cells = "".join(f"<td>{self._format_cell(c)}</td>" for c in row)
            body_rows.append(f"<tr>{cells}</tr>")
        body_html = f"<tbody>{''.join(body_rows)}</tbody>"

        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        return f"""
        <div class="reportlet table-reportlet" id="{self.reportlet_id}">
            {title_html}
            <div class="table-wrapper">
                <table class="{' '.join(classes)}">
                    {header_html}
                    {body_html}
                </table>
            </div>
        </div>
        """

    def _format_cell(self, value: Any) -> str:
        """Format a cell value for display."""
        if value is None:
            return "<em>—</em>"
        if isinstance(value, float):
            return f"{value:.4g}"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return str(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "headers": self.headers,
            "rows": self.rows,
            "sortable": self.sortable,
            "striped": self.striped,
            "compact": self.compact,
        }


class TextReportlet(BaseReportlet):
    """
    Reportlet for displaying text content.

    Supports plain text, HTML, and markdown-style formatting.
    Includes optional copy-to-clipboard functionality for boilerplate text.
    """

    def __init__(
        self,
        content: str,
        title: str | None = None,
        content_type: str = "text",
        copyable: bool = False,
        monospace: bool = False,
    ):
        super().__init__(title)
        self.content = content
        self.content_type = content_type  # 'text', 'html', 'code'
        self.copyable = copyable
        self.monospace = monospace

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.TEXT

    def render_html(self) -> str:
        """Render text content as HTML."""
        classes = ["text-content"]
        if self.monospace:
            classes.append("monospace")
        if self.copyable:
            classes.append("copyable")

        # Format content based on type
        if self.content_type == "html":
            formatted_content = self.content
        elif self.content_type == "code":
            formatted_content = (
                f"<pre><code>{self._escape_html(self.content)}</code></pre>"
            )
        else:
            # Plain text - convert newlines to paragraphs
            paragraphs = self.content.split("\n\n")
            formatted_content = "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())

        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        copy_button = ""
        if self.copyable:
            copy_button = f"""
            <button class="copy-btn" onclick="copyToClipboard('{self.reportlet_id}-content')">
                Copy to Clipboard
            </button>
            """

        return f"""
        <div class="reportlet text-reportlet" id="{self.reportlet_id}">
            {title_html}
            {copy_button}
            <div class="{' '.join(classes)}" id="{self.reportlet_id}-content">
                {formatted_content}
            </div>
        </div>
        """

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "content": self.content,
            "content_type": self.content_type,
            "copyable": self.copyable,
            "monospace": self.monospace,
        }


class ErrorReportlet(BaseReportlet):
    """
    Reportlet for displaying errors and warnings.

    Supports different severity levels with appropriate styling.
    """

    def __init__(
        self,
        messages: list[dict[str, Any]] | None = None,
        title: str | None = None,
    ):
        super().__init__(title or "Errors and Warnings")
        self.messages: list[dict[str, Any]] = messages or []

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.ERROR

    def add_message(
        self,
        message: str,
        severity: SeverityLevel = SeverityLevel.ERROR,
        context: str | None = None,
        step: str | None = None,
    ) -> None:
        """Add an error or warning message."""
        self.messages.append(
            {
                "message": message,
                "severity": (
                    severity.value if isinstance(severity, SeverityLevel) else severity
                ),
                "context": context,
                "step": step,
            }
        )

    def add_error(
        self, message: str, context: str | None = None, step: str | None = None
    ) -> None:
        """Add an error message."""
        self.add_message(message, SeverityLevel.ERROR, context, step)

    def add_warning(
        self, message: str, context: str | None = None, step: str | None = None
    ) -> None:
        """Add a warning message."""
        self.add_message(message, SeverityLevel.WARNING, context, step)

    def render_html(self) -> str:
        """Render errors and warnings as HTML."""
        if not self.messages:
            return f"""
            <div class="reportlet error-reportlet success" id="{self.reportlet_id}">
                <div class="success-message">
                    <span class="status-icon">[OK]</span>
                    No errors or warnings
                </div>
            </div>
            """

        message_items = []
        for msg in self.messages:
            severity = msg.get("severity", "error")
            icon = (
                "[!]"
                if severity == "warning"
                else "[X]" if severity in ("error", "critical") else "[i]"
            )
            context = msg.get("context", "")
            step = msg.get("step", "")

            context_html = (
                f'<span class="error-context">[{context}]</span>' if context else ""
            )
            step_html = f'<span class="error-step">Step: {step}</span>' if step else ""

            message_items.append(f"""
                <div class="message-item {severity}">
                    <span class="severity-icon">{icon}</span>
                    <div class="message-content">
                        {context_html}
                        <span class="message-text">{msg["message"]}</span>
                        {step_html}
                    </div>
                </div>
                """)

        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        return f"""
        <div class="reportlet error-reportlet" id="{self.reportlet_id}">
            {title_html}
            <div class="messages-list">
                {"".join(message_items)}
            </div>
        </div>
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "messages": self.messages,
        }


class ReferencesReportlet(BaseReportlet):
    """
    Reportlet for displaying citations and references.

    Automatically formats references in a consistent style.
    """

    def __init__(
        self,
        references: list[dict[str, str]] | None = None,
        title: str | None = None,
        show_empty_warning: bool = False,
    ):
        super().__init__(title or "References")
        self.references: list[dict[str, str]] = []
        self.show_empty_warning = show_empty_warning
        for ref in references or []:
            self.add_reference(
                key=ref["key"],
                citation=ref["citation"],
                url=ref.get("url"),
                doi=ref.get("doi"),
                label=ref.get("label"),
            )

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.REFERENCES

    def add_reference(
        self,
        key: str,
        citation: str,
        url: str | None = None,
        doi: str | None = None,
        label: str | None = None,
    ) -> None:
        """Add a reference, de-duplicating by stable reference key."""
        if any(ref.get("key") == key for ref in self.references):
            return

        self.references.append(
            {
                "key": key,
                "label": label or key,
                "citation": citation,
                "url": url,
                "doi": doi,
            }
        )

    def render_html(self) -> str:
        """Render references as HTML."""
        if not self.references:
            if not self.show_empty_warning:
                return ""
            return f"""
            <div class="reportlet references-reportlet" id="{self.reportlet_id}">
                <h3>{self._title}</h3>
                <div class="message-item warning">
                    <span class="severity-icon">[!]</span>
                    <span>No references selected.</span>
                </div>
            </div>
            """

        ref_items = []
        for ref in self.references:
            citation = ref["citation"]
            key = ref.get("key", "")
            label = ref.get("label") or key

            # Add DOI link if available
            if ref.get("doi"):
                doi_link = (
                    f'<a href="https://doi.org/{ref["doi"]}" target="_blank">[DOI]</a>'
                )
                citation = f"{citation} {doi_link}"
            elif ref.get("url"):
                url_link = f'<a href="{ref["url"]}" target="_blank">[Link]</a>'
                citation = f"{citation} {url_link}"

            ref_items.append(f"""
                <li class="reference-item" id="ref-{key}">
                    <span class="ref-key">[{label}]</span>
                    <span class="ref-citation">{citation}</span>
                </li>
                """)

        title_html = f"<h3>{self._title}</h3>"

        return f"""
        <div class="reportlet references-reportlet" id="{self.reportlet_id}">
            {title_html}
            <ol class="references-list">
                {"".join(ref_items)}
            </ol>
        </div>
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "references": self.references,
            "show_empty_warning": self.show_empty_warning,
        }
