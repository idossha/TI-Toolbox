"""``/api/tetravox`` — the HTTP surface of the dynamic embed delivery (E1-E4).

Everything here runs against a real ``create_app`` with a tmp install root, a
tmp baked floor, and (where a download is involved) a tarball served over
loopback http by :mod:`http.server`.  Nothing reaches the network.
"""

from __future__ import annotations

import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402
from tit.tetravox import store  # noqa: E402
from tests.test_tetravox_install import (  # noqa: E402
    digest_of,
    write_bundle_tarball,
)
from tests.test_tetravox_store import make_bundle  # noqa: E402

TOKEN = "test-token-abc123"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
# TestClient.websocket_connect joins against ws://testserver; an absolute URL is
# what gets the Host header past TrustedHost (same reason as test_server_skeleton).
WS_TETRAVOX = "ws://127.0.0.1:8765/ws/tetravox"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "project").mkdir()
    return tmp_path / "project"


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "install-root")


@pytest.fixture()
def baked(tmp_path: Path) -> str:
    return make_bundle(tmp_path / "opt" / "embed", "0.3.4", 1)


@pytest.fixture()
def client(project: Path, root: str, baked: str) -> TestClient:
    settings = ServerSettings(
        project_dir=str(project),
        token=TOKEN,
        tetravox_embed_dir=baked,
        tetravox_install_root=root,
    )
    return TestClient(create_app(settings), base_url=BASE)


@pytest.fixture()
def served(tmp_path: Path):
    """A loopback http server over a scratch directory; yields ``(base, dir)``."""
    directory = tmp_path / "www"
    directory.mkdir()
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", directory
    finally:
        server.shutdown()
        server.server_close()


def publish(directory, *, version="0.4.0", protocol=2, **kwargs) -> tuple[str, str]:
    """Write a bundle tarball into the served directory; return ``(name, sha256)``."""
    name = f"tetravox-embed-{version}.tgz"
    path = write_bundle_tarball(
        directory / name,
        version=version,
        protocol=protocol,
        top=f"tetravox-embed-{version}",
        **kwargs,
    )
    return name, digest_of(path)


# ── read ─────────────────────────────────────────────────────────────────────


def test_get_reports_the_baked_floor_when_nothing_is_installed(client, baked):
    body = client.get("/api/tetravox", headers=BEARER).json()
    assert body["active"]["source"] == "baked"
    assert body["active"]["path"] == baked
    assert body["active"]["active"] is True
    assert body["installed"] == []
    assert body["supported"] == {"min": 1, "max": 2}
    assert body["reason"] == "the version baked into the image"


def test_the_routes_need_authentication(client):
    assert client.get("/api/tetravox").status_code == 401
    assert client.get("/api/tetravox/updates").status_code == 401
    assert client.post("/api/tetravox/install", json={}).status_code == 401
    assert client.post("/api/tetravox/activate", json={}).status_code == 401
    assert client.delete("/api/tetravox/0.4.0").status_code == 401


# ── install ──────────────────────────────────────────────────────────────────


