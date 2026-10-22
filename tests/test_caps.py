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
from tit.scene import build, tvsc
from tit.scene import cache as scene_cache
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


def test_every_cap_tit_ships_is_labelled_ti_toolbox() -> None:
    shipped = Path(__file__).parents[1] / "resources" / "ElectrodeCaps_MNI"
    names = {p.name for p in shipped.glob("*.csv")}
    assert names, "has caps to check"
    assert caps.TIT_CAPS == names


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
    # A TI-Toolbox cap as the image has it: copied into SimNIBS's folder.
    (simnibs_caps / "GSN-HydroCel-185.csv").write_text(CAP)
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
    # The scene's surface build, faked: it publishes whatever skin the test
    # set as the cached ``skin`` entry, under the mesh's real fingerprint,
    # and counts how often the head mesh would have been read.
    skin = {"nodes": np.array([[10.0, 0, 92]]), "simplified": False, "builds": 0}

    def build_surfaces(pm, sid):
        skin["builds"] += 1
        fp = build.surface_fingerprint(pm, sid)
        blob = tvsc.encode(skin["nodes"].astype(np.float32))
        meta = {"simplified": skin["simplified"]}
        return {
            "skin": scene_cache.publish(
                pm.project_dir, sid, "skin", fp, blob, meta
            ).meta
        }

    monkeypatch.setattr(build, "build_surfaces", build_surfaces)
    monkeypatch.setattr(caps, "skin_nodes", lambda path: np.array([[10.0, 0, 95]]))
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="test")),
        base_url="http://127.0.0.1:8765",
    )
    return SimpleNamespace(
        pm=pm, client=client, calls=calls, positions=m2m / "eeg_positions", skin=skin
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
    assert by_name["GSN-HydroCel-185.csv"]["source"] == "ti-toolbox"
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
        ("GSN-HydroCel-185.csv", CAP, 409),
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


def _fz_scalp(project) -> float:
    r = project.client.get("/api/caps/inspect?subject=ernie&net=A.csv", headers=BEARER)
    assert r.status_code == 200, r.text
    return {row["name"]: row for row in r.json()["electrodes"]}["Fz"]["scalp_mm"]


def test_inspect_reads_the_mesh_once_and_again_only_when_it_changes(project) -> None:
    """Scalp distance comes from the scene's cached skin, keyed on the mesh file."""
    import os

    (project.positions / "A.csv").write_text(WARPED)
    assert _fz_scalp(project) == 2.0  # Fz (10,0,90) to the skin node (10,0,92)
    assert _fz_scalp(project) == 2.0
    assert project.skin["builds"] == 1, "a second inspect must not re-read the mesh"

    project.skin["nodes"] = np.array([[10.0, 0, 93]])
    mesh = Path(project.pm.m2m("ernie")) / "ernie.msh"
    mesh.write_bytes(b"a re-run charm")
    os.utime(mesh, (2_000_000_000, 2_000_000_000))
    assert _fz_scalp(project) == 3.0  # the new skin, not the cached one
    assert project.skin["builds"] == 2


def test_inspect_measures_a_simplified_skin_against_the_full_mesh(project) -> None:
    (project.positions / "A.csv").write_text(WARPED)
    project.skin["simplified"] = True
    assert _fz_scalp(project) == 5.0  # caps.skin_nodes' full-resolution (10,0,95)


# ── p14: the upload accepts only what SimNIBS's reader keeps ──────────────────
#
# The oracle is SimNIBS 4.6 ``simnibs/utils/csv_reader.py::read_csv_positions``
# (the reader ``warp_coordinates`` calls on the stored file), read as source:
#
# * it keeps a row only when ``row[0]`` is exactly ``"Electrode"``,
#   ``"ReferenceElectrode"`` or ``"Fiducial"`` (no strip, no case folding), so
#   ``electrode`` and `` Electrode`` rows are dropped and the warp of an
#   all-dropped file raises IndexError;
# * it indexes ``row[0]`` of every row, so a blank row in the middle raises
#   IndexError, and it refuses a file whose last row has < 3 cells, so one
#   extra blank line at the end raises ``IOError("... at least 4 rows")``;
# * a UTF-8 byte-order mark is read into the first type cell
#   (``"\ufeffElectrode"``), so that row is dropped;
# * when cells 5-7 of an Electrode row are numbers it reads them as a second
#   position and takes the name from cell 8;
# * names are kept verbatim (``" Cz"`` is not ``"Cz"``), and
#   ``_get_eeg_positions`` keys the net by name, so a repeated name keeps only
#   the last row.
#
# The same corpus against the real reader is
# ``tests/numerical/test_caps_validator_vs_simnibs.py``.

#: Three electrodes as SimNIBS reads them; every normalised upload below must
#: be stored as exactly this text.
CANON = "Electrode,10,0,80,Fz\nElectrode,-10,0,80,Cz\nElectrode,0,20,80,Fp\n"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(CANON.replace("Electrode", "electrode"), id="lowercase-type"),
        pytest.param(CANON.replace("Electrode", " Electrode"), id="leading-space"),
        pytest.param(CANON.replace("Fp\n", "Fz\n"), id="duplicate-name"),
        pytest.param(CANON.replace(",Cz", ", Cz"), id="padded-name"),
        pytest.param("Electrode,10,0,80,1,2,3\n", id="second-position-no-name"),
        pytest.param("Electrode,10,0,80,1,2,300,Fz\n", id="second-position-not-mni"),
    ],
)
def test_validate_mni_cap_refuses_rows_simnibs_drops_or_renames(text: str) -> None:
    with pytest.raises(caps.CapError):
        caps.validate_mni_cap(text)


