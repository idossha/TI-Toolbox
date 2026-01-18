#!/usr/bin/env simnibs_python
"""
Unit tests for sim.config module.

Tests configuration dataclasses for TI simulations including:
- SimulationMode and ConductivityType enums
- ElectrodeConfig dataclass
- IntensityConfig dataclass and parsing
- MontageConfig properties
- ParallelConfig with auto-detection
"""

import os
import sys
import pytest
from unittest.mock import patch

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.sim.config import (
    SimulationMode,
    ConductivityType,
    ElectrodeConfig,
    IntensityConfig,
    MontageConfig,
    ParallelConfig,
    SimulationConfig,
)


class TestSimulationMode:
    """Test suite for SimulationMode enum."""

    def test_ti_mode(self):
        """Test TI mode enum value."""
        assert SimulationMode.TI.value == "TI"

    def test_mti_mode(self):
        """Test mTI mode enum value."""
        assert SimulationMode.MTI.value == "mTI"

    def test_mode_comparison(self):
        """Test enum equality comparison."""
        assert SimulationMode.TI == SimulationMode.TI
        assert SimulationMode.TI != SimulationMode.MTI


class TestConductivityType:
    """Test suite for ConductivityType enum."""

    def test_scalar_type(self):
        """Test scalar conductivity type."""
        assert ConductivityType.SCALAR.value == "scalar"

    def test_vn_type(self):
        """Test volume normalized conductivity type."""
        assert ConductivityType.VN.value == "vn"

    def test_dir_type(self):
        """Test direct mapping conductivity type."""
        assert ConductivityType.DIR.value == "dir"

    def test_mc_type(self):
        """Test Monte Carlo conductivity type."""
        assert ConductivityType.MC.value == "mc"

    def test_enum_from_string(self):
        """Test creating enum from string value."""
        assert ConductivityType("scalar") == ConductivityType.SCALAR
        assert ConductivityType("dir") == ConductivityType.DIR


class TestElectrodeConfig:
    """Test suite for ElectrodeConfig dataclass."""

    def test_default_values(self):
        """Test ElectrodeConfig with default values."""
        config = ElectrodeConfig()

        assert config.shape == "ellipse"
        assert config.dimensions == [8.0, 8.0]
        assert config.thickness == 4.0
        assert config.sponge_thickness == 2.0

    def test_custom_values(self):
        """Test ElectrodeConfig with custom values."""
        config = ElectrodeConfig(
            shape="rect", dimensions=[10.0, 12.0], thickness=5.0, sponge_thickness=3.0
        )

        assert config.shape == "rect"
        assert config.dimensions == [10.0, 12.0]
        assert config.thickness == 5.0
        assert config.sponge_thickness == 3.0

    def test_ellipse_shape(self):
        """Test ellipse electrode shape."""
        config = ElectrodeConfig(shape="ellipse")
        assert config.shape == "ellipse"

    def test_rectangular_shape(self):
        """Test rectangular electrode shape."""
        config = ElectrodeConfig(shape="rect")
        assert config.shape == "rect"

    def test_dimension_modifications(self):
        """Test modifying electrode dimensions."""
        config = ElectrodeConfig()
        config.dimensions = [15.0, 20.0]

        assert config.dimensions[0] == 15.0
        assert config.dimensions[1] == 20.0


