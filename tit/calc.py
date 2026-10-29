"""Temporal-interference envelope and carrier-field metrics.

Fields are zero-to-peak amplitudes, ``(N, 3)`` arrays in V/m for zero-to-peak
channel currents, one array per channel (electrodes Ek+ and Ek-).  The
envelope functions take ``fields = [E1, E2, ..., E2K]`` in channel order, paired
positionally: channels ``2k-1`` and ``2k`` form beating pair ``k`` (carriers
``f_k`` and ``f_k + df``, beating at the common difference frequency ``df``), all
K beats phase-aligned (K = 1 is TI, K >= 2 is mTI).  In the formulas ``E_ka`` and
``E_kb`` are pair ``k``'s two channel fields.  The carrier metrics take the
fields of any number >= 1 of channels, one carrier each.

A channel with no beating partner enters the envelope functions with a zero
field as its partner, ``[E1, E2, Eu, np.zeros_like(Eu)]``: it adds to the
carrier power but not to the beat, so it lowers the envelope.  :func:`hf_peak`
and :func:`hf_power` take it as one more channel field in the list.

* :func:`envelope` -- envelope amplitude along a direction (``TI_normal``)
* :func:`envelope_max` -- its maximum over all directions (``TI_max``,
  ``mTI_max``) or within a plane (tangential maximum)
* :func:`envelope_mean` -- its mean over all directions (``TI_avg``)
* :func:`hf_peak` -- peak instantaneous carrier field
* :func:`hf_power` -- time-averaged mean-square carrier field, ``E_rms^2``

The math and the accuracy table are in ``docs/wiki/analyzer.md``.  The K >= 2
sphere maximum runs in the numba kernel :mod:`tit._calc_kernel`; numba is a
hard dependency (the image ships it).

References:
    Grossman et al. 2017, Cell 169(6):1029-1041, STAR Methods (K = 1 envelope).
    Botzanowski et al. 2025, Bioelectron Med 11:7, doi:10.1186/s42234-025-00169-6,
    pp. 4-5 (K >= 2 envelope, extending Grossman's: square, low-pass, square root).
    Hirata et al. 2024, Comput Biol Med 178:108697, Eq. 2 (K = 1 maximum).
    Cassarà et al. 2025, Bioelectromagnetics, Part I 46(2):e22542 and Part II
    46(1):e22536 (carrier metrics); IEEE C95.1-2019 p. 35 (SAR).

The K >= 2 envelope model and the Fibonacci direction grid behind
``_hemisphere_directions`` are ported from Larissa Albantakis's branch
``alba/mTI_testing`` (the solvers here are new); the unpaired-channel
convention follows Michael Sutherland's ``feature/uni_HF`` work.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from tit._calc_kernel import max_sphere as _sphere_kernel
from tit.constants import is_valid_pair_count

__all__ = ["envelope", "envelope_max", "envelope_mean", "hf_peak", "hf_power"]

# Elements per chunk: bounds peak memory independently of the mesh size.
_CHUNK = 16384
# The K>=2 mean holds (chunk, 2048) arrays, so it uses a smaller chunk.
_MEAN_CHUNK = 1024

_SQRT2 = np.sqrt(2.0)

# --- K>=2 sphere maximum (tit._calc_kernel) ---------------------------------
# theta grid: 16 uniform intervals on (0, pi/2) plus 16 log-spaced in tan(theta)
# (tan theta = sqrt(u/v) spans many decades when one beating pair is weak).
_THETA_GRID = np.unique(
    np.concatenate(
        [
            np.linspace(1e-7, np.pi / 2 - 1e-7, 17),
            np.arctan(np.exp(np.linspace(-14.0, 14.0, 17))),
        ]
    )
)
# Illinois iterations per bracketed root and Newton iterations per polish seed; fewer of
# either fails the dense-search tests in tests/test_calc.py.
_ROOT_ITERS = 14
_NEWTON_ITERS = 12


def _hemisphere_directions(n: int) -> np.ndarray:
    """``n`` equal-area (Fibonacci) unit directions with ``z > 0``: the K>=2 mean's quadrature.

    Equal area makes the plain average a sphere integral; ``E_AM(n) = E_AM(-n)``.
    """
    i = np.arange(n) + 0.5
    z = 1.0 - i / n
    r = np.sqrt(1.0 - z * z)
    t = np.pi * (3.0 - np.sqrt(5.0)) * i
    return np.stack([r * np.cos(t), r * np.sin(t), z], axis=-1)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _stack(fields: Sequence[ArrayLike], *, paired: bool) -> np.ndarray:
    """Validate a field list and stack it as ``(F, N, 3)`` float64: every public function's gate.

    Bad input is a ValueError here, not finite garbage from the solvers (the kernel included).
    """
    arrs = [np.asarray(f, dtype=np.float64) for f in fields]
    n = len(arrs)
    if paired and not is_valid_pair_count(n):
        raise ValueError(
            f"fields must be an even number (>= 2) of arrays, one per channel "
            f"and two channels per beating pair: [E1, E2, E3, E4, ...]; got {n}"
        )
    if not paired and n < 1:
        raise ValueError("fields must contain at least one channel field")
    shape = arrs[0].shape
    if len(shape) != 2 or shape[1] != 3:
        raise ValueError(f"each field must have shape (N, 3), got {shape}")
    for i, a in enumerate(arrs[1:], start=1):
        if a.shape != shape:
            raise ValueError(
                f"all fields must share one shape: field 0 has {shape}, "
                f"field {i} has {a.shape}"
            )
    stack = np.stack(arrs)
    bad = ~np.isfinite(stack).all(axis=(0, 2))
    if bad.any():
        raise ValueError(
            f"fields contain non-finite values (NaN or inf) at {int(bad.sum())} of "
            f"{len(bad)} elements, first at element {int(bad.argmax())}"
        )
    return stack


def _unit_rows(v: ArrayLike, n: int, name: str) -> np.ndarray:
    """``(3,)`` or ``(N, 3)`` -> ``(N, 3)`` validated unit rows; zero rows stay zero.

    A zero direction or plane normal is defined input (the result there is 0), not an error.
    """
    v = np.asarray(v, dtype=np.float64)
    if v.shape == (3,):
        v = np.broadcast_to(v, (n, 3))
    elif v.shape != (n, 3):
        raise ValueError(f"{name} must have shape (3,) or ({n}, 3), got {v.shape}")
    if not np.isfinite(v).all():
        raise ValueError(f"{name} contains non-finite values (NaN or inf)")
    norm = np.linalg.norm(v, axis=1, keepdims=True)
    return np.divide(v, norm, out=np.zeros((n, 3)), where=norm > 0)


def _ratio(num, den):
    """``num / den`` with 0 where ``den`` is 0: a null field's envelope is 0, not NaN."""
    return np.divide(num, den, out=np.zeros(np.shape(den)), where=den > 0)


