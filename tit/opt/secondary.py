"""Helpers for secondary-search optimization workflows."""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass

from simnibs import mesh_io

from tit import constants as const
from tit.paths import get_path_manager
from tit.sim.utils import load_montages

_TAGS_KEEP = list(
    range(const.BRAIN_TISSUE_TAG_RANGES[0][0], const.BRAIN_TISSUE_TAG_RANGES[0][1])
) + list(
    range(const.BRAIN_TISSUE_TAG_RANGES[1][0], const.BRAIN_TISSUE_TAG_RANGES[1][1])
)


@dataclass(frozen=True)
class BaseSimulationFields:
    subject_id: str
    simulation_name: str
    hf_mesh_dir: str
    pair_labels: list[str]
    base_electrode_labels: list[str]
    electrode_pairs: list[tuple[str, str]]
    intensities_mA: list[float]
    eeg_net: str | None
    mesh_paths: list[str]
    base_mesh: object
    e_fields: list


@dataclass(frozen=True)
class BaseMontageSpec:
    subject_id: str
    montage_name: str
    eeg_net: str
    electrode_pairs: list[tuple[str, str]]
    base_electrode_labels: list[str]


def load_base_montage(
    subject_id: str,
    montage_name: str,
    eeg_net: str,
    *,
    project_dir: str | None = None,
) -> BaseMontageSpec:
    project_root = project_dir or get_path_manager(project_dir).project_dir
    montages = load_montages(
        [montage_name],
        project_dir=project_root,
        eeg_net=eeg_net,
        include_flex=False,
    )
    if not montages:
        raise FileNotFoundError(
            f"Could not load montage '{montage_name}' for EEG net '{eeg_net}'."
        )
    montage = montages[0]
    electrode_pairs = [tuple(pair) for pair in montage.electrode_pairs]
    if len(electrode_pairs) != 2:
        raise ValueError(
            f"2nd Ex-Search currently requires a unipolar base montage with exactly 2 pairs, got {len(electrode_pairs)}."
        )
    labels = [label for pair in electrode_pairs for label in pair]
    return BaseMontageSpec(
        subject_id=subject_id,
        montage_name=montage_name,
        eeg_net=eeg_net,
        electrode_pairs=electrode_pairs,
        base_electrode_labels=labels,
    )


def load_base_simulation_fields(
    subject_id: str,
    simulation_name: str,
    *,
    project_dir: str | None = None,
) -> BaseSimulationFields:
    """Load cached high-frequency pair fields from an existing simulation."""
    pm = get_path_manager(project_dir)
    sim_dir = pm.simulation(subject_id, simulation_name)
    hf_mesh_dir = os.path.join(sim_dir, "high_Frequency", "mesh")
    if not os.path.isdir(hf_mesh_dir):
        raise FileNotFoundError(f"HF mesh directory not found: {hf_mesh_dir}")

    sim_config = _load_simulation_config(sim_dir)
    base_electrode_labels = _extract_base_electrode_labels(sim_config)
    electrode_pairs = _extract_label_electrode_pairs(sim_config)
    intensities_mA = _extract_intensities_mA(sim_config)
    eeg_net = sim_config.get("eeg_net")

    mesh_paths = [
        path
        for path in glob.glob(os.path.join(hf_mesh_dir, "*_TDCS_*_*.msh"))
        if not path.endswith(".opt") and "_normal" not in path
    ]
    if not mesh_paths:
        raise FileNotFoundError(f"No cached HF mesh files found in {hf_mesh_dir}")

    mesh_info = []
    for path in mesh_paths:
        label = _extract_tdcs_label(os.path.basename(path))
        if label is None:
            continue
        mesh_info.append((label, path))
    if not mesh_info:
        raise FileNotFoundError(
            f"No recognizable HF pair mesh files found in {hf_mesh_dir}"
        )

    mesh_info.sort(key=lambda item: _label_sort_key(item[0]))

    meshes = []
    e_fields = []
    pair_labels = []
    ordered_paths = []
    for label, path in mesh_info:
        mesh = mesh_io.read_msh(path).crop_mesh(tags=_TAGS_KEEP)
        if "E" not in mesh.field:
            raise ValueError(f"HF mesh missing E-field data: {path}")
        meshes.append(mesh)
        e_fields.append(mesh.field["E"].value)
        pair_labels.append(label)
        ordered_paths.append(path)

    return BaseSimulationFields(
        subject_id=subject_id,
        simulation_name=simulation_name,
        hf_mesh_dir=hf_mesh_dir,
        pair_labels=pair_labels,
        base_electrode_labels=base_electrode_labels,
        electrode_pairs=electrode_pairs,
        intensities_mA=intensities_mA,
        eeg_net=eeg_net,
        mesh_paths=ordered_paths,
        base_mesh=meshes[0],
        e_fields=e_fields,
    )


def _extract_tdcs_label(filename: str) -> str | None:
    match = re.search(r"_TDCS_([A-Z]|\d+)_", filename)
    if not match:
        return None
    return match.group(1)


def _label_sort_key(label: str):
    if label.isdigit():
        return (0, int(label))
    return (1, label)


def _load_simulation_config(sim_dir: str) -> dict:
    config_path = os.path.join(sim_dir, "documentation", "config.json")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path) as f:
            return json.load(f)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _extract_base_electrode_labels(data: dict) -> list[str]:
    if data.get("is_xyz_montage"):
        return []
    pairs = data.get("electrode_pairs") or []
    labels: list[str] = []
    for pair in pairs:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            if all(isinstance(x, str) for x in pair):
                labels.extend(pair)
    return labels


def _extract_label_electrode_pairs(data: dict) -> list[tuple[str, str]]:
    if data.get("is_xyz_montage"):
        return []
    pairs = data.get("electrode_pairs") or []
    label_pairs: list[tuple[str, str]] = []
    for pair in pairs:
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and all(
            isinstance(x, str) for x in pair
        ):
            label_pairs.append((pair[0], pair[1]))
    return label_pairs


def _extract_intensities_mA(data: dict) -> list[float]:
    values = (data.get("intensities") or {}).get("values") or []
    try:
        return [float(v) for v in values]
    except (TypeError, ValueError):
        return []