def test_validate_mni_cap_names_the_exact_type_spelling() -> None:
    with pytest.raises(caps.CapError, match="Row 2: .*Electrode"):
        caps.validate_mni_cap("Electrode,10,0,80,Fz\nelectrode,-10,0,80,Cz\n")


def test_validate_mni_cap_takes_the_name_simnibs_takes_from_a_second_position() -> None:
    # Type,x,y,z,pos2_x,pos2_y,pos2_z,name: two electrodes, names in cell 8.
    text = "Electrode,10,0,80,11,0,80,Fz\nElectrode,-10,0,80,-11,0,80,Cz\n"
    assert caps.validate_mni_cap(text) == 2


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(CANON.replace("Fz\n", "Fz\n\n"), id="blank-middle-row"),
        pytest.param(CANON + "\n", id="trailing-blank-line"),
        pytest.param(CANON.replace("Fz\n", "Fz\n , ,\n"), id="whitespace-row"),
        pytest.param("\ufeff" + CANON, id="utf8-bom"),
        pytest.param(CANON.replace("\n", "\r\n"), id="crlf"),
        pytest.param(CANON.replace("\n", "\r"), id="cr-only"),
    ],
)
def test_upload_stores_the_rows_simnibs_reads(project, text: str) -> None:
    r = project.client.post(
        "/api/caps/upload?name=x.csv", content=text.encode("utf-8"), headers=BEARER
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"name": "x.csv", "electrodes": 3}
    stored = (Path(project.pm.custom_eeg_caps()) / "x.csv").read_bytes()
    assert stored.decode("utf-8") == CANON


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        pytest.param(
            CANON.replace("Electrode", "electrode"), "Row 1", id="lowercase-type"
        ),
        pytest.param(
            CANON.replace("Fp\n", "Fz\n"), "Electrode names repeat", id="duplicate"
        ),
    ],
)
def test_upload_refuses_a_cap_simnibs_would_misread(project, text, reason) -> None:
    r = project.client.post("/api/caps/upload?name=x.csv", content=text, headers=BEARER)
    assert r.status_code == 422
    assert r.json()["detail"].startswith(reason)
    assert not (Path(project.pm.custom_eeg_caps()) / "x.csv").exists()


