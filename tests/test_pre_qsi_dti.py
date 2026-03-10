"""Tests for tit.pre.qsi.dti_extractor — DTI tensor extraction."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.pre.qsi.dti_extractor import (
    DSISTUDIO_TENSOR_PARAMS,
    _check_ants_available,
    _combine_dsistudio_tensor_components,
    _convert_tensor_to_simnibs_format,
    _find_dki_tensor_files,
    _find_dti_tensor_file,
    _find_dsistudio_tensor_components,
    _find_qsiprep_t1,
    _iter_qsirecon_subject_dirs,
    _validate_tensor,
    check_dti_tensor_exists,
    extract_dti_tensor,
)
from tit.pre.utils import PreprocessError


MODULE = "tit.pre.qsi.dti_extractor"


class TestIterQsireconSubjectDirs:
    """Tests for _iter_qsirecon_subject_dirs."""

    def test_primary_dir(self, tmp_path):
        result = _iter_qsirecon_subject_dirs(tmp_path, "001")
        assert any("sub-001" in str(d) for d in result)

    def test_with_derivatives(self, tmp_path):
        recon_dir = tmp_path / "derivatives" / "qsirecon-DSIStudio"
        recon_dir.mkdir(parents=True)

        result = _iter_qsirecon_subject_dirs(tmp_path, "001")
        assert len(result) >= 2

    def test_deduplication(self, tmp_path):
        result = _iter_qsirecon_subject_dirs(tmp_path, "001")
        assert len(result) == len(set(result))

    def test_skips_non_qsirecon_dirs(self, tmp_path):
        (tmp_path / "derivatives" / "other-pipeline").mkdir(parents=True)
        result = _iter_qsirecon_subject_dirs(tmp_path, "001")
        assert not any("other-pipeline" in str(d) for d in result)


class TestFindDsistudioTensorComponents:
    """Tests for _find_dsistudio_tensor_components."""

    def test_all_components_found(self, tmp_path):
        # Create DSIStudio output structure
        dwi_dir = tmp_path / "derivatives" / "qsirecon-DSIStudio" / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)

        for param in DSISTUDIO_TENSOR_PARAMS:
            (dwi_dir / f"sub-001_space-ACPC_model-tensor_param-{param}_dwimap.nii.gz").touch()

        result = _find_dsistudio_tensor_components(tmp_path, "001", MagicMock())
        assert result is not None
        assert len(result) == 6

    def test_missing_components(self, tmp_path):
        dwi_dir = tmp_path / "derivatives" / "qsirecon-DSIStudio" / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)

        # Only create some components
        for param in DSISTUDIO_TENSOR_PARAMS[:3]:
            (dwi_dir / f"sub-001_model-tensor_param-{param}_dwimap.nii.gz").touch()

        result = _find_dsistudio_tensor_components(tmp_path, "001", MagicMock())
        assert result is None

    def test_no_directory(self, tmp_path):
        result = _find_dsistudio_tensor_components(tmp_path, "001", MagicMock())
        assert result is None


class TestFindDtiTensorFile:
    """Tests for _find_dti_tensor_file."""

    def test_no_subject_dirs(self, tmp_path):
        result = _find_dti_tensor_file(tmp_path, "001", MagicMock())
        assert result is None

    def test_with_existing_but_empty_dir(self, tmp_path):
        sub_dir = tmp_path / "sub-001"
        sub_dir.mkdir(parents=True)
        result = _find_dti_tensor_file(tmp_path, "001", MagicMock())
        assert result is None


class TestFindDkiTensorFiles:
    """Tests for _find_dki_tensor_files."""

    def test_no_files(self, tmp_path):
        dt, kt = _find_dki_tensor_files(tmp_path, "001", MagicMock())
        assert dt is None
        assert kt is None

    def test_dt_found(self, tmp_path):
        sub_dir = tmp_path / "sub-001" / "dwi"
        sub_dir.mkdir(parents=True)
        (sub_dir / "sub-001_DT.nii.gz").touch()

        dt, kt = _find_dki_tensor_files(tmp_path, "001", MagicMock())
        assert dt is not None
        assert kt is None


class TestCombineDsistudioComponents:
    """Tests for _combine_dsistudio_tensor_components."""

    def test_combines_components(self):
        import nibabel as nib

        components = {}
        for param in DSISTUDIO_TENSOR_PARAMS:
            components[param] = Path(f"/fake/{param}.nii.gz")

        # Mock nibabel.load to return arrays
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.ones((5, 5, 5), dtype=np.float32)
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img

        data, affine, header = _combine_dsistudio_tensor_components(
            components, MagicMock()
        )
        assert data.shape == (5, 5, 5, 6)

    def test_handles_4d_input(self):
        import nibabel as nib

        components = {p: Path(f"/fake/{p}.nii.gz") for p in DSISTUDIO_TENSOR_PARAMS}

        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.ones((5, 5, 5, 1), dtype=np.float32)
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img

        data, _, _ = _combine_dsistudio_tensor_components(components, MagicMock())
        assert data.shape == (5, 5, 5, 6)

    def test_missing_component_raises(self):
        components = {p: Path(f"/fake/{p}.nii.gz") for p in DSISTUDIO_TENSOR_PARAMS[:5]}
        # Missing one component

        with pytest.raises(PreprocessError, match="Missing tensor"):
            _combine_dsistudio_tensor_components(components, MagicMock())


class TestConvertTensorToSimnibsFormat:
    """Tests for _convert_tensor_to_simnibs_format."""

    def test_6_component(self):
        data = np.ones((5, 5, 5, 6), dtype=np.float32)
        result = _convert_tensor_to_simnibs_format(data, MagicMock())
        np.testing.assert_array_equal(result, data)

    def test_9_component(self):
        data = np.ones((5, 5, 5, 9), dtype=np.float32)
        result = _convert_tensor_to_simnibs_format(data, MagicMock())
        assert result.shape == (5, 5, 5, 6)

    def test_5d_tensor(self):
        data = np.ones((5, 5, 5, 3, 3), dtype=np.float32)
        result = _convert_tensor_to_simnibs_format(data, MagicMock())
        assert result.shape == (5, 5, 5, 6)

    def test_3d_raises(self):
        data = np.ones((5, 5, 5), dtype=np.float32)
        with pytest.raises(ValueError, match="4D or 5D"):
            _convert_tensor_to_simnibs_format(data, MagicMock())

    def test_invalid_components(self):
        data = np.ones((5, 5, 5, 7), dtype=np.float32)
        with pytest.raises(ValueError, match="6 or 9"):
            _convert_tensor_to_simnibs_format(data, MagicMock())

    def test_5d_invalid_shape(self):
        data = np.ones((5, 5, 5, 2, 3), dtype=np.float32)
        with pytest.raises(ValueError, match="Unexpected tensor shape"):
            _convert_tensor_to_simnibs_format(data, MagicMock())


class TestValidateTensor:
    """Tests for _validate_tensor."""

    def test_valid_tensor(self):
        data = np.ones((5, 5, 5, 6), dtype=np.float32)
        _validate_tensor(data, MagicMock())  # Should not raise

    def test_invalid_shape(self):
        data = np.ones((5, 5, 5, 3), dtype=np.float32)
        with pytest.raises(PreprocessError, match="Invalid tensor shape"):
            _validate_tensor(data, MagicMock())

    def test_nan_values(self):
        data = np.ones((5, 5, 5, 6), dtype=np.float32)
        data[0, 0, 0, 0] = np.nan
        logger = MagicMock()
        _validate_tensor(data, logger)
        logger.warning.assert_called()
        assert data[0, 0, 0, 0] == 0.0

    def test_inf_values(self):
        data = np.ones((5, 5, 5, 6), dtype=np.float32)
        data[0, 0, 0, 0] = np.inf
        logger = MagicMock()
        _validate_tensor(data, logger)
        assert data[0, 0, 0, 0] == 0.0

    def test_all_zeros_raises(self):
        data = np.zeros((5, 5, 5, 6), dtype=np.float32)
        with pytest.raises(PreprocessError, match="entirely zero"):
            _validate_tensor(data, MagicMock())

    def test_low_coverage_warns(self):
        data = np.zeros((10, 10, 10, 6), dtype=np.float32)
        data[0, 0, 0, :] = 1.0  # Very few non-zero voxels
        logger = MagicMock()
        _validate_tensor(data, logger)
        logger.warning.assert_called()


class TestFindQsiprepT1:
    """Tests for _find_qsiprep_t1."""

    def test_found(self, tmp_path):
        t1 = (
            tmp_path / "derivatives" / "qsiprep" / "sub-001"
            / "anat" / "sub-001_space-ACPC_desc-preproc_T1w.nii.gz"
        )
        t1.parent.mkdir(parents=True)
        t1.touch()

        result = _find_qsiprep_t1(tmp_path, "001")
        assert result == t1

    def test_not_found(self, tmp_path):
        result = _find_qsiprep_t1(tmp_path, "001")
        assert result is None


class TestCheckAntsAvailable:
    """Tests for _check_ants_available."""

    @patch(f"{MODULE}.subprocess.run")
    def test_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert _check_ants_available() is True

    @patch(f"{MODULE}.subprocess.run")
    def test_not_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert _check_ants_available() is False

    @patch(f"{MODULE}.subprocess.run", side_effect=Exception)
    def test_exception(self, mock_run):
        assert _check_ants_available() is False


class TestRegisterWithAntsLocal:
    """Tests for _register_with_ants_local."""

    @patch(f"{MODULE}.subprocess.run")
    def test_registration_success(self, mock_run, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_with_ants_local

        mock_run.return_value = MagicMock(returncode=0)

        result = _register_with_ants_local(
            tmp_path / "tensor.nii.gz",
            tmp_path / "moving_t1.nii.gz",
            tmp_path / "fixed_t1.nii.gz",
            tmp_path / "output.nii.gz",
            tmp_path / "tmpdir",
            MagicMock(),
        )
        assert result == tmp_path / "output.nii.gz"
        assert mock_run.call_count == 2

    @patch(f"{MODULE}.subprocess.run")
    def test_registration_fails(self, mock_run, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_with_ants_local

        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        with pytest.raises(PreprocessError, match="ANTs registration failed"):
            _register_with_ants_local(
                tmp_path / "tensor.nii.gz",
                tmp_path / "moving_t1.nii.gz",
                tmp_path / "fixed_t1.nii.gz",
                tmp_path / "output.nii.gz",
                tmp_path / "tmpdir",
                MagicMock(),
            )

    @patch(f"{MODULE}.subprocess.run")
    def test_apply_transform_fails(self, mock_run, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_with_ants_local

        # First call (registration) succeeds, second (apply) fails
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="apply error"),
        ]

        with pytest.raises(PreprocessError, match="apply transform failed"):
            _register_with_ants_local(
                tmp_path / "tensor.nii.gz",
                tmp_path / "moving_t1.nii.gz",
                tmp_path / "fixed_t1.nii.gz",
                tmp_path / "output.nii.gz",
                tmp_path / "tmpdir",
                MagicMock(),
            )


class TestRegisterTensorToSimnibsT1:
    """Tests for _register_tensor_to_simnibs_t1."""

    @patch(f"{MODULE}._check_ants_available", return_value=True)
    @patch(f"{MODULE}._register_with_ants_local")
    def test_uses_ants_when_available(self, mock_ants, mock_check, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_tensor_to_simnibs_t1

        mock_ants.return_value = tmp_path / "out.nii.gz"

        _register_tensor_to_simnibs_t1(
            tmp_path / "tensor.nii.gz",
            tmp_path / "qsi_t1.nii.gz",
            tmp_path / "sim_t1.nii.gz",
            tmp_path / "out.nii.gz",
            MagicMock(),
        )
        mock_ants.assert_called_once()

    @patch(f"{MODULE}._check_ants_available", return_value=False)
    @patch(f"{MODULE}._resample_tensor_to_target")
    def test_falls_back_to_resample(self, mock_resample, mock_check, tmp_path):
        from tit.pre.qsi.dti_extractor import _register_tensor_to_simnibs_t1

        mock_resample.return_value = tmp_path / "out.nii.gz"

        _register_tensor_to_simnibs_t1(
            tmp_path / "tensor.nii.gz",
            tmp_path / "qsi_t1.nii.gz",
            tmp_path / "sim_t1.nii.gz",
            tmp_path / "out.nii.gz",
            MagicMock(),
        )
        mock_resample.assert_called_once()


class TestResampleTensorToTarget:
    """Tests for _resample_tensor_to_target."""

    def test_resamples(self, tmp_path):
        import sys
        from unittest.mock import MagicMock as MM

        # Ensure nibabel.processing is mocked
        mock_processing = MM()
        sys.modules["nibabel.processing"] = mock_processing

        from tit.pre.qsi.dti_extractor import _resample_tensor_to_target
        import nibabel as nib

        tensor_img = MM()
        tensor_img.get_fdata.return_value = np.ones((5, 5, 5, 6), dtype=np.float32)
        tensor_img.affine = np.eye(4)
        tensor_img.header = MM()

        target_img = MM()
        target_img.shape = (5, 5, 5)
        target_img.affine = np.eye(4)

        nib.load.side_effect = [tensor_img, target_img]

        resampled = MM()
        resampled.get_fdata.return_value = np.ones((5, 5, 5), dtype=np.float32)
        mock_processing.resample_from_to = MM(return_value=resampled)
        nib.Nifti1Image.return_value = MM()

        result = _resample_tensor_to_target(
            tmp_path / "tensor.nii.gz",
            tmp_path / "target.nii.gz",
            tmp_path / "output.nii.gz",
            MM(),
        )
        assert result == tmp_path / "output.nii.gz"
        nib.load.side_effect = None  # Reset


class TestCheckDtiTensorExists:
    """Tests for check_dti_tensor_exists."""

    @patch(f"{MODULE}.get_path_manager")
    def test_exists(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        # Create the tensor file
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


class TestExtractDtiTensor:
    """Tests for extract_dti_tensor."""

    @patch(f"{MODULE}.get_path_manager")
    def test_no_m2m_raises(self, mock_gpm, tmp_path):
        pm = MagicMock()
        pm.m2m.return_value = str(tmp_path / "nonexistent")
        mock_gpm.return_value = pm

        with pytest.raises(PreprocessError, match="m2m directory not found"):
            extract_dti_tensor("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    def test_existing_tensor_raises(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        # Create existing tensor
        (m2m / "DTI_coregT1_tensor.nii.gz").touch()

        with pytest.raises(PreprocessError, match="already exists"):
            extract_dti_tensor("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.get_path_manager")
    def test_unknown_source_raises(self, mock_gpm, tmp_path):
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        with pytest.raises(PreprocessError, match="Unknown source"):
            extract_dti_tensor("/proj", "001", logger=MagicMock(), source="invalid")

    @patch(f"{MODULE}.shutil.copy2")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components")
    @patch(f"{MODULE}._combine_dsistudio_tensor_components")
    @patch(f"{MODULE}.get_path_manager")
    def test_dsistudio_path_skip_registration(
        self, mock_gpm, mock_combine, mock_find_ds, mock_validate, mock_copy, tmp_path
    ):
        """Uses DSI Studio components when found, skip registration."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        mock_find_ds.return_value = {"txx": Path("/fake")}
        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_combine.return_value = (tensor, np.eye(4), MagicMock())

        nib.Nifti1Image.return_value = MagicMock()

        result = extract_dti_tensor(
            str(tmp_path), "001", logger=MagicMock(), skip_registration=True
        )
        assert result is not None
        mock_copy.assert_called_once()

    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files", return_value=(None, None))
    @patch(f"{MODULE}._find_dti_tensor_file", return_value=None)
    @patch(f"{MODULE}.get_path_manager")
    def test_no_tensor_found_raises(
        self, mock_gpm, mock_find_dti, mock_find_dki, mock_find_ds, mock_validate, tmp_path
    ):
        """Raises when no tensor file can be found."""
        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        with pytest.raises(PreprocessError, match="No DTI tensor found"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}.shutil.copy2")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files")
    @patch(f"{MODULE}.get_path_manager")
    def test_dki_path_skip_registration(
        self, mock_gpm, mock_find_dki, mock_find_ds, mock_validate, mock_copy, tmp_path
    ):
        """Uses DKI tensor when DSI Studio not available."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        dt_file = tmp_path / "dt.nii.gz"
        mock_find_dki.return_value = (dt_file, None)

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = tensor
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img
        nib.Nifti1Image.return_value = MagicMock()

        result = extract_dti_tensor(
            str(tmp_path), "001", logger=MagicMock(), skip_registration=True
        )
        assert result is not None

    @patch(f"{MODULE}.shutil.copy2")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files", return_value=(None, None))
    @patch(f"{MODULE}._find_dti_tensor_file")
    @patch(f"{MODULE}.get_path_manager")
    def test_fallback_dti_path(
        self, mock_gpm, mock_find_dti, mock_find_dki, mock_find_ds, mock_validate, mock_copy, tmp_path
    ):
        """Falls back to general DTI tensor search."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        dti_file = tmp_path / "tensor.nii.gz"
        mock_find_dti.return_value = dti_file

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = tensor
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img
        nib.Nifti1Image.return_value = MagicMock()

        result = extract_dti_tensor(
            str(tmp_path), "001", logger=MagicMock(), skip_registration=True
        )
        assert result is not None

    @patch(f"{MODULE}._resample_tensor_to_target")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files", return_value=(None, None))
    @patch(f"{MODULE}._find_dti_tensor_file")
    @patch(f"{MODULE}.get_path_manager")
    def test_registration_no_qsiprep_t1(
        self, mock_gpm, mock_find_dti, mock_find_dki, mock_find_ds,
        mock_validate, mock_resample, tmp_path
    ):
        """Falls back to resampling when no qsiprep T1 found."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        # Create SimNIBS T1
        (m2m / "T1.nii.gz").touch()

        mock_find_dti.return_value = tmp_path / "tensor.nii.gz"

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = tensor
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img
        nib.Nifti1Image.return_value = MagicMock()

        with patch(f"{MODULE}._find_qsiprep_t1", return_value=None):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

        mock_resample.assert_called_once()

    @patch(f"{MODULE}._register_tensor_to_simnibs_t1")
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files", return_value=(None, None))
    @patch(f"{MODULE}._find_dti_tensor_file")
    @patch(f"{MODULE}.get_path_manager")
    def test_registration_with_ants(
        self, mock_gpm, mock_find_dti, mock_find_dki, mock_find_ds,
        mock_validate, mock_register, tmp_path
    ):
        """Uses ANTs registration when qsiprep T1 exists."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        (m2m / "T1.nii.gz").touch()

        mock_find_dti.return_value = tmp_path / "tensor.nii.gz"

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = tensor
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img
        nib.Nifti1Image.return_value = MagicMock()

        qsiprep_t1 = tmp_path / "qsiprep_t1.nii.gz"
        with patch(f"{MODULE}._find_qsiprep_t1", return_value=qsiprep_t1):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

        mock_register.assert_called_once()

    @patch(f"{MODULE}._resample_tensor_to_target")
    @patch(f"{MODULE}._register_tensor_to_simnibs_t1", side_effect=Exception("ANTs failed"))
    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files", return_value=(None, None))
    @patch(f"{MODULE}._find_dti_tensor_file")
    @patch(f"{MODULE}.get_path_manager")
    def test_registration_fallback_on_failure(
        self, mock_gpm, mock_find_dti, mock_find_dki, mock_find_ds,
        mock_validate, mock_register, mock_resample, tmp_path
    ):
        """Falls back to resampling when registration fails."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        (m2m / "T1.nii.gz").touch()

        mock_find_dti.return_value = tmp_path / "tensor.nii.gz"

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = tensor
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img
        nib.Nifti1Image.return_value = MagicMock()

        qsiprep_t1 = tmp_path / "qsiprep_t1.nii.gz"
        with patch(f"{MODULE}._find_qsiprep_t1", return_value=qsiprep_t1):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

        mock_resample.assert_called_once()

    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files", return_value=(None, None))
    @patch(f"{MODULE}._find_dti_tensor_file")
    @patch(f"{MODULE}.get_path_manager")
    def test_no_simnibs_t1_raises(
        self, mock_gpm, mock_find_dti, mock_find_dki, mock_find_ds, mock_validate, tmp_path
    ):
        """Raises when SimNIBS T1 not found for registration."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        # No T1.nii.gz in m2m dir

        mock_find_dti.return_value = tmp_path / "tensor.nii.gz"

        tensor = np.ones((5, 5, 5, 6), dtype=np.float32)
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = tensor
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        nib.load.return_value = mock_img
        nib.Nifti1Image.return_value = MagicMock()

        with pytest.raises(PreprocessError, match="SimNIBS T1 not found"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

    @patch(f"{MODULE}._validate_tensor")
    @patch(f"{MODULE}._find_dsistudio_tensor_components", return_value=None)
    @patch(f"{MODULE}._find_dki_tensor_files", return_value=(None, None))
    @patch(f"{MODULE}._find_dti_tensor_file")
    @patch(f"{MODULE}.get_path_manager")
    def test_load_failure_raises(
        self, mock_gpm, mock_find_dti, mock_find_dki, mock_find_ds, mock_validate, tmp_path
    ):
        """Raises PreprocessError when tensor load fails."""
        import nibabel as nib

        pm = MagicMock()
        m2m = tmp_path / "m2m_001"
        m2m.mkdir()
        pm.m2m.return_value = str(m2m)
        mock_gpm.return_value = pm

        mock_find_dti.return_value = tmp_path / "tensor.nii.gz"
        nib.load.side_effect = Exception("corrupt file")

        with pytest.raises(PreprocessError, match="Failed to load"):
            extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())

        nib.load.side_effect = None  # Reset
