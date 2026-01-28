"""
Text-based reportlets for TI-Toolbox reports.

This module provides reportlets for displaying text content,
including methods boilerplate text for publications.
"""

from typing import Any, Dict, List, Optional

from ..core.base import BaseReportlet
from ..core.protocols import ReportletType


class MethodsBoilerplateReportlet(BaseReportlet):
    """
    Reportlet for displaying methods section boilerplate text.

    Generates publication-ready text describing the methods used
    in the analysis, with a copy-to-clipboard button.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        boilerplate_text: Optional[str] = None,
        pipeline_type: str = "simulation",
        parameters: Optional[Dict[str, Any]] = None,
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

        if self.pipeline_type == "simulation":
            return self._generate_simulation_boilerplate()
        elif self.pipeline_type == "preprocessing":
            return self._generate_preprocessing_boilerplate()
        elif self.pipeline_type == "optimization":
            return self._generate_optimization_boilerplate()
        else:
            return self._generate_generic_boilerplate()

    def _generate_simulation_boilerplate(self) -> str:
        """Generate simulation-specific boilerplate."""
        parts = []

        parts.append(
            "Temporal interference (TI) stimulation simulations were performed "
            "using TI-Toolbox, a Python-based software package for planning and "
            "simulating non-invasive deep brain stimulation."
        )

        # Add conductivity info
        cond_type = self.parameters.get("conductivity_type", "scalar")
        parts.append(
            f"Electric field simulations used {cond_type} conductivity values "
            "based on SimNIBS defaults (Thielscher et al., 2015)."
        )

        # Add electrode info
        if self.parameters.get("electrode_shape"):
            shape = self.parameters.get("electrode_shape", "circular")
            size = self.parameters.get("electrode_size", "not specified")
            parts.append(f"Electrodes were modeled as {shape} with dimensions {size}.")

        # Add intensity info
        if self.parameters.get("intensity"):
            intensity = self.parameters.get("intensity")
            parts.append(
                f"Stimulation was applied with a peak current of {intensity} mA."
            )

        parts.append(
            "The simulation framework is based on the finite element method "
            "implementation in SimNIBS (Saturnino et al., 2019)."
        )

        return " ".join(parts)

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
        """Generate optimization-specific boilerplate."""
        parts = []

        parts.append(
            "Electrode placement optimization was performed using TI-Toolbox's "
            "flex-search algorithm."
        )

        # Add optimization details
        if self.parameters.get("optimization_method"):
            method = self.parameters.get("optimization_method")
            parts.append(f"The {method} optimization strategy was employed.")

        if self.parameters.get("target_region"):
            target = self.parameters.get("target_region")
            parts.append(f"The target region was defined as {target}.")

        parts.append(
            "The optimization aims to maximize the temporal interference "
            "modulation envelope in the target region while minimizing "
            "off-target stimulation (Grossman et al., 2017)."
        )

        return " ".join(parts)

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
        """Render the boilerplate text as HTML."""
        boilerplate = self.generate_boilerplate()

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
            <div class="text-content monospace copyable" id="{self.reportlet_id}-content">
                {boilerplate}
            </div>
        </div>
        """

    def to_dict(self) -> Dict[str, Any]:
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
        title: Optional[str] = None,
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

    def to_dict(self) -> Dict[str, Any]:
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
        title: Optional[str] = None,
        commands: Optional[List[Dict[str, str]]] = None,
    ):
        """
        Initialize the command log reportlet.

        Args:
            title: Optional section title
            commands: List of command dicts with 'command' and optional 'output'
        """
        super().__init__(title or "Command Log")
        self.commands: List[Dict[str, str]] = commands or []

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.TEXT

    def add_command(
        self,
        command: str,
        output: Optional[str] = None,
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

            command_items.append(
                f"""
                <div class="command-item {status_class}">
                    <div class="command-prompt">$ {self._escape_html(cmd["command"])}</div>
                    {output_html}
                </div>
                """
            )

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "commands": self.commands,
        }
