"""Cheap capability probes for the scientific server runtime."""

from __future__ import annotations

import importlib.util
import os
import sys

from fastapi import APIRouter, Request

from tit.server.schemas import Capabilities

router = APIRouter()

DOCKER_SOCKET = "/var/run/docker.sock"
FASTSURFER_SCRIPT = "run_fastsurfer.sh"


def _module_available(name: str) -> bool:
    """Importable without importing it (``find_spec`` only)."""
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _fastsurfer_home() -> str | None:
    """``FASTSURFER_HOME`` if it has the runner script, else ``/opt/fastsurfer``, else ``None``."""
    for candidate in (os.environ.get("FASTSURFER_HOME"), "/opt/fastsurfer"):
        if candidate and os.path.isfile(os.path.join(candidate, FASTSURFER_SCRIPT)):
            return candidate
    return None


def probe_capabilities() -> Capabilities:
    """Probe server dependencies; native viewer availability belongs to the host."""
    return Capabilities(
        docker_socket=os.path.exists(DOCKER_SOCKET),
        bpy=_module_available("bpy"),
        # `jupyter` (the meta-package) importable in this same interpreter --
        # the container's `NOTEBOOK` alias runs `simnibs_python -m jupyter
        # lab`, and the server itself runs under `simnibs_python`, so
        # `find_spec` here answers the same question that alias depends on
        # (ra_13 finding 3e; there is no in-app start control yet, see
        # `pages/settings/index.tsx`'s Jupyter card).
        jupyter=_module_available("jupyter"),
        fastsurfer=_fastsurfer_home() is not None,
    )


@router.get(
    "/api/capabilities",
    response_model=Capabilities,
    summary="What this runtime can do (used to grey out UI)",
)
def capabilities(request: Request) -> Capabilities:
    return probe_capabilities()
