#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Docker command builder for QSI containers.

This module constructs Docker run commands for QSIPrep and QSIRecon,
handling volume mounts, resource allocation, and pipeline arguments.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from tit.core import constants as const
from .config import QSIPrepConfig, QSIReconConfig
from .utils import (
    check_docker_available,
    get_host_project_dir,
    get_freesurfer_license_path,
    get_inherited_dood_resources,
    format_memory_limit,
)


class DockerBuildError(Exception):
    """Raised when Docker command construction fails."""


@dataclass
class DockerPaths:
    """
    Container paths for QSI containers.

    QSI containers expect BIDS data at /data and outputs at /out.
    """

    bids_dir: str = "/data"
    output_dir: str = "/out"
    work_dir: str = "/work"
    license_file: str = "/opt/freesurfer/license.txt"


class DockerCommandBuilder:
    """
    Builds Docker commands for QSIPrep and QSIRecon.

    This class handles the complexity of constructing Docker run commands
    with proper volume mounts, resource limits, and pipeline arguments.

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project directory (container path).
    paths : Optional[DockerPaths]
        Container path configuration. Uses defaults if not provided.

    Raises
    ------
    DockerBuildError
        If Docker is not available or required paths cannot be resolved.
    """

    def __init__(
        self,
        project_dir: str,
        paths: Optional[DockerPaths] = None,
    ) -> None:
        # Validate Docker availability
        available, message = check_docker_available()
        if not available:
            raise DockerBuildError(f"Docker is not available: {message}")

        self.project_dir = project_dir
        self.paths = paths or DockerPaths()

        # Get host project directory for volume mounts
        try:
            self._host_project_dir = get_host_project_dir()
        except ValueError as e:
            raise DockerBuildError(str(e))

        # Get FreeSurfer license path
        self._fs_license = get_freesurfer_license_path()

    def build_qsiprep_cmd(self, config: QSIPrepConfig) -> List[str]:
        """
        Build Docker command for QSIPrep.

        Parameters
        ----------
        config : QSIPrepConfig
            QSIPrep configuration.

        Returns
        -------
        List[str]
            Complete Docker command as a list of arguments.
        """
        image = f"{const.QSI_QSIPREP_IMAGE}:{config.image_tag}"
        inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        effective_cpus = config.resources.cpus if config.resources.cpus is not None else inherited_cpus
        effective_mem_gb = (
            config.resources.memory_gb
            if config.resources.memory_gb is not None
            else inherited_mem_gb
        )

        # Build base docker run command
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            f"qsiprep_{config.subject_id}_{uuid.uuid4().hex[:8]}",
        ]

        # Resource limits
        cmd.extend(
            [
                "--cpus",
                str(effective_cpus),
                "--memory",
                format_memory_limit(effective_mem_gb),
            ]
        )

        # Environment variables
        cmd.extend(
            [
                "-e",
                f"OMP_NUM_THREADS={config.resources.omp_threads}",
            ]
        )

        # Volume mounts - mount host project directory
        # BIDS data is at project root
        cmd.extend(["-v", f"{self._host_project_dir}:{self.paths.bids_dir}:ro"])

        # QSIPrep output goes to derivatives/qsiprep
        qsiprep_output = str(
            Path(self._host_project_dir) / "derivatives" / "qsiprep"
        )
        cmd.extend(["-v", f"{qsiprep_output}:{self.paths.output_dir}"])

        # Work directory for intermediate files
        work_dir = str(Path(self._host_project_dir) / "derivatives" / ".qsiprep_work")
        cmd.extend(["-v", f"{work_dir}:{self.paths.work_dir}"])

        # FreeSurfer license
        if self._fs_license:
            cmd.extend(
                ["-v", f"{self._fs_license}:{self.paths.license_file}:ro"]
            )

        # Image
        cmd.append(image)

        # QSIPrep arguments
        # Input and output directories (container paths)
        cmd.extend(
            [
                self.paths.bids_dir,
                self.paths.output_dir,
                "participant",
            ]
        )

        # Subject filter
        cmd.extend(["--participant-label", config.subject_id])

        # Output resolution
        cmd.extend(["--output-resolution", str(config.output_resolution)])

        # Work directory
        cmd.extend(["-w", self.paths.work_dir])

        # Resource settings
        cmd.extend(["--nthreads", str(effective_cpus)])
        cmd.extend(["--omp-nthreads", str(config.resources.omp_threads)])
        cmd.extend(["--mem-mb", str(effective_mem_gb * 1024)])

        # FreeSurfer license
        if self._fs_license:
            cmd.extend(["--fs-license-file", self.paths.license_file])

        # Optional flags
        if config.skip_bids_validation:
            cmd.append("--skip-bids-validation")

        if config.denoise_method != "dwidenoise":
            cmd.extend(["--denoise-method", config.denoise_method])

        if config.unringing_method != "mrdegibbs":
            cmd.extend(["--unringing-method", config.unringing_method])

        if config.distortion_group_merge != "none":
            cmd.extend(
                ["--distortion-group-merge", config.distortion_group_merge]
            )

        return cmd

    def build_qsirecon_cmd(
        self, config: QSIReconConfig, recon_spec: str
    ) -> List[str]:
        """
        Build Docker command for QSIRecon with a specific recon spec.

        Parameters
        ----------
        config : QSIReconConfig
            QSIRecon configuration.
        recon_spec : str
            The reconstruction specification to use.

        Returns
        -------
        List[str]
            Complete Docker command as a list of arguments.
        """
        image = f"{const.QSI_QSIRECON_IMAGE}:{config.image_tag}"
        inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        effective_cpus = config.resources.cpus if config.resources.cpus is not None else inherited_cpus
        effective_mem_gb = (
            config.resources.memory_gb
            if config.resources.memory_gb is not None
            else inherited_mem_gb
        )

        # Build base docker run command
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            f"qsirecon_{config.subject_id}_{recon_spec.replace('-', '_')}_{uuid.uuid4().hex[:8]}",
        ]

        # GPU support
        if config.use_gpu:
            cmd.extend(["--gpus", "all"])

        # Resource limits
        cmd.extend(
            [
                "--cpus",
                str(effective_cpus),
                "--memory",
                format_memory_limit(effective_mem_gb),
            ]
        )

        # Environment variables
        cmd.extend(
            [
                "-e",
                f"OMP_NUM_THREADS={config.resources.omp_threads}",
            ]
        )

        # Volume mounts
        # QSIPrep output is the input for QSIRecon
        qsiprep_output = str(
            Path(self._host_project_dir) / "derivatives" / "qsiprep"
        )
        cmd.extend(["-v", f"{qsiprep_output}:{self.paths.bids_dir}:ro"])

        # QSIRecon output goes to derivatives/qsirecon
        qsirecon_output = str(
            Path(self._host_project_dir) / "derivatives" / "qsirecon"
        )
        cmd.extend(["-v", f"{qsirecon_output}:{self.paths.output_dir}"])

        # Work directory for intermediate files
        work_dir = str(
            Path(self._host_project_dir) / "derivatives" / ".qsirecon_work"
        )
        cmd.extend(["-v", f"{work_dir}:{self.paths.work_dir}"])

        # FreeSurfer license
        if self._fs_license:
            cmd.extend(
                ["-v", f"{self._fs_license}:{self.paths.license_file}:ro"]
            )

        # Image
        cmd.append(image)

        # QSIRecon arguments
        # Input and output directories (container paths)
        cmd.extend(
            [
                self.paths.bids_dir,
                self.paths.output_dir,
                "participant",
            ]
        )

        # Subject filter
        cmd.extend(["--participant-label", config.subject_id])

        # Recon specification
        cmd.extend(["--recon-spec", recon_spec])

        # Work directory
        cmd.extend(["-w", self.paths.work_dir])

        # Resource settings
        cmd.extend(["--nthreads", str(effective_cpus)])
        cmd.extend(["--omp-nthreads", str(config.resources.omp_threads)])
        cmd.extend(["--mem-mb", str(effective_mem_gb * 1024)])

        # FreeSurfer license
        if self._fs_license:
            cmd.extend(["--fs-license-file", self.paths.license_file])

        # Atlases for connectivity
        if config.atlases:
            for atlas in config.atlases:
                cmd.extend(["--atlases", atlas])

        # Optional flags
        if config.skip_odf_reports:
            cmd.append("--skip-odf-reports")

        return cmd

    def get_output_dir(self, pipeline: str) -> Path:
        """
        Get the output directory path for a pipeline.

        Parameters
        ----------
        pipeline : str
            Pipeline name ('qsiprep' or 'qsirecon').

        Returns
        -------
        Path
            Path to the output directory.
        """
        return Path(self._host_project_dir) / "derivatives" / pipeline
