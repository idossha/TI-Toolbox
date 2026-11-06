"""``/api/tract/*``, the ``tract`` job kind and the TVSL1 bytes (2026-11-05).

What this pins
    The route contract of network targeting: 200/202/404/409/422, no client path reaches the
    filesystem, the mask name rule, unknown region and min-n refusals, writes only under
    ``masks/``, the overwrite policy, and region-name pairs surviving a renumbered network.
    Also ``Selection(kind="edges")``, the preflight fingerprint refusal, and the job kind's plan,
    locks and validation.

Where the numbers come from
    A synthetic tractogram written byte by byte below (a TRX is a zip of raw arrays; the reader's
    agreement with trx-python is ``tests/numerical/test_tract_viz_real.py``). Counts are what this
    file put there. TVSL1 is read back with ``struct``/``numpy.frombuffer`` at the documented
    offsets, not with the writer. ``density_mask`` needs DIPY, so it is stubbed here and exercised
    for real in ``tests/numerical/test_tract_mask.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_tract_routes.py -q``.
"""

from __future__ import annotations

import json
import re
import struct
import zipfile
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs.locks import keys_for  # noqa: E402
from tit.jobs.preflight import preflight  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes import scene as scene_routes  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402
from tit.tract import target as tract_target  # noqa: E402
from tit.tract.config import Selection, TractConfig  # noqa: E402
from tit.tract.network import select  # noqa: E402

TOKEN = "test-token-tract"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

NAMES = ["lh.insula", "lh.precentral", "Left-Thalamus-Proper", "Brain-Stem"]
# Streamline end labels: thalamus-insula x4, thalamus-precentral x2, precentral-stem x6,
# one unassigned end.
LABELS = np.array(
    [[2, 0]] * 4 + [[1, 2]] * 2 + [[1, 3]] * 6 + [[0, -1]],
    dtype=np.int64,
)
# Edges by descending count; lower region index first.
PAIRS = np.array([[1, 3], [0, 2], [1, 2]], dtype=np.int64)
COUNTS = np.array([6, 4, 2], dtype=np.int64)
EDGE_ID = np.array([1] * 4 + [2] * 2 + [0] * 6 + [-1], dtype=np.int64)


def write_trx(path: Path, n_streamlines: int, points_each: int = 5) -> None:
    """A TRX by hand: streamline i runs along x at y = i, one point per mm."""
    positions = np.array(
        [
            [float(p), float(i), 0.0]
            for i in range(n_streamlines)
            for p in range(points_each)
        ],
        dtype="<f4",
    )
    offsets = np.arange(0, n_streamlines * points_each + 1, points_each, dtype="<u4")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "header.json",
            json.dumps(
                {"NB_STREAMLINES": n_streamlines, "NB_VERTICES": len(positions)}
            ),
        )
        archive.writestr("positions.3.float32", positions.tobytes())
        archive.writestr("offsets.uint32", offsets.tobytes())


def write_network(tract_dir: Path, pairs=PAIRS, edge_id=EDGE_ID, counts=COUNTS) -> None:
    np.savez(
        tract_dir / "network.npz",
        labels=LABELS,
        edge_id=edge_id,
        pairs=pairs,
        names=np.array(NAMES),
        counts=counts,
    )
    (tract_dir / "network.json").write_text(
        json.dumps(
            {
                "atlas": "DK40",
                "n_streamlines": len(LABELS),
                "frac_both_ends_assigned": 12 / 13,
            }
        )
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    project = tmp_path / "project"
    m2m = project / "derivatives" / "SimNIBS" / "sub-S1" / "m2m_S1"
    m2m.mkdir(parents=True)
    get_path_manager(str(project))
    (m2m / "S1.msh").write_bytes(b"mesh")
    (project / "sub-S1").mkdir()
    tract_dir = m2m.parent / "tractography"
    tract_dir.mkdir()
    write_trx(tract_dir / "tractogram.trx", len(LABELS))
    write_network(tract_dir)
    (tract_dir / "qc.json").write_text(json.dumps({"flip_test_passed": True}))
    scene_routes._IN_FLIGHT.clear()
    scene_routes._LAST_ERROR.clear()

    def fake_density(streamlines, ref_path, out_path, min_count=1):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"nifti")
        return {
            "path": out_path,
            "n_voxels": 10 * len(streamlines),
            "volume_mm3": 10.0 * len(streamlines),
            "min_count": min_count,
            "max_density": 1,
        }

    monkeypatch.setattr(tract_target, "density_mask", fake_density)
    return project


@pytest.fixture
def client(project: Path) -> TestClient:
    c = TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)), base_url=BASE
    )
    c.headers.update(BEARER)
    return c


def tract_dir(project: Path) -> Path:
    return project / "derivatives" / "SimNIBS" / "sub-S1" / "tractography"


def masks_dir(project: Path) -> Path:
    return project / "derivatives" / "SimNIBS" / "sub-S1" / "m2m_S1" / "masks"


# ---- Selection(kind="edges") ------------------------------------------------------------------


def test_edges_selection_is_the_union_of_unordered_pairs() -> None:
    sel = Selection(
        name="net",
        kind="edges",
        pairs=[["lh.insula", "Left-Thalamus-Proper"], ["Brain-Stem", "lh.precentral"]],
    )
    picked = select(sel, LABELS, NAMES, EDGE_ID)
    assert picked.tolist() == [True] * 4 + [False] * 2 + [True] * 6 + [False]


def test_edges_selection_never_matches_an_unassigned_end() -> None:
    # a = -1, b = 0 sorts to (-1, 0), whose key must not collide with any real pair.
    sel = Selection(name="net", kind="edges", pairs=[["lh.insula", "lh.insula"]])
    assert not select(sel, LABELS, NAMES, EDGE_ID).any()


@pytest.mark.parametrize("pairs", [[], [["only-one"]]])
def test_edges_selection_needs_two_region_pairs(pairs) -> None:
    with pytest.raises(ValueError, match="needs pairs"):
        Selection(name="net", kind="edges", pairs=pairs)


def test_edges_selection_refuses_an_unknown_region() -> None:
    sel = Selection(name="net", kind="edges", pairs=[["nope", "lh.insula"]])
    with pytest.raises(ValueError, match="Unknown region"):
        select(sel, LABELS, NAMES, EDGE_ID)


