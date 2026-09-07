"""fsaverage surface backend for cluster-based permutation stats.

The volumetric engine (:mod:`tit.stats.engine`) clusters voxels with
``scipy.ndimage.label`` on a 3-D grid -- which has no meaning for surface
vertices.  This module is the surface counterpart: it stacks the per-subject
fsaverage field caches written by :func:`tit.source.project_fields_to_fsaverage`
into a ``(n_vertices, n_subjects)`` matrix and runs the *same* statistics with
the *same* cluster conventions, swapping the grid clustering for graph
connected-components over the fsaverage triangle adjacency.

It deliberately **reuses** the engine's space-agnostic kernels
(:func:`~tit.stats.engine.correlation`, :func:`~tit.stats.engine.ttest_ind`,
:func:`~tit.stats.engine.ttest_rel`, :func:`~tit.stats.engine.pval_from_histogram`)
so the surface and volume paths give identical numbers on identical inputs; only
the spatial layer differs.  The volumetric engine is left untouched --
:mod:`tit.stats.permutation` dispatches here when ``config.space == "fsaverage"``.

Cluster conventions mirror the engine exactly: a cluster is a connected set of
vertices with ``p < cluster_threshold`` (sign-restricted for one-sided tests);
singletons (size 1) are ignored; cluster *mass* is the signed sum of t over its
vertices; the null is the per-permutation max cluster stat; per-cluster p-values
come from :func:`~tit.stats.engine.pval_from_histogram`.
"""

from __future__ import annotations

import logging
import os

import numpy as np

from tit.constants import FSAVG_NODES as _FSAVG_NODES
from tit.paths import get_path_manager
from tit.source.config import VALID_FSAVG_FIELDS
from tit.source.fsaverage import _output_path

from .config import CorrelationResult, GroupComparisonResult
from .engine import (
    correlation,
    pval_from_histogram,
    tail_from_alternative,
    tail_statistic,
    ttest_ind,
    ttest_rel,
)

logger = logging.getLogger(__name__)

# fsaverage triangle adjacency is fixed per spacing; build it once.
_ADJ_CACHE: dict[int, "object"] = {}


# ─── data loading ──────────────────────────────────────────────────────────


def load_group_surface_data(
    subjects: list[tuple[str, str]], field: str, spacing: int
) -> tuple[np.ndarray, list[str]]:
    """Stack per-subject fsaverage field caches into ``(n_vertices, n_subjects)``.

    Parameters
    ----------
    subjects : list of (str, str)
        ``(subject_id, simulation_name)`` pairs (bare ids, no ``sub-`` prefix).
    field : str
        Which cached field to load -- one of :data:`VALID_FSAVG_FIELDS`.
    spacing : int
        fsaverage subdivision factor (5, 6, or 7).

    Returns
    -------
    (numpy.ndarray, list of str)
        The ``(n_vertices, n_subjects)`` data matrix and the subject ids in
        column order.
    """
    if field not in VALID_FSAVG_FIELDS:
        raise ValueError(f"Unknown field {field!r}; valid: {VALID_FSAVG_FIELDS}")
    pm = get_path_manager()
    expected = _FSAVG_NODES[spacing]
    columns: list[np.ndarray] = []
    ids: list[str] = []
    for sid, sim in subjects:
        npz_path = _output_path(pm, sid, sim, spacing)
        if not npz_path.exists():
            raise FileNotFoundError(
                f"No fsaverage cache for {sid}/{sim}: {npz_path}. "
                "Run the simulation with map_to_fsavg=True (default) first."
            )
        with np.load(npz_path) as data:
            if field not in data:
                raise KeyError(
                    f"{npz_path.name} has no field {field!r}; "
                    f"available: {[k for k in data.files if k in VALID_FSAVG_FIELDS]}"
                )
            arr = np.asarray(data[field], dtype=np.float64).reshape(-1)
        if arr.shape[0] != expected:
            raise ValueError(
                f"{npz_path.name}: expected {expected} fsaverage{spacing} vertices, "
                f"got {arr.shape[0]}"
            )
        columns.append(arr)
        ids.append(sid)
    return np.column_stack(columns), ids


# ─── fsaverage adjacency ───────────────────────────────────────────────────


def _faces_to_adjacency(faces: np.ndarray, n_nodes: int):
    """Symmetric 0/1 vertex adjacency from triangle faces."""
    from scipy import sparse

    faces = np.asarray(faces)
    edges = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [0, 2]]])
    rows = np.concatenate([edges[:, 0], edges[:, 1]])
    cols = np.concatenate([edges[:, 1], edges[:, 0]])
    adj = sparse.coo_matrix(
        (np.ones(rows.shape[0], dtype=np.int8), (rows, cols)),
        shape=(n_nodes, n_nodes),
    ).tocsr()
    adj.data[:] = 1  # collapse duplicate edges to a single 1
    return adj


