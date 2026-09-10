"""2026-09-09: scene input/cache containment against preexisting symlinks.

Authored text/byte sentinels prove sources are refused and external cache bytes survive.
Run: python3 -m pytest tests/test_scene_storage_safety.py -q. Numerical parsers and
scene geometry assertions remain in test_scene_build; concurrent link swaps are separate.
"""

import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from tit.paths import PathManager
from tit.scene import build, cache
from tit.server.routes import scene


@pytest.mark.parametrize("source", ["mesh", "net", "lut", "central", "annot"])
@pytest.mark.parametrize("inside", [False, True])
def test_scene_source_links_stay_in_project(tmp_path, monkeypatch, source, inside):
    project = tmp_path / "project"
    project.mkdir()
    pm = PathManager(str(project))
    head = Path(pm.m2m("ernie"))
    head.mkdir(parents=True)
    (head / "ernie.msh").write_text("mesh")
    relative, content = {
        "mesh": ("ernie.msh", "mesh"),
        "net": ("eeg_positions/net.csv", "Electrode,1,2,3,private\n"),
        "lut": ("segmentation/labeling_LUT.txt", "1 private 1 2 3 0\n"),
        "central": ("surfaces/lh.central.gii", "surface"),
        "annot": ("segmentation/lh.ernie_DK40.annot", "annotation"),
    }[source]
    target = (project if inside else tmp_path) / "source"
    target.write_text(content)
    alias = head / relative
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.unlink(missing_ok=True)
    alias.symlink_to(target)
    monkeypatch.setattr(scene, "_pm", lambda: pm)
    if source in ("net", "lut", "mesh"):
        call = {
            "mesh": lambda: scene._scene_subject(pm, "ernie"),
            "net": lambda: scene.electrodes("ernie", "net.csv"),
            "lut": lambda: scene.volume_legend("ernie", "labeling"),
        }[source]
        if inside:
            assert call()
        else:
            with pytest.raises(HTTPException) as error:
                call()
            assert error.value.status_code in (403, 404)
    else:
        found = (
            build.central_surface_paths(pm, "ernie")
            if source == "central"
            else build.annot_paths(pm, "ernie", "DK40")
        )
        assert bool(found) is inside


@pytest.mark.parametrize("operation", ["publish", "find", "prune"])
def test_scene_cache_outward_directory_is_refused(tmp_path, operation):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "gm.old.tvsc").write_bytes(b"keep")
    root = project / "derivatives" / "ti-toolbox" / "scene_cache" / "sub-ernie"
    root.parent.mkdir(parents=True)
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        if operation == "publish":
            cache.publish(project, "ernie", "gm", "new", b"new", {})
        elif operation == "find":
            cache.find_cached(project, "ernie", "gm", "old")
        else:
            cache.prune_stale(project, "ernie", "gm", "new")
    assert (outside / "gm.old.tvsc").read_bytes() == b"keep"
    assert sorted(p.name for p in outside.iterdir()) == ["gm.old.tvsc"]


def test_scene_cache_rejects_outward_parent_with_leaf_back_inside(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    inside = project / "inside"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sub-ernie").symlink_to(inside, target_is_directory=True)
    parent = project / "derivatives" / "ti-toolbox" / "scene_cache"
    parent.parent.mkdir(parents=True)
    parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        cache.publish(project, "ernie", "gm", "new", b"new", {})
    assert list(inside.iterdir()) == []


@pytest.mark.parametrize("filename", ["gm.new.tvsc", "gm.new.json"])
def test_scene_cache_outward_leaf_is_refused(tmp_path, filename):
    project = tmp_path / "project"
    project.mkdir()
    root = cache.cache_dir(project, "ernie")
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"keep")
    (root / filename).symlink_to(outside)
    with pytest.raises(PermissionError):
        cache.publish(project, "ernie", "gm", "new", b"new", {})
    assert outside.read_bytes() == b"keep"


@pytest.mark.parametrize("filename", ["gm.new.tvsc", "gm.new.json"])
def test_scene_cache_temp_collision_does_not_write_or_unlink_link(
    tmp_path, monkeypatch, filename
):
    root = cache.cache_dir(tmp_path, "ernie")
    root.mkdir(parents=True)
    target = tmp_path / "keep"
    target.write_bytes(b"keep")
    monkeypatch.setattr(cache.os, "urandom", lambda size: b"\x01" * size)
    collision = root / f"{filename}.tmp-{os.getpid()}-{'01' * 16}"
    collision.symlink_to(target)
    with pytest.raises(FileExistsError):
        cache.publish(tmp_path, "ernie", "gm", "new", b"new", {})
    assert collision.is_symlink()
    assert target.read_bytes() == b"keep"


def test_scene_cache_inside_alias_publish_preserves_target(tmp_path):
    root = cache.cache_dir(tmp_path, "ernie")
    root.mkdir(parents=True)
    target = tmp_path / "keep"
    target.write_bytes(b"keep")
    alias = root / "gm.new.tvsc"
    alias.symlink_to(target)
    artifact = cache.publish(tmp_path, "ernie", "gm", "new", b"new", {})
    assert artifact.path.read_bytes() == b"new"
    assert target.read_bytes() == b"keep"
    assert not alias.is_symlink()


def test_scene_cache_inside_directory_link_keeps_unrelated_files(tmp_path):
    target = tmp_path / "relocated"
    target.mkdir()
    (target / "sentinel").write_bytes(b"keep")
    root = cache.cache_dir(tmp_path, "ernie")
    root.parent.mkdir(parents=True)
    root.symlink_to(target, target_is_directory=True)
    cache.publish(tmp_path, "ernie", "gm", "old", b"old", {})
    artifact = cache.publish(tmp_path, "ernie", "gm", "new", b"new", {})
    assert artifact.path.read_bytes() == b"new"
    assert cache.find_cached(tmp_path, "ernie", "gm", "new") is not None
    assert not (target / "gm.old.tvsc").exists()
    assert (target / "sentinel").read_bytes() == b"keep"


@pytest.mark.parametrize("kind", ["surface", "labels"])
def test_scene_cache_escape_maps_to_http_for_ready_check(tmp_path, monkeypatch, kind):
    project = tmp_path / "project"
    project.mkdir()
    pm = PathManager(str(project))
    head = Path(pm.m2m("ernie"))
    head.mkdir(parents=True)
    (head / "ernie.msh").write_text("mesh")
    outside = tmp_path / "outside"
    outside.mkdir()
    root = cache.cache_dir(project, "ernie")
    root.parent.mkdir(parents=True)
    root.symlink_to(outside, target_is_directory=True)
    ready = (
        scene._surface_ready(pm, "ernie", "gm")
        if kind == "surface"
        else scene._labels_ready(pm, "ernie", "DK40")
    )
    with pytest.raises(HTTPException) as error:
        ready()
    assert error.value.status_code == 403
