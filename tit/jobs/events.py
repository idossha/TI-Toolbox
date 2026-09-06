"""Runner-side structured events (owner: B4).

Runners call these helpers at existing loop boundaries; when the environment variable
``TIT_EVENTS_FILE`` is set, ``tit.logger.setup_logging`` attaches a JSON sink that appends one
object per line (``contracts/events.schema.json``) to that file; otherwise they are no-ops apart
from a normal log line. The job manager (B1) only ever *reads* that file.

Event shapes (the reconciled contract, ``contracts/events.schema.json`` / the ``Event`` component
in ``contracts/openapi.v1.yaml`` -- see ``contracts/SCHEMA-CHANGES.md``'s 2026-08-27 entry, item 8):
``{"seq", "ts", "type": "log|stage|progress|marker|artifact|result|exit", "level"?, "logger"?,
"msg"?, "stage"?, "i"?, "n"?, "pct"?, "path"?, "kind"?, "label"?, "outputs"?, "artifacts"?,
"code"?}``.

- ``artifact`` events carry their own flat ``path``/``kind``/``label`` fields (both ``path`` and
  ``kind`` required) -- not a nested one-item list.
- ``result`` events carry ``outputs`` as the runner's own arbitrary structured payload (a real
  object, required), plus ``artifacts``: the job's accumulated ``{path, kind, label}`` list (every
  :func:`emit_artifact` call seen so far), so a result event alone lists every produced file
  without a caller needing to replay the whole stream.
- ``exit`` events carry ``code``: the runner's actual (integer) process exit code.

One remaining wrinkle, not resolved by the contract (fixed by this helper's signature instead):
the schema requires ``stage``/``i``/``n`` on every ``progress`` event, but :func:`emit_progress`'s
signature is fixed to ``(pct, msg=None)`` with no stage/index arguments of its own. Module-level
state (:data:`_current`) remembers the ``stage``/``i``/``n`` from the most recent :func:`emit_stage`
call and reuses them here.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from tit.logger import get_event_sink

_log = logging.getLogger("tit.jobs.events")

#: Per-process, per-"current job" state so the fixed `emit_progress` signature can still
#: produce schema-valid events, and so `emit_result` can report every artifact produced so
#: far without every caller re-threading its own list. A runner process only ever drives one
#: job, so this being module-level (not per-job) is fine.
_lock = threading.Lock()
_current: dict[str, Any] = {"stage": None, "i": None, "n": None}
_artifacts: list[dict[str, str]] = []


def _reset_state() -> None:
    """Clear stage/artifact state -- for tests only (each test is one "job")."""
    with _lock:
        _current["stage"] = None
        _current["i"] = None
        _current["n"] = None
        _artifacts.clear()


def emit_stage(stage: str, i: int | None = None, n: int | None = None) -> None:
    """A named stage started (``i`` of ``n`` when the stage is one of a known sequence)."""
    with _lock:
        _current["stage"] = stage
        _current["i"] = i
        _current["n"] = n
    sink = get_event_sink()
    if sink is None:
        _log.debug(f"TIT_EVENTS_FILE not set; emit_stage({stage!r}) is a no-op")
        return
    event: dict[str, Any] = {"type": "stage", "stage": stage}
    if i is not None:
        event["i"] = i
    if n is not None:
        event["n"] = n
    sink.write(event)


def emit_progress(pct: float, msg: str | None = None) -> None:
    """Determinate progress within the current stage, 0-100.

    ``stage``/``i``/``n`` (required by the events schema) are carried over
    from the most recent :func:`emit_stage` call -- see the module
    docstring's final paragraph.
    """
    sink = get_event_sink()
    if sink is None:
        _log.debug(f"TIT_EVENTS_FILE not set; emit_progress({pct!r}) is a no-op")
        return
    with _lock:
        stage = _current["stage"] or "progress"
        i = _current["i"] if _current["i"] is not None else 0
        n = _current["n"] if _current["n"] is not None else 100
    event: dict[str, Any] = {
        "type": "progress",
        "stage": stage,
        "i": i,
        "n": n,
        "pct": max(0.0, min(100.0, float(pct))),
    }
    if msg is not None:
        event["msg"] = msg
    sink.write(event)


def emit_artifact(path: str, kind: str, label: str | None = None) -> None:
    """An output file exists now (``kind`` in report|nifti|mesh|csv|json|pdf|png|txt|dir).

    Written as its own flat ``path``/``kind``/``label`` fields (the schema's ``artifact`` event
    shape), and remembered in :data:`_artifacts` so a later :func:`emit_result` can report the
    job's whole artifact list.
    """
    item: dict[str, str] = {"path": path, "kind": kind}
    if label is not None:
        item["label"] = label
    with _lock:
        _artifacts.append(item)
    sink = get_event_sink()
    if sink is None:
        _log.debug(f"TIT_EVENTS_FILE not set; emit_artifact({path!r}) is a no-op")
        return
    sink.write({"type": "artifact", **item})


def emit_result(outputs: dict[str, Any]) -> None:
    """The runner's final structured result (written last, before ``exit``).

    *outputs* -- the runner's arbitrary result payload (mixes file paths and scalar metrics) --
    is written verbatim as the event's ``outputs`` object. ``artifacts`` carries every artifact
    seen so far via :func:`emit_artifact`, so a consumer reading only this one event still gets
    the job's full output-file list alongside its metrics.
    """
    with _lock:
        artifacts = list(_artifacts)
    sink = get_event_sink()
    if sink is None:
        _log.debug("TIT_EVENTS_FILE not set; emit_result(...) is a no-op")
        return
    event: dict[str, Any] = {"type": "result", "outputs": outputs}
    if artifacts:
        event["artifacts"] = artifacts
    sink.write(event)


def emit_exit(code: int) -> None:
    """Always written in the runner's ``finally`` so ``lost`` vs ``failed`` is decidable.

    *code* is the runner's actual (integer) process exit code, carried as the event's ``code``
    field.
    """
    sink = get_event_sink()
    if sink is None:
        _log.debug(f"TIT_EVENTS_FILE not set; emit_exit({code!r}) is a no-op")
        return
    sink.write({"type": "exit", "code": code})


_ARTIFACT_KIND_BY_EXT = {
    ".csv": "csv",
    ".json": "json",
    ".pdf": "pdf",
    ".png": "png",
    ".txt": "txt",
    ".html": "report",
    ".msh": "mesh",
    ".gii": "mesh",
    ".nii": "nifti",
    ".gz": "nifti",  # .nii.gz
    ".log": "txt",
}


def emit_new_artifacts(root: str, since: float, *, limit: int = 200) -> list[str]:
    """Emit one ``artifact`` event per file under *root* modified at or after *since*.

    Runners whose output directory is decided deep inside a pipeline (the analyzer, for one)
    call this after the pipeline returns, so the Jobs panel lists what was written without the
    science code having to know about events. Returns the emitted paths (sorted).
    """
    import os

    found: list[str] = []
    if not root or not os.path.isdir(root):
        return found
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                if os.path.getmtime(path) + 1.0 < since:
                    continue
            except OSError:
                continue
            found.append(path)
    found.sort()
    for path in found[:limit]:
        ext = os.path.splitext(path)[1].lower()
        emit_artifact(
            path, _ARTIFACT_KIND_BY_EXT.get(ext, "txt"), os.path.basename(path)
        )
    return found[:limit]
