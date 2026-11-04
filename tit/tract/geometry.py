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
* ``ti_max`` = :func:`tit.calc.envelope_max` (V/m) and ``align`` = ti_along / ti_max;
* ``e_par_pk`` = sum_c |E_c . t| (V/m) and ``p_par`` = 1/2 sum_c (E_c . t)^2 (V^2/m^2);
* ``f_c`` = -d(E_c . t)/ds (V/m^2, Rattay's activating function of each carrier) and
  ``f_am`` = the envelope of the ``f_c`` (for one pair 2 min(|f_a|, |f_b|)), derived
  from the linearity of d/ds, not taken from a paper.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from tit.calc import envelope, envelope_max

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


def point_metrics(
    fields: Sequence[np.ndarray], t: np.ndarray, offsets: np.ndarray, h: np.ndarray
) -> dict[str, np.ndarray]:
    """Per-point field descriptors (module docstring) for channel fields ``[E1, ..., E2K]``.

    Returns a dict of (P,) arrays plus ``e_par`` (C, P) and ``f`` (C, P).
    """
    E = [np.asarray(e, dtype=np.float64) for e in fields]
    e_par = np.stack([np.einsum("pk,pk->p", e, t) for e in E])
    ti_along = envelope(E, t)
    ti_max = envelope_max(E)
    f = -np.stack([derivative(p, offsets, h) for p in e_par]) * _PER_MM_TO_PER_M
    x = np.array([1.0, 0.0, 0.0])
    f_am = envelope([fc[:, None] * x for fc in f], x)
    return {
        "e_par": e_par,
        "ti_along": ti_along,
        "ti_max": ti_max,
        "align": np.divide(
            ti_along, ti_max, out=np.zeros_like(ti_max), where=ti_max > 0
        ),
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


def orientation_flips(points: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Which streamlines to reverse so all run the way the first one does (S,) bool.

    A streamline is reversed when its end points are closer to the reference's end
    points swapped than in order (the end-point form of DIPY's ``orient_by_streamline``).
    """
    a, b = points[offsets[:-1]], points[offsets[1:] - 1]
    keep = np.linalg.norm(a - a[0], axis=1) + np.linalg.norm(b - b[0], axis=1)
    swap = np.linalg.norm(a - b[0], axis=1) + np.linalg.norm(b - a[0], axis=1)
    return swap < keep


def profiles(
    values: np.ndarray, offsets: np.ndarray, n_nodes: int, flips: np.ndarray
) -> np.ndarray:
    """Each streamline's values at *n_nodes* equally spaced arc-length nodes (S, n_nodes).

    Linear interpolation on the uniform resampling; reversed streamlines (*flips*) are
    read end to start, so node 0 sits at the same end of the bundle for all.
    """
    n = np.diff(offsets).astype(np.float64)
    u = np.linspace(0.0, 1.0, n_nodes)[None, :] * (n - 1)[:, None]
    u = np.where(flips[:, None], (n - 1)[:, None] - u, u)
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
