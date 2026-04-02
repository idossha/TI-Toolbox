#!/usr/bin/env python3
"""
DTI registration diagnostic — run inside the SimNIBS container.

Usage:
    python -m tit.pre.qsi.debug_dti /mnt/<project> <subject_id>

Prints affines, orientations, centers of mass, overlap stats, and
eigenvalue/eigenvector sanity checks so we can diagnose alignment
and orientation issues remotely.
"""

import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.ndimage import center_of_mass


def _orientation_str(affine):
    """Return orientation code string like 'RAS' or 'LPS'."""
    return "".join(nib.aff2axcodes(affine))


def _print_affine(name, img):
    aff = img.affine
    print(f"\n{'=' * 60}")
    print(f"{name}")
    print(f"  Shape:       {img.shape[:3]}")
    print(f"  Voxel size:  {np.round(np.abs(np.diag(aff[:3,:3])), 3).tolist()} mm")
    print(f"  Orientation: {_orientation_str(aff)}")
    print(f"  Affine:")
    for row in aff:
        print(f"    [{row[0]:10.4f} {row[1]:10.4f} {row[2]:10.4f} {row[3]:10.4f}]")


def _brain_com(data, affine, label, thresh_pct=30):
    """Compute center of mass in world coordinates."""
    if data.ndim == 4:
        mask = np.any(data != 0, axis=-1)
    else:
        nonzero = data[data > 0]
        if nonzero.size == 0:
            print(f"  {label}: ALL ZEROS — cannot compute COM")
            return None
        thresh = np.percentile(nonzero, thresh_pct)
        mask = data > thresh

    n_vox = int(mask.sum())
    com_vox = np.array(center_of_mass(mask))
    com_world = nib.affines.apply_affine(affine, com_vox)
    print(f"  {label}:")
    print(f"    Mask voxels: {n_vox}")
    print(f"    COM (voxel): [{com_vox[0]:.1f}, {com_vox[1]:.1f}, {com_vox[2]:.1f}]")
    print(
        f"    COM (world): [{com_world[0]:.1f}, {com_world[1]:.1f}, {com_world[2]:.1f}]"
    )
    return com_world


def _check_overlap(tensor_data, t1_data, label):
    """Check how many non-zero tensor voxels overlap with T1 brain."""
    tensor_mask = np.any(tensor_data != 0, axis=-1)
    nonzero_t1 = t1_data[t1_data > 0]
    if nonzero_t1.size == 0:
        print(f"  {label}: T1 is all zeros")
        return
    t1_mask = t1_data > np.percentile(nonzero_t1, 30)
    overlap = tensor_mask & t1_mask
    tensor_count = int(tensor_mask.sum())
    t1_count = int(t1_mask.sum())
    overlap_count = int(overlap.sum())
    if tensor_count > 0:
        pct = 100.0 * overlap_count / tensor_count
    else:
        pct = 0.0
    print(f"  {label}:")
    print(f"    Tensor non-zero: {tensor_count}")
    print(f"    T1 brain:        {t1_count}")
    print(f"    Overlap:         {overlap_count} ({pct:.1f}% of tensor)")


def _check_eigenvectors(tensor_data, affine, label):
    """Sample a few voxels and show principal eigenvector direction."""
    mask = np.any(tensor_data != 0, axis=-1)
    voxels = tensor_data[mask]
    if voxels.shape[0] == 0:
        print(f"  {label}: no data")
        return

    # Sample up to 1000 voxels with highest trace (likely WM)
    trace = voxels[:, 0] + voxels[:, 3] + voxels[:, 5]
    top_idx = np.argsort(trace)[-min(1000, len(trace)) :]
    sample = voxels[top_idx]

    T = np.zeros((sample.shape[0], 3, 3), dtype=np.float32)
    T[:, 0, 0] = sample[:, 0]
    T[:, 0, 1] = T[:, 1, 0] = sample[:, 1]
    T[:, 0, 2] = T[:, 2, 0] = sample[:, 2]
    T[:, 1, 1] = sample[:, 3]
    T[:, 1, 2] = T[:, 2, 1] = sample[:, 4]
    T[:, 2, 2] = sample[:, 5]

    eigenvalues, eigenvectors = np.linalg.eigh(T)
    v1 = eigenvectors[:, :, -1]  # principal direction
    fa_vals = _compute_fa(eigenvalues)

    # Average absolute principal direction (weighted by FA)
    weights = fa_vals[:, np.newaxis]
    avg_dir = np.abs(v1 * weights).mean(axis=0)
    avg_dir /= np.linalg.norm(avg_dir) + 1e-10

    dominant = ["x (L-R)", "y (A-P)", "z (S-I)"][np.argmax(avg_dir)]

    print(f"  {label} (top-trace WM voxels):")
    print(
        f"    Mean |V1| (FA-weighted): [{avg_dir[0]:.3f}, {avg_dir[1]:.3f}, {avg_dir[2]:.3f}]"
    )
    print(f"    Dominant axis: {dominant}")
    print(f"    FA: mean={fa_vals.mean():.3f}, max={fa_vals.max():.3f}")


