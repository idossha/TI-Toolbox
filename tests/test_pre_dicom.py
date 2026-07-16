"""Tests for tit.pre.dicom2nifti — source-image ingestion to BIDS NIfTI."""

import gzip
import os
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.dicom2nifti import (
    MODALITIES,
    _DICOM_SUFFIXES,
    _NIFTI_SUFFIXES,
    _extract_archive,
    _extract_archives,
    _find_files,
    _ingest_modality,
    _iter_files,
    _modality_source_dir,
    _nifti_stem,
    run_dicom_to_nifti,
)
from tit.pre.utils import PreprocessError

MODULE = "tit.pre.dicom2nifti"


def _eperm_stat(*bad_fragments):
    """Return an ``os.stat`` replacement that raises EPERM for matching paths.

    Reproduces a macOS AppleDouble file on a Docker bind mount, where stat
    fails with EPERM rather than the ENOENT that pathlib tolerates.
    """
    real_stat = os.stat

    def fake_stat(path, *args, **kwargs):
        if any(fragment in str(path) for fragment in bad_fragments):
            raise PermissionError(1, "Operation not permitted")
        return real_stat(path, *args, **kwargs)

    return fake_stat


class TestSafeScanning:
    """Directory scanning must survive macOS/Docker junk files."""

    def test_skips_dotfiles(self, tmp_path):
        """Dotfiles are ignored: dcm2niix skips them and BIDS reserves them."""
        (tmp_path / "scan.dcm").touch()
        (tmp_path / ".DS_Store").touch()
        (tmp_path / "._.DS_Store").touch()
        (tmp_path / "._scan.dcm").touch()

        assert [p.name for p in _iter_files(tmp_path)] == ["scan.dcm"]

    def test_skips_dot_directories(self, tmp_path):
        """Dot-directories are not descended into."""
        hidden = tmp_path / ".AppleDouble"
        hidden.mkdir()
        (hidden / "scan.dcm").touch()
        (tmp_path / "real.dcm").touch()

        assert [p.name for p in _iter_files(tmp_path)] == ["real.dcm"]

    def test_appledouble_eperm_does_not_abort_scan(self, tmp_path):
        """Regression: '._.DS_Store' whose stat raises EPERM must not crash.

        Python 3.11's Path.is_file() only swallows ENOENT/ENOTDIR/EBADF/ELOOP,
        so EPERM propagated and aborted DICOM conversion entirely.
        """
        (tmp_path / "scan.dcm").touch()
        (tmp_path / "._.DS_Store").touch()

        with patch("os.stat", _eperm_stat("._")):
            found = _find_files(tmp_path, _DICOM_SUFFIXES)

        assert [p.name for p in found] == ["scan.dcm"]

    def test_unreadable_entry_is_skipped_not_fatal(self, tmp_path):
        """A non-dot entry that cannot be stat'd is skipped, not raised.

        Covers filesystems reporting DT_UNKNOWN, where scandir must fall back
        to a real stat syscall.
        """
        (tmp_path / "scan.dcm").touch()

        with patch(
            f"{MODULE}.os.scandir",
            return_value=[
                MagicMock(
                    name="x", **{"is_dir.side_effect": PermissionError(1, "nope")}
                )
            ],
        ):
            assert list(_iter_files(tmp_path)) == []

    def test_unreadable_directory_is_skipped(self, tmp_path):
        """An unreadable directory does not abort the whole scan."""
        (tmp_path / "good.dcm").touch()

        with patch(f"{MODULE}.os.scandir", side_effect=PermissionError(1, "nope")):
            assert list(_iter_files(tmp_path)) == []

    def test_finds_files_recursively(self, tmp_path):
        """DICOMs nested in series folders are found."""
        nested = tmp_path / "series" / "one"
        nested.mkdir(parents=True)
        (nested / "scan.DICOM").touch()

        assert [p.name for p in _find_files(tmp_path, _DICOM_SUFFIXES)] == [
            "scan.DICOM"
        ]

    def test_ignores_non_dicom_files(self, tmp_path):
        """Only .dcm/.dicom count as DICOM input."""
        (tmp_path / "scan.dcm").touch()
        (tmp_path / "notes.txt").touch()

        assert [p.name for p in _find_files(tmp_path, _DICOM_SUFFIXES)] == ["scan.dcm"]

    def test_matches_double_extension_nifti(self, tmp_path):
        """'.nii.gz' is two suffixes, so Path.suffix alone would miss it."""
        (tmp_path / "scan.nii.gz").touch()
        (tmp_path / "scan.nii").touch()
        (tmp_path / "notes.txt").touch()

        found = [p.name for p in _find_files(tmp_path, _NIFTI_SUFFIXES)]
        assert sorted(found) == ["scan.nii", "scan.nii.gz"]


