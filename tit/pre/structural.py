#!/usr/bin/env simnibs_python
"""
Preprocessing pipeline orchestration.

This module contains the top-level ``run_pipeline`` function that drives
all preprocessing steps for one or more subjects, including DICOM
conversion, FreeSurfer recon-all, SimNIBS CHARM, tissue analysis, DWI
preprocessing (QSIPrep/QSIRecon), DTI tensor extraction, and subcortical
segmentation.

Public API
----------
run_pipeline
    Run the full preprocessing pipeline for one or more subjects.

See Also
--------
tit.pre : Package-level overview and convenience re-exports.
"""

import os
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

from tit import constants as const
from tit.paths import get_path_manager

from .charm import run_charm, run_subject_atlas
from .dicom2nifti import run_dicom_to_nifti
from .qsi import extract_dti_tensor, run_qsiprep, run_qsirecon
from .recon_all import run_recon_all, run_subcortical_segmentations
from .tissue_analyzer import run_tissue_analysis
from .preflight import (
    STEP_CHARM,
    STEP_DICOM,
    STEP_DTI,
    STEP_QSIPREP,
    STEP_QSIRECON,
    STEP_RECON_ALL,
    existing_outputs_for_step,
    find_missing_preprocessing_inputs,
    remove_preprocessing_output,
)
from .utils import (
    CommandRunner,
    PreprocessCancelled,
    PreprocessError,
    build_logger,
    ensure_dataset_descriptions,
    ensure_subject_dirs,
)


def _run_step(label: str, func, logger) -> float:
    """Execute a single pipeline step with logging.

    Returns
    -------
    float
        Wall-clock duration of the step in seconds.
    """
    logger.info(f"{label}: Started")
    t0 = time.time()
    func()
    duration = time.time() - t0
    logger.info(f"{label}: ✓ Complete ({duration:.1f}s)")
    return duration


def _should_run_output_step(
    project_dir: str,
    subject_id: str,
    step: str,
    *,
    logger,
    skip_existing_outputs: bool,
    replace_existing_outputs: bool,
) -> bool:
    """Apply the selected existing-output policy for one pipeline step."""
    existing_outputs = existing_outputs_for_step(project_dir, subject_id, step)
    if not existing_outputs:
        return True

    paths = ", ".join(str(output.path) for output in existing_outputs)
    label = existing_outputs[0].label

    if replace_existing_outputs:
        logger.warning(f"{label}: replacing existing output(s): {paths}")
        for output in existing_outputs:
            remove_preprocessing_output(output)
        return True

    if skip_existing_outputs:
        logger.warning(f"{label}: skipping because output already exists: {paths}")
        return False

    raise PreprocessError(
        f"{label} output already exists for subject {subject_id}: {paths}. "
        "Choose skip existing outputs, replace existing outputs, or disable this step."
    )


def _report_status(durations: dict[str, float | None], step_name: str) -> str:
    """Return the report status for a selected step."""
    return "skipped" if step_name in durations and durations[step_name] is None else "completed"


def _format_input_problems(problems) -> str:
    lines = ["Missing required preprocessing inputs:"]
    for problem in problems:
        lines.append(
            f"- sub-{problem.subject_id} {problem.label}: {problem.message} "
            f"Checked: {problem.path}"
        )
    return "\n".join(lines)


