"""Dependency-free Docker Engine API client — stdlib ``http.client`` over ``AF_UNIX``.

The Node-side twin of this module is ``desktop/src/main/docker/engine.ts``; both talk the same
Docker Engine REST API subset directly over the Unix socket, never the ``docker`` CLI and never
the third-party ``docker`` PyPI package (r5-docker-integration.md §5 — that package is not
installed in ``idossha/ti-toolbox:v3.0.0`` today, and adding it would only grow a 19 GB image
further for something ~15 lines of stdlib already does).

**Scope, and why it is narrower than the TypeScript client**: this module is used from *inside*
the ``tit`` container, where QSIPrep/QSIRecon are spawned as sibling containers via
Docker-outside-of-Docker (DooD) — the root ``docker-compose.yml`` mounts the *host's*
``/var/run/docker.sock`` straight through, a Unix path, regardless of what OS the host actually
is. So unlike the Electron client (which must speak to a real Windows named pipe on a Windows
host), this module **never needs npipe transport at all** — Windows support here would mean
supporting it as a *pywin32* dependency for a case that cannot occur in this architecture, which
is why it is explicitly out of scope, not merely unimplemented. If a future redesign ever has
Electron spawn QSIPrep containers directly instead of via DooD (r5 §5's "bigger architectural
change, out of scope"), that would need a real npipe-capable Python client; this one is not it.

**Discovery**: ``DOCKER_HOST`` (``unix://`` only — ``tcp://``/``npipe://`` are parsed for
completeness but this module never *drives* the tcp/npipe internals `http.client` would need),
else the well-known mount path ``/var/run/docker.sock``. No ``docker context inspect`` shell-out
here (unlike ``discover.ts``): the Python side always runs *inside* the ``tit`` container, where
the socket location is a known, fixed bind mount, not an environment to be discovered the way a
user's host machine is (r5 §5's "the Python client only ever needs the Unix-socket transport").

**API version negotiation**: identical strategy to ``engine.ts`` — :meth:`DockerEngineClient.version`
hits the always-unversioned ``GET /version``, reads ``ApiVersion`` from the response, and every
later call is prefixed ``/v<ApiVersion>/...``.

**Framing**: :meth:`DockerEngineClient.logs` demultiplexes the same 8-byte
``[STREAM_TYPE, 0,0,0, SIZE(be32)][SIZE bytes]`` frames as ``frames.ts``'s ``LogFrameDecoder``
(mirrored here as :class:`LogFrameDecoder`, pure and independently unit-tested); pull progress and
``/events`` are newline-delimited JSON (:class:`NdjsonDecoder`, mirrors ``NdjsonDecoder``).

**Job-container convenience**: :func:`run_job_container` always accepts a ``job_id`` and sets
``Labels["tit.job_id"]`` — the exact label ``tit/jobs/runner.py``'s ``stop_docker_siblings(job_id)``
filters on (``docker ps -q --filter label=tit.job_id=<id>``). ``tit/pre/qsi/docker_builder.py``'s
``_label_args()`` now sets this same label on both the ``qsiprep`` and ``qsirecon`` ``docker run``
invocations it builds (confirmed: ``rg -n "tit\\.job_id" tit/pre/qsi/docker_builder.py`` — two
hits), so ``stop_docker_siblings`` already finds its matching containers for QSI jobs today; the
gap this paragraph used to describe (r5 §1.4 / skeptic-3 claim #3) is closed on the labeling side.
What is *not* closed: ``docker_builder.py`` still shells out to the ``docker`` CLI directly rather
than through this client (``rg -n '"docker"' tit/pre/qsi/docker_builder.py``) — migrating it onto
:func:`run_job_container` is still open work, out of scope here. Mount/env shape (``/data``
read-only BIDS input, ``/out`` output, ``/work`` scratch) mirrors ``tit/pre/qsi/docker_builder.py``'s
``DockerPaths`` so the two stay drop-in compatible; see ``run_qsiprep_example`` at the bottom of
this file for the exact call shape a migrated ``run_qsiprep()`` would make (documentation only —
this module is not wired into ``tit/pre/qsi/*.py`` yet).
"""

from __future__ import annotations

import http.client
import json
import os
import socket
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlencode

