"""``/api/jobs`` and ``/api/jobs/groups`` — thin HTTP wrappers over :mod:`tit.jobs.manager`.

Every rule that decides *whether* a job can run (dependencies, locks, budget) lives in
:mod:`tit.jobs`; this module only translates HTTP into :class:`~tit.jobs.manager.JobManager`
calls, plus the group/DAG seam into :mod:`tit.jobs.plans`. ``/api/jobs/groups`` covers every
per-subject kind (``pre``, ``sim``, ``flex``, ``flex_adaptive``, ``flex_pareto``, ``ex``, ``mex``);
the concurrency cap it carries is enforced by the scheduler, never by client-side POST timing.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from tit.jobs.bootstrap import get_manager
from tit.jobs.config_check import check_job_config
from tit.jobs.manager import JobManager
from tit.jobs.spec import JOB_KINDS, JOB_STATES
from tit.paths import is_valid_subject_id

logger = logging.getLogger(__name__)

router = APIRouter()


def _checked_subject_ids(subject_ids: Any) -> list[str]:
    """*subject_ids* as a list, or an HTTP 422 naming the first one that is not a subject id.

    Enforced here, before the job is persisted: a subject id becomes a path component
    (``sub-<id>``) in every runner downstream, and one carrying a separator or ``..`` used to
    reach outside the project (``tit.paths.validate_subject_id``, which is the same grammar).
    """
    if not isinstance(subject_ids, list):
        raise HTTPException(status_code=422, detail="subject_ids must be an array")
    for sid in subject_ids:
        if not is_valid_subject_id(sid):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"invalid subject id {sid!r}: letters, digits, '_' and '-' only, "
                    f"starting with a letter or digit, at most 64 characters"
                ),
            )
    return list(subject_ids)


def _manager(request: Request) -> JobManager:
    return get_manager(request.app)


@router.get("/api/jobs", summary="List jobs, most recent first")
def list_jobs(
    request: Request,
    state: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
) -> list[dict[str, Any]]:
    if state is not None and state not in JOB_STATES:
        raise HTTPException(status_code=422, detail=f"invalid state: {state!r}")
    if kind is not None and kind not in JOB_KINDS:
        raise HTTPException(status_code=422, detail=f"invalid kind: {kind!r}")
    return _manager(request).list_jobs(
        state=state, subject=subject, kind=kind, limit=limit
    )


@router.post("/api/jobs", status_code=201, summary="Submit one job")
def submit_job(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    kind = body.get("kind")
    if kind not in JOB_KINDS:
        raise HTTPException(
            status_code=422, detail=f"invalid or missing kind: {kind!r}"
        )
    config = body.get("config")
    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config must be an object")
    subject_ids = _checked_subject_ids(body.get("subject_ids"))
    # `/api/jobs/groups` gets this for free: `plan_per_subject` round-trips every generated
    # config through the kind's dataclass. This single-job route did not, so a config the
    # runner cannot deserialise (a `sim` config with no `subject_id`/`montages`) was accepted,
    # written to config.json, and only died minutes later inside `tit/sim/__main__.py`.
    try:
        check_job_config(kind, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return _manager(request).submit(
            kind,
            config,
            subject_ids,
            after=body.get("after"),
            tags=body.get("tags"),
            overwrite=bool(body.get("overwrite", False)),
            created_by="gui",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/api/jobs/groups",
    status_code=201,
    summary="Submit one job per subject with a shared group id and a scheduler-enforced cap",
)
def submit_group(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Submit a per-subject job group (R3).

    ``kind=pre`` expands into ``tit.jobs.plans.plan_preprocessing``'s G1-G6/report DAG;
    ``sim``/``flex``/``flex_adaptive``/``flex_pareto``/``ex``/``mex`` expand into one independent
    job per ``(subject, config)`` entry via ``tit.jobs.plans.plan_per_subject``.

    `parallel_subjects` is required on the wire (JobGroupRequest); it becomes every group job's
    JobSpec.group_cap and is enforced by tit.jobs.scheduler.evaluate() as an admission cap on how
    many of the group's jobs may be "running" at once (see the manager/scheduler docstrings for
    why a job-count cap, not a distinct-subject cap). The client never spaces out its POSTs: the
    whole group is created queued in this one request and released by the scheduler.

    `subject_configs` (optional, additive) carries per-subject resolved configs -- a page whose
    config depends on the subject (an ROI resolved against that subject's atlas, a leadfield
    path) sends one entry per job instead of one template. Entries are matched to
    `subject_ids` by their `subject_id`; a subject with no entry uses `config`. Whatever the
    caller sends, each generated config's `subject_id` is forced to its own subject.
    """
    from tit.jobs.plans import GROUP_KINDS

    kind = body.get("kind")
    if kind not in GROUP_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"kind must be one of {GROUP_KINDS} for a job group, got {kind!r}",
        )
    config = body.get("config")
    if not isinstance(config, dict):
        raise HTTPException(
            status_code=422, detail="config must be an object and subject_ids an array"
        )
    subject_ids = _checked_subject_ids(body.get("subject_ids"))
    parallel_subjects = body.get("parallel_subjects")
    if (
        not isinstance(parallel_subjects, int)
        or isinstance(parallel_subjects, bool)
        or parallel_subjects < 1
    ):
        raise HTTPException(
            status_code=422, detail="parallel_subjects must be an integer >= 1"
        )
    tags = body.get("tags") or []
    if not isinstance(tags, list):
        raise HTTPException(status_code=422, detail="tags must be an array")
    overwrite = bool(body.get("overwrite", False))

    if kind == "pre":
        planned = _plan_pre_group(config, subject_ids)
    else:
        planned = _plan_generic_group(kind, config, subject_ids, body, tags, overwrite)
    return _manager(request).submit_plan(
        planned, created_by="gui", group_cap=parallel_subjects
    )


