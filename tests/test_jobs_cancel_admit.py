"""A job cancelled (or forced) while it is being admitted stays terminal, and its process dies.

What this pins (2026-10-22, package p18 "cancel-admit-race"): ``JobManager._admit`` awaits
``runner.spawn`` without holding the manager lock. A ``cancel()`` or ``force()`` that lands in
that window finalizes the still-``queued`` job as ``cancelled`` -- and then, before this fix,
``_admit`` resumed, overwrote the state with ``running``, and the job ended ``succeeded`` with
``finished_at`` earlier than ``started_at``, its process left to run to completion.

Where the expected values come from: ``contracts/openapi.yaml`` (``POST /api/jobs/{id}/cancel``:
a cancelled job never runs; ``force``: a recovery hatch that lands the job in a terminal state),
plain time ordering (a job cannot finish before it starts), and the manager's two cancel
promises that ``tests/test_jobs_manager.py`` already holds a running job to: the log of a
cancelled job ends with ``CANCEL_NOTE``, and a stopped job holds no lock. No number here comes
from the code under test.

How the window is made deterministic: a ``LocalPopenRunner`` subclass sets an event on entry to
``spawn()`` and then awaits ``asyncio.sleep(0.5)`` before really spawning, so a ``cancel()``
issued after the event is guaranteed to land while ``_admit`` is suspended. The spawned command
sleeps 60 s, so "the pid is dead within 10 s" can only be true if the manager killed it.

The lock: right after the real spawn, the runner registers a lock for the job (``locks.hold``),
as a runner process does when it starts -- after ``force()`` has already released the job's
locks. The descriptor names a live process (a separate sleeper the fixture owns), so the lazy
clean-up of dead holders can never remove it: only the manager's explicit release can.

Run: ``python -m pytest tests/test_jobs_cancel_admit.py -q -p no:cacheprovider``.
Deliberately elsewhere: cancel of a *running* job (``tests/test_jobs_manager.py``).
"""

from __future__ import annotations

import asyncio
import contextlib
import queue
import subprocess
import sys
import threading
import time

import psutil
import pytest

from tit.jobs import locks
from tit.jobs.manager import CANCEL_NOTE, JobManager
from tit.jobs.registry import JobRegistry
from tit.jobs.runner import LocalPopenRunner
from tit.jobs.spec import Cost

#: Long enough that the process can only be gone within the test's 10 s bound if it was killed.
LONG_SLEEP_ARGV = [sys.executable, "-c", "import time; time.sleep(60)"]
SHORT_SLEEP_ARGV = [sys.executable, "-c", "import time; time.sleep(0.2)"]


#: The lock the runner takes for its job once spawned.
RUNNER_LOCK = locks.LockRequest(resource="subject:p18:m2m", mode="write")


class SlowSpawnRunner(LocalPopenRunner):
    """Holds ``_admit`` inside ``spawn()`` for 0.5 s before the real spawn, then takes a lock."""

    def __init__(self, project_dir: str, holder_pid: int) -> None:
        self.project_dir = project_dir
        self.holder_pid = holder_pid
        self.entered = threading.Event()
        self.spawned = threading.Event()
        self.pid: int | None = None
        self.held = contextlib.ExitStack()
        self.took_lock = False

    async def spawn(self, request):
        self.entered.set()
        await asyncio.sleep(0.5)
        proc = await super().spawn(request)
        self.pid = proc.pid
        self.held.enter_context(
            locks.hold(
                self.project_dir, request.job_id, [RUNNER_LOCK], pid=self.holder_pid
            )
        )
        self.took_lock = _locks_of(self.project_dir, request.job_id) != []
        self.spawned.set()
        return proc


def _manager(tmp_path, runner, argv) -> JobManager:
    manager = JobManager(
        str(tmp_path),
        runner=runner,
        runner_cwd=str(tmp_path),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, path: list(argv),
    )
    manager.start()
    return manager


