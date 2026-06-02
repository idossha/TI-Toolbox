import json
from pathlib import Path

import numpy as np
import pytest


class _FakeHeader:
    def copy(self):
        return _FakeHeader()

    def set_data_dtype(self, _dtype):
        return None


class _FakeImage:
    header = _FakeHeader()
    affine = np.eye(4)


def _make_project(tmp_path: Path, subject_id: str = "001") -> Path:
    m2m = (
        tmp_path
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / f"m2m_{subject_id}"
    )
    m2m.mkdir(parents=True)
    (m2m / "T1.nii.gz").touch()
    return tmp_path


def _make_templates(tmp_path: Path) -> Path:
    from tit.tools.thalamus_rois import THALAMUS_SIDES, THALAMUS_TARGETS

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    for target in THALAMUS_TARGETS:
        for side in THALAMUS_SIDES:
            (template_dir / f"thalamus_{target}_{side}_MNI.nii.gz").touch()
            (template_dir / f"thalamus_{target}_{side}_MNI.json").write_text(
                json.dumps(
                    {
                        "name": f"thalamus_{target}_{side}",
                        "space": "MNI",
                        "labels": [{"id": len(target) + len(side), "name": side}],
                    }
                )
            )
    return template_dir


def test_create_thalamus_functional_rois_writes_all_masks(tmp_path, monkeypatch):
    from tit.tools import thalamus_rois

    project = _make_project(tmp_path)
    template_dir = _make_templates(tmp_path)
    saved_masks = {}

    def fake_warp(_source, _m2m_dir, output, _reference):
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).touch()

    def fake_load(path):
        path = Path(path)
        if path in saved_masks:
            return saved_masks[path], _FakeImage()
        mask = np.zeros((2, 2, 2), dtype=bool)
        if "_left_" in path.name:
            mask[0, 0, 0] = True
        elif "_right_" in path.name:
            mask[1, 1, 1] = True
        return mask, _FakeImage()

    def fake_save(mask, _reference_img, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        saved_masks[output_path] = mask.copy()

    monkeypatch.setattr(thalamus_rois, "_warp_volume", fake_warp)
    monkeypatch.setattr(thalamus_rois, "_load_binary_mask", fake_load)
    monkeypatch.setattr(thalamus_rois, "_save_binary_mask", fake_save)

    results = thalamus_rois.create_thalamus_functional_rois(
        project,
        "001",
        template_dir=template_dir,
    )

    assert len(results) == 9
    assert all(result.created for result in results)

    roi_dir = (
        project
        / "derivatives"
        / "SimNIBS"
        / "sub-001"
        / "m2m_001"
        / "ROIs"
        / "thalamus_functional"
    )
    bilateral = roi_dir / "thalamus_anterior_bilateral_sub-001.nii.gz"
    assert bilateral.exists()
    assert int(saved_masks[bilateral].sum()) == 2

    sidecar = json.loads(
        (roi_dir / "thalamus_anterior_bilateral_sub-001.json").read_text()
    )
    assert sidecar["name"] == "thalamus_anterior_bilateral"
    assert sidecar["space"] == "sub-001 subject space"
    assert sidecar["voxels_subject"] == 2
    assert len(sidecar["source_mni_rois"]) == 2


def test_create_thalamus_functional_rois_requires_templates(tmp_path):
    from tit.tools.thalamus_rois import create_thalamus_functional_rois

    project = _make_project(tmp_path)
    empty_template_dir = tmp_path / "empty_templates"
    empty_template_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="Missing functional thalamus"):
        create_thalamus_functional_rois(
            project,
            "001",
            template_dir=empty_template_dir,
        )


def test_preflight_tracks_functional_thalamus_roi_outputs(tmp_path):
    from tit.pre.preflight import (
        STEP_THALAMUS_ROIS,
        existing_outputs_for_step,
        selected_preprocessing_steps,
    )

    project = _make_project(tmp_path)
    roi_dir = (
        project
        / "derivatives"
        / "SimNIBS"
        / "sub-001"
        / "m2m_001"
        / "ROIs"
        / "thalamus_functional"
    )
    roi_dir.mkdir(parents=True)

    assert STEP_THALAMUS_ROIS in selected_preprocessing_steps(run_thalamus_rois=True)
    outputs = existing_outputs_for_step(str(project), "001", STEP_THALAMUS_ROIS)
    assert len(outputs) == 1
    assert outputs[0].path == roi_dir
