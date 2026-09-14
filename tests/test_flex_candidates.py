"""2026-09-13: stream exact trials and reject penalty winners.

Run: python3 -m pytest tests/test_flex_candidates.py -q. Ground truth is
an authored asymmetric pose/current fixture, read independently with csv/json;
real TI-envelope and replay-library checks live in tests/numerical.
"""

import csv
import json
from types import SimpleNamespace

import numpy as np
import pytest

from tit.opt.flex.candidates import CandidateRecorder, install_candidate_recorder

CONFIG = {
    "goal": "mean",
    "postproc": "max_TI",
    "subject_id": "fixture",
    "electrode": {"shape": "rect", "dimensions": [8.0, 12.0], "gel_thickness": 3.0},
}


def _opt(tmp_path):
    pose = np.eye(4)
    pose[:3, 3] = [1.2345678901234567, -5.8, 9.1]
    channels = []
    for channel in range(2):
        cells = [
            SimpleNamespace(posmat=pose.copy(), ele_current=current)
            for current in (0.002, -0.002)
        ]
        channels.append(
            SimpleNamespace(_electrode_arrays=[SimpleNamespace(electrodes=cells)])
        )
    opt = SimpleNamespace(
        output_folder=str(tmp_path),
        electrode=channels,
        electrode_pos=[[[0.1, 0.2, 0.3]]],
        goal="mean",
    )
    opt.update_field = lambda **kwargs: [[np.ones((4, 3))], [np.ones((4, 3))]]
    opt.compute_goal = lambda fields: -float(np.mean(fields[0][0]))

    def goal(parameters):
        if opt.update_field() is None:
            return 2.0
        return opt.compute_goal([[np.array([1.0, 2.0, 3.0])]])

    opt.goal_fun = goal
    return opt


