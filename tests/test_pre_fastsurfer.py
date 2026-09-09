"""Unit tests for :mod:`tit.pre.fastsurfer`.

The runner is always mocked -- FastSurfer itself takes ~5 minutes and 4.8 GiB
per subject (``docs/dev/HISTORY.md § 2026-09-03``). One integration test
at the bottom runs the real thing, and skips unless ``$FASTSURFER_HOME`` points
at a checkout (it will run inside the TI-Toolbox image, per plan D1).
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tit.paths import get_path_manager, reset_path_manager
from tit.pre import fastsurfer as fs
from tit.pre.utils import PreprocessError


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project root with one subject's BIDS T1w in place."""
    reset_path_manager()
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    pm = get_path_manager(str(tmp_path))
    anat = Path(pm.bids_anat("001"))
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii.gz").write_bytes(b"")
    yield tmp_path
    reset_path_manager()


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """A directory that looks like a FastSurfer checkout."""
    home = tmp_path / "fastsurfer_home"
    home.mkdir()
    script = home / fs.RUN_SCRIPT
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    monkeypatch.setenv(fs.ENV_FASTSURFER_HOME, str(home))
    return home


# ── capability probe ─────────────────────────────────────────────────────────


class TestAvailability:
    def test_home_defaults_to_the_image_path(self, monkeypatch):
        monkeypatch.delenv(fs.ENV_FASTSURFER_HOME, raising=False)
        assert fs.fastsurfer_home() == Path(fs.DEFAULT_FASTSURFER_HOME)

    def test_empty_env_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv(fs.ENV_FASTSURFER_HOME, "")
        assert fs.fastsurfer_home() == Path(fs.DEFAULT_FASTSURFER_HOME)

    def test_env_wins(self, fake_home):
        assert fs.fastsurfer_home() == fake_home

    def test_available_when_the_script_is_there(self, fake_home):
        assert fs.fastsurfer_available() is True
        assert fs.fastsurfer_script() == fake_home / fs.RUN_SCRIPT

    def test_unavailable_without_the_script(self, tmp_path, monkeypatch):
        monkeypatch.setenv(fs.ENV_FASTSURFER_HOME, str(tmp_path / "nope"))
        assert fs.fastsurfer_available() is False
        assert fs.fastsurfer_script() is None


class TestThreadResolution:
    def test_explicit_argument_wins(self, monkeypatch):
        monkeypatch.setenv(fs.ENV_FASTSURFER_THREADS, "9")
        assert fs.resolve_threads(4) == 4

    def test_env_is_read_when_no_argument(self, monkeypatch):
        monkeypatch.setenv(fs.ENV_FASTSURFER_THREADS, "7")
        assert fs.resolve_threads() == 7

    def test_garbage_env_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv(fs.ENV_FASTSURFER_THREADS, "many")
        assert fs.resolve_threads() == fs.DEFAULT_THREADS

    def test_zero_is_clamped_to_one(self, monkeypatch):
        monkeypatch.delenv(fs.ENV_FASTSURFER_THREADS, raising=False)
        assert fs.resolve_threads(0) == 1


class TestPython:
    def test_defaults_to_simnibs_python(self, monkeypatch):
        monkeypatch.delenv(fs.ENV_FASTSURFER_PYTHON, raising=False)
        assert fs.fastsurfer_python() == "simnibs_python"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv(fs.ENV_FASTSURFER_PYTHON, "/opt/venv/bin/python3")
        assert fs.fastsurfer_python() == "/opt/venv/bin/python3"


# ── run_fastsurfer ───────────────────────────────────────────────────────────


def _runner(exit_code=0, on_run=None):
    runner = MagicMock()

    def _run(cmd, **kwargs):
        if on_run is not None:
            on_run(cmd)
        return exit_code

    runner.run.side_effect = _run
    return runner


