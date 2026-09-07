"""Host tests for the ``tit.server`` Phase-0 skeleton (FastAPI TestClient)."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server import COOKIE_NAME  # noqa: E402
from tit.server.app import CSP_HEADER, create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-abc123"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
# TestClient.websocket_connect joins against ws://testserver; give it an absolute
# URL so the Host header passes TrustedHost like the HTTP calls do.
WS = "ws://127.0.0.1:8765/ws/system"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A project laid out with PathManager's own path rules.

    ``001``: raw + freesurfer + m2m + two simulations (TI, and TI+mTI).
    ``002``: raw only.  ``003``: SimNIBS folder without m2m (ignored by
    ``list_simnibs_subjects``), plus a ``.hidden`` simulation dir.
    """
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.bids_anat("001"))
    os.makedirs(pm.freesurfer_mri("001"))
    os.makedirs(pm.m2m("001"))
    os.makedirs(pm.ti_mesh_dir("001", "simA"))
    os.makedirs(pm.ti_mesh_dir("001", "simB"))
    os.makedirs(pm.mti_mesh_dir("001", "simB"))
    os.makedirs(os.path.join(pm.simulations("001"), ".hidden"))
    os.makedirs(pm.bids_anat("002"))
    os.makedirs(pm.sub("003"))
    # non-subject entries that must be ignored
    os.makedirs(os.path.join(pm.freesurfer(), "fsaverage"))
    (tmp_path / "dataset_description.json").write_text("{}")
    return tmp_path


@pytest.fixture()
def settings(project: Path) -> ServerSettings:
    return ServerSettings(project_dir=str(project), token=TOKEN)


@pytest.fixture()
def client(settings: ServerSettings) -> TestClient:
    return TestClient(create_app(settings), base_url=BASE)


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------


def test_health_is_open(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["uptime_s"], (int, float))


