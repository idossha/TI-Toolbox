"""Runner interface + the local subprocess implementation (TODO.md §2.3).

``Runner`` is deliberately narrow (``spawn`` only) so a future ``SbatchRunner`` (3.1, HPC) can
drop in: everything else — waiting for exit, killing a process tree — works on a bare pid and
doesn't care how the process was started, which is also what makes cancelling a *re-attached*
job (one this server process never spawned) possible.
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass, field

import psutil

import tit as _tit_pkg
from tit.jobs.processes import send_kill, send_terminate, spawn_kwargs

logger = logging.getLogger(__name__)

# The repo/package root this *running* tit was imported from — prepended to a child's
# PYTHONPATH so it imports the identical `tit` package, even when a different `tit` install
# (e.g. an editable install pointing elsewhere) would otherwise win on the child's own sys.path.
_TIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(_tit_pkg.__file__)))

ENV_JOB_ID = "TIT_JOB_ID"
ENV_JOB_KIND = "TIT_JOB_KIND"
ENV_JOB_SUBJECT_IDS = "TIT_JOB_SUBJECT_IDS"
ENV_EVENTS_FILE = "TIT_EVENTS_FILE"
ENV_INTERFACE = "TIT_INTERFACE"
ENV_LOCK_KEYS = (
    "TIT_LOCK_KEYS"  # informational only; real runners derive keys via keys_for()
)

DEFAULT_GRACE_S = 10.0

# PETSc installs a C signal handler for SIGTERM the moment it is initialised -- which happens on
# `import simnibs`, in *every* runner, solver or not (verified in the shared dev container: a bare
# `simnibs_python -c "import simnibs; sleep"` prints the block below on SIGTERM). Its handler turns
# a cancel into what reads as a crash:
#     [0]PETSC ERROR: Caught signal number 15 Terminate: ...
#     application called MPI_Abort(MPI_COMM_WORLD, 59) - process 0
# -- ten lines of solver wreckage at the end of a `blender` job that ran no solver at all
# (`dev/notes/v3-pipelines/2026-09-03-smoke.md` open issue 2; job 169bb37396634a31).
# `-no_signal_handler` is PETSc's own documented switch for "do not install it", and PETSc reads
# options from this environment variable, so it applies to every runner without touching a single
# runner module. SIGTERM then does what a cancel means: the default disposition ends the process
# immediately (exit 143, no output), and `tit.jobs.manager` writes the one line that explains it.
# The trade-off, deliberately: PETSc no longer prints its own diagnostics for a genuine SIGSEGV/
# SIGFPE either. `PYTHONFAULTHANDLER=1` (set below) still dumps the Python-level traceback for
# those, which is the more useful half for this application's users.
PETSC_OPTIONS_ENV = "PETSC_OPTIONS"
PETSC_NO_SIGNAL_HANDLER = "-no_signal_handler"

# How close two create_time() reads must be to count as "the same process": repeated psutil
# reads of one live process are stable to well under a millisecond, so this is generous headroom
# for that, not a window meant to tolerate genuine pid reuse (a *different* process created a
# full 10ms later must never be mistaken for the original).
PID_REUSE_TOLERANCE_S = 0.01


@dataclass
class RunRequest:
    """Everything :meth:`Runner.spawn` needs to start one job's process."""

    job_id: str
    argv: list[str]
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    # os.devnull, not a hardcoded "/dev/null": the latter doesn't exist on Windows (N0.6 spike).
    # Every real caller (tit/jobs/manager.py) passes an explicit stdout_path, so this default is
    # only ever reached by a caller that doesn't need real output -- still worth getting right.
    stdout_path: str = os.devnull


class Runner(abc.ABC):
    """Starts a job's OS process. Waiting/cancelling operate on the resulting pid directly."""

    @abc.abstractmethod
    async def spawn(self, request: RunRequest) -> asyncio.subprocess.Process:
        """Start the process; must not block until exit (fire-and-return)."""


class LocalPopenRunner(Runner):
    """``asyncio.create_subprocess_exec`` with the safe-spawn options from TODO.md §2.3.

    Its own process group (:func:`tit.jobs.processes.spawn_kwargs` -- POSIX
    ``start_new_session``, Windows ``CREATE_NEW_PROCESS_GROUP`` -- so a cancel's SIGTERM/SIGKILL
    (or their Windows equivalents) never hits the server itself), stdin ``DEVNULL``, stdout
    appended to *stdout_path* with stderr merged in, ``close_fds=True``. Never ``preexec_fn``
    (unsafe with threads) and never a pipe (a dead server would ``BrokenPipe`` the runner instead
    of leaving it to finish on its own).
    """

    async def spawn(self, request: RunRequest) -> asyncio.subprocess.Process:
        os.makedirs(os.path.dirname(request.stdout_path) or ".", exist_ok=True)
        stdout_fh = open(request.stdout_path, "ab", buffering=0)
        try:
            proc = await asyncio.create_subprocess_exec(
                *request.argv,
                cwd=request.cwd,
                env=request.env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=stdout_fh,
                stderr=asyncio.subprocess.STDOUT,
                close_fds=True,
                **spawn_kwargs(),
            )
        finally:
            # The child already holds its own duplicated fd (exec has happened by the time
            # create_subprocess_exec returns); the parent's copy can close immediately.
            stdout_fh.close()
        return proc


