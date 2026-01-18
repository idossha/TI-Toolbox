#!/usr/bin/env simnibs_python
"""
DICOM to NIfTI conversion with T1/T2 detection.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from tit.core import get_path_manager
from .common import CommandRunner, PreprocessError
from tit.core.overwrite import OverwritePolicy, get_overwrite_policy


def _find_series_suffix(json_path: Path) -> str:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    series_desc = str(payload.get("SeriesDescription") or "")
    if "t1" in series_desc.lower():
        return "T1w"
    if "t2" in series_desc.lower():
        return "T2w"
    return ""


def _handle_compressed_dicom(source_dir: Path, target_dir: Path, logger) -> None:
    for tgz_file in source_dir.glob("*.tgz"):
        logger.info(f"Found compressed DICOM archive: {tgz_file.name}")
        temp_dir = Path(tempfile.mkdtemp())
        try:
            subprocess.check_call(["tar", "-xzf", str(tgz_file), "-C", str(temp_dir)])
            dicom_files = list(temp_dir.rglob("*.dcm"))
            dicom_files.extend(temp_dir.rglob("*.IMA"))
            dicom_files.extend(temp_dir.rglob("*.dicom"))
            if dicom_files:
                target_dir.mkdir(parents=True, exist_ok=True)
                for dicom_file in dicom_files:
                    shutil.move(str(dicom_file), str(target_dir / dicom_file.name))
                logger.info(f"Moved {len(dicom_files)} DICOM files into {target_dir}")
            else:
                logger.warning("No DICOM files found in extracted archive.")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _process_dicom_directory(
    source_dir: Path,
    bids_anat_dir: Path,
    subject_id: str,
    *,
    logger,
    policy: OverwritePolicy,
    runner: Optional[CommandRunner],
) -> None:
    if not source_dir.is_dir() or not any(source_dir.iterdir()):
        return

    logger.info(f"Processing DICOM files in {source_dir}")
    cmd = ["dcm2niix", "-z", "y", "-o", str(source_dir), str(source_dir)]
    if runner:
        exit_code = runner.run(cmd, logger=logger)
    else:
        exit_code = subprocess.call(cmd)
    if exit_code != 0:
        raise PreprocessError(f"dcm2niix failed for {source_dir}")

    wrote_t1w = False
    wrote_t2w = False

    for json_file in source_dir.glob("*.json"):
        nii_file = json_file.with_suffix(".nii.gz")
        if not nii_file.exists():
            continue

        if "T1w" in source_dir.parts:
            scan_suffix = "T1w"
        elif "T2w" in source_dir.parts:
            scan_suffix = "T2w"
        else:
            scan_suffix = _find_series_suffix(json_file)

        if not scan_suffix:
            base_name = f"sub-{subject_id}"
        else:
            base_name = f"sub-{subject_id}_{scan_suffix}"

        if scan_suffix == "T1w" and wrote_t1w:
            extra_dir = bids_anat_dir / "extra"
            extra_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(json_file), str(extra_dir / json_file.name))
            shutil.move(str(nii_file), str(extra_dir / nii_file.name))
            logger.warning(f"Additional T1w series moved to {extra_dir}")
            continue
        if scan_suffix == "T2w" and wrote_t2w:
            extra_dir = bids_anat_dir / "extra"
            extra_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(json_file), str(extra_dir / json_file.name))
            shutil.move(str(nii_file), str(extra_dir / nii_file.name))
            logger.warning(f"Additional T2w series moved to {extra_dir}")
            continue

        target_json = bids_anat_dir / f"{base_name}.json"
        target_nii = bids_anat_dir / f"{base_name}.nii.gz"

        if target_json.exists() or target_nii.exists():
            should_overwrite = policy.overwrite
            if not should_overwrite and policy.prompt and os.isatty(0):
                ans = (
                    input(
                        f"Canonical output exists for {subject_id}. Overwrite? [y/N]: "
                    )
                    .strip()
                    .lower()
                )
                should_overwrite = ans in {"y", "yes"}
            if should_overwrite:
                target_json.unlink(missing_ok=True)
                target_nii.unlink(missing_ok=True)
            else:
                extra_dir = bids_anat_dir / "extra"
                extra_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(json_file), str(extra_dir / json_file.name))
                shutil.move(str(nii_file), str(extra_dir / nii_file.name))
                logger.warning(
                    f"Canonical output exists; moved conversion to {extra_dir}"
                )
                continue

        bids_anat_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(json_file), str(target_json))
        shutil.move(str(nii_file), str(target_nii))
        logger.info(f"Renamed output to {target_nii.name}")

        if scan_suffix == "T1w":
            wrote_t1w = True
        elif scan_suffix == "T2w":
            wrote_t2w = True


def run_dicom_to_nifti(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    overwrite: Optional[bool] = None,
    prompt_overwrite: Optional[bool] = None,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Convert DICOMs to BIDS NIfTI for a subject.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the `sub-` prefix.
    logger : logging.Logger
        Logger used for progress and command output.
    overwrite : bool, optional
        Force overwrite of existing outputs.
    prompt_overwrite : bool, optional
        Allow interactive overwrite prompt.
    runner : CommandRunner, optional
        Subprocess runner used to stream output.
    """
    if not shutil.which("dcm2niix"):
        raise PreprocessError("dcm2niix is not installed.")

    pm = get_path_manager()
    pm.project_dir = project_dir
    sourcedata_dir = Path(pm.path("sourcedata_subject", subject_id=subject_id))
    bids_anat_dir = Path(pm.path("bids_anat", subject_id=subject_id))

    policy = get_overwrite_policy(overwrite, prompt_overwrite)

    t1_source = sourcedata_dir / "T1w"
    t2_source = sourcedata_dir / "T2w"
    t1_dicom_dir = Path(
        pm.path("sourcedata_dicom", subject_id=subject_id, modality="T1w")
    )
    t2_dicom_dir = Path(
        pm.path("sourcedata_dicom", subject_id=subject_id, modality="T2w")
    )

    t1_dicom_dir.mkdir(parents=True, exist_ok=True)
    t2_dicom_dir.mkdir(parents=True, exist_ok=True)
    bids_anat_dir.mkdir(parents=True, exist_ok=True)

    _handle_compressed_dicom(t1_source, t1_dicom_dir, logger)
    _handle_compressed_dicom(t2_source, t2_dicom_dir, logger)

    if not t1_dicom_dir.exists() and not t2_dicom_dir.exists():
        logger.warning("No DICOM directories found. Skipping conversion.")
        return

    if t1_dicom_dir.exists():
        _process_dicom_directory(
            t1_dicom_dir,
            bids_anat_dir,
            subject_id,
            logger=logger,
            policy=policy,
            runner=runner,
        )
    if t2_dicom_dir.exists():
        _process_dicom_directory(
            t2_dicom_dir,
            bids_anat_dir,
            subject_id,
            logger=logger,
            policy=policy,
            runner=runner,
        )

    if not bids_anat_dir.exists() or not any(bids_anat_dir.iterdir()):
        raise PreprocessError(f"No NIfTI files found in {bids_anat_dir}")
