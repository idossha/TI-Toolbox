"""Targeting a white-matter bundle: a tract-density ROI mask, and a direction-aware ranking.

(a) :func:`density_mask` writes the voxels a bundle crosses as a binary NIfTI on the m2m T1
grid, into ``m2m_<sid>/masks/`` where the optimizer ROI pickers already discover custom
masks. It runs through the existing optimizers unchanged, as
``FlexConfig.SubcorticalROI(atlas_path=mask, label=None, tissues="WM")`` or
``ExConfig.AtlasROI(atlas_path=mask, label=None)`` (:func:`roi_specs`).

(b) :func:`rank_montages` scores candidate two-pair montages on a bundle with fields built
from the ex-search leadfield. The ranking statistic is the one ``assess`` reports: the
median over streamlines of each streamline's arc-length mean ``ti_along`` (the envelope along
its tangent, :func:`tit.calc.envelope`). The pooled point mean (length-weighted), the same
statistics of ``ti_max`` and ``ti_avg``, and the alignment index are reported beside it.
"""

from __future__ import annotations

import csv
import itertools
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from tit.calc import envelope, envelope_max, envelope_mean

from . import geometry
from .io import load_streamlines, save_nifti
from .network import network_fingerprint, select

logger = logging.getLogger(__name__)

#: Seconds between progress lines of a long ranking (about 0.12 s per montage emulated).
RANK_REPORT_S = 30.0


def density_mask(streamlines, ref_path: str, out_path: str, min_count: int = 1) -> dict:
    """Voxels of *ref_path*'s grid crossed by >= *min_count* streamlines, as uint8 NIfTI."""
    import nibabel as nib
    from dipy.tracking.utils import density_map

    ref = nib.load(ref_path)
    density = density_map(
        [np.asarray(s, np.float64) for s in streamlines], ref.affine, ref.shape[:3]
    )
    mask = (density >= min_count).astype(np.uint8)
    if not mask.any():
        raise ValueError(
            f"No voxel is crossed by at least {min_count} streamline(s) of this selection."
        )
    # Replaced in one step: a job may be reading the mask this overwrites.
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(os.path.abspath(out_path)), suffix=".nii.gz"
    )
    os.close(fd)
    try:
        save_nifti(mask, ref.affine, tmp)
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; the mask is a shared output
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    vox_mm3 = float(abs(np.linalg.det(ref.affine[:3, :3])))
    return {
        "path": out_path,
        "n_voxels": int(mask.sum()),
        "volume_mm3": float(mask.sum() * vox_mm3),
        "min_count": int(min_count),
        "max_density": int(density.max()) if density.size else 0,
    }


def mask_sidecar_path(mask_path: str) -> str:
    """``tract-<name>.json`` beside ``tract-<name>.nii[.gz]``."""
    return re.sub(r"\.nii(\.gz)?$", "", mask_path) + ".json"


def read_mask_sidecar(mask_path: str) -> dict | None:
    """The mask's sidecar, or ``None`` when it has none (a mask made by hand or by an older run)."""
    try:
        with open(mask_sidecar_path(mask_path)) as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def write_mask_with_sidecar(
    pm, subject_id: str, selection, bundle, min_count: int
) -> dict:
    """The bundle's density mask, and the sidecar saying what made it.

    ``fingerprint`` is what the optimizers' preflight compares with the current tractogram and
    network (``tit.jobs.preflight``): a mask from a replaced network is refused, not optimized.
    """
    mask_path = os.path.join(pm.masks(subject_id), f"tract-{selection.name}.nii.gz")
    mask = density_mask(bundle, pm.t1(subject_id), mask_path, min_count)
    record = {
        "selection": asdict(selection),
        "n_streamlines": int(len(bundle)),
        "fingerprint": network_fingerprint(pm, subject_id),
        **mask,
    }
    sidecar = mask_sidecar_path(mask_path)
    Path(sidecar + ".tmp").write_text(json.dumps(record, indent=1) + "\n")
    os.replace(sidecar + ".tmp", sidecar)
    return record


def _current_mask(pm, subject_id: str, selection, min_count: int) -> dict | None:
    """The sidecar when the mask on disk is exactly this selection of this network."""
    path = os.path.join(pm.masks(subject_id), f"tract-{selection.name}.nii.gz")
    record = read_mask_sidecar(path)
    if (
        os.path.isfile(path)
        and record
        and record.get("selection") == asdict(selection)
        and record.get("min_count") == min_count
        and record.get("fingerprint") == network_fingerprint(pm, subject_id)
    ):
        return record
    return None


