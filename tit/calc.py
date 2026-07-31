#!/usr/bin/env simnibs_python
"""Temporal interference field calculation utilities.

Vectorised NumPy implementations of the TI/mTI modulation-amplitude
envelope from Grossman et al. (2017), extended to an arbitrary even
number of electrode pairs (mTI).

Public API
----------
get_TI_vectors
    TI modulation-amplitude vectors for a single electrode pair (K=1).
get_mTI_vectors
    Modulation-amplitude vectors for K >= 1 electrode pairs; the
    verified N>2 replacement for :func:`get_nTI_vectors`.
get_TI_avg
    Direction-averaged modulation depth for K >= 1 electrode pairs.
get_magnitude_am
    Direction-free magnitude-envelope AM, K >= 1 electrode pairs.
get_nTI_vectors
    Deprecated. Recursive binary-tree N-field TI; not physically valid
    for N > 2. Delegates to :func:`get_mTI_vectors`.

Attribution
-----------
The K >= 2 envelope and the ``_fibonacci_sphere`` /
``_validate_field_list`` helpers originate from collaborator Larissa
Albantakis's branch ``alba/mTI_testing`` and are ported here with
attribution, not reimplemented. ``get_magnitude_am`` is likewise ported
from that branch's ``_botzanowski_magnitude_am_components``.
"""

import warnings

import numpy as np


def get_TI_vectors(E1_org, E2_org):
    """Compute the TI modulation-amplitude vectors for two electric fields.

    Grossman et al. (2017) closed form: after ordering fields ``|E1| >=
    |E2|`` and flipping ``E2`` for an acute angle, ``TI = 2*E2`` when
    ``|E2| <= |E1|*cos(alpha)`` (parallel regime), else ``TI = 2 *`` the
    component of ``E2`` perpendicular to ``E1 - E2`` (oblique regime).

    Parameters
    ----------
    E1_org, E2_org : np.ndarray, shape (N, 3)
        Electric field vectors [V/m] from the two electrode pairs.

    Returns
    -------
    np.ndarray, shape (N, 3)
        TI vectors [V/m]: direction/magnitude of max envelope modulation.

    References
    ----------
    Grossman, N. et al. (2017). Cell, 169(6), 1029-1041.
    """
    assert E1_org.shape == E2_org.shape, "E1 and E2 must have same shape"
    assert E1_org.shape[1] == 3, "Vectors must be 3D"

    E1 = E1_org.copy()
    E2 = E2_org.copy()

    # Order fields so |E1| >= |E2|.
    idx_swap = np.linalg.norm(E2, axis=1) > np.linalg.norm(E1, axis=1)
    E1[idx_swap], E2[idx_swap] = E2[idx_swap], E1_org[idx_swap]

    # Flip E2 for an acute angle between the two fields.
    idx_flip = np.sum(E1 * E2, axis=1) < 0
    E2[idx_flip] = -E2[idx_flip]

    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)
    denom = normE1 * normE2
    denom[denom == 0] = 1.0
    cosalpha = np.clip(np.sum(E1 * E2, axis=1) / denom, -1.0, 1.0)

    # Regime 1 (parallel): |E2| <= |E1|*cos(alpha) -> TI = 2*E2.
    regime1_mask = normE2 <= normE1 * cosalpha
    TI_vectors = np.zeros_like(E1)
    TI_vectors[regime1_mask] = 2.0 * E2[regime1_mask]

    # Regime 2 (oblique): TI = 2 * (E2 perpendicular to h = E1 - E2).
    regime2_mask = ~regime1_mask
    if np.any(regime2_mask):
        h = E1[regime2_mask] - E2[regime2_mask]
        h_norm = np.linalg.norm(h, axis=1)
        h_norm[h_norm == 0] = 1.0
        e_h = h / h_norm[:, None]

        E2_parallel_component = np.sum(E2[regime2_mask] * e_h, axis=1)[:, None] * e_h
        E2_perp = E2[regime2_mask] - E2_parallel_component
        TI_vectors[regime2_mask] = 2.0 * E2_perp

    return TI_vectors


