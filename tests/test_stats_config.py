"""Unit tests for tit.stats.config — enums, subject configs, main configs, CSV loaders."""

from __future__ import annotations

import csv

import pytest

from tit.stats.config import (
    CorrelationConfig,
    GroupComparisonConfig,
)

# ============================================================================
# Enums
# ============================================================================


@pytest.mark.unit
class TestEnums:
    def test_tissue_type_values(self):
        assert GroupComparisonConfig.TissueType.GREY.value == "grey"
        assert GroupComparisonConfig.TissueType.WHITE.value == "white"
        assert GroupComparisonConfig.TissueType.ALL.value == "all"

    def test_test_type_values(self):
        assert GroupComparisonConfig.TestType.UNPAIRED.value == "unpaired"
        assert GroupComparisonConfig.TestType.PAIRED.value == "paired"

    def test_cluster_stat_values(self):
        assert GroupComparisonConfig.ClusterStat.MASS.value == "mass"
        assert GroupComparisonConfig.ClusterStat.SIZE.value == "size"

    def test_alternative_values(self):
        assert GroupComparisonConfig.Alternative.TWO_SIDED.value == "two-sided"
        assert GroupComparisonConfig.Alternative.GREATER.value == "greater"
        assert GroupComparisonConfig.Alternative.LESS.value == "less"

    def test_correlation_type_values(self):
        assert CorrelationConfig.CorrelationType.PEARSON.value == "pearson"
        assert CorrelationConfig.CorrelationType.SPEARMAN.value == "spearman"

    def test_shared_enums_are_same_class(self):
        """ClusterStat and TissueType are the same enum class on both configs."""
        assert GroupComparisonConfig.ClusterStat is CorrelationConfig.ClusterStat
        assert GroupComparisonConfig.TissueType is CorrelationConfig.TissueType


# ============================================================================
# Subject configs
# ============================================================================


@pytest.mark.unit
class TestSubjectConfigs:
    def test_group_subject_construction(self):
        gs = GroupComparisonConfig.Subject(
            subject_id="001", simulation_name="montage1", response=1
        )
        assert gs.subject_id == "001"
        assert gs.simulation_name == "montage1"
        assert gs.response == 1

    def test_correlation_subject_construction(self):
        cs = CorrelationConfig.Subject(
            subject_id="002",
            simulation_name="montage2",
            effect_size=0.75,
            weight=2.0,
        )
        assert cs.subject_id == "002"
        assert cs.simulation_name == "montage2"
        assert cs.effect_size == 0.75
        assert cs.weight == 2.0

    def test_correlation_subject_defaults(self):
        cs = CorrelationConfig.Subject(
            subject_id="003",
            simulation_name="montage3",
            effect_size=1.2,
        )
        assert cs.weight == 1.0


# ============================================================================
# Main configs
# ============================================================================


