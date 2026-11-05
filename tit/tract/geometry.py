"""Streamline geometry and field-on-tract metrics (numpy only).

Streamlines are held concatenated: ``points`` (P, 3) in mm and ``offsets`` (S + 1,) with
streamline ``s`` at ``points[offsets[s]:offsets[s + 1]]``. Every streamline is resampled
to a uniform arc-length step ``h_s`` (:func:`resample`), so a derivative along it is a
central difference (one-sided at the two ends, as ``numpy.gradient``) and an arc-length
mean is the trapezoid rule.

Per-point quantities (method spec section 2; each is a field descriptor, not a
prediction of activation):

* ``E_c . t`` per channel (V/m), ``t`` the unit tangent;
* ``ti_along`` = :func:`tit.calc.envelope` of the channel fields along ``t`` (V/m);
* ``ti_max`` = :func:`tit.calc.envelope_max` and ``ti_avg`` = :func:`tit.calc.envelope_mean`
  (the envelope averaged over all directions), both V/m;
* ``align`` = ti_along / ti_max and ``avg_ratio`` = ti_avg / ti_max (what ``align`` is for a
  direction drawn uniformly at random), and ``align_index`` = ti_along / ti_avg (above 1:
  more envelope along the streamline than along a random direction);
* ``e_par_pk`` = sum_c |E_c . t| (V/m) and ``p_par`` = 1/2 sum_c (E_c . t)^2 (V^2/m^2);
* ``f_c`` = -d(E_c . t)/ds at a fixed physical scale (V/m^2, Rattay's activating function of
  each carrier, :func:`smoothed_derivative`) and ``f_am`` = the envelope of the ``f_c`` (for
  one pair 2 min(|f_a|, |f_b|)), derived from the linearity of d/ds, not taken from a paper.
  A SimNIBS field is constant per tetrahedron, so a pointwise derivative grows without
  bound as the sampling step shrinks; the scale makes ``f`` a property of the field.

Signed quantities (``E_c . t``, ``f_c``) depend on which way a streamline runs; callers
orient streamlines first (:func:`tit.tract.network.orient`).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from tit.calc import envelope, envelope_max, envelope_mean

#: mm -> m, for derivatives taken along arc length in mm.
_PER_MM_TO_PER_M = 1e3


def resample(
    streamlines: Sequence[np.ndarray], step: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resample every streamline to a uniform arc-length step close to *step*.

    Each streamline of length ``L`` gets ``n = max(2, round(L / step) + 1)`` points, so
    its own step is ``h = L / (n - 1)``, and keeps both end points.

    Returns:
        ``(points (P, 3), offsets (S + 1,), h (S,))``.

    Raises:
        ValueError: a streamline has fewer than two points or zero length.
    """
    out, counts, hs = [], [], []
    for sl in streamlines:
        sl = np.asarray(sl, dtype=np.float64)
        if len(sl) < 2:
            raise ValueError("a streamline needs at least two points")
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(sl, axis=0), axis=1))]
        length = arc[-1]
        if length <= 0:
            raise ValueError("a streamline has zero length")
        n = max(2, int(round(length / step)) + 1)
        s = np.linspace(0.0, length, n)
        out.append(np.column_stack([np.interp(s, arc, sl[:, k]) for k in range(3)]))
        counts.append(n)
        hs.append(length / (n - 1))
    offsets = np.r_[0, np.cumsum(counts)].astype(np.intp)
    points = np.concatenate(out) if out else np.zeros((0, 3))
    return points, offsets, np.asarray(hs, dtype=np.float64)


