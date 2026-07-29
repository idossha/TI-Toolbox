"""Flex-search optimization for TI stimulation.

Orchestrates multi-start differential-evolution runs, selects the best
result, and writes a manifest + HTML report.

Public API
----------
run_flex_search
    Run differential-evolution electrode placement optimization.

See Also
--------
tit.opt.config.FlexConfig : Input configuration.
tit.opt.config.FlexResult : Output result container.
tit.opt.flex.builder : SimNIBS object construction used internally.
"""

import logging
import os
import shutil
import time
from pathlib import Path

import numpy as np

from tit.opt.config import FlexConfig, FlexResult
from tit.logger import add_file_handler
from tit.paths import get_path_manager
from . import builder, utils
from .skin_visualization import create_valid_skin_region_visualization

# ---------------------------------------------------------------------------
# Flat-objective diagnostic -- F5
# ---------------------------------------------------------------------------

# Below this standard deviation the recorded objective is treated as
# constant. The built-in "focality" goal collapses to an exact, bit-
# identical value once both t_ROI and t_nonROI are jointly infeasible (see
# _warn_if_objective_flat), so a tight tolerance is deliberate.
_FLATNESS_STD_TOLERANCE = 1e-6
_FLATNESS_MIN_SAMPLES = 5


def _warn_if_objective_flat(
    opt, goal: FlexConfig.OptGoal, logger: logging.Logger, restart_index: int
) -> None:
    """Warn when a completed restart's recorded objective values are flat.

    SimNIBS only appends to ``opt.goal_fun_value`` for its own built-in
    string goals -- a custom Python callable goal (``integral_focality``,
    ``auc_focality``, ``ratio_focality``) bypasses ``compute_goal`` entirely
    (see ``goal_fun`` in the vendored SimNIBS source), so this diagnostic is
    a no-op for those and only ever fires for ``"mean"``, ``"max"``, or
    ``"focality"``.

    A near-constant objective across the many electrode placements SimNIBS
    evaluates during a single differential-evolution run means the
    optimizer has no gradient to follow. For ``goal="focality"`` this is the
    signature of F5 (``tracks/active/mti-focality-core.md``): jointly
    infeasible ``t_ROI``/``t_nonROI`` thresholds against a deep ROI with an
    ``everything_else`` non-ROI pin SimNIBS' 2-point ROC evaluation
    (``measures.ROC``) at a constant value. Weise et al. (2025, *Comput Biol
    Med* 195:110648) report TIS-focality as having the largest run-to-run
    spread of any ``TesFlexOptimization`` application tested, attributed
    there to local minima -- a flat objective landscape is the better
    explanation.

    Parameters
    ----------
    opt : simnibs.optimization.TesFlexOptimization
        The just-completed optimization object.
    goal : FlexConfig.OptGoal
        The configured goal, used only for the warning message.
    logger : logging.Logger
        Logger to warn on.
    restart_index : int
        Zero-based multistart restart index, for the log message.
    """
    try:
        samples = np.asarray(opt.goal_fun_value[0], dtype=float)
    except (TypeError, ValueError, IndexError, AttributeError):
        return
    samples = samples[np.isfinite(samples)]
    if samples.size < _FLATNESS_MIN_SAMPLES:
        return
    spread = float(np.std(samples))
    if spread >= _FLATNESS_STD_TOLERANCE:
        return
    logger.warning(
        "Flex-search restart #%d: the '%s' objective barely varied across "
        "%d evaluations (std=%.3g). This is the signature of jointly "
        "infeasible focality thresholds (t_ROI/t_nonROI) against a deep "
        "ROI with an 'everything_else' non-ROI -- differential evolution "
        "has no gradient to follow (Weise et al. 2025, Comput Biol Med "
        "195:110648). Consider a threshold-free goal instead: "
        "goal='integral_focality', 'auc_focality', or 'ratio_focality'.",
        restart_index + 1,
        str(goal),
        samples.size,
        spread,
    )


def run_flex_search(config: FlexConfig) -> FlexResult:
    """Run differential-evolution electrode placement optimization.

    Uses ``scipy.optimize.differential_evolution`` (via SimNIBS
    ``TesFlexOptimization``) to find electrode positions that maximize
    field strength, peak intensity, or focality in a target ROI.

    Multiple independent restarts (controlled by
    ``config.n_multistart``) are executed sequentially; the best run's
    output is promoted to the base output folder.

    Parameters
    ----------
    config : FlexConfig
        Fully specified optimization configuration including subject,
        ROI definition, electrode geometry, and DE hyperparameters.

    Returns
    -------
    FlexResult
        Optimization outcomes including best montage, objective value,
        and convergence diagnostics.

    See Also
    --------
    FlexConfig : Configuration dataclass for flex-search.
    FlexResult : Result container with per-restart function values.
    tit.opt.ex.ex.run_ex_search : Alternative exhaustive grid search.
    """
    from tit.telemetry import track_operation
    from tit import constants as const

    _validate_flex_inputs(config)
    with track_operation(const.TELEMETRY_OP_FLEX_SEARCH):
        return _run_flex_search_inner(config)


