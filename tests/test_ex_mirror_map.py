"""``build_electrode_mirror_map`` pairs true left/right mirrors on real caps.

What this pins (2026-10-22, package p05 "mirror-map-real-caps"): subject-space caps sit in the
scanner frame -- the head is off-centre and slightly rotated -- so the map cannot reflect about
``x = 0``. The audit measured on Dataset 000: ernie EEG10-10 Fz->F1 with no electrode mapped to
itself, sub-101 TP9->TP10 but TP10->P9, BioSemi-64 P4->P1.

Where the expected values come from (never from ``tit``):

* a synthetic 10-10-like cap built symmetric by construction, then shifted (x -8 mm,
  y +12 mm) and rotated;
* for real 10-10/10-20 caps, the electrode nomenclature: an odd number mirrors the next even
  number with the same prefix (F3<->F4, TP9<->TP10, AFp9h<->AFp10h) and a ``z`` electrode is its
  own mirror. Old and new names that share one position (T3 = T7 in the extended SPM12 cap) are
  compared by position;
* for the bundled 2-D GSN-256 template, its midline column: twelve electrodes within 3.5 px of
  x = 928 (the most common x), the next electrode 28 px away. The audit's "2 % of head width"
  (30 px) would swallow the lateral pair E009/E186 (both 29 px from the midline), so the midline
  band used here is 0.5 % of the width.

* for subject-space GSN-HydroCel caps (labels without a side), geometry only: one plane of the
  test's own, fitted to the map's pairs, must reflect every electrode onto its partner;
* for the opposite-side rule, two synthetic same-side electrodes with no mirror, which must stay
  unpaired rather than be matched to each other.

Real-data leg: ``TIT_DATASET_000=/path/to/000 pytest tests/test_ex_mirror_map.py``; read-only.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from tit.opt.ex.buckets import _read_eeg_positions, build_electrode_mirror_map
from tit.opt.ex.logic import _electrode_combinations
from tit.opt.ex.symmetry import symmetric_pair_options

REPO = Path(__file__).resolve().parents[1]


def nomenclature_mirror(label: str) -> str | None:
    if label.lower().endswith("z"):
        return label
    m = re.fullmatch(r"([A-Za-z]+?)(\d+)(h?)", label)
    if not m:
        return None
    n = int(m.group(2))
    return f"{m.group(1)}{n + 1 if n % 2 else n - 1}{m.group(3)}"


def _synthetic_cap() -> dict[str, tuple[float, float, float]]:
    """A dome of 10-10-like rows, mirror-symmetric about x = 0 by construction."""
    rows = {
        "Fp": 85,
        "AF": 65,
        "F": 42,
        "FC": 20,
        "C": 0,
        "CP": -20,
        "P": -42,
        "PO": -65,
    }
    cap = {}
    for prefix, y in rows.items():
        cap[f"{prefix}z"] = (0.0, float(y), math.sqrt(95**2 - y**2))
        for k in range(1, 5 if abs(y) < 60 else 3):
            x = 17.0 * k
            z = math.sqrt(max(95**2 - x**2 - y**2, 1.0))
            cap[f"{prefix}{2 * k - 1}"] = (-x, float(y), z)
            cap[f"{prefix}{2 * k}"] = (x, float(y), z)
    return cap


def _move(cap, shift=(-8.0, 12.0, 0.0), yaw_deg=0.0, pitch_deg=0.0):
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    rz = np.array(
        [
            [math.cos(yaw), -math.sin(yaw), 0],
            [math.sin(yaw), math.cos(yaw), 0],
            [0, 0, 1],
        ]
    )
    rx = np.array(
        [
            [1, 0, 0],
            [0, math.cos(pitch), -math.sin(pitch)],
            [0, math.sin(pitch), math.cos(pitch)],
        ]
    )
    return {k: tuple(rx @ rz @ np.array(v) + np.array(shift)) for k, v in cap.items()}


def _write(path: Path, cap) -> Path:
    path.write_text(
        "".join(f"Electrode,{x},{y},{z},{label}\n" for label, (x, y, z) in cap.items())
    )
    return path


@pytest.mark.parametrize(
    "yaw,pitch",
    [(0.0, 0.0), (4.0, 0.0), (-3.0, 6.0)],
    ids=["shift", "yaw", "yaw+pitch"],
)
def test_shifted_rotated_synthetic_cap_mirrors_by_name(tmp_path, yaw, pitch):
    cap = _move(_synthetic_cap(), yaw_deg=yaw, pitch_deg=pitch)
    mirror = build_electrode_mirror_map(_write(tmp_path / "cap.csv", cap))
    expected = {label: nomenclature_mirror(label) for label in cap}
    assert mirror == expected


def test_an_electrode_without_a_mirror_is_left_out_not_self_mapped(tmp_path):
    cap = _move(_synthetic_cap())
    cap["X9"] = (cap["C7"][0] - 9.0, cap["C7"][1] + 1.0, cap["C7"][2] - 6.0)
    mirror = build_electrode_mirror_map(_write(tmp_path / "cap.csv", cap))
    assert mirror.get("X9") != "X9"
    assert all(mirror[mirror[k]] == k for k in mirror)
    assert {k for k, v in mirror.items() if k == v} == {
        k for k in cap if k.endswith("z")
    }


def test_two_same_side_orphans_are_not_each_others_mirror(tmp_path):
    # Two extra electrodes left of the midline, 5 mm apart and ~10 mm off it (too far to be
    # midline electrodes), with nothing on the right: neither has a mirror, and the nearest
    # thing to a partner each has is the other one -- on the same side.
    base = _synthetic_cap()
    base["X1"] = (-9.0, 30.0, math.sqrt(95**2 - 9.0**2 - 30.0**2))
    base["X3"] = (-12.0, 34.0, math.sqrt(95**2 - 12.0**2 - 34.0**2))
    cap = _move(base, yaw_deg=4.0)
    mirror = build_electrode_mirror_map(_write(tmp_path / "cap.csv", cap))
    assert "X1" not in mirror and "X3" not in mirror
    assert mirror == {
        label: nomenclature_mirror(label) for label in cap if label not in {"X1", "X3"}
    }


def test_bundled_gsn_template_midline_and_involution():
    path = REPO / "resources" / "amv" / "GSN-256.csv"
    positions = _read_eeg_positions(path)
    xs = [p[0] for p in positions.values()]
    midline_x = Counter(xs).most_common(1)[0][0]
    band = 0.005 * (max(xs) - min(xs))
    midline = {k for k, p in positions.items() if abs(p[0] - midline_x) <= band}
    assert len(midline) == 12  # the template's midline column (E008 ... E147)
    mirror = build_electrode_mirror_map(path)
    assert {k for k, v in mirror.items() if k == v} == midline
    lateral = [k for k in mirror if k not in midline]
    assert (
        len(lateral) >= len(positions) - len(midline) - 1
    )  # 243 lateral, odd: one unpaired
    assert all(mirror[mirror[k]] == k for k in lateral)
    assert all(
        (positions[k][0] - midline_x) * (positions[mirror[k]][0] - midline_x) < 0
        for k in lateral
    )
    assert mirror["E186"] == "E009"


# ── Dataset 000 (read-only) ─────────────────────────────────────────────────────────

_DATASET = os.environ.get("TIT_DATASET_000", "")
_SIMNIBS = Path(_DATASET) / "derivatives" / "SimNIBS"
_PATTERNS = ("EEG10-10_*.csv", "BioSemi-64-10-10.csv", "EEG10-20_*.csv")


def _real_caps() -> list[Path]:
    if not _DATASET or not _SIMNIBS.is_dir():
        return []
    return sorted(
        p
        for pattern in _PATTERNS
        for p in _SIMNIBS.glob(f"sub-*/m2m_*/eeg_positions/{pattern}")
    )


_CAPS = _real_caps()
_needs_data = pytest.mark.skipif(
    not _CAPS,
    reason="skipping: TIT_DATASET_000 unset or has no m2m_*/eeg_positions caps",
)


def _collapsed_pairs(positions) -> int:
    pts = np.array(list(positions.values()), dtype=float)
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    return int((np.triu(d < 1.0, 1)).sum())


@_needs_data
@pytest.mark.parametrize(
    "cap", _CAPS, ids=[str(p.relative_to(_SIMNIBS)) for p in _CAPS] or None
)
def test_real_cap_mirrors_follow_the_nomenclature(cap):
    before = cap.stat().st_mtime_ns
    positions = _read_eeg_positions(cap)
    if _collapsed_pairs(positions) > 8:
        pytest.skip(
            "skipping: stale cap with many electrodes at one position (collapsed net); "
            "refusing such nets is the net-sanity package's job"
        )
    mirror = build_electrode_mirror_map(cap)
    assert all(mirror[mirror[k]] == k for k in mirror), "map is not an involution"
    named = {k: nomenclature_mirror(k) for k in positions}
    named = {k: v for k, v in named.items() if v in positions}
    assert len(named) >= 0.9 * len(positions), "has nomenclature to check"
    for label in named:
        if label.lower().endswith("z"):
            assert mirror.get(label) == label, label
    wrong = [
        k
        for k, want in named.items()
        if k not in mirror or positions[mirror[k]] != positions[want]
    ]
    if "extended_SPM12" in cap.name:
        # 346 positions with 10-5 half steps 5-10 mm apart: measured 0-8 mismatches per subject,
        # all in the inferior temporal / mastoid rows (TP10<->TPP9, M2<->A1).
        assert len(wrong) <= 0.03 * len(named), wrong
    else:
        assert wrong == []
    assert cap.stat().st_mtime_ns == before


def _gsn_caps() -> list[Path]:
    if not _DATASET or not _SIMNIBS.is_dir():
        return []
    return sorted(_SIMNIBS.glob("sub-*/m2m_*/eeg_positions/GSN-HydroCel-*.csv"))


_GSN = _gsn_caps()


@pytest.mark.skipif(
    not _GSN, reason="skipping: TIT_DATASET_000 unset or has no GSN-HydroCel caps"
)
@pytest.mark.parametrize(
    "cap", _GSN, ids=[str(p.relative_to(_SIMNIBS)) for p in _GSN] or None
)
def test_real_gsn_hydrocel_cap_mirrors_across_one_plane(cap):
    # GSN-HydroCel labels (E1..E256) carry no left/right meaning, so the check is geometric and
    # uses a plane of its own, not tit's: normal = mean direction of the mapped pairs'
    # difference vectors, through the mean of their midpoints. One plane must then explain the
    # whole map -- each electrode's image across it is nearest to its partner, within half the
    # cap's median neighbour gap (measured 2026-10-22 on the 10 healthy caps: <= 0.48 gap).
    before = cap.stat().st_mtime_ns
    positions = _read_eeg_positions(cap)
    if _collapsed_pairs(positions) > 8:
        pytest.skip(
            "skipping: stale cap with many electrodes at one position (collapsed net); "
            "refusing such nets is the net-sanity package's job"
        )
    labels = list(positions)
    points = np.array([positions[k] for k in labels], dtype=float)
    gaps = np.sqrt(((points[:, None, :] - points[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(gaps, np.inf)
    median_gap = float(np.median(gaps.min(axis=1)))

    mirror = build_electrode_mirror_map(cap)
    # HydroCel nets are laid out bilaterally symmetric: every electrode has a mirror.
    assert set(mirror) == set(labels)
    assert all(mirror[mirror[k]] == k for k in mirror), "map is not an involution"
    lateral = [k for k in labels if mirror[k] != k]
    assert len(lateral) >= 0.9 * len(labels), "has lateral pairs to check"

    diffs = np.array([np.subtract(positions[k], positions[mirror[k]]) for k in lateral])
    diffs[diffs @ diffs[0] < 0] *= -1
    normal = diffs.sum(axis=0) / np.linalg.norm(diffs.sum(axis=0))
    centre = np.mean(
        [np.add(positions[k], positions[mirror[k]]) / 2 for k in labels], axis=0
    )
    side = {k: float((np.asarray(positions[k]) - centre) @ normal) for k in labels}
    assert all(side[k] * side[mirror[k]] < 0 for k in lateral), "same-side pair"
    for k in labels:
        image = np.asarray(positions[k]) - 2 * side[k] * normal
        distance = np.linalg.norm(points - image, axis=1)
        assert labels[int(distance.argmin())] == mirror[k], k
        assert distance[labels.index(mirror[k])] <= 0.5 * median_gap, k
    assert cap.stat().st_mtime_ns == before


@_needs_data
def test_symmetric_within_pairs_search_on_the_real_ernie_cap(tmp_path):
    cap = _SIMNIBS / "sub-ernie/m2m_ernie/eeg_positions/EEG10-10_UI_Jurak_2007.csv"
    if not cap.is_file():
        pytest.skip("skipping: sub-ernie EEG10-10_UI_Jurak_2007.csv absent")
    mirror = build_electrode_mirror_map(cap)
    assert set(symmetric_pair_options(["F3", "F7"], ["F4", "F8"], mirror)) == {
        ("F3", "F4"),
        ("F7", "F8"),
    }
    quads = _electrode_combinations(
        ["F3", "F7", "Fz"],
        ["F4", "F8", "F1"],
        ["P3", "P7"],
        ["P4", "P8"],
        False,
        symmetry_mirror_map=mirror,
    )
    assert set(quads) == {
        ("F3", "F4", "P3", "P4"),
        ("F3", "F4", "P7", "P8"),
        ("F7", "F8", "P3", "P4"),
        ("F7", "F8", "P7", "P8"),
    }
