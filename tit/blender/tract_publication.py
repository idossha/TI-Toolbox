"""Tract renders, the ``simnibs_python`` half: read the outputs, export a scene, spawn Blender.

:func:`run_tract` reads a simulation's ``tract/`` directory (see :mod:`tit.blender.tract_data`)
and the subject's anatomy, then writes:

``visual_exports/sub-<id>/<sim>/networks/<network>/``, one folder per network (``all`` for a
render of the whole tractogram):

- ``<colour>.png``, one figure of four panels, and ``<colour>_turntable.mp4``: the model and its
  tractography and nothing else, which Blender renders from a temporary bundle
  (``bundle_<colour>/``, ``manifest.json`` plus ``.npz`` arrays) that
  :mod:`tit.blender.tract_scene` reads in Blender's own Python. The bundle is deleted after a
  successful render, and kept after a failed one or with ``keep_bundle``;
- ``network.blend`` when asked for: the scene that render used, whole;
- ``network.json``: per colour the config that re-renders it
  (``simnibs_python -m tit.blender network.json <colour>``), the resolved setup and the files,
  and ``metrics``, the numbers a figure no longer carries, with the selection and the code version;
- ``tract_viewer.html`` (:mod:`tit.plotting.tract_web`) and ``connectome_<metric>.png``
  (:mod:`tit.plotting.tract_connectome`) when asked for.

Every quantity drawn is a field descriptor along the fibres, not a prediction of activation.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from tit.blender import tract_data as td
from tit.blender.network_setup import (
    PANELS,
    region_hemi,
    resolve_network_setup,
)
from tit.tract.config import Selection, own_selection_name

logger = logging.getLogger(__name__)

#: Point spacing of the render tubes; real tractograms step 0.2-1 mm, far finer than a tube.
RENDER_STEP_MM = 1.5
#: Context lines are thinned harder: they are drawn faint and thin.
CONTEXT_STEP_MM = 3.0
#: Tube radius per streamline, mm: ``TUBE_R0 + TUBE_R1 * gain`` (gain = its peak / the window).
TUBE_R0, TUBE_R1 = 0.12, 0.12
#: One tube radius, mm, for every fibre of a named network (thousands, all drawn).
NETWORK_RADIUS = 0.09
#: Regions lit: a bundle can reach dozens of regions, and lighting them all washed the cortex
#: (sub-CHN insula_lh: 41).
N_LIT = 6
#: A selection lights its busiest parcels only: all 64 of a hippocampal-cortical set wash the cortex.
MAX_LIT_PARCELS = 24
#: Glow of highlighted regions (e.g. both thalami in a named network): soft, not white.
HIGHLIGHT_LEVEL = 0.4
#: How far past the midline a same-side streamline must reach to count as crossing it twice.
MIDLINE_MARGIN_MM = 5.0
#: Frames of electrode pulse before the fronts leave their peaks.
FRONT_START_FRAME = 18
#: Frames the last state is held after the slowest front lands.
FRONT_HOLD_FRAMES = 36
#: Longest propagation animation, so an emulated render stays bounded.
FRONT_MAX_FRAMES = 240
#: Triangle budgets for the Blender glass brain and scalp.
GLASS_TRIANGLES = 200_000
SCALP_TRIANGLES = 60_000
#: A network's saved scene.
BLEND_NAME = "network.blend"
#: ``network.blend``'s size, measured (BENCHMARKS.md): the glass brain, scalp and shell, then fibres.
BLEND_BASE_MB, BLEND_MB_PER_STREAMLINE = 9.0, 0.0012
#: Where the panels sit in the figure, as ``network.json`` says it.
PANEL_ORDER = "two to a row, left to right, top to bottom"
#: The direction colouring's key: |x|, |y|, |z| of the local tangent as red, green, blue.
DIRECTION_KEY = {
    "red": "left – right",
    "green": "anterior – posterior",
    "blue": "superior – inferior",
}


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


def edges_between(edges: dict[int, dict], side_a, side_b) -> set[int]:
    """Edge ids joining a region of *side_a* to a region of *side_b* (either orientation)."""
    a, b = set(side_a), set(side_b)
    return {
        e
        for e, r in edges.items()
        if (r["region_a"] in a and r["region_b"] in b)
        or (r["region_a"] in b and r["region_b"] in a)
    }


def network_medians(tracts: td.Tracts) -> dict[str, float | None]:
    """Neutral medians over a whole network, whatever share of it is drawn.

    Per streamline: the arc-length mean of TI_max and of ti_along (the mean the assess stage
    reports), and align_index = mean ti_along / mean ti_avg, its definition; ``None`` for a
    tractogram with no ti_avg.
    """

    def mean(key):
        return td.arc_length_mean(tracts, tracts.dpv[key])

    along, align = mean("ti_along"), None
    if "ti_avg" in tracts.dpv:
        avg = mean("ti_avg")
        ratio = np.divide(along, avg, out=np.ones_like(along), where=avg > 0)
        align = round(float(np.median(ratio)), 4)
    return {
        "median_ti_max_v_per_m": round(float(np.median(mean("ti_max"))), 4),
        "median_ti_along_v_per_m": round(float(np.median(along)), 4),
        "median_align_index": align,
    }


def region_counts(tracts: td.Tracts, edges: dict[int, dict]) -> dict[str, int]:
    """Streamlines ending in each region, most first; one with both ends in a region counts once."""
    count: dict[str, int] = {}
    for pair in _end_regions(tracts, edges):
        for name in {n for n in pair if n}:
            count[name] = count.get(name, 0) + 1
    return dict(sorted(count.items(), key=lambda item: (-item[1], item[0])))


def montage_record(electrodes: list[dict]) -> list[dict]:
    """The montage per electrode: its label if it has one, and where it sits, to 0.1 mm."""
    return [
        {
            "channel": e["channel"],
            # A montage placed by coordinates names its electrodes by them: no label to keep.
            "label": None if e["name"].startswith("[") else e["name"],
            "xyz_mm": [round(c, 1) for c in e["xyz"]],
        }
        for e in electrodes
    ]


def network_metrics(
    network: td.Tracts,
    n_total: int,
    edges: dict[int, dict],
    electrodes: list[dict],
    setup: dict | None,
    *,
    synthetic: bool,
) -> dict:
    """What holds for the network whichever colour or budget renders it; no metric is singled out."""
    return {
        "synthetic": synthetic,
        "streamlines_total": int(n_total),
        "opposite_hemisphere_removed": setup.get("opposite_removed") if setup else None,
        "streamlines_per_region": region_counts(network, edges),
        **network_medians(network),
        "montage": montage_record(electrodes),
    }


def image_metrics(manifest: dict) -> dict:
    """What holds for one render: how much it drew, its shell, and how to read its colours."""
    record = {
        "streamlines_drawn": manifest["n_drawn"],
        "shell": manifest["shell_record"],
        "lateral_side": "left" if manifest["lateral_side"] < 0 else "right",
    }
    if manifest["metric"] == "direction":
        record["colour_key"] = DIRECTION_KEY
    else:
        record["colour_scale"] = {
            "label": manifest["label"],
            "units": manifest["units"],
            "range": [round(manifest["vmin"], 4), round(manifest["vmax"], 4)],
            "colour_map": (
                "coolwarm, log2 about 1" if manifest["diverging"] else "plasma"
            ),
            "smoothing_mm": manifest["smoothing_mm"],
        }
    return record


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


def select_network(cfg, tract_dir: str, everything: td.Tracts, summary) -> td.Tracts:
    """The foreground: the configured bundle plus the run's top stimulated edges.

    Top edges come from ``summary.json``'s ``top_edges`` (the pipeline's own ranking), kept
    when they have at least ``network_min_streamlines`` streamlines.
    """
    parts = []
    if cfg.network_bundle:
        path = os.path.join(tract_dir, f"{cfg.network_bundle}.trx")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Network bundle not found: {path}")
        parts.append(td.load_trx(path))
    ranked = summary.get("top_edges") or []
    top = [
        e for e in ranked if e.get("n_streamlines", 0) >= cfg.network_min_streamlines
    ]
    top = top[: cfg.network_top_edges]
    if top:
        ids = {int(e["edge_id"]) for e in top}
        pick = np.flatnonzero(np.isin(everything.dps["edge_id"], list(ids)))
        parts.append(td.select(everything, pick))
    if not parts:
        raise ValueError("network mode needs network_bundle or summary.json top_edges")
    network = parts[0] if len(parts) == 1 else td.concat(parts)
    if network.n > cfg.max_streamlines:
        weight = network.dps.get("ti_along_max", np.ones(network.n))
        network = td.select(
            network, td.subsample(weight, cfg.max_streamlines, cfg.seed)
        )
    return network


def network_slug(cfg) -> str:
    """The network's folder name: a loaded file's, a selection's, a bundle's, or ``all``."""
    if cfg.own_network:
        return own_selection_name(cfg.own_network)
    if cfg.selection is not None:
        return cfg.selection.name
    named = (cfg.network_bundle or cfg.network_name or "").strip()
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in named) or "all"


def network_output_dir(cfg, simulation_exports: str) -> str:
    """``networks/<datetime>/`` of a simulation's exports, named as an ex-search run's folder is,
    or the ``output_dir`` the config names."""
    explicit = (cfg.output_dir or "").strip()
    return explicit or os.path.join(
        simulation_exports, "networks", time.strftime("%Y%m%d_%H%M%S")
    )


def bundle_folder(cfg) -> str:
    """Where a run's temporary render bundle lies, inside the network's folder."""
    return f"bundle_{cfg.metric}"


def planned_outputs(cfg) -> list[str]:
    """The files this config's run writes, named as they will be."""
    names = []
    for metric in map(str, [cfg.metric, *cfg.extra_metrics]):
        if cfg.stills:
            names.append(f"{metric}.png")
        if cfg.turntable:
            names.append(f"{metric}_turntable.mp4")
        if cfg.propagation:
            names.append(f"{metric}_propagation.mp4")
    if cfg.export_blend:
        names.append(BLEND_NAME)
    if cfg.web:
        names.append("tract_viewer.html")
    return names


