"""Tests for tit.pre.qsi.qsiprep — QSIPrep runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.qsi.qsiprep import run_qsiprep
from tit.pre.utils import PreprocessError

MODULE = "tit.pre.qsi.qsiprep"


class TestRunQsiprep:
    """Tests for run_qsiprep."""

    @pytest.fixture(autouse=True)
    def _docker_preflight_ok(self):
        with patch(f"{MODULE}.validate_dood_environment", return_value=(True, None)):
            yield

    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_success(
        self, mock_validate, mock_builder, mock_pull, mock_output, tmp_path
    ):
        """Runs QSIPrep successfully end to end."""
        mock_builder.return_value.build_qsiprep_cmd.return_value = [
            "docker",
            "run",
            "qsiprep",
        ]

        runner = MagicMock()
        runner.run.return_value = 0
        logger = MagicMock()

        run_qsiprep(str(tmp_path), "001", logger=logger, runner=runner)

        runner.run.assert_called_once()
        mock_pull.assert_called_once()

    @patch(f"{MODULE}.validate_bids_dwi", return_value=(False, "No DWI"))
    def test_invalid_dwi_raises(self, mock_validate):
        """Raises PreprocessError when DWI validation fails."""
        with pytest.raises(PreprocessError, match="DWI validation failed"):
            run_qsiprep("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_existing_output_raises(self, mock_dwi, tmp_path):
        """Raises like the other steps when real output already exists.

        The pipeline's skip/replace policy is the only layer that skips or
        removes outputs; the step itself just refuses to overwrite.
        """
        out = tmp_path / "derivatives" / "qsiprep" / "sub-001"
        out.mkdir(parents=True)
        (out / "dwi").mkdir()

        with patch(f"{MODULE}.DockerCommandBuilder") as mock_builder:
            with pytest.raises(PreprocessError, match="already exists"):
                run_qsiprep(str(tmp_path), "001", logger=MagicMock())

        mock_builder.assert_not_called()

    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_existing_empty_output_dir_is_ignored(
        self, mock_dwi, mock_builder, mock_pull, mock_output, tmp_path
    ):
        """An empty subject dir (e.g. left by a Docker mount) is not an output."""
        out = tmp_path / "derivatives" / "qsiprep" / "sub-001"
        out.mkdir(parents=True)
        mock_builder.return_value.build_qsiprep_cmd.return_value = ["docker", "run"]

        runner = MagicMock()
        runner.run.return_value = 0

        run_qsiprep(str(tmp_path), "001", logger=MagicMock(), runner=runner)

        runner.run.assert_called_once()

    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_docker_build_error(self, mock_validate, mock_builder, tmp_path):
        """Raises PreprocessError when Docker command build fails."""
        from tit.pre.qsi.docker_builder import DockerBuildError

        mock_builder.side_effect = DockerBuildError("no docker")

        with pytest.raises(PreprocessError, match="Failed to build"):
            run_qsiprep(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.pull_image_if_needed", return_value=False)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_pull_failure_raises(
        self, mock_validate, mock_builder, mock_pull, tmp_path
    ):
        """Raises PreprocessError when image pull fails."""
        mock_builder.return_value.build_qsiprep_cmd.return_value = ["docker", "run"]

        with pytest.raises(PreprocessError, match="Failed to pull"):
            run_qsiprep(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(False, "no output"))
    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_run_failure_raises(
        self, mock_validate, mock_builder, mock_pull, mock_output, tmp_path
    ):
        """Raises PreprocessError when container exits non-zero."""
        mock_builder.return_value.build_qsiprep_cmd.return_value = ["docker", "run"]

        runner = MagicMock()
        runner.run.return_value = 1
        runner.last_output_lines = [
            "Preparing workflow",
            "RuntimeError: missing phase encoding metadata",
        ]

        with pytest.raises(PreprocessError, match="missing phase encoding metadata"):
            run_qsiprep(str(tmp_path), "001", logger=MagicMock(), runner=runner)

    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(False, "incomplete"))
    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_output_validation_failure(
        self, mock_dwi, mock_builder, mock_pull, mock_output, tmp_path
    ):
        """Raises PreprocessError when output validation fails."""
        mock_builder.return_value.build_qsiprep_cmd.return_value = ["docker", "run"]

        runner = MagicMock()
        runner.run.return_value = 0

        with pytest.raises(PreprocessError, match="output validation failed"):
            run_qsiprep(str(tmp_path), "001", logger=MagicMock(), runner=runner)

    @patch(f"{MODULE}.validate_qsiprep_output", return_value=(True, None))
    @patch(f"{MODULE}.pull_image_if_needed", return_value=True)
    @patch(f"{MODULE}.DockerCommandBuilder")
    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    @patch(f"{MODULE}.CommandRunner")
    def test_default_runner_created(
        self, mock_runner_cls, mock_dwi, mock_builder, mock_pull, mock_output, tmp_path
    ):
        """Creates default CommandRunner when none provided."""
        mock_builder.return_value.build_qsiprep_cmd.return_value = ["docker", "run"]
        mock_runner_cls.return_value.run.return_value = 0

        run_qsiprep(str(tmp_path), "001", logger=MagicMock())

        mock_runner_cls.assert_called_once()

    @patch(f"{MODULE}.validate_bids_dwi", return_value=(True, None))
    def test_existing_incomplete_output_raises(self, mock_dwi, tmp_path):
        """A non-empty (even incomplete) output dir blocks the rerun."""
        out = tmp_path / "derivatives" / "qsiprep" / "sub-001"
        out.mkdir(parents=True)
        (out / "partial.txt").touch()

        with pytest.raises(PreprocessError, match="Remove the directory manually"):
            run_qsiprep(str(tmp_path), "001", logger=MagicMock(), runner=MagicMock())
