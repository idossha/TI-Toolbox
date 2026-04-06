#!/usr/bin/env simnibs_python
"""
SimNIBS CHARM head-mesh creation and subject atlas segmentation.

Wraps the SimNIBS ``charm`` command to generate m2m head-mesh directories
and the ``subject_atlas`` command to create cortical parcellation
``.annot`` files for a2009s, DK40, and HCP_MMP1 atlases.

Public API
----------
run_charm
    Run SimNIBS ``charm`` for a subject.
run_subject_atlas
    Create atlas ``.annot`` files from an existing m2m directory.

See Also
--------
tit.pre.recon_all : FreeSurfer ``recon-all`` cortical reconstruction.
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
"""

from pathlib import Path

import nibabel as nib

from tit.paths import get_path_manager
from .utils import CommandRunner, PreprocessError, _find_anat_files


def _get_form_flag(nifti_path: Path) -> str:
    """Return ``--forcesform`` or ``--forceqform`` based on NIfTI header."""
    header = nib.load(str(nifti_path)).header
    if header["sform_code"] > 0:
        return "--forcesform"
    if header["qform_code"] > 0:
        return "--forceqform"
    raise PreprocessError(
        f"Neither sform nor qform is set in {nifti_path}. Fix the NIfTI header."
    )


# All available atlases for subject_atlas command
ATLASES = ["a2009s", "DK40", "HCP_MMP1"]


def run_charm(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: CommandRunner | None = None,
) -> None:
    """Run SimNIBS ``charm`` to generate a head mesh for a subject.

    Creates an m2m directory at the standard BIDS derivatives location
    containing the volumetric head model required for TI simulations.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    logger : logging.Logger
        Logger used for progress and command output.
    runner : CommandRunner or None, optional
        Subprocess runner used to stream output.

    Raises
    ------
    PreprocessError
        If no T1 image is found, the m2m directory already exists, or
        ``charm`` exits with a non-zero code.

    See Also
    --------
    run_subject_atlas : Create atlas ``.annot`` files after CHARM.
    run_recon_all : FreeSurfer cortical reconstruction.
    """
    from tit.telemetry import track_event
    from tit import constants as _const

    track_event(_const.TELEMETRY_OP_PRE_CHARM, {"status": "start"})

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

    form_flag = _get_form_flag(t1_file)
    cmd = ["charm", form_flag, subject_id, str(t1_file)]
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
    runner: CommandRunner | None = None,
) -> None:
    """Run ``subject_atlas`` to create ``.annot`` files for a subject.

    Should be called after ``run_charm`` completes successfully.
    Generates all three atlases: a2009s, DK40, and HCP_MMP1.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    logger : logging.Logger
        Logger used for progress and command output.
    runner : CommandRunner or None, optional
        Subprocess runner used to stream output.

    Raises
    ------
    PreprocessError
        If the m2m directory does not exist or ``subject_atlas`` fails.

    See Also
    --------
    run_charm : Generate the m2m head mesh (prerequisite).
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
            "-a",
            atlas,
            "-o",
            str(output_dir),
            str(m2m_dir),
        ]

        logger.info(f"  Creating {atlas} atlas...")
        exit_code = runner.run(cmd, logger=logger)
        if exit_code != 0:
            raise PreprocessError(
                f"subject_atlas failed for atlas {atlas} (exit code {exit_code})"
            )

    logger.info(f"All atlases created successfully for subject {subject_id}")
