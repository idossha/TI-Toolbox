"""
Flex-search optimization report generator for TI-Toolbox.

This module provides a report generator for electrode placement
optimization results from the flex-search algorithm.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.base import MetadataReportlet, TableReportlet, ImageReportlet
from ..reportlets.images import MontageImageReportlet
from ..reportlets.metadata import SummaryCardsReportlet, ParameterListReportlet
from .base_generator import BaseReportGenerator


class FlexSearchReportGenerator(BaseReportGenerator):
    """
    Report generator for flex-search optimization results.

    Creates comprehensive HTML reports including:
    - Optimization configuration
    - Target ROI specification
    - Search results and rankings
    - Best solution details
    - Visualization of optimal electrode placement
    """

    def __init__(
        self,
        project_dir: Union[str, Path],
        subject_id: str,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the flex-search report generator.

        Args:
            project_dir: Path to the project directory
            subject_id: BIDS subject ID
            session_id: Optional session identifier
        """
        super().__init__(
            project_dir=project_dir,
            subject_id=subject_id,
            session_id=session_id,
            report_type="flex-search",
        )

        # Flex-search specific data
        self.config: Dict[str, Any] = {}
        self.roi_info: Dict[str, Any] = {}
        self.search_results: List[Dict[str, Any]] = []
        self.best_solution: Optional[Dict[str, Any]] = None
        self.optimization_metrics: Dict[str, Any] = {}

    def _get_default_title(self) -> str:
        return f"Flex-Search Optimization Report - Subject {self.subject_id}"

    def _get_report_prefix(self) -> str:
        return "flex_search_report"

    def set_configuration(
        self,
        electrode_net: Optional[str] = None,
        optimization_target: Optional[str] = None,
        n_candidates: int = 100,
        selection_method: str = "best",
        intensity_ch1: float = 1.0,
        intensity_ch2: float = 1.0,
        **kwargs,
    ) -> None:
        """
        Set the optimization configuration.

        Args:
            electrode_net: EEG net used
            optimization_target: Target metric to optimize
            n_candidates: Number of candidate solutions evaluated
            selection_method: Method for selecting best solution
            intensity_ch1: Channel 1 intensity
            intensity_ch2: Channel 2 intensity
            **kwargs: Additional configuration
        """
        self.config = {
            "electrode_net": electrode_net,
            "optimization_target": optimization_target,
            "n_candidates": n_candidates,
            "selection_method": selection_method,
            "intensity_ch1": intensity_ch1,
            "intensity_ch2": intensity_ch2,
            **kwargs,
        }

    def set_roi_info(
        self,
        roi_name: str,
        roi_type: str = "mask",
        coordinates: Optional[List[float]] = None,
        radius: Optional[float] = None,
        volume_mm3: Optional[float] = None,
        n_voxels: Optional[int] = None,
        **kwargs,
    ) -> None:
        """
        Set the target ROI information.

        Args:
            roi_name: Name of the target ROI
            roi_type: Type of ROI (mask, sphere, coordinates)
            coordinates: Center coordinates (if applicable)
            radius: Radius in mm (if sphere)
            volume_mm3: ROI volume in mm³
            n_voxels: Number of voxels in ROI
            **kwargs: Additional ROI info
        """
        self.roi_info = {
            "name": roi_name,
            "type": roi_type,
            "coordinates": coordinates,
            "radius": radius,
            "volume_mm3": volume_mm3,
            "n_voxels": n_voxels,
            **kwargs,
        }

    def add_search_result(
        self,
        rank: int,
        electrode_1a: str,
        electrode_1b: str,
        electrode_2a: str,
        electrode_2b: str,
        score: float,
        mean_field_roi: Optional[float] = None,
        max_field_roi: Optional[float] = None,
        focality: Optional[float] = None,
        **metrics,
    ) -> None:
        """
        Add a search result entry.

        Args:
            rank: Ranking of this solution
            electrode_1a: First electrode of pair 1
            electrode_1b: Second electrode of pair 1
            electrode_2a: First electrode of pair 2
            electrode_2b: Second electrode of pair 2
            score: Optimization score
            mean_field_roi: Mean field in ROI (V/m)
            max_field_roi: Max field in ROI (V/m)
            focality: Focality metric
            **metrics: Additional metrics
        """
        self.search_results.append({
            "rank": rank,
            "electrode_1a": electrode_1a,
            "electrode_1b": electrode_1b,
            "electrode_2a": electrode_2a,
            "electrode_2b": electrode_2b,
            "pair_1": f"{electrode_1a}-{electrode_1b}",
            "pair_2": f"{electrode_2a}-{electrode_2b}",
            "score": score,
            "mean_field_roi": mean_field_roi,
            "max_field_roi": max_field_roi,
            "focality": focality,
            **metrics,
        })

    def set_best_solution(
        self,
        electrode_pairs: List[Dict[str, str]],
        score: float,
        metrics: Dict[str, Any],
        montage_image_base64: Optional[str] = None,
        field_map_base64: Optional[str] = None,
        electrode_coordinates: Optional[List[List[float]]] = None,
        channel_array_indices: Optional[List[List[int]]] = None,
    ) -> None:
        """
        Set the best (selected) solution.

        Args:
            electrode_pairs: List of electrode pair specs
            score: Final optimization score
            metrics: Solution metrics
            montage_image_base64: Base64 montage visualization
            field_map_base64: Base64 field map visualization
        """
        self.best_solution = {
            "electrode_pairs": electrode_pairs,
            "score": score,
            "metrics": metrics,
            "montage_image_base64": montage_image_base64,
            "field_map_base64": field_map_base64,
            "electrode_coordinates": electrode_coordinates,
            "channel_array_indices": channel_array_indices,
        }

    def populate_from_data(self, data: Dict[str, Any]) -> None:
        """
        Populate the report from a data dictionary.

        Args:
            data: Dictionary containing all optimization data
        """
        # Configuration
        if "config" in data:
            self.config = data["config"]

        # ROI info
        if "roi" in data:
            self.roi_info = data["roi"]

        # Search results
        if "results" in data:
            for i, result in enumerate(data["results"]):
                self.add_search_result(rank=i + 1, **result)

        # Best solution
        if "best_solution" in data:
            self.best_solution = data["best_solution"]

        # Optimization metrics
        if "metrics" in data:
            self.optimization_metrics = data["metrics"]

    def load_from_output_dir(self, output_dir: Union[str, Path]) -> None:
        """
        Load optimization data from an output directory.

        Args:
            output_dir: Path to the flex-search output directory
        """
        output_dir = Path(output_dir)

        # Try to load results JSON
        results_file = output_dir / "optimization_results.json"
        if results_file.exists():
            with open(results_file) as f:
                data = json.load(f)
                self.populate_from_data(data)

        # Try to load configuration
        config_file = output_dir / "config.json"
        if config_file.exists():
            with open(config_file) as f:
                self.config = json.load(f)

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

        # Target ROI
        roi_name = self.roi_info.get("name", "Unknown")
        cards.add_card(
            label="Target ROI",
            value=roi_name,
        )

        # Goal
        goal = self.config.get("optimization_goal") or self.config.get("optimization_target")
        if goal:
            cards.add_card(
                label="Goal",
                value=goal,
            )

        # Post-processing
        postproc = self.config.get("post_processing") or self.config.get("postproc")
        if postproc:
            cards.add_card(
                label="Post-processing",
                value=postproc,
            )

        # Candidates evaluated
        n_candidates = self.config.get("n_candidates", len(self.search_results))
        cards.add_card(
            label="Candidates",
            value=n_candidates,
        )

        # Starts
        n_starts = self.config.get("n_starts")
        if n_starts is not None:
            cards.add_card(
                label="Starts",
                value=n_starts,
            )

        # Best score
        if self.best_solution:
            score = self.best_solution.get("score", 0)
            cards.add_card(
                label="Best Score",
                value=f"{score:.4f}",
                color="#28a745",
            )

        section.add_reportlet(cards)

    def _build_config_section(self) -> None:
        """Build the configuration section."""
        if not self.config:
            return

        section = self.assembler.add_section(
            section_id="configuration",
            title="Configuration",
            order=10,
        )

        param_list = ParameterListReportlet(title="Optimization Settings")

        # Group config parameters
        main_params = {
            "electrode_net": self.config.get("electrode_net"),
            "optimization_goal": self.config.get("optimization_goal"),
            "optimization_target": self.config.get("optimization_target"),
            "post_processing": self.config.get("post_processing") or self.config.get("postproc"),
            "n_starts": self.config.get("n_starts"),
            "selection_method": self.config.get("selection_method"),
            "n_candidates": self.config.get("n_candidates"),
        }
        param_list.add_category("Optimization", {k: v for k, v in main_params.items() if v is not None})

        electrode_params = {
            "electrode_shape": self.config.get("electrode_shape"),
            "electrode_dimensions_mm": self.config.get("electrode_dimensions_mm"),
            "electrode_thickness_mm": self.config.get("electrode_thickness_mm"),
            "electrode_current_mA": self.config.get("electrode_current_mA"),
            "channel_1_intensity": self.config.get("intensity_ch1"),
            "channel_2_intensity": self.config.get("intensity_ch2"),
            "electrode_net": self.config.get("electrode_net"),
            "mapping_enabled": self.config.get("mapping_enabled"),
            "run_final_simulation": self.config.get("run_final_electrode_simulation"),
        }
        param_list.add_category("Electrodes", {k: v for k, v in electrode_params.items() if v is not None})

        algorithm_params = {
            "max_iterations": self.config.get("max_iterations"),
            "population_size": self.config.get("population_size"),
            "tolerance": self.config.get("tolerance"),
            "mutation": self.config.get("mutation"),
            "recombination": self.config.get("recombination"),
            "thresholds": self.config.get("thresholds"),
            "non_roi_method": self.config.get("non_roi_method"),
            "cpu_cores": self.config.get("cpu_cores"),
        }
        param_list.add_category("Algorithm", {k: v for k, v in algorithm_params.items() if v is not None})

        output_params = {
            "detailed_results": self.config.get("detailed_results"),
            "visualize_valid_skin_region": self.config.get("visualize_valid_skin_region"),
            "skin_visualization_net": self.config.get("skin_visualization_net"),
            "disable_mapping_simulation": self.config.get("disable_mapping_simulation"),
        }
        param_list.add_category("Output", {k: v for k, v in output_params.items() if v is not None})

        section.add_reportlet(param_list)

    def _build_roi_section(self) -> None:
        """Build the ROI information section."""
        if not self.roi_info:
            return

        section = self.assembler.add_section(
            section_id="roi",
            title="Target Region of Interest",
            order=20,
        )

        roi_data = {
            "name": self.roi_info.get("name", "Unknown"),
            "target_approach": self.roi_info.get("type", "mask"),
        }

        coordinates = self.roi_info.get("coordinates")
        if coordinates:
            roi_data["coordinates"] = coordinates
        if self.roi_info.get("coordinate_space"):
            roi_data["coordinate_space"] = self.roi_info.get("coordinate_space")
        if self.roi_info.get("radius"):
            roi_data["radius_mm"] = self.roi_info["radius"]
        if self.roi_info.get("hemisphere"):
            roi_data["hemisphere"] = self.roi_info.get("hemisphere")
        if self.roi_info.get("atlas"):
            roi_data["atlas"] = self.roi_info.get("atlas")
        if self.roi_info.get("atlas_label") is not None:
            roi_data["atlas_label"] = self.roi_info.get("atlas_label")
        if self.roi_info.get("volume_atlas"):
            roi_data["volume_atlas"] = self.roi_info.get("volume_atlas")
        if self.roi_info.get("volume_label") is not None:
            roi_data["volume_label"] = self.roi_info.get("volume_label")
        if self.roi_info.get("volume_mm3"):
            roi_data["volume_mm3"] = f"{self.roi_info['volume_mm3']:.1f}"
        if self.roi_info.get("n_voxels"):
            roi_data["n_voxels"] = self.roi_info["n_voxels"]
        if self.roi_info.get("non_roi_method"):
            roi_data["non_roi_method"] = self.roi_info.get("non_roi_method")
        if self.roi_info.get("non_roi_coordinates"):
            roi_data["non_roi_coordinates"] = self.roi_info.get("non_roi_coordinates")
        if self.roi_info.get("non_roi_radius"):
            roi_data["non_roi_radius_mm"] = self.roi_info.get("non_roi_radius")
        if self.roi_info.get("non_roi_coordinate_space"):
            roi_data["non_roi_coordinate_space"] = self.roi_info.get("non_roi_coordinate_space")
        if self.roi_info.get("non_roi_atlas"):
            roi_data["non_roi_atlas"] = self.roi_info.get("non_roi_atlas")
        if self.roi_info.get("non_roi_label") is not None:
            roi_data["non_roi_label"] = self.roi_info.get("non_roi_label")

        roi_metadata = MetadataReportlet(
            data=roi_data,
            title="ROI Specification",
            display_mode="table",
        )
        section.add_reportlet(roi_metadata)

    def _build_results_section(self) -> None:
        """Build the results table section."""
        if not self.search_results:
            return

        section = self.assembler.add_section(
            section_id="results",
            title="Search Results",
            description=f"Top {min(20, len(self.search_results))} electrode configurations ranked by optimization score.",
            order=30,
        )

        # Prepare table data (top 20)
        table_data = []
        for result in sorted(self.search_results, key=lambda x: x["rank"])[:20]:
            row = {
                "Rank": result["rank"],
                "Score": f"{result['score']:.4f}",
            }
            if result.get("pair_1"):
                row["Pair 1"] = result.get("pair_1", "")
            if result.get("pair_2"):
                row["Pair 2"] = result.get("pair_2", "")
            if result.get("mean_field_roi") is not None:
                row["Mean Field (V/m)"] = f"{result['mean_field_roi']:.4f}"
            if result.get("focality") is not None:
                row["Focality"] = f"{result['focality']:.4f}"
            table_data.append(row)

        results_table = TableReportlet(
            data=table_data,
            title="Ranked Configurations",
            striped=True,
        )
        section.add_reportlet(results_table)

    def _build_best_solution_section(self) -> None:
        """Build the best solution section."""
        if not self.best_solution:
            return

        section = self.assembler.add_section(
            section_id="best_solution",
            title="Optimal Solution",
            order=40,
        )

        # Solution summary
        pairs = self.best_solution.get("electrode_pairs", [])
        pair_strings = []
        for pair in pairs:
            if isinstance(pair, dict):
                pair_strings.append(f"{pair.get('electrode1', '?')}-{pair.get('electrode2', '?')}")
            else:
                pair_strings.append(str(pair))

        solution_data = {
            "optimization_score": f"{self.best_solution.get('score', 0):.4f}",
        }
        if pair_strings:
            solution_data["electrode_configuration"] = " | ".join(pair_strings)

        # Add metrics
        metrics = self.best_solution.get("metrics", {})
        for key, value in metrics.items():
            if isinstance(value, float):
                solution_data[key] = f"{value:.4f}"
            else:
                solution_data[key] = value

        solution_metadata = MetadataReportlet(
            data=solution_data,
            title="Selected Configuration",
            display_mode="cards",
            columns=3,
        )
        section.add_reportlet(solution_metadata)

        # Electrode coordinates (preferred over names)
        electrode_coords = self.best_solution.get("electrode_coordinates")
        if electrode_coords:
            indices = self.best_solution.get("channel_array_indices") or []
            coord_rows = []
            for idx, coords in enumerate(electrode_coords):
                row = {"Electrode": idx + 1}
                if isinstance(coords, (list, tuple)) and len(coords) >= 3:
                    row["X"] = f"{coords[0]:.2f}"
                    row["Y"] = f"{coords[1]:.2f}"
                    row["Z"] = f"{coords[2]:.2f}"
                else:
                    row["Coordinates"] = str(coords)
                if idx < len(indices):
                    row["Channel"] = indices[idx][0]
                    row["Array"] = indices[idx][1]
                coord_rows.append(row)

            coord_table = TableReportlet(
                data=coord_rows,
                title="Electrode Coordinates (Subject Space)",
                striped=True,
            )
            section.add_reportlet(coord_table)

        # Montage visualization
        if self.best_solution.get("montage_image_base64"):
            montage_img = ImageReportlet(
                title="Electrode Montage",
                caption="Optimal electrode placement",
            )
            montage_img.set_base64_data(self.best_solution["montage_image_base64"])
            section.add_reportlet(montage_img)

        # Field map visualization
        if self.best_solution.get("field_map_base64"):
            field_img = ImageReportlet(
                title="Electric Field Distribution",
                caption="TI modulation envelope in target region",
            )
            field_img.set_base64_data(self.best_solution["field_map_base64"])
            section.add_reportlet(field_img)

    def _get_methods_parameters(self) -> Dict[str, Any]:
        """Get parameters for methods boilerplate."""
        params = super()._get_methods_parameters()
        params.update({
            "optimization_method": "flex-search",
            "target_region": self.roi_info.get("name"),
            "n_candidates": self.config.get("n_candidates"),
        })
        return params

    def _build_report(self) -> None:
        """Build the complete flex-search report."""
        self._build_summary_section()
        self._build_config_section()
        self._build_roi_section()
        self._build_results_section()
        self._build_best_solution_section()


def create_flex_search_report(
    project_dir: Union[str, Path],
    subject_id: str,
    data: Dict[str, Any],
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Convenience function to create a flex-search report.

    Args:
        project_dir: Path to project directory
        subject_id: BIDS subject ID
        data: Dictionary containing optimization data
        output_path: Optional custom output path

    Returns:
        Path to the generated report
    """
    generator = FlexSearchReportGenerator(
        project_dir=project_dir,
        subject_id=subject_id,
    )
    generator.populate_from_data(data)
    return generator.generate(output_path)
