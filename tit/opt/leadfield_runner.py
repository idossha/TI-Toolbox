"""Entry point: simnibs_python -m tit.opt.leadfield_runner spec.json

Thin JSON-config runner around :class:`tit.opt.leadfield.LeadfieldGenerator`,
following the same shape as the other ``tit.<module>.__main__`` entry points
(:mod:`tit.sim.__main__`, :mod:`tit.opt.ex.__main__`, ...): read the spec,
initialise :class:`~tit.paths.PathManager`, build the typed config via
:func:`tit.config_io.deserialize_config`, run, exit ``0``/non-zero.

This module does not change :class:`~tit.opt.leadfield.LeadfieldGenerator`
(not owned by this track) -- see :class:`tit.opt.leadfield_config.LeadfieldConfig`'s
Notes for the two gaps that follow from that: ``tissues`` is accepted here
and passed through to ``generate()``, but ``generate()`` itself currently
discards its ``tissues`` argument and always uses ``[1, 2]``; there is no way
to set ``interpolation`` at all. Both are pre-existing bugs in
``tit/opt/leadfield.py``, not something this runner works around.

``overwrite`` is enforced here (the generator itself has no such parameter):
when ``False`` and a leadfield for ``(subject_id, eeg_net)`` already exists
(per ``LeadfieldGenerator.list_leadfields``), generation is skipped and the
existing path is reported instead of recomputing.
"""

from __future__ import annotations

import json
import sys

from tit.config_io import deserialize_config
from tit.opt.leadfield import LeadfieldGenerator
from tit.opt.leadfield_config import LeadfieldConfig
from tit.paths import get_path_manager


def main() -> None:
    """Run leadfield generation from a JSON config passed as the first CLI argument."""
    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.opt.leadfield")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))
    config = deserialize_config(LeadfieldConfig, data)

    generator = LeadfieldGenerator(config.subject_id, electrode_cap=config.eeg_net)

    if not config.overwrite:
        existing_nets = {net for net, _, _ in generator.list_leadfields()}
        if config.eeg_net in existing_nets:
            print(
                f"Leadfield already exists for {config.subject_id}/{config.eeg_net}; "
                "skipping (overwrite=False)"
            )
            sys.exit(0)

    hdf5_path = generator.generate(tissues=config.tissues)
    print(f"Leadfield ready: {hdf5_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