@pytest.mark.unit
class TestMainConfigs:
    def _make_group_subjects(self):
        return [
            GroupComparisonConfig.Subject("s1", "sim1", 1),
            GroupComparisonConfig.Subject("s2", "sim2", 0),
        ]

    def _make_correlation_subjects(self):
        return [
            CorrelationConfig.Subject("s1", "sim1", 0.5),
            CorrelationConfig.Subject("s2", "sim2", 1.0),
            CorrelationConfig.Subject("s3", "sim3", 1.5),
        ]

    def test_group_comparison_config_construction(self):
        subjects = self._make_group_subjects()
        cfg = GroupComparisonConfig(
            analysis_name="test_analysis",
            subjects=subjects,
        )
        assert cfg.analysis_name == "test_analysis"
        assert len(cfg.subjects) == 2
        # Verify defaults
        assert cfg.test_type == GroupComparisonConfig.TestType.UNPAIRED
        assert cfg.alternative == GroupComparisonConfig.Alternative.TWO_SIDED
        assert cfg.cluster_threshold == 0.05
        assert cfg.cluster_stat == GroupComparisonConfig.ClusterStat.MASS
        assert cfg.n_permutations == 1000
        assert cfg.alpha == 0.05
        assert cfg.n_jobs == -1
        assert cfg.tissue_type == GroupComparisonConfig.TissueType.GREY
        assert cfg.group1_name == "Responders"
        assert cfg.group2_name == "Non-Responders"
        # __post_init__ sets nifti_file_pattern
        assert (
            cfg.nifti_file_pattern == "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_correlation_config_construction(self):
        subjects = self._make_correlation_subjects()
        cfg = CorrelationConfig(
            analysis_name="corr_test",
            subjects=subjects,
        )
        assert cfg.analysis_name == "corr_test"
        assert len(cfg.subjects) == 3
        # Verify defaults
        assert cfg.correlation_type == CorrelationConfig.CorrelationType.PEARSON
        assert cfg.cluster_threshold == 0.05
        assert cfg.cluster_stat == CorrelationConfig.ClusterStat.MASS
        assert cfg.n_permutations == 1000
        assert cfg.alpha == 0.05
        assert cfg.use_weights is True
        assert cfg.tissue_type == CorrelationConfig.TissueType.GREY
        assert cfg.effect_metric == "Effect Size"
        assert cfg.field_metric == "Electric Field Magnitude"
        assert (
            cfg.nifti_file_pattern == "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )


# ============================================================================
# CSV loaders
# ============================================================================


@pytest.mark.unit
class TestCSVLoaders:
    """The participants-CSV loaders, read from real files with the standard ``csv`` module.

    Every expected value below is read off the CSV text the test writes (the spec in the
    loaders' docstrings: ``sub-`` stripped, a trailing ``.0`` stripped, blank/NaN rows skipped
    for correlation, weight 1.0 when absent). The loaders used to call ``pandas.read_csv``,
    which the host suite mocks, so this class was permanently skipped; the real-pandas
    comparison lives in ``tests/numerical/test_stats_csv_loaders.py``.
    """

    @staticmethod
    def _write(path, text, encoding="utf-8"):
        path.write_text(text, encoding=encoding)
        return str(path)

    def test_load_group_subjects(self, tmp_path):
        csv_file = tmp_path / "group.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["subject_id", "simulation_name", "response"])
            writer.writerow(["sub-001", "montage1", 1])
            writer.writerow(["sub-002", "montage2", 0])
            writer.writerow(["003", "montage3", 1])

        subjects = GroupComparisonConfig.load_subjects(str(csv_file))

        assert [(s.subject_id, s.simulation_name, s.response) for s in subjects] == [
            ("001", "montage1", 1),
            ("002", "montage2", 0),
            ("003", "montage3", 1),
        ]
        assert all(isinstance(s, GroupComparisonConfig.Subject) for s in subjects)

    def test_zero_padded_numeric_ids_keep_their_zeros(self, tmp_path):
        """An all-numeric id column is still text: ``001`` names ``sub-001``, not ``sub-1``."""
        path = self._write(
            tmp_path / "ids.csv",
            "subject_id,simulation_name,response\n001,m,1\n010,m,0\n",
        )
        assert [s.subject_id for s in GroupComparisonConfig.load_subjects(path)] == [
            "001",
            "010",
        ]
        path = self._write(
            tmp_path / "ids_corr.csv",
            "subject_id,simulation_name,effect_size\n001,m,0.5\n002,m,1\n003,m,2\n",
        )
        assert [s.subject_id for s in CorrelationConfig.load_subjects(path)] == [
            "001",
            "002",
            "003",
        ]

    def test_spreadsheet_float_cells_are_cleaned(self, tmp_path):
        """A spreadsheet export writes ``3.0``/``sub-10.0`` ids and ``1.0`` responses."""
        path = self._write(
            tmp_path / "floats.csv",
            "subject_id,simulation_name,response\n3.0,a,1.0\nsub-10.0,b,0.0\n",
        )
        subjects = GroupComparisonConfig.load_subjects(path)
        assert [(s.subject_id, s.response) for s in subjects] == [("3", 1), ("10", 0)]
        assert all(type(s.response) is int for s in subjects)

    def test_excel_bom_and_padded_cells_are_read(self, tmp_path):
        """Excel's "CSV UTF-8" starts with a byte-order mark; hand-typed files pad cells."""
        path = self._write(
            tmp_path / "bom.csv",
            "subject_id, simulation_name, response\n sub-001 , L_Insula ,1\n002,L_Insula, 0\n",
            encoding="utf-8-sig",
        )
        assert (tmp_path / "bom.csv").read_bytes()[:3] == b"\xef\xbb\xbf"
        subjects = GroupComparisonConfig.load_subjects(path)
        assert [(s.subject_id, s.simulation_name, s.response) for s in subjects] == [
            ("001", "L_Insula", 1),
            ("002", "L_Insula", 0),
        ]

    def test_group_missing_column_is_named(self, tmp_path):
        path = self._write(tmp_path / "bad.csv", "subject_id,simulation_name\n001,m\n")
        with pytest.raises(ValueError, match="missing required columns.*response"):
            GroupComparisonConfig.load_subjects(path)

    def test_group_row_without_a_response_is_refused(self, tmp_path):
        """A blank response cell is not silently a group label; the row number is named."""
        path = self._write(
            tmp_path / "blank.csv",
            "subject_id,simulation_name,response\n001,m,1\n002,m,\n",
        )
        with pytest.raises(ValueError, match="row 3"):
            GroupComparisonConfig.load_subjects(path)

    def test_load_correlation_subjects(self, tmp_path):
        csv_file = tmp_path / "corr.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["subject_id", "simulation_name", "effect_size", "weight"])
            writer.writerow(["sub-001", "montage1", 0.5, 1.5])
            writer.writerow(["sub-002", "montage2", 1.2, 2.0])
            writer.writerow(["sub-003", "montage3", 0.8, 1.0])

        subjects = CorrelationConfig.load_subjects(str(csv_file))

        assert [
            (s.subject_id, s.simulation_name, s.effect_size, s.weight) for s in subjects
        ] == [
            ("001", "montage1", 0.5, 1.5),
            ("002", "montage2", 1.2, 2.0),
            ("003", "montage3", 0.8, 1.0),
        ]
        assert all(isinstance(s, CorrelationConfig.Subject) for s in subjects)

    def test_correlation_skips_rows_without_id_or_effect(self, tmp_path):
        """Blank and NaN cells skip the row; a blank weight falls back to 1.0."""
        path = self._write(
            tmp_path / "gaps.csv",
            "subject_id,simulation_name,effect_size,weight\n"
            "sub-001,m,0.25,2\n"
            ",m,0.5,1\n"
            "sub-003,m,,1\n"
            "sub-004,m,NaN,1\n"
            "sub-005,m,-1.5e-1,\n"
            "sub-006,m,3,nan\n",
        )
        subjects = CorrelationConfig.load_subjects(path)
        assert [(s.subject_id, s.effect_size, s.weight) for s in subjects] == [
            ("001", 0.25, 2.0),
            ("005", -0.15, 1.0),
            ("006", 3.0, 1.0),
        ]

    def test_correlation_without_weight_column_weighs_one(self, tmp_path):
        path = self._write(
            tmp_path / "noweight.csv",
            "subject_id,simulation_name,effect_size\n7,m,1\n8,m,2\n",
        )
        assert [s.weight for s in CorrelationConfig.load_subjects(path)] == [1.0, 1.0]

    def test_correlation_with_no_usable_row_raises(self, tmp_path):
        path = self._write(
            tmp_path / "empty.csv",
            "subject_id,simulation_name,effect_size\n,m,1\n002,m,\n",
        )
        with pytest.raises(ValueError, match="No valid subjects"):
            CorrelationConfig.load_subjects(path)

    def test_correlation_missing_column_is_named(self, tmp_path):
        path = self._write(tmp_path / "bad.csv", "subject_id,simulation_name\n001,m\n")
        with pytest.raises(ValueError, match="missing required columns.*effect_size"):
            CorrelationConfig.load_subjects(path)

    def test_non_numeric_effect_size_is_refused(self, tmp_path):
        path = self._write(
            tmp_path / "words.csv",
            "subject_id,simulation_name,effect_size\n001,m,high\n",
        )
        with pytest.raises(ValueError, match="high"):
            CorrelationConfig.load_subjects(path)
