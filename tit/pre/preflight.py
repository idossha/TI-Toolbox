"""Preprocessing output preflight and rerun policy helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from tit import constants as const
from tit.paths import get_path_manager

STEP_DICOM = "dicom"
STEP_CHARM = "charm"
STEP_RECON_ALL = "recon_all"
STEP_QSIPREP = "qsiprep"
STEP_QSIRECON = "qsirecon"
STEP_DTI = "dti"
STEP_THALAMUS_ROIS = "thalamus_rois"

STEP_LABELS = {
    STEP_DICOM: "DICOM conversion",
    STEP_CHARM: "SimNIBS charm",
    STEP_RECON_ALL: "FreeSurfer recon-all",
    STEP_QSIPREP: "QSIPrep",
    STEP_QSIRECON: "QSIRecon",
    STEP_DTI: "DTI tensor extraction",
    STEP_THALAMUS_ROIS: "Functional thalamus ROIs",
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
    output_dir = Path(pm.bids_anat(subject_id))
    outputs: list[PreprocessingOutput] = []
    for modality in ("T1w", "T2w"):
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
    if not path.exists():
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
        return _single_path_output(project_dir, subject_id, step, Path(pm.m2m(subject_id)))
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
    if step == STEP_THALAMUS_ROIS:
        return _single_path_output(
            project_dir,
            subject_id,
            step,
            Path(pm.rois(subject_id)) / "thalamus_functional",
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
    run_thalamus_rois: bool = False,
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
    if run_thalamus_rois:
        steps.append(STEP_THALAMUS_ROIS)
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
    run_thalamus_rois: bool = False,
) -> list[PreprocessingOutput]:
    """Return outputs that already exist for selected subjects and steps."""
    selected_steps = list(steps) if steps is not None else selected_preprocessing_steps(
        convert_dicom=convert_dicom,
        create_m2m=create_m2m,
        run_recon=run_recon,
        run_qsiprep=run_qsiprep,
        run_qsirecon=run_qsirecon,
        extract_dti=extract_dti,
        run_thalamus_rois=run_thalamus_rois,
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
