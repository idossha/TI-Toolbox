"""Stateless visualization and output helpers for the analyzer pipeline.

Module-level functions that write output artifacts (mesh overlays,
NIfTI overlays, CSV, metadata JSON) without any shared mutable state.
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
# 3. Results CSV
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
# 4. Analysis metadata
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
