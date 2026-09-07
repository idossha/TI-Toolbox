"""A4/A2/A3 — "is there a newer Tetravox embed", and applying it on a policy.

Three things live here, and each exists because the alternative was measured to
be worse:

**The GitHub Releases API is the index** (A2).  The previous design read a
``releases.json`` committed to the Tetravox repo; it never existed
(``docs/dev/HISTORY.md § 2026-09-04 (embed convergence)`` §6, request 2 — the URL answered
404 for the whole of lane U's live run), and a file a human has to remember to
update is an index that goes stale silently.  ``/repos/idossha/tetravox/releases``
is written by the release itself.  A release is *incorporable* when it carries
the three assets ``tetravox-embed-<ver>.tgz``, ``tetravox-embed-<ver>.tgz.sha256``
and ``tetravox-embed-<ver>.manifest.json``; the protocol number is read from the
**manifest asset**, so deciding "does this build support it" never downloads the
bundle.  Drafts and prereleases are skipped.

``TIT_TETRAVOX_RELEASE_INDEX`` keeps working for an air-gapped mirror and now
accepts *either* shape — the GitHub JSON as the API returns it, or the flat
``{"releases": [...]}`` index — because a mirror is usually ``curl``'s output
saved to a file.

**An ETag cache** (:data:`CACHE_FILENAME`, in the install root).  Unauthenticated
GitHub allows 60 requests/hour/IP; a 304 costs nothing against that budget and a
403 is reported as *could not check*, never as an error dialog.  The cache also
persists the **last check time and result**, so Settings can say when it last
looked even after a restart, and so the 24 h timer survives one.

**A policy, not a habit** (A3).  ``auto_update`` (default on) is stored next to
the pin.  When it is on, the server checks at startup and every 24 h and installs
a newer release **only** when its protocol is inside this build's supported
range; a release past the range is reported as *needs a TI-Toolbox update* and is
never installed (A1).  When it is off, the check still runs and Settings shows
"Update available" — the choice being made is *whether to install*, not *whether
to know*.  After a successful install the last :data:`KEEP_INSTALLED` versions
are kept, so rollback (A4) still has somewhere to go back to.

Nothing here runs at import time, and every network failure is a sentence.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from tit.tetravox import install, store
from tit.tetravox.protocol import protocol_supported

ENV_RELEASE_INDEX = "TIT_TETRAVOX_RELEASE_INDEX"
ENV_AUTO_UPDATE = "TIT_TETRAVOX_AUTO_UPDATE"

#: A2 — where "is there a new one" is answered from.
GITHUB_RELEASES_URL = "https://api.github.com/repos/idossha/tetravox/releases"

#: Cache + last-check record, inside the install root.
CACHE_FILENAME = "updates.json"
#: The auto-update policy, next to the pin.
POLICY_FILENAME = "policy.json"

#: A3 — how often the background check runs, and how long it waits before the
#: first one.  The delay is not politeness: it keeps the check strictly behind
#: ``/api/health`` coming up, and it means a short-lived process (a test client,
#: ``--dump-openapi``) exits before any socket is opened.
CHECK_INTERVAL_S = 24 * 60 * 60
STARTUP_DELAY_S = 5.0

#: A4 — how many installed bundles survive an auto-install.
KEEP_INSTALLED = 2

#: How many releases deep the sidecar fetch goes.  Only the newest few can ever
#: be the answer, and each one costs two small requests against a 60/hour budget.
MAX_RELEASES_INSPECTED = 3

#: Asset names A2 fixes.  ``<ver>`` is the release's embed version, which is the
#: manifest's own version — matched from the filename, verified from the manifest.
_TGZ_RE = re.compile(r"^tetravox-embed-(?P<ver>.+)\.tgz$")
_SIDECAR_MAX_BYTES = 64 * 1024

InstallError = install.InstallError


# ── the policy ───────────────────────────────────────────────────────────────


def read_policy(root: str) -> bool:
    """Is auto-update on?  ``policy.json``, else ``TIT_TETRAVOX_AUTO_UPDATE``, else on.

    The env var is the operator's off switch for an image that must never reach
    the network (and the switch the test suite uses); the file is the user's.
    The file wins, because a user who turned it off in Settings has said
    something more specific than a deployment default.
    """
    try:
        with open(os.path.join(root, POLICY_FILENAME), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict) and isinstance(data.get("auto_update"), bool):
        return data["auto_update"]
    env = os.environ.get(ENV_AUTO_UPDATE)
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off")
    return True


def write_policy(root: str, auto_update: bool) -> bool:
    """Persist the policy atomically (same rename dance as the pin)."""
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, POLICY_FILENAME)
    tmp = f"{path}.tmp-{os.getpid()}-{time.monotonic_ns()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"auto_update": bool(auto_update)}, fh, indent=2)
    os.replace(tmp, path)
    return bool(auto_update)


# ── the cache / last-check record ────────────────────────────────────────────


@dataclass(frozen=True)
class CheckResult:
    """One answer to "is there a newer embed", cacheable and renderable as-is."""

    available: bool
    message: str | None = None
    releases: list[dict[str, Any]] = field(default_factory=list)
    checked_at: float | None = None
    from_cache: bool = False
    index_url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "message": self.message,
            "releases": list(self.releases),
            "checked_at": self.checked_at,
            "from_cache": self.from_cache,
            "index_url": self.index_url,
        }


def read_cache(root: str) -> dict[str, Any]:
    try:
        with open(os.path.join(root, CACHE_FILENAME), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_cache(root: str, data: dict[str, Any]) -> None:
    try:
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, CACHE_FILENAME)
        tmp = f"{path}.tmp-{os.getpid()}-{time.monotonic_ns()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except OSError:
        # A cache that cannot be written is a slower check, not a failed one.
        pass


# ── fetching ─────────────────────────────────────────────────────────────────


def release_index_url(configured: str | None = None) -> str:
    """*configured*, else ``TIT_TETRAVOX_RELEASE_INDEX``, else the GitHub API."""
    return configured or os.environ.get(ENV_RELEASE_INDEX) or GITHUB_RELEASES_URL


def _fetch(url: str, *, etag: str | None = None) -> tuple[int, bytes, str | None]:
    """GET *url* (allowlisted), optionally conditional.  ``(status, body, etag)``.

    A ``304`` comes back as a status with an empty body rather than an
    exception, because "nothing changed" is the good case, not a failure.
    """
    install.check_url(url)
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json, application/json")
    request.add_header("User-Agent", "TI-Toolbox")
    if etag:
        request.add_header("If-None-Match", etag)
    try:
        with install._opener().open(  # noqa: SLF001 - one opener, one allowlist
            request, timeout=install.NETWORK_TIMEOUT_S
        ) as response:
            body = response.read(4 * 1024 * 1024)
            return response.status, body, response.headers.get("ETag")
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return 304, b"", etag
        if exc.code in (403, 429):
            remaining = (
                exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
            )
            hint = (
                " (GitHub's unauthenticated rate limit is 60 requests per hour "
                "per IP; the next check is in 24 h)"
                if remaining == "0"
                else ""
            )
            raise InstallError(
                f"Could not check for updates: {url} answered {exc.code} "
                f"{exc.reason}{hint}",
                code="rate_limited",
                status=502,
            ) from exc
        raise InstallError(
            f"The release index answered {exc.code} {exc.reason} ({url})",
            code="network",
            status=502,
        ) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise InstallError(
            f"Could not reach the release index ({url}): {exc}",
            code="offline",
            status=502,
        ) from exc


def _fetch_text(url: str) -> str:
    status, body, _ = _fetch(url)
    if status != 200:
        raise InstallError(f"{url} answered {status}", code="network", status=502)
    return body.decode("utf-8", "replace")


# ── parsing: two shapes, one normalised entry ────────────────────────────────


def _entry(
    *,
    version: str,
    protocol: Any,
    url: str,
    sha256: str,
    notes: Any = None,
    published: Any = None,
) -> dict[str, Any] | None:
    if not (store.is_version_name(version) and url and sha256):
        return None
    digest = sha256.strip().lower()
    if len(digest) != 64 or not set(digest) <= set("0123456789abcdef"):
        return None
    return {
        "version": version,
        "protocol": (
            protocol
            if isinstance(protocol, int) and not isinstance(protocol, bool)
            else None
        ),
        "url": url,
        "sha256": digest,
        "notes": notes if isinstance(notes, str) else None,
        "published": published if isinstance(published, str) else None,
    }


def parse_plain_index(payload: Any) -> list[dict[str, Any]]:
    """The flat mirror shape: ``{"releases": [{version, protocol, url, sha256}]}``.

    Entries missing a version, a URL or a digest are dropped rather than shown:
    an entry that cannot be installed is not an update.
    """
    entries = payload.get("releases") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise InstallError(
            "The release index has no `releases` array", code="invalid", status=502
        )
    out: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        normalised = _entry(
            version=str(item.get("version") or ""),
            protocol=item.get("protocol"),
            url=str(item.get("url") or ""),
            sha256=str(item.get("sha256") or ""),
            notes=item.get("notes"),
            published=item.get("published"),
        )
        if normalised is not None:
            out.append(normalised)
    out.sort(key=lambda e: store.version_key(e["version"]), reverse=True)
    return out


def looks_like_github(payload: Any) -> bool:
    """Is this the Releases API's own JSON (a list of release objects)?"""
    if not isinstance(payload, list):
        return False
    return any(
        isinstance(item, dict) and ("assets" in item or "tag_name" in item)
        for item in payload
    )


