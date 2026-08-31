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
    get_TI_avg,
    get_mTI_vectors,
    get_magnitude_am,
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


# ---------------------------------------------------------------------------
# get_TI_avg -- direction-averaged modulation depth
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetTIAvg:
    @pytest.mark.parametrize("n_pairs", [1, 2, 3])
    def test_avg_never_exceeds_max(self, n_pairs):
        """Key invariant: an average over directions cannot exceed the
        direction maximum (get_mTI_vectors's norm)."""
        fields = _random_fields(2 * n_pairs, n_elements=200)
        avg = get_TI_avg(fields)
        max_mag = np.linalg.norm(get_mTI_vectors(fields), axis=1)
        assert np.all(avg <= max_mag + 1e-9)

    @pytest.mark.parametrize("n_pairs", [1, 2, 3])
    def test_shape_and_nonneg(self, n_pairs):
        n_elements = 40
        fields = _random_fields(2 * n_pairs, n_elements=n_elements)
        avg = get_TI_avg(fields)
        assert avg.shape == (n_elements,)
        assert not np.any(np.isnan(avg))
        assert np.all(avg >= 0.0)

    def test_psi_accepted(self):
        fields = _random_fields(4, n_elements=20)
        avg = get_TI_avg(fields, psi=[0.0, 1.2])
        assert avg.shape == (20,)
        assert not np.any(np.isnan(avg))

    def test_odd_n_raises(self):
        fields = _random_fields(5)
        with pytest.raises(ValueError, match="even number"):
            get_TI_avg(fields)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="even number"):
            get_TI_avg([])

    def test_bad_psi_shape_raises(self):
        fields = _random_fields(4, n_elements=10)
        with pytest.raises(ValueError, match="psi"):
            get_TI_avg(fields, psi=[0.0, 0.0, 0.0])  # K=2, needs shape (2,)


# ---------------------------------------------------------------------------
# get_magnitude_am -- direction-free magnitude envelope
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetMagnitudeAM:
    def test_k1_matches_norm_identity(self):
        """At K=1, get_magnitude_am reduces exactly to
        abs(|E1+E2| - |E1-E2|)."""
        E1, E2 = _random_fields(2, n_elements=300)
        result = get_magnitude_am([E1, E2])
        expected = np.abs(
            np.linalg.norm(E1 + E2, axis=1) - np.linalg.norm(E1 - E2, axis=1)
        )
        np.testing.assert_allclose(result, expected, atol=1e-9)

    def test_k1_differs_materially_from_mti_vectors(self):
        """get_magnitude_am is a genuinely different quantity from the
        direction-maximized modulation depth, not a refinement of it."""
        E1, E2 = _random_fields(2, n_elements=500)
        mag_am = get_magnitude_am([E1, E2])
        ti_mag = np.linalg.norm(get_mTI_vectors([E1, E2]), axis=1)

        rel_diff = np.abs(mag_am - ti_mag) / np.maximum(ti_mag, 1e-8)
        assert np.mean(rel_diff > 0.01) > 0.5

    def test_collinear_fields_all_three_forms_agree(self):
        """For collinear (same-direction) E1, E2 the magnitude-AM envelope,
        the direction-maximized envelope, and 2*min(|E1|,|E2|) all coincide
        -- an identity that holds only in the collinear case."""
        n = 20
        n_hat = np.array([1.0, 0.0, 0.0])
        a = RNG.uniform(0.5, 3.0, size=n)
        b = RNG.uniform(0.5, 3.0, size=n)
        E1 = np.outer(a, n_hat)
        E2 = np.outer(b, n_hat)

        mag_am = get_magnitude_am([E1, E2])
        ti_mag = np.linalg.norm(get_mTI_vectors([E1, E2]), axis=1)
        expected = 2.0 * np.minimum(a, b)

        np.testing.assert_allclose(mag_am, expected, atol=1e-9)
        np.testing.assert_allclose(ti_mag, expected, atol=1e-9)

    @pytest.mark.parametrize("n_fields", [2, 4, 6])
    def test_shape_and_nonneg(self, n_fields):
        n_elements = 30
        fields = _random_fields(n_fields, n_elements=n_elements)
        result = get_magnitude_am(fields)
        assert result.shape == (n_elements,)
        assert np.all(result >= -1e-9)  # tiny round-off only
        assert not np.any(np.isnan(result))

    def test_odd_n_raises(self):
        fields = _random_fields(5)
        with pytest.raises(ValueError, match="even number"):
            get_magnitude_am(fields)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="even number"):
            get_magnitude_am([])


