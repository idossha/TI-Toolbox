"""EEG caps panel back end: ``tit.caps`` and ``/api/caps/*`` (ARCHITECTURE § 8, EEG caps).

What this pins, 2026-10-16:

* ``net_stats`` on hand-placed coordinates: every expected spacing below is
  read off the coordinates themselves (axis-aligned points, so each distance
  is one difference), not from the implementation; a planted pair 0.5 mm
  apart and a repeated label must be reported.
* ``validate_mni_cap`` refuses what the warp would silently skip or misplace.
* The routes: auth, 409 without ``overwrite`` when the cap is already on the
  subject, unknown / traversing names refused before any path is built,
  output written only under ``m2m_<id>/eeg_positions``. SimNIBS is replaced
  by a fake ``warp_coordinates`` that writes a fixed net, so the charm call
  shape (direction, out_name, out_geo, skin_tag) is asserted here and the
  numbers of a real warp are in ``tests/numerical/test_caps_warp_realdata.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_caps.py -q``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tit import caps
from tit.paths import get_path_manager
from tit.server.app import create_app
from tit.server.settings import ServerSettings

BEARER = {"Authorization": "Bearer test"}
CAP = "Electrode,10,0,0,Fz\nElectrode,-10,0,0,Cz\nFiducial,0,80,0,Nz\n"
WARPED = "Electrode,10,0,90,Fz\nElectrode,-10,0,90,Cz\n"


# ── science: tit.caps ─────────────────────────────────────────────────────────


def test_net_stats_reports_spacing_collapse_and_duplicates() -> None:
    names = ["A", "B", "C", "D", "A"]
    world = np.array(
        [[0, 0, 0], [0.5, 0, 0], [10, 0, 0], [0, 30, 0], [50, 0, 0]], dtype=float
    )
    out = caps.net_stats(names, world)
    nn = {i: row["nn_mm"] for i, row in enumerate(out["electrodes"])}
    # A-B 0.5; C's nearest is B at 9.5; D's nearest is A at 30; second A's is C at 40.
    assert nn == {0: 0.5, 1: 0.5, 2: 9.5, 3: 30.0, 4: 40.0}
    assert out["electrodes"][2]["nn_name"] == "B"
    assert out["collapsed"] == [{"a": "A", "b": "B", "distance_mm": 0.5}]
    assert out["duplicate_names"] == ["A"]
    assert out["summary"]["count"] == 5
    assert out["summary"]["nn_min_mm"] == 0.5
    assert out["summary"]["nn_median_mm"] == 9.5


def test_net_stats_scalp_distance_is_to_the_nearest_skin_point() -> None:
    skin = np.array([[0, 0, 3], [100, 0, 0]], dtype=float)
    out = caps.net_stats(["A", "B"], np.array([[0, 0, 0], [96, 0, 0]], float), skin)
    assert [r["scalp_mm"] for r in out["electrodes"]] == [3.0, 4.0]
    assert out["summary"]["scalp_max_mm"] == 4.0


def test_compare_nets_names_the_nearest_label_of_the_other_net() -> None:
    match = caps.compare_nets(
        np.array([[0, 0, 0], [10, 0, 0]], float),
        ["X", "Y"],
        np.array([[0, 2, 0], [10, 0, 5]], float),
    )
    assert match == [
        {"name": "X", "distance_mm": 2.0},
        {"name": "Y", "distance_mm": 5.0},
    ]


def test_validate_mni_cap_counts_electrodes_not_fiducials() -> None:
    assert caps.validate_mni_cap(CAP) == 2


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Fiducial,0,0,0,Nz\n",
        "Generic,0,0,0,X\n",
        "Electrode,0,0,0\n",
        "Electrode,a,0,0,X\n",
        "Electrode,nan,0,0,X\n",
        "Electrode,0,0,1500,X\n",
        "Electrode,0,0,0, \n",
    ],
)
def test_validate_mni_cap_refuses_what_charm_would_skip(text: str) -> None:
    with pytest.raises(caps.CapError):
        caps.validate_mni_cap(text)


# ── routes ────────────────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path, monkeypatch):
    pm = get_path_manager(str(tmp_path))
    m2m = Path(pm.m2m("ernie"))
    (m2m / "eeg_positions").mkdir(parents=True)
    (m2m / "ernie.msh").write_bytes(b"mesh")
    simnibs_caps = tmp_path.parent / (tmp_path.name + "-simnibs-caps")
    simnibs_caps.mkdir()
    (simnibs_caps / "EEG10-10.csv").write_text(CAP)
    monkeypatch.setattr(caps, "simnibs_caps_dir", lambda: simnibs_caps)
    monkeypatch.setattr("tit.catalog.subject_ids", lambda pm: ["ernie"])

    calls: list[dict] = []

    def warp_coordinates(cap, m2m_dir, **kwargs):
        calls.append({"cap": cap, "m2m": m2m_dir, **kwargs})
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
    monkeypatch.setattr(caps, "skin_nodes", lambda path: np.array([[10.0, 0, 92]]))
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="test")),
        base_url="http://127.0.0.1:8765",
    )
    return SimpleNamespace(
        pm=pm, client=client, calls=calls, positions=m2m / "eeg_positions"
    )


def test_every_caps_route_needs_auth(project) -> None:
    c = project.client
    assert c.get("/api/caps/available?subject=ernie").status_code == 401
    assert (
        c.post(
            "/api/caps/warp", json={"subject": "ernie", "caps": ["EEG10-10.csv"]}
        ).status_code
        == 401
    )
    assert c.post("/api/caps/upload?name=x.csv", content=CAP).status_code == 401
    assert c.get("/api/caps/inspect?subject=ernie&net=EEG10-10.csv").status_code == 401


def test_available_lists_sources_and_subject_nets(project) -> None:
    (project.positions / "Legacy.csv").write_text(WARPED)
    rows = project.client.get(
        "/api/caps/available?subject=ernie", headers=BEARER
    ).json()["caps"]
    by_name = {r["name"]: r for r in rows}
    assert by_name["EEG10-10.csv"]["source"] == "simnibs"
    assert by_name["EEG10-10.csv"]["on_subject"] is False
    assert by_name["Legacy.csv"] == {
        **by_name["Legacy.csv"],
        "source": None,
        "on_subject": True,
    }
    assert by_name["Legacy.csv"]["subject_mtime"] > 0
    assert by_name["EEG10-10.csv"]["subject_mtime"] is None


def test_warp_writes_into_eeg_positions_the_way_charm_does(project) -> None:
    r = project.client.post(
        "/api/caps/warp",
        json={"subject": "ernie", "caps": ["EEG10-10.csv"]},
        headers=BEARER,
    )
    assert r.status_code == 200, r.text
    assert (project.positions / "EEG10-10.csv").read_text() == WARPED
    assert (project.positions / "EEG10-10.geo").is_file()
    assert sorted(p.name for p in project.positions.iterdir()) == [
        "EEG10-10.csv",
        "EEG10-10.geo",
    ]
    (call,) = project.calls
    assert call["transformation_direction"] == "mni2subject"
    assert call["skin_tag"] == 1005
    assert call["m2m"] == str(Path(project.pm.m2m("ernie")).resolve())


def test_warp_over_an_existing_cap_is_409_until_overwrite(project) -> None:
    (project.positions / "EEG10-10.csv").write_text("old")
    body = {"subject": "ernie", "caps": ["EEG10-10.csv"]}
    r = project.client.post("/api/caps/warp", json=body, headers=BEARER)
    assert r.status_code == 409
    assert (project.positions / "EEG10-10.csv").read_text() == "old"
    r = project.client.post(
        "/api/caps/warp", json={**body, "overwrite": True}, headers=BEARER
    )
    assert r.status_code == 200
    assert (project.positions / "EEG10-10.csv").read_text() == WARPED


@pytest.mark.parametrize(
    "name", ["../../evil.csv", "/etc/passwd", "a/b.csv", "..", "nope.csv"]
)
def test_warp_refuses_unknown_and_traversing_names(project, name: str) -> None:
    r = project.client.post(
        "/api/caps/warp", json={"subject": "ernie", "caps": [name]}, headers=BEARER
    )
    assert r.status_code in (404, 422)
    assert project.calls == []


def test_upload_stores_a_project_cap_that_can_then_be_warped(project) -> None:
    c = project.client
    r = c.post("/api/caps/upload?name=Mine.csv", content=CAP, headers=BEARER)
    assert r.status_code == 201, r.text
    assert r.json()["electrodes"] == 2
    assert (Path(project.pm.custom_eeg_caps()) / "Mine.csv").read_text() == CAP
    assert (
        c.post(
            "/api/caps/upload?name=Mine.csv", content=CAP, headers=BEARER
        ).status_code
        == 409
    )
    rows = c.get("/api/caps/available?subject=ernie", headers=BEARER).json()["caps"]
    assert {"name": "Mine.csv", "source": "project"}.items() <= {
        k: v for r in rows if r["name"] == "Mine.csv" for k, v in r.items()
    }.items()
    r = c.post(
        "/api/caps/warp",
        json={"subject": "ernie", "caps": ["Mine.csv"]},
        headers=BEARER,
    )
    assert r.status_code == 200


@pytest.mark.parametrize(
    ("name", "body", "status"),
    [
        ("../x.csv", CAP, 422),
        ("x.txt", CAP, 422),
        ("EEG10-10.csv", CAP, 409),
        ("x.csv", "Electrode,0,0,0\n", 422),
        ("x.csv", b"\xff\xfe", 422),
    ],
)
def test_upload_refuses_bad_names_and_bad_files(project, name, body, status) -> None:
    r = project.client.post(
        f"/api/caps/upload?name={name}", content=body, headers=BEARER
    )
    assert r.status_code == status
    assert not Path(project.pm.custom_eeg_caps()).joinpath("x.csv").exists()


def test_upload_size_limit(project, monkeypatch) -> None:
    monkeypatch.setattr(caps, "MAX_CAP_BYTES", 8)
    r = project.client.post("/api/caps/upload?name=x.csv", content=CAP, headers=BEARER)
    assert r.status_code == 413


def test_inspect_reports_the_net_and_its_comparison(project) -> None:
    (project.positions / "A.csv").write_text(WARPED)
    (project.positions / "B.csv").write_text(
        "Electrode,10,3,90,F1\nElectrode,-10,0,94,C1\n"
    )
    r = project.client.get(
        "/api/caps/inspect?subject=ernie&net=A.csv&compare=B.csv", headers=BEARER
    )
    assert r.status_code == 200, r.text
    out = r.json()
    rows = {row["name"]: row for row in out["electrodes"]}
    assert rows["Fz"]["nn_mm"] == 20.0  # Fz (10,0,90) to Cz (-10,0,90)
    assert rows["Fz"]["scalp_mm"] == 2.0  # to the one skin node (10,0,92)
    assert (rows["Fz"]["compare_name"], rows["Fz"]["compare_mm"]) == ("F1", 3.0)
    assert (rows["Cz"]["compare_name"], rows["Cz"]["compare_mm"]) == ("C1", 4.0)
    assert out["compare"]["max_mm"] == 4.0
    assert len(out["compare"]["electrodes"]) == 2


def test_inspect_unknown_net_is_404(project) -> None:
    r = project.client.get(
        "/api/caps/inspect?subject=ernie&net=none.csv", headers=BEARER
    )
    assert r.status_code == 404
