"""Helpers for reusable exhaustive-search electrode buckets.

Ported from collaborator Larissa Albantakis's branch
``alba/ex-search-multipolar`` and generalized: the loader/saver/normalizer
accept an arbitrary ordered bucket-key list instead of a hard-coded 4-key
scheme, so both 2-pair (:data:`BUCKET_KEYS`) and 4-pair
(:data:`tit.opt.mex.logic.MEX_BUCKET_KEYS`) bucket files share the same
JSON/CSV/TSV round-trip.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np

BUCKET_KEYS = ("e1_plus", "e1_minus", "e2_plus", "e2_minus")

BUCKET_ALIASES = {
    "e1_plus": "e1_plus",
    "e1+": "e1_plus",
    "e1plus": "e1_plus",
    "e1 plus": "e1_plus",
    "e1_minus": "e1_minus",
    "e1-": "e1_minus",
    "e1_": "e1_minus",
    "e1minus": "e1_minus",
    "e1 minus": "e1_minus",
    "e2_plus": "e2_plus",
    "e2+": "e2_plus",
    "e2plus": "e2_plus",
    "e2 plus": "e2_plus",
    "e2_minus": "e2_minus",
    "e2-": "e2_minus",
    "e2_": "e2_minus",
    "e2minus": "e2_minus",
    "e2 minus": "e2_minus",
}

QUADRANT_BUCKET_LABELS = {
    "e1_plus": "left anterior",
    "e1_minus": "right anterior",
    "e2_plus": "left posterior",
    "e2_minus": "right posterior",
}

_RESOURCE_DIR = Path(__file__).resolve().parents[3] / "resources" / "amv"
_CANONICAL_TEMPLATE_COORD_FILES = {
    "GSN-HydroCel-185.csv": "GSN-256.csv",
    "GSN-HydroCel-256.csv": "GSN-256.csv",
    "GSN-HydroCel-185": "GSN-256.csv",
    "GSN-HydroCel-256": "GSN-256.csv",
    "GSN-256.csv": "GSN-256.csv",
    "GSN-256": "GSN-256.csv",
}


def _generate_aliases(keys: Sequence[str]) -> dict[str, str]:
    """Derive alias variants (``e3+``, ``e3 plus``, ...) for arbitrary bucket keys.

    Used for any *keys* sequence other than the default :data:`BUCKET_KEYS`,
    whose hand-curated aliases are :data:`BUCKET_ALIASES` instead. Only keys
    shaped like ``e<n>_plus``/``e<n>_minus`` get alias variants; other key
    shapes map only to themselves.
    """
    aliases: dict[str, str] = {}
    for key in keys:
        aliases[key] = key
        match = re.match(r"^e(\d+)_(plus|minus)$", key)
        if not match:
            continue
        n, sign = match.groups()
        symbol = "+" if sign == "plus" else "-"
        raw_symbol = f"e{n}{symbol}"
        # _normalize_bucket_key replaces "-" with "_" before the alias lookup
        # runs, so "e3-" arrives as "e3_" by the time it is looked up; include
        # both the raw and the dash-normalized form so the lookup can't miss.
        variants = {
            raw_symbol,
            raw_symbol.replace("-", "_"),
            f"e{n}{sign}",
            f"e{n} {sign}",
        }
        for variant in variants:
            aliases[variant] = key
    return aliases


def _aliases_for(keys: Sequence[str]) -> dict[str, str]:
    """Return the alias table for *keys* (curated for the default, derived otherwise)."""
    return BUCKET_ALIASES if tuple(keys) == BUCKET_KEYS else _generate_aliases(keys)


def _normalize_bucket_key(key: str, aliases: dict[str, str]) -> str:
    normalized = key.strip().lower().replace("-", "_")
    normalized = " ".join(normalized.split())
    return aliases.get(normalized, normalized)


def _split_electrodes(value) -> list[str]:
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    else:
        parts = list(value)
    return [str(e).strip() for e in parts if str(e).strip()]


def normalize_buckets(
    raw: dict, keys: Sequence[str] = BUCKET_KEYS
) -> dict[str, list[str]]:
    """Normalize a bucket mapping to canonical bucket keys.

    ``keys`` defaults to the four 2-pair ex-search bucket keys
    (:data:`BUCKET_KEYS`); pass the eight m-ex-search keys
    (:data:`tit.opt.mex.logic.MEX_BUCKET_KEYS`) to normalize a 4-pair
    (8-electrode) bucket mapping through the same function.
    """
    aliases = _aliases_for(keys)
    buckets = {key: [] for key in keys}
    for key, value in raw.items():
        bucket_key = _normalize_bucket_key(str(key), aliases)
        if bucket_key in buckets:
            buckets[bucket_key] = _split_electrodes(value)
    return buckets


def _bucket_json_payload(data: dict) -> dict:
    """Return the bucket-shaped payload from a bucket file or full config."""
    electrodes = data.get("electrodes")
    if isinstance(electrodes, dict):
        nested = dict(electrodes)
        nested.pop("_type", None)
        return nested
    return data


def load_bucket_file(
    path: str | Path, keys: Sequence[str] = BUCKET_KEYS
) -> dict[str, list[str]]:
    """Load bucket definitions from JSON, CSV, or TSV.

    JSON may use canonical keys (``e1_plus``) or GUI-style keys
    (``E1+``). Full ex-search/m-ex-search config JSON files with nested
    ``electrodes`` are also accepted. CSV/TSV files should have one row
    per bucket, with the bucket name in the first column and electrodes
    in the remaining columns or as a comma/semicolon separated second
    column. ``keys`` selects the bucket scheme -- the four 2-pair keys by
    default, or an arbitrary key list (e.g. the eight m-ex-search keys)
    for other electrode-position counts.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Bucket JSON must contain an object")
        return normalize_buckets(_bucket_json_payload(data), keys)

    delimiter = "\t" if suffix == ".tsv" else ","
    aliases = _aliases_for(keys)
    rows = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if not row or not row[0].strip() or row[0].strip().startswith("#"):
                continue
            bucket_key = _normalize_bucket_key(row[0], aliases)
            if bucket_key not in keys:
                continue
            if len(row) == 2:
                rows[bucket_key] = _split_electrodes(row[1])
            else:
                rows[bucket_key] = _split_electrodes(row[1:])
    return normalize_buckets(rows, keys)


def save_bucket_file(
    path: str | Path,
    buckets: dict[str, list[str]],
    keys: Sequence[str] = BUCKET_KEYS,
) -> None:
    """Save bucket definitions as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalize_buckets(buckets, keys), f, indent=2)
        f.write("\n")


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


def build_quadrant_buckets(eeg_csv_path: str | Path) -> dict[str, list[str]]:
    """Split an EEG-position CSV into four RAS quadrants.

    Mapping: ``E1+`` = left anterior, ``E1-`` = right anterior,
    ``E2+`` = left posterior, ``E2-`` = right posterior.
    """
    buckets = {key: [] for key in BUCKET_KEYS}
    for label, coords in _read_eeg_positions(eeg_csv_path).items():
        x, y = coords[:2]
        if x < 0 and y >= 0:
            buckets["e1_plus"].append(label)
        elif x >= 0 and y >= 0:
            buckets["e1_minus"].append(label)
        elif x < 0 and y < 0:
            buckets["e2_plus"].append(label)
        else:
            buckets["e2_minus"].append(label)

    return {key: sorted(values) for key, values in buckets.items()}
