"""numba kernel for the K>=2 sphere maximum of :func:`tit.calc.envelope_max`.

One element at a time, parallel over elements: track the three eigen-branches of
``cos(t) C+ - sin(t) C-`` over ``tit.calc._THETA_GRID``, root-find every sign change of
``g = cos^2(t) u - sin^2(t) v`` along a branch, add safeguard candidates, then polish the best
candidates with Newton ascent.  Each step is load-bearing: removing any of them, or lowering
``tit.calc._ROOT_ITERS`` / ``_NEWTON_ITERS``, fails the dense-search tests in
``tests/test_calc.py``.  The 3x3 eigensolver is cyclic Jacobi warm-started from the previous
eigenvectors (LAPACK's per-call overhead was most of the cost of a NumPy version).

numba is a hard dependency: the image ships it and ``container/blueprint/verify_runtime.py``
fails the build without it.  Accuracy is pinned against independent oracles in
``tests/test_calc.py`` (host) and ``tests/numerical/test_calc_kernel.py`` (image).
"""

import numpy as np
from numba import njit, prange

_SQRT2 = np.sqrt(2.0)
_OFF = ((0, 1), (0, 2), (1, 2))
# Cyclic-Jacobi sweep cap.  10.8 million grid and safeguard solves on random and degenerate
# K = 2-4 fields needed at most 5 sweeps, the final check included (measured 2026-10-27);
# a row that still has not converged is flagged and tit.calc raises.
_SWEEPS = 50


@njit(cache=True, error_model="numpy")
def _qf(A, x0, x1, x2, y0, y1, y2):
    """``x^T A y`` for symmetric 3x3 ``A``, unrolled: the kernel's only matrix product."""
    return (
        x0 * (A[0, 0] * y0 + A[0, 1] * y1 + A[0, 2] * y2)
        + x1 * (A[1, 0] * y0 + A[1, 1] * y1 + A[1, 2] * y2)
        + x2 * (A[2, 0] * y0 + A[2, 1] * y1 + A[2, 2] * y2)
    )