@pytest.mark.parametrize(
    "path",
    [
        "/api/version",
        "/api/capabilities",
        "/api/project",
        "/api/catalog/subjects",
        "/api/catalog/simulations?subject=001",
        "/api/system",
    ],
)
def test_protected_routes_401_without_token(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 401
    assert r.json() == {"detail": "Unauthorized"}


def test_bearer_auth(client: TestClient) -> None:
    assert client.get("/api/version", headers=BEARER).status_code == 200
    bad = client.get("/api/version", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    basic = client.get("/api/version", headers={"Authorization": f"Basic {TOKEN}"})
    assert basic.status_code == 401


def test_cookie_exchange_then_cookie_auth(settings: ServerSettings) -> None:
    client = TestClient(create_app(settings), base_url=BASE)
    r = client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    set_cookie = r.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie
    assert "secure" not in set_cookie.replace("samesite", "")
    # the cookie is a random session id, never the token itself
    session_id = client.cookies.get(COOKIE_NAME)
    assert session_id and session_id != TOKEN and TOKEN not in session_id
    assert len(session_id) >= 32
    assert session_id in client.app.state.sessions
    # the client keeps the cookie jar; subsequent calls need no header
    assert client.get("/api/version").status_code == 200
    assert client.get("/api/catalog/subjects").status_code == 200
    # a second exchange mints a different id
    client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    assert client.cookies.get(COOKIE_NAME) != session_id


def test_bad_token_exchange_401(client: TestClient) -> None:
    r = client.get("/auth/session?token=wrong", follow_redirects=False)
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


def test_wrong_cookie_value_401(settings: ServerSettings) -> None:
    client = TestClient(create_app(settings), base_url=BASE)
    client.cookies.set(COOKIE_NAME, "wrong")
    assert client.get("/api/version").status_code == 401
    # the raw token is not a valid cookie value either
    client.cookies.set(COOKIE_NAME, TOKEN)
    assert client.get("/api/version").status_code == 401


def test_logout_forgets_session_and_clears_cookie(settings: ServerSettings) -> None:
    client = TestClient(create_app(settings), base_url=BASE)
    client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    session_id = client.cookies.get(COOKIE_NAME)
    assert client.get("/api/version").status_code == 200
    r = client.post("/auth/logout", headers={"Origin": BASE})
    assert r.status_code == 204
    assert r.content == b""
    cleared = r.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in cleared and (
        "max-age=0" in cleared or "expires=" in cleared
    )
    assert session_id not in client.app.state.sessions
    # the old id is dead even if a client keeps sending it
    client.cookies.set(COOKIE_NAME, session_id)
    assert client.get("/api/version").status_code == 401
    assert client.post("/auth/logout").status_code == 401


def test_logout_requires_auth_and_accepts_bearer(settings: ServerSettings) -> None:
    client = TestClient(create_app(settings), base_url=BASE)
    assert client.post("/auth/logout").status_code == 401
    assert client.post("/auth/logout", headers=BEARER).status_code == 204


def test_cookie_auth_rejects_cross_site_mutations(settings: ServerSettings) -> None:
    """ra_14 finding #7: a cookie alone must not authorize a state-changing request unless it
    also proves it came from this app's own origin -- otherwise another same-site localhost
    page could ride the session cookie into a mutating call (SameSite=Strict does not stop a
    *different origin on the same site*, e.g. a different localhost port)."""
    client = TestClient(create_app(settings), base_url=BASE)
    client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    # Safe (GET) method: cookie alone is fine, no Origin needed.
    assert client.get("/api/version").status_code == 200
    # Mutating method, no Origin/Sec-Fetch-Site at all: rejected (can't prove same-origin).
    assert client.post("/auth/logout").status_code == 403
    # Mutating method, a foreign Origin: rejected.
    assert (
        client.post(
            "/auth/logout", headers={"Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    # Mutating method, this app's own origin: allowed.
    assert client.post("/auth/logout", headers={"Origin": BASE}).status_code == 204
    # A Bearer credential is exempt from the Origin check even with a foreign Origin.
    client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    assert (
        client.post(
            "/auth/logout", headers={**BEARER, "Origin": "http://evil.example"}
        ).status_code
        == 204
    )
    # Sec-Fetch-Site: same-origin is accepted in place of Origin.
    client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    assert (
        client.post(
            "/auth/logout", headers={"Sec-Fetch-Site": "same-origin"}
        ).status_code
        == 204
    )
    client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    assert (
        client.post(
            "/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )


def test_restart_forgets_sessions(settings: ServerSettings) -> None:
    first = TestClient(create_app(settings), base_url=BASE)
    first.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    session_id = first.cookies.get(COOKIE_NAME)
    assert first.get("/api/version").status_code == 200
    # "restart": a new app instance with the same token and project
    second = TestClient(create_app(settings), base_url=BASE)
    second.cookies.set(COOKIE_NAME, session_id)
    assert second.get("/api/version").status_code == 401
    assert second.get("/api/version", headers=BEARER).status_code == 200


def test_trusted_host_rejects_foreign_host(settings: ServerSettings) -> None:
    evil = TestClient(create_app(settings), base_url="http://evil.example")
    r = evil.get("/api/health")
    assert r.status_code == 400
    ok = TestClient(create_app(settings), base_url="http://localhost:9999")
    assert ok.get("/api/health").status_code == 200


def test_trusted_host_allow_hosts(project: Path) -> None:
    import socket

    from tit.server.app import allowed_hosts

    default = ServerSettings(project_dir=str(project), token=TOKEN)
    assert allowed_hosts(default) == ["127.0.0.1", "localhost"]
    own = socket.gethostname()
    if own and own not in ("localhost", "127.0.0.1"):
        # the machine's own hostname is no longer trusted by default
        me = TestClient(create_app(default), base_url=f"http://{own}")
        assert me.get("/api/health").status_code == 400
    extra = ServerSettings(
        project_dir=str(project), token=TOKEN, allow_hosts=("node01.hpc",)
    )
    assert allowed_hosts(extra) == ["127.0.0.1", "localhost", "node01.hpc"]
    node = TestClient(create_app(extra), base_url="http://node01.hpc:8765")
    assert node.get("/api/health").status_code == 200
    other = TestClient(create_app(extra), base_url="http://node02.hpc:8765")
    assert other.get("/api/health").status_code == 400


# --------------------------------------------------------------------------
# websocket
# --------------------------------------------------------------------------


def test_ws_system_streams_snapshot(client: TestClient) -> None:
    with client.websocket_connect(f"{WS}?token={TOKEN}") as ws:
        msg = json.loads(ws.receive_text())
    for key in ("ts", "cpu_percent", "cpu_count", "mem", "disk", "processes"):
        assert key in msg
    assert set(msg["mem"]) == {"total", "available", "used", "percent"}
    assert set(msg["disk"]) == {"total", "free", "percent"}


def test_ws_accepts_cookie(settings: ServerSettings) -> None:
    client = TestClient(create_app(settings), base_url=BASE)
    client.get(f"/auth/session?token={TOKEN}", follow_redirects=False)
    with client.websocket_connect(WS) as ws:
        assert "ts" in json.loads(ws.receive_text())


def test_ws_rejects_missing_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS):
            pass
    assert exc.value.code == 4401


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "https://127.0.0.1:8765",  # scheme must match the connection (ws → http)
        "http://127.0.0.1.evil",
        "http://127.0.0.1:8766",  # any other local port is a different origin
        "http://localhost:8765",  # Host header is 127.0.0.1:8765, not localhost
        "http://localhost:5173",  # Vite dev server: only via --dev-origin
        "null",
        "",
    ],
)
def test_ws_rejects_foreign_origin(client: TestClient, origin: str) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{WS}?token={TOKEN}", headers={"Origin": origin}
        ):
            pass
    assert exc.value.code == 4403


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8765", "HTTP://127.0.0.1:8765"])
def test_ws_accepts_same_origin(client: TestClient, origin: str) -> None:
    with client.websocket_connect(
        f"{WS}?token={TOKEN}", headers={"Origin": origin}
    ) as ws:
        assert "ts" in json.loads(ws.receive_text())


def test_ws_dev_origin_allowlist(project: Path) -> None:
    settings = ServerSettings(
        project_dir=str(project), token=TOKEN, dev_origins=("http://localhost:5173",)
    )
    client = TestClient(create_app(settings), base_url=BASE)
    with client.websocket_connect(
        f"{WS}?token={TOKEN}", headers={"Origin": "http://localhost:5173"}
    ) as ws:
        assert "ts" in json.loads(ws.receive_text())
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{WS}?token={TOKEN}", headers={"Origin": "http://localhost:5174"}
        ):
            pass
    assert exc.value.code == 4403


def test_origin_allowed_policy() -> None:
    from tit.server.auth import origin_allowed

    host = "127.0.0.1:8765"
    assert origin_allowed(None, host)
    assert origin_allowed("http://127.0.0.1:8765", host)
    assert origin_allowed("http://127.0.0.1:8765", "127.0.0.1:8765")
    assert not origin_allowed("http://127.0.0.1:8765", None)
    assert not origin_allowed("http://127.0.0.1:8765", "")
    assert not origin_allowed("http://127.0.0.1:9999", host)
    assert not origin_allowed("http://localhost:8765", host)
    assert not origin_allowed("https://127.0.0.1:8765", host)
    assert origin_allowed("https://127.0.0.1:8765", host, secure=True)
    assert not origin_allowed("http://127.0.0.1:8765", host, secure=True)
    assert not origin_allowed("file://", host)
    assert not origin_allowed("null", host)
    dev = ("http://127.0.0.1:5173",)
    assert origin_allowed("http://127.0.0.1:5173", host, dev)
    assert not origin_allowed("http://127.0.0.1:5174", host, dev)


def test_ws_snapshot_failure_closes_1011(
    settings: ServerSettings, monkeypatch, caplog
) -> None:
    import tit.server.ws as ws_module

    def boom():
        raise RuntimeError("psutil exploded")

    monkeypatch.setattr(ws_module, "snapshot", boom)
    client = TestClient(create_app(settings), base_url=BASE)
    # the "tit" logger does not propagate: attach caplog's handler directly
    ws_module.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="tit.server.ws"):
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(f"{WS}?token={TOKEN}") as ws:
                    ws.receive_text()
    finally:
        ws_module.logger.removeHandler(caplog.handler)
    assert exc.value.code == 1011
    assert any("snapshot failed" in rec.message for rec in caplog.records)
    assert any("psutil exploded" in (rec.exc_text or "") for rec in caplog.records)


# --------------------------------------------------------------------------
# payloads
# --------------------------------------------------------------------------


def test_version_shape(client: TestClient) -> None:
    import hashlib

    import tit
    from tit.server.routes.schema import SCHEMA_PATH

    body = client.get("/api/version", headers=BEARER).json()
    assert body["tit_version"] == tit.__version__
    assert body["server_api"] == "v0"
    # ra_13 finding #3h: sha256 of contracts/schema.json's bytes (empty only if the file is
    # missing, e.g. a fresh checkout before dev/build_schema.py has ever run).
    assert body["schema_hash"] == hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
    assert len(body["schema_hash"]) == 64
    assert body["python"].count(".") == 2
    assert "simnibs" in body


def test_version_schema_hash_empty_when_schema_json_missing(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    from tit.server.routes import version as version_module

    monkeypatch.setattr(version_module, "SCHEMA_PATH", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(version_module, "_schema_hash_cache", None)
    body = client.get("/api/version", headers=BEARER).json()
    assert body["schema_hash"] == ""


def test_version_schema_hash_changes_when_schema_json_changes(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    import hashlib

    from tit.server.routes import version as version_module

    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"a": 1}')
    monkeypatch.setattr(version_module, "SCHEMA_PATH", schema_file)
    monkeypatch.setattr(version_module, "_schema_hash_cache", None)
    first = client.get("/api/version", headers=BEARER).json()["schema_hash"]

    # Same mtime-cache mechanism as routes/schema.py's own _load_schema(): edit-and-rewrite
    # (not just new bytes) must be picked up without a server restart.
    schema_file.write_text('{"a": 2}')
    second = client.get("/api/version", headers=BEARER).json()["schema_hash"]
    assert first != second
    assert second == hashlib.sha256(schema_file.read_bytes()).hexdigest()


def test_capabilities_shape(client: TestClient) -> None:
    body = client.get("/api/capabilities", headers=BEARER).json()
    # D3 (docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)): x11_display/freeview/gmsh/freesurfer are gone
    # from this runtime; `tetravox_embed` and `fastsurfer` are what replaced them. VE reversed V4's
    # brief removal of `tetravox_embed`: the viewer is served by this server, at /tetravox/, from a
    # bundle in this image -- which makes it exactly the kind of thing a capability describes.
    booleans = {"docker_socket", "bpy", "jupyter", "fastsurfer"}
    assert set(body) == booleans | {"tetravox_embed"}
    assert all(isinstance(body[k], bool) for k in booleans)
    # An object, not a boolean: a host asks "can this embed do markers", never "is it available".
    assert set(body["tetravox_embed"]) >= {"available", "supported", "features", "compatible"}
    assert set(body["tetravox_embed"]["supported"]) == {"min", "max"}


def test_project_shape(client: TestClient, project: Path, monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_PROJECT_DIR", raising=False)
    # With the variable unset the route asks this server's own container for the mapping
    # (tit/server/host_path.py). Pin "there is no container" so the assertion below is about
    # the response shape and not about where the suite happens to be running -- the resolver's
    # own behaviour is covered by tests/test_server_host_path.py.
    from tit.server import host_path as host_path_mod

    host_path_mod.clear_cache()
    monkeypatch.setattr(host_path_mod, "own_container_id", lambda: None)
    body = client.get("/api/project", headers=BEARER).json()
    assert body == {
        "container_path": str(project),
        "host_path": None,
        "name": project.name,
    }
    monkeypatch.setenv("LOCAL_PROJECT_DIR", "/Users/x/proj")
    assert client.get("/api/project", headers=BEARER).json()["host_path"] == (
        "/Users/x/proj"
    )


def test_catalog_subjects(client: TestClient) -> None:
    body = client.get("/api/catalog/subjects", headers=BEARER).json()
    assert body == {
        "subjects": [
            {
                "id": "001",
                "has_raw": True,
                "has_fastsurfer": False,
                "has_freesurfer": True,
                "has_m2m": True,
                "n_simulations": 2,
            },
            {
                "id": "002",
                "has_raw": True,
                "has_fastsurfer": False,
                "has_freesurfer": False,
                "has_m2m": False,
                "n_simulations": 0,
            },
        ]
    }


def test_catalog_simulations(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    body = client.get(
        "/api/catalog/simulations", params={"subject": "001"}, headers=BEARER
    ).json()
    # v1 enriches every item with SimulationDetail keys; the v0 keys stay exact.
    v0_keys = ("name", "path", "has_ti", "has_mti")
    body = {"simulations": [{k: it[k] for k in v0_keys} for it in body["simulations"]]}
    assert body == {
        "simulations": [
            {
                "name": "simA",
                "path": pm.simulation("001", "simA"),
                "has_ti": True,
                "has_mti": False,
            },
            {
                "name": "simB",
                "path": pm.simulation("001", "simB"),
                "has_ti": True,
                "has_mti": True,
            },
        ]
    }
    empty = client.get(
        "/api/catalog/simulations", params={"subject": "002"}, headers=BEARER
    ).json()
    assert empty == {"simulations": []}


def test_catalog_unknown_subject_404(client: TestClient) -> None:
    r = client.get(
        "/api/catalog/simulations", params={"subject": "nope"}, headers=BEARER
    )
    assert r.status_code == 404
    r = client.get(
        "/api/catalog/simulations", params={"subject": "003"}, headers=BEARER
    )
    assert r.status_code == 404  # SimNIBS folder without m2m is not a subject
    assert client.get("/api/catalog/simulations", headers=BEARER).status_code == 422


def test_system_snapshot_shape(client: TestClient) -> None:
    body = client.get("/api/system", headers=BEARER).json()
    assert set(body) == {"ts", "cpu_percent", "cpu_count", "mem", "disk", "processes"}
    assert isinstance(body["cpu_count"], int)
    for proc in body["processes"]:
        assert set(proc) >= {"pid", "name", "cpu_percent", "rss", "started"}
        assert len(proc["cmdline"]) <= 200


def test_process_filter_matches_expected_tools() -> None:
    """The keyword filter recognises the external tools TI-Toolbox actually spawns."""
    from tit.server.routes.system import RELEVANT_KEYWORDS, is_relevant_process

    # Every keyword the filter carries must be matched by is_relevant_process itself --
    # the constant and the predicate cannot drift apart.
    for keyword in RELEVANT_KEYWORDS:
        assert is_relevant_process(keyword, "")

    assert is_relevant_process("simnibs_python", "-m tit.sim cfg.json")
    assert is_relevant_process("", "/opt/fastsurfer/run_fastsurfer.sh --sid x")
    assert is_relevant_process("mri_convert", "")
    assert not is_relevant_process("bash", "-lc sleep 1")


def test_relevant_processes_excludes_own_pid(monkeypatch) -> None:
    import psutil

    from tit.server.routes import system as system_module

    class _Mem:
        rss = 1024

    class _Proc:
        def __init__(self, pid: int, name: str) -> None:
            self.info = {
                "pid": pid,
                "name": name,
                "cmdline": [name, "-m", "tit.sim"],
                "cpu_percent": 1.0,
                "create_time": 0.0,
                "memory_info": _Mem(),
            }

    fake = [_Proc(os.getpid(), "simnibs_python"), _Proc(424242, "simnibs_python")]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter(fake))
    pids = [p.pid for p in system_module.relevant_processes()]
    assert pids == [424242]


# --------------------------------------------------------------------------
# static / status page
# --------------------------------------------------------------------------


def test_status_page_when_no_bundle(client: TestClient, project: Path) -> None:
    import tit

    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"] == CSP_HEADER
    assert "TI-Toolbox job server is running" in r.text
    assert "no UI bundle" in r.text
    # unauthenticated: discloses nothing about the runtime
    assert str(project) not in r.text
    assert "docker_socket" not in r.text
    assert tit.__version__ not in r.text
    assert "SimNIBS" not in r.text


def test_status_page_when_bundle_dir_missing(project: Path) -> None:
    settings = ServerSettings(
        project_dir=str(project), token=TOKEN, static_dir=str(project / "nope")
    )
    client = TestClient(create_app(settings), base_url=BASE)
    r = client.get("/")
    assert "no UI bundle" in r.text
    assert str(project / "nope") not in r.text


def test_csp_header_is_exactly_the_todo_string() -> None:
    """The TODO string plus the docs website, the app's one outside origin.

    Help -> Docs frames https://idossha.github.io/TI-Toolbox/ (and probes it
    with a ``no-cors`` fetch first), so that origin -- and only that one --
    appears in ``frame-src``/``connect-src``.
    """
    assert CSP_HEADER == (
        "default-src 'self'; connect-src 'self' https://idossha.github.io; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "worker-src 'self' blob:; frame-src 'self' https://idossha.github.io; object-src 'none'"
    )


def test_csp_no_longer_grants_wasm_eval_in_the_app_origin() -> None:
    """V4: nothing in this origin instantiates WASM any more.

    D3 moved the in-app viewer into the embed's own iframe and CSP; V4
    (``docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)``) removed the embed
    outright. Neither ``eval`` nor WASM instantiation is granted anywhere this
    server serves.
    """
    assert "wasm-unsafe-eval" not in CSP_HEADER
    assert "unsafe-eval" not in CSP_HEADER
    assert "script-src 'self';" in CSP_HEADER


def test_static_bundle_spa_fallback_and_jail(project: Path) -> None:
    bundle = project / "bundle"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "index.html").write_text("<html><body>SPA</body></html>")
    (bundle / "assets" / "app.js").write_text("console.log(1)")
    (project / "secret.txt").write_text("nope")
    settings = ServerSettings(
        project_dir=str(project), token=TOKEN, static_dir=str(bundle)
    )
    client = TestClient(create_app(settings), base_url=BASE)
    r = client.get("/")
    assert r.status_code == 200 and "SPA" in r.text
    assert r.headers["content-security-policy"] == CSP_HEADER
    r = client.get("/assets/app.js")
    assert r.status_code == 200 and "console.log" in r.text
    assert "content-security-policy" not in r.headers
    # client-side route → index.html
    assert "SPA" in client.get("/jobs/42").text
    # traversal attempts never leave the bundle
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        r = client.get(path)
        assert "nope" not in r.text, path
    # unknown API paths are 404, not the SPA
    assert client.get("/api/nope", headers=BEARER).status_code == 404
    assert client.get("/api/nope").status_code == 404


def test_spa_head_matches_get_headers_with_no_body(project: Path) -> None:
    # Same APIRoute HEAD-inference gap as /tetravox/ (R2 item 7, FX3 item 1): `curl -I /` 405'd
    # before HEAD was registered explicitly on the SPA catch-all too.
    bundle = project / "bundle"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "index.html").write_text("<html><body>SPA</body></html>")
    (bundle / "assets" / "app.js").write_text("console.log(1)")
    settings = ServerSettings(
        project_dir=str(project), token=TOKEN, static_dir=str(bundle)
    )
    client = TestClient(create_app(settings), base_url=BASE)
    for path in ("/", "/jobs/42", "/assets/app.js"):
        get_resp = client.get(path)
        head_resp = client.head(path)
        assert head_resp.status_code == get_resp.status_code, path
        assert head_resp.content == b"", path
        assert (
            head_resp.headers["content-length"] == get_resp.headers["content-length"]
        ), path

    # And the no-bundle status page, which is served by the same catch-all.
    no_bundle_settings = ServerSettings(
        project_dir=str(project), token=TOKEN, static_dir=str(project / "missing")
    )
    no_bundle_client = TestClient(create_app(no_bundle_settings), base_url=BASE)
    get_resp = no_bundle_client.get("/")
    head_resp = no_bundle_client.head("/")
    assert head_resp.status_code == get_resp.status_code == 200
    assert head_resp.content == b""


def test_bundle_picked_up_without_restart(project: Path) -> None:
    bundle = project / "later"
    settings = ServerSettings(
        project_dir=str(project), token=TOKEN, static_dir=str(bundle)
    )
    client = TestClient(create_app(settings), base_url=BASE)
    assert "no UI bundle" in client.get("/").text
    bundle.mkdir()
    (bundle / "index.html").write_text("<html>built later</html>")
    assert "built later" in client.get("/").text


# --------------------------------------------------------------------------
# no token leaks; openapi
# --------------------------------------------------------------------------


def test_token_never_in_response_bodies(settings: ServerSettings) -> None:
    client = TestClient(create_app(settings), base_url=BASE)
    paths = [
        "/",
        "/api/health",
        "/api/version",
        "/api/capabilities",
        "/api/project",
        "/api/catalog/subjects",
        "/api/catalog/simulations?subject=001",
        "/api/catalog/simulations?subject=zzz",
        "/api/system",
        "/api/nope",
        f"/auth/session?token={TOKEN}",
        "/auth/session?token=bad",
    ]
    for path in paths:
        for headers in ({}, BEARER):
            r = client.get(path, headers=headers, follow_redirects=False)
            assert TOKEN not in r.text, (path, headers)
    with client.websocket_connect(f"{WS}?token={TOKEN}") as ws:
        assert TOKEN not in ws.receive_text()


def test_openapi_covers_v0_contract(settings: ServerSettings) -> None:
    yaml = pytest.importorskip("yaml")
    import importlib.util

    spec_path = Path(__file__).resolve().parents[1] / "dev" / "contracts_check.py"
    spec = importlib.util.spec_from_file_location("contracts_check", spec_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = yaml.safe_load(module.DEFAULT_CONTRACT.read_text())
    dump = create_app(settings).openapi()
    missing, _warnings = module.check(contract, dump)
    assert missing == []
    assert TOKEN not in json.dumps(dump)


def test_access_log_filter_masks_token(caplog) -> None:
    from tit.server.access_log import TokenMaskFilter, mask_token

    assert mask_token("/auth/session?token=abc123&x=1") == "/auth/session?token=***&x=1"
    assert mask_token("/ws/system?token=abc123") == "/ws/system?token=***"
    assert mask_token("/api/health") == "/api/health"

    flt = TokenMaskFilter()
    # uvicorn.access: msg with %s args (client, method, path, http version, status)
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", f"/auth/session?token={TOKEN}", "1.1", 303),
        None,
    )
    assert flt.filter(record) is True
    assert TOKEN not in record.getMessage()
    assert "token=***" in record.getMessage()
    # uvicorn.error WebSocket handshake line
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:1", f"/ws/system?token={TOKEN}"),
        None,
    )
    flt.filter(record)
    assert TOKEN not in record.getMessage()
    # pre-formatted message, no args
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, f"GET /auth/session?token={TOKEN}", None, None
    )
    flt.filter(record)
    assert record.getMessage() == "GET /auth/session?token=***"

    # installed on a logger, end to end through caplog
    log = logging.getLogger("uvicorn.access.test")
    log.addFilter(flt)
    log.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="uvicorn.access.test"):
            log.info(
                '%s - "GET %s HTTP/1.1" 303',
                "127.0.0.1",
                f"/auth/session?token={TOKEN}",
            )
    finally:
        log.removeFilter(flt)
        log.removeHandler(caplog.handler)
    assert TOKEN not in caplog.text
    assert "token=***" in caplog.text


