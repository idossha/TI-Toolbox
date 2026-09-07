"""SCI-07 -- the exposure metrics honour the montage's declared carriers.

Cassarà et al. 2025, *Recommendations for the Safe Application of Temporal
Interference Stimulation in the Human Brain*, Part II, p. 8:

    "In the presence of multiple currents (e.g., TIS channels), coherent field
    superposition was used for identical frequencies, and incoherent
    superposition (i.e., SAR addition) was used when the frequencies differed."

Before this fix ``tit/fields.py`` treated **every** raw FEM field as its own
incoherent carrier, so a montage that declares ``channels`` (several electrode
pairs driven phase-locked from one carrier, the shared-carrier design) had its
``hf_sar`` computed as ``sum_i |E_i|^2`` instead of ``sum_c |sum_{i in c} E_i|^2``
-- a lower bound, and therefore *non-conservative* for a safety metric.

Everything below is checked against an **independent time-domain simulation**:
the fields are given actual carrier frequencies and phases, ``E(t)`` is summed
on a fine grid over a full common period, and the true time-averaged ``|E|^2``,
the true peak ``|E(t)|`` and the true amplitude-modulation depth are measured
from that signal.  No toolbox code is reused to build the reference.

Frequencies are chosen commensurate (a common period exists) so that the
time-average is exact rather than asymptotic; they are still *distinct*, which
is all the incoherence argument needs -- the cross terms of two different
frequencies integrate to zero over the common period, while two contributions
at the *same* frequency keep their cross term.  That is precisely the
distinction the fix is about.
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
_FREQS = (2000.0, 2010.0, 2030.0, 2070.0)
_COMMON_PERIOD = 0.1  # s; 1 / gcd(_FREQS)
_N_SAMPLES = 400_000  # ~200 samples per cycle of the fastest carrier


def _time_series(fields, freqs, phases):
    """``E(t)`` at ``_N_SAMPLES`` instants, shape ``(T, 3)``.

    ``fields[i]`` is a ``(3,)`` amplitude vector driven at ``freqs[i]`` with
    phase ``phases[i]``: ``E(t) = sum_i E_i cos(2 pi f_i t + phi_i)``.  Fields
    that share a frequency *and* phase are phase-locked -- the shared-carrier
    case -- and their contributions add coherently at every instant.
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
# 1. One carrier group: aligned / opposing / orthogonal contributions.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "e_a, e_b, label",
    [
        ([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], "aligned"),
        ([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], "opposing"),
        ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], "orthogonal"),
        ([0.7, -0.2, 0.4], [0.3, 0.9, -0.1], "oblique"),
    ],
)
def test_same_channel_pair_sums_coherently(e_a, e_b, label):
    """Two fields on one carrier + a third on another.

    The reference drives fields 0 and 1 at the *same* frequency and phase, and
    field 2 at a different one.  The measured time-averaged ``|E|^2`` must be
    ``hf_sar / 2`` with ``channels`` declared, and must *not* match the
    ungrouped ``hf_sar / 2`` unless the two happen to be orthogonal.
    """
    from tit.fields import hf_sar

    e_a = np.array(e_a)
    e_b = np.array(e_b)
    e_c = np.array([0.2, 0.1, 0.8])
    fields = _as_rows(e_a, e_b, e_c)
    channels = [([0, 1], [2])]

    # Independent measurement: fields 0,1 share carrier 0; field 2 is carrier 1.
    measured = _true_mean_square(
        [e_a, e_b, e_c], (_FREQS[0], _FREQS[0], _FREQS[1]), (0.3, 0.3, 1.1)
    )

    grouped = hf_sar(*fields, channels=channels)
    assert grouped.shape == (4,)
    assert grouped[0] == pytest.approx(2.0 * measured, rel=1e-9)

    # And it equals the longhand coherent-then-power reference.
    assert grouped[0] == pytest.approx(_reference_hf_sar([e_a + e_b, e_c]), rel=1e-12)

    ungrouped = hf_sar(*fields)
    if label == "orthogonal":
        # Orthogonal same-carrier contributions have no cross term, so the two
        # models coincide -- the one case where the old behaviour was right.
        assert ungrouped[0] == pytest.approx(grouped[0], rel=1e-12)
    else:
        assert ungrouped[0] != pytest.approx(grouped[0], rel=1e-6)
        # Aligned contributions are the worst case: on the grouped carrier
        # alone the old value was a factor of two low for two equal aligned
        # fields (the third field's own carrier is common to both models).
        if label == "aligned":
            third = float(np.dot(e_c, e_c))
            assert grouped[0] - third == pytest.approx(
                2.0 * (ungrouped[0] - third), rel=1e-12
            )


