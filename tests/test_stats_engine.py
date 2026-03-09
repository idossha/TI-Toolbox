"""Tests for tit/stats/engine.py — core statistical computation engine.

Covers:
- pval_from_histogram: p-value computation from null distributions
- correlation / correlation_voxelwise: Pearson, Spearman, weighted
- ttest_ind / ttest_rel / ttest_voxelwise: vectorised t-tests
- _run_single_permutation: single permutation worker
- _identify_significant_clusters: cluster identification
- cluster_analysis: connected-component analysis
"""

import importlib
import logging
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Restore real scipy and reload engine so its module-level bindings
# (sp_stats, label, ndimage_sum, rankdata) point to real implementations.
# conftest.py mocks scipy before we get here, but engine.py needs real math.
# ---------------------------------------------------------------------------
_scipy_keys = [k for k in list(sys.modules) if k == "scipy" or k.startswith("scipy.")]
_saved = {k: sys.modules.pop(k) for k in _scipy_keys}

import scipy  # noqa: E402
import scipy.ndimage  # noqa: E402
import scipy.stats  # noqa: E402

# Keep real scipy.optimize too if available, else mock
try:
    import scipy.optimize  # noqa: E402
except ImportError:
    sys.modules["scipy.optimize"] = MagicMock()

# Spatial sub-packages are not needed by engine — mock them
sys.modules.setdefault("scipy.spatial", MagicMock())
sys.modules.setdefault("scipy.spatial.transform", MagicMock())

# Force-reload engine so its top-level from-imports bind to real scipy
import tit.stats.engine  # noqa: E402

importlib.reload(tit.stats.engine)

from tit.stats.engine import (  # noqa: E402
    _identify_significant_clusters,
    _run_single_permutation,
    cluster_analysis,
    correlation,
    correlation_voxelwise,
    pval_from_histogram,
    ttest_ind,
    ttest_rel,
    ttest_voxelwise,
)


# ─── pval_from_histogram ─────────────────────────────────────────────────


class TestPvalFromHistogram:
    """Tests for MNE-style p-value computation."""

    @pytest.mark.unit
    def test_two_tailed_extreme_value(self):
        """Observed stat larger than all nulls yields p ~ 0."""
        null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        observed = np.array([100.0])
        p = pval_from_histogram(observed, null, tail=0)
        assert p[0] == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.unit
    def test_two_tailed_small_value(self):
        """Observed stat at zero — all nulls have |null| >= 0, so p = 1."""
        null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        observed = np.array([0.0])
        p = pval_from_histogram(observed, null, tail=0)
        assert p[0] == pytest.approx(1.0)

    @pytest.mark.unit
    def test_right_tail(self):
        """Right-tailed: fraction of null >= observed."""
        null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        observed = np.array([3.0])
        p = pval_from_histogram(observed, null, tail=1)
        # 3, 4, 5 are >= 3 => 3/5 = 0.6
        assert p[0] == pytest.approx(0.6)

    @pytest.mark.unit
    def test_left_tail(self):
        """Left-tailed: fraction of null <= observed."""
        null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        observed = np.array([2.0])
        p = pval_from_histogram(observed, null, tail=-1)
        # 1, 2 are <= 2 => 2/5 = 0.4
        assert p[0] == pytest.approx(0.4)

    @pytest.mark.unit
    def test_multiple_observed(self):
        """Multiple observed stats produce correct per-element p-values."""
        null = np.arange(1.0, 11.0)  # 1..10
        observed = np.array([5.0, 10.0])
        p = pval_from_histogram(observed, null, tail=1)
        # >= 5: {5,6,7,8,9,10} = 6/10
        # >= 10: {10} = 1/10
        assert p[0] == pytest.approx(0.6)
        assert p[1] == pytest.approx(0.1)

    @pytest.mark.unit
    def test_scalar_input(self):
        """Scalar observed is promoted to 1-d array."""
        null = np.array([1.0, 2.0, 3.0])
        p = pval_from_histogram(3.0, null, tail=1)
        assert p.shape == (1,)
        assert p[0] == pytest.approx(1 / 3)


# ─── correlation ──────────────────────────────────────────────────────────


