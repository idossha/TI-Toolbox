"""Ex/mEx search engines leave the caller's SIGINT/SIGTERM handlers as they found them.

Pins (2026-10-22): a library call must not change process-global state behind its caller's back.
``ExSearchEngine.run`` / ``MExSearchEngine.run`` used to install flag-setting handlers for SIGINT
and SIGTERM and never put the old ones back, so after ``run_ex_search`` in a notebook, Kernel >
Interrupt (SIGINT) no longer raised ``KeyboardInterrupt``: the dead closure swallowed it for the
rest of the session.

Expected values are identities, not numbers: the handler objects installed by the test before
``run`` are the same objects afterwards, on a normal return and when ``run`` raises mid-search;
and with Python's own ``default_int_handler`` in place before ``run``, a SIGINT sent after it raises
``KeyboardInterrupt``. The engines run in-process (``n_jobs=1``) on a fake ``TI_utils``; the forked
worker path and SIGTERM's process-level effect are in ``tests/test_ex_cancel.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_signals.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import os
import signal
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    not hasattr(signal, "SIGTERM") or os.name == "nt",
    reason="skipping: POSIX signals only",
)


@pytest.fixture
def caller_handlers():
    """The caller's own handlers (distinct from every default), restored after the test."""
    saved = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
    received = []

    def on_int(signum, frame):
        received.append(signum)

    def on_term(signum, frame):
        received.append(signum)

    signal.signal(signal.SIGINT, on_int)
    signal.signal(signal.SIGTERM, on_term)
    yield on_int, on_term
    signal.signal(signal.SIGINT, saved[0])
    signal.signal(signal.SIGTERM, saved[1])


def _fake_ti(fail_on_call: int | None = None):
    calls = []

    def get_field(channel, leadfield, idx):
        calls.append(channel)
        if fail_on_call is not None and len(calls) == fail_on_call:
            raise RuntimeError("leadfield read failed mid-search")
        return np.ones((5, 3)) * channel[2]

    return SimpleNamespace(
        get_field=get_field,
        get_maxTI=lambda e1, e2: np.linalg.norm(e1 + e2, axis=1),
    )


def _ready(engine):
    engine.leadfield = np.zeros(1)
    engine.idx_lf = None
    engine.roi_indices = np.array([0, 1])
    engine.roi_volumes = np.array([1.0, 1.0])
    engine.gm_indices = np.array([0, 1, 2, 3, 4])
    engine.gm_volumes = np.ones(5)
    return engine


def _run_ex(monkeypatch, tmp_path, fail_on_call=None):
    import tit.opt.ex.engine as engine_mod

    monkeypatch.setattr(engine_mod, "TI", _fake_ti(fail_on_call))
    engine = _ready(engine_mod.ExSearchEngine("/lf.hdf5", "/r.csv", "R", MagicMock()))
    # Two montages (A or E on channel 1+), one symmetric pair of splits.
    return engine.run(
        ["A", "E"],
        ["B"],
        ["C"],
        ["D"],
        [(1.5, 0.5), (0.5, 1.5)],
        False,
        str(tmp_path),
        n_jobs=1,
    )


def _run_mex(monkeypatch, tmp_path, fail_on_call=None):
    import tit.opt.mex.engine as mex_mod

    monkeypatch.setattr(mex_mod, "TI", _fake_ti(fail_on_call))
    monkeypatch.setattr(
        mex_mod, "envelope_max", lambda fields: np.linalg.norm(sum(fields), axis=1)
    )
    engine = _ready(mex_mod.MExSearchEngine("/lf.hdf5", "/r.csv", "R", MagicMock()))
    buckets = {
        f"e{k}_{pole}": (
            [f"{pole[0]}{k}{x}" for x in ("a", "b")] if k == 1 else [f"{pole[0]}{k}"]
        )
        for k in range(1, 5)
        for pole in ("plus", "minus")
    }
    return engine.run(buckets, False, str(tmp_path), current_mA=1.0, n_jobs=1)


_RUNS = {
    "ex": (_run_ex, 3),
    "mex": (_run_mex, 5),
}  # (runner, first field call of candidate 2)


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_run_returns_with_the_callers_handlers_in_place(
    kind, caller_handlers, monkeypatch, tmp_path
):
    run, _ = _RUNS[kind]
    results = run(monkeypatch, tmp_path)
    assert len(results) > 1  # a real search ran: several candidates were evaluated
    assert signal.getsignal(signal.SIGINT) is caller_handlers[0]
    assert signal.getsignal(signal.SIGTERM) is caller_handlers[1]


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_run_that_raises_mid_search_leaves_the_callers_handlers_in_place(
    kind, caller_handlers, monkeypatch, tmp_path
):
    run, second = _RUNS[kind]
    with pytest.raises(RuntimeError, match="mid-search"):
        run(monkeypatch, tmp_path, fail_on_call=second)
    assert signal.getsignal(signal.SIGINT) is caller_handlers[0]
    assert signal.getsignal(signal.SIGTERM) is caller_handlers[1]


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_ctrl_c_after_a_search_still_raises_keyboard_interrupt(
    kind, caller_handlers, monkeypatch, tmp_path
):
    signal.signal(
        signal.SIGINT, signal.default_int_handler
    )  # a fresh interpreter's handler
    run, _ = _RUNS[kind]
    run(monkeypatch, tmp_path)
    with pytest.raises(KeyboardInterrupt):
        os.kill(os.getpid(), signal.SIGINT)
        # Python runs the handler at the next bytecode boundary; a few of them, no sleeping.
        for _ in range(1000):
            pass
