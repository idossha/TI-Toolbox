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
- The memory model's code-fact properties: ``tit/sim/__main__.py`` runs montages one
  after another (so sim memory does not scale with the montage count), flex memory never
  decreases with ``n_multistart`` (Dataset 000 measured 5.8 GB at 1 restart, 15.2 GB at 4), and
  ex/mEx memory never decreases with the workers they fork, one per CPU claimed (ex 4.8 GB at 1,
  7.3 GB at 8; mEx 4.9 GB in one process, 8.4-12.6 GB forked); the measured-peak check itself
  is ``tests/test_job_memory_realdata.py``.
- An ex search claiming more memory than a small container has is still admitted and runs.
- The claim covers each recorded Dataset 000 peak (``MEASURED_PEAKS``, copied from the jobs'
  ``status.json`` so the floor holds without the dataset), and a fractional count
  (``n_jobs``/thread counts of ``0.5``) is no count: truncated, ``n_jobs`` would claim 0 CPUs
  and a thread count one thread instead of the tool's default.

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
@pytest.mark.parametrize("n_jobs", [math.nan, math.inf, -math.inf, -1, 0, 0.5], ids=str)
def test_n_jobs_that_is_not_a_finite_count_means_the_whole_cpu_limit(
    kind, n_jobs, monkeypatch
):
    monkeypatch.setattr(costs, "cpu_limit", lambda: 6)
    # 0.5 is not a count either: truncated, it would claim 0 CPUs.
    assert costs.default_cost(kind, {"n_jobs": n_jobs}).cpus == 6
    # ...and a real count is still clamped to it.
    assert costs.default_cost(kind, {"n_jobs": 4}).cpus == 4
    assert costs.default_cost(kind, {"n_jobs": 64}).cpus == 6


@pytest.mark.parametrize(
    "stage,field",
    [
        ("run_fastsurfer", "fastsurfer_threads"),
        ("run_freesurfer", "freesurfer_threads"),
        ("create_m2m", "charm_threads"),
    ],
)
@pytest.mark.parametrize(
    "value", [0.5, *BAD], ids=["0.5", "nan", "inf", "-inf", "-5", "0"]
)
def test_a_thread_count_that_is_not_a_count_claims_the_tools_default(
    stage, field, value, tmp_path, monkeypatch
):
    """A fraction of a thread is no thread count: truncated, ``0.5`` became ``0``, which
    ``effective_threads`` raises to one thread instead of the tool's default."""
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "preferences.json"
    )
    monkeypatch.delenv("TIT_FASTSURFER_THREADS", raising=False)
    plain = costs.default_cost("pre", {stage: True})
    assert plain.cpus == 8  # no preference saved: the whole (patched) capacity
    assert costs.default_cost("pre", {stage: True, field: value}) == plain


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


@pytest.mark.parametrize("n", [math.nan, math.inf, -3, 0, 0.5, "4", True])
def test_a_restart_count_that_is_not_a_count_costs_one_restart(n):
    assert costs.default_cost("flex", {"n_multistart": n}) == costs.default_cost(
        "flex", {"n_multistart": 1}
    )


