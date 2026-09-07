"""Integration tests: JobManager driving real (fake) subprocesses end to end.

Each test builds its own :class:`~tit.jobs.manager.JobManager` pointed at a fresh ``tmp_path``,
with the command builder swapped for one that always runs ``tests/fake_runner.py`` regardless of
kind — so these exercise the real scheduler tick, real subprocess spawn/wait/cancel, and the real
lock directory, without needing any of the nine science runners to exist.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time

import psutil
import pytest

from tit.jobs import locks
from tit.jobs.kinds import may_spawn_docker_siblings
from tit.jobs.manager import JobManager
from tit.jobs.registry import events_path, stdout_path
from tit.jobs.spec import Cost

FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "fake_runner.py")


def _fake_command_for(kind, config, spec_path):
    return [sys.executable, FAKE_RUNNER, spec_path]


def make_manager(
    tmp_path, *, budget: Cost | None = None, poll_interval: float = 0.05
) -> JobManager:
    manager = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=poll_interval,
        budget=budget or Cost(cpus=8, mem_gb=64),
        command_for=_fake_command_for,
    )
    manager.start()
    return manager


def wait_until(predicate, timeout=10.0, interval=0.02):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s (last value: {last!r})")


@pytest.fixture()
def manager(tmp_path):
    m = make_manager(tmp_path)
    yield m
    m.shutdown()


# ---------------------------------------------------------------------------------------------
# happy path / failure
# ---------------------------------------------------------------------------------------------


def test_submit_runs_and_succeeds(manager):
    status = manager.submit(
        "tools",
        {"__fake": {"stages": ["a", "b"], "duration_s": 0.1, "artifact": "/x/out.txt"}},
        ["001"],
    )
    assert status["state"] == "queued"
    final = wait_until(
        lambda: (lambda s: s if s["state"] in ("succeeded", "failed") else None)(
            manager.get(status["id"])
        )
    )
    assert final["state"] == "succeeded"
    assert final["exit_code"] == 0
    assert final["started_at"] is not None and final["finished_at"] is not None
    assert final["artifacts"] == [{"path": "/x/out.txt", "kind": "txt"}]
    assert final["progress"]["stage"] == "b"
    # ra_13 finding #6: JobStatus.log_path, derived by the manager from its own registry rather
    # than reconstructed client-side (pages/jobs/JobDetailDrawer.tsx used to do exactly that).
    from tit.jobs.registry import stdout_path

    assert final["log_path"] == stdout_path(manager.project_dir, status["id"])
    assert os.path.isfile(final["log_path"])

    events = manager.get_events(status["id"])
    types = [e["type"] for e in events]
    assert types[:2] == ["stage", "log"]
    assert "result" in types and "exit" in types
    # seq is dense and starts at 0
    assert [e["seq"] for e in events] == list(range(len(events)))

    log = manager.get_log(status["id"])
    assert "fake_runner: starting kind=tools" in log


def test_submit_failure_records_exit_code_and_error(manager):
    status = manager.submit(
        "tools", {"__fake": {"duration_s": 0.05, "fail": True, "exit_code": 3}}, []
    )
    final = wait_until(
        lambda: (lambda s: s if s["state"] == "failed" else None)(
            manager.get(status["id"])
        )
    )
    assert final["exit_code"] == 3
    assert final["error"]["type"] == "runner_failed"
    assert "3" in final["error"]["message"]


def test_unknown_kind_rejected_at_submit(manager):
    with pytest.raises(ValueError):
        manager.submit("not_a_real_kind", {}, [])


def test_disallowed_kind_fails_with_kind_error_at_admit_time(tmp_path):
    """ra_13 finding #14: a kind that passes JOB_KINDS at submit() (it's a real, known kind)
    but that the *real* ``tit.jobs.kinds.command_for`` refuses -- the ``tools`` allowlist
    (ra_14 finding #2) is exactly such a case -- surfaces as a "failed" job with
    ``error.type == "kind_error"``, not a raised exception or a wedged "queued" job. Uses the
    real ``kinds.command_for`` (not this file's fake-runner override) since the point is what
    the real admit path does when it raises.
    """
    manager = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
    )
    manager.start()
    try:
        status = manager.submit("tools", {"module": "os"}, [])
        final = wait_until(
            lambda: (lambda s: s if s["state"] == "failed" else None)(
                manager.get(status["id"])
            )
        )
        assert final["error"]["type"] == "kind_error"
        assert "not an allowed tit.tools module" in final["error"]["message"]
    finally:
        manager.shutdown()


def test_list_and_get_detail(manager):
    status = manager.submit(
        "tools", {"__fake": {"duration_s": 0.05}}, ["001"], tags=["t1"]
    )
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager.get(status["id"])
        )
    )
    listed = manager.list_jobs(subject="001")
    assert any(j["id"] == status["id"] for j in listed)
    detail = manager.get_detail(status["id"])
    assert detail["spec"]["tags"] == ["t1"]
    assert detail["status"]["id"] == status["id"]
    assert detail["artifacts"] == detail["status"]["artifacts"]
    assert manager.get_detail("nope") is None


def test_delete_requires_terminal_state(manager):
    # 0.2s is plenty to observe "not_terminal" below before the job finishes (ra_11 finding #10
    # -- this was 1.0s, dominating a large slice of the file's real wall-clock time for no
    # correctness benefit).
    status = manager.submit("tools", {"__fake": {"duration_s": 0.2}}, [])
    assert manager.delete(status["id"]) == "not_terminal"
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager.get(status["id"])
        )
    )
    assert manager.delete(status["id"]) == "deleted"
    assert manager.get(status["id"]) is None
    assert manager.delete(status["id"]) == "not_found"


# ---------------------------------------------------------------------------------------------
# dependencies
# ---------------------------------------------------------------------------------------------


def test_after_dependency_waits_then_runs(manager):
    first = manager.submit("tools", {"__fake": {"duration_s": 0.3}}, [])
    second = manager.submit(
        "tools", {"__fake": {"duration_s": 0.05}}, [], after=[first["id"]]
    )

    waiting = wait_until(
        lambda: (lambda s: s if s["waiting_on"] else None)(manager.get(second["id"]))
    )
    assert waiting["state"] == "queued"
    assert waiting["waiting_on"] == [{"key": "after", "job_id": first["id"]}]

    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager.get(first["id"])
        )
    )
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager.get(second["id"])
        )
    )


def test_dependency_failure_skips_dependants_transitively(manager):
    first = manager.submit("tools", {"__fake": {"duration_s": 0.05, "fail": True}}, [])
    second = manager.submit("tools", {"__fake": {}}, [], after=[first["id"]])
    third = manager.submit("tools", {"__fake": {}}, [], after=[second["id"]])

    wait_until(
        lambda: (lambda s: s if s["state"] == "skipped" else None)(
            manager.get(third["id"])
        )
    )
    second_final = manager.get(second["id"])
    assert second_final["state"] == "skipped"
    assert "failed" in second_final["error"]["message"]


# ---------------------------------------------------------------------------------------------
# locks
# ---------------------------------------------------------------------------------------------


def test_lock_conflict_shows_waiting_on_then_admits(tmp_path):
    manager = make_manager(tmp_path)
    try:
        holder = manager.submit(
            "leadfield",
            {
                "__fake": {
                    "duration_s": 0.2,  # ra_11 finding #10: was 0.5s
                    "hold_locks": True,
                    "project_dir": str(tmp_path),
                }
            },
            ["001"],
        )
        wait_until(
            lambda: (lambda s: s if s["state"] == "running" else None)(
                manager.get(holder["id"])
            )
        )
        # The lock is acquired *inside* the fake_runner subprocess after it starts up, not the
        # instant the manager marks the job "running" -- wait for the actual on-disk hold.
        wait_until(
            lambda: [
                h for h in locks.holders(str(tmp_path)) if h["job_id"] == holder["id"]
            ]
            or None
        )

        waiter = manager.submit(
            "leadfield",
            {
                "__fake": {
                    "duration_s": 0.05,
                    "hold_locks": True,
                    "project_dir": str(tmp_path),
                }
            },
            ["001"],
        )
        waiting = wait_until(
            lambda: (lambda s: s if s["waiting_on"] else None)(
                manager.get(waiter["id"])
            )
        )
        assert waiting["waiting_on"][0]["job_id"] == holder["id"]
        assert "leadfields" in waiting["waiting_on"][0]["key"]

        wait_until(
            lambda: (lambda s: s if s["state"] == "succeeded" else None)(
                manager.get(holder["id"])
            )
        )
        wait_until(
            lambda: (lambda s: s if s["state"] == "succeeded" else None)(
                manager.get(waiter["id"])
            )
        )
    finally:
        manager.shutdown()


def test_lock_conflicts_query_for_plan_endpoint(tmp_path):
    manager = make_manager(tmp_path)
    try:
        holder = manager.submit(
            "leadfield",
            {
                "__fake": {
                    "duration_s": 0.2,  # ra_11 finding #10: was 0.5s
                    "hold_locks": True,
                    "project_dir": str(tmp_path),
                }
            },
            ["001"],
        )
        wait_until(
            lambda: (lambda s: s if s["state"] == "running" else None)(
                manager.get(holder["id"])
            )
        )
        wait_until(
            lambda: [
                h for h in locks.holders(str(tmp_path)) if h["job_id"] == holder["id"]
            ]
            or None
        )
        conflicts = wait_until(
            lambda: manager.lock_conflicts(["subject:001:leadfields:write"]) or None
        )
        assert conflicts[0]["held_by"] == holder["id"]
        assert conflicts[0]["subject"] == "001"
        assert conflicts[0]["kind"] == "leadfield"
    finally:
        manager.shutdown()


# ---------------------------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------------------------


def test_budget_fanout_limits_concurrency(tmp_path):
    manager = make_manager(tmp_path, budget=Cost(cpus=8, mem_gb=64))
    try:
        ids = []
        for _ in range(4):
            # 0.2s (ra_11 finding #10: was 0.6s x 4) still leaves plenty of 0.02s-interval
            # samples per "wave" (floor(8/3)=2 concurrent) below to reliably catch an overshoot.
            status = manager.submit(
                "flex", {"cpus": 3, "__fake": {"duration_s": 0.2}}, []
            )
            ids.append(status["id"])

        # At least one job must be observed waiting on budget (3 cpu x 3 running = 9 > 8).
        def _some_budget_waiting():
            statuses = [manager.get(i) for i in ids]
            return any(
                s["budget_wait"] if "budget_wait" in s else None for s in statuses
            ) or any(s["state"] == "queued" for s in statuses)

        # observe peak concurrency never exceeds floor(8/3) = 2
        max_running = 0
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            statuses = [manager.get(i) for i in ids]
            running = sum(1 for s in statuses if s["state"] == "running")
            max_running = max(max_running, running)
            if all(s["state"] == "succeeded" for s in statuses):
                break
            time.sleep(0.02)
        else:
            pytest.fail("jobs did not all finish in time")

        assert max_running <= 2
        assert all(manager.get(i)["state"] == "succeeded" for i in ids)
    finally:
        manager.shutdown()


# ---------------------------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------------------------


def test_cancel_queued_job(manager):
    blocker = manager.submit("tools", {"__fake": {"duration_s": 2.0}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "running" else None)(
            manager.get(blocker["id"])
        )
    )
    dependant = manager.submit("tools", {"__fake": {}}, [], after=[blocker["id"]])
    wait_until(
        lambda: (lambda s: s if s["state"] == "queued" and s["waiting_on"] else None)(
            manager.get(dependant["id"])
        )
    )
    result = manager.cancel(dependant["id"])
    assert result["state"] == "cancelled"
    manager.cancel(blocker["id"])


def test_cancel_running_job_kills_process(manager):
    status = manager.submit("tools", {"__fake": {"duration_s": 5.0}}, [])
    running = wait_until(
        lambda: (lambda s: s if s["state"] == "running" else None)(
            manager.get(status["id"])
        )
    )
    assert running["liveness"] == "active"

    with manager._lock:  # test-only peek; production code never needs this
        pid_val = manager._status[status["id"]].pid
    assert pid_val is not None and psutil.pid_exists(pid_val)

    result = manager.cancel(status["id"])
    assert result["state"] == "cancelled"
    assert (
        not psutil.pid_exists(pid_val)
        or psutil.Process(pid_val).status() == psutil.STATUS_ZOMBIE
    )


def test_cancel_closes_the_log_with_one_readable_line(manager):
    """FX2: a cancelled job's log used to end in PETSc's ten-line "Caught signal number 15 /
    MPI_Abort" block -- even for kinds that run no solver -- so a cancel read as a crash
    (`docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` open issue 2). The runner cannot write this
    line itself (SIGTERM's default disposition runs no Python), so the manager writes it once,
    after the process tree is gone."""
    from tit.jobs.manager import CANCEL_NOTE
    from tit.jobs.registry import stdout_path

    status = manager.submit("tools", {"__fake": {"duration_s": 5.0}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "running" else None)(
            manager.get(status["id"])
        )
    )
    assert manager.cancel(status["id"])["state"] == "cancelled"

    log = stdout_path(manager.project_dir, status["id"])
    lines = [ln for ln in open(log, encoding="utf-8").read().splitlines() if ln.strip()]
    assert lines.count(CANCEL_NOTE) == 1
    assert lines[-1] == CANCEL_NOTE  # nothing can write after it: the tree is dead
    assert not any("PETSC ERROR" in ln or "MPI_Abort" in ln for ln in lines)


def test_cancel_note_survives_a_missing_log(tmp_path):
    """Best-effort: a job whose log directory is gone must still cancel cleanly."""
    manager = make_manager(tmp_path)
    try:
        manager._append_note("no-such-job", "cancelled by user")  # must not raise
    finally:
        manager.shutdown()


def test_cancel_unknown_job_returns_none(manager):
    assert manager.cancel("nope") is None


def test_force_marks_terminal_without_waiting(manager):
    status = manager.submit("tools", {"__fake": {"duration_s": 5.0}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "running" else None)(
            manager.get(status["id"])
        )
    )
    forced = manager.force(status["id"])
    assert forced["state"] == "lost"
    assert forced["error"]["type"] == "forced"
    # best-effort background termination should eventually actually kill it too
    with manager._lock:
        pid_val = manager._status[status["id"]].pid
    assert pid_val is None  # cleared by force()


# ---------------------------------------------------------------------------------------------
# rerun
# ---------------------------------------------------------------------------------------------


def test_submit_plan_group_cap_limits_concurrent_running_jobs(tmp_path):
    """submit_plan(group_cap=N) (JobGroupRequest.parallel_subjects) admits at most N of the
    group's independent (no ``after``) jobs at once, end to end through the real scheduler.
    """
    from tit.jobs.spec import PlannedJob

    manager = make_manager(tmp_path, budget=Cost(cpus=64, mem_gb=256))
    try:
        planned = [
            PlannedJob(
                label=f"j{i}",
                kind="tools",
                config={"__fake": {"duration_s": 0.3}},
                subject_ids=[f"{i:03d}"],
            )
            for i in range(4)
        ]
        result = manager.submit_plan(planned, group_cap=2)
        ids = [j["id"] for j in result["jobs"]]
        assert len(ids) == 4

        max_running = 0
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            statuses = [manager.get(i) for i in ids]
            running = sum(1 for s in statuses if s["state"] == "running")
            max_running = max(max_running, running)
            if all(s["state"] == "succeeded" for s in statuses):
                break
            time.sleep(0.02)
        else:
            pytest.fail("group jobs did not all finish in time")

        assert max_running <= 2
        assert all(manager.get(i)["state"] == "succeeded" for i in ids)
    finally:
        manager.shutdown()


def test_rerun_submits_new_job_with_same_config(manager):
    original = manager.submit(
        "tools", {"__fake": {"duration_s": 0.05}}, ["001"], tags=["batch"]
    )
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager.get(original["id"])
        )
    )
    rerun = manager.rerun(original["id"])
    assert rerun["id"] != original["id"]
    assert rerun["subject_ids"] == ["001"]
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager.get(rerun["id"])
        )
    )
    assert manager.rerun("nope") is None


# ---------------------------------------------------------------------------------------------
# restart reconciliation (maintainer, Sep 2026: a restart must not keep running jobs)
# ---------------------------------------------------------------------------------------------


def test_restart_terminates_a_still_running_job_and_fails_it(tmp_path):
    """The headline policy: a runner that outlived the previous server is killed, not adopted."""
    manager1 = make_manager(tmp_path)
    status = manager1.submit(
        "tools", {"__fake": {"duration_s": 30.0, "stages": ["a", "b", "c"]}}, []
    )
    # Wait for at least one progress event to have been tailed, not just "running" (which flips
    # the instant the process is spawned, before it's necessarily emitted anything yet).
    wait_until(
        lambda: (lambda s: s if s["state"] == "running" and s["progress"] else None)(
            manager1.get(status["id"])
        )
    )
    with manager1._lock:
        pid = manager1._status[status["id"]].pid
    assert psutil.pid_exists(pid)
    # Shut down the manager (its background loop/thread) without touching the child process --
    # this simulates the server process restarting while a job's real OS process survives.
    manager1.shutdown()
    assert psutil.pid_exists(pid)

    manager2 = make_manager(tmp_path)
    try:
        final = wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                manager2.get(status["id"])
            )
        )
        assert final["state"] == "failed"
        assert final["error"]["message"] == "interrupted: server restarted"
        # ...and the surviving process was actually stopped, not left running unattended.
        wait_until(lambda: (not psutil.pid_exists(pid)) or None)
        # One line at the end of the log says why.
        log = open(stdout_path(str(tmp_path), status["id"]), encoding="utf-8").read()
        assert log.rstrip().endswith("interrupted: server restarted")
    finally:
        manager2.shutdown()


def test_restart_publishes_the_reconciled_job_to_subscribers(tmp_path):
    """Open clients (the jobs rail) must see the transition, not keep spinning on "running"."""
    manager1 = make_manager(tmp_path)
    status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    _strand_as_running(manager1, status["id"], pid=999_999_999, create_time=0.0)
    manager1.shutdown()

    # Subscribe *before* start(), so the reconciliation publish cannot be missed.
    manager2 = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=_fake_command_for,
    )
    q = manager2.subscribe_status()
    manager2.start()
    try:
        payload = q.get(timeout=10.0)
        assert payload["id"] == status["id"]
        assert payload["state"] == "failed"
    finally:
        manager2.shutdown()


def _strand_as_running(manager, job_id, *, pid, create_time):
    """Rewrite a finished job's status.json as if it were still "running" -- simulating a server
    restart finding a stranded job, without the real-OS-timing race of killing a process and
    hoping its pid isn't reused before the next manager starts."""
    with manager._lock:
        job_status = manager._status[job_id]
        job_status.state = "running"
        job_status.pid = pid
        job_status.create_time = create_time
        job_status.finished_at = None
        job_status.error = None
        job_status.exit_code = None
        manager.registry.write_status(job_status)
    open(events_path(str(manager.project_dir), job_id), "w", encoding="utf-8").close()


def test_restart_fails_a_stranded_running_job_whose_pid_is_dead(tmp_path):
    manager1 = make_manager(tmp_path)
    status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    _strand_as_running(manager1, status["id"], pid=999_999_999, create_time=0.0)
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        # start() only guarantees the background loop *exists*, not that its first tick (which
        # runs _reconcile_all()) has executed yet -- poll rather than assume it already has.
        final = wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                manager2.get(status["id"])
            )
        )
        assert final["state"] == "failed"
        assert final["error"]["type"] == "lost"
        assert final["error"]["message"] == "interrupted: server restarted"
    finally:
        manager2.shutdown()


def test_restart_fails_a_queued_job_and_never_resubmits_it(tmp_path):
    """"a restart should not automatically keep running jobs" -- including starting one that
    had not started yet."""
    manager1 = make_manager(tmp_path)
    status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    with manager1._lock:
        job_status = manager1._status[status["id"]]
        job_status.state = "queued"
        job_status.started_at = None
        job_status.finished_at = None
        job_status.pid = None
        job_status.create_time = None
        job_status.error = None
        job_status.exit_code = None
        manager1.registry.write_status(job_status)
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        final = wait_until(
            lambda: (lambda s: s if s["state"] != "queued" else None)(
                manager2.get(status["id"])
            )
        )
        assert final["state"] == "failed"
        assert final["error"]["message"] == "interrupted before start: server restarted"
        # Give the scheduler a few ticks: it must not admit the job after reconciliation.
        time.sleep(0.3)
        assert manager2.get(status["id"])["state"] == "failed"
    finally:
        manager2.shutdown()


def test_restart_leaves_terminal_jobs_untouched(tmp_path):
    manager1 = make_manager(tmp_path)
    status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    done = wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        time.sleep(0.3)
        after = manager2.get(status["id"])
        assert after["state"] == "succeeded"
        assert after["error"] is None
        assert after["finished_at"] == done["finished_at"]
    finally:
        manager2.shutdown()


def test_restart_still_reports_a_job_that_really_finished_while_the_server_was_down(
    tmp_path,
):
    """Reconciliation is not a blanket "fail everything": a stranded "running" job whose
    events.jsonl records a real exit keeps its true outcome and exit code."""
    manager1 = make_manager(tmp_path)
    status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    events_file = events_path(str(tmp_path), status["id"])
    kept = open(events_file, encoding="utf-8").read()
    _strand_as_running(manager1, status["id"], pid=999_999_999, create_time=0.0)
    open(events_file, "w", encoding="utf-8").write(kept)  # restore the real exit event
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        final = wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                manager2.get(status["id"])
            )
        )
        assert final["state"] == "succeeded"
        assert final["exit_code"] == 0
    finally:
        manager2.shutdown()


