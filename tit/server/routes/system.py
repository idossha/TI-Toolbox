"""``GET /api/system`` — one system snapshot (same payload as ``/ws/system``).

The process keyword filter is copied from the PyQt ``system_monitor_tab.py``
(that module is deleted with the Qt GUI; the server must not import it).
Only the keyword list is kept: the Qt tab's second branch — any ``python``
process whose command line contains ``ti-``, ``gui/``, ``pre-process/``,
``simulator/``, ``flex-search/`` or ``ex-search/`` — matched the legacy
script directories (``ti-toolbox/gui/…``) that no longer exist and would
match the server itself; it was dropped intentionally.  The server's own
process is always excluded.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tit.paths import get_path_manager
from tit.server.schemas import (
    ContainerInfo,
    DiskInfo,
    DockerDf,
    DockerHealth,
    DockerImage,
    DockerMount,
    MemoryInfo,
    NetIO,
    OwnContainer,
    ProcessInfo,
    SelfProcessInfo,
    SwapInfo,
    SystemSnapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter()

CMDLINE_MAX = 200

# Process-name/cmdline keywords the system monitor considers TI-Toolbox-relevant.
RELEVANT_KEYWORDS: tuple[str, ...] = (
    "charm",
    "simnibs",
    "fastsurfer",
    "run_fastsurfer.sh",
    "dcm2niix",
    "fsl",
    "bet",
    "fast",
    "first",
    "flirt",
    "fnirt",
    "pre_process.py",
    "pre/structural.py",
    "pre/dicom2nifti.py",
    "pre/charm.py",
    "pre/fastsurfer.py",
    "qsiprep",
    "qsirecon",
    "pennlinc/qsiprep",
    "pennlinc/qsirecon",
    "dti_extractor",
    "pre/qsi/",
    "ti_sim.py",
    "flex-search.py",
    "ex-search",
    "leadfield.py",
    "mesh_field_analyzer.py",
    "main-TI.sh",
    "main-mTI.sh",
    "simulator",
    "python.*TI",
    "matlab.*sim",
    "gmsh",
    "tetgen",
    "subject_atlas",
    "mri_convert",
    "mris_",
    "mri_",
    "fs_",
    "preprocessor",
    "field_extract",
    "mesh2nii",
)


def is_relevant_process(proc_name: str, cmdline: str) -> bool:
    """Substring match of any keyword against ``"<name> <cmdline>"`` (lower-cased)."""
    search_text = f"{proc_name} {cmdline}".lower()
    return any(keyword.lower() in search_text for keyword in RELEVANT_KEYWORDS)


#: The htop-style table shows the busiest processes, not all of them: a SimNIBS run inside the
#: container has a few dozen and a snapshot every second must stay small.  `process_total` on the
#: snapshot says how many there really were, so the table can honestly say "top 30 of 84".
PROCESS_LIMIT = 30


def job_pid_owners() -> dict[int, tuple[str, str]]:
    """``pid -> (job_id, label)`` for every job whose runner process is alive.

    Reads the job manager **only if one already exists in this process**: ``get_manager()`` builds
    and starts a manager on first call, and a system snapshot must never be the thing that spins
    up the job subsystem as a side effect of someone opening a monitoring page.

    Children are covered too. A job's runner spawns ``charm``/``simnibs_python`` as descendants,
    and those are the processes a person actually sees eating the CPU -- attributing only the
    runner pid would leave every interesting row unowned, and ownership is what gates the UI's
    stop affordance.
    """
    owners: dict[int, tuple[str, str]] = {}
    try:
        from tit.jobs import bootstrap

        manager = bootstrap._manager  # noqa: SLF001 - deliberately not get_manager()
        if manager is None:
            return owners
        for status in manager.list_jobs(state="running"):
            pid = status.get("pid")
            if pid is None:
                continue
            subjects = ", ".join(status.get("subject_ids") or []) or "project"
            label = f"{status.get('kind', 'job')} · {subjects}"
            owners[int(pid)] = (str(status.get("id", "")), label)
            try:
                for child in psutil.Process(int(pid)).children(recursive=True):
                    owners.setdefault(child.pid, (str(status.get("id", "")), label))
            except (psutil.Error, OSError):
                continue
    except Exception:  # pragma: no cover - jobs subsystem unavailable
        logger.debug("system snapshot: job pid map unavailable", exc_info=True)
    return owners


def kernel_pid_owners() -> dict[int, tuple[str, str]]:
    """``pid -> (kernel_id, label)`` for every notebook kernel this server owns."""
    owners: dict[int, tuple[str, str]] = {}
    try:
        from tit.server.kernels import get_kernel_registry

        for session in get_kernel_registry().list():
            # jupyter_client does not put the pid on one stable attribute across versions: a
            # modern KernelManager owns a `provisioner` with the pid, older ones a `kernel`
            # (the Popen object). Try both and skip the kernel rather than guess.
            manager = getattr(session, "manager", None)
            pid = getattr(getattr(manager, "provisioner", None), "pid", None) or getattr(
                getattr(manager, "kernel", None), "pid", None
            )
            if pid is None:
                continue
            label = f"kernel {session.id[:8]}"
            owners[int(pid)] = (session.id, label)
            try:
                for child in psutil.Process(int(pid)).children(recursive=True):
                    owners.setdefault(child.pid, (session.id, label))
            except (psutil.Error, OSError):
                continue
    except Exception:  # pragma: no cover
        logger.debug("system snapshot: kernel pid map unavailable", exc_info=True)
    return owners


def process_list() -> tuple[list[ProcessInfo], int]:
    """The busiest processes plus how many there were, sorted by CPU (descending).

    Two changes from the pre-2026-09-07 list, which returned *only* keyword-matched processes:

    - Everything is listed, capped at :data:`PROCESS_LIMIT`. A process table that hides the thing
      currently using the CPU because its name is not on a keyword list is not a process table.
      The keyword match survives as ``ProcessInfo.relevant``, so the UI can still say which rows
      are toolbox work.
    - Each row carries its **owner** (a job, a kernel, or this server). Only an owned row gets a
      stop affordance in the UI, and stopping it goes through the job's own cancel path -- the
      raw ``POST /api/system/terminate`` stays as it was, keyword-gated.

    The server's own process is still never *listed* (it is reported once, as ``own``).
    """
    found: list[ProcessInfo] = []
    total = 0
    own_pid = os.getpid()
    job_owners = job_pid_owners()
    kernel_owners = kernel_pid_owners()
    try:
        for proc in psutil.process_iter(
            [
                "pid",
                "ppid",
                "name",
                "cmdline",
                "cpu_percent",
                "create_time",
                "memory_info",
                "memory_percent",
                "num_threads",
                "status",
            ]
        ):
            try:
                info = proc.info
                total += 1
                if info["pid"] == own_pid:
                    continue
                cmdline = " ".join(info["cmdline"]) if info["cmdline"] else ""
                name = info["name"] or ""
                mem = info["memory_info"]
                owner_kind: str | None = None
                owner_id: str | None = None
                owner_label = ""
                if info["pid"] in job_owners:
                    owner_kind, (owner_id, owner_label) = "job", job_owners[info["pid"]]
                elif info["pid"] in kernel_owners:
                    owner_kind, (owner_id, owner_label) = (
                        "kernel",
                        kernel_owners[info["pid"]],
                    )
                found.append(
                    ProcessInfo(
                        pid=info["pid"],
                        ppid=int(info["ppid"] or 0),
                        name=name,
                        cmdline=cmdline[:CMDLINE_MAX],
                        cpu_percent=float(info["cpu_percent"] or 0.0),
                        rss=int(mem.rss) if mem is not None else 0,
                        mem_percent=float(info["memory_percent"] or 0.0),
                        threads=int(info["num_threads"] or 0),
                        status=str(info["status"] or ""),
                        started=float(info["create_time"] or 0.0),
                        relevant=is_relevant_process(name, cmdline),
                        owner_kind=owner_kind,  # type: ignore[arg-type]
                        owner_id=owner_id,
                        owner_label=owner_label,
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except (psutil.Error, OSError) as exc:
        logger.error("Error getting process list: %s", exc)
    # Busiest first, and ties broken by memory so the list is stable rather than reshuffling every
    # second among the many processes sitting at 0.0 %.
    found.sort(key=lambda p: (p.cpu_percent, p.rss), reverse=True)
    return found[:PROCESS_LIMIT], total


def relevant_processes() -> list[ProcessInfo]:
    """The pre-2026-09-07 list: keyword-matched processes only, busiest first.

    Kept because ``POST /api/system/terminate``'s allowlist is defined in terms of it.
    """
    rows, _total = process_list()
    return [p for p in rows if p.relevant]


#: Where the Docker root lives when the daemon's storage directory is visible
#: from inside this container.  It usually is not (the socket is bind-mounted,
#: the graph directory is not), which is exactly why ``disk_docker`` is optional
#: and why ``docker system df`` is the more useful answer to "is Docker filling
#: the disk" from in here.
DOCKER_ROOT_CANDIDATES: tuple[str, ...] = ("/var/lib/docker", "/var/lib/containers")


def _disk(path: str) -> DiskInfo | None:
    try:
        usage = psutil.disk_usage(path)
    except OSError:
        return None
    return DiskInfo(
        total=usage.total, free=usage.free, percent=usage.percent, path=path
    )


def project_disk() -> DiskInfo:
    """The filesystem the project volume is on; ``/`` when that cannot be read."""
    return (
        _disk(get_path_manager().project_dir or "/")
        or _disk("/")
        or DiskInfo(total=0, free=0, percent=0.0, path="/")
    )


def docker_disk() -> DiskInfo | None:
    """The Docker root filesystem, or ``None`` when it is not visible from here."""
    for candidate in DOCKER_ROOT_CANDIDATES:
        if os.path.isdir(candidate):
            return _disk(candidate)
    return None


def load_average() -> list[float]:
    """1/5/15-minute load average; ``[]`` on a platform without one."""
    try:
        return [float(x) for x in os.getloadavg()]
    except (OSError, AttributeError):  # pragma: no cover - Windows only
        return []


def kernel_count() -> int:
    """How many notebook kernels this server process owns right now."""
    try:
        from tit.server.kernels import get_kernel_registry

        return len(get_kernel_registry().list())
    except Exception:  # pragma: no cover - jupyter_client absent, registry down
        logger.debug("system snapshot: kernel count unavailable", exc_info=True)
        return 0


def own_process() -> SelfProcessInfo | None:
    """This server's own process — the parent of every job process."""
    try:
        proc = psutil.Process(os.getpid())
        return SelfProcessInfo(
            pid=proc.pid,
            cpu_percent=float(proc.cpu_percent(interval=None)),
            rss=int(proc.memory_info().rss),
        )
    except (psutil.Error, OSError):  # pragma: no cover
        return None