#: Peak PSS of succeeded jobs, in bytes: ``status.json`` ``rss_peak``, the server's own psutil
#: sample of the job's process tree, read from ``<project>/code/ti-toolbox/jobs/<id>/``: Dataset
#: 000 on 2026-10-22 (sim, flex) and 2026-11-03 (ex c6401588), and a copy-on-write clone of it
#: on 2026-11-03 (the other ex/mex jobs, run by the v3.1.3 release check). Copied here so the
#: floor holds in every CI run; ``tests/test_job_memory_realdata.py`` re-reads Dataset 000's live
#: (TIT_DATASET_000). Each sim ran one montage; the flex runs' ``n_multistart`` is from their
#: ``spec.json``. The CPUs column is what each job was admitted with (its ``spec.json`` cost,
#: or the ``n_jobs`` it ran): ex/mEx fork one worker per admitted CPU. The 256-montage ex runs
#: share c6401588's config at the stated ``n_jobs``; a2ddfabe and 1d689d52 are one-montage runs;
#: the mEx probes add two channels to that config (16 montages: 7a154326, 56eed5c6; 64:
#: e26b35b8; 256: 43c13b0b).
MEASURED_PEAKS = [
    ("sim 34ffcc59", "sim", {"montages": [_montage("m1")]}, 1, 7_769_851_904),
    ("sim b8fa6613", "sim", {"montages": [_montage("m1")]}, 1, 7_567_846_400),
    ("sim f56383c0", "sim", {"montages": [_montage("m1")]}, 1, 8_297_352_192),
    ("flex e689f217", "flex", {"n_multistart": 1}, 2, 5_838_716_928),
    ("flex ad8cf881", "flex", {"n_multistart": 4}, 2, 15_187_990_528),
    ("ex c6401588", "ex", {"n_jobs": -1}, 8, 7_304_898_560),
    ("ex 2fdca13b", "ex", {"n_jobs": 1}, 1, 4_787_320_832),
    ("ex 0f0802f6", "ex", {"n_jobs": 2}, 2, 4_975_965_184),
    ("ex 95712f85", "ex", {"n_jobs": 4}, 4, 5_765_708_800),
    ("ex 93ae4df0", "ex", {"n_jobs": 8}, 8, 7_268_092_928),
    ("ex a2ddfabe", "ex", {"n_jobs": -1}, 8, 4_867_426_304),
    ("mex 1d689d52", "mex", {"n_jobs": -1}, 8, 5_177_913_344),
    ("mex e26b35b8", "mex", {"n_jobs": 1}, 1, 4_890_470_400),
    ("mex 7a154326", "mex", {"n_jobs": 4}, 4, 8_424_146_944),
    ("mex 56eed5c6", "mex", {"n_jobs": 8}, 8, 8_468_759_552),
    ("mex 43c13b0b", "mex", {"n_jobs": 8}, 8, 12_642_045_952),
]


@pytest.mark.parametrize(
    "job,kind,config,cpus,peak", MEASURED_PEAKS, ids=[m[0] for m in MEASURED_PEAKS]
)
def test_the_memory_claim_covers_the_recorded_peak(
    job, kind, config, cpus, peak, monkeypatch
):
    # The claim on the machine the job ran on: its admitted CPUs are the CPU limit there.
    monkeypatch.setattr(costs, "cpu_limit", lambda: cpus)
    assert costs.default_cost(kind, config).cpus == cpus, job
    # 1e9 bytes per GB: the smaller reading of "GB", so the check is the strict one.
    assert costs.default_cost(kind, config).mem_gb * 1e9 >= peak, job


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_ex_memory_never_decreases_with_the_workers_it_forks(kind, monkeypatch):
    monkeypatch.setattr(costs, "cpu_limit", lambda: 64)
    claims = [costs.default_cost(kind, {"n_jobs": n}).mem_gb for n in range(1, 65)]
    assert claims == sorted(claims)
    assert claims[7] > claims[0]  # workers do cost memory (measured: 4.8 -> 7.3 GB at 1 -> 8)
    # n_jobs < 1 forks one worker per CPU of the limit.
    assert costs.default_cost(kind, {"n_jobs": -1}).mem_gb == claims[-1]


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


def test_an_ex_search_claiming_more_memory_than_the_container_still_runs(tmp_path):
    """8 workers claim 9 GB; a 4 GB container clamps the claim to 4 GB (JobManager) so the
    search runs alone instead of waiting on the budget forever."""
    manager = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=0.02,
        budget=Cost(cpus=8, mem_gb=4),
        command_for=_fake,
    )
    manager.start()
    try:
        job = manager.submit("ex", {"n_jobs": 8, "__fake": {"duration_s": 0.01}}, [])
        final = _wait(
            lambda: (lambda s: s if s["state"] in TERMINAL_STATES else None)(
                manager.get(job["id"])
            )
        )
        assert final["state"] == "succeeded", final
        assert manager._specs[job["id"]].cost.mem_gb == 4
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
