#!/usr/bin/env simnibs_python
"""
Unit tests for tit/calc.py additions -- mTI focality-core Phase 4 (tasks 3, 5).

Two independent pieces of new/changed behaviour are covered here:

1. ``get_TI_vectors`` was rewritten to Hirata et al. (2024)'s sign-agnostic
   closed form. ``TestHirataFormEquivalence`` proves the rewrite is exactly
   equivalent (not just numerically close) to the previous
   preprocess-then-branch implementation, by keeping a verbatim copy of
   that old implementation as a private reference (``_legacy_get_TI_vectors``
   below) and comparing outputs to 1e-12 over >= 1e4 random field pairs, plus
   a battery of hand-picked degenerate/boundary cases.

2. ``compute_direct_field_peak_hf`` / ``_direct_field_peak_hf_actual`` were
   ported from the ``albantakis`` collaborator branches (``mTI_testing`` /
   ``mti_formain_cleanup``), see ``tit/calc.py``'s module docstring
   "Attribution". ``TestDirectFieldPeakHF`` adapts her
   ``tests/test_calc.py::TestDirectFieldMagnitude`` /
   ``TestDirectFieldDirectional`` cases (which exercised
   ``compute_direct_field_peak_hf`` alongside functions not ported here) to
   this repo's conventions, dropping the ``MTIFieldMethod`` dispatch
   argument that does not exist in this repo's ``tit/calc.py``.
"""

import sys
import pytest
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.calc import (
    get_TI_vectors,
    compute_direct_field_peak_hf,
)

RNG = np.random.default_rng(1234)


# ---------------------------------------------------------------------------
# Reference (pre-Hirata-rewrite) implementation, kept ONLY for the
# equivalence check below. This is a verbatim copy of get_TI_vectors as it
# existed on `main` before tracks/active/mti-focality-core.md Phase 4 task 3
# rewrote it to the Hirata sign-agnostic closed form. Do not use elsewhere.
# ---------------------------------------------------------------------------


def _legacy_get_TI_vectors(E1_org, E2_org):
    assert E1_org.shape == E2_org.shape, "E1 and E2 must have same shape"
    assert E1_org.shape[1] == 3, "Vectors must be 3D"

    E1 = E1_org.copy()
    E2 = E2_org.copy()

    idx_swap = np.linalg.norm(E2, axis=1) > np.linalg.norm(E1, axis=1)
    E1[idx_swap], E2[idx_swap] = E2[idx_swap], E1_org[idx_swap]

    idx_flip = np.sum(E1 * E2, axis=1) < 0
    E2[idx_flip] = -E2[idx_flip]

    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)

    denom = normE1 * normE2
    denom[denom == 0] = 1.0
    cosalpha = np.clip(np.sum(E1 * E2, axis=1) / denom, -1.0, 1.0)

    regime1_mask = normE2 <= normE1 * cosalpha

    TI_vectors = np.zeros_like(E1)

    TI_vectors[regime1_mask] = 2.0 * E2[regime1_mask]

    regime2_mask = ~regime1_mask
    if np.any(regime2_mask):
        h = E1[regime2_mask] - E2[regime2_mask]
        h_norm = np.linalg.norm(h, axis=1)
        h_norm[h_norm == 0] = 1.0
        e_h = h / h_norm[:, None]
        E2_parallel_component = np.sum(E2[regime2_mask] * e_h, axis=1)[:, None] * e_h
        E2_perp = E2[regime2_mask] - E2_parallel_component
        TI_vectors[regime2_mask] = 2.0 * E2_perp

    return TI_vectors


