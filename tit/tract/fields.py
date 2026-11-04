"""TI fields along streamlines: sample the carrier meshes, compute the metrics, write outputs.

Carrier fields come from ``Simulations/<sim>/high_Frequency/mesh/<sid>_TDCS_<k>_<cond>.msh``
(element field ``E``, V/m, constant per tetrahedron, full head); 2 meshes for TI, 2K for
mTI, paired in name order as the simulator writes them.

Sampling methods (spec V2):

* ``"tet"`` -- the tetrahedron containing each point
  (``Msh.find_tetrahedron_with_points``) and its element value: exact for a
  piecewise-constant element field;
* ``"linear"`` -- SimNIBS ``ElementData.interpolate_scattered(method="linear")``: element
  values averaged to the nodes of each tissue, then barycentric interpolation.

Both search only the brain tissues (WM, GM, CSF); a point outside them gets a zero field
and is counted in ``summary.json`` (``points_outside_brain_mesh``).

Output, per simulation, in ``Simulations/<sim>/tract/`` (the data contract):

* ``<selection>.trx`` -- the resampled streamlines (m2m T1 world RAS mm) with
  data_per_vertex ``ti_along``, ``ti_max``, ``e1_par``, ``e2_par`` (... ``e<2K>_par`` for
  mTI; float32, V/m) and data_per_streamline ``length_mm``, ``ti_along_max``,
  ``ti_along_mean``, ``edge_id`` (int, -1 = unassigned);
* ``edges.json`` -- edge_id -> region_a, region_b, n_streamlines, summary statistics;
* ``connectome_<metric>.npz`` -- ``matrix``, ``labels``, ``definition``;
* ``summary.json``; plus ``streamline_metrics.npz`` (every per-streamline metric, keyed by
  tractogram index) and ``profiles.npz`` (per-edge along-tract node medians).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import numpy as np

from . import geometry
from .io import load_streamlines, save_tractogram
from .network import select

logger = logging.getLogger(__name__)

#: Brain tissue tags (SimNIBS ElementTags WM, GM, CSF) the point search is limited to.
BRAIN_TAGS = (1, 2, 3)
#: Metrics summarised per streamline (each with geometry.streamline_stats).
STREAMLINE_METRICS = ("ti_along", "ti_max", "align", "e_par_pk", "p_par", "f_am")
#: Per-streamline keys summarised per edge in edges.json.
EDGE_KEYS = (
    "length_mm",
    "ti_along_mean",
    "ti_along_max",
    "ti_max_mean",
    "align_mean",
    "f_am_max",
)


def carrier_meshes(pm, subject_id: str, simulation: str) -> list[Path]:
    """The channel meshes of a simulation, in pairing order (2 for TI, 2K for mTI).

    Raises:
        FileNotFoundError: fewer than two, or an odd number of, channel meshes.
        ValueError: the run recorded itself as carrier-only (no envelope to assess).
    """
    sim_dir = Path(pm.simulation(subject_id, simulation))
    paths = sorted(
        p
        for p in (sim_dir / "high_Frequency" / "mesh").glob("*_TDCS_*.msh")
        if not p.name.startswith("._")
    )
    if len(paths) < 2 or len(paths) % 2:
        raise FileNotFoundError(
            f"{simulation}: expected an even number (>= 2) of carrier meshes in "
            f"{sim_dir}/high_Frequency/mesh, found {len(paths)}"
        )
    config = sim_dir / "documentation" / "config.json"
    if config.is_file() and json.loads(config.read_text()).get("carrier_only") is True:
        raise ValueError(f"{simulation} is a carrier-only run; it has no TI envelope")
    return paths


def sample_carriers(paths, points: np.ndarray, method: str = "tet", cache=None):
    """Each carrier's ``E`` (P, 3) at *points*; returns ``(fields, outside (P,) bool)``.

    *cache* (a dict, ``"tet"`` only) keeps the point -> element lookup for the next call
    on the same points and the same mesh (several simulations of one head model).
    """
    from simnibs.mesh_tools import mesh_io

    fields, th, outside = [], None, None
    cache = {} if cache is None else cache
    for path in paths:
        mesh = mesh_io.read_msh(str(path)).crop_mesh(tags=list(BRAIN_TAGS))
        field = mesh.field["E"]
        if method == "tet":
            key = (len(points), mesh.elm.nr, float(mesh.nodes.node_coord.sum()))
            if cache.get("key") != key:
                if th is not None:
                    raise ValueError(f"{path.name} is not on the first carrier's mesh")
                cache["key"] = key
                cache["th"] = mesh.find_tetrahedron_with_points(
                    points, compute_baricentric=False
                )
            th = cache["th"]
            outside = th < 1
            values = np.zeros((len(points), 3))
            values[~outside] = field.value[th[~outside] - 1]
        else:
            values = np.asarray(
                field.interpolate_scattered(points, method="linear", squeeze=False),
                dtype=np.float64,
            )
            bad = ~np.isfinite(values).all(axis=1)
            outside = bad if outside is None else outside | bad
            values[bad] = 0.0
        fields.append(values)
        del mesh, field
    return fields, outside


def subset(offsets: np.ndarray, pick: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Point indices and new offsets of the streamlines *pick* (indices) of a set."""
    counts = np.diff(offsets)[pick]
    idx = (
        np.concatenate([np.arange(offsets[i], offsets[i + 1]) for i in pick])
        if len(pick)
        else np.zeros(0, np.intp)
    )
    return idx, np.r_[0, np.cumsum(counts)].astype(np.intp)


