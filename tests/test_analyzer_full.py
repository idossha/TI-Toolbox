#!/usr/bin/env python3
"""
Tests for tit/analyzer/analyzer.py — Analyzer class methods.

Covers: dispatch, sphere/cortex mesh/voxel, _analyze_mesh_roi,
_analyze_voxel_roi, _load_surface_mesh, _ensure_central_surface,
_get_normal_stats, _resolve_output_dir, _maybe_transform_coords,
_field_values, _node_areas, _resolve_voxel_atlas.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# Ensure repo root is on sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ---------------------------------------------------------------------------
# Mock heavy deps that conftest doesn't cover
# ---------------------------------------------------------------------------
_mock_simnibs = MagicMock()
sys.modules.setdefault("simnibs", _mock_simnibs)
sys.modules.setdefault("simnibs.utils", MagicMock())
sys.modules.setdefault("simnibs.utils.transformations", MagicMock())

_mock_nibabel = MagicMock()
sys.modules.setdefault("nibabel", _mock_nibabel)

# matplotlib submodules needed by tit.analyzer.group (imported via __init__)
_mock_mpl = sys.modules.get("matplotlib") or MagicMock()
sys.modules.setdefault("matplotlib", _mock_mpl)
sys.modules.setdefault("matplotlib.lines", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())
sys.modules.setdefault("matplotlib.colors", MagicMock())
sys.modules.setdefault("matplotlib.patches", MagicMock())

from tit.analyzer.analyzer import Analyzer, AnalysisResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: build an Analyzer with everything mocked
# ---------------------------------------------------------------------------

def _make_analyzer(space="mesh", output_dir=None, field_path=None, field_name="TI_max"):
    """Construct an Analyzer without touching the filesystem."""
    with patch("tit.analyzer.analyzer.select_field_file",
               return_value=(field_path or Path("/fake/sim/montage1_TI.msh"), field_name)), \
         patch("tit.analyzer.analyzer.get_path_manager") as mock_gpm, \
         patch("tit.analyzer.analyzer.add_file_handler"):
        pm = MagicMock()
        mock_gpm.return_value = pm
        pm.m2m.return_value = "/fake/m2m"
        pm.logs.return_value = "/tmp/logs"
        pm.ensure.return_value = "/tmp/logs"
        pm.analysis_output_dir.return_value = "/tmp/out"
        pm.freesurfer_mri.return_value = "/fake/fs/mri"
        pm.segmentation.return_value = "/fake/seg"
        a = Analyzer("001", "sim1", space, output_dir=output_dir)
    return a


def _mock_surface(values, node_coords=None, n_nodes=None, areas=None,
                  field_name="TI_max"):
    """Return a mock surface mesh with field values and node coordinates."""
    if n_nodes is None:
        n_nodes = len(values)
    surface = MagicMock()
    field_data = MagicMock()
    field_data.value = values
    surface.field.__getitem__ = lambda self, k: field_data
    surface.field.__contains__ = lambda self, k: k == field_name
    if node_coords is None:
        node_coords = np.random.rand(n_nodes, 3) * 100
    surface.nodes.node_coord = node_coords
    if areas is None:
        areas = np.ones(n_nodes, dtype=float)
    surface.nodes_areas.return_value = areas
    return surface


# ===========================================================================
# Tests
# ===========================================================================


class TestAnalyzeSphereDispatch:
    """Lines 151-152: analyze_sphere dispatches to mesh or voxel."""

    def test_dispatch_mesh(self):
        a = _make_analyzer(space="mesh")
        a._sphere_mesh = MagicMock(return_value="mesh_result")
        result = a.analyze_sphere((0, 0, 0), 10.0)
        a._sphere_mesh.assert_called_once_with((0, 0, 0), 10.0, "subject", False)
        assert result == "mesh_result"

    def test_dispatch_voxel(self):
        a = _make_analyzer(space="voxel")
        a._sphere_voxel = MagicMock(return_value="voxel_result")
        result = a.analyze_sphere((1, 2, 3), 5.0, coordinate_space="MNI", visualize=True)
        a._sphere_voxel.assert_called_once_with((1, 2, 3), 5.0, "MNI", True)
        assert result == "voxel_result"


class TestAnalyzeCortexDispatch:
    """Lines 171-172: analyze_cortex dispatches to mesh or voxel."""

    def test_dispatch_mesh(self):
        a = _make_analyzer(space="mesh")
        a._cortex_mesh = MagicMock(return_value="cortex_mesh")
        result = a.analyze_cortex("DK40", "precentral-lh")
        a._cortex_mesh.assert_called_once_with("DK40", "precentral-lh", False)
        assert result == "cortex_mesh"

    def test_dispatch_voxel(self):
        a = _make_analyzer(space="voxel")
        a._cortex_voxel = MagicMock(return_value="cortex_voxel")
        result = a.analyze_cortex("HCP_MMP1", "V1", visualize=True)
        a._cortex_voxel.assert_called_once_with("HCP_MMP1", "V1", True)
        assert result == "cortex_voxel"


class TestSphereMesh:
    """Lines 185-196: _sphere_mesh constructs mask and delegates."""

    def test_sphere_mesh_calls_analyze_mesh_roi(self):
        a = _make_analyzer(space="mesh")
        # 5 nodes; some inside sphere at origin with radius 5
        coords = np.array([
            [0, 0, 0],
            [1, 0, 0],
            [100, 100, 100],
            [2, 2, 0],
            [200, 200, 200],
        ], dtype=float)
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        surface = _mock_surface(values, node_coords=coords)

        a._load_surface_mesh = MagicMock(return_value=surface)
        a._maybe_transform_coords = MagicMock(return_value=np.array([0.0, 0.0, 0.0]))

        fake_result = MagicMock(spec=AnalysisResult)
        a._analyze_mesh_roi = MagicMock(return_value=fake_result)

        result = a._sphere_mesh((0, 0, 0), 5.0, "subject", False)

        assert result is fake_result
        call_args = a._analyze_mesh_roi.call_args
        mask = call_args[0][3]
        # nodes 0,1,3 are within 5mm of origin; 2,4 are not
        assert mask[0] and mask[1] and mask[3]
        assert not mask[2] and not mask[4]


class TestCortexMesh:
    """Lines 219-228: _cortex_mesh uses atlas mask and delegates."""

    @patch("tit.analyzer.analyzer.Analyzer._load_surface_mesh")
    def test_cortex_mesh_uses_atlas(self, mock_load):
        a = _make_analyzer(space="mesh")
        values = np.array([1.0, 2.0, 3.0, 4.0])
        surface = _mock_surface(values)
        mock_load.return_value = surface

        atlas_map = {"V1": np.array([True, False, True, False])}
        with patch("simnibs.utils.transformations.subject_atlas", return_value=atlas_map):
            fake_result = MagicMock(spec=AnalysisResult)
            a._analyze_mesh_roi = MagicMock(return_value=fake_result)
            result = a._cortex_mesh("DK40", "V1", False)

        assert result is fake_result
        call_args = a._analyze_mesh_roi.call_args
        mask = call_args[0][3]
        np.testing.assert_array_equal(mask, [True, False, True, False])


class TestSphereVoxel:
    """Lines 250-276: _sphere_voxel builds voxel mask and delegates."""

    def test_sphere_voxel_constructs_mask(self):
        a = _make_analyzer(space="voxel",
                           field_path=Path("/fake/field.nii.gz"))
        # 5x5x5 volume, positive values everywhere
        field_arr = np.ones((5, 5, 5), dtype=float) * 2.0
        affine = np.eye(4)
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)

        mock_img = MagicMock()
        mock_img.get_fdata.return_value = field_arr
        mock_img.affine = affine
        mock_img.header = header

        a._maybe_transform_coords = MagicMock(return_value=np.array([2.0, 2.0, 2.0]))
        fake_result = MagicMock(spec=AnalysisResult)
        a._analyze_voxel_roi = MagicMock(return_value=fake_result)

        with patch("nibabel.load", return_value=mock_img):
            result = a._sphere_voxel((2, 2, 2), 1.5, "subject", False)

        assert result is fake_result
        a._analyze_voxel_roi.assert_called_once()

    def test_sphere_voxel_uses_selected_tissue_mask(self):
        a = _make_analyzer(space="voxel", field_path=Path("/fake/grey_field.nii.gz"))
        a.tissue_type = "GM"
        field_arr = np.ones((3, 3, 3), dtype=float)
        affine = np.eye(4)
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = field_arr
        mock_img.affine = affine
        mock_img.header = header

        tissue_mask = np.zeros((3, 3, 3), dtype=bool)
        tissue_mask[1, 1, 1] = True
        a._maybe_transform_coords = MagicMock(return_value=np.array([1.0, 1.0, 1.0]))
        a._voxel_tissue_mask = MagicMock(return_value=tissue_mask)
        a._analyze_voxel_roi = MagicMock(return_value=MagicMock(spec=AnalysisResult))

        with patch("nibabel.load", return_value=mock_img):
            a._sphere_voxel((1, 1, 1), 1.5, "subject", False)

        passed_mask = a._analyze_voxel_roi.call_args[0][2]
        np.testing.assert_array_equal(passed_mask, tissue_mask)


class TestVoxelTissueMask:
    def test_both_uses_union_of_gm_and_wm_masks(self):
        a = _make_analyzer(space="voxel", field_path=Path("/fake/field.nii.gz"))
        a.tissue_type = "BOTH"

        gm_img = MagicMock()
        gm_img.get_fdata.return_value = np.array([[[1.0]], [[0.0]]])
        wm_img = MagicMock()
        wm_img.get_fdata.return_value = np.array([[[0.0]], [[2.0]]])

        def _load(path):
            if str(path).endswith("grey_field.nii.gz"):
                return gm_img
            if str(path).endswith("white_field.nii.gz"):
                return wm_img
            raise AssertionError(f"Unexpected load path: {path}")

        with patch("pathlib.Path.exists", return_value=True), patch(
            "nibabel.load", side_effect=_load
        ):
            mask = a._voxel_tissue_mask(MagicMock(), (2, 1, 1), np.eye(4))

        np.testing.assert_array_equal(mask, np.array([[[True]], [[True]]]))


class TestAnalyzeMeshROI:
    """Lines 353-413: _analyze_mesh_roi computes correct statistics."""

    @patch("tit.analyzer.analyzer.save_results_csv")
    def test_basic_stats(self, mock_csv):
        a = _make_analyzer(space="mesh")
        # 4 nodes, all positive
        values = np.array([2.0, 4.0, 6.0, 8.0])
        node_areas = np.array([1.0, 1.0, 1.0, 1.0])
        mask = np.array([True, True, False, False])
        surface = _mock_surface(values)

        a._get_normal_stats = MagicMock(return_value=None)
        a._resolve_output_dir = MagicMock(return_value="/tmp/out")

        result = a._analyze_mesh_roi(
            surface, values, node_areas, mask,
            region_name="test_roi", analysis_type="spherical",
            visualize=False,
        )

        assert isinstance(result, AnalysisResult)
        # ROI is values[0:2] = [2.0, 4.0], equal weights
        assert result.roi_mean == pytest.approx(3.0)
        assert result.roi_max == pytest.approx(4.0)
        assert result.roi_min == pytest.approx(2.0)
        # GM = all positive values = [2,4,6,8], equal weights
        assert result.gm_mean == pytest.approx(5.0)
        assert result.gm_max == pytest.approx(8.0)
        assert result.roi_focality == pytest.approx(3.0 / 5.0)
        assert result.space == "mesh"
        assert result.n_elements == 2

    @patch("tit.analyzer.analyzer.save_results_csv")
    def test_with_normal_stats(self, mock_csv):
        a = _make_analyzer(space="mesh")
        values = np.array([2.0, 4.0, 6.0])
        node_areas = np.ones(3)
        mask = np.array([True, True, False])
        surface = _mock_surface(values)

        normal_stats = {"mean": 1.5, "max": 3.0, "focality": 0.8}
        a._get_normal_stats = MagicMock(return_value=normal_stats)
        a._resolve_output_dir = MagicMock(return_value="/tmp/out")

        result = a._analyze_mesh_roi(
            surface, values, node_areas, mask,
            region_name="roi", analysis_type="spherical",
        )

        assert result.normal_mean == pytest.approx(1.5)
        assert result.normal_max == pytest.approx(3.0)
        assert result.normal_focality == pytest.approx(0.8)

    @patch("tit.analyzer.analyzer.save_results_csv")
    def test_calls_visualize_when_flag_set(self, mock_csv):
        a = _make_analyzer(space="mesh")
        values = np.array([1.0, 2.0, 3.0])
        node_areas = np.ones(3)
        mask = np.array([True, True, False])
        surface = _mock_surface(values)

        a._get_normal_stats = MagicMock(return_value=None)
        a._resolve_output_dir = MagicMock(return_value="/tmp/out")
        a._visualize_mesh = MagicMock()

        a._analyze_mesh_roi(
            surface, values, node_areas, mask,
            region_name="roi", analysis_type="spherical",
            visualize=True,
        )

        a._visualize_mesh.assert_called_once()


class TestAnalyzeVoxelROI:
    """Lines 432-481: _analyze_voxel_roi computes correct statistics."""

    @patch("tit.analyzer.analyzer.save_results_csv")
    def test_basic_stats(self, mock_csv):
        a = _make_analyzer(space="voxel")
        field_arr = np.array([[[1.0, 2.0], [3.0, 4.0]],
                              [[5.0, 6.0], [7.0, 8.0]]])
        roi_mask = np.zeros_like(field_arr, dtype=bool)
        roi_mask[0, 0, 0] = True  # value 1.0
        roi_mask[0, 0, 1] = True  # value 2.0
        gm_mask = field_arr > 0
        affine = np.eye(4)
        voxel_size = np.array([1.0, 1.0, 1.0])

        a._resolve_output_dir = MagicMock(return_value="/tmp/out")

        result = a._analyze_voxel_roi(
            field_arr, roi_mask, gm_mask, affine, voxel_size,
            region_name="test_roi", analysis_type="spherical",
        )

        assert isinstance(result, AnalysisResult)
        assert result.roi_mean == pytest.approx(1.5)
        assert result.roi_max == pytest.approx(2.0)
        assert result.roi_min == pytest.approx(1.0)
        assert result.gm_mean == pytest.approx(4.5)  # mean of 1..8
        assert result.gm_max == pytest.approx(8.0)
        assert result.roi_focality == pytest.approx(1.5 / 4.5)
        assert result.space == "voxel"
        assert result.n_elements == 2
        # total volume = n_elements * voxel_vol = 2 * 1.0
        assert result.total_area_or_volume == pytest.approx(2.0)

    @patch("tit.analyzer.analyzer.save_results_csv")
    def test_calls_visualize_when_flag_set(self, mock_csv):
        a = _make_analyzer(space="voxel")
        field_arr = np.ones((2, 2, 2))
        roi_mask = np.ones_like(field_arr, dtype=bool)
        gm_mask = roi_mask.copy()
        affine = np.eye(4)
        voxel_size = np.array([1.0, 1.0, 1.0])

        a._resolve_output_dir = MagicMock(return_value="/tmp/out")
        a._visualize_voxel = MagicMock()

        a._analyze_voxel_roi(
            field_arr, roi_mask, gm_mask, affine, voxel_size,
            region_name="roi", analysis_type="spherical",
            visualize=True,
        )

        a._visualize_voxel.assert_called_once()


class TestLoadSurfaceMesh:
    """Lines 489-498: _load_surface_mesh lazy-loads and caches."""

    def test_loads_mesh_on_first_call(self):
        a = _make_analyzer(space="mesh")
        fake_mesh = MagicMock()
        a._ensure_central_surface = MagicMock(return_value=Path("/fake/central.msh"))

        with patch("simnibs.read_msh", return_value=fake_mesh) as mock_read:
            result = a._load_surface_mesh()

        assert result is fake_mesh
        mock_read.assert_called_once_with("/fake/central.msh")
        assert a._surface_mesh is fake_mesh
        assert a._surface_mesh_path == Path("/fake/central.msh")

    def test_returns_cached_on_second_call(self):
        a = _make_analyzer(space="mesh")
        cached = MagicMock()
        a._surface_mesh = cached

        result = a._load_surface_mesh()
        assert result is cached


class TestEnsureCentralSurface:
    """Lines 502-523: _ensure_central_surface generates surface if missing."""

    def test_returns_existing_surface(self, tmp_path):
        a = _make_analyzer(space="mesh",
                           field_path=tmp_path / "montage1_TI.msh")
        surfaces_dir = tmp_path / "surfaces"
        surfaces_dir.mkdir()
        central = surfaces_dir / "montage1_TI_central.msh"
        central.touch()

        result = a._ensure_central_surface()
        assert result == central

    @patch("subprocess.run")
    def test_generates_surface_when_missing(self, mock_run, tmp_path):
        a = _make_analyzer(space="mesh",
                           field_path=tmp_path / "montage1_TI.msh")
        # surfaces dir does not exist yet
        result = a._ensure_central_surface()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "msh2cortex"
        assert str(tmp_path / "montage1_TI.msh") in cmd


class TestGetNormalStats:
    """Lines 535-561: _get_normal_stats extracts normal field statistics."""

    def test_returns_none_when_no_normal_path(self):
        a = _make_analyzer(space="mesh",
                           field_path=Path("/fake/data.msh"))
        a._normal_mesh_path = MagicMock(return_value=None)
        result = a._get_normal_stats(np.array([True, False]), np.array([1.0, 1.0]))
        assert result is None

    def test_returns_none_when_path_missing(self, tmp_path):
        a = _make_analyzer(space="mesh")
        a._normal_mesh_path = MagicMock(return_value=tmp_path / "nonexistent.msh")
        result = a._get_normal_stats(np.array([True]), np.array([1.0]))
        assert result is None

    def test_returns_none_when_field_missing(self, tmp_path):
        normal_path = tmp_path / "normal.msh"
        normal_path.touch()
        a = _make_analyzer(space="mesh")
        a._normal_mesh_path = MagicMock(return_value=normal_path)

        mock_mesh = MagicMock()
        mock_mesh.field.__contains__ = lambda self, k: False
        with patch("simnibs.read_msh", return_value=mock_mesh):
            result = a._get_normal_stats(np.array([True]), np.array([1.0]))
        assert result is None

    def test_computes_stats_correctly(self, tmp_path):
        normal_path = tmp_path / "normal.msh"
        normal_path.touch()
        a = _make_analyzer(space="mesh")
        a._normal_mesh_path = MagicMock(return_value=normal_path)

        # Mock the normal mesh
        mock_mesh = MagicMock()
        mock_mesh.field.__contains__ = lambda self, k: k == "TI_normal"
        field_data = MagicMock()
        field_data.value = np.array([2.0, 4.0, 6.0])
        mock_mesh.field.__getitem__ = lambda self, k: field_data
        mock_mesh.nodes_areas.return_value = np.array([1.0, 1.0, 1.0])

        roi_mask = np.array([True, True, False])
        node_areas = np.array([1.0, 1.0, 1.0])

        with patch("simnibs.read_msh", return_value=mock_mesh):
            result = a._get_normal_stats(roi_mask, node_areas)

        assert result is not None
        # ROI normal values: [2.0, 4.0], both positive, equal weights
        assert result["mean"] == pytest.approx(3.0)
        assert result["max"] == pytest.approx(4.0)
        # GM mean of all positive: [2,4,6] = 4.0
        assert result["focality"] == pytest.approx(3.0 / 4.0)

    def test_returns_none_when_no_positive_roi_values(self, tmp_path):
        normal_path = tmp_path / "normal.msh"
        normal_path.touch()
        a = _make_analyzer(space="mesh")
        a._normal_mesh_path = MagicMock(return_value=normal_path)

        mock_mesh = MagicMock()
        mock_mesh.field.__contains__ = lambda self, k: k == "TI_normal"
        field_data = MagicMock()
        field_data.value = np.array([-1.0, -2.0, 3.0])
        mock_mesh.field.__getitem__ = lambda self, k: field_data
        mock_mesh.nodes_areas.return_value = np.array([1.0, 1.0, 1.0])

        roi_mask = np.array([True, True, False])  # ROI values: [-1, -2]
        node_areas = np.array([1.0, 1.0, 1.0])

        with patch("simnibs.read_msh", return_value=mock_mesh):
            result = a._get_normal_stats(roi_mask, node_areas)
        assert result is None


class TestResolveOutputDir:
    """Lines 707-729: _resolve_output_dir."""

    def test_uses_explicit_output_dir(self):
        a = _make_analyzer(space="mesh", output_dir="/explicit/out")
        result = a._resolve_output_dir(analysis_type="spherical", region_name="roi")
        assert result == "/explicit/out"

    def test_spherical_passes_kwargs_to_pm(self):
        a = _make_analyzer(space="mesh")
        a._pm.analysis_output_dir.return_value = "/pm/out"
        result = a._resolve_output_dir(
            analysis_type="spherical",
            region_name="sphere_x0_y0_z0_r10",
            center=(1, 2, 3),
            radius=10,
            coordinate_space="MNI",
        )
        assert result == "/pm/out"
        call_kwargs = a._pm.analysis_output_dir.call_args[1]
        assert call_kwargs["coordinates"] == [1, 2, 3]
        assert call_kwargs["radius"] == 10
        assert call_kwargs["coordinate_space"] == "MNI"

    def test_cortical_passes_kwargs_to_pm(self):
        a = _make_analyzer(space="mesh")
        a._pm.analysis_output_dir.return_value = "/pm/cortex_out"
        result = a._resolve_output_dir(
            analysis_type="cortical",
            region_name="V1",
            atlas="DK40",
        )
        assert result == "/pm/cortex_out"
        call_kwargs = a._pm.analysis_output_dir.call_args[1]
        assert call_kwargs["region"] == "V1"
        assert call_kwargs["atlas_name"] == "DK40"


class TestMaybeTransformCoords:
    """Lines 741-747: _maybe_transform_coords."""

    def test_subject_space_passthrough(self):
        a = _make_analyzer(space="mesh")
        result = a._maybe_transform_coords((10.0, 20.0, 30.0), "subject")
        np.testing.assert_array_almost_equal(result, [10.0, 20.0, 30.0])

    def test_mni_space_calls_transform(self):
        a = _make_analyzer(space="mesh")
        with patch("simnibs.utils.transformations.mni2subject_coords",
                   return_value=np.array([[5.0, 15.0, 25.0]])) as mock_t:
            result = a._maybe_transform_coords((10.0, 20.0, 30.0), "MNI")
        mock_t.assert_called_once()
        np.testing.assert_array_almost_equal(result, [5.0, 15.0, 25.0])

    def test_mni_case_insensitive(self):
        a = _make_analyzer(space="mesh")
        with patch("simnibs.utils.transformations.mni2subject_coords",
                   return_value=np.array([[1.0, 2.0, 3.0]])):
            result = a._maybe_transform_coords((0, 0, 0), "mni")
        np.testing.assert_array_almost_equal(result, [1.0, 2.0, 3.0])


class TestFieldValues:
    """Lines 758-761: _field_values extracts scalar or vector magnitude."""

    def test_1d_field(self):
        a = _make_analyzer(space="mesh")
        surface = MagicMock()
        field = MagicMock()
        field.value = np.array([1.0, 2.0, 3.0])
        surface.field.__getitem__ = lambda self, k: field
        result = a._field_values(surface)
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])

    def test_2d_field_returns_magnitude(self):
        a = _make_analyzer(space="mesh")
        surface = MagicMock()
        field = MagicMock()
        field.value = np.array([[3.0, 4.0, 0.0], [0.0, 0.0, 5.0]])
        surface.field.__getitem__ = lambda self, k: field
        result = a._field_values(surface)
        np.testing.assert_array_almost_equal(result, [5.0, 5.0])


class TestNodeAreas:
    """Lines 766-769: _node_areas extracts from surface."""

    def test_plain_array(self):
        surface = MagicMock()
        surface.nodes_areas.return_value = np.array([1.0, 2.0, 3.0])
        result = Analyzer._node_areas(surface)
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])

    def test_value_attribute(self):
        surface = MagicMock()
        wrapper = MagicMock()
        wrapper.value = np.array([4.0, 5.0])
        surface.nodes_areas.return_value = wrapper
        result = Analyzer._node_areas(surface)
        np.testing.assert_array_equal(result, [4.0, 5.0])


class TestResolveVoxelAtlas:
    """Lines 785-800: _resolve_voxel_atlas searches for atlas files."""

    def test_direct_file_path(self, tmp_path):
        atlas_file = tmp_path / "my_atlas.nii.gz"
        atlas_file.touch()
        a = _make_analyzer(space="voxel")
        result = a._resolve_voxel_atlas(str(atlas_file))
        assert result == atlas_file

    def test_finds_mgz_in_freesurfer(self, tmp_path):
        a = _make_analyzer(space="voxel")
        a._pm.freesurfer_mri.return_value = str(tmp_path / "fs_mri")
        a._pm.segmentation.return_value = str(tmp_path / "seg")
        (tmp_path / "fs_mri").mkdir()
        mgz = tmp_path / "fs_mri" / "aparc+aseg.mgz"
        mgz.touch()
        result = a._resolve_voxel_atlas("aparc+aseg")
        assert result == mgz

    def test_finds_nii_gz_in_segmentation(self, tmp_path):
        a = _make_analyzer(space="voxel")
        a._pm.freesurfer_mri.return_value = str(tmp_path / "fs_mri")
        a._pm.segmentation.return_value = str(tmp_path / "seg")
        (tmp_path / "fs_mri").mkdir()
        (tmp_path / "seg").mkdir()
        nii = tmp_path / "seg" / "atlas.nii.gz"
        nii.touch()
        result = a._resolve_voxel_atlas("atlas")
        assert result == nii

    def test_raises_when_not_found(self, tmp_path):
        a = _make_analyzer(space="voxel")
        a._pm.freesurfer_mri.return_value = str(tmp_path / "fs_mri")
        a._pm.segmentation.return_value = str(tmp_path / "seg")
        (tmp_path / "fs_mri").mkdir()
        (tmp_path / "seg").mkdir()
        with pytest.raises(FileNotFoundError, match="Atlas file not found"):
            a._resolve_voxel_atlas("nonexistent")


class TestVisualizeMesh:
    """Lines 648-658: _visualize_mesh calls save helpers."""

    @patch("tit.analyzer.analyzer.save_histogram")
    @patch("tit.analyzer.analyzer.save_mesh_roi_overlay")
    def test_calls_save_helpers(self, mock_overlay, mock_hist):
        a = _make_analyzer(space="mesh")
        a._surface_mesh_path = Path("/fake/central.msh")
        surface = MagicMock()
        values = np.array([1.0, 2.0])
        roi_mask = np.array([True, False])
        result = MagicMock()
        result.roi_mean = 1.0

        a._visualize_mesh(
            surface, values, roi_mask, "test_roi", "/tmp/out",
            result, np.array([1.0, 2.0]), np.array([1.0, 1.0]),
            np.array([1.0]), np.array([1.0]),
        )

        mock_overlay.assert_called_once()
        mock_hist.assert_called_once()


class TestVisualizeVoxel:
    """Lines 678-688: _visualize_voxel calls save helpers."""

    @patch("tit.analyzer.analyzer.save_histogram")
    @patch("tit.analyzer.analyzer.save_nifti_roi_overlay")
    def test_calls_save_helpers(self, mock_overlay, mock_hist):
        a = _make_analyzer(space="voxel")
        field_arr = np.ones((2, 2, 2))
        roi_mask = np.ones_like(field_arr, dtype=bool)
        gm_mask = roi_mask.copy()
        affine = np.eye(4)
        result = MagicMock()
        result.roi_mean = 1.0

        a._visualize_voxel(
            field_arr, roi_mask, gm_mask, affine, "test_roi",
            "/tmp/out", result,
        )

        mock_overlay.assert_called_once()
        mock_hist.assert_called_once()
