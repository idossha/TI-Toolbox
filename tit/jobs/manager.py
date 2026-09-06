"""``JobManager`` — the in-process job engine (TODO.md §2.3–2.5).

Owns a private background thread running its own ``asyncio`` event loop (independent of
whatever loop ``tit.server`` itself runs requests on), so spawning/awaiting subprocesses never
depends on the request lifecycle of any particular HTTP call. Public methods are synchronous and
thread-safe (a single ``RLock`` guards the shared job table); everything async (subprocess
spawn/wait, event tailing, termination) happens on the manager's own loop.

Testing this directly (construct a ``JobManager`` pointed at a ``tmp_path`` with a fake runner,
call its synchronous methods, poll ``get()`` for state changes, ``shutdown()`` at teardown) needs
no asyncio test plugin — see ``tests/test_jobs_manager.py`` / ``tests/fake_runner.py``.
"""

from __future__ import annotations

import os

import asyncio
import contextlib
import logging
import queue
import threading
import time
from typing import Any

import psutil

from tit.jobs import kinds, locks, scheduler
from tit.jobs.bindings import merge_pipeline_bindings
from tit.jobs.costs import default_cost
from tit.jobs.registry import (
    JobRegistry,
    _atomic_write_json,
    events_path,
    job_dir,
    spec_path,
    stdout_path,
)
from tit.jobs.runner import (
    LocalPopenRunner,
    Runner,
    RunRequest,
    cpu_percent_and_rss,
    is_alive,
    runner_env,
    stop_docker_siblings,
    terminate_tree,
)
from tit.jobs.spec import (
    JOB_KINDS,
    Artifact,
    Cost,
    JobError,
    JobProgress,
    JobSpec,
    JobStatus,
    PlannedJob,
    new_job_id,
    utcnow_iso,
)
from tit.jobs.tailer import EventTailer, read_events

logger = logging.getLogger(__name__)

STALL_THRESHOLD_S = 45.0
STALL_CPU_PERCENT = 2.0
LOG_TAIL_ON_FAILURE = 20
SUBSCRIBER_QUEUE_MAXSIZE = 10_000
#: The single line a cancelled job's log ends with (see ``JobManager._append_cancel_note``).
CANCEL_NOTE = "cancelled by user"