def blend_size_mb(n_drawn: int) -> int:
    """About how large ``network.blend`` will be, from the render's streamline budget."""
    return round(BLEND_BASE_MB + BLEND_MB_PER_STREAMLINE * n_drawn)


def _one_colour(cfg, metric, first: bool):
    """*cfg* as the render of one of its colours: the first holds the ``.blend``, and only a scalar crossfades."""
    return replace(
        cfg,
        metric=metric,
        extra_metrics=[],
        export_blend=cfg.export_blend and first,
        turntable_crossfade=cfg.turntable_crossfade and str(metric) != "direction",
    )


def _remove_bundles(cfg, out: str, folders: list[str]) -> None:
    """A successful render leaves no bundle behind, unless the config asked to keep it."""
    if cfg.keep_bundle:
        return
    for folder in folders:
        shutil.rmtree(os.path.join(out, folder), ignore_errors=True)


def write_network_record(
    out: str, cfg, original, setup: dict | None, metrics: dict, image: dict
) -> str:
    """``network.json``: the sidecar of this network's renders.

    One entry per colour; ``config`` renders it again, in a new folder:
    ``simnibs_python -m tit.blender network.json <colour>``. ``metrics`` holds the network's numbers
    and, under ``images``, each image's; ``blend`` says which colour ``network.blend`` holds.
    """
    from datetime import datetime, timezone

    import tit
    from tit.config_io import serialize_config

    path = os.path.join(out, "network.json")
    record = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as stream:
            record = json.load(stream)
    selection = cfg.selection
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    files = [n for n in planned_outputs(cfg) if os.path.isfile(os.path.join(out, n))]
    colours = dict(record.get("colours") or {})
    # A turntable after a figure leaves the figure in the folder, so its record stays too.
    kept = (colours.get(str(cfg.metric)) or {}).get("files") or []
    colours[str(cfg.metric)] = {
        "config": serialize_config(original),
        "setup": setup,
        "files": sorted(
            {n for n in kept if os.path.isfile(os.path.join(out, n))}
            | {n for n in files if n != BLEND_NAME}
        ),
        "rendered_at": now,
    }
    blend = record.get("blend")
    if cfg.export_blend:
        blend = {
            "file": BLEND_NAME,
            "colour": str(cfg.metric),
            "bytes": os.path.getsize(os.path.join(out, BLEND_NAME)),
            "rendered_at": now,
        }
    drawn = {n for colour in colours.values() for n in colour["files"]}
    images = dict((record.get("metrics") or {}).get("images") or {})
    for name in files:
        if name.endswith(".png"):
            images[name] = {
                "panels": list(PANELS),
                "panel_order": PANEL_ORDER,
                **image,
            }
        elif name.endswith(".mp4"):
            images[name] = dict(image)
            if (
                cfg.turntable_crossfade
            ):  # it opens in direction colours, then fades to the metric
                images[name]["colour_key"] = DIRECTION_KEY
    images = {name: images[name] for name in images if name in drawn}
    updated = {
        "network": network_slug(cfg),
        "subject_id": cfg.subject_id.strip(),
        "simulation": cfg.simulation_name.strip(),
        "selection": asdict(selection) if selection else None,
        "preset": cfg.preset,
        "code_version": tit.__version__,
        "colours": colours,
        "metrics": {**metrics, "images": images},
        "blend": blend,
    }
    with open(path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(updated, stream, indent=1, allow_nan=False)
    os.replace(path + ".tmp", path)
    return path


def _simplified(vertices: np.ndarray, triangles: np.ndarray, budget: int):
    from tit.scene.simplify import simplify_to_budget

    result = simplify_to_budget(vertices, triangles, budget)
    return result.vertices.astype(np.float32), result.triangles.astype(np.int32)


def export_scene(
    cfg,
    tracts: td.Tracts,
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
    highlight: list[str] | None = None,
    shell: tuple[np.ndarray, np.ndarray, float] | None = None,
    setup: dict | None = None,
) -> str:
    """Write the Blender bundle; return the manifest path.

    *tracts* are drawn as full tubes of constant width per streamline, coloured along their
    length; *context* (optional) as faint thin lines. *regions* is :func:`region_geometry`'s
    result for the foreground's endpoint regions, which are lit by how much field their
    fibres carry, or, with *highlight*, exactly those regions, evenly. *shell* is
    :func:`ti_iso_shell`'s result, drawn as one faint translucent surface. *setup* is
    :func:`~tit.blender.network_setup.resolve_network_setup`'s result, recorded in the manifest.
    """
    os.makedirs(bundle_dir, exist_ok=True)
    named = bool(cfg.network_from or cfg.selection)
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
        np.full(
            tracts.n,
            setup["values"]["tube_radius_mm"] if setup else NETWORK_RADIUS,
        )
        if named
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
    sub_v, sub_t, sub_lit, sub_frame = [], [], [], []
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
            # Highlighted regions (the thalami) at HIGHLIGHT_LEVEL; the network's cortical
            # parcels by how many of its streamlines end in them, so the busiest glow most.
            parcels = [n for n in count if n in cortical and n not in highlight]
            if cfg.selection:
                parcels = sorted(parcels, key=lambda n: (-count[n], n))[
                    :MAX_LIT_PARCELS
                ]
            busiest = max((count[n] for n in parcels), default=1)
            drawn = [
                n for n in highlight if n in cortical or n in subcortical
            ] + parcels
            weight.update({n: HIGHLIGHT_LEVEL**2 for n in highlight})
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
            else:
                v, t = subcortical[name]
                sub_t.append(t + sum(len(x) for x in sub_v))
                sub_v.append(v)
                sub_lit.append(np.full(len(v), level, np.float32))
                sub_frame.append(np.full(len(v), when[name], np.float32))
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
    manifest = {
        "title": title,
        "synthetic": synthetic,
        "metric": metric,
        "label": label,
        "units": units,
        "vmin": 1.0 / vmax if metric in td.DIVERGING else 0.0,
        "vmax": vmax,
        "ticks": ticks,
        "stops": td.stops_for(metric),
        "diverging": metric in td.DIVERGING,
        "n_drawn": int(tracts.n),
        "smoothing_mm": td.SMOOTH_MM,
        "lateral_side": side,
        "tracts": "tracts.npz",
        "context": "context.npz" if context is not None and context.n else None,
        "glass": "glass.npz",
        "regions": "regions.npz" if sub_v else None,
        "shell": "shell.npz" if shell is not None else None,
        "shell_record": (
            {
                "level_v_per_m": round(float(shell[2]), 4),
                "percentile": float(cfg.iso_shell_percentile),
                "chosen_by": "volume-weighted percentile of TI_max over the brain's tetrahedra",
            }
            if shell is not None
            else None
        ),
        "crossfade": bool(cfg.turntable_crossfade),
        "network": named,
        "setup": setup,
        "smoothing_note": f"colour averaged along each fibre over ±{td.SMOOTH_MM:g} mm",
        "scalp": "scalp.npz" if scalp is not None else None,
        "electrodes": electrodes,
        "roi": (
            {"center": list(cfg.roi_center_mm), "radius": float(cfg.roi_radius_mm)}
            if cfg.roi_center_mm is not None
            else None
        ),
        "output_dir": "..",
        "stem": metric,
        "stills": bool(cfg.stills),
        "panels": list(PANELS),
        "export_blend": bool(cfg.export_blend),
        "preview": str(cfg.quality) == "preview",
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


def render(*scene_args: str) -> None:
    """Run :mod:`tit.blender.tract_scene` with *scene_args* in ``$TIT_BLENDER_BIN``."""
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
            *scene_args,
        ],
        check=True,
        env=env,
    )


