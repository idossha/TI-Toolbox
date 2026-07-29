"""TI/mTI simulation engine.

This package implements temporal interference (TI) and multi-channel
temporal interference (mTI) brain stimulation simulations.  It wraps
the SimNIBS finite-element solver, providing electrode configuration,
field computation, and BIDS-compliant output organization.

Public API
----------
BaseSimulation
    Abstract base class for TI/mTI simulation pipelines.
SimulationConfig
    Dataclass holding all parameters for a simulation run.
Montage
    Dataclass describing a named electrode montage.
SimulationMode
    Enum distinguishing TI (2-pair) from mTI (4+-pair) mode.
parse_intensities
    Parse a comma-separated intensity string into a float list.
run_simulation
    Execute simulations for every montage in a configuration.
load_montages
    Load named montages from the project's ``montage_list.json``.
list_montage_names
    List all montage names defined under an EEG net.
load_montage_data
    Load the full ``montage_list.json`` as a dict.
save_montage_data
    Write a montage dict to ``montage_list.json``.
ensure_montage_file
    Return (and optionally create) the path to ``montage_list.json``.
upsert_montage
    Insert or update a montage definition in ``montage_list.json``.

See Also
--------
tit.sim.config : Configuration dataclasses and enums.
tit.sim.utils : Orchestration, montage I/O, and post-processing helpers.
tit.sim.TI : 2-pair TI simulation implementation.
tit.sim.mTI : N-pair mTI simulation implementation.
tit.opt : Optimization modules that consume simulation results.
tit.analyzer : Field analysis applied to simulation outputs.
"""

from tit.sim.base import BaseSimulation
from tit.sim.config import (
    SimulationConfig,
    Montage,
    SimulationMode,
    parse_intensities,
)
from tit.sim.utils import (
    run_simulation,
    load_montages,
    list_montage_names,
    load_montage_data,
    save_montage_data,
    ensure_montage_file,
    upsert_montage,
)

__all__ = [
    "BaseSimulation",
    "SimulationConfig",
    "Montage",
    "SimulationMode",
    "parse_intensities",
    "run_simulation",
    "load_montages",
    "list_montage_names",
    "load_montage_data",
    "save_montage_data",
    "ensure_montage_file",
    "upsert_montage",
]
