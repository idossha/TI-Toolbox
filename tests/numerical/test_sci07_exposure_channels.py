"""SCI-07 -- the exposure metrics, on ``main``'s positional carrier model.

Cassarà et al. 2025, *Recommendations for the Safe Application of Temporal
Interference Stimulation in the Human Brain*, Part II, p. 8:

    "In the presence of multiple currents (e.g., TIS channels), coherent field
    superposition was used for identical frequencies, and incoherent
    superposition (i.e., SAR addition) was used when the frequencies differed."

**Which fields share a frequency is a property of the wiring.**  Since v2.5.0
(``7a5ee2dd``, ``d4706e5a``, ``b19a1c26``) TI-Toolbox has exactly one wiring:
**positional**.  ``electrode_pairs`` are taken two at a time, each pair driven
at its own carrier frequency, so *one FEM field is one carrier* and the
coherent pre-sum within a frequency is the identity.  The exposure metrics
therefore sum incoherently over the N fields:

    ``hf_sar = sum_i |E_i|^2``            (power adds; distinct frequencies)
    ``hf_peak = max_s |sum_i s_i E_i|``   (worst-case realisable phase)

with the sinusoid's ``1/2`` applied exactly once, in the SAR calibration
``(sigma / 2 rho) * hf_sar``, and nowhere in the field-domain quantity itself.

Everything below is checked against an **independent time-domain simulation**:
the fields are given actual carrier frequencies and phases, ``E(t)`` is summed
on a fine grid over a full common period, and the true time-averaged ``|E|^2``,
the true peak ``|E(t)|`` and the true amplitude-modulation depth are measured
from that signal.  No toolbox code is reused to build the reference.

Frequencies are chosen commensurate (a common period exists) so that the
time-average is exact rather than asymptotic; they are still *distinct*, which
is all the incoherence argument needs -- the cross terms of two different
frequencies integrate to zero over the common period, while two contributions
at the *same* frequency keep their cross term.  The last section pins that
distinction explicitly: it measures what a shared-frequency pair would do, and
records that the positional wiring never produces one.
"""

import itertools

import numpy as np
import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# Independent reference: an explicit time-domain simulation.
# --------------------------------------------------------------------------

#: Carrier frequencies in Hz.  Distinct, and with a common period of 1/10 s
#: (gcd = 10 Hz), so a whole number of cycles of every carrier fits the window.
_FREQS = (2000.0, 2010.0, 2030.0, 2070.0, 2110.0, 2130.0, 2170.0, 2190.0)
_COMMON_PERIOD = 0.1  # s; 1 / gcd(_FREQS)
_N_SAMPLES = 400_000  # ~180 samples per cycle of the fastest carrier


def _time_series(fields, freqs, phases):
    """``E(t)`` at ``_N_SAMPLES`` instants, shape ``(T, 3)``.

    ``fields[i]`` is a ``(3,)`` amplitude vector driven at ``freqs[i]`` with
    phase ``phases[i]``: ``E(t) = sum_i E_i cos(2 pi f_i t + phi_i)``.  Fields
    that share a frequency *and* phase are phase-locked and add coherently at
    every instant; distinct frequencies do not.
    """
    t = np.arange(_N_SAMPLES, dtype=np.float64) * (_COMMON_PERIOD / _N_SAMPLES)
    out = np.zeros((_N_SAMPLES, 3), dtype=np.float64)
    for e, f, ph in zip(fields, freqs, phases):
        out += np.outer(np.cos(2.0 * np.pi * f * t + ph), np.asarray(e, float))
    return out


def _true_mean_square(fields, freqs, phases):
    """Time-averaged ``|E(t)|^2`` over the common period, measured, not derived."""
    e_t = _time_series(fields, freqs, phases)
    return float(np.mean(np.sum(e_t * e_t, axis=1)))


def _true_peak(fields, freqs, phases):
    """``max_t |E(t)|`` over the common period."""
    e_t = _time_series(fields, freqs, phases)
    return float(np.max(np.linalg.norm(e_t, axis=1)))


