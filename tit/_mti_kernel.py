"""Fused numba kernel for the K>=2 mTI envelope direction search.

This is a per-element re-implementation of the NumPy pipeline in
:mod:`tit.calc` -- ``_quadratic_forms`` -> coarse Fibonacci sweep ->
``_diverse_top_m_directions`` -> ``_refine_local_directions`` -- that
walks every element once and keeps all intermediates (the 192-direction
sweep, the seed table, the patch evaluations) in small per-element
scratch instead of ``(n, 192)`` / ``(n, 6, 16)`` temporaries. The
NumPy path is memory-bound on those temporaries; this kernel is
compute-bound and parallel over elements (``prange``).

Every step mirrors the NumPy code's arithmetic and tie-breaking (first
maximum wins in every ``argmax``, the grid-cosine seed exclusion, the
patch geometry and the shrinking round schedule), so results agree with
the NumPy path to floating-point round-off. :func:`tit.calc` selects it
automatically when numba is importable; see :func:`sweep_refine`.

The module imports cleanly without numba (``HAVE_NUMBA`` is False and
:func:`sweep_refine` raises), so the caller can fall back.
"""

import numpy as np

try:  # pragma: no cover - exercised only where numba is installed
    from numba import njit, prange

    HAVE_NUMBA = True
except Exception:  # noqa: BLE001 - any import failure means "no kernel"
    HAVE_NUMBA = False

    def njit(*args, **kwargs):  # type: ignore[misc]
        def deco(fn):
            return fn

        return deco

    prange = range  # type: ignore[assignment]


@njit(cache=True, inline="always")
def _envelope(P, Q):
    # Same operation order as tit.calc._envelope_from_PQ.
    smin = np.sqrt(max(P - Q, 0.0) * 2.0)
    smax = np.sqrt(max(P + Q, 0.0) * 2.0)
    return smax - smin


@njit(cache=True, inline="always")
def _frame_form(basis, M, out):
    # tit.calc._pack_frame_form: out[k] = (basis_i M) . basis_j for the
    # packed (i, j) sequence (0,0),(1,1),(2,2),(0,1),(0,2),(1,2).
    for k in range(6):
        if k < 3:
            i = k
            j = k
        elif k == 3:
            i = 0
            j = 1
        elif k == 4:
            i = 0
            j = 2
        else:
            i = 1
            j = 2
        t0 = basis[i, 0] * M[0, 0] + basis[i, 1] * M[1, 0] + basis[i, 2] * M[2, 0]
        t1 = basis[i, 0] * M[0, 1] + basis[i, 1] * M[1, 1] + basis[i, 2] * M[2, 1]
        t2 = basis[i, 0] * M[0, 2] + basis[i, 1] * M[1, 2] + basis[i, 2] * M[2, 2]
        out[k] = t0 * basis[j, 0] + t1 * basis[j, 1] + t2 * basis[j, 2]


@njit(cache=True, inline="always")
def _patch_basis(c, basis):
    # tit.calc._local_patch_basis for a single center: rows [c, u, v].
    cx = c[0]
    cy = c[1]
    cz = c[2]
    if abs(cx) > 0.99:
        rx = 0.0
        ry = 1.0
        rz = 0.0
    else:
        rx = 1.0
        ry = 0.0
        rz = 0.0
    basis[0, 0] = cx
    basis[0, 1] = cy
    basis[0, 2] = cz
    ux = cy * rz - cz * ry
    uy = cz * rx - cx * rz
    uz = cx * ry - cy * rx
    un = np.sqrt(ux * ux + uy * uy + uz * uz)
    if un == 0.0:
        un = 1.0
    ux = ux / un
    uy = uy / un
    uz = uz / un
    basis[1, 0] = ux
    basis[1, 1] = uy
    basis[1, 2] = uz
    basis[2, 0] = cy * uz - cz * uy
    basis[2, 1] = cz * ux - cx * uz
    basis[2, 2] = cx * uy - cy * ux


@njit(cache=True, inline="always")
def _dot6(v, T, row):
    return (
        v[0] * T[row, 0]
        + v[1] * T[row, 1]
        + v[2] * T[row, 2]
        + v[3] * T[row, 3]
        + v[4] * T[row, 4]
        + v[5] * T[row, 5]
    )


@njit(cache=True, inline="always")
def _argmax_first(x, n):
    best = 0
    bv = x[0]
    for d in range(1, n):
        if x[d] > bv:
            bv = x[d]
            best = d
    return best


@njit(cache=True, inline="always")
def _pack6(M, out):
    out[0] = M[0, 0]
    out[1] = M[1, 1]
    out[2] = M[2, 2]
    out[3] = M[0, 1]
    out[4] = M[0, 2]
    out[5] = M[1, 2]


