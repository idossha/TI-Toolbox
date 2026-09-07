"""Server settings and their resolution from CLI arguments / environment."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, fields

from tit import constants as const

ENV_PROJECT_DIR = "TIT_PROJECT_DIR"
ENV_TOKEN = "TIT_SERVER_TOKEN"
ENV_STATIC_DIR = "TIT_STATIC_DIR"
ENV_HOST = "TIT_SERVER_HOST"
ENV_PORT = "TIT_SERVER_PORT"
ENV_DEV_ORIGINS = "TIT_DEV_ORIGINS"
ENV_ALLOW_HOSTS = "TIT_ALLOW_HOSTS"
ENV_SETTINGS_FILE = "TIT_SERVER_SETTINGS_FILE"
ENV_TETRAVOX_EMBED_DIR = "TIT_TETRAVOX_EMBED_DIR"
ENV_TETRAVOX_INSTALL_ROOT = "TIT_TETRAVOX_INSTALL_ROOT"

# The image bakes the embed bundle here (D1, dev/notes/v3-docker-streamline-plan.md); a dev
# checkout with no bundle installed just gets tetravox_embed.available=false and a 404 under
# /tetravox/ -- never a startup failure, since a host without the bundle is a normal state
# (Phase-B integration, or W2's image before the real embed tarball lands).
DEFAULT_TETRAVOX_EMBED_DIR = "/opt/tetravox/embed"


class SettingsError(ValueError):
    """Raised when required settings cannot be resolved."""


@dataclass
class ServerSettings:
    """Runtime configuration of one ``tit.server`` instance.

    Attributes
    ----------
    project_dir : str or None
        Container path of the BIDS project the server is bound to.  ``None``
        only when building the app for ``--dump-openapi``.
    host, port : str, int
        Bind address.  ``0.0.0.0`` inside the container (Docker port
        publishing restricts host exposure to ``127.0.0.1``).
    token : str
        Shared secret; never included in a response body.
    static_dir : str or None
        Directory holding the built UI bundle (checked at request time).
    tetravox_embed_dir : str
        The **floor**: the Tetravox embed bundle baked into the image (checked
        at request time; defaults to the image's baked-in path even when
        nothing is installed there -- see :func:`resolve_tetravox_embed_dir`).
        It is what ``/tetravox/`` serves when nothing newer is installed, which
        keeps an offline or air-gapped install working exactly as before (E2).
    tetravox_embed_override : str or None
        ``--tetravox-dir`` / ``TIT_TETRAVOX_EMBED_DIR``, when either was given.
        A dev override wins over every installed bundle
        (:func:`tit.tetravox.store.resolve_active`).
    tetravox_install_root : str or None
        Where installed bundles live (``POST /api/tetravox/install``).  ``None``
        means ``<user config>/tetravox/embed`` -- the directory the launcher
        already mounts into the container -- resolved per request by
        :func:`tit.tetravox.store.install_root`.
    dev_reload : bool
        Run uvicorn with auto-reload (development only).
    dev_origins : tuple of str
        Extra WebSocket ``Origin`` values accepted besides the request's own
        host (e.g. ``http://127.0.0.1:5173`` for the Vite dev proxy loop).
    allow_hosts : tuple of str
        Extra ``Host`` header values accepted by TrustedHost besides
        ``127.0.0.1`` / ``localhost`` (Apptainer or remote/HPC runs).
    """

    project_dir: str | None
    host: str = "0.0.0.0"
    port: int = 8765
    token: str = ""
    static_dir: str | None = None
    tetravox_embed_dir: str = DEFAULT_TETRAVOX_EMBED_DIR
    tetravox_embed_override: str | None = None
    tetravox_install_root: str | None = None
    dev_reload: bool = False
    dev_origins: tuple[str, ...] = ()
    allow_hosts: tuple[str, ...] = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "ServerSettings":
        """Rebuild settings from :meth:`to_json`, ignoring fields this build no longer has.

        The file this reads is written once at startup and re-read by every ``--reload``
        child (``tit/server/__main__.py``).  A settings-schema change mid-session therefore
        leaves the *old* keys on disk in front of the *new* dataclass, and ``cls(**data)``
        would raise ``TypeError: unexpected keyword argument`` on every reload -- the server
        stays down, with a message that names a field nobody edited.  That happened on
        2026-09-06 when ``tetravox_embed_dir`` was removed (and again when it came back).
        Dropping keys this class does not declare turns a dead dev container into a default
        for one setting.
        """
        data = json.loads(text)
        known = {field.name for field in fields(cls)}
        data = {key: value for key, value in data.items() if key in known}
        data["dev_origins"] = tuple(data.get("dev_origins", ()))
        data["allow_hosts"] = tuple(data.get("allow_hosts", ()))
        return cls(**data)


def resolve_project_dir(arg: str | None, *, required: bool = True) -> str | None:
    """Resolve the project directory.

    Order: ``--project`` argument, ``TIT_PROJECT_DIR``, ``LOCAL_PROJECT_DIR``
    (host-side runs), ``/mnt/<PROJECT_DIR_NAME>`` (container runs).

    Raises
    ------
    SettingsError
        If nothing resolves to an existing directory and *required* is true.
    """
    candidates: list[tuple[str, str | None]] = [
        ("--project", arg),
        (ENV_PROJECT_DIR, os.environ.get(ENV_PROJECT_DIR)),
        (const.ENV_LOCAL_PROJECT_DIR, os.environ.get(const.ENV_LOCAL_PROJECT_DIR)),
    ]
    name = os.environ.get(const.ENV_PROJECT_DIR_NAME)
    if name:
        candidates.append(
            (
                f"{const.DOCKER_MOUNT_PREFIX}/<{const.ENV_PROJECT_DIR_NAME}>",
                os.path.join(const.DOCKER_MOUNT_PREFIX, name),
            )
        )
    for source, value in candidates:
        if not value:
            continue
        if os.path.isdir(value):
            return os.path.abspath(value)
        raise SettingsError(f"Project directory from {source} does not exist: {value}")
    if required:
        raise SettingsError(
            "No project directory: pass --project, or set TIT_PROJECT_DIR, "
            "LOCAL_PROJECT_DIR or PROJECT_DIR_NAME"
        )
    return None


def resolve_token(arg: str | None) -> tuple[str, bool]:
    """Return ``(token, generated)``.

    Order: ``--token``, ``TIT_SERVER_TOKEN``, else a fresh
    ``secrets.token_urlsafe(32)`` (``generated`` is then true so the caller
    can print it exactly once).
    """
    if arg:
        return arg, False
    env = os.environ.get(ENV_TOKEN)
    if env:
        return env, False
    return secrets.token_urlsafe(32), True


def resolve_static_dir(arg: str | None) -> str | None:
    """``--static-dir`` argument, else ``TIT_STATIC_DIR``; may not exist yet."""
    return arg or os.environ.get(ENV_STATIC_DIR) or None


def resolve_tetravox_embed_dir(arg: str | None) -> str:
    """``--tetravox-dir`` argument, else ``TIT_TETRAVOX_EMBED_DIR``, else the image default.

    Always returns a string (unlike :func:`resolve_static_dir`): the default
    is the path the image bakes the bundle to, whether or not anything is
    installed there in this environment -- callers check ``os.path.isdir``.

    This is the *floor*, not necessarily what is served: an installed bundle
    (E2) or a dev override takes precedence, and
    :func:`tit.tetravox.store.resolve_active` decides between them on every
    request.  An explicit ``--tetravox-dir`` is both the override and the floor,
    so passing one still serves exactly that directory.
    """
    return arg or os.environ.get(ENV_TETRAVOX_EMBED_DIR) or DEFAULT_TETRAVOX_EMBED_DIR


def resolve_tetravox_embed_override(arg: str | None) -> str | None:
    """The dev override, or ``None`` when neither the flag nor the env var was set.

    Distinct from :func:`resolve_tetravox_embed_dir` because "the operator
    pointed us at a directory" and "nobody said anything, so use the image's"
    are different facts: only the first may outrank a bundle the user installed
    through ``POST /api/tetravox/install``.
    """
    return arg or os.environ.get(ENV_TETRAVOX_EMBED_DIR) or None


def resolve_tetravox_install_root(arg: str | None) -> str | None:
    """``--tetravox-install-root``, else ``TIT_TETRAVOX_INSTALL_ROOT``, else ``None``.

    ``None`` means "the default under the user config directory"; it is not
    resolved here because that call creates directories and this function runs
    while the process is still parsing arguments.
    """
    return arg or os.environ.get(ENV_TETRAVOX_INSTALL_ROOT) or None


def _csv_env(name: str) -> list[str]:
    return [
        item.strip() for item in os.environ.get(name, "").split(",") if item.strip()
    ]


def resolve_dev_origins(args: list[str] | None) -> tuple[str, ...]:
    """``--dev-origin`` values plus comma-separated ``TIT_DEV_ORIGINS``."""
    return tuple(dict.fromkeys((args or []) + _csv_env(ENV_DEV_ORIGINS)))


def resolve_allow_hosts(args: list[str] | None) -> tuple[str, ...]:
    """``--allow-host`` values plus comma-separated ``TIT_ALLOW_HOSTS``."""
    return tuple(dict.fromkeys((args or []) + _csv_env(ENV_ALLOW_HOSTS)))