def net_io() -> NetIO | None:
    """Cumulative interface counters; the page shows the delta between two snapshots."""
    try:
        counters = psutil.net_io_counters()
    except (psutil.Error, OSError, AttributeError):  # pragma: no cover
        return None
    if counters is None:  # pragma: no cover - no interfaces at all
        return None
    return NetIO(bytes_sent=int(counters.bytes_sent), bytes_recv=int(counters.bytes_recv))


# ── Docker health ────────────────────────────────────────────────────────────
#
# Everything the System page's Docker panel shows, read through
# :mod:`tit.jobs.docker_engine` (stdlib http over the Unix socket -- no CLI, no
# third-party client).  It is on its OWN, slower clock than the rest of the
# snapshot: ``/system/df`` walks the image graph and an inspect is a round trip,
# and neither changes at the 1-2 s cadence the CPU figures do.  The page would
# rather have a 5 s stale image total than have a wedged daemon stall a monitor.

DOCKER_TTL_S = 5.0
DOCKER_TIMEOUT_S = 3.0
#: ``/system/df`` gets its own, longer bound. It walks the image graph, and on a cold daemon with
#: a couple of hundred gigabytes of images it genuinely exceeds three seconds -- which is how it
#: came back empty in the container while the same call, warm, answered instantly. It is safe to
#: wait: this runs in a threadpool, behind a 5 s TTL, and nothing is blocked on it.
DF_TIMEOUT_S = 8.0
#: Only the largest few images are listed; the totals in ``df`` are the headline.
IMAGE_LIMIT = 8
#: The container is close enough to its memory limit that a large solve may be OOM-killed.
MEM_LIMIT_WARN = 0.85
#: Unused image bytes past which the panel suggests a prune.
IMAGE_RECLAIM_WARN = 20 * 1024**3