@njit(cache=True, inline="always")
def _element_forms(fields, e, cos_psi, sin_psi, use_phase, MP, MQr, MQi):
    # tit.calc._quadratic_forms for one element:
    #   M_P = 0.5 sum_f E_f E_f^T,  M_Q = sym(sum_k phasor_k E_ka E_kb^T)
    # ``fields`` is a homogeneous tuple of (N, 3) arrays (no stacked copy).
    n_fields = len(fields)
    n_pairs = n_fields // 2
    for a in range(3):
        for b in range(3):
            MP[a, b] = 0.0
            MQr[a, b] = 0.0
            MQi[a, b] = 0.0
    for f in range(n_fields):
        Ef = fields[f]
        for a in range(3):
            va = Ef[e, a]
            for b in range(3):
                MP[a, b] += va * Ef[e, b]
    for a in range(3):
        for b in range(3):
            MP[a, b] *= 0.5
    for k in range(n_pairs):
        Ea = fields[2 * k]
        Eb = fields[2 * k + 1]
        for a in range(3):
            xa = Ea[e, a]
            for b in range(3):
                prod = xa * Eb[e, b]
                if use_phase:
                    MQr[a, b] += cos_psi[k] * prod
                    MQi[a, b] += sin_psi[k] * prod
                else:
                    MQr[a, b] += prod
    for a in range(3):
        for b in range(a + 1, 3):
            s = 0.5 * (MQr[a, b] + MQr[b, a])
            MQr[a, b] = s
            MQr[b, a] = s
            s = 0.5 * (MQi[a, b] + MQi[b, a])
            MQi[a, b] = s
            MQi[b, a] = s


_BLOCK = 256


@njit(parallel=True, cache=True)
def _sweep_refine_kernel(
    fields,
    cos_psi,
    sin_psi,
    use_phase,
    directions,
    D6,
    too_close,
    W,
    W6,
    n_seeds,
    refine,
    out_md,
    out_P,
    out_dir,
):
    n = fields[0].shape[0]
    n_dirs = directions.shape[0]
    n_rounds = W.shape[0]
    n_patch = W.shape[1]
    n_blocks = (n + _BLOCK - 1) // _BLOCK

    for blk in prange(n_blocks):
        # Per-block scratch (no per-element heap traffic).
        MP = np.empty((3, 3))
        MQr = np.empty((3, 3))
        MQi = np.empty((3, 3))
        P6 = np.empty(6)
        Qr6 = np.empty(6)
        Qi6 = np.empty(6)
        P6f = np.empty(6)
        Qr6f = np.empty(6)
        Qi6f = np.empty(6)
        amp = np.empty(n_dirs)
        Pd = np.empty(n_dirs)
        Qd = np.empty(n_dirs)
        remaining = np.empty(n_dirs)
        seed_idx = np.empty(n_seeds, dtype=np.int64)
        best_md = np.empty(n_seeds)
        best_P = np.empty(n_seeds)
        best_dir = np.empty((n_seeds, 3))
        basis = np.empty((3, 3))
        pamp = np.empty(n_patch)
        pP = np.empty(n_patch)

        e0 = blk * _BLOCK
        e1 = min(n, e0 + _BLOCK)
        for e in range(e0, e1):
            _element_forms(fields, e, cos_psi, sin_psi, use_phase, MP, MQr, MQi)
            _pack6(MP, P6)
            _pack6(MQr, Qr6)
            _pack6(MQi, Qi6)

            # --- coarse sweep (tit.calc._envelope_at_quadratics)
            for d in range(n_dirs):
                Pd[d] = _dot6(P6, D6, d)
                Qd[d] = _dot6(Qr6, D6, d)
            if use_phase:
                for d in range(n_dirs):
                    Qd[d] = abs(complex(Qd[d], _dot6(Qi6, D6, d)))
            else:
                for d in range(n_dirs):
                    Qd[d] = abs(Qd[d])
            for d in range(n_dirs):
                amp[d] = _envelope(Pd[d], Qd[d])

            if not refine:
                best = _argmax_first(amp, n_dirs)
                out_md[e] = amp[best]
                out_P[e] = Pd[best]
                out_dir[e, 0] = directions[best, 0]
                out_dir[e, 1] = directions[best, 1]
                out_dir[e, 2] = directions[best, 2]
                continue

            # --- seeds (tit.calc._diverse_top_m_directions)
            for d in range(n_dirs):
                remaining[d] = amp[d]
            for s in range(n_seeds):
                best = _argmax_first(remaining, n_dirs)
                seed_idx[s] = best
                if s == n_seeds - 1:
                    break
                for d in range(n_dirs):
                    if too_close[best, d]:
                        remaining[d] = -np.inf

            for s in range(n_seeds):
                idx = seed_idx[s]
                best_md[s] = amp[idx]
                best_P[s] = Pd[idx]
                best_dir[s, 0] = directions[idx, 0]
                best_dir[s, 1] = directions[idx, 1]
                best_dir[s, 2] = directions[idx, 2]

            # --- local refinement (tit.calc._refine_local_directions)
            for r in range(n_rounds):
                for s in range(n_seeds):
                    _patch_basis(best_dir[s], basis)
                    _frame_form(basis, MP, P6f)
                    _frame_form(basis, MQr, Qr6f)
                    if use_phase:
                        _frame_form(basis, MQi, Qi6f)
                        for p in range(n_patch):
                            pP[p] = _dot6(P6f, W6[r], p)
                            q = abs(complex(_dot6(Qr6f, W6[r], p), _dot6(Qi6f, W6[r], p)))
                            pamp[p] = _envelope(pP[p], q)
                    else:
                        for p in range(n_patch):
                            pP[p] = _dot6(P6f, W6[r], p)
                            q = abs(_dot6(Qr6f, W6[r], p))
                            pamp[p] = _envelope(pP[p], q)
                    cbest = _argmax_first(pamp, n_patch)
                    if pamp[cbest] > best_md[s]:
                        best_md[s] = pamp[cbest]
                        best_P[s] = pP[cbest]
                        w0 = W[r, cbest, 0]
                        w1 = W[r, cbest, 1]
                        w2 = W[r, cbest, 2]
                        for d in range(3):
                            best_dir[s, d] = (
                                w0 * basis[0, d] + w1 * basis[1, d] + w2 * basis[2, d]
                            )

            bs = _argmax_first(best_md, n_seeds)
            out_md[e] = best_md[bs]
            out_P[e] = best_P[bs]
            out_dir[e, 0] = best_dir[bs, 0]
            out_dir[e, 1] = best_dir[bs, 1]
            out_dir[e, 2] = best_dir[bs, 2]


