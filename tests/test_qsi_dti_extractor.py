#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for DTI tensor extraction module.

These tests verify the DTI tensor extraction and conversion functions
for SimNIBS integration.
"""

import logging
import os
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock

from tit.core import constants as const
from tit.pre.common import PreprocessError
from tit.pre.qsi.dti_extractor import (
    _find_dti_tensor_file,
    _find_dki_tensor_files,
    _convert_tensor_to_simnibs_format,
    extract_dti_tensor,
    check_dti_tensor_exists,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    return MagicMock(spec=logging.Logger)


class TestFindDtiTensorFile:
    """Tests for _find_dti_tensor_file function."""

    def test_find_tensor_in_standard_location(self, tmp_path, mock_logger):
        """Test finding tensor file in standard DTI output location."""
        # Create QSIRecon output structure with tensor file
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        tensor_file = dwi_dir / "sub-001_dti_tensor.nii.gz"
        tensor_file.touch()

        # Mock nibabel to return valid tensor shape
        mock_img = MagicMock()
        mock_img.shape = (10, 10, 10, 6)  # Valid tensor shape

        with patch.dict("sys.modules", {"nibabel": MagicMock()}):
            import sys
            sys.modules["nibabel"].load.return_value = mock_img

            result = _find_dti_tensor_file(tmp_path, "001", mock_logger)
            assert result is not None
            assert result.name == "sub-001_dti_tensor.nii.gz"

    def test_find_tensor_with_different_naming(self, tmp_path, mock_logger):
        """Test finding tensor file with alternative naming convention."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        tensor_file = dwi_dir / "sub-001_tensor.nii.gz"
        tensor_file.touch()

        # Mock nibabel to return valid tensor shape
        mock_img = MagicMock()
        mock_img.shape = (10, 10, 10, 6)

        with patch.dict("sys.modules", {"nibabel": MagicMock()}):
            import sys
            sys.modules["nibabel"].load.return_value = mock_img

            result = _find_dti_tensor_file(tmp_path, "001", mock_logger)
            assert result is not None

    def test_no_tensor_file_found(self, tmp_path, mock_logger):
        """Test when no tensor file is found."""
        # Create directory structure but no tensor file matching patterns
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_fa.nii.gz").touch()  # FA file, not tensor

        # Mock nibabel - FA file won't match tensor patterns anyway
        mock_img = MagicMock()
        mock_img.shape = (10, 10, 10)  # 3D - not a tensor

        with patch.dict("sys.modules", {"nibabel": MagicMock()}):
            import sys
            sys.modules["nibabel"].load.return_value = mock_img

            result = _find_dti_tensor_file(tmp_path, "001", mock_logger)
            assert result is None

    def test_subject_directory_not_found(self, tmp_path, mock_logger):
        """Test when subject directory doesn't exist."""
        result = _find_dti_tensor_file(tmp_path, "001", mock_logger)
        assert result is None
        mock_logger.warning.assert_called()

    def test_filters_out_non_tensor_files(self, tmp_path, mock_logger):
        """Test that FA, MD, etc. files are filtered out."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        # Create files that should be filtered by name
        (dwi_dir / "sub-001_fa.nii.gz").touch()
        (dwi_dir / "sub-001_md.nii.gz").touch()
        (dwi_dir / "sub-001_mask.nii.gz").touch()
        # Create actual tensor file
        tensor_file = dwi_dir / "sub-001_dti_tensor.nii.gz"
        tensor_file.touch()

        # Mock nibabel to return valid tensor shape for tensor file
        mock_img = MagicMock()
        mock_img.shape = (10, 10, 10, 6)

        with patch.dict("sys.modules", {"nibabel": MagicMock()}):
            import sys
            sys.modules["nibabel"].load.return_value = mock_img

            result = _find_dti_tensor_file(tmp_path, "001", mock_logger)
            assert result is not None
            assert "tensor" in result.name.lower()


class TestFindDkiTensorFiles:
    """Tests for _find_dki_tensor_files function."""

    def test_find_both_dt_and_kt(self, tmp_path, mock_logger):
        """Test finding both DT and KT tensor files."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_DT.nii.gz").touch()
        (dwi_dir / "sub-001_KT.nii.gz").touch()

        dt_file, kt_file = _find_dki_tensor_files(tmp_path, "001", mock_logger)
        assert dt_file is not None
        assert kt_file is not None
        assert "DT" in dt_file.name
        assert "KT" in kt_file.name

    def test_find_only_dt(self, tmp_path, mock_logger):
        """Test finding only DT tensor file."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_DT.nii.gz").touch()

        dt_file, kt_file = _find_dki_tensor_files(tmp_path, "001", mock_logger)
        assert dt_file is not None
        assert kt_file is None

    def test_find_lowercase_dt(self, tmp_path, mock_logger):
        """Test finding lowercase dt tensor file."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)
        (dwi_dir / "sub-001_dt.nii.gz").touch()

        dt_file, kt_file = _find_dki_tensor_files(tmp_path, "001", mock_logger)
        assert dt_file is not None

    def test_no_dki_files_found(self, tmp_path, mock_logger):
        """Test when no DKI files are found."""
        dwi_dir = tmp_path / "sub-001" / "dwi"
        dwi_dir.mkdir(parents=True)

        dt_file, kt_file = _find_dki_tensor_files(tmp_path, "001", mock_logger)
        assert dt_file is None
        assert kt_file is None


