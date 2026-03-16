#!/usr/bin/env simnibs_python
"""
Unit tests for sim.config module and calc.get_nTI_vectors.

Tests configuration dataclasses for TI simulations including:
- SimulationMode enum
- MontageMode enum
- Montage dataclass (is_xyz, simulation_mode, num_pairs)
- SimulationConfig dataclass (flat fields, conductivity validation)
- parse_intensities helper function
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
    Montage,
    SimulationConfig,
    parse_intensities,
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


class TestMontageMode:
    """Test suite for Montage.Mode enum."""

    def test_montage_value(self):
        assert Montage.Mode.NET.value == "net"

    def test_flex_mapped_value(self):
        assert Montage.Mode.FLEX_MAPPED.value == "flex_mapped"

    def test_flex_opt_value(self):
        assert Montage.Mode.FLEX_FREE.value == "flex_free"

    def test_freehand_value(self):
        assert Montage.Mode.FREEHAND.value == "freehand"

    def test_enum_from_string(self):
        assert Montage.Mode("net") == Montage.Mode.NET
        assert Montage.Mode("flex_free") == Montage.Mode.FLEX_FREE


class TestMontage:
    """Test suite for unified Montage dataclass."""

    def test_label_montage_ti_mode(self):
        m = Montage(
            name="ti",
            mode=Montage.Mode.NET,
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")],
            eeg_net="net.csv",
        )
        assert m.simulation_mode == SimulationMode.TI
        assert m.num_pairs == 2
        assert m.is_xyz is False

    def test_label_montage_mti_mode(self):
        m = Montage(
            name="mti",
            mode=Montage.Mode.NET,
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4"), ("F3", "F4"), ("P3", "P4")],
            eeg_net="net.csv",
        )
        assert m.simulation_mode == SimulationMode.MTI
        assert m.num_pairs == 4
        assert m.is_xyz is False

    def test_mti_six_pairs(self):
        m = Montage(
            name="mti6",
            mode=Montage.Mode.NET,
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
        m = Montage(
            name="bad",
            mode=Montage.Mode.NET,
            electrode_pairs=[("Cz", "Oz")],
            eeg_net="net.csv",
        )
        with pytest.raises(ValueError, match="Invalid number of electrode pairs"):
            _ = m.simulation_mode

    def test_flex_mapped_is_not_xyz(self):
        m = Montage(
            name="fm",
            mode=Montage.Mode.FLEX_MAPPED,
            electrode_pairs=[("E1", "E2"), ("E3", "E4")],
            eeg_net="GSN-256.csv",
        )
        assert m.is_xyz is False

    def test_flex_opt_is_xyz(self):
        m = Montage(
            name="xyz",
            mode=Montage.Mode.FLEX_FREE,
            electrode_pairs=[
                ([0.0, 0.0, 100.0], [0.0, 0.0, -100.0]),
                ([50.0, 0.0, 0.0], [-50.0, 0.0, 0.0]),
            ],
        )
        assert m.is_xyz is True
        assert m.simulation_mode == SimulationMode.TI

    def test_freehand_is_xyz(self):
        m = Montage(
            name="fh",
            mode=Montage.Mode.FREEHAND,
            electrode_pairs=[
                ([0.0, 0.0, 100.0], [0.0, 0.0, -100.0]),
                ([50.0, 0.0, 0.0], [-50.0, 0.0, 0.0]),
            ],
        )
        assert m.is_xyz is True

    def test_eeg_net_default_none(self):
        m = Montage(
            name="test",
            mode=Montage.Mode.FLEX_FREE,
            electrode_pairs=[("a", "b"), ("c", "d")],
        )
        assert m.eeg_net is None


class TestParseIntensities:
    """Test suite for parse_intensities helper function."""

    def test_single_value(self):
        assert parse_intensities("2.0") == [2.0, 2.0]

    def test_two_values(self):
        assert parse_intensities("2.0,1.5") == [2.0, 1.5]

    def test_four_values(self):
        assert parse_intensities("2.0,1.5,1.0,0.5") == [2.0, 1.5, 1.0, 0.5]

    def test_six_values(self):
        assert parse_intensities("1.0,2.0,3.0,4.0,5.0,6.0") == [
            1.0,
            2.0,
            3.0,
            4.0,
            5.0,
            6.0,
        ]

    def test_eight_values(self):
        result = parse_intensities("1,2,3,4,5,6,7,8")
        assert len(result) == 8

    def test_with_spaces(self):
        assert parse_intensities("2.0 , 1.5") == [2.0, 1.5]

    def test_invalid_three_values(self):
        with pytest.raises(ValueError, match="Invalid intensity format"):
            parse_intensities("2.0,1.5,1.0")

    def test_invalid_five_values(self):
        with pytest.raises(ValueError, match="Invalid intensity format"):
            parse_intensities("2.0,2.0,1.5,1.5,1.0")

    def test_invalid_empty(self):
        with pytest.raises(ValueError):
            parse_intensities("")

    def test_invalid_non_numeric(self):
        with pytest.raises(ValueError):
            parse_intensities("abc")


class TestSimulationConfig:
    """Test suite for SimulationConfig dataclass."""

    def test_basic_creation(self):
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            montages=[],
            conductivity="dir",
        )
        assert config.subject_id == "001"
        assert config.conductivity == "dir"
        assert config.intensities == [1.0, 1.0]

    def test_default_values(self):
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            montages=[],
        )
        assert config.conductivity == "scalar"
        assert config.electrode_shape == "ellipse"
        assert config.electrode_dimensions == [8.0, 8.0]
        assert config.gel_thickness == 4.0
        assert config.rubber_thickness == 2.0

    def test_default_mapping_options(self):
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            montages=[],
        )
        assert config.map_to_surf is True
        assert config.map_to_vol is False
        assert config.map_to_mni is False
        assert config.map_to_fsavg is False

    def test_custom_electrode_fields(self):
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            montages=[],
            electrode_shape="rect",
            electrode_dimensions=[10.0, 12.0],
            gel_thickness=5.0,
            rubber_thickness=3.0,
        )
        assert config.electrode_shape == "rect"
        assert config.electrode_dimensions == [10.0, 12.0]
        assert config.gel_thickness == 5.0
        assert config.rubber_thickness == 3.0

    def test_invalid_conductivity_rejected(self):
        with pytest.raises(ValueError, match="Invalid conductivity"):
            SimulationConfig(
                subject_id="001",
                project_dir="/path/to/project",
                montages=[],
                conductivity="invalid",
            )

    def test_valid_conductivities(self):
        for cond in ("scalar", "vn", "dir", "mc"):
            config = SimulationConfig(
                subject_id="001",
                project_dir="/path/to/project",
                montages=[],
                conductivity=cond,
            )
            assert config.conductivity == cond

    def test_with_montages(self):
        m = Montage(
            name="test",
            mode=Montage.Mode.NET,
            electrode_pairs=[("C3", "C4"), ("F3", "F4")],
            eeg_net="net.csv",
        )
        config = SimulationConfig(
            subject_id="001",
            project_dir="/path/to/project",
            montages=[m],
        )
        assert len(config.montages) == 1
        assert config.montages[0].name == "test"


# -- get_nTI_vectors tests --


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


class TestIntensityRoundTrip:
    """Test intensities as plain list round-trip."""

    def test_round_trip(self):
        original = [2.0, 1.5, 1.0, 0.5]
        serialized = {"intensities": original}
        restored = serialized["intensities"]
        assert restored == original

    def test_round_trip_six_values(self):
        original = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        serialized = {"intensities": original}
        restored = serialized["intensities"]
        assert restored == original

    def test_round_trip_default(self):
        original = [1.0, 1.0]
        serialized = {"intensities": original}
        restored = serialized["intensities"]
        assert restored == original
