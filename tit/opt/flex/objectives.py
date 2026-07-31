"""Optimization objectives and current-ratio search for flex-search.

Two capabilities live here.

**Threshold-free focality.** SimNIBS's built-in ``"focality"`` goal scores a
candidate through a ROC distance that depends on user-supplied field thresholds
(``measures.ROC``).  Choosing those thresholds is itself a hard problem: when the
requested ROI and non-ROI thresholds are jointly infeasible the ROC distance
takes the same value for every candidate and the search landscape goes flat.
:func:`threshold_free_focality` scores the ROI/non-ROI contrast directly, so no
threshold has to be chosen and the landscape keeps a usable gradient.

**Current-ratio search.** The FEM solved by SimNIBS is linear, so for a fixed
electrode placement the field of each channel scales with that channel's
injected current (Lee et al. 2022).  A split other than 1:1 can therefore be
evaluated by rescaling the two per-channel fields rather than re-solving, and
published TI optima are rarely the 1:1 split that flex-search fixes by default
(Lee et al. 2020; Inoue et al. 2025, n = 60).  :func:`install_ratio_search`
turns the split into a searched dimension at roughly the cost of the extra
post-processing alone.

Public API
----------
threshold_free_focality
    Threshold-free ROI/non-ROI focality contrast (larger is more focal).
make_objective
    Build a ``f(e_roi, e_nonroi) -> float`` objective to *minimize* for any
    :class:`~tit.opt.config.FlexConfig.OptGoal`.
ratio_levels
    Enumerate the discrete ``(I1, I2)`` current splits to search.
install_ratio_search
    Wrap ``opt.goal_fun`` so placement and current split are optimized jointly.

See Also
--------
tit.opt.config.FlexConfig.OptGoal.FOCALITY_TF : Selects the threshold-free goal.
tit.opt.flex.builder.build_optimization : Wires these onto the SimNIBS object.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable, Sequence

import numpy as np

#: Progress is logged through SimNIBS's own logger so that ratio-search runs
#: interleave with the solver's goal lines in the same log file.
logger = logging.getLogger("simnibs")

#: Floor for the non-ROI denominator, keeping the contrast ratio finite when the
#: non-ROI field is ~0 (or negative, for a signed post-processing component).
#: Far below any physically meaningful E-field magnitude, so it never affects a
#: real candidate.
_DENOM_FLOOR = 1e-12

#: Percentile of the non-ROI field used as the "spread" term.  The 95th
#: percentile tracks the hot tail that actually competes with the target while
#: ignoring single outlier elements that a plain max would chase.
_NONROI_PERCENTILE = 95.0

#: Percentile used as the "peak" ROI field, matching SimNIBS's ``"max"`` goal.
_ROI_PEAK_PERCENTILE = 99.9

#: Value returned for a degenerate candidate.  Large and positive because the
#: differential evolution solver minimizes, so this marks the candidate as bad
#: without introducing the NaN/inf that would destabilize the solver (SimNIBS
#: uses the same idea with its overlap penalty of 2.0).
_PENALTY = 1e3


# ---------------------------------------------------------------------------
# Threshold-free focality measure
# ---------------------------------------------------------------------------


def threshold_free_focality(
    e_roi: np.ndarray,
    e_nonroi: np.ndarray,
    intensity_weight: float = 0.0,
) -> float:
    """Threshold-free focality contrast between ROI and non-ROI fields.

    Computes ``mean(e_roi) ** (1 + w) / p95(e_nonroi)``, where ``w`` is
    *intensity_weight*.  Unlike SimNIBS's ROC-based focality goal this needs no
    threshold, so it cannot be flattened by a threshold pair that no candidate
    can satisfy.  The non-ROI is summarised by its 95th percentile rather than
    its mean, so a candidate is judged against the hottest competing tissue
    instead of a bulk average dominated by far-field elements.

    The weight trades the two terms off: ``w = 0`` gives the balanced form
    (raising ROI mean and lowering the non-ROI tail count equally), while
    ``w = 1`` squares the ROI term so raw ROI intensity dominates.

    Parameters
    ----------
    e_roi : numpy.ndarray
        Post-processed field values in the ROI.
    e_nonroi : numpy.ndarray
        Post-processed field values in the non-ROI.
    intensity_weight : float, optional
        Weight ``w`` in ``[0, 1]``.  Default ``0.0``.

    Returns
    -------
    float
        Focality contrast; larger is more focal.  Returns ``0.0`` (the worst
        possible score) for a degenerate candidate -- an empty ROI or non-ROI,
        a non-positive mean ROI field, or a non-finite ratio.

    Notes
    -----
    A negative mean ROI field can arise from a signed post-processing component
    (e.g. ``dir_TI_normal``) and means the target is not being driven in the
    requested direction; it is floored at zero rather than raised to a
    fractional power.
    """
    roi = np.asarray(e_roi, dtype=float)
    non_roi = np.asarray(e_nonroi, dtype=float)
    if roi.size == 0 or non_roi.size == 0:
        return 0.0

    mean_roi = max(float(np.mean(roi)), 0.0)
    spread = max(float(np.percentile(non_roi, _NONROI_PERCENTILE)), _DENOM_FLOOR)

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        value = float(mean_roi ** (1.0 + float(intensity_weight)) / spread)

    if not np.isfinite(value):
        return 0.0
    return value


# ---------------------------------------------------------------------------
# Objective construction
# ---------------------------------------------------------------------------


def _guard(value: float) -> float:
    """Replace a non-finite objective value with a large positive penalty."""
    result = float(value)
    if not np.isfinite(result):
        return _PENALTY
    return result


def _parse_thresholds(thresholds) -> float | list[float]:
    """Normalise a threshold specification into the form ``measures.ROC`` wants.

    Parameters
    ----------
    thresholds : str or float or sequence of float
        Comma-separated string (``"0.1,0.2"``), a single number, or a sequence.

    Returns
    -------
    float or list of float
        A scalar for a single threshold, otherwise the list of values.

    Raises
    ------
    ValueError
        If *thresholds* is ``None``, empty, or a placeholder such as
        ``"dynamic"`` -- the ROC objective cannot be evaluated without an
        explicit threshold.
    """
    if thresholds is None:
        raise ValueError("goal 'focality' requires explicit numeric thresholds")
    if isinstance(thresholds, str):
        raw = thresholds.strip()
        if not raw or raw.lower() in {"dynamic", "auto"}:
            raise ValueError("goal 'focality' requires explicit numeric thresholds")
        values = [float(part) for part in raw.split(",")]
    elif isinstance(thresholds, (int, float)):
        values = [float(thresholds)]
    else:
        values = [float(part) for part in thresholds]
    if not values:
        raise ValueError("goal 'focality' requires explicit numeric thresholds")
    return values[0] if len(values) == 1 else values


def make_objective(
    goal,
    intensity_weight: float = 0.0,
    thresholds=None,
) -> Callable[[np.ndarray, np.ndarray], float]:
    """Build the scalar objective for an optimization goal.

    The returned callable takes the post-processed ROI and non-ROI fields of a
    single candidate and returns a value **to minimize**, matching the sign
    convention of SimNIBS's own ``compute_goal``.

    ==============  ==================================================
    Goal            Returned value
    ==============  ==================================================
    ``mean``        ``-mean(e_roi)``
    ``max``         ``-percentile(e_roi, 99.9)``
    ``focality``    ``-100 * (sqrt(2) - ROC(e_roi, e_nonroi, focal=True))``
    ``focality_tf`` ``-threshold_free_focality(e_roi, e_nonroi, w)``
    ==============  ==================================================

    ``mean`` and ``max`` ignore *e_nonroi*.

    Parameters
    ----------
    goal : FlexConfig.OptGoal or str
        Optimization goal.  Enum members and their plain string values are both
        accepted.
    intensity_weight : float, optional
        Weight ``w`` forwarded to :func:`threshold_free_focality`; only used by
        the ``focality_tf`` goal.  Default ``0.0``.
    thresholds : str or float or sequence of float, optional
        Threshold specification for the ROC-based ``focality`` goal; ignored by
        the other goals.

    Returns
    -------
    callable
        ``f(e_roi, e_nonroi) -> float``, lower being better.  Degenerate
        candidates yield a large positive penalty rather than NaN/inf.

    Raises
    ------
    ValueError
        If *goal* is not a recognised optimization goal, or the ``focality``
        goal is requested without usable thresholds.
    """
    goal_value = getattr(goal, "value", goal)

    if goal_value == "mean":

        def objective(e_roi, e_nonroi=None) -> float:
            roi = np.asarray(e_roi, dtype=float)
            if roi.size == 0:
                return _PENALTY
            return _guard(-float(np.mean(roi)))

    elif goal_value == "max":

        def objective(e_roi, e_nonroi=None) -> float:
            roi = np.asarray(e_roi, dtype=float)
            if roi.size == 0:
                return _PENALTY
            return _guard(-float(np.percentile(roi, _ROI_PEAK_PERCENTILE)))

    elif goal_value == "focality":
        threshold = _parse_thresholds(thresholds)

        def objective(e_roi, e_nonroi) -> float:
            # Imported lazily so this module stays importable without SimNIBS.
            from simnibs.optimization.tes_flex_optimization.measures import ROC

            roi = np.asarray(e_roi, dtype=float)
            non_roi = np.asarray(e_nonroi, dtype=float)
            if roi.size == 0 or non_roi.size == 0:
                return _PENALTY
            roc = ROC(e1=roi, e2=non_roi, threshold=threshold, focal=True)
            return _guard(-100.0 * (np.sqrt(2.0) - float(roc)))

    elif goal_value == "focality_tf":
        weight = float(intensity_weight)

        def objective(e_roi, e_nonroi) -> float:
            return _guard(-threshold_free_focality(e_roi, e_nonroi, weight))

    else:
        raise ValueError(f"Unknown optimization goal: {goal_value!r}")

    return objective


# ---------------------------------------------------------------------------
# Current-ratio search
# ---------------------------------------------------------------------------


def ratio_levels(total_mA: float, n: int = 21) -> list[tuple[float, float]]:
    """Enumerate the current splits searched by :func:`install_ratio_search`.

    Returns *n* splits ``(I1, I2)`` with ``I1 + I2 == total_mA``, sweeping the
    channel ratio from 1:3 to 3:1.  Individual channels therefore range from
    ``0.25 * total_mA`` to ``0.75 * total_mA`` -- i.e. half to one-and-a-half
    times the per-channel current of the 1:1 split.

    *n* is rounded **up to the next odd number** so the midpoint of the sweep is
    always the exact 1:1 split; this keeps flex-search's default behaviour inside
    the search range, so enabling the ratio search can never do worse than the
    balanced montage it would otherwise have used.

    Parameters
    ----------
    total_mA : float
        Total current (mA) shared by the two channels.
    n : int, optional
        Number of splits, rounded up to the next odd number.  Default ``21``.

    Returns
    -------
    list of tuple of float
        ``(I1, I2)`` pairs in mA, ordered from the most channel-2-heavy split
        to the most channel-1-heavy one.

    Raises
    ------
    ValueError
        If *total_mA* is non-positive or *n* is below 2.
    """
    total = float(total_mA)
    if total <= 0.0:
        raise ValueError(f"total_mA must be positive (was {total})")
    if int(n) < 2:
        raise ValueError(f"n must be >= 2 (was {n})")
    # Force an odd count so linspace lands exactly on the 1:1 midpoint.
    count = int(n) | 1
    first = np.linspace(total / 4.0, 3.0 * total / 4.0, count)
    return [(float(i1), float(total - i1)) for i1 in first]


def _subsample_index(n_rows: int, limit: int, cache: dict) -> np.ndarray | None:
    """Return deterministic row indices thinning *n_rows* down to *limit*.

    ``None`` means no thinning is needed.  Results are cached by row count
    because every candidate placement produces the same non-ROI array length.
    """
    if n_rows <= limit:
        return None
    index = cache.get(n_rows)
    if index is None:
        index = np.unique(np.linspace(0, n_rows - 1, limit).astype(int))
        cache[n_rows] = index
    return index


def _take(array, index: np.ndarray | None, n_rows: int):
    """Row-subset *array* by *index* when it has exactly *n_rows* rows.

    Passes ``None`` and non-aligned arrays through untouched -- SimNIBS allows a
    single ``(1, 3)`` direction vector that it broadcasts itself, and that must
    not be thinned.
    """
    if index is None or array is None:
        return array
    if np.shape(array)[0] != n_rows:
        return array
    return array[index]


def _balanced_first(
    splits: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Order splits from the most balanced outwards.

    Combined with a strict ``<`` improvement test this makes an exact tie
    resolve to the split closest to 1:1, which is the conservative choice for a
    stimulation-dose parameter.
    """
    return sorted(splits, key=lambda split: abs(split[0] - split[1]))


