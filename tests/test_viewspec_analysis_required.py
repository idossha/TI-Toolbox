"""An analysis view must name its analysis; without one the server answers 404.

What this pins (2026-10-22, package p38): ``tit.viewspec.build_view("analysis", ...)`` returns
``None`` -- which ``POST /api/view/open`` turns into HTTP 404 "Unknown subject/simulation/analysis"
-- when the request names the subject and the simulation but not the analysis, even though both
exist on disk; with the analysis named, the same request resolves to a scene that carries that
analysis's own overlay. This is the server spec the Results page's "Open in viewer" must meet
(it now opens the analysis's scene file or its overlay as a one-file view,
``desktop/tests/unit/results-open-in-viewer.test.ts``) and the one the mock server now enforces
(``desktop/tests/mock-server/plan-output-dirs.test.ts``).

The fixture is a throwaway project with one simulation folder and one voxel analysis whose
overlay is an empty file: ``build_view`` only resolves paths here, it never reads the volume.

Reproduce: ``.venv/bin/python -m pytest tests/test_viewspec_analysis_required.py -q``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tit import viewspec
from tit.paths import get_path_manager

SUBJECT, SIMULATION, ANALYSIS = "001", "Thalamus", "Thalamus_DK40_TI_max"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m(SUBJECT))
    analysis_dir = Path(
        pm.simulation(SUBJECT, SIMULATION), "Analyses", "Voxel", ANALYSIS
    )
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "roi_overlay.nii.gz").write_bytes(b"")
    return analysis_dir / "roi_overlay.nii.gz"


def _paths(spec: dict) -> list[str]:
    return [layer["path"] for layer in spec["layers"]]


def test_an_analysis_view_without_its_name_does_not_resolve(project: Path) -> None:
    assert (
        viewspec.build_view("analysis", subject=SUBJECT, simulation=SIMULATION) is None
    )
    assert (
        viewspec.build_view(
            "analysis", subject=SUBJECT, simulation=SIMULATION, analysis=""
        )
        is None
    )


def test_the_same_request_naming_the_analysis_draws_its_overlay(project: Path) -> None:
    spec = viewspec.build_view(
        "analysis", subject=SUBJECT, simulation=SIMULATION, analysis=ANALYSIS
    )
    assert spec is not None
    assert str(project) in _paths(spec)


def test_the_open_route_answers_404_for_the_unnamed_analysis(project: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    root = get_path_manager().project_dir
    assert root and project.is_relative_to(root)
    client = TestClient(
        create_app(ServerSettings(project_dir=root, token="t")),
        base_url="http://127.0.0.1:8765",
    )
    body = {"kind": "analysis", "subject": SUBJECT, "simulation": SIMULATION}
    headers = {"Authorization": "Bearer t"}
    # dry_run: resolve only, write no scene file into the project.
    r = client.post("/api/view/open", json={**body, "dry_run": True}, headers=headers)
    assert r.status_code == 404
    assert r.json()["detail"] == "Unknown subject/simulation/analysis"
    named = {**body, "analysis": ANALYSIS, "dry_run": True}
    assert client.post("/api/view/open", json=named, headers=headers).status_code == 200
