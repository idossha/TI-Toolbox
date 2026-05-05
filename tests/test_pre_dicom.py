"""Tests for tit.pre.dicom2nifti — DICOM to NIfTI conversion."""

import tarfile
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.dicom2nifti import (
    _convert_modality,
    _extract_archive,
    _find_dicom_files,
    run_dicom_to_nifti,
)
from tit.pre.utils import PreprocessError

MODULE = "tit.pre.dicom2nifti"


class TestDicomDiscoveryAndArchives:
    """Tests for recursive DICOM discovery and archive extraction."""

    def test_finds_direct_dcm_and_dicom_files(self, tmp_path):
        """Finds direct .dcm and .dicom files."""
        dicom_dir = tmp_path / "dicom"
        dicom_dir.mkdir()
        dcm = dicom_dir / "scan.dcm"
        dicom = dicom_dir / "scan2.dicom"
        txt = dicom_dir / "notes.txt"
        dcm.touch()
        dicom.touch()
        txt.touch()

        assert _find_dicom_files(dicom_dir) == [dcm, dicom]

    def test_finds_recursive_dicom_files(self, tmp_path):
        """Finds DICOM files in nested folders."""
        dicom_dir = tmp_path / "dicom"
        nested = dicom_dir / "series" / "one"
        nested.mkdir(parents=True)
        scan = nested / "scan.DICOM"
        scan.touch()

        assert _find_dicom_files(dicom_dir) == [scan]

    def test_extracts_zip_archive(self, tmp_path):
        """Safely extracts zip archives for later discovery."""
        archive = tmp_path / "dicoms.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("nested/scan.dcm", "dicom")

        destination = tmp_path / "dicom" / "extracted_archives" / archive.name
        extracted = _extract_archive(archive, destination)

        assert extracted == 1
        assert (destination / "nested" / "scan.dcm").read_text() == "dicom"

    def test_extracts_tgz_archive(self, tmp_path):
        """Safely extracts tgz archives for later discovery."""
        source = tmp_path / "scan.dicom"
        source.write_text("dicom")
        archive = tmp_path / "dicoms.tgz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(source, arcname="series/scan.dicom")

        destination = tmp_path / "dicom" / "extracted_archives" / archive.name
        extracted = _extract_archive(archive, destination)

        assert extracted == 1
        assert (destination / "series" / "scan.dicom").read_text() == "dicom"

    def test_rejects_unsafe_zip_member(self, tmp_path):
        """Rejects zip members that would escape the extraction directory."""
        archive = tmp_path / "bad.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escape.dcm", "bad")

        with pytest.raises(PreprocessError, match="Unsafe archive member"):
            _extract_archive(archive, tmp_path / "dest")


class TestConvertModality:
    """Tests for the _convert_modality helper."""

    def test_no_dicom_files_returns_false(self, tmp_path):
        """Returns False when no .dcm/.dicom files are present."""
        dicom_dir = tmp_path / "T1w" / "dicom"
        dicom_dir.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, None)

        assert result is False
        logger.info.assert_any_call(
            f"No .dcm or .dicom files found under {dicom_dir}; skipping conversion"
        )

    def test_existing_output_raises(self, tmp_path):
        """Raises PreprocessError when output already exists."""
        dicom_dir = tmp_path / "T1w" / "dicom"
        dicom_dir.mkdir(parents=True)
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "sub-001_T1w.nii.gz").touch()

        with pytest.raises(PreprocessError, match="already exists"):
            _convert_modality(dicom_dir, out_dir, "001", "T1w", MagicMock(), None)

    @patch(f"{MODULE}.subprocess.run")
    def test_subprocess_success(self, mock_run, tmp_path):
        """Returns True on successful subprocess conversion."""
        dicom_dir = tmp_path / "T1w" / "dicom"
        dicom_dir.mkdir(parents=True)
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
        dicom_dir = tmp_path / "T1w" / "dicom"
        dicom_dir.mkdir(parents=True)
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        mock_run.return_value = MagicMock(returncode=1)
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, None)

        assert result is False

    def test_with_runner_success(self, tmp_path):
        """Uses runner when provided."""
        dicom_dir = tmp_path / "T1w" / "dicom"
        dicom_dir.mkdir(parents=True)
        (dicom_dir / "scan.dicom").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        runner = MagicMock()
        runner.run.return_value = 0
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, runner)

        assert result is True
        runner.run.assert_called_once()
        cmd = runner.run.call_args.args[0]
        assert cmd[cmd.index("-r") + 1] == "y"

    def test_with_runner_failure(self, tmp_path):
        """Returns False on runner failure."""
        dicom_dir = tmp_path / "T1w" / "dicom"
        dicom_dir.mkdir(parents=True)
        (dicom_dir / "scan.dcm").touch()

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        runner = MagicMock()
        runner.run.return_value = 1
        logger = MagicMock()

        result = _convert_modality(dicom_dir, out_dir, "001", "T1w", logger, runner)

        assert result is False

    def test_extracts_modality_archive_before_conversion(self, tmp_path):
        """Archives in modality folders are extracted before conversion."""
        modality_dir = tmp_path / "T1w"
        dicom_dir = modality_dir / "dicom"
        dicom_dir.mkdir(parents=True)
        archive = modality_dir / "dicoms.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("series/scan.dcm", "dicom")

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        runner = MagicMock()
        runner.run.return_value = 0

        result = _convert_modality(
            dicom_dir, out_dir, "001", "T1w", MagicMock(), runner
        )

        assert result is True
        assert (
            dicom_dir / "extracted_archives" / "dicoms.zip" / "series" / "scan.dcm"
        ).exists()


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
