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
import os
from typing import Any

__all__ = ["BINDINGS_KEY", "merge_pipeline_bindings"]

#: Private key in a job's ``config``.  Never reaches a config dataclass: ``tit.pipeline.plan``
#: adds it after the config round-trips, and this module removes it before the runner's
#: ``config.json`` is written.
BINDINGS_KEY = "_pipeline_bindings"

#: Ports whose resolved value is a single name, not a list.
_SCALAR_PORTS = frozenset({"leadfield", "simulation"})


def _values_for(payload: dict[str, Any], subject_ids: list[str]) -> list[str]:
    """The resolved names for *subject_ids*, in the file's own order, de-duplicated."""
    found = payload.get("values")
    if not isinstance(found, dict):
        return []
    out: list[str] = []
    for subject_id in subject_ids or list(found):
        for value in found.get(subject_id) or []:
            if isinstance(value, str) and value not in out:
                out.append(value)
    return out


def merge_pipeline_bindings(
    payload: dict[str, Any], project_dir: str | None
) -> dict[str, Any]:
    """Pop :data:`BINDINGS_KEY` out of *payload* and write each resolved value into its field.

    Returns the same dict, mutated, so a caller can use it inline.  A descriptor whose file is
    missing or unreadable leaves the field exactly as the canvas set it -- an empty list or an
    empty string, which is what the config dataclass was constructed with -- so a resolve step
    that found nothing degrades to the honest "you still have to set this", never to a crash in
    the manager's admission path.

    A scalar port (``leadfield``, ``simulation``) takes the **newest** name the resolve step
    recorded (its files are written newest-last); a list port takes them all.
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
        path = os.path.join(project_dir, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                found = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(found, dict):
            continue
        subject_ids = descriptor.get("subject_ids")
        values = _values_for(
            found, subject_ids if isinstance(subject_ids, list) else []
        )
        if not values:
            continue
        if descriptor.get("port") in _SCALAR_PORTS:
            payload[field] = values[-1]
        else:
            payload[field] = values
    return payload
