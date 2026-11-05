"""Tract renders, the Blender half: a render bundle in, stills and MP4s out.

Run with ``blender --background --factory-startup --python tract_scene.py -- manifest.json
[stills,turntable,propagation]``; the optional second argument overrides which outputs the
manifest asks for. :mod:`tit.blender.tract_publication` writes the bundle. Works on Blender
4.4 (the image) and 5.x (a host build); the few API differences are handled where they occur.
No SimNIBS, SciPy or nibabel imports are permitted in this process.

The scene, written for TI-Toolbox after the method of STREAM-4D (Atalay et al., Brain Stimul
2025, doi:10.1016/j.brs.2025.06.015) -- none of its code or assets are used:

- one mesh of polylines carrying per-point attributes, swept into tubes by a geometry-nodes
  modifier (Mesh to Curve -> Set Curve Radius -> Curve to Mesh);
- emission-only materials reading those attributes: a perceptual colour ramp, brightness and
  radius rising with the field, so low-field fibres stay dim and thin;
- a glass brain and a ghosted scalp drawn as facing-ratio emission over transparency;
- a black world with no lamps, EEVEE, a Bloom pass for the glow.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

#: Brightness of a fibre at colour position v: ``LOW + (1 - LOW) * v**GAMMA``, then a boost
#: above 1 for the top of the range so only hot fibres reach the bloom threshold. Width and
#: opacity never vary along a fibre: varying them per point drew hot segments as stubs.
LOW, GAMMA, BOOST = 0.6, 1.0, 0.8
#: Brightness of a diverging (align_index) fibre: the colour carries the value.
DIVERGING_STRENGTH = 0.95
#: Context fibres: thin, grey, faint and additive. They must never occlude: a dithered,
#: partly opaque context stacked into a grey veil that cut the network into dashes.
CONTEXT_RADIUS, CONTEXT_COLOUR, CONTEXT_STRENGTH = 0.05, (0.6, 0.64, 0.72), 0.006
#: The TI_max iso-shell: a faint warm rim, so the hotspot reads behind the fibres.
SHELL_COLOUR, SHELL_STRENGTH = (1.0, 0.66, 0.36), 0.05
#: Frames a turntable crossfade from direction colours to the scalar metric takes.
CROSSFADE_FRAMES = 48
#: Glass brain rim emission (lighter than the scalp's ghost would make it).
GLASS_STRENGTH = 0.055
TEXT_GREY = 0.85
CHANNEL_COLOURS = (
    (0.25, 0.75, 1.0),
    (0.35, 0.95, 0.45),
    (1.0, 0.55, 0.2),
    (0.85, 0.4, 1.0),
)
GLASS_COLOUR = (0.55, 0.68, 0.9)
REGION_COLOUR = (1.0, 0.62, 0.28)
ROI_COLOUR = (0.2, 0.95, 0.85)
VIDEO_SIZE = (1920, 1080)
CAPTION_4D = (
    "Fronts run from each fibre's field maximum to both ends; brightness = that fibre's peak "
    "TI envelope along the fibre.\nA depiction of where the stimulated fibres project, not a "
    "model of evoked activity."
)


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# ── scene primitives ─────────────────────────────────────────────────────────


def _mesh_object(name, vertices, *, edges=(), faces=(), attributes=None):
    import bpy

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        np.asarray(vertices, dtype=np.float64), np.asarray(edges), np.asarray(faces)
    )
    for key, values in (attributes or {}).items():
        values = np.asarray(values, dtype=np.float32)
        if values.ndim == 1:
            mesh.attributes.new(key, "FLOAT", "POINT").data.foreach_set("value", values)
        else:
            mesh.attributes.new(key, "FLOAT_VECTOR", "POINT").data.foreach_set(
                "vector", values.ravel()
            )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _tube_modifier(obj, material, resolution: int = 6) -> None:
    import bpy

    tree = bpy.data.node_groups.new("TractTubes", "GeometryNodeTree")
    tree.interface.new_socket(
        "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
    )
    tree.interface.new_socket(
        "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    n, link = tree.nodes, tree.links.new
    group_in, group_out = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    to_curve = n.new("GeometryNodeMeshToCurve")
    radius = n.new("GeometryNodeSetCurveRadius")
    r = n.new("GeometryNodeInputNamedAttribute")
    r.data_type = "FLOAT"
    r.inputs["Name"].default_value = "r"
    profile = n.new("GeometryNodeCurvePrimitiveCircle")
    profile.inputs["Resolution"].default_value = resolution
    profile.inputs["Radius"].default_value = 1.0
    sweep = n.new("GeometryNodeCurveToMesh")
    # The swept mesh carries no material slot of its own; without this it renders black.
    paint = n.new("GeometryNodeSetMaterial")
    paint.inputs["Material"].default_value = material
    link(group_in.outputs[0], to_curve.inputs["Mesh"])
    link(to_curve.outputs["Curve"], radius.inputs["Curve"])
    link(r.outputs["Attribute"], radius.inputs["Radius"])
    link(radius.outputs["Curve"], sweep.inputs["Curve"])
    link(profile.outputs["Curve"], sweep.inputs["Profile Curve"])
    sweep.inputs["Fill Caps"].default_value = True  # open ends read as rings end-on
    scale = sweep.inputs.get("Scale")
    if scale is not None:  # 5.x scales the profile by this input, not the curve radius
        link(r.outputs["Attribute"], scale)
    link(sweep.outputs["Mesh"], paint.inputs["Geometry"])
    link(paint.outputs["Geometry"], group_out.inputs[0])
    obj.modifiers.new("Tubes", "NODES").node_group = tree


class _Nodes:
    """Terse shader-node building: ``m = _Nodes(material)``, then ``m.math("ADD", a, b)``."""

    def __init__(self, material):
        material.use_nodes = True
        self.tree = material.node_tree
        self.tree.nodes.clear()
        self.out = self.tree.nodes.new("ShaderNodeOutputMaterial")

    def new(self, kind, **props):
        node = self.tree.nodes.new(kind)
        for key, value in props.items():
            setattr(node, key, value)
        return node

    def feed(self, socket, value):
        if isinstance(value, (int, float)):
            socket.default_value = value
        else:
            self.tree.links.new(value, socket)

    def attr(self, name, output="Fac"):
        return self.new("ShaderNodeAttribute", attribute_name=name).outputs[output]

    def value(self, v=0.0):
        node = self.new("ShaderNodeValue")
        node.outputs[0].default_value = v
        return node

    def math(self, op, a, b=0.0, c=None, clamp=False):
        node = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, x in enumerate((a, b) if c is None else (a, b, c)):
            self.feed(node.inputs[i], x)
        return node.outputs[0]

    def emission(self, colour, strength):
        node = self.new("ShaderNodeEmission")
        if isinstance(colour, tuple):
            node.inputs["Color"].default_value = (*colour, 1.0)
        else:
            self.feed(node.inputs["Color"], colour)
        self.feed(node.inputs["Strength"], strength)
        return node.outputs[0]

    def add(self, a, b):
        node = self.new("ShaderNodeAddShader")
        self.feed(node.inputs[0], a)
        self.feed(node.inputs[1], b)
        return node.outputs[0]

    def transparent(self):
        return self.new("ShaderNodeBsdfTransparent").outputs[0]

    def finish(self, shader):
        self.feed(self.out.inputs["Surface"], shader)


def _ramp(m: _Nodes, v, stops):
    node = m.new("ShaderNodeValToRGB")
    elements = node.color_ramp.elements
    while len(elements) < len(stops):
        elements.new(0.5)
    for i, (element, colour) in enumerate(zip(elements, stops)):
        element.position = i / (len(stops) - 1)
        element.color = (*(_srgb_to_linear(c) for c in colour), 1.0)
    m.feed(node.inputs["Fac"], v)
    return node.outputs["Color"]


def _keyed(socket, keys) -> None:
    """Key *socket*'s value at each ``(frame, value)`` (linear between, held outside)."""
    for frame, value in keys:
        socket.default_value = float(value)
        socket.keyframe_insert("default_value", frame=int(frame))


