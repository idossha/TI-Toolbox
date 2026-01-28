"""
Simulation report generator for TI-Toolbox.

This module provides a report generator for TI/mTI simulation pipelines,
creating comprehensive HTML reports with simulation parameters, results,
and visualizations.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.base import MetadataReportlet, TableReportlet, ImageReportlet
from ..core.protocols import StatusType
from ..reportlets.images import SliceSeriesReportlet, MontageImageReportlet
from ..reportlets.metadata import (
    ConductivityTableReportlet,
    SummaryCardsReportlet,
    ParameterListReportlet,
)
from .base_generator import BaseReportGenerator
from tit.core import get_path_manager


class SimulationReportGenerator(BaseReportGenerator):
    """
    Report generator for TI/mTI simulation pipelines.

    Creates comprehensive HTML reports including:
    - Simulation parameters and configuration
    - Electrode specifications
    - Conductivity values
    - Montage configurations
    - Simulation results with visualizations
    - Methods boilerplate and references
    """

    def __init__(
        self,
        project_dir: Union[str, Path],
        simulation_session_id: Optional[str] = None,
        subject_id: Optional[str] = None,
    ):
        """
        Initialize the simulation report generator.

        Args:
            project_dir: Path to the project directory
            simulation_session_id: Unique session identifier
            subject_id: BIDS subject ID (for single-subject reports)
        """
        super().__init__(
            project_dir=project_dir,
            subject_id=subject_id,
            session_id=simulation_session_id,
            report_type="simulation",
        )

        # Simulation-specific data
        self.simulation_parameters: Dict[str, Any] = {}
        self.electrode_parameters: Dict[str, Any] = {}
        self.conductivities: Dict[str, Dict[str, Any]] = {}
        self.subjects: List[Dict[str, Any]] = []
        self.montages: List[Dict[str, Any]] = []
        self.simulation_results: Dict[str, Dict[str, Any]] = {}
        self.visualizations: List[Dict[str, Any]] = []

    def _get_default_title(self) -> str:
        if self.subject_id:
            return f"TI Simulation Report - Subject {self.subject_id}"
        return "TI Simulation Report"

    def _get_report_prefix(self) -> str:
        return "simulation_report"

    def add_simulation_parameters(
        self,
        conductivity_type: str = "scalar",
        simulation_mode: str = "TI",
        eeg_net: Optional[str] = None,
        intensity_ch1: float = 1.0,
        intensity_ch2: float = 1.0,
        quiet_mode: bool = False,
        conductivities: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        """
        Add simulation configuration parameters.

        Args:
            conductivity_type: Type of conductivity (scalar, anisotropic)
            simulation_mode: Simulation mode (TI, mTI)
            eeg_net: EEG electrode net used
            intensity_ch1: Channel 1 intensity (mA)
            intensity_ch2: Channel 2 intensity (mA)
            quiet_mode: Whether running in quiet mode
            conductivities: Optional custom conductivity values
            **kwargs: Additional parameters
        """
        self.simulation_parameters = {
            "conductivity_type": conductivity_type,
            "simulation_mode": simulation_mode,
            "eeg_net": eeg_net,
            "intensity_ch1": intensity_ch1,
            "intensity_ch2": intensity_ch2,
            "quiet_mode": quiet_mode,
            **kwargs,
        }
        if conductivities:
            self.add_conductivities(conductivities, conductivity_type)

    def add_electrode_parameters(
        self,
        shape: str = "circular",
        dimensions: Optional[Union[str, List[float]]] = None,
        thickness: Optional[float] = None,
        **kwargs,
    ) -> None:
        """
        Add electrode specifications.

        Args:
            shape: Electrode shape (circular, rectangular)
            dimensions: Electrode dimensions (string or list)
            thickness: Electrode thickness (mm)
            **kwargs: Additional parameters
        """
        # Convert list dimensions to string
        if isinstance(dimensions, list):
            dimensions = f"{dimensions[0]}x{dimensions[1]} mm"

        self.electrode_parameters = {
            "shape": shape,
            "dimensions": dimensions,
            "thickness": thickness,
            **kwargs,
        }

    def add_conductivities(
        self,
        conductivities: Dict[str, Dict[str, Any]],
        conductivity_type: str = "scalar",
    ) -> None:
        """
        Add tissue conductivity values.

        Args:
            conductivities: Dict mapping tissue names to conductivity info
            conductivity_type: Type of conductivity values
        """
        self.conductivities = conductivities
        self.simulation_parameters["conductivity_type"] = conductivity_type

    def add_subject(
        self,
        subject_id: str,
        m2m_path: Optional[str] = None,
        status: str = "pending",
    ) -> None:
        """
        Add a subject to the simulation.

        Args:
            subject_id: BIDS subject ID
            m2m_path: Path to the m2m folder
            status: Subject processing status
        """
        self.subjects.append(
            {
                "subject_id": subject_id,
                "m2m_path": m2m_path,
                "status": status,
            }
        )

    def add_montage(
        self,
        montage_name: str,
        electrode_pairs: List[Any],
        montage_type: str = "TI",
    ) -> None:
        """
        Add a montage configuration.

        Args:
            montage_name: Name of the montage
            electrode_pairs: List of electrode pair specifications
            montage_type: Type of montage (TI, mTI, unipolar, multipolar)
        """
        self.montages.append(
            {
                "name": montage_name,
                "electrode_pairs": self._normalize_electrode_pairs(electrode_pairs),
                "type": montage_type,
            }
        )

    def _normalize_electrode_pairs(
        self,
        electrode_pairs: Optional[List[Any]],
    ) -> List[Dict[str, Any]]:
        """Normalize electrode pairs into dicts for reportlets."""
        if not electrode_pairs:
            return []

        normalized: List[Dict[str, Any]] = []
        for idx, pair in enumerate(electrode_pairs, start=1):
            name = f"Pair {idx}"
            electrode1: Optional[str] = None
            electrode2: Optional[str] = None
            intensity: Optional[Any] = None

            if isinstance(pair, dict):
                name = pair.get("name", name)
                electrode1 = (
                    pair.get("electrode1")
                    or pair.get("electrode_1")
                    or pair.get("e1")
                    or pair.get("anode")
                )
                electrode2 = (
                    pair.get("electrode2")
                    or pair.get("electrode_2")
                    or pair.get("e2")
                    or pair.get("cathode")
                )
                intensity = (
                    pair.get("intensity")
                    if pair.get("intensity") is not None
                    else (
                        pair.get("current")
                        if pair.get("current") is not None
                        else pair.get("value")
                    )
                )

                pair_list = (
                    pair.get("pair")
                    or pair.get("electrodes")
                    or pair.get("electrode_pair")
                )
                if (not electrode1 or not electrode2) and isinstance(
                    pair_list, (list, tuple)
                ):
                    if len(pair_list) >= 2:
                        electrode1 = pair_list[0]
                        electrode2 = pair_list[1]
                    if intensity is None and len(pair_list) >= 3:
                        intensity = pair_list[2]

            elif isinstance(pair, (list, tuple)) and len(pair) >= 2:
                electrode1 = pair[0]
                electrode2 = pair[1]
                if len(pair) >= 3:
                    intensity = pair[2]
            else:
                electrode1 = str(pair)

            normalized.append(
                {
                    "name": name,
                    "electrode1": "" if electrode1 is None else str(electrode1),
                    "electrode2": "" if electrode2 is None else str(electrode2),
                    "intensity": intensity,
                }
            )

        self._apply_default_intensities(normalized)
        return normalized

    def _apply_default_intensities(self, pairs: List[Dict[str, Any]]) -> None:
        """Fill missing intensities using simulation parameters."""
        defaults = self._get_default_intensities()
        if not defaults:
            return

        for idx, pair in enumerate(pairs):
            if idx >= len(defaults):
                break
            if pair.get("intensity") is None or pair.get("intensity") == "":
                if defaults[idx] is not None:
                    pair["intensity"] = defaults[idx]

    def _get_default_intensities(self) -> List[Optional[float]]:
        """Return default pair intensities in pair order."""
        if isinstance(self.simulation_parameters.get("intensities"), (list, tuple)):
            return list(self.simulation_parameters["intensities"])

        keys = ["intensity_ch1", "intensity_ch2", "intensity_ch3", "intensity_ch4"]
        if any(key in self.simulation_parameters for key in keys):
            return [self.simulation_parameters.get(key) for key in keys]
        return []

    @staticmethod
    def _is_multipolar(montage_type: Optional[str]) -> bool:
        if not montage_type:
            return False
        normalized = str(montage_type).strip().lower()
        return normalized in {"m", "mti", "multipolar", "mt", "multi"}

    def _get_montage_subject_id(self) -> Optional[str]:
        if self.subject_id:
            return self.subject_id
        if self.subjects:
            return self.subjects[0].get("subject_id")
        return None

    def _find_montage_image(
        self, montage_name: str, montage_type: Optional[str]
    ) -> Optional[Path]:
        subject_id = self._get_montage_subject_id()
        if not subject_id:
            return None

        pm = get_path_manager()
        pm.project_dir = str(self.project_dir)
        montage_dir = Path(
            pm.path("simulation", subject_id=subject_id, simulation_name=montage_name)
        )

        preferred_subdir = "mTI" if self._is_multipolar(montage_type) else "TI"
        candidate_dirs = [
            montage_dir / preferred_subdir / "montage_imgs",
            montage_dir / "TI" / "montage_imgs",
            montage_dir / "mTI" / "montage_imgs",
        ]

        candidate_names = (
            [
                "combined_montage_visualization.png",
                f"{montage_name}_highlighted_visualization.png",
            ]
            if self._is_multipolar(montage_type)
            else [
                f"{montage_name}_highlighted_visualization.png",
                "combined_montage_visualization.png",
            ]
        )

        for directory in candidate_dirs:
            if not directory.exists():
                continue
            for name in candidate_names:
                path = directory / name
                if path.exists():
                    return path
            for fallback in sorted(directory.glob("*.png")):
                return fallback
        return None

    def add_simulation_result(
        self,
        subject_id: str,
        montage_name: str,
        output_files: Optional[List[str]] = None,
        duration: Optional[float] = None,
        status: str = "completed",
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add simulation results for a subject/montage combination.

        Args:
            subject_id: Subject ID
            montage_name: Montage name
            output_files: List of output file paths
            duration: Simulation duration in seconds
            status: Simulation status
            metrics: Optional computed metrics
        """
        key = f"{subject_id}_{montage_name}"
        self.simulation_results[key] = {
            "subject_id": subject_id,
            "montage_name": montage_name,
            "output_files": output_files or [],
            "duration": duration,
            "status": status,
            "metrics": metrics or {},
        }

    def add_visualization(
        self,
        subject_id: str,
        montage_name: str,
        image_type: str,
        base64_data: str,
        title: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> None:
        """
        Add a visualization image.

        Args:
            subject_id: Subject ID
            montage_name: Montage name
            image_type: Type of visualization
            base64_data: Base64-encoded image data
            title: Image title
            caption: Image caption
        """
        self.visualizations.append(
            {
                "subject_id": subject_id,
                "montage_name": montage_name,
                "image_type": image_type,
                "base64_data": base64_data,
                "title": title,
                "caption": caption,
            }
        )

    def _build_summary_section(self) -> None:
        """Build the summary section."""
        section = self.assembler.add_section(
            section_id="summary",
            title="Summary",
            order=0,
        )

        # Summary cards
        cards = SummaryCardsReportlet(columns=4)

        cards.add_card(
            label="Subjects",
            value=len(self.subjects),
        )

        cards.add_card(
            label="Montages",
            value=len(self.montages),
        )

        completed = sum(
            1
            for r in self.simulation_results.values()
            if r.get("status") == "completed"
        )
        cards.add_card(
            label="Completed",
            value=f"{completed}/{len(self.simulation_results)}",
            color="#28a745" if completed == len(self.simulation_results) else "#ffc107",
        )

        mode = self.simulation_parameters.get("simulation_mode", "TI")
        cards.add_card(
            label="Mode",
            value=mode,
        )

        section.add_reportlet(cards)

    def _build_parameters_section(self) -> None:
        """Build the parameters section."""
        section = self.assembler.add_section(
            section_id="parameters",
            title="Simulation Parameters",
            order=10,
        )

        # Group parameters by category
        param_list = ParameterListReportlet(title="Configuration")

        # Simulation parameters
        sim_params = {
            k: v for k, v in self.simulation_parameters.items() if v is not None
        }
        if sim_params:
            param_list.add_category("Simulation", sim_params)

        # Electrode parameters
        elec_params = {
            k: v for k, v in self.electrode_parameters.items() if v is not None
        }
        if elec_params:
            param_list.add_category("Electrodes", elec_params)

        section.add_reportlet(param_list)

    def _build_conductivities_section(self) -> None:
        """Build the conductivities section."""
        if not self.conductivities:
            return

        section = self.assembler.add_section(
            section_id="conductivities",
            title="Tissue Conductivities",
            order=20,
        )

        cond_table = ConductivityTableReportlet(
            conductivities=self.conductivities,
            conductivity_type=self.simulation_parameters.get(
                "conductivity_type", "scalar"
            ),
        )
        section.add_reportlet(cond_table)

    def _build_montages_section(self) -> None:
        """Build the montages section."""
        if not self.montages:
            return

        section = self.assembler.add_section(
            section_id="montages",
            title="Electrode Montages",
            order=30,
        )

        for montage in self.montages:
            montage_image_path = self._find_montage_image(
                montage_name=montage["name"],
                montage_type=montage.get("type"),
            )
            montage_reportlet = MontageImageReportlet(
                title=montage["name"],
                montage_name=montage["name"],
                electrode_pairs=montage.get("electrode_pairs", []),
                image_source=montage_image_path,
            )

            # Find visualization for this montage
            for viz in self.visualizations:
                if (
                    viz.get("montage_name") == montage["name"]
                    and viz.get("image_type") == "montage"
                ):
                    montage_reportlet.set_base64_data(viz["base64_data"])
                    break

            section.add_reportlet(montage_reportlet)

    def _build_results_section(self) -> None:
        """Build the results section."""
        if not self.simulation_results:
            return

        section = self.assembler.add_section(
            section_id="results",
            title="Simulation Results",
            order=40,
        )

        # Results table
        results_data = []
        for result in self.simulation_results.values():
            duration_str = (
                f"{result['duration']:.1f}s" if result.get("duration") else "—"
            )
            results_data.append(
                {
                    "Subject": result["subject_id"],
                    "Montage": result["montage_name"],
                    "Status": result["status"],
                    "Duration": duration_str,
                }
            )

        if results_data:
            results_table = TableReportlet(
                data=results_data,
                title="Results Summary",
                striped=True,
            )
            section.add_reportlet(results_table)

    def _build_visualizations_section(self) -> None:
        """Build the visualizations section."""
        # Filter to non-montage visualizations
        viz_list = [v for v in self.visualizations if v.get("image_type") != "montage"]

        if not viz_list:
            return

        section = self.assembler.add_section(
            section_id="visualizations",
            title="Visualizations",
            order=50,
        )

        for viz in viz_list:
            img = ImageReportlet(
                title=viz.get("title", "Visualization"),
                caption=viz.get("caption"),
            )
            img.set_base64_data(viz["base64_data"])
            section.add_reportlet(img)

    def _build_subjects_section(self) -> None:
        """Build the subjects section."""
        if not self.subjects:
            return

        section = self.assembler.add_section(
            section_id="subjects",
            title="Subjects",
            order=5,
        )

        subjects_data = []
        for subj in self.subjects:
            subjects_data.append(
                {
                    "Subject ID": subj["subject_id"],
                    "M2M Path": subj.get("m2m_path", "—"),
                    "Status": subj.get("status", "pending"),
                }
            )

        if subjects_data:
            subjects_table = TableReportlet(
                data=subjects_data,
                title="Subject Information",
                striped=True,
            )
            section.add_reportlet(subjects_table)

    def _get_methods_parameters(self) -> Dict[str, Any]:
        """Get parameters for methods boilerplate."""
        params = super()._get_methods_parameters()
        params.update(
            {
                "conductivity_type": self.simulation_parameters.get(
                    "conductivity_type"
                ),
                "electrode_shape": self.electrode_parameters.get("shape"),
                "electrode_size": self.electrode_parameters.get("dimensions"),
                "intensity": self.simulation_parameters.get("intensity_ch1"),
            }
        )
        return params

    def _build_report(self) -> None:
        """Build the complete simulation report."""
        self._build_summary_section()
        self._build_subjects_section()
        self._build_parameters_section()
        self._build_conductivities_section()
        self._build_montages_section()
        self._build_results_section()
        self._build_visualizations_section()