def get_mTI_vectors(fields, psi=None):
    """Compute mTI modulation-amplitude vectors for K >= 1 electrode pairs.

    ``fields`` is ``[E_1a, E_1b, ..., E_Ka, E_Kb]``, 2K arrays of shape
    ``(N, 3)``. K=1 dispatches exactly to :func:`get_TI_vectors`; K>=2
    returns ``best_direction * md`` from the verified
    :func:`_mti_modulation_depth` envelope.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Field vectors for 2K sub-channels (K electrode pairs), K >= 1.
    psi : array-like, shape (K,), or None
        Per-pair envelope phase offset (radians); ``None`` means
        phase-aligned pairs (``psi_k=0``), the standard case. Ignored
        at K=1 (phase-invariant there).

    Returns
    -------
    np.ndarray, shape (N, 3)
        Modulation-amplitude vectors [V/m]; norm is the modulation depth.

    Raises
    ------
    ValueError
        Odd/short field list, mismatched shapes, or non-``(N, 3)`` arrays.

    References
    ----------
    Grossman, N. et al. (2017). Cell, 169(6), 1029-1041 (K=1 closed form).
    Botzanowski, B. et al. (2025). Bioelectronic Medicine, 11(1), 7
    (multipolar AM envelope, K >= 2).
    """
    arrs = _validate_field_list(fields)
    n_pairs = len(arrs) // 2
    _validate_psi(psi, n_pairs)

    if n_pairs == 1:
        return get_TI_vectors(arrs[0], arrs[1])

    result = _mti_modulation_depth(arrs, psi=psi)
    return result["best_direction"] * result["md"][:, None]


def get_TI_avg(fields, psi=None):
    """Direction-averaged modulation depth for K >= 1 electrode pairs.

    ``TI_max`` (:func:`get_mTI_vectors`) maximizes the envelope over
    direction -- a best case for a neuron aligned with the optimal axis.
    ``TI_avg`` instead averages the same coarse Fibonacci-sphere sweep
    over all sampled directions, giving what a randomly-oriented neuron
    sees on average. Local refinement (accurate for a single best
    direction only) is skipped as irrelevant to an average.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Field vectors for 2K sub-channels (K electrode pairs), K >= 1.
    psi : array-like, shape (K,), or None
        Per-pair envelope phase offset (radians); see
        :func:`get_mTI_vectors`.

    Returns
    -------
    np.ndarray, shape (N,)
        Modulation depth [V/m], averaged over sampled directions.
    """
    arrs = _validate_field_list(fields)
    n_pairs = len(arrs) // 2
    psi_arr = _validate_psi(psi, n_pairs)
    return _mti_modulation_depth_avg(arrs, psi_arr)


def get_magnitude_am(fields):
    """Direction-free amplitude-modulation envelope of ``||E(t)||``.

    Not the direction-maximized modulation depth from
    :func:`get_mTI_vectors` -- the AM envelope of the field *magnitude*
    itself, no direction search, computed on the full 3-vectors:
    ``P = 0.5*sum_i ||E_i||^2``, ``Q = |sum_k E_ka . E_kb|`` (3D dot
    products per pair), result ``= sqrt(2*(P+Q)) - sqrt(2*max(P-Q, 0))``.
    At K=1 this reduces to ``abs(|E1+E2| - |E1-E2|)``.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Field vectors for 2K sub-channels (K electrode pairs), K >= 1.

    Returns
    -------
    np.ndarray, shape (N,)
        Magnitude-AM envelope [V/m].

    See Also
    --------
    get_mTI_vectors : Direction-maximized modulation-amplitude vectors --
        a different quantity from this magnitude envelope.

    References
    ----------
    Botzanowski, B. et al. (2025). Bioelectronic Medicine, 11(1), 7.
    """
    arrs = _validate_field_list(fields)
    n_pairs = len(arrs) // 2

    P = np.zeros(arrs[0].shape[0], dtype=np.float64)
    for e in arrs:
        P += np.sum(e * e, axis=1)
    P *= 0.5

    dot_sum = np.zeros(arrs[0].shape[0], dtype=np.float64)
    for k in range(n_pairs):
        dot_sum += np.sum(arrs[2 * k] * arrs[2 * k + 1], axis=1)
    Q = np.abs(dot_sum)

    env_max = np.sqrt(2.0 * np.maximum(P + Q, 0.0))
    env_min = np.sqrt(2.0 * np.maximum(P - Q, 0.0))
    return env_max - env_min


