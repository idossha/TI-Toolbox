"""Flex-search output manifest (``flex_meta.json``).

Every flex-search run writes a manifest alongside its outputs.
This is the single source of truth for run metadata -- downstream
consumers (simulator, GUI) read this instead of parsing folder names.

Public API
----------
write_manifest
    Serialize run metadata to ``flex_meta.json``.
read_manifest
    Load and parse an existing manifest.
MANIFEST_FILENAME
    Canonical filename (``"flex_meta.json"``).
MANIFEST_VERSION
    Integer schema version for forward compatibility.

See Also
--------
tit.opt.flex.flex.run_flex_search : Writes a manifest after each run.
"""

import json
import os
from datetime import datetime

from tit.opt.config import FlexConfig, FlexResult

MANIFEST_FILENAME = "flex_meta.json"
MANIFEST_VERSION = 1


def write_manifest(
    output_folder: str,
    config: FlexConfig,
    result: FlexResult,
    label: str,
    pareto_data: dict | None = None,
) -> str:
    """Write ``flex_meta.json`` to *output_folder*.

    Parameters
    ----------
    output_folder : str
        Directory to write the manifest into.
    config : FlexConfig
        The configuration used for this run.
    result : FlexResult
        The result from the completed run.
    label : str
        Human-readable summary label for GUI display.
    pareto_data : dict or None
        Optional dict with Pareto sweep summary (for sweep runs).

    Returns
    -------
    str
        Absolute path to the written manifest file.

    See Also
    --------
    read_manifest : Load a previously written manifest.
    """
    data = {
        "version": MANIFEST_VERSION,
        "created": datetime.now().isoformat(timespec="seconds"),
        "subject_id": config.subject_id,
        "goal": (
            str(config.goal.value)
            if hasattr(config.goal, "value")
            else str(config.goal)
        ),
        "postproc": (
            str(config.postproc.value)
            if hasattr(config.postproc, "value")
            else str(config.postproc)
        ),
        "current_mA": config.current_mA,
        "electrode": {
            "shape": config.electrode.shape,
            "dimensions": list(config.electrode.dimensions),
            "gel_thickness": config.electrode.gel_thickness,
        },
        "roi": _serialize_roi(config.roi),
        "non_roi": _serialize_roi(config.non_roi) if config.non_roi else None,
        "non_roi_method": (
            str(config.non_roi_method.value)
            if config.non_roi_method and hasattr(config.non_roi_method, "value")
            else str(config.non_roi_method) if config.non_roi_method else None
        ),
        "thresholds": config.thresholds,
        "n_multistart": config.n_multistart,
        "min_electrode_distance": config.min_electrode_distance,
        "result": {
            "success": result.success,
            "best_value": result.best_value,
            "best_run_index": result.best_run_index,
            "all_values": result.function_values,
        },
        "pareto": pareto_data,
        "label": label,
    }

    path = os.path.join(output_folder, MANIFEST_FILENAME)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def read_manifest(output_folder: str) -> dict | None:
    """Read ``flex_meta.json`` from a folder.

    Parameters
    ----------
    output_folder : str
        Directory that should contain the manifest.

    Returns
    -------
    dict or None
        Parsed manifest dict, or ``None`` if missing or invalid.

    See Also
    --------
    write_manifest : Create a new manifest.
    """
    path = os.path.join(output_folder, MANIFEST_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _serialize_roi(roi) -> dict:
    """Convert an ROI spec to a plain dict with a ``type`` discriminator."""
    if isinstance(roi, FlexConfig.SphericalROI):
        d = {
            "type": "spherical",
            "x": roi.x,
            "y": roi.y,
            "z": roi.z,
            "radius": roi.radius,
            "use_mni": roi.use_mni,
            "volumetric": roi.volumetric,
        }
        if roi.volumetric:
            d["tissues"] = roi.tissues
        return d
    if isinstance(roi, FlexConfig.AtlasROI):
        return {
            "type": "atlas",
            "atlas_path": roi.atlas_path,
            "label": roi.label,
            "hemisphere": roi.hemisphere,
        }
    if isinstance(roi, FlexConfig.SubcorticalROI):
        return {
            "type": "subcortical",
            "atlas_path": roi.atlas_path,
            "label": roi.label,
            "tissues": roi.tissues,
        }
    raise ValueError(f"Unknown ROI type: {type(roi)}")