# ---------------------------------------------------------------------------
# TestHirataFormEquivalence -- Task 1
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHirataFormEquivalence:
    """get_TI_vectors (Hirata sign-agnostic form) must exactly reproduce
    _legacy_get_TI_vectors (the old preprocess-then-branch form)."""

    def test_bulk_random_pairs_1e12(self):
        """>= 1e4 random field pairs, spanning several magnitude scales,
        must match to 1e-12."""
        n_total = 0
        for scale in (1e-3, 1.0, 1e3):
            for _ in range(20):
                n = 200
                E1 = scale * RNG.standard_normal((n, 3))
                E2 = scale * RNG.standard_normal((n, 3))
                new = get_TI_vectors(E1, E2)
                old = _legacy_get_TI_vectors(E1, E2)
                np.testing.assert_allclose(new, old, atol=1e-12, rtol=0)
                n_total += n
        assert n_total >= 10_000

    def test_near_boundary_pairs(self):
        """Random pairs constructed to sit close to the regime boundary
        min(|E1|,|E2|) == sqrt(|E1.E2|), where the two formulations are
        most likely to diverge numerically."""
        n = 2000
        # Build E2 as a small rotation/scaling of E1 so many pairs land
        # near-parallel (a common near-boundary configuration).
        E1 = RNG.standard_normal((n, 3))
        jitter = 0.05 * RNG.standard_normal((n, 3))
        E2 = 0.9 * E1 + jitter
        new = get_TI_vectors(E1, E2)
        old = _legacy_get_TI_vectors(E1, E2)
        np.testing.assert_allclose(new, old, atol=1e-12, rtol=0)

    def test_random_signs_and_orthogonality(self):
        """Mix of near-orthogonal and near-antiparallel pairs."""
        n = 2000
        E1 = RNG.standard_normal((n, 3))
        # Orthogonal complement (Gram-Schmidt against E1) plus small noise
        E2_raw = RNG.standard_normal((n, 3))
        proj = np.sum(E1 * E2_raw, axis=1, keepdims=True) / np.sum(
            E1 * E1, axis=1, keepdims=True
        )
        E2_orth = E2_raw - proj * E1
        new = get_TI_vectors(E1, E2_orth)
        old = _legacy_get_TI_vectors(E1, E2_orth)
        np.testing.assert_allclose(new, old, atol=1e-12, rtol=0)

        E2_anti = -E1 + 0.01 * RNG.standard_normal((n, 3))
        new2 = get_TI_vectors(E1, E2_anti)
        old2 = _legacy_get_TI_vectors(E1, E2_anti)
        np.testing.assert_allclose(new2, old2, atol=1e-12, rtol=0)

    @pytest.mark.parametrize(
        "E1,E2",
        [
            (np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 0.0, 0.0]])),
            (np.array([[0.0, 0.0, 0.0]]), np.array([[1.0, 0.0, 0.0]])),
            (np.array([[0.0, 0.0, 0.0]]), np.array([[0.0, 0.0, 0.0]])),
            (np.array([[1.0, 0.0, 0.0]]), np.array([[1.0, 0.0, 0.0]])),
            (np.array([[1.0, 0.0, 0.0]]), np.array([[-1.0, 0.0, 0.0]])),
            (np.array([[2.0, 0.0, 0.0]]), np.array([[0.0, 3.0, 0.0]])),
            (np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 1.0, 0.0]])),
            (np.array([[1.0, 2.0, 3.0]]), np.array([[1.0, 2.0, 3.0]]) * 1e-9),
        ],
    )
    def test_hand_picked_degenerate_cases(self, E1, E2):
        new = get_TI_vectors(E1, E2)
        old = _legacy_get_TI_vectors(E1, E2)
        np.testing.assert_allclose(new, old, atol=1e-12, rtol=0)

    def test_existing_regime1_and_regime2_fixtures_still_pass(self):
        """Sanity cross-check against tests/test_calc.py's own fixtures --
        the rewrite must not change get_TI_vectors's public behaviour."""
        cases = [
            (np.array([[2.0, 0.0, 0.0]]), np.array([[1.0, 0.0, 0.0]])),
            (np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 1.0, 0.0]])),
            (
                np.array([[2.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 3.0, 0.0]]),
                np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 0.0]]),
            ),
        ]
        for E1, E2 in cases:
            new = get_TI_vectors(E1, E2)
            old = _legacy_get_TI_vectors(E1, E2)
            np.testing.assert_allclose(new, old, atol=1e-12, rtol=0)


