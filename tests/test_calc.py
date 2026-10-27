"""``tit.calc``: the TI/mTI envelope and the carrier metrics, each against an independent oracle.

What this pins (2026-10-26, the five-function envelope API):

* ``envelope`` -- the phasor definition: along ``n`` pair ``k`` beats as ``a_k + b_k e^{i phi}``,
  the carriers' powers add, and the envelope is max - min over ``phi`` of
  ``sqrt(sum_k |a_k + b_k e^{i phi}|^2)``; sampled here on a ``phi`` grid, never the closed form.
* ``envelope_max`` -- K=1 against Grossman et al. 2017's published preprocess-then-branch formula
  (re-implemented below, vector and magnitude) and a dense sphere search; K>=2 against a dense
  sphere search (a lower bound: every value it reports is attained), on random K=2/3/4 fields,
  an unpaired carrier (a pair with a zero field), degenerate sets and six real grey-matter
  elements an earlier solver missed; the plane maximum
  against a dense in-plane angle scan and against the sphere maximum of the projected fields.
* ``envelope_mean`` -- 2x10^5-point equal-area sphere quadrature of the definition.
* ``hf_peak`` -- full ``2**N`` sign enumeration (itertools), Cassarà 2025 Part I Eq. 3 at N=2,
  and the zonotope support ``max_n sum |E_c . n|`` on a dense grid (lower bound).
* ``hf_power`` -- a numerically time-averaged ``|E(t)|^2`` of 2 and 4 incommensurate carriers
  (and of one shared carrier for ``coherent``), and ``sum |E_c|^2 / 2`` written out longhand.
* invariances (pair order, swap within a pair, sign flips, rotation, scale), the direction
  convention, chunking, shapes and validation errors.

Where the numbers come from: closed forms written out in each test, derivations in
``docs/wiki/analyzer.md``, and the oracles above; no value is read back from ``tit.calc``. The six real
elements (``REAL_GM_FIELDS``, ``REAL_GM_ROOT_FIELDS``) are sub-101 grey-matter E fields (V/m) at which the reference
eigen-branch solver without the Newton polish fell 0.13-0.65 % below the old sweep; their
expected values are a dense search run here.

Tolerances: an oracle that is itself a sampled maximum is a lower bound, so ``tit.calc`` must not
fall below it by more than round-off (1e-12 relative, or 1e-9 against the 2x10^5-direction
search whose values are float-summed differently); how far a grid falls short of the true maximum
is its resolution, bounded to show the oracle is tight: median 1e-8, and under 1 % of elements more
than 1e-6 below (where the grid's best point sat on a lower local peak and the cap search stayed there).

Expected numerical shifts vs the API before 2026-10-26 (``get_TI_*``), stated here because no
test may pin the old numbers: K=1 ``TI_avg`` moved from a 192-direction grid to the exact closed
form (random fields: up to 3.1 % per element, mean ~0; sub-101 grey matter: max 4.6 %, p99 1.8 %,
mean -0.09 % / +0.49 % for the two pairs); ``mTI_max`` rises where the old sweep undershot
(sub-101 grey matter K=2: 6.5 % of elements > 1e-3 low, worst 9.8 %, mean +0.023 %); ``TI_max``
(K=1) and ``TI_normal`` are unchanged to round-off.

Reproduce: ``.venv/bin/python -m pytest tests/test_calc.py -q -p no:cacheprovider``.
Deliberately elsewhere: SimNIBS ``get_maxTI``/``get_dirTI`` agreement
(``tests/numerical/test_calc_vs_simnibs.py``, image only); time-domain carrier checks of
``hf_peak``/``hf_power`` (``tests/numerical/test_sci07_exposure_channels.py``); the envelope vs
carrier-metric inequalities (``tests/test_field_physics_invariants.py``).
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from tit import calc
from tit.calc import envelope, envelope_max, envelope_mean, hf_peak, hf_power

# ---------------------------------------------------------------------------
# Oracles (independent of tit.calc)
# ---------------------------------------------------------------------------


def random_fields(seed: int, n: int, n_fields: int) -> list[np.ndarray]:
    """Gaussian directions, log-normal magnitudes: field ratios span ~2 decades."""
    rng = np.random.default_rng(seed)
    e = rng.standard_normal((n_fields, n, 3)) * np.exp(
        rng.normal(0.0, 0.7, (n_fields, n, 1))
    )
    return list(e)


def sphere_points(m: int, hemisphere: bool = True) -> np.ndarray:
    """``m`` equal-area Fibonacci directions on the upper hemisphere (or the sphere)."""
    i = np.arange(m) + 0.5
    z = 1.0 - i / m if hemisphere else 1.0 - 2.0 * i / m
    r = np.sqrt(1.0 - z * z)
    t = np.pi * (3.0 - np.sqrt(5.0)) * i
    return np.stack([r * np.cos(t), r * np.sin(t), z], axis=-1)


def envelope_naive(fields, dirs):
    """``| |S n| - |D n| |`` at ``dirs`` (D, 3) for every element: (N, D)."""
    p = np.einsum("fnx,dx->fnd", np.asarray(fields), dirs)
    a, b = p[0::2], p[1::2]
    return np.abs(np.sqrt(((a + b) ** 2).sum(0)) - np.sqrt(((a - b) ** 2).sum(0)))


def envelope_stable(E, dirs):
    """``4 |sum a_k b_k| / (|S n| + |D n|)`` at per-element ``dirs`` (N, D, 3): (N, D)."""
    p = np.einsum("fnx,ndx->fnd", E, dirs)
    a, b = p[0::2], p[1::2]
    den = np.sqrt(((a + b) ** 2).sum(0)) + np.sqrt(((a - b) ** 2).sum(0))
    return np.divide(
        4 * np.abs((a * b).sum(0)), den, out=np.zeros(den.shape), where=den > 0
    )


def dense_max(fields, m=40_000, chunk=200, rounds=40):
    """A dense hemisphere grid, then 40 shrinking 48-point spiral caps around its best point.

    Every value is the envelope at a real direction, so the result is a lower bound on the true
    maximum; the cap search makes it tight (~1e-8) even at a cusp, where the envelope peaks like
    ``|theta|`` and a grid alone falls short to first order.
    """
    dirs = sphere_points(m)
    E = np.asarray(fields)
    best = np.empty((E.shape[1], 3))
    for lo in range(0, E.shape[1], chunk):
        sl = slice(lo, lo + chunk)
        best[sl] = dirs[envelope_naive(E[:, sl], dirs).argmax(axis=1)]
    value = envelope_stable(E, best[:, None])[:, 0]
    k = np.arange(48) + 0.5
    radius = 1.2 * np.sqrt(2 * np.pi / m)
    for _ in range(rounds):
        r, ph = radius * np.sqrt(k / 48), np.pi * (3 - np.sqrt(5)) * k
        ref = np.where(np.abs(best[:, :1]) > 0.9, Y, X)
        u = unit(np.cross(best, ref))
        w = np.cross(best, u)
        cand = (
            np.cos(r)[None, :, None] * best[:, None]
            + (np.sin(r) * np.cos(ph))[None, :, None] * u[:, None]
            + (np.sin(r) * np.sin(ph))[None, :, None] * w[:, None]
        )
        f = envelope_stable(E, cand)
        j = f.argmax(1)
        better = f[np.arange(len(j)), j] > value
        value[better] = f[better, j[better]]
        best[better] = cand[better, j[better]]
        radius *= 0.75
    return value


def grossman_vector(E1, E2):
    """Grossman et al. 2017 STAR Methods, as published: order by magnitude, flip into the acute
    angle, then 2|E2| if |E2| < |E1| cos(alpha), else 2|E2 x (E1-E2)| / |E1-E2|; as a vector,
    2 E2 or twice E2's part perpendicular to E1 - E2."""
    out = np.empty_like(E1)
    for i, (a, b) in enumerate(zip(E1, E2)):
        if np.linalg.norm(b) > np.linalg.norm(a):
            a, b = b, a
        if a @ b < 0:
            b = -b
        cos_alpha = a @ b / (np.linalg.norm(a) * np.linalg.norm(b))
        if np.linalg.norm(b) < np.linalg.norm(a) * cos_alpha:
            out[i] = 2 * b
        else:
            h = (a - b) / np.linalg.norm(a - b)
            out[i] = 2 * (b - (b @ h) * h)
    return out


