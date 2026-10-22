"""Job costs, the CPU limit and admission stay finite, positive and live.

What this pins
--------------
- ``tit.jobs.costs.default_cost``: a config's own ``cpus``/``memory_gb``/``mem_gb`` claim (and an
  ex/mEx/stats ``n_jobs``) that is NaN, infinite, negative or zero never becomes the job's
  cost. Such a claim used to pass straight through: ``Cost(cpus=nan)`` never fits any budget
  (the job stayed queued forever with "need nan cpu"), ``memory_gb: -5`` lowered the running
  total so the scheduler over-admitted, ``n_jobs: inf`` raised ``OverflowError`` at submit.
- ``tit.cpu``: a saved percent of ``1e999``/``Infinity``/``NaN`` and ``TIT_JOB_CPUS=inf`` fall
  back to the defaults; ``1e999`` used to raise ``OverflowError`` on every scheduler tick.
- Liveness: each pathological claim, submitted as the only job, reaches a terminal state.
- The memory model's two code-fact properties: ``tit/sim/__main__.py`` runs montages one
  after another (so sim memory does not scale with the montage count), and flex memory never
  decreases with ``n_multistart`` (Dataset 000 measured 5.8 GB at 1 restart, 15.2 GB at 4; the
  measured-peak check itself is ``tests/test_job_memory_realdata.py``).

Expected values: the budget arithmetic is ``Cost.fits`` done by hand in each test's comment;
the fallbacks are the documented defaults (70 %, the kind's table entry).

Reproduce: ``.venv/bin/python -m pytest tests/test_job_costs.py -q``.
Deliberately elsewhere: the cost table's lookup and overrides (``tests/test_jobs_model.py``),
the budget fan-out (``tests/test_jobs_manager.py``). Written 2026-10-22 (package p41).
"""

from __future__ import annotations

import math
import os
import sys
import time

import pytest

import tit.cpu
from tit.jobs import costs
from tit.jobs.manager import JobManager
from tit.jobs.spec import Cost, TERMINAL_STATES

FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "fake_runner.py")
BAD = [math.nan, math.inf, -math.inf, -5, 0]


def _sane(cost: Cost) -> bool:
    return (
        math.isfinite(cost.cpus)
        and cost.cpus >= 1
        and math.isfinite(cost.mem_gb)
        and cost.mem_gb > 0
    )


# ---------------------------------------------------------------------------------------------
# default_cost
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["tools", "flex", "pre", "analyzer"])
@pytest.mark.parametrize("field", ["cpus", "memory_gb", "mem_gb"])
@pytest.mark.parametrize("value", BAD, ids=["nan", "inf", "-inf", "-5", "0"])
def test_a_non_finite_or_non_positive_claim_falls_back_to_the_kinds_default(
    kind, field, value
):
    claimed = costs.default_cost(kind, {field: value})
    assert _sane(claimed), claimed
    # The bad half is ignored: it is exactly what the job costs with no claim at all.
    unclaimed = costs.default_cost(kind, {})
    half = "cpus" if field == "cpus" else "mem_gb"
    assert getattr(claimed, half) == getattr(unclaimed, half)


@pytest.mark.parametrize("field", ["cpus", "memory_gb"])
def test_a_huge_finite_claim_is_kept_for_admission_to_clamp(field):
    # 1e9 is finite and positive, so it is the job's claim; the scheduler shrinks a claim
    # above the budget to the budget (JobManager._tick), see the liveness test below.
    claimed = costs.default_cost("tools", {field: 1e9})
    assert _sane(claimed)
    assert (claimed.cpus if field == "cpus" else claimed.mem_gb) == 1e9


def test_a_fractional_cpu_claim_still_claims_one_cpu():
    assert costs.default_cost("tools", {"cpus": 0.25}).cpus == 1


@pytest.mark.parametrize("kind", ["ex", "mex", "stats"])
@pytest.mark.parametrize("n_jobs", [math.nan, math.inf, -math.inf, -1, 0], ids=str)
def test_n_jobs_that_is_not_a_finite_count_means_the_whole_cpu_limit(
    kind, n_jobs, monkeypatch
):
    monkeypatch.setattr(costs, "cpu_limit", lambda: 6)
    assert costs.default_cost(kind, {"n_jobs": n_jobs}).cpus == 6
    # ...and a real count is still clamped to it.
    assert costs.default_cost(kind, {"n_jobs": 4}).cpus == 4
    assert costs.default_cost(kind, {"n_jobs": 64}).cpus == 6


@pytest.mark.parametrize("value", BAD, ids=["nan", "inf", "-inf", "-5", "0"])
def test_a_qsiprep_resource_claim_that_is_not_finite_and_positive_is_ignored(
    value, monkeypatch
):
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    config = {
        "run_qsiprep": True,
        "qsiprep_config": {"cpus": value, "memory_gb": value},
    }
    claimed = costs.default_cost("pre", config)
    assert _sane(claimed)
    # Unclaimed QSIPrep: the pre table's 6 GB and the tool's default thread count.
    plain = costs.default_cost("pre", {"run_qsiprep": True, "qsiprep_config": {}})
    assert claimed == plain


# ---------------------------------------------------------------------------------------------
# memory model properties (code facts, not measurements)
# ---------------------------------------------------------------------------------------------


