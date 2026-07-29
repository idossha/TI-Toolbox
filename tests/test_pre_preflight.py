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
    find_missing_preprocessing_inputs,
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
    for output_dir in (
        tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001",
        tmp_path / "derivatives" / "freesurfer" / "sub-001",
        tmp_path / "derivatives" / "qsiprep" / "sub-001",
        tmp_path / "derivatives" / "qsirecon" / "sub-001",
    ):
        output_dir.mkdir(parents=True)
        (output_dir / "output.txt").touch()
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


def test_empty_output_directories_are_not_existing_outputs(tmp_path):
    """Older releases pre-created empty per-subject dirs; ignore them."""
    (tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001").mkdir(parents=True)
    (tmp_path / "derivatives" / "freesurfer" / "sub-001").mkdir(parents=True)
    (tmp_path / "derivatives" / "qsiprep" / "sub-001").mkdir(parents=True)
    (tmp_path / "derivatives" / "qsirecon" / "sub-001").mkdir(parents=True)

    outputs = find_existing_preprocessing_outputs(
        str(tmp_path),
        ["001"],
        create_m2m=True,
        run_recon=True,
        run_qsiprep=True,
        run_qsirecon=True,
    )

    assert outputs == []


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


def test_dicom_output_detects_dwi_with_bval_bvec(tmp_path):
    dwi_dir = tmp_path / "sub-001" / "dwi"
    dwi_dir.mkdir(parents=True)
    nifti = dwi_dir / "sub-001_dwi.nii.gz"
    bval = dwi_dir / "sub-001_dwi.bval"
    bvec = dwi_dir / "sub-001_dwi.bvec"
    for path in (nifti, bval, bvec):
        path.touch()

    outputs = existing_outputs_for_step(str(tmp_path), "001", STEP_DICOM)

    assert len(outputs) == 1
    assert outputs[0].path == nifti
    assert set(outputs[0].paths_to_remove) == {nifti, bval, bvec}


def test_missing_outputs_are_ignored(tmp_path):
    outputs = find_existing_preprocessing_outputs(
        str(tmp_path),
        ["001"],
        create_m2m=True,
        run_qsiprep=True,
    )

    assert outputs == []


def test_missing_t1_input_detected_for_charm(tmp_path):
    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        create_m2m=True,
    )

    assert len(problems) == 1
    assert problems[0].step == STEP_CHARM
    assert "requires a BIDS T1w image" in problems[0].message


def test_missing_t1_input_ignored_when_dicom_conversion_selected(tmp_path):
    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        convert_dicom=True,
        create_m2m=True,
    )

    assert problems == []


def test_missing_t1_input_detected_when_dicom_conversion_would_be_skipped(tmp_path):
    anat_dir = tmp_path / "sub-001" / "anat"
    anat_dir.mkdir(parents=True)
    (anat_dir / "sub-001_T2w.nii.gz").touch()

    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        convert_dicom=True,
        create_m2m=True,
        skip_existing_outputs=True,
    )

    assert len(problems) == 1
    assert problems[0].step == STEP_CHARM


def test_missing_t1_input_ignored_when_dicom_conversion_will_run_with_skip_policy(
    tmp_path,
):
    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        convert_dicom=True,
        create_m2m=True,
        skip_existing_outputs=True,
    )

    assert problems == []


def test_present_t1_input_allows_charm(tmp_path):
    anat_dir = tmp_path / "sub-001" / "anat"
    anat_dir.mkdir(parents=True)
    (anat_dir / "sub-001_T1w.nii.gz").touch()

    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        create_m2m=True,
    )

    assert problems == []


def test_missing_dwi_input_detected_for_qsiprep(tmp_path):
    # Provide a T1w so this test isolates the DWI requirement.
    anat_dir = tmp_path / "sub-001" / "anat"
    anat_dir.mkdir(parents=True)
    (anat_dir / "sub-001_T1w.nii.gz").touch()

    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        run_qsiprep=True,
    )

    assert len(problems) == 1
    assert problems[0].step == STEP_QSIPREP
    assert "requires BIDS DWI data" in problems[0].message


def test_missing_t1_input_detected_for_qsiprep(tmp_path):
    """QSIPrep needs a T1w; without one it fails deep in the workflow."""
    dwi_dir = tmp_path / "sub-001" / "dwi"
    dwi_dir.mkdir(parents=True)
    (dwi_dir / "sub-001_dir-RL_dwi.nii.gz").touch()
    (dwi_dir / "sub-001_dir-RL_dwi.bval").touch()
    (dwi_dir / "sub-001_dir-RL_dwi.bvec").touch()

    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        run_qsiprep=True,
    )

    assert len(problems) == 1
    assert problems[0].step == STEP_QSIPREP
    assert "requires a BIDS T1w image" in problems[0].message


def test_present_dwi_input_allows_qsiprep(tmp_path):
    """DWI files may carry extra BIDS entities like dir-RL."""
    anat_dir = tmp_path / "sub-001" / "anat"
    anat_dir.mkdir(parents=True)
    (anat_dir / "sub-001_T1w.nii.gz").touch()
    dwi_dir = tmp_path / "sub-001" / "dwi"
    dwi_dir.mkdir(parents=True)
    (dwi_dir / "sub-001_dir-RL_dwi.nii.gz").touch()
    (dwi_dir / "sub-001_dir-RL_dwi.bval").touch()
    (dwi_dir / "sub-001_dir-RL_dwi.bvec").touch()

    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        run_qsiprep=True,
    )

    assert problems == []


def test_missing_dwi_input_ignored_when_dicom_conversion_selected(tmp_path):
    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        convert_dicom=True,
        run_qsiprep=True,
    )

    assert problems == []
