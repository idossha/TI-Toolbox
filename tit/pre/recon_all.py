#!/usr/bin/env simnibs_python
"""
FreeSurfer recon-all wrapper.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from tit.core import get_path_manager
from .common import CommandRunner, PreprocessError, should_overwrite_path
from tit.core.overwrite import OverwritePolicy, get_overwrite_policy


def _find_anat_files(bids_anat_dir: Path) -> tuple[Optional[Path], Optional[Path]]:
    t1_candidates = sorted(
        list(bids_anat_dir.glob("*T1*.nii*")) + list(bids_anat_dir.glob("*t1*.nii*"))
    )
    t2_candidates = sorted(
        list(bids_anat_dir.glob("*T2*.nii*")) + list(bids_anat_dir.glob("*t2*.nii*"))
    )
    t1_file = t1_candidates[0] if t1_candidates else None
    t2_file = t2_candidates[0] if t2_candidates else None
    return t1_file, t2_file


def _validate_freesurfer_env(logger) -> None:
    fs_home = os.environ.get("FREESURFER_HOME")
    if not fs_home:
        logger.warning("FREESURFER_HOME is not set. FreeSurfer may not work properly.")
    elif not Path(fs_home).is_dir():
        raise PreprocessError(f"FREESURFER_HOME directory does not exist: {fs_home}")
    if not shutil.which("recon-all"):
        raise PreprocessError("recon-all (FreeSurfer) is not installed or not in PATH.")
    if not shutil.which("tcsh"):
        raise PreprocessError("tcsh is required by FreeSurfer but was not found.")


def run_recon_all(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    parallel: bool = False,
    overwrite: Optional[bool] = None,
    prompt_overwrite: Optional[bool] = None,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Run FreeSurfer recon-all for a subject.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the `sub-` prefix.
    logger : logging.Logger
        Logger used for progress and command output.
    parallel : bool, optional
        Use FreeSurfer OpenMP parallelization.
    overwrite : bool, optional
        Force overwrite of existing outputs.
    prompt_overwrite : bool, optional
        Allow interactive overwrite prompt.
    runner : CommandRunner, optional
        Subprocess runner used to stream output.
    """
    _validate_freesurfer_env(logger)

    pm = get_path_manager()
    pm.project_dir = project_dir
    bids_anat_dir = Path(pm.path("bids_anat", subject_id=subject_id))
    fs_subject_dir = Path(pm.path("freesurfer_subject", subject_id=subject_id))
    fs_subjects_root = fs_subject_dir.parent

    t1_file, t2_file = _find_anat_files(bids_anat_dir)
    if not t1_file:
        raise PreprocessError(f"No T1 file found in {bids_anat_dir}")

    policy = get_overwrite_policy(overwrite, prompt_overwrite)
    continue_existing = False
    if fs_subject_dir.exists():
        has_contents = any(fs_subject_dir.iterdir())
        if not has_contents:
            shutil.rmtree(fs_subject_dir, ignore_errors=True)
        else:
            if should_overwrite_path(
                fs_subject_dir, policy=policy, logger=logger, label="FreeSurfer"
            ):
                shutil.rmtree(fs_subject_dir, ignore_errors=True)
            else:
                continue_existing = True
                logger.info(
                    f"Existing FreeSurfer outputs detected for sub-{subject_id}; "
                    "continuing without -i inputs."
                )

    cmd = ["recon-all", "-subject", f"sub-{subject_id}"]
    if not continue_existing:
        cmd += ["-i", str(t1_file)]
        if t2_file:
            cmd += ["-T2", str(t2_file), "-T2pial"]
    cmd += ["-all", "-sd", str(fs_subjects_root)]

    if parallel:
        cmd.append("-parallel")

    logger.info(f"Running recon-all for subject {subject_id}")
    if runner:
        exit_code = runner.run(cmd, logger=logger)
    else:
        exit_code = subprocess.call(cmd)

    if exit_code != 0:
        raise PreprocessError(
            f"recon-all failed for subject {subject_id} (exit {exit_code})."
        )
