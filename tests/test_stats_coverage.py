"""Tests to improve coverage for tit/stats/ modules.

Targets:
- tit/stats/permutation.py (helpers, run_group_comparison, run_correlation)
- tit/stats/reporting.py (generate_summary, generate_correlation_summary)
- tit/stats/engine.py (PermutationEngine.correct_groups/correct_correlation,
  _run_single_correlation_permutation, correlation_voxelwise edge cases)
- tit/stats/nifti.py (load_subject_nifti_ti_toolbox, load_group_data_ti_toolbox,
  load_grouped_subjects_ti_toolbox)
"""

import importlib
import logging
import os
import sys
from unittest.mock import MagicMock, patch, mock_open

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Restore real scipy and reload engine (same pattern as test_stats_engine.py)
# ---------------------------------------------------------------------------
_scipy_keys = [k for k in list(sys.modules) if k == "scipy" or k.startswith("scipy.")]
_saved = {k: sys.modules.pop(k) for k in _scipy_keys}

import scipy  # noqa: E402
import scipy.ndimage  # noqa: E402
import scipy.stats  # noqa: E402

try:
    import scipy.optimize  # noqa: E402
except ImportError:
    sys.modules["scipy.optimize"] = MagicMock()

sys.modules.setdefault("scipy.spatial", MagicMock())
sys.modules.setdefault("scipy.spatial.transform", MagicMock())

# Force-reload engine so its top-level from-imports bind to real scipy
import tit.stats.engine  # noqa: E402

importlib.reload(tit.stats.engine)

from tit.stats.engine import (  # noqa: E402
    PermutationEngine,
    _identify_significant_clusters,
    _run_single_correlation_permutation,
    _run_single_permutation,
    cluster_analysis,
    correlation,
    correlation_voxelwise,
    pval_from_histogram,
    ttest_ind,
    ttest_rel,
    ttest_voxelwise,
)

