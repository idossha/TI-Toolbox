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

    # -- threshold-free focality --------------------------------------------

    def test_string_threshold_free_goal_coerced_to_enum(self):
        cfg = _make_flex_config(goal="focality_tf")
        assert cfg.goal is OptGoal.FOCALITY_TF

    def test_focality_integral_goal_no_longer_exists(self):
        # Replaced by FOCALITY_TF; an old config must fail loudly.
        assert not hasattr(OptGoal, "FOCALITY_INTEGRAL")
        with pytest.raises(ValueError):
            _make_flex_config(goal="focality_integral")

    def test_is_focality_true_for_both_focality_goals(self):
        assert _make_flex_config(goal="focality").is_focality is True
        assert _make_flex_config(goal="focality_tf").is_focality is True

    def test_is_focality_false_for_mean_and_max(self):
        assert _make_flex_config(goal="mean").is_focality is False
        assert _make_flex_config(goal="max").is_focality is False

    def test_threshold_free_focality_defaults_non_roi_method(self):
        # Omitting the method should default to 'everything else', not crash.
        cfg = _make_flex_config(goal="focality_tf")
        assert cfg.non_roi_method is NonROIMethod.EVERYTHING_ELSE

    def test_threshold_free_focality_specific_without_non_roi_raises(self):
        with pytest.raises(ValueError, match="non_roi"):
            _make_flex_config(
                goal="focality_tf",
                non_roi_method="specific",
                non_roi=None,
            )

    def test_threshold_free_focality_specific_with_non_roi_is_valid(self):
        cfg = _make_flex_config(
            goal="focality_tf",
            non_roi_method="specific",
            non_roi=SphericalROI(x=10, y=10, z=10),
        )
        assert cfg.non_roi is not None

    def test_threshold_free_focality_does_not_require_thresholds(self):
        # Threshold-free goal: no thresholds set, still valid.
        cfg = _make_flex_config(goal="focality_tf")
        assert cfg.thresholds is None

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
# FlexConfig -- intensity weight (threshold-free focality)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexConfigIntensityWeight:
    """The [0, 1] weight trading ROI intensity against focality."""

    def test_defaults_to_balanced_form(self):
        assert _make_flex_config().intensity_weight == 0.0

    @pytest.mark.parametrize("weight", [0.0, 0.5, 1.0])
    def test_accepts_values_in_range(self, weight):
        cfg = _make_flex_config(goal="focality_tf", intensity_weight=weight)
        assert cfg.intensity_weight == weight

    @pytest.mark.parametrize("weight", [-0.1, 1.1])
    def test_rejects_values_out_of_range(self, weight):
        with pytest.raises(ValueError, match="intensity_weight"):
            _make_flex_config(goal="focality_tf", intensity_weight=weight)

    def test_coerced_to_float(self):
        cfg = _make_flex_config(intensity_weight="0.25")
        assert cfg.intensity_weight == 0.25
        assert isinstance(cfg.intensity_weight, float)


