#!/usr/bin/env simnibs_python
"""
Pre-processing pipeline orchestration.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

from tit.core import constants as const
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
from .qsi import run_qsiprep, run_qsirecon, extract_dti_tensor


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
    run_qsiprep_step: bool,
    run_qsirecon_step: bool,
    qsiprep_config: Optional[dict],
    qsi_recon_config: Optional[dict],
    extract_dti_step: bool,
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

    # QSI pipeline steps (DWI preprocessing)
    if run_qsiprep_step:
        qsiprep_cfg = qsiprep_config or {}
        overall_success &= _run_step(
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
                image_tag=qsiprep_cfg.get("image_tag", const.QSI_DEFAULT_IMAGE_TAG),
                skip_bids_validation=qsiprep_cfg.get("skip_bids_validation", True),
                denoise_method=qsiprep_cfg.get("denoise_method", "dwidenoise"),
                unringing_method=qsiprep_cfg.get("unringing_method", "mrdegibbs"),
                overwrite=policy.overwrite,
                runner=runner,
            ),
            logger,
        )

    if run_qsirecon_step:
        # Extract recon specs and atlases from config
        recon_cfg = qsi_recon_config or {}
        recon_specs = recon_cfg.get("recon_specs") if recon_cfg else None
        atlases = recon_cfg.get("atlases") if recon_cfg else None
        overall_success &= _run_step(
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
                omp_threads=recon_cfg.get("omp_threads", const.QSI_DEFAULT_OMP_THREADS),
                image_tag=recon_cfg.get("image_tag", const.QSI_DEFAULT_IMAGE_TAG),
                skip_odf_reports=recon_cfg.get("skip_odf_reports", True),
                overwrite=policy.overwrite,
                runner=runner,
            ),
            logger,
        )

    if extract_dti_step:
        overall_success &= _run_step(
            "DTI tensor extraction",
            lambda: extract_dti_tensor(
                project_dir,
                subject_id,
                logger=logger,
                overwrite=policy.overwrite if policy.overwrite else False,
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
    run_qsiprep: bool = False,
    run_qsirecon: bool = False,
    qsiprep_config: Optional[dict] = None,
    qsi_recon_config: Optional[dict] = None,
    extract_dti: bool = False,
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
    run_qsiprep : bool, optional
        Run QSIPrep DWI preprocessing via Docker.
    run_qsirecon : bool, optional
        Run QSIRecon reconstruction via Docker.
    qsi_recon_specs : iterable of str, optional
        QSIRecon reconstruction specs to run. Default: ['dipy_dki'].
    extract_dti : bool, optional
        Extract DTI tensor for SimNIBS anisotropic conductivity.
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
                    run_qsiprep_step=False,
                    run_qsirecon_step=False,
                    qsiprep_config=qsiprep_config,
                    qsi_recon_config=qsi_recon_config,
                    extract_dti_step=False,
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
                        run_qsiprep_step=False,
                        run_qsirecon_step=False,
                        qsiprep_config=qsiprep_config,
                        qsi_recon_config=qsi_recon_config,
                        extract_dti_step=False,
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
                        run_qsiprep_step=False,
                        run_qsirecon_step=False,
                        qsiprep_config=qsiprep_config,
                        qsi_recon_config=qsi_recon_config,
                        extract_dti_step=False,
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
        # Run QSI steps after tissue analysis (if enabled)
        if run_qsiprep or run_qsirecon or extract_dti:
            for sid in subject_list:
                try:
                    success = _run_subject_pipeline(
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
                    run_qsiprep_step=run_qsiprep,
                    run_qsirecon_step=run_qsirecon,
                    qsiprep_config=qsiprep_config,
                    qsi_recon_config=qsi_recon_config,
                    extract_dti_step=extract_dti,
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

    # Generate HTML reports for each subject
    try:
        from tit.reporting import PreprocessingReportGenerator

        for sid in subject_list:
            try:
                report_gen = PreprocessingReportGenerator(
                    project_dir=project_dir,
                    subject_id=sid,
                )

                # Add processing steps based on what was run
                if convert_dicom:
                    report_gen.add_processing_step(
                        step_name="DICOM Conversion",
                        description="Convert DICOM files to NIfTI format",
                        status="completed" if overall_success else "failed",
                    )

                if create_m2m:
                    report_gen.add_processing_step(
                        step_name="SimNIBS charm",
                        description="Create head mesh model for simulations",
                        status="completed" if overall_success else "failed",
                    )
                    report_gen.add_processing_step(
                        step_name="Subject Atlas Segmentation",
                        description="Generate atlas-based parcellation",
                        status="completed" if overall_success else "failed",
                    )

                if run_recon:
                    report_gen.add_processing_step(
                        step_name="FreeSurfer recon-all",
                        description="Cortical surface reconstruction",
                        status="completed" if overall_success else "failed",
                    )

                if run_tissue_analysis:
                    report_gen.add_processing_step(
                        step_name="Tissue Analysis",
                        description="Tissue segmentation and analysis",
                        status="completed" if overall_success else "failed",
                    )

                if run_qsiprep:
                    report_gen.add_processing_step(
                        step_name="QSIPrep",
                        description="Diffusion MRI preprocessing",
                        status="completed" if overall_success else "failed",
                    )

                if run_qsirecon:
                    report_gen.add_processing_step(
                        step_name="QSIRecon",
                        description="Diffusion MRI reconstruction",
                        status="completed" if overall_success else "failed",
                    )

                if extract_dti:
                    report_gen.add_processing_step(
                        step_name="DTI Tensor Extraction",
                        description="Extract DTI tensors for anisotropic conductivity",
                        status="completed" if overall_success else "failed",
                    )

                # Auto-scan for data
                report_gen.scan_for_data()

                # Generate report
                report_path = report_gen.generate()

                # Log report generation via callback if available
                if logger_callback:
                    logger_callback(f"Report generated: {report_path}", "info")

            except Exception as e:
                if logger_callback:
                    logger_callback(
                        f"Warning: Could not generate report for {sid}: {e}",
                        "warning",
                    )

    except ImportError:
        pass  # Reporting module not available

    return 0 if overall_success else 1
