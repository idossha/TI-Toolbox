"""2026-09-09: saved-view storage must not follow outward symlinks.

Authored JSON/PNG sentinel bytes are read independently from disk. Run with
pytest tests/test_viewer_storage_safety.py; scientific scene generation is elsewhere.
"""

import base64
import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from tit.paths import get_path_manager, reset_path_manager
from tit.server.routes import viewer_library as lib, viewers

PNG = b"\x89PNG\r\n\x1a\nfixture"
SCENE = {"layers": [{"id": "authored"}]}


@pytest.fixture
def storage(tmp_path):
    reset_path_manager()
    project = tmp_path / "project"
    project.mkdir()
    get_path_manager(str(project))
    directory = project / "code/ti-toolbox/viewer"
    directory.mkdir(parents=True)
    outside = tmp_path / "project-other"
    outside.mkdir()
    yield project, directory, outside
    reset_path_manager()


@pytest.mark.parametrize(
    "subdir,operation",
    [
        ("", viewers.viewer_scene_dir),
        ("presets", viewers.viewer_preset_dir),
        ("compositions", lib.composition_dir),
        ("scenes", lib.saved_scene_dir),
    ],
)
def test_outward_storage_directory_is_refused(storage, subdir, operation):
    _, directory, outside = storage
    link = directory / subdir if subdir else directory
    if not subdir:
        link.rmdir()
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(HTTPException) as exc:
        operation()
    assert exc.value.status_code == 403
    assert not list(outside.iterdir())


@pytest.mark.parametrize("kind", ["presets", "compositions", "scenes"])
def test_outward_leaf_is_not_read_or_overwritten(storage, kind):
    _, directory, outside = storage
    (directory / kind).mkdir()
    suffix = ".tetravox.json" if kind == "scenes" else ".json"
    secret = outside / "secret.json"
    secret.write_text('{"name":"private","layers":[{"id":"private"}]}')
    original = secret.read_bytes()
    target = directory / kind / ("test" + suffix)
    target.symlink_to(secret)
    if kind == "presets":
        assert viewers.viewer_presets() == {"presets": []}
        save = lambda: viewers.save_viewer_preset("test", {})
        delete = lambda: viewers.delete_viewer_preset("test")
    elif kind == "compositions":
        assert lib.list_compositions() == {"compositions": []}
        save = lambda: lib.save_composition("test", {})
        delete = lambda: lib.delete_composition("test")
    else:
        assert lib.list_scenes() == {"scenes": []}
        with pytest.raises(HTTPException):
            lib.read_scene("test")
        save = lambda: lib.save_scene("test", {"scene": SCENE})
        delete = lambda: lib.delete_scene("test")
    for action in (save, delete):
        with pytest.raises(HTTPException):
            action()
        assert secret.read_bytes() == original
        assert target.is_symlink()


@pytest.mark.parametrize("kind", ["presets", "compositions", "scenes", "thumbnail"])
def test_predictable_partial_symlink_cannot_overwrite_external_bytes(storage, kind):
    _, directory, outside = storage
    subdir = "scenes" if kind == "thumbnail" else kind
    (directory / subdir).mkdir()
    suffix = (
        ".png"
        if kind == "thumbnail"
        else ".tetravox.json" if kind == "scenes" else ".json"
    )
    target = directory / subdir / ("test" + suffix)
    partial = Path(
        str(target) + (".partial" if kind == "presets" else f".{os.getpid()}.partial")
    )
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    partial.symlink_to(sentinel)
    if kind == "presets":
        viewers.save_viewer_preset("test", {"subject": "ernie"})
    elif kind == "compositions":
        lib.save_composition("test", {"subject": "ernie"})
    else:
        lib.save_scene(
            "test",
            {
                "scene": SCENE,
                "thumbnail": "data:image/png;base64," + base64.b64encode(PNG).decode(),
            },
        )
    assert sentinel.read_bytes() == b"untouched"
    assert partial.is_symlink()
    assert target.is_file() and not target.is_symlink()


@pytest.mark.parametrize("kind", ["presets", "compositions", "scenes"])
def test_in_project_directory_links_preserve_save_read_delete(storage, kind):
    project, directory, _ = storage
    actual = project / ("linked-" + kind)
    actual.mkdir()
    (directory / kind).symlink_to(actual, target_is_directory=True)
    if kind == "presets":
        viewers.save_viewer_preset("test", {"subject": "ernie"})
        assert viewers.viewer_presets()["presets"][0]["subject"] == "ernie"
        viewers.delete_viewer_preset("test")
    elif kind == "compositions":
        lib.save_composition("test", {"subject": "ernie"})
        assert lib.list_compositions()["compositions"][0]["subject"] == "ernie"
        lib.delete_composition("test")
    else:
        lib.save_scene(
            "test",
            {
                "scene": SCENE,
                "thumbnail": "data:image/png;base64," + base64.b64encode(PNG).decode(),
            },
        )
        assert lib.read_scene("test")["scene"] == SCENE
        assert json.loads((actual / "test.tetravox.json").read_text()) == SCENE
        assert (actual / "test.png").read_bytes() == PNG
        assert lib.list_scenes()["scenes"][0]["has_thumbnail"]
        lib.delete_scene("test")
    assert not list(actual.iterdir())


