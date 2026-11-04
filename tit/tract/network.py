"""Streamline endpoints -> atlas regions, the region connectome, and bundle selection.

Endpoint association re-implements the *method* of STREAM-4D (Atalay, Fecchio & Edlow,
Brain Stimul 18(4):1254, 2025, doi:10.1016/j.brs.2025.06.015): a KD-tree on cortical
surface vertices queried at each streamline end within a fixed radius. No STREAM-4D code is
used (its licence is not GPL-compatible). Two differences: an end takes the *nearest*
labelled point within the radius (one label per end, which a connectome needs) instead of
the union of every vertex within it, and subcortical labels join the same tree as voxel
centres of the label volume.

Region names: ``"<hemi>.<name>"`` for an annotation label (as
:meth:`tit.atlas.mesh.MeshAtlasManager.list_regions` names them), the label table name for
a volume label (``"Left-Thalamus-Proper"``, or ``"ctx-lh-insula"`` from a FastSurfer volume).
"""

from __future__ import annotations

import glob
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

#: FreeSurfer aseg labels that are not a grey-matter region a streamline connects:
#: unknown, cerebral and cerebellar WM, ventricles, CSF, vessels, choroid plexus, WM
#: hypointensities, optic chiasm, corpus callosum segments.
NON_REGION_LABELS = frozenset(
    {0, 2, 4, 5, 7, 14, 15, 24, 30, 31, 41, 43, 44, 46, 62, 63, 72, 77, 78, 79, 80, 85}
    | set(range(251, 256))
)
#: aseg cortex labels, replaced by the annotation when one is used.
_CORTEX_LABELS = frozenset({3, 42})


def _keep_volume_label(value: int, have_annot: bool) -> bool:
    if value in NON_REGION_LABELS or 500 <= value < 1000:  # charm's 5xx: extra-cerebral
        return False
    return not (have_annot and (value in _CORTEX_LABELS or value >= 1000))


def default_label_volume(pm, subject_id: str) -> str | None:
    """charm ``segmentation/labeling.nii.gz``, else FastSurfer/FreeSurfer aparc+aseg."""
    candidates = [
        pm.tissue_labeling(subject_id),
        os.path.join(pm.fastsurfer_mri(subject_id), "aparc.DKTatlas+aseg.deep.nii.gz"),
        os.path.join(pm.freesurfer_mri(subject_id), "aparc.DKTatlas+aseg.mgz"),
    ]
    return next((p for p in candidates if os.path.isfile(p)), None)


