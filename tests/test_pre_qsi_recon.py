"""Tests for tit.pre.qsi.qsirecon — QSIRecon runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.qsi.qsirecon import (
    list_available_atlases,
    list_available_recon_specs,
    run_qsirecon,
)
from tit.pre.utils import PreprocessError

MODULE = "tit.pre.qsi.qsirecon"


class TestRunQsirecon:
    """Tests for run_qsirecon."""

    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_success(self, mock_validate, mock_builder, mock_pull, tmp_path):
        """Runs QSIRecon successfully."""
        mock_builder.return_value.build_qsirecon_cmd.return_value = ["docker", "run"]

        runner = MagicMock()
        runner.run.return_value = 0
        logger = MagicMock()

        run_qsirecon(str(tmp_path), "001", logger=logger, runner=runner)

        runner.run.assert_called_once()

    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(False, "no output"))
    def test_no_qsiprep_output_raises(self, mock_validate):
        """Raises PreprocessError when QSIPrep output missing."""
        with pytest.raises(PreprocessError, match="QSIPrep output"):
            run_qsirecon("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_existing_output_raises(
        self, mock_validate, mock_builder, mock_pull, tmp_path
    ):
        """Raises PreprocessError when output already exists."""
        out = tmp_path / "derivatives" / "qsirecon" / "sub-001"
        out.mkdir(parents=True)

        runner = MagicMock()
        logger = MagicMock()

        with pytest.raises(PreprocessError, match="already exists"):
            run_qsirecon(str(tmp_path), "001", logger=logger, runner=runner)

    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_docker_init_error(self, mock_validate, mock_builder, tmp_path):
        """Raises PreprocessError when Docker builder fails."""
        from tit.pre.qsi.docker_builder import DockerBuildError

        mock_builder.side_effect = DockerBuildError("no docker")

        with pytest.raises(PreprocessError, match="Failed to initialize"):
            run_qsirecon(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.pull_image_if_needed", return_value=False)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_pull_failure_raises(
        self, mock_validate, mock_builder, mock_pull, tmp_path
    ):
        """Raises PreprocessError when image pull fails."""
        with pytest.raises(PreprocessError, match="Failed to pull"):
            run_qsirecon(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_run_failure_raises(self, mock_validate, mock_builder, mock_pull, tmp_path):
        """Raises PreprocessError when container exits non-zero."""
        mock_builder.return_value.build_qsirecon_cmd.return_value = ["docker", "run"]

        runner = MagicMock()
        runner.run.return_value = 1

        with pytest.raises(PreprocessError, match="failed with exit code"):
            run_qsirecon(str(tmp_path), "001", logger=MagicMock(), runner=runner)

    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_multiple_specs(self, mock_validate, mock_builder, mock_pull, tmp_path):
        """Runs multiple recon specs sequentially."""
        mock_builder.return_value.build_qsirecon_cmd.return_value = ["docker", "run"]

        runner = MagicMock()
        runner.run.return_value = 0

        run_qsirecon(
            str(tmp_path),
            "001",
            logger=MagicMock(),
            runner=runner,
            recon_specs=["dipy_dki", "amico_noddi"],
        )

        assert runner.run.call_count == 2

    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    @patch(f"{MODULE}.CommandRunner")
    def test_default_runner(
        self, mock_runner_cls, mock_validate, mock_builder, mock_pull, tmp_path
    ):
        """Creates default CommandRunner when none provided."""
        mock_builder.return_value.build_qsirecon_cmd.return_value = ["docker", "run"]
        mock_runner_cls.return_value.run.return_value = 0

        run_qsirecon(str(tmp_path), "001", logger=MagicMock())

        mock_runner_cls.assert_called_once()

    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_default_specs_and_atlases(
        self, mock_validate, mock_builder, mock_pull, tmp_path
    ):
        """Uses default specs and atlases when none provided."""
        mock_builder.return_value.build_qsirecon_cmd.return_value = ["docker", "run"]

        runner = MagicMock()
        runner.run.return_value = 0

        run_qsirecon(str(tmp_path), "001", logger=MagicMock(), runner=runner)

        # Verify the config was built with defaults
        config = mock_builder.return_value.build_qsirecon_cmd.call_args[0][0]
        assert len(config.recon_specs) > 0
        assert config.atlases is not None

    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    def test_build_cmd_error_raises(
        self, mock_validate, mock_builder, mock_pull, tmp_path
    ):
        """Raises PreprocessError when build_qsirecon_cmd fails."""
        from tit.pre.qsi.docker_builder import DockerBuildError

        mock_builder.return_value.build_qsirecon_cmd.side_effect = DockerBuildError(
            "build failed"
        )

        runner = MagicMock()

        with pytest.raises(PreprocessError, match="Failed to build"):
            run_qsirecon(str(tmp_path), "001", logger=MagicMock(), runner=runner)


class TestListFunctions:
    """Tests for list_available_recon_specs and list_available_atlases."""

    def test_list_recon_specs(self):
        result = list_available_recon_specs()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_list_atlases(self):
        result = list_available_atlases()
        assert isinstance(result, list)
        assert len(result) > 0
