"""``GET /api/openapi.json`` — the live server's own OpenAPI document (lane FX2).

The failure these pin: the app is built with ``openapi_url=None``, so a client talking to a
running server could not discover its routes or which ``JobKind``s it accepts, and had to read a
checked-in contract file instead (`docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` open issue 6).
The document must be behind auth (it maps a server that can start jobs on the user's machine),
must be byte-identical to what ``--dump-openapi`` writes, and must actually carry the job enums.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs.spec import JOB_KINDS, JOB_STATES  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-abc123"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(project_dir=str(tmp_path), token=TOKEN)


@pytest.fixture()
def client(settings: ServerSettings) -> TestClient:
    return TestClient(create_app(settings), base_url=BASE)


def test_openapi_needs_auth(client: TestClient) -> None:
    assert client.get("/api/openapi.json").status_code == 401
    assert client.get("/api/openapi.json", headers=BEARER).status_code == 200


def test_openapi_is_the_dump_document(settings: ServerSettings) -> None:
    """The served document and ``--dump-openapi``'s are the same object, not two renderings."""
    served = TestClient(create_app(settings), base_url=BASE).get(
        "/api/openapi.json", headers=BEARER
    )
    dumped = create_app(settings).openapi()
    assert json.loads(served.text) == dumped


def test_openapi_describes_its_own_route_and_the_websockets(client: TestClient) -> None:
    doc = client.get("/api/openapi.json", headers=BEARER).json()
    assert "/api/openapi.json" in doc["paths"]
    assert "/api/jobs" in doc["paths"]
    assert "/ws/system" in doc["paths"]


def test_openapi_publishes_the_job_enums(client: TestClient) -> None:
    """The reason to publish it: the kinds a client may submit, from the server's own registry."""
    schemas = client.get("/api/openapi.json", headers=BEARER).json()["components"][
        "schemas"
    ]
    assert schemas["JobKind"]["enum"] == list(JOB_KINDS)
    assert schemas["JobState"]["enum"] == list(JOB_STATES)


def test_openapi_never_carries_the_token(client: TestClient) -> None:
    assert TOKEN not in client.get("/api/openapi.json", headers=BEARER).text