def test_uvicorn_log_config_installs_mask_filter() -> None:
    from tit.server.__main__ import _uvicorn_log_config

    config = _uvicorn_log_config()
    assert (
        config["filters"]["mask_token"]["()"] == "tit.server.access_log.TokenMaskFilter"
    )
    for name in ("default", "access"):
        assert config["handlers"][name]["filters"] == ["mask_token"]
    assert config["handlers"]["access"]["stream"] == "ext://sys.stderr"


def test_reload_passes_settings_via_0600_file(project: Path, monkeypatch) -> None:
    import uvicorn

    from tit.server import __main__ as cli
    from tit.server.settings import ENV_SETTINGS_FILE, ENV_TOKEN

    monkeypatch.setenv(ENV_TOKEN, TOKEN)
    seen: dict[str, object] = {}

    def fake_run(target, **kwargs):
        seen["target"] = target
        seen["kwargs"] = kwargs
        seen["token_in_env"] = ENV_TOKEN in os.environ
        path = os.environ[ENV_SETTINGS_FILE]
        seen["mode"] = stat.S_IMODE(os.stat(path).st_mode)
        seen["file"] = path
        # what the reloader's child does
        app = cli.app_factory()
        seen["settings"] = app.state.settings

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert cli.main(["--project", str(project), "--reload", "--port", "8799"]) == 0
    assert seen["target"] == "tit.server.__main__:app_factory"
    assert seen["kwargs"]["reload"] is True and seen["kwargs"]["factory"] is True
    assert seen["token_in_env"] is False
    assert seen["mode"] == 0o600
    loaded = seen["settings"]
    assert loaded.token == TOKEN and loaded.port == 8799
    assert loaded.project_dir == str(project) and loaded.dev_reload is True
    # cleaned up after uvicorn returns
    assert not os.path.exists(seen["file"])
    assert ENV_SETTINGS_FILE not in os.environ


