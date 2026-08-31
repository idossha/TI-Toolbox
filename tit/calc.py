#!/usr/bin/env simnibs_python
"""Temporal interference field calculation utilities.

Vectorised NumPy implementations of the TI/mTI modulation-amplitude
envelope from Grossman et al. (2017), extended to an arbitrary even
number of electrode pairs (mTI).

Public API
----------
get_TI_vectors
    Modulation-amplitude vectors for K >= 1 carriers (K=1 exact closed
    form; K>=2 direction search).
get_TI_avg
    Direction-averaged modulation depth for K >= 1 carriers.
get_TI_dir
    Modulation depth evaluated along a fixed per-element direction
    (e.g. the cortical surface normal); backs ``TI_normal`` for mTI.

Attribution
-----------
The K >= 2 envelope and the ``_fibonacci_sphere`` /
``_validate_field_list`` helpers originate from collaborator Larissa
Albantakis's branch ``alba/mTI_testing`` and are ported here with
attribution, not reimplemented.
"""

import os

import numpy as np


def _get_TI_vectors_k1(E1_org, E2_org):
    """Compute the TI modulation-amplitude vectors for two electric fields.

    Sign-agnostic closed form (Hirata et al. 2024), equivalent to the
    original Grossman et al. (2017) preprocess-then-branch formulation but
    needs no magnitude-ordering swap or acute-angle sign flip of the
    inputs: ``TI = 2*min(|E1|,|E2|)`` (as a vector, sign-corrected) when
    ``min(|E1|,|E2|) <= sqrt(|E1.E2|)``, else ``TI = 2 *`` that same
    sign-corrected vector's component perpendicular to ``h``, whichever of
    ``E1-E2``/``E1+E2`` has the smaller norm.

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
    Hirata, A. et al. (2024). Computers in Biology and Medicine, 178, 108697.
    """
    assert E1_org.shape == E2_org.shape, "E1 and E2 must have same shape"
    assert E1_org.shape[1] == 3, "Vectors must be 3D"

    E1 = E1_org
    E2 = E2_org

    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)
    dot = np.sum(E1 * E2, axis=1)

    min_norm = np.minimum(normE1, normE2)
    regime1_mask = min_norm <= np.sqrt(np.abs(dot))

    # The smaller-magnitude field, sign-corrected for an acute angle; ties
    # go to E2, matching the strict '>' swap convention of the original
    # preprocess-then-branch form.
    use_E1_as_small = normE1 < normE2
    Es_raw = np.where(use_E1_as_small[:, None], E1, E2)
    sign = np.where(dot < 0, -1.0, 1.0)
    Es = sign[:, None] * Es_raw

    TI_vectors = np.zeros_like(E1)
    TI_vectors[regime1_mask] = 2.0 * Es[regime1_mask]

    # Regime 2 (oblique): TI = 2 * (Es perpendicular to h), h = whichever
    # of (E1-E2), (E1+E2) has the smaller norm.
    regime2_mask = ~regime1_mask
    if np.any(regime2_mask):
        a2 = E1[regime2_mask]
        b2 = E2[regime2_mask]
        dot2 = dot[regime2_mask]
        h_minus = a2 - b2
        h_plus = a2 + b2
        # Decide from sign(dot) directly rather than comparing the two
        # norms: |E1-E2|^2 - |E1+E2|^2 == -4*dot, so the sign is exact,
        # while for near-orthogonal fields (dot tiny relative to |E1|,
        # |E2|) the two norms round to the same float64 and the
        # comparison loses the sign to cancellation.
        use_minus = dot2 >= 0
        h = np.where(use_minus[:, None], h_minus, h_plus)
        h_norm = np.linalg.norm(h, axis=1)
        h_norm_safe = np.where(h_norm == 0, 1.0, h_norm)
        e_h = h / h_norm_safe[:, None]

        Es_r2 = Es[regime2_mask]
        Es_parallel_component = np.sum(Es_r2 * e_h, axis=1)[:, None] * e_h
        Es_perp = Es_r2 - Es_parallel_component
        TI_vectors[regime2_mask] = 2.0 * Es_perp

    return TI_vectors


