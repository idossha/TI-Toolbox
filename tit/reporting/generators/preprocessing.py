"""
Preprocessing report generator for TI-Toolbox.

This module provides a report generator for the preprocessing pipeline,
creating comprehensive HTML reports with processing steps, input/output
data, and quality control information.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.base import MetadataReportlet, TableReportlet, ImageReportlet
from ..core.protocols import StatusType
from ..reportlets.images import SliceSeriesReportlet, MultiViewBrainReportlet
from ..reportlets.metadata import (
    ProcessingStepReportlet,
    SummaryCardsReportlet,
    ParameterListReportlet,
)
from .base_generator import BaseReportGenerator


class PreprocessingReportGenerator(BaseReportGenerator):
    """
    Report generator for preprocessing pipelines.

    Creates comprehensive HTML reports including:
    - Input data summary
    - Processing steps with status
    - Output data summary
    - Software versions
    - Quality control visualizations
    - Methods boilerplate and references
    """

    def __init__(
        self,
        project_dir: Union[str, Path],
        subject_id: str,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the preprocessing report generator.

        Args:
            project_dir: Path to the project directory
            subject_id: BIDS subject ID
            session_id: Optional session identifier
        """
        super().__init__(
            project_dir=project_dir,
            subject_id=subject_id,
            session_id=session_id,
            report_type="preprocessing",
        )

        # Preprocessing-specific data
        self.input_data: Dict[str, Dict[str, Any]] = {}
        self.output_data: Dict[str, Dict[str, Any]] = {}
        self.processing_steps: List[Dict[str, Any]] = []
        self.qc_images: List[Dict[str, Any]] = []
        self.pipeline_config: Dict[str, Any] = {}

    def _get_default_title(self) -> str:
        return f"Preprocessing Report - Subject {self.subject_id}"

    def _get_report_prefix(self) -> str:
        return "pre_processing_report"

    def set_pipeline_config(self, **config) -> None:
        """
        Set the pipeline configuration.

        Args:
            **config: Pipeline configuration parameters
        """
        self.pipeline_config = config

    def add_input_data(
        self,
        data_type: str,
        file_paths: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add input data information.

        Args:
            data_type: Type of data (T1w, T2w, DWI, etc.)
            file_paths: List of input file paths
            metadata: Optional metadata about the data
        """
        self.input_data[data_type] = {
            "file_paths": file_paths,
            "metadata": metadata or {},
            "n_files": len(file_paths),
        }

    def add_output_data(
        self,
        data_type: str,
        file_paths: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add output data information.

        Args:
            data_type: Type of data (m2m, FreeSurfer, etc.)
            file_paths: List of output file paths
            metadata: Optional metadata about the data
        """
        self.output_data[data_type] = {
            "file_paths": file_paths,
            "metadata": metadata or {},
            "n_files": len(file_paths),
        }

    def add_processing_step(
        self,
        step_name: str,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        status: Union[StatusType, str] = StatusType.PENDING,
        duration: Optional[float] = None,
        output_files: Optional[List[str]] = None,
        figures: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Add a processing step.

        Args:
            step_name: Name of the processing step
            description: Step description
            parameters: Step parameters
            status: Step status
            duration: Duration in seconds
            output_files: Output file paths
            figures: QC figures
            error_message: Error message if failed
        """
        if isinstance(status, StatusType):
            status = status.value

        self.processing_steps.append(
            {
                "name": step_name,
                "description": description,
                "parameters": parameters or {},
                "status": status,
                "duration": duration,
                "output_files": output_files or [],
                "figures": figures or [],
                "error_message": error_message,
            }
        )

        # Track errors
        if status == "failed" and error_message:
            self.add_error(error_message, step=step_name)

    def add_qc_image(
        self,
        title: str,
        base64_data: str,
        step_name: Optional[str] = None,
        caption: Optional[str] = None,
        image_type: str = "qc",
    ) -> None:
        """
        Add a quality control image.

        Args:
            title: Image title
            base64_data: Base64-encoded image data
            step_name: Associated processing step
            caption: Image caption
            image_type: Type of QC image
        """
        self.qc_images.append(
            {
                "title": title,
                "base64_data": base64_data,
                "step_name": step_name,
                "caption": caption,
                "image_type": image_type,
            }
        )

    def scan_for_data(self) -> None:
        """
        Automatically scan directories for input and output data.

        Only scans for outputs that correspond to the processing steps
        that were added to this report.
        """
        # Determine which steps were run based on added processing steps
        step_names = {s["name"].lower() for s in self.processing_steps}

        # Input data - look for raw data
        rawdata_dir = self.project_dir / "rawdata" / f"sub-{self.subject_id}"
        if rawdata_dir.exists():
            # Look for anatomical data
            anat_dir = rawdata_dir / "anat"
            if anat_dir.exists():
                t1_files = list(anat_dir.glob("*T1w*.nii*"))
                if t1_files:
                    self.add_input_data("T1w", [str(f) for f in t1_files])

                t2_files = list(anat_dir.glob("*T2w*.nii*"))
                if t2_files:
                    self.add_input_data("T2w", [str(f) for f in t2_files])

            # Look for diffusion data (only if QSI steps were run)
            if any("qsi" in s or "dti" in s or "diffusion" in s for s in step_names):
                dwi_dir = rawdata_dir / "dwi"
                if dwi_dir.exists():
                    dwi_files = list(dwi_dir.glob("*.nii*"))
                    if dwi_files:
                        self.add_input_data("DWI", [str(f) for f in dwi_files])

        # Output data - look for derivatives based on steps that were run
        derivatives_dir = self.project_dir / "derivatives"

        # DICOM conversion outputs (NIfTI files)
        if any("dicom" in s for s in step_names):
            nifti_dir = self.project_dir / "rawdata" / f"sub-{self.subject_id}"
            if nifti_dir.exists():
                nifti_files = list(nifti_dir.rglob("*.nii*"))
                if nifti_files:
                    self.add_output_data("NIfTI (converted)", [str(nifti_dir)])

        # FreeSurfer outputs - only if recon step was run
        if any("freesurfer" in s or "recon" in s for s in step_names):
            fs_dir = derivatives_dir / "freesurfer" / f"sub-{self.subject_id}"
            if fs_dir.exists():
                self.add_output_data("FreeSurfer", [str(fs_dir)])

        # SimNIBS m2m outputs - only if charm/m2m step was run
        if any("simnibs" in s or "charm" in s or "m2m" in s for s in step_names):
            # Try multiple possible paths
            m2m_paths = [
                derivatives_dir
                / "SimNIBS"
                / f"sub-{self.subject_id}"
                / f"m2m_{self.subject_id}",
                derivatives_dir
                / "simnibs"
                / f"sub-{self.subject_id}"
                / f"m2m_{self.subject_id}",
                derivatives_dir / "simnibs" / f"m2m_sub-{self.subject_id}",
            ]
            for m2m_dir in m2m_paths:
                if m2m_dir.exists():
                    self.add_output_data("SimNIBS m2m", [str(m2m_dir)])
                    break

        # Tissue analysis outputs
        if any("tissue" in s for s in step_names):
            tissue_dir = derivatives_dir / "tissue_analysis" / f"sub-{self.subject_id}"
            if tissue_dir.exists():
                self.add_output_data("Tissue Analysis", [str(tissue_dir)])

        # QSIPrep outputs - only if qsiprep step was run
        if any("qsiprep" in s for s in step_names):
            qsiprep_dir = derivatives_dir / "qsiprep" / f"sub-{self.subject_id}"
            if qsiprep_dir.exists():
                self.add_output_data("QSIPrep", [str(qsiprep_dir)])

        # QSIRecon outputs - only if qsirecon step was run
        if any("qsirecon" in s for s in step_names):
            qsirecon_dir = derivatives_dir / "qsirecon" / f"sub-{self.subject_id}"
            if qsirecon_dir.exists():
                self.add_output_data("QSIRecon", [str(qsirecon_dir)])

        # DTI outputs - only if DTI step was run
        if any("dti" in s for s in step_names):
            dti_dir = derivatives_dir / "dti" / f"sub-{self.subject_id}"
            if dti_dir.exists():
                self.add_output_data("DTI Tensors", [str(dti_dir)])

    def _build_summary_section(self) -> None:
        """Build the summary section."""
        section = self.assembler.add_section(
            section_id="summary",
            title="Summary",
            order=0,
        )

        cards = SummaryCardsReportlet(columns=4)

        # Subject
        cards.add_card(
            label="Subject",
            value=self.subject_id,
        )

        # Processing steps
        completed = sum(
            1 for s in self.processing_steps if s.get("status") == "completed"
        )
        total = len(self.processing_steps)
        cards.add_card(
            label="Steps",
            value=f"{completed}/{total}",
            color="#28a745" if completed == total else "#ffc107",
        )

        # Input types
        cards.add_card(
            label="Input Types",
            value=len(self.input_data),
        )

        # Total duration
        total_duration = sum(s.get("duration", 0) or 0 for s in self.processing_steps)
        if total_duration > 3600:
            duration_str = f"{total_duration / 3600:.1f}h"
        elif total_duration > 60:
            duration_str = f"{total_duration / 60:.1f}m"
        elif total_duration > 0:
            duration_str = f"{total_duration:.0f}s"
        else:
            duration_str = "N/A"
        cards.add_card(
            label="Duration",
            value=duration_str,
        )

        section.add_reportlet(cards)

    def _build_input_section(self) -> None:
        """Build the input data section."""
        if not self.input_data:
            return

        section = self.assembler.add_section(
            section_id="input_data",
            title="Input Data",
            order=10,
        )

        input_rows = []
        for data_type, data_info in self.input_data.items():
            files = data_info.get("file_paths", [])
            input_rows.append(
                {
                    "Data Type": data_type,
                    "Files": len(files),
                    "Path": files[0] if files else "—",
                }
            )

        input_table = TableReportlet(
            data=input_rows,
            title="Input Files",
            striped=True,
        )
        section.add_reportlet(input_table)

    def _build_steps_section(self) -> None:
        """Build the processing steps section."""
        if not self.processing_steps:
            return

        section = self.assembler.add_section(
            section_id="processing_steps",
            title="Processing Steps",
            order=20,
        )

        steps_reportlet = ProcessingStepReportlet(title="Pipeline Execution")
        for step in self.processing_steps:
            steps_reportlet.add_step(
                name=step["name"],
                description=step.get("description"),
                status=step.get("status", "pending"),
                duration=step.get("duration"),
                parameters=step.get("parameters"),
                output_files=step.get("output_files"),
                error_message=step.get("error_message"),
            )

        section.add_reportlet(steps_reportlet)

    def _build_output_section(self) -> None:
        """Build the output data section."""
        if not self.output_data:
            return

        section = self.assembler.add_section(
            section_id="output_data",
            title="Output Data",
            order=30,
        )

        output_rows = []
        for data_type, data_info in self.output_data.items():
            files = data_info.get("file_paths", [])
            output_rows.append(
                {
                    "Data Type": data_type,
                    "Files/Dirs": len(files),
                    "Path": files[0] if files else "—",
                }
            )

        output_table = TableReportlet(
            data=output_rows,
            title="Output Directories",
            striped=True,
        )
        section.add_reportlet(output_table)

    def _build_qc_section(self) -> None:
        """Build the quality control section."""
        if not self.qc_images:
            return

        section = self.assembler.add_section(
            section_id="quality_control",
            title="Quality Control",
            order=40,
        )

        for qc_img in self.qc_images:
            img = ImageReportlet(
                title=qc_img.get("title", "QC Image"),
                caption=qc_img.get("caption"),
            )
            img.set_base64_data(qc_img["base64_data"])
            section.add_reportlet(img)

    def _build_software_section(self) -> None:
        """Build the software versions section."""
        section = self.assembler.add_section(
            section_id="software",
            title="Software Versions",
            order=80,
        )

        software_data = MetadataReportlet(
            data=self.software_versions,
            title="Software Environment",
            display_mode="table",
        )
        section.add_reportlet(software_data)

    def _get_methods_parameters(self) -> Dict[str, Any]:
        """Get parameters for methods boilerplate."""
        params = super()._get_methods_parameters()

        # Add software versions for methods text
        if "freesurfer" in self.software_versions:
            params["freesurfer_version"] = self.software_versions["freesurfer"]
        if "simnibs" in self.software_versions:
            params["simnibs_version"] = self.software_versions["simnibs"]
        if "qsiprep" in self.output_data or "qsiprep" in [
            s["name"].lower() for s in self.processing_steps
        ]:
            params["qsiprep_version"] = self.software_versions.get("qsiprep", "")

        return params

    def _build_report(self) -> None:
        """Build the complete preprocessing report."""
        self._build_summary_section()
        self._build_input_section()
        self._build_steps_section()
        self._build_output_section()
        self._build_qc_section()
        self._build_software_section()


def create_preprocessing_report(
    project_dir: Union[str, Path],
    subject_id: str,
    processing_steps: Optional[List[Dict[str, Any]]] = None,
    output_path: Optional[Union[str, Path]] = None,
    auto_scan: bool = True,
) -> Path:
    """
    Convenience function to create a preprocessing report.

    Args:
        project_dir: Path to project directory
        subject_id: BIDS subject ID
        processing_steps: List of processing step dictionaries
        output_path: Optional custom output path
        auto_scan: Whether to auto-scan for data

    Returns:
        Path to the generated report
    """
    generator = PreprocessingReportGenerator(
        project_dir=project_dir,
        subject_id=subject_id,
    )

    if auto_scan:
        generator.scan_for_data()

    if processing_steps:
        for step in processing_steps:
            generator.add_processing_step(**step)

    return generator.generate(output_path)
