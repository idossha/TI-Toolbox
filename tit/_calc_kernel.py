"""numba kernel for the K>=2 sphere maximum of the TI envelope (:func:`tit.calc.envelope_max`).

The same algorithm as the NumPy reference ``tit.calc._max_sphere``, one element at a time and
parallel over elements (``prange``): eigen-branch tracking over the theta grid, Illinois regula
falsi on every bracketed sign change of ``g``, the safeguard candidates and the Newton polish,
with the same first-maximum-wins tie-breaking.  The deliberate differences:

* the 3x3 symmetric eigensolver is cyclic Jacobi, warm-started from the previous grid point's
  (or root iterate's) eigenvectors, instead of LAPACK -- LAPACK's per-call overhead on a 3x3
  matrix is most of the NumPy path's cost.  Eigenvectors agree to round-off except where
  eigenvalues coincide;
* the Newton polish stops once no step-halving raises the envelope: every later iteration would
  repeat that one from the same point, so the result is the same;
* sums run in a different order.

The two paths agree to round-off in the maximum (``tests/numerical/test_calc_kernel.py``:
1e-12 relative bound, ~2e-14 measured).

Importing this module raises ImportError when numba is absent; ``tit.calc`` then uses NumPy.
"""

import numpy as np

try:
    from numba import njit, prange
except ImportError as exc:  # host without numba: tit.calc falls back to NumPy
    raise ImportError("tit._calc_kernel needs numba") from exc

_SQRT2 = np.sqrt(2.0)
# itertools.permutations(range(3)), the order tit.calc._PERMS scores them in.
_PERMS = ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
_OFF = ((0, 1), (0, 2), (1, 2))


@njit(cache=True, error_model="numpy")
def _qf(A, x0, x1, x2, y0, y1, y2):
    """``x^T A y`` for symmetric 3x3 ``A``."""
    return (
        x0 * (A[0, 0] * y0 + A[0, 1] * y1 + A[0, 2] * y2)
        + x1 * (A[1, 0] * y0 + A[1, 1] * y1 + A[1, 2] * y2)
        + x2 * (A[2, 0] * y0 + A[2, 1] * y1 + A[2, 2] * y2)
    )


@njit(cache=True, error_model="numpy")
def _eigh(A, V, warm):
    """Eigenvectors of symmetric 3x3 ``A`` into the columns of ``V``, eigenvalues ascending.

    Cyclic Jacobi; ``A`` is overwritten (its diagonal ends up holding the eigenvalues).
    ``warm``: start from the orthonormal basis already in ``V`` (a nearby matrix's
    eigenvectors) instead of the identity, which leaves fewer rotations to do.
    """
    if warm:
        t00 = _qf(A, V[0, 0], V[1, 0], V[2, 0], V[0, 0], V[1, 0], V[2, 0])
        t11 = _qf(A, V[0, 1], V[1, 1], V[2, 1], V[0, 1], V[1, 1], V[2, 1])
        t22 = _qf(A, V[0, 2], V[1, 2], V[2, 2], V[0, 2], V[1, 2], V[2, 2])
        t01 = _qf(A, V[0, 0], V[1, 0], V[2, 0], V[0, 1], V[1, 1], V[2, 1])
        t02 = _qf(A, V[0, 0], V[1, 0], V[2, 0], V[0, 2], V[1, 2], V[2, 2])
        t12 = _qf(A, V[0, 1], V[1, 1], V[2, 1], V[0, 2], V[1, 2], V[2, 2])
        A[0, 0], A[1, 1], A[2, 2] = t00, t11, t22
        A[0, 1] = A[1, 0] = t01
        A[0, 2] = A[2, 0] = t02
        A[1, 2] = A[2, 1] = t12
    else:
        for i in range(3):
            for j in range(3):
                V[i, j] = 1.0 if i == j else 0.0
    # Off-diagonals below 1e-16 |A| move an eigenvector by under 1e-16 |A| / gap, LAPACK's
    # own accuracy (eps |A| / gap); quadratic convergence gets there in ~3 sweeps.
    tol = 0.0
    for i in range(3):
        for j in range(3):
            tol += A[i, j] * A[i, j]
    tol = 1e-16 * np.sqrt(tol)
    for _ in range(50):
        if abs(A[0, 1]) <= tol and abs(A[0, 2]) <= tol and abs(A[1, 2]) <= tol:
            break
        for p, q in _OFF:
            apq = A[p, q]
            if abs(apq) <= tol:
                continue
            theta = (A[q, q] - A[p, p]) / (2.0 * apq)
            if abs(theta) > 1e150:
                t = 0.5 / theta
            else:
                t = 1.0 / (abs(theta) + np.sqrt(theta * theta + 1.0))
                if theta < 0.0:
                    t = -t
            c = 1.0 / np.sqrt(t * t + 1.0)
            s = t * c
            A[p, p] -= t * apq
            A[q, q] += t * apq
            A[p, q] = A[q, p] = 0.0
            r = 3 - p - q
            arp, arq = A[r, p], A[r, q]
            A[r, p] = A[p, r] = c * arp - s * arq
            A[r, q] = A[q, r] = s * arp + c * arq
            for i in range(3):
                vp, vq = V[i, p], V[i, q]
                V[i, p] = c * vp - s * vq
                V[i, q] = s * vp + c * vq
    for i in range(1, 3):  # stable insertion sort of the columns by eigenvalue
        j = i
        while j > 0 and A[j - 1, j - 1] > A[j, j]:
            A[j - 1, j - 1], A[j, j] = A[j, j], A[j - 1, j - 1]
            for r in range(3):
                V[r, j - 1], V[r, j] = V[r, j], V[r, j - 1]
            j -= 1


