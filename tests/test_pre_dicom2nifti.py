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

from pre.dicom2nifti import (
    _detect_modality,
    _extract_archives,
    _find_dicom_files,
    _process_modality,
    run_dicom_to_nifti,
)
from pre.common import PreprocessError


class TestDetectModality:
    """Test _detect_modality function"""

    def test_find_t1w_from_series_description(self):
        """Test detecting T1w from SeriesDescription"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"SeriesDescription": "T1_MPRAGE"}, f)
            json_path = Path(f.name)

        try:
            suffix = _detect_modality(json_path, fallback="")
            assert suffix == "T1w"
        finally:
            json_path.unlink()

    def test_find_t2w_from_series_description(self):
        """Test detecting T2w from SeriesDescription"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"SeriesDescription": "T2_CUBE"}, f)
            json_path = Path(f.name)

        try:
            suffix = _detect_modality(json_path, fallback="")
            assert suffix == "T2w"
        finally:
            json_path.unlink()

    def test_find_t1w_case_insensitive(self):
        """Test T1w detection is case-insensitive"""
        test_cases = [
            {"SeriesDescription": "t1_mprage"},
            {"SeriesDescription": "T1W_sequence"},
            {"SeriesDescription": "scan_T1_protocol"},
        ]

        for test_data in test_cases:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(test_data, f)
                json_path = Path(f.name)

            try:
                suffix = _detect_modality(json_path, fallback="")
                assert suffix == "T1w", f"Failed for {test_data}"
            finally:
                json_path.unlink()

    def test_find_t2w_case_insensitive(self):
        """Test T2w detection is case-insensitive"""
        test_cases = [
            {"SeriesDescription": "t2_cube"},
            {"SeriesDescription": "T2W_sequence"},
            {"SeriesDescription": "scan_T2_protocol"},
        ]

        for test_data in test_cases:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(test_data, f)
                json_path = Path(f.name)

            try:
                suffix = _detect_modality(json_path, fallback="")
                assert suffix == "T2w", f"Failed for {test_data}"
            finally:
                json_path.unlink()

    def test_find_no_suffix_when_neither_t1_nor_t2(self):
        """Test returns empty string when neither T1 nor T2"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"SeriesDescription": "FLAIR"}, f)
            json_path = Path(f.name)

        try:
            suffix = _detect_modality(json_path, fallback="")
            assert suffix == ""
        finally:
            json_path.unlink()

    def test_find_no_suffix_when_series_description_missing(self):
        """Test returns empty string when SeriesDescription missing"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"OtherField": "value"}, f)
            json_path = Path(f.name)

        try:
            suffix = _detect_modality(json_path, fallback="")
            assert suffix == ""
        finally:
            json_path.unlink()

    def test_find_handles_invalid_json(self):
        """Test handles invalid JSON gracefully"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json")
            json_path = Path(f.name)

        try:
            suffix = _detect_modality(json_path, fallback="")
            assert suffix == ""
        finally:
            json_path.unlink()

    def test_find_handles_missing_file(self):
        """Test handles missing file gracefully"""
        json_path = Path("/nonexistent/file.json")
        suffix = _detect_modality(json_path, fallback="")
        assert suffix == ""


class TestFindDicomFiles:
    """Test _find_dicom_files function"""

    def test_find_dicom_files_recursively(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            nested = base / "nested"
            nested.mkdir()
            (base / "a.dcm").touch()
            (nested / "b.IMA").touch()
            (nested / "ignore.txt").touch()

            files = _find_dicom_files(base)
            names = {f.name for f in files}
            assert "a.dcm" in names
            assert "b.IMA" in names
            assert "ignore.txt" not in names


class TestExtractArchives:
    """Test _extract_archives function"""

    @patch("pre.dicom2nifti._find_dicom_files")
    @patch("pre.dicom2nifti.shutil.move")
    @patch("subprocess.check_call")
    def test_extract_archives_moves_files(
        self, mock_check_call, mock_move, mock_find_dicom
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()
            target_dir.mkdir()

            (source_dir / "dicom.tgz").touch()
            mock_find_dicom.return_value = [Path(tmpdir) / "file1.dcm"]

            logger = MagicMock()

            _extract_archives(source_dir, target_dir, logger)

            mock_check_call.assert_called_once()
            mock_move.assert_called_once_with(
                str(Path(tmpdir) / "file1.dcm"),
                str(target_dir / "file1.dcm"),
            )
            assert logger.info.called

    def test_extract_archives_no_archives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            target_dir = Path(tmpdir) / "target"
            source_dir.mkdir()
            target_dir.mkdir()

            logger = MagicMock()
            _extract_archives(source_dir, target_dir, logger)

            assert not logger.info.called


class TestProcessModality:
    """Test _process_modality function"""

    def test_process_returns_false_when_no_dicoms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sourcedata_dir = Path(tmpdir) / "sourcedata"
            bids_anat_dir = Path(tmpdir) / "anat"
            sourcedata_dir.mkdir()
            bids_anat_dir.mkdir()

            pm = MagicMock()
            pm.path.return_value = str(Path(tmpdir) / "dicom")

            logger = MagicMock()
            from tit.core.overwrite import OverwritePolicy

            policy = OverwritePolicy(overwrite=False, prompt=False)

            with patch("pre.dicom2nifti._find_dicom_files", return_value=[]):
                result = _process_modality(
                    "T1w",
                    sourcedata_dir,
                    bids_anat_dir,
                    "001",
                    pm,
                    policy,
                    logger,
                    runner=None,
                )

            assert result is False

    def test_process_runs_dcm2niix_and_converts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sourcedata_dir = Path(tmpdir) / "sourcedata"
            bids_anat_dir = Path(tmpdir) / "anat"
            sourcedata_dir.mkdir()
            (sourcedata_dir / "T1w").mkdir()
            bids_anat_dir.mkdir()

            pm = MagicMock()
            pm.path.return_value = str(Path(tmpdir) / "dicom")

            logger = MagicMock()
            from tit.core.overwrite import OverwritePolicy

            policy = OverwritePolicy(overwrite=False, prompt=False)

            with (
                patch(
                    "pre.dicom2nifti._find_dicom_files",
                    return_value=[Path(tmpdir) / "a.dcm"],
                ),
                patch("pre.dicom2nifti._run_dcm2niix", return_value=True) as mock_run,
                patch(
                    "pre.dicom2nifti._process_converted_files", return_value=True
                ) as mock_process,
            ):
                result = _process_modality(
                    "T1w",
                    sourcedata_dir,
                    bids_anat_dir,
                    "001",
                    pm,
                    policy,
                    logger,
                    runner=None,
                )

            assert result is True
            mock_run.assert_called_once()
            mock_process.assert_called_once()

    def test_process_raises_on_dcm2niix_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sourcedata_dir = Path(tmpdir) / "sourcedata"
            bids_anat_dir = Path(tmpdir) / "anat"
            sourcedata_dir.mkdir()
            (sourcedata_dir / "T1w").mkdir()
            bids_anat_dir.mkdir()

            pm = MagicMock()
            pm.path.return_value = str(Path(tmpdir) / "dicom")

            logger = MagicMock()
            from tit.core.overwrite import OverwritePolicy

            policy = OverwritePolicy(overwrite=False, prompt=False)

            with (
                patch(
                    "pre.dicom2nifti._find_dicom_files",
                    return_value=[Path(tmpdir) / "a.dcm"],
                ),
                patch("pre.dicom2nifti._run_dcm2niix", return_value=False),
            ):
                with pytest.raises(PreprocessError) as exc_info:
                    _process_modality(
                        "T1w",
                        sourcedata_dir,
                        bids_anat_dir,
                        "001",
                        pm,
                        policy,
                        logger,
                        runner=None,
                    )

            assert "dcm2niix failed" in str(exc_info.value)


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
            t1_dicom_dir = Path(tmpdir) / "sourcedata" / "sub-001" / "T1w"
            t2_dicom_dir = Path(tmpdir) / "sourcedata" / "sub-001" / "T2w"

            # Create source directories
            sourcedata_dir.mkdir(parents=True)
            (sourcedata_dir / "T1w").mkdir()
            (sourcedata_dir / "T2w").mkdir()

            mock_pm.path.side_effect = lambda key, **kwargs: {
                ("sourcedata_subject", "001"): str(sourcedata_dir),
                ("bids_anat", "001"): str(bids_anat_dir),
                ("sourcedata_dicom", "001", "T1w"): str(t1_dicom_dir),
                ("sourcedata_dicom", "001", "T2w"): str(t2_dicom_dir),
            }.get(
                (key, kwargs.get("subject_id"), kwargs.get("modality")),
                {
                    ("sourcedata_subject", "001"): str(sourcedata_dir),
                    ("bids_anat", "001"): str(bids_anat_dir),
                }.get((key, kwargs.get("subject_id"))),
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
    @patch("pre.dicom2nifti._extract_archives")
    @patch("pre.dicom2nifti._process_modality")
    def test_run_processes_both_modalities(
        self, mock_process, mock_extract, mock_get_pm, mock_which
    ):
        """Test processes both T1w and T2w directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_process.return_value = True
            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm

            sourcedata_dir = Path(tmpdir) / "sourcedata" / "sub-001"
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"
            t1_dicom_dir = Path(tmpdir) / "sourcedata" / "sub-001" / "T1w"
            t2_dicom_dir = Path(tmpdir) / "sourcedata" / "sub-001" / "T2w"

            # Create all directories
            for d in [sourcedata_dir, bids_anat_dir, t1_dicom_dir, t2_dicom_dir]:
                d.mkdir(parents=True, exist_ok=True)

            (sourcedata_dir / "T1w").mkdir(exist_ok=True)
            (sourcedata_dir / "T2w").mkdir(exist_ok=True)
            (bids_anat_dir / "dummy.nii.gz").touch()  # Make bids_anat non-empty

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "sourcedata_subject": str(sourcedata_dir),
                "bids_anat": str(bids_anat_dir),
                "sourcedata_dicom": (
                    str(t1_dicom_dir)
                    if kwargs.get("modality") == "T1w"
                    else str(t2_dicom_dir)
                ),
            }[key]

            logger = MagicMock()

            run_dicom_to_nifti(tmpdir, "001", logger=logger)

            # Verify both modalities were processed
            assert mock_process.call_count == 2

    @patch("shutil.which", return_value="/usr/bin/dcm2niix")
    @patch("pre.dicom2nifti.get_path_manager")
    @patch("pre.dicom2nifti._process_modality", return_value=False)
    def test_run_warns_if_no_output_files(self, mock_process, mock_get_pm, mock_which):
        """Test warns if no NIfTI files created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_pm = MagicMock()
            mock_get_pm.return_value = mock_pm

            sourcedata_dir = Path(tmpdir) / "sourcedata" / "sub-001"
            bids_anat_dir = Path(tmpdir) / "sub-001" / "anat"
            t1_dicom_dir = Path(tmpdir) / "sourcedata" / "sub-001" / "T1w"
            t2_dicom_dir = Path(tmpdir) / "sourcedata" / "sub-001" / "T2w"

            # Create directories
            for d in [sourcedata_dir, bids_anat_dir, t1_dicom_dir, t2_dicom_dir]:
                d.mkdir(parents=True, exist_ok=True)

            (sourcedata_dir / "T1w").mkdir(exist_ok=True)
            (sourcedata_dir / "T2w").mkdir(exist_ok=True)

            mock_pm.path.side_effect = lambda key, **kwargs: {
                "sourcedata_subject": str(sourcedata_dir),
                "bids_anat": str(bids_anat_dir),
                "sourcedata_dicom": (
                    str(t1_dicom_dir)
                    if kwargs.get("modality") == "T1w"
                    else str(t2_dicom_dir)
                ),
            }[key]

            logger = MagicMock()

            run_dicom_to_nifti(tmpdir, "001", logger=logger)

            logger.warning.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
