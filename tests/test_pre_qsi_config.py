"""Tests for tit.pre.qsi.config — QSI configuration dataclasses."""

import pytest

from tit.pre.qsi.config import (
    QSIAtlas,
    QSIPrepConfig,
    QSIReconConfig,
    ReconSpec,
    ResourceConfig,
)


class TestReconSpec:
    """Tests for the ReconSpec enum."""

    def test_str(self):
        assert str(ReconSpec.DIPY_DKI) == "dipy_dki"

    def test_from_string_valid(self):
        spec = ReconSpec.from_string("dipy_dki")
        assert spec == ReconSpec.DIPY_DKI

    def test_from_string_invalid(self):
        with pytest.raises(ValueError, match="Unknown recon spec"):
            ReconSpec.from_string("invalid")

    def test_list_all(self):
        result = ReconSpec.list_all()
        assert isinstance(result, list)
        assert "dipy_dki" in result
        assert len(result) > 0


class TestQSIAtlas:
    """Tests for the QSIAtlas enum."""

    def test_str(self):
        assert str(QSIAtlas.AAL116) == "AAL116"

    def test_from_string_valid(self):
        atlas = QSIAtlas.from_string("AAL116")
        assert atlas == QSIAtlas.AAL116

    def test_from_string_invalid(self):
        with pytest.raises(ValueError, match="Unknown atlas"):
            QSIAtlas.from_string("invalid")

    def test_list_all(self):
        result = QSIAtlas.list_all()
        assert isinstance(result, list)
        assert "AAL116" in result


class TestResourceConfig:
    """Tests for ResourceConfig."""

    def test_defaults(self):
        rc = ResourceConfig()
        assert rc.cpus is None
        assert rc.memory_gb is None
        assert rc.omp_threads >= 1

    def test_valid_values(self):
        rc = ResourceConfig(cpus=4, memory_gb=16, omp_threads=2)
        assert rc.cpus == 4
        assert rc.memory_gb == 16
        assert rc.omp_threads == 2

    def test_invalid_cpus(self):
        with pytest.raises(ValueError, match="cpus must be >= 1"):
            ResourceConfig(cpus=0)

    def test_invalid_memory(self):
        with pytest.raises(ValueError, match="memory_gb must be >= 4"):
            ResourceConfig(memory_gb=2)

    def test_invalid_omp(self):
        with pytest.raises(ValueError, match="omp_threads must be >= 1"):
            ResourceConfig(omp_threads=0)


class TestQSIPrepConfig:
    """Tests for QSIPrepConfig."""

    def test_defaults(self):
        cfg = QSIPrepConfig(subject_id="001")
        assert cfg.subject_id == "001"
        assert cfg.output_resolution > 0
        assert cfg.skip_bids_validation is True

    def test_empty_subject_raises(self):
        with pytest.raises(ValueError, match="subject_id is required"):
            QSIPrepConfig(subject_id="")

    def test_invalid_resolution(self):
        with pytest.raises(ValueError, match="output_resolution must be positive"):
            QSIPrepConfig(subject_id="001", output_resolution=-1.0)

    def test_invalid_denoise(self):
        with pytest.raises(ValueError, match="denoise_method"):
            QSIPrepConfig(subject_id="001", denoise_method="invalid")

    def test_invalid_unringing(self):
        with pytest.raises(ValueError, match="unringing_method"):
            QSIPrepConfig(subject_id="001", unringing_method="invalid")

    def test_valid_denoise_methods(self):
        for method in ("dwidenoise", "patch2self", "none"):
            cfg = QSIPrepConfig(subject_id="001", denoise_method=method)
            assert cfg.denoise_method == method

    def test_valid_unringing_methods(self):
        for method in ("mrdegibbs", "rpg", "none"):
            cfg = QSIPrepConfig(subject_id="001", unringing_method=method)
            assert cfg.unringing_method == method


class TestQSIReconConfig:
    """Tests for QSIReconConfig."""

    def test_defaults(self):
        cfg = QSIReconConfig(subject_id="001")
        assert cfg.subject_id == "001"
        assert len(cfg.recon_specs) > 0
        assert cfg.use_gpu is False

    def test_empty_subject_raises(self):
        with pytest.raises(ValueError, match="subject_id is required"):
            QSIReconConfig(subject_id="")

    def test_empty_specs_raises(self):
        with pytest.raises(ValueError, match="At least one recon_spec"):
            QSIReconConfig(subject_id="001", recon_specs=[])

    def test_invalid_spec_raises(self):
        with pytest.raises(ValueError, match="Unknown recon spec"):
            QSIReconConfig(subject_id="001", recon_specs=["invalid_spec"])

    def test_invalid_atlas_raises(self):
        with pytest.raises(ValueError, match="Unknown atlas"):
            QSIReconConfig(subject_id="001", atlases=["invalid_atlas"])

    def test_no_atlases(self):
        cfg = QSIReconConfig(subject_id="001", atlases=None)
        assert cfg.atlases is None

    def test_valid_config(self):
        cfg = QSIReconConfig(
            subject_id="001",
            recon_specs=["dipy_dki"],
            atlases=["AAL116"],
            use_gpu=True,
        )
        assert cfg.recon_specs == ["dipy_dki"]
        assert cfg.atlases == ["AAL116"]
        assert cfg.use_gpu is True
