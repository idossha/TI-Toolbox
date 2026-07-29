"""Entry point: simnibs_python -m tit.opt.ex config.json"""

import json
import sys

from tit.opt.config import ExConfig
from tit.opt.ex.ex import run_ex_search

_ELECTRODE_BUILDERS = {
    "PoolElectrodes": ExConfig.PoolElectrodes,
    "BucketElectrodes": ExConfig.BucketElectrodes,
}


def _build_electrodes(data: dict):
    data = dict(data)
    electrode_type = data.pop("_type", None)
    if electrode_type and electrode_type in _ELECTRODE_BUILDERS:
        return _ELECTRODE_BUILDERS[electrode_type](**data)
    if "electrodes" in data:
        return ExConfig.PoolElectrodes(**data)
    return ExConfig.BucketElectrodes(**data)


def _make_stdout_logger() -> None:
    """Attach a stdout handler so log messages are captured by BaseProcessThread."""
    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.opt.ex_search")


def main() -> None:
    """Run exhaustive search from a JSON config passed as the first CLI argument."""
    _make_stdout_logger()

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    electrodes = _build_electrodes(data.pop("electrodes"))
    config = ExConfig(electrodes=electrodes, **data)
    result = run_ex_search(config)
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
