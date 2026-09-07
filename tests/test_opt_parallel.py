"""Tests for tit/opt/ex/parallel.py -- ordered candidate evaluation."""

import multiprocessing
import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

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
    def test_negative_means_all_cores_minus_one(self):
        assert resolve_n_jobs(-1) == max(1, (os.cpu_count() or 1) - 1)
        assert resolve_n_jobs(None) == resolve_n_jobs(-1)
        assert resolve_n_jobs(0) == resolve_n_jobs(-1)

    def test_explicit(self):
        assert resolve_n_jobs(1) == 1
        assert resolve_n_jobs(3) == 3


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