class TestCorrelation:
    """Tests for vectorised correlation computation."""

    @pytest.mark.unit
    def test_perfect_positive_pearson(self):
        """Perfect positive linear relationship gives r=1."""
        x = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])  # 1 voxel, 5 subjects
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        r, t, p = correlation(x, y, correlation_type="pearson")
        assert r[0] == pytest.approx(1.0, abs=1e-10)
        assert p[0] < 0.01

    @pytest.mark.unit
    def test_perfect_negative_pearson(self):
        """Perfect negative linear relationship gives r=-1."""
        x = np.array([[5.0, 4.0, 3.0, 2.0, 1.0]])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        r, t, p = correlation(x, y, correlation_type="pearson")
        assert r[0] == pytest.approx(-1.0, abs=1e-10)

    @pytest.mark.unit
    def test_zero_correlation(self):
        """Uncorrelated data produces r near 0."""
        np.random.seed(42)
        n = 100
        x = np.random.randn(1, n)
        y = np.random.randn(n)
        r, t, p = correlation(x, y, correlation_type="pearson")
        assert abs(r[0]) < 0.3  # with 100 samples, should be near 0

    @pytest.mark.unit
    def test_spearman_monotonic(self):
        """Spearman correlation detects monotonic (non-linear) relationships."""
        x = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
        y = np.array([1.0, 4.0, 9.0, 16.0, 25.0])  # y = x^2, monotonic
        r, t, p = correlation(x, y, correlation_type="spearman")
        assert r[0] == pytest.approx(1.0, abs=1e-10)

    @pytest.mark.unit
    def test_multiple_voxels(self):
        """Multiple voxels produce correct independent r-values."""
        x = np.array([
            [1.0, 2.0, 3.0, 4.0, 5.0],  # perfect positive
            [5.0, 4.0, 3.0, 2.0, 1.0],  # perfect negative
        ])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        r, t, p = correlation(x, y, correlation_type="pearson")
        assert r[0] == pytest.approx(1.0, abs=1e-10)
        assert r[1] == pytest.approx(-1.0, abs=1e-10)

    @pytest.mark.unit
    def test_weighted_correlation(self):
        """Weighted correlation uses weights in computation."""
        x = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        weights = np.array([1.0, 1.0, 1.0, 1.0, 1.0])  # uniform weights
        r_w, _, _ = correlation(x, y, weights=weights)
        r_u, _, _ = correlation(x, y)
        # Uniform weights should give same result as unweighted
        assert r_w[0] == pytest.approx(r_u[0], abs=1e-6)

    @pytest.mark.unit
    def test_constant_voxel_gives_zero_r(self):
        """A constant voxel (zero std) produces r=0."""
        x = np.array([[3.0, 3.0, 3.0, 3.0, 3.0]])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        r, t, p = correlation(x, y, correlation_type="pearson")
        assert r[0] == pytest.approx(0.0, abs=1e-10)


# ─── correlation_voxelwise ────────────────────────────────────────────────


class TestCorrelationVoxelwise:
    """Tests for voxelwise correlation wrapper."""

    @pytest.mark.unit
    def test_basic_voxelwise_correlation(self):
        """3D voxelwise correlation produces correct output shapes."""
        np.random.seed(42)
        shape = (3, 3, 3)
        n_subjects = 5
        subject_data = np.random.rand(*shape, n_subjects)
        # Make one voxel have a strong correlation
        subject_data[1, 1, 1, :] = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        effect_sizes = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        r, t, p, mask = correlation_voxelwise(subject_data, effect_sizes)
        assert r.shape == shape
        assert t.shape == shape
        assert p.shape == shape
        assert mask.shape == shape
        # The voxel we rigged should have high r
        assert r[1, 1, 1] == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.unit
    def test_mismatched_subjects_raises(self):
        """Mismatched effect_sizes length raises ValueError."""
        data = np.random.rand(2, 2, 2, 5)
        with pytest.raises(ValueError, match="effect_sizes length"):
            correlation_voxelwise(data, np.array([1.0, 2.0, 3.0]))

    @pytest.mark.unit
    def test_too_few_subjects_raises(self):
        """Fewer than 3 subjects raises ValueError."""
        data = np.random.rand(2, 2, 2, 2)
        with pytest.raises(ValueError, match="Need >= 3 subjects"):
            correlation_voxelwise(data, np.array([1.0, 2.0]))

    @pytest.mark.unit
    def test_mismatched_weights_raises(self):
        """Mismatched weights length raises ValueError."""
        data = np.random.rand(2, 2, 2, 5)
        effect = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        with pytest.raises(ValueError, match="weights length"):
            correlation_voxelwise(
                data, effect, weights=np.array([1.0, 1.0, 1.0])
            )


