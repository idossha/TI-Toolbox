"""Tests for tit.pre.dicom2nifti — DICOM to NIfTI conversion."""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from tit.pre.dicom2nifti import (
    _run_dcm2niix,
    _process_converted_files,
    _process_modality,
    run_dicom_to_nifti,
)
from tit.pre.utils import PreprocessError


MODULE = "tit.pre.dicom2nifti"


class TestRunDcm2niix:
    """Tests for the _run_dcm2niix helper."""

    def test_with_runner(self):
        """Uses runner when provided."""
        runner = MagicMock()
        runner.run.return_value = 0
        logger = MagicMock()

        result = _run_dcm2niix(Path("/src"), Path("/out"), logger, runner)

        assert result is True
        runner.run.assert_called_once()

    def test_with_runner_failure(self):
        """Returns False on runner failure."""
        runner = MagicMock()
        runner.run.return_value = 1
        logger = MagicMock()

        result = _run_dcm2niix(Path("/src"), Path("/out"), logger, runner)

        assert result is False

    @patch(f"{MODULE}.subprocess.run")
    def test_without_runner(self, mock_run):
        """Falls back to subprocess.run when no runner."""
        mock_run.return_value = MagicMock(returncode=0)
        logger = MagicMock()

        result = _run_dcm2niix(Path("/src"), Path("/out"), logger, None)

        assert result is True
        mock_run.assert_called_once()

    @patch(f"{MODULE}.subprocess.run")
    def test_without_runner_failure(self, mock_run):
        """Returns False on subprocess failure."""
        mock_run.return_value = MagicMock(returncode=1)
        logger = MagicMock()

        result = _run_dcm2niix(Path("/src"), Path("/out"), logger, None)

        assert result is False


class TestProcessConvertedFiles:
    """Tests for _process_converted_files."""

    def test_no_json_files(self, tmp_path):
        """Returns False when no JSON files found."""
        result = _process_converted_files(
            tmp_path, tmp_path / "out", "001", "T1w", MagicMock()
        )
        assert result is False

    def test_json_without_nii(self, tmp_path):
        """Skips JSON files without matching NIfTI."""
        (tmp_path / "scan.json").touch()
        result = _process_converted_files(
            tmp_path, tmp_path / "out", "001", "T1w", MagicMock()
        )
        assert result is False

    @patch(f"{MODULE}.shutil.move")
    def test_with_gzipped_nii(self, mock_move, tmp_path):
        """Processes .nii.gz files correctly."""
        (tmp_path / "scan.json").touch()
        (tmp_path / "scan.nii.gz").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        logger = MagicMock()
        result = _process_converted_files(
            tmp_path, out_dir, "001", "T1w", logger
        )

        assert result is True
        assert mock_move.call_count == 2

    @patch(f"{MODULE}.subprocess.run")
    @patch(f"{MODULE}.shutil.move")
    def test_with_uncompressed_nii(self, mock_move, mock_run, tmp_path):
        """Compresses .nii files with gzip."""
        (tmp_path / "scan.json").touch()
        (tmp_path / "scan.nii").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # After gzip, the .nii.gz file should exist
        def create_gz(*args, **kwargs):
            (tmp_path / "scan.nii.gz").touch()
            return MagicMock(returncode=0)

        mock_run.side_effect = create_gz

        logger = MagicMock()
        result = _process_converted_files(
            tmp_path, out_dir, "001", "T1w", logger
        )

        assert result is True
        mock_run.assert_called_once()

    @patch(f"{MODULE}.shutil.move")
    def test_existing_output_raises(self, mock_move, tmp_path):
        """Raises PreprocessError when output already exists."""
        (tmp_path / "scan.json").touch()
        (tmp_path / "scan.nii.gz").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "sub-001_T1w.nii.gz").touch()

        with pytest.raises(PreprocessError, match="already exists"):
            _process_converted_files(
                tmp_path, out_dir, "001", "T1w", MagicMock()
            )


class TestProcessModality:
    """Tests for _process_modality."""

    def test_process_modality_calls_process_converted(self, tmp_path):
        """_process_modality creates temp dir and delegates."""
        sd = tmp_path / "T1w" / "dicom"
        sd.mkdir(parents=True)

        logger = MagicMock()
        pm = MagicMock()

        # The function won't find files in the temp dir, so returns False
        result = _process_modality(
            "T1w", tmp_path, tmp_path / "out", "001", pm, logger, None
        )
        assert result is False


class TestRunDicomToNifti:
    """Tests for run_dicom_to_nifti."""

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._process_modality")
    def test_converts_both_modalities(self, mock_process, mock_gpm, tmp_path):
        """Processes both T1w and T2w modalities."""
        pm = MagicMock()
        pm.sourcedata_subject.return_value = str(tmp_path / "sourcedata" / "sub-001")
        pm.bids_anat.return_value = str(tmp_path / "sub-001" / "anat")
        mock_gpm.return_value = pm

        mock_process.return_value = True
        logger = MagicMock()

        run_dicom_to_nifti("/proj", "001", logger=logger)

        assert mock_process.call_count == 2

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._process_modality")
    def test_no_converted_warns(self, mock_process, mock_gpm, tmp_path):
        """Logs warning when no files converted."""
        pm = MagicMock()
        pm.sourcedata_subject.return_value = str(tmp_path / "sourcedata" / "sub-001")
        pm.bids_anat.return_value = str(tmp_path / "sub-001" / "anat")
        mock_gpm.return_value = pm

        mock_process.return_value = False
        logger = MagicMock()

        run_dicom_to_nifti("/proj", "001", logger=logger)

        logger.warning.assert_called_once()