def _load_fsaverage_mesh_bundled(spacing: int):
    """Load lh/rh (coords, faces) from the vendored ``resources/fsaverage/``.

    Returns ``None`` (never raises) when the bundled directory is absent, so
    :func:`build_fsaverage_adjacency` can fall through to the nilearn
    download -- e.g. a dev checkout that hasn't vendored the resource.
    """
    import os

    import nibabel as nib

    from tit.paths import resolve_resource_path

    mesh_dir = resolve_resource_path("fsaverage", str(spacing))
    lh_path = os.path.join(mesh_dir, "lh.central.gii")
    rh_path = os.path.join(mesh_dir, "rh.central.gii")
    if not (os.path.isfile(lh_path) and os.path.isfile(rh_path)):
        return None

    lh = nib.load(lh_path)
    rh = nib.load(rh_path)
    coords_l, faces_l = lh.darrays[0].data, lh.darrays[1].data
    coords_r, faces_r = rh.darrays[0].data, rh.darrays[1].data
    return coords_l, faces_l, coords_r, faces_r


def _load_fsaverage_mesh_nilearn(spacing: int):
    """Load lh/rh (coords, faces) via nilearn's runtime-downloaded fsaverage.

    Fallback for a host without the vendored ``resources/fsaverage/``
    directory (see :func:`_load_fsaverage_mesh_bundled`). Requires nilearn
    and network access on first call (nilearn caches the download under
    ``~/nilearn_data/`` after that).
    """
    from nilearn import datasets, surface

    fs = datasets.fetch_surf_fsaverage(f"fsaverage{spacing}")
    coords_l, faces_l = surface.load_surf_mesh(fs["pial_left"])
    coords_r, faces_r = surface.load_surf_mesh(fs["pial_right"])
    return coords_l, faces_l, coords_r, faces_r


def build_fsaverage_adjacency(spacing: int):
    """Block-diagonal lh+rh fsaverage vertex adjacency (cached per spacing).

    No edges cross the hemisphere boundary, so a slow-wave cluster can never
    bridge the two hemispheres through a spurious midline edge -- matching the
    ``[lh; rh]`` node ordering the field caches are written in.

    Mesh source, tried in order (see ``resources/fsaverage/README.md`` for
    why the bundled source is preferred on correctness grounds, not just to
    avoid a download): the vendored ``resources/fsaverage/{spacing}/`` GIFTI
    surfaces (SimNIBS's own bundled fsaverage -- the same source
    :func:`tit.source.fsaverage._compute_fields` projects each subject's
    fields onto, via SimNIBS's ``cross_subject_map``); then nilearn's
    ``fetch_surf_fsaverage`` (a runtime download, the previous sole
    behavior); a :class:`RuntimeError` naming both failed sources if
    neither is available.
    """
    if spacing in _ADJ_CACHE:
        return _ADJ_CACHE[spacing]
    from scipy import sparse

    mesh = _load_fsaverage_mesh_bundled(spacing)
    source = "bundled resources/fsaverage"
    if mesh is None:
        try:
            mesh = _load_fsaverage_mesh_nilearn(spacing)
            source = "nilearn fetch_surf_fsaverage"
        except Exception as exc:
            raise RuntimeError(
                f"No fsaverage{spacing} mesh available: bundled "
                f"resources/fsaverage/{spacing}/ is missing, and the "
                f"nilearn fallback failed ({exc!r}). Vendor the resource "
                "(see resources/fsaverage/README.md) or ensure network "
                "access for nilearn's one-time download."
            ) from exc

    coords_l, faces_l, coords_r, faces_r = mesh
    adj = sparse.block_diag(
        [
            _faces_to_adjacency(faces_l, len(coords_l)),
            _faces_to_adjacency(faces_r, len(coords_r)),
        ]
    ).tocsr()
    if adj.shape[0] != _FSAVG_NODES[spacing]:
        raise ValueError(
            f"fsaverage{spacing} adjacency has {adj.shape[0]} nodes, "
            f"expected {_FSAVG_NODES[spacing]} (mesh source: {source})"
        )
    _ADJ_CACHE[spacing] = adj
    return adj


def _label_graph(mask: np.ndarray, adjacency):
    """Graph analogue of ``ndimage.label``: 1-based component labels (0 = none)."""
    from scipy.sparse.csgraph import connected_components

    labels = np.zeros(mask.shape[0], dtype=int)
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return labels, 0
    n_comp, comp = connected_components(adjacency[idx][:, idx], directed=False)
    labels[idx] = comp + 1
    return labels, n_comp


