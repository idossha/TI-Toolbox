#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for QSIRecon runner module.

These tests verify the run_qsirecon function and helper functions
without requiring Docker or actual data.
"""

import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tit.core import constants as const
from tit.pre.common import PreprocessError
from tit.pre.qsi.qsirecon import (
    run_qsirecon,
    list_available_recon_specs,
    list_available_atlases,
)


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
def mock_qsiprep_output_valid():
    """Mock valid QSIPrep output validation."""
    with patch("tit.pre.qsi.qsirecon.validate_qsiprep_output") as mock:
        mock.return_value = (True, None)
        yield mock


@pytest.fixture
def mock_docker_builder():
    """Mock DockerCommandBuilder."""
    with patch("tit.pre.qsi.qsirecon.DockerCommandBuilder") as mock:
        builder_instance = MagicMock()
        builder_instance.build_qsirecon_cmd.return_value = ["docker", "run", "qsirecon"]
        mock.return_value = builder_instance
        yield mock


@pytest.fixture
def mock_pull_image():
    """Mock pull_image_if_needed to always succeed."""
    with patch("tit.pre.qsi.qsirecon.pull_image_if_needed") as mock:
        mock.return_value = True
        yield mock


class TestRunQsirecon:
    """Tests for run_qsirecon function."""

    def test_run_qsirecon_success_single_spec(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test successful QSIRecon run with single spec."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            recon_specs=["dipy_dki"],
            runner=mock_runner,
        )

        # Verify runner was called once
        mock_runner.run.assert_called_once()
        mock_logger.info.assert_called()

    def test_run_qsirecon_success_multiple_specs(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test successful QSIRecon run with multiple specs."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            recon_specs=["dipy_dki", "amico_noddi"],
            runner=mock_runner,
        )

        # Verify runner was called twice (once per spec)
        assert mock_runner.run.call_count == 2

    def test_run_qsirecon_default_specs(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test QSIRecon with default recon specs."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            recon_specs=None,  # Use defaults
            runner=mock_runner,
        )

        # Should have run with default spec
        mock_runner.run.assert_called()

    def test_run_qsirecon_qsiprep_output_missing(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
    ):
        """Test that missing QSIPrep output raises PreprocessError."""
        with patch("tit.pre.qsi.qsirecon.validate_qsiprep_output") as mock_val:
            mock_val.return_value = (False, "QSIPrep output not found")

            with pytest.raises(PreprocessError, match="QSIPrep output validation failed"):
                run_qsirecon(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    runner=mock_runner,
                )

    def test_run_qsirecon_docker_build_error(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
    ):
        """Test that DockerBuildError is converted to PreprocessError."""
        from tit.pre.qsi.docker_builder import DockerBuildError

        with patch("tit.pre.qsi.qsirecon.DockerCommandBuilder") as mock_builder:
            mock_builder.side_effect = DockerBuildError("Docker not available")

            with pytest.raises(PreprocessError, match="Failed to initialize Docker"):
                run_qsirecon(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    runner=mock_runner,
                )

    def test_run_qsirecon_image_pull_fails(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
    ):
        """Test that image pull failure raises PreprocessError."""
        with patch("tit.pre.qsi.qsirecon.pull_image_if_needed") as mock_pull:
            mock_pull.return_value = False

            with pytest.raises(PreprocessError, match="Failed to pull"):
                run_qsirecon(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    runner=mock_runner,
                )

    def test_run_qsirecon_runner_fails(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that runner failure raises PreprocessError."""
        mock_runner.run.return_value = 1  # Non-zero exit code

        with pytest.raises(PreprocessError, match="failed with exit code"):
            run_qsirecon(
                project_dir=str(tmp_path),
                subject_id="001",
                logger=mock_logger,
                runner=mock_runner,
            )

    def test_run_qsirecon_skip_existing_output(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that existing output is skipped when overwrite=False."""
        # Create existing output structure
        output_dir = tmp_path / "derivatives" / "qsirecon" / "sub-001"
        output_dir.mkdir(parents=True)

        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            overwrite=False,
            runner=mock_runner,
        )

        # Verify runner was NOT called (skipped due to existing output)
        mock_runner.run.assert_not_called()

    def test_run_qsirecon_with_gpu(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test QSIRecon with GPU enabled."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            use_gpu=True,
            runner=mock_runner,
        )

        mock_runner.run.assert_called()

    def test_run_qsirecon_with_atlases(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test QSIRecon with custom atlases."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            atlases=["Schaefer200", "Gordon333Ext"],
            runner=mock_runner,
        )

        mock_runner.run.assert_called()

    def test_run_qsirecon_custom_resources(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test QSIRecon with custom resource allocation."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            cpus=16,
            memory_gb=64,
            omp_threads=4,
            runner=mock_runner,
        )

        mock_runner.run.assert_called()

    def test_run_qsirecon_custom_image_tag(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test QSIRecon with custom image tag."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            image_tag="1.0.0",
            runner=mock_runner,
        )

        mock_runner.run.assert_called()

    def test_run_qsirecon_creates_output_directories(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that output directories are created."""
        run_qsirecon(
            project_dir=str(tmp_path),
            subject_id="001",
            logger=mock_logger,
            runner=mock_runner,
        )

        # Check that output and work directories were created
        output_dir = tmp_path / "derivatives" / "qsirecon"
        work_dir = tmp_path / "derivatives" / ".qsirecon_work"
        assert output_dir.exists()
        assert work_dir.exists()

    def test_run_qsirecon_default_runner(
        self,
        tmp_path,
        mock_logger,
        mock_qsiprep_output_valid,
        mock_docker_builder,
        mock_pull_image,
    ):
        """Test that default CommandRunner is created when not provided."""
        with patch("tit.pre.qsi.qsirecon.CommandRunner") as mock_runner_class:
            mock_runner_instance = MagicMock()
            mock_runner_instance.run.return_value = 0
            mock_runner_class.return_value = mock_runner_instance

            run_qsirecon(
                project_dir=str(tmp_path),
                subject_id="001",
                logger=mock_logger,
                # No runner provided
            )

            mock_runner_class.assert_called_once()

    def test_run_qsirecon_command_build_fails(
        self,
        tmp_path,
        mock_logger,
        mock_runner,
        mock_qsiprep_output_valid,
        mock_pull_image,
    ):
        """Test that command build failure raises PreprocessError."""
        from tit.pre.qsi.docker_builder import DockerBuildError

        with patch("tit.pre.qsi.qsirecon.DockerCommandBuilder") as mock_builder:
            builder_instance = MagicMock()
            builder_instance.build_qsirecon_cmd.side_effect = DockerBuildError(
                "Command build failed"
            )
            mock_builder.return_value = builder_instance

            with pytest.raises(PreprocessError, match="Failed to build QSIRecon command"):
                run_qsirecon(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    runner=mock_runner,
                )


class TestListAvailableReconSpecs:
    """Tests for list_available_recon_specs function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        specs = list_available_recon_specs()
        assert isinstance(specs, list)

    def test_contains_expected_specs(self):
        """Test that list contains expected recon specs."""
        specs = list_available_recon_specs()
        assert "dipy_dki" in specs
        assert "amico_noddi" in specs

    def test_matches_constants(self):
        """Test that list matches constants definition."""
        specs = list_available_recon_specs()
        assert specs == list(const.QSI_RECON_SPECS)


class TestListAvailableAtlases:
    """Tests for list_available_atlases function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        atlases = list_available_atlases()
        assert isinstance(atlases, list)

    def test_contains_expected_atlases(self):
        """Test that list contains expected atlases."""
        atlases = list_available_atlases()
        assert "Schaefer100" in atlases
        assert "AAL116" in atlases

    def test_matches_constants(self):
        """Test that list matches constants definition."""
        atlases = list_available_atlases()
        assert atlases == list(const.QSI_ATLASES)
