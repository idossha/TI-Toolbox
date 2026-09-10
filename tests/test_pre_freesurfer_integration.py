"""Optional FreeSurfer plan, prerequisites, and bounded overwrite regression tests."""

import pytest
from fastapi import HTTPException

from tit.paths import get_path_manager
from tit.pre.config import PreprocessConfig
from tit.pre.preflight import (
    STEP_FREESURFER_THALAMUS,
    existing_outputs_for_step,
    find_missing_preprocessing_inputs,
    remove_preprocessing_output,
    selected_preprocessing_steps,
)


def reconstruction(root):
    subject = root / "derivatives/freesurfer/sub-001"
    for name in (
        "scripts/recon-all.done",
        "mri/norm.mgz",
        "mri/aseg.mgz",
        "mri/wmparc.mgz",
    ):
        path = subject / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"reconstruction")
    return subject


@pytest.fixture
def licensed_project(tmp_path, monkeypatch):
    get_path_manager(str(tmp_path))
    license_path = tmp_path / "license.txt"
    license_path.write_text("fixture")
    monkeypatch.setenv("FS_LICENSE", str(license_path))
    return tmp_path


def test_default_remains_optional_and_configuration_validates():
    config = PreprocessConfig(subject_ids=["001"])
    assert not config.run_freesurfer
    assert config.freesurfer_recon_all
    assert config.freesurfer_subregions == []
    for kwargs in (
        {"freesurfer_threads": 0},
        {"freesurfer_threads": True},
        {"freesurfer_subregions": ["invalid"]},
        {"run_freesurfer": True, "freesurfer_recon_all": False},
    ):
        with pytest.raises(ValueError):
            PreprocessConfig(subject_ids=["001"], **kwargs)


def test_stage_config_separates_freesurfer_and_preserves_selected_subregions():
    from tit.jobs.plans import plan_preprocessing

    config = PreprocessConfig(
        subject_ids=["001"],
        convert_dicom=True,
        run_fastsurfer=True,
        run_freesurfer=True,
        freesurfer_subregions=["thalamus"],
    )
    jobs = plan_preprocessing(config, ["001"])
    stage = next(j for j in jobs if "freesurfer" in j.tags)
    assert stage.label == "001:G2c"
    assert stage.after_labels == ["001:G1"]
    assert stage.config["run_freesurfer"] is True
    assert stage.config["run_fastsurfer"] is False
    assert stage.config["freesurfer_subregions"] == ["thalamus"]
    assert all(not j.config["run_freesurfer"] for j in jobs if j is not stage)


def test_selection_and_subregion_cleanup_preserve_reconstruction(licensed_project):
    subject = reconstruction(licensed_project)
    thalamus = subject / "mri/ThalamicNuclei.mgz"
    hippocampus = subject / "mri/lh.hippoAmygLabels.mgz"
    legacy = subject / "mri/ThalamicNuclei.v12.T1.mgz"
    legacy.write_bytes(b"legacy")
    thalamus.write_bytes(b"thalamus")
    hippocampus.write_bytes(b"hippocampus")
    assert selected_preprocessing_steps(
        run_freesurfer=True,
        freesurfer_recon_all=False,
        freesurfer_subregions=["thalamus"],
    ) == [STEP_FREESURFER_THALAMUS]
    outputs = existing_outputs_for_step(
        str(licensed_project), "001", STEP_FREESURFER_THALAMUS
    )
    assert len(outputs) == 1
    remove_preprocessing_output(outputs[0])
    assert not thalamus.exists()
    assert hippocampus.exists()
    assert legacy.read_bytes() == b"legacy"
    assert (subject / "mri/aseg.mgz").read_bytes() == b"reconstruction"
    assert (subject / "scripts/recon-all.done").exists()


def test_subregions_require_recon_all_not_only_segmentation(licensed_project):
    subject = reconstruction(licensed_project)
    (subject / "scripts/recon-all.done").unlink()
    problems = find_missing_preprocessing_inputs(
        str(licensed_project),
        ["001"],
        run_freesurfer=True,
        freesurfer_recon_all=False,
        freesurfer_subregions=["thalamus"],
    )
    assert len(problems) == 1
    assert "completed recon-all" in problems[0].message
    assert problems[0].step == STEP_FREESURFER_THALAMUS


