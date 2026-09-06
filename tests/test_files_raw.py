"""Tests for ``GET|HEAD /api/files/raw/{path}`` (``tit/server/routes/files.py``).

The in-app viewer's byte source. What is pinned here is the whole reason it
is a separate route from ``/api/files/artifact``: it serves file types that
one refuses, with the opposite response policy (opaque bytes, never a
document), from a narrower jail, with Range/ETag semantics a viewer needs to
stream a 250 MB mesh.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit import viewspec  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

VOLUME_BYTES = bytes(range(256)) * 64  # 16 KiB of non-repeating-enough bytes


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    m2m = pm.m2m("ernie")
    os.makedirs(m2m)
    Path(m2m, "T1.nii.gz").write_bytes(VOLUME_BYTES)
    Path(m2m, "final_tissues_LUT.txt").write_text("1 White 245 245 245 255\n")
    Path(m2m, "ernie.msh").write_bytes(b"$MeshFormat\n")
    Path(m2m, "ernie.msh.opt").write_text("// mesh options\n")
    Path(m2m, "report.html").write_text("<html><script>alert(1)</script></html>")
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def raw_url(path: str) -> str:
    return "/api/files/raw/" + str(path).lstrip("/")


def t1_path() -> str:
    return os.path.join(get_path_manager().m2m("ernie"), "T1.nii.gz")


def test_raw_serves_a_volume_the_artifact_route_refuses(client: TestClient) -> None:
    path = t1_path()
    assert (
        client.get(
            "/api/files/artifact", params={"path": path}, headers=BEARER
        ).status_code
        == 403
    )

    r = client.get(raw_url(path), headers=BEARER)
    assert r.status_code == 200
    assert r.content == VOLUME_BYTES
    assert r.headers["content-length"] == str(len(VOLUME_BYTES))


def test_raw_response_is_opaque_bytes(client: TestClient) -> None:
    r = client.get(raw_url(t1_path()), headers=BEARER)
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["etag"].startswith('"')


def test_raw_never_content_encodes(client: TestClient) -> None:
    """A ``.nii.gz`` must arrive still deflated: the viewer inflates it itself.

    An encoded body would also break ``Content-Length`` and make byte ranges
    meaningless, so any compression middleware added later must exempt this
    route -- there is none today, which this asserts from both ends.
    """
    from tit.server import app as app_module

    r = client.get(
        raw_url(t1_path()), headers={**BEARER, "accept-encoding": "gzip, br"}
    )
    assert "content-encoding" not in {k.lower() for k in r.headers}
    assert r.content == VOLUME_BYTES
    installed = {m.cls.__name__ for m in client.app.user_middleware}
    assert "GZipMiddleware" not in installed
    assert app_module.CSPMiddleware.__name__ in installed


def test_raw_last_url_segment_is_the_real_filename(client: TestClient) -> None:
    """The engine takes the file name, gzip decision and volume-vs-mesh routing
    from the URL's last segment, which a ``?path=`` route would mangle."""
    url = raw_url(t1_path())
    assert url.endswith("/T1.nii.gz")
    assert client.get(url, headers=BEARER).status_code == 200