_docker_cache: tuple[float, DockerHealth] = (0.0, DockerHealth())


def _mounts(info: dict[str, Any]) -> list[DockerMount]:
    out: list[DockerMount] = []
    for m in info.get("Mounts") or []:
        out.append(
            DockerMount(
                source=str(m.get("Source", "")),
                destination=str(m.get("Destination", "")),
                mode=str(m.get("Mode", "") or ("ro" if m.get("RW") is False else "rw")),
            )
        )
    return out


def _own_container(client: Any) -> OwnContainer | None:
    """``docker inspect`` of the container this server runs in, or ``None``.

    ``None`` is the normal answer on a developer's host, where the server is a plain process and
    there is no container at all -- the panel says so rather than inventing one.
    """
    from tit.server.host_path import own_container_id

    container_id = own_container_id()
    if not container_id:
        return None
    info = client.inspect_container(container_id)
    state = info.get("State") or {}
    config = info.get("Config") or {}
    host_config = info.get("HostConfig") or {}
    nano_cpus = host_config.get("NanoCpus") or 0
    mem_limit = host_config.get("Memory") or 0
    return OwnContainer(
        id=container_id[:12],
        name=str(info.get("Name", "")).lstrip("/"),
        image=str(config.get("Image", "")),
        image_id=str(info.get("Image", ""))[:19],
        state=str(state.get("Status", "")),
        status="running" if state.get("Running") else str(state.get("Status", "")),
        health=str((state.get("Health") or {}).get("Status", "")),
        started_at=str(state.get("StartedAt", "")),
        restarts=int(info.get("RestartCount") or 0),
        cpu_limit=(nano_cpus / 1e9) if nano_cpus else None,
        mem_limit=int(mem_limit) or None,
        mounts=_mounts(info),
    )