@njit(cache=True, error_model="numpy")
def _uvwf(S, D, n0, n1, n2):
    """``u, v`` and ``E_AM`` at ``n`` from the projections (``tit.calc._uvw``/``_env_uvw``)."""
    u = v = w = 0.0
    for k in range(S.shape[0]):
        s = S[k, 0] * n0 + S[k, 1] * n1 + S[k, 2] * n2
        d = D[k, 0] * n0 + D[k, 1] * n1 + D[k, 2] * n2
        u += s * s
        v += d * d
        w += (s + d) * (s - d)
    u, v, w = 0.5 * u, 0.5 * v, 0.5 * w
    den = np.sqrt(max(u, 0.0)) + np.sqrt(max(v, 0.0))
    f = _SQRT2 * abs(w) / den if den > 0.0 else 0.0
    return u, v, f


@njit(cache=True, error_model="numpy")
def _newton(S, D, Cp, Cm, n, iters):
    """``tit.calc._newton_ascent`` for one seed ``n`` (updated in place); returns ``f``.

    The gradient and Hessian are formed directly in the tangent frame ``(e1, e2)``
    (``T grad``, ``T hess T^T``) -- the same quantities, summed in another order.
    """
    n0, n1, n2 = n[0], n[1], n[2]
    u, v, f = _uvwf(S, D, n0, n1, n2)
    for _ in range(iters):
        up = u >= v
        A, B = (Cp, Cm) if up else (Cm, Cp)
        ua, vb = (u, v) if up else (v, u)
        ra, rb = np.sqrt(ua), np.sqrt(vb)
        # tit.calc._frame
        if abs(n0) > 0.9:
            a0, a1, a2 = -n2, 0.0, n0  # n x (0, 1, 0)
        else:
            a0, a1, a2 = 0.0, n2, -n1  # n x (1, 0, 0)
        nrm = np.sqrt(a0 * a0 + a1 * a1 + a2 * a2)
        nrm = nrm if nrm > 0.0 else 1.0
        a0, a1, a2 = a0 / nrm, a1 / nrm, a2 / nrm
        b0, b1, b2 = n1 * a2 - n2 * a1, n2 * a0 - n0 * a2, n0 * a1 - n1 * a0
        # projections of A n, B n on (e1, e2, n)
        pa1, pa2 = _qf(A, a0, a1, a2, n0, n1, n2), _qf(A, b0, b1, b2, n0, n1, n2)
        pb1, pb2 = _qf(B, a0, a1, a2, n0, n1, n2), _qf(B, b0, b1, b2, n0, n1, n2)
        pan, pbn = _qf(A, n0, n1, n2, n0, n1, n2), _qf(B, n0, n1, n2, n0, n1, n2)
        g0 = _SQRT2 * (pa1 / ra - pb1 / rb)
        g1 = _SQRT2 * (pa2 / ra - pb2 / rb)
        gn = _SQRT2 * (pan / ra - pbn / rb)
        ka, kb = ua * ra, vb * rb
        h00 = _SQRT2 * (
            _qf(A, a0, a1, a2, a0, a1, a2) / ra
            - _qf(B, a0, a1, a2, a0, a1, a2) / rb
            - pa1 * pa1 / ka
            + pb1 * pb1 / kb
        )
        h01 = _SQRT2 * (
            _qf(A, a0, a1, a2, b0, b1, b2) / ra
            - _qf(B, a0, a1, a2, b0, b1, b2) / rb
            - pa1 * pa2 / ka
            + pb1 * pb2 / kb
        )
        h11 = _SQRT2 * (
            _qf(A, b0, b1, b2, b0, b1, b2) / ra
            - _qf(B, b0, b1, b2, b0, b1, b2) / rb
            - pa2 * pa2 / ka
            + pb2 * pb2 / kb
        )
        h00 -= gn
        h11 -= gn
        det = h00 * h11 - h01 * h01
        if h00 < 0.0 and det > 0.0:
            s0 = -(h11 * g0 - h01 * g1) / det
            s1 = -(h00 * g1 - h01 * g0) / det
        else:
            gnorm = np.sqrt(g0 * g0 + g1 * g1)
            s0, s1 = 0.1 * g0 / gnorm, 0.1 * g1 / gnorm
        s0 = s0 if np.isfinite(s0) else 0.0
        s1 = s1 if np.isfinite(s1) else 0.0
        length = np.sqrt(s0 * s0 + s1 * s1)
        scale = min(1.0, 0.3 / (length if length > 0.0 else 1.0))
        s0 *= scale
        s1 *= scale
        for _ in range(6):  # halve until E_AM rises (never worse)
            c0 = n0 + s0 * a0 + s1 * b0
            c1 = n1 + s0 * a1 + s1 * b1
            c2 = n2 + s0 * a2 + s1 * b2
            cn = np.sqrt(c0 * c0 + c1 * c1 + c2 * c2)
            c0, c1, c2 = c0 / cn, c1 / cn, c2 / cn
            uc, vc, fc = _uvwf(S, D, c0, c1, c2)
            if fc > f:
                n0, n1, n2 = c0, c1, c2
                u, v, f = uc, vc, fc
                break
            s0 *= 0.5
            s1 *= 0.5
        else:
            # No step was taken: every later iteration starts from this same point and
            # repeats this one exactly, so stopping here changes nothing.
            break
    n[0], n[1], n[2] = n0, n1, n2
    return f


