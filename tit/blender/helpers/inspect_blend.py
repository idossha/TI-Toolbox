#!/usr/bin/env simnibs_python
"""
Script to inspect a Blender file and extract scene information.
"""
import bpy
import sys

# -----------------------------
# Helpers (robust across versions)
# -----------------------------


def _fmt(v):
    """Safe formatter for Blender values (Vector/Euler/Color/etc)."""
    try:
        # Many Blender types support slicing -> tuple
        if hasattr(v, "__len__") and not isinstance(v, (str, bytes)):
            try:
                return tuple(v[:])
            except Exception:
                # Tuple conversion may fail for some Blender types - continue with string conversion
                pass
        return str(v)
    except Exception:
        return "<unprintable>"


def _getattr(obj, name, default="<n/a>"):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _print_section(title: str) -> None:
    print("\n" + "-" * 80)
    print(title)
    print("-" * 80)


def _print_kv(key: str, value) -> None:
    print(f"{key}: {_fmt(value)}")


def _print_world_nodes(world) -> None:
    if not world:
        print("  <no world>")
        return

    print(f"  Name: {world.name}")
    print(f"  Use Nodes: {world.use_nodes}")
    if not world.use_nodes or not world.node_tree:
        return

    # Print a compact view of world nodes (background, env textures, mapping)
    nodes = list(world.node_tree.nodes)
    print(f"  Nodes: {len(nodes)}")
    for n in nodes:
        try:
            ntype = n.bl_idname
            label = n.label if getattr(n, "label", "") else n.name
            print(f"    - {label} ({ntype})")
            if ntype in {"ShaderNodeBackground"}:
                col = n.inputs.get("Color")
                strength = n.inputs.get("Strength")
                if col:
                    print(f"      Color: {_fmt(col.default_value)}")
                if strength:
                    print(f"      Strength: {_fmt(strength.default_value)}")
            if ntype in {"ShaderNodeTexEnvironment"}:
                img = getattr(n, "image", None)
                if img:
                    print(f"      Image: {img.name}")
                    fp = getattr(img, "filepath", None) or getattr(
                        img, "filepath_raw", None
                    )
                    if fp:
                        print(f"      Image File: {fp}")
            if ntype in {"ShaderNodeMapping"}:
                loc = n.inputs.get("Location")
                rot = n.inputs.get("Rotation")
                scale = n.inputs.get("Scale")
                if loc:
                    print(f"      Location: {_fmt(loc.default_value)}")
                if rot:
                    print(f"      Rotation: {_fmt(rot.default_value)}")
                if scale:
                    print(f"      Scale: {_fmt(scale.default_value)}")
        except Exception as e:
            print(f"    - <node print failed: {e}>")


def _print_color_management(scene) -> None:
    vs = getattr(scene, "view_settings", None)
    ds = getattr(scene, "display_settings", None)
    se = getattr(scene, "sequencer_colorspace_settings", None)

    if ds:
        _print_kv("Display Device", _getattr(ds, "display_device"))
    if vs:
        _print_kv("View Transform", _getattr(vs, "view_transform"))
        _print_kv("Look", _getattr(vs, "look"))
        _print_kv("Exposure", _getattr(vs, "exposure"))
        _print_kv("Gamma", _getattr(vs, "gamma"))
        _print_kv("Use Curve Mapping", _getattr(vs, "use_curve_mapping"))
    if se:
        _print_kv("Sequencer Colorspace", _getattr(se, "name"))


