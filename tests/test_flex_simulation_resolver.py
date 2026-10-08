"""``tit.sim.montage_sources.resolve_flex_simulation``: a finished flex run as a simulation montage.

What this pins (2026-10-07): which run is used (the named one, else the newest), which placement
(a given net -- mapped on demand when the run has no mapping for it -- else the first mapped net,
else the optimised XYZ as ``flex_free``), which currents (given, else the run's optimised split,
else its ``current_mA`` per channel, else 1 mA), and the errors for no run / an unknown run. This
is the one copy of the Simulator's flex-row rule that both ``GET /api/sim-from-flex`` (the agent
plugin's ``simulate_flex_result``) and a proposal's ``sim_from_flex`` step use.

Where the values come from: the run records below are authored here in the shape
``tit.catalog.flex_runs`` returns (groundTruth: authored); the expected montages and currents
restate the rule above, not the implementation. The on-disk catalog and the Hungarian mapping
are tested in their own modules, so both are replaced here.

Reproduce: .venv/bin/python -m pytest tests/test_flex_simulation_resolver.py -q
"""

from __future__ import annotations

import pytest

from tit.sim import montage_sources
from tit.sim.config import Montage

MAPPED = {"eeg_net": "GSN-HydroCel-185.csv", "pairs": [["E1", "E2"], ["E3", "E4"]]}
XYZ = [[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [1, 1, 1]]]


def run(name, created, *, mappings=(), manifest=None):
    return {
        "name": name,
        "created": created,
        "manifest": manifest or {},
        "mappings": list(mappings),
        "optimized": XYZ,
    }


@pytest.fixture()
def runs(monkeypatch):
    found: list = []
    monkeypatch.setattr("tit.catalog.flex_runs", lambda pm, sid: found)
    return found


def resolve(**kwargs):
    return montage_sources.resolve_flex_simulation(None, "101", **kwargs)


def test_newest_run_first_mapped_net_and_its_current_per_channel(runs):
    runs += [
        run("old", "2026-10-01T00:00:00", mappings=[MAPPED]),
        run(
            "new",
            "2026-10-07T00:00:00",
            mappings=[MAPPED],
            manifest={"current_mA": 2.0},
        ),
    ]
    out = resolve()
    assert out["flex_run"] == "new"
    assert out["montage"] == {
        "_type": "Montage",
        "name": "new",
        "mode": "flex_mapped",
        "electrode_pairs": MAPPED["pairs"],
        "eeg_net": MAPPED["eeg_net"],
    }
    assert out["intensities"] == [2.0, 2.0]
    assert out["intensities_from"] == "the run's current_mA per channel"


def test_named_run_without_mapping_uses_the_optimised_positions(runs):
    runs += [
        run("a", "2026-10-07"),
        run("b", "2026-10-01", manifest={"current_split": [1.5, 0.5]}),
    ]
    out = resolve(flex_run="/abs/flex-search/b/")
    assert out["flex_run"] == "b"
    assert out["montage"]["mode"] == "flex_free" and out["montage"]["eeg_net"] is None
    assert out["montage"]["electrode_pairs"] == XYZ
    assert out["intensities"] == [1.5, 0.5]


def test_a_net_the_run_was_not_mapped_to_is_mapped_on_demand(runs, monkeypatch):
    runs.append(run("a", "2026-10-07", mappings=[MAPPED]))
    asked = {}

    def fake_mapping(pm, sid, name, electrode_type, *, eeg_net):
        asked.update(sid=sid, name=name, type=electrode_type, net=eeg_net)
        return Montage(
            name="x",
            mode=Montage.Mode.FLEX_MAPPED,
            electrode_pairs=[("Fz", "Cz"), ("P3", "P4")],
            eeg_net=eeg_net,
        )

    monkeypatch.setattr(montage_sources, "resolve_flex_montage", fake_mapping)
    out = resolve(eeg_net="EEG10-10_UI_Jurak_2007", intensities=[1, 3])
    assert asked == {
        "sid": "101",
        "name": "a",
        "type": "mapped",
        "net": "EEG10-10_UI_Jurak_2007.csv",
    }
    assert out["montage"]["electrode_pairs"] == [["Fz", "Cz"], ["P3", "P4"]]
    assert out["intensities"] == [1.0, 3.0] and out["intensities_from"] == "given"
    # A net the run is already mapped to is read, not re-mapped ("GSN-HydroCel-185" == ".csv").
    asked.clear()
    assert (
        resolve(eeg_net="GSN-HydroCel-185")["montage"]["electrode_pairs"]
        == MAPPED["pairs"]
    )
    assert asked == {}


def test_no_run_and_unknown_run_are_errors(runs):
    with pytest.raises(ValueError, match="no finished flex-search run"):
        resolve()
    runs.append(run("only", "2026-10-07"))
    with pytest.raises(ValueError, match="only"):
        resolve(flex_run="other")
    assert resolve()["intensities"] == [
        1.0,
        1.0,
    ]  # no manifest current: 1 mA per channel
