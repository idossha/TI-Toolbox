"""Entry point: simnibs_python -m tit.sim config.json"""

import json
import os
import sys
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.paths import get_path_manager
from tit.sim.config import SimulationConfig
from tit.sim.utils import run_simulation


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job.

    ``tit.jobs.locks`` (B1) predicts the same keys server-side to admit or
    queue this job; holding them here too means a bare
    ``simnibs_python -m tit.<module> cfg.json`` from a second shell
    registers the same advisory lock a server-submitted job would.
    """
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
    """Run TI simulation from a JSON config passed as the first CLI argument."""
    from tit.logger import setup_logging, add_stream_handler
    from tit.jobs import events

    setup_logging()
    add_stream_handler("tit.sim")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))

    config = deserialize_config(SimulationConfig, data)
    lock_cm = _hold_locks("sim", [config.subject_id], data)

    # tit.sim.base.BaseSimulation._apply_tissue_conductivities reads TISSUE_COND_<n> from
    # the environment (a pre-existing mechanism, previously invisible to the job/config
    # system since nothing set these vars from a config field). Set them here so
    # SimulationConfig.tissue_conductivities actually reaches the simulation.
    if config.tissue_conductivities:
        for tissue_number, value in config.tissue_conductivities.items():
            os.environ[f"TISSUE_COND_{tissue_number}"] = str(value)

    total = len(config.montages)
    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("simulation", i=0, n=total)

            def _progress(idx: int, total_montages: int, name: str) -> None:
                events.emit_stage(name, i=idx, n=total_montages)
                events.emit_progress(
                    100.0 * idx / total_montages if total_montages else 100.0
                )

            results = run_simulation(
                config,
                progress_callback=_progress,
                overwrite=os.environ.get("TIT_JOB_OVERWRITE") == "1",
            )
            for r in results:
                mesh = r.get("output_mesh")
                if mesh:
                    events.emit_artifact(mesh, kind="mesh", label=r.get("montage_name"))
            failed = [r for r in results if r.get("status") == "failed"]
            exit_code = 1 if failed else 0
            events.emit_result({"n_montages": total, "n_failed": len(failed)})
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
