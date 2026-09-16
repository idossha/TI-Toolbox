"""``GET/POST /api/example-data`` — the example-data catalogue, and downloading one sample.

**Not a job, on purpose.** Example data was briefly wired as a ``project_init`` job, which meant
asking an established project for a sample re-ran the initializer and reprinted its "New project
detected / Initializing BIDS-compliant structure" banner. A download is not an initialization:
:mod:`tit.examples` is a plain function (``catalogue()``, ``status()``, ``fetch()``) and this
module is the thin HTTP skin over it -- no :mod:`tit.jobs`, no stages, no spec.

    GET  /api/example-data              catalogue + per-sample {installed, bytes, downloading,
                                        received, total, error}
    POST /api/example-data/{sample_id}  start the fetch on a background thread, return at once

One download at a time, because the samples are 15-630 MB and a user clicking twice wants the
first one to finish, not two half-downloads competing. A ``POST`` while one is in flight is **not**
an error: it returns the in-flight state, so the renderer's poll loop is the only thing that ever
reports progress. The renderer polls ``GET`` while anything is downloading and stops when nothing
is.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from tit.paths import get_path_manager
from tit.server.schemas import ExampleDataCatalog, ExampleDataStatus

router = APIRouter()


class _Download:
    """The single in-flight fetch, and the last one's error. Guarded by :attr:`lock`."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.sample_id: str | None = None
        self.received = 0
        self.total = 0
        #: sample id -> the message the last failed fetch of it ended with.
        self.errors: dict[str, str] = {}

    def active(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def snapshot(self, sample_id: str) -> dict[str, Any]:
        """The progress fields ``GET`` reports for *sample_id*."""
        with self.lock:
            running = self.active() and self.sample_id == sample_id
            out: dict[str, Any] = {
                "downloading": running,
                "received": self.received if running else 0,
                "total": self.total if running else 0,
            }
            if (err := self.errors.get(sample_id)) is not None:
                out["error"] = err
            return out


_STATE = _Download()


def _bound_project_dir() -> Path:
    project_dir = get_path_manager().project_dir
    if not project_dir:
        raise HTTPException(status_code=409, detail="This server is not bound to a project.")
    return Path(project_dir)


def _run(sample_id: str, project_dir: Path, force: bool) -> None:
    """The background thread: fetch, recording progress and any failure on :data:`_STATE`."""
    from tit import examples

    def progress(_id: str, _name: str, received: int, total: int) -> None:
        with _STATE.lock:
            _STATE.received, _STATE.total = received, total

    try:
        examples.fetch(sample_id, project_dir, force=force, progress=progress, log=lambda *a, **k: None)
    except Exception as exc:  # noqa: BLE001 - any failure must reach the user, not the log alone
        with _STATE.lock:
            _STATE.errors[sample_id] = str(exc)
    else:
        with _STATE.lock:
            _STATE.errors.pop(sample_id, None)


@router.get(
    "/api/example-data",
    response_model=ExampleDataCatalog,
    summary="The example-data catalogue, what is installed, and any download in flight",
    responses={409: {"description": "this server is not bound to a project"}},
)
def example_data() -> dict[str, Any]:
    """``{samples, status}``. ``status`` is read off disk (no network) plus the live progress of
    whichever sample is downloading right now, so one poll answers the whole page."""
    from tit import examples

    project_dir = _bound_project_dir()
    status = []
    for entry in examples.status(project_dir):
        status.append({**entry, **_STATE.snapshot(entry["id"])})
    return {"samples": [s.to_dict() for s in examples.catalogue()], "status": status}


@router.post(
    "/api/example-data/{sample_id}",
    response_model=ExampleDataStatus,
    summary="Start downloading one example sample into this project",
    responses={
        409: {"description": "this server is not bound to a project"},
        422: {"description": "unknown sample_id"},
    },
)
def start_example_data(sample_id: str, force: bool = False) -> dict[str, Any]:
    """Start the fetch and return immediately; the renderer polls ``GET`` for progress.

    Returns this sample's ``{id, installed, bytes, downloading, received, total, error?}`` --
    the same shape ``GET`` reports per sample -- whether it started a download, found the sample
    already installed, or found another one already in flight.
    """
    from tit import examples

    project_dir = _bound_project_dir()
    try:
        examples.sample_by_id(sample_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with _STATE.lock:
        if not _STATE.active():
            _STATE.sample_id, _STATE.received, _STATE.total = sample_id, 0, 0
            _STATE.errors.pop(sample_id, None)
            _STATE.thread = threading.Thread(
                target=_run, args=(sample_id, project_dir, force), daemon=True
            )
            _STATE.thread.start()

    entry = next(s for s in examples.status(project_dir) if s["id"] == sample_id)
    return {**entry, **_STATE.snapshot(sample_id)}
