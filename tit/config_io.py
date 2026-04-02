"""JSON serialisation for config dataclasses.

Provides helpers to serialise typed config dataclasses (with Enum fields,
nested dataclasses, and union-typed ROI/electrode specs) to JSON files and
read them back.

Public API
----------
serialize_config
    Convert a config dataclass to a JSON-serialisable dict (with
    ``project_dir`` injection).
write_config_json
    Serialise a config dataclass to a temporary JSON file.
read_config_json
    Read a JSON config file and return the parsed dict.

Examples
--------
>>> from tit.config_io import write_config_json, read_config_json
>>> path = write_config_json(my_flex_config, prefix="flex")
>>> data = read_config_json(path)

See Also
--------
tit.opt.config : ``FlexConfig`` and ``ExConfig`` dataclasses.
tit.sim.config : ``Montage`` dataclass.
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
    """Convert a config dataclass to a JSON-serialisable dict.

    Handles Enum fields (via ``.value``), nested dataclasses (recursed),
    union-typed ROI / electrode specs (injects a ``_type`` discriminator),
    and *None* values (preserved as JSON ``null``).

    Also injects ``project_dir`` from the active :class:`~tit.paths.PathManager`
    so that subprocess entry points can initialise their own singleton.

    Parameters
    ----------
    config : dataclass instance
        Any config dataclass (e.g., ``FlexConfig``, ``ExConfig``).

    Returns
    -------
    dict
        JSON-serialisable dictionary representation of *config*.

    See Also
    --------
    write_config_json : Serialise and write to a temp file in one step.
    read_config_json : Read a JSON config back into a dict.
    """
    data = _serialize(config)
    # Inject project_dir for subprocess entry points
    from tit.paths import get_path_manager

    data["project_dir"] = get_path_manager().project_dir
    return data


def write_config_json(config: Any, prefix: str = "config") -> str:
    """Serialise a config dataclass to a temporary JSON file.

    Parameters
    ----------
    config : dataclass instance
        Config object to serialise.
    prefix : str, optional
        Filename prefix for the temp file.  Default is ``"config"``.

    Returns
    -------
    str
        Absolute path to the created JSON file.

    See Also
    --------
    serialize_config : Convert to dict without writing to disk.
    read_config_json : Read a JSON config file.
    """
    data = serialize_config(config)
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    return path


def read_config_json(path: str) -> dict[str, Any]:
    """Read a JSON config file and return the parsed dict.

    Parameters
    ----------
    path : str
        Path to the JSON file.

    Returns
    -------
    dict
        Parsed JSON contents.

    See Also
    --------
    write_config_json : Create a config JSON file from a dataclass.
    """
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _serialize(obj: Any) -> Any:
    """Recursively serialise a value to a JSON-compatible type."""
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