# ---------------------------------------------------------------------------
# get_TI_vectors -- Hirata et al. (2024) sign-agnostic closed form vs. the
# legacy preprocess-then-branch (swap/flip) formulation it replaced
# ---------------------------------------------------------------------------


def _legacy_get_TI_vectors(E1_org, E2_org):
    """Pre-Hirata reference implementation of ``get_TI_vectors``, kept
    verbatim as a test-only equivalence oracle. Orders fields so
    ``|E1| >= |E2|``, flips ``E2`` for an acute angle, then branches on
    ``|E2| <= |E1|*cos(alpha)``."""
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


def _unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


@pytest.mark.unit
class TestHirataFormEquivalence:
    """get_TI_vectors (Hirata et al. 2024 sign-agnostic closed form) must
    match _legacy_get_TI_vectors (Grossman et al. 2017 preprocess-then-branch
    form) exactly -- measured bit-identical (max abs diff 0.0) over 400,000+
    random pairs spanning magnitude scales 1e-4..1e4, including a dense
    near-orthogonal sweep targeting the cancellation regime the sign(dot)
    decision (vs. comparing |E1-E2| to |E1+E2|) is designed to avoid."""

    def test_matches_legacy_random_log_uniform_magnitudes(self):
        rng = np.random.default_rng(12345)
        n = 100_000
        scale1 = 10.0 ** rng.uniform(-4, 4, size=n)
        scale2 = 10.0 ** rng.uniform(-4, 4, size=n)
        dir1 = rng.standard_normal((n, 3))
        dir1 /= np.linalg.norm(dir1, axis=1, keepdims=True)
        dir2 = rng.standard_normal((n, 3))
        dir2 /= np.linalg.norm(dir2, axis=1, keepdims=True)
        E1 = dir1 * scale1[:, None]
        E2 = dir2 * scale2[:, None]

        expected = _legacy_get_TI_vectors(E1, E2)
        result = get_TI_vectors(E1, E2)
        np.testing.assert_allclose(result, expected, atol=0)

    def test_matches_legacy_random_standard_normal(self):
        rng = np.random.default_rng(54321)
        n = 200_000
        E1 = rng.standard_normal((n, 3))
        E2 = rng.standard_normal((n, 3))

        expected = _legacy_get_TI_vectors(E1, E2)
        result = get_TI_vectors(E1, E2)
        np.testing.assert_allclose(result, expected, atol=0)

    def test_matches_legacy_near_orthogonal_cancellation_sweep(self):
        """Dense sweep of near-orthogonal field pairs (dot ~ 0 relative to
        |E1|,|E2|) at mixed magnitude scales -- the regime where comparing
        |E1-E2| to |E1+E2| loses the sign to float64 cancellation and
        deciding from sign(E1.E2) directly is required for equivalence."""
        rng = np.random.default_rng(98765)
        n = 100_000
        mag1 = 10.0 ** rng.uniform(-4, 4, size=n)
        mag2 = 10.0 ** rng.uniform(-4, 4, size=n)
        base = rng.standard_normal((n, 3))
        base /= np.linalg.norm(base, axis=1, keepdims=True)
        perp = rng.standard_normal((n, 3))
        perp -= np.sum(perp * base, axis=1, keepdims=True) * base
        perp /= np.linalg.norm(perp, axis=1, keepdims=True)
        tiny_angle = rng.uniform(-1e-6, 1e-6, size=n)  # radians, near pi/2

        E1 = base * mag1[:, None]
        E2 = (
            perp * np.cos(tiny_angle)[:, None] + base * np.sin(tiny_angle)[:, None]
        ) * mag2[:, None]

        expected = _legacy_get_TI_vectors(E1, E2)
        result = get_TI_vectors(E1, E2)
        np.testing.assert_allclose(result, expected, atol=0)

    @pytest.mark.parametrize(
        "name,E1,E2",
        [
            (
                "collinear_same_direction",
                np.tile(_unit([1.0, 2.0, 3.0]) * 2.0, (10, 1)),
                np.tile(_unit([1.0, 2.0, 3.0]) * 5.0, (10, 1)),
            ),
            (
                "antiparallel",
                np.tile(_unit([1.0, 2.0, 3.0]) * 3.0, (10, 1)),
                np.tile(-_unit([1.0, 2.0, 3.0]) * 7.0, (10, 1)),
            ),
            (
                "exactly_orthogonal",
                np.tile(_unit([1.0, 2.0, 3.0]) * 4.0, (10, 1)),
                np.tile(
                    _unit(
                        np.array([2.0, -1.0, 0.0])
                        - np.dot(_unit([2.0, -1.0, 0.0]), _unit([1.0, 2.0, 3.0]))
                        * _unit([1.0, 2.0, 3.0])
                    )
                    * 6.0,
                    (10, 1),
                ),
            ),
            (
                "zero_both",
                np.zeros((5, 3)),
                np.zeros((5, 3)),
            ),
            (
                "zero_E1",
                np.zeros((5, 3)),
                np.tile([1.0, 2.0, 3.0], (5, 1)),
            ),
            (
                "zero_E2",
                np.tile([1.0, 2.0, 3.0], (5, 1)),
                np.zeros((5, 3)),
            ),
            (
                "identical_fields",
                np.tile([1.0, -2.0, 0.5], (10, 1)),
                np.tile([1.0, -2.0, 0.5], (10, 1)),
            ),
            (
                "vastly_unequal_small_vs_large",
                np.tile(_unit([1.0, 2.0, 3.0]) * 1e-4, (10, 1)),
                np.tile(_unit([2.0, -1.0, 0.0]) * 1e4, (10, 1)),
            ),
            (
                "vastly_unequal_large_vs_small",
                np.tile(_unit([1.0, 2.0, 3.0]) * 1e4, (10, 1)),
                np.tile(_unit([2.0, -1.0, 0.0]) * 1e-4, (10, 1)),
            ),
        ],
    )
    def test_matches_legacy_degenerate_cases(self, name, E1, E2):
        expected = _legacy_get_TI_vectors(E1, E2)
        result = get_TI_vectors(E1, E2)
        np.testing.assert_allclose(result, expected, atol=0)


