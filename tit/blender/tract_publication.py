"""Tract renders, the ``simnibs_python`` half: read the outputs, export a scene, spawn Blender.

:func:`run_tract` reads a simulation's ``tract/`` directory (see :mod:`tit.blender.tract_data`)
and the subject's anatomy, then writes:

- ``tract_scene/``: the render bundle (``manifest.json`` plus ``.npz`` arrays, paths relative
  to the manifest) that :mod:`tit.blender.tract_scene` renders in Blender's own Python. Kept so
  another Blender build can re-render it:
  ``blender --background --python tit/blender/tract_scene.py -- tract_scene/manifest.json``;
- the stills, turntable and propagation MP4s Blender writes beside it;
- ``<sid>_<sim>_tract_viewer.html`` (:mod:`tit.plotting.tract_web`) and
  ``<sid>_<sim>_connectome_<metric>.png`` (:mod:`tit.plotting.tract_connectome`).

Every quantity drawn is a field descriptor along the fibres, not a prediction of activation.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
from pathlib import Path

import numpy as np

from tit.blender import tract_data as td

logger = logging.getLogger(__name__)

#: Point spacing of the render tubes; real tractograms step 0.2-1 mm, far finer than a tube.
RENDER_STEP_MM = 1.5
#: Context lines are thinned harder: they are drawn faint and thin.
CONTEXT_STEP_MM = 3.0
#: Tube radius per streamline, mm: ``TUBE_R0 + TUBE_R1 * gain`` (gain = its peak / the window).
TUBE_R0, TUBE_R1 = 0.12, 0.12
#: One tube radius, mm, for every fibre of a named network (thousands, all drawn).
NETWORK_RADIUS = 0.09
#: Regions named on a still, and regions lit: a bundle can reach dozens of regions, and
#: lighting them all washed the cortex (sub-CHN insula_lh: 41).
N_LABELS, N_LIT = 3, 6
#: Frames of electrode pulse before the fronts leave their peaks.
FRONT_START_FRAME = 18
#: Frames the last state is held after the slowest front lands.
FRONT_HOLD_FRAMES = 36
#: Longest propagation animation, so an emulated render stays bounded.
FRONT_MAX_FRAMES = 240
#: Triangle budgets for the Blender glass brain and scalp.
GLASS_TRIANGLES = 200_000
SCALP_TRIANGLES = 60_000


def resolve_tractogram(tract_dir: str, tractogram: str) -> str:
    """The ``.trx`` to read: an absolute path, a name in *tract_dir*, ``all.trx`` or the only one."""
    if tractogram:
        path = (
            tractogram
            if os.path.isabs(tractogram)
            else os.path.join(tract_dir, tractogram)
        )
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Tractogram not found: {path}")
        return path
    if os.path.isfile(os.path.join(tract_dir, "all.trx")):
        return os.path.join(tract_dir, "all.trx")
    found = sorted(glob.glob(os.path.join(tract_dir, "*.trx")))
    if len(found) != 1:
        raise FileNotFoundError(
            f"Expected all.trx or exactly one .trx in {tract_dir}, found {len(found)}; "
            "name one in the configuration's tractogram field."
        )
    return found[0]


def glass_surface(m2m_dir: str) -> tuple[np.ndarray, np.ndarray, int]:
    """Both hemispheres' central surfaces, merged: (V, T, number of lh vertices).

    The central surface carries the charm annotations vertex for vertex, so a region patch
    is the annotation's own vertices; it is also the surface every subject has.
    """
    import nibabel as nib

    vertices, triangles = [], []
    for hemi in ("lh", "rh"):
        path = os.path.join(m2m_dir, "surfaces", f"{hemi}.central.gii")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Cortical surface not found: {path}")
        darrays = nib.load(path).darrays
        offset = sum(len(v) for v in vertices)
        vertices.append(np.asarray(darrays[0].data, dtype=np.float64))
        triangles.append(np.asarray(darrays[1].data, dtype=np.int64) + offset)
    return np.concatenate(vertices), np.concatenate(triangles), len(vertices[0])


def simulation_electrodes(sim_dir: str) -> list[dict]:
    """The montage's electrodes from ``documentation/config.json``: name, xyz, channel."""
    record = os.path.join(sim_dir, "documentation", "config.json")
    if not os.path.isfile(record):
        logger.warning(f"No simulation record at {record}; electrodes not drawn")
        return []
    with open(record, encoding="utf-8") as stream:
        cfg = json.load(stream)
    names = [str(n) for pair in cfg.get("electrode_pairs") or [] for n in pair]
    coords = cfg.get("electrode_coordinates") or []
    if len(coords) != len(names):
        names = [f"E{i + 1}" for i in range(len(coords))]
    return [
        {"name": name, "xyz": [float(c) for c in xyz], "channel": i // 2}
        for i, (name, xyz) in enumerate(zip(names, coords))
    ]


def label_volume(pm, sid: str) -> str | None:
    """charm ``segmentation/labeling.nii.gz``, else the FastSurfer/FreeSurfer aparc+aseg.

    The same order the tract pipeline names regions from, so a region name finds its voxels.
    """
    for path in (
        pm.tissue_labeling(sid),
        os.path.join(pm.fastsurfer_mri(sid), "aparc.DKTatlas+aseg.deep.nii.gz"),
        os.path.join(pm.freesurfer_mri(sid), "aparc.DKTatlas+aseg.mgz"),
    ):
        if os.path.isfile(path):
            return path
    return None


def region_geometry(
    m2m_dir: str,
    volume: str | None,
    names: list[str],
    glass_vertices: np.ndarray,
    n_lh: int,
    atlas: str = "DK40",
) -> tuple[dict[str, np.ndarray], dict[str, tuple[np.ndarray, np.ndarray]]]:
    """Where each named region is drawn, from the subject's own labels.

    Returns ``(cortical, subcortical)``: cortical regions as indices into *glass_vertices*
    (an ``lh.``/``rh.`` name from the charm annotation on the central surface; a ``ctx-``
    volume label from the voxel under each vertex), subcortical regions as a marching-cubes
    surface ``(vertices, triangles)`` of their voxels. Names found in neither are left out.
    """
    import nibabel as nib

    cortical: dict[str, np.ndarray] = {}
    subcortical: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    wanted = set(names)
    for hemi, offset in (("lh", 0), ("rh", n_lh)):
        annots = sorted(
            glob.glob(os.path.join(m2m_dir, "segmentation", f"{hemi}.*_{atlas}.annot"))
        )
        if not annots:
            continue
        labels, _ctab, label_names = nib.freesurfer.read_annot(annots[0])
        for k, raw in enumerate(label_names):
            name = f"{hemi}.{raw.decode() if isinstance(raw, bytes) else raw}"
            if name in wanted:
                cortical[name] = np.flatnonzero(labels == k) + offset
    missing = wanted - set(cortical)
    if volume and missing:
        from tit.atlas.segstats import resolve_lut_for_atlas

        img = nib.load(volume)
        data = np.asanyarray(img.dataobj)
        data = (data[..., 0] if data.ndim == 4 else data).astype(np.int32)
        value_of = {v: k for k, v in resolve_lut_for_atlas(volume).items()}
        ijk = np.rint(
            (glass_vertices - img.affine[:3, 3]) @ np.linalg.inv(img.affine[:3, :3]).T
        ).astype(int)
        inside = np.all((ijk >= 0) & (ijk < data.shape), axis=1)
        under = np.zeros(len(glass_vertices), dtype=np.int32)
        under[inside] = data[tuple(ijk[inside].T)]
        for name in sorted(missing):
            value = value_of.get(name)
            if value is None:
                continue
            if name.startswith("ctx-"):
                cortical[name] = np.flatnonzero(under == value)
            else:
                mesh = _label_surface(data == value, img.affine)
                if mesh is not None:
                    subcortical[name] = mesh
    return cortical, subcortical


def _label_surface(mask: np.ndarray, affine: np.ndarray):
    """Marching-cubes surface of one label's voxels in world mm, or ``None`` when empty."""
    from skimage.measure import marching_cubes

    where = np.argwhere(mask)
    if len(where) < 8:
        return None
    lo, hi = where.min(0) - 1, where.max(0) + 2
    lo = np.maximum(lo, 0)
    box = np.pad(mask[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]], 1).astype(
        np.float32
    )
    verts, faces, _n, _v = marching_cubes(box, 0.5)
    verts = verts - 1 + lo
    return (verts @ affine[:3, :3].T + affine[:3, 3]).astype(np.float32), faces.astype(
        np.int32
    )


