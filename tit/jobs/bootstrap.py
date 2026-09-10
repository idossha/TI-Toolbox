"""Lazy :class:`~tit.jobs.manager.JobManager` singleton for ``tit.server``.

A route handler calls ``get_manager(request.app)``; ``tit.jobs.api`` (called from modules with no
``Request`` at hand — B2's viewer routes, B3's plan routes, notebooks running in-process) calls
``get_manager()`` with no argument. Both return the same instance, built lazily against the
current :func:`tit.paths.get_path_manager` project — this file is intentionally the *only* place
that constructs a ``JobManager``, so ``tit/server/app.py`` never needs to know jobs exist.
"""

from __future__ import annotations

import os
from typing import Any

from tit.jobs.manager import JobManager

ENV_RUNNER_CWD = "TIT_RUNNER_CWD"
DEFAULT_RUNNER_CWD = "/ti-toolbox"

_manager: JobManager | None = None


def get_manager(app: Any | None = None) -> JobManager:
    """The process-wide :class:`JobManager`, created on first call.

    Mirrors :func:`tit.paths.get_path_manager`'s singleton pattern: one job manager per process,
    scoped to whatever project :func:`tit.paths.get_path_manager` currently points at.
    """
    global _manager
    if _manager is None:
        from tit.paths import get_path_manager

        pm = get_path_manager()
        project_dir = pm.project_dir
        if not project_dir:
            raise RuntimeError(
                "tit.jobs.bootstrap.get_manager(): no project directory — "
                "initialise PathManager (get_path_manager(project_dir)) first"
            )
        runner_cwd = os.environ.get(ENV_RUNNER_CWD, DEFAULT_RUNNER_CWD)
        if not os.path.isdir(runner_cwd):
            # Host/dev fallback: /ti-toolbox only exists inside the container.
            runner_cwd = project_dir
        _manager = JobManager(project_dir, runner_cwd=runner_cwd)
        _manager.start()
    if app is not None:
        app.state.job_manager = _manager
    return _manager


def reset_manager() -> None:
    """Shut down and forget the singleton (tests only — mirrors ``reset_path_manager``)."""
    global _manager
    if _manager is not None:
        _manager.shutdown()
    _manager = None


def shutdown() -> None:
    """Stop the singleton's background thread if one was ever created, without raising when it
    wasn't (ra_11 finding #10/thread-leak: a session-scoped test fixture calls this once at
    interpreter exit so the manager's ``tit-job-manager`` thread never outlives the test run —
    the same leak :mod:`tests.test_telemetry`'s ``threading.enumerate()`` joins were paying for
    on every "send" test, see that finding). Safe to call whether or not :func:`get_manager` was
    ever called, and safe to call more than once.
    """
    reset_manager()


def set_manager_for_testing(manager: JobManager | None) -> None:
    """Install a specific, already-started manager (tests only — e.g. one wired to a fake
    runner) instead of letting :func:`get_manager` construct the default one lazily. Does not
    shut down whatever manager was previously installed; call :func:`reset_manager` for that.
    """
    global _manager
    _manager = manager
