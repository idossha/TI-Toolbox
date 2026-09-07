"""``/api/scene/*`` — routes, cache semantics and readable failures (lane SCA).

What this pins
    The frozen §2.1 response shapes, the 202 + ``Retry-After`` contract for a
    cold cache, the ``ETag``/304 revalidation the surface route promises, and
    that every "this subject cannot do that" case answers a 404 with a
    sentence a user can act on rather than a 500. Auth is asserted the same
    way every other v1 route module asserts it.

    Added in the 2026-09-04 fix round (lane FIX-B,
    ``docs/dev/HISTORY.md § 2026-09-04 (scene service)``): all six routes give *one*
    subject-level answer, and it names what is missing and what to run rather
    than "unknown subject" (which was what a subject staged under
    ``sourcedata/`` -- and listed by the app's own picker -- used to get); and
    every JSON body is validated against ``contracts/openapi.v1.yaml``, from
    which ``desktop/src/renderer/api/schema.d.ts`` is generated.

Where the numbers come from
    The payloads are written by :mod:`tit.scene.tvsc` into a synthetic project
    under ``tmp_path``; the counts asserted are the ones this test put there.
    Nothing here reads a mesh -- ``simnibs``/``nibabel``/``scipy`` are
    ``MagicMock``s in this suite, so :func:`tit.scene.build.build_surfaces` is
    replaced by a stub that publishes a known payload. What a *real* mesh
    produces is ``tests/test_scene_realdata.py`` (env-gated) and the live runs
    recorded in ``docs/dev/HISTORY.md § 2026-09-04 (scene service)``.

Deliberately elsewhere
    Format bytes: ``tests/test_scene_tvsc.py``. Cache internals:
    ``tests/test_scene_cache.py``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.scene import cache, gifti, tvsc  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes import scene as scene_routes  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-scene"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

NET_CSV = (
    "Electrode,-26.08,113.65,19.07,Fp1\n"
    "Electrode,1.87,116.90,22.64,Fpz\n"
    "ReferenceElectrode,0.0,0.0,90.0,Cz\n"
    "Fiducial,2.08,114.04,-12.88,Nz\n"
)
LUT_TXT = (
    "#No.\t  Label Name:\t\t\t   R   G   B   A\n"
    "2\t  Left-Cerebral-White-Matter       245 245 245 255 \n"
    "3\t  Left-Cerebral-Cortex     \t   205 62 78 255 \n"
)


@pytest.fixture(autouse=True)
def _reset_route_state():
    """Build bookkeeping is module-level; a leak makes the next test flaky."""
    scene_routes._IN_FLIGHT.clear()
    scene_routes._LAST_ERROR.clear()
    yield
    scene_routes._IN_FLIGHT.clear()
    scene_routes._LAST_ERROR.clear()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """The four states a subject can be in when a pane asks for its scene.

    ``ernie``  head model + net + LUT: everything works.
    ``bare``   ``m2m_bare/`` exists but the mesh does not (charm interrupted).
    ``raw``    raw BIDS only, no ``m2m_raw/`` at all (charm never run).
    ``102``    staged under ``sourcedata/`` and nothing else -- the state
               Dataset 000's ``sub-102`` is in, which
               :func:`tit.catalog.subject_ids` deliberately excludes while
               ``GET /api/catalog/subjects`` (and so the app's own subject
               picker) lists it.
    """
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.eeg_positions("ernie"))
    os.makedirs(pm.segmentation("ernie"))
    os.makedirs(pm.m2m("bare"))
    os.makedirs(pm.bids_anat("raw"))
    os.makedirs(os.path.join(pm.sourcedata_subject("102"), "T1w"))
    (Path(pm.sourcedata_subject("102")) / "T1w" / "0001.dcm").write_bytes(b"\x00")
    (Path(pm.m2m("ernie")) / "ernie.msh").write_bytes(b"not really a mesh")
    (Path(pm.eeg_positions("ernie")) / "EEG10-10.csv").write_text(NET_CSV)
    (Path(pm.segmentation("ernie")) / "labeling_LUT.txt").write_text(LUT_TXT)
    (tmp_path / "dataset_description.json").write_text("{}")
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    return TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
        base_url=BASE,
    )


def _publish_fake_surfaces(project: Path, sid: str = "ernie") -> dict:
    """Publish both parts the way a real build would, with known counts."""
    pm = get_path_manager()
    from tit.scene import build

    fingerprint = build.surface_fingerprint(pm, sid)
    counts = {"skin": (4, 2), "gm": (5, 3)}
    for part, (n_vertices, n_triangles) in counts.items():
        positions = np.arange(3 * n_vertices, dtype=np.float64).reshape(n_vertices, 3)
        triangles = np.stack(
            [
                np.arange(n_triangles) % n_vertices,
                (np.arange(n_triangles) + 1) % n_vertices,
                (np.arange(n_triangles) + 2) % n_vertices,
            ],
            axis=1,
        )
        # Both serialisations, the way one `build_surfaces` publishes them
        # (decision E7). Publishing only one would let a route bug that serves
        # the wrong file pass, because there would be no other file.
        for ext, blob in (
            ("gii", gifti.encode_surface(positions, triangles)),
            ("tvsc", tvsc.encode(positions, triangles)),
        ):
            cache.publish(
            project,
            sid,
            part,
            fingerprint,
            blob,
            {
                "part": part,
                "vertices": n_vertices,
                "triangles": n_triangles,
                "simplified": part == "gm",
                "within_budget": True,
                "max_deviation_mm": 0.0,
                "bbox": [0.0, 0.0, 0.0, 10.0, 11.0, 12.0],
                # The neck is what `focus_bbox` cuts off, so the fake ones
                # differ from `bbox` in z0 only -- which is what makes the
                # manifest's union of the two boxes distinguishable.
                "focus_bbox": [0.0, 0.0, 4.0, 10.0, 11.0, 12.0],
                "build_ms": 1234.5,
            },
            ext=ext,
            )
    return counts


def _publish_fake_labels(project: Path, sid: str = "ernie", atlas: str = "DK40") -> dict:
    """Publish a labels payload + legend the way :func:`build.build_labels` does.

    The two ``.annot`` files are empty on purpose: they exist so
    ``build.annot_paths`` finds the atlas, and nothing reads them because the
    artifact they would have produced is already in the cache.
    """
    pm = get_path_manager()
    from tit.scene import build

    for hemi in ("lh", "rh"):
        (Path(pm.segmentation(sid)) / f"{hemi}.{sid}_{atlas}.annot").write_bytes(b"")
    legend = [
        {"label": 1, "id": 1, "hemi": "lh", "name": "bankssts", "color": "#19190a"},
        {"label": 2, "id": 1, "hemi": "rh", "name": "bankssts", "color": "#19190a"},
    ]
    positions = np.arange(15, dtype=np.float64).reshape(5, 3)
    triangles = np.array([[0, 1, 2], [2, 3, 4], [4, 0, 1]], dtype=np.int64)
    values = np.array([1, 2, 0, 1, 2], dtype=np.uint16)
    for ext, blob in (
        (
            "gii",
            gifti.encode_surface(
                positions, triangles, values, gifti.label_table_from_legend(legend)
            ),
        ),
        ("tvsc", tvsc.encode(positions, None, values)),
    ):
        cache.publish(
            project,
            sid,
            build._labels_key(atlas),
            build.labels_fingerprint(pm, sid, atlas),
            blob,
            {
                "atlas": atlas,
                "aligned_to": "gm",
                "vertices": 5,
                "triangles": int(len(triangles)),
                "radius_mm": 3.0,
                "labelled_fraction": 0.8,
                "legend": legend,
                "build_ms": 42.0,
            },
            ext=ext,
        )
    return {"legend": legend}


# ── auth, the same rule every /api route follows ─────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/scene/manifest?subject=ernie",
        "/api/scene/surface?subject=ernie&part=gm",
        "/api/scene/electrodes?subject=ernie&net=EEG10-10.csv",
        "/api/scene/regions?subject=ernie&atlas=DK40",
        "/api/scene/labels?subject=ernie&atlas=DK40",
        "/api/scene/volume-legend?subject=ernie",
    ],
)
def test_every_scene_route_needs_auth(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


# ── unknown things answer readably, never 500 ────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/scene/manifest?subject=nope",
        "/api/scene/surface?subject=nope&part=gm",
        "/api/scene/electrodes?subject=nope&net=EEG10-10.csv",
        "/api/scene/volume-legend?subject=nope",
    ],
)
def test_unknown_subject_is_404(client: TestClient, path: str) -> None:
    response = client.get(path, headers=BEARER)
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


#: Every route of §2.1, addressed by subject id. A subject-level answer has to
#: be the same sentence on all six: the pane calls the manifest first, but the
#: form's own controls (net, atlas, volume legend) call the others directly.
SUBJECT_ROUTES = [
    "/api/scene/manifest?subject={sid}",
    "/api/scene/surface?subject={sid}&part=gm",
    "/api/scene/labels?subject={sid}&atlas=DK40",
    "/api/scene/regions?subject={sid}&atlas=DK40",
    "/api/scene/electrodes?subject={sid}&net=EEG10-10.csv",
    "/api/scene/volume-legend?subject={sid}",
]


@pytest.mark.parametrize("route", SUBJECT_ROUTES)
def test_a_staged_subject_is_told_what_to_run_not_that_it_is_unknown(
    client: TestClient, route: str
) -> None:
    """``sub-102``: in the app's subject picker, not in ``catalog.subject_ids``.

    Reported by lane SCC (``docs/dev/HISTORY.md § 2026-09-04 (scene service)`` §6.3): every
    scene route answered ``"Unknown subject: 102"``, a sentence that is true of
    the *function* and false to a user looking at 102 in the Subjects table.
    The answer has to name what is missing (no ``m2m_102/``), where the subject
    *is* known from (``sourcedata/``) and what to run.
    """
    response = client.get(route.format(sid="102"), headers=BEARER)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "unknown subject" not in detail.lower(), detail
    assert "m2m_102" in detail, detail
    assert "sourcedata/sub-102" in detail, detail
    assert "charm" in detail.lower(), detail


@pytest.mark.parametrize("route", SUBJECT_ROUTES)
def test_a_subject_with_raw_data_but_no_head_model_names_the_directory(
    client: TestClient, route: str
) -> None:
    """The onboarded-but-not-reconstructed case, on all six routes.

    ``catalog.subject_ids`` *does* list ``raw``, so this one never said
    "unknown" -- but only ``manifest`` and ``surface`` looked for the head
    mesh. ``electrodes`` blamed the net file, ``regions``/``labels`` blamed the
    atlas and ``volume-legend`` blamed the LUT, each naming a file that is
    missing only because the whole head model is.
    """
    response = client.get(route.format(sid="raw"), headers=BEARER)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "m2m_raw" in detail, detail
    assert "charm" in detail.lower(), detail
    assert "sourcedata" not in detail, detail  # raw/ is not staged-only


@pytest.mark.parametrize("route", SUBJECT_ROUTES)
def test_a_subject_the_project_does_not_have_says_what_it_does_have(
    client: TestClient, route: str
) -> None:
    """The one case "unknown" is the truth -- and it still has to be useful."""
    response = client.get(route.format(sid="nope"), headers=BEARER)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "nope" in detail
    for known in ("102", "bare", "ernie", "raw"):
        assert known in detail, detail


def test_a_subject_id_that_is_a_path_is_refused_before_any_stat(
    client: TestClient,
) -> None:
    """The gate builds ``m2m_<id>/`` paths, so the id is checked first."""
    response = client.get(
        "/api/scene/manifest?subject=../../../../etc", headers=BEARER
    )
    assert response.status_code == 404
    assert "etc" in response.json()["detail"]


def test_every_scene_json_response_matches_the_contract_schema(
    client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The four JSON scene bodies, validated against ``contracts/openapi.v1.yaml``.

    Why this exists: ``desktop/src/renderer/api/schema.d.ts`` is generated from
    that contract, and since this round
    ``desktop/src/renderer/pages/_shared/scene/api.ts`` takes its types from
    the generated file instead of hand-writing them a second time. These routes
    return plain ``dict``s, so FastAPI's own dump declares no schema for them
    (``dev/contracts_check.py`` counts that as a warning, not a gate) -- which
    leaves the contract free to say something the server never sends, and the
    renderer would believe it at compile time and find out at runtime. Here the
    contract is the independent reader and the responses are the data.
    """
    jsonschema = pytest.importorskip(
        "jsonschema",
        reason=(
            "jsonschema is not a runtime dependency; install with "
            "`python3 -m pip install --user --break-system-packages jsonschema`"
        ),
    )
    yaml = pytest.importorskip("yaml", reason="PyYAML reads the contract")

    contract = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "contracts/openapi.v1.yaml").read_text()
    )
    _publish_fake_surfaces(project)
    _publish_fake_labels(project)
    # The manifest counts an atlas' regions by reading its colour tables, and
    # nibabel is a MagicMock in this suite (see the module header). What a real
    # ctab yields is tests/test_scene_realdata.py's job.
    import tit.scene.build as build_module

    monkeypatch.setattr(build_module, "atlas_region_count", lambda pm, sid, atlas: 70)

    cases = {
        "/api/scene/manifest": "/api/scene/manifest?subject=ernie",
        "/api/scene/regions": "/api/scene/regions?subject=ernie&atlas=DK40",
        "/api/scene/electrodes": "/api/scene/electrodes?subject=ernie&net=EEG10-10.csv",
        "/api/scene/volume-legend": "/api/scene/volume-legend?subject=ernie",
    }
    assert cases, "has responses to check"
    for operation, url in cases.items():
        response = client.get(url, headers=BEARER)
        assert response.status_code == 200, (url, response.status_code, response.text)
        schema = contract["paths"][operation]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(response.json())


