"""Tests for tit/opt/ex/engine.py -- ExSearchEngine."""

import csv
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import tit.opt.ex.engine as engine_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def ti_mocks(monkeypatch):
    """Patch ``TI.get_field`` / ``TI.get_maxTI`` on the engine module's own
    bound reference (``tit.opt.ex.engine.TI``), not a freshly-resolved
    ``from simnibs.utils import TI_utils``.

    conftest.py installs a MagicMock into ``sys.modules`` for
    ``simnibs.utils``, but ``tit/opt/ex/engine.py`` binds ``TI`` once at
    *module import time* via ``from simnibs.utils import TI_utils as TI``.
    Re-resolving ``simnibs.utils.TI_utils`` from inside a test (as this
    file used to do) can land on a *different* mock object than the one
    the engine actually calls -- proven by an identity probe during a
    full-suite run inside the container (same code, different objects).
    Assigning attributes on that fresh, disconnected import never reaches
    the engine, so every test built on it passed vacuously: the engine ran
    against an unpatched ``MagicMock`` instead of the intended fake data.

    Patching ``engine_mod.TI`` directly targets the exact object the
    engine calls, and ``monkeypatch`` restores the originals afterwards so
    no mock state leaks into other tests.
    """
    get_field = MagicMock(name="TI.get_field")
    get_maxTI = MagicMock(name="TI.get_maxTI")
    monkeypatch.setattr(engine_mod.TI, "get_field", get_field)
    monkeypatch.setattr(engine_mod.TI, "get_maxTI", get_maxTI)
    return SimpleNamespace(get_field=get_field, get_maxTI=get_maxTI)


def _make_engine(logger=None):
    """Create an ExSearchEngine with mocked dependencies."""
    if logger is None:
        logger = MagicMock()
    from tit.opt.ex.engine import ExSearchEngine

    return ExSearchEngine(
        leadfield_hdf="/fake/leadfield.hdf5",
        roi_file="/fake/roi.csv",
        roi_name="TestROI",
        logger=logger,
    )


def _setup_engine_fields(engine):
    """Setup engine with mock leadfield/mesh data for compute_ti_field."""
    engine.leadfield = MagicMock()
    engine.idx_lf = MagicMock()
    engine.mesh = MagicMock()
    engine.roi_indices = np.array([0, 1, 2])
    engine.roi_volumes = np.array([1.0, 1.0, 1.0])
    engine.gm_indices = np.array([0, 1, 2, 3, 4])
    engine.gm_volumes = np.array([1.0, 1.0, 1.0, 1.0, 1.0])


def _make_engine_with_metric(
    metric="grossman", carrier_constraint=None, carrier_penalty_weight=0.0, logger=None
):
    """Create an ExSearchEngine with the new Phase-2 constructor kwargs."""
    if logger is None:
        logger = MagicMock()
    from tit.opt.ex.engine import ExSearchEngine

    return ExSearchEngine(
        leadfield_hdf="/fake/leadfield.hdf5",
        roi_file="/fake/roi.csv",
        roi_name="TestROI",
        logger=logger,
        metric=metric,
        carrier_constraint=carrier_constraint,
        carrier_penalty_weight=carrier_penalty_weight,
    )


# ---------------------------------------------------------------------------
# ExSearchEngine.__init__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExSearchEngineInit:
    def test_stores_attributes(self):
        engine = _make_engine()
        assert engine.leadfield_hdf == "/fake/leadfield.hdf5"
        assert engine.roi_file == "/fake/roi.csv"
        assert engine.roi_name == "TestROI"
        assert engine.leadfield is None
        assert engine.mesh is None

    def test_initial_state(self):
        engine = _make_engine()
        assert engine.idx_lf is None
        assert engine.roi_coords is None
        assert engine.roi_indices is None
        assert engine.roi_volumes is None
        assert engine.gm_indices is None
        assert engine.gm_volumes is None


