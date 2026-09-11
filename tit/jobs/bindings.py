"""Late-bound config values: what a job could only learn after another job ran.

A pipeline edge whose value is named at run time -- an optimizer's montage directory, a
leadfield ``.hdf5`` -- gets a small ``tools`` job (:mod:`tit.tools.pipeline_resolve`) planned
between producer and consumer (``tit.pipeline.plan``, D3).  That step writes what it found to a
file whose path is a pure function of the pipeline name, the consumer node and the port, so the
consumer can name the file *before* it exists.

This module is the other half: the consumer carries a list of descriptors under
:data:`BINDINGS_KEY`, and :meth:`tit.jobs.manager.JobManager._runner_config_path` calls
:func:`merge_pipeline_bindings` when it writes the runner's ``config.json`` -- which happens at
*admission*, i.e. after every job the consumer waits on has finished, which is exactly when the
file exists.

It lives under ``tit.jobs`` rather than ``tit.pipeline`` to keep the import direction one-way:
``tit.pipeline`` already imports ``tit.jobs.spec``, and the job manager must not import a
pipeline module to run an ordinary job.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["BINDINGS_KEY", "merge_pipeline_bindings"]

#: Private key in a job's ``config``.  Never reaches a config dataclass: ``tit.pipeline.plan``
#: adds it after the config round-trips, and this module removes it before the runner's
#: ``config.json`` is written.
BINDINGS_KEY = "_pipeline_bindings"

#: Ports whose resolved value is a single name, not a list.
_SCALAR_PORTS = frozenset({"leadfield", "simulation"})


def _values_for(payload: dict[str, Any], subject_ids: list[str]) -> list[Any]:
    """The resolved names for *subject_ids*, in the file's own order, de-duplicated."""
    found = payload.get("values")
    if not isinstance(found, dict):
        return []
    out: list[Any] = []
    for subject_id in subject_ids or list(found):
        for value in found.get(subject_id) or []:
            if isinstance(value, (str, dict)) and value not in out:
                out.append(value)
    return out


def merge_pipeline_bindings(
    payload: dict[str, Any], project_dir: str | None, *, run_id: str | None = None
) -> dict[str, Any]:
    """Pop :data:`BINDINGS_KEY` out of *payload* and write each resolved value into its field.

    Missing, malformed or ambiguous producer output refuses admission. A consumer never falls
    back to stale canvas values or chooses the newest unrelated result. The optional run id
    scopes files to the same submitted graph invocation.
    """
    descriptors = payload.pop(BINDINGS_KEY, None)
    if not descriptors or not project_dir:
        return payload
    if not isinstance(descriptors, list):
        return payload
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            continue
        rel = descriptor.get("path")
        field = descriptor.get("field")
        if not isinstance(rel, str) or not isinstance(field, str):
            continue
        path = binding_path(project_dir, rel, run_id=run_id)
        try:
            with open(path, encoding="utf-8") as fh:
                found = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read pipeline binding {rel!r}: {exc}") from exc
        if not isinstance(found, dict):
            continue
        subject_ids = descriptor.get("subject_ids")
        values = _values_for(
            found, subject_ids if isinstance(subject_ids, list) else []
        )
        if not values:
            raise ValueError(
                f"Pipeline binding {rel!r} has no output for {subject_ids}"
            )
        if descriptor.get("port") in _SCALAR_PORTS:
            if len(values) != 1:
                raise ValueError(
                    f"Pipeline binding {rel!r} requires exactly one output, got {len(values)}"
                )
            payload[field] = values[-1]
        else:
            payload[field] = values
    return payload


def binding_path(project_dir: str, relative: str, *, run_id: str | None = None) -> str:
    """Resolve a binding inside its project, isolated to one submitted run when provided."""
    from pathlib import Path

    path = Path(project_dir) / relative
    if run_id:
        if not run_id.isalnum():
            raise ValueError("Pipeline run id must be alphanumeric")
        path = path.parent / run_id / path.name
    resolved = path.resolve()
    if not resolved.is_relative_to(Path(project_dir).resolve()):
        raise ValueError("Pipeline binding must remain inside the project")
    return str(resolved)
