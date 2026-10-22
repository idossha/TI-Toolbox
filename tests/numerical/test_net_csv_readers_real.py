"""SimNIBS's own net reader is the independent reader for TI-Toolbox's net readers.

What this pins (2026-10-22, package p07, tasks net-csv-reader-contract and
reference-electrode-rule), in the image with the real SimNIBS, scipy and pandas:

* For every net, ``simnibs.utils.csv_reader.read_csv_positions`` (the reader the simulation
  itself resolves electrode labels with) restricted to ``Electrode`` rows gives the same
  labels and coordinates as ``tit.tools.map_electrodes.read_csv_positions`` (the flex
  mapper) and as the flex skin picture's ``_load_electrodes`` (real scipy). Nets: a
  hand-written charm-format fixture, every cap SimNIBS ships in ``ElectrodeCaps_MNI``, and,
  with ``TIT_DATASET_000`` set, every ``eeg_positions/*.csv`` of every Dataset 000 subject.
  The host-runnable readers are compared with each other in ``tests/test_net_csv_readers.py``.
* The flex optimizer's own mapping (``resources/map-electrodes/tes_flex_optimization.py``,
  loaded from the checkout by ``tit.opt.flex.runtime``) maps an optimised point that sits
  exactly on the ``ReferenceElectrode`` Cz to the nearest Electrode (CPz at
  sqrt(32^2 + 7^2) mm, hand-computed from the fixture), never to Cz.

The checks run in a subprocess: ``tests/conftest.py`` replaces SimNIBS and pandas with mocks
in this interpreter. SimNIBS raises on a net with a blank line (``CSV file must have at least
4 rows`` / ``IndexError``), so the blank-line fixture is only in the host test, where every
TI-Toolbox reader must skip it.

Reproduce in the image::

    simnibs_python -m pytest tests/numerical/test_net_csv_readers_real.py -q
    # with -v /Users/idohaber/datasets/000:/data/000:ro -e TIT_DATASET_000=/data/000
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CHARM = (
    "Electrode,-26.5,113.1,19.3,Fp1\r\n"
    "Electrode,40.25,-20.0,85.5,46\r\n"
    "Electrode,-70.0,-30.0,-40.0,Left Mastoid\r\n"
    "ReferenceElectrode,2.79,27.3,97.4,Cz\r\n"
    "Fiducial,2.4,113.8,-11.9,Nz\r\n"
)
JURAK_LIKE = (
    "Electrode,0.0,60.0,70.0,Fz\n"
    "Electrode,-60.0,-8.0,70.0,C3\n"
    "Electrode,60.0,-8.0,70.0,C4\n"
    "Electrode,0.0,25.0,90.0,FCz\n"
    "Electrode,0.0,-40.0,90.0,CPz\n"
    "Electrode,0.0,-70.0,70.0,Pz\n"
    "ReferenceElectrode,0.0,-8.0,97.0,Cz\n"
    "Fiducial,0.0,90.0,-20.0,Nz\n"
)

_SCRIPT = r"""
import json, logging, os, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import simnibs
from simnibs.utils.csv_reader import read_csv_positions as simnibs_read
from tit.tools.map_electrodes import read_csv_positions
from tit.opt.flex.skin_visualization import _load_electrodes
from tit.opt.flex.runtime import integration_module

work, root = Path(sys.argv[1]), sys.argv[2]
nets = [work / "charm.csv", work / "jurak.csv"]
nets += sorted((Path(simnibs.__file__).parent / "resources" / "ElectrodeCaps_MNI").glob("*.csv"))
if root:
    nets += sorted((Path(root) / "derivatives" / "SimNIBS").glob("sub-*/m2m_*/eeg_positions/*.csv"))