def sign_enumeration(fields):
    """``max_s |sum_c s_c E_c|`` over all ``2**N`` sign patterns."""
    E = np.asarray(fields)
    best = np.zeros(E.shape[1])
    for signs in itertools.product((1.0, -1.0), repeat=len(E)):
        total = np.einsum("f,fnx->nx", np.array(signs), E)
        best = np.maximum(best, np.linalg.norm(total, axis=1))
    return best


def rotation(seed: int) -> np.ndarray:
    q, r = np.linalg.qr(np.random.default_rng(seed).standard_normal((3, 3)))
    return q * np.sign(np.diag(r))


def unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


X, Y, Z = np.eye(3)


def row(*v):
    return np.array([v], dtype=float)


# ---------------------------------------------------------------------------
# envelope
# ---------------------------------------------------------------------------


class TestEnvelope:
    @pytest.mark.parametrize("k", [1, 2, 3, 4])
    def test_matches_the_phasor_beat_of_the_projected_fields(self, k):
        fields = random_fields(10 + k, 300, 2 * k)
        n = np.random.default_rng(20 + k).standard_normal((300, 3))
        p = np.einsum("fnx,nx->fn", np.asarray(fields), unit(n))
        phi = np.linspace(0.0, 2 * np.pi, 4097)
        beat = p[0::2, :, None] + p[1::2, :, None] * np.exp(1j * phi)
        amp = np.sqrt((np.abs(beat) ** 2).sum(axis=0))
        # The extremes sit at phi = 0 and pi, both on the grid: max - min is exact.
        np.testing.assert_allclose(
            envelope(fields, n), amp.max(1) - amp.min(1), rtol=1e-10, atol=1e-14
        )

    def test_k1_is_twice_the_smaller_projection(self):
        e1, e2 = random_fields(3, 500, 2)
        n = unit(np.random.default_rng(4).standard_normal((500, 3)))
        a, b = np.sum(e1 * n, 1), np.sum(e2 * n, 1)
        np.testing.assert_allclose(
            envelope([e1, e2], n), 2 * np.minimum(abs(a), abs(b)), rtol=1e-12
        )

    def test_direction_is_normalised_and_broadcast(self):
        fields = random_fields(5, 50, 4)
        d = np.array([0.3, -2.0, 0.7])
        np.testing.assert_allclose(
            envelope(fields, 5 * d), envelope(fields, np.tile(d, (50, 1))), rtol=1e-13
        )

    def test_zero_direction_and_null_fields_give_zero(self):
        fields = random_fields(6, 4, 2)
        assert np.array_equal(envelope(fields, np.zeros((4, 3))), np.zeros(4))
        assert np.array_equal(envelope([np.zeros((4, 3))] * 4, X), np.zeros(4))

    def test_weak_modulation_keeps_its_relative_accuracy(self):
        # |S n| and |D n| agree to ~q, so their naive difference keeps only ~eps/q relative
        # accuracy; the reference is the same difference in 60-digit decimal arithmetic.
        from decimal import Decimal, getcontext

        getcontext().prec = 60
        for q in (1e-8, 1e-12, 1e-16, 1e-20):
            a, b = (1.0, 0.7), (q, -0.5 * q)
            fields = [row(v, 0, 0) for pair in zip(a, b) for v in pair]
            A, B = [Decimal(x) for x in a], [Decimal(x) for x in b]
            s = sum((x + y) ** 2 for x, y in zip(A, B)).sqrt()
            d = sum((x - y) ** 2 for x, y in zip(A, B)).sqrt()
            assert envelope(fields, X)[0] == pytest.approx(
                float(abs(s - d)), rel=1e-14, abs=0
            )

    def test_collinear_k1(self):
        assert envelope([row(1, 0, 0), row(0.5, 0, 0)], X)[0] == pytest.approx(1.0)
        assert envelope([row(1, 0, 0), row(0.5, 0, 0)], Y)[0] == 0.0


