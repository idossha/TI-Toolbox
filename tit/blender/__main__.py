"""Command-line entry point for Blender export utilities.

Usage
-----
$ simnibs_python -m tit.blender config.json

Reads a JSON configuration file and dispatches to the appropriate
export function based on the ``_type`` discriminator field
(``MontageConfig``, ``VectorConfig``, or ``RegionConfig``).

Each handler returns the directory it actually wrote into -- montage resolves one when
``output_dir`` is ``None``, vectors and regions have ``_resolve_paths`` fill ``config.output_dir``
in -- and :func:`main` lists that directory through the same ``tit.jobs.events`` contract the
analyzer uses. Before this, a finished ``blender`` job reported ``artifacts: []`` even though it
had just written a ``.blend`` and two STLs, so the Jobs rail and Results had nothing to link
(job ``9aa38d4d9f414283``).

See Also
--------
tit.blender.config : Dataclass definitions for each export mode.
tit.config_io : Serialise / deserialise config objects to JSON.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.logger import setup_logging, add_stream_handler


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job."""
    from tit.paths import get_path_manager

    try:
        from tit.jobs import locks
        from tit.jobs.runner import ENV_JOB_ID
    except ImportError:
        return nullcontext()
    job_id = os.environ.get(ENV_JOB_ID)
    if not job_id:
        return nullcontext()
    requests = locks.keys_for(kind, subject_ids, config_dict)
    return locks.hold(get_path_manager().project_dir, job_id, requests)


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

    mode = data.get("_type")

    dispatch = {
        "MontageConfig": _run_montage,
        "VectorConfig": _run_vectors,
        "RegionConfig": _run_regions,
    }
    handler = dispatch.get(mode)
    if handler is None:
        logger.error(f"Unknown blender config type: {mode}")
        return 1

    subject_id = data.get("subject_id")
    lock_cm = _hold_locks("blender", [subject_id] if subject_id else [], data)

    from tit.jobs import events

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage(mode)
            started = time.time()
            output_dir = handler(data, logger)
            _emit_output_artifacts(output_dir, started, logger)
            exit_code = 0
            events.emit_result(
                {"mode": mode, "success": True, "output_dir": output_dir}
            )
    except Exception as exc:  # noqa: BLE001 - report and exit non-zero
        logger.error(str(exc), exc_info=True)
        exit_code = 1
    finally:
        events.emit_exit(exit_code)

    return exit_code


def _emit_output_artifacts(
    output_dir: str | None, started: float, logger: logging.Logger
) -> None:
    """List the files this export wrote. Bookkeeping never fails a finished run."""
    from tit.jobs.events import emit_new_artifacts

    if not isinstance(output_dir, str) or not output_dir:
        return
    try:
        emit_new_artifacts(output_dir, started)
    except Exception as exc:  # noqa: BLE001 - a finished export stays finished
        logger.warning(f"artifact listing skipped: {exc}")


def _run_montage(data: dict, logger: logging.Logger) -> str | None:
    from tit.blender.config import MontageConfig
    from tit.blender.montage_publication import run_montage

    config = deserialize_config(MontageConfig, data)
    result = run_montage(config, logger_override=logger)
    # `output_dir` may be None in the config (montage_publication resolves one under
    # derivatives/ti-toolbox/visual_exports/); the result's own paths are the truth.
    return os.path.dirname(result.final_blend) if result.final_blend else None


def _run_vectors(data: dict, logger: logging.Logger) -> str | None:
    from tit.blender.config import VectorConfig
    from tit.blender.vector_field_exporter import run_vectors

    config = deserialize_config(VectorConfig, data)
    run_vectors(config)
    # run_vectors() -> None; `_resolve_paths` filled config.output_dir in on the way.
    return config.output_dir or None


def _run_regions(data: dict, logger: logging.Logger) -> str | None:
    from tit.blender.config import RegionConfig
    from tit.blender.region_exporter import run_regions

    config = deserialize_config(RegionConfig, data)
    run_regions(config)
    # run_regions() -> int (regions exported); `_resolve_paths` set config.output_dir.
    return config.output_dir or None


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logging.getLogger("tit.blender").error(str(e), exc_info=True)
        sys.exit(1)