# ---------------------------------------------------------------------------
# Quadratic-form sweep/refinement regression vs the projection-based original
# ---------------------------------------------------------------------------
#
# ``_mti_modulation_depth_sweep`` evaluates (P, Q) as quadratic forms in
# per-element 3x3 matrices and refines in each seed's local frame (perf
# rewrite for m-ex-search). The reference below is the pre-rewrite
# algorithm verbatim in spirit: explicit per-field projections onto every
# direction, materialised patch directions, ``np.where`` seed masking. The
# two must agree to round-off on random inputs.


def _reference_mti_sweep(fields, psi=None, num_directions=192, refine=True):
    from tit.calc import (
        _REFINE_MIN_SEED_ANGLE_DEG,
        _REFINE_N_ROUNDS,
        _REFINE_N_SEEDS,
        _REFINE_PATCH_SIZE,
        _REFINE_SHRINK,
        _fibonacci_sphere,
    )

    arrs = [np.asarray(f, dtype=np.float64) for f in fields]
    n = arrs[0].shape[0]
    n_pairs = len(arrs) // 2
    directions = _fibonacci_sphere(num_directions)

    def pq(proj):
        P = 0.5 * sum(p * p for p in proj)
        if psi is not None and np.any(np.asarray(psi) != 0.0):
            z = sum(
                proj[2 * k] * proj[2 * k + 1] * np.exp(1j * psi[k]) for k in range(n_pairs)
            )
            return P, np.abs(z)
        return P, np.abs(sum(proj[2 * k] * proj[2 * k + 1] for k in range(n_pairs)))

    def env(P, Q):
        return np.sqrt(2.0 * np.maximum(P + Q, 0.0)) - np.sqrt(2.0 * np.maximum(P - Q, 0.0))

    def patch_dirs(centers, half_angle, n_patch):
        c = centers.reshape(-1, 3)
        ref = np.tile(np.array([1.0, 0.0, 0.0]), (c.shape[0], 1))
        parallel = np.abs(np.sum(c * ref, axis=1)) > 0.99
        ref[parallel] = np.array([0.0, 1.0, 0.0])
        u = np.cross(c, ref)
        u_norm = np.linalg.norm(u, axis=1, keepdims=True)
        u_norm[u_norm == 0.0] = 1.0
        u /= u_norm
        v = np.cross(c, u)
        j = np.arange(n_patch, dtype=np.float64)
        golden = np.pi * (3.0 - np.sqrt(5.0))
        r = half_angle * np.sqrt((j + 0.5) / n_patch)
        phi = golden * j
        patch = (
            c[:, None, :] * np.cos(r)[None, :, None]
            + u[:, None, :] * (np.sin(r) * np.cos(phi))[None, :, None]
            + v[:, None, :] * (np.sin(r) * np.sin(phi))[None, :, None]
        )
        return patch.reshape(*centers.shape[:-1], n_patch, 3)

    P, Q = pq([a @ directions.T for a in arrs])
    amp = env(P, Q)
    if not refine:
        idx = np.argmax(amp, axis=1)
        rows = np.arange(n)
        return amp[rows, idx], directions[idx]

    n_seeds = min(_REFINE_N_SEEDS, num_directions)
    min_cos = np.cos(np.radians(_REFINE_MIN_SEED_ANGLE_DEG))
    remaining = amp.copy()
    top = np.zeros((n, n_seeds), dtype=int)
    for s in range(n_seeds):
        idx = np.argmax(remaining, axis=1)
        top[:, s] = idx
        cos_to = (directions @ directions[idx].T).T
        remaining = np.where(cos_to > min_cos, -np.inf, remaining)

    best_dir = directions[top]
    best_md = np.take_along_axis(amp, top, axis=1)
    half_angle = 2.0 / np.sqrt(num_directions)
    rows = np.arange(n)[:, None, None]
    cols = np.arange(n_seeds)[None, :, None]
    for _ in range(_REFINE_N_ROUNDS):
        patch = patch_dirs(best_dir, half_angle, _REFINE_PATCH_SIZE)
        Pc, Qc = pq([np.einsum("nd,nspd->nsp", a, patch) for a in arrs])
        ampc = env(Pc, Qc)
        idx = np.argmax(ampc, axis=2)
        cand_md = np.take_along_axis(ampc, idx[:, :, None], axis=2)[:, :, 0]
        cand_dir = patch[rows, cols, idx[:, :, None], :][:, :, 0, :]
        improved = cand_md > best_md
        best_md = np.where(improved, cand_md, best_md)
        best_dir = np.where(improved[:, :, None], cand_dir, best_dir)
        half_angle *= _REFINE_SHRINK

    best_seed = np.argmax(best_md, axis=1)
    return best_md[np.arange(n), best_seed], best_dir[np.arange(n), best_seed]


