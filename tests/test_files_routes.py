"""Tests for ``/api/files/*`` (``tit/server/routes/files.py``).

Focused on the jail (traversal attempts must never escape the project or
resources tree) and the per-route response shapes; report-CSP and CSV/text
happy paths are also covered end to end in ``tests/test_catalog_v1.py``
(``test_reports_and_report_file``, ``test_files_artifact_traversal_forbidden``,
``test_files_csv``) since they need a populated project. This file adds the
cases that need their own project layout: text tail, unknown report id,
unsupported artifact extension, and jailed-but-nonexistent paths.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    log_dir = pm.logs("ernie")
    os.makedirs(log_dir)
    Path(log_dir, "sim.log").write_text(
        "\n".join(f"line {i}" for i in range(1, 11)) + "\n"
    )

    binary_dir = os.path.join(pm.ti_toolbox(), "misc")
    os.makedirs(binary_dir)
    Path(binary_dir, "config.exe").write_bytes(b"not-servable")
    Path(binary_dir, "notes.json").write_text('{"a": 1}')
    Path(binary_dir, "report.html").write_text(
        "<html><body><script>alert(document.cookie)</script></body></html>"
    )

    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def test_text_tail(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    log_path = os.path.join(pm.logs("ernie"), "sim.log")

    full = client.get("/api/files/text", params={"path": log_path}, headers=BEARER)
    assert full.status_code == 200
    assert full.text.count("\n") == 10

    tail = client.get(
        "/api/files/text", params={"path": log_path, "tail": 3}, headers=BEARER
    )
    assert tail.text.splitlines() == ["line 8", "line 9", "line 10"]


def test_text_unauthorized_without_token(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    log_path = os.path.join(pm.logs("ernie"), "sim.log")
    assert client.get("/api/files/text", params={"path": log_path}).status_code == 401


def test_text_missing_file_404(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    missing = os.path.join(pm.logs("ernie"), "nope.log")
    assert (
        client.get(
            "/api/files/text", params={"path": missing}, headers=BEARER
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "traversal_suffix",
    [
        "/../../../../../../etc/passwd",
        "/%2e%2e/%2e%2e/etc/passwd",
    ],
)
def test_text_traversal_outside_jail_is_403(
    client: TestClient, project: Path, traversal_suffix: str
) -> None:
    pm = get_path_manager()
    escaping_path = pm.logs("ernie") + traversal_suffix
    r = client.get("/api/files/text", params={"path": escaping_path}, headers=BEARER)
    # a %-encoded path never resolves off the querystring as a literal
    # traversal (httpx sends it verbatim; the segment stays inside the jail
    # as an odd filename that then 404s) -- either outcome proves nothing
    # outside the jail was read.
    assert r.status_code in (403, 404)
    assert "root:" not in r.text


def test_artifact_unsupported_extension_is_403(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    path = os.path.join(pm.ti_toolbox(), "misc", "config.exe")
    r = client.get("/api/files/artifact", params={"path": path}, headers=BEARER)
    assert r.status_code == 403


def test_artifact_json_is_servable(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    path = os.path.join(pm.ti_toolbox(), "misc", "notes.json")
    r = client.get("/api/files/artifact", params={"path": path}, headers=BEARER)
    assert r.status_code == 200
    assert r.json() == {"a": 1}


def test_artifact_outside_project_and_resources_is_403(
    client: TestClient, project: Path, tmp_path_factory
) -> None:
    outside_root = tmp_path_factory.mktemp("outside")
    secret = outside_root / "secret.json"
    secret.write_text("{}")
    r = client.get("/api/files/artifact", params={"path": str(secret)}, headers=BEARER)
    assert r.status_code == 403


def test_artifact_missing_file_404(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    missing = os.path.join(pm.ti_toolbox(), "misc", "nope.json")
    assert (
        client.get(
            "/api/files/artifact", params={"path": missing}, headers=BEARER
        ).status_code
        == 404
    )


def test_artifact_json_has_nosniff_but_no_sandbox_csp(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    path = os.path.join(pm.ti_toolbox(), "misc", "notes.json")
    r = client.get("/api/files/artifact", params={"path": path}, headers=BEARER)
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    # A non-HTML artifact carries no sandbox CSP -- there is nothing here for
    # a browser to execute as a document in the first place.
    assert "content-security-policy" not in r.headers


def test_artifact_html_has_sandbox_csp_and_nosniff(
    client: TestClient, project: Path
) -> None:
    """ra_14 finding 6: an artifact HTML file must never render with the
    app's own origin/CSP -- a same-origin <script src=...> back into the
    session-cookied API is exactly what an opaque sandboxed origin defeats.
    """
    pm = get_path_manager()
    path = os.path.join(pm.ti_toolbox(), "misc", "report.html")
    r = client.get("/api/files/artifact", params={"path": path}, headers=BEARER)
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    csp = r.headers["content-security-policy"]
    assert "sandbox" in csp
    assert "allow-scripts" in csp


def test_report_unknown_id_404(client: TestClient, project: Path) -> None:
    assert client.get("/api/files/report/ernie/nope", headers=BEARER).status_code == 404


def test_report_id_without_slash_is_404_not_500(
    client: TestClient, project: Path
) -> None:
    assert (
        client.get("/api/files/report/not-a-valid-id", headers=BEARER).status_code
        == 404
    )


def test_report_id_traversal_is_404(client: TestClient, project: Path) -> None:
    r = client.get("/api/files/report/ernie/../../../etc/passwd", headers=BEARER)
    assert r.status_code == 404