def _apply_current_split(opt, split: tuple[float, float]) -> None:
    """Rescale the channel electrodes so they inject the chosen *split*.

    The per-electrode currents are scaled rather than overwritten, so whatever
    sign and array structure SimNIBS built (including the ``_current_channel``
    used when Dirichlet correction is active) is preserved.
    """
    electrodes = getattr(opt, "electrode", None) or []
    for channel, current_mA in enumerate(split):
        if channel >= len(electrodes):
            break
        electrode = electrodes[channel]
        existing = getattr(electrode, "current", None)
        if existing is None or len(existing) == 0:
            continue
        # |current| is identical across a channel's electrodes; use it as the
        # reference amplitude so the scale factor is exact.
        reference = max(abs(float(existing[0])), 1e-12)
        scale = (float(current_mA) / 1000.0) / reference
        electrode.current = [float(value) * scale for value in existing]
        per_channel = getattr(electrode, "_current_channel", None)
        if per_channel is not None:
            electrode._current_channel = [float(v) * scale for v in per_channel]


def _install_split_applier(opt, state: dict) -> None:
    """Apply the winning current split before SimNIBS's final simulation.

    SimNIBS calls :meth:`get_nodes_electrode` once with ``electrode_pos_opt``
    after the search converges and immediately before it rebuilds the electrodes
    for the final simulation.  Hooking that one call is the only point at which
    the currents can be changed without perturbing the search itself, because
    every earlier call happens while candidates are still being scored.
    """
    original = opt.get_nodes_electrode

    def get_nodes_electrode(electrode_pos, plot=False):
        result = original(electrode_pos, plot=plot)
        optimum = getattr(opt, "electrode_pos_opt", None)
        if (
            optimum is not None
            and electrode_pos is optimum
            and state.get("best_split") is not None
        ):
            split = state["best_split"]
            _apply_current_split(opt, split)
            logger.info(
                "Applying optimized current split %.2f:%.2f mA to the final "
                "electrodes",
                split[0],
                split[1],
            )
        return result

    opt.get_nodes_electrode = get_nodes_electrode


