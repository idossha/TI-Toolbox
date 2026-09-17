"""Reciprocity-search engine: leadfield in, ranked montages out.

Pure NumPy plus ``h5py`` for the leadfield read -- no SimNIBS import at all,
so the whole search is exercisable under the host test suite.  The envelope
comes from :mod:`tit.calc` (the same verified formula the exhaustive searches
use), never from a local reimplementation.

Public API
----------
load_mesh
    Element centroids, tissue tags, electrode names/positions from a
    leadfield HDF5.
read_leadfield
    The leadfield columns for a subset of elements, in V/m per mA.
reciprocity_scores
    Rank every electrode pair by the reciprocity map at the target.
evaluate_candidates
    Score every disjoint combination of the top-ranked pairs.

See Also
--------
tit.opt.recip.recip.run_recip_search : Orchestrates the functions here.
"""

from __future__ import annotations

import itertools
import logging

import numpy as np

#: SimNIBS element tags in a leadfield mesh.
WM_TAG = 1
GM_TAG = 2

#: Seed for the background grey-matter subsample. Fixed so two runs of the
#: same config produce the same ``gm_p95``.
GM_SUBSAMPLE_SEED = 0

logger = logging.getLogger(__name__)


def load_mesh(leadfield_hdf: str) -> dict:
    """Read the geometry and electrode metadata of a leadfield HDF5.

    Parameters
    ----------
    leadfield_hdf : str
        Path to the ``*_leadfield_*.hdf5`` written by ``tit.opt.leadfield``.

    Returns
    -------
    dict
        ``centroids`` (n_elem, 3) element barycentres in subject mm,
        ``tags`` (n_elem,) tissue tags, ``names`` electrode names,
        ``reference`` the reference electrode name, and ``positions``
        (n_elec, 3) electrode positions.
    """
    import h5py

    with h5py.File(leadfield_hdf, "r") as handle:
        group = handle["mesh_leadfield"]
        nodes = group["nodes/node_coord"][:]
        conn = group["elm/node_number_list"][:] - 1
        tags = group["elm/tag1"][:]
        leadfield = group["leadfields/tdcs_leadfield"]
        names = [
            n.decode() if isinstance(n, bytes) else str(n)
            for n in leadfield.attrs["electrode_names"]
        ]
        reference = leadfield.attrs["reference_electrode"]
        if isinstance(reference, bytes):
            reference = reference.decode()
        positions = np.asarray(leadfield.attrs["electrode_pos"], dtype=float)
    return {
        "centroids": nodes[conn].mean(axis=1),
        "tags": np.asarray(tags),
        "names": names,
        "reference": str(reference),
        "positions": positions,
    }


def read_leadfield(
    leadfield_hdf: str, subset: np.ndarray, names: list[str], reference: str
) -> np.ndarray:
    """Leadfield columns for *subset*, one row per electrode, in V/m per mA.

    The stored dataset holds one row per **non-reference** electrode, in
    ``names`` order with the reference omitted, in V/m per 1 A.  The array
    returned here is re-indexed to ``names`` -- the reference electrode's row
    is all zeros, which is what makes a bipolar field a plain row difference.

    Only *subset* is materialised: the full grey matter of an ernie-sized head
    is tens of gigabytes across a 70-electrode net.
    """
    import h5py

    subset = np.asarray(subset, dtype=np.intp)
    result = np.zeros((len(names), len(subset), 3), dtype=np.float32)
    rows = [n for n in names if n != reference]
    with h5py.File(leadfield_hdf, "r") as handle:
        dataset = handle["mesh_leadfield/leadfields/tdcs_leadfield"]
        for row_index, name in enumerate(rows):
            result[names.index(name)] = dataset[row_index][subset] * 1e-3
    return result


def electrode_pairs(n_electrodes: int) -> np.ndarray:
    """Every unordered electrode pair, as an ``(n_pairs, 2)`` index array."""
    return np.array(list(itertools.combinations(range(n_electrodes), 2)), dtype=int)


