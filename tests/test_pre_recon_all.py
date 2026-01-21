#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox FreeSurfer recon-all wrapper (pre/recon_all.py)
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

from pre.recon_all import (
    _find_anat_files,
    _validate_freesurfer_env,
    run_recon_all,
)
from pre.common import PreprocessError, CommandRunner


class TestFindAnatFiles:
    """Test _find_anat_files function"""

    def test_find_returns_none_when_no_files(self):
        """Test returns (None, None) when no files found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file is None
            assert t2_file is None

    def test_find_detects_t1w_file(self):
        """Test detects T1w files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t1_file_path = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file == t1_file_path
            assert t2_file is None

    def test_find_detects_t2w_file(self):
        """Test detects T2w files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t2_file_path = bids_anat_dir / "sub-001_T2w.nii.gz"
            t2_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file is None
            assert t2_file == t2_file_path

    def test_find_case_insensitive(self):
        """Test detection is case-insensitive"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir)
            t1_file_path = bids_anat_dir / "sub-001_t1w.nii.gz"
            t1_file_path.touch()

            t1_file, t2_file = _find_anat_files(bids_anat_dir)

            assert t1_file == t1_file_path


class TestValidateFreesurferEnv:
    """Test _validate_freesurfer_env function"""

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_warns_if_freesurfer_home_not_set(self):
        """Test warns if FREESURFER_HOME not set"""
        logger = MagicMock()

        # Should not raise, but should warn
        with patch("shutil.which", return_value="/usr/bin/recon-all"):
            with patch("shutil.which", side_effect=lambda x: "/usr/bin/" + x):
                _validate_freesurfer_env(logger)

        assert logger.warning.called
        warning_msg = logger.warning.call_args[0][0]
        assert "FREESURFER_HOME" in warning_msg

    @patch.dict(os.environ, {"FREESURFER_HOME": "/nonexistent"}, clear=True)
    def test_validate_raises_if_freesurfer_home_invalid(self):
        """Test raises if FREESURFER_HOME directory doesn't exist"""
        logger = MagicMock()

        with pytest.raises(PreprocessError) as exc_info:
            _validate_freesurfer_env(logger)

        assert "FREESURFER_HOME" in str(exc_info.value)
        assert "does not exist" in str(exc_info.value)

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which", return_value=None)
    def test_validate_raises_if_recon_all_not_found(self, mock_which):
        """Test raises if recon-all not in PATH"""
        logger = MagicMock()

        with pytest.raises(PreprocessError) as exc_info:
            _validate_freesurfer_env(logger)

        assert "recon-all" in str(exc_info.value)
        assert "not installed" in str(exc_info.value).lower()

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    def test_validate_raises_if_tcsh_not_found(self, mock_which):
        """Test raises if tcsh not found"""
        # Return recon-all but not tcsh
        mock_which.side_effect = lambda x: "/usr/bin/recon-all" if x == "recon-all" else None

        logger = MagicMock()

        with pytest.raises(PreprocessError) as exc_info:
            _validate_freesurfer_env(logger)

        assert "tcsh" in str(exc_info.value)


