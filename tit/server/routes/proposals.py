"""``/api/proposals`` (agent plans the user approves) and ``/api/sim-from-flex``.

Thin HTTP wrappers over :mod:`tit.server.proposals`, which owns the record, the planning, the
approval rules and the queuing of approved steps (ARCHITECTURE §6).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from tit.jobs.bootstrap import get_manager
from tit.server.schemas import SubjectId

router = APIRouter()


def _engine():
    from tit.server import proposals

    return proposals


def _note(body: dict[str, Any] | None) -> Any:
    return (body or {}).get("note")


@router.get("/api/proposals", summary="Agent proposals, newest first")
def list_proposals(
    request: Request,
    status: str | None = Query(default=None),
    include_dismissed: bool = Query(default=False),
) -> list[dict[str, Any]]:
    return _engine().list_views(get_manager(request.app), status, include_dismissed)


@router.post(
    "/api/proposals",
    status_code=201,
    summary="Propose a pipeline for the user to approve (each step validated and planned)",
)
def create_proposal(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    return _engine().create(get_manager(request.app), body)


@router.get(
    "/api/proposals/{id}", summary="One proposal with live step states"
)
def get_proposal(request: Request, id: str) -> dict[str, Any]:
    return _engine().get_view(get_manager(request.app), id)


@router.patch(
    "/api/proposals/{id}/steps/{step_id}",
    summary="Edit a pending step (config, subject_ids, overwrite); the step is re-planned",
)
def edit_step(
    request: Request, id: str, step_id: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    return _engine().edit_step(get_manager(request.app), id, step_id, body)


@router.post(
    "/api/proposals/{id}/approve",
    summary="Approve (optionally with edited steps); the server queues the steps",
    responses={409: {"description": "already decided, or a step is not runnable"}},
)
def approve_proposal(
    request: Request, id: str, body: dict[str, Any] | None = Body(default=None)
) -> dict[str, Any]:
    edits = (body or {}).get("steps")
    if edits is not None and not isinstance(edits, list):
        raise HTTPException(status_code=422, detail="steps must be an array of edits")
    return _engine().approve(get_manager(request.app), id, edits, _note(body))


@router.post(
    "/api/proposals/{id}/reject",
    summary="Reject with an optional note",
    responses={409: {"description": "already decided"}},
)
def reject_proposal(
    request: Request, id: str, body: dict[str, Any] | None = Body(default=None)
) -> dict[str, Any]:
    return _engine().reject(get_manager(request.app), id, _note(body))


@router.post(
    "/api/proposals/{id}/dismiss",
    summary="Hide a finished plan (done, rejected or failed) from the default list",
    responses={409: {"description": "the plan is still waiting or running"}},
)
def dismiss_proposal(request: Request, id: str) -> dict[str, Any]:
    return _engine().dismiss(get_manager(request.app), id)


@router.post(
    "/api/proposals/{id}/steps/{step_id}/run",
    summary="Queue one approved step now (retry a failed, errored or skipped step)",
    responses={409: {"description": "not approved, already running, or waiting"}},
)
def run_step(request: Request, id: str, step_id: str) -> dict[str, Any]:
    return _engine().run_step(get_manager(request.app), id, step_id)


@router.get(
    "/api/sim-from-flex",
    summary="A finished flex-search run's electrodes and currents as a simulation montage",
)
def sim_from_flex(
    subject: Annotated[SubjectId, Query()],
    flex_run: str | None = Query(default=None),
    eeg_net: str | None = Query(default=None),
) -> dict[str, Any]:
    from tit.paths import get_path_manager
    from tit.sim.montage_sources import resolve_flex_simulation

    try:
        return resolve_flex_simulation(
            get_path_manager(), subject, flex_run, eeg_net=eeg_net
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