def _run_subject_pipeline(
    project_dir: str,
    subject_id: str,
    *,
    convert_dicom: bool,
    run_recon: bool,
    parallel_recon: bool,
    create_m2m: bool,
    run_tissue: bool,
    run_qsiprep_step: bool,
    run_qsirecon_step: bool,
    qsiprep_config: dict | None,
    qsi_recon_config: dict | None,
    extract_dti_step: bool,
    run_subcortical: bool,
    debug: bool,
    runner: CommandRunner,
    callback: Callable | None,
    skip_existing_outputs: bool,
    replace_existing_outputs: bool,
) -> dict[str, float | None]:
    """Run the full preprocessing sequence for a single subject.

    Returns
    -------
    dict[str, float | None]
        Mapping of step name to duration in seconds, or ``None`` when skipped.
    """
    logger = build_logger(
        "preprocess",
        subject_id,
        project_dir,
        console=callback is None,
    )

    logger.info(f"Beginning pre-processing for subject: {subject_id}")

    durations: dict[str, float | None] = {}

    if run_recon and not convert_dicom and not create_m2m:
        should_run_recon = _should_run_output_step(
            project_dir,
            subject_id,
            STEP_RECON_ALL,
            logger=logger,
            skip_existing_outputs=skip_existing_outputs,
            replace_existing_outputs=replace_existing_outputs,
        )
        if should_run_recon:
            durations["FreeSurfer recon-all"] = _run_step(
                "FreeSurfer recon-all",
                lambda: run_recon_all(
                    project_dir,
                    subject_id,
                    logger=logger,
                    parallel=not parallel_recon,
                    runner=runner,
                ),
                logger,
            )
        else:
            durations["FreeSurfer recon-all"] = None
    else:
        if convert_dicom:
            if _should_run_output_step(
                project_dir,
                subject_id,
                STEP_DICOM,
                logger=logger,
                skip_existing_outputs=skip_existing_outputs,
                replace_existing_outputs=replace_existing_outputs,
            ):
                durations["DICOM Conversion"] = _run_step(
                    "DICOM conversion",
                    lambda: run_dicom_to_nifti(
                        project_dir,
                        subject_id,
                        logger=logger,
                        runner=runner,
                    ),
                    logger,
                )
            else:
                durations["DICOM Conversion"] = None

        if create_m2m:
            if _should_run_output_step(
                project_dir,
                subject_id,
                STEP_CHARM,
                logger=logger,
                skip_existing_outputs=skip_existing_outputs,
                replace_existing_outputs=replace_existing_outputs,
            ):
                durations["SimNIBS charm"] = _run_step(
                    "SimNIBS charm",
                    lambda: run_charm(
                        project_dir,
                        subject_id,
                        logger=logger,
                        runner=runner,
                    ),
                    logger,
                )
                durations["Subject Atlas Segmentation"] = _run_step(
                    "Subject atlas segmentation",
                    lambda: run_subject_atlas(
                        project_dir,
                        subject_id,
                        logger=logger,
                        runner=runner,
                    ),
                    logger,
                )
            else:
                durations["SimNIBS charm"] = None
                durations["Subject Atlas Segmentation"] = None

        if run_recon:
            if _should_run_output_step(
                project_dir,
                subject_id,
                STEP_RECON_ALL,
                logger=logger,
                skip_existing_outputs=skip_existing_outputs,
                replace_existing_outputs=replace_existing_outputs,
            ):
                durations["FreeSurfer recon-all"] = _run_step(
                    "FreeSurfer recon-all",
                    lambda: run_recon_all(
                        project_dir,
                        subject_id,
                        logger=logger,
                        parallel=not parallel_recon,
                        runner=runner,
                    ),
                    logger,
                )
            else:
                durations["FreeSurfer recon-all"] = None

    if run_tissue:
        durations["Tissue Analysis"] = _run_step(
            "Tissue analysis",
            lambda: run_tissue_analysis(
                project_dir,
                subject_id,
                logger=logger,
                runner=runner,
            ),
            logger,
        )

    # QSI pipeline steps (DWI preprocessing)
    if run_qsiprep_step:
        qsiprep_cfg = qsiprep_config or {}
        if _should_run_output_step(
            project_dir,
            subject_id,
            STEP_QSIPREP,
            logger=logger,
            skip_existing_outputs=skip_existing_outputs,
            replace_existing_outputs=replace_existing_outputs,
        ):
            durations["QSIPrep"] = _run_step(
                "QSIPrep DWI preprocessing",
                lambda: run_qsiprep(
                    project_dir,
                    subject_id,
                    logger=logger,
                    output_resolution=qsiprep_cfg.get(
                        "output_resolution", const.QSI_DEFAULT_OUTPUT_RESOLUTION
                    ),
                    cpus=qsiprep_cfg.get("cpus"),
                    memory_gb=qsiprep_cfg.get("memory_gb"),
                    omp_threads=qsiprep_cfg.get(
                        "omp_threads", const.QSI_DEFAULT_OMP_THREADS
                    ),
                    image_tag=qsiprep_cfg.get("image_tag", const.QSI_QSIPREP_IMAGE_TAG),
                    skip_bids_validation=qsiprep_cfg.get("skip_bids_validation", True),
                    denoise_method=qsiprep_cfg.get("denoise_method", "dwidenoise"),
                    unringing_method=qsiprep_cfg.get("unringing_method", "mrdegibbs"),
                    runner=runner,
                ),
                logger,
            )
        else:
            durations["QSIPrep"] = None

    if run_qsirecon_step:
        recon_cfg = qsi_recon_config or {}
        recon_specs = recon_cfg.get("recon_specs") if recon_cfg else None
        atlases = recon_cfg.get("atlases") if recon_cfg else None
        if _should_run_output_step(
            project_dir,
            subject_id,
            STEP_QSIRECON,
            logger=logger,
            skip_existing_outputs=skip_existing_outputs,
            replace_existing_outputs=replace_existing_outputs,
        ):
            durations["QSIRecon"] = _run_step(
                "QSIRecon reconstruction",
                lambda: run_qsirecon(
                    project_dir,
                    subject_id,
                    logger=logger,
                    recon_specs=recon_specs,
                    atlases=atlases,
                    use_gpu=recon_cfg.get("use_gpu", False),
                    cpus=recon_cfg.get("cpus"),
                    memory_gb=recon_cfg.get("memory_gb"),
                    omp_threads=recon_cfg.get(
                        "omp_threads", const.QSI_DEFAULT_OMP_THREADS
                    ),
                    image_tag=recon_cfg.get("image_tag", const.QSI_QSIRECON_IMAGE_TAG),
                    skip_odf_reports=recon_cfg.get("skip_odf_reports", True),
                    runner=runner,
                ),
                logger,
            )
        else:
            durations["QSIRecon"] = None

    if extract_dti_step:
        if _should_run_output_step(
            project_dir,
            subject_id,
            STEP_DTI,
            logger=logger,
            skip_existing_outputs=skip_existing_outputs,
            replace_existing_outputs=replace_existing_outputs,
        ):
            durations["DTI Tensor Extraction"] = _run_step(
                "DTI tensor extraction",
                lambda: extract_dti_tensor(
                    project_dir,
                    subject_id,
                    logger=logger,
                ),
                logger,
            )
        else:
            durations["DTI Tensor Extraction"] = None

    if run_subcortical:
        durations["Subcortical Segmentations"] = _run_step(
            "Subcortical segmentations",
            lambda: run_subcortical_segmentations(
                project_dir,
                subject_id,
                logger=logger,
                runner=runner,
            ),
            logger,
        )

    logger.info(f"Pre-processing completed successfully for subject: {subject_id}")
    return durations


