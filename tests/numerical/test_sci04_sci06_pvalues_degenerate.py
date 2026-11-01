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

from types import SimpleNamespace

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


# ---------------------------------------------------------------------------
# The empty-mask guard SCI-06 made reachable
# ---------------------------------------------------------------------------


class TestEmptyValidMaskIsReported:
    """An all-degenerate group is a reportable state, not a numpy traceback.

    Excluding degenerate voxels from ``valid_mask`` (SCI-06) made an *empty* mask reachable for
    data that previously produced ``t = 0, p = 1`` everywhere. The caller's first act is
    ``np.min(p_values[valid_mask])``, which then raised "zero-size array to reduction operation
    minimum which has no identity" — observed on a real ``cluster-permutation`` job against the
    dev container, where it reached the user as a bare stack trace.
    """

    def test_every_voxel_degenerate_raises_naming_the_cause(self):
        import numpy as np
        import pytest

        from tit.stats.engine import ttest_voxelwise

        # Non-zero (so the voxels are in the mask) but constant within each group, at every
        # voxel: zero within-group variance everywhere.
        resp = np.full((2, 2, 2, 3), 1.0, dtype=np.float32)
        non_resp = np.full((2, 2, 2, 3), 2.0, dtype=np.float32)

        with pytest.raises(ValueError, match="zero within-group variance"):
            ttest_voxelwise(resp, non_resp, test_type="unpaired")

    def test_no_data_at_all_raises_saying_so_instead(self):
        import numpy as np
        import pytest

        from tit.stats.engine import ttest_voxelwise

        zeros = np.zeros((2, 2, 2, 3), dtype=np.float32)

        with pytest.raises(ValueError, match="non-zero in every subject"):
            ttest_voxelwise(zeros, zeros, test_type="unpaired")

    def test_one_testable_voxel_is_enough(self):
        """The guard fires on empty, not on small — one usable voxel still returns."""
        import numpy as np

        from tit.stats.engine import ttest_voxelwise

        resp = np.full((2, 2, 2, 3), 1.0, dtype=np.float32)
        non_resp = np.full((2, 2, 2, 3), 2.0, dtype=np.float32)
        resp[0, 0, 0, :] = [1.0, 2.0, 3.0]

        p_values, t_statistics, valid_mask = ttest_voxelwise(
            resp, non_resp, test_type="unpaired"
        )
        assert int(np.count_nonzero(valid_mask)) == 1
        assert valid_mask[0, 0, 0]


# ---------------------------------------------------------------------------
# Replicas of the observed grouping are ties
# ---------------------------------------------------------------------------


def test_every_relabelling_that_reproduces_the_observed_grouping_ties_it(monkeypatch):
    """A within-group reordering of the observed 5-vs-5 labelling, or its mirror, is the same
    partition, so its two-sided cluster mass IS the observed one and counts as at least as
    extreme. The engine computed t in float32 (float64 since S4-4), so the reordered mass
    differed by float32 rounding (1.4e-8 relative here, 4.3e-8 on the real-path block,
    measured 2026-10-31); with TIE_RTOL = 1e-9, 86 of these 240 replicas were dropped
    (p = 155/241), and on CI (numerical-image on 4be8739a) the planted block's p came out one count too small: 0.015
    where the written null gives 0.02. The expected value is a property of the design (every
    replica ties), not a number from the engine.
    """
    import itertools

    from tit.stats import engine

    rng = np.random.default_rng(20261022)
    shape = (8, 8, 8)
    block = (slice(2, 5),) * 3
    vols = []
    for subject in range(10):
        data = 0.1 + 0.05 * rng.random(shape)
        if subject < 5:
            data[block] = 1.0 + 0.02 * rng.random((3, 3, 3))
        vols.append(data)
    stack = np.stack(vols, axis=-1)
    valid = np.ones(shape, dtype=bool)
    coords = np.argwhere(valid)
    test_data = stack[valid].astype(np.float32)

    def mass(order):
        monkeypatch.setattr(
            engine.np.random,
            "default_rng",
            lambda seed=None: SimpleNamespace(permutation=lambda n: np.array(order)),
        )
        stat, *_ = engine._run_single_permutation(
            test_data, coords, 5, 10, 0.05, valid, shape, cluster_stat="mass"
        )
        return stat

    observed = mass(range(10))
    non = list(range(5, 10))
    replicas = [
        mass(order)
        for resp in itertools.permutations(range(5))
        for order in (list(resp) + non[::-1], non + list(resp))
    ]
    assert observed > 0, "the planted block must form a cluster"
    assert len(replicas) == 240
    p = engine.pval_from_histogram([observed], np.array(replicas), tail=0)
    assert p[0] == pytest.approx(1.0), "every replica of the observed grouping is a tie"
