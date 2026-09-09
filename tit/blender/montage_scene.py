"""Standalone Blender scene phase: prepared geometry in, existing montage files out.

Run with Blender --background --factory-startup --python-exit-code 1 --python this_file -- manifest.json.
No SimNIBS, SciPy or nibabel imports are permitted in this process.
"""

import json
import logging
import os
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


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
    mat.surface_render_method = "DITHERED"

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        # Match the user's manual .blend (slightly translucent scalp)
        bsdf.inputs["Base Color"].default_value = (0.24, 0.18, 0.13, 1.0)
        bsdf.inputs["Alpha"].default_value = 0.4
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.35

        # Match manual scalp shader details (if available on this Principled version)
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.2
        if "Subsurface Weight" in bsdf.inputs:
            bsdf.inputs["Subsurface Weight"].default_value = 0.0
        if "Subsurface Scale" in bsdf.inputs:
            bsdf.inputs["Subsurface Scale"].default_value = 0.05
        if "Subsurface Radius" in bsdf.inputs:
            bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.2, 0.1)

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
    mat.surface_render_method = "DITHERED"

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


def render_montage(manifest: dict) -> None:
    import bpy
    import numpy as np

    if not bpy.app.background:
        raise RuntimeError("Montage renderer requires Blender --background")
    from tit.blender.electrode_placement import (
        ElectrodePlacementConfig,
        ElectrodePlacer,
    )
    from tit.blender import scene_setup

    subject_id = manifest["subject_id"]
    simulation_name = manifest["simulation_name"]
    output_dir = manifest["output_dir"]
    gm_stl = manifest["gm_stl"]
    ele_cfg = ElectrodePlacementConfig(**manifest["placement"])
    with np.load(manifest["geometry"], allow_pickle=False) as mesh:
        geometry = (mesh["vertices"].tolist(), mesh["faces"].tolist())
    placer = ElectrodePlacer(
        ele_cfg,
        logger=logger,
        prepared_geometry=geometry,
        prepared_electrodes=manifest["electrodes"],
    )
    ok, msg = placer.place_electrodes()
    if not ok:
        raise RuntimeError(msg)
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


if __name__ == "__main__":
    # --python runs a file, not a package; only add this checked-out package's root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    logging.basicConfig(level=logging.INFO)
    manifest_path = sys.argv[sys.argv.index("--") + 1]
    with open(manifest_path, encoding="utf-8") as stream:
        render_montage(json.load(stream))
