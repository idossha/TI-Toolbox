"""Reciprocity search for TI stimulation.

Public API: ``run_recip_search(config) -> RecipResult``
"""

from __future__ import annotations

import logging
import os
import time

import numpy as np

from tit.logger import add_file_handler
from tit.opt.config import DEFAULT_TOP_K, RecipConfig, RecipResult
from tit.paths import get_path_manager

from .engine import (
    GM_SUBSAMPLE_SEED,
    GM_TAG,
    electrode_pairs,
    evaluate_candidates,
    load_mesh,
    read_leadfield,
    reciprocity_scores,
)
from .results import write_outputs


def run_recip_search(config: RecipConfig) -> RecipResult:
    """Run reciprocity search from a typed config object."""
    from tit import constants as const
    from tit.telemetry import track_operation

    with track_operation(const.TELEMETRY_OP_RECIP_SEARCH):
        return _run_recip_search_inner(config)


def _run_recip_search_inner(config: RecipConfig) -> RecipResult:
    """Inner implementation of :func:`run_recip_search` (unwrapped)."""
    pm = get_path_manager()

    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(
        logs_dir, f'recip_search_{time.strftime("%Y%m%d_%H%M%S")}.log'
    )
    logger_name = f"tit.opt.recip_search.{config.subject_id}"
    add_file_handler(log_file, logger_name=logger_name)
    logger = logging.getLogger(logger_name)

    logger.info("%s", "=" * 60)
    logger.info("TI Reciprocity Search")
    logger.info("%s", "=" * 60)
    logger.info("Project: %s", pm.project_dir)
    logger.info("Subject: %s", config.subject_id)

    run_name = config.run_name or time.strftime("%Y%m%d_%H%M%S")
    output_dir = pm.recip_search_run(config.subject_id, run_name)
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Output: %s", output_dir)

    leadfield_path = config.leadfield_hdf
    if not os.path.isabs(leadfield_path):
        leadfield_path = os.path.join(
            pm.leadfields(config.subject_id), config.leadfield_hdf
        )
    logger.info("Leadfield: %s", leadfield_path)

    started = time.perf_counter()
    mesh = load_mesh(leadfield_path)
    centroids = mesh["centroids"]
    logger.info(
        "Mesh: %d elements, %d electrodes (reference %s) in %.1fs",
        len(centroids),
        len(mesh["names"]),
        mesh["reference"],
        time.perf_counter() - started,
    )

    m2m_path = pm.m2m(config.subject_id)
    target_mask = _target_mask(config, centroids, m2m_path, output_dir, logger)
    n_target = int(target_mask.sum())
    if n_target == 0:
        raise ValueError(
            "the reciprocity target selects no mesh element; check the "
            "coordinates, radius or atlas labels"
        )
    target_centroid = centroids[target_mask].mean(axis=0)
    logger.info(
        "Target: %d elements, centroid %s", n_target, np.round(target_centroid, 1)
    )

    subset, roi_pos, background_pos = _evaluation_subset(
        target_mask, mesh["tags"], config.gm_subsample
    )
    logger.info(
        "Evaluation subset: %d elements (%d target, %d background GM)",
        len(subset),
        len(roi_pos),
        len(background_pos),
    )

    read_started = time.perf_counter()
    leadfield = read_leadfield(leadfield_path, subset, mesh["names"], mesh["reference"])
    read_seconds = time.perf_counter() - read_started
    logger.info("Leadfield subset read in %.1fs", read_seconds)

    direction = _direction(config, pm, logger)

    recip_started = time.perf_counter()
    pairs = electrode_pairs(len(mesh["names"]))
    target_field = leadfield[:, roi_pos, :].mean(axis=1)
    scores = reciprocity_scores(target_field, pairs, direction)
    order = np.argsort(-scores)
    recip_seconds = time.perf_counter() - recip_started
    top_k = config.top_k or DEFAULT_TOP_K[config.n_channels]
    top_k = min(top_k, len(pairs))
    logger.info(
        "Reciprocity map over %d pairs in %.3fs; keeping the top %d",
        len(pairs),
        recip_seconds,
        top_k,
    )
    top_pairs = pairs[order[:top_k]]

    eval_started = time.perf_counter()

    def progress(index: int, total: int) -> None:
        if index == 1 or index == total or index % 50 == 0:
            logger.info("[%d/%d] candidates evaluated", index, total)

    candidates = evaluate_candidates(
        leadfield,
        top_pairs,
        roi_pos,
        background_pos,
        config.n_channels,
        config.current_mA,
        direction,
        config.focality_weight,
        progress=progress,
    )
    eval_seconds = time.perf_counter() - eval_started
    if not candidates:
        raise ValueError(
            "no montage candidate survives the disjoint-electrode filter; "
            "raise top_k"
        )
    logger.info(
        "Evaluated %d candidates in %.1fs (%.3fs each)",
        len(candidates),
        eval_seconds,
        eval_seconds / len(candidates),
    )

    sort_key = "roi_mean" if config.objective == "intensity" else "focality_tf"
    candidates.sort(key=lambda record: -record[sort_key])
    for rank, record in enumerate(candidates, start=1):
        record["rank"] = rank
    best = candidates[0]
    logger.info(
        "Best montage: %s  roi_mean=%.4f V/m  gm_p95=%.4f  focality_tf=%.4f",
        " / ".join(f"{mesh['names'][a]}-{mesh['names'][b]}" for a, b in best["pairs"]),
        best["roi_mean"],
        best["gm_p95"],
        best["focality_tf"],
    )

    timings = {
        "leadfield_read_s": round(read_seconds, 3),
        "reciprocity_s": round(recip_seconds, 4),
        "candidate_evaluation_s": round(eval_seconds, 3),
        "total_s": round(time.perf_counter() - started, 3),
    }
    outputs = write_outputs(
        config=config,
        output_dir=output_dir,
        mesh=mesh,
        pairs=pairs,
        scores=scores,
        order=order,
        top_k=top_k,
        candidates=candidates,
        target_centroid=target_centroid,
        n_target_elements=n_target,
        direction=direction,
        timings=timings,
        leadfield_path=leadfield_path,
        logger=logger,
    )

    return RecipResult(
        success=True,
        output_dir=output_dir,
        n_candidates=len(candidates),
        best=outputs["best"],
        results_csv=outputs["candidates_csv"],
        config_json=outputs["summary_json"],
    )


