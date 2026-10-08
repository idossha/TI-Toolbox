"""Every job's outputs stay inside the project (ARCHITECTURE §6, 2026-10-08).

What this pins: a config that names an output folder outside the project -- an absolute
``FlexConfig.output_folder`` elsewhere on disk, or a name that climbs out (``subdir_name``
``../..``) -- is refused with one 422 sentence on ``/api/plan``, ``/api/jobs`` (even with
``overwrite: true``, which used to skip the planning step), ``/api/jobs/groups`` and a proposal
step, and nothing is queued; an absolute folder inside the project, which is what the Optimizer
page sends, is accepted. The check is the plan route's (``_require_outputs_inside_project``),
which every creator runs.

Where the values come from: the paths are built here from pytest's ``tmp_path`` (the project and
a sibling folder), so "inside" and "outside" are known without the code under test.
Reproduce: .venv/bin/python -m pytest tests/test_output_jail.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_jobs_routes import (  # noqa: E402,F401  (fixtures)
    BEARER,
    _reset_job_manager,
    client,
    project,
    settings,
)
from tests.test_proposals_routes import FLEX  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402

REFUSAL = "Outputs must stay inside the project folder"


def flex(project: Path, folder: str) -> dict:
    return {**FLEX, "subject_id": "001", "output_folder": folder}


def outside(project: Path) -> str:
    return str(project.parent / "elsewhere" / "run")


def inside(project: Path) -> str:
    return str(Path(get_path_manager(str(project)).flex_search("001")) / "run")


def test_plan_refuses_an_output_folder_outside_the_project(
    client: TestClient, project: Path
) -> None:
    r = client.post(
        "/api/plan/flex",
        headers=BEARER,
        json={"config": flex(project, outside(project)), "subject_ids": ["001"]},
    )
    assert r.status_code == 422 and REFUSAL in r.json()["detail"]
    assert outside(project) in r.json()["detail"]
    ok = client.post(
        "/api/plan/flex",
        headers=BEARER,
        json={"config": flex(project, inside(project)), "subject_ids": ["001"]},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["jobs"][0]["output_dir"] == inside(project)


def test_plan_refuses_a_name_that_climbs_out_of_the_project(
    client: TestClient,
) -> None:
    r = client.post(
        "/api/plan/nilearn",
        headers=BEARER,
        json={
            "config": {
                "subject_simulation_pairs": [
                    {"subject_id": "001", "simulation_name": "M1"}
                ],
                "subdir_name": "../../../../escape",
            }
        },
    )
    assert r.status_code == 422 and REFUSAL in r.json()["detail"]


@pytest.mark.parametrize("route", ["/api/jobs", "/api/jobs/groups"])
def test_submission_refuses_it_even_when_overwrite_is_allowed(
    client: TestClient, project: Path, route: str
) -> None:
    r = client.post(
        route,
        headers=BEARER,
        json={
            "kind": "flex",
            "config": flex(project, outside(project)),
            "subject_ids": ["001"],
            "overwrite": True,
        },
    )
    assert r.status_code == 422 and REFUSAL in r.text
    assert client.get("/api/jobs", headers=BEARER).json() == []
    assert not Path(outside(project)).exists()


def test_a_proposal_step_writing_outside_the_project_cannot_be_approved(
    client: TestClient, project: Path
) -> None:
    step = {
        "id": "opt",
        "kind": "flex",
        "config": {**FLEX, "output_folder": outside(project)},
        "subject_ids": ["001"],
        "overwrite": True,
    }
    body = {"title": "Optimise", "steps": [step]}
    draft = client.post(
        "/api/proposals", headers=BEARER, json={**body, "dry_run": True}
    ).json()
    assert any(REFUSAL in e for e in draft["steps"][0]["plan"]["errors"])
    pid = client.post("/api/proposals", headers=BEARER, json=body).json()["id"]
    refused = client.post(f"/api/proposals/{pid}/approve", headers=BEARER)
    assert refused.status_code == 409 and REFUSAL in refused.text
    assert client.get("/api/jobs", headers=BEARER).json() == []