def get_TI_vectors(fields, psi=None):
    """Compute TI modulation-amplitude vectors for K >= 1 carriers.

    ``fields`` is ``[E_1a, E_1b, ..., E_Ka, E_Kb]``, 2K arrays of shape
    ``(N, 3)`` -- one per channel, paired positionally: each two
    consecutive fields are the two channels sharing one carrier. K=1
    (standard TI) is solved by an exact closed form (Grossman et al.
    2017; Hirata et al. 2024) with no direction search; K>=2 (mTI)
    returns ``best_direction * md`` from the verified
    :func:`_mti_modulation_depth` envelope.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Channel field vectors, consecutive fields sharing a carrier.
    psi : array-like, shape (K,), or None
        Per-carrier envelope phase offset (radians); ``None`` means
        phase-aligned carriers (``psi_k=0``), the standard case. Ignored
        at K=1 (phase-invariant there).

    Returns
    -------
    np.ndarray, shape (N, 3)
        Modulation-amplitude vectors [V/m]; norm is the modulation depth.

    Raises
    ------
    ValueError
        Invalid ``fields`` or ``psi``; see :func:`_validate_field_list`
        and :func:`_validate_psi`.

    References
    ----------
    Grossman, N. et al. (2017). Cell, 169(6), 1029-1041 (K=1 closed form).
    """
    arrs = _validate_field_list(fields)
    n_pairs = len(arrs) // 2
    _validate_psi(psi, n_pairs)

    if n_pairs == 1:
        return _get_TI_vectors_k1(arrs[0], arrs[1])

    result = _mti_modulation_depth(arrs, psi=psi)
    return result["best_direction"] * result["md"][:, None]


def get_TI_avg(fields, psi=None):
    """Direction-averaged modulation depth for K >= 1 electrode pairs.

    ``TI_max`` (:func:`get_TI_vectors`) maximizes the envelope over
    direction -- a best case for a neuron aligned with the optimal axis.
    ``TI_avg`` instead averages the same coarse Fibonacci-sphere sweep
    over all sampled directions, giving what a randomly-oriented neuron
    sees on average. Local refinement (accurate for a single best
    direction only) is skipped as irrelevant to an average.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Channel field vectors, consecutive fields sharing a carrier.
    psi : array-like, shape (K,), or None
        Per-carrier envelope phase offset (radians); see
        :func:`get_TI_vectors`.

    Returns
    -------
    np.ndarray, shape (N,)
        Modulation depth [V/m], averaged over sampled directions.
    """
    arrs = _validate_field_list(fields)
    n_pairs = len(arrs) // 2
    psi_arr = _validate_psi(psi, n_pairs)
    return _mti_modulation_depth_avg(arrs, psi_arr)


def get_TI_dir(fields, directions, psi=None):
    """Modulation depth along a fixed per-element direction, K >= 1.

    The multi-carrier analogue of SimNIBS's 2-field ``TI.get_dirTI``:
    instead of maximizing the envelope over direction
    (:func:`get_TI_vectors`), evaluate it at a given direction per
    element -- typically the cortical surface normal, which yields the
    ``TI_normal`` quantity. Exact (no direction search) for any K.

    Parameters
    ----------
    fields : list of np.ndarray, each shape (N, 3)
        Field vectors ordered ``[E_1a, E_1b, E_2a, E_2b, ...]``, one per
        channel; consecutive fields are the two channels of one carrier.
    directions : np.ndarray, shape (N, 3)
        Per-element direction to evaluate the envelope along. Need not be
        unit length; zero vectors yield 0.
    psi : array-like, shape (K,), or None
        Per-carrier envelope phase offset (radians); see
        :func:`get_TI_vectors`.

    Returns
    -------
    np.ndarray, shape (N,)
        Modulation depth [V/m] along ``directions``.
    """
    result = _mti_modulation_depth(fields, psi=psi, directions=directions)
    return result["md"]


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
    tmp = np.empty_like(P)  # reused scratch: same arithmetic, no temporaries
    for p in proj_fields:
        np.multiply(p, p, out=tmp)
        P += tmp
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
            np.multiply(proj_fields[2 * k], proj_fields[2 * k + 1], out=tmp)
            b_sum += tmp
        Q = np.abs(b_sum, out=b_sum)

    return P, Q