def _fade(m: _Nodes, keys):
    """A Value socket following *keys*, or the constant 1 when there are none."""
    node = m.value(1.0)
    if keys:
        _keyed(node.outputs[0], keys)
    return node.outputs[0]


def _fibre_colour_strength(m: _Nodes, manifest, v, metric: str | None = None):
    """(colour, strength) of a fibre at normalised field socket *v* (shared with the bar)."""
    metric = metric or manifest["metric"]
    if metric == "direction":
        colour = m.new("ShaderNodeVectorMath", operation="ABSOLUTE")
        m.feed(colour.inputs[0], m.attr("tangent", "Vector"))
        # |t| is the display (sRGB) value, as in DEC maps; squaring approximates the
        # sRGB-to-linear step emission needs, else 0.5 shows as 0.73 and colours wash out.
        square = m.new("ShaderNodeVectorMath", operation="MULTIPLY")
        m.feed(square.inputs[0], colour.outputs[0])
        m.feed(square.inputs[1], colour.outputs[0])
        colour = square.outputs[0]
    else:
        colour = _ramp(m, v, manifest["stops"])
    if manifest.get("diverging") or metric == "direction":
        return colour, DIVERGING_STRENGTH
    base = m.math("MULTIPLY_ADD", m.math("POWER", v, GAMMA), 1.0 - LOW, LOW)
    boost = m.math("MULTIPLY_ADD", m.math("POWER", v, 3.0), BOOST, 1.0)
    return colour, m.math("MULTIPLY", base, boost)


def _keyed_frame(m: _Nodes, last: int):
    """A Value socket equal to the current frame (two linear keys, frame 1 and *last*)."""
    node = m.value(1.0)
    socket = node.outputs[0]
    for frame in (1, last):
        socket.default_value = float(frame)
        socket.keyframe_insert("default_value", frame=frame)
    return socket


