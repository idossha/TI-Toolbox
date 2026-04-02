"""
Preprocessing APIs for TI-Toolbox.

This package provides standalone, reusable functions for every stage of the
TI-Toolbox preprocessing pipeline: DICOM conversion, FreeSurfer cortical
reconstruction, SimNIBS head-mesh generation (CHARM), tissue analysis, and
diffusion-weighted imaging (DWI) preprocessing via QSIPrep/QSIRecon.

All heavy computation runs inside Docker containers (SimNIBS, FreeSurfer,
QSIPrep/QSIRecon). The functions in this package orchestrate those containers
and manage BIDS-compliant file layouts.

Public API
----------
run_pipeline
    Full preprocessing pipeline orchestrator (sequential or parallel).
run_dicom_to_nifti
    Convert DICOM series to BIDS-compliant NIfTI files.
run_recon_all
    Run FreeSurfer ``recon-all`` cortical reconstruction.
run_subcortical_segmentations
    Run thalamic-nuclei and hippocampal-subfield segmentations.
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
from .recon_all import run_recon_all, run_subcortical_segmentations
from .charm import run_charm
from .tissue_analyzer import run_tissue_analysis
from .qsi import run_qsiprep, run_qsirecon, extract_dti_tensor
from .utils import discover_subjects, check_m2m_exists

__all__ = [
    "run_pipeline",
    "run_dicom_to_nifti",
    "run_recon_all",
    "run_subcortical_segmentations",
    "run_charm",
    "run_tissue_analysis",
    "run_qsiprep",
    "run_qsirecon",
    "extract_dti_tensor",
    "discover_subjects",
    "check_m2m_exists",
]
