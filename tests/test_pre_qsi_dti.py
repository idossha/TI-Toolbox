"""tit.pre.qsi.dti_extractor: input discovery, preconditions and the QC gate.

The numerical route (fit, chain, resampling, SimNIBS frame) runs against the real
libraries in tests/numerical/test_dti_roundtrip.py; this file covers what the host
suite can check with nibabel/scipy mocked. QC-gate values are the thresholds the
module states, not measurements.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.pre.qsi import dti_extractor as dx
from tit.pre.qsi.dti_extractor import (
    DtiQc,
    check_dti_tensor_exists,
    extract_dti_tensor,
    fit_tensor,
    qsiprep_inputs,
)
from tit.pre.utils import PreprocessError

MODULE = "tit.pre.qsi.dti_extractor"


def _qsiprep_tree(root: Path, sid: str = "001", *, drop: str | None = None) -> Path:
    sub = root / f"sub-{sid}"
    names = {
        "dwi": f"dwi/sub-{sid}_space-ACPC_desc-preproc_dwi.nii.gz",
        "grad": f"dwi/sub-{sid}_space-ACPC_desc-preproc_dwi.b",
        "dwi_mask": f"dwi/sub-{sid}_space-ACPC_desc-brain_mask.nii.gz",
        "xfm": f"anat/sub-{sid}_from-ACPC_to-anat_mode-image_xfm.mat",
        "acpc_t1": f"anat/sub-{sid}_space-ACPC_desc-preproc_T1w.nii.gz",
        "acpc_mask": f"anat/sub-{sid}_space-ACPC_desc-brain_mask.nii.gz",
    }
    for key, rel in names.items():
        if key == drop:
            continue
        (sub / rel).parent.mkdir(parents=True, exist_ok=True)
        (sub / rel).touch()
    return sub


class TestQsiprepInputs:
    def test_finds_every_file(self, tmp_path):
        sub = _qsiprep_tree(tmp_path)
        found = qsiprep_inputs(sub)
        assert found["grad"].name == "sub-001_space-ACPC_desc-preproc_dwi.b"
        assert found["dwi_mask"].parent.name == "dwi"
        assert found["acpc_mask"].parent.name == "anat"
        assert all(p.is_file() for p in found.values())

    @pytest.mark.parametrize("missing", ["grad", "dwi_mask"])
    def test_missing_sibling_raises(self, tmp_path, missing):
        with pytest.raises(PreprocessError, match=missing):
            qsiprep_inputs(_qsiprep_tree(tmp_path, drop=missing))

    @pytest.mark.parametrize("missing", ["dwi", "xfm", "acpc_t1"])
    def test_missing_primary_raises(self, tmp_path, missing):
        with pytest.raises(PreprocessError, match="Expected exactly one"):
            qsiprep_inputs(_qsiprep_tree(tmp_path, drop=missing))

    def test_two_dwi_series_rejected(self, tmp_path):
        sub = _qsiprep_tree(tmp_path)
        (sub / "dwi" / "sub-001_run-2_space-ACPC_desc-preproc_dwi.nii.gz").touch()
        with pytest.raises(PreprocessError, match="one DWI series"):
            qsiprep_inputs(sub)


def _passing_qc(**overrides) -> DtiQc:
    # CHN's measured record (dti_eval chn/DTI_coregT1_qc.json), then the override.
    values = dict(
        ncc_chain=0.984,
        chain_vs_ncc_mm=0.038,
        pct_pd=100.0,
        pct_wm_covered=98.9,
        pct_gm_covered=99.5,
        pct_wmgm_zero=0.81,
        wm_md_median=0.677e-3,
        wm_fa_median=0.323,
        n_out_of_brain=0,
    )
    values.update(overrides)
    qc = DtiQc(**values)
    qc.gate()
    return qc


class TestQcGate:
    def test_chn_record_passes(self):
        qc = _passing_qc()
        assert qc.passed and qc.failures == []

    @pytest.mark.parametrize(
        "field,value",
        [
            ("ncc_chain", dx.QC_MIN_NCC - 0.01),
            ("chain_vs_ncc_mm", dx.QC_MAX_CHAIN_VS_NCC_MM + 0.1),
            ("pct_pd", dx.QC_MIN_PD_PCT - 0.5),
            ("pct_wmgm_zero", dx.QC_MAX_WMGM_ZERO_PCT + 0.1),
            ("wm_md_median", dx.QC_WM_MD_RANGE[0] * 0.9),
            ("wm_md_median", dx.QC_WM_MD_RANGE[1] * 1.1),
            ("n_out_of_brain", 1),
        ],
    )
    def test_each_threshold_fails_alone(self, field, value):
        qc = _passing_qc(**{field: value})
        assert not qc.passed
        assert qc.failures == [field]

    def test_thresholds_recorded_for_the_report(self):
        assert _passing_qc().thresholds["min_ncc"] == dx.QC_MIN_NCC


class TestFitTensorPreconditions:
    def test_too_few_directions_below_bmax(self, tmp_path):
        grad = tmp_path / "x.b"
        rows = ["0 0 0 0"] + [f"1 0 0 {b}" for b in (1000,) * 5 + (3000,) * 30]
        grad.write_text("\n".join(rows) + "\n")
        with pytest.raises(PreprocessError, match="5 diffusion-weighted"):
            fit_tensor(tmp_path / "dwi.nii.gz", grad, tmp_path / "mask.nii.gz")

    def test_not_an_mrtrix_table(self, tmp_path):
        grad = tmp_path / "x.b"
        grad.write_text("0 0 0\n1 0 0\n")
        with pytest.raises(PreprocessError, match="MRtrix"):
            fit_tensor(tmp_path / "dwi.nii.gz", grad, tmp_path / "mask.nii.gz")


class TestCheckDtiTensorExists:
    @patch(f"{MODULE}.get_path_manager")
    def test_exists(self, mock_gpm, tmp_path):
        mock_gpm.return_value.m2m.return_value = str(tmp_path)
        (tmp_path / "DTI_coregT1_tensor.nii.gz").touch()
        assert check_dti_tensor_exists("/proj", "001") is True

    @patch(f"{MODULE}.get_path_manager")
    def test_not_exists(self, mock_gpm, tmp_path):
        mock_gpm.return_value.m2m.return_value = str(tmp_path)
        assert check_dti_tensor_exists("/proj", "001") is False

    @patch(f"{MODULE}.get_path_manager")
    def test_no_m2m_dir(self, mock_gpm, tmp_path):
        mock_gpm.return_value.m2m.return_value = str(tmp_path / "missing")
        assert check_dti_tensor_exists("/proj", "001") is False


@pytest.fixture
def project(tmp_path):
    """A project with an m2m folder (T1 + labels), raw T1w and a QSIPrep tree."""
    m2m = tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001"
    m2m.mkdir(parents=True)
    (m2m / "T1.nii.gz").touch()
    (m2m / "final_tissues.nii.gz").touch()
    anat = tmp_path / "sub-001" / "anat"
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii.gz").touch()
    _qsiprep_tree(tmp_path / "derivatives" / "qsiprep")
    return tmp_path, m2m


class TestExtractPreconditions:
    def test_no_m2m_t1(self, project):
        root, m2m = project
        (m2m / "T1.nii.gz").unlink()
        with pytest.raises(PreprocessError, match="Run charm first"):
            extract_dti_tensor(str(root), "001", logger=MagicMock())

    def test_existing_tensor(self, project):
        root, m2m = project
        (m2m / "DTI_coregT1_tensor.nii.gz").touch()
        with pytest.raises(PreprocessError, match="already exists"):
            extract_dti_tensor(str(root), "001", logger=MagicMock())

    def test_no_raw_t1w(self, project):
        root, _ = project
        (root / "sub-001" / "anat" / "sub-001_T1w.nii.gz").unlink()
        with pytest.raises(PreprocessError, match="sub-001_T1w not found"):
            extract_dti_tensor(str(root), "001", logger=MagicMock())

    def test_no_qsiprep_output(self, project):
        root, _ = project
        for path in (root / "derivatives" / "qsiprep").rglob("*_dwi.nii.gz"):
            path.unlink()
        with pytest.raises(PreprocessError, match="preprocessed DWI"):
            extract_dti_tensor(str(root), "001", logger=MagicMock())

    def test_m2m_t1_not_the_raw_t1w(self, project):
        root, _ = project

        def fake_load(path):
            img = MagicMock()
            img.shape = (176, 256, 256)
            img.affine = np.eye(4)
            if path.endswith("sub-001_T1w.nii.gz"):
                img.affine = np.diag([1.0, 1.0, 1.0, 1.0])
                img.affine[0, 3] = 5.0  # charm ran on a different T1w
            return img

        with patch("nibabel.load", side_effect=fake_load):
            with pytest.raises(PreprocessError, match="same T1w"):
                extract_dti_tensor(str(root), "001", logger=MagicMock())
