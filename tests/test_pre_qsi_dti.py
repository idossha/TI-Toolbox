"""Tests for tit.pre.qsi.dti_extractor — DTI tensor extraction."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.pre.utils import PreprocessError
from tit.pre.qsi.dti_extractor import (
    _TENSOR_PARAMS,
    _dsistudio_dwi_dir,
    _load_tensor,
    _validate_tensor,
    check_dti_tensor_exists,
    extract_dti_tensor,
)

MODULE = "tit.pre.qsi.dti_extractor"


# ── Path resolution ──────────────────────────────────────────────────────


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


# ── Tensor loading ───────────────────────────────────────────────────────


class TestLoadTensor:
    def _create_components(self, dwi_dir, subject_id="001"):
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
        mock_load.return_value = mock_img

        data, affine = _load_tensor(dwi_dir, "001", MagicMock())
        assert data.shape == (5, 5, 5, 6)
        assert mock_load.call_count == 6

    @patch("nibabel.load")
    def test_handles_4d_components(self, mock_load, tmp_path):
        dwi_dir = tmp_path / "dwi"
        self._create_components(dwi_dir)

        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.ones((5, 5, 5, 1), dtype=np.float32)
        mock_img.affine = np.eye(4)
        mock_load.return_value = mock_img

        data, _ = _load_tensor(dwi_dir, "001", MagicMock())
        assert data.shape == (5, 5, 5, 6)

    def test_missing_component_raises(self, tmp_path):
        dwi_dir = tmp_path / "dwi"
        dwi_dir.mkdir(parents=True)
        for param in _TENSOR_PARAMS[:5]:
            (
                dwi_dir / f"sub-001_space-ACPC_model-tensor_param-{param}_dwimap.nii.gz"
            ).touch()

        with pytest.raises(PreprocessError, match="Missing tensor component"):
            _load_tensor(dwi_dir, "001", MagicMock())

    def test_empty_dir_raises(self, tmp_path):
        dwi_dir = tmp_path / "dwi"
        dwi_dir.mkdir(parents=True)

        with pytest.raises(PreprocessError, match="Missing tensor component"):
            _load_tensor(dwi_dir, "001", MagicMock())


# ── Validation ───────────────────────────────────────────────────────────


class TestValidateTensor:
    def test_valid_tensor(self):
        _validate_tensor(np.ones((5, 5, 5, 6), dtype=np.float32), MagicMock())

    def test_invalid_shape_raises(self):
        with pytest.raises(PreprocessError, match="Invalid tensor shape"):
            _validate_tensor(np.ones((5, 5, 5, 3), dtype=np.float32), MagicMock())

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
        with pytest.raises(PreprocessError, match="entirely zero"):
            _validate_tensor(np.zeros((5, 5, 5, 6), dtype=np.float32), MagicMock())

    def test_low_coverage_warns(self):
        data = np.zeros((10, 10, 10, 6), dtype=np.float32)
        data[0, 0, 0, :] = 1.0
        logger = MagicMock()
        _validate_tensor(data, logger)
        logger.warning.assert_called()


# ── Orientation ──────────────────────────────────────────────────────────


class TestRotationFromAffine:
    def test_identity(self):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        np.testing.assert_allclose(_rotation_from_affine(np.eye(4)), np.eye(3))

    def test_scaled_affine(self):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        np.testing.assert_allclose(
            _rotation_from_affine(np.diag([2.0, 2.0, 2.0, 1.0])), np.eye(3)
        )

    def test_lps_orientation(self):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        np.testing.assert_allclose(
            _rotation_from_affine(np.diag([-2.0, -2.0, 2.0, 1.0])),
            np.diag([-1.0, -1.0, 1.0]),
        )


class TestFSLConventionRoundtrip:
    """Prove: correct_FSL(R_fix @ T @ R_fix^T) = R_src @ T @ R_src^T."""

    @staticmethod
    def _simulate_correct_fsl(tensor_6, affine):
        """Replicate SimNIBS cond_utils.py:194-201."""
        M = affine[:3, :3] / np.linalg.norm(affine[:3, :3], axis=0)[:, None]
        R = np.eye(3)
        if np.linalg.det(M) > 0:
            R[0, 0] = -1
        M = M.dot(R)
        T = np.array(
            [
                [tensor_6[0], tensor_6[1], tensor_6[2]],
                [tensor_6[1], tensor_6[3], tensor_6[4]],
                [tensor_6[2], tensor_6[4], tensor_6[5]],
            ]
        )
        return M @ T @ M.T

    @staticmethod
    def _apply_rotation(tensor_6, R):
        T = np.array(
            [
                [tensor_6[0], tensor_6[1], tensor_6[2]],
                [tensor_6[1], tensor_6[3], tensor_6[4]],
                [tensor_6[2], tensor_6[4], tensor_6[5]],
            ]
        )
        Tr = R @ T @ R.T
        return np.array([Tr[0, 0], Tr[0, 1], Tr[0, 2], Tr[1, 1], Tr[1, 2], Tr[2, 2]])

    @staticmethod
    def _compute_r_fix(src_affine, tgt_affine):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        R_src = _rotation_from_affine(src_affine)
        R_tgt = _rotation_from_affine(tgt_affine)
        M_fsl = R_tgt.copy()
        if np.linalg.det(R_tgt) > 0:
            M_fsl[:, 0] *= -1
        return M_fsl.T @ R_src

    def _assert_roundtrip(self, tensor_6, src_affine, tgt_affine):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        R_fix = self._compute_r_fix(src_affine, tgt_affine)
        stored = self._apply_rotation(tensor_6, R_fix)
        world = self._simulate_correct_fsl(stored, tgt_affine)

        R_src = _rotation_from_affine(src_affine)
        gold = self._apply_rotation(tensor_6, R_src)
        gold_3x3 = np.array(
            [
                [gold[0], gold[1], gold[2]],
                [gold[1], gold[3], gold[4]],
                [gold[2], gold[4], gold[5]],
            ]
        )
        np.testing.assert_allclose(world, gold_3x3, atol=1e-6)

    def test_lps_to_ras(self):
        """LPS source -> RAS target with off-diagonal tensor."""
        self._assert_roundtrip(
            np.array([1.0, 0.5, 0.1, 0.8, 0.05, 0.2]),
            np.diag([-2.0, -2.0, 2.0, 1.0]),
            np.diag([1.0, 1.0, 1.0, 1.0]),
        )

    def test_ras_to_ras(self):
        self._assert_roundtrip(
            np.array([1.0, 0.5, 0.1, 0.8, 0.05, 0.2]),
            np.diag([1.0, 1.0, 1.0, 1.0]),
            np.diag([1.0, 1.0, 1.0, 1.0]),
        )

    def test_las_source(self):
        """LAS source (det < 0) -> RAS target."""
        self._assert_roundtrip(
            np.array([1.0, 0.5, 0.1, 0.8, 0.05, 0.2]),
            np.diag([-1.0, 1.0, 1.0, 1.0]),
            np.diag([1.0, 1.0, 1.0, 1.0]),
        )

    def test_lps_to_lps(self):
        """Same orientation, different scale."""
        self._assert_roundtrip(
            np.array([1.0, 0.5, 0.1, 0.8, 0.05, 0.2]),
            np.diag([-2.0, -2.0, 2.0, 1.0]),
            np.diag([-1.0, -1.0, 1.0, 1.0]),
        )


# ── check_dti_tensor_exists ─────────────────────────────────────────────


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


# ── extract_dti_tensor (integration) ─────────────────────────────────────


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

    @patch(
        "tit.reporting.generators.dti_qc.create_dti_qc_report",
        return_value=Path("/fake"),
    )
    @patch(f"{MODULE}.shutil.copy2")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._load_tensor")
    @patch(f"{MODULE}._save_nifti_gz")
    @patch(f"{MODULE}.get_path_manager")
    def test_skip_registration(
        self,
        mock_gpm,
        mock_save,
        mock_load,
        mock_validate,
        mock_copy,
        mock_qc,
        tmp_path,
    ):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        (m2m / "T1.nii.gz").touch()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        dwi_dir = _dsistudio_dwi_dir(tmp_path, "001")
        dwi_dir.mkdir(parents=True)

        mock_load.return_value = (np.ones((5, 5, 5, 6), dtype=np.float32), np.eye(4))
        result = extract_dti_tensor(
            str(tmp_path), "001", logger=MagicMock(), skip_registration=True
        )
        assert result is not None
        mock_copy.assert_called_once()

    @patch(
        "tit.reporting.generators.dti_qc.create_dti_qc_report",
        return_value=Path("/fake"),
    )
    @patch(f"{MODULE}._register_tensor")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._load_tensor")
    @patch(f"{MODULE}._save_nifti_gz")
    @patch(f"{MODULE}.get_path_manager")
    def test_with_registration(
        self,
        mock_gpm,
        mock_save,
        mock_load,
        mock_validate,
        mock_register,
        mock_qc,
        tmp_path,
    ):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        (m2m / "T1.nii.gz").touch()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        dwi_dir = _dsistudio_dwi_dir(tmp_path, "001")
        dwi_dir.mkdir(parents=True)

        mock_load.return_value = (np.ones((5, 5, 5, 6), dtype=np.float32), np.eye(4))
        extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())
        mock_register.assert_called_once()
