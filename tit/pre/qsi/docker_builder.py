#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Docker command builder for QSI containers.

This module constructs Docker run commands for QSIPrep and QSIRecon,
handling volume mounts, resource allocation, and pipeline arguments.
"""

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from tit import constants as const

# Custom pipeline YAMLs shipped in resources/qsirecon_pipelines/.
# These work around upstream QSIRecon bugs or missing features.
_CUSTOM_PIPELINE_MAP = {
    # dsi_studio_gqi without the connectivity node (avoids plot_reports bug
    # and the mandatory --atlases requirement in QSIRecon >= 1.2.0).
    "dsi_studio_gqi": "dsi_studio_gqi_scalar.yaml",
}
from .config import QSIPrepConfig, QSIReconConfig
from .utils import (
    get_host_project_dir,
    get_inherited_dood_resources,
    format_memory_limit,
)


class DockerBuildError(Exception):
    """Raised when Docker command construction fails."""


@dataclass
class DockerPaths:
    """Container-side mount points for QSI containers.

    QSI containers expect BIDS data at ``/data`` and write outputs to
    ``/out``.

    Attributes
    ----------
    bids_dir : str
        Container path for BIDS input data.
    output_dir : str
        Container path for pipeline outputs.
    work_dir : str
        Container path for intermediate working files.
    license_file : str
        Container path for the FreeSurfer license.
    """

    bids_dir: str = "/data"
    output_dir: str = "/out"
    work_dir: str = "/work"
    license_file: str = "/opt/freesurfer/license.txt"


class DockerCommandBuilder:
    """Build Docker ``run`` commands for QSIPrep and QSIRecon containers.

    Handles volume mounts (host ↔ container), resource limits (CPU /
    memory), FreeSurfer license staging, and custom pipeline YAML
    staging for Docker-outside-of-Docker (DooD) execution.

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project directory **inside the current
        container** (used to resolve relative paths).
    paths : DockerPaths or None, optional
        Container path configuration.  Uses ``DockerPaths()`` defaults
        when *None*.

    Attributes
    ----------
    project_dir : str
        Container-side BIDS project directory.
    paths : DockerPaths
        Resolved container path configuration.

    Raises
    ------
    DockerBuildError
        If Docker is not available or required paths cannot be resolved.

    See Also
    --------
    tit.pre.qsi.config : ``QSIPrepConfig`` and ``QSIReconConfig`` dataclasses.
    """

    def __init__(
        self,
        project_dir: str,
        paths: DockerPaths | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.paths = paths or DockerPaths()

        self._host_project_dir = get_host_project_dir()
        self._host_license_path = self._stage_fs_license()

    def _stage_fs_license(self) -> str | None:
        """Copy the FreeSurfer license into the project dir for DooD siblings."""
        src = Path(const.FS_LICENSE_PATH)
        if not src.is_file():
            return None
        dest = Path(self.project_dir) / ".freesurfer_license.txt"
        shutil.copy2(src, dest)
        return str(Path(self._host_project_dir) / ".freesurfer_license.txt")

    def _stage_custom_pipeline(self, yaml_filename: str) -> tuple[str, str]:
        """Stage a custom pipeline YAML into the project root for DooD mounting."""
        src = (
            Path(__file__).resolve().parents[3]
            / "resources"
            / "qsirecon_pipelines"
            / yaml_filename
        )
        if not src.is_file():
            raise DockerBuildError(f"Custom pipeline YAML not found: {src}")

        # Stage to project root — always exists, always writable
        staged_name = ".qsirecon_spec.yaml"
        dest = Path(self.project_dir) / staged_name
        shutil.copy2(src, dest)

        host_path = str(Path(self._host_project_dir) / staged_name)
        container_path = "/tmp/recon_spec.yaml"
        return container_path, host_path

    def build_qsiprep_cmd(self, config: QSIPrepConfig) -> list[str]:
        """
        Build Docker command for QSIPrep.

        Parameters
        ----------
        config : QSIPrepConfig
            QSIPrep configuration.

        Returns
        -------
        list[str]
            Complete Docker command as a list of arguments.
        """
        image = f"{const.QSI_QSIPREP_IMAGE}:{config.image_tag}"
        inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        effective_cpus = (
            config.resources.cpus
            if config.resources.cpus is not None
            else inherited_cpus
        )
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
            "--platform",
            "linux/amd64",
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
        cmd.extend(["-e", f"OMP_NUM_THREADS={config.resources.omp_threads}"])
        if self._host_license_path:
            cmd.extend(["-e", f"FS_LICENSE={self.paths.license_file}"])

        # Volume mounts - mount host project directory
        # BIDS data is at project root
        cmd.extend(["-v", f"{self._host_project_dir}:{self.paths.bids_dir}:ro"])

        qsiprep_output = str(Path(self._host_project_dir) / "derivatives" / "qsiprep")
        cmd.extend(["-v", f"{qsiprep_output}:{self.paths.output_dir}"])

        work_dir = str(Path(self._host_project_dir) / "derivatives" / ".qsiprep_work")
        cmd.extend(["-v", f"{work_dir}:{self.paths.work_dir}"])

        if self._host_license_path:
            cmd.extend(
                ["-v", f"{self._host_license_path}:{self.paths.license_file}:ro"]
            )

        cmd.append(image)

        # QSIPrep arguments
        cmd.extend(
            [
                self.paths.bids_dir,
                self.paths.output_dir,
                "participant",
            ]
        )

        cmd.extend(["--participant-label", config.subject_id])
        cmd.extend(["--output-resolution", str(config.output_resolution)])
        cmd.extend(["-w", self.paths.work_dir])
        cmd.extend(["--nthreads", str(effective_cpus)])
        cmd.extend(["--omp-nthreads", str(config.resources.omp_threads)])
        cmd.extend(["--mem-mb", str(effective_mem_gb * 1024)])

        if self._host_license_path:
            cmd.extend(["--fs-license-file", self.paths.license_file])

        if config.skip_bids_validation:
            cmd.append("--skip-bids-validation")

        cmd.extend(["--denoise-method", config.denoise_method])
        cmd.extend(["--unringing-method", config.unringing_method])

        if config.distortion_group_merge != "none":
            merge = (
                "concat"
                if config.distortion_group_merge == "concatenate"
                else config.distortion_group_merge
            )
            cmd.extend(["--distortion-group-merge", merge])

        return cmd

    def build_qsirecon_cmd(self, config: QSIReconConfig, recon_spec: str) -> list[str]:
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
        list[str]
            Complete Docker command as a list of arguments.
        """
        image = f"{const.QSI_QSIRECON_IMAGE}:{config.image_tag}"
        inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        effective_cpus = (
            config.resources.cpus
            if config.resources.cpus is not None
            else inherited_cpus
        )
        effective_mem_gb = (
            config.resources.memory_gb
            if config.resources.memory_gb is not None
            else inherited_mem_gb
        )

        cmd = [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--name",
            f"qsirecon_{config.subject_id}_{recon_spec.replace('-', '_')}_{uuid.uuid4().hex[:8]}",
        ]

        if config.use_gpu:
            cmd.extend(["--gpus", "all"])

        cmd.extend(
            [
                "--cpus",
                str(effective_cpus),
                "--memory",
                format_memory_limit(effective_mem_gb),
            ]
        )

        cmd.extend(["-e", f"OMP_NUM_THREADS={config.resources.omp_threads}"])
        if self._host_license_path:
            cmd.extend(["-e", f"FS_LICENSE={self.paths.license_file}"])

        qsiprep_output = str(Path(self._host_project_dir) / "derivatives" / "qsiprep")
        cmd.extend(["-v", f"{qsiprep_output}:{self.paths.bids_dir}:ro"])

        qsirecon_output = str(Path(self._host_project_dir) / "derivatives" / "qsirecon")
        cmd.extend(["-v", f"{qsirecon_output}:{self.paths.output_dir}"])

        work_dir = str(Path(self._host_project_dir) / "derivatives" / ".qsirecon_work")
        cmd.extend(["-v", f"{work_dir}:{self.paths.work_dir}"])

        if self._host_license_path:
            cmd.extend(
                ["-v", f"{self._host_license_path}:{self.paths.license_file}:ro"]
            )

        # Determine recon spec and stage custom YAML before appending image,
        # so we can add the file mount with the other -v flags.
        container_spec = recon_spec
        if not config.atlases and recon_spec in _CUSTOM_PIPELINE_MAP:
            container_spec, host_yaml = self._stage_custom_pipeline(
                _CUSTOM_PIPELINE_MAP[recon_spec]
            )
            cmd.extend(["-v", f"{host_yaml}:{container_spec}:ro"])

        cmd.append(image)

        cmd.extend(
            [
                self.paths.bids_dir,
                self.paths.output_dir,
                "participant",
            ]
        )

        cmd.extend(["--participant-label", config.subject_id])
        cmd.extend(["--recon-spec", container_spec])
        cmd.extend(["--input-type", "qsiprep"])
        cmd.extend(["-w", self.paths.work_dir])
        cmd.extend(["--nthreads", str(effective_cpus)])
        cmd.extend(["--omp-nthreads", str(config.resources.omp_threads)])
        cmd.extend(["--mem-mb", str(effective_mem_gb * 1024)])

        if self._host_license_path:
            cmd.extend(["--fs-license-file", self.paths.license_file])

        if config.atlases:
            cmd.append("--atlases")
            cmd.extend(config.atlases)

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
