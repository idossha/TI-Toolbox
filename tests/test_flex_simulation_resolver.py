"""``tit.sim.montage_sources.resolve_flex_simulation``: a finished flex run as a simulation montage.

What this pins (2026-10-08): which run is used (the named one, else the newest), which placement
(a given net -- mapped on demand when the run has no mapping for it -- else the first mapped net,
else the optimised XYZ as ``flex_free``), which currents (given, else the run's optimised split,
else its ``current_mA`` per channel, else 1 mA), and the errors for no run / an unknown run. This
is the one copy of the Simulator's flex-row rule that both ``GET /api/sim-from-flex`` (the agent
plugin's ``simulate_flex_result``) and a proposal's ``sim_from_flex`` step use. Its electrodes go
through ``resolve_flex_montage`` and so through ``tit.catalog.pair_by_channel`` -- the same pairs
the Simulator page reads from ``GET /api/catalog/flex-runs`` -- and a net the run is already
mapped to is read without re-mapping or rewriting its cache.

Where the values come from: the run files below are authored here in the shape flex-search writes
(``electrode_positions.json`` / ``electrode_mapping_<net>.json``: one ``[channel, array]`` per
electrode; groundTruth: authored, the out-of-order case listed so consecutive pairing would give a
different answer); the expected montages and currents restate the rule above, not the
implementation. The run listing (``tit.catalog.flex_runs``) and the Hungarian mapping are tested
in their own modules, so both are replaced here.

Reproduce: .venv/bin/python -m pytest tests/test_flex_simulation_resolver.py -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit import catalog
from tit.paths import PathManager
from tit.sim import montage_sources

NET = "GSN-HydroCel-185.csv"
#: Listed out of channel order: electrode i belongs to channel INDICES[i][0], array [i][1].
INDICES = [[1, 0], [0, 0], [1, 1], [0, 1]]
LABELS = ["E1", "E2", "E3", "E4"]
XYZ = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [1.0, 1.0, 1.0]]
#: Channel 0 is electrodes 2 and 4 (arrays 0, 1), channel 1 is electrodes 1 and 3.
PAIRED_LABELS = [["E2", "E4"], ["E1", "E3"]]
PAIRED_XYZ = [[XYZ[1], XYZ[3]], [XYZ[0], XYZ[2]]]


@pytest.fixture()
def project(tmp_path, monkeypatch):
    pm = PathManager(project_dir=str(tmp_path))
    found: list = []
    monkeypatch.setattr("tit.catalog.flex_runs", lambda pm_, sid: found)
    return pm, found


def _write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps(data))


def add_run(project, name, created, *, mapped=False, manifest=None):
    pm, found = project
    run_dir = pm.flex_search_run("101", name)
    _write(
        os.path.join(run_dir, "electrode_positions.json"),
        {"optimized_positions": XYZ, "channel_array_indices": INDICES},
    )
    mapping = os.path.join(run_dir, "electrode_mapping_GSN-HydroCel-185.json")
    if mapped:
        _write(
            mapping,
            {
                "mapped_labels": LABELS,
                "channel_array_indices": INDICES,
                "eeg_net": NET,
            },
        )
    found.append(
        {
            "name": name,
            "created": created,
            "manifest": manifest or {},
            "mappings": [catalog.read_flex_mapping(mapping)] if mapped else [],
        }
    )
    return mapping


def resolve(project, **kwargs):
    return montage_sources.resolve_flex_simulation(project[0], "101", **kwargs)


@pytest.fixture()
def no_mapping(monkeypatch):
    """Fail loudly if anything runs the Hungarian mapping."""
    import tit.tools.map_electrodes as map_electrodes

    def refuse(*args, **kwargs):
        raise AssertionError("re-mapped a net the run is already mapped to")

    monkeypatch.setattr(map_electrodes, "map_electrodes_to_net", refuse)
    monkeypatch.setattr(map_electrodes, "save_mapping_result", refuse)


def test_newest_run_first_mapped_net_and_its_current_per_channel(project, no_mapping):
    add_run(project, "old", "2026-10-01T00:00:00", mapped=True)
    cache = add_run(
        project, "new", "2026-10-07T00:00:00", mapped=True, manifest={"current_mA": 2}
    )
    before = Path(cache).read_bytes()
    out = resolve(project)
    assert out["flex_run"] == "new"
    assert out["montage"] == {
        "_type": "Montage",
        "name": "new",
        "mode": "flex_mapped",
        "electrode_pairs": PAIRED_LABELS,
        "eeg_net": NET,
    }
    assert out["intensities"] == [2.0, 2.0]
    assert out["intensities_from"] == "the run's current_mA per channel"
    assert Path(cache).read_bytes() == before  # read, never rewritten


def test_named_run_without_mapping_uses_the_optimised_positions(project):
    add_run(project, "a", "2026-10-07")
    add_run(project, "b", "2026-10-01", manifest={"current_split": [1.5, 0.5]})
    out = resolve(project, flex_run="/abs/flex-search/b/")
    assert out["flex_run"] == "b"
    assert out["montage"]["mode"] == "flex_free" and out["montage"]["eeg_net"] is None
    assert out["montage"]["electrode_pairs"] == PAIRED_XYZ
    assert out["intensities"] == [1.5, 0.5]


def test_a_net_the_run_was_not_mapped_to_is_mapped_on_demand(project, monkeypatch):
    pm, _ = project
    add_run(project, "a", "2026-10-07", mapped=True)
    net_dir = pm.eeg_positions("101")
    os.makedirs(net_dir)
    Path(net_dir, "EEG10-10_UI_Jurak_2007.csv").write_text("x\n")
    import tit.tools.map_electrodes as map_electrodes

    asked = []
    monkeypatch.setattr(
        map_electrodes, "read_csv_positions", lambda path: ([[0, 0, 0]] * 4, LABELS)
    )

    def fake_map(opt_pos, net_pos, net_labels, indices):
        asked.append(indices)
        return {
            "mapped_labels": ["Fz", "P3", "Cz", "P4"],
            "channel_array_indices": indices,
        }

    monkeypatch.setattr(map_electrodes, "map_electrodes_to_net", fake_map)
    out = resolve(project, eeg_net="EEG10-10_UI_Jurak_2007", intensities=[1, 3])
    assert asked == [INDICES]
    assert out["eeg_net"] == "EEG10-10_UI_Jurak_2007.csv"
    # INDICES pair electrodes 2+4 (channel 0) and 1+3 (channel 1).
    assert out["montage"]["electrode_pairs"] == [["P3", "P4"], ["Fz", "Cz"]]
    assert out["intensities"] == [1.0, 3.0] and out["intensities_from"] == "given"
    # The second time the cache it wrote is read, not re-mapped.
    asked.clear()
    again = resolve(project, eeg_net="EEG10-10_UI_Jurak_2007.csv")
    assert again["montage"]["electrode_pairs"] == [["P3", "P4"], ["Fz", "Cz"]]
    assert asked == []
    # A net the run is already mapped to ("GSN-HydroCel-185" == ".csv") is read too.
    assert resolve(project, eeg_net="GSN-HydroCel-185")["montage"][
        "electrode_pairs"
    ] == (PAIRED_LABELS)
    assert asked == []


def test_no_run_and_unknown_run_are_errors(project):
    with pytest.raises(ValueError, match="no finished flex-search run"):
        resolve(project)
    add_run(project, "only", "2026-10-07")
    with pytest.raises(ValueError, match="only"):
        resolve(project, flex_run="other")
    # no manifest current: 1 mA per channel
    assert resolve(project)["intensities"] == [1.0, 1.0]


def test_the_catalog_and_both_montage_paths_pair_alike(project, no_mapping):
    """One pairing rule: what the Simulator page reads (the catalog's run record) is what
    ``/api/plan``'s flex sources and the agent's simulation get."""
    pm, _ = project
    add_run(project, "a", "2026-10-07", mapped=True)
    run_dir = pm.flex_search_run("101", "a")
    assert catalog.flex_optimized_pairs(run_dir) == PAIRED_XYZ
    free = montage_sources.resolve_flex_montage(pm, "101", "a", "optimized")
    mapped = montage_sources.resolve_flex_montage(pm, "101", "a", "mapped", eeg_net=NET)
    assert [list(p) for p in free.electrode_pairs] == PAIRED_XYZ
    assert [list(p) for p in mapped.electrode_pairs] == PAIRED_LABELS


FLEX_CURRENTS = json.loads(
    (Path(__file__).parent / "fixtures" / "flex_currents.json").read_text()
)


@pytest.mark.parametrize("case", FLEX_CURRENTS, ids=lambda c: c["case"])
def test_flex_currents_order_is_split_then_current_mA_then_one_mA(case):
    # The same table pins the Simulator page (desktop/tests/unit/flex-currents.test.ts).
    currents, _ = montage_sources.flex_currents(case["manifest"], case["pairs"])
    assert currents == case["currents"]


def test_resolved_currents_come_from_flex_currents(project):
    add_run(project, "a", "2026-10-07", manifest={"current_split": [0.7, 1.3]})
    out = resolve(project)
    assert out["intensities"] == [0.7, 1.3]
    assert out["intensities_from"] == "the run's optimised split"