def fibre_material(
    manifest,
    *,
    animated: bool = False,
    name: str = "Fibres",
    metric: str | None = None,
    crossfade=None,
    fade=None,
):
    """Fibre (or colour-bar) emission.

    *crossfade* keys a mix from direction colours (0) to the manifest's metric (1); *fade*
    keys the whole material's strength over transparency (a colour bar that fades out).
    """
    import bpy

    mat = bpy.data.materials.new(name)
    m = _Nodes(mat)
    v = m.attr("v")
    colour, strength = _fibre_colour_strength(m, manifest, v, metric)

    finish = m.finish  # opaque everywhere: a fibre is one continuous tube

    if not animated:
        shader = m.emission(colour, strength)
        if crossfade:
            arrows, power = _fibre_colour_strength(m, manifest, v, "direction")
            mix = m.new("ShaderNodeMixShader")
            m.feed(mix.inputs[0], _fade(m, crossfade))
            m.feed(mix.inputs[1], m.emission(arrows, power))
            m.feed(mix.inputs[2], shader)
            shader = mix.outputs[0]
        if fade:
            mat.surface_render_method = "BLENDED"
            shader = m.add(
                m.transparent(),
                m.emission(colour, m.math("MULTIPLY", strength, _fade(m, fade))),
            )
        finish(shader)
        return mat
    front = manifest["front"]
    frame = _keyed_frame(m, front["frames"])
    reach = m.math(
        "MULTIPLY", m.math("SUBTRACT", frame, front["start"]), front["speed"]
    )
    d = m.attr("d")
    # Cubed: in a whole-brain tractogram most fibres carry a fair peak, and a linear gain lit
    # them all (sub-CHN left_insula_mean flooded white); the cube keeps the strongest apart.
    gain = m.math("POWER", m.attr("gain"), 3.0)
    x = m.math("DIVIDE", m.math("SUBTRACT", d, reach), 5.0)
    glow = m.math(
        "MULTIPLY",
        m.math("EXPONENT", m.math("MULTIPLY", m.math("MULTIPLY", x, x), -1.0)),
        gain,
    )
    trail = m.math("MULTIPLY", m.math("LESS_THAN", d, reach), gain)
    lit = m.math("MULTIPLY_ADD", trail, 0.55, m.math("MULTIPLY", glow, 1.6))
    resting = m.math("MULTIPLY", strength, 0.3)
    finish(
        m.add(
            m.emission(colour, m.math("MULTIPLY_ADD", lit, strength, resting)),
            m.emission(
                (1.0, 0.93, 0.8),
                m.math("MULTIPLY", glow, 0.45),
            ),
        )
    )
    return mat


def glass_material(
    name,
    colour,
    strength,
    power,
    *,
    region_frames: int | None = None,
    regions: bool = False,
):
    """Facing-ratio emission over transparency, with lit region patches when *regions*.

    The ``lit`` attribute sets each patch's brightness; with *region_frames* a patch lights
    when the frame passes its ``frame`` attribute, otherwise it is lit throughout.
    """
    import bpy

    mat = bpy.data.materials.new(name)
    mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = False
    m = _Nodes(mat)
    facing = m.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.5
    rim = m.math("POWER", facing.outputs["Facing"], power)
    shader = m.add(
        m.transparent(), m.emission(colour, m.math("MULTIPLY", rim, strength))
    )
    if regions or region_frames:
        lit = m.attr("lit")
        if region_frames:
            frame = _keyed_frame(m, region_frames)
            on = m.math(
                "DIVIDE", m.math("SUBTRACT", frame, m.attr("frame")), 8.0, clamp=True
            )
            lit = m.math("MULTIPLY", on, lit)
        # Brightest where the surface faces away (rim), so a patch reads as cortex, not a decal.
        glow = m.math("MULTIPLY", lit, m.math("MULTIPLY_ADD", rim, 0.45, 0.1))
        shader = m.add(shader, m.emission(REGION_COLOUR, glow))
    m.finish(shader)
    return mat


def _context_material():
    """Faint grey light added over the scene: the rest of the tractogram, hiding nothing."""
    import bpy

    mat = bpy.data.materials.new("Context")
    mat.surface_render_method = "BLENDED"
    m = _Nodes(mat)
    m.finish(m.add(m.transparent(), m.emission(CONTEXT_COLOUR, CONTEXT_STRENGTH)))
    return mat


