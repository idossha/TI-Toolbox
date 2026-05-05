"""
Text-based reportlets for TI-Toolbox reports.

This module provides reportlets for displaying text content,
including methods boilerplate text for publications.
"""

from html import escape
from typing import Any

from ..core.base import BaseReportlet
from ..core.protocols import ReportletType


class SimulationMethodsBuilder:
    """Build concise provenance-backed simulation methods text."""

    ANISOTROPIC_MODES = {"vn", "dir", "mc"}

    def __init__(self, parameters: dict[str, Any] | None = None):
        self.parameters = parameters or {}

    def build(self) -> str:
        """Return concise publication-oriented methods text."""
        paragraphs = [
            self._build_overview_paragraph(),
            self._build_modeling_paragraph(),
            self._build_output_paragraph(),
        ]
        return "\n\n".join(p for p in paragraphs if p)

    def _build_overview_paragraph(self) -> str:
        pair_count = self._max_pair_count()
        simulation_mode = self._simulation_mode(pair_count)
        mode_text = (
            f"multipolar temporal interference (mTI; {pair_count} electrode pairs)"
            if simulation_mode.lower() == "mti" or pair_count >= 4
            else "temporal interference (TI)"
        )
        citation = (
            "[Grossman2017; Botzanowski2025]"
            if simulation_mode.lower() == "mti" or pair_count >= 4
            else "[Grossman2017]"
        )
        return (
            "Temporal interference stimulation simulations were performed with "
            f"TI-Toolbox for {self._subjects_text()} using {self._montages_text()}. "
            f"The report describes {mode_text}; {self._pair_sentence()} {citation}."
        )

    def _build_modeling_paragraph(self) -> str:
        electrode_text = self._electrode_text()
        placement_text = self._placement_text()
        conductivity_text = self._conductivity_text()
        return (
            f"{electrode_text} Electrode positions were derived from {placement_text}. "
            "Subject-specific head models and finite-element electric-field solves "
            f"used the SimNIBS/CHARM workflow with {conductivity_text} "
            "[Saturnino2019; Puonti2020; Saturnino2015; Jurcak2007]."
        )

    def _build_output_paragraph(self) -> str:
        pair_count = self._max_pair_count()
        mode = self._simulation_mode(pair_count).lower()
        if mode == "mti" or pair_count >= 4:
            output_text = "multipolar TI field outputs"
        else:
            output_text = "TI_max and TI_normal field outputs"

        config_paths = self.parameters.get("config_paths") or []
        config_text = (
            " Report metadata were reloaded from saved simulation provenance."
            if config_paths
            else " Report metadata were taken from the available simulation provenance."
        )
        return (
            f"TI-Toolbox post-processing generated {output_text} and exported mesh or "
            f"NIfTI derivatives when available.{config_text} Software versions and "
            "audit metadata are listed in the report, following BIDS-style derivative "
            "provenance [BIDS2016]."
        )

    def _subjects_text(self) -> str:
        subjects = self.parameters.get("subjects") or []
        ids = [s.get("subject_id") for s in subjects if s.get("subject_id")]
        if not ids and self.parameters.get("subject_id"):
            ids = [self.parameters["subject_id"]]
        if not ids:
            return "the recorded subject(s)"
        if len(ids) == 1:
            return f"subject {ids[0]}"
        return "subjects " + ", ".join(map(str, ids))

    def _montages_text(self) -> str:
        names = [m.get("name") for m in self._montages() if m.get("name")]
        if not names and self.parameters.get("montage_name"):
            names = [self.parameters["montage_name"]]
        if not names:
            return "the recorded montage(s)"
        if len(names) == 1:
            return f"montage {names[0]}"
        return "montages " + ", ".join(map(str, names))

    def _pair_sentence(self) -> str:
        summaries = []
        intensities = []
        for montage in self._montages():
            for pair in montage.get("electrode_pairs", []):
                e1 = pair.get("electrode1", "")
                e2 = pair.get("electrode2", "")
                if e1 or e2:
                    summaries.append(f"{e1}-{e2}".strip("-"))
                if pair.get("intensity") not in (None, ""):
                    intensities.append(self._format_current(pair["intensity"]))

        if summaries:
            pairs_text = self._join_human(summaries)
            if len(set(intensities)) == 1 and intensities:
                return f"the modeled electrode pairs were {pairs_text} at {intensities[0]} mA per pair"
            if intensities:
                return f"the modeled electrode pairs were {pairs_text} with recorded per-pair currents"
            return f"the modeled electrode pairs were {pairs_text}"
        if self.parameters.get("intensity"):
            return (
                "the modeled electrode pairs used "
                f"{self._format_current(self.parameters['intensity'])} mA per pair"
            )
        return "electrode pairs and currents were taken from the saved provenance"

    def _electrode_text(self) -> str:
        geometry = self._electrode_geometry()
        shape = geometry.get("shape") or self.parameters.get("electrode_shape")
        dimensions = geometry.get("dimensions") or self.parameters.get("electrode_size")
        gel = geometry.get("gel_thickness") or self.parameters.get("gel_thickness")
        rubber = geometry.get("rubber_thickness") or self.parameters.get(
            "rubber_thickness"
        )

        dim_text = self._format_dimensions(dimensions)
        if shape and dim_text:
            electrode_text = (
                f"Electrodes were modeled as {shape} {dim_text} mm electrodes"
            )
        elif shape:
            electrode_text = f"Electrodes were modeled as {shape} electrodes"
        elif dim_text:
            electrode_text = f"Electrodes were modeled with {dim_text} mm dimensions"
        else:
            electrode_text = (
                "Electrode geometry was modeled from the available simulation metadata"
            )

        layers = []
        if gel is not None:
            layers.append(f"{self._format_number(gel)} mm conductive gel")
        if rubber is not None:
            layers.append(f"{self._format_number(rubber)} mm rubber")
        if layers:
            electrode_text += " with " + " and ".join(layers) + " layers"
        return electrode_text + "."

    def _conductivity_text(self) -> str:
        conductivity = str(
            self.parameters.get("conductivity_type")
            or self.parameters.get("conductivity")
            or "scalar"
        )
        conductivities = self.parameters.get("conductivities") or {}
        custom = self._has_custom_conductivity(conductivities)
        if conductivity.lower() in self.ANISOTROPIC_MODES:
            return f"anisotropic conductivity mode {conductivity}"
        if custom:
            return "scalar conductivity and recorded tissue-conductivity overrides"
        return "scalar conductivity and default SimNIBS tissue conductivities"

    def _placement_text(self) -> str:
        montages = self._montages()
        modes = {str(m.get("montage_mode") or "").lower() for m in montages}
        eeg_nets = {m.get("eeg_net") for m in montages if m.get("eeg_net")}
        if any(mode in {"freehand", "flex_free"} for mode in modes):
            return "freehand or optimized XYZ coordinates"
        if "flex_mapped" in modes:
            net_text = f" ({', '.join(sorted(map(str, eeg_nets)))})" if eeg_nets else ""
            return f"flex-search electrodes mapped to an EEG net{net_text}"
        if eeg_nets:
            return f"the EEG net {', '.join(sorted(map(str, eeg_nets)))}"
        if self.parameters.get("eeg_net"):
            return f"the EEG net {self.parameters['eeg_net']}"
        return "the recorded montage provenance"

    def _electrode_geometry(self) -> dict[str, Any]:
        geometry = self.parameters.get("electrode_geometry")
        if isinstance(geometry, dict):
            return geometry
        electrode_parameters = self.parameters.get("electrode_parameters")
        if isinstance(electrode_parameters, dict):
            return electrode_parameters
        return {}

    def _montages(self) -> list[dict[str, Any]]:
        montages = self.parameters.get("montages") or []
        return [m for m in montages if isinstance(m, dict)]

    def _max_pair_count(self) -> int:
        counts = [len(m.get("electrode_pairs", [])) for m in self._montages()]
        return max(counts) if counts else 0

    def _simulation_mode(self, pair_count: int) -> str:
        mode = self.parameters.get("simulation_mode") or ""
        if str(mode).lower() in {"mti", "multipolar", "m"}:
            return "mTI"
        if pair_count >= 4:
            return "mTI"
        return "TI"

    @staticmethod
    def _format_dimensions(dimensions: Any) -> str:
        if dimensions is None:
            return ""
        if isinstance(dimensions, str):
            lower = dimensions.lower()
            return dimensions[:-2].strip() if lower.endswith("mm") else dimensions
        if isinstance(dimensions, (list, tuple)) and len(dimensions) >= 2:
            return f"{SimulationMethodsBuilder._format_number(dimensions[0])}x{SimulationMethodsBuilder._format_number(dimensions[1])}"
        return str(dimensions)

    @staticmethod
    def _format_number(value: Any) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:g}"

    @staticmethod
    def _format_current(value: Any) -> str:
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _join_human(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + f", and {items[-1]}"

    @staticmethod
    def _has_custom_conductivity(conductivities: Any) -> bool:
        if not isinstance(conductivities, dict):
            return False
        for value in conductivities.values():
            if isinstance(value, dict):
                source = str(
                    value.get("source") or value.get("reference") or ""
                ).lower()
                if "custom" in source or "user" in source:
                    return True
        return False


class MethodsBoilerplateReportlet(BaseReportlet):
    """
    Reportlet for displaying methods section boilerplate text.

    Generates publication-ready text describing the methods used
    in the analysis, with a copy-to-clipboard button.
    """

    def __init__(
        self,
        title: str | None = None,
        boilerplate_text: str | None = None,
        pipeline_type: str = "simulation",
        parameters: dict[str, Any] | None = None,
    ):
        """
        Initialize the methods boilerplate reportlet.

        Args:
            title: Title for the section
            boilerplate_text: Pre-written boilerplate text
            pipeline_type: Type of pipeline (simulation, preprocessing, optimization)
            parameters: Parameters to include in generated text
        """
        super().__init__(title or "Methods Boilerplate")
        self._boilerplate_text = boilerplate_text
        self.pipeline_type = pipeline_type
        self.parameters = parameters or {}

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.TEXT

    def set_boilerplate(self, text: str) -> None:
        """Set the boilerplate text directly."""
        self._boilerplate_text = text

    def generate_boilerplate(self) -> str:
        """
        Generate boilerplate text based on pipeline type and parameters.

        Returns:
            Generated boilerplate text
        """
        if self._boilerplate_text:
            return self._boilerplate_text

        match self.pipeline_type:
            case "simulation":
                return self._generate_simulation_boilerplate()
            case "preprocessing":
                return self._generate_preprocessing_boilerplate()
            case "optimization" | "flex-search":
                return self._generate_optimization_boilerplate()
            case _:
                return self._generate_generic_boilerplate()

    def _generate_simulation_boilerplate(self) -> str:
        """Generate simulation-specific boilerplate."""
        return SimulationMethodsBuilder(self.parameters).build()

    def _generate_preprocessing_boilerplate(self) -> str:
        """Generate preprocessing-specific boilerplate."""
        parts = []

        parts.append(
            "Structural MRI data were preprocessed using TI-Toolbox's "
            "preprocessing pipeline."
        )

        # Add FreeSurfer info
        if self.parameters.get("freesurfer_version"):
            version = self.parameters.get("freesurfer_version")
            parts.append(
                f"Cortical reconstruction was performed using FreeSurfer {version} "
                "(Fischl, 2012)."
            )

        # Add SimNIBS info
        if self.parameters.get("simnibs_version"):
            version = self.parameters.get("simnibs_version")
            parts.append(
                f"Head mesh generation was performed using SimNIBS {version} "
                "(Thielscher et al., 2015)."
            )

        # Add DTI info
        if self.parameters.get("qsiprep_version"):
            version = self.parameters.get("qsiprep_version")
            parts.append(
                f"Diffusion MRI preprocessing was performed using QSIPrep {version} "
                "(Cieslak et al., 2021) for estimation of anisotropic conductivities."
            )

        return " ".join(parts)

    def _generate_optimization_boilerplate(self) -> str:
        """Generate flex-search/optimization-specific boilerplate."""
        target = self.parameters.get("target_region") or "the target region"
        n_candidates = self.parameters.get("n_candidates")
        candidate_text = (
            f" Candidate configurations evaluated in this report: {n_candidates}."
            if n_candidates is not None
            else ""
        )

        return "\n\n".join(
            [
                (
                    "Electrode placement optimization was performed with the "
                    "TI-Toolbox flex-search workflow, which integrates subject-specific "
                    "head modeling, montage optimization, simulation, and ROI analysis "
                    "for temporal interference research [Haber2026]."
                ),
                (
                    f"The optimization targeted {target} and searched electrode-pair "
                    "configurations to increase the temporal-interference modulation "
                    "envelope in the ROI while limiting off-target fields "
                    f"[Grossman2017].{candidate_text}"
                ),
                (
                    "The flex-search strategy follows the leadfield-free optimization "
                    "principle described by Weise et al., allowing electrode positions "
                    "or mapped electrode labels to be optimized directly on the head "
                    "surface while respecting geometric constraints such as electrode "
                    "separation and non-overlap [Weise2024]."
                ),
            ]
        )

    def _generate_generic_boilerplate(self) -> str:
        """Generate generic boilerplate."""
        return (
            "Analysis was performed using TI-Toolbox, a Python-based software "
            "package for temporal interference stimulation simulation and "
            "optimization. TI-Toolbox integrates with SimNIBS for finite element "
            "electric field simulations and provides tools for electrode "
            "placement optimization."
        )

    def render_html(self) -> str:
        """Render the boilerplate text as paragraph-based HTML."""
        boilerplate = self.generate_boilerplate()
        paragraphs = [p.strip() for p in boilerplate.split("\n\n") if p.strip()]
        paragraph_html = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)

        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        return f"""
        <div class="reportlet methods-boilerplate-reportlet" id="{self.reportlet_id}">
            {title_html}
            <p class="boilerplate-intro">
                The following text can be used as a starting point for the methods
                section of a publication. Please verify and adapt as needed.
            </p>
            <button class="copy-btn" onclick="copyToClipboard('{self.reportlet_id}-content')">
                Copy to Clipboard
            </button>
            <div class="text-content copyable methods-text" id="{self.reportlet_id}-content">
                {paragraph_html}
            </div>
        </div>
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "pipeline_type": self.pipeline_type,
            "parameters": self.parameters,
            "boilerplate": self.generate_boilerplate(),
        }


class DescriptionReportlet(BaseReportlet):
    """
    Reportlet for displaying descriptive text content.

    Renders paragraphs of text with optional formatting.
    """

    def __init__(
        self,
        content: str,
        title: str | None = None,
        format_type: str = "paragraphs",
    ):
        """
        Initialize the description reportlet.

        Args:
            content: Text content to display
            title: Optional section title
            format_type: How to format content (paragraphs, html, preformatted)
        """
        super().__init__(title)
        self.content = content
        self.format_type = format_type

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.TEXT

    def render_html(self) -> str:
        """Render the description text as HTML."""
        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        if self.format_type == "html":
            formatted_content = self.content
        elif self.format_type == "preformatted":
            formatted_content = f"<pre>{self._escape_html(self.content)}</pre>"
        else:
            # Split into paragraphs
            paragraphs = self.content.split("\n\n")
            formatted_content = "".join(
                f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()
            )

        return f"""
        <div class="reportlet description-reportlet" id="{self.reportlet_id}">
            {title_html}
            <div class="text-content">
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
            "format_type": self.format_type,
        }


