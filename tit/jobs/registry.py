"""On-disk job state: ``<project>/code/ti-toolbox/jobs/<id>/{spec.json,
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
import stat
import time
from typing import Any

from tit.jobs.spec import JobSpec, JobStatus
from tit.paths import resolve_leaf_within

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


def _storage_path(project_dir: str, path: str) -> str:
    """Check resolved targets, retaining the final entry for replace/unlink semantics.

    Parent aliases are resolved, but replacing/deleting a final symlink must not
    become replacing/deleting its target; reads/appends still follow a checked
    final link (:func:`tit.paths.resolve_leaf_within`).
    """
    try:
        return resolve_leaf_within(project_dir, path)
    except ValueError as exc:
        raise PermissionError("Job storage path escapes the project directory") from exc


def _instant(stamp: Any) -> float | None:
    """POSIX time of an ISO-8601 *stamp*, ``None`` if unreadable.

    A naive stamp is UTC: every time the store writes is UTC (``tit.jobs.spec.utcnow_iso``), so
    reading one in the machine's local zone would shift retention by hours.
    """
    import datetime as _dt

    try:
        parsed = _dt.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.timestamp()


def expired(
    finished: list[tuple[str, str, str | None]],
    *,
    keep_count: int = DEFAULT_RETENTION_COUNT,
    keep_days: float = DEFAULT_RETENTION_DAYS,
    now: float | None = None,
) -> list[str]:
    """The retention rule for finished records: which of *finished* to drop.

    *finished* is ``(id, created_at, finished_at)`` per finished record (ISO-8601 times). A record
    finished more than *keep_days* ago goes, and so do the oldest beyond the newest *keep_count*.
    Shared by the job registry (:meth:`JobRegistry.prune`) and the agent proposals
    (:func:`tit.server.proposals.prune`), so both keep the same history.
    """
    now = now if now is not None else time.time()
    cutoff = now - keep_days * 86400

    def oldest_first(item: tuple[str, str, str | None]) -> tuple[int, float]:
        # By instant, not by string: "+05:00", "Z" and fractional seconds do not sort as
        # text. A created_at that cannot be read sorts first (oldest).
        created = _instant(item[1])
        return (0, 0.0) if created is None else (1, created)

    ordered = sorted(finished, key=oldest_first)
    removed: list[str] = []
    for record_id, created_at, finished_at in ordered:
        ts = _instant(finished_at or created_at)
        if ts is not None and ts < cutoff:
            removed.append(record_id)
    remaining = [item[0] for item in ordered if item[0] not in removed]
    overflow = len(remaining) - keep_count
    if overflow > 0:
        removed.extend(remaining[:overflow])
    return removed


def jobs_root(project_dir: str) -> str:
    return _storage_path(
        project_dir, os.path.join(project_dir, "code", "ti-toolbox", "jobs")
    )


def ensure_bidsignore(project_dir: str) -> None:
    """Make sure *project_dir*'s ``.bidsignore`` lists :data:`BIDSIGNORE_LINE`.

    Idempotent: a no-op once the line is present. Creates ``.bidsignore`` if it doesn't exist
    yet; otherwise appends to whatever is already there without touching existing lines (same
    "users curate this file by hand" convention as :func:`tit.pre.utils.ensure_bidsignore`,
    which does the same for CT files -- kept separate here rather than imported so
    :mod:`tit.jobs.registry` never has to import :mod:`tit.pre`).
    """
    target = _storage_path(project_dir, os.path.join(project_dir, ".bidsignore"))
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
    # Legacy ids need not be UUIDs, but a job id is always one directory entry.
    if not job_id or job_id in (".", "..") or "/" in job_id or "\\" in job_id:
        raise PermissionError("Job id must be a single directory name")
    return _storage_path(project_dir, os.path.join(jobs_root(project_dir), job_id))


def spec_path(project_dir: str, job_id: str) -> str:
    return job_file_path(project_dir, job_id, SPEC_FILE)


def status_path(project_dir: str, job_id: str) -> str:
    return job_file_path(project_dir, job_id, STATUS_FILE)


def events_path(project_dir: str, job_id: str) -> str:
    return job_file_path(project_dir, job_id, EVENTS_FILE)


def stdout_path(project_dir: str, job_id: str) -> str:
    return job_file_path(project_dir, job_id, STDOUT_FILE)


def job_file_path(project_dir: str, job_id: str, filename: str) -> str:
    """A metadata file whose existing symlinks stay within the project."""
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        raise PermissionError("Job metadata filename must be a single entry")
    return _storage_path(
        project_dir, os.path.join(job_dir(project_dir, job_id), filename)
    )


def _atomic_write_json(path: str, data: dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}-{time.monotonic_ns()}"
    with open(tmp, "x", encoding="utf-8") as fh:
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
        # Validate the whole record before creating anything: a linked event/log file
        # must not be discovered only after spec/status have already been persisted.
        for resolve in (spec_path, status_path, events_path, stdout_path):
            resolve(self.project_dir, spec.id)
        status_path(self.project_dir, status.id)
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
        """The job's ``spec.json``, or ``None`` when it is missing, unreadable or malformed."""
        return self._read(job_id, spec_path, JobSpec.from_dict)

    def read_status(self, job_id: str) -> JobStatus | None:
        """The job's ``status.json``, or ``None`` when it is missing, unreadable or malformed."""
        return self._read(job_id, status_path, JobStatus.from_dict)

    def _read(self, job_id: str, path_for: Any, parse: Any) -> Any:
        # One record of the wrong shape (a hand edit, a sync conflict) is skipped, never
        # allowed to raise into the manager's startup and leave the whole scheduler dead.
        try:
            path = path_for(self.project_dir, job_id)
            with open(path, encoding="utf-8") as fh:
                record = parse(json.load(fh))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            logger.warning("job %s: skipping unreadable record: %s", job_id, exc)
            return None
        if record.id != job_id:
            logger.warning(
                "job %s: skipping a record that names another job (%s)",
                job_id,
                record.id,
            )
            return None
        return record

    def list_ids(self) -> list[str]:
        try:
            names = os.listdir(jobs_root(self.project_dir))
        except OSError:
            return []
        valid = []
        for name in names:
            if name == ".locks":
                continue
            try:
                # Skip an unsafe record without hiding unrelated valid jobs on restart.
                for resolve in (spec_path, status_path, events_path, stdout_path):
                    resolve(self.project_dir, name)
                if os.path.isfile(spec_path(self.project_dir, name)):
                    valid.append(name)
            except OSError:
                continue
        return valid

    def read_log_tail(self, job_id: str, tail: int | None = None) -> str:
        try:
            path = stdout_path(self.project_dir, job_id)
            with open(path, encoding="utf-8", errors="replace") as fh:
                if tail is None:
                    return fh.read()
                lines = fh.readlines()
                return "".join(lines[-tail:])
        except OSError:
            return ""

    # -- delete / retention ------------------------------------------------------------------

    def delete(self, job_id: str) -> bool:
        path = os.path.abspath(job_dir(self.project_dir, job_id))
        root = os.path.realpath(jobs_root(self.project_dir))
        # Deletion must stay below the job store, not merely inside the project.
        if not path.startswith(root + os.sep):
            raise PermissionError("Job deletion path escapes the job store")
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(mode):
            os.unlink(path)
        elif stat.S_ISDIR(mode):
            shutil.rmtree(path)
        else:
            raise NotADirectoryError(path)
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

        finished: list[tuple[str, str, str | None]] = []
        for job_id in self.list_ids():
            status = self.read_status(job_id)
            if status is not None and status.state in TERMINAL_STATES:
                finished.append((job_id, status.created_at, status.finished_at))
        removed = expired(finished, keep_count=keep_count, keep_days=keep_days, now=now)

        for job_id in removed:
            self.delete(job_id)
        if removed:
            logger.info("job registry: pruned %d old job(s)", len(removed))
        return removed
