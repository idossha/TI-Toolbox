"""Unit tests for tit.analyzer — AnalysisResult, atlas helpers, field selector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# AnalysisResult
# ============================================================================


@pytest.mark.unit
class TestAnalysisResult:
    def test_analysis_result_construction(self):
        from tit.analyzer.analyzer import AnalysisResult

        result = AnalysisResult(
            field_name="TI_max",
            region_name="precentral-lh",
            space="mesh",
            analysis_type="spherical",
            roi_mean=0.25,
            roi_max=0.50,
            roi_min=0.01,
            roi_focality=1.5,
            gm_mean=0.17,
            gm_max=0.48,
            n_elements=1200,
            total_area_or_volume=34.5,
        )

        assert result.field_name == "TI_max"
        assert result.region_name == "precentral-lh"
        assert result.space == "mesh"
        assert result.analysis_type == "spherical"
        assert result.roi_mean == 0.25
        assert result.roi_max == 0.50
        assert result.roi_min == 0.01
        assert result.roi_focality == 1.5
        assert result.gm_mean == 0.17
        assert result.gm_max == 0.48
        assert result.n_elements == 1200
        assert result.total_area_or_volume == 34.5
        # Optional fields default to None / 0
        assert result.normal_mean is None
        assert result.normal_max is None
        assert result.normal_focality is None
        assert result.percentile_95 is None
        assert result.percentile_99 is None
        assert result.percentile_99_9 is None
        assert result.focality_50_area is None
        assert result.focality_75_area is None
        assert result.focality_90_area is None
        assert result.focality_95_area is None


# ============================================================================
# Atlas functions
# ============================================================================


@pytest.mark.unit
class TestAtlasFunctions:
    def test_list_atlases_builtins(self):
        from tit.atlas import MeshAtlasManager

        mgr = MeshAtlasManager(seg_dir="")
        atlases = mgr.list_atlases()
        assert "DK40" in atlases
        assert "a2009s" in atlases
        assert "HCP_MMP1" in atlases
        assert len(atlases) == 3


# ============================================================================
# Field selector (mocked filesystem)
# ============================================================================


@pytest.mark.unit
class TestFieldSelector:
    """Tests for select_field_file with mocked PathManager and filesystem."""

    def _make_mock_pm(self, sim_dir: str):
        mock_pm = MagicMock()
        mock_pm.simulation.return_value = sim_dir
        return mock_pm

    @patch("tit.analyzer.field_selector.get_path_manager")
    def test_select_field_file_ti_mesh(self, mock_get_pm, tmp_path):
        """When mTI/mesh dir does NOT exist, returns TI field."""
        from tit.analyzer.field_selector import select_field_file

        sim_dir = tmp_path / "sim"
        ti_mesh_dir = sim_dir / "TI" / "mesh"
        ti_mesh_dir.mkdir(parents=True)
        mesh_file = ti_mesh_dir / "montage1_TI.msh"
        mesh_file.touch()

        mock_pm = self._make_mock_pm(str(sim_dir))
        mock_get_pm.return_value = mock_pm

        path, field_name = select_field_file("001", "montage1", "mesh")

        assert path == mesh_file
        assert field_name == "TI_max"

    @patch("tit.analyzer.field_selector.get_path_manager")
    def test_select_field_file_mti_mesh(self, mock_get_pm, tmp_path):
        """When mTI/mesh dir exists, returns mTI field."""
        from tit.analyzer.field_selector import select_field_file

        sim_dir = tmp_path / "sim"
        mti_mesh_dir = sim_dir / "mTI" / "mesh"
        mti_mesh_dir.mkdir(parents=True)
        mesh_file = mti_mesh_dir / "montage1_mTI.msh"
        mesh_file.touch()

        mock_pm = self._make_mock_pm(str(sim_dir))
        mock_get_pm.return_value = mock_pm

        path, field_name = select_field_file("001", "montage1", "mesh")

        assert path == mesh_file
        assert field_name == "TI_Max"
