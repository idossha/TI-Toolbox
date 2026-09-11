"""Resolve pipeline inputs from the exact completed producer jobs.

The server reads its resolve job's direct dependencies and their runner configs/events. Notebook
execution passes the same records directly. No directory enumeration chooses historical results.
Binding files are isolated by submitted group/run id, then merged at consumer admission.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

from tit.paths import is_valid_subject_id, is_within

__all__ = ["main", "producer_records", "resolve_from_producers", "runs_dir"]


#: ``--pipeline``/``--node`` become path components of the file this writes, so they are
#: names and nothing else. A traversal here wrote the binding file anywhere the container's
#: user could write (RUN-06); `tit.jobs.kinds.check_tool_args` refuses one before the job is
#: spawned, and this refuses it again for a direct `simnibs_python -m` invocation.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _checked_name(what: str, value: str) -> str:
    if not _SAFE_NAME.match(value or ""):
        raise SystemExit(
            f"[error] --{what} {value!r} must be a plain name "
            f"(letters, digits, '_', '-', '.', at most 64 characters)"
        )
    return value


def runs_dir(project_dir: str, pipeline: str) -> str:
    """``<project>/code/ti-toolbox/pipelines/runs/<pipeline>/``."""
    return os.path.join(
        project_dir,
        "code",
        "ti-toolbox",
        "pipelines",
        "runs",
        _checked_name("pipeline", pipeline),
    )


def producer_records(project_dir: str) -> tuple[list[dict], str]:
    """Read only this resolve job's direct dependencies, never historical project runs."""
    from tit.jobs.registry import spec_path, events_path, job_file_path

    job_id = os.environ.get("TIT_JOB_ID")
    if not job_id:
        raise ValueError("Pipeline resolution requires explicit producer results")
    with open(spec_path(project_dir, job_id), encoding="utf-8") as stream:
        own = json.load(stream)
    records = []
    for dependency in own.get("after", []):
        with open(spec_path(project_dir, dependency), encoding="utf-8") as stream:
            spec = json.load(stream)
        with open(
            job_file_path(project_dir, dependency, "config.json"), encoding="utf-8"
        ) as stream:
            config = json.load(stream)
        with open(events_path(project_dir, dependency), encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
        records.append(
            {
                "kind": spec["kind"],
                "subject_ids": spec["subject_ids"],
                "config": config,
                "events": events,
            }
        )
    return records, own.get("group_id") or job_id


def resolve_from_producers(
    pm, port: str, from_kind: str, subjects: list[str], records: list[dict]
) -> dict[str, list]:
    """Bind actual producer outputs through existing domain adapters, scoped per subject."""
    values = {}
    for subject in subjects:
        producers = [
            r for r in records if r["kind"] == from_kind and subject in r["subject_ids"]
        ]
        if not producers:
            raise ValueError(f"No {from_kind} producer results for {subject}")
        found = []
        for producer in producers:
            config = producer["config"]
            if port == "montages":
                if from_kind != "flex":
                    raise ValueError(
                        f"{from_kind} does not provide a supported montage binding"
                    )
                from tit.config_io import serialize_config
                from tit.sim.montage_sources import resolve_flex_montage

                outputs = [
                    e.get("outputs", {}).get("output_folder")
                    for e in producer["events"]
                    if e.get("type") == "result"
                ]
                outputs = [path for path in outputs if path]
                if len(outputs) != 1:
                    raise ValueError(
                        f"Expected one completed Flex output for {subject}"
                    )
                folder = os.path.realpath(outputs[0])
                if os.path.dirname(folder) != os.path.realpath(pm.flex_search(subject)):
                    raise ValueError(
                        "Flex montage binding requires an output in the subject's flex-search directory"
                    )
                montage = resolve_flex_montage(
                    pm, subject, os.path.basename(folder), "optimized"
                )
                serialized = serialize_config(montage)
                serialized.pop("project_dir", None)
                found.append(serialized)
            elif port == "simulation":
                found.extend(
                    m["name"]
                    for m in config.get("montages", [])
                    if isinstance(m, dict) and m.get("name")
                )
            elif port == "leadfield":
                found.extend(
                    e["outputs"]["leadfield_hdf"]
                    for e in producer["events"]
                    if e.get("type") == "result"
                    and e.get("outputs", {}).get("leadfield_hdf")
                )
            else:
                raise ValueError(f"Unsupported binding port {port!r}")
        if not found:
            raise ValueError(f"Producer supplied no {port} output for {subject}")
        if port in {"simulation", "leadfield"} and len(found) != 1:
            raise ValueError(
                f"{port} binding needs exactly one output per subject; {subject} has {len(found)}"
            )
        values[subject] = found
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pipeline", required=True, help="pipeline name (directory-safe)"
    )
    parser.add_argument("--node", required=True, help="consumer node id")
    parser.add_argument(
        "--port", required=True, choices=["montages", "leadfield", "simulation"]
    )
    parser.add_argument("--from-kind", default="", help="producer node kind")
    parser.add_argument("--subjects", default="", help="comma-separated subject ids")
    parser.add_argument(
        "--project-dir",
        default=None,
        help="project root; defaults to the bound PathManager (TI_PROJECT_DIR)",
    )
    args = parser.parse_args(argv)

    from tit import get_path_manager

    pm = get_path_manager(args.project_dir)
    project_dir = args.project_dir or pm.project_dir
    if not project_dir:
        print(
            "[error] no project directory bound; set TI_PROJECT_DIR or pass --project-dir"
        )
        return 2

    _checked_name("pipeline", args.pipeline)
    _checked_name("node", args.node)
    subjects = [s for s in (args.subjects or "").split(",") if s]
    for subject_id in subjects:
        if not is_valid_subject_id(subject_id):
            print(f"[error] invalid subject id {subject_id!r}")
            return 2
    records, run_id = producer_records(project_dir)
    values = resolve_from_producers(pm, args.port, args.from_kind, subjects, records)
    payload = {
        "node": args.node,
        "port": args.port,
        "from_kind": args.from_kind,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "values": values,
    }
    out_dir = runs_dir(project_dir, args.pipeline)
    out_path = os.path.join(out_dir, f"{args.node}.{args.port}.json")
    if not is_within(project_dir, out_path):
        print(f"[error] refusing to write {out_path!r}: outside {project_dir!r}")
        return 2
    from tit.jobs.bindings import binding_path

    out_path = binding_path(
        project_dir, os.path.relpath(out_path, project_dir), run_id=run_id
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"[info] wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