def _reference_hf_sar(carriers):
    """``sum_c |E_c|^2`` written out longhand."""
    return sum(float(np.dot(c, c)) for c in carriers)


def _reference_hf_peak(carriers):
    """``max_s |sum_c s_c E_c|`` by brute-force enumeration of every sign."""
    best = 0.0
    for signs in itertools.product((1.0, -1.0), repeat=len(carriers)):
        total = sum(s * np.asarray(c, float) for s, c in zip(signs, carriers))
        best = max(best, float(np.linalg.norm(total)))
    return best


def _as_rows(*vectors):
    """Turn ``(3,)`` vectors into the ``(N, 3)`` arrays the API takes."""
    return [np.tile(np.asarray(v, float), (4, 1)) for v in vectors]


# --------------------------------------------------------------------------
# 1. One field is one carrier: hf_sar / 2 is the measured time-average.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_carriers", [2, 3, 4, 6, 8])
def test_hf_sar_matches_measured_time_average(n_carriers):
    """``hf_sar / 2`` is the true time-averaged ``|E(t)|^2``.

    The ``1/2`` is the sinusoid's time-average (Cassarà Part II, p. 6: "For
    sinusoidal currents, root mean square (RMS) peak E-field and current
    density differ by a factor of sqrt(2)").  It is applied exactly once, in
    the SAR calibration ``(sigma / 2 rho) * hf_sar``, and this test pins that
    the field-domain quantity itself carries no factor.
    """
    from tit.fields import hf_sar

    rng = np.random.default_rng(20260907 + n_carriers)
    vecs = [rng.normal(size=3) for _ in range(n_carriers)]
    fields = _as_rows(*vecs)

    freqs = _FREQS[:n_carriers]
    phases = [0.37 * i for i in range(n_carriers)]

    measured = _true_mean_square(vecs, freqs, phases)
    got = hf_sar(*fields)
    assert got.shape == (4,)
    assert float(got[0]) == pytest.approx(2.0 * measured, rel=1e-9)
    # ... and it is the longhand incoherent sum (summation order aside).
    assert float(got[0]) == pytest.approx(_reference_hf_sar(vecs), rel=1e-15)


def test_hf_sar_is_phase_blind():
    """Distinct carriers: the time-average does not depend on their phases.

    This is the whole content of "incoherent superposition" -- the cross terms
    of two different frequencies integrate to zero over the common period, so
    ``hf_sar`` is a function of the amplitudes alone.
    """
    from tit.fields import hf_sar

    rng = np.random.default_rng(9091)
    vecs = [rng.normal(size=3) for _ in range(4)]
    freqs = _FREQS[:4]

    a = _true_mean_square(vecs, freqs, [0.0, 0.0, 0.0, 0.0])
    b = _true_mean_square(vecs, freqs, [0.0, 1.3, 2.9, 0.6])
    assert a == pytest.approx(b, rel=1e-9)
    assert float(hf_sar(*_as_rows(*vecs))[0]) == pytest.approx(2.0 * a, rel=1e-9)


# --------------------------------------------------------------------------
# 2. Peak carrier field: the worst-case realisable phase.
# --------------------------------------------------------------------------


def test_hf_peak_matches_measured_peak_two_carriers():
    """``hf_peak`` is the true ``max_t |E(t)|`` for two carriers.

    Cassarà Part I, Eq. 3 (p. 11): the worst case is "in-phase, spatially
    aligned fields", ``max(|E1+E2|, |E1-E2|)``.  Two distinct frequencies make
    the *relative* phase sweep the whole circle within one beat period, so the
    supremum is actually attained and the measurement is exact.
    """
    from tit.fields import hf_peak

    e0 = np.array([0.9, -0.3, 0.2])
    e1 = np.array([0.1, 0.5, -0.4])
    measured = _true_peak([e0, e1], (_FREQS[0], _FREQS[1]), (0.0, 0.0))
    got = float(hf_peak(*_as_rows(e0, e1))[0])
    assert got == pytest.approx(measured, rel=2e-4)
    assert got == pytest.approx(_reference_hf_peak([e0, e1]), rel=1e-12)