def test_restart_never_signals_pid_1_or_the_servers_own_pid(tmp_path):
    """ra_14 finding #5, now on the reconciliation path: a crafted/corrupted status.json naming
    this process's own pid (standing in for "the server's own pid") must never be treated as a
    live runner and must never be signalled -- even with a create_time that matches it exactly.
    """
    import psutil as _psutil

    own_create_time = _psutil.Process(os.getpid()).create_time()
    manager1 = make_manager(tmp_path)
    status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    _strand_as_running(
        manager1, status["id"], pid=os.getpid(), create_time=own_create_time
    )
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        final = wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                manager2.get(status["id"])
            )
        )
        assert final["state"] == "failed"
    finally:
        manager2.shutdown()
    # The pid this test runs under is still alive and untouched.
    assert psutil.pid_exists(os.getpid())


def test_restart_pid_reuse_guard_leaves_the_unrelated_process_alone(tmp_path):
    """A live pid whose create_time does *not* match the record is a different process that
    merely inherited the number -- reconciliation must fail the job without signalling it."""
    victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    manager1 = make_manager(tmp_path)
    try:
        status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
        wait_until(
            lambda: (lambda s: s if s["state"] == "succeeded" else None)(
                manager1.get(status["id"])
            )
        )
        # Same pid, wrong create_time: pid reuse, as far as the record can tell.
        _strand_as_running(manager1, status["id"], pid=victim.pid, create_time=1.0)
        manager1.shutdown()

        manager2 = make_manager(tmp_path)
        try:
            final = wait_until(
                lambda: (lambda s: s if s["state"] != "running" else None)(
                    manager2.get(status["id"])
                )
            )
            assert final["state"] == "failed"
            assert victim.poll() is None  # untouched
        finally:
            manager2.shutdown()
    finally:
        victim.kill()
        victim.wait()