def test_full_recon_provides_subregion_inputs_but_skip_does_not(licensed_project):
    reconstruction(licensed_project)
    (
        licensed_project / "derivatives/freesurfer/sub-001/scripts/recon-all.done"
    ).unlink()
    anat = licensed_project / "sub-001/anat"
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii").write_bytes(b"t1")
    options = dict(run_freesurfer=True, freesurfer_subregions=["thalamus"])
    assert not find_missing_preprocessing_inputs(
        str(licensed_project), ["001"], **options
    )
    assert find_missing_preprocessing_inputs(
        str(licensed_project), ["001"], skip_existing_outputs=True, **options
    )


def test_submission_checks_license_and_complete_recon_before_queue(
    licensed_project, monkeypatch
):
    from tit.server.routes.jobs import _check_freesurfer_inputs

    with pytest.raises(HTTPException, match="") as caught:
        _check_freesurfer_inputs(
            "pre",
            {
                "run_freesurfer": True,
                "freesurfer_recon_all": False,
                "freesurfer_subregions": ["thalamus"],
            },
            ["001"],
        )
    assert caught.value.status_code == 422
    reconstruction(licensed_project)
    _check_freesurfer_inputs(
        "pre",
        {
            "run_freesurfer": True,
            "freesurfer_recon_all": False,
            "freesurfer_subregions": ["thalamus"],
        },
        ["001"],
    )
    monkeypatch.setattr(
        "tit.pre.qsi.docker_builder.resolve_fs_license_path", lambda: None
    )
    with pytest.raises(HTTPException) as caught:
        _check_freesurfer_inputs(
            "pre",
            {
                "run_freesurfer": True,
                "freesurfer_recon_all": False,
                "freesurfer_subregions": ["thalamus"],
            },
            ["001"],
        )
    assert "license" in caught.value.detail


def test_scheduler_locks_cost_and_cancellation_eligibility():
    from tit.jobs.costs import default_cost
    from tit.jobs.kinds import may_spawn_docker_siblings
    from tit.jobs.locks import keys_for

    config = {"run_freesurfer": True, "freesurfer_threads": 4}
    assert default_cost("pre", config).cpus == 4
    assert default_cost("pre", config).mem_gb == 16
    assert may_spawn_docker_siblings("pre", config)
    assert any(
        "freesurfer" in str(request) for request in keys_for("pre", ["001"], config)
    )


def test_overwrite_permission_only_considers_selected_outputs(
    licensed_project, monkeypatch
):
    from tit.server.overwrite_policy import check_overwrite_permission

    monkeypatch.setattr("tit.server.routes.settings._load_project_settings", lambda: {})
    subject = reconstruction(licensed_project)
    config = {
        "run_freesurfer": True,
        "freesurfer_recon_all": False,
        "freesurfer_subregions": ["thalamus"],
        "replace_existing_outputs": True,
    }
    check_overwrite_permission("pre", config, ["001"])
    (subject / "mri/ThalamicNuclei.mgz").write_bytes(b"existing")
    with pytest.raises(HTTPException) as caught:
        check_overwrite_permission("pre", config, ["001"])
    assert caught.value.status_code == 403


def test_pipeline_skips_reconstruction_and_runs_only_selected_missing_subregion(
    licensed_project, monkeypatch
):
    from unittest.mock import Mock
    from tit.pre import structural

    subject = reconstruction(licensed_project)
    existing = subject / "mri/ThalamicNuclei.mgz"
    existing.write_bytes(b"existing-thalamus")
    worker = Mock()
    monkeypatch.setattr(structural, "run_freesurfer_worker", worker)
    monkeypatch.setattr(structural, "build_logger", lambda *a, **kw: Mock())
    structural._run_subject_pipeline(
        str(licensed_project),
        "001",
        runner=Mock(),
        run_freesurfer=True,
        freesurfer_subregions=["thalamus", "hippo-amygdala"],
        skip_existing_outputs=True,
    )
    assert worker.call_args.kwargs["recon_all"] is False
    assert worker.call_args.kwargs["subregions"] == ["hippo-amygdala"]
    assert existing.read_bytes() == b"existing-thalamus"
    assert (subject / "scripts/recon-all.done").exists()


def test_freesurfer_eta_is_unknown_instead_of_fastsurfer_estimate():
    from tit.jobs.eta import eta_minutes

    assert eta_minutes("pre", {"run_freesurfer": True}) is None
    assert eta_minutes("pre", {}, resolved={"stages": [{"tags": ["G2c"]}]}) is None
