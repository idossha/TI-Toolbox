"""Every EEG net the viewer and Blender read sits on its subject's skin, and collapsed ones are refused.

What this pins (2026-10-22, package p07, task realdata-net-sanity, container leg), read-only
over every subject in ``$TIT_DATASET_000/derivatives/SimNIBS`` and every net CSV in its
``m2m_<id>/eeg_positions``, with the real SimNIBS mesh reader:

* Every electrode and reference electrode, as ``tit.scene.build.read_net`` serves it, is
  within 15 mm of the nearest skin node (tag 1005) of the subject's own head mesh (the bound
  and its rationale are ``tests/test_scene_realdata.py``'s: a cap pad plus mesh spacing). The
  distance is computed here by brute force with numpy, not with ``tit.caps``.
* ``read_net`` refuses a net exactly when two of its electrodes are closer than 2 mm other
  than the 10-20 synonyms T3/T7, T4/T8, T5/P7, T6/P8 (typed from Oostenveld & Praamstra 2001),
  counted here with numpy; such a net is never drawn as a few points. Measured 2026-10-22:
  sub-LA and sub-CHN BioSemi-64/128/256 and GSN-HydroCel-128 (406-5995 pairs) are refused,
  pinned as such rather than skipped.

The host half (labels, cross-net 10-10 agreement, preflight) is
``tests/test_net_sanity_realdata.py``. The meshes are read in a subprocess:
``tests/conftest.py`` mocks SimNIBS in this interpreter.

Reproduce in the image::

    docker run --rm -v <repo>:/ti-toolbox -w /ti-toolbox \\
      -v /Users/idohaber/datasets/000:/data/000:ro -e TIT_DATASET_000=/data/000 \\
      idossha/ti-toolbox:v3.1.1 -lc 'simnibs_python -m pytest tests/numerical/test_net_on_scalp_realdata.py -q'
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
REPO = Path(__file__).resolve().parents[2]
ON_SKIN_MM = 15.0

pytestmark = pytest.mark.skipif(
    not ROOT or not Path(ROOT).is_dir(),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)

_SCRIPT = r"""
import json, sys
from pathlib import Path
import numpy as np
from simnibs.mesh_tools import mesh_io
from tit.paths import get_path_manager
from tit.scene import build

root = sys.argv[1]
aliases = {frozenset(p) for p in (("T3", "T7"), ("T4", "T8"), ("T5", "P7"), ("T6", "P8"))}
pm = get_path_manager(root)
out = {}
for m2m in sorted((Path(root) / "derivatives" / "SimNIBS").glob("sub-*/m2m_*")):
    sid = m2m.name[len("m2m_"):]
    nets = sorted((m2m / "eeg_positions").glob("*.csv"))
    mesh = m2m / f"{sid}.msh"
    if not nets or not mesh.is_file():
        continue
    skin = np.asarray(mesh_io.read_msh(str(mesh)).crop_mesh(tags=[1005]).nodes.node_coord, float)
    for path in nets:
        body = build.read_net(pm, sid, path.name, allow_collapsed=True)
        rows = body["electrodes"] + body["reference"]
        if not rows:
            continue
        names = [r["name"] for r in rows]
        world = np.array([r["world"] for r in rows], float)
        off = np.empty(len(world))
        for s in range(0, len(world), 32):
            chunk = world[s:s + 32]
            off[s:s + 32] = np.sqrt(((chunk[:, None, :] - skin[None, :, :]) ** 2).sum(-1)).min(1)
        d = np.sqrt(((world[:, None, :] - world[None, :, :]) ** 2).sum(-1))
        close = [
            (names[i], names[j]) for i, j in zip(*np.nonzero(np.triu(d < 2.0, k=1)))
            if frozenset((names[i], names[j])) not in aliases
        ]
        try:
            build.read_net(pm, sid, path.name)
            refused = ""
        except build.SceneUnavailable as exc:
            refused = str(exc)
        k = int(off.argmax())
        out[f"sub-{sid}/{path.name}"] = {
            "n": len(names), "max_off": float(off[k]), "worst": names[k],
            "collapsed": len(close), "refused": refused,
        }
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def nets() -> dict:
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs.mesh_tools.mesh_io"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        pytest.skip(
            "skipping: the real SimNIBS mesh reader is not importable (run in the image)"
        )
    files = sorted(Path(ROOT).glob("derivatives/SimNIBS/sub-*/m2m_*/*.msh")) + sorted(
        Path(ROOT).glob("derivatives/SimNIBS/sub-*/m2m_*/eeg_positions/*.csv")
    )
    before = {p: p.stat().st_mtime_ns for p in files}
    done = subprocess.run(
        [sys.executable, "-c", _SCRIPT, ROOT],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=1800,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-4000:]
    assert {p: p.stat().st_mtime_ns for p in files} == before, "the dataset was written"
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_every_subject_and_net_was_checked(nets: dict) -> None:
    subjects = {key.split("/")[0] for key in nets}
    assert len(subjects) >= 4, subjects
    assert len(nets) >= 40, sorted(nets)


def test_every_electrode_sits_on_its_subjects_skin(nets: dict) -> None:
    off = {
        k: (round(v["max_off"], 1), v["worst"])
        for k, v in nets.items()
        if v["max_off"] > ON_SKIN_MM
    }
    assert off == {}


def test_read_net_refuses_exactly_the_collapsed_nets(nets: dict) -> None:
    wrong = {
        k: (v["collapsed"], v["refused"][:80])
        for k, v in nets.items()
        if bool(v["collapsed"]) != bool(v["refused"])
        or (v["refused"] and "Re-apply in EEG caps" not in v["refused"])
    }
    assert wrong == {}
    assert any(v["collapsed"] == 0 for v in nets.values()), "has sound nets"
