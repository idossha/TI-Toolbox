#!/usr/bin/env python3
"""
Tests for tit/stats/config.py CorrelationConfig.

Covers:
- CorrelationConfig.__post_init__

The CSV loaders (``load_subjects``) read real files with the ``csv`` module now; their cases
moved to tests/test_stats_config.py::TestCSVLoaders, which writes the CSVs instead of mocking
``pandas.read_csv``.
"""

import sys
from unittest.mock import MagicMock

import pytest

# Mock heavy deps that tit.stats.__init__ pulls in via tit.stats.permutation
for _mod in (
    "nibabel",
    "numpy",
    "numpy.linalg",
    "scipy",
    "scipy.ndimage",
    "scipy.stats",
    "h5py",
    "pandas",
    "joblib",
):
    sys.modules.setdefault(_mod, MagicMock())

from tit.stats.config import (
    CorrelationConfig,
    GroupComparisonConfig,
)

# ---------------------------------------------------------------------------
# CorrelationConfig.__post_init__
# ---------------------------------------------------------------------------


class TestCorrelationConfigPostInit:
    """Tests for CorrelationConfig validation."""

    def _make_subjects(self, n):
        return [
            CorrelationConfig.Subject(
                subject_id=str(i),
                simulation_name=f"sim_{i}",
                effect_size=float(i) * 0.1,
            )
            for i in range(n)
        ]

    def test_sets_default_nifti_pattern(self):
        """nifti_file_pattern defaults based on tissue_type."""
        cfg = CorrelationConfig(
            analysis_name="test",
            subjects=self._make_subjects(3),
        )
        assert "grey" in cfg.nifti_file_pattern

    def test_fewer_than_3_subjects_raises(self):
        """Raise ValueError with fewer than 3 subjects."""
        with pytest.raises(ValueError, match="at least 3 subjects"):
            CorrelationConfig(
                analysis_name="test",
                subjects=self._make_subjects(2),
            )

    def test_exactly_3_subjects_ok(self):
        """Exactly 3 subjects is valid."""
        cfg = CorrelationConfig(
            analysis_name="test",
            subjects=self._make_subjects(3),
        )
        assert len(cfg.subjects) == 3

    def test_custom_nifti_pattern_preserved(self):
        """Explicit nifti_file_pattern is not overwritten."""
        cfg = CorrelationConfig(
            analysis_name="test",
            subjects=self._make_subjects(4),
            nifti_file_pattern="custom_{simulation_name}.nii.gz",
        )
        assert cfg.nifti_file_pattern == "custom_{simulation_name}.nii.gz"
