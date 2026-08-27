"""Entry point: simnibs_python -m tit.opt.mex config.json"""

import json
import sys

from tit.opt.config import MExConfig
from tit.opt.mex.mex import run_m_ex_search

_ELECTRODE_BUILDERS = {
    "PoolElectrodes": MExConfig.PoolElectrodes,
    "BucketElectrodes": MExConfig.BucketElectrodes,
}


def _build_electrodes(data: dict):
    data = dict(data)
    electrode_type = data.pop("_type", None)
    if electrode_type and electrode_type in _ELECTRODE_BUILDERS:
        return _ELECTRODE_BUILDERS[electrode_type](**data)
    if "electrodes" in data:
        return MExConfig.PoolElectrodes(**data)
    return MExConfig.BucketElectrodes(**data)


def _build_channels(data):
    """Restore ``MExConfig.channels`` from JSON, where tuples become lists."""
    if data is None:
        return None
    return [(list(group_a), list(group_b)) for group_a, group_b in data]


def _make_stdout_logger() -> None:
    """Attach a stdout handler so log messages are captured by BaseProcessThread."""
    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.opt.m_ex_search")


def main() -> None:
    """Run multipolar exhaustive search from a JSON config passed as the first CLI argument."""
    _make_stdout_logger()

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    electrodes = _build_electrodes(data.pop("electrodes"))
    channels = _build_channels(data.pop("channels", None))
    config = MExConfig(electrodes=electrodes, channels=channels, **data)
    try:
        result = run_m_ex_search(config)
    except ValueError as exc:
        # Configuration errors (e.g. an enumeration with zero candidates)
        # are reported plainly so the GUI console shows the reason.
        import logging

        logging.getLogger("tit.opt.m_ex_search").error("ERROR: %s", exc)
        sys.exit(1)
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
