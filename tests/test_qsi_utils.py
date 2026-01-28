#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for QSI utility functions.

These tests verify path resolution, Docker checks, and validation utilities
without requiring Docker to be installed.
"""

import logging
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tit.core import constants as const
from tit.pre.qsi.utils import (
    resolve_host_project_path,
    get_host_project_dir,
    check_docker_available,
    check_image_exists,
    pull_image_if_needed,
    validate_bids_dwi,
    validate_qsiprep_output,
    get_freesurfer_license_path,
    format_memory_limit,
)


class TestResolveHostProjectPath:
    """Tests for resolve_host_project_path function."""

    def test_resolve_with_local_project_dir_set(self):
        """Test path resolution when LOCAL_PROJECT_DIR is set."""
        with patch.dict(
            os.environ, {const.ENV_LOCAL_PROJECT_DIR: "/home/user/myproject"}
        ):
            # Test full path transformation
            result = resolve_host_project_path("/mnt/myproject/derivatives/qsiprep")
            assert result == "/home/user/myproject/derivatives/qsiprep"

    def test_resolve_root_mount_path(self):
        """Test path resolution for the root mount path."""
        with patch.dict(
            os.environ, {const.ENV_LOCAL_PROJECT_DIR: "/home/user/myproject"}
        ):
            result = resolve_host_project_path("/mnt/myproject")
            assert result == "/home/user/myproject"

    def test_resolve_non_mount_path(self):
        """Test that non-mount paths are returned unchanged."""
        with patch.dict(
            os.environ, {const.ENV_LOCAL_PROJECT_DIR: "/home/user/myproject"}
        ):
            result = resolve_host_project_path("/some/other/path")
            assert result == "/some/other/path"

    def test_resolve_without_local_project_dir(self):
        """Test that missing LOCAL_PROJECT_DIR raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if it exists
            os.environ.pop(const.ENV_LOCAL_PROJECT_DIR, None)
            with pytest.raises(ValueError, match="LOCAL_PROJECT_DIR"):
                resolve_host_project_path("/mnt/myproject")


class TestGetHostProjectDir:
    """Tests for get_host_project_dir function."""

    def test_get_with_env_var_set(self):
        """Test getting host project dir when env var is set."""
        with patch.dict(
            os.environ, {const.ENV_LOCAL_PROJECT_DIR: "/home/user/project"}
        ):
            result = get_host_project_dir()
            assert result == "/home/user/project"

    def test_get_without_env_var(self):
        """Test that missing env var raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(const.ENV_LOCAL_PROJECT_DIR, None)
            with pytest.raises(ValueError, match="LOCAL_PROJECT_DIR"):
                get_host_project_dir()


class TestCheckDockerAvailable:
    """Tests for check_docker_available function."""

    def test_docker_not_in_path(self):
        """Test when Docker CLI is not in PATH."""
        with patch("shutil.which", return_value=None):
            available, message = check_docker_available()
            assert available is False
            assert "not found" in message.lower()

    def test_docker_daemon_not_running(self):
        """Test when Docker daemon is not running."""
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stderr="daemon not running"
                )
                available, message = check_docker_available()
                assert available is False
                assert "daemon" in message.lower()

    def test_docker_available(self):
        """Test when Docker is fully available."""
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                available, message = check_docker_available()
                assert available is True
                assert "available" in message.lower()

    def test_docker_timeout(self):
        """Test when Docker command times out."""
        import subprocess

        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(
                    cmd="docker", timeout=10
                )
                available, message = check_docker_available()
                assert available is False
                assert "timed out" in message.lower()

    def test_docker_exception(self):
        """Test when Docker check raises an exception."""
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = OSError("Permission denied")
                available, message = check_docker_available()
                assert available is False
                assert "failed" in message.lower()


class TestCheckImageExists:
    """Tests for check_image_exists function."""

    def test_image_exists(self):
        """Test when image exists locally."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = check_image_exists("pennlinc/qsiprep", "1.1.1")
            assert result is True
            mock_run.assert_called_once()
            # Verify the command includes the full image:tag
            call_args = mock_run.call_args[0][0]
            assert "pennlinc/qsiprep:1.1.1" in call_args

    def test_image_not_exists(self):
        """Test when image does not exist locally."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = check_image_exists("pennlinc/qsiprep", "1.1.1")
            assert result is False

    def test_image_check_exception(self):
        """Test when image check raises an exception."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Network error")
            result = check_image_exists("pennlinc/qsiprep", "1.1.1")
            assert result is False