# ─── ttest_ind ────────────────────────────────────────────────────────────


class TestTtestInd:
    """Tests for vectorised independent-samples t-test."""

    @pytest.mark.unit
    def test_identical_groups_t_zero(self):
        """Identical groups produce t=0."""
        # 2 voxels, 6 subjects total: 3 resp + 3 non-resp, all identical
        data = np.ones((2, 6))
        t, p = ttest_ind(data, n_resp=3, n_non_resp=3)
        assert t[0] == pytest.approx(0.0, abs=1e-10)
        assert t[1] == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.unit
    def test_separated_groups(self):
        """Well-separated groups produce large |t| and small p."""
        data = np.array([[10.0, 11.0, 12.0, 0.0, 1.0, 2.0]])
        t, p = ttest_ind(data, n_resp=3, n_non_resp=3)
        assert t[0] > 0  # responders mean > non-responders mean
        assert p[0] < 0.05

    @pytest.mark.unit
    def test_alternative_greater(self):
        """One-sided 'greater' test returns correct p-value."""
        data = np.array([[10.0, 11.0, 12.0, 0.0, 1.0, 2.0]])
        _, p_two = ttest_ind(data, n_resp=3, n_non_resp=3, alternative="two-sided")
        _, p_gt = ttest_ind(data, n_resp=3, n_non_resp=3, alternative="greater")
        # One-sided p should be half of two-sided for positive t
        assert p_gt[0] == pytest.approx(p_two[0] / 2, abs=1e-10)

    @pytest.mark.unit
    def test_alternative_less(self):
        """One-sided 'less' test when resp < non_resp."""
        data = np.array([[0.0, 1.0, 2.0, 10.0, 11.0, 12.0]])
        t, p = ttest_ind(data, n_resp=3, n_non_resp=3, alternative="less")
        assert t[0] < 0
        assert p[0] < 0.05

    @pytest.mark.unit
    def test_invalid_alternative_raises(self):
        """Invalid alternative raises ValueError."""
        data = np.array([[1.0, 2.0, 3.0, 4.0]])
        with pytest.raises(ValueError, match="alternative must be"):
            ttest_ind(data, n_resp=2, n_non_resp=2, alternative="bogus")


# ─── ttest_rel ────────────────────────────────────────────────────────────


class TestTtestRel:
    """Tests for vectorised paired-samples t-test."""

    @pytest.mark.unit
    def test_no_difference(self):
        """Identical paired samples produce t=0."""
        data = np.array([[5.0, 5.0, 5.0, 5.0, 5.0, 5.0]])
        t, p = ttest_rel(data, n_resp=3)
        assert t[0] == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.unit
    def test_varying_difference(self):
        """Varying paired difference produces significant t."""
        # Pairs: (10,1), (12,2), (14,3) → diffs = [9, 10, 11]
        data = np.array([[10.0, 12.0, 14.0, 1.0, 2.0, 3.0]])
        t, p = ttest_rel(data, n_resp=3)
        assert t[0] > 0
        assert p[0] < 0.05

    @pytest.mark.unit
    def test_invalid_alternative_raises(self):
        """Invalid alternative raises ValueError."""
        data = np.array([[1.0, 2.0, 3.0, 4.0]])
        with pytest.raises(ValueError, match="alternative must be"):
            ttest_rel(data, n_resp=2, alternative="bogus")

    @pytest.mark.unit
    def test_alternative_greater(self):
        """One-sided 'greater' paired test."""
        data = np.array([[10.0, 12.0, 14.0, 1.0, 2.0, 3.0]])
        _, p_two = ttest_rel(data, n_resp=3, alternative="two-sided")
        _, p_gt = ttest_rel(data, n_resp=3, alternative="greater")
        assert p_gt[0] == pytest.approx(p_two[0] / 2, abs=1e-10)


