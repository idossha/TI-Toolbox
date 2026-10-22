"""Preprocessing output preflight and rerun policy helpers."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tit import constants as const
from tit.paths import get_path_manager

from .dicom2nifti import (
    MODALITIES,
    _iter_files,
    _modality_source_dir,
    bids_outputs,
    converted_nifti,
)
from .fastsurfer import SEG_FILENAME
from .qsi.qsirecon import existing_reconstructions
from .qsi.utils import (
    plan_distortion_correction,
    qsiprep_has_mni_transform,
    validate_bids_dwi,
    validate_qsiprep_output,
)
from .tissue_analyzer import DEFAULT_TISSUES
from .utils import _find_nifti

STEP_DICOM = "dicom"
STEP_CHARM = "charm"
STEP_FASTSURFER = "fastsurfer"
STEP_FREESURFER = "freesurfer"
STEP_FREESURFER_THALAMUS = "freesurfer_thalamus"
STEP_FREESURFER_HIPPO = "freesurfer_hippo_amygdala"
FREESURFER_SUBREGION_STEPS = {
    "thalamus": STEP_FREESURFER_THALAMUS,
    "hippo-amygdala": STEP_FREESURFER_HIPPO,
}
STEP_TISSUE = "tissue"
STEP_QSIPREP = "qsiprep"
STEP_QSIRECON = "qsirecon"
STEP_DTI = "dti"

STEP_LABELS = {
    STEP_DICOM: "DICOM conversion",
    STEP_CHARM: "SimNIBS charm",
    STEP_FASTSURFER: "FastSurfer segmentation",
    STEP_FREESURFER: "FreeSurfer recon-all",
    STEP_FREESURFER_THALAMUS: "FreeSurfer thalamic nuclei",
    STEP_FREESURFER_HIPPO: "FreeSurfer hippocampus/amygdala",
    STEP_TISSUE: "Tissue analysis",
    STEP_QSIPREP: "QSIPrep",
    STEP_QSIRECON: "QSIRecon",
    STEP_DTI: "DTI tensor extraction",
}


@dataclass(frozen=True)
class PreprocessingOutput:
    """Existing output for one preprocessing step.

    ``missing`` names the files the step's producer writes when it finishes and that
    are not there: a non-empty value means an earlier run was interrupted, so the
    output is incomplete -- "skip" must not keep it, only "replace" can clear it.
    """

    subject_id: str
    step: str
    label: str
    path: Path
    cleanup_paths: tuple[Path, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def paths_to_remove(self) -> tuple[Path, ...]:
        return self.cleanup_paths or (self.path,)

    @property
    def complete(self) -> bool:
        """``True`` when the producer's own success markers are all present."""
        return not self.missing


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
    project_dir: str,
    subject_id: str,
    step: str,
    *,
    qsirecon_atlases: Sequence[str] = (),
) -> list[PreprocessingInputProblem]:
    """Return missing required inputs for one subject and preprocessing step.

    Each check is the one the step's runner makes before it starts, read from disk as it
    is now. *qsirecon_atlases* are the QSIRecon atlases requested: they need the MNI
    transform in the QSIPrep output. :func:`find_missing_preprocessing_inputs` drops the
    problems a step selected earlier in the same run will fix.
    """
    pm = get_path_manager(project_dir)
    if step == STEP_TISSUE:
        labeling = Path(pm.tissue_labeling(subject_id))
        if labeling.is_file():
            return []
        return [
            PreprocessingInputProblem(
                subject_id=subject_id,
                step=step,
                label=STEP_LABELS[step],
                message=(
                    f"Tissue analysis reads the charm segmentation "
                    f"(segmentation/labeling.nii.gz), which sub-{subject_id} does not "
                    f"have. Run SimNIBS charm for sub-{subject_id} first."
                ),
                path=labeling,
            )
        ]
    if step == STEP_QSIRECON:
        qsiprep_dir = Path(pm.qsiprep_subject(subject_id))
        qsiprep_ok, qsiprep_error = validate_qsiprep_output(project_dir, subject_id)
        if not qsiprep_ok:
            message = (
                f"QSIRecon reconstructs QSIPrep output: {qsiprep_error}. "
                f"Run QSIPrep for sub-{subject_id} first."
            )
        elif qsirecon_atlases and not qsiprep_has_mni_transform(
            project_dir, subject_id
        ):
            message = (
                f"{_ATLASES_NEED_MNI}, which sub-{subject_id}'s QSIPrep run skipped. "
                "Re-run QSIPrep with MNI normalization enabled, or run QSIRecon "
                "without atlases."
            )
        else:
            return []
        return [
            PreprocessingInputProblem(
                subject_id, step, STEP_LABELS[step], message, qsiprep_dir
            )
        ]
    if step in (STEP_CHARM, STEP_FASTSURFER, STEP_FREESURFER) and not _has_bids_t1(
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
    if step in FREESURFER_SUBREGION_STEPS.values():
        from .freesurfer import validate_reconstruction
        from .utils import PreprocessError

        try:
            validate_reconstruction(subject_id)
        except PreprocessError as exc:
            return [
                PreprocessingInputProblem(
                    subject_id,
                    step,
                    STEP_LABELS[step],
                    str(exc),
                    Path(pm.freesurfer_subject(subject_id)),
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
        else:
            sdc = plan_distortion_correction(
                project_dir,
                subject_id,
                logger=logging.getLogger(__name__),
                repair=False,
            )
            if sdc.blocking_error:
                problems.append(
                    PreprocessingInputProblem(
                        subject_id=subject_id,
                        step=step,
                        label=STEP_LABELS[step],
                        message=f"sub-{subject_id}: {sdc.blocking_error}",
                        path=Path(pm.bids_datatype(subject_id, "fmap")),
                    )
                )
        return problems
    if step == STEP_DTI:
        problems = []
        qsiprep_ok, qsiprep_error = validate_qsiprep_output(project_dir, subject_id)
        if not qsiprep_ok:
            problems.append(
                PreprocessingInputProblem(
                    subject_id=subject_id,
                    step=step,
                    label=STEP_LABELS[step],
                    message=(
                        f"DTI extraction fits the tensor from QSIPrep output: "
                        f"{qsiprep_error}. Run QSIPrep for sub-{subject_id} first."
                    ),
                    path=Path(pm.qsiprep_subject(subject_id)),
                )
            )
        t1 = Path(pm.m2m(subject_id)) / const.FILE_T1
        if not t1.is_file():
            problems.append(
                PreprocessingInputProblem(
                    subject_id=subject_id,
                    step=step,
                    label=STEP_LABELS[step],
                    message=(
                        f"DTI extraction writes into the charm head model; run "
                        f"SimNIBS charm for sub-{subject_id} first."
                    ),
                    path=t1,
                )
            )
        return problems
    return []


_ATLASES_NEED_MNI = "QSIRecon atlases need QSIPrep's MNI normalization"


def _qsiprep_run_without_mni_transform(
    project_dir: str,
    subject_id: str,
    qsiprep_config: Mapping[str, Any],
    converted: set[str],
) -> list[PreprocessingInputProblem]:
    """The atlas conflict for a QSIPrep that runs before QSIRecon in the same run.

    That QSIPrep writes the MNI transform when ``mni_normalization`` is on or when it falls
    back to fieldmap-less SyN (:func:`tit.pre.qsi.qsiprep.run_qsiprep`). The fallback is
    decided by the subject's BIDS DWI and fieldmaps, so it is unknown while this run's DICOM
    conversion can still write them.
    """
    if qsiprep_config.get("mni_normalization") is True or converted & {"dwi", "fmap"}:
        return []
    sdc = plan_distortion_correction(
        project_dir, subject_id, logger=logging.getLogger(__name__), repair=False
    )
    if sdc.use_syn:
        return []
    pm = get_path_manager(project_dir)
    return [
        PreprocessingInputProblem(
            subject_id,
            STEP_QSIRECON,
            STEP_LABELS[STEP_QSIRECON],
            (
                f"{_ATLASES_NEED_MNI}, but this run's QSIPrep for sub-{subject_id} has "
                f"it off and corrects distortion by {sdc.describe()}, so it writes no "
                "MNI transform. Turn on MNI normalization in the QSIPrep settings, or "
                "run QSIRecon without atlases."
            ),
            Path(pm.qsiprep_subject(subject_id)),
        )
    ]


#: The source modalities whose conversion produces what each step's input check reads
#: (QSIPrep: a converted fieldmap can be the usable one its distortion check wants).
_CONVERTED_INPUTS = {
    STEP_CHARM: ("T1w",),
    STEP_FASTSURFER: ("T1w",),
    STEP_FREESURFER: ("T1w",),
    STEP_QSIPREP: ("T1w", "dwi", "fmap"),
}


def _modalities_dicom_conversion_will_produce(
    project_dir: str,
    subject_id: str,
    *,
    convert_dicom: bool,
    skip_existing_outputs: bool,
) -> set[str]:
    """The modalities this run's DICOM conversion can still write a NIfTI for.

    Without "skip", or before anything was converted, the conversion runs whole. Under
    "skip" it converts per modality, and only a modality whose source folder holds files
    and whose NIfTI is absent: the rule ``run_dicom_to_nifti`` applies. The empty
    ``dicom/`` folders the app scaffolds for every modality are not a source.
    """
    if not convert_dicom:
        return set()
    if not skip_existing_outputs or not _dicom_outputs(project_dir, subject_id):
        return {modality for modality, _datatype in MODALITIES}
    pm = get_path_manager(project_dir)
    sourcedata = Path(pm.sourcedata_subject(subject_id))
    return {
        modality
        for modality, datatype in MODALITIES
        if converted_nifti(
            Path(pm.bids_datatype(subject_id, datatype)), subject_id, modality
        )
        is None
        and any(_iter_files(_modality_source_dir(sourcedata, modality)))
    }


def find_missing_preprocessing_inputs(
    project_dir: str,
    subject_ids: Iterable[str],
    *,
    steps: Sequence[str] | None = None,
    convert_dicom: bool = False,
    create_m2m: bool = False,
    run_fastsurfer: bool = False,
    run_freesurfer: bool = False,
    freesurfer_recon_all: bool = True,
    freesurfer_subregions: Sequence[str] = (),
    run_tissue_analysis: bool = False,
    run_qsiprep: bool = False,
    run_qsirecon: bool = False,
    extract_dti: bool = False,
    skip_existing_outputs: bool = False,
    qsiprep_config: Mapping[str, Any] | None = None,
    qsi_recon_config: Mapping[str, Any] | None = None,
) -> list[PreprocessingInputProblem]:
    """Return missing inputs that can be detected before running subprocesses.

    *qsiprep_config* and *qsi_recon_config* are the run's settings dicts (only
    ``mni_normalization`` and ``atlases`` are read): QSIRecon atlases need QSIPrep's MNI
    transform. Under *skip_existing_outputs*, tissue analysis and QSIRecon are not
    checked where their output already exists, since the runner skips them there.
    """
    subject_ids = list(subject_ids)
    qsiprep_config = qsiprep_config if isinstance(qsiprep_config, Mapping) else {}
    atlases = (
        qsi_recon_config.get("atlases")
        if isinstance(qsi_recon_config, Mapping)
        else None
    )
    atlases = list(atlases) if isinstance(atlases, (list, tuple)) else []
    selected_steps = (
        list(steps)
        if steps is not None
        else selected_preprocessing_steps(
            convert_dicom=convert_dicom,
            create_m2m=create_m2m,
            run_fastsurfer=run_fastsurfer,
            run_freesurfer=run_freesurfer,
            freesurfer_recon_all=freesurfer_recon_all,
            freesurfer_subregions=freesurfer_subregions,
            run_tissue_analysis=run_tissue_analysis,
            run_qsiprep=run_qsiprep,
            run_qsirecon=run_qsirecon,
            extract_dti=extract_dti,
        )
    )

    problems: list[PreprocessingInputProblem] = []
    for subject_id in subject_ids:
        produced = _modalities_dicom_conversion_will_produce(
            project_dir,
            subject_id,
            convert_dicom=convert_dicom,
            skip_existing_outputs=skip_existing_outputs,
        )
        converted = set(produced)

        def runs(step: str, subject_id: str = subject_id) -> bool:
            """Selected, and not skipped because its output already exists."""
            return step in selected_steps and not (
                skip_existing_outputs
                and existing_outputs_for_step(project_dir, subject_id, step)
            )

        # Conversion in this run can still produce these steps' T1w/DWI inputs,
        # so don't flag them as missing yet.
        subject_steps = [
            step
            for step in selected_steps
            if not produced.intersection(_CONVERTED_INPUTS.get(step, ()))
        ]
        if STEP_FREESURFER in selected_steps and (
            not skip_existing_outputs
            or not existing_outputs_for_step(project_dir, subject_id, STEP_FREESURFER)
        ):
            # This job's recon-all supplies the subregion prerequisites.
            subject_steps = [
                s for s in subject_steps if s not in FREESURFER_SUBREGION_STEPS.values()
            ]
        if skip_existing_outputs and existing_outputs_for_step(
            project_dir, subject_id, STEP_FREESURFER
        ):
            subject_steps = [s for s in subject_steps if s != STEP_FREESURFER]
        subject_steps = [
            s for s in subject_steps if s not in (STEP_TISSUE, STEP_QSIRECON) or runs(s)
        ]
        for step in subject_steps:
            found = missing_inputs_for_step(
                project_dir, subject_id, step, qsirecon_atlases=atlases
            )
            if step == STEP_TISSUE and runs(STEP_CHARM):
                found = []  # this run's charm writes the segmentation first
            if step == STEP_QSIRECON and runs(STEP_QSIPREP):
                # This run's QSIPrep writes the output; its settings decide the transform.
                found = (
                    _qsiprep_run_without_mni_transform(
                        project_dir, subject_id, qsiprep_config, converted
                    )
                    if atlases
                    else []
                )
            if step == STEP_DTI:
                # Stages selected in the same run produce these inputs first.
                produced = [
                    (
                        Path(get_path_manager(project_dir).qsiprep_subject(subject_id))
                        if STEP_QSIPREP in selected_steps
                        else None
                    ),
                    (
                        Path(get_path_manager(project_dir).m2m(subject_id))
                        / const.FILE_T1
                        if STEP_CHARM in selected_steps
                        else None
                    ),
                ]
                found = [p for p in found if p.path not in produced]
            problems.extend(found)
    problems.extend(missing_freesurfer_license(selected_steps, subject_ids))
    return problems


#: The stages that run FreeSurfer binaries and therefore need the user's own
#: FreeSurfer license. FastSurfer ``--seg_only`` (STEP_FASTSURFER), charm,
#: DICOM conversion and DTI extraction need none.
LICENSED_STEPS = (STEP_FREESURFER, STEP_FREESURFER_THALAMUS, STEP_FREESURFER_HIPPO)


def missing_freesurfer_license(
    selected_steps: Sequence[str], subject_ids: Sequence[str] = ()
) -> list[PreprocessingInputProblem]:
    """One problem naming exactly which selected stages need a license, or none.

    Only :data:`LICENSED_STEPS` are checked, so a FastSurfer segmentation-only
    run is never held up by a missing license.
    """
    licensed = [step for step in selected_steps if step in LICENSED_STEPS]
    if not licensed:
        return []
    from tit.surfer_settings import (
        BUNDLED_FS_LICENSE_PATH,
        freesurfer_license_status,
    )

    if freesurfer_license_status()["configured"]:
        return []
    names = ", ".join(STEP_LABELS[step] for step in licensed)
    return [
        PreprocessingInputProblem(
            next(iter(subject_ids), ""),
            licensed[0],
            "FreeSurfer license",
            (
                f"{names} cannot find the FreeSurfer license supplied by TI-Toolbox. "
                "Repair or update the TI-Toolbox installation; no personal license is required."
            ),
            BUNDLED_FS_LICENSE_PATH,
        )
    ]


def _dicom_outputs(project_dir: str, subject_id: str) -> list[PreprocessingOutput]:
    pm = get_path_manager(project_dir)
    outputs: list[PreprocessingOutput] = []
    for modality, datatype in MODALITIES:
        output_dir = Path(pm.bids_datatype(subject_id, datatype))
        cleanup_paths = tuple(bids_outputs(output_dir, subject_id, modality))
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
    markers: Sequence[Path] = (),
) -> list[PreprocessingOutput]:
    # An empty directory is not a real output (older releases pre-created
    # empty per-subject derivative dirs in existing projects).
    if not path.exists() or (path.is_dir() and not any(path.iterdir())):
        return []
    missing = tuple(
        str(marker.relative_to(path)) for marker in markers if not marker.is_file()
    )
    return [
        PreprocessingOutput(
            subject_id=subject_id,
            step=step,
            label=STEP_LABELS[step],
            path=path,
            missing=missing,
        )
    ]


def _qsirecon_outputs(project_dir: str, subject_id: str) -> list[PreprocessingOutput]:
    """The reconstructions ``run_qsirecon`` refuses to overwrite, with what goes with them.

    QSIRecon 26 writes each reconstruction to
    ``derivatives/qsirecon/derivatives/qsirecon-<suffix>/sub-<id>/`` beside a
    ``sub-<id>.html`` report, and the run's logs to ``derivatives/qsirecon/sub-<id>/``.
    Only the reconstructions block a rerun (the runner's guard); the report and the
    logs describe them, so a replace removes them too.
    """
    reconstructions = existing_reconstructions(project_dir, subject_id)
    if not reconstructions:
        return []
    reports = [path.with_name(f"{path.name}.html") for path in reconstructions]
    logs = Path(get_path_manager(project_dir).qsirecon_subject(subject_id))
    extras = tuple(path for path in (*reports, logs) if path.exists())
    return [
        PreprocessingOutput(
            subject_id,
            STEP_QSIRECON,
            STEP_LABELS[STEP_QSIRECON],
            reconstructions[0],
            (*reconstructions, *extras),
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
        # charm's last science step writes the mesh; the segmentation comes before it.
        m2m = Path(pm.m2m(subject_id))
        return _single_path_output(
            project_dir,
            subject_id,
            step,
            m2m,
            (m2m / f"{subject_id}.msh", m2m / "final_tissues.nii.gz"),
        )
    if step == STEP_FASTSURFER:
        # The file run_fastsurfer checks for success (and returns early on).
        return _single_path_output(
            project_dir,
            subject_id,
            step,
            Path(pm.fastsurfer_subject(subject_id)),
            (Path(pm.fastsurfer_mri(subject_id)) / SEG_FILENAME,),
        )
    if step == STEP_FREESURFER:
        return _single_path_output(
            project_dir, subject_id, step, Path(pm.freesurfer_subject(subject_id))
        )
    if step in FREESURFER_SUBREGION_STEPS.values():
        subject = Path(pm.freesurfer_subject(subject_id))
        # FreeSurfer 7.4.1 segment_subregions, default suffix: exact output names
        # preserve legacy runs and every recon-all input during subset reruns.
        names = (
            [
                "ThalamicNuclei.mgz",
                "ThalamicNuclei.FSvoxelSpace.mgz",
                "ThalamicNuclei.volumes.txt",
            ]
            if step == STEP_FREESURFER_THALAMUS
            else [
                f"{hemi}.hippoAmygLabels{suffix}.mgz"
                for hemi in ("lh", "rh")
                for suffix in (
                    "",
                    ".FSvoxelSpace",
                    ".HBT",
                    ".HBT.FSvoxelSpace",
                    ".FS60",
                    ".FS60.FSvoxelSpace",
                    ".CA",
                    ".CA.FSvoxelSpace",
                )
            ]
            + [
                f"{hemi}.{stem}.txt"
                for hemi in ("lh", "rh")
                for stem in ("hippoSfVolumes", "amygNucVolumes")
            ]
        )
        paths = tuple(
            subject / "mri" / name
            for name in names
            if (subject / "mri" / name).is_file()
        )
        return (
            [PreprocessingOutput(subject_id, step, STEP_LABELS[step], paths[0], paths)]
            if paths
            else []
        )
    if step == STEP_TISSUE:
        # One report per tissue, written by TissueAnalyzer once its analysis is done.
        root = Path(pm.tissue_analysis_output(subject_id))
        return _single_path_output(
            project_dir,
            subject_id,
            step,
            root,
            tuple(
                root / f"{tissue}_analysis" / f"{tissue}_analysis.txt"
                for tissue in DEFAULT_TISSUES
            ),
        )
    if step == STEP_QSIPREP:
        outputs = _single_path_output(
            project_dir, subject_id, step, Path(pm.qsiprep_subject(subject_id))
        )
        # The check QSIRecon and DTI extraction apply to this output.
        valid, _error = validate_qsiprep_output(project_dir, subject_id)
        if outputs and not valid:
            return [replace(outputs[0], missing=("dwi/*_dwi.nii[.gz]",))]
        return outputs
    if step == STEP_QSIRECON:
        return _qsirecon_outputs(project_dir, subject_id)
    if step == STEP_DTI:
        m2m = Path(pm.m2m(subject_id))
        tensor = m2m / const.FILE_DTI_TENSOR
        if not tensor.exists():
            return []
        # The QC JSON and the ACPC intermediate older releases wrote go with it.
        extras = tuple(
            p
            for p in (m2m / const.FILE_DTI_QC, m2m / "DTI_ACPC_tensor.nii.gz")
            if p.exists()
        )
        return [
            PreprocessingOutput(
                subject_id,
                step,
                STEP_LABELS[step],
                tensor,
                (tensor, *extras),
                # extract_dti_tensor copies the finished tensor into place: an empty
                # file is a copy that was cut off. (A truncated non-empty one is not
                # detected here.)
                missing=() if tensor.stat().st_size else ("tensor data",),
            )
        ]
    raise ValueError(f"Unknown preprocessing step: {step}")


def step_output_complete(project_dir: str, subject_id: str, step: str) -> bool:
    """Return ``True`` when *step* has an output for *subject_id* and it is finished.

    A folder an interrupted run left behind is an existing output (replace can clear
    it) but not a complete one: FastSurfer without its segmentation, charm without its
    mesh and final segmentation, QSIPrep without a preprocessed DWI, tissue analysis
    without every tissue's report, a zero-byte DTI tensor. Callers that show whether a
    stage is done use this, not the folder's existence. FreeSurfer recon-all and QSIRecon
    have no completion marker, so any non-empty output of theirs counts as complete.
    """
    outputs = existing_outputs_for_step(project_dir, subject_id, step)
    return bool(outputs) and all(output.complete for output in outputs)


def selected_preprocessing_steps(
    *,
    convert_dicom: bool = False,
    create_m2m: bool = False,
    run_fastsurfer: bool = False,
    run_freesurfer: bool = False,
    freesurfer_recon_all: bool = True,
    freesurfer_subregions: Sequence[str] = (),
    run_tissue_analysis: bool = False,
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
    if run_fastsurfer:
        steps.append(STEP_FASTSURFER)
    if run_freesurfer:
        if freesurfer_recon_all:
            steps.append(STEP_FREESURFER)
        steps.extend(
            FREESURFER_SUBREGION_STEPS[item]
            for item in dict.fromkeys(freesurfer_subregions)
        )
    if run_tissue_analysis:
        steps.append(STEP_TISSUE)
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
    run_fastsurfer: bool = False,
    run_freesurfer: bool = False,
    freesurfer_recon_all: bool = True,
    freesurfer_subregions: Sequence[str] = (),
    run_tissue_analysis: bool = False,
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
            run_fastsurfer=run_fastsurfer,
            run_freesurfer=run_freesurfer,
            freesurfer_recon_all=freesurfer_recon_all,
            freesurfer_subregions=freesurfer_subregions,
            run_tissue_analysis=run_tissue_analysis,
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