@njit(cache=True, error_model="numpy")
def _element(
    S, D, Cp, Cm, Cw, grid, cg, sg, extra, root_iters, newton_iters, out_n, work
):
    """``tit.calc._max_sphere`` for one element; the direction goes to ``out_n``.

    ``work`` is scratch reused across elements: ``(Vs, g, branch_f, branch_n, Vj, M, bn, seed)``.
    """
    G = grid.shape[0]
    Vs, g, branch_f, branch_n, Vj, M, bn, seed = work
    branch_f[:] = -1.0
    branch_n[:] = 0.0
    bn[:] = 0.0
    best = -1.0

    # Track the three eigen-branches of cos(t) C+ - sin(t) C- over the grid.
    for j in range(G):
        ct, st = cg[j], sg[j]
        for x in range(3):
            for y in range(3):
                M[x, y] = ct * Cp[x, y] - st * Cm[x, y]
        if j > 0:
            Vj[:] = Vs[j - 1]
        _eigh(M, Vj, j > 0)
        if j == 0:
            Vs[0] = Vj
        else:  # tit.calc._match_columns: best permutation by |overlap|, then signs
            top = -1.0
            perm = _PERMS[0]
            for p in _PERMS:
                score = 0.0
                for i in range(3):
                    o = 0.0
                    for r in range(3):
                        o += Vs[j - 1, r, i] * Vj[r, p[i]]
                    score += abs(o)
                if score > top:
                    top, perm = score, p
            for i in range(3):
                o = 0.0
                for r in range(3):
                    o += Vs[j - 1, r, i] * Vj[r, perm[i]]
                sgn = -1.0 if o < 0.0 else 1.0
                for r in range(3):
                    Vs[j, r, i] = sgn * Vj[r, perm[i]]
        for c in range(3):
            u, v, f = _uvwf(S, D, Vs[j, 0, c], Vs[j, 1, c], Vs[j, 2, c])
            g[j, c] = ct * ct * u - st * st * v
            if f > branch_f[c]:
                branch_f[c] = f
                branch_n[c] = Vs[j, :, c]
            if f > best:
                best = f
                bn[:] = Vs[j, :, c]

    # Illinois regula falsi on every bracketed sign change of g along a branch.
    for j in range(G - 1):
        for c in range(3):
            if np.signbit(g[j, c]) == np.signbit(g[j + 1, c]):
                continue
            a, b = grid[j], grid[j + 1]
            ga, gb = g[j, c], g[j + 1, c]
            side = 0.0
            Vj[:] = Vs[j]  # warm start; then each iterate from the previous one
            for _ in range(root_iters):
                x = (a * gb - b * ga) / (gb - ga)
                cx, sx = np.cos(x), np.sin(x)
                for p in range(3):
                    for q in range(3):
                        M[p, q] = cx * Cp[p, q] - sx * Cm[p, q]
                _eigh(M, Vj, True)
                col, top = 0, -1.0
                for i in range(3):
                    o = abs(
                        Vs[j, 0, c] * Vj[0, i]
                        + Vs[j, 1, c] * Vj[1, i]
                        + Vs[j, 2, c] * Vj[2, i]
                    )
                    if o > top:
                        col, top = i, o
                u, v, f = _uvwf(S, D, Vj[0, col], Vj[1, col], Vj[2, col])
                gx = cx * cx * u - sx * sx * v
                if np.signbit(gx) == np.signbit(ga):
                    ga, a = gx, x
                    if side == 1.0:
                        gb = gb / 2
                    side = 1.0
                else:
                    gb, b = gx, x
                    if side == -1.0:
                        ga = ga / 2
                    side = -1.0
                if f > best:
                    best = f
                    bn[:] = Vj[:, col]

    # Safeguards: the eigenvectors of C+, C- and C+ - C-, and each pair's own K=1 optimum.
    for C in (Cp, Cm, Cw):
        M[:] = C
        _eigh(M, Vj, False)
        for i in range(3):
            u, v, f = _uvwf(S, D, Vj[0, i], Vj[1, i], Vj[2, i])
            if f > best:
                best = f
                bn[:] = Vj[:, i]
    for k in range(extra.shape[0]):
        u, v, f = _uvwf(S, D, extra[k, 0], extra[k, 1], extra[k, 2])
        if f > best:
            best = f
            bn[:] = extra[k]

    # Local polish: Newton ascent from the best point and from each branch's best grid point.
    seed[:] = bn
    f = _newton(S, D, Cp, Cm, seed, newton_iters)
    out_n[:] = bn
    if f > best:
        best = f
        out_n[:] = seed
    for c in range(3):
        seed[:] = branch_n[c]
        f = _newton(S, D, Cp, Cm, seed, newton_iters)
        if f > best:
            best = f
            out_n[:] = seed
    out_n /= np.sqrt(out_n[0] ** 2 + out_n[1] ** 2 + out_n[2] ** 2)
    return max(best, 0.0)


