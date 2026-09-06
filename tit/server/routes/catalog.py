"""``/api/catalog/*`` — thin HTTP wrappers over :mod:`tit.catalog`.

Discovery rules (which folders make a subject, what a simulation contains)
live in ``tit.catalog`` on top of :class:`tit.paths.PathManager`; this module
only maps them to responses.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from tit import catalog
from tit.paths import get_path_manager
from tit.server.schemas import SimulationList, SubjectList

router = APIRouter()


@router.get(
    "/api/catalog/subjects",
    response_model=SubjectList,
    response_model_exclude_unset=True,
    summary="Subjects with presence flags (PathManager rules, never re-implemented in TS)",
)
def subjects() -> SubjectList:
    # exclude_unset: tit.catalog.list_subjects only sets has_sourcedata on the (rare) entries
    # that have one -- every other field is always present, so this cannot hide them (see
    # list_subjects' own docstring for why: a byte-identical response for every project that
    # has no sourcedata-only subject, lane FX5).
    return SubjectList(subjects=catalog.list_subjects(get_path_manager()))


@router.get(
    "/api/catalog/simulations",
    response_model=SimulationList,
    summary="Simulations of one subject",
    responses={404: {"description": "unknown subject"}},
)
def simulations(subject: str = Query(...)) -> SimulationList:
    found = catalog.list_simulations(get_path_manager(), subject)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown subject: {subject}")
    return SimulationList(simulations=found)
