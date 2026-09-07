"""Saved **compositions** and saved **scenes** — the Viewer's two kinds of "get this back".

Maintainer, 2026-09-07: *"At the end they could choose to save it as a JSON for future
reproducibility. Also we should be integrating scene saving where users can essentially save
scenes — not only the input selection but also the scene for the user — and we should be very
opinionated about that and save it in the Tetravox [scene format]."*

Those are two different artefacts and this module keeps them apart on purpose, because they answer
different questions and age differently:

**A composition** (``compositions/<slug>.json``) is *what a person chose*: a subject, a space, and
the inputs ticked in the Menu's tree, by stable id. It is small, it is diffable, and it survives a
re-run of the pipeline — reloading it next month re-resolves today's choices against whatever is on
disk then, and reports what has gone missing rather than failing. This is the reproducibility
artefact: "show me the same thing, from the current data".

**A scene** (``scenes/<slug>.tetravox.json``) is *what a person was looking at*: the embed's own
serialized ``ViewSpec`` — camera, layout, per-layer window, threshold, colormap, opacity, cursor —
after they had adjusted it. It names concrete files. This is the record artefact: "show me exactly
this picture again". It is written in the app's own format, suffix and all, so the standalone
Tetravox app opens it by double-click; a PNG thumbnail is written beside it under the same stem.

Both live in the project (``<project>/code/ti-toolbox/viewer/``) rather than in browser storage or a
home directory, for the reason the presets already do: the project is the unit people copy, archive
and hand on, and a saved view that did not travel with it would be lost exactly when the work it
describes was passed to someone else.

**Why the suffix is not negotiable.** ``.tetravox.json`` is what the Tetravox app classifies as a
scene; a file ending in anything else — the working name ``.tvx.json`` included — is classified as
*data* and the app tries to read the JSON as a volume, silently, at the last step
(``tit/server/routes/viewers.py``'s note on ``_SCENE_SUFFIX``). This module refuses to write a scene
under any other suffix rather than trust a caller to remember that.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from tit import viewspec
from tit.server.routes.viewers import _SCENE_SUFFIX, viewer_scene_dir

router = APIRouter()

_COMPOSITION_SUFFIX = ".json"

#: The biggest thumbnail we will store, in decoded bytes. A Tetravox `screenshot` of a 2x2 grid at
#: the default size is ~200-400 KB of PNG; 4 MB is generous headroom and still small enough that a
#: project directory does not quietly become a photo album.
_MAX_THUMBNAIL_BYTES = 4 * 1024 * 1024

#: A scene document is a `ViewSpec`, which for a big montage can carry a few hundred layers and
#: points. Well above anything real, and a bound rather than none at all.
_MAX_SCENE_BYTES = 32 * 1024 * 1024


def composition_dir() -> str:
    return os.path.join(viewer_scene_dir(), "compositions")


def saved_scene_dir() -> str:
    return os.path.join(viewer_scene_dir(), "scenes")


def _slug(name: str) -> str:
    """A file name from a display name, or a 422.

    Deliberately strict rather than sanitising, exactly like the preset routes next door: a name
    that quietly becomes a *different* file is worse than a refusal, because the person who saved
    it will look for the name they typed. Every character kept here is one they typed on purpose.
    """
    if not isinstance(name, str):
        raise HTTPException(status_code=422, detail="A name must be a string")
    # A path separator is refused rather than replaced. Turning `reports/june` into `reports-june`
    # keeps the file inside this directory, but it also means the person who typed a path gets a
    # file under a name they did not choose and cannot find -- which is exactly the failure this
    # function's strictness exists to avoid.
    if "/" in name or "\\" in name:
        raise HTTPException(
            status_code=422, detail=f"A name cannot contain a path separator: {name!r}"
        )
    slug = "".join(c if (c.isalnum() or c in "-_ .") else "-" for c in name).strip()
    slug = slug.replace(" ", "_")
    # `..` in any form is a traversal, and a leading dot hides the file from the person who made it.
    if not slug or slug.startswith(".") or ".." in slug or len(slug) > 80:
        raise HTTPException(status_code=422, detail=f"Unusable name: {name!r}")
    return slug


def _write_json(target: str, document: dict[str, Any]) -> None:
    """Whole, then renamed — a reader must never parse half a document."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.{os.getpid()}.partial"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1)
    os.replace(tmp, target)


