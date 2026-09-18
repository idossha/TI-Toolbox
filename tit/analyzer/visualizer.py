"""Stateless visualization and output helpers for the analyzer pipeline.

Module-level functions that write output artifacts (mesh overlays,
NIfTI overlays, the field-distribution histogram, CSV, metadata JSON)
without any shared mutable state.
The scene that shows an overlay is :mod:`tit.analyzer.scene`.  These are
package-internal; the public API is :class:`~tit.analyzer.Analyzer`.

See Also
--------
tit.analyzer.analyzer : Analyzer class that calls these helpers.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from tit.paths import get_path_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Mesh ROI overlay
# ---------------------------------------------------------------------------


def save_mesh_roi_overlay(
    surface_mesh_path: Path,
    field_values: np.ndarray,
    roi_mask: np.ndarray,
    field_name: str,
    output_dir: Path,
    normal_mesh_path: Path | None = None,
) -> Path:
    """Write .msh + .msh.opt overlay with ROI field highlighted.

    Loads a fresh surface mesh copy, drops its own data (the whole-surface
    field is the simulation's file, not this analysis's), adds ``<field>_ROI``
    -- the field at the ROI's nodes and exactly ``0`` everywhere else -- and
    writes both the mesh and a Gmsh options file for colour-map / range.
    When *normal_mesh_path* is given ``TI_normal_ROI`` is added as a second
    (initially hidden) view.

    Parameters
    ----------
    surface_mesh_path : pathlib.Path
        Path to the cortical surface mesh file.
    field_values : numpy.ndarray
        Per-node field values for the entire surface.
    roi_mask : numpy.ndarray
        Boolean mask selecting ROI nodes.
    field_name : str
        Name of the primary field (used in the mesh view label).
    output_dir : pathlib.Path
        Directory where the overlay files are written.
    normal_mesh_path : pathlib.Path or None, optional
        Path to the TI_normal mesh file. When provided, the normal field
        is added as an additional (hidden) view.

    Returns
    -------
    pathlib.Path
        Path to the written ``roi_overlay.msh`` file.
    """
    import simnibs

    output_dir = Path(get_path_manager().ensure(str(output_dir)))

    region_mesh = simnibs.read_msh(str(surface_mesh_path))
    region_mesh.elmdata = []
    region_mesh.nodedata = []

    roi_data = np.zeros(region_mesh.nodes.nr)
    roi_data[roi_mask] = field_values[roi_mask]
    region_mesh.add_node_field(roi_data, f"{field_name}_ROI")

    max_value = float(np.max(roi_data[roi_mask])) if np.any(roi_mask) else 0.0

    normal_max_value = max_value
    if normal_mesh_path is not None and Path(normal_mesh_path).exists():
        logger.info("Adding TI_normal field from: %s", normal_mesh_path)
        normal_mesh = simnibs.read_msh(str(normal_mesh_path))
        if "TI_normal" in normal_mesh.field:
            nf_values = normal_mesh.field["TI_normal"].value
            masked_normal = np.zeros(region_mesh.nodes.nr)
            masked_normal[roi_mask] = nf_values[roi_mask]
            region_mesh.add_node_field(masked_normal, "TI_normal_ROI")
            positive_normal = nf_values[roi_mask][nf_values[roi_mask] > 0]
            if positive_normal.size > 0:
                normal_max_value = float(np.max(positive_normal))
            del normal_mesh

    out_msh = output_dir / "roi_overlay.msh"
    region_mesh.write(str(out_msh))
    _write_msh_opt(out_msh, max_value, normal_max_value)

    logger.info("Created mesh overlay: %s", out_msh)
    return out_msh


def _write_msh_opt(
    msh_path: Path,
    max_value: float,
    normal_max_value: float,
) -> None:
    """Write a Gmsh .msh.opt file controlling view settings."""
    opt_path = Path(f"{msh_path}.opt")
    opt_path.write_text(f"""\
// Hide mesh element faces for cleaner field visualization
Mesh.SurfaceFaces = 0;
Mesh.SurfaceEdges = 0;
Mesh.Points = 0;
Mesh.Lines = 0;

// View[0]: the field inside the ROI (zero outside it)
View[0].Visible = 1;
View[0].ColormapNumber = 1;
View[0].RangeType = 2;
View[0].CustomMin = 0;
View[0].CustomMax = {max_value};
View[0].ShowScale = 1;
View[0].ColormapAlpha = 1;
View[0].ColormapAlphaPower = 0.08;