# ---- manifest and edges -----------------------------------------------------------------------


def test_manifest_lists_cortical_regions_first(client: TestClient) -> None:
    body = client.get("/api/tract/manifest", params={"subject": "S1"}).json()
    assert body["available"] is True and body["atlas"] == "DK40"
    assert body["n_streamlines"] == 13 and body["n_edges"] == 3
    assert body["qc_passed"] is True and body["fingerprint"]
    assert [r["cortical"] for r in body["regions"]] == [True, True, False, False]


def test_manifest_without_a_network_says_what_exists(
    client: TestClient, project: Path
) -> None:
    (tract_dir(project) / "network.npz").unlink()
    body = client.get("/api/tract/manifest", params={"subject": "S1"}).json()
    assert body["available"] is False and body["tractogram_available"] is True
    assert body["qsiprep_available"] is False and body["regions"] == []


@pytest.mark.parametrize("subject", ["nobody", "../S1", "S1/.."])
def test_routes_answer_404_for_a_subject_the_project_lacks(
    client: TestClient, subject: str
) -> None:
    assert client.get(
        "/api/tract/manifest", params={"subject": subject}
    ).status_code in (
        404,
        422,
    )


def test_edges_touch_a_seed_and_keep_the_descending_order(client: TestClient) -> None:
    body = client.get(
        "/api/tract/edges", params={"subject": "S1", "seed": ["lh.precentral"]}
    ).json()
    assert [(e["region_a"], e["region_b"], e["n"]) for e in body["edges"]] == [
        ("lh.precentral", "Brain-Stem", 6),
        ("lh.precentral", "Left-Thalamus-Proper", 2),
    ]
    assert body["edges"][0]["share"] == pytest.approx(6 / 12)


def test_edges_refuse_an_unknown_seed(client: TestClient) -> None:
    r = client.get("/api/tract/edges", params={"subject": "S1", "seed": ["../etc"]})
    assert r.status_code == 422 and "Unknown region" in r.json()["detail"]


def test_edges_answer_404_before_the_network_exists(
    client: TestClient, project: Path
) -> None:
    (tract_dir(project) / "network.npz").unlink()
    r = client.get("/api/tract/edges", params={"subject": "S1", "seed": ["lh.insula"]})
    assert r.status_code == 404 and "network" in r.json()["detail"]


# ---- mask -------------------------------------------------------------------------------------


def mask_body(**over) -> dict:
    return {
        "subject": "S1",
        "name": "net",
        "pairs": [["lh.precentral", "Brain-Stem"]],
        **over,
    }


def test_mask_writes_only_under_masks_with_its_sidecar(
    client: TestClient, project: Path
) -> None:
    before = {p for p in project.rglob("*") if p.is_file()}
    r = client.post("/api/tract/mask", json=mask_body())
    assert r.status_code == 201, r.text
    body = r.json()
    assert (
        body["n_streamlines"] == 6 and body["stale"] is False and body["n_edges"] == 1
    )
    assert Path(body["path"]) == masks_dir(project) / "tract-net.nii.gz"
    new = {p for p in project.rglob("*") if p.is_file()} - before
    assert new == {
        masks_dir(project) / "tract-net.nii.gz",
        masks_dir(project) / "tract-net.json",
    }
    sidecar = json.loads((masks_dir(project) / "tract-net.json").read_text())
    assert sidecar["selection"]["pairs"] == [["lh.precentral", "Brain-Stem"]]
    assert sidecar["fingerprint"] == body["fingerprint"]


@pytest.mark.parametrize("name", ["../up", "a/b", "", "with space", "a.b"])
def test_mask_name_rule(client: TestClient, project: Path, name: str) -> None:
    r = client.post("/api/tract/mask", json=mask_body(name=name))
    assert r.status_code == 422
    assert not masks_dir(project).exists()


def test_mask_body_takes_no_path_field(client: TestClient) -> None:
    r = client.post("/api/tract/mask", json=mask_body(path="/etc/x.nii.gz"))
    assert r.status_code == 422


def test_mask_refuses_an_unknown_region(client: TestClient) -> None:
    r = client.post("/api/tract/mask", json=mask_body(pairs=[["nope", "Brain-Stem"]]))
    assert r.status_code == 422 and "Unknown region" in r.json()["detail"]


def test_mask_refuses_a_pair_no_streamline_connects(client: TestClient) -> None:
    r = client.post(
        "/api/tract/mask", json=mask_body(pairs=[["lh.insula", "Brain-Stem"]])
    )
    assert r.status_code == 422 and "No streamline" in r.json()["detail"]


def test_mask_refuses_an_edge_below_min_n(client: TestClient, project: Path) -> None:
    pairs = [["lh.precentral", "Left-Thalamus-Proper"]]  # 2 streamlines
    r = client.post("/api/tract/mask", json=mask_body(pairs=pairs))
    assert r.status_code == 422 and "fewer than 5" in r.json()["detail"]
    assert not masks_dir(project).exists()
    assert (
        client.post("/api/tract/mask", json=mask_body(pairs=pairs, min_n=2)).status_code
        == 201
    )


def test_mask_overwrite_is_explicit(client: TestClient) -> None:
    assert client.post("/api/tract/mask", json=mask_body()).status_code == 201
    r = client.post("/api/tract/mask", json=mask_body())
    assert r.status_code == 409 and "already exists" in r.json()["detail"]
    assert (
        client.post("/api/tract/mask", json=mask_body(overwrite=True)).status_code
        == 201
    )


def test_an_empty_mask_is_refused(client: TestClient, monkeypatch) -> None:
    def empty(*_a, **_k):
        raise ValueError("No voxel is crossed")

    monkeypatch.setattr(tract_target, "density_mask", empty)
    r = client.post("/api/tract/mask", json=mask_body())
    assert r.status_code == 422 and "No voxel" in r.json()["detail"]


def test_mask_pairs_survive_a_renumbered_network(
    client: TestClient, project: Path
) -> None:
    """Edge ids are transient: the same names still pick the same streamlines."""
    write_network(
        tract_dir(project),
        pairs=PAIRS[::-1],
        edge_id=np.where(EDGE_ID >= 0, 2 - EDGE_ID, -1),
        counts=COUNTS[::-1],
    )
    r = client.post("/api/tract/mask", json=mask_body())
    assert r.status_code == 201 and r.json()["n_streamlines"] == 6


