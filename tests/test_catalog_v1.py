"""Unit tests for the v1 additions to :mod:`tit.catalog`.

Uses ``fastapi.testclient.TestClient`` against ``tit.server`` (same pattern
as ``tests/test_server_skeleton.py``) so the routes in
``tit/server/routes/catalog_v1.py`` are exercised end to end, not just the
underlying ``tit.catalog`` functions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """``ernie``: m2m + montages + ROI + leadfield + a flex run + an ex run."""
    pm = get_path_manager(str(tmp_path))
    m2m = pm.m2m("ernie")
    os.makedirs(m2m)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1")

    eeg_dir = pm.eeg_positions("ernie")
    os.makedirs(eeg_dir)
    Path(eeg_dir, "GSN-HydroCel-185.csv").write_text(
        "Electrode,1.0,2.0,3.0,E001\nElectrode,4.0,5.0,6.0,E002\n"
    )
    # SimNIBS writes this beside every cap. Its rows are landmarks, not electrodes.
    Path(eeg_dir, "Fiducials.csv").write_text(
        "Fiducial,0.0,90.0,0.0,Nz\nFiducial,0.0,-90.0,0.0,Iz\n"
    )

    montage_config_dir = pm.config_dir()
    os.makedirs(montage_config_dir)
    Path(montage_config_dir, "montage_list.json").write_text(
        json.dumps(
            {
                "nets": {
                    "GSN-HydroCel-185.csv": {
                        "uni_polar_montages": {
                            "L_Insula": [["E001", "E002"], ["E003", "E004"]]
                        },
                        "multi_polar_montages": {},
                    }
                }
            }
        )
    )

    roi_dir = pm.rois("ernie")
    os.makedirs(roi_dir)
    Path(roi_dir, "L_Insula.csv").write_text("-30.0,10.0,5.0\n")
    Path(roi_dir, "roi_list.txt").write_text("L_Insula.csv\n")

    leadfields_dir = pm.leadfields("ernie")
    os.makedirs(leadfields_dir)
    Path(leadfields_dir, "ernie_leadfield_GSN-HydroCel-185.hdf5").write_bytes(
        b"0" * 1024
    )

    flex_run = pm.flex_search_run("ernie", "20260101_000000")
    os.makedirs(flex_run)
    Path(flex_run, "flex_meta.json").write_text(
        json.dumps(
            {
                "goal": "mean",
                "roi": {"type": "spherical", "x": 1, "y": 2, "z": 3},
                "created": "2026-01-01T00:00:00",
            }
        )
    )
    # a run without a manifest must be ignored
    os.makedirs(pm.flex_search_run("ernie", "incomplete_run"))

    ex_run = pm.ex_search_run("ernie", "docs_ex_large")
    os.makedirs(ex_run)
    Path(ex_run, "run_config.json").write_text(
        json.dumps({"leadfield_hdf": "/x/ernie_leadfield_GSN-HydroCel-185.hdf5"})
    )
    Path(ex_run, "final_output.csv").write_text(
        "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index\n"
        "A_B <> C_D,1.0,1.0,0.30,0.20,0.10,1.5,0.30\n"
        "A_B <> C_D,1.5,0.5,0.40,0.25,0.12,1.6,0.40\n"
    )
    # a run without run_config.json must be ignored
    os.makedirs(pm.ex_search_run("ernie", "incomplete_run"))

    sim_dir = pm.simulation("ernie", "L_Insula")
    os.makedirs(os.path.join(sim_dir, "documentation"))
    voxel_analysis = os.path.join(
        sim_dir, "Analyses", "Voxel", "cortical_thalamus_aparc"
    )
    os.makedirs(voxel_analysis)
    Path(voxel_analysis, "analysis.json").write_text(
        json.dumps(
            {
                "field_name": "TI_max",
                "regions": ["Left-Thalamus"],
                "coordinate_space": None,
            }
        )
    )
    Path(voxel_analysis, "results.csv").write_text("Metric,Value\nfield_name,TI_max\n")
    Path(voxel_analysis, "roi_overlay.nii.gz").write_bytes(b"x")

    reports_dir = os.path.join(pm.reports(), "sub-ernie")
    os.makedirs(reports_dir)
    Path(reports_dir, "simulation_report_20260101_120000.html").write_text(
        "<html><body><script>1</script>report</body></html>"
    )

    stim_dir = os.path.join(m2m, "stim_configs")
    os.makedirs(stim_dir)
    Path(stim_dir, "my_freehand.json").write_text(
        json.dumps(
            {
                "name": "my_freehand",
                "type": "U",
                "electrode_positions": {"E001": [1, 2, 3]},
            }
        )
    )

    Path(pm.ti_toolbox()).mkdir(parents=True, exist_ok=True)
    Path(pm.ti_toolbox(), "notes.txt").write_text("hello notes")

    return tmp_path


@pytest.fixture()
def client(project: Path, tmp_path_factory, monkeypatch) -> TestClient:
    # Isolate tit.telemetry's user-level config file (same pattern as
    # tests/test_telemetry.py) so /api/settings never touches the real host
    # ~/.config/ti-toolbox/telemetry.json.
    telemetry_file = tmp_path_factory.mktemp("telemetry") / "telemetry.json"
    monkeypatch.setattr("tit.telemetry._config_path", lambda: telemetry_file)
    monkeypatch.setattr("tit.telemetry._cached_config", None)
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def test_subject_detail(client: TestClient) -> None:
    body = client.get("/api/catalog/subjects/ernie", headers=BEARER).json()
    assert body["id"] == "ernie"
    assert body["has_m2m"] is True
    assert body["m2m_path"].endswith("m2m_ernie")
    assert body["eeg_nets"] == ["GSN-HydroCel-185.csv"]
    assert body["has_leadfields"] == ["GSN-HydroCel-185.csv"]
    assert body["has_dwi"] is False
    assert body["has_ct"] is False
    assert body["has_sourcedata"] is False


def test_subject_detail_unknown_404(client: TestClient) -> None:
    assert client.get("/api/catalog/subjects/nope", headers=BEARER).status_code == 404


def test_sourcedata_only_subject_reachable_through_the_routes(
    project: Path, client: TestClient
) -> None:
    """Lane FX5: a subject staged under ``sourcedata/`` only -- no BIDS dir, no derivative --
    is listed by ``GET /api/catalog/subjects`` and answers on
    ``GET /api/catalog/subjects/{id}``, not 404, so Pre-processing can plan its DICOM stage.
    """
    pm = get_path_manager(str(project))
    t1w_dir = os.path.join(pm.sourcedata_subject("102"), "T1w")
    os.makedirs(t1w_dir)
    Path(t1w_dir, "IM0001.dcm").write_bytes(b"dicom")

    listed = client.get("/api/catalog/subjects", headers=BEARER).json()["subjects"]
    row = next((s for s in listed if s["id"] == "102"), None)
    assert row is not None, listed
    assert row["has_raw"] is False
    assert row["has_sourcedata"] is True

    detail = client.get("/api/catalog/subjects/102", headers=BEARER)
    assert detail.status_code == 200
    assert detail.json()["has_sourcedata"] is True


def test_montages_roundtrip(client: TestClient) -> None:
    got = client.get("/api/catalog/montages", headers=BEARER).json()
    assert got["nets"]["GSN-HydroCel-185.csv"]["uni_polar"]["L_Insula"] == [
        ["E001", "E002"],
        ["E003", "E004"],
    ]

    r = client.put(
        "/api/catalog/montages/GSN-HydroCel-185.csv/uni_polar/New_One",
        json={"pairs": [["E001", "E002"]]},
        headers=BEARER,
    )
    assert r.status_code == 200
    got = client.get("/api/catalog/montages", headers=BEARER).json()
    assert got["nets"]["GSN-HydroCel-185.csv"]["uni_polar"]["New_One"] == [
        ["E001", "E002"]
    ]

    r = client.delete(
        "/api/catalog/montages/GSN-HydroCel-185.csv/uni_polar/New_One", headers=BEARER
    )
    assert r.status_code == 204
    got = client.get("/api/catalog/montages", headers=BEARER).json()
    assert "New_One" not in got["nets"]["GSN-HydroCel-185.csv"]["uni_polar"]

    assert (
        client.delete(
            "/api/catalog/montages/GSN-HydroCel-185.csv/uni_polar/New_One",
            headers=BEARER,
        ).status_code
        == 404
    )


def test_put_montage_rejects_encoded_traversal_name(client: TestClient) -> None:
    """A literal `..` path segment (with or without a `/`) is already
    collapsed/blocked before routing (httpx/Starlette normalise it), so the
    name-safety check is exercised with a percent-encoded segment that
    *does* reach the handler as a single opaque path-param value."""
    r = client.put(
        "/api/catalog/montages/GSN-HydroCel-185.csv/uni_polar/%2e%2e",
        json={"pairs": [["E001", "E002"]]},
        headers=BEARER,
    )
    assert r.status_code == 422


def test_put_montage_rejects_unsafe_characters(client: TestClient) -> None:
    """ra_14 finding 1's "same for montage names on write" -- a name that
    reaches the handler intact (no path separator, so Starlette's own
    routing doesn't block it) but isn't `^[A-Za-z0-9_-]{1,64}$`."""
    r = client.put(
        "/api/catalog/montages/GSN-HydroCel-185.csv/uni_polar/weird%20name",
        json={"pairs": [["E001", "E002"]]},
        headers=BEARER,
    )
    assert r.status_code == 422


def test_eeg_nets(client: TestClient) -> None:
    """A cap with no electrodes is not a net, and is not listed as one.

    ``Fiducials.csv`` sits in every subject's ``eeg_positions`` and holds only
    registration landmarks. Listed as a net it could be picked in the Simulator
    and mapped a flex run onto, and the row then stayed unrunnable forever with
    nothing said, because there is no electrode in it to place.
    """
    body = client.get(
        "/api/catalog/eeg-nets", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert body == [
        {"name": "GSN-HydroCel-185.csv", "electrodes": ["E001", "E002"], "n": 2}
    ]


def test_roi_crud_roundtrip(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/rois", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert body == [
        {"name": "L_Insula", "x": -30.0, "y": 10.0, "z": 5.0, "space": "subject"}
    ]

    r = client.post(
        "/api/catalog/rois",
        params={"subject": "ernie"},
        json={"name": "Target_MNI", "x": 1.0, "y": 2.0, "z": 3.0, "space": "mni"},
        headers=BEARER,
    )
    assert r.status_code == 201
    assert r.json()["space"] == "mni"

    body = client.get(
        "/api/catalog/rois", params={"subject": "ernie"}, headers=BEARER
    ).json()
    names = {roi["name"] for roi in body}
    assert names == {"L_Insula", "Target_MNI"}
    assert next(roi for roi in body if roi["name"] == "Target_MNI")["space"] == "mni"

    r = client.delete(
        "/api/catalog/rois/Target_MNI", params={"subject": "ernie"}, headers=BEARER
    )
    assert r.status_code == 204
    assert (
        client.delete(
            "/api/catalog/rois/Target_MNI", params={"subject": "ernie"}, headers=BEARER
        ).status_code
        == 404
    )


def test_create_roi_rejects_path_traversal_name(
    client: TestClient, project: Path
) -> None:
    """ra_14 finding 1: a `name` with `..`/`/` must never reach the filesystem
    -- was `201` with a file written outside the project entirely."""
    outside_marker = project.parent / "escaped.csv"
    r = client.post(
        "/api/catalog/rois",
        params={"subject": "ernie"},
        json={
            "name": "../../../../../../../../outside/escaped",
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
        },
        headers=BEARER,
    )
    assert r.status_code == 422
    assert not outside_marker.exists()


@pytest.mark.parametrize("bad_name", ["", "a/b", "..", "a b", "a" * 65, "a$b"])
def test_create_roi_rejects_unsafe_names(client: TestClient, bad_name: str) -> None:
    r = client.post(
        "/api/catalog/rois",
        params={"subject": "ernie"},
        json={"name": bad_name, "x": 1.0, "y": 2.0, "z": 3.0},
        headers=BEARER,
    )
    assert r.status_code == 422


def test_create_roi_rejects_non_numeric_coordinates(client: TestClient) -> None:
    """ra_14 finding 1: x/y/z were written to the CSV verbatim with no type
    check -- an attacker-controlled string like "PWNED" landed in the file."""
    r = client.post(
        "/api/catalog/rois",
        params={"subject": "ernie"},
        json={"name": "Bad_Coords", "x": "PWNED", "y": 0, "z": 0},
        headers=BEARER,
    )
    assert r.status_code == 422
    body = client.get(
        "/api/catalog/rois", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert not any(roi["name"] == "Bad_Coords" for roi in body)


def test_create_roi_accepts_numeric_string_coordinates(client: TestClient) -> None:
    """A form field posting "1.5" (not a JSON number) must still work."""
    r = client.post(
        "/api/catalog/rois",
        params={"subject": "ernie"},
        json={"name": "String_Coords", "x": "1.5", "y": "2", "z": "-3.25"},
        headers=BEARER,
    )
    assert r.status_code == 201
    assert r.json() == {
        "name": "String_Coords",
        "x": 1.5,
        "y": 2.0,
        "z": -3.25,
        "space": "subject",
        "radius": None,
    }


def test_leadfields(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/leadfields", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert len(body) == 1
    assert body[0]["net"] == "GSN-HydroCel-185"
    assert body[0]["exists"] is True
    assert body[0]["size_bytes"] == 1024


def test_flex_runs_ignores_incomplete(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/flex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert [r["name"] for r in body] == ["20260101_000000"]
    assert body[0]["goal"] == "mean"
    assert body[0]["created"] == "2026-01-01T00:00:00"


def test_flex_run_electrodes_come_from_the_run_not_the_manifest(
    client: TestClient,
) -> None:
    """``flex_meta.json`` records no electrodes, so the run's own files must.

    Without this the Simulator's "Flex result" tab had nothing to build a
    ``Montage`` from and disabled every row.
    """
    pm = get_path_manager()
    run_dir = pm.flex_search_run("ernie", "20260101_000000")
    Path(run_dir, "electrode_positions.json").write_text(
        json.dumps(
            {
                "optimized_positions": [
                    [1.0, 2.0, 3.0],
                    [4.0, 5.0, 6.0],
                    [7.0, 8.0, 9.0],
                    [10.0, 11.0, 12.0],
                ],
                "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
            }
        )
    )
    Path(run_dir, "electrode_mapping_GSN-HydroCel-185.json").write_text(
        json.dumps(
            {
                "mapped_labels": ["E001", "E002", "E003", "E004"],
                "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
                "eeg_net": "GSN-HydroCel-185.csv",
            }
        )
    )

    run = client.get(
        "/api/catalog/flex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()[0]
    assert "electrodes" not in run["manifest"]
    assert run["mappings"] == [
        {
            "eeg_net": "GSN-HydroCel-185.csv",
            "pairs": [["E001", "E002"], ["E003", "E004"]],
        }
    ]
    assert run["optimized"] == [
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]],
    ]


def test_flex_run_without_a_mapping_still_offers_free_positions(
    client: TestClient,
) -> None:
    pm = get_path_manager()
    run_dir = pm.flex_search_run("ernie", "20260101_000000")
    Path(run_dir, "electrode_positions.json").write_text(
        json.dumps(
            {
                "optimized_positions": [
                    [1.0, 2.0, 3.0],
                    [4.0, 5.0, 6.0],
                    [7.0, 8.0, 9.0],
                    [10.0, 11.0, 12.0],
                ]
            }
        )
    )
    run = client.get(
        "/api/catalog/flex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()[0]
    assert run["mappings"] == []
    # No channel_array_indices: consecutive pairing, as resolve_flex_montage does.
    assert run["optimized"] == [
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]],
    ]


def test_flex_run_with_no_positions_reports_none(client: TestClient) -> None:
    run = client.get(
        "/api/catalog/flex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()[0]
    assert run["mappings"] == []
    assert run["optimized"] is None


@pytest.fixture()
def real_mapping_stack(monkeypatch: pytest.MonkeyPatch):
    """Give the mapping code real implementations of its two mocked externals.

    ``conftest`` mocks ``scipy`` and ``simnibs`` because neither installs on
    the host, but the mapping this endpoint performs is exactly those two
    calls plus a distance matrix. Both are replaced here by independent
    implementations -- an exhaustive-permutation assignment (correct for the
    four electrodes a TI montage has) and a plain CSV parse -- so the test
    exercises ``resolve_flex_montage``'s real arithmetic and its real file
    output rather than a stubbed return value.
    """
    import itertools
    import sys

    import numpy as np

    def brute_force_assignment(cost):
        cost = np.asarray(cost)
        n = cost.shape[0]
        best = min(
            itertools.permutations(range(cost.shape[1]), n),
            key=lambda cols: sum(cost[i, c] for i, c in enumerate(cols)),
        )
        return np.arange(n), np.array(best)

    def read_csv(path):
        types, coords, names = [], [], []
        with open(path) as f:
            for line in f:
                parts = [p.strip() for p in line.strip().split(",")]
                if len(parts) < 5:
                    continue
                types.append(parts[0])
                coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
                names.append(parts[4])
        return types, np.array(coords), None, names, None, None

    monkeypatch.setattr(
        sys.modules["scipy.optimize"], "linear_sum_assignment", brute_force_assignment
    )
    monkeypatch.setattr(
        "tit.tools.map_electrodes.linear_sum_assignment", brute_force_assignment
    )
    csv_reader = sys.modules.setdefault("simnibs.utils.csv_reader", None)
    if csv_reader is None:  # pragma: no cover - depends on import order
        import types as _types

        csv_reader = _types.ModuleType("simnibs.utils.csv_reader")
        sys.modules["simnibs.utils.csv_reader"] = csv_reader
    monkeypatch.setattr(csv_reader, "read_csv_positions", read_csv, raising=False)


def test_flex_run_mapping_maps_onto_a_net_the_run_never_saw(
    client: TestClient, real_mapping_stack: None
) -> None:
    """The Simulator's "Map to net" must reach every net, not only pre-mapped ones.

    The run below has no ``electrode_mapping_*.json`` at all. Each optimised
    position sits on top of one electrode of ``EGI_template.csv`` and far from
    the others, so the nearest-electrode assignment is unambiguous without
    re-deriving it here; the endpoint must return those four labels and leave
    the mapping cached beside the run.
    """
    pm = get_path_manager()
    Path(pm.eeg_positions("ernie"), "EGI_template.csv").write_text(
        "Electrode,0.0,0.0,0.0,A1\n"
        "Electrode,100.0,0.0,0.0,A2\n"
        "Electrode,0.0,100.0,0.0,A3\n"
        "Electrode,0.0,0.0,100.0,A4\n"
        "Electrode,100.0,100.0,100.0,A5\n"
    )
    run_dir = pm.flex_search_run("ernie", "20260101_000000")
    Path(run_dir, "electrode_positions.json").write_text(
        json.dumps(
            {
                "optimized_positions": [
                    [1.0, 0.0, 0.0],
                    [99.0, 0.0, 0.0],
                    [0.0, 99.0, 0.0],
                    [0.0, 0.0, 99.0],
                ],
                "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
            }
        )
    )
    assert not os.path.exists(Path(run_dir, "electrode_mapping_EGI_template.json"))

    r = client.get(
        "/api/catalog/flex-runs/20260101_000000/mapping",
        params={"subject": "ernie", "eeg_net": "EGI_template.csv"},
        headers=BEARER,
    )
    assert r.status_code == 200
    assert r.json() == {
        "eeg_net": "EGI_template.csv",
        "pairs": [["A1", "A2"], ["A3", "A4"]],
    }
    # Cached beside the run, so `flex-runs` now lists it like any pre-mapped net.
    assert os.path.isfile(Path(run_dir, "electrode_mapping_EGI_template.json"))
    run = client.get(
        "/api/catalog/flex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()[0]
    assert {m["eeg_net"] for m in run["mappings"]} == {"EGI_template.csv"}


def test_flex_run_mapping_unknown_net_is_404(client: TestClient) -> None:
    r = client.get(
        "/api/catalog/flex-runs/20260101_000000/mapping",
        params={"subject": "ernie", "eeg_net": "Nope.csv"},
        headers=BEARER,
    )
    assert r.status_code == 404


def test_ex_runs_ignores_incomplete_and_derives_net(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/ex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert [r["run_name"] for r in body] == ["docs_ex_large"]
    assert body[0]["eeg_net"] == "GSN-HydroCel-185.csv"
    assert body[0]["best"] == {"montage": "A_B <> C_D", "score": 0.40}


def test_ex_run_results_table(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/ex-runs/docs_ex_large/results",
        params={"subject": "ernie", "kind": "ex"},
        headers=BEARER,
    ).json()
    assert body["columns"][0] == "Montage"
    assert len(body["rows"]) == 2


def test_analyses_and_summary(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/analyses",
        params={"subject": "ernie", "simulation": "L_Insula"},
        headers=BEARER,
    ).json()
    assert len(body) == 1
    entry = body[0]
    assert entry["name"] == "cortical_thalamus_aparc"
    assert entry["field"] == "TI_max"
    assert entry["roi"] == "Left-Thalamus"
    assert entry["nifti"].endswith("roi_overlay.nii.gz")

    summary = client.get(
        "/api/catalog/analyses/cortical_thalamus_aparc/summary",
        params={"subject": "ernie", "simulation": "L_Insula"},
        headers=BEARER,
    ).json()
    assert summary["columns"] == ["Metric", "Value"]


def test_reports_and_report_file(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/reports", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert len(body) == 1
    report = body[0]
    assert report["kind"] == "simulation_report"
    assert report["id"] == "ernie/simulation_report_20260101_120000"

    r = client.get(f"/api/files/report/{report['id']}", headers=BEARER)
    assert r.status_code == 200
    assert "report" in r.text
    # NOTE (gap for the orchestrator, tit/server/app.py is not this lane's to
    # edit): CSPMiddleware appends its own app-wide CSP to *every*
    # text/html response, so this header currently comes back as this
    # route's report CSP *plus* the app's, comma-joined -- browsers enforce
    # multiple CSP headers as the intersection, which would defeat this
    # route's `script-src 'unsafe-inline'` (the app CSP has no script-src,
    # so default-src 'self' wins and blocks the report's inline script).
    # CSPMiddleware needs to skip responses that already carry the header.
    # This asserts the substring this route contributes; see the final report.
    assert "script-src 'unsafe-inline'" in r.headers["content-security-policy"]
    assert "img-src data:" in r.headers["content-security-policy"]
    # ra_14 finding 6: the report's own CSP must also sandbox the document
    # (opaque origin -- no cookies, no same-origin fetch) independent of the
    # renderer's iframe `sandbox=` attribute, and nosniff on top of that.
    assert "sandbox allow-scripts" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_report_route_has_exactly_one_csp_header(client: TestClient) -> None:
    """`app.py`'s CSPMiddleware must skip a response that already set its own
    Content-Security-Policy (the report route's sandboxed-iframe policy) --
    two CSP headers are enforced by browsers as their *intersection*, which
    would silently strip this route's `script-src 'unsafe-inline'`."""
    reports = client.get(
        "/api/catalog/reports", params={"subject": "ernie"}, headers=BEARER
    ).json()
    report_id = reports[0]["id"]
    r = client.get(f"/api/files/report/{report_id}", headers=BEARER)
    assert r.status_code == 200
    assert len(r.headers.get_list("content-security-policy")) == 1


def test_freehand_roundtrip(client: TestClient) -> None:
    body = client.get(
        "/api/catalog/freehand", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert body == [
        {
            "name": "my_freehand",
            "type": "U",
            "electrode_positions": [{"label": "E001", "x": 1, "y": 2, "z": 3}],
        }
    ]

    r = client.put(
        "/api/catalog/freehand/second",
        params={"subject": "ernie"},
        json={
            "type": "M",
            "electrode_positions": [{"label": "P1", "x": 1.0, "y": 2.0, "z": 3.0}],
        },
        headers=BEARER,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "second"
    body = client.get(
        "/api/catalog/freehand", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert {c["name"] for c in body} == {"my_freehand", "second"}


def test_put_freehand_rejects_unsafe_characters(client: TestClient) -> None:
    """`{name}` can't carry `/` via routing already (a literal `..` segment
    is normalised away before it ever reaches the handler); a name that
    does reach the handler intact but isn't `^[A-Za-z0-9_-]{1,64}$` must
    still be rejected explicitly (ra_14 finding 1)."""
    r = client.put(
        "/api/catalog/freehand/weird%20name",
        params={"subject": "ernie"},
        json={
            "type": "U",
            "electrode_positions": [{"label": "P1", "x": 1, "y": 2, "z": 3}],
        },
        headers=BEARER,
    )
    assert r.status_code == 422


def test_put_freehand_rejects_non_numeric_coordinates(client: TestClient) -> None:
    r = client.put(
        "/api/catalog/freehand/bad_coords",
        params={"subject": "ernie"},
        json={
            "type": "U",
            "electrode_positions": [
                {"label": "P1", "x": "not-a-number", "y": 2, "z": 3}
            ],
        },
        headers=BEARER,
    )
    assert r.status_code == 422


def test_notes_roundtrip(client: TestClient) -> None:
    body = client.get("/api/catalog/notes", headers=BEARER).json()
    assert body["text"] == "hello notes"

    r = client.put("/api/catalog/notes", json={"text": "updated"}, headers=BEARER)
    assert r.status_code == 200
    assert r.json()["text"] == "updated"
    assert client.get("/api/catalog/notes", headers=BEARER).json()["text"] == "updated"


def test_subject_info_matrix(client: TestClient) -> None:
    # "fastsurfer" alongside the legacy "freesurfer" column is W3b's addition
    # (dev/notes/v3-docker-streamline-plan.md's D2/FastSurfer-in row) --
    # asserted by column *name* below rather than a fixed index, so this
    # test does not re-break the next time that lane adds a column.
    body = client.get("/api/catalog/subject-info", headers=BEARER).json()
    columns = body["columns"]
    assert columns[0] == "subject"
    assert set(columns) >= {
        "raw",
        "fastsurfer",
        "freesurfer",
        "m2m",
        "dwi",
        "ct",
        "simulations",
    }
    row = next(r for r in body["rows"] if r[0] == "ernie")
    assert row[columns.index("m2m")] is True


def test_group_catalog_shape(client: TestClient) -> None:
    body = client.get("/api/catalog/group", headers=BEARER).json()
    assert set(body) == {"stats", "nilearn", "group_analyses"}


def test_atlases_and_regions_with_fake_lut(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    seg_dir = os.path.join(pm.m2m("ernie"), "segmentation")
    os.makedirs(seg_dir, exist_ok=True)
    Path(seg_dir, "lh.aparc.DK40.annot").write_bytes(
        b""
    )  # presence is enough for list_atlases
    Path(seg_dir, "labeling.nii.gz").write_bytes(b"x")
    Path(seg_dir, "labeling_LUT.txt").write_text("1 GM 0 255 0\n")

    body = client.get(
        "/api/catalog/atlases",
        params={"subject": "ernie", "space": "subject", "kind": "cortical"},
        headers=BEARER,
    ).json()
    names = {a["name"] for a in body}
    assert "DK40" in names  # builtin, always listed

    body = client.get(
        "/api/catalog/atlases",
        params={"subject": "ernie", "space": "subject", "kind": "subcortical"},
        headers=BEARER,
    ).json()
    assert any(a["name"] == "labeling.nii.gz" for a in body)


def test_atlas_regions_unknown_returns_404(client: TestClient) -> None:
    r = client.get(
        "/api/catalog/atlases/regions",
        params={"subject": "ernie", "atlas": "nope.nii.gz"},
        headers=BEARER,
    )
    assert r.status_code == 404


def test_atlas_regions_cortical_returns_integer_id_and_hemi(
    client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Region.id must be the real `.annot` label index, not a display string
    (`FlexConfig.AtlasROI.label` needs this exact integer)."""
    import sys
    from unittest.mock import MagicMock

    pm = get_path_manager()
    seg_dir = os.path.join(pm.m2m("ernie"), "segmentation")
    os.makedirs(seg_dir, exist_ok=True)
    Path(seg_dir, "lh.aparc.DK40.annot").write_bytes(b"")
    Path(seg_dir, "rh.aparc.DK40.annot").write_bytes(b"")

    # monkeypatch (not a bare `sys.modules[...] = ...`/`setattr`) so this is
    # reverted after the test even on failure -- a direct assignment here
    # permanently altered the shared conftest mock for every later test in
    # the process (ra_11 finding 11).
    nfs_mock = sys.modules["nibabel.freesurfer"]
    fsio_mock = MagicMock()
    monkeypatch.setitem(sys.modules, "nibabel.freesurfer.io", fsio_mock)
    monkeypatch.setattr(nfs_mock, "io", fsio_mock, raising=False)

    def _read_annot(path, *_args, **_kwargs):
        if path.endswith("lh.aparc.DK40.annot"):
            return (None, None, [b"unknown", b"bankssts"])
        return (None, None, [b"unknown", b"precentral"])

    fsio_mock.read_annot.side_effect = _read_annot

    body = client.get(
        "/api/catalog/atlases/regions",
        params={"subject": "ernie", "atlas": "DK40"},
        headers=BEARER,
    ).json()
    assert {"id": 1, "name": "bankssts", "hemi": "lh"} in body
    assert {"id": 1, "name": "precentral", "hemi": "rh"} in body
    assert all(r["name"] != "unknown" for r in body)
    assert all(isinstance(r["id"], int) for r in body)


def test_atlas_regions_subcortical_returns_integer_id_and_null_hemi(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    seg_dir = os.path.join(pm.m2m("ernie"), "segmentation")
    os.makedirs(seg_dir, exist_ok=True)
    Path(seg_dir, "labeling.nii.gz").write_bytes(b"x")
    Path(seg_dir, "labeling_labels.txt").write_text(
        "# header\n 1 1 100 50.0 Left-Thalamus\n 2 2 120 60.0 Right-Thalamus\n"
    )

    body = client.get(
        "/api/catalog/atlases/regions",
        params={"subject": "ernie", "atlas": "labeling.nii.gz"},
        headers=BEARER,
    ).json()
    assert {"id": 1, "name": "Left-Thalamus", "hemi": None} in body
    assert {"id": 2, "name": "Right-Thalamus", "hemi": None} in body


def _seed_labeling(pm, cache: bool = True) -> Path:
    seg_dir = os.path.join(pm.m2m("ernie"), "segmentation")
    os.makedirs(seg_dir, exist_ok=True)
    volume = Path(seg_dir, "labeling.nii.gz")
    volume.write_bytes(b"x")
    if cache:
        Path(seg_dir, "labeling_labels.txt").write_text(
            "# Index SegId NVoxels Volume_mm3 StructName\n"
            "  1  49  1200  1200.0 Right-Thalamus\n"
            "  2  10  1100  1100.0 Left-Thalamus\n"
        )
    return volume


def test_nifti_labels_defaults_to_the_subject_labeling_volume(
    client: TestClient, project: Path
) -> None:
    _seed_labeling(get_path_manager())
    body = client.get(
        "/api/catalog/nifti/labels", params={"subject": "ernie"}, headers=BEARER
    ).json()
    # Sorted by id, with the voxel count VoxelAtlasManager's own parser discards.
    assert body == [
        {"id": 10, "name": "Left-Thalamus", "n_voxels": 1100},
        {"id": 49, "name": "Right-Thalamus", "n_voxels": 1200},
    ]


def test_nifti_labels_accepts_an_explicit_path_inside_the_project(
    client: TestClient, project: Path
) -> None:
    volume = _seed_labeling(get_path_manager())
    body = client.get(
        "/api/catalog/nifti/labels",
        params={"subject": "ernie", "path": str(volume)},
        headers=BEARER,
    ).json()
    assert [r["id"] for r in body] == [10, 49]


def test_nifti_labels_refuses_a_path_outside_the_project(
    client: TestClient, project: Path, tmp_path: Path
) -> None:
    outside = tmp_path.parent / "outside.nii.gz"
    outside.write_bytes(b"x")
    r = client.get(
        "/api/catalog/nifti/labels",
        params={"subject": "ernie", "path": str(outside)},
        headers=BEARER,
    )
    # Same 404 a missing file gets: the route must not confirm that a file outside the
    # jail exists.
    assert r.status_code == 404


def test_nifti_labels_404s_for_an_unknown_subject(client: TestClient) -> None:
    r = client.get(
        "/api/catalog/nifti/labels", params={"subject": "nobody"}, headers=BEARER
    )
    assert r.status_code == 404


def test_nifti_labels_404s_when_the_volume_is_not_there(
    client: TestClient, project: Path
) -> None:
    r = client.get(
        "/api/catalog/nifti/labels", params={"subject": "ernie"}, headers=BEARER
    )
    assert r.status_code == 404


def test_flex_run_artifacts_lists_pngs_json_and_manifest(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    run_dir = pm.flex_search_run("ernie", "20260101_000000")
    Path(run_dir, "pareto_sweep_plot.png").write_bytes(b"png")
    Path(run_dir, "pareto_results.json").write_text("{}")
    skin_dir = os.path.join(run_dir, "skin_visualization")
    os.makedirs(skin_dir, exist_ok=True)
    Path(skin_dir, "skin_surface_2d.png").write_bytes(b"png")

    body = client.get(
        "/api/catalog/flex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()
    run = next(r for r in body if r["name"] == "20260101_000000")
    kinds = {os.path.basename(a["path"]): a["kind"] for a in run["artifacts"]}
    assert kinds["pareto_sweep_plot.png"] == "image"
    assert kinds["skin_surface_2d.png"] == "image"
    assert kinds["pareto_results.json"] == "json"
    assert kinds["flex_meta.json"] == "manifest"


def test_ex_run_artifacts_lists_pngs_and_manifest(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    run_dir = pm.ex_search_run("ernie", "docs_ex_large")
    Path(run_dir, "montage_distributions.png").write_bytes(b"png")
    Path(run_dir, "intensity_vs_focality_scatter.png").write_bytes(b"png")

    body = client.get(
        "/api/catalog/ex-runs", params={"subject": "ernie"}, headers=BEARER
    ).json()
    run = next(r for r in body if r["run_name"] == "docs_ex_large")
    kinds = {os.path.basename(a["path"]): a["kind"] for a in run["artifacts"]}
    assert kinds["montage_distributions.png"] == "image"
    assert kinds["intensity_vs_focality_scatter.png"] == "image"
    assert kinds["final_output.csv"] == "csv"
    assert kinds["run_config.json"] == "manifest"


def test_electrode_overlays_presence(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    overlay_dir = os.path.join(pm.simulation("ernie", "L_Insula"), "TI", "montage_imgs")
    os.makedirs(overlay_dir, exist_ok=True)
    Path(overlay_dir, "electrode_overlay_subject.nii.gz").write_bytes(b"x")

    body = client.get(
        "/api/catalog/electrode-overlays",
        params={"subject": "ernie", "simulation": "L_Insula"},
        headers=BEARER,
    ).json()
    by_mode = {e["mode"]: e for e in body}
    assert by_mode["TI"]["exists"] is True
    assert by_mode["mTI"]["exists"] is False

    r = client.get(
        "/api/catalog/electrode-overlays",
        params={"subject": "ernie", "simulation": "nope"},
        headers=BEARER,
    )
    assert r.status_code == 404


def test_files_artifact_traversal_forbidden(client: TestClient, project: Path) -> None:
    outside = project.parent / "secret.txt"
    outside.write_text("nope")
    r = client.get("/api/files/artifact", params={"path": str(outside)}, headers=BEARER)
    assert r.status_code == 403


def test_files_csv(client: TestClient, project: Path) -> None:
    pm = get_path_manager()
    csv_path = os.path.join(
        pm.ex_search_run("ernie", "docs_ex_large"), "final_output.csv"
    )
    body = client.get(
        "/api/files/csv", params={"path": csv_path}, headers=BEARER
    ).json()
    assert body["columns"][0] == "Montage"


def test_settings_roundtrip(client: TestClient) -> None:
    body = client.get("/api/settings", headers=BEARER).json()
    assert body["theme"] == "system"
    assert body["panels"] == []

    r = client.put(
        "/api/settings",
        json={
            "telemetry": {"consented": True, "enabled": True},
            "panels": ["source", "quick-notes"],
            "image_tag": "v3.0.0",
            "allow_unsafe_overrides": True,
            "theme": "dark",
        },
        headers=BEARER,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["panels"] == ["source", "quick-notes"]
    assert body["image_tag"] == "v3.0.0"
    assert body["allow_unsafe_overrides"] is True
    assert body["theme"] == "dark"
    assert body["telemetry"] == {"consented": True, "enabled": True}

    # persisted: a fresh GET (same server instance) reflects it
    assert client.get("/api/settings", headers=BEARER).json()["theme"] == "dark"


def test_settings_rejects_invalid_theme(client: TestClient) -> None:
    r = client.put(
        "/api/settings",
        json={"panels": [], "theme": "solarized"},
        headers=BEARER,
    )
    assert r.status_code == 422


@pytest.mark.parametrize("bad_panels", [["not-a-real-panel"], "source", [1, 2]])
def test_settings_rejects_invalid_panels(client: TestClient, bad_panels) -> None:
    r = client.put(
        "/api/settings",
        json={"panels": bad_panels, "theme": "system"},
        headers=BEARER,
    )
    assert r.status_code == 422


def test_settings_accepts_every_known_panel(client: TestClient) -> None:
    known = [
        "source",
        "cluster-permutation",
        "nifti-group-average",
        "nilearn-visuals",
        "quick-notes",
        "visual-exporter",
    ]
    r = client.put(
        "/api/settings", json={"panels": known, "theme": "light"}, headers=BEARER
    )
    assert r.status_code == 200
    assert sorted(r.json()["panels"]) == sorted(known)


def test_system_terminate_refuses_pid_1(client: TestClient) -> None:
    r = client.post("/api/system/terminate", json={"pid": 1}, headers=BEARER)
    assert r.status_code == 403


def test_system_terminate_refuses_own_pid(client: TestClient) -> None:
    r = client.post("/api/system/terminate", json={"pid": os.getpid()}, headers=BEARER)
    assert r.status_code == 403


def test_system_terminate_refuses_non_toolbox_process(client: TestClient) -> None:
    """The current test-runner process is real and alive, but its cmdline
    matches none of `RELEVANT_KEYWORDS` -- must be refused, never killed."""
    r = client.post(
        "/api/system/terminate",
        json={"pid": os.getppid() or os.getpid()},
        headers=BEARER,
    )
    # os.getppid() is the test runner's own parent -- practically never a
    # toolbox-relevant process by keyword match, and if it somehow guessed
    # `pid == 1` (rare, container init) that's covered by the other test.
    assert r.status_code in (403, 404)


def test_system_terminate_rejects_bad_pid_type(client: TestClient) -> None:
    for bad in ["1", 1.5, True, None]:
        r = client.post("/api/system/terminate", json={"pid": bad}, headers=BEARER)
        assert r.status_code == 422, bad


def test_system_terminate_unknown_pid_404(client: TestClient) -> None:
    # A pid essentially guaranteed not to exist.
    r = client.post("/api/system/terminate", json={"pid": 2**30 - 1}, headers=BEARER)
    assert r.status_code in (403, 404)


def test_project_init_submits_a_job_or_degrades_to_503(client: TestClient) -> None:
    """``project_init`` is in the contract's frozen JobKind enum but B1 has
    not yet added it to ``tit.jobs.spec.JOB_KINDS``/``tit.jobs.kinds`` -- this
    route must degrade to a clear 503, never a raw 500, until that lands."""
    r = client.post("/api/project/init", json={"example_data": False}, headers=BEARER)
    assert r.status_code in (201, 503)
    if r.status_code == 201:
        assert r.json()["kind"] == "project_init"


def test_capabilities_has_jupyter_bool(client: TestClient) -> None:
    body = client.get("/api/capabilities", headers=BEARER).json()
    assert isinstance(body["jupyter"], bool)


def test_schema_routes(client: TestClient) -> None:
    full = client.get("/api/schema", headers=BEARER).json()
    assert "$defs" in full
    one = client.get("/api/schema/SimulationConfig", headers=BEARER).json()
    assert isinstance(one, dict) and one
    assert client.get("/api/schema/NoSuchThing", headers=BEARER).status_code == 404


def test_view_returns_a_valid_scene_no_x11_needed(client: TestClient) -> None:
    """D3 (dev/notes/v3-docker-streamline-plan.md): the in-app viewer needs no
    X11 capability at all any more -- it is the Tetravox embed, fed by
    /api/files/raw, and GET /api/view/{kind} builds its scene unconditionally."""
    spec = client.get(
        "/api/view/subject",
        params={"subject": "ernie", "space": "subject"},
        headers=BEARER,
    ).json()
    assert spec["space"] == "subject"
    scene = spec["scene"]
    assert scene["version"] == 2
    assert scene["datasets"], scene
    assert scene["layers"]


def test_view_args_rejects_option_looking_layer_path(client: TestClient) -> None:
    """A layer path that doesn't resolve to a real file (e.g. a bare
    ``-ss``, an attempt to smuggle a Freeview flag) is rejected by the jail
    before it ever reaches argument construction."""
    spec = client.get(
        "/api/view/subject",
        params={"subject": "ernie", "space": "subject"},
        headers=BEARER,
    ).json()
    spec["layers"].append({"path": "-ss", "kind": "volume"})
    r = client.post("/api/view/args", json={"viewspec": spec}, headers=BEARER)
    assert r.status_code == 403


def test_view_args_matches_freeview_launch_args(
    client: TestClient, monkeypatch
) -> None:
    """ra_13 finding 9: the Viewer page's command preview must be the exact
    argv the launch route would use, from one shared code path."""
    spec = client.get(
        "/api/view/subject",
        params={"subject": "ernie", "space": "subject"},
        headers=BEARER,
    ).json()
    r = client.post("/api/view/args", json={"viewspec": spec}, headers=BEARER)
    assert r.status_code == 200
    body = r.json()
    assert body["freeview_args"] == spec["freeview_args"]
    assert body["freeview_command"] == ["freeview"] + spec["freeview_args"]


def test_view_args_also_jails_layer_paths(client: TestClient) -> None:
    spec = client.get(
        "/api/view/subject",
        params={"subject": "ernie", "space": "subject"},
        headers=BEARER,
    ).json()
    spec["layers"].append({"path": "/etc/passwd", "kind": "volume"})
    r = client.post("/api/view/args", json={"viewspec": spec}, headers=BEARER)
    assert r.status_code == 403


def test_view_unknown_subject_404(client: TestClient) -> None:
    r = client.get("/api/view/subject", params={"subject": "nope"}, headers=BEARER)
    assert r.status_code == 404
