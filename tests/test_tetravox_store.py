"""E2 — where the embed comes from: two roots, a pin, newest compatible wins.

Every test here fixes the install root to a tmp directory.  The real root is
``<user config>/tetravox/embed``, which inside the container is a **host**
directory mounted from ``~/.config/ti-toolbox`` -- a test that read it would pass
or fail depending on what the developer had installed.
"""

from __future__ import annotations

import json
import os

import pytest

from tit.tetravox import store


def make_bundle(directory, version, protocol=1, *, name="@tetravox/embed", index=True):
    """A minimal on-disk bundle: ``manifest.json`` (+ ``index.html`` unless suppressed)."""
    os.makedirs(directory, exist_ok=True)
    manifest = {"name": name, "version": version, "protocol": protocol}
    with open(os.path.join(directory, "manifest.json"), "w") as fh:
        json.dump(manifest, fh)
    if index:
        with open(os.path.join(directory, "index.html"), "w") as fh:
            fh.write(f"<html>{version}</html>")
    return str(directory)


@pytest.fixture()
def roots(tmp_path):
    """``(baked_dir, install_root)`` with a baked 0.3.4 and an empty install root."""
    baked = make_bundle(tmp_path / "opt" / "embed", "0.3.4", 1)
    root = str(tmp_path / "config" / "tetravox" / "embed")
    return baked, root


def test_version_key_orders_numerically_and_puts_prereleases_below_the_release():
    versions = ["0.9.9", "0.10.0", "0.4.0", "0.4.0-rc1", "1.0.0"]
    assert sorted(versions, key=store.version_key) == [
        "0.4.0-rc1",
        "0.4.0",
        "0.9.9",
        "0.10.0",
        "1.0.0",
    ]


def test_is_version_name_rejects_traversal_and_reserved_names():
    assert store.is_version_name("0.4.0")
    assert store.is_version_name("1.0.0-rc.1+build2")
    for bad in ("..", "../0.4.0", "/0.4.0", ".hidden", "active.json", "baked", ""):
        assert not store.is_version_name(bad), bad


def test_describe_needs_both_a_manifest_and_an_index(tmp_path):
    """A directory that cannot be served is not a release.

    Reporting one would show a version in Settings that 404s the moment the
    viewer opens it.
    """
    no_index = make_bundle(tmp_path / "a", "0.4.0", index=False)
    assert store.describe(no_index, "installed") is None
    no_manifest = tmp_path / "b"
    no_manifest.mkdir()
    (no_manifest / "index.html").write_text("<html></html>")
    assert store.describe(str(no_manifest), "installed") is None


def test_describe_reports_protocol_features_and_compatibility(tmp_path):
    one = store.describe(make_bundle(tmp_path / "p1", "0.3.4", 1), "baked")
    assert one is not None
    assert (one.version, one.protocol, one.compatible) == ("0.3.4", 1, True)
    assert "markers" not in one.features and "cursor" in one.features
    two = store.describe(make_bundle(tmp_path / "p2", "0.4.0", 2), "installed")
    assert two is not None and two.compatible
    assert {"markers", "pick", "camera"} <= set(two.features)
    far = store.describe(make_bundle(tmp_path / "p9", "9.0.0", 99), "installed")
    assert far is not None and far.protocol == 99 and not far.compatible


def test_manifest_declared_features_win_over_the_protocol_map(tmp_path):
    """E1: a future embed can name a feature this build has never heard of.

    That is what makes an additive Tetravox release usable with no change here.
    """
    directory = tmp_path / "declared"
    make_bundle(directory, "0.5.0", 2)
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["features"] = ["markers", "clipping"]
    (directory / "manifest.json").write_text(json.dumps(manifest))
    release = store.describe(str(directory), "installed")
    assert release is not None
    assert release.features == ("clipping", "markers")


def test_baked_wins_when_nothing_is_installed(roots):
    baked, root = roots
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.path == baked
    assert resolved.release is not None and resolved.release.source == "baked"
    assert "baked into the image" in resolved.reason