def test_masks_lists_network_masks_and_marks_a_rebuilt_network_stale(
    client: TestClient, project: Path
) -> None:
    client.post("/api/tract/mask", json=mask_body())
    listed = client.get("/api/tract/masks", params={"subject": "S1"}).json()["masks"]
    assert [(m["name"], m["stale"]) for m in listed] == [("net", False)]
    write_trx(tract_dir(project) / "tractogram.trx", len(LABELS), points_each=7)
    listed = client.get("/api/tract/masks", params={"subject": "S1"}).json()["masks"]
    assert [(m["name"], m["stale"]) for m in listed] == [("net", True)]


# ---- preflight ----------------------------------------------------------------------------------


def test_preflight_refuses_a_mask_from_a_rebuilt_network(
    client: TestClient, project: Path
) -> None:
    path = client.post("/api/tract/mask", json=mask_body()).json()["path"]
    flex = {
        "subject_id": "S1",
        "roi": {"atlas_path": path, "label": None, "atlas_space": "subject"},
    }
    ex = {"subject_id": "S1", "roi_names": [], "roi_atlas": [{"atlas_path": path}]}
    assert not [
        m for m in preflight("flex", flex, str(project)) if m.expected_path == path
    ]
    assert not [m for m in preflight("ex", ex, str(project)) if m.expected_path == path]
    write_trx(tract_dir(project) / "tractogram.trx", len(LABELS), points_each=7)
    for kind, config in (("flex", flex), ("ex", ex)):
        found = [
            m for m in preflight(kind, config, str(project)) if m.expected_path == path
        ]
        assert len(found) == 1 and "Create the mask again" in found[0].how_to_fix


def test_preflight_ignores_a_mask_with_no_sidecar(project: Path) -> None:
    mask = masks_dir(project) / "hand.nii.gz"
    mask.parent.mkdir()
    mask.write_bytes(b"nifti")
    flex = {"subject_id": "S1", "roi": {"atlas_path": str(mask), "label": None}}
    assert not [
        m for m in preflight("flex", flex, str(project)) if m.expected_path == str(mask)
    ]


def test_preflight_ignores_a_neighbouring_json_that_is_not_ours(project: Path) -> None:
    for name in ("tract-hand.nii.gz", "bids.nii.gz"):
        mask = masks_dir(project) / name
        mask.parent.mkdir(exist_ok=True)
        mask.write_bytes(b"nifti")
        mask.with_name(name.replace(".nii.gz", ".json")).write_text(
            '{"RepetitionTime": 2}'
        )
        flex = {"subject_id": "S1", "roi": {"atlas_path": str(mask), "label": None}}
        found = preflight("flex", flex, str(project))
        assert not [m for m in found if m.expected_path == str(mask)]


def test_preflight_of_the_tract_kind_names_what_each_stage_needs(project: Path) -> None:
    def missing(**config) -> list[str]:
        found = preflight("tract", {"subject_id": "S1", **config}, str(project))
        return [m.what for m in found]

    assert missing(stages=["track", "network"]) == [
        "QSIPrep-preprocessed DWI for sub-S1"
    ]
    assert missing(stages=["network"]) == []
    (tract_dir(project) / "network.npz").unlink()
    assert missing(stages=["network"]) == []
    assert missing(stages=["assess"], assess={"simulations": ["A"]}) == [
        "network for sub-S1",
        "simulation 'A' for sub-S1",
    ]
    (tract_dir(project) / "tractogram.trx").unlink()
    assert "tractogram for sub-S1" in missing(stages=["network"])
    assert missing(
        stages=["target"],
        target={"leadfield_hdf": "S1_leadfield_x.hdf5", "ex_run": "r"},
    )[-2:] == [
        "sub-S1's own leadfield 'S1_leadfield_x.hdf5'",
        "ex-search run 'r' for sub-S1",
    ]


# ---- the job kind -------------------------------------------------------------------------------


def test_plan_says_what_a_tract_job_replaces(client: TestClient, project: Path) -> None:
    def plan(**config):
        r = client.post(
            "/api/plan/tract",
            json={"config": {"subject_id": "S1", **config}, "subject_ids": ["S1"]},
        )
        assert r.status_code == 200, r.text
        return r.json()["jobs"]

    jobs = plan(stages=["network"])
    assert [j["output_dir"] for j in jobs] == [str(tract_dir(project))]
    assert jobs[0]["will_overwrite"] is True
    (tract_dir(project) / "network.npz").unlink()
    assert plan(stages=["network"])[0]["will_overwrite"] is False
    jobs = plan(stages=["assess"], assess={"simulations": ["A"]})
    assert [j["output_dir"].split("/")[-2:] for j in jobs] == [["A", "tract"]]
    assert jobs[0]["will_overwrite"] is False


def test_validate_accepts_the_edges_selection_and_refuses_an_empty_one(
    client: TestClient,
) -> None:
    config = {
        "subject_id": "S1",
        "stages": ["target"],
        "target": {
            "selection": {
                "name": "net",
                "kind": "edges",
                "pairs": [["lh.precentral", "Brain-Stem"]],
            }
        },
    }
    assert client.post("/api/validate/tract", json={"config": config}).json()["ok"]
    config["target"]["selection"]["pairs"] = []
    assert not client.post("/api/validate/tract", json={"config": config}).json()["ok"]


def test_locks_write_the_tractogram_only_for_stages_that_replace_it() -> None:
    assess = {
        "subject_id": "S1",
        "stages": ["assess"],
        "assess": {"simulations": ["A"]},
    }
    keys = {lock.resource: lock.mode for lock in keys_for("tract", ["S1"], assess)}
    assert keys["subject:S1:tract"] == "read" and keys["subject:S1:sim:A"] == "write"
    rank = {
        "subject_id": "S1",
        "stages": ["target"],
        "target": {"leadfield_hdf": "x.hdf5", "ex_run": "r"},
    }
    keys = {lock.resource: lock.mode for lock in keys_for("tract", ["S1"], rank)}
    assert keys["subject:S1:tract"] == "write"
    assert keys["subject:S1:leadfields"] == "read" and keys["subject:S1:ex:r"] == "read"


