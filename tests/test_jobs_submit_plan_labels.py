"""Submitting never marks a job as stranded, and a plan's ``after_labels`` must all resolve.

What this pins (2026-10-22, package p18 "stranded-and-plan-labels"):

1. Commit 690c2cd2 copied ``_load_existing``'s "stranded job" snapshot into ``submit()``. Every
   new job was appended to ``_stranded`` (a list that only startup reconciliation drains), so the
   list grew for the server's whole life, and a job submitted before ``start()`` was failed by
   that reconciliation as "interrupted before start: server restarted" -- although no server had
   restarted.
2. ``submit_plan`` silently dropped an ``after_labels`` entry it could not resolve (a typo, or a
   label defined later in the list), so a hand-tuned plan ran a dependant without its
   dependency. RUN-04 already refuses the same mistake for ``after`` ids in ``submit()``; a plan
   must be refused the same way, before anything is persisted.

Where the expected values come from: the reconciliation contract in
``JobManager._reconcile_all`` (only jobs left over from a *previous* server life are
reconciled), RUN-04's rule for unknown dependencies, and the stage DAG written out in
``tit.jobs.plans.plan_preprocessing``'s docstring (G1 -> G2a -> G3 per subject).

Run: ``python -m pytest tests/test_jobs_submit_plan_labels.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from tit.jobs.manager import JobManager
from tit.jobs.registry import jobs_root
from tit.jobs.spec import Cost, PlannedJob

FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "fake_runner.py")


def _manager(project: str) -> JobManager:
    return JobManager(
        project,
        runner_cwd=project,
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, path: [sys.executable, FAKE_RUNNER, path],
    )


def _wait_terminal(manager, job_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    status = manager.get(job_id)
    while time.monotonic() < deadline and status["state"] in ("queued", "running"):
        time.sleep(0.02)
        status = manager.get(job_id)
    return status


def _records_on_disk(project: str) -> list[str]:
    return [n for n in os.listdir(jobs_root(project)) if not n.startswith(".")]


@pytest.fixture(autouse=True)
def isolated_resource_preferences(tmp_path, monkeypatch):
    # `pre` stage configs resolve thread counts from the user's preferences; keep the host's out.
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "preferences.json"
    )


# -- 1. _stranded ------------------------------------------------------------------------------


def test_a_job_submitted_before_start_runs_instead_of_being_reconciled(tmp_path):
    manager = _manager(str(tmp_path))
    job = manager.submit("tools", {}, [])
    manager.start()
    try:
        final = _wait_terminal(manager, job["id"])
        assert final["state"] == "succeeded", final["error"]
        assert final["exit_code"] == 0
    finally:
        manager.shutdown()


def test_submitting_after_start_leaves_nothing_stranded(tmp_path):
    manager = _manager(str(tmp_path))
    manager.start()
    try:
        ids = [manager.submit("tools", {}, [])["id"] for _ in range(10)]
        assert manager._stranded == []
        for job_id in ids:
            assert _wait_terminal(manager, job_id)["state"] == "succeeded"
    finally:
        manager.shutdown()


# -- 2. after_labels ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "plan",
    [
        pytest.param(
            [
                PlannedJob("b", "tools", {}, [], after_labels=["a"]),
                PlannedJob("a", "tools", {}, []),
            ],
            id="label defined later",
        ),
        pytest.param(
            [
                PlannedJob("a", "tools", {}, []),
                PlannedJob("b", "tools", {}, [], after_labels=["typo"]),
            ],
            id="label never defined",
        ),
        pytest.param(
            [PlannedJob("a", "tools", {}, [], after_labels=["a"])],
            id="label names itself",
        ),
    ],
)
def test_a_plan_with_an_unresolvable_label_is_refused_before_anything_is_stored(
    tmp_path, plan
):
    manager = _manager(str(tmp_path))
    with pytest.raises(ValueError, match="after_labels"):
        manager.submit_plan(plan)
    assert manager.list_jobs() == []
    assert _records_on_disk(str(tmp_path)) == []


def test_a_valid_preprocessing_plan_keeps_its_stage_edges(tmp_path):
    from tit.jobs.plans import plan_preprocessing
    from tit.paths import get_path_manager
    from tit.pre.config import PreprocessConfig

    get_path_manager(str(tmp_path))
    subjects = ["101", "102"]
    planned = plan_preprocessing(
        PreprocessConfig(
            subject_ids=subjects,
            convert_dicom=True,
            create_m2m=True,
            run_tissue_analysis=True,
        ),
        subjects,
    )
    manager = _manager(str(tmp_path))  # not started: this checks the records, not a run
    result = manager.submit_plan(planned)
    jobs = result["jobs"]
    assert len(jobs) == 6

    by_stage = {}
    for job in jobs:
        detail = manager.get_detail(job["id"])
        stage = next(t for t in detail["spec"].get("tags", []) if t.startswith("G"))
        by_stage[(job["subject_ids"][0], stage)] = (
            job["id"],
            detail["spec"].get("after", []),
        )
        assert job["group_id"] == result["group_id"]

    for sid in subjects:
        g1_id, g1_after = by_stage[(sid, "G1")]
        g2a_id, g2a_after = by_stage[(sid, "G2a")]
        _, g3_after = by_stage[(sid, "G3")]
        assert g1_after == []
        assert g2a_after == [g1_id]
        assert g3_after == [g2a_id]
