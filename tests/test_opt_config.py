#!/usr/bin/env python3
"""
Tests for tit/opt/config.py -- optimization configuration dataclasses.

Covers FlexConfig validation (enum coercion, focality rules, thresholds),
ExConfig validation (dict-to-dataclass coercion, roi_name suffix),
ROI type defaults, and result dataclass construction.
"""

import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import directly from tit.opt.config (not tit.opt) to avoid triggering
# tit.opt.__init__ which imports ex/flex engines that need simnibs.
from tit.opt.config import (
    ExConfig,
    ExResult,
    FlexConfig,
    FlexResult,
    MTIFrequencyPlan,
    validate_band_separation,
)

# Convenience aliases for nested types
OptGoal = FlexConfig.OptGoal
FieldPostproc = FlexConfig.FieldPostproc
NonROIMethod = FlexConfig.NonROIMethod
SphericalROI = FlexConfig.SphericalROI
AtlasROI = FlexConfig.AtlasROI
SubcorticalROI = FlexConfig.SubcorticalROI
FlexElectrodeConfig = FlexConfig.ElectrodeConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flex_config(**overrides):
    """Build a valid FlexConfig with sensible defaults, applying overrides."""
    defaults = dict(
        subject_id="001",
        goal=OptGoal.MEAN,
        postproc=FieldPostproc.MAX_TI,
        current_mA=2.0,
        electrode=FlexElectrodeConfig(),
        roi=SphericalROI(x=0, y=0, z=0),
    )
    defaults.update(overrides)
    return FlexConfig(**defaults)


# ---------------------------------------------------------------------------
# FlexConfig validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexConfigValidation:
    """FlexConfig __post_init__ coercion and validation."""

    def test_string_goal_coerced_to_enum(self):
        cfg = _make_flex_config(goal="mean")
        assert cfg.goal is OptGoal.MEAN

    def test_string_postproc_coerced_to_enum(self):
        cfg = _make_flex_config(postproc="max_TI")
        assert cfg.postproc is FieldPostproc.MAX_TI

    def test_string_non_roi_method_coerced_to_enum(self):
        cfg = _make_flex_config(
            goal="focality",
            non_roi_method="everything_else",
        )
        assert cfg.non_roi_method is NonROIMethod.EVERYTHING_ELSE

    def test_focality_specific_without_non_roi_raises(self):
        with pytest.raises(ValueError, match="non_roi"):
            _make_flex_config(
                goal="focality",
                non_roi_method="specific",
                non_roi=None,
            )

    def test_focality_everything_else_is_valid(self):
        cfg = _make_flex_config(
            goal="focality",
            non_roi_method="everything_else",
        )
        assert cfg.goal is OptGoal.FOCALITY
        assert cfg.non_roi_method is NonROIMethod.EVERYTHING_ELSE

    def test_focality_specific_with_non_roi_is_valid(self):
        cfg = _make_flex_config(
            goal="focality",
            non_roi_method="specific",
            non_roi=SphericalROI(x=10, y=10, z=10),
        )
        assert cfg.non_roi is not None

    @pytest.mark.parametrize(
        "goal_str", ["integral_focality", "auc_focality", "ratio_focality"]
    )
    def test_custom_focality_goal_coerced_to_enum(self, goal_str):
        cfg = _make_flex_config(goal=goal_str, non_roi_method="everything_else")
        assert cfg.goal is OptGoal(goal_str)

    @pytest.mark.parametrize(
        "goal_str", ["integral_focality", "auc_focality", "ratio_focality"]
    )
    def test_custom_focality_goal_requires_non_roi_method(self, goal_str):
        with pytest.raises(ValueError, match="non_roi_method"):
            _make_flex_config(goal=goal_str, non_roi_method=None)

    @pytest.mark.parametrize(
        "goal_str", ["integral_focality", "auc_focality", "ratio_focality"]
    )
    def test_custom_focality_goal_specific_without_non_roi_raises(self, goal_str):
        with pytest.raises(ValueError, match="non_roi"):
            _make_flex_config(
                goal=goal_str,
                non_roi_method="specific",
                non_roi=None,
            )

    @pytest.mark.parametrize(
        "goal_str", ["integral_focality", "auc_focality", "ratio_focality"]
    )
    def test_custom_focality_goal_everything_else_is_valid(self, goal_str):
        cfg = _make_flex_config(goal=goal_str, non_roi_method="everything_else")
        assert cfg.non_roi_method is NonROIMethod.EVERYTHING_ELSE

    @pytest.mark.parametrize(
        "goal_str", ["integral_focality", "auc_focality", "ratio_focality"]
    )
    def test_custom_focality_goal_specific_with_non_roi_is_valid(self, goal_str):
        cfg = _make_flex_config(
            goal=goal_str,
            non_roi_method="specific",
            non_roi=SphericalROI(x=10, y=10, z=10),
        )
        assert cfg.non_roi is not None

    def test_requiring_non_roi_includes_all_focality_goals(self):
        assert OptGoal.requiring_non_roi() == {
            OptGoal.FOCALITY,
            OptGoal.INTEGRAL_FOCALITY,
            OptGoal.AUC_FOCALITY,
            OptGoal.RATIO_FOCALITY,
        }

    def test_custom_callable_goals_excludes_focality(self):
        # "focality" still uses SimNIBS' built-in string goal (thresholds),
        # not a custom Python callable.
        assert OptGoal.FOCALITY not in OptGoal.custom_callable_goals()
        assert OptGoal.custom_callable_goals() == {
            OptGoal.INTEGRAL_FOCALITY,
            OptGoal.AUC_FOCALITY,
            OptGoal.RATIO_FOCALITY,
        }

    def test_invalid_thresholds_raises(self):
        with pytest.raises(ValueError):
            _make_flex_config(thresholds="abc,def")

    def test_valid_thresholds_passes(self):
        cfg = _make_flex_config(thresholds="0.5,0.75,0.9")
        assert cfg.thresholds == "0.5,0.75,0.9"

    def test_single_threshold_passes(self):
        cfg = _make_flex_config(thresholds="0.5")
        assert cfg.thresholds == "0.5"

    def test_min_electrode_distance_default(self):
        cfg = _make_flex_config()
        assert cfg.min_electrode_distance == 5.0

    def test_min_electrode_distance_custom(self):
        cfg = _make_flex_config(min_electrode_distance=50.0)
        assert cfg.min_electrode_distance == 50.0

    def test_min_electrode_distance_zero(self):
        cfg = _make_flex_config(min_electrode_distance=0.0)
        assert cfg.min_electrode_distance == 0.0

    def test_skin_region_margin_defaults_preserve_simnibs_region(self):
        cfg = _make_flex_config()
        assert cfg.skin_region_margin_mm == 0.0
        assert cfg.avoid_landmark_regions is True

    def test_skin_region_margin_coerced_to_float(self):
        cfg = _make_flex_config(skin_region_margin_mm="20")
        assert cfg.skin_region_margin_mm == 20.0


