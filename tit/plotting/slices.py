"""Slice figures that every report shares: one orientation convention, slices chosen by anatomy.

Convention (stated in every caption that uses it):

* volumes are reordered to the closest canonical **RAS** voxel order first (:func:`canonical`),
  whatever the grid on disk (ernie's m2m grid is PSR, CHN's is RAS);
* panels are **neurological**: subject left on image left, superior up; anterior up in axial
  panels and to the right in sagittal panels;
* slices are picked by coordinate, normally MNI through charm's ``Conform2MNI_nonl`` warp, and
  never where the brain is (nearly) absent, so a mosaic has no empty panels;
* panels are never cropped: each shows its whole slice of the volume, framed by a black margin of
  :data:`MARGIN` voxels (a brain-mask crop cut the scalp, and the brain where it reached the grid edge).

Rendering needs matplotlib and Pillow (WebP); everything else is numpy.
"""

from __future__ import annotations

import io

import numpy as np

#: Brain voxels a slice needs before it can be chosen; below this a panel reads as empty.
MIN_SLICE_VOXELS = 200
#: Black voxels framing every mosaic panel, so the head never touches a panel edge.
MARGIN = 8


def canonical(data: np.ndarray, affine: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reorder the first three axes of *data* to the closest RAS voxel order.

    Only axis permutations and flips (``nibabel.as_closest_canonical``'s rule), so values are
    untouched; world-frame vectors and tensors stay valid. Extra trailing axes are kept.
    """
    from nibabel.orientations import apply_orientation, inv_ornt_aff, io_orientation

    ornt = io_orientation(affine)
    out = np.asarray(apply_orientation(data, ornt))
    return out, affine @ inv_ornt_aff(ornt, data.shape[:3])


def pick_slice(axis: int, target: float, coord: np.ndarray, mask: np.ndarray) -> int:
    """Index along *axis* whose *mask* voxels' mean *coord* is closest to *target*.

    *coord* is one coordinate component per voxel (e.g. MNI y for a coronal slice). Slices with
    fewer than :data:`MIN_SLICE_VOXELS` mask voxels are never chosen.
    """
    best, best_i = np.inf, None
    for i in range(mask.shape[axis]):
        sl = [slice(None)] * 3
        sl[axis] = i
        m = mask[tuple(sl)]
        if m.sum() < MIN_SLICE_VOXELS:
            continue
        d = abs(float(coord[tuple(sl)][m].mean()) - target)
        if d < best:
            best, best_i = d, i
    if best_i is None:
        raise ValueError(
            f"no slice along axis {axis} holds {MIN_SLICE_VOXELS} mask voxels"
        )
    return best_i


def oriented(vol: np.ndarray, axis: int, i: int) -> np.ndarray:
    """The whole 2-D slice (rows top to bottom) of RAS *vol* at index *i* along *axis*, neurological.

    Axial (axis 2): anterior up, left on the left. Coronal (1): superior up, left on the left.
    Sagittal (0): superior up, anterior on the right. Trailing channel axes are kept.
    """
    return np.rot90(np.take(vol, i, axis=axis))


def mosaic(
    tiles: list[np.ndarray], cols: int, gap: int = 4, margin: int = MARGIN
) -> tuple[np.ndarray, tuple[int, int]]:
    """Tiles on a grid, centred in equal cells at least *margin* larger on every side; returns
    ``(image, (cell_h, cell_w))``."""
    h = max(t.shape[0] for t in tiles) + 2 * margin
    w = max(t.shape[1] for t in tiles) + 2 * margin
    rows = -(-len(tiles) // cols)
    out = np.zeros(
        (rows * h + (rows - 1) * gap, cols * w + (cols - 1) * gap) + tiles[0].shape[2:],
        dtype=tiles[0].dtype,
    )
    for n, t in enumerate(tiles):
        r, c = divmod(n, cols)
        y, x = (
            r * (h + gap) + (h - t.shape[0]) // 2,
            c * (w + gap) + (w - t.shape[1]) // 2,
        )
        out[y : y + t.shape[0], x : x + t.shape[1]] = t
    return out, (h, w)


def overlay(
    grey: np.ndarray,
    field: np.ndarray,
    lo: float,
    hi: float,
    cmap: str = "inferno",
    alpha: float = 0.85,
) -> np.ndarray:
    """RGB panel: *grey* (0–1) under *field* coloured from *lo* to *hi*; voxels below *lo* stay grey."""
    import matplotlib

    colours = matplotlib.colormaps[cmap](np.clip((field - lo) / (hi - lo), 0, 1))[
        ..., :3
    ]
    a = np.where(field >= lo, alpha, 0.0)[..., None]
    return grey[..., None] * (1 - a) + colours * a


def colour_stops(cmap: str = "inferno", n: int = 9) -> list[str]:
    """*n* evenly spaced colours of *cmap* as hex, for a CSS colour bar matching :func:`overlay`."""
    import matplotlib

    return [
        matplotlib.colors.to_hex(matplotlib.colormaps[cmap](i / (n - 1)))
        for i in range(n)
    ]


def render(img: np.ndarray, contours=(), quality: int = 82) -> bytes:
    """Draw a grey (2-D) or RGB (H, W, 3) panel at 2 px per voxel, with outline contours, as WebP.

    *contours* are ``(mask, colour, line width)``; every outline is drawn on the same grid as the
    image.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    h, w = img.shape[:2]
    fig = plt.figure(figsize=(w * 2 / 100, h * 2 / 100), dpi=100, facecolor="black")
    try:
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("black")
        if img.ndim == 2:
            ax.imshow(img, cmap="gray", vmin=0, vmax=1, interpolation="bilinear")
        else:
            ax.imshow(np.clip(img, 0, 1), interpolation="bilinear")
        for mask, color, lw in contours:
            if mask.any():
                ax.contour(
                    mask.astype(float),
                    [0.5],
                    colors=[color],
                    linewidths=lw,
                    antialiased=True,
                )
        ax.set_xlim(-0.5, w - 0.5)
        ax.set_ylim(h - 0.5, -0.5)
        ax.axis("off")
        fig.canvas.draw()
        rgb = Image.fromarray(np.asarray(fig.canvas.buffer_rgba())).convert("RGB")
    finally:
        plt.close(fig)
    out = io.BytesIO()
    rgb.save(out, "WEBP", quality=quality, method=6)
    return out.getvalue()