def test_restart_stops_sibling_containers_of_a_stranded_docker_job(tmp_path, monkeypatch):
    """QSIPrep/QSIRecon siblings can outlive the runner; reconciliation stops them by label,
    through the bounded Engine-API client (never the docker CLI)."""
    import tit.jobs.manager as jobs_manager

    stopped: list[str] = []

    async def _fake_stop(job_id, timeout_s=3.0):
        stopped.append(job_id)
        return 1

    monkeypatch.setattr(jobs_manager, "stop_docker_siblings_via_engine", _fake_stop)
    monkeypatch.setattr(jobs_manager, "may_spawn_docker_siblings", lambda *a, **k: True)

    manager1 = make_manager(tmp_path)
    status = manager1.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    _strand_as_running(manager1, status["id"], pid=999_999_999, create_time=0.0)
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                manager2.get(status["id"])
            )
        )
        assert stopped == [status["id"]]
    finally:
        manager2.shutdown()


def test_cancel_of_a_running_status_pointing_at_pid_1_never_signals_it(manager):
    """ra_14 finding #5, the ``cancel`` path specifically: even if a job's in-memory status
    somehow carries pid 1 (a corrupted status.json read back, or -- the real-world case this
    guards -- a re-attach that predates this fix), ``cancel()`` must finalize the job without
    ever calling ``terminate_tree`` on pid 1 itself. Bypasses ``_reconcile_all`` entirely (already
    covered by the two tests above) to isolate the cancel-path guard in ``runner.terminate_tree``.
    """
    status = manager.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager.get(status["id"])
        )
    )
    with manager._lock:
        job_status = manager._status[status["id"]]
        job_status.state = "running"
        job_status.pid = 1
        job_status.create_time = None
        job_status.finished_at = None
        job_status.error = None

    result = manager.cancel(status["id"])
    assert result["state"] == "cancelled"


