#!/usr/bin/env python
"""
Tissue Analysis for TI-toolbox.

Analyzes tissue types (CSF, bone, skin) from segmented NIfTI data,
calculating volumes, thickness, and generating visualizations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

import nibabel as nib
import numpy as np
from scipy import ndimage

from tit.core import get_path_manager
from .common import CommandRunner, PreprocessError

# Tissue configurations
TISSUE_CONFIGS = {
    "csf": {
        "name": "CSF",
        "labels": [4, 5, 14, 15, 43, 44, 72, 24, 520],
        "padding": 40,
        "color_scheme": "Blues",
        "tissue_color": [0, 0, 1],
        "brain_labels": [3, 42, 16],
    },
    "bone": {
        "name": "Bone",
        "labels": [515, 516],
        "padding": 30,
        "color_scheme": "hot",
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


class TissueAnalyzer:
    """Analyzes tissue from segmented NIfTI data."""

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

        # Load NIfTI
        self.logger.info(f"Loading NIfTI: {nifti_path}")
        self.nii = nib.load(str(nifti_path))
        self.data = self.nii.get_fdata()
        self.voxel_dims = self.nii.header.get_zooms()[:3]
        self.voxel_volume = float(np.prod(self.voxel_dims))

        # Load label names
        self.label_names = self._load_label_names()

    def _load_label_names(self) -> dict[int, str]:
        """Load label names from labeling_LUT.txt if available."""
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
            except Exception as e:
                self.logger.debug(f"Failed to load LUT: {e}")

        return label_names

    def _create_tissue_mask(self) -> np.ndarray:
        """Create combined mask for all tissue labels."""
        mask = np.zeros_like(self.data, dtype=np.uint8)
        for label in self.tissue_labels:
            mask |= (self.data == label).astype(np.uint8)
        return mask

    def _create_brain_mask(self) -> np.ndarray:
        """Create mask for brain reference regions."""
        mask = np.zeros_like(self.data, dtype=np.uint8)
        for label in self.brain_labels:
            mask |= (self.data == label).astype(np.uint8)
        return mask

    def _filter_to_brain_region(
        self, tissue_mask: np.ndarray, brain_mask: np.ndarray
    ) -> np.ndarray:
        """Filter tissue mask to brain region with padding."""
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

        # Z-coordinate filter (exclude lower regions)
        brain_center_z = (brain_coords[2].min() + brain_coords[2].max()) // 2
        z_threshold = brain_center_z - self.padding
        region_mask[:, :, :z_threshold] = 0

        return (tissue_mask * region_mask).astype(np.uint8)

    def _calculate_thickness(self, mask: np.ndarray) -> dict:
        """Calculate thickness using 3D distance transform."""
        if np.sum(mask) == 0:
            return {"max": 0, "min": 0, "mean": 0, "std": 0, "thickness_map": None}

        distance_map = ndimage.distance_transform_edt(mask, sampling=self.voxel_dims)
        thickness_values = distance_map[mask > 0] * 2  # Thickness = 2 * distance

        return {
            "max": float(np.max(thickness_values)),
            "min": float(np.min(thickness_values)),
            "mean": float(np.mean(thickness_values)),
            "std": float(np.std(thickness_values)),
            "thickness_map": distance_map * 2,
        }

    def _create_thickness_figure(
        self,
        filtered_mask: np.ndarray,
        thickness_stats: dict,
        plt,
    ) -> Optional[Path]:
        """Create thickness visualization: 3 views on top, histogram spanning bottom."""
        thickness_map = thickness_stats.get("thickness_map")
        if thickness_map is None or np.sum(filtered_mask) == 0:
            return None

        # Layout: top row has 3 views, bottom row has histogram spanning all columns
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(2, 3, height_ratios=[2, 1], width_ratios=[1, 1, 1])

        vx, vy, vz = self.voxel_dims
        mid = [s // 2 for s in thickness_map.shape]
        thickness_values = thickness_map[filtered_mask > 0]
        vmin, vmax = np.nanmin(thickness_values), np.nanmax(thickness_values)

        # A. Axial view (top-left)
        ax1 = fig.add_subplot(gs[0, 0])
        masked = np.where(
            filtered_mask[:, :, mid[2]] > 0, thickness_map[:, :, mid[2]], np.nan
        )
        im = ax1.imshow(
            masked.T,
            cmap=self.color_scheme,
            origin="lower",
            aspect=vy / vx,
            interpolation="bilinear",
            vmin=vmin,
            vmax=vmax,
        )
        ax1.set_title("A. Axial View", fontsize=12, fontweight="bold")
        ax1.set_xlabel("X (Anterior-Posterior)")
        ax1.set_ylabel("Y (Left-Right)")

        # B. Coronal view (top-center)
        ax2 = fig.add_subplot(gs[0, 1])
        masked = np.where(
            filtered_mask[:, mid[1], :] > 0, thickness_map[:, mid[1], :], np.nan
        )
        ax2.imshow(
            masked.T,
            cmap=self.color_scheme,
            origin="lower",
            aspect=vz / vx,
            interpolation="bilinear",
            vmin=vmin,
            vmax=vmax,
        )
        ax2.set_title("B. Coronal View", fontsize=12, fontweight="bold")
        ax2.set_xlabel("X (Anterior-Posterior)")
        ax2.set_ylabel("Z (Inferior-Superior)")

        # C. Sagittal view (top-right)
        ax3 = fig.add_subplot(gs[0, 2])
        masked = np.where(
            filtered_mask[mid[0], :, :] > 0, thickness_map[mid[0], :, :], np.nan
        )
        ax3.imshow(
            masked.T,
            cmap=self.color_scheme,
            origin="lower",
            aspect=vz / vy,
            interpolation="bilinear",
            vmin=vmin,
            vmax=vmax,
        )
        ax3.set_title("C. Sagittal View", fontsize=12, fontweight="bold")
        ax3.set_xlabel("Y (Left-Right)")
        ax3.set_ylabel("Z (Inferior-Superior)")

        # Colorbar for the 3 views
        cbar_ax = fig.add_axes([0.92, 0.55, 0.015, 0.35])
        cbar = fig.colorbar(im, cax=cbar_ax)
        cbar.set_label("Thickness (mm)", fontweight="bold")

        # D. Histogram (bottom, spanning all columns)
        ax4 = fig.add_subplot(gs[1, :])
        ax4.hist(
            thickness_values,
            bins=50,
            alpha=0.7,
            color="steelblue",
            edgecolor="navy",
            density=True,
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
        ax4.set_ylabel("Probability Density", fontsize=11, fontweight="bold")
        ax4.set_title("D. Thickness Distribution", fontsize=12, fontweight="bold")
        ax4.legend(loc="upper right", fontsize=9, framealpha=0.9)
        ax4.grid(True, alpha=0.3, axis="y")

        # Statistics text box
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
        ax4.text(
            0.02,
            0.98,
            stats_text,
            transform=ax4.transAxes,
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
            y=0.98,
        )
        plt.tight_layout()
        plt.subplots_adjust(right=0.90, top=0.93, bottom=0.08, hspace=0.25)

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
    ) -> Optional[Path]:
        """Create methodology figure showing brain regions, extraction, and Z-cutoff."""
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
        brain_coords = np.where(brain_mask > 0)
        if len(brain_coords[0]) > 0:
            brain_center_z = (brain_coords[2].min() + brain_coords[2].max()) // 2
            z_threshold = brain_center_z - self.padding
        else:
            brain_center_z = mid[2]
            z_threshold = mid[2] - self.padding

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
        """Create all visualization figures."""
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
        """Write analysis summary report."""
        volume_mm3 = float(np.sum(filtered_mask)) * self.voxel_volume
        volume_cm3 = volume_mm3 / 1000

        report_path = self.output_dir / f"{self.tissue_name.lower()}_analysis.txt"
        with open(report_path, "w") as f:
            f.write(f"{self.tissue_name.upper()} ANALYSIS SUMMARY\n")
            f.write("=" * 40 + "\n\n")
            f.write(f"Input: {self.nifti_path}\n")
            f.write(f"Voxel dimensions: {self.voxel_dims} mm\n\n")

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
        """Run the complete tissue analysis."""
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
        thickness_stats = self._calculate_thickness(filtered_mask)

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
    runner: Optional[CommandRunner] = None,
) -> dict:
    """Run tissue analysis for a subject.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the 'sub-' prefix.
    tissues : iterable of str
        Tissue types to analyze (default: bone, csf, skin).
    logger : logging.Logger
        Logger for progress output.
    runner : CommandRunner, optional
        Not used, kept for API compatibility.

    Returns
    -------
    dict
        Analysis results for each tissue type.
    """
    pm = get_path_manager()
    pm.project_dir = project_dir

    label_path = Path(pm.path("tissue_labeling", subject_id=subject_id))
    if not label_path.exists():
        raise PreprocessError(f"Labeling.nii.gz not found: {label_path}")

    output_root = Path(pm.ensure_dir("tissue_analysis_output", subject_id=subject_id))
    results = {}

    for tissue in tissues:
        if tissue not in TISSUE_CONFIGS:
            logger.warning(f"Unknown tissue type: {tissue}, skipping")
            continue

        output_dir = output_root / f"{tissue}_analysis"
        try:
            analyzer = TissueAnalyzer(label_path, output_dir, tissue, logger)
            results[tissue] = analyzer.analyze()
        except Exception as e:
            logger.error(f"Failed to analyze {tissue}: {e}")
            raise PreprocessError(f"Tissue analysis failed for {subject_id} ({tissue})")

    return results
