"""HTTP + WebSocket tests for ``/api/jobs*`` and ``/ws/jobs``.

Uses a real :class:`~tit.jobs.manager.JobManager` (fake-runner-backed, per
``tests/test_jobs_manager.py``) wired into the app via ``tit.jobs.bootstrap`` — these are true
end-to-end tests of the route <-> manager wiring, not mocks.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-jobs"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
WS = "ws://127.0.0.1:8765/ws/jobs"
FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "fake_runner.py")


def _fake_command_for(kind, config, spec_path):
    return [sys.executable, FAKE_RUNNER, spec_path]


def wait_until(predicate, timeout=10.0, interval=0.02):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s (last: {last!r})")


@pytest.fixture(autouse=True)
def _reset_job_manager():
    yield
    bootstrap.reset_manager()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def settings(project: Path) -> ServerSettings:
    return ServerSettings(project_dir=str(project), token=TOKEN)


@pytest.fixture()
def client(project: Path, settings: ServerSettings) -> TestClient:
    get_path_manager(str(project))
    manager = JobManager(
        str(project),
        runner_cwd=str(project),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=_fake_command_for,
    )
    manager.start()
    bootstrap.set_manager_for_testing(manager)
    return TestClient(create_app(settings), base_url=BASE)


# ---------------------------------------------------------------------------------------------
# submit / list / get / events / log
# ---------------------------------------------------------------------------------------------


def test_job_detail_top_level_shape_is_exactly_the_contract(
    client: TestClient, project: Path
) -> None:
    """FX2 / s2-notes item 3: ``GET /api/jobs/{id}`` is the one job route whose body is *not* a
    bare ``JobStatus`` -- it wraps it (``{spec, status, artifacts}``, ``JobDetail`` in
    ``contracts/openapi.yaml``), while the list route and every submit/cancel/rerun/force
    response are flat. A client that reads ``state`` off the top level here gets ``undefined``
    and a 200, i.e. a poll that never resolves (the exact bug in Level B's own helper). Pinned
    against the contract itself, so flattening the route would fail here rather than in a UI
    timeout."""
    yaml = pytest.importorskip("yaml")

    contract = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1] / "contracts" / "openapi.yaml"
        ).read_text()
    )
    required = contract["components"]["schemas"]["JobDetail"]["required"]
    assert set(required) == {
        "spec",
        "status",
        "artifacts",
    }  # the contract itself, unchanged

    job_id = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 0.05}},
            "subject_ids": ["001"],
        },
    ).json()["id"]
    detail = client.get(f"/api/jobs/{job_id}", headers=BEARER).json()

    assert set(detail) == set(required)
    assert "state" not in detail and detail["status"]["state"] in (
        "queued",
        "running",
        "succeeded",
    )
    assert detail["status"]["id"] == job_id
    assert detail["spec"]["kind"] == "tools"
    # ...and each half carries its own contract-required properties.
    for key in ("spec", "status"):
        schema = contract["components"]["schemas"][
            "JobSpec" if key == "spec" else "JobStatus"
        ]
        assert not set(schema["required"]) - set(detail[key]), key


def test_submit_list_get(client: TestClient, project: Path) -> None:
    r = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 0.1}},
            "subject_ids": ["001"],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["state"] == "queued"
    job_id = body["id"]

    listed = client.get("/api/jobs", headers=BEARER).json()
    assert any(j["id"] == job_id for j in listed)

    filtered = client.get("/api/jobs", params={"subject": "001"}, headers=BEARER).json()
    assert any(j["id"] == job_id for j in filtered)
    empty = client.get("/api/jobs", params={"subject": "999"}, headers=BEARER).json()
    assert not any(j["id"] == job_id for j in empty)

    def _succeeded():
        detail = client.get(f"/api/jobs/{job_id}", headers=BEARER).json()
        return detail if detail["status"]["state"] == "succeeded" else None

    detail = wait_until(_succeeded)
    assert detail["spec"]["kind"] == "tools"
    assert detail["artifacts"] == []
    # ra_13 finding #6: the route serves a real log_path end to end, not a client-reconstructed
    # one -- and GET /api/jobs (list) carries it too, not just the per-job detail route.
    from tit.jobs.registry import stdout_path

    assert detail["status"]["log_path"] == stdout_path(str(project), job_id)
    assert any(j["log_path"] == detail["status"]["log_path"] for j in listed)

    events = client.get(f"/api/jobs/{job_id}/events", headers=BEARER).json()
    assert any(e["type"] == "exit" for e in events)
    since = client.get(
        f"/api/jobs/{job_id}/events", params={"since": len(events)}, headers=BEARER
    ).json()
    assert since == []

    log = client.get(f"/api/jobs/{job_id}/log", headers=BEARER)
    assert log.status_code == 200
    assert "fake_runner" in log.text


def test_submit_validation_errors(client: TestClient) -> None:
    assert (
        client.post("/api/jobs", headers=BEARER, json={"kind": "nope"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/jobs", headers=BEARER, json={"kind": "tools", "config": "not-a-dict"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/jobs",
            headers=BEARER,
            json={"kind": "tools", "config": {}, "subject_ids": "not-a-list"},
        ).status_code
        == 422
    )


def test_submit_rejects_a_subject_id_that_is_not_one(client: TestClient, project: Path) -> None:
    """RUN-05: a subject id becomes a `sub-<id>` path component in every runner downstream.

    Rejected before persistence — no job record, no spec.json, no scaffolded directory.
    """
    before = client.get("/api/jobs", headers=BEARER).json()
    for bad in ("../../../outside", "001/../../x", "a/b", "..", "", "sub 001", 7, None):
        r = client.post(
            "/api/jobs",
            headers=BEARER,
            json={
                "kind": "tools",
                "config": {"__fake": {"duration_s": 0.01}},
                "subject_ids": [bad],
            },
        )
        assert r.status_code == 422, (bad, r.status_code)
        assert "subject id" in str(r.json()["detail"])
    assert client.get("/api/jobs", headers=BEARER).json() == before
    assert not list(project.glob("sub-*"))
    assert not list(project.glob("../outside"))


def test_submit_group_rejects_a_subject_id_that_is_not_one(client: TestClient) -> None:
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": {},
            "subject_ids": ["../../evil"],
            "parallel_subjects": 1,
        },
    )
    assert r.status_code == 422
    assert "subject id" in str(r.json()["detail"])


def test_submit_keeps_valid_subject_ids_exactly_as_given(client: TestClient) -> None:
    for good in ("001", "ernie", "sub-01", "P_01", "01a"):
        r = client.post(
            "/api/jobs",
            headers=BEARER,
            json={
                "kind": "tools",
                "config": {"__fake": {"duration_s": 0.01}},
                "subject_ids": [good],
            },
        )
        assert r.status_code == 201, (good, r.text)
        assert r.json()["subject_ids"] == [good]


def test_submit_rejects_an_after_naming_an_unknown_job(client: TestClient) -> None:
    """RUN-04 through the route: 422, not a job that ignores its own precondition."""
    r = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 0.01}},
            "subject_ids": ["001"],
            "after": ["no-such-job"],
        },
    )
    assert r.status_code == 422
    assert "after" in str(r.json()["detail"])


def test_submit_rejects_a_sim_config_the_runner_could_not_deserialise(
    client: TestClient,
) -> None:
    """Regression: this body was accepted, and only died later inside tit/sim/__main__.py with
    `TypeError: SimulationConfig.__init__() missing 2 required positional arguments`."""
    r = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": {"__mock_fail": False, "__mock_fast": True},
            "subject_ids": ["ernie"],
        },
    )
    assert r.status_code == 422
    assert "SimulationConfig" in r.json()["detail"]
    # A complete config from the same route still submits.
    ok = client.post(
        "/api/jobs",
        headers=BEARER,
        json={"kind": "sim", "config": _sim_config("001"), "subject_ids": ["001"]},
    )
    assert ok.status_code == 201


def test_submit_rejects_legacy_viewer_kind(client: TestClient) -> None:
    """D3: the "viewer" job kind and its freeview/gmsh launch routes are gone (the embedded
    Tetravox viewer needs no server-side job at all). A client still sending the old
    kind="viewer" shape gets the same generic "unknown kind" 422 as any other invalid kind,
    not a stale 403 pointing at a route that no longer exists."""
    r = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "viewer",
            "config": {"program": "freeview", "args": ["-v", "/x/T1.nii.gz"]},
            "subject_ids": [],
        },
    )
    assert r.status_code == 422
    # And no job was actually created.
    assert client.get("/api/jobs", headers=BEARER).json() == []


def test_get_events_log_unknown_job_404(client: TestClient) -> None:
    assert client.get("/api/jobs/nope", headers=BEARER).status_code == 404
    assert client.get("/api/jobs/nope/events", headers=BEARER).status_code == 404
    assert client.get("/api/jobs/nope/log", headers=BEARER).status_code == 404


def test_list_filters_by_state_and_kind_validate_enum(client: TestClient) -> None:
    assert (
        client.get("/api/jobs", params={"state": "bogus"}, headers=BEARER).status_code
        == 422
    )
    assert (
        client.get("/api/jobs", params={"kind": "bogus"}, headers=BEARER).status_code
        == 422
    )
    assert (
        client.get("/api/jobs", params={"state": "queued"}, headers=BEARER).status_code
        == 200
    )


# ---------------------------------------------------------------------------------------------
# cancel / rerun / force / delete
# ---------------------------------------------------------------------------------------------


def test_cancel_rerun_delete_flow(client: TestClient) -> None:
    submitted = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 0.05}},
            "subject_ids": [],
        },
    ).json()
    job_id = submitted["id"]

    def _succeeded():
        s = client.get(f"/api/jobs/{job_id}", headers=BEARER).json()["status"]
        return s if s["state"] == "succeeded" else None

    wait_until(_succeeded)

    assert client.delete(f"/api/jobs/{job_id}", headers=BEARER).status_code == 204
    assert client.get(f"/api/jobs/{job_id}", headers=BEARER).status_code == 404
    assert client.delete(f"/api/jobs/{job_id}", headers=BEARER).status_code == 404


def test_delete_running_job_conflicts(client: TestClient) -> None:
    submitted = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 2.0}},
            "subject_ids": [],
        },
    ).json()
    job_id = submitted["id"]

    def _running():
        s = client.get(f"/api/jobs/{job_id}", headers=BEARER).json()["status"]
        return s if s["state"] == "running" else None

    wait_until(_running)
    assert client.delete(f"/api/jobs/{job_id}", headers=BEARER).status_code == 409
    r = client.post(f"/api/jobs/{job_id}/cancel", headers=BEARER)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert client.delete(f"/api/jobs/{job_id}", headers=BEARER).status_code == 204


def test_rerun_and_force(client: TestClient) -> None:
    original = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 0.05}},
            "subject_ids": ["001"],
        },
    ).json()

    def _succeeded():
        s = client.get(f"/api/jobs/{original['id']}", headers=BEARER).json()["status"]
        return s if s["state"] == "succeeded" else None

    wait_until(_succeeded)
    rerun = client.post(f"/api/jobs/{original['id']}/rerun", headers=BEARER)
    assert rerun.status_code == 201
    assert rerun.json()["id"] != original["id"]

    assert client.post("/api/jobs/nope/rerun", headers=BEARER).status_code == 404
    assert client.post("/api/jobs/nope/force", headers=BEARER).status_code == 404

    long_job = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 5.0}},
            "subject_ids": [],
        },
    ).json()

    def _running():
        s = client.get(f"/api/jobs/{long_job['id']}", headers=BEARER).json()["status"]
        return s if s["state"] == "running" else None

    wait_until(_running)
    forced = client.post(f"/api/jobs/{long_job['id']}/force", headers=BEARER)
    assert forced.status_code == 200
    assert forced.json()["state"] == "lost"


def test_cancel_unknown_job_404(client: TestClient) -> None:
    assert client.post("/api/jobs/nope/cancel", headers=BEARER).status_code == 404


# ---------------------------------------------------------------------------------------------
# groups (501 until B3's plans.py exists)
# ---------------------------------------------------------------------------------------------


def test_groups_submits_a_preprocessing_dag(client: TestClient) -> None:
    # tit.jobs.plans.plan_preprocessing (B3) landed during Stage 1; PreprocessConfig requires a
    # non-empty subject_ids of its own even though plan_preprocessing takes the batch separately.
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "pre",
            "config": {
                "subject_ids": ["001"],
                "convert_dicom": True,
                "create_m2m": True,
            },
            "subject_ids": ["001"],
            "parallel_subjects": 1,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["group_id"]
    kinds = {j["kind"] for j in body["jobs"]}
    # A report is an attachment of the job that produced it, never a job of its own.
    assert kinds == {"pre"}
    assert len(body["jobs"]) == 2  # G1 (dicom) + G2a (charm)

    def _all_done():
        listed = client.get(
            "/api/jobs", params={"subject": "001"}, headers=BEARER
        ).json()
        ours = [j for j in listed if j["group_id"] == body["group_id"]]
        return (
            ours
            if len(ours) == 2 and all(j["state"] != "queued" for j in ours)
            else None
        )

    # Both stage jobs run through this fixture's fake-runner command builder (like every other
    # test here) -- this only checks the DAG shape (G1 before G2a, one shared group id) and that
    # the group really was handed to the job manager, not real `tit.pre` behaviour.
    wait_until(_all_done)


def test_groups_invalid_config_422(client: TestClient) -> None:
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "pre",
            "config": {},
            "subject_ids": ["001"],
            "parallel_subjects": 1,
        },
    )
    assert r.status_code == 422
    assert "PreprocessConfig" in r.json()["detail"]


def test_groups_rejects_a_kind_that_is_not_per_subject(client: TestClient) -> None:
    """R3 generalized groups to sim/flex/ex/mex, but not to cohort kinds: a group Analyzer run is
    one job over the whole cohort and has no per-subject cap, so ``analyzer`` is still a 422."""
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "analyzer",
            "config": {},
            "subject_ids": ["001"],
            "parallel_subjects": 1,
        },
    )
    assert r.status_code == 422
    assert "job group" in r.json()["detail"]


# ---------------------------------------------------------------------------------------------
# generic per-subject groups (R3): sim / flex / ex / mex
# ---------------------------------------------------------------------------------------------


def _sim_config(subject_id: str) -> dict:
    return {
        "subject_id": subject_id,
        "montages": [
            {
                "_type": "Montage",
                "name": "m1",
                "mode": "net",
                "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
                "eeg_net": "GSN-HydroCel-185.csv",
            }
        ],
    }


def test_sim_group_is_one_job_per_subject_with_isolated_configs(
    client: TestClient,
) -> None:
    """R3 gate: two subjects -> two group members, each carrying exactly its own subject id --
    even though the request sent one template config naming only the first subject."""
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": _sim_config("001"),
            "subject_ids": ["001", "002"],
            "parallel_subjects": 1,
            "tags": ["sim-batch"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    jobs = body["jobs"]
    assert [j["kind"] for j in jobs] == ["sim", "sim"]
    assert {j["group_id"] for j in jobs} == {body["group_id"]}
    assert [j["subject_ids"] for j in jobs] == [["001"], ["002"]]

    for job, subject in zip(jobs, ["001", "002"]):
        detail = client.get(f"/api/jobs/{job['id']}", headers=BEARER).json()
        config = detail["spec"]["config"]
        assert config["subject_id"] == subject
        # No other subject's id may appear anywhere in the generated config.
        other = "002" if subject == "001" else "001"
        assert other not in json.dumps(config)


def test_sim_group_takes_per_subject_configs(client: TestClient) -> None:
    """A page whose config depends on the subject (ROI resolved per subject, a leadfield path)
    sends one `subject_configs` entry per job instead of one template."""
    a = _sim_config("ignored")
    a["montages"][0]["name"] = "left"
    b = _sim_config("ignored")
    b["montages"][0]["name"] = "right"
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": _sim_config("001"),
            "subject_ids": ["001", "002"],
            "subject_configs": [
                {"subject_id": "001", "config": a},
                {"subject_id": "002", "config": b},
                # One subject may take several jobs (Simulator: one per (subject, montage)).
                {"subject_id": "002", "config": a},
            ],
            "parallel_subjects": 2,
        },
    )
    assert r.status_code == 201, r.text
    jobs = r.json()["jobs"]
    assert [j["subject_ids"][0] for j in jobs] == ["001", "002", "002"]
    names = []
    for job in jobs:
        detail = client.get(f"/api/jobs/{job['id']}", headers=BEARER).json()
        assert detail["spec"]["config"]["subject_id"] == job["subject_ids"][0]
        names.append(detail["spec"]["config"]["montages"][0]["name"])
    assert names == ["left", "right", "left"]


def test_sim_group_rejects_unknown_subject_in_subject_configs(
    client: TestClient,
) -> None:
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": _sim_config("001"),
            "subject_ids": ["001"],
            "subject_configs": [{"subject_id": "999", "config": _sim_config("999")}],
            "parallel_subjects": 1,
        },
    )
    assert r.status_code == 422
    assert "999" in r.json()["detail"]


def test_sim_group_invalid_config_is_422(client: TestClient) -> None:
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": {"subject_id": "001", "montages": [], "conductivity": "nope"},
            "subject_ids": ["001"],
            "parallel_subjects": 1,
        },
    )
    assert r.status_code == 422


def test_group_cap_of_one_never_runs_two_members_at_once(client: TestClient) -> None:
    """R3 gate, server-side half: with `parallel_subjects: 1` the whole group is created in one
    request (no client-side POST spacing) and the scheduler never has two members `running`."""
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": {**_sim_config("001"), "__fake": {"duration_s": 0.3}},
            "subject_ids": ["001", "002", "003"],
            "parallel_subjects": 1,
        },
    )
    assert r.status_code == 201, r.text
    group_id = r.json()["group_id"]
    assert len(r.json()["jobs"]) == 3
    # Every member exists immediately, queued -- the cap is admission, not submission.
    assert {j["state"] for j in r.json()["jobs"]} == {"queued"}

    peak = 0
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        listed = client.get("/api/jobs", headers=BEARER).json()
        ours = [j for j in listed if j["group_id"] == group_id]
        running = [j for j in ours if j["state"] == "running"]
        peak = max(peak, len(running))
        assert len(running) <= 1, [j["state"] for j in ours]
        if all(j["state"] not in ("queued", "running") for j in ours):
            break
        time.sleep(0.02)
    else:  # pragma: no cover - timing safety net
        raise AssertionError("group did not finish")
    assert peak == 1


def test_group_cap_of_two_admits_two_members_at_once(client: TestClient) -> None:
    """The other half of the gate: the same submission with `parallel_subjects: 2` really does
    put two members in `running` together (different subjects, so no lock conflict, and the
    fixture's budget is 8 cpu / 64 GB, so no budget wait either)."""
    r = client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": "sim",
            "config": {**_sim_config("001"), "__fake": {"duration_s": 0.6}},
            "subject_ids": ["001", "002", "003"],
            "parallel_subjects": 2,
        },
    )
    assert r.status_code == 201, r.text
    group_id = r.json()["group_id"]

    def _saw_two():
        listed = client.get("/api/jobs", headers=BEARER).json()
        ours = [j for j in listed if j["group_id"] == group_id]
        running = [j for j in ours if j["state"] == "running"]
        assert len(running) <= 2, [j["state"] for j in ours]
        return len(running) == 2

    wait_until(_saw_two)