# ---------------------------------------------------------------------------
# envelope
# ---------------------------------------------------------------------------


def envelope(fields: Sequence[ArrayLike], direction: ArrayLike) -> NDArray[np.float64]:
    """Envelope modulation amplitude along a direction.

    ``E_AM(n) = | |S n| - |D n| | = 4 |sum_k a_k b_k| / (|S n| + |D n|)``, with
    ``a_k = E_ka . n``, ``b_k = E_kb . n`` and ``S``, ``D`` the K x 3 matrices
    of rows ``E_ka + E_kb``, ``E_ka - E_kb``; the right-hand form (no
    cancellation) is evaluated.  K = 1 gives ``2 min(|a|, |b|)``.

    Method: closed form, exact for every K.  Literature: Grossman 2017's
    "envelope modulation amplitude along the direction n" (SimNIBS
    ``get_dirTI``); along the cortical normal it is ``TI_normal``.

    Defined edge cases: a zero ``direction`` row and a null field (every
    projection 0) give 0.

    Args:
        fields: ``[E1, E2, ..., E2K]``, one (N, 3) array per channel, in V/m.
        direction: (3,) or (N, 3); normalised internally, a zero row gives 0.

    Returns:
        (N,) peak-to-trough envelope amplitude in V/m.

    Raises:
        ValueError: odd or fewer than two fields, shapes not all one (N, 3),
            NaN or inf, or ``direction`` not (3,) or (N, 3).
    """
    E = _stack(fields, paired=True)
    n = _unit_rows(direction, E.shape[1], "direction")
    p = np.einsum("fnx,nx->fn", E, n)
    a, b = p[0::2], p[1::2]
    # w = u - v = 2 sum a b straight from the projections: _uvw's (s + d)(s - d) would lose
    # the weaker field of a pair to cancellation when the other dominates.
    u = 0.5 * np.sum((a + b) ** 2, axis=0)
    v = 0.5 * np.sum((a - b) ** 2, axis=0)
    return _env_uvw(u, v, 2.0 * np.sum(a * b, axis=0))