def _assets(release: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if isinstance(name, str) and isinstance(url, str):
            out[name] = url
    return out


def parse_github_releases(
    payload: Any,
    *,
    fetch_text: Any = None,
    limit: int = MAX_RELEASES_INSPECTED,
) -> tuple[list[dict[str, Any]], list[str]]:
    """A2 — the Releases API's JSON to normalised entries, newest first.

    Returns ``(entries, skipped)``: *skipped* is one honest sentence per release
    that exists but carries no embed, so "there are releases but none is
    installable" can be said out loud instead of showing an empty list.

    Drafts and prereleases never appear.  For each of the newest *limit*
    releases that carry the tarball, the two **sidecars** are fetched — the
    ``.sha256`` (the digest the installer will verify, which must come from the
    publisher, never from us) and the ``.manifest.json`` (the protocol, so this
    check never downloads a multi-megabyte bundle just to learn it cannot use
    it).  A release whose sidecars are missing or unreadable is skipped with its
    reason, not guessed at.
    """
    get_text = fetch_text or _fetch_text
    if not isinstance(payload, list):
        raise InstallError(
            "The GitHub releases response is not a list", code="invalid", status=502
        )
    entries: list[dict[str, Any]] = []
    skipped: list[str] = []
    inspected = 0
    for release in payload:
        if not isinstance(release, dict):
            continue
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or release.get("name") or "?")
        assets = _assets(release)
        tarball = next(
            ((n, u) for n, u in assets.items() if _TGZ_RE.match(n)),
            None,
        )
        if tarball is None:
            skipped.append(f"{tag} carries no tetravox-embed-<version>.tgz asset")
            continue
        name, url = tarball
        match = _TGZ_RE.match(name)
        assert match is not None
        version = match.group("ver")
        if inspected >= limit:
            break
        inspected += 1
        digest_url = assets.get(f"{name}.sha256")
        manifest_url = assets.get(f"tetravox-embed-{version}.manifest.json")
        if digest_url is None or manifest_url is None:
            skipped.append(
                f"{tag} has {name} but not its .tgz.sha256 and .manifest.json sidecars"
            )
            continue
        try:
            digest = get_text(digest_url).strip().split()[0] if digest_url else ""
            manifest = json.loads(get_text(manifest_url))
        except (InstallError, ValueError, IndexError) as exc:
            skipped.append(f"{tag}: could not read its sidecars ({exc})")
            continue
        normalised = _entry(
            version=version,
            protocol=(manifest.get("protocol") if isinstance(manifest, dict) else None),
            url=url,
            sha256=digest,
            notes=(
                release.get("name")
                if isinstance(release.get("name"), str)
                else release.get("body")
            ),
            published=release.get("published_at"),
        )
        if normalised is None:
            skipped.append(f"{tag}: its sidecars do not describe an installable bundle")
            continue
        entries.append(normalised)
    entries.sort(key=lambda e: store.version_key(e["version"]), reverse=True)
    return entries, skipped