def _usage(raw: dict[str, Any], key: str) -> dict[str, Any] | None:
    """One of Docker 29's ``*Usage`` blocks, when the daemon speaks that dialect."""
    block = raw.get(key)
    return block if isinstance(block, dict) and "TotalSize" in block else None


def _df(raw: dict[str, Any]) -> DockerDf:
    """``GET /system/df`` -> the totals ``docker system df`` prints.

    Two dialects, and the difference is not cosmetic. Docker 29 answers with authoritative
    ``ImageUsage`` / ``ContainerUsage`` / ``VolumeUsage`` / ``BuildCacheUsage`` blocks carrying
    ``TotalSize`` and ``Reclaimable``; older daemons return only the *rows*, and the totals have to
    be summed here.

    We prefer the blocks wherever they exist, because summing the rows does not reproduce what the
    CLI prints and cannot: an image's ``Size`` includes the layers it shares with other images, so
    summing 22 images gave 173 GB where the real on-disk total was 202 GB, and the "images with no
    container" heuristic for reclaimable gave 173 GB against the CLI's 33 GB. A monitor whose
    headline disk figure disagrees with ``docker system df`` by 140 GB is not worth having.
    The row-summing path below is the honest best effort for a daemon that offers nothing better.
    """
    images = raw.get("Images") or []
    containers = raw.get("Containers") or []
    volumes = raw.get("Volumes") or []
    cache = raw.get("BuildCache") or []

    image_usage = _usage(raw, "ImageUsage")
    container_usage = _usage(raw, "ContainerUsage")
    volume_usage = _usage(raw, "VolumeUsage")
    cache_usage = _usage(raw, "BuildCacheUsage")

    return DockerDf(
        images_size=int(
            (image_usage or {}).get("TotalSize")
            # `LayersSize` is the deduplicated on-disk total even on older daemons -- still much
            # closer than summing per-image sizes.
            or raw.get("LayersSize")
            or sum(int(i.get("Size") or 0) for i in images)
        ),
        images_count=int((image_usage or {}).get("TotalCount") or len(images)),
        images_reclaimable=int(
            (image_usage or {}).get("Reclaimable")
            if image_usage is not None
            else sum(int(i.get("Size") or 0) for i in images if not i.get("Containers"))
        ),
        containers_size=int(
            (container_usage or {}).get("TotalSize")
            or sum(int(c.get("SizeRw") or 0) for c in containers)
        ),
        containers_count=int(
            (container_usage or {}).get("TotalCount") or len(containers)
        ),
        volumes_size=int(
            (volume_usage or {}).get("TotalSize")
            or sum(int((v.get("UsageData") or {}).get("Size") or 0) for v in volumes)
        ),
        volumes_count=int((volume_usage or {}).get("TotalCount") or len(volumes)),
        volumes_reclaimable=int(
            (volume_usage or {}).get("Reclaimable")
            if volume_usage is not None
            else sum(
                int((v.get("UsageData") or {}).get("Size") or 0)
                for v in volumes
                if not (v.get("UsageData") or {}).get("RefCount")
            )
        ),
        build_cache_size=int(
            (cache_usage or {}).get("TotalSize")
            or sum(int(c.get("Size") or 0) for c in cache)
        ),
    )


