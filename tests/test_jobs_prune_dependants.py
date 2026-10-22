"""Pruned jobs leave the API, a deleted succeeded dependency still counts, retention orders by time.

What this pins (2026-10-22, package p18 "prune-and-delete-dependants"):

1. ``JobManager.start()`` used to prune the store *after* loading it into memory, so the records
   retention had just deleted stayed listed (with empty logs) until the next restart.
2. ``delete()`` of a succeeded job forgot it entirely, and the scheduler then skipped every queued
   job that named it in ``after`` with "dependency <id> is unknown" -- although a succeeded
   dependency is satisfied (``tit.jobs.scheduler._dependency_state``).
3. ``tit.jobs.registry.expired`` ordered records by the *string* ``created_at``, so mixed
   ``Z``/``+05:00``/naive timestamps were pruned in the wrong order, and a naive timestamp was
   read in the machine's local zone instead of UTC (every timestamp the store writes is UTC,
   ``tit.jobs.spec.utcnow_iso``).

Where the expected values come from: the retention rule's docstring (drop records finished more
than ``keep_days`` ago, then the oldest beyond the newest ``keep_count``), its default of 200, and
hand-converted UTC instants for the timestamp table (comments give the conversion).

Run: ``python -m pytest tests/test_jobs_prune_dependants.py -q -p no:cacheprovider``.
Deliberately elsewhere: running/queued records surviving retention
(``tests/test_jobs_registry.py``).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from tit.jobs.manager import JobManager
from tit.jobs.registry import JobRegistry, expired, jobs_root, stdout_path
from tit.jobs.spec import Cost, JobSpec, JobStatus

FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "fake_runner.py")
#: The retention rule's documented default (keep the newest 200 finished records).
KEEP_COUNT = 200


def _fake_command_for(kind, config, spec_path):
    return [sys.executable, FAKE_RUNNER, spec_path]


def _manager(project: str, budget: Cost) -> JobManager:
    manager = JobManager(
        project,
        runner_cwd=project,
        poll_interval=0.05,
        budget=budget,
        command_for=_fake_command_for,
    )
    manager.start()
    return manager


def _wait_state(manager, job_id, states, timeout=10.0):
    deadline = time.monotonic() + timeout
    status = manager.get(job_id)
    while time.monotonic() < deadline and status["state"] not in states:
        time.sleep(0.02)
        status = manager.get(job_id)
    return status


# -- 1. prune happens before the store is loaded ------------------------------------------------


def test_records_pruned_at_start_are_not_listed_and_every_listed_log_exists(tmp_path):
    project = str(tmp_path)
    registry = JobRegistry(project)
    base = datetime.now(timezone.utc) - timedelta(hours=1)  # all well inside 30 days
    ids = [f"job{i:03d}" for i in range(KEEP_COUNT + 5)]
    for i, job_id in enumerate(ids):
        stamp = (base + timedelta(seconds=i)).isoformat()
        spec = JobSpec(
            id=job_id,
            kind="tools",
            config={},
            subject_ids=[],
            created_at=stamp,
        )
        status = JobStatus.queued(spec)
        status.state = "succeeded"
        status.finished_at = stamp
        registry.create(spec, status)
        with open(stdout_path(project, job_id), "w", encoding="utf-8") as fh:
            fh.write(f"log of {job_id}\n")

    manager = _manager(project, Cost(cpus=8, mem_gb=64))
    try:
        listed = {j["id"] for j in manager.list_jobs()}
        on_disk = {
            name for name in os.listdir(jobs_root(project)) if not name.startswith(".")
        }
        assert listed == on_disk
        assert len(listed) == KEEP_COUNT
        # The five oldest (created first) are the ones the count rule drops.
        assert listed == set(ids[5:])
        for job_id in listed:
            assert manager.get_log(job_id) == f"log of {job_id}\n"
        for job_id in ids[:5]:
            assert manager.get(job_id) is None
            assert manager.get_log(job_id) is None
    finally:
        manager.shutdown()


# -- 2. deleting a succeeded dependency ---------------------------------------------------------


def test_deleting_a_succeeded_dependency_does_not_skip_its_queued_dependant(tmp_path):
    # One CPU: while `blocker` runs, the dependant cannot be admitted and stays queued.
    manager = _manager(str(tmp_path), Cost(cpus=1, mem_gb=64))
    try:
        dep = manager.submit("tools", {"__fake": {"duration_s": 0.05}}, [])
        assert _wait_state(manager, dep["id"], ("succeeded",))["state"] == "succeeded"

        blocker = manager.submit("tools", {"__fake": {"duration_s": 30.0}}, [])
        assert _wait_state(manager, blocker["id"], ("running",))["state"] == "running"
        dependant = manager.submit(
            "tools", {"__fake": {"duration_s": 0.05}}, [], after=[dep["id"]]
        )
        # The scheduler has evaluated it: dependency satisfied, held back by the budget only.
        deadline = time.monotonic() + 10.0
        while manager._status[dependant["id"]].budget_wait is None:
            assert time.monotonic() < deadline, "the dependant was never evaluated"
            time.sleep(0.02)
        assert manager.get(dependant["id"])["state"] == "queued"

        assert manager.delete(dep["id"]) == "deleted"
        assert manager.get(dep["id"]) is None

        manager.cancel(blocker["id"])
        final = _wait_state(
            manager, dependant["id"], ("succeeded", "failed", "skipped", "cancelled")
        )
        assert final["state"] == "succeeded", final["error"]
    finally:
        manager.shutdown()


def test_deleting_a_failed_dependency_still_skips_the_dependant(tmp_path):
    """Control: only a *succeeded* dependency is satisfied; a failed one skips its dependant."""
    manager = _manager(str(tmp_path), Cost(cpus=8, mem_gb=64))
    try:
        dep = manager.submit("tools", {"__fake": {"fail": True}}, [])
        assert _wait_state(manager, dep["id"], ("failed",))["state"] == "failed"
        dependant = manager.submit("tools", {}, [], after=[dep["id"]])
        final = _wait_state(manager, dependant["id"], ("skipped", "succeeded"))
        assert final["state"] == "skipped"
        assert manager.delete(dep["id"]) == "deleted"
    finally:
        manager.shutdown()


# -- 3. the retention rule orders by instant, not by string ------------------------------------


#: id -> created_at, with its UTC instant worked out by hand.
MIXED = [
    ("plus5", "2026-01-01T10:00:00+05:00"),  # 05:00:00Z
    ("frac", "2026-01-01T05:30:00.250000+00:00"),  # 05:30:00.25Z
    ("zulu", "2026-01-01T06:00:00Z"),  # 06:00:00Z
    ("naive", "2026-01-01T07:00:00"),  # 07:00:00Z (the store writes UTC)
]
#: Oldest first by instant: plus5 < frac < zulu < naive. String order would be
#: frac < zulu < naive < plus5.
ORDER_BY_INSTANT = ["plus5", "frac", "zulu", "naive"]


@pytest.fixture()
def chicago_clock(monkeypatch):
    """A machine clock six hours behind UTC, so a naive time read as local time is visible."""
    monkeypatch.setenv("TZ", "America/Chicago")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize("keep_count", [0, 1, 2, 3, 4])
def test_expired_drops_the_oldest_instants_first(keep_count, chicago_clock):
    now = datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()
    finished = [(rid, stamp, stamp) for rid, stamp in MIXED]
    removed = expired(finished, keep_count=keep_count, keep_days=3650, now=now)
    assert removed == ORDER_BY_INSTANT[: len(MIXED) - keep_count]


def test_a_naive_finish_time_is_read_as_utc(chicago_clock):
    # 30 days before 2026-02-01T00:00Z is 2026-01-02T00:00Z.
    now = datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
    # 23:00 on Jan 1 UTC is before the cutoff; read as Chicago time it would be 05:00Z Jan 2,
    # after the cutoff, and the record would wrongly survive.
    old = ("old", "2026-01-01T00:00:00Z", "2026-01-01T23:00:00")
    # 01:00 on Jan 2 UTC is after the cutoff and must stay.
    young = ("young", "2026-01-01T00:00:00Z", "2026-01-02T01:00:00")
    assert expired([old, young], keep_count=200, keep_days=30, now=now) == ["old"]
