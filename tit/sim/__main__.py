"""Entry point: simnibs_python -m tit.sim config.json"""


import json
import logging
import sys

from tit.paths import get_path_manager
from tit.sim.config import Montage, SimulationConfig
from tit.sim.utils import run_simulation


def _build_montage(data: dict) -> Montage:
    data = dict(data)
    data.pop("_type", None)
    pairs = [tuple(p) for p in data.pop("electrode_pairs")]
    mode = Montage.Mode(data.pop("mode"))
    return Montage(
        name=data.pop("name"),
        mode=mode,
        electrode_pairs=pairs,
        eeg_net=data.pop("eeg_net", None),
    )


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

    config = SimulationConfig(
        subject_id=data["subject_id"],
        project_dir=data["project_dir"],
        montages=montages,
        conductivity=data.get("conductivity", "scalar"),
        intensities=data.get("intensities", [1.0, 1.0]),
        electrode_shape=data.get("electrode_shape", "ellipse"),
        electrode_dimensions=data.get("electrode_dimensions", [8.0, 8.0]),
        gel_thickness=data.get("gel_thickness", 4.0),
        rubber_thickness=data.get("rubber_thickness", 2.0),
        map_to_surf=data.get("map_to_surf", True),
        map_to_vol=data.get("map_to_vol", False),
        map_to_mni=data.get("map_to_mni", False),
        map_to_fsavg=data.get("map_to_fsavg", False),
        open_in_gmsh=data.get("open_in_gmsh", False),
        tissues_in_niftis=data.get("tissues_in_niftis", "all"),
        aniso_maxratio=data.get("aniso_maxratio", 10.0),
        aniso_maxcond=data.get("aniso_maxcond", 2.0),
    )

    logger = _make_stdout_logger()
    results = run_simulation(config, logger=logger)
    failed = [r for r in results if r.get("status") == "failed"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
