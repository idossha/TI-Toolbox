"""A job cancelled (or forced) while it is being admitted stays terminal, and its process dies.

What this pins (2026-10-22, package p18 "cancel-admit-race"): ``JobManager._admit`` awaits
``runner.spawn`` without holding the manager lock. A ``cancel()`` or ``force()`` that lands in
that window finalizes the still-``queued`` job as ``cancelled`` -- and then, before this fix,
``_admit`` resumed, overwrote the state with ``running``, and the job ended ``succeeded`` with
``finished_at`` earlier than ``started_at``, its process left to run to completion.

Where the expected values come from: ``contracts/openapi.yaml`` (``POST /api/jobs/{id}/cancel``:
a cancelled job never runs; ``force``: a recovery hatch that lands the job in a terminal state)
and plain time ordering (a job cannot finish before it starts). No number here comes from the
code under test.

How the window is made deterministic: a ``LocalPopenRunner`` subclass sets an event on entry to
``spawn()`` and then awaits ``asyncio.sleep(0.5)`` before really spawning, so a ``cancel()``
issued after the event is guaranteed to land while ``_admit`` is suspended. The spawned command
sleeps 60 s, so "the pid is dead within 10 s" can only be true if the manager killed it.

Run: ``python -m pytest tests/test_jobs_cancel_admit.py -q -p no:cacheprovider``.
Deliberately elsewhere: cancel of a *running* job (``tests/test_jobs_manager.py``).
"""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
import time

import psutil
import pytest

from tit.jobs.manager import JobManager
from tit.jobs.registry import JobRegistry
from tit.jobs.runner import LocalPopenRunner
from tit.jobs.spec import Cost

#: Long enough that the process can only be gone within the test's 10 s bound if it was killed.
LONG_SLEEP_ARGV = [sys.executable, "-c", "import time; time.sleep(60)"]
SHORT_SLEEP_ARGV = [sys.executable, "-c", "import time; time.sleep(0.2)"]


class SlowSpawnRunner(LocalPopenRunner):
    """Holds ``_admit`` inside ``spawn()`` for 0.5 s before the real spawn."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.spawned = threading.Event()
        self.pid: int | None = None

    async def spawn(self, request):
        self.entered.set()
        await asyncio.sleep(0.5)
        proc = await super().spawn(request)
        self.pid = proc.pid
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


@pytest.fixture()
def slow_runner():
    runner = SlowSpawnRunner()
    yield runner
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