@njit(cache=True, error_model="numpy")
def _eigh(A, V, warm):
    """Cyclic-Jacobi eigenvectors of symmetric 3x3 ``A`` into ``V``'s columns, ascending.

    Replaces LAPACK, whose per-call overhead dominated.  ``A`` is overwritten (its diagonal
    ends up holding the eigenvalues).  ``warm`` starts from the basis already in ``V`` (a
    nearby matrix's eigenvectors) instead of the identity.  Returns whether it converged
    within ``_SWEEPS`` sweeps; for finite ``A`` it always does.
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
    converged = False
    for _ in range(_SWEEPS):
        if abs(A[0, 1]) <= tol and abs(A[0, 2]) <= tol and abs(A[1, 2]) <= tol:
            converged = True
            break
        for p, q in _OFF:
            apq = A[p, q]
            if abs(apq) <= tol:
                continue
            theta = (A[q, q] - A[p, p]) / (2.0 * apq)
            if abs(theta) > 1e150:  # theta^2 would overflow; t -> 1/(2 theta)
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
    return converged


@njit(cache=True, error_model="numpy")
def _uvwf(S, D, n0, n1, n2):
    """``u, v`` and ``E_AM`` at ``n`` from the projections, the kernel's one envelope evaluation.

    ``u = |S n|^2 / 2``, ``v = |D n|^2 / 2``, ``E_AM = sqrt(2) |u - v| / (sqrt(u) + sqrt(v))``
    (``tit.calc._uvw``/``_env_uvw``): from the projections, not ``n^T C n``, which loses ``v``
    to round-off next to a cusp.  A null field gives 0.
    """
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
    """Riemannian Newton ascent of ``E_AM`` from the unit seed ``n`` (updated in place); returns ``f``.

    The polish that closes the gap a grid interval leaves: the root-find can miss two close
    roots inside one interval, and a narrow ridge defeats a pattern search.  On the side
    ``u >= v``, ``E_AM = sqrt(2u) - sqrt(2v)`` (else its negative), smooth away from the cusps
    ``u = 0``, ``v = 0`` (the safeguards cover those).  Gradient and Hessian are formed in the
    tangent frame ``(e1, e2)``; where the tangent Hessian is not negative definite the step is
    a 0.1 rad gradient step.  A step is kept only if it raises ``E_AM`` (halved up to 6
    times), so the result is never below the seed; a zero gradient or a cusp gives no step.
    """
    n0, n1, n2 = n[0], n[1], n[2]
    u, v, f = _uvwf(S, D, n0, n1, n2)
    for _ in range(iters):
        up = u >= v
        A, B = (Cp, Cm) if up else (Cm, Cp)
        ua, vb = (u, v) if up else (v, u)
        ra, rb = np.sqrt(ua), np.sqrt(vb)
        # tangent frame: e1 = n x (unit axis least parallel to n), e2 = n x e1; for unit n
        # the cross product has norm >= 0.43, so the division is safe.
        if abs(n0) > 0.9:
            a0, a1, a2 = -n2, 0.0, n0  # n x (0, 1, 0)
        else:
            a0, a1, a2 = 0.0, n2, -n1  # n x (1, 0, 0)
        nrm = np.sqrt(a0 * a0 + a1 * a1 + a2 * a2)
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
        # A cusp (ra or rb = 0) or a zero gradient makes the step non-finite: take none.
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
    """The sphere maximum of one element, direction into ``out_n``; returns ``(amp, ok)``.

    Branches, root-find, safeguards and polish as in the module docstring; ``ok`` is False if
    any eigen-solve did not converge.  ``work`` is scratch reused across elements:
    ``(Vs, g, branch_f, branch_n, Vj, M, bn, seed)``.
    """
    G = grid.shape[0]
    Vs, g, branch_f, branch_n, Vj, M, bn, seed = work
    branch_f[:] = -1.0
    branch_n[:] = 0.0
    bn[:] = 0.0
    best = -1.0
    ok = True  # every eigen-solve converged

    # The three eigen-branches of cos(t) C+ - sin(t) C- over the grid, in eigenvalue order,
    # each solve warm-started from the previous grid point.
    for j in range(G):
        ct, st = cg[j], sg[j]
        for x in range(3):
            for y in range(3):
                M[x, y] = ct * Cp[x, y] - st * Cm[x, y]
        if j > 0:
            Vs[j] = Vs[j - 1]
        ok = _eigh(M, Vs[j], j > 0) and ok
        for c in range(3):
            u, v, f = _uvwf(S, D, Vs[j, 0, c], Vs[j, 1, c], Vs[j, 2, c])
            g[j, c] = ct * ct * u - st * st * v
            if f > branch_f[c]:
                branch_f[c] = f
                branch_n[c] = Vs[j, :, c]
            if f > best:
                best = f
                bn[:] = Vs[j, :, c]

    # Illinois regula falsi on every bracketed sign change of g along a branch: the maximiser
    # is the eigenvector at a root of g.
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
                ok = _eigh(M, Vj, True) and ok
                col, top = 0, -1.0  # the column that continues branch c
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

    # Safeguards: the eigenvectors of C+, C- and C+ - C- (the cusps and the grid's ends), and
    # each pair's own K=1 optimum (exact when the other pairs vanish).
    for C in (Cp, Cm, Cw):
        M[:] = C
        ok = _eigh(M, Vj, False) and ok
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
    return best, ok


@njit(cache=True, error_model="numpy", parallel=True)
def max_sphere(E, grid, extra, root_iters, newton_iters):
    """K>=2 sphere maximum of ``E`` ``(2K, n, 3)``: ``(amp (n,), n_hat (n, 3), ok (n,))``.

    ``ok`` is False where an eigen-solve did not converge; ``tit.calc`` raises on any such row.
    ``grid`` is ``tit.calc._THETA_GRID``, ``extra`` ``(n, K, 3)`` each pair's K=1 optimum,
    ``root_iters``/``newton_iters`` ``tit.calc._ROOT_ITERS``/``_NEWTON_ITERS``.  A null element
    gives 0 (its direction is set by ``tit.calc``).
    """
    K = E.shape[0] // 2
    n_el = E.shape[1]
    G = grid.shape[0]
    amp = np.empty(n_el)
    n_hat = np.empty((n_el, 3))
    ok = np.empty(n_el, dtype=np.bool_)
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
            # C+ = S^T S / 2, C- = D^T D / 2, Cw = sum_k (E_ka E_kb^T + E_kb E_ka^T) = C+ - C-
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
            amp[e], ok[e] = _element(
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
    return amp, n_hat, ok
