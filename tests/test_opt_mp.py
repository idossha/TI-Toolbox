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
        with pytest.raises(ValueError, match="n_pairs must be an even number >= 2"):
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

    def test_save_results_records_scheme_and_frequency_plan(self, tmp_path):
        """Finding F11: n_pairs alone is ambiguous -- scheme (and, if given,
        the frequency plan) must always be recorded in the results JSON."""
        from tit.opt.config import MTIFrequencyPlan
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

        plan = MTIFrequencyPlan(f_a=[2000.0], f_b=[2020.0])
        config = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=2,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
            current_mA=2.0,
            scheme="multiband",
            frequency_plan=plan,
        )

        logger = MagicMock()
        paths = save_results(de_result, config, str(tmp_path), logger)

        with open(paths["config_json"]) as f:
            data = json.load(f)
        assert data["scheme"] == "multiband"
        assert data["frequency_plan"]["f_a"] == [2000.0]
        assert data["frequency_plan"]["f_b"] == [2020.0]

    def test_save_results_frequency_plan_none_by_default(self, tmp_path):
        from tit.opt.mp.results import save_results

        de_result = {
            "best_focality": 2.5,
            "best_montage": [("E1", "E2", 1.0)],
            "best_indices": [0, 1],
            "n_iterations": 10,
            "n_evaluations": 100,
            "convergence_success": True,
            "message": "Converged",
        }
        config = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=2,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
        )
        paths = save_results(de_result, config, str(tmp_path), MagicMock())
        with open(paths["config_json"]) as f:
            data = json.load(f)
        assert data["scheme"] == "multiband"
        assert data["frequency_plan"] is None


# ===========================================================================
# MultiPolarConfig.scheme / frequency_plan (finding F11)
# ===========================================================================


@pytest.mark.unit
class TestMultiPolarConfigScheme:
    def test_default_scheme_is_multiband(self):
        cfg = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=4,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
        )
        assert cfg.scheme == "multiband"
        assert cfg.frequency_plan is None

    def test_dual_carrier_scheme_accepted(self):
        cfg = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=4,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
            scheme="dual_carrier",
        )
        assert cfg.scheme == "dual_carrier"

    def test_rejects_unknown_scheme(self):
        with pytest.raises(ValueError, match="scheme must be"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=4,
                roi=SphericalROI(x=0, y=0, z=0, radius=10),
                scheme="bogus",
            )

    def test_rejects_odd_n_pairs(self):
        with pytest.raises(ValueError, match="n_pairs must be an even number"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=3,
                roi=SphericalROI(x=0, y=0, z=0, radius=10),
            )

    def test_frequency_plan_requires_multiband(self):
        from tit.opt.config import MTIFrequencyPlan

        plan = MTIFrequencyPlan(f_a=[2000.0, 3500.0], f_b=[2020.0, 3520.0])
        with pytest.raises(ValueError, match="only meaningful for scheme='multiband'"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=4,
                roi=SphericalROI(x=0, y=0, z=0, radius=10),
                scheme="dual_carrier",
                frequency_plan=plan,
            )

    def test_frequency_plan_must_match_pair_count(self):
        from tit.opt.config import MTIFrequencyPlan

        # n_pairs=4 -> 2 interference pairs required, but plan only has 1
        plan = MTIFrequencyPlan(f_a=[2000.0], f_b=[2020.0])
        with pytest.raises(ValueError, match="requires exactly 2"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=4,
                roi=SphericalROI(x=0, y=0, z=0, radius=10),
                scheme="multiband",
                frequency_plan=plan,
            )

    def test_frequency_plan_validates_band_separation_at_config_time(self):
        """An invalid plan (insufficient carrier-band separation) must fail
        loudly at MultiPolarConfig construction time, not silently produce
        an invalid envelope later."""
        from tit.opt.config import MTIFrequencyPlan

        # Both pairs share nearly the same mean carrier frequency -> the
        # (gap - delta_f) > f_cutoff condition is violated.
        plan = MTIFrequencyPlan(f_a=[2000.0, 2000.5], f_b=[2020.0, 2020.5])
        with pytest.raises(ValueError, match="Insufficient carrier-band separation"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=4,
                roi=SphericalROI(x=0, y=0, z=0, radius=10),
                scheme="multiband",
                frequency_plan=plan,
            )

    def test_valid_frequency_plan_accepted(self):
        from tit.opt.config import MTIFrequencyPlan

        plan = MTIFrequencyPlan(f_a=[2000.0, 3500.0], f_b=[2020.0, 3520.0])
        cfg = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=4,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
            scheme="multiband",
            frequency_plan=plan,
        )
        assert cfg.frequency_plan is plan

    def test_rejects_search_nonroi_samples_below_1(self):
        with pytest.raises(ValueError, match="search_nonroi_samples"):
            MultiPolarConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                n_pairs=2,
                roi=SphericalROI(x=0, y=0, z=0, radius=10),
                search_nonroi_samples=0,
            )

    def test_default_search_nonroi_samples(self):
        cfg = MultiPolarConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            n_pairs=2,
            roi=SphericalROI(x=0, y=0, z=0, radius=10),
        )
        assert cfg.search_nonroi_samples == 6000


