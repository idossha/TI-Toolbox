"""Tests for tit.pre.qsi.dti_extractor — DTI tensor extraction."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.pre.utils import PreprocessError
from tit.pre.qsi.dti_extractor import (
    _TENSOR_PARAMS,
    _dsistudio_dwi_dir,
    _qsiprep_t1,
    _load_dsistudio_tensor,
    _validate_tensor,
    check_dti_tensor_exists,
    extract_dti_tensor,
)

MODULE = "tit.pre.qsi.dti_extractor"


# ============================================================================
# Path resolution
# ============================================================================


class TestDsistudioDwiDir:
    def test_returns_known_path(self, tmp_path):
        result = _dsistudio_dwi_dir(tmp_path, "001")
        expected = (
            tmp_path
            / "derivatives"
            / "qsirecon"
            / "derivatives"
            / "qsirecon-DSIStudio"
            / "sub-001"
            / "dwi"
        )
        assert result == expected


class TestQsiprepT1:
    def test_returns_known_path(self, tmp_path):
        result = _qsiprep_t1(tmp_path, "001")
        expected = (
            tmp_path
            / "derivatives"
            / "qsiprep"
            / "sub-001"
            / "anat"
            / "sub-001_space-ACPC_desc-preproc_T1w.nii.gz"
        )
        assert result == expected


# ============================================================================
# Tensor loading
# ============================================================================


class TestLoadDsistudioTensor:
    def _create_components(self, dwi_dir, subject_id="001"):
        """Create dummy tensor component files."""
        dwi_dir.mkdir(parents=True, exist_ok=True)
        for param in _TENSOR_PARAMS:
            (
                dwi_dir
                / f"sub-{subject_id}_space-ACPC_model-tensor_param-{param}_dwimap.nii.gz"
            ).touch()

    @patch("nibabel.load")
    def test_loads_all_six(self, mock_load, tmp_path):
        dwi_dir = tmp_path / "dwi"
        self._create_components(dwi_dir)

        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.ones((5, 5, 5), dtype=np.float32)
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        mock_load.return_value = mock_img

        data, affine, header = _load_dsistudio_tensor(dwi_dir, "001", MagicMock())
        assert data.shape == (5, 5, 5, 6)
        assert mock_load.call_count == 6

    @patch("nibabel.load")
    def test_handles_4d_components(self, mock_load, tmp_path):
        dwi_dir = tmp_path / "dwi"
        self._create_components(dwi_dir)

        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.ones((5, 5, 5, 1), dtype=np.float32)
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        mock_load.return_value = mock_img

        data, _, _ = _load_dsistudio_tensor(dwi_dir, "001", MagicMock())
        assert data.shape == (5, 5, 5, 6)

    def test_missing_component_raises(self, tmp_path):
        dwi_dir = tmp_path / "dwi"
        dwi_dir.mkdir(parents=True)
        # Create only 5 of 6 components
        for param in _TENSOR_PARAMS[:5]:
            (
                dwi_dir / f"sub-001_space-ACPC_model-tensor_param-{param}_dwimap.nii.gz"
            ).touch()

        with pytest.raises(PreprocessError, match="Missing tensor component"):
            _load_dsistudio_tensor(dwi_dir, "001", MagicMock())

    def test_empty_dir_raises(self, tmp_path):
        dwi_dir = tmp_path / "dwi"
        dwi_dir.mkdir(parents=True)

        with pytest.raises(PreprocessError, match="Missing tensor component"):
            _load_dsistudio_tensor(dwi_dir, "001", MagicMock())


# ============================================================================
# Validation
# ============================================================================


class TestValidateTensor:
    def test_valid_tensor(self):
        data = np.ones((5, 5, 5, 6), dtype=np.float32)
        _validate_tensor(data, MagicMock())

    def test_invalid_shape_raises(self):
        data = np.ones((5, 5, 5, 3), dtype=np.float32)
        with pytest.raises(PreprocessError, match="Invalid tensor shape"):
            _validate_tensor(data, MagicMock())

    def test_nan_replaced(self):
        data = np.ones((5, 5, 5, 6), dtype=np.float32)
        data[0, 0, 0, 0] = np.nan
        logger = MagicMock()
        _validate_tensor(data, logger)
        logger.warning.assert_called()
        assert data[0, 0, 0, 0] == 0.0

    def test_inf_replaced(self):
        data = np.ones((5, 5, 5, 6), dtype=np.float32)
        data[0, 0, 0, 0] = np.inf
        _validate_tensor(data, MagicMock())
        assert data[0, 0, 0, 0] == 0.0

    def test_all_zeros_raises(self):
        data = np.zeros((5, 5, 5, 6), dtype=np.float32)
        with pytest.raises(PreprocessError, match="entirely zero"):
            _validate_tensor(data, MagicMock())

    def test_low_coverage_warns(self):
        data = np.zeros((10, 10, 10, 6), dtype=np.float32)
        data[0, 0, 0, :] = 1.0
        logger = MagicMock()
        _validate_tensor(data, logger)
        logger.warning.assert_called()


# ============================================================================
# Registration
# ============================================================================


class TestRegisterTensor:
    @patch(f"{MODULE}.subprocess.run")
    def test_ants_registration_succeeds(self, mock_run, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_tensor

        mock_run.return_value = MagicMock(returncode=0)

        _register_tensor(
            tmp_path / "tensor.nii.gz",
            tmp_path / "moving_t1.nii.gz",
            tmp_path / "fixed_t1.nii.gz",
            tmp_path / "output.nii.gz",
            MagicMock(),
        )
        assert mock_run.call_count == 2

    @patch(f"{MODULE}.subprocess.run")
    def test_ants_registration_fails(self, mock_run, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_tensor

        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        with pytest.raises(PreprocessError, match="ANTs registration failed"):
            _register_tensor(
                tmp_path / "tensor.nii.gz",
                tmp_path / "moving_t1.nii.gz",
                tmp_path / "fixed_t1.nii.gz",
                tmp_path / "output.nii.gz",
                MagicMock(),
            )

    @patch(f"{MODULE}.subprocess.run")
    def test_apply_transform_fails(self, mock_run, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_tensor

        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="apply error"),
        ]

        with pytest.raises(PreprocessError, match="tensor transform failed"):
            _register_tensor(
                tmp_path / "tensor.nii.gz",
                tmp_path / "moving_t1.nii.gz",
                tmp_path / "fixed_t1.nii.gz",
                tmp_path / "output.nii.gz",
                MagicMock(),
            )


# ============================================================================
# check_dti_tensor_exists
# ============================================================================


class TestCheckDtiTensorExists:
    @patch(f"{MODULE}.get_path_manager")
    def test_exists(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        (m2m / "DTI_coregT1_tensor.nii.gz").touch()
        assert check_dti_tensor_exists("/proj", "001") is True

    @patch(f"{MODULE}.get_path_manager")
    def test_not_exists(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        assert check_dti_tensor_exists("/proj", "001") is False

    @patch(f"{MODULE}.get_path_manager")
    def test_no_m2m_dir(self, mock_gpm, tmp_path):
        pm = MagicMock()
        pm.m2m.return_value = str(tmp_path / "nonexistent")
        mock_gpm.return_value = pm

        assert check_dti_tensor_exists("/proj", "001") is False


# ============================================================================
# extract_dti_tensor (integration-level)
# ============================================================================


class TestExtractDtiTensor:
    @patch(f"{MODULE}.get_path_manager")
    def test_no_m2m_raises(self, mock_gpm, tmp_path):
        pm = MagicMock()
        pm.m2m.return_value = str(tmp_path / "nonexistent")
        mock_gpm.return_value = pm

        with pytest.raises(PreprocessError, match="m2m directory not found"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    def test_existing_tensor_raises(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        (m2m / "DTI_coregT1_tensor.nii.gz").touch()
        (m2m / "T1.nii.gz").touch()

        with pytest.raises(PreprocessError, match="already exists"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    def test_no_simnibs_t1_raises(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        with pytest.raises(PreprocessError, match="SimNIBS T1 not found"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    def test_no_dsistudio_dir_raises(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        (m2m / "T1.nii.gz").touch()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        with pytest.raises(PreprocessError, match="DSI Studio output not found"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._load_dsistudio_tensor")
    @patch("nibabel.save")
    @patch(f"{MODULE}.get_path_manager")
    def test_no_qsiprep_t1_raises(
        self, mock_gpm, mock_save, mock_load, mock_validate, tmp_path
    ):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        (m2m / "T1.nii.gz").touch()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        # Create DSI Studio dir but no QSIPrep T1
        dwi_dir = _dsistudio_dwi_dir(tmp_path, "001")
        dwi_dir.mkdir(parents=True)

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_load.return_value = (tensor, np.eye(4), MagicMock())

        with pytest.raises(PreprocessError, match="QSIPrep T1 not found"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

    @patch("tit.reporting.generators.dti_qc.create_dti_qc_report", return_value=Path("/fake"))
    @patch(f"{MODULE}.shutil.copy2")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._load_dsistudio_tensor")
    @patch("nibabel.save")
    @patch(f"{MODULE}.get_path_manager")
    def test_skip_registration(
        self, mock_gpm, mock_save, mock_load, mock_validate, mock_copy, mock_qc, tmp_path
    ):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        (m2m / "T1.nii.gz").touch()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        dwi_dir = _dsistudio_dwi_dir(tmp_path, "001")
        dwi_dir.mkdir(parents=True)

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_load.return_value = (tensor, np.eye(4), MagicMock())

        result = extract_dti_tensor(
            str(tmp_path), "001", logger=MagicMock(), skip_registration=True
        )
        assert result is not None
        mock_copy.assert_called_once()

    @patch("tit.reporting.generators.dti_qc.create_dti_qc_report", return_value=Path("/fake"))
    @patch(f"{MODULE}._register_tensor")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._load_dsistudio_tensor")
    @patch("nibabel.save")
    @patch(f"{MODULE}.get_path_manager")
    def test_with_registration(
        self, mock_gpm, mock_save, mock_load, mock_validate, mock_register, mock_qc, tmp_path
    ):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        (m2m / "T1.nii.gz").touch()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        dwi_dir = _dsistudio_dwi_dir(tmp_path, "001")
        dwi_dir.mkdir(parents=True)

        # Create QSIPrep T1
        qsiprep_t1 = _qsiprep_t1(tmp_path, "001")
        qsiprep_t1.parent.mkdir(parents=True)
        qsiprep_t1.touch()

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_load.return_value = (tensor, np.eye(4), MagicMock())

        extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

        mock_register.assert_called_once()
