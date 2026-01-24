#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
DTI tensor extraction for SimNIBS integration.

This module extracts DTI tensors from QSIRecon outputs and converts them
to the format expected by SimNIBS for anisotropic conductivity simulations.

SimNIBS expects a 4D NIfTI file with the diffusion tensor stored as a
6-component upper triangular representation: [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz].

The tensor must be coregistered to the SimNIBS T1 space.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import numpy as np

from tit.core import constants as const, get_path_manager
from tit.pre.common import PreprocessError


# ============================================================================
# DSI STUDIO TENSOR COMPONENT MAPPING
# ============================================================================

# DSIStudio outputs individual tensor components with these parameter names
# The order here matches SimNIBS expected format: [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz]
DSISTUDIO_TENSOR_PARAMS = ["txx", "txy", "txz", "tyy", "tyz", "tzz"]


def _iter_qsirecon_subject_dirs(
    qsirecon_dir: Path, subject_id: str
) -> List[Path]:
    """
    Yield possible subject directories across QSIRecon outputs.

    QSIRecon can store outputs directly under derivatives/qsirecon/sub-<id>
    or under derivatives/qsirecon/derivatives/qsirecon-*/sub-<id>.
    """
    subject_dirs: List[Path] = []

    # Legacy/primary output
    subject_dirs.append(qsirecon_dir / f"sub-{subject_id}")

    # QSIRecon derivatives organized by recon spec
    recon_root = qsirecon_dir / "derivatives"
    if recon_root.is_dir():
        for recon_dir in recon_root.iterdir():
            if not recon_dir.is_dir():
                continue
            if not recon_dir.name.startswith("qsirecon-"):
                continue
            subject_dirs.append(recon_dir / f"sub-{subject_id}")

    # De-duplicate while preserving order
    seen = set()
    unique_dirs = []
    for d in subject_dirs:
        if d in seen:
            continue
        seen.add(d)
        unique_dirs.append(d)

    return unique_dirs