def _quadratic_forms(arrs, psi):
    """Per-element symmetric 3x3 matrices behind the (P, Q) envelope terms.

    For a unit direction ``n``, ``P = 0.5*sum_f (E_f . n)^2 = n^T M_P n`` and
    the coherent sum ``sum_k (E_ka . n)(E_kb . n) exp(i psi_k) = n^T M_Q n``
    with ``M_P = 0.5*sum_f E_f E_f^T`` and ``M_Q = sum_k exp(i psi_k) *
    sym(E_ka E_kb^T)``. Both are direction-independent, so a direction
    sweep is two small matmuls over their packed 6-vectors
    (:func:`_pack_symmetric`) instead of 2K projection arrays.

    Returns
    -------
    M_P : np.ndarray, shape (N, 3, 3), float64
    M_Q : np.ndarray, shape (N, 3, 3), float64 (``psi`` None/zero) or
        complex128 (a phasor-weighted sum).
    """
    n_pairs = len(arrs) // 2
    stacked = np.stack(arrs, axis=1)  # (N, 2K, 3)
    M_P = np.einsum("nfa,nfb->nab", stacked, stacked)
    M_P *= 0.5

    a = stacked[:, 0::2]  # (N, K, 3)
    b = stacked[:, 1::2]
    use_phase = psi is not None and np.any(psi != 0.0)
    if use_phase:
        phasor = np.exp(1j * np.asarray(psi, dtype=np.float64))
        M_Q = np.einsum("k,nka,nkb->nab", phasor, a, b)
    else:
        M_Q = np.einsum("nka,nkb->nab", a, b)
    M_Q = 0.5 * (M_Q + M_Q.transpose(0, 2, 1))
    return M_P, M_Q


def _pack_symmetric(M):
    """Pack symmetric ``(..., 3, 3)`` matrices as ``(..., 6)`` so that
    ``n^T M n == _pack_symmetric(M) @ _direction_quadratics(n)``."""
    return np.stack(
        (M[..., 0, 0], M[..., 1, 1], M[..., 2, 2], M[..., 0, 1], M[..., 0, 2], M[..., 1, 2]),
        axis=-1,
    )


def _pack_frame_form(basis, M):
    """``_pack_symmetric(basis @ M @ basis^T)`` for frames ``basis``
    ``(..., 3, 3)`` and symmetric ``M`` broadcastable to it, as explicit
    broadcast arithmetic: entry ``(i, j)`` is ``(basis_i M) . basis_j``.
    Batched 3x3 matmuls are per-batch loops in NumPy and lose to this.
    """
    T = [
        [
            basis[..., i, 0] * M[..., 0, c]
            + basis[..., i, 1] * M[..., 1, c]
            + basis[..., i, 2] * M[..., 2, c]
            for c in range(3)
        ]
        for i in range(3)
    ]
    out = np.empty(np.broadcast_shapes(basis.shape[:-2], M.shape[:-2]) + (6,), dtype=T[0][0].dtype)
    for k, (i, j) in enumerate(((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))):
        out[..., k] = (
            T[i][0] * basis[..., j, 0] + T[i][1] * basis[..., j, 1] + T[i][2] * basis[..., j, 2]
        )
    return out


def _direction_quadratics(directions):
    """``(..., 6)`` quadratic monomials ``[x^2, y^2, z^2, 2xy, 2xz, 2yz]`` of
    ``(..., 3)`` directions; pairs with :func:`_pack_symmetric`."""
    x, y, z = directions[..., 0], directions[..., 1], directions[..., 2]
    return np.stack((x * x, y * y, z * z, 2.0 * x * y, 2.0 * x * z, 2.0 * y * z), axis=-1)


def _envelope_at_quadratics(P6, Q6, D6):
    """(amp, P) at every direction in ``D6`` (``(D, 6)``) for packed forms
    ``P6``/``Q6`` (``(..., 6)``); both outputs are ``(..., D)``."""
    lead = P6.shape[:-1]
    n_dirs = D6.shape[0]
    # One 2-D GEMM over the flattened leading axes: NumPy would otherwise
    # dispatch a stack of small matmuls, one per leading index.
    P = (P6.reshape(-1, 6) @ D6.T).reshape(lead + (n_dirs,))
    Q = (Q6.reshape(-1, 6) @ D6.T).reshape(lead + (n_dirs,))
    Q = np.abs(Q, out=Q) if np.isrealobj(Q) else np.abs(Q)
    return _envelope_from_PQ(P, Q), P


def _envelope_from_PQ(P, Q):
    """MD = sqrt(2) * (sqrt(P+Q) - sqrt(P-Q)), clamped against negative
    round-off inside the square roots."""
    smin = P - Q
    np.maximum(smin, 0.0, out=smin)
    smin *= 2.0
    np.sqrt(smin, out=smin)
    smax = P + Q
    np.maximum(smax, 0.0, out=smax)
    smax *= 2.0
    np.sqrt(smax, out=smax)
    smax -= smin
    return smax


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