def _edge_ids(edges: dict[int, dict], pairs) -> set[int]:
    """Edge ids of the region *pairs*, in either orientation."""
    wanted = {frozenset(pair) for pair in pairs}
    return {
        e
        for e, r in edges.items()
        if frozenset((r["region_a"], r["region_b"])) in wanted
    }


def _picked(everything: td.Tracts, ids: set[int]) -> np.ndarray:
    return np.flatnonzero(np.isin(everything.dps["edge_id"], sorted(ids)))


def _edge_counts(
    tracts: td.Tracts, edges: dict[int, dict]
) -> dict[tuple[str, str], int]:
    ids, counts = np.unique(tracts.dps["edge_id"], return_counts=True)
    return {
        (edges[int(e)]["region_a"], edges[int(e)]["region_b"]): int(n)
        for e, n in zip(ids, counts)
        if int(e) in edges
    }


def _bundle_as_selection(cfg, everything: td.Tracts, edges: dict[int, dict]):
    """An existing bundle file, as the one kind of network the automatic setup reads."""
    pairs = [list(pair) for pair in _edge_counts(everything, edges)]
    if not pairs:
        raise ValueError(f"{cfg.network_bundle}.trx has no labelled streamline")
    return replace(
        cfg,
        network_bundle="",
        selection=Selection(name=cfg.network_bundle.strip(), kind="edges", pairs=pairs),
    )


