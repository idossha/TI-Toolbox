"""Entry point: simnibs_python -m tit.stats config.json

Reports its outputs through the same ``tit.jobs.events`` contract the analyzer uses:
``run_group_comparison``/``run_correlation`` decide their own output directory (under
``derivatives/ti-toolbox/stats/<mode>/<analysis_name>/``) and write ~9 files into it --
NIfTI maps, the permutation plots, ``analysis_summary.txt``, the run log -- so the
runner lists what landed there rather than restating a filename list the science code
owns. Before this, a finished ``stats`` job reported ``artifacts: []`` and the Results
view had nothing to link (job ``60727ba738144204``).
"""

import json
import os
import sys
import time
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.stats.config import (
    CorrelationConfig,
    GroupComparisonConfig,
)


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job."""
    from tit.paths import get_path_manager

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


def _emit_output_artifacts(output_dir, started: float) -> None:
    """List the files the analysis wrote (it chooses its own directory).

    Bookkeeping must never fail a finished run, and *output_dir* is whatever the
    result object carries -- a non-string (a test double, a result from a partial
    run) is simply nothing to list.
    """
    from tit.jobs import events

    if not isinstance(output_dir, str):
        return
    try:
        events.emit_new_artifacts(output_dir, started)
    except Exception as exc:  # noqa: BLE001 - never fail a finished run
        print(f"artifact listing skipped: {exc}", flush=True)


def main() -> None:
    """Run statistical analysis from a JSON config passed as the first CLI argument."""
    from tit.logger import add_stream_handler, setup_logging
    from tit.jobs import events

    setup_logging("INFO")
    add_stream_handler("tit.stats")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    mode = data.pop("mode", "group_comparison")
    config_cls = CorrelationConfig if mode == "correlation" else GroupComparisonConfig
    config = deserialize_config(config_cls, data)
    # `mode` goes back in for the lock request only: `tit.jobs.locks.keys_for("stats", ...)`
    # reads it off the request dict to build `project:stats:<mode>/<analysis_name>`, so popping
    # it first would file every correlation run under the group_comparison key.
    lock_cm = _hold_locks("stats", [], {**data, "mode": mode})

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage(mode)
            started = time.time()
            if mode == "correlation":
                exit_code = _run_correlation(config, started)
            else:
                exit_code = _run_group_comparison(config, started)
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


def _run_group_comparison(config: GroupComparisonConfig, started: float = 0.0) -> int:
    from tit.jobs import events
    from tit.stats.permutation import run_group_comparison

    result = run_group_comparison(config)
    _emit_output_artifacts(result.output_dir, started)
    events.emit_result(
        {
            "success": result.success,
            "n_significant_clusters": result.n_significant_clusters,
            "output_dir": result.output_dir,
        }
    )
    return 0 if result.success else 1


def _run_correlation(config: CorrelationConfig, started: float = 0.0) -> int:
    from tit.jobs import events
    from tit.stats.permutation import run_correlation

    result = run_correlation(config)
    _emit_output_artifacts(result.output_dir, started)
    events.emit_result(
        {
            "success": result.success,
            "n_significant_clusters": result.n_significant_clusters,
            "output_dir": result.output_dir,
        }
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    main()
