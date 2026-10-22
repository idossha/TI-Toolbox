"""A saved ROI reads back as it was written: its space, its centre and its radius, all finite.

What this pins (p15, 2026-10-22)
--------------------------------
``POST /api/catalog/rois {name: "Thal", x: 10, y: 0, z: 0, space: "mni"}`` answered
``space: "mni"`` but ``GET`` then listed it as ``"subject"``: the CSV holds only ``x,y,z`` and the
listing guessed the space from an ``_MNI`` name suffix. The Optimizer sets the run's
``roi_coordinate_space`` from that listing, so an MNI centre was searched as subject
coordinates. ``x: "nan"`` was also accepted (201), the CSV held ``nan`` and ``GET`` answered
``x: null``.

The rule: for every ROI, ``GET`` returns what the ``POST`` answered (write-response equals
read-back), every listed item validates against the contract's ``Roi`` schema
(``contracts/generated/openapi.json``; numbers, never null), and a non-finite coordinate or
radius is refused with 422 without writing a file. ROIs saved before the space was persisted
(no sidecar) keep the ``_MNI`` suffix convention.

Where the expected values come from: the POST body (the writer's input), the contract file, and
hand-written CSVs; nothing is read back from the code under test to build an expectation.

Reproduce: ``.venv/bin/python -m pytest tests/test_catalog_rois_space.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
jsonschema = pytest.importorskip("jsonschema")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
SUBJECT = {"subject": "ernie"}
OPENAPI = Path(__file__).resolve().parents[1] / "contracts/generated/openapi.json"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m("ernie"))
    roi_dir = Path(pm.rois("ernie"))
    roi_dir.mkdir(parents=True)
    # Written by earlier versions: no sidecar, the space is in the name or not at all.
    (roi_dir / "L_Insula.csv").write_text("-30.0,10.0,5.0\n")
    (roi_dir / "Old_MNI.csv").write_text("1.0,2.0,3.0\n")
    (roi_dir / "roi_list.txt").write_text("L_Insula.csv\nOld_MNI.csv\n")
    return tmp_path


@pytest.fixture()
def client(project: Path, tmp_path_factory, monkeypatch) -> TestClient:
    telemetry_file = tmp_path_factory.mktemp("telemetry") / "telemetry.json"
    monkeypatch.setattr("tit.telemetry._config_path", lambda: telemetry_file)
    monkeypatch.setattr("tit.telemetry._cached_config", None)
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _roi_schema() -> dict:
    return json.loads(OPENAPI.read_text())["components"]["schemas"]["Roi"]


def _listed(client: TestClient) -> dict[str, dict]:
    body = client.get("/api/catalog/rois", params=SUBJECT, headers=BEARER).json()
    schema = _roi_schema()
    assert body, "has ROIs to check"
    for item in body:
        jsonschema.validate(item, schema)
        for key in ("x", "y", "z", "radius"):
            if key in item:
                assert math.isfinite(item[key]), (item["name"], key)
    return {item["name"]: item for item in body}


def _roi_files() -> dict[str, bytes]:
    roi_dir = Path(get_path_manager().rois("ernie"))
    return {p.name: p.read_bytes() for p in roi_dir.iterdir()}


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Thal", "x": 10, "y": 0, "z": 0, "space": "mni"},
        {"name": "Thal", "x": 10, "y": 0, "z": 0, "space": "subject"},
        # The name says MNI, the user said subject: the user's word is kept.
        {"name": "Target_MNI", "x": -12.5, "y": 3.25, "z": 40, "space": "subject"},
        {
            "name": "Ball",
            "x": "1.5",
            "y": "-2",
            "z": "0",
            "space": "mni",
            "radius": 7.5,
        },
        {"name": "NoSpace", "x": 1, "y": 2, "z": 3},
        {"name": "NoSpace_MNI", "x": 1, "y": 2, "z": 3},
    ],
    ids=["mni", "subject", "name-says-mni", "radius", "no-space", "no-space-mni-name"],
)
def test_the_listing_returns_what_the_write_answered(client: TestClient, body: dict):
    r = client.post("/api/catalog/rois", params=SUBJECT, json=body, headers=BEARER)
    assert r.status_code == 201
    written = r.json()
    jsonschema.validate(written, _roi_schema())
    # The write answers the body it was given (independent of the code: the request itself).
    expected_space = body.get(
        "space", "mni" if body["name"].upper().endswith("_MNI") else "subject"
    )
    assert written["space"] == expected_space
    assert [written[k] for k in "xyz"] == [float(body[k]) for k in "xyz"]
    assert written.get("radius") == (
        float(body["radius"]) if "radius" in body else None
    )
    assert _listed(client)[body["name"]] == written


def test_rois_saved_before_the_space_was_persisted_keep_the_suffix_rule(
    client: TestClient,
):
    listed = _listed(client)
    assert listed["L_Insula"] == {
        "name": "L_Insula",
        "x": -30.0,
        "y": 10.0,
        "z": 5.0,
        "space": "subject",
    }
    assert listed["Old_MNI"]["space"] == "mni"


def test_a_centre_rewritten_by_another_writer_is_not_given_a_stale_space(
    client: TestClient, project: Path
):
    """The Ex-search engine writes the same CSV without a sidecar. Its centre wins, and the
    space falls back to the name rule rather than to what an older save said."""
    client.post(
        "/api/catalog/rois",
        params=SUBJECT,
        json={"name": "Thal", "x": 10, "y": 0, "z": 0, "space": "mni"},
        headers=BEARER,
    )
    Path(get_path_manager().rois("ernie"), "Thal.csv").write_text("4.0,5.0,6.0\n")
    assert _listed(client)["Thal"] == {
        "name": "Thal",
        "x": 4.0,
        "y": 5.0,
        "z": 6.0,
        "space": "subject",
    }


NON_FINITE = ["nan", "NaN", "inf", "-inf", "Infinity", "1e309"]


@pytest.mark.parametrize("field", ["x", "y", "z", "radius"])
@pytest.mark.parametrize("value", NON_FINITE)
def test_a_non_finite_coordinate_or_radius_is_refused_and_nothing_is_written(
    client: TestClient, field: str, value: str
):
    body = {"name": "Bad", "x": 1, "y": 2, "z": 3, "space": "subject", field: value}
    before = _roi_files()
    r = client.post("/api/catalog/rois", params=SUBJECT, json=body, headers=BEARER)
    assert r.status_code == 422
    assert _roi_files() == before


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_a_non_finite_json_number_is_refused(client: TestClient, token: str):
    before = _roi_files()
    r = client.post(
        "/api/catalog/rois",
        params=SUBJECT,
        content=f'{{"name": "Bad", "x": {token}, "y": 0, "z": 0}}',
        headers={**BEARER, "Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert _roi_files() == before


@pytest.mark.parametrize(
    "extra", [{"space": "talairach"}, {"space": None}, {"radius": 0}, {"radius": -3}]
)
def test_a_space_outside_the_enum_or_a_radius_that_is_not_positive_is_refused(
    client: TestClient, extra: dict
):
    before = _roi_files()
    body = {"name": "Bad", "x": 1, "y": 2, "z": 3, **extra}
    r = client.post("/api/catalog/rois", params=SUBJECT, json=body, headers=BEARER)
    assert r.status_code == 422
    assert _roi_files() == before


def test_a_csv_holding_nan_is_left_out_of_the_listing_not_listed_as_null(
    client: TestClient,
):
    """Saved before the writer refused it; listing it would break every reader of ``Roi``."""
    Path(get_path_manager().rois("ernie"), "Broken.csv").write_text("nan,0,0\n")
    listed = _listed(client)
    assert "Broken" not in listed
    assert {"L_Insula", "Old_MNI"} <= set(listed)
