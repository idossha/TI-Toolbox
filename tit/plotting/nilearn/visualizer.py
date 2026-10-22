"""Multi-slice field figures with atlas outlines for Nilearn Visuals.

:func:`field_nifti` names the MNI field file one simulation contributes, and
:class:`NilearnVisualizer` draws the 3 x 7 slice grid of a group-averaged field
(:mod:`tit.plotting.nilearn.img_slices` wraps it for the runner).
"""

import os
import warnings

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import plotting
from nilearn.image import threshold_img

from tit.analyzer.field_selector import is_mti_simulation
from tit.paths import get_path_manager
from tit.plotting.nilearn.atlases import ATLASES, atlas_path
from tit.plotting.nilearn.cutoffs import format_vm, resolve_cutoffs

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
    """Draws a group-averaged field as a multi-slice PDF with atlas outlines.

    See Also
    --------
    tit.plotting.nilearn.img_slices : The runner's entry point to this class.
    tit.plotting.nilearn.img_glass : The glass-brain PDF of the same field.
    """

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
        cbar.set_ticklabels([format_vm(min_cutoff), format_vm(max_cutoff)])

        # Main title
        atlas_text = (
            f" with {atlas_name} contours"
            if atlas_img is not None
            else " (atlas contours unavailable, see the log)"
        )
        fig.suptitle(
            f"Electric Field Multi-Slices{atlas_text}\n"
            f"{format_vm(min_cutoff)}-{format_vm(max_cutoff)} V/m Range",
            fontsize=14,
            fontweight="bold",
        )

        plt.tight_layout(rect=[0, 0.08, 1, 0.92])

        # Save the figure
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"✓ Saved multi-slice plot: {output_path}")

        plt.close(fig)

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

        Sagittal, coronal and axial rows of seven slices each, the field on
        a hot colour map over the MNI template, with optional atlas outlines.

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
        print(f"  Absolute maximum: {format_vm(max_value)} V/m")
        print(f"  99.9th percentile: {format_vm(percentile_999)} V/m")
        print(f"  Minimum (non-zero): {format_vm(min_value)} V/m")
        print(
            f"  Visualization range: {format_vm(min_cutoff)} - {format_vm(max_cutoff)} V/m"
        )

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
        print(
            f"  Colorbar range: {format_vm(min_cutoff)} - {format_vm(max_cutoff)} V/m"
        )

        return pdf_filepath
