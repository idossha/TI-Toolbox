"""The MNI ROI confirmation artefact, on synthetic volumes with real nibabel.

The claims under test are geometric — a centroid in the subject's own
millimetres, a voxel count, a grey-matter overlap fraction — so they need real
``nibabel``/``scipy`` (this directory's conftest swaps the host suite's mocks
out).  ``prepare_mask``'s MNI branch needs SimNIBS, so the transform itself is
stubbed to the identity here and exercised for real in the container run
recorded in ``docs/dev/DECISIONS.md`` (2026-09-17); what is checked here is
everything around it, including the promise that a failure never propagates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("nibabel")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from tit import roi_confirmation  # noqa: E402


def _volume(path: Path, data, affine) -> str:
    # Imported per call, not at module scope: this directory's conftest swaps the
    # real nibabel in for the duration of the package, after collection.
    import nibabel as nib

    nib.save(nib.Nifti1Image(np.asarray(data), np.asarray(affine, dtype=float)), str(path))
    return str(path)


@pytest.fixture
def m2m(tmp_path: Path) -> Path:
    """A minimal ``m2m_`` directory: a T1 and a final_tissues both 12 mm cubed."""
    directory = tmp_path / "m2m_test"
    directory.mkdir()
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    _volume(directory / "T1.nii.gz", np.full((12, 12, 12), 100.0, dtype=np.float32), affine)
    # Grey matter (label 2) fills the x >= 6 half; the rest is white matter.
    tissues = np.full((12, 12, 12), 1, dtype=np.uint8)
    tissues[6:, :, :] = roi_confirmation.GM_TISSUE_LABEL
    _volume(directory / "final_tissues.nii.gz", tissues, affine)
    return directory


@pytest.fixture(autouse=True)
def identity_transform(monkeypatch):
    """`prepare_mask` with the MNI transform replaced by a pass-through.

    The real one calls SimNIBS.  Keeping the rest of the function — the
    validation, the binarisation, the write into the caller's directory — is
    what makes this a test of this module rather than of a stand-in.
    """
    import tit.opt.masks as masks

    real = masks.prepare_mask

    def passthrough(path, space, m2m, output_dir, *, binary=False):
        return real(path, "subject", m2m, output_dir, binary=binary)

    monkeypatch.setattr(masks, "prepare_mask", passthrough)
    return passthrough


def test_reports_the_centroid_in_subject_millimetres_and_the_gm_overlap(tmp_path, m2m):
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    atlas = np.zeros((12, 12, 12), dtype=np.uint16)
    # 2x2x2 block of label 7, all of it inside the grey-matter half (x >= 6).
    atlas[8:10, 4:6, 2:4] = 7
    atlas[0:2, 0:2, 0:2] = 9  # a second label the confirmation must ignore
    path = _volume(tmp_path / "atlas.nii.gz", atlas, affine)

    out = tmp_path / "run"
    summary = roi_confirmation.confirm_roi(
        atlas_path=path, space="mni", m2m=str(m2m), out_dir=str(out), label=7, name="Test-Region"
    )

    assert summary is not None
    assert summary["voxels"] == 8
    # Voxel centroid (8.5, 4.5, 2.5) through the affine -> (2.5, -1.5, -3.5).
    assert summary["centroid_ras"] == [2.5, -1.5, -3.5]
    assert summary["gm_overlap"] == 1.0
    assert summary["label"] == 7
    written = json.loads((out / roi_confirmation.JSON_NAME).read_text())
    assert written == summary


def test_gm_overlap_is_a_fraction_when_the_roi_straddles_the_boundary(tmp_path, m2m):
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    atlas = np.zeros((12, 12, 12), dtype=np.uint16)
    atlas[5:7, 4:6, 2:4] = 3  # half in white matter, half in grey
    path = _volume(tmp_path / "atlas.nii.gz", atlas, affine)
    summary = roi_confirmation.confirm_roi(
        atlas_path=path, space="mni", m2m=str(m2m), out_dir=str(tmp_path / "run"), label=3
    )
    assert summary is not None
    assert summary["gm_overlap"] == 0.5


def test_a_subject_space_roi_is_confirmed_too(tmp_path, m2m):
    """The check is no longer for MNI ROIs only: a subject mask off by a slice
    is as invisible in the numbers as a bad transform."""
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    mask = np.zeros((12, 12, 12), dtype=np.uint8)
    mask[8:10, 4:6, 2:4] = 1
    path = _volume(tmp_path / "a.nii.gz", mask, affine)
    out = tmp_path / "run"

    summary = roi_confirmation.confirm_roi(
        atlas_path=path, space="subject", m2m=str(m2m), out_dir=str(out), name="Hand-drawn"
    )

    assert summary is not None
    assert summary["space"] == "subject"
    assert summary["voxels"] == 8
    assert summary["cursor_rule"] == "single"
    assert (out / roi_confirmation.MASK_NAME).is_file()
    assert (out / roi_confirmation.JSON_NAME).is_file()


def test_a_failure_is_a_log_line_and_never_an_exception(tmp_path, m2m, caplog):
    """A job must not die because a picture could not be drawn."""
    out = tmp_path / "run"
    assert (
        roi_confirmation.confirm_roi(
            atlas_path=str(tmp_path / "does-not-exist.nii.gz"),
            space="mni",
            m2m=str(m2m),
            out_dir=str(out),
        )
        is None
    )


def test_the_env_switch_turns_the_whole_artefact_off(tmp_path, m2m, monkeypatch):
    monkeypatch.setenv(roi_confirmation.DISABLE_ENV, "1")
    path = _volume(tmp_path / "a.nii.gz", np.ones((4, 4, 4), dtype=np.uint8), np.eye(4))
    assert roi_confirmation.confirm_roi(atlas_path=path, space="mni", m2m=str(m2m), out_dir=str(tmp_path / "r")) is None


def test_several_targets_do_not_overwrite_each_others_artefacts(tmp_path, m2m):
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    atlas = np.zeros((12, 12, 12), dtype=np.uint16)
    atlas[8:10, 4:6, 2:4] = 7
    atlas[8:10, 6:8, 2:4] = 8
    path = _volume(tmp_path / "atlas.nii.gz", atlas, affine)
    out = tmp_path / "run"
    summaries = roi_confirmation.confirm_rois(
        [
            {"atlas_path": path, "label": 7, "space": "mni"},
            {"atlas_path": path, "label": 8, "space": "mni"},
        ],
        m2m=str(m2m),
        out_dir=str(out),
    )
    assert len(summaries) == 2
    assert (out / roi_confirmation.JSON_NAME).is_file()
    assert (out / "roi_2" / roi_confirmation.JSON_NAME).is_file()
