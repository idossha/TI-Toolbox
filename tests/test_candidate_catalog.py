"""Authored candidate fixtures pin pagination, project confinement and exact replay.

2026-09-13: run pytest tests/test_candidate_catalog.py. The records below are
independent of CandidateRecorder; real FEM accuracy belongs to numerical tests.
"""

import csv
import json
from types import SimpleNamespace

import pytest

from tit.opt import candidate_catalog as catalog


@pytest.fixture
def history(tmp_path, monkeypatch):
    directory = tmp_path / "flex" / "run"
    directory.mkdir(parents=True)
    monkeypatch.setattr("tit.catalog.subject_ids", lambda pm: ["ernie"])
    pm = SimpleNamespace(
        project_dir=str(tmp_path),
        flex_search_run=lambda subject, run: tmp_path / "flex" / run,
        ex_search_run=lambda subject, run: tmp_path / "ex" / run,
        m_ex_search_run=lambda subject, run: tmp_path / "mex" / run,
    )
    manifest = {
        "schema_version": 1,
        "config": {"anisotropy_type": "scalar"},
        "comparability_key": "same",
        "objective": "focality_tf",
    }
    (directory / "candidate_manifest.json").write_text(json.dumps(manifest))
    rows = [
        {
            "candidate_id": name,
            "objective": -score,
            "roi_mean": score,
            "non_roi_p95": "",
            "current_ch1_mA": 1,
            "current_ch2_mA": 2,
        }
        for name, score in [("trial-a", 2), ("trial-b", 4), ("trial-c", 3)]
    ]
    with (directory / "candidates.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    records = []
    for row in rows:
        channels = []
        for carrier in (1, 2):
            cells = []
            for polarity in (1, -1):
                x = carrier * 10 * polarity
                cells.append(
                    {
                        "posmat": [
                            [0, -1, 0, x],
                            [1, 0, 0, 23],
                            [0, 0, 1, 37],
                            [0, 0, 0, 1],
                        ],
                        "current_A": carrier * polarity / 1000,
                        "shape": "rect",
                        "dimensions": [12, 8],
                        "thickness": [5, 2],
                    }
                )
            channels.append(cells)
        records.append(
            {
                "candidate_id": row["candidate_id"],
                "objective": row["objective"],
                "electrodes": channels,
            }
        )
    (directory / "candidate_geometry.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + '\n{"partial":'
    )
    return pm, directory


def test_sort_page_and_missing_metrics(history):
    pm, _ = history
    result = catalog.list_candidates(pm, "ernie", "flex", "run", limit=2)
    assert result["total"] == 3
    assert [row["id"] for row in result["candidates"]] == ["trial-b", "trial-c"]
    assert result["candidates"][0]["positions"] == [
        [10, 23, 37],
        [-10, 23, 37],
        [20, 23, 37],
        [-20, 23, 37],
    ]
    assert result["candidates"][0]["metrics"]["background_p95"] is None
    assert not any(key.startswith("_") for key in result["candidates"][0])
    assert (
        catalog.list_candidates(pm, "ernie", "flex", "run", offset=2)["candidates"][0][
            "id"
        ]
        == "trial-a"
    )


def test_one_geometry_scan_per_page(history, monkeypatch):
    pm, directory = history
    from pathlib import Path

    original = Path.open
    reads = []

    def observed(path, *args, **kwargs):
        if path.name == "candidate_geometry.jsonl":
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed)
    catalog.list_candidates(pm, "ernie", "flex", "run")
    assert reads == [directory / "candidate_geometry.jsonl"]


def test_selected_simulation_preserves_geometry_currents(history):
    pm, _ = history
    detail = catalog.candidate_detail(pm, "ernie", "flex", "run", "trial-b")
    config = detail["simulation_config"]
    assert config["intensities"] == [1, 2]
    assert config["electrode_dimensions"] == [12, 8]
    assert (config["gel_thickness"], config["rubber_thickness"]) == (5, 2)
    montage = config["montages"][0]
    assert montage["electrode_pairs"] == [
        [[10, 23, 37], [-10, 23, 37]],
        [[20, 23, 37], [-20, 23, 37]],
    ]
    assert montage["electrode_poses"][0][:3] == [
        [0, -1, 0, 10],
        [1, 0, 0, 23],
        [0, 0, 1, 37],
    ]
    assert montage["provenance"]["candidate_id"] == "trial-b"


@pytest.mark.parametrize("run", ["..", "../outside", "a/b", "a\\b"])
def test_run_traversal_rejected(history, run):
    pm, _ = history
    with pytest.raises(ValueError):
        catalog.list_candidates(pm, "ernie", "flex", run)


def test_geometry_symlink_escape_rejected(history, tmp_path_factory):
    pm, directory = history
    path = directory / "candidate_geometry.jsonl"
    external = tmp_path_factory.mktemp("outside") / "geometry.jsonl"
    external.write_text(path.read_text())
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(ValueError, match="escapes"):
        catalog.list_candidates(pm, "ernie", "flex", "run")


