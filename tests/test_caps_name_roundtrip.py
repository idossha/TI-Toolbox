"""One cap name, every route: available -> warp -> inspect -> scene electrodes -> eeg-nets catalog.

What this pins (2026-10-22, package p38): a cap is named by its FILE name everywhere on the real
server. Every name ``GET /api/caps/available`` lists with an MNI source is accepted by
``POST /api/caps/warp`` (200, never 404); after the warp the same string is accepted by
``GET /api/caps/inspect`` and ``GET /api/scene/electrodes`` and is listed by
``GET /api/catalog/eeg-nets`` with ``n`` equal to the number of ``Electrode`` rows in the file the
warp wrote. The stem the mock server used to list and the caps e2e used to assert
(``{caps: ["GSN-HydroCel-185"]}``) is a 404 here -- which is why the mock now lists file names.

Where the numbers come from: the electrode counts are read off the written CSV itself (rows that
start with ``Electrode,``), not off any route. SimNIBS is replaced by a fake ``warp_coordinates``
that writes a fixed three-electrode net, as in ``tests/test_caps.py``; the numbers of a real warp
are in ``tests/numerical/test_caps_warp_realdata.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_caps_name_roundtrip.py -q``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tit import caps  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

BEARER = {"Authorization": "Bearer test"}
MNI_CAP = "Electrode,10,0,0,Fz\nElectrode,-10,0,0,Cz\nElectrode,0,10,0,Pz\nFiducial,0,80,0,Nz\n"
# Three electrodes tens of mm apart (no collapsed pair), a reference and a fiducial, as charm writes.
WARPED = (
    "Electrode,40,0,90,Fz\nElectrode,-40,0,90,Cz\nElectrode,0,40,90,Pz\n"
    "ReferenceElectrode,0,-40,90,Ref\nFiducial,0,90,0,Nz\n"
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    pm = get_path_manager(str(tmp_path))
    m2m = Path(pm.m2m("ernie"))
    (m2m / "eeg_positions").mkdir(parents=True)
    (m2m / "ernie.msh").write_bytes(b"mesh")
    simnibs_caps = tmp_path.parent / (tmp_path.name + "-simnibs-caps")
    simnibs_caps.mkdir()
    (simnibs_caps / "EEG10-10_UI_Jurak_2007.csv").write_text(MNI_CAP)
    (simnibs_caps / "GSN-HydroCel-185.csv").write_text(MNI_CAP)
    monkeypatch.setattr(caps, "simnibs_caps_dir", lambda: simnibs_caps)
    monkeypatch.setattr("tit.catalog.subject_ids", lambda pm: ["ernie"])

    def warp_coordinates(cap, m2m_dir, **kwargs):
        Path(kwargs["out_name"]).write_text(WARPED)
        Path(kwargs["out_geo"]).write_text("View{};")

    monkeypatch.setitem(
        sys.modules,
        "simnibs.utils",
        SimpleNamespace(
            transformations=SimpleNamespace(warp_coordinates=warp_coordinates)
        ),
    )
    monkeypatch.setitem(
        sys.modules, "simnibs.mesh_tools", SimpleNamespace(mesh_io=MagicMock())
    )
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="test")),
        base_url="http://127.0.0.1:8765",
    )
    return SimpleNamespace(client=client, positions=m2m / "eeg_positions")


def _electrode_rows(path: Path) -> int:
    return sum(
        1 for line in path.read_text().splitlines() if line.startswith("Electrode,")
    )


def test_every_listed_source_cap_round_trips_by_its_file_name(project) -> None:
    c = project.client
    listed = c.get("/api/caps/available?subject=ernie", headers=BEARER).json()["caps"]
    names = [row["name"] for row in listed if row["source"] is not None]
    assert len(names) == 2, "has caps to check"

    for name in names:
        r = c.post(
            "/api/caps/warp", json={"subject": "ernie", "caps": [name]}, headers=BEARER
        )
        assert r.status_code == 200, (name, r.text)
        written = project.positions / name
        assert written.is_file(), name
        n = _electrode_rows(written)
        assert n == 3

        inspect = c.get(f"/api/caps/inspect?subject=ernie&net={name}", headers=BEARER)
        assert inspect.status_code == 200, (name, inspect.text)
        assert inspect.json()["net"] == name

        scene = c.get(f"/api/scene/electrodes?subject=ernie&net={name}", headers=BEARER)
        assert scene.status_code == 200, (name, scene.text)
        assert len(scene.json()["electrodes"]) == n

    nets = {
        row["name"]: row["n"]
        for row in c.get("/api/catalog/eeg-nets?subject=ernie", headers=BEARER).json()
    }
    assert nets == {name: _electrode_rows(project.positions / name) for name in names}

    # Applied: the list now says so, under the same names, and a second warp asks first.
    again = c.get("/api/caps/available?subject=ernie", headers=BEARER).json()["caps"]
    assert {r["name"] for r in again if r["on_subject"]} == set(names)
    r = c.post(
        "/api/caps/warp", json={"subject": "ernie", "caps": names}, headers=BEARER
    )
    assert r.status_code == 409


def test_a_net_only_on_the_subject_is_listed_drawn_and_never_warped(project) -> None:
    # A net with no MNI file of its name (charm's own, or one copied in by hand): listed with
    # source null, readable by its file name, and a 404 on warp -- nothing to warp it from, and
    # the subject's copy is left as it was.
    c = project.client
    own = project.positions / "OnlyOnSubject.csv"
    own.write_text(WARPED)
    before = own.read_bytes()

    listed = c.get("/api/caps/available?subject=ernie", headers=BEARER).json()["caps"]
    row = next(r for r in listed if r["name"] == own.name)
    assert row["source"] is None
    assert row["on_subject"] is True

    r = c.post(
        "/api/caps/warp", json={"subject": "ernie", "caps": [own.name]}, headers=BEARER
    )
    assert r.status_code == 404
    assert r.json()["detail"] == f"No MNI cap named {own.name}"
    r = c.post(
        "/api/caps/warp",
        json={"subject": "ernie", "caps": [own.name], "overwrite": True},
        headers=BEARER,
    )
    assert r.status_code == 404, "overwrite does not invent a source"
    assert own.read_bytes() == before

    scene = c.get(f"/api/scene/electrodes?subject=ernie&net={own.name}", headers=BEARER)
    assert scene.status_code == 200, scene.text
    assert len(scene.json()["electrodes"]) == _electrode_rows(own)
    nets = {
        row["name"]: row["n"]
        for row in c.get("/api/catalog/eeg-nets?subject=ernie", headers=BEARER).json()
    }
    assert nets[own.name] == _electrode_rows(own) == 3


def test_the_stem_the_mock_used_is_not_a_cap_name(project) -> None:
    c = project.client
    stem = {"subject": "ernie", "caps": ["GSN-HydroCel-185"]}
    r = c.post("/api/caps/warp", json=stem, headers=BEARER)
    assert r.status_code == 404
    assert "GSN-HydroCel-185" in r.json()["detail"]
    assert not any(project.positions.iterdir())

    r = c.post(
        "/api/caps/warp",
        json={"subject": "ernie", "caps": ["GSN-HydroCel-185.csv"]},
        headers=BEARER,
    )
    assert r.status_code == 200
    stem_inspect = c.get(
        "/api/caps/inspect?subject=ernie&net=GSN-HydroCel-185", headers=BEARER
    )
    assert stem_inspect.status_code == 404