def roi_specs(mask_path: str):
    """The mask as a flex ROI (WM elements) and an ex/mex atlas ROI (element barycentres)."""
    from tit.opt.config import ExConfig, FlexConfig

    return (
        FlexConfig.SubcorticalROI(
            atlas_path=mask_path, label=None, tissues="WM", atlas_space="subject"
        ),
        ExConfig.AtlasROI(atlas_path=mask_path, label=None, atlas_space="subject"),
    )


def pool_montages(pool) -> list[list[str]]:
    """Every two-pair montage of four distinct electrodes from *pool*.

    The envelope is unchanged by swapping the channels or a pair's polarity, so each
    set of four electrodes gives its three pairings once.
    """
    out = []
    for a, b, c, d in itertools.combinations(pool, 4):
        out += [[a, b, c, d], [a, c, b, d], [a, d, b, c]]
    return out


def ex_run_montages(csv_path: str, top_n: int | None) -> list[list[str]]:
    """The *top_n* distinct electrode sets of an ex-search ``final_output.csv`` by composite.

    ``None`` is every one of them.
    """
    from tit.opt.ex.results import montage_score_records_from_csv

    records = sorted(
        montage_score_records_from_csv(csv_path), key=lambda r: -r["composite"]
    )
    seen, out = set(), []
    for r in records:
        key = tuple(r["electrodes"])
        if len(key) != 4:
            raise ValueError(
                f"{csv_path} is not a two-pair search: the ranking scores two-pair montages."
            )
        if key not in seen:
            seen.add(key)
            out.append(list(key))
        if top_n is not None and len(out) >= top_n:
            break
    return out


def streamline_means(values, weights, offsets):
    """Weighted arc-length mean per streamline; NaN for a streamline with no weight."""
    first = offsets[:-1]
    den = np.add.reduceat(weights, first)
    num = np.add.reduceat(weights * values, first)
    return np.divide(num, den, out=np.full(len(den), np.nan), where=den > 0)


def rank_montages(
    leadfield_hdf: str,
    points: np.ndarray,
    offsets: np.ndarray,
    h: np.ndarray,
    tangents: np.ndarray,
    montages,
    current_mA=(1.0, 1.0),
) -> tuple[list[dict], dict]:
    """Score each montage on a resampled bundle (``points``, ``offsets``, ``h``).

    The leadfield is loaded the way exhaustive search loads it
    (:class:`tit.opt.ex.engine.ExSearchEngine`); each point takes the leadfield-mesh
    element containing it, and points outside that mesh get no weight. Per montage:
    ``median_sl_mean_<q>`` (median over streamlines of the arc-length mean, the statistic
    ``assess`` reports) and ``pooled_mean_<q>`` (mean over all points, length-weighted) for
    ``q`` in ``ti_along``, ``ti_max``, ``ti_avg``; ``align_index`` = median over streamlines
    of mean ti_along / mean ti_avg. Sorted by ``median_sl_mean_ti_along``, highest first.
    Returns ``(rows, point counts)``.
    """
    from simnibs.utils import TI_utils as TI

    from tit.opt.ex.engine import ExSearchEngine

    engine = ExSearchEngine(leadfield_hdf, [], "tract", logger)
    engine._load_leadfield()
    th = engine.mesh.find_tetrahedron_with_points(
        np.asarray(points, np.float64), compute_baricentric=False
    )
    inside = th > 0
    weights = geometry._trapezoid_weights(offsets, h) * inside
    elm = np.where(inside, th - 1, 0)
    i1, i2 = (c / 1000.0 for c in current_mA)
    rows = []
    started = last_report = time.monotonic()
    for done, (e1p, e1m, e2p, e2m) in enumerate(montages):
        now = time.monotonic()
        if now - last_report >= RANK_REPORT_S:
            last_report = now
            left = (now - started) / done * (len(montages) - done)
            logger.info(
                f"ranked {done}/{len(montages)} montages, about {left:.0f} s left"
            )
        E1 = TI.get_field([e1p, e1m, i1], engine.leadfield, engine.idx_lf)[elm]
        E2 = TI.get_field([e2p, e2m, i2], engine.leadfield, engine.idx_lf)[elm]
        q = {
            "ti_along": envelope([E1, E2], tangents),
            "ti_max": envelope_max([E1, E2]),
            "ti_avg": envelope_mean([E1, E2]),
        }
        row = {"montage": [e1p, e1m, e2p, e2m]}
        sl = {k: streamline_means(v, weights, offsets) for k, v in q.items()}
        for k, v in q.items():
            row[f"median_sl_mean_{k}"] = float(np.nanmedian(sl[k]))
            row[f"pooled_mean_{k}"] = float(np.sum(weights * v) / np.sum(weights))
        row["align_index"] = float(np.nanmedian(sl["ti_along"] / sl["ti_avg"]))
        rows.append(row)
    rows.sort(key=lambda r: -r["median_sl_mean_ti_along"])
    by_max = sorted(rows, key=lambda r: -r["median_sl_mean_ti_max"])
    for rank, r in enumerate(by_max, start=1):
        r["rank_by_ti_max"] = rank
    for rank, r in enumerate(rows, start=1):
        r["rank_by_ti_along"] = rank
    logger.info(
        f"ranked {len(rows)} montages on {int(inside.sum())}/{len(th)} bundle points"
    )
    return rows, {
        "n_points": int(len(th)),
        "n_points_in_leadfield_mesh": int(inside.sum()),
    }