def _label_graph_signed(mask, t_full, adjacency, alternative):
    """Surface twin of :func:`tit.stats.engine.label_signed`.

    Two touching supra-threshold patches of opposite ``t`` sign are two
    clusters, not one: fusing them makes the signed mass their difference.
    """
    if alternative == "greater":
        return _label_graph(mask & (t_full > 0), adjacency)
    if alternative == "less":
        return _label_graph(mask & (t_full < 0), adjacency)
    pos, n_pos = _label_graph(mask & (t_full > 0), adjacency)
    neg, n_neg = _label_graph(mask & (t_full < 0), adjacency)
    if n_neg:
        sel = neg > 0
        pos[sel] = neg[sel] + n_pos
    return pos, n_pos + n_neg


def _cluster_sizes_masses(labels, n, t_full):
    sizes = np.bincount(labels, minlength=n + 1)[1:]
    masses = np.bincount(labels, weights=t_full, minlength=n + 1)[1:]
    return sizes, masses


def _max_cluster_stat(labels, n, t_full, cluster_stat, tail=0):
    """Max *oriented* stat over multi-vertex clusters (singletons ignored).

    Mirrors the engine: the null is a distribution of maxima, so the statistic
    must be monotone in extremeness (see
    :func:`tit.stats.engine.tail_statistic`).
    """
    if n == 0:
        return 0.0
    sizes, masses = _cluster_sizes_masses(labels, n, t_full)
    multi = sizes > 1
    if not np.any(multi):
        return 0.0
    stats = tail_statistic(sizes, masses, cluster_stat, tail)
    return float(stats[multi].max())


def _null_threshold(null, alpha, n_permutations):
    """Null-derived cluster-statistic cutoff at *alpha* (mirrors the engine)."""
    if null.size == 0:
        return 0.0
    sorted_null = np.sort(null)[::-1]
    ti = max(1, min(int(alpha * n_permutations), len(sorted_null)))
    return float(sorted_null[ti - 1])


def _identify_surface_clusters(
    t_full,
    p_full,
    valid_mask,
    adjacency,
    threshold,
    null_stats,
    cluster_stat,
    alpha,
    alternative,
    r_full=None,
):
    """Surface twin of engine._identify_significant_clusters."""
    mask = (p_full < threshold) & valid_mask
    labels, n = _label_graph_signed(mask, t_full, adjacency, alternative)
    sig_mask = np.zeros(t_full.shape[0], dtype=int)
    if n == 0:
        return sig_mask, [], []

    sizes, masses = _cluster_sizes_masses(labels, n, t_full)
    info = [
        (
            cid,
            int(sizes[cid - 1]),
            float(sizes[cid - 1]) if cluster_stat == "size" else float(masses[cid - 1]),
        )
        for cid in range(1, n + 1)
        if sizes[cid - 1] > 1
    ]
    if not info:
        return sig_mask, [], []

    tail = tail_from_alternative(alternative)
    tail_stats = np.array(
        [
            float(tail_statistic([size], [sv], "mass", tail)[0])
            if cluster_stat != "size"
            else float(size)
            for _, size, sv in info
        ]
    )
    # ``null_stats`` already holds oriented maxima -> always right-tailed.
    pvals = pval_from_histogram(tail_stats, null_stats, tail=1)

    all_observed = [
        {"id": cid, "size": size, "stat_value": sv, "p_value": float(p)}
        for (cid, size, sv), p in zip(info[:10], pvals[:10])
    ]
    sig_clusters = []
    for (cid, size, sv), p in zip(info, pvals):
        if p < alpha:
            verts = np.flatnonzero(labels == cid)
            sig_mask[verts] = 1
            entry = {
                "id": cid,
                "size": size,
                "stat_value": sv,
                "p_value": float(p),
                "vertices": verts.tolist(),
            }
            if r_full is not None:
                entry["peak_r"] = float(np.max(r_full[verts]))
                entry["mean_r"] = float(np.mean(r_full[verts]))
            sig_clusters.append(entry)
    return sig_mask, sig_clusters, all_observed


# ─── runners ───────────────────────────────────────────────────────────────


def _output_dir_and_log(analysis_type, analysis_name, callback_handler):
    # ponytail: reuse the proven helpers; lazy import avoids a module cycle
    # (permutation imports this module to dispatch).
    from .permutation import _resolve_output_dir, _setup_logger

    output_dir = _resolve_output_dir(analysis_type, analysis_name)
    log, log_file = _setup_logger(output_dir, analysis_type, callback_handler)
    return output_dir, log, log_file