# ---------------------------------------------------------------------------
# envelope_max -- K = 1
# ---------------------------------------------------------------------------


class TestEnvelopeMaxK1:
    def test_matches_grossman_2017_vector_and_magnitude(self):
        e1, e2 = random_fields(30, 2000, 2)
        ref = grossman_vector(e1, e2)
        amp, n = envelope_max([e1, e2], return_direction=True)
        np.testing.assert_allclose(amp, np.linalg.norm(ref, axis=1), rtol=1e-12)
        # The TI-vector orientation is kept: amp * n_hat is Grossman's vector.
        np.testing.assert_allclose(amp[:, None] * n, ref, rtol=1e-11, atol=1e-14)

    def test_never_below_a_dense_sphere_search(self):
        fields = random_fields(31, 1000, 2)
        amp = envelope_max(fields)
        dense = dense_max(fields)
        assert np.all(amp >= dense * (1 - 1e-12))
        assert np.median((amp - dense) / amp) < 1e-8

    @pytest.mark.parametrize(
        "e1, e2, expected",
        [
            ((2, 0, 0), (1, 0, 0), 2.0),  # parallel: 2 min
            ((2, 0, 0), (-1, 0, 0), 2.0),  # antiparallel: the sign is irrelevant
            (
                (1, 0, 0),
                (0, 1, 0),
                np.sqrt(2),
            ),  # orthogonal equal: 2*|E2 x h|/|h|, h=E1-E2
            ((1, 2, 3), (1, 2, 3), 2 * np.sqrt(14)),  # identical
            ((1, 0, 0), (0, 0, 0), 0.0),  # one field silent
            ((0, 0, 0), (0, 0, 0), 0.0),  # null: 0, not NaN
            ((1, 0, 0), (1e-9, 1e-9, 0), 2e-9 * np.sqrt(2)),  # one weak field: 2|E2|
        ],
    )
    def test_analytic_cases(self, e1, e2, expected):
        amp, n = envelope_max([row(*e1), row(*e2)], return_direction=True)
        assert amp[0] == pytest.approx(expected, rel=1e-12, abs=1e-300)
        assert np.linalg.norm(n[0]) == pytest.approx(1.0)
        if expected == 0:
            assert np.array_equal(n[0], X)  # every direction maximises 0: n_hat is x

    def test_orthogonal_equal_direction_bisects(self):
        _, n = envelope_max([row(1, 0, 0), row(0, 1, 0)], return_direction=True)
        np.testing.assert_allclose(n[0], unit(np.array([1.0, 1, 0])), atol=1e-15)


# ---------------------------------------------------------------------------
# envelope_max -- K >= 2, sphere
# ---------------------------------------------------------------------------

#: Four sub-101 grey-matter elements (V/m), fields [E1a, E1b, E2a, E2b] (pairing (LI1,TH1),
#: (LI2,TH2)) at which the reference eigen-branch root-find with a pattern-search polish fell
#: 0.13 %, 0.65 %, 2e-5 and 1e-4 below the old 192-direction sweep: two optima on a branch
#: whose g-roots share a grid interval, two on a narrow ridge.  ``REAL_GM_ROOT_FIELDS`` are two
#: more (pairings (LI1,LI2),(TH1,TH2) and (LI1,TH1),(LI2,TH2)) that the grid, safeguards and
#: Newton polish alone miss by 1.7e-4 and 2.2e-3: only the root-find reaches them.
REAL_GM_ROOT_FIELDS = np.array(
    [
        [
            [0.23604662967385384, 0.10551601803494715, 0.04470417420184087],
            [0.0087835115465272, 0.009379244653471746, 0.003218172550415311],
        ],
        [
            [-0.016982077299944387, 0.0018672328075365972, 0.0043453229782477],
            [-0.012067687656791365, -0.03340727514978171, 0.004730855918156364],
        ],
        [
            [0.04763998600670016, -0.040670135735502, 0.02530296444775025],
            [0.0017302317808746603, 0.006849722341950308, 0.014755124744149537],
        ],
        [
            [-0.09790215070286214, -0.03079459912281418, 0.023787587290632402],
            [0.10825148803542052, -0.2198988087391586, -0.03705426610942932],
        ],
    ]
)
REAL_GM_FIELDS = np.array(
    [
        [
            [0.014645279383607419, 0.005854487941767347, -0.017842365707282516],
            [0.0033920984591539857, -0.030405369616642402, -0.015321458427914662],
            [0.008432176885254189, -0.03268597695734617, -0.012115496176596569],
            [0.009619036253222557, -0.022932942038271422, -0.00942037158596825],
        ],
        [
            [-0.09016831092257259, -0.06112520059757962, -0.055504466633187706],
            [-0.06040754833473857, -0.2049123496432932, -0.051300345423474676],
            [-0.0076214201959858415, -0.2185390022054589, -0.05458205740088709],
            [-0.03057364613978285, -0.254422767239979, -0.10929000641067245],
        ],
        [
            [0.020436567394418965, 0.008579211351619372, 0.10004059953440839],
            [0.0016835531781650252, 0.10501687361121714, 0.05822233044820406],
            [-0.01704159757661434, 0.18442819283633338, 0.1030487853093919],
            [-0.08471546350267443, 0.17674369095379153, 0.14248808224652934],
        ],
        [
            [-0.0151491184965877, -0.013090836243758787, -0.028588630189741893],
            [-0.01608622061556481, -0.06149127296326966, -0.018412350840814964],
            [0.002728233723066453, -0.048879130077034906, -0.01630749130444984],
            [0.004323287619792266, -0.040463831965530814, -0.015106841998440116],
        ],
    ]
)