class TestIntensityConfig:
    """Test suite for IntensityConfig dataclass."""

    def test_default_values(self):
        """Test IntensityConfig with default values."""
        config = IntensityConfig()

        assert config.pair1 == 1.0
        assert config.pair2 == 1.0
        assert config.pair3 == 1.0
        assert config.pair4 == 1.0

    def test_custom_values(self):
        """Test IntensityConfig with custom values."""
        config = IntensityConfig(pair1=2.0, pair2=1.5, pair3=1.0, pair4=0.5)

        assert config.pair1 == 2.0
        assert config.pair2 == 1.5
        assert config.pair3 == 1.0
        assert config.pair4 == 0.5

    def test_from_string_single_value(self):
        """Test parsing single value (all pairs same)."""
        config = IntensityConfig.from_string("2.0")

        assert config.pair1 == 2.0
        assert config.pair2 == 2.0
        assert config.pair3 == 2.0
        assert config.pair4 == 2.0

    def test_from_string_two_values(self):
        """Test parsing two values (pair1, pair2 for TI mode)."""
        config = IntensityConfig.from_string("2.0,1.5")

        assert config.pair1 == 2.0
        assert config.pair2 == 1.5
        assert config.pair3 == 1.0  # Default
        assert config.pair4 == 1.0  # Default

    def test_from_string_four_values(self):
        """Test parsing four values (all pairs specified for mTI mode)."""
        config = IntensityConfig.from_string("2.0,1.5,1.0,0.5")

        assert config.pair1 == 2.0
        assert config.pair2 == 1.5
        assert config.pair3 == 1.0
        assert config.pair4 == 0.5

    def test_from_string_with_spaces(self):
        """Test parsing with spaces around values."""
        config = IntensityConfig.from_string("2.0 , 1.5")

        assert config.pair1 == 2.0
        assert config.pair2 == 1.5
        assert config.pair3 == 1.0  # Default
        assert config.pair4 == 1.0  # Default

    def test_from_string_float_values(self):
        """Test parsing with decimal values."""
        config = IntensityConfig.from_string("1.75,1.25,0.5,0.75")

        assert config.pair1 == 1.75
        assert config.pair2 == 1.25
        assert config.pair3 == 0.5
        assert config.pair4 == 0.75

    def test_from_string_invalid_three_values(self):
        """Test that three values raises ValueError."""
        with pytest.raises(ValueError, match="Invalid intensity format"):
            IntensityConfig.from_string("2.0,1.5,1.0")

    def test_from_string_invalid_five_values(self):
        """Test that five values raises ValueError."""
        with pytest.raises(ValueError, match="Invalid intensity format"):
            IntensityConfig.from_string("2.0,2.0,1.5,1.5,1.0")

    def test_from_string_invalid_empty(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError):
            IntensityConfig.from_string("")

    def test_from_string_invalid_non_numeric(self):
        """Test that non-numeric values raise ValueError."""
        with pytest.raises(ValueError):
            IntensityConfig.from_string("abc")

    def test_from_string_invalid_partial_numeric(self):
        """Test that partially numeric values raise ValueError."""
        with pytest.raises(ValueError):
            IntensityConfig.from_string("2.0,abc")


class TestMontageConfig:
    """Test suite for MontageConfig dataclass."""

    def test_basic_creation(self):
        """Test basic MontageConfig creation."""
        montage = MontageConfig(
            name="test_montage", electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        assert montage.name == "test_montage"
        assert len(montage.electrode_pairs) == 2
        assert montage.is_xyz is False
        assert montage.eeg_net is None

    def test_simulation_mode_ti(self):
        """Test simulation_mode property returns TI for 2 pairs."""
        montage = MontageConfig(
            name="ti_montage", electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        assert montage.simulation_mode == SimulationMode.TI

    def test_simulation_mode_mti(self):
        """Test simulation_mode property returns MTI for 4 pairs."""
        montage = MontageConfig(
            name="mti_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4"), ("F3", "F4"), ("P3", "P4")],
        )

        assert montage.simulation_mode == SimulationMode.MTI

    def test_simulation_mode_mti_more_than_four(self):
        """Test simulation_mode returns MTI for more than 4 pairs."""
        montage = MontageConfig(
            name="mti_montage",
            electrode_pairs=[
                ("Cz", "Oz"),
                ("C3", "C4"),
                ("F3", "F4"),
                ("P3", "P4"),
                ("T7", "T8"),
            ],
        )

        assert montage.simulation_mode == SimulationMode.MTI

    def test_simulation_mode_invalid_one_pair(self):
        """Test that 1 pair raises ValueError."""
        montage = MontageConfig(name="invalid_montage", electrode_pairs=[("Cz", "Oz")])

        with pytest.raises(ValueError, match="Invalid number of electrode pairs"):
            _ = montage.simulation_mode

    def test_num_pairs_property(self):
        """Test num_pairs property returns correct count."""
        montage_2 = MontageConfig(
            name="montage_2", electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )
        assert montage_2.num_pairs == 2

        montage_4 = MontageConfig(
            name="montage_4",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4"), ("F3", "F4"), ("P3", "P4")],
        )
        assert montage_4.num_pairs == 4

    def test_xyz_coordinates(self):
        """Test MontageConfig with XYZ coordinates."""
        montage = MontageConfig(
            name="xyz_montage",
            electrode_pairs=[
                ([0.0, 0.0, 100.0], [0.0, 0.0, -100.0]),
                ([50.0, 0.0, 0.0], [-50.0, 0.0, 0.0]),
            ],
            is_xyz=True,
        )

        assert montage.is_xyz is True
        assert isinstance(montage.electrode_pairs[0][0], list)

    def test_eeg_net_override(self):
        """Test EEG net override for flex montages."""
        montage = MontageConfig(
            name="flex_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")],
            eeg_net="custom_cap.csv",
        )

        assert montage.eeg_net == "custom_cap.csv"