def test_incomplete_geometry_not_replayable(history):
    pm, directory = history
    (directory / "candidate_geometry.jsonl").write_text('{"partial":')
    with pytest.raises(ValueError, match="incomplete"):
        catalog.candidate_detail(pm, "ernie", "flex", "run", "trial-a")


def _write_ex_fixture(history, kind="ex"):
    from tit.opt.ex.results import build_csv_rows

    pm, _ = history
    from pathlib import Path

    directory = Path(pm.project_dir) / kind / "run"
    directory.mkdir(parents=True)
    labels = ["E1", "E2", "E3", "E4"] + (
        ["E5", "E6", "E7", "E8"] if kind == "mex" else []
    )
    name = "_and_".join("_".join(labels[i : i + 2]) for i in range(0, len(labels), 2))
    data = {
        "target_TImax_ROI": 1.2,
        "target_TImean_ROI": 0.4,
        "target_TImean_GM": 0.2,
        "target_Focality": 2,
        "current_ch1_mA": 1.2,
        "current_ch2_mA": 2.8,
    }
    if kind == "mex":
        data.update(
            current_ch1_mA=2, current_ch2_mA=2, current_ch3_mA=2, current_ch4_mA=2
        )
    rows, *_ = build_csv_rows({f"TI_field_{name}.msh": data}, "target")
    with (directory / "final_output.csv").open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    config = {
        "subject_id": "ernie",
        "leadfield_hdf": "/old/project/ernie_leadfield_GSN-256.hdf5",
    }
    if kind == "mex":
        config["current_mA"] = 2
    (directory / "run_config.json").write_text(json.dumps(config))
    return pm, directory


@pytest.mark.parametrize("kind,expected", [("ex", [1.2, 2.8]), ("mex", [2, 2, 2, 2])])
def test_actual_ex_csv_writer_roundtrips_currents_and_labels(history, kind, expected):
    pm, _ = _write_ex_fixture(history, kind)
    page = catalog.list_candidates(pm, "ernie", kind, "run")
    assert page["candidates"][0]["metrics"]["contrast"] == 2
    assert page["candidates"][0]["metrics"]["background_mean"] == 0.2
    detail = catalog.candidate_detail(pm, "ernie", kind, "run", "ex-0")
    config = detail["simulation_config"]
    assert config["intensities"] == expected
    assert config["montages"][0]["electrode_pairs"][0] == ["E1", "E2"]
    assert config["montages"][0]["eeg_net"] == "GSN-256.csv"
    assert "not recorded" in config["montages"][0]["provenance"]["geometry"]
    assert "Simulator defaults" in detail["candidate"]["replay_note"]


def test_new_zero_candidate_history_is_not_legacy(history):
    pm, directory = history
    (directory / "candidates.csv").write_text("candidate_id,objective\n")
    page = catalog.list_candidates(pm, "ernie", "flex", "run")
    assert page["candidates"] == []
    assert page["legacy"] is False


def test_old_winner_only_run_remains_legacy(history):
    pm, directory = history
    for path in directory.iterdir():
        path.unlink()
    (directory / "electrode_positions.json").write_text('{"optimized_positions": []}')
    assert catalog.list_candidates(pm, "ernie", "flex", "run")["legacy"] is True


@pytest.mark.parametrize(
    "malformation", ["pose", "shape", "dimensions", "thickness", "reflection"]
)
def test_incomplete_geometry_is_a_validation_error(history, malformation):
    pm, directory = history
    path = directory / "candidate_geometry.jsonl"
    records = [
        json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")
    ]
    cell = records[0]["electrodes"][0][0]
    if malformation == "pose":
        cell["posmat"] = [[1]]
    elif malformation == "reflection":
        for row in cell["posmat"][:3]:
            row[0] *= -1
    elif malformation == "shape":
        cell["shape"] = "triangle"
    else:
        cell[malformation] = [0, float("nan")]
    path.write_text("\n".join(json.dumps(record) for record in records))
    with pytest.raises(ValueError):
        catalog.candidate_detail(pm, "ernie", "flex", "run", "trial-a")


def test_metadata_for_another_subject_is_not_replayed(history):
    pm, directory = history
    path = directory / "candidate_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["config"]["subject_id"] = "other"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="subject"):
        catalog.list_candidates(pm, "ernie", "flex", "run")


def test_finite_candidates_retain_nonconverged_termination_status(history):
    pm, directory = history
    path = directory / "candidate_manifest.json"
    manifest = json.loads(path.read_text())
    status = {
        "global": {
            "success": False,
            "message": "Maximum iterations exceeded",
            "iterations": 2,
            "evaluations": 30,
        },
        "accepted_stage": "global",
    }
    manifest["optimizer_termination"] = status
    path.write_text(json.dumps(manifest))
    row = catalog.list_candidates(pm, "ernie", "flex", "run")["candidates"][0]
    assert row["optimizer_termination"] == status


