"""2026-09-09: pipeline storage stays in the project and preserves alias entries.

Run: python3 -m pytest tests/test_pipeline_storage_safety.py -q
Authored JSON bytes and filesystem symlinks pin disclosure, overwrite, and cleanup
boundaries. Pipeline science/graph validation remains in the pipeline suites.
"""

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from tit.paths import get_path_manager, reset_path_manager
from tit.server.routes import pipelines

DOCUMENT = {"version": 1, "name": "demo", "nodes": [], "edges": []}


@pytest.fixture
def storage(tmp_path):
    project = tmp_path / "project"
    directory = project / "code/ti-toolbox/pipelines"
    directory.mkdir(parents=True)
    outside = tmp_path / "project-other"
    outside.mkdir()
    reset_path_manager()
    get_path_manager(str(project))
    yield project, directory, outside
    reset_path_manager()


@pytest.mark.parametrize("operation", ["list", "load", "save", "delete"])
@pytest.mark.parametrize("level", ["directory", "leaf"])
def test_outward_pipeline_links_are_never_read_or_mutated(storage, operation, level):
    _, directory, outside = storage
    target = outside / "demo.json"
    target.write_text(json.dumps(DOCUMENT))
    original = target.read_bytes()
    if level == "directory":
        directory.rmdir()
        directory.symlink_to(outside, target_is_directory=True)
    else:
        (directory / "demo.json").symlink_to(target)
    actions = {
        "list": pipelines.list_pipelines,
        "load": lambda: pipelines.load_pipeline("demo"),
        "save": lambda: pipelines.save_pipeline("demo", DOCUMENT),
        "delete": lambda: pipelines.delete_pipeline("demo"),
    }
    if operation == "list" and level == "leaf":
        assert actions[operation]() == []
    else:
        with pytest.raises(HTTPException) as exc:
            actions[operation]()
        assert exc.value.status_code == 403
    assert target.read_bytes() == original
    assert (directory / "demo.json").exists()


def test_pipeline_predictable_temporary_link_cannot_overwrite(storage):
    _, directory, outside = storage
    target = outside / "sentinel"
    target.write_bytes(b"untouched")
    temporary = directory / "demo.json.tmp"
    temporary.symlink_to(target)
    pipelines.save_pipeline("demo", DOCUMENT)
    assert target.read_bytes() == b"untouched"
    assert temporary.is_symlink()
    assert json.loads((directory / "demo.json").read_text())["name"] == "demo"


@pytest.mark.parametrize("operation", ["load", "save", "delete"])
def test_inside_project_pipeline_alias_keeps_target_bytes(storage, operation):
    project, directory, _ = storage
    target = project / "target.json"
    target.write_text(json.dumps(DOCUMENT))
    original = target.read_bytes()
    alias = directory / "demo.json"
    alias.symlink_to(target)
    if operation == "load":
        assert pipelines.load_pipeline("demo")["name"] == "demo"
        assert pipelines.list_pipelines()[0]["name"] == "demo"
        assert alias.is_symlink()
    elif operation == "save":
        pipelines.save_pipeline("demo", DOCUMENT)
        assert alias.is_file() and not alias.is_symlink()
    else:
        pipelines.delete_pipeline("demo")
        assert not alias.is_symlink()
        assert not alias.exists()
    assert target.read_bytes() == original


def test_inside_project_pipeline_directory_alias_keeps_crud(storage):
    project, directory, _ = storage
    target_dir = project / "actual-pipelines"
    target_dir.mkdir()
    directory.rmdir()
    directory.symlink_to(target_dir, target_is_directory=True)
    pipelines.save_pipeline("demo", DOCUMENT)
    assert pipelines.load_pipeline("demo")["name"] == "demo"
    assert pipelines.list_pipelines()[0]["nodes"] == 0
    pipelines.delete_pipeline("demo")
    assert list(target_dir.iterdir()) == []


@pytest.mark.parametrize("name", ["../escape", "/absolute", "sibling/name"])
def test_pipeline_invalid_name_still_returns_422(storage, name):
    with pytest.raises(HTTPException) as exc:
        pipelines.save_pipeline(name, DOCUMENT)
    assert exc.value.status_code == 422


@pytest.mark.parametrize("operation", ["load", "delete"])
def test_missing_pipeline_still_returns_404(storage, operation):
    action = (
        pipelines.load_pipeline if operation == "load" else pipelines.delete_pipeline
    )
    with pytest.raises(HTTPException) as exc:
        action("missing")
    assert exc.value.status_code == 404


@pytest.mark.parametrize("failure", ["collision", "replace"])
def test_pipeline_failed_save_preserves_original_and_cleans_only_owned_temp(
    storage, monkeypatch, failure
):
    _, directory, outside = storage
    pipelines.save_pipeline("demo", DOCUMENT)
    original = (directory / "demo.json").read_bytes()
    temporary = directory / ".pipeline-fixed.tmp"
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    monkeypatch.setattr(pipelines.secrets, "token_hex", lambda _: "fixed")
    if failure == "collision":
        temporary.symlink_to(sentinel)
    else:

        def fail_replace(*args):
            raise OSError("authored replace failure")

        monkeypatch.setattr(pipelines.os, "replace", fail_replace)
    with pytest.raises(OSError):
        pipelines.save_pipeline("demo", DOCUMENT)
    assert (directory / "demo.json").read_bytes() == original
    assert sentinel.read_bytes() == b"untouched"
    assert temporary.is_symlink() if failure == "collision" else not temporary.exists()


def test_pipeline_dangling_outside_leaf_cannot_be_created(storage):
    _, directory, outside = storage
    target = outside / "absent.json"
    alias = directory / "demo.json"
    alias.symlink_to(target)
    with pytest.raises(HTTPException) as exc:
        pipelines.save_pipeline("demo", DOCUMENT)
    assert exc.value.status_code == 403
    assert not target.exists()
    assert alias.is_symlink()


def test_pipeline_project_root_can_be_filesystem_root(storage, monkeypatch):
    project, _, _ = storage

    class RootProject:
        project_dir = str(project.anchor)

    monkeypatch.setattr(pipelines, "get_path_manager", lambda: RootProject())
    assert pipelines._checked_path(str(project / "demo.json")) == str(
        project / "demo.json"
    )
