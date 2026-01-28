#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox SimNIBS charm wrapper (pre/charm.py)
"""

import os
import pytest
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from pre.charm import (
    ATLASES,
    _find_anat_files,
    run_charm,
    run_subject_atlas,
)
from pre.common import PreprocessError, CommandRunner


class TestAtlasesConstant:
    """Test ATLASES constant"""

    def test_atlases_contains_expected_values(self):
        """Test ATLASES contains all expected atlas names"""
        assert "a2009s" in ATLASES
        assert "DK40" in ATLASES
        assert "HCP_MMP1" in ATLASES

    def test_atlases_is_list(self):
        """Test ATLASES is a list"""
        assert isinstance(ATLASES, list)

    def test_atlases_has_correct_count(self):
        """Test ATLASES has exactly 3 atlases"""
        assert len(ATLASES) == 3


class TestFindAnatFiles:
    """Test _find_anat_files function"""

    def test_find_returns_none_when_no_files(self):
        """Test returns (None, None) when no files found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file is None
            assert t2_file is None

    def test_find_detects_t1w_uppercase(self):
        """Test detects T1w files (uppercase)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t1_file_path = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file == t1_file_path
            assert t2_file is None

    def test_find_detects_t1w_lowercase(self):
        """Test detects t1w files (lowercase)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t1_file_path = bids_anat_dir / "sub-001_t1w.nii.gz"
            t1_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file == t1_file_path
            assert t2_file is None

    def test_find_detects_t2w_uppercase(self):
        """Test detects T2w files (uppercase)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t2_file_path = bids_anat_dir / "sub-001_T2w.nii.gz"
            t2_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file is None
            assert t2_file == t2_file_path

    def test_find_detects_t2w_lowercase(self):
        """Test detects t2w files (lowercase)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t2_file_path = bids_anat_dir / "sub-001_t2w.nii.gz"
            t2_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file is None
            assert t2_file == t2_file_path

    def test_find_detects_both_t1_and_t2(self):
        """Test detects both T1 and T2 files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t1_file_path = bids_anat_dir / "sub-001_T1w.nii.gz"
            t2_file_path = bids_anat_dir / "sub-001_T2w.nii.gz"
            t1_file_path.touch()
            t2_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file == t1_file_path
            assert t2_file == t2_file_path

    def test_find_returns_first_when_multiple_t1(self):
        """Test returns first T1 file when multiple exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t1_file1 = bids_anat_dir / "sub-001_acq-1_T1w.nii.gz"
            t1_file2 = bids_anat_dir / "sub-001_acq-2_T1w.nii.gz"
            t1_file1.touch()
            t1_file2.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            # Should return first in sorted order
            assert t1_file is not None
            assert t1_file in [t1_file1, t1_file2]

    def test_find_returns_first_when_multiple_t2(self):
        """Test returns first T2 file when multiple exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t2_file1 = bids_anat_dir / "sub-001_acq-1_T2w.nii.gz"
            t2_file2 = bids_anat_dir / "sub-001_acq-2_T2w.nii.gz"
            t2_file1.touch()
            t2_file2.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            # Should return first in sorted order
            assert t2_file is not None
            assert t2_file in [t2_file1, t2_file2]

    def test_find_handles_nii_extension(self):
        """Test handles .nii extension (uncompressed)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t1_file_path = bids_anat_dir / "sub-001_T1w.nii"
            t1_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file == t1_file_path


