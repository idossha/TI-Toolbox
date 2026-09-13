"""Seeded graph cluster inference over participant-by-feature arrays.

Sensors, source vertices and other features share the same sparse graph API.
No file formats, cohort labels, FEM libraries or plotting dependencies enter
this module. Safe defaults separate opposite signs. ``absolute_connected``
is an explicit compatibility policy for the published sleepTI sensor test.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import sparse, stats


def mannwhitney_z(group_a: np.ndarray, group_b: np.ndarray) -> np.ndarray:
    """NaN-aware U normal score without tie or continuity correction.

    This is the published permutation cluster-forming score, not a SciPy
    tie-corrected asymptotic p-value. Prefer the explicit permutation result."""
    n_group_a = group_a.shape[0]
    combined = np.vstack([group_a, group_b]).astype(
        float
    )  # (n_group_a+n_group_b, n_ch)
    finite = np.isfinite(combined)
    masked = np.where(finite, combined, np.nan)
    ranks = stats.rankdata(masked, axis=0, nan_policy="omit")
    group_a_finite = finite[:n_group_a]
    na = group_a_finite.sum(axis=0).astype(float)
    ns = finite[n_group_a:].sum(axis=0).astype(float)
    rank_sum = np.nansum(np.where(group_a_finite, ranks[:n_group_a], 0.0), axis=0)
    u_value = rank_sum - na * (na + 1.0) / 2.0
    mean_u = na * ns / 2.0
    std_u = np.sqrt(na * ns * (na + ns + 1.0) / 12.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        z_values = np.where(std_u > 0, (u_value - mean_u) / std_u, 0.0)
    z_values[(na < 2) | (ns < 2)] = np.nan
    return z_values


def wilcoxon_z(values: np.ndarray) -> np.ndarray:
    """NaN-aware signed-rank normal score without tie/continuity correction.

    Zeros are excluded (Wilcox rule). The normal score defines permutation
    clusters; it is not a SciPy tie-corrected asymptotic p-value."""
    values = values.astype(float)
    valid = np.isfinite(values) & (values != 0)
    abs_masked = np.where(valid, np.abs(values), np.nan)
    ranks = stats.rankdata(abs_masked, axis=0, nan_policy="omit")
    n_obs = valid.sum(axis=0).astype(float)
    t_plus = np.nansum(np.where(valid & (values > 0), ranks, 0.0), axis=0)
    mean_t = n_obs * (n_obs + 1.0) / 4.0
    std_t = np.sqrt(n_obs * (n_obs + 1.0) * (2.0 * n_obs + 1.0) / 24.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        z_values = np.where(std_t > 0, (t_plus - mean_t) / std_t, 0.0)
    z_values[n_obs < 2] = np.nan
    return z_values


def threshold_mask(z_values: np.ndarray, threshold: float, tail: int) -> np.ndarray:
    finite_z = np.nan_to_num(z_values, nan=0.0)
    if tail > 0:
        return finite_z > threshold
    if tail < 0:
        return finite_z < -threshold
    return np.abs(finite_z) > threshold


def _canonical_graph(adjacency, n_features: int) -> sparse.csr_matrix:
    """Copy connectivity, discarding explicitly stored zero-valued non-edges."""
    graph = sparse.csr_matrix(adjacency, dtype=bool, copy=True)
    graph.sum_duplicates()
    graph.eliminate_zeros()
    graph.sort_indices()
    if graph.shape != (n_features, n_features):
        raise ValueError("adjacency must match the feature dimension")
    if (graph != graph.T).nnz:
        raise ValueError("adjacency must be symmetric")
    return graph


def find_clusters(
    z_values: np.ndarray,
    adjacency: sparse.csr_matrix,
    threshold: float,
    tail: int,
    *,
    sign_policy: str = "separate",
    min_cluster_size: int = 1,
) -> list[np.ndarray]:
    if sign_policy not in ("separate", "absolute_connected") or min_cluster_size < 1:
        raise ValueError("invalid sign policy or minimum cluster size")
    z_values = np.asarray(z_values, dtype=float)
    if z_values.ndim != 1:
        raise ValueError("statistics must be a feature vector")
    adjacency = _canonical_graph(adjacency, z_values.size)
    supra = threshold_mask(z_values, threshold, tail)
    visited: set[int] = set()
    clusters: list[np.ndarray] = []

    for seed in np.where(supra)[0]:
        if int(seed) in visited:
            continue
        queue = [int(seed)]
        visited.add(int(seed))
        cluster: list[int] = []
        while queue:
            node = queue.pop(0)
            cluster.append(node)
            neighbors = adjacency.indices[
                adjacency.indptr[node] : adjacency.indptr[node + 1]
            ]
            for neighbor in neighbors:
                neighbor = int(neighbor)
                if (
                    supra[neighbor]
                    and neighbor not in visited
                    and (
                        sign_policy == "absolute_connected"
                        or np.sign(z_values[neighbor]) == np.sign(z_values[node])
                    )
                ):
                    visited.add(neighbor)
                    queue.append(neighbor)
        if len(cluster) >= min_cluster_size:
            clusters.append(np.asarray(sorted(cluster), dtype=int))
    return clusters


def cluster_mass(z_values: np.ndarray, cluster: np.ndarray, tail: int) -> float:
    cluster_values = np.nan_to_num(z_values[cluster], nan=0.0)
    if tail > 0:
        return float(cluster_values.sum())
    if tail < 0:
        return float(-cluster_values.sum())
    return float(np.abs(cluster_values).sum())


@dataclass(frozen=True)
class GraphClusterResult:
    """Observed statistics, feature-index clusters and max-statistic null."""

    statistic: np.ndarray
    clusters: tuple[np.ndarray, ...]
    pvalues: np.ndarray
    null_distribution: np.ndarray
    significant_mask: np.ndarray
    exact: bool = False


def _validate_graph(data, adjacency):
    values = np.asarray(data, dtype=float)
    if values.ndim != 2 or values.shape[0] < 2:
        raise ValueError("data must contain at least two participant rows")
    return values, _canonical_graph(adjacency, values.shape[1])


def cluster_permutation(
    data: np.ndarray,
    adjacency: sparse.spmatrix,
    *,
    other: np.ndarray | None = None,
    statistic: str = "t",
    n_permutations: int = 5000,
    seed: int = 42,
    threshold_p: float = 0.05,
    alpha: float = 0.05,
    tail: int = 0,
    sign_policy: str = "separate",
    min_cluster_size: int = 1,
) -> GraphClusterResult:
    """Paired-change or independent-group graph cluster permutation test.

    ``data`` is participant differences for a paired/one-sample test; supplying
    ``other`` requests independent groups. ``statistic='rank'`` uses the
    study's NaN-aware signed-rank or U normal score without tie correction;
    ``'t'`` uses SciPy t statistics (pooled variance between groups). Whole
    participant rows are sign-flipped or relabeled together across all features.
    This samples permutations with replacement; use ``mne_cluster_test`` for
    the source pipeline's MNE exact-enumeration/TFCE behavior.
    """
    data, graph = _validate_graph(data, adjacency)
    if (
        n_permutations < 1
        or not 0 < threshold_p < 1
        or not 0 < alpha < 1
        or tail not in (-1, 0, 1)
    ):
        raise ValueError("invalid inference parameters")
    if statistic not in ("t", "rank", "f"):
        raise ValueError("statistic must be t, rank or f")
    if other is not None:
        other, _ = _validate_graph(other, graph)
    if statistic == "f" and (other is None or tail != 1):
        raise ValueError("F requires independent groups and tail=1")
    prob = threshold_p / 2 if tail == 0 else threshold_p
    if statistic == "rank":
        threshold = stats.norm.ppf(1 - prob)
        compute = (
            (lambda x, y: mannwhitney_z(x, y))
            if other is not None
            else (lambda x, y: wilcoxon_z(x))
        )
    elif statistic == "f":
        threshold = stats.f.ppf(1 - prob, 1, data.shape[0] + other.shape[0] - 2)
        compute = lambda x, y: stats.f_oneway(x, y, axis=0).statistic
    else:
        df = data.shape[0] - 1 if other is None else data.shape[0] + other.shape[0] - 2
        threshold = stats.t.ppf(1 - prob, df)
        compute = (
            (lambda x, y: stats.ttest_ind(x, y, axis=0, nan_policy="omit").statistic)
            if other is not None
            else (
                lambda x, y: stats.ttest_1samp(
                    x, 0, axis=0, nan_policy="omit"
                ).statistic
            )
        )

    def clusters_for(observed):
        return find_clusters(
            observed,
            graph,
            threshold,
            tail,
            sign_policy=sign_policy,
            min_cluster_size=min_cluster_size,
        )

    observed = compute(data, other)
    clusters = clusters_for(observed)
    rng = np.random.default_rng(seed)
    null = np.zeros(n_permutations)
    combined = None if other is None else np.vstack([data, other])
    for i in range(n_permutations):
        if combined is None:
            perm = compute(
                data * rng.choice(np.array([-1.0, 1.0]), size=(data.shape[0], 1)), None
            )
        else:
            order = rng.permutation(combined.shape[0])
            perm = compute(
                combined[order[: data.shape[0]]], combined[order[data.shape[0] :]]
            )
        null[i] = max(
            (cluster_mass(perm, c, tail) for c in clusters_for(perm)), default=0.0
        )
    p = np.array(
        [
            (1 + np.sum(null >= cluster_mass(observed, c, tail))) / (n_permutations + 1)
            for c in clusters
        ]
    )
    mask = np.zeros(data.shape[1], bool)
    for c, pv in zip(clusters, p):
        if pv < alpha:
            mask[c] = True
    return GraphClusterResult(observed, tuple(clusters), p, null, mask)


def mne_cluster_test(
    data: np.ndarray,
    adjacency: sparse.spmatrix,
    *,
    other: np.ndarray | None = None,
    n_permutations: int = 5000,
    seed: int = 42,
    tail: int = 0,
    use_tfce: bool = False,
    n_jobs: int = 1,
) -> tuple:
    """Thin MNE source-statistics adapter preserving MNE null conventions.

    One-sample t/sign-flips when ``other`` is absent; MNE's default F/group
    relabeling otherwise. Returns MNE's statistic, clusters, p values, H0 tuple.
    MNE owns automatic exact enumeration at small N. With TFCE enabled, MNE
    owns per-feature interpretation of the returned clusters. Imported lazily.
    """
    data, graph = _validate_graph(data, adjacency)
    from mne.stats import (
        spatio_temporal_cluster_1samp_test,
        spatio_temporal_cluster_test,
    )

    kwargs = dict(
        n_permutations=n_permutations,
        threshold=dict(start=0.0, step=0.2) if use_tfce else None,
        tail=tail,
        adjacency=graph,
        n_jobs=n_jobs,
        seed=seed,
        verbose=False,
        buffer_size=None,
    )
    if other is None:
        return spatio_temporal_cluster_1samp_test(data[:, None, :], **kwargs)
    other, _ = _validate_graph(other, graph)
    return spatio_temporal_cluster_test([data[:, None, :], other[:, None, :]], **kwargs)


def rank_columns(matrix: np.ndarray) -> np.ndarray:
    """Rank each feature across participants, omitting nonfinite observations."""
    return np.apply_along_axis(stats.rankdata, 0, matrix, nan_policy="omit")


def pearson_columns(
    field: np.ndarray, response: np.ndarray, *, published_policy: bool = False
) -> tuple[np.ndarray, np.ndarray]:
    """Paired-column Pearson correlations with complete pairs per feature.

    ``published_policy`` retains the original study handling of exactly perfect
    correlations (p=1); the general default gives p=0 for finite |r|=1.
    """
    field, response = np.asarray(field, float), np.asarray(response, float)
    if field.ndim != 2 or field.shape != response.shape:
        raise ValueError("field and response must share participant × feature shape")
    valid = np.isfinite(field) & np.isfinite(response)
    n = valid.sum(axis=0)
    x, y = np.where(valid, field, np.nan), np.where(valid, response, np.nan)
    xc, yc = x - np.nanmean(x, axis=0, keepdims=True), y - np.nanmean(
        y, axis=0, keepdims=True
    )
    numerator = np.nansum(xc * yc, axis=0)
    denominator = np.sqrt(np.nansum(xc**2, axis=0) * np.nansum(yc**2, axis=0))
    r = np.divide(
        numerator,
        denominator,
        out=np.full(field.shape[1], np.nan),
        where=denominator > 0,
    )
    t = r * np.sqrt(
        np.divide(n - 2, 1 - r**2, out=np.zeros_like(r), where=(1 - r**2) > 0)
    )
    p = 2 * stats.t.sf(np.abs(t), df=np.maximum(n - 2, 1))
    if not published_policy:
        r = np.clip(r, -1.0, 1.0)
        p[np.isfinite(r) & (np.abs(r) >= 1)] = 0.0
    p[n < 4], r[n < 4] = np.nan, np.nan
    return r, p


def correlation_clusters(
    r: np.ndarray,
    p: np.ndarray,
    graph: sparse.csr_matrix,
    *,
    p_threshold: float = 0.05,
    min_vertices: int = 1,
) -> list[dict[str, object]]:
    """Sign-separated graph clusters and correlation-mass summaries."""
    from scipy.sparse.csgraph import connected_components

    r, p = np.asarray(r, dtype=float), np.asarray(p, dtype=float)
    if r.ndim != 1 or p.shape != r.shape:
        raise ValueError("correlation and p values must share a feature vector shape")
    graph = _canonical_graph(graph, r.size)
    clusters = []
    for name, sign in (("positive", r > 0), ("negative", r < 0)):
        mask = np.isfinite(p) & (p < p_threshold) & sign
        if not mask.any():
            continue
        n, labels = connected_components(graph[mask][:, mask])
        nodes = np.flatnonzero(mask)
        for k in range(n):
            c = nodes[labels == k]
            if c.size < min_vertices:
                continue
            clusters.append(
                dict(
                    nodes=c,
                    sign=name,
                    n_vertices=int(c.size),
                    cluster_mass_abs_r=float(np.nansum(np.abs(r[c]))),
                    mean_r=float(np.nanmean(r[c])),
                    max_abs_r=float(np.nanmax(np.abs(r[c]))),
                    min_p=float(np.nanmin(p[c])),
                )
            )
    return clusters


def correlation_permutation_null(
    field: np.ndarray,
    response: np.ndarray,
    graph: sparse.csr_matrix,
    *,
    n_permutations: int,
    rng: np.random.Generator,
    p_threshold: float = 0.05,
    min_vertices: int = 1,
    published_policy: bool = False,
) -> np.ndarray:
    """Whole-response-row permutations; pass preranked arrays for Spearman."""
    null = np.zeros(n_permutations)
    for i in range(n_permutations):
        r, p = pearson_columns(
            field,
            response[rng.permutation(response.shape[0]), :],
            published_policy=published_policy,
        )
        clusters = correlation_clusters(
            r, p, graph, p_threshold=p_threshold, min_vertices=min_vertices
        )
        if clusters:
            null[i] = max(float(c["cluster_mass_abs_r"]) for c in clusters)
    return null


def correlation_cluster_permutation(
    field: np.ndarray,
    response: np.ndarray,
    adjacency: sparse.spmatrix,
    *,
    method: str = "spearman",
    n_permutations: int = 5000,
    seed: int = 42,
    threshold_p: float = 0.05,
    alpha: float = 0.05,
    min_cluster_size: int = 1,
) -> GraphClusterResult:
    """Local field–response graph inference with sum-|rho| cluster mass.

    Both inputs are participant × feature maps. Complete finite arrays are
    required for Spearman so missingness cannot alter the rank population after
    shuffling. Use explicit lower-level helpers for a historical NaN policy.
    """
    field, graph = _validate_graph(field, adjacency)
    response = np.asarray(response, float)
    if response.shape != field.shape or n_permutations < 1 or min_cluster_size < 1:
        raise ValueError("invalid array shape or permutation/cluster count")
    if (
        method not in ("spearman", "pearson")
        or not 0 < threshold_p < 1
        or not 0 < alpha < 1
    ):
        raise ValueError("invalid method or threshold")
    if method == "spearman":
        if not np.isfinite(field).all() or not np.isfinite(response).all():
            raise ValueError("Spearman permutation requires complete finite arrays")
        field, response = rank_columns(field), rank_columns(response)
    r, p = pearson_columns(field, response)
    clusters = correlation_clusters(
        r, p, graph, p_threshold=threshold_p, min_vertices=min_cluster_size
    )
    null = correlation_permutation_null(
        field,
        response,
        graph,
        n_permutations=n_permutations,
        rng=np.random.default_rng(seed),
        p_threshold=threshold_p,
        min_vertices=min_cluster_size,
    )
    pv = np.array(
        [
            (1 + np.sum(null >= c["cluster_mass_abs_r"])) / (n_permutations + 1)
            for c in clusters
        ]
    )
    mask = np.zeros(field.shape[1], bool)
    for c, value in zip(clusters, pv):
        if value < alpha:
            mask[c["nodes"]] = True
    return GraphClusterResult(r, tuple(c["nodes"] for c in clusters), pv, null, mask)


def triangle_adjacency(triangles: np.ndarray, n_nodes: int) -> sparse.csr_matrix:
    edges = np.vstack(
        [
            triangles[:, [0, 1]],
            triangles[:, [1, 2]],
            triangles[:, [2, 0]],
        ]
    )
    row = np.concatenate([edges[:, 0], edges[:, 1]])
    col = np.concatenate([edges[:, 1], edges[:, 0]])
    data = np.ones(row.shape[0], dtype=bool)
    return sparse.coo_matrix((data, (row, col)), shape=(n_nodes, n_nodes)).tocsr()