def test_stream_preserves_pose_currents_and_rejects_unseen_penalty_winner(tmp_path):
    opt = _opt(tmp_path)
    recorder = CandidateRecorder(opt, CONFIG)
    recorder.fields_valid = True
    opt._candidate_postprocessed = [[np.array([1.0, 2.0, 3.0])]]
    parameters = np.array([0.12345678901234567, -0.66])
    opt._candidate_current_scale = (1.5, 0.5)
    recorder.record(parameters, -2.0)
    records = [
        json.loads(line)
        for line in (tmp_path / "candidate_geometry.jsonl").read_text().splitlines()
    ]
    assert len(records) == 1
    assert records[0]["parameters"] == parameters.tolist()
    assert records[0]["electrodes"][0][0]["posmat"][0][3] == 1.2345678901234567
    assert records[0]["current_split_mA"] == [3.0, 1.0]
    assert records[0]["electrodes"][1][1]["current_A"] == -0.001
    with (tmp_path / "candidates.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1 and rows[0]["non_roi_mean"] == ""
    assert rows[0]["candidate_id"] == records[0]["candidate_id"]

    # Equal objective alone is insufficient: an unevaluated pose cannot replay.
    opt.optim_parameters, opt.optim_funvalue = parameters + 1.0, -2.0
    assert not recorder.finalize(opt)
    opt.optim_parameters = parameters
    assert recorder.finalize(opt)
    assert recorder.finalize(opt)
    assert opt._accepted_candidate_id == rows[0]["candidate_id"]
    recorder.fields_valid = False
    recorder.record(parameters + 1.0, 2.0)
    opt.optim_parameters, opt.optim_funvalue = parameters + 1.0, 2.0
    assert not recorder.finalize(opt)
    assert json.loads((tmp_path / "candidate_manifest.json").read_text())[
        "rejected_counts"
    ] == {"rejected_placement_or_field": 1}


def test_wrapper_returns_unchanged_score_and_releases_fields(tmp_path, monkeypatch):
    import tit.config_io

    monkeypatch.setattr(tit.config_io, "serialize_config", lambda config: CONFIG)
    opt = _opt(tmp_path)
    recorder = install_candidate_recorder(opt, CONFIG)
    assert opt.goal_fun(np.array([0.1])) == -2.0
    assert opt._candidate_postprocessed is None
    assert recorder.valid == 1
    original = opt.update_field
    opt.update_field = lambda **kwargs: None
    assert opt.goal_fun(np.array([0.2])) == 2.0
    assert recorder.valid == 1
    opt.update_field = original


@pytest.mark.parametrize(
    "fields,objective,reason",
    [
        ([[np.array([np.nan])]], -1.0, "empty_or_nonfinite_target"),
        ([[np.array([1.0])]], float("nan"), "nonfinite_objective"),
        ([[np.array([])]], 1000.0, "empty_or_nonfinite_target"),
    ],
)
def test_nonfinite_and_empty_trials_never_enter_csv(
    tmp_path, fields, objective, reason
):
    opt = _opt(tmp_path)
    recorder = CandidateRecorder(opt, CONFIG)
    recorder.fields_valid = True
    opt._candidate_postprocessed = fields
    recorder.record([1.0], objective)
    with (tmp_path / "candidates.csv").open() as stream:
        assert list(csv.DictReader(stream)) == []
    assert recorder.rejected[reason] == 1


def test_observation_nan_does_not_reject_valid_intensity(tmp_path):
    opt = _opt(tmp_path)
    recorder = CandidateRecorder(opt, CONFIG)
    recorder.fields_valid = True
    opt._candidate_postprocessed = [[np.array([1.0, 2.0]), np.array([np.nan])]]
    recorder.record([1.0], -1.5)
    assert recorder.valid == 1


def test_background_complement_preserves_mean_objective_without_weights():
    from tit.opt.config import FlexConfig
    from tit.opt.flex.utils import configure_roi

    config = FlexConfig(
        subject_id="fixture",
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=1.0, y=2.0, z=3.0, radius=10.0),
        observe_background=True,
    )
    regions = []

    def add_roi():
        roi = SimpleNamespace()
        regions.append(roi)
        return roi

    opt = SimpleNamespace(add_roi=add_roi, goal="mean")
    configure_roi(opt, config)
    assert len(regions) == 2
    assert regions[1].roi_sphere_operator == ["difference"]
    assert config.goal == "mean"
    assert opt._observation_only_non_roi
    for background in (np.array([1e9]), np.array([np.nan]), np.array([])):
        assert opt.goal[0]([[np.array([1.0, 2.0, 3.0]), background]]) == -2.0


@pytest.mark.parametrize(
    "target,background",
    [
        ([1.0], [0.0]),
        ([1.0], [1e-13]),
        ([1.0], [-1.0]),
        ([-0.1, 1.0], [0.2]),
        ([1.0], [np.inf]),
        ([0.0], [0.2]),
    ],
)
def test_degenerate_focality_is_not_a_usable_candidate(tmp_path, target, background):
    from tit.opt.flex.objectives import threshold_free_focality

    opt = _opt(tmp_path)
    recorder = CandidateRecorder(opt, {**CONFIG, "goal": "focality_tf"})
    recorder.fields_valid = True
    opt._candidate_postprocessed = [[np.array(target), np.array(background)]]
    value = threshold_free_focality(np.array(target), np.array(background))
    assert value == 0.0
    recorder.record([1.0], -value)
    assert recorder.valid == 0


