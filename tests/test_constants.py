#!/usr/bin/env python3
"""
Unit tests for tit/constants.py

Validates the constants that code outside the module still reads. The
PyQt-era tables (tissue properties, EEG nets, validation bounds, default
electrode/optimisation/statistics dicts) were deleted with nothing reading
them; tests/test_stale_python_guard.py keeps them deleted.
"""

import pytest

from tit import constants as const


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
    def test_grey_matter_tag_is_simnibs_tissue_2(self):
        """SimNIBS numbers grey matter 2 (white matter 1) in every head mesh."""
        from tit.roi_confirmation import GM_TISSUE_LABEL

        assert GM_TISSUE_LABEL == 2
