"""Optional FreeSurfer reconstruction in disposable, project-bound containers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from tit.paths import get_path_manager, validate_subject_id
from .qsi.docker_builder import resolve_fs_license_path
from .qsi.utils import get_inherited_dood_resources, format_memory_limit
from .utils import CommandRunner, PreprocessError, _find_anat_files

IMAGE = "freesurfer/freesurfer:7.4.1"
SUBREGIONS = frozenset({"thalamus", "hippo-amygdala"})


def validate_reconstruction(subject_id: str) -> None:
    """Require full recon-all outputs before running T1 subregion segmentation."""
    subject = Path(get_path_manager().freesurfer_subject(subject_id))
    required = (
        "scripts/recon-all.done",
        "mri/norm.mgz",
        "mri/aseg.mgz",
        "mri/wmparc.mgz",
    )
    missing = [name for name in required if not (subject / name).is_file()]
    if missing:
        raise PreprocessError(
            f"FreeSurfer subregions require a completed recon-all for sub-{subject_id}; "
            f"missing {', '.join(missing)}. FastSurfer segmentation alone is insufficient."
        )


def _remove_container(name: str, logger: logging.Logger) -> None:
    try:
        result = subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode and "No such container" not in result.stderr:
            logger.warning(
                "Could not remove FreeSurfer worker %s: %s", name, result.stderr.strip()
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Could not remove FreeSurfer worker %s: %s", name, exc)


def run_freesurfer(
    subject_id: str,
    *,
    recon_all: bool = True,
    subregions: list[str] | None = None,
    threads: int | None = None,
    runner: CommandRunner,
    logger: logging.Logger,
) -> None:
    """Run recon-all and/or subregions, retaining outputs but removing workers.

    Project data is bind-mounted; no Docker data volume is created. Job labels
    let cancellation also reap workers if the Python process is terminated.
    """
    subject_id = validate_subject_id(subject_id)
    targets = list(dict.fromkeys(subregions or []))
    if set(targets) - SUBREGIONS:
        raise PreprocessError(
            "FreeSurfer subregions must be thalamus or hippo-amygdala."
        )
    if not recon_all and not targets:
        raise PreprocessError("Select recon-all or at least one FreeSurfer subregion.")
    pm = get_path_manager()
    project = Path(pm.project_dir).resolve()
    host_root = os.environ.get("LOCAL_PROJECT_DIR")
    if not host_root and Path("/.dockerenv").exists():
        raise PreprocessError(
            "LOCAL_PROJECT_DIR is required to launch FreeSurfer from Docker."
        )
    host_project = Path(host_root or str(project))
    if not host_project.is_absolute():
        raise PreprocessError("LOCAL_PROJECT_DIR must be an absolute host path.")
    if not recon_all:
        validate_reconstruction(subject_id)
    license_path = resolve_fs_license_path()
    if license_path is None:
        raise PreprocessError(
            "FreeSurfer requires a license. Configure the FreeSurfer license before running."
        )
    subjects_dir = Path(pm.freesurfer())
    subject = Path(pm.freesurfer_subject(subject_id))
    commands = []
    if recon_all:
        args = ["recon-all", "-s", f"sub-{subject_id}", "-sd", str(subjects_dir)]
        # Resume existing reconstruction without importing T1 a second time.
        if not (subject / "mri/orig/001.mgz").is_file():
            t1, _ = _find_anat_files(subject_id)
            if not t1:
                raise PreprocessError(f"No T1 file found in {pm.bids_anat(subject_id)}")
            if not Path(t1).resolve().is_relative_to(project):
                raise PreprocessError(
                    "FreeSurfer T1 must be inside the project directory."
                )
            args.extend(["-i", str(t1)])
        commands.append(args)
    cpus, memory = get_inherited_dood_resources()
    # Match the scheduler's FreeSurfer reservation, not the whole server budget.
    cpus = min(cpus, max(1, int(threads))) if threads is not None else min(cpus, 2)
    if memory < 16:
        raise PreprocessError(
            "FreeSurfer requires at least 16 GiB of available container memory."
        )
    memory = 16
    if commands:
        commands[0].extend(["-all", "-parallel", "-openmp", str(cpus)])
    for target in targets:
        commands.append(
            [
                "segment_subregions",
                target,
                "--cross",
                f"sub-{subject_id}",
                "--sd",
                str(subjects_dir),
                "--threads",
                str(cpus),
            ]
        )
    subjects_dir.mkdir(parents=True, exist_ok=True)
    # A unique temporary bind avoids races between concurrent jobs' licenses.
    with tempfile.TemporaryDirectory(prefix=".freesurfer-", dir=project) as stage:
        staged_license = Path(stage) / "license.txt"
        shutil.copyfile(license_path, staged_license)
        staged_license.chmod(0o600)
        host_license = host_project / staged_license.relative_to(project)
        for index, command in enumerate(commands):
            if command[0] == "segment_subregions":
                validate_reconstruction(subject_id)
            name = f"tit-freesurfer-{uuid.uuid4().hex}"
            argv = [
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/amd64",
                "--name",
                name,
                "--label",
                "tit.kind=freesurfer",
                "--cpus",
                str(cpus),
                "--memory",
                format_memory_limit(memory),
            ]
            if job_id := os.environ.get("TIT_JOB_ID"):
                argv.extend(["--label", f"tit.job_id={job_id}"])
            argv.extend(
                [
                    "-e",
                    "FS_LICENSE=/run/license.txt",
                    "-e",
                    f"OMP_NUM_THREADS={cpus}",
                    "-v",
                    f"{host_project}:{project}",
                    "-v",
                    f"{host_license}:/run/license.txt:ro",
                    IMAGE,
                    *command,
                ]
            )
            logger.info("Running FreeSurfer %s for sub-%s", command[0], subject_id)
            try:
                code = runner.run(argv, logger=logger)
                if code != 0:
                    raise PreprocessError(
                        f"FreeSurfer {command[0]} failed for sub-{subject_id} (exit {code})."
                    )
            finally:
                _remove_container(name, logger)
            if index == 0 and recon_all:
                validate_reconstruction(subject_id)
