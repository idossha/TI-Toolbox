#!/usr/bin/env simnibs_python
"""
SimNIBS charm (m2m) creation + subject atlas segmentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tit.paths import get_path_manager
from .utils import CommandRunner, PreprocessError, _find_anat_files

# All available atlases for subject_atlas command
ATLASES = ["a2009s", "DK40", "HCP_MMP1"]


def run_charm(
    project_dir: str,
    subject_id: str,
    *,
    logger,
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
    runner : CommandRunner, optional
        Subprocess runner used to stream output.
    """
    pm = get_path_manager(project_dir)

    simnibs_subject_dir = Path(pm.sub(subject_id))
    simnibs_subject_dir.mkdir(parents=True, exist_ok=True)
    m2m_dir = Path(pm.m2m(subject_id))

    t1_file, t2_file = _find_anat_files(subject_id)
    if not t1_file:
        bids_anat_dir = Path(pm.bids_anat(subject_id))
        raise PreprocessError(f"No T1 image found in {bids_anat_dir}")

    if m2m_dir.exists():
        raise PreprocessError(
            f"m2m output already exists at {m2m_dir}. "
            "Remove the directory manually before rerunning."
        )

    cmd = ["charm", "--forcesform", subject_id, str(t1_file)]
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

    pm = get_path_manager(project_dir)
    m2m_dir = Path(pm.m2m(subject_id))

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

    logger.info(f"All atlases created successfully for subject {subject_id}")
