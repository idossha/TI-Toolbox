#!/usr/bin/env python3
"""
Tests for tit/stats/config.py CSV loader functions and CorrelationConfig.

Covers:
- load_group_subjects (lines 198-216)
- load_correlation_subjects (lines 227-261)
- CorrelationConfig.__post_init__ (lines 145-148)
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy deps that tit.stats.__init__ pulls in via tit.stats.permutation
for _mod in ("nibabel", "numpy", "numpy.linalg", "scipy", "scipy.ndimage",
             "scipy.stats", "h5py", "pandas", "joblib"):
    sys.modules.setdefault(_mod, MagicMock())

from tit.stats.config import (
    CorrelationConfig,
    CorrelationSubject,
    GroupSubject,
    load_correlation_subjects,
    load_group_subjects,
)


# ---------------------------------------------------------------------------
# Helpers to build mock DataFrames for the mocked pandas
# ---------------------------------------------------------------------------


def _make_mock_df(columns, rows):
    """Return a MagicMock that behaves like a pandas DataFrame.

    Parameters
    ----------
    columns : list[str]
        Column names.
    rows : list[dict]
        Each dict maps column name -> value for one row.
    """
    df = MagicMock()
    df.columns = columns

    def iterrows():
        for idx, row_dict in enumerate(rows):
            row = MagicMock()
            row.__getitem__ = lambda self, key, _rd=row_dict: _rd[key]
            row.get = lambda key, default=None, _rd=row_dict: _rd.get(key, default)
            yield idx, row

    df.iterrows = iterrows
    return df


# ---------------------------------------------------------------------------
# load_group_subjects
# ---------------------------------------------------------------------------


class TestLoadGroupSubjects:
    """Tests for load_group_subjects."""

    def test_basic_load(self):
        """Load two subjects from a well-formed CSV."""
        rows = [
            {"subject_id": "001", "simulation_name": "sim_a", "response": 1},
            {"subject_id": "002", "simulation_name": "sim_b", "response": 0},
        ]
        mock_df = _make_mock_df(["subject_id", "simulation_name", "response"], rows)

        with patch("pandas.read_csv", return_value=mock_df):
            result = load_group_subjects("/fake/path.csv")

        assert len(result) == 2
        assert isinstance(result[0], GroupSubject)
        assert result[0].subject_id == "001"
        assert result[0].simulation_name == "sim_a"
        assert result[0].response == 1
        assert result[1].subject_id == "002"
        assert result[1].response == 0

    def test_strips_sub_prefix(self):
        """Subject IDs with 'sub-' prefix are stripped."""
        rows = [
            {"subject_id": "sub-005", "simulation_name": "sim_x", "response": 1},
        ]
        mock_df = _make_mock_df(["subject_id", "simulation_name", "response"], rows)

        with patch("pandas.read_csv", return_value=mock_df):
            result = load_group_subjects("/fake/path.csv")

        assert result[0].subject_id == "005"

    def test_strips_dot_zero_suffix(self):
        """Numeric subject IDs that become '3.0' are cleaned to '3'."""
        rows = [
            {"subject_id": "3.0", "simulation_name": "sim_y", "response": 0},
        ]
        mock_df = _make_mock_df(["subject_id", "simulation_name", "response"], rows)

        with patch("pandas.read_csv", return_value=mock_df):
            result = load_group_subjects("/fake/path.csv")

        assert result[0].subject_id == "3"

    def test_strips_sub_prefix_and_dot_zero(self):
        """sub-10.0 becomes '10'."""
        rows = [
            {"subject_id": "sub-10.0", "simulation_name": "sim_z", "response": 1},
        ]
        mock_df = _make_mock_df(["subject_id", "simulation_name", "response"], rows)

        with patch("pandas.read_csv", return_value=mock_df):
            result = load_group_subjects("/fake/path.csv")

        assert result[0].subject_id == "10"

    def test_missing_columns_raises(self):
        """Raise ValueError when required columns are absent."""
        mock_df = MagicMock()
        mock_df.columns = ["subject_id", "simulation_name"]  # missing 'response'

        with patch("pandas.read_csv", return_value=mock_df):
            with pytest.raises(ValueError, match="missing required columns"):
                load_group_subjects("/fake/path.csv")

    def test_multiple_subjects(self):
        """Load several subjects and confirm order is preserved."""
        rows = [
            {"subject_id": str(i), "simulation_name": f"sim_{i}", "response": i % 2}
            for i in range(5)
        ]
        mock_df = _make_mock_df(["subject_id", "simulation_name", "response"], rows)

        with patch("pandas.read_csv", return_value=mock_df):
            result = load_group_subjects("/fake/path.csv")

        assert len(result) == 5
        assert [s.subject_id for s in result] == ["0", "1", "2", "3", "4"]


# ---------------------------------------------------------------------------
# load_correlation_subjects
# ---------------------------------------------------------------------------


class TestLoadCorrelationSubjects:
    """Tests for load_correlation_subjects."""

    def _patch_isna(self):
        """Return a patch context for pd.isna and pd.notna used inside the function."""
        # Since the function does `import pandas as pd` locally,
        # we patch the module-level functions.
        mock_pd = MagicMock()
        mock_pd.isna = lambda v: v is None or (isinstance(v, float) and v != v)
        mock_pd.notna = lambda v: not (v is None or (isinstance(v, float) and v != v))
        return mock_pd

    def test_basic_load(self):
        """Load subjects with required columns only (no weight)."""
        rows = [
            {"subject_id": "001", "simulation_name": "sim_a", "effect_size": 0.5},
            {"subject_id": "002", "simulation_name": "sim_b", "effect_size": 1.2},
        ]
        cols = ["subject_id", "simulation_name", "effect_size"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            # Force re-import to pick up the patched pandas
            result = load_correlation_subjects("/fake/path.csv")

        assert len(result) == 2
        assert isinstance(result[0], CorrelationSubject)
        assert result[0].subject_id == "001"
        assert result[0].effect_size == 0.5
        assert result[0].weight == 1.0  # default

    def test_with_weight_column(self):
        """Load subjects with optional weight column."""
        rows = [
            {
                "subject_id": "001",
                "simulation_name": "sim_a",
                "effect_size": 0.5,
                "weight": 2.0,
            },
            {
                "subject_id": "002",
                "simulation_name": "sim_b",
                "effect_size": 1.2,
                "weight": 0.8,
            },
        ]
        cols = ["subject_id", "simulation_name", "effect_size", "weight"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = load_correlation_subjects("/fake/path.csv")

        assert result[0].weight == 2.0
        assert result[1].weight == 0.8

    def test_skips_nan_subject_id(self):
        """Rows with NaN subject_id are skipped."""
        rows = [
            {"subject_id": None, "simulation_name": "sim_a", "effect_size": 0.5},
            {"subject_id": "002", "simulation_name": "sim_b", "effect_size": 1.2},
        ]
        cols = ["subject_id", "simulation_name", "effect_size"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = load_correlation_subjects("/fake/path.csv")

        assert len(result) == 1
        assert result[0].subject_id == "002"

    def test_skips_nan_effect_size(self):
        """Rows with NaN effect_size are skipped."""
        rows = [
            {"subject_id": "001", "simulation_name": "sim_a", "effect_size": None},
            {"subject_id": "002", "simulation_name": "sim_b", "effect_size": 1.2},
        ]
        cols = ["subject_id", "simulation_name", "effect_size"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = load_correlation_subjects("/fake/path.csv")

        assert len(result) == 1
        assert result[0].subject_id == "002"

    def test_float_subject_id_converted(self):
        """Float subject_id (e.g. 3.0) is converted to int then str."""
        rows = [
            {"subject_id": 3.0, "simulation_name": "sim_a", "effect_size": 0.5},
        ]
        cols = ["subject_id", "simulation_name", "effect_size"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = load_correlation_subjects("/fake/path.csv")

        assert result[0].subject_id == "3"

    def test_string_subject_id_strips_sub_prefix(self):
        """String subject_id with 'sub-' prefix is stripped."""
        rows = [
            {"subject_id": "sub-007", "simulation_name": "sim_a", "effect_size": 0.5},
        ]
        cols = ["subject_id", "simulation_name", "effect_size"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = load_correlation_subjects("/fake/path.csv")

        assert result[0].subject_id == "007"

    def test_string_subject_id_strips_dot_zero(self):
        """String '10.0' has .0 suffix removed."""
        rows = [
            {"subject_id": "10.0", "simulation_name": "sim_a", "effect_size": 0.5},
        ]
        cols = ["subject_id", "simulation_name", "effect_size"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = load_correlation_subjects("/fake/path.csv")

        assert result[0].subject_id == "10"

    def test_no_valid_subjects_raises(self):
        """Raise ValueError when all rows are skipped."""
        rows = [
            {"subject_id": None, "simulation_name": "sim_a", "effect_size": None},
        ]
        cols = ["subject_id", "simulation_name", "effect_size"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            with pytest.raises(ValueError, match="No valid subjects"):
                load_correlation_subjects("/fake/path.csv")

    def test_missing_columns_raises(self):
        """Raise ValueError when required columns are absent."""
        mock_df = MagicMock()
        mock_df.columns = ["subject_id", "simulation_name"]  # missing effect_size
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            with pytest.raises(ValueError, match="missing required columns"):
                load_correlation_subjects("/fake/path.csv")

    def test_weight_defaults_when_nan(self):
        """Weight defaults to 1.0 when weight column exists but value is NaN."""
        rows = [
            {
                "subject_id": "001",
                "simulation_name": "sim_a",
                "effect_size": 0.5,
                "weight": None,
            },
        ]
        cols = ["subject_id", "simulation_name", "effect_size", "weight"]
        mock_df = _make_mock_df(cols, rows)
        mock_pd = self._patch_isna()
        mock_pd.read_csv = MagicMock(return_value=mock_df)

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = load_correlation_subjects("/fake/path.csv")

        assert result[0].weight == 1.0


# ---------------------------------------------------------------------------
# CorrelationConfig.__post_init__
# ---------------------------------------------------------------------------


class TestCorrelationConfigPostInit:
    """Tests for CorrelationConfig validation (lines 144-151)."""

    def _make_subjects(self, n):
        return [
            CorrelationSubject(
                subject_id=str(i),
                simulation_name=f"sim_{i}",
                effect_size=float(i) * 0.1,
            )
            for i in range(n)
        ]

    def test_sets_default_nifti_pattern(self):
        """nifti_file_pattern defaults based on tissue_type."""
        cfg = CorrelationConfig(
            project_dir="/proj",
            analysis_name="test",
            subjects=self._make_subjects(3),
        )
        assert "grey" in cfg.nifti_file_pattern

    def test_fewer_than_3_subjects_raises(self):
        """Raise ValueError with fewer than 3 subjects."""
        with pytest.raises(ValueError, match="at least 3 subjects"):
            CorrelationConfig(
                project_dir="/proj",
                analysis_name="test",
                subjects=self._make_subjects(2),
            )

    def test_exactly_3_subjects_ok(self):
        """Exactly 3 subjects is valid."""
        cfg = CorrelationConfig(
            project_dir="/proj",
            analysis_name="test",
            subjects=self._make_subjects(3),
        )
        assert len(cfg.subjects) == 3

    def test_custom_nifti_pattern_preserved(self):
        """Explicit nifti_file_pattern is not overwritten."""
        cfg = CorrelationConfig(
            project_dir="/proj",
            analysis_name="test",
            subjects=self._make_subjects(4),
            nifti_file_pattern="custom_{simulation_name}.nii.gz",
        )
        assert cfg.nifti_file_pattern == "custom_{simulation_name}.nii.gz"
