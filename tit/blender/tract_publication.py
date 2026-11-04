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
#: Endpoint-to-cortex radius for the propagation animation's region patches.
PATCH_RADIUS_MM = 5.0
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


def glass_surface(m2m_dir: str) -> tuple[np.ndarray, np.ndarray, str]:
    """Both hemispheres' pial surfaces (central when pial is absent), merged: (V, T, kind)."""
    import nibabel as nib

    surfaces = os.path.join(m2m_dir, "surfaces")
    kind = (
        "pial"
        if all(
            os.path.isfile(os.path.join(surfaces, f"{h}.pial.gii"))
            for h in ("lh", "rh")
        )
        else "central"
    )
    vertices, triangles = [], []
    for hemi in ("lh", "rh"):
        path = os.path.join(surfaces, f"{hemi}.{kind}.gii")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Cortical surface not found: {path}")
        darrays = nib.load(path).darrays
        offset = sum(len(v) for v in vertices)
        vertices.append(np.asarray(darrays[0].data, dtype=np.float64))
        triangles.append(np.asarray(darrays[1].data, dtype=np.int64) + offset)
    return np.concatenate(vertices), np.concatenate(triangles), kind


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


def endpoint_patches(
    surface: np.ndarray,
    tracts: td.Tracts,
    arrive_start: np.ndarray,
    arrive_end: np.ndarray,
    gain: np.ndarray,
    radius: float = PATCH_RADIUS_MM,
) -> tuple[np.ndarray, np.ndarray]:
    """Per surface vertex: the frame a front first lands within *radius*, and how bright.

    Brightness is the largest ``gain * (1 - distance / radius) ** 2`` over the endpoints in
    reach, so a patch fades out toward its rim. Vertices no endpoint reaches get frame ``1e6``
    and brightness 0, so they never light.
    """
    from scipy.spatial import cKDTree

    ends = np.concatenate(
        [tracts.points[tracts.offsets[:-1]], tracts.points[tracts.offsets[1:] - 1]]
    )
    when = np.concatenate([arrive_start, arrive_end])
    strength = np.concatenate([gain, gain])
    frame = np.full(len(surface), 1e6)
    lit = np.zeros(len(surface))
    for i, hits in enumerate(cKDTree(surface).query_ball_point(ends, radius)):
        if hits:
            falloff = 1.0 - np.linalg.norm(surface[hits] - ends[i], axis=1) / radius
            np.minimum.at(frame, hits, when[i])
            np.maximum.at(lit, hits, strength[i] * falloff**2)
    return frame.astype(np.float32), lit.astype(np.float32)


def _simplified(vertices: np.ndarray, triangles: np.ndarray, budget: int):
    from tit.scene.simplify import simplify_to_budget

    result = simplify_to_budget(vertices, triangles, budget)
    return result.vertices.astype(np.float32), result.triangles.astype(np.int32)