def install_ratio_search(
    opt,
    objective: Callable[[np.ndarray, np.ndarray], float],
    base_mA: float,
    ratios: Sequence[tuple[float, float]] | Iterable[tuple[float, float]],
    select_subsample: int = 50000,
) -> None:
    """Optimize the electrode placement and the channel current split jointly.

    SimNIBS's callable-``goal`` hook only ever sees the *combined* TI envelope,
    which has already fused both channels at their configured currents -- too
    late to rescale them.  This function therefore replaces ``opt.goal_fun``,
    which still holds the raw per-channel fields, and reimplements SimNIBS's own
    preamble (candidate counting, electrode placement, FEM update, overlap
    penalty) before scoring.

    Because the FEM is linear, applying a split ``(I1, I2)`` to a fixed
    placement is a rescaling of the two per-channel fields by ``I1 / base_mA``
    and ``I2 / base_mA`` (Lee et al. 2022), so every split reuses the single FEM
    solve already computed for that placement.  Searching the split is
    worthwhile because reported TI optima are typically not the 1:1 split that
    flex-search otherwise assumes (Lee et al. 2020; Inoue et al. 2025).

    Scoring runs in two stages so the added post-processing stays cheap: the
    non-ROI can hold millions of elements, so stage one ranks the splits using a
    deterministic subsample of at most *select_subsample* non-ROI rows, and
    stage two re-scores only the winning split on the full non-ROI.  The value
    returned to the solver is always the full-resolution one.

    Parameters
    ----------
    opt : TesFlexOptimization
        SimNIBS optimization object; mutated in place.  Attributes populated
        during ``opt.run()`` preparation (``_goal_dir``, ``e_postproc``) are
        read lazily inside the wrapper, so this may be called at build time.
    objective : callable
        ``f(e_roi, e_nonroi) -> float`` to minimize, e.g. from
        :func:`make_objective`.
    base_mA : float
        Per-channel current (mA) the electrodes were configured with; the
        reference the split is scaled against.
    ratios : sequence of tuple of float
        ``(I1, I2)`` splits in mA, e.g. from :func:`ratio_levels`.
    select_subsample : int, optional
        Maximum number of non-ROI rows used in the split-selection stage.
        Default ``50000``.

    Raises
    ------
    ValueError
        If *base_mA* is non-positive, *ratios* is empty, or *select_subsample*
        is below 1.

    Notes
    -----
    The chosen split of the most recent evaluation is recorded on the
    optimization object as ``opt._best_current_split`` so callers can report it.
    Progress is logged to the ``"simnibs"`` logger in SimNIBS's own goal-line
    format, keeping live log monitoring functional.
    """
    from simnibs.optimization.tes_flex_optimization.tes_flex_optimization import (
        postprocess_e,
    )

    base = float(base_mA)
    if base <= 0.0:
        raise ValueError(f"base_mA must be positive (was {base})")
    splits = [(float(i1), float(i2)) for i1, i2 in ratios]
    if not splits:
        raise ValueError("ratios must contain at least one (I1, I2) split")
    limit = int(select_subsample)
    if limit < 1:
        raise ValueError(f"select_subsample must be >= 1 (was {limit})")

    index_cache: dict[int, np.ndarray] = {}
    empty = np.zeros((0,), dtype=float)
    # Tracks the split of the best candidate so far, so the winning split (not
    # the last one evaluated) is what gets reported and simulated.
    state: dict = {"best_value": float("inf"), "best_split": None}

    def _combine(e_a, e_b, alpha_a, alpha_b, dirvec, postproc):
        """Post-process the two channels after scaling them to a split."""
        return postprocess_e(
            e=alpha_a * e_a,
            e2=alpha_b * e_b,
            dirvec=dirvec,
            type=postproc,
        )

    def goal_fun(parameters):
        # Mirror SimNIBS's own goal_fun preamble.
        opt.n_test += 1
        opt.electrode_pos = opt.get_electrode_pos_from_array(parameters)
        e = opt.update_field(electrode_pos=opt.electrode_pos, plot=False)
        if e is None:
            # Electrode arrays overlap; SimNIBS's own penalty for this case.
            logger.info(
                f"Goal (ratio): 2.000 (n_sim: {opt.n_sim}, n_test: {opt.n_test})"
            )
            return 2.0
        opt.n_sim += 1

        postproc = opt.e_postproc
        if not isinstance(postproc, (list, tuple)):
            postproc = [postproc] * len(e[0])

        roi_a = np.asarray(e[0][0], dtype=float)
        roi_b = np.asarray(e[1][0], dtype=float)
        roi_dir = opt._goal_dir[0]
        roi_pp = postproc[0]

        has_non_roi = len(e[0]) > 1
        if has_non_roi:
            non_a = np.asarray(e[0][1], dtype=float)
            non_b = np.asarray(e[1][1], dtype=float)
            non_dir = opt._goal_dir[1]
            non_pp = postproc[1]
            n_rows = non_a.shape[0]
            index = _subsample_index(n_rows, limit, index_cache)
            non_a_sub = _take(non_a, index, n_rows)
            non_b_sub = _take(non_b, index, n_rows)
            non_dir_sub = _take(non_dir, index, n_rows)

        # Stage 1: rank the splits, scoring the non-ROI on a subsample only.
        # Iterate from the most balanced split outwards and keep a strict "<"
        # comparison, so an exact tie resolves to the split closest to 1:1
        # rather than to an extreme one (a conservative choice for a
        # stimulation-dose parameter).
        best_value = None
        best_split = _balanced_first(splits)[0]
        for i1, i2 in _balanced_first(splits):
            alpha_a, alpha_b = i1 / base, i2 / base
            roi = _combine(roi_a, roi_b, alpha_a, alpha_b, roi_dir, roi_pp)
            non = (
                _combine(non_a_sub, non_b_sub, alpha_a, alpha_b, non_dir_sub, non_pp)
                if has_non_roi
                else empty
            )
            value = float(objective(roi, non))
            if best_value is None or value < best_value:
                best_value, best_split = value, (i1, i2)

        # Stage 2: re-score the winner on the full non-ROI and return that.
        i1, i2 = best_split
        alpha_a, alpha_b = i1 / base, i2 / base
        roi = _combine(roi_a, roi_b, alpha_a, alpha_b, roi_dir, roi_pp)
        non = (
            _combine(non_a, non_b, alpha_a, alpha_b, non_dir, non_pp)
            if has_non_roi
            else empty
        )
        value = float(objective(roi, non))

        # Remember the split of the BEST candidate seen so far -- not of the
        # most recently evaluated one, which is rarely the winner.
        if value < state["best_value"]:
            state["best_value"] = value
            state["best_split"] = (i1, i2)
            opt._best_current_split = (i1, i2)

        logger.info(
            f"Goal (ratio): {value:.3f} "
            f"(n_sim: {opt.n_sim}, n_test: {opt.n_test}) "
            f"split {i1:.1f}:{i2:.1f} mA"
        )
        return value

    opt.goal_fun = goal_fun
    _install_split_applier(opt, state)