def _end_regions(tracts: td.Tracts, edges: dict[int, dict]) -> list[tuple[str, str]]:
    """(start region, end region) per streamline: streamlines run region_a -> region_b."""
    out = []
    for e in tracts.dps.get("edge_id", np.full(tracts.n, -1)):
        record = edges.get(int(e))
        out.append((record["region_a"], record["region_b"]) if record else ("", ""))
    return out


def bundle_statement(name: str, n: int, summary: dict) -> str:
    """``"insula_lh, 1,232 streamlines: median ti_along 0.12 V/m, align_index 1.01"``.

    Bundle-level field statistics are what hold across tractography tools; which single
    edge ranks first does not, so captions lead with the bundle.
    """
    stats = (summary.get("bundles") or {}).get(name) or {}

    def median(key):
        value = stats.get(key)
        return value.get("median") if isinstance(value, dict) else value

    text = f"{name}, {n:,} streamlines"
    along, align = median("ti_along_mean"), median("align_index")
    if along is not None and align is not None:
        text += f": median ti_along {along:.3f} V/m, align_index {align:.2f}"
    return text


def edges_between(edges: dict[int, dict], side_a, side_b) -> set[int]:
    """Edge ids joining a region of *side_a* to a region of *side_b* (either orientation)."""
    a, b = set(side_a), set(side_b)
    return {
        e
        for e, r in edges.items()
        if (r["region_a"] in a and r["region_b"] in b)
        or (r["region_a"] in b and r["region_b"] in a)
    }


