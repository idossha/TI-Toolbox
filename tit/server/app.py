"""FastAPI application factory for ``tit.server``."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import psutil
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import tit
from tit.paths import get_path_manager
from tit.server import COOKIE_NAME, SERVER_API, static, ws
from tit.server.auth import _token_matches, new_session_id, require_auth
from tit.server.routes import OPEN_MODULES, iter_route_modules
from tit.server.settings import ServerSettings

# TODO.md §2.8. D3 (dev/notes/v3-docker-streamline-plan.md): the in-app viewer is now the
# Tetravox embed, rendered inside a same-origin <iframe src="/tetravox/...">, not code running in
# this app's own origin/CSP -- tit/server/static.py's TETRAVOX_CSP carries the 'wasm-unsafe-eval'
# its Rust->WASM engine needs, on responses under /tetravox/ only. This header no longer needs
# (and no longer grants) it: plain JS eval and WASM instantiation both stay blocked in the app's
# own origin. 'frame-src self' keeps permitting that iframe.
#: The published documentation website. Help -> Docs frames it (and probes it with a `no-cors`
#: fetch first), so it needs both `frame-src` and `connect-src`; nothing else in the app talks to
#: an outside origin. Framing a same-origin `/docs/` instead is what made that tab render the app
#: inside itself -- the static route is an SPA catch-all (`tit/server/static.py`).
DOCS_SITE_ORIGIN = "https://idossha.github.io"

CSP_HEADER = (
    f"default-src 'self'; connect-src 'self' {DOCS_SITE_ORIGIN}; img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; "
    f"worker-src 'self' blob:; frame-src 'self' {DOCS_SITE_ORIGIN}; object-src 'none'"
)

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")

logger = logging.getLogger(__name__)


class CSPMiddleware:
    """Add ``Content-Security-Policy`` to every HTML response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_csp(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                content_type = b""
                for key, value in headers:
                    if key.lower() == b"content-type":
                        content_type = value
                        break
                has_csp = any(
                    k.lower() == b"content-security-policy" for k, _ in headers
                )
                if content_type.lower().startswith(b"text/html") and not has_csp:
                    # Routes that set their own policy (sandboxed report HTML) keep it: two CSP
                    # headers are enforced as an intersection, which would block the report's
                    # inline scripts.
                    headers.append((b"content-security-policy", CSP_HEADER.encode()))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_csp)


def allowed_hosts(settings: ServerSettings) -> list[str]:
    """``127.0.0.1``/``localhost`` plus ``--allow-host`` / ``TIT_ALLOW_HOSTS`` entries."""
    hosts = list(DEFAULT_ALLOWED_HOSTS)
    for host in settings.allow_hosts:
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _rewrite_defs_refs(node: Any) -> Any:
    """Turn ``#/$defs/X`` references into ``#/components/schemas/X`` (recursively)."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if (
                key == "$ref"
                and isinstance(value, str)
                and value.startswith("#/$defs/")
            ):
                out[key] = "#/components/schemas/" + value[len("#/$defs/") :]
            else:
                out[key] = _rewrite_defs_refs(value)
        return out
    if isinstance(node, list):
        return [_rewrite_defs_refs(item) for item in node]
    return node


def _job_enum_schemas() -> dict[str, Any]:
    """``JobKind``/``JobState`` as this server actually understands them.

    Every job-submitting route takes its body as ``dict[str, Any]`` (the config shapes are
    dataclasses, not Pydantic models), so FastAPI's generated document names no job enum at all --
    a client reading the live document could not discover which kinds exist, which is most of the
    reason to publish it (`GET /api/openapi.json`). These come from ``tit.jobs.spec``, the same
    tuples the manager validates submissions against, so the published enum can never drift from
    what the server will accept.
    """
    from tit.jobs.spec import JOB_KINDS, JOB_STATES

    return {
        "JobKind": {
            "type": "string",
            "enum": list(JOB_KINDS),
            "description": "Job kinds this server can run (tit.jobs.spec.JOB_KINDS).",
        },
        "JobState": {
            "type": "string",
            "enum": list(JOB_STATES),
            "description": "Job lifecycle states (tit.jobs.spec.JOB_STATES).",
        },
    }


def _custom_openapi(app: FastAPI) -> dict[str, Any]:
    """Generated schema plus the WebSocket route FastAPI cannot describe."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Publish the config dataclass schemas so the dump is a superset of contracts/openapi.v1.json
    # (routes accept config bodies as dicts; the schemas come from contracts/schema.json).
    try:
        from tit.server.routes.schema import _load_schema as load_schema_document

        defs = load_schema_document().get("$defs", {})
    except Exception:  # pragma: no cover - schema.json missing in odd deployments
        defs = {}
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in defs.items():
        components.setdefault(name, _rewrite_defs_refs(definition))
    for name, definition in _job_enum_schemas().items():
        components.setdefault(name, definition)
    schema["paths"]["/ws/tetravox"] = {
        "get": {
            "summary": "WebSocket; app-level events (today only tetravox.updated, "
            "published by the auto-update policy)",
            "responses": {"101": {"description": "switching protocols"}},
        }
    }
    schema["paths"]["/ws/kernels/{kernel_id}"] = {
        "get": {
            "summary": "WebSocket; one notebook kernel's traffic — execute/interrupt/restart/"
            "complete/inspect down, status/input/output/clear/reply/complete/inspect/fatal up "
            "(auth via cookie or ?token=)",
            "responses": {"101": {"description": "switching protocols"}},
        }
    }
    schema["paths"]["/ws/system"] = {
        "get": {
            "summary": "WebSocket; one SystemSnapshot JSON message every 2 s "
            "(auth via cookie or ?token=)",
            "responses": {"101": {"description": "switching protocols"}},
        }
    }
    app.openapi_schema = schema
    return schema


