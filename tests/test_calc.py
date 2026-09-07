#!/usr/bin/env simnibs_python
"""
Unit tests for tit/calc.py — TI vector math (core physics).

Tests the Grossman et al. 2017 TI algorithm including:
- get_TI_vectors: two-field temporal interference
- get_TI_vectors: modulation-amplitude vectors for K >= 1 carriers

See tests/test_calc_mti.py for coverage of the N>2 modulation-depth
envelope (_mti_modulation_depth) that backs get_TI_vectors at K >= 2.
"""

import sys
import pytest
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.calc import get_TI_vectors

RNG = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parallel_fields():
    """Two fields pointing in the same direction (regime 1)."""
    E1 = np.array([[2.0, 0.0, 0.0]])
    E2 = np.array([[1.0, 0.0, 0.0]])
    return E1, E2


@pytest.fixture
def antiparallel_fields():
    """Two fields pointing in opposite directions (flip then regime 1)."""
    E1 = np.array([[2.0, 0.0, 0.0]])
    E2 = np.array([[-1.0, 0.0, 0.0]])
    return E1, E2


@pytest.fixture
def perpendicular_fields():
    """Two orthogonal fields of equal magnitude (regime 2)."""
    E1 = np.array([[1.0, 0.0, 0.0]])
    E2 = np.array([[0.0, 1.0, 0.0]])
    return E1, E2


@pytest.fixture
def multi_element():
    """Array with multiple spatial points."""
    E1 = np.array(
        [
            [2.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
        ]
    )
    E2 = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )
    return E1, E2