def _rewrite_as_running_under_a_dead_pid(manager, job_id: str) -> None:
    """Shared setup for the two tests below: same "server restarted while a job's real process
    was already gone" scenario as test_restart_detects_lost_job, but the job's own events.jsonl
    is left intact (not blanked) so its ``exit`` event can be read back."""
    with manager._lock:
        job_status = manager._status[job_id]
        job_status.state = "running"
        job_status.pid = 999_999_999
        job_status.create_time = 0.0
        job_status.finished_at = None
        job_status.error = None
        manager.registry.write_status(job_status)


def test_restart_reads_exit_code_from_the_exit_event_succeeded(tmp_path):
    """A re-attached job whose process is gone is finalized from its own ``exit`` event's
    ``code`` (contracts/events.schema.json), not merely whether a ``result`` event exists.
    """
    manager1 = make_manager(tmp_path)
    status = manager1.submit(
        "tools", {"__fake": {"duration_s": 0.05, "artifact": "/x/out.txt"}}, []
    )
    wait_until(
        lambda: (lambda s: s if s["state"] == "succeeded" else None)(
            manager1.get(status["id"])
        )
    )
    _rewrite_as_running_under_a_dead_pid(manager1, status["id"])
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        # start() only guarantees the background loop *exists*, not that its first tick (which
        # runs _reattach_all()) has executed yet -- poll rather than assume it already has.
        final = wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                manager2.get(status["id"])
            )
        )
        assert final["state"] == "succeeded"
        assert final["exit_code"] == 0
        assert final["error"] is None
        # Artifacts recorded before the (real, prior) exit are still recovered on reattach.
        assert final["artifacts"] == [{"path": "/x/out.txt", "kind": "txt"}]
    finally:
        manager2.shutdown()


