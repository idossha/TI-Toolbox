"""Tests for multi-polar montage optimizer.

Covers: MultiPolarConfig validation, ROIResolver, FastTIEvaluator,
DE optimizer helpers, results saving, and MultiPolarResult.

numpy is real; simnibs/scipy are mocked (see conftest.py).
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.config import FlexConfig, MultiPolarConfig, MultiPolarResult

SphericalROI = FlexConfig.SphericalROI
SubcorticalROI = FlexConfig.SubcorticalROI
AtlasROI = FlexConfig.AtlasROI


# ---------------------------------------------------------------------------
# Helpers: mock mesh + leadfield
# ---------------------------------------------------------------------------


def _make_mock_mesh(n_elements=100, seed=42):
    """Create a mock mesh with barycenters, volumes, and tissue tags.

    Elements 0-49: GM (tag=2), elements 50-99: WM (tag=1).
    Barycenters are random 3D points.
    """
    rng = np.random.default_rng(seed)
    centers = rng.uniform(-80, 80, size=(n_elements, 3))
    volumes = rng.uniform(0.1, 1.0, size=n_elements)
    tags = np.array([2] * (n_elements // 2) + [1] * (n_elements // 2))

    bary_mock = MagicMock()
    bary_mock.value = centers

    vol_mock = MagicMock()
    vol_mock.value = volumes

    mesh = MagicMock()
    mesh.elements_baricenters.return_value = bary_mock
    mesh.elements_volumes_and_areas.return_value = vol_mock
    mesh.elm = SimpleNamespace(tag1=tags)

    return mesh, centers, volumes, tags


def _make_mock_leadfield(n_elec=10, n_elements=100, seed=42):
    """Create a mock leadfield array and idx_lf dict.

    Returns (leadfield, mesh, idx_lf) matching TI.load_leadfield output.
    """
    rng = np.random.default_rng(seed)
    leadfield = rng.standard_normal((n_elec - 1, n_elements, 3)).astype(np.float64)
    mesh, centers, volumes, tags = _make_mock_mesh(n_elements, seed)

    names = [f"E{i}" for i in range(n_elec)]
    idx_lf = {}
    for i, name in enumerate(names[:-1]):
        idx_lf[name] = i
    idx_lf[names[-1]] = None  # reference electrode

    return leadfield, mesh, idx_lf


# ===========================================================================
# MultiPolarConfig
# ===========================================================================


@pytest.mark.unit
class TestMultiPolarConfig:
    def test_valid_config(self):
        cfg = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=4,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
            current_mA=2.0,
        )
        assert cfg.n_pairs == 4
        assert cfg.current_mA == 2.0

    def test_rejects_n_pairs_below_2(self):
        with pytest.raises(ValueError, match="n_pairs must be >= 2"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=1,
                roi=SphericalROI(x=0, y=0, z=0),
            )

    def test_rejects_atlas_roi(self):
        with pytest.raises(ValueError, match="AtlasROI"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=2,
                roi=AtlasROI(atlas_path="/a.annot", label=1),
            )

    def test_rejects_specific_without_nonroi(self):
        with pytest.raises(ValueError, match="non_roi_method='specific'"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=2,
                roi=SphericalROI(x=0, y=0, z=0),
                non_roi_method="specific",
                non_roi=None,
            )

    def test_specific_with_nonroi_ok(self):
        cfg = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=2,
            roi=SphericalROI(x=0, y=0, z=0),
            non_roi_method="specific",
            non_roi=SphericalROI(x=50, y=50, z=50, radius=20),
        )
        assert cfg.non_roi is not None


@pytest.mark.unit
class TestMultiPolarResult:
    def test_construction(self):
        r = MultiPolarResult(
            success=True,
            output_dir="/out",
            best_focality=3.14,
            best_montage=[("E1", "E2", 1.0), ("E3", "E4", 1.0)],
            n_iterations_run=100,
        )
        assert r.success
        assert r.best_focality == 3.14
        assert len(r.best_montage) == 2
        assert r.n_iterations_run == 100


# ===========================================================================
# ROIResolver
# ===========================================================================


@pytest.mark.unit
class TestROIResolver:
    def test_spherical_roi_finds_elements(self):
        from tit.opt.roi import ROIResolver

        mesh, centers, _, tags = _make_mock_mesh(100)
        resolver = ROIResolver(mesh)

        # Place ROI at one of the GM barycenters
        target = centers[10]
        roi = SphericalROI(x=target[0], y=target[1], z=target[2], radius=15.0)
        idx, vol = resolver.resolve_roi(roi)

        assert len(idx) > 0
        assert 10 in idx  # target element should be included

    def test_spherical_roi_tissue_filter(self):
        from tit.opt.roi import ROIResolver

        mesh, centers, _, tags = _make_mock_mesh(100)
        resolver = ROIResolver(mesh)

        # Huge sphere captures everything. Default tissues="GM" for non-volumetric.
        roi = SphericalROI(x=0, y=0, z=0, radius=1000.0)
        idx, _ = resolver.resolve_roi(roi)

        # Should only contain GM elements (tags index 0-49)
        for i in idx:
            assert tags[i] == 2, f"Element {i} has tag {tags[i]}, expected GM (2)"

    def test_resolve_tissue_elements(self):
        from tit.opt.roi import ROIResolver

        mesh, _, _, tags = _make_mock_mesh(100)
        resolver = ROIResolver(mesh)

        gm_idx, gm_vol = resolver.resolve_tissue_elements("GM")
        wm_idx, wm_vol = resolver.resolve_tissue_elements("WM")
        both_idx, both_vol = resolver.resolve_tissue_elements("both")

        assert len(gm_idx) == 50
        assert len(wm_idx) == 50
        assert len(both_idx) == 100

    def test_nonroi_everything_else(self):
        from tit.opt.roi import ROIResolver

        mesh, centers, _, tags = _make_mock_mesh(100)
        resolver = ROIResolver(mesh)

        target = centers[10]
        roi = SphericalROI(x=target[0], y=target[1], z=target[2], radius=5.0)
        roi_idx, _ = resolver.resolve_roi(roi)
        nonroi_idx, _ = resolver.resolve_nonroi(roi_idx, "everything_else")

        # No overlap between ROI and non-ROI
        assert len(set(roi_idx) & set(nonroi_idx)) == 0
        # Non-ROI = all brain (GM + WM) minus ROI
        all_brain = set(np.flatnonzero(np.isin(tags, [1, 2])))
        assert set(nonroi_idx) == all_brain - set(roi_idx)

    def test_rejects_atlas_roi(self):
        from tit.opt.roi import ROIResolver

        mesh, _, _, _ = _make_mock_mesh(100)
        resolver = ROIResolver(mesh)

        roi = AtlasROI(atlas_path="/a.annot", label=1)
        with pytest.raises(ValueError, match="AtlasROI"):
            resolver.resolve_roi(roi)


# ===========================================================================
# FastTIEvaluator
# ===========================================================================


@pytest.mark.unit
class TestFastTIEvaluator:
    def test_setup_stores_indices(self):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(10, 100)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)

        roi_idx = np.array([0, 1, 2, 3, 4])
        roi_vol = np.ones(5)
        nonroi_idx = np.arange(5, 100)  # rest of brain
        nonroi_vol = np.ones(95)

        evaluator.setup_evaluation(roi_idx, roi_vol, nonroi_idx, nonroi_vol)

        assert len(evaluator.roi_indices) == 5
        assert len(evaluator.nonroi_indices) == 95

    def test_pair_field_shape(self):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(10, 100)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)

        roi_idx = np.arange(5)
        nonroi_idx = np.arange(5, 100)
        evaluator.setup_evaluation(roi_idx, np.ones(5), nonroi_idx, np.ones(95))

        E = evaluator.pair_field(0, 1, 0.001)
        assert E.shape == (100, 3)  # full mesh

    def test_precompute_pair_diffs(self):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(10, 100)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)

        evaluator.setup_evaluation(
            np.arange(5), np.ones(5), np.arange(5, 100), np.ones(95)
        )

        diffs = evaluator.precompute_pair_diffs([(0, 1), (2, 3)])
        assert len(diffs) == 2
        assert diffs[0].shape == (100, 3)  # full mesh

    def test_evaluate_montage_npair(self):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(10, 100)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)
        evaluator.setup_evaluation(
            np.arange(5), np.ones(5), np.arange(5, 100), np.ones(95)
        )

        diffs = evaluator.precompute_pair_diffs([(0, 1), (2, 3)])
        metrics = evaluator.evaluate_montage_npair(diffs, [0.001, 0.001])

        assert "focality" in metrics
        assert "roi_mean" in metrics
        assert "nonroi_mean" in metrics
        assert "roi_max" in metrics
        for v in metrics.values():
            assert np.isfinite(v)

    def test_focality_from_diffs(self):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(10, 100)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)
        evaluator.setup_evaluation(
            np.arange(5), np.ones(5), np.arange(5, 100), np.ones(95)
        )

        diffs = evaluator.precompute_pair_diffs([(0, 1), (2, 3)])
        foc = evaluator.focality_from_diffs(diffs, np.array([0.001, 0.001]))
        assert np.isfinite(foc)


@pytest.mark.unit
class TestFastTIMagnitude:
    """Test the optimized _fast_ti_magnitude against get_TI_vectors."""

    def test_matches_reference_implementation(self):
        from tit.calc import get_TI_vectors
        from tit.opt.fast_eval import _fast_ti_magnitude

        rng = np.random.default_rng(123)
        E1 = rng.standard_normal((500, 3))
        E2 = rng.standard_normal((500, 3))

        ref = np.linalg.norm(get_TI_vectors(E1, E2), axis=1)
        fast = _fast_ti_magnitude(E1, E2)

        np.testing.assert_allclose(fast, ref, rtol=1e-10)

    def test_zero_fields(self):
        from tit.opt.fast_eval import _fast_ti_magnitude

        E1 = np.zeros((10, 3))
        E2 = np.zeros((10, 3))
        result = _fast_ti_magnitude(E1, E2)
        np.testing.assert_array_equal(result, 0.0)

    def test_parallel_fields(self):
        from tit.opt.fast_eval import _fast_ti_magnitude

        # Parallel fields: E2 smaller, same direction -> regime 1
        E1 = np.tile([1.0, 0.0, 0.0], (10, 1))
        E2 = np.tile([0.3, 0.0, 0.0], (10, 1))
        result = _fast_ti_magnitude(E1, E2)
        np.testing.assert_allclose(result, 0.6, atol=1e-10)


# ===========================================================================
# DE Optimizer
# ===========================================================================


@pytest.mark.unit
class TestDEOptimizer:
    def test_repair_duplicates_fixes_collisions(self):
        from tit.opt.mp.optimizer import _repair_duplicates

        indices = np.array([0, 0, 1, 2])
        n_elec = 10
        result = _repair_duplicates(indices, n_elec)

        # All indices should be unique after repair
        assert len(set(result.tolist())) == len(result)
        # First occurrence of 0 should stay at 0
        assert result[0] == 0
        # Second was 0 (duplicate), should be reassigned to nearest unused
        assert result[1] != 0
        # All values should be valid indices
        assert all(0 <= v < n_elec for v in result)

    def test_repair_duplicates_no_duplicates(self):
        from tit.opt.mp.optimizer import _repair_duplicates

        indices = np.array([0, 1, 2, 3])
        result = _repair_duplicates(indices, 10)
        np.testing.assert_array_equal(result, indices)

    def test_repair_duplicates_all_same(self):
        from tit.opt.mp.optimizer import _repair_duplicates

        indices = np.array([5, 5, 5, 5])
        result = _repair_duplicates(indices, 10)
        assert len(set(result.tolist())) == 4

    def test_parse_mutation_tuple_string(self):
        from tit.opt.mp.optimizer import _parse_mutation

        result = _parse_mutation("0.5,1.0")
        assert result == [0.5, 1.0]

    def test_parse_mutation_scalar_string(self):
        from tit.opt.mp.optimizer import _parse_mutation

        result = _parse_mutation("0.5")
        assert result == 0.5

    def test_parse_mutation_none(self):
        from tit.opt.mp.optimizer import _parse_mutation

        result = _parse_mutation(None)
        assert result == (0.5, 1.0)


# ===========================================================================
# Results
# ===========================================================================


@pytest.mark.unit
class TestMPResults:
    def test_save_results(self, tmp_path):
        from tit.opt.mp.results import save_results

        de_result = {
            "best_focality": 2.5,
            "best_montage": [("E1", "E2", 1.0), ("E3", "E4", 1.0)],
            "best_indices": [0, 1, 2, 3],
            "n_iterations": 50,
            "n_evaluations": 1500,
            "convergence_success": True,
            "message": "Converged",
        }

        config = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=2,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
            current_mA=2.0,
            population_size=20,
            max_iterations=50,
            patience=50,
            min_electrode_distance=5.0,
        )

        logger = MagicMock()
        paths = save_results(de_result, config, str(tmp_path), logger)

        assert "config_json" in paths
        assert Path(paths["config_json"]).exists()
        assert "top_k_csv" in paths
        assert Path(paths["top_k_csv"]).exists()

        # Verify config.json content
        with open(paths["config_json"]) as f:
            data = json.load(f)
        assert data["subject_id"] == "001"
        assert data["n_pairs"] == 2
        assert data["result"]["best_focality"] == 2.5
        assert len(data["result"]["best_montage"]) == 2

        # Verify top_k.csv content
        with open(paths["top_k_csv"]) as f:
            lines = f.readlines()
        assert len(lines) == 2  # header + 1 result row
        header = lines[0].strip().split(",")
        assert "rank" in header
        assert "pair1_plus" in header
        assert "focality" in header
