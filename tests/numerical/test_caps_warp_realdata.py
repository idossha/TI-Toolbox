"""``tit.caps.warp_caps`` reproduces charm's own EEG positions on a real head (2026-10-16).

The reference is independent of the code under test: the ``eeg_positions/<cap>.csv`` that
**charm itself** wrote when it built the head model. Re-warping SimNIBS's MNI file for the
same cap onto the same ``m2m_<id>`` with :func:`tit.caps.warp_caps` must land on those
positions (same labels, same order, < 0.05 mm -- the two runs differ only in float
round-off; a wrong direction, skin tag or mesh crop moves electrodes by centimetres).
The warped net is then inspected with the real skin: no collapsed pairs, every electrode
on the scalp.

Gated on a real project, like ``tests/test_scene_realdata.py``::

    docker run --rm -v "$PWD":/ti-toolbox -v /path/to/000:/data:ro -w /ti-toolbox \\
      -e TIT_SCENE_TESTDATA=/data idossha/ti-toolbox:v3.1.0 \\
      simnibs_python -m pytest tests/numerical/test_caps_warp_realdata.py -q -s

Writes only under ``tmp_path``; the project may be mounted read-only. The host suite's
synthetic half (spacing, collapse, routes) is ``tests/test_caps.py``.

``test_tit_caps_land_on_their_mni_coordinates_on_mni152`` (p14, 2026-10-22) is gated on
``TIT_DATASET_000`` instead: it warps each cap TI-Toolbox ships -- caps charm never wrote
for any subject -- onto ``sub-MNI152``, whose head is the MNI152 template itself, so the
reference is the MNI file being warped (independent of charm): each electrode must land
where its MNI row meets the template's skin. It moves by the row's own distance to that
skin and no further. That distance is the cap's anatomy, not the warp's: the six caps'
rows sit a median 1.0-3.2 mm and at most 10.4 mm (GSN-HydroCel-185/256 E080, at the
vertex, inside the scalp) from sub-MNI152's skin nodes (container probe, 2026-10-22),
so a flat "within 10 mm of the MNI row" bound would fail on correct warps::

    docker run --rm --platform linux/amd64 --entrypoint bash -v "$PWD":/ti-toolbox \\
      -w /ti-toolbox -v /path/to/000:/data/000:ro -e TIT_DATASET_000=/data/000 \\
      idossha/ti-toolbox:v3.1.1 -lc \\
      'simnibs_python -m pytest tests/numerical/test_caps_warp_realdata.py -q -s'
"""

from __future__ import annotations

import csv
import importlib
import os
import sys
from pathlib import Path

import numpy as np
import pytest

CAP = "EEG10-10_UI_Jurak_2007.csv"
#: Two runs of the same warp differ by float round-off only.
SAME_POSITION_MM = 0.05
#: charm projects electrodes onto the skin surface; the nearest skin *node* can be up to
#: about one skin triangle edge away (~2-3 mm on charm's skin), never more.
ON_SCALP_MM = 3.0
#: sub-MNI152's head *is* the MNI152 template, so mni2subject is the identity up to
#: the template's registration onto itself, and an electrode moves only by the
#: projection onto the skin: its shift is at most its MNI row's distance to the
#: nearest skin node (the projection lands on the surface, which is no farther than
#: a node) plus that registration residual. Measured excess over the node distance:
#: at most 0.43 mm over the six caps (container probe, 2026-10-22); 1 mm bounds it
#: with margin. A wrong skin tag, frame or source file moves electrodes by centimetres.
WARP_RESIDUAL_MM = 1.0
_REPO_CAPS = Path(__file__).resolve().parents[2] / "resources" / "ElectrodeCaps_MNI"


