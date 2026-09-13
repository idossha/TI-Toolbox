"""Native scene exports preserve settings and cannot reference unshared arbitrary files."""

import copy
import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import HTTPException

from tit import viewspec
from tit.paths import get_path_manager, reset_path_manager
from tit.server.routes import viewers, viewer_library


@pytest.fixture
def project(tmp_path, monkeypatch):
    reset_path_manager()
    root = tmp_path / "project"
    root.mkdir()
    get_path_manager(str(root))
    monkeypatch.setattr(
        "tit.server.host_path.host_project_dir", lambda _: "/host/project"
    )
    monkeypatch.setattr(viewspec, "raw_jail_roots", lambda: [root])
    yield root
    reset_path_manager()


def scene(path):
    return {
        "version": 2,
        "datasets": [
            {
                "id": "d",
                "path": viewspec.RAW_ROUTE_PREFIX + quote(str(path).lstrip("/")),
            }
        ],
        "layers": [{"id": "l", "kind": "volume", "datasetId": "d", "opacity": 0.37}],
        "camera": {"distance": 42},
    }


def test_export_localises_paths_and_preserves_scene_state(project):
    data = project / "my volume.nii"
    data.write_bytes(b"volume")
    spec = scene(data)
    original = copy.deepcopy(spec)
    result = viewers.export_scene({"name": "target preview", "scene": spec})
    saved = json.loads(Path(result["scene_path"]).read_text())
    assert result["scene_path"].endswith("target_preview.tetravox.json")
    assert saved["datasets"][0]["path"] == "/host/project/my volume.nii"
    assert saved["layers"] == spec["layers"]
    assert saved["camera"] == spec["camera"]
    assert spec == original
    assert result["host_path"].startswith("/host/project/code/ti-toolbox/viewer/")


def test_reference_assets_and_sidecars_are_staged(project, tmp_path, monkeypatch):
    resources = tmp_path / "resources"
    resources.mkdir()
    data, sidecar = resources / "atlas.gii", resources / "atlas.annot"
    data.write_bytes(b"atlas")
    sidecar.write_bytes(b"labels")
    monkeypatch.setattr(viewspec, "raw_jail_roots", lambda: [project, resources])
    spec = scene(data)
    spec["datasets"][0]["sidecars"] = {"annotation": {"path": str(sidecar)}}
    output = viewers.export_scene({"scene": spec})["scene"]["datasets"][0]
    for path, content in [
        (output["path"], b"atlas"),
        (output["sidecars"]["annotation"]["path"], b"labels"),
    ]:
        assert path.startswith("/host/project/code/ti-toolbox/viewer/assets/")
        assert (
            Path(str(project) + path.removeprefix("/host/project")).read_bytes()
            == content
        )


@pytest.mark.parametrize("symlink", [False, True])
def test_export_refuses_files_outside_the_shared_roots(project, tmp_path, symlink):
    private = tmp_path / "private.nii"
    private.write_bytes(b"private")
    path = private
    if symlink:
        path = project / "escape.nii"
        path.symlink_to(private)
    with pytest.raises(HTTPException) as error:
        viewers.export_scene({"scene": scene(path)})
    assert error.value.status_code == 403
    assert not (project / "code/ti-toolbox/viewer/preview.tetravox.json").exists()


def test_saved_scene_uses_native_paths_and_can_be_saved_again(project):
    data = project / "volume.nii"
    data.write_bytes(b"volume")
    result = viewer_library.save_scene("my scene", {"scene": scene(data)})
    saved = json.loads(Path(result["scene_path"]).read_text())
    assert saved["datasets"][0]["path"] == "/host/project/volume.nii"
    again = viewer_library.save_scene("my scene", {"scene": saved})
    assert (
        Path(again["scene_path"]).read_text() == Path(result["scene_path"]).read_text()
    )
