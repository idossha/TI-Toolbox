"""HTTP tests for ``/api/pipelines*`` against a real fake-runner-backed :class:`JobManager`.

The D6 mock-side gate lives here: a 4-node pre -> flex -> sim -> analyzer pipeline validates, and
``POST /api/pipelines/run`` produces **one** group id whose jobs' ``after`` chain is exactly the
document's edges resolved to real job ids.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-pipelines"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "fake_runner.py")


def _fake_command_for(kind, config, spec_path):
    return [sys.executable, FAKE_RUNNER, spec_path]


@pytest.fixture(autouse=True)
def _reset_job_manager():
    yield
    bootstrap.reset_manager()


def scaffold_subject(root: Path, sid: str, *, m2m: bool = True, simulation: bool = True) -> None:
    """The least on disk that makes *sid* read as ready in `GET /api/catalog/overview`.

    The readiness gate is real in these tests rather than stubbed: `POST /api/pipelines/validate`
    now refuses a graph whose subjects lack what its nodes need, so a route test running against
    an *empty* project would be refused for a reason that has nothing to do with the route.
    """
    (root / f"sub-{sid}" / "anat").mkdir(parents=True, exist_ok=True)
    (root / f"sub-{sid}" / "anat" / f"sub-{sid}_T1w.nii.gz").touch()
    if m2m:
        head = root / "derivatives" / "SimNIBS" / f"sub-{sid}" / f"m2m_{sid}"
        head.mkdir(parents=True, exist_ok=True)
        (head / f"{sid}.msh").touch()
    if simulation:
        mesh = (
            root / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / "M1" / "TI" / "mesh"
        )
        mesh.mkdir(parents=True, exist_ok=True)
        (mesh / f"{sid}_TI.msh").touch()


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    scaffold_subject(tmp_path, "ernie")
    get_path_manager(str(tmp_path))
    manager = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=_fake_command_for,
    )
    manager.start()
    bootstrap.set_manager_for_testing(manager)
    return TestClient(create_app(ServerSettings(project_dir=str(tmp_path), token=TOKEN)), base_url=BASE)


def flex_config() -> dict:
    from tit.config_io import serialize_config
    from tit.opt.config import FlexConfig

    return serialize_config(
        FlexConfig(
            subject_id="ernie",
            goal="mean",
            postproc="max_TI",
            current_mA=2.0,
            electrode=FlexConfig.ElectrodeConfig(),
            roi=FlexConfig.SubcorticalROI(atlas_path="aseg.mgz", label=[17]),
        )
    )


def four_node() -> dict:
    return {
        "version": 1,
        "name": "gate",
        "nodes": [
            # The cohort is stated once, on a node of its own, and reaches the rest of the graph
            # over the `subjects` wire -- no node is configured from the node upstream of it.
            {
                "id": "sub1",
                "kind": "subjects",
                "config": {"subject_ids": ["ernie"]},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "pre1",
                "kind": "pre",
                "config": {"create_m2m": True},
                "position": {"x": 0, "y": 0},
            },
            {"id": "flex1", "kind": "flex", "config": flex_config()},
            {"id": "sim1", "kind": "sim", "config": {"conductivity": "scalar"}},
            {
                "id": "an1",
                "kind": "analyzer",
                "config": {
                    "space": "mesh",
                    "analysis_type": "spherical",
                    "center": [1.0, 2.0, 3.0],
                    "radius": 5.0,
                },
            },
        ],
        "edges": [
            {"from": "sub1", "to": "pre1", "port": "subjects"},
            {"from": "pre1", "to": "flex1", "port": "subjects"},
            {"from": "pre1", "to": "sim1", "port": "subjects"},
            {"from": "flex1", "to": "sim1", "port": "montages"},
            {"from": "sim1", "to": "an1", "port": "subjects"},
            {"from": "sim1", "to": "an1", "port": "simulation"},
        ],
    }


# -- palette / validate --------------------------------------------------------------------------


def test_kinds_route_describes_every_node_kind(client: TestClient) -> None:
    body = client.get("/api/pipelines/kinds", headers=BEARER).json()
    from tit.pipeline.document import NODE_KINDS

    assert [k["kind"] for k in body["kinds"]] == list(NODE_KINDS)
    simulator = next(k for k in body["kinds"] if k["kind"] == "sim")
    assert "montages" in simulator["inputs"] and "simulation" in simulator["outputs"]


def test_validate_accepts_the_four_node_pipeline_and_previews_its_jobs(
    client: TestClient,
) -> None:
    body = client.post("/api/pipelines/validate", headers=BEARER, json=four_node()).json()
    assert body["ok"], body["issues"]
    assert body["order"] == ["sub1", "pre1", "flex1", "sim1", "an1"]
    labels = [job["label"] for job in body["jobs"]]
    assert labels[0] == "pre1:0"
    assert "sim1:resolve:montages" in labels


def test_validate_returns_reasons_not_a_500(client: TestClient) -> None:
    doc = four_node()
    doc["edges"].append({"from": "an1", "to": "flex1", "port": "subjects"})
    body = client.post("/api/pipelines/validate", headers=BEARER, json=doc).json()
    assert not body["ok"]
    assert any("cycle" in issue["message"] for issue in body["issues"])


def test_a_structurally_broken_document_is_422(client: TestClient) -> None:
    response = client.post(
        "/api/pipelines/validate", headers=BEARER, json={"version": 1, "nodes": [{"id": "a"}]}
    )
    assert response.status_code == 422


# -- run: one group, `after` = the edges -----------------------------------------------------------


def test_run_submits_the_whole_pipeline_as_one_group(client: TestClient) -> None:
    response = client.post(
        "/api/pipelines/run",
        headers=BEARER,
        json={"pipeline": four_node(), "parallel_subjects": 1},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["pipeline"] == "gate"

    group_id = body["group_id"]
    assert group_id
    assert {job["group_id"] for job in body["jobs"]} == {group_id}

    # One Jobs row per submitted job, all under the one group -- the UI groups by group_id.
    listed = client.get("/api/jobs", headers=BEARER).json()
    assert {job["group_id"] for job in listed} == {group_id}

    # The `after` chain is the document's edges resolved to real job ids.
    order = [job["id"] for job in body["jobs"]]
    jobs_root = Path(client.app.state.settings.project_dir) / "code" / "ti-toolbox" / "jobs"
    specs = {
        job_id: json.loads((jobs_root / job_id / "spec.json").read_text()) for job_id in order
    }

    def one(kind: str, node: str) -> str:
        """The single job this pipeline node produced (every job is tagged with its node)."""
        matches = [
            job_id
            for job_id in order
            if specs[job_id]["kind"] == kind and f"node:{node}" in specs[job_id]["tags"]
        ]
        assert len(matches) == 1, (kind, node, matches)
        return matches[0]

    pre_id = one("pre", "pre1")
    flex_id = one("flex", "flex1")
    resolve_montages = one("tools", "sim1")
    sim_id = one("sim", "sim1")
    resolve_simulation = one("tools", "an1")
    analyzer_id = one("analyzer", "an1")

    # Exactly the document's five edges, plus the two resolve steps they imply.
    assert specs[pre_id]["after"] == []
    assert specs[flex_id]["after"] == [pre_id]
    assert specs[resolve_montages]["after"] == [flex_id]
    assert set(specs[sim_id]["after"]) == {pre_id, resolve_montages}
    assert specs[resolve_simulation]["after"] == [sim_id]
    assert set(specs[analyzer_id]["after"]) == {sim_id, resolve_simulation}


def test_run_refuses_an_invalid_graph_with_its_reasons(client: TestClient) -> None:
    """Cutting the cohort loose leaves three nodes with no subjects at all."""
    doc = four_node()
    doc["edges"] = [e for e in doc["edges"] if e["from"] != "sub1"]
    response = client.post("/api/pipelines/run", headers=BEARER, json={"pipeline": doc})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("needs Subjects" in issue["message"] for issue in detail["issues"])


def test_run_refuses_a_graph_whose_subjects_are_not_ready(
    client: TestClient, tmp_path: Path
) -> None:
    """The readiness gate is enforced server-side, not only at drag time on the canvas."""
    scaffold_subject(tmp_path, "102", m2m=False, simulation=False)
    doc = {
        "version": 1,
        "name": "not ready",
        "nodes": [
            {"id": "sub1", "kind": "subjects", "config": {"subject_ids": ["102"]}},
            {"id": "sim1", "kind": "sim", "config": {"conductivity": "scalar"}},
        ],
        "edges": [{"from": "sub1", "to": "sim1", "port": "subjects"}],
    }
    response = client.post("/api/pipelines/run", headers=BEARER, json={"pipeline": doc})
    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(i["code"] == "not_ready" for i in issues)
    assert any("102 has no head model" in i["message"] for i in issues)


def test_the_kinds_route_carries_both_tables_the_canvas_gates_a_drag_with(
    client: TestClient,
) -> None:
    body = client.get("/api/pipelines/kinds", headers=BEARER).json()
    by_kind = {k["kind"]: k for k in body["kinds"]}
    assert by_kind["subjects"] == {
        "kind": "subjects",
        "inputs": [],
        "outputs": ["subjects"],
        "required": [],
        "requires": [],
        "produces": [],
    }
    assert by_kind["pre"]["requires"] == ["raw"]
    assert by_kind["pre"]["produces"] == ["m2m"]
    assert by_kind["sim"]["requires"] == ["m2m"]
    assert by_kind["sim"]["produces"] == ["simulation"]
    assert by_kind["analyzer"]["requires"] == ["simulation"]
    assert by_kind["ex"]["requires"] == ["m2m", "leadfield"]
    assert [c["capability"] for c in body["capabilities"]] == [
        "raw",
        "m2m",
        "leadfield",
        "simulation",
    ]


# -- save / load / list / delete -------------------------------------------------------------------


def test_save_load_list_and_delete_round_trip(client: TestClient, tmp_path: Path) -> None:
    doc = four_node()
    assert client.put("/api/pipelines/my run", headers=BEARER, json=doc).status_code == 200
    assert (tmp_path / "code" / "ti-toolbox" / "pipelines" / "my run.json").is_file()

    listed = client.get("/api/pipelines", headers=BEARER).json()
    assert [entry["name"] for entry in listed] == ["my run"]
    # The list states a pipeline's *size*, so the palette's Saved list can say "4 steps" without
    # loading every document to count them.
    assert listed[0]["nodes"] == 5
    assert listed[0]["edges"] == 6

    loaded = client.get("/api/pipelines/my run", headers=BEARER).json()
    assert loaded["name"] == "my run"
    assert [n["id"] for n in loaded["nodes"]] == ["sub1", "pre1", "flex1", "sim1", "an1"]

    assert client.delete("/api/pipelines/my run", headers=BEARER).status_code == 204
    assert client.get("/api/pipelines/my run", headers=BEARER).status_code == 404


def test_an_unreadable_saved_file_still_lists_but_without_counts(
    client: TestClient, tmp_path: Path
) -> None:
    """A file someone hand-edited into invalid JSON must not make the whole list disappear."""
    assert client.put("/api/pipelines/good", headers=BEARER, json=four_node()).status_code == 200
    broken = tmp_path / "code" / "ti-toolbox" / "pipelines" / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")

    listed = client.get("/api/pipelines", headers=BEARER).json()
    by_name = {entry["name"]: entry for entry in listed}
    assert set(by_name) == {"good", "broken"}
    assert by_name["good"]["nodes"] == 5
    assert "nodes" not in by_name["broken"]


@pytest.mark.parametrize("name", [".hidden", "a" * 65, "semi;colon", "dot.dot"])
def test_a_name_that_could_escape_the_pipelines_directory_is_refused(
    client: TestClient, name: str, tmp_path: Path
) -> None:
    """A saved pipeline is one file inside ``pipelines/``; nothing else is a legal name.

    (Names containing ``/`` or ``..`` never reach the handler -- the HTTP client normalises the
    path and Starlette routes it elsewhere -- so the ones worth pinning here are those that *do*
    reach it.)
    """
    response = client.put(f"/api/pipelines/{name}", headers=BEARER, json=four_node())
    assert response.status_code == 422, response.text
    assert not list((tmp_path / "code" / "ti-toolbox" / "pipelines").glob("*")) if (
        tmp_path / "code" / "ti-toolbox" / "pipelines"
    ).is_dir() else True


# -- export ----------------------------------------------------------------------------------------


def test_export_returns_a_valid_notebook(client: TestClient) -> None:
    nbformat = pytest.importorskip("nbformat")
    response = client.post(
        "/api/pipelines/export?format=ipynb", headers=BEARER, json={"pipeline": four_node()}
    )
    assert response.status_code == 200, response.text
    notebook = nbformat.reads(response.text, as_version=4)
    nbformat.validate(notebook)
    assert notebook.metadata["ti_toolbox"]["pipeline"]["name"] == "gate"


def test_export_refuses_an_unknown_format(client: TestClient) -> None:
    response = client.post(
        "/api/pipelines/export?format=pdf", headers=BEARER, json={"pipeline": four_node()}
    )
    assert response.status_code == 422


def test_pipeline_overwrite_conflict_rejects_whole_group(client, tmp_path):
    doc = four_node()
    doc["nodes"][1]["config"].update(
        replace_existing_outputs=True, skip_existing_outputs=True
    )
    response = client.post("/api/pipelines/run", headers=BEARER, json={"pipeline": doc})
    assert response.status_code == 403, response.text
    assert client.get("/api/jobs", headers=BEARER).json() == []
    assert (
        tmp_path / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie" / "ernie.msh"
    ).is_file()
