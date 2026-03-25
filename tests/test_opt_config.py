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
