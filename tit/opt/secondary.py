"""Helpers for secondary-search optimization workflows."""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass

from simnibs import mesh_io

from tit import constants as const
from tit.paths import get_path_manager

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
    mesh_paths: list[str]
    base_mesh: object
    e_fields: list


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
