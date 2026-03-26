#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
DTI tensor extraction for SimNIBS integration.

Extracts DTI tensors from QSIRecon DSI Studio GQI output and registers
them to SimNIBS T1 space for anisotropic conductivity simulations.

SimNIBS expects a 4D NIfTI (X, Y, Z, 6) with the diffusion tensor in
FSL upper-triangular format: [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz].
The tensor must be coregistered to the T1 in the m2m directory.

QSIRecon DSI Studio GQI output structure (known, BIDS-compliant):
    derivatives/qsirecon/derivatives/qsirecon-DSIStudio/sub-{id}/dwi/
        sub-{id}_space-ACPC_model-tensor_param-{txx,txy,...,tzz}_dwimap.nii.gz
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from tit import constants as const
from tit.paths import get_path_manager
from tit.pre.utils import PreprocessError

# DSI Studio tensor component names in SimNIBS order
_TENSOR_PARAMS = ("txx", "txy", "txz", "tyy", "tyz", "tzz")

# Known QSIRecon DSI Studio derivative directory name
_DSISTUDIO_DIR = "qsirecon-DSIStudio"


# ============================================================================
# Deterministic path resolution
# ============================================================================


def _dsistudio_dwi_dir(project_dir: Path, subject_id: str) -> Path:
    """Return the known DSI Studio DWI output directory."""
    return (
        project_dir
        / "derivatives"
        / "qsirecon"
        / "derivatives"
        / _DSISTUDIO_DIR
        / f"sub-{subject_id}"
        / "dwi"
    )


def _qsiprep_t1(project_dir: Path, subject_id: str) -> Path:
    """Return the known QSIPrep ACPC T1 path."""
    return (
        project_dir
        / "derivatives"
        / "qsiprep"
        / f"sub-{subject_id}"
        / "anat"
        / f"sub-{subject_id}_space-ACPC_desc-preproc_T1w.nii.gz"
    )


# ============================================================================
# Tensor loading
# ============================================================================


def _load_dsistudio_tensor(
    dwi_dir: Path, subject_id: str, logger: logging.Logger
) -> tuple[np.ndarray, np.ndarray, object]:
    """Load 6 DSI Studio tensor component files and stack into (X,Y,Z,6).

    Returns (tensor_data, affine, header).
    """
    import nibabel as nib

    arrays = []
    affine = None
    header = None

    for param in _TENSOR_PARAMS:
        pattern = f"sub-{subject_id}_space-ACPC_model-tensor_param-{param}_dwimap.nii*"
        matches = list(dwi_dir.glob(pattern))
        if not matches:
            raise PreprocessError(
                f"Missing tensor component '{param}' in {dwi_dir}. "
                f"Expected file matching: {pattern}"
            )

        img = nib.load(str(matches[0]))
        if affine is None:
            affine = img.affine
            header = img.header

        data = img.get_fdata(dtype=np.float32)
        if data.ndim == 4:
            data = data[..., 0]
        arrays.append(data)
        logger.debug(f"Loaded {param}: {matches[0].name}")

    tensor = np.stack(arrays, axis=-1)
    logger.info(f"Tensor shape: {tensor.shape}")
    return tensor, affine, header


# ============================================================================
# Validation
# ============================================================================


def _validate_tensor(tensor: np.ndarray, logger: logging.Logger) -> None:
    """Check tensor data for NaN/Inf and adequate brain coverage."""
    if tensor.ndim != 4 or tensor.shape[-1] != 6:
        raise PreprocessError(
            f"Invalid tensor shape {tensor.shape}, expected (X, Y, Z, 6)"
        )

    bad = ~np.isfinite(tensor)
    if bad.any():
        n_bad = int(bad.sum())
        logger.warning(f"Replacing {n_bad} non-finite values with 0")
        tensor[bad] = 0.0

    nonzero = int(np.count_nonzero(tensor.sum(axis=-1)))
    total = int(np.prod(tensor.shape[:3]))
    pct = 100.0 * nonzero / total

    if nonzero == 0:
        raise PreprocessError("Tensor is entirely zero — no valid diffusion data.")

    logger.info(f"Tensor: {nonzero}/{total} non-zero voxels ({pct:.1f}%)")
    if pct < 1.0:
        logger.warning(f"Very few non-zero voxels ({pct:.1f}%)")


# ============================================================================
# Registration — ANTs affine with tensor reorientation
# ============================================================================