def _plan_pre_group(config: dict[str, Any], subject_ids: list[str]) -> list[Any]:
    try:
        from tit.jobs.plans import plan_preprocessing
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=(
                "job groups are not available yet: tit.jobs.plans.plan_preprocessing has not "
                "been implemented (Stage 1, B3)"
            ),
        ) from exc

    try:
        from tit.config_io import deserialize_config
        from tit.pre.config import PreprocessConfig

        pre_config = deserialize_config(PreprocessConfig, config)
    except Exception as exc:  # invalid config shape -> 422, not a 500
        raise HTTPException(
            status_code=422, detail=f"invalid PreprocessConfig: {exc}"
        ) from exc

    try:
        return plan_preprocessing(pre_config, subject_ids)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=501, detail=f"job groups are not available yet: {exc}"
        ) from exc


def _plan_generic_group(
    kind: str,
    config: dict[str, Any],
    subject_ids: list[str],
    body: dict[str, Any],
    tags: list[str],
    overwrite: bool,
) -> list[Any]:
    """One job per (subject, config) entry -- see `submit_group`'s `subject_configs` note."""
    from tit.jobs.plans import plan_per_subject

    entries: list[tuple[str, dict[str, Any]]] = []
    raw_entries = body.get("subject_configs")
    if raw_entries is not None and not isinstance(raw_entries, list):
        raise HTTPException(status_code=422, detail="subject_configs must be an array")
    by_subject: dict[str, list[dict[str, Any]]] = {}
    for entry in raw_entries or []:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("subject_id"), str)
            or not isinstance(entry.get("config"), dict)
        ):
            raise HTTPException(
                status_code=422,
                detail="each subject_configs entry needs a subject_id string and a config object",
            )
        by_subject.setdefault(entry["subject_id"], []).append(entry["config"])
    unknown = set(by_subject) - set(subject_ids)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"subject_configs names subjects not in subject_ids: {sorted(unknown)}",
        )
    for subject_id in subject_ids:
        if not isinstance(subject_id, str):
            raise HTTPException(
                status_code=422, detail="subject_ids must be an array of strings"
            )
        for entry_config in by_subject.get(subject_id) or [config]:
            entries.append((subject_id, entry_config))

    try:
        return plan_per_subject(kind, entries, tags=tags, overwrite=overwrite)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        TypeError,
        KeyError,
    ) as exc:  # a config that does not fit the kind's dataclass
        raise HTTPException(
            status_code=422, detail=f"invalid config for kind {kind!r}: {exc}"
        ) from exc


@router.get("/api/jobs/{job_id}", summary="One job's spec, live status, and artifacts")
def get_job(request: Request, job_id: str) -> dict[str, Any]:
    detail = _manager(request).get_detail(job_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return detail


@router.delete(
    "/api/jobs/{job_id}",
    status_code=204,
    summary="Forget a finished job (queued/running jobs must be cancelled first)",
)
def delete_job(request: Request, job_id: str) -> None:
    result = _manager(request).delete(job_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    if result == "not_terminal":
        raise HTTPException(
            status_code=409, detail="job is still queued/running; cancel it first"
        )


@router.get(
    "/api/jobs/{job_id}/events",
    summary="Events since a given sequence number (reconnect/backfill; live tailing uses /ws/jobs)",
)
def get_events(
    request: Request, job_id: str, since: int = Query(default=0, ge=0)
) -> list[dict[str, Any]]:
    events = _manager(request).get_events(job_id, since=since)
    if events is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return events


@router.get(
    "/api/jobs/{job_id}/log",
    response_class=PlainTextResponse,
    summary="Raw stdout/stderr log tail",
)
def get_log(
    request: Request, job_id: str, tail: int | None = Query(default=None, ge=1)
) -> str:
    log = _manager(request).get_log(job_id, tail=tail)
    if log is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return log


@router.post(
    "/api/jobs/{job_id}/cancel",
    summary="Cancel a queued or running job (tree snapshot -> SIGTERM -> SIGKILL)",
)
async def cancel_job(request: Request, job_id: str) -> dict[str, Any]:
    # cancel() blocks up to the SIGTERM grace period; keep it off the request-handling loop.
    status = await run_in_threadpool(_manager(request).cancel, job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return status


@router.post(
    "/api/jobs/{job_id}/rerun",
    status_code=201,
    summary="Submit a new job with the same spec as a finished one",
)
def rerun_job(request: Request, job_id: str) -> dict[str, Any]:
    status = _manager(request).rerun(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return status


@router.post(
    "/api/jobs/{job_id}/force",
    summary="Force a stuck/lost job to a terminal state without waiting for the process",
)
def force_job(request: Request, job_id: str) -> dict[str, Any]:
    status = _manager(request).force(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return status
