#!/usr/bin/env simnibs_python
"""
Montage publication Blender scene builder (STL-only).

Given (subject_id, simulation_name), loads `documentation/config.json`, exports:
- `scalp.stl` (tag 1005 from tetrahedral mesh)
- `gm.stl` (central surface)
Then places electrodes and saves a publication-ready `.blend` using Eevee with
transparent background, a simple studio lighting setup, and standard cameras.

Designed to run under `simnibs_python` where both `simnibs` and `bpy` are available.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)

from tit.core import constants as const
from tit.core import get_path_manager
from tit.blender_exporter.utils import write_binary_stl


def _find_tetrahedral_mesh(sim_dir: str) -> str:
    """Find a tetrahedral mesh for scalp extraction within a simulation directory."""
    candidates: List[str] = []

    # Prefer TI/mesh
    ti_mesh_dir = os.path.join(sim_dir, "TI", "mesh")
    if os.path.isdir(ti_mesh_dir):
        for f in os.listdir(ti_mesh_dir):
            if f.endswith("_TI_final.msh") or f.endswith("_T1.msh"):
                candidates.append(os.path.join(ti_mesh_dir, f))

    # Fallback: high_Frequency/mesh
    hf_mesh_dir = os.path.join(sim_dir, "high_Frequency", "mesh")
    if os.path.isdir(hf_mesh_dir):
        for f in os.listdir(hf_mesh_dir):
            if f.endswith(".msh"):
                candidates.append(os.path.join(hf_mesh_dir, f))

    if not candidates:
        raise FileNotFoundError(f"No tetrahedral mesh found under {sim_dir}")

    # Stable choice: first match
    return sorted(candidates)[0]


def _find_central_surface_mesh(sim_dir: str, subject_id: str, simulation_name: str) -> str:
    """Find the TI central surface mesh (GM surface)."""
    pm = get_path_manager()
    expected = pm.get_ti_central_surface_path(subject_id, simulation_name)
    if expected and os.path.exists(expected):
        return expected

    # Search in TI/mesh and TI/mesh/surfaces (older layouts)
    search_dirs = [
        os.path.join(sim_dir, "TI", "mesh", "surfaces"),
        os.path.join(sim_dir, "TI", "mesh"),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith("_TI_central.msh"):
                return os.path.join(d, f)

    raise FileNotFoundError(f"Central surface mesh not found under {sim_dir}")


def export_scalp_stl_from_sim(sim_dir: str, *, output_stl: str, skin_tag: int = 1005) -> str:
    """Export a scalp STL from the simulation tetrahedral mesh."""
    import numpy as np
    import simnibs

    tetra_mesh = _find_tetrahedral_mesh(sim_dir)
    mesh = simnibs.read_msh(tetra_mesh)

    triangular = mesh.elm.elm_type == 2
    skin_mask = mesh.elm.tag1 == skin_tag
    skin_triangles_mask = triangular & skin_mask

    triangle_nodes = mesh.elm.node_number_list[skin_triangles_mask][:, :3]
    if len(triangle_nodes) == 0:
        raise ValueError(f"No skin triangles found with tag {skin_tag}")

    unique_nodes = np.unique(triangle_nodes.flatten())
    node_to_idx = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}

    vertices = mesh.nodes.node_coord[unique_nodes - 1]
    faces = np.array([[node_to_idx[n] for n in tri] for tri in triangle_nodes])

    os.makedirs(os.path.dirname(output_stl), exist_ok=True)
    write_binary_stl(vertices, faces, output_stl, "TI-Toolbox Scalp Mesh")
    return output_stl


def export_gm_stl_from_sim(sim_dir: str, *, subject_id: str, simulation_name: str, output_stl: str) -> str:
    """Export the (triangulated) GM central surface as STL."""
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
    write_binary_stl(vertices, faces, output_stl, "TI-Toolbox GM Surface Mesh")
    return output_stl


def load_sim_config(sim_dir: str) -> Dict[str, Any]:
    """Load `documentation/config.json` from the simulation directory."""
    config_path = os.path.join(sim_dir, "documentation", "config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r") as f:
        return json.load(f)


def _resolve_eeg_net_csv(*, subject_id: str, eeg_net_name: str) -> str:
    pm = get_path_manager()
    eeg_dir = pm.get_eeg_positions_dir(subject_id)
    if not eeg_dir:
        raise FileNotFoundError(f"EEG positions directory not found for subject {subject_id}")
    path = os.path.join(eeg_dir, eeg_net_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"EEG net CSV not found: {path}")
    return path


@dataclass
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
) -> MontagePublicationResult:
    """
    Build montage publication assets and final `.blend`.

    Returns:
        MontagePublicationResult with paths to scalp/GM STL, electrode blend, and final blend.
    """
    import bpy

    pm = get_path_manager()
    sim_dir = pm.get_simulation_dir(subject_id, simulation_name)
    if not sim_dir:
        raise FileNotFoundError(f"Simulation directory not found for {subject_id}/{simulation_name}")

    cfg = load_sim_config(sim_dir)

    if output_dir is None:
        # Default: <project>/derivatives/ti-toolbox/montage_publication/sub-<id>/<sim>/
        if not pm.project_dir:
            raise RuntimeError("Project directory is not set (PathManager.project_dir is None).")

        output_dir = os.path.join(
            pm.project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            "montage_publication",
            f"{const.PREFIX_SUBJECT}{subject_id}",
            simulation_name,
        )
    os.makedirs(output_dir, exist_ok=True)

    scalp_stl = os.path.join(output_dir, "scalp.stl")
    gm_stl = os.path.join(output_dir, "gm.stl")

    logger.info("Exporting scalp STL...")
    export_scalp_stl_from_sim(sim_dir, output_stl=scalp_stl)

    logger.info("Exporting GM STL...")
    export_gm_stl_from_sim(sim_dir, subject_id=subject_id, simulation_name=simulation_name, output_stl=gm_stl)

    # Electrode placement (produces an electrode-only blend that we append later)
    eeg_net = cfg.get("eeg_net")
    if not eeg_net:
        raise KeyError("config.json missing required field: 'eeg_net'")
    electrode_pairs = cfg.get("electrode_pairs") or []

    eeg_csv = _resolve_eeg_net_csv(subject_id=subject_id, eeg_net_name=str(eeg_net))
    electrode_template = os.path.join(os.path.dirname(__file__), "Electrode.blend")
    subject_m2m = pm.get_m2m_dir(subject_id)
    if not subject_m2m:
        raise FileNotFoundError(f"m2m directory not found for subject {subject_id}")
    subject_msh = os.path.join(subject_m2m, f"{subject_id}.msh")

    from tit.blender_exporter.electrode_placement import ElectrodePlacer, ElectrodePlacementConfig

    ele_cfg = ElectrodePlacementConfig(
        subject_id=subject_id,
        electrode_csv_path=eeg_csv,
        electrode_blend_path=electrode_template,
        output_dir=output_dir,
        subject_msh_path=subject_msh if os.path.exists(subject_msh) else None,
        scalp_stl_path=scalp_stl,
        electrode_size=60.0,
        montage_pairs=[tuple(p) for p in electrode_pairs if isinstance(p, (list, tuple)) and len(p) >= 2],
        export_glb=False,
        show_full_net=show_full_net,
    )

    logger.info("Placing electrodes (building electrode .blend)...")
    placer = ElectrodePlacer(ele_cfg, logger=logger)
    ok, msg = placer.place_electrodes()
    if not ok:
        raise RuntimeError(msg)
    electrodes_blend = ele_cfg.output_blend_path

    # Compose final scene (reuse the current scene produced by ElectrodePlacer)
    # This avoids re-loading the intermediate electrode `.blend` which can fail
    # in headless environments.
    from tit.blender_exporter import scene_setup
    configure_render_eevee = scene_setup.configure_render_eevee
    ensure_world_nodes = scene_setup.ensure_world_nodes
    configure_color_management_agx = scene_setup.configure_color_management_agx
    configure_eevee_publication_quality = scene_setup.configure_eevee_publication_quality
    ensure_collection = scene_setup.ensure_collection
    move_object_to_collection = scene_setup.move_object_to_collection
    ensure_gm_wireframe = scene_setup.ensure_gm_wireframe
    create_principled_material = scene_setup.create_principled_material
    import_stl = scene_setup.import_stl
    remove_objects_by_type = scene_setup.remove_objects_by_type
    create_hero_camera = scene_setup.create_hero_camera

    logger.info("Composing final Blender scene...")

    # Style existing scalp (created by electrode placement)
    scalp_obj = bpy.data.objects.get("Scalp")
    if scalp_obj and getattr(scalp_obj, "data", None) and hasattr(scalp_obj.data, "materials"):
        scalp_mat = create_principled_material(
            "ScalpMaterial",
            # Match the user's manual .blend (slightly translucent scalp).
            base_color=(0.24, 0.18, 0.13, 1.0),
            alpha=0.4,
            metallic=0.0,
            roughness=0.35,
            blend_method="HASHED",
        )
        # Match manual scalp shader details (if available on this Principled version).
        try:
            bsdf = scalp_mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.2
                if "Subsurface Weight" in bsdf.inputs:
                    bsdf.inputs["Subsurface Weight"].default_value = 0.0
                if "Subsurface Scale" in bsdf.inputs:
                    bsdf.inputs["Subsurface Scale"].default_value = 0.05
                if "Subsurface Radius" in bsdf.inputs:
                    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.2, 0.1)
        except Exception:
            pass
        scalp_obj.data.materials.clear()
        scalp_obj.data.materials.append(scalp_mat)

    # (1) Put head tissues under their own "Head" collection
    head_coll = ensure_collection("Head")

    # Import GM STL directly into Head collection (prevents duplicate membership)
    gm_obj = import_stl(gm_stl, name="GM", collection=head_coll)
    gm_mat = create_principled_material(
        "GMMaterial",
        # Slightly brighter and a touch more opaque so it reads under scalp.
        base_color=(0.36, 0.72, 0.80, 1.0),
        alpha=0.45,
        metallic=0.0,
        roughness=0.45,
        blend_method="HASHED",
    )
    gm_obj.data.materials.clear()
    gm_obj.data.materials.append(gm_mat)

    # Ensure scalp is ONLY in Head as well (no duplicates)
    move_object_to_collection(scalp_obj, collection=head_coll, unlink_from_others=True)
    # GM was linked directly to Head, but keep this for safety/determinism.
    move_object_to_collection(gm_obj, collection=head_coll, unlink_from_others=True)

    # (2) Add GM wireframe (match manual .blend)
    ensure_gm_wireframe(
        gm_obj,
        thickness=0.02,
        offset=0.0,
        use_replace=True,
        use_even_offset=True,
        use_boundary=False,
        name="Wireframe",
    )

    # Brighter ambient to avoid "dead" shadows; film stays transparent for PNG compositing.
    ensure_world_nodes(bg_color=(0.12, 0.12, 0.12, 1.0), strength=1.2)
    configure_render_eevee(resolution=(2048, 2048), transparent_film=True)
    configure_color_management_agx(exposure=0.9, look="Medium High Contrast")
    configure_eevee_publication_quality()

    # Camera + light
    add_area_light = scene_setup.add_area_light
    add_sun_light = scene_setup.add_sun_light
    create_standard_cameras = scene_setup.create_standard_cameras

    # Remove any prior lights/cameras to keep output deterministic across runs.
    remove_objects_by_type(("LIGHT", "CAMERA"))

    # Lighting: stronger key/fill + dedicated rim for depth/shape (less "tame").
    add_sun_light(location=(0.0, 0.0, 0.0), rotation_euler=(0.55, -0.25, 0.35), energy=3.5, name="Sun")
    add_area_light(
        location=(260.0, -320.0, 320.0),
        rotation_euler=(0.95, 0.0, 0.85),
        energy=1800.0,
        size=450.0,
        name="Key",
    )
    add_area_light(
        location=(-260.0, -220.0, 240.0),
        rotation_euler=(0.85, 0.0, -0.65),
        energy=750.0,
        size=700.0,
        name="Fill",
    )
    # Rim/back light: gives the scalp a crisp outline and makes electrodes pop.
    add_area_light(
        location=(0.0, 420.0, 340.0),
        rotation_euler=(-0.7, 0.0, 0.0),
        energy=1400.0,
        size=550.0,
        name="Rim",
    )

    # Create 5 standard cameras that share lens/sensor and are auto-framed to the scene.
    # Names: top/left/right/front/back (per user request).
    cams = create_standard_cameras(
        target_objects=[o for o in bpy.context.scene.objects if o.type in {"MESH", "FONT"}],
        lens=60.0,
        margin=1.08,
    )
    # Bring back a diagonal "hero" camera (more compelling) and make it active.
    hero = create_hero_camera(
        target_objects=[o for o in bpy.context.scene.objects if o.type in {"MESH", "FONT"}],
        lens=70.0,
        margin=1.04,
        name="hero",
    )
    bpy.context.scene.camera = hero

    final_blend = os.path.join(output_dir, f"{subject_id}_{simulation_name}_montage_publication.blend")
    bpy.ops.wm.save_as_mainfile(filepath=final_blend)

    return MontagePublicationResult(
        scalp_stl=scalp_stl,
        gm_stl=gm_stl,
        electrodes_blend=electrodes_blend,
        final_blend=final_blend,
    )


