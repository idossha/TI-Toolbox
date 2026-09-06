"""E3 — install is explicit, verified, and never executes the tarball.

The five refusals the plan names are the first five tests: a bad digest, a
``..`` member, an absolute member, a manifest outside the protocol range, and a
failure part-way through extraction never becoming the active bundle.  Each
asserts the *state after the refusal* as well as the error, because "it raised"
is not the property that matters -- "the install root is exactly as it was" is.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import ssl
import tarfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tit.tetravox import install, store
from tests.test_tetravox_store import make_bundle

# ── fixtures: tarballs, good and hostile ─────────────────────────────────────


def _add_bytes(tar, name, payload, *, mode=0o644):
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = mode
    tar.addfile(info, io.BytesIO(payload))


def write_bundle_tarball(
    path,
    *,
    version="0.4.0",
    protocol=2,
    name="@tetravox/embed",
    top="tetravox-embed-0.4.0",
    layout="dist",
    extra_members=(),
    manifest_extra=None,
):
    """A release-shaped tarball: ``<top>/manifest.json`` + ``<top>/dist/…``."""
    manifest = {
        "name": name,
        "version": version,
        "protocol": protocol,
        "sha": "deadbeef",
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    prefix = f"{top}/" if top else ""
    inner = "dist/" if layout == "dist" else ""
    with tarfile.open(path, "w:gz") as tar:
        _add_bytes(tar, f"{prefix}manifest.json", json.dumps(manifest).encode())
        _add_bytes(
            tar, f"{prefix}{inner}index.html", f"<html>{version}</html>".encode()
        )
        _add_bytes(tar, f"{prefix}{inner}assets/app.js", b"console.log(1)\n")
        for member in extra_members:
            member(tar, prefix)
    return str(path)


def digest_of(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


@pytest.fixture()
def root(tmp_path):
    return str(tmp_path / "config" / "tetravox" / "embed")


@pytest.fixture()
def baked(tmp_path):
    return make_bundle(tmp_path / "opt" / "embed", "0.3.4", 1)


def installed_names(root):
    return sorted(os.listdir(root)) if os.path.isdir(root) else []


# ── 1. the digest is verified before anything is unpacked ────────────────────


def test_a_tarball_whose_digest_does_not_match_is_rejected_and_nothing_is_written(
    tmp_path, root
):
    archive = write_bundle_tarball(tmp_path / "bundle.tgz")
    with pytest.raises(install.InstallError) as exc:
        install.install_archive(archive, root=root, sha256="0" * 64)
    assert "sha256 mismatch" in str(exc.value)
    assert "Nothing was installed" in str(exc.value)
    assert digest_of(archive) in str(exc.value)  # the real digest, to act on
    assert not os.path.exists(root), "the install root must not even be created"


def test_a_digest_that_is_not_a_digest_is_refused_before_the_network(root):
    for bad in (None, "", "not-hex", "abc123"):
        with pytest.raises(install.InstallError):
            install.install_from_url("https://github.com/x.tgz", root=root, sha256=bad)
    assert not os.path.exists(root)


# ── 2. traversal-safe extraction ─────────────────────────────────────────────


def _escaping_member(tar, prefix):
    _add_bytes(tar, f"{prefix}../../escape.txt", b"pwned")


def _absolute_member(tar, prefix):
    _add_bytes(tar, "/tmp/tit-tetravox-absolute.txt", b"pwned")


def _symlink_member(tar, prefix):
    info = tarfile.TarInfo(f"{prefix}dist/link.js")
    info.type = tarfile.SYMTYPE
    info.linkname = "/etc/passwd"
    tar.addfile(info)


@pytest.mark.parametrize(
    "member, message",
    [
        (_escaping_member, "path traversal"),
        (_absolute_member, "absolute path"),
        (_symlink_member, "link in archive"),
    ],
)
def test_a_hostile_archive_member_is_refused_and_nothing_is_installed(
    tmp_path, root, member, message
):
    archive = write_bundle_tarball(tmp_path / "bad.tgz", extra_members=(member,))
    with pytest.raises(install.InstallError, match=message):
        install.install_archive(archive, root=root, sha256=digest_of(archive))
    assert installed_names(root) == [], "no version and no staging left behind"
    assert not os.path.exists("/tmp/tit-tetravox-absolute.txt")
    assert not os.path.exists(tmp_path / "escape.txt")


def test_member_target_rejects_a_traversal_that_hides_in_the_middle(tmp_path):
    """``a/../../b`` never starts with ``../`` — the check is on the normalised path."""
    with pytest.raises(install.InstallError, match="path traversal"):
        install._member_target(str(tmp_path), "a/../../b")


def test_safe_extract_refuses_a_device_node(tmp_path):
    archive = tmp_path / "dev.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("pkg/dev/null")
        info.type = tarfile.CHRTYPE
        tar.addfile(info)
    with pytest.raises(install.InstallError, match="special file"):
        install.safe_extract(str(archive), str(tmp_path / "out"))


# ── 3. the manifest is validated ─────────────────────────────────────────────


def test_a_protocol_outside_the_supported_range_is_refused_with_a_readable_message(
    tmp_path, root
):
    archive = write_bundle_tarball(
        tmp_path / "future.tgz", version="9.0.0", protocol=99
    )
    with pytest.raises(install.InstallError) as exc:
        install.install_archive(archive, root=root, sha256=digest_of(archive))
    message = str(exc.value)
    assert "protocol 99" in message
    assert "supports protocol 1-2" in message
    assert "Update TI-Toolbox" in message  # what to do about it
    assert installed_names(root) == []


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"name": "evil-embed"}, "expected one of"),
        ({"protocol": "two"}, "not an integer"),
        ({"version": "../etc"}, "not usable"),
    ],
)
def test_a_manifest_that_is_not_a_tetravox_embed_is_refused(
    tmp_path, root, kwargs, message
):
    archive = write_bundle_tarball(tmp_path / "bad.tgz", **kwargs)
    with pytest.raises(install.InstallError, match=message):
        install.install_archive(archive, root=root, sha256=digest_of(archive))
    assert installed_names(root) == []


def test_an_archive_with_no_manifest_is_refused(tmp_path, root):
    archive = tmp_path / "empty.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        _add_bytes(tar, "pkg/dist/index.html", b"<html></html>")
    with pytest.raises(install.InstallError, match="no manifest.json"):
        install.install_archive(str(archive), root=root, sha256=digest_of(archive))


def test_an_archive_with_no_index_html_is_refused(tmp_path, root):
    archive = tmp_path / "noindex.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        _add_bytes(
            tar,
            "pkg/manifest.json",
            json.dumps(
                {"name": "@tetravox/embed", "version": "0.4.0", "protocol": 2}
            ).encode(),
        )
        _add_bytes(tar, "pkg/dist/app.js", b"1")
    with pytest.raises(install.InstallError, match="no index.html"):
        install.install_archive(str(archive), root=root, sha256=digest_of(archive))


# ── 4. a half-extracted install never becomes active ─────────────────────────


def test_a_failure_part_way_through_never_becomes_the_active_bundle(
    tmp_path, root, baked
):
    """The refusal happens *after* real files have been written to staging.

    The hostile member is last in the archive, so ``manifest.json``,
    ``index.html`` and ``assets/app.js`` are already on disk when extraction
    stops.  Everything must still be gone, and the resolver must still be
    serving the baked floor.
    """
    good = write_bundle_tarball(tmp_path / "good.tgz")
    install.install_archive(good, root=root, sha256=digest_of(good))
    assert installed_names(root) == ["0.4.0", "active.json"]

    bad = write_bundle_tarball(
        tmp_path / "bad.tgz",
        version="0.5.0",
        top="tetravox-embed-0.5.0",
        extra_members=(_escaping_member,),
    )
    with pytest.raises(install.InstallError):
        install.install_archive(bad, root=root, sha256=digest_of(bad))

    assert installed_names(root) == [
        "0.4.0",
        "active.json",
    ], "the failed install left a directory or staging behind"
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.release is not None and resolved.release.version == "0.4.0"


def test_a_reinstall_of_the_same_version_keeps_it_servable_throughout(tmp_path, root):
    """``os.replace`` cannot rename onto a non-empty directory.

    The naive fix (rmtree the old one first) leaves the version missing if the
    move then fails; this moves it aside and only deletes it once the new one is
    in place.
    """
    first = write_bundle_tarball(tmp_path / "a.tgz")
    install.install_archive(first, root=root, sha256=digest_of(first))
    second = write_bundle_tarball(
        tmp_path / "b.tgz", manifest_extra={"sha": "second-build"}
    )
    release = install.install_archive(second, root=root, sha256=digest_of(second))
    assert release.version == "0.4.0" and release.sha == "second-build"
    assert installed_names(root) == ["0.4.0", "active.json"]
    assert os.path.isfile(os.path.join(root, "0.4.0", "index.html"))


# ── 5. the happy path, and what it leaves on disk ────────────────────────────


def test_a_release_tarball_installs_flat_the_way_the_image_bakes_it(tmp_path, root):
    """``dist/`` + ``manifest.json`` is flattened into one served directory.

    The Dockerfile does exactly this for the baked floor
    (``cp -r /tmp/tvx/dist/. …`` + ``cp /tmp/tvx/manifest.json …``), so an
    installed bundle and the baked one are served by the same code path.
    """
    archive = write_bundle_tarball(tmp_path / "bundle.tgz")
    release = install.install_archive(archive, root=root, sha256=digest_of(archive))
    served = os.path.join(root, "0.4.0")
    assert release.path == served
    assert sorted(os.listdir(served)) == ["assets", "index.html", "manifest.json"]
    assert release.protocol == 2 and release.compatible
    assert store.read_pin(root) == "0.4.0"  # install activates
    # No executable bits on a static bundle.
    assert os.stat(os.path.join(served, "index.html")).st_mode & 0o111 == 0


def test_a_flat_tarball_without_a_dist_directory_also_installs(tmp_path, root):
    archive = write_bundle_tarball(tmp_path / "flat.tgz", layout="flat")
    release = install.install_archive(archive, root=root, sha256=digest_of(archive))
    assert os.path.isfile(os.path.join(release.path, "index.html"))


def test_install_without_activate_leaves_the_pin_alone(tmp_path, root, baked):
    archive = write_bundle_tarball(tmp_path / "bundle.tgz")
    install.install_archive(
        archive, root=root, sha256=digest_of(archive), activate=False
    )
    assert store.read_pin(root) is None


# ── 6. the download allowlist ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, message",
    [
        ("http://evil.example/b.tgz", "Only https"),
        ("ftp://github.com/b.tgz", "Only https"),
        ("file:///etc/passwd", "Only https"),
        ("https://evil.example/b.tgz", "not an allowed download host"),
        ("https://user:pw@github.com/b.tgz", "must not carry credentials"),
    ],
)
def test_a_url_off_the_allowlist_is_refused(url, message):
    with pytest.raises(install.InstallError, match=message):
        install.check_url(url)


def test_the_allowlist_is_extensible_by_env(monkeypatch):
    with pytest.raises(install.InstallError):
        install.check_url("https://mirror.example/b.tgz")
    monkeypatch.setenv(install.ENV_ALLOWED_HOSTS, "mirror.example")
    install.check_url("https://mirror.example/b.tgz")


def test_loopback_http_is_allowed_because_the_digest_is_the_control():
    install.check_url("http://127.0.0.1:8123/bundle.tgz")
    install.check_url("http://localhost:8123/bundle.tgz")


def test_a_redirect_off_the_allowlist_is_refused(monkeypatch):
    """An open redirect on an allowed host would otherwise bypass the allowlist."""
    handler = install._AllowlistRedirectHandler()
    with pytest.raises(install.InstallError, match="not an allowed download host"):
        handler.redirect_request(
            None, None, 302, "Found", {}, "https://evil.example/payload.tgz"
        )


# ── 6b. TLS on the interpreter the server actually runs on ───────────────────


def test_the_ssl_context_falls_back_to_certifi_when_the_interpreter_has_no_ca_store(
    monkeypatch,
):
    """Measured in the dev container: ``simnibs_python``'s OpenSSL points at the
    conda build-time placeholder paths, which do not exist in the image, so every
    https request failed ``CERTIFICATE_VERIFY_FAILED`` -- the only real-world
    install (from GitHub) could never have worked.
    """
    certifi = pytest.importorskip("certifi")
    monkeypatch.setattr(
        ssl,
        "get_default_verify_paths",
        lambda: ssl.DefaultVerifyPaths(
            None,
            None,
            "SSL_CERT_FILE",
            "/nonexistent/conda/placeholder/cert.pem",
            "SSL_CERT_DIR",
            "/nonexistent/conda/placeholder/certs",
        ),
    )
    assert not install._default_trust_store_is_usable()
    context = install.ssl_context()
    assert context.verify_mode is ssl.CERT_REQUIRED  # never "just turn it off"
    assert context.cert_store_stats()["x509_ca"] > 0, "no CAs loaded from certifi"
    assert os.path.exists(certifi.where())


def test_the_ssl_context_prefers_a_real_system_store(monkeypatch, tmp_path):
    """An operator's own CA bundle keeps working; certifi is only the fallback."""
    bundle = tmp_path / "cert.pem"
    bundle.write_text("")
    monkeypatch.setattr(
        ssl,
        "get_default_verify_paths",
        lambda: ssl.DefaultVerifyPaths(
            str(bundle), None, "SSL_CERT_FILE", str(bundle), "SSL_CERT_DIR", None
        ),
    )
    assert install._default_trust_store_is_usable()


