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
from tit import logger as logging_util

logger = logging.getLogger(__name__)


def configure_montage_loggers(parent_logger: logging.Logger) -> None:
    """
    Configure all montage publication related loggers to use the parent logger's handlers.

    This ensures consistent logging behavior between CLI and GUI interfaces.

    Args:
        parent_logger: The parent logger whose handlers should be used
    """
    logging_util.configure_external_loggers(
        names=[
            "tit.blender.montage_publication",
            "tit.blender.electrode_placement",
            "tit.blender.utils",
            "tit.blender.scene_setup",
            "simnibs",
        ],
        parent_logger=parent_logger,
    )


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


def _find_central_surface_mesh(
    sim_dir: str, subject_id: str, simulation_name: str
) -> str:
    import subprocess
    import shutil
    from pathlib import Path

    pm = get_path_manager()
    expected = pm.path_optional(
        "ti_central_surface", subject_id=subject_id, simulation_name=simulation_name
    )
    if expected and os.path.exists(expected):
        logger.debug(f"Found existing central surface: {expected}")
        return expected

    # Check for existing central surface in known locations
    for d in (
        os.path.join(sim_dir, "TI", "mesh", "surfaces"),
        os.path.join(sim_dir, "TI", "mesh"),
    ):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith("_TI_central.msh"):
                found_path = os.path.join(d, f)
                logger.debug(f"Found existing central surface: {found_path}")
                return found_path

    # Central surface not found - generate it using msh2cortex
    logger.info("Central surface not found, generating using msh2cortex...")

    # Get paths
    ti_mesh_path = pm.path_optional(
        "ti_mesh", subject_id=subject_id, simulation_name=simulation_name
    )
    if not ti_mesh_path or not os.path.exists(ti_mesh_path):
        raise FileNotFoundError(
            f"Volumetric TI mesh not found; expected at: {ti_mesh_path}"
        )

    m2m_dir = pm.path_optional("m2m", subject_id=subject_id)
    if not m2m_dir or not os.path.isdir(m2m_dir):
        raise FileNotFoundError(f"m2m directory not found for subject {subject_id}")

    # Create surfaces directory if it doesn't exist
    surfaces_dir = os.path.join(sim_dir, "TI", "mesh", "surfaces")
    os.makedirs(surfaces_dir, exist_ok=True)

    # Run msh2cortex
    cmd = ["msh2cortex", "-i", ti_mesh_path, "-m", m2m_dir, "-o", surfaces_dir]
    logger.info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True
        )
        if result.stdout:
            logger.debug(f"msh2cortex output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"msh2cortex failed with exit code {e.returncode}")
        if e.stdout:
            logger.error(f"msh2cortex output: {e.stdout}")
        raise RuntimeError(f"msh2cortex failed to generate surface mesh: {e}")

    # Find the generated central surface
    produced = None
    for p in Path(surfaces_dir).glob("*_central.msh"):
        produced = str(p)
        break

    if not produced or not os.path.exists(produced):
        raise FileNotFoundError(
            f"Central surface not found after msh2cortex in {surfaces_dir}"
        )

    # Copy to expected path if different
    if expected and os.path.abspath(produced) != os.path.abspath(expected):
        try:
            os.makedirs(os.path.dirname(expected), exist_ok=True)
            shutil.copyfile(produced, expected)
            logger.info(f"Generated central surface: {expected}")
            return expected
        except Exception as e:
            logger.warning(f"Could not copy to expected path: {e}")

    logger.info(f"Generated central surface: {produced}")
    return produced


def export_scalp_stl_from_sim(
    sim_dir: str, *, output_stl: str, skin_tag: int = 1005
) -> str:
    tetra_mesh = _find_tetrahedral_mesh(sim_dir)
    vertices, faces = be_utils.extract_scalp_from_msh(tetra_mesh, skin_tag=skin_tag)
    os.makedirs(os.path.dirname(output_stl), exist_ok=True)
    be_utils.write_binary_stl(vertices, faces, output_stl, "TI-Toolbox Scalp Mesh")
    return output_stl


def export_gm_stl_from_sim(
    sim_dir: str, *, subject_id: str, simulation_name: str, output_stl: str
) -> str:
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
        raise FileNotFoundError(
            f"EEG positions directory not found for subject {subject_id}"
        )
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


def _apply_scalp_material(scalp_obj) -> None:
    """
    Apply publication-ready scalp material.

    Publication-standard material properties:
    - Semi-transparent skin-tone appearance (alpha=0.4)
    - HASHED blend method for proper transparency
    - Subtle subsurface scattering for realism
    """
    import bpy

    # Remove existing materials
    scalp_obj.data.materials.clear()

    # Create scalp material with publication-standard properties
    mat = bpy.data.materials.new(name="ScalpMaterial")
    mat.use_nodes = True
    mat.blend_method = "HASHED"

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        # Match the user's manual .blend (slightly translucent scalp)
        bsdf.inputs["Base Color"].default_value = (0.24, 0.18, 0.13, 1.0)
        bsdf.inputs["Alpha"].default_value = 0.4
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.35

        # Match manual scalp shader details (if available on this Principled version)
        try:
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

    scalp_obj.data.materials.append(mat)
    logger.debug("Applied scalp material (alpha=0.4, skin-tone with subsurface)")


def _apply_gm_material(gm_obj) -> None:
    """
    Apply publication-ready GM material.

    Publication-standard material properties:
    - Semi-transparent blue-tinted color (alpha=0.45)
    - HASHED blend method for proper transparency
    """
    import bpy

    # Remove existing materials
    gm_obj.data.materials.clear()

    # Create GM material with publication-standard properties
    mat = bpy.data.materials.new(name="GMMaterial")
    mat.use_nodes = True
    mat.blend_method = "HASHED"

    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        # Slightly brighter and a touch more opaque so it reads under scalp
        bsdf.inputs["Base Color"].default_value = (0.36, 0.72, 0.80, 1.0)
        bsdf.inputs["Alpha"].default_value = 0.45  # Semi-transparent
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.45

    gm_obj.data.materials.append(mat)
    logger.debug("Applied GM material (alpha=0.45, blue-tinted)")


def build_montage_publication_blend(
    *,
    subject_id: str,
    simulation_name: str,
    output_dir: Optional[str] = None,
    show_full_net: bool = True,
    electrode_diameter_mm: float = 10.0,
    electrode_height_mm: float = 6.0,
    export_glb: bool = False,
) -> MontagePublicationResult:
    import bpy

    pm = get_path_manager()
    sim_dir = pm.path_optional(
        "simulation", subject_id=subject_id, simulation_name=simulation_name
    )
    if not sim_dir:
        raise FileNotFoundError(
            f"Simulation directory not found for {subject_id}/{simulation_name}"
        )

    cfg = be_utils.load_simulation_config(subject_id, simulation_name)
    if not cfg:
        raise FileNotFoundError(
            f"Simulation config.json not found for {subject_id}/{simulation_name} (expected under documentation/config.json)."
        )

    if output_dir is None:
        if not pm.project_dir:
            raise RuntimeError(
                "Project directory is not set (PathManager.project_dir is None)."
            )
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
    export_gm_stl_from_sim(
        sim_dir,
        subject_id=subject_id,
        simulation_name=simulation_name,
        output_stl=gm_stl,
    )

    eeg_net = cfg.get("eeg_net")
    if not eeg_net:
        raise KeyError("config.json missing required field: 'eeg_net'")
    electrode_pairs = cfg.get("electrode_pairs") or []

    eeg_csv = _resolve_eeg_net_csv(subject_id=subject_id, eeg_net_name=str(eeg_net))
    electrode_template = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "Electrode.blend")
    )

    subject_m2m = pm.path_optional("m2m", subject_id=subject_id)
    if not subject_m2m or not os.path.isdir(subject_m2m):
        raise FileNotFoundError(f"m2m directory not found for subject {subject_id}")
    subject_msh = os.path.join(subject_m2m, f"{subject_id}.msh")

    from tit.blender.electrode_placement import (
        ElectrodePlacer,
        ElectrodePlacementConfig,
    )

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
        montage_pairs=[
            tuple(p)
            for p in electrode_pairs
            if isinstance(p, (list, tuple)) and len(p) >= 2
        ],
        export_glb=export_glb,
        show_full_net=show_full_net,
    )

    placer = ElectrodePlacer(
        ele_cfg, logger=logging.getLogger("tit.blender.electrode_placement")
    )
    ok, msg = placer.place_electrodes()
    if not ok:
        raise RuntimeError(msg)
    electrodes_blend = ele_cfg.output_blend_path

    # Compose final scene on the current scene produced by ElectrodePlacer
    from tit.blender import scene_setup

    logger.info("Composing final scene...")

    # Get scalp object from ElectrodePlacer output
    scalp_obj = bpy.data.objects.get("Scalp")
    if not scalp_obj:
        raise RuntimeError(
            "Scalp object not found in scene (expected from ElectrodePlacer)"
        )

    # Create Head collection and organize objects
    head_coll = scene_setup.ensure_collection("Head")
    gm_obj = scene_setup.import_stl(gm_stl, name="GM", collection=head_coll)
    scene_setup.move_object_to_collection(
        scalp_obj, collection=head_coll, unlink_from_others=True
    )
    scene_setup.move_object_to_collection(
        gm_obj, collection=head_coll, unlink_from_others=True
    )

    # Apply publication-standard materials
    logger.info("Applying materials...")
    _apply_scalp_material(scalp_obj)
    _apply_gm_material(gm_obj)

    # Add GM wireframe (match manual .blend)
    scene_setup.ensure_gm_wireframe(
        gm_obj,
        thickness=0.02,
        offset=0.0,
        use_replace=True,
        use_even_offset=True,
        use_boundary=False,
        name="Wireframe",
    )

    # Set up world background (brighter ambient to avoid "dead" shadows)
    logger.info("Configuring world and render settings...")
    scene_setup.ensure_world_nodes(bg_color=(0.12, 0.12, 0.12, 1.0), strength=1.2)

    # Configure render settings
    scene_setup.configure_render_eevee(resolution=(2048, 2048), transparent_film=True)
    scene_setup.configure_color_management_agx(
        exposure=0.9, look="Medium High Contrast"
    )
    scene_setup.configure_eevee_publication_quality()

    # Remove any prior lights/cameras to keep output deterministic across runs
    logger.info("Setting up cameras and lighting...")
    scene_setup.remove_objects_by_type(("LIGHT", "CAMERA"))

    # Lighting: stronger key/fill + dedicated rim for depth/shape (less "tame")
    scene_setup.add_sun_light(
        location=(0.0, 0.0, 0.0),
        rotation_euler=(0.55, -0.25, 0.35),
        energy=3.5,
        name="Sun",
    )
    scene_setup.add_area_light(
        location=(260.0, -320.0, 320.0),
        rotation_euler=(0.95, 0.0, 0.85),
        energy=1800.0,
        size=450.0,
        name="Key",
    )
    scene_setup.add_area_light(
        location=(-260.0, -220.0, 240.0),
        rotation_euler=(0.85, 0.0, -0.65),
        energy=750.0,
        size=700.0,
        name="Fill",
    )
    # Rim/back light: gives the scalp a crisp outline and makes electrodes pop
    scene_setup.add_area_light(
        location=(0.0, 420.0, 340.0),
        rotation_euler=(-0.7, 0.0, 0.0),
        energy=1400.0,
        size=550.0,
        name="Rim",
    )

    # Create 5 standard cameras that share lens/sensor and are auto-framed to the scene
    # Names: top/left/right/front/back
    cams = scene_setup.create_standard_cameras(
        target_objects=[
            o for o in bpy.context.scene.objects if o.type in {"MESH", "FONT"}
        ],
        lens=60.0,
        margin=1.08,
    )
    # Bring back a diagonal "hero" camera (more compelling) and make it active
    hero = scene_setup.create_hero_camera(
        target_objects=[
            o for o in bpy.context.scene.objects if o.type in {"MESH", "FONT"}
        ],
        lens=70.0,
        margin=1.04,
        name="hero",
    )
    bpy.context.scene.camera = hero

    logger.info("Scene setup complete.")

    final_blend = os.path.join(
        output_dir, f"{subject_id}_{simulation_name}_montage_publication.blend"
    )
    bpy.ops.wm.save_as_mainfile(filepath=final_blend)

    return MontagePublicationResult(
        scalp_stl=scalp_stl,
        gm_stl=gm_stl,
        electrodes_blend=electrodes_blend,
        final_blend=final_blend,
    )