def crossing_twice(tracts: td.Tracts, edges: dict[int, dict], midline_x: float) -> int:
    """Same-side streamlines reaching past the midline and back, which labels cannot catch.

    Both ends of such a streamline lie on one side, so any point more than
    :data:`MIDLINE_MARGIN_MM` past the plane ``x = midline_x`` on the far side is the double
    crossing. A QC count over the kept fibres, not a filter.
    """
    side = np.zeros(tracts.n)
    for i, e in enumerate(tracts.dps["edge_id"].tolist()):
        record = edges.get(int(e))
        if record:
            hemis = {
                region_hemi(record["region_a"]),
                region_hemi(record["region_b"]),
            } - {0}
            side[i] = hemis.pop() if len(hemis) == 1 else 0
    x = tracts.points[:, 0].astype(np.float64) - midline_x
    deepest = np.minimum.reduceat(x * side[tracts.streamline_id()], tracts.offsets[:-1])
    return int(np.count_nonzero((side != 0) & (deepest < -MIDLINE_MARGIN_MM)))


def _opposite_record(pm, cfg) -> dict | None:
    """What this selection's preset left out, read from the subject's own network."""
    from tit.tract.presets import PRESETS, opposite_removed, resolve_preset

    preset = next((p for p in PRESETS if p.id == cfg.preset), None)
    path = os.path.join(pm.tractography(cfg.subject_id.strip()), "network.npz")
    if preset is None or not os.path.isfile(path):
        return None
    with np.load(path, allow_pickle=False) as data:
        resolved = resolve_preset(
            preset, [str(n) for n in data["names"]], data["pairs"], data["counts"]
        )
    return opposite_removed(resolved, cfg.selection.pairs)