# ---------------------------------------------------------------------------
# get_TI_vectors — Regime 1 (parallel alignment)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTIVectorsRegime1:
    """Tests for get_TI_vectors in regime 1 (|E2| <= |E1|*cos(alpha))."""

    def test_parallel_same_direction(self, parallel_fields):
        E1, E2 = parallel_fields
        result = get_TI_vectors([E1, E2])
        # cos(alpha) = 1, |E2|=1 <= |E1|*1=2 -> regime 1 -> TI = 2*E2
        np.testing.assert_allclose(result, 2.0 * E2)

    def test_antiparallel_flips_to_regime1(self, antiparallel_fields):
        E1, E2 = antiparallel_fields
        result = get_TI_vectors([E1, E2])
        # E2 is flipped to [1,0,0], then regime 1 -> TI = 2*[1,0,0]
        np.testing.assert_allclose(result, np.array([[2.0, 0.0, 0.0]]))

    def test_collinear_equal_magnitude(self):
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        # Same direction, equal magnitude, cos(alpha)=1
        # |E2|=1 <= |E1|*1=1 -> regime 1 -> TI = 2*E2
        np.testing.assert_allclose(result, np.array([[2.0, 0.0, 0.0]]))

    def test_small_e2_along_e1(self):
        E1 = np.array([[5.0, 0.0, 0.0]])
        E2 = np.array([[0.5, 0.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        np.testing.assert_allclose(result, np.array([[1.0, 0.0, 0.0]]))

    def test_parallel_3d_direction(self):
        direction = np.array([[1.0, 1.0, 1.0]]) / np.sqrt(3)
        E1 = 3.0 * direction
        E2 = 1.0 * direction
        result = get_TI_vectors([E1, E2])
        np.testing.assert_allclose(result, 2.0 * E2, atol=1e-12)

    def test_parallel_multi_element(self):
        E1 = np.array([[2.0, 0.0, 0.0], [0.0, 3.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        np.testing.assert_allclose(result, 2.0 * E2)


# ---------------------------------------------------------------------------
# get_TI_vectors — Regime 2 (oblique configuration)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTIVectorsRegime2:
    """Tests for get_TI_vectors in regime 2 (|E2| > |E1|*cos(alpha))."""

    def test_perpendicular_equal_magnitude(self, perpendicular_fields):
        E1, E2 = perpendicular_fields
        result = get_TI_vectors([E1, E2])
        # cos(alpha) = 0, so |E2| > |E1|*0 -> regime 2
        # h = E1 - E2 = [1,-1,0], e_h = [1,-1,0]/sqrt(2)
        # E2_parallel = (E2 . e_h) * e_h = (-1/sqrt(2)) * [1,-1,0]/sqrt(2) = [-0.5, 0.5, 0]
        # E2_perp = [0,1,0] - [-0.5,0.5,0] = [0.5, 0.5, 0]
        # TI = 2 * E2_perp = [1, 1, 0]
        np.testing.assert_allclose(result, np.array([[1.0, 1.0, 0.0]]), atol=1e-12)

    def test_perpendicular_unequal_magnitude(self):
        E1 = np.array([[2.0, 0.0, 0.0]])
        E2 = np.array([[0.0, 3.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        # |E2|=3 > |E1|=2 -> swap: E1=[0,3,0], E2=[2,0,0]
        # cos(alpha)=0, |E2|=2 > 0 -> regime 2
        # h = [0,3,0]-[2,0,0] = [-2,3,0], |h|=sqrt(13)
        # e_h = [-2,3,0]/sqrt(13)
        # E2_parallel = (E2.e_h)*e_h = (2*(-2)/sqrt(13)) * [-2,3,0]/sqrt(13)
        #             = (-4/13)*[-2,3,0] = [8/13, -12/13, 0]
        # E2_perp = [2,0,0] - [8/13, -12/13, 0] = [18/13, 12/13, 0]
        # TI = 2*E2_perp = [36/13, 24/13, 0]
        expected = np.array([[36.0 / 13, 24.0 / 13, 0.0]])
        np.testing.assert_allclose(result, expected, atol=1e-12)

    def test_perpendicular_magnitude_check(self, perpendicular_fields):
        E1, E2 = perpendicular_fields
        result = get_TI_vectors([E1, E2])
        # For perpendicular equal-magnitude fields, |TI| = sqrt(2)*|E|
        expected_mag = np.sqrt(2)
        np.testing.assert_allclose(
            np.linalg.norm(result, axis=1), [expected_mag], atol=1e-12
        )

    def test_45_degree_angle_boundary(self):
        # E1=[1,0,0], E2=[1,1,0] -> |E2|=sqrt(2) > |E1|=1 -> swap
        # After swap: E1=[1,1,0], E2=[1,0,0]
        # cos(alpha) = dot/norms = 1/sqrt(2), |E1|*cos = sqrt(2)*1/sqrt(2) = 1
        # |E2|=1 <= 1 -> regime 1 -> TI = 2*E2 = [2,0,0]
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[1.0, 1.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        np.testing.assert_allclose(result, np.array([[2.0, 0.0, 0.0]]), atol=1e-12)


# ---------------------------------------------------------------------------
# get_TI_vectors — Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTIVectorsEdgeCases:
    """Edge cases and input validation for get_TI_vectors."""

    def test_zero_e2(self):
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[0.0, 0.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        np.testing.assert_allclose(result, np.zeros((1, 3)))

    def test_zero_e1(self):
        E1 = np.array([[0.0, 0.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        # |E2|>|E1| -> swap: E1=[1,0,0], E2=[0,0,0]
        np.testing.assert_allclose(result, np.zeros((1, 3)))

    def test_both_zero(self):
        E1 = np.zeros((1, 3))
        E2 = np.zeros((1, 3))
        result = get_TI_vectors([E1, E2])
        np.testing.assert_allclose(result, np.zeros((1, 3)))

    def test_magnitude_ordering_swap(self):
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[3.0, 0.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        # |E2|>|E1| -> swap. After swap E1=[3,0,0], E2=[1,0,0]
        # regime 1 -> TI = 2*[1,0,0]
        np.testing.assert_allclose(result, np.array([[2.0, 0.0, 0.0]]))

    def test_single_element_array(self):
        E1 = np.array([[1.0, 2.0, 3.0]])
        E2 = np.array([[0.1, 0.0, 0.0]])
        result = get_TI_vectors([E1, E2])
        assert result.shape == (1, 3)

    def test_multi_element_array(self, multi_element):
        E1, E2 = multi_element
        result = get_TI_vectors([E1, E2])
        assert result.shape == (3, 3)

    def test_large_array(self):
        E1 = RNG.standard_normal((1000, 3))
        E2 = RNG.standard_normal((1000, 3))
        result = get_TI_vectors([E1, E2])
        assert result.shape == (1000, 3)
        assert not np.any(np.isnan(result))

    def test_shape_mismatch_raises(self):
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        with pytest.raises(ValueError, match="identical shape"):
            get_TI_vectors([E1, E2])

    def test_wrong_dimension_raises(self):
        E1 = np.array([[1.0, 0.0]])
        E2 = np.array([[1.0, 0.0]])
        with pytest.raises(ValueError, match=r"shape \(N, 3\)"):
            get_TI_vectors([E1, E2])

    def test_does_not_modify_input(self):
        E1 = np.array([[2.0, 0.0, 0.0]])
        E2 = np.array([[-3.0, 0.0, 0.0]])
        E1_copy = E1.copy()
        E2_copy = E2.copy()
        get_TI_vectors([E1, E2])
        np.testing.assert_array_equal(E1, E1_copy)
        np.testing.assert_array_equal(E2, E2_copy)

    def test_ti_magnitude_bounded_by_twice_min(self):
        """TI magnitude should never exceed 2*min(|E1|, |E2|)."""
        for _ in range(50):
            E1 = RNG.standard_normal((10, 3))
            E2 = RNG.standard_normal((10, 3))
            result = get_TI_vectors([E1, E2])
            ti_mag = np.linalg.norm(result, axis=1)
            min_mag = np.minimum(np.linalg.norm(E1, axis=1), np.linalg.norm(E2, axis=1))
            np.testing.assert_array_less(ti_mag, 2.0 * min_mag + 1e-10)

    def test_result_non_negative_magnitude(self):
        """TI magnitude should always be non-negative."""
        E1 = RNG.standard_normal((100, 3))
        E2 = RNG.standard_normal((100, 3))
        result = get_TI_vectors([E1, E2])
        magnitudes = np.linalg.norm(result, axis=1)
        assert np.all(magnitudes >= 0)

    def test_no_nans_for_random_inputs(self):
        E1 = RNG.standard_normal((200, 3))
        E2 = RNG.standard_normal((200, 3))
        result = get_TI_vectors([E1, E2])
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))


# ---------------------------------------------------------------------------
# get_TI_vectors — Known analytical solutions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTIVectorsAnalytical:
    """Analytical solutions for simple known geometries."""

    def test_identical_fields_give_2x(self):
        """Identical fields -> regime 1 -> TI = 2*E."""
        E = RNG.standard_normal((5, 3))
        result = get_TI_vectors([E, E.copy()])
        np.testing.assert_allclose(result, 2.0 * E, atol=1e-12)

    def test_opposite_fields_give_2x(self):
        """Opposite fields -> flip -> identical -> TI = 2*|E|."""
        E = RNG.standard_normal((5, 3))
        result = get_TI_vectors([E, -E])
        np.testing.assert_allclose(result, 2.0 * E, atol=1e-12)

    def test_perpendicular_equal_magnitude_analytical(self):
        """For perpendicular equal-magnitude fields, TI magnitude = sqrt(2)*|E|."""
        mag = 2.0
        E1 = np.array([[mag, 0.0, 0.0]])
        E2 = np.array([[0.0, mag, 0.0]])
        result = get_TI_vectors([E1, E2])
        expected_mag = mag * np.sqrt(2)
        np.testing.assert_allclose(
            np.linalg.norm(result, axis=1), [expected_mag], atol=1e-12
        )

    def test_symmetry_e1_e2_swap_magnitude(self):
        """TI(E1, E2) magnitude equals TI(E2, E1) magnitude."""
        for _ in range(20):
            E1 = RNG.standard_normal((5, 3))
            E2 = RNG.standard_normal((5, 3))
            r1 = get_TI_vectors([E1, E2])
            r2 = get_TI_vectors([E2, E1])
            np.testing.assert_allclose(
                np.linalg.norm(r1, axis=1),
                np.linalg.norm(r2, axis=1),
                atol=1e-12,
            )

    def test_scaling_property(self):
        """Scaling both fields by k should scale TI by k."""
        E1 = RNG.standard_normal((10, 3))
        E2 = RNG.standard_normal((10, 3))
        k = 3.7
        r_base = get_TI_vectors([E1, E2])
        r_scaled = get_TI_vectors([k * E1, k * E2])
        np.testing.assert_allclose(r_scaled, k * r_base, atol=1e-10)

    def test_mixed_regimes_per_element(self, multi_element):
        """Multi-element array where different elements hit different regimes."""
        E1, E2 = multi_element
        result = get_TI_vectors([E1, E2])
        assert result.shape == (3, 3)
        # Element 0: parallel -> regime 1 -> TI = 2*E2 = [2,0,0]
        np.testing.assert_allclose(result[0], [2.0, 0.0, 0.0], atol=1e-12)
        # Element 1: perpendicular equal mag -> regime 2
        assert np.linalg.norm(result[1]) > 0
        # Element 2: |E1|=3 along y, |E2|=1 along y -> parallel regime 1
        np.testing.assert_allclose(result[2], [0.0, 2.0, 0.0], atol=1e-12)


# ---------------------------------------------------------------------------
# get_TI_vectors, K >= 2
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMTIVectors:
    """Tests for the K >= 2 (multi-carrier) path of get_TI_vectors.

    Deep numerical verification of the K>=2 envelope (_mti_modulation_depth)
    lives in tests/test_calc_mti.py; this class covers the K >= 2 path's
    own contract: N=2 dispatch, shape, and input validation.
    """

    def test_mti_shape_validation_wrong_dim(self):
        bad = np.array([[1.0, 2.0]])  # (1, 2) not (N, 3)
        ok = np.array([[1.0, 2.0, 3.0]])
        with pytest.raises(ValueError, match="must have shape"):
            get_TI_vectors([bad, ok, ok, ok])

    def test_mti_shape_validation_1d(self):
        bad = np.array([1.0, 2.0, 3.0])  # 1D not 2D
        ok = np.array([[1.0, 2.0, 3.0]])
        with pytest.raises(ValueError, match="must have shape"):
            get_TI_vectors([bad, ok, ok, ok])

    def test_mti_shape_mismatch(self):
        E1 = np.ones((5, 3))
        E2 = np.ones((5, 3))
        E3 = np.ones((3, 3))
        E4 = np.ones((3, 3))
        with pytest.raises(ValueError, match="identical shape"):
            get_TI_vectors([E1, E2, E3, E4])

    def test_mti_output_shape(self):
        n = 15
        fields = [RNG.standard_normal((n, 3)) for _ in range(4)]
        result = get_TI_vectors(fields)
        assert result.shape == (n, 3)

    def test_mti_all_zeros(self):
        z = np.zeros((5, 3))
        result = get_TI_vectors([z, z, z, z])
        np.testing.assert_allclose(result, np.zeros((5, 3)))

    def test_mti_with_one_zero_pair(self):
        E1 = np.array([[1.0, 0.0, 0.0]])
        E2 = np.array([[0.5, 0.0, 0.0]])
        z = np.zeros((1, 3))
        result = get_TI_vectors([E1, E2, z, z])
        assert result.shape == (1, 3)
        assert not np.any(np.isnan(result))

    def test_mti_no_nans(self):
        for _ in range(20):
            fields = [RNG.standard_normal((10, 3)) for _ in range(4)]
            result = get_TI_vectors(fields)
            assert not np.any(np.isnan(result))
            assert not np.any(np.isinf(result))
