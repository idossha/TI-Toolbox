"""``tit.server.host_path`` — resolving the project's *host* directory (lane FX2).

The failure these pin: ``GET /api/project`` answered ``host_path: null`` on every v3 container,
because the only source it read (``LOCAL_PROJECT_DIR``) is interpolated into the compose file's
``volumes:`` entry and never put *inside* the container, so every client that needs to turn a
container path into a host path had to shell out to ``docker inspect``
(`docs/dev/HISTORY.md § 2026-09-03 (pipelines program)`).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server import host_path as host_path_mod  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-abc123"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


def _inspect(mounts=(), labels=None):
    return {
        "Mounts": list(mounts),
        "Config": {"Labels": dict(labels or {})},
    }


def _bind(source, destination):
    return {"Type": "bind", "Source": source, "Destination": destination}


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    monkeypatch.delenv("LOCAL_PROJECT_DIR", raising=False)
    host_path_mod.clear_cache()
    yield
    host_path_mod.clear_cache()


# -- host_dir_from_inspect (pure) --------------------------------------------------------------


def test_bind_mount_destination_gives_the_host_path():
    info = _inspect([_bind("/Users/me/datasets/000", "/mnt/000")])
    assert host_path_mod.host_dir_from_inspect(info, "/mnt/000") == (
        "/Users/me/datasets/000"
    )


def test_project_dir_nested_inside_a_mount_keeps_its_suffix():
    info = _inspect([_bind("/Users/me/data", "/mnt")])
    assert host_path_mod.host_dir_from_inspect(info, "/mnt/000/sub") == (
        "/Users/me/data/000/sub"
    )


def test_longest_matching_destination_wins():
    info = _inspect(
        [_bind("/Users/me/data", "/mnt"), _bind("/Volumes/ext/000", "/mnt/000")]
    )
    assert host_path_mod.host_dir_from_inspect(info, "/mnt/000") == "/Volumes/ext/000"


def test_label_is_the_fallback_when_no_mount_matches():
    info = _inspect(
        [_bind("/var/run/docker.sock", "/var/run/docker.sock")],
        {host_path_mod.HOST_DIR_LABEL: "/Users/me/datasets/000"},
    )
    assert host_path_mod.host_dir_from_inspect(info, "/mnt/000") == (
        "/Users/me/datasets/000"
    )


def test_named_volumes_are_not_host_paths():
    """A volume's ``Source`` is a path inside the Docker VM, not something a client can open."""
    info = {
        "Mounts": [
            {
                "Type": "volume",
                "Name": "tit_data",
                "Source": "/var/lib/docker/volumes/tit_data/_data",
                "Destination": "/mnt/000",
            }
        ],
        "Config": {"Labels": {}},
    }
    assert host_path_mod.host_dir_from_inspect(info, "/mnt/000") is None


def test_windows_host_source_keeps_its_own_separator():
    info = _inspect([_bind("C:\\Users\\me\\data", "/mnt")])
    assert host_path_mod.host_dir_from_inspect(info, "/mnt/000") == (
        "C:\\Users\\me\\data\\000"
    )


def test_unrelated_container_resolves_to_nothing():
    assert host_path_mod.host_dir_from_inspect(_inspect(), "/mnt/000") is None
    # A path that merely shares a prefix string with a mount point is not inside it.
    info = _inspect([_bind("/Users/me/data", "/mnt/000")])
    assert host_path_mod.host_dir_from_inspect(info, "/mnt/000x") is None


# -- host_project_dir (env, cache, no-container) -----------------------------------------------


def test_env_wins_and_no_container_lookup_happens(monkeypatch):
    monkeypatch.setenv("LOCAL_PROJECT_DIR", "/Users/me/from-env")
    monkeypatch.setattr(
        host_path_mod,
        "_from_own_container",
        lambda _p: pytest.fail("must not inspect when LOCAL_PROJECT_DIR is set"),
    )
    assert host_path_mod.host_project_dir("/mnt/000") == "/Users/me/from-env"


def test_container_lookup_is_made_once_and_cached(monkeypatch):
    calls = []

    def _fake(container_path):
        calls.append(container_path)
        return "/Users/me/datasets/000"

    monkeypatch.setattr(host_path_mod, "_from_own_container", _fake)
    assert host_path_mod.host_project_dir("/mnt/000") == "/Users/me/datasets/000"
    assert host_path_mod.host_project_dir("/mnt/000") == "/Users/me/datasets/000"
    assert calls == ["/mnt/000"]


def test_not_in_a_container_is_none_not_an_error(monkeypatch):
    monkeypatch.setattr(host_path_mod, "own_container_id", lambda: None)
    assert host_path_mod.host_project_dir("/mnt/000") is None


def test_engine_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(host_path_mod, "own_container_id", lambda: "a" * 64)
    monkeypatch.setattr(os.path, "exists", lambda _p: True)

    class _Boom:
        def __init__(self, *_a, **_kw):
            pass

        def inspect_container(self, _cid):
            raise RuntimeError("no such container")

    monkeypatch.setattr("tit.jobs.docker_engine.DockerEngineClient", _Boom)
    assert host_path_mod.host_project_dir("/mnt/000") is None


def test_own_container_id_reads_mountinfo(monkeypatch, tmp_path: Path):
    cid = "f17995acd796d054213272a650fba43fcb7f89726d2c061c64edb87047efda75"
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        f"1234 1000 0:59 /containers/{cid}/hostname /etc/hostname rw,relatime - ext4 x rw\n"
    )
    real_open = open
    monkeypatch.setattr(
        "builtins.open",
        lambda path, *a, **kw: (
            real_open(mountinfo, *a, **kw)
            if path == "/proc/self/mountinfo"
            else real_open(path, *a, **kw)
        ),
    )
    assert host_path_mod.own_container_id() == cid


def test_own_container_id_falls_back_to_hostname(monkeypatch):
    monkeypatch.setattr(
        "builtins.open", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("no /proc"))
    )
    monkeypatch.setenv("HOSTNAME", "f17995acd796")
    assert host_path_mod.own_container_id() == "f17995acd796"
    monkeypatch.setenv("HOSTNAME", "my-laptop.local")
    assert host_path_mod.own_container_id() is None


# -- the route ---------------------------------------------------------------------------------


def test_project_route_reports_the_resolved_host_path(tmp_path: Path, monkeypatch):
    get_path_manager(str(tmp_path))
    monkeypatch.setattr(
        host_path_mod, "_from_own_container", lambda _p: "/Users/me/datasets/000"
    )
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token=TOKEN)),
        base_url=BASE,
    )
    body = client.get("/api/project", headers=BEARER).json()
    assert body["container_path"] == str(tmp_path)
    assert body["host_path"] == "/Users/me/datasets/000"