def network_statement(name: str, tracts: td.Tracts) -> str:
    """Two caption lines: the network's name and n, then neutral streamline medians.

    Per streamline: the mean of TI_max and of ti_along over its points (tract points are
    evenly spaced, so a point mean is the arc-length mean), and align_index = mean ti_along /
    mean ti_avg, the tract pipeline's definition. The caption gives their medians.
    """
    sid = tracts.streamline_id()

    def mean(key):
        return np.bincount(sid, tracts.dpv[key], tracts.n) / tracts.lengths

    along, peak = mean("ti_along"), mean("ti_max")
    text = (
        f"{name} · n={tracts.n:,} streamlines (all drawn)\n"
        f"median TI_max {np.median(peak):.3f} V/m · median ti_along {np.median(along):.3f} V/m"
    )
    if "ti_avg" in tracts.dpv:
        avg = mean("ti_avg")
        align = np.divide(along, avg, out=np.ones_like(along), where=avg > 0)
        text += f" · median align_index {np.median(align):.2f}"
    return text


def ti_iso_shell(mesh_path: str, percentile: float, step_mm: float = 1.5):
    """``(vertices, triangles, level)``: the TI_max isosurface in the brain at *percentile*.

    The level is the volume-weighted *percentile* of TI_max over the brain's tetrahedra (white
    and grey matter, tags 1 and 2); the field is interpolated to a *step_mm* grid and the
    surface extracted by marching cubes. Display geometry only.
    """
    import simnibs
    from skimage.measure import marching_cubes

    brain = simnibs.read_msh(mesh_path).crop_mesh(tags=[1, 2])
    name = "TI_max" if "TI_max" in brain.field else next(iter(brain.field))
    field = brain.field[name]
    values = np.asarray(field.value, dtype=np.float64)
    volume = np.asarray(brain.elements_volumes_and_areas().value, dtype=np.float64)
    order = np.argsort(values)
    share = np.cumsum(volume[order]) / volume.sum()
    level = float(
        values[order][min(np.searchsorted(share, percentile / 100.0), len(order) - 1)]
    )
    nodes = np.asarray(brain.nodes.node_coord, dtype=np.float64)
    lo = nodes.min(0) - 2 * step_mm
    dims = np.ceil((nodes.max(0) + 2 * step_mm - lo) / step_mm).astype(int)
    affine = np.eye(4)
    affine[:3, :3] *= step_mm
    affine[:3, 3] = lo
    grid = np.nan_to_num(np.asarray(field.interpolate_to_grid(dims, affine)))
    verts, faces, _normals, _values = marching_cubes(grid, level)
    return (verts * step_mm + lo).astype(np.float32), faces.astype(np.int32), level