def test_reload_dir_scopes_the_watcher(project: Path, monkeypatch, caplog) -> None:
    """``--reload-dir`` reaches uvicorn, and a missing directory is dropped, not fatal.

    Without it uvicorn watches the working directory, which in the dev container is
    the bind-mounted repository -- ``desktop/node_modules`` included -- and watchfiles
    walking that makes the container unusable.  ``entrypoint.ti-toolbox.sh`` therefore
    passes ``--reload-dir /ti-toolbox/tit`` whenever ``TIT_SERVER_RELOAD=1``; a
    container started with that flag but *without* the worktree mounted would then hand
    uvicorn a path that does not exist, so the resolver drops it and says so.
    """
    import uvicorn

    from tit.server import __main__ as cli
    from tit.server.settings import ENV_TOKEN

    monkeypatch.setenv(ENV_TOKEN, TOKEN)
    watched = project / "tit"
    watched.mkdir()
    seen: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: seen.update(kw))

    assert (
        cli.main(
            [
                "--project",
                str(project),
                "--reload",
                "--reload-dir",
                str(watched),
                "--reload-dir",
                str(project / "does-not-exist"),
            ]
        )
        == 0
    )
    assert seen["reload_dirs"] == [str(watched)]

    seen.clear()
    assert cli.main(["--project", str(project), "--reload"]) == 0
    # No --reload-dir at all must stay uvicorn's own default, not an empty watch list
    # (an empty list would be read as "watch nothing" and the reloader would never fire).
    assert seen["reload_dirs"] is None

    assert cli.resolve_reload_dirs(None) == []
    # `tit`'s logger does not propagate to the root, so caplog only sees it once its
    # handler is attached directly (same idiom as the token-masking test above).
    log = logging.getLogger("tit.server")
    log.addHandler(caplog.handler)
    try:
        assert cli.resolve_reload_dirs(["/no/such/dir"]) == []
    finally:
        log.removeHandler(caplog.handler)
    assert "/no/such/dir" in caplog.text


