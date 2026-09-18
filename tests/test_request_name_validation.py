"""Request values that name a subject or an on-disk entity are validated at the boundary.

``tit.server.schemas.SubjectId`` / ``EntityName`` (docs/dev/DECISIONS.md
§ 2026-09-18): a traversal, an absolute path or a separator in a query or path
parameter is a 422 naming the rule, before any route body -- and therefore any
``PathManager`` call -- runs. A well-formed but unknown name still gets the
route's own answer (404), so the boundary check changes nothing for valid
input.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import (  # noqa: E402
    get_path_manager,
    is_valid_name,
    is_valid_subject_id,
    reset_path_manager,
)
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

BAD_NAMES = ["../x", "/etc/passwd", "a/b", "..", ".hidden", "a\\b"]


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_path_manager()
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m("ernie"))
    app = create_app(ServerSettings(project_dir=str(tmp_path), token=TOKEN))
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c
    reset_path_manager()


# (method, url, params) -- one representative per query/path parameter family.
SUBJECT_ROUTES = [
    ("GET", "/api/catalog/simulations", {}),
    ("GET", "/api/catalog/rois", {}),
    ("GET", "/api/catalog/flex-runs", {}),
    ("GET", "/api/catalog/eeg-nets", {}),
    ("GET", "/api/catalog/reports", {}),
    ("GET", "/api/catalog/atlases", {}),
    ("GET", "/api/scene/electrodes", {"net": "GSN-HydroCel-185.csv"}),
]


@pytest.mark.parametrize("bad", BAD_NAMES)
@pytest.mark.parametrize("method, url, extra", SUBJECT_ROUTES)
def test_subject_query_rejects_path_shaped_values(client, method, url, extra, bad):
    response = client.request(
        method, url, params={"subject": bad, **extra}, headers=BEARER
    )
    assert response.status_code == 422, (url, bad, response.text)
    assert "subject id" in response.text


@pytest.mark.parametrize("method, url, extra", SUBJECT_ROUTES)
def test_subject_query_accepts_a_valid_unknown_subject(client, method, url, extra):
    response = client.request(
        method, url, params={"subject": "nobody-01", **extra}, headers=BEARER
    )
    assert response.status_code == 404, (url, response.text)


# ``..`` and a separator never reach a path parameter: the client and the router
# normalise them away first, so a path segment can only be a single name.
BAD_PATH_SEGMENTS = [".hidden", "a\\b", "a b..c", "-" * 129]


@pytest.mark.parametrize("bad", BAD_PATH_SEGMENTS)
def test_subject_path_parameter_is_validated(client, bad):
    response = client.get(f"/api/catalog/subjects/{bad}", headers=BEARER)
    assert response.status_code == 422, (bad, response.text)


ENTITY_QUERIES = [
    ("/api/catalog/analyses", "simulation"),
    ("/api/catalog/atlases/regions", "atlas"),
    ("/api/scene/electrodes", "net"),
    ("/api/view/simulation", "simulation"),
]


@pytest.mark.parametrize("bad", BAD_NAMES)
@pytest.mark.parametrize("url, field", ENTITY_QUERIES)
def test_entity_query_rejects_path_shaped_values(client, url, field, bad):
    response = client.get(url, params={"subject": "ernie", field: bad}, headers=BEARER)
    assert response.status_code == 422, (url, field, bad, response.text)


def test_entity_query_accepts_dots_hyphens_and_underscores(client):
    response = client.get(
        "/api/catalog/analyses",
        params={"subject": "ernie", "simulation": "L_Insula-v1.0"},
        headers=BEARER,
    )
    assert response.status_code != 422, response.text


@pytest.mark.parametrize("bad", BAD_PATH_SEGMENTS)
def test_entity_path_parameter_is_validated(client, bad):
    response = client.delete(
        f"/api/catalog/rois/{bad}", params={"subject": "ernie"}, headers=BEARER
    )
    assert response.status_code == 422, (bad, response.text)


def test_plan_subject_ids_are_validated(client):
    response = client.post(
        "/api/plan/sim",
        json={"config": {}, "subject_ids": ["../../etc"]},
        headers=BEARER,
    )
    assert response.status_code == 422, response.text


def test_target_preview_subject_is_validated(client):
    response = client.post(
        "/api/scene/target-preview",
        json={
            "subject": "../ernie",
            "roi": {
                "kind": "spherical",
                "space": "subject",
                "spheres": [{"center": [0, 0, 0], "radius": 5}],
            },
        },
        headers=BEARER,
    )
    assert response.status_code == 422, response.text


# ── the real names of Dataset 000 must all pass ─────────────────────────────

DATASET_000 = os.environ.get("TIT_DATASET_000", "/Users/idohaber/datasets/000")


@pytest.mark.skipif(
    not os.path.isdir(DATASET_000), reason="Dataset 000 is not on this machine"
)
def test_every_name_in_dataset_000_passes_the_validators():
    """Read-only walk of the maintainer's dataset: no real name may be refused."""
    root = Path(DATASET_000)
    simnibs = root / "derivatives" / "SimNIBS"
    subjects = [p.name[4:] for p in simnibs.iterdir() if p.name.startswith("sub-")]
    assert subjects, "the dataset has subjects"
    for sid in subjects:
        assert is_valid_subject_id(sid), sid
        sub = simnibs / f"sub-{sid}"
        for kind in (
            "Simulations",
            "flex-search",
            "ex-search",
            "m-ex-search",
            "recip-search",
        ):
            for run in (sub / kind).iterdir() if (sub / kind).is_dir() else []:
                if run.name.startswith("."):
                    continue
                assert is_valid_name(run.name), (kind, run.name)
        for m2m in sub.glob("m2m_*"):
            for cap in (m2m / "eeg_positions").glob("*.csv"):
                assert is_valid_name(cap.name), cap.name
            for roi in (m2m / "ROIs").glob("*.csv"):
                assert is_valid_name(roi.name), roi.name
            for mask in (m2m / "masks").glob("*.nii*"):
                assert is_valid_name(mask.name), mask.name
    for atlas in (root / "derivatives" / "SimNIBS").glob(
        "sub-*/m2m_*/segmentation/*.nii.gz"
    ):
        assert is_valid_name(atlas.name), atlas.name
    for atlas in (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("resources", "atlas")
        .glob("*.nii*")
    ):
        assert is_valid_name(atlas.name), atlas.name
