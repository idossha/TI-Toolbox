"""Write desktop/src/renderer/scene/electrodeModel.ts: a light copy of the Blender exporter's electrode.

The 3-D scene draws one instanced copy of this mesh per EEG electrode (~185 per net) and stretches
it to a montage electrode's configured size (up to ~50 mm across), so it has to be both light and
clean under a large non-uniform scale. Its source is the exporter's own model
(``tit/blender/Electrode.blend``, object ``Electrode``, the one ``tit/blender/electrode_placement.py``
places), reduced to its **profile**: the convex hull of its vertices in the (radius, height)
half-plane about its axis, simplified to ``PROFILE_TOLERANCE`` of its radius and revolved in
``SEGMENTS`` steps. A mesh decimator (Blender's collapse) was tried first and rejected: it folded
9 of its 238 triangles over, which a 25x stretch turns into visible creases. Materials and the
cap's shallow relief are not kept: the scene colours each electrode by its channel.

Two layers, told apart by ``layers`` (0 = gel, 1 = pad):

* the **pad** — the revolved profile. Frame: +Z is the electrode's axis (the exporter aligns local
  +Z with the scalp normal), base at z = 0, radius 1, top at ``height``; the renderer scales x/y to
  the configured width/height and z to the rubber thickness, and maps each ring onto a square for a
  rect electrode (``SEGMENTS`` is a multiple of 8, so every ring has vertices on the square's
  corners and side midpoints);
* the **gel** — a slab of radius 1 from z = 0 to z = 1, the same ``SEGMENTS``, with no bottom cap
  (it lies on the skin); the renderer scales z to the gel thickness and stacks the pad on it.

Normals are per corner: smooth around the axis, split along the profile where it turns by more than
``SHARP_DEG``. Numbers are rounded, so the output is byte-deterministic.

Run (Blender 5.1.0 on the maintainer's Mac; any Blender with a Python API works — only the vertex
coordinates are read):

    /Applications/Blender.app/Contents/MacOS/Blender --background tit/blender/Electrode.blend \
        --python dev/export_electrode_model.py -- desktop/src/renderer/scene/electrodeModel.ts

``git diff`` after a re-run should be empty.
"""

from __future__ import annotations

import math
import sys

import bpy

SEGMENTS = 24
PROFILE_TOLERANCE = 0.02
SHARP_DEG = 35.0
OBJECT = "Electrode"


