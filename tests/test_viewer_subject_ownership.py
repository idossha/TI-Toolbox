"""The server and the Viewer agree on which subject owns a path, outside SimNIBS too.

What it pins: ``POST /api/view/open`` refuses a scene whose files belong to two subjects
(``tit/server/routes/viewers.py``). Before 2026-10-22 the server recognised a subject only under
``derivatives/SimNIBS/sub-<id>/``, so ernie's FastSurfer atlas next to 101's field -- a pair the
Viewer's anatomy tree offers (``tit/viewspec.py`` lists ``derivatives/fastsurfer|freesurfer/
sub-<id>/mri`` atlases) -- was composed into one scene: one person's labels over another's field,
with nothing on screen to say so.

Where the numbers come from: ``tests/fixtures/subject_paths.json``, a hand-written table of
container paths and owners derived from the BIDS layout rule stated in its ``_about``. The same
table drives ``desktop/tests/unit/viewer-subject-ownership.test.ts`` against the Viewer's
``subjectOfPath``, so the two sides cannot drift apart without one of them going red.

Reproduce: ``.venv/bin/python -m pytest tests/test_viewer_subject_ownership.py -q``.
Deliberately elsewhere: the scene composition itself (``tests/test_view_surfaces.py``,
``tests/test_view_open.py``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tit.server.routes import viewers

TABLE = json.loads(
    (Path(__file__).parent / "fixtures" / "subject_paths.json").read_text()
)
ROWS = TABLE["rows"]


def test_the_table_has_rows_on_both_sides_of_the_rule() -> None:
    owners = [row["owner"] for row in ROWS]
    assert len(ROWS) >= 15
    assert None in owners and len({o for o in owners if o is not None}) >= 5


@pytest.mark.parametrize("row", ROWS, ids=[row["why"] for row in ROWS])
def test_subject_of_path_matches_the_table(row: dict) -> None:
    assert viewers.subject_of_path(row["path"]) == row["owner"]


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(viewers.router)
    return TestClient(app)


def test_a_scene_mixing_a_fastsurfer_atlas_with_another_subjects_field_is_refused() -> (
    None
):
    case = TABLE["two_subject_scene"]
    response = _client().post(
        "/api/view/open",
        json={"kind": "subject", "subject": case["subject"], "files": case["files"]},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    # Both owners are named, each with the file that brought it in.
    assert "ernie (aparc.DKTatlas+aseg.deep.nii.gz)" in detail
    assert "101 (X_TI_subject_TI_max.nii.gz)" in detail


@pytest.mark.parametrize(
    "files",
    [
        # The prefix pair: 101 and 1010 are two people.
        [
            "/mnt/p/derivatives/SimNIBS/sub-101/m2m_101/T1.nii.gz",
            "/mnt/p/derivatives/SimNIBS/sub-1010/m2m_1010/T1.nii.gz",
        ],
        # Raw BIDS anatomy of one, a QSIRecon map of another.
        [
            "/mnt/p/sub-101/anat/sub-101_T1w.nii.gz",
            "/mnt/p/derivatives/qsirecon/derivatives/qsirecon-DSIStudio/sub-CHN/dwi/fa.nii.gz",
        ],
    ],
    ids=["sub-101-vs-sub-1010", "raw-bids-vs-qsirecon"],
)
def test_other_two_subject_pairs_are_refused(files: list[str]) -> None:
    with pytest.raises(viewers.HTTPException) as excinfo:
        viewers._refuse_a_scene_that_spans_two_subjects(files)
    assert excinfo.value.status_code == 422


def test_one_subjects_files_across_pipelines_with_shared_files_pass() -> None:
    """Every row owned by ernie, plus every row owned by nobody, is one subject's scene."""
    files = [row["path"] for row in ROWS if row["owner"] in ("ernie", None)]
    assert any("fastsurfer" in f for f in files) and any(
        "resources/atlas" in f for f in files
    )
    viewers._refuse_a_scene_that_spans_two_subjects(files)  # does not raise