def run_pipeline(
    subject_ids: Iterable[str],
    *,
    convert_dicom: bool = False,
    run_recon: bool = False,
    parallel_recon: bool = False,
    parallel_cores: int | None = None,
    create_m2m: bool = False,
    run_tissue_analysis: bool = False,
    run_qsiprep: bool = False,
    run_qsirecon: bool = False,
    qsiprep_config: dict | None = None,
    qsi_recon_config: dict | None = None,
    extract_dti: bool = False,
    run_subcortical_segmentations: bool = False,
    skip_existing_outputs: bool = False,
    replace_existing_outputs: bool = False,
    debug: bool = False,
    stop_event: object | None = None,
    logger_callback: Callable | None = None,
    runner: CommandRunner | None = None,
) -> int:
    """Run the preprocessing pipeline for one or more subjects.

    Orchestrates DICOM conversion, FreeSurfer recon-all, SimNIBS CHARM,
    tissue analysis, QSIPrep/QSIRecon DWI preprocessing, DTI tensor
    extraction, and subcortical segmentation.  Steps are enabled via
    boolean flags; disabled steps are skipped.

    Parameters
    ----------
    subject_ids : iterable of str
        Subject identifiers without the ``sub-`` prefix.
    convert_dicom : bool, optional
        Run DICOM-to-NIfTI conversion.
    run_recon : bool, optional
        Run FreeSurfer ``recon-all``.
    parallel_recon : bool, optional
        Run ``recon-all`` in parallel across subjects.
    parallel_cores : int or None, optional
        Maximum number of parallel subjects for ``recon-all``.
    create_m2m : bool, optional
        Run SimNIBS ``charm`` (also runs ``subject_atlas`` for ``.annot``
        files).
    run_tissue_analysis : bool, optional
        Run tissue-volume and thickness analysis.
    run_qsiprep : bool, optional
        Run QSIPrep DWI preprocessing via Docker.
    run_qsirecon : bool, optional
        Run QSIRecon reconstruction via Docker.
    qsiprep_config : dict or None, optional
        Extra configuration passed to ``run_qsiprep``.
    qsi_recon_config : dict or None, optional
        Extra configuration passed to ``run_qsirecon``.
    extract_dti : bool, optional
        Extract DTI tensor for SimNIBS anisotropic conductivity.
    run_subcortical_segmentations : bool, optional
        Run thalamic-nuclei and hippocampal-subfield segmentations.
    skip_existing_outputs : bool, optional
        Skip selected preprocessing steps when their output already exists.
    replace_existing_outputs : bool, optional
        Remove selected existing outputs before rerunning their steps.
    debug : bool, optional
        Enable verbose logging.
    stop_event : object or None, optional
        Threading event used to cancel running steps.
    logger_callback : callable or None, optional
        Callback used by the GUI to capture log lines.
    runner : CommandRunner or None, optional
        Subprocess runner used to stream command output.

    Returns
    -------
    int
        ``0`` on success, ``1`` on failure.

    Raises
    ------
    PreprocessError
        If no subjects are provided or a preprocessing step fails.
    PreprocessCancelled
        If *stop_event* is set during execution.

    See Also
    --------
    run_dicom_to_nifti : DICOM-to-NIfTI conversion step.
    run_recon_all : FreeSurfer recon-all step.
    run_charm : SimNIBS CHARM head-mesh step.
    run_tissue_analysis : Tissue analysis step.
    run_qsiprep : QSIPrep DWI preprocessing step.
    run_qsirecon : QSIRecon reconstruction step.
    extract_dti_tensor : DTI tensor extraction step.
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    subject_list = [str(s).strip() for s in subject_ids if str(s).strip()]
    if not subject_list:
        raise PreprocessError("No subjects provided.")
    if skip_existing_outputs and replace_existing_outputs:
        raise PreprocessError(
            "skip_existing_outputs and replace_existing_outputs cannot both be true."
        )

    pm = get_path_manager()
    project_dir = pm._root()
    input_problems = find_missing_preprocessing_inputs(
        project_dir,
        subject_list,
        convert_dicom=convert_dicom,
        create_m2m=create_m2m,
        run_recon=run_recon,
        run_qsiprep=run_qsiprep,
        run_qsirecon=run_qsirecon,
        extract_dti=extract_dti,
        skip_existing_outputs=skip_existing_outputs,
    )
    if input_problems:
        raise PreprocessError(_format_input_problems(input_problems))

    with track_operation(_const.TELEMETRY_OP_PRE_PIPELINE):
        return _run_pipeline_inner(
            subject_list,
            convert_dicom=convert_dicom,
            run_recon=run_recon,
            parallel_recon=parallel_recon,
            parallel_cores=parallel_cores,
            create_m2m=create_m2m,
            run_tissue_analysis=run_tissue_analysis,
            run_qsiprep=run_qsiprep,
            run_qsirecon=run_qsirecon,
            qsiprep_config=qsiprep_config,
            qsi_recon_config=qsi_recon_config,
            extract_dti=extract_dti,
            run_subcortical_segmentations=run_subcortical_segmentations,
            skip_existing_outputs=skip_existing_outputs,
            replace_existing_outputs=replace_existing_outputs,
            debug=debug,
            stop_event=stop_event,
            logger_callback=logger_callback,
            runner=runner,
        )


def _run_pipeline_inner(
    subject_ids,
    *,
    convert_dicom=False,
    run_recon=False,
    parallel_recon=False,
    parallel_cores=None,
    create_m2m=False,
    run_tissue_analysis=False,
    run_qsiprep=False,
    run_qsirecon=False,
    qsiprep_config=None,
    qsi_recon_config=None,
    extract_dti=False,
    run_subcortical_segmentations=False,
    skip_existing_outputs=False,
    replace_existing_outputs=False,
    debug=False,
    stop_event=None,
    logger_callback=None,
    runner=None,
) -> int:
    """Inner implementation of :func:`run_pipeline`."""
    subject_list = list(subject_ids)

    pm = get_path_manager()
    project_dir = pm._root()

    for sid in subject_list:
        ensure_subject_dirs(project_dir, sid)

    datasets = {"ti-toolbox"}
    if run_recon:
        datasets.add("freesurfer")
    if create_m2m:
        datasets.add("simnibs")
    ensure_dataset_descriptions(project_dir, datasets)

    if runner is None:
        runner = CommandRunner(stop_event=stop_event)
    elif stop_event is not None and runner.stop_event is not stop_event:
        runner.stop_event = stop_event

    # Collect step durations per subject for reporting
    all_durations: dict[str, dict[str, float | None]] = {
        sid: {} for sid in subject_list
    }

    if parallel_recon and run_recon and len(subject_list) > 1:
        for sid in subject_list:
            d = _run_subject_pipeline(
                project_dir,
                sid,
                convert_dicom=convert_dicom,
                run_recon=False,
                parallel_recon=parallel_recon,
                create_m2m=create_m2m,
                run_tissue=False,
                run_qsiprep_step=False,
                run_qsirecon_step=False,
                qsiprep_config=qsiprep_config,
                qsi_recon_config=qsi_recon_config,
                extract_dti_step=False,
                run_subcortical=False,
                debug=debug,
                runner=runner,
                callback=logger_callback,
                skip_existing_outputs=skip_existing_outputs,
                replace_existing_outputs=replace_existing_outputs,
            )
            all_durations[sid].update(d)

        max_workers = parallel_cores or os.cpu_count() or 1
        max_workers = min(max_workers, len(subject_list))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for sid in subject_list:
                futures[
                    executor.submit(
                        _run_subject_pipeline,
                        project_dir,
                        sid,
                        convert_dicom=False,
                        run_recon=True,
                        parallel_recon=True,
                        create_m2m=False,
                        run_tissue=False,
                        run_qsiprep_step=False,
                        run_qsirecon_step=False,
                        qsiprep_config=qsiprep_config,
                        qsi_recon_config=qsi_recon_config,
                        extract_dti_step=False,
                        run_subcortical=False,
                        debug=debug,
                        runner=runner,
                        callback=logger_callback,
                        skip_existing_outputs=skip_existing_outputs,
                        replace_existing_outputs=replace_existing_outputs,
                    )
                ] = sid

            for future in as_completed(futures):
                sid = futures[future]
                all_durations[sid].update(future.result())

        if run_tissue_analysis:
            for sid in subject_list:
                d = _run_subject_pipeline(
                    project_dir,
                    sid,
                    convert_dicom=False,
                    run_recon=False,
                    parallel_recon=parallel_recon,
                    create_m2m=False,
                    run_tissue=True,
                    run_qsiprep_step=False,
                    run_qsirecon_step=False,
                    qsiprep_config=qsiprep_config,
                    qsi_recon_config=qsi_recon_config,
                    extract_dti_step=False,
                    run_subcortical=False,
                    debug=debug,
                    runner=runner,
                    callback=logger_callback,
                    skip_existing_outputs=skip_existing_outputs,
                    replace_existing_outputs=replace_existing_outputs,
                )
                all_durations[sid].update(d)
        # Run QSI steps after tissue analysis (if enabled)
        if run_qsiprep or run_qsirecon or extract_dti:
            for sid in subject_list:
                d = _run_subject_pipeline(
                    project_dir,
                    sid,
                    convert_dicom=False,
                    run_recon=False,
                    parallel_recon=parallel_recon,
                    create_m2m=False,
                    run_tissue=False,
                    run_qsiprep_step=run_qsiprep,
                    run_qsirecon_step=run_qsirecon,
                    qsiprep_config=qsiprep_config,
                    qsi_recon_config=qsi_recon_config,
                    extract_dti_step=extract_dti,
                    run_subcortical=False,
                    debug=debug,
                    runner=runner,
                    callback=logger_callback,
                    skip_existing_outputs=skip_existing_outputs,
                    replace_existing_outputs=replace_existing_outputs,
                )
                all_durations[sid].update(d)
        if run_subcortical_segmentations:
            for sid in subject_list:
                d = _run_subject_pipeline(
                    project_dir,
                    sid,
                    convert_dicom=False,
                    run_recon=False,
                    parallel_recon=parallel_recon,
                    create_m2m=False,
                    run_tissue=False,
                    run_qsiprep_step=False,
                    run_qsirecon_step=False,
                    qsiprep_config=qsiprep_config,
                    qsi_recon_config=qsi_recon_config,
                    extract_dti_step=False,
                    run_subcortical=True,
                    debug=debug,
                    runner=runner,
                    callback=logger_callback,
                    skip_existing_outputs=skip_existing_outputs,
                    replace_existing_outputs=replace_existing_outputs,
                )
                all_durations[sid].update(d)
    else:
        for sid in subject_list:
            d = _run_subject_pipeline(
                project_dir,
                sid,
                convert_dicom=convert_dicom,
                run_recon=run_recon,
                parallel_recon=parallel_recon,
                create_m2m=create_m2m,
                run_tissue=run_tissue_analysis,
                run_qsiprep_step=run_qsiprep,
                run_qsirecon_step=run_qsirecon,
                qsiprep_config=qsiprep_config,
                qsi_recon_config=qsi_recon_config,
                extract_dti_step=extract_dti,
                run_subcortical=run_subcortical_segmentations,
                debug=debug,
                runner=runner,
                callback=logger_callback,
                skip_existing_outputs=skip_existing_outputs,
                replace_existing_outputs=replace_existing_outputs,
            )
            all_durations[sid].update(d)

    # Generate HTML reports for each subject
    from tit.reporting import PreprocessingReportGenerator

    for sid in subject_list:
        report_gen = PreprocessingReportGenerator(
            project_dir=project_dir,
            subject_id=sid,
        )
        durations = all_durations[sid]

        if convert_dicom:
            report_gen.add_processing_step(
                step_name="DICOM Conversion",
                description="Convert DICOM files to NIfTI format",
                status=_report_status(durations, "DICOM Conversion"),
                duration=durations.get("DICOM Conversion"),
            )

        if create_m2m:
            report_gen.add_processing_step(
                step_name="SimNIBS charm",
                description="Create head mesh model for simulations",
                status=_report_status(durations, "SimNIBS charm"),
                duration=durations.get("SimNIBS charm"),
            )
            report_gen.add_processing_step(
                step_name="Subject Atlas Segmentation",
                description="Generate atlas-based parcellation",
                status=_report_status(durations, "Subject Atlas Segmentation"),
                duration=durations.get("Subject Atlas Segmentation"),
            )

        if run_recon:
            report_gen.add_processing_step(
                step_name="FreeSurfer recon-all",
                description="Cortical surface reconstruction",
                status=_report_status(durations, "FreeSurfer recon-all"),
                duration=durations.get("FreeSurfer recon-all"),
            )

        if run_tissue_analysis:
            report_gen.add_processing_step(
                step_name="Tissue Analysis",
                description="Tissue segmentation and analysis",
                status=_report_status(durations, "Tissue Analysis"),
                duration=durations.get("Tissue Analysis"),
            )

        if run_qsiprep:
            report_gen.add_processing_step(
                step_name="QSIPrep",
                description="Diffusion MRI preprocessing",
                status=_report_status(durations, "QSIPrep"),
                duration=durations.get("QSIPrep"),
            )

        if run_qsirecon:
            report_gen.add_processing_step(
                step_name="QSIRecon",
                description="Diffusion MRI reconstruction",
                status=_report_status(durations, "QSIRecon"),
                duration=durations.get("QSIRecon"),
            )

        if extract_dti:
            report_gen.add_processing_step(
                step_name="DTI Tensor Extraction",
                description="Extract DTI tensors for anisotropic conductivity",
                status=_report_status(durations, "DTI Tensor Extraction"),
                duration=durations.get("DTI Tensor Extraction"),
            )

        if run_subcortical_segmentations:
            report_gen.add_processing_step(
                step_name="Subcortical Segmentations",
                description="Thalamic nuclei and hippocampal subfield segmentations",
                status=_report_status(durations, "Subcortical Segmentations"),
                duration=durations.get("Subcortical Segmentations"),
            )

        report_gen.scan_for_data()
        report_path = report_gen.generate()
        if logger_callback:
            logger_callback(f"Report generated: {report_path}", "info")

    return 0
