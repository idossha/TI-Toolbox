"""Entry point: simnibs_python -m tit.blender config.json

Reads a JSON config file, dispatches to the correct blender export function
based on the ``_type`` discriminator field.
"""

from __future__ import annotations

import json
import logging
import sys

from tit.logger import setup_logging, add_stream_handler


def _coerce_field_range(data: dict) -> dict:
    """Convert field_range from JSON list to tuple if present."""
    fr = data.get("field_range")
    if fr is not None:
        data["field_range"] = tuple(fr)
    return data


def main() -> int:
    setup_logging("INFO")
    add_stream_handler("tit.blender")
    logger = logging.getLogger("tit.blender")

    if len(sys.argv) < 2:
        logger.error("Usage: simnibs_python -m tit.blender <config.json>")
        return 1

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    mode = data.pop("_type", None)

    if mode == "MontageConfig":
        from tit.blender.montage_publication import run_montage
        from tit.blender.config import MontageConfig
        from tit.paths import get_path_manager

        get_path_manager(data.get("project_dir"))
        config = MontageConfig(**data)
        run_montage(config, logger_override=logger)
        return 0

    elif mode == "VectorConfig":
        from tit.blender.config import VectorConfig
        from tit.blender.vector_field_exporter import run_vectors

        config = VectorConfig(**data)
        run_vectors(config)
        return 0

    elif mode == "RegionConfig":
        from tit.blender.config import RegionConfig
        from tit.blender.region_exporter import run_regions

        data = _coerce_field_range(data)
        config = RegionConfig(**data)
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