def _print_eevee_settings(scene) -> None:
    ee = getattr(scene, "eevee", None)
    if not ee:
        print("  <no eevee settings on this Blender version/scene>")
        return

    # Blender versions rename Eevee properties fairly often (2.9x -> 3.x -> 4.x),
    # so we use a hybrid approach:
    # - print a curated set when present
    # - also auto-dump any Eevee properties whose names match key lighting keywords
    curated = [
        # AO / contact shadows
        "use_gtao",
        "gtao_distance",
        "gtao_factor",
        "use_gtao_bent_normals",
        "use_gtao_bounce",
        # Bloom / glare
        "use_bloom",
        "bloom_intensity",
        "bloom_threshold",
        "bloom_radius",
        # Shadows
        "use_soft_shadows",
        "shadow_cube_size",
        "shadow_cascade_size",
        "shadow_cascade_count",
        "shadow_high_bitdepth",
        "use_shadow_high_bitdepth",
        # Reflections
        "use_ssr",
        "use_ssr_refraction",
        "ssr_thickness",
        # Volumetrics
        "use_volumetric",
        "volumetric_tile_size",
        "volumetric_samples",
        "volumetric_sample_distribution",
        "use_volumetric_lights",
        "use_volumetric_shadows",
        # Sampling / TAA
        "taa_render_samples",
        "taa_samples",
        "use_taa_reprojection",
        # Motion blur
        "use_motion_blur",
        "motion_blur_shutter",
    ]

    printed = set()
    for f in curated:
        if hasattr(ee, f):
            _print_kv(f, getattr(ee, f))
            printed.add(f)

    # Keyword-driven dump (helps when property names differ across Blender versions).
    keywords = (
        "ao",
        "gtao",
        "bloom",
        "shadow",
        "contact",
        "ssr",
        "reflection",
        "refract",
        "volum",
        "taa",
        "sample",
        "light",
        "gi",
        "indirect",
        "exposure",
        "color",
        "curve",
        "bokeh",
    )

    auto = []
    for name in dir(ee):
        if name.startswith("_") or name in printed:
            continue
        lname = name.lower()
        if not any(k in lname for k in keywords):
            continue
        try:
            val = getattr(ee, name)
        except Exception:
            # Attribute access may fail for some Blender objects - skip this attribute
            continue
        # Only print "simple" values (avoid dumping large datablocks)
        if isinstance(val, (bool, int, float, str, tuple)):
            auto.append((name, val))

    if auto:
        print("\n  (auto-detected eevee properties)")
        for name, val in sorted(auto, key=lambda x: x[0]):
            _print_kv(name, val)


def _print_render_settings(scene) -> None:
    r = scene.render
    _print_kv("Engine", r.engine)
    _print_kv("Film Transparent", r.film_transparent)
    _print_kv("Resolution", (r.resolution_x, r.resolution_y))
    _print_kv("Resolution %", getattr(r, "resolution_percentage", "<n/a>"))
    _print_kv("Pixel Aspect", (r.pixel_aspect_x, r.pixel_aspect_y))
    _print_kv("Use Border", getattr(r, "use_border", "<n/a>"))
    _print_kv(
        "Border Min",
        (getattr(r, "border_min_x", "<n/a>"), getattr(r, "border_min_y", "<n/a>")),
    )
    _print_kv(
        "Border Max",
        (getattr(r, "border_max_x", "<n/a>"), getattr(r, "border_max_y", "<n/a>")),
    )
    _print_kv("Use Persistent Data", getattr(r, "use_persistent_data", "<n/a>"))
    _print_kv("Dither Intensity", getattr(r, "dither_intensity", "<n/a>"))


def _print_camera(cam_obj) -> None:
    cam = cam_obj.data
    print(f"Camera: {cam_obj.name}")
    print(f"  Location: {cam_obj.location}")
    print(f"  Rotation (euler): {cam_obj.rotation_euler}")
    print(f"  Type: {cam.type}")

    if cam.type == "ORTHO":
        print(f"  Ortho Scale: {cam.ortho_scale}")
    else:
        print(f"  Focal Length: {cam.lens}")

    # Optics / framing
    print(
        f"  Sensor: {getattr(cam, 'sensor_width', '<n/a>')} x {getattr(cam, 'sensor_height', '<n/a>')} ({getattr(cam, 'sensor_fit', '<n/a>')})"
    )
    print(
        f"  Clip: {getattr(cam, 'clip_start', '<n/a>')} .. {getattr(cam, 'clip_end', '<n/a>')}"
    )
    print(
        f"  Shift: {getattr(cam, 'shift_x', '<n/a>')}, {getattr(cam, 'shift_y', '<n/a>')}"
    )

    # DOF
    dof = getattr(cam, "dof", None)
    if dof:
        print(f"  DOF enabled: {getattr(dof, 'use_dof', '<n/a>')}")
        print(
            f"  Focus Object: {getattr(getattr(dof, 'focus_object', None), 'name', None)}"
        )
        print(f"  Focus Distance: {getattr(dof, 'focus_distance', '<n/a>')}")
        print(f"  Aperture fstop: {getattr(dof, 'aperture_fstop', '<n/a>')}")


