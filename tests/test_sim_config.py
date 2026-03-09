#!/usr/bin/env simnibs_python
"""
Unit tests for sim.config module and calc.get_nTI_vectors.

Tests configuration dataclasses for TI simulations including:
- SimulationMode and ConductivityType enums
- ElectrodeConfig dataclass
- IntensityConfig dataclass (dynamic values list + backward-compat properties)
- LabelMontage / XYZMontage properties
- get_nTI_vectors for N-pair TI computation
"""

import sys
import pytest
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.sim.config import (
    SimulationMode,
    ConductivityType,
    ElectrodeConfig,
    IntensityConfig,
    LabelMontage,
    XYZMontage,
    SimulationConfig,
)
from tit.calc import get_TI_vectors, get_mTI_vectors, get_nTI_vectors


class TestSimulationMode:
    """Test suite for SimulationMode enum."""

    def test_ti_mode(self):
        assert SimulationMode.TI.value == "TI"

    def test_mti_mode(self):
        assert SimulationMode.MTI.value == "mTI"

    def test_mode_comparison(self):
        assert SimulationMode.TI == SimulationMode.TI
        assert SimulationMode.TI != SimulationMode.MTI


class TestConductivityType:
    """Test suite for ConductivityType enum."""

    def test_scalar_type(self):
        assert ConductivityType.SCALAR.value == "scalar"

    def test_vn_type(self):
        assert ConductivityType.VN.value == "vn"

    def test_dir_type(self):
        assert ConductivityType.DIR.value == "dir"

    def test_mc_type(self):
        assert ConductivityType.MC.value == "mc"

    def test_enum_from_string(self):
        assert ConductivityType("scalar") == ConductivityType.SCALAR
        assert ConductivityType("dir") == ConductivityType.DIR


class TestElectrodeConfig:
    """Test suite for ElectrodeConfig dataclass."""

    def test_default_values(self):
        config = ElectrodeConfig()
        assert config.shape == "ellipse"
        assert config.dimensions == [8.0, 8.0]
        assert config.gel_thickness == 4.0
        assert config.rubber_thickness == 2.0

    def test_custom_values(self):
        config = ElectrodeConfig(
            shape="rect", dimensions=[10.0, 12.0], gel_thickness=5.0, rubber_thickness=3.0
        )
        assert config.shape == "rect"
        assert config.dimensions == [10.0, 12.0]
        assert config.gel_thickness == 5.0
        assert config.rubber_thickness == 3.0


class TestIntensityConfig:
    """Test suite for IntensityConfig dataclass with dynamic values list."""

    def test_default_values(self):
        """Default is 2 pairs at 1.0 mA each."""
        config = IntensityConfig()
        assert config.values == [1.0, 1.0]
        assert config.pair1 == 1.0
        assert config.pair2 == 1.0

    def test_two_values(self):
        config = IntensityConfig(values=[2.0, 1.5])
        assert config.pair1 == 2.0
        assert config.pair2 == 1.5
        assert config.pair3 == 1.0  # out-of-range fallback
        assert config.pair4 == 1.0  # out-of-range fallback

    def test_four_values(self):
        config = IntensityConfig(values=[2.0, 1.5, 1.0, 0.5])
        assert config.pair1 == 2.0
        assert config.pair2 == 1.5
        assert config.pair3 == 1.0
        assert config.pair4 == 0.5

    def test_six_values(self):
        config = IntensityConfig(values=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        assert len(config.values) == 6
        assert config.pair1 == 1.0
        assert config.pair4 == 4.0
        assert config.values[4] == 5.0
        assert config.values[5] == 6.0

    def test_eight_values(self):
        config = IntensityConfig(values=[0.5] * 8)
        assert len(config.values) == 8
        assert all(v == 0.5 for v in config.values)

    def test_backward_compat_properties_empty(self):
        """Backward-compat properties return 1.0 for missing indices."""
        config = IntensityConfig(values=[])
        assert config.pair1 == 1.0
        assert config.pair2 == 1.0
        assert config.pair3 == 1.0
        assert config.pair4 == 1.0

    # -- from_string tests --

    def test_from_string_single_value(self):
        config = IntensityConfig.from_string("2.0")
        assert config.values == [2.0, 2.0]

    def test_from_string_two_values(self):
        config = IntensityConfig.from_string("2.0,1.5")
        assert config.values == [2.0, 1.5]

    def test_from_string_four_values(self):
        config = IntensityConfig.from_string("2.0,1.5,1.0,0.5")
        assert config.values == [2.0, 1.5, 1.0, 0.5]

    def test_from_string_six_values(self):
        config = IntensityConfig.from_string("1.0,2.0,3.0,4.0,5.0,6.0")
        assert config.values == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

    def test_from_string_eight_values(self):
        config = IntensityConfig.from_string("1,2,3,4,5,6,7,8")
        assert len(config.values) == 8

    def test_from_string_with_spaces(self):
        config = IntensityConfig.from_string("2.0 , 1.5")
        assert config.values == [2.0, 1.5]

    def test_from_string_invalid_three_values(self):
        with pytest.raises(ValueError, match="Invalid intensity format"):
            IntensityConfig.from_string("2.0,1.5,1.0")

    def test_from_string_invalid_five_values(self):
        with pytest.raises(ValueError, match="Invalid intensity format"):
            IntensityConfig.from_string("2.0,2.0,1.5,1.5,1.0")

    def test_from_string_invalid_empty(self):
        with pytest.raises(ValueError):
            IntensityConfig.from_string("")

    def test_from_string_invalid_non_numeric(self):
        with pytest.raises(ValueError):
            IntensityConfig.from_string("abc")


class TestLabelMontage:
    """Test suite for LabelMontage."""

    def test_ti_mode(self):
        m = LabelMontage(
            name="ti", electrode_pairs=[("Cz", "Oz"), ("C3", "C4")], eeg_net="net.csv"
        )
        assert m.simulation_mode == SimulationMode.TI
        assert m.num_pairs == 2

    def test_mti_mode(self):
        m = LabelMontage(
            name="mti",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4"), ("F3", "F4"), ("P3", "P4")],
            eeg_net="net.csv",
        )
        assert m.simulation_mode == SimulationMode.MTI
        assert m.num_pairs == 4

    def test_mti_six_pairs(self):
        m = LabelMontage(
            name="mti6",
            electrode_pairs=[
                ("Cz", "Oz"),
                ("C3", "C4"),
                ("F3", "F4"),
                ("P3", "P4"),
                ("T7", "T8"),
                ("Fp1", "Fp2"),
            ],
            eeg_net="net.csv",
        )
        assert m.simulation_mode == SimulationMode.MTI
        assert m.num_pairs == 6

    def test_invalid_one_pair(self):
        m = LabelMontage(name="bad", electrode_pairs=[("Cz", "Oz")], eeg_net="net.csv")
        with pytest.raises(ValueError, match="Invalid number of electrode pairs"):
            _ = m.simulation_mode


class TestXYZMontage:
    """Test suite for XYZMontage."""

    def test_is_xyz(self):
        m = XYZMontage(
            name="xyz",
            electrode_pairs=[
                ([0.0, 0.0, 100.0], [0.0, 0.0, -100.0]),
                ([50.0, 0.0, 0.0], [-50.0, 0.0, 0.0]),
            ],
        )
        assert m.is_xyz is True
        assert m.simulation_mode == SimulationMode.TI


class TestSimulationConfig:
    """Test suite for SimulationConfig dataclass."""

    def test_basic_creation(self):
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
        )
        assert config.subject_id == "001"
        assert isinstance(config.intensities, IntensityConfig)

    def test_default_mapping_options(self):
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
        )
        assert config.map_to_surf is True
        assert config.map_to_vol is False
        assert config.map_to_mni is False
        assert config.map_to_fsavg is False