@pytest.mark.parametrize("n_carriers", [3, 4, 5])
def test_hf_peak_is_conservative_for_more_carriers(n_carriers):
    """Above two carriers the metric must *dominate* any observed instant.

    With commensurate frequencies the relative phases trace a closed line on
    the phase torus rather than filling it, so a finite simulation does not
    generally reach the all-in-phase vertex.  What matters for a safety metric
    is the direction of the inequality: ``hf_peak`` is an upper bound on every
    instantaneous magnitude, and the supremum over the torus is the sign
    enumeration it reports.
    """
    from tit.fields import hf_peak

    rng = np.random.default_rng(808 + n_carriers)
    vecs = [rng.normal(size=3) for _ in range(n_carriers)]
    got = float(hf_peak(*_as_rows(*vecs))[0])

    assert got == pytest.approx(_reference_hf_peak(vecs), rel=1e-12)
    for phases in ((0.0,) * n_carriers, tuple(0.31 * i for i in range(n_carriers))):
        assert _true_peak(vecs, _FREQS[:n_carriers], phases) <= got + 1e-9


def test_hf_peak_two_carriers_is_cassara_eq3():
    """At two carriers the sign enumeration *is* ``max(|E1+E2|, |E1-E2|)``."""
    from tit.fields import hf_peak

    rng = np.random.default_rng(3131)
    for _ in range(20):
        e1, e2 = rng.normal(size=3), rng.normal(size=3)
        eq3 = max(np.linalg.norm(e1 + e2), np.linalg.norm(e1 - e2))
        assert float(hf_peak(*_as_rows(e1, e2))[0]) == pytest.approx(eq3, rel=1e-14)


def test_hf_peak_never_below_any_single_carrier():
    """A safety metric must dominate every one of its constituents."""
    from tit.fields import hf_peak

    rng = np.random.default_rng(555)
    vecs = [rng.normal(size=3) for _ in range(6)]
    peak = float(hf_peak(*_as_rows(*vecs))[0])
    assert peak >= max(float(np.linalg.norm(v)) for v in vecs) - 1e-12


def test_hf_peak_is_exact_counts_carriers():
    """One field is one carrier, so the flag is a plain count threshold."""
    from tit.fields import EXACT_SIGN_ENUM_MAX_FIELDS, hf_peak_is_exact

    assert hf_peak_is_exact(2) is True
    assert hf_peak_is_exact(EXACT_SIGN_ENUM_MAX_FIELDS) is True
    assert hf_peak_is_exact(EXACT_SIGN_ENUM_MAX_FIELDS + 1) is False
    assert hf_peak_is_exact(12) is False


def test_hf_peak_sweep_is_a_lower_bound_on_the_exact_enumeration():
    """Above the enumeration cap the sweep may under-report, never over-report."""
    from tit.fields import EXACT_SIGN_ENUM_MAX_FIELDS, hf_peak

    n = EXACT_SIGN_ENUM_MAX_FIELDS + 2
    rng = np.random.default_rng(24601)
    vecs = [rng.normal(size=3) for _ in range(n)]
    swept = float(hf_peak(*_as_rows(*vecs))[0])
    exact = _reference_hf_peak(vecs)
    assert swept <= exact + 1e-9
    assert swept == pytest.approx(exact, rel=5e-2)


# --------------------------------------------------------------------------
# 3. The envelope: the stimulation-relevant quantity.
# --------------------------------------------------------------------------