def _own_as_selection(cfg, everything: td.Tracts, edges: dict[int, dict]):
    """A loaded file, as a selection of every streamline; the labelled edges are its regions."""
    pairs = [list(pair) for pair in _edge_counts(everything, edges)]
    return replace(
        cfg, selection=Selection(name=network_slug(cfg), kind="all", pairs=pairs)
    )


def _apply_setup(cfg, pm, everything: td.Tracts, edges: dict[int, dict]):
    """The config with its network's automatic setup applied, and the setup itself."""
    pick = (
        np.arange(everything.n)
        if cfg.own_network
        else _picked(everything, _edge_ids(edges, cfg.selection.pairs))
    )
    if not len(pick):
        raise ValueError(f"selection {cfg.selection.name!r} picks no streamline here")
    counts = _edge_counts(td.select(everything, pick), edges)
    setup = resolve_network_setup(
        cfg.selection,
        counts,
        cfg.overrides,
        n_unlabelled=everything.n - sum(counts.values()) if cfg.own_network else 0,
    )
    setup["opposite_removed"] = _opposite_record(pm, cfg)
    values = setup["values"]
    return (
        replace(
            cfg,
            lateral_side=int(values["lateral_side"]),
            highlight_regions=list(values["highlight_regions"]),
            max_streamlines=int(values["max_streamlines"]),
            vmax_v_per_m=values["vmax_v_per_m"],
            iso_shell_percentile=values["iso_shell_percentile"],
        ),
        setup,
    )


