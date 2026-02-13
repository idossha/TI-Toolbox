#!/usr/bin/env python
"""
DICOM to NIfTI conversion with BIDS-compliant naming.

Converts DICOM images to NIfTI format following BIDS naming conventions.
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


def _process_converted_files(
    temp_dir: Path,
    bids_anat_dir: Path,
    subject_id: str,
    expected_modality: str,
    policy: OverwritePolicy,
    logger,
) -> bool:
    """Process converted NIfTI files and move to BIDS location."""
    for json_file in temp_dir.glob("*.json"):
        nii_file = json_file.with_suffix(".nii.gz")
        if not nii_file.exists():
            nii_file = json_file.with_suffix(".nii")
            if not nii_file.exists():
                continue

        bids_name = f"sub-{subject_id}_{expected_modality}"
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
                logger.warning(f"Skipping {bids_name} (output exists)")
                continue

        # Compress if needed
        if not str(nii_file).endswith(".gz"):
            subprocess.run(
                ["gzip", "-f", str(nii_file)], check=True, capture_output=True
            )
            nii_file = nii_file.parent / (nii_file.name + ".gz")

        shutil.move(str(json_file), str(target_json))
        shutil.move(str(nii_file), str(target_nii))
        logger.info(f"Created {target_nii.name}")
        return True

    return False


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
    # DICOM files must be in dicom/ subdirectory
    dicom_dir = sourcedata_dir / modality / "dicom"

    if not dicom_dir.exists():
        return False

    # Check for .dcm files
    dcm_files = list(dicom_dir.glob("*.dcm"))
    if not dcm_files:
        return False

    logger.info(f"Processing {modality} DICOM files ({len(dcm_files)} files)")

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
            modality,
            sourcedata_dir,
            bids_anat_dir,
            subject_id,
            pm,
            policy,
            logger,
            runner,
        ):
            converted = True

    if not converted:
        logger.warning("No DICOM files found or converted")
