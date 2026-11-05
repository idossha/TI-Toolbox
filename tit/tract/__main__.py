"""Entry point: ``simnibs_python -m tit.tract config.json``.

The config is a serialised :class:`tit.tract.config.TractConfig` (``project_dir`` injected
by :func:`tit.config_io.serialize_config`); its ``stages`` run in the order
track -> network -> assess -> target.
"""

import json
import os
import sys
import time

from tit.tract.config import STAGES, TractConfig


def _already_done(config: TractConfig, stage: str, tract_dir: str) -> bool:
    """Under ``skip_existing``: the track or network stage has nothing left to do."""
    if not config.skip_existing:
        return False
    if stage == "track":
        return os.path.isfile(os.path.join(tract_dir, "tractogram.trx"))
    if stage == "network" and os.path.isfile(os.path.join(tract_dir, "network.npz")):
        try:
            with open(os.path.join(tract_dir, "network.json")) as f:
                return json.load(f).get("atlas") == config.network.atlas
        except (OSError, ValueError):
            return False
    return False


def main() -> None:
    """Run the configured stages; exit 0 on success, 1 on the first failed stage."""
    from tit.config_io import deserialize_config
    from tit.jobs import events, locks
    from tit.logger import add_stream_handler, setup_logging
    from tit.paths import get_path_manager

    setup_logging("INFO")
    add_stream_handler("tit.tract")

    with open(sys.argv[1]) as f:
        data = json.load(f)
    pm = get_path_manager(data.pop("project_dir"))
    try:
        config = deserialize_config(TractConfig, data)
    except (TypeError, ValueError, KeyError) as exc:
        print(f"Invalid tract config: {exc}", file=sys.stderr)
        sys.exit(1)

    from tit.tract import run_assess, run_network, run_target, run_track

    sid = config.subject_id
    lock_cm = locks.hold_for_job("tract", [sid], data)
    runners = {
        "track": lambda: run_track(sid, config.track),
        "network": lambda: run_network(sid, config.network),
        "assess": lambda: run_assess(sid, config.assess),
        "target": lambda: run_target(sid, config.target, config.assess.step_mm),
    }
    exit_code = 1
    stage = "start"
    try:
        with lock_cm:
            for stage in (s for s in STAGES if s in config.stages):
                events.emit_stage(stage)
                if _already_done(config, stage, pm.tractography(sid)):
                    print(f"tract {stage}: sub-{sid} exists, skipped", flush=True)
                    continue
                t0 = time.time()
                print(f"tract {stage}: sub-{sid}", flush=True)
                runners[stage]()
                print(f"tract {stage}: done in {time.time() - t0:.0f} s", flush=True)
        exit_code = 0
    except Exception as exc:  # noqa: BLE001 - one line for the job log, then exit 1
        print(f"tract {stage} failed: {exc}", file=sys.stderr, flush=True)
        raise
    finally:
        events.emit_exit(exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
