"""``GET /api/catalog/overview`` -- the Overview page's one aggregate read (R1).

Two halves: the pure state machine in
:mod:`tit.server.routes.overview` (``presence`` / ``job_states_by_subject``,
which is where "pending", "partial" and "failed" become distinguishable), and
the route itself over a real temporary project tree through ``TestClient``, so
the aggregation is exercised against :mod:`tit.catalog`'s own discovery rules
rather than against a mock of them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes.overview import (  # noqa: E402
    build_overview,
    job_states_by_subject,
    presence,
)
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


# ── the pure part: four states that answer four different questions ──────────


def test_presence_on_disk_wins_over_any_job_state() -> None:
    assert presence(True) == "present"
    assert (
        presence(True, column="m2m", job_states={"pre": "pending"}) == "present"
    ), "an artefact that exists is present even while a job runs"


def test_presence_partial_absent_pending_failed_are_distinct() -> None:
    assert presence(False) == "absent"
    assert presence(False, partial=True) == "partial"
    assert presence(False, column="m2m", job_states={"pre": "pending"}) == "pending"
    assert presence(False, column="m2m", job_states={"pre": "failed"}) == "failed"
    # a column no job kind produces can never be pending/failed
    assert presence(False, column="eeg_net", job_states={"pre": "failed"}) == "absent"


def test_job_states_take_the_newest_job_per_subject_and_kind() -> None:
    jobs = [  # manager order: newest first
        {"kind": "pre", "state": "succeeded", "subject_ids": ["101"]},
        {"kind": "pre", "state": "failed", "subject_ids": ["101"]},
        {"kind": "leadfield", "state": "failed", "subject_ids": ["101", "102"]},
        {"kind": "pre", "state": "running", "subject_ids": ["102"]},
    ]
    states = job_states_by_subject(jobs)
    assert "pre" not in states.get("101", {}), "a succeeded job is not a column state"
    assert states["101"]["leadfield"] == "failed"
    assert states["102"]["pre"] == "pending"
    assert states["102"]["leadfield"] == "failed"


def test_a_running_job_outranks_an_older_failure() -> None:
    jobs = [
        {"kind": "pre", "state": "failed", "subject_ids": ["101"]},
        {"kind": "pre", "state": "running", "subject_ids": ["101"]},
    ]
    # Newest-first order would stop at "failed"; an active job still wins, because
    # something is happening right now.
    assert job_states_by_subject(jobs)["101"]["pre"] == "pending"


# ── the route, over a real project tree ──────────────────────────────────────


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """``ernie`` (m2m + net + leadfield + a sim + a flex run), ``101`` (raw only),
    ``102`` (DICOMs staged under sourcedata/ and nothing else)."""
    pm = get_path_manager(str(tmp_path))

    m2m = pm.m2m("ernie")
    os.makedirs(m2m)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1")
    eeg_dir = pm.eeg_positions("ernie")
    os.makedirs(eeg_dir)
    Path(eeg_dir, "GSN-HydroCel-185.csv").write_text("Electrode,1,2,3,E001\n")
    leadfields_dir = pm.leadfields("ernie")
    os.makedirs(leadfields_dir)
    Path(leadfields_dir, "ernie_leadfield_GSN-HydroCel-185.hdf5").write_bytes(b"0" * 8)
    os.makedirs(pm.bids_subject("ernie"))
    sim_dir = pm.simulation("ernie", "L_Insula")
    os.makedirs(os.path.join(sim_dir, "documentation"))
    flex_run = pm.flex_search_run("ernie", "20260101_000000")
    os.makedirs(flex_run)
    Path(flex_run, "flex_meta.json").write_text(json.dumps({"goal": "mean", "roi": {}}))

    os.makedirs(pm.bids_subject("101"))

    staged = os.path.join(pm.sourcedata_subject("102"), "T1w")
    os.makedirs(staged)
    Path(staged, "0001.dcm").write_bytes(b"d")

    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def test_overview_is_one_request_for_the_whole_project(client: TestClient) -> None:
    body = client.get("/api/catalog/overview", headers=BEARER).json()
    ids = [s["id"] for s in body["subjects"]]
    # 102 is known only from sourcedata/ -- list_all_subjects territory, and exactly
    # the subject the old fan-out could not show a count for.
    assert ids == ["101", "102", "ernie"]
    assert body["totals"]["subjects"] == 3


def test_columns_and_counts_per_subject(client: TestClient) -> None:
    rows = {s["id"]: s for s in client.get("/api/catalog/overview", headers=BEARER).json()["subjects"]}

    ernie = rows["ernie"]
    assert ernie["raw"] == "present"
    assert ernie["m2m"] == "present"
    assert ernie["fastsurfer"] == "absent"
    assert ernie["eeg_net"] == "present"
    assert ernie["leadfield"] == "present"
    assert ernie["leadfields"] == ["GSN-HydroCel-185.csv"]
    assert ernie["counts"] == {"simulations": 1, "optimizations": 1, "analyses": 0}

    # Staged DICOMs, never converted: `partial`, not `absent`.
    assert rows["102"]["raw"] == "partial"
    assert rows["101"]["raw"] == "present"
    assert rows["101"]["m2m"] == "absent"


def test_readiness_carries_the_requirement_that_failed(client: TestClient) -> None:
    rows = {s["id"]: s for s in client.get("/api/catalog/overview", headers=BEARER).json()["subjects"]}
    stages = {r["stage"]: r for r in rows["101"]["readiness"]}
    assert stages["preprocess"]["ready"] is True
    assert stages["simulator"] == {
        "stage": "simulator",
        "ready": False,
        "reason": "no head model",
    }
    assert stages["optimizer"]["reason"] == "no head model"
    assert stages["analyzer"]["reason"] == "no simulations"
    # sourcedata-only 102 can still be pre-processed (that is where conversion runs)
    st102 = {r["stage"]: r["ready"] for r in rows["102"]["readiness"]}
    assert st102["preprocess"] is True


def test_totals_and_coverage_are_server_owned(client: TestClient) -> None:
    totals = client.get("/api/catalog/overview", headers=BEARER).json()["totals"]
    assert totals["simulations"] == 1
    assert totals["optimizations"] == 1
    coverage = {t["id"]: (t["have"], t["total"]) for t in totals["coverage"]}
    assert coverage["raw"] == (2, 3)
    assert coverage["m2m"] == (1, 3)
    assert coverage["leadfield"] == (1, 3)


def test_no_subjects_is_an_empty_overview(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    (empty / "derivatives").mkdir(parents=True)
    pm = get_path_manager(str(empty))
    body = build_overview(pm, [])
    assert body.subjects == []
    assert body.totals.subjects == 0


def test_a_pending_job_shows_on_the_column_it_would_produce(project: Path) -> None:
    pm = get_path_manager(str(project))
    body = build_overview(
        pm, [{"kind": "pre", "state": "running", "subject_ids": ["101"]}]
    )
    row = next(s for s in body.subjects if s.id == "101")
    assert row.m2m == "pending"
    assert row.raw == "present", "on disk still wins"