@pytest.mark.unit
class TestQuadraticFormSweepRegression:
    @pytest.mark.parametrize("n_fields", [4, 6, 8])
    def test_refined_envelope_matches_projection_reference(self, n_fields):
        rng = np.random.default_rng(1234 + n_fields)
        # Realistic magnitudes: leadfield fields are ~0.05-0.5 V/m.
        fields = [
            rng.standard_normal((400, 3)) * rng.uniform(0.05, 0.5)
            for _ in range(n_fields)
        ]
        ref_md, ref_dir = _reference_mti_sweep(fields)
        vec = get_mTI_vectors(fields)
        np.testing.assert_allclose(np.linalg.norm(vec, axis=1), ref_md, rtol=0, atol=1e-9)
        np.testing.assert_allclose(vec, ref_dir * ref_md[:, None], rtol=0, atol=1e-9)

    def test_phase_offsets_match_projection_reference(self):
        rng = np.random.default_rng(99)
        fields = [rng.standard_normal((300, 3)) * 0.3 for _ in range(6)]
        psi = np.array([0.0, 0.7, -2.1])
        ref_md, _ = _reference_mti_sweep(fields, psi=psi)
        result = _mti_modulation_depth(fields, psi=psi)
        np.testing.assert_allclose(result["md"], ref_md, rtol=0, atol=1e-9)

    def test_coarse_sweep_matches_projection_reference(self):
        rng = np.random.default_rng(5)
        fields = [rng.standard_normal((500, 3)) for _ in range(4)]
        ref_md, ref_dir = _reference_mti_sweep(fields, refine=False)
        result = _mti_modulation_depth(fields, refine=False)
        np.testing.assert_allclose(result["md"], ref_md, rtol=0, atol=1e-9)
        np.testing.assert_array_equal(result["best_direction"], ref_dir)

    def test_ti_avg_matches_projection_reference(self):
        from tit.calc import _fibonacci_sphere

        rng = np.random.default_rng(11)
        fields = [rng.standard_normal((200, 3)) for _ in range(4)]
        arrs = [np.asarray(f) for f in fields]
        dirs = _fibonacci_sphere(192)
        proj = [a @ dirs.T for a in arrs]
        P = 0.5 * sum(p * p for p in proj)
        Q = np.abs(proj[0] * proj[1] + proj[2] * proj[3])
        amp = np.sqrt(2.0 * np.maximum(P + Q, 0.0)) - np.sqrt(2.0 * np.maximum(P - Q, 0.0))
        np.testing.assert_allclose(get_TI_avg(fields), amp.mean(axis=1), rtol=0, atol=1e-9)


