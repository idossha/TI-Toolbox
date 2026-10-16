"""``/api/caps/*`` -- EEG caps on an existing head model (the optional EEG caps panel).

Synchronous on purpose, not a job: warping one cap onto ``sub-ernie`` takes
2.4 s and reading + cropping the head mesh 0.8 s (measured in the container,
2026-10-16), so a request is the honest unit (``docs/dev/DECISIONS.md`` §
2026-10-16). Science lives in :mod:`tit.caps`; this module only checks names,
confines paths to the project and maps errors to status codes.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from tit import caps as caps_core
from tit.paths import get_path_manager, resolve_within
from tit.scene import build
from tit.server.routes.scene import _scene_subject
from tit.server.schemas import EntityName, SubjectId

router = APIRouter()

#: ponytail: one lock for every warp in this process -- warps are seconds
#: long and rare; per-subject locks if two users ever warp at once.
_WARP_LOCK = threading.Lock()


class WarpRequest(BaseModel):
    subject: SubjectId
    caps: list[EntityName] = Field(min_length=1)
    overwrite: bool = False


def _confined(pm, path: str) -> str:
    try:
        return resolve_within(pm.project_dir, path)
    except ValueError as exc:
        raise HTTPException(403, "EEG cap folder resolves outside the project") from exc


@router.get(
    "/api/caps/available",
    summary="MNI caps that can be warped, and the nets on a subject",
)
def available(subject: Annotated[SubjectId, Query()]) -> dict:
    pm = get_path_manager()
    _scene_subject(pm, subject)
    return {"subject": subject, "caps": caps_core.available_caps(pm, subject)}


@router.post(
    "/api/caps/warp",
    summary="Warp MNI caps onto a subject's head model, as charm does",
    responses={409: {"description": "A named cap is already on the subject"}},
)
def warp(body: WarpRequest) -> dict:
    pm = get_path_manager()
    subject = body.subject
    _scene_subject(pm, subject)
    sources = caps_core.source_caps(pm)
    unknown = [name for name in body.caps if name not in sources]
    if unknown:
        raise HTTPException(404, f"No MNI cap named {', '.join(unknown)}")
    out_dir = _confined(pm, pm.eeg_positions(subject))
    existing = sorted(set(body.caps) & set(pm.list_eeg_caps(subject)))
    if existing and not body.overwrite:
        raise HTTPException(
            409,
            f"{len(existing)} of these caps are already on {subject} "
            f"({', '.join(existing)}); confirm overwrite to replace them.",
        )
    m2m = _confined(pm, pm.m2m(subject))
    with _WARP_LOCK:
        try:
            written = caps_core.warp_caps(
                m2m, subject, [sources[name][1] for name in body.caps], out_dir
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(422, f"Could not warp the cap: {exc}") from exc
    return {"subject": subject, "written": written}


@router.post(
    "/api/caps/upload",
    status_code=201,
    summary="Add an MNI-space cap CSV to the project's own caps",
    responses={
        409: {"description": "The name is taken"},
        413: {"description": "Cap file exceeds the size limit"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
)
async def upload(
    request: Request,
    name: Annotated[EntityName, Query()],
    overwrite: Annotated[bool, Query()] = False,
) -> dict:
    if not name.endswith(".csv"):
        raise HTTPException(422, "The cap file name must end in .csv")
    pm = get_path_manager()
    if caps_core.source_caps(pm).get(name, ("project",))[0] == "simnibs":
        raise HTTPException(
            409, f"{name} is a cap the image already ships; rename the file"
        )
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > caps_core.MAX_CAP_BYTES:
            raise HTTPException(413, "Cap file exceeds 256 KiB")
    try:
        electrodes = caps_core.validate_mni_cap(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "The cap file is not UTF-8 text") from exc
    except caps_core.CapError as exc:
        raise HTTPException(422, str(exc)) from exc
    directory = _confined(pm, pm.custom_eeg_caps())
    os.makedirs(directory, exist_ok=True)
    target = Path(directory) / name
    if target.exists() and not overwrite:
        raise HTTPException(409, f"The project already has a cap named {name}")
    with tempfile.NamedTemporaryFile(
        dir=directory, prefix=".upload-", delete=False
    ) as tmp:
        tmp.write(bytes(data))
    os.replace(tmp.name, target)
    return {"name": name, "electrodes": electrodes}


def _net_points(pm, subject: str, net: str) -> tuple[list[str], np.ndarray]:
    if net not in pm.list_eeg_caps(subject):
        raise HTTPException(404, f"{subject} has no EEG net file {net!r}")
    try:
        parsed = build.read_net(pm, subject, net)
    except build.SceneUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    rows = parsed["electrodes"] + parsed["reference"]
    world = np.asarray([r["world"] for r in rows], dtype=np.float64).reshape(-1, 3)
    return [r["name"] for r in rows], world


@router.get(
    "/api/caps/inspect",
    summary="Spacing, scalp distance and collapsed electrodes of one net",
)
def inspect(
    subject: Annotated[SubjectId, Query()],
    net: Annotated[EntityName, Query()],
    compare: Annotated[EntityName | None, Query()] = None,
) -> dict:
    pm = get_path_manager()
    _scene_subject(pm, subject)
    names, world = _net_points(pm, subject, net)
    mesh = build.head_mesh_path(pm, subject)
    try:
        skin = caps_core.skin_nodes(str(mesh))
    except (OSError, ValueError, RuntimeError):
        skin = None  # the table still answers spacing; scalp distance is blank
    result = {"subject": subject, "net": net, **caps_core.net_stats(names, world, skin)}
    result["compare"] = None
    if compare:
        names_b, world_b = _net_points(pm, subject, compare)
        nearest = caps_core.compare_nets(world, names_b, world_b)
        for row, match in zip(result["electrodes"], nearest):
            row["compare_name"] = match["name"]
            row["compare_mm"] = match["distance_mm"]
        distances = [m["distance_mm"] for m in nearest if m["distance_mm"] is not None]
        result["compare"] = {
            "net": compare,
            "electrodes": [
                {"name": n, "world": [round(float(v), 3) for v in w]}
                for n, w in zip(names_b, world_b)
            ],
            "median_mm": round(float(np.median(distances)), 3) if distances else None,
            "max_mm": round(float(np.max(distances)), 3) if distances else None,
        }
    return result