out = {}
log = logging.getLogger("fixture")
for path in nets:
    types, coords, _, names, _, _ = simnibs_read(str(path))
    simnibs = {n: [float(v) for v in c] for t, c, n in zip(types, coords, names) if t == "Electrode"}
    pos, labels = read_csv_positions(str(path))
    mapper = {l: [float(v) for v in p] for p, l in zip(pos, labels)}
    cloud = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    skin = _load_electrodes(str(path), cloud, cloud, np.array([True, True]), None, log)
    picture = {} if skin is None else {
        str(l): [float(v) for v in p] for p, l in zip(skin["positions"], skin["labels"])
    }
    out[str(path)] = {"simnibs": simnibs, "mapper": mapper, "picture": picture,
                      "label_types": sorted({type(l).__name__ for l in (skin or {}).get("labels", [])})}

module = integration_module()
opt = module.TesFlexOptimization()
def array_at(xyz):
    posmat = np.eye(4)
    posmat[:3, 3] = xyz
    return SimpleNamespace(electrodes=[SimpleNamespace(posmat=posmat)])
opt.electrode = [SimpleNamespace(_electrode_arrays=[array_at([0.0, 60.0, 70.0]), array_at([0.0, -8.0, 97.0])]),
                 SimpleNamespace(_electrode_arrays=[array_at([-60.0, -8.0, 70.0]), array_at([60.0, -8.0, 70.0])])]
opt.output_folder = str(work)
mapping = opt.map_to_nearest_net_electrodes(str(work / "jurak.csv"))
print(json.dumps({"nets": out, "optimizer_labels": list(mapping["mapped_labels"]),
                  "optimizer_distances": [float(d) for d in mapping["distances"]]}))
"""


def _run(tmp_path: Path) -> dict:
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs, pandas"], capture_output=True, text=True
    )
    if probe.returncode != 0:
        pytest.skip(
            "skipping: real SimNIBS and pandas are not importable (run in the image)"
        )
    (tmp_path / "charm.csv").write_bytes(CHARM.encode())
    (tmp_path / "jurak.csv").write_text(JURAK_LIKE)
    root = os.environ.get("TIT_DATASET_000", "")
    if root and not Path(root).is_dir():
        pytest.skip(f"skipping: TIT_DATASET_000={root} is not a directory")
    done = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(tmp_path), root],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=600,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-4000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def result(tmp_path_factory) -> dict:
    return _run(tmp_path_factory.mktemp("nets"))


def test_simnibs_the_mapper_and_the_skin_picture_read_the_same_electrodes(
    result: dict,
) -> None:
    nets = result["nets"]
    shipped = [p for p in nets if "ElectrodeCaps_MNI" in p]
    assert len(shipped) >= 10, f"has SimNIBS caps to check: {shipped}"
    if os.environ.get("TIT_DATASET_000"):
        assert any("eeg_positions" in p for p in nets), "has Dataset 000 nets to check"
    for path, readers in nets.items():
        simnibs = readers["simnibs"]
        for name in ("mapper", "picture"):
            got = readers[name]
            assert set(got) == set(simnibs), (path, name)
            for label, xyz in got.items():
                assert xyz == pytest.approx(simnibs[label], abs=1e-9), (
                    path,
                    name,
                    label,
                )
        if readers["picture"]:
            assert readers["label_types"] == ["str"], (path, readers["label_types"])


def test_the_fixture_reads_as_written(result: dict) -> None:
    charm = next(v for k, v in result["nets"].items() if k.endswith("charm.csv"))
    assert charm["simnibs"] == {
        "Fp1": [-26.5, 113.1, 19.3],
        "46": [40.25, -20.0, 85.5],
        "Left Mastoid": [-70.0, -30.0, -40.0],
    }


def test_the_optimizer_copy_never_maps_onto_the_reference(result: dict) -> None:
    labels = result["optimizer_labels"]
    assert sorted(labels) == ["C3", "C4", "CPz", "Fz"]
    by_label = dict(zip(labels, result["optimizer_distances"]))
    assert by_label["CPz"] == pytest.approx((32.0**2 + 7.0**2) ** 0.5)
    assert by_label["Fz"] == by_label["C3"] == by_label["C4"] == 0.0
