"""Entry point: simnibs_python -m tit.opt.leadfield_runner spec.json

Thin JSON-config runner around :class:`tit.opt.leadfield.LeadfieldGenerator`,
following the same shape as the other ``tit.<module>.__main__`` entry points
(:mod:`tit.sim.__main__`, :mod:`tit.opt.ex.__main__`, ...): read the spec,
initialise :class:`~tit.paths.PathManager`, build the typed config via
:func:`tit.config_io.deserialize_config`, run, exit ``0``/non-zero.

The electrode fields are passed through to ``generate()``, which places that
electrode at every cap position and records it in the leadfield's sidecar.
See :class:`tit.opt.leadfield_config.LeadfieldConfig`'s Notes for the two
gaps: ``generate()`` currently discards its ``tissues`` argument and always
uses ``[1, 2]``, and there is no way to set ``interpolation`` at all.

``overwrite`` is enforced here (the generator itself has no such parameter):
when ``False`` and a leadfield for ``(subject_id, eeg_net)`` already exists
(per ``LeadfieldGenerator.list_leadfields``), generation is skipped and the
existing path is reported instead of recomputing.

Like every other runner, it holds ``tit.jobs.locks.keys_for("leadfield", ...)``
while it works (so a bare ``simnibs_python -m`` run and the plan route see the
same holder the scheduler reserves) and writes an ``exit`` event in a
``finally``, so a restart can tell a finished job from a lost one.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.opt.leadfield import LeadfieldGenerator
from tit.opt.leadfield_config import LeadfieldConfig
from tit.paths import get_path_manager


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job."""
    try:
        from tit.jobs import locks
        from tit.jobs.runner import ENV_JOB_ID
    except ImportError:
        return nullcontext()
    job_id = os.environ.get(ENV_JOB_ID)
    if not job_id:
        return nullcontext()
    requests = locks.keys_for(kind, subject_ids, config_dict)
    return locks.hold(get_path_manager().project_dir, job_id, requests)


def main() -> None:
    """Run leadfield generation from a JSON config passed as the first CLI argument."""
    from tit.logger import setup_logging, add_stream_handler
    from tit.jobs import events

    setup_logging()
    add_stream_handler("tit.opt.leadfield")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))
    config = deserialize_config(LeadfieldConfig, data)
    lock_cm = _hold_locks("leadfield", [config.subject_id], data)

    exit_code = 1
    try:
        with lock_cm:
            _run(config)
            exit_code = 0
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


def _run(config: LeadfieldConfig) -> None:
    """Generate the leadfield, or report the existing one when ``overwrite`` is off."""
    from tit.jobs import events

    generator = LeadfieldGenerator(config.subject_id, electrode_cap=config.eeg_net)

    if not config.overwrite:
        existing = {net: path for net, path, _ in generator.list_leadfields()}
        if config.eeg_net in existing:
            print(
                f"Leadfield already exists for {config.subject_id}/{config.eeg_net}; "
                "skipping (overwrite=False)"
            )
            events.emit_artifact(
                existing[config.eeg_net], kind="hdf5", label="leadfield"
            )
            events.emit_result(
                {"leadfield_hdf": existing[config.eeg_net], "skipped": True}
            )
            return

    hdf5_path = generator.generate(
        tissues=config.tissues, electrode=config.electrode_record()
    )
    events.emit_artifact(str(hdf5_path), kind="hdf5", label="leadfield")
    events.emit_result({"leadfield_hdf": str(hdf5_path)})
    print(f"Leadfield ready: {hdf5_path}")


if __name__ == "__main__":
    main()
