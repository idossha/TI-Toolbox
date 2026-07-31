"""Joint electrode-placement + current-ratio search, and constrained objectives.

Two additions to flex-search, both riding on one hook.

**Current ratio as a free dimension.** flex-search fixes an equal 1:1 split
between the two TI channels, but the published optimum is essentially never 1:1
(Lee 2020: 1.35–1.67:1; Inoue 2025 over 60 subjects: ~1:1.86). Because the FEM
is linear, the fields for a *fixed* placement scale with the injected current,
so the ratio can be swept on the already-computed fields — Lee 2022: *"as the
relationship between the electric field and the amplitude of the injection
current is linear, the [objective] is affected only by the current ratio if the
location of the electrode pairs is fixed."* Cost is 2 FEM solves plus N cheap
envelope evaluations, so the ratio adds an optimization dimension **without
adding a single differential-evolution parameter** (it becomes an inner exact
search, the nesting every published implementation uses).

The ratio must be optimized *jointly* with placement, not applied afterwards:
Savvateev 2025 shows a montage optimized at 1:1 only loses amplitude when the
ratio is varied post hoc.

**Constrained / Pareto objective.** Rather than folding intensity and focality
into one ad-hoc ratio, maximize ROI intensity subject to an explicit off-target
bound and sweep the bound to trace a Pareto front (Brahma 2025 sweeps 12 energy
levels via SQP; Huang 2026; Ahsan 2022). This answers Weise 2025's own stated
future work — "flexibly weighted combined objectives / true Pareto-optimal
solutions".

The SimNIBS callable-`goal` hook only receives the *combined* envelope, so both
features instead wrap ``opt.goal_fun``, which still has the raw per-channel
fields.

Public API
----------
ratio_levels, pareto_objective, install_joint_goal
"""

from __future__ import annotations

import logging

import numpy as np

_log = logging.getLogger("simnibs")

# Baseline used by Huang & Parra: the modulation depth 2*min(|E1|,|E2|) is
# maximised when the two induced *fields* match at the target, which for
# asymmetric anatomy is a non-1:1 *current* ratio.
__all__ = ["ratio_levels", "pareto_objective", "install_joint_goal",
           "field_equalising_ratio"]


def ratio_levels(total_mA: float = 4.0, lo: float = 1.0, hi: float = 3.0,
                 n: int = 21) -> list[tuple[float, float]]:
    """Current splits ``(I1, I2)`` with ``I1 + I2 == total_mA``.

    Defaults give I1 ∈ [1, 3] mA in 21 steps of 0.1 mA — a 1:3 … 3:1 span at a
    fixed 4 mA total, matching the literature's ratio span (Lee 2020,
    Stoupis 2022, Rampersad/Ghanem ES all use 21 levels).
    """
    return [(float(a), float(total_mA - a)) for a in np.linspace(lo, hi, n)]


def pareto_objective(p_bound: float, lam: float = 10.0):
    """Maximize ROI intensity subject to an off-target bound (penalty form).

    ``minimize  −mean(E_ROI) + lam · max(0, rms(E_nonROI)/P − 1)²``

    The violation is *relative* to ``P`` so the penalty is scale-free and the
    same ``lam`` works across targets and subjects. Sweeping ``p_bound`` traces
    the intensity/focality Pareto front without any arbitrary weighting.

    Parameters
    ----------
    p_bound : float
        Off-target bound, as RMS TI envelope over the non-ROI (V/m).
    lam : float, optional
        Penalty weight on the relative violation.
    """

    def objective(e_roi, e_nonroi):
        roi = float(np.mean(e_roi))
        off = float(np.sqrt(np.mean(np.square(e_nonroi))))
        viol = max(0.0, off / max(p_bound, 1e-9) - 1.0)
        return -roi + lam * viol * viol

    return objective


def field_equalising_ratio(e1_roi, e2_roi, total_mA: float, base_mA: float):
    """Huang & Parra's analytic ratio: equalize |E1| = |E2| in the ROI.

    Since ``MD = 2·min(|E1|, |E2|)``, modulation depth peaks where the two
    induced field magnitudes match — one division instead of a grid sweep.
    Returned as ``(I1, I2)`` summing to *total_mA*.
    """
    m1 = float(np.mean(np.linalg.norm(np.asarray(e1_roi, float), axis=-1)))
    m2 = float(np.mean(np.linalg.norm(np.asarray(e2_roi, float), axis=-1)))
    # a1*m1 == a2*m2 with a=I/base and I1+I2=total  ->  I1 = total*m2/(m1+m2)
    denom = max(m1 + m2, 1e-12)
    i1 = total_mA * m2 / denom
    return float(i1), float(total_mA - i1)