def degenerate_sets(n=400):
    e = random_fields(41, n, 4)
    zero = np.zeros_like(e[0])
    return {
        "second pair zero": [e[0], e[1], zero, zero],
        "first pair zero": [zero, zero, e[2], e[3]],
        "all fields in one plane": [f * np.array([1.0, 1.0, 0.0]) for f in e],
        "second pair 1e-2 weaker": [e[0], e[1], 1e-2 * e[2], 1e-2 * e[3]],
        "all fields collinear": [f[:, :1] * X for f in e],
    }


class TestEnvelopeMaxSphere:
    @pytest.mark.parametrize("k", [2, 3, 4])
    def test_random_never_below_a_dense_sphere_search(self, k):
        fields = random_fields(50 + k, 1000, 2 * k)
        amp, n = envelope_max(fields, return_direction=True)
        dense = dense_max(fields)
        # amp is attained at n_hat, so it is <= the true maximum ...
        np.testing.assert_allclose(envelope(fields, n), amp, rtol=1e-13)
        # ... and >= every dense-grid direction.
        rel = (amp - dense) / amp
        assert rel.min() >= -1e-12, rel.min()
        assert np.median(rel) < 1e-8 and np.mean(rel > 1e-6) < 0.01

    @pytest.mark.parametrize("name", list(degenerate_sets()))
    def test_degenerate_sets_never_below_a_dense_search(self, name):
        fields = degenerate_sets()[name]
        amp, n = envelope_max(fields, return_direction=True)
        dense = dense_max(fields)
        np.testing.assert_allclose(envelope(fields, n), amp, rtol=1e-12, atol=1e-15)
        assert np.all(amp >= dense * (1 - 1e-12) - 1e-15)

    def test_unpaired_carrier_never_below_a_dense_sphere_search(self):
        # A carrier with no beating partner is a pair with a zero field: it adds to |S n| and
        # |D n| alike and to no beat term, so the envelope can only drop along every n.
        e1, e2, eu = random_fields(62, 1000, 3)
        eu = eu * np.random.default_rng(63).uniform(0.0, 2.0, (1000, 1))
        fields = [e1, e2, eu, np.zeros_like(eu)]
        amp, n = envelope_max(fields, return_direction=True)
        dense = dense_max(fields)
        np.testing.assert_allclose(envelope(fields, n), amp, rtol=1e-13)
        rel = (amp - dense) / amp
        assert rel.min() >= -1e-12, rel.min()
        # Oracle tightness: the extra carrier flattens the envelope into more local peaks, so the
        # grid's best point sits on a lower one more often (1.4 % of these elements > 1e-6 below
        # the solver, measured 2026-10-26) -- looseness of the oracle, in the solver's favour.
        assert np.median(rel) < 1e-8 and np.mean(rel > 1e-6) < 0.03
        assert np.all(amp <= envelope_max([e1, e2]) * (1 + 1e-12))

    def test_a_silent_pair_reduces_to_grossman(self):
        e1, e2 = random_fields(60, 500, 2)
        zero = np.zeros_like(e1)
        ref = np.linalg.norm(grossman_vector(e1, e2), axis=1)
        np.testing.assert_allclose(envelope_max([e1, e2, zero, zero]), ref, rtol=1e-12)
        np.testing.assert_allclose(envelope_max([zero, zero, e1, e2]), ref, rtol=1e-12)

    def test_collinear_fields_peak_along_their_axis(self):
        # Every projection scales by cos(theta), so E_AM(n) = |cos theta| E_AM(u).
        a, b = np.array([1.0, 0.5]), np.array([0.3, -0.2])
        u = unit(np.array([1.0, -2.0, 0.5]))
        fields = [np.array([v * u]) for pair in zip(a, b) for v in pair]
        s, d = np.linalg.norm(a + b), np.linalg.norm(a - b)
        amp, n = envelope_max(fields, return_direction=True)
        assert amp[0] == pytest.approx(abs(s - d), rel=1e-12)
        assert abs(n[0] @ u) == pytest.approx(1.0, abs=1e-12)

    def test_real_grey_matter_cases_an_earlier_solver_missed(self):
        fields = list(np.concatenate([REAL_GM_FIELDS, REAL_GM_ROOT_FIELDS], axis=1))
        amp = envelope_max(fields)
        dense = dense_max(fields, m=200_000)
        assert np.all(amp >= dense * (1 - 1e-9)), (amp - dense) / dense

    def test_k1_optimum_is_a_lower_bound_for_each_pair(self):
        # Adding a beating pair can lower E_AM along a given n, but the maximum over n is never
        # below what either pair's own optimum direction gives with all pairs present.
        fields = random_fields(61, 500, 4)
        amp = envelope_max(fields)
        for k in range(2):
            _, nk = envelope_max(fields[2 * k : 2 * k + 2], return_direction=True)
            assert np.all(amp >= envelope(fields, nk) * (1 - 1e-12))


# ---------------------------------------------------------------------------
# envelope_max -- invariances and the direction convention
# ---------------------------------------------------------------------------


