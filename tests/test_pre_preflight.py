"""Tests for preprocessing output preflight helpers."""

from pathlib import Path

from tit.pre.preflight import (
    STEP_CHARM,
    STEP_DICOM,
    STEP_DTI,
    STEP_QSIPREP,
    STEP_QSIRECON,
    STEP_RECON_ALL,
    existing_outputs_for_step,
    find_existing_preprocessing_outputs,
    remove_preprocessing_output,
    selected_preprocessing_steps,
)


def test_selected_preprocessing_steps_preserves_pipeline_order():
    steps = selected_preprocessing_steps(
        convert_dicom=True,
        create_m2m=True,
        run_recon=True,
        run_qsiprep=True,
        run_qsirecon=True,
        extract_dti=True,
    )

    assert steps == [
        STEP_DICOM,
        STEP_CHARM,
        STEP_RECON_ALL,
        STEP_QSIPREP,
        STEP_QSIRECON,
        STEP_DTI,
    ]


def test_find_existing_structural_and_qsi_outputs(tmp_path):
    subject_id = "001"
    (tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001").mkdir(
        parents=True
    )
    (tmp_path / "derivatives" / "freesurfer" / "sub-001").mkdir(parents=True)
    (tmp_path / "derivatives" / "qsiprep" / "sub-001").mkdir(parents=True)
    (tmp_path / "derivatives" / "qsirecon" / "sub-001").mkdir(parents=True)
    dti = (
        tmp_path
        / "derivatives"
        / "SimNIBS"
        / "sub-001"
        / "m2m_001"
        / "DTI_coregT1_tensor.nii.gz"
    )
    dti.touch()

    outputs = find_existing_preprocessing_outputs(
        str(tmp_path),
        [subject_id],
        create_m2m=True,
        run_recon=True,
        run_qsiprep=True,
        run_qsirecon=True,
        extract_dti=True,
    )

    assert {output.step for output in outputs} == {
        STEP_CHARM,
        STEP_RECON_ALL,
        STEP_QSIPREP,
        STEP_QSIRECON,
        STEP_DTI,
    }


def test_dicom_output_detects_sidecars_and_removes_them(tmp_path):
    anat_dir = tmp_path / "sub-001" / "anat"
    anat_dir.mkdir(parents=True)
    nifti = anat_dir / "sub-001_T1w.nii.gz"
    sidecar = anat_dir / "sub-001_T1w.json"
    nifti.touch()
    sidecar.touch()

    outputs = existing_outputs_for_step(str(tmp_path), "001", STEP_DICOM)

    assert len(outputs) == 1
    assert outputs[0].path == nifti
    assert set(outputs[0].paths_to_remove) == {nifti, sidecar}

    remove_preprocessing_output(outputs[0])

    assert not nifti.exists()
    assert not sidecar.exists()


def test_missing_outputs_are_ignored(tmp_path):
    outputs = find_existing_preprocessing_outputs(
        str(tmp_path),
        ["001"],
        create_m2m=True,
        run_qsiprep=True,
    )

    assert outputs == []