@pytest.mark.unit
class TestGetMTIDir:
    """get_mTI_dir -- the public fixed-direction envelope backing mTI's TI_normal."""

    def test_matches_best_direction_envelope(self):
        """Evaluating at get_mTI_vectors' own best directions reproduces the
        maximized modulation depth (up to refinement round-off)."""
        from tit.calc import get_mTI_dir, _mti_modulation_depth

        rng = np.random.default_rng(7)
        fields = [rng.standard_normal((300, 3)) for _ in range(4)]
        best = _mti_modulation_depth(fields)
        md = get_mTI_dir(fields, best["best_direction"])
        np.testing.assert_allclose(md, best["md"], rtol=0, atol=1e-9)

    def test_never_exceeds_maximized_envelope(self):
        from tit.calc import get_mTI_dir, get_mTI_vectors

        rng = np.random.default_rng(8)
        fields = [rng.standard_normal((300, 3)) for _ in range(4)]
        md_max = np.linalg.norm(get_mTI_vectors(fields), axis=1)
        dirs = rng.standard_normal((300, 3))
        assert np.all(get_mTI_dir(fields, dirs) <= md_max + 1e-6)

    def test_k1_colinear_along_field_axis(self):
        """One carrier, colinear equal fields, evaluated along that axis:
        MD = 2*min(|E1|,|E2|) exactly (Grossman 2017)."""
        from tit.calc import get_mTI_dir

        e = np.array([[0.5, 0.0, 0.0]])
        md = get_mTI_dir([e, e], np.array([[1.0, 0.0, 0.0]]))
        np.testing.assert_allclose(md, [1.0], atol=1e-12)

    def test_direction_shape_mismatch_raises(self):
        from tit.calc import get_mTI_dir

        fields = [np.zeros((5, 3)) for _ in range(4)]
        with pytest.raises(ValueError, match="directions"):
            get_mTI_dir(fields, np.zeros((4, 3)))
