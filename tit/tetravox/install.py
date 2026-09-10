"""E3 — install is explicit, verified, and never executes the tarball.

One entry point, :func:`install_from_url`, and the order of its steps is the
security property:

1. the URL is checked against an **allowlist of hosts** (and re-checked on every
   redirect hop, or an open redirect on an allowed host would be a bypass);
2. the bytes are downloaded to a temp file **outside** the install root, so a
   failure at any point below cannot leave anything in it;
3. the sha256 is verified **before the archive is opened at all** -- a tarball
   whose digest does not match is never unpacked, never inspected, never named
   in the install root;
4. extraction is traversal-safe and hand-rolled (absolute names, ``..``,
   symlinks, hardlinks, devices and anything that resolves outside the
   destination are rejected, with a size and member cap) -- ``TarFile.extractall``
   is not used at all, in any Python version;
5. the manifest is validated (name, ``protocol`` inside the supported range,
   ``index.html`` present) in a **staging** directory;
6. only then is the staged directory moved into place with ``os.replace``, which
   is atomic, so a half-extracted install can never be the one being served.

Nothing in this module executes anything from the archive; a bundle is a
directory of static files that :mod:`tit.server.static` serves and a browser
runs inside the embed's own CSP.  Every call here starts either at a request the
user made in Settings or at the auto-update policy in :mod:`tit.tetravox.updates`
(A3) -- and the policy uses this module unchanged, so an automatic install is
verified by exactly the same six steps as a manual one.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from tit.tetravox import store
from tit.tetravox.protocol import SUPPORTED_PROTOCOL_MAX, SUPPORTED_PROTOCOL_MIN

ENV_ALLOWED_HOSTS = "TIT_TETRAVOX_ALLOWED_HOSTS"

#: Hosts a bundle may be downloaded from, unless extended by
#: ``TIT_TETRAVOX_ALLOWED_HOSTS`` (comma-separated).  Tetravox releases are
#: GitHub release assets, and GitHub redirects the download to its own object
#: store, so both ends of that redirect are listed.  ``api.github.com`` joined
#: the list with A2: the Releases API is where "is there a new one" is asked.
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "raw.githubusercontent.com",
)

#: Loopback is allowed over plain ``http`` as well as https.  The integrity
#: control here is the sha256, not the transport, and a loopback connection has
#: no network segment for anyone to sit on -- without this, none of this module
#: could be exercised end to end against a local server, which is exactly the
#: test that proves it works.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "[::1]", "localhost"})

#: Caps.  A bundle is a few megabytes; these exist so a hostile or corrupt
#: archive cannot fill the user's disk before the manifest is ever read.
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
MAX_EXTRACT_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 5000
NETWORK_TIMEOUT_S = 30

#: The manifest ``name`` values this is willing to install.  A bundle that calls
#: itself something else is not the Tetravox embed, whatever its digest says.
ACCEPTED_NAMES = frozenset({"@tetravox/embed", "tetravox-embed"})

_HEX = frozenset("0123456789abcdef")


class InstallError(Exception):
    """A refused install, with the code and HTTP status the route reports."""

    def __init__(self, message: str, *, code: str = "invalid", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


# ── the allowlist ────────────────────────────────────────────────────────────


def allowed_hosts() -> tuple[str, ...]:
    """:data:`DEFAULT_ALLOWED_HOSTS` plus ``TIT_TETRAVOX_ALLOWED_HOSTS`` entries."""
    extra = [
        item.strip().lower()
        for item in os.environ.get(ENV_ALLOWED_HOSTS, "").split(",")
        if item.strip()
    ]
    return tuple(dict.fromkeys(DEFAULT_ALLOWED_HOSTS + tuple(extra)))


def check_url(url: str) -> None:
    """Raise :class:`InstallError` unless *url* is an allowed https (or loopback) URL."""
    try:
        parsed = urlparse(url)
    except ValueError as exc:  # pragma: no cover - urlparse is very tolerant
        raise InstallError(f"Not a usable URL: {url}") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("https", "http"):
        raise InstallError(
            f"Only https downloads are allowed (got {parsed.scheme or 'no'} scheme)"
        )
    if parsed.scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise InstallError(f"Only https downloads are allowed (got http://{host})")
    if parsed.username or parsed.password:
        raise InstallError("A download URL must not carry credentials")
    if host in _LOOPBACK_HOSTS:
        return
    if host not in allowed_hosts():
        raise InstallError(
            f"{host or 'that host'} is not an allowed download host. "
            f"Allowed: {', '.join(allowed_hosts())} "
            f"(extend with {ENV_ALLOWED_HOSTS})"
        )


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-check the allowlist on every redirect hop.

    Without this, one open redirect on an allowed host would turn the allowlist
    into decoration: ``https://github.com/…?next=https://evil/…`` would be
    followed anywhere.  The digest still has to match afterwards, but the fetch
    itself is what the allowlist is meant to bound.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_trust_store_is_usable() -> bool:
    """Does this interpreter's OpenSSL actually have a CA store on disk?"""
    paths = ssl.get_default_verify_paths()
    for cafile in (paths.cafile, paths.openssl_cafile):
        if cafile and os.path.exists(cafile):
            return True
    for capath in (paths.capath, paths.openssl_capath):
        if capath and os.path.isdir(capath):
            return True
    return False


