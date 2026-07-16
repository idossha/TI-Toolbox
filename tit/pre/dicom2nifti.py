#!/usr/bin/env python
"""Source-image ingestion with BIDS-compliant naming.

Converts each modality found under ``sourcedata/sub-{id}/`` into a
BIDS-named NIfTI (``sub-{id}_{suffix}.nii.gz``). DICOM series are
converted with ``dcm2niix``; a modality folder that already holds a
NIfTI is copied into place instead.

Public API
----------
run_dicom_to_nifti
    Ingest every supported modality for a subject.
MODALITIES
    Supported modalities and their BIDS datatype directories.

See Also
--------
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
"""

import gzip
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Iterator

from tit.paths import get_path_manager
from .utils import CommandRunner, PreprocessError

_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
_DICOM_SUFFIXES = (".dcm", ".dicom")
_NIFTI_SUFFIXES = (".nii.gz", ".nii")
_SIDECAR_SUFFIXES = (".json", ".bval", ".bvec")
_EXTRACTED_ARCHIVES_DIR = "extracted_archives"

# Source folder name (also the BIDS suffix) -> BIDS datatype directory.
#
# Single source of truth: tit.pre.preflight derives its rerun/cleanup list
# from this table, so a modality only has to be added here.
#
# ``ct`` is a deliberate local extension. BIDS has no CT datatype and no CT
# suffix -- BEP024 has been an unmerged draft since 2018 -- so no CT layout
# validates today. We write anat/sub-{id}_ct.nii.gz because that matches both
# BEP024's proposed suffix (making a future migration a directory move with no
# rename) and the majority of published OpenNeuro datasets carrying a head CT.
# tit.pre.utils.ensure_bidsignore keeps the validator quiet about it.
MODALITIES: tuple[tuple[str, str], ...] = (
    ("T1w", "anat"),
    ("T2w", "anat"),
    ("ct", "anat"),
    ("dwi", "dwi"),
)


def _has_suffix(name: str, suffixes: tuple[str, ...]) -> bool:
    """Return ``True`` when *name* ends with any of *suffixes* (case-insensitive)."""
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in suffixes)


def _iter_files(directory: Path) -> Iterator[Path]:
    """Yield regular files under *directory*, skipping dotfiles and unreadable entries.

    Dotfiles are filtered by name *before* any ``stat`` call, which is what
    makes this safe rather than merely tidy. macOS seeds bind mounts with
    AppleDouble ``._*`` siblings whose ``stat`` raises ``EPERM`` inside Docker,
    and Python 3.11's ``Path.is_file`` only swallows ENOENT/ENOTDIR/EBADF/ELOOP
    -- ``EPERM`` propagates and aborts the whole scan. ``dcm2niix`` skips
    dotfiles by the same rule, and BIDS reserves them for system use.

    The ``OSError`` guards cover the rest: filesystems that report
    ``DT_UNKNOWN`` make ``os.scandir`` fall back to a real ``stat`` syscall,
    so an unreadable non-dot entry must not abort the scan either.
    """
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    stack.append(Path(entry.path))
                elif entry.is_file():
                    yield Path(entry.path)
            except OSError:
                continue