# ===========================================================================
# fast_eval N>2 metric switch (finding F1)
# ===========================================================================


@pytest.mark.unit
class TestNPairMetricSwitch:
    """F1: fast_eval's N>2 path now defaults to the correct
    tit.calc.mti_modulation_depth envelope. The old tit.calc.get_nTI_vectors
    metric (measured -13%/+12% error at N=4 against time-domain ground
    truth) is reachable only via metric="recursive_ti", for comparison.
    """

    def _evaluator_and_diffs(self, n_pairs=4, n_elec=10, n_elements=100, seed=42):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(n_elec, n_elements, seed)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)
        roi_idx = np.arange(5)
        nonroi_idx = np.arange(5, n_elements)
        evaluator.setup_evaluation(
            roi_idx, np.ones(len(roi_idx)), nonroi_idx, np.ones(len(nonroi_idx))
        )
        pairs = [(2 * i, 2 * i + 1) for i in range(n_pairs)]
        diffs = evaluator.precompute_pair_diffs(pairs)
        return evaluator, diffs, roi_idx

    def test_default_metric_matches_mti_modulation_depth(self):
        from tit.calc import mti_modulation_depth

        evaluator, diffs, roi_idx = self._evaluator_and_diffs()
        currents = [0.001] * 4
        e_fields = [c * d for c, d in zip(currents, diffs)]
        expected = mti_modulation_depth(e_fields)["md"]

        metrics = evaluator.evaluate_montage_npair(diffs, currents)
        assert metrics["roi_max"] == pytest.approx(expected[roi_idx].max(), rel=1e-10)

    def test_default_metric_no_longer_matches_legacy_get_nTI_vectors(self):
        """The F1 fix: N=4 default output must differ from the old
        (wrong) get_nTI_vectors-based computation."""
        from tit.calc import get_nTI_vectors

        evaluator, diffs, roi_idx = self._evaluator_and_diffs()
        currents = [0.001] * 4
        e_fields = [c * d for c, d in zip(currents, diffs)]
        legacy_expected = np.linalg.norm(get_nTI_vectors(e_fields), axis=1)

        metrics = evaluator.evaluate_montage_npair(diffs, currents)
        assert metrics["roi_max"] != pytest.approx(
            legacy_expected[roi_idx].max(), rel=1e-6
        )

    def test_legacy_metric_still_reachable_for_comparison(self):
        """metric="recursive_ti" reproduces the old get_nTI_vectors path
        exactly -- kept reachable so the F1 error band stays checkable."""
        from tit.calc import get_nTI_vectors

        evaluator, diffs, roi_idx = self._evaluator_and_diffs()
        currents = [0.001] * 4
        e_fields = [c * d for c, d in zip(currents, diffs)]
        legacy_expected = np.linalg.norm(get_nTI_vectors(e_fields), axis=1)

        metrics = evaluator.evaluate_montage_npair(
            diffs, currents, metric="recursive_ti"
        )
        assert metrics["roi_max"] == pytest.approx(
            legacy_expected[roi_idx].max(), rel=1e-10
        )

    def test_focality_from_diffs_also_uses_correct_metric_by_default(self):
        from tit.calc import get_nTI_vectors

        evaluator, diffs, roi_idx = self._evaluator_and_diffs()
        currents = np.array([0.001] * 4)

        default_foc = evaluator.focality_from_diffs(diffs, currents)
        legacy_foc = evaluator.focality_from_diffs(
            diffs, currents, metric="recursive_ti"
        )

        assert np.isfinite(default_foc)
        assert np.isfinite(legacy_foc)
        assert default_foc != pytest.approx(legacy_foc, rel=1e-6)

    def test_two_pair_case_unaffected_by_metric_argument(self):
        """K=1 (2 electrode pairs) always uses the exact closed-form fast
        path regardless of `metric` -- unaffected by the F1 fix."""
        evaluator, _, _ = self._evaluator_and_diffs()
        pairs = [(0, 1), (2, 3)]
        diffs = evaluator.precompute_pair_diffs(pairs)
        currents = [0.001, 0.001]

        default_metrics = evaluator.evaluate_montage_npair(diffs, currents)
        legacy_metrics = evaluator.evaluate_montage_npair(
            diffs, currents, metric="recursive_ti"
        )
        assert default_metrics["roi_max"] == pytest.approx(
            legacy_metrics["roi_max"], rel=1e-10
        )

    def test_rejects_unknown_metric(self):
        evaluator, diffs, _ = self._evaluator_and_diffs()
        currents = [0.001] * 4
        with pytest.raises(ValueError, match="Unknown metric"):
            evaluator.evaluate_montage_npair(diffs, currents, metric="bogus")


