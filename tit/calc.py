"""Temporal-interference envelope and carrier-field metrics.

Five functions, NumPy only, vectorised and chunked over elements:

==================  ==========================================================
:func:`envelope`      envelope modulation amplitude along a given direction
                      (``TI_normal`` along the cortical normal)
:func:`envelope_max`  its maximum over all directions (``TI_max``/``mTI_max``),
                      or over the directions in a plane (tangential maximum)
:func:`envelope_mean` its mean over all directions (``TI_avg``)
:func:`hf_peak`       peak instantaneous carrier field (``hf_peak``)
:func:`hf_power`      time-averaged mean-square carrier field, E_rms^2
==================  ==========================================================

Field layout
------------
The envelope functions take ``fields = [E1a, E1b, E2a, E2b, ...]``: ``2K``
arrays of shape ``(N, 3)`` in V/m, paired positionally.  Each pair ``k`` is
one carrier pair beating at the common difference frequency, and all ``K``
envelopes are phase-aligned.  ``K = 1`` is standard TI; ``K >= 2`` is
multi-channel TI (mTI).  The carrier metrics take any number ``>= 1`` of
carrier fields (one field per electrode pair).

The envelope along a unit direction ``n``
-----------------------------------------
With ``a_k = E_ka . n`` and ``b_k = E_kb . n``, and ``S``/``D`` the ``K x 3``
matrices with rows ``E_ka + E_kb`` / ``E_ka - E_kb``::

    E_AM(n) = | |S n| - |D n| |  =  4 |sum_k a_k b_k| / (|S n| + |D n|)

The right-hand form has no subtraction of near-equal terms and is the one
evaluated everywhere here.  At ``K = 1`` it is exactly Grossman et al. 2017
(Cell 169(6):1029-1041, STAR Methods): ``||(E1+E2).n| - |(E1-E2).n|| =
2 min(|E1.n|, |E2.n|)``.  ``E_AM(n) = E_AM(-n)``.

Citations by function: :func:`envelope` is Grossman's "envelope modulation
amplitude along the direction n" (SimNIBS ``TI_utils.get_dirTI``);
:func:`envelope_max` is Grossman's "maximal modulation amplitude along any
orientation" (SimNIBS ``get_maxTI``), with the K=1 closed form in the
sign-agnostic shape of Hirata et al. 2024 (Comput Biol Med 178:108697, Eq. 2);
:func:`envelope_mean` (``TI_avg``) is defined by this toolbox, there is no
literature definition; :func:`hf_peak` is Cassarà et al. 2025 Part I
(Bioelectromagnetics 46(2):e22542) Eq. 3; :func:`hf_power` is Cassarà 2025
Part I p. 11 and Part II (Bioelectromagnetics 46(1):e22536) Eq. 1 with IEEE
C95.1-2019 p. 35.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from tit.constants import is_valid_pair_count

__all__ = ["envelope", "envelope_max", "envelope_mean", "hf_peak", "hf_power"]

# Elements per chunk: bounds peak memory independently of the mesh size.
_CHUNK = 16384
# The K>=2 mean holds (chunk, 2048) arrays, so it uses a smaller chunk.
_MEAN_CHUNK = 1024

_SQRT2 = np.sqrt(2.0)
_X_AXIS = np.array([1.0, 0.0, 0.0])

# --- K>=2 sphere maximum: eigen-branch root-find --------------------------
# theta grid: 16 uniform intervals on (0, pi/2) plus 16 log-spaced in tan(theta)
# (tan theta = sqrt(u/v) spans many decades when one carrier pair is weak).
_THETA_EPS = 1e-7
_THETA_GRID = np.unique(
    np.concatenate(
        [
            np.linspace(_THETA_EPS, np.pi / 2 - _THETA_EPS, 17),
            np.arctan(np.exp(np.linspace(-14.0, 14.0, 17))),
        ]
    )
)
_ROOT_ITERS = 14
_PERMS = np.array(list(itertools.permutations(range(3))))
# Local polish: Newton iterations from each seed.
_NEWTON_ITERS = 12

# --- K>=2 sphere mean: 2048 equal-area directions on the upper hemisphere ---
_MEAN_DIRECTIONS = 2048


def _hemisphere_directions(n: int) -> np.ndarray:
    """``n`` equal-area (Fibonacci) unit directions with ``z > 0``."""
    i = np.arange(n) + 0.5
    z = 1.0 - i / n
    r = np.sqrt(1.0 - z * z)
    t = np.pi * (3.0 - np.sqrt(5.0)) * i
    return np.stack([r * np.cos(t), r * np.sin(t), z], axis=-1)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _stack(fields: Sequence[ArrayLike], *, paired: bool) -> np.ndarray:
    """Validate a field list and stack it as ``(F, N, 3)`` float64."""
    arrs = [np.asarray(f, dtype=np.float64) for f in fields]
    n = len(arrs)
    if paired and not is_valid_pair_count(n):
        raise ValueError(
            f"fields must be an even number (>= 2) of arrays, two per carrier "
            f"pair: [E1a, E1b, E2a, E2b, ...]; got {n}"
        )
    if not paired and n < 1:
        raise ValueError("fields must contain at least one carrier field")
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
    """``(3,)`` or ``(N, 3)`` -> ``(N, 3)`` unit rows; zero rows stay zero."""
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
    """``num / den`` with 0 where ``den`` is 0 (a null field)."""
    return np.divide(num, den, out=np.zeros(np.shape(den)), where=den > 0)


# ---------------------------------------------------------------------------
# envelope
# ---------------------------------------------------------------------------


def envelope(fields: Sequence[ArrayLike], direction: ArrayLike) -> NDArray[np.float64]:
    """Envelope modulation amplitude along a direction, any K.

    ``E_AM(n) = 4 |sum_k a_k b_k| / (|S n| + |D n|)`` with ``a_k = E_ka.n``,
    ``b_k = E_kb.n`` (module docstring) -- Grossman et al. 2017 STAR Methods
    "envelope modulation amplitude along the direction n", the quantity SimNIBS
    ``TI_utils.get_dirTI`` computes for K=1.  Exact (a closed expression, no
    search) for every K.  Along the cortical normal it is ``TI_normal``.

    Parameters
    ----------
    fields : sequence of array-like, each (N, 3)
        ``[E1a, E1b, E2a, E2b, ...]``, 2K fields in V/m, paired positionally.
    direction : array-like, (3,) or (N, 3)
        One direction for every element, or one per element.  Normalised
        internally; a zero vector gives 0.

    Returns
    -------
    numpy.ndarray, (N,)
        Peak-to-trough envelope amplitude in V/m.

    Raises
    ------
    ValueError
        Odd or fewer than two fields, fields not all ``(N, 3)`` of one shape,
        a NaN or inf in ``fields``/``direction``, or ``direction`` not
        ``(3,)``/``(N, 3)``.

    Examples
    --------
    >>> import numpy as np
    >>> E1, E2 = np.array([[1.0, 0, 0]]), np.array([[0.5, 0, 0]])
    >>> envelope([E1, E2], [1.0, 0, 0])
    array([1.])
    >>> envelope([E1, E2], [0, 1.0, 0])
    array([0.])
    """
    E = _stack(fields, paired=True)
    n = _unit_rows(direction, E.shape[1], "direction")
    p = np.einsum("fnx,nx->fn", E, n)
    a, b = p[0::2], p[1::2]
    s = np.sqrt(np.sum((a + b) ** 2, axis=0))
    d = np.sqrt(np.sum((a - b) ** 2, axis=0))
    return _ratio(4.0 * np.abs(np.sum(a * b, axis=0)), s + d)


# ---------------------------------------------------------------------------
# envelope_max
# ---------------------------------------------------------------------------


def envelope_max(
    fields: Sequence[ArrayLike],
    *,
    perpendicular_to: ArrayLike | None = None,
    return_direction: bool = False,
) -> NDArray[np.float64] | tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Maximum of the envelope over all directions, or over a plane.

    ``max_n E_AM(n)`` over unit ``n`` -- Grossman et al. 2017's "maximal
    modulation amplitude along any orientation", SimNIBS ``get_maxTI``, the
    ``TI_max``/``mTI_max`` output.  With ``perpendicular_to`` the maximum runs
    over the unit ``n`` perpendicular to it (the tangential maximum, e.g. in the
    cortical surface plane); this equals the sphere maximum of the fields
    projected onto that plane.

    Method and accuracy
    -------------------
    * **K = 1, sphere**: the exact closed form of Grossman 2017 in the
      sign-agnostic shape of Hirata et al. 2024 Eq. 2.  Matches SimNIBS
      ``get_maxTI`` to ~1e-15 relative and is 0 (not NaN) on null fields.
    * **K = 1, plane**: the same closed form on the fields projected onto the
      plane.  Exact.
    * **K >= 2, sphere**: the optimum is an eigenvector of
      ``cos(t) C+ - sin(t) C-`` (``C+ = S^T S / 2``, ``C- = D^T D / 2``) at a
      ``t`` where ``g = cos^2(t) u - sin^2(t) v = 0`` (``u = n^T C+ n``,
      ``v = n^T C- n``).  All three eigen-branches are tracked by overlap on a
      grid of 16 uniform plus 16 log-spaced ``t``; each sign change of ``g`` is
      solved by Illinois regula falsi; the best stationary point, and safeguard
      candidates (the eigenvectors of ``C+``, ``C-`` and ``C+ - C-``, and each
      pair's own K=1 optimum), then get a Newton polish.  Measured offline
      (2026-10-26): of 10^4 random elements each for K = 2, 3, 4 and three
      degenerate sets, and of 2 x 2x10^5 sub-101 grey-matter elements, none
      falls more than 1e-6 below a dense 2x10^5-direction search (or the
      previous sweep).  ``tests/test_calc.py`` re-checks 1000 random elements
      per K, the degenerate sets and six real elements an earlier variant
      missed, against a dense search.
    * **K >= 2, plane**: exact.  Stationary points in ``psi = 2 phi`` are roots
      of the degree-3 trigonometric polynomial ``u'^2 v - v'^2 u`` (a degree-6
      polynomial in ``e^{i psi}``, from a 7-point DFT, solved by companion
      eigenvalues), plus the cusps ``u = 0``, ``v = 0`` (the minima of ``u``
      and ``v``, which only touch zero).

    Parameters
    ----------
    fields : sequence of array-like, each (N, 3)
        ``[E1a, E1b, E2a, E2b, ...]``, 2K fields in V/m, paired positionally.
    perpendicular_to : array-like, (3,) or (N, 3), optional
        Plane normal(s).  ``None`` (default) maximises over the whole sphere.
        Normalised internally; a zero row gives 0.
    return_direction : bool
        Also return the maximising unit direction.

    Returns
    -------
    amp : numpy.ndarray, (N,)
        Maximum envelope amplitude in V/m.
    n_hat : numpy.ndarray, (N, 3)
        Only with ``return_direction=True``: a unit maximiser (``-n_hat`` is
        equally one).  K=1 keeps the Grossman/Hirata TI-vector orientation --
        ``amp * n_hat`` is the classic TI vector, the sign-corrected smaller
        field (or its part perpendicular to ``E1 -/+ E2``).  That orientation
        satisfies ``n_hat . E_L >= 0`` for ``E_L`` the field of largest
        magnitude, which is the rule applied for K >= 2 (projected fields for
        a plane).  Where ``amp == 0`` every direction is a maximiser and
        ``n_hat`` is ``(1, 0, 0)`` (an in-plane unit vector for a plane).

    Raises
    ------
    ValueError
        As :func:`envelope`, or ``perpendicular_to`` not ``(3,)``/``(N, 3)``.

    Examples
    --------
    >>> import numpy as np
    >>> E1, E2 = np.array([[1.0, 0, 0]]), np.array([[0.5, 0, 0]])
    >>> envelope_max([E1, E2])
    array([1.])
    >>> envelope_max([E1, E2], perpendicular_to=[1.0, 0, 0])
    array([0.])
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
        n_hat[null] = _frame(m[null])[1] if plane else _X_AXIS
    return amp, n_hat


def _ti_vector_k1(E1: np.ndarray, E2: np.ndarray) -> np.ndarray:
    """K=1 TI vectors (Grossman 2017; sign-agnostic form of Hirata 2024 Eq. 2).

    ``2 * Es`` when ``min(|E1|, |E2|) <= sqrt(|E1.E2|)``, else twice the part
    of ``Es`` perpendicular to ``h``; ``Es`` is the smaller field flipped into
    the acute angle with the larger (ties go to ``E2``), ``h`` is whichever of
    ``E1 - E2``/``E1 + E2`` is shorter.  No magnitude-ordering swap or sign
    flip of the inputs is needed.
    """
    norm1 = np.linalg.norm(E1, axis=1)
    norm2 = np.linalg.norm(E2, axis=1)
    dot = np.sum(E1 * E2, axis=1)

    regime1 = np.minimum(norm1, norm2) <= np.sqrt(np.abs(dot))
    sign = np.where(dot < 0, -1.0, 1.0)
    Es = sign[:, None] * np.where((norm1 < norm2)[:, None], E1, E2)

    out = np.zeros_like(E1)
    out[regime1] = 2.0 * Es[regime1]
    r2 = ~regime1
    if np.any(r2):
        # |E1-E2|^2 - |E1+E2|^2 == -4 dot, so sign(dot) picks the shorter of
        # the two exactly; comparing the rounded norms would not.
        h = np.where((dot[r2] >= 0)[:, None], E1[r2] - E2[r2], E1[r2] + E2[r2])
        h_norm = np.linalg.norm(h, axis=1)
        e_h = h / np.where(h_norm == 0, 1.0, h_norm)[:, None]
        Es2 = Es[r2]
        out[r2] = 2.0 * (Es2 - np.sum(Es2 * e_h, axis=1)[:, None] * e_h)
    return out


def _max_k1(E1, E2):
    vec = _ti_vector_k1(E1, E2)
    amp = np.linalg.norm(vec, axis=1)
    return amp, vec / np.where(amp > 0, amp, 1.0)[:, None]


def _frame(m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Orthonormal ``(m, e1, e2)`` for unit rows ``m``; zero rows get x/y."""
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
    """``C+ = S^T S / 2``, ``C- = D^T D / 2`` and ``Cw = C+ - C-`` per element.

    ``Cw = sum_k (E_ka E_kb^T + E_kb E_ka^T)`` is built directly rather than as
    a difference.
    """
    S = E[0::2] + E[1::2]
    D = E[0::2] - E[1::2]
    Cp = 0.5 * np.einsum("knx,kny->nxy", S, S)
    Cm = 0.5 * np.einsum("knx,kny->nxy", D, D)
    Cw = np.einsum("knx,kny->nxy", E[0::2], E[1::2])
    Cw = Cw + Cw.transpose(0, 2, 1)
    return Cp, Cm, Cw


