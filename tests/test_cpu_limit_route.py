"""`GET/PUT /api/cpu-limit` round-trip (the Settings page's CPU limit).

Expected numbers are floor(percent x 10 / 100) for a pinned 10-CPU container; the conftest points
the settings file at a scratch path, so the developer's real config is never read or written.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import tit.cpu
from tit.server.routes.cpu_limit import router


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(tit.cpu, "effective_cpus", lambda root=None: 10)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_default_is_seventy_percent(client: TestClient) -> None:
    assert client.get("/api/cpu-limit").json() == {
        "percent": 70,
        "cores": 7,
        "available_cores": 10,
        "default_percent": 70,
    }


def test_put_saves_and_every_reader_sees_it(client: TestClient) -> None:
    saved = client.put("/api/cpu-limit", json={"percent": 45})
    assert saved.status_code == 200
    assert saved.json()["percent"] == 45 and saved.json()["cores"] == 4
    assert client.get("/api/cpu-limit").json()["cores"] == 4
    assert tit.cpu.cpu_limit() == 4


@pytest.mark.parametrize(
    "body",
    [
        {"percent": 5},
        {"percent": 101},
        {"percent": "70"},
        {"percent": 70.5},
        {},
        {"percent": 70, "x": 1},
    ],
)
def test_put_rejects_invalid_bodies(client: TestClient, body: dict) -> None:
    assert client.put("/api/cpu-limit", json=body).status_code == 422
    assert client.get("/api/cpu-limit").json()["percent"] == 70
