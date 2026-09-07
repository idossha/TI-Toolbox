"""Unit tests for :mod:`tit.catalog` on a tmp project built with PathManager paths."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tit import catalog
from tit.paths import PathManager


@pytest.fixture()
def pm(tmp_path: Path) -> PathManager:
    """``001``: raw + freesurfer + m2m + simA (TI) + simB (TI+mTI) + ``.hidden``.

    ``002``: raw only.  ``003``: SimNIBS folder without m2m (not a subject).
    ``010`` / ``3``: freesurfer-only, to check natural sorting.
    """
    pm = PathManager(project_dir=str(tmp_path))
    os.makedirs(pm.bids_anat("001"))
    os.makedirs(pm.freesurfer_mri("001"))
    os.makedirs(pm.m2m("001"))
    os.makedirs(pm.ti_mesh_dir("001", "simA"))
    os.makedirs(pm.ti_mesh_dir("001", "simB"))
    os.makedirs(pm.mti_mesh_dir("001", "simB"))
    os.makedirs(pm.simulation("001", "simC"))
    os.makedirs(os.path.join(pm.simulations("001"), ".hidden"))
    os.makedirs(pm.bids_anat("002"))
    os.makedirs(pm.sub("003"))
    os.makedirs(pm.freesurfer_subject("010"))
    os.makedirs(pm.freesurfer_subject("3"))
    os.makedirs(os.path.join(pm.freesurfer(), "fsaverage"))
    (tmp_path / "dataset_description.json").write_text("{}")
    return pm


def test_subject_ids_union_natural_sort(pm: PathManager) -> None:
    assert catalog.subject_ids(pm) == ["001", "002", "3", "010"]


def test_list_subjects(pm: PathManager) -> None:
    # None of these fixture subjects has a sourcedata/ copy, so has_sourcedata is left out of
    # every row entirely (see list_subjects' docstring) -- this is the exact pre-FX5 shape.
    assert catalog.list_subjects(pm) == [
        {
            "id": "001",
            "has_raw": True,
            "has_fastsurfer": False,
            "has_freesurfer": True,
            "has_m2m": True,
            "n_simulations": 3,
        },
        {
            "id": "002",
            "has_raw": True,
            "has_fastsurfer": False,
            "has_freesurfer": False,
            "has_m2m": False,
            "n_simulations": 0,
        },
        {
            "id": "3",
            "has_raw": False,
            "has_fastsurfer": False,
            "has_freesurfer": True,
            "has_m2m": False,
            "n_simulations": 0,
        },
        {
            "id": "010",
            "has_raw": False,
            "has_fastsurfer": False,
            "has_freesurfer": True,
            "has_m2m": False,
            "n_simulations": 0,
        },
    ]


# ── sourcedata-only subjects (lane FX5: docs/dev/HISTORY.md § 2026-09-03 (pipelines program)) ──────────────────


def test_sourcedata_only_subject_appears_in_list_subjects(tmp_path: Path) -> None:
    """A subject with only ``sourcedata/`` DICOMs -- no BIDS dir yet -- is listed, not
    invisible: this is Dataset 000's own ``sub-102`` before DICOM conversion has ever run."""
    pm = PathManager(project_dir=str(tmp_path))
    t1w_dir = os.path.join(pm.sourcedata_subject("102"), "T1w")
    os.makedirs(t1w_dir)
    Path(t1w_dir, "IM0001.dcm").write_bytes(b"dicom")
    (tmp_path / "dataset_description.json").write_text("{}")

    assert catalog.subject_ids(pm) == []  # not "onboarded" -- no BIDS/derivative dir yet
    assert catalog.sourcedata_only_subject_ids(pm) == ["102"]
    assert catalog.list_subjects(pm) == [
        {
            "id": "102",
            "has_raw": False,
            "has_fastsurfer": False,
            "has_freesurfer": False,
            "has_m2m": False,
            "n_simulations": 0,
            "has_sourcedata": True,
        }
    ]


