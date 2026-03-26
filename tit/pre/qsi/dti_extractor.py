#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
DTI tensor extraction for SimNIBS integration.

Extracts DTI tensors from QSIRecon DSI Studio GQI output and registers
them to SimNIBS T1 space for anisotropic conductivity simulations.

SimNIBS expects a 4D NIfTI (X, Y, Z, 6) with the diffusion tensor in
FSL upper-triangular format: [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz].
The tensor must be coregistered to the T1 in the m2m directory.

SimNIBS's ``cond2elmdata`` always applies ``correct_FSL=True``, which
assumes tensors follow FSL's radiological voxel convention (implicit
x-flip for neurological images).  DSI Studio stores tensors in the
actual image voxel frame with no such flip.  The registration step
pre-compensates for this so that the final world-space conductivity
tensors are correct.

QSIRecon DSI Studio GQI output structure (known, BIDS-compliant):
    derivatives/qsirecon/derivatives/qsirecon-DSIStudio/sub-{id}/dwi/
        sub-{id}_space-ACPC_model-tensor_param-{txx,txy,...,tzz}_dwimap.nii.gz
"""

import logging
import os
import shutil
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
# NIfTI save helper
# ============================================================================


def _save_nifti_gz(
    data: np.ndarray, affine: np.ndarray, output_path: Path, logger: logging.Logger
) -> None:
    """Save 4D NIfTI with gzip workaround for Docker bind mounts.

    Both nibabel's DeterministicGzipFile and stdlib gzip.open can fail
    with FileNotFoundError when creating .nii.gz on Docker bind-mount
    filesystems (macOS VirtioFS/gRPC-FUSE).  Work around this by
    writing and compressing in /tmp, then copying the final file.
    """
    import gzip as _gzip
    import tempfile

    import nibabel as nib

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_nii = Path(tmpdir) / "tensor.nii"
        tmp_gz = Path(tmpdir) / "tensor.nii.gz"
        nib.save(nib.Nifti1Image(data, affine), str(tmp_nii))
        with open(tmp_nii, "rb") as f_in, _gzip.open(str(tmp_gz), "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        shutil.copy2(str(tmp_gz), str(output_path))
    logger.debug(f"Saved {output_path}")


# ============================================================================
# Registration — nibabel resampling + tensor reorientation
#
# SimNIBS's cond2elmdata (cond_utils.py:194-201) applies correct_FSL,
# which extracts the rotation R_tgt from the tensor NIfTI affine, flips
# the x-column when det(R_tgt) > 0 (neurological orientation), forming
# M_fsl, then rotates: T_world = M_fsl @ T_stored @ M_fsl^T.
#
# FSL dtifit stores tensors with an implicit x-flip for neurological
# images, so correct_FSL undoes that.  DSI Studio does NOT apply this
# flip — tensors are in the actual image voxel frame.
#
# To produce correct world-space tensors after correct_FSL, we store:
#   T_stored = R_fix @ T_orig @ R_fix^T,  where  R_fix = M_fsl^T @ R_src
#
# Proof:
#   M_fsl @ (R_fix @ T @ R_fix^T) @ M_fsl^T
#   = M_fsl @ M_fsl^T @ R_src @ T @ R_src^T @ M_fsl @ M_fsl^T
#   = R_src @ T @ R_src^T  =  T_world  ✓
# ============================================================================


def _rotation_from_affine(affine: np.ndarray) -> np.ndarray:
    """Extract the pure rotation matrix from a 4x4 affine."""
    M = affine[:3, :3]
    # Normalize columns to remove scaling
    norms = np.linalg.norm(M, axis=0)
    norms[norms == 0] = 1.0
    return M / norms


def _build_target_grid(
    target_img_path: Path, resolution_mm: float = 1.0
) -> tuple[tuple[int, ...], np.ndarray]:
    """Build a target grid covering the same physical space as *target_img*
    but at a uniform *resolution_mm* isotropic voxel size.

    Resampling the DTI tensor to the full SimNIBS T1 grid (e.g. 240x512x512
    at 0.5 mm) would produce a ~1.5 GB volume.  A 1 mm grid covers the same
    brain region at a fraction of the memory while still being sufficient for
    SimNIBS mesh interpolation.

    Returns (shape, affine).
    """
    import nibabel as nib

    target = nib.load(str(target_img_path))
    src_affine = target.affine
    src_shape = target.shape[:3]

    # Physical bounding box in world coordinates (all 8 volume corners)
    s = src_shape
    ijk_corners = np.array(
        [
            [i, j, k]
            for i in (0, s[0] - 1)
            for j in (0, s[1] - 1)
            for k in (0, s[2] - 1)
        ],
        dtype=float,
    )
    world_corners = nib.affines.apply_affine(src_affine, ijk_corners)
    origin = world_corners.min(axis=0)
    extent = world_corners.max(axis=0) - origin

    # New shape at the requested resolution
    new_shape = tuple(int(np.ceil(e / resolution_mm)) for e in extent)

    # Build a RAS-aligned affine at *resolution_mm*
    new_affine = np.eye(4)
    new_affine[:3, :3] = np.diag([resolution_mm] * 3)
    new_affine[:3, 3] = origin

    return new_shape, new_affine


def _register_tensor(
    tensor_path: Path,
    fixed_t1: Path,
    output_path: Path,
    logger: logging.Logger,
) -> None:
    """Resample tensor to SimNIBS T1 space with FSL-convention reorientation.

    1. Build a 1 mm isotropic target grid covering the SimNIBS T1 FOV
    2. Resample each of the 6 tensor components to that grid
    3. Rotate each tensor so that SimNIBS's ``correct_FSL`` (which assumes
       FSL's radiological voxel convention) produces correct world-space
       conductivity tensors.

    The key insight is that ``correct_FSL`` builds ``M_fsl`` from the
    target affine (with an x-flip when det > 0) and applies
    ``T_world = M_fsl @ T_stored @ M_fsl^T``.  We pre-compensate by
    storing ``T_stored = R_fix @ T_orig @ R_fix^T`` where
    ``R_fix = M_fsl^T @ R_src``, so the final result is
    ``R_src @ T_orig @ R_src^T`` — the correct world-space tensor.
    """
    import nibabel as nib
    from nibabel.processing import resample_from_to

    tensor_img = nib.load(str(tensor_path))
    tensor_data = tensor_img.get_fdata(dtype=np.float32)

    # Use a 1 mm grid instead of the native T1 resolution to keep memory
    # manageable.  SimNIBS interpolates onto the mesh, so exact T1 voxel
    # alignment is not required — just a shared coordinate frame.
    target_shape, target_affine = _build_target_grid(fixed_t1, resolution_mm=1.0)
    logger.info(f"Target grid: {target_shape} at 1 mm (covers SimNIBS T1 FOV)")

    # Step 1: Resample each component to target grid
    logger.info("Resampling tensor components...")
    resampled = np.zeros((*target_shape, 6), dtype=np.float32)
    for i in range(6):
        comp = nib.Nifti1Image(tensor_data[..., i], tensor_img.affine)
        resampled[..., i] = resample_from_to(
            comp, (target_shape, target_affine)
        ).get_fdata(dtype=np.float32)

    # Step 2: Pre-compensate for SimNIBS correct_FSL (cond_utils.py:194-201).
    # correct_FSL assumes FSL's radiological tensor convention and applies:
    #   M_fsl = R_tgt; if det(R_tgt) > 0: flip x-column
    #   T_world = M_fsl @ T_stored @ M_fsl^T
    # DSI Studio tensors are in actual voxel space (no FSL x-flip).
    # We need: M_fsl @ T_stored @ M_fsl^T = R_src @ T_orig @ R_src^T
    # Solution: T_stored = R_fix @ T_orig @ R_fix^T, where R_fix = M_fsl^T @ R_src
    R_src = _rotation_from_affine(tensor_img.affine)
    R_tgt = _rotation_from_affine(target_affine)
    M_fsl = R_tgt.copy()
    if np.linalg.det(R_tgt) > 0:
        M_fsl[:, 0] *= -1
    R_fix = M_fsl.T @ R_src

    # Step 3: Apply tensor rotation R_fix @ T @ R_fix^T
    logger.info("Rotating tensor components for FSL convention...")
    nonzero = np.any(resampled != 0, axis=-1)
    voxels = resampled[nonzero]  # (N, 6)

    N = voxels.shape[0]
    T = np.zeros((N, 3, 3), dtype=np.float32)
    T[:, 0, 0] = voxels[:, 0]
    T[:, 0, 1] = T[:, 1, 0] = voxels[:, 1]
    T[:, 0, 2] = T[:, 2, 0] = voxels[:, 2]
    T[:, 1, 1] = voxels[:, 3]
    T[:, 1, 2] = T[:, 2, 1] = voxels[:, 4]
    T[:, 2, 2] = voxels[:, 5]

    R32 = R_fix.astype(np.float32)
    T_rot = np.einsum("ij,njk,lk->nil", R32, T, R32)

    voxels[:, 0] = T_rot[:, 0, 0]
    voxels[:, 1] = T_rot[:, 0, 1]
    voxels[:, 2] = T_rot[:, 0, 2]
    voxels[:, 3] = T_rot[:, 1, 1]
    voxels[:, 4] = T_rot[:, 1, 2]
    voxels[:, 5] = T_rot[:, 2, 2]
    resampled[nonzero] = voxels

    logger.info(f"Saving registered tensor ({resampled.shape})...")
    _save_nifti_gz(resampled, target_affine, output_path, logger)
    logger.info(f"Registered tensor saved to {output_path}")


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

    Loads the 6 tensor component files produced by ``dsi_studio_gqi``,
    validates the data, resamples it to SimNIBS T1 space with pure-Python
    nibabel registration, and saves to the m2m directory.

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
    _save_nifti_gz(tensor_data, affine, intermediate, logger)
    logger.info(f"Intermediate tensor: {intermediate}")

    # Register to SimNIBS T1 space
    if skip_registration:
        shutil.copy2(intermediate, output_path)
        logger.info("Copied tensor as-is (skip_registration=True)")
    else:
        _register_tensor(intermediate, simnibs_t1, output_path, logger)

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
