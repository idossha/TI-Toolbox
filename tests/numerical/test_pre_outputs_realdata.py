"""Dataset 000's pre-processing outputs are complete and agree with each other (read-only).

Gated on ``TIT_DATASET_000`` (a Dataset 000 copy; mount it ``:ro`` in the image). Nothing
is written: every file the sweep reads is listed with its mtime before and after.

1. Every ``m2m_<id>`` holds ``<id>.msh``, ``T1.nii.gz`` and ``final_tissues.nii.gz`` on the
   T1 grid, and the preflight calls it complete. For sub-CHN the m2m T1 grid is the BIDS
   T1w grid: the precondition of the DTI transform chain.
2. FastSurfer sub-ernie: the ``.nii.gz`` copy is voxel-identical to the ``.mgz`` (integer,
   same affine); the labels sidecar lists exactly ``np.unique(seg) - {0}`` with the counted
   voxels and FreeSurferColorLUT names. sub-101's interrupted run (no segmentation) is
   reported incomplete, missing exactly the segmentation.
3. sub-CHN DTI: the tensor is on the T1 grid and zero outside charm's brain labels; the WM
   MD median recomputed from it matches ``DTI_coregT1_qc.json``; ``passed`` and
   ``failures`` follow from the recorded values and thresholds.
4. sub-CHN distortion correction, derived by hand from the sidecars (DWI PE ``j-``;
   ``acq-dwi_dir-AP_epi.json`` PE ``j``; ``acq-dwi_dir-PA_epi`` has no JSON; the
   ``acq-bold`` pair is for the BOLD run): TOPUP with the AP fieldmap, the PA one reported.

    TIT_DATASET_000=/path/to/000 .venv/bin/python -m pytest \\
        tests/numerical/test_pre_outputs_realdata.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pytest

_DATASET = os.environ.get("TIT_DATASET_000", "")
ROOT = Path(_DATASET)
SIMNIBS = ROOT / "derivatives" / "SimNIBS"
FASTSURFER = ROOT / "derivatives" / "fastsurfer"
SEG = "aparc.DKTatlas+aseg.deep"

pytestmark = [
    pytest.mark.host_numerical,
    pytest.mark.skipif(
        not (_DATASET and SIMNIBS.is_dir()),
        reason="skipping: set TIT_DATASET_000 to a Dataset 000 copy (read-only)",
    ),
]


def _m2m_dirs() -> dict[str, Path]:
    return {
        p.name[len("sub-") :]: p / f"m2m_{p.name[len('sub-'):]}"
        for p in sorted(SIMNIBS.glob("sub-*"))
        if (p / f"m2m_{p.name[len('sub-'):]}").is_dir()
    }


def _listing() -> dict[str, int]:
    """mtime of every file the sweep reads, plus the trees it walks."""
    paths = [ROOT, *ROOT.iterdir(), *(ROOT / "sub-CHN").rglob("*")]
    if FASTSURFER.is_dir():
        paths += [FASTSURFER, *FASTSURFER.rglob("*")]
    for m2m in _m2m_dirs().values():
        paths += [m2m, *m2m.iterdir()]
    return {str(p): p.stat().st_mtime_ns for p in paths}


@pytest.fixture(scope="module", autouse=True)
def project():
    from tit.paths import get_path_manager, reset_path_manager

    before = _listing()
    reset_path_manager()
    get_path_manager(str(ROOT))
    yield str(ROOT)
    reset_path_manager()
    assert _listing() == before, "the read-only sweep changed Dataset 000"


def _grid(path: Path):
    import nibabel as nib

    img = nib.load(str(path))
    return img.shape[:3], img.affine


def _same_grid(a, b) -> bool:
    return a[0] == b[0] and np.allclose(a[1], b[1], atol=1e-3)


# -- 1. head models -----------------------------------------------------------------------


def test_every_head_model_is_complete_and_on_its_t1_grid(project):
    from tit.pre.preflight import STEP_CHARM, step_output_complete

    m2m_dirs = _m2m_dirs()
    assert {"101", "CHN", "ernie"} <= set(m2m_dirs)
    for sid, m2m in m2m_dirs.items():
        for name in (f"{sid}.msh", "T1.nii.gz", "final_tissues.nii.gz"):
            assert (m2m / name).is_file(), (sid, name)
        assert _same_grid(
            _grid(m2m / "final_tissues.nii.gz"), _grid(m2m / "T1.nii.gz")
        ), sid
        assert step_output_complete(project, sid, STEP_CHARM) is True, sid


def test_chn_head_model_kept_the_bids_t1w_grid(project):
    m2m_t1 = _grid(SIMNIBS / "sub-CHN" / "m2m_CHN" / "T1.nii.gz")
    bids_t1 = _grid(ROOT / "sub-CHN" / "anat" / "sub-CHN_T1w.nii.gz")
    assert _same_grid(m2m_t1, bids_t1)


# -- 2. FastSurfer ------------------------------------------------------------------------


def _freesurfer_lut() -> dict[int, str]:
    """``resources/atlas/FreeSurferColorLUT.txt``: id, name, R, G, B, A per line."""
    from tit.atlas.constants import MNI_ATLAS_DIR

    names = {}
    for line in Path(MNI_ATLAS_DIR, "FreeSurferColorLUT.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) == 6 and parts[0].isdigit():
            names[int(parts[0])] = parts[1]
    return names


def test_ernie_fastsurfer_copy_and_sidecar_agree_with_the_segmentation(project):
    import nibabel as nib

    from tit.pre.preflight import STEP_FASTSURFER, step_output_complete

    mri = FASTSURFER / "sub-ernie" / "mri"
    if not (mri / f"{SEG}.mgz").is_file():
        pytest.skip(
            "skipping: Dataset 000 has no FastSurfer segmentation for sub-ernie"
        )
    mgz = nib.load(str(mri / f"{SEG}.mgz"))
    nii = nib.load(str(mri / f"{SEG}.nii.gz"))
    seg = np.asarray(mgz.dataobj)
    copy = np.asarray(nii.dataobj)

    assert np.issubdtype(nii.get_data_dtype(), np.integer)
    np.testing.assert_array_equal(copy, seg)
    np.testing.assert_allclose(nii.affine, mgz.affine, atol=1e-4)

    values, counts = np.unique(seg, return_counts=True)
    expected = {int(v): int(c) for v, c in zip(values, counts) if v != 0}
    lut = _freesurfer_lut()
    rows = {}
    for line in (mri / f"{SEG}_labels.txt").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        _index, seg_id, n_voxels, volume, *name = line.split()
        rows[int(seg_id)] = (int(n_voxels), float(volume), " ".join(name))
    assert set(rows) == set(expected)
    voxel_mm3 = float(np.prod(mgz.header.get_zooms()[:3]))
    for label, count in expected.items():
        n_voxels, volume, name = rows[label]
        assert n_voxels == count, label
        assert volume == pytest.approx(count * voxel_mm3, rel=1e-6), label
        assert name == lut[label], label
    assert step_output_complete(project, "ernie", STEP_FASTSURFER) is True


def test_sub101_interrupted_fastsurfer_is_incomplete_for_want_of_its_segmentation(
    project,
):
    from tit.pre.preflight import (
        STEP_FASTSURFER,
        existing_outputs_for_step,
        step_output_complete,
    )

    subject = FASTSURFER / "sub-101"
    if not subject.is_dir() or (subject / "mri" / f"{SEG}.mgz").exists():
        pytest.skip(
            "skipping: Dataset 000 sub-101 FastSurfer is not the interrupted run"
        )
    outputs = existing_outputs_for_step(project, "101", STEP_FASTSURFER)

    assert [(o.path, o.missing) for o in outputs] == [(subject, (f"mri/{SEG}.mgz",))]
    assert step_output_complete(project, "101", STEP_FASTSURFER) is False


# -- 3. DTI on sub-CHN --------------------------------------------------------------------


def test_chn_tensor_matches_its_qc_record(project):
    import nibabel as nib

    m2m = SIMNIBS / "sub-CHN" / "m2m_CHN"
    tensor_path = m2m / "DTI_coregT1_tensor.nii.gz"
    if not tensor_path.is_file():
        pytest.skip("skipping: Dataset 000 sub-CHN has no DTI tensor")
    qc = json.loads((m2m / "DTI_coregT1_qc.json").read_text())

    tensor_img = nib.load(str(tensor_path))
    assert _same_grid(_grid(tensor_path), _grid(m2m / "T1.nii.gz"))
    assert tensor_img.shape[3:] == (6,)
    labels = np.asarray(nib.load(str(m2m / "final_tissues.nii.gz")).dataobj)
    labels = labels[..., 0] if labels.ndim == 4 else labels
    tensor = np.asarray(tensor_img.dataobj, dtype=np.float32)

    nonzero = np.any(tensor != 0, axis=-1)
    # charm labels 1 WM, 2 GM, 3 CSF: the only tissue the tensor may cover.
    assert not (nonzero & ~np.isin(labels, (1, 2, 3))).any()
    assert qc["n_out_of_brain"] == 0
    # FSL order xx, xy, xz, yy, yz, zz; the stored frame is a rotation of the world one,
    # so the trace (3 x MD) is the world tensor's.
    md = (tensor[..., 0] + tensor[..., 3] + tensor[..., 5]) / 3
    wm_md = float(np.median(md[nonzero & (labels == 1)]))
    assert wm_md == pytest.approx(qc["wm_md_median"], rel=0.01)
    assert 0.5e-3 < wm_md < 1.1e-3  # adult in-vivo WM, mm^2/s

    t = qc["thresholds"]
    failing = {
        "ncc_chain": qc["ncc_chain"] < t["min_ncc"],
        "chain_vs_ncc_mm": qc["chain_vs_ncc_mm"] > t["max_chain_vs_ncc_mm"],
        "pct_pd": qc["pct_pd"] < t["min_pct_pd"],
        "pct_wmgm_zero": qc["pct_wmgm_zero"] > t["max_pct_wmgm_zero"],
        "wm_md_median": not (
            t["wm_md_range"][0] <= qc["wm_md_median"] <= t["wm_md_range"][1]
        ),
        "n_out_of_brain": qc["n_out_of_brain"] > t["max_out_of_brain"],
    }
    assert sorted(qc["failures"]) == sorted(k for k, bad in failing.items() if bad)
    assert qc["passed"] is (qc["failures"] == [])


# -- 4. distortion correction on sub-CHN --------------------------------------------------


def test_chn_distortion_correction_uses_the_ap_fieldmap_and_names_the_pa_one(project):
    from tit.pre.preflight import find_missing_preprocessing_inputs
    from tit.pre.qsi.utils import plan_distortion_correction, validate_bids_dwi

    fmap = ROOT / "sub-CHN" / "fmap"
    if (
        not (fmap / "sub-CHN_acq-dwi_dir-PA_epi.nii.gz").is_file()
        or (fmap / "sub-CHN_acq-dwi_dir-PA_epi.json").exists()
    ):
        pytest.skip("skipping: Dataset 000 sub-CHN fieldmaps are not the audited set")
    logger = logging.getLogger("sdc-realdata")

    assert validate_bids_dwi(project, "CHN", logger) == (True, None)
    plan = plan_distortion_correction(project, "CHN", logger=logger, repair=False)

    assert plan.mode == "fieldmap"
    assert plan.fieldmaps == (fmap / "sub-CHN_acq-dwi_dir-AP_epi.nii.gz",)
    assert len(plan.problems) == 1
    assert "sub-CHN_acq-dwi_dir-PA_epi" in plan.problems[0]
    assert "sidecar" in plan.problems[0]
    assert plan.blocking_error is None
    assert find_missing_preprocessing_inputs(project, ["CHN"], run_qsiprep=True) == []
