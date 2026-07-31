"""Numeric tests for the Cassarà carrier safety metrics (tit.fields)."""

import itertools

import numpy as np
import pytest

import tit.fields as fields_module
from tit.fields import EXACT_SIGN_ENUM_MAX_FIELDS, hf_peak, hf_sar


def _brute_force_peak(*fields):
    """Reference max-over-signs peak via a plain Python loop (no chunking/BLAS)."""
    n = len(fields)
    arrays = [np.asarray(f, dtype=float) for f in fields]
    m = arrays[0].shape[0]
    best = np.zeros(m)
    for signs in itertools.product((1.0, -1.0), repeat=n - 1):
        signs = (1.0,) + signs
        total = np.zeros_like(arrays[0])
        for s, a in zip(signs, arrays):
            total = total + s * a
        best = np.maximum(best, np.linalg.norm(total, axis=-1))
    return best


class TestHfPeak:
    """hf_peak = max(|E1+E2|, |E1-E2|) — the true peak carrier field."""

    def test_parallel_aligned(self):
        # aligned same direction: |E1+E2| = |E1|+|E2| dominates
        e1 = np.array([[1.0, 0, 0]])
        e2 = np.array([[0.5, 0, 0]])
        assert hf_peak(e1, e2)[0] == pytest.approx(1.5)

    def test_antiparallel_uses_difference(self):
        # opposed: |E1+E2| = 0.5 but |E1-E2| = 1.5 -> the max captures the real peak
        e1 = np.array([[1.0, 0, 0]])
        e2 = np.array([[-0.5, 0, 0]])
        assert hf_peak(e1, e2)[0] == pytest.approx(1.5)

    def test_orthogonal(self):
        e1 = np.array([[1.0, 0, 0]])
        e2 = np.array([[0.0, 1.0, 0]])
        assert hf_peak(e1, e2)[0] == pytest.approx(np.sqrt(2))

    def test_bounded_by_magnitude_and_amplitude_sum(self):
        # |E1+E2| <= hf_peak <= |E1|+|E2| for arbitrary fields
        rng = np.random.default_rng(0)
        e1 = rng.normal(size=(200, 3))
        e2 = rng.normal(size=(200, 3))
        peak = hf_peak(e1, e2)
        assert np.all(peak >= np.linalg.norm(e1 + e2, axis=1) - 1e-9)
        assert np.all(
            peak <= np.linalg.norm(e1, axis=1) + np.linalg.norm(e2, axis=1) + 1e-9
        )

    def test_n2_bit_identical_to_old_formula(self):
        # Critical regression guard: the new N-field implementation must match
        # the original max(|E1+E2|, |E1-E2|) EXACTLY (atol=0), not just approximately.
        rng = np.random.default_rng(42)
        for _ in range(10):
            e1 = rng.normal(size=(500, 3))
            e2 = rng.normal(size=(500, 3))
            old = np.maximum(
                np.linalg.norm(e1 + e2, axis=-1), np.linalg.norm(e1 - e2, axis=-1)
            )
            new = hf_peak(e1, e2)
            np.testing.assert_array_equal(old, new)

    def test_adversarial_near_antiparallel(self):
        # Near-cancellation must not be mistaken for the peak: the real peak
        # is on the DIFFERENCE side (~1.999), not the near-zero sum side.
        e1 = np.array([[1.0, 0, 0]])
        e2 = np.array([[-0.999, 0, 0]])
        result = hf_peak(e1, e2)[0]
        assert result == pytest.approx(1.999, abs=1e-9)
        assert result > 1.0  # sanity: not the near-zero |E1+E2| = 0.001

    @pytest.mark.parametrize("n", [3, 4, 5, 6])
    def test_exact_enumeration_matches_brute_force(self, n):
        rng = np.random.default_rng(100 + n)
        fields = [rng.normal(size=(50, 3)) for _ in range(n)]
        expected = _brute_force_peak(*fields)
        result = hf_peak(*fields)
        np.testing.assert_allclose(result, expected, atol=1e-12)

    def test_exact_path_used_at_threshold(self):
        assert EXACT_SIGN_ENUM_MAX_FIELDS >= 8
        rng = np.random.default_rng(8)
        n = EXACT_SIGN_ENUM_MAX_FIELDS
        fields = [rng.normal(size=(30, 3)) for _ in range(n)]
        expected = _brute_force_peak(*fields)
        result = hf_peak(*fields)
        np.testing.assert_allclose(result, expected, atol=1e-12)

    def test_sweep_agrees_with_exact_near_threshold(self):
        # One field above the exact threshold: the sweep (lower bound) must
        # stay close to the exact brute-force reference.
        rng = np.random.default_rng(9)
        n = EXACT_SIGN_ENUM_MAX_FIELDS + 1
        fields = [rng.normal(size=(200, 3)) for _ in range(n)]
        exact = _brute_force_peak(*fields)
        swept = hf_peak(*fields)
        assert np.all(swept <= exact + 1e-9)  # sweep never overestimates
        rel_err = np.abs(swept - exact) / np.maximum(exact, 1e-9)
        assert rel_err.max() < 0.01  # within 1% of the true peak

    def test_sweep_at_least_as_tight_as_raw_support(self):
        # hf_peak's sign-refined estimate evaluates an actually-realizable
        # field state (a real sign combination), so by Cauchy-Schwarz it must
        # be >= the raw support-function value at the same sampled direction
        # (a mere projection sum_i |E_i . n*|).
        rng = np.random.default_rng(11)
        n = EXACT_SIGN_ENUM_MAX_FIELDS + 2
        m = 100
        fields = [rng.normal(size=(m, 3)) for _ in range(n)]
        directions = fields_module._fibonacci_directions(
            fields_module._SWEEP_N_DIRECTIONS
        )
        support_per_dir = np.zeros((m, directions.shape[0]))
        for f in fields:
            support_per_dir += np.abs(np.asarray(f, dtype=float) @ directions.T)
        raw_support = support_per_dir.max(axis=1)

        refined = hf_peak(*fields)
        assert np.all(refined >= raw_support - 1e-9)

    def test_sweep_matches_exact_on_random_trials(self):
        # The sign-refined sweep should recover the exact sign-enumeration
        # answer (or come very close) on typical inputs, well above N=8.
        for n in (10, 12):
            rng = np.random.default_rng(2000 + n)
            fields = [rng.normal(size=(30, 3)) for _ in range(n)]
            exact = _brute_force_peak(*fields)
            refined = hf_peak(*fields)
            assert np.all(refined <= exact + 1e-9)  # never overestimates
            np.testing.assert_allclose(refined, exact, atol=0.05, rtol=0)

    def test_chunking_matches_unchunked_reference(self):
        # Exercise the chunk boundary (element count not a multiple of the
        # internal chunk size) and confirm results are unaffected.
        rng = np.random.default_rng(7)
        e1 = rng.normal(size=(50123, 3))
        e2 = rng.normal(size=(50123, 3))
        old = np.maximum(
            np.linalg.norm(e1 + e2, axis=-1), np.linalg.norm(e1 - e2, axis=-1)
        )
        np.testing.assert_array_equal(old, hf_peak(e1, e2))

    def test_zero_fields(self):
        z = np.zeros((3, 3))
        np.testing.assert_array_equal(hf_peak(z, z), np.zeros(3))

    def test_identical_fields(self):
        e = np.array([[1.0, 2.0, 2.0]])  # |e| = 3
        # max(|e+e|, |e-e|) = |2e| = 6
        assert hf_peak(e, e)[0] == pytest.approx(6.0)

    def test_preserves_input_shape(self):
        rng = np.random.default_rng(3)
        e1 = rng.normal(size=(4, 5, 3))
        e2 = rng.normal(size=(4, 5, 3))
        assert hf_peak(e1, e2).shape == (4, 5)

    def test_requires_at_least_two_fields(self):
        with pytest.raises(ValueError):
            hf_peak(np.zeros((5, 3)))

    def test_requires_matching_shapes(self):
        with pytest.raises(ValueError):
            hf_peak(np.zeros((5, 3)), np.zeros((6, 3)))

    def test_requires_last_axis_three(self):
        with pytest.raises(ValueError):
            hf_peak(np.zeros((5, 2)), np.zeros((5, 2)))