@njit(cache=True, error_model="numpy", parallel=True)
def max_sphere(E, grid, extra, root_iters, newton_iters):
    """K>=2 sphere maximum of ``E`` ``(2K, n, 3)``: ``(amp (n,), n_hat (n, 3))``.

    ``grid`` is ``tit.calc._THETA_GRID``, ``extra`` ``(n, K, 3)`` each pair's K=1 optimum,
    ``root_iters``/``newton_iters`` ``tit.calc._ROOT_ITERS``/``_NEWTON_ITERS``.
    """
    K = E.shape[0] // 2
    n_el = E.shape[1]
    G = grid.shape[0]
    amp = np.empty(n_el)
    n_hat = np.empty((n_el, 3))
    block = 64  # elements per scratch allocation
    cg, sg = np.cos(grid), np.sin(grid)
    for blk in prange((n_el + block - 1) // block):
        S = np.empty((K, 3))
        D = np.empty((K, 3))
        Cp = np.empty((3, 3))
        Cm = np.empty((3, 3))
        Cw = np.empty((3, 3))
        work = (
            np.empty((G, 3, 3)),
            np.empty((G, 3)),
            np.empty(3),
            np.empty((3, 3)),
            np.empty((3, 3)),
            np.empty((3, 3)),
            np.empty(3),
            np.empty(3),
        )
        for e in range(blk * block, min(n_el, (blk + 1) * block)):
            for k in range(K):
                for x in range(3):
                    S[k, x] = E[2 * k, e, x] + E[2 * k + 1, e, x]
                    D[k, x] = E[2 * k, e, x] - E[2 * k + 1, e, x]
            # tit.calc._forms
            Cp[:] = 0.0
            Cm[:] = 0.0
            Cw[:] = 0.0
            for k in range(K):
                for x in range(3):
                    for y in range(3):
                        Cp[x, y] += S[k, x] * S[k, y]
                        Cm[x, y] += D[k, x] * D[k, y]
                        Cw[x, y] += E[2 * k, e, x] * E[2 * k + 1, e, y]
            Cp *= 0.5
            Cm *= 0.5
            for x in range(3):  # Cw + Cw^T
                for y in range(x, 3):
                    Cw[x, y] = Cw[y, x] = Cw[x, y] + Cw[y, x]
            amp[e] = _element(
                S,
                D,
                Cp,
                Cm,
                Cw,
                grid,
                cg,
                sg,
                extra[e],
                root_iters,
                newton_iters,
                n_hat[e],
                work,
            )
    return amp, n_hat