def _register_tensor(
    tensor_path: Path,
    moving_t1: Path,
    fixed_t1: Path,
    output_path: Path,
    logger: logging.Logger,
) -> None:
    """Register tensor from ACPC space to SimNIBS T1 space using ANTs.

    Performs a two-step registration:
    1. Affine registration of QSIPrep T1 (ACPC) -> SimNIBS T1 (native)
    2. Apply the transform to the tensor with -e 2 (PPD reorientation)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        xfm_prefix = str(Path(tmpdir) / "t1_to_simnibs_")

        # Step 1: T1-to-T1 affine registration
        logger.info("ANTs: registering QSIPrep T1 -> SimNIBS T1 (affine)...")
        result = subprocess.run(
            [
                "antsRegistrationSyN.sh",
                "-d",
                "3",
                "-f",
                str(fixed_t1),
                "-m",
                str(moving_t1),
                "-o",
                xfm_prefix,
                "-t",
                "a",  # affine only
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PreprocessError(f"ANTs registration failed:\n{result.stderr}")

        # Step 2: Apply transform to tensor with PPD reorientation
        xfm_file = f"{xfm_prefix}0GenericAffine.mat"
        logger.info("ANTs: applying affine to tensor (image type=tensor)...")
        result = subprocess.run(
            [
                "antsApplyTransforms",
                "-d",
                "3",
                "-e",
                "2",  # tensor image type (PPD reorientation)
                "-i",
                str(tensor_path),
                "-r",
                str(fixed_t1),
                "-o",
                str(output_path),
                "-t",
                xfm_file,
                "-n",
                "Linear",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PreprocessError(f"ANTs tensor transform failed:\n{result.stderr}")


def _resample_tensor(
    tensor_path: Path,
    target_path: Path,
    output_path: Path,
    logger: logging.Logger,
) -> None:
    """Resample tensor to target space using nibabel (no reorientation).

    Fallback when ANTs is unavailable. Spatial resampling only — tensor
    eigenvectors are NOT rotated, reducing accuracy.
    """
    import nibabel as nib
    from nibabel.processing import resample_from_to

    logger.warning(
        "Using nibabel resampling (no tensor reorientation). "
        "Anisotropic conductivity accuracy will be reduced."
    )

    tensor_img = nib.load(str(tensor_path))
    target_img = nib.load(str(target_path))
    target_shape = target_img.shape[:3]
    target_affine = target_img.affine

    tensor_data = tensor_img.get_fdata(dtype=np.float32)
    output = np.zeros((*target_shape, 6), dtype=np.float32)

    for i in range(6):
        comp = nib.Nifti1Image(
            tensor_data[..., i], tensor_img.affine, tensor_img.header
        )
        output[..., i] = resample_from_to(
            comp, (target_shape, target_affine)
        ).get_fdata(dtype=np.float32)

    nib.save(nib.Nifti1Image(output, target_affine), str(output_path))
    logger.info(f"Resampled tensor saved to {output_path}")


# ============================================================================
# Public API
# ============================================================================


def extract_dti_tensor(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    skip_registration: bool = False,
) -> Path:
    """Extract DTI tensor from QSIRecon DSI Studio output for SimNIBS.

    Loads the 6 tensor component files produced by `dsi_studio_gqi`,
    validates the data, registers it to SimNIBS T1 space via ANTs,
    and saves to the m2m directory.

    Parameters
    ----------
    project_dir : str
        BIDS project root directory.
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    logger : logging.Logger
        Logger for status messages.
    skip_registration : bool
        Skip registration to SimNIBS T1. Keeps tensor in ACPC space.

    Returns
    -------
    Path
        Path to ``DTI_coregT1_tensor.nii.gz`` in the m2m directory.

    Raises
    ------
    PreprocessError
        If any step fails.
    """
    import nibabel as nib

    project = Path(project_dir)
    logger.info(f"Extracting DTI tensor for subject {subject_id}")

    # Resolve paths
    pm = get_path_manager(project_dir)
    m2m_dir = Path(pm.m2m(subject_id))
    if not m2m_dir.is_dir():
        raise PreprocessError(f"m2m directory not found: {m2m_dir}. Run charm first.")

    output_path = m2m_dir / const.FILE_DTI_TENSOR
    if output_path.exists():
        raise PreprocessError(
            f"DTI tensor already exists at {output_path}. "
            "Remove the file before rerunning."
        )

    simnibs_t1 = m2m_dir / const.FILE_T1
    if not simnibs_t1.exists():
        raise PreprocessError(f"SimNIBS T1 not found: {simnibs_t1}. Run charm first.")

    dwi_dir = _dsistudio_dwi_dir(project, subject_id)
    if not dwi_dir.is_dir():
        raise PreprocessError(
            f"DSI Studio output not found: {dwi_dir}. "
            "Run QSIRecon with dsi_studio_gqi first."
        )

    # Load and validate tensor
    tensor_data, affine, header = _load_dsistudio_tensor(dwi_dir, subject_id, logger)
    _validate_tensor(tensor_data, logger)

    # Save intermediate tensor in ACPC space
    intermediate = m2m_dir / "DTI_ACPC_tensor.nii.gz"
    nib.save(nib.Nifti1Image(tensor_data, affine, header), str(intermediate))
    logger.info(f"Intermediate tensor: {intermediate}")

    # Register to SimNIBS T1 space
    if skip_registration:
        shutil.copy2(intermediate, output_path)
        logger.info("Copied tensor as-is (skip_registration=True)")
    else:
        qsiprep_t1 = _qsiprep_t1(project, subject_id)
        if not qsiprep_t1.exists():
            raise PreprocessError(
                f"QSIPrep T1 not found: {qsiprep_t1}. " "Run QSIPrep first."
            )
        _register_tensor(intermediate, qsiprep_t1, simnibs_t1, output_path, logger)

    logger.info(f"DTI tensor saved to: {output_path}")

    # Generate QC report (non-blocking)
    from tit.reporting.generators.dti_qc import create_dti_qc_report

    qc_path = create_dti_qc_report(
        project_dir=project_dir,
        subject_id=subject_id,
        tensor_file=str(output_path),
        t1_file=str(simnibs_t1),
    )
    logger.info(f"DTI QC report: {qc_path}")

    return output_path


def check_dti_tensor_exists(project_dir: str, subject_id: str) -> bool:
    """Check if DTI tensor exists in the m2m directory."""
    pm = get_path_manager(project_dir)
    m2m_dir = pm.m2m(subject_id)
    if not os.path.isdir(m2m_dir):
        return False
    return (Path(m2m_dir) / const.FILE_DTI_TENSOR).exists()