def _find_files(directory: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Return sorted files under *directory* whose name ends with one of *suffixes*."""
    return sorted(
        path for path in _iter_files(directory) if _has_suffix(path.name, suffixes)
    )


def _is_archive(path: Path) -> bool:
    """Return ``True`` when *path* is a supported archive."""
    return _has_suffix(path.name, _ARCHIVE_SUFFIXES)


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


def _extract_archives(modality_dir: Path, logger) -> None:
    """Extract every archive under *modality_dir* into ``extracted_archives/``."""
    for archive in _find_files(modality_dir, _ARCHIVE_SUFFIXES):
        # Never re-extract our own output, or extraction would recurse.
        if _EXTRACTED_ARCHIVES_DIR in archive.parts:
            continue
        destination = modality_dir / _EXTRACTED_ARCHIVES_DIR / archive.name
        if destination.exists() and any(_iter_files(destination)):
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


def _modality_source_dir(sourcedata_dir: Path, modality: str) -> Path:
    """Return the source folder for *modality*, matching its name case-insensitively.

    Users name the folder ``CT`` as readily as ``ct``, and ``DWI`` as ``dwi``.
    """
    default = sourcedata_dir / modality
    if default.exists() or not sourcedata_dir.exists():
        return default
    try:
        entries = sorted(os.scandir(sourcedata_dir), key=lambda entry: entry.name)
    except OSError:
        return default
    for entry in entries:
        if entry.name.startswith(".") or entry.name.lower() != modality.lower():
            continue
        try:
            if entry.is_dir():
                return Path(entry.path)
        except OSError:
            continue
    return default


def _nifti_stem(path: Path) -> str:
    """Return *path*'s name without its NIfTI extension (``.nii`` or ``.nii.gz``)."""
    for suffix in _NIFTI_SUFFIXES:
        if path.name.lower().endswith(suffix):
            return path.name[: -len(suffix)]
    return path.stem


def _copy_sidecars(source: Path, output_dir: Path, bids_name: str, logger) -> None:
    """Copy any ``.json``/``.bval``/``.bvec`` sitting beside *source*.

    The ``.bval``/``.bvec`` pair is what makes a copied DWI usable: QSIPrep
    rejects a diffusion series without them.
    """
    stem = _nifti_stem(source)
    for suffix in _SIDECAR_SUFFIXES:
        sidecar = source.with_name(f"{stem}{suffix}")
        if not sidecar.exists():
            continue
        shutil.copyfile(sidecar, output_dir / f"{bids_name}{suffix}")
        logger.info(f"Copied {sidecar.name} -> {bids_name}{suffix}")


def _copy_nifti(source: Path, output_dir: Path, bids_name: str, logger) -> bool:
    """Copy an existing NIfTI *source* into *output_dir* under its BIDS name."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{bids_name}.nii.gz"
    if source.name.lower().endswith(".gz"):
        shutil.copyfile(source, target)
    else:
        # Compress with stdlib gzip: nibabel's gzip save is unreliable on
        # Docker bind mounts, and this avoids loading the volume into memory.
        with source.open("rb") as src, gzip.open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    logger.info(f"Copied {source.name} -> {target.name}")
    _copy_sidecars(source, output_dir, bids_name, logger)
    return True


def _check_dcm2niix_outputs(output_dir: Path, bids_name: str, logger) -> bool:
    """Confirm dcm2niix produced the expected NIfTI and flag extra series."""
    produced = sorted(path.name for path in output_dir.glob(f"{bids_name}*"))
    expected = f"{bids_name}.nii.gz"
    if expected not in produced:
        logger.warning(
            f"dcm2niix produced no {expected} "
            f"(found: {', '.join(produced) if produced else 'nothing'})"
        )
        return False
    # dcm2niix appends a bare letter on name collisions (sub-01_T1wa.nii.gz),
    # which is not a BIDS name and is ignored by every downstream step.
    extra = [name for name in produced if not name.startswith(f"{bids_name}.")]
    if extra:
        logger.warning(
            f"More than one series was present, so dcm2niix suffixed the extras: "
            f"{', '.join(extra)}. Only {expected} is used downstream — keep one "
            f"series per modality folder if that is not the one you want."
        )
    logger.info(f"Created {expected}")
    return True


def _run_dcm2niix(
    input_dir: Path,
    output_dir: Path,
    bids_name: str,
    logger,
    runner: CommandRunner | None,
) -> bool:
    """Convert the DICOMs under *input_dir* into ``{bids_name}.nii.gz``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Converting DICOMs from {input_dir}")
    cmd = [
        "dcm2niix",
        "-z",
        "y",
        "-b",
        "y",
        # Search depth: dcm2niix defaults to 5, which a deep archive layout can
        # exceed. 9 is its maximum. It skips dotfiles on its own.
        "-d",
        "9",
        "-f",
        bids_name,
        "-o",
        str(output_dir),
        str(input_dir),
    ]

    if runner:
        exit_code = runner.run(cmd, logger=logger)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)
        exit_code = result.returncode

    if exit_code != 0:
        logger.warning(f"dcm2niix failed for {bids_name} (exit code {exit_code})")
        return False

    return _check_dcm2niix_outputs(output_dir, bids_name, logger)


