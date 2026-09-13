"""Scene library reports authored path failures and never deletes scientific inputs."""

import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from tit.paths import get_path_manager, reset_path_manager
from tit.server.routes import viewer_library as lib


@pytest.fixture
def project(tmp_path, monkeypatch):
    reset_path_manager()
    get_path_manager(str(tmp_path))
    monkeypatch.setattr(
        "tit.server.host_path.host_project_dir", lambda _: "C:\\Users\\me\\project"
    )
    directory = Path(lib.saved_scene_dir())
    directory.mkdir(parents=True)
    yield tmp_path, directory
    reset_path_manager()


def write_scene(directory, path, **extra):
    target = directory / "saved.tetravox.json"
    target.write_text(
        json.dumps(
            {
                "datasets": [{"id": "data", "path": path, **extra}],
                "layers": [{"datasetId": "data"}],
            }
        )
    )
    return target


def test_native_host_path_missing_and_restored(project):
    root, directory = project
    target = write_scene(directory, "C:\\Users\\me\\project\\volume.nii")
    assert lib.list_scenes()["scenes"][0]["health"] == "missing"
    (root / "volume.nii").write_bytes(b"not parsed")
    assert lib.list_scenes()["scenes"][0]["health"] == "valid"
    assert target.exists()


def test_relative_sidecar_and_broken_dataset_reference(project):
    root, directory = project
    (directory / "volume.nii").touch()
    target = write_scene(
        directory, "volume.nii", sidecars={"labels": {"path": "missing.txt"}}
    )
    row = lib.list_scenes()["scenes"][0]
    assert (row["health"], row["missing_count"]) == ("missing", 1)
    scene = json.loads(target.read_text())
    scene["layers"][0]["datasetId"] = "nonexistent"
    target.write_text(json.dumps(scene))
    assert lib.list_scenes()["scenes"][0]["health"] == "invalid"


@pytest.mark.parametrize("relative_exists", [True, False])
def test_dataset_path_and_absolute_path_are_alternatives(project, relative_exists):
    root, directory = project
    relative = directory / "relative.nii"
    absolute = root / "absolute.nii"
    (relative if relative_exists else absolute).write_bytes(b"available dataset")
    write_scene(directory, relative.name, absPath=str(absolute))

    row = lib.list_scenes()["scenes"][0]

    assert (row["health"], row["missing_count"]) == ("valid", 0)


def test_dataset_basename_beside_scene_is_a_safe_relocation_fallback(project):
    root, directory = project
    write_scene(directory, "old/volume.nii", absPath=str(root / "old/volume.nii"))
    relocated = directory / "volume.nii"
    relocated.write_bytes(b"relocated dataset")

    row = lib.list_scenes()["scenes"][0]
    assert (row["health"], row["missing_count"]) == ("valid", 0)

    relocated.unlink()
    relocated.symlink_to(root.parent / "outside.nii")
    assert lib.list_scenes()["scenes"][0]["health"] == "invalid"


def test_sidecar_paths_are_alternatives_but_separate_files_are_required(project):
    root, directory = project
    (directory / "volume.nii").touch()
    labels = root / "labels.txt"
    labels.write_bytes(b"available labels")
    write_scene(
        directory,
        "volume.nii",
        sidecars={"labels": {"path": "missing.txt", "absPath": str(labels)}},
    )
    assert lib.list_scenes()["scenes"][0]["health"] == "valid"

    labels.unlink()
    row = lib.list_scenes()["scenes"][0]
    assert (row["health"], row["missing_count"]) == ("missing", 1)


def test_corrupt_json_stays_visible_and_can_be_deleted(project):
    _, directory = project
    target = directory / "saved.tetravox.json"
    target.write_text("{broken")
    assert lib.list_scenes()["scenes"][0]["health"] == "invalid"
    assert lib.delete_scene("saved")["deleted"] is True
    assert not target.exists()


def test_external_paths_not_probed_and_symlink_escape_invalid(project, monkeypatch):
    root, directory = project
    write_scene(directory, "/private/never-stat-this.nii")
    original = os.path.isfile

    def guarded(path):
        assert not str(path).startswith("/private/never-stat")
        return original(path)

    monkeypatch.setattr(os.path, "isfile", guarded)
    assert lib.list_scenes()["scenes"][0]["health"] == "unchecked"
    (root / "escape.nii").symlink_to(root.parent / "outside.nii")
    write_scene(directory, str(root / "escape.nii"))
    assert lib.list_scenes()["scenes"][0]["health"] == "invalid"


def test_failed_delete_is_not_reported_as_success(project, monkeypatch):
    root, directory = project
    dataset = root / "volume.nii"
    dataset.write_bytes(b"science")
    target = write_scene(directory, str(dataset))
    real_remove = os.remove

    def fail(path):
        if str(path) == str(target):
            raise PermissionError("denied")
        real_remove(path)

    monkeypatch.setattr(os, "remove", fail)
    with pytest.raises(HTTPException) as error:
        lib.delete_scene("saved")
    assert error.value.status_code == 500
    assert target.exists() and dataset.read_bytes() == b"science"
    monkeypatch.setattr(os, "remove", real_remove)
    assert lib.delete_scene("saved")["deleted"] is True
    assert not target.exists()
    assert dataset.read_bytes() == b"science"
