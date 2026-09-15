"""``GET /api/project`` — the project this server instance is bound to.

``POST /api/project/init`` (v1) submits the project's BIDS/derivative-layout
initialization as a ``project_init`` job through :mod:`tit.jobs.api`, the
same submit path every other job-producing route uses (owner: B1 for the
manager; this module only builds the spec) -- see this lane's final report
for the one piece B1 still needs to land (``project_init`` is in the
contract's frozen ``JobKind`` enum but not yet in ``tit.jobs.spec.JOB_KINDS``
nor dispatched by ``tit.jobs.kinds.command_for``, so ``jobs_api.submit``
currently raises ``ValueError`` for it -- caught below and turned into a
503, exactly like ``tit.server.routes.viewers``'s ``NotImplementedError``
handling for the same "contract kind, no runner yet" situation).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from tit.paths import get_path_manager
from tit.server.host_path import host_project_dir
from tit.server.schemas import Project, ProjectStatus

router = APIRouter()


@router.get(
    "/api/project",
    response_model=Project,
    summary="The project this server instance is bound to",
)
def project() -> Project:
    """``host_path`` is ``LOCAL_PROJECT_DIR`` when set, else read off this server's own
    container (bind mount, then the ``tit.host_project_dir`` label) -- see
    :mod:`tit.server.host_path` for why the environment variable alone left every v3
    container answering ``null``."""
    pm = get_path_manager()
    container_path = pm.project_dir or ""
    return Project(
        container_path=container_path,
        host_path=host_project_dir(container_path),
        name=pm.project_dir_name or os.path.basename(container_path),
    )


@router.get(
    "/api/project/status",
    response_model=ProjectStatus,
    summary="This project's project_status.json (empty when the file is missing)",
)
def project_status() -> dict[str, Any]:
    from tit.project_init import load_project_status

    return load_project_status(Path(_bound_project_dir()))


@router.patch(
    "/api/project/status",
    response_model=ProjectStatus,
    summary="Merge fields into project_status.json and return the result",
)
def patch_project_status(body: ProjectStatus) -> dict[str, Any]:
    """Records one-time answers such as ``example_subject_prompted`` (the desktop's
    "Add the example subject?" dialog). Creates the file when it is missing, because
    an answer that is not persisted is asked again."""
    from tit.project_init import load_project_status, update_project_status
    from tit.project_init.initializer import initialize_project_status

    project_dir = Path(_bound_project_dir())
    updates = body.model_dump(exclude_none=True)
    initialize_project_status(project_dir)
    if updates and not update_project_status(project_dir, updates):
        raise HTTPException(status_code=500, detail="Could not write project_status.json.")
    return load_project_status(project_dir)


def _bound_project_dir() -> str:
    project_dir = get_path_manager().project_dir
    if not project_dir:
        raise HTTPException(status_code=409, detail="This server is not bound to a project.")
    return str(project_dir)


@router.post(
    "/api/project/init",
    status_code=201,
    summary="Initialize this project's layout",
)
def init_project(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{}`` -> ``JobStatus`` for the ``project_init`` job.

    ``body`` is optional and ignored -- unlike most job-submit routes this one
    has no meaningful ``subject_ids`` (project init runs once, before any
    subject exists). The example subject is ``POST /api/project/example-subject``.
    """
    del body
    try:
        from tit.jobs import api as jobs_api
    except ImportError as exc:  # pragma: no cover - tit.jobs is always importable
        raise HTTPException(
            status_code=503, detail=f"tit.jobs unavailable: {exc}"
        ) from exc
    try:
        return jobs_api.submit(
            {
                "kind": "project_init",
                "config": {},
                "subject_ids": [],
                "created_by": "gui",
            }
        )
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/project/example-subject",
    status_code=201,
    summary="Download the SimNIBS example subject (ernie, with head model) into this project",
)
def add_example_subject(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{force?}`` -> ``JobStatus`` for a ``project_init`` job that runs
    :func:`tit.examples.fetch_ernie` (~1 GB download, skipped when ``m2m_ernie`` exists)."""
    force = bool((body or {}).get("force", False))
    try:
        from tit.jobs import api as jobs_api
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"tit.jobs unavailable: {exc}") from exc
    try:
        return jobs_api.submit(
            {
                "kind": "project_init",
                "config": {"example_subject": True, "force": force},
                "subject_ids": [],
                "created_by": "gui",
            }
        )
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