DEFAULT_SOCKET_PATH = "/var/run/docker.sock"
DEFAULT_TIMEOUT_S = 10.0
# ``None`` disables the socket timeout entirely — used for long-lived calls (logs follow, events,
# wait), which can legitimately block for hours (a real SimNIBS/QSIPrep job's duration).
NO_TIMEOUT = None
# Short bound for calls made on a *latency-sensitive* path -- liveness probes, and anything a job
# cancellation waits on. A Docker daemon can be wedged (socket accepts the connection and then
# never answers); ten seconds of that per call is enough to make a cancel look hung, so these
# calls give up quickly and let the caller degrade to a warning.
SHORT_TIMEOUT_S = 3.0


class DockerEngineError(Exception):
    """Carries a stable ``kind`` (mirrors ``DockerErrorKind`` in ``engine.ts``) and, for an HTTP-
    level failure, the ``status_code`` that produced it."""

    def __init__(self, kind: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


def _classify_status_code(status_code: int) -> str:
    if status_code == 404:
        return "not-found"
    if status_code == 409:
        return "conflict"
    if status_code == 400:
        return "bad-request"
    if status_code >= 500:
        return "server-error"
    return "unknown"


def _api_error_from_body(status_code: int, body: bytes) -> DockerEngineError:
    text = body.decode("utf-8", errors="replace")
    message = text or f"HTTP {status_code}"
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("message"):
            message = str(parsed["message"])
    except (ValueError, TypeError):
        pass
    return DockerEngineError(_classify_status_code(status_code), message, status_code)


# ---------------------------------------------------------------------------------------------
# Pure streaming decoders (no I/O) — same shape as frames.ts's LogFrameDecoder/NdjsonDecoder, so
# tests/test_docker_engine.py can feed them arbitrary chunk splits without a socket anywhere.
# ---------------------------------------------------------------------------------------------

_STREAM_NAMES = {0: "stdin", 1: "stdout", 2: "stderr"}
_HEADER_LEN = 8


@dataclass
class LogFrame:
    stream: str
    payload: bytes


class LogFrameDecoder:
    """Demultiplexes Docker's ``[STREAM_TYPE,0,0,0,SIZE(be32)][SIZE bytes]`` log/attach framing."""

    def __init__(self) -> None:
        self._buf = b""

    def push(self, chunk: bytes) -> list[LogFrame]:
        self._buf += chunk
        frames: list[LogFrame] = []
        while True:
            if len(self._buf) < _HEADER_LEN:
                break
            size = int.from_bytes(self._buf[4:8], "big")
            if len(self._buf) < _HEADER_LEN + size:
                break
            stream_byte = self._buf[0]
            payload = self._buf[_HEADER_LEN : _HEADER_LEN + size]
            frames.append(
                LogFrame(
                    stream=_STREAM_NAMES.get(stream_byte, "stdout"), payload=payload
                )
            )
            self._buf = self._buf[_HEADER_LEN + size :]
        return frames

    def remainder(self) -> bytes:
        return self._buf


class NdjsonDecoder:
    """Splits a byte stream into complete JSON objects, one per newline-delimited line."""

    def __init__(self) -> None:
        self._carry = ""

    def push(self, chunk: bytes | str) -> list[Any]:
        text = self._carry + (
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        )
        lines = text.split("\n")
        self._carry = lines.pop()
        out: list[Any] = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue
            out.append(json.loads(trimmed))
        return out

    def has_carry(self) -> bool:
        return bool(self._carry.strip())


# ---------------------------------------------------------------------------------------------
# Transport: an HTTPConnection that dials AF_UNIX instead of AF_INET (~15-line pattern, r5 §5).
# ---------------------------------------------------------------------------------------------


class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self, socket_path: str, timeout: float | None = DEFAULT_TIMEOUT_S
    ) -> None:
        # host is cosmetic ("localhost") — connect() below ignores it entirely and dials the
        # Unix socket path instead; HTTPConnection still needs *some* Host header value.
        super().__init__("localhost", timeout=timeout if timeout is not None else 0)
        self._socket_path = socket_path
        self._no_timeout = timeout is None

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if not self._no_timeout:
            sock.settimeout(self.timeout)
        try:
            sock.connect(self._socket_path)
        except FileNotFoundError as exc:
            raise DockerEngineError(
                "not-installed", f"No Docker socket at {self._socket_path}"
            ) from exc
        except ConnectionRefusedError as exc:
            raise DockerEngineError(
                "not-running",
                f"Docker socket exists but nothing answers: {self._socket_path}",
            ) from exc
        except PermissionError as exc:
            raise DockerEngineError(
                "socket-permission",
                f"Permission denied connecting to {self._socket_path}",
            ) from exc
        except socket.timeout as exc:
            raise DockerEngineError(
                "timeout", f"Timed out connecting to {self._socket_path}"
            ) from exc
        self.sock = sock