def _save_surface_npz(output_dir, **maps):
    path = os.path.join(output_dir, "surface_maps.npz")
    np.savez_compressed(path, **maps)
    return path


def _write_clusters_csv(output_dir, clusters):
    import csv

    path = os.path.join(output_dir, "significant_clusters.csv")
    keys = ["id", "size", "stat_value", "p_value", "peak_r", "mean_r"]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for c in clusters:
            writer.writerow(c)
    return path


def run_surface_correlation(
    config, callback_handler=None, stop_callback=None
) -> CorrelationResult:
    """Vertexwise field-vs-response correlation on the fsaverage surface."""
    import time

    t0 = time.time()
    output_dir, log, log_file = _output_dir_and_log(
        "correlation", config.analysis_name, callback_handler
    )
    log.info(
        "CLUSTER-BASED PERMUTATION TESTING - SURFACE CORRELATION (fsaverage%d)",
        config.fsaverage_spacing,
    )
    log.info(
        "field=%s  corr=%s  stat=%s  thr=%.3f  perms=%d  alpha=%.3f",
        config.fsaverage_field,
        config.correlation_type.value,
        config.cluster_stat.value,
        config.cluster_threshold,
        config.n_permutations,
        config.alpha,
    )

    pairs = [(s.subject_id, s.simulation_name) for s in config.subjects]
    effect = np.array([float(s.effect_size) for s in config.subjects], dtype=np.float64)
    weights = (
        np.array([float(s.weight) for s in config.subjects], dtype=np.float64)
        if config.use_weights
        else None
    )
    data, ids = load_group_surface_data(
        pairs, config.fsaverage_field, config.fsaverage_spacing
    )
    n_nodes = data.shape[0]
    adjacency = build_fsaverage_adjacency(config.fsaverage_spacing)

    # != 0 (not > 0): TI_normal is signed, so a consistently-inward vertex
    # must stay in the analysis; background is exactly 0 for all fields.
    valid_mask = np.any(data != 0, axis=1)
    valid_idx = np.flatnonzero(valid_mask)
    data_valid = data[valid_idx]
    log.info("Subjects=%d  valid vertices=%d/%d", len(ids), valid_idx.size, n_nodes)

    ctype = config.correlation_type.value
    # Pre-rank once for Spearman so each permutation skips re-ranking.
    if ctype == "spearman":
        from scipy.stats import rankdata

        data_valid = np.apply_along_axis(rankdata, 1, data_valid)
        preranked = True
    else:
        preranked = False

    def _maps(eff, w):
        r, t, p = correlation(
            data_valid,
            eff,
            correlation_type=ctype,
            weights=w,
            voxel_data_preranked=preranked,
        )
        r_full = np.zeros(n_nodes)
        t_full = np.zeros(n_nodes)
        p_full = np.ones(n_nodes)
        r_full[valid_idx], t_full[valid_idx], p_full[valid_idx] = r, t, p
        return r_full, t_full, p_full

    r_full, t_full, p_full = _maps(effect, weights)

    log.info("[null] %d permutations", config.n_permutations)
    null = np.empty(config.n_permutations)
    rng = np.random.default_rng()
    for i in range(config.n_permutations):
        if stop_callback and stop_callback():
            raise KeyboardInterrupt("stopped")
        order = rng.permutation(len(ids))
        _, pt, pp = _maps(effect[order], None if weights is None else weights[order])
        labels, n = _label_graph_signed(
            (pp < config.cluster_threshold) & valid_mask, pt, adjacency, "two-sided"
        )
        null[i] = _max_cluster_stat(labels, n, pt, config.cluster_stat.value, tail=0)

    sig_mask, sig_clusters, observed = _identify_surface_clusters(
        t_full,
        p_full,
        valid_mask,
        adjacency,
        config.cluster_threshold,
        null,
        config.cluster_stat.value,
        config.alpha,
        "two-sided",
        r_full=r_full,
    )
    for obs in observed[:5]:
        log.info(
            "  cluster %d: %s=%.2f size=%d p=%.4f",
            obs["id"],
            config.cluster_stat.value,
            obs["stat_value"],
            obs["size"],
            obs["p_value"],
        )

    npz_path = _save_surface_npz(
        output_dir, r=r_full, t=t_full, p=p_full, sig_mask=sig_mask, null=null
    )
    _write_clusters_csv(output_dir, sig_clusters)
    log.info("Saved surface maps -> %s", npz_path)

    return CorrelationResult(
        success=True,
        output_dir=output_dir,
        n_subjects=len(ids),
        n_significant_voxels=int(sig_mask.sum()),
        n_significant_clusters=len(sig_clusters),
        cluster_threshold=_null_threshold(null, config.alpha, config.n_permutations),
        analysis_time=time.time() - t0,
        clusters=sig_clusters,
        log_file=log_file,
    )


