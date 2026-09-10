"""Tests for tit.pre.qsi.docker_builder — Docker command builder."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit import constants as const
from tit.pre.qsi.docker_builder import (
    DockerBuildError,
    DockerCommandBuilder,
    DockerPaths,
)
from tit.pre.qsi.config import QSIPrepConfig, QSIReconConfig, ResourceConfig

MODULE = "tit.pre.qsi.docker_builder"


@pytest.fixture
def builder():
    """Create a DockerCommandBuilder with mocked dependencies."""
    with patch(f"{MODULE}.get_host_project_dir", return_value="/host/project"):
        b = DockerCommandBuilder("/container/project")
        b._host_license_path = "/host/project/.freesurfer_license.txt"
        return b


class TestDockerPaths:
    """Tests for DockerPaths defaults."""

    def test_defaults(self):
        paths = DockerPaths()
        assert paths.bids_dir == "/data"
        assert paths.output_dir == "/out"
        assert paths.work_dir == "/work"


class TestDockerBuildError:
    """Tests for DockerBuildError."""

    def test_is_exception(self):
        with pytest.raises(DockerBuildError):
            raise DockerBuildError("test")


class TestDockerCommandBuilder:
    """Tests for DockerCommandBuilder."""

    def test_init(self, builder):
        assert builder._host_project_dir == "/host/project"
        assert builder._host_license_path == "/host/project/.freesurfer_license.txt"

    def test_custom_paths(self):
        custom = DockerPaths(bids_dir="/custom/data")
        with patch(f"{MODULE}.get_host_project_dir", return_value="/host"):
            b = DockerCommandBuilder("/proj", paths=custom)
            assert b.paths.bids_dir == "/custom/data"

    def test_get_output_dir(self, builder):
        result = builder.get_output_dir("qsiprep")
        assert result == Path("/host/project/derivatives/qsiprep")


class TestBuildQsiprepCmd:
    """Tests for build_qsiprep_cmd."""

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_basic_command(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)

        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--rm" in cmd
        assert "--participant-label" in cmd
        idx = cmd.index("--participant-label")
        assert cmd[idx + 1] == "001"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_resource_limits(self, mock_resources, builder):
        config = QSIPrepConfig(
            subject_id="001",
            resources=ResourceConfig(cpus=4, memory_gb=16),
        )
        cmd = builder.build_qsiprep_cmd(config)

        idx = cmd.index("--cpus")
        assert cmd[idx + 1] == "4"
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == "16g"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(2, 32))
    def test_omp_threads_clamped_to_nthreads(self, mock_resources, builder):
        # Default omp_threads comes from the raw host cpu count; nthreads is
        # cgroup-aware. A CPU-limited container must not emit omp > nthreads.
        config = QSIPrepConfig(
            subject_id="001", resources=ResourceConfig(omp_threads=8)
        )
        cmd = builder.build_qsiprep_cmd(config)

        assert cmd[cmd.index("--nthreads") + 1] == "2"
        assert int(cmd[cmd.index("--omp-nthreads") + 1]) <= 2
        assert "OMP_NUM_THREADS=2" in cmd
        assert "OMP_NUM_THREADS=8" not in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_inherited_resources(self, mock_resources, builder):
        """Uses inherited resources when not specified."""
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)

        idx = cmd.index("--cpus")
        assert cmd[idx + 1] == "8"
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == "32g"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_skip_bids_validation(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001", skip_bids_validation=True)
        cmd = builder.build_qsiprep_cmd(config)
        assert "--skip-bids-validation" in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_no_skip_bids_validation(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001", skip_bids_validation=False)
        cmd = builder.build_qsiprep_cmd(config)
        assert "--skip-bids-validation" not in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_custom_denoise(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001", denoise_method="patch2self")
        cmd = builder.build_qsiprep_cmd(config)
        idx = cmd.index("--denoise-method")
        assert cmd[idx + 1] == "patch2self"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_default_denoise_always_added(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001", denoise_method="dwidenoise")
        cmd = builder.build_qsiprep_cmd(config)
        idx = cmd.index("--denoise-method")
        assert cmd[idx + 1] == "dwidenoise"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_default_unringing_always_added(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001", unringing_method="mrdegibbs")
        cmd = builder.build_qsiprep_cmd(config)
        idx = cmd.index("--unringing-method")
        assert cmd[idx + 1] == "mrdegibbs"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_custom_unringing(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001", unringing_method="rpg")
        cmd = builder.build_qsiprep_cmd(config)
        idx = cmd.index("--unringing-method")
        assert cmd[idx + 1] == "rpg"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_volume_mounts(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)

        # Check volume mounts
        v_indices = [i for i, x in enumerate(cmd) if x == "-v"]
        assert len(v_indices) >= 3  # bids, output, work (+ optional license)

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_fs_license_uses_host_path(self, mock_resources, builder):
        """License mount source must be the host path, not container path."""
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)
        v_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-v"]
        license_mounts = [v for v in v_args if "license" in v]
        assert len(license_mounts) == 1
        assert license_mounts[0].startswith("/host/project/")

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_no_fs_license(self, mock_resources):
        """No license mount or --fs-license-file when staging fails."""
        with patch(f"{MODULE}.get_host_project_dir", return_value="/host"):
            b = DockerCommandBuilder("/proj")
            b._host_license_path = None
            config = QSIPrepConfig(subject_id="001")
            cmd = b.build_qsiprep_cmd(config)

            v_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-v"]
            assert not any("license" in v for v in v_args)
            assert "--fs-license-file" not in cmd


class TestBuildQsireconCmd:
    """Tests for build_qsirecon_cmd."""

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(2, 32))
    def test_omp_threads_clamped_to_nthreads(self, mock_resources, builder):
        config = QSIReconConfig(
            subject_id="001", resources=ResourceConfig(omp_threads=8)
        )
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        assert cmd[cmd.index("--nthreads") + 1] == "2"
        assert int(cmd[cmd.index("--omp-nthreads") + 1]) <= 2
        assert "OMP_NUM_THREADS=2" in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_basic_command(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001")
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        assert cmd[0] == "docker"
        assert "--recon-spec" in cmd
        idx = cmd.index("--recon-spec")
        assert cmd[idx + 1] == "dipy_dki"
        input_idx = cmd.index("--input-type")
        assert cmd[input_idx + 1] == "qsiprep"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_gpu_flag(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001", use_gpu=True)
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        assert "--gpus" in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_no_gpu(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001", use_gpu=False)
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        assert "--gpus" not in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_atlases(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001", atlases=["AAL116", "4S156Parcels"])
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        idx = cmd.index("--atlases")
        assert cmd[idx + 1] == "AAL116"
        assert cmd[idx + 2] == "4S156Parcels"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_dsi_studio_gqi_without_atlases_stages_scalar_workaround(
        self, mock_resources, tmp_path
    ):
        """dsi_studio_gqi without atlases uses the shipped scalar YAML."""
        with (
            patch(f"{MODULE}.get_host_project_dir", return_value=str(tmp_path)),
            patch(
                f"{MODULE}.const.FS_LICENSE_PATH", str(tmp_path / "missing_license.txt")
            ),
        ):
            builder = DockerCommandBuilder(str(tmp_path))

        config = QSIReconConfig(subject_id="001", atlases=None)
        cmd = builder.build_qsirecon_cmd(config, "dsi_studio_gqi")

        staged_yaml = tmp_path / ".qsirecon_spec.yaml"
        source_yaml = (
            Path(__file__).resolve().parents[1]
            / "resources"
            / "qsirecon_pipelines"
            / "dsi_studio_gqi_scalar.yaml"
        )
        assert staged_yaml.read_text() == source_yaml.read_text()

        v_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-v"]
        assert f"{staged_yaml}:/tmp/recon_spec.yaml:ro" in v_args
        idx = cmd.index("--recon-spec")
        assert cmd[idx + 1] == "/tmp/recon_spec.yaml"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_dsi_studio_gqi_with_atlases_does_not_use_scalar_workaround(
        self, mock_resources, builder
    ):
        """Atlas-enabled dsi_studio_gqi keeps the standard recon spec."""
        builder._stage_custom_pipeline = MagicMock()
        config = QSIReconConfig(subject_id="001", atlases=["AAL116"])
        cmd = builder.build_qsirecon_cmd(config, "dsi_studio_gqi")

        builder._stage_custom_pipeline.assert_not_called()
        assert "/tmp/recon_spec.yaml" not in cmd
        idx = cmd.index("--recon-spec")
        assert cmd[idx + 1] == "dsi_studio_gqi"

        v_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-v"]
        assert not any(".qsirecon_spec.yaml" in v for v in v_args)
        idx = cmd.index("--atlases")
        assert cmd[idx + 1] == "AAL116"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_no_atlases(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001", atlases=None)
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        assert "--atlases" not in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_skip_odf_reports(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001", skip_odf_reports=True)
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        assert "--skip-odf-reports" in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_no_skip_odf(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001", skip_odf_reports=False)
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        assert "--skip-odf-reports" not in cmd

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_resource_limits(self, mock_resources, builder):
        config = QSIReconConfig(
            subject_id="001",
            resources=ResourceConfig(cpus=16, memory_gb=64),
        )
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        idx = cmd.index("--cpus")
        assert cmd[idx + 1] == "16"
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == "64g"

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_no_fs_license_qsirecon(self, mock_resources):
        """No license mount or --fs-license-file when staging fails."""
        with patch(f"{MODULE}.get_host_project_dir", return_value="/host"):
            b = DockerCommandBuilder("/proj")
            b._host_license_path = None
            config = QSIReconConfig(subject_id="001")
            cmd = b.build_qsirecon_cmd(config, "dipy_dki")

            v_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-v"]
            assert not any("license" in v for v in v_args)
            assert "--fs-license-file" not in cmd


class TestDockerLabels:
    """tit.job_id / tit.kind --label flags (N0.6 spike).

    Before this change, no ``--label`` was ever emitted, so
    ``tit/jobs/runner.py``'s ``stop_docker_siblings(job_id)`` -- which filters
    ``docker ps --filter label=tit.job_id=<id>`` -- always matched zero containers for a
    QSIPrep/QSIRecon job: cancellation had no real container handle (r6 §3,
    skeptic-3 claim #3, ``docker_builder.py``'s own ``--label`` count was 0).
    """

    @staticmethod
    def _label_pairs(cmd: list[str]) -> list[str]:
        return [cmd[i + 1] for i, x in enumerate(cmd) if x == "--label"]

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_qsiprep_always_labels_kind(self, mock_resources, builder, monkeypatch):
        monkeypatch.delenv("TIT_JOB_ID", raising=False)
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)
        assert "tit.kind=qsiprep" in self._label_pairs(cmd)

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_qsirecon_always_labels_kind(self, mock_resources, builder, monkeypatch):
        monkeypatch.delenv("TIT_JOB_ID", raising=False)
        config = QSIReconConfig(subject_id="001")
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        assert "tit.kind=qsirecon" in self._label_pairs(cmd)

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_no_job_id_label_when_env_var_unset(
        self, mock_resources, builder, monkeypatch
    ):
        monkeypatch.delenv("TIT_JOB_ID", raising=False)
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)
        assert not any(
            label.startswith("tit.job_id=") for label in self._label_pairs(cmd)
        )

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_job_id_label_matches_env_var_qsiprep(
        self, mock_resources, builder, monkeypatch
    ):
        """Mirrors what tit/jobs/manager.py's cancel() actually passes to
        stop_docker_siblings(job_id): the exact TIT_JOB_ID this container's own job process was
        spawned with (tit/jobs/runner.py's runner_env sets this env var; the QSI docker builder
        runs inside that same job process, so os.environ carries it through)."""
        monkeypatch.setenv("TIT_JOB_ID", "job-abc123")
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)
        assert "tit.job_id=job-abc123" in self._label_pairs(cmd)

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_job_id_label_matches_env_var_qsirecon(
        self, mock_resources, builder, monkeypatch
    ):
        monkeypatch.setenv("TIT_JOB_ID", "job-xyz789")
        config = QSIReconConfig(subject_id="001")
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        assert "tit.job_id=job-xyz789" in self._label_pairs(cmd)

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_labels_appear_before_image_name(
        self, mock_resources, builder, monkeypatch
    ):
        """--label must be a docker-run *option*, not accidentally emitted after the image name
        (where Docker would treat it as a positional arg to the entrypoint instead)."""
        monkeypatch.setenv("TIT_JOB_ID", "job-1")
        config = QSIPrepConfig(subject_id="001")
        cmd = builder.build_qsiprep_cmd(config)
        image_idx = cmd.index(f"{const.QSI_QSIPREP_IMAGE}:{config.image_tag}")
        label_idx = cmd.index("--label")
        assert label_idx < image_idx