def select_network(
    cfg, tract_dir: str, everything: td.Tracts, edges, summary
) -> tuple[td.Tracts, str, list[dict]]:
    """The foreground: the configured bundle plus the run's top stimulated edges.

    Top edges come from ``summary.json``'s ``top_edges`` (the pipeline's own ranking), kept
    when they have at least ``network_min_streamlines`` streamlines. Returns the streamlines,
    a one-line description and the edges used.
    """
    parts, words = [], []
    if cfg.network_bundle:
        path = os.path.join(tract_dir, f"{cfg.network_bundle}.trx")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Network bundle not found: {path}")
        bundle = td.load_trx(path)
        parts.append(bundle)
        words.append(bundle_statement(cfg.network_bundle, bundle.n, summary))
    ranked = summary.get("top_edges") or []
    top = [
        e for e in ranked if e.get("n_streamlines", 0) >= cfg.network_min_streamlines
    ]
    top = top[: cfg.network_top_edges]
    if top:
        ids = {int(e["edge_id"]) for e in top}
        pick = np.flatnonzero(np.isin(everything.dps["edge_id"], list(ids)))
        parts.append(td.select(everything, pick))
        words.append(
            f"its {len(top)} strongest edges (≥ {cfg.network_min_streamlines} streamlines each)"
        )
    if not parts:
        raise ValueError("network mode needs network_bundle or summary.json top_edges")
    network = parts[0] if len(parts) == 1 else td.concat(parts)
    if network.n > cfg.max_streamlines:
        weight = network.dps.get("ti_along_max", np.ones(network.n))
        network = td.select(
            network, td.subsample(weight, cfg.max_streamlines, cfg.seed)
        )
    return network, " + ".join(words), top


def _simplified(vertices: np.ndarray, triangles: np.ndarray, budget: int):
    from tit.scene.simplify import simplify_to_budget

    result = simplify_to_budget(vertices, triangles, budget)
    return result.vertices.astype(np.float32), result.triangles.astype(np.int32)