@pytest.mark.parametrize("suffix", [".png", ".meta.json"])
def test_outward_scene_sidecars_do_not_leak_or_allow_partial_mutation(storage, suffix):
    _, directory, outside = storage
    scenes = directory / "scenes"
    scenes.mkdir()
    scene_path = scenes / "test.tetravox.json"
    scene_path.write_text(json.dumps(SCENE))
    sentinel = outside / "sidecar"
    sentinel.write_text('{"name":"private"}')
    (scenes / ("test" + suffix)).symlink_to(sentinel)
    listing = lib.list_scenes()["scenes"][0]
    assert listing["name"] == "test"
    assert not listing["has_thumbnail"]
    original = scene_path.read_bytes()
    for action in (
        lambda: lib.save_scene("test", {"scene": {"layers": [{"id": "new"}]}}),
        lambda: lib.delete_scene("test"),
    ):
        with pytest.raises(HTTPException):
            action()
        assert scene_path.read_bytes() == original
        assert sentinel.read_text() == '{"name":"private"}'


def test_open_scene_ignores_predictable_partial_symlink(storage, monkeypatch):
    _, directory, outside = storage
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    partial = directory / "custom.tetravox.json.partial"
    partial.symlink_to(sentinel)
    monkeypatch.setattr(
        viewers.viewspec, "build_view", lambda *a, **kw: {"scene": SCENE}
    )
    result = viewers.view_open({"kind": "custom"})
    assert sentinel.read_bytes() == b"untouched"
    assert partial.is_symlink()
    assert json.loads(Path(result["path"]).read_text()) == result["scene"]


def test_atomic_failure_preserves_document_and_removes_random_temp(
    storage, monkeypatch
):
    _, directory, _ = storage
    target = directory / "document.json"
    target.write_bytes(b"original")

    def fail_replace(*args):
        raise OSError("authored replace failure")

    monkeypatch.setattr(viewers.os, "replace", fail_replace)
    with pytest.raises(OSError, match="authored replace failure"):
        viewers.atomic_viewer_write(str(target), b"new")
    assert target.read_bytes() == b"original"
    assert sorted(p.name for p in directory.iterdir()) == ["document.json"]


@pytest.mark.parametrize("kind", ["presets", "compositions", "scenes"])
def test_in_project_leaf_links_are_readable(storage, kind):
    project, directory, _ = storage
    (directory / kind).mkdir()
    target = project / "valid.json"
    target.write_text(json.dumps({"name": "linked", **SCENE}))
    suffix = ".tetravox.json" if kind == "scenes" else ".json"
    (directory / kind / ("test" + suffix)).symlink_to(target)
    if kind == "presets":
        assert viewers.viewer_presets()["presets"][0]["name"] == "linked"
    elif kind == "compositions":
        assert lib.list_compositions()["compositions"][0]["name"] == "linked"
    else:
        assert lib.read_scene("test")["scene"]["name"] == "linked"


@pytest.mark.parametrize("kind", ["presets", "compositions", "scenes"])
def test_outward_parent_blocks_save_and_delete(storage, kind):
    _, directory, outside = storage
    (directory / kind).symlink_to(outside, target_is_directory=True)
    suffix = ".tetravox.json" if kind == "scenes" else ".json"
    sentinel = outside / ("test" + suffix)
    sentinel.write_text(json.dumps(SCENE))
    original = sentinel.read_bytes()
    if kind == "presets":
        actions = (
            lambda: viewers.save_viewer_preset("test", {}),
            lambda: viewers.delete_viewer_preset("test"),
        )
    elif kind == "compositions":
        actions = (
            lambda: lib.save_composition("test", {}),
            lambda: lib.delete_composition("test"),
        )
    else:
        actions = (
            lambda: lib.save_scene("test", {"scene": SCENE}),
            lambda: lib.delete_scene("test"),
        )
    for action in actions:
        with pytest.raises(HTTPException) as exc:
            action()
        assert exc.value.status_code == 403
        assert sentinel.read_bytes() == original
    assert [p.name for p in outside.iterdir()] == [sentinel.name]


def test_atomic_creation_collision_never_follows_or_removes_link(storage, monkeypatch):
    _, directory, outside = storage
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    collision = directory / ".viewer-authored.partial"
    collision.symlink_to(sentinel)
    monkeypatch.setattr(viewers.secrets, "token_hex", lambda size: "authored")
    with pytest.raises(FileExistsError):
        viewers.atomic_viewer_write(str(directory / "target.json"), b"new")
    assert sentinel.read_bytes() == b"untouched"
    assert collision.is_symlink()
    assert not (directory / "target.json").exists()


def test_atomic_save_retains_normal_umask_permissions(storage):
    _, directory, _ = storage
    ordinary = directory / "ordinary.json"
    ordinary.write_bytes(b"normal")
    target = directory / "atomic.json"
    viewers.atomic_viewer_write(str(target), b"atomic")
    assert target.stat().st_mode & 0o777 == ordinary.stat().st_mode & 0o777
