"""Tests for tit.pre.charm — run_charm and run_subject_atlas."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.charm import ATLASES, run_charm, run_subject_atlas
from tit.pre.utils import PreprocessError


MODULE = "tit.pre.charm"


@pytest.fixture
def mock_pm(tmp_path):
    """Provide a mock PathManager."""
    pm = MagicMock()
    pm.sub.return_value = str(tmp_path / "derivatives" / "SimNIBS" / "sub-001")
    pm.m2m.return_value = str(tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001")
    pm.bids_anat.return_value = str(tmp_path / "sub-001" / "anat")
    return pm


class TestRunCharm:
    """Tests for the run_charm function."""

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_success_with_t1_only(self, mock_find, mock_gpm, mock_pm, tmp_path):
        """charm runs successfully with T1 only."""
        mock_gpm.return_value = mock_pm
        t1 = tmp_path / "sub-001" / "anat" / "sub-001_T1w.nii.gz"
        t1.parent.mkdir(parents=True, exist_ok=True)
        t1.touch()
        mock_find.return_value = (t1, None)

        logger = MagicMock()
        runner = MagicMock()
        runner.run.return_value = 0

        run_charm("/proj", "001", logger=logger, runner=runner)

        runner.run.assert_called_once()
        cmd = runner.run.call_args[0][0]
        assert cmd[0] == "charm"
        assert "001" in cmd
        assert str(t1) in cmd

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_success_with_t1_and_t2(self, mock_find, mock_gpm, mock_pm, tmp_path):
        """charm includes T2 file in command when available."""
        mock_gpm.return_value = mock_pm
        t1 = tmp_path / "t1.nii.gz"
        t2 = tmp_path / "t2.nii.gz"
        mock_find.return_value = (t1, t2)

        logger = MagicMock()
        runner = MagicMock()
        runner.run.return_value = 0

        run_charm("/proj", "001", logger=logger, runner=runner)

        cmd = runner.run.call_args[0][0]
        assert str(t2) in cmd

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_no_t1_raises(self, mock_find, mock_gpm, mock_pm):
        """Raises PreprocessError when no T1 file is found."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (None, None)

        with pytest.raises(PreprocessError, match="No T1 image"):
            run_charm("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_existing_m2m_raises(self, mock_find, mock_gpm, mock_pm, tmp_path):
        """Raises PreprocessError when m2m directory already exists."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)

        # Create the m2m directory so it exists
        m2m = Path(mock_pm.m2m.return_value)
        m2m.mkdir(parents=True, exist_ok=True)

        with pytest.raises(PreprocessError, match="already exists"):
            run_charm("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    def test_charm_failure_raises(self, mock_find, mock_gpm, mock_pm, tmp_path):
        """Raises PreprocessError when charm exits non-zero."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)

        runner = MagicMock()
        runner.run.return_value = 1

        with pytest.raises(PreprocessError, match="charm failed"):
            run_charm("/proj", "001", logger=MagicMock(), runner=runner)

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._find_anat_files")
    @patch(f"{MODULE}.CommandRunner")
    def test_default_runner_created(self, mock_runner_cls, mock_find, mock_gpm, mock_pm, tmp_path):
        """Creates default CommandRunner when none provided."""
        mock_gpm.return_value = mock_pm
        mock_find.return_value = (tmp_path / "t1.nii.gz", None)
        mock_runner_cls.return_value.run.return_value = 0

        run_charm("/proj", "001", logger=MagicMock())

        mock_runner_cls.assert_called_once()


class TestRunSubjectAtlas:
    """Tests for the run_subject_atlas function."""

    @patch(f"{MODULE}.get_path_manager")
    def test_success(self, mock_gpm, mock_pm, tmp_path):
        """Runs subject_atlas for all atlases."""
        mock_gpm.return_value = mock_pm
        m2m = Path(mock_pm.m2m.return_value)
        m2m.mkdir(parents=True, exist_ok=True)

        logger = MagicMock()
        runner = MagicMock()
        runner.run.return_value = 0

        run_subject_atlas("/proj", "001", logger=logger, runner=runner)

        assert runner.run.call_count == len(ATLASES)
        for call in runner.run.call_args_list:
            cmd = call[0][0]
            assert cmd[0] == "subject_atlas"

    @patch(f"{MODULE}.get_path_manager")
    def test_m2m_missing_raises(self, mock_gpm, mock_pm):
        """Raises PreprocessError when m2m folder doesn't exist."""
        mock_gpm.return_value = mock_pm

        with pytest.raises(PreprocessError, match="not found"):
            run_subject_atlas("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    def test_atlas_failure_raises(self, mock_gpm, mock_pm, tmp_path):
        """Raises PreprocessError when any atlas command fails."""
        mock_gpm.return_value = mock_pm
        m2m = Path(mock_pm.m2m.return_value)
        m2m.mkdir(parents=True, exist_ok=True)

        runner = MagicMock()
        runner.run.return_value = 1

        with pytest.raises(PreprocessError, match="subject_atlas failed"):
            run_subject_atlas("/proj", "001", logger=MagicMock(), runner=runner)

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}.CommandRunner")
    def test_default_runner(self, mock_runner_cls, mock_gpm, mock_pm, tmp_path):
        """Creates default CommandRunner when none provided."""
        mock_gpm.return_value = mock_pm
        m2m = Path(mock_pm.m2m.return_value)
        m2m.mkdir(parents=True, exist_ok=True)
        mock_runner_cls.return_value.run.return_value = 0

        run_subject_atlas("/proj", "001", logger=MagicMock())

        mock_runner_cls.assert_called_once()
