"""The EEG nets packaged with the guide heads lie on that guide's skin and are distinct.

What this pins (2026-10-22, package p07, task guide-nets-on-guide-skin), from the committed
files only (no environment, no SimNIBS):

For each packaged guide (``tit/scene/guide`` = Ernie, ``tit/scene/guide-mni`` = MNI152) and
every net its manifest lists:

* the net file holds as many electrodes as the manifest says, in the manifest's space;
* every electrode is within 15 mm of the nearest vertex of the guide's own skin surface
  (``surfaces/skin.tvsc``, decoded with ``tit.scene.tvsc.decode``). 15 mm is the bound
  ``tests/test_scene_realdata.py`` uses for subject heads (a cap pad plus the skin mesh's
  vertex spacing); measured 2026-10-22 the worst guide electrode is 1.8 mm off, and a cap
  packaged in the wrong frame (the 3.1.1 MNI cap bug) sits tens of millimetres off;
* no two electrodes are closer than 2 mm, except the 10-20 synonyms T3/T7, T4/T8, T5/P7,
  T6/P8 (Oostenveld & Praamstra 2001, Table 1, typed here), which SimNIBS's SPM12 cap
  places on one point by design. Measured: exactly those four pairs, in SPM12 only.

``tests/test_scene_guide.py`` checks names and digests; this file checks the geometry.

Reproduce: ``.venv/bin/python -m pytest tests/test_scene_guide_nets.py -q``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tit.scene import guide, tvsc

ON_SKIN_MM = 15.0
COLLAPSE_MM = 2.0
ALIASES = {
    frozenset(p) for p in (("T3", "T7"), ("T4", "T8"), ("T5", "P7"), ("T6", "P8"))
}


def _skin(root: Path, manifest: dict) -> np.ndarray:
    part = next(p for p in manifest["parts"] if p["id"] == "skin")
    blob = (root / part["files"]["tvsc"]).read_bytes()
    return np.asarray(tvsc.decode(blob).positions, dtype=np.float64)


def _nearest(points: np.ndarray, cloud: np.ndarray) -> np.ndarray:
    out = np.empty(len(points))
    for start in range(0, len(points), 64):
        chunk = points[start : start + 64]
        d = np.linalg.norm(chunk[:, None, :] - cloud[None, :, :], axis=-1)
        out[start : start + 64] = d.min(axis=1)
    return out


CASES = [
    (guide_id, net["name"])
    for guide_id, root in guide.GUIDE_DIRS.items()
    for net in json.loads((root / guide.MANIFEST_NAME).read_text())["nets"]
]


def test_every_guide_packages_nets() -> None:
    assert {g for g, _ in CASES} == set(guide.GUIDE_DIRS)
    assert len(CASES) >= 10, CASES


@pytest.fixture(scope="module")
def skins() -> dict[str, np.ndarray]:
    return {
        guide_id: _skin(root, json.loads((root / guide.MANIFEST_NAME).read_text()))
        for guide_id, root in guide.GUIDE_DIRS.items()
    }


@pytest.mark.parametrize("guide_id,net", CASES, ids=[f"{g}:{n}" for g, n in CASES])
def test_a_guide_net_sits_distinct_on_the_guide_skin(
    guide_id: str, net: str, skins: dict[str, np.ndarray]
) -> None:
    root = guide.GUIDE_DIRS[guide_id]
    manifest = json.loads((root / guide.MANIFEST_NAME).read_text())
    entry = next(n for n in manifest["nets"] if n["name"] == net)
    body = json.loads((root / entry["file"]).read_text())
    assert body["net"] == net
    assert body["space"] == manifest["space"]
    names = [e["name"] for e in body["electrodes"]]
    world = np.array([e["world"] for e in body["electrodes"]], dtype=np.float64)
    assert len(names) == entry["electrodes"]
    assert len(set(names)) == len(names), "a label is used twice"

    off = _nearest(world, skins[guide_id])
    worst = int(off.argmax())
    assert (
        off[worst] <= ON_SKIN_MM
    ), f"{names[worst]} is {off[worst]:.1f} mm off the skin"

    d = np.linalg.norm(world[:, None, :] - world[None, :, :], axis=-1)
    close = {
        frozenset((names[i], names[j]))
        for i, j in zip(*np.nonzero(np.triu(d < COLLAPSE_MM, k=1)))
    }
    assert close - ALIASES == set()