def _find_dsistudio_tensor_components(
    qsirecon_dir: Path, subject_id: str, logger: logging.Logger
) -> Optional[Dict[str, Path]]:
    """
    Find DSI Studio tensor component files in QSIRecon output.

    DSI Studio produces individual tensor component files:
    sub-XXX_space-ACPC_model-tensor_param-{txx,txy,txz,tyy,tyz,tzz}_dwimap.nii.gz

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
    Optional[Dict[str, Path]]
        Dictionary mapping tensor component names to file paths, or None if not found.
    """
    # Look for DSIStudio outputs
    dsistudio_patterns = [
        "qsirecon-DSIStudio",
        "qsirecon-dsi_studio",
        "qsirecon-dsistudio",
    ]

    for subject_dir in _iter_qsirecon_subject_dirs(qsirecon_dir, subject_id):
        if not subject_dir.exists():
            continue

        # Check if this is a DSIStudio output directory
        parent_name = subject_dir.parent.name.lower() if subject_dir.parent else ""
        is_dsistudio = any(
            pattern.lower() in parent_name.lower() for pattern in dsistudio_patterns
        )

        if not is_dsistudio:
            # Also check the direct path
            dsistudio_dir = qsirecon_dir / "derivatives" / "qsirecon-DSIStudio" / f"sub-{subject_id}"
            if dsistudio_dir.exists():
                subject_dir = dsistudio_dir
                is_dsistudio = True

        if not is_dsistudio:
            continue

        # Look for tensor component files
        dwi_dir = subject_dir / "dwi"
        if not dwi_dir.exists():
            continue

        components: Dict[str, Path] = {}
        for param in DSISTUDIO_TENSOR_PARAMS:
            # Pattern: sub-XXX_space-ACPC_model-tensor_param-{param}_dwimap.nii.gz
            pattern = f"*_model-tensor_param-{param}_dwimap.nii*"
            matches = list(dwi_dir.glob(pattern))
            if matches:
                components[param] = matches[0]
                logger.debug(f"Found tensor component {param}: {matches[0]}")

        # Check if we found all 6 components
        if len(components) == 6:
            logger.info(f"Found all 6 DSI Studio tensor components in {dwi_dir}")
            return components

    return None


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
    # Search patterns for DTI tensor files (combined 4D tensor)
    search_patterns = [
        # dipy_dki / dti naming
        "**/dwi/*_dti_tensor.nii*",
        "**/dwi/*_tensor.nii*",
        "**/dwi/*_desc-dki_dti.nii*",
        "**/dwi/*_desc-dti.nii*",
        "**/dwi/*_dki_dt.nii*",
        "**/dwi/*_dt.nii*",
        "**/dwi/*dki*dt*.nii*",
        "**/dwi/*dti*dt*.nii*",
        "**/dwi/*model-dki_tensor*.nii*",
        "**/dwi/*model-dti_tensor*.nii*",
        "**/dwi/*model-tensor*.nii*",
        # General DTI outputs
        "**/dwi/*DTI*tensor*.nii*",
        "**/dwi/*dti*tensor*.nii*",
        # Fallback patterns
        "**/*tensor*.nii*",
        "**/*DTI*.nii*",
    ]

    def _is_tensor_candidate(path: Path) -> bool:
        name_lower = path.name.lower()
        # Skip scalar maps and other non-tensor files
        if any(
            skip in name_lower
            for skip in ["fa", "md", "rd", "ad", "mask", "b0", "rgb", "odf",
                        "gfa", "iso", "qa", "ha", "linearity", "planarity",
                        "sphericity", "kfa", "mk", "ak", "rk", "mkt"]
        ):
            return False
        # Skip individual tensor component files (we handle those separately)
        if any(f"param-t{c}" in name_lower for c in ["xx", "xy", "xz", "yy", "yz", "zz"]):
            return False
        try:
            import nibabel as nib

            img = nib.load(str(path))
            shape = img.shape
        except Exception:
            return False

        if len(shape) == 4 and shape[-1] in (6, 9):
            return True
        if len(shape) == 5 and shape[-2:] == (3, 3):
            return True
        return False

    subject_dirs = _iter_qsirecon_subject_dirs(qsirecon_dir, subject_id)
    if not any(d.exists() for d in subject_dirs):
        logger.warning(
            "QSIRecon subject directory not found in any expected location: "
            + ", ".join(str(d) for d in subject_dirs)
        )
        return None

    for subject_dir in subject_dirs:
        if not subject_dir.exists():
            continue
        for pattern in search_patterns:
            matches = [
                m for m in subject_dir.glob(pattern) if _is_tensor_candidate(m)
            ]
            if matches:
                logger.debug(f"Found DTI tensor file: {matches[0]}")
                return matches[0]

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
    dt_patterns = ["**/dwi/*_DT.nii*", "**/dwi/*_dt.nii*"]
    kt_patterns = ["**/dwi/*_KT.nii*", "**/dwi/*_kt.nii*"]

    dt_file = None
    kt_file = None

    for subject_dir in _iter_qsirecon_subject_dirs(qsirecon_dir, subject_id):
        if not subject_dir.exists():
            continue
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


def _combine_dsistudio_tensor_components(
    components: Dict[str, Path], logger: logging.Logger
) -> Tuple[np.ndarray, np.ndarray, any]:
    """
    Combine DSI Studio tensor component files into a single 4D array.

    Parameters
    ----------
    components : Dict[str, Path]
        Dictionary mapping tensor component names to file paths.
    logger : logging.Logger
        Logger for status messages.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray, any]
        (tensor_data, affine, header) where tensor_data has shape (X, Y, Z, 6)
        with components in order [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz].
    """
    import nibabel as nib

    # Load each component in the correct order
    component_arrays = []
    affine = None
    header = None

    for param in DSISTUDIO_TENSOR_PARAMS:
        if param not in components:
            raise PreprocessError(f"Missing tensor component: {param}")

        logger.debug(f"Loading tensor component {param} from {components[param]}")
        img = nib.load(str(components[param]))

        if affine is None:
            affine = img.affine
            header = img.header

        data = img.get_fdata(dtype=np.float32)

        # Ensure 3D
        if data.ndim == 4:
            data = data[..., 0]

        component_arrays.append(data)

    # Stack into 4D array with shape (X, Y, Z, 6)
    tensor_data = np.stack(component_arrays, axis=-1)
    logger.info(f"Combined tensor shape: {tensor_data.shape}")

    return tensor_data, affine, header


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
        raise ValueError("Tensor data must be 4D or 5D")

    if tensor_data.ndim == 5:
        if tensor_data.shape[-2:] != (3, 3):
            logger.error(f"Unexpected tensor shape: {tensor_data.shape}")
            raise ValueError(f"Unexpected tensor shape: {tensor_data.shape}")
        spatial_shape = tensor_data.shape[:3]
        tensor_data = tensor_data.reshape(*spatial_shape, 9)

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