def get_nTI_vectors(fields):
    """Deprecated: recursive binary-tree N-field TI. Use :func:`get_mTI_vectors`.

    This paired fields via ``TI(TI(E1,E2), TI(E3,E4), ...)``, feeding
    already-modulated envelope vectors back into :func:`get_TI_vectors` --
    a formula derived only for two carrier fields. Measured against the
    verified :func:`_mti_modulation_depth` envelope on random fields: signed
    mean error +38.6% (range -90% to +416%) at N=4, +103% at N=8.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)

    Returns
    -------
    np.ndarray, shape (N, 3)
    """
    warnings.warn(
        "get_nTI_vectors is deprecated and physically invalid for N>2 "
        "(measured +38.6% mean error at N=4 vs. the verified envelope); "
        "use get_mTI_vectors instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_mTI_vectors(fields)


def _mti_modulation_depth(
    fields,
    psi=None,
    directions=None,
    num_directions=192,
    chunk_size=16384,
    refine=True,
):
    r"""Compute the coherent multi-pair TI modulation-depth envelope.

    For K electrode pairs sharing a beat frequency, projected onto unit
    direction ``n``: ``MD = sqrt(2)*(sqrt(P+Q) - sqrt(P-Q))``, where
    ``P = 0.5*sum_k(a_k^2 + b_k^2)`` is total carrier power and
    ``Q = |sum_k a_k*b_k*exp(i*psi_k)|`` is the coherent phasor sum of the
    signed projections ``a_k = E_ka . n``, ``b_k = E_kb . n``. With
    ``psi=None`` every pair is assumed phase-aligned (``psi_k=0``). For
    K=1 this reduces exactly to ``2*min(|a|,|b|)`` (Grossman et al. 2017)
    and is solved via an exact closed form (Hirata et al. 2024) with no
    direction search. For K>=2 with ``directions=None``, the best
    direction per element is found by a coarse Fibonacci-sphere sweep,
    refined locally by default (``refine=True``) to control sampling
    error. Verified against a time-domain ground truth.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Field vectors ordered ``[E_1a, E_1b, E_2a, E_2b, ...]``, 2K arrays.
    psi : array-like, shape (K,), or None
        Per-pair envelope phase offset in radians.
    directions : np.ndarray, shape (N, 3), or None
        Fixed per-element direction to evaluate at, instead of searching.
    num_directions : int, default 192
        Coarse Fibonacci-sphere sample count used when searching (K>=2).
    chunk_size : int, default 16384
        Elements processed per chunk, bounding peak memory.
    refine : bool, default True
        Locally refine the coarse-sweep result for K>=2 (recommended);
        ``False`` reproduces the raw coarse sweep only.

    Returns
    -------
    dict
        ``"md"`` (N,): modulation depth. ``"carrier_power"`` (N,): ``P``
        at the direction ``md`` was evaluated at. ``"best_direction"``
        (N, 3): unit vector the envelope was evaluated at.

    Raises
    ------
    ValueError
        If ``fields`` is not an even-length list of identically-shaped
        ``(N, 3)`` arrays, or ``psi``/``directions`` have the wrong shape.

    References
    ----------
    Grossman, N. et al. (2017). Cell, 169(6), 1029-1041.
    """
    arrs = _validate_field_list(fields)
    n_pairs = len(arrs) // 2
    psi_arr = _validate_psi(psi, n_pairs)

    if directions is not None:
        return _mti_modulation_depth_at_directions(arrs, psi_arr, directions)

    if refine and n_pairs == 1:
        md, P, best_direction = _k1_exact_envelope(arrs[0], arrs[1])
        return {"md": md, "carrier_power": P, "best_direction": best_direction}

    return _mti_modulation_depth_sweep(
        arrs, psi_arr, num_directions, chunk_size, refine
    )


def _validate_field_list(fields):
    """Validate a field list: even length >= 2, identical (N, 3) shapes.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution").
    """
    arrs = [np.asarray(field, dtype=np.float64) for field in fields]
    n = len(arrs)
    if n < 2 or n % 2 != 0:
        raise ValueError(f"mTI requires an even number of fields >= 2, got {n}")
    ref_shape = arrs[0].shape
    if len(ref_shape) != 2 or ref_shape[1] != 3:
        raise ValueError(f"Fields must have shape (N, 3), got {ref_shape}")
    for i, arr in enumerate(arrs[1:], start=2):
        if arr.shape != ref_shape:
            raise ValueError(
                "All fields must have identical shape; "
                f"field 1 has {ref_shape}, field {i} has {arr.shape}"
            )
    return arrs


def _validate_psi(psi, n_pairs):
    """Normalise/validate the per-pair envelope phase array."""
    if psi is None:
        return None
    psi_arr = np.asarray(psi, dtype=np.float64)
    if psi_arr.shape != (n_pairs,):
        raise ValueError(
            "psi must be None or have shape "
            f"({n_pairs},) -- one phase offset per electrode pair; got "
            f"shape {psi_arr.shape}"
        )
    return psi_arr


def _pairwise_products(proj_fields, psi):
    """Return (P, Q): carrier power and coherent phasor magnitude.

    ``proj_fields`` is a list of 2K arrays of identical shape (signed
    projections onto one or more candidate directions). When ``psi`` is
    ``None`` or all-zero, ``Q`` reduces to a real-only sum, ``|sum_k
    a_k*b_k|`` (equivalent to evaluating the general phasor form at
    ``psi=0``).
    """
    n_pairs = len(proj_fields) // 2

    P = np.zeros_like(proj_fields[0], dtype=np.float64)
    for p in proj_fields:
        P += p * p
    P *= 0.5

    use_phase = psi is not None and np.any(psi != 0.0)
    if use_phase:
        z = np.zeros_like(P, dtype=np.complex128)
        for k in range(n_pairs):
            a = proj_fields[2 * k]
            b = proj_fields[2 * k + 1]
            z += (a * b) * np.exp(1j * psi[k])
        Q = np.abs(z)
    else:
        b_sum = np.zeros_like(P)
        for k in range(n_pairs):
            a = proj_fields[2 * k]
            b = proj_fields[2 * k + 1]
            b_sum += a * b
        Q = np.abs(b_sum)

    return P, Q


def _envelope_from_PQ(P, Q):
    """MD = sqrt(2) * (sqrt(P+Q) - sqrt(P-Q)), clamped against negative
    round-off inside the square roots."""
    smin = np.maximum(P - Q, 0.0)
    smax = np.maximum(P + Q, 0.0)
    return np.sqrt(2.0 * smax) - np.sqrt(2.0 * smin)


def _k1_exact_envelope(E1, E2):
    r"""Exact best-direction K=1 envelope via the sign-agnostic closed form
    (Hirata et al. 2024), with no sweep:

    .. math::

        MD = \begin{cases}
            2\min(|E_1|,|E_2|) & \min(|E_1|,|E_2|) \le \sqrt{|E_1\cdot E_2|} \\
            \dfrac{2|E_1\times E_2|}{\min(|E_1-E_2|,|E_1+E_2|)} & \text{otherwise}
        \end{cases}

    Verified to match :func:`get_TI_vectors`'s magnitude to < 1e-12 over
    a large sample of random field pairs. ``psi`` has no effect at K=1: a
    single complex term's magnitude is phase-invariant.

    Returns
    -------
    md : np.ndarray, shape (N,)
    carrier_power : np.ndarray, shape (N,)
        ``P = 0.5 * (a^2 + b^2)`` evaluated at the same direction as ``md``.
    best_direction : np.ndarray, shape (N, 3)
        Unit vector (sign is arbitrary -- MD and P are direction-sign
        invariant).
    """
    n = E1.shape[0]
    norm_e1 = np.linalg.norm(E1, axis=1)
    norm_e2 = np.linalg.norm(E2, axis=1)
    dot = np.sum(E1 * E2, axis=1)
    min_norm = np.minimum(norm_e1, norm_e2)

    md = np.zeros(n, dtype=np.float64)
    best_dir = np.tile(np.array([0.0, 0.0, 1.0]), (n, 1))

    # Regime A ("parallel"): the smaller field's own direction is optimal.
    regime_a = min_norm <= np.sqrt(np.abs(dot))
    if np.any(regime_a):
        use_e1 = norm_e1[regime_a] <= norm_e2[regime_a]
        e_small = np.where(use_e1[:, None], E1[regime_a], E2[regime_a])
        norm_small = np.where(use_e1, norm_e1[regime_a], norm_e2[regime_a])
        nonzero = norm_small > 0.0
        norm_small_safe = np.where(nonzero, norm_small, 1.0)
        dir_a = e_small / norm_small_safe[:, None]
        rows_a = np.flatnonzero(regime_a)
        best_dir[rows_a[nonzero]] = dir_a[nonzero]
        md[regime_a] = 2.0 * min_norm[regime_a]

    # Regime B ("oblique"): optimal direction is the component of either
    # field perpendicular to h = E1 -/+ E2 (whichever has smaller norm);
    # E1_perp == E2_perp exactly for that choice of h, so projecting
    # either field is exact.
    regime_b = ~regime_a
    if np.any(regime_b):
        e1b, e2b = E1[regime_b], E2[regime_b]
        h_minus = e1b - e2b
        h_plus = e1b + e2b
        norm_minus = np.linalg.norm(h_minus, axis=1)
        norm_plus = np.linalg.norm(h_plus, axis=1)
        use_minus = norm_minus <= norm_plus
        h = np.where(use_minus[:, None], h_minus, h_plus)
        h_norm = np.where(use_minus, norm_minus, norm_plus)
        h_nonzero = h_norm > 0.0
        h_norm_safe = np.where(h_nonzero, h_norm, 1.0)
        e_h = h / h_norm_safe[:, None]

        e2_perp = e2b - np.sum(e2b * e_h, axis=1, keepdims=True) * e_h
        perp_norm = np.linalg.norm(e2_perp, axis=1)
        perp_nonzero = perp_norm > 0.0
        perp_norm_safe = np.where(perp_nonzero, perp_norm, 1.0)
        dir_b = e2_perp / perp_norm_safe[:, None]

        cross_norm = np.linalg.norm(np.cross(e1b, e2b), axis=1)
        md_b = np.where(h_nonzero, 2.0 * cross_norm / h_norm_safe, 0.0)

        rows_b = np.flatnonzero(regime_b)
        valid = h_nonzero & perp_nonzero
        best_dir[rows_b[valid]] = dir_b[valid]
        md[regime_b] = md_b

    a = np.sum(E1 * best_dir, axis=1)
    b = np.sum(E2 * best_dir, axis=1)
    P = 0.5 * (a * a + b * b)
    return md, P, best_dir


# Local refinement (K>=2), pure NumPy -- no scipy dependency, so this stays
# testable under the project's mocked-scipy test environment. A single-seed
# local search (refine only around the coarse sweep's argmax) is not robust:
# the K>=2 envelope surface can have multiple close local maxima, and the
# coarse sweep occasionally ranks a decoy peak above the true global one.
# Diverse, angularly-spaced seeds (`_diverse_top_m_directions`) fix this at
# a modest, bounded extra cost.

_REFINE_N_ROUNDS = 3
_REFINE_PATCH_SIZE = 16
_REFINE_SHRINK = 0.4
_REFINE_N_SEEDS = 6
_REFINE_MIN_SEED_ANGLE_DEG = 25.0


def _local_patch_directions(centers, half_angle, n_patch):
    """Return ``n_patch`` unit directions within angular radius
    ``half_angle`` (radians) of each row of ``centers``, an array of unit
    vectors with an arbitrary leading batch shape ``(..., 3)``. Output has
    shape ``(..., n_patch, 3)``.

    Uses a deterministic spherical-cap parameterisation: an orthonormal
    tangent basis ``(u, v)`` perpendicular to each center, then a
    Fibonacci-spiral set of polar offsets bounded by ``half_angle``.
    """
    batch_shape = centers.shape[:-1]
    c = centers.reshape(-1, 3)
    m = c.shape[0]

    ref = np.tile(np.array([1.0, 0.0, 0.0]), (m, 1))
    parallel = np.abs(np.sum(c * ref, axis=1)) > 0.99
    if np.any(parallel):
        ref[parallel] = np.array([0.0, 1.0, 0.0])

    u = np.cross(c, ref)
    u_norm = np.linalg.norm(u, axis=1, keepdims=True)
    u_norm[u_norm == 0.0] = 1.0
    u /= u_norm
    v = np.cross(c, u)

    j = np.arange(n_patch, dtype=np.float64)
    golden_angle = np.pi * (3.0 - np.sqrt(5.0))
    r = half_angle * np.sqrt((j + 0.5) / n_patch)
    phi = golden_angle * j

    cos_r = np.cos(r)
    weight_u = np.sin(r) * np.cos(phi)
    weight_v = np.sin(r) * np.sin(phi)

    patch = (
        c[:, None, :] * cos_r[None, :, None]
        + u[:, None, :] * weight_u[None, :, None]
        + v[:, None, :] * weight_v[None, :, None]
    )
    return patch.reshape(*batch_shape, n_patch, 3)


def _diverse_top_m_directions(amp, directions, n_seeds, min_angle_deg):
    """Greedily select ``n_seeds`` coarse-sweep directions per element,
    spread across the sphere rather than just the top-M by raw amplitude
    (which tends to cluster around a single decoy peak).

    Parameters
    ----------
    amp : np.ndarray, shape (n, num_directions)
        Coarse-sweep envelope amplitude at every direction, per element.
    directions : np.ndarray, shape (num_directions, 3)
        The coarse Fibonacci-sweep direction grid (shared across elements).
    n_seeds : int
        Number of seeds to select.
    min_angle_deg : float
        Minimum angular separation enforced between chosen seeds.

    Returns
    -------
    np.ndarray, shape (n, n_seeds)
        Column indices into ``directions``/``amp`` for the chosen seeds.
    """
    n = amp.shape[0]
    min_cos = np.cos(np.radians(min_angle_deg))
    remaining = amp.copy()
    chosen_idx = np.zeros((n, n_seeds), dtype=np.int64)

    for s in range(n_seeds):
        idx = np.argmax(remaining, axis=1)
        chosen_idx[:, s] = idx
        if s == n_seeds - 1:
            break
        cos_to_chosen = (directions @ directions[idx].T).T  # (n, num_directions)
        remaining = np.where(cos_to_chosen > min_cos, -np.inf, remaining)

    return chosen_idx


def _refine_local_directions(
    arrs_chunk,
    psi,
    directions,
    amp,
    P,
    num_directions,
):
    """Multi-seed local-patch refinement of a coarse Fibonacci-sweep result.

    Refines around ``_REFINE_N_SEEDS`` diverse coarse-sweep candidates per
    element (see :func:`_diverse_top_m_directions`), then keeps the best
    result across seeds and rounds. The seed axis is a vectorised batch
    dimension throughout, so this costs a bounded multiple of a
    single-seed refinement, not a per-seed Python loop.

    Returns
    -------
    best_md, best_P, best_dir : the refined per-element results (never
        worse than the coarse sweep's own per-element best).
    """
    n = amp.shape[0]
    n_seeds = min(_REFINE_N_SEEDS, directions.shape[0])

    top_idx = _diverse_top_m_directions(
        amp, directions, n_seeds, _REFINE_MIN_SEED_ANGLE_DEG
    )  # (n, S)

    best_dir = directions[top_idx]  # (n, S, 3)
    best_md = np.take_along_axis(amp, top_idx, axis=1)  # (n, S)
    best_P = np.take_along_axis(P, top_idx, axis=1)  # (n, S)

    half_angle = 2.0 / np.sqrt(num_directions)
    seed_rows = np.arange(n)[:, None, None]
    seed_cols = np.arange(n_seeds)[None, :, None]

    for _ in range(_REFINE_N_ROUNDS):
        patch = _local_patch_directions(best_dir, half_angle, _REFINE_PATCH_SIZE)
        proj = [np.einsum("nd,nspd->nsp", field, patch) for field in arrs_chunk]
        Pc, Qc = _pairwise_products(proj, psi)  # (n, S, patch)
        ampc = _envelope_from_PQ(Pc, Qc)  # (n, S, patch)

        idx = np.argmax(ampc, axis=2)  # (n, S)
        cand_md = np.take_along_axis(ampc, idx[:, :, None], axis=2)[:, :, 0]
        cand_P = np.take_along_axis(Pc, idx[:, :, None], axis=2)[:, :, 0]
        cand_dir = patch[seed_rows, seed_cols, idx[:, :, None], :][:, :, 0, :]

        improved = cand_md > best_md
        best_md = np.where(improved, cand_md, best_md)
        best_P = np.where(improved, cand_P, best_P)
        best_dir = np.where(improved[:, :, None], cand_dir, best_dir)

        half_angle *= _REFINE_SHRINK

    best_seed = np.argmax(best_md, axis=1)  # (n,)
    final_md = np.take_along_axis(best_md, best_seed[:, None], axis=1)[:, 0]
    final_P = np.take_along_axis(best_P, best_seed[:, None], axis=1)[:, 0]
    final_dir = best_dir[np.arange(n), best_seed]
    return final_md, final_P, final_dir


def _sweep_envelope_chunk(arrs_chunk, psi, directions):
    """Coarse-sweep envelope amplitude/carrier-power at every candidate
    direction, for one chunk of elements. Shared by the max-seeking sweep
    (:func:`_mti_modulation_depth_sweep`) and the direction-averaged
    envelope (:func:`_mti_modulation_depth_avg`) -- the mean over
    directions is a by-product of the same (P, Q) computation the max
    search already does, not a second sweep.

    Returns
    -------
    amp, P : np.ndarray, each shape (n_chunk, num_directions)
    """
    proj = [field @ directions.T for field in arrs_chunk]
    P, Q = _pairwise_products(proj, psi)
    return _envelope_from_PQ(P, Q), P


def _mti_modulation_depth_avg(arrs, psi, num_directions=192, chunk_size=16384):
    """Mean coarse-sweep envelope amplitude over sampled directions.

    Backs :func:`get_TI_avg`. Unlike :func:`_mti_modulation_depth_sweep`,
    there is no per-element argmax or local refinement -- refinement only
    sharpens a single best direction, which an average over directions
    does not need.
    """
    directions = _fibonacci_sphere(num_directions)
    n_vox = arrs[0].shape[0]
    avg_md = np.zeros(n_vox, dtype=np.float64)

    for start in range(0, n_vox, chunk_size):
        stop = min(start + chunk_size, n_vox)
        arrs_chunk = [field[start:stop] for field in arrs]
        amp, _ = _sweep_envelope_chunk(arrs_chunk, psi, directions)
        avg_md[start:stop] = np.mean(amp, axis=1)

    return avg_md


def _mti_modulation_depth_sweep(arrs, psi, num_directions, chunk_size, refine):
    """Chunked Fibonacci-sphere direction sweep -- returns best-direction
    md/carrier_power/best_direction per element. When ``refine`` is True,
    each chunk's coarse-sweep result is locally refined (see
    :func:`_refine_local_directions`); when False, this returns the raw
    coarse-sweep-only result."""
    directions = _fibonacci_sphere(num_directions)
    n_vox = arrs[0].shape[0]

    md = np.zeros(n_vox, dtype=np.float64)
    carrier_power = np.zeros(n_vox, dtype=np.float64)
    best_direction = np.zeros((n_vox, 3), dtype=np.float64)

    for start in range(0, n_vox, chunk_size):
        stop = min(start + chunk_size, n_vox)
        arrs_chunk = [field[start:stop] for field in arrs]
        amp, P = _sweep_envelope_chunk(arrs_chunk, psi, directions)

        if refine:
            chunk_md, chunk_P, chunk_dir = _refine_local_directions(
                arrs_chunk, psi, directions, amp, P, num_directions
            )
        else:
            idx = np.argmax(amp, axis=1)
            rows = np.arange(stop - start)
            chunk_md = amp[rows, idx]
            chunk_P = P[rows, idx]
            chunk_dir = directions[idx]

        md[start:stop] = chunk_md
        carrier_power[start:stop] = chunk_P
        best_direction[start:stop] = chunk_dir

    return {"md": md, "carrier_power": carrier_power, "best_direction": best_direction}


def _mti_modulation_depth_at_directions(arrs, psi, directions):
    """Evaluate the envelope at an explicit per-element direction (no search)."""
    directions = np.asarray(directions, dtype=np.float64)
    if directions.shape != arrs[0].shape:
        raise ValueError(
            "directions must have the same shape as each field array; got "
            f"{directions.shape}, expected {arrs[0].shape}"
        )
    norms = np.linalg.norm(directions, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit_dirs = directions / norms

    proj = [np.sum(field * unit_dirs, axis=1) for field in arrs]
    P, Q = _pairwise_products(proj, psi)
    md = _envelope_from_PQ(P, Q)

    return {"md": md, "carrier_power": P, "best_direction": unit_dirs}


def _fibonacci_sphere(num_dirs: int) -> np.ndarray:
    """Return approximately uniform unit vectors on the sphere.

    Ported from ``alba/ex-search-multipolar`` (see module docstring
    "Attribution").
    """
    if num_dirs < 2:
        return np.array([[0.0, 0.0, 1.0]], dtype=np.float64)
    i = np.arange(num_dirs, dtype=np.float64)
    phi = np.pi * (3.0 - np.sqrt(5.0))
    y = 1.0 - 2.0 * i / (num_dirs - 1)
    radius = np.sqrt(np.maximum(0.0, 1.0 - y * y))
    theta = phi * i
    x = np.cos(theta) * radius
    z = np.sin(theta) * radius
    return np.stack((x, y, z), axis=1)
