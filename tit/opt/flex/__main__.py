"""Entry point: simnibs_python -m tit.opt.flex config.json

``FlexConfig.mode`` (``"flex"``, ``"flex_adaptive"``, or ``"flex_pareto"`` -- set by the
submitting job's kind, ``tit.jobs.kinds.MODULE_FOR_KIND`` maps all three to this module)
selects which of :func:`~tit.opt.flex.flex.run_flex_search`,
:func:`~tit.opt.flex.drivers.run_adaptive_focality`, or
:func:`~tit.opt.flex.drivers.run_pareto_sweep` actually runs.
"""

import json
import os
import sys
from contextlib import nullcontext

from tit.config_io import deserialize_config
from tit.opt.config import FlexConfig
from tit.opt.flex.flex import run_flex_search
from tit.opt.flex.drivers import run_adaptive_focality, run_pareto_sweep


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
    """Run flex search from a JSON config passed as the first CLI argument."""
    from tit.logger import setup_logging, add_stream_handler
    from tit.jobs import events

    setup_logging()
    add_stream_handler("tit.opt.flex")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    config = deserialize_config(FlexConfig, data)
    lock_cm = _hold_locks(config.mode.value, [config.subject_id], data)

    driver = {
        FlexConfig.Mode.FLEX: run_flex_search,
        FlexConfig.Mode.FLEX_ADAPTIVE: run_adaptive_focality,
        FlexConfig.Mode.FLEX_PARETO: run_pareto_sweep,
    }[config.mode]

    exit_code = 1
    try:
        with lock_cm:
            if config.mode is FlexConfig.Mode.FLEX:
                events.emit_stage("flex_search")
            result = driver(config)
            if result.output_folder:
                events.emit_artifact(
                    result.output_folder, kind="dir", label="output_folder"
                )
            exit_code = 0 if result.success else 1
            events.emit_result(
                {
                    "success": result.success,
                    "output_folder": result.output_folder,
                    "best_value": result.best_value,
                    "best_run_index": result.best_run_index,
                }
            )
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
