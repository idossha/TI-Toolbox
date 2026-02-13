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
    """Test _find_anat_files function - looks for exact BIDS pattern"""

    @patch("pre.charm.get_path_manager")
    def test_find_returns_none_when_no_files(self, mock_get_pm):
        """Test returns (None, None) when no files found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm
            mock_pm.path.return_value = str(Path(tmpdir) / "sub-001" / "anat")

            t1_file, t2_file = _find_anat_files("001")

            assert t1_file is None
            assert t2_file is None

    @patch("pre.charm.get_path_manager")
    def test_find_detects_t1w_file(self, mock_get_pm):
        """Test detects T1w file with exact BIDS pattern"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"
            bids_anat_dir.mkdir(parents=True)
            t1_file_path = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file_path.touch()

            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm
            mock_pm.path.return_value = str(bids_anat_dir)

            t1_file, t2_file = _find_anat_files("001")

            assert t1_file == t1_file_path
            assert t2_file is None

    @patch("pre.charm.get_path_manager")
    def test_find_detects_t2w_file(self, mock_get_pm):
        """Test detects T2w file with exact BIDS pattern"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"
            bids_anat_dir.mkdir(parents=True)
            t2_file_path = bids_anat_dir / "sub-001_T2w.nii.gz"
            t2_file_path.touch()

            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm
            mock_pm.path.return_value = str(bids_anat_dir)

            t1_file, t2_file = _find_anat_files("001")

            assert t1_file is None
            assert t2_file == t2_file_path

    @patch("pre.charm.get_path_manager")
    def test_find_detects_both_t1_and_t2(self, mock_get_pm):
        """Test detects both T1 and T2 files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"
            bids_anat_dir.mkdir(parents=True)
            t1_file_path = bids_anat_dir / "sub-001_T1w.nii.gz"
            t2_file_path = bids_anat_dir / "sub-001_T2w.nii.gz"
            t1_file_path.touch()
            t2_file_path.touch()

            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm
            mock_pm.path.return_value = str(bids_anat_dir)

            t1_file, t2_file = _find_anat_files("001")

            assert t1_file == t1_file_path
            assert t2_file == t2_file_path


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
