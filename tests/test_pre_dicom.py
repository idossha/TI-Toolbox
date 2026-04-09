"""Tests for tit.pre.dicom2nifti — DICOM to NIfTI conversion."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.dicom2nifti import (
    _convert_modality,
    run_dicom_to_nifti,
)
from tit.pre.utils import PreprocessError

MODULE = "tit.pre.dicom2nifti"


class TestConvertModality:
    """Tests for the _convert_modality helper."""

    def test_no_dcm_files_returns_false(self, tmp_path):
        """Returns False when no .dcm files in directory."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", MagicMock(), None)
        assert result is False

    def test_existing_output_raises(self, tmp_path):
        """Raises PreprocessError when output already exists."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "sub-001_T1w.nii.gz").touch()

        with pytest.raises(PreprocessError, match="already exists"):
            _convert_modality(dicom_dir, out_dir, "001", "T1w", MagicMock(), None)

    @patch(f"{MODULE}.subprocess.run")
    def test_subprocess_success(self, mock_run, tmp_path):
        """Returns True on successful subprocess conversion."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        mock_run.return_value = MagicMock(returncode=0)
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, None)

        assert result is True
        mock_run.assert_called_once()

    @patch(f"{MODULE}.subprocess.run")
    def test_subprocess_failure(self, mock_run, tmp_path):
        """Returns False on subprocess failure."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        mock_run.return_value = MagicMock(returncode=1)
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, None)

        assert result is False

    def test_with_runner_success(self, tmp_path):
        """Uses runner when provided."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        runner = MagicMock()
        runner.run.return_value = 0
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, runner)

        assert result is True
        runner.run.assert_called_once()

    def test_with_runner_failure(self, tmp_path):
        """Returns False on runner failure."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        runner = MagicMock()
        runner.run.return_value = 1
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, runner)

        assert result is False


class TestRunDicomToNifti:
    """Tests for run_dicom_to_nifti."""

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._convert_modality")
    def test_converts_both_modalities(self, mock_convert, mock_gpm, tmp_path):
        """Processes both T1w and T2w modalities."""
        pm = MagicMock()
        pm.sourcedata_subject.return_value = str(tmp_path / "sourcedata" / "sub-001")
        pm.bids_anat.return_value = str(tmp_path / "sub-001" / "anat")
        mock_gpm.return_value = pm

        mock_convert.return_value = True
        logger = MagicMock()

        run_dicom_to_nifti("/proj", "001", logger=logger)

        assert mock_convert.call_count == 2

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._convert_modality")
    def test_no_converted_warns(self, mock_convert, mock_gpm, tmp_path):
        """Logs warning when no files converted."""
        pm = MagicMock()
        pm.sourcedata_subject.return_value = str(tmp_path / "sourcedata" / "sub-001")
        pm.bids_anat.return_value = str(tmp_path / "sub-001" / "anat")
        mock_gpm.return_value = pm

        mock_convert.return_value = False
        logger = MagicMock()

        run_dicom_to_nifti("/proj", "001", logger=logger)

        logger.warning.assert_called_once()