# ---------------------------------------------------------------------------
# envelope_max
# ---------------------------------------------------------------------------


def envelope_max(
    fields: Sequence[ArrayLike],
    *,
    perpendicular_to: ArrayLike | None = None,
    return_direction: bool = False,
) -> NDArray[np.float64] | tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Maximum of the envelope over all directions, or within a plane.

    ``max_n E_AM(n)`` over unit ``n`` (:func:`envelope`), or over the unit ``n``
    perpendicular to ``perpendicular_to``, which equals the sphere maximum of
    the fields projected onto that plane.

    Method: K = 1, sphere or plane, is an exact closed form (SimNIBS
    ``get_maxTI`` to ~1e-15; 0 on null fields).  K >= 2 is exact in a plane
    (polynomial roots); on the sphere, an eigen-branch root-find plus Newton
    polish, never measured more than 1e-6 relative below a dense direction
    search.  Literature: Grossman 2017's "maximal modulation
    amplitude along any orientation" (SimNIBS ``TImax``), K = 1 in the form of
    Hirata 2024 Eq. 2.  Outputs ``TI_max``/``mTI_max``; the plane form is the
    tangential maximum.

    Args:
        fields: ``[E1, E2, ..., E2K]``, one (N, 3) array per channel, in V/m.
        perpendicular_to: plane normal(s), (3,) or (N, 3); ``None`` maximises
            over the sphere.  Normalised internally; a zero row gives 0.
        return_direction: also return the maximising unit direction.

    Returns:
        ``amp`` (N,) in V/m, or ``(amp, n_hat)`` with ``n_hat`` (N, 3) unit.
        ``-n_hat`` is equally a maximiser; the sign gives ``n_hat . E_L >= 0``
        for ``E_L`` the largest (projected) field, so at K = 1 ``amp * n_hat``
        is the Grossman TI vector.  Where ``amp == 0``, ``n_hat`` is (1, 0, 0),
        or an in-plane unit vector for a plane.

    Raises:
        ValueError: the :func:`envelope` errors for ``fields``, or
            ``perpendicular_to`` not (3,) or (N, 3) or containing NaN or inf.
        RuntimeError: K >= 2 on the sphere, a 3x3 eigen-solve in the kernel did
            not converge (seen only for fields that overflow float64 once squared).
    """
    E = _stack(fields, paired=True)
    n_el = E.shape[1]
    plane = perpendicular_to is not None
    if plane:
        m = _unit_rows(perpendicular_to, n_el, "perpendicular_to")
        E = E - np.einsum("fnx,nx->fn", E, m)[..., None] * m
        E[:, ~m.any(axis=1)] = 0.0  # undefined plane -> 0, like a zero direction
    k = E.shape[0] // 2

    amp = np.empty(n_el)
    n_hat = np.empty((n_el, 3))
    for lo in range(0, n_el, _CHUNK):
        sl = slice(lo, min(lo + _CHUNK, n_el))
        if k == 1:
            amp[sl], n_hat[sl] = _max_k1(E[0, sl], E[1, sl])
        elif plane:
            amp[sl], n_hat[sl] = _max_plane(E[:, sl], m[sl])
        else:
            amp[sl], n_hat[sl] = _max_sphere(E[:, sl])
    if not return_direction:
        return amp

    if k >= 2:
        norms = np.linalg.norm(E, axis=2)
        e_big = E[norms.argmax(axis=0), np.arange(n_el)]
        n_hat[np.einsum("nx,nx->n", n_hat, e_big) < 0] *= -1.0
    null = amp <= 0.0
    if null.any():
        n_hat[null] = _frame(m[null])[1] if plane else (1.0, 0.0, 0.0)
    return amp, n_hat


def _max_k1(E1: np.ndarray, E2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """K=1 maximum and unit direction (a zero row where it is 0): every K = 1 ``TI_max``.

    The TI vector of Grossman 2017, in the sign-agnostic form of Hirata 2024 Eq. 2.
    """
    # 2 Es where min(|E1|, |E2|) <= sqrt(|E1.E2|), else twice Es's part perpendicular to h:
    # Es is the smaller field flipped into the acute angle (ties go to E2), h the shorter
    # of E1 -/+ E2.
    norm1 = np.linalg.norm(E1, axis=1)
    norm2 = np.linalg.norm(E2, axis=1)
    dot = np.sum(E1 * E2, axis=1)

    regime1 = np.minimum(norm1, norm2) <= np.sqrt(np.abs(dot))
    sign = np.where(dot < 0, -1.0, 1.0)
    Es = sign[:, None] * np.where((norm1 < norm2)[:, None], E1, E2)

    vec = np.zeros_like(E1)
    vec[regime1] = 2.0 * Es[regime1]
    r2 = ~regime1
    if np.any(r2):
        # |E1-E2|^2 - |E1+E2|^2 == -4 dot, so sign(dot) picks the shorter of
        # the two exactly; comparing the rounded norms would not.
        h = np.where((dot[r2] >= 0)[:, None], E1[r2] - E2[r2], E1[r2] + E2[r2])
        h_norm = np.linalg.norm(h, axis=1)
        # h = 0 here only when rounding put E1 = +-E2 in this regime, where 2 Es is exact.
        e_h = h / np.where(h_norm == 0, 1.0, h_norm)[:, None]
        Es2 = Es[r2]
        vec[r2] = 2.0 * (Es2 - np.sum(Es2 * e_h, axis=1)[:, None] * e_h)
    amp = np.linalg.norm(vec, axis=1)
    return amp, vec / np.where(amp > 0, amp, 1.0)[:, None]


def _frame(m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Orthonormal ``(m, e1, e2)`` for unit rows ``m``: the in-plane basis of the plane maximum.

    Zero rows (an undefined plane) get x/y, the defined in-plane direction where ``amp == 0``.
    """
    ref = np.where(np.abs(m[:, :1]) > 0.9, [[0.0, 1.0, 0.0]], [[1.0, 0.0, 0.0]])
    e1 = np.cross(m, ref)
    norm = np.linalg.norm(e1, axis=1, keepdims=True)
    zero = norm[:, 0] == 0
    e1 = e1 / np.where(norm > 0, norm, 1.0)
    e2 = np.cross(m, e1)
    e1[zero] = [1.0, 0.0, 0.0]
    e2[zero] = [0.0, 1.0, 0.0]
    return m, e1, e2


