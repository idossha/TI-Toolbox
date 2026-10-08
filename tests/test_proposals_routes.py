"""``/api/proposals`` + ``/api/sim-from-flex``: an agent proposes, the user approves, the server runs.

What this pins (ARCHITECTURE §6, 2026-10-07): a proposal is planned on creation (outputs,
overwrites, ETA); the user can edit a pending step and what is approved is what runs; reject
keeps the note and queues nothing; approval is refused while a step would replace output it was
not allowed to; approved root steps are queued at once as ``created_by: "agent"`` jobs tagged
with the proposal; a ``sim_from_flex`` step is queued by the server itself when its flex step's
job succeeds, with the montage and currents read from that run; a failed prerequisite skips its
dependants and ``run`` retries; every change reaches ``/ws/jobs``.

Where the numbers come from: the flex run on disk (``flex_meta.json`` current_mA = 2.0 and an
``electrode_mapping_GSN-HydroCel-185.json`` with labels E1..E4) is written by this file, so the
expected montage ([[E1, E2], [E3, E4]] on that net, 2.0 mA per channel) is authored here and
read back through the server, not computed by the code under test. Jobs run on the fake runner
(``tests/fake_runner.py``), which writes no outputs.

Reproduce: .venv/bin/python -m pytest tests/test_proposals_routes.py -q
Deliberately elsewhere: the direct-submission refusal (tests/test_jobs_routes.py), the MCP verbs
(tests/test_agent_plugin_jobs.py), the card (desktop/tests/unit/proposal-card.test.tsx).
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
    TOKEN,
    WS,
    _reset_job_manager,
    _sim_config,
    client,
    project,
    settings,
    wait_until,
)
from tit.jobs.registry import spec_path  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402

NET = "GSN-HydroCel-185.csv"
MONTAGE = _sim_config("001")["montages"][0]
SPHERE = {
    "_type": "SphericalROI",
    "x": [0.0],
    "y": [0.0],
    "z": [0.0],
    "radius": [10.0],
    "use_mni": False,
    "volumetric": False,
    "tissues": "GM",
}
#: The FlexConfig fields with no dataclass default (the agent plugin fills them from the app).
FLEX = {
    "goal": "mean",
    "postproc": "max_TI",
    "current_mA": 1.0,
    "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4},
    "roi": SPHERE,
}


def sim_step(step_id="sim", montage_name="m1", **extra):
    return {
        "id": step_id,
        "kind": "sim",
        "config": {"montages": [{**MONTAGE, "name": montage_name}]},
        "subject_ids": ["001"],
        **extra,
    }


def propose(client: TestClient, *steps, title="Simulate m1") -> dict:
    r = client.post(
        "/api/proposals",
        headers=BEARER,
        json={
            "title": title,
            "rationale": "because the user asked",
            "client": "Claude Code",
            "steps": list(steps) or [sim_step()],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def get(client: TestClient, pid: str) -> dict:
    return client.get(f"/api/proposals/{pid}", headers=BEARER).json()


def job_spec(project: Path, job_id: str) -> dict:
    return json.loads(Path(spec_path(str(project), job_id)).read_text())


def finished(client: TestClient, pid: str) -> dict:
    return wait_until(
        lambda: (p := get(client, pid))["status"] in ("succeeded", "failed") and p
    )


def test_create_plans_every_step_and_waits_for_the_user(
    client: TestClient, project: Path
) -> None:
    with client.websocket_connect(f"{WS}?token={TOKEN}") as ws:
        proposal = propose(client)
        message = ws.receive_json()
    assert message["type"] == "proposal" and message["proposal"]["id"] == proposal["id"]
    assert proposal["status"] == "pending" and proposal["client"] == "Claude Code"
    assert proposal["created_by"] == "agent" and not proposal["edited"]
    [step] = proposal["steps"]
    assert step["state"] == "proposed" and step["job_ids"] == []
    pm = get_path_manager(str(project))
    assert step["plan"]["outputs"][0]["output_dir"] == pm.simulation("001", "m1")
    assert step["plan"]["errors"] == [] and step["plan"]["will_overwrite"] == []
    assert client.get("/api/jobs", headers=BEARER).json() == []
    listed = client.get("/api/proposals", headers=BEARER).json()
    assert [p["id"] for p in listed] == [proposal["id"]]
    pending = client.get("/api/proposals?status=pending", headers=BEARER).json()
    assert len(pending) == 1


def test_reject_keeps_the_note_and_queues_nothing(client: TestClient) -> None:
    pid = propose(client)["id"]
    r = client.post(
        f"/api/proposals/{pid}/reject", headers=BEARER, json={"note": "use 2 mA"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["decision"]["note"] == "use 2 mA"
    assert (
        client.post(f"/api/proposals/{pid}/approve", headers=BEARER).status_code == 409
    )
    assert client.get("/api/jobs", headers=BEARER).json() == []


def test_the_edited_step_is_what_runs(client: TestClient, project: Path) -> None:
    pid = propose(client)["id"]
    edited = {"montages": [{**MONTAGE, "name": "m2"}], "intensities": [2.0, 2.0]}
    r = client.patch(
        f"/api/proposals/{pid}/steps/sim", headers=BEARER, json={"config": edited}
    )
    assert r.status_code == 200, r.text
    pm = get_path_manager(str(project))
    assert r.json()["steps"][0]["plan"]["outputs"][0]["output_dir"] == pm.simulation(
        "001", "m2"
    )
    assert r.json()["edited"] is True

    approved = client.post(
        f"/api/proposals/{pid}/approve", headers=BEARER, json={"note": "ok"}
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["decision"]["state"] == "approved"
    assert body["proposed_steps"][0]["config"]["montages"][0]["name"] == "m1"
    [job_id] = body["steps"][0]["job_ids"]
    spec = job_spec(project, job_id)
    assert spec["created_by"] == "agent"
    assert spec["tags"] == [f"proposal:{pid}"]
    assert spec["config"]["montages"][0]["name"] == "m2"
    assert spec["config"]["intensities"] == [2.0, 2.0]
    assert finished(client, pid)["status"] == "succeeded"


def test_approve_with_edits_in_the_body(client: TestClient, project: Path) -> None:
    pid = propose(client)["id"]
    r = client.post(
        f"/api/proposals/{pid}/approve",
        headers=BEARER,
        json={
            "steps": [
                {"id": "sim", "config": {"montages": [{**MONTAGE, "name": "m3"}]}}
            ]
        },
    )
    assert r.status_code == 200, r.text
    [job_id] = r.json()["steps"][0]["job_ids"]
    assert job_spec(project, job_id)["config"]["montages"][0]["name"] == "m3"


def test_approval_is_refused_while_a_step_would_replace_output(
    client: TestClient, project: Path
) -> None:
    earlier = Path(get_path_manager(str(project)).simulation("001", "m1"))
    earlier.mkdir(parents=True)
    (earlier / "TI.msh").write_bytes(b"")  # a non-empty folder is a previous result
    proposal = propose(client)
    pid = proposal["id"]
    assert proposal["steps"][0]["plan"]["will_overwrite"]
    refused = client.post(f"/api/proposals/{pid}/approve", headers=BEARER)
    assert refused.status_code == 409 and "replace existing output" in refused.text
    assert get(client, pid)["status"] == "pending"
    assert client.get("/api/jobs", headers=BEARER).json() == []

    r = client.patch(
        f"/api/proposals/{pid}/steps/sim", headers=BEARER, json={"overwrite": True}
    )
    assert r.status_code == 200
    approved = client.post(f"/api/proposals/{pid}/approve", headers=BEARER)
    assert approved.status_code == 200, approved.text
    assert job_spec(project, approved.json()["steps"][0]["job_ids"][0])["overwrite"]


def write_flex_run(project: Path, run: str) -> None:
    """A finished flex run as the optimizer leaves it: manifest + one mapped net."""
    folder = Path(get_path_manager(str(project)).flex_search("001")) / run
    folder.mkdir(parents=True)
    (folder / "flex_meta.json").write_text(
        json.dumps(
            {"goal": "mean", "current_mA": 2.0, "created": "2026-10-07T10:00:00"}
        )
    )
    (folder / "electrode_mapping_GSN-HydroCel-185.json").write_text(
        json.dumps({"eeg_net": NET, "mapped_labels": ["E1", "E2", "E3", "E4"]})
    )


def test_sim_from_flex_is_queued_by_the_server_when_its_flex_finishes(
    client: TestClient, project: Path
) -> None:
    write_flex_run(project, "thalamus")
    proposal = propose(
        client,
        {
            "id": "opt",
            "kind": "flex",
            "config": {**FLEX, "output_folder": "thalamus"},
            "subject_ids": ["001"],
            "overwrite": True,
        },
        {
            "id": "simulate",
            "kind": "sim_from_flex",
            "config": {"flex_step": "opt", "conductivity": "scalar"},
            "subject_ids": ["001"],
        },
    )
    pid = proposal["id"]
    flex, sim = proposal["steps"]
    assert sim["after"] == ["opt"] and sim["plan"]["deferred"]
    assert flex["plan"]["will_overwrite"], flex["plan"]  # the warning the card shows

    approved = client.post(f"/api/proposals/{pid}/approve", headers=BEARER)
    assert approved.status_code == 200, approved.text
    flex, sim = approved.json()["steps"]
    assert (
        len(flex["job_ids"]) == 1 and sim["state"] == "waiting" and not sim["job_ids"]
    )

    done = finished(client, pid)
    assert done["status"] == "succeeded", done
    [sim_job] = done["steps"][1]["job_ids"]
    spec = job_spec(project, sim_job)
    assert spec["kind"] == "sim" and spec["created_by"] == "agent"
    assert spec["config"]["montages"][0]["electrode_pairs"] == [
        ["E1", "E2"],
        ["E3", "E4"],
    ]
    assert spec["config"]["montages"][0]["eeg_net"] == NET
    assert spec["config"]["montages"][0]["name"] == "thalamus"
    assert spec["config"]["intensities"] == [2.0, 2.0]
    assert done["steps"][1]["resolved"]["001"]["intensities_from"].startswith(
        "the run's"
    )


def test_a_failed_prerequisite_skips_its_dependants_and_run_retries(
    client: TestClient, project: Path
) -> None:
    proposal = propose(
        client,
        {
            "id": "opt",
            "kind": "flex",
            "config": {**FLEX, "output_folder": "nothing_here"},
            "subject_ids": ["001"],
        },
        {
            "id": "simulate",
            "kind": "sim_from_flex",
            "config": {"flex_step": "opt"},
            "subject_ids": ["001"],
        },
    )
    pid = proposal["id"]
    assert (
        client.post(f"/api/proposals/{pid}/approve", headers=BEARER).status_code == 200
    )
    # The fake flex job "succeeds" without writing a run, so the montage cannot be resolved:
    # the deferred step errors instead of queuing a simulation of nothing.
    done = finished(client, pid)
    assert done["status"] == "failed"
    assert done["steps"][1]["state"] == "error"
    assert "no finished flex-search run" in done["steps"][1]["error"]

    write_flex_run(project, "nothing_here")
    r = client.post(f"/api/proposals/{pid}/steps/simulate/run", headers=BEARER)
    assert r.status_code == 200, r.text
    assert len(r.json()["steps"][1]["job_ids"]) == 1
    assert finished(client, pid)["status"] == "succeeded"
    again = client.post(f"/api/proposals/{pid}/steps/simulate/run", headers=BEARER)
    assert again.status_code == 409


def test_bad_proposals_are_422(client: TestClient) -> None:
    bad_steps = [
        [],
        [{**sim_step(), "kind": "nope"}],
        [sim_step(), sim_step()],  # duplicate id
        [sim_step(after=["later"])],
        [{**sim_step(), "subject_ids": ["../x"]}],
        [{"id": "s", "kind": "sim_from_flex", "config": {}, "subject_ids": ["001"]}],
        [
            sim_step(),
            {
                "id": "s2",
                "kind": "sim_from_flex",
                "config": {"flex_step": "sim"},
                "subject_ids": ["001"],
            },
        ],
    ]
    for steps in bad_steps:
        r = client.post(
            "/api/proposals", headers=BEARER, json={"title": "x", "steps": steps}
        )
        assert r.status_code == 422, (steps, r.text)
    no_title = client.post(
        "/api/proposals", headers=BEARER, json={"steps": [sim_step()]}
    )
    assert no_title.status_code == 422
    assert client.get("/api/proposals/..%2F..%2Fetc", headers=BEARER).status_code == 404
    assert (
        client.get("/api/proposals/0123456789abcdef", headers=BEARER).status_code == 404
    )


def test_sim_from_flex_route_resolves_the_run(
    client: TestClient, project: Path
) -> None:
    write_flex_run(project, "thalamus")
    r = client.get("/api/sim-from-flex?subject=001", headers=BEARER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["flex_run"] == "thalamus" and body["eeg_net"] == NET
    assert body["montage"]["mode"] == "flex_mapped"
    assert body["intensities"] == [2.0, 2.0]
    missing = client.get("/api/sim-from-flex?subject=001&flex_run=nope", headers=BEARER)
    assert missing.status_code == 404 and "thalamus" in missing.text


def test_a_failed_step_skips_the_steps_that_wait_on_it(client: TestClient) -> None:
    proposal = propose(
        client,
        {
            "id": "first",
            "kind": "tools",
            "config": {"__fake": {"fail": True}},
            "subject_ids": ["001"],
        },
        sim_step(after=["first"]),
    )
    pid = proposal["id"]
    assert (
        client.post(f"/api/proposals/{pid}/approve", headers=BEARER).status_code == 200
    )
    done = finished(client, pid)
    assert [s["state"] for s in done["steps"]] == ["failed", "skipped"]
    assert "first" in done["steps"][1]["skipped"]
    assert done["steps"][1]["job_ids"] == []


def ids(client: TestClient, query: str = "") -> list[str]:
    return [p["id"] for p in client.get(f"/api/proposals{query}", headers=BEARER).json()]


def test_dismiss_hides_a_finished_plan_and_broadcasts(client: TestClient) -> None:
    pid = propose(client)["id"]
    client.post(f"/api/proposals/{pid}/reject", headers=BEARER, json={})
    with client.websocket_connect(f"{WS}?token={TOKEN}") as ws:
        r = client.post(f"/api/proposals/{pid}/dismiss", headers=BEARER)
        message = ws.receive_json()
    assert r.status_code == 200 and r.json()["dismissed_at"]
    assert message["type"] == "proposal" and message["proposal"]["dismissed_at"]
    assert ids(client) == []
    assert ids(client, "?include_dismissed=true") == [pid]
    assert get(client, pid)["status"] == "rejected"  # still readable by id


def test_a_waiting_plan_cannot_be_dismissed(client: TestClient) -> None:
    pid = propose(client)["id"]
    r = client.post(f"/api/proposals/{pid}/dismiss", headers=BEARER)
    assert r.status_code == 409
    assert ids(client) == [pid]


def test_a_finished_approved_plan_can_be_dismissed(client: TestClient) -> None:
    pid = propose(client)["id"]
    client.post(f"/api/proposals/{pid}/approve", headers=BEARER, json={})
    assert finished(client, pid)["status"] == "succeeded"
    assert client.post(f"/api/proposals/{pid}/dismiss", headers=BEARER).status_code == 200
    assert ids(client) == []