# ── get_nTI_vectors tests ──────────────────────────────────────────────


class TestGetNTIVectors:
    """Test get_nTI_vectors with various field counts."""

    @pytest.fixture
    def random_fields(self):
        """Generate reproducible random (N,3) arrays."""
        rng = np.random.default_rng(42)

        def _make(n_fields, n_elements=100):
            return [rng.standard_normal((n_elements, 3)) for _ in range(n_fields)]

        return _make

    def test_two_fields_matches_get_TI_vectors(self, random_fields):
        fs = random_fields(2)
        result = get_nTI_vectors(fs)
        expected = get_TI_vectors(fs[0], fs[1])
        np.testing.assert_array_almost_equal(result, expected)

    def test_four_fields_matches_get_mTI_vectors(self, random_fields):
        fs = random_fields(4)
        result = get_nTI_vectors(fs)
        expected = get_mTI_vectors(fs[0], fs[1], fs[2], fs[3])
        np.testing.assert_array_almost_equal(result, expected)

    def test_six_fields_shape(self, random_fields):
        fs = random_fields(6, n_elements=50)
        result = get_nTI_vectors(fs)
        assert result.shape == (50, 3)

    def test_eight_fields_shape(self, random_fields):
        fs = random_fields(8, n_elements=50)
        result = get_nTI_vectors(fs)
        assert result.shape == (50, 3)

    def test_odd_number_raises(self, random_fields):
        with pytest.raises(ValueError, match="even number"):
            get_nTI_vectors(random_fields(3))

    def test_one_field_raises(self, random_fields):
        with pytest.raises(ValueError, match="even number"):
            get_nTI_vectors(random_fields(1))

    def test_six_fields_differ_from_four(self, random_fields):
        """Extra fields (5th & 6th) must actually contribute to the result."""
        fs6 = random_fields(6, n_elements=50)
        result_6 = get_nTI_vectors(fs6)
        result_4 = get_nTI_vectors(fs6[:4])
        assert not np.allclose(
            result_6, result_4
        ), "6-field result should differ from 4-field result"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="even number"):
            get_nTI_vectors([])


class TestIntensityConfigRoundTrip:
    """Test IntensityConfig JSON serialization round-trip."""

    def test_round_trip(self):
        original = IntensityConfig(values=[2.0, 1.5, 1.0, 0.5])
        serialized = {"values": original.values}
        restored = IntensityConfig(values=serialized["values"])
        assert restored.values == original.values

    def test_round_trip_six_values(self):
        original = IntensityConfig(values=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        serialized = {"values": original.values}
        restored = IntensityConfig(values=serialized["values"])
        assert restored.values == original.values

    def test_round_trip_default(self):
        original = IntensityConfig()
        serialized = {"values": original.values}
        restored = IntensityConfig(values=serialized["values"])
        assert restored.values == original.values