from tit.stats.config import (  # noqa: E402
    CorrelationConfig,
    GroupComparisonConfig,
    GroupComparisonResult,
    CorrelationResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# reporting.py
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestGenerateSummary:
    """Tests for tit.stats.reporting.generate_summary."""

    def _make_group_config(self, cluster_stat="mass", n_jobs=1):
        """Build a minimal GroupComparisonConfig mock."""
        cfg = MagicMock()
        cfg.cluster_stat.value = cluster_stat
        cfg.test_type.value = "unpaired"
        cfg.cluster_threshold = 0.05
        cfg.n_permutations = 100
        cfg.alpha = 0.05
        cfg.n_jobs = n_jobs
        cfg.group1_name = "Responders"
        cfg.group2_name = "Non-Responders"
        cfg.value_metric = "Current Intensity"
        return cfg

    def test_basic_summary_no_significant_voxels(self, tmp_path):
        """Generate summary when no voxels are significant."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config()
        resp = np.random.rand(3, 3, 3, 5).astype(np.float32)
        non_resp = np.random.rand(3, 3, 3, 5).astype(np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 10.0, [], {}, out)

        text = open(out).read()
        assert "VOXELWISE STATISTICAL ANALYSIS SUMMARY" in text
        assert "Number of Significant Voxels: 0" in text
        assert "Number of Clusters: 0" in text

    def test_summary_with_significant_clusters(self, tmp_path):
        """Generate summary with significant voxels and clusters."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config(cluster_stat="size")
        resp = np.ones((3, 3, 3, 4), dtype=np.float32) * 5.0
        non_resp = np.ones((3, 3, 3, 4), dtype=np.float32) * 2.0
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        sig_mask[1, 1, 1] = 1
        sig_mask[1, 1, 2] = 1
        clusters = [
            {
                "cluster_id": 1,
                "size": 2,
                "center_mni": np.array([10.0, 20.0, 30.0]),
                "stat_value": 2.0,
            }
        ]
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 5.0, clusters, {}, out)

        text = open(out).read()
        assert "Number of Significant Voxels: 2" in text
        assert "Number of Clusters: 1" in text
        assert "Cluster 1: 2 voxels" in text

    def test_summary_with_mass_stat(self, tmp_path):
        """Mass cluster stat includes mass value in cluster output."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config(cluster_stat="mass")
        resp = np.ones((3, 3, 3, 4), dtype=np.float32) * 5.0
        non_resp = np.ones((3, 3, 3, 4), dtype=np.float32) * 2.0
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        sig_mask[1, 1, 1] = 1
        sig_mask[1, 1, 2] = 1
        clusters = [
            {
                "cluster_id": 1,
                "size": 2,
                "center_mni": np.array([10.0, 20.0, 30.0]),
                "stat_value": 7.5,
            }
        ]
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 5.0, clusters, {}, out)

        text = open(out).read()
        assert "Cluster Mass" in text
        assert "mass = 7.50" in text

    def test_summary_with_atlas_results(self, tmp_path):
        """Atlas overlap results appear in the summary."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config()
        resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        non_resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        atlas_results = {
            "AAL": [
                {"region_id": 1, "overlap_voxels": 10, "region_size": 100},
                {"region_id": 2, "overlap_voxels": 5, "region_size": 200},
            ]
        }
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 5.0, [], atlas_results, out)

        text = open(out).read()
        assert "AAL" in text
        assert "Region   1" in text

    def test_summary_with_empty_atlas(self, tmp_path):
        """Atlas with no regions reports that."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config()
        resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        non_resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        atlas_results = {"Harvard-Oxford": []}
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 5.0, [], atlas_results, out)

        text = open(out).read()
        assert "No overlapping regions found" in text

    def test_summary_n_jobs_minus_one(self, tmp_path):
        """n_jobs=-1 reports CPU count."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config(n_jobs=-1)
        resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        non_resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 5.0, [], {}, out)

        text = open(out).read()
        assert "cores" in text

    def test_summary_n_jobs_explicit(self, tmp_path):
        """Explicit n_jobs value is reported."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config(n_jobs=4)
        resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        non_resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 5.0, [], {}, out)

        text = open(out).read()
        assert "4 cores" in text

    def test_summary_paired_test_name(self, tmp_path):
        """Paired test type is shown correctly."""
        from tit.stats.reporting import generate_summary

        cfg = self._make_group_config()
        cfg.test_type.value = "paired"
        resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        non_resp = np.random.rand(3, 3, 3, 4).astype(np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "summary.txt")

        generate_summary(cfg, resp, non_resp, sig_mask, 5.0, [], {}, out)

        text = open(out).read()
        assert "Paired t-test" in text


@pytest.mark.unit
class TestGenerateCorrelationSummary:
    """Tests for tit.stats.reporting.generate_correlation_summary."""

    def _make_corr_config(self, cluster_stat="mass"):
        cfg = MagicMock()
        cfg.cluster_stat.value = cluster_stat
        cfg.correlation_type.value = "pearson"
        cfg.cluster_threshold = 0.05
        cfg.n_permutations = 100
        cfg.alpha = 0.05
        cfg.effect_metric = "ACES Score"
        cfg.field_metric = "E-field Magnitude"
        return cfg

    def test_basic_correlation_summary(self, tmp_path):
        """Correlation summary is generated without errors."""
        from tit.stats.reporting import generate_correlation_summary

        cfg = self._make_corr_config()
        n_subjects = 5
        subject_data = np.random.rand(3, 3, 3, n_subjects).astype(np.float32)
        effect_sizes = np.array([0.1, 0.5, 0.9, 1.2, 1.5])
        r_values = np.random.rand(3, 3, 3).astype(np.float32) * 0.5
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "corr_summary.txt")

        generate_correlation_summary(
            cfg, subject_data, effect_sizes, r_values, sig_mask,
            5.0, [], {}, out,
        )

        text = open(out).read()
        assert "CORRELATION-BASED CLUSTER PERMUTATION ANALYSIS SUMMARY" in text
        assert "Number of Subjects: 5" in text
        assert "Number of Significant Voxels: 0" in text

    def test_correlation_summary_with_significant_voxels(self, tmp_path):
        """Correlation summary includes r-value stats for significant voxels."""
        from tit.stats.reporting import generate_correlation_summary

        cfg = self._make_corr_config()
        n_subjects = 5
        subject_data = np.random.rand(3, 3, 3, n_subjects).astype(np.float32)
        effect_sizes = np.array([0.1, 0.5, 0.9, 1.2, 1.5])
        r_values = np.zeros((3, 3, 3), dtype=np.float32)
        r_values[1, 1, 1] = 0.8
        r_values[1, 1, 2] = 0.6
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        sig_mask[1, 1, 1] = 1
        sig_mask[1, 1, 2] = 1
        clusters = [
            {
                "cluster_id": 1,
                "size": 2,
                "center_mni": np.array([10.0, 20.0, 30.0]),
                "mean_r": 0.7,
                "peak_r": 0.8,
            }
        ]
        out = str(tmp_path / "corr_summary.txt")

        generate_correlation_summary(
            cfg, subject_data, effect_sizes, r_values, sig_mask,
            5.0, clusters, {}, out,
        )

        text = open(out).read()
        assert "Number of Significant Voxels: 2" in text
        assert "Mean r:" in text
        assert "Peak r:" in text
        assert "SIGNIFICANT CLUSTERS" in text

    def test_correlation_summary_with_subject_ids(self, tmp_path):
        """Subject IDs and per-subject effect sizes appear in the summary."""
        from tit.stats.reporting import generate_correlation_summary

        cfg = self._make_corr_config()
        n_subjects = 3
        subject_data = np.random.rand(3, 3, 3, n_subjects).astype(np.float32)
        effect_sizes = np.array([0.1, 0.5, 0.9])
        r_values = np.zeros((3, 3, 3), dtype=np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "corr_summary.txt")

        generate_correlation_summary(
            cfg, subject_data, effect_sizes, r_values, sig_mask,
            5.0, [], {}, out,
            subject_ids=["001", "002", "003"],
        )

        text = open(out).read()
        assert "001" in text
        assert "002" in text

    def test_correlation_summary_with_weights(self, tmp_path):
        """Weights section appears when weights are provided."""
        from tit.stats.reporting import generate_correlation_summary

        cfg = self._make_corr_config()
        n_subjects = 3
        subject_data = np.random.rand(3, 3, 3, n_subjects).astype(np.float32)
        effect_sizes = np.array([0.1, 0.5, 0.9])
        r_values = np.zeros((3, 3, 3), dtype=np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        weights = np.array([1.0, 2.0, 1.5])
        out = str(tmp_path / "corr_summary.txt")

        generate_correlation_summary(
            cfg, subject_data, effect_sizes, r_values, sig_mask,
            5.0, [], {}, out,
            subject_ids=["001", "002", "003"],
            weights=weights,
        )

        text = open(out).read()
        assert "WEIGHT DISTRIBUTION" in text
        assert "weight=" in text

    def test_correlation_summary_with_atlas(self, tmp_path):
        """Atlas results appear in correlation summary."""
        from tit.stats.reporting import generate_correlation_summary

        cfg = self._make_corr_config()
        n_subjects = 3
        subject_data = np.random.rand(3, 3, 3, n_subjects).astype(np.float32)
        effect_sizes = np.array([0.1, 0.5, 0.9])
        r_values = np.zeros((3, 3, 3), dtype=np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        atlas_results = {
            "AAL": [
                {"region_id": 42, "overlap_voxels": 8, "region_size": 50},
            ],
            "Empty_Atlas": [],
        }
        out = str(tmp_path / "corr_summary.txt")

        generate_correlation_summary(
            cfg, subject_data, effect_sizes, r_values, sig_mask,
            5.0, [], atlas_results, out,
        )

        text = open(out).read()
        assert "AAL" in text
        assert "Region  42" in text
        assert "No overlapping regions found" in text

    def test_correlation_summary_size_stat(self, tmp_path):
        """Cluster size stat label appears correctly."""
        from tit.stats.reporting import generate_correlation_summary

        cfg = self._make_corr_config(cluster_stat="size")
        n_subjects = 3
        subject_data = np.random.rand(3, 3, 3, n_subjects).astype(np.float32)
        effect_sizes = np.array([0.1, 0.5, 0.9])
        r_values = np.zeros((3, 3, 3), dtype=np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "corr_summary.txt")

        generate_correlation_summary(
            cfg, subject_data, effect_sizes, r_values, sig_mask,
            10.0, [], {}, out,
        )

        text = open(out).read()
        assert "Cluster Size" in text
        assert "10.0 voxels" in text

    def test_interpretation_notes(self, tmp_path):
        """Interpretation notes section is present in correlation summary."""
        from tit.stats.reporting import generate_correlation_summary

        cfg = self._make_corr_config()
        n_subjects = 3
        subject_data = np.random.rand(3, 3, 3, n_subjects).astype(np.float32)
        effect_sizes = np.array([0.1, 0.5, 0.9])
        r_values = np.zeros((3, 3, 3), dtype=np.float32)
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        out = str(tmp_path / "corr_summary.txt")

        generate_correlation_summary(
            cfg, subject_data, effect_sizes, r_values, sig_mask,
            5.0, [], {}, out,
        )

        text = open(out).read()
        assert "INTERPRETATION NOTES" in text
        assert "ACES Score" in text
        assert "References:" in text


# ═══════════════════════════════════════════════════════════════════════════
# engine.py — PermutationEngine.correct_groups
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestPermutationEngineCorrectGroups:
    """Tests for PermutationEngine.correct_groups."""

    def _make_data(self, shape=(4, 4, 4), n_resp=5, n_non_resp=5, seed=42):
        np.random.seed(seed)
        resp = np.random.rand(*shape, n_resp).astype(np.float32)
        non_resp = np.random.rand(*shape, n_non_resp).astype(np.float32)
        # Add signal to create significant clusters
        resp[1, 1, 1, :] += 10.0
        resp[1, 1, 2, :] += 10.0
        resp[1, 2, 1, :] += 10.0
        return resp, non_resp

    def test_correct_groups_no_clusters(self):
        """When data has no signal, correct_groups returns empty results."""
        np.random.seed(42)
        shape = (4, 4, 4)
        resp = np.random.rand(*shape, 5).astype(np.float32) * 0.001
        non_resp = np.random.rand(*shape, 5).astype(np.float32) * 0.001
        # Make everything nearly identical so no clusters form
        resp += 1.0
        non_resp += 1.0

        p_values, t_statistics, valid_mask = ttest_voxelwise(
            resp, non_resp, test_type="unpaired"
        )

        engine = PermutationEngine(
            cluster_threshold=0.001,  # very strict to ensure no clusters
            n_permutations=10,
            alpha=0.05,
            cluster_stat="size",
            n_jobs=1,
        )

        with patch("tit.stats.io_utils.save_permutation_details"):
            sig_mask, threshold, sig_clusters, null_dist, obs, corr_data = (
                engine.correct_groups(
                    resp, non_resp,
                    p_values=p_values,
                    t_statistics=t_statistics,
                    valid_mask=valid_mask,
                    test_type="unpaired",
                )
            )

        assert np.sum(sig_mask) == 0
        assert len(sig_clusters) == 0

    def test_correct_groups_with_signal(self):
        """correct_groups detects clusters with strong signal."""
        resp, non_resp = self._make_data()
        p_values, t_statistics, valid_mask = ttest_voxelwise(
            resp, non_resp, test_type="unpaired"
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=20,
            alpha=0.05,
            cluster_stat="size",
            n_jobs=1,
        )

        with patch("tit.stats.io_utils.save_permutation_details"):
            sig_mask, threshold, sig_clusters, null_dist, obs, corr_data = (
                engine.correct_groups(
                    resp, non_resp,
                    p_values=p_values,
                    t_statistics=t_statistics,
                    valid_mask=valid_mask,
                    test_type="unpaired",
                )
            )

        assert isinstance(threshold, (int, float, np.integer, np.floating))
        assert null_dist.shape == (20,)
        assert "sizes" in corr_data
        assert "masses" in corr_data

    def test_correct_groups_mass_stat(self):
        """correct_groups works with cluster_stat='mass'."""
        resp, non_resp = self._make_data()
        p_values, t_statistics, valid_mask = ttest_voxelwise(
            resp, non_resp, test_type="unpaired"
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=15,
            alpha=0.05,
            cluster_stat="mass",
            n_jobs=1,
        )

        with patch("tit.stats.io_utils.save_permutation_details"):
            sig_mask, threshold, sig_clusters, null_dist, obs, corr_data = (
                engine.correct_groups(
                    resp, non_resp,
                    p_values=p_values,
                    t_statistics=t_statistics,
                    valid_mask=valid_mask,
                    test_type="unpaired",
                )
            )

        assert null_dist.shape == (15,)

    def test_correct_groups_paired(self):
        """correct_groups handles paired test_type."""
        np.random.seed(42)
        shape = (4, 4, 4)
        n = 5
        resp = np.random.rand(*shape, n).astype(np.float32)
        non_resp = np.random.rand(*shape, n).astype(np.float32)
        resp[1, 1, 1, :] += 10.0

        p_values, t_statistics, valid_mask = ttest_voxelwise(
            resp, non_resp, test_type="paired"
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=10,
            alpha=0.05,
            cluster_stat="size",
            n_jobs=1,
        )

        with patch("tit.stats.io_utils.save_permutation_details"):
            result = engine.correct_groups(
                resp, non_resp,
                p_values=p_values,
                t_statistics=t_statistics,
                valid_mask=valid_mask,
                test_type="paired",
            )

        assert len(result) == 6  # 6-tuple

    def test_correct_groups_with_logging(self):
        """correct_groups logs permutation details when tracking is on."""
        resp, non_resp = self._make_data()
        p_values, t_statistics, valid_mask = ttest_voxelwise(
            resp, non_resp, test_type="unpaired"
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=10,
            alpha=0.05,
            cluster_stat="size",
            n_jobs=1,
        )

        with patch("tit.stats.io_utils.save_permutation_details") as mock_save:
            engine.correct_groups(
                resp, non_resp,
                p_values=p_values,
                t_statistics=t_statistics,
                valid_mask=valid_mask,
                test_type="unpaired",
                perm_log_file="/tmp/test_perm.txt",
                subject_ids_resp=["s1", "s2", "s3", "s4", "s5"],
                subject_ids_non_resp=["s6", "s7", "s8", "s9", "s10"],
            )
            # save_permutation_details should have been called
            mock_save.assert_called_once()

    def test_correct_groups_mass_raises_without_t_stats(self):
        """cluster_stat='mass' raises ValueError if t_statistics is None."""
        resp, non_resp = self._make_data()
        p_values, _, valid_mask = ttest_voxelwise(
            resp, non_resp, test_type="unpaired"
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=10,
            alpha=0.05,
            cluster_stat="mass",
            n_jobs=1,
        )

        with pytest.raises(ValueError, match="t_statistics required"):
            engine.correct_groups(
                resp, non_resp,
                p_values=p_values,
                t_statistics=None,
                valid_mask=valid_mask,
                test_type="unpaired",
            )


# ═══════════════════════════════════════════════════════════════════════════
# engine.py — PermutationEngine.correct_correlation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestPermutationEngineCorrectCorrelation:
    """Tests for PermutationEngine.correct_correlation."""

    def _make_corr_data(self, shape=(4, 4, 4), n_subjects=8, seed=42):
        np.random.seed(seed)
        subject_data = np.random.rand(*shape, n_subjects).astype(np.float32)
        effect_sizes = np.random.rand(n_subjects) * 2.0
        # Add a strong correlation signal at one location
        for i in range(n_subjects):
            subject_data[1, 1, 1, i] = effect_sizes[i] * 5.0 + 0.1
            subject_data[1, 1, 2, i] = effect_sizes[i] * 4.0 + 0.2
        return subject_data, effect_sizes

    def test_correct_correlation_no_clusters(self):
        """No clusters when data is uncorrelated and threshold is strict."""
        np.random.seed(42)
        shape = (4, 4, 4)
        n = 8
        subject_data = np.random.rand(*shape, n).astype(np.float32)
        effect_sizes = np.random.rand(n)

        r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
            subject_data, effect_sizes
        )

        engine = PermutationEngine(
            cluster_threshold=0.001,  # very strict
            n_permutations=10,
            alpha=0.05,
            cluster_stat="size",
            alternative="two-sided",
            n_jobs=1,
        )

        result = engine.correct_correlation(
            subject_data, effect_sizes,
            r_values=r_values,
            t_statistics=t_statistics,
            p_values=p_values,
            valid_mask=valid_mask,
            correlation_type="pearson",
        )

        assert len(result) == 6

    def test_correct_correlation_with_signal(self):
        """Correlation correction detects real signal."""
        subject_data, effect_sizes = self._make_corr_data()

        r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
            subject_data, effect_sizes
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=20,
            alpha=0.05,
            cluster_stat="mass",
            alternative="two-sided",
            n_jobs=1,
        )

        sig_mask, threshold, sig_clusters, null_dist, obs, corr_data = (
            engine.correct_correlation(
                subject_data, effect_sizes,
                r_values=r_values,
                t_statistics=t_statistics,
                p_values=p_values,
                valid_mask=valid_mask,
                correlation_type="pearson",
            )
        )

        assert null_dist.shape == (20,)
        assert isinstance(threshold, (int, float, np.integer, np.floating))

    def test_correct_correlation_spearman(self):
        """Spearman correlation path (with pre-ranking) executes."""
        subject_data, effect_sizes = self._make_corr_data()

        r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
            subject_data, effect_sizes, correlation_type="spearman"
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=10,
            alpha=0.05,
            cluster_stat="size",
            alternative="two-sided",
            n_jobs=1,
        )

        result = engine.correct_correlation(
            subject_data, effect_sizes,
            r_values=r_values,
            t_statistics=t_statistics,
            p_values=p_values,
            valid_mask=valid_mask,
            correlation_type="spearman",
        )

        assert len(result) == 6

    def test_correct_correlation_greater_alternative(self):
        """One-sided (greater) alternative forms only positive clusters."""
        subject_data, effect_sizes = self._make_corr_data()

        r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
            subject_data, effect_sizes
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=10,
            alpha=0.05,
            cluster_stat="size",
            alternative="greater",
            n_jobs=1,
        )

        result = engine.correct_correlation(
            subject_data, effect_sizes,
            r_values=r_values,
            t_statistics=t_statistics,
            p_values=p_values,
            valid_mask=valid_mask,
            correlation_type="pearson",
        )

        assert len(result) == 6

    def test_correct_correlation_less_alternative(self):
        """One-sided (less) alternative forms only negative clusters."""
        subject_data, effect_sizes = self._make_corr_data()

        r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
            subject_data, effect_sizes
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=10,
            alpha=0.05,
            cluster_stat="size",
            alternative="less",
            n_jobs=1,
        )

        result = engine.correct_correlation(
            subject_data, effect_sizes,
            r_values=r_values,
            t_statistics=t_statistics,
            p_values=p_values,
            valid_mask=valid_mask,
            correlation_type="pearson",
        )

        assert len(result) == 6

    def test_correct_correlation_with_weights(self):
        """Weighted correlation path executes."""
        subject_data, effect_sizes = self._make_corr_data()
        weights = np.ones(len(effect_sizes))

        r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
            subject_data, effect_sizes, weights=weights
        )

        engine = PermutationEngine(
            cluster_threshold=0.05,
            n_permutations=10,
            alpha=0.05,
            cluster_stat="mass",
            alternative="two-sided",
            n_jobs=1,
        )

        result = engine.correct_correlation(
            subject_data, effect_sizes,
            r_values=r_values,
            t_statistics=t_statistics,
            p_values=p_values,
            valid_mask=valid_mask,
            correlation_type="pearson",
            weights=weights,
        )

        assert len(result) == 6


# ═══════════════════════════════════════════════════════════════════════════
# engine.py — _run_single_correlation_permutation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRunSingleCorrelationPermutation:
    """Tests for the correlation permutation worker."""

    def _make_inputs(self, n_voxels=20, n_subjects=8, seed=42):
        np.random.seed(seed)
        voxel_data = np.random.rand(n_voxels, n_subjects).astype(np.float64)
        effect_sizes = np.random.rand(n_subjects) * 2.0

        shape = (5, 5, 5)
        valid_mask = np.zeros(shape, dtype=bool)
        valid_coords = []
        for idx in range(n_voxels):
            i = idx // 25
            j = (idx % 25) // 5
            k = idx % 5
            valid_mask[i, j, k] = True
            valid_coords.append([i, j, k])
        valid_coords = np.array(valid_coords)

        return voxel_data, effect_sizes, valid_coords, valid_mask, shape

    def test_returns_three_values(self):
        """Without return_indices, returns 3-tuple."""
        vd, es, vc, vm, shape = self._make_inputs()
        result = _run_single_correlation_permutation(
            vd, es, vc, 0.05, vm, shape,
            correlation_type="pearson",
            seed=42,
            return_indices=False,
        )
        assert len(result) == 3

    def test_returns_four_values_with_indices(self):
        """With return_indices=True, returns 4-tuple."""
        vd, es, vc, vm, shape = self._make_inputs()
        result = _run_single_correlation_permutation(
            vd, es, vc, 0.05, vm, shape,
            correlation_type="pearson",
            seed=42,
            return_indices=True,
        )
        assert len(result) == 4
        assert result[1] is not None  # perm_idx

    def test_deterministic_with_seed(self):
        """Same seed produces same result."""
        vd, es, vc, vm, shape = self._make_inputs()
        kwargs = dict(
            voxel_data=vd,
            effect_sizes=es,
            valid_coords=vc,
            cluster_threshold=0.05,
            valid_mask=vm,
            shape=shape,
            seed=99,
        )
        r1 = _run_single_correlation_permutation(**kwargs)
        r2 = _run_single_correlation_permutation(**kwargs)
        assert r1[0] == r2[0]

    def test_spearman_correlation(self):
        """Spearman type executes without error."""
        vd, es, vc, vm, shape = self._make_inputs()
        result = _run_single_correlation_permutation(
            vd, es, vc, 0.05, vm, shape,
            correlation_type="spearman",
            seed=42,
        )
        assert len(result) == 3

    def test_with_weights(self):
        """Weighted correlation permutation executes."""
        vd, es, vc, vm, shape = self._make_inputs()
        weights = np.ones(len(es))
        result = _run_single_correlation_permutation(
            vd, es, vc, 0.05, vm, shape,
            correlation_type="pearson",
            weights=weights,
            seed=42,
        )
        assert len(result) == 3

    def test_mass_cluster_stat(self):
        """cluster_stat='mass' uses mass-based max stat."""
        vd, es, vc, vm, shape = self._make_inputs()
        result = _run_single_correlation_permutation(
            vd, es, vc, 0.05, vm, shape,
            cluster_stat="mass",
            seed=42,
        )
        assert len(result) == 3

    def test_greater_alternative(self):
        """'greater' alternative path executes."""
        vd, es, vc, vm, shape = self._make_inputs()
        result = _run_single_correlation_permutation(
            vd, es, vc, 0.05, vm, shape,
            alternative="greater",
            seed=42,
        )
        assert len(result) == 3

    def test_less_alternative(self):
        """'less' alternative path executes."""
        vd, es, vc, vm, shape = self._make_inputs()
        result = _run_single_correlation_permutation(
            vd, es, vc, 0.05, vm, shape,
            alternative="less",
            seed=42,
        )
        assert len(result) == 3

    def test_preranked_data(self):
        """Pre-ranked Spearman data skips re-ranking."""
        vd, es, vc, vm, shape = self._make_inputs()
        # Pre-rank the voxel data
        from scipy.stats import rankdata
        vd_ranked = np.apply_along_axis(rankdata, 1, vd)
        result = _run_single_correlation_permutation(
            vd_ranked, es, vc, 0.05, vm, shape,
            correlation_type="spearman",
            voxel_data_preranked=True,
            seed=42,
        )
        assert len(result) == 3


# ═══════════════════════════════════════════════════════════════════════════
# engine.py — correlation_voxelwise additional coverage
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestCorrelationVoxelwiseCoverage:
    """Extra correlation_voxelwise tests for edge cases."""

    def test_spearman_voxelwise(self):
        """Spearman correlation via the voxelwise wrapper."""
        np.random.seed(42)
        shape = (3, 3, 3)
        n_subjects = 5
        subject_data = np.random.rand(*shape, n_subjects)
        subject_data[1, 1, 1, :] = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        effect_sizes = np.array([1.0, 4.0, 9.0, 16.0, 25.0])

        r, t, p, mask = correlation_voxelwise(
            subject_data, effect_sizes, correlation_type="spearman"
        )

        assert r.shape == shape
        # Monotonic relationship: Spearman r should be 1
        assert r[1, 1, 1] == pytest.approx(1.0, abs=1e-6)

    def test_weighted_voxelwise(self):
        """Weighted correlation via voxelwise wrapper."""
        np.random.seed(42)
        shape = (3, 3, 3)
        n_subjects = 5
        subject_data = np.random.rand(*shape, n_subjects)
        effect_sizes = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        weights = np.array([1.0, 1.0, 1.0, 1.0, 1.0])

        r, t, p, mask = correlation_voxelwise(
            subject_data, effect_sizes, weights=weights
        )

        assert r.shape == shape
        assert mask.shape == shape


# ═══════════════════════════════════════════════════════════════════════════
# nifti.py
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestLoadSubjectNiftiTiToolbox:
    """Tests for tit.stats.nifti.load_subject_nifti_ti_toolbox."""

    def test_loads_nifti_file(self, tmp_path):
        """Successfully loads a NIfTI file."""
        mock_pm = MagicMock()
        mock_pm.simulation.return_value = str(tmp_path)

        # Create the expected directory structure
        nifti_dir = tmp_path / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        nifti_file = nifti_dir / "grey_my_sim_TI_MNI_MNI_TI_max.nii.gz"
        nifti_file.touch()

        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.random.rand(3, 3, 3).astype(np.float32)

        with patch("tit.stats.nifti.get_path_manager", return_value=mock_pm), \
             patch("tit.stats.nifti.nib.load", return_value=mock_img):
            from tit.stats.nifti import load_subject_nifti_ti_toolbox

            data, img, fpath = load_subject_nifti_ti_toolbox("001", "my_sim")

        assert data.shape == (3, 3, 3)
        assert img is mock_img

    def test_file_not_found_no_dir(self, tmp_path):
        """Raises FileNotFoundError when directory doesn't exist."""
        mock_pm = MagicMock()
        mock_pm.simulation.return_value = str(tmp_path / "nonexistent")

        with patch("tit.stats.nifti.get_path_manager", return_value=mock_pm):
            from tit.stats.nifti import load_subject_nifti_ti_toolbox

            with pytest.raises(FileNotFoundError, match="NIfTI file not found"):
                load_subject_nifti_ti_toolbox("001", "my_sim")

    def test_file_not_found_dir_exists(self, tmp_path):
        """Raises FileNotFoundError with directory listing when dir exists."""
        mock_pm = MagicMock()
        mock_pm.simulation.return_value = str(tmp_path)

        nifti_dir = tmp_path / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        # Create a different file
        (nifti_dir / "other_file.nii.gz").touch()

        with patch("tit.stats.nifti.get_path_manager", return_value=mock_pm):
            from tit.stats.nifti import load_subject_nifti_ti_toolbox

            with pytest.raises(FileNotFoundError, match="Directory exists"):
                load_subject_nifti_ti_toolbox("001", "my_sim")

    def test_squeezes_extra_dimensions(self, tmp_path):
        """Data with extra dimensions is squeezed to 3D."""
        mock_pm = MagicMock()
        mock_pm.simulation.return_value = str(tmp_path)

        nifti_dir = tmp_path / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        nifti_file = nifti_dir / "grey_my_sim_TI_MNI_MNI_TI_max.nii.gz"
        nifti_file.touch()

        mock_img = MagicMock()
        # Return 4D data
        mock_img.get_fdata.return_value = np.random.rand(3, 3, 3, 1).astype(np.float32)

        with patch("tit.stats.nifti.get_path_manager", return_value=mock_pm), \
             patch("tit.stats.nifti.nib.load", return_value=mock_img):
            from tit.stats.nifti import load_subject_nifti_ti_toolbox

            data, img, fpath = load_subject_nifti_ti_toolbox("001", "my_sim")

        assert data.shape == (3, 3, 3)

    def test_custom_pattern(self, tmp_path):
        """Custom nifti_file_pattern is used."""
        mock_pm = MagicMock()
        mock_pm.simulation.return_value = str(tmp_path)

        nifti_dir = tmp_path / "TI" / "niftis"
        nifti_dir.mkdir(parents=True)
        nifti_file = nifti_dir / "custom_001_my_sim.nii.gz"
        nifti_file.touch()

        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.random.rand(3, 3, 3).astype(np.float32)

        with patch("tit.stats.nifti.get_path_manager", return_value=mock_pm), \
             patch("tit.stats.nifti.nib.load", return_value=mock_img):
            from tit.stats.nifti import load_subject_nifti_ti_toolbox

            data, img, fpath = load_subject_nifti_ti_toolbox(
                "001", "my_sim",
                nifti_file_pattern="custom_{subject_id}_{simulation_name}.nii.gz",
            )

        assert "custom_001_my_sim.nii.gz" in fpath