class TestEnvelopeMaxInvariance:
    @pytest.mark.parametrize("k", [1, 2, 3])
    def test_pair_order_swap_within_pair_and_pair_sign_flip(self, k):
        fields = random_fields(70 + k, 300, 2 * k)
        ref = envelope_max(fields)
        pairs = [fields[2 * i : 2 * i + 2] for i in range(k)]
        variants = [
            [f for p in reversed(pairs) for f in p],  # carrier order
            [f for p in pairs for f in reversed(p)],  # swap within each pair
            [-f for f in fields[:2]] + fields[2:],  # flip both fields of a pair
        ]
        for v in variants:
            np.testing.assert_allclose(envelope_max(v), ref, rtol=1e-9)

    def test_k1_single_field_flip_is_a_symmetry_k2_is_not(self):
        e = random_fields(75, 300, 4)
        np.testing.assert_allclose(
            envelope_max([-e[0], e[1]]), envelope_max(e[:2]), rtol=1e-12
        )
        moved = envelope_max([-e[0]] + e[1:])
        assert np.max(np.abs(moved / envelope_max(e) - 1)) > 1e-2

    @pytest.mark.parametrize("k", [1, 2])
    def test_rotation_rotates_the_maximiser(self, k):
        fields = random_fields(80 + k, 300, 2 * k)
        R = rotation(81)
        amp, n = envelope_max(fields, return_direction=True)
        amp_r, n_r = envelope_max([f @ R.T for f in fields], return_direction=True)
        np.testing.assert_allclose(amp_r, amp, rtol=1e-9)
        # n and -n are equally maximisers; the orientation rule is rotation-equivariant.
        np.testing.assert_allclose(n_r, n @ R.T, atol=1e-6)

    @pytest.mark.parametrize("c", [3.0, -0.5, 1e-6])
    def test_scale(self, c):
        fields = random_fields(85, 200, 4)
        np.testing.assert_allclose(
            envelope_max([c * f for f in fields]),
            abs(c) * envelope_max(fields),
            rtol=1e-9,
        )

    @pytest.mark.parametrize("k", [2, 3])
    def test_k2_direction_points_along_the_largest_field(self, k):
        fields = random_fields(86 + k, 300, 2 * k)
        _, n = envelope_max(fields, return_direction=True)
        E = np.asarray(fields)
        big = E[np.linalg.norm(E, axis=2).argmax(0), np.arange(300)]
        assert np.all(np.sum(n * big, axis=1) >= 0)
        np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1.0, rtol=1e-14)


# ---------------------------------------------------------------------------
# envelope_max -- plane (perpendicular_to)
# ---------------------------------------------------------------------------


def plane_scan(fields, normals, m=20_000):
    """Max of the envelope over ``m`` angles in the plane perpendicular to each normal."""
    E = np.asarray(fields)
    nrm = unit(normals)
    ref = np.where(np.abs(nrm[:, :1]) > 0.9, Y, X)
    e1 = unit(np.cross(nrm, ref))
    e2 = np.cross(nrm, e1)
    phi = (np.arange(m) + 0.5) * np.pi / m
    out = np.empty(E.shape[1])
    for i in range(E.shape[1]):
        d = np.cos(phi)[:, None] * e1[i] + np.sin(phi)[:, None] * e2[i]
        out[i] = envelope_naive(E[:, i : i + 1], d)[0].max()
    return out


class TestEnvelopeMaxPlane:
    @pytest.mark.parametrize("k", [1, 2, 3, 4])
    def test_never_below_an_in_plane_scan(self, k):
        fields = random_fields(90 + k, 300, 2 * k)
        normals = np.random.default_rng(99).standard_normal((300, 3))
        amp, n = envelope_max(fields, perpendicular_to=normals, return_direction=True)
        scan = plane_scan(fields, normals)
        rel = (amp - scan) / amp
        assert rel.min() >= -1e-12 and np.median(rel) < 1e-6
        np.testing.assert_allclose(np.sum(n * unit(normals), axis=1), 0.0, atol=1e-14)
        np.testing.assert_allclose(envelope(fields, n), amp, rtol=1e-12)

    @pytest.mark.parametrize("k", [1, 2, 3])
    def test_equals_the_sphere_maximum_of_the_projected_fields(self, k):
        fields = random_fields(100 + k, 300, 2 * k)
        m = unit(np.random.default_rng(201).standard_normal((300, 3)))
        projected = [f - np.sum(f * m, 1, keepdims=True) * m for f in fields]
        np.testing.assert_allclose(
            envelope_max(fields, perpendicular_to=m), envelope_max(projected), rtol=1e-9
        )

    def test_k1_is_grossman_on_the_projected_fields(self):
        e1, e2 = random_fields(105, 300, 2)
        m = unit(np.random.default_rng(106).standard_normal((300, 3)))
        p1, p2 = (f - np.sum(f * m, 1, keepdims=True) * m for f in (e1, e2))
        ref = np.linalg.norm(grossman_vector(p1, p2), axis=1)
        np.testing.assert_allclose(
            envelope_max([e1, e2], perpendicular_to=m), ref, rtol=1e-12
        )

    def test_normal_broadcast_zero_normal_and_degenerate_plane(self):
        fields = random_fields(107, 20, 4)
        np.testing.assert_allclose(
            envelope_max(fields, perpendicular_to=2 * Z),
            envelope_max(fields, perpendicular_to=np.tile(Z, (20, 1))),
            rtol=1e-14,
        )
        normals = np.tile(Z, (20, 1))
        normals[3] = 0.0
        amp, n = envelope_max(fields, perpendicular_to=normals, return_direction=True)
        assert amp[3] == 0.0 and np.linalg.norm(n[3]) == pytest.approx(1.0)
        # Fields along the normal have no in-plane part: 0, with an in-plane unit direction.
        along = [f[:, 2:] * Z for f in fields]
        amp, n = envelope_max(along, perpendicular_to=Z, return_direction=True)
        assert np.array_equal(amp, np.zeros(20))
        np.testing.assert_allclose(n @ Z, 0.0, atol=1e-15)
        np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1.0)

    def test_cusp_maximum_with_collinear_difference_rows(self):
        # In-plane, S rows along a and D rows along b (a perpendicular to b): along
        # n = cos(p) a + sin(p) b the envelope is | |s| |cos p| - |d| |sin p| |, so the maximum
        # max(|s|, |d|) sits on a cusp -- at n = a (v = |D n|^2 / 2 touches zero) or n = b
        # (u touches zero). Out-of-plane parts are projected away.
        rng = np.random.default_rng(110)
        a, b = unit(np.array([1.0, 1.0, 0.0])), unit(np.array([1.0, -1.0, 0.0]))
        s, d = rng.normal(size=(2, 2, 40))
        fields = []
        for k in range(2):
            out = rng.normal(size=(2, 40, 1)) * Z
            fields += [(s[k, :, None] * a + d[k, :, None] * b) / 2 + out[0]]
            fields += [(s[k, :, None] * a - d[k, :, None] * b) / 2 + out[1]]
        amp, n = envelope_max(fields, perpendicular_to=Z, return_direction=True)
        ns, nd = np.hypot(s[0], s[1]), np.hypot(d[0], d[1])
        np.testing.assert_allclose(amp, np.maximum(ns, nd), rtol=1e-12)
        axis = np.where((ns > nd)[:, None], a, b)
        np.testing.assert_allclose(np.abs(np.sum(n * axis, 1)), 1.0, atol=1e-12)

    def test_fields_collinear_after_projection(self):
        # u(psi) and v(psi) are then proportional, the stationarity polynomial vanishes
        # identically, and the maximum sits at the extremum of u: along the common axis w.
        rng = np.random.default_rng(109)
        w = unit(np.array([1.0, 2.0, 0.0]))
        c = rng.normal(size=(4, 50))
        fields = [ci[:, None] * w + rng.normal(size=(50, 1)) * Z for ci in c]
        s = np.hypot(c[0] + c[1], c[2] + c[3])
        d = np.hypot(c[0] - c[1], c[2] - c[3])
        amp, n = envelope_max(fields, perpendicular_to=Z, return_direction=True)
        np.testing.assert_allclose(amp, np.abs(s - d), rtol=1e-12)
        np.testing.assert_allclose(np.abs(n @ w), 1.0, atol=1e-12)

    def test_in_plane_fields_keep_the_sphere_maximum(self):
        fields = [f * np.array([1.0, 1.0, 0.0]) for f in random_fields(108, 200, 4)]
        np.testing.assert_allclose(
            envelope_max(fields, perpendicular_to=Z), envelope_max(fields), rtol=1e-9
        )