def test_config_round_trips_through_the_registry() -> None:
    from tit.config_io import deserialize_config, resolve_config_class

    assert resolve_config_class("TractConfig") is TractConfig
    config = deserialize_config(
        TractConfig,
        {
            "subject_id": "S1",
            "stages": ["target"],
            "target": {
                "selection": {"name": "n", "kind": "edges", "pairs": [["a", "b"]]},
                "min_count": 2,
            },
        },
    )
    assert config.target.selection.pairs == [["a", "b"]]
    assert config.target.min_count == 2


# ---- rankings -----------------------------------------------------------------------------------


def test_rankings_are_filtered_by_the_run_that_made_them(
    client: TestClient, project: Path
) -> None:
    montage = {
        "montage": ["a", "b", "c", "d"],
        "median_sl_mean_ti_along": 1.0,
        "pooled_mean_ti_along": 1.0,
        "median_sl_mean_ti_max": 1.0,
        "pooled_mean_ti_max": 1.0,
        "median_sl_mean_ti_avg": 1.0,
        "pooled_mean_ti_avg": 1.0,
        "align_index": 1.0,
        "rank_by_ti_along": 1,
        "rank_by_ti_max": 1,
    }
    (tract_dir(project) / "target_net.json").write_text(
        json.dumps(
            {
                "selection": {"name": "net"},
                "n_streamlines": 6,
                "ranking": {
                    "ex_run": "run1",
                    "current_mA": [1.0, 1.0],
                    "n_points": 9,
                    "n_points_in_leadfield_mesh": 8,
                    "montages": [montage],
                },
            }
        )
    )
    get = lambda run: client.get(  # noqa: E731
        "/api/tract/rankings", params={"subject": "S1", "ex_run": run}
    ).json()["rankings"]
    assert [r["name"] for r in get("run1")] == ["net"]
    assert get("run2") == []


# ---- the contract -------------------------------------------------------------------------------


def test_every_tract_json_response_matches_the_contract(
    client: TestClient, project: Path
) -> None:
    import jsonschema
    import yaml
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    root = Path(__file__).resolve().parent.parent
    contract = yaml.safe_load((root / "contracts" / "openapi.yaml").read_text())
    uri = "urn:tit-contract"
    registry = Registry().with_resource(
        uri, Resource.from_contents(contract, default_specification=DRAFT202012)
    )

    def check(schema: str, body: dict) -> None:
        jsonschema.Draft202012Validator(
            {"$ref": f"{uri}#/components/schemas/{schema}"}, registry=registry
        ).validate(body)

    mask = client.post("/api/tract/mask", json=mask_body())
    params = {"subject": "S1"}
    check("TractMask", mask.json())
    check("TractManifest", client.get("/api/tract/manifest", params=params).json())
    edges = client.get("/api/tract/edges", params={**params, "seed": ["lh.insula"]})
    check("TractEdges", edges.json())
    masks = client.get("/api/tract/masks", params=params).json()
    assert masks["masks"]
    check("TractMasks", masks)
    rankings = client.get("/api/tract/rankings", params={**params, "ex_run": "r"})
    check("TractRankings", rankings.json())


# ---- streamlines --------------------------------------------------------------------------------


def parse_tvsl(blob: bytes):
    """Read TVSL1 at the offsets its docstring documents, without the writer."""
    magic, version, s, p, flags = struct.unpack_from("<4sIIII", blob, 0)
    assert magic == b"TVSL" and version == 1 and flags == 1
    assert len(blob) == 32 + 12 * p + 4 * (s + 1) + 4 * s + 4 * s
    points = np.frombuffer(blob, "<f4", 3 * p, 32).reshape(-1, 3)
    at = 32 + 12 * p
    offsets = np.frombuffer(blob, "<u4", s + 1, at)
    index = np.frombuffer(blob, "<u4", s, at + 4 * (s + 1))
    group = np.frombuffer(blob, "<u4", s, at + 4 * (2 * s + 1))
    return points, offsets, index, group


def test_streamlines_cold_cache_answers_202_then_tvsl(
    client: TestClient, monkeypatch
) -> None:
    import threading

    gate = threading.Event()
    from tit.server.routes import tract as routes

    original = routes._build_preview

    def held(*args):
        gate.wait(5)
        original(*args)

    monkeypatch.setattr(routes, "_build_preview", held)
    params = {"subject": "S1", "pair": ["lh.insula|Left-Thalamus-Proper"]}
    r = client.get("/api/tract/streamlines", params=params)
    assert r.status_code == 202 and r.headers["retry-after"] == "1"
    gate.set()
    r = client.get("/api/tract/streamlines", params={**params, "wait": 10})
    assert (
        r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    )
    points, offsets, index, group = parse_tvsl(r.content)
    # The four thalamus-insula streamlines are y = 0..3; both ends kept by the decimation.
    assert index.tolist() == [0, 1, 2, 3] and group.tolist() == [0, 0, 0, 0]
    assert points[offsets[1]][1] == 1.0
    for i in range(4):
        assert points[offsets[i]].tolist() == [0.0, float(i), 0.0]
        assert points[offsets[i + 1] - 1].tolist() == [4.0, float(i), 0.0]


def test_streamlines_group_is_the_position_in_the_request(client: TestClient) -> None:
    r = client.get(
        "/api/tract/streamlines",
        params={
            "subject": "S1",
            "pair": ["Brain-Stem|lh.precentral", "Left-Thalamus-Proper|lh.insula"],
            "wait": 10,
        },
    )
    _, _, index, group = parse_tvsl(r.content)
    by_edge = dict(zip(index.tolist(), group.tolist()))
    assert all(by_edge[i] == 1 for i in range(4))
    assert all(by_edge[i] == 0 for i in range(6, 12))
    assert 12 not in by_edge  # an unassigned end belongs to no edge


@pytest.mark.parametrize(
    ("pair", "why"),
    [
        (["lh.insula"], "region_a|region_b"),
        (["nope|lh.insula"], "Unknown region"),
        (["lh.insula|Brain-Stem"], "No streamline"),
        (["lh.insula|Left-Thalamus-Proper"] * 65, "1 to 64"),
    ],
)
def test_streamlines_refuse_a_bad_pair(client: TestClient, pair, why: str) -> None:
    r = client.get("/api/tract/streamlines", params={"subject": "S1", "pair": pair})
    assert r.status_code == 422 and why in r.json()["detail"]


