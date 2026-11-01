"""Preprocessing cancellation stops the pipeline and leaves the process's SIGTERM handling as found.

Pins (2026-10-31, assessment items A1-7, G2-5, A1-10):

* A SIGTERM during ``run_pipeline`` sets the runner's stop event (``request_stop``), so no new
  command (the next dcm2niix, charm, ...) starts after a cancel; it used to only terminate the
  running children (``terminate_all``), and the loop went on to the next command.
* ``run_pipeline`` puts back the SIGTERM handler it replaced when it returns or raises; it used
  to leave its own installed for the rest of the process (a notebook, a test session).
* ``check_m2m_exists`` answers for the path manager's m2m directory.

Expected behaviour is read from ``signal.getsignal`` and ``CommandRunner.run``'s documented
``PreprocessCancelled``; nothing is retyped from the implementation.

Reproduce: ``.venv/bin/python -m pytest tests/test_pre_scripting_surface.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import logging
import signal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tit.pre import structural
from tit.pre.utils import CommandRunner, PreprocessCancelled


def _sentinel(signum, frame):  # a handler the test can recognise
    pass


def test_sigterm_stops_the_runner_so_no_new_command_starts():
    runner = CommandRunner()
    saved = signal.getsignal(signal.SIGTERM)
    try:
        structural._install_sigterm_handler(runner)
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        assert runner.stop_event.is_set()
        with pytest.raises(PreprocessCancelled):
            runner.run(["true"], logger=logging.getLogger("t"))
    finally:
        signal.signal(signal.SIGTERM, saved)


@pytest.mark.parametrize("fails", [False, True])
def test_run_pipeline_restores_the_previous_sigterm_handler(tmp_path, fails):
    saved = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _sentinel)
    pm = SimpleNamespace(_root=lambda: str(tmp_path))
    try:
        with (
            patch.object(structural, "get_path_manager", return_value=pm),
            patch.object(structural, "ensure_subject_dirs"),
            patch.object(structural, "ensure_dataset_descriptions"),
            patch.object(structural, "ensure_bidsignore"),
            patch.object(
                structural,
                "_run_subject_pipeline",
                side_effect=RuntimeError("step failed") if fails else None,
            ),
        ):
            if fails:
                with pytest.raises(RuntimeError):
                    structural._run_pipeline_inner(["001"])
            else:
                structural._run_pipeline_inner(["001"])
        assert signal.getsignal(signal.SIGTERM) is _sentinel
    finally:
        signal.signal(signal.SIGTERM, saved)


def test_check_m2m_exists_uses_the_path_managers_m2m(tmp_path):
    from tit.paths import PathManager
    from tit.pre.utils import check_m2m_exists

    assert not check_m2m_exists(str(tmp_path), "001")
    m2m = PathManager(str(tmp_path)).m2m("001")
    (tmp_path / m2m).mkdir(parents=True)
    assert check_m2m_exists(str(tmp_path), "001")