def place_labels(
    scene, camera, overlay, labels, hh: float, material, *, edge: float = 0.45
) -> None:
    """Region names at their centroids' projections onto *camera* (overlay coordinates).

    Text sits right of its point, or left of it beyond *edge* (toward the colour bar), on a
    dark translucent plate so it reads over bright fibres; a small white dot in 3-D marks the
    point itself. Labels within a line of each other are pushed apart vertically.
    """
    import bpy
    from mathutils import Vector

    for obj in [o for o in overlay.children if o.name.startswith("RegionLabel")]:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    size = 0.026 * hh * 2
    spots = []
    half = (
        camera.data.ortho_scale / 2
    )  # stills are orthographic: overlay units = local / half
    to_camera = camera.matrix_world.inverted()
    for label in labels:
        local = to_camera @ Vector(label["xyz"])
        spots.append([local.x / half, local.y / half, label["name"]])
    spots.sort(key=lambda spot: -spot[1])
    for above, below in zip(spots, spots[1:]):
        if above[1] - below[1] < 1.5 * size:
            below[1] = above[1] - 1.5 * size
    plate = bpy.data.materials.get("RegionLabelPlate") or _plate_material()
    for i, (ox, oy, name) in enumerate(spots):
        # Flip left of the point when the text (~0.5 em per glyph) would reach the colour bar.
        right = ox > edge or ox + 0.012 + 0.5 * size * len(name) > 0.82
        text = _text(
            f"RegionLabel{i}",
            name,
            size,
            (ox - 0.012 if right else ox + 0.012, oy - 0.008, 0.0),
            overlay,
            align="RIGHT" if right else "LEFT",
            material=material,
        )
        bpy.context.view_layer.update()
        width = text.dimensions.x / max(overlay.scale.x, 1e-9)
        x0 = text.location.x - width if right else text.location.x
        pad = 0.25 * size
        box = _mesh_object(
            f"RegionLabelPlate{i}",
            [
                (x0 - pad, oy - 0.008 - pad, -0.002),
                (x0 + width + pad, oy - 0.008 - pad, -0.002),
                (x0 + width + pad, oy - 0.008 + size, -0.002),
                (x0 - pad, oy - 0.008 + size, -0.002),
            ],
            faces=[(0, 1, 2, 3)],
        )
        box.parent = overlay
        box.data.materials.append(plate)


def _plate_material():
    import bpy

    mat = bpy.data.materials.new("RegionLabelPlate")
    mat.surface_render_method = "BLENDED"
    m = _Nodes(mat)
    mix = m.new("ShaderNodeMixShader")
    m.feed(mix.inputs[0], 0.6)
    m.feed(mix.inputs[1], m.transparent())
    m.feed(mix.inputs[2], m.emission((0.0, 0.0, 0.0), 0.0))
    m.finish(mix.outputs[0])
    return mat


def fading_material(name, colour, strength, keys):
    """Emission over transparency whose strength follows *keys* (text that fades in or out)."""
    import bpy

    if not keys:
        return flat_material(name, colour, strength)
    mat = bpy.data.materials.new(name)
    mat.surface_render_method = "BLENDED"
    m = _Nodes(mat)
    m.finish(
        m.add(
            m.transparent(),
            m.emission(colour, m.math("MULTIPLY", _fade(m, keys), strength)),
        )
    )
    return mat


def flat_material(name, colour, strength=1.0):
    import bpy

    mat = bpy.data.materials.new(name)
    m = _Nodes(mat)
    m.finish(m.emission(colour, strength))
    return mat


def _text(name, body, size, location, parent, *, align="LEFT", material):
    import bpy

    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align
    curve.materials.append(material)
    obj = bpy.data.objects.new(name, curve)
    obj.parent = parent
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _two_lines(text: str) -> str:
    """*text* broken at the space nearest its middle."""
    spaces = [i for i, c in enumerate(text) if c == " "]
    if not spaces:
        return text
    cut = min(spaces, key=lambda i: abs(i - len(text) / 2))
    return text[:cut] + "\n" + text[cut + 1 :]


def _legend(
    root, manifest, metric: str, hh: float, size: float, keys=None, tag: str = ""
):
    """The colour key of *metric* at the right edge: a bar with ticks, or the direction key.

    With *keys* every part fades by them (a turntable crossfade swaps two legends).
    """
    text = fading_material(f"LegendText{tag}", (TEXT_GREY,) * 3, 1.0, keys)
    x0, x1, y0, y1 = 0.885, 0.91, -0.42 * hh, 0.42 * hh
    if metric == "direction":
        _text(
            f"BarTitle{tag}",
            "Fibre direction",
            size * 0.8,
            (0.97, 0.22 * hh + 1.6 * size, 0),
            root,
            align="RIGHT",
            material=text,
        )
        rows = (
            ((1, 0, 0), "left – right"),
            ((0, 1, 0), "anterior – posterior"),
            ((0, 0, 1), "superior – inferior"),
        )
        for i, (colour, words) in enumerate(rows):
            y = 0.22 * hh - i * 1.5 * size
            swatch = _mesh_object(
                f"Swatch{tag}{i}",
                [
                    (0.94, y, 0),
                    (0.97, y, 0),
                    (0.97, y + 0.8 * size, 0),
                    (0.94, y + 0.8 * size, 0),
                ],
                faces=[(0, 1, 2, 3)],
            )
            swatch.parent = root
            swatch.data.materials.append(
                fading_material(f"Swatch{tag}{i}", colour, 0.95, keys)
            )
            _text(
                f"Swatch{tag}{i}Text",
                words,
                size * 0.72,
                (0.93, y + 0.1 * size, 0),
                root,
                align="RIGHT",
                material=text,
            )
        return
    bar = _mesh_object(
        f"ColourBar{tag}",
        [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)],
        faces=[(0, 1, 2, 3)],
        attributes={"v": [0, 0, 1, 1]},
    )
    bar.parent = root
    bar.data.materials.append(
        fibre_material(
            manifest, name=f"ColourBarMaterial{tag}", metric=metric, fade=keys
        )
    )
    ticks = manifest.get("ticks") or [
        [f, f"{f * manifest['vmax']:.2f}"] for f in (0.0, 0.5, 1.0)
    ]
    for frac, tick in ticks:
        y = y0 + frac * (y1 - y0) - 0.35 * size
        _text(
            f"Tick{tag}{frac}",
            tick,
            size * 0.8,
            (x0 - 0.012, y, 0),
            root,
            align="RIGHT",
            material=text,
        )
    units = f" ({manifest['units']})" if manifest["units"] not in ("", "1") else ""
    _text(
        f"BarTitle{tag}",
        _two_lines(manifest["label"] + units),
        size * 0.8,
        (x1, y1 + 1.9 * size, 0),
        root,
        align="RIGHT",
        material=text,
    )
    if manifest.get(
        "network"
    ):  # in network captions the smoothing note sits with the bar
        _text(
            f"BarNote{tag}",
            _two_lines(manifest.get("smoothing_note", "")),
            size * 0.55,
            (x1, y0 - 1.6 * size, 0),
            root,
            align="RIGHT",
            material=text,
        )