# ── 7. end to end over loopback http, including the release index ────────────


@pytest.fixture()
def http_dir(tmp_path):
    """A directory served over loopback http; yields ``(base_url, directory)``."""
    directory = tmp_path / "www"
    directory.mkdir()
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", directory
    finally:
        server.shutdown()
        server.server_close()


def test_install_from_url_downloads_verifies_and_activates(http_dir, root, baked):
    base, directory = http_dir
    archive = write_bundle_tarball(directory / "tetravox-embed-0.4.0.tgz")
    release = install.install_from_url(
        f"{base}/tetravox-embed-0.4.0.tgz", root=root, sha256=digest_of(archive)
    )
    assert release.version == "0.4.0"
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.release is not None and resolved.release.version == "0.4.0"


def test_install_from_url_rejects_a_served_file_whose_digest_moved(http_dir, root):
    """The digest is the whole trust model: same URL, different bytes, refused."""
    base, directory = http_dir
    archive = write_bundle_tarball(directory / "b.tgz")
    good = digest_of(archive)
    write_bundle_tarball(directory / "b.tgz", manifest_extra={"sha": "swapped"})
    with pytest.raises(install.InstallError, match="sha256 mismatch"):
        install.install_from_url(f"{base}/b.tgz", root=root, sha256=good)
    assert installed_names(root) == []


# The release-index tests moved to tests/test_tetravox_updates.py with the index
# itself (A2: the GitHub Releases API, not a committed releases.json).
