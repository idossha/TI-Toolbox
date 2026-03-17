"""Entry point: simnibs_python -m tit.opt.ex config.json"""


import json
import sys

from tit.opt.config import (
    BucketElectrodes,
    ExConfig,
    ExCurrentConfig,
    PoolElectrodes,
)
from tit.opt.ex.ex import run_ex_search

_ELECTRODE_BUILDERS = {
    "PoolElectrodes": PoolElectrodes,
    "BucketElectrodes": BucketElectrodes,
}


def _build_electrodes(data: dict):
    data = dict(data)
    electrode_type = data.pop("_type", None)
    if electrode_type and electrode_type in _ELECTRODE_BUILDERS:
        return _ELECTRODE_BUILDERS[electrode_type](**data)
    if "electrodes" in data:
        return PoolElectrodes(**data)
    return BucketElectrodes(**data)


def _make_stdout_logger() -> None:
    """Attach a stdout handler so log messages are captured by BaseProcessThread."""
    from tit.logger import add_stream_handler

    add_stream_handler("tit.opt.ex_search")


def main() -> None:
    _make_stdout_logger()

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    electrodes = _build_electrodes(data.pop("electrodes"))
    currents_data = data.pop("currents", None)
    currents = ExCurrentConfig(**currents_data) if currents_data else ExCurrentConfig()

    config = ExConfig(electrodes=electrodes, currents=currents, **data)
    result = run_ex_search(config)
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
