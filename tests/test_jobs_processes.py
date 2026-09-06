"""Unit tests for tit.jobs.processes (N0.6 spike: cross-platform process-tree primitives).

``is_windows()`` is monkeypatched (never ``sys.platform``/``os.name`` directly) so every test
below exercises the *real* Windows-branch code paths -- not a stand-in -- on whatever OS this
suite actually runs on, per the module's own design (see its docstring).
"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock

from tit.jobs import processes

# ---------------------------------------------------------------------------------------------
# is_windows()
# ---------------------------------------------------------------------------------------------


def test_is_windows_reflects_real_platform():
    import sys

    assert processes.is_windows() is (sys.platform == "win32")


# ---------------------------------------------------------------------------------------------
# spawn_kwargs()
# ---------------------------------------------------------------------------------------------


def test_spawn_kwargs_posix_branch():
    assert processes.spawn_kwargs() == {"start_new_session": True}


def test_spawn_kwargs_windows_branch(monkeypatch):
    monkeypatch.setattr(processes, "is_windows", lambda: True)
    kwargs = processes.spawn_kwargs()
    assert kwargs == {"creationflags": processes.CREATE_NEW_PROCESS_GROUP}
    # The hardcoded value must match the real win32/winbase.h constant used by CPython's own
    # subprocess.CREATE_NEW_PROCESS_GROUP on an actual Windows build (0x00000200) -- pinned here
    # so a typo in the module wouldn't silently produce a different, wrong creation flag.
    assert processes.CREATE_NEW_PROCESS_GROUP == 0x00000200


def test_spawn_kwargs_windows_branch_never_touches_start_new_session(monkeypatch):
    """start_new_session is documented POSIX-only and is a silent no-op on Windows (r6 audit) --
    the Windows branch must not rely on it at all, only on the creation flag."""
    monkeypatch.setattr(processes, "is_windows", lambda: True)
    assert "start_new_session" not in processes.spawn_kwargs()


# ---------------------------------------------------------------------------------------------
# send_terminate() / send_kill() -- POSIX branch
# ---------------------------------------------------------------------------------------------


def test_send_terminate_posix_sends_sigterm():
    proc = MagicMock()
    processes.send_terminate(proc)
    proc.send_signal.assert_called_once_with(signal.SIGTERM)
    proc.terminate.assert_not_called()


def test_send_kill_posix_sends_sigkill():
    proc = MagicMock()
    processes.send_kill(proc)
    proc.send_signal.assert_called_once_with(signal.SIGKILL)
    proc.kill.assert_not_called()


# ---------------------------------------------------------------------------------------------
# send_terminate() / send_kill() -- Windows branch (monkeypatched; exercised on this Mac)
# ---------------------------------------------------------------------------------------------


def test_send_terminate_windows_calls_psutil_terminate_not_send_signal(monkeypatch):
    monkeypatch.setattr(processes, "is_windows", lambda: True)
    proc = MagicMock()
    processes.send_terminate(proc)
    proc.terminate.assert_called_once_with()
    proc.send_signal.assert_not_called()


def test_send_kill_windows_calls_psutil_kill_not_send_signal(monkeypatch):
    """The exact bug this module fixes (tit/jobs/runner.py:213, r6/skeptic-3): the Windows path
    must never reach ``proc.send_signal(signal.SIGKILL)`` -- referencing ``signal.SIGKILL`` is
    itself an AttributeError on a real Windows interpreter (the attribute doesn't exist there at
    all), so the assertion that send_signal was never called is the meaningful one; this test
    running to completion on this (POSIX) host is not by itself proof the Windows branch is
    correct on real Windows, only that the code path this suite CAN exercise here takes the
    right branch -- see REPORT.md for what this does and does not prove."""
    monkeypatch.setattr(processes, "is_windows", lambda: True)
    proc = MagicMock()
    processes.send_kill(proc)
    proc.kill.assert_called_once_with()
    proc.send_signal.assert_not_called()


def test_send_kill_windows_branch_source_never_references_signal_sigkill():
    """Static guard against regression: greps this module's own source for a Windows-branch
    reference to signal.SIGKILL, which would be an AttributeError on a real Windows build even
    though every test above runs the branch on this (POSIX) host without incident -- the tests
    above prove *which branch runs*, this one proves the Windows branch's source can never
    evaluate the POSIX-only attribute at all, regardless of platform."""
    import inspect

    source = inspect.getsource(processes.send_kill)
    lines = source.splitlines()
    windows_branch = []
    in_windows_branch = False
    for line in lines:
        if "if is_windows():" in line:
            in_windows_branch = True
            continue
        if in_windows_branch:
            if line.strip().startswith("else:"):
                break
            windows_branch.append(line)
    assert windows_branch, "could not locate the Windows branch in send_kill's source"
    assert "SIGKILL" not in "".join(windows_branch)