def install_joint_goal(opt, objective, store, base_mA: float,
                       ratios: list[tuple[float, float]] | None = None,
                       select_subsample: int = 50000):
    """Replace ``opt.goal_fun`` with a joint placement + current-ratio search.

    *objective* is called as ``objective(e_roi_env, e_nonroi_env)`` and must
    return a scalar to **minimize**. When *ratios* is given, every candidate
    placement is scored at each split and the best is returned, so the reported
    objective is already ratio-optimized.

    Parameters
    ----------
    opt : TesFlexOptimization
        Built (not yet run) optimization object; mutated in place.
    objective : callable
        ``(e_roi, e_nonroi) -> float`` to minimize.
    store : dict
        Receives ``trajectory``, ``best_value``, ``best_ratio_mA``,
        ``e_roi``/``e_nonroi`` of the best montage, and ``ratio_progress``.
    base_mA : float
        Per-channel current baked into ``opt.electrode`` (fields scale from it).
    ratios : list of (I1, I2), optional
        Splits to sweep. ``None`` keeps the built-in equal split (1:1).
    select_subsample : int, optional
        Evaluate the *ratio choice* on at most this many non-ROI points, then
        re-score the winner on the full non-ROI. The non-ROI is typically the
        whole brain (~3M elements), so sweeping every ratio at full resolution
        would dominate the FEM cost; a fixed deterministic subsample makes the
        selection ~free while the returned objective stays exact. Set to 0 to
        always use the full non-ROI.
    """
    from simnibs.optimization.tes_flex_optimization.tes_flex_optimization import (
        postprocess_e,
    )

    store.setdefault("trajectory", [])
    store.setdefault("ratio_progress", [])
    store.setdefault("best_value", float("inf"))
    store.setdefault("best_ratio_mA", None)
    store.setdefault("best_ratio_hist", [])

    sweep = ratios if ratios else [(base_mA, base_mA)]
    idx_cache: dict[int, np.ndarray | None] = {}

    def _sub_idx(n):
        """Deterministic subsample index for the non-ROI (cached by size)."""
        if n not in idx_cache:
            idx_cache[n] = (np.linspace(0, n - 1, select_subsample).astype(int)
                            if select_subsample and n > select_subsample else None)
        return idx_cache[n]

    def _envelope(e, i_roi, a1, a2, rows=None):
        e1 = e[0][i_roi] if rows is None else e[0][i_roi][rows]
        e2 = e[1][i_roi] if rows is None else e[1][i_roi][rows]
        dirvec = opt._goal_dir[i_roi]
        if rows is not None and isinstance(dirvec, np.ndarray) and dirvec.ndim == 2 \
                and dirvec.shape[0] == len(e[0][i_roi]):
            dirvec = dirvec[rows]
        return postprocess_e(e=a1 * e1, e2=a2 * e2, dirvec=dirvec,
                             type=opt.e_postproc[i_roi])

    def goal_fun(parameters):
        opt.n_test += 1
        opt.electrode_pos = opt.get_electrode_pos_from_array(parameters)
        e = opt.update_field(electrode_pos=opt.electrode_pos, plot=False)
        if e is None:
            return 2.0  # electrode overlap — SimNIBS's own penalty value
        opt.n_sim += 1

        # -- stage 1: pick the split on a cheap non-ROI subsample --
        rows = _sub_idx(len(e[0][1])) if len(sweep) > 1 and opt._n_roi > 1 else None
        best_split, best_probe = sweep[0], float("inf")
        if len(sweep) > 1:
            for i1, i2 in sweep:
                a1, a2 = i1 / base_mA, i2 / base_mA
                roi_env = _envelope(e, 0, a1, a2)
                non_env = _envelope(e, 1, a1, a2, rows)
                v = float(objective(roi_env, non_env))
                if np.isfinite(v) and v < best_probe:
                    best_probe, best_split = v, (i1, i2)

        # -- stage 2: exact score for the winning split (full non-ROI) --
        a1, a2 = best_split[0] / base_mA, best_split[1] / base_mA
        best_env = [_envelope(e, i_roi, a1, a2) for i_roi in range(opt._n_roi)]
        best_v = float(objective(best_env[0], best_env[1]))
        if not np.isfinite(best_v):
            return 1e3

        store["trajectory"].append(best_v)
        store["best_ratio_hist"].append(best_split)
        if best_v < store["best_value"]:
            e_roi = np.asarray(best_env[0], float)
            e_nonroi = np.asarray(best_env[1], float)
            store["best_value"] = best_v
            store["best_ratio_mA"] = best_split
            store["e_roi"] = e_roi.copy()
            store["e_nonroi"] = e_nonroi.copy()
            store["best_ratio"] = float(e_roi.mean()) / max(float(e_nonroi.mean()), 1e-9)
            try:
                store["electrode_pos"] = [
                    [None if p is None else np.asarray(p, float).tolist() for p in arr]
                    for arr in opt.electrode_pos
                ]
            except Exception:
                store["electrode_pos"] = None
        store["ratio_progress"].append(store.get("best_ratio", 0.0))
        # Emit SimNIBS's own progress line so live monitoring and the report's
        # trajectory parser keep working for joint runs.
        _log.info(
            "Goal (joint): %.3f (n_sim: %d, n_test: %d) split %.1f:%.1f mA",
            best_v, opt.n_sim, opt.n_test, best_split[0], best_split[1],
        )
        return best_v

    opt.goal_fun = goal_fun
    return opt