# ---------------------------------------------------------------------------
# envelope_mean
# ---------------------------------------------------------------------------

#: 2x10^5 equal-area hemisphere points (E_AM(n) = E_AM(-n)): quadrature error ~1e-6 relative.
QUAD = sphere_points(200_000)


def quadrature_mean(fields, chunk=10):
    E = np.asarray(fields)
    return np.concatenate(
        [
            envelope_naive(E[:, lo : lo + chunk], QUAD).mean(1)
            for lo in range(0, E.shape[1], chunk)
        ]
    )


class TestEnvelopeMean:
    def test_k1_closed_form_matches_sphere_quadrature(self):
        fields = random_fields(110, 60, 2)
        np.testing.assert_allclose(
            envelope_mean(fields), quadrature_mean(fields), rtol=2e-5
        )

    @pytest.mark.parametrize("k", [2, 3])
    def test_k2_quadrature_within_7e_4_of_a_fine_quadrature(self, k):
        # The documented worst case of the 2048-direction rule is ~7e-4 (measured 5.7e-4 / 5.3e-4
        # on these seeds); a rule whose points are shifted off the cell midpoints exceeds it
        # (8.4e-4 / 8.0e-4).
        fields = random_fields(111 + k, 60, 2 * k)
        rel = np.abs(envelope_mean(fields) / quadrature_mean(fields) - 1)
        assert rel.max() < 7e-4, rel.max()

    @pytest.mark.parametrize(
        "e1, e2, expected",
        [
            ((1, 0, 0), (0.5, 0, 0), 0.5),  # 2 * 0.5 * mean|cos| over the sphere = 0.5
            ((1, 0, 0), (-0.5, 0, 0), 0.5),
            ((1, 0, 0), (0, 0, 0), 0.0),
            ((0, 0, 0), (0, 0, 0), 0.0),
        ],
    )
    def test_analytic_cases(self, e1, e2, expected):
        assert envelope_mean([row(*e1), row(*e2)])[0] == pytest.approx(
            expected, abs=1e-15
        )

    @pytest.mark.parametrize("k", [1, 2])
    def test_never_exceeds_the_maximum(self, k):
        fields = random_fields(115 + k, 300, 2 * k)
        assert np.all(envelope_mean(fields) <= envelope_max(fields) * (1 + 1e-12))

    def test_a_silent_pair_is_the_k1_mean(self):
        e1, e2 = random_fields(118, 100, 2)
        zero = np.zeros_like(e1)
        rel = envelope_mean([e1, e2, zero, zero]) / envelope_mean([e1, e2]) - 1
        assert np.abs(rel).max() < 1e-3


# ---------------------------------------------------------------------------
# hf_peak / hf_power
# ---------------------------------------------------------------------------


def peak_sets():
    e = random_fields(120, 300, 7)
    zero = np.zeros_like(e[0])
    return {
        "planar": [f * np.array([1.0, 1.0, 0.0]) for f in e[:6]],
        "parallel and antiparallel copies": [e[0], 2 * e[0], -e[1], e[1], e[2]],
        "with zero fields": [e[0], zero, e[1], zero, e[2]],
        "all collinear": [f[:, :1] * X for f in e[:5]],
        "duplicated": [e[0], e[1], e[0], e[1]],
    }


