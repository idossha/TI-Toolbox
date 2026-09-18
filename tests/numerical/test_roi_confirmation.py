"""The ROI scene artefact, on synthetic volumes with real nibabel.

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


SCENE = roi_confirmation.SCENE_NAME


def _scene(out: Path) -> dict:
    return json.loads((out / SCENE).read_text())


def _listing(out: Path) -> set[str]:
    return {p.name for p in out.iterdir()}


def test_reports_the_centroid_in_subject_millimetres_and_the_gm_overlap(tmp_path, m2m):
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    atlas = np.zeros((12, 12, 12), dtype=np.uint16)
    # 2x2x2 block of label 7, all of it inside the grey-matter half (x >= 6).
    atlas[8:10, 4:6, 2:4] = 7
    atlas[0:2, 0:2, 0:2] = 9  # a second label the confirmation must ignore
    path = _volume(tmp_path / "atlas.nii.gz", atlas, affine)

    out = tmp_path / "run"
    meta = roi_confirmation.confirm_roi(
        atlas_path=path, space="mni", m2m=str(m2m), out_dir=str(out), label=7, name="Test-Region"
    )

    assert meta is not None
    assert meta["voxels"] == 8
    # Voxel centroid (8.5, 4.5, 2.5) through the affine -> (2.5, -1.5, -3.5).
    assert meta["centroid_ras"] == [2.5, -1.5, -3.5]
    assert meta["gm_overlap"] == 1.0
    assert meta["label"] == [7]
    # An MNI target is the one case with an intermediate, and it is the only one.
    assert _listing(out) == {SCENE, roi_confirmation.MNI_MASK_NAME}
    assert _scene(out)["meta"] == meta


def test_gm_overlap_is_a_fraction_when_the_roi_straddles_the_boundary(tmp_path, m2m):
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    atlas = np.zeros((12, 12, 12), dtype=np.uint16)
    atlas[5:7, 4:6, 2:4] = 3  # half in white matter, half in grey
    path = _volume(tmp_path / "atlas.nii.gz", atlas, affine)
    meta = roi_confirmation.confirm_roi(
        atlas_path=path, space="mni", m2m=str(m2m), out_dir=str(tmp_path / "run"), label=3
    )
    assert meta is not None
    assert meta["gm_overlap"] == 0.5


def test_a_subject_space_target_writes_the_scene_and_nothing_else(tmp_path, m2m):
    """The whole point of the change: the scene points at the file the user named.

    A subject-space ROI needs no intermediate at all, so the directory holds one
    file, and the dataset it names is the mask that was passed in."""
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    mask = np.zeros((12, 12, 12), dtype=np.uint8)
    mask[8:10, 4:6, 2:4] = 1
    path = _volume(tmp_path / "a.nii.gz", mask, affine)
    out = tmp_path / "run"

    meta = roi_confirmation.confirm_roi(
        atlas_path=path, space="subject", m2m=str(m2m), out_dir=str(out), name="Hand-drawn"
    )

    assert meta is not None
    assert meta["space"] == "subject"
    assert meta["voxels"] == 8
    assert meta["rule"] == "single"
    assert _listing(out) == {SCENE}

    scene = _scene(out)
    names = [d["name"] for d in scene["datasets"]]
    assert names == ["T1.nii.gz", "a.nii.gz"]
    for dataset in scene["datasets"]:
        resolved = (out / dataset["path"]).resolve()
        assert resolved.is_file(), f"{dataset['path']} does not exist"
    # The cursor is on the ROI, and the ROI is what the camera is centred on.
    assert scene["cursor"] == pytest.approx(meta["cursor_ras"], abs=0.01)
    assert all(slice_["camera"]["mmPerPx"] > 0 for slice_ in scene["slices"])


def test_a_failure_is_a_log_line_and_never_an_exception(tmp_path, m2m, caplog):
    """A job must not die because an artefact could not be written."""
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


def test_several_targets_are_one_scene_in_one_directory(tmp_path, m2m):
    """A search treats a union of regions as one target, so the confirmation is
    one scene and one directory — never ``roi_2/`` — with one colour per region."""
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    atlas = np.zeros((12, 12, 12), dtype=np.uint16)
    atlas[8:10, 4:6, 2:4] = 7
    atlas[8:10, 6:8, 2:4] = 8
    path = _volume(tmp_path / "atlas.nii.gz", atlas, affine)
    out = tmp_path / "run"
    written = roi_confirmation.confirm_rois(
        [
            {"atlas_path": path, "label": 7, "space": "subject", "name": "seven"},
            {"atlas_path": path, "label": 8, "space": "subject", "name": "eight"},
        ],
        m2m=str(m2m),
        out_dir=str(out),
    )
    assert len(written) == 1
    assert written[0]["roi"] == "seven + eight"
    assert set(written[0]["regions"]) == {"seven", "eight"}
    assert _listing(out) == {SCENE}
    assert not (out / "roi_2").exists()

    scene = _scene(out)
    # One dataset for the atlas, listed once and styled twice (fill and outline).
    atlas_layers = [la for la in scene["layers"] if la["name"] == "atlas.nii.gz"]
    assert len(atlas_layers) == 2
    assert {la["labelMode"] for la in atlas_layers} == {"fill", "outline"}
    assert atlas_layers[0]["visibleLabels"] == [7, 8]
    colours = atlas_layers[0]["labelColors"]
    assert colours["7"] != colours["8"], "a union shows one colour per region"


def test_a_field_target_gets_a_second_scene_naming_the_field_file(tmp_path, m2m):
    """No `_field-in-roi.nii`: the field scene points at the file the table came from."""
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [-6.0, -6.0, -6.0]
    mask = np.zeros((12, 12, 12), dtype=np.uint8)
    mask[8:10, 4:6, 2:4] = 1
    path = _volume(tmp_path / "a.nii.gz", mask, affine)
    field = np.zeros((12, 12, 12), dtype=np.float32)
    field[8:10, 4:6, 2:4] = np.linspace(0.1, 0.5, 8).reshape(2, 2, 2)
    field_path = _volume(tmp_path / "TI_max.nii.gz", field, affine)
    out = tmp_path / "run"

    roi_confirmation.confirm_rois(
        [{"atlas_path": path, "space": "subject", "field_path": field_path}],
        m2m=str(m2m),
        out_dir=str(out),
    )

    assert _listing(out) == {SCENE, roi_confirmation.FIELD_SCENE_NAME}
    scene = json.loads((out / roi_confirmation.FIELD_SCENE_NAME).read_text())
    field_layer = [la for la in scene["layers"] if la["name"] == "TI_max.nii.gz"][0]
    assert field_layer["colormap"] == "inferno"
    # `clamp` (the default) would paint a black wash over the whole T1.
    assert field_layer["threshold"]["mode"] == "hide"
    assert field_layer["threshold"]["lo"] == pytest.approx(0.2 * field_layer["scale"]["hi"])
    assert scene["meta"]["field"]["file"] == field_path


def test_a_sphere_target_is_the_cursor_and_no_file(tmp_path, m2m):
    """A sphere names no file, so the scene references none: T1 and a crosshair."""
    out = tmp_path / "run"
    written = roi_confirmation.confirm_rois(
        [{"sphere": ((2.0, -1.0, -3.0), 3.0), "name": "target"}],
        m2m=str(m2m),
        out_dir=str(out),
    )
    assert len(written) == 1
    assert written[0]["rule"] == "sphere"
    assert written[0]["spheres"] == [{"centre_ras": [2.0, -1.0, -3.0], "radius_mm": 3.0}]
    assert _listing(out) == {SCENE}
    scene = _scene(out)
    assert [d["name"] for d in scene["datasets"]] == ["T1.nii.gz"]
    assert scene["cursor"] == pytest.approx([2.0, -1.0, -3.0])