def _env_uvw(u, v, w):
    """``E_AM = sqrt(2) |w| / (sqrt(u) + sqrt(v))``, ``w = u - v``."""
    den = np.sqrt(np.maximum(u, 0.0)) + np.sqrt(np.maximum(v, 0.0))
    return _ratio(_SQRT2 * np.abs(w), den)


def _uvw(S, D, dirs):
    """``u = |S n|^2/2``, ``v = |D n|^2/2``, ``w = u - v`` at ``dirs`` (n, c, 3).

    From the projections, not from ``n^T C n``: next to a cusp (``v -> 0``) the
    quadratic form loses ``v`` to round-off (``sqrt(eps)`` relative in the
    envelope), while ``sum (D_k . n)^2`` keeps it.
    """
    s = np.einsum("knx,ncx->knc", S, dirs)
    d = np.einsum("knx,ncx->knc", D, dirs)
    return (
        0.5 * np.sum(s * s, axis=0),
        0.5 * np.sum(d * d, axis=0),
        0.5 * np.sum((s + d) * (s - d), axis=0),
    )


def _match_columns(Vprev, V):
    """Reorder (and sign-fix) the eigenvector columns of ``V`` to follow ``Vprev``."""
    overlap = np.abs(np.einsum("nji,njk->nik", Vprev, V))
    score = overlap[:, np.arange(3)[None, :], _PERMS].sum(-1)
    perm = _PERMS[score.argmax(axis=1)]
    Vm = np.take_along_axis(V, perm[:, None, :], axis=2)
    sgn = np.sign(np.einsum("nji,nji->ni", Vprev, Vm))
    sgn[sgn == 0] = 1.0
    return Vm * sgn[:, None, :]


