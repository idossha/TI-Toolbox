"""A step of a kind that runs once for all its subjects queues one job, not one per subject.

What this pins
--------------
``stats``, ``nifti_average`` and ``nilearn`` configs name their whole cohort (``subjects`` /
``subject_simulation_pairs`` rows), as does a ``source`` config (``subject_ids`` / ``pairs``) and
an ``analyzer`` config in group mode; none of them has a per-subject ``subject_id``.
``plan_submission`` (``tit.server.routes.jobs``), which an approved proposal step goes through,
expanded every kind outside the job-group kinds into one job per subject with ``subject_id``
injected: a stats step over three subjects became three identical whole-cohort jobs writing one
``stats/group_comparison/<name>`` folder, and the proposal card refused the step because
``/api/validate`` calls the injected ``subject_id`` an unknown key.

Where the expected values come from
    - The job count is what the desktop page submits for the same config: the committed
      corpus case (``tests/fixtures/desktop_configs``, written by the real builders) holds one
      job for all its subjects.
    - That the plan route treats the stats/nifti/nilearn run as one project-level job is its
      own answer (``POST /api/plan/<kind>`` returns one job with ``subject == ""``).
    - Which kinds these are is read off the config dataclasses: a class without a
      ``subject_id`` field cannot be narrowed to one subject.

Reproduce: ``.venv/bin/python -m pytest tests/test_proposal_project_kinds.py -q``.
Deliberately elsewhere: per-subject steps and proposal lifecycle
(``tests/test_proposals_routes.py``). Written 2026-10-22 (package p41).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tests.field_mesh import write_field_mesh
from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.preflight import preflight  # noqa: E402
from tit.jobs.registry import spec_path  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes import jobs as jobs_route  # noqa: E402
from tit.server.routes.validate import (  # noqa: E402
    ALL_KINDS,
    AMBIGUOUS_KIND_CLASSES,
    cls_for,
)
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-cohort"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
CORPUS = Path(__file__).parent / "fixtures" / "desktop_configs"
PLACEHOLDER = "/corpus/project"

#: (corpus case, kind): accepted desktop cases whose one job covers several subjects.
CASES = [
    ("panels-stats/classification-2-groups", "stats"),
    ("panels-stats/correlation-3-rows", "stats"),
    ("panels-nifti/typed-pattern-and-pairs", "nifti_average"),
    ("panels-nilearn/two-pairs", "nilearn"),
    ("panels-source/forward-two-subjects", "source"),
    ("analyzer/group-cortical", "analyzer"),
]


def _case(case_id: str, project: Path) -> dict:
    text = (CORPUS / f"{case_id}.json").read_text()
    return json.loads(text.replace(PLACEHOLDER, str(project)))


def _seed_inputs(kind: str, config: dict, project: Path) -> None:
    """Create every input preflight asks for (empty files, folders), so only the job count and
    config decide the outcome."""
    for _ in range(10):  # each round can reveal the next input (m2m, mesh, surface)
        missing = preflight(kind, config, str(project))
        if not missing:
            return
        for item in missing:
            path = Path(item.expected_path)
            if path.suffix == ".msh":
                write_field_mesh(path)  # a mesh whose field list can be read
            elif path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            else:
                path.mkdir(parents=True, exist_ok=True)
    assert preflight(kind, config, str(project)) == []


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    return root


@pytest.fixture()
def manager(project: Path, monkeypatch):
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: project / "preferences.json"
    )
    get_path_manager(str(project))
    fake = str(Path(__file__).parent / "fake_runner.py")
    jobs = JobManager(
        str(project),
        runner_cwd=str(project),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, spec: [sys.executable, fake, spec],
    )
    jobs.start()
    bootstrap.set_manager_for_testing(jobs)
    yield jobs
    jobs.shutdown()
    bootstrap.reset_manager()


@pytest.fixture()
def client(project: Path, manager) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def test_the_once_for_all_subjects_kinds_are_those_with_no_subject_id_field():
    # Set aside: `pre` (its config lists its subjects in `subject_ids` and plan_submission
    # gives it its own branch, the stage DAG), and the two kinds whose class depends on the
    # config's `_type` (cls_for needs one for blender): each of their classes is checked below.
    no_subject_id = set()
    for kind in ALL_KINDS - {"pre", "blender", "stats"}:
        fields = {f.name for f in dataclasses.fields(cls_for(kind, {}))}
        if "subject_id" not in fields:
            no_subject_id.add(kind)
    for type_tag in ("GroupComparisonConfig", "CorrelationConfig"):
        fields = {
            f.name for f in dataclasses.fields(cls_for("stats", {"_type": type_tag}))
        }
        assert "subject_id" not in fields
    no_subject_id.add("stats")
    # Every blender export is of one subject: blender stays per-subject.
    for type_tag in AMBIGUOUS_KIND_CLASSES["blender"]:
        fields = {
            f.name for f in dataclasses.fields(cls_for("blender", {"_type": type_tag}))
        }
        assert "subject_id" in fields, type_tag
    assert set(jobs_route.ONCE_FOR_ALL_SUBJECTS_KINDS) == no_subject_id


@pytest.mark.parametrize("case_id,kind", CASES, ids=[c for c, _ in CASES])
def test_plan_submission_queues_what_the_page_submits(
    case_id: str, kind: str, project: Path, manager: JobManager
) -> None:
    case = _case(case_id, project)
    assert case["desktop"]["accepts"]
    [job] = case["jobs"]  # the page submits one job for all its subjects
    _seed_inputs(kind, job["config"], project)
    planned = jobs_route.plan_submission(
        manager, kind, job["config"], job["subject_ids"]
    )
    assert len(planned) == len(case["jobs"]) == 1
    assert planned[0].config == job["config"]  # nothing injected, no subject_id
    assert planned[0].subject_ids == job["subject_ids"]


@pytest.mark.parametrize("case_id,kind", CASES[:4], ids=[c for c, _ in CASES[:4]])
def test_the_plan_route_calls_the_cohort_tools_one_project_level_job(
    case_id: str, kind: str, project: Path, client: TestClient
) -> None:
    [job] = _case(case_id, project)["jobs"]
    plan = client.post(
        f"/api/plan/{kind}",
        json={"config": job["config"], "subject_ids": job["subject_ids"]},
        headers=BEARER,
    )
    assert plan.status_code == 200, plan.text
    assert [j["subject"] for j in plan.json()["jobs"]] == [""]


def _approved(client: TestClient, pid: str) -> dict:
    r = client.post(f"/api/proposals/{pid}/approve", headers=BEARER)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("case_id,kind", CASES, ids=[c for c, _ in CASES])
def test_an_approved_step_queues_one_job_writing_where_its_plan_said(
    case_id: str, kind: str, project: Path, client: TestClient
) -> None:
    [job] = _case(case_id, project)["jobs"]
    _seed_inputs(kind, job["config"], project)
    r = client.post(
        "/api/proposals",
        headers=BEARER,
        json={
            "title": f"one {kind} run",
            "steps": [
                {
                    "id": "cohort",
                    "kind": kind,
                    "config": job["config"],
                    "subject_ids": job["subject_ids"],
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    step = r.json()["steps"][0]
    assert step["plan"]["errors"] == []
    plan_dirs = sorted(o["output_dir"] for o in step["plan"]["outputs"])

    approved = _approved(client, r.json()["id"])
    job_ids = approved["steps"][0]["job_ids"]
    assert len(job_ids) == 1
    spec = json.loads(Path(spec_path(str(project), job_ids[0])).read_text())
    assert spec["config"] == job["config"]
    assert spec["subject_ids"] == job["subject_ids"]

    if kind == "analyzer":
        return  # its group folder is named by the second the run starts
    # The queued job's own plan is the step's plan: same folders, nothing more.
    replan = client.post(
        f"/api/plan/{kind}",
        json={"config": spec["config"], "subject_ids": spec["subject_ids"]},
        headers=BEARER,
    ).json()
    assert sorted(j["output_dir"] for j in replan["jobs"]) == plan_dirs


def test_a_per_subject_kind_still_queues_one_job_per_subject(
    project: Path, manager: JobManager
) -> None:
    """The narrowing that is right for a config with a subject_id is kept (analyzer, single)."""
    pm = get_path_manager(str(project))
    config = {
        "mode": "single",
        "simulation": "M1",
        "space": "mesh",
        "analysis_type": "spherical",
        "center": [0.0, 0.0, 0.0],
        "radius": 5.0,
    }
    for sid in ("001", "002"):
        _seed_inputs("analyzer", {**config, "subject_id": sid}, project)
    planned = jobs_route.plan_submission(manager, "analyzer", config, ["001", "002"])
    assert [(p.subject_ids, p.config["subject_id"]) for p in planned] == [
        (["001"], "001"),
        (["002"], "002"),
    ]
    assert Path(pm.m2m("002")).is_dir()
