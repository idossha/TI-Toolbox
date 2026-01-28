#!/usr/bin/env simnibs_python
"""
SimNIBS charm (m2m) creation + subject atlas segmentation.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from tit.core import get_path_manager
from .common import CommandRunner, PreprocessError
from tit.core.overwrite import get_overwrite_policy

# All available atlases for subject_atlas command
ATLASES = ["a2009s", "DK40", "HCP_MMP1"]


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


def run_charm(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    overwrite: Optional[bool] = None,
    prompt_overwrite: Optional[bool] = None,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Run SimNIBS charm for a subject.

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
    if not shutil.which("charm"):
        raise PreprocessError("charm (SimNIBS) is not installed.")

    pm = get_path_manager()
    pm.project_dir = project_dir
    bids_anat_dir = Path(pm.path("bids_anat", subject_id=subject_id))
    simnibs_subject_dir = Path(pm.path("simnibs_subject", subject_id=subject_id))
    simnibs_subject_dir.mkdir(parents=True, exist_ok=True)
    m2m_dir = Path(pm.path("m2m", subject_id=subject_id))

    t1_file, t2_file = _find_anat_files(bids_anat_dir)
    if not t1_file:
        raise PreprocessError(f"No T1 image found in {bids_anat_dir}")

    policy = get_overwrite_policy(overwrite, prompt_overwrite)
    forcerun = False
    existing_m2m = None
    if m2m_dir.exists():
        existing_m2m = m2m_dir
    if existing_m2m is not None:
        if policy.overwrite:
            forcerun = True
            logger.warning(f"m2m output exists at {existing_m2m}; using --forcerun.")
        elif policy.prompt and os.isatty(0):
            ans = (
                input(
                    f"m2m output already exists for sub-{subject_id}. Re-run and overwrite? [y/N]: "
                )
                .strip()
                .lower()
            )
            if ans in {"y", "yes"}:
                forcerun = True
                logger.warning(
                    f"User confirmed overwrite for sub-{subject_id}; using --forcerun."
                )
            else:
                logger.warning(f"Skipping charm for sub-{subject_id} (outputs exist).")
                return
        else:
            logger.warning(f"Skipping charm for sub-{subject_id} (outputs exist).")
            return

    cmd = ["charm"]
    if forcerun:
        cmd.append("--forcerun")
    cmd += ["--forcesform", subject_id, str(t1_file)]
    if t2_file:
        cmd.append(str(t2_file))

    logger.info(f"Running SimNIBS charm for subject {subject_id}")
    if runner is None:
        runner = CommandRunner()
    exit_code = runner.run(cmd, logger=logger, cwd=str(simnibs_subject_dir))

    if exit_code != 0:
        raise PreprocessError(
            f"charm failed for subject {subject_id} (exit {exit_code})."
        )


def run_subject_atlas(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: Optional[CommandRunner] = None,
) -> None:
    """Run subject_atlas to create .annot files for a subject.

    This should be called after charm completes successfully.
    Generates all three atlases: a2009s, DK40, and HCP_MMP1.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the `sub-` prefix.
    logger : logging.Logger
        Logger used for progress and command output.
    runner : CommandRunner, optional
        Subprocess runner used to stream output.
    """
    if not shutil.which("subject_atlas"):
        raise PreprocessError("subject_atlas (SimNIBS) is not installed.")

    pm = get_path_manager()
    pm.project_dir = project_dir
    m2m_dir = Path(pm.path("m2m", subject_id=subject_id))

    if not m2m_dir.exists():
        raise PreprocessError(f"m2m folder not found at {m2m_dir}. Run charm first.")

    # Output directory for atlas segmentation
    output_dir = m2m_dir / "segmentation"
    output_dir.mkdir(parents=True, exist_ok=True)

    if runner is None:
        runner = CommandRunner()

    logger.info(
        f"Running subject_atlas for subject {subject_id} with atlases: {', '.join(ATLASES)}"
    )

    for atlas in ATLASES:
        cmd = [
            "subject_atlas",
            "-m",
            str(m2m_dir),
            "-a",
            atlas,
            "-o",
            str(output_dir),
        ]

        logger.info(f"  Creating {atlas} atlas...")
        exit_code = runner.run(cmd, logger=logger)

        if exit_code != 0:
            raise PreprocessError(
                f"subject_atlas failed for subject {subject_id} with atlas {atlas} (exit {exit_code})."
            )

    logger.info(f"All atlases created successfully for subject {subject_id}")
