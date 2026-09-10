"""Grid vertex clustering — how the GM surface gets under the §S3 budget.

Measured problem (plan §0, re-measured 2026-09-04 in the dev container):
``sub-ernie``'s head mesh has **335 930** grey-matter triangles / 168 952
vertices = 6.06 MB of raw ``TVSC1``. Decision S3 caps a single surface at
150 000 triangles and 3 MB.

**Why vertex clustering and not quadric decimation.** Quadric edge collapse
gives a better surface for the same triangle count, but no library already in
the SimNIBS image can perform it. Measured in the running container on
2026-09-04: ``trimesh`` 5.0.0 and ``meshio`` are installed, but
``Trimesh.simplify_quadric_decimation`` raises
``ModuleNotFoundError: No module named 'fast_simplification'`` (trimesh 5 has
no built-in implementation, it delegates); ``open3d``, ``pymeshlab``, ``vtk``,
``pyvista``, ``pyacvd`` and ``fast_simplification`` are all absent. Adding one
for a form control's backdrop is exactly the dependency decision S3 exists to
refuse.
Grid clustering needs only ``numpy``, is ~0.4 s on the GM surface, and has a
property quadric decimation does not: **every output vertex is an input
vertex**, unmoved. A retained vertex's world position is bit-identical to the
mesh's, so an electrode drawn at its measured coordinate and a region drawn
from a per-vertex label still line up with the surface; and the per-vertex
label array can be carried across by plain index selection instead of a
second nearest-neighbour transfer that would introduce its own error.

The geometric cost is therefore not a displacement of the vertices that
survive (that is exactly 0) but the removal of the ones that do not:
:attr:`SimplifyResult.max_deviation` is the largest distance from any input
vertex to the nearest surviving one — the one-sided Hausdorff distance from
the input vertex set to the output's, computed exactly, in pure ``numpy``,
and checked against an independent ``cKDTree`` measurement on real meshes in
``tests/test_scene_realdata.py``.

Pure ``numpy``: ``scipy`` is a ``MagicMock`` in the host suite, so nothing
here may reach for ``scipy.spatial``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = ["SimplifyResult", "cluster_simplify", "simplify_to_budget", "mean_edge_length"]

#: Guard against a caller passing a cell so small that the flat grid key
#: overflows ``int64``. 2**62 leaves three bits of headroom over the largest
#: product this can produce before the multiply itself wraps.
_MAX_GRID_CELLS = 1 << 62

#: How many times :func:`simplify_to_budget` may grow the cell before giving
#: up and reporting the shortfall. Each round costs ~0.4 s on the GM surface,
#: and the first estimate has landed within one round on every real subject
#: measured (ernie / 101 / MNI152), so four is generous, not a hot loop.
_MAX_ROUNDS = 4


@dataclass(frozen=True)
class SimplifyResult:
    """One clustering pass.

    ``source_index[j]`` is the index, in the *input* vertex array, of output
    vertex ``j`` -- so any per-vertex attribute is carried over with
    ``attr[result.source_index]`` and cannot drift out of alignment.
    """

    vertices: np.ndarray  # (V', 3) float32, a subset of the input positions
    triangles: np.ndarray  # (T', 3) uint32
    source_index: np.ndarray  # (V',) int64 into the input vertex array
    cell: float  # grid cell size in mm, 0.0 when nothing was done
    max_deviation: float  # mm; max over input vertices of the distance to the
    # nearest *output* vertex. 0.0 when nothing was done, because then the
    # output is the input.
    rounds: int = 1

    @property
    def simplified(self) -> bool:
        return self.cell > 0.0


def mean_edge_length(vertices: np.ndarray, triangles: np.ndarray) -> float:
    """Mean triangle-edge length in mm (each edge counted once per triangle)."""
    if triangles.size == 0:
        return 0.0
    v = np.asarray(vertices, dtype=np.float64)
    t = np.asarray(triangles, dtype=np.int64)
    edges = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    return float(np.linalg.norm(v[edges[:, 0]] - v[edges[:, 1]], axis=1).mean())


def cluster_simplify(
    vertices: np.ndarray, triangles: np.ndarray, cell: float
) -> SimplifyResult:
    """Collapse every vertex in a ``cell``-sized grid cube to one of its own.

    The representative of a cluster is the member closest to the cluster's
    centroid -- a deterministic, position-preserving choice (ties broken by
    the lowest input index, so the same mesh always yields the same output
    and the cache fingerprint stays meaningful).
    """
    if not (cell > 0.0):
        raise ValueError(f"cell must be > 0, got {cell}")
    v = np.asarray(vertices, dtype=np.float64)
    t = np.asarray(triangles, dtype=np.int64)
    if v.ndim != 2 or v.shape[1] != 3:
        raise ValueError(f"vertices must be (V, 3), got {v.shape}")
    if t.ndim != 2 or t.shape[1] != 3:
        raise ValueError(f"triangles must be (T, 3), got {t.shape}")

    origin = v.min(axis=0)
    grid = np.floor((v - origin) / cell).astype(np.int64)
    dims = grid.max(axis=0) + 1
    if float(dims[0]) * float(dims[1]) * float(dims[2]) > _MAX_GRID_CELLS:
        raise ValueError(f"cell {cell} makes an unrepresentable grid {tuple(dims)}")
    flat = (grid[:, 0] * dims[1] + grid[:, 1]) * dims[2] + grid[:, 2]
    _, cluster_of = np.unique(flat, return_inverse=True)
    cluster_of = np.asarray(cluster_of, dtype=np.int64).ravel()
    n_clusters = int(cluster_of.max()) + 1 if cluster_of.size else 0

    counts = np.bincount(cluster_of, minlength=n_clusters).astype(np.float64)
    centroid = np.empty((n_clusters, 3), dtype=np.float64)
    for axis in range(3):
        centroid[:, axis] = (
            np.bincount(cluster_of, weights=v[:, axis], minlength=n_clusters) / counts
        )
    offset = v - centroid[cluster_of]
    dist2 = np.einsum("ij,ij->i", offset, offset)

    # Representative = argmin(dist2) within each cluster, lowest index on a
    # tie. lexsort's last key is primary, so this sorts by cluster then by
    # distance, and (being stable) by original index within equal distances.
    order = np.lexsort((np.arange(len(v)), dist2, cluster_of))
    is_first = np.ones(order.shape, dtype=bool)
    is_first[1:] = cluster_of[order[1:]] != cluster_of[order[:-1]]
    representative = order[is_first]  # (n_clusters,), in cluster-id order

    remapped = representative[cluster_of[t]]
    keep = (
        (remapped[:, 0] != remapped[:, 1])
        & (remapped[:, 1] != remapped[:, 2])
        & (remapped[:, 0] != remapped[:, 2])
    )
    remapped = remapped[keep]
    # Two source triangles can collapse onto the same corner triple; drawing
    # both is wasted bandwidth and z-fights. Keep the first occurrence so the
    # survivor's winding is the original mesh's.
    if remapped.size:
        _, first_of = np.unique(np.sort(remapped, axis=1), axis=0, return_index=True)
        remapped = remapped[np.sort(first_of)]

    used, compacted = np.unique(remapped, return_inverse=True)
    compacted = np.asarray(compacted, dtype=np.int64).reshape(-1, 3)
    return SimplifyResult(
        vertices=v[used].astype(np.float32),
        triangles=compacted.astype(np.uint32),
        source_index=used.astype(np.int64),
        cell=float(cell),
        max_deviation=_max_deviation(v, cluster_of, representative, used),
    )


def _max_deviation(
    vertices: np.ndarray,
    cluster_of: np.ndarray,
    representative: np.ndarray,
    used: np.ndarray,
) -> float:
    """Distance from the furthest input vertex to the nearest output vertex.

    For nearly every vertex this is the distance to its own cluster's
    representative. The exception is a cluster whose representative was
    dropped by the compaction above -- every triangle touching it collapsed --
    and *those* vertices are further from the surface than their
    representative was. Measured on ``sub-ernie``: 108 of 70 685 clusters, and
    ignoring them understates the deviation by 2.5 mm to 5.3 mm, which is why
    they are searched exhaustively here instead of being assumed away. They
    are few enough that a brute-force search over the kept vertices costs
    milliseconds and needs no ``scipy`` (which is mocked in the host suite).
    """
    if used.size == 0:  # pragma: no cover - a fully collapsed surface
        return 0.0
    deviation = np.linalg.norm(vertices - vertices[representative[cluster_of]], axis=1)
    survived = np.zeros(len(representative), dtype=bool)
    survived[cluster_of[used]] = True
    orphaned = ~survived[cluster_of]
    if orphaned.any():
        kept = vertices[used]
        query = vertices[orphaned]
        best = np.empty(len(query))
        for start in range(0, len(query), 256):  # bounded peak memory
            block = query[start : start + 256]
            best[start : start + len(block)] = np.linalg.norm(
                block[:, None, :] - kept[None, :, :], axis=2
            ).min(axis=1)
        deviation[orphaned] = best
    return float(deviation.max())


def simplify_to_budget(
    vertices: np.ndarray,
    triangles: np.ndarray,
    max_triangles: int,
    max_bytes: int | None = None,
) -> SimplifyResult:
    """Cluster until the surface fits the budget, or report the shortfall.

    The first cell size is derived, not guessed: clustering a surface of mean
    edge ``e`` with cell ``c`` leaves roughly ``(e/c)**2`` of its triangles,
    so ``c = e * sqrt(T / T_budget)`` is the one-shot estimate. Subsequent
    rounds correct it by the same ratio (plus 2 %, so a round that lands
    exactly on the budget still terminates).

    A surface already inside the budget is returned untouched, with
    ``cell == 0.0`` and ``max_deviation == 0.0`` -- the skin surface (77 032
    triangles) takes this path on every subject measured, and a caller can
    tell the two cases apart with :attr:`SimplifyResult.simplified`.
    """
    v = np.asarray(vertices, dtype=np.float64)
    t = np.asarray(triangles, dtype=np.int64)

    def fits(n_v: int, n_t: int) -> bool:
        if n_t > max_triangles:
            return False
        return max_bytes is None or 12 * n_v + 12 * n_t <= max_bytes

    if fits(len(v), len(t)):
        return SimplifyResult(
            vertices=v.astype(np.float32),
            triangles=t.astype(np.uint32),
            source_index=np.arange(len(v), dtype=np.int64),
            cell=0.0,
            max_deviation=0.0,
            rounds=0,
        )

    budget = max_triangles
    if max_bytes is not None:
        # bytes = 12V + 12T and V ~ T/2 on a closed triangulation, so the
        # byte cap bites at T = max_bytes / 18. Take whichever cap is tighter
        # up front instead of discovering it after a round.
        budget = min(budget, max(1, int(max_bytes // 18)))

    cell = max(mean_edge_length(v, t), 1e-6) * math.sqrt(max(len(t), 1) / budget)
    result = cluster_simplify(v, t, cell)
    for round_no in range(2, _MAX_ROUNDS + 1):
        if fits(len(result.vertices), len(result.triangles)):
            break
        cell *= math.sqrt(len(result.triangles) / budget) * 1.02
        result = cluster_simplify(v, t, cell)
        result = SimplifyResult(
            vertices=result.vertices,
            triangles=result.triangles,
            source_index=result.source_index,
            cell=result.cell,
            max_deviation=result.max_deviation,
            rounds=round_no,
        )
    return result
