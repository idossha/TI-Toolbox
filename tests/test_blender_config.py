"""Unit tests for tit/blender/config.py -- Blender export configuration dataclasses.

Covers:
- Enum value checks (RegionConfig.Format, VectorConfig.Color/Anchor/Length, RegionConfig.Surface)
- MontageConfig construction, defaults, and validation
- VectorConfig construction, defaults, enum coercion, is_mti property, validation
- RegionConfig construction, defaults, enum coercion, and validation
"""

import pytest

from tit.blender.config import (
    MontageConfig,
    RegionConfig,
    VectorConfig,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestRegionFormat:
    """RegionConfig.Format enum values."""

    def test_stl_value(self):
        assert RegionConfig.Format.STL.value == "stl"

    def test_ply_value(self):
        assert RegionConfig.Format.PLY.value == "ply"

    def test_from_string(self):
        assert RegionConfig.Format("stl") is RegionConfig.Format.STL
        assert RegionConfig.Format("ply") is RegionConfig.Format.PLY

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            RegionConfig.Format("obj")


class TestVectorColor:
    """VectorConfig.Color enum values."""

    def test_rgb_value(self):
        assert VectorConfig.Color.RGB.value == "rgb"

    def test_magscale_value(self):
        assert VectorConfig.Color.MAGSCALE.value == "magscale"

    def test_from_string(self):
        assert VectorConfig.Color("rgb") is VectorConfig.Color.RGB
        assert VectorConfig.Color("magscale") is VectorConfig.Color.MAGSCALE

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            VectorConfig.Color("hsv")


class TestVectorAnchor:
    """VectorConfig.Anchor enum values."""

    def test_tail_value(self):
        assert VectorConfig.Anchor.TAIL.value == "tail"

    def test_head_value(self):
        assert VectorConfig.Anchor.HEAD.value == "head"

    def test_from_string(self):
        assert VectorConfig.Anchor("tail") is VectorConfig.Anchor.TAIL
        assert VectorConfig.Anchor("head") is VectorConfig.Anchor.HEAD


class TestVectorLength:
    """VectorConfig.Length enum values."""

    def test_linear_value(self):
        assert VectorConfig.Length.LINEAR.value == "linear"

    def test_visual_value(self):
        assert VectorConfig.Length.VISUAL.value == "visual"

    def test_from_string(self):
        assert VectorConfig.Length("linear") is VectorConfig.Length.LINEAR
        assert VectorConfig.Length("visual") is VectorConfig.Length.VISUAL


class TestRegionSurface:
    """RegionConfig.Surface enum values."""

    def test_central_value(self):
        assert RegionConfig.Surface.CENTRAL.value == "central"

    def test_pial_value(self):
        assert RegionConfig.Surface.PIAL.value == "pial"

    def test_white_value(self):
        assert RegionConfig.Surface.WHITE.value == "white"

    def test_from_string(self):
        assert RegionConfig.Surface("central") is RegionConfig.Surface.CENTRAL
        assert RegionConfig.Surface("pial") is RegionConfig.Surface.PIAL
        assert RegionConfig.Surface("white") is RegionConfig.Surface.WHITE


# ---------------------------------------------------------------------------
# MontageConfig
# ---------------------------------------------------------------------------


def _montage(**overrides):
    """Build a valid MontageConfig with sensible defaults."""
    defaults = dict(
        subject_id="001",
        simulation_name="sim_A",
    )
    defaults.update(overrides)
    return MontageConfig(**defaults)


class TestMontageConfig:
    """MontageConfig construction and validation."""

    def test_required_fields(self):
        cfg = _montage()
        assert cfg.subject_id == "001"
        assert cfg.simulation_name == "sim_A"

    def test_default_values(self):
        cfg = _montage()
        assert cfg.output_dir is None
        assert cfg.show_full_net is True
        assert cfg.electrode_diameter_mm == 10.0
        assert cfg.electrode_height_mm == 6.0
        assert cfg.export_glb is False

    def test_custom_values(self):
        cfg = _montage(
            output_dir="/out",
            show_full_net=False,
            electrode_diameter_mm=12.0,
            electrode_height_mm=8.0,
            export_glb=True,
        )
        assert cfg.output_dir == "/out"
        assert cfg.show_full_net is False
        assert cfg.electrode_diameter_mm == 12.0
        assert cfg.electrode_height_mm == 8.0
        assert cfg.export_glb is True

    def test_empty_subject_id_raises(self):
        with pytest.raises(ValueError, match="subject_id is required"):
            _montage(subject_id="")

    def test_whitespace_subject_id_raises(self):
        with pytest.raises(ValueError, match="subject_id is required"):
            _montage(subject_id="   ")

    def test_none_subject_id_raises(self):
        with pytest.raises(ValueError, match="subject_id is required"):
            _montage(subject_id=None)

    def test_empty_simulation_name_raises(self):
        with pytest.raises(ValueError, match="simulation_name is required"):
            _montage(simulation_name="")

    def test_negative_electrode_diameter_raises(self):
        with pytest.raises(ValueError, match="electrode_diameter_mm must be > 0"):
            _montage(electrode_diameter_mm=-1.0)

    def test_zero_electrode_diameter_raises(self):
        with pytest.raises(ValueError, match="electrode_diameter_mm must be > 0"):
            _montage(electrode_diameter_mm=0.0)

    def test_negative_electrode_height_raises(self):
        with pytest.raises(ValueError, match="electrode_height_mm must be > 0"):
            _montage(electrode_height_mm=-2.0)

    def test_zero_electrode_height_raises(self):
        with pytest.raises(ValueError, match="electrode_height_mm must be > 0"):
            _montage(electrode_height_mm=0.0)


# ---------------------------------------------------------------------------
# VectorConfig
# ---------------------------------------------------------------------------


def _vector(**overrides):
    """Build a valid VectorConfig with sensible defaults."""
    defaults = dict(
        mesh1="/mesh1.msh",
        mesh2="/mesh2.msh",
        output_dir="/out",
        central_surface="/central.msh",
    )
    defaults.update(overrides)
    return VectorConfig(**defaults)


class TestVectorConfig:
    """VectorConfig construction, coercion, and validation."""

    def test_required_fields(self):
        cfg = _vector()
        assert cfg.mesh1 == "/mesh1.msh"
        assert cfg.mesh2 == "/mesh2.msh"
        assert cfg.output_dir == "/out"
        assert cfg.central_surface == "/central.msh"

    def test_default_values(self):
        cfg = _vector()
        assert cfg.mesh3 is None
        assert cfg.mesh4 is None
        assert cfg.export_ch1_ch2 is False
        assert cfg.export_sum is False
        assert cfg.export_ti_normal is False
        assert cfg.export_combined is False
        assert cfg.top_percent is None
        assert cfg.count == 100_000
        assert cfg.all_nodes is False
        assert cfg.seed == 42
        assert cfg.length_mode is VectorConfig.Length.LINEAR
        assert cfg.length_scale == 1.0
        assert cfg.vector_scale == 1.0
        assert cfg.vector_width == 1.0
        assert cfg.vector_length == 1.0
        assert cfg.anchor is VectorConfig.Anchor.TAIL
        assert cfg.color is VectorConfig.Color.RGB
        assert cfg.blue_percentile == 50.0
        assert cfg.green_percentile == 80.0
        assert cfg.red_percentile == 95.0
        assert cfg.verbose is False

    # -- is_mti property --

    def test_is_mti_false_with_two_meshes(self):
        cfg = _vector()
        assert cfg.is_mti is False

    def test_is_mti_true_with_four_meshes(self):
        cfg = _vector(mesh3="/mesh3.msh", mesh4="/mesh4.msh")
        assert cfg.is_mti is True

    # -- String-to-enum coercion --

    def test_string_color_mode_coerced(self):
        cfg = _vector(color="rgb")
        assert cfg.color is VectorConfig.Color.RGB

    def test_string_color_mode_magscale_coerced(self):
        cfg = _vector(color="magscale")
        assert cfg.color is VectorConfig.Color.MAGSCALE

    def test_string_length_mode_coerced(self):
        cfg = _vector(length_mode="visual")
        assert cfg.length_mode is VectorConfig.Length.VISUAL

    def test_string_anchor_coerced(self):
        cfg = _vector(anchor="head")
        assert cfg.anchor is VectorConfig.Anchor.HEAD

    def test_invalid_color_string_raises(self):
        with pytest.raises(ValueError):
            _vector(color="hsv")

    def test_invalid_length_mode_string_raises(self):
        with pytest.raises(ValueError):
            _vector(length_mode="logarithmic")

    def test_invalid_anchor_string_raises(self):
        with pytest.raises(ValueError):
            _vector(anchor="middle")

    # -- Validation: required paths --

    def test_empty_mesh1_raises(self):
        with pytest.raises(ValueError, match="mesh1 is required"):
            _vector(mesh1="")

    def test_empty_mesh2_raises(self):
        with pytest.raises(ValueError, match="mesh2 is required"):
            _vector(mesh2="")

    def test_empty_output_dir_raises(self):
        with pytest.raises(ValueError, match="output_dir is required"):
            _vector(output_dir="")

    def test_empty_central_surface_raises(self):
        with pytest.raises(ValueError, match="central_surface is required"):
            _vector(central_surface="")

    # -- Validation: mTI requires both mesh3 and mesh4 --

    def test_mesh3_without_mesh4_raises(self):
        with pytest.raises(ValueError, match="both mesh3 and mesh4"):
            _vector(mesh3="/m3.msh", mesh4=None)

    def test_mesh4_without_mesh3_raises(self):
        with pytest.raises(ValueError, match="both mesh3 and mesh4"):
            _vector(mesh3=None, mesh4="/m4.msh")

    # -- Validation: count and top_percent --

    def test_zero_count_raises(self):
        with pytest.raises(ValueError, match="count must be positive"):
            _vector(count=0)

    def test_negative_count_raises(self):
        with pytest.raises(ValueError, match="count must be positive"):
            _vector(count=-10)

    def test_top_percent_zero_raises(self):
        with pytest.raises(ValueError, match="top_percent must be in"):
            _vector(top_percent=0.0)

    def test_top_percent_over_100_raises(self):
        with pytest.raises(ValueError, match="top_percent must be in"):
            _vector(top_percent=101.0)

    def test_top_percent_valid(self):
        cfg = _vector(top_percent=50.0)
        assert cfg.top_percent == 50.0

    def test_top_percent_at_100(self):
        cfg = _vector(top_percent=100.0)
        assert cfg.top_percent == 100.0

    # -- Validation: arrow styling --

    def test_zero_vector_scale_raises(self):
        with pytest.raises(ValueError, match="vector_scale must be positive"):
            _vector(vector_scale=0)

    def test_zero_vector_width_raises(self):
        with pytest.raises(ValueError, match="vector_width must be positive"):
            _vector(vector_width=0)

    def test_zero_vector_length_raises(self):
        with pytest.raises(ValueError, match="vector_length must be positive"):
            _vector(vector_length=0)

    def test_zero_length_scale_raises(self):
        with pytest.raises(ValueError, match="length_scale must be positive"):
            _vector(length_scale=0)

    # -- Validation: percentile range --

    def test_blue_percentile_negative_raises(self):
        with pytest.raises(ValueError, match="blue_percentile"):
            _vector(blue_percentile=-1.0)

    def test_green_percentile_over_100_raises(self):
        with pytest.raises(ValueError, match="green_percentile"):
            _vector(green_percentile=101.0)

    def test_red_percentile_negative_raises(self):
        with pytest.raises(ValueError, match="red_percentile"):
            _vector(red_percentile=-5.0)


# ---------------------------------------------------------------------------
# RegionConfig
# ---------------------------------------------------------------------------


def _region(**overrides):
    """Build a valid RegionConfig with sensible defaults."""
    defaults = dict(
        m2m_dir="/m2m_001",
        output_dir="/out",
        mesh="/central.msh",
    )
    defaults.update(overrides)
    return RegionConfig(**defaults)


class TestRegionConfig:
    """RegionConfig construction, coercion, and validation."""

    def test_required_fields(self):
        cfg = _region()
        assert cfg.m2m_dir == "/m2m_001"
        assert cfg.output_dir == "/out"
        assert cfg.mesh == "/central.msh"

    def test_default_values(self):
        cfg = _region()
        assert cfg.gm_mesh is None
        assert cfg.format is RegionConfig.Format.PLY
        assert cfg.atlas == "DK40"
        assert cfg.surface is RegionConfig.Surface.CENTRAL
        assert cfg.msh2cortex_path is None
        assert cfg.field_name == "TI_max"
        assert cfg.skip_regions is False
        assert cfg.skip_whole_gm is False
        assert cfg.regions == []
        assert cfg.keep_meshes is False
        assert cfg.scalars is False
        assert cfg.colormap == "viridis"
        assert cfg.field_range is None
        assert cfg.global_from_nifti is None

    # -- String-to-enum coercion --

    def test_string_format_stl_coerced(self):
        cfg = _region(format="stl")
        assert cfg.format is RegionConfig.Format.STL

    def test_string_format_ply_coerced(self):
        cfg = _region(format="ply")
        assert cfg.format is RegionConfig.Format.PLY

    def test_string_surface_coerced(self):
        cfg = _region(surface="pial")
        assert cfg.surface is RegionConfig.Surface.PIAL

    def test_enum_format_accepted(self):
        cfg = _region(format=RegionConfig.Format.STL)
        assert cfg.format is RegionConfig.Format.STL

    def test_invalid_format_string_raises(self):
        with pytest.raises(ValueError):
            _region(format="obj")

    def test_invalid_surface_string_raises(self):
        with pytest.raises(ValueError):
            _region(surface="inflated")

    # -- Validation: required paths --

    def test_empty_m2m_dir_raises(self):
        with pytest.raises(ValueError, match="m2m_dir is required"):
            _region(m2m_dir="")

    def test_empty_output_dir_raises(self):
        with pytest.raises(ValueError, match="output_dir is required"):
            _region(output_dir="")

    # -- Validation: mesh vs gm_mesh --

    def test_no_mesh_and_no_gm_mesh_raises(self):
        with pytest.raises(ValueError, match="one of mesh or gm_mesh is required"):
            RegionConfig(m2m_dir="/m2m", output_dir="/out")

    def test_both_mesh_and_gm_mesh_raises(self):
        with pytest.raises(ValueError, match="only one of mesh or gm_mesh"):
            RegionConfig(
                m2m_dir="/m2m",
                output_dir="/out",
                mesh="/a.msh",
                gm_mesh="/b.msh",
            )

    def test_gm_mesh_only(self):
        cfg = RegionConfig(
            m2m_dir="/m2m",
            output_dir="/out",
            gm_mesh="/gm.msh",
        )
        assert cfg.gm_mesh == "/gm.msh"
        assert cfg.mesh is None

    # -- Validation: field_range --

    def test_field_range_valid(self):
        cfg = _region(field_range=(0.0, 1.0))
        assert cfg.field_range == (0.0, 1.0)

    def test_field_range_min_greater_than_max_raises(self):
        with pytest.raises(ValueError, match="field_range min must be <= max"):
            _region(field_range=(5.0, 2.0))

    def test_field_range_wrong_length_raises(self):
        with pytest.raises(ValueError, match="field_range must be a .* pair"):
            _region(field_range=(1.0, 2.0, 3.0))

    def test_field_range_equal_min_max(self):
        cfg = _region(field_range=(3.0, 3.0))
        assert cfg.field_range == (3.0, 3.0)

    # -- Optional fields --

    def test_custom_regions(self):
        cfg = _region(regions=["lh.precentral", "rh.postcentral"])
        assert cfg.regions == ["lh.precentral", "rh.postcentral"]

    def test_scalars_flag(self):
        cfg = _region(scalars=True)
        assert cfg.scalars is True