def cross2(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def profile(points):
    """The outer boundary of the (r, z) points' convex hull, from the top of the axis, round the
    rim, to the bottom of the axis."""
    zmax = max(z for _, z in points)
    zmin = min(z for _, z in points)
    pts = sorted(set(points + [(0.0, zmax), (0.0, zmin)]))
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross2(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross2(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    ring = lower[:-1] + upper[:-1]  # counter-clockwise
    ring = ring[ring.index((0.0, zmax)) :] + ring[: ring.index((0.0, zmax))]
    ring.reverse()  # clockwise from the top of the axis: top -> rim -> base ... -> back to top
    ring = [ring[-1]] + ring[:-1] if ring[0] != (0.0, zmax) else ring
    return ring[: ring.index((0.0, zmin)) + 1]


def simplify(poly, tol):
    """Douglas-Peucker."""
    if len(poly) < 3:
        return poly
    (x0, y0), (x1, y1) = poly[0], poly[-1]
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    best, index = 0.0, 0
    for i in range(1, len(poly) - 1):
        d = abs((x1 - x0) * (y0 - poly[i][1]) - (x0 - poly[i][0]) * (y1 - y0)) / length
        if d > best:
            best, index = d, i
    if best <= tol:
        return [poly[0], poly[-1]]
    return simplify(poly[: index + 1], tol)[:-1] + simplify(poly[index:], tol)


def main(out_path: str) -> None:
    mesh = bpy.data.objects[OBJECT].data
    raw = [(math.hypot(v.co.x, v.co.y), v.co.z) for v in mesh.vertices]
    radius = max(r for r, _ in raw)
    zmin = min(z for _, z in raw)
    prof = simplify(
        profile(
            [(round(r / radius, 5), round((z - zmin) / radius, 5)) for r, z in raw]
        ),
        PROFILE_TOLERANCE,
    )
    height = max(z for _, z in prof)

    out_pos: list[float] = []
    out_nrm: list[float] = []
    out_idx: list[int] = []
    out_layer: list[int] = []
    seen: dict[tuple, int] = {}

    def vertex(p, n, layer):
        p = tuple(round(x, 4) + 0.0 for x in p)
        n = tuple(round(x, 3) + 0.0 for x in n)
        key = p + n + (layer,)
        if key not in seen:
            seen[key] = len(out_layer)
            out_pos.extend(p)
            out_nrm.extend(n)
            out_layer.append(layer)
        return seen[key]

    def revolve(poly, layer):
        """One band per profile edge; normals smooth around the axis, split at sharp profile turns."""
        edges = list(zip(poly[:-1], poly[1:]))
        # The profile runs clockwise in (r, z) (top -> rim -> base), so an edge's outward normal is
        # its direction (dr, dz) turned a quarter anticlockwise: (-dz, dr).
        en = []
        for (r0, z0), (r1, z1) in edges:
            length = math.hypot(r1 - r0, z1 - z0) or 1.0
            en.append((-(z1 - z0) / length, (r1 - r0) / length))
        cos_sharp = math.cos(math.radians(SHARP_DEG))

        def end_normal(j, other):
            n = en[j]
            if (
                0 <= other < len(en)
                and en[other][0] * n[0] + en[other][1] * n[1] >= cos_sharp
            ):
                s = (n[0] + en[other][0], n[1] + en[other][1])
                length = math.hypot(*s) or 1.0
                return (s[0] / length, s[1] / length)
            return n

        for j, ((r0, z0), (r1, z1)) in enumerate(edges):
            n0, n1 = end_normal(j, j - 1), end_normal(j, j + 1)
            for k in range(SEGMENTS):
                corners = []
                for r, z, n, step in (
                    (r0, z0, n0, k),
                    (r0, z0, n0, k + 1),
                    (r1, z1, n1, k + 1),
                    (r1, z1, n1, k),
                ):
                    t = 2 * math.pi * step / SEGMENTS
                    c, s = math.cos(t), math.sin(t)
                    corners.append(((r * c, r * s, z), (n[0] * c, n[0] * s, n[1])))
                for tri in ((0, 1, 2), (0, 2, 3)):
                    pts = [corners[i][0] for i in tri]
                    if len({tuple(round(x, 6) for x in p) for p in pts}) < 3:
                        continue  # the fan at the axis: one corner pair coincides
                    for i in tri:
                        out_idx.append(vertex(corners[i][0], corners[i][1], layer))

    revolve(prof, 1)
    pad_triangles = len(out_idx) // 3
    revolve([(0.0, 1.0), (1.0, 1.0), (1.0, 0.0)], 0)  # gel: top cap and wall, no bottom

    fmt = lambda xs: ",".join(f"{x:g}" for x in xs)  # noqa: E731
    text = f"""// GENERATED by dev/export_electrode_model.py from tit/blender/Electrode.blend ({bpy.app.version_string}).
// Do not edit: re-run the script. Frame: +Z is the electrode axis, base at z = 0, max radius 1.
export const ELECTRODE_MODEL = {{
  /** Triangles: {len(out_idx) // 3} — pad {pad_triangles} (the .blend's profile, {len(prof)} points, revolved in {SEGMENTS}), gel {len(out_idx) // 3 - pad_triangles}. */
  height: {height:.4f},
  positions: new Float32Array([{fmt(out_pos)}]),
  normals: new Float32Array([{fmt(out_nrm)}]),
  /** 0 = gel slab, 1 = pad. */
  layers: new Uint8Array([{fmt(out_layer)}]),
  indices: new Uint16Array([{fmt(out_idx)}]),
}};
"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(
        f"electrode model: {len(out_idx) // 3} triangles (pad {pad_triangles}), {len(out_layer)} vertices, profile {prof}, height {height:.4f} -> {out_path}"
    )


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 1:
        raise SystemExit(
            "usage: blender --background Electrode.blend --python export_electrode_model.py -- OUT.ts"
        )
    main(argv[0])
