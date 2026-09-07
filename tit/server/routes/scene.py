"""``/api/scene/*`` — the slim scene service the 3D panes read (plan §2).

Decision S1: this is a **form control's** data source, not a viewer's. It
serves exactly four things — two translucent surfaces, an EEG net's electrode
positions, per-vertex atlas labels, and a label volume's legend — so a user
can *choose* electrodes (Simulator), a target (Optimizer) or an ROI
(Analyzer). Volume slicing, colormaps, field overlays and screenshots are
Tetravox's job on the Viewer page and are deliberately not here.

Decision S2 in three rules, each with the failure it prevents:

* **The server extracts; the browser never sees the mesh.** ``ernie.msh`` is
  184 MB. What crosses the wire is 1.4 MB of skin and 2.6 MB of grey matter.
* **Everything is cached under ``derivatives/ti-toolbox/scene_cache/``**,
  keyed by a fingerprint of its source files (:mod:`tit.scene.cache`), so the
  second pane open is a file read. ``X-Scene-Build-Ms`` reports what the
  artifact being served cost to build and ``X-Scene-Cache: hit|miss`` says
  whether *this* request paid it.
* **A cold request answers 202 + ``Retry-After``, it does not hold the
  connection.** A build takes seconds; a held request looks like a hung app,
  and a proxy or a browser may drop it before it finishes. The build runs on a
  background thread under a per-subject lock, and the client polls. Callers
  that want one deterministic call (tests, smoke, curl) pass ``wait=<seconds>``
  and get an explicit, capped block instead.

Every path is jailed the way :mod:`tit.server.routes.files` jails its own:
nothing here takes a path from the client at all. The only client-supplied
strings are a subject id, a part name, a net *file name* and an atlas id, and
each is checked against what the project actually contains
(:func:`tit.catalog.subject_ids`, :data:`tit.scene.build.PART_TAGS`,
``PathManager.list_eeg_caps``, ``MeshAtlasManager.list_atlases``) before it
reaches the filesystem -- a traversal segment can never survive a membership
test against a listed directory.
"""

from __future__ import annotations

import json
import os
import threading
import time
from urllib.parse import quote
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from tit import catalog
from tit.paths import get_path_manager, natural_key
from tit.scene import build, cache

router = APIRouter()

#: How long a client should wait before polling a 202'd scene payload again.
#: A surfaces build is 2-4 s warm-page-cache and up to ~12 s cold (decision
#: S8's budget), so one second is a poll the user's first paint can absorb
#: without hammering the server.
RETRY_AFTER_S = 1

#: Upper bound on the explicit ``?wait=`` block. Past this a caller is better
#: served by polling; the cap exists so a client cannot pin a worker thread.
MAX_WAIT_S = 60.0

#: Builds in flight, keyed by (project, subject, unit). The value is the
#: monotonic start time, so a stuck build can be reported rather than looking
#: like "not building" forever.
_IN_FLIGHT: dict[tuple[str, str, str], float] = {}
_IN_FLIGHT_GUARD = threading.Lock()

#: The last error a background build raised, so the *next* request can report
#: it instead of silently 202-ing forever (the failure mode this prevents: a
#: subject whose mesh is corrupt would otherwise poll for ever).
_LAST_ERROR: dict[tuple[str, str, str], str] = {}


def _pm():
    pm = get_path_manager()
    if not pm.project_dir:
        raise HTTPException(status_code=409, detail="No project directory is bound")
    return pm


#: How many ids "this project has no subject X" lists before it truncates. A
#: 404 detail is read by a person, and a group project can hold hundreds.
MAX_LISTED_SUBJECTS = 12


def _project_subject_ids(pm) -> list[str]:
    """Every id the app's own subject picker shows, in its order.

    The union :func:`tit.catalog.list_subjects` lists -- onboarded subjects
    *and* subjects whose raw data is only staged under ``sourcedata/`` --
    without paying for its per-subject simulation counts.
    """
    return sorted(
        set(catalog.subject_ids(pm)) | set(catalog.sourcedata_only_subject_ids(pm)),
        key=natural_key,
    )


def _no_such_subject(pm, subject: str) -> HTTPException:
    known = _project_subject_ids(pm)
    shown = ", ".join(known[:MAX_LISTED_SUBJECTS]) or "no subjects at all"
    if len(known) > MAX_LISTED_SUBJECTS:
        shown += f" (+{len(known) - MAX_LISTED_SUBJECTS} more)"
    return HTTPException(
        status_code=404,
        detail=f"This project has no subject {subject!r}. It has: {shown}.",
    )


