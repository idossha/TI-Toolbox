#!/usr/bin/env python
"""
DICOM-to-NIfTI conversion with BIDS-compliant naming.

Wraps ``dcm2niix`` to convert DICOM series into NIfTI files that follow
the BIDS naming convention (``sub-{id}_{modality}.nii.gz``).

Public API
----------
run_dicom_to_nifti
    Convert DICOM files for a subject to BIDS-compliant NIfTI.

See Also
--------
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
"""

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from tit.paths import get_path_manager
from .utils import CommandRunner, PreprocessError

_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
_DICOM_SUFFIXES = (".dcm", ".dicom")
_EXTRACTED_ARCHIVES_DIR = ".extracted_archives"


def _is_archive(path: Path) -> bool:
    """Return ``True`` when *path* is a supported archive."""
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


def _find_dicom_files(dicom_dir: Path) -> list[Path]:
    """Return recursive ``.dcm`` and ``.dicom`` files under *dicom_dir*."""
    if not dicom_dir.exists():
        return []
    return sorted(
        path
        for path in dicom_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in _DICOM_SUFFIXES
    )


def _find_archives(modality_dir: Path, dicom_dir: Path) -> list[Path]:
    """Find supported archives directly in modality or modality/dicom folders."""
    archives: list[Path] = []
    for directory in (modality_dir, dicom_dir):
        if not directory.exists():
            continue
        archives.extend(
            path for path in directory.iterdir() if path.is_file() and _is_archive(path)
        )
    return sorted(set(archives))


def _archive_extract_dir(dicom_dir: Path, archive: Path) -> Path:
    """Return deterministic extraction directory for *archive*."""
    safe_name = archive.name.replace("/", "_").replace("\\", "_")
    return dicom_dir / _EXTRACTED_ARCHIVES_DIR / safe_name


def _safe_target(base_dir: Path, member_name: str) -> Path:
    """Resolve an archive member target and reject path traversal."""
    target = (base_dir / member_name).resolve()
    base = base_dir.resolve()
    if target != base and base not in target.parents:
        raise PreprocessError(f"Unsafe archive member path: {member_name}")
    return target


def _extract_zip(archive: Path, destination: Path) -> int:
    """Safely extract *archive* zip members into *destination*."""
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = _safe_target(destination, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def _extract_tar(archive: Path, destination: Path) -> int:
    """Safely extract *archive* tar members into *destination*."""
    count = 0
    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            target = _safe_target(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def _extract_archive(archive: Path, destination: Path) -> int:
    """Safely extract a supported archive into *destination*."""
    destination.mkdir(parents=True, exist_ok=True)
    if archive.name.lower().endswith(".zip"):
        return _extract_zip(archive, destination)
    return _extract_tar(archive, destination)


def _prepare_dicom_inputs(modality_dir: Path, dicom_dir: Path, logger) -> list[Path]:
    """Extract supported archives and return recursive DICOM files."""
    archives = _find_archives(modality_dir, dicom_dir)
    for archive in archives:
        destination = _archive_extract_dir(dicom_dir, archive)
        if destination.exists() and any(destination.iterdir()):
            logger.info(f"Using previously extracted {archive.name} at {destination}")
            continue
        try:
            extracted = _extract_archive(archive, destination)
        except (tarfile.TarError, zipfile.BadZipFile, OSError, PreprocessError) as exc:
            logger.warning(f"Could not extract {archive}: {exc}")
            continue
        logger.info(
            f"Extracted {extracted} file(s) from {archive.name} to {destination}"
        )

    dicom_files = _find_dicom_files(dicom_dir)
    if dicom_files:
        logger.info(f"Found {len(dicom_files)} DICOM file(s) under {dicom_dir}")
    else:
        logger.info(
            f"No .dcm or .dicom files found under {dicom_dir}; skipping conversion"
        )
    return dicom_files


def _convert_modality(
    dicom_dir: Path,
    output_dir: Path,
    subject_id: str,
    modality: str,
    logger,
    runner: CommandRunner | None,
) -> bool:
    """Convert DICOM files for a single modality to BIDS location."""
    modality_dir = dicom_dir.parent
    dicom_files = _prepare_dicom_inputs(modality_dir, dicom_dir, logger)
    if not dicom_files:
        return False

    bids_name = f"sub-{subject_id}_{modality}"
    if (output_dir / f"{bids_name}.nii.gz").exists():
        raise PreprocessError(
            f"Output already exists for {bids_name}. "
            "Remove the files manually before rerunning."
        )

    logger.info(f"Converting {modality} DICOMs from {dicom_dir}")
    cmd = [
        "dcm2niix",
        "-z",
        "y",
        "-b",
        "y",
        "-r",
        "y",
        "-f",
        bids_name,
        "-o",
        str(output_dir),
        str(dicom_dir),
    ]

    if runner:
        exit_code = runner.run(cmd, logger=logger)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)
        exit_code = result.returncode

    if exit_code != 0:
        logger.warning(f"dcm2niix failed for {modality}")
        return False

    logger.info(f"Created {bids_name}.nii.gz")
    return True


def run_dicom_to_nifti(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: CommandRunner | None = None,
) -> None:
    """Convert DICOM files to BIDS-compliant NIfTI for a subject.

    Looks for ``T1w`` and ``T2w`` DICOM directories under
    ``sourcedata/sub-{subject_id}/`` and converts each found modality
    using ``dcm2niix``. DICOM discovery is recursive under each
    modality's ``dicom/`` directory and includes ``.dcm`` and ``.dicom``
    files. Supported archives (``.zip``, ``.tar``, ``.tar.gz``, ``.tgz``)
    placed directly in the modality folder or its ``dicom/`` folder are
    safely extracted to ``dicom/.extracted_archives/`` before discovery.

    Parameters
    ----------
    project_dir : str
        BIDS project root directory.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    logger : logging.Logger
        Logger for progress messages.
    runner : CommandRunner or None, optional
        Subprocess runner for streaming output.

    Raises
    ------
    PreprocessError
        If output NIfTI files already exist for a modality.

    See Also
    --------
    run_pipeline : Full preprocessing pipeline.
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_PRE_DICOM):
        pm = get_path_manager(project_dir)
        sourcedata_dir = Path(pm.sourcedata_subject(subject_id))
        bids_anat_dir = Path(pm.bids_anat(subject_id))
        bids_anat_dir.mkdir(parents=True, exist_ok=True)

        converted = False
        for modality in ("T1w", "T2w"):
            dicom_dir = sourcedata_dir / modality / "dicom"
            if _convert_modality(
                dicom_dir, bids_anat_dir, subject_id, modality, logger, runner
            ):
                converted = True

        if not converted:
            logger.warning("No DICOM files found or converted")
