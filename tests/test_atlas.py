#!/usr/bin/env python3
"""
Unit tests for TI-Toolbox atlas module: MeshAtlasManager, constants.
"""

import os
import pytest

from tit.atlas import MeshAtlasManager
from tit.atlas.constants import BUILTIN_ATLASES, VOXEL_ATLASES, VOXEL_ATLAS_FILES


# ---------------------------------------------------------------------------
# Constants
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


@pytest.mark.unit
class TestVoxelAtlases:
    """Tests for the VOXEL_ATLASES dict and derived VOXEL_ATLAS_FILES list."""

    def test_has_five_atlases(self):
        assert len(VOXEL_ATLASES) == 5

    def test_flat_list_matches_dict_keys(self):
        assert VOXEL_ATLAS_FILES == list(VOXEL_ATLASES)

    def test_hemisphere_values_valid(self):
        for name, hemi in VOXEL_ATLASES.items():
            assert hemi in ("both", "lh", "rh"), f"Bad hemisphere for {name}"

    def test_hippo_lh_and_rh_present(self):
        assert "lh.hippoAmygLabels-T1.v22.mgz" in VOXEL_ATLASES
        assert "rh.hippoAmygLabels-T1.v22.mgz" in VOXEL_ATLASES

    def test_hippo_hemispheres_correct(self):
        assert VOXEL_ATLASES["lh.hippoAmygLabels-T1.v22.mgz"] == "lh"
        assert VOXEL_ATLASES["rh.hippoAmygLabels-T1.v22.mgz"] == "rh"

    def test_combined_atlases(self):
        for name in ("aparc.DKTatlas+aseg.mgz", "aparc.a2009s+aseg.mgz",
                      "ThalamicNuclei.v13.T1.mgz"):
            assert VOXEL_ATLASES[name] == "both"



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
