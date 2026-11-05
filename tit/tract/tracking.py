"""Whole-brain tractography with DIPY, written in m2m T1 world (the SimNIBS mesh frame).

One route (method spec section 3): QSIPrep ACPC DWI, single-shell single-tissue CSD
(Tournier 2007) on b0 + one shell (:func:`pick_shell`), anatomically constrained (Smith 2012) by charm's
WM/GM/CSF labels mapped into the DWI grid, probabilistic tracking. Streamlines come out in
ACPC world and are mapped to m2m T1 world with the exact QSIPrep chain
(:func:`tit.pre.qsi.tensor_math.acpc_to_t1_world`). A subject without QSIPrep output is
refused before any work (:func:`csd_inputs`).

DIPY tracks in voxel index space (a voxel-frame direction ``d`` steps
``A[:3, :3] @ (d / voxel_size)`` in world), so every direction it reads -- gradient
directions, peak directions -- is converted from world with ``d_vox = M^-1 d_world``,
``M = A[:3, :3] / column norms``.

The QC record carries an 8-axis-flip frame check; the unflipped frame must score highest
on the tangent-vs-DTI-V1 coherence (spec V4), the median ``|t . e1|`` over streamline
points where FA > 0.4, for each gradient-axis sign flip on a central block of the brain;
the same coherence is reported for the whole-brain tractogram. The reference tensor is
fitted here, on the same QSIPrep DWI and brain mask (:func:`dti_reference`: DIPY WLS on b0
+ the shells <= 1500, else the lowest shell), with the world-RAS table and no flip, so
tracking needs only QSIPrep output and the charm m2m folder. Everything is compared in ACPC
world, the frame both are fitted in.

ACT treats the label volume's deep grey nuclei as grey matter
(:data:`DEEP_GREY`; charm's tissue map calls the pallidum WM).
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
#: Default CSD shell: the one closest to this b (s/mm^2) among shells with at least
#: CSD_SHELL_MIN_DIRS volumes; ties go to the shell with more volumes.
CSD_SHELL_TARGET_B = 3000.0
CSD_SHELL_MIN_DIRS = 30
CSD_SHELL_RULE = (
    f"closest to b{CSD_SHELL_TARGET_B:g} among shells with >= {CSD_SHELL_MIN_DIRS} "
    "directions; ties to more directions"
)
#: Side of the central block the flip test fits and tracks in (voxels).
FLIP_BLOCK = 48
FLIP_SEEDS = 4000
#: aseg deep grey nuclei (thalamus, caudate, putamen, pallidum, hippocampus, amygdala,
#: accumbens). charm's final_tissues calls the pallidum WM; ACT treats them all as grey
#: matter (a valid end). Brain stem and ventral DC stay WM: tracts run through them.
DEEP_GREY = (10, 11, 12, 13, 17, 18, 26, 49, 50, 51, 52, 53, 54, 58)
#: Label-volume labels through which a streamline leaves the brain inferiorly: brain stem
#: (16), cerebellar WM (7, 46) and charm's spinal cord (512).
EXIT_LABELS = (16, 7, 46, 512)


def inferior_exit(aseg: np.ndarray, fod_mask: np.ndarray) -> np.ndarray:
    """Brain-stem, cerebellar-WM and spinal-cord voxels with no fibre orientation: a valid end.

    The DWI brain mask (and so the fitted FOD) stops above the bottom of the image (CHN:
    z -62 mm ACPC, inside charm's spinal cord), and charm labels the tissue below it WM. A
    corticospinal streamline running down the brain stem then finds no orientation, stops
    while still "tracking", and DIPY's ACT drops it. MRtrix ACT accepts a streamline that
    leaves this way; marking these voxels as include does the same, and a streamline that
    ends in CSF is still rejected.
    """
    return np.isin(aseg, EXIT_LABELS) & ~fod_mask


class TrackingError(RuntimeError):
    """The tracking inputs are missing or the frame check failed."""


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


# ── tracking ─────────────────────────────────────────────────────────────


def csd_inputs(pm, subject_id: str) -> dict:
    """QSIPrep DWI, ``.b`` table, mask, ACPC->T1 chain and charm labels for *subject_id*.

    Raises:
        TrackingError: no QSIPrep output.
    """
    import nibabel as nib

    from tit.pre.qsi.dti_extractor import qsiprep_inputs, read_itk_transform
    from tit.pre.utils import PreprocessError

    qsi = Path(pm.qsiprep_subject(subject_id))
    try:
        paths = qsiprep_inputs(qsi)
    except PreprocessError as exc:
        raise TrackingError(
            f"Tractography needs QSIPrep-preprocessed DWI in {qsi} ({exc}). Run tit.pre's "
            "QSIPrep step (PreprocessConfig run_qsiprep=True) for this subject first."
        ) from exc
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


def pick_shell(bvals, shell: float | None = None) -> tuple[float, int, str]:
    """The CSD shell, its direction (volume) count and the rule that chose it.

    Default :data:`CSD_SHELL_RULE`; an explicit ``shell`` overrides it. Shells are the
    diffusion-weighted b-values rounded to 100 s/mm^2; a volume belongs to a shell within
    :data:`SHELL_TOLERANCE`.
    """
    b = np.asarray(bvals, dtype=float)
    weighted = b[b >= const.QSI_B0_THRESHOLD]

    def count(s: float) -> int:
        return int((np.abs(weighted - s) <= SHELL_TOLERANCE).sum())

    if shell is not None:
        n = count(float(shell))
        if not n:
            raise TrackingError(f"no volume at the configured shell b{float(shell):g}")
        return float(shell), n, "configured"
    shells = [(float(s), count(s)) for s in np.unique(np.round(weighted, -2))]
    eligible = [(s, n) for s, n in shells if n >= CSD_SHELL_MIN_DIRS]
    if not eligible:
        raise TrackingError(
            f"no shell has >= {CSD_SHELL_MIN_DIRS} directions ({shells}); "
            "set track.shell explicitly"
        )
    s, n = min(eligible, key=lambda sn: (abs(sn[0] - CSD_SHELL_TARGET_B), -sn[1]))
    return s, n, CSD_SHELL_RULE


def load_shell(dwi_path, grad_path, shell: float | None = None):
    """DWI volumes of b0 + one shell (:func:`pick_shell`) and their world-RAS table.

    Returns ``(data (X, Y, Z, n) float32, affine, bvals (n,), bvecs_world (n, 3),
    (shell, n_directions, rule))``.
    """
    import nibabel as nib

    table = np.loadtxt(str(grad_path), ndmin=2)
    if table.shape[1] != 4:
        raise TrackingError(f"{grad_path} is not an MRtrix gradient table (x y z b)")
    b = table[:, 3]
    picked = pick_shell(b, shell)
    keep = (b < const.QSI_B0_THRESHOLD) | (np.abs(b - picked[0]) <= SHELL_TOLERANCE)
    img = nib.load(str(dwi_path))
    data = np.asarray(img.dataobj, dtype=np.float32)[..., keep]
    return data, img.affine, b[keep], table[keep, :3], picked


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


def act_criterion(wm, gm, csf, exit_mask=None):
    """DIPY's ACT criterion from binary tissue maps (``ActStoppingCriterion.from_pve``'s
    rule: include = GM + background, exclude = CSF), plus *exit_mask* as include.

    *exit_mask* marks where a streamline may legitimately end in white matter because the
    data end there -- MRtrix ACT's convention for the inferior brain-stem exit. Without it,
    a streamline running out of the DWI brain mask in the brain stem finds no fibre
    orientation, stops still "tracking" and DIPY drops it as invalid.
    """
    from dipy.tracking.stopping_criterion import ActStoppingCriterion

    include = gm.astype(np.float64)
    include[~(wm | gm | csf)] = 1.0
    if exit_mask is not None:
        include[exit_mask] = 1.0
    return ActStoppingCriterion(include, csf.astype(np.float64))


#: DIPY ``StreamlineStatus`` values -> names; ``NODIRECTION`` is a streamline whose next
#: point would still be ``TRACKPOINT`` (no direction found, or the length limit).
_STATES = {2: "ENDPOINT", 0: "INVALIDPOINT", -1: "OUTSIDEIMAGE", 1: "NODIRECTION"}


def end_states(streamlines, sc, affine) -> np.ndarray:
    """How each end of each streamline (world coordinates) stopped, (S, 2) of state names.

    DIPY does not return the terminal state, so it is read back: *sc* is checked one step
    beyond each end, along the last segment (the point that made DIPY stop is not stored).
    Approximate: the stopping step may turn, and on a synthetic tract about 2 % of ends
    are misread. A diagnostic, not a filter.
    """
    inv = np.linalg.inv(affine)
    out = np.empty((len(streamlines), 2), dtype=object)
    for k, s in enumerate(streamlines):
        s = np.asarray(s, np.float64)
        for j, (end, prev) in enumerate(((s[0], s[1]), (s[-1], s[-2]))):
            p = apply_affine(inv, 2 * end - prev)
            out[k, j] = _STATES.get(int(sc.check_point(np.ascontiguousarray(p))), "?")
    return out


def track_sh(
    shm,
    wm,
    gm,
    csf,
    affine,
    seeds_mask,
    cfg,
    *,
    n_seeds,
    n_jobs,
    return_all=False,
    exit_mask=None,
):
    """ACT probabilistic tracking on SH coefficients; streamlines in the affine's world."""
    from dipy.data import default_sphere
    from dipy.tracking.tracker import probabilistic_tracking
    from dipy.tracking.utils import random_seeds_from_mask

    sc = act_criterion(wm, gm, csf, exit_mask)
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
        pmf_threshold=cfg.pmf_threshold,
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


