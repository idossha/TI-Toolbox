"""Carrier-derived high-frequency field metrics — single source of truth.

Safety metrics computed from per-pair carrier E-field vector arrays (shape
``(..., 3)`` each), following Cassarà et al. 2025, *Recommendations for the
Safe Application of Temporal Interference Stimulation in the Human Brain*
Part I (Bioelectromagnetics 46(2), e22542) and Part II (46(1), e22536).

The governing rule is Part II, p. 8: *"In the presence of multiple currents
(e.g., TIS channels), coherent field superposition was used for identical
frequencies, and incoherent superposition (i.e., SAR addition) was used when
the frequencies differed."*  So fields that share a carrier are summed **as
vectors first**; only then do distinct carriers combine — in power for
time-averaged quantities, and by worst-case relative phase for the peak.

Which fields share a carrier is declared by the montage: pass ``channels``
(the same ``(group_a, group_b)`` index grouping :func:`tit.calc.get_mTI_vectors`
takes) and each group becomes one coherently-summed carrier.  ``channels=None``
means every field is its own carrier, which is the independent-dyad default.

``hf_peak(*fields, channels=...)`` — peak carrier field.  Distinct carriers run
at mutually incommensurate frequencies, so every relative phase combination
occurs over time; the worst-case instantaneous magnitude is the max over sign
choices, ``max_s |sum_c s_c * E_c|`` over *carriers* ``c``.  At two carriers
this is exactly ``max(|E1+E2|, |E1-E2|)`` (Cassarà Part I, Eq. 3, p. 11: the
worst case is "in-phase, spatially aligned fields").

``hf_sar(*fields, channels=...)`` — heating driver, proportional to SAR.
Distinct carriers are incoherent, so power adds rather than amplitude:
``sum_c |E_c|^2`` (Cassarà Part I, p. 11: "the SAR distributions from the two
channels, rather than the E-fields themselves, must be summed"; Part II, p. 16:
total power deposition "is equal to the summed combination from all channels
(incoherent field superposition)").

Both are distinct from the stimulation-relevant modulation envelope
(``TI_max`` / ``TI_normal``), computed in :mod:`tit.calc`.

See Also
--------
tit.sim.TI : Writes hf_peak / hf_sar as volume fields on the TI mesh.
tit.sim.mTI : Writes hf_peak / hf_sar as volume fields on the mTI mesh.
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


def channel_index_groups(n_fields: int, channels) -> list[list[int]]:
    """Validate a ``channels`` spec and flatten it to one index group per carrier.

    ``channels`` is a sequence of ``(group_a, group_b)``, each group a sequence
    of integer indices into a list of ``n_fields`` carrier fields.  The two
    groups of a channel are the channel's two *different* carrier frequencies
    (they beat against each other); the fields within one group share a
    frequency and are phase-locked.  The returned list is the groups in flat
    channel order — ``[ch0_a, ch0_b, ch1_a, ch1_b, ...]`` — with empty groups
    dropped (an empty ``group_b`` is a non-beating carrier and contributes no
    field of its own).

    The spec must be an exact partition of ``range(n_fields)``: every field
    used exactly once.  Silently dropping an unreferenced field would describe
    a *different* montage from the one the caller passed.

    Raises
    ------
    ValueError
        No channels, an empty ``group_a``, an out-of-range index, an index
        reused across groups, or a field index that no channel uses.
    """
    channels = list(channels)
    if len(channels) == 0:
        raise ValueError("channels must contain at least one channel")

    seen: set[int] = set()
    groups: list[list[int]] = []
    for ci, (group_a, group_b) in enumerate(channels):
        group_a = list(group_a)
        group_b = list(group_b)
        if len(group_a) == 0:
            raise ValueError(f"channels[{ci}]: group_a must be non-empty")
        for label, group in (("group_a", group_a), ("group_b", group_b)):
            for idx in group:
                if not (0 <= idx < n_fields):
                    raise ValueError(
                        f"channels[{ci}] {label}: index {idx} out of range "
                        f"for {n_fields} fields"
                    )
                if idx in seen:
                    raise ValueError(
                        f"channels[{ci}] {label}: field index {idx} is "
                        "used in more than one channel group"
                    )
                seen.add(idx)
        groups.append(group_a)
        groups.append(group_b)

    missing = sorted(set(range(n_fields)) - seen)
    if missing:
        raise ValueError(
            f"channels must use every field exactly once; field index "
            f"{missing} " + ("is" if len(missing) == 1 else "are") + " unused. "
            "Add the field to a channel, or give it its own channel with an "
            "empty group_b (a non-beating carrier)."
        )
    return [g for g in groups if g]


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


def _carrier_stack(fields: tuple, channels) -> tuple[np.ndarray, tuple]:
    """Stack *fields* into one flat ``(C, M, 3)`` array of **carriers**.

    With ``channels=None`` every field is its own carrier and this is exactly
    :func:`_stack_fields` — bit-identical, including its error messages.
    Otherwise the fields in each declared group are summed **as vectors**
    (coherent superposition, Cassarà Part II p. 8) into one carrier, and the
    exposure metric sees ``C`` carriers rather than ``N`` raw fields.
    """
    stack, shape = _stack_fields(fields)
    if channels is None:
        return stack, shape
    groups = channel_index_groups(stack.shape[0], channels)
    summed = np.stack([stack[g].sum(axis=0) for g in groups], axis=0)
    return summed, shape


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


def hf_peak_is_exact(n_fields: int, channels=None) -> bool:
    """Is :func:`hf_peak` exact for this many carriers, or a lower bound?

    ``True`` up to `EXACT_SIGN_ENUM_MAX_FIELDS` carriers, where every one of
    the ``2**(C-1)`` sign patterns is enumerated.  Above that the direction
    sweep tries only the sign patterns implied by sampled directions, so the
    result is a **lower bound** on the true worst-case peak and is therefore
    slightly non-conservative as a safety metric.  Callers that record or
    display ``hf_peak`` should carry this flag alongside the value.

    Pass the same *channels* given to :func:`hf_peak`: grouping fields onto
    shared carriers reduces the carrier count, so a montage that would need
    the sweep as raw fields may be exact once its carriers are declared.
    """
    n = int(n_fields)
    if channels is not None:
        n = len(channel_index_groups(n, channels))
    return n <= EXACT_SIGN_ENUM_MAX_FIELDS


def hf_peak(*fields, channels=None) -> np.ndarray:
    """Peak carrier field: max over sign choices of the carrier vector sum.

    Fields sharing a carrier (one declared ``channels`` group) are summed as
    vectors first — they are phase-locked, so their relative sign is not free.
    Distinct carriers then combine at their worst-case relative phase, which
    for incommensurate frequencies is realised over time:
    ``max_s |sum_c s_c E_c|``.  At two carriers this is Cassarà et al. 2025
    Part I, Eq. 3 (p. 11), ``max(|E1+E2|, |E1-E2|)``.

    Exact sign enumeration (``2**(C-1)`` combinations over ``C`` carriers) is
    used up to `EXACT_SIGN_ENUM_MAX_FIELDS`. Above that, a Fibonacci-sphere
    direction sweep picks the best-sampled direction and evaluates the exact,
    realizable vector sum for the sign pattern it implies -- tighter than a
    raw support-function value, but still a lower bound (hence slightly
    non-conservative) since only sampled directions' sign patterns are tried.
    Query :func:`hf_peak_is_exact` for which path a montage takes.

    Parameters
    ----------
    *fields : array-like, shape ``(..., 3)``
        Two or more carrier E-field vectors (one per electrode pair), all
        the same shape.
    channels : sequence of (group_a, group_b), or None
        Which fields share a carrier, as index groups into *fields* (the
        grouping :func:`tit.calc.get_mTI_vectors` takes, and the montage's
        ``channels``).  ``None`` — the default — treats every field as its
        own carrier, the independent-dyad case.

    Returns
    -------
    numpy.ndarray, shape ``(...,)``
        The worst-case peak carrier field magnitude.

    Notes
    -----
    Declaring ``channels`` can only *lower* ``hf_peak`` relative to the
    ungrouped result, because grouping removes sign patterns that the
    ungrouped enumeration is free to pick but the hardware cannot realise:
    two electrode pairs driven from the same phase-locked source cannot be in
    anti-phase.  ``hf_sar`` moves the other way (see there).
    """
    stack, shape = _carrier_stack(fields, channels)
    n = stack.shape[0]
    if n <= EXACT_SIGN_ENUM_MAX_FIELDS:
        flat = _hf_peak_exact(stack)
    else:
        flat = _hf_peak_sweep(stack)
    return flat.reshape(shape[:-1])


def hf_sar(*fields, channels=None) -> np.ndarray:
    """Incoherent carrier heating driver, proportional to SAR: ``sum_c |E_c|^2``.

    Fields sharing a carrier are summed as vectors first (coherent
    superposition at identical frequency); the resulting carriers sit at
    different, incommensurate frequencies, so their SAR/power adds rather
    than their amplitudes — Cassarà et al. 2025 Part II, p. 8: *"coherent
    field superposition was used for identical frequencies, and incoherent
    superposition (i.e., SAR addition) was used when the frequencies
    differed."*

    This is a field-domain proxy in ``(V/m)^2``, **not** calibrated SAR.
    With ``E_c`` the sinusoidal *amplitude* (peak, as the paper's thresholds
    are stated), the time-averaged SAR of Part II Eq. 1 is
    ``(sigma / 2 rho) * hf_sar`` — the ``1/2`` being the sinusoid's
    time-average, applied once here and nowhere else in the toolbox.
    Equivalently the RMS-squared carrier field is ``hf_sar / 2``.

    Parameters
    ----------
    *fields : array-like, shape ``(..., 3)``
        Two or more carrier E-field vectors (one per electrode pair), all
        the same shape.
    channels : sequence of (group_a, group_b), or None
        Which fields share a carrier; see :func:`hf_peak`.  ``None`` treats
        every field as its own carrier.

    Returns
    -------
    numpy.ndarray, shape ``(...,)``
        ``sum_c |E_c|^2`` in ``(V/m)^2`` — proportional to tissue heating.

    Notes
    -----
    Declaring ``channels`` *raises* ``hf_sar`` wherever a group's fields
    reinforce -- by up to the size of the group when they are aligned, since
    ``|sum_i E_i|^2 = sum_i |E_i|^2 + cross terms`` -- leaves it unchanged
    where they are mutually orthogonal, and lowers it where they oppose.  The
    reinforcing case is the one that matters for safety: it is where the
    ungrouped value *understated* exposure.
    """
    stack, shape = _carrier_stack(fields, channels)
    flat = np.sum(np.linalg.norm(stack, axis=-1) ** 2, axis=0)
    return flat.reshape(shape[:-1])
