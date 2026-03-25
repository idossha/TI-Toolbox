#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Utility functions for QSI integration.

This module provides path resolution, validation, and helper functions
for the QSI Docker-out-of-Docker integration.
"""

import logging
import math
import os
import subprocess
from pathlib import Path

from tit import constants as const


def resolve_host_project_path(container_path: str) -> str:
    """
    Resolve a container path to the corresponding host path for Docker mounts.

    When running inside the SimNIBS container, project directories are mounted
    at /mnt/$PROJECT_DIR_NAME. However, sibling containers (QSIPrep/QSIRecon)
    need to mount the original host path, not the container path.

    The LOCAL_PROJECT_DIR environment variable contains the host machine's
    absolute path to the project directory.

    Parameters
    ----------
    container_path : str
        Path as seen from inside the SimNIBS container (e.g., /mnt/myproject).

    Returns
    -------
    str
        The corresponding host path for Docker volume mounts.

    Raises
    ------
    ValueError
        If LOCAL_PROJECT_DIR is not set or the path cannot be resolved.
    """
    local_project_dir = os.environ.get(const.ENV_LOCAL_PROJECT_DIR)
    if not local_project_dir:
        raise ValueError(
            f"{const.ENV_LOCAL_PROJECT_DIR} environment variable is not set. "
            "This is required for spawning sibling Docker containers."
        )

    # If the container_path starts with /mnt/, replace with host path
    container_path = str(container_path)
    if container_path.startswith(const.DOCKER_MOUNT_PREFIX):
        # Extract the relative path after /mnt/project_name/
        parts = container_path.split(os.sep)
        # /mnt/project_name -> parts[0]='', parts[1]='mnt', parts[2]=project_name
        if len(parts) > 3:
            relative_path = os.sep.join(parts[3:])
            return os.path.join(local_project_dir, relative_path)
        else:
            return local_project_dir

    return container_path


def get_host_project_dir() -> str:
    """
    Get the host machine's project directory path.

    Returns
    -------
    str
        Absolute path to the project directory on the host machine.

    Raises
    ------
    ValueError
        If LOCAL_PROJECT_DIR is not set.
    """
    local_project_dir = os.environ.get(const.ENV_LOCAL_PROJECT_DIR)
    if not local_project_dir:
        raise ValueError(
            f"{const.ENV_LOCAL_PROJECT_DIR} environment variable is not set. "
            "This is required for spawning sibling Docker containers."
        )
    return local_project_dir


def check_image_exists(image: str, tag: str) -> bool:
    """
    Check if a Docker image exists locally.

    Parameters
    ----------
    image : str
        Docker image name (e.g., 'pennlinc/qsiprep').
    tag : str
        Image tag (e.g., '1.1.1').

    Returns
    -------
    bool
        True if the image exists locally.
    """
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", f"{image}:{tag}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pull_image_if_needed(image: str, tag: str, logger: logging.Logger) -> bool:
    """
    Pull a Docker image if it doesn't exist locally.

    Parameters
    ----------
    image : str
        Docker image name.
    tag : str
        Image tag.
    logger : logging.Logger
        Logger for status messages.

    Returns
    -------
    bool
        True if image is available (either existed or was pulled successfully).
    """
    full_image = f"{image}:{tag}"

    if check_image_exists(image, tag):
        logger.debug(f"Docker image {full_image} already exists locally")
        return True

    logger.info(f"Pulling Docker image {full_image}...")
    try:
        result = subprocess.run(
            ["docker", "pull", full_image],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minutes timeout for large images
        )
        if result.returncode == 0:
            logger.info(f"Successfully pulled {full_image}")
            return True
        else:
            logger.error(f"Failed to pull {full_image}: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Timed out pulling {full_image}")
        return False
    except (FileNotFoundError, OSError) as e:
        logger.error(f"Error pulling {full_image}: {e}")
        return False


def validate_bids_dwi(
    project_dir: str, subject_id: str, logger: logging.Logger
) -> tuple[bool, str | None]:
    """
    Validate that DWI data exists for a subject in BIDS format.

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project root.
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    logger : logging.Logger
        Logger for status messages.

    Returns
    -------
    tuple[bool, str | None]
        (is_valid, error_message). If valid, error_message is None.
    """
    dwi_dir = Path(project_dir) / f"sub-{subject_id}" / "dwi"

    if not dwi_dir.exists():
        return False, f"DWI directory not found: {dwi_dir}"

    # Look for DWI NIfTI files
    dwi_files = list(dwi_dir.glob("*_dwi.nii*"))
    if not dwi_files:
        return False, f"No DWI NIfTI files found in {dwi_dir}"

    # Check for bval and bvec files
    bval_files = list(dwi_dir.glob("*.bval"))
    bvec_files = list(dwi_dir.glob("*.bvec"))

    if not bval_files:
        return False, f"No .bval files found in {dwi_dir}"
    if not bvec_files:
        return False, f"No .bvec files found in {dwi_dir}"

    logger.debug(f"Found valid DWI data for sub-{subject_id}")
    return True, None


def validate_qsiprep_output(
    project_dir: str, subject_id: str
) -> tuple[bool, str | None]:
    """
    Validate that QSIPrep output exists for a subject.

    Parameters
    ----------
    project_dir : str
        Path to the project root.
    subject_id : str
        Subject identifier.

    Returns
    -------
    tuple[bool, str | None]
        (is_valid, error_message). If valid, error_message is None.
    """
    qsiprep_dir = Path(project_dir) / "derivatives" / "qsiprep" / f"sub-{subject_id}"

    if not qsiprep_dir.exists():
        return False, f"QSIPrep output directory not found: {qsiprep_dir}"

    # Check for preprocessed DWI
    dwi_dir = qsiprep_dir / "dwi"
    if not dwi_dir.exists():
        return False, f"QSIPrep DWI output not found: {dwi_dir}"

    # Check for at least one preprocessed DWI file
    preproc_files = list(dwi_dir.glob("*_dwi.nii*"))
    if not preproc_files:
        return False, f"No preprocessed DWI files found in {dwi_dir}"

    return True, None


def get_freesurfer_license_path() -> str | None:
    """
    Get the FreeSurfer license file path suitable for DooD volume mounts.

    Resolution order:
    1. LOCAL_FS_LICENSE env var (host path, preferred for DooD mounts)
    2. FS_LICENSE env var (container path, fallback)

    Returns
    -------
    str | None
        Path to the license file, or None if not found.
    """
    local_fs_license = os.environ.get(const.ENV_LOCAL_FS_LICENSE)
    if local_fs_license:
        return local_fs_license
    return os.environ.get("FS_LICENSE")


def format_memory_limit(memory_gb: int) -> str:
    """
    Format memory limit for Docker --memory flag.

    Parameters
    ----------
    memory_gb : int
        Memory limit in gigabytes.

    Returns
    -------
    str
        Formatted memory string (e.g., '32g').
    """
    return f"{memory_gb}g"


def _read_first_line(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readline().strip()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError):
        return None


def _parse_cpuset(value: str) -> int | None:
    """
    Parse cpuset string like '0-3,6,8-9' to an integer count.
    """
    value = (value or "").strip()
    if not value:
        return None

    count = 0
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                start = int(start_s)
                end = int(end_s)
            except ValueError:
                return None
            if end < start:
                return None
            count += end - start + 1
        else:
            try:
                int(part)
            except ValueError:
                return None
            count += 1
    return count or None


def _get_total_mem_bytes_from_proc() -> int | None:
    """
    Read total system memory visible inside the current container.
    """
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    # MemTotal:      154457636 kB
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb * 1024
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    return None


def get_container_resource_limits() -> tuple[int | None, int | None]:
    """
    Return (cpu_limit, mem_limit_bytes) for the *current* container.

    - cpu_limit: integer number of CPUs available via cgroups/cpuset if limited,
      otherwise None.
    - mem_limit_bytes: memory limit in bytes via cgroups if limited,
      otherwise None.
    """
    # ---- Memory ----
    mem_limit_bytes: int | None = None

    # cgroup v2
    mem_max = _read_first_line("/sys/fs/cgroup/memory.max")
    if mem_max and mem_max != "max":
        try:
            val = int(mem_max)
            # Treat extremely large values as effectively unlimited
            if val > 1 << 60:
                mem_limit_bytes = None
            else:
                mem_limit_bytes = val
        except ValueError:
            mem_limit_bytes = None
    else:
        # cgroup v1
        mem_v1 = _read_first_line("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        if mem_v1:
            try:
                val = int(mem_v1)
                if val > 1 << 60:
                    mem_limit_bytes = None
                else:
                    mem_limit_bytes = val
            except ValueError:
                mem_limit_bytes = None

    # ---- CPU ----
    cpu_limit: int | None = None

    # Prefer cpuset if present
    cpuset = _read_first_line(
        "/sys/fs/cgroup/cpuset.cpus.effective"
    ) or _read_first_line("/sys/fs/cgroup/cpuset/cpuset.cpus")
    cpuset_count = _parse_cpuset(cpuset) if cpuset else None
    if cpuset_count:
        cpu_limit = cpuset_count

    # cgroup v2 cpu.max
    cpu_max = _read_first_line("/sys/fs/cgroup/cpu.max")
    if cpu_max and cpu_max.strip():
        parts = cpu_max.split()
        if len(parts) >= 2 and parts[0] != "max":
            try:
                quota = int(parts[0])
                period = int(parts[1])
                if quota > 0 and period > 0:
                    derived = max(1, math.floor(quota / period))
                    cpu_limit = min(cpu_limit, derived) if cpu_limit else derived
            except ValueError:
                pass
    else:
        # cgroup v1 cpu quota
        quota_s = _read_first_line("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period_s = _read_first_line("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if quota_s and period_s:
            try:
                quota = int(quota_s)
                period = int(period_s)
                if quota > 0 and period > 0:
                    derived = max(1, math.floor(quota / period))
                    cpu_limit = min(cpu_limit, derived) if cpu_limit else derived
            except ValueError:
                pass

    return cpu_limit, mem_limit_bytes


def get_inherited_dood_resources() -> tuple[int, int]:
    """
    Determine DooD resource defaults that match the current container.

    Returns (cpus, memory_gb) with conservative rounding.
    """
    cpu_limit, mem_limit_bytes = get_container_resource_limits()

    cpus = cpu_limit or (os.cpu_count() or 1)

    if mem_limit_bytes is None:
        mem_limit_bytes = _get_total_mem_bytes_from_proc()

    if mem_limit_bytes is None:
        # Last-resort fallback: keep existing historical default
        return int(cpus), int(const.QSI_DEFAULT_MEMORY_GB)

    # Convert bytes -> GiB (floor), ensure minimum 4GB
    mem_gb = max(4, int(mem_limit_bytes // (1024**3)))
    return int(cpus), int(mem_gb)