def _direction(config: RecipConfig, pm, logger) -> np.ndarray | None:
    """The unit target direction in subject space, or ``None``."""
    if config.direction is None:
        return None
    direction = np.asarray(config.direction, dtype=float)
    norm = float(np.linalg.norm(direction))
    if norm == 0:
        raise ValueError("direction must have a non-zero norm")
    direction = direction / norm
    anchor = _mni_anchor(config.target)
    if anchor is not None:
        logger.info(
            "Direction given in MNI space; rotating it with the subject transform"
        )
        direction = _mni_direction_to_subject(
            direction, anchor, pm.m2m(config.subject_id)
        )
    logger.info("Direction: %s", np.round(direction, 4))
    return direction


def _mni_anchor(target) -> np.ndarray | None:
    """The MNI point a direction is anchored at, or ``None`` for subject space.

    A direction is given in the target's own space, and only the two targets
    that *carry* an MNI coordinate can anchor the transform: an MNI
    :class:`~tit.opt.config.RecipConfig.PointTarget` and an MNI-space
    ``SphericalROI``.  An atlas ROI declares the space of its *mask*, not of a
    direction, so a direction beside one is read as subject space.
    """
    from tit.opt.config import FlexConfig, RecipConfig

    if isinstance(target, RecipConfig.PointTarget):
        return np.asarray(target.xyz, dtype=float) if target.space == "mni" else None
    if isinstance(target, FlexConfig.SphericalROI) and target.use_mni:
        return np.asarray(
            [_first(target.x), _first(target.y), _first(target.z)], dtype=float
        )
    return None


def _first(value) -> float:
    """The first entry of a scalar-or-list ROI coordinate field."""
    return float(value[0] if isinstance(value, (list, tuple)) else value)


def _mni_direction_to_subject(
    direction: np.ndarray, mni_xyz: np.ndarray, m2m_path: str
) -> np.ndarray:
    """Rotate an MNI-space direction into subject space around *mni_xyz*.

    Uses the same point transform as every other MNI input
    (``simnibs.mni2subject_coords``) applied to the target and to a point one
    millimetre along the direction, so the result follows the local
    deformation rather than assuming the transform is a rotation.
    """
    from simnibs import mni2subject_coords

    points = np.vstack([mni_xyz, mni_xyz + direction])
    transformed = np.atleast_2d(mni2subject_coords(points, str(m2m_path)))
    moved = transformed[1] - transformed[0]
    norm = float(np.linalg.norm(moved))
    if norm == 0:
        raise ValueError("the MNI direction degenerates in subject space")
    return moved / norm


def _target_mask(
    config: RecipConfig,
    centroids: np.ndarray,
    m2m_path: str,
    output_dir: str,
    logger,
) -> np.ndarray:
    """Boolean element mask for the config's target."""
    if isinstance(config.target, RecipConfig.PointTarget):
        return _point_mask(config.target, centroids, m2m_path, logger)
    return _roi_mask(config, centroids, m2m_path, output_dir, logger)


def _point_mask(
    target: RecipConfig.PointTarget, centroids: np.ndarray, m2m_path: str, logger
) -> np.ndarray:
    """Elements within ``radius_mm`` of the point, or the nearest one."""
    xyz = np.asarray(target.xyz, dtype=float)
    if target.space == "mni":
        from simnibs import mni2subject_coords

        xyz = np.atleast_2d(mni2subject_coords(np.array([xyz]), str(m2m_path)))[0]
        logger.info("MNI target transformed to subject space: %s", np.round(xyz, 1))
    distance = np.linalg.norm(centroids - xyz, axis=1)
    if target.radius_mm > 0:
        mask = distance <= target.radius_mm
        if mask.any():
            return mask
        logger.warning(
            "No element within %.1fmm of the target; using the nearest element",
            target.radius_mm,
        )
    mask = np.zeros(len(centroids), dtype=bool)
    mask[int(np.argmin(distance))] = True
    return mask


