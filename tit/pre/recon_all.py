#!/usr/bin/env simnibs_python
"""
FreeSurfer ``recon-all`` wrapper for cortical surface reconstruction.

This module provides a wrapper around FreeSurfer's ``recon-all`` command
for automated cortical reconstruction and segmentation, as well as
standalone subcortical segmentation (thalamic nuclei and hippocampal
subfields).

Public API
----------
run_recon_all
    Run FreeSurfer ``recon-all`` for a subject.
run_subcortical_segmentations
    Run thalamic-nuclei and hippocampal-subfield segmentations standalone.

See Also
--------
tit.pre.charm : SimNIBS CHARM head-mesh generation.
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
"""

import os
import shutil
import subprocess
from pathlib import Path

from tit.paths import get_path_manager
from .utils import CommandRunner, PreprocessError, _find_anat_files


def _run_subcortical_segmentations(
    subject_id: str,
    fs_subjects_root: Path,
    *,
    logger,
    runner: CommandRunner | None = None,
) -> None:
    """Run thalamic-nuclei and hippocampal-subfield segmentations (internal)."""
    fs_subject = f"sub-{subject_id}"
    env = {**os.environ, "SUBJECTS_DIR": str(fs_subjects_root)}

    segmentations = [
        ("segmentThalamicNuclei.sh", "thalamic nuclei"),
        ("segmentHA_T1.sh", "hippocampal subfields"),
    ]

    for script, label in segmentations:

        cmd = [script, fs_subject]
        logger.info(f"Segmenting {label} for {fs_subject}")
        if runner:
            exit_code = runner.run(cmd, logger=logger, env=env)
        else:
            exit_code = subprocess.call(cmd, env=env)

        if exit_code != 0:
            logger.warning(
                f"{script} exited with code {exit_code}; "
                f"{label} segmentation may be incomplete."
            )


def run_subcortical_segmentations(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: CommandRunner | None = None,
) -> None:
    """Run thalamic-nuclei and hippocampal-subfield segmentations standalone.

    Resolves the FreeSurfer subjects directory from the project layout and
    delegates to the internal segmentation runner.  Intended for cases where
    ``recon-all`` has already completed and only the subcortical step needs
    to be (re-)run.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    logger : logging.Logger
        Logger for progress output.
    runner : CommandRunner or None, optional
        Subprocess runner for streaming output.

    See Also
    --------
    run_recon_all : Full FreeSurfer ``recon-all`` (includes subcortical).
    run_pipeline : Full preprocessing pipeline.
    """
    pm = get_path_manager(project_dir)
    fs_subject_dir = Path(pm.freesurfer_subject(subject_id))
    fs_subjects_root = fs_subject_dir.parent
    _run_subcortical_segmentations(
        subject_id, fs_subjects_root, logger=logger, runner=runner
    )


def run_recon_all(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    parallel: bool = False,
    runner: CommandRunner | None = None,
) -> None:
    """Run FreeSurfer ``recon-all`` for a subject.

    Runs the full ``recon-all -all`` pipeline and, upon success,
    automatically runs thalamic-nuclei and hippocampal-subfield
    segmentations.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    logger : logging.Logger
        Logger used for progress and command output.
    parallel : bool, optional
        Use FreeSurfer OpenMP parallelization.
    runner : CommandRunner or None, optional
        Subprocess runner used to stream output.

    Raises
    ------
    PreprocessError
        If no T1 file is found, the output directory already exists, or
        ``recon-all`` exits with a non-zero code.

    See Also
    --------
    run_subcortical_segmentations : Standalone subcortical segmentation.
    run_charm : SimNIBS CHARM head-mesh generation.
    """

    from tit.telemetry import track_event
    from tit import constants as _const

    track_event(_const.TELEMETRY_OP_PRE_RECON_ALL, {"status": "start"})

    pm = get_path_manager(project_dir)

    fs_subject_dir = Path(pm.freesurfer_subject(subject_id))
    fs_subjects_root = fs_subject_dir.parent

    t1_file, t2_file = _find_anat_files(subject_id)
    if not t1_file:
        bids_anat_dir = Path(pm.bids_anat(subject_id))
        raise PreprocessError(f"No T1 file found in {bids_anat_dir}")

    if fs_subject_dir.exists():
        if any(fs_subject_dir.iterdir()):
            raise PreprocessError(
                f"FreeSurfer output already exists at {fs_subject_dir}. "
                "Remove the directory manually before rerunning."
            )
        else:
            shutil.rmtree(fs_subject_dir, ignore_errors=True)

    cmd = ["recon-all", "-subject", f"sub-{subject_id}", "-i", str(t1_file)]
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

    _run_subcortical_segmentations(
        subject_id, fs_subjects_root, logger=logger, runner=runner
    )
