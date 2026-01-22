#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for QSI Docker command builder.

These tests verify command construction without requiring Docker to be installed.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from tit.core import constants as const
from tit.pre.qsi.config import QSIPrepConfig, QSIReconConfig, ResourceConfig
from tit.pre.qsi.docker_builder import (
    DockerCommandBuilder,
    DockerBuildError,
    DockerPaths,
)


@pytest.fixture
def mock_docker_available():
    """Mock Docker availability check to return True."""
    with patch("tit.pre.qsi.docker_builder.check_docker_available") as mock:
        mock.return_value = (True, "Docker is available")
        yield mock


@pytest.fixture
def mock_host_project_dir():
    """Mock the host project directory resolution."""
    with patch("tit.pre.qsi.docker_builder.get_host_project_dir") as mock:
        mock.return_value = "/home/user/myproject"
        yield mock


@pytest.fixture
def mock_fs_license():
    """Mock the FreeSurfer license path."""
    with patch("tit.pre.qsi.docker_builder.get_freesurfer_license_path") as mock:
        mock.return_value = "/usr/local/freesurfer/license.txt"
        yield mock


class TestDockerPaths:
    """Tests for DockerPaths dataclass."""

    def test_default_paths(self):
        """Test default container paths."""
        paths = DockerPaths()
        assert paths.bids_dir == "/data"
        assert paths.output_dir == "/out"
        assert paths.work_dir == "/work"
        assert paths.license_file == "/opt/freesurfer/license.txt"


