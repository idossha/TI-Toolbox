"""
Pre-processing Python APIs for TI-Toolbox.

This package provides standalone, reusable functions for preprocessing steps
such as DICOM conversion, FreeSurfer recon-all, SimNIBS charm, atlas creation,
tissue analysis, and DWI preprocessing via QSIPrep/QSIRecon.
"""

from .structural import run_pipeline
from .dicom2nifti import run_dicom_to_nifti
from .recon_all import run_recon_all
from .charm import run_charm
from .tissue_analyzer import run_tissue_analysis
from .fix_t2_filenames import run_fix_t2_filenames
from .qsi import run_qsiprep, run_qsirecon, extract_dti_tensor

__all__ = [
    "run_pipeline",
    "run_dicom_to_nifti",
    "run_recon_all",
    "run_charm",
    "run_tissue_analysis",
    "run_fix_t2_filenames",
    "run_qsiprep",
    "run_qsirecon",
    "extract_dti_tensor",
]