def test_streamlines_cache_stays_in_the_dot_directory(
    client: TestClient, project: Path
) -> None:
    client.get(
        "/api/tract/streamlines",
        params={
            "subject": "S1",
            "pair": ["lh.insula|Left-Thalamus-Proper"],
            "wait": 10,
        },
    )
    cached = list(
        (project / ".ti-toolbox" / "cache" / "scene" / "sub-S1").glob(
            "tract-preview-*.npz"
        )
    )
    assert len(cached) == 1


def test_preview_subsample_is_uniform_and_bounded() -> None:
    from tit.tract.preview import edge_streamlines

    edge_id = np.array([0] * 500 + [1] * 3 + [-1] * 10)
    picked = edge_streamlines(edge_id, 100)
    assert (edge_id[picked] == 0).sum() == 100 and (edge_id[picked] == 1).sum() == 3
    assert (edge_id[picked] == -1).sum() == 0
    # Reproducible, and spread over the edge rather than its first members.
    assert picked.tolist() == edge_streamlines(edge_id, 100).tolist()
    assert picked[99] > 400


def test_tvsl_refuses_arrays_that_disagree() -> None:
    from tit.scene import tvsl

    points = np.zeros((4, 3))
    with pytest.raises(ValueError, match="offsets"):
        tvsl.encode(points, np.array([0, 3]), np.array([0]))
    with pytest.raises(ValueError, match="groups"):
        tvsl.encode(points, np.array([0, 4]), np.array([0]), np.array([0, 1]))
    bad = points.copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        tvsl.encode(bad, np.array([0, 4]), np.array([0]))


# ---- the Pre-processing stage -------------------------------------------------------------------


