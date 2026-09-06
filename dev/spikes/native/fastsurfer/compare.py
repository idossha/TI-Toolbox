#!/usr/bin/env python3
"""Compare FastSurfer --seg_only DKT output against real FreeSurfer recon-all
and against SimNIBS charm's labeling.nii.gz, on sub-ernie.

Uses only nibabel + numpy (no scipy/nilearn), per the N0.2 spike brief --
this is itself a spike for the `mri_convert --reslice_like` replacement
skeptic-2 flagged as risky (tkreg/scanner-RAS, conform order-of-operations).

Outputs a single Markdown report fragment to stdout (redirect to a file).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import nibabel as nib
import numpy as np

# ---------------------------------------------------------------------------
# Paths (real data, this machine)
# ---------------------------------------------------------------------------

DATASET = Path("/Users/idohaber/datasets/000")
FS_MRI = DATASET / "derivatives/freesurfer/sub-ernie/mri"
M2M = DATASET / "derivatives/SimNIBS/sub-ernie/m2m_ernie"
FASTSURFER_OUT = Path(
    "/private/tmp/claude-501/-Users-idohaber-01-production-TI-toolbox/"
    "2f1d440f-51f9-4340-bb8a-c347107a12b1/scratchpad/native/fastsurfer/out"
)

PATHS = {
    "fastsurfer": FASTSURFER_OUT / "sub-ernie/mri/aparc.DKTatlas+aseg.deep.mgz",
    "freesurfer": FS_MRI / "aparc.DKTatlas+aseg.mgz",
    "charm": M2M / "segmentation/labeling.nii.gz",
    # Sanity cross-check only: the analyzer's own pre-existing resample of
    # `freesurfer` onto the charm/native-T1w grid, produced by the *current*
    # `mri_convert --reslice_like` pipeline. Not used as ground truth --
    # used only to check our from-scratch nearest-neighbour resampler agrees
    # with the tool it would replace.
    "freesurfer_preresampled": FS_MRI
    / "aparc_DKTatlas+aseg_resampled_256x256x208_45dfa12d.nii.gz",
}

# ---------------------------------------------------------------------------
# Label sets (standard FreeSurferColorLUT numeric IDs -- charm's
# labeling_LUT.txt and FreeSurfer's own aseg/DKT LUT use the same numbers,
# verified by reading both files directly, see REPORT.md)
# ---------------------------------------------------------------------------

SUBCORTICAL = {
    10: "Left-Thalamus", 49: "Right-Thalamus",
    11: "Left-Caudate", 50: "Right-Caudate",
    12: "Left-Putamen", 51: "Right-Putamen",
    13: "Left-Pallidum", 52: "Right-Pallidum",
    17: "Left-Hippocampus", 53: "Right-Hippocampus",
    18: "Left-Amygdala", 54: "Right-Amygdala",
    26: "Left-Accumbens", 58: "Right-Accumbens",
}

CORTICAL_DKT = {
    1024: "ctx-lh-precentral", 2024: "ctx-rh-precentral",
    1022: "ctx-lh-postcentral", 2022: "ctx-rh-postcentral",
    1028: "ctx-lh-superiorfrontal", 2028: "ctx-rh-superiorfrontal",
    1035: "ctx-lh-insula", 2035: "ctx-rh-insula",
    1008: "ctx-lh-inferiorparietal", 2008: "ctx-rh-inferiorparietal",
    1030: "ctx-lh-superiortemporal", 2030: "ctx-rh-superiortemporal",
    1025: "ctx-lh-precuneus", 2025: "ctx-rh-precuneus",
    1011: "ctx-lh-lateraloccipital", 2011: "ctx-rh-lateraloccipital",
    1029: "ctx-lh-superiorparietal", 2029: "ctx-rh-superiorparietal",
    1018: "ctx-lh-parsopercularis", 2018: "ctx-rh-parsopercularis",
}


# ---------------------------------------------------------------------------
# Core numeric utilities -- nibabel + numpy only
# ---------------------------------------------------------------------------


def load(path: Path):
    img = nib.load(str(path))
    data = np.asarray(img.get_fdata()).astype(np.int32)
    return data, img.affine.astype(np.float64), img.shape


def affines_close(a: np.ndarray, b: np.ndarray, atol: float = 1e-2) -> bool:
    return bool(np.allclose(a, b, atol=atol))


def voxel_volume_mm3(affine: np.ndarray) -> float:
    """|det| of the 3x3 linear part = mm^3 per voxel for this grid."""
    return float(abs(np.linalg.det(affine[:3, :3])))


def resample_nn(
    src_data: np.ndarray,
    src_affine: np.ndarray,
    target_shape: tuple[int, int, int],
    target_affine: np.ndarray,
) -> np.ndarray:
    """Nearest-neighbour resample of a label volume onto a new grid.

    Pure affine-matrix math: for each target voxel, its world (scanner RAS)
    coordinate is target_affine @ [i,j,k,1]; the corresponding source voxel
    is inv(src_affine) @ world, rounded to nearest integer. This is what
    `mri_convert --reslice_like` does for label volumes (nearest-neighbour
    interpolation) modulo FreeSurfer's own internal RAS bookkeeping -- see
    REPORT.md "reslice_like replacement" section for the validation against
    a real mri_convert output.
    """
    inv_src = np.linalg.inv(src_affine)
    m = inv_src @ target_affine  # target-voxel -> source-voxel, 4x4

    nx, ny, nz = target_shape
    ii, jj, kk = np.meshgrid(
        np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij"
    )
    ones = np.ones_like(ii, dtype=np.float64)
    target_ijk1 = np.stack(
        [ii.astype(np.float64), jj.astype(np.float64), kk.astype(np.float64), ones],
        axis=0,
    ).reshape(4, -1)

    src_ijk1 = m @ target_ijk1
    src_idx = np.rint(src_ijk1[:3]).astype(np.int64)

    sx, sy, sz = src_data.shape
    valid = (
        (src_idx[0] >= 0) & (src_idx[0] < sx)
        & (src_idx[1] >= 0) & (src_idx[1] < sy)
        & (src_idx[2] >= 0) & (src_idx[2] < sz)
    )

    out = np.zeros(nx * ny * nz, dtype=src_data.dtype)
    flat_idx = np.zeros_like(valid, dtype=np.int64)
    flat_idx[valid] = np.ravel_multi_index(
        (src_idx[0][valid], src_idx[1][valid], src_idx[2][valid]), src_data.shape
    )
    out[valid] = src_data.reshape(-1)[flat_idx[valid]]
    return out.reshape(target_shape)


def dice(a: np.ndarray, b: np.ndarray, label: int) -> tuple[float, int, int, int]:
    am = a == label
    bm = b == label
    inter = int(np.count_nonzero(am & bm))
    na = int(np.count_nonzero(am))
    nb = int(np.count_nonzero(bm))
    if na + nb == 0:
        return float("nan"), na, nb, inter
    return 2.0 * inter / (na + nb), na, nb, inter


def centroid_world(data: np.ndarray, affine: np.ndarray, label: int) -> np.ndarray | None:
    idx = np.argwhere(data == label)
    if idx.size == 0:
        return None
    centroid_vox = idx.mean(axis=0)  # (i,j,k)
    world = affine @ np.array([*centroid_vox, 1.0])
    return world[:3]


def centroid_distance_mm(
    data_a: np.ndarray, affine_a: np.ndarray,
    data_b: np.ndarray, affine_b: np.ndarray,
    label: int,
) -> float | None:
    ca = centroid_world(data_a, affine_a, label)
    cb = centroid_world(data_b, affine_b, label)
    if ca is None or cb is None:
        return None
    return float(np.linalg.norm(ca - cb))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    t0 = time.time()
    print("# FastSurfer vs FreeSurfer vs charm -- label comparison (sub-ernie)\n")

    for name, p in PATHS.items():
        print(f"- `{name}`: `{p}`  exists={p.exists()}")
    print()

    if not PATHS["fastsurfer"].exists():
        print("FastSurfer output not found -- aborting comparison.", file=sys.stderr)
        return 1

    fs_data, fs_aff, fs_shape = load(PATHS["freesurfer"])
    fastsurfer_data, fastsurfer_aff, fastsurfer_shape = load(PATHS["fastsurfer"])
    charm_data, charm_aff, charm_shape = load(PATHS["charm"])

    print("## 1. Grid / affine check\n")
    print("| Source | Shape | Affine (flattened) |")
    print("|---|---|---|")
    for name, (d, a, s) in {
        "freesurfer (real recon-all)": (fs_data, fs_aff, fs_shape),
        "fastsurfer (--seg_only)": (fastsurfer_data, fastsurfer_aff, fastsurfer_shape),
        "charm (labeling.nii.gz)": (charm_data, charm_aff, charm_shape),
    }.items():
        flat = " ".join(f"{x:.3f}" for x in a[:3].flatten())
        print(f"| {name} | {s} | `{flat}` |")
    print()

    same_conform_grid = fs_shape == fastsurfer_shape and affines_close(fs_aff, fastsurfer_aff)
    print(
        f"FreeSurfer-conform grid match (FastSurfer vs real recon-all): "
        f"**{same_conform_grid}**\n"
    )

    if same_conform_grid:
        fastsurfer_on_fs_grid = fastsurfer_data
    else:
        print(
            "Affines differ -- resampling FastSurfer output onto the real "
            "recon-all conform grid (nearest-neighbour via affine).\n"
        )
        fastsurfer_on_fs_grid = resample_nn(fastsurfer_data, fastsurfer_aff, fs_shape, fs_aff)

    # ---- Part A: FastSurfer vs real FreeSurfer, on the FS-conform grid ----
    print("## 2. FastSurfer vs real FreeSurfer recon-all (FreeSurfer-conform grid)\n")
    print("### 2a. Subcortical structures (Dice, volumes)\n")
    print(
        "| Structure | Dice | Vol FreeSurfer (mm3) | Vol FastSurfer (mm3) | "
        "%diff | Centroid dist (mm) |"
    )
    print("|---|---|---|---|---|---|")
    vv_fs = voxel_volume_mm3(fs_aff)
    for label, name in SUBCORTICAL.items():
        d, na, nb, inter = dice(fs_data, fastsurfer_on_fs_grid, label)
        vol_a = na * vv_fs
        vol_b = nb * vv_fs
        pdiff = (vol_b - vol_a) / vol_a * 100 if vol_a else float("nan")
        cdist = centroid_distance_mm(fs_data, fs_aff, fastsurfer_data, fastsurfer_aff, label)
        cdist_s = f"{cdist:.2f}" if cdist is not None else "n/a"
        print(f"| {name} | {d:.3f} | {vol_a:.0f} | {vol_b:.0f} | {pdiff:+.1f}% | {cdist_s} |")
    print()

    print("### 2b. Cortical DKT labels (Dice, volumes)\n")
    print(
        "| Region | Dice | Vol FreeSurfer (mm3) | Vol FastSurfer (mm3) | "
        "%diff | Centroid dist (mm) |"
    )
    print("|---|---|---|---|---|---|")
    for label, name in CORTICAL_DKT.items():
        d, na, nb, inter = dice(fs_data, fastsurfer_on_fs_grid, label)
        vol_a = na * vv_fs
        vol_b = nb * vv_fs
        pdiff = (vol_b - vol_a) / vol_a * 100 if vol_a else float("nan")
        cdist = centroid_distance_mm(fs_data, fs_aff, fastsurfer_data, fastsurfer_aff, label)
        cdist_s = f"{cdist:.2f}" if cdist is not None else "n/a"
        print(f"| {name} | {d:.3f} | {vol_a:.0f} | {vol_b:.0f} | {pdiff:+.1f}% | {cdist_s} |")
    print()

    dices_sub = [dice(fs_data, fastsurfer_on_fs_grid, l)[0] for l in SUBCORTICAL]
    dices_ctx = [dice(fs_data, fastsurfer_on_fs_grid, l)[0] for l in CORTICAL_DKT]
    print(f"Mean subcortical Dice (FastSurfer vs real FreeSurfer): {np.nanmean(dices_sub):.3f}")
    print(f"Mean cortical Dice (FastSurfer vs real FreeSurfer): {np.nanmean(dices_ctx):.3f}\n")

    # ---- Part B: subcortical, both tools vs charm's labeling.nii.gz -------
    print("## 3. Subcortical vs charm `labeling.nii.gz` (different grid, resampled)\n")

    t1 = time.time()
    fs_on_charm = resample_nn(fs_data, fs_aff, charm_shape, charm_aff)
    fastsurfer_on_charm = resample_nn(fastsurfer_data, fastsurfer_aff, charm_shape, charm_aff)
    print(f"(resampled both onto charm's {charm_shape} grid in {time.time()-t1:.2f}s)\n")

    # Cross-check: does our own resample agree with the pipeline's existing
    # `mri_convert --reslice_like`-produced file for the same source/target?
    if PATHS["freesurfer_preresampled"].exists():
        preres_data, preres_aff, preres_shape = load(PATHS["freesurfer_preresampled"])
        agree_shape = preres_shape == charm_shape and affines_close(preres_aff, charm_aff)
        if agree_shape:
            match = float(np.mean(fs_on_charm == preres_data))
            print(
                f"**Cross-check**: our nearest-neighbour resample of real FreeSurfer's "
                f"aparc.DKTatlas+aseg onto the charm grid agrees with the pipeline's own "
                f"pre-existing `mri_convert --reslice_like` output at "
                f"**{match*100:.2f}%** of voxels (grid: {preres_shape}).\n"
            )
        else:
            print(
                "Cross-check skipped: pre-existing resampled file grid does not match "
                f"charm grid (shape={preres_shape}, affine_match={affines_close(preres_aff, charm_aff)}).\n"
            )

    vv_charm = voxel_volume_mm3(charm_aff)
    print(
        "| Structure | Dice(FastSurfer,charm) | Dice(FreeSurfer,charm) | "
        "Vol charm (mm3) | Vol FreeSurfer (mm3) | Vol FastSurfer (mm3) | "
        "Centroid dist FS-charm (mm) | Centroid dist FreeSurfer-charm (mm) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for label, name in SUBCORTICAL.items():
        d_fsurf_charm, na1, nb1, _ = dice(fastsurfer_on_charm, charm_data, label)
        d_fs_charm, na2, nb2, _ = dice(fs_on_charm, charm_data, label)
        vol_charm = int(np.count_nonzero(charm_data == label)) * vv_charm
        vol_fastsurfer = na1 * vv_charm
        vol_freesurfer = na2 * vv_charm
        cd_fastsurfer = centroid_distance_mm(fastsurfer_data, fastsurfer_aff, charm_data, charm_aff, label)
        cd_freesurfer = centroid_distance_mm(fs_data, fs_aff, charm_data, charm_aff, label)
        cd_fastsurfer_s = f"{cd_fastsurfer:.2f}" if cd_fastsurfer is not None else "n/a"
        cd_freesurfer_s = f"{cd_freesurfer:.2f}" if cd_freesurfer is not None else "n/a"
        print(
            f"| {name} | {d_fsurf_charm:.3f} | {d_fs_charm:.3f} | {vol_charm:.0f} | "
            f"{vol_freesurfer:.0f} | {vol_fastsurfer:.0f} | {cd_fastsurfer_s} | {cd_freesurfer_s} |"
        )
    print()

    print(f"Total compare.py wall time: {time.time()-t0:.1f}s\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