class TestRunFastsurfer:
    def test_clear_error_when_fastsurfer_is_absent(
        self, project, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(fs.ENV_FASTSURFER_HOME, str(tmp_path / "absent"))
        with pytest.raises(PreprocessError) as exc:
            fs.run_fastsurfer(str(project), "001", logger=MagicMock(), runner=_runner())
        message = str(exc.value)
        assert "FastSurfer is not installed" in message
        assert fs.RUN_SCRIPT in message

    def test_missing_t1_is_an_error(self, project, fake_home):
        pm = get_path_manager(str(project))
        os.remove(Path(pm.bids_anat("001")) / "sub-001_T1w.nii.gz")
        with pytest.raises(PreprocessError, match="No T1 file found"):
            fs.run_fastsurfer(str(project), "001", logger=MagicMock(), runner=_runner())

    def test_command_shape(self, project, fake_home, monkeypatch):
        seen = {}

        def capture(cmd):
            seen["cmd"] = cmd
            # Pretend FastSurfer wrote its output.
            pm = get_path_manager(str(project))
            mri = Path(pm.fastsurfer_mri("001"))
            mri.mkdir(parents=True, exist_ok=True)
            (mri / fs.SEG_FILENAME).write_bytes(b"")

        monkeypatch.setattr(fs, "write_derived_outputs", lambda *a, **k: None)
        fs.run_fastsurfer(
            str(project),
            "001",
            logger=MagicMock(),
            runner=_runner(on_run=capture),
            threads=5,
        )

        cmd = seen["cmd"]
        assert cmd[0] == str(fake_home / fs.RUN_SCRIPT)
        assert "--seg_only" in cmd
        assert (
            "--allow_root" in cmd
        )  # the container runs as root; FastSurfer refuses without it
        # --no_cc is mandatory: without it the CC module downloads 81 MB of
        # unused checkpoints and crashed in the spike.
        assert "--no_cc" in cmd
        assert "--no_cereb" in cmd
        assert "--no_hypothal" in cmd
        assert cmd[cmd.index("--sid") + 1] == "sub-001"
        assert cmd[cmd.index("--device") + 1] == "auto"
        assert cmd[cmd.index("--threads") + 1] == "5"
        assert cmd[cmd.index("--py") + 1] == "simnibs_python"

        pm = get_path_manager(str(project))
        assert cmd[cmd.index("--sd") + 1] == str(Path(pm.fastsurfer()))
        # The raw BIDS T1w, not charm's m2m copy.
        assert cmd[cmd.index("--t1") + 1] == str(
            Path(pm.bids_anat("001")) / "sub-001_T1w.nii.gz"
        )

    def test_nonzero_exit_raises(self, project, fake_home):
        with pytest.raises(PreprocessError, match="exit 3"):
            fs.run_fastsurfer(
                str(project),
                "001",
                logger=MagicMock(),
                runner=_runner(exit_code=3),
            )

    def test_success_without_output_raises(self, project, fake_home):
        with pytest.raises(PreprocessError, match="was not written"):
            fs.run_fastsurfer(str(project), "001", logger=MagicMock(), runner=_runner())

    def test_skips_when_the_segmentation_exists(self, project, fake_home, monkeypatch):
        pm = get_path_manager(str(project))
        mri = Path(pm.fastsurfer_mri("001"))
        mri.mkdir(parents=True)
        (mri / fs.SEG_FILENAME).write_bytes(b"")

        calls = []
        monkeypatch.setattr(
            fs, "write_derived_outputs", lambda *a, **k: calls.append("derived")
        )
        runner = _runner()
        fs.run_fastsurfer(str(project), "001", logger=MagicMock(), runner=runner)

        runner.run.assert_not_called()
        # The derived NIfTI/labels are still backfilled for an older run.
        assert calls == ["derived"]


class TestWriteDerivedOutputs:
    def test_missing_segmentation_is_an_error(self, tmp_path):
        with pytest.raises(PreprocessError, match="not found"):
            fs.write_derived_outputs(tmp_path, logger=MagicMock())

    def test_existing_derived_files_are_left_alone(self, tmp_path, monkeypatch):
        (tmp_path / fs.SEG_FILENAME).write_bytes(b"")
        (tmp_path / fs.SEG_NIFTI_FILENAME).write_bytes(b"nifti")
        (tmp_path / fs.SEG_LABELS_FILENAME).write_text("labels")

        def _boom(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("should not rewrite an existing derived file")

        monkeypatch.setattr(fs, "_write_nifti_copy", _boom)
        monkeypatch.setattr(fs, "_write_labels_sidecar", _boom)
        fs.write_derived_outputs(tmp_path, logger=MagicMock())

        assert (tmp_path / fs.SEG_NIFTI_FILENAME).read_bytes() == b"nifti"

    def test_labels_sidecar_name_matches_the_atlas_reader(self):
        """The reader derives the sidecar name from either atlas filename."""
        from tit.atlas.voxel import VoxelAtlasManager

        for atlas in (fs.SEG_FILENAME, fs.SEG_NIFTI_FILENAME):
            stem = os.path.splitext(atlas)[0]
            if stem.endswith(".nii"):
                stem = os.path.splitext(stem)[0]
            assert f"{stem}_labels.txt" == fs.SEG_LABELS_FILENAME

        assert hasattr(VoxelAtlasManager, "list_regions")


# ── integration (real FastSurfer, skipped unless present) ────────────────────


@pytest.mark.skipif(
    not (Path(os.environ.get("FASTSURFER_HOME") or "/opt/fastsurfer")).is_dir(),
    reason="requires a FastSurfer checkout at $FASTSURFER_HOME",
)
def test_real_fastsurfer_checkout_is_runnable():
    """The installed checkout exposes a runnable ``run_fastsurfer.sh``.

    Deliberately does not run a segmentation (~5 min, 4.8 GiB): the full
    smoke command for Phase C is in
    ``docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)``.
    """
    script = fs.fastsurfer_script()
    assert script is not None, f"no {fs.RUN_SCRIPT} under {fs.fastsurfer_home()}"
    assert os.access(script, os.X_OK)
    assert fs.fastsurfer_available() is True


@pytest.mark.parametrize("device", ["auto", "cpu", "mps", "cuda", "cuda:1"])
def test_device_override(monkeypatch, device):
    monkeypatch.setenv(fs.ENV_FASTSURFER_DEVICE, device)
    assert fs.resolve_device() == device


def test_default_uses_upstream_auto_detection(monkeypatch):
    monkeypatch.delenv(fs.ENV_FASTSURFER_DEVICE, raising=False)
    assert fs.resolve_device() == "auto"


def test_invalid_device_fails_before_launch(monkeypatch):
    monkeypatch.setenv(fs.ENV_FASTSURFER_DEVICE, "gpu")
    with pytest.raises(PreprocessError, match="cuda"):
        fs.resolve_device()


def test_mps_fallback_is_child_only_and_preserves_override(monkeypatch):
    monkeypatch.delenv("PYTORCH_ENABLE_MPS_FALLBACK", raising=False)
    assert fs.inference_environment()["PYTORCH_ENABLE_MPS_FALLBACK"] == "1"
    assert "PYTORCH_ENABLE_MPS_FALLBACK" not in os.environ
    monkeypatch.setenv("PYTORCH_ENABLE_MPS_FALLBACK", "0")
    assert fs.inference_environment()["PYTORCH_ENABLE_MPS_FALLBACK"] == "0"


def test_unavailable_explicit_device_explains_cpu_image(monkeypatch):
    monkeypatch.setattr(fs.subprocess, "run", lambda *a, **kw: MagicMock(returncode=1))
    with pytest.raises(PreprocessError, match="CPU-only"):
        fs._validate_device("cuda", fs.inference_environment())


def test_probe_uses_selected_interpreter_and_device(monkeypatch):
    monkeypatch.setenv(fs.ENV_FASTSURFER_PYTHON, "/native/fastsurfer/python")
    run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(fs.subprocess, "run", run)
    env = fs.inference_environment()
    fs._validate_device("mps", env)
    assert run.call_args.args[0][0] == "/native/fastsurfer/python"
    assert run.call_args.args[0][-1] == "mps"
    assert run.call_args.kwargs["env"] is env


@pytest.mark.parametrize("device", ["auto", "cpu"])
def test_default_devices_do_not_probe_torch_in_server(monkeypatch, device):
    run = MagicMock()
    monkeypatch.setattr(fs.subprocess, "run", run)
    fs._validate_device(device, fs.inference_environment())
    run.assert_not_called()


@pytest.mark.parametrize(
    "config, memory",
    [
        ({"run_fastsurfer": True}, 8),
        ({"run_fastsurfer": False, "create_m2m": True}, 6),
        ({"run_fastsurfer": True, "memory_gb": 12}, 12),
        ({"run_fastsurfer": True, "mem_gb": 10}, 10),
    ],
)
def test_fastsurfer_memory_budget_only_changes_its_stage(config, memory):
    from tit.jobs.costs import default_cost

    cost = default_cost("pre", config)
    assert cost.mem_gb == memory
    assert cost.cpus == 2
