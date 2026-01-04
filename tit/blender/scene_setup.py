#!/usr/bin/env simnibs_python
"""
Reusable Blender scene setup helpers for TI-Toolbox 3D exporter.

This module is intended to be imported from within Blender/simnibs_python
(i.e., when `bpy` is available). Keep it lightweight and "ops"-free where
possible for speed and stability in headless mode.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import struct


RGBA = Tuple[float, float, float, float]


def clear_scene(*, remove_collections: bool = True) -> None:
    """Clear objects (and optionally collections) from the current Blender file."""
    import bpy

    # Remove objects first (unlinks from collections too)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # Remove meshes to avoid accumulating datablocks
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)

    # Optionally remove collections (except the scene's master collection)
    if remove_collections:
        for coll in list(bpy.data.collections):
            try:
                bpy.data.collections.remove(coll)
            except Exception:
                # Some collections may be in use or required by Blender - skip them
                pass


def ensure_collection(name: str):
    """Get or create a top-level collection linked to the scene."""
    import bpy

    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def move_object_to_collection(
    obj,
    *,
    collection,
    unlink_from_others: bool = True,
) -> None:
    """
    Ensure obj is linked to `collection` and (optionally) unlinked from other collections.
    """
    import bpy

    if obj is None or collection is None:
        return

    # Link to target collection if not already linked
    try:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
    except Exception:
        # Object linking may fail if object is already linked or invalid
        pass

    if not unlink_from_others:
        return

    # Unlink from all other collections
    for coll in list(bpy.data.collections):
        if coll == collection:
            continue
        try:
            if obj.name in coll.objects:
                coll.objects.unlink(obj)
        except Exception:
            # Object unlinking may fail if object is not in collection
            pass


def ensure_gm_wireframe(
    gm_obj,
    *,
    thickness: float = 0.02,
    offset: float = 0.0,
    use_replace: bool = True,
    use_even_offset: bool = True,
    use_boundary: bool = False,
    name: str = "Wireframe",
) -> None:
    """Add (or replace) a Wireframe modifier on GM to match the publication style."""
    if gm_obj is None:
        return

    # Remove existing wireframe modifiers so output is deterministic.
    for m in list(gm_obj.modifiers):
        if m.type == "WIREFRAME":
            try:
                gm_obj.modifiers.remove(m)
            except Exception:
                # Modifier removal may fail if modifier is in use
                pass

    mod = gm_obj.modifiers.new(name=name, type="WIREFRAME")
    mod.thickness = float(thickness)
    mod.offset = float(offset)
    mod.use_replace = bool(use_replace)
    mod.use_even_offset = bool(use_even_offset)
    mod.use_boundary = bool(use_boundary)
    # material_offset kept at 0 (matches the user's manual .blend)
    try:
        mod.material_offset = 0
    except Exception:
        # Material offset setting may fail in some Blender versions
        pass


def ensure_world_nodes(*, bg_color: RGBA = (0.05, 0.05, 0.05, 1.0), strength: float = 1.0) -> None:
    """Ensure the scene world uses nodes and set a consistent background."""
    import bpy

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = bg_color
        bg_node.inputs["Strength"].default_value = float(strength)


def configure_render_eevee(
    *,
    resolution: Tuple[int, int] = (2048, 2048),
    transparent_film: bool = True,
) -> None:
    """Configure Eevee render settings."""
    import bpy

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = bool(transparent_film)
    scene.render.resolution_x = int(resolution[0])
    scene.render.resolution_y = int(resolution[1])


def configure_color_management_agx(
    *,
    exposure: float = 0.8,
    look: str = "Medium High Contrast",
) -> None:
    """
    Set explicit color management so renders are brighter and have more punch.

    This repo's montage publication scenes were observed to use AgX with neutral settings
    (Exposure=0). For more compelling images, we push exposure and a contrast "look".
    """
    import bpy

    scene = bpy.context.scene
    vs = scene.view_settings
    ds = scene.display_settings

    # Explicitly set AgX pipeline (matches the user's inspected .blend)
    ds.display_device = "sRGB"
    vs.view_transform = "AgX"
    vs.exposure = float(exposure)
    vs.gamma = 1.0
    vs.use_curve_mapping = False

    # AgX look names vary slightly across Blender builds; keep it simple and fail-soft.
    try:
        vs.look = look
    except Exception:
        # Fallback to default/none if the exact look name isn't available.
        vs.look = "None"


def configure_eevee_publication_quality() -> None:
    """
    Configure Eevee for nicer, less "tame" publication renders:
    - enable/boost fast GI
    - improve shadows
    - enable bloom when available (nice for electrode highlights)
    """
    import bpy

    scene = bpy.context.scene
    ee = scene.eevee

    # Eevee Next / fast GI
    ee.use_fast_gi = True
    ee.fast_gi_method = "GLOBAL_ILLUMINATION"
    ee.fast_gi_quality = 1.0
    ee.fast_gi_ray_count = 8
    ee.gi_diffuse_bounces = 3
    # In this Blender build it's an ENUM with identifiers like "512", "1024", ...
    ee.gi_cubemap_resolution = "1024"

    # Shadows: cleaner + less noisy
    ee.use_shadows = True
    # Enum in this Blender build: "512", "1024", ...
    ee.shadow_pool_size = "1024"
    ee.shadow_resolution_scale = 2.0
    ee.shadow_ray_count = 4
    ee.shadow_step_count = 8

    # Keep more lights contributing (avoid "why is it dark?" surprises)
    ee.light_threshold = 0.001

    # Optional bloom for highlights (available in some Eevee builds)
    if hasattr(ee, "use_bloom"):
        ee.use_bloom = True
        if hasattr(ee, "bloom_intensity"):
            ee.bloom_intensity = 0.05
        if hasattr(ee, "bloom_threshold"):
            ee.bloom_threshold = 1.0
        if hasattr(ee, "bloom_radius"):
            ee.bloom_radius = 6.0


def remove_objects_by_type(types: Tuple[str, ...]) -> None:
    """Remove all objects in the scene matching the given Blender object types."""
    import bpy

    for obj in list(bpy.context.scene.objects):
        if obj.type in set(types):
            bpy.data.objects.remove(obj, do_unlink=True)


def create_hero_camera(
    *,
    target_objects,
    lens: float = 70.0,
    margin: float = 1.05,
    name: str = "hero",
):
    """
    Create a single "hero" 3/4 camera for more compelling renders.
    Frames the same bounds logic as create_standard_cameras, but from a diagonal angle.
    """
    import bpy
    from math import tan
    from mathutils import Vector

    (minx, miny, minz), (maxx, maxy, maxz) = _world_bounds(target_objects)
    center = Vector(((minx + maxx) / 2.0, (miny + maxy) / 2.0, (minz + maxz) / 2.0))
    size_x = maxx - minx
    size_y = maxy - miny
    size_z = maxz - minz

    # Diagonal 3/4 view with a bit of elevation.
    direction = Vector((1.0, 1.0, 0.6)).normalized()

    bpy.ops.object.camera_add(location=tuple(center))
    cam_obj = bpy.context.selected_objects[0]
    cam_obj.name = name
    cam_obj.data.type = "PERSP"
    cam_obj.data.lens = float(lens)
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 10000.0

    # Fit the largest of X/Y/Z into view conservatively.
    fit_w = max(size_x, size_y)
    fit_h = max(size_y, size_z)
    fov_x = cam_obj.data.angle_x
    fov_y = cam_obj.data.angle_y
    dist_x = (fit_w / 2.0) / tan(fov_x / 2.0) if fov_x > 1e-6 else 1.0
    dist_y = (fit_h / 2.0) / tan(fov_y / 2.0) if fov_y > 1e-6 else 1.0
    dist = max(dist_x, dist_y) * float(margin)

    cam_obj.location = center + direction * dist
    _look_at(cam_obj, (center.x, center.y, center.z))
    bpy.context.scene.camera = cam_obj
    return cam_obj


def add_point_light(
    *,
    location: Tuple[float, float, float] = (3.0290, 14.2176, 22.8508),
    energy: float = 1000.0,
    name: str = "Light",
):
    """Add a point light."""
    import bpy

    bpy.ops.object.light_add(type="POINT", location=location)
    light = bpy.context.selected_objects[0]
    light.name = name
    light.data.energy = float(energy)
    return light


def add_sun_light(
    *,
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation_euler: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    energy: float = 1.0,
    name: str = "Sun",
):
    """Add a sun light (matches typical publication default in this repo)."""
    import bpy

    bpy.ops.object.light_add(type="SUN", location=location)
    sun = bpy.context.selected_objects[0]
    sun.name = name
    sun.rotation_euler = rotation_euler
    sun.data.energy = float(energy)
    return sun


def add_area_light(
    *,
    location: Tuple[float, float, float],
    rotation_euler: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    energy: float = 200.0,
    size: float = 500.0,
    name: str = "Area",
):
    """Add an area light (useful to brighten scenes in Eevee)."""
    import bpy

    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.selected_objects[0]
    light.name = name
    light.rotation_euler = rotation_euler
    light.data.energy = float(energy)
    try:
        light.data.size = float(size)
    except Exception:
        # Light size setting may fail in some Blender versions
        pass
    return light


def add_camera(
    *,
    location: Tuple[float, float, float] = (2.1216, 27.0958, 406.2056),
    rotation_euler: Tuple[float, float, float] = (-0.0223, 0.0060, -0.0028),
    lens: float = 50.0,
    name: str = "Camera",
):
    """Add a perspective camera and set it as active scene camera."""
    import bpy

    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.selected_objects[0]
    cam.name = name
    cam.rotation_euler = rotation_euler
    cam.data.type = "PERSP"
    cam.data.lens = float(lens)
    bpy.context.scene.camera = cam
    return cam


def _world_bounds(target_objects) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Compute world-space AABB (min_xyz, max_xyz) over objects that have a bound_box."""
    from mathutils import Vector

    min_v = Vector((1e18, 1e18, 1e18))
    max_v = Vector((-1e18, -1e18, -1e18))

    any_found = False
    for obj in target_objects:
        if obj is None:
            continue
        if getattr(obj, "hide_render", False):
            continue
        bb = getattr(obj, "bound_box", None)
        if not bb:
            continue
        any_found = True
        for corner in bb:
            w = obj.matrix_world @ Vector(corner)
            min_v.x = min(min_v.x, w.x)
            min_v.y = min(min_v.y, w.y)
            min_v.z = min(min_v.z, w.z)
            max_v.x = max(max_v.x, w.x)
            max_v.y = max(max_v.y, w.y)
            max_v.z = max(max_v.z, w.z)

    if not any_found:
        min_v = Vector((-1.0, -1.0, -1.0))
        max_v = Vector((1.0, 1.0, 1.0))

    return (float(min_v.x), float(min_v.y), float(min_v.z)), (float(max_v.x), float(max_v.y), float(max_v.z))


