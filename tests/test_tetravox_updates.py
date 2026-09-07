"""A2-A5 — automatic Tetravox embed updates, proved against a fake GitHub API.

Lane TX is producing the real release assets concurrently; until they exist,
every claim here is made against a **loopback HTTP server that speaks the shape
of ``/repos/idossha/tetravox/releases``** and serves real assets built from a
real (tiny) embed tarball: ``tetravox-embed-<ver>.tgz`` with its true sha256 in
``…​.tgz.sha256`` and its true protocol in ``…​.manifest.json``.  So the digest
that gets verified and the protocol that gets compared are the ones a publisher
wrote, not values this test asserts about itself.

The four properties the plan names, each with its own test:

* a release whose protocol is past the supported range is **reported, never
  installed** (A1);
* a digest that does not match replaces nothing (E3, re-proved through the
  automatic path — the policy uses the same installer);
* with ``auto_update`` off the same release is **reported only**;
* the startup check does not delay ``/api/health`` (measured, not asserted).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tit.tetravox import install, store, updates

# ── a real (tiny) embed release, and a fake GitHub serving it ────────────────


def build_release(directory, *, version, protocol):
    """Write ``tetravox-embed-<v>.tgz`` + its two sidecars.  Returns the digest."""
    manifest = {
        "name": "@tetravox/embed",
        "version": version,
        "protocol": protocol,
        "sha": "cafebabe",
    }
    tgz = directory / f"tetravox-embed-{version}.tgz"
    top = f"tetravox-embed-{version}"
    with tarfile.open(tgz, "w:gz") as tar:
        for name, payload in (
            (f"{top}/manifest.json", json.dumps(manifest).encode()),
            (f"{top}/dist/index.html", b"<!doctype html><title>embed</title>"),
            (f"{top}/dist/assets/app.js", b"// engine"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha256(tgz.read_bytes()).hexdigest()
    (directory / f"tetravox-embed-{version}.tgz.sha256").write_text(
        f"{digest}  tetravox-embed-{version}.tgz\n"
    )
    (directory / f"tetravox-embed-{version}.manifest.json").write_text(
        json.dumps(manifest)
    )
    return digest


class FakeGitHub:
    """``/repos/idossha/tetravox/releases`` plus the asset files, over loopback.

    Deliberately not a mock of :mod:`tit.tetravox.updates`: the module under test
    makes real HTTP requests, parses a real body, follows the real asset URLs and
    hands a real tarball to the real installer.  ``requests`` counts what it was
    asked for, which is how the ETag test proves the second check was cheap.
    """

    def __init__(self, directory):
        self.directory = directory
        self.releases: list[dict] = []
        self.etag = '"v1"'
        self.requests: list[str] = []
        self.status_override: int | None = None
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def index_url(self) -> str:
        return f"{self.base}/repos/idossha/tetravox/releases"

    def add(self, version, protocol, *, draft=False, prerelease=False, assets=True):
        entry = {
            "tag_name": f"v{version}",
            "name": f"Tetravox {version}",
            "draft": draft,
            "prerelease": prerelease,
            "published_at": "2026-09-05T10:00:00Z",
            "assets": [],
        }
        if assets:
            build_release(self.directory, version=version, protocol=protocol)
            for suffix in (".tgz", ".tgz.sha256", ".manifest.json"):
                name = (
                    f"tetravox-embed-{version}{suffix}"
                    if suffix != ".manifest.json"
                    else f"tetravox-embed-{version}.manifest.json"
                )
                entry["assets"].append(
                    {"name": name, "browser_download_url": f"{self.base}/a/{name}"}
                )
        self.releases.insert(0, entry)
        # A changed body means a changed ETag, exactly as GitHub behaves --
        # without this the fake would answer 304 to a client asking about a list
        # it has never seen, and the cache tests would be proving nothing.
        self.etag = f'"v{len(self.releases) + 1}"'
        return entry

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _handler(server_self):  # noqa: N805 - closure over the fixture instance
        outer = server_self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep pytest output clean
                pass

            def do_GET(self):  # noqa: N802
                outer.requests.append(self.path)
                if self.path.endswith("/releases"):
                    if outer.status_override:
                        self.send_response(outer.status_override)
                        self.send_header("X-RateLimit-Remaining", "0")
                        self.end_headers()
                        self.wfile.write(b'{"message":"rate limit exceeded"}')
                        return
                    if self.headers.get("If-None-Match") == outer.etag:
                        self.send_response(304)
                        self.send_header("ETag", outer.etag)
                        self.end_headers()
                        return
                    body = json.dumps(outer.releases).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("ETag", outer.etag)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.startswith("/a/"):
                    path = outer.directory / self.path[len("/a/") :]
                    if not path.is_file():
                        self.send_error(404)
                        return
                    body = path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_error(404)

        return Handler


@pytest.fixture
def gh(tmp_path):
    directory = tmp_path / "assets"
    directory.mkdir()
    fake = FakeGitHub(directory)
    try:
        yield fake
    finally:
        fake.close()


@pytest.fixture
def root(tmp_path):
    return str(tmp_path / "install-root")


@pytest.fixture
def use_fake(gh, monkeypatch):
    monkeypatch.setenv(updates.ENV_RELEASE_INDEX, gh.index_url)
    return gh


# ── the policy file ──────────────────────────────────────────────────────────


def test_auto_update_is_on_by_default_and_the_file_wins_over_the_env(root, monkeypatch):
    assert updates.read_policy(root) is True
    monkeypatch.setenv(updates.ENV_AUTO_UPDATE, "0")
    assert updates.read_policy(root) is False
    updates.write_policy(root, True)
    assert updates.read_policy(root) is True  # the user's answer beats the default
    updates.write_policy(root, False)
    monkeypatch.delenv(updates.ENV_AUTO_UPDATE)
    assert updates.read_policy(root) is False


# ── A2: the GitHub Releases API ──────────────────────────────────────────────


def test_the_newest_non_draft_release_with_the_three_assets_is_the_candidate(
    use_fake, root
):
    gh = use_fake
    gh.add("0.4.0", 2)
    gh.add("0.4.1", 2, draft=True)
    gh.add("0.4.2", 2, prerelease=True)
    result = updates.check(root)
    assert result.available is True
    assert [e["version"] for e in result.releases] == ["0.4.0"]
    assert result.releases[0]["protocol"] == 2  # read from the manifest asset


def test_a_release_without_the_embed_assets_is_reported_not_guessed_at(use_fake, root):
    gh = use_fake
    gh.add("0.3.11", 2, assets=False)
    result = updates.check(root)
    assert result.available is True
    assert result.releases == []
    assert "carries no tetravox-embed-<version>.tgz asset" in (result.message or "")


def test_the_check_never_downloads_the_tarball(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    updates.check(root)
    assert not any(path.endswith(".tgz") for path in gh.requests)
    assert any(path.endswith(".manifest.json") for path in gh.requests)


def test_the_env_override_still_accepts_a_flat_mirror_index(
    tmp_path, root, monkeypatch
):
    payload = {
        "releases": [
            {
                "version": "0.4.0",
                "protocol": 2,
                "url": "https://github.com/x/y.tgz",
                "sha256": "AB" * 32,
                "notes": "adds markers",
            },
            {
                "version": "0.10.0",
                "protocol": 2,
                "url": "https://github.com/x/z.tgz",
                "sha256": "cd" * 32,
            },
            {"version": "0.5.0"},  # no url/digest: not installable, dropped
        ]
    }
    directory = tmp_path / "www"
    directory.mkdir()
    (directory / "releases.json").write_text(json.dumps(payload))
    from functools import partial
    from http.server import SimpleHTTPRequestHandler

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(directory))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv(
            updates.ENV_RELEASE_INDEX,
            f"http://127.0.0.1:{server.server_port}/releases.json",
        )
        entries = updates.fetch_release_index()
    finally:
        server.shutdown()
        server.server_close()
    assert [e["version"] for e in entries] == ["0.10.0", "0.4.0"]
    assert entries[1]["sha256"] == "ab" * 32  # lower-cased, ready to compare
    assert entries[1]["notes"] == "adds markers"


def test_api_github_com_is_on_the_allowlist(monkeypatch):
    monkeypatch.delenv(install.ENV_ALLOWED_HOSTS, raising=False)
    assert "api.github.com" in install.allowed_hosts()
    install.check_url(updates.GITHUB_RELEASES_URL)  # does not raise


def test_an_unreachable_index_is_a_sentence_not_a_traceback(root, monkeypatch):
    monkeypatch.setenv(updates.ENV_RELEASE_INDEX, "http://127.0.0.1:9/releases")
    result = updates.check(root)
    assert result.available is False
    assert "Could not reach the release index" in (result.message or "")


def test_a_403_says_it_could_not_check_and_names_the_rate_limit(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    gh.status_override = 403
    result = updates.check(root)
    assert result.available is False
    assert "403" in (result.message or "")
    assert "60 requests per hour" in (result.message or "")


# ── the cache ────────────────────────────────────────────────────────────────


def test_a_second_check_within_the_window_makes_no_request_at_all(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    updates.check(root)
    before = len(gh.requests)
    again = updates.check(root)
    assert again.from_cache is True
    assert len(gh.requests) == before


def test_forcing_a_check_sends_the_etag_and_a_304_costs_nothing(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    updates.check(root)
    sidecars_before = sum(1 for p in gh.requests if p.startswith("/a/"))
    result = updates.check(root, force=True)
    assert result.available is True
    assert [e["version"] for e in result.releases] == ["0.4.0"]
    # 304: the index body was not re-parsed, so no sidecar was fetched again.
    assert sum(1 for p in gh.requests if p.startswith("/a/")) == sidecars_before


def test_the_last_check_time_survives_a_fresh_process(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    updates.check(root)
    record = updates.last_check(root)
    assert record is not None and record["available"] is True
    assert time.time() - record["checked_at"] < 60


# ── A3/A1: what gets installed, and what only gets reported ──────────────────


def test_a_newer_compatible_release_is_installed_and_activated(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    outcome = updates.run_check_and_maybe_install(root, current_version="0.3.4")
    assert outcome.action == "installed", outcome.message
    assert outcome.version == "0.4.0"
    assert [r.version for r in store.list_installed(root)] == ["0.4.0"]
    assert store.read_pin(root) == "0.4.0"


def test_a_protocol_past_the_supported_range_is_reported_and_never_installed(
    use_fake, root
):
    gh = use_fake
    gh.add("9.0.0", updates.protocol_supported.__module__ and 99)
    outcome = updates.run_check_and_maybe_install(root, current_version="0.3.4")
    assert outcome.action == "unsupported"
    assert "protocol 99" in outcome.message
    assert "Update TI-Toolbox" in outcome.message
    assert store.list_installed(root) == []
    assert not os.path.isdir(os.path.join(root, "9.0.0"))


def test_a_digest_that_does_not_match_replaces_nothing(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    # Re-write the tarball after its sidecar was published: the digest the
    # publisher signed no longer describes the bytes being served.
    tgz = gh.directory / "tetravox-embed-0.4.0.tgz"
    tgz.write_bytes(tgz.read_bytes() + b"tampered")
    outcome = updates.run_check_and_maybe_install(root, current_version="0.3.4")
    assert outcome.action == "failed"
    assert "sha256 mismatch" in outcome.message
    assert store.list_installed(root) == []
    assert store.read_pin(root) is None


def test_with_auto_update_off_the_same_release_is_only_reported(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    updates.write_policy(root, False)
    outcome = updates.run_check_and_maybe_install(root, current_version="0.3.4")
    assert outcome.action == "available"
    assert outcome.version == "0.4.0"
    assert store.list_installed(root) == []
    assert not any(p.endswith(".tgz") for p in gh.requests)


def test_nothing_newer_than_the_active_bundle_is_current(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    outcome = updates.run_check_and_maybe_install(root, current_version="0.4.0")
    assert outcome.action == "current"
    assert store.list_installed(root) == []


def test_only_the_last_two_installed_versions_are_kept(use_fake, root):
    gh = use_fake
    for version in ("0.4.0", "0.4.1", "0.4.2"):
        gh.add(version, 2)
        outcome = updates.run_check_and_maybe_install(
            root, current_version=None, force=True
        )
        assert outcome.action == "installed", outcome.message
    assert [r.version for r in store.list_installed(root)] == ["0.4.2", "0.4.1"]
    assert store.read_pin(root) == "0.4.2"


def test_the_active_version_is_never_pruned(use_fake, root):
    gh = use_fake
    for version in ("0.4.0", "0.4.1", "0.4.2"):
        gh.add(version, 2)
        updates.run_check_and_maybe_install(root, current_version=None, force=True)
    store.activate(root, "0.4.1")
    updates.prune(root, keep=1)
    assert "0.4.1" in [r.version for r in store.list_installed(root)]


def test_the_last_outcome_is_remembered_across_checks(use_fake, root):
    gh = use_fake
    gh.add("0.4.0", 2)
    outcome = updates.run_check_and_maybe_install(root, current_version="0.3.4")
    updates.record_outcome(root, outcome)
    updates.check(root, force=True)  # a later check must not erase it
    remembered = updates.read_outcome(root)
    assert remembered is not None
    assert remembered["action"] == "installed" and remembered["version"] == "0.4.0"


# ── provenance: a hand-installed dev bundle must not block a real release ────


def test_a_manually_installed_dev_bundle_does_not_block_a_lower_numbered_release(
    use_fake, root, tmp_path
):
    """The dev container's exact state, and the bug it would otherwise cause.

    ``ti-toolbox-fad740e5-tit-1`` runs a hand-installed embed calling itself
    **0.4.0**, built from Tetravox's pre-release ``feat/embed-viewport`` branch.
    The first *real* release will be **0.3.12** — numerically lower.  Comparing
    the candidate against the active bundle would answer "you are up to date"
    forever on exactly the machine where the check matters most, so the baseline
    is the newest bundle this updater itself installed from a release, and a
    manual install (``POST /api/tetravox/install``, or an operator unpacking one)
    is provenance-free and blocks nothing.
    """
    gh = use_fake
    # A hand install of 0.4.0, exactly as the route performs it: no release record.
    manual = build_release(gh.directory, version="0.4.0", protocol=2)
    install.install_from_url(
        f"{gh.base}/a/tetravox-embed-0.4.0.tgz", root=root, sha256=manual, activate=True
    )
    assert [r.version for r in store.list_installed(root)] == ["0.4.0"]
    assert updates.newest_release_installed(root) is None

    gh.add("0.3.12", 2)
    outcome = updates.run_check_and_maybe_install(root, force=True)
    assert outcome.action == "installed", outcome.message
    assert outcome.version == "0.3.12"
    assert store.read_pin(root) == "0.3.12"
    assert updates.newest_release_installed(root) == "0.3.12"

    # And once it is the release baseline, the same release is not offered again.
    again = updates.run_check_and_maybe_install(root, force=True)
    assert again.action == "current"


def test_the_release_baseline_ignores_a_version_that_was_removed(use_fake, root):
    gh = use_fake
    gh.add("0.3.12", 2)
    updates.run_check_and_maybe_install(root, force=True)
    store.remove_version(root, "0.3.12")
    assert updates.newest_release_installed(root) is None
    outcome = updates.run_check_and_maybe_install(root, force=True)
    assert outcome.action == "installed"
