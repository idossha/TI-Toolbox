"""Carrier-derived high-frequency field metrics — single source of truth.

Safety metrics computed from *N* per-pair carrier E-field vector arrays
(shape ``(..., 3)`` each, one per electrode pair), following Cassarà et al.
2025, *Safety Recommendations for Temporal Interference Stimulation in the
Brain, Part I* (Bioelectromagnetics 46(2), doi:10.1002/bem.22542):

``hf_peak(*fields)`` — peak carrier field.  Carriers run at mutually
incommensurate frequencies, so every relative phase combination occurs over
time; the true worst-case instantaneous magnitude is the max over sign
choices, ``max_s |sum_i s_i * E_i|`` for ``s_i in {+1,-1}``.  At N=2 this is
exactly ``max(|E1+E2|, |E1-E2|)`` (Cassarà Eq. 3).

``hf_sar(*fields)`` — heating driver, proportional to SAR: carriers are
incoherent, so power adds rather than amplitude, giving ``sum_i |E_i|^2``.

Both are distinct from the stimulation-relevant modulation envelope
(``TI_max`` / ``TI_normal``), computed in :mod:`tit.calc`.

See Also
--------
tit.sim.TI : Writes hf_peak / hf_sar as volume fields on the TI mesh.
tit.source.fsaverage : Projects hf_peak / hf_sar onto fsaverage.
"""

from __future__ import annotations

import itertools

import numpy as np

#: Fields at or below this count use exact sign enumeration (2**(N-1)
#: combinations) in `hf_peak`; above it, a sign-refined direction sweep is
#: used instead (see `_hf_peak_sweep`). Measured cost of exact enumeration at
#: 200k elements: N=8 (128 combos) ~2.0s, N=12 (2048 combos) ~44.6s -- the
#: combinatorial blowup past N=8 is what the sweep fallback avoids.
EXACT_SIGN_ENUM_MAX_FIELDS = 8

# Spatial elements processed per chunk, bounding peak memory independent of
# input size for both the sign-enumeration and direction-sweep paths.
_CHUNK_SIZE = 20_000

# Direction count for the N > EXACT_SIGN_ENUM_MAX_FIELDS sweep fallback.
# The sweep is still a lower bound on the true max (only sampled directions'
# implied sign patterns are tried), so this is chosen generously to keep the
# sampling gap small.
_SWEEP_N_DIRECTIONS = 4000

# Directions processed per inner batch during the sweep, bounding memory
# alongside _CHUNK_SIZE (peak use ~ _CHUNK_SIZE * _SWEEP_DIR_BATCH, independent
# of N since the sweep accumulates one field at a time).
_SWEEP_DIR_BATCH = 200


def _stack_fields(fields: tuple) -> tuple[np.ndarray, tuple]:
    """Validate and stack N carrier fields into a flat ``(N, M, 3)`` array.

    Returns the stack plus the common original shape (for reshaping the
    result back). Raises ``ValueError`` if fewer than 2 fields, shapes
    differ, or the last axis isn't 3.
    """
    if len(fields) < 2:
        raise ValueError(f"hf_peak/hf_sar require at least 2 fields, got {len(fields)}")
    arrays = [np.asarray(f, dtype=float) for f in fields]
    shape = arrays[0].shape
    if shape[-1] != 3:
        raise ValueError(f"fields must have shape (..., 3), got last axis {shape[-1]}")
    for i, a in enumerate(arrays[1:], start=1):
        if a.shape != shape:
            raise ValueError(
                f"all fields must share the same shape: field 0 has {shape}, "
                f"field {i} has {a.shape}"
            )
    stack = np.stack(arrays, axis=0).reshape(len(arrays), -1, 3)
    return stack, shape


def _sign_matrix(n: int) -> np.ndarray:
    """The ``2**(n-1)`` sign vectors needed for the max-over-signs peak.

    The first sign is fixed to +1: flipping every sign leaves ``|sum|``
    unchanged, so enumerating the rest covers all distinct sums.
    """
    tail = np.array(list(itertools.product((1.0, -1.0), repeat=n - 1)))
    head = np.ones((tail.shape[0], 1))
    return np.hstack([head, tail])


def _hf_peak_exact(stack: np.ndarray) -> np.ndarray:
    """Exact ``max_s |sum_i s_i * E_i|`` via sign enumeration, chunked over rows."""
    n, m, _ = stack.shape
    signs = _sign_matrix(n)
    out = np.empty(m, dtype=float)
    for lo in range(0, m, _CHUNK_SIZE):
        hi = min(lo + _CHUNK_SIZE, m)
        block = stack[:, lo:hi, :]
        best = np.zeros(hi - lo, dtype=float)
        for row in signs:
            total = block[0] * row[0]
            for i in range(1, n):
                total = total + block[i] * row[i]
            np.maximum(best, np.linalg.norm(total, axis=-1), out=best)
        out[lo:hi] = best
    return out


