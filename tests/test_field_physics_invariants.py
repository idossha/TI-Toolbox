"""Physical laws tying ``tit.calc`` (the TI/mTI envelope) to ``tit.fields`` (the carrier peak and SAR).

Pins (2026-10-22, package p25), on seeded random fields with N = 2, 4, 6 and 8 channels (one
channel = one carrier, so ``hf_peak`` enumerates every sign pattern exactly, N <= 8):

* **envelope <= instantaneous peak**: ``|get_TI_vectors(E)| <= hf_peak(*E)``. Along a direction n
  with projections ``x_i = E_i . n`` the modulation depth is ``sqrt(2)(sqrt(P+Q) - sqrt(P-Q))``
  with ``P = sum x_i^2 / 2`` and ``Q = |sum_k x_ka x_kb|``; ``sqrt(P+Q) - sqrt(P-Q) <= sqrt(2Q)``
  gives ``MD <= 2 sqrt(Q) <= sum_i |x_i| = max_s |sum_i s_i x_i| <= max_s |sum_i s_i E_i|``. The
  computed envelope is evaluated at one direction, so it can never exceed the bound.
* **SAR bracket**: ``hf_sar <= hf_peak^2 <= N hf_sar``. The mean of ``|sum s_i E_i|^2`` over all
  sign patterns is ``sum |E_i|^2`` (cross terms cancel), so the maximum is at least that; and
  ``|sum s_i E_i|^2 <= (sum |E_i|)^2 <= N sum |E_i|^2`` (Cauchy-Schwarz).
* **scaling**: every field times c scales TI_max and hf_peak by |c| and hf_sar by c^2 (all three
  are homogeneous; the direction search compares ratios, so its choice does not move).
* **sign symmetry**: flipping one channel leaves TI_max (N = 2: the closed form depends on |E1.E2|),
  hf_sar (a sum of squares) and hf_peak (a maximum over all sign patterns) unchanged; for mTI,
  flipping both channels of one carrier leaves every product ``x_ka x_kb`` and so TI_max unchanged.
* **a silent carrier**: with one mTI pair at zero, P and Q are those of the remaining pair, so the
  envelope along any direction is the TI envelope of that pair (``get_TI_dir`` evaluates both
  exactly), and the searched mTI maximum is the TI maximum up to the search's sampling.

Expected values come from these derivations, never from running the code; nothing here reads a
fixture. The report's NaN-voxel peak (``np.argmax`` returned the NaN) is pinned in
``tests/test_report_simulation_edges.py::test_peak_ignores_nan_voxels`` (package p03). Real-mesh
versions of these bounds are ``tests/numerical/test_ti_recompute_realdata.py``.
Reproduce: ``.venv/bin/python -m pytest tests/test_field_physics_invariants.py -q``.
"""

from __future__ import annotations

import numpy as np
import pytest

from tit.calc import get_TI_dir, get_TI_vectors
from tit.fields import hf_peak, hf_sar

#: Elements per draw: enough that a bound violated on a few percent of directions shows up.
N_ELEMENTS = 1500
#: Float64 slack for inequalities that hold with equality on some elements (aligned fields).
EPS = 1e-9
#: The K >= 2 direction search samples 192 Fibonacci directions and refines locally, so it can
#: stop short of the true maximum of a kinked envelope. With one pair silent, its worst shortfall
#: against the exact K = 1 closed form was 1.13 % over 4000 random elements and its mean 0.06 %
#: (host probe, 2026-10-22); 2 % and 0.3 % bound the tail and the bulk.
SEARCH_WORST = 0.02
SEARCH_MEAN = 0.003


def _fields(n_channels: int, seed: int) -> list[np.ndarray]:
    """``n_channels`` random fields with magnitudes spread over 0.1-3 V/m per element."""
    rng = np.random.default_rng(seed)
    return [
        rng.normal(size=(N_ELEMENTS, 3)) * rng.uniform(0.1, 3.0, size=(N_ELEMENTS, 1))
        for _ in range(n_channels)
    ]


def _ti(fields: list[np.ndarray]) -> np.ndarray:
    return np.linalg.norm(get_TI_vectors(fields), axis=1)


@pytest.mark.parametrize("n_channels", [2, 4, 6, 8])
def test_the_envelope_never_exceeds_the_instantaneous_carrier_peak(n_channels):
    fields = _fields(n_channels, seed=100 + n_channels)
    ti, peak = _ti(fields), hf_peak(*fields)
    assert np.all(ti <= peak + EPS), float(np.max(ti - peak))
    # The bound is attained by two aligned channels (TI = 2|E| = |E + E|): it is tight, not slack.
    e = fields[0][:1]
    assert _ti([e, e])[0] == pytest.approx(hf_peak(e, e)[0], rel=1e-12)


