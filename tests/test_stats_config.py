"""Unit tests for tit.stats.config — enums, subject configs, main configs, CSV loaders."""

from __future__ import annotations

import csv
import importlib
import os
import sys
from unittest.mock import patch

import pytest

from tit.stats.config import (
    Alternative,
    ClusterStat,
    CorrelationConfig,
    CorrelationSubject,
    CorrelationType,
    GroupComparisonConfig,
    GroupSubject,
    TestType,
    TissueType,
    load_correlation_subjects,
    load_group_subjects,
)

# ============================================================================
# Enums
# ============================================================================


@pytest.mark.unit
class TestEnums:
    def test_tissue_type_values(self):
        assert TissueType.GREY.value == "grey"
        assert TissueType.WHITE.value == "white"
        assert TissueType.ALL.value == "all"

    def test_test_type_values(self):
        assert TestType.UNPAIRED.value == "unpaired"
        assert TestType.PAIRED.value == "paired"

    def test_cluster_stat_values(self):
        assert ClusterStat.MASS.value == "mass"
        assert ClusterStat.SIZE.value == "size"

    def test_alternative_values(self):
        assert Alternative.TWO_SIDED.value == "two-sided"
        assert Alternative.GREATER.value == "greater"
        assert Alternative.LESS.value == "less"

    def test_correlation_type_values(self):
        assert CorrelationType.PEARSON.value == "pearson"
        assert CorrelationType.SPEARMAN.value == "spearman"


# ============================================================================
# Subject configs
# ============================================================================


@pytest.mark.unit
class TestSubjectConfigs:
    def test_group_subject_construction(self):
        gs = GroupSubject(subject_id="001", simulation_name="montage1", response=1)
        assert gs.subject_id == "001"
        assert gs.simulation_name == "montage1"
        assert gs.response == 1

    def test_correlation_subject_construction(self):
        cs = CorrelationSubject(
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
        cs = CorrelationSubject(
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
            GroupSubject("s1", "sim1", 1),
            GroupSubject("s2", "sim2", 0),
        ]

    def _make_correlation_subjects(self):
        return [
            CorrelationSubject("s1", "sim1", 0.5),
            CorrelationSubject("s2", "sim2", 1.0),
            CorrelationSubject("s3", "sim3", 1.5),
        ]

    def test_group_comparison_config_construction(self):
        subjects = self._make_group_subjects()
        cfg = GroupComparisonConfig(
            project_dir="/data/project",
            analysis_name="test_analysis",
            subjects=subjects,
        )
        assert cfg.project_dir == "/data/project"
        assert cfg.analysis_name == "test_analysis"
        assert len(cfg.subjects) == 2
        # Verify defaults
        assert cfg.test_type == TestType.UNPAIRED
        assert cfg.alternative == Alternative.TWO_SIDED
        assert cfg.cluster_threshold == 0.05
        assert cfg.cluster_stat == ClusterStat.MASS
        assert cfg.n_permutations == 1000
        assert cfg.alpha == 0.05
        assert cfg.n_jobs == -1
        assert cfg.tissue_type == TissueType.GREY
        assert cfg.group1_name == "Responders"
        assert cfg.group2_name == "Non-Responders"
        # __post_init__ sets nifti_file_pattern
        assert (
            cfg.nifti_file_pattern == "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_correlation_config_construction(self):
        subjects = self._make_correlation_subjects()
        cfg = CorrelationConfig(
            project_dir="/data/project",
            analysis_name="corr_test",
            subjects=subjects,
        )
        assert cfg.project_dir == "/data/project"
        assert cfg.analysis_name == "corr_test"
        assert len(cfg.subjects) == 3
        # Verify defaults
        assert cfg.correlation_type == CorrelationType.PEARSON
        assert cfg.cluster_threshold == 0.05
        assert cfg.cluster_stat == ClusterStat.MASS
        assert cfg.n_permutations == 1000
        assert cfg.alpha == 0.05
        assert cfg.use_weights is True
        assert cfg.tissue_type == TissueType.GREY
        assert cfg.effect_metric == "Effect Size"
        assert cfg.field_metric == "Electric Field Magnitude"
        assert (
            cfg.nifti_file_pattern == "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
        )


# ============================================================================
# CSV loaders
# ============================================================================


@pytest.mark.skip(
    reason="Unmocking numpy/pandas corrupts sys.modules for all subsequent tests. "
    "CSV loader logic is fully tested in test_stats_full.py with proper mocking."
)
@pytest.mark.unit
class TestCSVLoaders:
    """CSV loader tests — SKIPPED.

    These tests permanently destroy numpy/pandas mocks from sys.modules,
    which breaks all subsequent test files. The CSV loader functions are
    now tested in test_stats_full.py using mock pandas instead.
    """

    _real_config = None

    @classmethod
    def _get_config_with_real_pandas(cls):
        """Return a reloaded tit.stats.config module that uses real pandas.

        Removes numpy/pandas mocks once, imports the real packages, and
        caches the module.  The mocks are NOT restored because numpy's C
        extension cannot be loaded a second time in the same process.
        """
        if cls._real_config is not None:
            return cls._real_config

        prefixes = ("numpy", "pandas")
        keys_to_pop = [
            k
            for k in sys.modules
            if any(k == p or k.startswith(p + ".") for p in prefixes)
        ]
        for k in keys_to_pop:
            del sys.modules[k]

        mod = importlib.import_module("tit.stats.config")
        importlib.reload(mod)
        cls._real_config = mod
        return mod

    def test_load_group_subjects(self, tmp_path):
        csv_file = tmp_path / "group.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["subject_id", "simulation_name", "response"])
            writer.writerow(["sub-001", "montage1", 1])
            writer.writerow(["sub-002", "montage2", 0])
            writer.writerow(["003", "montage3", 1])

        mod = self._get_config_with_real_pandas()
        subjects = mod.load_group_subjects(str(csv_file))

        assert len(subjects) == 3
        # sub- prefix is stripped
        assert subjects[0].subject_id == "001"
        assert subjects[0].simulation_name == "montage1"
        assert subjects[0].response == 1
        assert subjects[1].subject_id == "002"
        assert subjects[1].response == 0
        # No sub- prefix -- kept as-is
        assert subjects[2].subject_id == "003"

    def test_load_correlation_subjects(self, tmp_path):
        csv_file = tmp_path / "corr.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["subject_id", "simulation_name", "effect_size", "weight"])
            writer.writerow(["sub-001", "montage1", 0.5, 1.5])
            writer.writerow(["sub-002", "montage2", 1.2, 2.0])
            writer.writerow(["sub-003", "montage3", 0.8, 1.0])

        mod = self._get_config_with_real_pandas()
        subjects = mod.load_correlation_subjects(str(csv_file))

        assert len(subjects) == 3
        assert subjects[0].subject_id == "001"
        assert subjects[0].effect_size == 0.5
        assert subjects[0].weight == 1.5
        assert subjects[1].subject_id == "002"
        assert subjects[1].effect_size == 1.2
        assert subjects[1].weight == 2.0
        assert subjects[2].subject_id == "003"
        assert subjects[2].effect_size == 0.8
        assert subjects[2].weight == 1.0