def build_overlay(manifest, camera, *, caption: str, distance: float, swap=None):
    """Colour key, title and caption in camera space; returns its root empty.

    Built at half-width 1 (x right, y up); :func:`fit_overlay` scales it to a camera. A
    manifest with ``"bare": true`` gets only the root (region labels still hang from it).
    *swap* = ``(out_keys, in_keys)`` crossfades the direction key out and the metric's in.
    """
    import bpy

    root = bpy.data.objects.new("Overlay", None)
    bpy.context.scene.collection.objects.link(root)
    root.parent = camera
    root.location = (0.0, 0.0, -distance)
    text = flat_material("OverlayText", (TEXT_GREY,) * 3, 1.0)
    w, h = manifest["still_size"] if camera.data.type == "ORTHO" else VIDEO_SIZE
    hh = h / w
    size = 0.034 * hh * 2
    if manifest.get(
        "bare"
    ):  # a panel for a composed figure: it brings its own bar and text
        return root
    if swap:
        _legend(root, manifest, "direction", hh, size, swap[0], tag="Out")
        _legend(root, manifest, manifest["metric"], hh, size, swap[1], tag="In")
    else:
        _legend(root, manifest, manifest["metric"], hh, size)
    _text(
        "Title",
        manifest["title"],
        size,
        (-0.96, hh - 1.6 * size, 0),
        root,
        material=text,
    )
    if caption:
        lines = caption.count("\n") + 1
        scale = 0.7 if manifest.get("network") else 0.62
        _text(
            "Caption",
            caption,
            size * scale,
            (-0.96, -hh + 0.04 + 1.2 * scale * size * (lines - 1), 0),
            root,
            material=text,
        )
    return root


def fit_overlay(root, camera, distance: float) -> None:
    """Scale the unit overlay to the camera's visible half-width at *distance*."""
    data = camera.data
    half = (
        data.ortho_scale / 2
        if data.type == "ORTHO"
        else distance * data.sensor_width / 2 / data.lens
    )
    root.scale = (half, half, half)


# ── framing ──────────────────────────────────────────────────────────────────


def _basis(direction, up):
    from mathutils import Vector

    forward = -Vector(direction).normalized()  # camera looks along -direction
    right = forward.cross(Vector(up)).normalized()
    return forward, right, right.cross(forward)


def aim_ortho(camera, cloud: np.ndarray, direction, up, size, *, bar: bool) -> None:
    """Orthographic camera along *direction* fitting *cloud*, leaving room for the bar."""
    from mathutils import Vector

    forward, right, true_up = _basis(direction, up)
    xs, ys = cloud @ np.asarray(right), cloud @ np.asarray(true_up)
    w, h = size
    usable = 0.80 if bar else 0.94
    scale = max(np.ptp(xs) / usable, np.ptp(ys) * w / h / 0.84)
    centre_x = (xs.max() + xs.min()) / 2 + (0.5 - usable / 2 - 0.02) * scale * (
        1 if bar else 0
    )
    centre_y = (ys.max() + ys.min()) / 2 - 0.015 * scale * h / w
    zs = cloud @ np.asarray(forward)
    target = (
        Vector(right) * centre_x
        + Vector(true_up) * centre_y
        + Vector(forward) * zs.mean()
    )
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = scale
    camera.location = target - Vector(forward) * (np.ptp(zs) + 400.0)
    camera.rotation_euler = _look_rotation(forward, true_up)


def _look_rotation(forward, up):
    from mathutils import Matrix

    z = -forward
    x = up.cross(z).normalized()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed().to_euler()