# ---------------------------------------------------------------------------
# ExConfig validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExConfigValidation:
    """ExConfig __post_init__ coercion and validation."""

    def test_flat_current_fields(self):
        cfg = ExConfig(
            subject_id="001",
            leadfield_hdf="/lf.hdf5",
            roi_name="region",
            electrodes=ExConfig.PoolElectrodes(electrodes=["E1", "E2"]),
            total_current=3.0,
            current_step=1.0,
        )
        assert cfg.total_current == 3.0
        assert cfg.current_step == 1.0

    def test_dict_to_pool_electrodes(self):
        cfg = ExConfig(
            subject_id="001",
            leadfield_hdf="/lf.hdf5",
            roi_name="region",
            electrodes={"electrodes": ["E1", "E2", "E3"]},
        )
        assert isinstance(cfg.electrodes, ExConfig.PoolElectrodes)
        assert cfg.electrodes.electrodes == ["E1", "E2", "E3"]

    def test_dict_to_bucket_electrodes(self):
        cfg = ExConfig(
            subject_id="001",
            leadfield_hdf="/lf.hdf5",
            roi_name="region",
            electrodes={
                "e1_plus": ["A1"],
                "e1_minus": ["A2"],
                "e2_plus": ["B1"],
                "e2_minus": ["B2"],
            },
        )
        assert isinstance(cfg.electrodes, ExConfig.BucketElectrodes)
        assert cfg.electrodes.e1_plus == ["A1"]

    def test_roi_name_gets_csv_suffix(self):
        cfg = ExConfig(
            subject_id="001",
            leadfield_hdf="/lf.hdf5",
            roi_name="my_region",
            electrodes=ExConfig.PoolElectrodes(electrodes=["E1"]),
        )
        assert cfg.roi_name == "my_region.csv"

    def test_roi_name_keeps_csv_suffix(self):
        cfg = ExConfig(
            subject_id="001",
            leadfield_hdf="/lf.hdf5",
            roi_name="my_region.csv",
            electrodes=ExConfig.PoolElectrodes(electrodes=["E1"]),
        )
        assert cfg.roi_name == "my_region.csv"

    def test_ex_config_rejects_zero_step(self):
        with pytest.raises(ValueError, match="current_step must be positive"):
            ExConfig(
                subject_id="001",
                leadfield_hdf="/lf.hdf5",
                roi_name="region",
                electrodes=ExConfig.PoolElectrodes(electrodes=["E1"]),
                current_step=0,
            )

    def test_ex_config_rejects_negative_total(self):
        with pytest.raises(ValueError, match="total_current must be positive"):
            ExConfig(
                subject_id="001",
                leadfield_hdf="/lf.hdf5",
                roi_name="region",
                electrodes=ExConfig.PoolElectrodes(electrodes=["E1"]),
                total_current=-1.0,
            )

    def test_ex_config_rejects_negative_channel_limit(self):
        with pytest.raises(ValueError, match="channel_limit must be positive"):
            ExConfig(
                subject_id="001",
                leadfield_hdf="/lf.hdf5",
                roi_name="region",
                electrodes=ExConfig.PoolElectrodes(electrodes=["E1"]),
                channel_limit=-0.5,
            )


