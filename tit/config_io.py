"""JSON serialization for config dataclasses.

Provides helpers to serialize typed config dataclasses (with Enum fields,
nested dataclasses, and union-typed ROI/electrode specs) to JSON files and
reconstruct them back.

Usage::

    from tit.config_io import write_config_json, read_config_json
    path = write_config_json(my_flex_config, prefix="flex")
    data = read_config_json(path)
"""

import json
import os
import tempfile
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from typing import Any

from tit.opt.config import ExConfig, FlexConfig
from tit.sim.config import Montage

# Mapping from class to discriminator string.
# Blender configs are registered lazily (see _get_discriminator_map) to avoid
# importing tit.blender at module load time — that package pulls in heavy deps
# (trimesh, simnibs, bpy) which are only available inside Docker.
_TYPE_DISCRIMINATED: dict[type, str] = {
    FlexConfig.SphericalROI: "SphericalROI",
    FlexConfig.AtlasROI: "AtlasROI",
    FlexConfig.SubcorticalROI: "SubcorticalROI",
    ExConfig.PoolElectrodes: "PoolElectrodes",
    ExConfig.BucketElectrodes: "BucketElectrodes",
    Montage: "Montage",
}

# Blender config types are matched by class name to avoid importing
# tit.blender.__init__ (which pulls in heavy deps like trimesh/bpy).
# The config module itself is pure Python, but the package __init__
# re-exports the heavy exporters.
_TYPE_DISCRIMINATED_BY_NAME: dict[str, str] = {
    "MontageConfig": "MontageConfig",
    "VectorConfig": "VectorConfig",
    "RegionConfig": "RegionConfig",
}


def serialize_config(config: Any) -> dict[str, Any]:
    """Convert a dataclass to a JSON-serializable dict.

    Handles:
    - Enum fields (uses ``.value``)
    - Nested dataclasses (recursed)
    - Union-typed ROI / electrode specs (adds ``_type`` discriminator)
    - None values (preserved)

    Also injects ``project_dir`` from the active PathManager so that
    subprocess entry points can initialise their own PathManager.
    """
    data = _serialize(config)
    # Inject project_dir for subprocess entry points
    from tit.paths import get_path_manager

    data["project_dir"] = get_path_manager().project_dir
    return data


def write_config_json(config: Any, prefix: str = "config") -> str:
    """Serialize config dataclass to a temporary JSON file.

    Returns the absolute file path.
    """
    data = serialize_config(config)
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    return path


def read_config_json(path: str) -> dict[str, Any]:
    """Read a JSON config file and return the parsed dict."""
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _serialize(obj: Any) -> Any:
    """Recursively serialize a value to a JSON-compatible type."""
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        result: dict[str, Any] = {}
        # Add _type discriminator for union-typed / top-level config classes
        obj_type = type(obj)
        if obj_type in _TYPE_DISCRIMINATED:
            result["_type"] = _TYPE_DISCRIMINATED[obj_type]
        elif obj_type.__name__ in _TYPE_DISCRIMINATED_BY_NAME:
            result["_type"] = _TYPE_DISCRIMINATED_BY_NAME[obj_type.__name__]
        for fld in fields(obj):
            result[fld.name] = _serialize(getattr(obj, fld.name))
        return result
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    # Primitive types (int, float, str, bool) pass through
    return obj