def ssl_context() -> ssl.SSLContext:
    """A verifying context that works on the interpreter the server actually runs on.

    Measured in the dev container, 2026-09-04: the server runs under
    ``simnibs_python`` (SimNIBS's conda build of CPython 3.11.14), whose OpenSSL
    default verify paths are the conda **build-time placeholders**
    (``/home/conda/feedstock_root/build_artifacts/openssl_split_…/ssl/cert.pem``)
    and do not exist in the image.  Every https request from the server therefore
    failed with ``CERTIFICATE_VERIFY_FAILED: unable to get local issuer
    certificate`` -- including the only real-world install, from GitHub -- while
    ``curl`` in the same container worked, because curl carries its own bundle.
    ``certifi`` *is* installed in that environment and verifies correctly.

    So: the default context when the interpreter has a real store (an operator's
    corporate CA keeps working), and ``certifi``'s bundle when it does not.
    Verification is never disabled.
    """
    if _default_trust_store_is_usable():
        return ssl.create_default_context()
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi ships with SimNIBS
        # Nothing better to offer; the failure message names the certificate
        # problem rather than pretending the host is unreachable.
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_context()),
        _AllowlistRedirectHandler(),
    )


# ── digest ───────────────────────────────────────────────────────────────────


def normalise_digest(sha256: Any) -> str:
    """Lower-cased 64-hex digest, or :class:`InstallError`."""
    if not isinstance(sha256, str):
        raise InstallError("A sha256 digest is required to install a bundle")
    value = sha256.strip().lower()
    if len(value) != 64 or not set(value) <= _HEX:
        raise InstallError(f"Not a sha256 digest: {sha256!r}")
    return value


