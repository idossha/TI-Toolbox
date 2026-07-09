"""Numeric tests for the Cassarà carrier safety metrics (tit.fields)."""

import numpy as np
import pytest

from tit.fields import hf_peak, hf_sar


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
