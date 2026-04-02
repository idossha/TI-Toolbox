"""Command-line entry point for Blender export utilities.

Usage
-----
$ simnibs_python -m tit.blender config.json

Reads a JSON configuration file and dispatches to the appropriate
export function based on the ``_type`` discriminator field
(``MontageConfig``, ``VectorConfig``, or ``RegionConfig``).

See Also
--------
tit.blender.config : Dataclass definitions for each export mode.
tit.config_io : Serialise / deserialise config objects to JSON.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import fields as dc_fields

from tit.logger import setup_logging, add_stream_handler


def _coerce_field_range(data: dict) -> dict:
    """Convert ``field_range`` from a JSON list to a tuple if present."""
    fr = data.get("field_range")
    if fr is not None:
        data["field_range"] = tuple(fr)
    return data


def _filter_fields(data: dict, cls: type) -> dict:
    """Keep only keys that match *cls* dataclass constructor parameters."""
    valid = {f.name for f in dc_fields(cls) if f.init}
    return {k: v for k, v in data.items() if k in valid}


def main() -> int:
    """Parse the config JSON and dispatch to the matching export runner."""
    setup_logging("INFO")
    add_stream_handler("tit.blender")
    logger = logging.getLogger("tit.blender")

    if len(sys.argv) < 2:
        logger.error("Usage: simnibs_python -m tit.blender <config.json>")
        return 1

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    mode = data.pop("_type", None)

    if mode == "MontageConfig":
        from tit.blender.montage_publication import run_montage
        from tit.blender.config import MontageConfig

        config = MontageConfig(**_filter_fields(data, MontageConfig))
        run_montage(config, logger_override=logger)
        return 0

    elif mode == "VectorConfig":
        from tit.blender.config import VectorConfig
        from tit.blender.vector_field_exporter import run_vectors

        config = VectorConfig(**_filter_fields(data, VectorConfig))
        run_vectors(config)
        return 0

    elif mode == "RegionConfig":
        from tit.blender.config import RegionConfig
        from tit.blender.region_exporter import run_regions

        data = _coerce_field_range(data)
        config = RegionConfig(**_filter_fields(data, RegionConfig))
        run_regions(config)
        return 0

    else:
        logger.error(f"Unknown blender config type: {mode}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logging.getLogger("tit.blender").error(str(e), exc_info=True)
        sys.exit(1)