def run_target(subject_id: str, cfg, step_mm: float = 0.5) -> dict:
    """The ``target`` stage: the bundle's density mask, and the ranking when a leadfield is set."""
    from tit.paths import get_path_manager

    from .fields import load_network

    pm = get_path_manager()
    tract_dir = pm.tractography(subject_id)
    streamlines = load_streamlines(os.path.join(tract_dir, "tractogram.trx"))
    network = load_network(subject_id)
    names = [str(n) for n in network["names"]]
    sel = cfg.selection
    pick = np.flatnonzero(
        select(sel, network["labels"], names, network["edge_id"], streamlines)
    )
    bundle = [streamlines[i] for i in pick]
    if not bundle:
        raise ValueError(f"selection {sel.name!r} picks no streamline")
    # A ranking of an existing target must not rewrite the mask an optimizer may be reading.
    record = _current_mask(pm, subject_id, sel, cfg.min_count)
    if record is None:
        record = write_mask_with_sidecar(pm, subject_id, sel, bundle, cfg.min_count)
    mask_path = record["path"]
    result = {
        "selection": asdict(sel),
        "n_streamlines": int(len(bundle)),
        "mask": {
            k: record[k]
            for k in ("path", "n_voxels", "volume_mm3", "min_count", "max_density")
        },
        "optimizer_rois": {
            "flex": f"FlexConfig.SubcorticalROI(atlas_path={mask_path!r}, label=None, tissues='WM')",
            "ex": f"ExConfig.AtlasROI(atlas_path={mask_path!r}, label=None)",
        },
    }
    if cfg.leadfield_hdf:
        montages = [list(m) for m in cfg.montages] + pool_montages(cfg.pool)
        if cfg.ex_run:
            csv_path = os.path.join(
                pm.ex_search(subject_id), cfg.ex_run, "final_output.csv"
            )
            montages += ex_run_montages(csv_path, cfg.top_n)
        if not montages:
            raise ValueError("ranking needs montages, a pool or an ex_run")
        lf = cfg.leadfield_hdf
        if not os.path.isabs(lf):
            lf = os.path.join(pm.leadfields(subject_id), lf)
        pts, off, h = geometry.resample(bundle, step_mm)
        rows, info = rank_montages(
            lf, pts, off, h, geometry.tangents(pts, off, h), montages, cfg.current_mA
        )
        result["ranking"] = {
            "leadfield": lf,
            "ex_run": cfg.ex_run,
            "current_mA": cfg.current_mA,
            "sorted_by": "median_sl_mean_ti_along",
            **info,
            "montages": rows,
        }
        with open(
            os.path.join(tract_dir, f"ranking_{sel.name}.csv"), "w", newline=""
        ) as f:
            w = csv.writer(f)
            keys = [k for k in rows[0] if k != "montage"]
            w.writerow(["montage", *keys])
            for r in rows:
                w.writerow([" ".join(r["montage"]), *(r[k] for k in keys)])
    Path(tract_dir, f"target_{sel.name}.json").write_text(
        json.dumps(result, indent=1) + "\n"
    )
    return result
