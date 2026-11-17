"""A free-hand (x, y, z) montage is one head model's: no route plans or runs it for two subjects.

Pins (2026-11-17): the owner's rule "every free-hand placement is specific to the head model;
no free-hand should be automatically available to another model". Free-hand electrodes are
millimetres in one subject's head mesh, and SimNIBS projects them onto any other scalp without
complaint, so a wrong-subject run succeeds and looks plausible. Before this, one sim config with
an inline free-hand montage and ``subject_ids: [001, 002]`` was planned by
``POST /api/plan/sim`` and queued by ``POST /api/jobs/groups`` and by an approved proposal as one
job per subject, each with 001's points.

What must keep working: one subject plans and queues; a label (EEG-net) montage still fans out
over several subjects; ``montage_sources`` free-hand placements resolve per subject from each
subject's own ``stim_configs`` file.

Where the values come from: the montages, the stim_configs files and the subjects are authored
here; the refusal's wording is the one rule's (``tit.sim.config.check_xyz_montages_one_subject``)
and each route is asserted to answer with that same text. Reproduce:
``.venv/bin/python -m pytest tests/test_freehand_one_subject.py -q``.
Deliberately elsewhere: the agent plugin's client-side fan-out
(``tests/test_agent_plugin_plan_job.py``), the desktop plan step
(``desktop/tests/unit/plan-step-form.test.ts``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_jobs_routes import (  # noqa: E402,F401  (fixtures)
    BEARER,
    _reset_job_manager,
    _sim_config,
    client,
    project,
    settings,
)
from tit.paths import get_path_manager  # noqa: E402

FREEHAND = {
    "_type": "Montage",
    "name": "hand",
    "mode": "freehand",
    "electrode_pairs": [
        [[-60.0, 10.0, 40.0], [60.0, 10.0, 40.0]],
        [[-60.0, -40.0, 40.0], [60.0, -40.0, 40.0]],
    ],
    "eeg_net": None,
}
FLEX_FREE = {**FREEHAND, "name": "flexfree", "mode": "flex_free"}
REASON = "a free-hand placement belongs to one subject"


def _config(subject_id: str, montage: dict) -> dict:
    return {"subject_id": subject_id, "montages": [montage]}


def _refusal(name: str) -> str:
    """The one rule's sentence for montage *name* on subjects 001 and 002."""
    return (
        f"Montage {name!r} is a free-hand placement (x, y, z on one head model) and "
        f"cannot run for 001, 002: {REASON}."
    )


