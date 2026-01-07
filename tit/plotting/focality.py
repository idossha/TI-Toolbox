"""
Analyzer-focused matplotlib plots.

Contains simple 2D plots that are shared by analyzers (voxel/mesh) and are not
the complex 3D/SimNIBS mesh visualization.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np

from ._common import SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close


def _stem_no_nii_gz(path: str) -> str:
    name = Path(path).name
    if name.endswith(".nii.gz"):
        return name[:-7]
    return Path(name).stem


def plot_whole_head_roi_histogram(
    *,
    output_dir: str,
    whole_head_field_data: np.ndarray,
    roi_field_data: np.ndarray,
    whole_head_element_sizes: Optional[np.ndarray] = None,
    roi_element_sizes: Optional[np.ndarray] = None,
    filename: Optional[str] = None,
    region_name: Optional[str] = None,
    roi_field_value: Optional[float] = None,
    data_type: str = "element",
    voxel_dims: Optional[tuple] = None,
    n_bins: int = 100,
    dpi: int = 600,
) -> str | None:
    """
    Generate a whole-head histogram with ROI contribution color coding.

    Efficient implementation: ROI contribution per bin is computed via vectorized
    division (no Python loops).
    """
    if whole_head_field_data is None or roi_field_data is None:
        return None

    whole_head_field_data = np.asarray(whole_head_field_data)
    roi_field_data = np.asarray(roi_field_data)

    if whole_head_field_data.size == 0 or roi_field_data.size == 0:
        return None

    # Remove NaN values
    wh_mask = ~np.isnan(whole_head_field_data)
    roi_mask = ~np.isnan(roi_field_data)
    whole_head_field_data = whole_head_field_data[wh_mask]
    roi_field_data = roi_field_data[roi_mask]

    if whole_head_field_data.size == 0 or roi_field_data.size == 0:
        return None

    # Optional volume weighting (only if we can do it consistently for both datasets)
    weights_wh = None
    weights_roi = None
    if data_type == "voxel" and voxel_dims is not None:
        voxel_volume = float(np.prod(voxel_dims[:3]))
        weights_wh = np.full(whole_head_field_data.shape, voxel_volume, dtype=float)
        weights_roi = np.full(roi_field_data.shape, voxel_volume, dtype=float)
    elif whole_head_element_sizes is not None and roi_element_sizes is not None:
        # Robust handling: some callers may pass scalar (0-d) "element sizes" in edge
        # cases (e.g., tiny ROIs). In that case, treat it as a uniform weight.
        wh_sizes = np.asarray(whole_head_element_sizes)
        roi_sizes = np.asarray(roi_element_sizes)

        # Broadcast scalars to match data, otherwise apply NaN masks.
        if wh_sizes.ndim == 0:
            wh_sizes = np.full(whole_head_field_data.shape, wh_sizes.item(), dtype=float)
        else:
            wh_sizes = wh_sizes[wh_mask]

        if roi_sizes.ndim == 0:
            roi_sizes = np.full(roi_field_data.shape, roi_sizes.item(), dtype=float)
        else:
            roi_sizes = roi_sizes[roi_mask]

        if wh_sizes.shape == whole_head_field_data.shape and roi_sizes.shape == roi_field_data.shape:
            weights_wh = wh_sizes
            weights_roi = roi_sizes

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt

    # Keep these local to the plotting call (avoid global side effects).
    #
    # Note: In minimal Docker/SimNIBS environments, matplotlib can emit very noisy
    # `findfont:` messages when fonts are missing. We suppress that noise in
    # `ensure_headless_matplotlib_backend()`; here we avoid forcing Helvetica (which
    # may not be installed) and provide a reasonable preference order.
    rc = {
        "pdf.fonttype": 42,  # Embed fonts as text (not paths)
        "pdf.use14corefonts": True,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Bitstream Vera Sans", "sans-serif"],
        "text.usetex": False,
        "svg.fonttype": "none",
    }

    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=(14, 10))

        # Histogram bins based on whole head data
        hist, bin_edges = np.histogram(whole_head_field_data, bins=n_bins, weights=weights_wh)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_width = float(bin_edges[1] - bin_edges[0])

        roi_hist, _ = np.histogram(roi_field_data, bins=bin_edges, weights=weights_roi)

        # Vectorized ROI contribution
        roi_contribution = np.divide(roi_hist, hist, out=np.zeros_like(hist, dtype=float), where=hist > 0)

        non_zero = roi_contribution[roi_contribution > 0]
        if non_zero.size > 0:
            max_contribution = float(max(np.percentile(non_zero, 95), 0.01))
        else:
            max_contribution = 0.01

        normalized = np.clip(roi_contribution / max_contribution, 0, 1)

        rainbow_cmap = plt.cm.get_cmap("rainbow")
        colors = rainbow_cmap(normalized)
        colors[:, 3] = 0.7

        ax.bar(bin_centers, hist, width=bin_width, color=colors, edgecolor="black")

        # Focality cutoffs based on 99.9 percentile
        focality_cutoffs = np.array([50, 75, 90, 95], dtype=float)
        percentile_99_9 = float(np.percentile(whole_head_field_data, 99.9))
        thresholds = (focality_cutoffs / 100.0) * percentile_99_9
        counts = [int(np.count_nonzero(whole_head_field_data >= t)) for t in thresholds]

        colors_lines = ["red", "darkred", "crimson", "maroon"]
        for i, (threshold, cutoff, count) in enumerate(zip(thresholds, focality_cutoffs, counts)):
            if float(np.min(whole_head_field_data)) <= threshold <= float(np.max(whole_head_field_data)):
                ax.axvline(
                    x=threshold,
                    color=colors_lines[i % len(colors_lines)],
                    linestyle="--",
                    linewidth=2,
                    label=f"{int(cutoff)}% of 99.9%ile\n({threshold:.2f} V/m)\nCount: {count:,} {data_type}s",
                )

        if roi_field_value is not None and float(np.min(whole_head_field_data)) <= float(roi_field_value) <= float(np.max(whole_head_field_data)):
            ax.axvline(
                x=float(roi_field_value),
                color="green",
                linestyle="-",
                linewidth=3,
                label=f"Mean ROI Field\n({float(roi_field_value):.2f} V/m)",
            )

        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.98), frameon=True, fontsize=11)

        ax.set_xlabel("Field Strength (V/m)", fontsize=14)
        ax.set_ylabel(f"{data_type.capitalize()}s", fontsize=14)
        ax.tick_params(axis="both", which="major", labelsize=12)

        title_parts = ["Whole-Head Field Distribution with ROI Contribution"]
        if region_name:
            title_parts.append(f"ROI: {region_name}")
        if filename:
            title_parts.append(f"File: {filename}")
        ax.set_title("\n".join(title_parts), fontsize=14)
        ax.grid(True, alpha=0.3)

        # Colorbar for ROI contribution
        sm = plt.cm.ScalarMappable(cmap=rainbow_cmap, norm=plt.Normalize(0, 1))
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, shrink=0.7, pad=0.02, aspect=25)
        # Avoid non-ASCII arrows to keep PDF core fonts (Helvetica) warning-free in minimal containers.
        cbar.set_label(
            f"ROI Contribution Fraction\n(Blue->Green->Red, max={max_contribution:.3f})",
            fontsize=12,
        )

        # Stats box
        stats_text = (
            "Whole Head:\n"
            f"Max: {float(np.max(whole_head_field_data)):.2f} V/m\n"
            f"Mean: {float(np.mean(whole_head_field_data)):.2f} V/m\n"
            f"99.9%ile: {float(np.percentile(whole_head_field_data, 99.9)):.2f} V/m\n"
            f"{data_type.capitalize()}s: {whole_head_field_data.size:,}\n\n"
            "ROI:\n"
            f"Mean: {float(np.mean(roi_field_data)):.2f} V/m\n"
            f"Max: {float(np.max(roi_field_data)):.2f} V/m\n"
            f"{data_type.capitalize()}s: {roi_field_data.size:,}"
        )
        ax.text(
            0.98,
            0.98,
            stats_text,
            transform=ax.transAxes,
            fontsize=11,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="square", facecolor="lightyellow"),
        )

        if filename:
            base_name = _stem_no_nii_gz(filename)
        elif region_name:
            base_name = f"{region_name}_whole_head_roi"
        else:
            base_name = "whole_head_roi_histogram"

        os.makedirs(output_dir, exist_ok=True)
        hist_file = os.path.join(output_dir, f"{base_name}_histogram.pdf")
        fig.tight_layout()
        return savefig_close(fig, hist_file, fmt="pdf", opts=SaveFigOptions(dpi=dpi))


