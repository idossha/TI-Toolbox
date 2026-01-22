#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
DTI tensor extraction for SimNIBS integration.

This module extracts DTI tensors from QSIRecon outputs and converts them
to the format expected by SimNIBS for anisotropic conductivity simulations.

SimNIBS expects a 4D NIfTI file with the diffusion tensor stored as a
6-component upper triangular representation: [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz].
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np

from tit.core import constants as const, get_path_manager
from tit.pre.common import PreprocessError


def _find_dti_tensor_file(
    qsirecon_dir: Path, subject_id: str, logger: logging.Logger
) -> Optional[Path]:
    """
    Find the DTI tensor file in QSIRecon output.

    QSIRecon stores DTI tensors in various locations depending on the
    reconstruction spec used. This function searches common patterns.

    Parameters
    ----------
    qsirecon_dir : Path
        Path to the QSIRecon output directory.
    subject_id : str
        Subject identifier.
    logger : logging.Logger
        Logger for status messages.

    Returns
    -------
    Optional[Path]
        Path to the DTI tensor file, or None if not found.
    """
    subject_dir = qsirecon_dir / f"sub-{subject_id}"

    if not subject_dir.exists():
        logger.warning(f"QSIRecon subject directory not found: {subject_dir}")
        return None

    # Search patterns for DTI tensor files
    # Different recon specs produce different output patterns
    search_patterns = [
        # dipy_dki outputs
        "**/dwi/*_dti_tensor.nii*",
        "**/dwi/*_tensor.nii*",
        # General DTI outputs
        "**/dwi/*DTI*tensor*.nii*",
        "**/dwi/*dti*tensor*.nii*",
        # Fallback patterns
        "**/*tensor*.nii*",
        "**/*DTI*.nii*",
    ]

    for pattern in search_patterns:
        matches = list(subject_dir.glob(pattern))
        if matches:
            # Filter to find the most likely DTI tensor file
            for match in matches:
                name_lower = match.name.lower()
                # Skip files that are clearly not tensor files
                if any(
                    skip in name_lower
                    for skip in ["fa", "md", "rd", "ad", "mask", "b0"]
                ):
                    continue
                logger.debug(f"Found DTI tensor file: {match}")
                return match

    logger.warning(f"No DTI tensor file found for subject {subject_id}")
    return None