def _compute_fa(eigenvalues):
    lam_mean = eigenvalues.mean(axis=-1, keepdims=True)
    lam_sq_sum = np.sum(eigenvalues**2, axis=-1)
    lam_diff_sq_sum = np.sum((eigenvalues - lam_mean) ** 2, axis=-1)
    denom = lam_sq_sum.copy()
    denom[denom == 0] = 1.0
    fa = np.sqrt(1.5) * np.sqrt(lam_diff_sq_sum) / np.sqrt(denom)
    return np.clip(fa, 0.0, 1.0)


def main():
    if len(sys.argv) < 3:
        print(f"Usage: python -m tit.pre.qsi.debug_dti <project_dir> <subject_id>")
        sys.exit(1)

    project_dir = Path(sys.argv[1])
    subject_id = sys.argv[2]

    m2m_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / f"m2m_{subject_id}"
    )
    t1_path = m2m_dir / "T1.nii.gz"
    registered_path = m2m_dir / "DTI_coregT1_tensor.nii.gz"
    intermediate_path = m2m_dir / "DTI_ACPC_tensor.nii.gz"

    dsi_dir = (
        project_dir
        / "derivatives"
        / "qsirecon"
        / "derivatives"
        / "qsirecon-DSIStudio"
        / f"sub-{subject_id}"
        / "dwi"
    )
    acpc_t1_path = (
        project_dir
        / "derivatives"
        / "qsiprep"
        / f"sub-{subject_id}"
        / "anat"
        / f"sub-{subject_id}_space-ACPC_desc-preproc_T1w.nii.gz"
    )

    print("=" * 60)
    print("DTI REGISTRATION DIAGNOSTIC")
    print("=" * 60)

    # 1. Print all affines
    if t1_path.exists():
        t1_img = nib.load(str(t1_path))
        _print_affine("SimNIBS T1", t1_img)
    else:
        print(f"\nSimNIBS T1 NOT FOUND: {t1_path}")
        sys.exit(1)

    if intermediate_path.exists():
        acpc_img = nib.load(str(intermediate_path))
        _print_affine("ACPC tensor (intermediate)", acpc_img)
    else:
        print(f"\nACPC tensor NOT FOUND: {intermediate_path}")

    if registered_path.exists():
        reg_img = nib.load(str(registered_path))
        _print_affine("Registered tensor (final)", reg_img)
    else:
        print(f"\nRegistered tensor NOT FOUND: {registered_path}")

    if acpc_t1_path.exists():
        acpc_t1_img = nib.load(str(acpc_t1_path))
        _print_affine("QSIPrep ACPC T1", acpc_t1_img)

    # Load a single source component for reference
    src_files = list(
        dsi_dir.glob(f"sub-{subject_id}_space-ACPC_model-tensor_param-txx_dwimap.nii*")
    )
    if src_files:
        src_img = nib.load(str(src_files[0]))
        _print_affine("Source tensor component (txx)", src_img)

    # 2. Centers of mass
    print(f"\n{'=' * 60}")
    print("CENTERS OF MASS (world coordinates)")
    t1_com = _brain_com(t1_img.get_fdata(dtype=np.float32), t1_img.affine, "SimNIBS T1")

    if intermediate_path.exists():
        acpc_com = _brain_com(
            acpc_img.get_fdata(dtype=np.float32), acpc_img.affine, "ACPC tensor"
        )
        if t1_com is not None and acpc_com is not None:
            diff = t1_com - acpc_com
            print(f"  Shift needed: [{diff[0]:.1f}, {diff[1]:.1f}, {diff[2]:.1f}] mm")
            print(f"  Distance: {np.linalg.norm(diff):.1f} mm")

    # 3. Overlap check
    if registered_path.exists():
        print(f"\n{'=' * 60}")
        print("OVERLAP CHECK")
        reg_data = reg_img.get_fdata(dtype=np.float32)
        t1_data = t1_img.get_fdata(dtype=np.float32)

        if reg_data.shape[:3] == t1_data.shape[:3]:
            _check_overlap(reg_data, t1_data, "Registered tensor vs T1 (same grid)")
        else:
            print(
                f"  Shape mismatch: tensor={reg_data.shape[:3]}, T1={t1_data.shape[:3]}"
            )

    # 4. Eigenvector check
    if registered_path.exists():
        print(f"\n{'=' * 60}")
        print("EIGENVECTOR CHECK (stored tensor, pre-FSL-compensation)")
        _check_eigenvectors(reg_data, reg_img.affine, "Registered tensor")

        # Also check what SimNIBS would see after correct_FSL
        print(f"\n{'=' * 60}")
        print("EIGENVECTOR CHECK (after simulated correct_FSL = world space)")
        aff = reg_img.affine
        M = aff[:3, :3] / np.linalg.norm(aff[:3, :3], axis=0)[:, None]
        R = np.eye(3)
        if np.linalg.det(M) > 0:
            R[0, 0] = -1
        M_fsl = M.dot(R)

        # Rotate the stored tensor to world space
        mask = np.any(reg_data != 0, axis=-1)
        vox = reg_data[mask].copy()
        T = np.zeros((vox.shape[0], 3, 3), dtype=np.float32)
        T[:, 0, 0] = vox[:, 0]
        T[:, 0, 1] = T[:, 1, 0] = vox[:, 1]
        T[:, 0, 2] = T[:, 2, 0] = vox[:, 2]
        T[:, 1, 1] = vox[:, 3]
        T[:, 1, 2] = T[:, 2, 1] = vox[:, 4]
        T[:, 2, 2] = vox[:, 5]

        M32 = M_fsl.astype(np.float32)
        T_world = np.einsum("ij,njk,lk->nil", M32, T, M32)

        world_data = np.zeros_like(reg_data)
        world_vox = np.zeros((vox.shape[0], 6), dtype=np.float32)
        world_vox[:, 0] = T_world[:, 0, 0]
        world_vox[:, 1] = T_world[:, 0, 1]
        world_vox[:, 2] = T_world[:, 0, 2]
        world_vox[:, 3] = T_world[:, 1, 1]
        world_vox[:, 4] = T_world[:, 1, 2]
        world_vox[:, 5] = T_world[:, 2, 2]
        world_data[mask] = world_vox
        _check_eigenvectors(world_data, aff, "World-space tensor (after correct_FSL)")

    # 5. Compare FA: source vs registered (is our processing destroying FA?)
    if intermediate_path.exists() and registered_path.exists():
        print(f"\n{'=' * 60}")
        print("FA COMPARISON: SOURCE vs REGISTERED")

        acpc_data = acpc_img.get_fdata(dtype=np.float32)
        acpc_mask = np.any(acpc_data != 0, axis=-1)
        acpc_vox = acpc_data[acpc_mask]

        T_acpc = np.zeros((acpc_vox.shape[0], 3, 3), dtype=np.float32)
        T_acpc[:, 0, 0] = acpc_vox[:, 0]
        T_acpc[:, 0, 1] = T_acpc[:, 1, 0] = acpc_vox[:, 1]
        T_acpc[:, 0, 2] = T_acpc[:, 2, 0] = acpc_vox[:, 2]
        T_acpc[:, 1, 1] = acpc_vox[:, 3]
        T_acpc[:, 1, 2] = T_acpc[:, 2, 1] = acpc_vox[:, 4]
        T_acpc[:, 2, 2] = acpc_vox[:, 5]

        evals_acpc = np.linalg.eigvalsh(T_acpc)
        fa_acpc = _compute_fa(evals_acpc)

        reg_mask2 = np.any(reg_data != 0, axis=-1)
        reg_vox = reg_data[reg_mask2]

        T_reg = np.zeros((reg_vox.shape[0], 3, 3), dtype=np.float32)
        T_reg[:, 0, 0] = reg_vox[:, 0]
        T_reg[:, 0, 1] = T_reg[:, 1, 0] = reg_vox[:, 1]
        T_reg[:, 0, 2] = T_reg[:, 2, 0] = reg_vox[:, 2]
        T_reg[:, 1, 1] = reg_vox[:, 3]
        T_reg[:, 1, 2] = T_reg[:, 2, 1] = reg_vox[:, 4]
        T_reg[:, 2, 2] = reg_vox[:, 5]

        evals_reg = np.linalg.eigvalsh(T_reg)
        fa_reg = _compute_fa(evals_reg)

        # Also print raw tensor component ranges
        print(f"  ACPC tensor (source, 2mm):")
        print(
            f"    FA: mean={fa_acpc.mean():.4f}, median={np.median(fa_acpc):.4f}, "
            f"max={fa_acpc.max():.4f}, p95={np.percentile(fa_acpc, 95):.4f}"
        )
        print(
            f"    Eigenvalues: min={evals_acpc.min():.6f}, max={evals_acpc.max():.6f}"
        )
        print(f"    Component ranges:")
        for i, name in enumerate(["Dxx", "Dxy", "Dxz", "Dyy", "Dyz", "Dzz"]):
            vals = acpc_vox[:, i]
            print(
                f"      {name}: [{vals.min():.6f}, {vals.max():.6f}], mean={vals.mean():.6f}"
            )

        print(f"  Registered tensor (0.5mm, after resampling+rotation):")
        print(
            f"    FA: mean={fa_reg.mean():.4f}, median={np.median(fa_reg):.4f}, "
            f"max={fa_reg.max():.4f}, p95={np.percentile(fa_reg, 95):.4f}"
        )
        print(f"    Eigenvalues: min={evals_reg.min():.6f}, max={evals_reg.max():.6f}")

    print(f"\n{'=' * 60}")
    print("DONE")


if __name__ == "__main__":
    main()