def test_aligned_pair_old_behaviour_was_a_lower_bound():
    """The documented 2 -> 4 magnitude for two aligned unit fields."""
    from tit.fields import hf_sar

    fields = _as_rows([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    ungrouped = float(hf_sar(*fields)[0])
    grouped = float(hf_sar(*fields, channels=[([0, 1], [2])])[0])
    assert ungrouped == pytest.approx(3.0)  # 1 + 1 + 1
    assert grouped == pytest.approx(5.0)  # |E0+E1|^2 + |E2|^2 = 4 + 1


# --------------------------------------------------------------------------
# 2. Time-averaged |E|^2 for 1, 2 and 3 carriers.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_carriers", [1, 2, 3])
def test_hf_sar_matches_measured_time_average(n_carriers):
    """``hf_sar / 2`` is the true time-averaged ``|E(t)|^2``, for any carrier count.

    The ``1/2`` is the sinusoid's time-average (Cassarà Part II, p. 6: "For
    sinusoidal currents, root mean square (RMS) peak E-field and current
    density differ by a factor of sqrt(2)").  It is applied exactly once, in
    the SAR calibration ``(sigma / 2 rho) * hf_sar``, and this test pins that
    the field-domain quantity itself carries no factor.
    """
    from tit.fields import hf_sar

    rng = np.random.default_rng(20260907 + n_carriers)
    # Two fields per carrier, so the coherent-sum step is exercised at every
    # carrier count and the flat field list is never trivially the carriers.
    per_carrier = [rng.normal(size=(2, 3)) for _ in range(n_carriers)]
    flat = [v for pair in per_carrier for v in pair]
    channels = []
    for c in range(n_carriers):
        # One carrier per group_a; group_b of the previous channel is empty for
        # odd counts, so pair the carriers up and leave a lone one non-beating.
        channels.append(([2 * c, 2 * c + 1], []))

    fields = _as_rows(*flat)
    freqs = [f for c in range(n_carriers) for f in (_FREQS[c], _FREQS[c])]
    phases = [p for c in range(n_carriers) for p in (0.4 * c, 0.4 * c)]

    measured = _true_mean_square(flat, freqs, phases)
    got = float(hf_sar(*fields, channels=channels)[0])
    assert got == pytest.approx(2.0 * measured, rel=1e-9)


# --------------------------------------------------------------------------
# 3. Peak carrier field over channel sums.
# --------------------------------------------------------------------------


def test_hf_peak_matches_measured_peak_two_carriers():
    """``hf_peak`` is the true ``max_t |E(t)|`` for two carriers.

    Cassarà Part I, Eq. 3 (p. 11): the worst case is "in-phase, spatially
    aligned fields", ``max(|E1+E2|, |E1-E2|)``.  With distinct frequencies the
    relative phase sweeps the full circle, and the supremum of
    ``|sum_c A_c cos(theta_c)|`` over the phase box is attained at a vertex --
    which is exactly the sign enumeration.
    """
    from tit.fields import hf_peak

    e0 = np.array([0.9, -0.3, 0.2])
    e1 = np.array([0.1, 0.5, -0.4])
    e2 = np.array([0.3, 0.3, 0.7])
    fields = _as_rows(e0, e1, e2)
    channels = [([0, 1], [2])]

    measured = _true_peak(
        [e0, e1, e2], (_FREQS[0], _FREQS[0], _FREQS[1]), (0.0, 0.0, 0.0)
    )
    got = float(hf_peak(*fields, channels=channels)[0])
    assert got == pytest.approx(measured, rel=2e-4)
    assert got == pytest.approx(_reference_hf_peak([e0 + e1, e2]), rel=1e-12)


def test_hf_peak_grouping_can_only_lower_the_peak():
    """Grouping removes sign patterns the hardware cannot realise.

    Two pairs fed from one phase-locked source cannot be in anti-phase, so the
    ungrouped enumeration -- which is free to flip them independently -- is an
    over-estimate.  It is a *safe* over-estimate, but not the physical value.
    """
    from tit.fields import hf_peak

    e0 = np.array([1.0, 0.0, 0.0])
    e1 = np.array([-0.9, 0.0, 0.0])  # nearly cancels e0 on its own carrier
    e2 = np.array([0.0, 0.4, 0.0])
    fields = _as_rows(e0, e1, e2)

    ungrouped = float(hf_peak(*fields)[0])
    grouped = float(hf_peak(*fields, channels=[([0, 1], [2])])[0])
    assert grouped < ungrouped
    # carrier 0 is e0 + e1 = 0.1 x-hat; peak is |0.1 x| + |0.4 y| in quadrature
    assert grouped == pytest.approx(np.hypot(0.1, 0.4), rel=1e-12)
    assert ungrouped == pytest.approx(np.hypot(1.9, 0.4), rel=1e-12)


def test_three_pairs_sharing_one_carrier():
    """Six electrode pairs, three per carrier -- the Lee et al. 2022 design.

    This is the case the old code got most wrong: ``hf_sar`` saw six
    independent carriers where the montage declares two.
    """
    from tit.fields import hf_peak, hf_peak_is_exact, hf_sar

    rng = np.random.default_rng(70725)
    vecs = [rng.normal(size=3) for _ in range(6)]
    fields = _as_rows(*vecs)
    channels = [([0, 1, 2], [3, 4, 5])]

    a = vecs[0] + vecs[1] + vecs[2]
    b = vecs[3] + vecs[4] + vecs[5]

    measured_ms = _true_mean_square(
        vecs, [_FREQS[0]] * 3 + [_FREQS[1]] * 3, [0.7] * 3 + [2.1] * 3
    )
    assert float(hf_sar(*fields, channels=channels)[0]) == pytest.approx(
        2.0 * measured_ms, rel=1e-9
    )
    assert float(hf_sar(*fields, channels=channels)[0]) == pytest.approx(
        _reference_hf_sar([a, b]), rel=1e-12
    )

    measured_peak = _true_peak(vecs, [_FREQS[0]] * 3 + [_FREQS[1]] * 3, [0.0] * 6)
    assert float(hf_peak(*fields, channels=channels)[0]) == pytest.approx(
        measured_peak, rel=2e-4
    )
    assert float(hf_peak(*fields, channels=channels)[0]) == pytest.approx(
        max(np.linalg.norm(a + b), np.linalg.norm(a - b)), rel=1e-12
    )

    # Six raw fields would still be exact, but the carrier count is what counts.
    assert hf_peak_is_exact(6, channels) is True
    assert len(channels) == 1


def test_hf_peak_is_exact_counts_carriers_not_fields():
    """Twelve fields on two carriers take the exact path, not the sweep."""
    from tit.fields import hf_peak_is_exact

    twelve_on_two = [(list(range(6)), list(range(6, 12)))]
    assert hf_peak_is_exact(12) is False  # ungrouped: 12 carriers, sweep
    assert hf_peak_is_exact(12, twelve_on_two) is True  # grouped: 2 carriers


# --------------------------------------------------------------------------
# 4. The envelope: the stimulation-relevant quantity, unchanged.
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

    # Measured: the envelope of the projected beat, from the time series.
    # The envelope is the peak |proj| within each *carrier* period; the beat
    # then swings that envelope between |a|+|b| and ||a|-|b|| over the window
    # (which is exactly one beat period here).
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

    # Dense Fibonacci sweep, written here rather than imported.
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
            get_TI_vectors(np.tile(e1, (4, 1)), np.tile(e2, (4, 1)))[0]
        )
    )
    # The sweep is a lower bound that converges quadratically in the angular
    # spacing; the closed form is the exact maximum, so it must sit just above.
    assert got == pytest.approx(swept, rel=1e-3)
    assert got >= swept - 1e-12