class TestArchives:
    """Archive extraction feeds DICOM discovery."""

    def test_extracts_zip_archive(self, tmp_path):
        archive = tmp_path / "dicoms.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("nested/scan.dcm", "dicom")

        destination = tmp_path / "extracted_archives" / archive.name
        assert _extract_archive(archive, destination) == 1
        assert (destination / "nested" / "scan.dcm").read_text() == "dicom"

    def test_extracts_tgz_archive(self, tmp_path):
        source = tmp_path / "scan.dicom"
        source.write_text("dicom")
        archive = tmp_path / "dicoms.tgz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(source, arcname="series/scan.dicom")

        destination = tmp_path / "extracted_archives" / archive.name
        assert _extract_archive(archive, destination) == 1
        assert (destination / "series" / "scan.dicom").read_text() == "dicom"

    def test_rejects_unsafe_zip_member(self, tmp_path):
        archive = tmp_path / "bad.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escape.dcm", "bad")

        with pytest.raises(PreprocessError, match="Unsafe archive member"):
            _extract_archive(archive, tmp_path / "dest")

    def test_extracts_archive_before_conversion(self, tmp_path):
        """Archives anywhere in the modality folder are extracted first."""
        modality_dir = tmp_path / "T1w"
        (modality_dir / "dicom").mkdir(parents=True)
        archive = modality_dir / "dicoms.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("series/scan.dcm", "dicom")

        runner = MagicMock()
        runner.run.return_value = 0

        with patch(f"{MODULE}._check_dcm2niix_outputs", return_value=True):
            assert _ingest_modality(
                modality_dir, tmp_path / "out", "001", "T1w", MagicMock(), runner
            )
        assert (
            modality_dir / "extracted_archives" / "dicoms.zip" / "series" / "scan.dcm"
        ).exists()

    def test_does_not_re_extract_own_output(self, tmp_path):
        """An archive inside extracted_archives/ must not be extracted again."""
        modality_dir = tmp_path / "T1w"
        nested = modality_dir / "extracted_archives" / "outer.zip"
        nested.mkdir(parents=True)
        with zipfile.ZipFile(nested / "inner.zip", "w") as zf:
            zf.writestr("scan.dcm", "dicom")

        _extract_archives(modality_dir, MagicMock())

        assert not (nested / "extracted_archives").exists()

    def test_bad_archive_warns_and_continues(self, tmp_path):
        """A corrupt archive is reported, not fatal."""
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "broken.zip").write_text("not a zip")
        logger = MagicMock()

        _extract_archives(modality_dir, logger)

        assert "Could not extract" in str(logger.warning.call_args)


class TestModalitySourceDir:
    """Modality folders are matched case-insensitively."""

    def test_exact_folder_name(self, tmp_path):
        (tmp_path / "dwi").mkdir()
        assert _modality_source_dir(tmp_path, "dwi") == tmp_path / "dwi"

    def test_case_insensitive_folder_name(self, tmp_path):
        """Users name the folder CT as often as ct."""
        (tmp_path / "CT").mkdir()
        result = _modality_source_dir(tmp_path, "ct")
        assert result.exists()
        assert result.name.lower() == "ct"

    def test_missing_folder_returns_default(self, tmp_path):
        assert _modality_source_dir(tmp_path, "dwi") == tmp_path / "dwi"