def test_directional_envelope_matches_time_domain_beat_depth():
    """Cassarà Part I, Eq. 1 (p. 10) against a measured beat.

    Along a direction ``n``, the projected signal is
    ``a cos(w1 t) + b cos(w2 t)``; its envelope swings between ``|a| + |b|``
    and ``||a| - |b||``, so the peak-to-trough modulation depth is
    ``2 min(|a|, |b|)``, which is Eq. 1's
    ``| |(E1+E2).n| - |(E1-E2).n| |``.  This is the one place a time axis
    appears at all: the engine itself is quasi-static and never forms
    ``E(t)`` -- the beat is synthesised here only to show that the phasor
    worst-case convention reproduces what the real signal does.
    """
    e1 = np.array([0.8, 0.2, -0.1])
    e2 = np.array([0.3, -0.5, 0.4])
    n = np.array([0.0, 0.0, 1.0])

    a = float(np.dot(e1, n))
    b = float(np.dot(e2, n))
    eq1 = abs(abs(a + b) - abs(a - b))
    assert eq1 == pytest.approx(2.0 * min(abs(a), abs(b)), rel=1e-12)

    e_t = _time_series([e1, e2], (_FREQS[0], _FREQS[1]), (0.0, 0.0))
    proj = np.abs(e_t @ n)
    per_carrier_period = int(round(_N_SAMPLES / (_FREQS[0] * _COMMON_PERIOD)))
    env = proj[: (len(proj) // per_carrier_period) * per_carrier_period]
    env = env.reshape(-1, per_carrier_period).max(axis=1)
    assert float(env.max()) == pytest.approx(abs(a) + abs(b), abs=2e-3)
    assert float(env.min()) == pytest.approx(abs(abs(a) - abs(b)), abs=2e-3)
    measured_depth = float(env.max() - env.min())
    assert measured_depth == pytest.approx(eq1, abs=4e-3)


def test_max_envelope_matches_the_best_direction_of_the_measured_beat():
    """``get_TI_vectors``'s norm is the largest beat depth over any direction.

    The per-direction depth is Eq. 1 (checked against the time domain in the
    test above); maximising it over a dense direction sweep is an independent
    reconstruction of the K=1 closed form the engine uses.
    """
    from tit.calc import get_TI_vectors

    e1 = np.array([0.8, 0.2, -0.1])
    e2 = np.array([0.3, -0.5, 0.4])

    m = 200_001
    i = np.arange(m) + 0.5
    phi = np.arccos(1 - 2 * i / m)
    theta = np.pi * (3 - np.sqrt(5)) * i
    dirs = np.stack(
        [np.sin(phi) * np.cos(theta), np.sin(phi) * np.sin(theta), np.cos(phi)],
        axis=-1,
    )
    a = dirs @ e1
    b = dirs @ e2
    swept = float(np.max(np.abs(np.abs(a + b) - np.abs(a - b))))

    got = float(
        np.linalg.norm(
            get_TI_vectors([np.tile(e1, (4, 1)), np.tile(e2, (4, 1))])[0]
        )
    )
    assert got == pytest.approx(swept, rel=1e-3)
    assert got >= swept - 1e-12


# --------------------------------------------------------------------------
# 4. The envelope and the exposure metrics see the SAME carriers.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_fields", [2, 4, 6, 8])
def test_envelope_and_exposure_consume_the_same_positional_field_list(n_fields):
    """One field list, one carrier per entry, both paths.

    ``tit.calc`` pairs ``fields`` positionally into ``n_fields // 2`` beating
    carriers and ``tit.fields`` sums the same ``n_fields`` entries
    incoherently.  There is no grouping argument on either side to drift, so
    what this pins is the *shape* contract: both accept exactly the montage's
    field list, in order, and neither drops or re-pairs an entry.
    """
    from tit.calc import get_TI_vectors
    from tit.fields import hf_peak, hf_sar

    rng = np.random.default_rng(1729 + n_fields)
    fields = [rng.normal(size=(8, 3)) for _ in range(n_fields)]

    assert get_TI_vectors(fields).shape == (8, 3)
    assert hf_sar(*fields).shape == (8,)
    assert hf_peak(*fields).shape == (8,)

    # Permuting whole positional pairs re-labels carriers but changes neither
    # metric: both are symmetric under carrier exchange.
    pairs = [(fields[2 * k], fields[2 * k + 1]) for k in range(n_fields // 2)]
    reordered = [f for p in reversed(pairs) for f in p]
    assert np.allclose(hf_sar(*reordered), hf_sar(*fields), rtol=0, atol=1e-12)
    assert np.allclose(hf_peak(*reordered), hf_peak(*fields), rtol=0, atol=1e-12)


def test_shared_frequency_would_need_a_coherent_presum_and_never_occurs():
    """The regime the positional wiring rules out, measured rather than argued.

    If two electrode pairs were driven *phase-locked at one frequency* -- the
    Lee et al. 2022 shared-carrier design -- the true time-averaged ``|E|^2``
    would be ``|E_a + E_b|^2 / 2``, not ``(|E_a|^2 + |E_b|^2) / 2``, and
    ``hf_sar`` over the raw fields would understate exposure by the cross term
    (a factor of 2 for two equal aligned fields).  That is why the metric is
    stated over *carriers*.  Positional wiring gives every field its own
    frequency, so the case cannot arise -- and ``Montage`` has no field with
    which to express it.  If a future montage regains one, the coherent
    pre-sum belongs in ``tit.fields`` and this test is the specification.
    """
    from dataclasses import fields as dataclass_fields

    from tit.fields import hf_sar
    from tit.sim.config import Montage

    e_a = np.array([1.0, 0.0, 0.0])
    e_b = np.array([1.0, 0.0, 0.0])

    shared = _true_mean_square([e_a, e_b], (_FREQS[0], _FREQS[0]), (0.3, 0.3))
    distinct = _true_mean_square([e_a, e_b], (_FREQS[0], _FREQS[1]), (0.3, 0.3))
    assert shared == pytest.approx(2.0, rel=1e-9)  # |E_a + E_b|^2 / 2 = 4/2
    assert distinct == pytest.approx(1.0, rel=1e-9)  # (1 + 1) / 2

    # The toolbox computes the distinct-frequency value, which is correct for
    # the only wiring it can express.
    assert float(hf_sar(*_as_rows(e_a, e_b))[0]) == pytest.approx(
        2.0 * distinct, rel=1e-12
    )

    # And there is no way to declare the shared-frequency wiring.
    assert "channels" not in {f.name for f in dataclass_fields(Montage)}
    assert "channels" not in hf_sar.__code__.co_varnames


# --------------------------------------------------------------------------
# 5. The rationalised envelope form at extreme P/Q.
# --------------------------------------------------------------------------


def test_envelope_from_pq_survives_catastrophic_cancellation():
    """``2 sqrt(2) Q / (sqrt(P+Q) + sqrt(P-Q))`` where the naive form collapses.

    The ill-conditioned regime is **weak modulation**, ``Q / P -> 0``: there
    the two roots of ``sqrt(2(P+Q)) - sqrt(2(P-Q))`` converge and the
    subtraction throws away the leading digits -- absolute error ~``eps*sqrt(P)``
    regardless of how small the true depth is, so the *relative* error grows
    without bound and the result is exactly ``0`` once ``Q/P < eps/2``.  The
    rationalised form has no subtraction of near-equal terms and stays
    accurate to the last bit.

    (The opposite extreme, ``Q -> P``, is benign in both forms: ``sqrt(P-Q)``
    simply goes to zero.  It is checked here too, to pin that the rewrite did
    not trade one regime for the other.)

    The reference is the same expression in 60-digit ``decimal`` arithmetic.
    """
    from decimal import Decimal, getcontext

    from tit.calc import _envelope_from_PQ

    getcontext().prec = 60
    P = 1.0

    worst_ours = 0.0
    worst_naive = 0.0
    for q in (1e-8, 1e-11, 1e-13, 1e-15, 1e-17, 1e-20):
        Q = P * q
        dP, dQ = Decimal(P), Decimal(Q)
        exact = (2 * (dP + dQ)).sqrt() - (2 * (dP - dQ)).sqrt()

        got = float(_envelope_from_PQ(np.array([P]), np.array([Q]))[0])
        naive = np.sqrt(2 * (P + Q)) - np.sqrt(2 * (P - Q))

        assert got == pytest.approx(float(exact), rel=1e-14), (
            f"Q/P={q}: got {got}, exact {exact}"
        )
        worst_ours = max(worst_ours, abs(got / float(exact) - 1.0))
        worst_naive = max(worst_naive, abs(naive / float(exact) - 1.0))

    assert worst_ours < 1e-14
    assert worst_naive > 0.1

    for rel in (1e-13, 0.0):
        Q = P * (1.0 - rel)
        dP, dQ = Decimal(P), Decimal(Q)
        exact = (2 * (dP + dQ)).sqrt() - (2 * (dP - dQ)).sqrt()
        got = float(_envelope_from_PQ(np.array([P]), np.array([Q]))[0])
        assert got == pytest.approx(float(exact), rel=1e-14)


def test_envelope_from_pq_null_field_is_zero():
    """``P = Q = 0`` (a null field) yields ``0``, not a division by zero."""
    from tit.calc import _envelope_from_PQ

    out = _envelope_from_PQ(np.array([0.0, 1.0]), np.array([0.0, 0.5]))
    assert out[0] == 0.0
    assert np.isfinite(out).all()


def test_numba_kernel_envelope_agrees_with_the_numpy_form():
    """``tit._mti_kernel._envelope`` carries the same conditioning fix.

    The accelerated K>=2 sweep has its own scalar copy of the envelope; if the
    two forms ever diverge, the numba and NumPy paths would report different
    modulation depths for the same montage.
    """
    from tit._mti_kernel import _envelope
    from tit.calc import _envelope_from_PQ

    for P, Q in [(1.0, 1e-20), (1.0, 1e-13), (1.0, 0.5), (1.0, 1.0), (0.0, 0.0)]:
        vec = float(_envelope_from_PQ(np.array([P]), np.array([Q]))[0])
        assert float(_envelope(P, Q)) == pytest.approx(vec, rel=1e-14, abs=1e-300)


# --------------------------------------------------------------------------
# 6. Allowed channel (electrode-pair) counts.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n, ok", [(0, False), (1, False), (2, True), (3, False), (4, True),
              (5, False), (6, True), (8, True), (12, True), (16, True)]
)
def test_allowed_electrode_pair_counts(n, ok):
    """One current channel per electrode pair; every channel needs a partner.

    2 pairs is standard TI (one beat); 4, 6, 8, 12, 16 … are mTI.  An odd
    count leaves a channel with nothing to beat against, and a single pair is
    tACS, not TI.
    """
    from tit.constants import is_valid_pair_count

    assert is_valid_pair_count(n) is ok


def test_calc_rejects_disallowed_field_counts():
    """``tit.calc`` enforces the same rule as the montage config."""
    from tit.calc import get_TI_vectors

    rng = np.random.default_rng(5)
    three = [rng.normal(size=(4, 3)) for _ in range(3)]
    with pytest.raises(ValueError, match="even number of fields"):
        get_TI_vectors(three)


def test_montage_rejects_odd_pair_counts():
    """A 5-pair montage no longer silently reports itself as mTI."""
    pytest.importorskip("tit.sim.config")
    from tit.sim.config import Montage, MontageMode, SimulationMode

    def mk(n):
        return Montage(
            name="m",
            mode=MontageMode.NET,
            electrode_pairs=[(f"E{2 * i}", f"E{2 * i + 1}") for i in range(n)],
        )

    assert mk(2).simulation_mode is SimulationMode.TI
    assert mk(4).simulation_mode is SimulationMode.MTI
    assert mk(6).simulation_mode is SimulationMode.MTI
    for bad in (1, 3, 5):
        with pytest.raises(ValueError, match="even number of electrode pairs"):
            mk(bad).simulation_mode
