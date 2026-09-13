"""Surface label alignment and parcel reduction without study-specific atlases."""

from __future__ import annotations

from pathlib import Path
import numpy as np


def labels_for_vertices(
    annotation_path: str | Path, vertex_ids: np.ndarray
) -> tuple[np.ndarray, list[str]]:
    """Read FreeSurfer annotation labels at explicit native vertex identities."""
    from nibabel.freesurfer.io import read_annot

    labels, _, names = read_annot(str(annotation_path))
    vertices = np.asarray(vertex_ids)
    if vertices.ndim != 1 or not np.issubdtype(vertices.dtype, np.integer):
        raise ValueError("vertex_ids must be a one-dimensional integer array")
    if vertices.size and (vertices.min() < 0 or vertices.max() >= len(labels)):
        raise ValueError("Vertex identity lies outside the annotation")
    return labels[vertices].astype(int), [
        n.decode() if isinstance(n, bytes) else str(n) for n in names
    ]


def nearest_vertex_ids(
    reference_coordinates: np.ndarray,
    query_coordinates: np.ndarray,
    *,
    max_distance: float | None = None,
) -> np.ndarray:
    """Align explicit coordinates in a common frame, optionally bounding distance."""
    from scipy.spatial import cKDTree

    ref, query = np.asarray(reference_coordinates, float), np.asarray(
        query_coordinates, float
    )
    if any(
        a.ndim != 2 or a.shape[1] != 3 or not np.isfinite(a).all() for a in (ref, query)
    ) or not len(ref):
        raise ValueError(
            "Coordinate arrays must be finite N-by-3, with a nonempty reference"
        )
    distances, vertices = cKDTree(ref).query(query, k=1)
    if max_distance is not None and (
        max_distance < 0 or np.any(distances > max_distance)
    ):
        raise ValueError("Surface coordinates exceed the requested alignment tolerance")
    return vertices


def parcel_means(
    values: np.ndarray,
    labels: np.ndarray,
    *,
    region_ids: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    nan_policy: str = "propagate",
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce the final vertex axis to parcels, preserving all preceding axes.

    Unweighted means are the default. Supply vertex areas explicitly for area
    weighting. Negative label IDs are unassigned and omitted by default. Empty
    regions return NaN. Returns (means, region_ids), retaining requested order.
    """
    values, labels = np.asarray(values, float), np.asarray(labels)
    if values.ndim < 1 or labels.ndim != 1 or values.shape[-1] != labels.size:
        raise ValueError("Last values axis must align with the label vector")
    if not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("Labels must be integer region IDs")
    if nan_policy not in {"propagate", "omit", "raise"}:
        raise ValueError("nan_policy must be propagate, omit or raise")
    if nan_policy == "raise" and not np.isfinite(values).all():
        raise ValueError("Values contain nonfinite entries")
    regions = (
        np.unique(labels[labels >= 0]) if region_ids is None else np.asarray(region_ids)
    )
    if regions.ndim != 1 or not np.issubdtype(regions.dtype, np.integer):
        raise ValueError("region_ids must be a one-dimensional integer array")
    if weights is not None:
        weights = np.asarray(weights, float)
        if (
            weights.shape != labels.shape
            or not np.isfinite(weights).all()
            or np.any(weights < 0)
        ):
            raise ValueError(
                "Weights must be finite, nonnegative and aligned with vertices"
            )
    out = np.full(values.shape[:-1] + (regions.size,), np.nan)
    for index, region in enumerate(regions):
        mask = labels == region
        if not mask.any():
            continue
        selected = values[..., mask]
        if weights is None and nan_policy != "omit":
            out[..., index] = selected.mean(axis=-1)
            continue
        w = np.ones(mask.sum()) if weights is None else weights[mask]
        finite = (
            np.isfinite(selected)
            if nan_policy == "omit"
            else np.ones(selected.shape, bool)
        )
        denom = np.sum(w * finite, axis=-1)
        numerator = np.sum(np.where(finite, selected, 0) * w, axis=-1)
        out[..., index] = np.divide(
            numerator, denom, out=np.full(np.shape(numerator), np.nan), where=denom > 0
        )
    return out, regions
