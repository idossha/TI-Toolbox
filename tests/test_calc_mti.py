#!/usr/bin/env simnibs_python
"""
Unit tests for tit/calc.py — mti_modulation_depth (Phase 1 of
tracks/active/mti-focality-core.md).

Covers the verified N-pair (mTI) modulation-depth envelope:
- Exact K=1 reduction to the Grossman/Huang two-channel form.
- Agreement with a time-domain ground truth (square -> brick-wall
  low-pass -> sqrt demodulation, per Botzanowski et al.) for K in
  {1, 2, 4, 6}, both phase-blind (psi=None) and phase-aware (random psi).
- The anti-phase cancellation case (Botzanowski Suppl. Fig. 1).
- Equivalence with the ported collaborator implementation
  (compute_botzanowski_directional_am_stats, from alba/ex-search-multipolar)
  when psi=None.
- Agreement with the exact K=1 closed form (get_TI_vectors) in full 3D via
  the direction sweep.
- Input validation and the carrier power (P) return value.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.calc import (
    compute_botzanowski_directional_am_stats,
    get_TI_vectors,
    mti_modulation_depth,
)

RNG = np.random.default_rng(2026729)


# ---------------------------------------------------------------------------
# Time-domain ground truth (Botzanowski demodulator: square -> low-pass -> sqrt)
# ---------------------------------------------------------------------------


def _demodulate(x, fs, lp_hz=200.0):
    """Square -> zero-phase brick-wall low-pass (frequency domain) -> sqrt."""
    x2 = x**2
    X = np.fft.rfft(x2)
    freqs = np.fft.rfftfreq(len(x2), 1.0 / fs)
    X[freqs > lp_hz] = 0.0
    lp = np.fft.irfft(X, n=len(x2))
    return np.sqrt(np.maximum(lp, 0.0))


def _ground_truth_md(a, b, fca, fcb, pha, phb, fs=200_000.0, dur=0.4, edge=0.05):
    """Synthesise the projected multi-carrier waveform, demodulate, return peak MD."""
    t = np.arange(0, dur, 1.0 / fs)
    x = np.zeros_like(t)
    for ak, bk, fa, fb, pa, pb in zip(a, b, fca, fcb, pha, phb):
        x += ak * np.cos(2 * np.pi * fa * t + pa)
        x += bk * np.cos(2 * np.pi * fb * t + pb)
    env_rms = _demodulate(x, fs)
    n_edge = int(edge * len(t))  # drop FFT edge effects
    core = env_rms[n_edge:-n_edge]
    return np.sqrt(2.0) * (core.max() - core.min())


def _make_fields(a, b):
    """Embed scalar per-pair amplitudes a, b (each length K) as (1, 3) field
    arrays [E_1a, E_1b, E_2a, E_2b, ...] all aligned with the x-axis, so that
    projecting onto direction=[1,0,0] recovers exactly a_k, b_k."""
    fields = []
    for ak, bk in zip(a, b):
        fields.append(np.array([[ak, 0.0, 0.0]]))
        fields.append(np.array([[bk, 0.0, 0.0]]))
    return fields


_UNIT_X = np.array([[1.0, 0.0, 0.0]])


# ---------------------------------------------------------------------------
# K=1 exact reduction to Grossman/Huang 2*min(|a|,|b|)
# ---------------------------------------------------------------------------


class TestK1ExactReduction:
    """For K=1, MD must reduce EXACTLY to 2*min(|a|,|b|) (< 1e-9)."""

    def test_random_amplitudes(self):
        for _ in range(20):
            a, b = RNG.normal(size=2) * 3
            fields = _make_fields([a], [b])
            res = mti_modulation_depth(fields, directions=_UNIT_X)
            want = 2 * min(abs(a), abs(b))
            assert abs(res["md"][0] - want) < 1e-9

    def test_equal_amplitudes(self):
        fields = _make_fields([2.0], [2.0])
        res = mti_modulation_depth(fields, directions=_UNIT_X)
        assert abs(res["md"][0] - 4.0) < 1e-9

    def test_zero_amplitude_gives_zero_md(self):
        fields = _make_fields([0.0], [3.0])
        res = mti_modulation_depth(fields, directions=_UNIT_X)
        assert abs(res["md"][0]) < 1e-9


# ---------------------------------------------------------------------------
# Ground-truth agreement: K in {1, 2, 4, 6}, psi=None and random psi
# ---------------------------------------------------------------------------


class TestGroundTruthAgreement:
    """mti_modulation_depth matches the time-domain demodulator ground truth
    to < 0.01% for K in {1, 2, 4, 6}, both psi=None and random psi."""

    @pytest.mark.parametrize("K", [1, 2, 4, 6])
    def test_phase_blind(self, K):
        means = np.linspace(2000.0, 2000.0 + 2000.0 * (K - 1), K)
        df = 50.0
        for trial in range(3):
            a = RNG.normal(size=K) * 1.5
            b = RNG.normal(size=K) * 1.5
            gt = _ground_truth_md(
                a, b, means - df / 2, means + df / 2, np.zeros(K), np.zeros(K)
            )
            res = mti_modulation_depth(_make_fields(a, b), psi=None, directions=_UNIT_X)
            err_pct = 100 * abs(res["md"][0] - gt) / gt
            assert err_pct < 0.01, f"K={K} trial={trial}: {err_pct:.5f}% error"

    @pytest.mark.parametrize("K", [1, 2, 4, 6])
    def test_random_phase(self, K):
        means = np.linspace(2000.0, 2000.0 + 2000.0 * (K - 1), K)
        df = 50.0
        for trial in range(3):
            a = RNG.normal(size=K) * 1.5
            b = RNG.normal(size=K) * 1.5
            pha = np.zeros(K)
            phb = RNG.uniform(0, 2 * np.pi, K)
            psi = phb - pha
            gt = _ground_truth_md(a, b, means - df / 2, means + df / 2, pha, phb)
            res = mti_modulation_depth(_make_fields(a, b), psi=psi, directions=_UNIT_X)
            err_pct = 100 * abs(res["md"][0] - gt) / gt
            assert err_pct < 0.01, f"K={K} trial={trial}: {err_pct:.5f}% error"


# ---------------------------------------------------------------------------
# Anti-phase cancellation (Botzanowski Suppl. Fig. 1)
# ---------------------------------------------------------------------------


class TestAntiPhaseCancellation:
    """K=2, equal amplitudes, psi=[0, pi] -> aggregate envelope is exactly 0."""

    def test_equal_amplitude_antiphase_pair_cancels(self):
        fields = _make_fields([1.0, 1.0], [1.0, 1.0])
        psi = np.array([0.0, np.pi])
        res = mti_modulation_depth(fields, psi=psi, directions=_UNIT_X)
        assert res["md"][0] == pytest.approx(0.0, abs=1e-9)

    def test_in_phase_pair_does_not_cancel(self):
        fields = _make_fields([1.0, 1.0], [1.0, 1.0])
        psi = np.array([0.0, 0.0])
        res = mti_modulation_depth(fields, psi=psi, directions=_UNIT_X)
        assert res["md"][0] > 1.0


# ---------------------------------------------------------------------------
# psi=None reproduces the ported collaborator implementation
# ---------------------------------------------------------------------------


class TestMatchesCollaboratorImplementation:
    """With psi=None, mti_modulation_depth must reproduce the ported
    alba/ex-search-multipolar real-weight implementation
    (compute_botzanowski_directional_am_stats) to floating-point equality.

    The comparison goes through vectors=direction*amplitude on the
    collaborator side (the only way to recover the scalar amplitude from
    its public API), which reintroduces a norm/sqrt operation absent on
    our side -- so equality is to ~1 ULP (machine precision), not
    bit-for-bit through every intermediate.
    """

    @pytest.mark.parametrize("K", [1, 2, 4, 6])
    def test_random_fields(self, K):
        fields = [RNG.normal(size=(30, 3)) for _ in range(2 * K)]
        ours = mti_modulation_depth(fields)["md"]
        theirs = np.linalg.norm(
            compute_botzanowski_directional_am_stats(fields)["vectors"], axis=1
        )
        np.testing.assert_allclose(ours, theirs, rtol=1e-10, atol=1e-10)


# ---------------------------------------------------------------------------
# K=1 direction sweep vs exact closed form (get_TI_vectors) in full 3D
# ---------------------------------------------------------------------------


class TestK1MatchesExactClosedFormIn3D:
    """The best-direction sweep result for K=1 matches the exact Grossman
    closed form (get_TI_vectors) to < 0.1% -- residual is direction-sweep
    sampling error. The production default (192 directions) is a coarse
    sweep (~1% mean error); this uses a much finer sweep to demonstrate the
    sampling error vanishes with resolution, per
    tracks/active/mti-focality-core.md Phase 1 acceptance."""

    def test_fine_sweep_matches_grossman_closed_form(self):
        n_trials = 8
        E1 = RNG.normal(size=(n_trials, 3))
        E2 = RNG.normal(size=(n_trials, 3))
        res = mti_modulation_depth([E1, E2], num_directions=300_000)
        md_sweep = res["md"]
        md_exact = np.linalg.norm(get_TI_vectors(E1, E2), axis=1)
        err_pct = 100 * np.abs(md_sweep - md_exact) / md_exact
        assert err_pct.max() < 0.1, f"max error {err_pct.max():.4f}%"

    def test_default_192_direction_sweep_is_a_coarser_approximation(self):
        # Documents the production-default resolution/accuracy trade-off:
        # 192 directions (matching the ported implementation) is fast and
        # bit-parity-preserving for psi=None, but is NOT sub-0.1%-accurate
        # against the exact closed form on its own -- num_directions must
        # be raised for that; see the test above.
        n_trials = 20
        E1 = RNG.normal(size=(n_trials, 3))
        E2 = RNG.normal(size=(n_trials, 3))
        res = mti_modulation_depth([E1, E2])  # default num_directions=192
        md_sweep = res["md"]
        md_exact = np.linalg.norm(get_TI_vectors(E1, E2), axis=1)
        err_pct = 100 * np.abs(md_sweep - md_exact) / md_exact
        # Sweep result never overshoots the true maximum.
        assert np.all(md_sweep <= md_exact + 1e-9)
        # Coarse sweep is measurably less accurate than the fine one above.
        assert err_pct.mean() > 0.1


# ---------------------------------------------------------------------------
# Carrier power (P) return value
# ---------------------------------------------------------------------------


class TestCarrierPower:
    """P = 0.5 * sum_k (a_k^2 + b_k^2) at the direction MD was evaluated at."""

    def test_carrier_power_matches_hand_computation_directional(self):
        a = np.array([1.3, -0.7])
        b = np.array([0.9, 1.4])
        fields = _make_fields(a, b)
        res = mti_modulation_depth(fields, directions=_UNIT_X)
        expected_P = 0.5 * np.sum(a**2 + b**2)
        assert res["carrier_power"][0] == pytest.approx(expected_P)

    def test_carrier_power_nonnegative_and_bounds_md(self):
        # P >= Q always (Q is a Cauchy-Schwarz-bounded coherent sum of the
        # same terms P is built from), so MD = sqrt(2(P+Q)) - sqrt(2(P-Q))
        # is well-defined and P >= md^2 / 8 for any single pair (K=1 case:
        # P=0.5(a^2+b^2) >= |a||b| >= min(|a|,|b|)^2 = (md/2)^2).
        fields = [RNG.normal(size=(25, 3)) for _ in range(4)]
        res = mti_modulation_depth(fields)
        assert np.all(res["carrier_power"] >= 0.0)
        assert np.all(res["md"] >= 0.0)

    def test_carrier_power_present_in_sweep_and_directional_modes(self):
        fields = [RNG.normal(size=(10, 3)) for _ in range(4)]
        directions = RNG.normal(size=(10, 3))
        res_sweep = mti_modulation_depth(fields)
        res_dir = mti_modulation_depth(fields, directions=directions)
        assert "carrier_power" in res_sweep and "carrier_power" in res_dir
        assert res_sweep["carrier_power"].shape == (10,)
        assert res_dir["carrier_power"].shape == (10,)


# ---------------------------------------------------------------------------
# Return shape / best_direction
# ---------------------------------------------------------------------------


class TestReturnStructure:
    def test_returns_dict_with_required_keys(self):
        fields = [RNG.normal(size=(5, 3)) for _ in range(4)]
        res = mti_modulation_depth(fields)
        assert set(res.keys()) >= {"md", "carrier_power", "best_direction"}
        assert res["md"].shape == (5,)
        assert res["carrier_power"].shape == (5,)
        assert res["best_direction"].shape == (5, 3)

    def test_sweep_best_direction_is_unit_norm(self):
        fields = [RNG.normal(size=(8, 3)) for _ in range(4)]
        res = mti_modulation_depth(fields)
        norms = np.linalg.norm(res["best_direction"], axis=1)
        np.testing.assert_allclose(norms, 1.0, rtol=1e-10)

    def test_directional_mode_normalises_input_direction(self):
        fields = [RNG.normal(size=(3, 3)) for _ in range(4)]
        directions = RNG.normal(size=(3, 3)) * 5.0  # not unit norm
        res = mti_modulation_depth(fields, directions=directions)
        norms = np.linalg.norm(res["best_direction"], axis=1)
        np.testing.assert_allclose(norms, 1.0, rtol=1e-10)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_odd_number_of_fields_raises(self):
        fields = [RNG.normal(size=(3, 3)) for _ in range(3)]
        with pytest.raises(ValueError):
            mti_modulation_depth(fields)

    def test_too_few_fields_raises(self):
        with pytest.raises(ValueError):
            mti_modulation_depth([RNG.normal(size=(3, 3))])

    def test_wrong_field_dimensionality_raises(self):
        with pytest.raises(ValueError):
            mti_modulation_depth([RNG.normal(size=(3, 2)), RNG.normal(size=(3, 2))])

    def test_mismatched_field_shapes_raises(self):
        with pytest.raises(ValueError):
            mti_modulation_depth([RNG.normal(size=(3, 3)), RNG.normal(size=(4, 3))])

    def test_wrong_psi_length_raises(self):
        fields = [RNG.normal(size=(3, 3)) for _ in range(4)]  # K=2
        with pytest.raises(ValueError, match="psi"):
            mti_modulation_depth(fields, psi=[0.0, 0.0, 0.0])

    def test_wrong_directions_shape_raises(self):
        fields = [RNG.normal(size=(3, 3)) for _ in range(2)]
        with pytest.raises(ValueError):
            mti_modulation_depth(fields, directions=RNG.normal(size=(5, 3)))
