"""Non-blocking DTI checks and provenance recorded in ``DTI_coregT1_qc.json`` (numpy/scipy only).

The QC gate in :mod:`tit.pre.qsi.dti_extractor` decides whether a tensor is written; the advisories
here are measured on the same tensor, never block (ARCHITECTURE.md §9, §14), and are stored as
``tit.reporting.html.components.Check`` records whose label, role, citation and plain text come
from ``tit.reporting.qc_rules.RULES["dti"]``. The numbers behind them go to ``metrics``.

Everything works on world-frame tensors in a canonical RAS voxel order (:class:`DtiVolumes`), so
the numbers do not depend on how the grid is stored on disk. Cost on CHN (176 x 256 x 256, 1.4 M
tensors): about 9 s on an Apple M-series host, most of it the flip test and the residual-shift
search; hashing the 2 GB DWI for provenance adds a few seconds.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tit import constants as const

from . import tensor_math as tm

TISSUE = {1: "WM", 2: "GM", 3: "CSF"}
FA_BINS = np.linspace(0.0, 1.0, 51)
MD_BINS = np.linspace(0.0, 3.0e-3, 61)  # mm^2/s

#: SimNIBS 4.6 ``cond2elmdata`` defaults (``aniso_maxratio``, ``aniso_maxcond``), used by the
#: one-line ``vn`` note.
MAX_RATIO = 10.0
MAX_COND = 2.0

#: Landmark tracts: (name, expected axis 0=L-R 1=A-P 2=S-I, FA floor).
TRACTS = {
    "cc": ("Corpus callosum body", 0, 0.45),
    "cst": ("Corticospinal tract / PLIC", 2, 0.45),
    "cingulum": ("Cingulum", 1, 0.35),
}
#: Their MNI boxes: inclusive (|x|, y, z) ranges in mm.
_TRACT_BOXES = {
    "cc": ((0, 3), (-25, 15), (15, 28)),
    "cst": ((12, 28), (-28, -8), (-14, 12)),
    "cingulum": ((5, 10), (-35, 10), (30, 40)),
}

#: Flip test: every axis permutation times these sign flips (Jeurissen et al. 2014).
_FLIPS = {
    "none": (1, 1, 1),
    "flip x": (-1, 1, 1),
    "flip y": (1, -1, 1),
    "flip z": (1, 1, -1),
}
IDENTITY = "xyz none"


# ── volumes ────────────────────────────────────────────────────────────────


@dataclass
class DtiVolumes:
    """World-frame tensors and their anatomy on one canonical (RAS voxel order) grid.

    ``t6w`` holds ``(X, Y, Z, 6)`` world tensors in FSL order, zero where no tensor was written;
    ``mni`` is charm's ``Conform2MNI_nonl`` warp on the same grid (MNI mm per voxel) or ``None``.
    """

    affine: np.ndarray
    t1: np.ndarray
    labels: np.ndarray
    t6w: np.ndarray
    mni: np.ndarray | None = None

    @classmethod
    def from_arrays(cls, affine, t1, labels, t6w, mni=None) -> DtiVolumes:
        from tit.plotting.slices import canonical

        def ras(a, dtype):
            return canonical(np.asarray(a).astype(dtype, copy=False), affine)[0]

        t1_c, aff_c = canonical(np.asarray(t1, np.float32), affine)
        return cls(
            affine=aff_c,
            t1=t1_c,
            labels=ras(labels, np.uint8),
            t6w=ras(t6w, np.float32),
            mni=None if mni is None else ras(mni, np.float32),
        )

    @property
    def valid(self) -> np.ndarray:
        return np.any(self.t6w != 0, axis=-1)


def _labels(path: Path) -> np.ndarray:
    import nibabel as nib

    labels = np.asanyarray(nib.load(str(path)).dataobj)
    return labels[..., 0] if labels.ndim == 4 else labels


def load_volumes(m2m_dir: Path, tensor_path: Path | None = None) -> DtiVolumes:
    """Read the written tensor (SimNIBS frame), T1, labels and MNI warp of one m2m folder."""
    import nibabel as nib

    m2m_dir = Path(m2m_dir)
    img = nib.load(str(tensor_path or m2m_dir / const.FILE_DTI_TENSOR))
    stored = np.asanyarray(img.dataobj).astype(np.float32)
    valid = np.any(stored != 0, axis=-1)
    t6w = np.zeros(stored.shape, np.float32)
    t6w[valid] = tm.unsym(
        tm.simnibs_to_world(stored[valid].astype(np.float64), img.affine)
    )
    del stored
    t1 = np.asanyarray(nib.load(str(m2m_dir / const.FILE_T1)).dataobj)
    warp = m2m_dir / "toMNI" / "Conform2MNI_nonl.nii.gz"
    mni = np.asanyarray(nib.load(str(warp)).dataobj) if warp.is_file() else None
    labels = _labels(m2m_dir / "final_tissues.nii.gz")
    return DtiVolumes.from_arrays(img.affine, t1, labels, t6w, mni)


# ── statistics per tissue ──────────────────────────────────────────────────


def _hist(values: np.ndarray, bins: np.ndarray) -> list[float]:
    h, _ = np.histogram(values, bins=bins)
    return (h / max(h.sum(), 1)).round(6).tolist()


def tissue_stats(fa: np.ndarray, md: np.ndarray, labv: np.ndarray) -> dict:
    """Median, IQR and a normalised histogram of FA and MD per charm tissue (WM, GM, CSF)."""
    out = {}
    for k, name in TISSUE.items():
        s = labv == k
        if not s.any():
            continue
        f, d = fa[s], md[s]
        out[name] = {
            "n": int(s.sum()),
            "fa_median": float(np.median(f)),
            "fa_iqr": [float(np.percentile(f, 25)), float(np.percentile(f, 75))],
            "md_median": float(np.median(d)),
            "md_iqr": [float(np.percentile(d, 25)), float(np.percentile(d, 75))],
            "fa_hist": _hist(f, FA_BINS),
            "md_hist": _hist(d, MD_BINS),
        }
    return out


# ── orientation ────────────────────────────────────────────────────────────


def tract_orientation(t6w: np.ndarray, mni: np.ndarray) -> dict:
    """Share of high-FA voxels in three landmark tracts whose V1 lies along the expected world axis."""
    out = {}
    for key, (name, axis, fa_floor) in TRACTS.items():
        mask = np.ones(mni.shape[:3], bool)
        for i, (lo, hi) in enumerate(_TRACT_BOXES[key]):
            c = np.abs(mni[..., 0]) if i == 0 else mni[..., i]
            mask &= (c >= lo) & (c <= hi)
        w, v = tm.eig_desc(tm.sym(t6w[mask]))
        keep = (tm.fa_md(w)[0] > fa_floor) & (w[:, 2] > 0)
        along = np.argmax(np.abs(v[keep][:, :, 0]), 1) == axis
        out[key] = {
            "name": name,
            "n": int(keep.sum()),
            "frac_expected": float(along.mean()) if keep.any() else 0.0,
        }
    return out


def flip_test(
    t6w: np.ndarray,
    affine: np.ndarray,
    fa_vol: np.ndarray,
    labels: np.ndarray,
    step_mm: float = 1.5,
    n_seeds: int = 60000,
) -> dict:
    """Fibre coherence of V1 for every axis permutation and sign flip of the gradient table.

    From WM seeds with FA > 0.5, step ``step_mm`` along the transformed V1 both ways and score
    ``|V1_seed . V1_neighbour|``. A correct table scores highest as written (Jeurissen et al.
    2014); a flipped or permuted one breaks the continuity of tracts.
    """
    from scipy.ndimage import map_coordinates

    seeds = np.array(np.nonzero((fa_vol > 0.5) & (labels == 1)))
    if seeds.shape[1] > n_seeds:
        pick = np.random.default_rng(0).choice(seeds.shape[1], n_seeds, replace=False)
        seeds = seeds[:, pick]
    v1 = tm.eig_desc(tm.sym(t6w[tuple(seeds)]))[1][..., 0]
    world_to_voxel = np.linalg.inv(affine[:3, :3])
    comps = [t6w[..., c] for c in range(6)]
    scores = {}
    for perm in itertools.permutations(range(3)):
        for flip_name, flip in _FLIPS.items():
            q = np.diag(flip) @ np.eye(3)[list(perm)]
            v = v1 @ q.T
            both = []
            for sign in (1, -1):
                pos = seeds + sign * step_mm * (world_to_voxel @ v.T)
                nb = np.stack([map_coordinates(c, pos, order=1) for c in comps], -1)
                vn = tm.eig_desc(tm.sym(nb))[1][..., 0]
                both.append(np.abs((v * (vn @ q.T)).sum(-1)))
            name = f"{''.join('xyz'[i] for i in perm)} {flip_name}"
            scores[name] = float(np.mean(both))
    ranked = sorted(scores, key=scores.get, reverse=True)
    return {
        "scores": scores,
        "n_seeds": int(seeds.shape[1]),
        "best": ranked[0],
        "runner_up": ranked[1],
    }


# ── residual distortion ────────────────────────────────────────────────────


def _regions(mni: np.ndarray, labels: np.ndarray) -> dict[str, np.ndarray]:
    x, y, z = mni[..., 0], mni[..., 1], mni[..., 2]
    brain = np.isin(labels, (1, 2))
    return {
        "Frontal (y > 30)": brain & (y > 30),
        "Orbitofrontal (y > 15, z < 0)": brain & (y > 15) & (z < 0),
        "Central (−20 < y < 20)": brain & (y > -20) & (y <= 20),
        "Temporal (z < −5, |x| > 30)": brain & (z < -5) & (np.abs(x) > 30),
        "Posterior (y < −40)": brain & (y < -40),
        "Superior (z > 45)": brain & (z > 45),
    }


def residual_shift(
    fa_vol: np.ndarray,
    labels: np.ndarray,
    affine: np.ndarray,
    mni: np.ndarray,
    limit_mm: int = 5,
    max_voxels: int = 200_000,
) -> dict:
    """Per region, the world A–P and S–I shift of smoothed FA that best matches charm WM.

    A positive value moves FA anterior / superior, so ``+3`` means FA sits 3 mm posterior of the
    anatomy. Coarse-to-fine: every 2 mm within ±4 mm, then a 1 mm neighbourhood of each region's
    best, within ``±limit_mm``. The search space is the same as an exhaustive 1 mm grid for any
    smooth, single-peaked correlation surface, at a fraction of its cost.
    """
    from scipy.ndimage import gaussian_filter, map_coordinates

    smooth = gaussian_filter(fa_vol.astype(np.float32), 1.0)
    wm = labels == 1
    world_to_voxel = np.linalg.inv(affine[:3, :3])
    rng = np.random.default_rng(0)
    out = {}
    for name, mask in _regions(mni, labels).items():
        ijk = np.array(np.nonzero(mask), dtype=np.float64)
        if ijk.shape[1] < 100:
            continue
        if ijk.shape[1] > max_voxels:
            ijk = ijk[:, rng.choice(ijk.shape[1], max_voxels, replace=False)]
        target = wm[tuple(ijk.astype(int))].astype(np.float32)
        seen: dict[tuple[int, int], float] = {}

        def corr(a: int, s: int) -> float:
            if (a, s) not in seen:
                d = world_to_voxel @ np.array([0.0, a, s])
                vals = map_coordinates(
                    smooth, ijk - d[:, None], order=1, mode="nearest"
                )
                r = np.corrcoef(vals, target)[0, 1]
                seen[(a, s)] = float(r) if np.isfinite(r) else -1.0
            return seen[(a, s)]

        coarse = range(-4, 5, 2)
        a0, s0 = max(((a, s) for a in coarse for s in coarse), key=lambda k: corr(*k))
        near = [
            (a, s)
            for a in range(a0 - 1, a0 + 2)
            for s in range(s0 - 1, s0 + 2)
            if abs(a) <= limit_mm and abs(s) <= limit_mm
        ]
        best_a, best_s = max(near, key=lambda k: corr(*k))
        out[name] = {
            "n": int(mask.sum()),
            "corr0": corr(0, 0),
            "best_ap_mm": float(best_a),
            "best_si_mm": float(best_s),
            "gain": corr(best_a, best_s) - corr(0, 0),
        }
    return out


# ── conductivity note (mirrors SimNIBS 4.6 cond_utils) ─────────────────────


def fix_eigv(e: np.ndarray, max_value: float, max_ratio: float, c: float) -> np.ndarray:
    """SimNIBS 4.6 ``cond_utils._fix_eigv`` on descending eigenvalues (column 0 is the largest)."""
    e = np.array(e, dtype=np.float64)
    bad = np.all(e <= 0.0, axis=1) | np.all(np.isclose(e, 0), axis=1)
    e[bad] = c
    e[e > max_value] = max_value
    small = e < (e[:, 0] / max_ratio)[:, None]
    e[small[:, 1], 1] = e[small[:, 1], 0] / max_ratio
    e[small[:, 2], 2] = e[small[:, 2], 0] / max_ratio
    return e


def vn_eigenvalues(
    e: np.ndarray, c: float, max_cond: float = MAX_COND, max_ratio: float = MAX_RATIO
) -> np.ndarray:
    """Conductivity eigenvalues of ``vn``: normalise to unit volume, clamp, renormalise, clamp, times *c*."""
    e = np.array(e, dtype=np.float64)
    e /= (np.abs(e).prod(axis=1) ** (1.0 / 3.0))[:, None]
    e = fix_eigv(e, max_cond, max_ratio, c)
    e /= (e.prod(axis=1) ** (1.0 / 3.0))[:, None]
    return fix_eigv(e, max_cond, max_ratio, c) * c


def conductivity_preview(w: np.ndarray, labv: np.ndarray) -> dict:
    """How often SimNIBS's anisotropy clamps bind in WM: the ratio cap (any mode) and ``vn``'s ``aniso_maxcond``."""
    e = w[labv == 1]
    if not len(e):
        return {}
    c = const.CONDUCTIVITY_WHITE_MATTER
    sigma = vn_eigenvalues(e, c)
    ratio = e[:, 0] / np.maximum(e[:, 2], 1e-12)
    return {
        "max_ratio": MAX_RATIO,
        "max_cond": MAX_COND,
        "pct_wm_ratio_clamped": float(100 * np.mean(ratio > MAX_RATIO)),
        "pct_wm_vn_maxcond": float(100 * np.mean(sigma[:, 0] >= MAX_COND * c - 1e-12)),
    }


# ── QSIPrep record: SDC, acquisition, motion ───────────────────────────────


def _last(paths) -> Path | None:
    return max(paths, default=None)


def _tsv(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _image_qc(qsiprep_sub: Path) -> dict:
    return (_tsv(_last(qsiprep_sub.glob("dwi/*desc-image_qc.tsv"))) or [{}])[0]


def sdc_status(qsiprep_sub: Path, bids_sub: Path) -> dict:
    """What QSIPrep reported for susceptibility distortion correction, and the DWI fieldmaps on disk."""
    page = _last(qsiprep_sub.glob("figures/*desc-summary_dwi.html"))
    summary = (
        dict(re.findall(r"<li>([^:<]+):\s*([^<]*)</li>", page.read_text()))
        if page
        else {}
    )
    fmaps = []
    for nii in sorted((bids_sub / "fmap").glob("*_epi.nii*")):
        sidecar = nii.with_name(re.sub(r"\.nii(\.gz)?$", ".json", nii.name))
        meta = json.loads(sidecar.read_text()) if sidecar.is_file() else {}
        intended = meta.get("IntendedFor") or []
        intended = [intended] if isinstance(intended, str) else intended
        if "acq-dwi" in nii.name or any("dwi/" in i for i in intended):
            fmaps.append(
                {
                    "file": nii.name,
                    "has_json": sidecar.is_file(),
                    "intended_for": intended,
                }
            )
    reported = summary.get("Susceptibility distortion correction")
    return {
        "reported": reported,
        "applied": bool(reported) and reported.strip().lower() not in ("none", ""),
        "pe_direction": summary.get("Phase-encoding (PE) direction"),
        "dwi_fmaps": fmaps,
    }


def acquisition(qsiprep_sub: Path) -> dict:
    """Scanner, shells and QSIPrep settings from QSIPrep's own output files."""
    import tomllib

    dwi_json = _last(qsiprep_sub.glob("dwi/*_space-ACPC_desc-preproc_dwi.json"))
    meta = json.loads(dwi_json.read_text()) if dwi_json else {}
    grad = _last(qsiprep_sub.glob("dwi/*_space-ACPC_desc-preproc_dwi.b"))
    bvals = np.loadtxt(grad, ndmin=2)[:, 3].tolist() if grad else []
    qc = _image_qc(qsiprep_sub)
    toml_path = _last(qsiprep_sub.glob("log/*/qsiprep.toml"))
    toml = tomllib.loads(toml_path.read_text()) if toml_path else {}
    about = _last(qsiprep_sub.glob("figures/*_about.html"))
    command = (
        re.search(r"<code>(.*?)</code>", about.read_text(), re.S) if about else None
    )
    keys = (
        "Manufacturer",
        "ManufacturersModelName",
        "MagneticFieldStrength",
        "PhaseEncodingDirection",
    )
    settings = ("denoise_method", "unringing_method", "hmc_model", "output_resolution")
    return {
        "scanner": {k: meta.get(k) for k in keys},
        "raw_voxel_mm": [_num(qc.get(f"raw_voxel_size_{a}")) for a in "xyz"],
        "bvals": [round(b, 1) for b in bvals],
        "shells": dict(Counter(str(int(round(b, -2))) for b in bvals)),
        "qsiprep": {
            "version": toml.get("environment", {}).get("version"),
            "command": command.group(1).strip() if command else None,
            **{k: toml.get("workflow", {}).get(k) for k in settings},
        },
    }


