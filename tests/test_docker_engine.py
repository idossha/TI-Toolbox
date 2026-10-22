"""Tests for tit/jobs/docker_engine.py.

The module covers only what production calls: discovery, ``version``, ``list_containers``,
``stop_container`` and ``inspect_container`` (plus ``system_df``/``list_images``, which the System
route's own tests drive). Three layers:

1. ``discover()`` — pure.
2. Integration tests against ``_FakeEngineServer``, a real ``http.server`` bound to a real Unix
   socket (via ``address_family = socket.AF_UNIX``, the standard stdlib trick — no extra
   dependency), answering the endpoint subset the client uses with the fixture conventions of
   ``desktop/tests/e2e/fixtures/fake-engine-api.mjs`` (unknown container id -> HTTP 404).
   Containers are seeded straight into the fake daemon's table.
3. Connection-level error-classification tests using real, synthetic socket states (an absent
   path, a bound-but-not-listening socket, a mode-000 socket, a socket that never answers) — no
   live Docker daemon required.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import os
import socket
import socketserver
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tit.jobs.docker_engine import (  # noqa: E402
    DockerConnection,
    DockerEngineClient,
    DockerEngineError,
    _api_error_from_body,
    discover,
)


# ---------------------------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------------------------


class TestDiscover:
    def test_default_is_well_known_dood_mount(self):
        assert discover({}) == DockerConnection(socket_path="/var/run/docker.sock")

    def test_docker_host_unix_scheme(self):
        assert discover({"DOCKER_HOST": "unix:///tmp/custom.sock"}) == DockerConnection(socket_path="/tmp/custom.sock")

    def test_non_unix_docker_host_falls_back_to_default(self):
        # tcp:// isn't driven by this module (module docstring) — falling back rather than
        # crashing is deliberate: a caller inside the tit container never legitimately sets a
        # tcp:// DOCKER_HOST (the DooD mount is always a Unix socket), so this is a defensive
        # default, not a real supported configuration.
        assert discover({"DOCKER_HOST": "tcp://1.2.3.4:2375"}) == DockerConnection(socket_path="/var/run/docker.sock")


# ---------------------------------------------------------------------------------------------
# Fake Engine API server — a real http.server.HTTPServer bound to a real AF_UNIX socket.
# ---------------------------------------------------------------------------------------------


class _FakeEngineServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    address_family = socket.AF_UNIX
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, socket_path: str, handler_cls: type) -> None:
        self.containers: dict[str, dict] = {}
        self.lock = threading.Lock()
        super().__init__(socket_path, handler_cls)  # type: ignore[arg-type]

    def seed(self, labels: dict[str, str], *, running: bool = True) -> str:
        """Put one container in the daemon's table, as `docker run` would have."""
        container_id = uuid.uuid4().hex
        with self.lock:
            self.containers[container_id] = {
                "id": container_id,
                "image": "fixture/ok",
                "labels": labels,
                "running": running,
                "exit_code": None if running else 0,
            }
        return container_id


class _FakeEngineHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass

    def _write_json(self, status: int, body) -> None:
        payload = b"" if body is None else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/v") and (slash := path.find("/", 1)) != -1:
            path = path[slash:]  # strip an optional /vX.YY version prefix, same as the real daemon
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.server.requests.append((method, path, query, parsed.path))

        if method == "GET" and path == "/version":
            return self._write_json(200, {"Version": "29.7.2-fake", "ApiVersion": "1.51", "MinAPIVersion": "1.24", "Os": "linux", "Arch": "amd64"})

        if method == "GET" and path == "/containers/json":
            # `filters` is the Engine's JSON-encoded filter map; only `label` is supported here,
            # which is all `tit/jobs/runner.py::stop_docker_siblings_via_engine` ever sends.
            wanted = []
            if query.get("filters"):
                wanted = json.loads(query["filters"]).get("label", [])
            show_all = query.get("all") in ("1", "true", "True")
            out = []
            with self.server.lock:
                for container in self.server.containers.values():
                    if not show_all and not container["running"]:
                        continue
                    labels = container["labels"]
                    if all(labels.get(w.split("=", 1)[0]) == w.split("=", 1)[1] for w in wanted):
                        out.append({"Id": container["id"], "Labels": labels, "State": "running" if container["running"] else "exited"})
            return self._write_json(200, out)

        parts = path.split("/")
        if len(parts) >= 3 and parts[1] == "containers":
            container_id = parts[2]
            sub = "/" + "/".join(parts[3:]) if len(parts) > 3 else ""
            with self.server.lock:
                container = self.server.containers.get(container_id)
            if container is None:
                return self._write_json(404, {"message": f"No such container: {container_id}"})
            if method == "POST" and sub == "/stop":
                with self.server.lock:
                    container["running"] = False
                    container["exit_code"] = 0
                return self._write_json(204, None)
            if method == "GET" and sub == "/json":
                with self.server.lock:
                    return self._write_json(
                        200,
                        {
                            "Id": container["id"],
                            "State": {"Status": "running" if container["running"] else "exited", "Running": container["running"], "ExitCode": container["exit_code"] or 0},
                            "Config": {"Image": container["image"], "Labels": container["labels"]},
                        },
                    )

        return self._write_json(404, {"message": f"fake-engine-server: unhandled route {method} {path}"})