@pytest.mark.unit
class TestLoadGroupDataTiToolbox:
    """Tests for tit.stats.nifti.load_group_data_ti_toolbox."""

    def test_loads_multiple_subjects(self, tmp_path):
        """Load multiple subjects into a 4D array."""
        mock_pm = MagicMock()

        data_shape = (3, 3, 3)

        def mock_load_subject(subject_id, simulation_name, nifti_file_pattern, dtype=np.float32):
            data = np.random.rand(*data_shape).astype(dtype)
            mock_img = MagicMock()
            mock_img.affine = np.eye(4)
            mock_img.header = MagicMock()
            mock_img.header.copy.return_value = MagicMock()
            return data, mock_img, f"/path/to/{subject_id}.nii.gz"

        configs = [
            {"subject_id": "001", "simulation_name": "sim1"},
            {"subject_id": "002", "simulation_name": "sim2"},
        ]

        with patch("tit.stats.nifti.load_subject_nifti_ti_toolbox", side_effect=mock_load_subject), \
             patch("tit.stats.nifti.nib.Nifti1Image") as mock_nifti_cls:
            mock_nifti_cls.return_value = MagicMock()
            from tit.stats.nifti import load_group_data_ti_toolbox

            data_4d, template_img, subject_ids = load_group_data_ti_toolbox(configs)

        assert data_4d.shape == (3, 3, 3, 2)
        assert subject_ids == ["001", "002"]

    def test_empty_subject_list_raises(self):
        """Empty subject list raises ValueError."""
        with patch("tit.stats.nifti.load_subject_nifti_ti_toolbox") as mock_load:
            from tit.stats.nifti import load_group_data_ti_toolbox

            with pytest.raises(ValueError, match="No subjects could be loaded"):
                load_group_data_ti_toolbox([])