def _find_qsiprep_t1(project_dir: Path, subject_id: str) -> Optional[Path]:
    """Find the qsiprep T1 in ACPC space."""
    qsiprep_t1 = (
        project_dir / "derivatives" / "qsiprep" / f"sub-{subject_id}" / "anat" /
        f"sub-{subject_id}_space-ACPC_desc-preproc_T1w.nii.gz"
    )
    if qsiprep_t1.exists():
        return qsiprep_t1
    return None


def _check_ants_available() -> bool:
    """Check if ANTs is available in the current environment."""
    try:
        result = subprocess.run(
            ["which", "antsRegistration"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def _register_tensor_to_simnibs_t1(
    tensor_path: Path,
    qsiprep_t1_path: Path,
    simnibs_t1_path: Path,
    output_path: Path,
    logger: logging.Logger,
    docker_image: str = "idossha/simnibs:v2.2.4",
) -> Path:
    """
    Register the tensor to SimNIBS T1 space using ANTs or nibabel resampling.

    This function first checks if ANTs is available in the current environment.
    If running inside a Docker container with ANTs, it uses ANTs directly.
    Otherwise, it falls back to nibabel-based resampling.

    Parameters
    ----------
    tensor_path : Path
        Path to the tensor file in ACPC space.
    qsiprep_t1_path : Path
        Path to the qsiprep T1 in ACPC space (moving reference).
    simnibs_t1_path : Path
        Path to the SimNIBS T1 (fixed reference).
    output_path : Path
        Path for the output registered tensor.
    logger : logging.Logger
        Logger for status messages.
    docker_image : str
        Docker image to use for registration (if using Docker).

    Returns
    -------
    Path
        Path to the registered tensor file.
    """
    # Check if ANTs is available locally
    if _check_ants_available():
        logger.info("ANTs found in environment, using ANTs for registration")
        with tempfile.TemporaryDirectory() as tmpdir:
            return _register_with_ants_local(
                tensor_path, qsiprep_t1_path, simnibs_t1_path,
                output_path, Path(tmpdir), logger
            )

    # Fall back to simple resampling
    logger.info(
        "ANTs not available. Using nibabel resampling to align tensor to "
        "SimNIBS T1 space. Note: This performs spatial resampling but not "
        "tensor reorientation, which is acceptable for most applications."
    )
    return _resample_tensor_to_target(
        tensor_path, simnibs_t1_path, output_path, logger
    )


def _register_with_ants_local(
    tensor_path: Path,
    moving_t1_path: Path,
    fixed_t1_path: Path,
    output_path: Path,
    tmpdir: Path,
    logger: logging.Logger,
) -> Path:
    """
    Use ANTs (available locally) to register tensor to SimNIBS T1 space.

    This performs affine registration of T1s, then applies the transform
    to the tensor with proper reorientation.
    """
    # Step 1: Register T1 to T1
    xfm_prefix = str(tmpdir / "t1_to_simnibs_")
    reg_cmd = [
        "antsRegistrationSyN.sh",
        "-d", "3",
        "-f", str(fixed_t1_path),
        "-m", str(moving_t1_path),
        "-o", xfm_prefix,
        "-t", "a",  # Affine only for speed
    ]

    logger.info("Running ANTs registration...")
    result = subprocess.run(reg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"ANTs registration failed: {result.stderr}")
        raise PreprocessError(f"ANTs registration failed: {result.stderr}")

    # Step 2: Apply transform to tensor
    xfm_file = f"{xfm_prefix}0GenericAffine.mat"

    # For tensors, we use image type 2 (tensor)
    apply_cmd = [
        "antsApplyTransforms",
        "-d", "3",
        "-e", "2",  # Tensor image type
        "-i", str(tensor_path),
        "-r", str(fixed_t1_path),
        "-o", str(output_path),
        "-t", xfm_file,
        "-n", "Linear",
    ]

    logger.info("Applying transform to tensor...")
    result = subprocess.run(apply_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"ANTs apply transform failed: {result.stderr}")
        raise PreprocessError(f"ANTs apply transform failed: {result.stderr}")

    return output_path


def _resample_tensor_to_target(
    tensor_path: Path,
    target_path: Path,
    output_path: Path,
    logger: logging.Logger,
) -> Path:
    """
    Resample tensor to target space using nibabel.

    This is a simple fallback when ANTs is not available.
    Note: This does not perform proper tensor reorientation.
    """
    import nibabel as nib
    from nibabel.processing import resample_from_to

    logger.info("Resampling tensor to SimNIBS T1 space...")

    tensor_img = nib.load(str(tensor_path))
    target_img = nib.load(str(target_path))

    # Resample each component separately
    tensor_data = tensor_img.get_fdata(dtype=np.float32)
    target_shape = target_img.shape[:3]
    target_affine = target_img.affine

    # Create output array
    output_data = np.zeros((*target_shape, 6), dtype=np.float32)

    for i in range(6):
        component_img = nib.Nifti1Image(
            tensor_data[..., i], tensor_img.affine, tensor_img.header
        )
        resampled = resample_from_to(component_img, (target_shape, target_affine))
        output_data[..., i] = resampled.get_fdata(dtype=np.float32)

    # Save output
    output_img = nib.Nifti1Image(output_data, target_affine)
    nib.save(output_img, str(output_path))

    logger.info(f"Resampled tensor saved to {output_path}")
    return output_path


def extract_dti_tensor(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    source: str = "qsirecon",
    overwrite: bool = False,
    skip_registration: bool = False,
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
    skip_registration : bool, optional
        If True, skip registration to SimNIBS T1 space. Use this if the
        tensor is already in the correct space. Default: False.

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
    if source != "qsirecon":
        raise PreprocessError(f"Unknown source: {source}")

    qsirecon_dir = Path(project_dir) / "derivatives" / "qsirecon"

    # Try to find DSI Studio tensor components first (most common)
    dsistudio_components = _find_dsistudio_tensor_components(
        qsirecon_dir, subject_id, logger
    )

    if dsistudio_components:
        logger.info("Using DSI Studio tensor components")
        tensor_data, affine, header = _combine_dsistudio_tensor_components(
            dsistudio_components, logger
        )
        # Already in the correct format [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz]
        simnibs_tensor = tensor_data
    else:
        # Try to find DKI tensor
        dt_file, _ = _find_dki_tensor_files(qsirecon_dir, subject_id, logger)

        if dt_file is not None:
            source_file = dt_file
            logger.info(f"Using DKI diffusion tensor: {dt_file}")
        else:
            # Fall back to general DTI tensor search
            source_file = _find_dti_tensor_file(qsirecon_dir, subject_id, logger)

        if source_file is None:
            raise PreprocessError(
                f"No DTI tensor found for subject {subject_id} in QSIRecon output. "
                "Ensure QSIRecon was run with DSI Studio (dsi_studio_gqi) or "
                "another DTI-producing spec like dipy_dki."
            )

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

    # Save intermediate tensor (before registration)
    intermediate_path = Path(m2m_dir) / "DTI_ACPC_tensor.nii.gz"
    try:
        intermediate_img = nib.Nifti1Image(simnibs_tensor, affine, header)
        nib.save(intermediate_img, str(intermediate_path))
        logger.info(f"Saved intermediate tensor to: {intermediate_path}")
    except Exception as e:
        raise PreprocessError(f"Failed to save intermediate tensor: {e}")

    # Register to SimNIBS T1 space
    if not skip_registration:
        simnibs_t1_path = Path(m2m_dir) / const.FILE_T1
        if not simnibs_t1_path.exists():
            raise PreprocessError(
                f"SimNIBS T1 not found at {simnibs_t1_path}. "
                "Run SimNIBS charm first."
            )

        qsiprep_t1_path = _find_qsiprep_t1(Path(project_dir), subject_id)
        if qsiprep_t1_path is None:
            logger.warning(
                "qsiprep T1 not found. Using simple resampling instead of "
                "proper registration."
            )
            _resample_tensor_to_target(
                intermediate_path, simnibs_t1_path, output_path, logger
            )
        else:
            try:
                _register_tensor_to_simnibs_t1(
                    intermediate_path,
                    qsiprep_t1_path,
                    simnibs_t1_path,
                    output_path,
                    logger,
                )
            except Exception as e:
                logger.warning(
                    f"Registration failed: {e}. Falling back to simple resampling."
                )
                _resample_tensor_to_target(
                    intermediate_path, simnibs_t1_path, output_path, logger
                )
    else:
        # Just copy the intermediate file to output
        shutil.copy2(intermediate_path, output_path)
        logger.info(f"Copied tensor to output (skip_registration=True)")

    logger.info(f"Saved DTI tensor to: {output_path}")
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
