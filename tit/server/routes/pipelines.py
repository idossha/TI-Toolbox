"""``/api/pipelines`` — validate, run, export and store pipeline canvases (plan §1-D, D3/D4).

Thin HTTP over :mod:`tit.pipeline`: every rule about *whether* a graph can run lives there, every
rule about *how* its jobs are released lives in :mod:`tit.jobs`.  Running a pipeline is exactly one
``submit_plan`` call — the same call ``POST /api/jobs/groups`` makes for a ``pre`` DAG — so a
pipeline run is one ``group_id``, one row in Jobs, cancellable as one thing.

Saved documents live in ``<project>/code/ti-toolbox/pipelines/<name>.json``, beside the jobs and
config directories the rest of the server already owns.

Import cost is deliberately small (``dev/route_import_guard.py``): :mod:`tit.pipeline` pulls in no
SimNIBS, and ``nbformat`` / ``tit.config_io`` are imported inside the handlers that need them.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from tit.jobs.bootstrap import get_manager
from tit.paths import get_path_manager
from tit.pipeline import (
    NODE_KINDS,
    PORT_TYPES,
    PORTS,
    PipelineDocument,
    PipelineDocumentError,
    node_inputs,
    node_outputs,
    validate,
)
from tit.pipeline.validate import (
    CAPABILITIES,
    CAPABILITY_LABELS,
    KIND_READINESS,
    Readiness,
    readiness_from_overview,
)

router = APIRouter()

#: A saved pipeline's file name: no separators, no dots, no surprises on any filesystem.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")


def _pipelines_dir() -> str:
    """``<project>/code/ti-toolbox/pipelines/`` (sibling of ``config/`` and ``jobs/``)."""
    return os.path.join(os.path.dirname(get_path_manager().config_dir()), "pipelines")


def _safe_path(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise HTTPException(
            status_code=422,
            detail=(
                "pipeline name must be 1-64 characters of letters, digits, space, '-' or '_' "
                "and start with a letter or digit"
            ),
        )
    return os.path.join(_pipelines_dir(), f"{name}.json")


def _readiness() -> Readiness | None:
    """What every subject in the bound project already has, for the readiness gate.

    Read from the same aggregate the Overview page shows, so the canvas's refusal and the board a
    user just looked at cannot disagree. Returns ``None`` -- "check shape only" -- if the project
    cannot be read at all, because refusing every wire on a transient catalog error would be a
    worse failure than not checking.
    """
    try:
        from tit.server.routes.overview import build_overview

        return readiness_from_overview(build_overview(get_path_manager()))
    except Exception:  # pragma: no cover - a broken project must not block the canvas
        return None


def _document(body: Any) -> PipelineDocument:
    payload = (
        body.get("pipeline") if isinstance(body, dict) and "pipeline" in body else body
    )
    try:
        return PipelineDocument.from_dict(payload)
    except PipelineDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/api/pipelines/kinds",
    summary="Node kinds, their typed ports and what they need of a subject",
)
def list_kinds() -> dict[str, Any]:
    """The palette, and both tables that decide whether a wire may be drawn.

    The canvas draws its handles from this rather than from a hand-kept copy, so a port added on
    the server appears in the UI without a renderer change. It also needs to refuse a drag *at
    drag time* -- which is before there is a graph to ask the server about -- so it gets the
    readiness table (`requires`/`produces`) and applies it itself, while
    `POST /api/pipelines/validate` applies the same one server-side. One definition, in
    :mod:`tit.pipeline.validate`; two readers; no way for the drag and the receipt to disagree.

    Served here rather than from a second `/ports` route: it is the same table, and two endpoints
    for one fact is how they drift.
    """
    return {
        "port_types": list(PORT_TYPES),
        "capabilities": [
            {"capability": c, "label": CAPABILITY_LABELS[c]} for c in CAPABILITIES
        ],
        "kinds": [
            {
                "kind": kind,
                "inputs": list(node_inputs(kind)),
                "outputs": list(node_outputs(kind)),
                "required": list(PORTS[kind].required),
                "requires": list(KIND_READINESS[kind].requires),
                "produces": list(KIND_READINESS[kind].produces),
            }
            for kind in NODE_KINDS
        ],
    }


@router.get("/api/pipelines", summary="Saved pipelines in this project")
def list_pipelines() -> list[dict[str, Any]]:
    directory = _pipelines_dir()
    if not os.path.isdir(directory):
        return []
    out: list[dict[str, Any]] = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(directory, filename)
        try:
            stat = os.stat(path)
        except OSError:  # pragma: no cover - raced deletion
            continue
        entry: dict[str, Any] = {
            "name": filename[: -len(".json")],
            "modified_at": stat.st_mtime,
            "size": stat.st_size,
        }
        # Its size in steps, so the Saved list can state what a pipeline *is* without the user
        # opening it. Read, never parsed into a document: an unreadable or hand-mangled file
        # still lists (with no counts) rather than disappearing from the list.
        try:
            with open(path, encoding="utf-8") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                if isinstance(saved.get("nodes"), list):
                    entry["nodes"] = len(saved["nodes"])
                if isinstance(saved.get("edges"), list):
                    entry["edges"] = len(saved["edges"])
        except (OSError, ValueError):
            pass
        out.append(entry)
    return out


@router.get("/api/pipelines/{name}", summary="Load a saved pipeline")
def load_pipeline(name: str) -> dict[str, Any]:
    path = _safe_path(name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"no saved pipeline named {name!r}")
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"saved pipeline {name!r} is not valid JSON: {exc}",
            ) from exc
    return _document(data).to_dict()


@router.put("/api/pipelines/{name}", summary="Save a pipeline document")
def save_pipeline(name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    doc = _document(body)
    doc.name = name
    path = _safe_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc.to_dict(), fh, indent=2)
    os.replace(tmp, path)
    return {"name": name, "saved": True}


@router.delete(
    "/api/pipelines/{name}", status_code=204, summary="Delete a saved pipeline"
)
def delete_pipeline(name: str) -> None:
    path = _safe_path(name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"no saved pipeline named {name!r}")
    os.remove(path)


@router.post(
    "/api/pipelines/validate", summary="Validate a pipeline graph, with reasons"
)
def validate_pipeline(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    doc = _document(body)
    result = validate(doc, _readiness()).to_dict()
    result["jobs"] = _job_preview(doc) if result["ok"] else []
    return result


def _job_preview(doc: PipelineDocument) -> list[dict[str, Any]]:
    """The receipt: what Run would submit, without submitting it."""
    from tit.pipeline.plan import PipelinePlanError, plan_pipeline

    try:
        planned = plan_pipeline(doc)
    except PipelinePlanError:
        # A config that does not fit its dataclass is a *validation* answer, not a 500; the
        # graph-level issues are already in the response and this preview is best-effort.
        return []
    return [
        {
            "label": job.label,
            "kind": job.kind,
            "subject_ids": list(job.subject_ids),
            "after": list(job.after_labels),
            "tags": list(job.tags),
        }
        for job in planned
    ]


@router.post(
    "/api/pipelines/run",
    status_code=201,
    summary="Run a whole pipeline as one job group",
)
def run_pipeline_route(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """One ``submit_plan`` call: one ``group_id`` for the whole canvas.

    ``after`` on every submitted job is the document's edges resolved to real job ids, so the
    scheduler enforces the graph — there is no client-side sequencing and no second executor.
    """
    from tit.pipeline.plan import PipelinePlanError, plan_pipeline

    doc = _document(body)
    result = validate(doc, _readiness())
    if not result.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "pipeline does not validate",
                "issues": [i.to_dict() for i in result.errors],
            },
        )
    parallel_subjects = body.get("parallel_subjects", 1)
    if (
        not isinstance(parallel_subjects, int)
        or isinstance(parallel_subjects, bool)
        or parallel_subjects < 1
    ):
        raise HTTPException(
            status_code=422, detail="parallel_subjects must be an integer >= 1"
        )
    try:
        planned = plan_pipeline(
            doc,
            tags=list(body.get("tags") or []),
            overwrite=bool(body.get("overwrite", False)),
        )
    except PipelinePlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    submitted = get_manager(request.app).submit_plan(
        planned, created_by="gui", group_cap=parallel_subjects
    )
    submitted["pipeline"] = doc.name
    return submitted


@router.post(
    "/api/pipelines/export",
    response_class=PlainTextResponse,
    summary="Export a pipeline as a Jupyter notebook",
    responses={
        501: {"description": "nbformat is not installed in this environment"},
    },
)
def export_pipeline(
    body: dict[str, Any] = Body(...),
    format: str = Query(default="ipynb"),
) -> str:
    """The notebook, as ``.ipynb`` JSON text (``Content-Type: text/plain`` so it downloads raw).

    ``export`` is a pure function of the document — it reads no project state beyond the bound
    project directory it writes into the setup cell.
    """
    if format != "ipynb":
        raise HTTPException(status_code=422, detail="only format=ipynb is supported")
    from tit.pipeline.notebook import export_notebook

    doc = _document(body)
    try:
        project_dir = get_path_manager().project_dir
    except Exception:  # pragma: no cover - unbound project is fine for a pure export
        project_dir = None
    try:
        return export_notebook(doc, project_dir=project_dir)
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=(
                "notebook export needs `nbformat`, which is not installed in this environment "
                f"({exc})"
            ),
        ) from exc
