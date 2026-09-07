"""``/api/catalog/*`` v1 endpoints beyond the v0 subjects/simulations list.

Thin HTTP wrappers over :mod:`tit.catalog` only -- every discovery/CRUD rule
(which files make a montage, how an ROI is named, which run dirs count as
complete) lives there on top of :class:`tit.paths.PathManager`, per
``dev/notes/v3-build-plan.md`` "Design rules" R1. Response bodies are plain
dicts rather than a ``response_model`` for endpoints where the v1 contract's
hand-authored schema does not exactly match what the underlying files
contain today (see ``FreehandConfig`` below and this lane's final report);
FastAPI still serialises them correctly, just without an extra validation
pass that would reject real data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from tit import catalog
from tit.paths import get_path_manager

router = APIRouter()


def _pm():
    return get_path_manager()


def _or_404(value: Any, detail: str = "Not found") -> Any:
    if value is None:
        raise HTTPException(status_code=404, detail=detail)
    return value


# ── subjects / simulations detail ────────────────────────────────────────────


@router.get("/api/catalog/subjects/{id}", summary="One subject's full detail")
def subject_detail(id: str) -> dict:
    return _or_404(catalog.subject_detail(_pm(), id), f"Unknown subject: {id}")


@router.get("/api/catalog/simulations/{name}", summary="One simulation's full detail")
def simulation_detail(name: str, subject: str = Query(...)) -> dict:
    return _or_404(
        catalog.simulation_detail(_pm(), subject, name),
        f"Unknown subject/simulation: {subject}/{name}",
    )


@router.get(
    "/api/catalog/electrode-overlays",
    summary="Electrode overlay NIfTI presence for one simulation, per TI/mTI mode",
)
def electrode_overlays(
    subject: str = Query(...), simulation: str = Query(...)
) -> list[dict]:
    return _or_404(
        catalog.electrode_overlays(_pm(), subject, simulation),
        f"Unknown subject or simulation: {subject}/{simulation}",
    )


# ── montages ─────────────────────────────────────────────────────────────────


@router.get(
    "/api/catalog/montages",
    summary="All montages, grouped by EEG net and polarity kind",
)
def montages() -> dict:
    return catalog.get_montages(_pm())


@router.put(
    "/api/catalog/montages/{net}/{kind}/{name}",
    summary="Create or overwrite one montage",
)
def put_montage(
    net: str, kind: str, name: str, body: dict = Body(...)
) -> list[list[str]]:
    if kind not in ("uni_polar", "multi_polar"):
        raise HTTPException(
            status_code=422, detail="kind must be uni_polar or multi_polar"
        )
    pairs = body.get("pairs")
    if not isinstance(pairs, list):
        raise HTTPException(status_code=422, detail="body.pairs is required")
    try:
        return catalog.put_montage(_pm(), net, kind, name, pairs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/api/catalog/montages/{net}/{kind}/{name}",
    status_code=204,
    summary="Delete one montage",
)
def delete_montage(net: str, kind: str, name: str) -> None:
    if kind not in ("uni_polar", "multi_polar"):
        raise HTTPException(
            status_code=422, detail="kind must be uni_polar or multi_polar"
        )
    if not catalog.delete_montage(_pm(), net, kind, name):
        raise HTTPException(
            status_code=404, detail=f"Unknown montage: {net}/{kind}/{name}"
        )


# ── EEG nets ─────────────────────────────────────────────────────────────────


@router.get("/api/catalog/eeg-nets", summary="EEG nets available to a subject")
def eeg_nets(subject: str = Query(...)) -> list[dict]:
    return _or_404(catalog.eeg_nets(_pm(), subject), f"Unknown subject: {subject}")


# ── atlases / regions ────────────────────────────────────────────────────────


@router.get(
    "/api/catalog/atlases", summary="Atlases available to a subject in a given space"
)
def atlases(
    subject: str = Query(...),
    space: str | None = Query(None),
    kind: str | None = Query(None),
) -> list[dict]:
    return _or_404(
        catalog.atlases(_pm(), subject, space, kind), f"Unknown subject: {subject}"
    )


@router.get("/api/catalog/atlases/regions", summary="Regions of one atlas")
def atlas_regions(
    subject: str = Query(...),
    atlas: str = Query(...),
    hemi: str | None = Query(None),
) -> list[dict]:
    return _or_404(
        catalog.atlas_regions(_pm(), subject, atlas, hemi),
        f"Unknown subject or atlas: {subject}/{atlas}",
    )


@router.get("/api/catalog/nifti/labels", summary="Integer labels of a NIfTI volume")
def nifti_labels(
    subject: str = Query(...),
    path: str | None = Query(None),
) -> list[dict]:
    """Browse the labels of a segmentation volume (the sub-cortical exporter's picker).

    One 404 covers unknown subject, a path outside the project jail, and a file that
    is not there -- see :func:`tit.catalog.nifti_labels` for why they are not
    distinguished.
    """
    return _or_404(
        catalog.nifti_labels(_pm(), subject, path),
        f"No readable label volume for {subject}",
    )


# ── ROIs ─────────────────────────────────────────────────────────────────────


@router.get("/api/catalog/rois", summary="Saved ROIs for a subject")
def rois(subject: str = Query(...)) -> list[dict]:
    return _or_404(catalog.list_rois(_pm(), subject), f"Unknown subject: {subject}")


@router.post(
    "/api/catalog/rois", status_code=201, summary="Save a new ROI for a subject"
)
def create_roi(subject: str = Query(...), body: dict = Body(...)) -> dict:
    if subject not in catalog.subject_ids(_pm()):
        raise HTTPException(status_code=404, detail=f"Unknown subject: {subject}")
    for field in ("name", "x", "y", "z"):
        if field not in body:
            raise HTTPException(status_code=422, detail=f"body.{field} is required")
    try:
        return catalog.create_roi(_pm(), subject, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/api/catalog/rois/{name}", status_code=204, summary="Delete one saved ROI"
)
def delete_roi(name: str, subject: str = Query(...)) -> None:
    if subject not in catalog.subject_ids(_pm()):
        raise HTTPException(status_code=404, detail=f"Unknown subject: {subject}")
    if not catalog.delete_roi(_pm(), subject, name):
        raise HTTPException(status_code=404, detail=f"Unknown ROI: {name}")


# ── leadfields ───────────────────────────────────────────────────────────────


@router.get("/api/catalog/leadfields", summary="Precomputed leadfields for a subject")
def leadfields(subject: str = Query(...)) -> list[dict]:
    return _or_404(
        catalog.list_leadfields(_pm(), subject), f"Unknown subject: {subject}"
    )


# ── flex / ex / mex runs ─────────────────────────────────────────────────────


@router.get("/api/catalog/flex-runs", summary="Flex-search runs for a subject")
def flex_runs(subject: str = Query(...)) -> list[dict]:
    return _or_404(catalog.flex_runs(_pm(), subject), f"Unknown subject: {subject}")


@router.get(
    "/api/catalog/flex-runs/{run}/mapping",
    summary="Map one flex-search run's optimised positions onto an EEG net",
)
def flex_run_mapping(
    run: str, subject: str = Query(...), eeg_net: str = Query(...)
) -> dict:
    """Return the run's electrodes as *eeg_net*'s labels, mapping if needed.

    A flex run only carries ``electrode_mapping_<net>.json`` for the nets it
    was already mapped onto, so the Simulator's "Map to net" choice would
    otherwise be limited to those. :func:`resolve_flex_montage` maps the
    optimiser's XYZ onto *any* net of the subject (Hungarian assignment) and
    caches the result beside the run, so the first request for a new net
    computes the mapping and every later one -- including ``flex_runs``'
    ``mappings`` list -- reads the file it wrote.
    """
    from tit.sim import montage_sources

    try:
        montage = montage_sources.resolve_flex_montage(
            _pm(), subject, run, "mapped", eeg_net=eeg_net
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "eeg_net": eeg_net,
        "pairs": [list(pair) for pair in montage.electrode_pairs],
    }


@router.get(
    "/api/catalog/ex-runs", summary="Ex-search (or mEx-search) runs for a subject"
)
def ex_runs(subject: str = Query(...), kind: str = Query("ex")) -> list[dict]:
    if kind not in ("ex", "mex"):
        raise HTTPException(status_code=422, detail="kind must be ex or mex")
    return _or_404(catalog.ex_runs(_pm(), subject, kind), f"Unknown subject: {subject}")


@router.get(
    "/api/catalog/ex-runs/{run}/results", summary="Full results table of one ex/mEx run"
)
def ex_run_results(run: str, subject: str = Query(...), kind: str = Query(...)) -> dict:
    if kind not in ("ex", "mex"):
        raise HTTPException(status_code=422, detail="kind must be ex or mex")
    return _or_404(
        catalog.ex_run_results(_pm(), subject, kind, run),
        f"Unknown run: {subject}/{kind}/{run}",
    )


# ── analyses ─────────────────────────────────────────────────────────────────


@router.get("/api/catalog/analyses", summary="Analyzer runs for one subject/simulation")
def analyses(subject: str = Query(...), simulation: str = Query(...)) -> list[dict]:
    return _or_404(
        catalog.analyses(_pm(), subject, simulation),
        f"Unknown subject or simulation: {subject}/{simulation}",
    )


@router.get(
    "/api/catalog/analyses/{name}/summary",
    summary="Summary statistics table of one analysis",
)
def analysis_summary(
    name: str, subject: str = Query(...), simulation: str = Query(...)
) -> dict:
    return _or_404(
        catalog.analysis_summary(_pm(), subject, simulation, name),
        f"Unknown analysis: {subject}/{simulation}/{name}",
    )


# ── reports ──────────────────────────────────────────────────────────────────


@router.get("/api/catalog/reports", summary="Generated HTML reports for a subject")
def reports(subject: str = Query(...)) -> list[dict]:
    return _or_404(catalog.reports(_pm(), subject), f"Unknown subject: {subject}")


# ── freehand ─────────────────────────────────────────────────────────────────


@router.get(
    "/api/catalog/freehand",
    summary="Saved free-hand electrode configurations for a subject",
)
def freehand(subject: str = Query(...)) -> list[dict]:
    return _or_404(
        catalog.freehand_configs(_pm(), subject), f"Unknown subject: {subject}"
    )


@router.put(
    "/api/catalog/freehand/{name}",
    summary="Create or overwrite one free-hand electrode configuration",
)
def put_freehand(name: str, subject: str = Query(...), body: dict = Body(...)) -> dict:
    if subject not in catalog.subject_ids(_pm()):
        raise HTTPException(status_code=404, detail=f"Unknown subject: {subject}")
    try:
        return catalog.put_freehand_config(_pm(), subject, name, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=422, detail=f"electrode_positions[]: missing {exc}"
        ) from exc


# ── project-level: group, notes, subject-info ────────────────────────────────


@router.get("/api/catalog/group", summary="Project-level group catalog")
def group() -> dict:
    return catalog.group_catalog(_pm())


@router.get("/api/catalog/notes", summary="Quick Notes content")
def get_notes() -> dict:
    return catalog.read_notes(_pm())


@router.put("/api/catalog/notes", summary="Replace Quick Notes content")
def put_notes(body: dict = Body(...)) -> dict:
    return catalog.write_notes(_pm(), str(body.get("text", "")))


@router.get(
    "/api/catalog/subject-info", summary="Presence matrix across the whole project"
)
def subject_info() -> dict:
    return catalog.subject_info_matrix(_pm())
