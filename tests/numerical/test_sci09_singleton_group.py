"""SCI-09 -- a group of one made every voxel degenerate.

``engine.ttest_ind`` built the pooled variance as
``(n - 1) * np.var(x, ddof=1)``.  For ``n == 1`` that is ``0 * nan == nan``,
not the ``0`` the pooled estimator calls for, so the standard error and the t
of *every* voxel of a one-vs-many comparison came out ``nan``.

On 2.2.3--2.5.0 the ``valid = se_diff > 0`` guard then left ``t = 0, p = 1``
everywhere: a complete, uniformly null result.  On this branch, after
SCI-06 (docs/releases/v3.0.0.md#scientific-corrections) made ``_safe_t`` IEEE-correct, the
``nan`` reached ``ttest_voxelwise``, emptied ``valid_mask`` and raised.

These are numerical claims about agreement with ``scipy``, so they live in the
real-library leg.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.unit

ALTERNATIVES = ("two-sided", "greater", "less")

# Two voxels: one with a real contrast, one with almost none.
_RESP = np.array([[0.40, 0.90], [0.20, 0.30]])
_NON_RESP = np.array([[0.15], [0.25]])


def _scipy_alternative(alt):
    return {"two-sided": "two-sided", "greater": "greater", "less": "less"}[alt]


@pytest.mark.parametrize("alternative", ALTERNATIVES)
def test_two_vs_one_matches_scipy(alternative):
    """A 2-vs-1 design agrees with ``scipy.stats.ttest_ind(equal_var=True)``."""
    import scipy.stats as sp_stats

    from tit.stats.engine import ttest_ind

    data = np.hstack([_RESP, _NON_RESP])
    t, p = ttest_ind(data, n_resp=2, n_non_resp=1, alternative=alternative)

    for i in range(data.shape[0]):
        ref = sp_stats.ttest_ind(
            _RESP[i],
            _NON_RESP[i],
            equal_var=True,
            alternative=_scipy_alternative(alternative),
        )
        assert t[i] == pytest.approx(float(ref.statistic))
        assert p[i] == pytest.approx(float(ref.pvalue))


@pytest.mark.parametrize("alternative", ALTERNATIVES)
def test_one_vs_two_matches_scipy(alternative):
    """The singleton on the *other* side of the split is equally well defined."""
    import scipy.stats as sp_stats

    from tit.stats.engine import ttest_ind

    data = np.hstack([_NON_RESP, _RESP])
    t, p = ttest_ind(data, n_resp=1, n_non_resp=2, alternative=alternative)

    for i in range(data.shape[0]):
        ref = sp_stats.ttest_ind(
            _NON_RESP[i],
            _RESP[i],
            equal_var=True,
            alternative=_scipy_alternative(alternative),
        )
        assert t[i] == pytest.approx(float(ref.statistic))
        assert p[i] == pytest.approx(float(ref.pvalue))


def test_the_v2x_expression_really_is_nan_here():
    """The defect, stated directly: the old numerator is ``nan`` on this input.

    Without this the tests above only show the new form is right, not that the
    old one was wrong.
    """
    n_resp, n_non_resp = 2, 1
    with np.errstate(invalid="ignore"):
        resp_vars = np.var(_RESP, axis=1, ddof=1)
        non_resp_vars = np.var(_NON_RESP, axis=1, ddof=1)
        numerator = (n_resp - 1) * resp_vars + (n_non_resp - 1) * non_resp_vars

    assert np.all(np.isfinite(resp_vars))
    assert np.all(np.isnan(non_resp_vars))  # 0/0 for a group of one
    assert np.all(np.isnan(numerator))  # 0 * nan == nan, not 0


def test_degrees_of_freedom_are_one():
    """df = n1 + n2 - 2 = 1, so the p-values come from a t(1), not a normal."""
    import scipy.stats as sp_stats

    from tit.stats.engine import ttest_ind

    data = np.array([[10.0, 12.0, 1.0]])
    t, p = ttest_ind(data, n_resp=2, n_non_resp=1)
    # pooled var = ((10-11)^2 + (12-11)^2 + 0) / 1 = 2; se = sqrt(2 * 3/2) = sqrt(3)
    assert t[0] == pytest.approx(10.0 / np.sqrt(3.0))
    assert p[0] == pytest.approx(2 * sp_stats.t.sf(abs(t[0]), 1))


def test_groups_of_two_or_more_are_unchanged():
    """The rewrite is a no-op wherever the old expression was already defined."""
    import scipy.stats as sp_stats

    from tit.stats.engine import ttest_ind

    rng = np.random.default_rng(20260907)
    resp = rng.normal(0.5, 0.2, size=(16, 4))
    non_resp = rng.normal(0.4, 0.2, size=(16, 5))
    t, p = ttest_ind(np.hstack([resp, non_resp]), n_resp=4, n_non_resp=5)

    for i in range(16):
        ref = sp_stats.ttest_ind(resp[i], non_resp[i], equal_var=True)
        assert t[i] == pytest.approx(float(ref.statistic))
        assert p[i] == pytest.approx(float(ref.pvalue))


def test_ttest_voxelwise_keeps_a_non_empty_valid_mask():
    """End-to-end shape: the 2-vs-1 run has voxels to test, so it writes maps.

    Before the fix every voxel was ``nan``, ``ttest_voxelwise`` counted them all
    degenerate, ``valid_mask`` emptied and the run raised "No voxel could be
    tested" with nothing but its log on disk.
    """
    from tit.stats.engine import ttest_voxelwise

    responders = np.zeros((2, 1, 1, 2))
    non_responders = np.zeros((2, 1, 1, 1))
    responders[0, 0, 0, :] = _RESP[0]
    non_responders[0, 0, 0, :] = _NON_RESP[0]
    responders[1, 0, 0, :] = _RESP[1]
    non_responders[1, 0, 0, :] = _NON_RESP[1]

    p_values, t_stats, valid_mask = ttest_voxelwise(responders, non_responders)

    assert valid_mask.sum() == 2
    assert np.all(np.isfinite(t_stats[valid_mask]))
    assert np.all(p_values[valid_mask] <= 1.0)


def test_three_subjects_cannot_reach_significance():
    """The floor: three subjects admit three relabellings, so p can never be small.

    Documents that "zero significant clusters with three subjects" is the
    arithmetic of the design, not a defect downstream of this fix.
    """
    from itertools import combinations

    from tit.stats.engine import pval_from_histogram

    relabellings = list(combinations(range(3), 1))
    assert len(relabellings) == 3

    # Best case: the observed labelling is the most extreme of the three.  An
    # exhaustive enumeration contains the observation itself, so b >= 1.
    observed = 1e9
    null = np.array([observed, 0.0, 0.0])

    exhaustive = pval_from_histogram(np.array([observed]), null, tail=1, sampled=False)
    assert exhaustive[0] == pytest.approx(1.0 / 3.0)

    # The shipped default treats the null as a sample and adds the observation
    # again, which is one notch more conservative still.
    sampled = pval_from_histogram(np.array([observed]), null, tail=1)
    assert sampled[0] == pytest.approx(2.0 / 4.0)

    # Either estimator is an order of magnitude above any usable alpha.
    assert min(exhaustive[0], sampled[0]) > 0.3
