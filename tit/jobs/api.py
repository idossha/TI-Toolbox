"""Stable interface between the job manager (owner: B1) and the rest of ``tit.server``.

Other modules (viewers, plan routes) call ONLY these functions; B1 replaces the bodies with the
real implementation without changing the signatures. Shapes follow ``contracts/openapi.v1.yaml``
(``JobStatus``, ``LockConflict``).
"""

from __future__ import annotations

from typing import Any

from tit.jobs.bootstrap import get_manager


def submit(spec: dict[str, Any]) -> dict[str, Any]:
    """Submit one job. ``spec`` = ``{kind, config, subject_ids, after?, tags?, env?, created_by}``.

    Returns the job's ``JobStatus`` dict (state ``queued`` or ``running``).
    """
    manager = get_manager()
    return manager.submit(
        spec["kind"],
        spec.get("config", {}),
        spec.get("subject_ids", []),
        after=spec.get("after"),
        tags=spec.get("tags"),
        env=spec.get("env"),
        created_by=spec.get("created_by", "api"),
        group_id=spec.get("group_id"),
        overwrite=spec.get("overwrite", False),
    )


def lock_conflicts(keys: list[str]) -> list[dict[str, Any]]:
    """Lock keys currently held by other jobs, as ``LockConflict`` dicts (may be empty)."""
    return get_manager().lock_conflicts(keys)


def get_status(job_id: str) -> dict[str, Any] | None:
    """``JobStatus`` for ``job_id`` or ``None`` when unknown."""
    return get_manager().get(job_id)