def _find_dki_tensor_files(
    qsirecon_dir: Path, subject_id: str, logger: logging.Logger
) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Find DKI tensor files (DT and KT) in QSIRecon output.

    DKI (Diffusion Kurtosis Imaging) produces both a diffusion tensor (DT)
    and a kurtosis tensor (KT). For SimNIBS, we only need the DT.

    Parameters
    ----------
    qsirecon_dir : Path
        Path to the QSIRecon output directory.
    subject_id : str
        Subject identifier.
    logger : logging.Logger
        Logger for status messages.

    Returns
    -------
    Tuple[Optional[Path], Optional[Path]]
        (DT path, KT path) tuple. Either may be None if not found.
    """
    subject_dir = qsirecon_dir / f"sub-{subject_id}"

    dt_patterns = ["**/dwi/*_DT.nii*", "**/dwi/*_dt.nii*"]
    kt_patterns = ["**/dwi/*_KT.nii*", "**/dwi/*_kt.nii*"]

    dt_file = None
    kt_file = None

    for pattern in dt_patterns:
        matches = list(subject_dir.glob(pattern))
        if matches:
            dt_file = matches[0]
            break

    for pattern in kt_patterns:
        matches = list(subject_dir.glob(pattern))
        if matches:
            kt_file = matches[0]
            break

    return dt_file, kt_file


def _convert_tensor_to_simnibs_format(
    tensor_data: np.ndarray, logger: logging.Logger
) -> np.ndarray:
    """
    Convert a diffusion tensor to SimNIBS format.

    SimNIBS expects a 6-component upper triangular representation:
    [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz]

    Input tensor formats supported:
    - 6-component: Already in correct format
    - 9-component (3x3 flattened): Convert to upper triangular
    - 3D with 4th dimension of 6 or 9: Process accordingly

    Parameters
    ----------
    tensor_data : np.ndarray
        Input tensor data.
    logger : logging.Logger
        Logger for status messages.

    Returns
    -------
    np.ndarray
        Tensor in SimNIBS 6-component format with shape (X, Y, Z, 6).
    """
    # Handle different input shapes
    if tensor_data.ndim == 3:
        logger.error("Expected 4D tensor data, got 3D")
        raise ValueError("Tensor data must be 4D")

    if tensor_data.ndim != 4:
        logger.error(f"Unexpected tensor shape: {tensor_data.shape}")
        raise ValueError(f"Unexpected tensor shape: {tensor_data.shape}")

    n_components = tensor_data.shape[-1]

    if n_components == 6:
        # Already in upper triangular format
        logger.debug("Tensor already in 6-component format")
        return tensor_data

    elif n_components == 9:
        # Convert from 3x3 flattened to upper triangular
        # Assumes row-major ordering: [D00, D01, D02, D10, D11, D12, D20, D21, D22]
        logger.debug("Converting 9-component tensor to 6-component format")
        spatial_shape = tensor_data.shape[:3]
        output = np.zeros((*spatial_shape, 6), dtype=tensor_data.dtype)

        # Extract upper triangular elements
        # [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz] = indices [0, 1, 2, 4, 5, 8]
        output[..., 0] = tensor_data[..., 0]  # Dxx
        output[..., 1] = tensor_data[..., 1]  # Dxy
        output[..., 2] = tensor_data[..., 2]  # Dxz
        output[..., 3] = tensor_data[..., 4]  # Dyy
        output[..., 4] = tensor_data[..., 5]  # Dyz
        output[..., 5] = tensor_data[..., 8]  # Dzz

        return output

    else:
        logger.error(f"Unexpected number of tensor components: {n_components}")
        raise ValueError(
            f"Expected 6 or 9 tensor components, got {n_components}"
        )


def extract_dti_tensor(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    source: str = "qsirecon",
    overwrite: bool = False,
) -> Path:
    """
    Extract DTI tensor from QSIRecon output for SimNIBS.

    This function finds the DTI tensor in QSIRecon outputs, converts it
    to SimNIBS format, and saves it to the m2m directory.

    Parameters
    ----------
    project_dir : str
        Path to the BIDS project root directory.
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    logger : logging.Logger
        Logger for status messages.
    source : str, optional
        Source of DTI tensor. Currently only 'qsirecon' is supported.
        Default: 'qsirecon'.
    overwrite : bool, optional
        Whether to overwrite existing tensor file. Default: False.

    Returns
    -------
    Path
        Path to the extracted DTI tensor file in m2m directory.

    Raises
    ------
    PreprocessError
        If tensor extraction fails.
    """
    # Delayed import to avoid circular dependencies
    import nibabel as nib

    logger.info(f"Extracting DTI tensor for subject {subject_id}")

    # Get paths
    pm = get_path_manager()
    pm.project_dir = project_dir

    m2m_dir = pm.path_optional("m2m", subject_id=subject_id)
    if not m2m_dir or not os.path.isdir(m2m_dir):
        raise PreprocessError(
            f"m2m directory not found for subject {subject_id}. "
            "Run SimNIBS charm first."
        )

    output_path = Path(m2m_dir) / const.FILE_DTI_TENSOR

    # Check for existing output
    if output_path.exists() and not overwrite:
        logger.info(f"DTI tensor already exists: {output_path}")
        return output_path

    # Find source tensor
    if source == "qsirecon":
        qsirecon_dir = Path(project_dir) / "derivatives" / "qsirecon"

        # Try to find DKI tensor first (more accurate)
        dt_file, _ = _find_dki_tensor_files(qsirecon_dir, subject_id, logger)

        if dt_file is not None:
            source_file = dt_file
            logger.info(f"Using DKI diffusion tensor: {dt_file}")
        else:
            # Fall back to general DTI tensor search
            source_file = _find_dti_tensor_file(
                qsirecon_dir, subject_id, logger
            )

        if source_file is None:
            raise PreprocessError(
                f"No DTI tensor found for subject {subject_id} in QSIRecon output. "
                "Ensure QSIRecon was run with dipy_dki or another DTI-producing spec."
            )
    else:
        raise PreprocessError(f"Unknown source: {source}")

    logger.info(f"Source tensor file: {source_file}")

    # Load and convert tensor
    try:
        tensor_img = nib.load(str(source_file))
        tensor_data = tensor_img.get_fdata(dtype=np.float32)
        affine = tensor_img.affine
        header = tensor_img.header
    except Exception as e:
        raise PreprocessError(f"Failed to load tensor file: {e}")

    # Convert to SimNIBS format
    try:
        simnibs_tensor = _convert_tensor_to_simnibs_format(tensor_data, logger)
    except ValueError as e:
        raise PreprocessError(f"Failed to convert tensor: {e}")

    # Save to m2m directory
    try:
        output_img = nib.Nifti1Image(simnibs_tensor, affine, header)
        nib.save(output_img, str(output_path))
        logger.info(f"Saved DTI tensor to: {output_path}")
    except Exception as e:
        raise PreprocessError(f"Failed to save tensor file: {e}")

    return output_path


def check_dti_tensor_exists(project_dir: str, subject_id: str) -> bool:
    """
    Check if a DTI tensor file exists for a subject.

    Parameters
    ----------
    project_dir : str
        Path to the project directory.
    subject_id : str
        Subject identifier.

    Returns
    -------
    bool
        True if the DTI tensor file exists in the m2m directory.
    """
    pm = get_path_manager()
    pm.project_dir = project_dir

    m2m_dir = pm.path_optional("m2m", subject_id=subject_id)
    if not m2m_dir:
        return False

    tensor_path = Path(m2m_dir) / const.FILE_DTI_TENSOR
    return tensor_path.exists()
