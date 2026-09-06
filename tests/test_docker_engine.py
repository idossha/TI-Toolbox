"""Tests for tit/jobs/docker_engine.py.

Two layers, mirroring desktop/tests/unit/docker-engine-*.test.ts:

1. Pure decoder tests (``LogFrameDecoder``/``NdjsonDecoder``) — chunk-split edge cases, no socket.
2. Integration tests against ``_FakeEngineServer``, a real ``http.server`` bound to a real Unix
   socket (via ``address_family = socket.AF_UNIX``, the standard stdlib trick — no extra
   dependency), answering the same endpoint subset as
   ``desktop/tests/e2e/fixtures/fake-engine-api.mjs``, including its exact fixture conventions
   (``Image: "fixture/409-on-create"`` -> HTTP 409, ``"fixture/500-on-create"`` -> HTTP 500,
   unknown container id -> HTTP 404, ``Labels["fixture.exitCode"]``/``["fixture.execDelayMs"]``)
   so the two test suites document the same contract in both languages.
3. Connection-level error-classification tests using real, synthetic socket states (an absent
   path, a bound-but-not-listening socket, a mode-000 socket) — no live Docker daemon required.
"""

from __future__ import annotations

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
    ContainerCreateSpec,
    DockerConnection,
    DockerEngineClient,
    DockerEngineError,
    LogFrameDecoder,
    NdjsonDecoder,
    discover,
    run_job_container,
)


# ---------------------------------------------------------------------------------------------
# Pure decoders
# ---------------------------------------------------------------------------------------------


def _raw_frame(stream_type: int, text: str) -> bytes:
    payload = text.encode("utf-8")
    header = bytes([stream_type, 0, 0, 0]) + len(payload).to_bytes(4, "big")
    return header + payload


class TestLogFrameDecoder:
    def test_single_whole_frame(self):
        decoder = LogFrameDecoder()
        frames = decoder.push(_raw_frame(1, "hello\n"))
        assert len(frames) == 1
        assert frames[0].stream == "stdout"
        assert frames[0].payload == b"hello\n"
        assert decoder.remainder() == b""

    def test_stdout_stderr_stdin_distinct(self):
        decoder = LogFrameDecoder()
        frames = decoder.push(_raw_frame(1, "out") + _raw_frame(2, "err") + _raw_frame(0, "in"))
        assert [f.stream for f in frames] == ["stdout", "stderr", "stdin"]
        assert [f.payload for f in frames] == [b"out", b"err", b"in"]

    def test_header_split_across_chunks(self):
        decoder = LogFrameDecoder()
        whole = _raw_frame(1, "split-header")
        assert decoder.push(whole[:3]) == []
        assert decoder.remainder() == whole[:3]
        frames = decoder.push(whole[3:])
        assert len(frames) == 1
        assert frames[0].payload == b"split-header"
        assert decoder.remainder() == b""

    def test_payload_split_across_three_chunks(self):
        decoder = LogFrameDecoder()
        whole = _raw_frame(2, "0123456789")
        assert decoder.push(whole[:8]) == []  # exactly the header
        assert decoder.push(whole[8:12]) == []  # 4 of 10 payload bytes
        frames = decoder.push(whole[12:])
        assert len(frames) == 1
        assert frames[0].stream == "stderr"
        assert frames[0].payload == b"0123456789"

    def test_back_to_back_frames_one_chunk(self):
        decoder = LogFrameDecoder()
        batch = _raw_frame(1, "a") + _raw_frame(1, "b") + _raw_frame(1, "c")
        frames = decoder.push(batch)
        assert [f.payload for f in frames] == [b"a", b"b", b"c"]

    def test_truncated_final_frame_stays_in_remainder(self):
        decoder = LogFrameDecoder()
        whole = _raw_frame(1, "truncated-tail")
        frames = decoder.push(whole[:-3])
        assert frames == []
        assert len(decoder.remainder()) == len(whole) - 3

    def test_zero_length_payload_frame(self):
        decoder = LogFrameDecoder()
        frames = decoder.push(_raw_frame(1, ""))
        assert len(frames) == 1
        assert frames[0].payload == b""