def region_points(
    m2m_dir: str,
    label_volume: str | None,
    atlas: str = "DK40",
    surface: str = "central",
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Every labelled point an endpoint can be matched to.

    Returns ``(coords (M, 3) world mm, region (M,) index into names, names)``.

    Raises:
        FileNotFoundError: neither an annotation nor a label volume is available.
    """
    import nibabel as nib
    import nibabel.freesurfer as nfs

    coords, region, names = [], [], []
    have_annot = False
    for hemi in ("lh", "rh"):
        annots = sorted(
            glob.glob(os.path.join(m2m_dir, "segmentation", f"{hemi}.*_{atlas}.annot"))
        )
        surf = os.path.join(m2m_dir, "surfaces", f"{hemi}.{surface}.gii")
        if not annots or not os.path.isfile(surf):
            continue
        have_annot = True
        labels, _, label_names = nfs.read_annot(annots[0])
        verts = nib.load(surf).darrays[0].data.astype(np.float64)
        if len(verts) != len(labels):
            raise ValueError(
                f"{annots[0]} has {len(labels)} labels, {surf} {len(verts)}"
            )
        for k, raw in enumerate(label_names):
            name = raw.decode() if isinstance(raw, bytes) else str(raw)
            sel = labels == k
            if name == "unknown" or not sel.any():
                continue
            coords.append(verts[sel])
            region.append(np.full(sel.sum(), len(names)))
            names.append(f"{hemi}.{name}")

    if label_volume:
        from tit.atlas.segstats import resolve_lut_for_atlas

        img = nib.load(label_volume)
        data = np.asanyarray(img.dataobj)
        data = (data[..., 0] if data.ndim == 4 else data).astype(np.int64)
        lut = resolve_lut_for_atlas(label_volume)
        for value in np.unique(data):
            if not _keep_volume_label(int(value), have_annot):
                continue
            ijk = np.argwhere(data == value).astype(np.float64)
            coords.append(ijk @ img.affine[:3, :3].T + img.affine[:3, 3])
            region.append(np.full(len(ijk), len(names)))
            names.append(lut.get(int(value), f"label-{int(value)}"))

    if not names:
        raise FileNotFoundError(
            f"No {atlas} annotation under {m2m_dir}/segmentation and no label volume: "
            "nothing to match streamline endpoints to."
        )
    return np.concatenate(coords), np.concatenate(region), names


def assign_endpoints(
    endpoints: np.ndarray, coords: np.ndarray, region: np.ndarray, radius: float
) -> np.ndarray:
    """Region index of each endpoint: the nearest labelled point within *radius*, else -1.

    *endpoints* is (..., 3); the result has its leading shape.
    """
    from scipy.spatial import cKDTree

    pts = np.asarray(endpoints, dtype=np.float64)
    dist, idx = cKDTree(coords).query(pts.reshape(-1, 3), distance_upper_bound=radius)
    found = np.isfinite(dist)
    out = np.full(len(idx), -1, dtype=np.int64)
    out[found] = region[idx[found]]
    return out.reshape(pts.shape[:-1])


def edges_from_labels(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Edge of each streamline from its two end labels (S, 2).

    Returns ``(edge_id (S,), pairs (E, 2))``: an edge is an unordered region pair (a <= b),
    edges are numbered by descending streamline count (ties by pair), and a streamline
    with an unassigned end has edge_id -1.
    """
    labels = np.asarray(labels, dtype=np.int64)
    edge_id = np.full(len(labels), -1, dtype=np.int64)
    valid = np.all(labels >= 0, axis=1)
    if not valid.any():
        return edge_id, np.zeros((0, 2), dtype=np.int64)
    pairs = np.sort(labels[valid], axis=1)
    uniq, inv, counts = np.unique(
        pairs, axis=0, return_inverse=True, return_counts=True
    )
    order = np.lexsort((uniq[:, 1], uniq[:, 0], -counts))
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    edge_id[valid] = rank[inv.ravel()]
    return edge_id, uniq[order]


def connectome(
    pairs: np.ndarray, values: np.ndarray, n_regions: int, fill: float = 0.0
) -> np.ndarray:
    """Symmetric region x region matrix with ``values[e]`` at edge ``pairs[e]``."""
    mat = np.full((n_regions, n_regions), fill, dtype=np.float64)
    mat[pairs[:, 0], pairs[:, 1]] = values
    mat[pairs[:, 1], pairs[:, 0]] = values
    return mat


def _region_ids(regions, names: list[str]) -> np.ndarray:
    missing = [r for r in regions if r not in names]
    if missing:
        raise ValueError(f"Unknown region(s) {missing}; the network names {len(names)}")
    return np.array([names.index(r) for r in regions], dtype=np.int64)


def points_in_mask(
    points: np.ndarray, mask_path: str, label: int | None = None
) -> np.ndarray:
    """Whether each world point (P, 3) falls in a voxel of *mask_path* (== label, or > 0)."""
    import nibabel as nib

    img = nib.load(mask_path)
    data = np.asanyarray(img.dataobj)
    data = data[..., 0] if data.ndim == 4 else data
    mask = data == label if label is not None else data > 0
    inv = np.linalg.inv(img.affine)
    vox = np.rint(points @ inv[:3, :3].T + inv[:3, 3]).astype(np.intp)
    ok = np.all((vox >= 0) & (vox < mask.shape), axis=1)
    out = np.zeros(len(points), dtype=bool)
    out[ok] = mask[tuple(vox[ok].T)]
    return out


def select(
    selection,
    labels: np.ndarray,
    names: list[str],
    edge_id: np.ndarray,
    streamlines=None,
) -> np.ndarray:
    """Boolean mask (S,) of the streamlines a :class:`~tit.tract.config.Selection` picks.

    *streamlines* (a sequence of (n, 3) arrays) is needed only for ``"through"``.
    """
    kind = selection.kind
    if kind == "all":
        return np.ones(len(labels), dtype=bool)
    if kind == "through":
        counts = np.array([len(s) for s in streamlines])
        hit = points_in_mask(
            np.concatenate(streamlines), selection.mask_path, selection.label
        )
        return np.logical_or.reduceat(hit, np.r_[0, np.cumsum(counts)[:-1]])
    ids = _region_ids(selection.regions, names)
    if kind == "between":
        a, b = ids[0], ids[1]
        return ((labels[:, 0] == a) & (labels[:, 1] == b)) | (
            (labels[:, 0] == b) & (labels[:, 1] == a)
        )
    if kind == "from":
        return np.isin(labels, ids).any(axis=1)
    # top_edges: the k most-populated edges with one end in regions[0]
    touches = (labels == ids[0]).any(axis=1) & (edge_id >= 0)
    edges, counts = np.unique(edge_id[touches], return_counts=True)
    keep = edges[np.argsort(-counts, kind="stable")[: selection.k]]
    return np.isin(edge_id, keep) & touches


def run_network(subject_id: str, cfg) -> dict:
    """The ``network`` stage: label every streamline end, number the edges, write
    ``network.npz``, ``connectome_count.npz`` and ``network.json`` beside the tractogram.
    """
    import json
    from pathlib import Path

    from tit.paths import get_path_manager

    from .io import load_streamlines

    pm = get_path_manager()
    tract_dir = pm.tractography(subject_id)
    streamlines = load_streamlines(os.path.join(tract_dir, "tractogram.trx"))
    ends = np.stack([np.stack([s[0], s[-1]]) for s in streamlines])
    del streamlines
    volume = cfg.label_volume or default_label_volume(pm, subject_id)
    coords, region, names = region_points(
        pm.m2m(subject_id), volume, cfg.atlas, cfg.surface
    )
    labels = assign_endpoints(ends, coords, region, cfg.radius_mm)
    edge_id, pairs = edges_from_labels(labels)
    counts = np.bincount(edge_id[edge_id >= 0], minlength=len(pairs))
    np.savez_compressed(
        os.path.join(tract_dir, "network.npz"),
        labels=labels,
        edge_id=edge_id,
        pairs=pairs,
        names=np.array(names),
        counts=counts,
    )
    np.savez_compressed(
        os.path.join(tract_dir, "connectome_count.npz"),
        matrix=connectome(pairs, counts, len(names)),
        labels=np.array(names),
        definition="streamlines per edge (unweighted; not a connection strength)",
    )
    record = {
        "subject_id": subject_id,
        "atlas": cfg.atlas,
        "surface": cfg.surface,
        "label_volume": volume,
        "radius_mm": cfg.radius_mm,
        "n_regions": len(names),
        "n_streamlines": int(len(labels)),
        "frac_both_ends_assigned": float(np.mean(edge_id >= 0)),
        "frac_ends_assigned": float(np.mean(labels >= 0)),
        "n_edges": int(len(pairs)),
        "top_edges": [
            {
                "edge_id": e,
                "region_a": names[pairs[e][0]],
                "region_b": names[pairs[e][1]],
                "n_streamlines": int(counts[e]),
            }
            for e in range(min(20, len(pairs)))
        ],
    }
    Path(tract_dir, "network.json").write_text(json.dumps(record, indent=1) + "\n")
    return record