# ---------------------------------------------------------------------------
# ExSearchEngine._load_leadfield
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadLeadfield:
    def test_loads_via_simnibs(self, monkeypatch):
        monkeypatch.setattr(
            engine_mod.TI,
            "load_leadfield",
            MagicMock(return_value=("lf", "mesh", "idx")),
        )

        engine = _make_engine()
        engine._load_leadfield()

        assert engine.leadfield == "lf"
        assert engine.mesh == "mesh"
        assert engine.idx_lf == "idx"
        engine_mod.TI.load_leadfield.assert_called_once_with("/fake/leadfield.hdf5")


# ---------------------------------------------------------------------------
# ExSearchEngine._load_roi_coordinates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadRoiCoordinates:
    def test_reads_csv(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        with open(roi_file, "w", newline="") as f:
            csv.writer(f).writerow([10.5, -20.3, 55.0])

        engine = _make_engine()
        engine.roi_file = str(roi_file)
        engine._load_roi_coordinates()

        assert engine.roi_coords == [10.5, -20.3, 55.0]

    def test_skips_empty_rows(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        with open(roi_file, "w") as f:
            f.write("\n\n10.5, -20.3, 55.0\n")

        engine = _make_engine()
        engine.roi_file = str(roi_file)
        engine._load_roi_coordinates()

        assert engine.roi_coords == [10.5, -20.3, 55.0]

    def test_raises_on_invalid(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        roi_file.write_text("")

        engine = _make_engine()
        engine.roi_file = str(roi_file)

        with pytest.raises(ValueError, match="No valid coordinates"):
            engine._load_roi_coordinates()

    def test_handles_extra_columns(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        with open(roi_file, "w", newline="") as f:
            csv.writer(f).writerow([10.5, -20.3, 55.0, 99.0, 88.0])

        engine = _make_engine()
        engine.roi_file = str(roi_file)
        engine._load_roi_coordinates()

        assert engine.roi_coords == [10.5, -20.3, 55.0]


# ---------------------------------------------------------------------------
# ExSearchEngine._find_roi_elements
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindRoiElements:
    def test_finds_elements_within_radius(self):
        engine = _make_engine()
        engine.roi_coords = [0.0, 0.0, 0.0]

        # Create mock mesh with baricenters
        centers = np.array(
            [
                [0.0, 0.0, 0.0],  # inside
                [1.0, 0.0, 0.0],  # inside (dist=1)
                [5.0, 0.0, 0.0],  # outside (dist=5, radius=3)
                [10.0, 0.0, 0.0],  # outside
            ]
        )
        volumes = np.array([1.0, 2.0, 3.0, 4.0])

        mesh = MagicMock()
        mesh.elements_baricenters.return_value = MagicMock(value=centers)
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_roi_elements(roi_radius=3.0)

        assert len(engine.roi_indices) == 2
        assert 0 in engine.roi_indices
        assert 1 in engine.roi_indices
        np.testing.assert_array_equal(engine.roi_volumes, [1.0, 2.0])

    def test_handles_2d_volumes(self):
        engine = _make_engine()
        engine.roi_coords = [0.0, 0.0, 0.0]

        centers = np.array([[0.0, 0.0, 0.0]])
        volumes = np.array([[1.0, 0.5]])  # 2D

        mesh = MagicMock()
        mesh.elements_baricenters.return_value = MagicMock(value=centers)
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_roi_elements(roi_radius=5.0)
        assert len(engine.roi_indices) == 1


# ---------------------------------------------------------------------------
# ExSearchEngine._find_gm_elements
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindGmElements:
    def test_finds_gm_by_tag(self):
        engine = _make_engine()

        tags = np.array([1, 2, 2, 1, 2])  # GM=2
        volumes = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        mesh = MagicMock()
        mesh.elm.tag1 = tags
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_gm_elements()

        assert len(engine.gm_indices) == 3
        np.testing.assert_array_equal(engine.gm_volumes, [2.0, 3.0, 5.0])


# ---------------------------------------------------------------------------
# ExSearchEngine.compute_ti_field
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeTiField:
    def test_computes_metrics(self, ti_mocks):
        engine = _make_engine()
        _setup_engine_fields(engine)

        # Mock TI functions to return known arrays
        ti_field = np.array([0.1, 0.2, 0.3, 0.15, 0.25])
        ti_mocks.get_field.return_value = np.zeros((5, 3))
        ti_mocks.get_maxTI.return_value = ti_field

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        # Proves the patch actually reached the engine, and that concrete
        # numerics -- not an unpatched MagicMock -- flowed through.
        assert ti_mocks.get_field.call_count == 2
        ti_mocks.get_maxTI.assert_called_once()
        assert result["TestROI_TImax_ROI"] == float(
            np.max(ti_field[engine.roi_indices])
        )
        assert result["TestROI_TImean_ROI"] == pytest.approx(
            np.average(ti_field[engine.roi_indices], weights=engine.roi_volumes)
        )
        assert result["TestROI_TImean_GM"] == pytest.approx(
            np.average(ti_field[engine.gm_indices], weights=engine.gm_volumes)
        )
        assert "TestROI_Focality" in result
        assert result["TestROI_n_elements"] == len(engine.roi_indices)
        assert result["current_ch1_mA"] == 1.0
        assert result["current_ch2_mA"] == 1.0
        # Additive Phase-2 carrier metrics (finding F4) -- present on every
        # montage, even when TI.get_field/TI.get_maxTI are mocked to zeros.
        assert "TestROI_CarrierRMS_ROI" in result
        assert "TestROI_CarrierRMS_GM" in result
        assert "TestROI_CarrierPeak_GM" in result
        assert "TestROI_CarrierPenalty" in result

    def test_empty_roi(self, ti_mocks):
        engine = _make_engine()
        _setup_engine_fields(engine)
        engine.roi_indices = np.array([], dtype=int)
        engine.roi_volumes = np.array([])

        ti_field = np.array([0.1, 0.2, 0.3, 0.15, 0.25])
        ti_mocks.get_field.return_value = np.zeros((5, 3))
        ti_mocks.get_maxTI.return_value = ti_field

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        ti_mocks.get_maxTI.assert_called_once()
        assert result["TestROI_TImax_ROI"] == 0.0
        assert result["TestROI_TImean_ROI"] == 0.0
        assert result["TestROI_Focality"] == 0.0
        assert result["TestROI_CarrierRMS_ROI"] == 0.0

    def test_zero_gm_mean(self, ti_mocks):
        engine = _make_engine()
        _setup_engine_fields(engine)
        engine.gm_indices = np.array([3, 4])
        engine.gm_volumes = np.array([1.0, 1.0])

        # All-zero GM field
        ti_field = np.array([0.1, 0.2, 0.3, 0.0, 0.0])
        ti_mocks.get_field.return_value = np.zeros((5, 3))
        ti_mocks.get_maxTI.return_value = ti_field

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        ti_mocks.get_maxTI.assert_called_once()
        assert result["TestROI_TImean_GM"] == 0.0
        assert result["TestROI_Focality"] == 0.0

    def test_empty_gm(self, ti_mocks):
        engine = _make_engine()
        _setup_engine_fields(engine)
        engine.gm_indices = np.array([], dtype=int)
        engine.gm_volumes = np.array([])

        ti_field = np.array([0.1, 0.2, 0.3])
        ti_mocks.get_field.return_value = np.zeros((3, 3))
        ti_mocks.get_maxTI.return_value = ti_field

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        ti_mocks.get_maxTI.assert_called_once()
        assert result["TestROI_TImax_ROI"] == float(np.max(ti_field))
        assert result["TestROI_TImean_GM"] == 0.0
        assert result["TestROI_Focality"] == 0.0


# ---------------------------------------------------------------------------
# ExSearchEngine.compute_ti_field -- Phase 2 carrier metrics (finding F4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCarrierMetrics:
    """Carrier-exposure metrics are additive only -- existing TImax/TImean/
    Focality/n_elements keys and values must be unaffected."""

    def test_carrier_rms_gm_matches_direction_free_formula(self, ti_mocks):
        engine = _make_engine()
        _setup_engine_fields(engine)

        ef1 = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 3.0],
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        )
        ef2 = np.array(
            [
                [0.0, 1.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 3.0, 0.0],
                [0.0, 1.0, 1.0],
                [0.0, 0.0, 0.0],
            ]
        )
        ti_mocks.get_field.side_effect = [ef1, ef2]
        ti_mocks.get_maxTI.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        assert ti_mocks.get_field.call_count == 2
        expected_power = 0.5 * (np.sum(ef1**2, axis=1) + np.sum(ef2**2, axis=1))
        expected_rms_gm = float(
            np.sqrt(np.average(expected_power, weights=engine.gm_volumes))
        )
        expected_peak_gm = float(np.sqrt(np.max(expected_power)))

        assert result["TestROI_CarrierRMS_GM"] == pytest.approx(expected_rms_gm)
        assert result["TestROI_CarrierPeak_GM"] == pytest.approx(expected_peak_gm)

    def test_carrier_rms_roi_uses_best_direction_power(self, ti_mocks):
        from tit.calc import mti_modulation_depth

        engine = _make_engine()
        _setup_engine_fields(engine)

        rng = np.random.default_rng(0)
        ef1 = rng.normal(size=(5, 3))
        ef2 = rng.normal(size=(5, 3))
        ti_mocks.get_field.side_effect = [ef1, ef2]
        ti_mocks.get_maxTI.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        assert ti_mocks.get_field.call_count == 2
        expected_P = mti_modulation_depth([ef1, ef2])["carrier_power"]
        expected_rms_roi = float(
            np.sqrt(
                np.average(expected_P[engine.roi_indices], weights=engine.roi_volumes)
            )
        )
        assert result["TestROI_CarrierRMS_ROI"] == pytest.approx(expected_rms_roi)

    def test_existing_metrics_unchanged_by_carrier_additions(self, ti_mocks):
        """Regression: TImax/TImean/GM-mean/Focality/n_elements are exactly
        what the pre-Phase-2 formula computes -- carrier metrics are
        additive only and must not perturb them."""
        engine = _make_engine()
        _setup_engine_fields(engine)

        ti_field = np.array([0.1, 0.2, 0.3, 0.15, 0.25])
        ti_mocks.get_field.return_value = np.zeros((5, 3))
        ti_mocks.get_maxTI.return_value = ti_field

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        ti_mocks.get_maxTI.assert_called_once()
        field_roi = ti_field[engine.roi_indices]
        field_gm = ti_field[engine.gm_indices]
        expected_roi_max = float(np.max(field_roi))
        expected_roi_mean = float(np.average(field_roi, weights=engine.roi_volumes))
        expected_gm_mean = float(np.average(field_gm, weights=engine.gm_volumes))
        expected_focality = expected_roi_mean / expected_gm_mean

        assert result["TestROI_TImax_ROI"] == expected_roi_max
        assert result["TestROI_TImean_ROI"] == expected_roi_mean
        assert result["TestROI_TImean_GM"] == expected_gm_mean
        assert result["TestROI_Focality"] == expected_focality
        assert result["TestROI_n_elements"] == 3

    def test_default_metric_uses_grossman_get_maxTI(self, ti_mocks):
        engine = _make_engine()  # default metric="grossman"
        _setup_engine_fields(engine)

        ti_field = np.array([0.1, 0.2, 0.3, 0.15, 0.25])
        ti_mocks.get_field.return_value = np.zeros((5, 3))
        ti_mocks.get_maxTI.return_value = ti_field

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        ti_mocks.get_maxTI.assert_called_once()
        assert result["TestROI_TImax_ROI"] == float(
            np.max(ti_field[engine.roi_indices])
        )

    def test_mti_modulation_depth_metric_routes_through_calc(self, ti_mocks):
        from tit.calc import mti_modulation_depth

        engine = _make_engine_with_metric(metric="mti_modulation_depth")
        _setup_engine_fields(engine)

        rng = np.random.default_rng(1)
        ef1 = rng.normal(size=(5, 3))
        ef2 = rng.normal(size=(5, 3))
        ti_mocks.get_field.side_effect = [ef1, ef2]
        # A sentinel value the mocked TI.get_maxTI would return if it were
        # (incorrectly) still used -- must NOT appear in the result.
        ti_mocks.get_maxTI.return_value = np.array([9.9, 9.9, 9.9, 9.9, 9.9])

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        assert ti_mocks.get_field.call_count == 2
        # "mti_modulation_depth" metric must route through tit.calc, not
        # SimNIBS's TI.get_maxTI.
        ti_mocks.get_maxTI.assert_not_called()
        expected_md = mti_modulation_depth([ef1, ef2])["md"]
        expected_roi_max = float(np.max(expected_md[engine.roi_indices]))
        assert result["TestROI_TImax_ROI"] == pytest.approx(expected_roi_max)
        assert result["TestROI_TImax_ROI"] != pytest.approx(9.9)

    def test_grossman_and_mti_modulation_depth_agree_for_k1(self, ti_mocks):
        """K=1 (2-pair standard TI) is exact for both metrics -- they
        should agree to floating-point precision on identical fields."""
        from tit.calc import get_TI_vectors

        engine_grossman = _make_engine_with_metric(metric="grossman")
        engine_md = _make_engine_with_metric(metric="mti_modulation_depth")
        _setup_engine_fields(engine_grossman)
        _setup_engine_fields(engine_md)

        rng = np.random.default_rng(2)
        ef1 = rng.normal(size=(5, 3))
        ef2 = rng.normal(size=(5, 3))

        # Mocked SimNIBS TI.get_maxTI stands in for the real function --
        # replicate its exact-closed-form output via tit.calc so the
        # "grossman" side of the comparison is meaningful.
        ti_mocks.get_field.side_effect = [ef1, ef2, ef1, ef2]
        ti_mocks.get_maxTI.return_value = np.linalg.norm(
            get_TI_vectors(ef1, ef2), axis=1
        )

        result_grossman = engine_grossman.compute_ti_field(
            "E1", "E2", 1.0, "E3", "E4", 1.0
        )
        result_md = engine_md.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        assert ti_mocks.get_field.call_count == 4
        # get_maxTI is only used by the "grossman" engine.
        ti_mocks.get_maxTI.assert_called_once()

        assert result_grossman["TestROI_TImax_ROI"] == pytest.approx(
            result_md["TestROI_TImax_ROI"], abs=1e-9
        )


# ---------------------------------------------------------------------------
# ExSearchEngine.compute_ti_field -- carrier constraint (finding F4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCarrierConstraint:
    """ExConfig.carrier_constraint / carrier_penalty_weight -- default off,
    additive CarrierPenalty key, logs every time the constraint binds."""

    def test_disabled_by_default_penalty_is_zero(self, ti_mocks):
        engine = _make_engine()  # carrier_constraint=None, weight=0.0
        _setup_engine_fields(engine)

        rng = np.random.default_rng(3)
        ef1 = rng.normal(size=(5, 3)) * 10  # deliberately large
        ef2 = rng.normal(size=(5, 3)) * 10
        ti_mocks.get_field.side_effect = [ef1, ef2]
        ti_mocks.get_maxTI.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        assert ti_mocks.get_field.call_count == 2
        # Carrier RMS is genuinely large (real numerics ran) yet the
        # penalty is still zero because the constraint is disabled.
        assert result["TestROI_CarrierRMS_GM"] > 1.0
        assert result["TestROI_CarrierPenalty"] == 0.0

    def test_binds_and_logs_when_exceeded(self, caplog, ti_mocks):
        import logging

        engine = _make_engine_with_metric(
            carrier_constraint=0.01, carrier_penalty_weight=1.0
        )
        _setup_engine_fields(engine)

        rng = np.random.default_rng(4)
        ef1 = rng.normal(size=(5, 3)) * 10  # large -> GM carrier RMS >> 0.01
        ef2 = rng.normal(size=(5, 3)) * 10
        ti_mocks.get_field.side_effect = [ef1, ef2]
        ti_mocks.get_maxTI.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])

        # tit/__init__.py calls setup_logging() at import time, which sets
        # propagate=False on the "tit" logger by design (file-only
        # logging) -- that stops propagation to the root logger where
        # caplog's default handler lives, so caplog.at_level(logger=...)
        # alone won't see it. Attach caplog's handler directly to the
        # emitting logger instead.
        carrier_logger = logging.getLogger("tit.opt.carrier")
        carrier_logger.addHandler(caplog.handler)
        carrier_logger.setLevel(logging.WARNING)
        try:
            result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)
        finally:
            carrier_logger.removeHandler(caplog.handler)

        assert ti_mocks.get_field.call_count == 2
        # Concrete numeric check that the penalty is the real quadratic
        # formula (weight * (rms - constraint) ** 2), not just "> 0".
        rms_gm = result["TestROI_CarrierRMS_GM"]
        assert rms_gm > 0.01
        assert result["TestROI_CarrierPenalty"] == pytest.approx((rms_gm - 0.01) ** 2)
        assert any("Carrier constraint bound" in r.message for r in caplog.records)

    def test_not_exceeded_gives_zero_penalty_and_no_log(self, caplog, ti_mocks):
        import logging

        engine = _make_engine_with_metric(
            carrier_constraint=1e6, carrier_penalty_weight=1.0
        )
        _setup_engine_fields(engine)

        ef1 = np.zeros((5, 3))
        ef2 = np.zeros((5, 3))
        ti_mocks.get_field.side_effect = [ef1, ef2]
        ti_mocks.get_maxTI.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])

        carrier_logger = logging.getLogger("tit.opt.carrier")
        carrier_logger.addHandler(caplog.handler)
        carrier_logger.setLevel(logging.WARNING)
        try:
            result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)
        finally:
            carrier_logger.removeHandler(caplog.handler)

        assert ti_mocks.get_field.call_count == 2
        assert result["TestROI_CarrierRMS_GM"] == 0.0
        assert result["TestROI_CarrierPenalty"] == 0.0
        assert not any("Carrier constraint bound" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# ExSearchEngine.initialize
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInitialize:
    def test_calls_all_steps(self):
        engine = _make_engine()
        engine._load_leadfield = MagicMock()
        engine._load_roi_coordinates = MagicMock()
        engine._find_roi_elements = MagicMock()
        engine._find_gm_elements = MagicMock()

        engine.initialize(roi_radius=5.0)

        engine._load_leadfield.assert_called_once()
        engine._load_roi_coordinates.assert_called_once()
        engine._find_roi_elements.assert_called_once_with(5.0)
        engine._find_gm_elements.assert_called_once()


# ---------------------------------------------------------------------------
# ExSearchEngine.run
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRun:
    def test_basic_run(self):
        engine = _make_engine()
        engine.compute_ti_field = MagicMock(
            return_value={
                "TestROI_TImax_ROI": 0.5,
                "TestROI_TImean_ROI": 0.3,
                "TestROI_TImean_GM": 0.2,
                "TestROI_Focality": 1.5,
                "TestROI_n_elements": 100,
                "current_ch1_mA": 1.0,
                "current_ch2_mA": 1.0,
            }
        )

        results = engine.run(
            e1_plus=["E1"],
            e1_minus=["E2"],
            e2_plus=["E3"],
            e2_minus=["E4"],
            current_ratios=[(1.0, 1.0)],
            all_combinations=False,
            output_dir="/tmp/out",
        )

        assert len(results) == 1
        engine.compute_ti_field.assert_called_once()

    def test_multiple_combinations(self):
        engine = _make_engine()
        engine.compute_ti_field = MagicMock(
            return_value={
                "TestROI_TImax_ROI": 0.5,
                "TestROI_TImean_ROI": 0.3,
                "TestROI_TImean_GM": 0.2,
                "TestROI_Focality": 1.5,
                "TestROI_n_elements": 100,
                "current_ch1_mA": 1.0,
                "current_ch2_mA": 1.0,
            }
        )

        results = engine.run(
            e1_plus=["E1", "E2"],
            e1_minus=["E3"],
            e2_plus=["E4"],
            e2_minus=["E5"],
            current_ratios=[(1.0, 1.0), (1.5, 0.5)],
            all_combinations=False,
            output_dir="/tmp/out",
        )

        assert len(results) == 4  # 2 electrodes * 2 ratios

    def test_empty_results_no_crash(self):
        engine = _make_engine()
        results = engine.run(
            e1_plus=[],
            e1_minus=[],
            e2_plus=[],
            e2_minus=[],
            current_ratios=[(1.0, 1.0)],
            all_combinations=False,
            output_dir="/tmp/out",
        )
        assert len(results) == 0


# ---------------------------------------------------------------------------
# ExSearchEngine._log_config_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLogConfigSummary:
    def test_logs_summary(self):
        logger = MagicMock()
        engine = _make_engine(logger=logger)
        engine._log_config_summary(
            ["E1"],
            ["E2"],
            ["E3"],
            ["E4"],
            [(1.0, 1.0)],
            False,
            1,
        )
        assert logger.info.call_count >= 3


# ---------------------------------------------------------------------------
# Static ROI CRUD methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestROICrud:
    @patch("tit.paths.get_path_manager")
    def test_get_available_rois(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "motor.csv").write_text("1,2,3")
        (roi_dir / "visual.csv").write_text("4,5,6")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        rois = ExSearchEngine.get_available_rois("001")
        assert rois == ["motor.csv", "visual.csv"]

    @patch("tit.paths.get_path_manager")
    def test_create_roi(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.create_roi("001", "motor", 10.0, -20.0, 55.0)
        assert ok is True
        assert (roi_dir / "motor.csv").exists()
        assert (roi_dir / "roi_list.txt").exists()

        # Read the CSV
        with open(roi_dir / "motor.csv") as f:
            row = list(csv.reader(f))[0]
        assert float(row[0]) == 10.0

    @patch("tit.paths.get_path_manager")
    def test_create_roi_with_csv_suffix(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.create_roi("001", "motor.csv", 10.0, -20.0, 55.0)
        assert ok is True
        assert (roi_dir / "motor.csv").exists()

    @patch("tit.paths.get_path_manager")
    def test_create_roi_no_duplicate_in_list(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir(parents=True)
        (roi_dir / "roi_list.txt").write_text("motor.csv\n")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ExSearchEngine.create_roi("001", "motor.csv", 10.0, -20.0, 55.0)
        content = (roi_dir / "roi_list.txt").read_text()
        assert content.count("motor.csv") == 1

    @patch("tit.paths.get_path_manager")
    def test_delete_roi(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "motor.csv").write_text("1,2,3")
        (roi_dir / "roi_list.txt").write_text("motor.csv\nvisual.csv\n")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.delete_roi("001", "motor")
        assert ok is True
        assert not (roi_dir / "motor.csv").exists()
        content = (roi_dir / "roi_list.txt").read_text()
        assert "motor.csv" not in content
        assert "visual.csv" in content

    @patch("tit.paths.get_path_manager")
    def test_delete_nonexistent_roi(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.delete_roi("001", "nonexistent")
        assert ok is True

    @patch("tit.paths.get_path_manager")
    def test_delete_last_roi_clears_list(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "motor.csv").write_text("1,2,3")
        (roi_dir / "roi_list.txt").write_text("motor.csv\n")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ExSearchEngine.delete_roi("001", "motor")
        content = (roi_dir / "roi_list.txt").read_text()
        assert content == ""

    @patch("tit.paths.get_path_manager")
    def test_get_roi_coordinates(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        with open(roi_dir / "motor.csv", "w", newline="") as f:
            csv.writer(f).writerow([10.5, -20.3, 55.0])

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        coords = ExSearchEngine.get_roi_coordinates("001", "motor")
        assert coords == (10.5, -20.3, 55.0)

    @patch("tit.paths.get_path_manager")
    def test_get_roi_coordinates_not_found(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        coords = ExSearchEngine.get_roi_coordinates("001", "nonexistent")
        assert coords is None

    @patch("tit.paths.get_path_manager")
    def test_get_roi_coordinates_empty_file(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "empty.csv").write_text("")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        coords = ExSearchEngine.get_roi_coordinates("001", "empty")
        assert coords is None
