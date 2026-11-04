"""Whole-brain tractography with DIPY, written in m2m T1 world (the SimNIBS mesh frame).

Two routes (method spec section 3):

* ``csd`` -- QSIPrep ACPC DWI: single-shell single-tissue CSD (Tournier 2007) on b0 + the
  highest shell, anatomically constrained (Smith 2012) by charm's WM/GM/CSF labels mapped
  into the DWI grid, probabilistic tracking. Streamlines come out in ACPC world and are
  mapped to m2m T1 world with the exact QSIPrep chain
  (:func:`tit.pre.qsi.tensor_math.acpc_to_t1_world`).
* ``tensor`` -- the m2m DTI tensor (already on the T1 grid): EuDX on the principal
  eigenvector (FACT-type deterministic tracking; cannot resolve crossings), FA stopping
  inside charm WM.

DIPY tracks in voxel index space (a voxel-frame direction ``d`` steps
``A[:3, :3] @ (d / voxel_size)`` in world), so every direction it reads -- gradient
directions, peak directions -- is converted from world with ``d_vox = M^-1 d_world``,
``M = A[:3, :3] / column norms``.

The QC record carries the tangent-vs-DTI-V1 coherence (spec V4): the median ``|t . e1|``
over streamline points where the m2m tensor's FA > 0.4, and for the csd route the same
number for all 8 gradient-axis sign flips on a central block of the brain; the unflipped
frame must score highest.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import time
from pathlib import Path

import numpy as np

from tit import constants as const
from tit.pre.qsi import tensor_math as tm

from . import geometry
from .io import save_tractogram

logger = logging.getLogger(__name__)

#: charm ``final_tissues`` labels.
WM, GM, CSF = 1, 2, 3
#: FA above which tangent / V1 coherence is measured (spec V4).
COHERENCE_FA = 0.4
#: Shell half-width when picking the CSD shell (s/mm^2): b2950 joins b3000.
SHELL_TOLERANCE = 100.0
#: Side of the central block the flip test fits and tracks in (voxels).
FLIP_BLOCK = 48
FLIP_SEEDS = 4000


class TrackingError(RuntimeError):
    """The inputs of a route are missing or the frame check failed."""


# ── frames ───────────────────────────────────────────────────────────────


def direction_frame(affine: np.ndarray) -> np.ndarray:
    """``M = A[:3, :3] / column norms``: voxel-frame unit direction -> world direction."""
    lin = np.asarray(affine, dtype=np.float64)[:3, :3]
    return lin / np.linalg.norm(lin, axis=0)


def world_to_voxel_dirs(dirs: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """World directions (..., 3) -> unit voxel-frame directions (zero rows stay zero)."""
    d = np.asarray(dirs, dtype=np.float64)
    v = np.linalg.solve(direction_frame(affine), d.reshape(-1, 3).T).T
    n = np.linalg.norm(v, axis=1, keepdims=True)
    v = np.divide(v, n, out=np.zeros_like(v), where=n > 0)
    return v.reshape(d.shape)


def apply_affine(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def labels_on_grid(
    labels_path: str, shape, grid_affine: np.ndarray, grid_to_label_world: np.ndarray
) -> np.ndarray:
    """Nearest-neighbour labels of *labels_path* at every voxel of a grid.

    *grid_to_label_world* maps the grid's world to the label image's world (identity
    when they share a world).
    """
    import nibabel as nib

    img = nib.load(labels_path)
    lab = np.asanyarray(img.dataobj)
    lab = lab[..., 0] if lab.ndim == 4 else lab
    vox = np.linalg.inv(img.affine) @ grid_to_label_world @ grid_affine
    ijk = np.indices(shape).reshape(3, -1).T.astype(np.float64)
    src = np.rint(apply_affine(vox, ijk)).astype(np.intp)
    ok = np.all((src >= 0) & (src < lab.shape), axis=1)
    out = np.zeros(len(src), dtype=lab.dtype)
    out[ok] = lab[tuple(src[ok].T)]
    return out.reshape(shape)


# ── CSD route ────────────────────────────────────────────────────────────


def csd_inputs(pm, subject_id: str) -> dict:
    """QSIPrep DWI, ``.b`` table, mask, ACPC->T1 chain and charm labels for *subject_id*."""
    import nibabel as nib

    from tit.pre.qsi.dti_extractor import qsiprep_inputs, read_itk_transform

    paths = qsiprep_inputs(Path(pm.qsiprep_subject(subject_id)))
    t1 = nib.load(pm.t1(subject_id))
    chain = tm.acpc_to_t1_world(
        t1.affine, t1.shape[:3], read_itk_transform(paths["xfm"])
    )
    qc_path = os.path.join(pm.m2m(subject_id), const.FILE_DTI_QC)
    recorded = None
    if os.path.isfile(qc_path):
        recorded = json.loads(Path(qc_path).read_text()).get("acpc_to_t1")
    return {
        **paths,
        "chain": chain,
        "chain_vs_dti_qc": (
            float(np.abs(chain - np.asarray(recorded)).max()) if recorded else None
        ),
        "labels": os.path.join(pm.m2m(subject_id), "final_tissues.nii.gz"),
    }


def load_shell(dwi_path, grad_path, shell: float | None = None):
    """DWI volumes of b0 + one shell (default the highest) and their world-RAS table.

    Returns ``(data (X, Y, Z, n) float32, affine, bvals (n,), bvecs_world (n, 3), shell)``.
    """
    import nibabel as nib

    table = np.loadtxt(str(grad_path), ndmin=2)
    if table.shape[1] != 4:
        raise TrackingError(f"{grad_path} is not an MRtrix gradient table (x y z b)")
    b = table[:, 3]
    shell = float(b.max()) if shell is None else float(shell)
    keep = (b < const.QSI_B0_THRESHOLD) | (np.abs(b - shell) <= SHELL_TOLERANCE)
    img = nib.load(str(dwi_path))
    data = np.asarray(img.dataobj, dtype=np.float32)[..., keep]
    return data, img.affine, b[keep], table[keep, :3], shell


def fit_csd(
    data, affine, bvals, bvecs_world, mask, wm, *, sh_order=8, n_jobs=1, flip=None
):
    """SSST CSD fit; gradients go to the voxel frame first (times *flip* signs, if given).

    The response comes from FA > 0.7 voxels within 10 voxels of the *wm* centroid (the
    volume centre DIPY defaults to can fall in the ventricles of an ACPC grid).

    Returns ``(sh coefficients (X, Y, Z, n_coef), response info dict)``.
    """
    from dipy.core.gradients import gradient_table
    from dipy.reconst.csdeconv import (
        ConstrainedSphericalDeconvModel,
        mask_for_response_ssst,
        response_from_mask_ssst,
    )

    g = world_to_voxel_dirs(bvecs_world, affine)
    if flip is not None:
        g = g * np.asarray(flip, dtype=np.float64)
    gtab = gradient_table(bvals, bvecs=g, b0_threshold=const.QSI_B0_THRESHOLD)
    centre = np.rint(np.argwhere(wm).mean(axis=0)).astype(int)
    resp_mask = mask_for_response_ssst(
        gtab, data, roi_center=centre, roi_radii=10, fa_thr=0.7
    )
    if not resp_mask.any():
        raise TrackingError("no FA > 0.7 voxel near the WM centroid for the response")
    response, ratio = response_from_mask_ssst(gtab, data, resp_mask)
    model = ConstrainedSphericalDeconvModel(gtab, response, sh_order_max=sh_order)
    kwargs = {"engine": "joblib", "n_jobs": n_jobs} if n_jobs > 1 else {}
    fit = model.fit(data, mask=mask, **kwargs)
    info = {
        "response_evals": [float(x) for x in response[0]],
        "response_s0": float(response[1]),
        "response_ratio": float(ratio),
        "response_voxels": int(resp_mask.sum()),
    }
    return np.asarray(fit.shm_coeff, dtype=np.float64), info


def track_sh(
    shm, wm, gm, csf, affine, seeds_mask, cfg, *, n_seeds, n_jobs, return_all=False
):
    """ACT probabilistic tracking on SH coefficients; streamlines in the affine's world."""
    from dipy.data import default_sphere
    from dipy.tracking.stopping_criterion import ActStoppingCriterion
    from dipy.tracking.tracker import probabilistic_tracking
    from dipy.tracking.utils import random_seeds_from_mask

    sc = ActStoppingCriterion.from_pve(
        wm.astype(np.float64), gm.astype(np.float64), csf.astype(np.float64)
    )
    seeds = random_seeds_from_mask(
        seeds_mask,
        affine,
        seeds_count=int(n_seeds),
        seed_count_per_voxel=False,
        random_seed=cfg.random_seed,
    )
    gen = probabilistic_tracking(
        seeds,
        sc,
        affine,
        sh=shm,
        sphere=default_sphere,
        max_angle=cfg.max_angle,
        step_size=cfg.step_mm,
        min_len=cfg.min_length_mm,
        max_len=cfg.max_length_mm,
        random_seed=cfg.random_seed,
        nbr_threads=n_jobs,
        return_all=return_all,
    )
    return [np.asarray(s, np.float32) for s in gen], len(seeds)