def perspective_rig(cloud: np.ndarray, direction, up, lens: float = 50.0):
    """Camera on a pivot at the cloud's centre, distance fitting its bounding sphere."""
    import bpy
    from mathutils import Vector

    centre = (cloud.max(0) + cloud.min(0)) / 2
    radius = float(np.linalg.norm(cloud - centre, axis=1).max()) * 1.12
    pivot = bpy.data.objects.new("Pivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = Vector(centre)
    camera = bpy.data.objects.new("VideoCamera", bpy.data.cameras.new("VideoCamera"))
    bpy.context.scene.collection.objects.link(camera)
    camera.data.lens = lens
    camera.data.clip_start, camera.data.clip_end = 1.0, 5000.0
    half_v = math.atan(
        camera.data.sensor_width * VIDEO_SIZE[1] / VIDEO_SIZE[0] / 2 / lens
    )
    forward, _right, true_up = _basis(direction, up)
    camera.parent = pivot
    camera.location = -forward * (radius * 0.98 / math.tan(half_v))
    camera.rotation_euler = _look_rotation(forward, true_up)
    return pivot, camera


# ── render settings ──────────────────────────────────────────────────────────


def configure(scene, size, samples: int) -> None:
    import bpy

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"  # 4.2 - 4.5
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"  # 5.x
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = samples
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0, 0, 0, 1)
    background.inputs["Strength"].default_value = 0.0
    _bloom(scene)


def _bloom(scene) -> None:
    """Compositor Glare (Bloom) on emission above 1; tree API differs in 4.x and 5.x."""
    import bpy

    if hasattr(scene, "compositing_node_group"):  # 5.x
        tree = bpy.data.node_groups.new("Glow", "CompositorNodeTree")
        tree.interface.new_socket(
            "Image", in_out="OUTPUT", socket_type="NodeSocketColor"
        )
        scene.compositing_node_group = tree
        out = tree.nodes.new("NodeGroupOutput")
    else:
        scene.use_nodes = True
        tree = scene.node_tree
        tree.nodes.clear()
        out = tree.nodes.new("CompositorNodeComposite")
    layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    settings = {
        "glare_type": "BLOOM",
        "quality": "HIGH",
        "threshold": 1.0,
        "size": 7,
        "mix": 0.0,
    }
    for key, value in settings.items():
        if hasattr(glare, key):
            setattr(glare, key, value)
    for key, value in (
        ("Type", "Bloom"),
        ("Quality", "High"),
        ("Threshold", 1.0),
        ("Size", 0.6),
        ("Strength", 1.0),
    ):
        socket = glare.inputs.get(key)
        if socket is not None:
            socket.default_value = value
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], out.inputs[0])


def video_output(scene, path_stem: str) -> None:
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):  # 5.x splits images from video
        settings.media_type = "VIDEO"
    settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.fps = 24
    scene.render.filepath = path_stem


def _render_movie(scene, out_dir: str, name: str) -> str:
    import bpy

    stem = os.path.join(out_dir, f".{name}_")
    video_output(scene, stem)
    bpy.ops.render.render(animation=True)
    produced = [
        f
        for f in os.listdir(out_dir)
        if f.startswith(f".{name}_") and f.endswith(".mp4")
    ]
    if not produced:
        raise RuntimeError(f"Blender wrote no movie for {name}")
    final = os.path.join(out_dir, f"{name}.mp4")
    os.replace(os.path.join(out_dir, produced[0]), final)
    return final


# ── scene ────────────────────────────────────────────────────────────────────


