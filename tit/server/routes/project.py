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
from typing import Any

from fastapi import APIRouter, HTTPException

from tit.paths import get_path_manager
from tit.server.host_path import host_project_dir
from tit.server.schemas import Project

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


@router.post(
    "/api/project/init",
    status_code=201,
    summary="Initialize this project's layout, optionally seeded with example data",
)
def init_project(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{example_data?}`` -> ``JobStatus`` for the ``project_init`` job.

    ``body`` is optional (an empty POST means "just initialize, no example
    data") -- unlike most job-submit routes this one has no meaningful
    ``subject_ids`` (project init runs once, before any subject exists).
    """
    example_data = bool((body or {}).get("example_data", False))
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
                "config": {"example_data": example_data},
                "subject_ids": [],
                "created_by": "gui",
            }
        )
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