def test_install_serves_the_new_bundle_at_tetravox_without_a_restart(
    client, served, root, baked
):
    """E2's whole point: the same running process serves the new bundle.

    A restart to pick up a viewer update would defeat installing one at runtime.
    """
    base, directory = served
    name, sha256 = publish(directory)
    assert client.get("/tetravox/index.html").text == "<html>0.3.4</html>"

    response = client.post(
        "/api/tetravox/install",
        headers=BEARER,
        json={"url": f"{base}/{name}", "sha256": sha256},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active"]["version"] == "0.4.0"
    assert body["active"]["source"] == "installed"
    assert body["active"]["path"] == os.path.join(root, "0.4.0")
    assert [r["version"] for r in body["installed"]] == ["0.4.0"]

    assert client.get("/tetravox/index.html").text == "<html>0.4.0</html>"
    caps = client.get("/api/capabilities", headers=BEARER).json()["tetravox_embed"]
    assert caps["version"] == "0.4.0"
    assert caps["source"] == "installed"
    assert {"markers", "pick", "camera"} <= set(caps["features"])


def test_install_refuses_a_digest_mismatch_with_the_real_digest_in_the_message(
    client, served, root
):
    base, directory = served
    name, _sha = publish(directory)
    response = client.post(
        "/api/tetravox/install",
        headers=BEARER,
        json={"url": f"{base}/{name}", "sha256": "0" * 64},
    )
    assert response.status_code == 400
    assert "sha256 mismatch" in response.json()["detail"]
    assert not os.path.isdir(os.path.join(root, "0.4.0"))
    assert client.get("/api/tetravox", headers=BEARER).json()["installed"] == []


def test_install_refuses_a_host_off_the_allowlist(client):
    response = client.post(
        "/api/tetravox/install",
        headers=BEARER,
        json={"url": "https://evil.example/b.tgz", "sha256": "a" * 64},
    )
    assert response.status_code == 400
    assert "not an allowed download host" in response.json()["detail"]


def test_install_refuses_a_bundle_outside_the_supported_protocol_range(client, served):
    base, directory = served
    name, sha256 = publish(directory, version="9.0.0", protocol=99)
    response = client.post(
        "/api/tetravox/install",
        headers=BEARER,
        json={"url": f"{base}/{name}", "sha256": sha256},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "protocol 99" in detail and "supports protocol 1-2" in detail


def test_install_needs_a_url_or_a_version(client):
    response = client.post("/api/tetravox/install", headers=BEARER, json={})
    assert response.status_code == 400
    assert "url" in response.json()["detail"]


# ── the release index ────────────────────────────────────────────────────────


def test_updates_lists_the_index_and_marks_what_is_installed(
    client, served, monkeypatch, root
):
    base, directory = served
    name, sha256 = publish(directory)
    (directory / "releases.json").write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "version": "0.4.0",
                        "protocol": 2,
                        "url": f"{base}/{name}",
                        "sha256": sha256,
                        "notes": "adds markers",
                    },
                    {
                        "version": "9.0.0",
                        "protocol": 99,
                        "url": f"{base}/future.tgz",
                        "sha256": "f" * 64,
                    },
                ]
            }
        )
    )
    monkeypatch.setenv("TIT_TETRAVOX_RELEASE_INDEX", f"{base}/releases.json")

    body = client.get("/api/tetravox/updates", headers=BEARER).json()
    assert body["available"] is True
    versions = {r["version"]: r for r in body["releases"]}
    assert versions["0.4.0"]["compatible"] is True
    assert versions["0.4.0"]["installed"] is False
    assert versions["0.4.0"]["notes"] == "adds markers"
    assert versions["9.0.0"]["compatible"] is False  # shown, but not installable

    # Install by version, with no URL or digest in the request at all.
    installed = client.post(
        "/api/tetravox/install", headers=BEARER, json={"version": "0.4.0"}
    )
    assert installed.status_code == 200, installed.text
    assert installed.json()["active"]["version"] == "0.4.0"
    body = client.get("/api/tetravox/updates", headers=BEARER).json()
    assert {r["version"]: r["installed"] for r in body["releases"]}["0.4.0"] is True


def test_updates_says_it_is_offline_instead_of_failing(client, monkeypatch):
    """A machine with no network must render a sentence, not an error state."""
    monkeypatch.setenv("TIT_TETRAVOX_RELEASE_INDEX", "http://127.0.0.1:9/releases.json")
    response = client.get("/api/tetravox/updates", headers=BEARER)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["releases"] == []
    assert "Could not reach the release index" in body["message"]


def test_install_by_a_version_the_index_does_not_have_is_a_readable_404(
    client, served, monkeypatch
):
    base, directory = served
    (directory / "releases.json").write_text(json.dumps({"releases": []}))
    monkeypatch.setenv("TIT_TETRAVOX_RELEASE_INDEX", f"{base}/releases.json")
    response = client.post(
        "/api/tetravox/install", headers=BEARER, json={"version": "0.9.9"}
    )
    assert response.status_code == 404
    assert "no version 0.9.9" in response.json()["detail"]


# ── activate / rollback / remove ─────────────────────────────────────────────


