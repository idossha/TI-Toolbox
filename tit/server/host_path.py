"""Where this server's project directory lives *on the host*, when that can be known.

``GET /api/project`` reports ``container_path`` (what the server itself sees, e.g.
``/mnt/000``) and ``host_path`` (``/Users/me/datasets/000``). Only the second one lets a
client turn the container paths every artifact carries into something the host's file
manager, a ``docker run -v`` for a sibling container, or a "Reveal in Finder" can use.

Until now ``host_path`` was ``os.environ["LOCAL_PROJECT_DIR"]`` and nothing else, and the v3
compose stack does not put that variable *inside* the container (``desktop/docker/
docker-compose.v3.yml`` interpolates it into the ``volumes:`` entry only), so every v3 server
answered ``host_path: null`` -- while the very same container carried the answer twice over,
in its ``tit.host_project_dir`` label and in the bind mount that produced ``/mnt/<name>``.
That forced every client that needs a host path to run ``docker inspect`` itself
(``dev/smoke.sh``, `docs/dev/HISTORY.md § 2026-09-03 (pipelines program)`).

So: the environment variable stays authoritative when it is set, and when it is not, the
server asks the Docker Engine about *its own container* through the socket the stack already
mounts for DooD (``/var/run/docker.sock``) and reads the answer off the container's own
definition:

1. the ``Mounts`` entry whose ``Destination`` is (or contains) the project directory -- its
   ``Source`` is the host path, and this also covers a project dir *nested* inside a mount;
2. failing that, the ``tit.host_project_dir`` label the desktop app stamps on every container
   it creates (``desktop/src/shared/compose.ts``'s ``LABEL_HOST_DIR``).

Everything here is best-effort by construction: no socket, no ``/proc``, an engine error, a
server running outside a container at all -- every one of them yields ``None``, the same
answer the route gave before, never an exception on a request path. The lookup result is
cached per project directory, so a running server makes at most one Engine call for it.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from tit import constants as const

logger = logging.getLogger(__name__)

#: Label the desktop app puts on every container it creates (``compose.ts``'s ``LABEL_HOST_DIR``).
HOST_DIR_LABEL = "tit.host_project_dir"

#: ``/proc/self/mountinfo`` names the container's own id in the paths Docker bind-mounts into it
#: (``/var/lib/docker/containers/<64 hex>/hostname`` and friends) -- the one identifier that is
#: correct even when ``HOSTNAME`` has been overridden.
_MOUNTINFO_CONTAINER_RE = re.compile(r"/containers/([0-9a-f]{64})")
_SHORT_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")

_cache: dict[str, str | None] = {}


def clear_cache() -> None:
    """Forget the memoised lookup (tests; a server never needs it)."""
    _cache.clear()


def host_project_dir(container_path: str) -> str | None:
    """The host directory *container_path* is mounted from, or ``None`` if unknowable.

    ``LOCAL_PROJECT_DIR`` wins when set (it is what the loader and the packaged app pass, and
    it is the documented contract of ``Project.host_path``); otherwise the container's own
    definition is consulted once and the result -- including ``None`` -- is cached.
    """
    from_env = os.environ.get(const.ENV_LOCAL_PROJECT_DIR)
    if from_env:
        return from_env
    if not container_path:
        return None
    if container_path in _cache:
        return _cache[container_path]
    resolved = _from_own_container(container_path)
    _cache[container_path] = resolved
    return resolved


def _join_host(source: str, suffix: str) -> str:
    """``source`` + the container-side remainder, in *the host's* separator.

    The mount's ``Source`` is written the way the host writes paths -- on a Windows host that is
    ``C:\\Users\\me\\data`` while ``suffix`` is always a POSIX fragment from the container side,
    so a naive concatenation would hand a client a mixed-separator path.
    """
    if not suffix:
        return source.rstrip("/").rstrip("\\") or source
    if "\\" in source and "/" not in source:
        return source.rstrip("\\") + suffix.replace("/", "\\")
    return source.rstrip("/") + suffix


def host_dir_from_inspect(info: dict[str, Any], container_path: str) -> str | None:
    """Pure half of the lookup: a container's inspect payload -> the host path of *container_path*.

    Prefers the bind mount that actually produced the directory (exact destination, or the
    closest enclosing one, so ``/mnt/000`` resolves even when the server was pointed at
    ``/mnt/000/sub-project``), and falls back to the ``tit.host_project_dir`` label.
    """
    target = container_path.rstrip("/") or "/"
    best: tuple[int, str] | None = None
    for mount in info.get("Mounts") or []:
        if not isinstance(mount, dict):
            continue
        # Bind mounts only. A named volume's Source is a path inside the Docker VM
        # (/var/lib/docker/volumes/...), which is not a host path any client could open.
        if mount.get("Type") not in (None, "bind"):
            continue
        source = mount.get("Source")
        destination = (mount.get("Destination") or "").rstrip("/")
        if not source or not destination:
            continue
        if target == destination:
            suffix = ""
        elif target.startswith(destination + "/"):
            suffix = target[len(destination) :]
        else:
            continue
        # The longest matching destination wins: with both `/mnt` and `/mnt/000` mounted, the
        # project dir belongs to `/mnt/000`.
        if best is None or len(destination) > best[0]:
            best = (len(destination), _join_host(source, suffix))
    if best is not None:
        return best[1]
    labels = (info.get("Config") or {}).get("Labels") or {}
    label = labels.get(HOST_DIR_LABEL)
    return label or None


def own_container_id() -> str | None:
    """This process's own container id, or ``None`` when not running in one."""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as fh:
            match = _MOUNTINFO_CONTAINER_RE.search(fh.read())
    except OSError:
        match = None
    if match:
        return match.group(1)
    # Docker sets the container's hostname to its own short id unless the caller overrode it;
    # an override just makes the inspect below 404, which is handled like every other miss.
    hostname = os.environ.get("HOSTNAME", "")
    return hostname if _SHORT_ID_RE.match(hostname) else None


def _from_own_container(container_path: str) -> str | None:
    container_id = own_container_id()
    if not container_id:
        return None
    try:
        from tit.jobs.docker_engine import DockerEngineClient, discover

        connection = discover()
        if not os.path.exists(connection.socket_path):
            return None
        info = DockerEngineClient(connection, timeout_s=5.0).inspect_container(
            container_id
        )
    except Exception as exc:  # noqa: BLE001 - a path lookup must never fail a request
        logger.debug("could not inspect own container for host path: %s", exc)
        return None
    resolved = host_dir_from_inspect(info, container_path)
    if resolved:
        logger.info("host project dir resolved from own container: %s", resolved)
    return resolved