def _scene_subject(pm, subject: str) -> str:
    """*subject* if a scene can be built for it, else a 404 saying what to run.

    Every route calls this first, so all six give one answer to a
    subject-level question. What it prevents, measured on Dataset 000 (lane
    SCC, ``docs/dev/HISTORY.md § 2026-09-04 (scene service)`` §6.3):

    * ``sub-102`` is listed by ``GET /api/catalog/subjects`` and by the app's
      Subjects table -- its DICOMs are staged under ``sourcedata/`` -- but not
      by :func:`tit.catalog.subject_ids`, which is deliberately the *onboarded*
      set. The old gate answered ``"Unknown subject: 102"``: true of the
      function, and false to a user looking straight at 102 in the picker.
    * Only ``manifest`` and ``surface`` ever looked for the head mesh, so for a
      subject with raw data and no ``m2m_``, ``electrodes`` blamed the net
      file, ``regions``/``labels`` blamed the atlas -- with the flourish of
      ``"raw has no cortical atlas 'DK40'; available: DK40, HCP_MMP1,
      a2009s"``, because "available" lists the atlas *names the toolbox knows*
      -- and ``volume-legend`` blamed the LUT. Each named a file that is
      missing only because the head model is.

    The order matters: the head model is what every payload here is derived
    from, so its absence is the answer whenever it is absent, and the catalog
    is consulted only to say *why* it is absent and what to run.
    """
    if not catalog.is_safe_name(subject):
        # The gate builds ``m2m_<id>/`` paths below; a separator or a ``..``
        # segment must never reach the filesystem (routes/files.py's rule).
        raise _no_such_subject(pm, subject)
    if os.path.isdir(pm.m2m(subject)):
        try:
            build.head_mesh_path(pm, subject)
        except build.SceneUnavailable as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return subject
    if subject in catalog.subject_ids(pm):
        raise HTTPException(
            status_code=404,
            detail=(
                f"{subject} has no head model yet: m2m_{subject}/ does not exist. "
                f"Run Pre-processing (charm) on {subject} to create it."
            ),
        )
    if subject in catalog.sourcedata_only_subject_ids(pm):
        raise HTTPException(
            status_code=404,
            detail=(
                f"{subject} has no head model yet: m2m_{subject}/ does not exist "
                f"and the only data staged for it is sourcedata/sub-{subject}/. "
                f"Run Pre-processing on {subject} -- convert the raw data, then "
                f"charm -- to create it."
            ),
        )
    raise _no_such_subject(pm, subject)


def _unit_key(pm, subject: str, unit: str) -> tuple[str, str, str]:
    return (str(pm.project_dir), subject, unit)


def _run_build(key: tuple[str, str, str], work: Callable[[], Any], lock) -> None:
    """Run one build unit under the per-subject lock, recording its outcome."""
    try:
        with lock:
            work()
        _LAST_ERROR.pop(key, None)
    except Exception as exc:  # noqa: BLE001 - reported to the next request
        _LAST_ERROR[key] = f"{type(exc).__name__}: {exc}"
    finally:
        with _IN_FLIGHT_GUARD:
            _IN_FLIGHT.pop(key, None)


def _ensure(
    pm,
    subject: str,
    unit: str,
    work: Callable[[], Any],
    ready: Callable[[], Any],
    wait: float,
) -> Any:
    """Cached artifact for *unit*, or ``None`` when the caller must retry.

    ``ready()`` returns the cached artifact or ``None``; ``work()`` builds it.
    A previous build's failure is re-raised as a 404/500 here rather than
    letting the client poll a unit that will never appear.
    """
    found = ready()
    if found is not None:
        return found

    key = _unit_key(pm, subject, unit)
    error = _LAST_ERROR.get(key)
    if error is not None:
        _LAST_ERROR.pop(key, None)
        raise HTTPException(status_code=500, detail=f"scene build failed: {error}")

    with _IN_FLIGHT_GUARD:
        already = key in _IN_FLIGHT
        if not already:
            _IN_FLIGHT[key] = time.monotonic()
    if not already:
        thread = threading.Thread(
            target=_run_build,
            args=(key, work, cache.subject_lock(pm.project_dir, subject)),
            name=f"scene-build:{subject}:{unit}",
            daemon=True,
        )
        thread.start()

    deadline = time.monotonic() + min(max(wait, 0.0), MAX_WAIT_S)
    while time.monotonic() < deadline:
        time.sleep(0.05)
        found = ready()
        if found is not None:
            return found
        if _LAST_ERROR.get(key) is not None:
            error = _LAST_ERROR.pop(key)
            raise HTTPException(status_code=500, detail=f"scene build failed: {error}")
    return None