def _alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _wait_until(predicate, timeout: float, interval: float = 0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()


def _drain(q: queue.Queue) -> list[dict]:
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


def _last_log_lines(manager: JobManager, job_id: str) -> list[str]:
    return (manager.get_log(job_id) or "").splitlines()


def _locks_of(project_dir: str, job_id: str) -> list[dict]:
    return [h for h in locks.holders(project_dir) if h.get("job_id") == job_id]


@pytest.fixture()
def slow_runner(tmp_path):
    # The lock's owner: alive for the whole test, and not this process (whose own pid the lock
    # store never counts as a live holder).
    holder = subprocess.Popen(LONG_SLEEP_ARGV)
    runner = SlowSpawnRunner(str(tmp_path), holder.pid)
    yield runner
    runner.held.close()
    holder.kill()
    holder.wait()
    # Never leave a 60 s sleeper behind when an assertion fails on the unfixed code.
    if runner.pid is not None and _alive(runner.pid):
        psutil.Process(runner.pid).kill()


def _race(
    manager: JobManager, runner: SlowSpawnRunner, stop
) -> tuple[dict, dict, list]:
    """Submit, call *stop* while spawn is pending, wait for spawn to return and settle."""
    statuses = manager.subscribe_status()
    job = manager.submit("tools", {}, [])
    assert runner.entered.wait(10.0), "the scheduler never tried to spawn the job"
    stopped = stop(job["id"])
    assert runner.spawned.wait(10.0), "spawn never returned"
    pid = runner.pid
    # Settled means: the process is gone, or the job left 'cancelled' (the bug).
    _wait_until(
        lambda: not _alive(pid) or manager.get(job["id"])["state"] != "cancelled",
        timeout=10.0,
    )
    return job, stopped, _drain(statuses)


@pytest.mark.parametrize("how", ["cancel", "force"])
def test_a_job_stopped_while_spawning_stays_cancelled_and_its_process_dies(
    tmp_path, slow_runner, how
):
    manager = _manager(tmp_path, slow_runner, LONG_SLEEP_ARGV)
    try:
        stop = manager.cancel if how == "cancel" else manager.force
        job, stopped, published = _race(manager, slow_runner, stop)

        assert stopped["state"] == "cancelled"
        final = manager.get(job["id"])
        assert final["state"] == "cancelled"
        # Every status the manager published for this job after the stop is terminal.
        states = [s["state"] for s in published if s["id"] == job["id"]]
        assert "running" not in states and "succeeded" not in states, states
        # The process the runner started was killed (it would sleep 60 s otherwise).
        assert _wait_until(lambda: not _alive(slow_runner.pid), timeout=10.0)
        # Time ordering: a job never finishes before it starts.
        assert final["finished_at"] is not None
        assert (
            final["started_at"] is None or final["started_at"] <= final["finished_at"]
        )
        # The store on disk agrees with the API, so a restart sees the same truth.
        on_disk = JobRegistry(str(tmp_path)).read_status(job["id"])
        assert on_disk.state == "cancelled"
        assert on_disk.pid is None
        if how == "force":
            assert final["error"]["type"] == "forced"
        # The stop finishes after the process is reaped: the log is closed with the cancel
        # note, then the lock the runner took is released.
        _wait_until(
            lambda: _last_log_lines(manager, job["id"])[-1:] == [CANCEL_NOTE]
            and not _locks_of(str(tmp_path), job["id"]),
            timeout=10.0,
        )
        assert slow_runner.took_lock  # the release below had something to release
        lines = _last_log_lines(manager, job["id"])
        assert lines[-1:] == [CANCEL_NOTE], lines
        assert lines.count(CANCEL_NOTE) == 1, lines
        assert _locks_of(str(tmp_path), job["id"]) == []
    finally:
        manager.shutdown()


def test_a_slow_spawn_that_nobody_stops_still_runs_to_success(tmp_path, slow_runner):
    """Control: the race guard must not cancel jobs that were never stopped."""
    manager = _manager(tmp_path, slow_runner, SHORT_SLEEP_ARGV)
    try:
        job = manager.submit("tools", {}, [])
        final = _wait_until(
            lambda: (lambda s: s if s["state"] not in ("queued", "running") else None)(
                manager.get(job["id"])
            ),
            timeout=10.0,
        )
        assert final["state"] == "succeeded"
        assert final["exit_code"] == 0
        assert final["started_at"] <= final["finished_at"]
    finally:
        manager.shutdown()