# ---------------------------------------------------------------------------
# FlexConfig -- current-ratio search
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexConfigCurrentRatio:
    """Opt-in joint search over the channel current split."""

    def test_ratio_search_defaults_off(self):
        cfg = _make_flex_config()
        assert cfg.optimize_current_ratio is False
        assert cfg.ratio_total_mA is None
        assert cfg.ratio_levels == 21

    def test_ratio_total_can_be_set_explicitly(self):
        cfg = _make_flex_config(optimize_current_ratio=True, ratio_total_mA=6.0)
        assert cfg.ratio_total_mA == 6.0

    def test_ratio_levels_coerced_to_int(self):
        cfg = _make_flex_config(optimize_current_ratio=True, ratio_levels="9")
        assert cfg.ratio_levels == 9

    def test_two_levels_is_the_minimum(self):
        cfg = _make_flex_config(optimize_current_ratio=True, ratio_levels=2)
        assert cfg.ratio_levels == 2

    @pytest.mark.parametrize("levels", [1, 0, -3])
    def test_too_few_levels_raises_when_ratio_search_enabled(self, levels):
        with pytest.raises(ValueError, match="ratio_levels"):
            _make_flex_config(optimize_current_ratio=True, ratio_levels=levels)

    def test_levels_unvalidated_when_ratio_search_disabled(self):
        # The field is inert unless the search is on, so it must not raise.
        cfg = _make_flex_config(optimize_current_ratio=False, ratio_levels=1)
        assert cfg.ratio_levels == 1

    @pytest.mark.parametrize("goal", ["mean", "max", "focality", "focality_tf"])
    def test_ratio_search_allowed_for_every_goal(self, goal):
        # The ROC goal additionally needs explicit thresholds; see
        # TestFlexConfigRatioSearchThresholds.
        extra = {"thresholds": "0.1,0.2"} if goal == "focality" else {}
        cfg = _make_flex_config(goal=goal, optimize_current_ratio=True, **extra)
        assert cfg.optimize_current_ratio is True

    # -- ratio_total_mA -----------------------------------------------------

    @pytest.mark.parametrize("total", [0.0, -0.5, -6.0])
    def test_non_positive_ratio_total_raises(self, total):
        with pytest.raises(ValueError) as exc:
            _make_flex_config(optimize_current_ratio=True, ratio_total_mA=total)
        message = str(exc.value)
        assert "ratio_total_mA" in message
        # Actionable: says how to get the default back.
        assert "None" in message

    def test_zero_ratio_total_is_not_silently_defaulted(self):
        # 0.0 is falsy, so an `or`-based default would swallow it and quietly
        # run the search at 2 * current_mA instead of failing.
        with pytest.raises(ValueError, match="ratio_total_mA"):
            _make_flex_config(optimize_current_ratio=True, ratio_total_mA=0.0)

    def test_ratio_total_validated_even_when_the_search_is_off(self):
        with pytest.raises(ValueError, match="ratio_total_mA"):
            _make_flex_config(optimize_current_ratio=False, ratio_total_mA=-2.0)

    def test_ratio_total_coerced_to_float(self):
        cfg = _make_flex_config(optimize_current_ratio=True, ratio_total_mA="6")
        assert cfg.ratio_total_mA == 6.0
        assert isinstance(cfg.ratio_total_mA, float)

    def test_ratio_total_none_stays_none_as_the_default_sentinel(self):
        # None -- not 0.0 -- is what means "use 2 * current_mA".
        cfg = _make_flex_config(optimize_current_ratio=True, ratio_total_mA=None)
        assert cfg.ratio_total_mA is None


# ---------------------------------------------------------------------------
# FlexConfig -- ratio search with the ROC focality goal
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexConfigRatioSearchThresholds:
    """The ratio search scores ROC focality itself, so it needs thresholds.

    SimNIBS supplies its own defaults for ``goal="focality"``, but the
    current-ratio search evaluates the ROC measure from Python and has nothing
    to fall back on -- so the combination is rejected up front instead of
    failing inside the ``simnibs_python -m tit.opt.flex`` child process.
    """

    @pytest.mark.parametrize(
        "thresholds", [None, "", "dynamic", "auto", "AUTO", "  Dynamic  "]
    )
    def test_roc_focality_ratio_search_without_usable_thresholds_raises(
        self, thresholds
    ):
        with pytest.raises(ValueError) as exc:
            _make_flex_config(
                goal="focality",
                optimize_current_ratio=True,
                thresholds=thresholds,
            )
        message = str(exc.value)
        # Actionable: names every field the user could change.
        assert "optimize_current_ratio" in message
        assert "focality" in message
        assert "thresholds" in message

    def test_placeholder_gives_the_actionable_message_not_a_float_error(self):
        # The gate runs before the numeric parse, so "dynamic" produces the
        # explanation rather than a bare float() conversion error.
        with pytest.raises(ValueError) as exc:
            _make_flex_config(
                goal="focality", optimize_current_ratio=True, thresholds="dynamic"
            )
        message = str(exc.value)
        assert "could not convert" not in message
        assert "optimize_current_ratio" in message

    def test_roc_focality_ratio_search_with_thresholds_is_accepted(self):
        cfg = _make_flex_config(
            goal="focality", optimize_current_ratio=True, thresholds="0.1,0.2"
        )
        assert cfg.optimize_current_ratio is True
        assert cfg.thresholds == "0.1,0.2"

    def test_a_single_threshold_is_enough(self):
        cfg = _make_flex_config(
            goal="focality", optimize_current_ratio=True, thresholds="0.2"
        )
        assert cfg.thresholds == "0.2"

    def test_roc_focality_without_the_ratio_search_needs_no_thresholds(self):
        # Unchanged behaviour: SimNIBS picks its own defaults.
        cfg = _make_flex_config(goal="focality")
        assert cfg.thresholds is None
        assert cfg.optimize_current_ratio is False

    @pytest.mark.parametrize("goal", ["mean", "max", "focality_tf"])
    def test_other_goals_need_no_thresholds_for_the_ratio_search(self, goal):
        cfg = _make_flex_config(goal=goal, optimize_current_ratio=True)
        assert cfg.thresholds is None
        assert cfg.optimize_current_ratio is True


