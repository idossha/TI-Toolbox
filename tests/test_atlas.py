#!/usr/bin/env python3
"""
Unit tests for TI-Toolbox atlas module: MeshAtlasManager, builtin_regions, constants.
"""

import os
import pytest

from tit.atlas import MeshAtlasManager, builtin_regions
from tit.atlas.constants import BUILTIN_ATLASES, DK40_REGIONS


# ---------------------------------------------------------------------------
# BUILTIN_ATLASES constant
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuiltinAtlasesConstant:
    """Tests for the BUILTIN_ATLASES list."""

    def test_contains_dk40(self):
        assert "DK40" in BUILTIN_ATLASES

    def test_contains_a2009s(self):
        assert "a2009s" in BUILTIN_ATLASES

    def test_contains_hcp_mmp1(self):
        assert "HCP_MMP1" in BUILTIN_ATLASES

    def test_exactly_three_builtins(self):
        assert len(BUILTIN_ATLASES) == 3


# ---------------------------------------------------------------------------
# DK40_REGIONS constant
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDK40RegionsConstant:
    """Tests for the DK40_REGIONS list."""

    def test_dk40_has_34_regions(self):
        assert len(DK40_REGIONS) == 34

    def test_contains_precentral(self):
        assert "precentral" in DK40_REGIONS

    def test_contains_postcentral(self):
        assert "postcentral" in DK40_REGIONS

    def test_contains_superiorfrontal(self):
        assert "superiorfrontal" in DK40_REGIONS


# ---------------------------------------------------------------------------
# builtin_regions function
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuiltinRegions:
    """Tests for the builtin_regions() function."""

    def test_dk40_returns_68_regions(self):
        regions = builtin_regions("DK40")
        assert len(regions) == 68

    def test_dk40_has_lh_and_rh_variants(self):
        regions = builtin_regions("DK40")
        lh = [r for r in regions if r.endswith("-lh")]
        rh = [r for r in regions if r.endswith("-rh")]
        assert len(lh) == 34
        assert len(rh) == 34

    def test_dk40_regions_are_sorted(self):
        regions = builtin_regions("DK40")
        assert regions == sorted(regions)

    def test_dk40_case_insensitive_aliases(self):
        """DK40, DESIKAN-KILLIANY, and APARC should all return regions."""
        for name in ("DK40", "DESIKAN-KILLIANY", "APARC"):
            regions = builtin_regions(name)
            assert len(regions) == 68, f"Failed for atlas name: {name}"

    def test_unknown_atlas_returns_empty_list(self):
        regions = builtin_regions("nonexistent_atlas")
        assert regions == []

    def test_each_dk40_region_has_both_hemispheres(self):
        regions = builtin_regions("DK40")
        for base in DK40_REGIONS:
            assert f"{base}-lh" in regions
            assert f"{base}-rh" in regions


# ---------------------------------------------------------------------------
# MeshAtlasManager
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMeshAtlasManager:
    """Tests for MeshAtlasManager."""

    def test_construction(self, tmp_path):
        mgr = MeshAtlasManager(str(tmp_path))
        assert mgr.seg_dir == str(tmp_path)

    def test_list_atlases_returns_builtins_for_empty_dir(self, tmp_path):
        mgr = MeshAtlasManager(str(tmp_path))
        atlases = mgr.list_atlases()
        assert "DK40" in atlases
        assert "a2009s" in atlases
        assert "HCP_MMP1" in atlases

    def test_list_atlases_returns_sorted(self, tmp_path):
        mgr = MeshAtlasManager(str(tmp_path))
        atlases = mgr.list_atlases()
        assert atlases == sorted(atlases)

    def test_list_atlases_includes_builtins_with_three(self, tmp_path):
        mgr = MeshAtlasManager(str(tmp_path))
        atlases = mgr.list_atlases()
        # At minimum, should have the 3 builtins
        assert len(atlases) >= 3

    def test_list_atlases_discovers_custom_annot_files(self, tmp_path):
        """Custom .annot files in seg_dir are discovered as additional atlases."""
        # Create a custom annot file: lh.custom_MyAtlas.annot
        (tmp_path / "lh.custom_MyAtlas.annot").touch()
        (tmp_path / "rh.custom_MyAtlas.annot").touch()
        mgr = MeshAtlasManager(str(tmp_path))
        atlases = mgr.list_atlases()
        assert "MyAtlas" in atlases

    def test_list_atlases_does_not_duplicate_builtins(self, tmp_path):
        """If a builtin atlas name appears as a file, it should not be duplicated."""
        (tmp_path / "lh.fsavg_DK40.annot").touch()
        mgr = MeshAtlasManager(str(tmp_path))
        atlases = mgr.list_atlases()
        assert atlases.count("DK40") == 1

    def test_list_atlases_nonexistent_dir(self):
        mgr = MeshAtlasManager("/nonexistent/path")
        atlases = mgr.list_atlases()
        # Should still return builtins even with missing dir
        assert set(BUILTIN_ATLASES).issubset(set(atlases))

    def test_find_atlas_file_nonexistent_dir(self):
        mgr = MeshAtlasManager("/nonexistent/path")
        result = mgr.find_atlas_file("DK40", "lh")
        assert result is None

    def test_find_atlas_file_returns_none_when_no_match(self, tmp_path):
        mgr = MeshAtlasManager(str(tmp_path))
        result = mgr.find_atlas_file("DK40", "lh")
        assert result is None

    def test_find_all_atlases_empty_dir(self, tmp_path):
        mgr = MeshAtlasManager(str(tmp_path))
        result = mgr.find_all_atlases("lh")
        assert result == {}

    def test_find_all_atlases_nonexistent_dir(self):
        mgr = MeshAtlasManager("/nonexistent/path")
        result = mgr.find_all_atlases("lh")
        assert result == {}

    def test_find_all_atlases_discovers_annot_files(self, tmp_path):
        (tmp_path / "lh.myatlas.annot").touch()
        mgr = MeshAtlasManager(str(tmp_path))
        result = mgr.find_all_atlases("lh")
        assert "myatlas" in result
