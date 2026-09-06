"""Serve the UI bundle at ``/`` (SPA fallback) or a minimal status page.

The bundle directory is checked on every request so a bundle built after
the server started is picked up without a restart.  Non-``/api``,
non-``/ws``, non-``/auth`` paths fall back to ``index.html``; the bundle
directory is a jail (resolved paths must stay inside it).  The status page
is unauthenticated, so it discloses nothing about the runtime.

V4 (``dev/notes/v3-native-panes-external-viewer-plan.md``): ``/tetravox/``, its
own CSP and the ``.wasm`` mimetype registration it needed are gone with the
embed.  This module serves one thing again -- the app bundle.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

logger = logging.getLogger(__name__)

router = APIRouter()

RESERVED_PREFIXES = ("api", "ws", "auth")

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


@router.get("/{path:path}", include_in_schema=False)
# HEAD isn't inferred from GET on an APIRoute (unlike a plain Starlette Route), so a plain GET
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
