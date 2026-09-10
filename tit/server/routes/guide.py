"""``/api/guide/*`` — the fixed, packaged guide scene (plan R4).

The shape mirrors ``/api/scene/*`` on purpose, minus everything that made the
scene routes *project* routes: there is no ``subject`` parameter, no cache
state, no 202, no build. Every answer here is a read of a file that shipped
with the installation (:mod:`tit.scene.guide`), so the pane paints on a
machine with no project bound, no head model built, and no subject selected.

Three rules, each with the failure it prevents:

* **No client string ever reaches the filesystem.** ``part``, ``atlas`` and
  ``net`` are checked against the packaged manifest's own ids before anything
  is opened, and the manifest's relative paths are resolved back inside the
  package directory. A traversal segment cannot survive a membership test
  against a list the server wrote itself.
* **The payloads are immutable, so they are cached hard.** ``ETag`` is the
  file's SHA-256 out of the manifest and ``Cache-Control`` is a year: unlike a
  subject's surface, this URL's content cannot change under a client without
  the installation itself changing.
* **The space is ``guide-ras``, and it is in every response.** A consumer that
  mistakes it for a research subject's RAS writes a silently wrong coordinate;
  saying so on the wire is what lets the desktop pane disable click-to-config
  instead of trusting a comment.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response

from tit.scene import guide

router = APIRouter()

#: Immutable payload, content-addressed by ETag: a year, publicly cacheable.
IMMUTABLE_CACHE_CONTROL = "private, max-age=31536000, immutable"


def _unavailable(exc: guide.GuideUnavailable) -> HTTPException:
    """A missing packaged guide is a 404 with the sentence the user needs.

    Not a 500: nothing went wrong at request time. The installation is
    incomplete, and the message says how to complete it.
    """
    return HTTPException(status_code=404, detail=str(exc))


def _manifest() -> dict[str, Any]:
    try:
        return guide.manifest()
    except guide.GuideUnavailable as exc:
        raise _unavailable(exc) from exc


def _format(fmt: str) -> str:
    if fmt not in ("tvsc", "gii"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown guide format {fmt!r}; expected 'tvsc' or 'gii'",
        )
    return fmt


def _bytes_response(asset: guide.GuideAsset, if_none_match: str | None) -> Response:
    etag = f'"{asset.sha256}"'
    headers = {
        "etag": etag,
        "cache-control": IMMUTABLE_CACHE_CONTROL,
        "x-content-type-options": "nosniff",
        "x-guide-version": str(guide.GUIDE_VERSION),
        "x-scene-vertices": str(asset.meta.get("vertices", 0)),
        "x-scene-triangles": str(asset.meta.get("triangles", 0)),
    }
    if if_none_match and etag in [p.strip() for p in if_none_match.split(",")]:
        return Response(status_code=304, headers=headers)
    return Response(
        content=asset.path.read_bytes(),
        media_type="application/octet-stream",
        headers=headers,
    )


def _json_response(body: Any) -> Response:
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers={
            "cache-control": IMMUTABLE_CACHE_CONTROL,
            "x-guide-version": str(guide.GUIDE_VERSION),
        },
    )


@router.get(
    "/api/guide/manifest",
    summary="Everything the fixed guide scene contains (no subject, no build, no cache state)",
)
def manifest() -> Any:
    """The packaged manifest, minus the per-file bookkeeping a client never uses.

    ``files``/``*_meta``/``sha256`` describe the *package* (the gate test reads
    them off disk); what crosses the wire is the same shape the scene manifest
    has, so one pane component can consume either.
    """
    body = _manifest()
    parts = [
        {k: v for k, v in part.items() if k != "files"}
        for part in body.get("parts", [])
    ]
    atlases = [
        {
            k: v
            for k, v in atlas.items()
            if k not in ("files", "legend_file", "legend_meta")
        }
        for atlas in body.get("atlases", [])
    ]
    nets = [
        {k: v for k, v in net.items() if k not in ("file", "sha256", "bytes")}
        for net in body.get("nets", [])
    ]
    return _json_response(
        {
            "guide": body.get("guide", {}),
            "guide_version": body.get("guide_version", guide.GUIDE_VERSION),
            "space": body.get("space", guide.GUIDE_SPACE),
            "bbox": body.get("bbox"),
            "focus_bbox": body.get("focus_bbox"),
            "parts": parts,
            "nets": nets,
            "atlases": atlases,
            "volumes": body.get("volumes", []),
            "provenance": body.get("provenance", {}),
            "cache": {"state": "ready", "built_ms": 0.0},
        }
    )


@router.get(
    "/api/guide/surface",
    summary="One packaged guide surface as TVSC1 or GIfTI bytes",
    response_class=Response,
    responses={
        200: {
            "description": "TVSC1 or GIfTI binary, per ?format",
            "content": {"application/octet-stream": {}},
        },
        304: {"description": "not modified (If-None-Match matched the ETag)"},
        400: {"description": "unknown ?format"},
        404: {"description": "no such packaged part, or the guide is not installed"},
    },
)
def surface(
    part: str = Query(...),
    format: str = Query("tvsc"),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
) -> Response:
    fmt = _format(format)
    try:
        asset = guide.surface(part, fmt)
    except guide.GuideUnavailable as exc:
        raise _unavailable(exc) from exc
    return _bytes_response(asset, if_none_match)


@router.get(
    "/api/guide/labels",
    summary="One packaged atlas' grey-matter surface with per-vertex labels",
    response_class=Response,
    responses={
        200: {
            "description": "GIfTI binary with a label array and label table",
            "content": {"application/octet-stream": {}},
        },
        304: {"description": "not modified"},
        400: {"description": "unknown ?format"},
        404: {"description": "no such packaged atlas, or the guide is not installed"},
    },
)
def labels(
    atlas: str = Query(...),
    format: str = Query("gii"),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
) -> Response:
    fmt = _format(format)
    try:
        asset = guide.labels(atlas, fmt)
    except guide.GuideUnavailable as exc:
        raise _unavailable(exc) from exc
    return _bytes_response(asset, if_none_match)


@router.get(
    "/api/guide/regions",
    summary="One packaged atlas' legend plus the URL of its label payload",
)
def regions(atlas: str = Query(...)) -> Any:
    try:
        body = guide.legend(atlas)
    except guide.GuideUnavailable as exc:
        raise _unavailable(exc) from exc
    return _json_response({**body, "cache": {"state": "ready", "built_ms": 0.0}})


@router.get(
    "/api/guide/electrodes",
    summary="One packaged EEG net's electrode positions in the guide's own space",
)
def electrodes(net: str = Query(...)) -> Any:
    try:
        return _json_response(guide.electrodes(net))
    except guide.GuideUnavailable as exc:
        raise _unavailable(exc) from exc
