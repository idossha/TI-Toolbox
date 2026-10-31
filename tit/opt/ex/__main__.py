"""Entry point: simnibs_python -m tit.opt.ex config.json"""

import json
import logging
import sys

from tit.config_io import deserialize_config
from tit.jobs import locks
from tit.opt.config import ExConfig
from tit.opt.ex.ex import run_ex_search


def _make_stdout_logger() -> logging.Logger:
    """Attach a stdout handler so log messages are captured by BaseProcessThread."""
    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.opt.ex_search")
    return logging.getLogger("tit.opt.ex_search")


def main() -> None:
    """Run exhaustive search from a JSON config passed as the first CLI argument."""
    _make_stdout_logger()
    from tit.jobs import events

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    config = deserialize_config(ExConfig, data)
    lock_cm = locks.hold_for_job("ex", [config.subject_id], data)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("ex_search")
            result = run_ex_search(config)
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
    except ValueError as exc:
        # Configuration errors -- an enumeration with zero candidates, say --
        # are the user's to fix, so report the reason plainly instead of a
        # traceback (the console shows this line verbatim).
        logging.getLogger("tit.opt.ex_search").error("ERROR: %s", exc)
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
