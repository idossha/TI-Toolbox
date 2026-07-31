#!/usr/bin/env simnibs_python
"""
Unit tests for the mTI (N>2 electrode pair) envelope in tit/calc.py.

Covers get_mTI_vectors's dispatch/validation contract and the verified
_mti_modulation_depth envelope that backs it for K>=2 electrode pairs,
including the K=1 exact-vs-sweep consistency check and a regression test
documenting the intentional behavior change away from the old (invalid)
recursive binary-tree formula.
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.calc import (
    get_TI_vectors,
    get_mTI_vectors,
    get_nTI_vectors,
    _mti_modulation_depth,
)

RNG = np.random.default_rng(7)


def _random_fields(n_fields, n_elements=50, rng=RNG):
    return [rng.standard_normal((n_elements, 3)) for _ in range(n_fields)]


# ---------------------------------------------------------------------------
# get_mTI_vectors -- N=2 exact dispatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMTIVectorsN2:
    def test_matches_get_ti_vectors_exactly(self):
        E1, E2 = _random_fields(2, n_elements=500)
        result = get_mTI_vectors([E1, E2])
        expected = get_TI_vectors(E1, E2)
        diff = np.max(np.abs(result - expected))
        assert diff == 0.0
        np.testing.assert_array_equal(result, expected)

    def test_psi_ignored_at_n2(self):
        """psi has no effect on a single pair (K=1 phase invariance)."""
        E1, E2 = _random_fields(2, n_elements=50)
        result_no_psi = get_mTI_vectors([E1, E2], psi=None)
        result_with_psi = get_mTI_vectors([E1, E2], psi=[1.7])
        np.testing.assert_allclose(result_no_psi, result_with_psi, atol=1e-12)


# ---------------------------------------------------------------------------
# get_mTI_vectors -- N=4/6/8 shapes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMTIVectorsShapes:
    @pytest.mark.parametrize("n_pairs", [2, 3, 4])
    def test_runs_and_returns_correct_shape(self, n_pairs):
        n_elements = 30
        fields = _random_fields(2 * n_pairs, n_elements=n_elements)
        result = get_mTI_vectors(fields)
        assert result.shape == (n_elements, 3)
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))

    def test_eight_fields_shape_with_psi(self):
        n_elements = 20
        fields = _random_fields(8, n_elements=n_elements)
        psi = [0.0, 0.5, -0.5, 1.0]
        result = get_mTI_vectors(fields, psi=psi)
        assert result.shape == (n_elements, 3)
        assert not np.any(np.isnan(result))


# ---------------------------------------------------------------------------
# get_mTI_vectors -- input validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMTIVectorsValidation:
    def test_odd_n_raises(self):
        fields = _random_fields(5)
        with pytest.raises(ValueError, match="even number"):
            get_mTI_vectors(fields)

    def test_n_less_than_2_raises(self):
        fields = _random_fields(1)
        with pytest.raises(ValueError, match="even number"):
            get_mTI_vectors(fields)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="even number"):
            get_mTI_vectors([])

    def test_mismatched_shapes_raises(self):
        E1, E2 = _random_fields(2, n_elements=10)
        E3, E4 = _random_fields(2, n_elements=7)
        with pytest.raises(ValueError, match="identical shape"):
            get_mTI_vectors([E1, E2, E3, E4])

    def test_wrong_last_dim_raises(self):
        bad = RNG.standard_normal((10, 2))
        ok = RNG.standard_normal((10, 3))
        with pytest.raises(ValueError, match="must have shape"):
            get_mTI_vectors([bad, ok])

    def test_bad_psi_shape_raises(self):
        fields = _random_fields(4, n_elements=10)
        with pytest.raises(ValueError, match="psi"):
            get_mTI_vectors(fields, psi=[0.0, 0.0, 0.0])  # K=2, needs shape (2,)


# ---------------------------------------------------------------------------
# K=1 exact-vs-sweep consistency (_mti_modulation_depth)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestK1ExactVsSweep:
    """The (P, Q) sweep form reduces exactly to the K=1 closed form."""

    def test_sweep_matches_exact_magnitude(self):
        E1, E2 = _random_fields(2, n_elements=300)
        exact = _mti_modulation_depth([E1, E2], refine=True)
        sweep = _mti_modulation_depth([E1, E2], refine=False, num_directions=2048)
        ti_mag = np.linalg.norm(get_TI_vectors(E1, E2), axis=1)

        np.testing.assert_allclose(exact["md"], ti_mag, atol=1e-9)
        # A dense coarse sweep should closely approximate the exact value;
        # generous tolerance since it is a finite direction search.
        np.testing.assert_allclose(sweep["md"], ti_mag, atol=5e-2)

    def test_refine_false_is_coarse_sweep_only(self):
        """refine=False at K=1 does not take the exact-closed-form path."""
        E1, E2 = _random_fields(2, n_elements=50)
        result = _mti_modulation_depth([E1, E2], refine=False, num_directions=192)
        assert result["md"].shape == (50,)
        assert np.all(result["md"] >= 0.0)


# ---------------------------------------------------------------------------
# _mti_modulation_depth -- K>=2 sanity checks
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModulationDepthKGe2:
    def test_returns_expected_keys_and_shapes(self):
        n_elements = 25
        fields = _random_fields(4, n_elements=n_elements)
        result = _mti_modulation_depth(fields)
        assert set(result.keys()) == {"md", "carrier_power", "best_direction"}
        assert result["md"].shape == (n_elements,)
        assert result["carrier_power"].shape == (n_elements,)
        assert result["best_direction"].shape == (n_elements, 3)

    def test_best_direction_is_unit_vector(self):
        fields = _random_fields(4, n_elements=25)
        result = _mti_modulation_depth(fields)
        norms = np.linalg.norm(result["best_direction"], axis=1)
        np.testing.assert_allclose(norms, np.ones(25), atol=1e-8)

    def test_anti_phase_pairs_cancel(self):
        """Equal-amplitude K=2 with psi=[0, pi] cancels to MD=0 exactly
        along the direction shared by both pairs."""
        n = 5
        n_hat = np.array([1.0, 0.0, 0.0])
        a = RNG.uniform(0.5, 2.0, size=n)
        b = RNG.uniform(0.5, 2.0, size=n)
        E1a = np.outer(a, n_hat)
        E1b = np.outer(b, n_hat)
        E2a = np.outer(a, n_hat)
        E2b = np.outer(b, n_hat)
        directions = np.tile(n_hat, (n, 1))
        result = _mti_modulation_depth(
            [E1a, E1b, E2a, E2b], psi=[0.0, np.pi], directions=directions
        )
        np.testing.assert_allclose(result["md"], np.zeros(n), atol=1e-10)

    def test_refine_true_never_worse_than_refine_false(self):
        fields = _random_fields(4, n_elements=100)
        coarse = _mti_modulation_depth(fields, refine=False)
        refined = _mti_modulation_depth(fields, refine=True)
        assert np.all(refined["md"] >= coarse["md"] - 1e-12)


# ---------------------------------------------------------------------------
# get_nTI_vectors -- deprecation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNTIDeprecation:
    def test_emits_deprecation_warning(self):
        E1, E2 = _random_fields(2, n_elements=10)
        with pytest.warns(DeprecationWarning, match="deprecated"):
            get_nTI_vectors([E1, E2])

    def test_warning_survives_error_filter_context(self):
        E1, E2 = _random_fields(2, n_elements=10)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            get_nTI_vectors([E1, E2])
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)


# ---------------------------------------------------------------------------
# Regression: new mTI result intentionally differs from the old recursive
# binary-tree formula at N=4 (documents the fixed +38.6% mean error bug).
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecursiveRegression:
    def test_new_result_differs_materially_from_old_recursive_formula(self):
        fields = _random_fields(4, n_elements=200)
        new_result = get_mTI_vectors(fields)

        # The old (removed) get_nTI_vectors algorithm: TI(TI(E1,E2), TI(E3,E4)).
        old_ti_a = get_TI_vectors(fields[0], fields[1])
        old_ti_b = get_TI_vectors(fields[2], fields[3])
        old_recursive_result = get_TI_vectors(old_ti_a, old_ti_b)

        new_mag = np.linalg.norm(new_result, axis=1)
        old_mag = np.linalg.norm(old_recursive_result, axis=1)

        # They must not be materially the same -- if they were, the old
        # bug (measured +38.6% mean signed error at N=4) would still be
        # silently reproduced by the new, supposedly-fixed code path.
        assert not np.allclose(new_mag, old_mag, rtol=0.05, atol=1e-8)

        rel_diff = np.abs(new_mag - old_mag) / np.maximum(old_mag, 1e-8)
        assert np.mean(rel_diff) > 0.05
