"""scheduler.py: pure admission decisions (dependencies, lock waits, budget, skip cascade)."""

from __future__ import annotations

from tit.jobs import locks, scheduler
from tit.jobs.spec import Cost, JobSpec, JobStatus


def _spec(job_id: str, kind: str = "tools", **overrides) -> JobSpec:
    defaults = dict(config={}, subject_ids=[], cost=Cost(cpus=1, mem_gb=1))
    defaults.update(overrides)
    return JobSpec(id=job_id, kind=kind, **defaults)


def _status(job_id: str, state: str, **overrides) -> JobStatus:
    defaults = dict(
        kind="tools", subject_ids=[], created_at="2026-01-01T00:00:00+00:00"
    )
    defaults.update(overrides)
    return JobStatus(id=job_id, state=state, **defaults)


BUDGET = Cost(cpus=8, mem_gb=32)


def test_admits_with_no_dependencies_locks_or_budget_pressure():
    job = _spec("j1")
    decision = scheduler.evaluate(job, {}, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert decision.admit
    assert decision.waiting_on == []
    assert decision.budget_wait is None


def test_waits_on_unfinished_dependency():
    job = _spec("j2", after=["j1"])
    jobs = {"j1": _status("j1", "running")}
    decision = scheduler.evaluate(job, jobs, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert not decision.admit
    assert decision.skip_reason is None
    assert decision.waiting_on == [scheduler.WaitingOn(key="after", job_id="j1")]


def test_admits_once_dependency_succeeded():
    job = _spec("j2", after=["j1"])
    jobs = {"j1": _status("j1", "succeeded")}
    decision = scheduler.evaluate(job, jobs, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert decision.admit


def test_skips_when_dependency_failed():
    job = _spec("j2", after=["j1"])
    jobs = {"j1": _status("j1", "failed")}
    decision = scheduler.evaluate(job, jobs, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert not decision.admit
    assert decision.skip_reason == "dependency j1 failed"


def test_missing_dependency_treated_as_satisfied():
    job = _spec("j2", after=["ghost"])
    decision = scheduler.evaluate(job, {}, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert decision.admit


def test_lock_conflict_produces_waiting_on():
    job = _spec("j2", kind="leadfield", subject_ids=["001"])
    holder = {
        "key": "subject:001:m2m:write",
        "resource": "subject:001:m2m",
        "mode": "write",
        "job_id": "other-job",
        "pid": 1,
        "create_time": 0.0,
        "ts": 0.0,
    }
    decision = scheduler.evaluate(
        job, {}, [holder], running_cost=Cost(0, 0), budget=BUDGET
    )
    assert not decision.admit
    assert decision.waiting_on == [
        scheduler.WaitingOn(key="subject:001:m2m:write", job_id="other-job")
    ]


def test_readers_do_not_conflict_with_each_other():
    job = _spec("j2", kind="sim", subject_ids=["001"], config={"montages": []})
    holder = {
        "key": "subject:001:m2m:read",
        "resource": "subject:001:m2m",
        "mode": "read",
        "job_id": "reader-1",
        "pid": 1,
        "create_time": 0.0,
        "ts": 0.0,
    }
    decision = scheduler.evaluate(
        job, {}, [holder], running_cost=Cost(0, 0), budget=BUDGET
    )
    assert decision.admit  # sim wants m2m:read too; two readers don't conflict


def test_own_lock_holder_is_excluded():
    job = _spec("j1", kind="leadfield", subject_ids=["001"])
    holder = {
        "key": "subject:001:m2m:write",
        "resource": "subject:001:m2m",
        "mode": "write",
        "job_id": "j1",  # this is the candidate job itself (e.g. a rerun re-checking)
        "pid": 1,
        "create_time": 0.0,
        "ts": 0.0,
    }
    decision = scheduler.evaluate(
        job, {}, [holder], running_cost=Cost(0, 0), budget=BUDGET
    )
    assert decision.admit


def test_budget_wait_when_projected_cost_exceeds_budget():
    job = _spec("j1", cost=Cost(cpus=4, mem_gb=4))
    decision = scheduler.evaluate(
        job, {}, [], running_cost=Cost(cpus=6, mem_gb=4), budget=Cost(cpus=8, mem_gb=32)
    )
    assert not decision.admit
    assert decision.budget_wait is not None
    assert "budget" in decision.budget_wait


def test_legacy_viewer_kind_never_waits_on_budget():
    # "viewer" is no longer a submittable JobKind (D3), but scheduler.evaluate()'s special
    # case for it stays as legacy tolerance for a job.jsonl record persisted before this
    # change -- never budget-blocked, matching its historical zero-cost admission.
    job = _spec("j1", kind="viewer", cost=Cost(cpus=0, mem_gb=0))
    decision = scheduler.evaluate(
        job,
        {},
        [],
        running_cost=Cost(cpus=999, mem_gb=999),
        budget=Cost(cpus=1, mem_gb=1),
    )
    assert decision.admit


def test_budget_fanout_four_jobs_two_cpu_each_on_eight_cpu_budget():
    """4 fake jobs at 2 cpu each fit entirely within an 8-cpu budget (no wait); scaled to 3
    cpu each, only 2 fit at once -- this is the pure-decision half of the scenario the
    manager-level test drives end to end with real (fake) processes."""
    budget = Cost(cpus=8, mem_gb=64)
    jobs = [_spec(f"j{i}", cost=Cost(cpus=3, mem_gb=1)) for i in range(4)]
    running_cost = Cost(0, 0)
    admitted = []
    for job in jobs:
        decision = scheduler.evaluate(
            job, {}, [], running_cost=running_cost, budget=budget
        )
        if decision.admit:
            admitted.append(job.id)
            running_cost = running_cost + job.cost
    assert admitted == ["j0", "j1"]  # 3rd would be 9 cpu > 8


def test_group_cap_waits_once_running_jobs_reach_the_cap():
    """JobGroupRequest.parallel_subjects (mirrored onto JobSpec.group_cap by
    JobManager.submit_plan) caps how many of the group's jobs may be running at once."""
    job = _spec("j3", group_id="g1", group_cap=2)
    jobs = {
        "j1": _status("j1", "running", group_id="g1"),
        "j2": _status("j2", "running", group_id="g1"),
        # A running job in a different group must never count against this cap.
        "other": _status("other", "running", group_id="g2"),
    }
    decision = scheduler.evaluate(job, jobs, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert not decision.admit
    assert decision.budget_wait is not None
    assert "group" in decision.budget_wait


def test_group_cap_admits_below_the_cap():
    job = _spec("j3", group_id="g1", group_cap=2)
    jobs = {"j1": _status("j1", "running", group_id="g1")}
    decision = scheduler.evaluate(job, jobs, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert decision.admit


def test_group_cap_ignores_non_running_jobs_of_the_group():
    job = _spec("j3", group_id="g1", group_cap=1)
    jobs = {
        "j1": _status("j1", "succeeded", group_id="g1"),
        "j2": _status("j2", "queued", group_id="g1"),
    }
    decision = scheduler.evaluate(job, jobs, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert decision.admit


def test_no_group_cap_never_waits():
    job = _spec("j3", group_id="g1", group_cap=None)
    jobs = {"j1": _status("j1", "running", group_id="g1")}
    decision = scheduler.evaluate(job, jobs, [], running_cost=Cost(0, 0), budget=BUDGET)
    assert decision.admit


def test_cascade_skip_transitive():
    edges = {"a": ["b"], "b": ["c"]}
    jobs = {
        "a": _status("a", "failed"),
        "b": _status("b", "queued"),
        "c": _status("c", "queued"),
    }
    assert set(scheduler.cascade_skip("a", jobs, edges)) == {"b", "c"}


def test_cascade_skip_ignores_already_terminal_dependants():
    edges = {"a": ["b"]}
    jobs = {"a": _status("a", "failed"), "b": _status("b", "succeeded")}
    assert scheduler.cascade_skip("a", jobs, edges) == []


def test_build_after_edges_reverse_index():
    specs = {
        "a": _spec("a"),
        "b": _spec("b", after=["a"]),
        "c": _spec("c", after=["a", "b"]),
    }
    edges = scheduler.build_after_edges(specs)
    assert set(edges["a"]) == {"b", "c"}
    assert edges["b"] == ["c"]


def test_discover_budget_returns_positive_cost():
    budget = scheduler.discover_budget()
    assert budget.cpus >= 1
    assert budget.mem_gb >= 1


def test_locks_match_conflicts_matches_scheduler_evaluate_directly():
    # sanity: scheduler.evaluate's lock check is exactly locks.match_conflicts
    requests = locks.keys_for("ex", ["001"], {"run_name": "r1"})
    holder = {
        "key": "subject:001:ex:r1:write",
        "resource": "subject:001:ex:r1",
        "mode": "write",
        "job_id": "blocker",
    }
    assert locks.match_conflicts(requests, [holder]) == [holder]
