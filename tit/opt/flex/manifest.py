"""Flex-search output manifest (flex_meta.json).

Every flex-search run writes a manifest alongside its outputs.
This is the single source of truth for run metadata -- downstream
consumers (simulator, GUI) read this instead of parsing folder names.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from tit.opt.config import (
    AtlasROI,
    FlexConfig,
    FlexResult,
    SphericalROI,
    SubcorticalROI,
)

MANIFEST_FILENAME = "flex_meta.json"
MANIFEST_VERSION = 1


def write_manifest(
    output_folder: str,
    config: FlexConfig,
    result: FlexResult,
    label: str,
    pareto_data: Optional[dict] = None,
) -> str:
    """Write flex_meta.json to output_folder.

    Args:
        output_folder: Directory to write the manifest into.
        config: The FlexConfig used for this run.
        result: The FlexResult from the completed run.
        label: Human-readable summary label for GUI display.
        pareto_data: Optional dict with pareto sweep summary (for sweep runs).

    Returns:
        Absolute path to the written manifest file.
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


def read_manifest(output_folder: str) -> Optional[dict]:
    """Read flex_meta.json from a folder.

    Args:
        output_folder: Directory that should contain the manifest.

    Returns:
        Parsed manifest dict, or None if missing or invalid.
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
    """Convert an ROISpec to a plain dict with a 'type' discriminator."""
    if isinstance(roi, SphericalROI):
        return {
            "type": "spherical",
            "x": roi.x,
            "y": roi.y,
            "z": roi.z,
            "radius": roi.radius,
            "use_mni": roi.use_mni,
        }
    if isinstance(roi, AtlasROI):
        return {
            "type": "atlas",
            "atlas_path": roi.atlas_path,
            "label": roi.label,
            "hemisphere": roi.hemisphere,
        }
    if isinstance(roi, SubcorticalROI):
        return {
            "type": "subcortical",
            "atlas_path": roi.atlas_path,
            "label": roi.label,
            "tissues": roi.tissues,
        }
    raise ValueError(f"Unknown ROI type: {type(roi)}")
