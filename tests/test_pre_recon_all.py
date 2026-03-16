"""Tests for tit.pre.recon_all — FreeSurfer recon-all wrapper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.recon_all import (
    _run_subcortical_segmentations,
    run_recon_all,
    run_subcortical_segmentations,
)
from tit.pre.utils import PreprocessError

MODULE = "tit.pre.recon_all"


@pytest.fixture
def mock_pm(tmp_path):
    """Provide a mock PathManager."""
    pm = MagicMock()
    pm.freesurfer_subject.return_value = str(
        tmp_path / "derivatives" / "freesurfer" / "sub-001"
    )
    pm.bids_anat.return_value = str(tmp_path / "sub-001" / "anat")
    return pm


class TestRunSubcorticalSegmentations:
    """Tests for _run_subcortical_segmentations."""

    def test_success_with_runner(self, tmp_path):
        """Runs both segmentation scripts successfully."""
        logger = MagicMock()
        runner = MagicMock()
        runner.run.return_value = 0

        _run_subcortical_segmentations("001", tmp_path, logger=logger, runner=runner)

        assert runner.run.call_count == 2

    @patch(f"{MODULE}.subprocess.call")
    def test_success_without_runner(self, mock_call, tmp_path):
        """Falls back to subprocess.call when no runner."""
        mock_call.return_value = 0
        logger = MagicMock()

        _run_subcortical_segmentations("001", tmp_path, logger=logger)

        assert mock_call.call_count == 2

    def test_failure_logs_warning(self, tmp_path):
        """Logs warning on non-zero exit (non-fatal)."""
        logger = MagicMock()
        runner = MagicMock()
        runner.run.return_value = 1

        _run_subcortical_segmentations("001", tmp_path, logger=logger, runner=runner)

        assert logger.warning.call_count == 2

    @patch(f"{MODULE}.subprocess.call")
    def test_failure_without_runner_logs_warning(self, mock_call, tmp_path):
        """Logs warning on subprocess failure."""
        mock_call.return_value = 1
        logger = MagicMock()

        _run_subcortical_segmentations("001", tmp_path, logger=logger)

        assert logger.warning.call_count == 2

    def test_env_includes_subjects_dir(self, tmp_path):
        """SUBJECTS_DIR is set in environment."""
        logger = MagicMock()
        runner = MagicMock()
        runner.run.return_value = 0

        _run_subcortical_segmentations("001", tmp_path, logger=logger, runner=runner)

        env = runner.run.call_args_list[0][1]["env"]
        assert env["SUBJECTS_DIR"] == str(tmp_path)


class TestRunSubcorticalSegmentationsPublic:
    """Tests for the public run_subcortical_segmentations wrapper."""

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._run_subcortical_segmentations")
    def test_delegates_to_internal(self, mock_internal, mock_gpm, mock_pm):
        """Resolves paths and delegates to internal function."""
        mock_gpm.return_value = mock_pm
        logger = MagicMock()
        runner = MagicMock()

        run_subcortical_segmentations("/proj", "001", logger=logger, runner=runner)

        mock_internal.assert_called_once()
        assert mock_internal.call_args[0][0] == "001"


class TestRunReconAll:
    """Tests for run_recon_all."""

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    @patch(f"{MODULE}._run_subcortical_segmentations")
    def test_success_with_runner(
        self, mock_subcort, mock_find, mock_gpm, mock_pm, tmp_path
    ):
        """Runs recon-all successfully."""
        mock_gpm.return_value = mock_pm
        t1 = tmp_path / "t1.nii.gz"
        mock_find.return_value = (t1, None)

        logger = MagicMock()
        runner = MagicMock()
        runner.run.return_value = 0

        run_recon_all("/proj", "001", logger=logger, runner=runner)

        runner.run.assert_called_once()
        cmd = runner.run.call_args[0][0]
        assert cmd[0] == "recon-all"
        mock_subcort.assert_called_once()

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    @patch(f"{MODULE}._run_subcortical_segmentations")
    def test_with_t2(self, mock_subcort, mock_find, mock_gpm, mock_pm, tmp_path):
        """Includes T2 flags when T2 file exists."""
        mock_gpm.return_value = mock_pm
        t1 = tmp_path / "t1.nii.gz"
        t2 = tmp_path / "t2.nii.gz"
        mock_find.return_value = (t1, t2)

        runner = MagicMock()
        runner.run.return_value = 0

        run_recon_all("/proj", "001", logger=MagicMock(), runner=runner)

        cmd = runner.run.call_args[0][0]
        assert "-T2" in cmd
        assert "-T2pial" in cmd

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    @patch(f"{MODULE}._run_subcortical_segmentations")
    def test_parallel_flag(self, mock_subcort, mock_find, mock_gpm, mock_pm, tmp_path):
        """Adds -parallel when parallel=True."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)

        runner = MagicMock()
        runner.run.return_value = 0

        run_recon_all("/proj", "001", logger=MagicMock(), parallel=True, runner=runner)

        cmd = runner.run.call_args[0][0]
        assert "-parallel" in cmd

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_no_t1_raises(self, mock_find, mock_gpm, mock_pm):
        """Raises PreprocessError when no T1 found."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (None, None)

        with pytest.raises(PreprocessError, match="No T1"):
            run_recon_all("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_existing_nonempty_dir_raises(self, mock_find, mock_gpm, mock_pm, tmp_path):
        """Raises PreprocessError when non-empty output dir exists."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)

        fs_dir = Path(mock_pm.freesurfer_subject.return_value)
        fs_dir.mkdir(parents=True, exist_ok=True)
        (fs_dir / "dummy_file").touch()

        with pytest.raises(PreprocessError, match="already exists"):
            run_recon_all("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.shutil.rmtree")
    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    @patch(f"{MODULE}._run_subcortical_segmentations")
    def test_existing_empty_dir_removed(
        self, mock_subcort, mock_find, mock_gpm, mock_rmtree, mock_pm, tmp_path
    ):
        """Empty existing directory is removed."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)

        fs_dir = Path(mock_pm.freesurfer_subject.return_value)
        fs_dir.mkdir(parents=True, exist_ok=True)

        runner = MagicMock()
        runner.run.return_value = 0

        run_recon_all("/proj", "001", logger=MagicMock(), runner=runner)

        mock_rmtree.assert_called_once()

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_recon_failure_raises(self, mock_find, mock_gpm, mock_pm, tmp_path):
        """Raises PreprocessError on recon-all failure."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)

        runner = MagicMock()
        runner.run.return_value = 1

        with pytest.raises(PreprocessError, match="recon-all failed"):
            run_recon_all("/proj", "001", logger=MagicMock(), runner=runner)

    @patch(f"{MODULE}.subprocess.call")
    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    @patch(f"{MODULE}._run_subcortical_segmentations")
    def test_without_runner(
        self, mock_subcort, mock_find, mock_gpm, mock_call, mock_pm, tmp_path
    ):
        """Falls back to subprocess.call when no runner."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)
        mock_call.return_value = 0

        run_recon_all("/proj", "001", logger=MagicMock())

        mock_call.assert_called_once()