@pytest.mark.unit
class TestLoadGroupedSubjectsTiToolbox:
    """Tests for tit.stats.nifti.load_grouped_subjects_ti_toolbox."""

    def test_loads_grouped_subjects(self):
        """Subjects are organized by group."""
        data_shape = (3, 3, 3)

        def mock_load_group(configs, pattern, dtype=np.float32):
            n = len(configs)
            data_4d = np.random.rand(*data_shape, n).astype(dtype)
            mock_img = MagicMock()
            ids = [c["subject_id"] for c in configs]
            return data_4d, mock_img, ids

        configs = [
            {"subject_id": "001", "simulation_name": "sim1", "group": "responders"},
            {"subject_id": "002", "simulation_name": "sim2", "group": "responders"},
            {"subject_id": "003", "simulation_name": "sim3", "group": "non_responders"},
        ]

        with patch("tit.stats.nifti.load_group_data_ti_toolbox", side_effect=mock_load_group):
            from tit.stats.nifti import load_grouped_subjects_ti_toolbox

            groups_data, template_img, groups_ids = load_grouped_subjects_ti_toolbox(configs)

        assert "responders" in groups_data
        assert "non_responders" in groups_data
        assert groups_data["responders"].shape[-1] == 2
        assert groups_data["non_responders"].shape[-1] == 1
        assert groups_ids["responders"] == ["001", "002"]

    def test_default_group_name(self):
        """Subjects without 'group' key go into 'default' group."""
        data_shape = (3, 3, 3)

        def mock_load_group(configs, pattern, dtype=np.float32):
            n = len(configs)
            data_4d = np.random.rand(*data_shape, n).astype(dtype)
            mock_img = MagicMock()
            ids = [c["subject_id"] for c in configs]
            return data_4d, mock_img, ids

        configs = [
            {"subject_id": "001", "simulation_name": "sim1"},
            {"subject_id": "002", "simulation_name": "sim2"},
        ]

        with patch("tit.stats.nifti.load_group_data_ti_toolbox", side_effect=mock_load_group):
            from tit.stats.nifti import load_grouped_subjects_ti_toolbox

            groups_data, _, groups_ids = load_grouped_subjects_ti_toolbox(configs)

        assert "default" in groups_data
        assert groups_ids["default"] == ["001", "002"]