# ---------------------------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------------------------


@dataclass
class DockerConnection:
    socket_path: str = DEFAULT_SOCKET_PATH


def discover(env: dict[str, str] | None = None) -> DockerConnection:
    """``DOCKER_HOST=unix://...`` if set, else the well-known DooD bind-mount path. See the module
    docstring for why this is intentionally narrower than ``discover.ts``'s multi-candidate,
    CLI-assisted search — this module always runs inside a container with a known socket mount.
    """
    resolved_env = os.environ if env is None else env
    host = resolved_env.get("DOCKER_HOST")
    if host and host.startswith("unix://"):
        path = host[len("unix://") :] or DEFAULT_SOCKET_PATH
        return DockerConnection(socket_path=path)
    return DockerConnection(socket_path=DEFAULT_SOCKET_PATH)


# ---------------------------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------------------------


@dataclass
class ContainerCreateSpec:
    image: str
    cmd: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    tty: bool = False
    working_dir: str | None = None
    platform: str | None = None
    binds: list[str] = field(default_factory=list)
    auto_remove: bool = False
    nano_cpus: int | None = None
    memory_bytes: int | None = None

    def to_wire(self) -> dict[str, Any]:
        host_config: dict[str, Any] = {
            "Binds": self.binds,
            "AutoRemove": self.auto_remove,
        }
        if self.nano_cpus is not None:
            host_config["NanoCpus"] = self.nano_cpus
        if self.memory_bytes is not None:
            host_config["Memory"] = self.memory_bytes
        spec: dict[str, Any] = {
            "Image": self.image,
            "Cmd": self.cmd,
            "Env": [f"{k}={v}" for k, v in self.env.items()],
            "Labels": self.labels,
            "Tty": self.tty,
            "HostConfig": host_config,
        }
        if self.working_dir:
            spec["WorkingDir"] = self.working_dir
        if self.platform:
            spec["Platform"] = self.platform
        return spec