def _keep_best(best, best_n, vals, dirs):
    """Fold candidates ``vals`` (n, c) / ``dirs`` (n, c, 3) into the running best."""
    j = vals.argmax(axis=1)
    rows = np.arange(len(best))
    cand = vals[rows, j]
    better = cand > best
    best[better] = cand[better]
    best_n[better] = dirs[rows, j][better]


def _max_sphere(E):
    """K>=2 sphere maximum: eigen-branch root-find, safeguards, local polish."""
    S = E[0::2] + E[1::2]
    D = E[0::2] - E[1::2]
    Cp, Cm, Cw = _forms(E)
    n_el = Cp.shape[0]
    best = np.full(n_el, -1.0)
    best_n = np.zeros((n_el, 3))

    # Track the three eigen-branches of cos(t) C+ - sin(t) C- over the grid.
    grid = _THETA_GRID
    Vs = np.empty((n_el, len(grid), 3, 3))
    g = np.empty((n_el, len(grid), 3))
    branch_f = np.full((n_el, 3), -1.0)  # best grid point of each branch
    branch_n = np.zeros((n_el, 3, 3))
    V = None
    for j, t in enumerate(grid):
        Vj = np.linalg.eigh(np.cos(t) * Cp - np.sin(t) * Cm)[1]
        V = Vj if V is None else _match_columns(V, Vj)
        cols = V.transpose(0, 2, 1)
        u, v, w = _uvw(S, D, cols)
        Vs[:, j] = V
        g[:, j] = np.cos(t) ** 2 * u - np.sin(t) ** 2 * v
        f = _env_uvw(u, v, w)
        up = f > branch_f
        branch_f[up] = f[up]
        branch_n[up] = cols[up]
        _keep_best(best, best_n, f, cols)

    # Illinois regula falsi on every bracketed sign change of g along a branch.
    el, jc, br = np.nonzero(np.signbit(g[:, :-1]) != np.signbit(g[:, 1:]))
    if len(el):
        a, b = grid[jc], grid[jc + 1]
        ga, gb = g[el, jc, br], g[el, jc + 1, br]
        ref = Vs[el, jc, :, br]
        Cpe, Cme, Se, De = Cp[el], Cm[el], S[:, el], D[:, el]
        idx = np.arange(len(el))
        side = np.zeros(len(el))
        for _ in range(_ROOT_ITERS):
            x = (a * gb - b * ga) / (gb - ga)
            Vx = np.linalg.eigh(
                np.cos(x)[:, None, None] * Cpe - np.sin(x)[:, None, None] * Cme
            )[1]
            nx = Vx[idx, :, np.abs(np.einsum("mj,mjk->mk", ref, Vx)).argmax(axis=1)]
            u, v, w = (q[:, 0] for q in _uvw(Se, De, nx[:, None, :]))
            gx = np.cos(x) ** 2 * u - np.sin(x) ** 2 * v
            left = np.signbit(gx) == np.signbit(ga)
            ga, gb = (
                np.where(left, gx, np.where(side == -1, ga / 2, ga)),
                np.where(left, np.where(side == 1, gb / 2, gb), gx),
            )
            a, b = np.where(left, x, a), np.where(left, b, x)
            side = np.where(left, 1.0, -1.0)
            # several brackets per element: keep each element's best iterate
            fx = _env_uvw(u, v, w)
            top = np.full(n_el, -1.0)
            np.maximum.at(top, el, fx)
            win = (fx >= top[el]) & (fx > best[el])
            best_n[el[win]] = nx[win]
            np.maximum(best, top, out=best)

    # Safeguards: the eigenvectors of C+, C- and C+ - C-, and each pair's own
    # K=1 optimum (exact when the other pairs vanish).
    safe = [np.linalg.eigh(C)[1].transpose(0, 2, 1) for C in (Cp, Cm, Cw)]
    for k in range(E.shape[0] // 2):
        safe.append(_max_k1(E[2 * k], E[2 * k + 1])[1][:, None, :])
    safe = np.concatenate(safe, axis=1)
    _keep_best(best, best_n, _env_uvw(*_uvw(S, D, safe)), safe)

    # Local polish: Newton ascent from the best point and from each branch's
    # best grid point -- the root-find can miss a pair of close roots inside
    # one grid interval, and a narrow ridge defeats a pattern search.
    seeds = np.concatenate([best_n[:, None], branch_n], axis=1)
    c = seeds.shape[1]
    f, n = _newton_ascent(
        np.repeat(S, c, axis=1), np.repeat(D, c, axis=1), seeds.reshape(-1, 3)
    )
    _keep_best(best, best_n, f.reshape(n_el, c), n.reshape(n_el, c, 3))

    best_n /= np.linalg.norm(best_n, axis=1, keepdims=True)
    return np.maximum(best, 0.0), best_n


def _newton_ascent(S, D, n):
    """Riemannian Newton ascent of ``E_AM`` on the sphere from unit rows ``n``.

    ``S``, ``D`` are ``(K, m, 3)``; returns ``(f, n)`` per row.  On the side
    ``u >= v``, ``E_AM = sqrt(2u) - sqrt(2v)`` (else its negative), smooth
    away from the cusps ``u = 0``, ``v = 0``.  A step is taken only if it
    raises ``E_AM`` (halved up to 6 times), so the result never gets worse;
    where the tangent Hessian is not negative definite the step is a 0.1 rad
    gradient step instead.  Cusp maxima are covered by the safeguard
    candidates, not by this.
    """
    Cp = 0.5 * np.einsum("kmx,kmy->mxy", S, S)
    Cm = 0.5 * np.einsum("kmx,kmy->mxy", D, D)

    def at(n):
        u, v, w = (q[:, 0] for q in _uvw(S, D, n[:, None]))
        return _env_uvw(u, v, w), u, v

    f, u, v = at(n)
    with np.errstate(all="ignore"):
        for _ in range(_NEWTON_ITERS):
            up = (u >= v)[:, None, None]
            A, B = np.where(up, Cp, Cm), np.where(up, Cm, Cp)
            ua, vb = np.where(up[:, 0, 0], u, v), np.where(up[:, 0, 0], v, u)
            ra, rb = np.sqrt(ua), np.sqrt(vb)
            An = np.einsum("mxy,my->mx", A, n)
            Bn = np.einsum("mxy,my->mx", B, n)
            grad = _SQRT2 * (An / ra[:, None] - Bn / rb[:, None])
            hess = _SQRT2 * (
                A / ra[:, None, None]
                - B / rb[:, None, None]
                - An[:, :, None] * An[:, None, :] / (ua * ra)[:, None, None]
                + Bn[:, :, None] * Bn[:, None, :] / (vb * rb)[:, None, None]
            )
            _, e1, e2 = _frame(n)
            T = np.stack([e1, e2], axis=1)
            gt = np.einsum("mix,mx->mi", T, grad)
            Ht = np.einsum("mix,mxy,mjy->mij", T, hess, T)
            Ht -= np.einsum("mx,mx->m", grad, n)[:, None, None] * np.eye(2)
            det = Ht[:, 0, 0] * Ht[:, 1, 1] - Ht[:, 0, 1] ** 2
            concave = (Ht[:, 0, 0] < 0) & (det > 0)
            newton = (
                -np.stack(
                    [
                        Ht[:, 1, 1] * gt[:, 0] - Ht[:, 0, 1] * gt[:, 1],
                        Ht[:, 0, 0] * gt[:, 1] - Ht[:, 0, 1] * gt[:, 0],
                    ],
                    axis=1,
                )
                / det[:, None]
            )
            gnorm = np.linalg.norm(gt, axis=1, keepdims=True)
            step = np.where(concave[:, None], newton, 0.1 * gt / gnorm)
            step = np.nan_to_num(step, nan=0.0, posinf=0.0, neginf=0.0)
            length = np.linalg.norm(step, axis=1, keepdims=True)
            step *= np.minimum(1.0, 0.3 / np.where(length > 0, length, 1.0))
            for _ in range(6):
                cand = n + np.einsum("mi,mix->mx", step, T)
                cand /= np.linalg.norm(cand, axis=1, keepdims=True)
                fc, uc, vc = at(cand)
                ok = fc > f
                n[ok], f[ok], u[ok], v[ok] = cand[ok], fc[ok], uc[ok], vc[ok]
                step[ok] = 0.0
                step *= 0.5
                if ok.all():
                    break
    return f, n


def _max_plane(E, m):
    """K>=2 maximum over the plane perpendicular to unit rows ``m`` (exact)."""
    _, e1, e2 = _frame(m)
    S = E[0::2] + E[1::2]
    D = E[0::2] - E[1::2]

    def trig(X):
        """``u(psi) = c0 + c1 cos(psi) + c2 sin(psi)`` with ``psi = 2 phi``."""
        x1 = np.einsum("knx,nx->kn", X, e1)
        x2 = np.einsum("knx,nx->kn", X, e2)
        c11 = 0.5 * np.sum(x1 * x1, 0)
        c22 = 0.5 * np.sum(x2 * x2, 0)
        c12 = 0.5 * np.sum(x1 * x2, 0)
        return np.stack([(c11 + c22) / 2, (c11 - c22) / 2, c12], axis=-1)

    A, B = trig(S), trig(D)

    def val(C, psi):
        return C[:, :1] + C[:, 1:2] * np.cos(psi) + C[:, 2:3] * np.sin(psi)

    def der(C, psi):
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
    """Mean of the envelope over all directions (``TI_avg``), any K.

    The average of ``E_AM(n)`` over the unit sphere: what an arbitrarily
    oriented element sees on average.  Defined by this toolbox (no literature
    definition); never exceeds :func:`envelope_max`.

    Method and accuracy
    -------------------
    * **K = 1**: exact closed form.  ``E_AM(n) = 2 min(|a|, |b|) = 2|a| + 2|b|
      - |a + b| - |a - b|`` and the sphere mean of ``|v . n|`` is ``|v| / 2``,
      so the mean is ``|E1| + |E2| - (|E1 + E2| + |E1 - E2|) / 2``.
    * **K >= 2**: equal-weight quadrature on 2048 equal-area directions of one
      hemisphere (``E_AM(n) = E_AM(-n)``, so this is the 4096-point full-sphere
      rule): about 7e-4 worst-case relative error on random fields.

    Parameters
    ----------
    fields : sequence of array-like, each (N, 3)
        ``[E1a, E1b, E2a, E2b, ...]``, 2K fields in V/m, paired positionally.

    Returns
    -------
    numpy.ndarray, (N,)
        Direction-averaged envelope amplitude in V/m.

    Raises
    ------
    ValueError
        As :func:`envelope`.

    Examples
    --------
    >>> import numpy as np
    >>> E1, E2 = np.array([[1.0, 0, 0]]), np.array([[0.5, 0, 0]])
    >>> envelope_mean([E1, E2])  # 2 * 0.5 * mean|cos| = 0.5
    array([0.5])
    """
    E = _stack(fields, paired=True)
    if E.shape[0] == 2:

        def norm(x):
            return np.linalg.norm(x, axis=1)

        E1, E2 = E
        return norm(E1) + norm(E2) - 0.5 * (norm(E1 + E2) + norm(E1 - E2))

    dirs = _hemisphere_directions(_MEAN_DIRECTIONS)
    x, y, z = dirs.T
    monomials = np.stack([x * x, y * y, z * z, 2 * x * y, 2 * x * z, 2 * y * z])

    def pack(C):
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
    """Peak instantaneous carrier field: ``max_s |sum_c s_c E_c|``.

    Each field is one carrier (one electrode pair).  Carriers at mutually
    incommensurate frequencies pass through every relative phase, so the worst
    case is the maximum over sign choices ``s_c = +-1`` -- equivalently the
    support of the zonotope ``max_n sum_c |E_c . n|``.  At two carriers it is
    ``max(|E1 + E2|, |E1 - E2|)``, Cassarà et al. 2025 Part I Eq. 3 (p. 11:
    the worst case is in-phase, spatially aligned fields).

    Method: exact for every carrier count.  One carrier is ``|E1|``; two is
    Eq. 3.  From three on, the maximum is a zonotope vertex, and every vertex
    is a cell of the arrangement of planes ``E_c . n = 0``, adjacent to one of
    its vertices ``n = E_i x E_j``: the ``4 C(N, 2)`` sign patterns around
    those vertices (plus ``n`` along the largest field, for all-collinear
    fields) contain the maximum.  Fields lying in the plane of ``E_i, E_j``
    (``E_c . n = 0``) take their sign from an in-plane direction inside the
    chosen quadrant, so coplanar and parallel fields stay exact.

    Cost grows as ``N^3`` (``C(N, 2)`` vertices x 4 patterns x ``N`` fields).
    Measured per element (NumPy, one core, 2026-10-26): N = 4: 1.5 us,
    8: 11 us, 12: 36 us, 16: 82 us, 26: 0.39 ms, 52: 3.5 ms -- a 1.4 M-element
    head at the 26-pair limit (52 fields) takes over an hour.

    Parameters
    ----------
    fields : sequence of array-like, each (N, 3)
        One or more carrier fields in V/m, all the same shape.
    coherent : bool
        Carrier-only control (every pair at one frequency, in phase, ΔF = 0):
        the fields add as vectors, ``|sum_c E_c|`` (Cassarà 2025 Part II p. 8).

    Returns
    -------
    numpy.ndarray, (N,)
        Peak carrier field magnitude in V/m.

    Raises
    ------
    ValueError
        No fields, fields not all ``(N, 3)`` of one shape, or a NaN or inf.

    Examples
    --------
    >>> import numpy as np
    >>> hf_peak([np.array([[1.0, 0, 0]]), np.array([[0, 1.0, 0]])])
    array([1.41421356])
    """
    E = _stack(fields, paired=False)
    if coherent or len(E) == 1:
        return np.linalg.norm(E.sum(axis=0), axis=-1)
    if len(E) == 2:
        return np.maximum(
            np.linalg.norm(E[0] + E[1], axis=-1), np.linalg.norm(E[0] - E[1], axis=-1)
        )
    n_el = E.shape[1]
    out = np.empty(n_el)
    for lo in range(0, n_el, _CHUNK):
        sl = slice(lo, min(lo + _CHUNK, n_el))
        out[sl] = _hf_peak_vertices(E[:, sl])
    return out


def _hf_peak_vertices(E):
    """Exact ``max_s |sum s_c E_c|`` for ``(F >= 3, n, 3)`` by arrangement vertices."""
    F, n_el, _ = E.shape
    rows = np.arange(n_el)
    norms = np.linalg.norm(E, axis=2)

    def total(signs):
        return np.linalg.norm(np.einsum("fm,fmx->mx", signs, E), axis=1)

    def sign(x):
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
    """Time-averaged mean-square carrier field ``(1/2) sum_c |E_c|^2`` = ``E_rms^2``.

    Each ``E_c`` is a zero-to-peak carrier amplitude at its own frequency, so
    over time the cross terms average out and the carriers' powers add:
    Cassarà et al. 2025 Part I p. 11 ("the SAR distributions from the two
    channels, rather than the E-fields themselves, must be summed") and Part II
    p. 8 (incoherent superposition for distinct frequencies).  ``sigma *
    hf_power`` is the absorbed power density (W/m^3) and ``sigma * hf_power /
    rho`` the SAR (IEEE C95.1-2019 p. 35, ``SAR = sigma |E_rms|^2 / rho``;
    Cassarà 2025 Part II Eq. 1).  At 1-10 kHz, however, ICNIRP 2010 and IEEE
    C95.1 limit the RMS in-situ field -- ``sqrt(hf_power)``, spatially averaged
    -- not SAR (SAR limits start at 100 kHz).

    Units convention: every other field here (``E_c``, ``TI_max``/
    :func:`envelope_max`, :func:`hf_peak`) is zero-to-peak for zero-to-peak
    channel currents; this one is a time average.  Compare ``sqrt(hf_power)``
    with RMS limits, or ``hf_peak`` with ``sqrt(2)`` times them.

    Parameters
    ----------
    fields : sequence of array-like, each (N, 3)
        One or more zero-to-peak carrier fields in V/m, all the same shape.
    coherent : bool
        Carrier-only control (every pair at one frequency, in phase, ΔF = 0):
        one sinusoid of amplitude ``sum_c E_c``, so ``(1/2) |sum_c E_c|^2``.

    Returns
    -------
    numpy.ndarray, (N,)
        Mean-square carrier field in (V/m)^2.

    Raises
    ------
    ValueError
        As :func:`hf_peak`.

    Examples
    --------
    >>> import numpy as np
    >>> hf_power([np.array([[1.0, 0, 0]]), np.array([[0, 2.0, 0]])])
    array([2.5])
    """
    E = _stack(fields, paired=False)
    if coherent:
        E = E.sum(axis=0, keepdims=True)
    return 0.5 * np.einsum("fnx,fnx->n", E, E)
