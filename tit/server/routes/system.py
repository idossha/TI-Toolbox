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

from tit.paths import get_path_manager
from tit.server.schemas import DiskInfo, MemoryInfo, ProcessInfo, SystemSnapshot

logger = logging.getLogger(__name__)

router = APIRouter()

CMDLINE_MAX = 200

# Same list as tit/gui/system_monitor_tab.py (SystemMonitorThread.relevant_keywords).
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


def relevant_processes() -> list[ProcessInfo]:
    """Toolbox-relevant processes, sorted by CPU usage (descending).

    The server's own process is never listed.
    """
    found: list[ProcessInfo] = []
    own_pid = os.getpid()
    try:
        for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "cpu_percent", "create_time", "memory_info"]
        ):
            try:
                info = proc.info
                if info["pid"] == own_pid:
                    continue
                cmdline = " ".join(info["cmdline"]) if info["cmdline"] else ""
                name = info["name"] or ""
                if not is_relevant_process(name, cmdline):
                    continue
                mem = info["memory_info"]
                found.append(
                    ProcessInfo(
                        pid=info["pid"],
                        name=name,
                        cmdline=cmdline[:CMDLINE_MAX],
                        cpu_percent=float(info["cpu_percent"] or 0.0),
                        rss=int(mem.rss) if mem is not None else 0,
                        started=float(info["create_time"] or 0.0),
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except (psutil.Error, OSError) as exc:
        logger.error("Error getting process list: %s", exc)
    found.sort(key=lambda p: p.cpu_percent, reverse=True)
    return found


def snapshot() -> SystemSnapshot:
    """Build one :class:`SystemSnapshot` (blocking; call from a thread)."""
    mem = psutil.virtual_memory()
    disk_path = get_path_manager().project_dir or "/"
    try:
        disk = psutil.disk_usage(disk_path)
    except OSError:
        disk = psutil.disk_usage("/")
    return SystemSnapshot(
        ts=time.time(),
        cpu_percent=psutil.cpu_percent(interval=None),
        cpu_count=psutil.cpu_count() or 1,
        mem=MemoryInfo(
            total=mem.total,
            available=mem.available,
            used=mem.used,
            percent=mem.percent,
        ),
        disk=DiskInfo(total=disk.total, free=disk.free, percent=disk.percent),
        processes=relevant_processes(),
    )


@router.get(
    "/api/system",
    response_model=SystemSnapshot,
    summary="One system snapshot (same payload as the /ws/system stream)",
)
def system() -> SystemSnapshot:
    return snapshot()


GRACE_SECONDS = 3.0


@router.post(
    "/api/system/terminate",
    summary="Terminate one toolbox-relevant process by pid (System page's Terminate button)",
)
def terminate(body: dict[str, Any]) -> dict[str, Any]:
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
    return {"pid": pid, "terminated": True}
