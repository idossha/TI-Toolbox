#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
DTI tensor for SimNIBS, fitted with DIPY on QSIPrep's preprocessed DWI.

Route (DECISIONS.md, 2026-09-27 "DTI via DIPY on QSIPrep output"):

1. DIPY ``TensorModel`` WLS fit on the ACPC-space DWI, shells b <= 1500 only, with
   QSIPrep's ``.b`` gradient table (MRtrix convention: scanner/world RAS), so the
   fitted quadratic form is already a world-frame tensor.
2. The exact QSIPrep ACPC -> raw-T1 map from QSIPrep's own files
   (:func:`tit.pre.qsi.tensor_math.acpc_to_t1_world`). A same-modality NCC rigid
   refinement of QSIPrep's ACPC T1 against the m2m T1 is a QC check, never the map.
3. Normalised trilinear resampling onto the m2m ``T1.nii.gz`` grid, every tensor
   rotated by the polar factor of the map, then a brain mask.
4. Stored in the frame SimNIBS ``cond2elmdata(correct_FSL=True)`` reads back as the
   world tensor, beside ``DTI_coregT1_qc.json``. A tensor that fails the QC gate is
   not written.

No QSIRecon, no DSI Studio.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from tit import constants as const
from tit.paths import get_path_manager
from tit.pre.utils import PreprocessError, _find_nifti

from . import tensor_math as tm

#: Tensor fit shell cut-off (s/mm^2). DIPY WLS on b <= 1500 matches DSI Studio's
#: OLS on b <= 1750 within 0.5 deg on CHN (dti_eval q1/fit_shells.txt).
DTI_BMAX = 1500.0
#: WM|GM dilation, in voxels of the 1 mm m2m grid, before intersecting with the head.
MASK_DILATE_VOX = 2
#: charm labels kept: WM, GM, CSF.
BRAIN_LABELS = (1, 2, 3)

#: QC gate. CHN measured 0.984 / 0.04 mm / 100 % / 0.8 % / 0 / 0.68e-3
#: (dti_eval chn/DTI_coregT1_qc.json); the synthetic round trip NCC 0.9999.
QC_MIN_NCC = 0.90
QC_MAX_CHAIN_VS_NCC_MM = 1.0
QC_MIN_PD_PCT = 99.0
QC_MAX_WMGM_ZERO_PCT = 5.0
QC_WM_MD_RANGE = (0.5e-3, 1.1e-3)  # mm^2/s, adult in vivo at b ~ 1000


@dataclass
class DtiQc:
    """What ``DTI_coregT1_qc.json`` records."""

    ncc_chain: float
    chain_vs_ncc_mm: float
    pct_pd: float
    pct_wm_covered: float
    pct_gm_covered: float
    pct_wmgm_zero: float
    wm_md_median: float
    wm_fa_median: float
    n_out_of_brain: int
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    acpc_to_t1: list[list[float]] = field(default_factory=list)
    thresholds: dict = field(
        default_factory=lambda: {
            "min_ncc": QC_MIN_NCC,
            "max_chain_vs_ncc_mm": QC_MAX_CHAIN_VS_NCC_MM,
            "min_pct_pd": QC_MIN_PD_PCT,
            "max_pct_wmgm_zero": QC_MAX_WMGM_ZERO_PCT,
            "wm_md_range": list(QC_WM_MD_RANGE),
            "max_out_of_brain": 0,
        }
    )

    def gate(self) -> None:
        """Fill ``passed``/``failures`` from the measured values."""
        checks = {
            "ncc_chain": self.ncc_chain >= QC_MIN_NCC,
            "chain_vs_ncc_mm": self.chain_vs_ncc_mm <= QC_MAX_CHAIN_VS_NCC_MM,
            "pct_pd": self.pct_pd >= QC_MIN_PD_PCT,
            "pct_wmgm_zero": self.pct_wmgm_zero <= QC_MAX_WMGM_ZERO_PCT,
            "wm_md_median": QC_WM_MD_RANGE[0] <= self.wm_md_median <= QC_WM_MD_RANGE[1],
            "n_out_of_brain": self.n_out_of_brain == 0,
        }
        self.failures = [name for name, ok in checks.items() if not ok]
        self.passed = not self.failures


# ── fit ──────────────────────────────────────────────────────────────────


