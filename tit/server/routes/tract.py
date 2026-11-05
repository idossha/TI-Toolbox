"""``/api/tract/*`` — white-matter networks as targets for the optimizers.

Like :mod:`tit.server.routes.scene`, a **form control's** data source: no client path anywhere.
The only client strings are a subject id, region names and a mask name, each checked against what
the project holds. Requests name edges by **region pairs, never edge ids**, because ids renumber
when a network is rebuilt.

Writes follow ``POST /api/files/mask``: confined to the subject's mask folder, resolved through
the project jail, replaced in one step, and refused over an existing mask without ``overwrite``.

The streamlines route is the scene service's cold-cache grammar: one per-subject subsample is built
on a background thread (202 + ``Retry-After`` until then) and each request is a slice of it, so
changing the selection never costs another build.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from tit import catalog
from tit.scene import build, cache, tvsl
from tit.server.routes.scene import (
    _building_response,
    _ensure,
    _no_such_subject,
    _pm,
)
from tit.server.schemas import SubjectId

router = APIRouter()

#: How many edges one pane request may draw (the design budget: 64 × 100 streamlines).
MAX_EDGES = 64
#: ``AssessConfig.min_streamlines``: below this an edge is reported but not offered as a target.
DEFAULT_MIN_N = 5


RegionPair = Annotated[list[str], Field(min_length=2, max_length=2)]


class TractRegion(BaseModel):
    name: str
    cortical: bool


class TractManifest(BaseModel):
    available: bool
    qsiprep_available: bool
    tractogram_available: bool
    atlas: str | None = None
    n_streamlines: int | None = None
    n_edges: int | None = None
    frac_both_ends_assigned: float | None = None
    qc_passed: bool | None = None
    fingerprint: str | None = None
    regions: list[TractRegion] = []


class TractEdge(BaseModel):
    edge_id: int
    region_a: str
    region_b: str
    n: int
    share: float


class TractEdges(BaseModel):
    edges: list[TractEdge]


class TractMaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: SubjectId
    name: str
    pairs: list[RegionPair] = Field(min_length=1, max_length=5000)
    min_count: int = Field(default=1, ge=1)
    min_n: int = Field(default=DEFAULT_MIN_N, ge=1)
    overwrite: bool = False


class TractMask(BaseModel):
    name: str
    path: str
    fingerprint: str
    stale: bool
    pairs: list[RegionPair]
    min_count: int
    n_edges: int
    n_streamlines: int
    n_voxels: int
    volume_mm3: float


class TractMasks(BaseModel):
    masks: list[TractMask]


class TractRankingMontage(BaseModel):
    montage: list[str]
    median_sl_mean_ti_along: float
    pooled_mean_ti_along: float
    median_sl_mean_ti_max: float
    pooled_mean_ti_max: float
    median_sl_mean_ti_avg: float
    pooled_mean_ti_avg: float
    align_index: float
    rank_by_ti_along: int
    rank_by_ti_max: int


class TractRanking(BaseModel):
    name: str
    ex_run: str
    n_streamlines: int
    current_mA: list[float]
    n_points: int
    n_points_in_leadfield_mesh: int
    montages: list[TractRankingMontage]


class TractRankings(BaseModel):
    rankings: list[TractRanking]


def _subject(pm, subject: str) -> str:
    if not catalog.is_safe_name(subject) or subject not in catalog.subject_ids(pm):
        raise _no_such_subject(pm, subject)
    return subject


def _source(pm, path: str | Path) -> Path:
    """*path* inside the project with its links resolved, or 404."""
    resolved = build.source_path(pm, path)
    if resolved is None:
        raise HTTPException(404, "Tractography resolves outside the project")
    return resolved


def _network(pm, subject: str) -> dict[str, Any]:
    """``network.npz``, or the 404 sentence naming what to run."""
    path = _source(pm, Path(pm.tractography(subject)) / "network.npz")
    if not path.is_file():
        raise HTTPException(
            404,
            f"sub-{subject} has no network yet: {path.name} does not exist. "
            "Run the tract job's track and network stages first.",
        )
    with np.load(path, allow_pickle=False) as data:
        return {
            "names": [str(n) for n in data["names"]],
            "pairs": data["pairs"],
            "counts": data["counts"],
        }


def _pair_edges(network: dict[str, Any], pairs: list[list[str]]) -> list[int]:
    """Each pair's edge index, or 422 naming a region or pair the network does not have."""
    names = network["names"]
    index = {name: i for i, name in enumerate(names)}
    unknown = sorted({r for p in pairs for r in p if r not in index})
    if unknown:
        raise HTTPException(422, f"Unknown region(s): {', '.join(unknown[:8])}")
    edge_of = {tuple(p): e for e, p in enumerate(network["pairs"].tolist())}
    edges = []
    for a, b in pairs:
        key = tuple(sorted((index[a], index[b])))
        if key not in edge_of:
            raise HTTPException(422, f"No streamline connects {a} and {b}.")
        edges.append(edge_of[key])
    return edges


