#!/usr/bin/env python3
"""Unit tests for the field registry in tit/constants.py.

Covers the FieldSpec dataclass, FIELD_REGISTRY, and the get_field_* helpers,
plus the consumers that must stay in sync with it (VALID_FSAVG_FIELDS).
"""

import pytest

from tit import constants as const
from tit.source.config import VALID_FSAVG_FIELDS


@pytest.mark.unit
class TestFieldRegistryCompleteness:
    """Every FIELD_* module constant must be represented in FIELD_REGISTRY."""

    FIELD_CONSTANTS = (
        "FIELD_TI_MAX",
        "FIELD_MTI_MAX",
        "FIELD_TI_NORMAL",
        "FIELD_TI_AVG",
        "FIELD_HF_PEAK",
        "FIELD_HF_SAR",
    )

    def test_field_constants_are_in_registry(self):
        registry_names = {spec.name for spec in const.FIELD_REGISTRY}
        for attr in self.FIELD_CONSTANTS:
            value = getattr(const, attr)
            assert (
                value in registry_names
            ), f"{attr} ({value!r}) missing from FIELD_REGISTRY"

    def test_registry_has_exactly_six_fields(self):
        assert len(const.FIELD_REGISTRY) == 6

    def test_registry_names_match_constants_exactly(self):
        """No drift: the registry's name set equals the FIELD_* constant set."""
        registry_names = {spec.name for spec in const.FIELD_REGISTRY}
        constant_values = {getattr(const, attr) for attr in self.FIELD_CONSTANTS}
        assert registry_names == constant_values

    def test_each_field_spec_is_well_formed(self):
        for spec in const.FIELD_REGISTRY:
            assert isinstance(spec, const.FieldSpec)
            assert isinstance(spec.name, str) and spec.name
            assert isinstance(spec.label, str) and spec.label
            assert isinstance(spec.units, str) and spec.units
            assert isinstance(spec.description, str) and spec.description
            assert spec.kind in (
                const.FIELD_KIND_FUNCTIONAL,
                const.FIELD_KIND_SAFETY,
            )


@pytest.mark.unit
class TestFieldSpecNamingPreserved:
    """TI_max (2-pair, unipolar) vs mTI_max (4-pair, multipolar) naming is
    load-bearing on disk; must survive."""

    def test_ti_max_and_mti_max_are_distinct_strings(self):
        assert const.FIELD_TI_MAX == "TI_max"
        assert const.FIELD_MTI_MAX == "mTI_max"
        assert const.FIELD_TI_MAX != const.FIELD_MTI_MAX

    def test_unipolar_is_never_uppercase_max(self):
        assert const.FIELD_TI_MAX != "TI_MAX"
        assert const.FIELD_MTI_MAX != "TI_Max"

    def test_registry_contains_both_names(self):
        names = {spec.name for spec in const.FIELD_REGISTRY}
        assert "TI_max" in names
        assert "mTI_max" in names

    def test_field_selector_resolves_mti_default_to_mti_max(self, tmp_path):
        """A default (None) field request on an mTI simulation must resolve to
        FIELD_MTI_MAX == "mTI_max"; a "TI_max" request on the same sim aliases
        to it too."""
        from unittest.mock import patch

        from tit.analyzer.field_selector import select_field_file

        sim_dir = tmp_path / "Simulations" / "montage2"
        (sim_dir / "mTI" / "mesh").mkdir(parents=True)
        (sim_dir / "mTI" / "mesh" / "montage2_mTI.msh").touch()

        with patch("tit.analyzer.field_selector.get_path_manager") as mock_gpm:
            mock_gpm.return_value.simulation.return_value = str(sim_dir)
            _, default_name = select_field_file("001", "montage2", "mesh")
            _, alias_name = select_field_file("001", "montage2", "mesh", field="TI_max")

        assert default_name == const.FIELD_MTI_MAX == "mTI_max"
        assert alias_name == "mTI_max"

    def test_field_name_values_unchanged(self):
        """Pin the exact literal values so no future edit silently renames a field."""
        assert const.FIELD_TI_MAX == "TI_max"
        assert const.FIELD_MTI_MAX == "mTI_max"
        assert const.FIELD_TI_NORMAL == "TI_normal"
        assert const.FIELD_TI_AVG == "TI_avg"
        assert const.FIELD_HF_PEAK == "hf_peak"
        assert const.FIELD_HF_SAR == "hf_sar"