def reciprocity_scores(
    target_field: np.ndarray, pairs: np.ndarray, direction: np.ndarray | None
) -> np.ndarray:
    """Reciprocity score of every electrode pair at the target.

    *target_field* is the target-averaged leadfield per electrode
    ``(n_elec, 3)``; the score of pair ``(i, j)`` is the magnitude of
    ``F_i - F_j``, or its component along *direction* when one is given.
    With a direction this is exactly the reciprocity map: the best pair is
    ``argmax_i F_i.d`` minus ``argmin_i F_i.d``.
    """
    difference = target_field[pairs[:, 0]] - target_field[pairs[:, 1]]
    if direction is None:
        return np.linalg.norm(difference, axis=1)
    return np.abs(difference @ direction)


def envelope(fields: list[np.ndarray], direction: np.ndarray | None) -> np.ndarray:
    """TI modulation depth of *fields*, optionally along a fixed *direction*.

    Two fields take :func:`tit.calc.get_TI_vectors`' exact Grossman closed
    form; four take the verified mTI envelope.  A *direction* selects the
    directional envelope (SimNIBS ``get_dirTI`` semantics), which is exact for
    either count.
    """
    from tit.calc import get_TI_dir, get_TI_vectors

    if direction is None:
        return np.linalg.norm(get_TI_vectors(fields), axis=1)
    directions = np.broadcast_to(direction, fields[0].shape)
    return get_TI_dir(fields, directions)


def focality_tf(roi_mean: float, gm_p95: float, weight: float) -> float:
    """``roi_mean ** (1 + weight) / gm_p95`` -- the flex ``focality_tf`` goal."""
    if gm_p95 <= 0:
        return 0.0
    return float(roi_mean ** (1.0 + weight) / gm_p95)


def candidate_combinations(pairs: np.ndarray, n_channels: int):
    """Every *n_channels*-combination of *pairs* sharing no electrode."""
    for combination in itertools.combinations(range(len(pairs)), n_channels):
        electrodes = pairs[list(combination)].ravel()
        if len(set(electrodes.tolist())) == 2 * n_channels:
            yield combination


def evaluate_candidates(
    leadfield: np.ndarray,
    pairs: np.ndarray,
    roi_pos: np.ndarray,
    background_pos: np.ndarray,
    n_channels: int,
    current_mA: float,
    direction: np.ndarray | None,
    focality_weight: float,
    progress=None,
) -> list[dict]:
    """Metrics for every disjoint montage built from *pairs*.

    Parameters
    ----------
    leadfield : np.ndarray, shape (n_elec, n_subset, 3)
        Per-electrode field on the evaluation subset, V/m per mA.
    pairs : np.ndarray, shape (n_pairs, 2)
        The reciprocity-ranked pairs to combine (already truncated to
        ``top_k``).
    roi_pos, background_pos : np.ndarray
        Positions within the evaluation subset of the ROI elements and of the
        non-ROI grey-matter elements.
    progress : callable, optional
        Called as ``progress(index, total)`` after each candidate.

    Returns
    -------
    list of dict
        One record per candidate: ``pairs`` (index pairs), ``roi_mean``,
        ``roi_max``, ``roi_min``, ``gm_mean``, ``gm_p95``, ``focality_tf``.
    """
    pair_fields = (leadfield[pairs[:, 0]] - leadfield[pairs[:, 1]]) * current_mA
    combinations = list(candidate_combinations(pairs, n_channels))
    records = []
    for index, combination in enumerate(combinations, start=1):
        depth = envelope([pair_fields[i] for i in combination], direction)
        roi = depth[roi_pos]
        background = depth[background_pos]
        roi_mean = float(roi.mean())
        gm_p95 = float(np.percentile(background, 95)) if len(background) else 0.0
        records.append(
            {
                "pairs": [tuple(int(v) for v in pairs[i]) for i in combination],
                "roi_mean": roi_mean,
                "roi_max": float(roi.max()),
                "roi_min": float(roi.min()),
                "gm_mean": float(background.mean()) if len(background) else 0.0,
                "gm_p95": gm_p95,
                "focality_tf": focality_tf(roi_mean, gm_p95, focality_weight),
            }
        )
        if progress is not None:
            progress(index, len(combinations))
    return records