@pytest.mark.parametrize("error", [IndexError, KeyError])
def test_a_warp_simnibs_crashes_on_is_422_and_leaves_nothing(
    project, monkeypatch, error
) -> None:
    def crashes(cap, m2m_dir, **kwargs):
        Path(kwargs["out_name"]).write_text("half a net")
        raise error("list index out of range")

    monkeypatch.setitem(
        sys.modules,
        "simnibs.utils",
        SimpleNamespace(transformations=SimpleNamespace(warp_coordinates=crashes)),
    )
    r = project.client.post(
        "/api/caps/warp",
        json={"subject": "ernie", "caps": ["EEG10-10.csv"]},
        headers=BEARER,
    )
    assert r.status_code == 422
    assert "list index out of range" in r.json()["detail"]
    assert list(project.positions.iterdir()) == []


def test_upload_with_overwrite_replaces_the_project_cap(project) -> None:
    c = project.client
    directory = Path(project.pm.custom_eeg_caps())
    first = c.post("/api/caps/upload?name=Mine.csv", content=CAP, headers=BEARER)
    assert first.json() == {"name": "Mine.csv", "electrodes": 2}
    r = c.post(
        "/api/caps/upload?name=Mine.csv&overwrite=true", content=CANON, headers=BEARER
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"name": "Mine.csv", "electrodes": 3}
    assert (directory / "Mine.csv").read_text() == CANON
    # Written to a temporary name and renamed into place: no temporary is left.
    assert sorted(p.name for p in directory.iterdir()) == ["Mine.csv"]


def test_an_image_cap_name_is_409_even_with_overwrite(project) -> None:
    r = project.client.post(
        "/api/caps/upload?name=EEG10-10.csv&overwrite=true", content=CAP, headers=BEARER
    )
    assert r.status_code == 409
    assert "rename" in r.json()["detail"]


# ── p14: a Fiducial-only file is not a cap ─────────────────────────────────────

#: SimNIBS 4.6 ``resources/ElectrodeCaps_MNI/Fiducials.csv``: four landmarks,
#: no electrode. charm also writes it to every ``eeg_positions``.
FIDUCIALS = (
    "Fiducial,0,82.9,-43,Nz\nFiducial,0,-116.2,-30.5,Iz\n"
    "Fiducial,-79.6,-20.6,-48.6,LPA\nFiducial,80.6,-20.6,-48.1,RPA\n"
)


def test_fiducials_are_neither_a_source_cap_nor_a_net_on_the_subject(project) -> None:
    from tit import catalog

    (caps.simnibs_caps_dir() / "Fiducials.csv").write_text(FIDUCIALS)
    (project.positions / "Fiducials.csv").write_text(FIDUCIALS)
    (project.positions / "EEG10-10.csv").write_text(WARPED)
    rows = project.client.get(
        "/api/caps/available?subject=ernie", headers=BEARER
    ).json()["caps"]
    assert sorted(r["name"] for r in rows) == ["EEG10-10.csv", "GSN-HydroCel-185.csv"]
    # The catalog's rule (``catalog._eeg_caps_with_electrodes``) is the one shared rule.
    on_subject = {r["name"] for r in rows if r["on_subject"]}
    assert on_subject == {n["name"] for n in catalog.eeg_nets(project.pm, "ernie")}
    assert on_subject == {"EEG10-10.csv"}

    r = project.client.post(
        "/api/caps/warp",
        json={"subject": "ernie", "caps": ["Fiducials.csv"]},
        headers=BEARER,
    )
    assert r.status_code == 404
    assert project.calls == []


# ── p14 fix 1: the validator and the caps list agree; one name, one point ─────
#
# ``_get_eeg_positions`` (SimNIBS 4.6 ``simnibs/utils/csv_reader.py``, read in
# the image) keys Electrode, ReferenceElectrode and Fiducial rows into one
# dict by name, the last row winning. SimNIBS's own EEG10-10_UI_Jurak_2007 and
# EEG10-20_extended_SPM12 repeat ``Iz`` as a later fiducial on the electrode's
# exact point (container probe, 2026-10-22), which moves nothing.

