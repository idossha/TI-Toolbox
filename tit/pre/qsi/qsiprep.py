#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
QSIPrep runner for TI-Toolbox.

This module provides functions to run QSIPrep as a sibling Docker container
using the Docker-out-of-Docker (DooD) pattern.
"""

import logging
import os
from pathlib import Path

from tit import constants as const
from tit.paths import get_path_manager
from tit.pre.utils import CommandRunner, PreprocessError

from .config import QSIPrepConfig, ResourceConfig
from .docker_builder import DockerCommandBuilder, DockerBuildError
from .utils import (
    choose_unringing_method,
    ensure_total_readout_time,
    native_dwi_resolution,
    plan_distortion_correction,
    pull_image_if_needed,
    validate_dood_environment,
    validate_bids_dwi,
    validate_qsiprep_output,
)

# A nipype crashfile leads with the node name and ends with the exception that
# actually stopped the run; the middle is the nipype call stack, which says
# nothing about the cause.
_CRASH_TAIL_LINES = 12


def _report_crashfiles(output_dir: Path, logger: logging.Logger) -> int:
    """Log the tail of every nipype crashfile QSIPrep wrote. Returns the count.

    QSIPrep reports node failures only as a path to a crashfile inside the
    output directory, so the container's stdout ends with a summary that names
    no cause. Without this the user has to go find the files by hand.
    """
    crashfiles = sorted(output_dir.glob("**/crash-*.txt"))
    for crashfile in crashfiles:
        try:
            lines = crashfile.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            logger.error(f"Could not read crashfile {crashfile}: {exc}")
            continue
        node = lines[0] if lines else crashfile.name
        tail = "\n    ".join(
            line for line in lines[-_CRASH_TAIL_LINES:] if line.strip()
        )
        logger.error(f"QSIPrep node crash -- {node}\n    {tail}")
    return len(crashfiles)


def _format_qsiprep_failure(
    returncode: int, runner: CommandRunner, crash_count: int = 0
) -> str:
    crash_note = (
        f" {crash_count} node crashfile(s) were logged above." if crash_count else ""
    )
    lines = getattr(runner, "last_output_lines", []) or []
    if not lines:
        return (
            f"QSIPrep failed with exit code {returncode}.{crash_note} "
            "No container output was captured; check the preprocessing log for details."
        )
    tail = " | ".join(lines[-5:])
    return (
        f"QSIPrep failed with exit code {returncode}.{crash_note} Last output: {tail}"
    )


def run_qsiprep(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    output_resolution: float | None = None,
    cpus: int | None = None,
    memory_gb: int | None = None,
    omp_threads: int = const.QSI_DEFAULT_OMP_THREADS,
    image_tag: str = const.QSI_QSIPREP_IMAGE_TAG,
    skip_bids_validation: bool = True,
    denoise_method: str = "dwidenoise",
    unringing_method: str = "auto",
    mni_normalization: bool = False,
    runner: CommandRunner | None = None,
) -> None:
    """
    Run QSIPrep preprocessing for a subject's DWI data.

    This function spawns a QSIPrep Docker container as a sibling to the
    current SimNIBS container using Docker-out-of-Docker (DooD). QSIPrep needs
    an x86-64 Docker host (its SynthSeg step needs AVX); an arm64 host is
    refused before anything runs.

    Susceptibility distortion correction is always on: TOPUP with the subject's
    reverse phase-encoding fieldmap (``IntendedFor`` written into its sidecar when
    missing) or reverse-PE DWI series, else fieldmap-less SyN
    (``--use-syn-sdc warn``). DWI fieldmaps that exist but cannot be used stop the
    run instead of silently falling back.

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project root directory.
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    logger : logging.Logger
        Logger for status messages.
    output_resolution : float or None, optional
        Isotropic output voxel size in mm. ``None`` (default) uses the native DWI
        voxel size (smallest axis, rounded to 0.1 mm).
    cpus : int, optional
        Number of CPUs to allocate. Default: 8.
    memory_gb : int, optional
        Memory limit in GB. Default: 32.
    omp_threads : int, optional
        Threads per process. Default: ``constants.QSI_DEFAULT_OMP_THREADS``
        (min(cpu_count - 1, 8), matching QSIPrep's own default).
    image_tag : str, optional
        QSIPrep Docker image tag. Default from ``constants.QSI_QSIPREP_IMAGE_TAG``.
    skip_bids_validation : bool, optional
        Skip BIDS validation. Default: True.
    denoise_method : str, optional
        Denoising method. Default: 'dwidenoise'.
    unringing_method : str, optional
        'mrdegibbs', 'rpg', 'none' or 'auto' (default): rpg when the DWI sidecar
        has ``PartialFourier`` < 1, else mrdegibbs.
    mni_normalization : bool, optional
        Run the anatomical normalization to MNI (needed only for QSIRecon atlases
        and template-space specs). Default: False; forced on by SyN SDC.
    runner : CommandRunner | None, optional
        Command runner for subprocess execution.

    Raises
    ------
    PreprocessError
        If QSIPrep fails or prerequisites are not met.
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_PRE_QSIPREP):
        logger.info(f"Starting QSIPrep for subject {subject_id}")
        ok, preflight_error = validate_dood_environment(
            project_dir, require_x86_64=True
        )
        if not ok:
            raise PreprocessError(f"QSI Docker preflight failed: {preflight_error}")

        # Validate DWI data exists. This runs before the container starts
        # because QSIPrep surfaces a bad gradient table or an incomplete
        # sidecar only after the anatomical workflow has finished, an hour in.
        is_valid, error_msg = validate_bids_dwi(project_dir, subject_id, logger)
        if not is_valid:
            raise PreprocessError(f"DWI validation failed: {error_msg}")

        is_valid, error_msg = ensure_total_readout_time(
            project_dir, subject_id, logger=logger
        )
        if not is_valid:
            raise PreprocessError(f"DWI sidecar validation failed: {error_msg}")

        pm = get_path_manager(project_dir)
        output_dir = Path(pm.qsiprep_subject(subject_id))
        # Docker `-v` can leave an empty directory behind; only a non-empty
        # one is a real output.
        if output_dir.exists() and any(output_dir.iterdir()):
            raise PreprocessError(
                f"QSIPrep output already exists at {output_dir}. "
                "Remove the directory manually before rerunning. The working "
                f"directory at {Path(pm.derivatives()) / '.qsiprep_work'} is kept "
                "on purpose: QSIPrep reuses the nodes that already finished, so "
                "a rerun after a failure skips the anatomical workflow. Delete "
                "it too only if you want to start from scratch."
            )

        sdc = plan_distortion_correction(project_dir, subject_id, logger=logger)
        if sdc.blocking_error:
            raise PreprocessError(sdc.blocking_error)
        logger.info(f"Distortion correction: {sdc.describe()}")
        if sdc.use_syn and not mni_normalization:
            logger.info(
                "MNI normalization enabled: SyN distortion correction needs the "
                "anat-to-MNI transform."
            )

        if unringing_method == "auto":
            unringing_method, reason = choose_unringing_method(project_dir, subject_id)
            logger.info(f"Unringing: {unringing_method} ({reason})")

        if output_resolution is None:
            output_resolution = native_dwi_resolution(project_dir, subject_id)
            if output_resolution is None:
                output_resolution = const.QSI_DEFAULT_OUTPUT_RESOLUTION
                logger.warning(
                    "Could not read the DWI voxel size; using "
                    f"{output_resolution:g} mm output resolution."
                )
            else:
                logger.info(
                    f"Output resolution: {output_resolution:g} mm (native DWI voxel size)"
                )

        # Create output directories
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        work_dir = Path(pm.derivatives()) / ".qsiprep_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Build configuration
        config = QSIPrepConfig(
            subject_id=subject_id,
            output_resolution=output_resolution,
            resources=ResourceConfig(
                cpus=cpus,
                memory_gb=memory_gb,
                omp_threads=omp_threads,
            ),
            image_tag=image_tag,
            skip_bids_validation=skip_bids_validation,
            denoise_method=denoise_method,
            unringing_method=unringing_method,
            use_syn_sdc=sdc.use_syn,
            mni_normalization=mni_normalization,
        )

        try:
            # Build Docker command
            builder = DockerCommandBuilder(project_dir)
            cmd = builder.build_qsiprep_cmd(config)
        except DockerBuildError as e:
            raise PreprocessError(f"Failed to build QSIPrep command: {e}")

        # Ensure image is available
        if not pull_image_if_needed(const.QSI_QSIPREP_IMAGE, image_tag, logger):
            raise PreprocessError(
                f"Failed to pull QSIPrep image: {const.QSI_QSIPREP_IMAGE}:{image_tag}"
            )

        # Log the command for debugging
        logger.debug(f"QSIPrep command: {' '.join(cmd)}")

        # Run the container
        if runner is None:
            runner = CommandRunner()

        logger.info(f"Running QSIPrep for subject {subject_id}...")
        returncode = runner.run(cmd, logger=logger)

        if returncode != 0:
            crash_count = _report_crashfiles(output_dir, logger)
            raise PreprocessError(
                _format_qsiprep_failure(returncode, runner, crash_count)
            )

        # Validate output
        is_valid, error_msg = validate_qsiprep_output(project_dir, subject_id)
        if not is_valid:
            raise PreprocessError(f"QSIPrep output validation failed: {error_msg}")

    logger.info(f"QSIPrep completed successfully for subject {subject_id}")