def test_the_contract_schema_check_can_actually_fail(
    client: TestClient, project: Path
) -> None:
    """A schema that accepts everything would make the test above vacuous."""
    jsonschema = pytest.importorskip("jsonschema")
    yaml = pytest.importorskip("yaml")

    contract = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "contracts/openapi.v1.yaml").read_text()
    )
    schema = contract["paths"]["/api/scene/electrodes"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    body = client.get(
        "/api/scene/electrodes?subject=ernie&net=EEG10-10.csv", headers=BEARER
    ).json()
    body["electrodes"][0]["world"] = "-26.08,113.65,19.07"  # the classic: a CSV row
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(body)
    del body["net"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(body)


def test_unknown_part_names_the_parts_that_exist(client: TestClient) -> None:
    response = client.get("/api/scene/surface?subject=ernie&part=bone", headers=BEARER)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "gm" in detail and "skin" in detail


def test_a_subject_with_no_head_model_says_so(client: TestClient) -> None:
    """Decision S6: no head model yet is a normal state, not a server error."""
    for path in (
        "/api/scene/manifest?subject=bare",
        "/api/scene/surface?subject=bare&part=gm",
    ):
        response = client.get(path, headers=BEARER)
        assert response.status_code == 404
        assert "charm" in response.json()["detail"]


def test_an_atlas_the_subject_lacks_is_404_not_500(client: TestClient) -> None:
    """MNI152-style case: answer readably rather than blowing up on a glob."""
    response = client.get(
        "/api/scene/regions?subject=ernie&atlas=NotAnAtlas", headers=BEARER
    )
    assert response.status_code == 404
    assert "NotAnAtlas" in response.json()["detail"]


def test_an_unknown_net_is_404(client: TestClient) -> None:
    response = client.get(
        "/api/scene/electrodes?subject=ernie&net=../../etc/passwd", headers=BEARER
    )
    assert response.status_code == 404


# ── electrodes and the volume legend (no build needed) ───────────────────────


def test_electrodes_are_split_by_row_type_and_carry_world_mm(
    client: TestClient,
) -> None:
    body = client.get(
        "/api/scene/electrodes?subject=ernie&net=EEG10-10.csv", headers=BEARER
    ).json()
    assert body["net"] == "EEG10-10.csv"
    assert body["space"] == "subject-ras"
    assert [e["name"] for e in body["electrodes"]] == ["Fp1", "Fpz"]
    assert body["electrodes"][0]["world"] == [-26.08, 113.65, 19.07]
    assert [e["name"] for e in body["reference"]] == ["Cz"]
    assert [e["name"] for e in body["fiducials"]] == ["Nz"]


def test_volume_legend_parses_the_freesurfer_style_table(client: TestClient) -> None:
    body = client.get("/api/scene/volume-legend?subject=ernie", headers=BEARER).json()
    assert body["id"] == "labeling"
    assert body["entries"][0] == {
        "id": 2,
        "name": "Left-Cerebral-White-Matter",
        "color": "#f5f5f5",
    }
    assert body["entries"][1]["color"] == "#cd3e4e"


def test_an_unknown_volume_id_is_404(client: TestClient) -> None:
    response = client.get(
        "/api/scene/volume-legend?subject=ernie&id=whatever", headers=BEARER
    )
    assert response.status_code == 404


# ── the cache contract: 202 while building, 200 + ETag once ready ────────────


def test_a_cold_surface_answers_202_with_retry_after(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2.1: never a held connection over ~10 s."""
    import tit.scene.build as build_module

    def never_finishes(pm, sid):  # noqa: ANN001
        import time

        time.sleep(5)

    monkeypatch.setattr(build_module, "build_surfaces", never_finishes)
    response = client.get("/api/scene/surface?subject=ernie&part=gm", headers=BEARER)
    assert response.status_code == 202
    assert response.headers["retry-after"] == str(scene_routes.RETRY_AFTER_S)
    assert response.headers["x-scene-cache"] == "building"
    assert response.json()["cache"]["state"] == "building"


def test_a_failed_build_is_reported_not_polled_forever(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tit.scene.build as build_module

    def explode(pm, sid):  # noqa: ANN001
        raise RuntimeError("mesh is corrupt")

    monkeypatch.setattr(build_module, "build_surfaces", explode)
    first = client.get(
        "/api/scene/surface?subject=ernie&part=gm&wait=2", headers=BEARER
    )
    assert first.status_code == 500
    assert "mesh is corrupt" in first.json()["detail"]


def test_a_warm_surface_is_served_with_its_etag_and_counts(
    client: TestClient, project: Path
) -> None:
    counts = _publish_fake_surfaces(project)
    response = client.get("/api/scene/surface?subject=ernie&part=gm", headers=BEARER)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-scene-cache"] == "hit"
    assert response.headers["x-scene-build-ms"] == "1234.5"
    assert response.headers["x-scene-triangles"] == str(counts["gm"][1])
    assert response.headers["cache-control"] == "private, max-age=0, must-revalidate"

    decoded = tvsc.decode(response.content)
    assert decoded.vertex_count == counts["gm"][0]
    assert decoded.triangle_count == counts["gm"][1]


def test_revalidating_a_warm_surface_is_a_304(client: TestClient, project: Path) -> None:
    _publish_fake_surfaces(project)
    first = client.get("/api/scene/surface?subject=ernie&part=skin", headers=BEARER)
    etag = first.headers["etag"]

    second = client.get(
        "/api/scene/surface?subject=ernie&part=skin",
        headers={**BEARER, "If-None-Match": etag},
    )
    assert second.status_code == 304
    assert second.content == b""


def test_the_etag_changes_when_the_head_model_changes(
    client: TestClient, project: Path
) -> None:
    """The reason ``must-revalidate`` is the right cache policy here."""
    _publish_fake_surfaces(project)
    before = client.get(
        "/api/scene/surface?subject=ernie&part=gm", headers=BEARER
    ).headers["etag"]

    pm = get_path_manager()
    (Path(pm.m2m("ernie")) / "ernie.msh").write_bytes(b"a different mesh entirely")
    _publish_fake_surfaces(project)

    after = client.get(
        "/api/scene/surface?subject=ernie&part=gm", headers=BEARER
    ).headers["etag"]
    assert before != after


# ── the manifest ─────────────────────────────────────────────────────────────


def test_the_manifest_has_the_frozen_shape(client: TestClient, project: Path) -> None:
    """§2.1's keys, spelled out: lane SCB builds against exactly these."""
    _publish_fake_surfaces(project)
    response = client.get("/api/scene/manifest?subject=ernie", headers=BEARER)
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {
        "subject",
        "space",
        "bbox",
        "focus_bbox",
        "parts",
        "nets",
        "atlases",
        "volumes",
        "cache",
    }
    assert body["subject"] == "ernie"
    assert body["space"] == "subject-ras"
    assert body["cache"]["state"] == "ready"

    parts = {p["id"]: p for p in body["parts"]}
    assert set(parts) == {"skin", "gm"}
    for part in parts.values():
        assert part["kind"] == "surface"
        assert part["triangles"] > 0
        assert part["vertices"] > 0
        assert part["bytes"] > 0
        assert part["fingerprint"]
        assert part["url"].startswith("/api/scene/surface?subject=ernie&part=")

    assert body["nets"] == [
        {
            "name": "EEG10-10.csv",
            "electrodes": 2,
            "url": "/api/scene/electrodes?subject=ernie&net=EEG10-10.csv",
        }
    ]
    assert body["atlases"] == []  # this synthetic subject has no .annot files
    assert body["volumes"] == []  # nor a labeling.nii.gz


def test_the_manifest_bbox_spans_every_part(client: TestClient, project: Path) -> None:
    _publish_fake_surfaces(project)
    body = client.get("/api/scene/manifest?subject=ernie", headers=BEARER).json()
    assert body["bbox"] == [0.0, 0.0, 0.0, 10.0, 11.0, 12.0]


def test_the_manifest_carries_the_framing_box_beside_the_bounding_box(
    client: TestClient, project: Path
) -> None:
    """``focus_bbox`` is the head; ``bbox`` is the head and the neck (S7).

    Both are unioned over the parts by the same rule, and the pane frames the
    first while still containing the second -- which is why they are two
    fields rather than one.
    """
    _publish_fake_surfaces(project)
    body = client.get("/api/scene/manifest?subject=ernie", headers=BEARER).json()
    assert body["focus_bbox"] == [0.0, 0.0, 4.0, 10.0, 11.0, 12.0]
    assert body["focus_bbox"] != body["bbox"]
    for part in body["parts"]:
        assert part["focus_bbox"] == [0.0, 0.0, 4.0, 10.0, 11.0, 12.0]


def test_the_framing_box_is_null_when_no_part_reports_one(
    client: TestClient, project: Path
) -> None:
    """A payload an older builder wrote carries no ``focus_bbox``.

    The fingerprint salt makes that unreachable in practice
    (``tests/test_scene_orientation.py``); the route still has to answer
    ``null`` rather than crash, because the renderer's fallback to ``bbox`` is
    what makes the field additive.
    """
    _publish_fake_surfaces(project)
    pm = get_path_manager()
    from tit.scene import build

    fp = build.surface_fingerprint(pm, "ernie")
    for part in ("skin", "gm"):
        _, sidecar = cache.artifact_paths(project, "ernie", part, fp)
        meta = json.loads(sidecar.read_text())
        meta.pop("focus_bbox")
        sidecar.write_text(json.dumps(meta))

    body = client.get("/api/scene/manifest?subject=ernie", headers=BEARER).json()
    assert body["focus_bbox"] is None
    assert body["bbox"] == [0.0, 0.0, 0.0, 10.0, 11.0, 12.0]


def test_a_cold_manifest_answers_202_and_says_it_is_building(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tit.scene.build as build_module

    def never_finishes(pm, sid):  # noqa: ANN001
        import time

        time.sleep(5)

    monkeypatch.setattr(build_module, "build_surfaces", never_finishes)
    response = client.get("/api/scene/manifest?subject=ernie", headers=BEARER)
    assert response.status_code == 202
    assert response.headers["retry-after"] == str(scene_routes.RETRY_AFTER_S)
    body = response.json()
    assert body["cache"]["state"] == "building"
    assert body["parts"] == []
    # The cheap halves are still answered: a pane can populate its net picker
    # while the surfaces build.
    assert body["nets"][0]["name"] == "EEG10-10.csv"


def test_wait_lets_a_caller_ask_for_one_deterministic_call(
    client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``?wait=`` is the opt-in block; the default stays 202."""
    import tit.scene.build as build_module

    def slow_but_finite(pm, sid):  # noqa: ANN001
        import time

        time.sleep(0.2)
        _publish_fake_surfaces(project)

    monkeypatch.setattr(build_module, "build_surfaces", slow_but_finite)
    response = client.get(
        "/api/scene/surface?subject=ernie&part=gm&wait=10", headers=BEARER
    )
    assert response.status_code == 200
    assert tvsc.decode(response.content).triangle_count == 3


def test_wait_is_capped(client: TestClient) -> None:
    """A client must not be able to pin a worker thread indefinitely."""
    response = client.get(
        f"/api/scene/surface?subject=ernie&part=gm&wait={scene_routes.MAX_WAIT_S + 1}",
        headers=BEARER,
    )
    assert response.status_code == 422


def test_only_one_build_runs_per_subject(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two panes opening at once must not both read the 184 MB mesh."""
    import tit.scene.build as build_module

    calls: list[int] = []

    def counting(pm, sid):  # noqa: ANN001
        import time

        calls.append(1)
        time.sleep(1.0)

    monkeypatch.setattr(build_module, "build_surfaces", counting)
    for _ in range(4):
        assert (
            client.get("/api/scene/surface?subject=ernie&part=gm", headers=BEARER).status_code
            == 202
        )
    assert sum(calls) == 1


# ── ?format: one build, two serialisations (decision E7) ─────────────────────


def test_format_gii_serves_gifti_and_format_tvsc_serves_tvsc1(
    client: TestClient, project: Path
) -> None:
    """The same URL, two payloads, each what its ``?format`` names.

    ``tvsc`` stays the default until compatibility is intentionally retired: a
    default that moved would change what every existing client receives from a
    URL it already fetches.
    """
    _publish_fake_surfaces(project)
    default = client.get("/api/scene/surface?subject=ernie&part=gm", headers=BEARER)
    tvsc_body = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=tvsc", headers=BEARER
    )
    gii = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=gii", headers=BEARER
    )
    assert default.status_code == tvsc_body.status_code == gii.status_code == 200
    assert default.content == tvsc_body.content
    assert tvsc_body.content.startswith(b"TVSC")
    assert gii.content.startswith(b"<?xml")
    assert b"NIFTI_INTENT_POINTSET" in gii.content
    assert b"NIFTI_INTENT_TRIANGLE" in gii.content
    # Same geometry, both ways round: the counts the sidecar reports are the
    # ones both payloads carry, which is what "only the serialisation changed"
    # means.
    assert tvsc.decode(tvsc_body.content).triangle_count == 3
    assert gii.headers["x-scene-triangles"] == "3"


def test_an_unknown_format_is_a_400_that_names_the_formats(
    client: TestClient, project: Path
) -> None:
    _publish_fake_surfaces(project)
    response = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=glb", headers=BEARER
    )
    assert response.status_code == 400
    assert "glb" in response.json()["detail"]
    assert "tvsc" in response.json()["detail"] and "gii" in response.json()["detail"]


def test_the_etag_names_the_format_so_one_payload_cannot_answer_for_the_other(
    client: TestClient, project: Path
) -> None:
    """The failure this prevents, and it is silent.

    One key and one fingerprint now name **two** payloads. An ETag built from
    the key and the fingerprint alone is the same string for both, so a client
    that fetched ``format=tvsc`` and then asked for ``format=gii`` with its
    ``If-None-Match`` would be told 304 — and would go on drawing TVSC1 bytes
    while believing it holds GIfTI. Nothing downstream would report it.
    """
    _publish_fake_surfaces(project)
    tvsc_response = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=tvsc", headers=BEARER
    )
    gii_response = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=gii", headers=BEARER
    )
    assert tvsc_response.headers["etag"] != gii_response.headers["etag"]
    assert tvsc_response.headers["etag"].endswith('-tvsc"')
    assert gii_response.headers["etag"].endswith('-gii"')

    # Its own ETag still revalidates to a 304 — the cheap path is not lost.
    same = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=gii",
        headers={**BEARER, "If-None-Match": gii_response.headers["etag"]},
    )
    assert same.status_code == 304
    # The other format's does not.
    crossed = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=gii",
        headers={**BEARER, "If-None-Match": tvsc_response.headers["etag"]},
    )
    assert crossed.status_code == 200
    assert crossed.content == gii_response.content


