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
import functools
import logging
import queue
import threading
import time
from typing import Any

import psutil

from tit.jobs import kinds, locks, scheduler
from tit.jobs.kinds import may_spawn_docker_siblings
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
    stop_docker_siblings_via_engine,
    terminate_tree,
)
from tit.jobs.spec import (
    JOB_KINDS,
    TERMINAL_STATES,
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
from tit.paths import validate_subject_id

logger = logging.getLogger(__name__)

STALL_THRESHOLD_S = 45.0
STALL_CPU_PERCENT = 2.0
LOG_TAIL_ON_FAILURE = 20
SUBSCRIBER_QUEUE_MAXSIZE = 10_000
#: The single line a cancelled job's log ends with (see ``JobManager._append_note``).
#: Upper bound on the whole "stop this job's sibling containers" step during a cancel. Kept well
#: under ``cancel()``'s own 20 s future timeout so a wedged Docker daemon can never be what makes
#: a cancel fail: the job still lands in ``cancelled``, with a warning in the log.
DOCKER_CANCEL_TIMEOUT_S = 3.0

CANCEL_NOTE = "cancelled by user"
#: The single line a job interrupted by a server restart ends with, and the message of its
#: ``JobError`` (see :meth:`JobManager._reconcile_all`).
RESTART_NOTE = "interrupted: server restarted"
#: Same, for a job that was still queued (nothing was ever started, nothing is re-submitted).
RESTART_QUEUED_NOTE = "interrupted before start: server restarted"
#: Upper bound on the whole reconciliation's Docker work, per job. Startup must stay bounded.
DOCKER_RECONCILE_TIMEOUT_S = 3.0
#: How long start() waits for reconciliation before serving requests anyway (see start()).
RECONCILE_STARTUP_TIMEOUT_S = 30.0


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
        # Bound to this manager's project root so a `tools` job's path arguments can be
        # jailed to it (tit.jobs.kinds.check_tool_args). A caller-supplied builder (tests,
        # and only tests) keeps the plain three-argument signature.
        self._command_for = command_for or functools.partial(
            kinds.command_for, project_dir=project_dir
        )
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
        #: Non-terminal jobs found in the store at start(), i.e. left over from a previous
        #: server life -- reconciled once, before the first tick (see _reconcile_all).
        self._stranded: list[str] = []
        #: Set once _reconcile_all() has finished; start() waits on it (see start()).
        self._reconciled = threading.Event()

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
                break
            time.sleep(0.005)
        else:
            raise RuntimeError("JobManager background loop failed to start")
        # Block the caller (tit.server's startup) until startup reconciliation has finished, so
        # no request can ever observe a stranded job from the previous server life as "running".
        # Bounded: a wedged Docker daemon or an unkillable process must not stop the server from
        # coming up -- reconciliation keeps going on the manager's own loop either way.
        if not self._reconciled.wait(timeout=RECONCILE_STARTUP_TIMEOUT_S):
            logger.warning(
                "startup reconciliation is still running after %.0fs; serving anyway",
                RECONCILE_STARTUP_TIMEOUT_S,
            )

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
        try:
            await self._reconcile_all()
        finally:
            self._reconciled.set()
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
            if status.state not in TERMINAL_STATES:
                # Snapshot taken *before* the manager's loop thread starts, so a job submitted
                # by this server life can never be swept up by startup reconciliation.
                self._stranded.append(job_id)

    async def _reconcile_all(self) -> None:
        """Startup reconciliation: a server restart must not leave jobs running (maintainer,
        Sep 2026: *"a restart should not automatically keep running jobs"*).

        This replaces the older re-attach behaviour, which adopted a still-live runner pid from
        the previous server life. Re-attaching left three bad states observed live: the store
        said ``running`` while nothing watched the process, the rail spun forever, and ``cancel``
        did nothing — while a leftover subprocess tree or QSIPrep/QSIRecon sibling container kept
        burning the machine unattended. So instead, for every non-terminal job:

        * ``running`` with a pid that is *still alive and still the same process* (create_time
          match — :func:`tit.jobs.runner.is_alive` is what rules out pid reuse, and refuses pid 1
          and this server's own pid outright): SIGTERM → SIGKILL its whole tree, ``docker stop``
          any container carrying its ``tit.job_id`` label (bounded, Engine API, never the CLI),
          then finalize it ``failed``.
        * ``running`` whose process is gone: finalized from its own ``events.jsonl`` when that
          records a real ``exit`` (a job that genuinely finished while the server was down is
          still reported ``succeeded``/``failed`` with its true exit code) — otherwise ``failed``
          with the same "interrupted" reason. Sibling containers are stopped either way: a
          container can outlive the runner that started it.
        * ``queued``: ``failed`` with "interrupted before start". Nothing is ever re-submitted
          automatically; re-running is the user's call.

        Runs on the manager's loop before the first tick, i.e. before the server accepts
        requests, and every transition is persisted *and* published so open clients update.
        """
        stranded, self._stranded = self._stranded, []
        for job_id in stranded:
            status = self._status.get(job_id)
            if status is None:
                continue
            try:
                if status.state == "queued":
                    self._finalize_interrupted(
                        job_id, status, note=RESTART_QUEUED_NOTE, use_events=False
                    )
                elif status.state == "running":
                    await self._reconcile_running(job_id, status)
            except Exception:
                logger.exception("job %s: startup reconciliation failed", job_id)

    async def _reconcile_running(self, job_id: str, status: JobStatus) -> None:
        pid, create_time = status.pid, status.create_time
        terminated = False
        if pid is not None and create_time is not None and is_alive(pid, create_time):
            terminated = True
            logger.warning(
                "job %s: runner pid %s outlived the previous server; terminating it", job_id, pid
            )
            await terminate_tree(pid, create_time)
        if may_spawn_docker_siblings(
            self._specs[job_id].kind if job_id in self._specs else status.kind,
            self._specs[job_id].config if job_id in self._specs else None,
        ):
            await stop_docker_siblings_via_engine(
                job_id, timeout_s=DOCKER_RECONCILE_TIMEOUT_S
            )
        self._finalize_interrupted(
            job_id, status, note=RESTART_NOTE, use_events=True, trust_exit=not terminated
        )

    def _finalize_interrupted(
        self,
        job_id: str,
        status: JobStatus,
        *,
        note: str,
        use_events: bool,
        trust_exit: bool = True,
    ) -> None:
        """Land one non-terminal job in a terminal state after a restart.

        With *use_events*, the job's whole ``events.jsonl`` is replayed first: artifacts recorded
        before the server went away are recovered, and a recorded ``exit`` still decides
        succeeded/failed with its real code (``contracts/events.schema.json``). ``events`` is the
        file from seq 0, not a delta, so ``artifacts`` is rebuilt from scratch rather than
        appended onto whatever a live poll persisted earlier.

        *trust_exit* is ``False`` when reconciliation itself killed the runner: the ``exit``
        event it managed to write on the way down (``terminated by signal 15``) describes our
        own SIGTERM, not the job's outcome, so the reason must stay "interrupted".
        """
        self._append_note(job_id, note)
        state, exit_code, error = "failed", None, None
        with self._lock:
            if use_events:
                events = read_events(events_path(self.project_dir, job_id))
                if events:
                    status.artifacts = []
                    self._apply_events(job_id, status, events)
                exit_code = self._last_exit_code.get(job_id) if trust_exit else None
                if exit_code is not None:
                    state = "succeeded" if exit_code == 0 else "failed"
                    error = (
                        None
                        if state == "succeeded"
                        else self._build_error(job_id, exit_code)
                    )
                elif trust_exit and any(e.get("type") == "exit" for e in events):
                    # An "exit" event without a usable integer `code` (the schema requires one;
                    # be defensive about older/malformed lines): fall back to whether a "result"
                    # event was recorded too.
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
            if error is None and state == "failed":
                # `lost` is the existing taxonomy value for "the server restarted mid-run"
                # (`desktop/.../jobs-rail/format.ts::ERROR_LABEL`); the state is `failed`
                # because the job is over and will not resume -- see JobState in
                # contracts/openapi.yaml, which has no `interrupted` member.
                error = JobError(
                    type="lost", message=note, last_lines=self._log_tail(job_id)
                )
            self._finalize_locked(
                status, state=state, exit_code=exit_code, error=error
            )
        locks.release_job(self.project_dir, job_id)

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
        for sid in subject_ids or []:
            # Defence in depth behind the route's own check: a subject id becomes a
            # `sub-<id>` path component in every runner this job spawns.
            validate_subject_id(sid)
        with self._lock:
            unknown = [dep for dep in (after or []) if dep not in self._specs]
        if unknown:
            # RUN-04: an `after` naming a job that does not exist used to be treated as
            # satisfied, so a typo'd dependency ran immediately and unordered. Caught here,
            # before anything is persisted, so the caller gets a 422 rather than a job that
            # quietly ignores its own precondition.
            raise ValueError(
                f"unknown job id in 'after': {', '.join(sorted(unknown))}"
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
            if status.state not in TERMINAL_STATES:
                # Snapshot taken *before* the manager's loop thread starts, so a job submitted
                # by this server life can never be swept up by startup reconciliation.
                self._stranded.append(job_id)
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
        # The runner process is signalled first and unconditionally: whatever Docker is doing
        # (including nothing at all, on a wedged daemon), a cancel must always end the job.
        await terminate_tree(pid, create_time)
        await self._stop_docker_siblings_if_any(job_id)
        self._append_note(job_id, CANCEL_NOTE)
        with self._lock:
            status = self._status.get(job_id)
            if status is not None and status.state == "running":
                # The exit-watcher task normally finalizes; if it hasn't yet (or this job was
                # re-attached and has no such task), finalize here so cancel() never hangs.
                self._finalize_locked(
                    status, state="cancelled", exit_code=None, error=None
                )

    async def _stop_docker_siblings_if_any(self, job_id: str) -> None:
        """``docker stop`` this job's sibling containers -- only when it could have any.

        Two guards, both learned from a wedged Docker daemon on a developer machine: a `docker
        ps` against an unresponsive socket blocks forever, which used to hang *every* cancel,
        including a ``tools`` job that never went near Docker. So (1) only job kinds that spawn
        siblings (the DWI stages of ``pre`` -- QSIPrep/QSIRecon/DTI, the only code paths that
        ``docker run`` anything) ask Docker at all, and (2) that ask is bounded, degrading to a
        logged warning rather than a stuck job.
        """
        with self._lock:
            status = self._status.get(job_id)
            spec = self._specs.get(job_id)
        kind = spec.kind if spec is not None else (status.kind if status else None)
        config = spec.config if spec is not None else None
        if not may_spawn_docker_siblings(kind, config):
            return
        try:
            await asyncio.wait_for(
                stop_docker_siblings(job_id), timeout=DOCKER_CANCEL_TIMEOUT_S
            )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning(
                "job %s: could not reach Docker to stop sibling containers within %.1fs; "
                "cancelling anyway",
                job_id,
                DOCKER_CANCEL_TIMEOUT_S,
            )
        except Exception:
            logger.warning(
                "job %s: could not reach Docker to stop sibling containers",
                job_id,
                exc_info=True,
            )

    def _append_note(self, job_id: str, note: str) -> None:
        """Close a job's log with one line saying what happened to it (a cancel, or a server
        restart that interrupted it).

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
                fh.write(f"{note}\n")
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
        # RUN-03: an admitted job holds its locks from the instant it is admitted, not from
        # whenever its runner process gets around to `locks.hold`. Without these reservations
        # a second job needing the same exclusive resource was admitted in the very same tick
        # (the on-disk snapshot is taken once) or in the next one (the runner had not started
        # yet), and two writers then shared one subject.
        for other_id, other in specs.items():
            other_status = self._status.get(other_id)
            if other_status is not None and other_status.state == "running":
                current_holders.extend(self._reserved_holders(other))
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
                if status.state == "running":
                    # Same tick, next candidate: it must see this job's locks. A spawn that
                    # failed leaves the status terminal, so its reservation is never taken.
                    current_holders.extend(self._reserved_holders(spec))
                running_cost = running_cost + spec.cost
            else:
                self._persist_status(status)

    def _reserved_holders(self, spec: JobSpec) -> list[dict[str, Any]]:
        """*spec*'s locks as holder descriptors, for a job that is running but whose runner
        may not have written its own descriptors yet (see the RUN-03 note in ``_tick``).

        Built from ``spec.locks`` — the keys recorded at submission — so this and the runner's
        own ``locks.hold`` always request the same set. Duplicates against the on-disk holders
        are harmless: ``match_conflicts`` de-duplicates by job id and skips the candidate's own.
        """
        descriptors: list[dict[str, Any]] = []
        for key in spec.locks:
            request = locks.parse_key(key)
            descriptors.append(
                {
                    "key": request.key,
                    "resource": request.resource,
                    "mode": request.mode,
                    "job_id": spec.id,
                    "reserved": True,
                }
            )
        return descriptors

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
                # payload) has no home on JobStatus (contracts/openapi.yaml's JobStatus
                # carries no such field) -- parsed above via the generic event dict, otherwise
                # unused here.
                pass
            elif etype == "exit":
                code = event.get("code")
                if isinstance(code, int) and not isinstance(code, bool):
                    self._last_exit_code[job_id] = code

    def _persist_status(self, status: JobStatus) -> None:
        self.registry.write_status(status)
