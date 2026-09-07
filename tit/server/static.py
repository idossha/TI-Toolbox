"""Serve the UI bundle at ``/`` (SPA fallback) or a minimal status page.

The bundle directory is checked on every request so a bundle built after
the server started is picked up without a restart.  Non-``/api``,
non-``/ws``, non-``/auth`` paths fall back to ``index.html``; the bundle
directory is a jail (resolved paths must stay inside it).  The status page
is unauthenticated, so it discloses nothing about the runtime.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from tit.tetravox.store import active_embed_dir

logger = logging.getLogger(__name__)

router = APIRouter()

# The viewer's WASM module is instantiated with WebAssembly.instantiateStreaming,
# which rejects anything but application/wasm. Python 3.11 already maps .wasm,
# but older interpreters (and a host with a thin /etc/mime.types) do not, so
# register it explicitly rather than depend on the runtime's table.
mimetypes.add_type("application/wasm", ".wasm")

RESERVED_PREFIXES = ("api", "ws", "auth", "tetravox")

# The embed's own CSP (D1/D3, docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)): distinct from the app's
# main CSP_HEADER in tit/server/app.py (which drops 'wasm-unsafe-eval' now that the embed carries
# its own) -- 'wasm-unsafe-eval' for the engine's Rust->WASM module, 'blob:' for its dataset
# workers, no 'frame-src'/'object-src' entries the embed itself has no use for.
TETRAVOX_CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
    "worker-src 'self' blob:; connect-src 'self'; img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'"
)

STATUS_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>tit.server</title>
<style>body{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#222}</style></head>
<body><p>TI-Toolbox job server is running; no UI bundle at <code>--static-dir</code>;
see logs.</p></body></html>
"""

_warned_no_bundle = False


def status_page(static_dir: str | None) -> HTMLResponse:
    global _warned_no_bundle
    if not _warned_no_bundle:
        logger.warning(
            "No UI bundle at --static-dir=%s; serving the status page",
            static_dir or "-",
        )
        _warned_no_bundle = True
    return HTMLResponse(STATUS_PAGE)


def resolve_static_file(static_dir: str, path: str) -> Path | None:
    """File under *static_dir* for *path*, or ``None`` (missing / escapes the jail)."""
    root = Path(static_dir).resolve()
    candidate = (root / path).resolve() if path else root / "index.html"
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


def resolve_tetravox_file(embed_dir: str, path: str) -> Path | None:
    """File under *embed_dir* for *path* (``""``/``"index.html"`` -> ``index.html``).

    Unlike :func:`resolve_static_file` this is **not** a SPA fallback: an
    unknown asset path 404s rather than serving ``index.html``, because the
    embed bundle is a fixed set of files (JS/WASM chunks, the manifest), not
    a client-routed app that needs deep-link fallback.
    """
    root = Path(embed_dir).resolve()
    target = "index.html" if path in ("", "index.html") else path
    candidate = (root / target).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


def _tetravox_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _active_embed_dir(request: Request) -> str:
    """The bundle directory ``/tetravox/`` serves right now, or 404.

    Resolved **per request** (E2: dev override -> pinned/newest installed ->
    the version baked into the image), so a bundle installed through
    ``POST /api/tetravox/install`` is served immediately -- the same reason the
    static bundle directory is re-checked on every request rather than cached at
    startup.  A server restart to pick up a viewer update would defeat the whole
    point of installing one at runtime.
    """
    embed_dir = active_embed_dir(getattr(request.app.state, "settings", None))
    if not embed_dir or not os.path.isdir(embed_dir):
        raise HTTPException(status_code=404, detail="Tetravox embed not installed")
    return embed_dir


def _tetravox_response(embed_dir: str, path: str) -> Response:
    target = resolve_tetravox_file(embed_dir, path)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        target,
        media_type=_tetravox_media_type(target),
        headers={"content-security-policy": TETRAVOX_CSP},
    )


@router.get("/tetravox", include_in_schema=False)
@router.get("/tetravox/", include_in_schema=False)
# HEAD isn't inferred from GET on an APIRoute (unlike a plain Starlette Route), so `curl -I` would
# otherwise 405 -- registered explicitly rather than left to fall through. FileResponse already
# answers a HEAD request with headers only and no body (`starlette.responses.FileResponse.__call__`
# checks `scope["method"]`), so this needs no separate handler.
@router.head("/tetravox", include_in_schema=False)
@router.head("/tetravox/", include_in_schema=False)
def tetravox_index(request: Request) -> Response:
    return _tetravox_response(_active_embed_dir(request), "")


@router.get("/tetravox/{path:path}", include_in_schema=False)
@router.head("/tetravox/{path:path}", include_in_schema=False)
def tetravox_asset(path: str, request: Request) -> Response:
    return _tetravox_response(_active_embed_dir(request), path)


@router.get("/{path:path}", include_in_schema=False)
# Same APIRoute HEAD-inference gap as /tetravox/ above (R2 item 7): a plain GET decorator alone
# leaves `curl -I /` 405ing. FileResponse (the bundle path) and HTMLResponse (the status page)
# both already answer HEAD with headers only and no body, so no separate handler is needed.
@router.head("/{path:path}", include_in_schema=False)
def serve(path: str, request: Request) -> Response:
    first = path.split("/", 1)[0]
    if first in RESERVED_PREFIXES:
        raise HTTPException(status_code=404, detail="Not found")
    static_dir = request.app.state.settings.static_dir
    if static_dir and os.path.isdir(static_dir):
        target = resolve_static_file(static_dir, path)
        if target is None:
            target = resolve_static_file(static_dir, "index.html")
        if target is None:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(target)
    return status_page(static_dir)