def test_a_format_that_is_not_published_yet_is_building_not_the_other_one(
    client: TestClient, project: Path
) -> None:
    """A half-published cache answers 202, never the wrong bytes.

    ``publish`` writes one format at a time, so between the two writes the
    sidecar exists and one payload does not. A route that fell back to the file
    it *can* find would hand GIfTI to a TVSC1 reader.
    """
    _publish_fake_surfaces(project)
    pm = get_path_manager()
    from tit.scene import build

    fingerprint = build.surface_fingerprint(pm, "ernie")
    blob, _ = cache.artifact_paths(project, "ernie", "gm", fingerprint, "gii")
    blob.unlink()

    response = client.get(
        "/api/scene/surface?subject=ernie&part=gm&format=gii", headers=BEARER
    )
    assert response.status_code == 202
    assert response.json()["cache"]["state"] == "building"
    assert (
        client.get(
            "/api/scene/surface?subject=ernie&part=gm&format=tvsc", headers=BEARER
        ).status_code
        == 200
    )


def test_labels_as_gifti_carry_the_atlas_table_with_no_region_first(
    client: TestClient, project: Path
) -> None:
    """The ``<LabelTable>`` is what makes a region a colour rather than a number.

    Without it the engine reads the array as a continuous scalar and paints the
    cortex through a colormap; and with a real region in the first row every
    unlabelled vertex takes that region's colour, because an unnamed value maps
    to the table's **first** entry.
    """
    _publish_fake_surfaces(project)
    _publish_fake_labels(project)
    body = client.get(
        "/api/scene/labels?subject=ernie&atlas=DK40&format=gii", headers=BEARER
    ).content.decode()
    assert body.index('Key="0"') < body.index('Key="1"')
    assert "unlabelled" in body
    assert body.count("<Label ") == 3  # unlabelled + the two legend rows
    assert "NIFTI_INTENT_LABEL" in body
    assert "NIFTI_INTENT_TRIANGLE" in body
