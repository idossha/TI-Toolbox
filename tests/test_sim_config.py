#!/usr/bin/env simnibs_python
"""
Unit tests for sim.config module and calc.envelope_max.

Tests configuration dataclasses for TI simulations including:
- SimulationMode enum
- MontageMode enum
- Montage dataclass (is_xyz, simulation_mode, num_pairs)
- SimulationConfig dataclass (flat fields, conductivity validation)
- parse_intensities helper function
- envelope_max for multi-channel (mTI) computation
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
from tit.calc import envelope_max


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
            montages=[],
            conductivity="dir",
        )
        assert config.subject_id == "001"
        assert config.conductivity == "dir"
        assert config.intensities == [1.0, 1.0]

    def test_default_values(self):
        config = SimulationConfig(
            subject_id="001",
            montages=[],
        )
        assert config.conductivity == "scalar"
        assert config.electrode_shape == "ellipse"
        assert config.electrode_dimensions == [8.0, 8.0]
        assert config.gel_thickness == 1.0
        assert config.rubber_thickness == 2.0

    def test_every_published_gel_default_is_one_millimetre(self):
        """The served schema is what the app's forms start from (DECISIONS 2026-10-28, gel 1 mm):
        the Simulator's, the flex electrode's and the leadfield's gel, and the Flex page's table.
        """
        import json

        schema = json.loads(
            (
                Path(__file__).resolve().parent.parent
                / "contracts"
                / "generated"
                / "config.schema.json"
            ).read_text()
        )
        defs = schema["$defs"]
        for cls in ("SimulationConfig", "ElectrodeConfig", "LeadfieldConfig"):
            assert defs[cls]["properties"]["gel_thickness"]["default"] == 1.0, cls
        for kind in ("flex", "flex_adaptive", "flex_pareto"):
            assert (
                schema["x-app-defaults"][kind]["electrode"]["gel_thickness"] == 1
            ), kind

    def test_default_mapping_options(self):
        config = SimulationConfig(
            subject_id="001",
            montages=[],
        )
        assert config.map_to_surf is True
        assert config.map_to_vol is False
        assert config.map_to_mni is False
        assert config.map_to_fsavg is True  # on by default: auto fsaverage projection

    def test_custom_electrode_fields(self):
        config = SimulationConfig(
            subject_id="001",
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
                montages=[],
                conductivity="invalid",
            )

    def test_valid_conductivities(self):
        for cond in ("scalar", "vn", "dir", "mc"):
            config = SimulationConfig(
                subject_id="001",
                montages=[],
                conductivity=cond,
            )
            assert config.conductivity == cond

    def test_default_output_fields(self):
        # docs/dev/DECISIONS.md 2026-10-30: the envelope and the two carrier fields the
        # analyzer's carrier metrics read; TI_avg and hf_power_density stay opt-in.
        config = SimulationConfig(subject_id="001", montages=[])
        assert config.output_fields == ["TI_max", "hf_peak", "hf_sar"]

    def test_carrier_only_default_is_its_carrier_fields(self):
        config = SimulationConfig(subject_id="001", montages=[], carrier_only=True)
        assert config.output_fields == ["hf_peak", "hf_sar"]

    def test_nifti_volumes_are_opt_in(self):
        config = SimulationConfig(subject_id="001", montages=[])
        assert config.map_to_vol is False and config.map_to_mni is False

    def test_mni_niftis_need_nifti_volumes(self):
        with pytest.raises(ValueError, match="needs map_to_vol"):
            SimulationConfig(subject_id="001", montages=[], map_to_mni=True)
        config = SimulationConfig(
            subject_id="001", montages=[], map_to_vol=True, map_to_mni=True
        )
        assert config.map_to_mni is True

    def test_output_fields_individually_selectable(self):
        for name in ("TI_max", "TI_avg", "hf_peak", "hf_sar"):
            config = SimulationConfig(
                subject_id="001", montages=[], output_fields=[name]
            )
            assert config.output_fields == [name]

    def test_output_fields_combination(self):
        config = SimulationConfig(
            subject_id="001",
            montages=[],
            output_fields=["TI_max", "hf_peak", "hf_sar"],
        )
        assert config.output_fields == ["TI_max", "hf_peak", "hf_sar"]

    def test_output_fields_unknown_name_rejected(self):
        with pytest.raises(ValueError, match="Invalid output field"):
            SimulationConfig(
                subject_id="001", montages=[], output_fields=["not_a_field"]
            )

    def test_output_fields_empty_rejected(self):
        with pytest.raises(ValueError, match="output_fields must not be empty"):
            SimulationConfig(subject_id="001", montages=[], output_fields=[])

    def test_carrier_only_rejects_envelope_fields(self):
        # ΔF = 0 has no envelope, so TI_max is undefined rather than zero
        with pytest.raises(ValueError, match="carrier_only has no envelope"):
            SimulationConfig(
                subject_id="001",
                montages=[],
                carrier_only=True,
                output_fields=["TI_max", "hf_peak"],
            )

    def test_carrier_only_rejects_mti(self):
        m = Montage(
            name="m",
            mode=Montage.Mode.NET,
            electrode_pairs=[("C3", "C4"), ("F3", "F4"), ("P3", "P4"), ("O1", "O2")],
            eeg_net="net.csv",
        )
        with pytest.raises(ValueError, match="two-channel TI"):
            SimulationConfig(
                subject_id="001",
                montages=[m],
                intensities=[1.0] * 4,
                carrier_only=True,
                output_fields=["hf_peak"],
            )

    def test_carrier_only_accepts_carrier_fields(self):
        config = SimulationConfig(
            subject_id="001",
            montages=[],
            carrier_only=True,
            output_fields=["hf_peak", "hf_sar"],
        )
        assert config.carrier_only

    def test_with_montages(self):
        m = Montage(
            name="test",
            mode=Montage.Mode.NET,
            electrode_pairs=[("C3", "C4"), ("F3", "F4")],
            eeg_net="net.csv",
        )
        config = SimulationConfig(
            subject_id="001",
            montages=[m],
        )
        assert len(config.montages) == 1
        assert config.montages[0].name == "test"

    def test_tissue_conductivities_default_none(self):
        config = SimulationConfig(subject_id="001", montages=[])
        assert config.tissue_conductivities is None

    def test_tissue_conductivities_int_keys_preserved(self):
        config = SimulationConfig(
            subject_id="001", montages=[], tissue_conductivities={1: 0.126, 3: 1.654}
        )
        assert config.tissue_conductivities == {1: 0.126, 3: 1.654}

    def test_tissue_conductivities_string_keys_coerced_to_int(self):
        """A config built with JSON-shaped string keys (as deserialize_config would
        pass through before its own coercion) is normalised the same way."""
        config = SimulationConfig(
            subject_id="001",
            montages=[],
            tissue_conductivities={"1": 0.126, "3": 1.654},
        )
        assert config.tissue_conductivities == {1: 0.126, 3: 1.654}
        assert all(isinstance(k, int) for k in config.tissue_conductivities)

    def test_tissue_conductivities_non_positive_rejected(self):
        with pytest.raises(ValueError, match="must be > 0"):
            SimulationConfig(
                subject_id="001", montages=[], tissue_conductivities={1: 0.0}
            )


# -- envelope_max field-count tests --


class TestGetMTIVectorsFieldCounts:
    """Test envelope_max with various field counts."""

    @pytest.fixture
    def random_fields(self):
        """Generate reproducible random (N,3) arrays."""
        rng = np.random.default_rng(42)

        def _make(n_fields, n_elements=100):
            return [rng.standard_normal((n_elements, 3)) for _ in range(n_fields)]

        return _make

    def test_six_fields_shape(self, random_fields):
        fs = random_fields(6, n_elements=50)
        result = envelope_max(fs)
        assert result.shape == (50,)

    def test_eight_fields_shape(self, random_fields):
        fs = random_fields(8, n_elements=50)
        result = envelope_max(fs)
        assert result.shape == (50,)

    def test_odd_number_raises(self, random_fields):
        with pytest.raises(ValueError, match="even number"):
            envelope_max(random_fields(3))

    def test_one_field_raises(self, random_fields):
        with pytest.raises(ValueError, match="even number"):
            envelope_max(random_fields(1))

    def test_six_fields_differ_from_four(self, random_fields):
        """Extra fields (5th & 6th) must actually contribute to the result."""
        fs6 = random_fields(6, n_elements=50)
        result_6 = envelope_max(fs6)
        result_4 = envelope_max(fs6[:4])
        assert not np.allclose(
            result_6, result_4
        ), "6-field result should differ from 4-field result"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="even number"):
            envelope_max([])


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