class TestConvertTensorToSimnibsFormat:
    """Tests for _convert_tensor_to_simnibs_format function."""

    def test_6_component_tensor_passthrough(self, mock_logger):
        """Test that 6-component tensor passes through unchanged."""
        tensor_data = np.random.rand(10, 10, 10, 6).astype(np.float32)
        result = _convert_tensor_to_simnibs_format(tensor_data, mock_logger)
        assert result.shape == (10, 10, 10, 6)
        np.testing.assert_array_equal(result, tensor_data)

    def test_9_component_tensor_conversion(self, mock_logger):
        """Test conversion of 9-component tensor to 6-component format."""
        # Create 9-component tensor (3x3 flattened)
        # [Dxx, Dxy, Dxz, Dyx, Dyy, Dyz, Dzx, Dzy, Dzz]
        tensor_9 = np.zeros((3, 3, 3, 9), dtype=np.float32)
        tensor_9[..., 0] = 1.0  # Dxx
        tensor_9[..., 1] = 2.0  # Dxy
        tensor_9[..., 2] = 3.0  # Dxz
        tensor_9[..., 4] = 4.0  # Dyy
        tensor_9[..., 5] = 5.0  # Dyz
        tensor_9[..., 8] = 6.0  # Dzz

        result = _convert_tensor_to_simnibs_format(tensor_9, mock_logger)

        assert result.shape == (3, 3, 3, 6)
        # Check upper triangular extraction
        np.testing.assert_array_equal(result[..., 0], 1.0)  # Dxx
        np.testing.assert_array_equal(result[..., 1], 2.0)  # Dxy
        np.testing.assert_array_equal(result[..., 2], 3.0)  # Dxz
        np.testing.assert_array_equal(result[..., 3], 4.0)  # Dyy
        np.testing.assert_array_equal(result[..., 4], 5.0)  # Dyz
        np.testing.assert_array_equal(result[..., 5], 6.0)  # Dzz

    def test_3d_tensor_raises_error(self, mock_logger):
        """Test that 3D tensor raises ValueError."""
        tensor_3d = np.random.rand(10, 10, 10).astype(np.float32)
        with pytest.raises(ValueError, match="must be 4D"):
            _convert_tensor_to_simnibs_format(tensor_3d, mock_logger)

    def test_invalid_component_count(self, mock_logger):
        """Test that invalid component count raises ValueError."""
        tensor_wrong = np.random.rand(10, 10, 10, 7).astype(np.float32)
        with pytest.raises(ValueError, match="Expected 6 or 9"):
            _convert_tensor_to_simnibs_format(tensor_wrong, mock_logger)

    def test_preserves_dtype(self, mock_logger):
        """Test that dtype is preserved during conversion."""
        tensor_data = np.random.rand(3, 3, 3, 6).astype(np.float64)
        result = _convert_tensor_to_simnibs_format(tensor_data, mock_logger)
        # Note: The function doesn't explicitly preserve dtype,
        # but should maintain the input dtype
        assert result.dtype == tensor_data.dtype