def _forms(E):
    """``C+ = S^T S / 2``, ``C- = D^T D / 2``, ``Cw = C+ - C-`` per element, for the K>=2 mean.

    ``n^T C n`` at all 2048 quadrature directions then costs 6 multiplies per form.
    """
    # Cw = sum_k (E_ka E_kb^T + E_kb E_ka^T), built directly, not as a lossy difference.
    S = E[0::2] + E[1::2]
    D = E[0::2] - E[1::2]
    Cp = 0.5 * np.einsum("knx,kny->nxy", S, S)
    Cm = 0.5 * np.einsum("knx,kny->nxy", D, D)
    Cw = np.einsum("knx,kny->nxy", E[0::2], E[1::2])
    Cw = Cw + Cw.transpose(0, 2, 1)
    return Cp, Cm, Cw


def _env_uvw(u, v, w):
    """``E_AM = sqrt(2) |w| / (sqrt(u) + sqrt(v))``, ``w = u - v``; a null field gives 0.

    ``sqrt(2u) - sqrt(2v)`` would lose a small envelope to round-off next to strong carriers.
    """
    den = np.sqrt(np.maximum(u, 0.0)) + np.sqrt(np.maximum(v, 0.0))
    return _ratio(_SQRT2 * np.abs(w), den)


def _uvw(S, D, dirs):
    """``u = |S n|^2/2``, ``v = |D n|^2/2``, ``w = u - v`` at ``dirs`` (n, c, 3): ranks candidates.

    From the projections: ``n^T C n`` loses ``v`` near a cusp (``sqrt(eps)`` in the envelope).
    """
    s = np.einsum("knx,ncx->knc", S, dirs)
    d = np.einsum("knx,ncx->knc", D, dirs)
    return (
        0.5 * np.sum(s * s, axis=0),
        0.5 * np.sum(d * d, axis=0),
        0.5 * np.sum((s + d) * (s - d), axis=0),
    )