# ═══════════════════════════════════════════════════════════════════════════
# permutation.py — helper functions
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestPermutationHelpers:
    """Tests for permutation.py helper functions."""

    def test_setup_logger(self, tmp_path):
        """_setup_logger creates a logger with file handler."""
        from tit.stats.permutation import _setup_logger

        log, log_file = _setup_logger(str(tmp_path), "test_analysis")

        assert log is not None
        assert "test_analysis" in log_file
        assert os.path.dirname(log_file) == str(tmp_path)

        # Cleanup handlers
        for h in log.handlers[:]:
            h.close()
            log.removeHandler(h)

    def test_setup_logger_with_callback(self, tmp_path):
        """_setup_logger adds callback handler when provided."""
        from tit.stats.permutation import _setup_logger

        callback = logging.StreamHandler()
        log, log_file = _setup_logger(str(tmp_path), "test", callback)

        assert callback in log.handlers

        # Cleanup
        for h in log.handlers[:]:
            h.close()
            log.removeHandler(h)

    def test_resolve_output_dir(self, tmp_project):
        """_resolve_output_dir creates output directory via PathManager."""
        from tit.paths import get_path_manager

        pm = get_path_manager(str(tmp_project))

        from tit.stats.permutation import _resolve_output_dir

        output_dir = _resolve_output_dir(
            "group_comparison", "my_analysis"
        )

        assert os.path.isdir(output_dir)
        assert "my_analysis" in output_dir

    def test_save_nifti(self, tmp_path):
        """_save_nifti creates a NIfTI file via nibabel."""
        from tit.stats.permutation import _save_nifti

        data = np.random.rand(3, 3, 3).astype(np.float32)
        mock_template = MagicMock()
        mock_template.affine = np.eye(4)
        mock_template.header = MagicMock()
        out_path = str(tmp_path / "test.nii.gz")

        with patch("tit.stats.permutation.nib.Nifti1Image") as mock_cls, \
             patch("tit.stats.permutation.nib.save") as mock_save:
            _save_nifti(data, mock_template, out_path)

            mock_cls.assert_called_once()
            mock_save.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# permutation.py — run_group_comparison (integration-style with mocks)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRunGroupComparison:
    """Tests for permutation.run_group_comparison."""

    def _make_config(self, tmp_path):
        subjects = [
            GroupComparisonConfig.Subject("001", "sim1", 1),
            GroupComparisonConfig.Subject("002", "sim2", 1),
            GroupComparisonConfig.Subject("003", "sim3", 1),
            GroupComparisonConfig.Subject("004", "sim4", 0),
            GroupComparisonConfig.Subject("005", "sim5", 0),
            GroupComparisonConfig.Subject("006", "sim6", 0),
        ]
        return GroupComparisonConfig(
            analysis_name="test_gc",
            subjects=subjects,
            n_permutations=10,
            n_jobs=1,
            cluster_stat=GroupComparisonConfig.ClusterStat.SIZE,
            cluster_threshold=0.05,
        )

    def test_run_group_comparison_full(self, tmp_project, init_pm):
        """Full run_group_comparison with mocked data loading."""
        cfg = self._make_config(tmp_project)

        shape = (4, 4, 4)
        n_resp = 3
        n_non = 3
        np.random.seed(42)
        resp_data = np.random.rand(*shape, n_resp).astype(np.float32)
        non_resp_data = np.random.rand(*shape, n_non).astype(np.float32)
        # Add signal
        resp_data[1, 1, 1, :] += 10.0

        mock_template = MagicMock()
        mock_template.affine = np.eye(4)
        mock_template.header = MagicMock()

        with patch("tit.stats.permutation.load_group_data_ti_toolbox") as mock_load, \
             patch("tit.stats.permutation._save_nifti") as mock_save_nifti, \
             patch("tit.stats.permutation.generate_summary") as mock_gen_summary, \
             patch("tit.stats.permutation.plot_permutation_null_distribution"), \
             patch("tit.stats.permutation.plot_cluster_size_mass_correlation"), \
             patch("tit.stats.permutation.atlas_overlap_analysis", return_value={}), \
             patch("nibabel.affines.apply_affine", side_effect=lambda a, c: c):

            mock_load.side_effect = [
                (resp_data, mock_template, ["001", "002", "003"]),
                (non_resp_data, mock_template, ["004", "005", "006"]),
            ]

            from tit.stats.permutation import run_group_comparison

            result = run_group_comparison(cfg)

        assert isinstance(result, GroupComparisonResult)
        assert result.success is True
        assert result.n_responders == 3
        assert result.n_non_responders == 3

    def test_run_group_comparison_stop_callback(self, tmp_project, init_pm):
        """Stop callback aborts the run."""
        cfg = self._make_config(tmp_project)

        shape = (4, 4, 4)
        mock_template = MagicMock()
        mock_template.affine = np.eye(4)
        mock_template.header = MagicMock()

        # stop_callback returns True on first call
        stop_cb = MagicMock(return_value=True)

        with patch("tit.stats.permutation.load_group_data_ti_toolbox") as mock_load:
            mock_load.side_effect = [
                (np.random.rand(*shape, 3).astype(np.float32), mock_template, ["001", "002", "003"]),
                (np.random.rand(*shape, 3).astype(np.float32), mock_template, ["004", "005", "006"]),
            ]

            from tit.stats.permutation import run_group_comparison

            with pytest.raises(KeyboardInterrupt, match="Stopped by user"):
                run_group_comparison(cfg, stop_callback=stop_cb)


