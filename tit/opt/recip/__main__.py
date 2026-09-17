"""Entry point: simnibs_python -m tit.opt.recip config.json"""

import json
import logging
import os
import sys
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.opt.config import RecipConfig
from tit.opt.recip.recip import run_recip_search


def _make_stdout_logger() -> logging.Logger:
    """Attach a stdout handler so log messages are captured by the job runner."""
    from tit.logger import add_stream_handler, setup_logging

    setup_logging()
    add_stream_handler("tit.opt.recip_search")
    return logging.getLogger("tit.opt.recip_search")


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
    """Run reciprocity search from a JSON config passed as the first CLI argument."""
    _make_stdout_logger()
    from tit.jobs import events

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    config = deserialize_config(RecipConfig, data)
    lock_cm = _hold_locks("recip", [config.subject_id], data)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("recip_search")
            result = run_recip_search(config)
            if result.results_csv:
                events.emit_artifact(result.results_csv, kind="csv", label="candidates")
            if result.config_json:
                events.emit_artifact(result.config_json, kind="json", label="summary")
            exit_code = 0 if result.success else 1
            events.emit_result(
                {
                    "success": result.success,
                    "output_dir": result.output_dir,
                    "n_candidates": result.n_candidates,
                    "best": result.best,
                }
            )
    except ValueError as exc:
        # Configuration errors -- an empty target, say -- are the user's to
        # fix, so report the reason plainly instead of a traceback.
        logging.getLogger("tit.opt.recip_search").error("ERROR: %s", exc)
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