class TestNiftiPassthrough:
    """A modality folder holding a NIfTI is copied, not converted."""

    def test_copies_gzipped_nifti(self, tmp_path):
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.nii.gz").write_bytes(b"volume")
        out_dir = tmp_path / "anat"

        with patch(f"{MODULE}._run_dcm2niix") as mock_convert:
            assert _ingest_modality(
                modality_dir, out_dir, "001", "T1w", MagicMock(), None
            )

        mock_convert.assert_not_called()
        assert (out_dir / "sub-001_T1w.nii.gz").read_bytes() == b"volume"

    def test_compresses_bare_nifti(self, tmp_path):
        """A bare .nii is gzipped on the way, so the output is always .nii.gz."""
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.nii").write_bytes(b"volume")
        out_dir = tmp_path / "anat"

        assert _ingest_modality(modality_dir, out_dir, "001", "T1w", MagicMock(), None)

        assert (
            gzip.decompress((out_dir / "sub-001_T1w.nii.gz").read_bytes()) == b"volume"
        )

    def test_copies_bval_bvec_sidecars(self, tmp_path):
        """QSIPrep rejects a DWI without its .bval/.bvec pair."""
        modality_dir = tmp_path / "dwi"
        modality_dir.mkdir()
        (modality_dir / "scan.nii.gz").write_bytes(b"volume")
        (modality_dir / "scan.bval").write_text("0 1000")
        (modality_dir / "scan.bvec").write_text("0 1")
        (modality_dir / "scan.json").write_text("{}")
        out_dir = tmp_path / "dwi_out"

        assert _ingest_modality(modality_dir, out_dir, "001", "dwi", MagicMock(), None)

        assert (out_dir / "sub-001_dwi.bval").read_text() == "0 1000"
        assert (out_dir / "sub-001_dwi.bvec").read_text() == "0 1"
        assert (out_dir / "sub-001_dwi.json").read_text() == "{}"

    def test_dicom_wins_over_nifti(self, tmp_path):
        """DICOMs carry the metadata, so a stray NIfTI must not shadow them."""
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.dcm").touch()
        (modality_dir / "stray.nii.gz").write_bytes(b"volume")
        out_dir = tmp_path / "anat"

        with patch(f"{MODULE}._run_dcm2niix", return_value=True) as mock_convert:
            assert _ingest_modality(
                modality_dir, out_dir, "001", "T1w", MagicMock(), None
            )

        mock_convert.assert_called_once()
        assert not (out_dir / "sub-001_T1w.nii.gz").exists()

    def test_nifti_stem_strips_double_extension(self):
        assert _nifti_stem(Path("scan.nii.gz")) == "scan"
        assert _nifti_stem(Path("scan.nii")) == "scan"


class TestIngestModality:
    """Conversion behaviour for a single modality."""

    def test_no_inputs_returns_false(self, tmp_path):
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()

        assert not _ingest_modality(
            modality_dir, tmp_path / "out", "001", "T1w", MagicMock(), None
        )

    def test_existing_output_raises(self, tmp_path):
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.dcm").touch()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "sub-001_T1w.nii.gz").touch()

        with pytest.raises(PreprocessError, match="already exists"):
            _ingest_modality(modality_dir, out_dir, "001", "T1w", MagicMock(), None)

    @patch(f"{MODULE}.subprocess.run")
    def test_subprocess_success(self, mock_run, tmp_path):
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.dcm").touch()
        mock_run.return_value = MagicMock(returncode=0)

        with patch(f"{MODULE}._check_dcm2niix_outputs", return_value=True):
            assert _ingest_modality(
                modality_dir, tmp_path / "out", "001", "T1w", MagicMock(), None
            )
        mock_run.assert_called_once()

    @patch(f"{MODULE}.subprocess.run")
    def test_subprocess_failure(self, mock_run, tmp_path):
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.dcm").touch()
        mock_run.return_value = MagicMock(returncode=1)

        assert not _ingest_modality(
            modality_dir, tmp_path / "out", "001", "T1w", MagicMock(), None
        )

    def test_runner_command_shape(self, tmp_path):
        """dcm2niix recursion is -d (max 9); -r would rename instead of convert."""
        modality_dir = tmp_path / "dwi"
        modality_dir.mkdir()
        (modality_dir / "scan.dcm").touch()
        out_dir = tmp_path / "sub-001" / "dwi"
        runner = MagicMock()
        runner.run.return_value = 0

        with patch(f"{MODULE}._check_dcm2niix_outputs", return_value=True):
            assert _ingest_modality(
                modality_dir, out_dir, "001", "dwi", MagicMock(), runner
            )

        cmd = runner.run.call_args.args[0]
        assert "-r" not in cmd
        assert cmd[cmd.index("-d") + 1] == "9"
        assert cmd[cmd.index("-f") + 1] == "sub-001_dwi"
        assert cmd[cmd.index("-o") + 1] == str(out_dir)
        assert cmd[-1] == str(modality_dir)
        assert out_dir.is_dir()

    def test_missing_expected_output_returns_false(self, tmp_path):
        """A zero exit code with no matching NIfTI is still a failure."""
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.dcm").touch()
        runner = MagicMock()
        runner.run.return_value = 0
        logger = MagicMock()

        assert not _ingest_modality(
            modality_dir, tmp_path / "out", "001", "T1w", logger, runner
        )
        assert "produced no" in str(logger.warning.call_args)

    def test_extra_series_is_warned_about(self, tmp_path):
        """dcm2niix appends a bare letter per extra series (sub-001_T1wa)."""
        modality_dir = tmp_path / "T1w"
        modality_dir.mkdir()
        (modality_dir / "scan.dcm").touch()
        out_dir = tmp_path / "out"
        logger = MagicMock()

        def fake_run(cmd, logger=None):
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "sub-001_T1w.nii.gz").touch()
            (out_dir / "sub-001_T1wa.nii.gz").touch()
            return 0

        runner = MagicMock()
        runner.run.side_effect = fake_run

        assert _ingest_modality(modality_dir, out_dir, "001", "T1w", logger, runner)
        assert "sub-001_T1wa.nii.gz" in str(logger.warning.call_args)


