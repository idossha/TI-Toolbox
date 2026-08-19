#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Utility functions for QSI integration.

This module provides path resolution, validation, and helper functions
for the QSI Docker-out-of-Docker integration.
"""

import gzip
import json
import logging
import math
import os
import shutil
import struct
import subprocess
from pathlib import Path

from tit import constants as const
from tit.paths import get_path_manager

_NIFTI1_HEADER_SIZE = 348
_NIFTI2_HEADER_SIZE = 540

# QSIPrep warns below this and assumes the series is a reverse-phase-encode scan.
_SHORT_DWI_VOLUMES = 16


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
        Image tag (e.g., '26.0.0').

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


def validate_dood_environment(
    project_dir: str,
    *,
    require_gpu: bool = False,
) -> tuple[bool, str | None]:
    """Validate Docker-outside-of-Docker prerequisites before QSI runs."""
    if shutil.which("docker") is None:
        return False, "Docker CLI not found in PATH."

    local_project_dir = os.environ.get(const.ENV_LOCAL_PROJECT_DIR)
    if not local_project_dir:
        return (
            False,
            f"{const.ENV_LOCAL_PROJECT_DIR} is not set; sibling Docker containers "
            "cannot mount the host project directory.",
        )

    if not Path(project_dir).exists():
        return False, f"Project directory does not exist: {project_dir}"

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False, "Docker did not respond to `docker info` within 15 seconds."
    except OSError as exc:
        return False, f"Docker is not accessible: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "docker info failed").strip()
        return False, f"Docker daemon is not accessible: {detail}"

    if require_gpu:
        docker_info = f"{result.stdout}\n{result.stderr}".lower()
        if "nvidia" not in docker_info:
            return False, "Docker GPU runtime is not available."

    return True, None


def nifti_stem(path: Path) -> str:
    """Return *path*'s name without its ``.nii`` or ``.nii.gz`` extension."""
    name = path.name
    for suffix in (".nii.gz", ".nii"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def read_nifti_dims(path: Path) -> tuple[int, ...] | None:
    """Return the 8-element ``dim`` field of a NIfTI header, or ``None``.

    Parsed from the raw header rather than through nibabel so that a
    validation pass costs one 540-byte read instead of opening the image,
    and so it stays available in environments without nibabel. Both
    NIfTI-1 (``dim`` is ``int16[8]`` at offset 40) and NIfTI-2 (``int64[8]``
    at offset 16) are recognised, in either byte order.
    """
    try:
        opener = gzip.open if path.name.lower().endswith(".gz") else open
        with opener(path, "rb") as handle:  # type: ignore[operator]
            header = handle.read(_NIFTI2_HEADER_SIZE)
    except (OSError, EOFError, gzip.BadGzipFile):
        return None

    if len(header) < 80:
        return None

    for endian in ("<", ">"):
        (sizeof_hdr,) = struct.unpack(endian + "i", header[:4])
        if sizeof_hdr == _NIFTI1_HEADER_SIZE:
            return struct.unpack(endian + "8h", header[40:56])
        if sizeof_hdr == _NIFTI2_HEADER_SIZE:
            return struct.unpack(endian + "8q", header[16:80])
    return None


def _nifti_volume_count(path: Path) -> int | None:
    """Return the number of volumes in a NIfTI file, or ``None`` if unreadable."""
    dims = read_nifti_dims(path)
    if dims is None or dims[0] < 1:
        return None
    return int(dims[4]) if dims[0] >= 4 else 1


def _read_numeric_rows(path: Path) -> list[list[float]] | None:
    """Return the whitespace-separated numbers in *path*, one list per line.

    ``str.split()`` treats ``\\r`` as whitespace, so a file written with
    Windows line endings parses the same as a Unix one. ``None`` means the
    file held a token that is not a number.
    """
    rows: list[list[float]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                tokens = line.split()
                if not tokens:
                    continue
                rows.append([float(token) for token in tokens])
    except (OSError, ValueError):
        return None
    return rows


def _find_gradient_file(dwi_file: Path, suffix: str, project_dir: Path) -> Path | None:
    """Locate the ``.bval``/``.bvec`` that belongs to *dwi_file*.

    The sibling with the identical stem is what every tool in the stack
    expects, so it wins. BIDS inheritance also lets the file sit higher in
    the tree, so the subject and dataset roots are searched as a fallback --
    rejecting an inherited-but-valid dataset would be worse than the delay
    of a late failure.
    """
    stem = nifti_stem(dwi_file)
    sibling = dwi_file.with_name(f"{stem}{suffix}")
    if sibling.is_file():
        return sibling

    for parent in (dwi_file.parent.parent, project_dir):
        for name in (f"{stem}{suffix}", f"dwi{suffix}"):
            candidate = parent / name
            if candidate.is_file():
                return candidate
    return None


def _describe_gradient_mismatch(dwi_file: Path, suffix: str) -> str:
    """Explain which gradient files exist beside *dwi_file*, for an error message."""
    present = sorted(p.name for p in dwi_file.parent.glob(f"*{suffix}"))
    if not present:
        return f"no {suffix} file exists anywhere in {dwi_file.parent}"
    return f"{dwi_file.parent} contains {', '.join(present)} instead"


def _validate_gradient_table(
    dwi_file: Path, project_dir: Path, logger: logging.Logger
) -> str | None:
    """Return an error message for *dwi_file*'s gradient table, or ``None``.

    Every check here mirrors one that would otherwise surface as an opaque
    failure deep inside QSIPrep -- DSI Studio reports a mismatched or
    unparseable table as ``cannot find bval/bvec file`` after the run has
    already spent an hour on the anatomical workflow.
    """
    stem = nifti_stem(dwi_file)

    bval_file = _find_gradient_file(dwi_file, ".bval", project_dir)
    if bval_file is None:
        return (
            f"{dwi_file.name} has no matching {stem}.bval "
            f"({_describe_gradient_mismatch(dwi_file, '.bval')}). "
            "A DWI series and its gradient table must share one basename."
        )
    bvec_file = _find_gradient_file(dwi_file, ".bvec", project_dir)
    if bvec_file is None:
        return (
            f"{dwi_file.name} has no matching {stem}.bvec "
            f"({_describe_gradient_mismatch(dwi_file, '.bvec')}). "
            "A DWI series and its gradient table must share one basename."
        )

    bval_rows = _read_numeric_rows(bval_file)
    if bval_rows is None:
        return f"{bval_file} is not readable as a list of b-values."
    bvals = [value for row in bval_rows for value in row]
    if not bvals:
        return f"{bval_file} is empty; it must hold one b-value per volume."

    bvec_rows = _read_numeric_rows(bvec_file)
    if bvec_rows is None:
        return f"{bvec_file} is not readable as a list of gradient directions."
    if not bvec_rows:
        return f"{bvec_file} is empty; it must hold one direction per volume."

    # FSL writes 3 rows of N; a transposed N-by-3 table is common enough to accept.
    if len(bvec_rows) == 3 and len({len(row) for row in bvec_rows}) == 1:
        vectors = list(zip(*bvec_rows))
    elif all(len(row) == 3 for row in bvec_rows):
        vectors = [tuple(row) for row in bvec_rows]
    else:
        return (
            f"{bvec_file} is not a gradient table: expected 3 rows of N values "
            f"(or N rows of 3), found {len(bvec_rows)} rows of "
            f"{sorted({len(row) for row in bvec_rows})}."
        )

    if len(vectors) != len(bvals):
        return (
            f"{bval_file.name} lists {len(bvals)} b-values but "
            f"{bvec_file.name} lists {len(vectors)} directions. "
            "They must describe the same volumes."
        )

    n_volumes = _nifti_volume_count(dwi_file)
    if n_volumes is None:
        return f"{dwi_file} is not a readable NIfTI file."
    if n_volumes != len(bvals):
        return (
            f"{dwi_file.name} has {n_volumes} volume(s) but "
            f"{bval_file.name} lists {len(bvals)} b-value(s). "
            "The gradient table belongs to a different series -- this usually "
            "means more than one DWI series was converted into the same "
            "folder and the wrong one kept the BIDS name."
        )

    weighted = [
        vector for vector, b in zip(vectors, bvals) if b > const.QSI_B0_THRESHOLD
    ]
    directions = {tuple(round(component, 3) for component in v) for v in weighted}
    if len(directions) < const.QSI_MIN_DWI_DIRECTIONS:
        return (
            f"{dwi_file.name} has only {len(directions)} distinct "
            f"diffusion-weighted direction(s) above b={const.QSI_B0_THRESHOLD:g} "
            f"({len(bvals)} volume(s) total). Fitting a diffusion tensor needs at "
            f"least {const.QSI_MIN_DWI_DIRECTIONS}. This is usually a derived "
            "series (ADC, FA, TRACEW) or a reverse-phase-encode b=0 block rather "
            "than the diffusion acquisition."
        )

    if n_volumes < _SHORT_DWI_VOLUMES:
        logger.warning(
            f"{dwi_file.name} has only {n_volumes} volumes. QSIPrep treats a "
            "series this short as a reverse-phase-encode scan; check that this "
            "is really the diffusion acquisition."
        )
    logger.debug(
        f"{dwi_file.name}: {n_volumes} volumes, {len(directions)} directions, "
        f"b-values up to {max(bvals):g}"
    )
    return None


def validate_bids_dwi(
    project_dir: str, subject_id: str, logger: logging.Logger
) -> tuple[bool, str | None]:
    """
    Validate that usable DWI data exists for a subject in BIDS format.

    Checks that every ``*_dwi.nii*`` under the subject's ``dwi/`` folder has a
    gradient table that matches it: same basename, parseable, one b-value and
    one direction per volume, and enough distinct directions to fit a tensor.

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

    See Also
    --------
    ensure_total_readout_time : The sidecar metadata QSIPrep needs alongside this.
    """
    dwi_dir = Path(get_path_manager(project_dir).bids_dwi(subject_id))

    if not dwi_dir.exists():
        return False, f"DWI directory not found: {dwi_dir}"

    dwi_files = sorted(
        path for path in dwi_dir.glob("*_dwi.nii*") if not path.name.startswith(".")
    )
    if not dwi_files:
        return False, f"No DWI NIfTI files found in {dwi_dir}"

    for dwi_file in dwi_files:
        error = _validate_gradient_table(dwi_file, Path(project_dir), logger)
        if error:
            return False, error

    logger.debug(f"Found valid DWI data for sub-{subject_id}")
    return True, None


def _subject_has_fieldmaps(project_dir: str, subject_id: str) -> bool:
    """Return ``True`` when the subject has any ``fmap/`` image."""
    subject_dir = Path(get_path_manager(project_dir).bids_subject(subject_id))
    return any(subject_dir.glob("**/fmap/*.nii*"))


def _derive_total_readout_time(metadata: dict) -> tuple[float | None, str]:
    """Derive TotalReadoutTime from other sidecar fields.

    Returns ``(value, provenance)``; *value* is ``None`` when the sidecar
    carries nothing to derive it from.
    """
    estimated = metadata.get("EstimatedTotalReadoutTime")
    if isinstance(estimated, (int, float)) and estimated > 0:
        return float(estimated), "EstimatedTotalReadoutTime"

    echo_spacing = metadata.get("EffectiveEchoSpacing")
    recon_pe = metadata.get("ReconMatrixPE") or metadata.get("AcquisitionMatrixPE")
    if (
        isinstance(echo_spacing, (int, float))
        and echo_spacing > 0
        and isinstance(recon_pe, (int, float))
        and recon_pe > 1
    ):
        return (
            float(echo_spacing) * (int(recon_pe) - 1),
            "EffectiveEchoSpacing x (ReconMatrixPE - 1)",
        )

    return None, ""


def ensure_total_readout_time(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    repair: bool = True,
) -> tuple[bool, str | None]:
    """Make sure every DWI sidecar carries the metadata QSIPrep dereferences.

    QSIPrep formats ``TotalReadoutTime`` into an FSL ``acqp`` line for *every*
    run, including ones with no fieldmap and no TOPUP, and its sidecar reader
    has no fallback when the key is absent -- the run dies with
    ``TypeError: must be real number, not NoneType`` only after the anatomical
    workflow has finished, an hour in.

    A missing value is derived from ``EstimatedTotalReadoutTime`` or from
    ``EffectiveEchoSpacing`` and the phase-encode matrix size when the sidecar
    carries them. Failing that, and only when the subject has no fieldmap and
    a single phase-encoding direction, a conventional placeholder is written:
    in that configuration no susceptibility correction is estimated, so the
    readout time is a common scale factor that cancels. Anything else is
    reported rather than guessed, because a wrong readout time does bias
    distortion correction once a fieldmap is present.

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project root.
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    logger : logging.Logger
        Logger for status messages.
    repair : bool, optional
        Write the derived value back into the sidecar. When *False* a missing
        value is reported as an error instead. Default: True.

    Returns
    -------
    tuple[bool, str | None]
        (is_ok, error_message). If ok, error_message is None.
    """
    dwi_dir = Path(get_path_manager(project_dir).bids_dwi(subject_id))
    dwi_files = sorted(
        path for path in dwi_dir.glob("*_dwi.nii*") if not path.name.startswith(".")
    )

    has_fieldmaps = _subject_has_fieldmaps(project_dir, subject_id)
    pe_directions: set[str] = set()
    pending: list[tuple[Path, dict]] = []

    for dwi_file in dwi_files:
        stem = nifti_stem(dwi_file)
        sidecar = dwi_file.with_name(f"{stem}.json")
        if not sidecar.is_file():
            return False, (
                f"{dwi_file.name} has no {stem}.json sidecar. QSIPrep reads "
                "PhaseEncodingDirection and TotalReadoutTime from it."
            )
        try:
            with open(sidecar, "r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return False, f"{sidecar} could not be read as JSON: {exc}"

        pe_dir = metadata.get("PhaseEncodingDirection")
        if not pe_dir:
            return False, (
                f"{sidecar.name} has no PhaseEncodingDirection. QSIPrep needs it "
                "to build the eddy acquisition parameters and cannot run without it."
            )
        pe_directions.add(pe_dir)

        readout = metadata.get("TotalReadoutTime")
        if isinstance(readout, (int, float)) and readout > 0:
            continue
        pending.append((sidecar, metadata))

    for sidecar, metadata in pending:
        value, provenance = _derive_total_readout_time(metadata)
        if value is None:
            if has_fieldmaps or len(pe_directions) > 1:
                return False, (
                    f"{sidecar.name} has no TotalReadoutTime and nothing to derive "
                    "it from (EstimatedTotalReadoutTime, or EffectiveEchoSpacing "
                    "with ReconMatrixPE). This subject has fieldmaps or more than "
                    "one phase-encoding direction, so the value affects distortion "
                    "correction and must come from the acquisition -- add it to "
                    "the sidecar before rerunning."
                )
            value = const.QSI_FALLBACK_TOTAL_READOUT_TIME
            provenance = (
                "placeholder (no fieldmap and a single phase-encoding "
                "direction, so the value cancels)"
            )

        if not repair:
            return False, (
                f"{sidecar.name} has no TotalReadoutTime. QSIPrep will fail on it. "
                f"Derivable value: {value:g} s from {provenance}."
            )

        metadata["TotalReadoutTime"] = value
        try:
            with open(sidecar, "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=2, sort_keys=True)
                handle.write("\n")
        except OSError as exc:
            return False, f"Could not write TotalReadoutTime into {sidecar}: {exc}"

        logger.warning(
            f"Added TotalReadoutTime={value:g}s to {sidecar.name} "
            f"[{provenance}]. QSIPrep cannot run without this field."
        )

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
    qsiprep_dir = Path(get_path_manager(project_dir).qsiprep_subject(subject_id))

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
