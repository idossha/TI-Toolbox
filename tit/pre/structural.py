#!/usr/bin/env simnibs_python
"""
Pre-processing pipeline orchestration.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

from tit.core import get_path_manager
from .charm import run_charm, run_subject_atlas
from .common import (
    CommandRunner,
    PreprocessCancelled,
    PreprocessError,
    ensure_dataset_descriptions,
    ensure_subject_dirs,
    build_logger,
    get_overwrite_policy,
)
from .dicom2nifti import run_dicom_to_nifti
from .recon_all import run_recon_all
from .tissue_analyzer import run_tissue_analysis


def _run_step(label: str, func, logger) -> bool:
    logger.info(f"├─ {label}: Started")
    try:
        func()
    except PreprocessCancelled:
        raise
    except Exception as exc:
        logger.error(f"{label} failed: {exc}")
        logger.info(f"├─ {label}: ✗ Failed")
        return False
    logger.info(f"├─ {label}: ✓ Complete")
    return True


def _run_subject_pipeline(
    project_dir: str,
    subject_id: str,
    *,
    convert_dicom: bool,
    run_recon: bool,
    parallel_recon: bool,
    create_m2m: bool,
    run_tissue: bool,
    debug: bool,
    overwrite: Optional[bool],
    prompt_overwrite: Optional[bool],
    runner: CommandRunner,
    callback: Optional[callable],
) -> bool:
    logger = build_logger(
        "preprocess",
        subject_id,
        project_dir,
        debug=debug,
        console=callback is None,
        callback=callback,
    )

    logger.info(f"Beginning pre-processing for subject: {subject_id}")

    overall_success = True
    policy = get_overwrite_policy(overwrite, prompt_overwrite)

    if run_recon and not convert_dicom and not create_m2m:
        overall_success &= _run_step(
            "FreeSurfer recon-all",
            lambda: run_recon_all(
                project_dir,
                subject_id,
                logger=logger,
                parallel=not parallel_recon,
                overwrite=policy.overwrite,
                prompt_overwrite=policy.prompt,
                runner=runner,
            ),
            logger,
        )
    else:
        if convert_dicom:
            overall_success &= _run_step(
                "DICOM conversion",
                lambda: run_dicom_to_nifti(
                    project_dir,
                    subject_id,
                    logger=logger,
                    overwrite=policy.overwrite,
                    prompt_overwrite=policy.prompt,
                    runner=runner,
                ),
                logger,
            )

        if create_m2m:
            overall_success &= _run_step(
                "SimNIBS charm",
                lambda: run_charm(
                    project_dir,
                    subject_id,
                    logger=logger,
                    overwrite=policy.overwrite,
                    prompt_overwrite=policy.prompt,
                    runner=runner,
                ),
                logger,
            )
            # Run subject_atlas after charm completes to create .annot files
            if overall_success:
                overall_success &= _run_step(
                    "Subject atlas segmentation",
                    lambda: run_subject_atlas(
                        project_dir,
                        subject_id,
                        logger=logger,
                        runner=runner,
                    ),
                    logger,
                )

        if run_recon:
            overall_success &= _run_step(
                "FreeSurfer recon-all",
                lambda: run_recon_all(
                    project_dir,
                    subject_id,
                    logger=logger,
                    parallel=not parallel_recon,
                    overwrite=policy.overwrite,
                    prompt_overwrite=policy.prompt,
                    runner=runner,
                ),
                logger,
            )

    if run_tissue:
        overall_success &= _run_step(
            "Tissue analysis",
            lambda: run_tissue_analysis(
                project_dir,
                subject_id,
                logger=logger,
                runner=runner,
            ),
            logger,
        )

    if overall_success:
        logger.info(
            f"└─ Pre-processing completed successfully for subject: {subject_id}"
        )
    else:
        logger.info(f"└─ Pre-processing failed for subject: {subject_id}")

    return overall_success


def run_pipeline(
    project_dir: str,
    subject_ids: Iterable[str],
    *,
    convert_dicom: bool = False,
    run_recon: bool = False,
    parallel_recon: bool = False,
    parallel_cores: Optional[int] = None,
    create_m2m: bool = False,
    run_tissue_analysis: bool = False,
    debug: bool = False,
    overwrite: Optional[bool] = None,
    prompt_overwrite: Optional[bool] = None,
    stop_event: Optional[object] = None,
    logger_callback: Optional[callable] = None,
    runner: Optional[CommandRunner] = None,
) -> int:
    """Run the preprocessing pipeline for one or more subjects.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_ids : iterable of str
        Subject identifiers without the `sub-` prefix.
    convert_dicom : bool, optional
        Run DICOM to NIfTI conversion.
    run_recon : bool, optional
        Run FreeSurfer recon-all.
    parallel_recon : bool, optional
        Run recon-all in parallel across subjects.
    parallel_cores : int, optional
        Max parallel subjects for recon-all.
    create_m2m : bool, optional
        Run SimNIBS charm (also runs subject_atlas for .annot files).
    run_tissue_analysis : bool, optional
        Run tissue analysis pipeline.
    debug : bool, optional
        Enable verbose logging.
    overwrite : bool, optional
        Force overwrite of existing outputs.
    prompt_overwrite : bool, optional
        Allow interactive overwrite prompt.
    stop_event : object, optional
        Event used to cancel running steps.
    logger_callback : callable, optional
        Callback used by GUI to capture log lines.
    runner : CommandRunner, optional
        Subprocess runner used to stream output.

    Returns
    -------
    int
        0 on success, 1 on failure.
    """
    subject_list = [str(s).strip() for s in subject_ids if str(s).strip()]
    if not subject_list:
        raise PreprocessError("No subjects provided.")

    pm = get_path_manager()
    pm.project_dir = project_dir

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
    overall_success = True

    if parallel_recon and run_recon and len(subject_list) > 1:
        for sid in subject_list:
            try:
                success = _run_subject_pipeline(
                    project_dir,
                    sid,
                    convert_dicom=convert_dicom,
                    run_recon=False,
                    parallel_recon=parallel_recon,
                    create_m2m=create_m2m,
                    run_tissue=False,
                    debug=debug,
                    overwrite=overwrite,
                    prompt_overwrite=prompt_overwrite,
                    runner=runner,
                    callback=logger_callback,
                )
                overall_success &= success
            except PreprocessCancelled:
                raise
            except Exception:
                overall_success = False

        max_workers = parallel_cores or os.cpu_count() or 1
        max_workers = min(max_workers, len(subject_list))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for sid in subject_list:
                futures.append(
                    executor.submit(
                        _run_subject_pipeline,
                        project_dir,
                        sid,
                        convert_dicom=False,
                        run_recon=True,
                        parallel_recon=True,
                        create_m2m=False,
                        run_tissue=False,
                        debug=debug,
                        overwrite=overwrite,
                        prompt_overwrite=prompt_overwrite,
                        runner=runner,
                        callback=logger_callback,
                    )
                )

            for future in as_completed(futures):
                try:
                    overall_success &= future.result()
                except PreprocessCancelled:
                    raise
                except Exception:
                    overall_success = False
        if run_tissue_analysis:
            for sid in subject_list:
                try:
                    success = _run_subject_pipeline(
                        project_dir,
                        sid,
                        convert_dicom=False,
                        run_recon=False,
                        parallel_recon=parallel_recon,
                        create_m2m=False,
                        run_tissue=True,
                        debug=debug,
                        overwrite=overwrite,
                        prompt_overwrite=prompt_overwrite,
                        runner=runner,
                        callback=logger_callback,
                    )
                    overall_success &= success
                except PreprocessCancelled:
                    raise
                except Exception:
                    overall_success = False
    else:
        for sid in subject_list:
            try:
                success = _run_subject_pipeline(
                    project_dir,
                    sid,
                    convert_dicom=convert_dicom,
                    run_recon=run_recon,
                    parallel_recon=parallel_recon,
                    create_m2m=create_m2m,
                    run_tissue=run_tissue_analysis,
                    debug=debug,
                    overwrite=overwrite,
                    prompt_overwrite=prompt_overwrite,
                    runner=runner,
                    callback=logger_callback,
                )
                overall_success &= success
            except PreprocessCancelled:
                raise
            except Exception:
                overall_success = False

    return 0 if overall_success else 1