# ---------------------------------------------------------------------------
# TestDirectFieldPeakHF -- Task 3 (ported from albantakis collaborator
# branches, tests/test_calc.py::TestDirectFieldMagnitude /
# TestDirectFieldDirectional)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDirectFieldPeakHF:
    """Tests for compute_direct_field_peak_hf, adapted from the
    albantakis collaborator branches' tests/test_calc.py."""

    def test_parallel_pairs_have_expected_amplitude(self):
        """Adapted from TestDirectFieldMagnitude::
        test_parallel_pairs_have_expected_amplitude (mTI_testing /
        mti_formain_cleanup). Signed vector sum of
        [[2,0,0],[1,0,0],[4,0,0],[3,0,0]] -> [10,0,0], norm 10."""
        fields = [
            np.array([[2.0, 0.0, 0.0]]),
            np.array([[1.0, 0.0, 0.0]]),
            np.array([[4.0, 0.0, 0.0]]),
            np.array([[3.0, 0.0, 0.0]]),
        ]
        peak = compute_direct_field_peak_hf(fields)
        np.testing.assert_allclose(peak, [10.0], atol=1e-12)

    def test_two_field_case_matches_direct_sum(self):
        """K=1 (two fields): peak_hf = |E1 + E2|."""
        E1 = np.array([[3.0, 0.0, 0.0]])
        E2 = np.array([[0.0, 4.0, 0.0]])
        peak = compute_direct_field_peak_hf([E1, E2])
        np.testing.assert_allclose(peak, [5.0], atol=1e-12)

    def test_cancelling_pairs_give_zero(self):
        """Opposing pairs cancel exactly in the signed sum."""
        fields = [
            np.array([[1.0, 0.0, 0.0]]),
            np.array([[-1.0, 0.0, 0.0]]),
        ]
        peak = compute_direct_field_peak_hf(fields)
        np.testing.assert_allclose(peak, [0.0], atol=1e-12)

    def test_multi_element_arrays(self):
        n = 25
        fields = [RNG.standard_normal((n, 3)) for _ in range(4)]
        peak = compute_direct_field_peak_hf(fields)
        expected = np.linalg.norm(sum(fields), axis=1)
        assert peak.shape == (n,)
        np.testing.assert_allclose(peak, expected, atol=1e-12)

    def test_no_nans_for_random_inputs(self):
        fields = [RNG.standard_normal((50, 3)) for _ in range(6)]
        peak = compute_direct_field_peak_hf(fields)
        assert not np.any(np.isnan(peak))
        assert not np.any(np.isinf(peak))
        assert np.all(peak >= 0)

    def test_odd_number_of_fields_raises(self):
        fields = [RNG.standard_normal((5, 3)) for _ in range(3)]
        with pytest.raises(ValueError, match="even number"):
            compute_direct_field_peak_hf(fields)

    def test_single_field_raises(self):
        with pytest.raises(ValueError, match="even number"):
            compute_direct_field_peak_hf([RNG.standard_normal((5, 3))])

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="even number"):
            compute_direct_field_peak_hf([])

    def test_shape_mismatch_raises(self):
        E1 = np.ones((5, 3))
        E2 = np.ones((3, 3))
        with pytest.raises(ValueError, match="identical shape"):
            compute_direct_field_peak_hf([E1, E2])

    def test_wrong_dimension_raises(self):
        bad = np.array([[1.0, 2.0]])  # (1, 2), not (N, 3)
        with pytest.raises(ValueError, match="shape"):
            compute_direct_field_peak_hf([bad, bad])

    def test_bounded_by_sum_of_norms(self):
        """Triangle inequality: peak_hf <= sum(|field_i|)."""
        for _ in range(20):
            fields = [RNG.standard_normal((10, 3)) for _ in range(4)]
            peak = compute_direct_field_peak_hf(fields)
            upper_bound = sum(np.linalg.norm(f, axis=1) for f in fields)
            np.testing.assert_array_less(peak, upper_bound + 1e-10)
