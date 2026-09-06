"""On-disk job state (TODO.md §2.3): ``<project>/code/ti-toolbox/jobs/<id>/{spec.json,
status.json, events.jsonl, stdout.log}``.

Persisted inside the project (not a temp dir) so notebook users and a restarted server both see
the same jobs. Writes that must never leave a half-written file behind (``spec.json``,
``status.json``) go through a temp-file + :func:`os.replace`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from typing import Any

from tit.jobs.spec import JobSpec, JobStatus

logger = logging.getLogger(__name__)

SPEC_FILE = "spec.json"
STATUS_FILE = "status.json"
EVENTS_FILE = "events.jsonl"
STDOUT_FILE = "stdout.log"

DEFAULT_RETENTION_COUNT = 200
DEFAULT_RETENTION_DAYS = 30

#: Job records are internal server bookkeeping (spec.json/status.json/events.jsonl/stdout.log
#: per job), not a BIDS entity -- listed in the project's .bidsignore so bids-validator never
#: flags code/ti-toolbox/jobs/ the way it would flag an unrecognised data file.
BIDSIGNORE_LINE = "code/ti-toolbox/jobs/"


def jobs_root(project_dir: str) -> str:
    return os.path.join(project_dir, "code", "ti-toolbox", "jobs")


def ensure_bidsignore(project_dir: str) -> None:
    """Make sure *project_dir*'s ``.bidsignore`` lists :data:`BIDSIGNORE_LINE`.

    Idempotent: a no-op once the line is present. Creates ``.bidsignore`` if it doesn't exist
    yet; otherwise appends to whatever is already there without touching existing lines (same
    "users curate this file by hand" convention as :func:`tit.pre.utils.ensure_bidsignore`,
    which does the same for CT files -- kept separate here rather than imported so
    :mod:`tit.jobs.registry` never has to import :mod:`tit.pre`).
    """
    target = os.path.join(project_dir, ".bidsignore")
    try:
        with open(target, encoding="utf-8") as fh:
            existing = fh.read().splitlines()
    except OSError:
        existing = []
    if BIDSIGNORE_LINE in existing:
        return
    lines = [*existing, BIDSIGNORE_LINE] if existing else [BIDSIGNORE_LINE]
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def job_dir(project_dir: str, job_id: str) -> str:
    return os.path.join(jobs_root(project_dir), job_id)


def spec_path(project_dir: str, job_id: str) -> str:
    return os.path.join(job_dir(project_dir, job_id), SPEC_FILE)


def status_path(project_dir: str, job_id: str) -> str:
    return os.path.join(job_dir(project_dir, job_id), STATUS_FILE)


def events_path(project_dir: str, job_id: str) -> str:
    return os.path.join(job_dir(project_dir, job_id), EVENTS_FILE)


def stdout_path(project_dir: str, job_id: str) -> str:
    return os.path.join(job_dir(project_dir, job_id), STDOUT_FILE)


def _atomic_write_json(path: str, data: dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}-{time.monotonic_ns()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


class JobRegistry:
    """Filesystem operations for the job store of one project."""

    def __init__(self, project_dir: str) -> None:
        self.project_dir = project_dir
        root = jobs_root(project_dir)
        first_time = not os.path.isdir(root)
        os.makedirs(root, exist_ok=True)
        if first_time:
            ensure_bidsignore(project_dir)

    # -- create / persist ------------------------------------------------------------------

    def create(self, spec: JobSpec, status: JobStatus) -> None:
        os.makedirs(job_dir(self.project_dir, spec.id), exist_ok=True)
        self.write_spec(spec)
        self.write_status(status)
        # Touch the event/log files up front so tailers never race a not-yet-existing file.
        open(events_path(self.project_dir, spec.id), "a", encoding="utf-8").close()
        open(stdout_path(self.project_dir, spec.id), "a", encoding="utf-8").close()

    def write_spec(self, spec: JobSpec) -> None:
        _atomic_write_json(spec_path(self.project_dir, spec.id), spec.to_dict())

    def write_status(self, status: JobStatus) -> None:
        _atomic_write_json(status_path(self.project_dir, status.id), status.to_dict())

    # -- read --------------------------------------------------------------------------------

    def read_spec(self, job_id: str) -> JobSpec | None:
        try:
            with open(spec_path(self.project_dir, job_id), encoding="utf-8") as fh:
                return JobSpec.from_dict(json.load(fh))
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def read_status(self, job_id: str) -> JobStatus | None:
        try:
            with open(status_path(self.project_dir, job_id), encoding="utf-8") as fh:
                return JobStatus.from_dict(json.load(fh))
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def list_ids(self) -> list[str]:
        try:
            return [
                name
                for name in os.listdir(jobs_root(self.project_dir))
                if name != ".locks"
                and os.path.isfile(spec_path(self.project_dir, name))
            ]
        except OSError:
            return []

    def read_log_tail(self, job_id: str, tail: int | None = None) -> str:
        path = stdout_path(self.project_dir, job_id)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                if tail is None:
                    return fh.read()
                lines = fh.readlines()
                return "".join(lines[-tail:])
        except OSError:
            return ""

    # -- delete / retention ------------------------------------------------------------------

    def delete(self, job_id: str) -> bool:
        path = job_dir(self.project_dir, job_id)
        if not os.path.isdir(path):
            return False
        shutil.rmtree(path, ignore_errors=True)
        return True

    def prune(
        self,
        *,
        keep_count: int = DEFAULT_RETENTION_COUNT,
        keep_days: float = DEFAULT_RETENTION_DAYS,
        now: float | None = None,
    ) -> list[str]:
        """Drop old, terminal jobs beyond *keep_count* / *keep_days*. Returns removed ids.

        Never removes a job that is not in a terminal state (queued/running survive regardless
        of age — a long-lived job should never disappear out from under it).
        """
        from tit.jobs.spec import (
            TERMINAL_STATES,
        )  # local import: avoid a cycle at module load

        now = now if now is not None else time.time()
        cutoff = now - keep_days * 86400
        records: list[tuple[str, JobStatus]] = []
        for job_id in self.list_ids():
            status = self.read_status(job_id)
            if status is not None:
                records.append((job_id, status))
        terminal = [(jid, st) for jid, st in records if st.state in TERMINAL_STATES]
        terminal.sort(key=lambda pair: pair[1].created_at)  # oldest first

        removed: list[str] = []
        # Age-based
        for job_id, status in terminal:
            finished = status.finished_at or status.created_at
            try:
                # created_at/finished_at are ISO-8601; string compare works for same-format
                # timestamps, but be defensive and just compare via time.time() fallback.
                import datetime as _dt

                ts = _dt.datetime.fromisoformat(finished).timestamp()
            except ValueError:
                ts = now
            if ts < cutoff:
                removed.append(job_id)

        # Count-based: beyond keep_count oldest terminal jobs (not already marked)
        remaining_terminal = [jid for jid, _ in terminal if jid not in removed]
        overflow = len(remaining_terminal) - keep_count
        if overflow > 0:
            removed.extend(remaining_terminal[:overflow])

        for job_id in removed:
            self.delete(job_id)
        if removed:
            logger.info("job registry: pruned %d old job(s)", len(removed))
        return removed
