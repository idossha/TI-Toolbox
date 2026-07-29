"""Preprocessing output preflight and rerun policy helpers."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from tit import constants as const
from tit.paths import get_path_manager

from .dicom2nifti import MODALITIES
from .qsi.utils import validate_bids_dwi
from .utils import _find_nifti

STEP_DICOM = "dicom"
STEP_CHARM = "charm"
STEP_RECON_ALL = "recon_all"
STEP_QSIPREP = "qsiprep"
STEP_QSIRECON = "qsirecon"
STEP_DTI = "dti"

STEP_LABELS = {
    STEP_DICOM: "DICOM conversion",
    STEP_CHARM: "SimNIBS charm",
    STEP_RECON_ALL: "FreeSurfer recon-all",
    STEP_QSIPREP: "QSIPrep",
    STEP_QSIRECON: "QSIRecon",
    STEP_DTI: "DTI tensor extraction",
}


@dataclass(frozen=True)
class PreprocessingOutput:
    """Existing output for one preprocessing step."""

    subject_id: str
    step: str
    label: str
    path: Path
    cleanup_paths: tuple[Path, ...] = ()

    @property
    def paths_to_remove(self) -> tuple[Path, ...]:
        return self.cleanup_paths or (self.path,)


@dataclass(frozen=True)
class PreprocessingInputProblem:
    """Missing or invalid input for one selected preprocessing step."""

    subject_id: str
    step: str
    label: str
    message: str
    path: Path


def _has_bids_t1(project_dir: str, subject_id: str) -> bool:
    pm = get_path_manager(project_dir)
    bids_anat_dir = Path(pm.bids_anat(subject_id))
    return _find_nifti(bids_anat_dir, f"sub-{subject_id}_T1w") is not None


def missing_inputs_for_step(
    project_dir: str, subject_id: str, step: str
) -> list[PreprocessingInputProblem]:
    """Return missing required inputs for one subject and preprocessing step."""
    pm = get_path_manager(project_dir)
    if step in (STEP_CHARM, STEP_RECON_ALL) and not _has_bids_t1(
        project_dir, subject_id
    ):
        return [
            PreprocessingInputProblem(
                subject_id=subject_id,
                step=step,
                label=STEP_LABELS[step],
                message=(
                    f"{STEP_LABELS[step]} requires a BIDS T1w image for "
                    f"sub-{subject_id}. Run DICOM conversion first or place "
                    f"sub-{subject_id}_T1w.nii[.gz] in the subject anat folder."
                ),
                path=Path(pm.bids_anat(subject_id)),
            )
        ]
    if step == STEP_QSIPREP:
        problems: list[PreprocessingInputProblem] = []
        # QSIPrep needs an anatomical reference (default --anat-modality T1w);
        # without one it fails deep in the workflow ("No T1w images found").
        if not _has_bids_t1(project_dir, subject_id):
            problems.append(
                PreprocessingInputProblem(
                    subject_id=subject_id,
                    step=step,
                    label=STEP_LABELS[step],
                    message=(
                        f"QSIPrep requires a BIDS T1w image for sub-{subject_id}. "
                        f"Run DICOM conversion first or place "
                        f"sub-{subject_id}_T1w.nii[.gz] in the subject anat folder."
                    ),
                    path=Path(pm.bids_anat(subject_id)),
                )
            )
        dwi_ok, dwi_error = validate_bids_dwi(
            project_dir, subject_id, logging.getLogger(__name__)
        )
        if not dwi_ok:
            problems.append(
                PreprocessingInputProblem(
                    subject_id=subject_id,
                    step=step,
                    label=STEP_LABELS[step],
                    message=(
                        f"QSIPrep requires BIDS DWI data for sub-{subject_id}: "
                        f"{dwi_error} Run DICOM conversion with DWI DICOMs or "
                        f"place sub-{subject_id}_dwi.nii[.gz] with .bval/.bvec "
                        "in the subject dwi folder."
                    ),
                    path=Path(pm.bids_dwi(subject_id)),
                )
            )
        return problems
    return []


def _dicom_conversion_will_run(
    project_dir: str,
    subject_id: str,
    *,
    convert_dicom: bool,
    skip_existing_outputs: bool,
) -> bool:
    if not convert_dicom:
        return False
    if not skip_existing_outputs:
        return True
    return not existing_outputs_for_step(project_dir, subject_id, STEP_DICOM)


def find_missing_preprocessing_inputs(
    project_dir: str,
    subject_ids: Iterable[str],
    *,
    steps: Sequence[str] | None = None,
    convert_dicom: bool = False,
    create_m2m: bool = False,
    run_recon: bool = False,
    run_qsiprep: bool = False,
    run_qsirecon: bool = False,
    extract_dti: bool = False,
    skip_existing_outputs: bool = False,
) -> list[PreprocessingInputProblem]:
    """Return missing inputs that can be detected before running subprocesses."""
    selected_steps = (
        list(steps)
        if steps is not None
        else selected_preprocessing_steps(
            convert_dicom=convert_dicom,
            create_m2m=create_m2m,
            run_recon=run_recon,
            run_qsiprep=run_qsiprep,
            run_qsirecon=run_qsirecon,
            extract_dti=extract_dti,
        )
    )

    problems: list[PreprocessingInputProblem] = []
    for subject_id in subject_ids:
        subject_steps = selected_steps
        if _dicom_conversion_will_run(
            project_dir,
            subject_id,
            convert_dicom=convert_dicom,
            skip_existing_outputs=skip_existing_outputs,
        ):
            # Conversion can produce the T1w and DWI inputs these steps need,
            # so don't flag them as missing yet.
            subject_steps = [
                step
                for step in selected_steps
                if step not in (STEP_CHARM, STEP_RECON_ALL, STEP_QSIPREP)
            ]
        for step in subject_steps:
            problems.extend(missing_inputs_for_step(project_dir, subject_id, step))
    return problems


def _existing_bids_sidecars(output_dir: Path, bids_name: str) -> tuple[Path, ...]:
    paths = (
        output_dir / f"{bids_name}.nii.gz",
        output_dir / f"{bids_name}.nii",
        output_dir / f"{bids_name}.json",
        output_dir / f"{bids_name}.bval",
        output_dir / f"{bids_name}.bvec",
    )
    return tuple(path for path in paths if path.exists())


def _dicom_outputs(project_dir: str, subject_id: str) -> list[PreprocessingOutput]:
    pm = get_path_manager(project_dir)
    outputs: list[PreprocessingOutput] = []
    for modality, datatype in MODALITIES:
        output_dir = Path(pm.bids_datatype(subject_id, datatype))
        bids_name = f"sub-{subject_id}_{modality}"
        cleanup_paths = _existing_bids_sidecars(output_dir, bids_name)
        if cleanup_paths:
            outputs.append(
                PreprocessingOutput(
                    subject_id=subject_id,
                    step=STEP_DICOM,
                    label=f"DICOM conversion ({modality})",
                    path=cleanup_paths[0],
                    cleanup_paths=cleanup_paths,
                )
            )
    return outputs


def _single_path_output(
    project_dir: str,
    subject_id: str,
    step: str,
    path: Path,
) -> list[PreprocessingOutput]:
    # An empty directory is not a real output (older releases pre-created
    # empty per-subject freesurfer dirs in existing projects).
    if not path.exists() or (path.is_dir() and not any(path.iterdir())):
        return []
    return [
        PreprocessingOutput(
            subject_id=subject_id,
            step=step,
            label=STEP_LABELS[step],
            path=path,
        )
    ]


def existing_outputs_for_step(
    project_dir: str, subject_id: str, step: str
) -> list[PreprocessingOutput]:
    """Return existing outputs for one subject and preprocessing step."""
    pm = get_path_manager(project_dir)
    if step == STEP_DICOM:
        return _dicom_outputs(project_dir, subject_id)
    if step == STEP_CHARM:
        return _single_path_output(
            project_dir, subject_id, step, Path(pm.m2m(subject_id))
        )
    if step == STEP_RECON_ALL:
        return _single_path_output(
            project_dir, subject_id, step, Path(pm.freesurfer_subject(subject_id))
        )
    if step == STEP_QSIPREP:
        return _single_path_output(
            project_dir, subject_id, step, Path(pm.qsiprep_subject(subject_id))
        )
    if step == STEP_QSIRECON:
        return _single_path_output(
            project_dir, subject_id, step, Path(pm.qsirecon_subject(subject_id))
        )
    if step == STEP_DTI:
        return _single_path_output(
            project_dir,
            subject_id,
            step,
            Path(pm.m2m(subject_id)) / const.FILE_DTI_TENSOR,
        )
    raise ValueError(f"Unknown preprocessing step: {step}")


def selected_preprocessing_steps(
    *,
    convert_dicom: bool = False,
    create_m2m: bool = False,
    run_recon: bool = False,
    run_qsiprep: bool = False,
    run_qsirecon: bool = False,
    extract_dti: bool = False,
) -> list[str]:
    """Return output-producing steps enabled by the current run options."""
    steps: list[str] = []
    if convert_dicom:
        steps.append(STEP_DICOM)
    if create_m2m:
        steps.append(STEP_CHARM)
    if run_recon:
        steps.append(STEP_RECON_ALL)
    if run_qsiprep:
        steps.append(STEP_QSIPREP)
    if run_qsirecon:
        steps.append(STEP_QSIRECON)
    if extract_dti:
        steps.append(STEP_DTI)
    return steps


def find_existing_preprocessing_outputs(
    project_dir: str,
    subject_ids: Iterable[str],
    *,
    steps: Sequence[str] | None = None,
    convert_dicom: bool = False,
    create_m2m: bool = False,
    run_recon: bool = False,
    run_qsiprep: bool = False,
    run_qsirecon: bool = False,
    extract_dti: bool = False,
) -> list[PreprocessingOutput]:
    """Return outputs that already exist for selected subjects and steps."""
    selected_steps = (
        list(steps)
        if steps is not None
        else selected_preprocessing_steps(
            convert_dicom=convert_dicom,
            create_m2m=create_m2m,
            run_recon=run_recon,
            run_qsiprep=run_qsiprep,
            run_qsirecon=run_qsirecon,
            extract_dti=extract_dti,
        )
    )
    outputs: list[PreprocessingOutput] = []
    for subject_id in subject_ids:
        for step in selected_steps:
            outputs.extend(existing_outputs_for_step(project_dir, subject_id, step))
    return outputs


def remove_preprocessing_output(output: PreprocessingOutput) -> None:
    """Remove an existing preprocessing output before an explicit rerun."""
    for path in output.paths_to_remove:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
