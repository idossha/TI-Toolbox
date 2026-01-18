#!/usr/bin/env simnibs_python
"""
TI-Toolbox Visualization Module
Provides comprehensive visualization tools for electric field distributions from TES simulations.

Features:
1. Multiple surface views (lateral, medial, left/right hemispheres) saved as high-res PDF
2. Interactive 3D visualization saved as HTML using plotly
3. Atlas contour overlays for anatomical context
4. Support for both subject-specific and MNI space visualizations

Based on: https://nilearn.github.io/dev/auto_examples/01_plotting/plot_3d_map_to_surface_projection.html
"""

import os
import sys
import argparse
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
from nilearn import datasets, plotting, image
from nilearn.plotting import plot_img_on_surf, view_img_on_surf
from nilearn.image import threshold_img
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import warnings

from tit.core import get_path_manager
from tit.core.constants import DIR_NILEARN_VISUALS

warnings.filterwarnings("ignore")


class NilearnVisualizer:
    """
    Main visualization class for electric field distributions.

    Provides methods for creating both static PDF visualizations and interactive HTML plots.
    Uses PathManager for consistent path handling and supports multiple atlas overlays.
    """

    def __init__(self, subject_id: Optional[str] = None):
        """
        Initialize the visualizer.

        Args:
            subject_id: Subject ID (optional, will use PathManager detection if not provided)
        """
        self.pm = get_path_manager()
        self.subject_id = subject_id
        self.output_dir = None

        # Set up output directory
        self._setup_output_directory()

    def _setup_output_directory(self):
        """Set up the output directory for visualizations."""
        derivatives_dir = self.pm.path("derivatives")
        self.output_dir = os.path.join(
            derivatives_dir, "ti-toolbox", DIR_NILEARN_VISUALS
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_simulation_files(self, subject_id: str) -> Dict[str, str]:
        """
        Get simulation files for a subject using PathManager.

        Args:
            subject_id: Subject ID

        Returns:
            Dictionary mapping simulation names to their TI max files
        """
        simulations = self.pm.list_simulations(subject_id)
        sim_files = {}

        for sim_name in simulations:
            sim_dir = self.pm.path_optional(
                "simulation", subject_id=subject_id, simulation_name=sim_name
            )
            if sim_dir:
                # Look for TI max files in the niftis directory
                nifti_dir = os.path.join(sim_dir, "TI", "niftis")
                if os.path.exists(nifti_dir):
                    for file in os.listdir(nifti_dir):
                        if file.endswith(".nii.gz") and "TI_max" in file:
                            sim_files[sim_name] = os.path.join(nifti_dir, file)
                            break

        return sim_files

    def _load_electric_field_data(self, filepath: str) -> Optional[nib.Nifti1Image]:
        """
        Load electric field NIfTI data.

        Args:
            filepath: Path to NIfTI file

        Returns:
            Loaded NIfTI image or None if file not found
        """
        if os.path.exists(filepath):
            return nib.load(filepath)
        else:
            print(f"Warning: {filepath} not found")
            return None

    def create_pdf_visualization(
        self,
        subject_id: str,
        simulation_name: str,
        min_cutoff: float = 0.3,
        max_cutoff: float = None,
        atlas_name: str = "harvard_oxford_sub",
        selected_regions: Optional[List[int]] = None,
    ) -> Optional[str]:
        """
        Create PDF visualization with multiple surface views and atlas contours.

        Args:
            subject_id: Subject ID
            simulation_name: Name of the simulation
            min_cutoff: Minimum cutoff for visualization (V/m)
            max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
            atlas_name: Name of atlas to overlay
            selected_regions: List of region indices to include (0-indexed), if None includes all

        Returns:
            Path to saved PDF file or None if failed
        """
        print(f"=== Creating PDF Visualization for {subject_id}/{simulation_name} ===")

        # Get simulation files
        sim_files = self._get_simulation_files(subject_id)
        if simulation_name not in sim_files:
            print(
                f"Error: Simulation '{simulation_name}' not found for subject {subject_id}"
            )
            return None

        ef_filepath = sim_files[simulation_name]
        ef_img = self._load_electric_field_data(ef_filepath)
        if ef_img is None:
            return None

        # Load and analyze data
        data = ef_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            print("Warning: No non-zero field values found")
            return None

        max_value = np.max(data)
        percentile_999 = np.percentile(data_nonzero, 99.9)
        min_value = np.min(data_nonzero)

        # Use provided max_cutoff or default to 99.9th percentile
        if max_cutoff is None:
            max_cutoff = percentile_999

        print(f"Electric field statistics:")
        print(f"  Absolute maximum: {max_value:.2f} V/m")
        print(f"  99.9th percentile: {percentile_999:.2f} V/m")
        print(f"  Minimum (non-zero): {min_value:.2f} V/m")
        print(f"  Visualization range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m")

        # Create output filename
        pdf_filename = f"{subject_id}_{simulation_name}_multiple_views.pdf"
        pdf_filepath = os.path.join(self.output_dir, pdf_filename)

        # Load atlas for contours
        atlas_img, atlas_display_name = self._load_atlas(atlas_name, selected_regions)

        # Create multi-slice plot with atlas contours
        self._create_multi_slice_plot_with_atlas(
            ef_img, atlas_img, atlas_display_name, pdf_filepath, min_cutoff, max_cutoff
        )

        print(f"✓ Saved: {pdf_filepath}")
        print(f"  Colorbar range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m")

        return pdf_filepath

    def _load_atlas(
        self, atlas_name: str, selected_regions: Optional[List[int]] = None
    ) -> Tuple[Optional[nib.Nifti1Image], str]:
        """
        Load the specified atlas and optionally filter to specific regions.

        Args:
            atlas_name: Name of the atlas
            selected_regions: Optional list of region indices to include

        Returns:
            Tuple of (atlas_image, display_name) or (None, "") if failed
        """
        atlas_configs = {
            "harvard_oxford": {
                "name": "Harvard Oxford Cortical Atlas",
                "function": lambda: datasets.fetch_atlas_harvard_oxford(
                    "cort-maxprob-thr25-2mm"
                ),
                "atlas_key": "filename",
                "labels_key": "labels",
            },
            "harvard_oxford_sub": {
                "name": "Harvard Oxford Subcortical Atlas",
                "function": lambda: datasets.fetch_atlas_harvard_oxford(
                    "sub-maxprob-thr25-2mm"
                ),
                "atlas_key": "filename",
                "labels_key": "labels",
            },
            "aal": {
                "name": "AAL Atlas",
                "function": lambda: datasets.fetch_atlas_aal(),
                "atlas_key": "maps",
                "labels_key": "labels",
            },
            "schaefer_2018": {
                "name": "Schaefer 2018 Atlas (100 regions)",
                "function": lambda: datasets.fetch_atlas_schaefer_2018(n_rois=100),
                "atlas_key": "maps",
                "labels_key": "labels",
            },
        }

        if atlas_name not in atlas_configs:
            print(
                f"Error: Unknown atlas '{atlas_name}'. Available: {list(atlas_configs.keys())}"
            )
            return None, ""

        config = atlas_configs[atlas_name]

        try:
            print(f"Loading {config['name']}...")
            atlas_data = config["function"]()
            atlas_img = atlas_data[config["atlas_key"]]

            if selected_regions and "labels" in atlas_data:
                # Create a filtered atlas with only selected regions
                atlas_nii = nib.load(atlas_img)
                atlas_array = atlas_nii.get_fdata()

                # Create mask for selected regions (regions are 0-indexed in the data)
                mask = np.zeros_like(atlas_array, dtype=bool)
                for region_idx in selected_regions:
                    mask = mask | (atlas_array == region_idx)

                # Create new atlas with only selected regions
                filtered_array = np.zeros_like(atlas_array)
                filtered_array[mask] = atlas_array[mask]

                # Create new nifti image
                atlas_img = nib.Nifti1Image(
                    filtered_array, atlas_nii.affine, atlas_nii.header
                )

                atlas_name_display = (
                    f"{config['name']} (Selected regions: {len(selected_regions)})"
                )
            else:
                atlas_name_display = config["name"]

            return atlas_img, atlas_name_display

        except Exception as e:
            print(f"Error loading atlas: {e}")
            return None, ""

    def _create_multi_slice_plot_with_atlas(
        self,
        field_img: nib.Nifti1Image,
        atlas_img: Optional[nib.Nifti1Image],
        atlas_name: str,
        output_path: str,
        min_cutoff: float,
        max_cutoff: float,
    ):
        """
        Create multi-slice plot with atlas contours and field overlay.

        Args:
            field_img: Electric field NIfTI image
            atlas_img: Atlas NIfTI image (optional)
            atlas_name: Display name for atlas
            output_path: Path to save the plot
            min_cutoff: Minimum threshold for field visualization
            max_cutoff: Maximum threshold for field visualization
        """
        # Threshold field data
        field_img_thresholded = threshold_img(field_img, threshold=min_cutoff)

        # Create figure with multiple slices - 3 rows (one per view) x 8 columns (slices)
        fig, axes = plt.subplots(3, 7, figsize=(32, 12), facecolor="white")
        fig.patch.set_facecolor("white")

        # Coordinates for multiple slices
        sagittal_coords = [-60, -40, -20, 0, 20, 40, 60]  # x coordinates
        coronal_coords = [-80, -55, -30, -5, 20, 45, 70]  # y coordinates
        axial_coords = [-30, -15, 10, 25, 40, 55, 70]  # z coordinates

        all_coords = [sagittal_coords, coronal_coords, axial_coords]
        view_names = ["Sagittal", "Coronal", "Axial"]
        coord_labels = ["x", "y", "z"]

        for row, (coords, view_name, coord_label) in enumerate(
            zip(all_coords, view_names, coord_labels)
        ):
            for col, cut_coord in enumerate(coords):
                ax = axes[row, col]

                # Plot the field data as the base layer
                display = plotting.plot_stat_map(
                    field_img_thresholded,
                    cut_coords=[cut_coord],
                    display_mode=coord_label.lower(),
                    axes=ax,
                    annotate=True,
                    black_bg=False,
                    cmap="hot",
                    vmin=min_cutoff,
                    vmax=max_cutoff,
                    colorbar=False,
                )

                # Add atlas contours on top if available
                if atlas_img is not None:
                    display.add_contours(
                        atlas_img,
                        colors=["red", "blue", "green", "yellow", "purple", "orange"]
                        * 20,
                        alpha=0.4,
                        linewidths=1,
                        levels=list(range(1, 200)),
                    )

                # Set view names only on first column for cleaner layout
                if col == 0:
                    ax.set_ylabel(
                        f"{view_name}",
                        fontsize=10,
                        fontweight="bold",
                        rotation=90,
                        labelpad=10,
                    )

        # Add colorbar
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors

        norm = mcolors.Normalize(vmin=min_cutoff, vmax=max_cutoff)
        sm = cm.ScalarMappable(cmap="hot", norm=norm)
        sm.set_array([])

        cbar_ax = fig.add_axes([0.15, 0.02, 0.7, 0.02])
        cbar = fig.colorbar(
            sm, cax=cbar_ax, orientation="horizontal", label="Electric Field (V/m)"
        )
        cbar.set_ticks([min_cutoff, max_cutoff])
        cbar.set_ticklabels([f"{min_cutoff:.2f}", f"{max_cutoff:.2f}"])

        # Main title
        atlas_text = f" with {atlas_name} Contours" if atlas_img is not None else ""
        fig.suptitle(
            f"Electric Field Multi-Slices{atlas_text}\n{min_cutoff:.2f}-{max_cutoff:.2f} V/m Range",
            fontsize=14,
            fontweight="bold",
        )

        plt.tight_layout(rect=[0, 0.08, 1, 0.92])

        # Save the figure
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"✓ Saved multi-slice plot: {output_path}")

        plt.close(fig)

    def create_html_visualization(
        self, subject_id: str, simulation_name: str, min_cutoff: float = 0.3
    ) -> Optional[str]:
        """
        Create interactive HTML visualization.

        Args:
            subject_id: Subject ID
            simulation_name: Name of the simulation
            min_cutoff: Minimum cutoff for visualization (V/m)

        Returns:
            Path to saved HTML file or None if failed
        """
        print(f"=== Creating HTML Visualization for {subject_id}/{simulation_name} ===")

        # Get simulation files
        sim_files = self._get_simulation_files(subject_id)
        if simulation_name not in sim_files:
            print(
                f"Error: Simulation '{simulation_name}' not found for subject {subject_id}"
            )
            return None

        ef_filepath = sim_files[simulation_name]
        ef_img = self._load_electric_field_data(ef_filepath)
        if ef_img is None:
            return None

        # Analyze data for thresholds
        data = ef_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            print("Warning: No non-zero field values found")
            return None

        percentile_999 = np.percentile(data_nonzero, 99.9)

        # Create output filename
        html_filename = f"{subject_id}_{simulation_name}_interactive.html"
        html_filepath = os.path.join(self.output_dir, html_filename)

        # Create interactive visualization
        view = view_img_on_surf(
            stat_map=ef_img,
            threshold=min_cutoff,
            vmax=percentile_999,
            cmap="hot",
            symmetric_cmap=False,
            bg_on_data=True,
            title=f"Electric Field - {subject_id}/{simulation_name}",
        )

        # Save as HTML
        view.save_as_html(html_filepath)
        print(f"✓ Saved interactive HTML: {html_filepath}")

        return html_filepath

    def create_pdf_visualization_group(
        self,
        averaged_img,
        base_filename: str,
        output_dir: str,
        min_cutoff: float = 0.3,
        max_cutoff: float = None,
        atlas_name: str = "harvard_oxford_sub",
        selected_regions: Optional[List[int]] = None,
    ) -> Optional[str]:
        """
        Create PDF visualization with pre-averaged nifti data.

        Args:
            averaged_img: Pre-averaged nibabel Nifti1Image
            base_filename: Base filename for output (without extension)
            output_dir: Output directory path
            min_cutoff: Minimum cutoff for visualization (V/m)
            max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
            atlas_name: Name of atlas to overlay
            selected_regions: List of region indices to include (0-indexed), if None includes all

        Returns:
            Path to saved PDF file or None if failed
        """
        print(f"=== Creating PDF Visualization for Group Averaged Data ===")

        # Load and analyze data
        data = averaged_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            print("Warning: No non-zero field values found")
            return None

        max_value = np.max(data)
        percentile_999 = np.percentile(data_nonzero, 99.9)
        min_value = np.min(data_nonzero)

        # Use provided max_cutoff or default to 99.9th percentile
        if max_cutoff is None:
            max_cutoff = percentile_999

        print(f"Electric field statistics (averaged data):")
        print(f"  Absolute maximum: {max_value:.2f} V/m")
        print(f"  99.9th percentile: {percentile_999:.2f} V/m")
        print(f"  Minimum (non-zero): {min_value:.2f} V/m")
        print(f"  Visualization range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m")

        # Create output filename
        pdf_filename = f"{base_filename}_multiple_views.pdf"
        pdf_filepath = os.path.join(output_dir, pdf_filename)

        # Load atlas for contours
        atlas_img, atlas_display_name = self._load_atlas(atlas_name, selected_regions)

        # Create multi-slice plot with atlas contours
        self._create_multi_slice_plot_with_atlas(
            averaged_img,
            atlas_img,
            atlas_display_name,
            pdf_filepath,
            min_cutoff,
            max_cutoff,
        )

        print(f"✓ Saved: {pdf_filepath}")
        print(f"  Colorbar range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m")

        return pdf_filepath

    def create_glass_brain_visualization(
        self,
        subject_id: str,
        simulation_name: str,
        min_cutoff: float = 0.3,
        max_cutoff: float = None,
        cmap: str = "hot",
    ) -> Optional[str]:
        """
        Create glass brain visualization using nilearn's plot_glass_brain.

        Args:
            subject_id: Subject ID
            simulation_name: Name of the simulation
            min_cutoff: Minimum cutoff for visualization (V/m)
            max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
            cmap: Colormap name for visualization

        Returns:
            Path to saved PNG file or None if failed
        """
        print(
            f"=== Creating Glass Brain Visualization for {subject_id}/{simulation_name} ==="
        )

        # Get simulation files
        sim_files = self._get_simulation_files(subject_id)
        if simulation_name not in sim_files:
            print(
                f"Error: Simulation '{simulation_name}' not found for subject {subject_id}"
            )
            return None

        ef_filepath = sim_files[simulation_name]
        ef_img = self._load_electric_field_data(ef_filepath)
        if ef_img is None:
            return None

        # Load and analyze data
        data = ef_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            print("Warning: No non-zero field values found")
            return None

        max_value = np.max(data)
        percentile_999 = np.percentile(data_nonzero, 99.9)
        min_value = np.min(data_nonzero)

        # Use provided max_cutoff or default to 99.9th percentile
        if max_cutoff is None:
            max_cutoff = percentile_999

        print(f"Electric field statistics:")
        print(f"  Absolute maximum: {max_value:.2f} V/m")
        print(f"  99.9th percentile: {percentile_999:.2f} V/m")
        print(f"  Minimum (non-zero): {min_value:.2f} V/m")
        print(f"  Visualization range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m")

        # Create output filename
        png_filename = f"{subject_id}_{simulation_name}_glass_brain.png"
        png_filepath = os.path.join(self.output_dir, png_filename)

        # Create glass brain visualization
        plotting.plot_glass_brain(
            stat_map_img=ef_img,
            threshold=min_cutoff,
            vmax=max_cutoff,
            cmap=cmap,
            colorbar=True,
            plot_abs=False,
            symmetric_cbar=False,
            title=f"Electric Field - {subject_id}/{simulation_name}\n{min_cutoff:.2f}-{max_cutoff:.2f} V/m",
            output_file=png_filepath,
        )

        print(f"✓ Saved glass brain visualization: {png_filepath}")

        return png_filepath
