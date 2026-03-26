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


class TestRotationFromAffine:
    def test_identity(self):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        R = _rotation_from_affine(np.eye(4))
        np.testing.assert_allclose(R, np.eye(3))

    def test_scaled_affine(self):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        affine = np.diag([2.0, 2.0, 2.0, 1.0])
        R = _rotation_from_affine(affine)
        np.testing.assert_allclose(R, np.eye(3))

    def test_lps_orientation(self):
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        # LPS affine: negative x, negative y, positive z
        affine = np.diag([-2.0, -2.0, 2.0, 1.0])
        R = _rotation_from_affine(affine)
        expected = np.diag([-1.0, -1.0, 1.0])
        np.testing.assert_allclose(R, expected)


class TestFSLConventionRoundtrip:
    """Prove: correct_FSL(R_fix @ T @ R_fix^T) = R_src @ T @ R_src^T = T_world."""

    def _simulate_correct_fsl(self, tensor_6, affine):
        """Replicate SimNIBS cond_utils.py:194-201."""
        M = affine[:3, :3] / np.linalg.norm(affine[:3, :3], axis=0)[:, None]
        R = np.eye(3)
        if np.linalg.det(M) > 0:
            R[0, 0] = -1
        M = M.dot(R)
        # Expand 6 -> 3x3
        T = np.array(
            [
                [tensor_6[0], tensor_6[1], tensor_6[2]],
                [tensor_6[1], tensor_6[3], tensor_6[4]],
                [tensor_6[2], tensor_6[4], tensor_6[5]],
            ]
        )
        T_rot = M @ T @ M.T
        return T_rot

    def _compute_r_fix(self, src_affine, tgt_affine):
        """Replicate the fixed rotation from dti_extractor."""
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        R_src = _rotation_from_affine(src_affine)
        R_tgt = _rotation_from_affine(tgt_affine)
        M_fsl = R_tgt.copy()
        if np.linalg.det(R_tgt) > 0:
            M_fsl[:, 0] *= -1
        return M_fsl.T @ R_src

    def _apply_rotation(self, tensor_6, R):
        """Apply R @ T @ R^T to a 6-component tensor, return 6-component."""
        T = np.array(
            [
                [tensor_6[0], tensor_6[1], tensor_6[2]],
                [tensor_6[1], tensor_6[3], tensor_6[4]],
                [tensor_6[2], tensor_6[4], tensor_6[5]],
            ]
        )
        T_rot = R @ T @ R.T
        return np.array(
            [
                T_rot[0, 0],
                T_rot[0, 1],
                T_rot[0, 2],
                T_rot[1, 1],
                T_rot[1, 2],
                T_rot[2, 2],
            ]
        )

    def _gold_standard_world_tensor(self, tensor_6, src_affine):
        """Correct world-space tensor: R_src @ T @ R_src^T."""
        from tit.pre.qsi.dti_extractor import _rotation_from_affine

        R_src = _rotation_from_affine(src_affine)
        return self._apply_rotation(tensor_6, R_src)

    def test_lps_to_ras_45deg_fiber(self):
        """LPS source -> RAS target, fiber at 45 deg in xy plane."""
        # Tensor with significant off-diagonal: fiber at 45 deg in xy
        tensor_6 = np.array([1.0, 0.5, 0.1, 0.8, 0.05, 0.2])

        src_affine = np.diag([-2.0, -2.0, 2.0, 1.0])  # LPS
        tgt_affine = np.diag([1.0, 1.0, 1.0, 1.0])  # RAS 1mm

        R_fix = self._compute_r_fix(src_affine, tgt_affine)
        stored = self._apply_rotation(tensor_6, R_fix)
        world = self._simulate_correct_fsl(stored, tgt_affine)
        gold = self._gold_standard_world_tensor(tensor_6, src_affine)

        # Flatten gold to match world shape
        gold_3x3 = np.array(
            [
                [gold[0], gold[1], gold[2]],
                [gold[1], gold[3], gold[4]],
                [gold[2], gold[4], gold[5]],
            ]
        )
        np.testing.assert_allclose(world, gold_3x3, atol=1e-6)

    def test_ras_to_ras_identity(self):
        """RAS source -> RAS target, should be near-identity rotation."""
        tensor_6 = np.array([1.0, 0.5, 0.1, 0.8, 0.05, 0.2])

        src_affine = np.diag([1.0, 1.0, 1.0, 1.0])  # RAS
        tgt_affine = np.diag([1.0, 1.0, 1.0, 1.0])  # RAS

        R_fix = self._compute_r_fix(src_affine, tgt_affine)
        stored = self._apply_rotation(tensor_6, R_fix)
        world = self._simulate_correct_fsl(stored, tgt_affine)
        gold = self._gold_standard_world_tensor(tensor_6, src_affine)

        gold_3x3 = np.array(
            [
                [gold[0], gold[1], gold[2]],
                [gold[1], gold[3], gold[4]],
                [gold[2], gold[4], gold[5]],
            ]
        )
        np.testing.assert_allclose(world, gold_3x3, atol=1e-6)

    def test_las_source_negative_det(self):
        """LAS source (det < 0) -> RAS target."""
        tensor_6 = np.array([1.0, 0.5, 0.1, 0.8, 0.05, 0.2])

        src_affine = np.diag([-1.0, 1.0, 1.0, 1.0])  # LAS (det < 0)
        tgt_affine = np.diag([1.0, 1.0, 1.0, 1.0])  # RAS

        R_fix = self._compute_r_fix(src_affine, tgt_affine)
        stored = self._apply_rotation(tensor_6, R_fix)
        world = self._simulate_correct_fsl(stored, tgt_affine)
        gold = self._gold_standard_world_tensor(tensor_6, src_affine)

        gold_3x3 = np.array(
            [
                [gold[0], gold[1], gold[2]],
                [gold[1], gold[3], gold[4]],
                [gold[2], gold[4], gold[5]],
            ]
        )
        np.testing.assert_allclose(world, gold_3x3, atol=1e-6)