def export_scene(
    cfg,
    tracts: td.Tracts,
    n_total: int,
    glass: tuple[np.ndarray, np.ndarray],
    scalp: tuple[np.ndarray, np.ndarray] | None,
    electrodes: list[dict],
    bundle_dir: str,
    *,
    title: str,
    synthetic: bool,
) -> str:
    """Write the Blender bundle for *tracts* (already subsampled); return the manifest path."""
    os.makedirs(bundle_dir, exist_ok=True)
    metric = str(cfg.metric)
    along = tracts.dpv["ti_along"]
    shown = td.vertex_metric(tracts, "ti_along" if metric == "direction" else metric)
    vmax = td.robust_max(shown)
    # Peak, arc and gain come from the full-resolution streamline, then the tube is thinned.
    s = td.arc_length(tracts)
    peak = td.peak_vertex(tracts, along)
    sid = tracts.streamline_id()
    tracts.dpv["d"] = np.abs(s - s[peak][sid]).astype(np.float32)
    along_top = td.robust_max(along)
    gain = np.clip(along[peak] / along_top, 0.0, 1.0)
    tracts.dpv["gain"] = gain[sid].astype(np.float32)
    tracts.dpv["v"] = np.clip(shown / vmax, 0.0, 1.0).astype(np.float32)
    total = s[tracts.offsets[1:] - 1]
    speed = float(cfg.front_speed_mm_per_frame)
    arrive_start = FRONT_START_FRAME + s[peak] / speed
    arrive_end = FRONT_START_FRAME + (total - s[peak]) / speed
    tube = td.decimate(tracts, RENDER_STEP_MM)
    np.savez(
        os.path.join(bundle_dir, "tracts.npz"),
        points=tube.points.astype(np.float32),
        offsets=tube.offsets.astype(np.int64),
        v=tube.dpv["v"],
        d=tube.dpv["d"],
        gain=tube.dpv["gain"],
        tangent=np.abs(td.tangents(tube)).astype(np.float32),
    )

    gv, gt = _simplified(*glass, GLASS_TRIANGLES)
    edge = tracts.dps.get("edge_id")
    assigned = np.flatnonzero(edge >= 0) if edge is not None else np.arange(tracts.n)
    if len(assigned) == 0:
        assigned = np.arange(tracts.n)
    frame, lit = endpoint_patches(
        gv,
        td.select(tracts, assigned),
        arrive_start[assigned],
        arrive_end[assigned],
        gain[assigned],
    )
    np.savez(
        os.path.join(bundle_dir, "glass.npz"),
        vertices=gv,
        triangles=gt,
        frame=frame,
        lit=lit,
    )
    if scalp is not None:
        sv, st = _simplified(*scalp, SCALP_TRIANGLES)
        np.savez(os.path.join(bundle_dir, "scalp.npz"), vertices=sv, triangles=st)

    hot = tracts.points[along >= np.percentile(along, 99)]
    side = -1.0 if hot[:, 0].mean() < gv[:, 0].mean() else 1.0
    label, units = td.METRICS[metric]
    travel = float(np.percentile(np.maximum(arrive_start, arrive_end), 98))
    frames = int(min(FRONT_MAX_FRAMES, np.ceil(travel) + FRONT_HOLD_FRAMES))
    stem = f"{cfg.subject_id}_{cfg.simulation_name}_tract_{metric}"
    manifest = {
        "title": title,
        "synthetic": synthetic,
        "metric": metric,
        "label": label,
        "units": units,
        "vmax": vmax,
        "stops": td.PLASMA_SRGB,
        "n_shown": tracts.n,
        "n_total": int(n_total),
        "lateral_side": side,
        "tracts": "tracts.npz",
        "glass": "glass.npz",
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
    tracts = td.load_trx(path)
    for key in ("ti_along", "ti_max"):
        if key not in tracts.dpv:
            raise ValueError(f"{path} has no data_per_vertex {key!r}")
    n_total = tracts.n
    weight = tracts.dps.get("ti_along_max")
    if weight is None:
        weight = np.maximum.reduceat(tracts.dpv["ti_along"], tracts.offsets[:-1])
    tracts = td.select(tracts, td.subsample(weight, cfg.max_streamlines, cfg.seed))
    log.info(f"{path}: {n_total} streamlines, rendering {tracts.n}")
    edges = td.read_edges(os.path.join(tract_dir, "edges.json"))
    electrodes = simulation_electrodes(sim_dir)
    m2m = pm.m2m(sid)
    glass = glass_surface(m2m)
    title = f"sub-{sid} · {sim}" + (" · synthetic tracts" if synthetic else "")

    if cfg.web:
        from tit.plotting.tract_web import write_viewer

        viewer = os.path.join(out, f"{sid}_{sim}_tract_viewer.html")
        write_viewer(viewer, tracts, glass[:2], electrodes, edges, title=title)
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
        manifest = export_scene(
            cfg,
            tracts,
            n_total,
            glass[:2],
            scalp,
            electrodes,
            os.path.join(out, "tract_scene"),
            title=title,
            synthetic=synthetic,
        )
        render(manifest)
    return out