def test_settings_json_roundtrip_and_cli_lists(monkeypatch) -> None:
    from tit.server.settings import (
        ENV_ALLOW_HOSTS,
        ENV_DEV_ORIGINS,
        resolve_allow_hosts,
        resolve_dev_origins,
    )

    original = ServerSettings(
        project_dir="/p",
        token="t",
        dev_origins=("http://127.0.0.1:5173",),
        allow_hosts=("node01",),
    )
    assert ServerSettings.from_json(original.to_json()) == original

    monkeypatch.delenv(ENV_DEV_ORIGINS, raising=False)
    monkeypatch.delenv(ENV_ALLOW_HOSTS, raising=False)
    assert resolve_dev_origins(None) == ()
    assert resolve_allow_hosts(None) == ()
    monkeypatch.setenv(ENV_DEV_ORIGINS, "http://a:1, http://b:2 ,")
    monkeypatch.setenv(ENV_ALLOW_HOSTS, "h1,h2")
    assert resolve_dev_origins(["http://c:3", "http://a:1"]) == (
        "http://c:3",
        "http://a:1",
        "http://b:2",
    )
    assert resolve_allow_hosts(["h2", "h3"]) == ("h2", "h3", "h1")

    from tit.server.__main__ import build_parser

    args = build_parser().parse_args(
        [
            "--dev-origin",
            "http://x:1",
            "--dev-origin",
            "http://y:2",
            "--allow-host",
            "z",
        ]
    )
    assert args.dev_origin == ["http://x:1", "http://y:2"]
    assert args.allow_host == ["z"]