class TestExtractDtiTensor:
    """Tests for extract_dti_tensor function."""

    @pytest.fixture
    def mock_path_manager(self, tmp_path):
        """Create a mock PathManager."""
        pm = MagicMock()
        pm.path_optional.return_value = str(tmp_path / "m2m_001")
        return pm

    @pytest.fixture
    def setup_m2m_dir(self, tmp_path):
        """Set up m2m directory structure."""
        m2m_dir = tmp_path / "m2m_001"
        m2m_dir.mkdir(parents=True)
        return m2m_dir

    def test_extract_dti_tensor_success(self, tmp_path, mock_logger, setup_m2m_dir):
        """Test successful DTI tensor extraction."""
        # Create mock tensor file in qsirecon output
        qsirecon_dir = tmp_path / "derivatives" / "qsirecon" / "sub-001" / "dwi"
        qsirecon_dir.mkdir(parents=True)
        tensor_file = qsirecon_dir / "sub-001_dti_tensor.nii.gz"

        # Create a mock nibabel module
        mock_nib = MagicMock()
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.random.rand(10, 10, 10, 6).astype(np.float32)
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        mock_img.shape = (10, 10, 10, 6)
        mock_nib.load.return_value = mock_img
        mock_nib.Nifti1Image.return_value = MagicMock()

        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = str(setup_m2m_dir)
            mock_get_pm.return_value = mock_pm

            # Patch nibabel at import time using patch.dict on sys.modules
            with patch.dict("sys.modules", {"nibabel": mock_nib}):
                with patch(
                    "tit.pre.qsi.dti_extractor._find_dsistudio_tensor_components",
                    return_value=None,
                ):
                    with patch(
                        "tit.pre.qsi.dti_extractor._find_dki_tensor_files",
                        return_value=(None, None),
                    ):
                        with patch(
                            "tit.pre.qsi.dti_extractor._find_dti_tensor_file",
                            return_value=tensor_file,
                        ):
                            with patch(
                                "tit.pre.qsi.dti_extractor.shutil.copy2"
                            ) as mock_copy:
                                result = extract_dti_tensor(
                                    project_dir=str(tmp_path),
                                    subject_id="001",
                                    logger=mock_logger,
                                    skip_registration=True,  # Skip registration in test
                                )

                                assert result is not None
                                # Should have saved the intermediate file
                                assert mock_nib.save.called
                                # Should have copied to final location
                                assert mock_copy.called

    def test_extract_dti_tensor_m2m_not_found(self, tmp_path, mock_logger):
        """Test that missing m2m directory raises PreprocessError."""
        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = None
            mock_get_pm.return_value = mock_pm

            with pytest.raises(PreprocessError, match="m2m directory not found"):
                extract_dti_tensor(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                )

    def test_extract_dti_tensor_skip_existing(
        self, tmp_path, mock_logger, setup_m2m_dir
    ):
        """Test that existing tensor is skipped when overwrite=False."""
        # Create existing tensor file
        tensor_path = setup_m2m_dir / const.FILE_DTI_TENSOR
        tensor_path.touch()

        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = str(setup_m2m_dir)
            mock_get_pm.return_value = mock_pm

            result = extract_dti_tensor(
                project_dir=str(tmp_path),
                subject_id="001",
                logger=mock_logger,
                overwrite=False,
            )

            assert result == tensor_path
            mock_logger.info.assert_called()

    def test_extract_dti_tensor_no_source_found(
        self, tmp_path, mock_logger, setup_m2m_dir
    ):
        """Test that missing source tensor raises PreprocessError."""
        # Create qsirecon directory but no tensor file
        qsirecon_dir = tmp_path / "derivatives" / "qsirecon"
        qsirecon_dir.mkdir(parents=True)

        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = str(setup_m2m_dir)
            mock_get_pm.return_value = mock_pm

            with patch(
                "tit.pre.qsi.dti_extractor._find_dki_tensor_files",
                return_value=(None, None),
            ):
                with patch(
                    "tit.pre.qsi.dti_extractor._find_dti_tensor_file",
                    return_value=None,
                ):
                    with pytest.raises(PreprocessError, match="No DTI tensor found"):
                        extract_dti_tensor(
                            project_dir=str(tmp_path),
                            subject_id="001",
                            logger=mock_logger,
                        )

    def test_extract_dti_tensor_unknown_source(
        self, tmp_path, mock_logger, setup_m2m_dir
    ):
        """Test that unknown source raises PreprocessError."""
        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = str(setup_m2m_dir)
            mock_get_pm.return_value = mock_pm

            with pytest.raises(PreprocessError, match="Unknown source"):
                extract_dti_tensor(
                    project_dir=str(tmp_path),
                    subject_id="001",
                    logger=mock_logger,
                    source="unknown_source",
                )

    def test_extract_dti_tensor_uses_dki_first(
        self, tmp_path, mock_logger, setup_m2m_dir
    ):
        """Test that DKI tensor is preferred over general DTI tensor."""
        # Create a mock nibabel module
        mock_nib = MagicMock()
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.random.rand(10, 10, 10, 6).astype(np.float32)
        mock_img.affine = np.eye(4)
        mock_img.header = MagicMock()
        mock_img.shape = (10, 10, 10, 6)
        mock_nib.load.return_value = mock_img
        mock_nib.Nifti1Image.return_value = MagicMock()

        dki_dt_file = tmp_path / "sub-001_DT.nii.gz"
        dti_tensor_file = tmp_path / "sub-001_dti_tensor.nii.gz"

        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = str(setup_m2m_dir)
            mock_get_pm.return_value = mock_pm

            # Patch nibabel at import time using patch.dict on sys.modules
            with patch.dict("sys.modules", {"nibabel": mock_nib}):
                with patch(
                    "tit.pre.qsi.dti_extractor._find_dsistudio_tensor_components",
                    return_value=None,
                ):
                    with patch(
                        "tit.pre.qsi.dti_extractor._find_dki_tensor_files",
                        return_value=(dki_dt_file, None),
                    ) as mock_find_dki:
                        with patch(
                            "tit.pre.qsi.dti_extractor._find_dti_tensor_file",
                            return_value=dti_tensor_file,
                        ) as mock_find_dti:
                            with patch(
                                "tit.pre.qsi.dti_extractor.shutil.copy2"
                            ):
                                extract_dti_tensor(
                                    project_dir=str(tmp_path),
                                    subject_id="001",
                                    logger=mock_logger,
                                    skip_registration=True,
                                )

                                # DKI should be tried first
                                mock_find_dki.assert_called_once()
                                # General DTI should not be called since DKI was found
                                mock_find_dti.assert_not_called()


class TestCheckDtiTensorExists:
    """Tests for check_dti_tensor_exists function."""

    def test_tensor_exists(self, tmp_path):
        """Test when tensor file exists."""
        m2m_dir = tmp_path / "m2m_001"
        m2m_dir.mkdir(parents=True)
        tensor_path = m2m_dir / const.FILE_DTI_TENSOR
        tensor_path.touch()

        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = str(m2m_dir)
            mock_get_pm.return_value = mock_pm

            result = check_dti_tensor_exists(str(tmp_path), "001")
            assert result is True

    def test_tensor_not_exists(self, tmp_path):
        """Test when tensor file doesn't exist."""
        m2m_dir = tmp_path / "m2m_001"
        m2m_dir.mkdir(parents=True)

        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = str(m2m_dir)
            mock_get_pm.return_value = mock_pm

            result = check_dti_tensor_exists(str(tmp_path), "001")
            assert result is False

    def test_m2m_dir_not_found(self, tmp_path):
        """Test when m2m directory is not found."""
        with patch("tit.pre.qsi.dti_extractor.get_path_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.path_optional.return_value = None
            mock_get_pm.return_value = mock_pm

            result = check_dti_tensor_exists(str(tmp_path), "001")
            assert result is False