class DockerEngineClient:
    """Covers the endpoints a QSIPrep/QSIRecon DooD spawn needs: pull, create/start/wait/
    stop/kill/remove/inspect, logs (demuxed), events. No exec/attach-hijack (unused, r5 §1.2).
    """

    def __init__(
        self, conn: DockerConnection, timeout_s: float | None = DEFAULT_TIMEOUT_S
    ) -> None:
        self._conn = conn
        self._timeout_s = timeout_s
        self._api_version: str | None = None

    def _open(self, timeout_s: float | None) -> _UnixSocketHTTPConnection:
        return _UnixSocketHTTPConnection(self._conn.socket_path, timeout=timeout_s)

    def _vpath(self, path: str) -> str:
        return f"/v{self._api_version}{path}" if self._api_version else path

    def _ensure_negotiated(self) -> None:
        if self._api_version is None:
            self.version()

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: bytes | str | None = None,
        timeout_s: float | None | object = "default",
    ) -> tuple[int, http.client.HTTPResponse, _UnixSocketHTTPConnection]:
        full_path = path
        if query:
            filtered = {k: v for k, v in query.items() if v is not None}
            if filtered:
                full_path += "?" + urlencode(
                    {
                        k: (
                            v
                            if isinstance(v, str)
                            else json.dumps(v) if isinstance(v, (dict, list)) else v
                        )
                        for k, v in filtered.items()
                    }
                )
        effective_timeout = self._timeout_s if timeout_s == "default" else timeout_s
        conn = self._open(effective_timeout)
        headers: dict[str, str] = {}
        body_bytes: bytes | None = None
        if body is not None:
            body_bytes = body.encode("utf-8") if isinstance(body, str) else body
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body_bytes))
        conn.request(method, full_path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp, conn

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: bytes | str | None = None,
        timeout_s: float | None | object = "default",
    ) -> Any:
        status, resp, conn = self._request(
            method, path, query=query, body=body, timeout_s=timeout_s
        )
        try:
            raw = resp.read()
        finally:
            conn.close()
        if status >= 400:
            raise _api_error_from_body(status, raw)
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise DockerEngineError(
                "unsupported-engine",
                f"Non-JSON response from {method} {path} (status {status}): {raw[:200]!r}",
            ) from exc

    # -- capability probes --------------------------------------------------------------------

    def version(self) -> dict[str, Any]:
        info = self._json_request("GET", "/version")
        if info and info.get("ApiVersion"):
            self._api_version = info["ApiVersion"]
        return info

    def info(self) -> dict[str, Any]:
        self._ensure_negotiated()
        return self._json_request("GET", self._vpath("/info"))

    def ping(self, timeout_s: float | None = SHORT_TIMEOUT_S) -> bool:
        """Liveness probe. Bounded by *timeout_s* (not the client's default): a wedged daemon
        that accepts connections and never answers must report "not reachable" promptly rather
        than block the caller."""
        try:
            status, resp, conn = self._request("GET", "/_ping", timeout_s=timeout_s)
            try:
                resp.read()
            finally:
                conn.close()
            return status == 200
        except (DockerEngineError, OSError):
            return False

    def system_df(
        self, timeout_s: float | None | object = "default"
    ) -> dict[str, Any]:
        """``GET /system/df`` -- the Engine-API equivalent of ``docker system df``.

        Read-only, used by the System page's Docker-health panel. It is a genuinely expensive call
        on the daemon side (it walks the image graph), which is why the caller polls it on a
        multi-second TTL and passes an explicit timeout rather than the client default.
        """
        self._ensure_negotiated()
        return self._json_request(
            "GET", self._vpath("/system/df"), timeout_s=timeout_s
        )

    # -- images ---------------------------------------------------------------------------------

    def list_images(
        self, timeout_s: float | None | object = "default"
    ) -> list[dict[str, Any]]:
        """``GET /images/json`` -- ``docker images``. Read-only; see :meth:`system_df`."""
        self._ensure_negotiated()
        result = self._json_request(
            "GET", self._vpath("/images/json"), timeout_s=timeout_s
        )
        return list(result or [])

    def pull_image(
        self,
        image: str,
        tag: str,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """``POST /images/create`` — streams NDJSON progress; raises on a non-2xx status *or* a
        ``{"error": ...}`` object appearing mid-stream (Docker reports some pull failures inside an
        HTTP-200 NDJSON stream, not as an HTTP error status)."""
        self._ensure_negotiated()
        status, resp, conn = self._request(
            "POST",
            self._vpath("/images/create"),
            query={"fromImage": image, "tag": tag},
            timeout_s=NO_TIMEOUT,
        )
        try:
            if status >= 400:
                raise _api_error_from_body(status, resp.read())
            decoder = NdjsonDecoder()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                for event in decoder.push(chunk):
                    if event.get("error"):
                        raise DockerEngineError("unknown", str(event["error"]))
                    if on_progress:
                        on_progress(event)
        finally:
            conn.close()

    # -- container lifecycle ---------------------------------------------------------------------

    def create_container(
        self, spec: ContainerCreateSpec, name: str | None = None
    ) -> str:
        self._ensure_negotiated()
        result = self._json_request(
            "POST",
            self._vpath("/containers/create"),
            query={"name": name} if name else None,
            body=json.dumps(spec.to_wire()),
        )
        return result["Id"]

    def list_containers(
        self,
        *,
        filters: dict[str, list[str]] | None = None,
        all_containers: bool = False,
        timeout_s: float | None | object = "default",
    ) -> list[dict[str, Any]]:
        """``GET /containers/json`` — the Engine-API equivalent of ``docker ps [--filter …]``.

        *filters* is the Engine's own filter map (e.g. ``{"label": ["tit.job_id=abc"]}``); it is
        JSON-encoded into the query string by :meth:`_request`. Every caller in this repo passes
        an explicit *timeout_s* (startup reconciliation must never block on a wedged daemon).
        """
        self._ensure_negotiated()
        result = self._json_request(
            "GET",
            self._vpath("/containers/json"),
            query={
                "all": "1" if all_containers else "0",
                "filters": filters or None,
            },
            timeout_s=timeout_s,
        )
        return list(result or [])

    def start_container(self, container_id: str) -> None:
        self._ensure_negotiated()
        self._json_request("POST", self._vpath(f"/containers/{container_id}/start"))

    def wait_container(self, container_id: str, condition: str = "not-running") -> int:
        self._ensure_negotiated()
        result = self._json_request(
            "POST",
            self._vpath(f"/containers/{container_id}/wait"),
            query={"condition": condition},
            timeout_s=NO_TIMEOUT,
        )
        return int(result["StatusCode"])

    def stop_container(
        self, container_id: str, grace_seconds: int | None = None
    ) -> None:
        self._ensure_negotiated()
        self._json_request(
            "POST",
            self._vpath(f"/containers/{container_id}/stop"),
            query={"t": grace_seconds} if grace_seconds is not None else None,
            timeout_s=NO_TIMEOUT,
        )

    def kill_container(self, container_id: str, signal: str = "SIGKILL") -> None:
        self._ensure_negotiated()
        self._json_request(
            "POST",
            self._vpath(f"/containers/{container_id}/kill"),
            query={"signal": signal},
        )

    def remove_container(
        self, container_id: str, force: bool = False, volumes: bool = False
    ) -> None:
        self._ensure_negotiated()
        self._json_request(
            "DELETE",
            self._vpath(f"/containers/{container_id}"),
            query={
                "force": "true" if force else None,
                "v": "true" if volumes else None,
            },
        )

    def inspect_container(self, container_id: str) -> dict[str, Any]:
        self._ensure_negotiated()
        return self._json_request(
            "GET", self._vpath(f"/containers/{container_id}/json")
        )

    def logs(
        self,
        container_id: str,
        *,
        follow: bool = False,
        stdout: bool = True,
        stderr: bool = True,
        tail: str | None = None,
    ) -> Generator[LogFrame, None, None]:
        self._ensure_negotiated()
        query = {
            "follow": "true" if follow else "false",
            "stdout": "true" if stdout else "false",
            "stderr": "true" if stderr else "false",
            "tail": tail,
        }
        status, resp, conn = self._request(
            "GET",
            self._vpath(f"/containers/{container_id}/logs"),
            query=query,
            timeout_s=NO_TIMEOUT,
        )
        try:
            if status >= 400:
                raise _api_error_from_body(status, resp.read())
            decoder = LogFrameDecoder()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                yield from decoder.push(chunk)
        finally:
            conn.close()

    def events(
        self, filters: dict[str, list[str]] | None = None
    ) -> Generator[dict[str, Any], None, None]:
        self._ensure_negotiated()
        query = {"filters": json.dumps(filters)} if filters else None
        status, resp, conn = self._request(
            "GET", self._vpath("/events"), query=query, timeout_s=NO_TIMEOUT
        )
        try:
            if status >= 400:
                raise _api_error_from_body(status, resp.read())
            decoder = NdjsonDecoder()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                yield from decoder.push(chunk)
        finally:
            conn.close()


# ---------------------------------------------------------------------------------------------
# Job-container convenience (mirrors engine.ts's runJobContainer — r5 §4's sketch).
# ---------------------------------------------------------------------------------------------


def run_job_container(
    client: DockerEngineClient,
    *,
    image: str,
    cmd: list[str],
    job_id: str | None = None,
    name: str | None = None,
    env: dict[str, str] | None = None,
    binds: Iterable[str] = (),
    labels: dict[str, str] | None = None,
    platform: str | None = None,
    cpus: float | None = None,
    memory_bytes: int | None = None,
    auto_remove: bool = False,
) -> str:
    """``create_container`` + ``start_container``, returning the container id immediately. Always
    sets ``Labels["tit.job_id"]`` when *job_id* is given — see the module docstring for how
    ``tit/pre/qsi/docker_builder.py``'s own ``_label_args()`` sets the same label independently
    today, and what migrating it onto this client would still change (the CLI shell-out).
    """
    resolved_labels = dict(labels or {})
    if job_id:
        resolved_labels["tit.job_id"] = job_id
    spec = ContainerCreateSpec(
        image=image,
        cmd=cmd,
        env=env or {},
        labels=resolved_labels,
        platform=platform,
        binds=list(binds),
        auto_remove=auto_remove,
        nano_cpus=int(cpus * 1e9) if cpus is not None else None,
        memory_bytes=memory_bytes,
    )
    container_id = client.create_container(spec, name=name)
    client.start_container(container_id)
    return container_id


def run_qsiprep_example(
    client: DockerEngineClient, job_id: str, host_project_dir: str, subject_id: str
) -> str:
    """Documentation only (not called by production code): the call shape a
    ``tit/pre/qsi/docker_builder.py`` migration would make, using the exact same
    ``/data``:ro / ``/out`` / ``/work`` mount points as today's ``DockerPaths`` dataclass, and the
    same ``tit.job_id`` label ``build_qsiprep_cmd`` already sets via ``_label_args`` — the
    migration this documents is about the CLI shell-out, not the label."""
    return run_job_container(
        client,
        image="pennlinc/qsiprep:26.0.0",
        cmd=["/data", "/out", "participant", "--participant-label", subject_id],
        job_id=job_id,
        env={"OMP_NUM_THREADS": "4"},
        binds=[
            f"{host_project_dir}:/data:ro",
            f"{host_project_dir}/derivatives/qsiprep:/out",
            f"{host_project_dir}/derivatives/.qsiprep_work:/work",
        ],
        platform="linux/amd64",
    )