def _containers(client: Any, own_id: str | None = None) -> list[ContainerInfo]:
    """Every container on the daemon except **us**.

    Excluding our own id matters: the System page reports this container once, in its own block
    with its limits and mounts, and listing it again under "sibling containers" said there were
    two of it. *Sibling* means "beside us", and we are not beside ourselves.
    """
    out: list[ContainerInfo] = []
    for raw in client.list_containers(timeout_s=DOCKER_TIMEOUT_S):
        container_id = str(raw.get("Id", ""))
        if own_id and container_id.startswith(own_id[:12]):
            continue
        names = raw.get("Names") or []
        out.append(
            ContainerInfo(
                id=container_id[:12],
                name=str(names[0] if names else container_id).lstrip("/"),
                image=str(raw.get("Image", "")),
                state=str(raw.get("State", "")),
                status=str(raw.get("Status", "")),
            )
        )
    return out


def _images(client: Any) -> list[DockerImage]:
    rows: list[DockerImage] = []
    for raw in client.list_images(timeout_s=DOCKER_TIMEOUT_S):
        tags = raw.get("RepoTags") or []
        rows.append(
            DockerImage(
                repo_tag=str(tags[0]) if tags else str(raw.get("Id", ""))[7:19],
                size=int(raw.get("Size") or 0),
            )
        )
    rows.sort(key=lambda i: i.size, reverse=True)
    return rows[:IMAGE_LIMIT]


def docker_warnings(health: DockerHealth) -> list[str]:
    """The row the panel shows in the warning colour. Only conditions a person can act on."""
    warnings: list[str] = []
    if health.df and health.df.images_reclaimable > IMAGE_RECLAIM_WARN:
        gb = health.df.images_reclaimable / 1024**3
        warnings.append(
            f"{gb:.0f} GB of unused images — `docker image prune` would reclaim it"
        )
    own = health.own
    if own and own.mem_limit:
        try:
            used = psutil.virtual_memory().used
        except (psutil.Error, OSError):  # pragma: no cover
            used = 0
        if used > own.mem_limit * MEM_LIMIT_WARN:
            warnings.append(
                "this container is near its memory limit — a large solve may be OOM-killed"
            )
    if own and own.restarts > 0:
        warnings.append(f"this container has restarted {own.restarts} time(s)")
    return warnings


def docker_health(now: float | None = None) -> DockerHealth:
    """Daemon reachability, ``docker system df``, our own container and the siblings.

    TTL-cached and hard-bounded, and every failure is *reported* rather than raised:
    ``reachable: false`` with an ``error`` is a first-class answer, and the most useful thing the
    panel could say at that moment. A monitoring page that goes down because the Docker daemon is
    wedged has failed at the one job it had.
    """
    global _docker_cache
    stamp = time.time() if now is None else now
    cached_at, cached = _docker_cache
    if stamp - cached_at < DOCKER_TTL_S:
        return cached

    health = DockerHealth()
    try:
        from tit.jobs.docker_engine import DockerEngineClient, discover

        connection = discover()
        if not os.path.exists(connection.socket_path):
            health.error = f"no Docker socket at {connection.socket_path}"
        else:
            client = DockerEngineClient(connection, timeout_s=DOCKER_TIMEOUT_S)
            started = time.monotonic()
            version = client.version()
            health.latency_ms = round((time.monotonic() - started) * 1000, 1)
            health.reachable = True
            health.version = str(version.get("Version", ""))
            health.api_version = str(version.get("ApiVersion", ""))

            # Each read below is independently optional: a daemon that refuses `/system/df` (it is
            # permission-gated on some setups) should still give us the container list, so one
            # failure must not cost the other three.
            def _set_df() -> None:
                health.df = _df(client.system_df(timeout_s=DF_TIMEOUT_S))

            def _set_own() -> None:
                health.own = _own_container(client)

            def _set_containers() -> None:
                # After `_set_own`, so the container we are running in can be excluded from its
                # own sibling list. `health.own` is None on a host with no container at all.
                health.containers = _containers(client, health.own.id if health.own else None)

            def _set_images() -> None:
                health.images = _images(client)

            for label, fn in (
                ("df", _set_df),
                ("own", _set_own),
                ("containers", _set_containers),
                ("images", _set_images),
            ):
                try:
                    fn()
                except Exception:
                    logger.debug("docker health: %s unavailable", label, exc_info=True)
            health.warnings = docker_warnings(health)
    except Exception as exc:
        logger.debug("docker health: unavailable", exc_info=True)
        health.reachable = False
        health.error = str(exc) or exc.__class__.__name__

    _docker_cache = (stamp, health)
    return health


