"""Standalone notebook adapter for the canvas's existing plans and JSON runners.

No scheduling or scientific recipes: the caller walks the plan in dependency order and this
adapter checks completed prerequisites, invokes one existing runner, and returns its events.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tit.jobs.bindings import binding_path, merge_pipeline_bindings
from tit.jobs.spec import PlannedJob


def execute_job(
    job: PlannedJob,
    completed: dict[str, dict[str, Any]],
    *,
    project_dir: str,
    run_id: str,
) -> dict[str, Any]:
    """Execute one planned job using the same configs and binding adapter as the job server."""
    from tit import get_path_manager
    from tit.jobs.kinds import command_for
    from tit.tools.pipeline_resolve import resolve_from_producers

    if job.label in completed:
        raise ValueError(
            "This job already completed; rerun Setup to start a fresh pipeline run"
        )
    missing = [label for label in job.after_labels if label not in completed]
    if missing:
        raise ValueError(f"Run prerequisites first: {', '.join(missing)}")
    config = copy.deepcopy(job.config)
    config["project_dir"] = project_dir
    if job.kind == "tools" and config.get("module") == "tit.tools.pipeline_resolve":
        args = config["args"]
        options = dict(zip(args[::2], args[1::2]))
        values = resolve_from_producers(
            get_path_manager(project_dir),
            options["--port"],
            options["--from-kind"],
            options["--subjects"].split(","),
            [completed[label] for label in job.after_labels],
        )
        from tit.pipeline.plan import bindings_relpath

        path = Path(
            binding_path(
                project_dir,
                bindings_relpath(
                    options["--pipeline"], options["--node"], options["--port"]
                ),
                run_id=run_id,
            )
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"port": options["--port"], "values": values}), encoding="utf-8"
        )
        events = []
    else:
        merge_pipeline_bindings(config, project_dir, run_id=run_id)
        with tempfile.TemporaryDirectory(prefix="tit-notebook-") as directory:
            config_path = Path(directory) / "config.json"
            events_path = Path(directory) / "events.jsonl"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            env = dict(os.environ)
            for key in (
                "TIT_JOB_ID",
                "TIT_JOB_KIND",
                "TIT_JOB_SUBJECT_IDS",
                "TIT_LOCK_KEYS",
            ):
                env.pop(key, None)
            env.update(
                TIT_EVENTS_FILE=str(events_path),
                TIT_INTERFACE="notebook",
                TIT_JOB_OVERWRITE="1" if job.overwrite else "0",
            )
            subprocess.run(
                command_for(
                    job.kind, config, str(config_path), project_dir=project_dir
                ),
                env=env,
                check=True,
            )
            events = (
                [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if events_path.exists()
                else []
            )
    record = {
        "kind": job.kind,
        "subject_ids": list(job.subject_ids),
        "config": config,
        "events": events,
    }
    completed[job.label] = record
    return record
