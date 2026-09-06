"""``GET /api/openapi.json`` — this server's own OpenAPI document, behind auth.

The app is built with ``openapi_url=None`` (``tit.server.app.create_app``): FastAPI's own
``/openapi.json`` and the ``/docs`` UI are unauthenticated by construction, and an unauthenticated
route map of a server that can start jobs on the user's machine is not something to publish. The
document itself is still worth serving -- a client (the smoke harness, a notebook, a future SDK)
should be able to ask a *live* server what routes and what ``JobKind``s it actually has instead of
reading a checked-in file that may be a release behind (`dev/notes/v3-pipelines/2026-09-03-smoke.md`
open issue 6). So the same document, at a path under ``/api`` that inherits the app's ``require_auth``
dependency like every other ``/api`` route.

Identical to ``python -m tit.server --dump-openapi <path>``: both call ``app.openapi()``, which is
``tit.server.app._custom_openapi`` (generated schema + the WebSocket routes FastAPI cannot describe
+ the config dataclass schemas + ``JobKind``), and FastAPI caches it on the app after the first call.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get(
    "/api/openapi.json",
    summary="This server's OpenAPI document (identical to --dump-openapi)",
)
def openapi_document(request: Request) -> dict[str, Any]:
    return request.app.openapi()