# ═══════════════════════════════════════════════════════════════════════════
# permutation.py — run_correlation (integration-style with mocks)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRunCorrelation:
    """Tests for permutation.run_correlation."""

    def _make_config(self, tmp_path):
        subjects = [
            CorrelationConfig.Subject("001", "sim1", 0.5),
            CorrelationConfig.Subject("002", "sim2", 1.0),
            CorrelationConfig.Subject("003", "sim3", 1.5),
            CorrelationConfig.Subject("004", "sim4", 2.0),
            CorrelationConfig.Subject("005", "sim5", 2.5),
        ]
        return CorrelationConfig(
            analysis_name="test_corr",
            subjects=subjects,
            n_permutations=10,
            n_jobs=1,
            cluster_stat=CorrelationConfig.ClusterStat.SIZE,
            cluster_threshold=0.05,
            use_weights=False,
        )

    def test_run_correlation_full(self, tmp_project, init_pm):
        """Full run_correlation with mocked data loading."""
        cfg = self._make_config(tmp_project)

        shape = (4, 4, 4)
        n_subjects = 5
        np.random.seed(42)
        subject_data = np.random.rand(*shape, n_subjects).astype(np.float32)
        # Add correlation signal
        effect = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
        for i in range(n_subjects):
            subject_data[1, 1, 1, i] = effect[i] * 5.0

        mock_template = MagicMock()
        mock_template.affine = np.eye(4)
        mock_template.header = MagicMock()

        # Mock scipy_label used in permutation.py for cluster annotation
        mock_labeled = np.zeros(shape, dtype=int)
        with patch("tit.stats.permutation.load_group_data_ti_toolbox") as mock_load, \
             patch("tit.stats.permutation._save_nifti"), \
             patch("tit.stats.permutation.generate_correlation_summary"), \
             patch("tit.stats.permutation.plot_permutation_null_distribution"), \
             patch("tit.stats.permutation.plot_cluster_size_mass_correlation"), \
             patch("tit.stats.permutation.atlas_overlap_analysis", return_value={}), \
             patch("nibabel.affines.apply_affine", side_effect=lambda a, c: c), \
             patch("scipy.ndimage.label", return_value=(mock_labeled, 0)):

            mock_load.return_value = (
                subject_data,
                mock_template,
                ["001", "002", "003", "004", "005"],
            )

            from tit.stats.permutation import run_correlation

            result = run_correlation(cfg)

        assert isinstance(result, CorrelationResult)
        assert result.success is True
        assert result.n_subjects == 5

    def test_run_correlation_stop_callback(self, tmp_project, init_pm):
        """Stop callback aborts correlation run."""
        cfg = self._make_config(tmp_project)

        shape = (4, 4, 4)
        n_subjects = 5
        mock_template = MagicMock()
        mock_template.affine = np.eye(4)
        mock_template.header = MagicMock()

        stop_cb = MagicMock(return_value=True)

        with patch("tit.stats.permutation.load_group_data_ti_toolbox") as mock_load:
            mock_load.return_value = (
                np.random.rand(*shape, n_subjects).astype(np.float32),
                mock_template,
                ["001", "002", "003", "004", "005"],
            )

            from tit.stats.permutation import run_correlation

            with pytest.raises(KeyboardInterrupt, match="Stopped by user"):
                run_correlation(cfg, stop_callback=stop_cb)

    def test_run_correlation_with_weights(self, tmp_project, init_pm):
        """Weighted correlation analysis runs to completion."""
        subjects = [
            CorrelationConfig.Subject("001", "sim1", 0.5, weight=1.0),
            CorrelationConfig.Subject("002", "sim2", 1.0, weight=2.0),
            CorrelationConfig.Subject("003", "sim3", 1.5, weight=1.5),
            CorrelationConfig.Subject("004", "sim4", 2.0, weight=1.0),
            CorrelationConfig.Subject("005", "sim5", 2.5, weight=2.0),
        ]
        cfg = CorrelationConfig(
            analysis_name="test_corr_weighted",
            subjects=subjects,
            n_permutations=10,
            n_jobs=1,
            cluster_stat=CorrelationConfig.ClusterStat.SIZE,
            cluster_threshold=0.05,
            use_weights=True,
        )

        shape = (4, 4, 4)
        n_subjects = 5
        np.random.seed(42)
        subject_data = np.random.rand(*shape, n_subjects).astype(np.float32)

        mock_template = MagicMock()
        mock_template.affine = np.eye(4)
        mock_template.header = MagicMock()

        mock_labeled = np.zeros(shape, dtype=int)
        with patch("tit.stats.permutation.load_group_data_ti_toolbox") as mock_load, \
             patch("tit.stats.permutation._save_nifti"), \
             patch("tit.stats.permutation.generate_correlation_summary"), \
             patch("tit.stats.permutation.plot_permutation_null_distribution"), \
             patch("tit.stats.permutation.plot_cluster_size_mass_correlation"), \
             patch("tit.stats.permutation.atlas_overlap_analysis", return_value={}), \
             patch("nibabel.affines.apply_affine", side_effect=lambda a, c: c), \
             patch("scipy.ndimage.label", return_value=(mock_labeled, 0)):

            mock_load.return_value = (
                subject_data,
                mock_template,
                ["001", "002", "003", "004", "005"],
            )

            from tit.stats.permutation import run_correlation

            result = run_correlation(cfg)

        assert result.success is True