def _ingest_modality(
    modality_dir: Path,
    output_dir: Path,
    subject_id: str,
    modality: str,
    logger,
    runner: CommandRunner | None,
) -> bool:
    """Ingest one modality folder into its BIDS destination.

    DICOMs win when both are present: they carry the metadata dcm2niix needs
    to write a full sidecar, so a stray NIfTI never shadows the real series.
    """
    bids_name = f"sub-{subject_id}_{modality}"
    if (output_dir / f"{bids_name}.nii.gz").exists():
        raise PreprocessError(
            f"Output already exists for {bids_name}. "
            "Remove the files manually before rerunning."
        )

    _extract_archives(modality_dir, logger)

    dicom_files = _find_files(modality_dir, _DICOM_SUFFIXES)
    if dicom_files:
        logger.info(f"Found {len(dicom_files)} DICOM file(s) under {modality_dir}")
        return _run_dcm2niix(modality_dir, output_dir, bids_name, logger, runner)

    nifti_files = _find_files(modality_dir, _NIFTI_SUFFIXES)
    if nifti_files:
        if len(nifti_files) > 1:
            logger.warning(
                f"Found {len(nifti_files)} NIfTI files under {modality_dir}; "
                f"using {nifti_files[0].name} and ignoring the rest."
            )
        return _copy_nifti(nifti_files[0], output_dir, bids_name, logger)

    logger.info(
        f"No DICOM (.dcm/.dicom) or NIfTI (.nii/.nii.gz) files found under "
        f"{modality_dir}; skipping {modality}"
    )
    return False


def run_dicom_to_nifti(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: CommandRunner | None = None,
) -> None:
    """Ingest a subject's source images into BIDS-named NIfTI files.

    Looks for a ``T1w``, ``T2w``, ``ct``, and ``dwi`` folder under
    ``sourcedata/sub-{subject_id}/`` (folder names are matched
    case-insensitively) and ingests each one that exists. Anatomical images
    and CT go to the subject's ``anat/`` folder, diffusion images to ``dwi/``
    (with their ``.bval``/``.bvec`` sidecars).

    Each modality folder is searched recursively. Supported archives
    (``.zip``, ``.tar``, ``.tar.gz``, ``.tgz``) are safely extracted to
    ``extracted_archives/`` first. DICOM files (``.dcm``/``.dicom``) are then
    converted with ``dcm2niix``; if the folder holds no DICOMs but does hold a
    NIfTI, that file is copied into place instead (compressing a bare ``.nii``
    on the way). Dotfiles are ignored throughout.

    CT is written as ``anat/sub-{id}_ct.nii.gz``. This is a local convention,
    not BIDS -- see :data:`MODALITIES`.

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
        If an output NIfTI already exists for a modality.

    See Also
    --------
    run_pipeline : Full preprocessing pipeline.
    MODALITIES : Supported modalities and their BIDS datatype directories.
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_PRE_DICOM):
        pm = get_path_manager(project_dir)
        sourcedata_dir = Path(pm.sourcedata_subject(subject_id))

        converted = False
        for modality, datatype in MODALITIES:
            modality_dir = _modality_source_dir(sourcedata_dir, modality)
            if not modality_dir.exists():
                continue
            output_dir = Path(pm.bids_datatype(subject_id, datatype))
            if _ingest_modality(
                modality_dir, output_dir, subject_id, modality, logger, runner
            ):
                converted = True

        if not converted:
            logger.warning("No DICOM or NIfTI files found or converted")
