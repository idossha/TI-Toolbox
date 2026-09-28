"""CHN end to end: QSIPrep output -> DTI_coregT1_tensor + QC JSON, on a scratch project.

Gated on ``TIT_DTI_REAL`` (a Dataset-000-shaped root holding ``sub-CHN/anat``,
``derivatives/qsiprep/sub-CHN`` and ``derivatives/SimNIBS/sub-CHN/m2m_CHN``). The
dataset is only read: a scratch project in ``tmp_path`` symlinks those inputs and
receives every output. Optional ``TIT_DTI_PROTO`` points at the prototype's CHN
tensor (dti_eval chn/proposed_DTI_coregT1_tensor.nii.gz, produced by
proto/proposed_dti_extractor.py on 2026-09-27) to compare V1 against.

Why the synthetic sibling (test_dti_roundtrip.py) is not enough: it cannot show that
QSIPrep's real ``.b`` table is world-frame, that QSIPrep's real deoblique/ACPC files
compose as modelled, or that the QC thresholds pass on an in-vivo brain.

    export TIT_DTI_REAL=/data000 TIT_DTI_PROTO=/eval/chn/proposed_DTI_coregT1_tensor.nii.gz
    simnibs_python -m pytest tests/numerical/test_dti_real.py -s
"""

import json
import logging
import os
from pathlib import Path

import numpy as np
import pytest

ROOT = os.environ.get("TIT_DTI_REAL")
PROTO = os.environ.get("TIT_DTI_PROTO")
SID = "CHN"

pytestmark = pytest.mark.skipif(
    not ROOT, reason="skipping: TIT_DTI_REAL (Dataset 000 root with sub-CHN) is unset"
)


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src)


@pytest.fixture(scope="module")
def chn_run(tmp_path_factory):
    pytest.importorskip("dipy", reason="skipping: dipy is not installed here")
    from tit.paths import get_path_manager, reset_path_manager
    from tit.pre.qsi.dti_extractor import extract_dti_tensor

    root = Path(ROOT)
    scratch = tmp_path_factory.mktemp("chn_project")
    raw_t1 = root / f"sub-{SID}" / "anat" / f"sub-{SID}_T1w.nii.gz"
    _link(raw_t1, scratch / f"sub-{SID}" / "anat" / raw_t1.name)
    _link(
        root / "derivatives" / "qsiprep" / f"sub-{SID}",
        scratch / "derivatives" / "qsiprep" / f"sub-{SID}",
    )
    m2m_src = root / "derivatives" / "SimNIBS" / f"sub-{SID}" / f"m2m_{SID}"
    m2m = scratch / "derivatives" / "SimNIBS" / f"sub-{SID}" / f"m2m_{SID}"
    for name in ("T1.nii.gz", "final_tissues.nii.gz"):
        _link(m2m_src / name, m2m / name)

    reset_path_manager()
    get_path_manager(str(scratch))
    try:
        out = extract_dti_tensor(
            str(scratch), SID, logger=logging.getLogger("dti-real")
        )
    finally:
        reset_path_manager()
    qc = json.loads((m2m / "DTI_coregT1_qc.json").read_text())
    print("\nCHN QC:", json.dumps(qc, indent=1))
    return out, m2m, qc


def test_qc_gate_passes(chn_run):
    out, _, qc = chn_run
    assert qc["passed"], qc["failures"]
    assert out.is_file()
    assert qc["n_out_of_brain"] == 0


def test_v1_matches_prototype(chn_run):
    if not PROTO:
        pytest.skip("skipping: TIT_DTI_PROTO (prototype CHN tensor) is unset")
    import nibabel as nib

    from tit.pre.qsi import tensor_math as tm

    out, m2m, _ = chn_run
    ours_img = nib.load(str(out))
    theirs_img = nib.load(PROTO)
    assert np.allclose(ours_img.affine, theirs_img.affine)
    ours = np.asanyarray(ours_img.dataobj, dtype=np.float64)
    theirs = np.asanyarray(theirs_img.dataobj, dtype=np.float64)
    labels = np.asanyarray(nib.load(str(m2m / "final_tissues.nii.gz")).dataobj)
    labels = labels[..., 0] if labels.ndim == 4 else labels
    both = np.any(ours != 0, -1) & np.any(theirs != 0, -1) & (labels == 1)
    wo = tm.simnibs_to_world(ours[both], ours_img.affine)
    wt = tm.simnibs_to_world(theirs[both], theirs_img.affine)
    val, vo = tm.eig_desc(wo)
    _, vt = tm.eig_desc(wt)
    fa, _ = tm.fa_md(val)
    keep = fa > 0.3
    cos = np.abs(np.einsum("ni,ni->n", vo[keep, :, 0], vt[keep, :, 0]))
    angle = np.degrees(np.arccos(np.clip(cos, 0, 1)))
    print(
        f"\nV1 vs prototype, WM FA>0.3: n={keep.sum()} median {np.median(angle):.3f} "
        f"p95 {np.percentile(angle, 95):.3f} deg"
    )
    # Same inputs and method as the prototype; only float order differs.
    assert np.median(angle) < 0.5
    assert np.percentile(angle, 95) < 3.0