def _montage(name: str) -> dict:
    return {"_type": "Montage", "name": name, "mode": "net"}


def test_sim_memory_does_not_scale_with_montages_run_one_after_another():
    """``tit/sim/__main__.py`` hands every montage to ``run_simulation``, which solves them in a
    loop: the peak is one montage's, whatever the count."""
    one = costs.default_cost("sim", {"montages": [_montage("m1")]})
    five = costs.default_cost(
        "sim", {"montages": [_montage(f"m{i}") for i in range(5)]}
    )
    assert five.mem_gb == one.mem_gb
    assert five.cpus == one.cpus


@pytest.mark.parametrize("kind", ["flex", "flex_adaptive", "flex_pareto"])
def test_flex_memory_never_decreases_with_more_restarts(kind):
    claims = [costs.default_cost(kind, {"n_multistart": n}).mem_gb for n in range(1, 9)]
    assert claims == sorted(claims)
    assert claims[-1] > claims[0]  # restarts do cost memory (measured: 5.8 -> 15.2 GB)
    # No n_multistart is FlexConfig's default of one restart.
    assert costs.default_cost(kind, {}).mem_gb == claims[0]


@pytest.mark.parametrize("n", [math.nan, math.inf, -3, 0, "4", True])
def test_a_restart_count_that_is_not_a_count_costs_one_restart(n):
    assert costs.default_cost("flex", {"n_multistart": n}) == costs.default_cost(
        "flex", {"n_multistart": 1}
    )


# ---------------------------------------------------------------------------------------------
# tit.cpu
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["1e999", "-1e999", "Infinity", "-Infinity", "NaN"])
def test_a_non_finite_saved_cpu_limit_is_the_default(raw, tmp_path, monkeypatch):
    path = tmp_path / tit.cpu.CPU_LIMIT_FILENAME
    path.write_text('{"percent": %s}' % raw)
    monkeypatch.setattr(tit.cpu, "cpu_limit_file", lambda: str(path))
    monkeypatch.setattr(tit.cpu, "effective_cpus", lambda root=None: 10)
    assert tit.cpu.cpu_limit_percent() == tit.cpu.DEFAULT_CPU_LIMIT_PERCENT == 70
    assert tit.cpu.cpu_limit() == 7  # floor(70 % x 10)


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "1e999", "0", "-4", "x"])
def test_a_job_cpu_budget_that_is_not_a_count_is_the_cpu_limit(raw, monkeypatch):
    monkeypatch.setenv(tit.cpu.JOB_CPUS_ENV, raw)
    monkeypatch.setattr(tit.cpu, "cpu_limit", lambda root=tit.cpu.CGROUP_ROOT: 5)
    assert tit.cpu.job_cpus() == 5
    monkeypatch.setenv(tit.cpu.JOB_CPUS_ENV, "3")
    assert tit.cpu.job_cpus() == 3


# ---------------------------------------------------------------------------------------------
# admission liveness (real scheduler, fake runner)
# ---------------------------------------------------------------------------------------------


def _fake(kind, config, spec_path):
    return [sys.executable, FAKE_RUNNER, spec_path]


def _manager(tmp_path) -> JobManager:
    manager = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=0.02,
        budget=Cost(cpus=4, mem_gb=8),
        command_for=_fake,
    )
    manager.start()
    return manager


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.02)
    raise AssertionError(f"not reached within {timeout}s (last: {last!r})")


@pytest.mark.parametrize("kind", ["tools", "flex"])
@pytest.mark.parametrize("field", ["cpus", "memory_gb"])
@pytest.mark.parametrize(
    "value", [*BAD, 1e9], ids=["nan", "inf", "-inf", "-5", "0", "1e9"]
)
def test_a_lone_job_with_a_pathological_claim_is_admitted_never_stuck(
    tmp_path, kind, field, value
):
    manager = _manager(tmp_path)
    try:
        job = manager.submit(kind, {field: value, "__fake": {"duration_s": 0.01}}, [])
        final = _wait(
            lambda: (lambda s: s if s["state"] in TERMINAL_STATES else None)(
                manager.get(job["id"])
            )
        )
        assert final["state"] == "succeeded", final
    finally:
        manager.shutdown()


def test_a_negative_memory_claim_cannot_make_room_for_two_jobs(tmp_path):
    """Budget 8 GB. The -100 GB job costs the tools default (1 GB) instead, so with it running
    one 6 GB job fits (1 + 6 = 7 <= 8) and the second does not (7 + 6 = 13 > 8). With the
    claim taken at face value, -100 + 6 + 6 = -88 <= 8 admitted both."""
    manager = _manager(tmp_path)
    try:
        negative = manager.submit(
            "tools", {"memory_gb": -100, "__fake": {"duration_s": 1.5}}, []
        )
        _wait(lambda: manager.get(negative["id"])["state"] == "running")
        big = [
            manager.submit(
                "tools", {"memory_gb": 6, "__fake": {"duration_s": 0.3}}, []
            )["id"]
            for _ in range(2)
        ]
        peak = 0
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            states = [manager.get(i)["state"] for i in big]
            peak = max(peak, states.count("running"))
            if all(s == "succeeded" for s in states):
                break
            time.sleep(0.01)
        else:
            pytest.fail(f"the two 6 GB jobs did not finish: {states}")
        assert peak == 1
    finally:
        manager.shutdown()