def flip_test(data, affine, bvals, bvecs, maps, reference, cfg, n_jobs) -> list[dict]:
    """Coherence of a small tractogram for each of the 8 gradient-axis sign flips.

    CSD is fitted and tracked in a :data:`FLIP_BLOCK`-voxel cube centred on the WM
    centroid, :data:`FLIP_SEEDS` seeds, for each flip; the streamlines (ACPC world) are
    scored with :func:`coherence` against *reference* (:func:`dti_reference`).
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
        sl = [s for s in sl if len(s) > 2]
        rows.append(
            {
                "flip": list(flip),
                "n_streamlines": len(sl),
                **coherence(sl, *reference),
            }
        )
        logger.info(f"flip test {flip}: {rows[-1]}")
    return rows


def track_csd(pm, subject_id: str, cfg, n_jobs: int) -> tuple[list, dict]:
    """Track one subject; returns streamlines in ACPC world and the QC fields."""
    import nibabel as nib
    from scipy.ndimage import binary_dilation

    inp = csd_inputs(pm, subject_id)
    data, affine, bvals, bvecs, (shell, shell_dirs, shell_rule) = load_shell(
        inp["dwi"], inp["grad"], cfg.shell
    )
    brain = np.asanyarray(nib.load(str(inp["dwi_mask"])).dataobj) > 0
    labels = labels_on_grid(inp["labels"], data.shape[:3], affine, inp["chain"])
    wm, gm, csf = (labels == WM), (labels == GM), (labels == CSF)
    deep_moved, exit_mask, aseg = 0, None, None
    if os.path.isfile(pm.tissue_labeling(subject_id)):
        aseg = labels_on_grid(
            pm.tissue_labeling(subject_id), data.shape[:3], affine, inp["chain"]
        )
        deep = np.isin(aseg, DEEP_GREY) & (wm | gm)
        deep_moved = int((deep & wm).sum())
        gm |= deep
        wm &= ~deep
    fit_mask = brain & binary_dilation(wm | gm, iterations=1)
    if aseg is not None:
        exit_mask = inferior_exit(aseg, fit_mask)
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
        shm,
        wm,
        gm,
        csf,
        affine,
        wm,
        cfg,
        n_seeds=cfg.n_seeds,
        n_jobs=n_jobs,
        exit_mask=exit_mask,
    )
    del shm
    info = {
        "inputs": {
            k: str(inp[k]) for k in ("dwi", "grad", "dwi_mask", "xfm", "labels")
        },
        "shell": shell,
        "shell_directions": shell_dirs,
        "shell_rule": shell_rule,
        "n_volumes": int(len(bvals)),
        "fit_voxels": int(fit_mask.sum()),
        "act_deep_grey_from_wm_voxels": deep_moved,
        "act_inferior_exit_voxels": (
            int(exit_mask.sum()) if exit_mask is not None else 0
        ),
        "acpc_to_t1": inp["chain"].round(6).tolist(),
        "acpc_to_t1_vs_dti_qc_max_abs": inp["chain_vs_dti_qc"],
        "csd": resp,
        "seconds": {"csd_fit": round(fit_s, 1), "tracking": round(time.time() - t0, 1)},
        "n_seeds": int(n_seeds),
        "dwi_affine": np.asarray(affine).tolist(),
    }
    t0 = time.time()
    reference, info["dti_reference"] = dti_reference(
        inp["dwi"], inp["grad"], inp["dwi_mask"]
    )
    info["seconds"]["dti_reference"] = round(time.time() - t0, 1)
    # CSD on the high shell against a tensor fitted on the low shell(s): two estimates
    info["coherence_vs_dti_v1"] = coherence(sl, *reference)
    if cfg.flip_test:
        t0 = time.time()
        info["flip_test"] = flip_test(
            data,
            affine,
            bvals,
            bvecs,
            (wm, gm, csf, fit_mask),
            reference,
            cfg,
            n_jobs,
        )
        info["flip_test_score"] = "median_abs_cos"
        info["seconds"]["flip_test"] = round(time.time() - t0, 1)
    return sl, info


# ── QC ───────────────────────────────────────────────────────────────────


def reference_bmax(bvals: np.ndarray) -> float:
    """b cut-off of the reference tensor: the extractor's 1500 s/mm^2 when a shell lies
    there, else the lowest shell (a single-shell b = 3000 scan)."""
    from tit.pre.qsi.dti_extractor import DTI_BMAX

    weighted = np.asarray(bvals)[np.asarray(bvals) > const.QSI_B0_THRESHOLD]
    if not len(weighted):
        raise TrackingError("the DWI has no diffusion-weighted volume")
    if weighted.min() <= DTI_BMAX:
        return DTI_BMAX
    return float(weighted.min()) + SHELL_TOLERANCE


def dti_reference(dwi_path, grad_path, mask_path) -> tuple[tuple, dict]:
    """The frame check's reference: principal eigenvector and FA of a tensor fitted here.

    DIPY ``TensorModel`` WLS (:func:`tit.pre.qsi.dti_extractor.fit_tensor`, the DTI
    extractor's own fit) on b0 + the shells up to :func:`reference_bmax`, with QSIPrep's
    world-RAS gradient table, so the eigenvectors are ACPC-world directions. Returns
    ``((e1 (X, Y, Z, 3), fa (X, Y, Z), affine), record for qc.json)``.
    """
    from tit.pre.qsi.dti_extractor import fit_tensor
    from tit.pre.utils import PreprocessError

    b = np.loadtxt(str(grad_path), ndmin=2)[:, 3]
    bmax = reference_bmax(b)
    try:
        tensors, affine, mask = fit_tensor(
            Path(dwi_path), Path(grad_path), Path(mask_path), bmax
        )
    except PreprocessError as exc:
        raise TrackingError(f"frame-check tensor: {exc}") from exc
    e1 = np.zeros(mask.shape + (3,))
    fa = np.zeros(mask.shape)
    vals, vecs = tm.eig_desc(tensors[mask])
    del tensors
    e1[mask] = vecs[:, :, 0]
    fa[mask], _ = tm.fa_md(vals)
    used = b <= bmax
    record = {
        "fit": "DIPY TensorModel WLS on the tracked QSIPrep DWI and brain mask",
        "bmax": bmax,
        "shells_b": sorted(
            {float(round(x, -2)) for x in b[used & (b > const.QSI_B0_THRESHOLD)]}
        ),
        "n_volumes": int(used.sum()),
    }
    return (e1, fa, affine), record


def coherence(
    streamlines,
    e1: np.ndarray,
    fa: np.ndarray,
    affine: np.ndarray,
    max_streamlines: int = 20_000,
) -> dict:
    """Median ``|t . e1|`` over streamline points where FA > 0.4 (spec V4).

    *streamlines* are in the reference's world (:func:`dti_reference`); tangents by
    central differences on a 1 mm resampling; ``e1`` and FA of the nearest voxel. Up to
    *max_streamlines* (evenly spaced) are scored.
    """
    if not len(streamlines):
        return {"median_abs_cos": None, "n_points": 0}
    pick = np.linspace(0, len(streamlines) - 1, min(len(streamlines), max_streamlines))
    sl = [streamlines[int(i)] for i in np.unique(pick.astype(int))]
    pts, off, h = geometry.resample(sl, 1.0)
    t = geometry.tangents(pts, off, h)
    vox = np.rint(apply_affine(np.linalg.inv(affine), pts)).astype(np.intp)
    ok = np.all((vox >= 0) & (vox < fa.shape), axis=1)
    v = tuple(vox[ok].T)
    keep = fa[v] > COHERENCE_FA
    cos = np.abs(np.einsum("pk,pk->p", t[ok][keep], e1[v][keep]))
    if not len(cos):
        return {"median_abs_cos": None, "n_points": 0}
    return {
        "median_abs_cos": float(np.median(cos)),
        "mean_abs_cos": float(np.mean(cos)),
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


def run_track(subject_id: str, cfg) -> dict:
    """The ``track`` stage: write ``tractogram.trx`` (m2m T1 world) and ``qc.json``.

    Returns the QC record. With ``cfg.flip_test``, raises :class:`TrackingError` (after
    writing ``qc.json``) when a flipped frame beats the unflipped one.
    """
    from tit.cpu import resolve_n_jobs
    from tit.paths import get_path_manager

    pm = get_path_manager()
    out_dir = pm.ensure(pm.tractography(subject_id))
    trx_path = os.path.join(out_dir, "tractogram.trx")
    if os.path.exists(trx_path) and not cfg.overwrite:
        raise TrackingError(f"{trx_path} exists; set track.overwrite to replace it")
    n_jobs = resolve_n_jobs(cfg.n_jobs)
    t0 = time.time()
    sl_native, info = track_csd(pm, subject_id, cfg, n_jobs)
    chain = np.asarray(info["acpc_to_t1"])
    if cfg.export_acpc_tck:
        import nibabel as nib

        ref = nib.Nifti1Image(
            np.zeros((1, 1, 1), np.uint8), np.asarray(info["dwi_affine"])
        )
        save_tractogram(os.path.join(out_dir, "tractogram_acpc.tck"), sl_native, ref)
    sl = [apply_affine(chain, s.astype(np.float64)) for s in sl_native]
    del sl_native
    save_tractogram(trx_path, sl, pm.t1(subject_id))
    qc = {
        "subject_id": subject_id,
        "space": "m2m T1 world, RAS mm (SimNIBS mesh coordinates)",
        "config": {k: getattr(cfg, k) for k in cfg.__dataclass_fields__},
        "n_workers": n_jobs,
        "n_streamlines": len(sl),
        "length_mm": _length_stats(sl),
        **info,
    }
    qc["seconds"]["total"] = round(time.time() - t0, 1)
    if qc.get("flip_test"):
        qc.update(flip_verdict(qc["flip_test"], qc["flip_test_score"]))
    Path(out_dir, "qc.json").write_text(json.dumps(qc, indent=1) + "\n")
    if qc.get("flip_test") and not qc["flip_test_passed"]:
        raise TrackingError(
            f"Gradient frame check failed: flip {qc['flip_test_winner']} beats the "
            f"unflipped frame (see {out_dir}/qc.json)."
        )
    return qc


def flip_verdict(rows: list[dict], key: str = "median_abs_cos") -> dict:
    """Did the unflipped frame win the 8-flip test on *key*, and by how much?

    Flipping all three axes reflects every direction through the origin, which leaves an
    antipodally symmetric ODF unchanged, so
    ``(-1, -1, -1)`` is the unflipped frame again and the 8 flips are 4 distinct frames.
    Passed when the best score belongs to the unflipped pair; the margin is its lower
    score minus the best of the other three frames.
    """
    score = {tuple(r["flip"]): r[key] or 0.0 for r in rows}
    same = [(1, 1, 1), (-1, -1, -1)]
    best = max(score, key=score.get)
    others = [v for k, v in score.items() if k not in same]
    return {
        "flip_test_winner": list(best),
        "flip_test_passed": best in same,
        "flip_test_margin": float(min(score[k] for k in same) - max(others)),
    }