# ===========================================================================
# fast_eval grouping schemes (finding F11)
# ===========================================================================


@pytest.mark.unit
class TestGroupingSchemes:
    def test_multiband_is_adjacent_grouping_noop(self):
        from tit.opt.fast_eval import SCHEME_MULTIBAND, _group_fields_for_scheme

        rng = np.random.default_rng(0)
        fields = [rng.standard_normal((10, 3)) for _ in range(4)]
        grouped = _group_fields_for_scheme(fields, SCHEME_MULTIBAND)

        assert len(grouped) == 4
        for a, b in zip(grouped, fields):
            np.testing.assert_array_equal(a, b)

    def test_dual_carrier_superposes_even_and_odd_pairs(self):
        from tit.opt.fast_eval import SCHEME_DUAL_CARRIER, _group_fields_for_scheme

        rng = np.random.default_rng(1)
        fields = [rng.standard_normal((10, 3)) for _ in range(4)]
        grouped = _group_fields_for_scheme(fields, SCHEME_DUAL_CARRIER)

        assert len(grouped) == 2
        np.testing.assert_allclose(grouped[0], fields[0] + fields[2])
        np.testing.assert_allclose(grouped[1], fields[1] + fields[3])

    def test_dual_carrier_requires_even_length(self):
        from tit.opt.fast_eval import SCHEME_DUAL_CARRIER, _group_fields_for_scheme

        fields = [np.zeros((5, 3))] * 3
        with pytest.raises(ValueError, match="even length"):
            _group_fields_for_scheme(fields, SCHEME_DUAL_CARRIER)

    def test_rejects_unknown_scheme(self):
        from tit.opt.fast_eval import _group_fields_for_scheme

        fields = [np.zeros((5, 3))] * 4
        with pytest.raises(ValueError, match="Unknown scheme"):
            _group_fields_for_scheme(fields, "bogus")

    def test_schemes_produce_different_envelopes_for_n4(self):
        """multiband (K=2, adjacent) and dual_carrier (K=1, superposed) are
        different physics (finding F11) and generally give different
        fields for the same montage."""
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(n_elec=10, n_elements=100, seed=99)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)
        evaluator.setup_evaluation(
            np.arange(5), np.ones(5), np.arange(5, 100), np.ones(95)
        )
        diffs = evaluator.precompute_pair_diffs([(0, 1), (2, 3), (4, 5), (6, 7)])
        currents = [0.001] * 4

        multiband = evaluator.evaluate_montage_npair(
            diffs, currents, scheme="multiband"
        )
        dual_carrier = evaluator.evaluate_montage_npair(
            diffs, currents, scheme="dual_carrier"
        )

        assert multiband["roi_mean"] != pytest.approx(
            dual_carrier["roi_mean"], rel=1e-6
        )

    def test_two_pair_case_both_schemes_agree(self):
        """K=1 is reached identically regardless of scheme when n_pairs=2 --
        both group down to the same two fields."""
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(n_elec=10, n_elements=100, seed=5)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)
        evaluator.setup_evaluation(
            np.arange(5), np.ones(5), np.arange(5, 100), np.ones(95)
        )
        diffs = evaluator.precompute_pair_diffs([(0, 1), (2, 3)])
        currents = [0.001, 0.001]

        multiband = evaluator.evaluate_montage_npair(
            diffs, currents, scheme="multiband"
        )
        dual_carrier = evaluator.evaluate_montage_npair(
            diffs, currents, scheme="dual_carrier"
        )
        assert multiband["roi_mean"] == pytest.approx(
            dual_carrier["roi_mean"], rel=1e-10
        )


