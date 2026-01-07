#!/usr/bin/env simnibs_python
"""
Montage publication asset builder.

This module owns the Blender/montage-publication business logic. The CLI wrapper lives in `tit/cli/vis_blender.py`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from tit.core import get_path_manager
from tit.core import constants as const
from tit.blender import utils as be_utils

logger = logging.getLogger(__name__)


def _find_tetrahedral_mesh(sim_dir: str) -> str:
    candidates: List[str] = []

    ti_mesh_dir = os.path.join(sim_dir, "TI", "mesh")
    if os.path.isdir(ti_mesh_dir):
        for f in os.listdir(ti_mesh_dir):
            if f.endswith("_TI_final.msh") or f.endswith("_T1.msh"):
                candidates.append(os.path.join(ti_mesh_dir, f))

    hf_mesh_dir = os.path.join(sim_dir, "high_Frequency", "mesh")
    if os.path.isdir(hf_mesh_dir):
        for f in os.listdir(hf_mesh_dir):
            if f.endswith(".msh"):
                candidates.append(os.path.join(hf_mesh_dir, f))

    if not candidates:
        raise FileNotFoundError(f"No tetrahedral mesh found under {sim_dir}")
    return sorted(candidates)[0]


def _find_central_surface_mesh(sim_dir: str, subject_id: str, simulation_name: str) -> str:
    pm = get_path_manager()
    expected = pm.path_optional("ti_central_surface", subject_id=subject_id, simulation_name=simulation_name)
    if expected and os.path.exists(expected):
        return expected

    for d in (os.path.join(sim_dir, "TI", "mesh", "surfaces"), os.path.join(sim_dir, "TI", "mesh")):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith("_TI_central.msh"):
                return os.path.join(d, f)

    raise FileNotFoundError(f"Central surface mesh not found under {sim_dir}")


def export_scalp_stl_from_sim(sim_dir: str, *, output_stl: str, skin_tag: int = 1005) -> str:
    tetra_mesh = _find_tetrahedral_mesh(sim_dir)
    vertices, faces = be_utils.extract_scalp_from_msh(tetra_mesh, skin_tag=skin_tag)
    os.makedirs(os.path.dirname(output_stl), exist_ok=True)
    be_utils.write_binary_stl(vertices, faces, output_stl, "TI-Toolbox Scalp Mesh")
    return output_stl


def export_gm_stl_from_sim(sim_dir: str, *, subject_id: str, simulation_name: str, output_stl: str) -> str:
    import numpy as np
    import simnibs

    central_mesh_path = _find_central_surface_mesh(sim_dir, subject_id, simulation_name)
    mesh = simnibs.read_msh(central_mesh_path)

    triangular = mesh.elm.elm_type == 2
    triangle_nodes = mesh.elm.node_number_list[triangular][:, :3]
    if len(triangle_nodes) == 0:
        raise ValueError("No triangular surface elements found in central surface mesh")

    unique_nodes = np.unique(triangle_nodes.flatten())
    node_to_idx = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}

    vertices = mesh.nodes.node_coord[unique_nodes - 1]
    faces = np.array([[node_to_idx[n] for n in tri] for tri in triangle_nodes])

    os.makedirs(os.path.dirname(output_stl), exist_ok=True)
    be_utils.write_binary_stl(vertices, faces, output_stl, "TI-Toolbox GM Surface Mesh")
    return output_stl


def _resolve_eeg_net_csv(*, subject_id: str, eeg_net_name: str) -> str:
    pm = get_path_manager()
    eeg_dir = pm.path_optional("eeg_positions", subject_id=subject_id)
    if not eeg_dir:
        raise FileNotFoundError(f"EEG positions directory not found for subject {subject_id}")
    path = os.path.join(eeg_dir, eeg_net_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"EEG net CSV not found: {path}")
    return path


@dataclass(frozen=True)
class MontagePublicationResult:
    scalp_stl: str
    gm_stl: str
    electrodes_blend: str
    final_blend: str


def build_montage_publication_blend(
    *,
    subject_id: str,
    simulation_name: str,
    output_dir: Optional[str] = None,
    show_full_net: bool = True,
    electrode_diameter_mm: float = 10.0,
    electrode_height_mm: float = 6.0,
) -> MontagePublicationResult:
    import bpy

    pm = get_path_manager()
    sim_dir = pm.path_optional("simulation", subject_id=subject_id, simulation_name=simulation_name)
    if not sim_dir:
        raise FileNotFoundError(f"Simulation directory not found for {subject_id}/{simulation_name}")

    cfg = be_utils.load_simulation_config(subject_id, simulation_name)
    if not cfg:
        raise FileNotFoundError(
            f"Simulation config.json not found for {subject_id}/{simulation_name} (expected under documentation/config.json)."
        )

    if output_dir is None:
        if not pm.project_dir:
            raise RuntimeError("Project directory is not set (PathManager.project_dir is None).")
        output_dir = os.path.join(
            pm.project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            "visual_exports",
            f"{const.PREFIX_SUBJECT}{subject_id}",
            "montage_publication",
        )
    os.makedirs(output_dir, exist_ok=True)

    scalp_stl = os.path.join(output_dir, "scalp.stl")
    gm_stl = os.path.join(output_dir, "gm.stl")

    export_scalp_stl_from_sim(sim_dir, output_stl=scalp_stl)
    export_gm_stl_from_sim(sim_dir, subject_id=subject_id, simulation_name=simulation_name, output_stl=gm_stl)

    eeg_net = cfg.get("eeg_net")
    if not eeg_net:
        raise KeyError("config.json missing required field: 'eeg_net'")
    electrode_pairs = cfg.get("electrode_pairs") or []

    eeg_csv = _resolve_eeg_net_csv(subject_id=subject_id, eeg_net_name=str(eeg_net))
    electrode_template = os.path.abspath(os.path.join(os.path.dirname(__file__), "Electrode.blend"))

    subject_m2m = pm.path_optional("m2m", subject_id=subject_id)
    if not subject_m2m or not os.path.isdir(subject_m2m):
        raise FileNotFoundError(f"m2m directory not found for subject {subject_id}")
    subject_msh = os.path.join(subject_m2m, f"{subject_id}.msh")

    from tit.blender.electrode_placement import ElectrodePlacer, ElectrodePlacementConfig

    ele_cfg = ElectrodePlacementConfig(
        subject_id=subject_id,
        electrode_csv_path=eeg_csv,
        electrode_blend_path=electrode_template,
        output_dir=output_dir,
        subject_msh_path=subject_msh if os.path.exists(subject_msh) else None,
        scalp_stl_path=scalp_stl,
        electrode_diameter_mm=electrode_diameter_mm,
        electrode_height_mm=electrode_height_mm,
        electrode_size=None,
        montage_pairs=[tuple(p) for p in electrode_pairs if isinstance(p, (list, tuple)) and len(p) >= 2],
        export_glb=False,
        show_full_net=show_full_net,
    )

    placer = ElectrodePlacer(ele_cfg, logger=logging.getLogger("tit.blender.electrode_placement"))
    ok, msg = placer.place_electrodes()
    if not ok:
        raise RuntimeError(msg)
    electrodes_blend = ele_cfg.output_blend_path

    # Compose final scene on the current scene produced by ElectrodePlacer
    from tit.blender import scene_setup

    scalp_obj = bpy.data.objects.get("Scalp")
    head_coll = scene_setup.ensure_collection("Head")
    gm_obj = scene_setup.import_stl(gm_stl, name="GM", collection=head_coll)
    scene_setup.move_object_to_collection(scalp_obj, collection=head_coll, unlink_from_others=True)
    scene_setup.move_object_to_collection(gm_obj, collection=head_coll, unlink_from_others=True)

    scene_setup.ensure_world_nodes(bg_color=(0.12, 0.12, 0.12, 1.0), strength=1.2)
    scene_setup.configure_render_eevee(resolution=(2048, 2048), transparent_film=True)
    scene_setup.configure_color_management_agx(exposure=0.9, look="Medium High Contrast")
    scene_setup.configure_eevee_publication_quality()

    final_blend = os.path.join(output_dir, f"{subject_id}_{simulation_name}_montage_publication.blend")
    bpy.ops.wm.save_as_mainfile(filepath=final_blend)

    return MontagePublicationResult(
        scalp_stl=scalp_stl,
        gm_stl=gm_stl,
        electrodes_blend=electrodes_blend,
        final_blend=final_blend,
    )