def motion(qsiprep_sub: Path) -> dict:
    """Framewise displacement per volume and QSIPrep's image-quality numbers."""
    rows = _tsv(_last(qsiprep_sub.glob("dwi/*desc-confounds_timeseries.tsv")))
    fd = [_num(r.get("framewise_displacement")) or 0.0 for r in rows]
    qc = _image_qc(qsiprep_sub)
    return {
        "fd": [round(x, 4) for x in fd],
        "mean_fd": float(np.mean(fd[1:])) if len(fd) > 1 else None,
        "max_fd": float(np.max(fd)) if fd else None,
        "neighbor_corr": _num(qc.get("raw_neighbor_corr")),
        "t1_dice_distance": _num(qc.get("t1_dice_distance")),
        "num_bad_slices": _num(qc.get("raw_num_bad_slices")),
    }


# ── advisories ─────────────────────────────────────────────────────────────


def advisories(
    metrics: dict, sdc: dict, mot: dict, acq: dict, reference_fa: float | None = None
) -> list[dict]:
    """The non-blocking rows, as QC-check records: advisories (warn, never block) and reported values.

    Label, rule text, role and citations come from ``tit.reporting.qc_rules.RULES["dti"]``.
    """
    from tit.reporting.qc_rules import RULES

    rows = {}  # rule key -> (shown, threshold, status, value)
    reported = sdc["reported"]
    sdc_st = "info" if reported is None else ("pass" if sdc["applied"] else "warn")
    rows["sdc_applied"] = (reported or "unknown", "applied", sdc_st, None)
    if shift := metrics.get("residual_shift"):
        voxel = max((v for v in acq.get("raw_voxel_mm", []) if v), default=2.0)
        worst = max(
            max(abs(r["best_ap_mm"]), abs(r["best_si_mm"])) for r in shift.values()
        )
        rows["residual_shift_mm"] = (
            f"{worst:.0f} mm",
            f"≤ {voxel:g} mm (1 DWI voxel)",
            "warn" if worst > voxel else "pass",
            worst,
        )
    if tracts := metrics.get("tracts"):
        floor = RULES["dti"]["tract_frac_expected"]["value"]
        fracs = [t["frac_expected"] for t in tracts.values()]
        rows["tract_frac_expected"] = (
            " / ".join(f"{100 * f:.0f} %" for f in fracs),
            f"≥ {100 * floor:.0f} % each",
            "pass" if min(fracs) >= floor else "warn",
            None,
        )
    flip = metrics["flip_test"]
    scores, ok = flip["scores"], flip["best"] == IDENTITY
    other = flip["runner_up"] if ok else flip["best"]
    rows["flip_identity_best"] = (
        f"as given {scores[IDENTITY]:.4f}; {'next' if ok else 'best'} {other} {scores[other]:.4f} (margin {scores[IDENTITY] - scores[other]:+.4f})",
        f"as given scores best of {len(scores)}",
        "pass" if ok else "warn",
        scores[IDENTITY],
    )
    if mot.get("mean_fd") is not None:
        rows["mean_fd_mm"] = (
            f"{mot['mean_fd']:.2f} mm mean FD (largest step {mot['max_fd']:.2f} mm)",
            "reference only",
            "info",
            mot["mean_fd"],
        )
    if "WM" in metrics.get("tissue", {}):
        fa = metrics["tissue"]["WM"]["fa_median"]
        ref = (
            "no reference subject"
            if reference_fa is None
            else f"reference subject {reference_fa:.2f}"
        )
        rows["wm_fa_median"] = (f"{fa:.2f}", ref, "info", fa)
    iqm = [
        f"{name} {mot[k]:.3g}"
        for name, k in (
            ("neighbour correlation", "neighbor_corr"),
            ("T1 Dice distance", "t1_dice_distance"),
            ("bad slices", "num_bad_slices"),
        )
        if mot.get(k) is not None
    ]
    if iqm:
        rows["qsiprep_iqms"] = (" · ".join(iqm), "no accepted cut-off", "info", None)
    return [
        {
            "id": key,
            "label": r["label"],
            "description": r["plain"],
            "shown": shown,
            "threshold": threshold,
            "status": st,
            "role": r["role"],
            "value": v,
            "rail": None,
            "cite": r["cite"],
            "note": r["note"],
        }
        for key, (shown, threshold, st, v) in rows.items()
        for r in [RULES["dti"][key]]
    ]