class JobManager:
    def __init__(
        self,
        project_dir: str,
        *,
        runner: Runner | None = None,
        runner_cwd: str | None = None,
        poll_interval: float = 0.25,
        budget: Cost | None = None,
        command_for: Any = None,
    ) -> None:
        self.project_dir = project_dir
        self.runner = runner or LocalPopenRunner()
        self.runner_cwd = runner_cwd or project_dir
        self._command_for = command_for or kinds.command_for
        self.poll_interval = poll_interval
        self.registry = JobRegistry(project_dir)
        self._budget = budget or scheduler.discover_budget()

        self._lock = threading.RLock()
        self._specs: dict[str, JobSpec] = {}
        self._status: dict[str, JobStatus] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._tailers: dict[str, EventTailer] = {}
        self._last_event_ts: dict[str, float] = {}
        self._last_exit_code: dict[str, int] = {}
        self._cancelled: set[str] = set()
        self._reattached: set[str] = set()

        self._status_subs: list[queue.Queue[dict[str, Any]]] = []
        self._event_subs: dict[str, list[queue.Queue[dict[str, Any]]]] = {}

        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task | None = None
        self._thread: threading.Thread | None = None
        self._started = False

    # -- lifecycle --------------------------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._load_existing()
        locks.reconcile(self.project_dir)
        self.registry.prune()
        self._thread = threading.Thread(
            target=self._run_loop, name="tit-job-manager", daemon=True
        )
        self._thread.start()
        for _ in range(400):
            if self._loop is not None:
                return
            time.sleep(0.005)
        raise RuntimeError("JobManager background loop failed to start")

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._main_task = loop.create_task(self._main())
        try:
            loop.run_until_complete(self._main_task)
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()

    async def _main(self) -> None:
        await self._reattach_all()
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("job manager tick failed")
            await asyncio.sleep(self.poll_interval)

    def shutdown(self, timeout: float = 5.0) -> None:
        if self._loop is None:
            return

        def _cancel() -> None:
            if self._main_task is not None and not self._main_task.done():
                self._main_task.cancel()

        self._loop.call_soon_threadsafe(_cancel)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._started = False
        self._loop = None

    def _load_existing(self) -> None:
        for job_id in self.registry.list_ids():
            spec = self.registry.read_spec(job_id)
            status = self.registry.read_status(job_id)
            if spec is None or status is None:
                continue
            self._specs[job_id] = spec
            self._status[job_id] = status

    async def _reattach_all(self) -> None:
        for job_id, status in list(self._status.items()):
            if status.state != "running":
                continue
            # ra_14 finding #5: a "running" status.json with no create_time can't be verified
            # as the same process this server actually spawned (create_time is what is_alive()
            # uses to rule out pid reuse) -- treat it as lost rather than re-attaching to
            # whatever unrelated process now happens to hold that pid (including this server's
            # own pid, or pid 1, which is_alive() also refuses on its own).
            if (
                status.pid is not None
                and status.create_time is not None
                and is_alive(status.pid, status.create_time)
            ):
                self._reattached.add(job_id)
                self._tailers[job_id] = EventTailer(
                    events_path(self.project_dir, job_id),
                    start_seq=_next_seq_for(events_path(self.project_dir, job_id)),
                )
                logger.info("re-attached running job %s (pid %s)", job_id, status.pid)
            else:
                self._finalize_reattached_gone(job_id, status)

    def _finalize_reattached_gone(self, job_id: str, status: JobStatus) -> None:
        """The process a re-attached "running" job pointed to is gone (crashed, OOM-killed, or
        the pid was reused) -- decide succeeded/failed/lost from whatever ``events.jsonl`` the
        process managed to write before dying, primarily its ``exit`` event's ``code``
        (``contracts/events.schema.json``).
        """
        events = read_events(events_path(self.project_dir, job_id))
        with self._lock:
            if events:
                # `events` is the job's *entire* events.jsonl from seq 0 (not just what's new
                # since some prior poll), so rebuild `artifacts` from scratch rather than
                # appending onto whatever a live-running poll already persisted before the
                # server went away -- otherwise an "artifact" event already applied once would
                # be double-counted here.
                status.artifacts = []
                self._apply_events(job_id, status, events)
            exit_code = self._last_exit_code.pop(job_id, None)
            if exit_code is not None:
                state = "succeeded" if exit_code == 0 else "failed"
                error = (
                    None
                    if state == "succeeded"
                    else self._build_error(job_id, exit_code)
                )
            elif any(e.get("type") == "exit" for e in events):
                # An "exit" event was written but without a valid integer `code` (the schema
                # requires one, but be defensive against a malformed/older-shape line): fall
                # back to whether a "result" event was also recorded.
                saw_result = any(e.get("type") == "result" for e in events)
                state = "succeeded" if saw_result else "failed"
                error = (
                    None
                    if state == "succeeded"
                    else JobError(
                        type="runner_failed",
                        message="process exited; no result event recorded",
                        last_lines=self._log_tail(job_id),
                    )
                )
            else:
                state = "lost"
                error = JobError(
                    type="lost",
                    message="server restarted while this job was running and no exit "
                    "event was recorded; it may still be running under another pid, "
                    "or it crashed",
                    last_lines=self._log_tail(job_id),
                )
            status.state = state
            status.exit_code = exit_code
            status.error = error
            status.finished_at = status.finished_at or utcnow_iso()
            status.pid = None
            status.liveness = None
            self._tailers.pop(job_id, None)
            self._last_event_ts.pop(job_id, None)
            self._persist_status(status)

    # -- submission ---------------------------------------------------------------------------

    def submit(
        self,
        kind: str,
        config: dict[str, Any],
        subject_ids: list[str],
        *,
        after: list[str] | None = None,
        tags: list[str] | None = None,
        env: dict[str, str] | None = None,
        created_by: str = "api",
        group_id: str | None = None,
        group_cap: int | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        if kind not in JOB_KINDS:
            raise ValueError(
                f"unknown job kind: {kind!r} (expected one of {JOB_KINDS})"
            )
        job_id = new_job_id()
        cost = default_cost(kind, config)
        lock_requests = locks.keys_for(kind, subject_ids, config)
        spec = JobSpec(
            id=job_id,
            kind=kind,
            config=config,
            subject_ids=list(subject_ids),
            after=list(after or []),
            tags=list(tags or []),
            env=dict(env or {}),
            locks=[r.key for r in lock_requests],
            cost=cost,
            created_by=created_by,
            group_id=group_id,
            group_cap=group_cap,
            overwrite=overwrite,
        )
        status = JobStatus.queued(spec)
        with self._lock:
            self._specs[job_id] = spec
            self._status[job_id] = status
            self.registry.create(spec, status)
        self._publish_status(status)
        return status.to_api(self.project_dir)

    def submit_plan(
        self,
        planned: list[PlannedJob],
        *,
        created_by: str = "api",
        group_cap: int | None = None,
    ) -> dict[str, Any]:
        """Submit a labelled DAG of :class:`PlannedJob` (``tit.jobs.plans.plan_preprocessing``)
        under one shared ``group_id``, resolving ``after_labels`` to real job ids.

        *group_cap* (``JobGroupRequest.parallel_subjects``) is stamped onto every job in the
        group as ``JobSpec.group_cap``; :func:`tit.jobs.scheduler.evaluate` enforces it as an
        admission cap on how many of the group's jobs may be ``running`` at once.
        """
        group_id = new_job_id()
        label_to_id: dict[str, str] = {}
        submitted: list[dict[str, Any]] = []
        # Labels must be defined before they're referenced (plan_preprocessing emits them in
        # dependency order); resolve what we can, ignore an unknown label defensively.
        for job in planned:
            after_ids = [
                label_to_id[lbl] for lbl in job.after_labels if lbl in label_to_id
            ]
            status = self.submit(
                job.kind,
                job.config,
                job.subject_ids,
                after=after_ids,
                tags=job.tags,
                created_by=created_by,
                group_id=group_id,
                group_cap=group_cap,
                overwrite=job.overwrite,
            )
            label_to_id[job.label] = status["id"]
            submitted.append(status)
        return {"group_id": group_id, "jobs": submitted}

    # -- reads ----------------------------------------------------------------------------------

    def list_jobs(
        self,
        *,
        state: str | None = None,
        subject: str | None = None,
        kind: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            statuses = list(self._status.values())
        statuses.sort(key=lambda s: s.created_at, reverse=True)
        if state is not None:
            statuses = [s for s in statuses if s.state == state]
        if kind is not None:
            statuses = [s for s in statuses if s.kind == kind]
        if subject is not None:
            statuses = [s for s in statuses if subject in s.subject_ids]
        if limit is not None:
            statuses = statuses[:limit]
        return [s.to_api(self.project_dir) for s in statuses]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            status = self._status.get(job_id)
            return status.to_api(self.project_dir) if status else None

    def get_detail(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            spec = self._specs.get(job_id)
            status = self._status.get(job_id)
        if spec is None or status is None:
            return None
        api_status = status.to_api(self.project_dir)
        return {
            "spec": spec.to_api(),
            "status": api_status,
            "artifacts": api_status["artifacts"],
        }

    def get_events(self, job_id: str, since: int = 0) -> list[dict[str, Any]] | None:
        with self._lock:
            if job_id not in self._specs:
                return None
        return read_events(events_path(self.project_dir, job_id), since=since)

    def get_log(self, job_id: str, tail: int | None = None) -> str | None:
        with self._lock:
            if job_id not in self._specs:
                return None
        return self.registry.read_log_tail(job_id, tail=tail)

    def _log_tail(self, job_id: str, n: int = LOG_TAIL_ON_FAILURE) -> list[str]:
        text = self.registry.read_log_tail(job_id, tail=n)
        return text.splitlines()

    # -- lock conflicts (for tit.jobs.api / plan routes) -----------------------------------------

    def lock_conflicts(self, keys: list[str]) -> list[dict[str, Any]]:
        requests = [locks.parse_key(k) for k in keys]
        current = locks.holders(self.project_dir)
        blocking = locks.match_conflicts(requests, current)
        out: list[dict[str, Any]] = []
        for holder in blocking:
            job_id = holder["job_id"]
            with self._lock:
                status = self._status.get(job_id)
                spec = self._specs.get(job_id)
            out.append(
                {
                    "key": holder.get("key", holder.get("resource", "?")),
                    "held_by": job_id,
                    "kind": status.kind if status else "tools",
                    "subject": (
                        spec.subject_ids[0] if spec and spec.subject_ids else ""
                    ),
                    "started_at": (
                        status.started_at
                        if status and status.started_at
                        else utcnow_iso()
                    ),
                }
            )
        return out

    # -- cancel / rerun / force / delete ---------------------------------------------------------

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            status = self._status.get(job_id)
            if status is None:
                return None
            if status.state == "queued":
                status.state = "cancelled"
                status.finished_at = utcnow_iso()
                self._persist_status(status)
                self._publish_status(status)
                return status.to_api(self.project_dir)
            if status.state != "running":
                return status.to_api(self.project_dir)
            self._cancelled.add(job_id)
            pid, create_time = status.pid, status.create_time

        if self._loop is not None and pid is not None:
            future = asyncio.run_coroutine_threadsafe(
                self._cancel_running(job_id, pid, create_time), self._loop
            )
            try:
                future.result(timeout=20.0)
            except Exception:
                logger.exception("job %s: cancellation coroutine failed", job_id)
        with self._lock:
            return self._status[job_id].to_api(self.project_dir)

    async def _cancel_running(
        self, job_id: str, pid: int, create_time: float | None
    ) -> None:
        await terminate_tree(pid, create_time)
        await stop_docker_siblings(job_id)
        self._append_cancel_note(job_id)
        with self._lock:
            status = self._status.get(job_id)
            if status is not None and status.state == "running":
                # The exit-watcher task normally finalizes; if it hasn't yet (or this job was
                # re-attached and has no such task), finalize here so cancel() never hangs.
                self._finalize_locked(
                    status, state="cancelled", exit_code=None, error=None
                )

    def _append_cancel_note(self, job_id: str) -> None:
        """Close a cancelled job's log with one line saying what happened.

        A cancelled job's last log line used to be whatever the runner happened to be printing
        when SIGTERM landed -- and, before ``tit.jobs.runner``'s ``PETSC_OPTIONS`` fix, PETSc's
        ten-line "Caught signal number 15 / MPI_Abort" block, which reads as a crash even for a
        job that runs no solver. The runner cannot write this line itself: SIGTERM's default
        disposition ends it without running any Python, and giving every runner a handler that
        prints first would mean a handler per runner package *and* a race with a solver that is
        deep in C code when the signal arrives. The manager can, and it knows something the
        runner does not: that the process is *gone* (this is called after ``terminate_tree``
        returns), so nothing can write after the line.

        Best-effort by design: a job whose log was already deleted, or an unwritable file, must
        never turn a successful cancel into an error.
        """
        try:
            with open(
                stdout_path(self.project_dir, job_id), "a", encoding="utf-8"
            ) as fh:
                fh.write(f"{CANCEL_NOTE}\n")
        except OSError as exc:
            logger.debug("job %s: could not append the cancel note: %s", job_id, exc)

    def rerun(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            spec = self._specs.get(job_id)
        if spec is None:
            return None
        return self.submit(
            spec.kind,
            spec.config,
            spec.subject_ids,
            tags=spec.tags,
            created_by=spec.created_by,
            overwrite=spec.overwrite,
        )

    def force(self, job_id: str) -> dict[str, Any] | None:
        """Force a stuck/lost job straight to a terminal state without waiting on its process
        (the OpenAPI contract's semantics for ``POST /api/jobs/{id}/force`` — a recovery escape
        hatch, distinct from "skip lock waits").
        """
        with self._lock:
            status = self._status.get(job_id)
            if status is None:
                return None
            if status.state not in ("running", "lost", "queued"):
                return status.to_api(self.project_dir)
            pid = status.pid
            self._cancelled.add(job_id)
            state = "lost" if status.state != "queued" else "cancelled"
            self._finalize_locked(
                status,
                state=state,
                exit_code=None,
                error=JobError(
                    type="forced",
                    message="forced to a terminal state by the user without waiting for the process",
                    last_lines=self._log_tail(job_id),
                ),
            )
        locks.release_job(self.project_dir, job_id)
        if pid is not None and self._loop is not None:
            # Best-effort, fire-and-forget: still try to actually stop it in the background.
            asyncio.run_coroutine_threadsafe(terminate_tree(pid), self._loop)
        with self._lock:
            return self._status[job_id].to_api(self.project_dir)

    def delete(self, job_id: str) -> str:
        """Returns ``"deleted"``, ``"not_found"``, or ``"not_terminal"``."""
        from tit.jobs.spec import TERMINAL_STATES

        with self._lock:
            status = self._status.get(job_id)
            if status is None:
                return "not_found"
            if status.state not in TERMINAL_STATES:
                return "not_terminal"
            del self._status[job_id]
            self._specs.pop(job_id, None)
            self._tailers.pop(job_id, None)
            self._event_subs.pop(job_id, None)
        self.registry.delete(job_id)
        return "deleted"

    # -- pub/sub (for /ws/jobs) -------------------------------------------------------------------

    def subscribe_status(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=SUBSCRIBER_QUEUE_MAXSIZE)
        with self._lock:
            self._status_subs.append(q)
        return q

    def unsubscribe_status(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if q in self._status_subs:
                self._status_subs.remove(q)

    def subscribe_events(
        self, job_id: str, since: int = 0
    ) -> queue.Queue[dict[str, Any]]:
        """A queue pre-loaded with backlog events since *since*, then fed live ones."""
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=SUBSCRIBER_QUEUE_MAXSIZE)
        with self._lock:
            for event in read_events(
                events_path(self.project_dir, job_id), since=since
            ):
                q.put(event)
            self._event_subs.setdefault(job_id, []).append(q)
        return q

    def unsubscribe_events(self, job_id: str, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            subs = self._event_subs.get(job_id)
            if subs and q in subs:
                subs.remove(q)

    def _publish_status(self, status: JobStatus) -> None:
        payload = status.to_api(self.project_dir)
        with self._lock:
            subs = list(self._status_subs)
        for q in subs:
            # A full or otherwise broken subscriber queue (slow/gone WS client) must never
            # stall a job — it just misses events.
            with contextlib.suppress(Exception):
                q.put_nowait(payload)

    def _publish_event(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._event_subs.get(job_id, ()))
        for q in subs:
            with contextlib.suppress(Exception):
                q.put_nowait(event)

    # -- background loop --------------------------------------------------------------------------

    async def _tick(self) -> None:
        with self._lock:
            specs = dict(self._specs)

        for job_id, spec in specs.items():
            status = self._status.get(job_id)
            if status is not None and status.state == "running":
                await self._poll_running(job_id, spec, status)

        running_cost = Cost(0, 0)
        with self._lock:
            for job_id, spec in specs.items():
                status = self._status.get(job_id)
                if status is not None and status.state == "running":
                    running_cost = running_cost + spec.cost
            status_view = dict(self._status)

        current_holders = locks.holders(self.project_dir)
        edges = scheduler.build_after_edges(specs)
        queued_ids = sorted(
            (jid for jid, st in status_view.items() if st.state == "queued"),
            key=lambda jid: specs[jid].created_at if jid in specs else "",
        )
        for job_id in queued_ids:
            status = self._status.get(job_id)
            spec = specs.get(job_id)
            if status is None or spec is None or status.state != "queued":
                continue
            decision = scheduler.evaluate(
                spec,
                status_view,
                current_holders,
                running_cost=running_cost,
                budget=self._budget,
            )
            if decision.skip_reason:
                self._mark_skipped(job_id, decision.skip_reason)
                for dep_id in scheduler.cascade_skip(job_id, status_view, edges):
                    self._mark_skipped(dep_id, f"dependency {job_id} was skipped")
                continue
            status.waiting_on = decision.waiting_on
            status.budget_wait = decision.budget_wait
            if decision.admit:
                await self._admit(spec, status)
                running_cost = running_cost + spec.cost
            else:
                self._persist_status(status)

    def _mark_skipped(self, job_id: str, reason: str) -> None:
        with self._lock:
            status = self._status.get(job_id)
            if status is None or status.state != "queued":
                return
            self._finalize_locked(
                status,
                state="skipped",
                exit_code=None,
                error=JobError(type="skipped", message=reason, last_lines=[]),
            )

    def _runner_config_path(self, spec: JobSpec) -> str:
        """Write the file a pipeline runner reads and return its path.

        Runners (``simnibs_python -m tit.<module> <file>``) expect the *config* JSON that
        ``tit.config_io.write_config_json`` produces for the Qt GUI: the config fields plus
        ``project_dir`` (and ``subject_ids`` for ``tit.pre``), never the job record. ``spec.json``
        stays the job record; ``config.json`` is what the runner gets.
        """
        if spec.kind not in kinds.MODULE_FOR_KIND:
            return spec_path(self.project_dir, spec.id)
        payload: dict[str, Any] = dict(spec.config or {})
        payload["project_dir"] = self.project_dir
        # A pipeline's dynamic binding (an optimizer's montage name, a leadfield path) does not
        # exist when the group is submitted -- only after that edge's `tit.tools.pipeline_resolve`
        # step ran.  The consumer carries the descriptor; this is the moment the value exists,
        # because admission happens after every `after` job finished.  Inert for every other job.
        merge_pipeline_bindings(payload, self.project_dir)
        if spec.kind == "pre" and "subject_ids" not in payload:
            payload["subject_ids"] = list(spec.subject_ids)
        path = os.path.join(job_dir(self.project_dir, spec.id), "config.json")
        _atomic_write_json(path, payload)
        return path

    async def _admit(self, spec: JobSpec, status: JobStatus) -> None:
        try:
            runner_file = self._runner_config_path(spec)
            argv = self._command_for(spec.kind, spec.config, runner_file)
        except Exception as exc:
            with self._lock:
                self._finalize_locked(
                    status,
                    state="failed",
                    exit_code=None,
                    error=JobError(type="kind_error", message=str(exc), last_lines=[]),
                )
            return

        env = runner_env(
            spec.id,
            events_path(self.project_dir, spec.id),
            interface=spec.created_by,
            cpus=spec.cost.cpus,
            kind=spec.kind,
            subject_ids=list(spec.subject_ids),
        )
        env.update(spec.env)
        request = RunRequest(
            job_id=spec.id,
            argv=argv,
            cwd=self.runner_cwd,
            env=env,
            stdout_path=stdout_path(self.project_dir, spec.id),
        )
        try:
            proc = await self.runner.spawn(request)
        except OSError as exc:
            with self._lock:
                self._finalize_locked(
                    status,
                    state="failed",
                    exit_code=None,
                    error=JobError(type="spawn_error", message=str(exc), last_lines=[]),
                )
            return

        with self._lock:
            self._processes[spec.id] = proc
            self._tailers[spec.id] = EventTailer(events_path(self.project_dir, spec.id))
            status.state = "running"
            status.started_at = utcnow_iso()
            status.pid = proc.pid
            try:
                status.create_time = psutil.Process(proc.pid).create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                status.create_time = None
            status.waiting_on = []
            status.budget_wait = None
            status.liveness = "active"
            self._persist_status(status)
        self._publish_status(status)
        assert self._loop is not None
        self._loop.create_task(self._await_exit(spec.id, proc))

    async def _await_exit(self, job_id: str, proc: asyncio.subprocess.Process) -> None:
        try:
            code = await proc.wait()
        except Exception:
            code = None
        with self._lock:
            cancelled = job_id in self._cancelled
            self._processes.pop(job_id, None)
            status = self._status.get(job_id)
            if status is None or status.state != "running":
                return  # already finalized elsewhere (e.g. force())
            if code is None:
                # proc.wait() itself failed (rare) -- fall back to the runner's own "exit"
                # event (contracts/events.schema.json's `code`) as the source of truth for
                # its real exit code.
                self._drain_events(status)
                code = self._last_exit_code.get(job_id)
            if cancelled:
                self._finalize_locked(
                    status, state="cancelled", exit_code=code, error=None
                )
            elif code == 0:
                self._finalize_locked(
                    status, state="succeeded", exit_code=code, error=None
                )
            else:
                self._finalize_locked(
                    status,
                    state="failed",
                    exit_code=code,
                    error=self._build_error(job_id, code),
                )

    def _build_error(self, job_id: str, code: int | None) -> JobError:
        if code is not None and code < 0:
            message = (
                f"terminated by signal {-code} — likely out-of-memory"
                if code == -9
                else (f"terminated by signal {-code}")
            )
        else:
            message = f"exited with code {code}"
        return JobError(
            type="runner_failed", message=message, last_lines=self._log_tail(job_id)
        )

    def _finalize_locked(
        self,
        status: JobStatus,
        *,
        state: str,
        exit_code: int | None,
        error: JobError | None,
    ) -> None:
        """Caller must hold ``self._lock``."""
        self._drain_events(status)
        status.state = state
        status.exit_code = exit_code
        status.error = error
        status.finished_at = status.finished_at or utcnow_iso()
        status.liveness = None
        status.pid = None
        status.waiting_on = []
        status.budget_wait = None
        self._tailers.pop(status.id, None)
        self._last_event_ts.pop(status.id, None)
        self._last_exit_code.pop(status.id, None)
        self._cancelled.discard(status.id)
        self._reattached.discard(status.id)
        self._persist_status(status)
        self._publish_status(status)

    def _drain_events(self, status: JobStatus) -> None:
        tailer = self._tailers.get(status.id)
        if tailer is None:
            return
        events = tailer.poll()
        if events:
            self._apply_events(status.id, status, events)

    async def _poll_running(
        self, job_id: str, spec: JobSpec, status: JobStatus
    ) -> None:
        tailer = self._tailers.get(job_id)
        if tailer is None:
            return
        events = tailer.poll()
        if events:
            with self._lock:
                self._apply_events(job_id, status, events)
        if status.pid is not None:
            cpu, rss = cpu_percent_and_rss(status.pid)
            status.cpu_percent = cpu
            status.rss = rss
            last_ts = self._last_event_ts.get(job_id, time.time())
            stalled = (time.time() - last_ts) > STALL_THRESHOLD_S and (
                cpu or 0.0
            ) < STALL_CPU_PERCENT
            status.liveness = "stalled" if stalled else "active"
        with self._lock:
            self._persist_status(status)

    def _apply_events(
        self, job_id: str, status: JobStatus, events: list[dict[str, Any]]
    ) -> None:
        for event in events:
            self._last_event_ts[job_id] = float(event.get("ts", time.time()))
            self._publish_event(job_id, event)
            etype = event.get("type")
            if etype == "stage":
                status.progress = JobProgress(
                    stage=event.get("stage", ""),
                    i=int(event.get("i") or 0),
                    n=int(event.get("n") or 0),
                    pct=float(event.get("pct") or 0.0),
                )
            elif etype == "progress":
                prior = status.progress
                status.progress = JobProgress(
                    stage=event.get("stage") or (prior.stage if prior else ""),
                    i=int(
                        event.get("i")
                        if event.get("i") is not None
                        else (prior.i if prior else 0)
                    ),
                    n=int(
                        event.get("n")
                        if event.get("n") is not None
                        else (prior.n if prior else 0)
                    ),
                    pct=float(event.get("pct") or 0.0),
                )
            elif etype == "artifact":
                status.artifacts.append(
                    Artifact(
                        path=event.get("path", ""),
                        kind=event.get("kind", "file"),
                        label=event.get("label"),
                    )
                )
            elif etype == "result":
                # `result.artifacts` (contracts/events.schema.json) is the runner's own
                # accumulated *every artifact event seen so far* list, purely for a consumer
                # reading only this one event -- every entry in it already arrived (in order)
                # as its own "artifact" event above, so applying it here too would double the
                # job's artifact list. `result.outputs` (the runner's free-form metrics/paths
                # payload) has no home on JobStatus (contracts/openapi.v1.yaml's JobStatus
                # carries no such field) -- parsed above via the generic event dict, otherwise
                # unused here.
                pass
            elif etype == "exit":
                code = event.get("code")
                if isinstance(code, int) and not isinstance(code, bool):
                    self._last_exit_code[job_id] = code

    def _persist_status(self, status: JobStatus) -> None:
        self.registry.write_status(status)


def _next_seq_for(path: str) -> int:
    from tit.jobs.tailer import line_count

    return line_count(path)
