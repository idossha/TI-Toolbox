"""Unit + real-subprocess tests for tit.jobs.runner (N0.6 spike).

Covers the parts of runner.py this lane touched: LocalPopenRunner.spawn() actually using
tit.jobs.processes.spawn_kwargs() (both the real POSIX branch, exercised against a real child
process, and the Windows branch, exercised via monkeypatched tit.jobs.processes.is_windows() +
a mocked asyncio.create_subprocess_exec since this host cannot pass a real
CREATE_NEW_PROCESS_GROUP creationflags value to a real POSIX subprocess.Popen), terminate_tree()
escalating through tit.jobs.processes.send_terminate()/send_kill() instead of raw
signal.SIGTERM/SIGKILL (a real end-to-end kill of a SIGTERM-ignoring child, proving the grace ->
hard-kill escalation still works after the refactor), and RunRequest.stdout_path's
platform-safe default.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import MagicMock

import psutil
import pytest

from tit.jobs import processes as jobs_processes
from tit.jobs import runner as jobs_runner

# ---------------------------------------------------------------------------------------------
# RunRequest.stdout_path default
# ---------------------------------------------------------------------------------------------


def test_run_request_stdout_path_default_is_os_devnull_not_a_posix_literal():
    """Was a hard-coded "/dev/null" (N0.6 audit): doesn't exist on Windows. Every real caller
    (tit/jobs/manager.py) always passes an explicit stdout_path, so this only matters for a
    caller that constructs RunRequest without one -- still worth getting right."""
    req = jobs_runner.RunRequest(job_id="j", argv=["true"], cwd=".")
    assert req.stdout_path == os.devnull


# ---------------------------------------------------------------------------------------------
# LocalPopenRunner.spawn() -- POSIX branch, real child process
# ---------------------------------------------------------------------------------------------


def test_spawn_gives_the_child_its_own_process_group_on_posix(tmp_path):
    """Real integration check (not a mock): a child spawned via spawn_kwargs()'s POSIX branch
    (start_new_session=True) must land in a *different* process group than this test process --
    the whole reason terminate_tree can SIGTERM/SIGKILL the child without also signalling the
    runner that spawned it."""

    async def _run():
        runner = jobs_runner.LocalPopenRunner()
        req = jobs_runner.RunRequest(
            job_id="j-pgrp",
            argv=[sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=str(tmp_path),
            env=dict(os.environ),
            stdout_path=str(tmp_path / "out.log"),
        )
        proc = await runner.spawn(req)
        try:
            own_pgid = os.getpgid(os.getpid())
            child_pgid = os.getpgid(proc.pid)
            assert child_pgid != own_pgid
        finally:
            proc.kill()
            await proc.wait()

    asyncio.run(_run())


# ---------------------------------------------------------------------------------------------
# LocalPopenRunner.spawn() -- Windows branch (monkeypatched; exercised on this Mac)
# ---------------------------------------------------------------------------------------------


def test_spawn_uses_creation_flag_not_start_new_session_when_windows(
    monkeypatch, tmp_path
):
    """asyncio.create_subprocess_exec is mocked here (not exercised for real) because passing a
    real CREATE_NEW_PROCESS_GROUP creationflags value to an actual POSIX subprocess.Popen call
    raises ValueError -- that's the platform boundary this test cannot cross on a Mac. What it
    does prove for real: spawn() asks tit.jobs.processes.spawn_kwargs() for its process-group
    kwargs (rather than hard-coding start_new_session itself), so the Windows branch is reached
    and its exact kwargs dict is what actually gets forwarded to subprocess creation.
    """
    monkeypatch.setattr(jobs_processes, "is_windows", lambda: True)

    captured_kwargs: dict = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured_kwargs.update(kwargs)
        fake_proc = MagicMock()
        return fake_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    async def _run():
        runner = jobs_runner.LocalPopenRunner()
        req = jobs_runner.RunRequest(
            job_id="j-win",
            argv=["irrelevant-on-windows-mock"],
            cwd=str(tmp_path),
            env={},
            stdout_path=str(tmp_path / "out.log"),
        )
        await runner.spawn(req)

    asyncio.run(_run())

    assert (
        captured_kwargs.get("creationflags") == jobs_processes.CREATE_NEW_PROCESS_GROUP
    )
    assert "start_new_session" not in captured_kwargs


# ---------------------------------------------------------------------------------------------
# terminate_tree() -- real end-to-end escalation (grace-period SIGTERM -> hard-kill)
# ---------------------------------------------------------------------------------------------

_IGNORE_SIGTERM_AND_SLEEP = (
    "import signal, time; "
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "time.sleep(30)"
)


def test_terminate_tree_escalates_to_hard_kill_when_child_ignores_sigterm(tmp_path):
    """End-to-end proof that switching terminate_tree's two send_signal(...) calls to
    tit.jobs.processes.send_terminate()/send_kill() didn't change real behaviour on POSIX: a
    child that ignores SIGTERM must still be dead (via the SIGKILL/kill() escalation) once the
    grace period elapses."""

    async def _run():
        runner = jobs_runner.LocalPopenRunner()
        req = jobs_runner.RunRequest(
            job_id="j-hardkill",
            argv=[sys.executable, "-c", _IGNORE_SIGTERM_AND_SLEEP],
            cwd=str(tmp_path),
            env=dict(os.environ),
            stdout_path=str(tmp_path / "out.log"),
        )
        proc = await runner.spawn(req)
        create_time = psutil.Process(proc.pid).create_time()
        assert jobs_runner.is_alive(proc.pid, create_time) is True

        await jobs_runner.terminate_tree(proc.pid, create_time, grace_s=0.3)

        # Reap promptly; asyncio.subprocess.Process needs .wait() called or the OS may keep it
        # a zombie briefly even after the kill signal lands.
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        assert jobs_runner.is_alive(proc.pid, create_time) is False

    asyncio.run(_run())


# ---------------------------------------------------------------------------------------------
# terminate_tree() -- Windows branch (monkeypatched; exercised on this Mac via mocked psutil)
# ---------------------------------------------------------------------------------------------


def test_terminate_tree_windows_branch_calls_terminate_then_kill_not_send_signal(
    monkeypatch,
):
    """psutil.Process itself is mocked here (not exercised for real): the point is only to prove
    terminate_tree's two escalation stages call tit.jobs.processes.send_terminate/send_kill,
    which on the Windows branch means proc.terminate()/proc.kill() -- never
    proc.send_signal(signal.SIGTERM/SIGKILL), the exact pre-fix call site
    (tit/jobs/runner.py:213) that raised AttributeError on a real Windows interpreter.
    """
    monkeypatch.setattr(jobs_processes, "is_windows", lambda: True)

    root = MagicMock()
    root.create_time.return_value = 1000.0
    root.children.return_value = []
    # First status() call (inside the grace-period poll loop) reports still-running so the
    # escalation to send_kill is actually reached; is_running() stays True throughout (the mock
    # doesn't simulate the process actually dying, which is fine -- this test is about which
    # primitive gets called, not about real process lifecycle).
    root.is_running.return_value = True
    root.status.return_value = "running"

    monkeypatch.setattr(jobs_runner.psutil, "Process", lambda pid: root)

    asyncio.run(jobs_runner.terminate_tree(4242, create_time=1000.0, grace_s=0.05))

    root.terminate.assert_called_once_with()
    root.kill.assert_called_once_with()
    root.send_signal.assert_not_called()


class TestStopDockerSiblingsIsBounded:
    """A wedged Docker daemon makes `docker ps` hang forever; a cancel must not inherit that."""

    @staticmethod
    def _fake_docker(tmp_path, body: str) -> str:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        script = bin_dir / "docker"
        script.write_text("#!/bin/sh\n" + body + "\n")
        script.chmod(0o755)
        return str(bin_dir)

    def test_hanging_docker_ps_times_out_and_returns(self, tmp_path, monkeypatch):
        bin_dir = self._fake_docker(tmp_path, "sleep 300")
        monkeypatch.setenv("PATH", bin_dir + os.pathsep + os.environ["PATH"])
        started = time.monotonic()
        asyncio.run(jobs_runner.stop_docker_siblings("job-1", timeout_s=0.5))
        assert time.monotonic() - started < 5.0

    def test_missing_docker_cli_is_a_silent_no_op(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        asyncio.run(jobs_runner.stop_docker_siblings("job-1", timeout_s=0.5))

    def test_listed_containers_are_stopped(self, tmp_path, monkeypatch):
        log = tmp_path / "calls.log"
        bin_dir = self._fake_docker(
            tmp_path,
            f'echo "$@" >> {log}\n'
            'case "$1" in ps) echo abc123;; esac',
        )
        monkeypatch.setenv("PATH", bin_dir + os.pathsep + os.environ["PATH"])
        asyncio.run(jobs_runner.stop_docker_siblings("job-1", timeout_s=5.0))
        calls = log.read_text().splitlines()
        assert any(c.startswith("ps ") for c in calls)
        assert "stop abc123" in calls
