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
"""

from __future__ import annotations

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


@pytest.fixture(scope="module")
def real():
    root = os.environ.get("TIT_SCENE_TESTDATA")
    if not root or not Path(root).is_dir():
        print("skipping: TIT_SCENE_TESTDATA is unset or not a directory")
        pytest.skip("TIT_SCENE_TESTDATA is unset (no real BIDS project)")
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
    from tit.paths import get_path_manager

    yield caps, get_path_manager(root), os.environ.get("TIT_SCENE_SUBJECT", "ernie")
    for k in [k for k in sys.modules if k.split(".")[0] == "simnibs"]:
        del sys.modules[k]
    sys.modules.update(saved)


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