def test_raw_range_returns_206_with_content_range(client: TestClient) -> None:
    r = client.get(raw_url(t1_path()), headers={**BEARER, "Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-9/{len(VOLUME_BYTES)}"
    assert r.headers["content-length"] == "10"
    assert r.content == VOLUME_BYTES[:10]


def test_raw_open_ended_and_suffix_ranges(client: TestClient) -> None:
    size = len(VOLUME_BYTES)
    tail = client.get(
        raw_url(t1_path()), headers={**BEARER, "Range": f"bytes={size - 4}-"}
    )
    assert tail.status_code == 206
    assert tail.content == VOLUME_BYTES[-4:]

    suffix = client.get(raw_url(t1_path()), headers={**BEARER, "Range": "bytes=-4"})
    assert suffix.status_code == 206
    assert suffix.content == VOLUME_BYTES[-4:]


def test_raw_unsatisfiable_range_is_416(client: TestClient) -> None:
    size = len(VOLUME_BYTES)
    r = client.get(
        raw_url(t1_path()), headers={**BEARER, "Range": f"bytes={size + 10}-"}
    )
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{size}"


def test_raw_multi_range_falls_back_to_the_whole_body(client: TestClient) -> None:
    r = client.get(raw_url(t1_path()), headers={**BEARER, "Range": "bytes=0-9,20-29"})
    assert r.status_code == 200
    assert r.content == VOLUME_BYTES


def test_raw_head_has_length_and_no_body(client: TestClient) -> None:
    """FastAPI does not add HEAD to a GET route by itself -- this catches the 405."""
    r = client.head(raw_url(t1_path()), headers=BEARER)
    assert r.status_code == 200
    assert r.headers["content-length"] == str(len(VOLUME_BYTES))
    assert r.headers["accept-ranges"] == "bytes"
    assert r.content == b""


def test_raw_if_none_match_is_304(client: TestClient) -> None:
    first = client.get(raw_url(t1_path()), headers=BEARER)
    etag = first.headers["etag"]
    again = client.get(raw_url(t1_path()), headers={**BEARER, "If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag


def test_raw_stale_if_range_sends_the_whole_file(client: TestClient) -> None:
    r = client.get(
        raw_url(t1_path()),
        headers={**BEARER, "Range": "bytes=0-9", "If-Range": '"stale"'},
    )
    assert r.status_code == 200
    assert r.content == VOLUME_BYTES


def test_raw_serves_mesh_lut_and_opt_sidecars(client: TestClient) -> None:
    m2m = get_path_manager().m2m("ernie")
    for name in ("ernie.msh", "ernie.msh.opt", "final_tissues_LUT.txt"):
        r = client.get(raw_url(os.path.join(m2m, name)), headers=BEARER)
        assert r.status_code == 200, name
        assert r.headers["content-type"] == "application/octet-stream", name


def test_raw_html_is_403(client: TestClient) -> None:
    """Nothing served from this origin may be executable as a document."""
    path = os.path.join(get_path_manager().m2m("ernie"), "report.html")
    r = client.get(raw_url(path), headers=BEARER)
    assert r.status_code == 403
    assert "raw data" in r.json()["detail"]


def test_raw_traversal_outside_jail_is_403(client: TestClient) -> None:
    escaping = os.path.join(
        get_path_manager().m2m("ernie"), "..", "..", "..", "..", "etc", "passwd"
    )
    r = client.get(raw_url(escaping), headers=BEARER)
    assert r.status_code in (403, 404)
    assert "root:" not in r.text


def test_raw_absolute_outside_path_is_403(client: TestClient) -> None:
    assert client.get(raw_url("/etc/hosts"), headers=BEARER).status_code == 403


def test_raw_symlink_out_of_the_jail_is_403(client: TestClient, project: Path) -> None:
    """``Path.resolve`` follows the link, so the *target* is what is jailed."""
    outside = project.parent / "outside.nii.gz"
    outside.write_bytes(b"secret")
    link = Path(get_path_manager().m2m("ernie"), "linked.nii.gz")
    link.symlink_to(outside)
    r = client.get(raw_url(str(link)), headers=BEARER)
    assert r.status_code == 403
    assert b"secret" not in r.content


def test_raw_missing_file_is_404(client: TestClient) -> None:
    missing = os.path.join(get_path_manager().m2m("ernie"), "nope.nii.gz")
    assert client.get(raw_url(missing), headers=BEARER).status_code == 404


def test_raw_directory_is_404(client: TestClient) -> None:
    assert (
        client.get(raw_url(get_path_manager().m2m("ernie")), headers=BEARER).status_code
        == 404
    )


def test_raw_unauthorized_without_token(client: TestClient) -> None:
    assert client.get(raw_url(t1_path())).status_code == 401
    assert client.head(raw_url(t1_path())).status_code == 401


def test_raw_jail_is_narrower_than_the_launcher_jail(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The raw route serves ``resources/atlas``, not the whole ``resources/`` tree.

    ``jail_roots`` (what a Freeview launch is checked against) admits the
    bundled ``resources/`` directory, which also holds patches and scripts;
    handing those to a browser from the app's own origin is a different
    proposition, so the raw route uses ``raw_jail_roots``.
    """
    # Outside the project, so only the resources root can admit it.
    resources = tmp_path.parent / f"resources-{tmp_path.name}"
    atlas = resources / "atlas"
    atlas.mkdir(parents=True)
    (atlas / "MNI152_T1_1mm.nii.gz").write_bytes(b"atlas")
    (resources / "patch.py").write_text("print('hi')\n")
    monkeypatch.setattr(viewspec, "mni_resources_dir", lambda: str(atlas))

    assert Path(resources).resolve() in viewspec.jail_roots()
    assert Path(atlas).resolve() in viewspec.raw_jail_roots()
    assert (
        client.get(
            raw_url(str(atlas / "MNI152_T1_1mm.nii.gz")), headers=BEARER
        ).status_code
        == 200
    )
    assert (
        client.get(raw_url(str(resources / "patch.py")), headers=BEARER).status_code
        == 403
    )