class TestRunDicomToNifti:
    """Top-level modality dispatch."""

    def _path_manager(self, tmp_path):
        pm = MagicMock()
        pm.sourcedata_subject.return_value = str(tmp_path / "sourcedata" / "sub-001")
        pm.bids_datatype.side_effect = lambda sid, datatype: str(
            tmp_path / f"sub-{sid}" / datatype
        )
        return pm

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._ingest_modality")
    def test_converts_every_present_modality(self, mock_ingest, mock_gpm, tmp_path):
        """T1w, T2w, ct and dwi are all ingested when present."""
        sourcedata = tmp_path / "sourcedata" / "sub-001"
        for modality, _ in MODALITIES:
            (sourcedata / modality).mkdir(parents=True)
        mock_gpm.return_value = self._path_manager(tmp_path)
        mock_ingest.return_value = True

        run_dicom_to_nifti("/proj", "001", logger=MagicMock())

        assert [call.args[3] for call in mock_ingest.call_args_list] == [
            "T1w",
            "T2w",
            "ct",
            "dwi",
        ]

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._ingest_modality")
    def test_skips_absent_modality_folders(self, mock_ingest, mock_gpm, tmp_path):
        """A subject with only T1w must not trigger CT or DWI work."""
        (tmp_path / "sourcedata" / "sub-001" / "T1w").mkdir(parents=True)
        mock_gpm.return_value = self._path_manager(tmp_path)
        mock_ingest.return_value = True

        run_dicom_to_nifti("/proj", "001", logger=MagicMock())

        assert [call.args[3] for call in mock_ingest.call_args_list] == ["T1w"]

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._ingest_modality")
    def test_ct_goes_to_anat_and_dwi_to_dwi(self, mock_ingest, mock_gpm, tmp_path):
        """CT is a local extension living in anat/; DWI goes where QSIPrep looks."""
        sourcedata = tmp_path / "sourcedata" / "sub-001"
        (sourcedata / "ct").mkdir(parents=True)
        (sourcedata / "dwi").mkdir(parents=True)
        mock_gpm.return_value = self._path_manager(tmp_path)
        mock_ingest.return_value = True

        run_dicom_to_nifti("/proj", "001", logger=MagicMock())

        destinations = {
            call.args[3]: call.args[1] for call in mock_ingest.call_args_list
        }
        assert destinations["ct"] == tmp_path / "sub-001" / "anat"
        assert destinations["dwi"] == tmp_path / "sub-001" / "dwi"

    @patch(f"{MODULE}.get_path_manager")
    @patch(f"{MODULE}._ingest_modality")
    def test_no_converted_warns(self, mock_ingest, mock_gpm, tmp_path):
        (tmp_path / "sourcedata" / "sub-001" / "T1w").mkdir(parents=True)
        mock_gpm.return_value = self._path_manager(tmp_path)
        mock_ingest.return_value = False
        logger = MagicMock()

        run_dicom_to_nifti("/proj", "001", logger=logger)

        logger.warning.assert_called_once()