def measure(vols: DtiVolumes) -> dict:
    """Every tensor-derived number the report shows: tissue statistics, orientation, flip test, shifts."""
    t0 = time.time()
    valid = vols.valid
    w, _ = tm.eig_desc(tm.sym(vols.t6w[valid]))
    fa, md = tm.fa_md(w)
    labv = vols.labels[valid]
    fa_vol = np.zeros(valid.shape, np.float32)
    fa_vol[valid] = fa
    has_mni = vols.mni is not None
    zooms = np.linalg.norm(vols.affine[:3, :3], axis=0)
    metrics = {
        "grid": {
            "shape": list(valid.shape),
            "zooms": [round(float(z), 4) for z in zooms],
        },
        "fa_bins": FA_BINS.tolist(),
        "md_bins": MD_BINS.tolist(),
        "tissue": tissue_stats(fa, md, labv),
        "conductivity": conductivity_preview(w, labv),
        "flip_test": flip_test(vols.t6w, vols.affine, fa_vol, vols.labels),
        "tracts": tract_orientation(vols.t6w, vols.mni) if has_mni else None,
        "residual_shift": (
            residual_shift(fa_vol, vols.labels, vols.affine, vols.mni)
            if has_mni
            else None
        ),
    }
    metrics["seconds"] = round(time.time() - t0, 1)
    return metrics