class TestNdjsonDecoder:
    def test_three_objects_one_chunk(self):
        decoder = NdjsonDecoder()
        objs = decoder.push(b'{"n":1}\n{"n":2}\n{"n":3}\n')
        assert objs == [{"n": 1}, {"n": 2}, {"n": 3}]
        assert decoder.has_carry() is False

    def test_partial_trailing_line_carried_forward(self):
        decoder = NdjsonDecoder()
        first = decoder.push('{"status":"pulling"}\n{"status":"downloa')
        assert first == [{"status": "pulling"}]
        assert decoder.has_carry() is True
        second = decoder.push('ding"}\n')
        assert second == [{"status": "downloading"}]
        assert decoder.has_carry() is False

    def test_one_line_split_across_three_chunks(self):
        decoder = NdjsonDecoder()
        assert decoder.push('{"ok"') == []
        assert decoder.push(":tr") == []
        assert decoder.push("ue}\n") == [{"ok": True}]

    def test_accepts_bytes_chunks(self):
        decoder = NdjsonDecoder()
        assert decoder.push(b'{"x":1}\n{"x":2}\n') == [{"x": 1}, {"x": 2}]

    def test_ignores_blank_lines(self):
        decoder = NdjsonDecoder()
        assert decoder.push('{"a":1}\n\n') == [{"a": 1}]


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