#: An electrode, then a fiducial of its name 134.9 mm away:
#: sqrt(10^2 + 90^2 + 100^2) = sqrt(18200).
FIDUCIAL_TAKES_NZ = (
    "Electrode,10,0,80,Nz\nElectrode,-10,0,80,Cz\nFiducial,0,90,-20,Nz\n"
)


def test_validate_mni_cap_refuses_a_fiducial_that_moves_an_electrode() -> None:
    with pytest.raises(caps.CapError) as raised:
        caps.validate_mni_cap(FIDUCIAL_TAKES_NZ)
    message = str(raised.value)
    assert message.startswith("Row 3: ")
    assert "row 1" in message
    assert "134.9 mm" in message


@pytest.mark.parametrize(
    ("text", "count"),
    [
        # SimNIBS's Jurak / SPM12 pattern: the fiducial sits on the electrode.
        pytest.param(
            "Electrode,10,0,80,Iz\nElectrode,-10,0,80,Cz\nFiducial,10.0,0,80.0,Iz\n",
            2,
            id="fiducial-on-the-electrode",
        ),
        # The electrode is the later row, so the name resolves to it.
        pytest.param(
            "Fiducial,0,90,-20,Nz\nElectrode,10,0,80,Nz\nElectrode,-10,0,80,Cz\n",
            2,
            id="fiducial-before-the-electrode",
        ),
    ],
)
def test_validate_mni_cap_accepts_a_fiducial_that_moves_nothing(text, count) -> None:
    assert caps.validate_mni_cap(text) == count


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("ReferenceElectrode,10,0,80,Ref\n", id="reference-only"),
        pytest.param(
            "ReferenceElectrode,10,0,80,Ref\nFiducial,0,90,-20,Nz\n",
            id="reference-and-fiducial",
        ),
    ],
)
def test_upload_refuses_a_file_the_caps_list_would_hide(project, text) -> None:
    r = project.client.post(
        "/api/caps/upload?name=Ref.csv", content=text, headers=BEARER
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"].startswith("The file has no Electrode rows")
    assert not (Path(project.pm.custom_eeg_caps()) / "Ref.csv").exists()


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(CANON, id="electrodes"),
        pytest.param(CAP, id="electrodes-and-fiducial"),
        pytest.param(
            "ReferenceElectrode,0,-10,95,Ref\nElectrode,10,0,80,Fz\n",
            id="reference-then-electrode",
        ),
        pytest.param(
            "Fiducial,0,90,-20,Nz\nElectrode,10,0,80,Nz\n", id="fiducial-first"
        ),
    ],
)
def test_every_cap_the_upload_accepts_is_listed_as_a_project_cap(project, text) -> None:
    """``validate_mni_cap`` and ``has_electrodes`` are one rule: no 201 the list hides."""
    r = project.client.post(
        "/api/caps/upload?name=Mine.csv", content=text, headers=BEARER
    )
    assert r.status_code == 201, r.text
    rows = project.client.get(
        "/api/caps/available?subject=ernie", headers=BEARER
    ).json()["caps"]
    assert {"name": "Mine.csv", "source": "project"} in [
        {"name": row["name"], "source": row["source"]} for row in rows
    ]


@pytest.mark.parametrize("overwrite", ["false", "true"])
def test_upload_never_takes_the_name_of_simnibs_landmark_file(
    project, overwrite
) -> None:
    """``Fiducials.csv`` is not a cap, but its name is the image's: a project cap
    of that name would be warped over the landmarks charm wrote to the subject."""
    (caps.simnibs_caps_dir() / "Fiducials.csv").write_text(FIDUCIALS)
    r = project.client.post(
        f"/api/caps/upload?name=Fiducials.csv&overwrite={overwrite}",
        content=CANON,
        headers=BEARER,
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == (
        "Fiducials.csv is a cap the image already ships; rename the file"
    )
    assert not (Path(project.pm.custom_eeg_caps()) / "Fiducials.csv").exists()
