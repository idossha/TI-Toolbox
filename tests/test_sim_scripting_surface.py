"""The scripting surface of ``tit.sim`` does what its config says, in-process too.

Pins (2026-10-31, assessment items A1-1, A1-6, A1-9):

* ``SimulationConfig.tissue_conductivities`` reaches the SimNIBS TDCS list from the config
  itself, so ``run_simulation()`` called from a script or notebook uses it; a
  ``TISSUE_COND_<n>`` variable left in the environment changes nothing, and ``config.json``
  records the overrides the config applied.
* ``run_simulation`` removes the per-run log file handlers it attached.
* ``SimulationConfig`` refuses an electrode shape SimNIBS has no meaning for here and
  non-positive or non-finite geometry.

Expected values are written out from the inputs of each test: tissue 2 at 0.4 S/m sets
``cond[1]`` (SimNIBS tissue numbers are 1-based) and leaves every other entry alone.
The real-SimNIBS half of the conductivity claim is
``tests/numerical/test_sim_tissue_conductivities_real.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_sim_scripting_surface.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tit.sim.base import BaseSimulation
from tit.sim.config import Montage, MontageMode, SimulationConfig
from tit.sim.utils import create_simulation_config_file

NET = [("E1", "E2"), ("E3", "E4")]


def _montage():
    return Montage(
        name="m", mode=MontageMode.NET, electrode_pairs=NET, eeg_net="net.csv"
    )


def _tdcs(n=10):
    return SimpleNamespace(cond=[SimpleNamespace(value=-1.0) for _ in range(n)])


# -- A1-1: tissue conductivities come from the config ----------------------------------------


def test_config_overrides_reach_the_tdcs_list_in_process(monkeypatch):
    for key in [k for k in os.environ if k.startswith("TISSUE_COND_")]:
        monkeypatch.delenv(key)
    cfg = SimulationConfig(
        subject_id="X", montages=[_montage()], tissue_conductivities={2: 0.4, 10: 0.16}
    )
    tdcs = _tdcs()
    BaseSimulation._apply_tissue_conductivities(SimpleNamespace(config=cfg), tdcs)
    values = [c.value for c in tdcs.cond]
    assert values[1] == 0.4 and values[9] == 0.16
    assert [v for i, v in enumerate(values) if i not in (1, 9)] == [-1.0] * 8


def test_a_stale_environment_variable_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("TISSUE_COND_3", "1.654")
    cfg = SimulationConfig(subject_id="X", montages=[_montage()])
    tdcs = _tdcs()
    BaseSimulation._apply_tissue_conductivities(SimpleNamespace(config=cfg), tdcs)
    assert [c.value for c in tdcs.cond] == [-1.0] * 10
    create_simulation_config_file(
        cfg, cfg.montages[0], str(tmp_path), logging.getLogger("t")
    )
    written = json.loads((tmp_path / "config.json").read_text())
    assert written["tissue_conductivities"] == {}


def test_config_json_records_the_configs_overrides(monkeypatch, tmp_path):
    for key in [k for k in os.environ if k.startswith("TISSUE_COND_")]:
        monkeypatch.delenv(key)
    cfg = SimulationConfig(
        subject_id="X", montages=[_montage()], tissue_conductivities={2: 0.4}
    )
    create_simulation_config_file(
        cfg, cfg.montages[0], str(tmp_path), logging.getLogger("t")
    )
    written = json.loads((tmp_path / "config.json").read_text())
    assert written["tissue_conductivities"] == {"2": 0.4}


def test_tissue_number_zero_is_refused():
    # cond[0 - 1] would silently set the last tissue.
    with pytest.raises(ValueError, match="tissue"):
        SimulationConfig(subject_id="X", montages=[], tissue_conductivities={0: 0.3})


# -- A1-9: electrode geometry ----------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"electrode_shape": "circle"},
        {"electrode_dimensions": [-8.0, 8.0]},
        {"electrode_dimensions": [8.0]},
        {"electrode_dimensions": [float("nan"), 8.0]},
        {"gel_thickness": -1.0},
        {"rubber_thickness": 0.0},
        {"gel_thickness": float("inf")},
    ],
)
def test_impossible_electrode_geometry_is_refused(change):
    with pytest.raises(ValueError):
        SimulationConfig(subject_id="X", montages=[], **change)


def test_rect_electrodes_with_unequal_sides_are_accepted():
    cfg = SimulationConfig(
        subject_id="X",
        montages=[],
        electrode_shape="rect",
        electrode_dimensions=[12.0, 6.0],
    )
    assert cfg.electrode_dimensions == [12.0, 6.0]


# -- A1-6: per-run log handlers are removed ---------------------------------------------------


def test_run_simulation_removes_its_file_handlers(tmp_path):
    from tit.sim import utils as sim_utils

    cfg = SimulationConfig(subject_id="X", montages=[])
    pm = SimpleNamespace(
        logs=lambda sid: str(tmp_path / "logs"),
        simulations=lambda sid: str(tmp_path / "sims"),
    )
    before = {
        name: list(logging.getLogger(name).handlers) for name in ("tit.sim", "simnibs")
    }
    with patch.object(sim_utils, "get_path_manager", return_value=pm):
        sim_utils._run_simulation_inner(cfg, None, None)
    for name, handlers in before.items():
        assert logging.getLogger(name).handlers == handlers