def _pair_optima(E):
    """``(n, K, 3)``: each beating pair's own K=1 optimum, a kernel safeguard candidate.

    Exact when the other pairs vanish, where the root-find may have no sign change to bracket.
    """
    return np.stack([_max_k1(E[k], E[k + 1])[1] for k in range(0, len(E), 2)], axis=1)


def _max_sphere(E):
    """K>=2 sphere maximum and direction, from :mod:`tit._calc_kernel`; raises on a failed solve.

    A row whose eigen-solve did not converge has no trustworthy value, so it is an error.
    """
    # The maximiser is an eigenvector of cos(t) C+ - sin(t) C- at a t where
    # g = cos^2(t) u - sin^2(t) v = 0 (u = n^T C+ n, v = n^T C- n).
    E = np.ascontiguousarray(E)
    amp, n_hat, ok = _sphere_kernel(
        E, _THETA_GRID, _pair_optima(E), _ROOT_ITERS, _NEWTON_ITERS
    )
    if not ok.all():
        raise RuntimeError(
            f"envelope_max: the K>=2 eigen-solve did not converge at {int((~ok).sum())} "
            f"elements; fields above ~1e150 V/m overflow float64 once squared"
        )
    return amp, n_hat


def _max_plane(E, m):
    """K>=2 maximum over the plane perpendicular to unit rows ``m``, exact by polynomial roots."""
    # With n = cos(phi) e1 + sin(phi) e2 and psi = 2 phi, u and v are first-order trig
    # polynomials in psi; the stationary points are the roots of u'^2 v - v'^2 u (degree 3 in
    # psi) plus the cusps u = 0, v = 0.
    _, e1, e2 = _frame(m)
    S = E[0::2] + E[1::2]
    D = E[0::2] - E[1::2]

    def trig(X):
        """``u(psi) = c0 + c1 cos(psi) + c2 sin(psi)``, ``psi = 2 phi``: makes F a polynomial."""
        x1 = np.einsum("knx,nx->kn", X, e1)
        x2 = np.einsum("knx,nx->kn", X, e2)
        c11 = 0.5 * np.sum(x1 * x1, 0)
        c22 = 0.5 * np.sum(x2 * x2, 0)
        c12 = 0.5 * np.sum(x1 * x2, 0)
        return np.stack([(c11 + c22) / 2, (c11 - c22) / 2, c12], axis=-1)

    A, B = trig(S), trig(D)

    def val(C, psi):
        """The trig form ``C`` at ``psi``."""
        return C[:, :1] + C[:, 1:2] * np.cos(psi) + C[:, 2:3] * np.sin(psi)

    def der(C, psi):
        """Its ``psi`` derivative, for the stationarity condition ``F = 0``."""
        return -C[:, 1:2] * np.sin(psi) + C[:, 2:3] * np.cos(psi)

    # F = u'^2 v - v'^2 u is a degree-3 trig polynomial: 7 samples fix it.
    ps = 2 * np.pi * np.arange(7)[None, :] / 7
    F = der(A, ps) ** 2 * val(B, ps) - der(B, ps) ** 2 * val(A, ps)
    c = np.fft.fft(F, axis=1) / 7
    # z^3 F(z) = sum_{m=-3}^{3} c_m z^(m+3), highest degree first
    P = np.stack([c[:, mm % 7] for mm in range(3, -4, -1)], axis=1)
    scale = np.abs(P).max(axis=1)
    scale = np.where(scale > 0, scale, 1.0)
    lead = P[:, 0]
    tiny = np.abs(lead) < 1e-14 * scale
    P[tiny, 0] = 1e-14 * scale[tiny]  # degree drop: push the lost roots to infinity
    comp = np.zeros((len(P), 6, 6), dtype=complex)
    comp[:, 0, :] = -P[:, 1:] / P[:, :1]
    comp[:, np.arange(1, 6), np.arange(5)] = 1.0
    cand = [np.angle(np.linalg.eigvals(comp))]
    for C in (A, B):
        # u, v >= 0 (sums of squares) only touch zero, at their minimum psi = delta + pi:
        # the cusps of sqrt.  They are double roots of F, which the companion matrix
        # resolves only to ~sqrt(eps); the minimum is exact.
        cand.append((np.arctan2(C[:, 2], C[:, 1]) + np.pi)[:, None])
    phi = np.concatenate(cand, axis=1)[..., None] / 2
    dirs = np.cos(phi) * e1[:, None] + np.sin(phi) * e2[:, None]
    # Pick the winner from the projections: sqrt(u) of the trig form keeps only
    # ~sqrt(eps) next to a cusp, enough to rank a near-cusp root above the cusp.
    f = _env_uvw(*_uvw(S, D, dirs))
    j = f.argmax(axis=1)
    rows = np.arange(len(j))
    return f[rows, j], dirs[rows, j]


