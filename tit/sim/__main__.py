"""Entry point: simnibs_python -m tit.sim config.json"""

from __future__ import annotations

import json
import logging
import sys

from tit.paths import get_path_manager
from tit.sim.config import (
    ConductivityType,
    ElectrodeConfig,
    IntensityConfig,
    LabelMontage,
    SimulationConfig,
    XYZMontage,
)
from tit.sim.utils import run_simulation


def _build_montage(data: dict):
    data = dict(data)
    data.pop("_type", None)
    pairs = [tuple(p) for p in data.pop("electrode_pairs")]
    is_xyz = data.pop("is_xyz", False)
    if is_xyz:
        return XYZMontage(electrode_pairs=pairs, **data)
    return LabelMontage(electrode_pairs=pairs, **data)


def _make_stdout_logger() -> logging.Logger:
    """Create a logger that writes to stdout (captured by BaseProcessThread)."""
    logger = logging.getLogger("tit.sim.subprocess")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def main() -> None:
    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data["project_dir"])

    montages_data = data.pop("montages")
    montages = [_build_montage(m) for m in montages_data]

    electrode = ElectrodeConfig(**data.pop("electrode"))
    intensities = IntensityConfig(**data.pop("intensities"))
    conductivity_type = ConductivityType(data.pop("conductivity_type"))

    config = SimulationConfig(
        conductivity_type=conductivity_type,
        intensities=intensities,
        electrode=electrode,
        **data,
    )

    logger = _make_stdout_logger()
    results = run_simulation(config, montages, logger=logger)
    failed = [r for r in results if r.get("status") == "failed"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
