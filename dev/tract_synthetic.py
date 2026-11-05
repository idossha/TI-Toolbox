#!/usr/bin/env python3
"""Write a synthetic ``tit.tract`` output directory inside a real subject's brain.

A stand-in for the tract pipeline's outputs while it is being built, so the tract visuals can
be developed and tested against the same data contract (``tit/blender/tract_data.py``):

- ``all.trx``: curved bundles between cortical patches of the subject's own central surfaces
  (quadratic Bezier paths through the deep white matter, 1 mm steps), plus unassigned
  context streamlines; ``ti_max`` is a Gaussian hotspot and ``ti_along = ti_max * |t . n|``
  for one fixed field direction ``n``, so ``ti_along <= ti_max`` holds as it must;
- ``edges.json``, ``connectome_ti_along_max.npz`` and ``summary.json`` (``"synthetic": true``).

The TRX is written with the standard library (``zipfile``) straight from the TRX
specification, never with trx-python, so a reader test that loads it with trx-python checks
the reader against an independent writer.

Usage::

    python3 dev/tract_synthetic.py <m2m_dir> <out_dir> [--seed 0] [--hotspot x y z]

Needs numpy and nibabel (for the ``surfaces/{lh,rh}.central.gii`` it reads).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

import numpy as np


def write_trx(
    path: str,
    points: np.ndarray,
    offsets: np.ndarray,
    dpv: dict[str, np.ndarray],
    dps: dict[str, np.ndarray],
) -> None:
    """Write an uncompressed TRX zip: ``header.json``, positions, offsets, dpv/, dps/.

    *offsets* has ``S + 1`` entries (the last is ``NB_VERTICES``), as the file stores them.
    """
    points = np.ascontiguousarray(points, dtype="<f4")
    header = {
        "DIMENSIONS": [256, 256, 256],
        "VOXEL_TO_RASMM": np.eye(4).tolist(),
        "NB_VERTICES": int(len(points)),
        "NB_STREAMLINES": int(len(offsets) - 1),
    }

    def raw(array: np.ndarray, dtype: str) -> bytes:
        return np.ascontiguousarray(array, dtype=dtype).tobytes()

    entries = {
        "header.json": json.dumps(header).encode(),
        "positions.3.float32": raw(points, "<f4"),
        "offsets.uint64": raw(np.asarray(offsets), "<u8"),
    }
    for name, value in dpv.items():
        entries[f"dpv/{name}.float32"] = raw(value, "<f4")
    for name, value in dps.items():
        kind = (
            "int32" if np.issubdtype(np.asarray(value).dtype, np.integer) else "float32"
        )
        entries[f"dps/{name}.{kind}"] = raw(value, "<i4" if kind == "int32" else "<f4")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            archive.writestr(info, payload)


def _read_gifti(path: str) -> np.ndarray:
    import nibabel as nib

    return np.asarray(nib.load(path).darrays[0].data, dtype=np.float64)


def _nearest(points: np.ndarray, cloud: np.ndarray) -> np.ndarray:
    """Index into *cloud* of each point's nearest neighbour (brute force, chunked)."""
    out = np.empty(len(points), dtype=np.int64)
    for start in range(0, len(points), 512):
        block = points[start : start + 512]
        d = ((block[:, None, :] - cloud[None, :, :]) ** 2).sum(-1)
        out[start : start + len(block)] = d.argmin(1)
    return out


def _farthest_points(cloud: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    chosen = [int(rng.integers(len(cloud)))]
    dist = ((cloud - cloud[chosen[0]]) ** 2).sum(1)
    for _ in range(k - 1):
        chosen.append(int(dist.argmax()))
        dist = np.minimum(dist, ((cloud - cloud[chosen[-1]]) ** 2).sum(1))
    return cloud[chosen]


def _bezier(p0, pc, p1, step_mm: float = 1.0) -> np.ndarray:
    t = np.linspace(0.0, 1.0, 400)[:, None]
    curve = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * pc + t**2 * p1
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))]
    target = np.arange(0.0, s[-1], step_mm)
    target = np.r_[target, s[-1]] if s[-1] - target[-1] > 1e-6 else target
    return np.stack([np.interp(target, s, curve[:, c]) for c in range(3)], axis=1)