@pytest.mark.unit
class TestFieldRegistryLookupHelpers:
    def test_get_field_names_returns_all_in_registry_order(self):
        names = const.get_field_names()
        assert names == tuple(spec.name for spec in const.FIELD_REGISTRY)
        assert names == (
            "TI_max",
            "mTI_max",
            "TI_normal",
            "TI_avg",
            "hf_peak",
            "hf_sar",
        )

    def test_get_field_names_filters_by_kind(self):
        functional = const.get_field_names(kind=const.FIELD_KIND_FUNCTIONAL)
        safety = const.get_field_names(kind=const.FIELD_KIND_SAFETY)
        assert set(functional) == {"TI_max", "mTI_max", "TI_normal", "TI_avg"}
        assert set(safety) == {"hf_peak", "hf_sar"}
        # Partition: every field is exactly one kind.
        assert set(functional) | set(safety) == set(const.get_field_names())
        assert set(functional) & set(safety) == set()

    def test_get_field_spec_returns_matching_spec(self):
        spec = const.get_field_spec("TI_max")
        assert spec.name == "TI_max"
        assert spec.kind == const.FIELD_KIND_FUNCTIONAL

        spec = const.get_field_spec("hf_sar")
        assert spec.name == "hf_sar"
        assert spec.kind == const.FIELD_KIND_SAFETY

    def test_get_field_spec_unknown_name_raises(self):
        with pytest.raises(KeyError):
            const.get_field_spec("not_a_real_field")

    def test_get_fields_by_kind_returns_specs_not_names(self):
        safety_specs = const.get_fields_by_kind(const.FIELD_KIND_SAFETY)
        assert all(isinstance(spec, const.FieldSpec) for spec in safety_specs)
        assert {spec.name for spec in safety_specs} == {"hf_peak", "hf_sar"}


@pytest.mark.unit
class TestSafetyFieldsGuard:
    """Load-bearing guard: safety fields must never silently gain/lose members.

    A later phase must be able to rely on "safety fields == {hf_peak, hf_sar}"
    to make sure carrier-exposure safety metrics are never made optional by
    accident when new fields are added to the registry.
    """

    def test_safety_fields_are_exactly_hf_peak_and_hf_sar(self):
        safety_names = set(const.get_field_names(kind=const.FIELD_KIND_SAFETY))
        assert safety_names == {"hf_peak", "hf_sar"}

    def test_functional_fields_are_exactly_the_ti_fields(self):
        functional_names = set(const.get_field_names(kind=const.FIELD_KIND_FUNCTIONAL))
        assert functional_names == {"TI_max", "mTI_max", "TI_normal", "TI_avg"}


@pytest.mark.unit
class TestFieldRegistryTIAvg:
    """TI_avg (tit.calc.get_TI_avg) registry entry."""

    def test_ti_avg_present_and_functional(self):
        assert const.FIELD_TI_AVG == "TI_avg"
        registry_names = {spec.name for spec in const.FIELD_REGISTRY}
        assert const.FIELD_TI_AVG in registry_names
        spec = const.get_field_spec(const.FIELD_TI_AVG)
        assert spec.kind == const.FIELD_KIND_FUNCTIONAL

    def test_safety_fields_unaffected_by_ti_avg(self):
        """Adding a new functional field must not perturb the safety set."""
        safety_names = set(const.get_field_names(kind=const.FIELD_KIND_SAFETY))
        assert safety_names == {"hf_peak", "hf_sar"}


@pytest.mark.unit
class TestValidFsavgFieldsConsumer:
    """tit.source.config.VALID_FSAVG_FIELDS must derive from the registry
    without changing its historical value, order, or type."""

    def test_valid_fsavg_fields_unchanged(self):
        assert VALID_FSAVG_FIELDS == ("TI_max", "TI_normal", "hf_peak", "hf_sar")

    def test_valid_fsavg_fields_is_a_tuple_of_str(self):
        assert isinstance(VALID_FSAVG_FIELDS, tuple)
        assert all(isinstance(name, str) for name in VALID_FSAVG_FIELDS)

    def test_valid_fsavg_fields_excludes_mti_spelling(self):
        """fsaverage projection only ever emits TI_max (see tit.source.fsaverage);
        the 4-pair mesh spelling mTI_max must not appear."""
        assert const.FIELD_MTI_MAX not in VALID_FSAVG_FIELDS

    def test_valid_fsavg_fields_excludes_ti_avg(self):
        """TI_avg has no central-surface overlay to project (tit.source.fsaverage
        does not handle it); it must stay out of the fsaverage field list."""
        assert const.FIELD_TI_AVG not in VALID_FSAVG_FIELDS

    def test_valid_fsavg_fields_all_come_from_registry(self):
        registry_names = set(const.get_field_names())
        assert set(VALID_FSAVG_FIELDS).issubset(registry_names)


@pytest.mark.unit
class TestOutputFieldHelpText:
    """The output-field help must define fields, not classify them."""

    def test_help_gives_definition_equation_and_reference_per_field(self):
        defs = const.OUTPUT_FIELD_DEFINITIONS
        help_text = const.output_fields_help_text()

        selectable = set(const.SELECTABLE_OUTPUT_FIELDS)
        assert {d[0] for d in defs} == selectable
        for name, units, definition, equation, reference in defs:
            assert units and definition and equation and reference
            for part in (name, units, definition, equation, reference):
                assert part in help_text
        assert "Equation:" in help_text
        assert "Reference:" in help_text

    def test_no_functional_versus_safety_framing_in_user_facing_text(self):
        """Which fields bear on efficacy vs safety is debated; do not assert it.

        The registry still groups fields by ``kind`` for programmatic subset
        selection, but nothing the user reads may present that as a claim.
        """
        user_text = [const.output_fields_help_text()] + [
            spec.description for spec in const.FIELD_REGISTRY
        ]
        for text in user_text:
            lowered = text.lower()
            assert "safety metric" not in lowered
            assert "functional" not in lowered