def _read_json(path: str) -> dict[str, Any] | None:
    """The document, or ``None`` for anything unreadable.

    A hand-edited or half-written file is skipped, never fatal: one bad file must not empty a list
    the person is using to find their work.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            body = json.load(handle)
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── the composition tree ─────────────────────────────────────────────────────


@router.get("/api/viewer/tree", summary="What one subject offers the Menu's composition tree")
def viewer_tree(
    subject: str | None = Query(None),
    space: str | None = Query(None),
    simulations: list[str] | None = Query(None),
) -> dict[str, Any]:
    """Anatomy, simulations and analyses for *subject*, as the Menu draws them.

    *simulations* repeats (``?simulations=a&simulations=b``) and says which ones are expanded, so
    analyses are listed only for those. Everything is `os.listdir` and `os.stat`; no voxel is read,
    because this is redrawn as a person clicks.
    """
    return viewspec.viewer_tree(subject, space, list(simulations) if simulations else None)


# ── compositions ─────────────────────────────────────────────────────────────


@router.get("/api/viewer/compositions", summary="Saved Viewer compositions")
def list_compositions() -> dict[str, Any]:
    directory = composition_dir()
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        names = []
    out: list[dict[str, Any]] = []
    for entry in names:
        if not entry.endswith(_COMPOSITION_SUFFIX):
            continue
        body = _read_json(os.path.join(directory, entry))
        if body is None:
            continue
        body.setdefault("name", entry[: -len(_COMPOSITION_SUFFIX)])
        out.append(body)
    return {"compositions": out}


@router.put("/api/viewer/compositions/{name}", summary="Save one Viewer composition")
def save_composition(name: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
    """Store *body* as this composition.

    The shape is the client's — a subject, a space and the chosen input ids — and this route does
    not validate it beyond "it is an object". That is deliberate: the tree's vocabulary is going to
    grow, and a server that rejected an unknown key would make every Menu change a two-repository
    change. What it does own is the *name*, the timestamp and the atomic write.
    """
    document = dict(body or {})
    document["name"] = name
    document["saved_at"] = _now()
    document.setdefault("version", 1)
    _write_json(os.path.join(composition_dir(), f"{_slug(name)}{_COMPOSITION_SUFFIX}"), document)
    return document


@router.delete("/api/viewer/compositions/{name}", summary="Forget one composition")
def delete_composition(name: str) -> dict[str, Any]:
    target = os.path.join(composition_dir(), f"{_slug(name)}{_COMPOSITION_SUFFIX}")
    try:
        os.remove(target)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No composition named {name!r}")
    return {"name": name, "deleted": True}


# ── saved scenes ─────────────────────────────────────────────────────────────


def _thumbnail_bytes(data_url: Any) -> bytes | None:
    """The PNG bytes of a ``data:image/png;base64,…`` URL, or ``None``.

    The embed's ``screenshot`` reply is a data URL (``EMBED.md`` §6), so that is what the client
    has to hand and what this accepts. Anything else — another image type, a bare URL, something
    over the size cap — is dropped rather than refused: a scene worth keeping is still worth
    keeping without its picture.
    """
    if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
        return None
    payload = data_url.split(",", 1)[1] if "," in data_url else ""
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError):
        return None
    if not raw or len(raw) > _MAX_THUMBNAIL_BYTES:
        return None
    # A real PNG, not just something that decoded. Refusing to write bytes we have not identified
    # keeps this route from being a way to drop arbitrary files into someone's project.
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return raw


@router.get("/api/viewer/scenes", summary="Saved Tetravox scenes")
def list_scenes() -> dict[str, Any]:
    """Every saved scene, newest first, with whether it has a thumbnail.

    The scene documents themselves are not returned — one is megabytes and the Menu only needs to
    draw a row. `GET /api/viewer/scenes/{name}` is the read.
    """
    directory = saved_scene_dir()
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        names = []
    out: list[dict[str, Any]] = []
    for entry in names:
        if not entry.endswith(_SCENE_SUFFIX):
            continue
        stem = entry[: -len(_SCENE_SUFFIX)]
        path = os.path.join(directory, entry)
        try:
            st = os.stat(path)
        except OSError:
            continue
        meta = _read_json(os.path.join(directory, f"{stem}.meta.json")) or {}
        out.append(
            {
                "name": meta.get("name", stem),
                "slug": stem,
                "path": path,
                "bytes": st.st_size,
                "saved_at": meta.get("saved_at"),
                "subject": meta.get("subject"),
                "simulation": meta.get("simulation"),
                "field": meta.get("field"),
                "has_thumbnail": os.path.isfile(os.path.join(directory, f"{stem}.png")),
            }
        )
    out.sort(key=lambda row: (row.get("saved_at") or "", row["slug"]), reverse=True)
    return {"scenes": out}


@router.get("/api/viewer/scenes/{name}", summary="One saved scene document")
def read_scene(name: str) -> dict[str, Any]:
    target = os.path.join(saved_scene_dir(), f"{_slug(name)}{_SCENE_SUFFIX}")
    body = _read_json(target)
    if body is None:
        raise HTTPException(status_code=404, detail=f"No saved scene named {name!r}")
    return {"name": name, "path": target, "scene": body}


@router.put(
    "/api/viewer/scenes/{name}",
    summary="Save the scene the viewer is showing",
    # Declared rather than merely raised: `dev/contracts_check.py` holds the server's own OpenAPI
    # to being a superset of `contracts/openapi.yaml`, and a status a client is told to expect but
    # the document never mentions is exactly the drift that gate exists to catch.
    responses={413: {"description": "Scene document is implausibly large"}},
)
def save_scene(name: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
    """Write *body*'s ``scene`` as ``scenes/<slug>.tetravox.json``, plus a thumbnail and metadata.

    ``scene`` is the embed's own ``serialize`` reply — the live ``ViewSpec``, with the camera the
    person left it at and every layer's current window. It is written **verbatim**: the whole point
    of saving a scene rather than a composition is that it is a record of a picture, and a server
    that re-derived any part of it would be recording something else.

    Three files share one stem, so a person moving the scene knows what belongs with it:
    ``<slug>.tetravox.json`` (the app opens this), ``<slug>.png`` (the Menu's row), and
    ``<slug>.meta.json`` (what it was of, and when).
    """
    payload = dict(body or {})
    scene = payload.get("scene")
    if not isinstance(scene, dict) or not scene.get("layers"):
        raise HTTPException(
            status_code=422,
            detail="A scene must be the embed's serialized ViewSpec, with at least one layer",
        )
    encoded = json.dumps(scene)
    if len(encoded.encode("utf-8")) > _MAX_SCENE_BYTES:
        raise HTTPException(status_code=413, detail="Scene document is implausibly large")

    slug = _slug(name)
    directory = saved_scene_dir()
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, f"{slug}{_SCENE_SUFFIX}")
    _write_json(target, scene)

    thumbnail = _thumbnail_bytes(payload.get("thumbnail"))
    thumb_path = os.path.join(directory, f"{slug}.png")
    if thumbnail is not None:
        tmp = f"{thumb_path}.{os.getpid()}.partial"
        with open(tmp, "wb") as handle:
            handle.write(thumbnail)
        os.replace(tmp, thumb_path)

    meta = {
        "name": name,
        "slug": slug,
        "saved_at": _now(),
        "subject": payload.get("subject"),
        "simulation": payload.get("simulation"),
        "field": payload.get("field"),
        "space": payload.get("space"),
    }
    _write_json(os.path.join(directory, f"{slug}.meta.json"), meta)

    from tit.server.host_path import host_project_dir
    from tit.paths import get_path_manager

    container_root = get_path_manager().project_dir or ""
    host_root = host_project_dir(container_root)
    host_path = None
    if host_root and container_root and target.startswith(container_root):
        host_path = os.path.join(host_root, os.path.relpath(target, container_root))

    return {
        **meta,
        "path": target,
        "host_path": host_path,
        "has_thumbnail": thumbnail is not None,
        "bytes": len(encoded.encode("utf-8")),
    }


@router.delete("/api/viewer/scenes/{name}", summary="Forget one saved scene")
def delete_scene(name: str) -> dict[str, Any]:
    slug = _slug(name)
    directory = saved_scene_dir()
    target = os.path.join(directory, f"{slug}{_SCENE_SUFFIX}")
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail=f"No saved scene named {name!r}")
    for path in (target, os.path.join(directory, f"{slug}.png"), os.path.join(directory, f"{slug}.meta.json")):
        try:
            os.remove(path)
        except OSError:
            # The thumbnail and the metadata are optional; only the scene had to exist.
            pass
    return {"name": name, "deleted": True}


#: Characters a default scene name may carry. Everything else becomes `-`, matching `_slug`.
_DEFAULT_NAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@router.get("/api/viewer/scenes/suggest/name", summary="A default name for a new scene")
def suggest_scene_name(
    subject: str | None = Query(None),
    simulation: str | None = Query(None),
    field: str | None = Query(None),
) -> dict[str, Any]:
    """``<subject>_<sim>_<field>_<date>`` — what the Save field is pre-filled with.

    Server-side so the name a scene gets does not depend on which client saved it, and so the
    date is the project's clock rather than a browser's.
    """
    parts = [p for p in (subject, simulation, field) if p]
    parts.append(datetime.now(timezone.utc).strftime("%Y%m%d"))
    name = _DEFAULT_NAME_SAFE.sub("-", "_".join(str(p) for p in parts)).strip("-_") or "scene"
    return {"name": name[:80]}