def _look_at(camera_obj, target: Tuple[float, float, float]) -> None:
    """Rotate camera so that it looks at target point."""
    from mathutils import Vector

    direction = Vector(target) - camera_obj.location
    # Blender camera looks along -Z; Y is up.
    camera_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def create_standard_cameras(
    *,
    target_objects,
    lens: float = 50.0,
    margin: float = 1.15,
) -> Dict[str, object]:
    """
    Create 5 cameras (top/left/right/front/back) that share lens/sensor and frame the scene.

    - **target_objects**: iterable of Blender objects to frame (typically scalp+GM+electrodes)
    - **lens**: focal length (mm)
    - **margin**: multiplicative padding around the framed bounds
    """
    import bpy
    from math import tan
    from mathutils import Vector

    (minx, miny, minz), (maxx, maxy, maxz) = _world_bounds(target_objects)
    center = Vector(((minx + maxx) / 2.0, (miny + maxy) / 2.0, (minz + maxz) / 2.0))
    size_x = maxx - minx
    size_y = maxy - miny
    size_z = maxz - minz

    # Unit view directions for each camera position.
    # These are expressed in world axes; adjust if your coordinate system differs.
    specs = {
        "front": Vector((0.0, 1.0, 0.0)),
        "back": Vector((0.0, -1.0, 0.0)),
        "left": Vector((-1.0, 0.0, 0.0)),
        "right": Vector((1.0, 0.0, 0.0)),
        "top": Vector((0.0, 0.0, 1.0)),
    }

    cams: Dict[str, object] = {}
    for name, direction in specs.items():
        bpy.ops.object.camera_add(location=tuple(center))
        cam_obj = bpy.context.selected_objects[0]
        cam_obj.name = name
        cam_obj.data.type = "PERSP"
        cam_obj.data.lens = float(lens)
        cam_obj.data.clip_start = 0.1
        cam_obj.data.clip_end = 10000.0

        # Determine which bounds to fit into the camera based on view direction.
        if abs(direction.z) > 0.5:  # top view: fit X/Y
            fit_w, fit_h = size_x, size_y
        elif abs(direction.x) > 0.5:  # left/right: fit Y/Z
            fit_w, fit_h = size_y, size_z
        else:  # front/back: fit X/Z
            fit_w, fit_h = size_x, size_z

        # Use camera's angle_x/angle_y after lens is set.
        fov_x = cam_obj.data.angle_x
        fov_y = cam_obj.data.angle_y
        dist_x = (fit_w / 2.0) / tan(fov_x / 2.0) if fov_x > 1e-6 else 1.0
        dist_y = (fit_h / 2.0) / tan(fov_y / 2.0) if fov_y > 1e-6 else 1.0
        dist = max(dist_x, dist_y) * float(margin)

        cam_obj.location = center + direction.normalized() * dist
        _look_at(cam_obj, (center.x, center.y, center.z))
        cams[name] = cam_obj

    return cams


