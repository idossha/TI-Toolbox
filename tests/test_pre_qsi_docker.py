"""Tests for tit.pre.qsi.docker_builder — Docker command builder."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
    def test_distortion_group_merge(self, mock_resources, builder):
        config = QSIPrepConfig(subject_id="001", distortion_group_merge="concatenate")
        cmd = builder.build_qsiprep_cmd(config)
        assert "--distortion-group-merge" in cmd

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

    @patch(f"{MODULE}.get_inherited_dood_resources", return_value=(8, 32))
    def test_basic_command(self, mock_resources, builder):
        config = QSIReconConfig(subject_id="001")
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        assert cmd[0] == "docker"
        assert "--recon-spec" in cmd
        idx = cmd.index("--recon-spec")
        assert cmd[idx + 1] == "dipy_dki"

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
        config = QSIReconConfig(subject_id="001", atlases=["AAL116", "Schaefer100"])
        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")
        idx = cmd.index("--atlases")
        assert cmd[idx + 1] == "AAL116"
        assert cmd[idx + 2] == "Schaefer100"

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
