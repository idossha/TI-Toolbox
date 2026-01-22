#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Utility functions for QSI integration.

This module provides path resolution, validation, and helper functions
for the QSI Docker-out-of-Docker integration.
"""

from __future__ import annotations

import logging
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
