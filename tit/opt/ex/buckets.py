"""EEG-cap helpers for exhaustive search: electrode positions, the bundled 2-D
template coordinates of a known net, and each electrode's left/right mirror.

:func:`build_electrode_mirror_map` drives the symmetric bucket search
(:mod:`tit.opt.ex.symmetry`); :func:`_read_eeg_positions` also feeds the
ex-search cap figures (:mod:`tit.plotting.ti_metrics`).
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

_RESOURCE_DIR = Path(__file__).resolve().parents[3] / "resources" / "amv"
_CANONICAL_TEMPLATE_COORD_FILES = {
    "GSN-HydroCel-185.csv": "GSN-256.csv",
    "GSN-HydroCel-256.csv": "GSN-256.csv",
    "GSN-HydroCel-185": "GSN-256.csv",
    "GSN-HydroCel-256": "GSN-256.csv",
    "GSN-256.csv": "GSN-256.csv",
    "GSN-256": "GSN-256.csv",
}


def _read_eeg_positions(eeg_csv_path: str | Path) -> dict[str, tuple[float, ...]]:
    """Read electrode labels and positions from supported EEG CSV layouts."""
    positions: dict[str, tuple[float, ...]] = {}
    with open(eeg_csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            first = row[0].strip().lower()
            if first in {"electrode_name", "name", "label"}:
                try:
                    label = row[0].strip()
                    x = float(row[1])
                    y = float(row[2])
                    coords = (x, y)
                except ValueError:
                    continue
            elif first == "electrode" and len(row) >= 5:
                try:
                    label = row[4].strip()
                    x = float(row[1])
                    y = float(row[2])
                    z = float(row[3])
                    coords = (x, y, z)
                except ValueError:
                    continue
            elif len(row) >= 5:
                continue
            else:
                try:
                    label = row[0].strip()
                    x = float(row[1])
                    y = float(row[2])
                    coords = (x, y)
                    if len(row) >= 4:
                        coords = (x, y, float(row[3]))
                except ValueError:
                    continue
            if label:
                positions[label] = coords
    return positions


def canonical_template_coord_path(eeg_net_name: str | Path | None) -> Path | None:
    """Return a canonical 2D EEG-template coordinate file for known net names."""
    if not eeg_net_name:
        return None
    name = Path(str(eeg_net_name)).name
    coord_file = _CANONICAL_TEMPLATE_COORD_FILES.get(name)
    if coord_file is None:
        coord_file = _CANONICAL_TEMPLATE_COORD_FILES.get(Path(name).stem)
    if coord_file is None:
        return None
    path = _RESOURCE_DIR / coord_file
    return path if path.is_file() else None


def _squared_distances(a, b):
    return ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=-1)


def _midsagittal_plane(points):
    """Unit normal and offset of the plane a cap is left/right symmetric about.

    Subject-space caps sit in the scanner frame: the head is off-centre and
    turned a few degrees, so ``x = 0`` is not the midline. Starting from the
    x axis through the median x, each electrode is reflected and paired with
    the electrode nearest its image; the plane is refit through the midpoints of
    those pairs (a midline electrode is its own midpoint) until it settles.
    """
    dim = points.shape[1]
    normal = np.eye(dim)[0]
    offset = float(np.median(points[:, 0]))
    for _ in range(50):
        images = points - 2 * (points @ normal - offset)[:, None] * normal
        nearest = _squared_distances(images, points).argmin(axis=1)
        midpoints = (points + points[nearest]) / 2
        centre = midpoints.mean(axis=0)
        _, spread, axes = np.linalg.svd(midpoints - centre, full_matrices=False)
        new_normal = normal
        if len(spread) == dim and spread[dim - 2] > 1e-9 * max(spread[0], 1.0):
            # The midpoints span the plane: its normal is their least-spread axis.
            new_normal = axes[-1] if axes[-1] @ normal >= 0 else -axes[-1]
        new_offset = float(centre @ new_normal)
        if np.allclose(new_normal, normal, atol=1e-12) and abs(
            new_offset - offset
        ) <= 1e-9 * max(abs(offset), 1.0):
            break
        normal, offset = new_normal, new_offset
    return normal, offset


def build_electrode_mirror_map(eeg_csv_path: str | Path) -> dict[str, str]:
    """Map each electrode to its left/right mirror in an EEG CSV.

    The mirror plane is estimated from the cap (:func:`_midsagittal_plane`),
    so off-centre and slightly rotated subject-space caps and 2-D templates in
    pixel units mirror correctly. Electrodes are then matched greedily, best
    first: a left/right pair costs the distance between one electrode's image
    and the other; a midline electrode (closer to the plane than half the gap to
    its nearest neighbour) may pair with itself at the cost of the distance to
    its own image. The map is therefore an involution; an electrode left
    without a partner on the other side is not in it. Downstream channel-pair
    validation still prevents self-pairs from being evaluated.
    """
    positions = _read_eeg_positions(eeg_csv_path)
    if not positions:
        raise ValueError(f"No electrode positions found in {eeg_csv_path}")

    labels = list(positions)
    points = np.array([positions[label] for label in labels], dtype=float)
    normal, offset = _midsagittal_plane(points)
    side = points @ normal - offset
    cost = _squared_distances(points - 2 * side[:, None] * normal, points)
    gaps = _squared_distances(points, points)
    np.fill_diagonal(gaps, np.inf)
    nearest_gap = np.sqrt(gaps.min(axis=1)) if len(labels) > 1 else [np.inf]

    candidates = [
        (cost[i, i], i, i)
        for i in range(len(labels))
        if 2 * abs(side[i]) < nearest_gap[i]
    ]
    candidates += [
        (cost[i, j], i, j)
        for i in range(len(labels))
        for j in range(i + 1, len(labels))
        if side[i] * side[j] < 0
    ]
    partner: dict[int, int] = {}
    for _, i, j in sorted(candidates):
        if i not in partner and j not in partner:
            partner[i] = j
            partner[j] = i
    return {labels[i]: labels[partner[i]] for i in range(len(labels)) if i in partner}