class TestRunCharm:
    """Test run_charm function"""

    @patch("shutil.which", return_value=None)
    def test_run_charm_raises_if_not_installed(self, mock_which):
        """Test raises PreprocessError if charm not installed"""
        logger = MagicMock()

        with pytest.raises(PreprocessError) as exc_info:
            run_charm("/test/project", "001", logger=logger)

        assert "charm" in str(exc_info.value).lower()
        assert "not installed" in str(exc_info.value).lower()

    @patch("shutil.which", return_value="/usr/bin/charm")
    @patch("pre.charm.get_path_manager")
    @patch("pre.charm._find_anat_files")
    def test_run_charm_raises_if_no_t1(self, mock_find_anat, mock_get_pm, mock_which):
        """Test raises PreprocessError if no T1 file found"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            bids_anat_dir.mkdir()
            mock_pm.path.return_value = str(bids_anat_dir)

            # No T1 file found
            mock_find_anat.return_value = (None, None)

            logger = MagicMock()

            with pytest.raises(PreprocessError) as exc_info:
                run_charm(tmpdir, "001", logger=logger)

            assert "No T1 image found" in str(exc_info.value)

    @patch("shutil.which", return_value="/usr/bin/charm")
    @patch("pre.charm.get_path_manager")
    @patch("pre.charm._find_anat_files")
    def test_run_charm_executes_with_t1_only(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test executes charm with T1 only (no T2)"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            simnibs_dir = Path(tmpdir) / "simnibs"
            m2m_dir = Path(tmpdir) / "m2m_001"

            bids_anat_dir.mkdir()
            simnibs_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "simnibs_subject": str(simnibs_dir),
                "m2m": str(m2m_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_charm(tmpdir, "001", logger=logger, runner=runner)

            # Verify command was called
            runner.run.assert_called_once()
            cmd = runner.run.call_args[0][0]
            assert "charm" in cmd
            assert str(t1_file) in cmd
            assert "001" in cmd

    @patch("shutil.which", return_value="/usr/bin/charm")
    @patch("pre.charm.get_path_manager")
    @patch("pre.charm._find_anat_files")
    def test_run_charm_executes_with_t1_and_t2(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test executes charm with both T1 and T2"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            simnibs_dir = Path(tmpdir) / "simnibs"
            m2m_dir = Path(tmpdir) / "m2m_001"

            bids_anat_dir.mkdir()
            simnibs_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t2_file = bids_anat_dir / "sub-001_T2w.nii.gz"
            t1_file.touch()
            t2_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "simnibs_subject": str(simnibs_dir),
                "m2m": str(m2m_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, t2_file)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_charm(tmpdir, "001", logger=logger, runner=runner)

            # Verify T2 file was included
            cmd = runner.run.call_args[0][0]
            assert str(t2_file) in cmd

    @patch("shutil.which", return_value="/usr/bin/charm")
    @patch("pre.charm.get_path_manager")
    @patch("pre.charm._find_anat_files")
    def test_run_charm_uses_forcerun_when_overwrite(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test uses --forcerun flag when overwrite is True"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            simnibs_dir = Path(tmpdir) / "simnibs"
            m2m_dir = Path(tmpdir) / "m2m_001"

            bids_anat_dir.mkdir()
            simnibs_dir.mkdir()
            m2m_dir.mkdir()  # Existing m2m directory

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "simnibs_subject": str(simnibs_dir),
                "m2m": str(m2m_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_charm(tmpdir, "001", logger=logger, overwrite=True, runner=runner)

            # Verify --forcerun was included
            cmd = runner.run.call_args[0][0]
            assert "--forcerun" in cmd

    @patch("shutil.which", return_value="/usr/bin/charm")
    @patch("pre.charm.get_path_manager")
    @patch("pre.charm._find_anat_files")
    def test_run_charm_skips_when_exists_no_overwrite(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test skips execution when m2m exists and overwrite is False"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            simnibs_dir = Path(tmpdir) / "simnibs"
            m2m_dir = Path(tmpdir) / "m2m_001"

            bids_anat_dir.mkdir()
            simnibs_dir.mkdir()
            m2m_dir.mkdir()  # Existing m2m directory

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "simnibs_subject": str(simnibs_dir),
                "m2m": str(m2m_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()

            run_charm(tmpdir, "001", logger=logger, overwrite=False, runner=runner)

            # Verify runner was not called
            runner.run.assert_not_called()

    @patch("shutil.which", return_value="/usr/bin/charm")
    @patch("pre.charm.get_path_manager")
    @patch("pre.charm._find_anat_files")
    def test_run_charm_raises_on_nonzero_exit(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test raises PreprocessError on non-zero exit code"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            simnibs_dir = Path(tmpdir) / "simnibs"
            m2m_dir = Path(tmpdir) / "m2m_001"

            bids_anat_dir.mkdir()
            simnibs_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "simnibs_subject": str(simnibs_dir),
                "m2m": str(m2m_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 1  # Non-zero exit

            with pytest.raises(PreprocessError) as exc_info:
                run_charm(tmpdir, "001", logger=logger, runner=runner)

            assert "charm failed" in str(exc_info.value)


class TestRunSubjectAtlas:
    """Test run_subject_atlas function"""

    @patch("shutil.which", return_value=None)
    def test_run_subject_atlas_raises_if_not_installed(self, mock_which):
        """Test raises PreprocessError if subject_atlas not installed"""
        logger = MagicMock()

        with pytest.raises(PreprocessError) as exc_info:
            run_subject_atlas("/test/project", "001", logger=logger)

        assert "subject_atlas" in str(exc_info.value).lower()
        assert "not installed" in str(exc_info.value).lower()

    @patch("shutil.which", return_value="/usr/bin/subject_atlas")
    @patch("pre.charm.get_path_manager")
    def test_run_subject_atlas_raises_if_no_m2m(self, mock_get_pm, mock_which):
        """Test raises PreprocessError if m2m directory not found"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            m2m_dir = Path(tmpdir) / "m2m_001"
            mock_pm.path.return_value = str(m2m_dir)

            logger = MagicMock()

            with pytest.raises(PreprocessError) as exc_info:
                run_subject_atlas(tmpdir, "001", logger=logger)

            assert "m2m folder not found" in str(exc_info.value)

    @patch("shutil.which", return_value="/usr/bin/subject_atlas")
    @patch("pre.charm.get_path_manager")
    def test_run_subject_atlas_runs_all_atlases(self, mock_get_pm, mock_which):
        """Test runs subject_atlas for all atlases"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            m2m_dir = Path(tmpdir) / "m2m_001"
            m2m_dir.mkdir()

            mock_pm.path.return_value = str(m2m_dir)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_subject_atlas(tmpdir, "001", logger=logger, runner=runner)

            # Verify called for each atlas
            assert runner.run.call_count == len(ATLASES)

            # Verify each atlas was used
            all_calls = runner.run.call_args_list
            for atlas in ATLASES:
                assert any(atlas in str(call) for call in all_calls)

    @patch("shutil.which", return_value="/usr/bin/subject_atlas")
    @patch("pre.charm.get_path_manager")
    def test_run_subject_atlas_creates_segmentation_dir(self, mock_get_pm, mock_which):
        """Test creates segmentation output directory"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            m2m_dir = Path(tmpdir) / "m2m_001"
            m2m_dir.mkdir()

            mock_pm.path.return_value = str(m2m_dir)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_subject_atlas(tmpdir, "001", logger=logger, runner=runner)

            # Verify segmentation directory was created
            segmentation_dir = m2m_dir / "segmentation"
            assert segmentation_dir.exists()

    @patch("shutil.which", return_value="/usr/bin/subject_atlas")
    @patch("pre.charm.get_path_manager")
    def test_run_subject_atlas_raises_on_failure(self, mock_get_pm, mock_which):
        """Test raises PreprocessError if atlas generation fails"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            m2m_dir = Path(tmpdir) / "m2m_001"
            m2m_dir.mkdir()

            mock_pm.path.return_value = str(m2m_dir)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 1  # Failure

            with pytest.raises(PreprocessError) as exc_info:
                run_subject_atlas(tmpdir, "001", logger=logger, runner=runner)

            assert "subject_atlas failed" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