def generate(
    m2m_dir: str, out_dir: str, *, seed: int = 0, hotspot: np.ndarray | None = None
) -> dict:
    """Write the synthetic tract directory; return ``summary.json``'s content."""
    rng = np.random.default_rng(seed)
    hemis = {
        h: _read_gifti(os.path.join(m2m_dir, "surfaces", f"{h}.central.gii"))
        for h in ("lh", "rh")
    }
    centre = np.concatenate(list(hemis.values())).mean(0)
    sub = {
        h: v[rng.choice(len(v), min(6000, len(v)), replace=False)]
        for h, v in hemis.items()
    }
    regions: dict[str, np.ndarray] = {}
    for h in ("lh", "rh"):
        for i, p in enumerate(_farthest_points(sub[h], 18, rng)):
            regions[f"{h}.region{i + 1:02d}"] = p
    names = list(regions)
    if hotspot is None:  # under the left insula: lateral, slightly anterior, mid-height
        hotspot = sub["lh"][_nearest((centre + [-38.0, 8.0, -2.0])[None], sub["lh"])[0]]
    hotspot = np.asarray(hotspot, dtype=np.float64)
    direction = np.array([0.85, 0.35, 0.4]) / np.linalg.norm([0.85, 0.35, 0.4])
    other = np.cross(direction, [0.0, 0.0, 1.0])
    other /= np.linalg.norm(other)

    pairs: list[tuple[str, str]] = []
    for h in ("lh", "rh"):
        own = [n for n in names if n.startswith(h)]
        while sum(p[0].startswith(h) for p in pairs) < 22:
            a, b = rng.choice(own, 2, replace=False)
            d = np.linalg.norm(regions[a] - regions[b])
            if 35 < d < 120 and (a, b) not in pairs and (b, a) not in pairs:
                pairs.append((str(a), str(b)))
    while len(pairs) < 60:  # commissural bundles between roughly mirrored patches
        a = str(rng.choice([n for n in names if n.startswith("lh")]))
        mirror = regions[a] * [-1, 1, 1] + [2 * centre[0], 0, 0]
        b = min(
            (n for n in names if n.startswith("rh")),
            key=lambda n: np.linalg.norm(regions[n] - mirror),
        )
        if (a, b) not in pairs:
            pairs.append((a, b))

    lines: list[np.ndarray] = []
    edge_of: list[int] = []
    for edge, (a, b) in enumerate(pairs):
        ha, hb = a[:2], b[:2]
        for _ in range(int(rng.integers(60, 160))):
            ends = []
            for name, h in ((a, ha), (b, hb)):
                q = regions[name] + rng.normal(0, 4.0, 3)
                p = sub[h][_nearest(q[None], sub[h])[0]]
                ends.append(p + 2.0 * (centre - p) / np.linalg.norm(centre - p))
            mid = (ends[0] + ends[1]) / 2
            if ha == hb:
                hemi_centre = hemis[ha].mean(0)
                control = mid + 0.55 * (hemi_centre - mid)
            else:
                control = np.array([centre[0], mid[1], centre[2] + 18.0])
            control = control + rng.normal(0, 3.0, 3)
            lines.append(_bezier(ends[0], control, ends[1]))
            edge_of.append(edge)
    for _ in range(1500):  # unassigned context: short arcs anywhere in the white matter
        h = ("lh", "rh")[int(rng.integers(2))]
        p0 = sub[h][int(rng.integers(len(sub[h])))]
        p1 = sub[h][_nearest((p0 + rng.normal(0, 25.0, 3))[None], sub[h])[0]]
        inward = [p + 2.0 * (centre - p) / np.linalg.norm(centre - p) for p in (p0, p1)]
        control = (inward[0] + inward[1]) / 2 + 0.4 * (
            hemis[h].mean(0) - (inward[0] + inward[1]) / 2
        )
        if np.linalg.norm(inward[1] - inward[0]) > 10:
            lines.append(_bezier(inward[0], control, inward[1]))
            edge_of.append(-1)

    points = np.concatenate(lines).astype(np.float32)
    offsets = np.r_[0, np.cumsum([len(l) for l in lines])].astype(np.int64)
    p = points.astype(np.float64)
    r2 = ((p - hotspot) ** 2).sum(1)
    ti_max = (
        0.03 + 0.32 * np.exp(-r2 / (2 * 16.0**2)) + 0.05 * np.exp(-r2 / (2 * 45.0**2))
    )
    tangent = np.concatenate([np.gradient(l, axis=0) for l in lines])
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
    align = np.abs(tangent @ direction)
    ti_along = ti_max * (0.15 + 0.85 * align)
    e1 = 0.6 * ti_max[:, None] * (direction + 0.4 * other)
    e2 = 0.6 * ti_max[:, None] * (direction - 0.4 * other)
    sid = np.repeat(np.arange(len(lines)), np.diff(offsets))
    length = np.array([np.linalg.norm(np.diff(l, axis=0), axis=1).sum() for l in lines])
    along_max = np.maximum.reduceat(ti_along, offsets[:-1])
    along_mean = np.bincount(sid, ti_along) / np.diff(offsets)
    dpv = {
        "ti_along": ti_along,
        "ti_max": ti_max,
        "e1_par": (e1 * tangent).sum(1),
        "e2_par": (e2 * tangent).sum(1),
    }
    dps = {
        "length_mm": length,
        "ti_along_max": along_max,
        "ti_along_mean": along_mean,
        "edge_id": np.asarray(edge_of, dtype=np.int32),
    }
    os.makedirs(out_dir, exist_ok=True)
    write_trx(os.path.join(out_dir, "all.trx"), points, offsets, dpv, dps)

    edge_ids = np.asarray(edge_of)
    edges = {}
    matrix = np.zeros((len(names), len(names)))
    for edge, (a, b) in enumerate(pairs):
        mine = along_max[edge_ids == edge]
        edges[str(edge)] = {
            "region_a": a,
            "region_b": b,
            "n_streamlines": int(len(mine)),
            "stats": {"ti_along_max_median": float(np.median(mine))},
        }
        i, j = names.index(a), names.index(b)
        matrix[i, j] = matrix[j, i] = float(np.median(mine))
    with open(os.path.join(out_dir, "edges.json"), "w", encoding="utf-8") as stream:
        json.dump(edges, stream, indent=1)
    np.savez(
        os.path.join(out_dir, "connectome_ti_along_max.npz"),
        matrix=matrix,
        labels=np.asarray(names),
    )
    summary = {
        "synthetic": True,
        "seed": seed,
        "n_streamlines": int(len(lines)),
        "n_edges": len(pairs),
        "hotspot_mm": [round(float(x), 2) for x in hotspot],
        "units": "V/m",
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=1)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("m2m_dir")
    parser.add_argument("out_dir")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--hotspot", type=float, nargs=3)
    args = parser.parse_args(argv)
    hotspot = np.asarray(args.hotspot) if args.hotspot else None
    print(
        json.dumps(
            generate(args.m2m_dir, args.out_dir, seed=args.seed, hotspot=hotspot)
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