// View[1]: TI_normal inside the ROI (initially hidden)
View[1].Visible = 0;
View[1].ColormapNumber = 2;
View[1].RangeType = 2;
View[1].CustomMin = 0;
View[1].CustomMax = {normal_max_value};
View[1].ShowScale = 1;
View[1].ColormapAlpha = 1;
View[1].ColormapAlphaPower = 0.08;
""")


# ---------------------------------------------------------------------------
# 2. NIfTI ROI overlay
# ---------------------------------------------------------------------------


def save_nifti_roi_overlay(
    field_data: np.ndarray,
    roi_mask: np.ndarray,
    output_dir: Path,
    affine: np.ndarray,
) -> Path:
    """Write NIfTI overlay with field values only inside ROI.

    Parameters
    ----------
    field_data : numpy.ndarray
        3-D field intensity array.
    roi_mask : numpy.ndarray
        Boolean mask selecting ROI voxels.
    output_dir : pathlib.Path
        Directory where the overlay file is written.
    affine : numpy.ndarray
        4x4 affine matrix for the NIfTI image.

    Returns
    -------
    pathlib.Path
        Path to the written ``roi_overlay.nii.gz`` file.
    """
    output_dir = Path(get_path_manager().ensure(str(output_dir)))

    overlay = np.zeros_like(field_data)
    overlay[roi_mask] = field_data[roi_mask]

    out_path = output_dir / "roi_overlay.nii.gz"
    nib.save(nib.Nifti1Image(overlay, affine), str(out_path))

    logger.info("Created NIfTI overlay: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# 3. Histogram
# ---------------------------------------------------------------------------


def save_histogram(
    whole_head_values: np.ndarray,
    roi_values: np.ndarray,
    output_dir: Path,
    whole_head_weights: np.ndarray | None = None,
    roi_weights: np.ndarray | None = None,
    roi_mean: float | None = None,
    region_name: str | None = None,
    unit_label: str = "Area (mm\u00b2)",
    n_bins: int = 100,
    dpi: int = 150,
) -> Path | None:
    """Write ``histogram.png``: the field's distribution in the ROI against grey matter.

    Two weighted histograms on shared bins -- the whole grey matter (area- or
    volume-weighted) and the ROI on top of it -- with the ROI's mean and the
    focality cutoffs (50/75/90/95 % of the GM 99.9th percentile) as vertical
    lines.  One PNG at *dpi*, sized to stay legible as a thumbnail.

    Parameters
    ----------
    whole_head_values : numpy.ndarray
        Field values over the whole grey matter surface / volume.
    roi_values : numpy.ndarray
        Field values inside the ROI.
    output_dir : pathlib.Path
        Directory the PNG is written to.
    whole_head_weights, roi_weights : numpy.ndarray or None, optional
        Per-node areas (mm^2) or per-voxel volumes (mm^3).  Both or neither;
        without them the histogram counts elements.
    roi_mean : float or None, optional
        Drawn as a vertical line.
    region_name : str or None, optional
        Named in the title and the legend.
    unit_label : str, optional
        The y-axis label when weights are given.
    n_bins : int, optional
        Bins over the whole-GM range (default 100).
    dpi : int, optional
        Output resolution (default 150).

    Returns
    -------
    pathlib.Path or None
        ``<output_dir>/histogram.png``, or ``None`` when either input is empty.
    """
    from tit.plotting._common import (
        SaveFigOptions,
        ensure_headless_matplotlib_backend,
        savefig_close,
    )

    gm = np.asarray(whole_head_values, dtype=float).ravel()
    roi = np.asarray(roi_values, dtype=float).ravel()
    gm_ok = np.isfinite(gm)
    roi_ok = np.isfinite(roi)
    gm_w = roi_w = None
    if whole_head_weights is not None and roi_weights is not None:
        gm_w = np.broadcast_to(np.asarray(whole_head_weights, float), gm.shape)[gm_ok]
        roi_w = np.broadcast_to(np.asarray(roi_weights, float), roi.shape)[roi_ok]
    gm = gm[gm_ok]
    roi = roi[roi_ok]
    if gm.size == 0 or roi.size == 0:
        logger.warning("Histogram skipped: empty ROI or grey-matter distribution")
        return None

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt

    weighted = gm_w is not None
    y_label = unit_label if weighted else "Elements"
    edges = np.histogram_bin_edges(gm, bins=n_bins)
    gm_hist, _ = np.histogram(gm, bins=edges, weights=gm_w)
    roi_hist, _ = np.histogram(roi, bins=edges, weights=roi_w)
    centers = (edges[:-1] + edges[1:]) / 2
    width = float(edges[1] - edges[0])
    roi_label = f"ROI ({region_name})" if region_name else "ROI"

    rc = {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "sans-serif"],
        "font.size": 11,
        "text.usetex": False,
    }
    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=(9, 5.5))
        ax.bar(
            centers,
            gm_hist,
            width=width,
            color="#9aa5b1",
            edgecolor="none",
            label="Grey matter",
        )
        ax.bar(
            centers,
            roi_hist,
            width=width,
            color="#d1495b",
            edgecolor="none",
            alpha=0.9,
            label=roi_label,
        )

        p999 = float(np.percentile(gm, 99.9))
        for frac, color in zip(
            (0.5, 0.75, 0.9, 0.95), ("#f4a261", "#e76f51", "#c1440e", "#7a1f00")
        ):
            t = frac * p999
            if edges[0] <= t <= edges[-1]:
                ax.axvline(
                    t,
                    color=color,
                    linestyle="--",
                    linewidth=1.3,
                    label=f"{int(frac * 100)}% of GM 99.9th pct ({t:.2f} V/m)",
                )
        if roi_mean is not None and edges[0] <= float(roi_mean) <= edges[-1]:
            ax.axvline(
                float(roi_mean),
                color="#1b6f3a",
                linewidth=2.2,
                label=f"ROI mean ({float(roi_mean):.2f} V/m)",
            )

        ax.set_yscale("log")
        ax.set_xlabel("Field strength (V/m)")
        ax.set_ylabel(y_label + " (log)")
        title = "Field distribution: ROI vs grey matter"
        if region_name:
            title += f" \u2014 {region_name}"
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right", frameon=True, fontsize=9)

        stats = (
            f"GM  mean {float(np.average(gm, weights=gm_w)):.2f}  "
            f"max {float(gm.max()):.2f}  99.9% {p999:.2f} V/m\n"
            f"ROI mean {float(np.average(roi, weights=roi_w)):.2f}  "
            f"max {float(roi.max()):.2f} V/m  n={roi.size:,}"
        )
        ax.text(
            0.99,
            0.02,
            stats,
            transform=ax.transAxes,
            fontsize=8.5,
            ha="right",
            va="bottom",
            family="monospace",
            bbox=dict(
                boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#cccccc"
            ),
        )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "histogram.png"
        fig.tight_layout()
        savefig_close(fig, str(out_path), fmt="png", opts=SaveFigOptions(dpi=dpi))

    logger.info("Saved histogram: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# 4. Results CSV
# ---------------------------------------------------------------------------


def save_results_csv(result: dict[str, Any], output_dir: Path) -> Path:
    """Write analysis result dict to a two-column CSV (Metric, Value).

    Entries whose value is ``None`` are silently skipped.

    Parameters
    ----------
    result : dict of str to Any
        Flat dictionary of metric names to scalar values.
    output_dir : pathlib.Path
        Directory where ``results.csv`` is written.

    Returns
    -------
    pathlib.Path
        Path to the written ``results.csv`` file.
    """
    output_dir = Path(get_path_manager().ensure(str(output_dir)))

    out_path = output_dir / "results.csv"
    with open(out_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Metric", "Value"])
        for key, value in result.items():
            if value is None:
                continue
            writer.writerow([key, value])

    logger.info("Saved results CSV: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# 5. Analysis metadata
# ---------------------------------------------------------------------------


def save_analysis_metadata(output_dir: Path, metadata: dict[str, Any]) -> Path:
    """Write analysis configuration to ``analysis.json``.

    Parameters
    ----------
    output_dir : pathlib.Path
        Directory where ``analysis.json`` is written.
    metadata : dict of str to Any
        Analysis configuration dictionary to persist.

    Returns
    -------
    pathlib.Path
        Path to the written ``analysis.json`` file.
    """
    output_dir = Path(get_path_manager().ensure(str(output_dir)))
    out_path = output_dir / "analysis.json"
    with open(out_path, "w") as fh:
        json.dump(metadata, fh, indent=2)
    logger.info("Saved analysis metadata: %s", out_path)
    return out_path