def parse_index(
    payload: Any, *, fetch_text: Any = None
) -> tuple[list[dict], list[str]]:
    """Whichever shape came back.  See :func:`parse_github_releases` for the pair."""
    if looks_like_github(payload):
        return parse_github_releases(payload, fetch_text=fetch_text)
    return parse_plain_index(payload), []


# ── the check ────────────────────────────────────────────────────────────────


def fetch_release_index(url: str | None = None) -> list[dict[str, Any]]:
    """Both shapes, no cache.  Raises :class:`InstallError`.  (Used by install-by-version.)"""
    target = release_index_url(url)
    _status, body, _etag = _fetch(target)
    try:
        payload = json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise InstallError(
            f"The release index is not valid JSON: {exc}", code="invalid", status=502
        ) from exc
    entries, _skipped = parse_index(payload)
    return entries


def check(
    root: str,
    *,
    url: str | None = None,
    force: bool = False,
    max_age_s: float = CHECK_INTERVAL_S,
    now: float | None = None,
) -> CheckResult:
    """Answer "is there a newer embed", using and updating the ETag cache.

    Never raises: an unreachable index, a 403 and malformed JSON all come back
    as ``available=False`` with the sentence Settings shows.  A cached answer
    younger than *max_age_s* is returned untouched unless *force*.
    """
    target = release_index_url(url)
    stamp = time.time() if now is None else now
    cached = read_cache(root)
    same_index = cached.get("index_url") == target
    if (
        not force
        and same_index
        and isinstance(cached.get("checked_at"), (int, float))
        and stamp - float(cached["checked_at"]) < max_age_s
        and "available" in cached
    ):
        return CheckResult(
            available=bool(cached.get("available")),
            message=cached.get("message"),
            releases=list(cached.get("releases") or []),
            checked_at=float(cached["checked_at"]),
            from_cache=True,
            index_url=target,
        )

    etag = cached.get("etag") if same_index else None
    try:
        status, body, new_etag = _fetch(
            target, etag=etag if isinstance(etag, str) else None
        )
        if status == 304 and same_index:
            result = CheckResult(
                available=bool(cached.get("available", True)),
                message=cached.get("message"),
                releases=list(cached.get("releases") or []),
                checked_at=stamp,
                index_url=target,
            )
        else:
            payload = json.loads(body.decode("utf-8"))
            entries, skipped = parse_index(payload)
            message = None
            if not entries and skipped:
                message = "; ".join(skipped[:3])
            result = CheckResult(
                available=True,
                message=message,
                releases=entries,
                checked_at=stamp,
                index_url=target,
            )
            etag = new_etag
    except InstallError as exc:
        result = CheckResult(
            available=False, message=str(exc), checked_at=stamp, index_url=target
        )
        etag = None
    except ValueError as exc:
        result = CheckResult(
            available=False,
            message=f"The release index is not valid JSON: {exc}",
            checked_at=stamp,
            index_url=target,
        )
        etag = None

    payload_out = result.as_dict()
    payload_out["etag"] = etag if isinstance(etag, str) else None
    # The last automatic outcome outlives any number of checks: it is what
    # Settings shows ("installed 0.3.12", "needs a newer TI-Toolbox"), and a
    # later check that merely finds nothing new must not erase it.
    if isinstance(cached.get("last_outcome"), dict):
        payload_out["last_outcome"] = cached["last_outcome"]
    write_cache(root, payload_out)
    return result


