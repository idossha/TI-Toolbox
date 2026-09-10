"""Bounded mask import, jail, and auth; numerical file validation has real-library tests."""

import gzip
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tit.paths import get_path_manager
from tit.server.app import create_app
from tit.server.settings import ServerSettings


@pytest.fixture
def client(tmp_path, monkeypatch):
    pm = get_path_manager(str(tmp_path))
    Path(pm.m2m("s")).mkdir(parents=True)
    monkeypatch.setattr("tit.catalog.subject_ids", lambda pm: ["s"])
    monkeypatch.setattr("tit.opt.masks.validate_mask", lambda path: None)
    return TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="test")),
        base_url="http://127.0.0.1:8765",
    )


def post(client, data=b"volume", name="mask.nii", auth=True):
    return client.post(
        "/api/files/mask",
        params={"subject": "s", "name": name},
        content=data,
        headers={"Authorization": "Bearer test"} if auth else {},
    )


def test_upload_preserves_source_and_avoids_overwrite(client):
    a, b = post(client), post(client)
    assert a.status_code == b.status_code == 201
    assert a.json()["path"] != b.json()["path"]
    assert Path(a.json()["path"]).read_bytes() == b"volume"


@pytest.mark.parametrize(
    "name", ["../mask.nii", "/mask.nii", "mask.html", "a\\mask.nii"]
)
def test_filename_is_jailed(client, name):
    assert post(client, name=name).status_code == 422


def test_upload_requires_authentication(client):
    assert post(client, auth=False).status_code == 401


def test_upload_size_limit_cleans_partial_file(client, monkeypatch):
    monkeypatch.setattr("tit.server.routes.files._MASK_UPLOAD_LIMIT", 4)
    assert post(client).status_code == 413
    assert not list(Path(get_path_manager().masks("s")).rglob("*.*"))


def test_gzip_expansion_is_bounded(client, monkeypatch):
    monkeypatch.setattr("tit.server.routes.files._MASK_DECOMPRESSED_LIMIT", 4)
    assert post(client, gzip.compress(b"12345"), "mask.nii.gz").status_code == 413


def test_corrupt_gzip_is_rejected(client):
    assert post(client, b"invalid", "mask.nii.gz").status_code == 422


def test_mask_validation_error_is_actionable(client, monkeypatch):
    def reject(path):
        raise ValueError("Mask must be a three-dimensional NIfTI volume")

    monkeypatch.setattr("tit.opt.masks.validate_mask", reject)
    response = post(client)
    assert response.status_code == 422
    assert "three-dimensional" in response.json()["detail"]


def test_symlinked_mask_directory_is_rejected(client, tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    Path(get_path_manager().masks("s")).symlink_to(outside, target_is_directory=True)
    assert post(client).status_code == 403
    assert not list(outside.iterdir())


def test_upload_filename_limit_reserves_collision_suffix(client):
    response = post(client, name="a" * 238 + ".nii")
    assert response.status_code == 201
    assert len(Path(response.json()["path"]).name) == 255
    assert post(client, name="a" * 239 + ".nii").status_code == 422


def test_upload_rejects_oversized_filename_before_validation(client, monkeypatch):
    def unexpected_validation(path):
        pytest.fail("Oversized names must be rejected before mask validation")

    monkeypatch.setattr("tit.opt.masks.validate_mask", unexpected_validation)
    assert post(client, name="0" * 10000 + ".nii").status_code == 422