def runner_env(
    job_id: str,
    events_file: str,
    *,
    interface: str = "api",
    base_env: dict[str, str] | None = None,
    cpus: float | None = None,
    kind: str | None = None,
    subject_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    """The child process environment (TODO.md §2.3): unbuffered/faulthandler Python, job
    identity, thread knobs derived from the budget, and ``TIT_SERVER_TOKEN`` /
    ``TIT_SERVER_SETTINGS_FILE`` scrubbed so a job can never read the server's own auth secret
    directly, or the 0600 settings file a ``--reload`` parent hands its child (which itself
    carries the token in plain JSON) -- see ``tit/server/__main__.py``'s module docstring,
    which promises both are scrubbed (ra_14 finding #10: only the first one actually was).

    Also adds ``-no_signal_handler`` to ``PETSC_OPTIONS`` (see
    :data:`PETSC_NO_SIGNAL_HANDLER`) so cancelling a job does not end its log in a PETSc/MPI
    crash block; a value the caller already set is kept and appended to.
    """
    env = dict(base_env if base_env is not None else os.environ)
    env.pop("TIT_SERVER_TOKEN", None)
    env.pop("TIT_SERVER_SETTINGS_FILE", None)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        os.pathsep.join([_TIT_ROOT, existing_pythonpath])
        if existing_pythonpath
        else _TIT_ROOT
    )
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONFAULTHANDLER"] = "1"
    existing_petsc = env.get(PETSC_OPTIONS_ENV, "")
    if PETSC_NO_SIGNAL_HANDLER not in existing_petsc.split():
        env[PETSC_OPTIONS_ENV] = (
            f"{existing_petsc} {PETSC_NO_SIGNAL_HANDLER}".strip()
            if existing_petsc
            else PETSC_NO_SIGNAL_HANDLER
        )
    env[ENV_JOB_ID] = job_id
    if kind:
        env[ENV_JOB_KIND] = kind
    if subject_ids:
        env[ENV_JOB_SUBJECT_IDS] = ",".join(str(sid) for sid in subject_ids)
    env[ENV_EVENTS_FILE] = events_file
    env[ENV_INTERFACE] = interface
    if cpus is not None and cpus > 0:
        threads = str(max(1, int(cpus)))
        for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
            env[name] = threads
        env["TI_NIFTI_WORKERS"] = threads
    return env


def _is_untouchable_pid(pid: int) -> bool:
    """``pid`` this process must never treat as a job's own, still less signal (ra_14 finding
    #5): ``1`` (a container's init — some tini configurations forward signals from ``pid 1`` to
    every descendant, so SIGTERM/SIGKILLing it would take the whole stack down with it), and
    this server's own pid (a crafted/corrupted ``status.json`` naming it would otherwise let a
    ``cancel`` kill the server that's servicing the request)."""
    return pid <= 1 or pid == os.getpid()


def is_alive(pid: int, create_time: float | None) -> bool:
    """True if *pid* is a live, non-zombie process — and, when *create_time* is known, it's
    still the same process (not pid reuse after the original exited). Never true for pid 1 or
    this server's own pid, regardless of what ``create_time`` claims (see
    :func:`_is_untouchable_pid`)."""
    if _is_untouchable_pid(pid):
        return False
    try:
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        if (
            create_time is not None
            and abs(proc.create_time() - create_time) > PID_REUSE_TOLERANCE_S
        ):
            return False
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return False


def cpu_percent_and_rss(pid: int) -> tuple[float | None, int | None]:
    """Best-effort CPU%/RSS of *pid* (0.0 CPU on the first sample — psutil convention)."""
    try:
        proc = psutil.Process(pid)
        return proc.cpu_percent(interval=None), int(proc.memory_info().rss)
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return None, None