def run_surface_group_comparison(
    config, callback_handler=None, stop_callback=None
) -> GroupComparisonResult:
    """Responder-vs-non-responder t-test on the fsaverage surface."""
    import time

    t0 = time.time()
    output_dir, log, log_file = _output_dir_and_log(
        "group_comparison", config.analysis_name, callback_handler
    )
    log.info(
        "CLUSTER-BASED PERMUTATION TESTING - SURFACE GROUP (fsaverage%d)",
        config.fsaverage_spacing,
    )

    # Responders first, then non-responders, so column [:n_resp] are responders.
    resp = [s for s in config.subjects if s.response == 1]
    non = [s for s in config.subjects if s.response == 0]
    ordered = resp + non
    n_resp = len(resp)
    pairs = [(s.subject_id, s.simulation_name) for s in ordered]
    data, ids = load_group_surface_data(
        pairs, config.fsaverage_field, config.fsaverage_spacing
    )
    n_nodes = data.shape[0]
    n_total = data.shape[1]
    adjacency = build_fsaverage_adjacency(config.fsaverage_spacing)

    # != 0 (not > 0): TI_normal is signed, so a consistently-inward vertex
    # must stay in the analysis; background is exactly 0 for all fields.
    valid_mask = np.any(data != 0, axis=1)
    valid_idx = np.flatnonzero(valid_mask)
    data_valid = data[valid_idx]
    paired = config.test_type.value == "paired"
    alt = config.alternative.value
    log.info(
        "resp=%d  non=%d  valid vertices=%d  paired=%s",
        n_resp,
        len(non),
        valid_idx.size,
        paired,
    )

    def _maps(mat):
        if paired:
            t, p = ttest_rel(mat, n_resp, alternative=alt)
        else:
            t, p = ttest_ind(mat, n_resp, n_total - n_resp, alternative=alt)
        t_full = np.zeros(n_nodes)
        p_full = np.ones(n_nodes)
        t_full[valid_idx], p_full[valid_idx] = t, p
        return t_full, p_full

    t_full, p_full = _maps(data_valid)

    log.info("[null] %d permutations", config.n_permutations)
    null = np.empty(config.n_permutations)
    rng = np.random.default_rng()
    for i in range(config.n_permutations):
        if stop_callback and stop_callback():
            raise KeyboardInterrupt("stopped")
        if paired:
            flips = rng.choice([-1.0, 1.0], size=n_resp)
            mean = (data_valid[:, :n_resp] + data_valid[:, n_resp:]) / 2
            diff = (data_valid[:, :n_resp] - data_valid[:, n_resp:]) / 2
            perm = np.empty_like(data_valid)
            perm[:, :n_resp] = mean + flips * diff
            perm[:, n_resp:] = mean - flips * diff
        else:
            perm = data_valid[:, rng.permutation(n_total)]
        pt, pp = _maps(perm)
        labels, n = _label_graph_signed(
            (pp < config.cluster_threshold) & valid_mask, pt, adjacency, alt
        )
        null[i] = _max_cluster_stat(
            labels, n, pt, config.cluster_stat.value, tail=tail_from_alternative(alt)
        )

    sig_mask, sig_clusters, observed = _identify_surface_clusters(
        t_full,
        p_full,
        valid_mask,
        adjacency,
        config.cluster_threshold,
        null,
        config.cluster_stat.value,
        config.alpha,
        alt,
    )
    for obs in observed[:5]:
        log.info(
            "  cluster %d: %s=%.2f size=%d p=%.4f",
            obs["id"],
            config.cluster_stat.value,
            obs["stat_value"],
            obs["size"],
            obs["p_value"],
        )

    npz_path = _save_surface_npz(
        output_dir, t=t_full, p=p_full, sig_mask=sig_mask, null=null
    )
    _write_clusters_csv(output_dir, sig_clusters)
    log.info("Saved surface maps -> %s", npz_path)

    return GroupComparisonResult(
        success=True,
        output_dir=output_dir,
        n_responders=n_resp,
        n_non_responders=len(non),
        n_significant_voxels=int(sig_mask.sum()),
        n_significant_clusters=len(sig_clusters),
        cluster_threshold=_null_threshold(null, config.alpha, config.n_permutations),
        analysis_time=time.time() - t0,
        clusters=sig_clusters,
        log_file=log_file,
    )
