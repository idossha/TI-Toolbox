#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
QSIRecon runner for TI-Toolbox.

This module provides functions to run QSIRecon as a sibling Docker container
using the Docker-out-of-Docker (DooD) pattern.
"""

import logging
from pathlib import Path

from tit import constants as const
from tit.pre.utils import CommandRunner, PreprocessError

from .config import QSIReconConfig, ResourceConfig
from .docker_builder import DockerCommandBuilder, DockerBuildError
from .utils import pull_image_if_needed, validate_qsiprep_output


def run_qsirecon(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    recon_specs: list[str] | None = None,
    atlases: list[str] | None = None,
    use_gpu: bool = False,
    cpus: int | None = None,
    memory_gb: int | None = None,
    omp_threads: int = const.QSI_DEFAULT_OMP_THREADS,
    image_tag: str = const.QSI_QSIRECON_IMAGE_TAG,
    skip_odf_reports: bool = True,
    runner: CommandRunner | None = None,
) -> None:
    """
    Run QSIRecon reconstruction for a subject's preprocessed DWI data.

    This function spawns QSIRecon Docker containers as siblings to the
    current SimNIBS container using Docker-out-of-Docker (DooD).

    QSIRecon requires QSIPrep output as input. Multiple reconstruction
    specs can be run sequentially.

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project root directory.
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    logger : logging.Logger
        Logger for status messages.
    recon_specs : list[str] | None, optional
        List of reconstruction specifications to run. Default: ['dsi_studio_gqi'].
        This default produces DTI tensors for SimNIBS anisotropic modeling.
        Other specs (mrtrix_*, dipy_*, amico_noddi, pyafq_*, etc.) remain available.
    atlases : list[str] | None, optional
        List of atlases for connectivity analysis. Default: None (no connectivity).
        Not needed for DTI extraction. Set to e.g. ['4S156Parcels', 'AAL116']
        if connectivity matrices are desired.
    use_gpu : bool, optional
        Enable GPU acceleration. Default: False.
    cpus : int | None, optional
        Number of CPUs to allocate. None = inherit from current container.
    memory_gb : int | None, optional
        Memory limit in GB. None = inherit from current container.
    omp_threads : int, optional
        Number of OpenMP threads. Default: 1.
    image_tag : str, optional
        QSIRecon Docker image tag. Default from ``constants.QSI_QSIRECON_IMAGE_TAG``.
    skip_odf_reports : bool, optional
        Skip ODF report generation. Default: True.
    runner : CommandRunner | None, optional
        Command runner for subprocess execution.

    Raises
    ------
    PreprocessError
        If QSIRecon fails or prerequisites are not met.
    """
    # Default to dsi_studio_gqi for SimNIBS DTI extraction
    if recon_specs is None:
        recon_specs = [const.QSI_DEFAULT_RECON_SPEC]

    # Atlases are optional — not needed for DTI extraction
    # Pass through None/empty to skip connectivity workflows

    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_PRE_QSIRECON):
        logger.info(
            f"Starting QSIRecon for subject {subject_id} with specs: {recon_specs}, atlases: {atlases}"
        )

        # Validate QSIPrep output exists
        is_valid, error_msg = validate_qsiprep_output(project_dir, subject_id)
        if not is_valid:
            raise PreprocessError(
                f"QSIPrep output validation failed: {error_msg}. "
                "Run QSIPrep first before running QSIRecon."
            )

        # No mkdir here — Docker's `-v` creates host directories automatically.
        # Creating them from SimNIBS fails on Docker Desktop due to phantom
        # bind-mount entries left by previous sibling containers.
        output_base = Path(project_dir) / "derivatives" / "qsirecon"

        # Build configuration
        config = QSIReconConfig(
            subject_id=subject_id,
            recon_specs=recon_specs,
            atlases=atlases,
            use_gpu=use_gpu,
            resources=ResourceConfig(
                cpus=cpus,
                memory_gb=memory_gb,
                omp_threads=omp_threads,
            ),
            image_tag=image_tag,
            skip_odf_reports=skip_odf_reports,
        )

        try:
            # Build Docker command builder
            builder = DockerCommandBuilder(project_dir)
        except DockerBuildError as e:
            raise PreprocessError(f"Failed to initialize Docker: {e}")

        # Ensure image is available
        if not pull_image_if_needed(const.QSI_QSIRECON_IMAGE, image_tag, logger):
            raise PreprocessError(
                f"Failed to pull QSIRecon image: {const.QSI_QSIRECON_IMAGE}:{image_tag}"
            )

        # Create runner if not provided
        if runner is None:
            runner = CommandRunner()

        # Check for existing output before starting any specs
        subject_output_dir = output_base / f"sub-{subject_id}"
        if subject_output_dir.exists():
            raise PreprocessError(
                f"QSIRecon output already exists at {subject_output_dir}. "
                "Remove the directory manually before rerunning."
            )

        # Run each recon spec
        for spec in recon_specs:
            logger.info(f"Running QSIRecon spec: {spec}")

            try:
                cmd = builder.build_qsirecon_cmd(config, spec)
            except DockerBuildError as e:
                raise PreprocessError(f"Failed to build QSIRecon command: {e}")

            # Log the command for debugging
            logger.debug(f"QSIRecon command: {' '.join(cmd)}")

            # Run the container
            logger.info(f"Running QSIRecon {spec} for subject {subject_id}...")
            returncode = runner.run(cmd, logger=logger)

            if returncode != 0:
                raise PreprocessError(f"QSIRecon {spec} failed with exit code {returncode}")

            logger.info(f"QSIRecon {spec} completed for subject {subject_id}")

        logger.info(f"QSIRecon completed successfully for subject {subject_id}")


def list_available_recon_specs() -> list[str]:
    """
    Return list of available QSIRecon reconstruction specifications.

    Returns
    -------
    list[str]
        List of available recon spec names.
    """
    return list(const.QSI_RECON_SPECS)


def list_available_atlases() -> list[str]:
    """
    Return list of available atlases for connectivity analysis.

    Returns
    -------
    list[str]
        List of available atlas names.
    """
    return list(const.QSI_ATLASES)