@pytest.mark.parametrize(
    "montage", [FREEHAND, FLEX_FREE], ids=["freehand", "flex_free"]
)
def test_the_planner_refuses_an_xyz_montage_for_two_subjects(
    client: TestClient, montage: dict
) -> None:
    r = client.post(
        "/api/plan/sim",
        json={"config": _config("001", montage), "subject_ids": ["001", "002"]},
        headers=BEARER,
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == _refusal(montage["name"])


def test_the_planner_refuses_one_subjects_placement_planned_for_another(
    client: TestClient,
) -> None:
    r = client.post(
        "/api/plan/sim",
        json={"config": _config("001", FREEHAND), "subject_ids": ["002"]},
        headers=BEARER,
    )
    assert r.status_code == 422 and REASON in r.json()["detail"]


def test_the_group_route_refuses_the_template_on_two_subjects(
    client: TestClient,
) -> None:
    r = client.post(
        "/api/jobs/groups",
        json={
            "kind": "sim",
            "config": _config("001", FREEHAND),
            "subject_ids": ["001", "002"],
        },
        headers=BEARER,
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == _refusal("hand")
    assert client.get("/api/jobs", headers=BEARER).json() == []


def test_the_group_route_refuses_an_entry_naming_another_subject(
    client: TestClient,
) -> None:
    """The route forces each entry's subject_id to its own; it must not launder 001's points."""
    r = client.post(
        "/api/jobs/groups",
        json={
            "kind": "sim",
            "config": _config("001", FREEHAND),
            "subject_ids": ["001", "002"],
            "subject_configs": [
                {"subject_id": "001", "config": _config("001", FREEHAND)},
                {"subject_id": "002", "config": _config("001", FREEHAND)},
            ],
        },
        headers=BEARER,
    )
    assert r.status_code == 422 and REASON in r.json()["detail"]


def test_one_subject_still_plans_and_queues(client: TestClient) -> None:
    config = _config("001", FREEHAND)
    plan = client.post(
        "/api/plan/sim", json={"config": config, "subject_ids": ["001"]}, headers=BEARER
    )
    assert plan.status_code == 200, plan.text
    assert [j["subject"] for j in plan.json()["jobs"]] == ["001"]
    queued = client.post(
        "/api/jobs/groups",
        json={"kind": "sim", "config": config, "subject_ids": ["001"]},
        headers=BEARER,
    )
    assert queued.status_code == 201, queued.text
    assert len(queued.json()["jobs"]) == 1


def test_each_subjects_own_placement_in_one_group_is_queued(client: TestClient) -> None:
    """The Simulator's batch: one entry per row, each with its own subject's points."""
    other = {
        **FREEHAND,
        "electrode_pairs": [
            [[-50.0, 10.0, 40.0], [50.0, 10.0, 40.0]],
            [[-50.0, -40.0, 40.0], [50.0, -40.0, 40.0]],
        ],
    }
    r = client.post(
        "/api/jobs/groups",
        json={
            "kind": "sim",
            "config": _config("001", FREEHAND),
            "subject_ids": ["001", "002"],
            "subject_configs": [
                {"subject_id": "001", "config": _config("001", FREEHAND)},
                {"subject_id": "002", "config": _config("002", other)},
            ],
        },
        headers=BEARER,
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["jobs"]) == 2


def test_a_label_montage_still_fans_out_over_subjects(client: TestClient) -> None:
    config = _sim_config("001")
    plan = client.post(
        "/api/plan/sim",
        json={"config": config, "subject_ids": ["001", "002"]},
        headers=BEARER,
    )
    assert plan.status_code == 200, plan.text
    assert sorted(j["subject"] for j in plan.json()["jobs"]) == ["001", "002"]
    queued = client.post(
        "/api/jobs/groups",
        json={"kind": "sim", "config": config, "subject_ids": ["001", "002"]},
        headers=BEARER,
    )
    assert queued.status_code == 201, queued.text
    assert len(queued.json()["jobs"]) == 2


def test_montage_sources_resolve_each_subjects_own_placement(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    for sid, x in (("001", 60.0), ("002", 50.0)):
        stim = Path(pm.m2m(sid)) / "stim_configs"
        stim.mkdir()
        positions = {
            "E1+": [-x, 10.0, 40.0],
            "E1-": [x, 10.0, 40.0],
            "E2+": [-x, -40.0, 40.0],
            "E2-": [x, -40.0, 40.0],
        }
        (stim / "hand.json").write_text(
            json.dumps({"name": "hand", "electrode_positions": positions})
        )
    r = client.post(
        "/api/plan/sim",
        json={
            "config": {"subject_id": "001", "montages": []},
            "subject_ids": ["001", "002"],
            "montage_sources": {
                "freehand": [
                    {"subject": "001", "name": "hand"},
                    {"subject": "002", "name": "hand"},
                ]
            },
        },
        headers=BEARER,
    )
    assert r.status_code == 200, r.text
    assert sorted(j["subject"] for j in r.json()["jobs"]) == ["001", "002"]
    firsts = [m["electrode_pairs"][0][0][0] for m in r.json()["resolved"]["montages"]]
    assert sorted(firsts) == [-60.0, -50.0]


def _propose(client: TestClient, subjects: list[str]) -> dict:
    r = client.post(
        "/api/proposals",
        headers=BEARER,
        json={
            "title": "Simulate a placement",
            "steps": [
                {
                    "id": "sim",
                    "kind": "sim",
                    "config": {"montages": [FREEHAND]},
                    "subject_ids": subjects,
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_a_proposal_step_on_two_subjects_is_refused_and_cannot_be_approved(
    client: TestClient,
) -> None:
    proposal = _propose(client, ["001", "002"])
    [step] = proposal["steps"]
    assert step["plan"]["errors"] == [_refusal("hand")]
    r = client.post(f"/api/proposals/{proposal['id']}/approve", headers=BEARER, json={})
    assert r.status_code == 409 and _refusal("hand") in r.json()["detail"]
    assert client.get("/api/jobs", headers=BEARER).json() == []


def test_a_proposal_step_on_one_subject_plans(client: TestClient) -> None:
    [step] = _propose(client, ["001"])["steps"]
    assert step["plan"]["errors"] == []
    assert [o["subject"] for o in step["plan"]["outputs"]] == ["001"]