def test_sourcedata_only_subject_not_duplicated_once_onboarded(tmp_path: Path) -> None:
    """Once ``sub-102`` has a BIDS dir it is not double-listed, even though ``sourcedata/``
    still holds its DICOMs (which the real DICOM-conversion pipeline leaves in place)."""
    pm = PathManager(project_dir=str(tmp_path))
    t1w_dir = os.path.join(pm.sourcedata_subject("102"), "T1w")
    os.makedirs(t1w_dir)
    Path(t1w_dir, "IM0001.dcm").write_bytes(b"dicom")
    os.makedirs(pm.bids_anat("102"))
    (tmp_path / "dataset_description.json").write_text("{}")

    assert catalog.subject_ids(pm) == ["102"]
    assert catalog.sourcedata_only_subject_ids(pm) == []
    rows = catalog.list_subjects(pm)
    assert [r["id"] for r in rows] == ["102"]
    assert rows[0]["has_raw"] is True
    assert rows[0]["has_sourcedata"] is True  # the sourcedata copy is still on disk


def test_sourcedata_dir_without_valid_series_is_ignored(tmp_path: Path) -> None:
    """An empty/garbage ``sourcedata/sub-*/`` (no T1w/T2w series, no ``.tgz``) never appears --
    a bare directory left by some other tool is not "raw data staged"."""
    pm = PathManager(project_dir=str(tmp_path))
    os.makedirs(pm.sourcedata_subject("999"))
    (tmp_path / "dataset_description.json").write_text("{}")

    assert catalog.sourcedata_only_subject_ids(pm) == []
    assert catalog.list_subjects(pm) == []


def test_sourcedata_only_subject_ids_natural_sort(tmp_path: Path) -> None:
    pm = PathManager(project_dir=str(tmp_path))
    for sid in ("010", "3", "002"):
        t1w_dir = os.path.join(pm.sourcedata_subject(sid), "T1w")
        os.makedirs(t1w_dir)
        Path(t1w_dir, "IM0001.dcm").write_bytes(b"dicom")
    (tmp_path / "dataset_description.json").write_text("{}")

    assert catalog.sourcedata_only_subject_ids(pm) == ["002", "3", "010"]


def test_subject_detail_for_sourcedata_only_subject(tmp_path: Path) -> None:
    pm = PathManager(project_dir=str(tmp_path))
    t1w_dir = os.path.join(pm.sourcedata_subject("102"), "T1w")
    os.makedirs(t1w_dir)
    Path(t1w_dir, "IM0001.dcm").write_bytes(b"dicom")
    (tmp_path / "dataset_description.json").write_text("{}")

    detail = catalog.subject_detail(pm, "102")
    assert detail is not None
    assert detail["has_raw"] is False
    assert detail["has_sourcedata"] is True
    assert detail["has_m2m"] is False


def test_subject_detail_still_unknown_without_any_raw_data(tmp_path: Path) -> None:
    pm = PathManager(project_dir=str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    assert catalog.subject_detail(pm, "nope") is None


def test_list_simulations(pm: PathManager) -> None:
    listed = catalog.list_simulations(pm, "001")
    # v1 enriches each item with SimulationDetail keys; the v0 keys must still be exact.
    v0 = [{k: it[k] for k in ("name", "path", "has_ti", "has_mti")} for it in listed]
    assert all("fields" in it and "montages" in it for it in listed)
    assert v0 == [
        {
            "name": "simA",
            "path": pm.simulation("001", "simA"),
            "has_ti": True,
            "has_mti": False,
        },
        {
            "name": "simB",
            "path": pm.simulation("001", "simB"),
            "has_ti": True,
            "has_mti": True,
        },
        {
            "name": "simC",
            "path": pm.simulation("001", "simC"),
            "has_ti": False,
            "has_mti": False,
        },
    ]
    assert catalog.list_simulations(pm, "002") == []


def test_list_simulations_unknown_subject_is_none(pm: PathManager) -> None:
    assert catalog.list_simulations(pm, "nope") is None
    assert catalog.list_simulations(pm, "003") is None  # SimNIBS dir without m2m


def test_empty_project(tmp_path: Path) -> None:
    pm = PathManager(project_dir=str(tmp_path))
    assert catalog.subject_ids(pm) == []
    assert catalog.list_subjects(pm) == []
    assert catalog.list_simulations(pm, "001") is None
