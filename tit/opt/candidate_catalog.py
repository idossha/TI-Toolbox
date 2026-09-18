"""Bounded, project-confined reads of optimization candidate records."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

from tit.paths import resolve_within

_FIELDS = {
    "roi_mean": "roi_mean",
    "roi_p99_9": "roi_p99_9",
    "background_mean": "non_roi_mean",
    "background_p95": "non_roi_p95",
    "contrast": "target_background_ratio",
}
_MAX_BYTES = 128 * 1024 * 1024
_MAX_ROWS = 250_000


def _termination(manifest: dict) -> dict:
    value = manifest.get("optimizer_termination")
    if value is None:
        return {}
    if not isinstance(value, dict) or value.get("accepted_stage") not in {
        "global",
        "local",
    }:
        raise ValueError("Invalid optimizer termination metadata.")
    cleaned = {"accepted_stage": value["accepted_stage"]}
    for stage in ("global", "local"):
        status = value.get(stage)
        if status is None and stage == "local" and value["accepted_stage"] != "local":
            continue
        if (
            not isinstance(status, dict)
            or not isinstance(status.get("success"), bool)
            or not isinstance(status.get("message"), str)
        ):
            raise ValueError("Invalid optimizer termination status.")
        for field in ("iterations", "evaluations"):
            count = status.get(field)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("Invalid optimizer termination counts.")
        cleaned[stage] = {
            key: status[key]
            for key in ("success", "message", "iterations", "evaluations")
        }
    return {"optimizer_termination": cleaned}


def _safe(root: Path, path: Path) -> Path:
    try:
        resolved = Path(resolve_within(str(root), str(path)))
    except ValueError as exc:
        raise ValueError("Candidate reference escapes the project.") from exc
    if resolved.is_file() and resolved.stat().st_size > _MAX_BYTES:
        raise ValueError("Candidate file exceeds the supported size.")
    return resolved


def _json(root: Path, path: Path) -> dict:
    with _file(root, path).open() as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Invalid candidate metadata.")
    return value


def _file(root: Path, path: Path) -> Path:
    resolved = _safe(root, path)
    if not resolved.is_file():
        if resolved.exists():
            raise ValueError("Candidate record must be a regular file.")
        raise FileNotFoundError("Candidate record is missing or incomplete.")
    return resolved


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def run_directory(pm, subject: str, kind: str, run: str) -> Path:
    from tit.catalog import subject_ids

    if (
        subject not in subject_ids(pm)
        or not run
        or Path(run).name != run
        or run in {".", ".."}
        or "\\" in run
    ):
        raise ValueError("Unknown subject or invalid optimization run.")
    getter = {
        "flex": pm.flex_search_run,
        "ex": pm.ex_search_run,
        "mex": pm.m_ex_search_run,
    }.get(kind)
    if getter is None:
        raise ValueError("Unknown optimization kind.")
    directory = _safe(Path(pm.project_dir), Path(getter(subject, run)))
    if not directory.is_dir():
        raise FileNotFoundError("Optimization run not found.")
    return directory


def _flex_rows(root: Path, directory: Path) -> list[dict]:
    rows = []
    seen = set()
    scanned = 0
    for path in sorted(directory.rglob("candidates.csv")):
        _safe(root, path)
        manifest = _json(root, path.with_name("candidate_manifest.json"))
        if manifest.get("schema_version") != 1:
            raise ValueError("Unsupported candidate history version.")
        with _file(root, path).open(newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"candidate_id", "objective"}.issubset(reader.fieldnames or []):
                raise ValueError("Candidate CSV is missing its required columns.")
            for row in reader:
                scanned += 1
                if scanned > _MAX_ROWS:
                    raise ValueError(
                        "Candidate history is too large for interactive review; use its CSV."
                    )
                candidate_id = row["candidate_id"]
                if not candidate_id:
                    raise ValueError("Candidate CSV contains an empty identity.")
                if candidate_id in seen:
                    continue  # Promoted winner is also present in restart history.
                seen.add(candidate_id)
                objective = _number(row.get("objective"))
                if objective is None:
                    continue
                rows.append(
                    {
                        "id": candidate_id,
                        "objective": objective,
                        "objective_label": manifest.get("objective", "Objective"),
                        "objective_direction": "minimize",
                        "metrics": {
                            key: _number(row.get(field))
                            for key, field in _FIELDS.items()
                        },
                        "metric_labels": {
                            key: manifest.get("metric_definitions", {}).get(field, key)
                            for key, field in _FIELDS.items()
                        },
                        "comparison_key": manifest.get(
                            "comparability_key", str(path.parent)
                        ),
                        "currents_mA": [
                            _number(row.get(f"current_ch{i}_mA")) for i in (1, 2)
                        ],
                        "_directory": path.parent,
                        "_manifest": manifest,
                        **_termination(manifest),
                    }
                )
                if len(rows) > _MAX_ROWS:
                    raise ValueError(
                        "Candidate history is too large for interactive review; use its CSV."
                    )
    return rows


def _ex_rows(root: Path, directory: Path, kind: str) -> list[dict]:
    from tit.catalog import _net_from_leadfield_hdf
    from tit.opt.ex.results import parse_montage_string

    config = _json(root, directory / "run_config.json")
    rows = []
    leadfield = config.get("leadfield_hdf")
    if not isinstance(leadfield, str) or not leadfield.strip():
        raise ValueError("Saved results do not identify their leadfield EEG net.")
    with _file(root, directory / "final_output.csv").open(newline="") as stream:
        for index, row in enumerate(csv.DictReader(stream)):
            if index >= _MAX_ROWS:
                raise ValueError(
                    "Results are too large for interactive review; use the CSV."
                )
            labels = parse_montage_string(row["Montage"])
            if len(labels) != (4 if kind == "ex" else 8):
                raise ValueError(
                    "Saved montage pair count does not match the optimization kind."
                )
            if _number(row.get("Composite_Index")) is None:
                raise ValueError(
                    "Saved montage has an invalid or incomplete objective."
                )
            rows.append(
                {
                    "id": f"ex-{index}",
                    "objective": _number(row.get("Composite_Index")),
                    "objective_label": "Composite index",
                    "objective_direction": "maximize",
                    "metrics": {
                        "roi_mean": _number(row.get("TImean_ROI")),
                        "roi_p99_9": None,
                        "background_mean": _number(row.get("TImean_GM")),
                        "background_p95": None,
                        "contrast": _number(row.get("Focality")),
                    },
                    "metric_labels": {
                        "roi_mean": "ROI mean (V/m, volume weighted)",
                        "background_mean": "Whole GM mean (V/m, includes ROI)",
                        "contrast": "ROI / whole-GM mean",
                    },
                    "comparison_key": str(directory),
                    "pairs": [labels[i : i + 2] for i in range(0, len(labels), 2)],
                    "eeg_net": _net_from_leadfield_hdf(leadfield),
                    "currents_mA": [
                        _number(
                            row.get(f"Current_Ch{i+1}_mA", config.get("current_mA"))
                        )
                        for i in range(len(labels) // 2)
                    ],
                    "_manifest": {"config": config},
                    "replay_note": "Simulator defaults for electrode geometry; Ex history records leadfield estimates, not a full-electrode model.",
                }
            )
            if len(rows) > _MAX_ROWS:
                raise ValueError(
                    "Results are too large for interactive review; use the CSV."
                )
    return rows


def _geometries(root: Path, rows: list[dict]) -> dict[str, dict]:
    """Read each requested history once, including a partially written last line."""
    grouped: dict[Path, set[str]] = {}
    for row in rows:
        if "_directory" in row:
            grouped.setdefault(row["_directory"], set()).add(row["id"])
    records = {}
    for directory, wanted in grouped.items():
        path = _file(root, directory / "candidate_geometry.jsonl")
        with path.open() as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and record.get("candidate_id") in wanted:
                    _validate_geometry(record)
                    records[record["candidate_id"]] = record
                    wanted.remove(record["candidate_id"])
                    if not wanted:
                        break
        if wanted:
            raise ValueError("Candidate geometry is missing or incomplete.")
    for row in rows:
        if row["id"] not in records:
            continue
        record = records[row["id"]]
        if _number(record.get("objective")) != row["objective"]:
            raise ValueError("Candidate score does not match its geometry record.")
        currents = [
            sum(max(0.0, float(cell["current_A"])) for cell in channel) * 1000.0
            for channel in record["electrodes"]
        ]
        if any(
            recorded is None
            or not math.isclose(actual, recorded, rel_tol=1e-9, abs_tol=1e-9)
            for actual, recorded in zip(currents, row["currents_mA"])
        ):
            raise ValueError("Candidate currents do not match its geometry record.")
    return records


def _validate_geometry(record: dict) -> None:
    """Reject incomplete geometry before preview indexes or replay consumes it."""
    from tit.sim.config import Montage

    channels = record.get("electrodes")
    if not isinstance(channels, list) or len(channels) != 2:
        raise ValueError("Candidate geometry requires exactly two carriers.")
    poses = []
    for channel in channels:
        if not isinstance(channel, list) or len(channel) != 2:
            raise ValueError("Candidate geometry requires two electrodes per carrier.")
        for cell in channel:
            if not isinstance(cell, dict) or _number(cell.get("current_A")) is None:
                raise ValueError("Candidate geometry has an invalid electrode current.")
            if cell.get("shape") not in {"rect", "ellipse"}:
                raise ValueError("Candidate electrode shape is unsupported.")
            for field in ("dimensions", "thickness"):
                values = cell.get(field)
                if (
                    not isinstance(values, list)
                    or len(values) != 2
                    or any(
                        _number(value) is None or float(value) <= 0 for value in values
                    )
                ):
                    raise ValueError(
                        f"Candidate electrode {field} must contain two positive finite values."
                    )
            pose = cell.get("posmat")
            if (
                not isinstance(pose, list)
                or len(pose) != 4
                or any(not isinstance(row, list) or len(row) != 4 for row in pose)
            ):
                raise ValueError(
                    "Candidate electrode pose must be a complete 4x4 matrix."
                )
            poses.append(pose)
    positions = [[pose[i][3] for i in range(3)] for pose in poses]
    Montage(
        "validation",
        Montage.Mode.FLEX_FREE,
        [positions[:2], positions[2:]],
        electrode_poses=poses,
    )


def _rows(root: Path, directory: Path, subject: str, kind: str) -> list[dict]:
    try:
        rows = (
            _flex_rows(root, directory)
            if kind == "flex"
            else _ex_rows(root, directory, kind)
        )
    except csv.Error as error:
        raise ValueError(
            "Candidate CSV is malformed or exceeds field limits."
        ) from error
    for row in rows:
        config = row["_manifest"].get("config", {})
        if not isinstance(config, dict):
            raise ValueError("Candidate configuration is invalid.")
        if config.get("subject_id", subject) != subject:
            raise ValueError("Candidate metadata does not match the selected subject.")
    return rows


def _public(row: dict, geometry: dict | None = None) -> dict:
    result = {key: value for key, value in row.items() if not key.startswith("_")}
    if geometry is not None:
        result["positions"] = [
            [cell["posmat"][i][3] for i in range(3)]
            for channel in geometry["electrodes"]
            for cell in channel
        ]
    return result


def list_candidates(
    pm,
    subject: str,
    kind: str,
    run: str,
    offset: int = 0,
    limit: int = 100,
    sort: str = "roi_mean",
    descending: bool = True,
) -> dict:
    """Return a deterministic page, with unavailable metrics sorted last."""
    root = Path(pm.project_dir)
    directory = run_directory(pm, subject, kind, run)
    rows = _rows(root, directory, subject, kind)
    if sort not in {*_FIELDS, "objective"}:
        raise ValueError("Unknown sort metric.")

    def key(row):
        value = (
            row.get("objective") if sort == "objective" else row["metrics"].get(sort)
        )
        return (
            value is None,
            (-value if descending else value) if value is not None else 0,
            row["id"],
        )

    if offset < 0 or not 1 <= limit <= 500:
        raise ValueError("Invalid candidate page.")
    rows.sort(key=key)
    page = rows[offset : offset + limit]
    geometries = _geometries(root, page)
    return {
        "candidates": [_public(row, geometries.get(row["id"])) for row in page],
        "total": len(rows),
        "legacy": kind == "flex"
        and not any(directory.rglob("candidate_manifest.json"))
        and not any(directory.rglob("candidates.csv")),
    }


def candidate_detail(pm, subject: str, kind: str, run: str, candidate_id: str) -> dict:
    """Resolve a saved candidate into the standard editable simulation config."""
    from tit.config_io import serialize_config
    from tit.sim.config import Montage, SimulationConfig

    root = Path(pm.project_dir)
    directory = run_directory(pm, subject, kind, run)
    rows = _rows(root, directory, subject, kind)
    row = next((r for r in rows if r["id"] == candidate_id), None)
    if row is None:
        raise FileNotFoundError("Candidate not found.")
    name = (
        "candidate_"
        + hashlib.sha256(f"{kind}/{run}/{candidate_id}".encode()).hexdigest()[:16]
    )
    provenance = {
        "kind": kind,
        "run": run,
        "candidate_id": candidate_id,
        "metrics": "optimization estimates",
    }
    config = row["_manifest"].get("config", {})
    geometry = None
    if kind == "flex":
        identity = row["_manifest"].get("head_mesh_identity")
        if identity is None:
            row["replay_note"] = (
                "Head mesh identity was not recorded; unchanged mesh physics cannot be verified for this history."
            )
            provenance["head_mesh_identity"] = "unavailable in legacy history"
        else:
            from tit.mesh_identity import verify_subject_mesh

            if not isinstance(identity, dict) or not isinstance(
                identity.get("path"), str
            ):
                raise ValueError("Candidate head mesh identity is malformed.")
            verify_subject_mesh(pm, subject, identity.get("sha256"))
            provenance["head_mesh_sha256"] = identity["sha256"]
            provenance["head_mesh_source_path"] = identity["path"]
        geometry = _geometries(root, [row])[candidate_id]
        electrodes = []
        currents = []
        for channel in geometry["electrodes"]:
            if len(channel) != 2:
                raise ValueError(
                    "Simulation replay currently requires two electrodes per carrier."
                )
            ordered = sorted(channel, key=lambda e: -e["current_A"])
            positive, negative = (float(e["current_A"]) for e in ordered)
            if not (
                math.isfinite(positive)
                and math.isfinite(negative)
                and positive > 0 > negative
                and abs(positive + negative) < 1e-10
            ):
                raise ValueError(
                    "Candidate carrier currents are invalid or unbalanced."
                )
            currents.append(positive * 1000)
            electrodes.extend(ordered)
        if len(currents) != 2:
            raise ValueError("Flex replay requires exactly two carriers.")
        spec = electrodes[0]
        if any(
            any(cell[key] != spec[key] for key in ("shape", "dimensions", "thickness"))
            for cell in electrodes
        ):
            raise ValueError(
                "Mixed electrode geometries cannot be replayed in the standard Simulator."
            )
        poses = [cell["posmat"] for cell in electrodes]
        positions = [[pose[i][3] for i in range(3)] for pose in poses]
        montage = Montage(
            name,
            Montage.Mode.FLEX_FREE,
            [positions[i : i + 2] for i in range(0, len(positions), 2)],
            electrode_poses=poses,
            provenance=provenance,
        )
        simulation = SimulationConfig(
            subject,
            [montage],
            conductivity=config.get("anisotropy_type", "scalar"),
            intensities=currents,
            electrode_shape=spec["shape"],
            electrode_dimensions=spec["dimensions"],
            gel_thickness=spec["thickness"][0],
            rubber_thickness=spec["thickness"][1],
            aniso_maxratio=config.get("aniso_maxratio", 10),
            aniso_maxcond=config.get("aniso_maxcond", 2),
        )
    else:
        if not all(value is not None and value > 0 for value in row["currents_mA"]):
            raise ValueError("Saved montage does not contain usable carrier currents.")
        montage = Montage(
            name,
            Montage.Mode.NET,
            row["pairs"],
            eeg_net=row["eeg_net"],
            provenance=provenance,
        )
        provenance["geometry"] = "Simulator defaults; not recorded in Ex history"
        simulation = SimulationConfig(
            subject, [montage], intensities=row["currents_mA"]
        )
    return {
        "candidate": _public(row, geometry),
        "simulation_config": serialize_config(simulation),
    }


def candidate_mapping(
    pm, subject: str, run: str, candidate_id: str, eeg_net: str
) -> dict:
    """Map this candidate to distinct cap sites without changing recorded history.

    Distances are Euclidean millimetres, not scalp geodesics. Uses the same
    assignment as ordinary Flex-result mapping, with candidate-specific poses.
    """
    import numpy as np

    from tit.tools.map_electrodes import map_electrodes_to_net, read_csv_positions

    if not eeg_net or Path(eeg_net).name != eeg_net or "\\" in eeg_net:
        raise ValueError("EEG net must be a filename.")
    detail = candidate_detail(pm, subject, "flex", run, candidate_id)
    pairs = detail["simulation_config"]["montages"][0]["electrode_pairs"]
    positions = np.asarray([point for pair in pairs for point in pair], dtype=float)
    root = Path(pm.project_dir)
    net_path = _file(root, Path(pm.eeg_positions(subject)) / eeg_net)
    net_positions, labels = read_csv_positions(str(net_path))
    if (
        net_positions.shape != (len(labels), 3)
        or len(labels) < len(positions)
        or len(set(labels)) != len(labels)
        or not np.isfinite(net_positions).all()
    ):
        raise ValueError("EEG net needs enough distinct, finite electrode sites.")
    indices = [[i // 2, i % 2] for i in range(len(positions))]
    mapped = map_electrodes_to_net(positions, net_positions, labels, indices)
    mapped_labels = mapped["mapped_labels"]
    if len(mapped_labels) != len(positions):
        raise ValueError("Could not assign every candidate electrode to the cap.")
    return {
        "eeg_net": eeg_net,
        "pairs": [mapped_labels[i : i + 2] for i in range(0, len(mapped_labels), 2)],
        "optimized_positions": mapped["optimized_positions"],
        "mapped_positions": mapped["mapped_positions"],
        "distances": [float(distance) for distance in mapped["distances"]],
    }
