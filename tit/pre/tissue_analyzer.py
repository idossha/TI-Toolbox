#!/usr/bin/env python
"""
Tissue analysis for TI-Toolbox.

Analyzes tissue types (CSF, bone, skin) from segmented NIfTI data,
calculating volumes, thickness, and generating visualizations (thickness
maps and methodology figures).

Public API
----------
run_tissue_analysis
    Run tissue analysis for one or more tissue types for a subject.
TissueAnalyzer
    Low-level class that performs volume, thickness, and visualization
    analysis on a single tissue type.

See Also
--------
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
tit.pre.charm : CHARM head-mesh generation (produces the segmentation
    input consumed here).
"""

import logging
from pathlib import Path
from typing import Iterable

import nibabel as nib
import numpy as np
from scipy import ndimage

from tit.paths import get_path_manager
from .utils import PreprocessError

# Tissue configurations
TISSUE_CONFIGS = {
    "csf": {
        "name": "CSF",
        "labels": [4, 5, 14, 15, 43, 44, 72, 24, 520],
        "padding": 40,
        "color_scheme": "cividis",
        "tissue_color": [0, 0, 1],
        "brain_labels": [3, 42, 16],
    },
    "bone": {
        "name": "Bone",
        "labels": [515, 516],
        "padding": 30,
        "color_scheme": "plasma",
        "tissue_color": [1, 1, 1],
        "brain_labels": [3, 42, 16],
    },
    "skin": {
        "name": "Skin",
        "labels": [511],
        "padding": 35,
        "color_scheme": "viridis",
        "tissue_color": [1, 0.5, 0],
        "brain_labels": [3, 42, 16],
    },
}

DEFAULT_TISSUES = ("bone", "csf", "skin")

#: Slices on either side of a view's cut whose medial voxels colour it (display only).
VIEW_SLAB = 2
#: Margin drawn around the tissue in the thickness views, mm.
VIEW_MARGIN_MM = 10.0
#: The thickness histogram never splits the range finer than this many bins.
MAX_HISTOGRAM_BINS = 100


def _centre_slices(mask: np.ndarray) -> list[int]:
    """Voxel index of *mask*'s centre of mass along each axis, where the views cut."""
    return [int(round(float(np.mean(c)))) for c in np.nonzero(mask)]


def _histogram_edges(values: np.ndarray) -> np.ndarray:
    """Histogram bin edges halfway between neighbouring distinct values.

    Distances on a voxel grid take few distinct values (``2*sqrt(k)`` mm on a 1 mm
    grid), so equal-width bins leave some bins empty and give others two values, which
    draws spikes. Here each value gets a bin of its own; only where neighbours lie
    closer than 1/``MAX_HISTOGRAM_BINS`` of the range (a fine or anisotropic grid) do
    several share one.
    """
    levels = np.unique(values)
    if levels.size == 1:
        return levels[0] + np.array([-0.5, 0.5])
    step = (levels[-1] - levels[0]) / MAX_HISTOGRAM_BINS
    inner = []
    for mid in (levels[1:] + levels[:-1]) / 2:
        if not inner or mid - inner[-1] >= step:
            inner.append(mid)
    return np.array([2 * levels[0] - inner[0], *inner, 2 * levels[-1] - inner[-1]])