async def terminate_tree(
    pid: int, create_time: float | None = None, *, grace_s: float = DEFAULT_GRACE_S
) -> None:
    """Snapshot descendants, SIGTERM the tree, wait up to *grace_s*, SIGKILL survivors.

    Uses ``asyncio.sleep`` for the grace period so the caller's event loop keeps servicing other
    jobs while this one shuts down. Never raises: a pid that's already gone is a no-op. Also a
    no-op for pid 1 or this server's own pid (ra_14 finding #5, see :func:`_is_untouchable_pid`)
    -- a re-attached "running" job can only ever point there via a corrupted or crafted
    ``status.json``, never a job this server actually spawned itself.
    """
    if _is_untouchable_pid(pid):
        logger.warning("terminate_tree refused to signal untouchable pid %s", pid)
        return
    try:
        root = psutil.Process(pid)
        if create_time is not None and abs(root.create_time() - create_time) > 2.0:
            return  # pid was reused; nothing to do
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return

    procs = [root] + root.children(recursive=True)
    for proc in procs:
        with _ignore_gone():
            send_terminate(proc)

    deadline = asyncio.get_event_loop().time() + grace_s
    while asyncio.get_event_loop().time() < deadline:
        if not any(_still_running(p) for p in procs):
            return
        await asyncio.sleep(0.2)

    for proc in procs:
        if _still_running(proc):
            with _ignore_gone():
                send_kill(proc)


def _still_running(proc: psutil.Process) -> bool:
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


#: Every ``docker`` CLI call made while cancelling a job is bounded by this many seconds. A
#: wedged Docker daemon (``docker ps`` hanging forever on an unresponsive socket) must never
#: keep a cancel from finishing: the runner process is already dead by the time we get here, so
#: the worst case of giving up is an orphaned sibling container, not a job stuck in "running".
DOCKER_CLI_TIMEOUT_S = 3.0


async def _run_docker(argv: list[str], timeout_s: float) -> bytes | None:
    """Run ``docker <argv>`` with a hard timeout; ``None`` if it could not be run or timed out."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        return out
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning(
            "could not reach Docker to stop sibling containers: `docker %s` did not answer "
            "within %.1fs (is the Docker daemon responsive?)",
            " ".join(argv),
            timeout_s,
        )
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.kill()
        return None
    except OSError:
        return None


async def stop_docker_siblings(
    job_id: str, timeout_s: float = DOCKER_CLI_TIMEOUT_S
) -> None:
    """Best-effort ``docker stop`` for any container labelled ``tit.job_id=<id>``.

    QSIPrep/QSIRecon's DooD builders add this label (TODO.md §2.3); a job that never spawned a
    sibling container, or a host without a docker CLI, makes this a silent no-op. Every call is
    bounded by *timeout_s* so an unresponsive daemon degrades to a logged warning.
    """
    out = await _run_docker(
        ["ps", "-q", "--filter", f"label=tit.job_id={job_id}"], timeout_s
    )
    if not out:
        return
    ids = out.decode().split()
    if not ids:
        return
    await _run_docker(["stop", *ids], timeout_s)


def _stop_siblings_via_engine_blocking(job_id: str, timeout_s: float) -> int:
    """Blocking half of :func:`stop_docker_siblings_via_engine` (runs in a worker thread)."""
    from tit.jobs import docker_engine

    conn = docker_engine.discover()
    client = docker_engine.DockerEngineClient(conn, timeout_s=timeout_s)
    containers = client.list_containers(
        filters={"label": [f"tit.job_id={job_id}"]}, timeout_s=timeout_s
    )
    stopped = 0
    for container in containers:
        cid = container.get("Id")
        if not cid:
            continue
        # `t` is the daemon-side SIGTERM->SIGKILL grace, and the HTTP call itself is bounded by
        # the client's own socket timeout, so a container that ignores SIGTERM cannot wedge us.
        client.stop_container(cid, grace_seconds=int(max(1, timeout_s)))
        stopped += 1
    return stopped


async def stop_docker_siblings_via_engine(
    job_id: str, timeout_s: float = DOCKER_CLI_TIMEOUT_S
) -> int:
    """Stop this job's sibling containers through the bounded Engine-API client.

    Used by startup reconciliation (``JobManager._reconcile_all``), which must not shell out:
    at startup a ``docker`` CLI may not be on PATH at all, and every step before the server
    accepts requests has to be hard-bounded. :func:`stop_docker_siblings` (the CLI form) stays
    for the cancel path, whose behaviour and tests predate this. Never raises — an unreachable
    or wedged daemon degrades to a logged warning and ``0``.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_stop_siblings_via_engine_blocking, job_id, timeout_s),
            timeout=timeout_s,
        )
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning(
            "job %s: Docker did not answer within %.1fs; leaving any sibling containers alone",
            job_id,
            timeout_s,
        )
        return 0
    except Exception as exc:  # daemon absent, socket refused, API error
        logger.debug("job %s: could not stop sibling containers: %s", job_id, exc)
        return 0


class _ignore_gone:
    def __enter__(self) -> "_ignore_gone":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return exc_type is not None and issubclass(
            exc_type, (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError)
        )