def _print_light(light_obj) -> None:
    ld = light_obj.data
    print(f"  {light_obj.name}:")
    print(f"    Type: {ld.type}")
    print(f"    Energy: {ld.energy}")
    if hasattr(ld, "color"):
        print(f"    Color: {_fmt(ld.color)}")
    if hasattr(ld, "specular_factor"):
        print(f"    Specular Factor: {_fmt(ld.specular_factor)}")
    if hasattr(ld, "use_shadow"):
        print(f"    Use Shadow: {_fmt(ld.use_shadow)}")
    if hasattr(ld, "shadow_soft_size"):
        print(f"    Shadow Soft Size: {_fmt(ld.shadow_soft_size)}")
    if hasattr(ld, "angle"):
        print(f"    Angle: {_fmt(ld.angle)}")

    print(f"    Location: {light_obj.location}")
    print(f"    Rotation: {light_obj.rotation_euler}")

    if ld.type == "AREA":
        # Blender uses size/size_y depending on shape
        if hasattr(ld, "shape"):
            print(f"    Shape: {_fmt(ld.shape)}")
        if hasattr(ld, "size"):
            print(f"    Size: {_fmt(ld.size)}")
        if hasattr(ld, "size_y"):
            print(f"    Size Y: {_fmt(ld.size_y)}")


# Clear any existing data
bpy.ops.wm.read_homefile(use_empty=True)

# Open the blend file
blend_file = sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=blend_file)

print("=" * 80)
print(f"Inspecting: {blend_file}")
print("=" * 80)

# Render / output settings
scene = bpy.context.scene
_print_section("Render Settings")
_print_render_settings(scene)

_print_section("Color Management")
_print_color_management(scene)

_print_section("Eevee Settings")
_print_eevee_settings(scene)

# Camera
_print_section("Active Camera")
if scene.camera:
    _print_camera(scene.camera)
else:
    print("<no active camera>")

_print_section("All Cameras")
for obj in scene.objects:
    if obj.type == "CAMERA":
        _print_camera(obj)

# Collections
print(f"\nCollections:")
for coll in bpy.data.collections:
    print(f"  - {coll.name} ({len(coll.objects)} objects)")
    for obj in coll.objects:
        print(f"    • {obj.type}: {obj.name}")

# All objects in scene
print(f"\nAll Objects in Scene:")
for obj in bpy.context.scene.objects:
    print(f"\n  Object: {obj.name}")
    print(f"    Type: {obj.type}")
    print(f"    Location: {obj.location}")
    print(f"    Rotation: {obj.rotation_euler}")
    print(f"    Scale: {obj.scale}")
    print(f"    Visible: {not obj.hide_viewport}")
    print(f"    Render: {not obj.hide_render}")

    # Parent relationship
    if obj.parent:
        print(f"    Parent: {obj.parent.name}")

    # Materials
    if hasattr(obj.data, "materials"):
        print(f"    Materials: {len(obj.data.materials)}")
        for i, mat in enumerate(obj.data.materials):
            if mat:
                print(f"      [{i}] {mat.name}")
                print(f"        Use Nodes: {mat.use_nodes}")
                print(f"        Blend Method: {mat.blend_method}")
                if mat.use_nodes:
                    bsdf = mat.node_tree.nodes.get("Principled BSDF")
                    if bsdf:
                        print(
                            f"        Base Color: {bsdf.inputs['Base Color'].default_value[:]}"
                        )
                        print(f"        Alpha: {bsdf.inputs['Alpha'].default_value}")
                        print(
                            f"        Metallic: {bsdf.inputs['Metallic'].default_value}"
                        )
                        print(
                            f"        Roughness: {bsdf.inputs['Roughness'].default_value}"
                        )
                        if "Emission" in bsdf.inputs:
                            print(
                                f"        Emission: {bsdf.inputs['Emission'].default_value[:]}"
                            )
                        if "Emission Strength" in bsdf.inputs:
                            print(
                                f"        Emission Strength: {bsdf.inputs['Emission Strength'].default_value}"
                            )
                        if "Transmission" in bsdf.inputs:
                            print(
                                f"        Transmission: {bsdf.inputs['Transmission'].default_value}"
                            )

# Lights
_print_section("Lights")
any_lights = False
for obj in scene.objects:
    if obj.type == "LIGHT":
        any_lights = True
        _print_light(obj)
if not any_lights:
    print("<no lights>")

# World settings
_print_section("World")
_print_world_nodes(scene.world)

print("\n" + "=" * 80)