def _plan_pre(client: TestClient, **flags) -> dict:
    r = client.post(
        "/api/plan/pre",
        json={"config": {"subject_ids": ["S1"], **flags}, "subject_ids": ["S1"]},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_tractography_is_a_tract_job_after_its_prerequisites_and_not_qsirecon(
    client: TestClient,
) -> None:
    resolved = _plan_pre(
        client,
        run_qsiprep=True,
        create_m2m=True,
        run_tractography=True,
        tractography_atlas="HCP_MMP1",
    )
    stage = {s["tags"][0]: s for s in resolved["resolved"]["stages"]}["G7"]
    assert stage["kind"] == "tract"
    assert set(stage["after"]) == {"S1:G4", "S1:G2a"}
    jobs = [j for j in resolved["jobs"] if j["kind"] == "tract"]
    assert jobs[0]["output_dir"].endswith("sub-S1/tractography")


def test_tractography_stage_config_carries_the_page_s_choices() -> None:
    from tit.jobs.plans import plan_preprocessing
    from tit.pre.config import PreprocessConfig

    config = PreprocessConfig(
        subject_ids=["S1"],
        run_tractography=True,
        tractography_atlas="HCP_MMP1",
        tractography_seeds=5000,
        skip_existing_outputs=True,
    )
    (job,) = plan_preprocessing(config, ["S1"])
    assert job.config["stages"] == ["track", "network"]
    assert job.config["network"]["atlas"] == "HCP_MMP1"
    assert job.config["track"]["n_seeds"] == 5000
    assert job.config["track"]["overwrite"] is False
    assert job.config["skip_existing"] is True
    replaced = PreprocessConfig(
        subject_ids=["S1"], run_tractography=True, replace_existing_outputs=True
    )
    assert plan_preprocessing(replaced, ["S1"])[0].config["track"]["overwrite"] is True


def test_preprocess_preflight_needs_qsiprep_unless_this_run_makes_it(
    project: Path,
) -> None:
    flags = {"subject_ids": ["S1"], "run_tractography": True}
    found = preflight("pre", flags, str(project))
    assert any("Run QSIPrep for sub-S1 first" in m.how_to_fix for m in found)
    assert any("Run charm for sub-S1 first" in m.how_to_fix for m in found)
    relieved = [
        m.how_to_fix
        for m in preflight(
            "pre", {**flags, "run_qsiprep": True, "create_m2m": True}, str(project)
        )
    ]
    assert not [m for m in relieved if "Tractography" in m]


def test_skip_existing_keeps_the_tractogram_and_rebuilds_only_for_a_new_atlas(
    project: Path,
) -> None:
    from tit.tract.__main__ import _already_done
    from tit.tract.config import NetworkConfig

    folder = str(tract_dir(project))
    config = TractConfig(subject_id="S1", stages=["track", "network"])
    assert not _already_done(config, "track", folder)  # the policy is opt-in
    config.skip_existing = True
    assert _already_done(config, "track", folder)
    assert _already_done(config, "network", folder)  # network.json says DK40
    config.network = NetworkConfig(atlas="HCP_MMP1")
    assert not _already_done(config, "network", folder)


@pytest.mark.parametrize(
    ("policy", "replaces"),
    [("skip_existing_outputs", False), ("replace_existing_outputs", True)],
)
def test_a_preprocess_group_runs_tractography_over_existing_output_under_its_policy(
    client: TestClient, monkeypatch, policy: str, replaces: bool
) -> None:
    """The real app's 409: the G7 job met the per-kind overwrite check the page already answered."""
    monkeypatch.setattr(
        "tit.pre.preflight.find_missing_preprocessing_inputs", lambda *_a, **_k: []
    )
    r = client.post(
        "/api/jobs/groups",
        json={
            "kind": "pre",
            "subject_ids": ["S1"],
            "config": {"subject_ids": ["S1"], "run_tractography": True, policy: True},
        },
    )
    assert r.status_code == 201, r.text
    (job,) = r.json()["jobs"]
    assert job["kind"] == "tract"
    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert detail["spec"]["config"]["track"]["overwrite"] is replaces
    client.post(f"/api/jobs/{job['id']}/cancel")


# ---- presets, connections, what a network's outputs replace (2026-11-05) ------------------------


def test_presets_answer_for_every_set_and_say_why_one_cannot_be_chosen(
    client: TestClient,
) -> None:
    presets = {
        p["id"]: p
        for p in client.get("/api/tract/presets", params={"subject": "S1"}).json()[
            "presets"
        ]
    }
    # NAMES above: only lh.precentral of the posterior or frontal parcels; 2 + 6 streamlines.
    frontal = presets["frontal_thalamocortical"]
    assert frontal["pairs"] == [["lh.precentral", "Left-Thalamus-Proper"]]
    assert frontal["n_streamlines"] == 2
    assert frontal["same_side"] is True
    assert presets["precentral_brainstem"]["n_streamlines"] == 6
    assert presets["posterior_thalamocortical"]["reason"].startswith(
        "These labels are not in this network"
    )
    insular = presets["insular_cortical"]
    assert insular["same_side"] is False
    assert insular["pairs"] == []
    assert insular["reason"] == "0 streamlines join these regions in this network."


def test_presets_of_a_subject_with_no_network_say_what_to_run(
    client: TestClient, project: Path
) -> None:
    (tract_dir(project) / "network.npz").unlink()
    response = client.get("/api/tract/presets", params={"subject": "S1"})
    assert response.status_code == 404
    assert "Run Tractography" in response.json()["detail"]


def _assessed_edges(project: Path) -> Path:
    out = project / "derivatives/SimNIBS/sub-S1/Simulations/sim1/tract"
    out.mkdir(parents=True)
    median = lambda value: {"median": value}  # noqa: E731
    (out / "edges.json").write_text(
        json.dumps(
            {
                "0": {
                    "region_a": "lh.precentral",
                    "region_b": "Brain-Stem",
                    "n_streamlines": 6,
                    "ti_along_mean": median(0.1),
                    "ti_max_mean": median(0.2),
                    "ti_avg_mean": median(0.15),
                    "align_index": median(0.66),
                }
            }
        )
    )
    return out


def test_connections_give_the_medians_of_an_assessed_simulation(
    client: TestClient, project: Path
) -> None:
    query = {"subject": "S1", "simulation": "sim1"}
    assert client.get("/api/tract/connections", params=query).status_code == 404
    _assessed_edges(project)
    rows = client.get("/api/tract/connections", params=query).json()["connections"]
    assert rows == [
        {
            "region_a": "lh.precentral",
            "region_b": "Brain-Stem",
            "n": 6,
            "ti_along_mean": 0.1,
            "ti_max_mean": 0.2,
            "ti_avg_mean": 0.15,
            "align_index": 0.66,
        }
    ]


@pytest.mark.parametrize("simulation", ["../sim1", "nothing"])
def test_connections_refuse_a_simulation_this_subject_does_not_have(
    client: TestClient, simulation: str
) -> None:
    response = client.get(
        "/api/tract/connections", params={"subject": "S1", "simulation": simulation}
    )
    assert response.status_code == 404


def _assess(selections) -> dict:
    return {
        "_type": "TractConfig",
        "subject_id": "S1",
        "stages": ["assess"],
        "assess": {"simulations": ["sim1"], "selections": selections},
    }


def _plan_replaces(client: TestClient, kind: str, config: dict) -> list[bool]:
    body = client.post(
        f"/api/plan/{kind}", json={"config": config, "subject_ids": ["S1"]}
    ).json()
    return [job["will_overwrite"] for job in body["jobs"]]


def test_assessing_another_network_replaces_nothing_and_the_same_name_does(
    client: TestClient, project: Path
) -> None:
    out = _assessed_edges(project)
    pair = {"name": "a", "kind": "edges", "pairs": [["lh.precentral", "Brain-Stem"]]}
    assert _plan_replaces(client, "tract", _assess([pair])) == [False]
    (out / "a.trx").write_bytes(b"trx")
    assert _plan_replaces(client, "tract", _assess([pair])) == [True]
    other = {**pair, "name": "b"}
    assert _plan_replaces(client, "tract", _assess([other])) == [False]
    # With no selection the edge table is the job's whole output.
    assert _plan_replaces(client, "tract", _assess([])) == [True]


def _render(name: str, metric: str = "ti_max") -> dict:
    return {
        "_type": "TractVisualConfig",
        "subject_id": "S1",
        "simulation_name": "sim1",
        "metric": metric,
        "web": False,
        "connectome": False,
        "selection": {
            "name": name,
            "kind": "edges",
            "regions": ["Brain-Stem"],
            "pairs": [["lh.precentral", "Brain-Stem"]],
        },
    }


def test_the_plan_of_a_render_is_a_new_dated_folder_that_replaces_nothing(
    client: TestClient, project: Path
) -> None:
    out = project / "derivatives/ti-toolbox/visual_exports/sub-S1/sim1/networks"
    (out / "mine").mkdir(parents=True)
    (out / "mine" / "ti_max.png").touch()
    job = client.post(
        "/api/plan/blender",
        json={"config": _render("mine"), "subject_ids": ["S1"]},
    ).json()["jobs"][0]
    assert job["will_overwrite"] is False and job["exists"] is False
    assert Path(job["output_dir"]).parent == out
    assert re.fullmatch(r"\d{8}_\d{6}", Path(job["output_dir"]).name)


def test_the_plan_of_a_render_states_its_files_and_a_blends_size(
    client: TestClient, project: Path
) -> None:
    from tit.blender.tract_publication import blend_size_mb

    def resolved(**fields) -> dict:
        config = {**_render("mine"), **fields}
        return client.post(
            "/api/plan/blender", json={"config": config, "subject_ids": ["S1"]}
        ).json()["resolved"]

    plain = resolved()
    assert plain["planned_outputs"] == ["ti_max.png"]
    assert "blend_size_mb" not in plain
    asked = resolved(export_blend=True)
    assert asked["planned_outputs"] == ["ti_max.png", "network.blend"]
    assert asked["blend_size_mb"] == blend_size_mb(6)  # COUNTS above


def test_the_plan_of_a_render_states_its_automatic_setup_from_the_network(
    client: TestClient,
) -> None:
    body = client.post(
        "/api/plan/blender",
        json={"config": _render("mine"), "subject_ids": ["S1"]},
    ).json()
    setup = body["resolved"]["network_setup"]
    assert setup["n_streamlines"] == 6  # COUNTS above
    assert setup["values"]["highlight_regions"] == ["Brain-Stem"]
    assert (
        setup["values"]["lateral_side"] == -1
    )  # 6 ends in lh.precentral, none on the right
    assert setup["opposite_removed"] is None


def test_the_plan_of_an_existing_bundle_states_the_setup_of_the_edges_it_holds(
    client: TestClient, project: Path
) -> None:
    out = _assessed_edges(project)
    # One streamline, edge 0 in edges.json above: lh.precentral to Brain-Stem.
    with zipfile.ZipFile(out / "a.trx", "w") as archive:
        archive.writestr("dps/edge_id.int64", np.array([0, 99], dtype="<i8").tobytes())
    body = client.post(
        "/api/plan/blender",
        json={
            "config": {
                "_type": "TractVisualConfig",
                "subject_id": "S1",
                "simulation_name": "sim1",
                "network_bundle": "a",
                "network_top_edges": 0,
            },
            "subject_ids": ["S1"],
        },
    ).json()
    values = body["resolved"]["network_setup"]["values"]
    assert values["highlight_regions"] == ["Brain-Stem", "lh.precentral"]
    assert body["resolved"]["network_setup"]["n_streamlines"] == 6  # COUNTS above


def test_catalog_records_what_a_bundle_holds_and_that_edges_exist(
    client: TestClient, project: Path
) -> None:
    out = _assessed_edges(project)
    (out / "a.trx").write_bytes(b"trx")
    (out / "old.trx").write_bytes(b"trx")
    (out / "summary.json").write_text(
        json.dumps(
            {
                "bundles": {
                    "a": {"pairs": [["x", "y"]], "n_selected": 3},
                    "old": {"selection": "edges", "regions": []},
                    "gone": {"pairs": [["x", "y"]], "n_selected": 3},
                }
            }
        )
    )
    # The route needs its simulation listed, which takes more than this synthetic folder.
    import unittest.mock as mock

    from tit import catalog

    pm = get_path_manager()

    with (
        mock.patch.object(catalog, "_simulation_names", return_value=["sim1"]),
        mock.patch.object(catalog, "subject_ids", return_value=["S1"]),
    ):
        answer = catalog.simulation_networks(pm, "S1", "sim1")
    assert answer["networks"] == ["a", "old"]
    assert answer["assessed"] == [
        {"name": "a", "pairs": [["x", "y"]], "n_streamlines": 3}
    ]
    assert answer["has_edges"] is True


def test_the_gallery_reads_a_figure_a_video_a_scene_and_an_older_folder(
    client: TestClient, project: Path
) -> None:
    from unittest import mock

    from tit import catalog
    from tit.server.schemas import SimulationNetworks

    root = project / "derivatives/ti-toolbox/visual_exports/sub-S1/sim1/networks"
    new, old = root / "new", root / "old"
    new.mkdir(parents=True)
    old.mkdir()
    for name in (
        "ti_max.png",
        "direction.png",
        "ti_max_turntable.mp4",
        "network.blend",
        "network.json",
        "ti_max.png.part",
    ):
        (new / name).touch()
    # A folder from before the one-figure form, and files no render writes.
    for name in (
        "direction_lateral.png",
        "ti_max_posterior.png",
        "stray.png",
        ".DS_Store",
    ):
        (old / name).touch()
    (old / "network.json").write_text('{"colours": {"direction": {"files": []}}}')
    pm = get_path_manager()
    with (
        mock.patch.object(catalog, "_simulation_names", return_value=["sim1"]),
        mock.patch.object(catalog, "subject_ids", return_value=["S1"]),
    ):
        answer = catalog.simulation_networks(pm, "S1", "sim1")
    SimulationNetworks(**answer)  # what the route's response model must accept
    seen = {
        (r["network"], r["name"]): (r["kind"], r["colour"], r["view"])
        for r in answer["renders"]
    }
    assert seen == {
        ("new", "ti_max.png"): ("image", "ti_max", ""),
        ("new", "direction.png"): ("image", "direction", ""),
        ("new", "ti_max_turntable.mp4"): ("video", "ti_max", "turntable"),
        ("new", "network.blend"): ("scene", "", ""),
        ("old", "direction_lateral.png"): ("image", "direction", "lateral"),
        ("old", "ti_max_posterior.png"): ("image", "ti_max", "posterior"),
        ("old", "stray.png"): ("image", "stray", ""),
    }


def test_a_loaded_file_is_kept_after_its_checks_and_a_refusal_is_said_plainly(
    client: TestClient, project: Path, monkeypatch
) -> None:
    from tit.tract import own

    assert client.get("/api/tract/own", params={"subject": "S1"}).json() == {
        "networks": []
    }

    def post(name: str, body: bytes = b"bytes"):
        return client.post(
            "/api/tract/own",
            params={"subject": "S1", "name": name},
            content=body,
            headers={"content-type": "application/octet-stream"},
        )

    assert "choose a .trx, .tck or .trk" in post("mask.nii").json()["detail"]
    assert post("mine.tck", b"").json()["detail"] == "This file is empty."
    assert post("mine.tck", b"").status_code == 422
    assert (
        post("x.tck", b"bytes").status_code == 422
    )  # nibabel is mocked: no streamlines

    record = {
        "name": "mine",
        "source_filename": "mine.tck",
        "file": "mine.tck",
        "sha256": "0",
        "checks": {
            "coordinates": "world",
            "n_streamlines": 2,
            "n_points": 10,
            "fraction_points_in_brain": 1.0,
            "fraction_points_in_head": 1.0,
            "minimum_fraction_in_brain": 0.95,
            "checked_against": "final_tissues.nii.gz",
            "not_proven": "cannot prove",
        },
        "atlas": "DK40",
        "n_streamlines": 2,
        "n_both_ends_labelled": 1,
        "n_unlabelled": 1,
        "unlabelled_means": "far",
    }
    monkeypatch.setattr(own, "store", lambda *a: record)
    answer = post("mine.tck")
    assert answer.status_code == 201
    assert answer.json()["checks"]["not_proven"] == "cannot prove"


def test_a_loaded_files_assess_and_render_write_its_own_folders(
    client: TestClient, project: Path
) -> None:
    def plan(kind: str, config: dict) -> dict:
        return client.post(
            f"/api/plan/{kind}", json={"config": config, "subject_ids": ["S1"]}
        ).json()

    assess = plan(
        "tract",
        {
            "subject_id": "S1",
            "stages": ["assess"],
            "assess": {
                "simulations": ["sim1"],
                "selections": [],
                "own_network": "mine",
            },
        },
    )
    assert assess["jobs"][0]["output_dir"].endswith("sim1/tract/own_mine")
    render = plan(
        "blender",
        {
            "_type": "TractVisualConfig",
            "subject_id": "S1",
            "simulation_name": "sim1",
            "own_network": "mine",
            "metric": "ti_max",
        },
    )
    assert re.search(r"networks/\d{8}_\d{6}$", render["jobs"][0]["output_dir"])
    assert render["cost"]["mem_gb"] == 6


def test_a_config_may_not_name_a_loaded_file_and_another_network() -> None:
    from tit.blender.config import TractVisualConfig
    from tit.tract.config import Selection

    with pytest.raises(ValueError, match="own_network is the network"):
        TractVisualConfig("S1", "sim1", own_network="mine", network_bundle="cst")
    with pytest.raises(ValueError, match="kind must be 'edges'"):
        TractVisualConfig(
            "S1",
            "sim1",
            own_network="mine",
            selection=Selection(name="x", kind="edges", pairs=[["a", "b"]]),
        )
    with pytest.raises(ValueError, match="letters, digits"):
        TractVisualConfig("S1", "sim1", own_network="../escape")


def test_two_jobs_claim_one_blend_but_a_colour_each() -> None:
    from tit.server.overwrite_policy import _network_claims

    def claims(metric: str, **fields) -> set[str]:
        config = {"_type": "TractVisualConfig", "metric": metric, **fields}
        return _network_claims("blender", config, {"/net"})

    assert not claims("ti_max") & claims("direction")
    assert not claims("ti_max", export_blend=True) & claims("direction")
    assert claims("ti_max", export_blend=True) & claims(
        "direction", export_blend=True
    ) == {"/net/network.blend"}


def test_two_jobs_claim_a_network_each_in_one_folder() -> None:
    from tit.server.overwrite_policy import _named_folders

    class Job:
        output_dir = "/p/sim/tract"

    render = lambda metric: {  # noqa: E731
        "_type": "TractVisualConfig",
        "metric": metric,
        "selection": {"name": "a"},
    }
    # One network's two colours share its folder and no file.
    assert _named_folders("blender", render("ti_max"), [Job()]) != _named_folders(
        "blender", render("direction"), [Job()]
    )
    assert _named_folders("blender", render("ti_max"), [Job()]) == _named_folders(
        "blender", render("ti_max"), [Job()]
    )
    assess = lambda name: {"assess": {"selections": [{"name": name}]}}  # noqa: E731
    assert _named_folders("tract", assess("a"), [Job()]) != _named_folders(
        "tract", assess("b"), [Job()]
    )
    assert _named_folders("tract", assess("a"), [Job()]) == _named_folders(
        "tract", assess("a"), [Job()]
    )
    # Anything else claims the folder.
    assert _named_folders("blender", {"_type": "VectorConfig"}, [Job()]) == {
        "/p/sim/tract"
    }


def test_a_ranking_reads_every_montage_of_a_run_or_its_top_rows(tmp_path: Path) -> None:
    from tit.tract.target import ex_run_montages

    csv_path = tmp_path / "final_output.csv"
    # Composite = TImean_ROI x Focality: 0.2 > 0.1 > 0.05, and the last row repeats the first set.
    csv_path.write_text(
        "Montage,TImean_ROI,Focality\n"
        "A_B <> C_D_I1-1.0mA_I2-1.0mA,0.1,1.0\n"
        "E_F <> G_H_I1-1.0mA_I2-1.0mA,0.2,1.0\n"
        "I_J <> K_L_I1-1.0mA_I2-1.0mA,0.05,1.0\n"
        "A_B <> C_D_I1-0.5mA_I2-1.5mA,0.01,1.0\n"
    )
    assert ex_run_montages(str(csv_path), None) == [
        ["E", "F", "G", "H"],
        ["A", "B", "C", "D"],
        ["I", "J", "K", "L"],
    ]
    assert ex_run_montages(str(csv_path), 1) == [["E", "F", "G", "H"]]


@pytest.mark.parametrize("top_n", [0, -1])
def test_a_top_n_of_nothing_is_refused(top_n: int) -> None:
    from tit.tract.config import TargetConfig

    with pytest.raises(ValueError, match="top_n"):
        TargetConfig(top_n=top_n)
    assert TargetConfig(top_n=None).top_n is None


def test_a_long_ranking_reports_how_far_it_has_got(monkeypatch, caplog) -> None:
    import logging

    from simnibs.utils import TI_utils

    from tit.opt.ex import engine as ex_engine
    from tit.tract import target

    class Engine:
        def __init__(self, *args):
            self.leadfield, self.idx_lf = None, None

        def _load_leadfield(self):
            class Mesh:
                @staticmethod
                def find_tetrahedron_with_points(points, compute_baricentric=False):
                    return np.ones(len(points), dtype=int)

            self.mesh = Mesh()

    monkeypatch.setattr(ex_engine, "ExSearchEngine", Engine)
    monkeypatch.setattr(
        TI_utils, "get_field", lambda *a: np.ones((1, 3)), raising=False
    )
    # Each montage takes 40 s of a clock this test runs, so each after the first logs.
    clock = iter(range(0, 4000, 40))
    monkeypatch.setattr(target.time, "monotonic", lambda: next(clock))
    points = np.array([[0.0, 0, 0], [1, 0, 0]])
    offsets = np.array([0, 2])
    tangents = np.array([[1.0, 0, 0], [1, 0, 0]])
    with caplog.at_level(logging.INFO, logger="tit.tract.target"):
        rows, _ = target.rank_montages(
            "lf.hdf5",
            points,
            offsets,
            np.array([1.0]),
            tangents,
            [["A", "B", "C", "D"]] * 3,
        )
    assert len(rows) == 3
    assert "ranked 1/3 montages" in caplog.text
    assert "ranked 2/3 montages" in caplog.text