def _local_patch_basis(centers):
    """Orthonormal frame ``[c, u, v]`` around each unit vector in ``centers``
    (arbitrary leading batch shape ``(..., 3)``): the center itself plus a
    deterministic tangent basis ``(u, v)`` perpendicular to it. Output has
    shape ``(..., 3, 3)`` with the three frame vectors as rows.
    """
    batch_shape = centers.shape[:-1]
    c = np.ascontiguousarray(centers.reshape(-1, 3))
    m = c.shape[0]
    cx, cy, cz = c[:, 0], c[:, 1], c[:, 2]

    # Reference axis: x, or y where the center is (nearly) parallel to x.
    ref = np.zeros((m, 3), dtype=np.float64)
    ref[:, 0] = 1.0
    parallel = np.abs(cx) > 0.99
    if np.any(parallel):
        ref[parallel] = np.array([0.0, 1.0, 0.0])
    rx, ry, rz = ref[:, 0], ref[:, 1], ref[:, 2]

    basis = np.empty((m, 3, 3), dtype=np.float64)
    basis[:, 0, :] = c
    u = basis[:, 1, :]
    v = basis[:, 2, :]
    # Component-wise cross products (the multiply/subtract sequence of
    # ``np.cross``, without its temporaries): u = c x ref, v = c x u.
    u[:, 0] = cy * rz - cz * ry
    u[:, 1] = cz * rx - cx * rz
    u[:, 2] = cx * ry - cy * rx
    u_norm = np.sqrt(u[:, 0] * u[:, 0] + u[:, 1] * u[:, 1] + u[:, 2] * u[:, 2])
    u_norm[u_norm == 0.0] = 1.0
    u /= u_norm[:, None]
    ux, uy, uz = u[:, 0], u[:, 1], u[:, 2]
    v[:, 0] = cy * uz - cz * uy
    v[:, 1] = cz * ux - cx * uz
    v[:, 2] = cx * uy - cy * ux
    return basis.reshape(*batch_shape, 3, 3)


def _patch_weights(half_angle, n_patch):
    """Frame weights ``(n_patch, 3)`` of a Fibonacci-spiral spherical cap of
    angular radius ``half_angle`` (radians): direction ``p`` of the patch
    around a center with frame ``[c, u, v]`` is ``w[p] @ [c, u, v]``.
    """
    j = np.arange(n_patch, dtype=np.float64)
    golden_angle = np.pi * (3.0 - np.sqrt(5.0))
    r = half_angle * np.sqrt((j + 0.5) / n_patch)
    phi = golden_angle * j
    return np.stack((np.cos(r), np.sin(r) * np.cos(phi), np.sin(r) * np.sin(phi)), axis=1)


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

    # Pairwise cosines between grid directions are candidate-independent:
    # look them up per chosen seed instead of re-multiplying per element.
    grid_cos = directions @ directions.T  # (num_directions, num_directions)
    too_close = grid_cos > min_cos

    for s in range(n_seeds):
        idx = np.argmax(remaining, axis=1)
        chosen_idx[:, s] = idx
        if s == n_seeds - 1:
            break
        np.copyto(remaining, -np.inf, where=too_close[idx])

    return chosen_idx


