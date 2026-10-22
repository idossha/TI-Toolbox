"""One rule for a net's ReferenceElectrode: it is never offered as a stimulation electrode.

What this pins (2026-10-22, package p07, task reference-electrode-rule):

The 10-10 caps SimNIBS ships (Jurak 2007, Cutini 2011, Neuroelectrics, Okamoto 2004) and the
SPM12 cap store Cz as a ``ReferenceElectrode`` row. The catalog's net pickers, job preflight,
the simulation's coordinate resolution and the electrode overlay all read ``Electrode`` rows
only; the flex mapper (``tit.tools.map_electrodes`` and the optimizer's own copy in
``resources/map-electrodes/tes_flex_optimization.py``) also took ``ReferenceElectrode`` rows.
So an optimised position on Cz was mapped to "Cz", and preflight then refused the mapped
montage ("electrode(s) Cz ... in EEG net"). The rule kept is the one the catalog, preflight
and the UI already apply: the mapper skips the reference too.

Expected values are the fixture rows below (a Jurak-shaped net, coordinates hand-placed so
every distance is one or two differences): an optimised point exactly on the reference goes
to the nearest *Electrode* still free, CPz at sqrt(32^2 + 7^2) = 32.76 mm, ahead of FCz at
sqrt(33^2 + 7^2) = 33.73 mm. The assignment is solved by brute force over permutations in
the test (scipy is a mock on the host), a second implementation of the Hungarian step.

The optimizer copy runs SimNIBS's own reader; its leg is in
``tests/numerical/test_net_csv_readers_real.py`` (container). It is loaded from the checkout
at run time (``tit.opt.flex.runtime``), so the change is live without an image rebuild.

Reproduce: ``.venv/bin/python -m pytest tests/test_reference_electrode_rule.py -q``.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tit.catalog import _read_cap_electrode_labels
from tit.jobs.preflight import _eeg_labels, preflight
from tit.opt.ex.buckets import _read_eeg_positions
from tit.paths import get_path_manager
from tit.scene.build import parse_electrode_csv
from tit.sim.utils import _load_eeg_position_csv, resolve_montage_electrode_coordinates
from tit.tools import map_electrodes
from tit.tools.electrode_overlay import _extract_position_pairs, _load_eeg_positions

NET = "EEG10-10_UI_Jurak_2007.csv"
ELECTRODES = {
    "Fz": (0.0, 60.0, 70.0),
    "C3": (-60.0, -8.0, 70.0),
    "C4": (60.0, -8.0, 70.0),
    "FCz": (0.0, 25.0, 90.0),
    "CPz": (0.0, -40.0, 90.0),
    "Pz": (0.0, -70.0, 70.0),
}
CZ = (0.0, -8.0, 97.0)
TEXT = (
    "".join(f"Electrode,{x},{y},{z},{name}\n" for name, (x, y, z) in ELECTRODES.items())
    + f"ReferenceElectrode,{CZ[0]},{CZ[1]},{CZ[2]},Cz\n"
    + "Fiducial,0.0,90.0,-20.0,Nz\n"
)


def _brute_force_assignment(cost):
    cost = np.asarray(cost)
    n = cost.shape[0]
    best = min(
        itertools.permutations(range(cost.shape[1]), n),
        key=lambda cols: sum(cost[i, c] for i, c in enumerate(cols)),
    )
    return np.arange(n), np.array(best)


@pytest.fixture
def net(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pm = get_path_manager(str(tmp_path))
    m2m = Path(pm.m2m("ernie"))
    (m2m / "eeg_positions").mkdir(parents=True)
    (m2m / "ernie.msh").write_bytes(b"mesh")
    path = m2m / "eeg_positions" / NET
    path.write_text(TEXT)
    monkeypatch.setattr(
        map_electrodes, "linear_sum_assignment", _brute_force_assignment
    )
    return path


def _map(path: Path, points: list[tuple[float, float, float]]) -> dict:
    positions, labels = map_electrodes.read_csv_positions(str(path))
    return map_electrodes.map_electrodes_to_net(
        np.array(points), positions, labels, [[i, 0] for i in range(len(points))]
    )


def test_every_reader_offers_the_electrode_rows_and_never_the_reference(
    net: Path,
) -> None:
    expected = set(ELECTRODES)
    _, mapper_labels = map_electrodes.read_csv_positions(str(net))
    offered = {
        "map_electrodes": set(mapper_labels),
        "catalog": set(_read_cap_electrode_labels(str(net))),
        "preflight": _eeg_labels(net),
        "sim.utils": set(_load_eeg_position_csv(str(net))),
        "electrode_overlay": set(_load_eeg_positions(net.parent, NET)),
        "ex.buckets": set(_read_eeg_positions(net)),
        "scene electrodes": {
            e["name"] for e in parse_electrode_csv(TEXT)["electrodes"]
        },
    }
    assert offered == {reader: expected for reader in offered}


def test_a_point_on_the_reference_maps_to_the_nearest_free_electrode(net: Path) -> None:
    mapping = _map(net, [ELECTRODES["Fz"], CZ, ELECTRODES["C3"], ELECTRODES["C4"]])
    assert mapping["mapped_labels"] == ["Fz", "CPz", "C3", "C4"]
    assert mapping["mapped_positions"][1] == list(ELECTRODES["CPz"])
    assert mapping["distances"][1] == pytest.approx(np.hypot(32.0, 7.0))


def test_whatever_the_mapper_outputs_preflight_and_coordinates_accept(
    net: Path, tmp_path: Path
) -> None:
    # Every optimised point on the reference or an electrode, in turn.
    points = [CZ, *ELECTRODES.values()]
    labels = (
        _map(net, points[:4])["mapped_labels"] + _map(net, points[3:])["mapped_labels"]
    )
    assert "Cz" not in labels
    pairs = [labels[i : i + 2] for i in range(0, len(labels) - 1, 2)]
    montage = {
        "name": "mapped",
        "mode": "flex_mapped",
        "eeg_net": NET,
        "electrode_pairs": pairs,
    }
    assert (
        preflight("sim", {"subject_id": "ernie", "montages": [montage]}, str(tmp_path))
        == []
    )

    coords, source = resolve_montage_electrode_coordinates(
        SimpleNamespace(subject_id="ernie"),
        SimpleNamespace(is_xyz=False, eeg_net=NET, electrode_pairs=pairs),
    )
    assert source == f"eeg_positions/{NET}"
    assert coords == [list(ELECTRODES[label]) for pair in pairs for label in pair]
    overlay = _extract_position_pairs(
        {"eeg_net": NET, "electrode_pairs": pairs}, None, net.parent
    )
    assert overlay == [[ELECTRODES[a], ELECTRODES[b]] for a, b in pairs]


def test_preflight_refuses_the_reference_the_mapper_no_longer_offers(
    net: Path, tmp_path: Path
) -> None:
    montage = {
        "name": "ref",
        "mode": "flex_mapped",
        "eeg_net": NET,
        "electrode_pairs": [["Cz", "Fz"]],
    }
    found = preflight(
        "sim", {"subject_id": "ernie", "montages": [montage]}, str(tmp_path)
    )
    assert [f.what for f in found] == [
        f"electrode(s) Cz of montage 'ref' in EEG net '{NET}'"
    ]


def test_the_optimizer_copy_skips_the_reference_row() -> None:
    """The flex optimizer's own mapping loop keeps ``Electrode`` rows only.

    It runs inside SimNIBS (its numerical leg is in the container); here the source is read
    off disk so a host run catches the type filter being widened again.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "resources/map-electrodes/tes_flex_optimization.py"
    ).read_text()
    body = source[source.index("def map_to_nearest_net_electrodes") :]
    body = body[: body.index("\n    def ", 1)]
    assert "if t == 'Electrode':" in body
    assert "ReferenceElectrode']" not in body
