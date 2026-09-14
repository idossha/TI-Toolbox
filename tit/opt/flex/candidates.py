"""Stream replayable Flex trials without retaining electric-field histories.

The optimizer remains the sole owner of scoring. Observations consume its
postprocessed fields and never perform a solve or participate in selection.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import types
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

_COLUMNS = (
    "candidate_id",
    "evaluation",
    "objective",
    "roi_mean",
    "roi_p99_9",
    "non_roi_mean",
    "non_roi_p95",
    "target_background_ratio",
    "current_ch1_mA",
    "current_ch2_mA",
    "geometry_file",
)


def summarize_fields(fields: list) -> dict[str, float | None]:
    """Summarize samples without volume weighting; missing background is null.

    TI has one effective channel. Other postprocessors average the separate
    channel summaries, matching the optimizer's channel aggregation.
    """
    summaries = []
    for channel in fields:
        roi = np.asarray(channel[0], dtype=float)
        if roi.size == 0 or not np.isfinite(roi).all():
            raise ValueError("empty_or_nonfinite_target")
        row = {
            "roi_mean": float(np.mean(roi)),
            "roi_p99_9": float(np.percentile(roi, 99.9)),
        }
        non = np.asarray(channel[1], dtype=float) if len(channel) > 1 else np.empty(0)
        if non.size and np.isfinite(non).all():
            mean, p95 = float(np.mean(non)), float(np.percentile(non, 95))
            row.update(
                non_roi_mean=mean,
                non_roi_p95=p95,
                target_background_ratio=row["roi_mean"] / mean if mean > 0 else None,
            )
        else:
            row.update(
                non_roi_mean=None, non_roi_p95=None, target_background_ratio=None
            )
        summaries.append(row)
    if not summaries:
        raise ValueError("missing_postprocessed_fields")
    return {
        key: (
            float(np.mean([r[key] for r in summaries]))
            if all(r[key] is not None for r in summaries)
            else None
        )
        for key in summaries[0]
    }


def _plain(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _solver_setting(value: Any) -> Any:
    """Normalize small effective solver settings without unsafe JSON numbers."""
    value = _plain(value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"nonfinite": str(value)}
    if isinstance(value, list):
        return [_solver_setting(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _solver_setting(item) for key, item in value.items()}
    if hasattr(value, "lb") and hasattr(value, "ub"):
        return {"lower": _solver_setting(value.lb), "upper": _solver_setting(value.ub)}
    return {"unavailable_type": type(value).__name__}


def _geometry(opt: Any, config: dict) -> tuple[list, list[float]]:
    channels = []
    currents = []
    scales = getattr(opt, "_candidate_current_scale", None) or (1.0, 1.0)
    for channel_index, pair in enumerate(opt.electrode):
        cells = []
        for array_index, array in enumerate(pair._electrode_arrays):
            for index, electrode in enumerate(array.electrodes):
                pose = np.asarray(electrode.posmat, dtype=float)
                current = float(np.sum(electrode.ele_current)) * scales[channel_index]
                if (
                    pose.shape != (4, 4)
                    or not np.isfinite(pose).all()
                    or not math.isfinite(current)
                ):
                    raise ValueError("invalid_electrode_geometry")
                # SimNIBS rectangles use x=cross(z,y), a reflected basis.
                # Canonical replay changes only x; y, normal, centre and the
                # symmetric rectangular footprint remain exactly the same.
                source_pose = pose.copy()
                basis = pose[:3, :3]
                if not np.allclose(
                    pose[3], [0.0, 0.0, 0.0, 1.0], atol=1e-6, rtol=0
                ) or not np.allclose(basis.T @ basis, np.eye(3), atol=1e-6, rtol=0):
                    raise ValueError("nonorthogonal_electrode_geometry")
                reflected = np.linalg.det(basis) < 0
                if reflected:
                    pose = pose.copy()
                    pose[:3, 0] = np.cross(pose[:3, 1], pose[:3, 2])
                spec = config["electrode"]
                cells.append(
                    {
                        "channel": channel_index,
                        "array": array_index,
                        "index": index,
                        "posmat": pose.tolist(),
                        "source_posmat": source_pose.tolist(),
                        "source_pose_convention": (
                            "simnibs_reflected_x" if reflected else "right_handed"
                        ),
                        "shape": spec["shape"],
                        "dimensions": spec["dimensions"],
                        "thickness": [spec.get("gel_thickness", 4.0), 2.0],
                        "current_A": current,
                    }
                )
        if not cells:
            raise ValueError("missing_electrode_geometry")
        channels.append(cells)
        currents.append(sum(max(0.0, cell["current_A"]) for cell in cells) * 1000.0)
    if len(channels) != 2:
        raise ValueError("expected_two_channels")
    return channels, currents


class CandidateRecorder:
    """Write valid evaluated trials and count rejected trials separately."""

    def __init__(self, opt: Any, config: dict) -> None:
        self.opt = opt
        self.config = config
        self.run_id = uuid4().hex
        self.evaluations = 0
        self.valid = 0
        self.rejected: Counter = Counter()
        self.directory: Path | None = None
        self.accepted_id: str | None = None
        self.active = False
        self.fields_valid = False
        self.recording_state = "open"
        self.head_mesh_identity: dict | None = None
        self.solver_settings: dict = {}

    def _start(self) -> None:
        if self.directory is not None:
            return
        from tit.mesh_identity import sha256_file

        self.solver_settings = {
            key: _solver_setting(getattr(self.opt, key, None))
            for key in ("seed", "optimizer", "polish")
        }
        self.solver_settings["options"] = _solver_setting(
            getattr(self.opt, "_optimizer_options_std", {})
        )
        source = getattr(getattr(self.opt, "_mesh", None), "fn", None)
        if isinstance(source, (str, Path)) and source:
            path = Path(source).resolve()
            self.head_mesh_identity = {"path": str(path), "sha256": sha256_file(path)}
        self.directory = Path(self.opt.output_folder)
        self.directory.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects prior runs from accidental reuse.
        with (self.directory / "candidates.csv").open("x", newline="") as stream:
            csv.DictWriter(stream, fieldnames=_COLUMNS).writeheader()
        (self.directory / "candidate_geometry.jsonl").touch(exist_ok=False)
        self._manifest()

    def _manifest(self) -> None:
        if self.directory is None:
            return
        definition = {
            key: self.config.get(key)
            for key in (
                "project_dir",
                "subject_id",
                "goal",
                "intensity_weight",
                "thresholds",
                "anisotropy_type",
                "roi",
                "non_roi",
                "non_roi_method",
                "postproc",
                "observe_background",
            )
        }
        definition["weighting"] = "unweighted_sample_mean"
        # Separates new arithmetic-mean focality from prior p95 histories.
        definition["focality_definition"] = (
            "roi_mean_power_1_plus_w_over_non_roi_mean_v2"
        )
        definition["ratio_definition"] = "roi_mean_over_non_roi_mean_v2"
        definition["head_mesh_sha256"] = (
            self.head_mesh_identity["sha256"] if self.head_mesh_identity else None
        )
        definition["background_domain"] = (
            "target_tissue_complement"
            if self.config.get("observe_background")
            and self.config["goal"] in ("mean", "max")
            else self.config.get("non_roi_method")
        )
        manifest = {
            "schema_version": 1,
            "run_id": self.run_id,
            "config": self.config,
            "objective": self.config["goal"],
            "objective_direction": "minimize",
            "definitions": definition,
            "metric_definitions": {
                "roi_mean": "unweighted mean of target samples, V/m",
                "roi_p99_9": "target sample percentile 99.9, V/m",
                "non_roi_mean": "unweighted mean of background samples, V/m",
                "non_roi_p95": "background sample percentile 95, V/m",
                "target_background_ratio": "roi_mean / non_roi_mean; null for missing or nonpositive denominator; not Ex focality",
            },
            "comparability_key": hashlib.sha256(
                json.dumps(definition, sort_keys=True).encode()
            ).hexdigest(),
            "evaluations": self.evaluations,
            "valid_candidates": self.valid,
            "rejected_counts": dict(self.rejected),
            "accepted_candidate_id": self.accepted_id,
            "recording_state": self.recording_state,
            "optimizer_termination": getattr(self.opt, "optimizer_termination", None),
            "geometry_file": "candidate_geometry.jsonl",
            "head_mesh_identity": self.head_mesh_identity,
            "effective_solver_settings": self.solver_settings,
        }
        destination = self.directory / "candidate_manifest.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        temporary.replace(destination)

    def record(self, parameters: Any, objective: float) -> None:
        """Append a valid sample; invalid samples affect counts only."""
        self._start()
        self.evaluations += 1
        try:
            if not self.fields_valid:
                raise ValueError("rejected_placement_or_field")
            if not math.isfinite(objective):
                raise ValueError("nonfinite_objective")
            parameter_array = np.asarray(parameters, dtype=float)
            if not np.isfinite(parameter_array).all():
                raise ValueError("nonfinite_parameters")
            fields = getattr(self.opt, "_candidate_postprocessed", None)
            if fields is None:
                raise ValueError("missing_postprocessed_fields")
            metrics = summarize_fields(fields)
            if (
                self.config["goal"] in ("focality", "focality_tf")
                and metrics["non_roi_mean"] is None
            ):
                raise ValueError("empty_or_nonfinite_background")
            if self.config["goal"] == "focality_tf":
                from tit.opt.flex.objectives import threshold_free_focality

                if objective >= 0 or any(
                    threshold_free_focality(
                        channel[0], channel[1], self.config.get("intensity_weight", 0.0)
                    )
                    <= 0
                    for channel in fields
                ):
                    raise ValueError("degenerate_threshold_free_focality")
            geometry, currents = _geometry(self.opt, self.config)
        except ValueError as error:
            self.rejected[str(error)] += 1
            self._manifest()
            return
        candidate_id = f"{self.run_id}:{self.evaluations}"
        row = {
            "candidate_id": candidate_id,
            "evaluation": self.evaluations,
            "objective": objective,
            **metrics,
            "current_ch1_mA": currents[0],
            "current_ch2_mA": currents[1],
            "geometry_file": "candidate_geometry.jsonl",
        }
        record = {
            "candidate_id": candidate_id,
            "parameters": parameter_array.tolist(),
            "objective": objective,
            "electrode_pos": _plain(self.opt.electrode_pos),
            "electrodes": geometry,
            "current_split_mA": currents,
            "coordinate_space": "subject",
            "coordinate_units": "mm",
        }
        assert self.directory is not None
        # Geometry first: a visible CSV row always has replay information.
        with (self.directory / "candidate_geometry.jsonl").open("a") as stream:
            stream.write(json.dumps(record, allow_nan=False) + "\n")
        with (self.directory / "candidates.csv").open("a", newline="") as stream:
            csv.DictWriter(stream, fieldnames=_COLUMNS).writerow(row)
        self.valid += 1
        self._manifest()

    def finalize(self, opt: Any) -> bool:
        """Validate the accepted exact parameter vector against a valid trial."""
        self._start()
        self.accepted_id = None
        opt._accepted_candidate_valid = False
        opt._accepted_candidate_id = None
        parameters = getattr(opt, "optim_parameters", None)
        objective = getattr(opt, "optim_funvalue", None)
        if (
            parameters is not None
            and objective is not None
            and math.isfinite(float(objective))
        ):
            assert self.directory is not None
            with (self.directory / "candidate_geometry.jsonl").open() as stream:
                for line in stream:
                    candidate = json.loads(line)
                    if candidate["objective"] == float(objective) and np.array_equal(
                        candidate["parameters"], parameters
                    ):
                        self.accepted_id = candidate["candidate_id"]
                        opt._accepted_candidate_id = self.accepted_id
                        opt._accepted_candidate_valid = True
                        opt._accepted_current_split_mA = tuple(
                            candidate["current_split_mA"]
                        )
                        if getattr(opt, "_best_current_split", None) is not None:
                            opt._best_current_split = opt._accepted_current_split_mA
                        break
        self._manifest()
        return opt._accepted_candidate_valid

    def close(self) -> None:
        """Flush metadata without inferring optimizer convergence or success."""
        self.recording_state = "closed"
        self._manifest()


def install_candidate_recorder(opt: Any, config: Any) -> CandidateRecorder:
    """Observe the actual scoring path after optional ratio-search installation."""
    from tit.config_io import serialize_config

    recorder = CandidateRecorder(opt, serialize_config(config))
    opt._candidate_recorder = recorder
    original_field = opt.update_field
    original_goal = opt.goal_fun
    original_compute = opt.compute_goal

    def update_field(*args, **kwargs):
        result = original_field(*args, **kwargs)
        if recorder.active:
            recorder.fields_valid = result is not None and all(
                field is not None for channel in result for field in channel
            )
        return result

    def capture_goal(fields):
        opt._candidate_postprocessed = fields
        return original_compute(fields)

    opt.update_field = update_field
    opt.compute_goal = capture_goal
    goals = opt.goal if isinstance(opt.goal, list) else [opt.goal]
    if goals and isinstance(goals[0], types.FunctionType):
        callable_goal = goals[0]

        def capture_callable(fields):
            opt._candidate_postprocessed = fields
            return callable_goal(fields)

        opt.goal = [capture_callable, *goals[1:]]

    def goal_fun(parameters):
        recorder.active = True
        recorder.fields_valid = False
        opt._candidate_postprocessed = None
        opt._candidate_current_scale = None
        opt._candidate_split_mA = None
        try:
            value = original_goal(parameters)
            recorder.record(parameters, float(value))
            return value
        finally:
            recorder.active = False
            opt._candidate_postprocessed = None

    opt.goal_fun = goal_fun
    return recorder
