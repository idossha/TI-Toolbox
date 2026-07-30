#!/usr/bin/env python3
"""Tests for tit/opt/flex/objectives.py -- custom flex-search objectives.

numpy is real in the test environment, so these exercise the actual integral
focality math and the closure's ROI/non-ROI indexing, channel averaging, lazy
volume lookup, and degenerate-input handling. SimNIBS is mocked here, so the
numerical equivalence with ``measures.integral_focality`` is asserted in-container
rather than in this suite.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# objectives.py depends only on numpy (no simnibs import), so it imports cleanly.
from tit.opt.flex.objectives import (
    integral_focality_value,
    make_integral_focality_objective,
)


@pytest.mark.unit
class TestIntegralFocalityValue:
    """The pure-function integral-focality measure."""

    def test_matches_reference_formula(self):
        e1 = np.array([0.4, 0.6, 0.5])
        e2 = np.array([0.1, 0.2, 0.1, 0.2])
        v1, v2 = 2.0, 3.0
        expected = (np.mean(e1) / v1) / np.sqrt(np.mean(e2) / v2)
        assert integral_focality_value(e1, e2, v1, v2) == pytest.approx(expected)

    def test_increases_with_roi_field(self):
        e2 = np.array([0.1, 0.1])
        low = integral_focality_value(np.array([0.3, 0.3]), e2, 1.0, 1.0)
        high = integral_focality_value(np.array([0.6, 0.6]), e2, 1.0, 1.0)
        assert high > low

    def test_decreases_with_nonroi_field(self):
        e1 = np.array([0.5, 0.5])
        focal = integral_focality_value(e1, np.array([0.05, 0.05]), 1.0, 1.0)
        diffuse = integral_focality_value(e1, np.array([0.4, 0.4]), 1.0, 1.0)
        assert focal > diffuse

    def test_zero_nonroi_stays_finite(self):
        # Denominator floor prevents division blow-up when non-ROI mean is 0.
        val = integral_focality_value(
            np.array([0.5, 0.5]), np.array([0.0, 0.0]), 1.0, 1.0
        )
        assert np.isfinite(val)


def _fake_opt(v1=2.0, v2=3.0):
    return SimpleNamespace(_vol=[v1, v2])


@pytest.mark.unit
class TestIntegralFocalityObjective:
    """The SimNIBS goal callable built by make_integral_focality_objective."""

    def test_negates_the_measure(self):
        opt = _fake_opt(v1=1.0, v2=1.0)
        objective = make_integral_focality_objective(opt)
        e1 = np.array([0.5, 0.5])
        e2 = np.array([0.1, 0.1])
        e_pp = [[e1, e2]]
        assert objective(e_pp) == pytest.approx(-integral_focality_value(e1, e2, 1.0, 1.0))

    def test_indexes_roi_then_nonroi(self):
        # Swapping ROI/non-ROI must change the result (index 0 = ROI).
        opt = make_integral_focality_objective(_fake_opt(1.0, 1.0))
        strong_roi = opt([[np.array([0.8, 0.8]), np.array([0.1, 0.1])]])
        weak_roi = opt([[np.array([0.1, 0.1]), np.array([0.8, 0.8])]])
        # More focal (strong ROI) => more negative objective.
        assert strong_roi < weak_roi

    def test_averages_multiple_channels(self):
        opt = make_integral_focality_objective(_fake_opt(1.0, 1.0))
        chan_a = [np.array([0.6, 0.6]), np.array([0.1, 0.1])]
        chan_b = [np.array([0.2, 0.2]), np.array([0.1, 0.1])]
        combined = opt([chan_a, chan_b])
        only_a = opt([chan_a])
        only_b = opt([chan_b])
        assert combined == pytest.approx((only_a + only_b) / 2)

    def test_reads_volumes_lazily(self):
        # Volumes are populated by SimNIBS after the closure is built, so the
        # closure must read opt._vol at call time, not capture it at build time.
        opt = _fake_opt(1.0, 1.0)
        objective = make_integral_focality_objective(opt)
        e_pp = [[np.array([0.5, 0.5]), np.array([0.2, 0.2])]]
        before = objective(e_pp)
        opt._vol = [4.0, 4.0]  # simulate SimNIBS's prepare step
        after = objective(e_pp)
        assert before != pytest.approx(after)

    def test_penalizes_nonfinite(self):
        # v1 = 0 makes the ratio non-finite; the objective returns a positive
        # penalty (bad for a minimizer) instead of inf/NaN.
        opt = make_integral_focality_objective(_fake_opt(v1=0.0, v2=1.0))
        result = opt([[np.array([0.5, 0.5]), np.array([0.1, 0.1])]])
        assert np.isfinite(result)
        assert result > 0