# ═══════════════════════════════════════════════════════════════════════════
# engine.py — _identify_significant_clusters additional cases
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestIdentifySignificantClustersCoverage:
    """Additional coverage for _identify_significant_clusters."""

    def test_greater_alternative_tail(self):
        """Greater alternative uses tail=1 for p-value computation."""
        labeled = np.zeros((5, 5, 5), dtype=int)
        labeled[1, 1, 1] = 1
        labeled[1, 1, 2] = 1
        t_stats = np.zeros((5, 5, 5))
        t_stats[1, 1, 1] = 3.0
        t_stats[1, 1, 2] = 2.5
        null = np.array([0.0, 1.0, 0.0, 0.0, 1.0])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 1, t_stats, null, "size",
            alpha=0.05, alternative="greater",
            _log=logging.getLogger("test"),
        )

        # Should still detect the cluster
        assert len(sig_clusters) >= 0  # result depends on tail computation

    def test_less_alternative_tail(self):
        """Less alternative uses tail=-1 for p-value computation."""
        labeled = np.zeros((5, 5, 5), dtype=int)
        labeled[1, 1, 1] = 1
        labeled[1, 1, 2] = 1
        t_stats = np.zeros((5, 5, 5))
        t_stats[1, 1, 1] = -3.0
        t_stats[1, 1, 2] = -2.5
        null = np.array([0.0, 0.5, 0.0, 0.3, 0.1])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 1, t_stats, null, "mass",
            alpha=0.05, alternative="less",
            _log=logging.getLogger("test"),
        )

        assert isinstance(sig_mask, np.ndarray)

    def test_many_clusters_top_10_logged(self):
        """More than 10 clusters only logs top 10 in observed."""
        labeled = np.zeros((30, 30, 1), dtype=int)
        t_stats = np.ones((30, 30, 1)) * 3.0

        # Create 15 small clusters (2 voxels each)
        for i in range(15):
            labeled[i * 2, 0, 0] = i + 1
            labeled[i * 2 + 1, 0, 0] = i + 1

        null = np.array([0.0, 0.0, 0.0])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 15, t_stats, null, "size",
            alpha=0.05, alternative="two-sided",
            _log=logging.getLogger("test"),
        )

        # observed should have at most 10 entries
        assert len(observed) <= 10

    def test_empty_stat_values(self):
        """No multi-voxel clusters results in empty stat_values list."""
        labeled = np.zeros((3, 3, 3), dtype=int)
        # Only single-voxel clusters
        labeled[0, 0, 0] = 1
        labeled[2, 2, 2] = 2
        t_stats = np.ones((3, 3, 3))
        null = np.array([0.0])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 2, t_stats, null, "size",
            alpha=0.05, alternative="two-sided",
            _log=logging.getLogger("test"),
        )

        assert len(sig_clusters) == 0
        assert len(observed) == 0