# ─── ttest_voxelwise ─────────────────────────────────────────────────────


class TestTtestVoxelwise:
    """Tests for the voxelwise t-test wrapper."""

    @pytest.mark.unit
    def test_unpaired_output_shapes(self):
        """Unpaired voxelwise t-test returns correct shapes."""
        shape = (3, 3, 3)
        resp = np.random.rand(*shape, 4) + 5.0  # shift up
        non_resp = np.random.rand(*shape, 4)
        p, t, mask = ttest_voxelwise(resp, non_resp, test_type="unpaired")
        assert p.shape == shape
        assert t.shape == shape
        assert mask.shape == shape

    @pytest.mark.unit
    def test_paired_output_shapes(self):
        """Paired voxelwise t-test returns correct shapes."""
        shape = (2, 2, 2)
        resp = np.random.rand(*shape, 3) + 10.0
        non_resp = np.random.rand(*shape, 3)
        p, t, mask = ttest_voxelwise(resp, non_resp, test_type="paired")
        assert p.shape == shape
        assert t.shape == shape

    @pytest.mark.unit
    def test_paired_mismatched_sizes_raises(self):
        """Paired test with unequal sample sizes raises ValueError."""
        resp = np.random.rand(2, 2, 2, 3)
        non_resp = np.random.rand(2, 2, 2, 4)
        with pytest.raises(ValueError, match="equal sample sizes"):
            ttest_voxelwise(resp, non_resp, test_type="paired")

    @pytest.mark.unit
    def test_invalid_test_type_raises(self):
        """Invalid test_type raises ValueError."""
        resp = np.random.rand(2, 2, 2, 3)
        non_resp = np.random.rand(2, 2, 2, 3)
        with pytest.raises(ValueError, match="test_type must be"):
            ttest_voxelwise(resp, non_resp, test_type="invalid")

    @pytest.mark.unit
    def test_significant_voxel_detected(self):
        """A voxel with large group difference has small p-value."""
        shape = (3, 3, 3)
        np.random.seed(123)
        resp = np.random.rand(*shape, 5) * 0.1
        non_resp = np.random.rand(*shape, 5) * 0.1
        # Make one voxel strongly different
        resp[1, 1, 1, :] = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
        non_resp[1, 1, 1, :] = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        p, t, mask = ttest_voxelwise(resp, non_resp, test_type="unpaired")
        assert p[1, 1, 1] < 0.001
        assert t[1, 1, 1] > 0


# ─── _run_single_permutation ─────────────────────────────────────────────


