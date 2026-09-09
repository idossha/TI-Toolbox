"""CLI entry point for the analyzer package.

Usage::

    simnibs_python -m tit.analyzer config.json

The JSON config is parsed and dispatched to either single-subject
(:class:`~tit.analyzer.Analyzer`) or group
(:func:`~tit.analyzer.run_group_analysis`) analysis depending on the
``"mode"`` field (``"single"`` or ``"group"``).
"""

import time
import json
import logging
import os
import sys
from contextlib import nullcontext

from tit.analyzer.config import AnalysisMode, AnalysisType, AnalyzerConfig
from tit.paths import get_path_manager


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job."""
    try:
        from tit.jobs import locks
        from tit.jobs.runner import ENV_JOB_ID
    except ImportError:
        return nullcontext()
    job_id = os.environ.get(ENV_JOB_ID)
    if not job_id:
        return nullcontext()
    requests = locks.keys_for(kind, subject_ids, config_dict)
    return locks.hold(get_path_manager().project_dir, job_id, requests)


def _build_config_legacy(data: dict) -> AnalyzerConfig:
    """Old, pre-``AnalyzerConfig`` dict layout -- read verbatim.

    Kept for one release: a caller sending the flat dict this entry point
    accepted before :class:`~tit.analyzer.config.AnalyzerConfig` existed
    (including the plural ``"regions"`` alias, which the dataclass itself
    never round-trips -- see its Notes) still works.
    """
    return AnalyzerConfig(
        mode=data.get("mode", "single"),
        subject_id=data.get("subject_id"),
        subject_ids=data.get("subject_ids", []),
        simulation=data.get("simulation", ""),
        space=data.get("space", "mesh"),
        tissue_type=data.get("tissue_type", "GM"),
        analysis_type=data.get("analysis_type", "spherical"),
        field=data.get("field"),
        center=data.get("center"),
        radius=data.get("radius"),
        coordinate_space=data.get("coordinate_space", "subject"),
        mask_path=data.get("mask_path"),
        atlas=data.get("atlas"),
        region=data.get("regions") or data.get("region"),
        output_dir=data.get("output_dir"),
        visualize=data.get("visualize", True),
    )


def _build_config(data: dict) -> AnalyzerConfig:
    """Build an :class:`AnalyzerConfig`, preferring ``deserialize_config``.

    Falls back to :func:`_build_config_legacy` when *data* does not
    round-trip through the typed path -- see the module-level "old dict
    layout for one release" note.
    """
    from tit.config_io import deserialize_config

    try:
        return deserialize_config(AnalyzerConfig, data)
    except (TypeError, ValueError, KeyError) as exc:
        logging.getLogger("tit.analyzer").debug(
            f"deserialize_config(AnalyzerConfig, ...) failed ({exc}); "
            "falling back to the legacy dict layout"
        )
        return _build_config_legacy(data)


def main() -> None:
    """Parse config JSON and dispatch to single or group analysis."""
    from tit.logger import add_stream_handler, setup_logging
    from tit.jobs import events

    setup_logging("INFO")
    add_stream_handler("tit.analyzer")
    logger = logging.getLogger("tit.analyzer")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))

    try:
        config = _build_config(data)
    except (TypeError, ValueError) as exc:
        print(f"Invalid analyzer config: {exc}", file=sys.stderr)
        sys.exit(1)

    subject_ids = [config.subject_id] if config.subject_id else config.subject_ids
    lock_cm = _hold_locks("analyzer", subject_ids, data)

    exit_code = 1
    try:
        with lock_cm:
            started = time.time()
            events.emit_stage(config.mode.value)
            print(f"Starting {config.mode.value} analysis...", flush=True)

            if config.analysis_type is AnalysisType.SUBCORTICAL:
                # Known gap: AnalyzerConfig models this shape but the underlying
                # single/group analysis functions only branch on spherical/cortical
                # today (tit.analyzer.analyzer / tit.analyzer.group, not owned by
                # this track) -- a clear error beats a silent no-op.
                print(
                    "analysis_type='subcortical' is not implemented by the "
                    "analyzer runner yet.",
                    file=sys.stderr,
                )
            elif config.mode is AnalysisMode.GROUP:
                _emit_group_artifacts(_run_group(config))
                exit_code = 0
            else:
                _run_single(config)
                _emit_analysis_artifacts(config, started)
                exit_code = 0

            print(
                "✓ Analysis complete." if exit_code == 0 else "✗ Analysis failed.",
                flush=True,
            )
            events.emit_result({"mode": config.mode.value, "success": exit_code == 0})
    except Exception as exc:  # noqa: BLE001 - report and exit non-zero
        logger.error(f"Analysis failed: {exc}", exc_info=True)
        exit_code = 1
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


def _emit_group_artifacts(result) -> None:
    """Report the two files a group run itself writes: the summary CSV and its plot.

    Named rather than walked (which is how the single-subject branch does it): a group run
    writes each subject's own analysis into that subject's own directory, and only
    ``GroupResult``'s two paths belong to the group job. Without this a finished group
    analysis reported ``artifacts: []`` -- the same hole as the three silent runners.
    """
    try:
        from tit.jobs import events

        summary = getattr(result, "summary_csv_path", None)
        if summary:
            events.emit_artifact(str(summary), kind="csv", label="group summary")
        plot = getattr(result, "comparison_plot_path", None)
        if plot:
            events.emit_artifact(str(plot), kind="pdf", label="group comparison")
    except Exception as exc:  # noqa: BLE001 - bookkeeping never fails a finished run
        print(f"artifact listing skipped: {exc}", flush=True)


def _run_group(config: AnalyzerConfig):
    """Dispatch group analysis from a parsed :class:`AnalyzerConfig`.

    Returns the :class:`~tit.analyzer.group.GroupResult` so :func:`main` can report the
    files it wrote.
    """
    from tit.analyzer import run_group_analysis

    print(
        f"Group analysis: {len(config.subject_ids)} subjects, "
        f"space={config.space.value}, type={config.analysis_type.value}",
        flush=True,
    )

    return run_group_analysis(
        subject_ids=config.subject_ids,
        simulation=config.simulation,
        space=config.space.value,
        tissue_type=config.tissue_type,
        analysis_type=config.analysis_type.value,
        center=tuple(config.center) if config.center else None,
        radius=config.radius,
        coordinate_space=config.coordinate_space.value,
        atlas=config.atlas,
        region=config.region,
        visualize=config.visualize,
        output_dir=config.output_dir,
        field=config.field,
        mask_path=config.mask_path,
    )


def analysis_artifact_root(config: AnalyzerConfig, pm) -> str | None:
    """The directory to list this run's outputs from.

    ``config.output_dir`` wins when it is set -- :meth:`Analyzer._resolve_output_dir`
    honours it verbatim, so ``Analyses/<Space>/`` holds nothing for such a run and
    listing that instead reported zero artifacts for a run that had just written five
    files.
    """
    if config.output_dir:
        return config.output_dir
    if not config.subject_id or not config.simulation:
        return None
    return pm.analysis_dir(config.subject_id, config.simulation, config.space.value)


def _warn_if_undiscoverable(config: AnalyzerConfig, pm) -> None:
    """Say so, in one line, when this run's output cannot be attributed to a simulation.

    ``output_dir`` stays free (it is a documented argument of the public
    :class:`~tit.analyzer.Analyzer` API, used by scripts that analyse into a scratch
    directory), and :func:`tit.catalog.analyses` now finds an analysis anywhere *under
    the simulation*. Outside it there is nothing left to key on -- the catalog is
    indexed by subject and simulation -- so the run is invisible to the app and the
    person who chose that directory is the only one who can know why.
    """
    if not (config.output_dir and config.subject_id and config.simulation):
        return
    try:
        sim_dir = os.path.realpath(pm.simulation(config.subject_id, config.simulation))
        out = os.path.realpath(config.output_dir)
    except Exception:  # noqa: BLE001 - advisory only
        return
    if os.path.commonpath([sim_dir, out]) != sim_dir:
        print(
            f"note: output_dir {config.output_dir} is outside {sim_dir}, so this "
            "analysis will not be listed under the simulation in the app "
            "(its files are still written, and the job reports them as artifacts).",
            flush=True,
        )


def _emit_analysis_artifacts(config: AnalyzerConfig, started: float) -> None:
    """List the files this analysis wrote (the analyzer decides its own output dir)."""
    try:
        from tit.jobs.events import emit_new_artifacts
        from tit.paths import get_path_manager

        pm = get_path_manager()
        root = analysis_artifact_root(config, pm)
        if not root:
            return
        _warn_if_undiscoverable(config, pm)
        emit_new_artifacts(root, started)
    except (
        Exception
    ) as exc:  # pragma: no cover - bookkeeping must never fail a finished run
        print(f"artifact listing skipped: {exc}", flush=True)


def _run_single(config: AnalyzerConfig) -> None:
    """Dispatch single-subject analysis from a parsed :class:`AnalyzerConfig`."""
    from tit.analyzer import Analyzer

    print(
        f"Single analysis: subject={config.subject_id}, "
        f"sim={config.simulation}, space={config.space.value}, "
        f"type={config.analysis_type.value}",
        flush=True,
    )

    if config.analysis_type is AnalysisType.MASK:
        from tit.opt.masks import validate_mask

        validate_mask(config.mask_path)

    analyzer = Analyzer(
        subject_id=config.subject_id,
        simulation=config.simulation,
        space=config.space.value,
        tissue_type=config.tissue_type,
        output_dir=config.output_dir,
        field=config.field,
    )

    if config.analysis_type is AnalysisType.SPHERICAL:
        analyzer.analyze_sphere(
            center=tuple(config.center),
            radius=config.radius,
            coordinate_space=config.coordinate_space.value,
            visualize=config.visualize,
        )
    elif config.analysis_type is AnalysisType.MASK:
        analyzer.analyze_mask(
            mask_path=config.mask_path,
            coordinate_space=config.coordinate_space.value,
            visualize=config.visualize,
        )
    elif config.analysis_type is AnalysisType.CORTICAL:
        analyzer.analyze_cortex(
            atlas=config.atlas,
            region=config.region or "",
            visualize=config.visualize,
        )


if __name__ == "__main__":
    main()