def test_reflected_simnibs_rectangle_keeps_footprint_and_y_direction(tmp_path):
    opt = _opt(tmp_path)
    source = np.array(
        [
            [0.0, -1.0, 0.0, 11.0],
            [-1.0, 0.0, 0.0, 23.0],
            [0.0, 0.0, 1.0, 37.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    for pair in opt.electrode:
        for array in pair._electrode_arrays:
            for electrode in array.electrodes:
                electrode.posmat = source.copy()
    recorder = CandidateRecorder(opt, CONFIG)
    recorder.fields_valid = True
    opt._candidate_postprocessed = [[np.ones(4)]]
    recorder.record([1.0], -1.0)
    record = json.loads((tmp_path / "candidate_geometry.jsonl").read_text())
    electrode = record["electrodes"][0][0]
    canonical = np.asarray(electrode["posmat"])
    assert np.linalg.det(canonical[:3, :3]) == 1.0
    assert electrode["source_posmat"] == source.tolist()
    assert electrode["source_pose_convention"] == "simnibs_reflected_x"
    np.testing.assert_array_equal(canonical[:3, 1:], source[:3, 1:])
    # Independent geometric oracle: all four rectangle corners are unchanged
    # as a set, even though local x has the opposite sign.
    corners = np.array([[x, y, 0.0, 1.0] for x in (-4.0, 4.0) for y in (-6.0, 6.0)])
    before = {tuple(point) for point in (source @ corners.T).T}
    after = {tuple(point) for point in (canonical @ corners.T).T}
    assert before == after
    assert all(
        np.array_equal(e.posmat, source)
        for p in opt.electrode
        for a in p._electrode_arrays
        for e in a.electrodes
    )


@pytest.mark.parametrize("weight", [-0.1, 1.1, float("nan"), float("inf")])
def test_threshold_free_weight_must_be_valid(weight):
    from tit.opt.flex.objectives import threshold_free_focality

    with pytest.raises(ValueError, match="intensity_weight"):
        threshold_free_focality(np.ones(3), np.ones(3), weight)


def test_head_mesh_is_hashed_once_and_manifest_keeps_original_identity(
    tmp_path, monkeypatch
):
    import hashlib
    from tit import mesh_identity

    mesh = tmp_path / "fixture.msh"
    original_bytes = b"authored head mesh bytes"
    mesh.write_bytes(original_bytes)
    opt = _opt(tmp_path / "history")
    opt._mesh = SimpleNamespace(fn=str(mesh))
    original = mesh_identity.sha256_file
    calls = []

    def observed(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(mesh_identity, "sha256_file", observed)
    recorder = CandidateRecorder(opt, CONFIG)
    recorder._start()
    mesh.write_bytes(b"changed after the first recording")
    recorder._start()
    recorder.close()
    manifest = json.loads(
        (tmp_path / "history" / "candidate_manifest.json").read_text()
    )
    assert manifest["head_mesh_identity"] == {
        "path": str(mesh.resolve()),
        "sha256": hashlib.sha256(original_bytes).hexdigest(),
    }
    assert calls == [mesh.resolve()]


def test_manifest_records_effective_solver_overrides_and_finite_safe_bounds(tmp_path):
    opt = _opt(tmp_path)
    opt.seed = np.int64(42)
    opt.optimizer = "differential_evolution"
    opt.polish = False
    opt._optimizer_options_std = {
        "maxiter": 1,
        "popsize": 5,
        "bounds": SimpleNamespace(lb=np.array([-np.inf, -1]), ub=np.array([np.inf, 1])),
        "mutation": np.array([0.01, 0.5]),
    }
    recorder = CandidateRecorder(opt, {**CONFIG, "max_iterations": None})
    recorder._start()
    opt._optimizer_options_std["maxiter"] = 999
    recorder.close()
    text = (tmp_path / "candidate_manifest.json").read_text()
    manifest = json.loads(
        text, parse_constant=lambda value: (_ for _ in ()).throw(AssertionError(value))
    )
    settings = manifest["effective_solver_settings"]
    assert settings["seed"] == 42
    assert settings["optimizer"] == "differential_evolution"
    assert settings["polish"] is False
    assert settings["options"]["maxiter"] == 1
    assert settings["options"]["bounds"] == {
        "lower": [{"nonfinite": "-inf"}, -1.0],
        "upper": [{"nonfinite": "inf"}, 1.0],
    }
    assert manifest["config"]["max_iterations"] is None


def test_corrected_focality_manifest_versions_mean_denominator(tmp_path):
    recorder = CandidateRecorder(_opt(tmp_path), CONFIG)
    recorder._start()
    manifest = json.loads((tmp_path / "candidate_manifest.json").read_text())
    assert (
        manifest["definitions"]["focality_definition"]
        == "roi_mean_power_1_plus_w_over_non_roi_mean_v2"
    )
    assert (
        "roi_mean / non_roi_mean;"
        in manifest["metric_definitions"]["target_background_ratio"]
    )
