#!/usr/bin/env python3
"""Tests for tit/opt/flex/objectives.py -- flex-search objectives and ratio search.

numpy is real in the test environment, so these exercise the actual
threshold-free focality math, the goal dispatch of ``make_objective``, the
current-split enumeration, and the ``goal_fun`` wrapper that searches the split
jointly with the electrode placement.

SimNIBS is mocked here, so ``measures.ROC`` and ``postprocess_e`` are stubbed:
numerical equivalence with SimNIBS's own measures is asserted in-container
rather than in this suite.
"""

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# objectives.py imports SimNIBS lazily *inside* its functions, so the mocked
# submodules must be resolvable from sys.modules for those imports to succeed.
for _mod_name in (
    "simnibs.optimization",
    "simnibs.optimization.tes_flex_optimization",
    "simnibs.optimization.tes_flex_optimization.measures",
    "simnibs.optimization.tes_flex_optimization.tes_flex_optimization",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

_MEASURES = sys.modules["simnibs.optimization.tes_flex_optimization.measures"]
_TFO = sys.modules["simnibs.optimization.tes_flex_optimization.tes_flex_optimization"]

from tit.opt.config import FlexConfig
from tit.opt.flex import objectives
from tit.opt.flex.objectives import (
    install_ratio_search,
    make_objective,
    ratio_levels,
    threshold_free_focality,
)

OptGoal = FlexConfig.OptGoal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat(value, n=8):
    """Constant 1-D field of *n* elements -- percentiles are then exact."""
    return np.full(n, float(value))


def _channel_field(magnitude, n_rows):
    """``(n_rows, 3)`` vector field along +x with the given magnitude."""
    field = np.zeros((n_rows, 3), dtype=float)
    field[:, 0] = magnitude
    return field


def _norm_sum(e, e2, dirvec=None, type=None):
    """Stand-in for SimNIBS ``postprocess_e``: per-row ``|e| + |e2|``.

    Keeps the linear scaling behaviour that the ratio search depends on while
    staying trivially hand-checkable.
    """
    return np.linalg.norm(e, axis=1) + np.linalg.norm(e2, axis=1)


def _make_ratio_opt(roi_mag=(1.0, 0.0), nonroi_mag=(0.0, 1.0), n_roi=8, n_nonroi=64):
    """Minimal stand-in for a prepared SimNIBS ``TesFlexOptimization``.

    ``e[channel][roi_index]`` holds the raw per-channel vector fields, matching
    what ``opt.update_field`` returns inside SimNIBS's own ``goal_fun``.
    """
    e = [
        [_channel_field(roi_mag[0], n_roi), _channel_field(nonroi_mag[0], n_nonroi)],
        [_channel_field(roi_mag[1], n_roi), _channel_field(nonroi_mag[1], n_nonroi)],
    ]
    return _opt_from_fields(e), e


def _electrode_pair(current=(0.002, -0.002), channel_current=None):
    """Stand-in for a SimNIBS ``ElectrodeArrayPair`` after ``_prepare()``.

    ``current`` holds the per-electrode currents in **amperes** -- the builder
    configures one channel as ``[+c_A, -c_A]``.  ``_current_channel`` is the
    per-channel total SimNIBS reads instead when Dirichlet correction is on, and
    is only present on the object when that path is active.
    """
    pair = SimpleNamespace(current=list(current))
    if channel_current is not None:
        pair._current_channel = list(channel_current)
    return pair


def _opt_from_fields(e, electrodes=None):
    dirvec = np.array([[1.0, 0.0, 0.0]])
    opt = SimpleNamespace(
        n_test=0,
        n_sim=0,
        electrode_pos=None,
        # Set by SimNIBS once the search converges; the split applier keys off
        # its identity to recognise the final, post-search call.
        electrode_pos_opt=object(),
        electrode=(
            electrodes
            if electrodes is not None
            else [_electrode_pair(), _electrode_pair()]
        ),
        e_postproc="max_TI",
        _goal_dir=[dirvec, dirvec],
        get_electrode_pos_from_array=lambda parameters: parameters,
        update_field=lambda electrode_pos=None, plot=False: e,
    )
    opt.get_nodes_electrode = lambda electrode_pos, plot=False: ("nodes", electrode_pos)
    return opt


# ---------------------------------------------------------------------------
# threshold_free_focality
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThresholdFreeFocality:
    """The pure-function threshold-free focality measure."""

    def test_matches_hand_computed_value(self):
        # mean([0.4, 0.6, 0.5]) = 0.5; p95([0.1, 0.1, 0.2, 0.2]) = 0.2
        # => 0.5 ** 1 / 0.2 = 2.5
        e_roi = np.array([0.4, 0.6, 0.5])
        e_nonroi = np.array([0.1, 0.2, 0.1, 0.2])
        assert threshold_free_focality(e_roi, e_nonroi) == pytest.approx(2.5)

    def test_matches_reference_formula(self):
        e_roi = np.array([0.4, 0.6, 0.5])
        e_nonroi = np.array([0.1, 0.2, 0.1, 0.2])
        expected = np.mean(e_roi) / np.percentile(e_nonroi, 95.0)
        assert threshold_free_focality(e_roi, e_nonroi) == pytest.approx(expected)

    def test_intensity_weight_raises_roi_to_one_plus_w(self):
        # mean = 0.5, p95 = 0.2, w = 0.5 => 0.5 ** 1.5 / 0.2
        e_roi = np.array([0.4, 0.6, 0.5])
        e_nonroi = np.array([0.1, 0.2, 0.1, 0.2])
        expected = 0.5**1.5 / 0.2
        assert threshold_free_focality(e_roi, e_nonroi, 0.5) == pytest.approx(expected)

    def test_intensity_weight_one_flips_ranking_toward_intensity(self):
        # Candidate A is the more *focal* one (contrast 0.2/0.05 = 4);
        # candidate B is the more *intense* one (mean 0.6 vs 0.2) but less
        # focal (contrast 0.6/0.2 = 3).
        roi_a, non_a = _flat(0.2), _flat(0.05)
        roi_b, non_b = _flat(0.6), _flat(0.2)

        balanced_a = threshold_free_focality(roi_a, non_a, 0.0)
        balanced_b = threshold_free_focality(roi_b, non_b, 0.0)
        assert balanced_a == pytest.approx(4.0)
        assert balanced_b == pytest.approx(3.0)
        assert balanced_a > balanced_b  # w=0 prefers the focal candidate

        intense_a = threshold_free_focality(roi_a, non_a, 1.0)
        intense_b = threshold_free_focality(roi_b, non_b, 1.0)
        assert intense_a == pytest.approx(0.8)
        assert intense_b == pytest.approx(1.8)
        assert intense_b > intense_a  # w=1 flips to the intense candidate

    def test_increases_with_roi_field(self):
        non_roi = _flat(0.1)
        low = threshold_free_focality(_flat(0.3), non_roi)
        high = threshold_free_focality(_flat(0.6), non_roi)
        assert high > low

    def test_decreases_with_off_target_hotspot(self):
        e_roi = _flat(0.5)
        focal = threshold_free_focality(e_roi, _flat(0.05))
        diffuse = threshold_free_focality(e_roi, _flat(0.4))
        assert focal > diffuse

    def test_hotspot_penalised_under_every_weight(self):
        e_roi = _flat(0.5)
        for weight in (0.0, 0.5, 1.0):
            focal = threshold_free_focality(e_roi, _flat(0.05), weight)
            diffuse = threshold_free_focality(e_roi, _flat(0.4), weight)
            assert focal > diffuse

    def test_uses_p95_not_max(self):
        # A single extreme outlier must not dominate the non-ROI term the way
        # it would with a plain max.
        e_roi = _flat(0.5)
        clean = np.full(1000, 0.1)
        with_outlier = clean.copy()
        with_outlier[0] = 50.0
        assert threshold_free_focality(e_roi, with_outlier) == pytest.approx(
            threshold_free_focality(e_roi, clean), rel=0.05
        )

    def test_zero_nonroi_stays_finite(self):
        value = threshold_free_focality(_flat(0.5), np.zeros(4))
        assert np.isfinite(value)

    def test_empty_roi_returns_worst_score(self):
        assert threshold_free_focality(np.array([]), _flat(0.1)) == 0.0

    def test_empty_nonroi_returns_worst_score(self):
        assert threshold_free_focality(_flat(0.5), np.array([])) == 0.0

    def test_negative_roi_mean_returns_worst_score(self):
        # A signed post-processing component can go negative; a fractional
        # exponent of a negative base would be NaN, so it is floored at zero.
        value = threshold_free_focality(_flat(-0.5), _flat(0.1), 0.5)
        assert value == 0.0

    def test_nan_input_stays_finite(self):
        value = threshold_free_focality(np.array([np.nan, 0.5]), _flat(0.1))
        assert np.isfinite(value)


# ---------------------------------------------------------------------------
# make_objective
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMakeObjective:
    """Goal dispatch; every objective returns a value to *minimize*."""

    def test_mean_goal_negates_roi_mean(self):
        objective = make_objective(OptGoal.MEAN)
        e_roi = np.array([0.2, 0.4, 0.6])
        assert objective(e_roi, _flat(0.1)) == pytest.approx(-0.4)

    def test_mean_goal_ignores_nonroi(self):
        objective = make_objective("mean")
        e_roi = _flat(0.5)
        assert objective(e_roi, _flat(0.01)) == objective(e_roi, _flat(10.0))

    def test_max_goal_uses_high_percentile_of_roi(self):
        objective = make_objective(OptGoal.MAX)
        e_roi = np.array([0.1, 0.2, 0.3, 1.0])
        assert objective(e_roi, _flat(0.1)) == pytest.approx(
            -float(np.percentile(e_roi, 99.9))
        )

    def test_max_goal_beats_mean_goal_on_a_peaky_roi(self):
        e_roi = np.array([0.0, 0.0, 0.0, 1.0])
        peak = make_objective("max")(e_roi, _flat(0.1))
        average = make_objective("mean")(e_roi, _flat(0.1))
        assert peak < average  # the peak objective is the more negative one

    def test_focality_tf_negates_the_measure(self):
        objective = make_objective(OptGoal.FOCALITY_TF)
        e_roi, e_nonroi = _flat(0.5), _flat(0.1)
        assert objective(e_roi, e_nonroi) == pytest.approx(
            -threshold_free_focality(e_roi, e_nonroi)
        )

    def test_focality_tf_forwards_intensity_weight(self):
        e_roi, e_nonroi = _flat(0.5), _flat(0.1)
        objective = make_objective("focality_tf", intensity_weight=0.75)
        assert objective(e_roi, e_nonroi) == pytest.approx(
            -threshold_free_focality(e_roi, e_nonroi, 0.75)
        )

    def test_focality_tf_prefers_the_more_focal_candidate(self):
        objective = make_objective(OptGoal.FOCALITY_TF)
        focal = objective(_flat(0.5), _flat(0.05))
        diffuse = objective(_flat(0.5), _flat(0.4))
        assert focal < diffuse

    def test_focality_uses_simnibs_roc_form(self):
        roc = MagicMock(return_value=0.5)
        with patch.object(_MEASURES, "ROC", roc):
            objective = make_objective(OptGoal.FOCALITY, thresholds="0.1,0.2")
            value = objective(_flat(0.5), _flat(0.1))
        assert value == pytest.approx(-100.0 * (np.sqrt(2.0) - 0.5))
        assert roc.call_args.kwargs["threshold"] == [0.1, 0.2]
        assert roc.call_args.kwargs["focal"] is True

    def test_focality_single_threshold_passed_as_scalar(self):
        roc = MagicMock(return_value=0.4)
        with patch.object(_MEASURES, "ROC", roc):
            objective = make_objective("focality", thresholds="0.5")
            objective(_flat(0.5), _flat(0.1))
        assert roc.call_args.kwargs["threshold"] == 0.5

    @pytest.mark.parametrize("thresholds", [None, "", "dynamic", "auto"])
    def test_focality_without_usable_thresholds_raises(self, thresholds):
        with pytest.raises(ValueError, match="threshold"):
            make_objective(OptGoal.FOCALITY, thresholds=thresholds)

    def test_unknown_goal_raises(self):
        with pytest.raises(ValueError, match="Unknown optimization goal"):
            make_objective("focality_integral")

    @pytest.mark.parametrize("goal", list(OptGoal))
    def test_every_goal_returns_a_minimisable_scalar(self, goal):
        kwargs = {"thresholds": "0.1,0.2"} if goal is OptGoal.FOCALITY else {}
        with patch.object(_MEASURES, "ROC", MagicMock(return_value=0.9)):
            objective = make_objective(goal, intensity_weight=0.3, **kwargs)
            value = objective(np.array([0.4, 0.5, 0.6]), np.array([0.05, 0.1, 0.2]))
        assert isinstance(value, float)
        assert np.isfinite(value)

    @pytest.mark.parametrize("goal", list(OptGoal))
    def test_empty_roi_is_penalised_not_nan(self, goal):
        # A degenerate candidate must stay finite (NaN/inf would destabilise the
        # DE solver) and must never score better than a real candidate.
        kwargs = {"thresholds": "0.1,0.2"} if goal is OptGoal.FOCALITY else {}
        with patch.object(_MEASURES, "ROC", MagicMock(return_value=0.9)):
            objective = make_objective(goal, **kwargs)
            degenerate = objective(np.array([]), _flat(0.1))
            healthy = objective(_flat(0.5), _flat(0.05))
        assert np.isfinite(degenerate)
        assert degenerate >= healthy

    @pytest.mark.parametrize("goal", ["mean", "max", "focality"])
    def test_empty_roi_uses_the_explicit_penalty(self, goal):
        kwargs = {"thresholds": "0.1,0.2"} if goal == "focality" else {}
        with patch.object(_MEASURES, "ROC", MagicMock(return_value=0.9)):
            value = make_objective(goal, **kwargs)(np.array([]), _flat(0.1))
        assert value == pytest.approx(objectives._PENALTY)

    def test_focality_tf_degenerate_candidate_is_its_worst_score(self):
        # threshold_free_focality is non-negative, so the negated objective is
        # always <= 0 and the degenerate score 0.0 is already the worst value.
        objective = make_objective(OptGoal.FOCALITY_TF)
        assert objective(np.array([]), _flat(0.1)) == pytest.approx(0.0)
        assert objective(_flat(0.5), _flat(0.05)) < 0.0


# ---------------------------------------------------------------------------
# ratio_levels
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRatioLevels:
    """Enumeration of the discrete (I1, I2) current splits."""

    def test_returns_n_splits_for_an_odd_n(self):
        assert len(ratio_levels(4.0, 21)) == 21
        assert len(ratio_levels(4.0, 5)) == 5

    def test_default_count_is_21(self):
        assert len(ratio_levels(4.0)) == 21

    @pytest.mark.parametrize(
        "n, expected", [(2, 3), (4, 5), (20, 21), (21, 21), (51, 51)]
    )
    def test_rounds_n_up_to_the_next_odd_count(self, n, expected):
        assert len(ratio_levels(4.0, n)) == expected

    @pytest.mark.parametrize("n", [2, 4, 20, 21, 51])
    def test_always_contains_the_exact_balanced_split(self, n):
        # An even count straddles the midpoint and drops the 1:1 split
        # entirely, which would let the ratio search score *worse* than the
        # balanced montage flex-search uses when the search is off.
        splits = ratio_levels(4.0, n)
        assert any(
            i1 == pytest.approx(2.0) and i2 == pytest.approx(2.0) for i1, i2 in splits
        )

    @pytest.mark.parametrize("n", [2, 4, 20, 21, 51])
    def test_balanced_split_sits_at_the_midpoint(self, n):
        splits = ratio_levels(4.0, n)
        assert splits[len(splits) // 2] == pytest.approx((2.0, 2.0))

    @pytest.mark.parametrize("n", [2, 4, 20, 21, 51])
    def test_odd_rounding_keeps_the_sweep_symmetric(self, n):
        # Rounding up must not shift the endpoints: the sweep still spans
        # 1:3 .. 3:1 whatever n the user asked for.
        splits = ratio_levels(4.0, n)
        assert splits[0] == pytest.approx((1.0, 3.0))
        assert splits[-1] == pytest.approx((3.0, 1.0))

    def test_every_split_sums_to_total(self):
        for i1, i2 in ratio_levels(3.0, 11):
            assert i1 + i2 == pytest.approx(3.0)

    @pytest.mark.parametrize("n", [2, 4, 20, 21, 51])
    def test_balanced_split_is_exact_for_an_odd_total(self, n):
        # 3 mA splits evenly at 1.5 mA; linspace must land on it exactly, not
        # merely close, or the 1:1 baseline is still not in the search set.
        assert (1.5, 1.5) in ratio_levels(3.0, n)

    def test_spans_one_to_three(self):
        splits = ratio_levels(4.0, 21)
        assert splits[0] == pytest.approx((1.0, 3.0))
        assert splits[-1] == pytest.approx((3.0, 1.0))
        assert splits[0][0] / splits[0][1] == pytest.approx(1.0 / 3.0)
        assert splits[-1][0] / splits[-1][1] == pytest.approx(3.0)

    def test_balanced_split_is_the_midpoint(self):
        splits = ratio_levels(4.0, 21)
        assert splits[10] == pytest.approx((2.0, 2.0))

    def test_splits_are_monotonically_increasing_in_channel_one(self):
        first = [i1 for i1, _ in ratio_levels(4.0, 9)]
        assert first == sorted(first)

    def test_rejects_non_positive_total(self):
        with pytest.raises(ValueError, match="total_mA"):
            ratio_levels(0.0)

    def test_rejects_fewer_than_two_levels(self):
        with pytest.raises(ValueError, match="n must be"):
            ratio_levels(4.0, 1)


# ---------------------------------------------------------------------------
# install_ratio_search
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInstallRatioSearch:
    """The goal_fun wrapper that searches placement and current split jointly."""

    SPLITS = [(1.0, 3.0), (2.0, 2.0), (3.0, 1.0)]

    def _install(self, opt, objective=None, **kwargs):
        objective = objective or make_objective(OptGoal.FOCALITY_TF)
        with patch.object(_TFO, "postprocess_e", _norm_sum):
            install_ratio_search(
                opt,
                objective,
                base_mA=2.0,
                ratios=kwargs.pop("ratios", self.SPLITS),
                **kwargs,
            )

    def test_replaces_goal_fun(self):
        opt, _ = _make_ratio_opt()
        self._install(opt)
        assert callable(opt.goal_fun)

    def test_picks_the_split_that_maximises_contrast(self):
        # ROI is driven only by channel 1, the non-ROI only by channel 2, so
        # the most channel-1-heavy split is optimal.
        opt, _ = _make_ratio_opt(roi_mag=(1.0, 0.0), nonroi_mag=(0.0, 1.0))
        self._install(opt)

        value = opt.goal_fun(np.zeros(3))

        assert opt._best_current_split == pytest.approx((3.0, 1.0))
        # a1 = 3/2/2 = 1.5, a2 = 1/2 = 0.5 => contrast 1.5 / 0.5 = 3
        assert value == pytest.approx(-3.0)

    def test_picks_the_mirror_split_when_channels_swap(self):
        opt, _ = _make_ratio_opt(roi_mag=(0.0, 1.0), nonroi_mag=(1.0, 0.0))
        self._install(opt)

        value = opt.goal_fun(np.zeros(3))

        assert opt._best_current_split == pytest.approx((1.0, 3.0))
        assert value == pytest.approx(-3.0)

    def test_scaling_is_linear_in_the_split(self):
        # Both regions driven by channel 1: contrast is split-independent, so
        # every split scores the same and only the tie-break decides.
        opt, _ = _make_ratio_opt(roi_mag=(1.0, 0.0), nonroi_mag=(1.0, 0.0))
        self._install(opt)

        value = opt.goal_fun(np.zeros(3))

        assert value == pytest.approx(-1.0)
        assert opt._best_current_split == pytest.approx((2.0, 2.0))

    def test_exact_tie_resolves_to_the_most_balanced_split(self):
        # A constant objective makes every split score identically, so the
        # result is decided purely by the tie-break. The conservative answer
        # for a stimulation dose is the split closest to 1:1.
        opt, _ = _make_ratio_opt()
        self._install(opt, objective=lambda e_roi, e_nonroi: 1.0)

        opt.goal_fun(np.zeros(3))

        assert opt._best_current_split == pytest.approx((2.0, 2.0))

    def test_exact_tie_picks_the_closest_to_balanced_when_none_is_1_to_1(self):
        # No exactly-balanced split is offered, so "most balanced" means the
        # smallest |I1 - I2|, not simply the first or last candidate.
        opt, _ = _make_ratio_opt()
        self._install(
            opt,
            objective=lambda e_roi, e_nonroi: 1.0,
            ratios=[(0.5, 3.5), (1.8, 2.2), (3.5, 0.5)],
        )

        opt.goal_fun(np.zeros(3))

        assert opt._best_current_split == pytest.approx((1.8, 2.2))

    def test_tie_break_never_overrides_a_genuinely_better_split(self):
        # The balanced-first ordering only decides exact ties: a strictly
        # better extreme split must still win.
        opt, _ = _make_ratio_opt(roi_mag=(1.0, 0.0), nonroi_mag=(0.0, 1.0))
        self._install(opt)

        opt.goal_fun(np.zeros(3))

        assert opt._best_current_split == pytest.approx((3.0, 1.0))

    def test_records_the_best_candidates_split_not_the_last_one(self, caplog):
        # Candidate A is good (contrast 3.0, won by the 3:1 split); candidate B
        # is worse (contrast 1.0, a tie won by the 2:2 split) and is evaluated
        # last. Reporting the most recent evaluation would hand back 2:2, i.e.
        # a split that belongs to a placement the solver rejected.
        good = [
            [_channel_field(1.0, 8), _channel_field(0.0, 64)],
            [_channel_field(0.0, 8), _channel_field(1.0, 64)],
        ]
        worse = [
            [_channel_field(0.0, 8), _channel_field(0.0, 64)],
            [_channel_field(1.0, 8), _channel_field(1.0, 64)],
        ]
        sequence = [good, worse]
        opt = _opt_from_fields(good)
        opt.update_field = lambda electrode_pos=None, plot=False: sequence.pop(0)
        self._install(opt)

        with caplog.at_level(logging.INFO, logger="simnibs"):
            first = opt.goal_fun(np.zeros(3))
            last = opt.goal_fun(np.zeros(3))

        assert first == pytest.approx(-3.0)
        assert last == pytest.approx(-1.0)  # the last candidate really is worse
        # ... and it really did settle on a different split, so the assertion
        # below is not passing by accident.
        messages = [r.getMessage() for r in caplog.records if r.name == "simnibs"]
        assert "split 2.0:2.0 mA" in messages[-1]
        assert opt._best_current_split == pytest.approx((3.0, 1.0))

    def test_recorded_split_updates_when_a_better_candidate_arrives(self):
        # Mirror image of the test above: the worse candidate is scored first,
        # so the record must move to the later, better one.
        worse = [
            [_channel_field(0.0, 8), _channel_field(0.0, 64)],
            [_channel_field(1.0, 8), _channel_field(1.0, 64)],
        ]
        good = [
            [_channel_field(1.0, 8), _channel_field(0.0, 64)],
            [_channel_field(0.0, 8), _channel_field(1.0, 64)],
        ]
        sequence = [worse, good]
        opt = _opt_from_fields(worse)
        opt.update_field = lambda electrode_pos=None, plot=False: sequence.pop(0)
        self._install(opt)

        opt.goal_fun(np.zeros(3))
        assert opt._best_current_split == pytest.approx((2.0, 2.0))
        opt.goal_fun(np.zeros(3))
        assert opt._best_current_split == pytest.approx((3.0, 1.0))

    def test_winning_split_reaches_the_final_electrodes(self):
        # End-to-end: score a candidate, then replay SimNIBS's single
        # post-search get_nodes_electrode(electrode_pos_opt) call, which is the
        # last chance to change the currents before the final simulation.
        opt, _ = _make_ratio_opt(roi_mag=(1.0, 0.0), nonroi_mag=(0.0, 1.0))
        self._install(opt)

        opt.goal_fun(np.zeros(3))
        opt.get_nodes_electrode(electrode_pos=opt.electrode_pos_opt)

        assert opt._best_current_split == pytest.approx((3.0, 1.0))
        # Electrodes were built at +-2 mA; a 3:1 split of the 4 mA total gives
        # +-3 mA on channel 1 and +-1 mA on channel 2.
        assert opt.electrode[0].current == pytest.approx([0.003, -0.003])
        assert opt.electrode[1].current == pytest.approx([0.001, -0.001])

    def test_search_time_calls_leave_the_currents_untouched(self):
        # Every get_nodes_electrode call before convergence happens while
        # candidates are still being scored; rescaling there would perturb the
        # search itself.
        opt, _ = _make_ratio_opt(roi_mag=(1.0, 0.0), nonroi_mag=(0.0, 1.0))
        self._install(opt)

        opt.goal_fun(np.zeros(3))
        opt.get_nodes_electrode(electrode_pos=["a", "candidate"])

        assert opt._best_current_split == pytest.approx((3.0, 1.0))
        assert opt.electrode[0].current == pytest.approx([0.002, -0.002])
        assert opt.electrode[1].current == pytest.approx([0.002, -0.002])

    def test_returns_the_full_resolution_value_not_the_subsampled_one(self):
        # An off-target hotspot confined to rows the subsample never selects:
        # stage 1 cannot see it, so only a full re-score of the winner reflects
        # it in the returned value.
        n_nonroi = 200
        non_ch2 = _channel_field(0.1, n_nonroi)
        non_ch2[1:21, 0] = 5.0
        e = [
            [_channel_field(1.0, 8), _channel_field(0.0, n_nonroi)],
            [_channel_field(0.0, 8), non_ch2],
        ]
        opt = _opt_from_fields(e)
        objective = make_objective(OptGoal.FOCALITY_TF)
        self._install(opt, objective, select_subsample=8)

        value = opt.goal_fun(np.zeros(3))

        i1, i2 = opt._best_current_split
        a1, a2 = i1 / 2.0, i2 / 2.0
        roi_full = _norm_sum(a1 * e[0][0], a2 * e[1][0])
        non_full = _norm_sum(a1 * e[0][1], a2 * e[1][1])
        assert value == pytest.approx(objective(roi_full, non_full))

        # And the subsampled score really is different, so the assertion above
        # is not passing by accident.
        index = np.unique(np.linspace(0, n_nonroi - 1, 8).astype(int))
        non_sub = _norm_sum(a1 * e[0][1][index], a2 * e[1][1][index])
        assert objective(roi_full, non_sub) != pytest.approx(value)

    def test_overlapping_electrodes_return_simnibs_penalty(self):
        opt, _ = _make_ratio_opt()
        self._install(opt)
        opt.update_field = lambda electrode_pos=None, plot=False: None

        assert opt.goal_fun(np.zeros(3)) == 2.0
        assert opt.n_test == 1
        assert opt.n_sim == 0  # no FEM solve was consumed

    def test_counts_tests_and_sims_like_simnibs(self):
        opt, _ = _make_ratio_opt()
        self._install(opt)

        opt.goal_fun(np.zeros(3))
        opt.goal_fun(np.zeros(3))

        assert opt.n_test == 2
        assert opt.n_sim == 2

    def test_works_without_a_non_roi(self):
        # MEAN/MAX goals have a single ROI, so e[0] has length 1.
        e = [
            [_channel_field(1.0, 8)],
            [_channel_field(0.0, 8)],
        ]
        opt = _opt_from_fields(e)
        opt._goal_dir = [np.array([[1.0, 0.0, 0.0]])]
        self._install(opt, make_objective(OptGoal.MEAN))

        value = opt.goal_fun(np.zeros(3))

        # Best mean ROI field comes from the most channel-1-heavy split.
        assert opt._best_current_split == pytest.approx((3.0, 1.0))
        assert value == pytest.approx(-1.5)

    def test_logs_progress_on_the_simnibs_logger(self, caplog):
        opt, _ = _make_ratio_opt()
        self._install(opt)
        with caplog.at_level(logging.INFO, logger="simnibs"):
            opt.goal_fun(np.zeros(3))
        messages = [r.getMessage() for r in caplog.records if r.name == "simnibs"]
        assert any("Goal (ratio):" in m and "split 3.0:1.0 mA" in m for m in messages)

    def test_rejects_non_positive_base_current(self):
        opt, _ = _make_ratio_opt()
        with pytest.raises(ValueError, match="base_mA"):
            with patch.object(_TFO, "postprocess_e", _norm_sum):
                install_ratio_search(
                    opt, make_objective("mean"), base_mA=0.0, ratios=self.SPLITS
                )

    def test_rejects_empty_ratio_list(self):
        opt, _ = _make_ratio_opt()
        with pytest.raises(ValueError, match="ratios"):
            with patch.object(_TFO, "postprocess_e", _norm_sum):
                install_ratio_search(
                    opt, make_objective("mean"), base_mA=2.0, ratios=[]
                )

    def test_rejects_zero_subsample(self):
        opt, _ = _make_ratio_opt()
        with pytest.raises(ValueError, match="select_subsample"):
            with patch.object(_TFO, "postprocess_e", _norm_sum):
                install_ratio_search(
                    opt,
                    make_objective("mean"),
                    base_mA=2.0,
                    ratios=self.SPLITS,
                    select_subsample=0,
                )


# ---------------------------------------------------------------------------
# _apply_current_split
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyCurrentSplit:
    """Rescaling the channel electrodes so they inject the chosen split.

    The electrodes are built by ``builder.build_optimization`` as one
    ``ElectrodeArrayPair`` per channel with ``current = [+c_A, -c_A]``, i.e. at
    the 1:1 split.  Rescaling (rather than overwriting) is what preserves the
    sign structure SimNIBS validates on -- it asserts each pair sums to zero.
    """

    def test_rescales_each_channel_to_its_share(self):
        # Built at +-2 mA (the 1:1 split of a 4 mA total); a 3:1 split of that
        # same total gives +-3 mA on channel 1 and +-1 mA on channel 2.
        electrodes = [_electrode_pair(), _electrode_pair()]
        objectives._apply_current_split(
            SimpleNamespace(electrode=electrodes), (3.0, 1.0)
        )
        assert electrodes[0].current == pytest.approx([0.003, -0.003])
        assert electrodes[1].current == pytest.approx([0.001, -0.001])

    @pytest.mark.parametrize("per_pole", [1, 2, 4])
    def test_split_is_per_channel_not_per_electrode(self, per_pole):
        # The split is a per-CHANNEL dose, so the sum of a channel's anode
        # currents must equal it regardless of how many electrodes share the
        # load. Scaling off a single electrode's current would overshoot by
        # `per_pole` once a pole holds more than one electrode.
        share = 0.002 / per_pole
        electrodes = [
            SimpleNamespace(current=[share] * per_pole + [-share] * per_pole)
            for _ in range(2)
        ]
        objectives._apply_current_split(
            SimpleNamespace(electrode=electrodes), (3.0, 1.0)
        )

        for pair, expected_mA in zip(electrodes, (3.0, 1.0)):
            injected_mA = sum(v for v in pair.current if v > 0) * 1000.0
            assert injected_mA == pytest.approx(expected_mA)
            # Still balanced, and the load is still shared evenly.
            assert sum(pair.current) == pytest.approx(0.0)
            assert len(pair.current) == 2 * per_pole

    def test_preserves_the_total_current(self):
        electrodes = [_electrode_pair(), _electrode_pair()]
        objectives._apply_current_split(
            SimpleNamespace(electrode=electrodes), (3.0, 1.0)
        )
        per_channel = [abs(pair.current[0]) * 1000.0 for pair in electrodes]
        assert sum(per_channel) == pytest.approx(4.0)

    def test_preserves_sign_structure(self):
        # Whichever pole SimNIBS made the source stays the source.
        electrodes = [
            _electrode_pair(current=(-0.002, 0.002)),
            _electrode_pair(current=(0.002, -0.002)),
        ]
        objectives._apply_current_split(
            SimpleNamespace(electrode=electrodes), (3.0, 1.0)
        )
        assert electrodes[0].current == pytest.approx([-0.003, 0.003])
        assert electrodes[1].current == pytest.approx([0.001, -0.001])

    def test_each_channel_still_sums_to_zero(self):
        # SimNIBS raises AssertionError if a pair's currents do not cancel.
        electrodes = [_electrode_pair(), _electrode_pair(current=(-0.002, 0.002))]
        objectives._apply_current_split(
            SimpleNamespace(electrode=electrodes), (3.5, 0.5)
        )
        for pair in electrodes:
            assert sum(pair.current) == pytest.approx(0.0, abs=1e-15)

    def test_balanced_split_is_a_no_op(self):
        # 2:2 of a 4 mA total is exactly what the electrodes were built with.
        electrodes = [_electrode_pair(), _electrode_pair()]
        objectives._apply_current_split(
            SimpleNamespace(electrode=electrodes), (2.0, 2.0)
        )
        assert electrodes[0].current == pytest.approx([0.002, -0.002])
        assert electrodes[1].current == pytest.approx([0.002, -0.002])

    def test_scales_current_channel_when_present(self):
        # Dirichlet correction makes SimNIBS read _current_channel instead of
        # .current, so it has to move by the same factor.
        electrodes = [
            _electrode_pair(channel_current=(0.002, -0.002)),
            _electrode_pair(channel_current=(0.002, -0.002)),
        ]
        objectives._apply_current_split(
            SimpleNamespace(electrode=electrodes), (3.0, 1.0)
        )
        assert electrodes[0]._current_channel == pytest.approx([0.003, -0.003])
        assert electrodes[1]._current_channel == pytest.approx([0.001, -0.001])

    def test_does_not_invent_a_current_channel_attribute(self):
        pair = _electrode_pair()
        objectives._apply_current_split(SimpleNamespace(electrode=[pair]), (3.0, 1.0))
        assert not hasattr(pair, "_current_channel")

    def test_accepts_numpy_current_arrays(self):
        # After ElectrodeArrayPair._prepare() the currents are a numpy array.
        pair = SimpleNamespace(current=np.array([0.002, -0.002]))
        objectives._apply_current_split(SimpleNamespace(electrode=[pair]), (3.0, 1.0))
        assert list(pair.current) == pytest.approx([0.003, -0.003])

    def test_skips_electrodes_without_currents(self):
        empty = SimpleNamespace(current=[])
        missing = SimpleNamespace(current=None)
        objectives._apply_current_split(
            SimpleNamespace(electrode=[empty, missing]), (3.0, 1.0)
        )
        assert empty.current == []
        assert missing.current is None

    def test_ignores_splits_beyond_the_available_channels(self):
        pair = _electrode_pair()
        objectives._apply_current_split(SimpleNamespace(electrode=[pair]), (3.0, 1.0))
        assert pair.current == pytest.approx([0.003, -0.003])

    @pytest.mark.parametrize(
        "opt", [SimpleNamespace(electrode=None), SimpleNamespace()]
    )
    def test_missing_electrodes_is_a_no_op(self, opt):
        objectives._apply_current_split(opt, (3.0, 1.0))


class _FakeElectrode:
    """Mimics ``simnibs...electrode_layout.Electrode``'s current plumbing.

    The ``ele_current`` setter re-derives ``node_current`` from the node areas,
    exactly as SimNIBS does; ``ele_current_init`` is what ``get_nodes_electrode``
    resets ``ele_current`` to before every FEM update.
    """

    def __init__(self, ele_current, node_area):
        self.node_area = np.asarray(node_area, dtype=float)
        self.node_area_total = float(self.node_area.sum())
        self.n_nodes = len(self.node_area)
        self.ele_current_init = ele_current
        self.ele_current = ele_current

    @property
    def ele_current(self):
        return self._ele_current

    @ele_current.setter
    def ele_current(self, value):
        self._ele_current = value
        self._node_current = value * self.node_area / self.node_area_total

    @property
    def node_current(self):
        return self._node_current


class _FakeArrayPair:
    """Mimics an ``ElectrodeArrayPair`` after ``_prepare()``.

    ``current`` / ``_current_channel`` / ``_current_total`` / ``_current_mean``
    are the pair-level bookkeeping; the FEM reads the per-electrode
    ``ele_current`` / ``node_current`` and the compiled ``_node_current``.
    """

    def __init__(self, per_pole=1, c_A=0.002):
        share = c_A / per_pole
        self.current = np.array([share] * per_pole + [-share] * per_pole)
        self._current_total = c_A
        self._current_mean = np.array([share, -share])
        self._current_channel = np.array([c_A, -c_A])
        self._electrode_arrays = [
            SimpleNamespace(
                electrodes=[
                    _FakeElectrode(sign * share, node_area=[1.0, 3.0])
                    for _ in range(per_pole)
                ]
            )
            for sign in (1.0, -1.0)
        ]
        self.compiled = 0
        self.compile_node_arrays()

    def compile_node_arrays(self):
        self.compiled += 1
        self._node_current = np.hstack(
            [
                ele.node_current
                for array in self._electrode_arrays
                for ele in array.electrodes
            ]
        )

    def reset_from_init(self):
        # What SimNIBS's get_nodes_electrode does before every FEM update.
        for array in self._electrode_arrays:
            for ele in array.electrodes:
                ele.ele_current = ele.ele_current_init
        self.compile_node_arrays()

    def injected_ele_A(self):
        return sum(
            float(np.sum(ele.ele_current))
            for array in self._electrode_arrays
            for ele in array.electrodes
            if np.sum(ele.ele_current) > 0
        )


@pytest.mark.unit
class TestApplyCurrentSplitReachesTheFEM:
    """The split must land on what ``onlinefem`` actually reads.

    After ``_prepare()`` the FEM never looks at ``ElectrodeArrayPair.current``:
    ``set_rhs`` gathers each ``Electrode``'s ``node_current`` / ``ele_current``
    and the Dirichlet loop reads the pair's compiled ``_node_current`` and
    ``_current_channel``.  ``get_nodes_electrode`` rebuilds those from
    ``ele_current_init``, so all of them have to move together.
    """

    @pytest.mark.parametrize("per_pole", [1, 2])
    def test_per_electrode_currents_are_scaled(self, per_pole):
        pairs = [_FakeArrayPair(per_pole), _FakeArrayPair(per_pole)]
        objectives._apply_current_split(SimpleNamespace(electrode=pairs), (3.0, 1.0))
        assert pairs[0].injected_ele_A() == pytest.approx(0.003)
        assert pairs[1].injected_ele_A() == pytest.approx(0.001)
        for pair, expected in zip(pairs, (0.003, 0.001)):
            for array, sign in zip(pair._electrode_arrays, (1.0, -1.0)):
                for ele in array.electrodes:
                    assert ele.ele_current == pytest.approx(sign * expected / per_pole)
                    assert ele.ele_current_init == pytest.approx(
                        sign * expected / per_pole
                    )
                    assert ele.node_current == pytest.approx(
                        sign * expected / per_pole * np.array([0.25, 0.75])
                    )

    def test_node_arrays_are_recompiled(self):
        pair = _FakeArrayPair()
        before = pair.compiled
        objectives._apply_current_split(SimpleNamespace(electrode=[pair]), (3.0, 1.0))
        assert pair.compiled == before + 1
        assert pair._node_current == pytest.approx(
            np.array([0.003 * 0.25, 0.003 * 0.75, -0.003 * 0.25, -0.003 * 0.75])
        )

    def test_pair_level_bookkeeping_stays_consistent(self):
        pair = _FakeArrayPair()
        objectives._apply_current_split(SimpleNamespace(electrode=[pair]), (3.0, 1.0))
        assert list(pair.current) == pytest.approx([0.003, -0.003])
        assert list(pair._current_channel) == pytest.approx([0.003, -0.003])
        assert pair._current_total == pytest.approx(0.003)
        assert list(pair._current_mean) == pytest.approx([0.003, -0.003])
        # Dirichlet path: channel total equals the compiled node current sum.
        anodes = pair._node_current[pair._node_current > 0]
        assert anodes.sum() == pytest.approx(pair._current_channel[0])

    def test_survives_simnibs_reset_from_init(self):
        # get_nodes_electrode resets ele_current from ele_current_init before
        # the final update_field, so the init values must carry the split.
        pair = _FakeArrayPair()
        objectives._apply_current_split(SimpleNamespace(electrode=[pair]), (3.0, 1.0))
        pair.reset_from_init()
        assert pair.injected_ele_A() == pytest.approx(0.003)

    def test_is_idempotent_across_the_two_final_calls(self):
        # SimNIBS calls get_nodes_electrode(electrode_pos_opt) twice (once after
        # the search, once inside update_field); applying twice must not
        # compound.
        pair = _FakeArrayPair()
        opt = SimpleNamespace(electrode=[pair])
        objectives._apply_current_split(opt, (3.0, 1.0))
        pair.reset_from_init()
        objectives._apply_current_split(opt, (3.0, 1.0))
        assert pair.injected_ele_A() == pytest.approx(0.003)
        assert list(pair.current) == pytest.approx([0.003, -0.003])
        assert list(pair._current_channel) == pytest.approx([0.003, -0.003])

    def test_rescales_estimator_overwritten_currents(self):
        # With a current estimator, get_nodes_electrode overwrites ele_current
        # with unscaled estimates; the applier must bring them back to the
        # split rather than trusting the already-scaled pair-level `.current`.
        pair = _FakeArrayPair()
        opt = SimpleNamespace(electrode=[pair])
        objectives._apply_current_split(opt, (3.0, 1.0))
        for array, sign in zip(pair._electrode_arrays, (1.0, -1.0)):
            for ele in array.electrodes:
                ele.ele_current = sign * 0.002
        objectives._apply_current_split(opt, (3.0, 1.0))
        assert pair.injected_ele_A() == pytest.approx(0.003)


# ---------------------------------------------------------------------------
# _install_split_applier
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSplitApplierHook:
    """The get_nodes_electrode hook that applies the winning split.

    SimNIBS calls ``get_nodes_electrode(electrode_pos=self.electrode_pos_opt)``
    exactly once, after the search converges and immediately before it builds
    the sessions for the final simulation; every earlier call happens while
    candidates are still being scored.
    """

    def _hooked(self, best_split):
        opt = _opt_from_fields([[_channel_field(1.0, 8)], [_channel_field(0.0, 8)]])
        objectives._install_split_applier(opt, {"best_split": best_split})
        return opt

    def test_wraps_rather_than_replaces_the_original(self):
        opt = self._hooked(None)
        assert opt.get_nodes_electrode(electrode_pos="candidate") == (
            "nodes",
            "candidate",
        )

    def test_returns_the_originals_value_on_the_final_call_too(self):
        opt = self._hooked(None)
        result = opt.get_nodes_electrode(electrode_pos=opt.electrode_pos_opt)
        assert result == ("nodes", opt.electrode_pos_opt)

    def test_search_time_calls_do_not_rescale(self):
        opt = self._hooked((3.0, 1.0))
        opt.get_nodes_electrode(electrode_pos=["a", "candidate"])
        assert opt.electrode[0].current == pytest.approx([0.002, -0.002])
        assert opt.electrode[1].current == pytest.approx([0.002, -0.002])

    def test_no_recorded_split_leaves_the_currents_alone(self):
        # Nothing to apply when the ratio search never produced a winner.
        opt = self._hooked(None)
        opt.get_nodes_electrode(electrode_pos=opt.electrode_pos_opt)
        assert opt.electrode[0].current == pytest.approx([0.002, -0.002])
        assert opt.electrode[1].current == pytest.approx([0.002, -0.002])

    def test_applies_the_winning_split_on_the_final_call(self):
        opt = self._hooked((3.0, 1.0))
        opt.get_nodes_electrode(electrode_pos=opt.electrode_pos_opt)
        assert opt.electrode[0].current == pytest.approx([0.003, -0.003])
        assert opt.electrode[1].current == pytest.approx([0.001, -0.001])
