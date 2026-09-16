"""``GET/POST /api/example-data`` — the example-data catalogue, and downloading one part.

**Not a job, on purpose.** Example data was briefly wired as a ``project_init`` job, which meant
asking an established project for a sample re-ran the initializer and reprinted its "New project
detected / Initializing BIDS-compliant structure" banner. A download is not an initialization:
:mod:`tit.examples` is a plain function (``catalogue()``, ``status()``, ``fetch()``) and this
module is the thin HTTP skin over it -- no :mod:`tit.jobs`, no stages, no spec.

    GET  /api/example-data                    datasets (each with its parts) + per-part
                                              {installed, bytes, downloading, queued, received,
                                              total, error}
    POST /api/example-data/{dataset}/{part}   start that one part, return at once

One download at a time, because the files are 15-590 MB and two competing 500 MB streams help
nobody. A ``POST`` while one is in flight is **not** an error: the part is appended to a small
queue the worker drains in order (that is what the chooser's *Download selected* relies on) and
the response is that part's current state -- ``queued`` for one waiting its turn. The renderer
polls ``GET`` while anything is downloading or queued and stops when nothing is.
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
    """The single worker thread, its queue, and the last error per part. Guarded by :attr:`lock`."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        #: The part id (``ernie/headmodel``) being fetched right now.
        self.part_id: str | None = None
        self.received = 0
        self.total = 0
        #: Parts waiting their turn, in order: ``(part_id, force)``.
        self.queue: list[tuple[str, bool]] = []
        #: part id -> the message the last failed fetch of it ended with.
        self.errors: dict[str, str] = {}

    def active(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def reset(self) -> None:
        """Forget everything -- used by tests between cases."""
        self.thread = None
        self.part_id = None
        self.received = self.total = 0
        self.queue.clear()
        self.errors.clear()

    def snapshot(self, part_id: str) -> dict[str, Any]:
        """The progress fields ``GET`` reports for *part_id*."""
        with self.lock:
            running = self.active() and self.part_id == part_id
            out: dict[str, Any] = {
                "downloading": running,
                "queued": any(q == part_id for q, _ in self.queue),
                "received": self.received if running else 0,
                "total": self.total if running else 0,
            }
            if (err := self.errors.get(part_id)) is not None:
                out["error"] = err
            return out


_STATE = _Download()


def _bound_project_dir() -> Path:
    project_dir = get_path_manager().project_dir
    if not project_dir:
        raise HTTPException(status_code=409, detail="This server is not bound to a project.")
    return Path(project_dir)


def _run(part_id: str, project_dir: Path, force: bool) -> None:
    """The worker thread: fetch this part, then whatever the queue picked up while it ran."""
    from tit import examples

    def progress(_id: str, _name: str, received: int, total: int) -> None:
        with _STATE.lock:
            _STATE.received, _STATE.total = received, total

    while True:
        dataset, part = examples.parse_part_id(part_id)
        try:
            examples.fetch(
                dataset,
                part,
                project_dir,
                force=force,
                progress=progress,
                log=lambda *a, **k: None,
            )
        except Exception as exc:  # noqa: BLE001 - any failure must reach the user, not the log alone
            with _STATE.lock:
                _STATE.errors[part_id] = str(exc)
        else:
            with _STATE.lock:
                _STATE.errors.pop(part_id, None)
        with _STATE.lock:
            if not _STATE.queue:
                _STATE.part_id = None
                _STATE.received = _STATE.total = 0
                return
            part_id, force = _STATE.queue.pop(0)
            _STATE.part_id, _STATE.received, _STATE.total = part_id, 0, 0


@router.get(
    "/api/example-data",
    response_model=ExampleDataCatalog,
    summary="The example-data catalogue, what is installed, and any download in flight",
    responses={409: {"description": "this server is not bound to a project"}},
)
def example_data() -> dict[str, Any]:
    """``{datasets, status}``. ``status`` is one entry per *part*, read off disk (no network) plus
    the live progress of whichever part is downloading right now, so one poll answers the page."""
    from tit import examples

    project_dir = _bound_project_dir()
    status = [{**entry, **_STATE.snapshot(entry["id"])} for entry in examples.status(project_dir)]
    return {"datasets": [d.to_dict() for d in examples.catalogue()], "status": status}


@router.post(
    "/api/example-data/{dataset_id}/{part_id}",
    response_model=ExampleDataStatus,
    summary="Start downloading one part of one example dataset into this project",
    responses={
        409: {"description": "this server is not bound to a project"},
        422: {"description": "unknown dataset or part"},
    },
)
def start_example_data(dataset_id: str, part_id: str, force: bool = False) -> dict[str, Any]:
    """Start (or queue) the fetch and return immediately; the renderer polls ``GET`` for progress.

    Returns this part's ``{id, dataset, part, installed, bytes, downloading, queued, received,
    total, error?}`` -- the same shape ``GET`` reports per part -- whether it started a download,
    queued one behind the fetch already running, or found the part already installed.
    """
    from tit import examples

    project_dir = _bound_project_dir()
    try:
        part = examples.part_by_id(dataset_id, part_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    full_id = part.full_id
    with _STATE.lock:
        if _STATE.active():
            if _STATE.part_id != full_id and not any(q == full_id for q, _ in _STATE.queue):
                _STATE.queue.append((full_id, force))
                _STATE.errors.pop(full_id, None)
        else:
            _STATE.part_id, _STATE.received, _STATE.total = full_id, 0, 0
            _STATE.queue.clear()
            _STATE.errors.pop(full_id, None)
            _STATE.thread = threading.Thread(
                target=_run, args=(full_id, project_dir, force), daemon=True
            )
            _STATE.thread.start()

    entry = next(s for s in examples.status(project_dir) if s["id"] == full_id)
    return {**entry, **_STATE.snapshot(full_id)}