class TestParallelConfig:
    """Test suite for ParallelConfig dataclass."""

    def test_default_disabled(self):
        """Test ParallelConfig defaults to disabled."""
        config = ParallelConfig()

        assert config.enabled is False

    def test_enabled_config(self):
        """Test ParallelConfig when enabled."""
        config = ParallelConfig(enabled=True)

        assert config.enabled is True

    @patch("os.cpu_count", return_value=8)
    def test_auto_detect_max_workers(self, mock_cpu_count):
        """Test max_workers auto-detection uses half of CPU count."""
        config = ParallelConfig(max_workers=0)

        # cpu_count = 8, so max_workers should be min(4, 8//2) = 4
        assert config.max_workers == 4

    @patch("os.cpu_count", return_value=4)
    def test_auto_detect_low_cpu_count(self, mock_cpu_count):
        """Test max_workers auto-detection with low CPU count."""
        config = ParallelConfig(max_workers=0)

        # cpu_count = 4, so max_workers should be min(4, 4//2) = 2
        assert config.max_workers == 2

    @patch("os.cpu_count", return_value=16)
    def test_auto_detect_limits_to_four(self, mock_cpu_count):
        """Test max_workers auto-detection limits to 4."""
        config = ParallelConfig(max_workers=0)

        # cpu_count = 16, so max_workers should be min(4, 16//2) = 4
        assert config.max_workers == 4

    @patch("os.cpu_count", return_value=2)
    def test_auto_detect_minimum_one(self, mock_cpu_count):
        """Test max_workers auto-detection minimum is 1."""
        config = ParallelConfig(max_workers=0)

        # cpu_count = 2, so max_workers should be min(4, max(1, 2//2)) = 1
        assert config.max_workers == 1

    @patch("os.cpu_count", return_value=None)
    def test_auto_detect_fallback(self, mock_cpu_count):
        """Test max_workers auto-detection fallback when cpu_count is None."""
        config = ParallelConfig(max_workers=0)

        # cpu_count = None -> default 4, so max_workers = min(4, 4//2) = 2
        assert config.max_workers == 2

    def test_explicit_max_workers(self):
        """Test setting explicit max_workers value."""
        config = ParallelConfig(max_workers=6)

        assert config.max_workers == 6

    def test_negative_max_workers_triggers_auto(self):
        """Test negative max_workers triggers auto-detection."""
        with patch("os.cpu_count", return_value=8):
            config = ParallelConfig(max_workers=-1)

            # Should auto-detect to 4
            assert config.max_workers == 4

    def test_effective_workers_property(self):
        """Test effective_workers property returns max_workers."""
        config = ParallelConfig(max_workers=3)

        assert config.effective_workers == 3

    def test_memory_warning_disabled(self):
        """Test no memory warning when parallel is disabled."""
        config = ParallelConfig(enabled=False, max_workers=4)

        assert config.get_memory_warning() is None

    def test_memory_warning_enabled_low_workers(self):
        """Test no memory warning with <= 2 workers."""
        config = ParallelConfig(enabled=True, max_workers=2)

        assert config.get_memory_warning() is None

    def test_memory_warning_enabled_high_workers(self):
        """Test memory warning with > 2 workers."""
        config = ParallelConfig(enabled=True, max_workers=4)

        warning = config.get_memory_warning()
        assert warning is not None
        assert "4 parallel simulations" in warning
        assert "memory" in warning.lower()


class TestSimulationConfig:
    """Test suite for SimulationConfig dataclass."""

    def test_basic_creation(self):
        """Test basic SimulationConfig creation."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
        )

        assert config.subject_id == "001"
        assert config.project_dir == "/path/to/project"
        assert config.conductivity_type == ConductivityType.DIR
        assert isinstance(config.intensities, IntensityConfig)
        assert isinstance(config.electrode, ElectrodeConfig)

    def test_string_conductivity_conversion(self):
        """Test automatic conversion of string conductivity type to enum."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type="scalar",
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
        )

        assert isinstance(config.conductivity_type, ConductivityType)
        assert config.conductivity_type == ConductivityType.SCALAR

    def test_default_mapping_options(self):
        """Test default mapping options."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
        )

        assert config.map_to_surf is True
        assert config.map_to_vol is True
        assert config.map_to_mni is True
        assert config.map_to_fsavg is False
        assert config.tissues_in_niftis == "all"
        assert config.open_in_gmsh is False

    def test_custom_eeg_net(self):
        """Test custom EEG net template."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
            eeg_net="custom_template.csv",
        )

        assert config.eeg_net == "custom_template.csv"

    def test_parallel_config_creation(self):
        """Test ParallelConfig is created by default."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
        )

        assert isinstance(config.parallel, ParallelConfig)
        assert config.parallel.enabled is False

    def test_parallel_config_from_dict(self):
        """Test ParallelConfig conversion from dict."""
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
            parallel={"enabled": True, "max_workers": 2},
        )

        assert isinstance(config.parallel, ParallelConfig)
        assert config.parallel.enabled is True
        assert config.parallel.max_workers == 2