def _read_json(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


@router.get(
    "/api/tract/manifest",
    response_model=TractManifest,
    summary="Whether a subject has a network to target, and its regions",
)
def manifest(subject: Annotated[SubjectId, Query()]) -> TractManifest:
    pm = _pm()
    _subject(pm, subject)
    tract_dir = _source(pm, pm.tractography(subject))
    qsiprep = build.source_path(pm, pm.qsiprep_subject(subject))
    out = {
        "qsiprep_available": qsiprep is not None and qsiprep.is_dir(),
        "tractogram_available": (tract_dir / "tractogram.trx").is_file(),
    }
    if not (out["tractogram_available"] and (tract_dir / "network.npz").is_file()):
        return TractManifest(available=False, **out)

    from tit.tract.network import is_cortical, network_fingerprint

    network = _network(pm, subject)
    record = _read_json(tract_dir / "network.json")
    regions = [
        TractRegion(name=name, cortical=is_cortical(name)) for name in network["names"]
    ]
    return TractManifest(
        available=True,
        **out,
        atlas=record.get("atlas"),
        n_streamlines=record.get("n_streamlines"),
        n_edges=len(network["pairs"]),
        frac_both_ends_assigned=record.get("frac_both_ends_assigned"),
        qc_passed=_read_json(tract_dir / "qc.json").get("flip_test_passed"),
        fingerprint=network_fingerprint(pm, subject),
        regions=sorted(regions, key=lambda r: not r.cortical),
    )


@router.get(
    "/api/tract/edges",
    response_model=TractEdges,
    summary="Every edge touching any seed region, most streamlines first",
)
def edges(
    subject: Annotated[SubjectId, Query()],
    seed: Annotated[list[str], Query(min_length=1, max_length=500)],
) -> TractEdges:
    pm = _pm()
    _subject(pm, subject)
    network = _network(pm, subject)
    names = network["names"]
    unknown = sorted(set(seed) - set(names))
    if unknown:
        raise HTTPException(422, f"Unknown region(s): {', '.join(unknown[:8])}")
    ids = {names.index(s) for s in seed}
    total = max(int(network["counts"].sum()), 1)
    # `pairs` is numbered by descending count, so walking it keeps the order.
    return TractEdges(
        edges=[
            TractEdge(
                edge_id=e,
                region_a=names[a],
                region_b=names[b],
                n=int(network["counts"][e]),
                share=float(network["counts"][e]) / total,
            )
            for e, (a, b) in enumerate(network["pairs"].tolist())
            if a in ids or b in ids
        ]
    )


def _preview_path(pm, subject: str, per_edge: int, step_mm: float) -> tuple[Path, Path]:
    """``(tractogram, cache file)``; the file's name carries the sources' fingerprint."""
    tract_dir = _source(pm, pm.tractography(subject))
    trx = tract_dir / "tractogram.trx"
    stamp = cache.fingerprint([trx, tract_dir / "network.npz"], version="preview1")
    folder = cache.cache_dir(pm.project_dir, subject)
    return trx, folder / f"tract-preview-{per_edge}-{step_mm:g}.{stamp}.npz"


def _build_preview(pm, subject: str, per_edge: int, step_mm: float) -> None:
    from tit.tract.preview import build_preview

    trx, path = _preview_path(pm, subject, per_edge, step_mm)
    with np.load(trx.parent / "network.npz", allow_pickle=False) as data:
        edge_id = data["edge_id"]
    arrays = build_preview(str(trx), edge_id, per_edge, step_mm)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache.ensure_bidsignore(pm.project_dir)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with tmp.open("wb") as stream:
        np.savez(stream, **arrays)
    os.replace(tmp, path)
    for old in path.parent.glob(f"tract-preview-{per_edge}-{step_mm:g}.*.npz"):
        if old != path:
            old.unlink(missing_ok=True)


@router.get(
    "/api/tract/streamlines",
    summary="A bounded subsample of the given edges' streamlines as TVSL1 binary",
    responses={
        200: {"content": {"application/octet-stream": {}}},
        202: {"description": "Cold cache: still building, poll after Retry-After"},
    },
)
def streamlines(
    subject: Annotated[SubjectId, Query()],
    pair: Annotated[list[str], Query(description="region_a|region_b")],
    wait: Annotated[float, Query(ge=0)] = 0.0,
) -> Response:
    from tit.tract.preview import PER_EDGE, STEP_MM, slice_edges

    pm = _pm()
    _subject(pm, subject)
    if not 1 <= len(pair) <= MAX_EDGES:
        raise HTTPException(422, f"Ask for 1 to {MAX_EDGES} edges, not {len(pair)}.")
    parsed: list[list[str]] = []
    for item in pair:
        a, sep, b = item.partition("|")
        if not sep or not a or not b:
            raise HTTPException(422, f"{item!r} is not region_a|region_b.")
        parsed.append([a, b])
    network = _network(pm, subject)
    wanted = _pair_edges(network, parsed)
    if not (Path(pm.tractography(subject)) / "tractogram.trx").is_file():
        raise HTTPException(404, f"sub-{subject} has no tractogram yet.")

    def ready() -> Path | None:
        path = _preview_path(pm, subject, PER_EDGE, STEP_MM)[1]
        return path if path.is_file() else None

    found = _ensure(
        pm,
        subject,
        "tract-preview",
        lambda: _build_preview(pm, subject, PER_EDGE, STEP_MM),
        ready,
        wait,
    )
    if found is None:
        return _building_response({"cache": {"state": "building"}})
    with np.load(found, allow_pickle=False) as data:
        arrays = {k: data[k] for k in data.files}
    points, offsets, index, group = slice_edges(arrays, wanted)
    return Response(
        content=tvsl.encode(points, offsets, index, group),
        media_type="application/octet-stream",
        headers={
            "cache-control": "private, max-age=0, must-revalidate",
            "x-content-type-options": "nosniff",
        },
    )


def _mask_record(path: Path, record: dict[str, Any], current: str) -> TractMask:
    selection = record.get("selection") or {}
    pairs = selection.get("pairs") or []
    return TractMask(
        name=selection.get("name", ""),
        path=str(path),
        fingerprint=record.get("fingerprint", ""),
        stale=record.get("fingerprint") != current,
        pairs=pairs,
        min_count=record.get("min_count", 1),
        n_edges=len(pairs),
        n_streamlines=record.get("n_streamlines", 0),
        n_voxels=record.get("n_voxels", 0),
        volume_mm3=record.get("volume_mm3", 0.0),
    )


@router.post(
    "/api/tract/mask",
    status_code=201,
    response_model=TractMask,
    summary="Write the tract-density mask of the given region pairs",
    responses={
        404: {"description": "No such subject, or no network yet"},
        409: {"description": "A mask of this name exists and overwrite is false"},
        422: {"description": "A bad name, pair or edge, or an empty mask"},
    },
)
def create_mask(body: TractMaskRequest) -> TractMask:
    from tit.blender.tract_data import load_trx
    from tit.paths import resolve_under, resolve_within
    from tit.tract.config import Selection
    from tit.tract.network import network_fingerprint, select
    from tit.tract.target import write_mask_with_sidecar

    pm = _pm()
    subject = _subject(pm, body.subject)
    try:
        selection = Selection(name=body.name, kind="edges", pairs=body.pairs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    network = _network(pm, subject)
    wanted = _pair_edges(network, body.pairs)
    too_few = [
        f"{a} - {b} ({int(network['counts'][e])})"
        for (a, b), e in zip(body.pairs, wanted)
        if network["counts"][e] < body.min_n
    ]
    if too_few:
        raise HTTPException(
            422,
            f"These edges have fewer than {body.min_n} streamlines: "
            + ", ".join(too_few[:8]),
        )
    try:
        mask_path = Path(
            resolve_within(
                pm.project_dir,
                resolve_under(pm.masks(subject), f"tract-{body.name}.nii.gz"),
            )
        )
    except ValueError as exc:
        raise HTTPException(403, "Mask folder escapes the project") from exc
    if mask_path.exists() and not body.overwrite:
        raise HTTPException(
            409, f"A mask named {body.name!r} already exists; replace it or rename."
        )
    tract_dir = _source(pm, pm.tractography(subject))
    trx = tract_dir / "tractogram.trx"
    if not trx.is_file():
        raise HTTPException(404, f"sub-{subject} has no tractogram yet.")
    with np.load(tract_dir / "network.npz", allow_pickle=False) as data:
        labels, edge_id = data["labels"], data["edge_id"]
    tracts = load_trx(str(trx))
    if tracts.n != len(labels):
        raise HTTPException(
            409, "The tractogram and the network disagree; run the network stage again."
        )
    pick = np.flatnonzero(select(selection, labels, network["names"], edge_id))
    bundle = [tracts.points[tracts.offsets[i] : tracts.offsets[i + 1]] for i in pick]
    with cache.subject_lock(pm.project_dir, subject):
        try:
            record = write_mask_with_sidecar(
                pm, subject, selection, bundle, body.min_count
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return _mask_record(mask_path, record, network_fingerprint(pm, subject))


@router.get(
    "/api/tract/masks",
    response_model=TractMasks,
    summary="This subject's masks made from its network",
)
def masks(subject: Annotated[SubjectId, Query()]) -> TractMasks:
    from tit.tract.network import network_fingerprint

    pm = _pm()
    _subject(pm, subject)
    folder = build.source_path(pm, pm.masks(subject))
    if folder is None or not folder.is_dir():
        return TractMasks(masks=[])
    current = network_fingerprint(pm, subject)
    out = []
    for sidecar in sorted(folder.glob("tract-*.json")):
        mask = sidecar.with_suffix(".nii.gz")
        record = _read_json(sidecar)
        if mask.is_file() and record.get("selection", {}).get("kind") == "edges":
            out.append(_mask_record(mask, record, current))
    return TractMasks(masks=out)


@router.get(
    "/api/tract/rankings",
    response_model=TractRankings,
    summary="Montage rankings of an ex-search run on this subject's networks",
)
def rankings(
    subject: Annotated[SubjectId, Query()],
    ex_run: Annotated[str, Query(min_length=1)],
) -> TractRankings:
    pm = _pm()
    _subject(pm, subject)
    tract_dir = _source(pm, pm.tractography(subject))
    out = []
    for path in sorted(tract_dir.glob("target_*.json")):
        record = _read_json(path)
        ranking = record.get("ranking") or {}
        if ranking.get("ex_run") != ex_run:
            continue
        out.append(
            TractRanking(
                name=record["selection"]["name"],
                ex_run=ex_run,
                n_streamlines=record["n_streamlines"],
                current_mA=ranking["current_mA"],
                n_points=ranking["n_points"],
                n_points_in_leadfield_mesh=ranking["n_points_in_leadfield_mesh"],
                montages=ranking["montages"],
            )
        )
    return TractRankings(rankings=out)
