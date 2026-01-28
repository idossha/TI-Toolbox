"""
Base report generator for TI-Toolbox.

This module provides the abstract base class for all report generators,
with common functionality for BIDS output management, software version
collection, and error tracking.
"""

import json
import os
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.assembler import ReportAssembler
from ..core.protocols import ReportMetadata, SeverityLevel
from ..core.base import ErrorReportlet
from ..reportlets.references import TIToolboxReferencesReportlet
from ..reportlets.text import MethodsBoilerplateReportlet


# BIDS constants
REPORTS_BASE_DIR = "derivatives/ti-toolbox/reports"
BIDS_VERSION = "1.8.0"


class BaseReportGenerator(ABC):
    """
    Abstract base class for all TI-Toolbox report generators.

    Provides common functionality including:
    - BIDS-compliant output path management
    - Software version collection
    - Error and warning tracking
    - Dataset description generation
    """

    def __init__(
        self,
        project_dir: Union[str, Path],
        subject_id: Optional[str] = None,
        session_id: Optional[str] = None,
        report_type: str = "general",
    ):
        """
        Initialize the base report generator.

        Args:
            project_dir: Path to the project directory
            subject_id: BIDS subject ID (without 'sub-' prefix)
            session_id: Optional session/run identifier
            report_type: Type of report being generated
        """
        self.project_dir = Path(project_dir)
        self.subject_id = subject_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_type = report_type

        # Initialize report metadata
        self.metadata = ReportMetadata(
            title=self._get_default_title(),
            subject_id=subject_id,
            session_id=session_id,
            report_type=report_type,
            project_dir=str(project_dir),
        )

        # Initialize assembler
        self.assembler = ReportAssembler(metadata=self.metadata)

        # Tracking
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.software_versions: Dict[str, str] = {}

        # Collect software versions
        self._collect_software_versions()

    @abstractmethod
    def _get_default_title(self) -> str:
        """Return the default report title."""
        pass

    @abstractmethod
    def _get_report_prefix(self) -> str:
        """Return the report filename prefix."""
        pass

    def _collect_software_versions(self) -> None:
        """Collect versions of relevant software tools."""
        # Python version
        import sys

        self.software_versions["python"] = sys.version.split()[0]

        # TI-Toolbox version
        try:
            from tit import __version__

            self.software_versions["ti_toolbox"] = __version__
        except (ImportError, AttributeError):
            self.software_versions["ti_toolbox"] = "unknown"

        # SimNIBS version
        try:
            result = subprocess.run(
                ["simnibs", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                self.software_versions["simnibs"] = result.stdout.strip()
        except Exception:
            pass

        # FreeSurfer version
        try:
            fs_home = os.environ.get("FREESURFER_HOME", "")
            if fs_home:
                version_file = Path(fs_home) / "build-stamp.txt"
                if version_file.exists():
                    self.software_versions["freesurfer"] = (
                        version_file.read_text().strip()
                    )
        except Exception:
            pass

        # dcm2niix version
        try:
            result = subprocess.run(
                ["dcm2niix", "-v"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse version from output
                for line in result.stdout.split("\n"):
                    if "version" in line.lower():
                        self.software_versions["dcm2niix"] = line.strip()
                        break
        except Exception:
            pass

    def add_error(
        self,
        message: str,
        context: Optional[str] = None,
        step: Optional[str] = None,
    ) -> None:
        """
        Add an error to the report.

        Args:
            message: Error message
            context: Context (e.g., subject ID, montage name)
            step: Processing step where error occurred
        """
        self.errors.append(
            {
                "message": message,
                "context": context,
                "step": step,
                "severity": SeverityLevel.ERROR.value,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def add_warning(
        self,
        message: str,
        context: Optional[str] = None,
        step: Optional[str] = None,
    ) -> None:
        """
        Add a warning to the report.

        Args:
            message: Warning message
            context: Context (e.g., subject ID, montage name)
            step: Processing step where warning occurred
        """
        self.warnings.append(
            {
                "message": message,
                "context": context,
                "step": step,
                "severity": SeverityLevel.WARNING.value,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def get_output_dir(self) -> Path:
        """
        Get the BIDS-compliant output directory for reports.

        Returns:
            Path to the reports directory
        """
        base_dir = self.project_dir / REPORTS_BASE_DIR

        if self.subject_id:
            return base_dir / f"sub-{self.subject_id}"
        return base_dir

    def get_output_path(self, timestamp: Optional[str] = None) -> Path:
        """
        Get the full output path for the report file.

        Args:
            timestamp: Optional timestamp string (uses current time if not provided)

        Returns:
            Full path to the report file
        """
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        prefix = self._get_report_prefix()
        filename = f"{prefix}_{timestamp}.html"

        return self.get_output_dir() / filename

    def _ensure_output_dir(self) -> Path:
        """
        Ensure the output directory exists.

        Returns:
            Path to the output directory
        """
        output_dir = self.get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _create_dataset_description(self) -> None:
        """Create or update the BIDS dataset_description.json file."""
        desc_path = self.project_dir / REPORTS_BASE_DIR / "dataset_description.json"

        description = {
            "Name": "TI-Toolbox Reports",
            "BIDSVersion": BIDS_VERSION,
            "DatasetType": "derivative",
            "GeneratedBy": [
                {
                    "Name": "TI-Toolbox",
                    "Version": self.software_versions.get("ti_toolbox", "unknown"),
                }
            ],
        }

        desc_path.parent.mkdir(parents=True, exist_ok=True)
        with open(desc_path, "w") as f:
            json.dump(description, f, indent=2)

    def _add_errors_section(self) -> None:
        """Add errors and warnings section to the report."""
        error_reportlet = ErrorReportlet(title="Errors and Warnings")

        for error in self.errors:
            error_reportlet.add_error(
                message=error["message"],
                context=error.get("context"),
                step=error.get("step"),
            )

        for warning in self.warnings:
            error_reportlet.add_warning(
                message=warning["message"],
                context=warning.get("context"),
                step=warning.get("step"),
            )

        section = self.assembler.add_section(
            section_id="errors",
            title="Errors and Warnings",
            order=90,  # Near the end
        )
        section.add_reportlet(error_reportlet)

    def _add_methods_section(
        self, pipeline_components: Optional[List[str]] = None
    ) -> None:
        """
        Add methods boilerplate section to the report.

        Args:
            pipeline_components: List of pipeline components used
        """
        methods_reportlet = MethodsBoilerplateReportlet(
            title="Methods Boilerplate",
            pipeline_type=self.report_type,
            parameters=self._get_methods_parameters(),
        )

        section = self.assembler.add_section(
            section_id="methods",
            title="Methods",
            description="The following text can be adapted for publications.",
            order=95,
        )
        section.add_reportlet(methods_reportlet)

    def _add_references_section(
        self, pipeline_components: Optional[List[str]] = None
    ) -> None:
        """
        Add references section to the report.

        Args:
            pipeline_components: List of pipeline components used
        """
        refs_reportlet = TIToolboxReferencesReportlet(
            title="References",
            include_defaults=True,
            pipeline_components=pipeline_components or [],
        )

        section = self.assembler.add_section(
            section_id="references",
            title="References",
            order=100,  # At the end
        )
        section.add_reportlet(refs_reportlet)

    def _get_methods_parameters(self) -> Dict[str, Any]:
        """
        Get parameters for methods boilerplate generation.

        Returns:
            Dictionary of parameters for the methods text
        """
        return {
            "software_versions": self.software_versions,
        }

    @abstractmethod
    def _build_report(self) -> None:
        """Build the report content. Must be implemented by subclasses."""
        pass

    def generate(self, output_path: Optional[Union[str, Path]] = None) -> Path:
        """
        Generate the HTML report.

        Args:
            output_path: Optional custom output path

        Returns:
            Path to the generated report file
        """
        # Build the report content
        self._build_report()

        # Add standard sections
        self._add_errors_section()
        self._add_methods_section(pipeline_components=[self.report_type])
        self._add_references_section(pipeline_components=[self.report_type])

        # Ensure output directory exists
        self._ensure_output_dir()

        # Create dataset description
        self._create_dataset_description()

        # Determine output path
        if output_path:
            final_path = Path(output_path)
        else:
            final_path = self.get_output_path()

        # Save the report
        self.assembler.save(final_path)

        return final_path