def sweep_refine(arrs, psi, directions, too_close, patch_weights, n_seeds, refine):
    """Run the fused sweep(+refine) kernel.

    Parameters
    ----------
    arrs : list of np.ndarray, each (N, 3) float64
        Validated field list ``[E_1a, E_1b, ...]`` (2K arrays).
    psi : np.ndarray (K,) or None
        Per-pair envelope phase; ``None``/all-zero selects the real path.
    directions : np.ndarray (D, 3)
        Coarse sweep grid (:func:`tit.calc._fibonacci_sphere`).
    too_close : np.ndarray (D, D) bool
        Seed-exclusion table ``directions @ directions.T > cos(min_angle)``.
    patch_weights : np.ndarray (R, patch, 3)
        Frame weights for every refinement round (already shrunk per round).
    n_seeds : int
    refine : bool

    Returns
    -------
    md, carrier_power, best_direction
    """
    if not HAVE_NUMBA:
        raise RuntimeError("numba is not available")
    from tit.calc import _direction_quadratics

    # A homogeneous tuple of C-contiguous (N, 3) float64 arrays: numba
    # indexes it at runtime, so no (N, 2K, 3) stacked copy is needed.
    fields = tuple(np.ascontiguousarray(a, dtype=np.float64) for a in arrs)
    n = fields[0].shape[0]
    n_pairs = len(fields) // 2
    use_phase = bool(psi is not None and np.any(np.asarray(psi) != 0.0))
    if use_phase:
        psi_arr = np.asarray(psi, dtype=np.float64)
        cos_psi = np.cos(psi_arr)
        sin_psi = np.sin(psi_arr)
    else:
        cos_psi = np.ones(n_pairs)
        sin_psi = np.zeros(n_pairs)

    directions = np.ascontiguousarray(directions, dtype=np.float64)
    D6 = np.ascontiguousarray(_direction_quadratics(directions))
    W = np.ascontiguousarray(patch_weights, dtype=np.float64)
    W6 = np.ascontiguousarray(_direction_quadratics(W))
    too_close = np.ascontiguousarray(too_close, dtype=np.bool_)

    md = np.empty(n)
    P = np.empty(n)
    best_dir = np.empty((n, 3))
    _sweep_refine_kernel(
        fields,
        cos_psi,
        sin_psi,
        use_phase,
        directions,
        D6,
        too_close,
        W,
        W6,
        int(n_seeds),
        bool(refine),
        md,
        P,
        best_dir,
    )
    return md, P, best_dir