def export_scene(
    cfg,
    tracts: td.Tracts,
    n_total: int,
    glass: tuple[np.ndarray, np.ndarray, int],
    scalp: tuple[np.ndarray, np.ndarray] | None,
    electrodes: list[dict],
    bundle_dir: str,
    *,
    title: str,
    synthetic: bool,
    context: td.Tracts | None = None,
    edges: dict[int, dict] | None = None,
    regions: tuple[dict, dict] | None = None,
    caption: str = "",
    highlight: list[str] | None = None,
    shell: tuple[np.ndarray, np.ndarray, float] | None = None,
) -> str:
    """Write the Blender bundle; return the manifest path.

    *tracts* are drawn as full tubes of constant width per streamline, coloured along their
    length; *context* (optional) as faint thin lines. *regions* is :func:`region_geometry`'s
    result for the foreground's endpoint regions, which are lit by how much field their
    fibres carry, or, with *highlight*, exactly those regions, evenly. *shell* is
    :func:`ti_iso_shell`'s result, drawn as one faint translucent surface.
    """
    os.makedirs(bundle_dir, exist_ok=True)
    edges = edges or {}
    metric = str(cfg.metric)
    along = td.smooth_along(tracts, tracts.dpv["ti_along"])
    shown = td.display_metric(tracts, "ti_along" if metric == "direction" else metric)
    if metric in td.DIVERGING:
        vmax = 2.0**td.ALIGN_OCTAVES
    elif metric == "ti_ratio":
        vmax = 1.0
    else:
        vmax = float(cfg.vmax_v_per_m) if cfg.vmax_v_per_m else td.robust_max(shown)
    along_top = (
        float(cfg.vmax_v_per_m)
        if cfg.vmax_v_per_m and metric == "ti_along"
        else td.robust_max(along)
    )
    s = td.arc_length(tracts)
    peak = td.peak_vertex(tracts, along)
    sid = tracts.streamline_id()
    gain = np.clip(along[peak] / along_top, 0.0, 1.0)
    tracts.dpv["d"] = np.abs(s - s[peak][sid]).astype(np.float32)
    tracts.dpv["gain"] = gain[sid].astype(np.float32)
    tracts.dpv["v"] = td.colour_position(shown, metric, vmax)
    # A named network draws every fibre at one width: width must not encode the field there.
    radius = (
        np.full(tracts.n, NETWORK_RADIUS)
        if cfg.network_from
        else TUBE_R0 + TUBE_R1 * gain
    )
    tracts.dpv["r"] = radius[sid].astype(np.float32)
    total = s[tracts.offsets[1:] - 1]
    speed = float(cfg.front_speed_mm_per_frame)
    arrive = np.stack(
        [
            FRONT_START_FRAME + s[peak] / speed,
            FRONT_START_FRAME + (total - s[peak]) / speed,
        ],
        1,
    )
    tube = td.decimate(tracts, RENDER_STEP_MM)
    np.savez(
        os.path.join(bundle_dir, "tracts.npz"),
        points=tube.points.astype(np.float32),
        offsets=tube.offsets.astype(np.int64),
        v=tube.dpv["v"],
        r=tube.dpv["r"],
        d=tube.dpv["d"],
        gain=tube.dpv["gain"],
        tangent=np.abs(td.tangents(tube)).astype(np.float32),
    )
    if context is not None and context.n:
        thin = td.decimate(context, CONTEXT_STEP_MM)
        np.savez(
            os.path.join(bundle_dir, "context.npz"),
            points=thin.points.astype(np.float32),
            offsets=thin.offsets.astype(np.int64),
        )

    from tit.scene.simplify import simplify_to_budget

    simple = simplify_to_budget(glass[0], glass[1], GLASS_TRIANGLES)
    gv, gt = simple.vertices.astype(np.float32), simple.triangles.astype(np.int32)
    lit_full = np.zeros(len(glass[0]), np.float32)
    frame_full = np.full(len(glass[0]), 1e6, np.float32)
    labels, sub_v, sub_t, sub_lit, sub_frame = [], [], [], [], []
    if regions is not None:
        cortical, subcortical = regions
        weight, when, count = {}, {}, {}
        for i, pair in enumerate(_end_regions(tracts, edges)):
            for name in {n for n in pair if n}:  # n counts streamlines, not ends
                count[name] = count.get(name, 0) + 1
            for k, name in enumerate(pair):
                if name:
                    weight[name] = weight.get(name, 0.0) + float(gain[i])
                    when[name] = min(when.get(name, 1e6), float(arrive[i, k]))
        drawn = sorted(
            (n for n in weight if n in cortical or n in subcortical),
            key=lambda n: -weight[n],
        )[:N_LIT]
        if highlight:
            # Highlighted regions (the thalami) at full level; the network's cortical parcels
            # by how many of its streamlines end in them, so the busiest terminals glow most.
            parcels = [n for n in count if n in cortical and n not in highlight]
            busiest = max((count[n] for n in parcels), default=1)
            drawn = [
                n for n in highlight if n in cortical or n in subcortical
            ] + parcels
            weight.update({n: 1.0 for n in highlight})
            # Squared: the level below is its square root, so a parcel glows linearly in n.
            weight.update({n: max(count[n] / busiest, 0.15) ** 2 for n in parcels})
            top = 1.0
            when.update({n: float(FRONT_START_FRAME) for n in drawn})
        if not highlight:
            top = max((weight[n] for n in drawn), default=1.0)
        for name in drawn:
            level = float(np.clip(np.sqrt(weight[name] / top), 0.2, 1.0))
            if name in cortical:
                ix = cortical[name]
                lit_full[ix] = np.maximum(lit_full[ix], level)
                frame_full[ix] = np.minimum(frame_full[ix], when[name])
                centre = glass[0][ix].mean(0) if len(ix) else None
            else:
                v, t = subcortical[name]
                sub_t.append(t + sum(len(x) for x in sub_v))
                sub_v.append(v)
                sub_lit.append(np.full(len(v), level, np.float32))
                sub_frame.append(np.full(len(v), when[name], np.float32))
                centre = v.mean(0)
            if centre is not None and cfg.region_labels and len(labels) < N_LABELS:
                labels.append(
                    {
                        "name": f"{name} (n={count.get(name, 0)})",
                        "xyz": [float(c) for c in centre],
                    }
                )
    np.savez(
        os.path.join(bundle_dir, "glass.npz"),
        vertices=gv,
        triangles=gt,
        lit=lit_full[simple.source_index],
        frame=frame_full[simple.source_index],
    )
    if sub_v:
        np.savez(
            os.path.join(bundle_dir, "regions.npz"),
            vertices=np.concatenate(sub_v),
            triangles=np.concatenate(sub_t),
            lit=np.concatenate(sub_lit),
            frame=np.concatenate(sub_frame),
        )
    if shell is not None:
        np.savez(
            os.path.join(bundle_dir, "shell.npz"), vertices=shell[0], triangles=shell[1]
        )
    if scalp is not None:
        sv, st = _simplified(*scalp, SCALP_TRIANGLES)
        np.savez(os.path.join(bundle_dir, "scalp.npz"), vertices=sv, triangles=st)

    hot = tracts.points[along >= np.percentile(along, 99)]
    side = -1.0 if hot[:, 0].mean() < gv[:, 0].mean() else 1.0
    side = float(cfg.lateral_side) if cfg.lateral_side else side
    label, units = td.METRICS[metric]
    if metric in td.DIVERGING:
        ticks = [[0.0, "0.5"], [0.5, "1"], [1.0, "2"]]
    else:
        ticks = [[f, f"{f * vmax:.2f}"] for f in (0.0, 0.5, 1.0)]
    travel = float(np.percentile(arrive.max(1), 98))
    frames = int(min(FRONT_MAX_FRAMES, np.ceil(travel) + FRONT_HOLD_FRAMES))
    stem = f"{cfg.subject_id}_{cfg.simulation_name}_tract_{metric}"
    shown_text = (caption or f"{tracts.n:,} of {n_total:,} streamlines") + (
        ""
        if cfg.network_from
        else f" · colour averaged along each fibre over ±{td.SMOOTH_MM:g} mm"
    )
    if context is not None and context.n:
        shown_text += f" · grey: {context.n:,} other streamlines"
    manifest = {
        "title": title,
        "synthetic": synthetic,
        "metric": metric,
        "label": label,
        "units": units,
        "vmax": vmax,
        "ticks": ticks,
        "stops": td.stops_for(metric),
        "diverging": metric in td.DIVERGING,
        "caption": shown_text,
        "n_shown": tracts.n,
        "n_total": int(n_total),
        "smoothing_mm": td.SMOOTH_MM,
        "lateral_side": side,
        "tracts": "tracts.npz",
        "context": "context.npz" if context is not None and context.n else None,
        "glass": "glass.npz",
        "regions": "regions.npz" if sub_v else None,
        "shell": "shell.npz" if shell is not None else None,
        "shell_level": float(shell[2]) if shell is not None else None,
        "shell_percentile": float(cfg.iso_shell_percentile or 0),
        "crossfade": bool(cfg.turntable_crossfade),
        "network": bool(cfg.network_from),
        "smoothing_note": f"colour averaged along each fibre over ±{td.SMOOTH_MM:g} mm",
        "labels": labels,
        "scalp": "scalp.npz" if scalp is not None else None,
        "electrodes": electrodes,
        "roi": (
            {"center": list(cfg.roi_center_mm), "radius": float(cfg.roi_radius_mm)}
            if cfg.roi_center_mm is not None
            else None
        ),
        "output_dir": "..",
        "stem": stem,
        "stills": bool(cfg.stills),
        "still_size": [int(cfg.width), int(cfg.height)],
        "turntable": bool(cfg.turntable),
        "turntable_frames": int(cfg.turntable_frames),
        "turntable_degrees": float(cfg.turntable_degrees),
        "propagation": bool(cfg.propagation),
        "front": {
            "speed": speed,
            "start": FRONT_START_FRAME,
            "frames": frames,
        },
    }
    path = os.path.join(bundle_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=1, allow_nan=False)
    return path


