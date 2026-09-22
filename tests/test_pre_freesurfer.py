"""FreeSurfer worker lifecycle/argv tests, 2026-09-10.

Authored temporary files pin mount, resume and prerequisite failures. Run
pytest tests/test_pre_freesurfer.py. Actual FreeSurfer computation is separate.
"""

from pathlib import Path
from unittest.mock import Mock
import pytest
from tit.paths import get_path_manager, reset_path_manager
from tit.pre import freesurfer as fs
from tit.pre.utils import PreprocessError, PreprocessCancelled


@pytest.fixture
def project(tmp_path, monkeypatch):
    reset_path_manager()
    pm = get_path_manager(str(tmp_path))
    anat = Path(pm.bids_anat("001"))
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii.gz").write_bytes(b"t1")
    license = tmp_path / "test-license.txt"
    license.write_text("test fixture")
    monkeypatch.setattr(fs, "resolve_fs_license_path", lambda: license)
    monkeypatch.setattr(fs, "get_inherited_dood_resources", lambda: (4, 16))
    monkeypatch.setenv("LOCAL_PROJECT_DIR", "/host/project")
    monkeypatch.setenv("TIT_JOB_ID", "job-123")
    cleanup = Mock(return_value=Mock(returncode=0, stderr=""))
    monkeypatch.setattr(fs.subprocess, "run", cleanup)
    yield pm, cleanup
    reset_path_manager()


def complete(pm):
    subject = Path(pm.freesurfer_subject("001"))
    for name in (
        "scripts/recon-all.done",
        "mri/norm.mgz",
        "mri/aseg.mgz",
        "mri/wmparc.mgz",
    ):
        path = subject / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")


def test_reconstruction_mounts_and_cleanup(project):
    pm, cleanup = project

    def success(argv, **kwargs):
        complete(pm)
        return 0

    runner = Mock()
    runner.run.side_effect = success
    fs.run_freesurfer(
        "001",
        subregions=["thalamus", "hippo-amygdala"],
        threads=2,
        runner=runner,
        logger=Mock(),
    )
    assert runner.run.call_count == 3
    commands = [call.args[0] for call in runner.run.call_args_list]
    for argv in commands:
        assert "--rm" in argv
        assert "tit.job_id=job-123" in argv
        assert f"/host/project:{pm.project_dir}" in argv
        assert argv[argv.index("--cpus") + 1] == "2"
        assert "idossha/ti-toolbox:freesurfer-20260910" in argv
    assert "-i" in commands[0]
    assert commands[1][commands[1].index("segment_subregions") :] == [
        "segment_subregions",
        "thalamus",
        "--cross",
        "sub-001",
        "--sd",
        pm.freesurfer(),
        "--threads",
        "2",
    ]
    assert "hippo-amygdala" in commands[2]
    assert cleanup.call_count == 3
    assert not list(Path(pm.project_dir).glob(".freesurfer-*"))
    assert Path(pm.freesurfer_mri("001"), "aseg.mgz").is_file()


@pytest.mark.parametrize(
    "error", [PreprocessCancelled("cancel"), RuntimeError("worker crash")]
)
def test_failure_removes_worker_and_license_preserves_data(project, error):
    pm, cleanup = project
    complete(pm)
    runner = Mock()
    runner.run.side_effect = error
    with pytest.raises(type(error)):
        fs.run_freesurfer(
            "001",
            recon_all=False,
            subregions=["thalamus"],
            runner=runner,
            logger=Mock(),
        )
    name = runner.run.call_args.args[0][
        runner.run.call_args.args[0].index("--name") + 1
    ]
    assert cleanup.call_args.args[0] == ["docker", "rm", "-f", name]
    assert Path(pm.freesurfer_mri("001"), "aseg.mgz").is_file()
    assert not list(Path(pm.project_dir).glob(".freesurfer-*"))


def test_no_subregions_without_reconstruction(project):
    runner = Mock()
    with pytest.raises(PreprocessError, match="completed recon-all"):
        fs.run_freesurfer(
            "001",
            recon_all=False,
            subregions=["thalamus"],
            runner=runner,
            logger=Mock(),
        )
    runner.run.assert_not_called()


def test_missing_license(project, monkeypatch):
    monkeypatch.setattr(fs, "resolve_fs_license_path", lambda: None)
    runner = Mock()
    with pytest.raises(PreprocessError, match="license supplied by TI-Toolbox"):
        fs.run_freesurfer("001", runner=runner, logger=Mock())
    runner.run.assert_not_called()


def test_resume_does_not_reimport_t1(project):
    pm, _ = project
    complete(pm)
    orig = Path(pm.freesurfer_subject("001"), "mri/orig/001.mgz")
    orig.parent.mkdir()
    orig.write_bytes(b"original")
    runner = Mock()
    runner.run.return_value = 0
    fs.run_freesurfer("001", runner=runner, logger=Mock())
    assert "-i" not in runner.run.call_args.args[0]


