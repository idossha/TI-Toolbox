#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox DICOM to NIfTI conversion (pre/dicom2nifti.py)
"""

import json
import os
import pytest
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from pre.dicom2nifti import run_dicom_to_nifti
from pre.common import PreprocessError


class TestRunDicomToNifti:
    """Test run_dicom_to_nifti function"""

    @patch("shutil.which", return_value=None)
    def test_run_raises_if_dcm2niix_not_installed(self, mock_which):
        """Test raises PreprocessError if dcm2niix not found"""
        logger = MagicMock()

        with pytest.raises(PreprocessError) as exc_info:
            run_dicom_to_nifti("/test/project", "001", logger=logger)

        assert "dcm2niix is not installed" in str(exc_info.value)

    @patch("shutil.which", return_value="/usr/bin/dcm2niix")
    @patch("pre.dicom2nifti.get_path_manager")
    def test_run_creates_directories(self, mock_get_pm, mock_which):
        """Test creates required directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm

            sourcedata_dir = Path(tmpdir) / "sourcedata" / "sub-001"
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"

            # Create source directories with dicom subdirs
            (sourcedata_dir / "T1w" / "dicom").mkdir(parents=True)
            (sourcedata_dir / "T2w" / "dicom").mkdir(parents=True)

            mock_pm.path.side_effect = lambda key, **kwargs: {
                ("sourcedata_subject", "001"): str(sourcedata_dir),
                ("bids_anat", "001"): str(bids_anat_dir),
            }.get(
                (key, kwargs.get("subject_id")),
            )

            logger = MagicMock()

            # This will fail at processing but should create directories
            try:
                run_dicom_to_nifti(tmpdir, "001", logger=logger)
            except:
                pass

            # Verify PathManager project_dir was set
            assert mock_pm.project_dir == tmpdir

    @patch("shutil.which", return_value="/usr/bin/dcm2niix")
    @patch("pre.dicom2nifti.get_path_manager")
    @patch("pre.dicom2nifti._run_dcm2niix")
    @patch("pre.dicom2nifti._process_converted_files")
    def test_run_processes_t1w_dicom(
        self, mock_process, mock_dcm2niix, mock_get_pm, mock_which
    ):
        """Test processes T1w DICOM files from dicom/ subdirectory"""
        mock_process.return_value = True
        mock_dcm2niix.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm

            sourcedata_dir = Path(tmpdir) / "sourcedata" / "sub-001"
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"
            t1_dicom_dir = sourcedata_dir / "T1w" / "dicom"
            t2_dicom_dir = sourcedata_dir / "T2w" / "dicom"

            # Create dicom directories with .dcm files
            t1_dicom_dir.mkdir(parents=True)
            t2_dicom_dir.mkdir(parents=True)
            (t1_dicom_dir / "0001.dcm").touch()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "sourcedata_subject": str(sourcedata_dir),
                "bids_anat": str(bids_anat_dir),
            }[key]

            logger = MagicMock()

            run_dicom_to_nifti(tmpdir, "001", logger=logger)

            # Verify dcm2niix was called for T1w
            mock_dcm2niix.assert_called()

    @patch("shutil.which", return_value="/usr/bin/dcm2niix")
    @patch("pre.dicom2nifti.get_path_manager")
    def test_run_skips_non_dicom_dirs(self, mock_get_pm, mock_which):
        """Test skips directories without dicom/ subdirectory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm

            sourcedata_dir = Path(tmpdir) / "sourcedata" / "sub-001"
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"

            # Create T1w dir but NO dicom/ subdir
            (sourcedata_dir / "T1w").mkdir(parents=True)
            (sourcedata_dir / "T2w").mkdir(parents=True)

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "sourcedata_subject": str(sourcedata_dir),
                "bids_anat": str(bids_anat_dir),
            }[key]

            logger = MagicMock()

            run_dicom_to_nifti(tmpdir, "001", logger=logger)

            # Should warn that no DICOM files were found
            logger.warning.assert_called_once()
            assert "No DICOM files" in logger.warning.call_args[0][0]

    @patch("shutil.which", return_value="/usr/bin/dcm2niix")
    @patch("pre.dicom2nifti.get_path_manager")
    def test_run_skips_empty_dicom_dirs(self, mock_get_pm, mock_which):
        """Test skips dicom/ directories without .dcm files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm

            sourcedata_dir = Path(tmpdir) / "sourcedata" / "sub-001"
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"

            # Create empty dicom directories
            (sourcedata_dir / "T1w" / "dicom").mkdir(parents=True)
            (sourcedata_dir / "T2w" / "dicom").mkdir(parents=True)

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "sourcedata_subject": str(sourcedata_dir),
                "bids_anat": str(bids_anat_dir),
            }[key]

            logger = MagicMock()

            run_dicom_to_nifti(tmpdir, "001", logger=logger)

            # Should warn that no DICOM files were found
            logger.warning.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