def _building_response(payload: dict) -> Response:
    return JSONResponse(
        status_code=202,
        content=payload,
        headers={"retry-after": str(RETRY_AFTER_S), "x-scene-cache": "building"},
    )


def _surface_work(pm, subject: str) -> Callable[[], Any]:
    def work() -> Any:
        return build.build_surfaces(pm, subject)

    return work


def _surface_ready(pm, subject: str, part: str, fmt: str = "tvsc") -> Callable[[], Any]:
    fingerprint = build.surface_fingerprint(pm, subject)

    def ready() -> Any:
        return cache.find_cached(pm.project_dir, subject, part, fingerprint, fmt)

    return ready


def _labels_work(pm, subject: str, atlas: str) -> Callable[[], Any]:
    def work() -> Any:
        return build.build_labels(pm, subject, atlas)

    return work


def _labels_ready(pm, subject: str, atlas: str, fmt: str = "tvsc") -> Callable[[], Any]:
    key = build._labels_key(atlas)
    fingerprint = build.labels_fingerprint(pm, subject, atlas)

    def ready() -> Any:
        return cache.find_cached(pm.project_dir, subject, key, fingerprint, fmt)

    return ready


#: What ``?format=`` accepts on the two byte routes (decision E7).
#:
#: ``tvsc`` is the frozen compatibility payload from :mod:`tit.scene.tvsc`;
#: ``gii`` is GIfTI, which the **Tetravox embed** reads and which needs no
#: bespoke decoder on either side. Both are built from the same vertices and
#: triangles by one call to :func:`tit.scene.build.build_surfaces`.
#:
#: The default remains ``tvsc`` until the compatibility route is intentionally
#: retired: moving a default would change what existing clients receive from a
#: URL they already fetch.
def _scene_format(fmt: str) -> str:
    if fmt not in cache.FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown scene format {fmt!r}; expected one of "
                f"{', '.join(cache.FORMATS)}"
            ),
        )
    return fmt


def _known_atlas(pm, subject: str, atlas: str) -> str:
    """*atlas* if the subject has a cortical annotation for it, else 404."""
    if not build.annot_paths(pm, subject, atlas):
        available = sorted(
            a["id"] for a in (catalog.atlases(pm, subject, kind="cortical") or [])
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"{subject} has no cortical atlas {atlas!r}"
                + (f"; available: {', '.join(available)}" if available else "")
            ),
        )
    return atlas


# ── routes ───────────────────────────────────────────────────────────────────