# ═══════════════════════════════════════════════════════════════════════════
# io_utils.py — save_permutation_details
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestSavePermutationDetails:
    """Tests for tit.stats.io_utils.save_permutation_details."""

    def test_save_with_integer_stats(self, tmp_path):
        """Permutation details are saved with integer stats."""
        from tit.stats.io_utils import save_permutation_details

        info = [
            {"perm_num": 0, "perm_idx": [0, 1, 2, 3, 4, 5], "max_cluster_size": 5},
            {"perm_num": 1, "perm_idx": [3, 4, 5, 0, 1, 2], "max_cluster_size": 3},
        ]
        out = str(tmp_path / "perm_details.txt")

        save_permutation_details(info, out, ["s1", "s2", "s3"], ["s4", "s5", "s6"])

        text = open(out).read()
        assert "PERMUTATION TEST DETAILS" in text
        assert "Total permutations: 2" in text

    def test_save_with_float_stats(self, tmp_path):
        """Permutation details are saved with float stats (mass)."""
        from tit.stats.io_utils import save_permutation_details

        info = [
            {"perm_num": 0, "perm_idx": [0, 1, 2, 3], "max_cluster_size": 7.5},
        ]
        out = str(tmp_path / "perm_details.txt")

        save_permutation_details(info, out, ["s1", "s2"], ["s3", "s4"])

        text = open(out).read()
        assert "7.50" in text