def _roi_mask(
    config: RecipConfig,
    centroids: np.ndarray,
    m2m_path: str,
    output_dir: str,
    logger,
) -> np.ndarray:
    """Elements selected by one flex-shaped ROI target.

    The ROI objects are flex-search's own dataclasses, so the semantics are
    theirs: a ``SphericalROI`` is a union of spheres (MNI centres transformed
    first), a ``SubcorticalROI`` a union of atlas labels, and ``tissues``
    restricts the result to grey and/or white matter.  Only the geometry
    differs -- the elements come from the leadfield file rather than from a
    SimNIBS mesh object.
    """
    from tit.opt.config import FlexConfig

    target = config.target
    mask = np.zeros(len(centroids), dtype=bool)

    if isinstance(target, FlexConfig.AtlasROI):
        raise ValueError(
            "a cortical surface AtlasROI (a FreeSurfer .annot region) has no "
            "volume elements in the leadfield mesh; use a SphericalROI, a "
            "SubcorticalROI or a PointTarget"
        )

    if isinstance(target, FlexConfig.SphericalROI):
        centres = np.column_stack(
            [_as_array(target.x), _as_array(target.y), _as_array(target.z)]
        )
        if target.use_mni:
            from simnibs import mni2subject_coords

            centres = np.atleast_2d(mni2subject_coords(centres, str(m2m_path)))
            logger.info("MNI ROI centres transformed to subject space")
        radii = _as_array(target.radius)
        if len(radii) == 1:
            radii = np.repeat(radii, len(centres))
        for centre, radius in zip(centres, radii):
            mask |= np.linalg.norm(centroids - centre, axis=1) <= radius
    else:
        labels = target.label if isinstance(target.label, list) else [target.label]
        paths = (
            target.atlas_path
            if isinstance(target.atlas_path, list)
            else [target.atlas_path] * len(labels)
        )
        if len(paths) == 1:
            paths = paths * len(labels)
        for path, label in zip(paths, labels):
            if target.atlas_space == "mni":
                from tit.opt.masks import prepare_mask

                path = prepare_mask(
                    path, "mni", m2m_path, os.path.join(output_dir, "masks")
                )
            mask |= _atlas_mask(path, label, centroids, logger)

    # The ROI's `tissues` field is not applied: like the exhaustive search
    # (tit.opt.ex.engine._find_roi_elements), the region is taken as given --
    # the leadfield mesh holds only grey- and white-matter volume elements, and
    # dropping one tag here would silently shrink a deep target.
    return mask


def _as_array(value) -> np.ndarray:
    """A scalar-or-list ROI field as a 1-D float array."""
    return np.atleast_1d(np.asarray(value, dtype=float))


def _atlas_mask(
    path: str, label: int | None, centroids: np.ndarray, logger
) -> np.ndarray:
    """Elements whose centroid falls in one atlas label (or any positive voxel)."""
    import nibabel as nib

    logger.info(
        "Target elements from %s: %s",
        "atlas label " + str(label) if label is not None else "mask",
        path,
    )
    image = nib.load(path)
    data = np.asanyarray(image.dataobj)
    if data.ndim == 4:
        data = np.squeeze(data)
    if data.ndim != 3:
        raise ValueError(f"Expected a 3D ROI mask, got shape {data.shape}")
    homogeneous = np.hstack([centroids, np.ones((len(centroids), 1))])
    voxel = np.rint((homogeneous @ np.linalg.inv(image.affine).T)[:, :3]).astype(int)
    shape = np.asarray(data.shape[:3])
    inside = np.all((voxel >= 0) & (voxel < shape), axis=1)
    values = np.zeros(len(centroids), dtype=data.dtype)
    valid = voxel[inside]
    if len(valid):
        values[inside] = data[valid[:, 0], valid[:, 1], valid[:, 2]]
    return values == label if label is not None else values > 0


def _evaluation_subset(
    target_mask: np.ndarray, tags: np.ndarray, gm_subsample: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Target elements plus a fixed random grey-matter background sample.

    Building every candidate's field over the whole grey matter would cost
    tens of gigabytes, and the metrics only read the target and a background
    percentile, so the subset is chosen before any leadfield column is read.
    """
    background = (np.asarray(tags) == GM_TAG) & ~target_mask
    background_index = np.flatnonzero(background)
    if gm_subsample and len(background_index) > gm_subsample:
        rng = np.random.default_rng(GM_SUBSAMPLE_SEED)
        background_index = np.sort(
            rng.choice(background_index, gm_subsample, replace=False)
        )
    elif not gm_subsample:
        background_index = background_index[:0]
    subset = np.union1d(np.flatnonzero(target_mask), background_index)
    roi_pos = np.searchsorted(subset, np.flatnonzero(target_mask))
    background_pos = np.searchsorted(subset, background_index)
    return subset, roi_pos, background_pos
