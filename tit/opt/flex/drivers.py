"""Multi-step flex-search drivers: adaptive focality and Pareto threshold sweeps.

Extracted from the Qt orchestration logic in ``tit.gui.flex_search_tab``
(``_start_mean_optimization`` / ``_run_adaptive_focality_step2`` /
``_run_pareto_sweep_step2`` and friends), with two bugs from that
implementation fixed along the way:

1. **Achievable intensity from the run's own result, not a filesystem scan.**
   The Qt version's fallback path
   (``_read_mean_intensity_from_manifest``) scanned the subject's whole
   flex-search output directory, newest folder first, for *any* manifest
   with ``goal="mean"`` -- which can silently pick up a stale mean run
   from an earlier session, or (if multiple runs are ever executed
   concurrently against the same subject) another run's manifest
   entirely. Both drivers here read
   :attr:`~tit.opt.config.FlexResult.best_value` directly off the
   :class:`~tit.opt.config.FlexResult` their own step-1 call returned --
   there is no directory scan and nothing else's output can be mistaken
   for it.
2. **Every subject actually gets its Pareto sweep.** The Qt version's
   ``_finalize_pareto_sweep`` never called ``_process_next_subject``, so a
   multi-subject GUI session silently stopped after the first subject's
   sweep completed (``_run_adaptive_focality_step2`` had the equivalent
   continuation and did not have this bug). That whole multi-subject loop
   does not exist here: the job system submits one :class:`FlexConfig`
   (one ``subject_id``) per job (``tit.jobs.kinds`` maps
   ``flex``/``flex_adaptive``/``flex_pareto`` one-for-one to a single
   ``simnibs_python -m tit.opt.flex`` invocation), so a multi-subject
   request is already N independent jobs at the point these drivers run --
   each one runs its subject's sweep to completion regardless of what any
   other subject's job does.

Public API
----------
run_adaptive_focality
    Two-step: a ``"mean"`` calibration run, then one ``"focality"`` run
    with thresholds computed as percentages of the achievable intensity.
run_pareto_sweep
    A ``"mean"`` calibration run followed by a full (roi_pct, nonroi_pct)
    threshold grid of ``"focality"`` runs.

See Also
--------
tit.opt.config.FlexConfig.AdaptiveFocalityConfig : Adaptive driver's config.
tit.opt.config.FlexConfig.ParetoSweepConfig : Pareto driver's config.
tit.opt.flex.flex.run_flex_search : The single-run primitive both drivers
    call for every step.
tit.opt.flex.pareto : Grid computation, plot/JSON persistence, and
    best-run promotion shared with the legacy Qt orchestration.
tit.opt.flex.__main__ : Dispatches to these by ``FlexConfig.mode``.
"""

from __future__ import annotations

import copy
import os

from tit.opt.config import FlexConfig, FlexResult


def _achievable_intensity(result: FlexResult) -> float:
    """Achievable mean ROI intensity (V/m) from a completed ``goal="mean"`` run.

    SimNIBS's differential-evolution minimizer stores the *negative* of the
    mean-field objective in ``best_value`` (it minimizes; the GUI's own
    real-time parser and manifest fallback both took ``abs()`` for the same
    reason -- see this module's docstring), so the sign is normalised here.

    Raises
    ------
    ValueError
        If the mean run did not report a usable (nonzero) intensity.
    """
    intensity = abs(result.best_value)
    if intensity <= 0:
        raise ValueError(
            "Could not determine achievable ROI intensity from the mean "
            f"optimization run (best_value={result.best_value!r}, "
            f"output_folder={result.output_folder!r})"
        )
    return intensity


def _step_config(
    config: FlexConfig,
    *,
    goal: FlexConfig.OptGoal,
    thresholds: str | None = None,
    output_folder: str | None = None,
) -> FlexConfig:
    """A shallow copy of *config* set up for one single-run step.

    Mirrors ``tit.opt.flex.pareto.build_focality_config``'s shallow-copy
    style: fields not touched here (ROI, non-ROI, electrode geometry, DE
    hyperparameters, ...) come through unchanged, and -- like that
    function -- this does not re-run ``__post_init__`` validation, so the
    driver-only fields are simply cleared rather than re-validated.
    """
    step = copy.copy(config)
    step.goal = goal
    step.mode = FlexConfig.Mode.FLEX
    step.adaptive = None
    step.pareto = None
    step.thresholds = thresholds
    step.output_folder = output_folder
    return step


def run_adaptive_focality(config: FlexConfig) -> FlexResult:
    """Run step 1 (mean) then step 2 (focality with adaptive thresholds).

    Parameters
    ----------
    config : FlexConfig
        ``config.mode`` should be ``"flex_adaptive"`` and ``config.goal``
        must be ``"focality"`` (enforced by
        :meth:`FlexConfig.__post_init__`); ``config.adaptive`` supplies
        *roi_percentage*/*nonroi_percentage* (defaulted to 80/20 if
        ``None``).

    Returns
    -------
    FlexResult
        The step-2 focality run's result, unless step 1 fails -- in which
        case that (failed) mean-run result is returned unchanged and step
        2 never starts.

    See Also
    --------
    tit.opt.flex.flex.run_flex_search : The single-run primitive used for
        both steps.
    FlexConfig.AdaptiveFocalityConfig : The threshold-percentage config.
    """
    from tit.jobs import events

    from tit.opt.flex.flex import run_flex_search

    adaptive = config.adaptive or FlexConfig.AdaptiveFocalityConfig()

    events.emit_stage("mean_optimization", i=0, n=2)
    mean_result = run_flex_search(_step_config(config, goal=FlexConfig.OptGoal.MEAN))
    events.emit_progress(50.0)
    if not mean_result.success:
        return mean_result

    achievable = _achievable_intensity(mean_result)
    nonroi_threshold = achievable * adaptive.nonroi_percentage / 100.0
    roi_threshold = achievable * adaptive.roi_percentage / 100.0

    events.emit_stage("focality_optimization", i=1, n=2)
    result = run_flex_search(
        _step_config(
            config,
            goal=FlexConfig.OptGoal.FOCALITY,
            thresholds=f"{nonroi_threshold:.4f},{roi_threshold:.4f}",
            output_folder=config.output_folder,
        )
    )
    events.emit_progress(100.0)
    return result


