#!/usr/bin/env python3
"""Build docs/assets/imgs/eeg-caps/eeg-caps-on-ernie.png: every EEG cap the image ships, on ernie.

1. Warps each MNI cap onto ernie's head with ``tit.caps.warp_caps``, the toolbox's own copy of
   charm's warp. The TI-Toolbox caps come from this checkout's ``resources/ElectrodeCaps_MNI``,
   SimNIBS's own caps from the installed SimNIBS.
2. Checks every warped net with ``tit.caps.net_stats`` and draws nothing if one fails: no two
   electrodes closer than ``COLLAPSE_MM`` (the 10-20 alias pairs such as T3/T7 excepted), no
   repeated label, every electrode within ``SCALP_MAX_MM`` of the scalp. Prints one row per cap
   and writes the rows to ``<work>/net_stats.json``.
3. Draws one panel per cap: ernie's skin surface (Lambert-shaded, one fixed view from the front
   left and above, one scale) with the electrodes that view can see, and Cz (or the electrode
   nearest to it) ringed. The full-resolution skin (about 110 k triangles) draws all panels in
   seconds, so it is not decimated: vertex clustering only added terraces to the shading.

Run in the TI-Toolbox image (needs SimNIBS). Only ``<m2m>/ernie.msh`` and
``<m2m>/toMNI/MNI2Conform_nonl.nii.gz`` are read, and nothing is written to the m2m folder:

    simnibs_python dev/build_eeg_caps_figure.py /path/to/m2m_ernie --work /tmp/caps

Not wired into CI: the PNG is generated offline and committed.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tit.caps import (  # noqa: E402
    SKIN_TAG,
    TIT_CAPS,
    has_electrodes,
    net_points,
    net_stats,
    simnibs_caps_dir,
    warp_caps,
)
from tit.scene.build import parse_electrode_csv  # noqa: E402

DEFAULT_OUT = ROOT / "docs/assets/imgs/eeg-caps/eeg-caps-on-ernie.png"
#: A warped electrode is projected onto the skin, so it lies within a node spacing of a skin node.
SCALP_MAX_MM = 3.0
#: Camera: azimuth from the nose towards the subject's left, elevation above the horizon.
AZIMUTH_DEG = 60.0
ELEVATION_DEG = 45.0
#: An electrode this much deeper than the nearest surface in its 2 mm screen bin is hidden
#: (behind an ear); one on scalp turned this far from the camera (cosine) is not drawn.
OCCLUDE_MM = 8.0
MIN_FACING = 0.1
#: Electrode marker area (pt^2) where the scalp faces the camera; it shrinks towards the outline.
DOT_PT2 = 44.0
#: The toolbox's caps by vendor and size; SimNIBS's follow by electrode count.
ORDER = (
    "GSN-HydroCel-128",
    "GSN-HydroCel-185",
    "GSN-HydroCel-256",
    "BioSemi-64-10-10",
    "BioSemi-128-A1",
    "BioSemi-256-A1",
)
SKIN_RGB = np.array([0.90, 0.885, 0.87])
DOT = "#2E86AB"  # the docs' --color-primary
RING = "#A23B72"  # --color-accent
TEXT = "#16191d"  # --color-heading
MUTED = "#59636e"  # --color-text-muted


def caps_to_draw() -> list[tuple[str, Path]]:
    """``(source, MNI cap)`` for every cap the image ships; the toolbox's from this checkout."""
    ours = ROOT / "resources" / "ElectrodeCaps_MNI"
    caps = [("TI-Toolbox", ours / name) for name in sorted(TIT_CAPS)]
    for path in sorted(simnibs_caps_dir().glob("*.csv"), key=lambda p: p.name.lower()):
        if path.name not in TIT_CAPS and has_electrodes(path):
            caps.append(("SimNIBS", path))
    return caps


