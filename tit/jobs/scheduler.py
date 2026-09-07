"""Admission logic (TODO.md §2.4): pure decision function plus budget discovery.

``evaluate()`` takes a snapshot of the world (the candidate job, every other job the manager
knows about, currently held locks, and the running/budget cost totals) and returns one
:class:`Decision` — never touches the filesystem or a clock other than what it's handed, so the
"budget fan-out of 4 fake jobs on an 8-cpu budget" and "lock waits with waiting_on" scheduler
tests can drive it directly with synthetic state.

:class:`tit.jobs.manager.JobManager` owns the loop that calls this once per queued job per tick
and acts on the result (spawn, mark skipped, or leave queued with the reported ``waiting_on``/
``budget_wait``).

A ``JobGroupRequest.parallel_subjects`` cap (``POST /api/jobs/groups``) is mirrored onto every
job of a submitted group as ``JobSpec.group_cap`` (:mod:`tit.jobs.manager`); ``evaluate()``
enforces it here by counting *running* jobs sharing that ``group_id`` in *jobs* — no separate
group registry needed, and the count naturally survives a server restart since it's read straight
off each job's live status.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import psutil

from tit.jobs import locks
from tit.jobs.spec import Cost, JobSpec, JobStatus, WaitingOn

logger = logging.getLogger(__name__)

FAILED_LIKE_STATES = frozenset({"failed", "cancelled", "lost", "skipped"})


@dataclass
class Decision:
    admit: bool = False
    waiting_on: list[WaitingOn] = field(default_factory=list)
    budget_wait: str | None = None
    skip_reason: str | None = None


def _dependency_state(job: JobSpec, jobs: dict[str, JobStatus]) -> Decision | None:
    """``None`` when dependencies are satisfied; otherwise the decision to return."""
    if not job.after:
        return None
    pending: list[WaitingOn] = []
    for dep_id in job.after:
        dep = jobs.get(dep_id)
        if dep is None:
            # Never "satisfied": an `after` naming a job that does not exist is either a
            # typo or a dependency that was deleted, and admitting the dependant runs it
            # against a precondition nobody established. Submission rejects unknown ids
            # (JobManager.submit), so reaching here means the record went away after the
            # fact -- recovery from the store included, which is why this is a skip with
            # its own reason rather than a wait for something that will never arrive.
            logger.warning("job %s: dependency %s not found; refusing to run", job.id, dep_id)
            return Decision(skip_reason=f"dependency {dep_id} is unknown")
        if dep.state in FAILED_LIKE_STATES:
            return Decision(skip_reason=f"dependency {dep_id} {dep.state}")
        if dep.state != "succeeded":
            pending.append(WaitingOn(key="after", job_id=dep_id))
    if pending:
        return Decision(waiting_on=pending)
    return None


def evaluate(
    job: JobSpec,
    jobs: dict[str, JobStatus],
    current_holders: list[dict[str, Any]],
    *,
    running_cost: Cost,
    budget: Cost,
) -> Decision:
    """Admission decision for one queued *job* (does not mutate anything)."""
    dep_decision = _dependency_state(job, jobs)
    if dep_decision is not None:
        return dep_decision

    requests = locks.keys_for(job.kind, job.subject_ids, job.config)
    blocking = locks.match_conflicts(requests, current_holders, self_job_id=job.id)
    if blocking:
        waiting_on = [
            WaitingOn(
                key=holder.get("key", holder.get("resource", "?")),
                job_id=holder["job_id"],
            )
            for holder in blocking
        ]
        return Decision(waiting_on=waiting_on)

    if job.group_id and job.group_cap:
        running_in_group = sum(
            1
            for st in jobs.values()
            if st.group_id == job.group_id and st.state == "running"
        )
        if running_in_group >= job.group_cap:
            return Decision(
                budget_wait=(
                    f"waiting for group concurrency: {running_in_group}/"
                    f"{job.group_cap} slots in use for group {job.group_id}"
                )
            )

    projected = running_cost + job.cost
    if job.kind != "viewer" and not projected.fits(budget):
        return Decision(
            budget_wait=(
                f"waiting for budget: need {job.cost.cpus:g} cpu / {job.cost.mem_gb:g} GB, "
                f"{running_cost.cpus:g} cpu / {running_cost.mem_gb:g} GB already running, "
                f"budget is {budget.cpus:g} cpu / {budget.mem_gb:g} GB"
            )
        )

    return Decision(admit=True)


def cascade_skip(
    job_id: str, jobs: dict[str, JobStatus], edges: dict[str, list[str]]
) -> list[str]:
    """Every job (transitively) depending on *job_id* that is still queued, for cascading a
    skip: *edges* maps a job id to the ids of jobs that list it in ``after``.
    """
    skipped: list[str] = []
    frontier = [job_id]
    seen = {job_id}
    while frontier:
        current = frontier.pop()
        for dependant in edges.get(current, []):
            if dependant in seen:
                continue
            seen.add(dependant)
            status = jobs.get(dependant)
            if status is not None and status.state == "queued":
                skipped.append(dependant)
            frontier.append(dependant)
    return skipped


def build_after_edges(specs: dict[str, JobSpec]) -> dict[str, list[str]]:
    """``job_id -> [ids of jobs that name it in their own after list]`` (reverse of ``after``)."""
    edges: dict[str, list[str]] = {}
    for job_id, spec in specs.items():
        for dep_id in spec.after:
            edges.setdefault(dep_id, []).append(job_id)
    return edges


def discover_budget() -> Cost:
    """Container cgroup CPU/RAM limit, clamped by currently-available memory (TODO.md §2.4)."""
    cpus: float
    mem_gb: float
    try:
        from tit.pre.qsi.utils import get_inherited_dood_resources

        cgroup_cpus, cgroup_mem_gb = get_inherited_dood_resources()
        cpus = float(cgroup_cpus)
        mem_gb = float(cgroup_mem_gb)
    except (
        Exception
    ):  # pragma: no cover - defensive; qsi utils is another lane's module
        cpus = float(os.cpu_count() or 1)
        mem_gb = 8.0
    try:
        available_gb = psutil.virtual_memory().available / (1024**3)
        mem_gb = min(mem_gb, available_gb)
    except (psutil.Error, OSError):
        pass
    return Cost(cpus=max(cpus, 1.0), mem_gb=max(mem_gb, 1.0))
