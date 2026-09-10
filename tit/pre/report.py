"""Entry point: ``simnibs_python -m tit.pre.report config.json``

Builds one consolidated per-subject preprocessing report.

A report is an **attachment of the job that produced it, never a job of its own**
(maintainer, 2026-09-07). :func:`tit.jobs.plans.plan_preprocessing` therefore plans
no trailing ``report`` job: :meth:`tit.jobs.manager.JobManager._attach_pre_report`
calls :func:`build_report` in-process once the last preprocessing job for a subject
succeeds, and records the result as an artifact on that job. The ``report`` job kind
stays in the frozen wire contract (and in ``MODULE_FOR_KIND``, so this module remains
runnable by hand) but nothing plans or submits one.

Why this exists alongside ``tit.pre``'s own per-stage report
--------------------------------------------------------------
Every stage job in a ``pre`` group (``G1``..``G6``) already writes its own HTML
report as a side effect of :func:`tit.pre.structural.run_pipeline` (see
``tit/pre/__main__.py``'s ``_logger_callback``) -- but that report only covers
the *one* flag that stage's narrowed :class:`~tit.pre.config.PreprocessConfig`
left set (``_stage_config`` in :mod:`tit.jobs.plans` forces every other flag to
``False``). A group running DICOM conversion + charm + tissue analysis therefore
produces three separate, each-incomplete reports, and whichever stage finishes
last "wins" the newest-report fallback the UI's job-report pane uses for a
``report``-kind job (``desktop/src/renderer/app/jobs-rail/ReportPane.tsx``).

This module instead reads the group's *un-narrowed* config -- every flag the
caller actually requested for this subject, exactly as :func:`plan_preprocessing`
decided which stage jobs to plan in the first place -- and builds one report
covering every one of them. It does no science of its own: by the time this job
runs (the scheduler only starts a job once every id in its own ``after`` list has
reached a non-failed terminal state -- see ``tit/jobs/scheduler.py``'s
``FAILED_LIKE_STATES`` cascade), every stage it lists already ran to completion,
so every step here is reported ``"completed"`` and :meth:`scan_for_data
<tit.reporting.generators.preprocessing.PreprocessingReportGenerator.scan_for_data>`
picks up the real output paths those stages left on disk.

See Also
--------
tit.jobs.plans.plan_preprocessing : Plans this job's config and ``after`` list.
tit.pre.structural.run_pipeline : The near-identical per-stage report-building
    loop this module's ``_STEPS`` table mirrors, so the step names/descriptions
    read identically wherever a preprocessing report shows them.
tit.reporting.generators.preprocessing.PreprocessingReportGenerator : Report
    builder used here and by ``run_pipeline``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.paths import get_path_manager
from tit.pre.config import PreprocessConfig, migrate_legacy_keys

#: (PreprocessConfig flag name, step name, description) -- one row per flag that
#: contributes a processing step to the report, in the same order and with the
#: same labels as tit.pre.structural.run_pipeline's own report-building loop
#: (lines building each PreprocessingReportGenerator.add_processing_step call).
#: create_m2m contributes two steps (charm proper, then subject_atlas), matching
#: that loop exactly.
_STEPS: tuple[tuple[str, str, str], ...] = (
    ("convert_dicom", "DICOM Conversion", "Convert DICOM files to NIfTI format"),
    ("create_m2m", "SimNIBS charm", "Create head mesh model for simulations"),
    ("create_m2m", "Subject Atlas Segmentation", "Generate atlas-based parcellation"),
    (
        "run_fastsurfer",
        "FastSurfer segmentation",
        "Deep-learning cortical and subcortical parcellation",
    ),
    ("run_freesurfer", "FreeSurfer", "Selected reconstruction and subregion steps"),
    ("run_tissue_analysis", "Tissue Analysis", "Tissue segmentation and analysis"),
    ("run_qsiprep", "QSIPrep", "Diffusion MRI preprocessing"),
    ("run_qsirecon", "QSIRecon", "Diffusion MRI reconstruction"),
    (
        "extract_dti",
        "DTI Tensor Extraction",
        "Extract DTI tensors for anisotropic conductivity",
    ),
)


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


def build_report(
    config: PreprocessConfig,
    subject_id: str,
    *,
    logger: logging.Logger | None = None,
) -> str:
    """Write one consolidated preprocessing report for *subject_id*; return its path.

    In-process and side-effect-free apart from the HTML it writes, so the job manager can
    call it as a post-success attachment of the subject's last preprocessing job
    (:meth:`tit.jobs.manager.JobManager._attach_pre_report`) instead of scheduling a
    separate ``report`` job. *config*'s step flags decide which steps the report lists --
    pass the union of the flags the group's stage jobs actually ran.
    """
    log = logger or logging.getLogger("tit.pre.report")

    from tit.reporting import PreprocessingReportGenerator

    report_gen = PreprocessingReportGenerator(
        project_dir=get_path_manager().project_dir,
        subject_id=subject_id,
    )

    steps_added = 0
    for flag_name, step_name, description in _STEPS:
        if not getattr(config, flag_name):
            continue
        report_gen.add_processing_step(
            step_name=step_name,
            description=description,
            status="completed",
        )
        steps_added += 1

    if steps_added == 0:
        log.warning(
            f"No preprocessing steps were requested for subject "
            f"{subject_id}; writing an empty report."
        )

    report_gen.scan_for_data()
    return str(report_gen.generate())


def main() -> None:
    """Build one consolidated preprocessing report from a JSON config."""
    if len(sys.argv) < 2:
        sys.exit("Usage: simnibs_python -m tit.pre.report <config.json>")

    config_path = sys.argv[1]
    try:
        with open(config_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Could not read config file {config_path}: {exc}")

    for key in ("project_dir", "subject_ids"):
        if key not in data:
            sys.exit(f"Config file {config_path} is missing required key: {key}")

    from tit.logger import setup_logging, add_stream_handler
    from tit.jobs import events

    setup_logging()
    add_stream_handler("tit.pre.report")
    logger = logging.getLogger("tit.pre.report")

    get_path_manager(data.pop("project_dir"))

    data = migrate_legacy_keys(data)
    try:
        config = deserialize_config(PreprocessConfig, data)
    except (TypeError, ValueError, KeyError) as exc:
        sys.exit(f"Invalid preprocessing config: {exc}")

    if len(config.subject_ids) != 1:
        sys.exit(
            "tit.pre.report builds one subject's report at a time; got "
            f"subject_ids={config.subject_ids!r}"
        )
    subject_id = config.subject_ids[0]

    lock_cm = _hold_locks("report", config.subject_ids, data)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("report")

            report_path = build_report(config, subject_id, logger=logger)
            logger.info(f"Report generated: {report_path}")
            events.emit_artifact(str(report_path), kind="report")

            exit_code = 0
            events.emit_result({"success": True, "report_path": str(report_path)})
    except Exception as exc:  # noqa: BLE001 - report, don't crash the process silently
        logger.error(f"Report generation failed: {exc}")
        events.emit_result({"success": False, "error": str(exc)})
        exit_code = 1
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