# ---------------------------------------------------------------------------
# envelope_mean
# ---------------------------------------------------------------------------


def envelope_mean(fields: Sequence[ArrayLike]) -> NDArray[np.float64]:
    """Mean of the envelope over all directions (``TI_avg``).

    The mean of ``E_AM(n)`` over the unit sphere; at K = 1 exactly
    ``|E1| + |E2| - (|E1 + E2| + |E1 - E2|) / 2``.  Never exceeds
    :func:`envelope_max`.

    Method: K = 1 closed form, exact.  K >= 2: equal-area quadrature on 2048
    hemisphere directions (``E_AM(n) = E_AM(-n)``, so a 4096-point sphere
    rule), ~7e-4 relative error at worst.  Literature: none, ``TI_avg`` is
    defined by this toolbox.

    Args:
        fields: ``[E1, E2, ..., E2K]``, one (N, 3) array per channel, in V/m.

    Returns:
        (N,) direction-averaged envelope amplitude in V/m.

    Raises:
        ValueError: as :func:`envelope`.
    """
    E = _stack(fields, paired=True)
    if E.shape[0] == 2:

        def norm(x):
            """Row norms."""
            return np.linalg.norm(x, axis=1)

        E1, E2 = E
        return norm(E1) + norm(E2) - 0.5 * (norm(E1 + E2) + norm(E1 - E2))

    dirs = _hemisphere_directions(2048)  # the ~7e-4 rule of the docstring
    x, y, z = dirs.T
    monomials = np.stack([x * x, y * y, z * z, 2 * x * y, 2 * x * z, 2 * y * z])

    def pack(C):
        """The 6 unique entries of each symmetric ``C``, in the order of ``monomials``."""
        return np.stack(
            [C[:, 0, 0], C[:, 1, 1], C[:, 2, 2], C[:, 0, 1], C[:, 0, 2], C[:, 1, 2]], 1
        )

    n_el = E.shape[1]
    out = np.empty(n_el)
    for lo in range(0, n_el, _MEAN_CHUNK):
        sl = slice(lo, min(lo + _MEAN_CHUNK, n_el))
        u, v, w = (pack(C) @ monomials for C in _forms(E[:, sl]))
        out[sl] = _env_uvw(u, v, w).mean(axis=1)
    return out