class TestRunReconAll:
    """Test run_recon_all function"""

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    def test_run_raises_if_no_t1_file(self, mock_find_anat, mock_get_pm, mock_which):
        """Test raises PreprocessError if no T1 file found"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

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
                run_recon_all(tmpdir, "001", logger=logger)

            assert "No T1 file found" in str(exc_info.value)

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    @patch("subprocess.call")
    def test_run_executes_recon_all_with_t1_only(
        self, mock_call, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test executes recon-all with T1 only"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            fs_subject_dir = Path(tmpdir) / "freesurfer" / "sub-001"

            bids_anat_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "freesurfer_subject": str(fs_subject_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)
            mock_call.return_value = 0

            logger = MagicMock()

            run_recon_all(tmpdir, "001", logger=logger)

            # Verify recon-all was called
            mock_call.assert_called_once()
            cmd = mock_call.call_args[0][0]
            assert "recon-all" in cmd
            assert "-subject" in cmd
            assert "sub-001" in cmd
            assert "-i" in cmd
            assert str(t1_file) in cmd
            assert "-all" in cmd

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    @patch("subprocess.call")
    def test_run_includes_t2_if_available(
        self, mock_call, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test includes T2 options if T2 file available"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            fs_subject_dir = Path(tmpdir) / "freesurfer" / "sub-001"

            bids_anat_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t2_file = bids_anat_dir / "sub-001_T2w.nii.gz"
            t1_file.touch()
            t2_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "freesurfer_subject": str(fs_subject_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, t2_file)
            mock_call.return_value = 0

            logger = MagicMock()

            run_recon_all(tmpdir, "001", logger=logger)

            cmd = mock_call.call_args[0][0]
            assert "-T2" in cmd
            assert str(t2_file) in cmd
            assert "-T2pial" in cmd

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    @patch("subprocess.call")
    def test_run_uses_parallel_flag(
        self, mock_call, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test uses -parallel flag when requested"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            fs_subject_dir = Path(tmpdir) / "freesurfer" / "sub-001"

            bids_anat_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "freesurfer_subject": str(fs_subject_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)
            mock_call.return_value = 0

            logger = MagicMock()

            run_recon_all(tmpdir, "001", logger=logger, parallel=True)

            cmd = mock_call.call_args[0][0]
            assert "-parallel" in cmd

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    @patch("shutil.rmtree")
    def test_run_removes_existing_output_on_overwrite(
        self, mock_rmtree, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test removes existing FreeSurfer output when overwrite is True"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            fs_subject_dir = Path(tmpdir) / "freesurfer" / "sub-001"

            bids_anat_dir.mkdir()
            fs_subject_dir.mkdir(parents=True)
            (fs_subject_dir / "existing_file").touch()  # Make directory non-empty

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "freesurfer_subject": str(fs_subject_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_recon_all(tmpdir, "001", logger=logger, overwrite=True, runner=runner)

            # Verify rmtree was called
            mock_rmtree.assert_called()

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    def test_run_continues_existing_when_not_overwriting(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test continues existing processing when output exists and not overwriting"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            fs_subject_dir = Path(tmpdir) / "freesurfer" / "sub-001"

            bids_anat_dir.mkdir()
            fs_subject_dir.mkdir(parents=True)
            (fs_subject_dir / "existing_file").touch()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "freesurfer_subject": str(fs_subject_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_recon_all(tmpdir, "001", logger=logger, overwrite=False, runner=runner)

            # Verify command does not include -i (continuing existing)
            cmd = runner.run.call_args[0][0]
            assert "-i" not in cmd

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    def test_run_raises_on_nonzero_exit(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test raises PreprocessError on non-zero exit code"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            fs_subject_dir = Path(tmpdir) / "freesurfer" / "sub-001"

            bids_anat_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "freesurfer_subject": str(fs_subject_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 1  # Non-zero exit

            with pytest.raises(PreprocessError) as exc_info:
                run_recon_all(tmpdir, "001", logger=logger, runner=runner)

            assert "recon-all failed" in str(exc_info.value)

    @patch.dict(os.environ, {"FREESURFER_HOME": "/"}, clear=True)
    @patch("shutil.which")
    @patch("pre.recon_all.get_path_manager")
    @patch("pre.recon_all._find_anat_files")
    def test_run_uses_runner_if_provided(
        self, mock_find_anat, mock_get_pm, mock_which
    ):
        """Test uses CommandRunner if provided"""
        mock_which.side_effect = lambda x: "/usr/bin/" + x

        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            bids_anat_dir = Path(tmpdir) / "bids_anat"
            fs_subject_dir = Path(tmpdir) / "freesurfer" / "sub-001"

            bids_anat_dir.mkdir()

            t1_file = bids_anat_dir / "sub-001_T1w.nii.gz"
            t1_file.touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "bids_anat": str(bids_anat_dir),
                "freesurfer_subject": str(fs_subject_dir),
            }[key]

            mock_find_anat.return_value = (t1_file, None)

            logger = MagicMock()
            runner = MagicMock()
            runner.run.return_value = 0

            run_recon_all(tmpdir, "001", logger=logger, runner=runner)

            # Verify runner was used
            runner.run.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
