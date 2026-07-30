"""Custom optimization objectives for flex-search.

SimNIBS ``TesFlexOptimization`` accepts a Python callable as its ``goal``. The
callable is invoked as ``goal(e_pp)`` where ``e_pp[channel][roi_index]`` holds
the post-processed field values for each ROI (index ``0`` = ROI, index ``1`` =
non-ROI). This module builds such callables for objectives that SimNIBS
implements as *measures* but does not otherwise expose as optimizable goals.

Public API
----------
make_integral_focality_objective
    Build a callable goal that maximizes integral focality.
integral_focality_value
    Pure-function integral-focality measure (Fernandez-Corazza 2020, eq. 14).

See Also
--------
tit.opt.config.FlexConfig.OptGoal.FOCALITY_INTEGRAL : Selects this objective.
tit.opt.flex.builder.build_optimization : Wires the callable onto ``opt.goal``.
"""

from __future__ import annotations

import numpy as np

# Floor for the non-ROI term to keep the ratio finite when the mean non-ROI
# field is ~0 (e.g. a signed post-processing component). Well below any
# physically meaningful E-field magnitude, so it never affects real candidates.
_DENOM_FLOOR = 1e-12

# Penalty returned for degenerate candidates (non-finite ratio). Positive
# because differential evolution minimizes the negated measure, so a large
# positive value marks the candidate as bad without introducing NaN/inf that
# would destabilize the optimizer (mirrors SimNIBS's overlap penalty of 2.0).
_PENALTY = 1e3


def integral_focality_value(
    e1: np.ndarray, e2: np.ndarray, v1: float, v2: float
) -> float:
    """Integral focality measure (Fernandez-Corazza et al. 2020, eq. 14).

    Mirrors ``simnibs.optimization.tes_flex_optimization.measures.integral_focality``
    so the optimized objective and SimNIBS's tracked metric agree exactly for
    non-negative fields; equivalence is asserted numerically in the tests.

    Parameters
    ----------
    e1 : np.ndarray
        Field values in the ROI.
    e2 : np.ndarray
        Field values in the non-ROI.
    v1 : float
        ROI volume/area normalizer (mean node volume-or-area).
    v2 : float
        Non-ROI volume/area normalizer.

    Returns
    -------
    float
        ``(mean(e1) / v1) / sqrt(mean(e2) / v2)``. Larger is more focal.
    """
    # Stay in numpy arithmetic so a degenerate normalizer (v == 0) yields inf
    # rather than raising ZeroDivisionError; the caller treats non-finite scores
    # as a penalty. The floor keeps the denominator strictly positive when the
    # mean non-ROI field is ~0 or (for signed components) negative.
    with np.errstate(divide="ignore", invalid="ignore"):
        num = np.mean(e1) / v1
        denom = np.sqrt(max(np.mean(e2) / v2, _DENOM_FLOOR))
        return float(num / denom)


def make_integral_focality_objective(opt):
    """Build a SimNIBS goal callable that maximizes integral focality.

    Differential evolution *minimizes* the goal, so the returned callable
    negates the measure. The ROI is expected at index ``0`` and the non-ROI at
    index ``1`` of each channel in ``e_pp`` (as configured by
    :func:`tit.opt.flex.utils.configure_roi` for focality goals).

    The ROI/non-ROI volume normalizers ``opt._vol`` are read lazily at call
    time because SimNIBS only populates them during ``opt.run()``'s preparation
    step, after this callable has been attached to ``opt.goal``.

    Parameters
    ----------
    opt : TesFlexOptimization
        The optimization object; ``opt._vol`` must hold ``[V_ROI, V_nonROI]``
        by the time the callable runs.

    Returns
    -------
    callable
        A ``goal(e_pp) -> float`` closure (a ``types.FunctionType``, which is
        what SimNIBS's callable-goal path requires).
    """

    def objective(e_pp):
        v1, v2 = opt._vol[0], opt._vol[1]
        values = []
        for channel in e_pp:
            e1 = np.asarray(channel[0], dtype=float)  # ROI
            e2 = np.asarray(channel[1], dtype=float)  # non-ROI
            values.append(integral_focality_value(e1, e2, v1, v2))
        score = float(np.mean(values))
        if not np.isfinite(score):
            return _PENALTY
        return -score

    return objective