def build_scene(manifest, base: str, *, animated: bool, crossfade=None):
    """Fibres, glass brain, scalp, electrodes, ROI.

    Returns the brain's vertices (what a video orbits) and those plus the cranium (what a
    still frames).
    """
    import bpy
    from mathutils import Vector

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for block in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.cameras,
        bpy.data.node_groups,
    ):
        for item in list(block):
            block.remove(item)

    with np.load(os.path.join(base, manifest["tracts"])) as t:
        points, offsets = t["points"], t["offsets"]
        starts, ends = offsets[:-1], offsets[1:]
        mask = np.ones(len(points) - 1, dtype=bool)
        mask[ends[:-1] - 1] = (
            False  # no edge from one streamline's last point to the next
        )
        edges = np.stack([np.arange(len(points) - 1), np.arange(1, len(points))], 1)[
            mask
        ]
        v = t["v"]
        fibres = _mesh_object(
            "Fibres",
            points,
            edges=edges,
            attributes={
                "v": v,
                "r": t["r"] if "r" in t.files else np.full(len(v), 0.2, np.float32),
                "d": t["d"],
                "gain": t["gain"],
                "tangent": t["tangent"],
            },
        )
    _tube_modifier(
        fibres, fibre_material(manifest, animated=animated, crossfade=crossfade)
    )
    if manifest.get("context"):
        with np.load(os.path.join(base, manifest["context"])) as c:
            cp, co = c["points"], c["offsets"]
        keep = np.ones(len(cp) - 1, dtype=bool)
        keep[co[1:-1] - 1] = False
        pairs = np.stack([np.arange(len(cp) - 1), np.arange(1, len(cp))], 1)[keep]
        context = _mesh_object(
            "Context",
            cp,
            edges=pairs,
            attributes={"r": np.full(len(cp), CONTEXT_RADIUS)},
        )
        _tube_modifier(context, _context_material(), resolution=4)

    with np.load(os.path.join(base, manifest["glass"])) as g:
        glass_v = g["vertices"]
        brain = _mesh_object(
            "GlassBrain",
            glass_v,
            faces=g["triangles"],
            attributes={"frame": g["frame"], "lit": g["lit"]},
        )
    region_frames = manifest["front"]["frames"] if animated else None
    brain.data.materials.append(
        glass_material(
            "Glass",
            GLASS_COLOUR,
            GLASS_STRENGTH,
            2.6,
            region_frames=region_frames,
            regions=True,
        )
    )
    if manifest.get("regions"):
        with np.load(os.path.join(base, manifest["regions"])) as r:
            deep = _mesh_object(
                "DeepRegions",
                r["vertices"],
                faces=r["triangles"],
                attributes={"frame": r["frame"], "lit": r["lit"]},
            )
        deep.data.materials.append(
            glass_material(
                "DeepRegion",
                REGION_COLOUR,
                0.12,
                1.5,
                region_frames=region_frames,
                regions=True,
            )
        )
    if manifest.get("shell"):
        with np.load(os.path.join(base, manifest["shell"])) as sh:
            shell = _mesh_object("TIShell", sh["vertices"], faces=sh["triangles"])
        shell.data.polygons.foreach_set("use_smooth", [True] * len(shell.data.polygons))
        shell.data.materials.append(
            glass_material("TIShell", SHELL_COLOUR, SHELL_STRENGTH, 1.4)
        )
    if manifest.get("scalp"):
        with np.load(os.path.join(base, manifest["scalp"])) as s:
            scalp = _mesh_object("Scalp", s["vertices"], faces=s["triangles"])
            centre = s["vertices"].mean(0)
            # Frame the cranium, not the neck: a ghost cut by the frame edge reads as a crop.
            frame_cloud = s["vertices"][
                s["vertices"][:, 2] > glass_v[:, 2].min() - 10.0
            ]
        scalp.data.materials.append(
            glass_material("ScalpGhost", (0.8, 0.72, 0.65), 0.035, 4.0)
        )
    else:
        centre, frame_cloud = glass_v.mean(0), glass_v[:0]
    for i, electrode in enumerate(manifest["electrodes"]):
        position = Vector(electrode["xyz"])
        normal = (position - Vector(centre)).normalized()
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=40, radius=3.5, depth=1.0, location=position + normal * 0.5
        )
        disc = bpy.context.active_object
        disc.name = f"Electrode_{electrode['name']}"
        disc.rotation_euler = Vector((0, 0, 1)).rotation_difference(normal).to_euler()
        colour = CHANNEL_COLOURS[electrode["channel"] % len(CHANNEL_COLOURS)]
        mat = flat_material(f"Electrode{i}", colour, 0.9)
        disc.data.materials.append(mat)
        if animated:  # a carrier pulse before the fronts leave
            socket = mat.node_tree.nodes["Emission"].inputs["Strength"]
            for frame, value in (
                (1, 0.9),
                (6, 3.0),
                (12, 0.9),
                (manifest["front"]["start"], 2.0),
                (manifest["front"]["start"] + 8, 0.9),
            ):
                socket.default_value = value
                socket.keyframe_insert("default_value", frame=frame)
    for i, label in enumerate(manifest.get("labels") or []):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=16, ring_count=8, radius=1.4, location=label["xyz"]
        )
        bpy.context.active_object.name = f"RegionPoint{i}"
        bpy.context.active_object.data.materials.append(
            flat_material(f"RegionPoint{i}", (1, 1, 1), 1.0)
        )
    if manifest.get("roi"):
        roi = manifest["roi"]
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=48, ring_count=24, radius=roi["radius"], location=roi["center"]
        )
        bpy.context.active_object.data.materials.append(
            glass_material("ROI", ROI_COLOUR, 0.9, 1.6)
        )
    return glass_v, np.concatenate([glass_v, frame_cloud])