def streamline_table(metrics, offsets, h, kappa, thresholds) -> dict[str, np.ndarray]:
    """Every per-streamline array: ``length_mm``, ``kappa_max`` and ``<metric>_<stat>``."""
    table = {
        "length_mm": geometry.lengths(offsets, h),
        "kappa_max": np.maximum.reduceat(kappa, offsets[:-1]),
    }
    for name in STREAMLINE_METRICS:
        taus = thresholds if name == "ti_along" else ()
        for stat, v in geometry.streamline_stats(
            metrics[name], offsets, h, taus
        ).items():
            table[f"{name}_{stat}"] = v
    return table


def _edge_records(table, edge_id, pairs, names, thresholds) -> dict:
    records = {}
    order = np.argsort(edge_id, kind="stable")
    ids, starts = np.unique(edge_id[order], return_index=True)
    for e, rows in zip(ids, np.split(order, starts[1:])):
        if e < 0:
            continue
        stats = geometry.bundle_summary({k: table[k][rows] for k in EDGE_KEYS}, ())
        for tau in thresholds:
            stats[f"frac_streamlines_ti_along_max_ge_{tau:g}"] = float(
                np.mean(table["ti_along_max"][rows] >= tau)
            )
        a, b = pairs[e]
        records[str(int(e))] = {"region_a": names[a], "region_b": names[b], **stats}
    return records


def _profiles(values, offsets, n_nodes):
    flips = geometry.orientation_flips(values["points"], offsets)
    return {
        k: geometry.profiles(values[k], offsets, n_nodes, flips)
        for k in ("ti_along", "ti_max")
    }