def _refine_local_directions(M_P, M_Q, directions, amp, P, num_directions):
    """Multi-seed local-patch refinement of a coarse Fibonacci-sweep result.

    Refines around ``_REFINE_N_SEEDS`` diverse coarse-sweep candidates per
    element (see :func:`_diverse_top_m_directions`), then keeps the best
    result across seeds and rounds. The seed axis is a vectorised batch
    dimension throughout, so this costs a bounded multiple of a
    single-seed refinement, not a per-seed Python loop.

    Each round expresses the envelope forms in the local frame of every
    seed (``B M B^T``, :func:`_local_patch_basis`) and evaluates the patch
    through :func:`_patch_weights` -- the patch directions are never
    materialised, only the winning one is reconstructed.

    Parameters
    ----------
    M_P, M_Q : np.ndarray, shape (n, 3, 3)
        Per-element envelope forms from :func:`_quadratic_forms`.
    directions : np.ndarray, shape (num_directions, 3)
        Coarse sweep grid.
    amp, P : np.ndarray, shape (n, num_directions)
        Coarse sweep envelope and carrier power at every grid direction.

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
    seed_rows = np.arange(n)[:, None]
    seed_cols = np.arange(n_seeds)[None, :]
    M_P = M_P[:, None]  # (n, 1, 3, 3), broadcast over seeds
    M_Q = M_Q[:, None]

    for _ in range(_REFINE_N_ROUNDS):
        basis = _local_patch_basis(best_dir)  # (n, S, 3, 3)
        weights = _patch_weights(half_angle, _REFINE_PATCH_SIZE)  # (patch, 3)
        W6 = _direction_quadratics(weights)  # (patch, 6)
        P6 = _pack_frame_form(basis, M_P)  # (n, S, 6)
        Q6 = _pack_frame_form(basis, M_Q)
        ampc, Pc = _envelope_at_quadratics(P6, Q6, W6)  # (n, S, patch)

        idx = np.argmax(ampc, axis=2)  # (n, S)
        cand_md = ampc[seed_rows, seed_cols, idx]
        cand_P = Pc[seed_rows, seed_cols, idx]
        cand_dir = np.einsum("nsk,nskd->nsd", weights[idx], basis)

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
    M_P, M_Q : np.ndarray, each shape (n_chunk, 3, 3)
        The per-element forms (:func:`_quadratic_forms`) the sweep was
        evaluated from, for reuse by the local refinement.
    """
    M_P, M_Q = _quadratic_forms(arrs_chunk, psi)
    amp, P = _envelope_at_quadratics(
        _pack_symmetric(M_P), _pack_symmetric(M_Q), _direction_quadratics(directions)
    )
    return amp, P, M_P, M_Q


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
        amp, _, _, _ = _sweep_envelope_chunk(arrs_chunk, psi, directions)
        avg_md[start:stop] = np.mean(amp, axis=1)

    return avg_md


def _fused_sweep_kernel():
    """The numba sweep+refine kernel (:mod:`tit._mti_kernel`), or ``None``.

    ``None`` -- meaning "use the chunked NumPy path" -- when numba is not
    importable or the environment variable ``TIT_MTI_KERNEL`` is set to
    ``"numpy"`` (any other value, or unset, prefers numba). The kernel
    reproduces the NumPy algorithm step for step, so the two paths agree
    to round-off; the override exists for A/B testing and as an escape
    hatch.
    """
    if os.environ.get("TIT_MTI_KERNEL", "").strip().lower() == "numpy":
        return None
    try:
        from tit import _mti_kernel
    except Exception:  # noqa: BLE001 - any failure means "no kernel"
        return None
    if not _mti_kernel.HAVE_NUMBA:
        return None
    return _mti_kernel.sweep_refine


def _mti_modulation_depth_sweep(arrs, psi, num_directions, chunk_size, refine):
    """Chunked Fibonacci-sphere direction sweep -- returns best-direction
    md/carrier_power/best_direction per element. When ``refine`` is True,
    each chunk's coarse-sweep result is locally refined (see
    :func:`_refine_local_directions`); when False, this returns the raw
    coarse-sweep-only result."""
    directions = _fibonacci_sphere(num_directions)
    n_vox = arrs[0].shape[0]

    kernel = _fused_sweep_kernel()
    if kernel is not None and n_vox > 0:
        n_seeds = min(_REFINE_N_SEEDS, directions.shape[0])
        min_cos = np.cos(np.radians(_REFINE_MIN_SEED_ANGLE_DEG))
        too_close = (directions @ directions.T) > min_cos
        half_angle = 2.0 / np.sqrt(num_directions)
        patch_weights = np.stack(
            [
                _patch_weights(half_angle * _REFINE_SHRINK**r, _REFINE_PATCH_SIZE)
                for r in range(_REFINE_N_ROUNDS)
            ]
        )
        md, carrier_power, best_direction = kernel(
            arrs, psi, directions, too_close, patch_weights, n_seeds, refine
        )
        return {"md": md, "carrier_power": carrier_power, "best_direction": best_direction}

    md = np.zeros(n_vox, dtype=np.float64)
    carrier_power = np.zeros(n_vox, dtype=np.float64)
    best_direction = np.zeros((n_vox, 3), dtype=np.float64)

    for start in range(0, n_vox, chunk_size):
        stop = min(start + chunk_size, n_vox)
        arrs_chunk = [field[start:stop] for field in arrs]
        amp, P, M_P, M_Q = _sweep_envelope_chunk(arrs_chunk, psi, directions)

        if refine:
            chunk_md, chunk_P, chunk_dir = _refine_local_directions(
                M_P, M_Q, directions, amp, P, num_directions
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