@router.get(
    "/api/scene/manifest",
    summary="Everything one subject's scene pane can load, with cache state",
    responses={
        200: {"description": "the whole manifest; every surface part is cached"},
        202: {
            "description": "surfaces are still building; retry after Retry-After "
            "seconds (nets, atlases and volumes are already filled in)"
        },
    },
)
def manifest(
    subject: str = Query(...), wait: float = Query(0.0, ge=0.0, le=MAX_WAIT_S)
) -> Any:
    pm = _pm()
    _scene_subject(pm, subject)

    parts: list[dict] = []
    building = False
    built_ms = 0.0
    for part in build.PART_TAGS:
        found = _ensure(
            pm,
            subject,
            "surfaces",
            _surface_work(pm, subject),
            _surface_ready(pm, subject, part),
            wait,
        )
        if found is None:
            building = True
            continue
        meta = found.meta
        built_ms = max(built_ms, float(meta.get("build_ms", 0.0)))
        parts.append(
            {
                "id": part,
                "kind": "surface",
                "triangles": meta.get("triangles"),
                "vertices": meta.get("vertices"),
                "bytes": meta.get("bytes"),
                "fingerprint": meta.get("fingerprint"),
                "url": f"/api/scene/surface?subject={quote(subject, safe='')}&part={part}",
                "simplified": meta.get("simplified"),
                "within_budget": meta.get("within_budget"),
                "max_deviation_mm": meta.get("max_deviation_mm"),
                "bbox": meta.get("bbox"),
                "focus_bbox": meta.get("focus_bbox"),
            }
        )

    def _union(field: str) -> list[float] | None:
        box = None
        for entry in parts:
            other = entry.get(field)
            if not other:
                continue
            box = (
                other
                if box is None
                else [min(a, b) for a, b in zip(box[:3], other[:3])]
                + [max(a, b) for a, b in zip(box[3:], other[3:])]
            )
        return box

    bbox = _union("bbox")
    # S7's framing hint: everything at or above the grey matter's floor, so a
    # pane frames the head and lets the neck run off the bottom. `null` on a
    # cache entry written before builder version 2, which the fingerprint salt
    # makes unreachable -- the renderer falls back to `bbox` either way.
    focus = _union("focus_bbox")

    # Every url here is quoted: these ids come from file names on disk, and an
    # unquoted "&" or "#" in one would silently truncate the query the client
    # then sends back.
    subject_q = quote(subject, safe="")
    nets = [
        {
            "name": net["name"],
            "electrodes": net["n"],
            "url": f"/api/scene/electrodes?subject={subject_q}&net={quote(net['name'], safe='')}",
        }
        for net in (catalog.eeg_nets(pm, subject) or [])
    ]
    atlases = []
    for entry in catalog.atlases(pm, subject, kind="cortical") or []:
        atlas_id = entry["id"]
        hemispheres = sorted(build.annot_paths(pm, subject, atlas_id))
        if not hemispheres:
            continue  # listed as a builtin name, but this subject has no file
        atlases.append(
            {
                "id": atlas_id,
                "hemispheres": hemispheres,
                "regions": build.atlas_region_count(pm, subject, atlas_id),
                "url": f"/api/scene/regions?subject={subject_q}&atlas={quote(atlas_id, safe='')}",
            }
        )
    volumes = []
    labeling = pm.tissue_labeling(subject)
    if labeling and os.path.isfile(labeling):
        volumes.append(
            {
                "id": "labeling",
                "url": "/api/files/raw" + quote(labeling),
                "legend_url": f"/api/scene/volume-legend?subject={subject_q}&id=labeling",
            }
        )

    body = {
        "subject": subject,
        "space": "subject-ras",
        "bbox": bbox,
        "focus_bbox": focus,
        "parts": parts,
        "nets": nets,
        "atlases": atlases,
        "volumes": volumes,
        "cache": {
            "state": "building" if building else "ready",
            "built_ms": round(built_ms, 1),
        },
    }
    if building:
        return _building_response(body)
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers={
            "x-scene-build-ms": str(round(built_ms, 1)),
            "x-scene-cache": "hit",
        },
    )


@router.get(
    "/api/scene/surface",
    summary="One scene surface as TVSC1 or GIfTI bytes (202 + Retry-After while building)",
    response_class=Response,
    responses={
        200: {
            "description": "TVSC1 or GIfTI binary, per ?format",
            "content": {"application/octet-stream": {}},
        },
        202: {"description": "the cache is building; retry after Retry-After seconds"},
        304: {"description": "not modified (If-None-Match matched the ETag)"},
        400: {"description": "unknown ?format"},
    },
)
def surface(
    subject: str = Query(...),
    part: str = Query(...),
    format: str = Query("tvsc"),
    wait: float = Query(0.0, ge=0.0, le=MAX_WAIT_S),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
) -> Response:
    pm = _pm()
    fmt = _scene_format(format)
    _scene_subject(pm, subject)
    if part not in build.PART_TAGS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scene part {part!r}; expected one of {sorted(build.PART_TAGS)}",
        )
    found = _ensure(
        pm,
        subject,
        "surfaces",
        _surface_work(pm, subject),
        _surface_ready(pm, subject, part, fmt),
        wait,
    )
    if found is None:
        return _building_response(
            {"subject": subject, "part": part, "cache": {"state": "building"}}
        )
    return _payload_response(found, fmt, if_none_match)


@router.get(
    "/api/scene/labels",
    summary="Per-vertex region labels aligned to part 'gm', as TVSC1 or GIfTI bytes",
    response_class=Response,
    responses={
        200: {
            "description": "TVSC1 labels payload or a renderable GIfTI mesh with label data, per ?format",
            "content": {"application/octet-stream": {}},
        },
        202: {"description": "the cache is building; retry after Retry-After seconds"},
        304: {"description": "not modified (If-None-Match matched the ETag)"},
        400: {"description": "unknown ?format"},
    },
)
def labels(
    subject: str = Query(...),
    atlas: str = Query(...),
    format: str = Query("tvsc"),
    wait: float = Query(0.0, ge=0.0, le=MAX_WAIT_S),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
) -> Response:
    pm = _pm()
    fmt = _scene_format(format)
    _scene_subject(pm, subject)
    _known_atlas(pm, subject, atlas)
    found = _ensure(
        pm,
        subject,
        f"labels:{atlas}",
        _labels_work(pm, subject, atlas),
        _labels_ready(pm, subject, atlas, fmt),
        wait,
    )
    if found is None:
        return _building_response(
            {"subject": subject, "atlas": atlas, "cache": {"state": "building"}}
        )
    return _payload_response(found, fmt, if_none_match)


