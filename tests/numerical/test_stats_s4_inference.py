"""S4-1 / S4-2 / S4-4 -- what the volume group test admits and how it studentises (2026-10-31).

S4-1  A voxel entered the test when ANY subject was > 0, so subjects whose warped grey matter
      did not reach it contributed their 0 as if it were a field value. Grey-matter coverage
      that differs by group then made significant "field" clusters out of identical fields.
      A voxel is now tested only where EVERY subject is > 0 (the intersection of coverage),
      ``python -m tit.stats.nifti_average`` averages a group only where every subject of it is
      non-zero (pinned in ``test_nifti_average_runner.py``).
S4-2  The unpaired voxel statistic was pooled-variance Student t. It is now Welch's t, checked
      against ``scipy.stats.ttest_ind(equal_var=False)``; a one-subject group (Welch undefined)
      keeps the pooled t, pinned by ``test_sci09_singleton_group.py``.
S4-4  The t arithmetic ran in float32 (the loader's dtype), so two constant groups got a tiny
      non-zero standard error and a finite |t| of ~1e7 instead of the +/-inf that excludes
      them (SCI-06). It now runs in float64.

Expected values come from scipy (Welch), from the coverage masks the test itself draws
(intersection) -- never from the engine.

Run: ``.venv/bin/python -m pytest tests/numerical/test_stats_s4_inference.py -q -p no:cacheprovider``
(host_numerical: needs only numpy, scipy and nibabel).
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.host_numerical]

_LOG = logging.getLogger("test.s4")


# ─── S4-2: Welch's t ──────────────────────────────────────────────────────


@pytest.mark.parametrize("alternative", ["two-sided", "greater", "less"])
def test_unpaired_statistic_is_welch_t(alternative):
    """12 vs 4 with SD 1:3 -- t and p equal ``scipy.stats.ttest_ind(equal_var=False)``."""
    import scipy.stats as sp_stats

    from tit.stats.engine import ttest_ind

    rng = np.random.default_rng(3)
    a = rng.normal(1.0, 1.0, size=(40, 12))
    b = rng.normal(1.3, 3.0, size=(40, 4))
    t, p = ttest_ind(np.hstack([a, b]), 12, 4, alternative=alternative)
    ref = sp_stats.ttest_ind(a, b, axis=1, equal_var=False, alternative=alternative)
    np.testing.assert_allclose(t, ref.statistic, rtol=1e-12)
    np.testing.assert_allclose(p, ref.pvalue, rtol=1e-10)


def test_voxelwise_unpaired_p_map_is_welch():
    """``ttest_voxelwise``'s p-map is Welch's, voxel by voxel."""
    import scipy.stats as sp_stats

    from tit.stats.engine import ttest_voxelwise

    rng = np.random.default_rng(4)
    a = rng.uniform(0.5, 1.5, size=(3, 4, 2, 6)).astype(np.float32)
    b = rng.uniform(0.2, 3.0, size=(3, 4, 2, 3)).astype(np.float32)
    p, t, valid = ttest_voxelwise(a, b, log=_LOG)
    ref = sp_stats.ttest_ind(
        a.astype(np.float64), b.astype(np.float64), axis=-1, equal_var=False
    )
    assert valid.all()
    np.testing.assert_allclose(t, ref.statistic, rtol=1e-10)
    np.testing.assert_allclose(p, ref.pvalue, rtol=1e-8)


# ─── S4-4: float64 arithmetic ─────────────────────────────────────────────


def test_constant_float32_groups_are_degenerate_not_finite():
    """Two constant float32 groups give +/-inf (excluded), never a finite huge t."""
    from tit.stats.engine import ttest_ind, ttest_rel, ttest_voxelwise

    rng = np.random.default_rng(0)
    n = 7
    levels = rng.uniform(0.01, 1.0, 500).astype(np.float32)
    resp = np.repeat(levels[:, None], n, axis=1)
    non = resp * np.float32(0.5)
    data = np.hstack([resp, non])

    t_ind, _ = ttest_ind(data, n, n)
    t_rel, _ = ttest_rel(data, n)
    assert np.isposinf(t_ind).all(), np.abs(t_ind[np.isfinite(t_ind)]).max()
    assert np.isposinf(t_rel).all(), np.abs(t_rel[np.isfinite(t_rel)]).max()

    # Through the voxelwise test: only the one voxel with real variance is left.
    r4 = np.zeros((501, 1, 1, n), np.float32)
    n4 = np.zeros((501, 1, 1, n), np.float32)
    r4[:500, 0, 0] = resp
    n4[:500, 0, 0] = non
    r4[500, 0, 0] = rng.uniform(0.5, 1.0, n)
    n4[500, 0, 0] = rng.uniform(0.1, 0.5, n)
    _, t_map, valid = ttest_voxelwise(r4, n4, log=_LOG)
    assert int(valid.sum()) == 1 and valid[500, 0, 0]
    assert (t_map[:500] == 0).all()


# ─── S4-1: voxel inclusion = intersection of coverage ─────────────────────


def _coverage_design(seed=7, n1=8, n2=8, cov1=0.9, cov2=0.5):
    """Same field law everywhere; boundary coverage 0.9 in group 1, 0.5 in group 2."""
    from scipy.ndimage import binary_dilation, gaussian_filter

    rng = np.random.default_rng(seed)
    shape = (20, 20, 8)
    core = np.zeros(shape, bool)
    core[6:14, 6:14, 2:6] = True
    shell = binary_dilation(core, iterations=2) & ~core

    def subject(cov):
        field = 0.2 + 0.01 * gaussian_filter(rng.normal(size=shape), 1.0)
        gm = core | (shell & (rng.random(shape) < cov))
        return np.where(gm, field, 0.0).astype(np.float32), gm

    g1 = [subject(cov1) for _ in range(n1)]
    g2 = [subject(cov2) for _ in range(n2)]
    covered_by_all = np.all([gm for _, gm in g1 + g2], axis=0)
    a = np.stack([d for d, _ in g1], -1)
    b = np.stack([d for d, _ in g2], -1)
    return a, b, core, covered_by_all


def test_group_test_admits_only_voxels_every_subject_covers():
    from tit.stats.engine import ttest_voxelwise

    a, b, core, covered_by_all = _coverage_design()
    assert covered_by_all.sum() > core.sum()  # some boundary voxels are covered by all
    _, _, valid = ttest_voxelwise(a, b, log=_LOG)
    np.testing.assert_array_equal(valid, covered_by_all)


def test_group_dependent_coverage_makes_no_significant_cluster():
    """Identical field law, coverage differing by group: no cluster (was 20/20 runs)."""
    from tit.stats.engine import PermutationEngine, ttest_voxelwise

    a, b, _, _ = _coverage_design()
    p, t, valid = ttest_voxelwise(a, b, log=_LOG)
    engine = PermutationEngine(n_permutations=199, n_jobs=1, seed=11, log=_LOG)
    sig_mask, _, sig_clusters, *_ = engine.correct_groups(
        a, b, p_values=p, t_statistics=t, valid_mask=valid
    )
    assert sig_clusters == []
    assert not sig_mask.any()


def test_correlation_admits_only_voxels_every_subject_covers():
    from tit.stats.engine import correlation_voxelwise

    a, b, _, covered_by_all = _coverage_design()
    data = np.concatenate([a, b], axis=-1)
    effect = np.linspace(0.0, 1.0, data.shape[-1])
    *_, valid = correlation_voxelwise(data, effect, log=_LOG)
    np.testing.assert_array_equal(valid, covered_by_all)


# ─── S4-2: the label-shuffling test holds its level under unequal variances ──


def _shuffle_rejection_rate(statistic, data, n_resp, rng, n_shuffles=199):
    """Share of rows a label-shuffling test rejects at 0.05: p = (1 + #{|T*| >= |T|}) / (B + 1)."""
    observed = np.abs(statistic(data))
    at_least = np.ones(len(data))
    for _ in range(n_shuffles):
        at_least += np.abs(statistic(data[:, rng.permutation(data.shape[1])])) >= observed
    return float(np.mean(at_least / (n_shuffles + 1) < 0.05))


def test_welch_shuffle_test_is_not_worse_than_pooled_under_unequal_variances():
    """12 vs 4, SD 1:3, no effect: shuffling the pooled t over-rejects; Welch's t does not.

    600 independent null "voxels" per seed, rates computed here from scipy's pooled
    ``ttest_ind`` and the engine's Welch ``ttest_ind``. Measured at these seeds: pooled
    0.19-0.25, Welch 0.09-0.10 (nominal 0.05; Welch is approximate at 4 subjects).
    """
    import scipy.stats as sp_stats

    from tit.stats.engine import ttest_ind

    rows = 600
    for seed in (1, 2, 3):
        rng = np.random.default_rng(seed)
        data = np.hstack([rng.normal(0, 1, (rows, 12)), rng.normal(0, 3, (rows, 4))])
        welch = _shuffle_rejection_rate(
            lambda d: ttest_ind(d, 12, 4)[0], data, 12, rng
        )
        pooled = _shuffle_rejection_rate(
            lambda d: sp_stats.ttest_ind(d[:, :12], d[:, 12:], axis=1).statistic,
            data,
            12,
            rng,
        )
        assert welch < 0.13
        assert pooled > 0.15
        assert welch + 0.07 < pooled