@pytest.fixture(scope="module")
def simnibs_real():
    """``tit.caps`` with the real SimNIBS in place of the host suite's mock."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "simnibs"
    }
    try:
        importlib.import_module("simnibs.utils.transformations")
        importlib.import_module("simnibs.mesh_tools.mesh_io")
    except Exception:
        sys.modules.update(saved)
        print("skipping: real SimNIBS is unavailable")
        pytest.skip("real SimNIBS is unavailable; run in the toolbox container")
    from tit import caps

    yield caps
    for k in [k for k in sys.modules if k.split(".")[0] == "simnibs"]:
        del sys.modules[k]
    sys.modules.update(saved)


@pytest.fixture(scope="module")
def real(request):
    root = os.environ.get("TIT_SCENE_TESTDATA")
    if not root or not Path(root).is_dir():
        print("skipping: TIT_SCENE_TESTDATA is unset or not a directory")
        pytest.skip("TIT_SCENE_TESTDATA is unset (no real BIDS project)")
    caps = request.getfixturevalue("simnibs_real")
    from tit.paths import get_path_manager

    yield caps, get_path_manager(root), os.environ.get("TIT_SCENE_SUBJECT", "ernie")


def _read(path: Path) -> tuple[list[str], np.ndarray]:
    from tit.scene.build import parse_electrode_csv

    parsed = parse_electrode_csv(path.read_text())
    rows = parsed["electrodes"] + parsed["reference"]
    return [r["name"] for r in rows], np.array([r["world"] for r in rows], dtype=float)


def test_rewarp_matches_charms_own_positions(real, tmp_path) -> None:
    caps, pm, sid = real
    charm_csv = Path(pm.eeg_positions(sid)) / CAP
    if not charm_csv.is_file():
        pytest.skip(f"{sid} has no charm-written {CAP}")
    source = caps.simnibs_caps_dir() / CAP

    caps.warp_caps(pm.m2m(sid), sid, [source], str(tmp_path))

    names, ours = _read(tmp_path / CAP)
    charm_names, charm = _read(charm_csv)
    assert names == charm_names and len(names) > 0
    shift = np.linalg.norm(ours - charm, axis=1)
    print(
        f"[{sid}] {CAP}: {len(names)} electrodes, max shift vs charm {shift.max():.4f} mm"
    )
    assert shift.max() < SAME_POSITION_MM

    stats = caps.net_stats(
        names, ours, caps.skin_nodes(str(Path(pm.m2m(sid)) / f"{sid}.msh"))
    )
    print(f"[{sid}] summary {stats['summary']}")
    assert stats["collapsed"] == []
    assert stats["summary"]["scalp_max_mm"] < ON_SCALP_MM


def test_shipped_gsn128_warps_without_collapsed_electrodes(real, tmp_path) -> None:
    """The repository's GSN-HydroCel-128 (MNI since 6361c2b2) spreads over the scalp.

    The earlier file, in Brainstorm's head frame, put 43 central electrodes on one scalp
    point; :func:`tit.caps.net_stats` is the check that reports that as ``collapsed``.
    """
    caps, pm, sid = real
    source = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "ElectrodeCaps_MNI"
        / "GSN-HydroCel-128.csv"
    )
    caps.warp_caps(pm.m2m(sid), sid, [source], str(tmp_path))
    names, world = _read(tmp_path / source.name)
    stats = caps.net_stats(names, world)
    print(f"[{sid}] GSN-HydroCel-128: {stats['summary']}")
    assert stats["summary"]["count"] >= 128
    assert stats["collapsed"] == []


def _csv_electrodes(path: Path) -> tuple[list[str], np.ndarray]:
    """``Electrode`` / ``ReferenceElectrode`` rows read with the csv module alone."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if r and r[0] in _ELECTRODE_TYPES]
    return [r[4] for r in rows], np.array([r[1:4] for r in rows], dtype=float)


_ELECTRODE_TYPES = ("Electrode", "ReferenceElectrode")


def _mtimes(directory: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in directory.rglob("*") if p.is_file()}


@pytest.fixture(scope="module")
def mni152(request):
    root = os.environ.get("TIT_DATASET_000")
    if not root or not Path(root).is_dir():
        print("skipping: TIT_DATASET_000 is unset or not a directory")
        pytest.skip("TIT_DATASET_000 is unset (no Dataset 000 copy)")
    caps = request.getfixturevalue("simnibs_real")
    from tit.paths import get_path_manager

    pm = get_path_manager(root)
    m2m = Path(pm.m2m("MNI152"))
    if not (m2m / "MNI152.msh").is_file():
        print(f"skipping: {m2m} has no head mesh")
        pytest.skip("Dataset 000 has no sub-MNI152 head model")
    return caps, m2m


def test_tit_caps_land_on_their_mni_coordinates_on_mni152(mni152, tmp_path) -> None:
    """Each TI-Toolbox cap, warped onto the MNI152 head, lands where its MNI rows meet the skin.

    Same labels in the same order; every electrode moved by no more than its MNI row's
    distance to the skin plus ``WARP_RESIDUAL_MM``, ends within ``ON_SCALP_MM`` of a skin
    node, and no two electrodes are closer than ``tit.caps.COLLAPSE_MM``. Distances are
    taken with SciPy's KD-tree, not with ``tit.caps``.
    """
    from scipy.spatial import cKDTree

    caps, m2m = mni152
    sources = sorted(_REPO_CAPS.glob("*.csv"))
    assert {p.name for p in sources} == caps.TIT_CAPS, "has the six TI-Toolbox caps"
    before = _mtimes(m2m)

    caps.warp_caps(str(m2m), "MNI152", sources, str(tmp_path))

    skin = cKDTree(caps.skin_nodes(str(m2m / "MNI152.msh")))
    for source in sources:
        names, mni = _csv_electrodes(source)
        warped_names, warped = _csv_electrodes(tmp_path / source.name)
        assert warped_names == names and len(names) >= 64, source.name
        shift = np.linalg.norm(warped - mni, axis=1)
        row_to_skin = skin.query(mni)[0]
        scalp = skin.query(warped)[0]
        excess = shift - row_to_skin
        print(
            f"[MNI152] {source.name}: {len(names)} electrodes, shift median "
            f"{np.median(shift):.2f} max {shift.max():.2f} mm "
            f"({names[int(shift.argmax())]}), excess over the row's skin distance "
            f"max {excess.max():.2f} mm, scalp max {scalp.max():.2f} mm"
        )
        assert excess.max() < WARP_RESIDUAL_MM, names[int(excess.argmax())]
        assert scalp.max() < ON_SCALP_MM, names[int(scalp.argmax())]
        collapsed = cKDTree(warped).query_pairs(caps.COLLAPSE_MM)
        assert not collapsed, [(names[i], names[j]) for i, j in sorted(collapsed)][:3]
    assert _mtimes(m2m) == before, "Dataset 000 must stay untouched"