# ---------------------------------------------------------------------------
# Carrier metrics
# ---------------------------------------------------------------------------


def hf_peak(
    fields: Sequence[ArrayLike], *, coherent: bool = False
) -> NDArray[np.float64]:
    """Peak instantaneous carrier field, ``max_s |sum_c s_c E_c|`` over ``s_c = +-1``.

    Equal to ``max_n sum_c |E_c . n|``; two channels give ``max(|E1 + E2|,
    |E1 - E2|)``.  The default is the worst case over channel phases (reached
    by incommensurate frequencies), the safety-relevant value.  ``coherent=True``
    gives ``|sum_c E_c|``, the phase-aligned sum some scripts call "peak HF".

    Method: exact for any number of channels; closed form up to two, every
    sign pattern from three to eight (``2^(F-1)`` of them), zonotope vertices
    from nine (cost ~F^3 per element for F fields, 3.5 ms at 52).
    Literature: Cassarà et al. 2025 Part I Eq. 3.

    Args:
        fields: one or more channel fields (N, 3) in V/m, one per channel.
        coherent: carrier-only control (all channels at one frequency, in phase,
            ΔF = 0): the fields add as vectors (Cassarà 2025 Part II p. 8).

    Returns:
        (N,) peak carrier field magnitude in V/m (zero-to-peak).

    Raises:
        ValueError: no fields, shapes not all one (N, 3), or NaN or inf.
    """
    E = _stack(fields, paired=False)
    if coherent or len(E) == 1:
        return np.linalg.norm(E.sum(axis=0), axis=-1)
    if len(E) == 2:
        return np.maximum(
            np.linalg.norm(E[0] + E[1], axis=-1), np.linalg.norm(E[0] - E[1], axis=-1)
        )
    exact = _hf_peak_signs if len(E) <= _SIGN_ENUMERATION_MAX else _hf_peak_vertices
    n_el = E.shape[1]
    out = np.empty(n_el)
    for lo in range(0, n_el, _CHUNK):
        sl = slice(lo, min(lo + _CHUNK, n_el))
        out[sl] = exact(E[:, sl])
    return out


# Up to 8 fields, trying all 2^(F-1) sign patterns is 4-20x faster than the zonotope
# vertices (16384 elements: 1.0 vs 20 ms at 4 fields, 24 vs 160 ms at 8) and its
# (patterns, chunk, 3) work array stays under ~50 MB.
_SIGN_ENUMERATION_MAX = 8