class TestBuildTargetGridCorners:
    """Verify _build_target_grid uses all 8 corners for bounding box."""

    @patch("nibabel.affines.apply_affine")
    @patch("nibabel.load")
    def test_oblique_affine_covers_full_volume(self, mock_load, mock_apply_affine):
        from tit.pre.qsi.dti_extractor import _build_target_grid

        # Create an oblique affine (45 deg rotation in xy plane)
        angle = np.pi / 4
        affine = np.eye(4)
        affine[0, 0] = np.cos(angle)
        affine[0, 1] = -np.sin(angle)
        affine[1, 0] = np.sin(angle)
        affine[1, 1] = np.cos(angle)

        mock_img = MagicMock()
        mock_img.affine = affine
        mock_img.shape = (100, 100, 100)
        mock_load.return_value = mock_img

        # Make apply_affine do real matrix math
        def real_apply_affine(aff, pts):
            pts = np.asarray(pts)
            return (aff[:3, :3] @ pts.T).T + aff[:3, 3]

        mock_apply_affine.side_effect = real_apply_affine

        shape, new_affine = _build_target_grid(Path("/fake"), resolution_mm=1.0)

        # For a 100^3 volume rotated 45 deg, the bounding box should be larger
        # than 100 in the x and y directions (diagonal ~ 141)
        assert shape[0] > 100 or shape[1] > 100


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

    @patch(
        "tit.reporting.generators.dti_qc.create_dti_qc_report",
        return_value=Path("/fake"),
    )
    @patch(f"{MODULE}.shutil.copy2")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._load_dsistudio_tensor")
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

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_load.return_value = (tensor, np.eye(4), MagicMock())

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
    @patch(f"{MODULE}._load_dsistudio_tensor")
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

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_load.return_value = (tensor, np.eye(4), MagicMock())

        extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

        mock_register.assert_called_once()