class TestHfSar:
    """hf_sar = |E1|^2 + |E2|^2 — heating driver (incoherent, angle-independent)."""

    def test_sum_of_squares(self):
        e1 = np.array([[3.0, 0, 0]])
        e2 = np.array([[0.0, 4.0, 0]])
        assert hf_sar(e1, e2)[0] == pytest.approx(25.0)

    def test_independent_of_relative_orientation(self):
        e1 = np.array([[1.0, 0, 0]])
        for e2 in (
            np.array([[1.0, 0, 0]]),
            np.array([[-1.0, 0, 0]]),
            np.array([[0.0, 1.0, 0]]),
        ):
            assert hf_sar(e1, e2)[0] == pytest.approx(2.0)

    def test_not_equal_to_amplitude_sum_squared(self):
        # Cassarà: heating ∝ |E1|^2+|E2|^2, NOT (|E1|+|E2|)^2 (over-estimates up to 2x)
        e1 = np.array([[1.0, 0, 0]])
        e2 = np.array([[1.0, 0, 0]])
        assert hf_sar(e1, e2)[0] == pytest.approx(2.0)
        amp_sum_sq = (np.linalg.norm(e1) + np.linalg.norm(e2)) ** 2
        assert amp_sum_sq == pytest.approx(4.0)  # the over-estimate we avoid

    def test_n_field_sum(self):
        # sum_i |E_i|^2 over N=4 fields, each unit magnitude along an axis
        fields = [
            np.array([[1.0, 0, 0]]),
            np.array([[0.0, 1.0, 0]]),
            np.array([[0.0, 0.0, 1.0]]),
            np.array([[1.0, 1.0, 1.0]]),
        ]
        assert hf_sar(*fields)[0] == pytest.approx(1 + 1 + 1 + 3)

    def test_zero_fields(self):
        z = np.zeros((3, 3))
        np.testing.assert_array_equal(hf_sar(z, z), np.zeros(3))

    def test_identical_fields(self):
        e = np.array([[1.0, 2.0, 2.0]])  # |e|^2 = 9
        assert hf_sar(e, e)[0] == pytest.approx(18.0)

    def test_preserves_input_shape(self):
        rng = np.random.default_rng(4)
        fields = [rng.normal(size=(4, 5, 3)) for _ in range(3)]
        assert hf_sar(*fields).shape == (4, 5)

    def test_requires_at_least_two_fields(self):
        with pytest.raises(ValueError):
            hf_sar(np.zeros((5, 3)))

    def test_requires_matching_shapes(self):
        with pytest.raises(ValueError):
            hf_sar(np.zeros((5, 3)), np.zeros((6, 3)))