def read_skin(mesh_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Skin nodes (mm) and triangles (0-based) of the head mesh, cropped as charm tags it."""
    from simnibs.mesh_tools import mesh_io

    skin = mesh_io.read_msh(str(mesh_path)).crop_mesh(tags=[SKIN_TAG])
    nodes = np.asarray(skin.nodes.node_coord, dtype=np.float64)
    tris = np.asarray(skin.elm.node_number_list[:, :3], dtype=np.int64) - 1
    return nodes, tris


def check_nets(work: Path, caps: list[tuple[str, Path]], skin: np.ndarray) -> list[dict]:
    """Names, positions and ``net_stats`` of each warped net; exits if any net is broken."""
    nets, problems = [], []
    for source, cap in caps:
        text = (work / f"{cap.stem}.csv").read_text(encoding="utf-8")
        names, world = net_points(parse_electrode_csv(text))
        stats = net_stats(names, world, skin)
        s = stats["summary"]
        if stats["collapsed"]:
            problems.append(f"{cap.stem}: {len(stats['collapsed'])} collapsed pairs")
        if stats["duplicate_names"]:
            problems.append(f"{cap.stem}: repeated labels {stats['duplicate_names']}")
        if s["count"] == 0 or s["scalp_max_mm"] > SCALP_MAX_MM:
            problems.append(f"{cap.stem}: an electrode {s['scalp_max_mm']} mm off the scalp")
        nets.append(
            {
                "name": cap.stem,
                "source": source,
                "names": names,
                "world": world,
                "summary": s,
                "aliases": [f"{p['a']}/{p['b']}" for p in stats["aliases"]],
                "collapsed": stats["collapsed"],
            }
        )
    print(f"{'cap':26s} {'source':10s} {'n':>4s} {'nn min':>7s} {'nn med':>7s} "
          f"{'scalp med':>9s} {'scalp max':>9s}  aliases (mm)")
    for net in nets:
        s = net["summary"]
        print(f"{net['name']:26s} {net['source']:10s} {s['count']:4d} {s['nn_min_mm']:7.2f} "
              f"{s['nn_median_mm']:7.2f} {s['scalp_median_mm']:9.3f} {s['scalp_max_mm']:9.3f}  "
              f"{', '.join(net['aliases']) or '-'}")
    rows = [{k: v for k, v in n.items() if k not in ("names", "world")} for n in nets]
    (work / "net_stats.json").write_text(json.dumps(rows, indent=2))
    if problems:
        raise SystemExit("refusing to draw a broken net:\n  " + "\n  ".join(problems))
    return nets


def unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n > 0, n, 1.0)


def camera() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unit vectors towards the camera, screen right and screen up (world +x right, +y nose)."""
    az, el = np.radians(AZIMUTH_DEG), np.radians(ELEVATION_DEG)
    toward = np.array([-np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)])
    right = unit(np.cross([0.0, 0.0, 1.0], toward))
    return toward, right, np.cross(toward, right)


