"""Tests for tit/opt/ex/parallel.py -- ordered candidate evaluation."""

import multiprocessing
import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import tit.cpu  # noqa: E402
from tit.opt.ex import parallel  # noqa: E402
from tit.opt.ex.parallel import evaluate_ordered, resolve_n_jobs  # noqa: E402


class _Engine:
    def __init__(self, tag):
        self.tag = tag

    def score(self, a, b):
        return (self.tag, a * b, os.getpid())


def _has_fork():
    try:
        multiprocessing.get_context("fork")
    except ValueError:
        return False
    return True


@pytest.mark.unit
class TestResolveNJobs:
    def test_negative_means_the_global_cpu_limit(self, monkeypatch):
        """Outside a job the default is 70 % of the container (floor), not all cores minus one."""
        monkeypatch.delenv("TIT_JOB_CPUS", raising=False)
        monkeypatch.setattr(tit.cpu, "effective_cpus", lambda root=None: 10)
        assert resolve_n_jobs(-1) == 7
        assert resolve_n_jobs(None) == resolve_n_jobs(-1)
        assert resolve_n_jobs(0) == resolve_n_jobs(-1)

    def test_explicit_is_clamped_to_the_budget(self, monkeypatch):
        monkeypatch.setenv("TIT_JOB_CPUS", "4")
        assert resolve_n_jobs(1) == 1
        assert resolve_n_jobs(3) == 3
        assert resolve_n_jobs(16) == 4


@pytest.mark.unit
@pytest.mark.parametrize(("admitted", "n_jobs"), [(7, -1), (7, 3), (8, 3), (4, 16)])
def test_workers_times_numba_threads_never_exceed_the_admitted_cpus(
    monkeypatch, admitted, n_jobs
):
    """The pool is sized from TIT_JOB_CPUS and each worker's numba share is that budget divided
    by the workers -- not the container's full core count divided by them."""
    monkeypatch.setenv("TIT_JOB_CPUS", str(admitted))
    seen = {}

    class _Pool:
        def __init__(self, processes, initializer=None, initargs=()):
            seen["workers"], seen["threads"] = processes, initargs[0]

        def imap(self, fn, tasks, chunksize):
            return iter(())

        def close(self):
            pass

        terminate = join = close

    class _Ctx:
        Pool = _Pool

    monkeypatch.setattr(parallel.multiprocessing, "get_context", lambda _m: _Ctx())
    list(evaluate_ordered(_Engine("x"), "score", [], n_jobs))
    assert seen["workers"] <= admitted
    assert seen["workers"] * seen["threads"] <= admitted


@pytest.mark.unit
class TestEvaluateOrdered:
    def test_serial_path_runs_in_process(self):
        engine = _Engine("s")
        tasks = [(i, 2) for i in range(5)]
        out = list(evaluate_ordered(engine, "score", tasks, 1))
        assert [o[1] for o in out] == [0, 2, 4, 6, 8]
        assert {o[2] for o in out} == {os.getpid()}

    @pytest.mark.skipif(not _has_fork(), reason="fork start method unavailable")
    def test_pool_preserves_order_and_forks(self):
        engine = _Engine("p")
        tasks = ((i, 3) for i in range(40))
        out = list(evaluate_ordered(engine, "score", tasks, 2))
        assert [o[1] for o in out] == [3 * i for i in range(40)]
        assert all(o[0] == "p" for o in out)
        assert os.getpid() not in {o[2] for o in out}

    @pytest.mark.skipif(not _has_fork(), reason="fork start method unavailable")
    def test_early_close_terminates_pool(self):
        engine = _Engine("c")
        gen = evaluate_ordered(engine, "score", ((i, 1) for i in range(1000)), 2)
        first = next(gen)
        assert first[1] == 0
        gen.close()  # must not hang or raise