class TestPullImageIfNeeded:
    """Tests for pull_image_if_needed function."""

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger for testing."""
        return MagicMock(spec=logging.Logger)

    def test_image_already_exists(self, mock_logger):
        """Test when image already exists (no pull needed)."""
        with patch("tit.pre.qsi.utils.check_image_exists", return_value=True):
            result = pull_image_if_needed("pennlinc/qsiprep", "1.1.1", mock_logger)
            assert result is True
            mock_logger.debug.assert_called()

    def test_pull_success(self, mock_logger):
        """Test successful image pull."""
        with patch("tit.pre.qsi.utils.check_image_exists", return_value=False):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = pull_image_if_needed("pennlinc/qsiprep", "1.1.1", mock_logger)
                assert result is True
                mock_logger.info.assert_called()

    def test_pull_failure(self, mock_logger):
        """Test failed image pull."""
        with patch("tit.pre.qsi.utils.check_image_exists", return_value=False):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="pull failed")
                result = pull_image_if_needed("pennlinc/qsiprep", "1.1.1", mock_logger)
                assert result is False
                mock_logger.error.assert_called()

    def test_pull_timeout(self, mock_logger):
        """Test image pull timeout."""
        import subprocess

        with patch("tit.pre.qsi.utils.check_image_exists", return_value=False):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(
                    cmd="docker", timeout=1800
                )
                result = pull_image_if_needed("pennlinc/qsiprep", "1.1.1", mock_logger)
                assert result is False
                mock_logger.error.assert_called()


class TestValidateBidsDwi:
    """Tests for validate_bids_dwi function."""

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger for testing."""
        return MagicMock(spec=logging.Logger)

    def test_valid_dwi_data(self, tmp_path, mock_logger):
        """Test validation with valid DWI data structure."""
        # Create valid BIDS DWI structure
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_dwi.nii.gz").touch()
        (dwi_dir / "sub-001_dwi.bval").touch()
        (dwi_dir / "sub-001_dwi.bvec").touch()

        is_valid, error_msg = validate_bids_dwi(str(tmp_path), "001", mock_logger)
        assert is_valid is True
        assert error_msg is None

    def test_missing_dwi_directory(self, tmp_path, mock_logger):
        """Test validation when DWI directory is missing."""
        is_valid, error_msg = validate_bids_dwi(str(tmp_path), "001", mock_logger)
        assert is_valid is False
        assert "not found" in error_msg.lower()

    def test_missing_nifti_files(self, tmp_path, mock_logger):
        """Test validation when NIfTI files are missing."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_dwi.bval").touch()
        (dwi_dir / "sub-001_dwi.bvec").touch()

        is_valid, error_msg = validate_bids_dwi(str(tmp_path), "001", mock_logger)
        assert is_valid is False
        assert "nifti" in error_msg.lower()

    def test_missing_bval_files(self, tmp_path, mock_logger):
        """Test validation when bval files are missing."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_dwi.nii.gz").touch()
        (dwi_dir / "sub-001_dwi.bvec").touch()

        is_valid, error_msg = validate_bids_dwi(str(tmp_path), "001", mock_logger)
        assert is_valid is False
        assert "bval" in error_msg.lower()

    def test_missing_bvec_files(self, tmp_path, mock_logger):
        """Test validation when bvec files are missing."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_dwi.nii.gz").touch()
        (dwi_dir / "sub-001_dwi.bval").touch()

        is_valid, error_msg = validate_bids_dwi(str(tmp_path), "001", mock_logger)
        assert is_valid is False
        assert "bvec" in error_msg.lower()


class TestValidateQsiprepOutput:
    """Tests for validate_qsiprep_output function."""

    def test_valid_qsiprep_output(self, tmp_path):
        """Test validation with valid QSIPrep output."""
        # Create valid QSIPrep output structure
        qsiprep_dir = tmp_path / "derivatives" / "qsiprep" / "sub-001" / "dwi"
        qsiprep_dir.mkdir(parents=True)
        (qsiprep_dir / "sub-001_space-T1w_desc-preproc_dwi.nii.gz").touch()

        is_valid, error_msg = validate_qsiprep_output(str(tmp_path), "001")
        assert is_valid is True
        assert error_msg is None

    def test_missing_qsiprep_directory(self, tmp_path):
        """Test validation when QSIPrep directory is missing."""
        is_valid, error_msg = validate_qsiprep_output(str(tmp_path), "001")
        assert is_valid is False
        assert "not found" in error_msg.lower()

    def test_missing_dwi_output(self, tmp_path):
        """Test validation when DWI output is missing."""
        qsiprep_dir = tmp_path / "derivatives" / "qsiprep" / "sub-001"
        qsiprep_dir.mkdir(parents=True)

        is_valid, error_msg = validate_qsiprep_output(str(tmp_path), "001")
        assert is_valid is False
        assert "dwi output not found" in error_msg.lower()

    def test_empty_dwi_directory(self, tmp_path):
        """Test validation when DWI directory is empty."""
        dwi_dir = tmp_path / "derivatives" / "qsiprep" / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)

        is_valid, error_msg = validate_qsiprep_output(str(tmp_path), "001")
        assert is_valid is False
        assert "no preprocessed" in error_msg.lower()


class TestGetFreesurferLicensePath:
    """Tests for get_freesurfer_license_path function."""

    def test_license_from_env_var(self, tmp_path):
        """Test getting license from FS_LICENSE env var."""
        license_file = tmp_path / "license.txt"
        license_file.touch()

        with patch.dict(os.environ, {"FS_LICENSE": str(license_file)}):
            result = get_freesurfer_license_path()
            assert result == str(license_file)

    def test_license_from_freesurfer_home(self, tmp_path):
        """Test getting license from FREESURFER_HOME."""
        fs_home = tmp_path / "freesurfer"
        fs_home.mkdir()
        license_file = fs_home / "license.txt"
        license_file.touch()

        with patch.dict(os.environ, {"FREESURFER_HOME": str(fs_home)}, clear=False):
            # Clear FS_LICENSE if set
            os.environ.pop("FS_LICENSE", None)
            result = get_freesurfer_license_path()
            assert result == str(license_file)

    def test_license_not_found(self):
        """Test when license file is not found."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("FS_LICENSE", None)
            os.environ.pop("FREESURFER_HOME", None)
            result = get_freesurfer_license_path()
            assert result is None


class TestFormatMemoryLimit:
    """Tests for format_memory_limit function."""

    def test_format_memory_standard(self):
        """Test standard memory formatting."""
        assert format_memory_limit(32) == "32g"
        assert format_memory_limit(64) == "64g"
        assert format_memory_limit(8) == "8g"

    def test_format_memory_small(self):
        """Test small memory values."""
        assert format_memory_limit(4) == "4g"
        assert format_memory_limit(1) == "1g"