class _FakeEngineHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass

    # -- write helpers --------------------------------------------------------------------------

    def _write_json(self, status: int, body) -> None:
        payload = b"" if body is None else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _begin_stream(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def _write_chunk(self, data: bytes) -> None:
        # Real chunked transfer framing so http.client's own reader is exercised end-to-end.
        self.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")

    def _end_stream(self) -> None:
        self.wfile.write(b"0\r\n\r\n")

    def _write_ndjson_chunk(self, obj: dict) -> None:
        self._write_chunk((json.dumps(obj) + "\n").encode("utf-8"))

    def _write_log_frame_chunk(self, stream_type: int, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytes([stream_type, 0, 0, 0]) + len(payload).to_bytes(4, "big")
        self._write_chunk(header)  # header and payload as two separate chunks, on purpose —
        self._write_chunk(payload)  # exercises the exact split LogFrameDecoder must tolerate.

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    def _schedule_exit(self, container: dict) -> None:
        delay_ms = int(container["labels"].get("fixture.execDelayMs", "40"))
        exit_code = int(container["labels"].get("fixture.exitCode", "0"))

        def _exit():
            time.sleep(delay_ms / 1000.0)
            with self.server.lock:
                container["running"] = False
                container["exit_code"] = exit_code

        threading.Thread(target=_exit, daemon=True).start()

    # -- routing ----------------------------------------------------------------------------------

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method: str) -> None:  # noqa: C901 - fixture routing, kept flat on purpose
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/v") and (slash := path.find("/", 1)) != -1:
            path = path[slash:]  # strip an optional /vX.YY version prefix, same as the real daemon
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        raw_body = self._read_body()

        if method == "GET" and path == "/version":
            return self._write_json(200, {"Version": "29.7.2-fake", "ApiVersion": "1.51", "MinAPIVersion": "1.24", "Os": "linux", "Arch": "amd64"})
        if method == "GET" and path == "/_ping":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
            return None
        if method == "GET" and path == "/info":
            return self._write_json(200, {"ServerVersion": "29.7.2-fake", "OperatingSystem": "Fake Linux", "OSType": "linux", "Architecture": "x86_64", "NCPU": 4, "MemTotal": 8_000_000_000})

        if method == "POST" and path == "/images/create":
            image = query.get("fromImage", "")
            tag = query.get("tag", "latest")
            if image == "fixture/404-on-pull":
                return self._write_json(404, {"message": f"pull access denied for {image}"})
            self._begin_stream(200)
            if image == "fixture/midstream-error":
                self._write_ndjson_chunk({"status": f"Pulling from {image}", "id": "layer1"})
                self._write_ndjson_chunk({"error": "manifest for fixture/midstream-error:latest not found: manifest unknown"})
            else:
                self._write_ndjson_chunk({"status": f"Pulling from {image}", "id": "a1b2c3d4"})
                self._write_ndjson_chunk({"status": "Downloading", "progressDetail": {"current": 1024, "total": 4096}, "id": "a1b2c3d4"})
                self._write_ndjson_chunk({"status": "Downloading", "progressDetail": {"current": 4096, "total": 4096}, "id": "a1b2c3d4"})
                self._write_ndjson_chunk({"status": "Pull complete", "id": "a1b2c3d4"})
                self._write_ndjson_chunk({"status": f"Status: Downloaded newer image for {image}:{tag}"})
            self._end_stream()
            return None

        if method == "POST" and path == "/containers/create":
            try:
                spec = json.loads(raw_body or b"{}")
            except (ValueError, TypeError):
                return self._write_json(400, {"message": "invalid JSON body"})
            if spec.get("Image") == "fixture/409-on-create":
                return self._write_json(409, {"message": "Conflict. The container name is already in use"})
            if spec.get("Image") == "fixture/500-on-create":
                return self._write_json(500, {"message": "fake internal server error"})
            container_id = uuid.uuid4().hex
            with self.server.lock:
                self.server.containers[container_id] = {
                    "id": container_id,
                    "image": spec.get("Image"),
                    "labels": spec.get("Labels") or {},
                    "running": False,
                    "started": False,
                    "exit_code": None,
                }
            return self._write_json(201, {"Id": container_id, "Warnings": []})

        parts = path.split("/")
        if len(parts) >= 3 and parts[1] == "containers":
            container_id = parts[2]
            sub = "/" + "/".join(parts[3:]) if len(parts) > 3 else ""
            with self.server.lock:
                container = self.server.containers.get(container_id)
            if container is None:
                return self._write_json(404, {"message": f"No such container: {container_id}"})

            if method == "POST" and sub == "/start":
                with self.server.lock:
                    container["running"] = True
                    container["started"] = True
                self._schedule_exit(container)
                return self._write_json(204, None)
            if method == "POST" and sub == "/wait":
                deadline = time.time() + 30
                while time.time() < deadline:
                    with self.server.lock:
                        if not container["running"] and container["exit_code"] is not None:
                            return self._write_json(200, {"StatusCode": container["exit_code"]})
                    time.sleep(0.01)
                return self._write_json(500, {"message": "fake wait() timed out"})
            if method == "POST" and sub == "/stop":
                with self.server.lock:
                    container["running"] = False
                    container["exit_code"] = container["exit_code"] if container["exit_code"] is not None else 0
                return self._write_json(204, None)
            if method == "POST" and sub == "/kill":
                with self.server.lock:
                    container["running"] = False
                    container["exit_code"] = 137
                return self._write_json(204, None)
            if method == "DELETE" and sub == "":
                with self.server.lock:
                    self.server.containers.pop(container_id, None)
                return self._write_json(204, None)
            if method == "GET" and sub == "/json":
                with self.server.lock:
                    return self._write_json(
                        200,
                        {
                            "Id": container["id"],
                            "Name": f"/{container['id'][:12]}",
                            "State": {"Status": "running" if container["running"] else ("exited" if container["started"] else "created"), "Running": container["running"], "ExitCode": container["exit_code"] or 0},
                            "Config": {"Image": container["image"], "Labels": container["labels"]},
                        },
                    )
            if method == "GET" and sub == "/logs":
                self._begin_stream(200)
                self._write_log_frame_chunk(1, container["labels"].get("fixture.stdout", "out\n"))
                self._write_log_frame_chunk(2, container["labels"].get("fixture.stderr", "err\n"))
                self._end_stream()
                return None

        if method == "GET" and path == "/events":
            self._begin_stream(200)
            with self.server.lock:
                last_id = next(reversed(list(self.server.containers)), "unknown")
            self._write_ndjson_chunk({"Type": "container", "Action": "start", "Actor": {"ID": last_id, "Attributes": {}}, "time": int(time.time())})
            time.sleep(0.02)
            self._write_ndjson_chunk({"Type": "container", "Action": "die", "Actor": {"ID": last_id, "Attributes": {"exitCode": "0"}}, "time": int(time.time())})
            self._end_stream()
            return None

        return self._write_json(404, {"message": f"fake-engine-server: unhandled route {method} {path}"})


@pytest.fixture
def fake_engine():
    socket_dir = tempfile.mkdtemp(prefix="tit-fake-engine-")
    socket_path = os.path.join(socket_dir, "engine.sock")
    server = _FakeEngineServer(socket_path, _FakeEngineHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield socket_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def client(fake_engine):
    return DockerEngineClient(DockerConnection(socket_path=fake_engine), timeout_s=5.0)


# ---------------------------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------------------------


class TestDockerEngineClient:
    def test_version_negotiates_api_version(self, client):
        v = client.version()
        assert v["ApiVersion"] == "1.51"
        assert v["Os"] == "linux"

    def test_info_and_ping(self, client):
        info = client.info()
        assert info["NCPU"] == 4
        assert client.ping() is True

    def test_ping_false_against_nothing_listening(self):
        dead = DockerEngineClient(DockerConnection(socket_path="/tmp/tit-nothing-here.sock"), timeout_s=1.0)
        assert dead.ping() is False

    def test_pull_image_streams_progress_ending_with_status_line(self, client):
        events = []
        client.pull_image("alpine", "3.20", on_progress=lambda e: events.append(e["status"]))
        assert len(events) >= 4
        assert "Status: Downloaded newer image" in events[-1]
        assert "Downloading" in events

    def test_pull_image_midstream_error_raises(self, client):
        with pytest.raises(DockerEngineError, match="manifest unknown"):
            client.pull_image("fixture/midstream-error", "latest")

    def test_pull_image_404_maps_to_not_found(self, client):
        with pytest.raises(DockerEngineError) as excinfo:
            client.pull_image("fixture/404-on-pull", "latest")
        assert excinfo.value.kind == "not-found"
        assert excinfo.value.status_code == 404

    def test_full_container_lifecycle(self, client):
        spec = ContainerCreateSpec(
            image="alpine:3.20",
            cmd=["sh", "-c", "echo out; echo err 1>&2; sleep 1; exit 3"],
            labels={"fixture.exitCode": "3", "fixture.execDelayMs": "30"},
        )
        container_id = client.create_container(spec)
        client.start_container(container_id)

        running = client.inspect_container(container_id)
        assert running["State"]["Running"] is True

        frames = list(client.logs(container_id, follow=False))
        by_stream = {}
        for f in frames:
            by_stream[f.stream] = by_stream.get(f.stream, b"") + f.payload
        assert by_stream["stdout"] == b"out\n"
        assert by_stream["stderr"] == b"err\n"

        status_code = client.wait_container(container_id)
        assert status_code == 3

        exited = client.inspect_container(container_id)
        assert exited["State"]["Running"] is False
        assert exited["State"]["ExitCode"] == 3

        client.remove_container(container_id)
        with pytest.raises(DockerEngineError) as excinfo:
            client.inspect_container(container_id)
        assert excinfo.value.kind == "not-found"
        assert excinfo.value.status_code == 404

    def test_stop_container_sets_exit_code_zero(self, client):
        container_id = client.create_container(ContainerCreateSpec(image="alpine:3.20", cmd=["sleep", "999"], labels={"fixture.execDelayMs": "999999"}))
        client.start_container(container_id)
        client.stop_container(container_id, grace_seconds=1)
        assert client.wait_container(container_id) == 0

    def test_kill_container_reports_137(self, client):
        container_id = client.create_container(ContainerCreateSpec(image="alpine:3.20", cmd=["sleep", "999"], labels={"fixture.execDelayMs": "999999"}))
        client.start_container(container_id)
        client.kill_container(container_id)
        inspected = client.inspect_container(container_id)
        assert inspected["State"]["ExitCode"] == 137

    def test_create_container_maps_409_and_500(self, client):
        with pytest.raises(DockerEngineError) as conflict:
            client.create_container(ContainerCreateSpec(image="fixture/409-on-create"))
        assert conflict.value.kind == "conflict"
        assert conflict.value.status_code == 409

        with pytest.raises(DockerEngineError) as servererr:
            client.create_container(ContainerCreateSpec(image="fixture/500-on-create"))
        assert servererr.value.kind == "server-error"
        assert servererr.value.status_code == 500

    def test_events_yields_lifecycle_events(self, client):
        container_id = client.create_container(ContainerCreateSpec(image="alpine:3.20", cmd=["true"], labels={"fixture.execDelayMs": "20"}))
        client.start_container(container_id)
        events = []
        for event in client.events({"type": ["container"]}):
            events.append(event)
            if len(events) >= 2:
                break
        assert [e["Action"] for e in events] == ["start", "die"]
        assert events[0]["Actor"]["ID"] == container_id

    def test_run_job_container_sets_tit_job_id_label(self, client):
        container_id = run_job_container(
            client,
            image="alpine:3.20",
            cmd=["true"],
            job_id="job-abc123",
            binds=["/host/project:/data:ro"],
            env={"OMP_NUM_THREADS": "4"},
        )
        inspected = client.inspect_container(container_id)
        assert inspected["Config"]["Labels"]["tit.job_id"] == "job-abc123"
        assert inspected["State"]["Running"] is True


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