# ---------------------------------------------------------------------------
# ExConfig.metric / carrier_constraint / carrier_penalty_weight
# (mti-carrier-metrics track, Tasks B/C)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExConfigMetricAndCarrier:
    """New Phase-2 fields default off / to the current behaviour."""

    def _make(self, **overrides):
        defaults = dict(
            subject_id="001",
            leadfield_hdf="/lf.hdf5",
            roi_name="region",
            electrodes=ExConfig.PoolElectrodes(electrodes=["E1", "E2"]),
        )
        defaults.update(overrides)
        return ExConfig(**defaults)

    def test_metric_defaults_to_grossman(self):
        cfg = self._make()
        assert cfg.metric == "grossman"

    def test_metric_accepts_mti_modulation_depth(self):
        cfg = self._make(metric="mti_modulation_depth")
        assert cfg.metric == "mti_modulation_depth"

    def test_metric_rejects_unknown_value(self):
        with pytest.raises(ValueError, match="metric must be"):
            self._make(metric="not_a_real_metric")

    def test_carrier_constraint_defaults_to_none(self):
        cfg = self._make()
        assert cfg.carrier_constraint is None

    def test_carrier_penalty_weight_defaults_to_zero(self):
        cfg = self._make()
        assert cfg.carrier_penalty_weight == 0.0

    def test_carrier_constraint_and_weight_settable(self):
        cfg = self._make(carrier_constraint=0.5, carrier_penalty_weight=2.0)
        assert cfg.carrier_constraint == 0.5
        assert cfg.carrier_penalty_weight == 2.0

    def test_negative_carrier_penalty_weight_rejected(self):
        with pytest.raises(ValueError, match="carrier_penalty_weight"):
            self._make(carrier_penalty_weight=-1.0)


# ---------------------------------------------------------------------------
# ROI type defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestROIDefaults:
    """Default values on ROI dataclasses."""

    def test_spherical_roi_defaults(self):
        roi = SphericalROI(x=1.0, y=2.0, z=3.0)
        assert roi.radius == 10.0
        assert roi.use_mni is False

    def test_atlas_roi_defaults(self):
        roi = AtlasROI(atlas_path="/atlas.annot", label=5)
        assert roi.hemisphere == "lh"

    def test_subcortical_roi_defaults(self):
        roi = SubcorticalROI(atlas_path="/atlas.nii.gz", label=17)
        assert roi.atlas_space == "subject"
        assert roi.tissues == "GM"

    def test_flex_electrode_config_defaults(self):
        elec = FlexElectrodeConfig()
        assert elec.shape == "ellipse"
        assert elec.dimensions == [8.0, 8.0]
        assert elec.gel_thickness == 4.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexResult:
    """FlexResult construction."""

    def test_construction(self):
        result = FlexResult(
            success=True,
            output_folder="/out/flex",
            function_values=[1.0, 0.8, 0.9],
            best_value=1.0,
            best_run_index=0,
        )
        assert result.success is True
        assert result.output_folder == "/out/flex"
        assert result.best_value == 1.0
        assert result.best_run_index == 0
        assert len(result.function_values) == 3


@pytest.mark.unit
class TestExResult:
    """ExResult construction, including optional fields."""

    def test_construction_with_all_fields(self):
        result = ExResult(
            success=True,
            output_dir="/out/ex",
            n_combinations=500,
            results_csv="/out/results.csv",
            config_json="/out/results.json",
        )
        assert result.success is True
        assert result.n_combinations == 500
        assert result.results_csv == "/out/results.csv"
        assert result.config_json == "/out/results.json"

    def test_construction_with_optional_none(self):
        result = ExResult(
            success=False,
            output_dir="/out/ex",
            n_combinations=0,
        )
        assert result.results_csv is None
        assert result.config_json is None


# ---------------------------------------------------------------------------
# MTIFrequencyPlan
# ---------------------------------------------------------------------------


