"""The catalog does not call an interrupted FastSurfer or charm run "done".

What this pins (package p24, audit_pre.md "incomplete output", 2026-10-22): the catalog's
``has_fastsurfer`` and ``has_m2m`` flags (``subject_detail``, ``list_subjects`` and,
through ``subject_detail``, the Overview) were "the folder
exists". Dataset 000's ``derivatives/fastsurfer/sub-101`` holds only ``mri/orig.mgz``,
``mri/orig/001.mgz`` and ``scripts/deep-seg.log`` ending at "Run coronal prediction" -- an
interrupted run -- and the Overview showed FastSurfer present for it. Pre-processing's skip
(package p17, ``tests/test_pre_incomplete_outputs.py``) already refuses such a folder; the
catalog now reads the same completion rule (``tit.pre.preflight.step_output_complete``).

Expected values: the completion markers are the producers' own success conditions, written
here as literals, not imported: FastSurfer's ``run_fastsurfer`` checks
``mri/aparc.DKTatlas+aseg.deep.mgz`` (``tit/pre/fastsurfer.py`` SEG_FILENAME); charm's last
science step writes ``<id>.msh`` after ``final_tissues.nii.gz``.

Reproduce: ``.venv/bin/python -m pytest tests/test_catalog_incomplete_outputs.py -q``.
Deliberately elsewhere: the skip/replace half (p17's test file above) and the Dataset 000
read-only check of the same layout (``tests/test_pre_incomplete_outputs.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tit import catalog
from tit.paths import get_path_manager
from tit.server.routes.overview import build_overview

SID = "001"
FASTSURFER_SEG = "aparc.DKTatlas+aseg.deep.mgz"


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture()
def project(tmp_path):
    """sub-001 with an interrupted FastSurfer and a cancelled charm, as Dataset 000 has them."""
    (tmp_path / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(tmp_path))
    fs = Path(pm.fastsurfer_subject(SID))
    _write(fs / "mri" / "orig.mgz")
    _write(fs / "mri" / "orig" / "001.mgz")
    _write(
        fs / "scripts" / "deep-seg.log",
        "Run sagittal prediction\nRun axial prediction\nRun coronal prediction\n",
    )
    _write(Path(pm.m2m(SID)) / "charm_log.html", "<html>charm started</html>")
    return pm


def _flags(pm) -> dict:
    """has_fastsurfer / has_m2m from every catalog surface that reports them."""
    detail = catalog.subject_detail(pm, SID)
    (row,) = [r for r in catalog.list_subjects(pm) if r["id"] == SID]
    (orow,) = [s for s in build_overview(pm, []).subjects if s.id == SID]
    return {
        "detail": (detail["has_fastsurfer"], detail["has_m2m"]),
        "list": (row["has_fastsurfer"], row["has_m2m"]),
        "overview": (orow.fastsurfer == "present", orow.m2m == "present"),
    }


def test_interrupted_fastsurfer_and_charm_are_not_present(project):
    flags = _flags(project)
    assert flags == {surface: (False, False) for surface in flags}
    # The subject is still onboarded (listed), it is just not done.
    assert SID in catalog.subject_ids(project)
    detail = catalog.subject_detail(project, SID)
    assert detail["m2m_path"] is None
    assert detail["eeg_nets"] == []


def test_finished_outputs_are_present(project):
    _write(Path(project.fastsurfer_mri(SID)) / FASTSURFER_SEG)
    m2m = Path(project.m2m(SID))
    _write(m2m / f"{SID}.msh")
    _write(m2m / "final_tissues.nii.gz")
    flags = _flags(project)
    assert flags == {surface: (True, True) for surface in flags}
    assert catalog.subject_detail(project, SID)["m2m_path"] == str(m2m)


@pytest.mark.parametrize("present", ["mesh", "segmentation"])
def test_a_head_model_needs_both_the_mesh_and_the_final_segmentation(project, present):
    m2m = Path(project.m2m(SID))
    _write(m2m / (f"{SID}.msh" if present == "mesh" else "final_tissues.nii.gz"))
    detail = catalog.subject_detail(project, SID)
    assert detail["has_m2m"] is False


def test_fastsurfer_segmentation_alone_is_enough_for_fastsurfer(project):
    _write(Path(project.fastsurfer_mri(SID)) / FASTSURFER_SEG)
    detail = catalog.subject_detail(project, SID)
    assert (detail["has_fastsurfer"], detail["has_m2m"]) == (True, False)