def docker_siblings(now: float | None = None) -> list[ContainerInfo]:
    """The sibling containers, from the same bounded, TTL-cached read as everything Docker."""
    return docker_health(now).containers


def snapshot() -> SystemSnapshot:
    """Build one :class:`SystemSnapshot` (blocking; call from a thread)."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    processes, process_total = process_list()
    docker = docker_health()
    return SystemSnapshot(
        ts=time.time(),
        cpu_percent=psutil.cpu_percent(interval=None),
        cpu_count=psutil.cpu_count() or 1,
        cpu_per_core=[float(x) for x in psutil.cpu_percent(interval=None, percpu=True)],
        load_avg=load_average(),
        uptime_s=max(0.0, time.time() - psutil.boot_time()),
        mem=MemoryInfo(
            total=mem.total,
            available=mem.available,
            used=mem.used,
            percent=mem.percent,
            free=int(getattr(mem, "free", 0) or 0),
            # Linux only; macOS/Windows psutil has no `cached`/`buffers`, and 0 there is honest —
            # the page's stacked bar then shows used/free with no cache band rather than a
            # fabricated one.
            cached=int(getattr(mem, "cached", 0) or 0),
            buffers=int(getattr(mem, "buffers", 0) or 0),
        ),
        swap=SwapInfo(
            total=swap.total, used=swap.used, free=swap.free, percent=swap.percent
        ),
        disk=project_disk(),
        disk_docker=docker_disk(),
        own=own_process(),
        kernels=kernel_count(),
        net=net_io(),
        docker=docker,
        containers=docker.containers,
        processes=processes,
        process_total=process_total,
    )


@router.get(
    "/api/system",
    response_model=SystemSnapshot,
    summary="One system snapshot (same payload as the /ws/system stream)",
)
def system() -> SystemSnapshot:
    return snapshot()


GRACE_SECONDS = 3.0


class Terminated(BaseModel):
    """``contracts/openapi.yaml``'s ``POST /api/system/terminate`` 200 body."""

    pid: int
    terminated: bool


@router.post(
    "/api/system/terminate",
    summary="Terminate one toolbox-relevant process by pid (System page's Terminate button)",
)
def terminate(body: dict[str, Any]) -> Terminated:
    """``{pid}`` -> ``{pid, terminated}``.

    Deliberately narrow (ra_14 finding 5's own-process/pid-1 guard, applied
    here rather than reused from :mod:`tit.jobs.runner` since this route has
    no job/lock context at all -- it is a raw "kill this pid" button):

    - ``pid`` must be a real ``int`` greater than 1 (pid 1 is the container's
      init and, under some launchers, this very server's parent).
    - never the server's own pid (``os.getpid()``).
    - must currently match :func:`is_relevant_process` -- the same keyword
      allowlist the System page's process list is built from, so this can
      only ever terminate a process the UI already showed as toolbox-related,
      never an arbitrary pid a caller guesses.
    """
    pid = body.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        raise HTTPException(status_code=422, detail="body.pid must be an integer")
    if pid <= 1:
        raise HTTPException(status_code=403, detail="Refusing to terminate pid <= 1")
    if pid == os.getpid():
        raise HTTPException(
            status_code=403, detail="Refusing to terminate the server's own process"
        )
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        cmdline = " ".join(proc.cmdline())
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"No such process: {pid}")
    except psutil.AccessDenied as exc:
        raise HTTPException(
            status_code=403, detail=f"Access denied inspecting pid {pid}"
        ) from exc
    if not is_relevant_process(name, cmdline):
        raise HTTPException(
            status_code=403,
            detail=f"Refusing to terminate pid {pid}: not a toolbox-relevant process",
        )
    try:
        proc.terminate()
        try:
            proc.wait(timeout=GRACE_SECONDS)
        except psutil.TimeoutExpired:
            proc.kill()
    except psutil.NoSuchProcess:
        pass  # already gone -- success either way
    except psutil.AccessDenied as exc:
        raise HTTPException(
            status_code=403, detail=f"Access denied terminating pid {pid}"
        ) from exc
    return Terminated(pid=pid, terminated=True)