def render_stills(manifest, base, out_dir) -> list[str]:
    import bpy

    scene = bpy.context.scene
    size = manifest["still_size"]
    configure(
        scene, size, samples=32
    )  # 32: smooth dithering; 48 took 15 min/still emulated
    _brain, cloud = build_scene(manifest, base, animated=False)
    camera = bpy.data.objects.new("StillCamera", bpy.data.cameras.new("StillCamera"))
    scene.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.clip_start, camera.data.clip_end = 1.0, 5000.0
    scene.camera = camera
    shown = manifest.get("caption") or (
        f"{manifest['n_shown']:,} of {manifest['n_total']:,} streamlines · colour averaged "
        f"along each fibre over ±{manifest.get('smoothing_mm', 0):g} mm"
    )
    overlay = build_overlay(manifest, camera, caption=shown, distance=10.0)
    label_material = flat_material("RegionLabelText", (1.0, 0.86, 0.7), 1.0)
    side = manifest["lateral_side"]
    views = {
        "lateral": ((side, 0.0, 0.0), (0, 0, 1)),
        "superior": ((0.0, 0.0, 1.0), (0, 1, 0)),
        "oblique": ((side * 0.78, 0.5, 0.38), (0, 0, 1)),
    }
    if manifest.get("views"):  # a subset, e.g. one quick check view
        views = {k: views[k] for k in manifest["views"]}
    written = []
    for view, (direction, up) in views.items():
        aim_ortho(
            camera,
            cloud,
            direction,
            up,
            size,
            bar=not manifest.get("bare"),  # the direction key needs the column too
        )
        fit_overlay(overlay, camera, 10.0)
        place_labels(
            scene,
            camera,
            overlay,
            manifest.get("labels") or [],
            size[1] / size[0],
            label_material,
            edge=0.62 if manifest.get("bare") else 0.45,
        )
        scene.render.filepath = os.path.join(out_dir, f"{manifest['stem']}_{view}.png")
        scene.render.image_settings.file_format = "PNG"
        started = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"rendered {view} in {time.time() - started:.1f} s", flush=True)
        written.append(scene.render.filepath)
    return written


def render_turntable(manifest, base, out_dir) -> str:
    import bpy

    scene = bpy.context.scene
    configure(scene, VIDEO_SIZE, samples=16)
    n, degrees = manifest["turntable_frames"], manifest["turntable_degrees"]
    swap = crossfade = None
    if manifest.get("crossfade"):  # direction for the first half, then the metric
        a, b = n // 2 - CROSSFADE_FRAMES // 2, n // 2 + CROSSFADE_FRAMES // 2
        crossfade = [(a, 0.0), (b, 1.0)]
        # The keys share one place: the direction key leaves before the colour bar arrives.
        mid = (a + b) // 2
        swap = ([(a, 1.0), (mid, 0.0)], [(mid, 0.0), (b, 1.0)])
    cloud, _head = build_scene(manifest, base, animated=False, crossfade=crossfade)
    side = manifest["lateral_side"]
    pivot, camera = perspective_rig(cloud, (side * 0.9, 0.15, 0.32), (0, 0, 1))
    scene.camera = camera
    overlay = build_overlay(
        manifest, camera, caption=manifest.get("caption", ""), distance=60.0, swap=swap
    )
    fit_overlay(overlay, camera, 60.0)
    scene.frame_start, scene.frame_end = 1, n
    step = math.radians(degrees) / (
        n if degrees >= 360 else n - 1
    )  # a full loop never repeats
    for frame in (1, n):
        pivot.rotation_euler = (0.0, 0.0, step * (frame - 1))
        pivot.keyframe_insert("rotation_euler", frame=frame)
    return _render_movie(scene, out_dir, f"{manifest['stem']}_turntable")


def render_propagation(manifest, base, out_dir) -> str:
    import bpy

    scene = bpy.context.scene
    configure(scene, VIDEO_SIZE, samples=16)
    cloud, _head = build_scene(manifest, base, animated=True)
    side = manifest["lateral_side"]
    pivot, camera = perspective_rig(cloud, (side * 0.8, 0.45, 0.4), (0, 0, 1))
    scene.camera = camera
    overlay = build_overlay(manifest, camera, caption=CAPTION_4D, distance=60.0)
    fit_overlay(overlay, camera, 60.0)
    n = manifest["front"]["frames"]
    scene.frame_start, scene.frame_end = 1, n
    for frame, angle in (
        (1, -20.0),
        (n, 20.0),
    ):  # a slow drift keeps the depth readable
        pivot.rotation_euler = (0.0, 0.0, math.radians(angle))
        pivot.keyframe_insert("rotation_euler", frame=frame)
    return _render_movie(scene, out_dir, f"{manifest['stem']}_propagation")


def main(argv: list[str]) -> None:
    import bpy

    if not bpy.app.background:
        raise RuntimeError("tract_scene.py renders with blender --background")
    # New keys interpolate linearly: the front and the orbit move at constant speed.
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    manifest_path = os.path.abspath(argv[0])
    base = os.path.dirname(manifest_path)
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    wanted = (
        set(argv[1].split(","))
        if len(argv) > 1
        else {k for k in ("stills", "turntable", "propagation") if manifest[k]}
    )
    out_dir = os.path.normpath(os.path.join(base, manifest["output_dir"]))
    if "stills" in wanted:
        print("\n".join(render_stills(manifest, base, out_dir)), flush=True)
    for kind, run in (
        ("turntable", render_turntable),
        ("propagation", render_propagation),
    ):
        if kind in wanted:
            started = time.time()
            print(
                f"{run(manifest, base, out_dir)} in {time.time() - started:.0f} s",
                flush=True,
            )


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