class TestRunSinglePermutation:
    """Tests for the single permutation worker function."""

    def _make_permutation_inputs(self, n_voxels=10, n_resp=5, n_non_resp=5):
        """Create minimal inputs for _run_single_permutation."""
        n_total = n_resp + n_non_resp
        np.random.seed(7)
        test_data = np.random.randn(n_voxels, n_total).astype(np.float32)
        # Make responders higher on average for first few voxels
        test_data[:3, :n_resp] += 3.0

        shape = (4, 4, 4)
        valid_mask = np.zeros(shape, dtype=bool)
        test_coords = []
        for idx in range(n_voxels):
            i, j, k = idx // 16, (idx % 16) // 4, idx % 4
            valid_mask[i, j, k] = True
            test_coords.append([i, j, k])
        test_coords = np.array(test_coords)

        return test_data, test_coords, n_resp, n_total, valid_mask, shape

    @pytest.mark.unit
    def test_unpaired_returns_three_values(self):
        """Unpaired permutation returns (max_stat, max_size, max_mass)."""
        data, coords, n_r, n_t, mask, shape = self._make_permutation_inputs()
        result = _run_single_permutation(
            data, coords, n_r, n_t,
            cluster_threshold=0.05, valid_mask=mask,
            p_values_shape=shape, test_type="unpaired",
            seed=42, return_indices=False,
        )
        assert len(result) == 3
        assert isinstance(result[0], (int, float, np.integer, np.floating))

    @pytest.mark.unit
    def test_paired_returns_three_values(self):
        """Paired permutation returns (max_stat, max_size, max_mass)."""
        data, coords, n_r, n_t, mask, shape = self._make_permutation_inputs(
            n_resp=5, n_non_resp=5
        )
        result = _run_single_permutation(
            data, coords, n_r, n_t,
            cluster_threshold=0.05, valid_mask=mask,
            p_values_shape=shape, test_type="paired",
            seed=42, return_indices=False,
        )
        assert len(result) == 3

    @pytest.mark.unit
    def test_return_indices_gives_four_values(self):
        """With return_indices=True, returns 4-tuple including perm_idx."""
        data, coords, n_r, n_t, mask, shape = self._make_permutation_inputs()
        result = _run_single_permutation(
            data, coords, n_r, n_t,
            cluster_threshold=0.05, valid_mask=mask,
            p_values_shape=shape, seed=42,
            return_indices=True,
        )
        assert len(result) == 4
        assert result[1] is not None  # perm_idx

    @pytest.mark.unit
    def test_deterministic_with_seed(self):
        """Same seed produces same result."""
        data, coords, n_r, n_t, mask, shape = self._make_permutation_inputs()
        kwargs = dict(
            test_data=data, test_coords=coords, n_resp=n_r, n_total=n_t,
            cluster_threshold=0.05, valid_mask=mask, p_values_shape=shape,
            seed=99,
        )
        r1 = _run_single_permutation(**kwargs)
        r2 = _run_single_permutation(**kwargs)
        assert r1[0] == r2[0]

    @pytest.mark.unit
    def test_cluster_stat_mass(self):
        """cluster_stat='mass' returns mass-based max stat."""
        data, coords, n_r, n_t, mask, shape = self._make_permutation_inputs()
        result = _run_single_permutation(
            data, coords, n_r, n_t,
            cluster_threshold=0.05, valid_mask=mask,
            p_values_shape=shape, seed=42,
            cluster_stat="mass",
        )
        assert len(result) == 3


# ─── _identify_significant_clusters ──────────────────────────────────────


class TestIdentifySignificantClusters:
    """Tests for shared cluster significance identification."""

    @pytest.mark.unit
    def test_no_multi_voxel_clusters(self):
        """Single-voxel clusters are excluded (size <= 1)."""
        labeled = np.zeros((3, 3, 3), dtype=int)
        labeled[0, 0, 0] = 1
        labeled[2, 2, 2] = 2
        t_stats = np.ones((3, 3, 3))
        null = np.array([0.0, 0.0, 0.0])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 2, t_stats, null, "size", alpha=0.05,
            alternative="two-sided", _log=logging.getLogger("test"),
        )
        assert len(sig_clusters) == 0
        assert np.sum(sig_mask) == 0

    @pytest.mark.unit
    def test_significant_cluster_detected(self):
        """A large cluster exceeding null distribution is marked significant."""
        labeled = np.zeros((5, 5, 5), dtype=int)
        # Create a 3-voxel cluster
        labeled[1, 1, 1] = 1
        labeled[1, 1, 2] = 1
        labeled[1, 2, 1] = 1
        t_stats = np.zeros((5, 5, 5))
        t_stats[1, 1, 1] = 3.0
        t_stats[1, 1, 2] = 2.5
        t_stats[1, 2, 1] = 2.0
        # Null distribution with small values so cluster is significant
        null = np.array([0.0, 1.0, 0.0, 0.0, 1.0])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 1, t_stats, null, "size", alpha=0.05,
            alternative="two-sided", _log=logging.getLogger("test"),
        )
        assert len(sig_clusters) == 1
        assert sig_clusters[0]["size"] == 3
        assert np.sum(sig_mask) == 3

    @pytest.mark.unit
    def test_mass_stat_cluster(self):
        """cluster_stat='mass' uses sum of t-statistics for threshold."""
        labeled = np.zeros((5, 5, 5), dtype=int)
        labeled[1, 1, 1] = 1
        labeled[1, 1, 2] = 1
        t_stats = np.zeros((5, 5, 5))
        t_stats[1, 1, 1] = 5.0
        t_stats[1, 1, 2] = 3.0
        # Mass = 5 + 3 = 8; null has small masses
        null = np.array([0.0, 1.0, 2.0, 0.0, 1.0])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 1, t_stats, null, "mass", alpha=0.05,
            alternative="two-sided", _log=logging.getLogger("test"),
        )
        assert len(sig_clusters) == 1
        assert sig_clusters[0]["stat_value"] == pytest.approx(8.0)

    @pytest.mark.unit
    def test_with_r_values(self):
        """When r_values provided, sig_clusters include peak_r and mean_r."""
        labeled = np.zeros((5, 5, 5), dtype=int)
        labeled[1, 1, 1] = 1
        labeled[1, 1, 2] = 1
        t_stats = np.zeros((5, 5, 5))
        t_stats[1, 1, 1] = 3.0
        t_stats[1, 1, 2] = 2.0
        r_values = np.zeros((5, 5, 5))
        r_values[1, 1, 1] = 0.8
        r_values[1, 1, 2] = 0.6
        null = np.array([0.0, 0.0, 0.0])

        sig_mask, sig_clusters, observed = _identify_significant_clusters(
            labeled, 1, t_stats, null, "size", alpha=0.05,
            alternative="two-sided", _log=logging.getLogger("test"),
            r_values=r_values,
        )
        assert len(sig_clusters) == 1
        assert sig_clusters[0]["peak_r"] == pytest.approx(0.8)
        assert sig_clusters[0]["mean_r"] == pytest.approx(0.7)


