"""``SimulationConfig.tissue_conductivities`` reaches a real SimNIBS TDCS list, in-process.

Pins (2026-10-31, assessment item A1-1): ``BaseSimulation._add_electrode_pair`` builds each
channel's ``TDCSLIST`` with the config's per-tissue overrides (tissue number ``n`` sets
``cond[n - 1]``), whatever ``TISSUE_COND_<n>`` the process environment holds; every other tissue
keeps SimNIBS's ``standard_cond()`` value. Before, only ``python -m tit.sim`` applied the
overrides (through environment variables), so ``run_simulation()`` from a script used SimNIBS
defaults and a stale variable leaked into later runs.

Where the expected numbers come from: SimNIBS ``standard_cond()`` for the untouched tissues and
the values written in the script for the overridden ones. No FEM solve.

Reproduce in the image: ``simnibs_python -m pytest tests/numerical/test_sim_tissue_conductivities_real.py -q``
(the subprocess avoids the host conftest's SimNIBS mocks).
Deliberately elsewhere: the host half (``tests/test_sim_scripting_surface.py``).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = r"""
import os
from types import SimpleNamespace
from simnibs.simulation import sim_struct
from simnibs.utils.cond_utils import standard_cond
from tit.sim.base import BaseSimulation
from tit.sim.config import Montage, MontageMode, SimulationConfig

os.environ["TISSUE_COND_3"] = "9.0"  # a stale variable must change nothing
montage = Montage(name="m", mode=MontageMode.NET,
                  electrode_pairs=[("E1", "E2"), ("E3", "E4")], eeg_net="net.csv")
cfg = SimulationConfig(subject_id="X", montages=[montage],
                       tissue_conductivities={2: 0.4, 1: 0.2})
stub = SimpleNamespace(config=cfg, montage=montage)
stub._apply_tissue_conductivities = lambda t: BaseSimulation._apply_tissue_conductivities(stub, t)
session = sim_struct.SESSION()
tdcs = BaseSimulation._add_electrode_pair(stub, session, ["E1", "E2"], 1.0)
std = [c.value for c in standard_cond()]
got = [c.value for c in tdcs.cond]
assert len(got) == len(std)
assert got[0] == 0.2 and got[1] == 0.4, got[:3]
assert got[2:] == std[2:], "untouched tissues keep SimNIBS's standard values"
"""


def test_config_overrides_reach_a_real_tdcs_list():
    root = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True, text=True
    )
    if probe.returncode:
        pytest.skip(
            "real SimNIBS unavailable; run this test with simnibs_python in the image"
        )
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=root, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