# ---------------------------------------------------------------------------
# FlexConfig -- detailed_results vs callable goals
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexConfigDetailedResults:
    """detailed_results cannot be combined with a Python-callable goal.

    SimNIBS writes ``opt.goal`` into its detailed-results HDF5 file and h5py
    cannot serialise a function.  That failure fires only after the (possibly
    hours-long) optimization finishes, so the config rejects it up front.
    """

    def test_allowed_on_its_own(self):
        cfg = _make_flex_config(detailed_results=True)
        assert cfg.detailed_results is True

    def test_allowed_with_the_roc_focality_goal(self):
        cfg = _make_flex_config(
            goal="focality", thresholds="0.1,0.2", detailed_results=True
        )
        assert cfg.detailed_results is True

    def test_rejected_with_threshold_free_focality(self):
        with pytest.raises(ValueError) as exc:
            _make_flex_config(goal="focality_tf", detailed_results=True)
        message = str(exc.value)
        assert "detailed_results" in message
        assert "focality_tf" in message
        assert "Set detailed_results=False" in message

    def test_rejected_with_the_ratio_search(self):
        with pytest.raises(ValueError) as exc:
            _make_flex_config(
                goal="mean", optimize_current_ratio=True, detailed_results=True
            )
        message = str(exc.value)
        assert "detailed_results" in message
        assert "optimize_current_ratio" in message
        assert "Set detailed_results=False" in message

    def test_message_names_the_goal_when_both_triggers_apply(self):
        with pytest.raises(ValueError) as exc:
            _make_flex_config(
                goal="focality_tf", optimize_current_ratio=True, detailed_results=True
            )
        assert "focality_tf" in str(exc.value)

    def test_default_is_off_so_callable_goal_configs_build(self):
        cfg = _make_flex_config(goal="focality_tf", optimize_current_ratio=True)
        assert cfg.detailed_results is False

    @pytest.mark.parametrize("goal", ["mean", "max", "focality_tf"])
    def test_detailed_results_false_is_always_accepted(self, goal):
        cfg = _make_flex_config(
            goal=goal, optimize_current_ratio=True, detailed_results=False
        )
        assert cfg.detailed_results is False


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


@pytest.mark.unit
class TestSearchModeBackend:
    """The TI/mTI mode -> backend mapping.

    Lives in ``tit.opt.config`` rather than the GUI so the wiring is testable
    without a display; PyQt5 is absent from the host test environment.
    """

    def test_ti_mode_selects_ex_backend(self):
        from tit.opt.config import SEARCH_MODE_TI, ExConfig, search_backend_for_mode

        assert search_backend_for_mode(SEARCH_MODE_TI) == ("tit.opt.ex", ExConfig)

    def test_mti_mode_selects_mex_backend(self):
        from tit.opt.config import SEARCH_MODE_MTI, MExConfig, search_backend_for_mode

        assert search_backend_for_mode(SEARCH_MODE_MTI) == ("tit.opt.mex", MExConfig)

    def test_unknown_mode_raises(self):
        from tit.opt.config import search_backend_for_mode

        with pytest.raises(ValueError, match="Unknown search mode"):
            search_backend_for_mode("nope")

    def test_two_carrier_architecture_maps_to_paired_channels(self):
        """Pairs 1&3 share one carrier, 2&4 the other (Lee et al. 2022)."""
        from tit.opt.config import MTI_CHANNEL_ARCHITECTURES

        arch = dict(MTI_CHANNEL_ARCHITECTURES)
        assert arch["Two independent channels"] is None
        assert arch["Four pairs, two carriers"] == [([0, 2], [1, 3])]