@pytest.fixture
def engine():
    socket_dir = tempfile.mkdtemp(prefix="tit-fake-engine-")
    socket_path = os.path.join(socket_dir, "engine.sock")
    server = _FakeEngineServer(socket_path, _FakeEngineHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def client(engine):
    return DockerEngineClient(DockerConnection(socket_path=engine.server_address), timeout_s=5.0)


def jobs_runner_docker_engine():
    """The module object ``stop_docker_siblings_via_engine`` imports lazily (patched by name)."""
    import tit.jobs.docker_engine as mod

    return mod


# ---------------------------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------------------------


class TestListContainersAndSiblingStop:
    """``list_containers`` + ``tit/jobs/runner.py::stop_docker_siblings_via_engine`` -- the
    Engine-API path startup reconciliation uses to stop a stranded job's sibling containers."""

    def test_list_containers_filters_by_job_label(self, client, engine):
        mine = engine.seed({"tit.job_id": "job-a"})
        engine.seed({"tit.job_id": "job-b"})
        found = client.list_containers(filters={"label": ["tit.job_id=job-a"]})
        assert [c["Id"] for c in found] == [mine]

    def test_list_containers_hides_stopped_ones_unless_asked(self, client, engine):
        running = engine.seed({"tit.job_id": "job-a"})
        stopped = engine.seed({"tit.job_id": "job-a"}, running=False)
        assert [c["Id"] for c in client.list_containers()] == [running]
        assert {c["Id"] for c in client.list_containers(all_containers=True)} == {running, stopped}

    def test_stop_docker_siblings_via_engine_stops_only_this_jobs_containers(self, client, engine, monkeypatch):
        import tit.jobs.runner as jobs_runner

        mine = engine.seed({"tit.job_id": "job-a"})
        theirs = engine.seed({"tit.job_id": "job-b"})
        monkeypatch.setattr(
            jobs_runner_docker_engine(),
            "discover",
            lambda env=None: DockerConnection(socket_path=engine.server_address),
        )
        stopped = asyncio.run(jobs_runner.stop_docker_siblings_via_engine("job-a", timeout_s=5.0))
        assert stopped == 1
        assert client.inspect_container(mine)["State"]["Running"] is False
        assert client.inspect_container(theirs)["State"]["Running"] is True

    def test_unreachable_daemon_is_a_silent_no_op(self, tmp_path, monkeypatch):
        import tit.jobs.runner as jobs_runner

        monkeypatch.setattr(
            jobs_runner_docker_engine(),
            "discover",
            lambda env=None: DockerConnection(socket_path=str(tmp_path / "nope.sock")),
        )
        assert asyncio.run(jobs_runner.stop_docker_siblings_via_engine("job-a", timeout_s=1.0)) == 0


class TestDockerEngineClient:
    def test_version_negotiates_api_version_for_later_calls(self, client, engine):
        v = client.version()
        assert v["ApiVersion"] == "1.51"
        assert v["Os"] == "linux"
        client.list_containers()
        # /version is always unversioned; every later call carries the negotiated prefix.
        assert [raw for *_, raw in engine.requests] == ["/version", "/v1.51/containers/json"]

    def test_stop_container_passes_grace_and_stops_it(self, client, engine):
        container_id = engine.seed({"fixture.execDelayMs": "999999"})
        client.stop_container(container_id, grace_seconds=7)
        method, path, query, _ = engine.requests[-1]
        assert (method, path, query.get("t")) == ("POST", f"/containers/{container_id}/stop", "7")
        inspected = client.inspect_container(container_id)
        assert inspected["State"]["Running"] is False
        assert inspected["State"]["ExitCode"] == 0

    def test_inspect_unknown_container_is_not_found(self, client):
        with pytest.raises(DockerEngineError) as excinfo:
            client.inspect_container("0123456789ab")
        assert excinfo.value.kind == "not-found"
        assert excinfo.value.status_code == 404
        assert "No such container" in str(excinfo.value)


class TestApiErrorFromBody:
    @pytest.mark.parametrize(
        ("status", "kind"),
        [(400, "bad-request"), (404, "not-found"), (409, "conflict"), (500, "server-error"), (503, "server-error"), (418, "unknown")],
    )
    def test_status_codes_map_to_the_engine_ts_kinds(self, status, kind):
        error = _api_error_from_body(status, b'{"message": "daemon says no"}')
        assert (error.kind, error.status_code, str(error)) == (kind, status, "daemon says no")

    def test_a_body_that_is_not_json_is_the_message(self):
        assert str(_api_error_from_body(500, b"plain text failure")) == "plain text failure"
        assert str(_api_error_from_body(502, b"")) == "HTTP 502"


# ---------------------------------------------------------------------------------------------
# Connection-level error classification (no live daemon needed — synthetic socket states).
# ---------------------------------------------------------------------------------------------


class TestConnectionErrorClassification:
    def test_absent_socket_path_is_not_installed(self):
        dead = DockerEngineClient(DockerConnection(socket_path="/tmp/tit-does-not-exist-9f3a.sock"), timeout_s=2.0)
        with pytest.raises(DockerEngineError) as excinfo:
            dead.version()
        assert excinfo.value.kind == "not-installed"

    def test_bound_but_not_listening_socket_is_not_running(self):
        socket_dir = tempfile.mkdtemp(prefix="tit-fake-engine-notlistening-")
        socket_path = os.path.join(socket_dir, "engine.sock")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_path)  # bound, but never listen()/accept() — connect() must be refused
        try:
            dead = DockerEngineClient(DockerConnection(socket_path=socket_path), timeout_s=2.0)
            with pytest.raises(DockerEngineError) as excinfo:
                dead.version()
            assert excinfo.value.kind == "not-running"
        finally:
            sock.close()

    def test_mode_000_socket_is_socket_permission(self):
        socket_dir = tempfile.mkdtemp(prefix="tit-fake-engine-noperm-")
        socket_path = os.path.join(socket_dir, "engine.sock")
        server = _FakeEngineServer(socket_path, _FakeEngineHandler)
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        os.chmod(socket_path, 0o000)
        try:
            if os.geteuid() == 0:
                pytest.skip("root bypasses filesystem permission checks (CAP_DAC_OVERRIDE)")
            dead = DockerEngineClient(DockerConnection(socket_path=socket_path), timeout_s=2.0)
            with pytest.raises(DockerEngineError) as excinfo:
                dead.version()
            assert excinfo.value.kind == "socket-permission"
        finally:
            os.chmod(socket_path, 0o777)
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class TestHungDaemonIsBounded:
    """A wedged daemon — a socket that accepts the connection and then never answers a byte —
    is the state that hung every job cancellation on a developer machine. A call made with a
    short timeout must give up rather than block."""

    def test_short_timeout_call_raises_rather_than_hanging(self):
        timeout_s = 1.0
        socket_dir = tempfile.mkdtemp(prefix="tit-fake-engine-hung-")
        socket_path = os.path.join(socket_dir, "engine.sock")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_path)
        sock.listen(8)  # accepts (well, backlogs) connections, but never reads or replies
        try:
            client = DockerEngineClient(DockerConnection(socket_path=socket_path), timeout_s=timeout_s)
            started = time.monotonic()
            with pytest.raises((DockerEngineError, OSError)):
                client.version()
            assert time.monotonic() - started <= timeout_s + 1.0
        finally:
            sock.close()
