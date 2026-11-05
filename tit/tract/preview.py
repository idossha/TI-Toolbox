"""The streamlines a run-page pane draws: a bounded, uniform subsample of each edge.

Uniform on purpose, not weighted by any field: there is no field while a target is being chosen,
and a display that favoured one would favour a metric. Only numpy and the standard library
(through :mod:`tit.blender.tract_data`'s TRX reader) are imported.
"""

from __future__ import annotations

import numpy as np

#: Per-edge streamline and point-spacing budgets of the pane (at most 64 edges are requested).
PER_EDGE = 100
STEP_MM = 2.0


def edge_streamlines(edge_id: np.ndarray, per_edge: int) -> np.ndarray:
    """Up to *per_edge* streamline indices per edge, drawn uniformly, seeded by the edge id."""
    edge_id = np.asarray(edge_id)
    chosen = []
    for edge in np.unique(edge_id[edge_id >= 0]):
        members = np.flatnonzero(edge_id == edge)
        if len(members) > per_edge:
            rng = np.random.default_rng(int(edge))
            members = np.sort(rng.choice(members, per_edge, replace=False))
        chosen.append(members)
    return np.concatenate(chosen) if chosen else np.zeros(0, dtype=np.int64)


def build_preview(
    trx_path: str, edge_id: np.ndarray, per_edge: int, step_mm: float
) -> dict[str, np.ndarray]:
    """``points``, ``offsets``, ``index`` (tractogram) and ``edge`` of the subsample.

    Raises:
        ValueError: the tractogram and the network disagree on the streamline count.
    """
    from tit.blender.tract_data import decimate, load_trx, select

    tracts = load_trx(trx_path)
    if tracts.n != len(edge_id):
        raise ValueError(
            f"{trx_path} has {tracts.n} streamlines, the network {len(edge_id)}: "
            "run the network stage again."
        )
    index = edge_streamlines(edge_id, per_edge)
    kept = decimate(select(tracts, index), step_mm)
    return {
        "points": kept.points,
        "offsets": kept.offsets,
        "index": index,
        "edge": np.asarray(edge_id)[index],
    }


def slice_edges(
    preview: dict[str, np.ndarray], edges: list[int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(points, offsets, index, group)`` of *edges*, ``group`` being the position in *edges*."""
    positions = {int(e): i for i, e in enumerate(edges)}
    wanted = np.flatnonzero(np.isin(preview["edge"], list(positions)))
    offsets = preview["offsets"]
    lengths = offsets[wanted + 1] - offsets[wanted]
    new_offsets = np.r_[0, np.cumsum(lengths)].astype(np.int64)
    vertex = np.repeat(offsets[wanted] - new_offsets[:-1], lengths) + np.arange(
        new_offsets[-1]
    )
    group = np.array(
        [positions[int(e)] for e in preview["edge"][wanted]], dtype=np.int64
    )
    return preview["points"][vertex], new_offsets, preview["index"][wanted], group