def _thickness_view(
    mask: np.ndarray,
    thickness_map: np.ndarray,
    axis: int,
    index: int,
    voxel_dims: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """One cut through *mask* at *index* along *axis*, coloured by thickness for display.

    Thickness exists only on the medial surface, which a plane crosses in a broken
    one-voxel line. Each tissue pixel of the cut shows instead the thickness of the
    nearest medial voxel within ``VIEW_SLAB`` slices; a cut with none stays NaN.

    Returns:
        ``(band, colour)``: the tissue in the cut, and the thickness drawn on it.
    """
    band = np.take(mask, index, axis=axis) > 0
    slab = range(
        max(0, index - VIEW_SLAB), min(mask.shape[axis], index + VIEW_SLAB + 1)
    )
    seeds = np.fmax.reduce(np.take(thickness_map, slab, axis=axis), axis=axis)
    colour = np.full(band.shape, np.nan)
    known = np.isfinite(seeds)
    if known.any():
        spacing = [d for i, d in enumerate(voxel_dims) if i != axis]
        nearest = ndimage.distance_transform_edt(
            ~known, sampling=spacing, return_distances=False, return_indices=True
        )
        colour[band] = seeds[tuple(nearest)][band]
    return band, colour


class TissueAnalyzer:
    """Analyze a single tissue type from segmented NIfTI data.

    Loads a labeling NIfTI volume, extracts the requested tissue mask,
    filters it to the brain region, computes thickness statistics via a 3-D
    distance transform, and writes a text report plus optional matplotlib
    visualizations.

    Parameters
    ----------
    nifti_path : str or pathlib.Path
        Path to the segmented labeling NIfTI file (e.g. ``labeling.nii.gz``).
    output_dir : str or pathlib.Path
        Directory where reports and figures are written.
    tissue_type : str
        One of ``'csf'``, ``'bone'``, or ``'skin'``.
    logger : logging.Logger
        Logger for progress messages.

    Attributes
    ----------
    tissue_name : str
        Human-readable tissue name (e.g. ``'CSF'``).
    tissue_labels : list[int]
        Segmentation label IDs for this tissue.
    voxel_volume : float
        Volume of a single voxel in mm^3.

    Raises
    ------
    PreprocessError
        If *tissue_type* is not a recognised key in ``TISSUE_CONFIGS``.

    See Also
    --------
    run_tissue_analysis : Convenience wrapper that analyses multiple tissues.
    """

    def __init__(
        self,
        nifti_path: str | Path,
        output_dir: str | Path,
        tissue_type: str,
        logger: logging.Logger,
    ):
        self.nifti_path = Path(nifti_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger

        if tissue_type not in TISSUE_CONFIGS:
            raise PreprocessError(f"Unknown tissue type: {tissue_type}")

        config = TISSUE_CONFIGS[tissue_type]
        self.tissue_name = config["name"]
        self.tissue_labels = config["labels"]
        self.padding = config["padding"]
        self.color_scheme = config["color_scheme"]
        self.tissue_color = config["tissue_color"]
        self.brain_labels = config["brain_labels"]

        # Load NIfTI in RAS+ voxel order (axis 0 left->right, 1 posterior->anterior,
        # 2 inferior->superior): charm keeps its input's storage order (Dataset 000's
        # sub-ernie is P, S, R), and the inferior cut and the figures' views and labels
        # assume these axes. Reordering only transposes/flips; nothing is resampled.
        self.logger.info(f"Loading NIfTI: {nifti_path}")
        self.nii = nib.as_closest_canonical(nib.load(str(nifti_path)))
        self.data = self.nii.get_fdata()
        self.voxel_dims = tuple(float(z) for z in self.nii.header.get_zooms()[:3])
        self.voxel_volume = float(np.prod(self.voxel_dims))

        # Load label names
        self.label_names = self._load_label_names()

    def _load_label_names(self) -> dict[int, str]:
        """Load label-ID-to-name mapping from ``labeling_LUT.txt``."""
        label_names = {}

        # Search for LUT file
        search_paths = [
            self.nifti_path.parent / "labeling_LUT.txt",
        ]

        # Check SimNIBS derivatives structure
        if "SimNIBS" in self.nifti_path.parts:
            for i, part in enumerate(self.nifti_path.parts):
                if part == "SimNIBS" and i + 1 < len(self.nifti_path.parts):
                    simnibs_dir = Path(*self.nifti_path.parts[: i + 2])
                    for subdir in simnibs_dir.iterdir():
                        if subdir.name.startswith("m2m_"):
                            lut = subdir / "segmentation" / "labeling_LUT.txt"
                            if lut.exists():
                                search_paths.insert(0, lut)

        for lut_path in search_paths:
            if not lut_path.exists():
                continue
            try:
                with open(lut_path, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            try:
                                label_id = int(parts[0].strip())
                                label_name = parts[1].strip().rstrip(":")
                                label_names[label_id] = label_name
                            except ValueError:
                                continue
                self.logger.debug(f"Loaded {len(label_names)} labels from {lut_path}")
                return label_names
            except OSError as e:
                self.logger.debug(f"Failed to load LUT: {e}")

        return label_names

    def _create_tissue_mask(self) -> np.ndarray:
        """Create a combined binary mask for all tissue labels."""
        mask = np.zeros_like(self.data, dtype=np.uint8)
        for label in self.tissue_labels:
            mask |= (self.data == label).astype(np.uint8)
        return mask

    def _create_brain_mask(self) -> np.ndarray:
        """Create a binary mask for brain reference regions."""
        mask = np.zeros_like(self.data, dtype=np.uint8)
        for label in self.brain_labels:
            mask |= (self.data == label).astype(np.uint8)
        return mask

    def _filter_to_brain_region(
        self, tissue_mask: np.ndarray, brain_mask: np.ndarray
    ) -> np.ndarray:
        """Restrict tissue mask to the brain bounding box with padding."""
        brain_coords = np.where(brain_mask > 0)
        if len(brain_coords[0]) == 0:
            return tissue_mask

        # Brain bounding box with padding
        min_coords = [max(0, c.min() - self.padding) for c in brain_coords]
        max_coords = [
            min(s, c.max() + self.padding)
            for c, s in zip(brain_coords, tissue_mask.shape)
        ]

        # Create region mask
        region_mask = np.zeros_like(tissue_mask)
        region_mask[
            min_coords[0] : max_coords[0],
            min_coords[1] : max_coords[1],
            min_coords[2] : max_coords[2],
        ] = 1

        # Exclude lower regions: slices inferior to the cut-off (RAS axis 2)
        _, z_threshold = self._inferior_cutoff(brain_coords[2])
        region_mask[:, :, :z_threshold] = 0

        return (tissue_mask * region_mask).astype(np.uint8)

    def _inferior_cutoff(self, brain_z: np.ndarray) -> tuple[int, int]:
        """Return the brain's centre slice and the first slice kept above it.

        The cut-off is ``padding`` slices below the centre, clamped at 0: a negative
        index would slice from the top of the volume instead.
        """
        centre = int(brain_z.min() + brain_z.max()) // 2
        return centre, max(0, centre - self.padding)

    def _calculate_thickness(
        self, mask: np.ndarray, region: np.ndarray | None = None
    ) -> dict:
        """Measure the tissue's thickness on its medial surface.

        The distance transform of *mask* gives each tissue voxel its distance ``d``
        to the nearest non-tissue voxel. On the medial surface (voxels no
        26-neighbour exceeds) ``d`` is the radius of the largest ball inscribed in
        the tissue there, so ``2d`` is the local thickness (the maximal-sphere
        definition of Hildebrand & Rüegsegger, 1997, J Microsc 185:67-75): a shell
        ``T`` mm thick reads ``T`` within one voxel. Averaging ``2d`` over every
        voxel instead reads about two thirds of ``T`` and a minimum of two voxels.

        Args:
            mask: Binary tissue mask; the distances are measured within it.
            region: Where thickness is reported (the filtered analysis region);
                defaults to *mask*.

        Returns:
            ``mean``/``std``/``min``/``max`` in mm over the medial voxels inside
            *region*, and ``thickness_map``: ``2d`` on those voxels, NaN elsewhere
            (``None`` when there are none).
        """
        region = mask if region is None else region
        medial = np.zeros(mask.shape, dtype=bool)
        if np.any(region):
            distance = ndimage.distance_transform_edt(mask, sampling=self.voxel_dims)
            medial = (
                (mask > 0)
                & (region > 0)
                & (distance >= ndimage.maximum_filter(distance, size=3))
            )
        if not medial.any():
            return {"max": 0, "min": 0, "mean": 0, "std": 0, "thickness_map": None}

        thickness_map = np.where(medial, 2 * distance, np.nan)
        thickness_values = thickness_map[medial]

        return {
            "max": float(np.max(thickness_values)),
            "min": float(np.min(thickness_values)),
            "mean": float(np.mean(thickness_values)),
            "std": float(np.std(thickness_values)),
            "thickness_map": thickness_map,
        }

    def _create_thickness_figure(
        self,
        filtered_mask: np.ndarray,
        thickness_stats: dict,
        plt,
    ) -> Path | None:
        """Create thickness visualization with 3 views and a histogram.

        The views cut through the tissue's centre of mass (the volume's middle can miss
        it), in mm, with the tissue drawn faintly under its thickness.
        """
        thickness_map = thickness_stats.get("thickness_map")
        if thickness_map is None or np.sum(filtered_mask) == 0:
            return None

        vx, vy, vz = dims = self.voxel_dims
        # Thickness is measured on the medial surface only; the map is NaN elsewhere.
        thickness_values = thickness_map[
            (filtered_mask > 0) & np.isfinite(thickness_map)
        ]
        vmin, vmax = np.nanmin(thickness_values), np.nanmax(thickness_values)
        centre = _centre_slices(filtered_mask)
        # Window per RAS axis, mm (voxel centres at index * size): tissue plus a margin.
        limits = [
            (c.min() * d - VIEW_MARGIN_MM, c.max() * d + VIEW_MARGIN_MM)
            for c, d in zip(np.nonzero(filtered_mask), dims)
        ]
        spans = [hi - lo for lo, hi in limits]
        directions = ("Left-Right", "Posterior-Anterior", "Inferior-Superior")

        # Layout: 3 views at one mm scale on top; histogram and statistics below
        fig = plt.figure(figsize=(14, 9), layout="constrained")
        rows = fig.add_gridspec(2, 1, height_ratios=[1.8, 1])
        top = rows[0].subgridspec(1, 3, width_ratios=[spans[0], spans[0], spans[1]])
        bottom = rows[1].subgridspec(1, 2, width_ratios=[3, 1])

        view_axes = []
        views = (("A. Axial", 2, "z"), ("B. Coronal", 1, "y"), ("C. Sagittal", 0, "x"))
        for col, (name, axis, letter) in enumerate(views):
            u, v = (a for a in range(3) if a != axis)
            band, colour = _thickness_view(
                filtered_mask, thickness_map, axis, centre[axis], dims
            )
            extent = (
                -dims[u] / 2,
                (band.shape[0] - 0.5) * dims[u],
                -dims[v] / 2,
                (band.shape[1] - 0.5) * dims[v],
            )
            ax = fig.add_subplot(top[0, col])
            ax.imshow(
                np.where(band, 1.0, np.nan).T,
                cmap="Greys",
                vmin=0,
                vmax=5,
                origin="lower",
                extent=extent,
                interpolation="nearest",
            )
            im = ax.imshow(
                colour.T,
                cmap=self.color_scheme,
                origin="lower",
                extent=extent,
                interpolation="nearest",
                vmin=vmin,
                vmax=vmax,
            )
            ax.set_xlim(limits[u])
            ax.set_ylim(limits[v])
            ax.set_title(
                f"{name} View ({letter} = {centre[axis] * dims[axis]:.0f} mm)",
                fontsize=12,
                fontweight="bold",
            )
            ax.set_xlabel(f"{directions[u]} (mm)")
            ax.set_ylabel(f"{directions[v]} (mm)")
            view_axes.append(ax)

        # Colorbar for the 3 views
        cbar = fig.colorbar(im, ax=view_axes, shrink=0.85)
        cbar.set_label("Thickness (mm)", fontweight="bold")

        # D. Histogram (bottom left): one bar per distinct thickness the grid allows
        ax4 = fig.add_subplot(bottom[0, 0])
        ax4.hist(
            thickness_values,
            bins=_histogram_edges(thickness_values),
            weights=np.full(thickness_values.shape, 100 / thickness_values.size),
            alpha=0.7,
            color="steelblue",
            edgecolor="navy",
        )

        # Statistical lines
        mean, std = thickness_stats["mean"], thickness_stats["std"]
        ax4.axvline(
            mean,
            color="red",
            linestyle="-",
            linewidth=2.5,
            label=f"Mean: {mean:.2f} mm",
        )
        ax4.axvline(
            mean + std,
            color="red",
            linestyle="--",
            linewidth=1.5,
            label=f"+1 SD: {mean + std:.2f} mm",
        )
        ax4.axvline(
            mean - std,
            color="red",
            linestyle="--",
            linewidth=1.5,
            label=f"-1 SD: {mean - std:.2f} mm",
        )

        p25, p75 = np.percentile(thickness_values, [25, 75])
        ax4.axvline(
            p25,
            color="orange",
            linestyle=":",
            linewidth=1.5,
            alpha=0.8,
            label=f"25th %ile: {p25:.2f} mm",
        )
        ax4.axvline(
            p75,
            color="orange",
            linestyle=":",
            linewidth=1.5,
            alpha=0.8,
            label=f"75th %ile: {p75:.2f} mm",
        )

        ax4.set_xlabel(
            f"{self.tissue_name} Thickness (mm)", fontsize=11, fontweight="bold"
        )
        ax4.set_ylabel("Medial voxels (%)", fontsize=11, fontweight="bold")
        ax4.set_title("D. Thickness Distribution", fontsize=12, fontweight="bold")
        ax4.grid(True, alpha=0.3, axis="y")

        # Statistics and legend (bottom right), in their own panel: never over a bar
        side = fig.add_subplot(bottom[0, 1])
        side.axis("off")
        side.legend(
            handles=ax4.get_lines(), loc="lower left", fontsize=9, framealpha=0.9
        )
        volume_cm3 = np.sum(filtered_mask) * self.voxel_volume / 1000
        stats_text = (
            f"Statistics Summary:\n"
            f"Range: {thickness_stats['min']:.2f} - {thickness_stats['max']:.2f} mm\n"
            f"Mean ± SD: {mean:.2f} ± {std:.2f} mm\n"
            f"Median: {np.median(thickness_values):.2f} mm\n"
            f"IQR: {p25:.2f} - {p75:.2f} mm\n"
            f"Voxels: {np.sum(filtered_mask):,}\n"
            f"Volume: {volume_cm3:.1f} cm³\n"
            f"Voxel dims: {vx:.2f}×{vy:.2f}×{vz:.2f} mm"
        )
        side.text(
            0.0,
            1.0,
            stats_text,
            transform=side.transAxes,
            fontsize=9,
            verticalalignment="top",
            bbox=dict(
                boxstyle="round,pad=0.4", facecolor="white", alpha=0.9, edgecolor="gray"
            ),
        )

        fig.suptitle(
            f"{self.tissue_name} Thickness Analysis",
            fontsize=16,
            fontweight="bold",
        )

        # Save
        output_png = self.output_dir / f"{self.tissue_name.lower()}_thickness.png"
        output_pdf = self.output_dir / f"{self.tissue_name.lower()}_thickness.pdf"
        plt.savefig(output_png, dpi=300, bbox_inches="tight", facecolor="white")
        plt.savefig(output_pdf, bbox_inches="tight", facecolor="white")
        plt.close()

        self.logger.debug(f"Saved thickness figure: {output_png}")
        return output_png

    def _create_methodology_figure(
        self,
        tissue_mask: np.ndarray,
        brain_mask: np.ndarray,
        filtered_mask: np.ndarray,
        plt,
    ) -> Path | None:
        """Create methodology figure showing brain regions and Z-cutoff."""
        if np.sum(tissue_mask) == 0:
            return None

        # Layout: 2 rows x 3 columns (Row 1: brain reference, Row 2: filtered extraction)
        fig = plt.figure(figsize=(18, 12))
        gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], width_ratios=[1, 1, 1])

        vx, vy, vz = self.voxel_dims
        mid = [s // 2 for s in tissue_mask.shape]

        # Create separate masks for visualization
        hemisphere_mask = np.zeros_like(brain_mask)
        brainstem_mask = np.zeros_like(brain_mask)
        for label in self.brain_labels:
            if label in [3, 42]:  # Cerebral cortex labels
                hemisphere_mask |= (self.data == label).astype(np.uint8)
            elif label == 16:  # Brainstem
                brainstem_mask = (self.data == label).astype(np.uint8)

        # Calculate Z-cutoff parameters
        brain_z = np.where(brain_mask > 0)[2]
        brain_center_z, z_threshold = self._inferior_cutoff(
            brain_z if brain_z.size else np.array([mid[2]])
        )

        kept_pct = np.sum(filtered_mask) / max(np.sum(tissue_mask), 1) * 100
        view_configs = [
            ("Axial", lambda m: m[:, :, mid[2]], vy / vx),
            ("Coronal", lambda m: m[:, mid[1], :], vz / vx),
            ("Sagittal", lambda m: m[mid[0], :, :], vz / vy),
        ]

        # Row labels
        row_labels = [
            "A. Brain Reference Regions",
            "B. Filtered Tissue Extraction",
        ]

        for row in range(2):
            for col, (view_name, slice_fn, aspect) in enumerate(view_configs):
                ax = fig.add_subplot(gs[row, col])

                # Get slices
                tissue_slice = slice_fn(tissue_mask)
                filtered_slice = slice_fn(filtered_mask)
                hemisphere_slice = slice_fn(hemisphere_mask)
                brainstem_slice = slice_fn(brainstem_mask)

                # Create RGB image
                img = np.zeros((tissue_slice.shape[1], tissue_slice.shape[0], 3))

                if row == 0:  # Brain reference row
                    img[tissue_slice.T > 0] = self.tissue_color
                    img[hemisphere_slice.T > 0] = [0.5, 0.5, 0.5]  # Gray for cortex
                    img[brainstem_slice.T > 0] = [0, 0.8, 0]  # Green for brainstem

                else:  # Filtered extraction row
                    # Dimmed tissue for excluded regions
                    dimmed = [c * 0.3 for c in self.tissue_color]
                    img[tissue_slice.T > 0] = dimmed
                    img[filtered_slice.T > 0] = self.tissue_color
                    img[hemisphere_slice.T > 0] = [0.5, 0.5, 0.5]
                    img[brainstem_slice.T > 0] = [0, 0.8, 0]

                    # Add Z-cutoff lines for coronal and sagittal views
                    if col in [1, 2]:
                        ax.axhline(
                            y=z_threshold,
                            color="yellow",
                            linewidth=3,
                            linestyle="--",
                            alpha=0.9,
                            label="Z-cutoff",
                        )
                        ax.axhline(
                            y=brain_center_z,
                            color="white",
                            linewidth=2,
                            linestyle=":",
                            alpha=0.8,
                            label="Brain center",
                        )

                ax.imshow(img, origin="lower", aspect=aspect)
                ax.set_title(f"{view_name} View", fontsize=11, fontweight="bold")
                ax.set_xticks([])
                ax.set_yticks([])

                # Add legend on first column only
                if col == 0:
                    if row == 0:
                        legend_text = (
                            f"Brain Reference:\n"
                            f"• Gray: Cerebral Cortex\n"
                            f"• Green: Brainstem\n"
                            f"• Colored: {self.tissue_name}"
                        )
                        box_color = "lightblue"
                    else:
                        legend_text = (
                            f"Tissue Extraction:\n"
                            f"• Bright: Kept ({kept_pct:.1f}%)\n"
                            f"• Dim: Excluded\n"
                            f"• Yellow: Z-cutoff\n"
                            f"• White: Brain center"
                        )
                        box_color = "lightyellow"

                    ax.text(
                        0.02,
                        0.98,
                        legend_text,
                        transform=ax.transAxes,
                        fontsize=9,
                        verticalalignment="top",
                        bbox=dict(
                            boxstyle="round,pad=0.3", facecolor=box_color, alpha=0.85
                        ),
                    )

            # Row label on left side
            fig.text(
                0.02,
                0.75 - row * 0.42,
                row_labels[row],
                fontsize=12,
                fontweight="bold",
                ha="left",
                va="center",
                rotation=90,
            )

        fig.suptitle(
            f"{self.tissue_name} Extraction Methodology",
            fontsize=16,
            fontweight="bold",
            y=0.96,
        )
        plt.tight_layout()
        plt.subplots_adjust(
            left=0.06, right=0.98, top=0.92, bottom=0.05, wspace=0.08, hspace=0.15
        )

        # Save
        output_png = self.output_dir / f"{self.tissue_name.lower()}_methodology.png"
        output_pdf = self.output_dir / f"{self.tissue_name.lower()}_methodology.pdf"
        plt.savefig(output_png, dpi=300, bbox_inches="tight", facecolor="white")
        plt.savefig(output_pdf, bbox_inches="tight", facecolor="white")
        plt.close()

        self.logger.debug(f"Saved methodology figure: {output_png}")
        return output_png

    def _create_visualizations(
        self,
        tissue_mask: np.ndarray,
        brain_mask: np.ndarray,
        filtered_mask: np.ndarray,
        thickness_stats: dict,
    ) -> None:
        """Create all visualization figures (thickness + methodology)."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            self.logger.warning("matplotlib not available, skipping visualizations")
            return

        plt.style.use("default")
        plt.rcParams.update(
            {
                "font.size": 11,
                "font.family": "DejaVu Sans",
                "axes.linewidth": 1.2,
                "figure.dpi": 150,
            }
        )

        # Create thickness figure
        self._create_thickness_figure(filtered_mask, thickness_stats, plt)

        # Create methodology figure
        self._create_methodology_figure(tissue_mask, brain_mask, filtered_mask, plt)

    def _write_report(
        self,
        tissue_mask: np.ndarray,
        filtered_mask: np.ndarray,
        thickness_stats: dict,
    ) -> Path:
        """Write a plain-text analysis summary report."""
        volume_mm3 = float(np.sum(filtered_mask)) * self.voxel_volume
        volume_cm3 = volume_mm3 / 1000

        report_path = self.output_dir / f"{self.tissue_name.lower()}_analysis.txt"
        with open(report_path, "w") as f:
            f.write(f"{self.tissue_name.upper()} ANALYSIS SUMMARY\n")
            f.write("=" * 40 + "\n\n")
            f.write(f"Input: {self.nifti_path}\n")
            dims = " x ".join(f"{d:g}" for d in self.voxel_dims)
            f.write(f"Voxel dimensions: {dims} mm\n\n")

            f.write("VOLUME:\n")
            f.write(f"  Total voxels: {np.sum(tissue_mask):,}\n")
            f.write(f"  Filtered voxels: {np.sum(filtered_mask):,}\n")
            f.write(f"  Volume: {volume_cm3:.3f} cm³\n\n")

            f.write("THICKNESS:\n")
            f.write(f"  Mean: {thickness_stats['mean']:.3f} mm\n")
            f.write(f"  Std: {thickness_stats['std']:.3f} mm\n")
            f.write(f"  Min: {thickness_stats['min']:.3f} mm\n")
            f.write(f"  Max: {thickness_stats['max']:.3f} mm\n\n")

            f.write("LABELS ANALYZED:\n")
            for label in self.tissue_labels:
                name = self.label_names.get(label, str(label))
                count = int(np.sum(self.data == label))
                f.write(f"  {label}: {name} ({count:,} voxels)\n")

        return report_path

    def analyze(self) -> dict:
        """Run the complete tissue analysis.

        Returns
        -------
        dict
            Analysis results with keys ``'volume_cm3'``, ``'volume_mm3'``,
            ``'thickness'`` (dict with mean/std/min/max), ``'voxels'``
            (dict with total/filtered), and ``'report_path'``.
        """
        self.logger.info(f"Analyzing {self.tissue_name}...")

        # Create masks
        tissue_mask = self._create_tissue_mask()
        brain_mask = self._create_brain_mask()

        total_voxels = int(np.sum(tissue_mask))
        if total_voxels == 0:
            self.logger.warning(f"No {self.tissue_name} tissue found")
            return {
                "volume_cm3": 0,
                "thickness": {"mean": 0, "std": 0, "min": 0, "max": 0},
            }

        # Filter to brain region
        if np.sum(brain_mask) > 0:
            filtered_mask = self._filter_to_brain_region(tissue_mask, brain_mask)
        else:
            filtered_mask = tissue_mask

        filtered_voxels = int(np.sum(filtered_mask))
        self.logger.debug(
            f"Voxels: {total_voxels:,} total, {filtered_voxels:,} filtered"
        )

        # Calculate thickness
        thickness_stats = self._calculate_thickness(tissue_mask, filtered_mask)

        # Calculate volume
        volume_mm3 = filtered_voxels * self.voxel_volume
        volume_cm3 = volume_mm3 / 1000

        # Generate outputs
        self._create_visualizations(
            tissue_mask, brain_mask, filtered_mask, thickness_stats
        )
        report_path = self._write_report(tissue_mask, filtered_mask, thickness_stats)

        self.logger.info(
            f"{self.tissue_name}: Volume={volume_cm3:.2f}cm³, "
            f"Thickness={thickness_stats['mean']:.2f}±{thickness_stats['std']:.2f}mm"
        )

        return {
            "volume_cm3": volume_cm3,
            "volume_mm3": volume_mm3,
            "thickness": {
                "mean": thickness_stats["mean"],
                "std": thickness_stats["std"],
                "min": thickness_stats["min"],
                "max": thickness_stats["max"],
            },
            "voxels": {"total": total_voxels, "filtered": filtered_voxels},
            "report_path": str(report_path),
        }


def run_tissue_analysis(
    project_dir: str,
    subject_id: str,
    *,
    tissues: Iterable[str] = DEFAULT_TISSUES,
    logger: logging.Logger,
) -> dict:
    """Run tissue analysis for a subject.

    Creates a ``TissueAnalyzer`` for each requested tissue type, computes
    volume and thickness statistics, and writes reports and visualizations.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    tissues : iterable of str, optional
        Tissue types to analyze.  Defaults to ``('bone', 'csf', 'skin')``.
    logger : logging.Logger
        Logger for progress output.

    Returns
    -------
    dict
        Mapping of tissue name to per-tissue analysis results (volume,
        thickness, voxel counts, report path).

    Raises
    ------
    PreprocessError
        If the segmentation labeling file does not exist.

    See Also
    --------
    TissueAnalyzer : Low-level analysis for a single tissue type.
    run_pipeline : Full preprocessing pipeline.
    """
    pm = get_path_manager(project_dir)

    label_path = Path(pm.tissue_labeling(subject_id))
    if not label_path.exists():
        raise PreprocessError(f"labeling.nii.gz not found: {label_path}")

    output_root = Path(pm.ensure(pm.tissue_analysis_output(subject_id)))
    results = {}

    for tissue in tissues:
        if tissue not in TISSUE_CONFIGS:
            logger.warning(f"Unknown tissue type: {tissue}, skipping")
            continue

        output_dir = output_root / f"{tissue}_analysis"
        analyzer = TissueAnalyzer(label_path, output_dir, tissue, logger)
        results[tissue] = analyzer.analyze()

    return results