def record_outcome(
    root: str, outcome: "UpdateOutcome", *, at: float | None = None
) -> None:
    """Persist what the last automatic pass decided, so Settings can say it after a restart."""
    cached = read_cache(root)
    payload = outcome.as_dict()
    payload["at"] = time.time() if at is None else at
    cached["last_outcome"] = payload
    write_cache(root, cached)


def read_outcome(root: str) -> dict[str, Any] | None:
    """The persisted last outcome, or ``None`` if nothing has run yet."""
    value = read_cache(root).get("last_outcome")
    return value if isinstance(value, dict) else None


def record_installed_release(root: str, version: str, url: str) -> None:
    """Remember that *version* came from a **release**, not from a hand install.

    This is the provenance the "is there a newer one" question actually needs.
    The dev container is the proof: it carries a hand-installed embed calling
    itself ``0.4.0`` from a pre-release branch, which is *numerically newer* than
    the first real release (``0.3.12``).  Comparing the candidate against
    whatever happens to be active would therefore decide "you are up to date"
    forever, on the one machine where the check matters most.  So the baseline is
    the newest version this updater itself installed from a release; a manual or
    dev bundle blocks nothing.
    """
    cached = read_cache(root)
    released = cached.get("released")
    if not isinstance(released, dict):
        released = {}
    released[version] = {"url": url, "at": time.time()}
    cached["released"] = released
    write_cache(root, cached)


def newest_release_installed(root: str) -> str | None:
    """The newest **release-sourced** version still present in *root*, or ``None``."""
    released = read_cache(root).get("released")
    if not isinstance(released, dict):
        return None
    present = [v for v in released if store.find_installed(root, v) is not None]
    if not present:
        return None
    return max(present, key=store.version_key)