def test_activate_rolls_back_to_the_baked_bundle_and_forward_again(
    client, served, baked, root
):
    base, directory = served
    name, sha256 = publish(directory)
    client.post(
        "/api/tetravox/install",
        headers=BEARER,
        json={"url": f"{base}/{name}", "sha256": sha256},
    )
    assert client.get("/tetravox/index.html").text == "<html>0.4.0</html>"

    rolled_back = client.post(
        "/api/tetravox/activate", headers=BEARER, json={"version": "baked"}
    ).json()
    assert rolled_back["active"]["source"] == "baked"
    assert rolled_back["active"]["version"] == "0.3.4"
    assert client.get("/tetravox/index.html").text == "<html>0.3.4</html>"
    # The rolled-back bundle is still installed: going forward again is one click.
    assert [r["version"] for r in rolled_back["installed"]] == ["0.4.0"]

    forward = client.post(
        "/api/tetravox/activate", headers=BEARER, json={"version": "0.4.0"}
    ).json()
    assert forward["active"]["version"] == "0.4.0"
    assert client.get("/tetravox/index.html").text == "<html>0.4.0</html>"


def test_activating_a_version_that_is_not_installed_is_a_readable_404(client):
    response = client.post(
        "/api/tetravox/activate", headers=BEARER, json={"version": "0.9.9"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Not installed: 0.9.9"


def test_activate_needs_a_version(client):
    response = client.post("/api/tetravox/activate", headers=BEARER, json={})
    assert response.status_code == 400


def test_delete_removes_a_bundle_and_falls_back_to_the_baked_one(client, served, root):
    base, directory = served
    name, sha256 = publish(directory)
    client.post(
        "/api/tetravox/install",
        headers=BEARER,
        json={"url": f"{base}/{name}", "sha256": sha256},
    )
    body = client.delete("/api/tetravox/0.4.0", headers=BEARER).json()
    assert body["installed"] == []
    assert body["active"]["source"] == "baked"
    assert not os.path.exists(os.path.join(root, "0.4.0"))
    assert client.get("/tetravox/index.html").text == "<html>0.3.4</html>"


def test_delete_of_an_unknown_version_is_a_404(client):
    assert client.delete("/api/tetravox/0.9.9", headers=BEARER).status_code == 404


def test_delete_cannot_escape_the_install_root(client, tmp_path):
    """``version`` is a directory name; a traversal must never reach a rmtree."""
    victim = tmp_path / "victim"
    victim.mkdir()
    for version in ("%2e%2e", "..%2Fvictim", "..%2f..%2fvictim"):
        response = client.delete(f"/api/tetravox/{version}", headers=BEARER)
        # 404 (rejected by name) or 405/307 (never routed at all) -- both mean the
        # rmtree was never reached, which is the property under test.
        assert response.status_code != 200, version
    assert victim.exists()


# ── the dev override still wins ──────────────────────────────────────────────


def test_a_dev_override_outranks_an_installed_bundle(project, tmp_path, root, baked):
    override = make_bundle(tmp_path / "dev-embed", "0.0.0-dev", 1)
    make_bundle(os.path.join(root, "0.4.0"), "0.4.0", 2)
    store.write_pin(root, "0.4.0")
    settings = ServerSettings(
        project_dir=str(project),
        token=TOKEN,
        tetravox_embed_dir=baked,
        tetravox_embed_override=override,
        tetravox_install_root=root,
    )
    client = TestClient(create_app(settings), base_url=BASE)
    body = client.get("/api/tetravox", headers=BEARER).json()
    assert body["active"]["source"] == "override"
    assert body["active"]["version"] == "0.0.0-dev"
    assert client.get("/tetravox/index.html").text == "<html>0.0.0-dev</html>"


# ── A3: the policy, the cache, and the startup task ──────────────────────────


def test_the_policy_is_on_by_default_and_the_route_turns_it_off(client, root):
    assert client.get("/api/tetravox", headers=BEARER).json()["auto_update"] is True
    response = client.post(
        "/api/tetravox/policy", headers=BEARER, json={"auto_update": False}
    )
    assert response.status_code == 200
    assert response.json()["auto_update"] is False
    # Persisted, not held in memory: a restart must not silently turn it back on.
    from tit.tetravox import updates

    assert updates.read_policy(root) is False
    assert (
        client.get("/api/tetravox/updates", headers=BEARER).json()["auto_update"]
        is False
    )


def test_a_policy_that_is_not_a_boolean_is_refused(client):
    response = client.post(
        "/api/tetravox/policy", headers=BEARER, json={"auto_update": "yes"}
    )
    assert response.status_code == 400
    assert "boolean" in response.json()["detail"]


def test_reading_updates_twice_costs_one_request_and_check_now_forces_a_fresh_one(
    client, served, monkeypatch
):
    """The 60-per-hour budget is spent by the user pressing the button, not by rendering."""
    base, directory = served
    (directory / "releases.json").write_text(json.dumps({"releases": []}))
    monkeypatch.setenv("TIT_TETRAVOX_RELEASE_INDEX", f"{base}/releases.json")
    first = client.get("/api/tetravox/updates", headers=BEARER).json()
    assert first["from_cache"] is False and first["checked_at"] is not None
    second = client.get("/api/tetravox/updates", headers=BEARER).json()
    assert second["from_cache"] is True
    forced = client.get("/api/tetravox/updates?refresh=true", headers=BEARER).json()
    assert forced["from_cache"] is False


def test_the_startup_check_does_not_delay_health(project, root, baked, monkeypatch):
    """Measured, not asserted: the index hangs for 5 s and /api/health still answers.

    The background task is created by the lifespan and every network call runs in
    a threadpool, so the only way this can fail is if something awaited the check
    on the event loop -- which is exactly the mistake worth a timing test.
    """
    import time as _time

    import threading as _threading

    from http.server import BaseHTTPRequestHandler

    class Slow(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            _time.sleep(5.0)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"[]")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    _threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv(
        "TIT_TETRAVOX_RELEASE_INDEX",
        f"http://127.0.0.1:{server.server_port}/repos/idossha/tetravox/releases",
    )
    monkeypatch.setenv("TIT_TETRAVOX_INSTALL_ROOT", root)
    from tit.tetravox import updates

    monkeypatch.setattr(updates, "STARTUP_DELAY_S", 0.0)
    settings = ServerSettings(
        project_dir=str(project),
        token=TOKEN,
        tetravox_embed_dir=baked,
        tetravox_install_root=root,
    )
    try:
        with TestClient(create_app(settings), base_url=BASE) as c:
            # Sampled across 3 s, not three times in a row: the check is a task that has to be
            # *scheduled* before it could stall anything, so a burst of requests issued the
            # microsecond the client opens can finish before it ever runs.
            #
            # Honest about its reach: `TestClient` drives the app through a blocking portal, and
            # moving the check off `run_in_threadpool` onto the event loop did **not** make this
            # fail (measured -- the run took 8.8 s instead of 3.3 s, and every health sample was
            # still under 10 ms). So this asserts the property, and the evidence that it holds
            # under a real uvicorn is the container measurement in dev/notes/.../AU.md §gates:
            # eight samples straight after a reload, worst 9.3 ms, while the startup check was
            # demonstrably running (its outcome timestamp lands mid-window).
            elapsed = []
            deadline = _time.monotonic() + 3.0
            while _time.monotonic() < deadline:
                start = _time.monotonic()
                assert c.get("/api/health").status_code == 200
                elapsed.append(_time.monotonic() - start)
                _time.sleep(0.05)
            assert len(elapsed) > 10
            assert max(elapsed) < 1.0, f"worst /api/health took {max(elapsed):.3f}s"
    finally:
        server.shutdown()
        server.server_close()


def test_the_tetravox_updated_event_reaches_a_connected_client(client):
    """`/ws/tetravox` is silent until the bundle is replaced under the app."""
    from tit.server import ws as server_ws

    with client.websocket_connect(f"{WS_TETRAVOX}?token={TOKEN}") as socket:
        # The hub is what the background task publishes through.
        for _ in range(50):
            if server_ws.events.subscriber_count:
                break
            import time as _t

            _t.sleep(0.02)
        server_ws.publish_tetravox_updated(
            "0.4.0",
            2,
            "Tetravox 0.4.0 installed and active — reload the viewer to use it",
        )
        message = socket.receive_json()
    assert message["type"] == "tetravox.updated"
    assert message["version"] == "0.4.0"
    assert message["protocol"] == 2
    assert "reload the viewer" in message["message"]


def test_ws_tetravox_refuses_an_unauthenticated_client(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS_TETRAVOX) as socket:
            socket.receive_json()
    assert exc.value.code == 4401
