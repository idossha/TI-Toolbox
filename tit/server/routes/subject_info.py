"""``GET /api/subjects/{id}/info`` -- one subject's whole processing story.

The v3 home of ``tit/gui/extensions/subject_info_viewer.py``. The Qt dialog
walked the project directory inside the GUI process and rendered the result
into a ``QTableWidget``; the panel that replaces it
(``desktop/src/renderer/pages/panel-subject-info/``) asks for one JSON body
instead, so the scan happens where the files are.

Why its own module rather than another ``/api/catalog/*`` route: the catalog
answers "what exists of kind X", one kind per route (simulations, analyses,
reports, free-hand configs). This answers "what exists **for this subject**"
across all of them at once, which is a different question and the only reason
the panel exists at all -- assembling it in the browser would be a dozen
requests whose partial failures the user would have to interpret.

Thin over :func:`tit.catalog.subject_info` (rule R1: every discovery rule
lives in :mod:`tit.catalog`, never in a route).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tit import catalog
from tit.paths import get_path_manager

router = APIRouter()


@router.get(
    "/api/subjects/{id}/info",
    summary="Everything known about one subject: anatomy, head model, runs, derivatives",
    responses={
        200: {"description": "the subject's full information"},
        404: {"description": "no such subject in this project"},
    },
)
def subject_info(id: str) -> dict:
    info = catalog.subject_info(get_path_manager(), id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown subject: {id}")
    return info
