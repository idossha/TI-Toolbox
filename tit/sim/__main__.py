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
    MTIFieldMethod,
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
    from tit.logger import add_stream_handler

    logger = logging.getLogger("tit.sim.subprocess")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    add_stream_handler("tit.sim.subprocess")
    return logger


def main() -> None:
    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data["project_dir"])

    montages_data = data.pop("montages")
    montages = [_build_montage(m) for m in montages_data]

    electrode = ElectrodeConfig(**data.pop("electrode"))
    raw_intensities = data.pop("intensities")
    if "values" in raw_intensities:
        intensities = IntensityConfig(values=raw_intensities["values"])
    else:
        # Legacy format: {pair1: ..., pair2: ..., ...}
        vals = [raw_intensities[k] for k in sorted(raw_intensities.keys())]
        intensities = IntensityConfig(values=vals)
    conductivity_type = ConductivityType(data.pop("conductivity_type"))
    if "mti_field_methods" in data:
        data["mti_field_methods"] = [
            MTIFieldMethod(v) for v in data["mti_field_methods"]
        ]
    elif "mti_field_method" in data:
        data["mti_field_methods"] = [MTIFieldMethod(data.pop("mti_field_method"))]

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