def per_point(values: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Broadcast a per-streamline array (S, ...) to every point (P, ...)."""
    return np.repeat(values, np.diff(offsets), axis=0)


def derivative(values: np.ndarray, offsets: np.ndarray, h: np.ndarray) -> np.ndarray:
    """d(values)/ds along each streamline (``numpy.gradient``, edge order 1, per streamline).

    *values* is (P,) or (P, k); *h* (S,) is each streamline's step. Returns per mm.
    """
    v = np.asarray(values, dtype=np.float64)
    hp = per_point(h, offsets).reshape((-1,) + (1,) * (v.ndim - 1))
    d = np.empty_like(v)
    d[1:-1] = (v[2:] - v[:-2]) / (2.0 * hp[1:-1])
    first, last = offsets[:-1], offsets[1:] - 1
    d[first] = (v[first + 1] - v[first]) / hp[first]
    d[last] = (v[last] - v[last - 1]) / hp[last]
    return d


def tangents(points: np.ndarray, offsets: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Unit tangents (P, 3) by central differences along each streamline."""
    d = derivative(points, offsets, h)
    norm = np.linalg.norm(d, axis=1, keepdims=True)
    return np.divide(d, norm, out=np.zeros_like(d), where=norm > 0)


def curvature(t: np.ndarray, offsets: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Curvature |dt/ds| (P,) in 1/mm."""
    return np.linalg.norm(derivative(t, offsets, h), axis=1)


def _ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    return np.divide(num, den, out=np.zeros_like(den), where=den > 0)


def _along(values, offsets, h, q):
    """Each streamline's *values* (P,) linearly interpolated at arc positions *q* (P,)."""
    n = per_point(np.diff(offsets), offsets)
    u = q / per_point(h, offsets)
    lo = np.clip(np.floor(u).astype(np.intp), 0, n - 2)
    frac = u - lo
    base = per_point(offsets[:-1], offsets)
    return (1 - frac) * values[base + lo] + frac * values[base + lo + 1]


def smoothed_derivative(
    values: np.ndarray, offsets: np.ndarray, h: np.ndarray, scale: float
) -> np.ndarray:
    """d(values)/ds per mm of *values* smoothed by a triangle of half-width *scale* mm.

    With ``C`` the running arc-length integral of *values* along its streamline,
    ``(C(s + a) - 2 C(s) + C(s - a)) / a^2`` is the derivative of the triangle-weighted
    mean, ``a = min(scale, L / 2)``. Integrating first keeps the result converging as the
    step shrinks on a piecewise-constant field. Within ``a`` of an end, the value at ``a``
    from that end is used, so the window never leaves the streamline.
    """
    v = np.asarray(values, dtype=np.float64)
    hp = per_point(h, offsets)
    inc = np.zeros_like(v)
    inc[1:] = 0.5 * (v[1:] + v[:-1]) * hp[1:]
    inc[offsets[:-1]] = 0.0
    c = np.cumsum(inc)
    c -= per_point(c[offsets[:-1]], offsets)
    length = per_point(lengths(offsets, h), offsets)
    s = (np.arange(len(v)) - per_point(offsets[:-1], offsets)) * hp
    a = np.minimum(scale, 0.5 * length)
    s = np.clip(s, a, length - a)
    up = _along(c, offsets, h, s + a)
    down = _along(c, offsets, h, s - a)
    return (up - 2.0 * _along(c, offsets, h, s) + down) / a**2


def point_metrics(
    fields: Sequence[np.ndarray],
    t: np.ndarray,
    offsets: np.ndarray,
    h: np.ndarray,
    scale_mm: float = 2.0,
) -> dict[str, np.ndarray]:
    """Per-point field descriptors (module docstring) for channel fields ``[E1, ..., E2K]``.

    *scale_mm* is the half-width of the activating function's smoothing.
    Returns a dict of (P,) arrays plus ``e_par`` (C, P) and ``f`` (C, P).
    """
    E = [np.asarray(e, dtype=np.float64) for e in fields]
    e_par = np.stack([np.einsum("pk,pk->p", e, t) for e in E])
    ti_along = envelope(E, t)
    ti_max = envelope_max(E)
    ti_avg = envelope_mean(E)
    f = -_PER_MM_TO_PER_M * np.stack(
        [smoothed_derivative(p, offsets, h, scale_mm) for p in e_par]
    )
    x = np.array([1.0, 0.0, 0.0])
    f_am = envelope([fc[:, None] * x for fc in f], x)
    return {
        "e_par": e_par,
        "ti_along": ti_along,
        "ti_max": ti_max,
        "ti_avg": ti_avg,
        "align": _ratio(ti_along, ti_max),
        "avg_ratio": _ratio(ti_avg, ti_max),
        "align_index": _ratio(ti_along, ti_avg),
        "e_par_pk": np.abs(e_par).sum(axis=0),
        "p_par": 0.5 * (e_par**2).sum(axis=0),
        "f": f,
        "f_am": f_am,
    }


def _trapezoid_weights(offsets: np.ndarray, h: np.ndarray) -> np.ndarray:
    w = per_point(h, offsets).copy()
    w[offsets[:-1]] *= 0.5
    w[offsets[1:] - 1] *= 0.5
    return w


def streamline_stats(
    values: np.ndarray,
    offsets: np.ndarray,
    h: np.ndarray,
    thresholds: Sequence[float] = (),
) -> dict[str, np.ndarray]:
    """Per-streamline ``max``, arc-length ``mean``, ``start``/``end`` values and, per
    threshold ``tau``, the fraction of arc length where ``value >= tau``.

    Returns (S,) arrays keyed ``max``, ``mean``, ``start``, ``end`` and ``frac_ge_<tau>``.
    """
    first = offsets[:-1]
    w = _trapezoid_weights(offsets, h)
    length = np.add.reduceat(w, first)
    out = {
        "max": np.maximum.reduceat(values, first),
        "mean": np.add.reduceat(w * values, first) / length,
        "start": values[first],
        "end": values[offsets[1:] - 1],
    }
    for tau in thresholds:
        out[f"frac_ge_{tau:g}"] = np.add.reduceat(w * (values >= tau), first) / length
    return out


def lengths(offsets: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Arc length (S,) of each resampled streamline, mm."""
    return h * (np.diff(offsets) - 1)


def profiles(values: np.ndarray, offsets: np.ndarray, n_nodes: int) -> np.ndarray:
    """Each streamline's values at *n_nodes* equally spaced arc-length nodes (S, n_nodes).

    Linear interpolation on the uniform resampling, start to end: orient the streamlines
    first (:func:`tit.tract.network.orient`) so node 0 is the same end for all.
    """
    n = np.diff(offsets).astype(np.float64)
    u = np.linspace(0.0, 1.0, n_nodes)[None, :] * (n - 1)[:, None]
    lo = np.floor(u).astype(np.intp)
    lo = np.minimum(lo, (n - 2).astype(np.intp)[:, None])
    frac = u - lo
    base = offsets[:-1, None]
    return (1 - frac) * values[base + lo] + frac * values[base + lo + 1]


def bundle_summary(
    per_streamline: dict[str, np.ndarray],
    thresholds: Sequence[float] = (),
) -> dict:
    """Across-streamline distribution of a bundle: median and p5/p95 of every
    per-streamline array, and the fraction of streamlines whose ``ti_along_max`` is
    at least each threshold."""
    out: dict = {"n_streamlines": int(len(next(iter(per_streamline.values()))))}
    if out["n_streamlines"] == 0:
        return out
    for key, v in per_streamline.items():
        p5, med, p95 = np.percentile(v, [5, 50, 95])
        out[key] = {"median": float(med), "p5": float(p5), "p95": float(p95)}
    for tau in thresholds:
        out[f"frac_streamlines_ti_along_max_ge_{tau:g}"] = float(
            np.mean(per_streamline["ti_along_max"] >= tau)
        )
    return out