def test_contracts_check_reports_type_and_enum_mismatch() -> None:
    import importlib.util

    spec_path = Path(__file__).resolve().parents[1] / "dev" / "contracts_check.py"
    spec = importlib.util.spec_from_file_location("contracts_check_unit", spec_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def doc(status_type, simnibs, mode):
        return {
            "paths": {},
            "components": {
                "schemas": {
                    "V": {
                        "type": "object",
                        "required": ["status"],
                        "properties": {
                            "status": status_type,
                            "simnibs": simnibs,
                            "mode": mode,
                        },
                    }
                }
            },
        }

    contract = doc(
        {"type": "string", "enum": ["ok"]},
        {"type": ["string", "null"]},
        {"type": "string", "enum": ["a", "b"]},
    )
    good = doc(
        {"type": "string", "const": "ok"},
        {"anyOf": [{"type": "string"}, {"type": "null"}]},
        {"type": "string", "enum": ["b", "a"]},
    )
    good_missing, _good_warnings = module.check(contract, good)
    assert good_missing == []
    bad = doc(
        {"type": "integer"},
        {"type": "string"},
        {"type": "string", "enum": ["a"]},
    )
    problems, _warnings = module.check(contract, bad)
    assert any("schema V.status: type" in p for p in problems)
    assert any("schema V.status: enum" in p for p in problems)
    assert any("schema V.simnibs: type" in p for p in problems)
    assert any("schema V.mode: enum" in p for p in problems)


def test_settings_resolution(tmp_path: Path, monkeypatch) -> None:
    from tit.server.settings import (
        SettingsError,
        resolve_project_dir,
        resolve_token,
    )

    for var in ("TIT_PROJECT_DIR", "LOCAL_PROJECT_DIR", "PROJECT_DIR_NAME"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SettingsError):
        resolve_project_dir(None)
    assert resolve_project_dir(None, required=False) is None
    assert resolve_project_dir(str(tmp_path)) == str(tmp_path)
    with pytest.raises(SettingsError):
        resolve_project_dir(str(tmp_path / "missing"))
    monkeypatch.setenv("TIT_PROJECT_DIR", str(tmp_path))
    assert resolve_project_dir(None) == str(tmp_path)

    monkeypatch.delenv("TIT_SERVER_TOKEN", raising=False)
    assert resolve_token("abc") == ("abc", False)
    monkeypatch.setenv("TIT_SERVER_TOKEN", "from-env")
    assert resolve_token(None) == ("from-env", False)
    monkeypatch.delenv("TIT_SERVER_TOKEN")
    token, generated = resolve_token(None)
    assert generated and len(token) >= 32


def test_reload_settings_file_survives_a_removed_field(tmp_path, monkeypatch) -> None:
    """A settings file written by an older build must not take the reload child down.

    ``--reload`` writes the settings once and every reloaded worker re-reads that same file.
    When a field is removed from :class:`ServerSettings` mid-session the file on disk still
    carries it, and a strict ``cls(**data)`` raised ``TypeError`` on every reload -- the dev server
    stayed down naming a field nobody had edited.  That happened on 2026-09-06, twice in one day
    and in both directions, when ``tetravox_embed_dir`` was removed and then restored.  Unknown
    keys are dropped instead; the fields this build does declare are kept.

    The stale keys below are deliberately names no build has ever had.  Using a real removed field
    would make this test pass or fail on whether that field happens to be declared today, which is
    the one thing it is not about.
    """
    import json

    from tit.server.__main__ import settings_from_file
    from tit.server.settings import ENV_SETTINGS_FILE

    stale = json.loads(
        ServerSettings(project_dir="/p", token="t", port=9001, allow_hosts=("node01",)).to_json()
    )
    stale["a_field_this_build_never_had"] = "/opt/somewhere"
    stale["another_one"] = 17
    path = tmp_path / "tit-server-stale.json"
    path.write_text(json.dumps(stale))

    monkeypatch.setenv(ENV_SETTINGS_FILE, str(path))
    loaded = settings_from_file()
    assert loaded.project_dir == "/p"
    assert loaded.port == 9001
    assert loaded.allow_hosts == ("node01",)
    assert not hasattr(loaded, "a_field_this_build_never_had")
    assert not hasattr(loaded, "another_one")
