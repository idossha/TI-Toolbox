"""Every shipped EEG cap in resources/ElectrodeCaps_MNI is in MNI space.

Pins (2026-10-16): charm warps these coordinates from MNI to the subject, so a cap in another
frame lands off the head (four Brainstorm caps had x/y swapped and sat ~50 mm high; 43 GSN-128
electrodes collapsed onto one scalp point). Bounds are authored from MNI anatomy, not from the
files: the scalp spans about +-110 mm in z, the head is left/right symmetric about x = 0, and
Cz is near SimNIBS's EEG10-10_UI_Jurak_2007 Cz (0.0, -8.2, 97.3) mm.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

CAPS = sorted((Path(__file__).parents[1] / "resources" / "ElectrodeCaps_MNI").glob("*.csv"))


def test_has_caps_to_check():
    assert len(CAPS) >= 4


@pytest.mark.parametrize("cap", CAPS, ids=lambda p: p.name)
def test_cap_is_in_mni_scalp_range(cap):
    with cap.open() as f:
        pos = {r[4]: np.array(r[1:4], float) for r in csv.reader(f) if r and r[0].endswith("Electrode")}
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
JURAK = Path(__file__).parents[1] / "tit" / "scene" / "guide-mni" / "nets" / "EEG10-10_UI_Jurak_2007.csv.json"


@pytest.mark.parametrize("net", ["128", "256"])
def test_egi_10_10_sensors_sit_on_their_10_10_site(net):
    import json

    sites = {e["name"]: np.array(e["world"]) for e in json.loads(JURAK.read_text())["electrodes"]}
    cap = CAPS[0].parent / f"GSN-HydroCel-{net}.csv"
    with cap.open() as f:
        pos = {r[4]: np.array(r[1:4], float) for r in csv.reader(f) if r and r[0] == "Electrode"}
    with EGI_TABLE.open() as f:
        rows = [r for r in csv.DictReader(f) if r["net"] == net and r["first_listing"] == "1"]
    dist = {
        r["ten_ten_label"]: float(np.linalg.norm(pos[f"E{int(r['egi_sensor']):03d}"] - sites[r["ten_ten_label"]]))
        for r in rows
        if r["egi_sensor"] and r["ten_ten_label"] in sites  # Cz is the reference sensor, absent from the caps
    }
    assert len(dist) >= 60
    assert max(dist.values()) < 40, max(dist.items(), key=lambda kv: kv[1])
    assert np.median(list(dist.values())) < 20
