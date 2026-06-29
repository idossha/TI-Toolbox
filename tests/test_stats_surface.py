"""Tests for the fsaverage surface stats backend (``tit.stats.surface``).

scipy / nilearn are mocked in this environment, so the adjacency build and
permutation clustering can't run numerically here -- those are exercised in the
container.  What's covered: config wiring for the ``space`` option, the npz
loader (real numpy), and the runner dispatch from ``tit.stats.permutation``.
"""

import sys
from unittest.mock import MagicMock

# tit.stats.__init__ -> permutation -> engine imports scipy submodules the global
# conftest doesn't mock.  Inject them (numpy stays REAL so the loader test runs).
for _mod in ("scipy.ndimage", "scipy.stats", "scipy.sparse", "scipy.sparse.csgraph"):
    sys.modules.setdefault(_mod, MagicMock())

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from tit.stats.config import CorrelationConfig, GroupComparisonConfig  # noqa: E402

# ---------------------------------------------------------------------------
# Config: space option
# ---------------------------------------------------------------------------


class TestSurfaceConfig:
    def _corr_subjects(self):
        return [
            CorrelationConfig.Subject("001", "TI_sim", 1.0),
            CorrelationConfig.Subject("002", "TI_sim", 2.0),
            CorrelationConfig.Subject("003", "TI_sim", 3.0),
        ]

    def test_default_space_is_mni(self):
        cfg = CorrelationConfig(analysis_name="a", subjects=self._corr_subjects())
        assert cfg.space == CorrelationConfig.AnalysisSpace.MNI

    def test_fsaverage_space_accepts_valid_field(self):
        cfg = CorrelationConfig(
            analysis_name="a",
            subjects=self._corr_subjects(),
            space=CorrelationConfig.AnalysisSpace.FSAVERAGE,
            fsaverage_field="hf_max",
        )
        assert cfg.fsaverage_field == "hf_max"

    def test_fsaverage_space_rejects_unknown_field(self):
        with pytest.raises(ValueError):
            CorrelationConfig(
                analysis_name="a",
                subjects=self._corr_subjects(),
                space=CorrelationConfig.AnalysisSpace.FSAVERAGE,
                fsaverage_field="bogus",
            )

    def test_fsaverage_space_rejects_bad_spacing(self):
        with pytest.raises(ValueError):
            GroupComparisonConfig(
                analysis_name="a",
                subjects=[
                    GroupComparisonConfig.Subject("001", "TI_sim", 1),
                    GroupComparisonConfig.Subject("002", "TI_sim", 0),
                ],
                space=GroupComparisonConfig.AnalysisSpace.FSAVERAGE,
                fsaverage_spacing=4,
            )

    def test_mni_space_ignores_field_validation(self):
        # In MNI space the fsaverage_field is irrelevant and not validated.
        cfg = CorrelationConfig(
            analysis_name="a", subjects=self._corr_subjects(), fsaverage_field="bogus"
        )
        assert cfg.space == CorrelationConfig.AnalysisSpace.MNI


# ---------------------------------------------------------------------------
# Loader (real numpy)
# ---------------------------------------------------------------------------


class TestLoadGroupSurfaceData:
    def _write_cache(self, pm, sid, sim, spacing, **fields):
        from tit.source.fsaverage import _output_path

        path = _output_path(pm, sid, sim, spacing)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, subject_id=sid, simulation=sim, **fields)
        return path

    def test_stacks_subjects_in_order(self, init_pm):
        from tit.source.fsaverage import _FSAVG_NODES
        from tit.stats import surface

        n = _FSAVG_NODES[5]
        self._write_cache(init_pm, "001", "TI_sim", 5, TI_max=np.full(n, 1.0))
        self._write_cache(init_pm, "002", "TI_sim", 5, TI_max=np.full(n, 2.0))

        data, ids = surface.load_group_surface_data(
            [("001", "TI_sim"), ("002", "TI_sim")], "TI_max", 5
        )
        assert data.shape == (n, 2)
        assert ids == ["001", "002"]
        assert data[0, 0] == 1.0 and data[0, 1] == 2.0

    def test_missing_cache_raises(self, init_pm):
        from tit.stats import surface

        with pytest.raises(FileNotFoundError):
            surface.load_group_surface_data([("999", "TI_sim")], "TI_max", 5)

    def test_missing_field_raises(self, init_pm):
        from tit.source.fsaverage import _FSAVG_NODES
        from tit.stats import surface

        self._write_cache(init_pm, "001", "TI_sim", 5, TI_max=np.zeros(_FSAVG_NODES[5]))
        with pytest.raises(KeyError):
            surface.load_group_surface_data([("001", "TI_sim")], "hf_max", 5)

    def test_wrong_node_count_raises(self, init_pm):
        from tit.stats import surface

        self._write_cache(init_pm, "001", "TI_sim", 5, TI_max=np.zeros(10))
        with pytest.raises(ValueError):
            surface.load_group_surface_data([("001", "TI_sim")], "TI_max", 5)


# ---------------------------------------------------------------------------
# Dispatch from the public runners
# ---------------------------------------------------------------------------


class TestSurfaceDispatch:
    def test_correlation_dispatches_to_surface(self, monkeypatch):
        from tit.stats import permutation

        captured = {}
        monkeypatch.setattr(
            "tit.stats.surface.run_surface_correlation",
            lambda cfg, cb, stop: captured.__setitem__("cfg", cfg) or "SURFACE",
        )
        cfg = CorrelationConfig(
            analysis_name="a",
            subjects=[
                CorrelationConfig.Subject("001", "TI_sim", 1.0),
                CorrelationConfig.Subject("002", "TI_sim", 2.0),
                CorrelationConfig.Subject("003", "TI_sim", 3.0),
            ],
            space=CorrelationConfig.AnalysisSpace.FSAVERAGE,
        )
        assert permutation.run_correlation(cfg) == "SURFACE"
        assert captured["cfg"] is cfg

    def test_group_comparison_dispatches_to_surface(self, monkeypatch):
        from tit.stats import permutation

        # The MNI path is wrapped in telemetry; make track_operation a no-op CM.
        import contextlib

        monkeypatch.setattr(
            "tit.telemetry.track_operation",
            lambda *a, **k: contextlib.nullcontext(),
        )
        monkeypatch.setattr(
            "tit.stats.surface.run_surface_group_comparison",
            lambda cfg, cb, stop: "SURFACE_GROUP",
        )
        cfg = GroupComparisonConfig(
            analysis_name="a",
            subjects=[
                GroupComparisonConfig.Subject("001", "TI_sim", 1),
                GroupComparisonConfig.Subject("002", "TI_sim", 0),
            ],
            space=GroupComparisonConfig.AnalysisSpace.FSAVERAGE,
        )
        assert permutation.run_group_comparison(cfg) == "SURFACE_GROUP"
