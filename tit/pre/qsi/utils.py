#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Utility functions for QSI integration.

This module provides path resolution, validation, and helper functions
for the QSI Docker-out-of-Docker integration.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from tit.core import constants as const


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


def check_docker_available() -> Tuple[bool, str]:
    """
    Check if Docker CLI is available and the Docker daemon is running.

    Returns
    -------
    Tuple[bool, str]
        (is_available, message) tuple. If not available, message contains
        the error description.
    """
    # Check if docker command exists
    if not shutil.which("docker"):
        return False, "Docker CLI not found in PATH"

    # Check if Docker daemon is running
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, f"Docker daemon not responding: {result.stderr.strip()}"
        return True, "Docker is available"
    except subprocess.TimeoutExpired:
        return False, "Docker daemon timed out"
    except Exception as e:
        return False, f"Failed to check Docker: {e}"


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
    except Exception:
        return False


def pull_image_if_needed(
    image: str, tag: str, logger: logging.Logger
) -> bool:
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
    except Exception as e:
        logger.error(f"Error pulling {full_image}: {e}")
        return False


def validate_bids_dwi(
    project_dir: str, subject_id: str, logger: logging.Logger
) -> Tuple[bool, Optional[str]]:
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
    Tuple[bool, Optional[str]]
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
) -> Tuple[bool, Optional[str]]:
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
    Tuple[bool, Optional[str]]
        (is_valid, error_message). If valid, error_message is None.
    """
    qsiprep_dir = (
        Path(project_dir) / "derivatives" / "qsiprep" / f"sub-{subject_id}"
    )

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


def get_freesurfer_license_path() -> Optional[str]:
    """
    Get the FreeSurfer license file path.

    QSIPrep and QSIRecon require a FreeSurfer license for certain operations.
    This function checks common locations for the license file.

    Returns
    -------
    Optional[str]
        Path to the license file, or None if not found.
    """
    # Check environment variable
    fs_license = os.environ.get("FS_LICENSE")
    if fs_license and os.path.isfile(fs_license):
        return fs_license

    # Check FREESURFER_HOME
    fs_home = os.environ.get("FREESURFER_HOME")
    if fs_home:
        license_path = os.path.join(fs_home, "license.txt")
        if os.path.isfile(license_path):
            return license_path

    # Check common locations
    common_paths = [
        "/usr/local/freesurfer/license.txt",
        "/opt/freesurfer/license.txt",
        os.path.expanduser("~/.freesurfer/license.txt"),
    ]

    for path in common_paths:
        if os.path.isfile(path):
            return path

    return None


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


def _read_first_line(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readline().strip()
    except Exception:
        return None


def _parse_cpuset(value: str) -> Optional[int]:
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


def _get_total_mem_bytes_from_proc() -> Optional[int]:
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
    except Exception:
        return None
    return None


def get_container_resource_limits() -> Tuple[Optional[int], Optional[int]]:
    """
    Return (cpu_limit, mem_limit_bytes) for the *current* container.

    - cpu_limit: integer number of CPUs available via cgroups/cpuset if limited,
      otherwise None.
    - mem_limit_bytes: memory limit in bytes via cgroups if limited,
      otherwise None.
    """
    # ---- Memory ----
    mem_limit_bytes: Optional[int] = None

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
    cpu_limit: Optional[int] = None

    # Prefer cpuset if present
    cpuset = _read_first_line("/sys/fs/cgroup/cpuset.cpus.effective") or _read_first_line(
        "/sys/fs/cgroup/cpuset/cpuset.cpus"
    )
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


def get_inherited_dood_resources() -> Tuple[int, int]:
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