def run_pareto_sweep(config: FlexConfig) -> FlexResult:
    """Run the mean calibration, then every (roi_pct, nonroi_pct) combination.

    Persists ``pareto_results.json`` and a scatter-plot PNG under the
    sweep's base output folder (:func:`tit.opt.flex.pareto.save_results`),
    which also promotes the best-scoring point's optimizer output into
    that folder and removes the per-point numbered subdirectories.

    Parameters
    ----------
    config : FlexConfig
        ``config.mode`` should be ``"flex_pareto"`` and ``config.goal``
        must be ``"focality"`` (enforced by
        :meth:`FlexConfig.__post_init__`); ``config.pareto`` supplies
        *roi_pcts*/*nonroi_pcts* (defaulted if ``None``).
        ``config.output_folder``, if set, names the sweep's base folder;
        otherwise one is auto-generated under the subject's flex-search
        directory.

    Returns
    -------
    FlexResult
        A summary over the whole sweep: ``success`` is True if at least
        one grid point completed, ``output_folder`` is the sweep's base
        folder (post-promotion), ``function_values`` lists every
        completed point's focality score, and ``best_value``/
        ``best_run_index`` name the best-scoring point (most negative
        ``focality_score``, matching ``tit.opt.flex.pareto``'s own
        best-run convention) and its position in run order.

    See Also
    --------
    tit.opt.flex.pareto : Grid computation and persistence helpers used
        here.
    FlexConfig.ParetoSweepConfig : The threshold-percentage-grid config.
    """
    from tit.jobs import events

    from tit.opt.flex.flex import run_flex_search
    from tit.opt.flex.pareto import (
        ParetoSweepConfig as _InternalParetoConfig,
        ParetoSweepResult,
        build_focality_config,
        compute_sweep_grid,
        save_results,
    )
    from tit.opt.flex.utils import generate_run_dirname
    from tit.paths import get_path_manager

    pareto = config.pareto or FlexConfig.ParetoSweepConfig()

    pm = get_path_manager()
    flex_root = pm.flex_search(config.subject_id)
    os.makedirs(flex_root, exist_ok=True)
    base_folder = config.output_folder or os.path.join(
        flex_root, generate_run_dirname(flex_root)
    )
    os.makedirs(base_folder, exist_ok=True)

    n_points = len(pareto.roi_pcts) * len(pareto.nonroi_pcts)
    total_steps = n_points + 1

    events.emit_stage("mean_optimization", i=0, n=total_steps)
    mean_result = run_flex_search(_step_config(config, goal=FlexConfig.OptGoal.MEAN))
    events.emit_progress(100.0 / total_steps)
    if not mean_result.success:
        return FlexResult(
            success=False,
            output_folder=mean_result.output_folder,
            function_values=[],
            best_value=mean_result.best_value,
            best_run_index=-1,
        )

    achievable = _achievable_intensity(mean_result)
    points = compute_sweep_grid(
        pareto.roi_pcts, pareto.nonroi_pcts, achievable, base_folder
    )
    sweep_config = _InternalParetoConfig(
        roi_pcts=pareto.roi_pcts,
        nonroi_pcts=pareto.nonroi_pcts,
        achievable_roi_mean=achievable,
        base_output_folder=base_folder,
    )
    sweep_result = ParetoSweepResult(config=sweep_config, points=points)

    for idx, point in enumerate(points):
        events.emit_stage(
            f"sweep_point_{idx + 1}_of_{n_points}", i=idx + 1, n=total_steps
        )
        os.makedirs(point.output_folder, exist_ok=True)
        point.status = "running"
        point_result = run_flex_search(build_focality_config(config, point))
        if point_result.success:
            point.focality_score = point_result.best_value
            point.status = "done"
        else:
            point.status = "failed"
        events.emit_progress(100.0 * (idx + 2) / total_steps)

    json_path, plot_path = save_results(sweep_result, base_folder)
    events.emit_artifact(json_path, kind="json", label="pareto_results")
    events.emit_artifact(plot_path, kind="png", label="pareto_sweep_plot")

    done = [p for p in points if p.status == "done" and p.focality_score is not None]
    best_value = 0.0
    best_index = -1
    if done:
        best = min(done, key=lambda p: p.focality_score)
        best_value = best.focality_score
        best_index = points.index(best)

    return FlexResult(
        success=bool(done),
        output_folder=base_folder,
        function_values=[p.focality_score for p in done],
        best_value=best_value,
        best_run_index=best_index,
    )