class TestHfPeak:
    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 8, 10])
    def test_random_matches_full_sign_enumeration(self, n):
        fields = random_fields(130 + n, 300, n)
        np.testing.assert_allclose(
            hf_peak(fields), sign_enumeration(fields), rtol=1e-12
        )

    @pytest.mark.parametrize("name", list(peak_sets()))
    def test_degenerate_sets_match_full_sign_enumeration(self, name):
        fields = peak_sets()[name]
        np.testing.assert_allclose(
            hf_peak(fields), sign_enumeration(fields), rtol=1e-12
        )

    def test_two_carriers_is_cassara_eq3(self):
        e1, e2 = random_fields(140, 300, 2)
        eq3 = np.maximum(
            np.linalg.norm(e1 + e2, axis=1), np.linalg.norm(e1 - e2, axis=1)
        )
        np.testing.assert_allclose(hf_peak([e1, e2]), eq3, rtol=1e-15)

    def test_is_the_zonotope_support(self):
        fields = random_fields(141, 30, 4)
        dirs = sphere_points(200_000)
        support = (
            np.abs(np.einsum("fnx,dx->fnd", np.asarray(fields), dirs)).sum(0).max(1)
        )
        peak = hf_peak(fields)
        assert np.all(peak >= support * (1 - 1e-12))
        assert np.all(peak <= support * (1 + 1e-4))

    def test_bounds_and_symmetries(self):
        fields = random_fields(142, 300, 5)
        peak = hf_peak(fields)
        norms = np.linalg.norm(np.asarray(fields), axis=2)
        assert np.all(peak >= norms.max(0) * (1 - 1e-12))
        assert np.all(peak <= norms.sum(0) * (1 + 1e-12))
        np.testing.assert_allclose(hf_peak(fields[::-1]), peak, rtol=1e-12)
        np.testing.assert_allclose(hf_peak([-fields[0]] + fields[1:]), peak, rtol=1e-12)
        R = rotation(143)
        np.testing.assert_allclose(hf_peak([f @ R.T for f in fields]), peak, rtol=1e-12)

    def test_coherent_is_the_vector_sum(self):
        fields = random_fields(144, 50, 3)
        np.testing.assert_allclose(
            hf_peak(fields, coherent=True),
            np.linalg.norm(sum(fields), axis=1),
            rtol=1e-15,
        )


def time_averaged_square(vecs, freqs, phases, periods=4000.0, samples=2_000_000):
    """``<|E(t)|^2>`` of ``E(t) = sum_c E_c cos(2 pi f_c t + phi_c)``, sampled over ``periods``
    cycles of the slowest carrier (midpoint rule)."""
    t = (np.arange(samples) + 0.5) * (periods / min(freqs) / samples)
    e_t = sum(
        np.cos(2 * np.pi * f * t + ph)[:, None] * v
        for v, f, ph in zip(vecs, freqs, phases)
    )
    return float(np.mean(np.sum(e_t * e_t, axis=1)))


class TestHfPower:
    @pytest.mark.parametrize("n", [2, 4])
    def test_is_the_time_averaged_square_of_incommensurate_carriers(self, n):
        # Frequencies in ratio 1 : sqrt(2) : sqrt(3) : sqrt(5) never share a period; each cross
        # term averages to O(1 / (2 pi df T)) ~ 1e-4 of the total over 4000 cycles.
        rng = np.random.default_rng(152 + n)
        vecs = [rng.normal(size=3) for _ in range(n)]
        freqs = [1.0, np.sqrt(2), np.sqrt(3), np.sqrt(5)][:n]
        measured = time_averaged_square(vecs, freqs, rng.uniform(0, 2 * np.pi, n))
        got = hf_power([v[None, :] for v in vecs])[0]
        assert got == pytest.approx(measured, rel=1e-3)

    def test_coherent_is_the_time_averaged_square_of_one_shared_carrier(self):
        # dF = 0, in phase: one sinusoid of amplitude E1 + E2; an integer number of periods
        # makes the average exact.
        rng = np.random.default_rng(156)
        vecs = [rng.normal(size=3) for _ in range(2)]
        measured = time_averaged_square(vecs, [1.0, 1.0], [0.4, 0.4], periods=10.0)
        got = hf_power([v[None, :] for v in vecs], coherent=True)[0]
        assert got == pytest.approx(measured, rel=1e-9)
        # ... which differs from the incoherent value by the cross term E1 . E2.
        assert hf_power([v[None, :] for v in vecs])[0] == pytest.approx(
            measured - vecs[0] @ vecs[1], rel=1e-9
        )

    def test_incoherent_and_coherent_longhand(self):
        fields = random_fields(150, 50, 3)
        np.testing.assert_allclose(
            hf_power(fields),
            0.5 * sum(np.sum(f * f, axis=1) for f in fields),
            rtol=1e-14,
        )
        s = sum(fields)
        np.testing.assert_allclose(
            hf_power(fields, coherent=True), 0.5 * np.sum(s * s, 1), rtol=1e-14
        )
        assert hf_power([row(1, 0, 0), row(0, 2, 0)])[0] == pytest.approx(2.5)

    def test_single_carrier(self):
        e = random_fields(151, 10, 1)
        np.testing.assert_allclose(hf_power(e), 0.5 * np.sum(e[0] ** 2, 1), rtol=1e-15)
        np.testing.assert_allclose(hf_peak(e), np.linalg.norm(e[0], axis=1), rtol=1e-15)


# ---------------------------------------------------------------------------
# Chunking, shapes, validation, public surface
# ---------------------------------------------------------------------------