# ─── cluster_analysis ────────────────────────────────────────────────────


class TestClusterAnalysis:
    """Tests for connected-component analysis with MNI mapping."""

    @pytest.mark.unit
    def test_no_clusters(self):
        """Empty significance mask returns empty list."""
        sig_mask = np.zeros((3, 3, 3), dtype=int)
        affine = np.eye(4)
        with patch("nibabel.affines.apply_affine", side_effect=lambda a, c: c):
            result = cluster_analysis(sig_mask, affine)
        assert result == []

    @pytest.mark.unit
    def test_single_cluster(self):
        """Single cluster is correctly identified and sized."""
        sig_mask = np.zeros((5, 5, 5), dtype=int)
        sig_mask[1, 1, 1] = 1
        sig_mask[1, 1, 2] = 1
        sig_mask[1, 2, 1] = 1
        affine = np.eye(4)

        with patch("nibabel.affines.apply_affine", side_effect=lambda a, c: c):
            result = cluster_analysis(sig_mask, affine)

        assert len(result) == 1
        assert result[0]["size"] == 3
        assert result[0]["cluster_id"] == 1

    @pytest.mark.unit
    def test_multiple_clusters_sorted_by_size(self):
        """Multiple clusters are returned sorted by size (descending)."""
        sig_mask = np.zeros((10, 10, 10), dtype=int)
        # Small cluster: 2 voxels
        sig_mask[0, 0, 0] = 1
        sig_mask[0, 0, 1] = 1
        # Large cluster: 4 voxels
        sig_mask[5, 5, 5] = 1
        sig_mask[5, 5, 6] = 1
        sig_mask[5, 6, 5] = 1
        sig_mask[5, 6, 6] = 1
        affine = np.eye(4)

        with patch("nibabel.affines.apply_affine", side_effect=lambda a, c: c):
            result = cluster_analysis(sig_mask, affine)

        assert len(result) == 2
        assert result[0]["size"] == 4  # largest first
        assert result[1]["size"] == 2

    @pytest.mark.unit
    def test_center_mni_computed(self):
        """Cluster center is mapped through the affine."""
        sig_mask = np.zeros((5, 5, 5), dtype=int)
        sig_mask[2, 2, 2] = 1
        sig_mask[2, 2, 3] = 1
        affine = np.eye(4)
        # Identity affine: MNI coords = voxel coords
        with patch("nibabel.affines.apply_affine", side_effect=lambda a, c: c):
            result = cluster_analysis(sig_mask, affine)

        assert len(result) == 1
        # Center should be mean of (2,2,2) and (2,2,3) = (2,2,2.5)
        center = result[0]["center_mni"]
        assert center[0] == pytest.approx(2.0)
        assert center[1] == pytest.approx(2.0)
        assert center[2] == pytest.approx(2.5)