def create_principled_material(
    name: str,
    *,
    base_color: RGBA = (0.8, 0.8, 0.8, 1.0),
    alpha: float = 1.0,
    metallic: float = 0.0,
    roughness: float = 0.5,
    blend_method: str = "HASHED",
):
    """Create a simple Principled-BSDF material."""
    import bpy

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    try:
        mat.blend_method = blend_method
    except Exception:
        # Blend method setting may fail in some Blender versions
        pass

    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = base_color
        bsdf.inputs["Alpha"].default_value = float(alpha)
        bsdf.inputs["Metallic"].default_value = float(metallic)
        bsdf.inputs["Roughness"].default_value = float(roughness)
    return mat


def copy_material_with_color(
    base_material,
    *,
    name: str,
    base_color: RGBA,
) :
    """Copy an existing material and override its base color (Principled BSDF)."""
    mat = base_material.copy() if base_material else None
    if mat is None:
        # Fallback to creating a fresh material
        return create_principled_material(name, base_color=base_color)

    mat.name = name
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = base_color
        # Ensure opaque for electrode highlight colors
        bsdf.inputs["Alpha"].default_value = 1.0
    return mat


def assign_material(obj, mat) -> None:
    """Assign a single material to a mesh object (replace existing slots)."""
    if not hasattr(obj, "data") or not hasattr(obj.data, "materials"):
        return
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def import_stl(filepath: str, *, name: Optional[str] = None, collection=None):
    """
    Import an STL and return the imported object (assumes one object).

    IMPORTANT: This implementation is ops-free (does not rely on `bpy.ops.import_mesh.stl`),
    because the STL importer operator/addon may not be registered in some headless
    SimNIBS/Blender environments.
    """
    import bpy

    vertices, faces = _read_binary_stl(filepath)

    mesh_data = bpy.data.meshes.new(f"{name or 'Mesh'}_Mesh")
    mesh_data.from_pydata(vertices, [], faces)
    mesh_data.update()

    obj = bpy.data.objects.new(name or "Object", mesh_data)
    # Allow caller to control where the object is linked (prevents duplicate collection membership).
    target_coll = collection or bpy.context.scene.collection
    target_coll.objects.link(obj)
    if name:
        obj.name = name
    return obj


def _read_binary_stl(filepath: str):
    """Read a binary STL into (vertices, faces) with vertex de-duplication."""
    # STL parsing is intentionally lightweight; only supports binary STL.
    vertices = []
    faces = []
    vertex_map = {}

    with open(filepath, "rb") as f:
        f.read(80)  # header
        num_triangles = struct.unpack("<I", f.read(4))[0]

        for _ in range(num_triangles):
            f.read(12)  # normal
            face_indices = []
            for _ in range(3):
                v = struct.unpack("<fff", f.read(12))
                if v not in vertex_map:
                    vertex_map[v] = len(vertices)
                    vertices.append(v)
                face_indices.append(vertex_map[v])
            faces.append(tuple(face_indices))
            f.read(2)  # attribute byte count

    return vertices, faces