def _named_network(cfg, pm, everything, edges, glass, log, setup=None):
    """A named network, the streamlines of it to draw, and :func:`export_scene`'s kwargs.

    ``network_from`` <-> ``network_to`` draws every streamline; a selection an even sample of at
    most ``max_streamlines``, never by field, with ``network.json`` saying how many.
    """
    sid = cfg.subject_id.strip()
    selection = cfg.selection
    ids = (
        _edge_ids(edges, selection.pairs)
        if selection
        else edges_between(edges, cfg.network_from, cfg.network_to)
    )
    pick = np.arange(everything.n) if cfg.own_network else _picked(everything, ids)
    if not len(pick):
        raise ValueError(
            f"network_from / network_to join no streamline ({cfg.network_name})"
        )
    network = td.select(everything, pick)
    tracts = network
    if selection and network.n > cfg.max_streamlines:
        rng = np.random.default_rng(cfg.seed)
        tracts = td.select(
            network, np.sort(rng.choice(network.n, cfg.max_streamlines, replace=False))
        )
    removed = setup.get("opposite_removed") if setup else None
    if removed:
        # Both surfaces' mean x sit either side of the plane the hemispheres share.
        midline = float(
            (glass[0][: glass[2]][:, 0].mean() + glass[0][glass[2] :][:, 0].mean()) / 2
        )
        removed["qc_crossing_midline_twice"] = {
            "n": crossing_twice(network, edges, midline),
            "midline_x_mm": midline,
            "margin_mm": MIDLINE_MARGIN_MM,
            "space": "m2m T1 world",
        }
    ends = {r for p in selection.pairs for r in p} if selection else set(cfg.network_to)
    names = sorted(set(cfg.highlight_regions) | ends)
    regions = region_geometry(
        pm.m2m(sid), label_volume(pm, sid), names, glass[0], glass[2]
    )
    log.info(
        f"network {network_slug(cfg)}: {len(ids)} edges, {network.n} streamlines, "
        f"{tracts.n} drawn"
    )
    return (
        network,
        tracts,
        {
            "edges": edges,
            "regions": regions,
            "highlight": list(cfg.highlight_regions),
            "setup": setup,
        },
    )


def _tractogram_name(cfg, sim_dir: str) -> str:
    """What a named network reads: its own bundle when assessed, else ``all.trx``."""
    if cfg.own_network:
        slug = network_slug(cfg)
        path = os.path.join(sim_dir, "tract", slug, f"{slug}.trx")
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"{path} does not exist: assess this file first (the tract job's assess stage)."
            )
        return path
    named = cfg.tractogram.strip()
    if named:
        return named
    bundle = cfg.selection.name if cfg.selection else ""
    if not cfg.selection and not cfg.network_top_edges:
        bundle = (cfg.network_bundle or "").strip()
    if not bundle:
        return ""
    tract_dir = os.path.join(sim_dir, "tract")
    if os.path.isfile(os.path.join(tract_dir, f"{bundle}.trx")):
        return f"{bundle}.trx"
    if cfg.selection and os.path.isfile(os.path.join(tract_dir, "all.trx")):
        return "all.trx"
    raise FileNotFoundError(
        f"{tract_dir} has neither {bundle}.trx nor all.trx: assess this network first "
        "(the tract job's assess stage, with this selection)."
    )


