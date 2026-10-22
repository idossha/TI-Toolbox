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

import argparse
import os
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import image, plotting
from nilearn.image import threshold_img
from nilearn.plotting import view_img_on_surf

from tit.analyzer.field_selector import is_mti_simulation
from tit.constants import DIR_NILEARN_VISUALS
from tit.paths import get_path_manager
from tit.plotting.nilearn.atlases import ATLASES, atlas_path
from tit.plotting.nilearn.cutoffs import resolve_cutoffs

warnings.filterwarnings("ignore")


def field_nifti(subject_id: str, simulation_name: str) -> str:
    """The MNI grey-matter field NIfTI one simulation contributes to these figures.

    ``TI/niftis/grey_<sim>_TI_MNI_MNI_TI_max.nii.gz`` for a two-pair run, and
    ``mTI/niftis/grey_<sim>_mTI_MNI_MNI_mTI_max.nii.gz`` for an mTI run
    (:mod:`tit.sim.mTI`): the same quantity, the modulation depth, named per mode.
    """
    mode = "mTI" if is_mti_simulation(subject_id, simulation_name) else "TI"
    return os.path.join(
        get_path_manager().simulation(subject_id, simulation_name),
        mode,
        "niftis",
        f"grey_{simulation_name}_{mode}_MNI_MNI_{mode}_max.nii.gz",
    )


