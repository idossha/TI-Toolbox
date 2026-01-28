#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
QSIPrep runner for TI-Toolbox.

This module provides functions to run QSIPrep as a sibling Docker container
using the Docker-out-of-Docker (DooD) pattern.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from tit.core import constants as const
from tit.core.overwrite import OverwritePolicy, should_overwrite_path
from tit.pre.common import CommandRunner, PreprocessError

from .config import QSIPrepConfig, ResourceConfig
from .docker_builder import DockerCommandBuilder, DockerBuildError
from .utils import (
    pull_image_if_needed,
    validate_bids_dwi,
    validate_qsiprep_output,
)


def run_qsiprep(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    output_resolution: float = const.QSI_DEFAULT_OUTPUT_RESOLUTION,
    cpus: Optional[int] = None,
    memory_gb: Optional[int] = None,
    omp_threads: int = const.QSI_DEFAULT_OMP_THREADS,
    image_tag: str = const.QSI_DEFAULT_IMAGE_TAG,
    skip_bids_validation: bool = True,
    denoise_method: str = "dwidenoise",
    unringing_method: str = "mrdegibbs",
    overwrite: Optional[bool] = None,
    runner: Optional[CommandRunner] = None,
) -> None:
    """
    Run QSIPrep preprocessing for a subject's DWI data.

    This function spawns a QSIPrep Docker container as a sibling to the
    current SimNIBS container using Docker-out-of-Docker (DooD).

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project root directory.
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    logger : logging.Logger
        Logger for status messages.
    output_resolution : float, optional
        Target output resolution in mm. Default: 2.0.
    cpus : int, optional
        Number of CPUs to allocate. Default: 8.
    memory_gb : int, optional
        Memory limit in GB. Default: 32.
    omp_threads : int, optional
        Number of OpenMP threads. Default: 1.
    image_tag : str, optional
        QSIPrep Docker image tag. Default: '1.1.1'.
    skip_bids_validation : bool, optional
        Skip BIDS validation. Default: True.
    denoise_method : str, optional
        Denoising method. Default: 'dwidenoise'.
    unringing_method : str, optional
        Unringing method. Default: 'mrdegibbs'.
    overwrite : Optional[bool], optional
        If True, overwrite existing outputs. If False, skip if outputs exist.
        If None, will check and potentially error.
    runner : Optional[CommandRunner], optional
        Command runner for subprocess execution.

    Raises
    ------
    PreprocessError
        If QSIPrep fails or prerequisites are not met.
    """
    logger.info(f"Starting QSIPrep for subject {subject_id}")

    # Validate DWI data exists
    is_valid, error_msg = validate_bids_dwi(project_dir, subject_id, logger)
    if not is_valid:
        raise PreprocessError(f"DWI validation failed: {error_msg}")

    # Check for existing output
    output_dir = Path(project_dir) / "derivatives" / "qsiprep" / f"sub-{subject_id}"

    if output_dir.exists():
        existing_valid, _ = validate_qsiprep_output(project_dir, subject_id)
        if existing_valid:
            if overwrite is False:
                logger.info(f"QSIPrep output exists for {subject_id}, skipping")
                return
            elif overwrite is None:
                # Check using overwrite policy
                policy = OverwritePolicy(overwrite=False, prompt=False)
                if not should_overwrite_path(
                    output_dir, policy=policy, logger=logger, label="QSIPrep output"
                ):
                    logger.info(f"QSIPrep output exists for {subject_id}, skipping")
                    return

    # Create output directories
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(project_dir) / "derivatives" / ".qsiprep_work"
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
    )

    try:
        # Build Docker command
        builder = DockerCommandBuilder(project_dir)
        cmd = builder.build_qsiprep_cmd(config)
    except DockerBuildError as e:
        raise PreprocessError(f"Failed to build QSIPrep command: {e}")

    # Ensure image is available
    if not pull_image_if_needed(
        const.QSI_QSIPREP_IMAGE, image_tag, logger
    ):
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
        raise PreprocessError(f"QSIPrep failed with exit code {returncode}")

    # Validate output
    is_valid, error_msg = validate_qsiprep_output(project_dir, subject_id)
    if not is_valid:
        raise PreprocessError(f"QSIPrep output validation failed: {error_msg}")

    logger.info(f"QSIPrep completed successfully for subject {subject_id}")