def run_tract(cfg, *, logger_override: logging.Logger | None = None) -> str:
    """Write every output *cfg* asks for; return the output directory."""
    from tit import constants as const
    from tit.paths import get_path_manager

    log = logger_override or logger
    pm = get_path_manager()
    sid, sim = cfg.subject_id.strip(), cfg.simulation_name.strip()
    sim_dir = pm.simulation(sid, sim)
    path = resolve_tractogram(
        os.path.join(sim_dir, "tract"), _tractogram_name(cfg, sim_dir)
    )
    tract_dir = os.path.dirname(path)
    original = cfg
    exports = os.path.join(
        pm.ti_toolbox(), "visual_exports", f"{const.PREFIX_SUBJECT}{sid}", sim
    )
    # Each run its own folder: two started within one second must not share one.
    while True:
        out = network_output_dir(cfg, exports)
        try:
            os.makedirs(out, exist_ok=bool((cfg.output_dir or "").strip()))
            break
        except FileExistsError:
            time.sleep(1)

    summary = {}
    if os.path.isfile(os.path.join(tract_dir, "summary.json")):
        with open(os.path.join(tract_dir, "summary.json"), encoding="utf-8") as stream:
            summary = json.load(stream)
    synthetic = bool(summary.get("synthetic"))
    everything = td.load_trx(path)
    needed = ["ti_along", "ti_max"] + (
        ["ti_avg"]
        if "align_index" in map(str, [cfg.metric, *cfg.extra_metrics])
        else []
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

        viewer = os.path.join(out, "tract_viewer.html")
        write_viewer(
            viewer, tracts, glass[:2], electrodes, edges, title=title, n_total=n_total
        )
        log.info(f"wrote {viewer}")
    if cfg.connectome:
        from tit.plotting.tract_connectome import plot_connectome

        for npz in sorted(glob.glob(os.path.join(tract_dir, "connectome_*.npz"))):
            metric = Path(npz).stem.removeprefix("connectome_")
            png = os.path.join(out, f"connectome_{metric}.png")
            plot_connectome(npz, png, title=title)
            log.info(f"wrote {png}")
    if cfg.stills or cfg.turntable or cfg.propagation:
        from tit.blender.utils import extract_scalp_from_msh

        msh = os.path.join(m2m, f"{sid}.msh")
        scalp = extract_scalp_from_msh(msh) if os.path.isfile(msh) else None
        kwargs = {}
        setup = None
        network = everything
        if cfg.own_network:
            cfg = _own_as_selection(cfg, everything, edges)
        elif (cfg.network_bundle or "").strip() and not cfg.network_top_edges:
            cfg = _bundle_as_selection(cfg, everything, edges)
        if cfg.selection:
            cfg, setup = _apply_setup(cfg, pm, everything, edges)
        if cfg.iso_shell_percentile:
            kwargs["shell"] = ti_iso_shell(
                pm.ti_mesh(sid, sim), cfg.iso_shell_percentile
            )
            log.info(
                f"TI_max iso-shell at {kwargs['shell'][2]:.3f} V/m "
                f"(brain p{cfg.iso_shell_percentile:g})"
            )
        if cfg.network_from or cfg.selection:
            network, tracts, network_kwargs = _named_network(
                cfg, pm, everything, edges, glass, log, setup
            )
            kwargs.update(network_kwargs)
            title = (cfg.network_name or title) + (
                " · synthetic tracts" if cfg.selection and synthetic else ""
            )
            n_total = network.n
        elif cfg.focus:
            network = select_network(cfg, tract_dir, everything, summary)
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
            log.info(
                f"network: {network.n} of {n_total} drawn; {len(names)} endpoint regions"
            )
            kwargs.update(context=context, edges=edges, regions=regions)
            tracts = network
        metrics = network_metrics(
            network, n_total, edges, electrodes, setup, synthetic=synthetic
        )
        if cfg.own_network:
            from tit.tract.own import own_record

            metrics["source"] = own_record(pm, sid, cfg.own_network)
        # Everything above is the network's; only the scene and its render are per colour.
        for index, metric in enumerate([cfg.metric, *cfg.extra_metrics]):
            one = _one_colour(cfg, metric, index == 0)
            manifest = export_scene(
                one,
                tracts,
                glass,
                scalp,
                electrodes,
                os.path.join(out, bundle_folder(one)),
                title=title,
                synthetic=synthetic,
                **kwargs,
            )
            render(manifest)
            with open(manifest, encoding="utf-8") as stream:
                image = image_metrics(json.load(stream))
            image["sampling"] = (
                "all drawn"
                if tracts.n >= n_total
                else "even sample" if cfg.selection else "weighted by ti_along_max"
            )
            write_network_record(
                out,
                one,
                _one_colour(original, metric, index == 0),
                setup,
                metrics,
                image,
            )
            _remove_bundles(one, out, [bundle_folder(one)])
    return out
