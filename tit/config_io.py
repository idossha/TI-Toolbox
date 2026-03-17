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

from tit.opt.config import (
    AtlasROI,
    BucketElectrodes,
    PoolElectrodes,
    SphericalROI,
    SubcorticalROI,
)
from tit.sim.config import Montage

# Mapping from class to discriminator string
_TYPE_DISCRIMINATED = {
    SphericalROI: "SphericalROI",
    AtlasROI: "AtlasROI",
    SubcorticalROI: "SubcorticalROI",
    PoolElectrodes: "PoolElectrodes",
    BucketElectrodes: "BucketElectrodes",
    Montage: "Montage",
}


def serialize_config(config: Any) -> dict[str, Any]:
    """Convert a dataclass to a JSON-serializable dict.

    Handles:
    - Enum fields (uses ``.value``)
    - Nested dataclasses (recursed)
    - Union-typed ROI / electrode specs (adds ``_type`` discriminator)
    - None values (preserved)
    """
    return _serialize(config)


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
        # Add _type discriminator for union-typed classes
        obj_type = type(obj)
        if obj_type in _TYPE_DISCRIMINATED:
            result["_type"] = _TYPE_DISCRIMINATED[obj_type]
        for fld in fields(obj):
            result[fld.name] = _serialize(getattr(obj, fld.name))
        return result
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    # Primitive types (int, float, str, bool) pass through
    return obj
