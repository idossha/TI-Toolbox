"""Resolve one **dynamic** pipeline binding (plan §1-D, D3).

A pipeline edge whose value only exists after the upstream job ran -- an optimizer's montage name
(its run directory is named at run time by :meth:`tit.paths.PathManager.flex_search_run`), a
leadfield's ``.hdf5`` -- gets one of these planned between producer and consumer by
:func:`tit.pipeline.plan.plan_pipeline`.  It runs as an ordinary ``tools`` job under the pipeline's
own job group, so the scheduler stays the only executor and the binding is visible in Jobs as a
step of the pipeline rather than as hidden server magic.

It reads the producer's output directory and writes what it found to
``<project>/code/ti-toolbox/pipelines/runs/<pipeline>/<node>.<port>.json`` -- the path
:func:`tit.pipeline.plan.bindings_relpath` puts in the consumer's config, and
:func:`tit.jobs.bindings.merge_pipeline_bindings` reads back when the consumer is admitted::

    {"port": "montages", "node": "sim1", "from_kind": "flex",
     "resolved_at": "2026-09-05T...", "values": {"ernie": ["L_Insula_mean"]}}

Usage (the argv :func:`tit.pipeline.plan.plan_pipeline` builds)::

    simnibs_python -m tit.tools.pipeline_resolve --pipeline <name> --node <id> \\
        --port montages --from-kind flex --subjects ernie,101
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

from tit.paths import is_valid_subject_id, is_within

__all__ = [
    "main",
    "resolve_leadfield",
    "resolve_montages",
    "resolve_simulations",
    "runs_dir",
]


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
        project_dir, "code", "ti-toolbox", "pipelines", "runs", _checked_name("pipeline", pipeline)
    )


def resolve_montages(pm, subject_id: str, from_kind: str) -> list[str]:
    """The montage names *from_kind*'s search wrote for *subject_id*, newest run last.

    Each search kind writes one directory per run under its own root; the directory's basename
    **is** the montage name a Simulator consumes (``FlexResult.output_folder``'s basename, and the
    same convention for ``ex``/``mex``).
    """
    root = {
        "flex": pm.flex_search,
        "ex": pm.ex_search,
        "mex": pm.m_ex_search,
    }.get(from_kind)
    if root is None:
        return []
    directory = root(subject_id)
    if not os.path.isdir(directory):
        return []
    entries = [
        name
        for name in os.listdir(directory)
        if not name.startswith(".") and os.path.isdir(os.path.join(directory, name))
    ]
    entries.sort(key=lambda n: os.path.getmtime(os.path.join(directory, n)))
    return entries


def resolve_simulations(pm, subject_id: str) -> list[str]:
    """Simulation names that exist for *subject_id*, newest last -- one directory per run."""
    directory = pm.simulations(subject_id)
    if not os.path.isdir(directory):
        return []
    entries = [
        name
        for name in os.listdir(directory)
        if not name.startswith(".") and os.path.isdir(os.path.join(directory, name))
    ]
    entries.sort(key=lambda n: os.path.getmtime(os.path.join(directory, n)))
    return entries


def resolve_leadfield(pm, subject_id: str) -> list[str]:
    """Leadfield ``.hdf5`` files that exist for *subject_id*, newest last."""
    directory = pm.sub(subject_id)
    if not os.path.isdir(directory):
        return []
    hits = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.endswith(".hdf5")
    ]
    hits.sort(key=os.path.getmtime)
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", required=True, help="pipeline name (directory-safe)")
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
        print("[error] no project directory bound; set TI_PROJECT_DIR or pass --project-dir")
        return 2

    _checked_name("pipeline", args.pipeline)
    _checked_name("node", args.node)
    subjects = [s for s in (args.subjects or "").split(",") if s]
    for subject_id in subjects:
        if not is_valid_subject_id(subject_id):
            print(f"[error] invalid subject id {subject_id!r}")
            return 2
    values: dict[str, list[str]] = {}
    for subject_id in subjects:
        if args.port == "montages":
            values[subject_id] = resolve_montages(pm, subject_id, args.from_kind)
        elif args.port == "simulation":
            values[subject_id] = resolve_simulations(pm, subject_id)
        else:
            values[subject_id] = resolve_leadfield(pm, subject_id)
        print(f"[info] {subject_id}: {args.port} -> {values[subject_id]}")

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
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"[info] wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
