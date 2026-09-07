"""``GET /api/subjects/{id}/info`` and :func:`tit.catalog.subject_info`.

The route the Subject Info Viewer panel replaced the Qt extension with. What
these pin, each with the failure it prevents:

* the body really is ``SubjectDetail`` **plus** the inventory, so the panel can
  render its summary from one request rather than two;
* file lists are names and sizes, never paths -- a path in this body is a
  container path the browser cannot open and the user cannot use;
* an unknown subject is a 404 naming the id, not an empty body the panel would
  render as "this subject has nothing";
* the shape matches ``contracts/openapi.v1.yaml``'s ``SubjectInfo``, so the
  generated TypeScript and the server cannot drift apart silently.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("yaml")

import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tit import catalog  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
CONTRACT = Path(__file__).resolve().parents[1] / "contracts/openapi.v1.yaml"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """``ernie``: BIDS anat (T1 + T2) and dwi, an m2m, one simulation with one analysis."""
    pm = get_path_manager(str(tmp_path))

    anat = pm.bids_anat("ernie")
    os.makedirs(anat)
    Path(anat, "sub-ernie_T1w.nii.gz").write_bytes(b"0" * 16)
    Path(anat, "sub-ernie_T1w.json").write_text("{}")
    Path(anat, "sub-ernie_T2w.nii.gz").write_bytes(b"0" * 32)

    dwi = pm.bids_dwi("ernie")
    os.makedirs(dwi)
    Path(dwi, "sub-ernie_dwi.nii.gz").write_bytes(b"0" * 8)
    Path(dwi, "sub-ernie_dwi.bval").write_text("0 1000\n")

    src = pm.sourcedata_subject("ernie")
    os.makedirs(src)
    Path(src, "raw.zip").write_bytes(b"0" * 4)

    m2m = pm.m2m("ernie")
    os.makedirs(m2m)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1")

    os.makedirs(pm.ti_mesh_dir("ernie", "Thalamus"))
    Path(pm.ti_mesh("ernie", "Thalamus")).write_bytes(b"mesh")
    analysis = os.path.join(
        pm.simulation("ernie", "Thalamus"), "Analyses", "Mesh", "run1"
    )
    os.makedirs(analysis)
    # An analysis is the `analysis.json` + `results.csv` pair `tit.analyzer` writes; nothing else
    # on disk identifies one (`tit/catalog.py::_analysis_entry`).
    Path(analysis, "analysis.json").write_text(json.dumps({"field_name": "TI_max"}))
    Path(analysis, "results.csv").write_text("roi,value\nA,1\n")

    stim = os.path.join(m2m, "stim_configs")
    os.makedirs(stim)
    Path(stim, "manual.json").write_text(
        json.dumps({"name": "manual", "type": "U", "electrode_positions": {"E1+": [1, 2, 3]}})
    )
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    return TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )


def test_route_needs_auth(client: TestClient) -> None:
    assert client.get("/api/subjects/ernie/info").status_code == 401


def test_unknown_subject_is_a_404_naming_the_id(client: TestClient) -> None:
    res = client.get("/api/subjects/nobody/info", headers=BEARER)
    assert res.status_code == 404
    assert "nobody" in res.json()["detail"]


def test_body_carries_subject_detail_and_the_inventory(client: TestClient) -> None:
    body = client.get("/api/subjects/ernie/info", headers=BEARER).json()

    # SubjectDetail's own keys, so the panel needs one request and not two.
    assert body["id"] == "ernie"
    assert body["has_m2m"] is True
    assert body["has_dwi"] is True
    assert body["m2m_path"].endswith("m2m_ernie")

    # ... plus the inventory the Qt extension walked the directory for.
    assert [f["name"] for f in body["anat_files"]] == [
        "sub-ernie_T1w.json",
        "sub-ernie_T1w.nii.gz",
        "sub-ernie_T2w.nii.gz",
    ]
    assert body["anat_modalities"] == ["T1w", "T2w"]
    assert [f["name"] for f in body["dwi_files"]] == [
        "sub-ernie_dwi.bval",
        "sub-ernie_dwi.nii.gz",
    ]
    assert [f["name"] for f in body["sourcedata_files"]] == ["raw.zip"]
    assert body["m2m_dirs"] == ["m2m_ernie"]
    assert body["freehand_configs"] == ["manual"]

    sim = body["simulations"][0]
    assert sim["name"] == "Thalamus"
    assert sim["has_ti"] is True
    assert sim["n_meshes"] == 1
    assert sim["analyses"] == ["run1"]
    assert body["n_analyses"] == 1


def test_file_entries_are_names_and_sizes_never_paths(client: TestClient) -> None:
    """A container path in this body is a string the browser cannot open and the user cannot use."""
    body = client.get("/api/subjects/ernie/info", headers=BEARER).json()
    for key in ("anat_files", "dwi_files", "sourcedata_files"):
        for entry in body[key]:
            assert set(entry) == {"name", "size_bytes"}
            assert os.sep not in entry["name"]
    assert body["anat_files"][2]["size_bytes"] == 32


def test_missing_directories_are_empty_lists_not_errors(tmp_path: Path) -> None:
    """A subject with only an m2m still answers; the panel must never 500 on a sparse project."""
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m("bare"))
    info = catalog.subject_info(pm, "bare")
    assert info is not None
    assert info["anat_files"] == []
    assert info["dwi_files"] == []
    assert info["simulations"] == []
    assert info["n_analyses"] == 0


def _required(schema: dict[str, Any], spec: dict[str, Any]) -> set[str]:
    """Required property names of a schema, resolving `$ref` and merging `allOf`."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _required(spec["components"]["schemas"][name], spec)
    out = set(schema.get("required", []))
    for part in schema.get("allOf", []):
        out |= _required(part, spec)
    return out


def test_body_matches_the_contract_schema(client: TestClient) -> None:
    spec = yaml.safe_load(CONTRACT.read_text())
    body = client.get("/api/subjects/ernie/info", headers=BEARER).json()
    required = _required({"$ref": "#/components/schemas/SubjectInfo"}, spec)
    assert required, "SubjectInfo declares no required properties"
    assert required <= set(body), sorted(required - set(body))
