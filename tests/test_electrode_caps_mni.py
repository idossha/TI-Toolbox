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
