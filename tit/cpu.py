"""How many CPUs this process may actually use — one answer, used everywhere.

``os.cpu_count()`` inside a container reports the *host's* (or the Docker VM's) cores, not the
limit Docker applied: an image started with ``--cpus=4`` on a 12-core machine still answers 12.
Every plan number derived from it was therefore a promise of cores that do not exist, and every
worker count derived from it oversubscribed the container.

:func:`effective_cpus` asks, in order, and takes the smallest answer anything gives:

1. cgroup v2 ``cpu.max`` — ``"<quota> <period>"``, or ``"max <period>"`` for no limit
   (``--cpus=4`` writes ``400000 100000``);
2. cgroup v1 ``cpu/cpu.cfs_quota_us`` over ``cpu/cpu.cfs_period_us`` (``-1`` = no limit);
3. the effective cpuset (``cpuset.cpus.effective``, v1 ``cpuset/cpuset.cpus``) — what
   ``--cpuset-cpus`` pins the container to;
4. ``os.sched_getaffinity(0)``;
5. ``os.cpu_count()``.

The result is an integer >= 1. ``root`` exists so the tests can point the whole lookup at a
fixture directory rather than mocking ``open``.
"""

from __future__ import annotations

import json
import math
import os

CGROUP_ROOT = "/sys/fs/cgroup"


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.readline().strip()
    except OSError:
        return None


def _quota_cpus(quota: str | None, period: str | None) -> int | None:
    """``floor(quota / period)`` when both are positive integers, else ``None``."""
    if not quota or not period:
        return None
    try:
        q, p = int(quota), int(period)
    except ValueError:
        return None
    if q <= 0 or p <= 0:
        return None
    return max(1, math.floor(q / p))


def _cpuset_count(spec: str | None) -> int | None:
    """Number of CPUs in a cpuset list like ``"0-3,8"``; ``None`` when unparseable/empty."""
    if not spec:
        return None
    total = 0
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                total += max(0, int(hi) - int(lo) + 1)
            except ValueError:
                return None
        else:
            try:
                int(part)
            except ValueError:
                return None
            total += 1
    return total or None


def cgroup_cpu_limit(root: str = CGROUP_ROOT) -> int | None:
    """The container's CPU limit from cgroups, or ``None`` when it is unlimited/unreadable."""
    limits: list[int] = []

    cpu_max = _read(os.path.join(root, "cpu.max"))
    if cpu_max:
        parts = cpu_max.split()
        if len(parts) >= 2 and parts[0] != "max":
            derived = _quota_cpus(parts[0], parts[1])
            if derived:
                limits.append(derived)
    else:
        derived = _quota_cpus(
            _read(os.path.join(root, "cpu", "cpu.cfs_quota_us")),
            _read(os.path.join(root, "cpu", "cpu.cfs_period_us")),
        )
        if derived:
            limits.append(derived)

    cpuset = _read(os.path.join(root, "cpuset.cpus.effective")) or _read(
        os.path.join(root, "cpuset", "cpuset.cpus")
    )
    pinned = _cpuset_count(cpuset)
    if pinned:
        limits.append(pinned)

    return min(limits) if limits else None


def effective_cpus(root: str = CGROUP_ROOT) -> int:
    """CPUs this process may actually use (>= 1). See the module docstring for the order."""
    counts: list[int] = []
    limit = cgroup_cpu_limit(root)
    if limit:
        counts.append(limit)
    getaffinity = getattr(os, "sched_getaffinity", None)
    if getaffinity is not None:
        try:
            counts.append(len(getaffinity(0)))
        except OSError:  # pragma: no cover - defensive
            pass
    counts.append(os.cpu_count() or 1)
    return max(1, min(c for c in counts if c > 0))


#: The user's global CPU limit, as a percent of :func:`effective_cpus`. TI-Toolbox shares the
#: machine with the user's own work, so no default claims every core (DECISIONS 2026-09-22).
DEFAULT_CPU_LIMIT_PERCENT = 70
MIN_CPU_LIMIT_PERCENT = 10
CPU_LIMIT_FILENAME = "cpu-limit.json"


def cpu_limit_file() -> str:
    """Where the Settings page saves the percent: the user config dir every project shares."""
    from tit.paths import PathManager

    return os.path.join(PathManager.user_config_dir(), CPU_LIMIT_FILENAME)


def _valid_percent(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        percent = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return percent if MIN_CPU_LIMIT_PERCENT <= percent <= 100 else None


def cpu_limit_percent() -> int:
    """The global CPU limit percent: the saved setting (the only source), else 70."""
    try:
        with open(cpu_limit_file(), encoding="utf-8") as fh:
            saved = _valid_percent(json.load(fh).get("percent"))
    except (OSError, ValueError, AttributeError):
        saved = None
    return saved if saved is not None else DEFAULT_CPU_LIMIT_PERCENT


def save_cpu_limit_percent(percent: int) -> None:
    """Atomically save the percent (10-100) for the server and every later script."""
    if type(percent) is not int or _valid_percent(percent) is None:
        raise ValueError(
            f"percent must be an integer from {MIN_CPU_LIMIT_PERCENT} to 100"
        )
    path = cpu_limit_file()
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"percent": percent}, fh)
    os.replace(tmp, path)


def cpu_limit(root: str = CGROUP_ROOT) -> int:
    """Cores TI-Toolbox may use in total: ``floor(percent/100 x effective_cpus())``, at least 1.

    The scheduler's CPU budget and every "use all the cores" default resolve to this.
    """
    return max(1, math.floor(cpu_limit_percent() * effective_cpus(root) / 100))


#: Env var the job runner exports with the CPU count the plan admitted this job
#: (:mod:`tit.jobs.runner`), so a solver's own "use all the cores" default cannot disagree with
#: the number the plan showed the user.
JOB_CPUS_ENV = "TIT_JOB_CPUS"


def job_cpus() -> int:
    """The CPU budget this job was admitted with, else (outside a job) :func:`cpu_limit`."""
    raw = os.environ.get(JOB_CPUS_ENV)
    if raw:
        try:
            value = int(float(raw))
        except ValueError:
            value = 0
        if value > 0:
            return value
    return cpu_limit()


def resolve_n_jobs(n_jobs: int | None) -> int:
    """Pool worker count (ex/mex searches, stats permutations), capped at the job's CPU budget.

    The budget is :func:`job_cpus`: the CPUs the plan admitted the job with
    (``TIT_JOB_CPUS``, exported by :mod:`tit.jobs.runner`), or outside a job the user's global CPU
    limit (70 % of the container by default). ``n_jobs < 1`` (or ``None``) means the whole budget;
    an explicit ``n_jobs`` is clamped to it, so no API value can exceed the limit.
    """
    budget = job_cpus()
    if n_jobs is None or n_jobs < 1:
        return budget
    return max(1, min(int(n_jobs), budget))
