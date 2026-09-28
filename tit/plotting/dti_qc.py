"""Images for the DTI QC report: WebP bytes plus the label geometry the page needs.

Two figures: the registration flicker (T1w and FA mosaics with the same charm contours) and the
direction-encoded colour (DEC) stack with its orientation legend. Every panel follows
:mod:`tit.plotting.slices`: canonical RAS, neurological (subject left on image left), slices chosen
by MNI coordinate through charm's warp, cropped to the brain. DEC is ``|V1|`` in world RAS
(red L–R, green A–P, blue S–I) scaled by FA.
"""

from __future__ import annotations

import io

import numpy as np

from . import slices as sl

WM_COLOUR = "#ffd23f"
PIAL_COLOUR = "#4cc9f0"
DEC_GAIN = 1.6  # FA-weighted DEC is dark; this makes WM tracts read at report size
FA_DISPLAY_MAX = 0.85

#: MNI targets of every panel (mm). Registration mosaics are 3 x 2 per plane.
REG_PLANES = {
    "axial": (2, (-20, -4, 8, 20, 34, 50), "z"),
    "coronal": (1, (48, 28, 8, -12, -34, -62), "y"),
    "sagittal": (0, (-40, -24, -8, 8, 24, 40), "x"),
}
DEC_STACK_Z = tuple(range(-32, 66, 4))


def _coordinates(vols, pial: np.ndarray) -> tuple[np.ndarray, bool]:
    """Per-voxel MNI coordinates from charm's warp, else approximate ones (and ``False``)."""
    if vols.mni is not None:
        return vols.mni, True
    # ponytail: no charm warp -> world mm about the WM+GM centroid, moved to where a typical centroid
    # sits in MNI; captions then say "approximate". Use the warp when it matters.
    centre = (
        vols.affine[:3, :3] @ np.array(np.nonzero(pial)).mean(1) + vols.affine[:3, 3]
    )
    grid = np.indices(pial.shape, dtype=np.float32).reshape(3, -1)
    world = (
        (vols.affine[:3, :3] @ grid).T
        + vols.affine[:3, 3]
        - centre
        + np.array([0.0, -18.0, 18.0])
    )
    return world.reshape(pial.shape + (3,)).astype(np.float32), False


def render_all(vols) -> dict:
    """Every image of the DTI QC report from :class:`tit.pre.qsi.dti_advisories.DtiVolumes`."""
    from tit.pre.qsi import tensor_math as tm

    lab = vols.labels
    valid = vols.valid
    w, v = tm.eig_desc(tm.sym(vols.t6w[valid]))
    fa = np.clip(tm.fa_md(w)[0], 0, 1)
    fa_vol = np.zeros(lab.shape, np.float32)
    fa_vol[valid] = fa
    rgb = np.zeros(lab.shape + (3,), np.float32)
    rgb[valid] = np.abs(v[:, :, 0]) * fa[:, None]
    del w, v
    brain, wm, pial = np.isin(lab, (1, 2, 3)), lab == 1, np.isin(lab, (1, 2))
    csf_t1, wm_t1 = vols.t1[lab == 3], vols.t1[wm]
    lo = (
        float(np.percentile(csf_t1, 40))
        if csf_t1.size
        else float(np.percentile(vols.t1, 5))
    )
    hi = (
        float(np.percentile(wm_t1, 98))
        if wm_t1.size
        else float(np.percentile(vols.t1, 99))
    )
    t1n = np.clip((vols.t1 - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)
    coord, is_mni = _coordinates(vols, pial)
    box = sl.brain_box(brain, coord[..., 2])

    def pick(axis: int, target: float) -> int:
        return sl.pick_slice(axis, target, coord[..., axis], brain, box)

    registration = {}
    for plane, (axis, targets, letter) in REG_PLANES.items():
        idx = [pick(axis, t) for t in targets]

        def mosaic(vol, idx=idx, axis=axis):
            return sl.mosaic([sl.oriented(vol, axis, i, box) for i in idx], 3)

        t1_m, tile = mosaic(t1n)
        contours = [
            (mosaic(pial)[0], PIAL_COLOUR, 0.7),
            (mosaic(wm)[0], WM_COLOUR, 0.9),
        ]
        registration[plane] = {
            "t1": sl.render(t1_m, contours),
            "fa": sl.render(
                np.clip(mosaic(fa_vol)[0] / FA_DISPLAY_MAX, 0, 1), contours
            ),
            "labels": [f"{letter} = {t:+d}" for t in targets],
            "cols": 3,
            "tile": tile,
            "shape": t1_m.shape[:2],
        }
    frames = [
        sl.render(
            np.clip(sl.oriented(rgb, 2, pick(2, z), box) * DEC_GAIN, 0, 1), quality=80
        )
        for z in DEC_STACK_Z
    ]
    sphere, sphere_axes = orientation_sphere()
    return {
        "is_mni": is_mni,
        "registration": registration,
        "dec": {"z": list(DEC_STACK_Z), "frames": frames},
        "sphere": sphere,
        "sphere_axes": sphere_axes,
    }


def orientation_sphere(px: int = 220) -> tuple[bytes, dict[str, list[float]]]:
    """Shaded sphere coloured by ``|direction|`` (PNG with alpha) and the screen position of R, A, S."""
    from PIL import Image

    view = np.array([0.52, 0.62, 0.58])
    view /= np.linalg.norm(view)
    up = np.array([0.0, 0.0, 1.0]) - view[2] * view
    up /= np.linalg.norm(up)
    right = np.cross(up, view)
    u, v = np.meshgrid(np.linspace(-1, 1, px), np.linspace(1, -1, px))
    r2 = u**2 + v**2
    n = (
        u[..., None] * right
        + v[..., None] * up
        + np.sqrt(np.clip(1 - r2, 0, 1))[..., None] * view
    )
    light = np.array([0.35, 0.45, 0.82])
    light /= np.linalg.norm(light)
    lam = np.clip(n @ (0.6 * light + 0.4 * view), 0, 1)
    col = np.abs(n) * (0.35 + 0.65 * lam[..., None])
    col = (
        col
        / np.maximum(col.max(-1, keepdims=True), 1e-6)
        * (0.45 + 0.55 * lam[..., None])
    )
    alpha = np.clip((1 - np.sqrt(r2)) * px / 2, 0, 1) * (r2 <= 1)
    buf = io.BytesIO()
    Image.fromarray(
        (np.dstack([np.clip(col, 0, 1), alpha]) * 255).astype(np.uint8), "RGBA"
    ).save(buf, "PNG", optimize=True)
    axes = {
        name: [float(e @ right), float(e @ up)] for name, e in zip("RAS", np.eye(3))
    }
    return buf.getvalue(), axes
