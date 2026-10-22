"""Mapping a flex result onto an EEG net: refused nets, distinct labels, and the snap distance.

What this pins (package p24, audit_caps-electrodes.md "mapping edge cases" and audit_flex.md
"mapping snap is unbounded and invisible", 2026-10-22):

- ``resolve_flex_montage(..., "mapped")`` checked nothing about the net before the Hungarian
  assignment (unlike ``candidate_mapping``). A net with no ``Electrode`` rows (a Fiducials
  file, a header-less ``Label,X,Y,Z`` list), fewer electrodes than the run placed, a NaN
  coordinate or a repeated label now raises a ValueError naming the net and the defect, and
  no ``electrode_mapping_<net>.json`` is written.
- ``catalog.read_flex_mapping`` refuses a mapping whose labels repeat (two optimised
  electrodes on one site is not a montage) and carries ``max_snap_mm`` -- the largest
  distance an electrode moved -- into the catalog's ``mappings``, so the Simulator can warn.

Expected values are hand fixtures: net sites placed at hand-computed offsets (3-4-5 and
6-8-10 triangles, axis offsets) from the optimised positions, so each snap distance is known
without running the code under test. The happy path replaces SciPy's assignment (mocked on
the host by tests/conftest.py) with an exhaustive search over permutations, a second
implementation; the real-SciPy check on Dataset 000 is
tests/numerical/test_flex_mapping_snap_realdata.py.

Reproduce: ``.venv/bin/python -m pytest tests/test_flex_mapping_edges.py -q``.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
import pytest

from tit import catalog
from tit.paths import get_path_manager
from tit.sim.montage_sources import resolve_flex_montage

SID = "ernie"
RUN = "run1"
OPTIMIZED = [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 100.0, 0.0], [0.0, 0.0, 100.0]]
#: Channel 1 holds electrodes 3 and 0, channel 0 holds 1 and 2: pairs follow the indices,
#: not the listing order.
CHANNELS = [[1, 1], [0, 0], [0, 1], [1, 0]]
#: Each optimised electrode's nearest site and its hand-computed distance (mm).
NEAR = [
    ("Fz", [3.0, 4.0, 0.0], 5.0),  # 3-4-5
    ("C3", [100.0, 0.0, 12.0], 12.0),
    ("Pz", [0.0, 106.0, 8.0], 10.0),  # 6-8-10
    ("Oz", [0.0, 0.0, 125.0], 25.0),
]
DECOYS = [("T7", [400.0, 400.0, 400.0]), ("T8", [-400.0, -400.0, -400.0])]


def _project(root: Path, net_rows: list[str], net: str = "Net.csv") -> object:
    (root / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(root))
    run = Path(pm.flex_search_run(SID, RUN))
    run.mkdir(parents=True)
    (run / "electrode_positions.json").write_text(
        json.dumps(
            {"optimized_positions": OPTIMIZED, "channel_array_indices": CHANNELS}
        )
    )
    # What makes the folder a run the catalog lists.
    (run / "flex_meta.json").write_text(
        json.dumps({"version": 1, "goal": "mean", "label": RUN, "result": {}})
    )
    Path(pm.m2m(SID), f"{SID}.msh").parent.mkdir(parents=True)
    Path(pm.m2m(SID), f"{SID}.msh").write_bytes(b"")
    Path(pm.m2m(SID), "final_tissues.nii.gz").write_bytes(b"")
    caps = Path(pm.eeg_positions(SID))
    caps.mkdir(parents=True)
    (caps / net).write_text("\n".join(net_rows) + "\n")
    return pm


def _electrodes(sites) -> list[str]:
    return [f"Electrode,{x},{y},{z},{label}" for label, (x, y, z), *_ in sites]


def _mapping_files(pm) -> list[str]:
    run = Path(pm.flex_search_run(SID, RUN))
    return sorted(p.name for p in run.glob("electrode_mapping*.json"))


@pytest.mark.parametrize(
    "rows,defect",
    [
        (
            [
                "Fiducial,0,85,-40,Nz",
                "Fiducial,-80,-20,-50,LPA",
                "Fiducial,80,-20,-50,RPA",
            ],
            "no stimulation electrodes",
        ),
        (
            ["Fz,3,4,0", "C3,100,0,12", "Pz,0,106,8", "Oz,0,0,125"],
            "no stimulation electrodes",
        ),
        (_electrodes(NEAR[:3]), "3 stimulation electrodes; the run placed 4"),
        (
            _electrodes(NEAR[:2])
            + ["Electrode,nan,106,8,Pz"]
            + _electrodes(NEAR[3:] + DECOYS),
            "non-finite coordinates for Pz",
        ),
        (_electrodes(NEAR + DECOYS) + ["Electrode,5,5,5,C3"], "repeats the label C3"),
    ],
    ids=[
        "fiducials-only",
        "label-xyz-no-type",
        "three-for-four",
        "nan",
        "duplicate-label",
    ],
)
def test_a_net_that_cannot_take_the_run_is_refused_by_name(tmp_path, rows, defect):
    pm = _project(tmp_path, rows, net="BadNet.csv")
    with pytest.raises(ValueError) as info:
        resolve_flex_montage(pm, SID, RUN, "mapped", eeg_net="BadNet.csv")
    message = str(info.value)
    assert "BadNet.csv" in message
    assert defect in message
    assert _mapping_files(pm) == []


def _exhaustive_assignment(cost):
    """A second implementation of the optimal assignment: every injective choice of sites."""
    cost = np.asarray(cost)
    n_rows, n_cols = cost.shape
    best, best_cols = math.inf, None
    for cols in itertools.permutations(range(n_cols), n_rows):
        total = sum(cost[i, j] for i, j in enumerate(cols))
        if total < best:
            best, best_cols = total, cols
    return np.arange(n_rows), np.asarray(best_cols)


def test_a_good_net_maps_onto_distinct_labels_paired_by_channel_with_its_snap(
    tmp_path, monkeypatch
):
    from tit.tools import map_electrodes

    monkeypatch.setattr(map_electrodes, "linear_sum_assignment", _exhaustive_assignment)
    pm = _project(tmp_path, _electrodes(DECOYS[:1] + NEAR + DECOYS[1:]))
    montage = resolve_flex_montage(pm, SID, RUN, "mapped", eeg_net="Net.csv")

    # Channel 0 = electrodes 1 (array 0) and 2 (array 1); channel 1 = electrodes 3 and 0.
    assert [list(p) for p in montage.electrode_pairs] == [["C3", "Pz"], ["Oz", "Fz"]]
    (written,) = _mapping_files(pm)
    data = json.loads(
        Path(pm.flex_search_run(SID, RUN), written).read_text(encoding="utf-8")
    )
    by_label = {label: d for label, _, d in NEAR}
    assert data["distances"] == pytest.approx(
        [by_label[label] for label in data["mapped_labels"]]
    )
    (run,) = catalog.flex_runs(pm, SID)
    assert run["mappings"] == [
        {
            "eeg_net": "Net.csv",
            "pairs": [["C3", "Pz"], ["Oz", "Fz"]],
            "max_snap_mm": pytest.approx(25.0),
        }
    ]


def _mapping_json(path: Path, **fields) -> str:
    data = {
        "mapped_labels": ["Fz", "C3", "Pz", "Oz"],
        "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
        "distances": [5.0, 12.0, 10.0, 25.0],
        "eeg_net": "Net.csv",
    }
    data.update(fields)
    path.write_text(json.dumps(data))
    return str(path)


def test_read_flex_mapping_carries_the_largest_snap(tmp_path):
    mapping = catalog.read_flex_mapping(_mapping_json(tmp_path / "m.json"))
    assert mapping == {
        "eeg_net": "Net.csv",
        "pairs": [["Fz", "C3"], ["Pz", "Oz"]],
        "max_snap_mm": 25.0,
    }


@pytest.mark.parametrize(
    "distances",
    [
        None,
        [5.0, 12.0, 10.0],
        [5.0, float("nan"), 10.0, 25.0],
        [5, "12", 10, 25],
        [True] * 4,
    ],
    ids=["missing", "short", "nan", "string", "bool"],
)
def test_read_flex_mapping_leaves_out_a_snap_it_cannot_trust(tmp_path, distances):
    fields = {"distances": distances} if distances is not None else {}
    path = _mapping_json(tmp_path / "m.json", **fields)
    if distances is None:
        data = json.loads(Path(path).read_text())
        data.pop("distances")
        Path(path).write_text(json.dumps(data))
    mapping = catalog.read_flex_mapping(path)
    assert mapping is not None
    assert "max_snap_mm" not in mapping
    assert mapping["pairs"] == [["Fz", "C3"], ["Pz", "Oz"]]


def test_read_flex_mapping_refuses_repeated_labels(tmp_path):
    path = _mapping_json(tmp_path / "m.json", mapped_labels=["Fz", "C3", "Fz", "Oz"])
    assert catalog.read_flex_mapping(path) is None