def test_chunking_does_not_change_results(monkeypatch):
    sets = {k: random_fields(160 + k, 23, 2 * k) for k in (1, 2)}
    sets[3] = random_fields(163, 23, 5)
    normals = np.random.default_rng(164).standard_normal((23, 3))
    whole = {
        k: (
            envelope_max(f),
            envelope_max(f, perpendicular_to=normals),
            envelope_mean(f),
        )
        for k, f in sets.items()
        if k < 3
    }
    peak = hf_peak(sets[3])
    monkeypatch.setattr(calc, "_CHUNK", 5)
    monkeypatch.setattr(calc, "_MEAN_CHUNK", 4)
    for k, ref in whole.items():
        got = (
            envelope_max(sets[k]),
            envelope_max(sets[k], perpendicular_to=normals),
            envelope_mean(sets[k]),
        )
        for g, r in zip(got, ref):
            np.testing.assert_array_equal(g, r)
    np.testing.assert_array_equal(hf_peak(sets[3]), peak)


def test_without_numba_the_numpy_path_runs(monkeypatch):
    """No numba: the K>=2 sphere maximum falls back to NumPy (numba is in the image only).

    ``sys.modules["numba"] = None`` makes ``import numba`` raise ImportError, as on a host
    without it; kernel/NumPy agreement is ``tests/numerical/test_calc_kernel.py`` (image).
    """
    import sys

    fields = list(np.concatenate([REAL_GM_FIELDS, REAL_GM_ROOT_FIELDS], axis=1))
    monkeypatch.setitem(sys.modules, "numba", None)
    monkeypatch.delitem(sys.modules, "tit._calc_kernel", raising=False)
    calc._sphere_kernel.cache_clear()
    try:
        with pytest.raises(ImportError, match="numba"):
            import tit._calc_kernel  # noqa: F401
        assert calc._sphere_kernel() is None
        amp, n = envelope_max(fields, return_direction=True)
    finally:
        calc._sphere_kernel.cache_clear()
    np.testing.assert_allclose(envelope(fields, n), amp, rtol=1e-13)
    assert np.all(amp > 0)


def test_a_numba_that_breaks_at_import_falls_back_too(monkeypatch):
    """numba's ``__init__`` raises AttributeError, not ImportError, when a dependency it version-
    checks is unusable (seen in the image with the host conftest's mocked scipy)."""
    import builtins

    real_import = builtins.__import__

    def broken(name, *args, **kwargs):
        if name == "tit._calc_kernel":
            raise AttributeError("__version__")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken)
    calc._sphere_kernel.cache_clear()
    try:
        assert calc._sphere_kernel() is None
    finally:
        calc._sphere_kernel.cache_clear()


def test_empty_input_gives_empty_output():
    empty = [np.zeros((0, 3))] * 4
    for out in (
        envelope(empty, X),
        envelope_max(empty),
        envelope_max(empty, perpendicular_to=Z),
        envelope_mean(empty),
        hf_peak(empty),
        hf_power(empty),
    ):
        assert out.shape == (0,)


def test_inputs_are_not_modified():
    fields = random_fields(170, 20, 4)
    normals = np.random.default_rng(171).standard_normal((20, 3))
    before = [f.copy() for f in fields], normals.copy()
    envelope_max(fields, perpendicular_to=normals, return_direction=True)
    envelope_mean(fields)
    hf_peak(fields)
    for f, b in zip(fields, before[0]):
        np.testing.assert_array_equal(f, b)
    np.testing.assert_array_equal(normals, before[1])


@pytest.mark.parametrize("fn", [envelope_max, envelope_mean, lambda f: envelope(f, X)])
@pytest.mark.parametrize("n", [0, 1, 3, 5])
def test_envelope_functions_need_an_even_number_of_fields(fn, n):
    with pytest.raises(ValueError, match="even number"):
        fn([np.zeros((4, 3))] * n)


@pytest.mark.parametrize("fn", [hf_peak, hf_power])
def test_carrier_metrics_need_at_least_one_field(fn):
    with pytest.raises(ValueError, match="at least one"):
        fn([])


@pytest.mark.parametrize(
    "fields, match",
    [
        ([np.zeros((4, 3)), np.zeros((5, 3))], "share one shape"),
        ([np.zeros((4, 2)), np.zeros((4, 2))], r"\(N, 3\)"),
        ([np.zeros(3), np.zeros(3)], r"\(N, 3\)"),
        (np.zeros((4, 3)), r"\(N, 3\)"),  # one array, not a list of fields
    ],
)
def test_field_shape_errors(fields, match):
    for fn in (envelope_max, hf_peak):
        with pytest.raises(ValueError, match=match):
            fn(fields)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize(
    "fn",
    [
        lambda f: envelope(f, X),
        envelope_max,
        lambda f: envelope_max(f, perpendicular_to=Z),
        envelope_mean,
        hf_peak,
        hf_power,
    ],
)
@pytest.mark.parametrize("k", [1, 2])
def test_non_finite_fields_are_rejected(fn, bad, k):
    fields = random_fields(185, 6, 2 * k)
    fields[-1][4, 1] = bad
    with pytest.raises(
        ValueError, match="non-finite.*1 of 6 elements, first at element 4"
    ):
        fn(fields)


def test_non_finite_directions_are_rejected():
    fields = random_fields(186, 3, 2)
    with pytest.raises(ValueError, match="direction contains non-finite"):
        envelope(fields, [np.nan, 0.0, 1.0])
    with pytest.raises(ValueError, match="perpendicular_to contains non-finite"):
        envelope_max(fields, perpendicular_to=[np.inf, 0.0, 1.0])


def test_direction_and_normal_shape_errors():
    fields = random_fields(180, 4, 2)
    with pytest.raises(ValueError, match="direction"):
        envelope(fields, np.zeros((5, 3)))
    with pytest.raises(ValueError, match="perpendicular_to"):
        envelope_max(fields, perpendicular_to=np.zeros((4, 2)))


def test_public_surface_is_exactly_five_functions():
    assert calc.__all__ == [
        "envelope",
        "envelope_max",
        "envelope_mean",
        "hf_peak",
        "hf_power",
    ]