async def _tetravox_auto_update(app: FastAPI) -> None:
    """A3 — check the Tetravox release index at startup and every 24 h.

    Three properties, in the order they matter:

    1. **It never delays ``/api/health``.**  It is an :mod:`asyncio` task created
       by the lifespan *after* startup completes, and its first act is to sleep
       :data:`tit.tetravox.updates.STARTUP_DELAY_S`, so a request arriving in the
       first moments of the process is answered by a loop that is doing nothing.
    2. **Every network call runs in a threadpool.**  ``tit.tetravox`` is
       ``urllib``-based and blocking; awaiting it on the event loop would stall
       every other request for the length of a 30 s timeout.
    3. **It cannot take the server down.**  Every pass is wrapped: an offline
       host, a 403 and a corrupt archive are all recorded as the last outcome and
       reported by ``GET /api/tetravox/updates``, never raised.

    A short-lived process (a ``TestClient`` block, ``--dump-openapi``) shuts its
    lifespan down long before the initial sleep elapses, so it makes no request
    at all -- which is why the delay is part of the design and not politeness.
    """
    from tit.tetravox import store as tvx_store
    from tit.tetravox import updates as tvx_updates

    await asyncio.sleep(tvx_updates.STARTUP_DELAY_S)
    while True:
        try:
            settings = app.state.settings
            root = tvx_store.install_root(
                getattr(settings, "tetravox_install_root", None)
            )
            # No `current_version`: the baseline is the newest bundle this updater
            # itself installed from a release, not whatever happens to be active.
            # The dev container holds a hand-installed 0.4.0 from a pre-release
            # branch -- numerically ahead of the first real release (0.3.12) --
            # so comparing against the active bundle would answer "up to date"
            # forever on exactly the machine this matters on.
            outcome = await run_in_threadpool(
                tvx_updates.run_check_and_maybe_install, root
            )
            await run_in_threadpool(tvx_updates.record_outcome, root, outcome)
            logger.info(
                "tetravox auto-update: %s — %s", outcome.action, outcome.message
            )
            if outcome.action == "installed" and outcome.version:
                ws.publish_tetravox_updated(
                    outcome.version, outcome.protocol, outcome.message
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # never take the server down for a viewer update
            logger.exception("tetravox auto-update: check failed")
        await asyncio.sleep(tvx_updates.CHECK_INTERVAL_S)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the background Tetravox check; cancel it on shutdown."""
    task = asyncio.create_task(_tetravox_auto_update(app))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        # Every kernel this process started is this process's to end. A
        # notebook kernel is a full SimNIBS Python interpreter; leaking one
        # per server restart is how a container ends up out of memory.
        with contextlib.suppress(Exception):
            from tit.server.kernels import get_kernel_registry

            get_kernel_registry().shutdown_all()


def create_app(settings: ServerSettings) -> FastAPI:
    """Build the application; sets the PathManager singleton from *settings*."""
    if settings.project_dir:
        get_path_manager(settings.project_dir)

    app = FastAPI(
        title="TI-Toolbox job server (tit.server)",
        version=tit.__version__,
        description=f"server API {SERVER_API}",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.started_at = time.monotonic()
    # Live cookie sessions (random ids, never the token). In-memory only: a
    # restart forgets them all and the UI falls back to the launcher.
    app.state.sessions = set()
    psutil.cpu_percent(interval=None)  # prime: the first sample is always 0.0

    # Middleware: last added = outermost. TrustedHost runs before everything.
    app.add_middleware(CSPMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(settings))

    @app.get(
        "/auth/session",
        summary="Token → cookie exchange (called by the launcher once)",
        status_code=303,
        responses={
            303: {"description": "cookie set, redirect to /"},
            401: {"description": "bad token"},
        },
        response_class=RedirectResponse,
    )
    def auth_session(token: str, request: Request) -> RedirectResponse:
        if not _token_matches(token, request.app.state.settings.token):
            raise HTTPException(status_code=401, detail="Unauthorized")
        session_id = new_session_id()
        request.app.state.sessions.add(session_id)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return response

    @app.post(
        "/auth/logout",
        summary="End the cookie session (cookie or Bearer auth required)",
        status_code=204,
        dependencies=[Depends(require_auth)],
        responses={
            204: {"description": "cookie cleared, session forgotten"},
            401: {"description": "Unauthorized"},
        },
        response_class=Response,
    )
    def auth_logout(request: Request) -> Response:
        request.app.state.sessions.discard(request.cookies.get(COOKIE_NAME))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict")
        return response

    protected = [Depends(require_auth)]
    for (
        module
    ) in iter_route_modules():  # auto-discovered; see tit/server/routes/__init__.py
        name = module.__name__.rsplit(".", 1)[-1]
        router = getattr(module, "router", None)
        if router is not None:
            if name in OPEN_MODULES:
                app.include_router(router)
            else:
                app.include_router(router, dependencies=protected)
        ws_router = getattr(module, "ws_router", None)
        if ws_router is not None:
            app.include_router(ws_router)  # authorises inside the handshake
    app.include_router(ws.router)  # /ws/system, authorises inside the handshake
    app.include_router(static.router)  # catch-all, must be last

    app.openapi = lambda: _custom_openapi(app)  # type: ignore[method-assign]
    return app