def _fibonacci_directions(n_points: int) -> np.ndarray:
    """``n_points`` roughly-uniform unit directions on the sphere (golden-angle spiral)."""
    i = np.arange(n_points) + 0.5
    phi = np.arccos(1 - 2 * i / n_points)
    theta = np.pi * (3 - np.sqrt(5)) * i
    return np.stack(
        [np.sin(phi) * np.cos(theta), np.sin(phi) * np.sin(theta), np.cos(phi)],
        axis=-1,
    )


def _hf_peak_sweep(stack: np.ndarray) -> np.ndarray:
    """Sign-refined direction sweep for N > `EXACT_SIGN_ENUM_MAX_FIELDS`.

    Samples directions and finds each row's best support direction ``n*``
    (``max_n sum_i |E_i . n|``), then evaluates the *exact*, realizable
    vector sum for the sign pattern ``n*`` implies: ``s_i = sign(E_i . n*)``,
    result ``|sum_i s_i E_i|``. By Cauchy-Schwarz this is >= the raw support
    value (a mere projection), so it is both tighter and an actually
    achievable field state. Still a lower bound on the true max over all
    ``2**(N-1)`` sign combinations, since only the sampled directions'
    implied patterns are tried -- see `hf_peak`.
    """
    n, m, _ = stack.shape
    directions = _fibonacci_directions(_SWEEP_N_DIRECTIONS)
    out = np.empty(m, dtype=float)
    for lo in range(0, m, _CHUNK_SIZE):
        hi = min(lo + _CHUNK_SIZE, m)
        c = hi - lo
        best_support = np.full(c, -np.inf, dtype=float)
        best_dir = np.zeros(c, dtype=np.int64)
        for d0 in range(0, _SWEEP_N_DIRECTIONS, _SWEEP_DIR_BATCH):
            d1 = min(d0 + _SWEEP_DIR_BATCH, _SWEEP_N_DIRECTIONS)
            dirs_batch = directions[d0:d1]
            support = np.zeros((c, d1 - d0), dtype=float)
            for i in range(n):
                support += np.abs(stack[i, lo:hi, :] @ dirs_batch.T)
            batch_argmax = support.argmax(axis=1)
            batch_best = support[np.arange(c), batch_argmax]
            improved = batch_best > best_support
            best_support = np.where(improved, batch_best, best_support)
            best_dir = np.where(improved, d0 + batch_argmax, best_dir)

        n_star = directions[best_dir]  # (c, 3), each row's best direction
        total = np.zeros((c, 3), dtype=float)
        for i in range(n):
            e_i = stack[i, lo:hi, :]
            dot = np.einsum("cx,cx->c", e_i, n_star)
            sign = np.where(dot < 0, -1.0, 1.0)  # tie-break dot==0 to +1
            total += sign[:, None] * e_i
        out[lo:hi] = np.linalg.norm(total, axis=-1)
    return out


def hf_peak(*fields) -> np.ndarray:
    """Peak carrier field: max over sign choices of the vector sum (Cassarà 2025, Eq. 3).

    Exact sign enumeration (``2**(N-1)`` combinations) is used up to
    `EXACT_SIGN_ENUM_MAX_FIELDS` fields. Above that, a Fibonacci-sphere
    direction sweep picks the best-sampled direction and evaluates the exact,
    realizable vector sum for the sign pattern it implies -- tighter than a
    raw support-function value, but still a lower bound (hence slightly
    non-conservative) since only sampled directions' sign patterns are tried.

    Parameters
    ----------
    *fields : array-like, shape ``(..., 3)``
        Two or more carrier E-field vectors (one per electrode pair), all
        the same shape.

    Returns
    -------
    numpy.ndarray, shape ``(...,)``
        The worst-case peak carrier field magnitude.
    """
    stack, shape = _stack_fields(fields)
    n = stack.shape[0]
    if n <= EXACT_SIGN_ENUM_MAX_FIELDS:
        flat = _hf_peak_exact(stack)
    else:
        flat = _hf_peak_sweep(stack)
    return flat.reshape(shape[:-1])


def hf_sar(*fields) -> np.ndarray:
    """Incoherent carrier heating driver, proportional to SAR: ``sum_i |E_i|^2``.

    Carriers sit at different, incommensurate frequencies, so their SAR/power
    adds rather than their amplitudes. This is a field-domain proxy in
    ``(V/m)^2``, **not** calibrated SAR: the latter is ``(sigma / 2 rho) *
    hf_sar`` and needs per-tissue conductivity and density.

    Parameters
    ----------
    *fields : array-like, shape ``(..., 3)``
        Two or more carrier E-field vectors (one per electrode pair), all
        the same shape.

    Returns
    -------
    numpy.ndarray, shape ``(...,)``
        ``sum_i |E_i|^2`` in ``(V/m)^2`` — proportional to tissue heating.
    """
    stack, shape = _stack_fields(fields)
    flat = np.sum(np.linalg.norm(stack, axis=-1) ** 2, axis=0)
    return flat.reshape(shape[:-1])