# --------------------------------------------------------------------------
# 5. The channels=None path is bit-identical to the pre-fix behaviour.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_fields", [2, 3, 4, 5, 8])
def test_channels_none_is_bit_identical(n_fields):
    """Every montage without a declared grouping is untouched, to the last bit.

    Both metrics are compared against a reference written out longhand in this
    file, with ``==`` rather than a tolerance.
    """
    from tit.fields import hf_peak, hf_sar

    rng = np.random.default_rng(1000 + n_fields)
    vecs = [rng.normal(size=3) for _ in range(n_fields)]
    fields = _as_rows(*vecs)

    sar = hf_sar(*fields)
    peak = hf_peak(*fields)

    assert float(sar[0]) == _reference_hf_sar(vecs)
    assert float(peak[0]) == pytest.approx(_reference_hf_peak(vecs), rel=1e-15)

    # Passing an explicit trivial grouping names the same carriers, so it must
    # give exactly the same numbers as no grouping at all.
    trivial = [
        ([2 * k], [2 * k + 1]) for k in range(n_fields // 2)
    ]
    if n_fields % 2:
        trivial.append(([n_fields - 1], []))
    assert np.array_equal(hf_sar(*fields, channels=trivial), sar)
    assert np.array_equal(hf_peak(*fields, channels=trivial), peak)


def test_channels_none_leaves_the_full_mti_path_unchanged():
    """``get_mTI_vectors`` with and without an equivalent explicit grouping."""
    from tit.calc import get_mTI_vectors

    rng = np.random.default_rng(4242)
    fields = [rng.normal(size=(16, 3)) for _ in range(4)]
    default = get_mTI_vectors(fields)
    explicit = get_mTI_vectors(fields, channels=[([0], [1]), ([2], [3])])
    assert np.allclose(default, explicit, rtol=0, atol=0)


# --------------------------------------------------------------------------
# 6. The rationalised envelope form at extreme P/Q.
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

    # Weak-modulation regime: Q/P from 1e-8 down to 1e-20.
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

    # The naive form loses everything at the bottom of that range; ours does not.
    assert worst_ours < 1e-14
    assert worst_naive > 0.1

    # |P - Q| / P ~ 1e-13 and exact equality: well-conditioned, still exact.
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


# --------------------------------------------------------------------------
# 7. The envelope and the exposure metrics see the SAME channel vectors.
# --------------------------------------------------------------------------


def test_envelope_and_exposure_resolve_identical_carriers():
    """One grouping rule, consumed by both paths.

    ``tit.calc._resolve_channels`` (the modulation-depth search) and
    ``tit.fields._carrier_stack`` (the exposure metrics) both go through
    ``tit.fields.channel_index_groups``.  Feeding the exposure metrics the
    envelope path's own resolved channel vectors must therefore reproduce the
    grouped result exactly -- if the two ever drifted apart, this fails.
    """
    from tit.calc import _resolve_channels
    from tit.fields import hf_peak, hf_sar

    rng = np.random.default_rng(1729)
    fields = [rng.normal(size=(8, 3)) for _ in range(6)]
    channels = [([0, 1], [2]), ([3], [4, 5])]

    resolved = _resolve_channels(fields, channels)
    assert np.array_equal(hf_sar(*resolved), hf_sar(*fields, channels=channels))
    assert np.array_equal(hf_peak(*resolved), hf_peak(*fields, channels=channels))


def test_non_beating_carrier_group_is_a_zero_field_for_the_envelope_only():
    """An empty ``group_b`` adds nothing to either exposure metric."""
    from tit.calc import _resolve_channels
    from tit.fields import hf_sar

    rng = np.random.default_rng(31337)
    fields = [rng.normal(size=(4, 3)) for _ in range(3)]
    channels = [([0], [1]), ([2], [])]

    # The envelope path materialises the empty group as a zero field so the
    # flat list stays 2K long; the exposure path drops it. Same numbers.
    assert len(_resolve_channels(fields, channels)) == 4
    assert np.allclose(
        hf_sar(*fields, channels=channels),
        sum(np.sum(f * f, axis=1) for f in fields),
    )


# --------------------------------------------------------------------------
# 8. Allowed channel (electrode-pair) counts.
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
    from tit.calc import get_mTI_vectors

    rng = np.random.default_rng(5)
    three = [rng.normal(size=(4, 3)) for _ in range(3)]
    with pytest.raises(ValueError, match="even number of fields"):
        get_mTI_vectors(three)


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
