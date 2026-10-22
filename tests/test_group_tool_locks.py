"""Group tools hold a lock on what they write and read-lock the simulations they read (p23).

What this pins: ``tit.jobs.locks.keys_for`` for the two group kinds.

- ``nifti_average`` writes ``derivatives/ti-toolbox/nifti_average/<output_name>/``; before this
  it requested nothing (``keys_for("nifti_average", ...) == []``), so two runs of one name
  interleaved their writes. ``keys_for``'s own docstring: never request nothing.
- ``stats`` (both config classes) and ``nifti_average`` read each row's simulation NIfTIs. A
  simulation job write-locks ``subject:<sid>:sim:<montage>`` (the ``sim`` branch of
  ``keys_for``), so a group job must read-lock the same resource to wait for a re-run of a
  simulation it is about to read.

Where the expected keys come from: the sim kind's own key for the same montage, computed here
by ``keys_for("sim", ...)`` (never retyped from the group branch), and the output folder
names in ``tit.stats.nifti_average.main``/``tit.server.routes.plan._plan_nifti_average``.
The scheduler half drives ``tit.jobs.scheduler.evaluate`` and the runner half
``tit.jobs.locks.hold`` with real lock directories.

Reproduce: ``.venv/bin/python -m pytest tests/test_group_tool_locks.py -q -p no:cacheprovider``.
Dated 2026-10-22.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tit.jobs import locks, scheduler
from tit.jobs.spec import Cost, JobSpec

BUDGET = Cost(cpus=8, mem_gb=32)


def _sim_write_key(sid: str, montage: str) -> str:
    """The resource a simulation job of *montage* on *sid* writes, from the sim branch itself."""
    sim = locks.keys_for("sim", [sid], {"montages": [{"name": montage}]})
    (resource,) = [
        r.resource
        for r in sim
        if r.mode == "write" and r.resource.endswith(f":{montage}")
    ]
    return resource


def _nifti_config(output_name: str = "insula_avg") -> dict:
    return {
        "output_name": output_name,
        "subjects": [
            {"subject_id": "101", "simulation_name": "L_Insula", "group": "A"},
            {"subject_id": "LA", "simulation_name": "L_Insula", "group": "B"},
            {"subject_id": "101", "simulation_name": "Thalamus", "group": "B"},
        ],
    }


def _stats_config(_type: str) -> dict:
    if _type == "CorrelationConfig":
        rows = [
            {"subject_id": s, "simulation_name": m, "effect_size": e}
            for s, m, e in (
                ("101", "L_Insula", 0.4),
                ("LA", "L_Insula", 1.2),
                ("CHN", "M1", -0.3),
            )
        ]
    else:
        rows = [
            {"subject_id": s, "simulation_name": m, "response": r}
            for s, m, r in (
                ("101", "L_Insula", 1),
                ("LA", "L_Insula", 0),
                ("CHN", "M1", 0),
            )
        ]
    return {"_type": _type, "analysis_name": "run1", "subjects": rows}


def _pairs(requests) -> list[tuple[str, str]]:
    return [(r.resource, r.mode) for r in requests]


def test_nifti_average_writes_its_output_and_reads_each_row_simulation() -> None:
    requests = locks.keys_for("nifti_average", ["101", "LA"], _nifti_config())
    assert _pairs(requests) == [
        ("project:nifti_average:insula_avg", "write"),
        (_sim_write_key("101", "L_Insula"), "read"),
        (_sim_write_key("LA", "L_Insula"), "read"),
        (_sim_write_key("101", "Thalamus"), "read"),
    ]


@pytest.mark.parametrize(
    "_type,mode",
    [
        ("GroupComparisonConfig", "group_comparison"),
        ("CorrelationConfig", "correlation"),
    ],
)
def test_stats_read_locks_the_simulations_of_its_rows(_type: str, mode: str) -> None:
    # tit/stats/__main__.py passes no subject ids: the rows are the only source.
    requests = locks.keys_for("stats", [], _stats_config(_type))
    assert _pairs(requests) == [
        (f"project:stats:{mode}/run1", "write"),
        (_sim_write_key("101", "L_Insula"), "read"),
        (_sim_write_key("LA", "L_Insula"), "read"),
        (_sim_write_key("CHN", "M1"), "read"),
    ]


def test_a_repeated_row_is_one_read_lock() -> None:
    config = _nifti_config()
    config["subjects"].append(dict(config["subjects"][0], group="C"))
    resources = [r.resource for r in locks.keys_for("nifti_average", [], config)]
    assert len(resources) == len(set(resources)) == 4


def _spec(job_id: str, kind: str, config: dict, subject_ids: list[str]) -> JobSpec:
    return JobSpec(
        id=job_id, kind=kind, config=config, subject_ids=subject_ids, cost=Cost(1, 1)
    )


def _holding(job: JobSpec) -> list[dict]:
    """The lock descriptors a running *job* leaves on disk (what ``locks.hold`` writes)."""
    return [
        {
            "key": r.key,
            "resource": r.resource,
            "mode": r.mode,
            "job_id": job.id,
        }
        for r in locks.keys_for(job.kind, job.subject_ids, job.config)
    ]


def test_a_running_simulation_rerun_holds_back_a_stats_job_that_reads_it() -> None:
    sim = _spec("sim1", "sim", {"montages": [{"name": "L_Insula"}]}, ["101"])
    stats = _spec("stats1", "stats", _stats_config("GroupComparisonConfig"), [])
    decision = scheduler.evaluate(
        stats, {}, _holding(sim), running_cost=Cost(0, 0), budget=BUDGET
    )
    assert not decision.admit
    assert [w.job_id for w in decision.waiting_on] == ["sim1"]

    # A simulation of a montage no row reads does not hold it back.
    other = _spec("sim2", "sim", {"montages": [{"name": "Occipital"}]}, ["101"])
    decision = scheduler.evaluate(
        stats, {}, _holding(other), running_cost=Cost(0, 0), budget=BUDGET
    )
    assert decision.admit


def test_two_nifti_average_jobs_of_one_name_serialize_and_readers_share() -> None:
    first = _spec("avg1", "nifti_average", _nifti_config("same"), ["101", "LA"])
    second = _spec("avg2", "nifti_average", _nifti_config("same"), ["101", "LA"])
    decision = scheduler.evaluate(
        second, {}, _holding(first), running_cost=Cost(0, 0), budget=BUDGET
    )
    assert not decision.admit
    assert [w.key for w in decision.waiting_on] == ["project:nifti_average:same:write"]

    # Another name reading the same simulations runs alongside: reads never block reads.
    third = _spec("avg3", "nifti_average", _nifti_config("other"), ["101", "LA"])
    decision = scheduler.evaluate(
        third, {}, _holding(first), running_cost=Cost(0, 0), budget=BUDGET
    )
    assert decision.admit


@pytest.fixture()
def live_pid():
    """A process `locks.holders` believes in (the test process's own pid is never reported)."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait()


def test_a_second_runner_of_one_output_name_is_refused(tmp_path, live_pid) -> None:
    """The runners take these keys through ``locks.hold``: write against write is refused."""
    requests = locks.keys_for("nifti_average", [], _nifti_config("same"))
    with locks.hold(str(tmp_path), "avg1", requests, pid=live_pid):
        with pytest.raises(locks.LockConflictError, match="project:nifti_average:same"):
            with locks.hold(str(tmp_path), "avg2", requests, pid=live_pid):
                pass
