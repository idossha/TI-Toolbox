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
import re
import shutil
import time
from pathlib import Path

import numpy as np

from tit.cpu import job_cpus
from tit.opt.config import FlexConfig, FlexResult, _as_list
from tit.logger import add_file_handler, stage_heartbeat
from tit.paths import get_path_manager
from . import builder, utils
from .skin_visualization import create_valid_skin_region_visualization


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
        ``success``, ``output_folder`` (the run directory under the
        subject's ``flex-search/``), per-restart ``function_values``,
        ``best_value`` and ``best_run_index``.

    Raises
    ------
    ValueError
        If the subject's m2m directory or head mesh is missing, a
        referenced ROI/atlas/EEG-net file is missing, ``cpus`` or
        ``n_multistart`` is below 1, ``min_electrode_distance`` is not
        positive, ``enable_mapping`` is set without ``eeg_net``, or an
        ``"ellipse"`` electrode has unequal dimensions (flex-search
        supports circular electrodes only).

    Notes
    -----
    When every restart fails the function does not raise: it returns a
    :class:`FlexResult` with ``success=False``, ``best_value=inf`` and
    ``best_run_index=-1``.  Always check ``result.success``.

    Examples
    --------
    >>> from tit.opt import FlexConfig, run_flex_search
    >>> cfg = FlexConfig(
    ...     subject_id="ernie", goal="mean", postproc="max_TI", current_mA=1.0,
    ...     electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    ...     roi=FlexConfig.SphericalROI(x=-35.0, y=5.0, z=5.0, radius=10.0, use_mni=True),
    ...     n_multistart=3, output_folder="insula_mean",
    ... )
    >>> res = run_flex_search(cfg)  # doctest: +SKIP
    >>> res.success, res.best_run_index, len(res.function_values)  # doctest: +SKIP
    (True, 1, 3)

    See Also
    --------
    FlexConfig : Configuration dataclass for flex-search.
    FlexResult : Result container with per-restart function values.
    tit.opt.ex.ex.run_ex_search : Alternative exhaustive grid search.
    """
    from tit.telemetry import track_operation
    from tit import constants as const

    from tit.opt.masks import validate_mask_paths

    validate_mask_paths(config)
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
    """Check ``roi.atlas_path`` exists on disk -- scalar or a region-union list.

    ``AtlasROI``/``SubcorticalROI.atlas_path`` is ``str | list[str]`` (PR #130's ROI
    unions: one entry per region, often repeating the same file for several labels
    within one hemisphere/atlas -- see the maintainer's own failing config,
    ``atlas_path: [path, path, path]`` for three DK40 labels). ``Path(atlas_path)``
    on a list raises ``TypeError: expected str, bytes or os.PathLike object, not
    list`` before any real validation runs (job ``c45cb53b0e864d02``); ``_as_list``
    plus de-duplication checks every distinct file once, matching how
    :mod:`tit.opt.flex.utils`/``builder`` already read this same field downstream.
    """
    atlas_path = getattr(roi, "atlas_path", None)
    if not atlas_path:
        return

    for path in dict.fromkeys(_as_list(atlas_path)):
        _require_file(Path(path), f"{label} atlas")


def confirm_roi(config, pm, out_dir: str) -> list:
    """Write the ROI plate for this search's volume target, in whatever space.

    Subject space is not exempt: an atlas label with detached islands or a mask
    off by a slice fails the same way an MNI transform does, and neither is
    visible in any number the search produces.
    """
    from tit.roi_confirmation import confirm_rois

    roi = getattr(config, "roi", None)
    if roi is None or not getattr(roi, "atlas_path", None):
        return []
    space = str(getattr(roi, "atlas_space", "subject")).lower()
    paths = roi.atlas_path if isinstance(roi.atlas_path, list) else [roi.atlas_path]
    labels = roi.label if isinstance(roi.label, list) else [roi.label]
    if len(paths) == 1 and len(labels) > 1:
        paths = paths * len(labels)
    entries = [
        {"atlas_path": path, "label": label, "space": space}
        for path, label in zip(paths, labels)
    ]
    return confirm_rois(entries, m2m=pm.m2m(config.subject_id), out_dir=out_dir)


#: The name this had while the check was for MNI ROIs only.
confirm_mni_roi = confirm_roi


def _confirm_roi_message(config) -> str:
    """The console line for :func:`confirm_roi`, naming the slow part when there is one."""
    roi = getattr(config, "roi", None)
    space = str(getattr(roi, "atlas_space", "subject") or "subject").lower()
    if roi is not None and getattr(roi, "atlas_path", None) and space == "mni":
        return "Confirming ROI placement (warping the MNI atlas into subject space)"
    return "Confirming ROI placement"


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

    # The ROI is resolved into this subject BEFORE any optimisation runs, and
    # leaves a plate and a JSON behind: a misplaced ROI is the one error here
    # that no later number can reveal (tit/roi_confirmation.py). An MNI atlas
    # label is warped into subject space here (1-2 min under emulation) with
    # nothing else to say meanwhile, so the heartbeat keeps the console alive.
    with stage_heartbeat(logger, _confirm_roi_message(config)):
        confirm_roi(config, pm, base_folder)

    fvals = np.full(n, float("inf"))

    folders = [os.path.join(base_folder, f"{i:02d}") for i in range(n)]
    # Winning channel current split per restart; stays None unless the
    # optional current-ratio search ran (see objectives.install_ratio_search).
    splits: list[tuple[float, float] | None] = [None] * n

    # -- Run optimizations --
    for i in range(n):
        opt = builder.build_optimization(config)
        opt.output_folder = folders[i]
        os.makedirs(opt.output_folder, exist_ok=True)
        builder.configure_optimizer_options(opt, config, logger)

        recorder = getattr(opt, "_candidate_recorder", None)
        try:
            # An explicit `cpus` wins; otherwise the CPU budget the plan admitted this job
            # with (TIT_JOB_CPUS), so SimNIBS gets the number the plan panel showed rather
            # than its own internal default. See `tit.cpu.job_cpus`.
            opt.run(cpus=config.cpus or job_cpus())
            if recorder is not None:
                recorder.finalize(opt)
        finally:
            if recorder is not None:
                recorder.close()
            # Keep every restart's compact records before winner promotion
            # removes the temporary solver directories.
            history = Path(base_folder) / "candidate_history" / f"{i:02d}"
            for name in (
                "candidates.csv",
                "candidate_geometry.jsonl",
                "candidate_manifest.json",
            ):
                source = Path(folders[i]) / name
                if source.is_file():
                    history.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(history / name))
        # A finite optimizer penalty is not evidence of a valid montage. The
        # recorder ties the returned optimum to its successfully evaluated pose.
        if (
            getattr(opt, "_accepted_candidate_valid", False) is True
            and getattr(opt, "_accepted_candidate_id", None)
            and np.isfinite(opt.optim_funvalue)
        ):
            fvals[i] = opt.optim_funvalue
        else:
            logger.warning("Restart %d did not accept a recorded valid candidate", i)
        splits[i] = getattr(opt, "_best_current_split", None)

    # -- Select best --
    valid_mask = np.isfinite(fvals)
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

    best_idx = int(np.argmin(np.where(valid_mask, fvals, np.inf)))
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

    # -- Clean up the "Goal:" line in summary.txt --
    # For callable goals (e.g. focality_tf), SimNIBS logs repr(opt.goal),
    # which prints the raw closure object instead of a readable label.
    summary_path = os.path.join(base_folder, "summary.txt")
    if os.path.isfile(summary_path):
        with open(summary_path, "r") as f:
            summary_text = f.read()
        summary_text = re.sub(
            r"^Goal:(\s*).*$",
            lambda m: f"Goal:{m.group(1)}{config.goal.value}",
            summary_text,
            count=1,
            flags=re.MULTILINE,
        )
        with open(summary_path, "w") as f:
            f.write(summary_text)

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
    write_manifest(base_folder, config, result, label, current_split=splits[best_idx])

    return result