class CommandLogReportlet(BaseReportlet):
    """
    Reportlet for displaying command execution logs.

    Shows commands that were run with their outputs in a
    terminal-like display.
    """

    def __init__(
        self,
        title: str | None = None,
        commands: list[dict[str, str]] | None = None,
    ):
        """
        Initialize the command log reportlet.

        Args:
            title: Optional section title
            commands: List of command dicts with 'command' and optional 'output'
        """
        super().__init__(title or "Command Log")
        self.commands: list[dict[str, str]] = commands or []

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.TEXT

    def add_command(
        self,
        command: str,
        output: str | None = None,
        status: str = "success",
    ) -> None:
        """
        Add a command to the log.

        Args:
            command: The command that was executed
            output: Command output (if any)
            status: Execution status (success, error)
        """
        self.commands.append(
            {
                "command": command,
                "output": output or "",
                "status": status,
            }
        )

    def render_html(self) -> str:
        """Render the command log as HTML."""
        if not self.commands:
            return ""

        command_items = []
        for cmd in self.commands:
            status_class = "success" if cmd.get("status") == "success" else "error"
            output_html = ""
            if cmd.get("output"):
                output_html = f'<div class="command-output">{self._escape_html(cmd["output"])}</div>'

            command_items.append(f"""
                <div class="command-item {status_class}">
                    <div class="command-prompt">$ {self._escape_html(cmd["command"])}</div>
                    {output_html}
                </div>
                """)

        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        return f"""
        <div class="reportlet command-log-reportlet" id="{self.reportlet_id}">
            {title_html}
            <div class="command-log">
                {"".join(command_items)}
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
            "commands": self.commands,
        }
