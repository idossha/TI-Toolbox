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

**What it covers**: only the read-and-stop subset production calls --
:meth:`DockerEngineClient.version`, :meth:`~DockerEngineClient.system_df` and
:meth:`~DockerEngineClient.list_images` (the System page's Docker panel, ``tit/server/routes/system.py``),
:meth:`~DockerEngineClient.list_containers` and :meth:`~DockerEngineClient.stop_container`
(``tit/jobs/runner.py``'s ``stop_docker_siblings_via_engine``, which stops a stranded job's
QSIPrep/QSIRecon siblings by their ``tit.job_id`` label at startup) and
:meth:`~DockerEngineClient.inspect_container` (``tit/host_path.py`` and the System page, reading
the container's own mounts). QSIPrep/QSIRecon themselves are still started through the
``docker`` CLI by ``tit/pre/qsi/docker_builder.py``, which sets the same ``tit.job_id`` label.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

DEFAULT_SOCKET_PATH = "/var/run/docker.sock"
DEFAULT_TIMEOUT_S = 10.0
# ``None`` disables the socket timeout entirely -- :meth:`DockerEngineClient.stop_container` uses
# it, because the daemon itself bounds a stop by its grace period.
NO_TIMEOUT = None


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


class DockerEngineClient:
    """Version, disk usage, images, containers (list/inspect/stop) over the Engine REST API."""

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

    def system_df(self, timeout_s: float | None | object = "default") -> dict[str, Any]:
        """``GET /system/df`` -- the Engine-API equivalent of ``docker system df``.

        Read-only, used by the System page's Docker-health panel. It is a genuinely expensive call
        on the daemon side (it walks the image graph), which is why the caller polls it on a
        multi-second TTL and passes an explicit timeout rather than the client default.
        """
        self._ensure_negotiated()
        return self._json_request("GET", self._vpath("/system/df"), timeout_s=timeout_s)

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

    # -- container lifecycle ---------------------------------------------------------------------

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

    def inspect_container(self, container_id: str) -> dict[str, Any]:
        self._ensure_negotiated()
        return self._json_request(
            "GET", self._vpath(f"/containers/{container_id}/json")
        )
