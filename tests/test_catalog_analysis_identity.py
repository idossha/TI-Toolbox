"""A Mesh and a Voxel analysis with the same ROI name are two catalog entries, each reachable.

What this pins (2026-10-22)
    ``Analyses/Mesh/<X>`` and ``Analyses/Voxel/<X>`` -- the same sphere analysed in both spaces
    -- were both listed under the bare name ``X``. ``GET /api/catalog/analyses/X/summary``
    returned the first match (Mesh) for both rows, so the Voxel numbers could not be read, and
    the Results tree gave both rows the same node id. Now every listed name is unique within its
    simulation (a name two analyses would share becomes each one's path relative to the
    simulation, the rule custom ``output_dir`` runs already follow), every entry says which
    analysis space it was computed in (``analysis_space``: ``mesh`` / ``voxel``), and each
    listed name's summary is that analysis's own ``results.csv``. A bare name that two analyses
    share answers 404 instead of silently picking one.

Where the expectations come from
    Authored: the two ``results.csv`` files are written here with ``roi_mean`` 0.1 (Mesh) and
    0.2 (Voxel); which is which is the folder each was written into. ``analysis_space`` of a
    standard run is the folder ``PathManager.analysis_output_dir`` writes it into
    (``Analyses/Mesh`` or ``Analyses/Voxel``); of a custom ``output_dir`` run, the ``space`` key
    the analyzer writes into ``analysis.json`` (``Analyzer._save_metadata``).

Run: .venv/bin/python -m pytest tests/test_catalog_analysis_identity.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit import catalog  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
SID = "ernie"
SIM = "S1"
SPHERE = "sphere_x0.00_y0.00_z0.00_r5.0_MNI"
#: Authored per folder: the number each analysis's own results.csv holds.
ROI_MEAN = {"Mesh": "0.1", "Voxel": "0.2"}


def _write_analysis(directory: Path, roi_mean: str, meta: dict) -> Path:
    directory.mkdir(parents=True)
    (directory / "analysis.json").write_text(json.dumps(meta))
    (directory / "results.csv").write_text(
        f"Metric,Value\nroi_mean,{roi_mean}\nfield_name,TI_max\n"
    )
    return directory


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m(SID))
    (tmp_path / "dataset_description.json").write_text("{}")
    sim = Path(pm.simulation(SID, SIM))
    (sim / "TI" / "mesh").mkdir(parents=True)
    for space, mean in ROI_MEAN.items():
        _write_analysis(
            sim / "Analyses" / space / SPHERE,
            mean,
            {
                "field_name": "TI_max",
                "coordinate_space": "mni",
                "space": space.lower(),
                "analysis_type": "spherical",
            },
        )
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _listed(client: TestClient) -> list[dict]:
    resp = client.get(
        "/api/catalog/analyses",
        params={"subject": SID, "simulation": SIM},
        headers=BEARER,
    )
    assert resp.status_code == 200
    return resp.json()


def _summary(client: TestClient, name: str):
    return client.get(
        f"/api/catalog/analyses/{name}/summary",
        params={"subject": SID, "simulation": SIM},
        headers=BEARER,
    )


def _folder_of(entry: dict) -> str:
    """``Mesh`` or ``Voxel``: the folder the entry's results.csv sits under, read off its path."""
    return Path(entry["csv"]).parent.parent.name


def test_same_named_mesh_and_voxel_analyses_are_two_distinct_entries(
    client: TestClient,
) -> None:
    listed = _listed(client)
    assert len(listed) == 2
    names = [a["name"] for a in listed]
    assert len(set(names)) == len(names), names
    assert sorted(_folder_of(a) for a in listed) == ["Mesh", "Voxel"]
    for entry in listed:
        assert entry["analysis_space"] == _folder_of(entry).lower()
        # ``space`` stays the coordinate space of the target, not mesh/voxel.
        assert entry["space"] == "mni"


def test_each_listed_name_summarises_its_own_results_csv(client: TestClient) -> None:
    listed = _listed(client)
    assert len(listed) == 2
    for entry in listed:
        resp = _summary(client, entry["name"])
        assert resp.status_code == 200, entry["name"]
        rows = dict(map(tuple, resp.json()["rows"]))
        assert rows["roi_mean"] == ROI_MEAN[_folder_of(entry)], entry["name"]


def test_a_bare_name_two_analyses_share_is_not_silently_one_of_them(
    client: TestClient,
) -> None:
    resp = _summary(client, SPHERE)
    assert resp.status_code == 404


def test_the_runs_own_relative_path_still_resolves_each_one(project: Path) -> None:
    pm = get_path_manager(str(project))
    for space, mean in ROI_MEAN.items():
        table = catalog.analysis_summary(pm, SID, SIM, f"Analyses/{space}/{SPHERE}")
        assert dict(map(tuple, table["rows"]))["roi_mean"] == mean


def test_a_name_used_once_keeps_its_bare_form(project: Path) -> None:
    """Only a shared name changes: every existing single-space analysis keeps its URL."""
    pm = get_path_manager(str(project))
    sim = Path(pm.simulation(SID, SIM))
    _write_analysis(
        sim / "Analyses" / "Voxel" / "cortical_lh.insula_DK40",
        "0.3",
        {"field_name": "TI_max", "space": "voxel"},
    )
    by_name = {a["name"]: a for a in catalog.analyses(pm, SID, SIM)}
    assert "cortical_lh.insula_DK40" in by_name
    assert by_name["cortical_lh.insula_DK40"]["analysis_space"] == "voxel"
    table = catalog.analysis_summary(pm, SID, SIM, "cortical_lh.insula_DK40")
    assert dict(map(tuple, table["rows"]))["roi_mean"] == "0.3"


def test_a_custom_output_dir_takes_its_space_from_analysis_json(project: Path) -> None:
    pm = get_path_manager(str(project))
    sim = Path(pm.simulation(SID, SIM))
    _write_analysis(sim / "custom" / "run_v", "0.4", {"space": "voxel"})
    _write_analysis(sim / "custom" / "run_old", "0.5", {"field_name": "TI_max"})
    by_name = {a["name"]: a for a in catalog.analyses(pm, SID, SIM)}
    assert by_name["custom__run_v"]["analysis_space"] == "voxel"
    # An analysis.json written before ``space`` existed says nothing; neither does the catalog.
    assert by_name["custom__run_old"]["analysis_space"] is None


def test_names_are_unique_whatever_the_mix(project: Path) -> None:
    """Shared names in Mesh/Voxel plus custom runs: one entry per folder, no name twice,
    and every name resolves to the folder it was listed for."""
    pm = get_path_manager(str(project))
    sim = Path(pm.simulation(SID, SIM))
    for i, folder in enumerate(
        ("Analyses/Mesh/A", "Analyses/Voxel/A", "Analyses/Mesh/B", "extra/A")
    ):
        _write_analysis(sim / folder, f"1.{i}", {"space": "mesh"})
    folders = sorted(str(p.parent.relative_to(sim)) for p in sim.rglob("results.csv"))
    listed = catalog.analyses(pm, SID, SIM)
    assert len(listed) == len(folders) == 6
    names = [a["name"] for a in listed]
    assert len(set(names)) == len(names), names
    for entry in listed:
        table = catalog.analysis_summary(pm, SID, SIM, entry["name"])
        on_disk = (Path(entry["csv"])).read_text().splitlines()[1].split(",")[1]
        assert dict(map(tuple, table["rows"]))["roi_mean"] == on_disk