@pytest.mark.parametrize(
    "status", [[], {"accepted_stage": "global"}, {"accepted_stage": "invalid"}]
)
def test_malformed_termination_status_is_rejected(history, status):
    pm, directory = history
    path = directory / "candidate_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["optimizer_termination"] = status
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="termination"):
        catalog.list_candidates(pm, "ernie", "flex", "run")


def test_ex_without_leadfield_does_not_invent_eeg_net(history):
    pm, directory = _write_ex_fixture(history)
    (directory / "run_config.json").write_text("{}")
    with pytest.raises(ValueError, match="EEG net"):
        catalog.candidate_detail(pm, "ernie", "ex", "run", "ex-0")


@pytest.mark.parametrize("field,value", [("objective", 999.0), ("current_A", 0.005)])
def test_csv_and_geometry_must_identify_same_evaluation(history, field, value):
    pm, directory = history
    path = directory / "candidate_geometry.jsonl"
    records = [
        json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")
    ]
    target = records[0] if field == "objective" else records[0]["electrodes"][0][0]
    target[field] = value
    path.write_text("\n".join(json.dumps(record) for record in records))
    with pytest.raises(ValueError, match="does not match|do not match"):
        catalog.candidate_detail(pm, "ernie", "flex", "run", "trial-a")


def test_invalid_ex_objective_is_an_error_not_a_replayable_row(history):
    pm, directory = _write_ex_fixture(history)
    path = directory / "final_output.csv"
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["Composite_Index"] = "nan"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="objective"):
        catalog.list_candidates(pm, "ernie", "ex", "run")


def test_nonregular_geometry_is_rejected_without_opening(history):
    pm, directory = history
    path = directory / "candidate_geometry.jsonl"
    path.unlink()
    path.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        catalog.list_candidates(pm, "ernie", "flex", "run")


def test_oversized_csv_field_returns_validation_error(history):
    pm, directory = history
    (directory / "candidates.csv").write_text(
        "candidate_id,objective\n" + "x" * (csv.field_size_limit() + 1) + ",-1\n"
    )
    with pytest.raises(ValueError, match="field limits"):
        catalog.list_candidates(pm, "ernie", "flex", "run")


def _record_mesh_identity(history):
    import hashlib

    pm, directory = history
    mesh_dir = directory.parent.parent / "m2m_ernie"
    mesh_dir.mkdir()
    mesh = mesh_dir / "ernie.msh"
    mesh.write_bytes(b"authored candidate head mesh")
    pm.m2m = lambda subject: mesh_dir
    path = directory / "candidate_manifest.json"
    manifest = json.loads(path.read_text())
    # Source path is provenance, not an instruction to read outside this project.
    manifest["head_mesh_identity"] = {
        "path": "/old/location/ernie.msh",
        "sha256": hashlib.sha256(mesh.read_bytes()).hexdigest(),
    }
    path.write_text(json.dumps(manifest))
    return pm, mesh


def test_mesh_identity_is_carried_to_execution_and_source_path_is_not_opened(
    history, monkeypatch
):
    from tit.config_io import deserialize_config
    from tit.sim.config import SimulationConfig
    from tit.sim import utils

    pm, mesh = _record_mesh_identity(history)
    detail = catalog.candidate_detail(pm, "ernie", "flex", "run", "trial-a")
    config = deserialize_config(SimulationConfig, detail["simulation_config"])
    assert len(config.montages[0].provenance["head_mesh_sha256"]) == 64
    monkeypatch.setattr(utils, "get_path_manager", lambda: pm)
    utils._validate_simulation_inputs(config)
    mesh.write_bytes(b"modified after the simulation form was opened")
    with pytest.raises(ValueError, match="mesh has changed"):
        utils._validate_simulation_inputs(config)


@pytest.mark.parametrize("change", ["modify", "remove"])
def test_replay_refuses_changed_or_missing_recorded_mesh(history, change):
    pm, mesh = _record_mesh_identity(history)
    if change == "modify":
        mesh.write_bytes(b"different mesh")
    else:
        mesh.unlink()
    with pytest.raises(ValueError, match="mesh has changed|mesh is missing"):
        catalog.candidate_detail(pm, "ernie", "flex", "run", "trial-a")


def test_old_history_without_mesh_identity_has_explicit_replay_note(history):
    pm, _ = history
    detail = catalog.candidate_detail(pm, "ernie", "flex", "run", "trial-a")
    assert "cannot be verified" in detail["candidate"]["replay_note"]
    assert (
        detail["simulation_config"]["montages"][0]["provenance"]["head_mesh_identity"]
        == "unavailable in legacy history"
    )


def test_historical_focality_labels_are_not_reinterpreted(history):
    pm, directory = history
    path = directory / "candidate_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["metric_definitions"] = {
        "target_background_ratio": "roi_mean / non_roi_p95"
    }
    path.write_text(json.dumps(manifest))
    candidate = catalog.list_candidates(pm, "ernie", "flex", "run")["candidates"][0]
    assert candidate["metric_labels"]["contrast"] == "roi_mean / non_roi_p95"
    assert candidate["comparison_key"] == "same"