def assess_simulation(
    subject_id: str,
    simulation: str,
    cfg,
    network,
    masks: dict[str, np.ndarray],
    resampled,
    cache: dict | None = None,
) -> dict:
    """Assess one simulation on the union of the selected streamlines; write its outputs.

    *resampled* is ``(union_idx, (points, offsets, h, tangents, curvature))`` from
    :func:`run_assess`; *cache* is passed on to :func:`sample_carriers`.
    """
    from tit.paths import get_path_manager

    pm = get_path_manager()
    union_idx, (pts, off, h, t, kappa) = resampled
    out_dir = pm.ensure(pm.sim_tract(subject_id, simulation))
    t0 = time.time()
    paths = carrier_meshes(pm, subject_id, simulation)
    fields, outside = sample_carriers(paths, pts, cfg.method, cache)
    sample_s = time.time() - t0
    m = geometry.point_metrics(fields, t, off, h)
    table = streamline_table(m, off, h, kappa, cfg.thresholds)
    names = [str(n) for n in network["names"]]
    edge_id = network["edge_id"][union_idx]
    pairs = network["pairs"]
    table["edge_id"] = edge_id
    table["label_a"], table["label_b"] = network["labels"][union_idx].T
    table["tractogram_index"] = union_idx

    ref = pm.t1(subject_id)
    pos = {i: k for k, i in enumerate(union_idx)}
    bundles = {}
    for sel in cfg.selections:
        pick = np.array([pos[i] for i in np.flatnonzero(masks[sel.name])], np.intp)
        idx, sub_off = subset(off, pick)
        dpv = {"ti_along": m["ti_along"][idx], "ti_max": m["ti_max"][idx]}
        for c, e_par in enumerate(m["e_par"], start=1):
            dpv[f"e{c}_par"] = e_par[idx]
        sub_pts = pts[idx]
        save_tractogram(
            os.path.join(out_dir, f"{sel.name}.trx"),
            [sub_pts[a:b] for a, b in zip(sub_off[:-1], sub_off[1:])],
            ref,
            data_per_vertex=dpv,
            data_per_streamline={
                "length_mm": table["length_mm"][pick],
                "ti_along_max": table["ti_along_max"][pick],
                "ti_along_mean": table["ti_along_mean"][pick],
                "edge_id": edge_id[pick],
            },
        )
        summary = geometry.bundle_summary({k: table[k][pick] for k in EDGE_KEYS}, ())
        for tau in cfg.thresholds:
            summary[f"frac_streamlines_ti_along_max_ge_{tau:g}"] = float(
                np.mean(table["ti_along_max"][pick] >= tau)
            )
        if len(pick):
            prof = _profiles(
                {
                    "points": sub_pts,
                    "ti_along": dpv["ti_along"],
                    "ti_max": dpv["ti_max"],
                },
                sub_off,
                cfg.profile_points,
            )
            summary["profile_median"] = {
                k: np.median(v, axis=0).round(5).tolist() for k, v in prof.items()
            }
        bundles[sel.name] = {"selection": sel.kind, "regions": sel.regions, **summary}

    edges = _edge_records(table, edge_id, pairs, names, cfg.thresholds)
    Path(out_dir, "edges.json").write_text(json.dumps(edges, indent=1) + "\n")
    _write_connectomes(out_dir, table, edge_id, pairs, names)
    _write_edge_profiles(out_dir, pts, off, m, edge_id, cfg.profile_points)
    np.savez_compressed(os.path.join(out_dir, "streamline_metrics.npz"), **table)

    summary = {
        "subject_id": subject_id,
        "simulation": simulation,
        "space": "m2m T1 world, RAS mm",
        "carriers": [p.name for p in paths],
        "n_pairs": len(paths) // 2,
        "method": cfg.method,
        "step_mm": cfg.step_mm,
        "thresholds_v_per_m": list(cfg.thresholds),
        "n_streamlines": int(len(union_idx)),
        "n_points": int(len(pts)),
        "points_outside_brain_mesh": int(outside.sum()),
        "seconds": {
            "sampling": round(sample_s, 1),
            "total": round(time.time() - t0, 1),
        },
        "units": {
            "ti_along, ti_max, e_par, e_par_pk": "V/m",
            "p_par": "V^2/m^2",
            "f_am, f": "V/m^2",
            "align": "1 (ti_along / ti_max)",
            "length_mm": "mm",
            "kappa_max": "1/mm",
        },
        "bundles": bundles,
    }
    Path(out_dir, "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def _write_connectomes(out_dir, table, edge_id, pairs, names) -> None:
    n = len(names)
    valid = edge_id >= 0
    counts = np.bincount(edge_id[valid], minlength=len(pairs)).astype(float)
    sums = np.bincount(
        edge_id[valid], weights=table["ti_along_mean"][valid], minlength=len(pairs)
    )
    medians = np.zeros(len(pairs))
    order = np.argsort(edge_id[valid], kind="stable")
    ids, starts = np.unique(edge_id[valid][order], return_index=True)
    for e, rows in zip(ids, np.split(order, starts[1:])):
        medians[e] = np.median(table["ti_along_max"][valid][rows])
    has = counts > 0
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=has)
    for metric, values, definition in (
        (
            "count",
            counts,
            "streamlines per edge (unweighted; not a connection strength)",
        ),
        (
            "ti_along_mean",
            means,
            "mean over the edge's streamlines of each streamline's arc-length mean "
            "ti_along (V/m)",
        ),
        (
            "ti_along_max",
            medians,
            "median over the edge's streamlines of each streamline's maximum ti_along (V/m)",
        ),
    ):
        np.savez_compressed(
            os.path.join(out_dir, f"connectome_{metric}.npz"),
            matrix=_matrix(pairs[has], values[has], n),
            labels=np.array(names),
            definition=definition,
        )