# ===========================================================================
# fast_eval search subsampling (finding F10)
# ===========================================================================


@pytest.mark.unit
class TestSearchSubsample:
    def _build_evaluator(self, n_elements, n_roi, n_elec=20, seed=7):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(n_elec, n_elements, seed)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)

        vol_rng = np.random.default_rng(seed + 1)
        roi_idx = np.arange(0, n_roi)
        nonroi_idx = np.arange(n_roi, n_elements)
        roi_vol = vol_rng.uniform(0.5, 1.5, size=len(roi_idx))
        nonroi_vol = vol_rng.uniform(0.5, 1.5, size=len(nonroi_idx))

        evaluator.setup_evaluation(roi_idx, roi_vol, nonroi_idx, nonroi_vol)
        return evaluator

    def test_setup_requires_setup_evaluation_first(self):
        from tit.opt.fast_eval import FastTIEvaluator

        lf, mesh, idx_lf = _make_mock_leadfield(10, 100)
        evaluator = FastTIEvaluator(lf, mesh, idx_lf)
        with pytest.raises(RuntimeError, match="setup_evaluation"):
            evaluator.setup_search_subsample()

    def test_subsample_keeps_all_roi_elements(self):
        evaluator = self._build_evaluator(n_elements=8000, n_roi=300)
        evaluator.setup_search_subsample(n_nonroi_samples=1500, seed=0)

        assert len(evaluator._search_roi_pos) == 300
        assert len(evaluator.search_nonroi_indices) == 1500
        np.testing.assert_array_equal(
            evaluator._search_index[evaluator._search_roi_pos], evaluator.roi_indices
        )

    def test_subsample_clamped_to_available_nonroi(self):
        evaluator = self._build_evaluator(n_elements=1000, n_roi=300)
        # Only 700 non-ROI elements exist; asking for more should clamp,
        # not error, and should be equivalent to "no subsampling".
        evaluator.setup_search_subsample(n_nonroi_samples=10000, seed=0)
        assert len(evaluator.search_nonroi_indices) == 700

    def test_setup_evaluation_invalidates_stale_subsample(self):
        evaluator = self._build_evaluator(n_elements=8000, n_roi=300)
        evaluator.setup_search_subsample(n_nonroi_samples=1500, seed=0)
        assert evaluator._search_index is not None

        evaluator.setup_evaluation(
            np.arange(10), np.ones(10), np.arange(10, 500), np.ones(490)
        )
        assert evaluator._search_index is None

    def test_deterministic_across_calls(self):
        evaluator = self._build_evaluator(n_elements=8000, n_roi=300)
        evaluator.setup_search_subsample(n_nonroi_samples=1500, seed=0)
        first = evaluator.search_nonroi_indices.copy()

        evaluator.setup_search_subsample(n_nonroi_samples=1500, seed=0)
        second = evaluator.search_nonroi_indices.copy()

        np.testing.assert_array_equal(first, second)

    def test_subsample_focality_matches_full_mesh_within_1pct(self):
        """F10 acceptance: for >=20 random montages, the subsampled
        `focality` must match the full-mesh `focality` to <1% relative.

        Uses ``n_nonroi_samples=6000`` -- the tuned production default
        (see ``MultiPolarConfig.search_nonroi_samples``) -- against a
        moderately sized synthetic mesh (N=10,000, ~62% non-ROI sampling
        fraction) for test-suite speed. A separate one-off benchmark at
        production scale (N=100,000 synthetic elements, matching finding
        F10's measurement, ~6% sampling fraction) measured mean/worst-case
        relative error of 0.33%/0.77% across 20 random 4-pair montages
        with this same ``n_nonroi_samples=6000`` -- still comfortably
        under the 1% bar even at the harsher, more realistic fraction (a
        smaller sampling *fraction* of a larger population is a harder
        estimation problem for a fixed absolute sample size, so this test
        passing at the easier fraction here is consistent with, not a
        substitute for, that production-scale measurement). 4000 (the
        original candidate) measured 1.41% worst-case at production scale
        -- too high -- which is why the default was raised to 6000.
        """
        n_elements = 10000
        n_roi = 300
        evaluator = self._build_evaluator(n_elements=n_elements, n_roi=n_roi, n_elec=24)
        evaluator.setup_search_subsample(n_nonroi_samples=6000, seed=0)

        n_elec_usable = 23  # n_elec=24, one reserved as reference
        rel_errors = []
        for trial in range(20):
            rng_t = np.random.default_rng(2000 + trial)
            elec_idx = rng_t.choice(n_elec_usable, size=8, replace=False)
            pairs = [(int(elec_idx[i]), int(elec_idx[i + 1])) for i in range(0, 8, 2)]
            diffs = evaluator.precompute_pair_diffs(pairs)
            currents = np.full(4, 0.001)

            full_focality = evaluator.evaluate_montage_npair(diffs, currents)[
                "focality"
            ]
            search_focality = evaluator.focality_from_diffs(diffs, currents)

            assert full_focality > 0
            rel_err = abs(search_focality - full_focality) / full_focality
            rel_errors.append(rel_err)

        worst = max(rel_errors)
        assert worst < 0.01, f"worst relative error {worst:.4%} across 20 montages"

    def test_evaluate_final_matches_full_mesh_not_subsample(self):
        """evaluate_final always recomputes on the full mesh -- it must
        match evaluate_montage_npair exactly, not the (possibly biased)
        search-subsample estimate."""
        evaluator = self._build_evaluator(n_elements=8000, n_roi=300, n_elec=24)
        evaluator.setup_search_subsample(n_nonroi_samples=1500, seed=0)

        diffs = evaluator.precompute_pair_diffs([(0, 1), (2, 3), (4, 5), (6, 7)])
        currents = [0.001] * 4

        full = evaluator.evaluate_montage_npair(diffs, currents)
        final = evaluator.evaluate_final(diffs, currents)

        assert final == full