class TestDockerCommandBuilder:
    """Tests for DockerCommandBuilder class."""

    def test_init_docker_unavailable(self):
        """Test that initialization fails when Docker is unavailable."""
        with patch("tit.pre.qsi.docker_builder.check_docker_available") as mock:
            mock.return_value = (False, "Docker not found")
            with pytest.raises(DockerBuildError, match="Docker is not available"):
                DockerCommandBuilder("/mnt/project")

    def test_init_missing_local_project_dir(self, mock_docker_available):
        """Test that initialization fails without LOCAL_PROJECT_DIR."""
        with patch("tit.pre.qsi.docker_builder.get_host_project_dir") as mock:
            mock.side_effect = ValueError("LOCAL_PROJECT_DIR not set")
            with pytest.raises(DockerBuildError):
                DockerCommandBuilder("/mnt/project")

    def test_build_qsiprep_cmd_basic(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test basic QSIPrep command construction."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIPrepConfig(subject_id="001")

        cmd = builder.build_qsiprep_cmd(config)

        # Verify it's a list
        assert isinstance(cmd, list)

        # Verify docker run is present
        assert cmd[0] == "docker"
        assert cmd[1] == "run"

        # Verify --rm flag
        assert "--rm" in cmd

        # Verify image name
        expected_image = f"{const.QSI_QSIPREP_IMAGE}:{const.QSI_DEFAULT_IMAGE_TAG}"
        assert expected_image in cmd

        # Verify participant label
        assert "--participant-label" in cmd
        label_idx = cmd.index("--participant-label")
        assert cmd[label_idx + 1] == "001"

        # Verify output resolution
        assert "--output-resolution" in cmd

        # Verify skip-bids-validation (default is True)
        assert "--skip-bids-validation" in cmd

    def test_build_qsiprep_cmd_custom_resources(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test QSIPrep command with custom resources."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIPrepConfig(
            subject_id="001",
            resources=ResourceConfig(cpus=16, memory_gb=64, omp_threads=4),
        )

        cmd = builder.build_qsiprep_cmd(config)

        # Verify CPU limit
        assert "--cpus" in cmd
        cpu_idx = cmd.index("--cpus")
        assert cmd[cpu_idx + 1] == "16"

        # Verify memory limit
        assert "--memory" in cmd
        mem_idx = cmd.index("--memory")
        assert cmd[mem_idx + 1] == "64g"

        # Verify nthreads
        assert "--nthreads" in cmd
        nthreads_idx = cmd.index("--nthreads")
        assert cmd[nthreads_idx + 1] == "16"

    def test_build_qsiprep_cmd_custom_methods(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test QSIPrep command with custom denoising/unringing methods."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIPrepConfig(
            subject_id="001",
            denoise_method="patch2self",
            unringing_method="rpg",
        )

        cmd = builder.build_qsiprep_cmd(config)

        # Verify denoise method
        assert "--denoise-method" in cmd
        denoise_idx = cmd.index("--denoise-method")
        assert cmd[denoise_idx + 1] == "patch2self"

        # Verify unringing method
        assert "--unringing-method" in cmd
        unring_idx = cmd.index("--unringing-method")
        assert cmd[unring_idx + 1] == "rpg"

    def test_build_qsirecon_cmd_basic(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test basic QSIRecon command construction."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIReconConfig(subject_id="001")

        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        # Verify it's a list
        assert isinstance(cmd, list)

        # Verify docker run is present
        assert cmd[0] == "docker"
        assert cmd[1] == "run"

        # Verify image name
        expected_image = f"{const.QSI_QSIRECON_IMAGE}:{const.QSI_DEFAULT_IMAGE_TAG}"
        assert expected_image in cmd

        # Verify recon spec
        assert "--recon-spec" in cmd
        spec_idx = cmd.index("--recon-spec")
        assert cmd[spec_idx + 1] == "dipy_dki"

        # Verify participant label
        assert "--participant-label" in cmd
        label_idx = cmd.index("--participant-label")
        assert cmd[label_idx + 1] == "001"

    def test_build_qsirecon_cmd_with_gpu(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test QSIRecon command with GPU enabled."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIReconConfig(subject_id="001", use_gpu=True)

        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        # Verify GPU flag
        assert "--gpus" in cmd
        gpu_idx = cmd.index("--gpus")
        assert cmd[gpu_idx + 1] == "all"

    def test_build_qsirecon_cmd_with_atlases(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test QSIRecon command with atlases for connectivity."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIReconConfig(
            subject_id="001",
            atlases=["Schaefer100", "AAL116"],
        )

        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        # Verify atlases are included
        atlas_indices = [i for i, x in enumerate(cmd) if x == "--atlases"]
        assert len(atlas_indices) == 2  # One for each atlas

    def test_build_qsirecon_cmd_skip_odf_reports(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test QSIRecon command with ODF reports skipped."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIReconConfig(subject_id="001", skip_odf_reports=True)

        cmd = builder.build_qsirecon_cmd(config, "dipy_dki")

        # Verify skip-odf-reports flag
        assert "--skip-odf-reports" in cmd

    def test_get_output_dir(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test output directory path retrieval."""
        builder = DockerCommandBuilder("/mnt/project")

        qsiprep_output = builder.get_output_dir("qsiprep")
        assert str(qsiprep_output).endswith("derivatives/qsiprep")

        qsirecon_output = builder.get_output_dir("qsirecon")
        assert str(qsirecon_output).endswith("derivatives/qsirecon")

    def test_volume_mounts_present(
        self, mock_docker_available, mock_host_project_dir, mock_fs_license
    ):
        """Test that volume mounts are present in the command."""
        builder = DockerCommandBuilder("/mnt/project")
        config = QSIPrepConfig(subject_id="001")

        cmd = builder.build_qsiprep_cmd(config)

        # Count -v flags for volume mounts
        v_count = cmd.count("-v")
        assert v_count >= 3  # At least bids_dir, output_dir, work_dir


class TestDockerCommandBuilderNoLicense:
    """Tests for DockerCommandBuilder without FreeSurfer license."""

    def test_build_cmd_without_license(self, mock_docker_available, mock_host_project_dir):
        """Test command construction without FreeSurfer license."""
        with patch("tit.pre.qsi.docker_builder.get_freesurfer_license_path") as mock:
            mock.return_value = None
            builder = DockerCommandBuilder("/mnt/project")
            config = QSIPrepConfig(subject_id="001")

            cmd = builder.build_qsiprep_cmd(config)

            # Should still produce a valid command
            assert "docker" in cmd
            assert "--participant-label" in cmd