def test_newest_compatible_installed_beats_the_baked_floor(tmp_path, roots):
    baked, root = roots
    make_bundle(os.path.join(root, "0.4.0"), "0.4.0", 2)
    make_bundle(os.path.join(root, "0.3.9"), "0.3.9", 1)
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.release is not None
    assert resolved.release.version == "0.4.0"
    assert resolved.release.source == "installed"


def test_an_installed_version_outside_the_range_is_skipped(roots):
    """The floor must keep working when a future bundle is left installed.

    Without this, upgrading Tetravox past what this build speaks would leave the
    app serving a viewer it cannot drive -- with no way back short of a shell.
    """
    baked, root = roots
    make_bundle(os.path.join(root, "9.0.0"), "9.0.0", 99)
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.path == baked
    assert "supported protocol range" in resolved.reason


def test_the_pin_selects_an_installed_version_and_baked_is_the_rollback(roots):
    baked, root = roots
    make_bundle(os.path.join(root, "0.4.0"), "0.4.0", 2)
    make_bundle(os.path.join(root, "0.5.0"), "0.5.0", 2)
    store.write_pin(root, "0.4.0")
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.release is not None and resolved.release.version == "0.4.0"
    # Rollback all the way to the image's own copy, without deleting anything.
    store.write_pin(root, store.BAKED)
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.path == baked
    assert store.list_installed(root)[0].version == "0.5.0"
    # Clearing the pin returns to newest-compatible.
    store.clear_pin(root)
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.release is not None and resolved.release.version == "0.5.0"


def test_a_pin_to_a_removed_version_falls_back_and_says_so(roots):
    baked, root = roots
    make_bundle(os.path.join(root, "0.4.0"), "0.4.0", 2)
    store.write_pin(root, "0.4.0")
    store.remove_version(root, "0.4.0")
    assert store.read_pin(root) is None  # removing the pinned version clears the pin
    store.write_pin(root, "0.9.9")  # a pin whose directory was deleted by hand
    resolved = store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert resolved.path == baked
    assert "0.9.9 is not installed" in resolved.reason


def test_the_dev_override_wins_over_everything(tmp_path, roots):
    baked, root = roots
    make_bundle(os.path.join(root, "9.9.9"), "9.9.9", 1)
    override = make_bundle(tmp_path / "dev" / "embed", "0.0.0-dev", 1)
    resolved = store.resolve_active(override_dir=override, baked_dir=baked, root=root)
    assert resolved.path == override
    assert resolved.release is not None and resolved.release.source == "override"


def test_a_broken_dev_override_does_not_silently_fall_back(tmp_path, roots):
    """An override that points at nothing is a mistake worth seeing.

    Silently serving the baked copy instead would have the developer debugging a
    bundle they are not looking at.
    """
    baked, root = roots
    resolved = store.resolve_active(
        override_dir=str(tmp_path / "missing"), baked_dir=baked, root=root
    )
    assert resolved.release is None
    assert "no readable embed bundle" in resolved.reason


def test_activate_and_remove_report_unknown_versions(roots):
    _baked, root = roots
    with pytest.raises(store.StoreError, match="Not installed: 0.4.0"):
        store.activate(root, "0.4.0")
    with pytest.raises(store.StoreError, match="Not installed: 0.4.0"):
        store.remove_version(root, "0.4.0")
    with pytest.raises(store.StoreError):
        store.remove_version(root, "../etc")


def test_install_root_prefers_the_env_var_over_the_user_config(monkeypatch, tmp_path):
    monkeypatch.setenv(store.ENV_INSTALL_ROOT, str(tmp_path / "elsewhere"))
    assert store.install_root() == str(tmp_path / "elsewhere")
    assert store.install_root("/explicit") == "/explicit"


def test_resolution_never_creates_the_install_root(roots):
    """It runs on every ``/tetravox/`` request; a read must not write."""
    baked, root = roots
    store.resolve_active(override_dir=None, baked_dir=baked, root=root)
    assert not os.path.exists(root)
