"""HTTP-level tests for ``POST /api/validate/{kind}`` and ``POST /api/plan/{kind}``."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

# kind="nifti_average"/"nilearn" resolve to tit.stats.nifti_average_config.NiftiAverageConfig /
# tit.plotting.nilearn.config.NilearnConfig. Importing either runs tit/stats/__init__.py (any
# submodule import does), which eagerly imports tit.stats.permutation -> tit.stats.engine ->
# scipy.ndimage/scipy.stats -- neither is in tests/conftest.py's _MOCK_PACKAGES.
# test_config_schema.py/test_plotting.py/test_pre_pipeline.py carry this same local fallback
# for the same reason; see their comments.
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-abc123"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m("001"))
    os.makedirs(pm.m2m("002"))
    (tmp_path / "dataset_description.json").write_text("{}")
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url=BASE)


def _montage(name: str = "M1") -> dict:
    return {
        "_type": "Montage",
        "name": name,
        "mode": "net",
        "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
        "eeg_net": "GSN-HydroCel-185.csv",
    }


def _sim_config(**overrides) -> dict:
    data = {
        "subject_id": "001",
        "montages": [_montage()],
        "output_fields": ["TI_max"],
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------


def test_validate_unknown_kind_404(client: TestClient) -> None:
    resp = client.post("/api/validate/bogus", json={"config": {}}, headers=BEARER)
    assert resp.status_code == 404


def test_validate_sim_ok_for_a_good_config(client: TestClient) -> None:
    resp = client.post(
        "/api/validate/sim", json={"config": _sim_config()}, headers=BEARER
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ok": True, "errors": []}


def test_validate_sim_reports_field_path_for_bad_conductivity(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/validate/sim",
        json={"config": _sim_config(conductivity="bogus")},
        headers=BEARER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert len(body["errors"]) == 1
    assert body["errors"][0]["path"] == "conductivity"
    assert "bogus" in body["errors"][0]["message"]


def test_validate_sim_rejects_a_misspelled_key(client: TestClient) -> None:
    """ra_11 finding 3: deserialize_config's strict=True (wired in at this route) turns a
    renamed/misspelled config field into a reported error instead of a silent no-op --
    e.g. a page that renamed "conductivity" to "conductivety" used to validate as ok=True
    and simply run with the SimulationConfig default instead."""
    resp = client.post(
        "/api/validate/sim",
        json={"config": _sim_config(conductivety="scalar")},
        headers=BEARER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert len(body["errors"]) == 1
    assert "conductivety" in body["errors"][0]["message"]


def test_validate_sim_reports_error_for_bad_output_fields(client: TestClient) -> None:
    # "Invalid output field(s) [...]" doesn't literally contain the identifier
    # "output_fields", so _guess_field_path's heuristic falls back to "" (whole-config)
    # here -- this test documents that limitation rather than asserting a false positive.
    resp = client.post(
        "/api/validate/sim",
        json={"config": _sim_config(output_fields=["not_a_real_field"])},
        headers=BEARER,
    )
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"][0]["path"] == ""
    assert "not_a_real_field" in body["errors"][0]["message"]


def test_validate_pre_reports_empty_subject_ids(client: TestClient) -> None:
    resp = client.post(
        "/api/validate/pre", json={"config": {"subject_ids": []}}, headers=BEARER
    )
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"][0]["path"] == "subject_ids"


def _analyzer_group_config(**overrides) -> dict:
    data = {
        "mode": "group",
        "subject_id": None,
        "subject_ids": ["001", "002"],
        "simulation": "M1",
        "analysis_type": "spherical",
        "center": [1.0, 2.0, 3.0],
        "radius": 5.0,
    }
    data.update(overrides)
    return data


def test_validate_analyzer_group_mode_ok_with_null_subject_id(
    client: TestClient,
) -> None:
    # mode="group" is valid with subject_id explicitly null as long as subject_ids is
    # non-empty -- AnalyzerConfig.__post_init__ only requires subject_id for mode="single".
    resp = client.post(
        "/api/validate/analyzer",
        json={"config": _analyzer_group_config()},
        headers=BEARER,
    )
    assert resp.json() == {"ok": True, "errors": []}


def test_validate_analyzer_group_mode_rejects_empty_subject_ids(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/validate/analyzer",
        json={"config": _analyzer_group_config(subject_ids=[])},
        headers=BEARER,
    )
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"][0]["path"] == "subject_ids"


def test_validate_analyzer_single_mode_rejects_missing_subject_id(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/validate/analyzer",
        json={
            "config": _analyzer_group_config(
                mode="single", subject_id=None, subject_ids=[]
            )
        },
        headers=BEARER,
    )
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"][0]["path"] == "subject_id"


def test_validate_nilearn_rejects_empty_pairs(client: TestClient) -> None:
    # NiftiAverageConfig/NilearnConfig are real dataclasses now (CONFIG_CLASS_REGISTRY,
    # registered by the runners lane) -- validate/plan actually check them, not the old
    # trivially-ok NO_SCHEMA_KINDS stub. NilearnConfig.__post_init__ requires at least one
    # subject/simulation pair.
    resp = client.post(
        "/api/validate/nilearn",
        json={"config": {"subject_simulation_pairs": []}},
        headers=BEARER,
    )
    body = resp.json()
    assert body["ok"] is False
    assert "pair" in body["errors"][0]["message"]


def test_validate_nilearn_ok_for_a_good_config(client: TestClient) -> None:
    resp = client.post(
        "/api/validate/nilearn",
        json={
            "config": {
                "subject_simulation_pairs": [
                    {"subject_id": "001", "simulation_name": "M1"}
                ]
            }
        },
        headers=BEARER,
    )
    assert resp.json() == {"ok": True, "errors": []}


def test_validate_nifti_average_ok_for_a_good_config(client: TestClient) -> None:
    resp = client.post(
        "/api/validate/nifti_average",
        json={
            "config": {
                "output_name": "avg1",
                "subjects": [
                    {
                        "subject_id": "001",
                        "simulation_name": "M1",
                        "group": "Group1",
                    },
                    {
                        "subject_id": "002",
                        "simulation_name": "M1",
                        "group": "Group2",
                    },
                ],
            }
        },
        headers=BEARER,
    )
    assert resp.json() == {"ok": True, "errors": []}


def test_validate_ambiguous_kind_bad_type_reports_error(client: TestClient) -> None:
    resp = client.post(
        "/api/validate/stats",
        json={"config": {"_type": "NotAThing"}},
        headers=BEARER,
    )
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"][0]["path"] == "_type"


def test_validate_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/validate/sim", json={"config": _sim_config()})
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# plan: sim
# --------------------------------------------------------------------------


def test_plan_sim_resolves_montage_output_dir(
    client: TestClient, project: Path
) -> None:
    resp = client.post("/api/plan/sim", json={"config": _sim_config()}, headers=BEARER)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["jobs"]) == 1
    job = body["jobs"][0]
    assert job["kind"] == "sim"
    assert job["subject"] == "001"
    assert job["output_dir"].endswith(os.path.join("Simulations", "M1"))
    assert job["exists"] is False
    assert job["will_overwrite"] is False
    assert body["resolved"]["montages"][0]["name"] == "M1"


def test_plan_sim_flags_existing_nonempty_output(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    sim_dir = pm.simulation("001", "M1")
    os.makedirs(sim_dir)
    (Path(sim_dir) / "marker.txt").write_text("x")

    resp = client.post("/api/plan/sim", json={"config": _sim_config()}, headers=BEARER)
    job = resp.json()["jobs"][0]
    assert job["exists"] is True
    assert job["will_overwrite"] is True


def test_plan_sim_empty_output_dir_is_not_flagged_as_existing(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    os.makedirs(pm.simulation("001", "M1"))  # dir exists but is empty

    resp = client.post("/api/plan/sim", json={"config": _sim_config()}, headers=BEARER)
    job = resp.json()["jobs"][0]
    assert job["exists"] is False


def test_plan_sim_batches_shared_montage_across_subject_ids(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/sim",
        json={"config": _sim_config(), "subject_ids": ["001", "002"]},
        headers=BEARER,
    )
    jobs = resp.json()["jobs"]
    assert {j["subject"] for j in jobs} == {"001", "002"}
    assert len(jobs) == 2


def test_plan_sim_resolves_freehand_montage_source(
    client: TestClient, project: Path
) -> None:
    pm = get_path_manager()
    stim_dir = os.path.join(pm.m2m("001"), "stim_configs")
    os.makedirs(stim_dir)
    import json as _json

    with open(os.path.join(stim_dir, "hand1.json"), "w") as f:
        _json.dump(
            {
                "name": "hand1",
                "electrode_positions": {
                    "E1+": [1, 1, 1],
                    "E1-": [2, 2, 2],
                    "E2+": [3, 3, 3],
                    "E2-": [4, 4, 4],
                },
            },
            f,
        )

    config = _sim_config(montages=[])
    config["montage_sources"] = {"freehand": ["hand1"]}
    resp = client.post("/api/plan/sim", json={"config": config}, headers=BEARER)
    body = resp.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["subject"] == "001"
    assert body["resolved"]["montages"][0]["name"] == "hand1"


def test_plan_sim_resolves_freehand_montage_source_via_top_level_field(
    client: TestClient, project: Path
) -> None:
    # contracts/openapi.v1.yaml's MontageSources is a top-level PlanRequest field, keyed
    # "subject"/"name" (not the pre-contract config["montage_sources"] convention above,
    # which used "subject_id"). Both must resolve to the same montage.
    pm = get_path_manager()
    stim_dir = os.path.join(pm.m2m("001"), "stim_configs")
    os.makedirs(stim_dir)
    import json as _json

    with open(os.path.join(stim_dir, "hand1.json"), "w") as f:
        _json.dump(
            {
                "name": "hand1",
                "electrode_positions": {
                    "E1+": [1, 1, 1],
                    "E1-": [2, 2, 2],
                    "E2+": [3, 3, 3],
                    "E2-": [4, 4, 4],
                },
            },
            f,
        )

    config = _sim_config(montages=[])
    resp = client.post(
        "/api/plan/sim",
        json={
            "config": config,
            "montage_sources": {"freehand": [{"subject": "001", "name": "hand1"}]},
        },
        headers=BEARER,
    )
    body = resp.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["subject"] == "001"
    assert body["resolved"]["montages"][0]["name"] == "hand1"


def test_plan_sim_top_level_montage_sources_wins_over_config_key(
    client: TestClient, project: Path
) -> None:
    # When both the new top-level field and the old config["montage_sources"] convention
    # are present, the top-level field wins outright (no merge of the two).
    pm = get_path_manager()
    stim_dir = os.path.join(pm.m2m("001"), "stim_configs")
    os.makedirs(stim_dir)
    import json as _json

    for name in ("hand1", "hand2"):
        with open(os.path.join(stim_dir, f"{name}.json"), "w") as f:
            _json.dump(
                {
                    "name": name,
                    "electrode_positions": {
                        "E1+": [1, 1, 1],
                        "E1-": [2, 2, 2],
                        "E2+": [3, 3, 3],
                        "E2-": [4, 4, 4],
                    },
                },
                f,
            )

    config = _sim_config(montages=[])
    config["montage_sources"] = {"freehand": ["hand2"]}
    resp = client.post(
        "/api/plan/sim",
        json={
            "config": config,
            "montage_sources": {"freehand": [{"subject": "001", "name": "hand1"}]},
        },
        headers=BEARER,
    )
    body = resp.json()
    names = {m["name"] for m in body["resolved"]["montages"]}
    assert names == {"hand1"}


# --------------------------------------------------------------------------
# plan: pre
# --------------------------------------------------------------------------


def _pre_config(**overrides) -> dict:
    data = {
        "subject_ids": ["placeholder"],
        "convert_dicom": True,
        "create_m2m": True,
        "run_fastsurfer": True,
        "run_tissue_analysis": True,
        "run_qsiprep": True,
        "run_qsirecon": True,
        "extract_dti": True,
    }
    data.update(overrides)
    return data


def test_plan_pre_builds_full_dag_for_two_subjects(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/pre",
        json={"config": _pre_config(), "subject_ids": ["001", "002"]},
        headers=BEARER,
    )
    assert resp.status_code == 200
    body = resp.json()

    by_subject: dict[str, dict[str, str]] = {}
    for stage in body["resolved"]["stages"]:
        by_subject.setdefault(stage["subject"], {})[
            stage["label"].split(":")[1]
        ] = stage

    for sid in ("001", "002"):
        stages = by_subject[sid]
        assert set(stages) == {"G1", "G2a", "G2b", "G3", "G4", "G5", "G6", "report"}
        assert stages["G1"]["after"] == []
        assert stages["G2a"]["after"] == [f"{sid}:G1"]
        assert stages["G2b"]["after"] == [f"{sid}:G1"]
        assert stages["G3"]["after"] == [f"{sid}:G2a"]
        assert stages["G4"]["after"] == [f"{sid}:G1"]
        assert stages["G5"]["after"] == [f"{sid}:G4"]
        assert set(stages["G6"]["after"]) == {f"{sid}:G5", f"{sid}:G2a"}
        assert set(stages["report"]["after"]) == {
            f"{sid}:G1",
            f"{sid}:G2a",
            f"{sid}:G2b",
            f"{sid}:G3",
            f"{sid}:G4",
            f"{sid}:G5",
            f"{sid}:G6",
        }

    # top-level subject_ids overrides config.subject_ids (the config's own list is a
    # required-non-empty placeholder here, not what gets planned)
    assert {j["subject"] for j in body["jobs"]} == {"001", "002"}


def test_plan_pre_g2b_output_dir_is_fastsurfer_not_freesurfer(
    client: TestClient, project: Path
) -> None:
    from tit.paths import get_path_manager

    resp = client.post(
        "/api/plan/pre",
        json={"config": _pre_config(), "subject_ids": ["001"]},
        headers=BEARER,
    )
    body = resp.json()
    pm = get_path_manager(str(project))

    stages = body["resolved"]["stages"]
    jobs = body["jobs"]
    assert len(stages) == len(jobs)
    g2b_index = next(i for i, s in enumerate(stages) if "G2b" in s["tags"])
    assert jobs[g2b_index]["output_dir"] == pm.fastsurfer_subject("001")
    assert jobs[g2b_index]["output_dir"] != pm.freesurfer_subject("001")


def test_plan_pre_accepts_legacy_run_recon_key(
    client: TestClient, project: Path
) -> None:
    # A client that still sends the pre-FastSurfer `run_recon` flag (instead of the current
    # `run_fastsurfer`) still gets a G2b stage planned -- migrate_legacy_keys() runs before
    # the config dict is deserialized.
    config = _pre_config()
    del config["run_fastsurfer"]
    config["run_recon"] = True
    resp = client.post(
        "/api/plan/pre",
        json={"config": config, "subject_ids": ["001"]},
        headers=BEARER,
    )
    assert resp.status_code == 200
    stages = resp.json()["resolved"]["stages"]
    labels = {s["label"].split(":")[1] for s in stages}
    assert "G2b" in labels


def test_plan_pre_legacy_run_recon_key_surfaces_a_response_warning(
    client: TestClient, project: Path
) -> None:
    # FX3 item 4 / qa-neuro-researcher-notes.md #5: migrate_legacy_keys previously only
    # logged server-side, so a caller still on the pre-v3 JSON shape had no way to see its
    # config was silently translated from the HTTP response alone.
    config = _pre_config()
    del config["run_fastsurfer"]
    config["run_recon"] = True
    resp = client.post(
        "/api/plan/pre",
        json={"config": config, "subject_ids": ["001"]},
        headers=BEARER,
    )
    assert resp.status_code == 200
    warnings = resp.json()["warnings"]
    assert any("run_recon" in w and "run_fastsurfer" in w for w in warnings)


def test_plan_pre_only_plans_requested_stages(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/pre",
        json={
            "config": _pre_config(
                create_m2m=False,
                run_fastsurfer=False,
                run_tissue_analysis=False,
                run_qsiprep=False,
                run_qsirecon=False,
                extract_dti=False,
            ),
            "subject_ids": ["001"],
        },
        headers=BEARER,
    )
    stages = resp.json()["resolved"]["stages"]
    labels = {s["label"].split(":")[1] for s in stages}
    assert labels == {"G1", "report"}


def test_plan_pre_falls_back_to_config_subject_ids_when_none_given(
    client: TestClient, project: Path
) -> None:
    # No top-level subject_ids in the request -> falls back to config.subject_ids
    # (PreprocessConfig itself never allows an empty subject_ids, so the "nothing to
    # plan" warning in _plan_pre is unreachable in practice; this documents the fallback).
    resp = client.post(
        "/api/plan/pre",
        json={"config": {"subject_ids": ["001"], "convert_dicom": True}},
        headers=BEARER,
    )
    body = resp.json()
    assert {j["subject"] for j in body["jobs"]} == {"001"}


def test_plan_pre_default_parallel_subjects_is_one(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/pre",
        json={"config": _pre_config(), "subject_ids": ["001", "002"]},
        headers=BEARER,
    )
    body = resp.json()
    assert body["resolved"]["parallel_subjects"] == 1


def test_plan_pre_honours_parallel_subjects_in_summary_and_cost(
    client: TestClient, project: Path
) -> None:
    serial = client.post(
        "/api/plan/pre",
        json={
            "config": _pre_config(),
            "subject_ids": ["001", "002"],
            "parallel_subjects": 1,
        },
        headers=BEARER,
    ).json()
    parallel = client.post(
        "/api/plan/pre",
        json={
            "config": _pre_config(),
            "subject_ids": ["001", "002"],
            "parallel_subjects": 2,
        },
        headers=BEARER,
    ).json()

    assert serial["resolved"]["parallel_subjects"] == 1
    assert parallel["resolved"]["parallel_subjects"] == 2
    # Same DAG either way -- parallel_subjects changes concurrency, not the plan's jobs.
    assert len(serial["jobs"]) == len(parallel["jobs"])
    assert parallel["cost"]["cpus"] == pytest.approx(2 * serial["cost"]["cpus"])
    assert parallel["cost"]["mem_gb"] == pytest.approx(2 * serial["cost"]["mem_gb"])


def test_plan_pre_clamps_parallel_subjects_to_subject_count(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/pre",
        json={
            "config": _pre_config(),
            "subject_ids": ["001"],
            "parallel_subjects": 5,
        },
        headers=BEARER,
    )
    body = resp.json()
    assert body["resolved"]["parallel_subjects"] == 1
    assert body["warnings"]


# --------------------------------------------------------------------------
# plan: ex (search-space counts)
# --------------------------------------------------------------------------


def _ex_config(**overrides) -> dict:
    data = {
        "subject_id": "001",
        "leadfield_hdf": "001_leadfield_GSN-HydroCel-185.hdf5",
        "roi_name": "target.csv",
        "electrodes": {
            "_type": "PoolElectrodes",
            "electrodes": ["E1", "E2", "E3", "E4"],
        },
        "total_current": 2.0,
        "current_step": 1.0,
    }
    data.update(overrides)
    return data


def test_plan_ex_reports_exact_search_space_count(
    client: TestClient, project: Path
) -> None:
    resp = client.post("/api/plan/ex", json={"config": _ex_config()}, headers=BEARER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["jobs"][0]["kind"] == "ex"
    assert body["jobs"][0]["subject"] == "001"
    # Pool of 4 electrodes, all_combinations=True: 4*3*2*1 = 24 electrode arrangements.
    # current_step=1.0, total_current=2.0 -> channel_limit defaults to 1.0, one ratio (1.0, 1.0).
    n = body["resolved"]["search_space"]["n_combinations"]
    n_ratios = body["resolved"]["search_space"]["n_current_ratios"]
    assert n == 24 * n_ratios
    assert n_ratios >= 1


def test_plan_ex_bucket_mode_count(client: TestClient, project: Path) -> None:
    config = _ex_config(
        electrodes={
            "_type": "BucketElectrodes",
            "e1_plus": ["E1"],
            "e1_minus": ["E2"],
            "e2_plus": ["E3"],
            "e2_minus": ["E4"],
        }
    )
    resp = client.post("/api/plan/ex", json={"config": config}, headers=BEARER)
    body = resp.json()
    assert (
        body["resolved"]["search_space"]["n_combinations"]
        == 1 * body["resolved"]["search_space"]["n_current_ratios"]
    )


# --------------------------------------------------------------------------
# plan: analyzer (group mode)
# --------------------------------------------------------------------------


def test_plan_analyzer_group_mode_plans_every_config_subject_id(
    client: TestClient, project: Path
) -> None:
    # No top-level subject_ids in the request -> _plan_analyzer falls back to
    # config.subject_ids for mode="group" (not config.subject_id, which is null here).
    resp = client.post(
        "/api/plan/analyzer",
        json={"config": _analyzer_group_config()},
        headers=BEARER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert {j["subject"] for j in body["jobs"]} == {"001", "002"}
    for job in body["jobs"]:
        assert job["kind"] == "analyzer"
        assert job["exists"] is False


# --------------------------------------------------------------------------
# plan: leadfield / unknown kind
# --------------------------------------------------------------------------


def test_plan_unknown_kind_404(client: TestClient) -> None:
    resp = client.post("/api/plan/bogus", json={"config": {}}, headers=BEARER)
    assert resp.status_code == 404


def test_plan_leadfield_reports_nonexistent_output(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/leadfield",
        json={"config": {"subject_id": "001", "eeg_net": "GSN-HydroCel-185"}},
        headers=BEARER,
    )
    assert resp.status_code == 200
    job = resp.json()["jobs"][0]
    assert job["subject"] == "001"
    assert job["exists"] is False


def test_plan_nifti_average_bad_config_is_422(client: TestClient) -> None:
    # NiftiAverageConfig is a real dataclass now; an empty config fails its own
    # __post_init__ (output_name required) the same way any other kind's bad config would.
    resp = client.post("/api/plan/nifti_average", json={"config": {}}, headers=BEARER)
    assert resp.status_code == 422


def test_plan_nifti_average_resolves_output_dir(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/nifti_average",
        json={
            "config": {
                "output_name": "avg1",
                "subjects": [
                    {"subject_id": "001", "simulation_name": "M1", "group": "G1"},
                    {"subject_id": "002", "simulation_name": "M1", "group": "G2"},
                ],
            }
        },
        headers=BEARER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["jobs"]) == 1
    job = body["jobs"][0]
    assert job["kind"] == "nifti_average"
    assert job["subject"] == ""
    assert job["output_dir"].endswith(
        os.path.join("derivatives", "ti-toolbox", "nifti_average", "avg1")
    )
    assert job["exists"] is False


def test_plan_nilearn_resolves_output_dir(client: TestClient, project: Path) -> None:
    resp = client.post(
        "/api/plan/nilearn",
        json={
            "config": {
                "subject_simulation_pairs": [
                    {"subject_id": "001", "simulation_name": "M1"}
                ],
                "subdir_name": "viz1",
            }
        },
        headers=BEARER,
    )
    assert resp.status_code == 200
    job = resp.json()["jobs"][0]
    assert job["kind"] == "nilearn"
    assert job["subject"] == ""
    assert job["output_dir"].endswith(
        os.path.join("derivatives", "ti-toolbox", "nilearn_visuals", "viz1")
    )


def test_plan_bad_config_is_422(client: TestClient) -> None:
    resp = client.post(
        "/api/plan/sim",
        json={"config": _sim_config(conductivity="bogus")},
        headers=BEARER,
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# plan: PlanCost.eta_minutes (tit.jobs.eta)
# --------------------------------------------------------------------------


def _write_cap(project: Path, sid: str, net: str, n: int) -> None:
    from tit.paths import get_path_manager

    positions = Path(get_path_manager().eeg_positions(sid))
    positions.mkdir(parents=True, exist_ok=True)
    (positions / f"{net}.csv").write_text(
        "\n".join(f"Electrode,0,0,0,E{i}" for i in range(n)) + "\n"
    )


def test_plan_cost_reports_the_machine_it_estimated_for(client: TestClient) -> None:
    resp = client.post(
        "/api/plan/sim", json={"config": _sim_config()}, headers=BEARER
    )
    cost = resp.json()["cost"]
    assert cost["eta_minutes"] > 0
    assert cost["system"]["cpus"] >= 1
    assert isinstance(cost["system"]["emulated"], bool)
    assert cost["system"]["factor"] > 0


def test_plan_leadfield_eta_scales_with_the_caps_electrode_count(
    client: TestClient, project: Path
) -> None:
    """The number the Generate button shows: a 19-electrode cap is not a 256-electrode cap."""
    _write_cap(project, "001", "tiny-net", 19)
    _write_cap(project, "001", "huge-net", 256)

    def eta(net: str) -> float:
        resp = client.post(
            "/api/plan/leadfield",
            json={"config": {"subject_id": "001", "eeg_net": net}},
            headers=BEARER,
        )
        assert resp.status_code == 200
        return resp.json()["cost"]["eta_minutes"]

    assert eta("huge-net") > 5 * eta("tiny-net")


def test_plan_leadfield_eta_is_null_when_the_cap_is_unknown(
    client: TestClient, project: Path
) -> None:
    resp = client.post(
        "/api/plan/leadfield",
        json={"config": {"subject_id": "001", "eeg_net": "no-such-net"}},
        headers=BEARER,
    )
    assert resp.json()["cost"]["eta_minutes"] is None


def test_plan_sim_eta_grows_with_the_batch(client: TestClient, project: Path) -> None:
    one = client.post("/api/plan/sim", json={"config": _sim_config()}, headers=BEARER)
    two = client.post(
        "/api/plan/sim",
        json={"config": _sim_config(), "subject_ids": ["001", "002"]},
        headers=BEARER,
    )
    assert two.json()["cost"]["eta_minutes"] > one.json()["cost"]["eta_minutes"]