# ---------------------------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------------------------


def test_jobs_routes_require_auth(client: TestClient) -> None:
    assert client.get("/api/jobs").status_code == 401
    assert client.post("/api/jobs", json={"kind": "tools"}).status_code == 401


# ---------------------------------------------------------------------------------------------
# /ws/jobs
# ---------------------------------------------------------------------------------------------


def test_ws_jobs_receives_status_transitions(client: TestClient) -> None:
    with client.websocket_connect(f"{WS}?token={TOKEN}") as ws:
        submitted = client.post(
            "/api/jobs",
            headers=BEARER,
            json={
                "kind": "tools",
                "config": {"__fake": {"duration_s": 0.1}},
                "subject_ids": [],
            },
        ).json()
        job_id = submitted["id"]

        seen_states = []
        for _ in range(200):
            if "succeeded" in seen_states:
                break
            raw = ws.receive_text()
            msg = json.loads(raw)
            if msg["type"] == "job" and msg["job"]["id"] == job_id:
                seen_states.append(msg["job"]["state"])
        assert "succeeded" in seen_states


def test_ws_jobs_subscribe_streams_events(client: TestClient) -> None:
    submitted = client.post(
        "/api/jobs",
        headers=BEARER,
        json={
            "kind": "tools",
            "config": {"__fake": {"duration_s": 0.2}},
            "subject_ids": [],
        },
    ).json()
    job_id = submitted["id"]

    with client.websocket_connect(f"{WS}?token={TOKEN}") as ws:
        # Unknown ids are ignored without disconnecting or preventing a later valid
        # subscription in the same frame (2026-09-09 traversal regression).
        ws.send_text(json.dumps({"subscribe": {"../outside": 0, job_id: 0}}))
        seen_types = []
        for _ in range(200):
            if "exit" in seen_types:
                break
            raw = ws.receive_text()
            msg = json.loads(raw)
            if msg["type"] == "event" and msg["job_id"] == job_id:
                seen_types.append(msg["event"]["type"])
        assert "exit" in seen_types
        assert "stage" in seen_types

        ws.send_text(json.dumps({"unsubscribe": [job_id]}))


def test_ws_jobs_rejects_missing_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS):
            pass
    assert exc.value.code == 4401


def test_ws_jobs_rejects_foreign_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{WS}?token={TOKEN}", headers={"Origin": "http://evil.example"}
        ):
            pass
    assert exc.value.code == 4403