def render(manifest_path: str) -> None:
    """Run :mod:`tit.blender.tract_scene` on *manifest_path* in ``$TIT_BLENDER_BIN``."""
    renderer = Path(__file__).with_name("tract_scene.py")
    executable = os.environ.get("TIT_BLENDER_BIN", "/opt/blender/blender")
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"}
    }
    # Inherit the parent's process group: cancelling a job must also stop Blender.
    subprocess.run(
        [
            executable,
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(renderer),
            "--",
            manifest_path,
        ],
        check=True,
        env=env,
    )


def run_tract(cfg, *, logger_override: logging.Logger | None = None) -> str:
    """Write every output *cfg* asks for; return the output directory."""
    from tit import constants as const
    from tit.paths import get_path_manager

    log = logger_override or logger
    pm = get_path_manager()
    sid, sim = cfg.subject_id.strip(), cfg.simulation_name.strip()
    sim_dir = pm.simulation(sid, sim)
    path = resolve_tractogram(os.path.join(sim_dir, "tract"), cfg.tractogram.strip())
    tract_dir = os.path.dirname(path)
    out = (cfg.output_dir or "").strip() or os.path.join(
        pm.ti_toolbox(), "visual_exports", f"{const.PREFIX_SUBJECT}{sid}", sim, "tract"
    )
    os.makedirs(out, exist_ok=True)

    summary = {}
    if os.path.isfile(os.path.join(tract_dir, "summary.json")):
        with open(os.path.join(tract_dir, "summary.json"), encoding="utf-8") as stream:
            summary = json.load(stream)
    synthetic = bool(summary.get("synthetic"))
    everything = td.load_trx(path)
    needed = ["ti_along", "ti_max"] + (
        ["ti_avg"] if cfg.metric == "align_index" else []
    )
    for key in needed:
        if key not in everything.dpv:
            raise ValueError(f"{path} has no data_per_vertex {key!r}")
    n_total = everything.n
    weight = everything.dps.get("ti_along_max")
    if weight is None:
        weight = np.maximum.reduceat(
            everything.dpv["ti_along"], everything.offsets[:-1]
        )
    tracts = td.select(everything, td.subsample(weight, cfg.max_streamlines, cfg.seed))
    log.info(f"{path}: {n_total} streamlines, rendering {tracts.n}")
    edges = td.read_edges(os.path.join(tract_dir, "edges.json"))
    electrodes = simulation_electrodes(sim_dir)
    m2m = pm.m2m(sid)
    glass = glass_surface(m2m)
    title = f"sub-{sid} · {sim}" + (" · synthetic tracts" if synthetic else "")

    if cfg.web:
        from tit.plotting.tract_web import write_viewer

        viewer = os.path.join(out, f"{sid}_{sim}_tract_viewer.html")
        write_viewer(
            viewer, tracts, glass[:2], electrodes, edges, title=title, n_total=n_total
        )
        log.info(f"wrote {viewer}")
    if cfg.connectome:
        from tit.plotting.tract_connectome import plot_connectome

        for npz in sorted(glob.glob(os.path.join(tract_dir, "connectome_*.npz"))):
            metric = Path(npz).stem.removeprefix("connectome_")
            png = os.path.join(out, f"{sid}_{sim}_connectome_{metric}.png")
            plot_connectome(npz, png, title=title)
            log.info(f"wrote {png}")
    if cfg.stills or cfg.turntable or cfg.propagation:
        from tit.blender.utils import extract_scalp_from_msh

        msh = os.path.join(m2m, f"{sid}.msh")
        scalp = extract_scalp_from_msh(msh) if os.path.isfile(msh) else None
        kwargs = {}
        if cfg.iso_shell_percentile:
            kwargs["shell"] = ti_iso_shell(
                pm.ti_mesh(sid, sim), cfg.iso_shell_percentile
            )
            log.info(
                f"TI_max iso-shell at {kwargs['shell'][2]:.3f} V/m "
                f"(brain p{cfg.iso_shell_percentile:g})"
            )
        if cfg.network_from:
            ids = edges_between(edges, cfg.network_from, cfg.network_to)
            pick = np.flatnonzero(np.isin(everything.dps["edge_id"], sorted(ids)))
            if not len(pick):
                raise ValueError("network_from / network_to join no streamline")
            tracts = td.select(everything, pick)  # every streamline: no subsampling
            pairs = " + ".join(
                "–".join(e["name"] for e in electrodes if e["channel"] == c)
                for c in sorted({e["channel"] for e in electrodes})
            )
            caption = network_statement(f"sub-{sid} · {sim} montage ({pairs})", tracts)
            if "shell" in kwargs:
                caption += (
                    f"\ntranslucent shell: TI_max = {kwargs['shell'][2]:.3f} V/m "
                    f"(brain p{cfg.iso_shell_percentile:g}, volume-weighted)"
                )
            title = cfg.network_name or title
            names = sorted(set(cfg.highlight_regions) | set(cfg.network_to))
            regions = region_geometry(
                m2m, label_volume(pm, sid), names, glass[0], glass[2]
            )
            log.info(
                f"network {cfg.network_name}: {len(ids)} edges, {tracts.n} streamlines"
            )
            kwargs.update(
                edges=edges,
                regions=regions,
                caption=caption,
                highlight=list(cfg.highlight_regions),
            )
        elif cfg.focus:
            network, words, top = select_network(
                cfg, tract_dir, everything, edges, summary
            )
            names = sorted(
                {n for pair in _end_regions(network, edges) for n in pair if n}
            )
            regions = region_geometry(
                m2m, label_volume(pm, sid), names, glass[0], glass[2]
            )
            context = None
            if cfg.context_streamlines:
                keep = td.subsample(
                    np.ones(everything.n), cfg.context_streamlines, cfg.seed
                )
                context = td.select(everything, keep)
            caption = (
                words.replace(" + ", "\n+ ", 1)
                + f" · {network.n:,} of {n_total:,} drawn"
            )
            log.info(f"network: {caption}; {len(names)} endpoint regions")
            kwargs.update(
                context=context, edges=edges, regions=regions, caption=caption
            )
            tracts = network
        manifest = export_scene(
            cfg,
            tracts,
            n_total,
            glass,
            scalp,
            electrodes,
            os.path.join(out, "tract_scene"),
            title=title,
            synthetic=synthetic,
            **kwargs,
        )
        render(manifest)
    return out
