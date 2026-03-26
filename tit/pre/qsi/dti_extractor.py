#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
DTI tensor extraction for SimNIBS integration.

Extracts DTI tensors from QSIRecon DSI Studio GQI output, registers them
to the SimNIBS T1 grid, and pre-compensates for SimNIBS's ``correct_FSL``
so that world-space conductivity tensors are correct.

SimNIBS expects ``DTI_coregT1_tensor.nii.gz`` — a 4D NIfTI (X, Y, Z, 6)
in FSL upper-triangular order: [Dxx, Dxy, Dxz, Dyy, Dyz, Dzz].

QSIRecon DSI Studio GQI output (BIDS-compliant):
    derivatives/qsirecon/derivatives/qsirecon-DSIStudio/sub-{id}/dwi/
        sub-{id}_space-ACPC_model-tensor_param-{txx,...,tzz}_dwimap.nii.gz
"""

import logging
import os
import shutil
from pathlib import Path

import numpy as np

from tit import constants as const
from tit.paths import get_path_manager
from tit.pre.utils import PreprocessError

_TENSOR_PARAMS = ("txx", "txy", "txz", "tyy", "tyz", "tzz")
_DSISTUDIO_DIR = "qsirecon-DSIStudio"


# ── Path helpers ─────────────────────────────────────────────────────────


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


# ── Tensor loading ───────────────────────────────────────────────────────


def _load_tensor(
    dwi_dir: Path, subject_id: str, logger: logging.Logger
) -> tuple[np.ndarray, np.ndarray]:
    """Load 6 DSI Studio tensor components → (X, Y, Z, 6) array + affine."""
    import nibabel as nib

    arrays = []
    affine = None

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
        data = img.get_fdata(dtype=np.float32)
        if data.ndim == 4:
            data = data[..., 0]
        arrays.append(data)
        logger.debug(f"Loaded {param}: {matches[0].name}")

    tensor = np.stack(arrays, axis=-1)
    logger.info(f"Tensor shape: {tensor.shape}")
    return tensor, affine


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


# ── I/O helper ───────────────────────────────────────────────────────────


def _save_nifti_gz(
    data: np.ndarray, affine: np.ndarray, output_path: Path, logger: logging.Logger
) -> None:
    """Save NIfTI via /tmp to work around Docker bind-mount gzip failures."""
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


# ── Registration ─────────────────────────────────────────────────────────
#
# SimNIBS correct_FSL (cond_utils.py:194-201) always runs on the tensor:
#   M = normalize(affine[:3,:3]);  if det(M)>0: flip x;  T_world = M·T·M^T
#
# FSL dtifit bakes in an implicit x-flip; DSI Studio does NOT.
# We pre-compensate: store  R_fix·T·R_fix^T  where  R_fix = M_fsl^T · R_src
# so that  M_fsl · stored · M_fsl^T = R_src · T · R_src^T = T_world.


def _rotation_from_affine(affine: np.ndarray) -> np.ndarray:
    """Extract pure rotation from a 4x4 affine (column-normalize the 3x3)."""
    M = affine[:3, :3].copy()
    norms = np.linalg.norm(M, axis=0)
    norms[norms == 0] = 1.0
    return M / norms


def _find_alignment(
    moving_path: Path, fixed_path: Path, logger: logging.Logger
) -> np.ndarray:
    """Find the translation aligning moving to fixed via cross-correlation.

    Resamples both images to a common 2 mm RAS grid and uses 3D
    cross-correlation to find the voxel shift that maximizes overlap.
    Returns the shift in mm (world coordinates).
    """
    import nibabel as nib
    from nibabel.processing import resample_from_to
    from scipy.signal import fftconvolve

    res = 2.0
    half = 150.0  # ±150 mm covers any head
    n = int(2 * half / res)
    common_shape = (n, n, n)
    common_affine = np.diag([res, res, res, 1.0])
    common_affine[:3, 3] = [-half, -half, -half]

    mov = nib.load(str(moving_path))
    fix = nib.load(str(fixed_path))

    mov_rs = resample_from_to(mov, (common_shape, common_affine), order=1).get_fdata(
        dtype=np.float32
    )
    fix_rs = resample_from_to(fix, (common_shape, common_affine), order=1).get_fdata(
        dtype=np.float32
    )

    # Normalize (zero-mean, unit-variance)
    mov_rs = (mov_rs - mov_rs.mean()) / (mov_rs.std() + 1e-10)
    fix_rs = (fix_rs - fix_rs.mean()) / (fix_rs.std() + 1e-10)

    # Cross-correlate: peak gives optimal shift
    cc = fftconvolve(fix_rs, mov_rs[::-1, ::-1, ::-1], mode="full")
    peak = np.unravel_index(cc.argmax(), cc.shape)
    center = np.array(mov_rs.shape) - 1
    shift = (np.array(peak) - center) * res

    logger.info(
        f"Cross-correlation shift: [{shift[0]:.1f}, {shift[1]:.1f}, {shift[2]:.1f}] mm"
    )
    return shift


def _register_tensor(
    tensor_data: np.ndarray,
    tensor_affine: np.ndarray,
    fixed_t1: Path,
    moving_t1: Path | None,
    output_path: Path,
    logger: logging.Logger,
) -> None:
    """Resample tensor to the SimNIBS T1 grid with correct orientation.

    1. Cross-correlation alignment (ACPC ↔ SimNIBS coords differ)
    2. Resample each component onto the T1 grid
    3. Rotate tensors to pre-compensate for SimNIBS ``correct_FSL``
    """
    import nibabel as nib
    from nibabel.processing import resample_from_to

    # ── Load T1 (our target grid) ────────────────────────────────────
    t1_img = nib.load(str(fixed_t1))
    target_shape = t1_img.shape[:3]
    target_affine = t1_img.affine
    logger.info(f"Target grid: {target_shape} (SimNIBS T1)")

    # ── Cross-correlation alignment ──────────────────────────────────
    # ACPC and SimNIBS world coordinates can differ by ~50 mm.
    # Use 3D cross-correlation between the two T1s (or tensor vs T1
    # as fallback) to find the exact translation.
    if moving_t1 is not None and moving_t1.exists():
        shift = _find_alignment(moving_t1, fixed_t1, logger)
    else:
        logger.warning(
            "QSIPrep T1 not found — saving intermediate for manual alignment"
        )
        shift = np.zeros(3)

    aligned_affine = tensor_affine.copy()
    aligned_affine[:3, 3] += shift

    # ── Resample each component to T1 grid ───────────────────────────
    logger.info("Resampling tensor components...")
    resampled = np.zeros((*target_shape, 6), dtype=np.float32)
    for i in range(6):
        comp = nib.Nifti1Image(tensor_data[..., i], aligned_affine)
        resampled[..., i] = resample_from_to(
            comp, (target_shape, target_affine)
        ).get_fdata(dtype=np.float32)

    # ── Tensor reorientation (FSL convention pre-compensation) ───────
    R_src = _rotation_from_affine(tensor_affine)
    R_tgt = _rotation_from_affine(target_affine)
    M_fsl = R_tgt.copy()
    if np.linalg.det(R_tgt) > 0:
        M_fsl[:, 0] *= -1
    R_fix = (M_fsl.T @ R_src).astype(np.float32)

    logger.info("Rotating tensors for FSL convention...")
    mask = np.any(resampled != 0, axis=-1)
    vox = resampled[mask]  # (N, 6)

    T = np.zeros((vox.shape[0], 3, 3), dtype=np.float32)
    T[:, 0, 0] = vox[:, 0]
    T[:, 0, 1] = T[:, 1, 0] = vox[:, 1]
    T[:, 0, 2] = T[:, 2, 0] = vox[:, 2]
    T[:, 1, 1] = vox[:, 3]
    T[:, 1, 2] = T[:, 2, 1] = vox[:, 4]
    T[:, 2, 2] = vox[:, 5]

    Tr = np.einsum("ij,njk,lk->nil", R_fix, T, R_fix)
    vox[:, 0] = Tr[:, 0, 0]
    vox[:, 1] = Tr[:, 0, 1]
    vox[:, 2] = Tr[:, 0, 2]
    vox[:, 3] = Tr[:, 1, 1]
    vox[:, 4] = Tr[:, 1, 2]
    vox[:, 5] = Tr[:, 2, 2]
    resampled[mask] = vox

    # ── Save ─────────────────────────────────────────────────────────
    logger.info(f"Saving registered tensor ({resampled.shape})...")
    _save_nifti_gz(resampled, target_affine, output_path, logger)
    logger.info(f"Registered tensor saved to {output_path}")


# ── Public API ───────────────────────────────────────────────────────────


def extract_dti_tensor(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
    skip_registration: bool = False,
) -> Path:
    """Extract DTI tensor from QSIRecon DSI Studio output for SimNIBS.

    Returns path to ``DTI_coregT1_tensor.nii.gz`` in the m2m directory.
    """
    project = Path(project_dir)
    logger.info(f"Extracting DTI tensor for subject {subject_id}")

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

    # Load and validate
    tensor_data, affine = _load_tensor(dwi_dir, subject_id, logger)
    _validate_tensor(tensor_data, logger)

    # Save intermediate in ACPC space
    intermediate = m2m_dir / "DTI_ACPC_tensor.nii.gz"
    _save_nifti_gz(tensor_data, affine, intermediate, logger)
    logger.info(f"Intermediate tensor: {intermediate}")

    # Register to SimNIBS T1 space
    if skip_registration:
        shutil.copy2(intermediate, output_path)
        logger.info("Copied tensor as-is (skip_registration=True)")
    else:
        acpc_t1 = _qsiprep_t1(project, subject_id)
        _register_tensor(tensor_data, affine, simnibs_t1, acpc_t1, output_path, logger)

    logger.info(f"DTI tensor saved to: {output_path}")

    # QC report
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