def test_restart_reads_exit_code_from_the_exit_event_failed(tmp_path):
    manager1 = make_manager(tmp_path)
    status = manager1.submit(
        "tools", {"__fake": {"duration_s": 0.05, "fail": True, "exit_code": 7}}, []
    )
    wait_until(
        lambda: (lambda s: s if s["state"] == "failed" else None)(
            manager1.get(status["id"])
        )
    )
    _rewrite_as_running_under_a_dead_pid(manager1, status["id"])
    manager1.shutdown()

    manager2 = make_manager(tmp_path)
    try:
        final = wait_until(
            lambda: (lambda s: s if s["state"] != "running" else None)(
                manager2.get(status["id"])
            )
        )
        assert final["state"] == "failed"
        assert final["exit_code"] == 7
        assert final["error"]["type"] == "runner_failed"
    finally:
        manager2.shutdown()


def test_module_kinds_get_a_config_file_with_project_dir(tmp_path):
    """Pipeline runners read a *config* JSON (fields + project_dir), never the job record.

    Found by the first real analyzer job on Dataset 000: ``tit.analyzer`` crashed with
    ``KeyError: 'project_dir'`` because it was handed ``spec.json``.
    """
    import json
    import os

    from tit.jobs.registry import job_dir

    manager = make_manager(tmp_path)
    try:
        job = manager.submit(
            "analyzer",
            {"subject_id": "001", "simulation": "sim", "__fake": {"duration_s": 0.05}},
            ["001"],
        )
        wait_until(
            lambda: (lambda s: s if s["state"] in ("succeeded", "failed") else None)(
                manager.get(job["id"])
            )
        )
        cfg_path = os.path.join(job_dir(str(tmp_path), job["id"]), "config.json")
        assert os.path.exists(cfg_path)
        data = json.load(open(cfg_path))
        assert data["project_dir"] == str(tmp_path)
        assert data["subject_id"] == "001"
        assert "kind" not in data and "id" not in data  # config, not the job record
        spec = json.load(
            open(os.path.join(job_dir(str(tmp_path), job["id"]), "spec.json"))
        )
        assert spec["kind"] == "analyzer"
    finally:
        manager.shutdown()


