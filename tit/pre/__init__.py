"""
Preprocessing APIs for TI-Toolbox.

This package provides standalone, reusable functions for every stage of the
TI-Toolbox preprocessing pipeline: DICOM conversion, SimNIBS head-mesh
generation (CHARM), FastSurfer deep segmentation, tissue analysis, and
diffusion-weighted imaging (DWI) preprocessing via QSIPrep/QSIRecon.

Structural work runs in the TI-Toolbox image itself (SimNIBS + FastSurfer);
only the DWI stages spawn sibling containers (QSIPrep/QSIRecon). The
functions here orchestrate those and manage BIDS-compliant file layouts.

Public API
----------
run_pipeline
    Full preprocessing pipeline orchestrator (sequential or parallel).
run_dicom_to_nifti
    Convert DICOM series to BIDS-compliant NIfTI files.
run_fastsurfer
    Run FastSurfer ``--seg_only`` deep segmentation.
fastsurfer_available
    Probe for a runnable FastSurfer install.
run_charm
    Generate a SimNIBS head mesh via the ``charm`` command.
run_tissue_analysis
    Compute tissue volumes and thickness from segmented NIfTI data.
run_qsiprep
    Preprocess DWI data using QSIPrep (Docker-out-of-Docker).
run_qsirecon
    Reconstruct DWI data using QSIRecon (Docker-out-of-Docker).
extract_dti_tensor
    Extract a DTI tensor for SimNIBS anisotropic conductivity.
discover_subjects
    Discover subject IDs present in a BIDS project tree.
check_m2m_exists
    Check whether a SimNIBS m2m directory already exists.

See Also
--------
tit.pre.qsi : QSI subpackage for DWI preprocessing and reconstruction.
tit.sim : Simulation engine that consumes preprocessing outputs.
"""

from .structural import run_pipeline
from .dicom2nifti import run_dicom_to_nifti
from .fastsurfer import fastsurfer_available, run_fastsurfer
from .charm import run_charm
from .tissue_analyzer import run_tissue_analysis
from .qsi import run_qsiprep, run_qsirecon, extract_dti_tensor
from .utils import discover_subjects, check_m2m_exists
from .preflight import (
    PreprocessingInputProblem,
    PreprocessingOutput,
    find_existing_preprocessing_outputs,
    find_missing_preprocessing_inputs,
    selected_preprocessing_steps,
)

__all__ = [
    "run_pipeline",
    "run_dicom_to_nifti",
    "run_fastsurfer",
    "fastsurfer_available",
    "run_charm",
    "run_tissue_analysis",
    "run_qsiprep",
    "run_qsirecon",
    "extract_dti_tensor",
    "discover_subjects",
    "check_m2m_exists",
    "PreprocessingInputProblem",
    "PreprocessingOutput",
    "find_existing_preprocessing_outputs",
    "find_missing_preprocessing_inputs",
    "selected_preprocessing_steps",
]
