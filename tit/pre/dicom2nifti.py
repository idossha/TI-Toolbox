#!/usr/bin/env python
"""
DICOM to NIfTI conversion with BIDS-compliant naming.

Converts DICOM images to NIfTI format following BIDS naming conventions.
Handles T1w/T2w detection, compressed archives, and duplicate series.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from tit.core import get_path_manager
from tit.core.overwrite import OverwritePolicy, get_overwrite_policy
from .common import CommandRunner, PreprocessError


DICOM_EXTENSIONS = (".dcm", ".ima", ".dicom")
ARCHIVE_EXTENSIONS = (".tgz", ".tar.gz")


def _detect_modality(json_path: Path, fallback: str) -> str:
    """Detect modality (T1w/T2w) from DICOM metadata."""
    try:
        metadata = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return fallback

    series_desc = str(metadata.get("SeriesDescription", "")).lower()
    if "t1" in series_desc or "mprage" in series_desc:
        return "T1w"
    if "t2" in series_desc or "cube" in series_desc:
        return "T2w"

    seq_name = str(metadata.get("SequenceName", "")).lower()
    if "t1" in seq_name:
        return "T1w"
    if "t2" in seq_name:
        return "T2w"

    return fallback


def _find_dicom_files(directory: Path) -> list[Path]:
    """Recursively find all DICOM files in a directory."""
    files = []
    for ext in DICOM_EXTENSIONS:
        files.extend(directory.rglob(f"*{ext}"))
        files.extend(directory.rglob(f"*{ext.upper()}"))
    return files


def _extract_archives(source_dir: Path, target_dir: Path, logger) -> None:
    """Extract compressed DICOM archives."""
    if not source_dir.exists():
        return

    for archive in source_dir.iterdir():
        if not archive.is_file():
            continue
        if not any(str(archive).endswith(ext) for ext in ARCHIVE_EXTENSIONS):
            continue

        logger.info(f"Extracting archive: {archive.name}")
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                subprocess.check_call(
                    ["tar", "-xzf", str(archive), "-C", temp_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                dicom_files = _find_dicom_files(Path(temp_dir))
                if dicom_files:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for f in dicom_files:
                        shutil.move(str(f), str(target_dir / f.name))
                    logger.info(f"Extracted {len(dicom_files)} DICOM files")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to extract {archive.name}: {e}")


def _run_dcm2niix(
    source_dir: Path,
    output_dir: Path,
    logger,
    runner: Optional[CommandRunner],
) -> bool:
    """Run dcm2niix conversion."""
    cmd = ["dcm2niix", "-z", "y", "-b", "y", "-o", str(output_dir), str(source_dir)]

    if runner:
        exit_code = runner.run(cmd, logger=logger)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)
        exit_code = result.returncode

    return exit_code == 0


def _move_to_extra(bids_anat_dir: Path, json_file: Path, nii_file: Path, logger) -> None:
    """Move extra series to separate directory."""
    extra_dir = bids_anat_dir / "extra"
    extra_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(json_file), str(extra_dir / json_file.name))
    shutil.move(str(nii_file), str(extra_dir / nii_file.name))
    logger.warning(f"Additional series moved to {extra_dir}")


def _process_converted_files(
    temp_dir: Path,
    bids_anat_dir: Path,
    subject_id: str,
    expected_modality: str,
    policy: OverwritePolicy,
    logger,
) -> bool:
    """Process converted NIfTI files and move to BIDS location."""
    processed = False
    written = {"T1w": False, "T2w": False}

    for json_file in sorted(temp_dir.glob("*.json")):
        nii_file = json_file.with_suffix(".nii.gz")
        if not nii_file.exists():
            nii_file = json_file.with_suffix(".nii")
            if not nii_file.exists():
                continue

        modality = _detect_modality(json_file, expected_modality)

        # Skip duplicates
        if written[modality]:
            _move_to_extra(bids_anat_dir, json_file, nii_file, logger)
            continue

        bids_name = f"sub-{subject_id}_{modality}"
        target_nii = bids_anat_dir / f"{bids_name}.nii.gz"
        target_json = bids_anat_dir / f"{bids_name}.json"

        # Handle existing files
        if target_nii.exists() or target_json.exists():
            should_overwrite = policy.overwrite
            if not should_overwrite and policy.prompt:
                import sys
                if sys.stdin.isatty():
                    ans = input(f"Output exists for {subject_id}. Overwrite? [y/N]: ")
                    should_overwrite = ans.strip().lower() in ("y", "yes")

            if should_overwrite:
                target_nii.unlink(missing_ok=True)
                target_json.unlink(missing_ok=True)
            else:
                _move_to_extra(bids_anat_dir, json_file, nii_file, logger)
                continue

        # Compress if needed
        if not str(nii_file).endswith(".gz"):
            subprocess.run(["gzip", "-f", str(nii_file)], check=True, capture_output=True)
            nii_file = nii_file.parent / (nii_file.name + ".gz")

        shutil.move(str(json_file), str(target_json))
        shutil.move(str(nii_file), str(target_nii))
        logger.info(f"Created {target_nii.name}")

        written[modality] = True
        processed = True

    return processed


def _process_modality(
    modality: str,
    sourcedata_dir: Path,
    bids_anat_dir: Path,
    subject_id: str,
    pm,
    policy: OverwritePolicy,
    logger,
    runner: Optional[CommandRunner],
) -> bool:
    """Process DICOM files for a specific modality."""
    source_dir = sourcedata_dir / modality
    dicom_dir = Path(pm.path("sourcedata_dicom", subject_id=subject_id, modality=modality))
    dicom_dir.mkdir(parents=True, exist_ok=True)

    _extract_archives(source_dir, dicom_dir, logger)

    if not dicom_dir.exists() or not _find_dicom_files(dicom_dir):
        return False

    logger.info(f"Processing {modality} DICOM files")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        if not _run_dcm2niix(dicom_dir, temp_path, logger, runner):
            raise PreprocessError(f"dcm2niix failed for {modality}")

        return _process_converted_files(
            temp_path, bids_anat_dir, subject_id, modality, policy, logger
        )


def run_dicom_to_nifti(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    overwrite: Optional[bool] = None,
    prompt_overwrite: Optional[bool] = None,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Convert DICOMs to BIDS-compliant NIfTI for a subject.

    Parameters
    ----------
    project_dir : str
        BIDS project root directory.
    subject_id : str
        Subject identifier without the 'sub-' prefix.
    logger : logging.Logger
        Logger for progress and command output.
    overwrite : bool, optional
        Force overwrite of existing outputs.
    prompt_overwrite : bool, optional
        Allow interactive overwrite prompt.
    runner : CommandRunner, optional
        Subprocess runner for streaming output.
    """
    if not shutil.which("dcm2niix"):
        raise PreprocessError("dcm2niix is not installed or not in PATH")

    pm = get_path_manager()
    pm.project_dir = project_dir

    sourcedata_dir = Path(pm.path("sourcedata_subject", subject_id=subject_id))
    bids_anat_dir = Path(pm.path("bids_anat", subject_id=subject_id))
    bids_anat_dir.mkdir(parents=True, exist_ok=True)

    policy = get_overwrite_policy(overwrite, prompt_overwrite)

    converted = False
    for modality in ("T1w", "T2w"):
        if _process_modality(
            modality, sourcedata_dir, bids_anat_dir, subject_id, pm, policy, logger, runner
        ):
            converted = True

    if not converted:
        logger.warning("No DICOM files found or converted")
