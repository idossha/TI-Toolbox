"""Entry point: simnibs_python -m tit.opt.mex config.json"""

import json
import logging
import os
import sys
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.opt.config import MExConfig
from tit.opt.mex.mex import run_m_ex_search


def _make_stdout_logger() -> logging.Logger:
    """Attach a stdout handler so log messages are captured by BaseProcessThread."""
    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.opt.m_ex_search")
    return logging.getLogger("tit.opt.m_ex_search")


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


def main() -> None:
    """Run multipolar exhaustive search from a JSON config passed as the first CLI argument."""
    _make_stdout_logger()
    from tit.jobs import events

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    config = deserialize_config(MExConfig, data)
    lock_cm = _hold_locks("mex", [config.subject_id], data)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("mex_search")
            result = run_m_ex_search(config)
            if result.results_csv:
                events.emit_artifact(result.results_csv, kind="csv", label="results")
            if result.config_json:
                events.emit_artifact(result.config_json, kind="json", label="config")
            exit_code = 0 if result.success else 1
            events.emit_result(
                {
                    "success": result.success,
                    "output_dir": result.output_dir,
                    "n_combinations": result.n_combinations,
                }
            )
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
