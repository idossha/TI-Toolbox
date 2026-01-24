#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for QSIPrep runner module.

These tests verify the run_qsiprep function behavior without requiring
Docker or actual DWI data.
"""

import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tit.core import constants as const
from tit.pre.common import PreprocessError
from tit.pre.qsi.qsiprep import run_qsiprep


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_runner():
    """Create a mock CommandRunner for testing."""
    runner = MagicMock()
    runner.run.return_value = 0  # Success by default
    return runner


@pytest.fixture
def mock_dwi_validation_pass():
    """Mock successful DWI validation."""
    with patch("tit.pre.qsi.qsiprep.validate_bids_dwi") as mock:
        mock.return_value = (True, None)
        yield mock


@pytest.fixture
def mock_qsiprep_output_validation_pass():
    """Mock successful QSIPrep output validation."""
    with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock:
        mock.return_value = (True, None)
        yield mock


@pytest.fixture
def mock_docker_builder():
    """Mock DockerCommandBuilder."""
    with patch("tit.pre.qsi.qsiprep.DockerCommandBuilder") as mock:
        builder_instance = MagicMock()
        builder_instance.build_qsiprep_cmd.return_value = ["docker", "run", "qsiprep"]
        mock.return_value = builder_instance
        yield mock


@pytest.fixture
def mock_pull_image():
    """Mock pull_image_if_needed to always succeed."""
    with patch("tit.pre.qsi.qsiprep.pull_image_if_needed") as mock:
        mock.return_value = True
        yield mock


class TestRunQsiprep:
    """Tests for run_qsiprep function."""

    def test_run_qsiprep_success(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test successful QSIPrep run."""
        # Setup: Create output dir that validation will check
        output_dir = tmp_path / "derivatives" / "qsiprep" / "sub-001" / "dwi"
        output_dir.mkdir(parents=True)
        (output_dir / "sub-001_dwi.nii.gz").touch()

        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_output_val:
            # First call returns False (no existing output), second returns True (success)
            mock_output_val.side_effect = [(False, "not found"), (True, None)]

            run_qsiprep(
                project_dir=str(tmp_path),
                subject_id="001",
                logger=mock_logger,
                runner=mock_runner,
            )

        # Verify runner was called
        mock_runner.run.assert_called_once()
        mock_logger.info.assert_called()

    def test_run_qsiprep_dwi_validation_fails(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
    ):
        """Test that DWI validation failure raises PreprocessError."""
        with patch("tit.pre.qsi.qsiprep.validate_bids_dwi") as mock_val:
            mock_val.return_value = (False, "No DWI data found")

            with pytest.raises(PreprocessError, match="DWI validation failed"):
                run_qsiprep(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    runner=mock_runner,
                )

    def test_run_qsiprep_skip_existing_output(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
    ):
        """Test that existing output is skipped when overwrite=False."""
        # Create existing output structure
        output_dir = tmp_path / "derivatives" / "qsiprep" / "sub-001" / "dwi"
        output_dir.mkdir(parents=True)
        (output_dir / "sub-001_dwi.nii.gz").touch()

        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            mock_val.return_value = (True, None)

            run_qsiprep(
                project_dir=str(tmp_path),
                subject_id="001",
                logger=mock_logger,
                overwrite=False,
                runner=mock_runner,
            )

        # Verify runner was NOT called (skipped)
        mock_runner.run.assert_not_called()

    def test_run_qsiprep_docker_build_error(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
    ):
        """Test that DockerBuildError is converted to PreprocessError."""
        from tit.pre.qsi.docker_builder import DockerBuildError

        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            mock_val.return_value = (False, "not found")

            with patch("tit.pre.qsi.qsiprep.DockerCommandBuilder") as mock_builder:
                mock_builder.side_effect = DockerBuildError("Docker not available")

                with pytest.raises(PreprocessError, match="Failed to build"):
                    run_qsiprep(
                        project_dir=str(tmp_path),
                        subject_id="001",
                        logger=mock_logger,
                        runner=mock_runner,
                    )

    def test_run_qsiprep_image_pull_fails(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
        mock_docker_builder,
    ):
        """Test that image pull failure raises PreprocessError."""
        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            mock_val.return_value = (False, "not found")

            with patch("tit.pre.qsi.qsiprep.pull_image_if_needed") as mock_pull:
                mock_pull.return_value = False

                with pytest.raises(PreprocessError, match="Failed to pull"):
                    run_qsiprep(
                        project_dir=str(tmp_path),
                        subject_id="001",
                        logger=mock_logger,
                        runner=mock_runner,
                    )

    def test_run_qsiprep_runner_fails(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that runner failure raises PreprocessError."""
        mock_runner.run.return_value = 1  # Non-zero exit code

        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            mock_val.return_value = (False, "not found")

            with pytest.raises(PreprocessError, match="failed with exit code"):
                run_qsiprep(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    runner=mock_runner,
                )

    def test_run_qsiprep_output_validation_fails(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that post-run output validation failure raises PreprocessError."""
        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            # First check: no existing output. Second check: still no output after run
            mock_val.side_effect = [(False, "not found"), (False, "Output missing")]

            with pytest.raises(PreprocessError, match="output validation failed"):
                run_qsiprep(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    runner=mock_runner,
                )

    def test_run_qsiprep_custom_parameters(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test QSIPrep with custom parameters."""
        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            # Always return success for output validation (no existing, then valid)
            mock_val.return_value = (True, None)

            run_qsiprep(
                project_dir=str(tmp_path),
                subject_id="001",
                logger=mock_logger,
                output_resolution=1.5,
                cpus=16,
                memory_gb=64,
                omp_threads=4,
                image_tag="1.0.0",
                skip_bids_validation=False,
                denoise_method="patch2self",
                unringing_method="rpg",
                overwrite=True,
                runner=mock_runner,
            )

        # Verify runner was called
        mock_runner.run.assert_called_once()

    def test_run_qsiprep_creates_output_directories(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_dwi_validation_pass,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that output directories are created."""
        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            # Return valid for final output validation
            mock_val.return_value = (True, None)

            run_qsiprep(
                project_dir=str(tmp_path),
                subject_id="001",
                logger=mock_logger,
                runner=mock_runner,
            )

        # Check that work directory was created
        work_dir = tmp_path / "derivatives" / ".qsiprep_work"
        assert work_dir.exists()

    def test_run_qsiprep_default_runner(
        self,
        tmp_path,
        mock_logger,
        mock_dwi_validation_pass,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that default CommandRunner is created when not provided."""
        with patch("tit.pre.qsi.qsiprep.validate_qsiprep_output") as mock_val:
            # Return valid for final output validation
            mock_val.return_value = (True, None)

            with patch("tit.pre.qsi.qsiprep.CommandRunner") as mock_runner_class:
                mock_runner_instance = MagicMock()
                mock_runner_instance.run.return_value = 0
                mock_runner_class.return_value = mock_runner_instance

                run_qsiprep(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    # No runner provided
                )

                mock_runner_class.assert_called_once()
