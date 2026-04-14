#!/usr/bin/env python
"""
DICOM-to-NIfTI conversion with BIDS-compliant naming.

Wraps ``dcm2niix`` to convert DICOM series into NIfTI files that follow
the BIDS naming convention (``sub-{id}_{modality}.nii.gz``).

Public API
----------
run_dicom_to_nifti
    Convert DICOM files for a subject to BIDS-compliant NIfTI.

See Also
--------
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
"""

import subprocess
from pathlib import Path

from tit.paths import get_path_manager
from .utils import CommandRunner, PreprocessError


def _convert_modality(
    dicom_dir: Path,
    output_dir: Path,
    subject_id: str,
    modality: str,
    logger,
    runner: CommandRunner | None,
) -> bool:
    """Convert DICOM files for a single modality to BIDS location."""
    if not list(dicom_dir.glob("*.dcm")):
        return False

    bids_name = f"sub-{subject_id}_{modality}"
    if (output_dir / f"{bids_name}.nii.gz").exists():
        raise PreprocessError(
            f"Output already exists for {bids_name}. "
            "Remove the files manually before rerunning."
        )

    logger.info(f"Converting {modality} DICOMs")
    cmd = [
        "dcm2niix",
        "-z",
        "y",
        "-b",
        "y",
        "-f",
        bids_name,
        "-o",
        str(output_dir),
        str(dicom_dir),
    ]

    if runner:
        exit_code = runner.run(cmd, logger=logger)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)
        exit_code = result.returncode

    if exit_code != 0:
        logger.warning(f"dcm2niix failed for {modality}")
        return False

    logger.info(f"Created {bids_name}.nii.gz")
    return True


def run_dicom_to_nifti(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: CommandRunner | None = None,
) -> None:
    """Convert DICOM files to BIDS-compliant NIfTI for a subject.

    Looks for ``T1w`` and ``T2w`` DICOM directories under
    ``sourcedata/sub-{subject_id}/`` and converts each found modality
    using ``dcm2niix``.

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
        If output NIfTI files already exist for a modality.

    See Also
    --------
    run_pipeline : Full preprocessing pipeline.
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_PRE_DICOM):
        pm = get_path_manager(project_dir)
        sourcedata_dir = Path(pm.sourcedata_subject(subject_id))
        bids_anat_dir = Path(pm.bids_anat(subject_id))
        bids_anat_dir.mkdir(parents=True, exist_ok=True)

        converted = False
        for modality in ("T1w", "T2w"):
            dicom_dir = sourcedata_dir / modality / "dicom"
            if _convert_modality(
                dicom_dir, bids_anat_dir, subject_id, modality, logger, runner
            ):
                converted = True

        if not converted:
            logger.warning("No DICOM files found or converted")
