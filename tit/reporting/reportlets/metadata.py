"""
Metadata-focused reportlets for TI-Toolbox reports.

This module provides specialized reportlets for displaying conductivity tables,
processing steps, and other structured metadata.
"""

from typing import Any

from ..core.base import BaseReportlet
from ..core.protocols import ReportletType, StatusType

# Default TI conductivity values with sources
DEFAULT_CONDUCTIVITIES = {
    "white_matter": {
        "value": 0.126,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "gray_matter": {
        "value": 0.275,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "csf": {
        "value": 1.654,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "bone": {
        "value": 0.010,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "scalp": {
        "value": 0.465,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "eye_balls": {
        "value": 0.500,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "compact_bone": {
        "value": 0.008,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "spongy_bone": {
        "value": 0.025,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "blood": {
        "value": 0.600,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
    "muscle": {
        "value": 0.160,
        "unit": "S/m",
        "source": "SimNIBS default",
    },
}


class ConductivityTableReportlet(BaseReportlet):
    """
    Reportlet for displaying tissue conductivity values.

    Shows conductivity values for different tissue types with
    their sources/references.
    """

    def __init__(
        self,
        conductivities: dict[str, dict[str, Any]] | None = None,
        title: str | None = None,
        show_sources: bool = True,
        conductivity_type: str = "scalar",
    ):
        """
        Initialize the conductivity table reportlet.

        Args:
            conductivities: Dict mapping tissue names to conductivity info
            title: Title for the table
            show_sources: Whether to show source references
            conductivity_type: Type of conductivity (scalar, anisotropic, etc.)
        """
        super().__init__(title or "Tissue Conductivities")
        self.conductivities = conductivities or DEFAULT_CONDUCTIVITIES.copy()
        self.show_sources = show_sources
        self.conductivity_type = conductivity_type

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.TABLE

    def set_conductivity(
        self,
        tissue: str,
        value: float,
        unit: str = "S/m",
        source: str | None = None,
    ) -> None:
        """
        Set conductivity for a tissue type.

        Args:
            tissue: Tissue name
            value: Conductivity value
            unit: Unit of measurement
            source: Source reference
        """
        self.conductivities[tissue] = {
            "value": value,
            "unit": unit,
            "source": source or "User-defined",
        }

    def render_html(self) -> str:
        """Render the conductivity table as HTML."""
        # Build table headers
        headers = ["Tissue", "Conductivity"]
        if self.show_sources:
            headers.append("Source")

        header_cells = "".join(f"<th>{h}</th>" for h in headers)

        # Build table rows
        rows = []
        for tissue, data in self.conductivities.items():
            # Handle both string keys ("white_matter") and integer keys (1)
            if isinstance(tissue, int):
                # Integer key - use the 'name' field from data if available
                tissue_name = data.get("name", f"Tissue {tissue}")
            else:
                tissue_name = str(tissue).replace("_", " ").title()
            # Handle both 'value' and 'conductivity' field names
            value = data.get("value", data.get("conductivity", 0))
            unit = data.get("unit", "S/m")

            cells = [
                f"<td>{tissue_name}</td>",
                f"<td>{value:.4f} {unit}</td>",
            ]

            if self.show_sources:
                # Handle both 'source' and 'reference' field names
                source = data.get("source", data.get("reference", "—"))
                cells.append(f"<td class='source-cell'>{source}</td>")

            rows.append(f"<tr>{''.join(cells)}</tr>")

        title_html = f"<h3>{self._title}</h3>" if self._title else ""
        type_badge = (
            f'<span class="conductivity-type-badge">{self.conductivity_type}</span>'
        )

        return f"""
        <div class="reportlet conductivity-reportlet" id="{self.reportlet_id}">
            {title_html}
            {type_badge}
            <div class="table-wrapper">
                <table class="data-table conductivity-table striped">
                    <thead>
                        <tr>{header_cells}</tr>
                    </thead>
                    <tbody>
                        {"".join(rows)}
                    </tbody>
                </table>
            </div>
        </div>
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "conductivity_type": self.conductivity_type,
            "conductivities": self.conductivities,
            "show_sources": self.show_sources,
        }


class SummaryCardsReportlet(BaseReportlet):
    """
    Reportlet for displaying key summary metrics as cards.

    Shows important values in a prominent card grid layout.
    """

    def __init__(
        self,
        title: str | None = None,
        cards: list[dict[str, Any]] | None = None,
        columns: int = 4,
    ):
        """
        Initialize the summary cards reportlet.

        Args:
            title: Title for the summary section
            cards: List of card data dicts
            columns: Number of columns in grid
        """
        super().__init__(title)
        self.cards: list[dict[str, Any]] = cards or []
        self.columns = columns

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.METADATA

    def add_card(
        self,
        label: str,
        value: Any,
        icon: str | None = None,
        color: str | None = None,
        subtitle: str | None = None,
    ) -> None:
        """
        Add a summary card.

        Args:
            label: Card label
            value: Card value
            icon: Optional icon character
            color: Optional accent color
            subtitle: Optional subtitle text
        """
        self.cards.append(
            {
                "label": label,
                "value": value,
                "icon": icon,
                "color": color,
                "subtitle": subtitle,
            }
        )

    def render_html(self) -> str:
        """Render the summary cards as HTML."""
        if not self.cards:
            return ""

        card_items = []
        for card in self.cards:
            icon_html = (
                f'<span class="card-icon">{card["icon"]}</span>'
                if card.get("icon")
                else ""
            )
            subtitle_html = (
                f'<div class="card-subtitle">{card["subtitle"]}</div>'
                if card.get("subtitle")
                else ""
            )
            style = f'border-top-color: {card["color"]};' if card.get("color") else ""

            card_items.append(f"""
                <div class="summary-card" style="{style}">
                    {icon_html}
                    <div class="card-label">{card["label"]}</div>
                    <div class="card-value">{card["value"]}</div>
                    {subtitle_html}
                </div>
                """)

        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        return f"""
        <div class="reportlet summary-cards-reportlet" id="{self.reportlet_id}">
            {title_html}
            <div class="card-grid columns-{self.columns}">
                {"".join(card_items)}
            </div>
        </div>
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "cards": self.cards,
            "columns": self.columns,
        }


class ParameterListReportlet(BaseReportlet):
    """
    Reportlet for displaying a categorized list of parameters.

    Organizes parameters into groups with clear visual hierarchy.
    """

    def __init__(
        self,
        title: str | None = None,
        parameters: dict[str, dict[str, Any]] | None = None,
    ):
        """
        Initialize the parameter list reportlet.

        Args:
            title: Title for the parameters section
            parameters: Dict of category -> {param_name: param_value}
        """
        super().__init__(title or "Parameters")
        self.parameters: dict[str, dict[str, Any]] = parameters or {}

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.METADATA

    def add_category(self, category: str, params: dict[str, Any]) -> None:
        """
        Add a parameter category.

        Args:
            category: Category name
            params: Dict of parameter name to value
        """
        self.parameters[category] = params

    def add_parameter(self, category: str, name: str, value: Any) -> None:
        """
        Add a single parameter to a category.

        Args:
            category: Category name
            name: Parameter name
            value: Parameter value
        """
        if category not in self.parameters:
            self.parameters[category] = {}
        self.parameters[category][name] = value

    def _format_value(self, value: Any) -> str:
        """Format parameter value for display."""
        if value is None:
            return "<em>N/A</em>"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        if isinstance(value, dict):
            items = [f"{k}: {v}" for k, v in value.items()]
            return "<br>".join(items)
        if isinstance(value, float):
            return f"{value:.4g}"
        return str(value)

    def render_html(self) -> str:
        """Render the parameter list as HTML."""
        if not self.parameters:
            return ""

        category_sections = []
        for category, params in self.parameters.items():
            rows = []
            for name, value in params.items():
                formatted_name = name.replace("_", " ").title()
                formatted_value = self._format_value(value)
                rows.append(f"""<tr>
                        <td class="param-name">{formatted_name}</td>
                        <td class="param-value">{formatted_value}</td>
                    </tr>""")

            category_sections.append(f"""
                <div class="parameter-category">
                    <h4>{category}</h4>
                    <table class="data-table compact">
                        <tbody>{"".join(rows)}</tbody>
                    </table>
                </div>
                """)

        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        return f"""
        <div class="reportlet parameter-list-reportlet" id="{self.reportlet_id}">
            {title_html}
            {"".join(category_sections)}
        </div>
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "parameters": self.parameters,
        }