def last_check(root: str) -> dict[str, Any] | None:
    """The persisted last check (time, availability, message), or ``None``."""
    cached = read_cache(root)
    if not isinstance(cached.get("checked_at"), (int, float)):
        return None
    return {
        "checked_at": float(cached["checked_at"]),
        "available": bool(cached.get("available")),
        "message": cached.get("message"),
        "index_url": cached.get("index_url"),
    }


# ── applying it ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UpdateOutcome:
    """What the auto-update decided, in the words Settings and the log use."""

    action: (
        str  # "installed" | "available" | "current" | "unsupported" | "failed" | "off"
    )
    message: str
    version: str | None = None
    protocol: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "message": self.message,
            "version": self.version,
            "protocol": self.protocol,
        }


def newest_candidate(
    releases: list[dict[str, Any]], *, current: str | None
) -> dict[str, Any] | None:
    """The newest entry strictly newer than *current* (compatible or not).

    Deliberately *not* filtered to compatible releases: A1 requires a release
    past the supported range to be **reported** as needing a TI-Toolbox update,
    and filtering it out here would silently show "you are up to date" instead.
    """
    if not releases:
        return None
    ordered = sorted(
        releases, key=lambda e: store.version_key(e["version"]), reverse=True
    )
    newest = ordered[0]
    if current and store.version_key(newest["version"]) <= store.version_key(current):
        return None
    return newest


def prune(
    root: str, *, keep: int = KEEP_INSTALLED, active: str | None = None
) -> list[str]:
    """Keep the newest *keep* installed bundles (and *active*); return what went.

    A4's other half: rollback needs somewhere to go back to, and an install root
    that grows one 5-6 MB bundle per Tetravox release forever is a disk leak.
    """
    installed = store.list_installed(root)
    removed: list[str] = []
    for release in installed[keep:]:
        if release.version == active or release.version == store.read_pin(root):
            continue
        try:
            store.remove_version(root, release.version)
            removed.append(release.version)
        except (store.StoreError, OSError):
            continue
    return removed


def run_check_and_maybe_install(
    root: str,
    *,
    current_version: str | None = None,
    auto: bool | None = None,
    url: str | None = None,
    force: bool = False,
) -> UpdateOutcome:
    """A3 — one pass of the policy.  Safe to call from a thread; never raises.

    The order is the policy: check (always), decide (always), install (only when
    the policy says so *and* the protocol is inside the range).

    *current_version* is the baseline to compare against and defaults to
    :func:`newest_release_installed` -- **not** to whatever is active.  See that
    function for why: the active bundle may be a hand-installed dev build whose
    version number is ahead of every real release.
    """
    auto_update = read_policy(root) if auto is None else auto
    if current_version is None:
        current_version = newest_release_installed(root)
    result = check(root, url=url, force=force)
    if not result.available:
        return UpdateOutcome("failed", result.message or "Could not check for updates")
    candidate = newest_candidate(result.releases, current=current_version)
    if candidate is None:
        if not result.releases:
            return UpdateOutcome(
                "current",
                result.message
                or "No Tetravox release carries an installable embed bundle yet",
            )
        return UpdateOutcome(
            "current",
            (
                f"Tetravox {current_version} is the newest release"
                if current_version
                else f"Tetravox {result.releases[0]['version']} is already the newest release"
            ),
            version=current_version,
        )
    version = candidate["version"]
    protocol = candidate["protocol"]
    if not protocol_supported(protocol):
        return UpdateOutcome(
            "unsupported",
            f"Tetravox {version} speaks embed protocol {protocol}, which this "
            "TI-Toolbox cannot host. Update TI-Toolbox to use it.",
            version=version,
            protocol=protocol,
        )
    if store.find_installed(root, version) is not None:
        store.write_pin(root, version)
        record_installed_release(root, version, candidate["url"])
        return UpdateOutcome(
            "installed",
            f"Tetravox {version} was already downloaded; it is now active",
            version=version,
            protocol=protocol,
        )
    if not auto_update:
        return UpdateOutcome(
            "available",
            f"Tetravox {version} is available (automatic updates are off)",
            version=version,
            protocol=protocol,
        )
    try:
        install.install_from_url(
            candidate["url"], root=root, sha256=candidate["sha256"], activate=True
        )
    except InstallError as exc:
        return UpdateOutcome(
            "failed", f"Could not install Tetravox {version}: {exc}", version=version
        )
    record_installed_release(root, version, candidate["url"])
    prune(root, active=version)
    return UpdateOutcome(
        "installed",
        f"Tetravox {version} installed and active — reload the viewer to use it",
        version=version,
        protocol=protocol,
    )