def _hf_peak_signs(E):
    """Exact ``max_s |sum s_c E_c|`` for ``(F <= 8, n, 3)``: the definition, every sign pattern.

    ``s_1 = +1`` throughout: ``-s`` gives the same norm, so half the patterns suffice.
    """
    patterns = np.array(
        [(1.0, *s) for s in itertools.product((1.0, -1.0), repeat=len(E) - 1)]
    )
    total = np.einsum("pf,fnx->pnx", patterns, E)
    return np.sqrt(np.einsum("pnx,pnx->pn", total, total).max(axis=0))


def _hf_peak_vertices(E):
    """Exact ``max_s |sum s_c E_c|`` for ``(F >= 3, n, 3)`` from zonotope vertices, no grid."""
    # The maximum is a zonotope vertex: a cell of the plane arrangement E_c . n = 0 next to
    # one of its vertices n = E_i x E_j. The 4 sign patterns around each such vertex (plus n
    # along the largest field, for collinear sets) contain it; fields in the plane of E_i, E_j
    # take their sign from an in-plane direction in the chosen quadrant, so coplanar and
    # parallel fields stay exact.
    F, n_el, _ = E.shape
    rows = np.arange(n_el)
    norms = np.linalg.norm(E, axis=2)

    def total(signs):
        """``|sum_c s_c E_c|`` for one sign pattern per element."""
        return np.linalg.norm(np.einsum("fm,fmx->mx", signs, E), axis=1)

    def sign(x):
        """``sign`` with 0 -> +1, so a field on a cell boundary still gets a carrier sign."""
        return np.where(x < 0, -1.0, 1.0)

    e_big = E[norms.argmax(axis=0), rows]
    best = total(sign(np.einsum("fmx,mx->fm", E, e_big)))
    for i, j in itertools.combinations(range(F), 2):
        n = np.cross(E[i], E[j])
        d = np.einsum("fmx,mx->fm", E, n)
        # in the plane of E_i, E_j: sign from m = si (E_j x n) + sj (n x E_i)
        coplanar = np.abs(d) <= 1e-12 * norms * np.linalg.norm(n, axis=1)
        t_i = np.einsum("fmx,mx->fm", E, np.cross(E[j], n))
        t_j = np.einsum("fmx,mx->fm", E, np.cross(n, E[i]))
        base = sign(d)
        for si in (1.0, -1.0):
            for sj in (1.0, -1.0):
                s = np.where(coplanar, sign(si * t_i + sj * t_j), base)
                s[i] = si
                s[j] = sj
                np.maximum(best, total(s), out=best)
    return best


def hf_power(
    fields: Sequence[ArrayLike], *, coherent: bool = False
) -> NDArray[np.float64]:
    """Time-averaged mean-square carrier field, ``(1/2) sum_c |E_c|^2 = E_rms^2``.

    Channel fields at distinct frequencies add in power (their cross terms
    average out).  ``sigma * hf_power`` (isotropic ``sigma``) is the absorbed
    power density (W/m^3), and over the tissue density the SAR.  Unlike every other output this is a time
    average: compare ``sqrt(hf_power)`` with RMS limits (at 1-10 kHz ICNIRP 2010
    and IEEE C95.1 limit the RMS in-situ field, not SAR), or :func:`hf_peak`
    with ``sqrt(2)`` times them.

    Method: closed form, exact for any number of channels.  Literature:
    Cassarà et al. 2025 Part I p. 11 and Part II Eq. 1; IEEE C95.1-2019 p. 35.

    Args:
        fields: one or more zero-to-peak channel fields (N, 3) in V/m.
        coherent: carrier-only control (all channels at one frequency, in phase,
            ΔF = 0): one sinusoid of amplitude ``sum_c E_c``, so
            ``(1/2) |sum_c E_c|^2``.

    Returns:
        (N,) mean-square carrier field in (V/m)^2.

    Raises:
        ValueError: as :func:`hf_peak`.
    """
    E = _stack(fields, paired=False)
    if coherent:
        E = E.sum(axis=0, keepdims=True)
    return 0.5 * np.einsum("fnx,fnx->n", E, E)
