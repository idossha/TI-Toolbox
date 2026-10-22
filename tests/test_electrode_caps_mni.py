"""Every shipped EEG cap in resources/ElectrodeCaps_MNI is in MNI space.

Pins (2026-10-16): charm warps these coordinates from MNI to the subject, so a cap in another
frame lands off the head (four Brainstorm caps had x/y swapped and sat ~50 mm high; 43 GSN-128
electrodes collapsed onto one scalp point). Bounds are authored from MNI anatomy, not from the
files: the scalp spans about +-110 mm in z, the head is left/right symmetric about x = 0, and
Cz is near SimNIBS's EEG10-10_UI_Jurak_2007 Cz (0.0, -8.2, 97.3) mm.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
import pytest

CAPS = sorted(
    (Path(__file__).parents[1] / "resources" / "ElectrodeCaps_MNI").glob("*.csv")
)


def test_has_caps_to_check():
    assert len(CAPS) >= 4


@pytest.mark.parametrize("cap", CAPS, ids=lambda p: p.name)
def test_cap_is_in_mni_scalp_range(cap):
    with cap.open() as f:
        pos = {
            r[4]: np.array(r[1:4], float)
            for r in csv.reader(f)
            if r and r[0].endswith("Electrode")
        }
    xyz = np.array(list(pos.values()))
    assert np.all(np.abs(xyz[:, 2]) <= 110), (xyz[:, 2].min(), xyz[:, 2].max())
    assert abs(xyz[:, 0].mean()) < 5
    if "Cz" in pos:
        assert np.linalg.norm(pos["Cz"] - (0.0, -10.0, 100.0)) < 15


# EGI's own 10-10 equivalents (Luu & Ferree, EGI technical note, rev. 10/24/05, Tables 1-2,
# https://www.egi.com/images/HydroCelGSN_10-10.pdf), transcribed to tests/data. The 10-10 sites
# are SimNIBS's EEG10-10_UI_Jurak_2007 as stored in tit/scene/guide-mni (<= 1.2 mm from the
# SimNIBS MNI file). Bounds come from the GSN-256 control, which was never in the wrong frame:
# median 10.3 mm, max 27.8 mm (T9); EGI reports the 128's sensors up to ~2.5 cm of arc from their
# 10-10 site versus ~1.3 cm on the 256, so 40 mm / median 20 mm leaves the 128 its coarser grid.
# The previous GSN-128 file sat 137 mm (median) from these sites.
EGI_TABLE = Path(__file__).parent / "data" / "egi_hydrocel_10-10.csv"
JURAK = (
    Path(__file__).parents[1]
    / "tit"
    / "scene"
    / "guide-mni"
    / "nets"
    / "EEG10-10_UI_Jurak_2007.csv.json"
)


@pytest.mark.parametrize("net", ["128", "256"])
def test_egi_10_10_sensors_sit_on_their_10_10_site(net):
    import json

    sites = {
        e["name"]: np.array(e["world"])
        for e in json.loads(JURAK.read_text())["electrodes"]
    }
    cap = CAPS[0].parent / f"GSN-HydroCel-{net}.csv"
    with cap.open() as f:
        pos = {
            r[4]: np.array(r[1:4], float)
            for r in csv.reader(f)
            if r and r[0] == "Electrode"
        }
    with EGI_TABLE.open() as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r["net"] == net and r["first_listing"] == "1"
        ]
    dist = {
        r["ten_ten_label"]: float(
            np.linalg.norm(
                pos[f"E{int(r['egi_sensor']):03d}"] - sites[r["ten_ten_label"]]
            )
        )
        for r in rows
        if r["egi_sensor"]
        and r["ten_ten_label"]
        in sites  # Cz is the reference sensor, absent from the caps
    }
    assert len(dist) >= 60
    assert max(dist.values()) < 40, max(dist.items(), key=lambda kv: kv[1])
    assert np.median(list(dist.values())) < 20


# ── Anatomy of each shipped cap (2026-10-22, package p13, task shipped-cap-anatomy) ──────────
#
# The checks above pass a left/right-mirrored cap (|mean x| and Cz only). These are hand-derived
# from anatomy and the nets' own naming, not from the files:
# * real EEG nets space electrodes >= 9 mm apart (measured 13.1-24 mm across the six caps), so a
#   smaller nearest-neighbour distance is a collapsed or duplicated sensor;
# * MNI is RAS: the left preauricular point (LPA) has x < 0 < RPA x, the nasion y > 0 > inion y;
# * 10-10 names carry their side: an odd number is left (x < 0), an even one right, a "z" the
#   midline (BioSemi-64-10-10);
# * the BioSemi ABC layout starts at the vertex: A1 is within 15 mm of Cz (0, -10, 100);
# * a net named for its sensor count has that many Electrode rows.


def _rows(cap: Path) -> list[list[str]]:
    with cap.open(newline="") as f:
        return [r for r in csv.reader(f) if r]


@pytest.mark.parametrize("cap", CAPS, ids=lambda p: p.name)
def test_cap_labels_are_unique_and_never_collapse(cap):
    rows = [r for r in _rows(cap) if r[0] == "Electrode"]
    labels = [r[4] for r in rows]
    assert len(labels) == len(set(labels))
    xyz = np.array([r[1:4] for r in rows], float)
    gaps = np.sqrt(((xyz[:, None, :] - xyz[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(gaps, np.inf)
    assert gaps.min() >= 9.0, labels[int(np.argmin(gaps.min(axis=1)))]


@pytest.mark.parametrize("cap", CAPS, ids=lambda p: p.name)
def test_cap_fiducials_are_on_their_anatomical_side(cap):
    fid = {r[4]: np.array(r[1:4], float) for r in _rows(cap) if r[0] == "Fiducial"}
    assert set(fid) == {"LPA", "RPA", "Nz", "Iz"}
    assert fid["LPA"][0] < 0 < fid["RPA"][0]
    assert fid["Nz"][1] > 0 > fid["Iz"][1]


def test_biosemi_64_follows_10_10_sides():
    rows = [
        r for r in _rows(CAPS[0].parent / "BioSemi-64-10-10.csv") if r[0] == "Electrode"
    ]
    checked = 0
    for _, x, _, _, label in rows:
        x = float(x)
        number = re.search(r"(\d+)$", label)
        if label.lower().endswith("z"):
            assert abs(x) < 10, label
        elif number and int(number.group(1)) % 2:
            assert x < -5, label
        elif number:
            assert x > 5, label
        else:
            continue
        checked += 1
    assert checked == len(rows) == 64


@pytest.mark.parametrize("net", ["BioSemi-128-A1", "BioSemi-256-A1"])
def test_biosemi_abc_layout_starts_at_the_vertex(net):
    a1 = [
        r
        for r in _rows(CAPS[0].parent / f"{net}.csv")
        if r[0] == "Electrode" and r[4] == "A1"
    ]
    assert len(a1) == 1
    assert np.linalg.norm(np.array(a1[0][1:4], float) - (0.0, -10.0, 100.0)) < 15


@pytest.mark.parametrize(
    "net,count",
    [
        ("BioSemi-64-10-10", 64),
        ("BioSemi-128-A1", 128),
        ("BioSemi-256-A1", 256),
        ("GSN-HydroCel-128", 128),
        ("GSN-HydroCel-256", 256),
    ],
)
def test_net_has_the_electrode_count_in_its_name(net, count):
    rows = _rows(CAPS[0].parent / f"{net}.csv")
    assert sum(r[0] == "Electrode" for r in rows) == count
