#!/usr/bin/env python3
"""
Unit tests for tit/constants.py

Validates structure and types of all public constant collections.
"""

import pytest

from tit import constants as const


@pytest.mark.unit
class TestTissueProperties:
    def test_tissue_properties_structure(self):
        """TISSUE_PROPERTIES is a list of dicts, each with 'name' and 'conductivity'."""
        assert isinstance(const.TISSUE_PROPERTIES, list)
        assert len(const.TISSUE_PROPERTIES) > 0
        for entry in const.TISSUE_PROPERTIES:
            assert isinstance(entry, dict)
            assert "name" in entry, f"Missing 'name' key in {entry}"
            assert "conductivity" in entry, f"Missing 'conductivity' key in {entry}"
            assert isinstance(entry["name"], str)
            assert isinstance(entry["conductivity"], (int, float))
            assert entry["conductivity"] > 0


@pytest.mark.unit
class TestEegNets:
    def test_eeg_nets_structure(self):
        """EEG_NETS is a list of dicts with 'value', 'label', 'electrode_count'."""
        assert isinstance(const.EEG_NETS, list)
        assert len(const.EEG_NETS) > 0
        for entry in const.EEG_NETS:
            assert isinstance(entry, dict)
            assert "value" in entry
            assert "label" in entry
            assert "electrode_count" in entry
            assert isinstance(entry["value"], str)
            assert isinstance(entry["label"], str)
            assert isinstance(entry["electrode_count"], int)
            assert entry["electrode_count"] > 0


@pytest.mark.unit
class TestValidationBounds:
    def test_validation_bounds_keys(self):
        """VALIDATION_BOUNDS has expected keys like 'radius', 'current_mA', etc."""
        assert isinstance(const.VALIDATION_BOUNDS, dict)
        expected_keys = {"radius", "coordinates", "current_mA", "max_iterations"}
        assert expected_keys.issubset(
            const.VALIDATION_BOUNDS.keys()
        ), f"Missing keys: {expected_keys - const.VALIDATION_BOUNDS.keys()}"
        for key, bounds in const.VALIDATION_BOUNDS.items():
            assert "min" in bounds, f"Missing 'min' in VALIDATION_BOUNDS[{key!r}]"
            assert "max" in bounds, f"Missing 'max' in VALIDATION_BOUNDS[{key!r}]"
            assert bounds["min"] < bounds["max"]


@pytest.mark.unit
class TestDefaultElectrode:
    def test_default_electrode_keys(self):
        """DEFAULT_ELECTRODE has shape, dimensions, gel_thickness, and rubber_thickness."""
        assert isinstance(const.DEFAULT_ELECTRODE, dict)
        assert "shape" in const.DEFAULT_ELECTRODE
        assert "dimensions" in const.DEFAULT_ELECTRODE
        assert "gel_thickness" in const.DEFAULT_ELECTRODE
        assert "rubber_thickness" in const.DEFAULT_ELECTRODE
        assert isinstance(const.DEFAULT_ELECTRODE["shape"], str)
        assert isinstance(const.DEFAULT_ELECTRODE["dimensions"], list)
        assert isinstance(const.DEFAULT_ELECTRODE["gel_thickness"], (int, float))
        assert isinstance(const.DEFAULT_ELECTRODE["rubber_thickness"], (int, float))


@pytest.mark.unit
class TestDefaultOptimization:
    def test_default_optimization_keys(self):
        """DEFAULT_OPTIMIZATION has expected keys."""
        assert isinstance(const.DEFAULT_OPTIMIZATION, dict)
        expected = {
            "max_iterations",
            "population_size",
            "tolerance",
            "mutation_min",
            "mutation_max",
            "recombination",
            "current_mA",
            "n_multistart",
        }
        assert expected.issubset(
            const.DEFAULT_OPTIMIZATION.keys()
        ), f"Missing: {expected - const.DEFAULT_OPTIMIZATION.keys()}"


@pytest.mark.unit
class TestFieldNameConstants:
    def test_field_name_constants(self):
        """FIELD_TI_MAX, FIELD_MTI_MAX, FIELD_TI_NORMAL are non-empty strings."""
        for attr in ("FIELD_TI_MAX", "FIELD_MTI_MAX", "FIELD_TI_NORMAL"):
            value = getattr(const, attr)
            assert isinstance(value, str), f"{attr} should be str"
            assert len(value) > 0, f"{attr} should be non-empty"


@pytest.mark.unit
class TestTissueTagConstants:
    def test_tissue_tag_constants(self):
        """WM_TISSUE_TAG and GM_TISSUE_TAG are positive ints."""
        assert isinstance(const.WM_TISSUE_TAG, int)
        assert isinstance(const.GM_TISSUE_TAG, int)
        assert const.WM_TISSUE_TAG > 0
        assert const.GM_TISSUE_TAG > 0
        assert const.WM_TISSUE_TAG != const.GM_TISSUE_TAG


@pytest.mark.unit
class TestDefaultPercentiles:
    def test_default_percentiles(self):
        """DEFAULT_PERCENTILES is a list of floats."""
        assert isinstance(const.DEFAULT_PERCENTILES, list)
        assert len(const.DEFAULT_PERCENTILES) > 0
        for val in const.DEFAULT_PERCENTILES:
            assert isinstance(val, (int, float))
            assert 0 < val <= 100


@pytest.mark.unit
class TestDefaultFocalityCutoffs:
    def test_default_focality_cutoffs(self):
        """DEFAULT_FOCALITY_CUTOFFS is a list of floats."""
        assert isinstance(const.DEFAULT_FOCALITY_CUTOFFS, list)
        assert len(const.DEFAULT_FOCALITY_CUTOFFS) > 0
        for val in const.DEFAULT_FOCALITY_CUTOFFS:
            assert isinstance(val, (int, float))
            assert 0 < val <= 100
