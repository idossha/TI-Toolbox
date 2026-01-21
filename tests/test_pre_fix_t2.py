#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox T2 filename fixing (pre/fix_t2_filenames.py)
"""

import os
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from pre.fix_t2_filenames import _clean_name, run_fix_t2_filenames
from pre.common import PreprocessError


class TestCleanName:
    """Test _clean_name function"""

    def test_clean_removes_special_characters(self):
        """Test removes special characters"""
        name = "file@name#with$special%chars"
        cleaned = _clean_name(name)
        assert "@" not in cleaned
        assert "#" not in cleaned
        assert "$" not in cleaned
        assert "%" not in cleaned

    def test_clean_replaces_special_with_underscore(self):
        """Test special characters replaced with underscore"""
        name = "file name with spaces"
        cleaned = _clean_name(name)
        assert " " not in cleaned
        assert "_" in cleaned

    def test_clean_collapses_multiple_underscores(self):
        """Test multiple underscores collapsed to single"""
        name = "file___with___multiple___underscores"
        cleaned = _clean_name(name)
        assert "___" not in cleaned
        assert "__" not in cleaned

    def test_clean_strips_leading_trailing_underscores(self):
        """Test strips leading and trailing underscores"""
        name = "___filename___"
        cleaned = _clean_name(name)
        assert not cleaned.startswith("_")
        assert not cleaned.endswith("_")

    def test_clean_preserves_alphanumeric(self):
        """Test preserves alphanumeric characters"""
        name = "abc123XYZ"
        cleaned = _clean_name(name)
        assert cleaned == "abc123XYZ"

    def test_clean_preserves_dots_and_hyphens(self):
        """Test preserves dots and hyphens"""
        name = "file-name.with.dots"
        cleaned = _clean_name(name)
        assert "file-name.with.dots" == cleaned

    def test_clean_detects_t1_uppercase(self):
        """Test detects T1 and returns standard name (uppercase)"""
        name = "scan_T1_mprage"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T1w_acq-MPRAGE"

    def test_clean_detects_t1_lowercase(self):
        """Test detects T1 and returns standard name (lowercase)"""
        name = "scan_t1_mprage"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T1w_acq-MPRAGE"

    def test_clean_detects_t1_mixed_case(self):
        """Test detects T1 and returns standard name (mixed case)"""
        name = "scan_t1_MPRAGE"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T1w_acq-MPRAGE"

    def test_clean_detects_t2_uppercase(self):
        """Test detects T2 and returns standard name (uppercase)"""
        name = "scan_T2_cube"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T2w_acq-CUBE"

    def test_clean_detects_t2_lowercase(self):
        """Test detects T2 and returns standard name (lowercase)"""
        name = "scan_t2_cube"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T2w_acq-CUBE"

    def test_clean_detects_t2_mixed_case(self):
        """Test detects T2 and returns standard name (mixed case)"""
        name = "scan_T2_CUBE"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T2w_acq-CUBE"

    def test_clean_t1_takes_precedence_over_cleanup(self):
        """Test T1 detection returns standard name instead of cleaned name"""
        name = "weird@T1#scan$name"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T1w_acq-MPRAGE"

    def test_clean_t2_takes_precedence_over_cleanup(self):
        """Test T2 detection returns standard name instead of cleaned name"""
        name = "weird@T2#scan$name"
        cleaned = _clean_name(name)
        assert cleaned == "anat-T2w_acq-CUBE"

    def test_clean_returns_cleaned_name_for_other_sequences(self):
        """Test returns cleaned name for non-T1/T2 sequences"""
        name = "flair scan name"
        cleaned = _clean_name(name)
        assert cleaned == "flair_scan_name"

    def test_clean_empty_string(self):
        """Test handles empty string"""
        name = ""
        cleaned = _clean_name(name)
        assert cleaned == ""


class TestRunFixT2Filenames:
    """Test run_fix_t2_filenames function"""

    def test_run_raises_on_nonexistent_project_dir(self):
        """Test raises PreprocessError if project directory doesn't exist"""
        logger = MagicMock()

        with pytest.raises(PreprocessError) as exc_info:
            run_fix_t2_filenames("/nonexistent/directory", logger=logger)

        assert "does not exist" in str(exc_info.value)

    def test_run_processes_subjects_with_anat_dirs(self):
        """Test processes subjects that have anat directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project structure
            sub1_anat = Path(tmpdir) / "sub-001" / "anat"
            sub2_anat = Path(tmpdir) / "sub-002" / "anat"
            sub1_anat.mkdir(parents=True)
            sub2_anat.mkdir(parents=True)

            # Create files with spaces (should be renamed)
            (sub1_anat / "sub-001 T2w.nii.gz").touch()
            (sub2_anat / "sub-002 T2w.json").touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # Verify files were renamed
            assert not (sub1_anat / "sub-001 T2w.nii.gz").exists()
            assert not (sub2_anat / "sub-002 T2w.json").exists()

            # Should have new cleaned names
            renamed_files_sub1 = list(sub1_anat.glob("*.nii.gz"))
            renamed_files_sub2 = list(sub2_anat.glob("*.json"))
            assert len(renamed_files_sub1) == 1
            assert len(renamed_files_sub2) == 1

    def test_run_renames_files_with_spaces(self):
        """Test renames files with spaces in filename"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_anat = Path(tmpdir) / "sub-001" / "anat"
            sub_anat.mkdir(parents=True)

            original_file = sub_anat / "scan T2 data.nii.gz"
            original_file.touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # Original file should not exist
            assert not original_file.exists()

            # Should have renamed file without spaces
            new_files = list(sub_anat.glob("*.nii.gz"))
            assert len(new_files) == 1
            assert " " not in new_files[0].name

    def test_run_renames_files_with_t2_in_name(self):
        """Test renames files with T2 in filename"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_anat = Path(tmpdir) / "sub-001" / "anat"
            sub_anat.mkdir(parents=True)

            original_file = sub_anat / "scan_T2_cube.nii.gz"
            original_file.touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # File should be renamed to standard T2w name
            new_files = list(sub_anat.glob("*.nii.gz"))
            assert len(new_files) == 1
            assert "T2w" in new_files[0].name

    def test_run_skips_files_without_spaces_or_t2(self):
        """Test skips files that don't need renaming"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_anat = Path(tmpdir) / "sub-001" / "anat"
            sub_anat.mkdir(parents=True)

            # File that doesn't need renaming
            original_file = sub_anat / "sub-001_T1w.nii.gz"
            original_file.touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # File should still exist with same name
            assert original_file.exists()

    def test_run_handles_multiple_file_extensions(self):
        """Test handles files with multiple extensions"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_anat = Path(tmpdir) / "sub-001" / "anat"
            sub_anat.mkdir(parents=True)

            # File with multiple extensions
            original_file = sub_anat / "scan T2 data.nii.gz"
            original_file.touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # Extension should be preserved
            new_files = list(sub_anat.glob("*.nii.gz"))
            assert len(new_files) == 1
            assert new_files[0].name.endswith(".nii.gz")

    def test_run_handles_name_collision_with_timestamp(self):
        """Test handles name collision by adding timestamp"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_anat = Path(tmpdir) / "sub-001" / "anat"
            sub_anat.mkdir(parents=True)

            # Create file that will be the target of rename
            target_file = sub_anat / "anat-T2w_acq-CUBE.nii.gz"
            target_file.touch()

            # Create file that will be renamed to same name
            original_file = sub_anat / "scan T2 data.nii.gz"
            original_file.touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # Both files should exist (one with timestamp suffix)
            nii_files = list(sub_anat.glob("*.nii.gz"))
            assert len(nii_files) == 2
            assert target_file.exists()

    def test_run_skips_non_directory_subjects(self):
        """Test skips non-directory items in project root"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file (not directory) with sub- prefix
            (Path(tmpdir) / "sub-001").touch()

            # Create an actual subject directory
            sub_anat = Path(tmpdir) / "sub-002" / "anat"
            sub_anat.mkdir(parents=True)
            (sub_anat / "scan T2.nii.gz").touch()

            logger = MagicMock()

            # Should not raise error
            run_fix_t2_filenames(tmpdir, logger=logger)

    def test_run_skips_subjects_without_anat_dir(self):
        """Test skips subjects without anat directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create subject directory without anat
            sub_dir = Path(tmpdir) / "sub-001"
            sub_dir.mkdir()

            logger = MagicMock()

            # Should not raise error
            run_fix_t2_filenames(tmpdir, logger=logger)

    def test_run_logs_progress(self):
        """Test logs progress messages"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_anat = Path(tmpdir) / "sub-001" / "anat"
            sub_anat.mkdir(parents=True)
            (sub_anat / "scan T2.nii.gz").touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # Verify logging was called
            assert logger.info.called
            info_messages = [call[0][0] for call in logger.info.call_args_list]

            # Should log processing subject
            assert any("sub-001" in msg for msg in info_messages)

            # Should log completion
            assert any("Completed" in msg for msg in info_messages)

    def test_run_processes_multiple_subjects(self):
        """Test processes multiple subjects"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple subjects
            for subject_id in ["001", "002", "003"]:
                sub_anat = Path(tmpdir) / f"sub-{subject_id}" / "anat"
                sub_anat.mkdir(parents=True)
                (sub_anat / f"scan T2 {subject_id}.nii.gz").touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # Verify all subjects were processed
            info_messages = [call[0][0] for call in logger.info.call_args_list]
            completion_message = [msg for msg in info_messages if "Completed" in msg][0]
            assert "3 subjects" in completion_message

    def test_run_handles_files_with_lowercase_t2(self):
        """Test handles files with lowercase t2"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_anat = Path(tmpdir) / "sub-001" / "anat"
            sub_anat.mkdir(parents=True)

            original_file = sub_anat / "scan_t2_data.nii.gz"
            original_file.touch()

            logger = MagicMock()

            run_fix_t2_filenames(tmpdir, logger=logger)

            # Should be renamed
            assert not original_file.exists()
            new_files = list(sub_anat.glob("*.nii.gz"))
            assert len(new_files) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
