"""``GET /api/capabilities`` — what this runtime can do (UI greys out the rest).

D3 (``dev/notes/v3-docker-streamline-plan.md``): X11/Freeview/Gmsh/FreeSurfer
are gone from this runtime entirely -- viewing is the Tetravox embed
(``tetravox_embed``, served at ``/tetravox/`` by :mod:`tit.server.static`) and
voxel-space cortical parcellation is FastSurfer ``--seg_only`` (``fastsurfer``).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Request

from tit.server.schemas import Capabilities, ProtocolRange, TetravoxEmbedCapability
from tit.server.settings import DEFAULT_TETRAVOX_EMBED_DIR
from tit.tetravox import protocol as tvx_protocol
from tit.tetravox import store as tvx_store

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


def _probe_tetravox_embed(settings: Any) -> TetravoxEmbedCapability:
    """The **active** bundle, resolved the same way ``/tetravox/`` resolves it.

    ``available=False`` (never an exception) for every failure mode -- no
    directory, no manifest, unreadable, malformed JSON -- so a dev checkout
    with no embed installed just greys the viewer out instead of failing
    ``GET /api/capabilities`` outright.

    E1: the answer carries ``protocol``, the named ``features`` that protocol
    provides, the ``supported`` range this build can host and whether the two
    agree -- so a pane asks "can this embed do markers" and never "is this
    version >= x". ``source`` is what the Settings page shows the user (baked
    into the image / installed / dev override).
    """
    supported = ProtocolRange(**tvx_protocol.supported_range())
    release = tvx_store.resolve_from_settings(settings).release
    if release is None:
        return TetravoxEmbedCapability(available=False, supported=supported)
    return TetravoxEmbedCapability(
        available=True,
        version=release.version,
        protocol=release.protocol,
        source=release.source,
        features=list(release.features),
        compatible=release.compatible,
        supported=supported,
    )


def probe_capabilities(
    tetravox_embed_dir: str | None = None, *, settings: Any = None
) -> Capabilities:
    """Cheap filesystem/env probes only — nothing heavy is imported.

    *settings* is a ``ServerSettings``; without one, *tetravox_embed_dir* is
    treated as the baked floor (defaulting to the image's own path) so a direct
    call from a test or a script still probes something real.
    """
    if settings is None:
        settings = SimpleNamespace(
            tetravox_embed_dir=tetravox_embed_dir or DEFAULT_TETRAVOX_EMBED_DIR,
            tetravox_embed_override=None,
            tetravox_install_root=None,
        )
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
        tetravox_embed=_probe_tetravox_embed(settings),
        fastsurfer=_fastsurfer_home() is not None,
    )


@router.get(
    "/api/capabilities",
    response_model=Capabilities,
    summary="What this runtime can do (used to grey out UI)",
)
def capabilities(request: Request) -> Capabilities:
    return probe_capabilities(settings=request.app.state.settings)
