"""Host <-> container path handling: the one place that knows a host path's flavour.

The server runs in a Linux container while the Docker host may be Windows, macOS or Linux,
so a host path is parsed in *its own* flavour (:func:`flavour`), never with ``os.path``.
``desktop/src/shared/paths.ts`` holds the same rules; both suites read
``tests/fixtures/host_paths.json`` so they cannot drift.

Where this server's project directory lives *on the host*, when that can be known:

``GET /api/project`` reports ``container_path`` (what the server itself sees, e.g.
``/mnt/000``) and ``host_path`` (``/Users/me/datasets/000``). Only the second one lets a
client turn the container paths every artifact carries into something the host's file
manager, a ``docker run -v`` for a sibling container, or a "Reveal in Finder" can use.

Until now ``host_path`` was ``os.environ["LOCAL_PROJECT_DIR"]`` and nothing else, and the v3
compose stack does not put that variable *inside* the container (the root
``docker-compose.yml`` interpolates it into the ``volumes:`` entry only), so every v3 server
answered ``host_path: null`` -- while the very same container carried the answer twice over,
in its ``tit.host_project_dir`` label and in the bind mount that produced ``/mnt/<name>``.
That forced every client that needs a host path to run ``docker inspect`` itself
(``dev/smoke.sh``, `docs/dev/DECISIONS.md § 2026-09-03 (One Docker image and a real development loop)`).

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

import csv
import io
import logging
import os
import re
from pathlib import PurePath, PurePosixPath, PureWindowsPath
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


_WINDOWS_RE = re.compile(r"^([A-Za-z]:|[\\/]{2})")


def flavour(path: str) -> PurePath:
    """*path* in the flavour it is written in: a drive letter or a UNC prefix (``\\\\`` or
    ``//``) is Windows, anything else POSIX, so joins and ``is_absolute`` follow the host.
    """
    if _WINDOWS_RE.match(path):
        return PureWindowsPath(path)
    return PurePosixPath(path)


def project_dir_name(host_dir: str) -> str:
    """The ``<name>`` in ``/mnt/<name>`` the compose stack mounts *host_dir* at.

    Raises ``ValueError`` for a drive or share root, which has no name to mount under.
    """
    name = flavour(host_dir.strip()).name
    if not name:
        raise ValueError(f"Project directory has no name: {host_dir!r}")
    return name


def to_host(container_path: str, container_root: str, host_root: str) -> str | None:
    """*container_path* re-rooted onto *host_root* in the host's separator, or ``None`` when
    it is not under *container_root* (``/mnt/000x`` is not under ``/mnt/000``)."""
    try:
        rest = PurePosixPath(container_path).relative_to(container_root).parts
    except ValueError:
        return None
    if ".." in rest:
        return None
    return str(flavour(host_root).joinpath(*rest))


def to_container(host: str, host_root: str, container_root: str) -> str | None:
    """*host* re-rooted onto *container_root*, or ``None`` when it is not under *host_root*.

    A Windows root compares case-insensitively (``c:\\users`` is ``C:\\Users``).
    """
    root, target = flavour(host_root), flavour(host)
    if type(root) is not type(target):
        return None
    try:
        rest = target.relative_to(root).parts
    except ValueError:
        return None
    if ".." in rest:
        return None
    return str(PurePosixPath(container_root).joinpath(*rest))


def get_host_project_dir() -> str:
    """The host's project directory (``LOCAL_PROJECT_DIR``), for sibling-container mounts.

    Raises ``ValueError`` if it is unset or not an absolute host path.
    """
    value = os.environ.get(const.ENV_LOCAL_PROJECT_DIR, "").strip()
    if not value:
        raise ValueError(
            f"{const.ENV_LOCAL_PROJECT_DIR} environment variable is not set. "
            "This is required for spawning sibling Docker containers."
        )
    if not flavour(value).is_absolute():
        raise ValueError(
            f"{const.ENV_LOCAL_PROJECT_DIR} must be an absolute host path, got {value!r}."
        )
    return value


def bind_mount(source: object, target: object, *, readonly: bool = False) -> list[str]:
    """``docker run`` argv for one bind mount: ``--mount``, not ``-v``, whose colon-separated
    form is ambiguous with a Windows ``C:\\`` source; CSV quoting covers a comma in a path.
    """
    fields = ["type=bind", f"source={source}", f"target={target}"]
    if readonly:
        fields.append("readonly")
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return ["--mount", buf.getvalue()]


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
        host = to_host(target, destination, source)
        # The longest matching destination wins: with both `/mnt` and `/mnt/000` mounted, the
        # project dir belongs to `/mnt/000`.
        if host is not None and (best is None or len(destination) > best[0]):
            best = (len(destination), host)
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