def _validate_flex_inputs(config: FlexConfig) -> None:
    """Validate user-controlled flex-search inputs before telemetry starts."""
    pm = get_path_manager()
    m2m_dir = Path(pm.m2m(config.subject_id))
    if not m2m_dir.is_dir():
        raise ValueError(
            f"SimNIBS m2m directory not found for subject {config.subject_id}: {m2m_dir}. "
            "Run preprocessing/CHARM before flex-search."
        )
    _require_file(
        m2m_dir / f"{config.subject_id}.msh",
        "SimNIBS head mesh",
    )
    if config.cpus is not None and config.cpus < 1:
        raise ValueError("Flex-search cpus must be >= 1.")
    if config.n_multistart < 1:
        raise ValueError("Flex-search n_multistart must be >= 1.")
    if config.min_electrode_distance <= 0:
        raise ValueError("min_electrode_distance must be positive.")
    if config.enable_mapping and not config.eeg_net:
        raise ValueError("enable_mapping requires an EEG net name.")
    if config.enable_mapping:
        _require_file(
            utils.eeg_net_csv_path(pm.eeg_positions(config.subject_id), config.eeg_net),
            "mapped EEG net",
        )
    if config.skin_visualization_net:
        _require_file(Path(config.skin_visualization_net), "skin visualization EEG net")
    if config.avoid_landmark_regions and config.skin_region_margin_mm > 0:
        _require_file(
            Path(pm.eeg_positions(config.subject_id)) / "Fiducials.csv",
            "SimNIBS fiducials",
        )

    for label, roi in (("ROI", config.roi), ("non-ROI", config.non_roi)):
        if roi is None:
            continue
        _validate_roi_input(label, roi)


def _require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise ValueError(f"{description} file not found: {path}")


def _validate_roi_input(label: str, roi) -> None:
    atlas_path = getattr(roi, "atlas_path", None)
    if not atlas_path:
        return

    _require_file(Path(atlas_path), f"{label} atlas")


def _run_flex_search_inner(config: FlexConfig) -> FlexResult:
    """Inner implementation of :func:`run_flex_search` (unwrapped)."""
    from .manifest import write_manifest
    from .utils import generate_label, generate_run_dirname

    pm = get_path_manager()

    # Set up file logging — capture both tit and simnibs output
    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(
        logs_dir, f'flex_search_{time.strftime("%Y%m%d_%H%M%S")}.log'
    )
    logger_name = f"tit.opt.flex.{config.subject_id}"
    add_file_handler(log_file, logger_name=logger_name)
    add_file_handler(log_file, logger_name="simnibs")
    logger = logging.getLogger(logger_name)

    n = config.n_multistart

    # Resolve base output folder
    if config.output_folder:
        base_folder = config.output_folder
    else:
        flex_root = pm.flex_search(config.subject_id)
        os.makedirs(flex_root, exist_ok=True)
        dirname = generate_run_dirname(flex_root)
        base_folder = os.path.join(flex_root, dirname)

    os.makedirs(base_folder, exist_ok=True)
    fvals = np.full(n, float("inf"))

    folders = [os.path.join(base_folder, f"{i:02d}") for i in range(n)]

    # -- Run optimizations --
    for i in range(n):
        opt = builder.build_optimization(config)
        opt.output_folder = folders[i]
        os.makedirs(opt.output_folder, exist_ok=True)
        builder.configure_optimizer_options(opt, config, logger)

        opt.run(cpus=config.cpus)
        fvals[i] = opt.optim_funvalue
        _warn_if_objective_flat(opt, config.goal, logger, i)

    # -- Select best --
    valid_mask = fvals < float("inf")
    if not valid_mask.any():
        logger.error("All optimization runs failed")
        result = FlexResult(
            success=False,
            output_folder=base_folder,
            function_values=fvals.tolist(),
            best_value=float("inf"),
            best_run_index=-1,
        )
        label = generate_label(config)
        write_manifest(base_folder, config, result, label)
        return result

    best_idx = int(np.argmin(fvals))
    logger.info(f"Best run: #{best_idx + 1} (value={fvals[best_idx]:.6f})")

    # -- Promote best to base folder --
    best_folder = folders[best_idx]
    for item in os.listdir(best_folder):
        src = os.path.join(best_folder, item)
        dst = os.path.join(base_folder, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # -- Cleanup temp subdirs --
    for folder in folders:
        if os.path.isdir(folder):
            shutil.rmtree(folder)

    # -- Valid skin-region visualization --
    create_valid_skin_region_visualization(config, base_folder, logger)

    # -- Report --
    builder.generate_report(config, n, fvals, best_idx, base_folder, logger)

    result = FlexResult(
        success=True,
        output_folder=base_folder,
        function_values=fvals.tolist(),
        best_value=float(fvals[best_idx]),
        best_run_index=best_idx,
    )

    # -- Write manifest --
    label = generate_label(config)
    write_manifest(base_folder, config, result, label)

    return result
