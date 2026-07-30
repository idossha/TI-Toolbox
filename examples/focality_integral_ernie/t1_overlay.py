"""T1 + TI-field + ROI-contour slice panels.

Adapted from an earlier prototype (`viz.py`): scatters a per-element TI field onto
the subject T1 voxel grid, then renders coronal/axial/sagittal slices centered on
the ROI with the field overlaid and the ROI drawn as a white contour.

Public API
----------
render_overlay_from_meshes(channel_meshes, center_mni, radius_mm, m2m_dir, out_png, title)
"""

from __future__ import annotations

import os

import numpy as np
import nibabel as nib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# Tissue tags kept when combining channels (mirrors tit/sim/TI.py).
_TAGS_KEEP = np.hstack([np.arange(1, 100), np.arange(1001, 1100)])

TI_CMAP = LinearSegmentedColormap.from_list(
    "ti", ["#00000000", "#1b2a6b", "#2e7ab8", "#4fbfa8", "#f2d857", "#f07d34", "#c2352b"]
)


def _field_to_nifti(vals, bary, ref_img):
    """Scatter per-element field onto the T1 grid (max within voxel, gap-filled)."""
    data = np.zeros(ref_img.shape, np.float32)
    cnt = np.zeros(ref_img.shape, np.float32)
    inv = np.linalg.inv(ref_img.affine)
    vx = np.rint((inv[:3, :3] @ bary.T).T + inv[:3, 3]).astype(int)
    ok = np.all((vx >= 0) & (vx < np.array(ref_img.shape)), axis=1)
    np.maximum.at(data, (vx[ok, 0], vx[ok, 1], vx[ok, 2]), vals[ok])
    np.add.at(cnt, (vx[ok, 0], vx[ok, 1], vx[ok, 2]), 1)
    from scipy.ndimage import grey_dilation

    filled = grey_dilation(data, size=(3, 3, 3))
    return nib.Nifti1Image(np.where(cnt > 0, data, filled), ref_img.affine)


def _sphere_roi_mask(center_mni, radius_mm, m2m_dir, ref_img):
    """Spherical ROI mask (+ its voxel centre) from an MNI centre and radius."""
    import simnibs

    c_sub = np.asarray(
        simnibs.mni2subject_coords([list(center_mni)], m2m_dir)
    ).reshape(3)
    inv = np.linalg.inv(ref_img.affine)
    c_vox = inv[:3, :3] @ c_sub + inv[:3, 3]
    vsize = np.linalg.norm(ref_img.affine[:3, :3], axis=0).mean()
    rad_vox = radius_mm / vsize
    zz, yy, xx = np.ogrid[: ref_img.shape[0], : ref_img.shape[1], : ref_img.shape[2]]
    d2 = (zz - c_vox[0]) ** 2 + (yy - c_vox[1]) ** 2 + (xx - c_vox[2]) ** 2
    mask = d2 <= rad_vox ** 2
    return mask, tuple(np.clip(np.round(c_vox), 0, np.array(ref_img.shape) - 1).astype(int))


def render_overlay_from_meshes(channel_meshes, center_mni, radius_mm, m2m_dir,
                               out_png, title, vmax=None):
    """Render T1 + TI field + white ROI contour from the two channel meshes."""
    paths = [p for p in (channel_meshes or []) if os.path.isfile(p)][:2]
    if len(paths) < 2:
        return False
    import simnibs
    from simnibs.utils import TI_utils

    m1 = simnibs.read_msh(paths[0]).crop_mesh(tags=_TAGS_KEEP)
    m2 = simnibs.read_msh(paths[1]).crop_mesh(tags=_TAGS_KEEP)
    ti = np.asarray(TI_utils.get_maxTI(m1.field["E"].value, m2.field["E"].value)).ravel()
    bary = m1.elements_baricenters().value

    # Restrict the rendered field to brain (WM/GM/CSF); scalp/muscle under the
    # electrodes carries a much higher field and would otherwise dominate vmax.
    brain = np.isin(m1.elm.tag1, [1, 2, 3])
    ti, bary = ti[brain], bary[brain]

    t1 = nib.load(os.path.join(m2m_dir, "T1.nii.gz"))
    t1d = np.asarray(t1.dataobj).astype(float)
    t1d = np.clip(t1d / (np.percentile(t1d, 99.0) or 1), 0, 1.0)
    field = np.asarray(_field_to_nifti(ti, bary, t1).dataobj)
    roi, (i0, j0, k0) = _sphere_roi_mask(center_mni, radius_mm, m2m_dir, t1)
    if vmax is None:
        vmax = float(np.percentile(ti, 99)) if ti.size else 1.0

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.4), facecolor="#0d0d0f")
    im = None
    for ax, (bg, md, rm, lab) in zip(axes, [
        (t1d[i0], field[i0], roi[i0], "coronal"),
        (t1d[:, j0], field[:, j0], roi[:, j0], "axial"),
        (t1d[:, :, k0], field[:, :, k0], roi[:, :, k0], "sagittal"),
    ]):
        ax.set_facecolor("#0d0d0f")
        ax.imshow(np.rot90(bg), cmap="gray", vmin=0.02, vmax=0.92, interpolation="bilinear")
        masked = np.ma.masked_where(np.rot90(md) <= vmax * 0.03, np.rot90(md))
        im = ax.imshow(masked, cmap=TI_CMAP, vmin=0, vmax=vmax, alpha=0.85,
                       interpolation="bilinear")
        ax.contour(np.rot90(rm).astype(float), levels=[0.5], colors="#ffffff",
                   linewidths=1.2, alpha=0.95)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(lab, color="#9aa0a6", fontsize=10, pad=5)
    cb = fig.colorbar(im, ax=axes, shrink=0.72, pad=0.01)
    cb.set_label("TI_max (V/m)", color="#e8eaed")
    cb.ax.yaxis.set_tick_params(color="#9aa0a6")
    plt.setp(plt.getp(cb.ax, "yticklabels"), color="#9aa0a6")
    fig.suptitle(f"{title}   (white contour = target ROI)", color="#e8eaed", fontsize=12)
    fig.savefig(out_png, dpi=130, facecolor="#0d0d0f", bbox_inches="tight")
    plt.close(fig)
    return True
