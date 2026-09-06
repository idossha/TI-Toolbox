"""Advisory, filesystem-based locks (TODO.md §2.4).

Keys are **held by the runner process itself** (``with tit.jobs.locks.hold(...)``, a few lines
per ``__main__``) and *predicted* by the scheduler by reading the same lock directory with
:func:`holders` — so a bare ``simnibs_python -m tit.sim cfg.json`` from a second shell and a
server-submitted job share one policy and one lock directory. Direct Python calls
(``run_simulation()`` in a notebook) remain advisory: nothing stops them, they just don't
register a hold.

Storage: one directory per **held (resource, mode, holder)** triple,
``jobs/.locks/<sha1(discriminator)[:16]>/lock.json``, created with :func:`os.mkdir` (atomic on
bind mounts — no ``:`` or arbitrary user text in path components; NTFS-hostile characters never
appear because the directory name is a hash). Reader/writer semantics: a ``"write"`` request
conflicts with *any* existing holder of the same resource (read or write) other than itself; a
``"read"`` request conflicts only with an existing ``"write"`` holder of the same resource — so
concurrent readers each get their own directory (discriminated by job id) and never collide.

The full lock-key table (which kind holds which resource, in which mode) lives in
:func:`keys_for`, transcribed from TODO.md §2.4.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import psutil

logger = logging.getLogger(__name__)

LOCKS_SUBDIR = ".locks"
DESCRIPTOR_FILE = "lock.json"
ENV_STRICT = "TIT_LOCKS"  # "strict" refuses on conflict; default warn-and-continue


class LockConflictError(RuntimeError):
    """Raised by :func:`hold` in strict mode (``TIT_LOCKS=strict``) on a real conflict."""


@dataclass(frozen=True)
class LockRequest:
    """One lock a job needs. ``resource`` excludes the mode (e.g. ``"subject:001:m2m"``)."""

    resource: str
    mode: str = "write"  # "write" (exclusive) | "read" (shared among readers)

    @property
    def key(self) -> str:
        """Human-readable key for display (``LockConflict.key``), e.g. ``subject:001:m2m:write``."""
        return f"{self.resource}:{self.mode}"


def locks_dir(project_dir: str) -> str:
    return os.path.join(project_dir, "code", "ti-toolbox", "jobs", LOCKS_SUBDIR)


def _discriminator(request: LockRequest, job_id: str) -> str:
    if request.mode == "read":
        return f"{request.resource}::read::{job_id}"
    return request.resource


def _dir_for(project_dir: str, request: LockRequest, job_id: str) -> str:
    digest = hashlib.sha1(_discriminator(request, job_id).encode()).hexdigest()[:16]
    return os.path.join(locks_dir(project_dir), digest)


def _is_alive(pid: int, create_time: float) -> bool:
    from tit.jobs.runner import is_alive  # local import: avoid a module-load cycle

    return is_alive(pid, create_time)


def holders(project_dir: str, *, reconcile_stale: bool = True) -> list[dict[str, Any]]:
    """Every currently-held lock, as descriptor dicts (``{key, resource, mode, job_id, pid,
    create_time, ts}``). Stale entries (process gone) are removed as a side effect when
    *reconcile_stale* is true (the default; boot-time reconciliation passes it explicitly, but
    every read benefits since a crashed holder never cleans up after itself).
    """
    base = locks_dir(project_dir)
    found: list[dict[str, Any]] = []
    try:
        entries = os.listdir(base)
    except OSError:
        return found
    for name in entries:
        path = os.path.join(base, name, DESCRIPTOR_FILE)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        pid = data.get("pid")
        create_time = data.get("create_time")
        if reconcile_stale and pid is not None and create_time is not None:
            if not _is_alive(int(pid), float(create_time)):
                _remove_dir(os.path.join(base, name))
                continue
        found.append(data)
    return found


def _remove_dir(path: str) -> None:
    try:
        for name in os.listdir(path):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(path, name))
        os.rmdir(path)
    except OSError:
        pass


def parse_key(key: str) -> LockRequest:
    """Inverse of :attr:`LockRequest.key` (``"<resource>:<mode>"``); unknown/missing mode
    suffix defaults to ``"write"`` (the conservative choice — treat it as exclusive)."""
    if key.endswith(":read"):
        return LockRequest(resource=key[: -len(":read")], mode="read")
    if key.endswith(":write"):
        return LockRequest(resource=key[: -len(":write")], mode="write")
    return LockRequest(resource=key, mode="write")


def release_job(project_dir: str, job_id: str) -> int:
    """Forcibly remove every lock directory held by *job_id*, regardless of liveness.

    Used by :meth:`tit.jobs.manager.JobManager.force` — a job being forced to a terminal state
    isn't waited on, so its locks must be dropped immediately rather than on the next lazy
    :func:`holders` reconciliation. Returns the number of directories removed.
    """
    base = locks_dir(project_dir)
    removed = 0
    try:
        entries = os.listdir(base)
    except OSError:
        return 0
    for name in entries:
        path = os.path.join(base, name)
        descriptor = os.path.join(path, DESCRIPTOR_FILE)
        try:
            with open(descriptor, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("job_id") == job_id:
            _remove_dir(path)
            removed += 1
    return removed


def reconcile(project_dir: str) -> int:
    """Boot-time sweep: drop lock directories whose holder process is gone.

    Returns the number of stale directories removed.
    """
    before = len(holders(project_dir, reconcile_stale=False))
    after = len(holders(project_dir, reconcile_stale=True))
    return max(before - after, 0)


def match_conflicts(
    requests: list[LockRequest],
    current_holders: list[dict[str, Any]],
    *,
    self_job_id: str | None = None,
) -> list[dict[str, Any]]:
    """Pure function: which of *current_holders* block *requests* (reader/writer rule, §2.4).

    Takes an already-fetched holder list (rather than reading the lock directory itself) so the
    scheduler can reuse one on-disk scan across every queued job in a tick, and so this rule is
    unit-testable without any filesystem I/O.
    """
    blocking: list[dict[str, Any]] = []
    seen_job_ids: set[str] = set()
    for request in requests:
        for holder in current_holders:
            if holder.get("job_id") == self_job_id:
                continue
            if holder.get("resource") != request.resource:
                continue
            holder_mode = holder.get("mode", "write")
            if request.mode == "write" or holder_mode == "write":
                if holder["job_id"] not in seen_job_ids:
                    blocking.append(holder)
                    seen_job_ids.add(holder["job_id"])
    return blocking


def conflicts(
    project_dir: str,
    requests: list[LockRequest],
    *,
    self_job_id: str | None = None,
) -> list[dict[str, Any]]:
    """Holders that block *requests* (reader/writer rule, §2.4), excluding *self_job_id*."""
    return match_conflicts(requests, holders(project_dir), self_job_id=self_job_id)


@contextlib.contextmanager
def hold(
    project_dir: str,
    job_id: str,
    requests: list[LockRequest],
    *,
    pid: int | None = None,
    strict: bool | None = None,
) -> Iterator[None]:
    """Acquire *requests* for the duration of the context (called by the runner process).

    Default policy is warn-and-continue: a conflict is logged but the lock is still taken (the
    directories are per-holder, so this never raises ``FileExistsError`` — it just means more
    than one process now believes it holds an exclusive resource). Pass ``strict=True`` or set
    ``TIT_LOCKS=strict`` to raise :class:`LockConflictError` instead of proceeding.
    """
    if strict is None:
        strict = os.environ.get(ENV_STRICT, "").strip().lower() == "strict"
    pid = pid if pid is not None else os.getpid()
    try:
        create_time = psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        create_time = time.time()

    held_dirs: list[str] = []
    try:
        blocking = conflicts(project_dir, requests, self_job_id=job_id)
        if blocking:
            msg = (
                f"job {job_id}: lock conflict on "
                f"{sorted({b.get('key', b.get('resource', '?')) for b in blocking})} "
                f"held by {sorted({b['job_id'] for b in blocking})}"
            )
            if strict:
                raise LockConflictError(msg)
            logger.warning(msg)
        os.makedirs(locks_dir(project_dir), exist_ok=True)
        for request in requests:
            path = _dir_for(project_dir, request, job_id)
            try:
                os.mkdir(path)
            except FileExistsError:
                # Same (resource, mode, job) re-entered (e.g. a rerun reusing the id) — fine.
                pass
            descriptor = {
                "key": request.key,
                "resource": request.resource,
                "mode": request.mode,
                "job_id": job_id,
                "pid": pid,
                "create_time": create_time,
                "ts": time.time(),
            }
            with open(os.path.join(path, DESCRIPTOR_FILE), "w", encoding="utf-8") as fh:
                json.dump(descriptor, fh)
            held_dirs.append(path)
        yield
    finally:
        for path in held_dirs:
            _remove_dir(path)


# ---------------------------------------------------------------------------------------------
# keys_for(): the lock table, transcribed from TODO.md §2.4.
# ---------------------------------------------------------------------------------------------

#: ``PreprocessConfig`` step-flag name -> lock stage name (``tit/pre/config.py``, ``tit.jobs.plans``
#: forces every flag but one False per stage job, so at most one of these is true per "pre" job).
_PRE_STAGE_FLAGS: tuple[tuple[str, str], ...] = (
    ("convert_dicom", "dicom"),
    ("create_m2m", "charm"),
    ("run_fastsurfer", "fastsurfer"),
    ("run_tissue_analysis", "tissue"),
    ("run_qsiprep", "qsiprep"),
    ("run_qsirecon", "qsirecon"),
    ("extract_dti", "dti"),
)

# FastSurfer writes derivatives/fastsurfer/, not m2m -- "fastsurfer" is deliberately absent here
# (§2.4: write access to m2m is charm/subject_atlas/DTI-extraction/leadfield-gen), so G2a and G2b
# hold different lock domains and run in parallel.
_WRITES_M2M = {"charm", "dti", "leadfield"}


def _pre_requests(sid: str, config: dict[str, Any]) -> list[LockRequest]:
    stage = config.get("stage")
    if isinstance(stage, str) and stage:
        stages = [stage]
    else:
        stages = [
            stage_name
            for flag_key, stage_name in _PRE_STAGE_FLAGS
            if config.get(flag_key)
        ]
        stages = list(dict.fromkeys(stages))  # de-dupe, keep order
        if not stages:
            stages = ["pre"]  # unknown shape: one coarse lock rather than none

    requests = [LockRequest(f"subject:{sid}:stage:{s}") for s in stages]
    if any(s in _WRITES_M2M for s in stages):
        requests.append(LockRequest(f"subject:{sid}:m2m", mode="write"))
    if "dicom" in stages or "qsiprep" in stages:
        requests.append(LockRequest(f"subject:{sid}:bids", mode="write"))
    return requests


def _report_requests(sid: str, config: dict[str, Any]) -> list[LockRequest]:
    """What one subject's consolidated preprocessing report needs (``tit.pre.report``).

    The report *reads* whatever the group ran -- ``rawdata/sub-<id>`` and the derivatives of
    each stage it covers (``PreprocessingReportGenerator.scan_for_data``) -- and *writes* one
    HTML file for that subject. Its config is the group's own ``PreprocessConfig`` narrowed to
    one subject with every stage flag left as the caller set it (``tit.jobs.plans``), which is
    exactly the shape :data:`_PRE_STAGE_FLAGS` reads, so the read set is the same stage
    resources the ``pre`` jobs take for writing.

    Read locks, not write ones: two reports for different subjects, and a report next to an
    unrelated subject's ``pre`` job, must still run concurrently. The one write is the report's
    own output, so two reports for the *same* subject serialize instead of racing on one file.
    Before this, ``keys_for("report", ...)`` returned nothing at all for a per-subject report
    (`dev/notes/v3-pipelines/f0-notes.md` open issue 1) -- it scanned a subject's derivatives
    while anything at all could be rewriting them.
    """
    stages = [name for flag_key, name in _PRE_STAGE_FLAGS if config.get(flag_key)]
    requests = [
        LockRequest(f"subject:{sid}:stage:{stage}", mode="read")
        for stage in dict.fromkeys(stages)
    ]
    requests.append(LockRequest(f"subject:{sid}:bids", mode="read"))
    requests.append(LockRequest(f"subject:{sid}:m2m", mode="read"))
    requests.append(LockRequest(f"subject:{sid}:report", mode="write"))
    return requests


def keys_for(
    kind: str, subject_ids: list[str], config: dict[str, Any] | None = None
) -> list[LockRequest]:
    """Lock requests one job of *kind* needs, given its (still-serialized) *config*.

    Best-effort against configs whose exact dataclass shape is owned by another lane (marked
    below): falls back to a coarse subject-scoped lock rather than requesting nothing, so two
    jobs of an unrecognised shape still serialize instead of silently racing.
    """
    config = config or {}
    subject_ids = subject_ids or (
        [config["subject_id"]] if config.get("subject_id") else []
    )
    requests: list[LockRequest] = []

    for sid in subject_ids:
        if kind == "pre":
            requests.extend(_pre_requests(sid, config))
        elif kind == "sim":
            requests.append(LockRequest(f"subject:{sid}:m2m", mode="read"))
            requests.append(LockRequest(f"subject:{sid}:m2m:t1mni"))
            for montage in config.get("montages", []) or []:
                name = montage.get("name") if isinstance(montage, dict) else None
                if name:
                    requests.append(LockRequest(f"subject:{sid}:sim:{name}"))
        elif kind in ("flex", "flex_adaptive", "flex_pareto"):
            requests.append(LockRequest(f"subject:{sid}:m2m", mode="read"))
        elif kind in ("ex", "mex"):
            run_name = config.get("run_name") or "default"
            requests.append(LockRequest(f"subject:{sid}:{kind}:{run_name}"))
            requests.append(LockRequest(f"subject:{sid}:leadfields", mode="read"))
            requests.append(LockRequest(f"subject:{sid}:m2m", mode="read"))
            requests.append(LockRequest(f"subject:{sid}:rois", mode="read"))
        elif kind == "leadfield":
            requests.append(LockRequest(f"subject:{sid}:leadfields", mode="write"))
            requests.append(LockRequest(f"subject:{sid}:m2m", mode="write"))
        elif kind == "analyzer":
            output_dir = (
                config.get("output_dir")
                or config.get("analysis_output_dir")
                or "default"
            )
            requests.append(LockRequest(f"subject:{sid}:analysis:{output_dir}"))
            requests.append(LockRequest(f"subject:{sid}:m2m", mode="read"))
        elif kind == "source":
            requests.append(LockRequest(f"subject:{sid}:forward"))
            requests.append(LockRequest(f"subject:{sid}:m2m", mode="read"))
        elif kind == "report":
            requests.extend(_report_requests(sid, config))

    if kind == "stats":
        # GroupComparisonConfig / CorrelationConfig (tit/stats/config.py) -- neither carries an
        # "analysis_type"/"output_dir"/"name" field. tit/stats/__main__.py distinguishes them by
        # a top-level "mode" key on the request dict itself (default "group_comparison", else
        # "correlation" -- config_io's own "_type" discriminator is not used here, that
        # mechanism is for union-typed *fields*, not this top-level kind switch), and the
        # human-chosen run name is "analysis_name" on both dataclasses.
        analysis_type = config.get("mode", "group_comparison")
        name = config.get("analysis_name") or "default"
        requests.append(LockRequest(f"project:stats:{analysis_type}/{name}"))
    elif kind == "report" and config.get("group"):
        output_dir = config.get("output_dir", "default")
        requests.append(LockRequest(f"project:group_analysis:{output_dir}"))

    return requests
