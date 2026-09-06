"""E2 — two install roots, newest compatible wins.

The image keeps baking a floor version at ``/opt/tetravox/embed`` so an offline or
air-gapped install is unaffected by anything in this module.  A **writable** root
under the already-mounted user config (``/root/.config/ti-toolbox`` in the
container, ``~/.config/ti-toolbox`` on a host) holds anything installed later, one
directory per version::

    <user config>/tetravox/embed/
        active.json          {"version": "0.4.0"}  or  {"version": "baked"}
        0.4.0/               index.html, assets/…, manifest.json
        0.3.4/               …

What ``/tetravox/`` serves is decided by :func:`resolve_active`, per request:

1. ``TIT_TETRAVOX_EMBED_DIR`` / ``--tetravox-dir`` (the pre-existing dev override) — always wins;
2. the pin in ``active.json`` when that version is still installed and in range
   (``"baked"`` pins the image's copy: this is what rollback writes);
3. the newest installed version whose manifest protocol is inside the supported range;
4. the baked directory.

**Why a pin file and not "newest always wins".**  Rollback has to be reachable
without deleting the newer bundle -- a user who installs a broken release must be
able to go back *and* forward again.  With newest-always-wins the only rollback is
``DELETE``, which throws away the evidence of what broke.

Nothing here executes anything from an install root; it only reads ``manifest.json``
and joins paths.  Installing is :mod:`tit.tetravox.install`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from typing import Any, Literal

from tit.tetravox.protocol import features_for, protocol_supported

ENV_INSTALL_ROOT = "TIT_TETRAVOX_INSTALL_ROOT"

#: Sub-path of the user config directory holding installed bundles.
INSTALL_SUBPATH = os.path.join("tetravox", "embed")

#: Filename of the pin, inside the install root.
ACTIVE_FILENAME = "active.json"

#: The version name that pins the image's baked copy (rollback target).  Not a
#: real version string, so it can never collide with an installed directory: a
#: directory called ``baked`` would not parse as a version and is ignored anyway.
BAKED = "baked"

MANIFEST_FILENAME = "manifest.json"
INDEX_FILENAME = "index.html"

#: Directory names inside the install root that are never a version.
_RESERVED_NAMES = frozenset({ACTIVE_FILENAME, BAKED})

Source = Literal["override", "installed", "baked"]


class StoreError(ValueError):
    """A requested version does not exist, or a name is not a usable version."""


@dataclass(frozen=True)
class EmbedRelease:
    """One embed bundle on disk, as everything above the filesystem sees it."""

    version: str
    protocol: int | None
    path: str
    source: Source
    name: str | None = None
    sha: str | None = None
    features: tuple[str, ...] = ()
    compatible: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "protocol": self.protocol,
            "path": self.path,
            "source": self.source,
            "name": self.name,
            "sha": self.sha,
            "features": list(self.features),
            "compatible": self.compatible,
        }


@dataclass(frozen=True)
class Resolution:
    """What ``/tetravox/`` serves right now, and the one-line reason it does."""

    release: EmbedRelease | None
    reason: str

    @property
    def path(self) -> str | None:
        return self.release.path if self.release else None


# ── version ordering ─────────────────────────────────────────────────────────


def version_key(version: str) -> tuple[tuple[int, ...], int, str]:
    """Sort key for a version string: numeric parts first, pre-releases below.

    ``0.10.0 > 0.9.9`` (numeric, not lexicographic) and ``0.4.0 > 0.4.0-rc1``
    (a trailing suffix sorts *below* the bare release, which a plain tuple
    comparison would get backwards because ``(0,4,0,1) > (0,4,0)``).
    """
    head = re.match(r"\d+(?:\.\d+)*", version.strip())
    if not head:
        return ((), -1, version)
    numbers = tuple(int(part) for part in head.group(0).split("."))
    rest = version.strip()[head.end() :]
    return (numbers, 0 if not rest else -1, rest)


def is_version_name(name: str) -> bool:
    """Is *name* usable as an install directory name (and a version)?

    Rejects anything with a path separator, a leading dot, or no leading digit --
    a manifest version is a directory name here, so it must never be able to
    escape the root or shadow ``active.json``.
    """
    if not name or name in _RESERVED_NAMES:
        return False
    if name.startswith("."):
        return False
    if os.sep in name or (os.altsep and os.altsep in name) or "/" in name:
        return False
    return re.fullmatch(r"\d[0-9A-Za-z.+_-]*", name) is not None


# ── reading a bundle ─────────────────────────────────────────────────────────


def read_manifest(directory: str) -> dict[str, Any] | None:
    """``<directory>/manifest.json`` as a dict, or ``None`` for every failure.

    Never raises: a missing directory, an unreadable file and malformed JSON all
    mean the same thing to every caller -- there is no usable bundle here.
    """
    try:
        with open(os.path.join(directory, MANIFEST_FILENAME), encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def describe(
    directory: str, source: Source, *, fallback_version: str | None = None
) -> EmbedRelease | None:
    """An :class:`EmbedRelease` for the bundle in *directory*, or ``None``.

    ``None`` when there is no readable manifest **or** no ``index.html``: a
    directory that cannot be served is not a release, and reporting one would put
    a version in the UI that 404s when opened.
    """
    manifest = read_manifest(directory)
    if manifest is None:
        return None
    if not os.path.isfile(os.path.join(directory, INDEX_FILENAME)):
        return None
    protocol = manifest.get("protocol")
    protocol_int = (
        int(protocol)
        if isinstance(protocol, int) and not isinstance(protocol, bool)
        else None
    )
    version = manifest.get("version")
    version_str = str(version) if version else (fallback_version or "unknown")
    return EmbedRelease(
        version=version_str,
        protocol=protocol_int,
        path=directory,
        source=source,
        name=str(manifest["name"]) if isinstance(manifest.get("name"), str) else None,
        sha=str(manifest["sha"]) if isinstance(manifest.get("sha"), str) else None,
        features=features_for(protocol_int, manifest.get("features")),
        compatible=protocol_supported(protocol_int),
    )


# ── roots ────────────────────────────────────────────────────────────────────


def install_root(configured: str | None = None) -> str:
    """The writable install root: *configured*, else ``TIT_TETRAVOX_INSTALL_ROOT``,
    else ``<user config>/tetravox/embed``.

    Not created here -- resolution must work on a system where nothing was ever
    installed, and creating a directory is a side effect a read has no business
    causing (it also runs on every ``/tetravox/`` request).
    """
    if configured:
        return os.path.abspath(configured)
    env = os.environ.get(ENV_INSTALL_ROOT)
    if env:
        return os.path.abspath(env)
    from tit.paths import PathManager

    return os.path.join(PathManager.user_config_dir(), INSTALL_SUBPATH)


def list_installed(root: str) -> list[EmbedRelease]:
    """Every readable bundle under *root*, newest version first."""
    try:
        names = os.listdir(root)
    except OSError:
        return []
    releases: list[EmbedRelease] = []
    for name in names:
        if not is_version_name(name):
            continue
        directory = os.path.join(root, name)
        if not os.path.isdir(directory):
            continue
        release = describe(directory, "installed", fallback_version=name)
        if release is not None:
            releases.append(release)
    releases.sort(key=lambda r: version_key(r.version), reverse=True)
    return releases


def find_installed(root: str, version: str) -> EmbedRelease | None:
    """The installed bundle whose **directory name** is *version*, or ``None``."""
    if not is_version_name(version):
        return None
    directory = os.path.join(root, version)
    if not os.path.isdir(directory):
        return None
    return describe(directory, "installed", fallback_version=version)


# ── the pin ──────────────────────────────────────────────────────────────────


def read_pin(root: str) -> str | None:
    """The pinned version name from ``active.json``, or ``None`` if unset/unreadable."""
    try:
        with open(os.path.join(root, ACTIVE_FILENAME), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    return version if isinstance(version, str) and version else None


def write_pin(root: str, version: str) -> None:
    """Pin *version* (or :data:`BAKED`) atomically.

    Unique temp name (pid + monotonic ns) then ``os.replace``, like
    ``tit/server/routes/settings.py`` -- two concurrent writers never race each
    other's rename, and a reader never sees a half-written file.
    """
    if version != BAKED and not is_version_name(version):
        raise StoreError(f"Not a usable version name: {version!r}")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, ACTIVE_FILENAME)
    tmp = f"{path}.tmp-{os.getpid()}-{time.monotonic_ns()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": version}, fh, indent=2)
    os.replace(tmp, path)


def clear_pin(root: str) -> None:
    """Remove the pin, returning to "newest compatible installed, else baked"."""
    try:
        os.remove(os.path.join(root, ACTIVE_FILENAME))
    except OSError:
        pass


# ── resolution ───────────────────────────────────────────────────────────────


def resolve_active(
    *, override_dir: str | None, baked_dir: str | None, root: str
) -> Resolution:
    """Which bundle ``/tetravox/`` serves, and why (see this module's docstring)."""
    if override_dir:
        release = describe(override_dir, "override")
        if release is not None:
            return Resolution(release, f"TIT_TETRAVOX_EMBED_DIR={override_dir}")
        return Resolution(
            None, f"dev override {override_dir} has no readable embed bundle"
        )

    baked = describe(baked_dir, "baked") if baked_dir else None
    installed = list_installed(root)
    pin = read_pin(root)

    if pin == BAKED:
        if baked is not None:
            return Resolution(baked, "pinned to the version baked into the image")
        return Resolution(None, "pinned to the baked bundle, which is not installed")
    if pin:
        pinned = next((r for r in installed if r.version == pin), None)
        if pinned is not None and pinned.compatible:
            return Resolution(pinned, f"pinned to installed {pin}")
        if pinned is not None:
            reason = (
                f"pinned {pin} speaks protocol {pinned.protocol}, outside the "
                "supported range; falling back"
            )
        else:
            reason = f"pinned {pin} is not installed; falling back"
        fallback = _newest_compatible(installed) or baked
        return Resolution(fallback, reason)

    newest = _newest_compatible(installed)
    if newest is not None:
        return Resolution(
            newest, f"newest compatible installed version ({newest.version})"
        )
    if baked is not None:
        if installed:
            return Resolution(
                baked,
                "no installed version is inside the supported protocol range; "
                "using the version baked into the image",
            )
        return Resolution(baked, "the version baked into the image")
    return Resolution(None, "no embed bundle is installed")


def _newest_compatible(installed: list[EmbedRelease]) -> EmbedRelease | None:
    return next((r for r in installed if r.compatible), None)


def remove_version(root: str, version: str) -> None:
    """Delete an installed version; clears the pin if it pointed at it."""
    if not is_version_name(version):
        raise StoreError(f"Not an installed version: {version!r}")
    directory = os.path.join(root, version)
    if not os.path.isdir(directory):
        raise StoreError(f"Not installed: {version}")
    shutil.rmtree(directory)
    if read_pin(root) == version:
        clear_pin(root)


def activate(root: str, version: str) -> EmbedRelease | None:
    """Pin *version* (or :data:`BAKED`).  Raises :class:`StoreError` if not installed."""
    if version == BAKED:
        write_pin(root, BAKED)
        return None
    release = find_installed(root, version)
    if release is None:
        raise StoreError(f"Not installed: {version}")
    write_pin(root, version)
    return release


# ── settings adapter ─────────────────────────────────────────────────────────


def resolve_from_settings(settings: Any) -> Resolution:
    """:func:`resolve_active` for a ``tit.server.settings.ServerSettings``.

    Duck-typed on purpose: :mod:`tit.tetravox` must not import
    :mod:`tit.server`, because ``tit.server.static`` imports *this*.
    """
    return resolve_active(
        override_dir=getattr(settings, "tetravox_embed_override", None),
        baked_dir=getattr(settings, "tetravox_embed_dir", None),
        root=install_root(getattr(settings, "tetravox_install_root", None)),
    )


def active_embed_dir(settings: Any) -> str | None:
    """The directory ``/tetravox/`` serves right now, or ``None``."""
    return resolve_from_settings(settings).path
