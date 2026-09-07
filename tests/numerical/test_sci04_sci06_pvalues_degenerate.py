"""SCI-04 / SCI-06 -- permutation p-values and degenerate t-tests.

SCI-04  ``pval_from_histogram`` returned ``b / m``, so an observed cluster more
        extreme than all ``m`` sampled permutations got ``p = 0``.  That is not
        a valid p-value: with a *sampled* (Monte-Carlo) null the unbiased,
        exact estimator is ``(b + 1) / (m + 1)`` (Phipson & Smyth 2010) -- the
        observation is a member of its own permutation distribution.  ``b / m``
        is correct only for exhaustive enumeration, now opted into explicitly
        with ``sampled=False``.

SCI-06  ``ttest_ind`` / ``ttest_rel`` set ``t = 0`` (hence ``p = 1``) whenever
        the standard error was zero, conflating "no evidence" with "perfect
        separation".  A nonzero contrast over zero within-group variance is the
        *strongest* possible evidence; scipy reports ``+/-inf`` with ``p -> 0``.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.unit


# ─── SCI-04 ───────────────────────────────────────────────────────────────


def test_sampled_pvalue_is_never_zero():
    from tit.stats.engine import pval_from_histogram

    null = np.arange(1.0, 1001.0)  # m = 1000
    p = pval_from_histogram(np.array([1e9]), null, tail=1)
    assert p[0] > 0.0
    assert p[0] == pytest.approx(1.0 / 1001.0)


def test_minimum_p_is_one_over_m_plus_one():
    from tit.stats.engine import pval_from_histogram

    for m in (10, 100, 5000):
        null = np.zeros(m)
        p = pval_from_histogram(np.array([1.0]), null, tail=1)
        assert p[0] == pytest.approx(1.0 / (m + 1))


@pytest.mark.parametrize(
    "tail,observed,expected_b",
    [(1, 3.0, 3), (-1, 2.0, 2), (0, 3.0, 3)],
)
def test_counts_match_hand_computation(tail, observed, expected_b):
    from tit.stats.engine import pval_from_histogram

    null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    p = pval_from_histogram(np.array([observed]), null, tail=tail)
    assert p[0] == pytest.approx((expected_b + 1) / (5 + 1))


def test_exact_enumeration_opt_out_uses_b_over_m():
    from tit.stats.engine import pval_from_histogram

    null = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    p = pval_from_histogram(np.array([3.0]), null, tail=1, sampled=False)
    assert p[0] == pytest.approx(3 / 5)


def test_sampled_pvalue_is_conservative_relative_to_naive():
    from tit.stats.engine import pval_from_histogram

    rng = np.random.default_rng(0)
    null = rng.normal(size=500)
    obs = np.array([0.0, 1.0, 2.0, 3.0])
    sampled = pval_from_histogram(obs, null, tail=1)
    naive = pval_from_histogram(obs, null, tail=1, sampled=False)
    assert np.all(sampled >= naive)
    assert np.all(sampled <= 1.0)


# ─── SCI-06 ───────────────────────────────────────────────────────────────


def _pack(a, b):
    """Two constant groups of 4 as a single (1, 8) test_data row."""
    return np.array([[a] * 4 + [b] * 4], dtype=float)


@pytest.mark.parametrize("alternative", ["two-sided", "greater", "less"])
def test_degenerate_zero_over_zero_is_nan_like_scipy(alternative):
    from scipy import stats as sp

    from tit.stats.engine import ttest_ind, ttest_rel

    for fn in (lambda d: ttest_ind(d, 4, 4, alternative=alternative),
               lambda d: ttest_rel(d, 4, alternative=alternative)):
        t, p = fn(_pack(1.0, 1.0))
        assert np.isnan(t[0])
        assert np.isnan(p[0])

    ref = sp.ttest_ind([1.0] * 4, [1.0] * 4, alternative=alternative)
    assert np.isnan(ref.statistic) and np.isnan(ref.pvalue)


@pytest.mark.parametrize(
    "a,b,sign", [(2.0, 1.0, +1), (1.0, 2.0, -1)]
)
@pytest.mark.parametrize("alternative", ["two-sided", "greater", "less"])
def test_perfect_separation_matches_scipy(a, b, sign, alternative):
    from scipy import stats as sp

    from tit.stats.engine import ttest_ind

    t, p = ttest_ind(_pack(a, b), 4, 4, alternative=alternative)
    ref = sp.ttest_ind([a] * 4, [b] * 4, alternative=alternative)

    assert np.isinf(t[0]) and np.sign(t[0]) == sign
    assert t[0] == ref.statistic
    assert p[0] == pytest.approx(float(ref.pvalue))


@pytest.mark.parametrize("alternative", ["two-sided", "greater", "less"])
def test_perfect_separation_paired_matches_scipy(alternative):
    from scipy import stats as sp

    from tit.stats.engine import ttest_rel

    t, p = ttest_rel(_pack(2.0, 1.0), 4, alternative=alternative)
    ref = sp.ttest_rel([2.0] * 4, [1.0] * 4, alternative=alternative)
    assert np.isinf(t[0]) and t[0] > 0
    assert p[0] == pytest.approx(float(ref.pvalue))


def test_v2_behaviour_would_have_reported_no_effect():
    """The defect in one line: a perfectly separated voxel scored t=0, p=1."""
    from tit.stats.engine import ttest_ind

    t, p = ttest_ind(_pack(2.0, 1.0), 4, 4)
    assert not (t[0] == 0.0 and p[0] == 1.0)


def test_voxelwise_drops_degenerate_voxels_from_valid_mask():
    from tit.stats.engine import ttest_voxelwise

    resp = np.zeros((3, 1, 1, 4))
    non = np.zeros((3, 1, 1, 4))
    # voxel 0: real, noisy effect;  1: perfect separation;  2: constant/equal
    resp[0, 0, 0] = [1.0, 1.2, 0.9, 1.1]
    non[0, 0, 0] = [0.2, 0.1, 0.3, 0.25]
    resp[1, 0, 0] = 2.0
    non[1, 0, 0] = 1.0
    resp[2, 0, 0] = 1.0
    non[2, 0, 0] = 1.0

    p, t, valid = ttest_voxelwise(resp, non)
    assert valid[0, 0, 0]
    assert not valid[1, 0, 0] and not valid[2, 0, 0]
    assert np.all(np.isfinite(t))
    assert np.all(np.isfinite(p))