def file_digest(path: str) -> str:
    """sha256 of the file at *path*, read in 1 MiB blocks."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# ── download ─────────────────────────────────────────────────────────────────


def download(url: str, dest: str, *, max_bytes: int = MAX_DOWNLOAD_BYTES) -> int:
    """Fetch *url* to *dest*.  Returns the byte count.  Checks the allowlist first."""
    check_url(url)
    total = 0
    try:
        with _opener().open(url, timeout=NETWORK_TIMEOUT_S) as response:
            with open(dest, "wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise InstallError(
                            f"Download exceeds {max_bytes // (1024 * 1024)} MB; refusing"
                        )
                    out.write(chunk)
    except InstallError:
        raise
    except urllib.error.HTTPError as exc:
        raise InstallError(
            f"Download failed: {exc.code} {exc.reason} for {url}",
            code="network",
            status=502,
        ) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise InstallError(
            f"Could not reach {url}: {exc}", code="network", status=502
        ) from exc
    if total == 0:
        raise InstallError(f"Download from {url} was empty", code="network", status=502)
    return total


# ── traversal-safe extraction ────────────────────────────────────────────────


def _member_target(dest_root: str, name: str) -> str:
    """The path *name* would extract to, or :class:`InstallError` if it escapes.

    Rejects an absolute path, any ``..`` component and any name that does not
    normalise to somewhere strictly inside *dest_root*.  The check is on the
    normalised path, not on the string, because ``a/../../b`` is a traversal that
    a substring test for ``"../"`` at the start would miss.
    """
    if not name or name in (".", "/"):
        raise InstallError(f"Refusing archive member with an empty name: {name!r}")
    if name.startswith("/") or name.startswith("\\") or os.path.isabs(name):
        raise InstallError(f"Refusing absolute path in archive: {name}")
    parts = name.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise InstallError(f"Refusing path traversal in archive: {name}")
    target = os.path.realpath(os.path.join(dest_root, name))
    root = os.path.realpath(dest_root)
    if target != root and not target.startswith(root + os.sep):
        raise InstallError(f"Refusing archive member outside the target: {name}")
    return target


def safe_extract(
    archive_path: str,
    dest_root: str,
    *,
    max_bytes: int = MAX_EXTRACT_BYTES,
    max_members: int = MAX_MEMBERS,
) -> int:
    """Extract *archive_path* into *dest_root*, refusing anything unsafe.

    Only regular files and directories are written.  ``TarFile.extractall`` is
    never used -- not even with ``filter="data"``, which does not exist on every
    interpreter this ships to -- so the rules below are the ones that apply,
    everywhere, and :mod:`tests.test_tetravox_install` is what proves it.
    Returns the total number of bytes written.
    """
    os.makedirs(dest_root, exist_ok=True)
    written = 0
    count = 0
    try:
        tar = tarfile.open(archive_path, "r:*")
    except (tarfile.TarError, OSError) as exc:
        raise InstallError(f"Not a readable tar archive: {exc}") from exc
    with tar:
        for member in tar:
            count += 1
            if count > max_members:
                raise InstallError(
                    f"Archive has more than {max_members} entries; refusing"
                )
            if member.issym() or member.islnk():
                raise InstallError(f"Refusing link in archive: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise InstallError(f"Refusing special file in archive: {member.name}")
            target = _member_target(dest_root, member.name)
            if member.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            written += member.size
            if written > max_bytes:
                raise InstallError(
                    f"Archive expands to more than {max_bytes // (1024 * 1024)} MB; refusing"
                )
            source = tar.extractfile(member)
            if source is None:  # pragma: no cover - isfile() implies a stream
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out:
                shutil.copyfileobj(source, out, 1024 * 1024)
            # Executable bits are dropped deliberately: a served static bundle has
            # no use for them, and nothing here should be runnable by accident.
            os.chmod(target, 0o644)
    return written


# ── manifest validation ──────────────────────────────────────────────────────


def _package_root(unpacked: str) -> str:
    """Where the bundle actually starts: *unpacked*, or its single top-level dir.

    ``npm pack`` output has everything under one directory
    (``tetravox-embed-0.3.4/``); a directory tarball may not.  Both are accepted
    so an operator does not have to know which tool produced the archive.
    """
    if os.path.isfile(os.path.join(unpacked, store.MANIFEST_FILENAME)):
        return unpacked
    entries = [e for e in os.listdir(unpacked) if not e.startswith(".")]
    if len(entries) == 1:
        candidate = os.path.join(unpacked, entries[0])
        if os.path.isfile(os.path.join(candidate, store.MANIFEST_FILENAME)):
            return candidate
    raise InstallError(
        "The archive has no manifest.json at its root "
        "(expected <name>-<version>/manifest.json, as `pnpm pack:embed` writes)"
    )


def _served_dir(package_root: str) -> str:
    """The subdirectory that becomes the served bundle.

    The release tarball keeps the browser bundle in ``dist/`` with
    ``manifest.json`` one level above it -- the same split
    ``container/blueprint/Dockerfile.ti-toolbox`` flattens when it bakes the
    floor version, and this reproduces that layout exactly so an installed
    bundle and the baked one are served identically.
    """
    dist = os.path.join(package_root, "dist")
    if os.path.isfile(os.path.join(dist, store.INDEX_FILENAME)):
        return dist
    if os.path.isfile(os.path.join(package_root, store.INDEX_FILENAME)):
        return package_root
    raise InstallError(
        "The archive has no index.html (looked in dist/ and at the package root)"
    )


def validate_manifest(manifest: Any) -> tuple[str, int]:
    """Return ``(version, protocol)`` or raise with a message a user can act on."""
    if not isinstance(manifest, dict):
        raise InstallError("manifest.json is not a JSON object")
    name = manifest.get("name")
    if name not in ACCEPTED_NAMES:
        raise InstallError(
            f"manifest.json name is {name!r}; expected one of "
            f"{', '.join(sorted(ACCEPTED_NAMES))}"
        )
    version = manifest.get("version")
    if not isinstance(version, str) or not store.is_version_name(version):
        raise InstallError(f"manifest.json version is not usable: {version!r}")
    protocol = manifest.get("protocol")
    if isinstance(protocol, bool) or not isinstance(protocol, int):
        raise InstallError(f"manifest.json protocol is not an integer: {protocol!r}")
    if not SUPPORTED_PROTOCOL_MIN <= protocol <= SUPPORTED_PROTOCOL_MAX:
        raise InstallError(
            f"That bundle speaks embed protocol {protocol}; this version of "
            f"TI-Toolbox supports protocol {SUPPORTED_PROTOCOL_MIN}"
            f"-{SUPPORTED_PROTOCOL_MAX}. Update TI-Toolbox to install it."
        )
    return version, protocol


# ── install ──────────────────────────────────────────────────────────────────


def install_archive(
    archive_path: str,
    *,
    root: str,
    sha256: str,
    activate: bool = True,
) -> store.EmbedRelease:
    """Verify, unpack and activate the bundle in *archive_path*.

    The digest is verified here rather than by the caller so that no path into
    this function can skip it.  On any failure the install root is left exactly
    as it was found.
    """
    expected = normalise_digest(sha256)
    actual = file_digest(archive_path)
    if actual != expected:
        raise InstallError(
            f"sha256 mismatch: the download is {actual}, expected {expected}. "
            "Nothing was installed."
        )

    os.makedirs(root, exist_ok=True)
    staging = os.path.join(root, f".staging-{os.getpid()}-{time.monotonic_ns()}")
    try:
        unpacked = os.path.join(staging, "unpacked")
        safe_extract(archive_path, unpacked)
        package_root = _package_root(unpacked)
        manifest_path = os.path.join(package_root, store.MANIFEST_FILENAME)
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError) as exc:
            raise InstallError(f"manifest.json could not be read: {exc}") from exc
        version, _protocol = validate_manifest(manifest)

        served = _served_dir(package_root)
        # Decided before the move, not after: once `served` is renamed away, comparing paths
        # that no longer exist is a coincidence rather than a check.
        manifest_travels_with_it = os.path.realpath(served) == os.path.realpath(
            package_root
        )
        assembled = os.path.join(staging, version)
        os.replace(served, assembled)
        if not manifest_travels_with_it:
            shutil.copyfile(
                manifest_path, os.path.join(assembled, store.MANIFEST_FILENAME)
            )

        final = os.path.join(root, version)
        previous = None
        if os.path.exists(final):
            # os.replace() cannot rename onto a non-empty directory, so an
            # existing install of the same version is moved aside first and only
            # deleted once the new one is in place -- a reinstall that fails
            # never leaves the version missing.
            previous = os.path.join(staging, f"previous-{version}")
            os.replace(final, previous)
        try:
            os.replace(assembled, final)
        except OSError:
            if previous is not None:
                os.replace(previous, final)
            raise
        release = store.describe(final, "installed", fallback_version=version)
        if release is None:  # pragma: no cover - validated above
            raise InstallError("The installed bundle is not readable")
        if activate:
            store.write_pin(root, version)
        return release
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def install_from_url(
    url: str, *, root: str, sha256: str, activate: bool = True
) -> store.EmbedRelease:
    """Download *url* and install it.  See this module's docstring for the order."""
    expected = normalise_digest(sha256)  # before any network call
    check_url(url)
    tmpdir = tempfile.mkdtemp(prefix="tit-tetravox-")
    try:
        archive = os.path.join(tmpdir, "bundle.tgz")
        download(url, archive)
        return install_archive(archive, root=root, sha256=expected, activate=activate)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
