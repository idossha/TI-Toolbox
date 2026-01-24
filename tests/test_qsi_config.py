#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for QSI configuration dataclasses and enums.
"""

import pytest

from tit.core import constants as const
from tit.pre.qsi.config import (
    ReconSpec,
    QSIAtlas,
    ResourceConfig,
    QSIPrepConfig,
    QSIReconConfig,
)


class TestReconSpec:
    """Tests for the ReconSpec enum."""

    def test_enum_values(self):
        """Test that all expected recon specs are defined."""
        assert ReconSpec.DIPY_DKI.value == "dipy_dki"
        assert ReconSpec.MRTRIX_MULTISHELL_MSMT_ACT_FAST.value == "mrtrix_multishell_msmt_ACT-fast"
        assert ReconSpec.AMICO_NODDI.value == "amico_noddi"

    def test_from_string(self):
        """Test string to enum conversion."""
        spec = ReconSpec.from_string("dipy_dki")
        assert spec == ReconSpec.DIPY_DKI

    def test_from_string_invalid(self):
        """Test that invalid string raises ValueError."""
        with pytest.raises(ValueError, match="Unknown recon spec"):
            ReconSpec.from_string("invalid_spec")

    def test_list_all(self):
        """Test listing all spec values."""
        specs = ReconSpec.list_all()
        assert "dipy_dki" in specs
        assert "amico_noddi" in specs
        assert len(specs) == len(ReconSpec)

    def test_str_conversion(self):
        """Test that str() returns the value."""
        assert str(ReconSpec.DIPY_DKI) == "dipy_dki"


class TestQSIAtlas:
    """Tests for the QSIAtlas enum."""

    def test_enum_values(self):
        """Test that expected atlases are defined."""
        assert QSIAtlas.AAL116.value == "AAL116"
        assert QSIAtlas.SCHAEFER100.value == "Schaefer100"

    def test_from_string(self):
        """Test string to enum conversion."""
        atlas = QSIAtlas.from_string("Schaefer200")
        assert atlas == QSIAtlas.SCHAEFER200

    def test_from_string_invalid(self):
        """Test that invalid string raises ValueError."""
        with pytest.raises(ValueError, match="Unknown atlas"):
            QSIAtlas.from_string("invalid_atlas")

    def test_list_all(self):
        """Test listing all atlas values."""
        atlases = QSIAtlas.list_all()
        assert "AAL116" in atlases
        assert len(atlases) == len(QSIAtlas)


class TestResourceConfig:
    """Tests for the ResourceConfig dataclass."""

    def test_default_values(self):
        """Test default resource values."""
        config = ResourceConfig()
        assert config.cpus == const.QSI_DEFAULT_CPUS
        assert config.memory_gb == const.QSI_DEFAULT_MEMORY_GB
        assert config.omp_threads == const.QSI_DEFAULT_OMP_THREADS

    def test_custom_values(self):
        """Test custom resource values."""
        config = ResourceConfig(cpus=16, memory_gb=64, omp_threads=4)
        assert config.cpus == 16
        assert config.memory_gb == 64
        assert config.omp_threads == 4

    def test_invalid_cpus(self):
        """Test that invalid cpus raises ValueError."""
        with pytest.raises(ValueError, match="cpus must be >= 1"):
            ResourceConfig(cpus=0)

    def test_invalid_memory(self):
        """Test that invalid memory raises ValueError."""
        with pytest.raises(ValueError, match="memory_gb must be >= 4"):
            ResourceConfig(memory_gb=2)

    def test_invalid_omp_threads(self):
        """Test that invalid omp_threads raises ValueError."""
        with pytest.raises(ValueError, match="omp_threads must be >= 1"):
            ResourceConfig(omp_threads=0)


class TestQSIPrepConfig:
    """Tests for the QSIPrepConfig dataclass."""

    def test_required_subject_id(self):
        """Test that subject_id is required."""
        with pytest.raises(ValueError, match="subject_id is required"):
            QSIPrepConfig(subject_id="")

    def test_default_values(self):
        """Test default configuration values."""
        config = QSIPrepConfig(subject_id="001")
        assert config.subject_id == "001"
        assert config.output_resolution == const.QSI_DEFAULT_OUTPUT_RESOLUTION
        assert config.image_tag == const.QSI_DEFAULT_IMAGE_TAG
        assert config.skip_bids_validation is True
        assert config.denoise_method == "dwidenoise"
        assert config.unringing_method == "mrdegibbs"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = QSIPrepConfig(
            subject_id="002",
            output_resolution=1.5,
            image_tag="1.0.0",
            denoise_method="patch2self",
        )
        assert config.subject_id == "002"
        assert config.output_resolution == 1.5
        assert config.image_tag == "1.0.0"
        assert config.denoise_method == "patch2self"

    def test_invalid_output_resolution(self):
        """Test that non-positive resolution raises ValueError."""
        with pytest.raises(ValueError, match="output_resolution must be positive"):
            QSIPrepConfig(subject_id="001", output_resolution=0)

    def test_invalid_denoise_method(self):
        """Test that invalid denoise method raises ValueError."""
        with pytest.raises(ValueError, match="denoise_method must be one of"):
            QSIPrepConfig(subject_id="001", denoise_method="invalid")

    def test_invalid_unringing_method(self):
        """Test that invalid unringing method raises ValueError."""
        with pytest.raises(ValueError, match="unringing_method must be one of"):
            QSIPrepConfig(subject_id="001", unringing_method="invalid")

    def test_resource_config_included(self):
        """Test that resource config is properly initialized."""
        config = QSIPrepConfig(subject_id="001")
        assert isinstance(config.resources, ResourceConfig)
        assert config.resources.cpus == const.QSI_DEFAULT_CPUS


class TestQSIReconConfig:
    """Tests for the QSIReconConfig dataclass."""

    def test_required_subject_id(self):
        """Test that subject_id is required."""
        with pytest.raises(ValueError, match="subject_id is required"):
            QSIReconConfig(subject_id="")

    def test_required_recon_specs(self):
        """Test that at least one recon_spec is required."""
        with pytest.raises(ValueError, match="At least one recon_spec is required"):
            QSIReconConfig(subject_id="001", recon_specs=[])

    def test_default_values(self):
        """Test default configuration values."""
        config = QSIReconConfig(subject_id="001")
        assert config.subject_id == "001"
        assert config.recon_specs == ["mrtrix_multishell_msmt_ACT-fast"]
        assert config.atlases == ["Schaefer100", "AAL116"]
        assert config.use_gpu is False
        assert config.image_tag == const.QSI_DEFAULT_IMAGE_TAG

    def test_custom_values(self):
        """Test custom configuration values."""
        config = QSIReconConfig(
            subject_id="002",
            recon_specs=["dipy_dki", "amico_noddi"],
            atlases=["Schaefer100", "AAL116"],
            use_gpu=True,
        )
        assert config.subject_id == "002"
        assert config.recon_specs == ["dipy_dki", "amico_noddi"]
        assert config.atlases == ["Schaefer100", "AAL116"]
        assert config.use_gpu is True

    def test_invalid_recon_spec(self):
        """Test that invalid recon spec raises ValueError."""
        with pytest.raises(ValueError, match="Unknown recon spec"):
            QSIReconConfig(subject_id="001", recon_specs=["invalid_spec"])

    def test_invalid_atlas(self):
        """Test that invalid atlas raises ValueError."""
        with pytest.raises(ValueError, match="Unknown atlas"):
            QSIReconConfig(subject_id="001", atlases=["invalid_atlas"])

    def test_multiple_valid_specs(self):
        """Test configuration with multiple valid specs."""
        config = QSIReconConfig(
            subject_id="001",
            recon_specs=["dipy_dki", "dipy_mapmri", "amico_noddi"],
        )
        assert len(config.recon_specs) == 3

    def test_resource_config_included(self):
        """Test that resource config is properly initialized."""
        config = QSIReconConfig(subject_id="001")
        assert isinstance(config.resources, ResourceConfig)