def test_nonzero_exit_is_failure(project):
    runner = Mock()
    runner.run.return_value = 7
    with pytest.raises(PreprocessError, match="exit 7"):
        fs.run_freesurfer("001", runner=runner, logger=Mock())
    assert project[1].call_count == 1


def test_success_without_reconstruction_outputs_is_failure(project):
    runner = Mock()
    runner.run.return_value = 0
    with pytest.raises(PreprocessError, match="completed recon-all"):
        fs.run_freesurfer("001", runner=runner, logger=Mock())
    assert project[1].call_count == 1


def test_subregion_requests_are_deduplicated(project):
    complete(project[0])
    runner = Mock()
    runner.run.return_value = 0
    fs.run_freesurfer(
        "001",
        recon_all=False,
        subregions=["thalamus", "thalamus"],
        runner=runner,
        logger=Mock(),
    )
    assert runner.run.call_count == 1


def test_cleanup_errors_do_not_hide_job_error(project):
    project[1].side_effect = OSError("docker unavailable")
    runner = Mock()
    runner.run.return_value = 3
    with pytest.raises(PreprocessError, match="exit 3"):
        fs.run_freesurfer("001", runner=runner, logger=Mock())


def test_default_limits_match_reserved_job_budget(project, monkeypatch):
    from tit import surfer_settings

    monkeypatch.setattr(surfer_settings, "available_threads", lambda: 10)
    monkeypatch.setattr(
        surfer_settings,
        "load_preferences",
        lambda: {"fastsurfer_threads": None, "freesurfer_threads": None},
    )
    complete(project[0])
    monkeypatch.setattr(fs, "get_inherited_dood_resources", lambda: (32, 128))
    runner = Mock()
    runner.run.return_value = 0
    fs.run_freesurfer(
        "001", recon_all=False, subregions=["thalamus"], runner=runner, logger=Mock()
    )
    argv = runner.run.call_args.args[0]
    # available_threads is already the global CPU limit, so the default is all of it.
    assert argv[argv.index("--cpus") + 1] == "10"
    assert argv[argv.index("--memory") + 1] == "16g"
    assert argv[-2:] == ["--threads", "10"]


def test_container_requires_host_project_mapping(project, monkeypatch):
    monkeypatch.delenv("LOCAL_PROJECT_DIR")
    real_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda path: True if str(path) == "/.dockerenv" else real_exists(path),
    )
    runner = Mock()
    with pytest.raises(PreprocessError, match="LOCAL_PROJECT_DIR is required"):
        fs.run_freesurfer("001", runner=runner, logger=Mock())
    runner.run.assert_not_called()


def test_explicit_threads_are_capped_at_container_limit(project, roomy_cpus):
    complete(project[0])
    runner = Mock()
    runner.run.return_value = 0
    fs.run_freesurfer(
        "001",
        recon_all=False,
        subregions=["thalamus"],
        threads=32,
        runner=runner,
        logger=Mock(),
    )
    argv = runner.run.call_args.args[0]
    assert argv[argv.index("--cpus") + 1] == "4"
    assert argv[-2:] == ["--threads", "4"]


def test_insufficient_memory_fails_before_worker(project, monkeypatch):
    monkeypatch.setattr(fs, "get_inherited_dood_resources", lambda: (4, 8))
    runner = Mock()
    with pytest.raises(PreprocessError, match="at least 16 GiB"):
        fs.run_freesurfer("001", runner=runner, logger=Mock())
    runner.run.assert_not_called()


def test_reconstruction_automatically_mounts_bundled_license(
    project, monkeypatch, tmp_path
):
    import hashlib
    from tit import surfer_settings as prefs
    from tit.pre.qsi.docker_builder import resolve_fs_license_path

    pm, _ = project
    monkeypatch.setattr(fs, "resolve_fs_license_path", resolve_fs_license_path)
    monkeypatch.delenv("FS_LICENSE", raising=False)
    monkeypatch.setattr(
        prefs.PathManager,
        "user_config_dir",
        staticmethod(lambda: str(tmp_path / "config")),
    )
    monkeypatch.setattr(
        "tit.pre.qsi.docker_builder.const.FS_LICENSE_PATH", str(tmp_path / "missing")
    )
    bundled = (
        Path(__file__).resolve().parents[1] / "tit/resources/freesurfer/license.txt"
    )
    monkeypatch.setattr(prefs, "BUNDLED_FS_LICENSE_PATH", bundled)

    def success(argv, **kwargs):
        mount = next(arg for arg in argv if arg.endswith(":/run/license.txt:ro"))
        host_path = Path(mount.removesuffix(":/run/license.txt:ro"))
        staged = Path(pm.project_dir) / host_path.relative_to("/host/project")
        assert (
            hashlib.sha256(staged.read_bytes()).digest()
            == hashlib.sha256(bundled.read_bytes()).digest()
        )
        assert "FS_LICENSE=/run/license.txt" in argv
        complete(pm)
        return 0

    runner = Mock()
    runner.run.side_effect = success
    fs.run_freesurfer("001", subregions=[], runner=runner, logger=Mock())
    runner.run.assert_called_once()
    assert not list(Path(pm.project_dir).glob(".freesurfer-*"))
