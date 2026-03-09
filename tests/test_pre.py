"""
Unit tests for tit.pre utilities: discover_subjects and check_m2m_exists.
"""

import os

import pytest

from tit.pre.utils import check_m2m_exists, discover_subjects

# ============================================================================
# discover_subjects
# ============================================================================


class TestDiscoverSubjects:
    """Tests for the discover_subjects helper."""

    @pytest.mark.unit
    def test_discover_subjects_finds_subjects(self, tmp_path):
        """Subjects with valid sourcedata structure are discovered."""
        # Create sourcedata/sub-001/T1w/ with a NIfTI file
        sd1 = tmp_path / "sourcedata" / "sub-001" / "T1w"
        sd1.mkdir(parents=True)
        (sd1 / "sub-001_T1w.nii.gz").touch()

        # Create sourcedata/sub-002/T1w/ with a subdirectory (DICOM series)
        sd2 = tmp_path / "sourcedata" / "sub-002" / "T1w"
        sd2.mkdir(parents=True)
        (sd2 / "series01").mkdir()

        result = discover_subjects(str(tmp_path))
        assert sorted(result) == ["001", "002"]

    @pytest.mark.unit
    def test_discover_subjects_empty(self, tmp_path):
        """An empty project directory returns an empty list."""
        result = discover_subjects(str(tmp_path))
        assert result == []

    @pytest.mark.unit
    def test_discover_subjects_ignores_non_sub(self, tmp_path):
        """Directories not matching sub-* are ignored."""
        # Create non-matching dirs in sourcedata
        sd = tmp_path / "sourcedata"
        sd.mkdir()
        (sd / "other-dir").mkdir()
        (sd / "data").mkdir()
        (sd / "readme.txt").touch()

        # Also create non-matching dirs at project root
        (tmp_path / "docs").mkdir()
        (tmp_path / "code").mkdir()

        result = discover_subjects(str(tmp_path))
        assert result == []


# ============================================================================
# check_m2m_exists
# ============================================================================


class TestCheckM2mExists:
    """Tests for the check_m2m_exists helper."""

    @pytest.mark.unit
    def test_check_m2m_exists_true(self, tmp_path):
        """Returns True when the m2m directory exists."""
        m2m = tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001"
        m2m.mkdir(parents=True)

        assert check_m2m_exists(str(tmp_path), "001") is True

    @pytest.mark.unit
    def test_check_m2m_exists_false(self, tmp_path):
        """Returns False when the m2m directory does not exist."""
        assert check_m2m_exists(str(tmp_path), "999") is False


# ============================================================================
# Public API imports
# ============================================================================


class TestPreImports:
    """Verify the public surface of tit.pre."""

    @pytest.mark.unit
    def test_pre_imports(self):
        """All __all__ names are importable from tit.pre."""
        from tit.pre import (
            check_m2m_exists,
            discover_subjects,
            extract_dti_tensor,
            run_charm,
            run_dicom_to_nifti,
            run_pipeline,
            run_qsiprep,
            run_qsirecon,
            run_recon_all,
            run_subcortical_segmentations,
            run_tissue_analysis,
        )

        # Smoke-check they are callable
        for fn in (
            check_m2m_exists,
            discover_subjects,
            extract_dti_tensor,
            run_charm,
            run_dicom_to_nifti,
            run_pipeline,
            run_qsiprep,
            run_qsirecon,
            run_recon_all,
            run_subcortical_segmentations,
            run_tissue_analysis,
        ):
            assert callable(fn), f"{fn!r} is not callable"