def _crop(arr, lo, hi):
    return arr[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]]


def flip_test(
    data, affine, bvals, bvecs, maps, chain, tensor, cfg, n_jobs
) -> list[dict]:
    """Coherence of a small tractogram for each of the 8 gradient-axis sign flips.

    CSD is fitted and tracked in a :data:`FLIP_BLOCK`-voxel cube centred on the WM
    centroid, :data:`FLIP_SEEDS` seeds, for each flip; the streamlines go to T1 world and
    are scored with :func:`coherence` against the m2m tensor.
    """
    wm, gm, csf, fit_mask = maps
    centre = np.rint(np.argwhere(wm).mean(axis=0)).astype(int)
    lo = np.maximum(centre - FLIP_BLOCK // 2, 0)
    hi = np.minimum(lo + FLIP_BLOCK, wm.shape)
    shift = np.eye(4)
    shift[:3, 3] = lo
    aff = affine @ shift
    block = [_crop(m, lo, hi) for m in (wm, gm, csf, fit_mask)]
    sub = _crop(data, lo, hi)
    rows = []
    for flip in itertools.product((1, -1), repeat=3):
        shm, _ = fit_csd(
            sub,
            aff,
            bvals,
            bvecs,
            block[3],
            block[0],
            sh_order=cfg.sh_order,
            n_jobs=n_jobs,
            flip=flip,
        )
        sl, _ = track_sh(
            shm,
            *block[:3],
            aff,
            block[0],
            cfg,
            n_seeds=FLIP_SEEDS,
            n_jobs=n_jobs,
            return_all=True,
        )
        sl = [apply_affine(chain, s.astype(np.float64)) for s in sl if len(s) > 2]
        rows.append(
            {"flip": list(flip), "n_streamlines": len(sl), **coherence(sl, *tensor)}
        )
        logger.info(f"flip test {flip}: {rows[-1]}")
    return rows


def track_csd(pm, subject_id: str, cfg, n_jobs: int) -> tuple[list, dict]:
    """The csd route; returns streamlines in ACPC world and the QC fields."""
    import nibabel as nib
    from scipy.ndimage import binary_dilation

    inp = csd_inputs(pm, subject_id)
    data, affine, bvals, bvecs, shell = load_shell(inp["dwi"], inp["grad"])
    brain = np.asanyarray(nib.load(str(inp["dwi_mask"])).dataobj) > 0
    labels = labels_on_grid(inp["labels"], data.shape[:3], affine, inp["chain"])
    wm, gm, csf = (labels == WM), (labels == GM), (labels == CSF)
    fit_mask = brain & binary_dilation(wm | gm, iterations=1)
    logger.info(
        f"CSD on b0 + b{shell:g} ({len(bvals)} volumes), {int(fit_mask.sum())} voxels, "
        f"{n_jobs} worker(s)"
    )
    t0 = time.time()
    shm, resp = fit_csd(
        data, affine, bvals, bvecs, fit_mask, wm, sh_order=cfg.sh_order, n_jobs=n_jobs
    )
    fit_s = time.time() - t0
    logger.info(f"CSD fit {fit_s:.0f} s; tracking {cfg.n_seeds} seeds")
    t0 = time.time()
    sl, n_seeds = track_sh(
        shm, wm, gm, csf, affine, wm, cfg, n_seeds=cfg.n_seeds, n_jobs=n_jobs
    )
    del shm
    info = {
        "inputs": {
            k: str(inp[k]) for k in ("dwi", "grad", "dwi_mask", "xfm", "labels")
        },
        "shell": shell,
        "n_volumes": int(len(bvals)),
        "fit_voxels": int(fit_mask.sum()),
        "acpc_to_t1": inp["chain"].round(6).tolist(),
        "acpc_to_t1_vs_dti_qc_max_abs": inp["chain_vs_dti_qc"],
        "csd": resp,
        "seconds": {"csd_fit": round(fit_s, 1), "tracking": round(time.time() - t0, 1)},
        "n_seeds": int(n_seeds),
        "dwi_affine": np.asarray(affine).tolist(),
    }
    if cfg.flip_test:
        t0 = time.time()
        tensor = m2m_tensor(pm, subject_id)
        info["flip_test"] = flip_test(
            data,
            affine,
            bvals,
            bvecs,
            (wm, gm, csf, fit_mask),
            inp["chain"],
            tensor,
            cfg,
            n_jobs,
        )
        info["seconds"]["flip_test"] = round(time.time() - t0, 1)
    return sl, info


# ── tensor route ─────────────────────────────────────────────────────────


def m2m_tensor(pm, subject_id: str) -> tuple[np.ndarray, np.ndarray]:
    """The m2m DTI tensor as stored (SimNIBS frame 6-vectors) and its affine."""
    import nibabel as nib

    path = os.path.join(pm.m2m(subject_id), const.FILE_DTI_TENSOR)
    if not os.path.isfile(path):
        raise TrackingError(f"No DTI tensor at {path}")
    img = nib.load(path)
    return np.asarray(img.dataobj, dtype=np.float32), img.affine


def tensor_peaks(t6: np.ndarray, affine: np.ndarray, mask: np.ndarray):
    """``(e1_world (N, 3), fa (N,))`` of the voxels in *mask* (world-frame tensors)."""
    vals, vecs = tm.eig_desc(tm.simnibs_to_world(t6[mask].astype(np.float64), affine))
    fa, _ = tm.fa_md(vals)
    return vecs[:, :, 0], fa


def track_tensor(pm, subject_id: str, cfg, n_jobs: int) -> tuple[list, dict]:
    """The tensor route; returns streamlines in m2m T1 world and the QC fields."""
    import nibabel as nib
    from dipy.data import get_sphere
    from dipy.direction.peaks import PeaksAndMetrics
    from dipy.tracking.stopping_criterion import ThresholdStoppingCriterion
    from dipy.tracking.tracker import eudx_tracking
    from dipy.tracking.utils import random_seeds_from_mask

    t6, affine = m2m_tensor(pm, subject_id)
    labels_path = os.path.join(pm.m2m(subject_id), "final_tissues.nii.gz")
    labels = labels_on_grid(labels_path, t6.shape[:3], affine, np.eye(4))
    wm = labels == WM
    nonzero = np.any(t6 != 0, axis=-1)
    e1, fa_vals = tensor_peaks(t6, affine, nonzero)
    fa = np.zeros(t6.shape[:3])
    fa[nonzero] = fa_vals
    sphere = get_sphere(name="repulsion724")
    idx = np.zeros(len(e1), dtype=np.int32)
    e1_vox = world_to_voxel_dirs(e1, affine)
    for lo in range(0, len(e1), 100_000):
        idx[lo : lo + 100_000] = np.argmax(
            np.abs(e1_vox[lo : lo + 100_000] @ sphere.vertices.T), axis=1
        )
    del t6, e1, e1_vox
    pam = PeaksAndMetrics()
    pam.sphere = sphere
    pam.peak_indices = np.full(fa.shape + (1,), -1, dtype=np.int32)
    pam.peak_indices[nonzero, 0] = idx
    pam.peak_values = np.zeros(fa.shape + (1,))
    pam.peak_values[nonzero, 0] = fa_vals
    pam.peak_dirs = np.zeros(fa.shape + (1, 3))
    pam.peak_dirs[nonzero, 0] = sphere.vertices[idx]
    fa_wm = np.where(wm, fa, 0.0)
    sc = ThresholdStoppingCriterion(fa_wm, cfg.fa_threshold)
    seed_mask = fa_wm >= cfg.fa_threshold
    seeds = random_seeds_from_mask(
        seed_mask,
        affine,
        seeds_count=int(cfg.n_seeds),
        seed_count_per_voxel=False,
        random_seed=cfg.random_seed,
    )
    t0 = time.time()
    gen = eudx_tracking(
        seeds,
        sc,
        affine,
        pam=pam,
        sphere=sphere,
        max_angle=cfg.max_angle,
        step_size=cfg.step_mm,
        min_len=cfg.min_length_mm,
        max_len=cfg.max_length_mm,
        random_seed=cfg.random_seed,
        nbr_threads=n_jobs,
        return_all=False,
    )
    sl = [np.asarray(s, np.float32) for s in gen]
    info = {
        "inputs": {
            "tensor": os.path.join(pm.m2m(subject_id), const.FILE_DTI_TENSOR),
            "labels": labels_path,
        },
        "n_seeds": int(len(seeds)),
        "seconds": {"tracking": round(time.time() - t0, 1)},
        "wm_fa_median": float(np.median(fa[wm & nonzero])),
    }
    return sl, info


# ── QC ───────────────────────────────────────────────────────────────────


def coherence(
    streamlines, t6: np.ndarray, affine: np.ndarray, max_streamlines: int = 20_000
) -> dict:
    """Median ``|t . e1|`` over streamline points where the tensor's FA > 0.4 (spec V4).

    *streamlines* are in the tensor's world; tangents by central differences on a 1 mm
    resampling; ``e1`` and FA of the nearest tensor voxel. Up to *max_streamlines*
    (evenly spaced) are scored.
    """
    if not len(streamlines):
        return {"median_abs_cos": None, "n_points": 0}
    pick = np.linspace(0, len(streamlines) - 1, min(len(streamlines), max_streamlines))
    sl = [streamlines[int(i)] for i in np.unique(pick.astype(int))]
    pts, off, h = geometry.resample(sl, 1.0)
    t = geometry.tangents(pts, off, h)
    vox = np.rint(apply_affine(np.linalg.inv(affine), pts)).astype(np.intp)
    ok = np.all((vox >= 0) & (vox < t6.shape[:3]), axis=1)
    mask = np.zeros(t6.shape[:3], dtype=bool)
    mask[tuple(vox[ok].T)] = True
    e1, fa = tensor_peaks(t6, affine, mask)
    lookup = np.full(t6.shape[:3], -1, dtype=np.intp)
    lookup[mask] = np.arange(mask.sum())
    j = lookup[tuple(vox[ok].T)]
    keep = fa[j] > COHERENCE_FA
    cos = np.abs(np.einsum("pk,pk->p", t[ok][keep], e1[j[keep]]))
    if not len(cos):
        return {"median_abs_cos": None, "n_points": 0}
    return {
        "median_abs_cos": float(np.median(cos)),
        "frac_abs_cos_ge_0.9": float(np.mean(cos >= 0.9)),
        "n_points": int(len(cos)),
    }


def _length_stats(streamlines) -> dict:
    if not streamlines:
        return {}
    lengths = np.array(
        [np.linalg.norm(np.diff(s, axis=0), axis=1).sum() for s in streamlines]
    )
    q = np.percentile(lengths, [0, 5, 50, 95, 100])
    return dict(zip(("min", "p5", "median", "p95", "max"), map(float, q))) | {
        "mean": float(lengths.mean())
    }


def resolve_route(pm, subject_id: str, route: str) -> str:
    if route != "auto":
        return route
    qsi = Path(pm.qsiprep_subject(subject_id))
    has_dwi = any(qsi.glob("**/dwi/*_space-ACPC_desc-preproc_dwi.nii.gz"))
    return "csd" if has_dwi else "tensor"


def run_track(subject_id: str, cfg) -> dict:
    """The ``track`` stage: write ``tractogram.trx`` (m2m T1 world) and ``qc.json``.

    Returns the QC record. With the csd route and ``cfg.flip_test``, raises
    :class:`TrackingError` (after writing ``qc.json``) when the unflipped gradient frame
    does not give the highest coherence.
    """
    from tit.cpu import resolve_n_jobs
    from tit.paths import get_path_manager

    pm = get_path_manager()
    out_dir = pm.ensure(pm.tractography(subject_id))
    trx_path = os.path.join(out_dir, "tractogram.trx")
    if os.path.exists(trx_path) and not cfg.overwrite:
        raise TrackingError(f"{trx_path} exists; set track.overwrite to replace it")
    route = resolve_route(pm, subject_id, cfg.route)
    n_jobs = resolve_n_jobs(cfg.n_jobs)
    t0 = time.time()
    if route == "csd":
        sl_native, info = track_csd(pm, subject_id, cfg, n_jobs)
        chain = np.asarray(info["acpc_to_t1"])
        if cfg.export_acpc_tck:
            import nibabel as nib

            ref = nib.Nifti1Image(
                np.zeros((1, 1, 1), np.uint8), np.asarray(info["dwi_affine"])
            )
            save_tractogram(
                os.path.join(out_dir, "tractogram_acpc.tck"), sl_native, ref
            )
        sl = [apply_affine(chain, s.astype(np.float64)) for s in sl_native]
        del sl_native
    else:
        sl, info = track_tensor(pm, subject_id, cfg, n_jobs)
    save_tractogram(trx_path, sl, pm.t1(subject_id))
    tensor = m2m_tensor(pm, subject_id)
    qc = {
        "subject_id": subject_id,
        "route": route,
        "space": "m2m T1 world, RAS mm (SimNIBS mesh coordinates)",
        "config": {k: getattr(cfg, k) for k in cfg.__dataclass_fields__},
        "n_workers": n_jobs,
        "n_streamlines": len(sl),
        "length_mm": _length_stats(sl),
        "coherence_vs_dti_v1": coherence(sl, *tensor),
        **info,
    }
    qc["seconds"]["total"] = round(time.time() - t0, 1)
    if qc.get("flip_test"):
        qc.update(flip_verdict(qc["flip_test"]))
    Path(out_dir, "qc.json").write_text(json.dumps(qc, indent=1) + "\n")
    if qc.get("flip_test") and not qc["flip_test_passed"]:
        raise TrackingError(
            f"Gradient frame check failed: flip {qc['flip_test_winner']} beats the "
            f"unflipped frame (see {out_dir}/qc.json)."
        )
    return qc


def flip_verdict(rows: list[dict]) -> dict:
    """Did the unflipped frame win the 8-flip test, and by how much?

    Flipping all three axes reflects every direction through the origin, which leaves an
    antipodally symmetric ODF unchanged, so ``(-1, -1, -1)`` is the unflipped frame again and
    the 8 flips are 4 distinct frames. Passed when the best score belongs to the unflipped
    pair; the margin is its lower score minus the best of the other three frames.
    """
    score = {tuple(r["flip"]): r["median_abs_cos"] or 0.0 for r in rows}
    same = [(1, 1, 1), (-1, -1, -1)]
    best = max(score, key=score.get)
    others = [v for k, v in score.items() if k not in same]
    return {
        "flip_test_winner": list(best),
        "flip_test_passed": best in same,
        "flip_test_margin": float(min(score[k] for k in same) - max(others)),
    }