class NilearnVisualizer:
    """Main visualization class for electric field distributions.

    Provides methods for creating both static PDF visualizations and
    interactive HTML plots.  Uses PathManager for consistent path handling
    and supports multiple atlas overlays.

    Parameters
    ----------
    subject_id : str or None, optional
        Subject identifier.  When *None*, PathManager auto-detection is
        used instead.

    Attributes
    ----------
    pm : PathManager
        Resolved path-manager instance.
    subject_id : str or None
        Subject identifier passed at construction time.
    output_dir : str
        Directory where visualizations are saved.

    See Also
    --------
    tit.plotting.nilearn.img_slices : Convenience entry-points for PDF creation.
    tit.plotting.nilearn.img_glass : Convenience entry-points for glass-brain PNGs.
    tit.plotting.nilearn.html_report : Convenience entry-point for HTML reports.
    """

    def __init__(self, subject_id: str | None = None):
        """Create a new visualizer instance.

        Parameters
        ----------
        subject_id : str or None, optional
            Subject identifier.  When *None*, PathManager auto-detection
            is used instead.
        """
        self.pm = get_path_manager()
        self.subject_id = subject_id
        self.output_dir = None

        # Set up output directory
        self._setup_output_directory()

    def _setup_output_directory(self):
        """Create the output directory for visualizations if it does not exist."""
        derivatives_dir = self.pm.derivatives()
        self.output_dir = os.path.join(
            derivatives_dir, "ti-toolbox", DIR_NILEARN_VISUALS
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def _load_electric_field_data(self, filepath: str) -> nib.Nifti1Image | None:
        """Load a NIfTI file, returning *None* when *filepath* does not exist."""
        if os.path.exists(filepath):
            return nib.load(filepath)
        else:
            print(f"Warning: {filepath} not found")
            return None

    def create_pdf_visualization(
        self,
        subject_id: str,
        simulation_name: str,
        min_cutoff: float | None = None,
        max_cutoff: float | None = None,
        atlas_name: str = "harvard_oxford_sub",
        selected_regions: list[int] | None = None,
    ) -> str | None:
        """Create a multi-slice PDF with atlas contours for a single subject.

        Generates sagittal, coronal, and axial slice rows with the electric
        field overlaid as a hot colormap and optional atlas contour lines.
        Reads the simulation's MNI grey-matter NIfTI (:func:`field_nifti`).

        Parameters
        ----------
        subject_id : str
            Subject identifier (e.g. ``'070'``).
        simulation_name : str
            Name of the simulation folder.
        min_cutoff : float or None, optional
            Lower display threshold in V/m.  When *None* the 95th
            percentile of non-zero voxels is used.
        max_cutoff : float or None, optional
            Upper display threshold in V/m.  When *None* the 99.9th
            percentile of non-zero voxels is used.
        atlas_name : str, optional
            Nilearn atlas key.  One of ``'harvard_oxford'``,
            ``'harvard_oxford_sub'``, ``'aal'``, ``'schaefer_2018'``.
        selected_regions : list of int or None, optional
            0-indexed region indices to include in the atlas overlay.
            When *None*, all regions are shown.

        Returns
        -------
        str or None
            Path to the saved PDF, or *None* on failure.
        """
        print(f"=== Creating PDF Visualization for {subject_id}/{simulation_name} ===")
        ef_img = self._load_electric_field_data(
            field_nifti(subject_id, simulation_name)
        )
        if ef_img is None:
            return None
        return self.create_pdf_visualization_group(
            ef_img,
            f"{subject_id}_{simulation_name}",
            self.output_dir,
            min_cutoff,
            max_cutoff,
            atlas_name,
            selected_regions,
        )

    def _load_atlas(
        self, atlas_name: str, selected_regions: list[int] | None = None
    ) -> tuple[nib.Nifti1Image | None, str]:
        """Load a nilearn atlas, optionally filtered to *selected_regions*.

        Never raises: outlines are context, so a failure is reported in plain words and
        the caller draws the field without them.
        """
        if atlas_name not in ATLASES:
            print(
                f"Atlas contours skipped: unknown atlas {atlas_name!r} "
                f"(choose one of {', '.join(ATLASES)}). The figure has no region outlines."
            )
            return None, ""

        display_name = ATLASES[atlas_name][0]
        try:
            print(f"Loading {display_name}...")
            atlas_img = atlas_path(atlas_name)

            if selected_regions:
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

                display_name = (
                    f"{display_name} (Selected regions: {len(selected_regions)})"
                )

            return atlas_img, display_name

        # No network, a read-only cache or a corrupt file costs only the outlines.
        except Exception as e:  # noqa: BLE001
            print(
                f"Atlas contours skipped: the {display_name} could not be loaded "
                f"({type(e).__name__}: {e}). The figure is drawn without region outlines. "
                f"The TI-Toolbox image ships this atlas in NILEARN_DATA "
                f"({os.environ.get('NILEARN_DATA', 'not set here')}); anywhere else nilearn "
                "downloads it on first use, which needs network access."
            )
            return None, ""

    def _create_multi_slice_plot_with_atlas(
        self,
        field_img: nib.Nifti1Image,
        atlas_img: nib.Nifti1Image | None,
        atlas_name: str,
        output_path: str,
        min_cutoff: float,
        max_cutoff: float,
    ):
        """Render a 3-row x 7-column slice grid with field overlay and atlas contours."""
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
                    # Cool hues only: red/orange/yellow outlines read as field on "hot".
                    display.add_contours(
                        atlas_img,
                        colors=["blue", "green", "purple", "cyan", "navy", "teal"] * 20,
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
        atlas_text = (
            f" with {atlas_name} contours"
            if atlas_img is not None
            else " (atlas contours unavailable, see the log)"
        )
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
        self, subject_id: str, simulation_name: str, min_cutoff: float | None = None
    ) -> str | None:
        """Create an interactive HTML surface visualization.

        Uses ``nilearn.plotting.view_img_on_surf`` to project the
        electric-field map onto the cortical surface and saves the result
        as a self-contained HTML file.

        Parameters
        ----------
        subject_id : str
            Subject identifier.
        simulation_name : str
            Name of the simulation folder.
        min_cutoff : float or None, optional
            Lower display threshold in V/m.  When *None* the 95th
            percentile of non-zero voxels is used.

        Returns
        -------
        str or None
            Path to the saved HTML file, or *None* on failure.
        """
        print(f"=== Creating HTML Visualization for {subject_id}/{simulation_name} ===")
        ef_img = self._load_electric_field_data(
            field_nifti(subject_id, simulation_name)
        )
        if ef_img is None:
            return None

        # Analyze data for thresholds
        data = ef_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            print("Warning: No non-zero field values found")
            return None

        min_cutoff, percentile_999 = resolve_cutoffs(data_nonzero, min_cutoff, None)

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
        min_cutoff: float | None = None,
        max_cutoff: float | None = None,
        atlas_name: str = "harvard_oxford_sub",
        selected_regions: list[int] | None = None,
    ) -> str | None:
        """Create a multi-slice PDF from a pre-averaged group NIfTI image.

        Identical layout to :meth:`create_pdf_visualization` but accepts
        an already-averaged ``nibabel.Nifti1Image`` instead of looking up
        a per-subject simulation file.

        Parameters
        ----------
        averaged_img : nibabel.Nifti1Image
            Pre-averaged electric-field image.
        base_filename : str
            Base filename for output (without extension).
        output_dir : str
            Directory where the PDF will be saved.
        min_cutoff : float or None, optional
            Lower display threshold in V/m.  When *None* the 95th
            percentile of non-zero voxels is used.
        max_cutoff : float or None, optional
            Upper display threshold in V/m.  When *None* the 99.9th
            percentile of non-zero voxels is used.
        atlas_name : str, optional
            Nilearn atlas key.
        selected_regions : list of int or None, optional
            0-indexed region indices for the atlas overlay.

        Returns
        -------
        str or None
            Path to the saved PDF, or *None* on failure.
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
        min_cutoff, max_cutoff = resolve_cutoffs(data_nonzero, min_cutoff, max_cutoff)

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
        min_cutoff: float | None = None,
        max_cutoff: float | None = None,
        cmap: str = "hot",
    ) -> str | None:
        """Create a glass-brain PNG for a single subject simulation.

        Uses ``nilearn.plotting.plot_glass_brain`` to render a
        maximum-intensity projection of the electric-field map.

        Parameters
        ----------
        subject_id : str
            Subject identifier.
        simulation_name : str
            Name of the simulation folder.
        min_cutoff : float or None, optional
            Lower display threshold in V/m.  When *None* the 95th
            percentile of non-zero voxels is used.
        max_cutoff : float or None, optional
            Upper display threshold in V/m.  When *None* the 99.9th
            percentile of non-zero voxels is used.
        cmap : str, optional
            Matplotlib colormap name.  Default is ``'hot'``.

        Returns
        -------
        str or None
            Path to the saved PNG file, or *None* on failure.
        """
        print(
            f"=== Creating Glass Brain Visualization for {subject_id}/{simulation_name} ==="
        )
        ef_img = self._load_electric_field_data(
            field_nifti(subject_id, simulation_name)
        )
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
        min_cutoff, max_cutoff = resolve_cutoffs(data_nonzero, min_cutoff, max_cutoff)

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