def fit_tensor(
    dwi_path: Path, grad_path: Path, mask_path: Path, bmax: float = DTI_BMAX
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """DIPY WLS tensor fit on shells ``b <= bmax``.

    *grad_path* is QSIPrep's MRtrix ``.b`` table (``x y z b`` per volume, directions in
    scanner RAS), so the result is a world-frame tensor field. Returns
    ``(tensors (X, Y, Z, 3, 3), affine, mask)``, zero outside the mask.
    """
    table = np.loadtxt(str(grad_path), ndmin=2)
    if table.shape[1] != 4:
        raise PreprocessError(f"{grad_path} is not an MRtrix gradient table (x y z b)")
    keep = table[:, 3] <= bmax
    n_weighted = int((table[keep, 3] > const.QSI_B0_THRESHOLD).sum())
    if n_weighted < const.QSI_MIN_DWI_DIRECTIONS:
        raise PreprocessError(
            f"{dwi_path.name} has {n_weighted} diffusion-weighted volume(s) with "
            f"b <= {bmax:g}; a tensor needs at least {const.QSI_MIN_DWI_DIRECTIONS}."
        )
    import nibabel as nib
    from dipy.core.gradients import gradient_table
    from dipy.reconst.dti import TensorModel

    img = nib.load(str(dwi_path))
    data = np.asanyarray(img.dataobj)
    if data.ndim != 4 or data.shape[3] != len(table):
        raise PreprocessError(
            f"{dwi_path.name} has shape {data.shape} but {grad_path.name} lists "
            f"{len(table)} volumes."
        )
    data = data[..., keep].astype(np.float32)
    mask = np.asanyarray(nib.load(str(mask_path)).dataobj) > 0
    gtab = gradient_table(
        table[keep, 3], bvecs=table[keep, :3], b0_threshold=const.QSI_B0_THRESHOLD
    )
    tensors = TensorModel(gtab, fit_method="WLS").fit(data, mask=mask).quadratic_form
    tensors = np.nan_to_num(np.asarray(tensors, dtype=np.float64))
    tensors[~mask] = 0
    return tensors, img.affine, mask


# ── transforms and QC registration ───────────────────────────────────────


def read_itk_transform(path: Path) -> np.ndarray:
    """An ANTs/ITK ``.mat`` (as QSIPrep writes it) -> 4x4 RAS point map."""
    import scipy.io as sio

    mat = sio.loadmat(str(path))
    keys = [
        k
        for k in mat
        if k.startswith(("Euler3DTransform", "AffineTransform", "MatrixOffset"))
    ]
    if not keys or "fixed" not in mat:
        raise PreprocessError(f"{path} is not an ITK linear transform file")
    return tm.itk_euler_to_ras(mat[keys[0]], mat["fixed"])


def _rigid(params: np.ndarray) -> np.ndarray:
    from scipy.spatial.transform import Rotation

    out = np.eye(4)
    out[:3, :3] = Rotation.from_rotvec(params[:3]).as_matrix()
    out[:3, 3] = params[3:6]
    return out


def _rigid_params(matrix: np.ndarray) -> np.ndarray:
    from scipy.spatial.transform import Rotation

    return np.r_[
        Rotation.from_matrix(tm.polar_rotation(matrix)).as_rotvec(), matrix[:3, 3]
    ]


def _ncc_function(mov, mov_aff, mov_mask, fix, fix_aff, n=60000, seed=0, smooth=1.0):
    """NCC of *fix* sampled at ``G(moving points)``, as a function of ``G``."""
    from scipy.ndimage import gaussian_filter, map_coordinates

    ijk = np.array(np.nonzero(mov_mask), dtype=float)
    if ijk.shape[1] > n:
        pick = np.random.default_rng(seed).choice(ijk.shape[1], n, replace=False)
        ijk = ijk[:, pick]
    mov_values = map_coordinates(
        gaussian_filter(mov.astype(np.float32), smooth), ijk, order=1
    )
    points = mov_aff[:3, :3] @ ijk + mov_aff[:3, 3:4]
    fix_smooth = gaussian_filter(fix.astype(np.float32), smooth)
    fix_inv = np.linalg.inv(fix_aff)

    def ncc(matrix: np.ndarray) -> float:
        world = matrix[:3, :3] @ points + matrix[:3, 3:4]
        vox = fix_inv[:3, :3] @ world + fix_inv[:3, 3:4]
        r = np.corrcoef(map_coordinates(fix_smooth, vox, order=1, cval=0), mov_values)[
            0, 1
        ]
        return float(r) if np.isfinite(r) else -1.0

    return ncc


def check_registration(
    chain: np.ndarray,
    acpc_t1: np.ndarray,
    acpc_aff: np.ndarray,
    acpc_mask: np.ndarray,
    m2m_t1: np.ndarray,
    m2m_aff: np.ndarray,
) -> tuple[float, float]:
    """``(NCC under the chain, mean brain displacement chain vs NCC refinement, mm)``.

    Same-modality (QSIPrep's ACPC T1 vs the m2m T1) rigid refinement, Powell on -NCC,
    started from the chain. Only a QC measurement: the tensor always uses the chain.
    """
    from scipy.optimize import minimize

    ncc = _ncc_function(acpc_t1, acpc_aff, acpc_mask, m2m_t1, m2m_aff)
    result = minimize(
        lambda x: -ncc(_rigid(x)),
        _rigid_params(chain),
        method="Powell",
        options={"xtol": 1e-4, "ftol": 1e-7, "maxfev": 8000},
    )
    refined = _rigid(result.x)
    pts = np.array(np.nonzero(acpc_mask), dtype=float)[:, ::50]
    pts = acpc_aff[:3, :3] @ pts + acpc_aff[:3, 3:4]
    shift = (chain[:3, :3] - refined[:3, :3]) @ pts + (
        chain[:3, 3:4] - refined[:3, 3:4]
    )
    return ncc(chain), float(np.linalg.norm(shift, axis=0).mean())


# ── resampling ───────────────────────────────────────────────────────────


def resample_tensor(
    tensors_src: np.ndarray,
    src_affine: np.ndarray,
    src_valid: np.ndarray,
    src_to_tgt: np.ndarray,
    tgt_shape,
    tgt_affine: np.ndarray,
    chunk: int = 4_000_000,
    min_weight: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Pull a world-frame tensor field onto a target grid through the map *src_to_tgt*.

    Components are interpolated trilinearly (order 1, monotone: no spline ringing) as
    a normalised convolution over valid voxels (divided by the interpolated validity),
    so edge voxels are not shrunk towards zero. Every tensor is then rotated by the
    polar factor of *src_to_tgt*. Returns ``(tensors (X, Y, Z, 3, 3), valid)``.
    """
    from scipy.ndimage import map_coordinates

    tgt_shape = tuple(int(s) for s in tgt_shape)
    tgt_vox_to_src_vox = (
        np.linalg.inv(src_affine) @ np.linalg.inv(src_to_tgt) @ tgt_affine
    )
    rot = tm.polar_rotation(src_to_tgt)
    t6 = tm.unsym(tensors_src).astype(np.float32)
    weight = src_valid.astype(np.float32)
    out = np.zeros(tgt_shape + (6,), np.float32)
    valid = np.zeros(tgt_shape, bool)
    flat_out, flat_valid = out.reshape(-1, 6), valid.reshape(-1)
    total = int(np.prod(tgt_shape))
    for start in range(0, total, chunk):
        idx = np.arange(start, min(total, start + chunk))
        ijk = np.array(np.unravel_index(idx, tgt_shape), dtype=float)
        src = tgt_vox_to_src_vox[:3, :3] @ ijk + tgt_vox_to_src_vox[:3, 3:4]
        wsum = map_coordinates(weight, src, order=1, cval=0)
        ok = wsum >= min_weight
        if not ok.any():
            continue
        vals = np.stack(
            [
                map_coordinates(t6[..., c], src[:, ok], order=1, cval=0)
                for c in range(6)
            ],
            axis=-1,
        )
        vals /= wsum[ok][:, None]
        flat_out[idx[ok]] = tm.unsym(tm.rotate(tm.sym(vals), rot))
        flat_valid[idx[ok]] = True
    return tm.sym(out), valid


# ── I/O helpers ──────────────────────────────────────────────────────────


def _save_nifti_gz(data: np.ndarray, affine: np.ndarray, output_path: Path) -> None:
    """Save ``.nii.gz`` via a plain ``.nii`` + stdlib gzip (bind mounts break nibabel's)."""
    import gzip
    import tempfile

    import nibabel as nib

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_nii = Path(tmpdir) / "tensor.nii"
        tmp_gz = Path(tmpdir) / "tensor.nii.gz"
        nib.save(nib.Nifti1Image(data, affine), str(tmp_nii))
        with open(tmp_nii, "rb") as f_in, gzip.open(str(tmp_gz), "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        shutil.copy2(str(tmp_gz), str(output_path))


def _one(paths: list[Path], what: str, where: Path) -> Path:
    if len(paths) != 1:
        found = ", ".join(p.name for p in paths) or "none"
        raise PreprocessError(
            f"Expected exactly one QSIPrep {what} under {where}; found {found}. "
            "Run QSIPrep for this subject (one DWI series per subject is supported)."
        )
    return paths[0]


def qsiprep_inputs(qsiprep_sub: Path) -> dict[str, Path]:
    """Locate the QSIPrep files the DTI step reads, or raise naming the missing one."""
    dwi = _one(
        sorted(qsiprep_sub.glob("**/dwi/*_space-ACPC_desc-preproc_dwi.nii.gz")),
        "preprocessed DWI",
        qsiprep_sub,
    )
    stem = dwi.name[: -len("_desc-preproc_dwi.nii.gz")]
    anat = qsiprep_sub / "anat"
    paths = {
        "dwi": dwi,
        "grad": dwi.with_name(f"{stem}_desc-preproc_dwi.b"),
        "dwi_mask": dwi.with_name(f"{stem}_desc-brain_mask.nii.gz"),
        "xfm": _one(
            sorted(anat.glob("*_from-ACPC_to-anat_mode-image_xfm.mat")),
            "ACPC-to-anat transform",
            anat,
        ),
        "acpc_t1": _one(
            sorted(anat.glob("*_space-ACPC_desc-preproc_T1w.nii.gz")),
            "ACPC T1w",
            anat,
        ),
        "acpc_mask": _one(
            sorted(anat.glob("*_space-ACPC_desc-brain_mask.nii.gz")),
            "ACPC brain mask",
            anat,
        ),
    }
    for name, path in paths.items():
        if not path.is_file():
            raise PreprocessError(f"QSIPrep output missing ({name}): {path}")
    return paths


# ── public API ───────────────────────────────────────────────────────────


def extract_dti_tensor(
    project_dir: str,
    subject_id: str,
    *,
    logger: logging.Logger,
) -> Path:
    """Fit, register and write ``DTI_coregT1_tensor.nii.gz`` for *subject_id*.

    Reads QSIPrep output and the charm m2m folder; writes the tensor and
    ``DTI_coregT1_qc.json`` into the m2m folder, then a DTI QC report.

    Raises
    ------
    tit.pre.utils.PreprocessError
        Missing inputs, an existing tensor, an m2m T1 that is not the T1w QSIPrep
        used, or a failed QC gate (the QC JSON is still written; the tensor is not).
    """
    import nibabel as nib
    from scipy.ndimage import binary_dilation

    pm = get_path_manager(project_dir)
    m2m_dir = Path(pm.m2m(subject_id))
    output_path = m2m_dir / const.FILE_DTI_TENSOR
    qc_path = m2m_dir / const.FILE_DTI_QC
    t1_path = m2m_dir / const.FILE_T1
    labels_path = m2m_dir / "final_tissues.nii.gz"
    for path, fix in ((t1_path, "Run charm first."), (labels_path, "Run charm first.")):
        if not path.is_file():
            raise PreprocessError(f"{path} not found. {fix}")
    if output_path.exists():
        raise PreprocessError(
            f"DTI tensor already exists at {output_path}. Remove it before rerunning."
        )
    raw_t1_path = _find_nifti(Path(pm.bids_anat(subject_id)), f"sub-{subject_id}_T1w")
    if raw_t1_path is None:
        raise PreprocessError(
            f"sub-{subject_id}_T1w not found in {pm.bids_anat(subject_id)}; the "
            "transform chain starts from the T1w QSIPrep used."
        )
    inputs = qsiprep_inputs(Path(pm.qsiprep_subject(subject_id)))

    t1 = nib.load(str(t1_path))
    raw = nib.load(str(raw_t1_path))
    if raw.shape[:3] != t1.shape[:3] or not np.allclose(
        raw.affine, t1.affine, atol=1e-3
    ):
        raise PreprocessError(
            f"The m2m T1 grid ({t1_path}) differs from the raw T1w QSIPrep used "
            f"({raw_t1_path}). The QSIPrep transform chain is only valid when charm "
            "ran on that same T1w file."
        )
    labels = np.asanyarray(nib.load(str(labels_path)).dataobj)
    labels = labels[..., 0] if labels.ndim == 4 else labels
    if labels.shape != t1.shape[:3]:
        raise PreprocessError(f"{labels_path} is not on the T1 grid {t1.shape[:3]}")

    logger.info(f"DTI: WLS tensor fit (b <= {DTI_BMAX:g}) on {inputs['dwi'].name}")
    tensors_acpc, acpc_affine, fit_mask = fit_tensor(
        inputs["dwi"], inputs["grad"], inputs["dwi_mask"]
    )

    chain = tm.acpc_to_t1_world(
        raw.affine, raw.shape[:3], read_itk_transform(inputs["xfm"])
    )
    acpc_t1 = nib.load(str(inputs["acpc_t1"]))
    acpc_mask = np.asanyarray(nib.load(str(inputs["acpc_mask"])).dataobj) > 0
    logger.info("DTI: checking the QSIPrep ACPC -> T1 chain against an NCC refinement")
    ncc, disp = check_registration(
        chain,
        np.asanyarray(acpc_t1.dataobj, dtype=np.float32),
        acpc_t1.affine,
        acpc_mask,
        np.asanyarray(t1.dataobj, dtype=np.float32),
        t1.affine,
    )

    logger.info("DTI: resampling onto the m2m T1 grid with tensor rotation")
    tensors, valid = resample_tensor(
        tensors_acpc, acpc_affine, fit_mask, chain, t1.shape[:3], t1.affine
    )
    del tensors_acpc
    wmgm = np.isin(labels, (1, 2))
    mask = (
        valid
        & binary_dilation(wmgm, iterations=MASK_DILATE_VOX)
        & np.isin(labels, BRAIN_LABELS)
    )
    tensors[~mask] = 0

    eigenvalues, _ = tm.eig_desc(tensors[mask])
    fa, md = tm.fa_md(eigenvalues)
    wm_in_mask = (labels == 1)[mask]
    qc = DtiQc(
        ncc_chain=float(ncc),
        chain_vs_ncc_mm=disp,
        pct_pd=(
            float(100 * (eigenvalues[:, -1] > 0).mean()) if len(eigenvalues) else 0.0
        ),
        pct_wm_covered=float(100 * mask[labels == 1].mean()),
        pct_gm_covered=float(100 * mask[labels == 2].mean()),
        pct_wmgm_zero=float(100 * (~mask[wmgm]).mean()),
        wm_md_median=float(np.median(md[wm_in_mask])) if wm_in_mask.any() else 0.0,
        wm_fa_median=float(np.median(fa[wm_in_mask])) if wm_in_mask.any() else 0.0,
        n_out_of_brain=int((mask & ~np.isin(labels, BRAIN_LABELS)).sum()),
        acpc_to_t1=chain.round(6).tolist(),
    )
    qc.gate()
    qc_path.write_text(json.dumps(asdict(qc), indent=1) + "\n")
    logger.info(
        f"DTI QC: {json.dumps({k: v for k, v in asdict(qc).items() if k not in ('acpc_to_t1', 'thresholds')})}"
    )
    if not qc.passed:
        raise PreprocessError(
            "DTI QC gate failed (" + ", ".join(qc.failures) + f"); see {qc_path}. "
            "The tensor was not written. Check QSIPrep's report for this subject, and "
            "that charm ran on the same T1w QSIPrep used."
        )

    stored = tm.world_to_simnibs(tensors, t1.affine).astype(np.float32)
    stored[~mask] = 0
    _save_nifti_gz(stored, t1.affine, output_path)
    logger.info(f"DTI tensor saved to: {output_path}")

    from tit.reporting.generators.dti_qc import create_dti_qc_report

    report = create_dti_qc_report(
        project_dir=project_dir,
        subject_id=subject_id,
        tensor_file=str(output_path),
        t1_file=str(t1_path),
        qc=asdict(qc),
    )
    logger.info(f"DTI QC report: {report}")
    return output_path


def check_dti_tensor_exists(project_dir: str, subject_id: str) -> bool:
    """Whether ``DTI_coregT1_tensor.nii.gz`` exists in *subject_id*'s m2m folder."""
    m2m_dir = get_path_manager(project_dir).m2m(subject_id)
    return os.path.isdir(m2m_dir) and (Path(m2m_dir) / const.FILE_DTI_TENSOR).exists()