# ---------------------------------------------------------------------------------------------
# Cancellation must never depend on Docker being reachable.
#
# Regression: with the Docker daemon wedged (a socket that accepts and never answers), every
# cancel -- including a ``tools`` job that cannot possibly have spawned a sibling container --
# blocked in ``stop_docker_siblings``'s `docker ps` until cancel()'s 20 s future timeout, so the
# job never reached "cancelled". Two independent fixes, one test each: the call is skipped for
# kinds that cannot spawn siblings, and it is time-bounded when it is made.
# ---------------------------------------------------------------------------------------------


def _hang_forever_stop(recorder):
    async def _stop(job_id):
        recorder.append(job_id)
        await asyncio.sleep(3600)

    return _stop


def test_cancel_of_a_tools_job_never_asks_docker(tmp_path, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(
        "tit.jobs.manager.stop_docker_siblings", _hang_forever_stop(called)
    )
    manager = make_manager(tmp_path)
    try:
        status = manager.submit("tools", {"__fake": {"duration_s": 30.0}}, [])
        wait_until(lambda: manager.get(status["id"])["state"] == "running" or None)
        started = time.monotonic()
        result = manager.cancel(status["id"])
        assert result["state"] == "cancelled"
        assert time.monotonic() - started < 5.0
        assert called == []  # a tools job cannot have spawned a sibling container
    finally:
        manager.shutdown()


def test_cancel_of_a_dwi_job_still_stops_siblings_but_is_bounded(tmp_path, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(
        "tit.jobs.manager.stop_docker_siblings", _hang_forever_stop(called)
    )
    manager = make_manager(tmp_path)
    try:
        status = manager.submit(
            "pre",
            {"run_qsiprep": True, "__fake": {"duration_s": 30.0}},
            ["001"],
        )
        wait_until(lambda: manager.get(status["id"])["state"] == "running" or None)
        started = time.monotonic()
        result = manager.cancel(status["id"])
        assert result["state"] == "cancelled"
        # It did ask Docker (this kind can spawn siblings) but did not wait on the hung call.
        assert called == [status["id"]]
        assert time.monotonic() - started < 10.0
    finally:
        manager.shutdown()


class TestMaySpawnDockerSiblings:
    def test_tools_and_science_kinds_never_do(self):
        for kind in ("tools", "sim", "flex", "ex", "analyzer", "stats", None):
            assert may_spawn_docker_siblings(kind, {}) is False

    def test_pre_dwi_stages_do(self):
        assert may_spawn_docker_siblings("pre", {"run_qsiprep": True}) is True
        assert may_spawn_docker_siblings("pre", {"run_qsirecon": True}) is True
        assert may_spawn_docker_siblings("pre", {"extract_dti": True}) is True

    def test_pre_structural_only_does_not(self):
        assert (
            may_spawn_docker_siblings(
                "pre", {"run_charm": True, "run_qsiprep": False, "extract_dti": False}
            )
            is False
        )

    def test_unrecognised_pre_config_is_treated_conservatively(self):
        assert may_spawn_docker_siblings("pre", {"something_new": True}) is True
        assert may_spawn_docker_siblings("pre", None) is True