class TestMTIFrequencyPlan:
    """Construction, defaults, and validation for MTIFrequencyPlan."""

    def test_minimal_construction_defaults_phases_to_zero(self):
        plan = MTIFrequencyPlan(f_a=[2000.0], f_b=[2010.0])
        assert plan.phi_a == [0.0]
        assert plan.phi_b == [0.0]

    def test_delta_f_and_pair_means(self):
        plan = MTIFrequencyPlan(f_a=[2000.0, 4000.0], f_b=[2010.0, 4010.0])
        assert plan.delta_f == pytest.approx(10.0)
        assert plan.pair_means == pytest.approx([2005.0, 4005.0])

    def test_psi_property_is_phi_b_minus_phi_a(self):
        plan = MTIFrequencyPlan(
            f_a=[2000.0, 4000.0],
            f_b=[2010.0, 4010.0],
            phi_a=[0.1, 0.2],
            phi_b=[0.4, 0.0],
        )
        assert plan.psi == pytest.approx([0.3, -0.2])

    def test_empty_f_a_raises(self):
        with pytest.raises(ValueError, match="at least one pair"):
            MTIFrequencyPlan(f_a=[], f_b=[])

    def test_mismatched_f_a_f_b_length_raises(self):
        with pytest.raises(ValueError, match="equal length"):
            MTIFrequencyPlan(f_a=[2000.0, 4000.0], f_b=[2010.0])

    def test_mismatched_phase_length_raises(self):
        with pytest.raises(ValueError, match="phi_a and phi_b"):
            MTIFrequencyPlan(f_a=[2000.0, 4000.0], f_b=[2010.0, 4010.0], phi_a=[0.0])

    def test_nonpositive_frequency_raises(self):
        with pytest.raises(ValueError, match="positive"):
            MTIFrequencyPlan(f_a=[0.0], f_b=[10.0])
        with pytest.raises(ValueError, match="positive"):
            MTIFrequencyPlan(f_a=[-2000.0], f_b=[-1990.0])

    def test_inconsistent_delta_f_across_pairs_raises(self):
        with pytest.raises(ValueError, match="delta_f"):
            MTIFrequencyPlan(f_a=[2000.0, 4000.0], f_b=[2010.0, 4030.0])


# ---------------------------------------------------------------------------
# validate_band_separation
# ---------------------------------------------------------------------------


class TestValidateBandSeparation:
    """F7 carrier-band-gap validity condition:
    (mean-frequency gap - delta_f) > f_cutoff for every pair of pairs."""

    def test_wide_separation_passes(self):
        plan = MTIFrequencyPlan(f_a=[2000.0, 4000.0], f_b=[2010.0, 4010.0])
        validate_band_separation(plan)  # gap=2000, delta_f=10 -> margin=1990 > 200

    def test_botzanowski_style_four_pair_plan_passes(self):
        # Pair-mean carriers 2000/4000/6000/8000 Hz, delta_f=100 Hz.
        means = [2000.0, 4000.0, 6000.0, 8000.0]
        plan = MTIFrequencyPlan(
            f_a=[m - 50.0 for m in means], f_b=[m + 50.0 for m in means]
        )
        validate_band_separation(plan)

    def test_gap_at_exactly_cutoff_plus_delta_f_rejected(self):
        # gap=210, delta_f=10 -> margin=200 == f_cutoff -> must reject (uses <=).
        plan = MTIFrequencyPlan(f_a=[2000.0, 2210.0], f_b=[2010.0, 2220.0])
        with pytest.raises(ValueError, match="pairs 0 and 1"):
            validate_band_separation(plan, f_cutoff=200.0)

    def test_narrow_separation_rejected_with_pair_indices_named(self):
        plan = MTIFrequencyPlan(f_a=[2000.0, 2050.0], f_b=[2010.0, 2060.0])
        with pytest.raises(ValueError) as excinfo:
            validate_band_separation(plan, f_cutoff=200.0)
        msg = str(excinfo.value)
        assert "pairs 0 and 1" in msg
        assert "delta_f" in msg

    def test_three_pairs_names_only_offending_pair(self):
        # Pair 0<->1 too close, pair 0<->2 and 1<->2 fine.
        plan = MTIFrequencyPlan(
            f_a=[2000.0, 2050.0, 5000.0], f_b=[2010.0, 2060.0, 5010.0]
        )
        with pytest.raises(ValueError) as excinfo:
            validate_band_separation(plan, f_cutoff=200.0)
        msg = str(excinfo.value)
        assert "pairs 0 and 1" in msg
        assert "pairs 0 and 2" not in msg
        assert "pairs 1 and 2" not in msg

    def test_custom_f_cutoff_respected(self):
        plan = MTIFrequencyPlan(f_a=[2000.0, 2100.0], f_b=[2010.0, 2110.0])
        # gap=100, delta_f=10 -> margin=90.
        validate_band_separation(plan, f_cutoff=50.0)
        with pytest.raises(ValueError):
            validate_band_separation(plan, f_cutoff=100.0)
