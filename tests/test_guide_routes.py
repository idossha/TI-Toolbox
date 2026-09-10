"""``/api/guide/*`` — the fixed guide scene over HTTP (plan R4).

What this pins
    That the guide answers **with no project bound at all** (the thing that
    separates it from ``/api/scene/*``), that every JSON body validates against
    ``contracts/openapi.yaml`` — from which the desktop's
    ``api/schema.d.ts`` is generated — that the bytes routes revalidate by
    SHA-256 ETag, that auth is required like every other ``/api/*`` route, and
    that an unknown part/atlas/net is a readable 404 rather than a traceback.

Where the numbers come from
    The packaged guide itself, so these are the same bytes an installation
    serves. The whole module skips when the assets are not in the checkout.

Deliberately elsewhere
    Package integrity, budgets and provenance: ``tests/test_scene_guide.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.scene import guide  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-guide"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.skipif(
    not (guide.GUIDE_DIR / guide.MANIFEST_NAME).is_file(),
    reason="the guide assets are not present in this checkout",
)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """A server bound to an EMPTY directory: the guide must not need a project."""
    return TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token=TOKEN)), base_url=BASE
    )


def test_the_guide_answers_without_any_project_data(client: TestClient) -> None:
    """No subjects, no head models, no scene cache — and the pane still paints.

    This is R4's reason for existing: the old pane needed the *first selected
    subject* to have an ``m2m_`` directory, so on a fresh project it showed a
    "run charm first" sentence instead of anatomy.
    """
    body = client.get("/api/guide/manifest", headers=BEARER).json()
    assert body["space"] == "guide-ras"
    assert [p["id"] for p in body["parts"]] == ["skin", "gm"]
    assert body["nets"] and body["atlases"]
    assert body["cache"] == {"state": "ready", "built_ms": 0.0}


def test_no_route_takes_a_subject() -> None:
    """A `subject` parameter would be an invitation to couple the pane again.

    Read off the route module's own signatures rather than off a response, so
    the check fails the moment someone adds the parameter back, not once
    something starts sending it.
    """
    import inspect

    from tit.server.routes import guide as guide_routes

    endpoints = [route.endpoint for route in guide_routes.router.routes]
    assert len(endpoints) == 5
    for endpoint in endpoints:
        params = set(inspect.signature(endpoint).parameters)
        assert "subject" not in params, endpoint.__name__
        assert params <= {"part", "atlas", "net", "format", "if_none_match"}


def test_manifest_ids_are_fetchable(client: TestClient) -> None:
    """Every id the manifest advertises resolves over HTTP, at its own url."""
    body = client.get("/api/guide/manifest", headers=BEARER).json()
    for part in body["parts"]:
        response = client.get(part["url"], headers=BEARER)
        assert response.status_code == 200, part["url"]
        assert len(response.content) == part["bytes"]
        gii = client.get(part["url"] + "&format=gii", headers=BEARER)
        assert gii.status_code == 200 and gii.content[:5] == b"<?xml"
    for atlas in body["atlases"]:
        regions = client.get(atlas["url"], headers=BEARER)
        assert regions.status_code == 200, atlas["url"]
        payload = regions.json()
        assert len(payload["legend"]) == atlas["regions"]
        assert client.get(payload["url"], headers=BEARER).status_code == 200
    for net in body["nets"]:
        response = client.get(net["url"], headers=BEARER)
        assert response.status_code == 200, net["url"]
        assert len(response.json()["electrodes"]) == net["electrodes"]


def test_bytes_revalidate_by_sha256_etag(client: TestClient) -> None:
    """Immutable bytes, so a repeat visit costs a 304 and not 2.4 MB."""
    first = client.get("/api/guide/surface?part=gm&format=gii", headers=BEARER)
    etag = first.headers["etag"]
    assert len(etag.strip('"')) == 64, "the ETag is the file's SHA-256"
    assert "immutable" in first.headers["cache-control"]
    again = client.get(
        "/api/guide/surface?part=gm&format=gii",
        headers={**BEARER, "If-None-Match": etag},
    )
    assert again.status_code == 304
    assert again.content == b""


def test_unknown_ids_and_formats_are_readable_failures(client: TestClient) -> None:
    cases = {
        "/api/guide/surface?part=cerebellum": 404,
        "/api/guide/surface?part=gm&format=obj": 400,
        "/api/guide/labels?atlas=NoSuchAtlas": 404,
        "/api/guide/regions?atlas=NoSuchAtlas": 404,
        "/api/guide/electrodes?net=../../etc/passwd": 404,
    }
    for url, status in cases.items():
        response = client.get(url, headers=BEARER)
        assert response.status_code == status, (url, response.status_code)
        assert response.json()["detail"], url


def test_every_guide_route_requires_auth(client: TestClient) -> None:
    for url in (
        "/api/guide/manifest",
        "/api/guide/surface?part=skin",
        "/api/guide/labels?atlas=DK40",
        "/api/guide/regions?atlas=DK40",
        "/api/guide/electrodes?net=EEG10-10_UI_Jurak_2007.csv",
    ):
        assert client.get(url).status_code in (401, 403), url


def test_every_guide_json_response_matches_the_contract_schema(client: TestClient) -> None:
    """The contract is the independent reader; the responses are the data.

    ``desktop/src/renderer/api/schema.d.ts`` is generated from this contract
    and the pane's fetchers take their types from it, so a contract that says
    something the server never sends compiles fine and fails at runtime.
    """
    jsonschema = pytest.importorskip("jsonschema")
    yaml = pytest.importorskip("yaml")

    contract = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "contracts/openapi.yaml").read_text()
    )
    body = client.get("/api/guide/manifest", headers=BEARER).json()
    cases = {
        "/api/guide/manifest": "/api/guide/manifest",
        "/api/guide/regions": body["atlases"][0]["url"],
        "/api/guide/electrodes": body["nets"][0]["url"],
    }
    for operation, url in cases.items():
        response = client.get(url, headers=BEARER)
        assert response.status_code == 200, url
        schema = contract["paths"][operation]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(response.json())


def test_the_contract_schema_check_can_actually_fail(client: TestClient) -> None:
    """A schema that accepts anything would make the test above vacuous."""
    jsonschema = pytest.importorskip("jsonschema")
    yaml = pytest.importorskip("yaml")

    contract = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "contracts/openapi.yaml").read_text()
    )
    schema = contract["paths"]["/api/guide/manifest"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    body = client.get("/api/guide/manifest", headers=BEARER).json()
    # The exact mistake this contract exists to prevent: a guide that claims a
    # subject's coordinate space, which would let a client write its
    # millimetres into a research subject's configuration.
    body["space"] = "subject-ras"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(body)