def draw(nets: list[dict], nodes: np.ndarray, tris: np.ndarray, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from PIL import Image
    from scipy.spatial import cKDTree

    toward, right, up = camera()
    center = (nodes.min(axis=0) + nodes.max(axis=0)) / 2
    rel = nodes - center
    u, v, depth = rel @ right, rel @ up, rel @ toward

    # Outward normals (flip the triangles if most point inwards), then smooth vertex normals.
    fn = unit(np.cross(nodes[tris[:, 1]] - nodes[tris[:, 0]], nodes[tris[:, 2]] - nodes[tris[:, 0]]))
    if np.mean(np.einsum("ij,ij->i", fn, rel[tris].mean(axis=1)) > 0) < 0.5:
        tris, fn = tris[:, ::-1], -fn
    vn = np.zeros_like(nodes)
    for i in range(3):
        np.add.at(vn, tris[:, i], fn)
    vn = unit(vn)

    # The scalp: faces turned to the camera, far to near, shaded by their corners' normals.
    front = tris[fn @ toward > 0]
    front = front[np.argsort(depth[front].mean(axis=1))]
    light = unit(toward + 0.55 * up - 0.35 * right)
    shade = 0.62 + 0.38 * np.clip(unit(vn[front].sum(axis=1)) @ light, 0, 1)
    colors = np.clip(SKIN_RGB * shade[:, None], 0, 1)
    polys = np.stack([u[front], v[front]], axis=-1)

    # Depth buffer over 2 mm screen bins, for electrodes hidden behind an ear.
    lo = np.array([u.min(), v.min()])
    zbuf = np.full(np.floor((np.array([u.max(), v.max()]) - lo) / 2.0).astype(int) + 1, -np.inf)
    np.maximum.at(zbuf, tuple(np.floor((np.c_[u, v] - lo) / 2.0).astype(int).T), depth)
    tree = cKDTree(nodes)

    # Cz: each net's own, or its electrode nearest the median Cz of the nets that have one.
    cz = np.median([n["world"][n["names"].index("Cz")] for n in nets if "Cz" in n["names"]], axis=0)

    # Layout in pixels: four panels a row, one scale for every head.
    width_px, dpi, side, cols, pad = 1600, 100, 12, 4, 4.0
    col_w = (width_px - 2 * side) / cols
    mm_px = (col_w - 10) / (u.max() - u.min() + 2 * pad)
    head_h = (v.max() - v.min() + 2 * pad) * mm_px
    title_h, gap = 62, 18
    row_h = title_h + head_h + gap
    height_px = int(round(-(-len(nets) // cols) * row_h + 4))
    fig = plt.figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi, facecolor="white")

    for i, net in enumerate(nets):
        top, x0 = (i // cols) * row_h + 4, side + (i % cols) * col_w
        cx = (x0 + col_w / 2) / width_px
        fig.text(cx, 1 - (top + 24) / height_px, net["name"], fontsize=17, fontweight="bold",
                 color=TEXT, ha="center", va="baseline")
        fig.text(cx, 1 - (top + 51) / height_px,
                 f"{net['summary']['count']} electrodes · {net['source']}",
                 fontsize=15.5, color=MUTED, ha="center", va="baseline")
        ax = fig.add_axes([(x0 + 5) / width_px, 1 - (top + title_h + head_h) / height_px,
                           (col_w - 10) / width_px, head_h / height_px])
        ax.set_xlim(u.min() - pad, u.max() + pad)
        ax.set_ylim(v.min() - pad, v.max() + pad)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.add_collection(PolyCollection(polys, facecolors=colors, edgecolors=colors,
                                         linewidths=0.25))

        world = net["world"]
        facing = vn[tree.query(world)[1]] @ toward
        e = world - center
        ue, ve, de = e @ right, e @ up, e @ toward
        b = np.clip(np.floor((np.c_[ue, ve] - lo) / 2.0).astype(int), 0, np.array(zbuf.shape) - 1)
        seen = (facing > MIN_FACING) & (de >= zbuf[b[:, 0], b[:, 1]] - OCCLUDE_MM)
        idx = np.flatnonzero(seen)[np.argsort(de[seen])]
        ax.scatter(ue[idx], ve[idx], s=DOT_PT2 * (0.45 + 0.55 * facing[idx]), c=DOT,
                   edgecolors="white", linewidths=0.6, zorder=3)
        k = (net["names"].index("Cz") if "Cz" in net["names"]
             else int(np.argmin(np.linalg.norm(world - cz, axis=1))))
        if seen[k]:
            ax.scatter([ue[k]], [ve[k]], s=4.5 * DOT_PT2, facecolors="none", edgecolors=RING,
                       linewidths=2.0, zorder=4)

    fig.canvas.draw()
    rgb = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    # 256 colours keep the page light: the scalp is greys, the marks two hues. Max-coverage
    # keeps the few ring pixels that median-cut merges into grey.
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).quantize(
        256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE
    ).save(out, optimize=True)
    print(f"wrote {out} ({width_px}x{height_px} px, {out.stat().st_size // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("m2m", type=Path, help="ernie's m2m folder (ernie.msh and toMNI/)")
    parser.add_argument("--work", type=Path, help="folder for the warped nets (default: temporary)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="the PNG to write")
    args = parser.parse_args()
    sid = args.m2m.name.removeprefix("m2m_")
    work = args.work or Path(tempfile.mkdtemp(prefix="eeg-caps-"))

    caps = caps_to_draw()
    warp_caps(str(args.m2m), sid, [cap for _, cap in caps], str(work))
    nodes, tris = read_skin(args.m2m / f"{sid}.msh")
    nets = check_nets(work, caps, nodes)
    by_name = {n["name"]: n for n in nets}
    simnibs = sorted((n for n in nets if n["name"] not in ORDER), key=lambda n: n["summary"]["count"])
    draw([by_name[name] for name in ORDER] + simnibs, nodes, tris, args.out)


if __name__ == "__main__":
    main()
