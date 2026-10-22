"""One malformed job record never kills the scheduler, and a failed start is never cached.

What this pins (2026-10-22, package p18 "malformed-record-start"): the job store is plain JSON
inside the user's project, so a hand edit, a sync conflict or a half-restored backup can leave a
``status.json``/``spec.json`` of the wrong shape. Before this fix ``JobStatus.from_dict`` raised
``TypeError``/``AttributeError`` on such a record, ``JobRegistry.read_status`` caught only
``OSError``/``JSONDecodeError``/``KeyError``, and ``JobManager.start()`` -- which had already set
``_started = True`` -- raised before its loop thread existed. ``bootstrap.get_manager`` had stored
that half-built manager, and the server lifespan suppresses the error, so every job submitted
afterwards stayed ``queued`` forever.

Where the expected values come from: the registry's contract that an unreadable record is
skipped (``read_spec``/``read_status`` return ``None``; ``list_ids`` "skip an unsafe record
without hiding unrelated valid jobs"), so the expected job list is exactly the one valid record
this test wrote; and the job contract that a submitted job runs (``succeeded`` with exit 0 for a
command that exits 0). The records are authored by hand below, one malformed shape each.

Run: ``python -m pytest tests/test_jobs_malformed_records.py -q -p no:cacheprovider``.
Deliberately elsewhere: unsafe (symlinked) records, ``tests/test_jobs_registry.py``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from tit.jobs import bootstrap
from tit.jobs.manager import JobManager
from tit.jobs.registry import JobRegistry, spec_path, status_path
from tit.jobs.spec import Cost

GOOD_ID = "goodjob0000000001"
BAD_ID = "badjob00000000002"
#: An hour ago: well inside the store's 30-day retention, so pruning never removes a record here.
RECENT = datetime.now(timezone.utc) - timedelta(hours=1)


def _iso(offset_s: float) -> str:
    return (RECENT + timedelta(seconds=offset_s)).isoformat()


def _spec(job_id: str) -> dict:
    return {
        "id": job_id,
        "kind": "tools",
        "config": {},
        "subject_ids": [],
        "after": [],
        "tags": [],
        "env": {},
        "locks": [],
        "cost": {"cpus": 1.0, "mem_gb": 1.0},
        "created_by": "api",
        "created_at": _iso(0),
        "group_id": None,
        "overwrite": False,
    }


def _status(job_id: str) -> dict:
    return {
        "id": job_id,
        "kind": "tools",
        "state": "succeeded",
        "subject_ids": [],
        "created_at": _iso(0),
        "started_at": _iso(1),
        "finished_at": _iso(2),
        "exit_code": 0,
        "waiting_on": [],
        "artifacts": [],
    }


def _without(d: dict, key: str) -> dict:
    return {k: v for k, v in d.items() if k != key}


#: name -> (spec.json body, status.json body) of the malformed record.
MALFORMED = {
    "status is a list": lambda: (_spec(BAD_ID), [_status(BAD_ID)]),
    "spec is a list": lambda: ([_spec(BAD_ID)], _status(BAD_ID)),
    "waiting_on holds a string": lambda: (
        _spec(BAD_ID),
        {**_status(BAD_ID), "waiting_on": ["x"]},
    ),
    "artifacts holds null": lambda: (
        _spec(BAD_ID),
        {**_status(BAD_ID), "artifacts": [None]},
    ),
    "progress is a list": lambda: (
        _spec(BAD_ID),
        {**_status(BAD_ID), "progress": []},
    ),
    "cost is a list": lambda: ({**_spec(BAD_ID), "cost": [1, 2]}, _status(BAD_ID)),
    "cost is not a number": lambda: (
        {**_spec(BAD_ID), "cost": {"cpus": "many", "mem_gb": 1}},
        _status(BAD_ID),
    ),
    "created_at missing": lambda: (
        _spec(BAD_ID),
        _without(_status(BAD_ID), "created_at"),
    ),
    "created_at null": lambda: (_spec(BAD_ID), {**_status(BAD_ID), "created_at": None}),
    "subject_ids null": lambda: (
        _spec(BAD_ID),
        {**_status(BAD_ID), "subject_ids": None},
    ),
    "subject_ids a string": lambda: (
        {**_spec(BAD_ID), "subject_ids": "101"},
        {**_status(BAD_ID), "subject_ids": "101"},
    ),
    "state is a number": lambda: (_spec(BAD_ID), {**_status(BAD_ID), "state": 5}),
    "record names another job": lambda: (
        {**_spec(BAD_ID), "id": "someoneelse"},
        {**_status(BAD_ID), "id": "someoneelse"},
    ),
}


def _write(project: str, job_id: str, spec, status) -> None:
    os.makedirs(os.path.join(project, "code", "ti-toolbox", "jobs", job_id))
    with open(spec_path(project, job_id), "w", encoding="utf-8") as fh:
        json.dump(spec, fh)
    with open(status_path(project, job_id), "w", encoding="utf-8") as fh:
        json.dump(status, fh)


def _manager(project: str) -> JobManager:
    return JobManager(
        project,
        runner_cwd=project,
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, path: [sys.executable, "-c", "pass"],
    )


def _wait_terminal(manager: JobManager, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    status = manager.get(job_id)
    while time.monotonic() < deadline and status["state"] in ("queued", "running"):
        time.sleep(0.02)
        status = manager.get(job_id)
    return status


@pytest.mark.parametrize("shape", sorted(MALFORMED))
def test_a_malformed_record_is_skipped_and_the_scheduler_still_runs_jobs(
    tmp_path, shape
):
    project = str(tmp_path)
    JobRegistry(project)  # creates the store (and .bidsignore) like a real first run
    _write(project, GOOD_ID, _spec(GOOD_ID), _status(GOOD_ID))
    spec, status = MALFORMED[shape]()
    _write(project, BAD_ID, spec, status)

    manager = _manager(project)
    try:
        manager.start()  # must not raise
        listed = manager.list_jobs()
        assert [j["id"] for j in listed] == [GOOD_ID]
        assert listed[0]["state"] == "succeeded"
        assert manager.get(BAD_ID) is None

        job = manager.submit("tools", {}, [])
        final = _wait_terminal(manager, job["id"])
        assert final["state"] == "succeeded"
        assert final["exit_code"] == 0
    finally:
        manager.shutdown()
    # Skipped, not destroyed: the malformed record is still on disk for the user to inspect.
    assert os.path.isfile(status_path(project, BAD_ID))


@pytest.mark.parametrize("shape", sorted(MALFORMED))
def test_the_registry_reads_a_malformed_record_as_unreadable(tmp_path, shape):
    project = str(tmp_path)
    registry = JobRegistry(project)
    spec, status = MALFORMED[shape]()
    _write(project, BAD_ID, spec, status)
    # At least one of the two files is unusable; the record as a whole must read as absent.
    assert registry.read_spec(BAD_ID) is None or registry.read_status(BAD_ID) is None


def test_a_start_that_failed_can_be_retried_on_the_same_manager(tmp_path, monkeypatch):
    project = str(tmp_path)
    manager = _manager(project)
    real_load = JobManager._load_existing
    calls = {"n": 0}

    def flaky_load(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("store briefly unreadable")
        return real_load(self)

    monkeypatch.setattr(JobManager, "_load_existing", flaky_load)
    with pytest.raises(OSError):
        manager.start()
    try:
        manager.start()  # a retry really starts the loop, it is not a silent no-op
        assert manager._loop is not None
        job = manager.submit("tools", {}, [])
        assert _wait_terminal(manager, job["id"])["state"] == "succeeded"
    finally:
        manager.shutdown()


def test_bootstrap_never_caches_a_manager_whose_start_failed(tmp_path, monkeypatch):
    from tit.paths import get_path_manager

    get_path_manager(str(tmp_path))
    monkeypatch.setenv(bootstrap.ENV_RUNNER_CWD, str(tmp_path))
    bootstrap.reset_manager()
    real_start = JobManager.start
    calls = {"n": 0}

    def flaky_start(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TypeError("malformed store")
        return real_start(self)

    monkeypatch.setattr(JobManager, "start", flaky_start)
    try:
        with pytest.raises(TypeError):
            bootstrap.get_manager()
        manager = bootstrap.get_manager()  # retried, not the broken instance
        assert calls["n"] == 2
        assert manager._loop is not None
        assert bootstrap.get_manager() is manager
    finally:
        bootstrap.reset_manager()