def compute(
    vols: DtiVolumes,
    qsiprep_sub: Path,
    bids_sub: Path,
    reference_fa: float | None = None,
) -> dict:
    """The QC-JSON additions: ``advisories``, ``metrics``, ``acquisition``, ``motion``, ``sdc``.

    *reference_fa* is the reference subject's WM median FA (:func:`reference`), shown beside this one's.
    """
    qsiprep_sub = Path(qsiprep_sub)
    metrics = measure(vols)
    acq, mot = acquisition(qsiprep_sub), motion(qsiprep_sub)
    sdc = sdc_status(qsiprep_sub, Path(bids_sub))
    return {
        "advisories": advisories(metrics, sdc, mot, acq, reference_fa),
        "metrics": metrics,
        "acquisition": acq,
        "motion": mot,
        "sdc": sdc,
    }


# ── provenance ─────────────────────────────────────────────────────────────


def sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _version(dist: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(dist)
    except PackageNotFoundError:
        return None


def provenance(
    inputs: dict[str, Path],
    config: dict,
    project_dir: Path,
    qsiprep_version: str | None,
    recorded_by: str,
) -> dict:
    """Software versions, input SHA-256s (paths relative to the project) and the configuration hash."""
    import tit

    project_dir = Path(project_dir).resolve()

    def rel(p: Path) -> str:
        p = Path(p).resolve()
        if p.is_relative_to(project_dir):
            return f"<project>/{p.relative_to(project_dir)}"
        return str(p)

    blob = json.dumps(config, sort_keys=True, default=list).encode()
    return {
        "recorded_by": recorded_by,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "versions": {
            "ti_toolbox": tit.__version__,
            "python": sys.version.split()[0],
            "qsiprep": qsiprep_version,
            **{
                n: _version(n) for n in ("simnibs", "dipy", "numpy", "scipy", "nibabel")
            },
        },
        "config": config,
        "config_hash": hashlib.sha256(blob).hexdigest(),
        "inputs": {
            name: {"path": rel(p), "sha256": sha256(p), "bytes": Path(p).stat().st_size}
            for name, p in inputs.items()
            if p and Path(p).is_file()
        },
    }


REFERENCE_SUBJECT = "ernie"


def reference(project_dir: str | Path, subject_id: str) -> dict | None:
    """White-matter median FA of the project's ernie tensor (SimNIBS's example subject), if it has one."""
    import nibabel as nib

    from tit.paths import get_path_manager

    if subject_id == REFERENCE_SUBJECT:
        return None
    m2m = Path(get_path_manager(str(project_dir)).m2m(REFERENCE_SUBJECT))
    if not (m2m / const.FILE_DTI_TENSOR).is_file():
        return None
    img = nib.load(str(m2m / const.FILE_DTI_TENSOR))
    labels = _labels(m2m / "final_tissues.nii.gz")
    stored = np.asanyarray(img.dataobj)[labels == 1].astype(np.float64)
    stored = stored[np.any(stored != 0, axis=-1)]
    fa, _ = tm.fa_md(np.linalg.eigvalsh(tm.simnibs_to_world(stored, img.affine)))
    return {"subject": REFERENCE_SUBJECT, "wm_fa_median": float(np.median(fa))}