@router.get(
    "/api/scene/regions",
    summary="One atlas' legend plus the URL of its label payload for part 'gm'",
    responses={
        200: {"description": "the legend and the labels URL"},
        202: {
            "description": "the labels payload is still building; retry after "
            "Retry-After seconds"
        },
    },
)
def regions(
    subject: str = Query(...),
    atlas: str = Query(...),
    wait: float = Query(0.0, ge=0.0, le=MAX_WAIT_S),
) -> Any:
    pm = _pm()
    _scene_subject(pm, subject)
    _known_atlas(pm, subject, atlas)
    found = _ensure(
        pm,
        subject,
        f"labels:{atlas}",
        _labels_work(pm, subject, atlas),
        _labels_ready(pm, subject, atlas),
        wait,
    )
    url = (
        f"/api/scene/labels?subject={quote(subject, safe='')}"
        f"&atlas={quote(atlas, safe='')}"
    )
    if found is None:
        return _building_response(
            {
                "atlas": atlas,
                "subject": subject,
                "url": url,
                "legend": [],
                "cache": {"state": "building"},
            }
        )
    meta = found.meta
    return Response(
        content=json.dumps(
            {
                "atlas": atlas,
                "subject": subject,
                "aligned_to": meta.get("aligned_to", "gm"),
                "vertices": meta.get("vertices"),
                "radius_mm": meta.get("radius_mm"),
                "labelled_fraction": meta.get("labelled_fraction"),
                "legend": meta.get("legend", []),
                "url": url,
                "cache": {"state": "ready", "built_ms": meta.get("build_ms")},
            }
        ),
        media_type="application/json",
        headers={
            "x-scene-build-ms": str(meta.get("build_ms", 0)),
            "x-scene-cache": "hit",
        },
    )


@router.get(
    "/api/scene/electrodes",
    summary="One EEG net's electrode positions in the surfaces' world space",
)
def electrodes(subject: str = Query(...), net: str = Query(...)) -> dict:
    pm = _pm()
    _scene_subject(pm, subject)
    if net not in pm.list_eeg_caps(subject):
        raise HTTPException(
            status_code=404, detail=f"{subject} has no EEG net file {net!r}"
        )
    try:
        return build.read_net(pm, subject, net)
    except build.SceneUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/api/scene/volume-legend",
    summary="The label volume's id -> name/colour legend",
)
def volume_legend(subject: str = Query(...), id: str = Query("labeling")) -> dict:
    pm = _pm()
    _scene_subject(pm, subject)
    try:
        return build.volume_legend(pm, subject, id)
    except build.SceneUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _payload_response(
    found: cache.CachedArtifact, fmt: str, if_none_match: str | None
) -> Response:
    """Serve one cached payload with its fingerprint as the ETag.

    ``must-revalidate`` rather than a long ``max-age``: the URL carries no
    fingerprint, so the same URL legitimately changes content after a charm
    re-run. A revalidation is one 304 round trip; a stale cached surface is a
    pane drawn from a head model the user replaced.

    **The format is part of the ETag.** One key and one fingerprint now name
    two payloads (``tvsc`` and ``gii``), and an ETag that named only the key
    would answer a ``format=gii`` request that carries the ``tvsc`` ETag with a
    304 — the client would then parse TVSC1 bytes it already had as GIfTI, or,
    worse, keep drawing them and never notice.
    """
    meta = found.meta
    etag = '"%s-%s-%s"' % (meta.get("key", "scene"), meta.get("fingerprint", "0"), fmt)
    headers = {
        "etag": etag,
        "cache-control": "private, max-age=0, must-revalidate",
        "x-content-type-options": "nosniff",
        "x-scene-build-ms": str(meta.get("build_ms", 0)),
        "x-scene-cache": "hit",
        "x-scene-vertices": str(meta.get("vertices", 0)),
        "x-scene-triangles": str(meta.get("triangles", 0)),
    }
    if if_none_match and etag in [p.strip() for p in if_none_match.split(",")]:
        return Response(status_code=304, headers=headers)
    return Response(
        content=found.path.read_bytes(),
        media_type="application/octet-stream",
        headers=headers,
    )