@pytest.mark.parametrize("n_channels", [2, 4, 6, 8])
def test_the_squared_peak_lies_between_the_sar_and_n_times_the_sar(n_channels):
    fields = _fields(n_channels, seed=200 + n_channels)
    peak2, sar = hf_peak(*fields) ** 2, hf_sar(*fields)
    assert np.all(sar <= peak2 * (1 + EPS)), float(np.max(sar - peak2))
    assert np.all(peak2 <= n_channels * sar * (1 + EPS)), float(
        np.max(peak2 - n_channels * sar)
    )
    # Equalities: orthogonal channels give peak^2 == SAR; N equal aligned channels give N * SAR.
    basis = [np.eye(3)[[i % 3]] for i in range(2)]
    assert hf_peak(*basis)[0] ** 2 == pytest.approx(hf_sar(*basis)[0], rel=1e-12)
    same = [fields[0][:1]] * n_channels
    assert hf_peak(*same)[0] ** 2 == pytest.approx(
        n_channels * hf_sar(*same)[0], rel=1e-12
    )


@pytest.mark.parametrize("n_channels", [2, 4, 6, 8])
@pytest.mark.parametrize("c", [2.5, -3.0, 1e-3])
def test_scaling_every_field_scales_the_envelope_peak_and_sar(n_channels, c):
    fields = _fields(n_channels, seed=300 + n_channels)
    scaled = [c * f for f in fields]
    np.testing.assert_allclose(_ti(scaled), abs(c) * _ti(fields), rtol=1e-9)
    np.testing.assert_allclose(hf_peak(*scaled), abs(c) * hf_peak(*fields), rtol=1e-9)
    np.testing.assert_allclose(hf_sar(*scaled), c**2 * hf_sar(*fields), rtol=1e-9)


@pytest.mark.parametrize("n_channels", [2, 4, 6, 8])
def test_flipping_one_channel_keeps_the_sar_and_the_peak(n_channels):
    fields = _fields(n_channels, seed=400 + n_channels)
    for i in range(n_channels):
        flipped = [-f if j == i else f for j, f in enumerate(fields)]
        np.testing.assert_allclose(hf_sar(*flipped), hf_sar(*fields), rtol=1e-12)
        np.testing.assert_allclose(hf_peak(*flipped), hf_peak(*fields), rtol=1e-12)


def test_flipping_one_channel_of_a_ti_pair_keeps_the_envelope():
    e1, e2 = _fields(2, seed=500)
    ti = _ti([e1, e2])
    np.testing.assert_allclose(_ti([-e1, e2]), ti, rtol=1e-12)
    np.testing.assert_allclose(_ti([e1, -e2]), ti, rtol=1e-12)


@pytest.mark.parametrize("n_channels", [4, 6, 8])
def test_flipping_both_channels_of_one_mti_carrier_keeps_the_envelope(n_channels):
    fields = _fields(n_channels, seed=600 + n_channels)
    ti = _ti(fields)
    for k in range(n_channels // 2):
        flipped = [-f if j // 2 == k else f for j, f in enumerate(fields)]
        np.testing.assert_allclose(_ti(flipped), ti, rtol=1e-9)
    # One channel alone is not a symmetry of mTI (its product changes sign), so the test above
    # is not vacuous: the envelope does move somewhere.
    one = [-fields[0]] + fields[1:]
    assert np.max(np.abs(_ti(one) - ti) / ti) > 0.01


@pytest.mark.parametrize("silent", [0, 1])
def test_an_mti_montage_with_one_silent_pair_is_the_ti_of_the_other(silent):
    e1, e2 = _fields(2, seed=700 + silent)
    zero = np.zeros_like(e1)
    mti = [zero, zero, e1, e2] if silent == 0 else [e1, e2, zero, zero]
    ti_vec = get_TI_vectors([e1, e2])
    ti = np.linalg.norm(ti_vec, axis=1)

    # Exact along any direction: the silent pair adds nothing to P or Q.
    directions = np.random.default_rng(701).normal(size=e1.shape)
    np.testing.assert_allclose(
        get_TI_dir(mti, directions), get_TI_dir([e1, e2], directions), rtol=1e-12
    )
    # Along the TI optimum the mTI envelope is the TI maximum.
    np.testing.assert_allclose(get_TI_dir(mti, ti_vec), ti, rtol=1e-6)

    # The searched maximum is evaluated at one direction, so it never exceeds the exact one,
    # and the 192-direction search with refinement stops short by little.
    searched = _ti(mti)
    assert np.all(searched <= ti + EPS), float(np.max(searched - ti))
    shortfall = (ti - searched) / ti
    assert shortfall.max() <= SEARCH_WORST, float(shortfall.max())
    assert shortfall.mean() <= SEARCH_MEAN, float(shortfall.mean())