def _matrix(pairs, values, n):
    from .network import connectome

    return connectome(pairs, values, n)


def _write_edge_profiles(out_dir, pts, off, m, edge_id, n_nodes) -> None:
    ids, rows_ti, rows_max = [], [], []
    for e in np.unique(edge_id[edge_id >= 0]):
        pick = np.flatnonzero(edge_id == e)
        idx, sub = subset(off, pick)
        prof = _profiles(
            {
                "points": pts[idx],
                "ti_along": m["ti_along"][idx],
                "ti_max": m["ti_max"][idx],
            },
            sub,
            n_nodes,
        )
        ids.append(e)
        rows_ti.append(np.median(prof["ti_along"], axis=0))
        rows_max.append(np.median(prof["ti_max"], axis=0))
    np.savez_compressed(
        os.path.join(out_dir, "profiles.npz"),
        edge_id=np.array(ids, dtype=np.int64),
        ti_along_median=np.array(rows_ti).reshape(-1, n_nodes),
        ti_max_median=np.array(rows_max).reshape(-1, n_nodes),
    )


def load_network(subject_id: str) -> dict:
    """The network stage's ``network.npz`` (labels, edge_id, pairs, names)."""
    from tit.paths import get_path_manager

    path = os.path.join(get_path_manager().tractography(subject_id), "network.npz")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{path} not found; run the network stage first")
    with np.load(path) as data:
        return {k: data[k] for k in data.files}


def run_assess(subject_id: str, cfg) -> list[dict]:
    """The ``assess`` stage over every simulation in *cfg*."""
    from tit.paths import get_path_manager

    pm = get_path_manager()
    tract_dir = pm.tractography(subject_id)
    streamlines = load_streamlines(os.path.join(tract_dir, "tractogram.trx"))
    network = load_network(subject_id)
    if len(network["labels"]) != len(streamlines):
        raise ValueError(
            "network.npz does not match tractogram.trx; rerun the network stage"
        )
    names = [str(n) for n in network["names"]]
    masks = {
        s.name: select(s, network["labels"], names, network["edge_id"], streamlines)
        for s in cfg.selections
    }
    union_idx = np.flatnonzero(np.logical_or.reduce(list(masks.values())))
    logger.info(f"assess: {len(union_idx)} streamlines in {list(masks)}")
    pts, off, h = geometry.resample([streamlines[i] for i in union_idx], cfg.step_mm)
    del streamlines
    t = geometry.tangents(pts, off, h)
    kappa = geometry.curvature(t, off, h)
    resampled = (union_idx, (pts, off, h, t, kappa))
    cache: dict = {}
    return [
        assess_simulation(subject_id, sim, cfg, network, masks, resampled, cache)
        for sim in cfg.simulations
    ]
