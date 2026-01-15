#!/usr/bin/env simnibs_python
"""
DWI/DTI preprocessing wrappers (QSIPrep/QSIRECON).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from tit.core import constants as const
from tit.core import get_path_manager
from .common import CommandRunner, PreprocessError, should_overwrite_path
from tit.core.overwrite import get_overwrite_policy


def _strip_nii_suffix(path: Path) -> str:
    if path.name.endswith(".nii.gz"):
        return path.name[:-7]
    return path.stem


def _validate_bids_dwi_layout(bids_dwi_dir: Path, subject_id: str) -> None:
    expected_prefix = f"{const.PREFIX_SUBJECT}{subject_id}_"
    invalid_files = [
        path.name
        for path in bids_dwi_dir.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and not path.name.startswith(expected_prefix)
    ]
    if invalid_files:
        preview = ", ".join(sorted(invalid_files)[:5])
        raise PreprocessError(
            "Non-BIDS filenames found in DWI directory. "
            f"Expected files to start with '{expected_prefix}'. "
            f"Examples: {preview}. "
            "Move non-BIDS files to /sourcedata or rename to BIDS."
        )

    has_session_label = any(
        "_ses-" in path.name
        for path in bids_dwi_dir.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
    if has_session_label and not bids_dwi_dir.parent.name.startswith("ses-"):
        raise PreprocessError(
            "Session labels were found in DWI filenames but the data are not "
            "inside a ses-* folder. Move files to "
            f"sub-{subject_id}/ses-<label>/dwi or remove the ses- label from filenames."
        )


def _find_dwi_series(bids_dwi_dir: Path, subject_id: str) -> tuple[Path, Path, Path]:
    if not bids_dwi_dir.exists():
        raise PreprocessError(f"DWI directory not found: {bids_dwi_dir}")

    _validate_bids_dwi_layout(bids_dwi_dir, subject_id)

    nifti_candidates = sorted(bids_dwi_dir.glob("*_dwi.nii*"))
    if not nifti_candidates:
        nifti_candidates = sorted(bids_dwi_dir.glob("*.nii*"))

    for nifti_path in nifti_candidates:
        base = _strip_nii_suffix(nifti_path)
        bval_path = bids_dwi_dir / f"{base}.bval"
        bvec_path = bids_dwi_dir / f"{base}.bvec"
        if bval_path.exists() and bvec_path.exists():
            return nifti_path, bval_path, bvec_path

    raise PreprocessError(
        f"No DWI series with .bval/.bvec found in {bids_dwi_dir}"
    )


def _validate_qsiprep(logger) -> None:
    if not shutil.which("qsiprep"):
        raise PreprocessError(
            "qsiprep is not available in PATH. "
            "Enable the QSIPrep container in loader.sh."
        )
    if not shutil.which("qsirecon"):
        logger.warning("qsirecon is not available in PATH.")


def run_qsiprep(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    overwrite: Optional[bool] = None,
    prompt_overwrite: Optional[bool] = None,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Run QSIPrep for a subject."""
    _validate_qsiprep(logger)

    pm = get_path_manager()
    pm.project_dir = project_dir
    bids_dwi_dir = Path(pm.path("bids_dwi", subject_id=subject_id))
    _find_dwi_series(bids_dwi_dir, subject_id)

    qsiprep_root = Path(pm.path("qsiprep"))
    qsiprep_root.mkdir(parents=True, exist_ok=True)
    qsiprep_subject = qsiprep_root / f"{const.PREFIX_SUBJECT}{subject_id}"

    policy = get_overwrite_policy(overwrite, prompt_overwrite)
    if qsiprep_subject.exists() and any(qsiprep_subject.iterdir()):
        if should_overwrite_path(qsiprep_subject, policy=policy, logger=logger, label="QSIPrep"):
            shutil.rmtree(qsiprep_subject, ignore_errors=True)
        else:
            logger.warning(f"Skipping QSIPrep for sub-{subject_id} (outputs exist).")
            return

    cmd = [
        "qsiprep",
        "/data",
        "/out/derivatives/qsiprep",
        "participant",
        "--participant-label",
        subject_id,
        "--fs-license-file",
        "/opt/freesurfer/license.txt",
        "--output-resolution",
        "2.0",
    ]

    logger.info(f"Running QSIPrep for subject {subject_id}")
    if runner is None:
        runner = CommandRunner()
    exit_code = runner.run(cmd, logger=logger)

    if exit_code != 0:
        raise PreprocessError(f"qsiprep failed for subject {subject_id} (exit {exit_code}).")


def run_qsirecon(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    overwrite: Optional[bool] = None,
    prompt_overwrite: Optional[bool] = None,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Run QSIRECON for a subject."""
    _validate_qsiprep(logger)

    pm = get_path_manager()
    pm.project_dir = project_dir
    qsiprep_root = Path(pm.path("qsiprep"))
    qsiprep_subject = qsiprep_root / f"{const.PREFIX_SUBJECT}{subject_id}"
    if not qsiprep_subject.exists():
        raise PreprocessError(
            f"QSIPrep outputs not found for sub-{subject_id} in {qsiprep_root}"
        )

    qsirecon_root = Path(pm.path("qsirecon"))
    qsirecon_root.mkdir(parents=True, exist_ok=True)
    qsirecon_subject = qsirecon_root / f"{const.PREFIX_SUBJECT}{subject_id}"

    policy = get_overwrite_policy(overwrite, prompt_overwrite)
    if qsirecon_subject.exists() and any(qsirecon_subject.iterdir()):
        if should_overwrite_path(qsirecon_subject, policy=policy, logger=logger, label="QSIRECON"):
            shutil.rmtree(qsirecon_subject, ignore_errors=True)
        else:
            logger.warning(f"Skipping QSIRECON for sub-{subject_id} (outputs exist).")
            return

    cmd = [
        "qsirecon",
        "/out/derivatives/qsiprep",
        "/out/derivatives/qsirecon",
        "participant",
        "--participant-label",
        subject_id,
        "--input-type",
        "qsiprep",
    ]

    logger.info(f"Running QSIRECON for subject {subject_id}")
    if runner is None:
        runner = CommandRunner()
    exit_code = runner.run(cmd, logger=logger)

    if exit_code != 0:
        raise PreprocessError(f"qsirecon failed for subject {subject_id} (exit {exit_code}).")
