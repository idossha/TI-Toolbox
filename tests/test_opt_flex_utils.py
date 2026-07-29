"""Tests for tit/opt/flex/utils.py -- ROI configuration and output naming.

Supplements test_flex_manifest.py which already covers generate_run_dirname,
generate_label, and parse_optimization_output. This file covers configure_roi
and the private _configure_* functions.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.config import FlexConfig

# Convenience aliases for nested types
SphericalROI = FlexConfig.SphericalROI
AtlasROI = FlexConfig.AtlasROI
SubcorticalROI = FlexConfig.SubcorticalROI
FlexElectrodeConfig = FlexConfig.ElectrodeConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    defaults = dict(
        subject_id="001",
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexElectrodeConfig(),
        roi=SphericalROI(x=-42, y=-20, z=55, radius=10),
    )
    defaults.update(overrides)
    return FlexConfig(**defaults)


# ---------------------------------------------------------------------------
# configure_roi -- spherical
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigureSphericalROI:
    def test_basic_spherical(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(roi=SphericalROI(x=10, y=20, z=30, radius=15))
        configure_roi(opt, config)

        opt.add_roi.assert_called_once()
        assert roi_mock.method == "surface"
        assert roi_mock.surface_type == "central"
        assert roi_mock.roi_sphere_center == [10, 20, 30]
        assert roi_mock.roi_sphere_radius == 15

    def test_spherical_with_mni(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(x=-42, y=-20, z=55, radius=10, use_mni=True),
        )
        configure_roi(opt, config)

        assert roi_mock.roi_sphere_center_space == "mni"
        assert roi_mock.roi_sphere_center == [-42, -20, 55]

    def test_spherical_focality_everything_else(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            roi=SphericalROI(x=10, y=20, z=30, radius=10),
        )
        configure_roi(opt, config)

        assert opt.add_roi.call_count == 2
        assert non_roi_mock.roi_sphere_operator == ["difference"]
        assert non_roi_mock.weight == -1

    def test_spherical_focality_specific(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="specific",
            roi=SphericalROI(x=10, y=20, z=30, radius=10),
            non_roi=SphericalROI(x=-10, y=-20, z=-30, radius=15),
        )
        configure_roi(opt, config)

        assert non_roi_mock.roi_sphere_center == [-10, -20, -30]
        assert non_roi_mock.roi_sphere_radius == 15
        assert non_roi_mock.weight == -1

    def test_spherical_focality_specific_mni_non_roi(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="specific",
            roi=SphericalROI(x=10, y=20, z=30, radius=10, use_mni=True),
            non_roi=SphericalROI(x=-10, y=-20, z=-30, radius=15, use_mni=True),
        )
        configure_roi(opt, config)

        assert roi_mock.roi_sphere_center_space == "mni"
        assert roi_mock.roi_sphere_center == [10, 20, 30]
        assert non_roi_mock.roi_sphere_center_space == "mni"
        assert non_roi_mock.roi_sphere_center == [-10, -20, -30]

    def test_zero_coords_no_warning(self):
        """(0,0,0) in subject space is valid — no warning should be emitted."""
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(x=0, y=0, z=0, radius=10, use_mni=False),
        )
        with patch("tit.opt.flex.utils.log") as mock_log:
            configure_roi(opt, config)
            mock_log.warning.assert_not_called()

    def test_volumetric_sphere_uses_volume_method(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(
                x=-24, y=-4, z=-20, radius=8, volumetric=True, tissues="GM"
            ),
        )
        configure_roi(opt, config)

        opt.add_roi.assert_called_once()
        assert roi_mock.method == "volume"
        assert roi_mock.roi_sphere_center == [-24, -4, -20]
        assert roi_mock.roi_sphere_radius == 8
        # tissues should be set (list of ElementTags)
        assert roi_mock.tissues is not None
        assert len(roi_mock.tissues) == 1

    def test_volumetric_sphere_both_tissues(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(
                x=-24, y=-4, z=-20, radius=8, volumetric=True, tissues="both"
            ),
        )
        configure_roi(opt, config)

        assert roi_mock.method == "volume"
        assert len(roi_mock.tissues) == 2

    def test_volumetric_sphere_focality_everything_else(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            roi=SphericalROI(
                x=-24, y=-4, z=-20, radius=8, volumetric=True, tissues="GM"
            ),
        )
        configure_roi(opt, config)

        assert opt.add_roi.call_count == 2
        assert roi_mock.method == "volume"
        assert non_roi_mock.method == "volume"
        assert non_roi_mock.roi_sphere_operator == ["difference"]
        assert non_roi_mock.weight == -1
        # non-ROI should inherit tissue tags
        assert non_roi_mock.tissues == roi_mock.tissues

    def test_volumetric_false_preserves_surface(self):
        """Default volumetric=False should keep surface method."""
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(x=10, y=20, z=30, radius=15, volumetric=False),
        )
        configure_roi(opt, config)

        assert roi_mock.method == "surface"
        assert roi_mock.surface_type == "central"

    def test_volumetric_sphere_with_mni(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(
                x=-24,
                y=-4,
                z=-20,
                radius=8,
                use_mni=True,
                volumetric=True,
                tissues="WM",
            ),
        )
        configure_roi(opt, config)

        assert roi_mock.method == "volume"
        assert roi_mock.roi_sphere_center_space == "mni"
        assert roi_mock.roi_sphere_center == [-24, -4, -20]
        assert len(roi_mock.tissues) == 1


# ---------------------------------------------------------------------------
# configure_roi -- atlas
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigureAtlasROI:
    def test_basic_atlas(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=AtlasROI(
                atlas_path="/path/to/lh.aparc.annot", label=1001, hemisphere="lh"
            ),
        )
        configure_roi(opt, config)

        assert roi_mock.method == "surface"
        assert roi_mock.mask_space == ["subject_lh"]
        assert roi_mock.mask_path == ["/path/to/lh.aparc.annot"]
        assert roi_mock.mask_value == [1001]

    def test_atlas_focality_everything_else(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            roi=AtlasROI(
                atlas_path="/path/to/lh.aparc.annot", label=1001, hemisphere="lh"
            ),
        )
        configure_roi(opt, config)

        assert non_roi_mock.mask_operator == ["difference"]
        assert non_roi_mock.weight == -1

    def test_atlas_focality_specific(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="specific",
            roi=AtlasROI(
                atlas_path="/path/to/lh.aparc.annot", label=1001, hemisphere="lh"
            ),
            non_roi=AtlasROI(
                atlas_path="/path/to/lh.other.annot", label=2001, hemisphere="lh"
            ),
        )
        configure_roi(opt, config)

        assert non_roi_mock.mask_path == ["/path/to/lh.other.annot"]
        assert non_roi_mock.mask_value == [2001]
        assert non_roi_mock.weight == -1


# ---------------------------------------------------------------------------
# configure_roi -- subcortical
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigureSubcorticalROI:
    def test_basic_subcortical(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SubcorticalROI(atlas_path=str(atlas_file), label=11, tissues="GM"),
        )
        configure_roi(opt, config)

        assert roi_mock.method == "volume"
        assert roi_mock.mask_space == ["subject"]
        assert roi_mock.mask_path == [str(atlas_file)]
        assert roi_mock.mask_value == [11]

    def test_mni_subcortical(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "mni_atlas.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SubcorticalROI(
                atlas_path=str(atlas_file),
                label=11,
                atlas_space="mni",
                tissues="GM",
            ),
        )
        configure_roi(opt, config)

        assert roi_mock.method == "volume"
        assert roi_mock.mask_space == ["mni"]
        assert roi_mock.mask_path == [str(atlas_file)]
        assert roi_mock.mask_value == [11]

    def test_subcortical_rejects_unknown_atlas_space(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "atlas.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        config = _make_config(
            roi=SubcorticalROI(
                atlas_path=str(atlas_file),
                label=11,
                atlas_space="native",  # type: ignore[arg-type]
            ),
        )

        with pytest.raises(ValueError, match="atlas_space"):
            configure_roi(opt, config)

    def test_subcortical_missing_atlas(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        config = _make_config(
            roi=SubcorticalROI(atlas_path="/nonexistent/file.nii.gz", label=11),
        )

        with pytest.raises(FileNotFoundError):
            configure_roi(opt, config)

    def test_subcortical_focality_everything_else(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            roi=SubcorticalROI(atlas_path=str(atlas_file), label=11),
        )
        configure_roi(opt, config)

        assert non_roi_mock.mask_operator == ["difference"]
        assert non_roi_mock.weight == -1

    def test_subcortical_focality_specific(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")
        non_roi_file = tmp_path / "other.nii.gz"
        non_roi_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="specific",
            roi=SubcorticalROI(atlas_path=str(atlas_file), label=11),
            non_roi=SubcorticalROI(atlas_path=str(non_roi_file), label=22),
        )
        configure_roi(opt, config)

        assert non_roi_mock.mask_path == [str(non_roi_file)]
        assert non_roi_mock.mask_value == [22]
        assert non_roi_mock.weight == -1

    def test_subcortical_focality_specific_preserves_non_roi_atlas_space(
        self, tmp_path
    ):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")
        non_roi_file = tmp_path / "mni_atlas.nii.gz"
        non_roi_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="specific",
            roi=SubcorticalROI(atlas_path=str(atlas_file), label=11),
            non_roi=SubcorticalROI(
                atlas_path=str(non_roi_file),
                label=22,
                atlas_space="mni",
            ),
        )
        configure_roi(opt, config)

        assert roi_mock.mask_space == ["subject"]
        assert non_roi_mock.mask_space == ["mni"]

    def test_subcortical_focality_specific_missing_non_roi(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="specific",
            roi=SubcorticalROI(atlas_path=str(atlas_file), label=11),
            non_roi=SubcorticalROI(atlas_path="/nonexistent.nii.gz", label=22),
        )

        with pytest.raises(FileNotFoundError):
            configure_roi(opt, config)


# ---------------------------------------------------------------------------
# configure_roi -- unknown type
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigureROIUnknown:
    def test_unknown_roi_type(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        config = _make_config()
        config.roi = "not_a_valid_roi"

        with pytest.raises(ValueError, match="Unknown ROI type"):
            configure_roi(opt, config)


# ---------------------------------------------------------------------------
# _resolve_roi_tissues
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveRoiTissues:
    def test_gm_default(self):
        from tit.opt.flex.utils import _resolve_roi_tissues
        from simnibs.mesh_tools.mesh_io import ElementTags

        config = _make_config(
            roi=SubcorticalROI(atlas_path="/fake", label=11, tissues="GM"),
        )
        result = _resolve_roi_tissues(config)
        assert len(result) == 1

    def test_wm_tissue(self):
        from tit.opt.flex.utils import _resolve_roi_tissues

        config = _make_config(
            roi=SubcorticalROI(atlas_path="/fake", label=11, tissues="WM"),
        )
        result = _resolve_roi_tissues(config)
        assert len(result) == 1

    def test_both_tissues(self):
        from tit.opt.flex.utils import _resolve_roi_tissues

        config = _make_config(
            roi=SubcorticalROI(atlas_path="/fake", label=11, tissues="BOTH"),
        )
        result = _resolve_roi_tissues(config)
        assert len(result) == 2

    def test_unknown_defaults_to_gm(self):
        from tit.opt.flex.utils import _resolve_roi_tissues

        config = _make_config(
            roi=SubcorticalROI(atlas_path="/fake", label=11, tissues="xyz"),
        )
        result = _resolve_roi_tissues(config)
        assert len(result) == 1  # defaults to GM


# ---------------------------------------------------------------------------
# generate_label edge cases (supplement to test_flex_manifest.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateLabelEdgeCases:
    def test_unknown_roi_type_label(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config()
        config.roi = "something_else"
        label = generate_label(config)
        assert "unknown" in label

    def test_tangential_postproc(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config(postproc="dir_TI_tangential")
        label = generate_label(config)
        assert "tangentialTI" in label

    def test_subcortical_mgz_extension(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config(
            roi=SubcorticalROI(atlas_path="/path/to/aseg.mgz", label=11),
        )
        label = generate_label(config)
        assert "aseg" in label
        assert ".mgz" not in label

    def test_subcortical_nii_extension(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config(
            roi=SubcorticalROI(atlas_path="/path/to/atlas.nii", label=17),
        )
        label = generate_label(config)
        assert "atlas" in label
        assert ".nii" not in label

    def test_spherical_float_coords(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config(
            roi=SphericalROI(x=10.5, y=-20.5, z=55.5, radius=10.5),
        )
        label = generate_label(config)
        assert "10.5" in label
        assert "-20.5" in label


# ---------------------------------------------------------------------------
# Union of same-type ROIs (multi-region targets)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigureAtlasUnion:
    def test_two_label_same_hemisphere(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=AtlasROI(
                atlas_path="/path/to/lh.aparc.annot",
                label=[1001, 1002],
                hemisphere="lh",
            ),
        )
        configure_roi(opt, config)

        assert roi_mock.mask_value == [1001, 1002]
        # atlas_path broadcast to match the label list
        assert roi_mock.mask_path == [
            "/path/to/lh.aparc.annot",
            "/path/to/lh.aparc.annot",
        ]
        assert roi_mock.mask_space == ["subject_lh", "subject_lh"]
        # First fold intersects the all-True base, the rest union on.
        assert roi_mock.mask_operator == ["intersection", "union"]

    def test_cross_hemisphere_union(self):
        """Two entries with differing mask_path AND mask_space (lh + rh)."""
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=AtlasROI(
                atlas_path=["/path/to/lh.aparc.annot", "/path/to/rh.aparc.annot"],
                label=[17, 53],
                hemisphere=["lh", "rh"],
            ),
        )
        configure_roi(opt, config)

        assert roi_mock.mask_value == [17, 53]
        assert roi_mock.mask_path == [
            "/path/to/lh.aparc.annot",
            "/path/to/rh.aparc.annot",
        ]
        assert roi_mock.mask_space == ["subject_lh", "subject_rh"]
        assert roi_mock.mask_operator == ["intersection", "union"]

    def test_union_focality_everything_else_complement_length(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            roi=AtlasROI(
                atlas_path="/path/to/lh.aparc.annot",
                label=[1001, 1002],
                hemisphere="lh",
            ),
        )
        configure_roi(opt, config)

        # Complement operator length must equal the ROI mask length (N=2).
        assert non_roi_mock.mask_operator == ["difference", "difference"]
        assert len(non_roi_mock.mask_operator) == len(roi_mock.mask_value)
        assert non_roi_mock.weight == -1


@pytest.mark.unit
class TestConfigureSubcorticalUnion:
    def test_two_label_shared_atlas(self, tmp_path):
        """Both hippocampi (17, 53) from one aseg atlas."""
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SubcorticalROI(atlas_path=str(atlas_file), label=[17, 53]),
        )
        configure_roi(opt, config)

        assert roi_mock.mask_value == [17, 53]
        assert roi_mock.mask_path == [str(atlas_file), str(atlas_file)]
        assert roi_mock.mask_space == ["subject", "subject"]
        assert roi_mock.mask_operator == ["intersection", "union"]

    def test_union_focality_complement_length(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            roi=SubcorticalROI(atlas_path=str(atlas_file), label=[17, 53]),
        )
        configure_roi(opt, config)

        assert non_roi_mock.mask_operator == ["difference", "difference"]
        assert len(non_roi_mock.mask_operator) == len(roi_mock.mask_value)

    def test_union_missing_one_atlas_raises(self, tmp_path):
        from tit.opt.flex.utils import configure_roi

        atlas_file = tmp_path / "aseg.nii.gz"
        atlas_file.write_text("fake")

        opt = MagicMock()
        opt.add_roi.return_value = MagicMock()

        config = _make_config(
            roi=SubcorticalROI(
                atlas_path=[str(atlas_file), "/nonexistent.nii.gz"],
                label=[17, 53],
            ),
        )
        with pytest.raises(FileNotFoundError):
            configure_roi(opt, config)


@pytest.mark.unit
class TestConfigureSphericalUnion:
    def test_two_sphere_union(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(x=[10, -10], y=[20, -20], z=[30, -30], radius=[8, 12]),
        )
        configure_roi(opt, config)

        assert roi_mock.roi_sphere_center == [[10, 20, 30], [-10, -20, -30]]
        assert roi_mock.roi_sphere_radius == [8, 12]
        assert roi_mock.roi_sphere_center_space == ["subject", "subject"]
        assert roi_mock.roi_sphere_operator == ["intersection", "union"]

    def test_two_sphere_shared_radius_broadcast(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(x=[10, -10], y=[20, -20], z=[30, -30], radius=9),
        )
        configure_roi(opt, config)

        assert roi_mock.roi_sphere_radius == [9, 9]

    def test_single_sphere_back_compat_flat(self):
        """Scalar sphere keeps the flat (non-nested) form, no operator set."""
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(roi=SphericalROI(x=10, y=20, z=30, radius=15))
        configure_roi(opt, config)

        assert roi_mock.roi_sphere_center == [10, 20, 30]
        assert roi_mock.roi_sphere_radius == 15

    def test_union_focality_complement_length(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        non_roi_mock = MagicMock()
        opt.add_roi.side_effect = [roi_mock, non_roi_mock]

        config = _make_config(
            goal="focality",
            non_roi_method="everything_else",
            roi=SphericalROI(x=[10, -10], y=[20, -20], z=[30, -30], radius=8),
        )
        configure_roi(opt, config)

        assert non_roi_mock.roi_sphere_operator == ["difference", "difference"]
        assert non_roi_mock.roi_sphere_center == [[10, 20, 30], [-10, -20, -30]]
        assert non_roi_mock.weight == -1


@pytest.mark.unit
class TestUnionLabelRendering:
    def test_generate_label_atlas_union_joined(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config(
            roi=AtlasROI(
                atlas_path=["/path/to/lh.aparc.annot", "/path/to/rh.aparc.annot"],
                label=[17, 53],
                hemisphere=["lh", "rh"],
            ),
        )
        label = generate_label(config)
        assert "17+53" in label
        assert "lh+rh" in label
        assert "[" not in label and "]" not in label

    def test_generate_label_subcortical_union_joined(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config(
            roi=SubcorticalROI(atlas_path="/path/to/aseg.nii.gz", label=[17, 53]),
        )
        label = generate_label(config)
        assert "17+53" in label
        assert "[" not in label

    def test_generate_label_sphere_union_joined(self):
        from tit.opt.flex.utils import generate_label

        config = _make_config(
            roi=SphericalROI(x=[10, -10], y=[20, -20], z=[30, -30], radius=8),
        )
        label = generate_label(config)
        assert label.count("sphere(") == 2
        assert "+" in label


@pytest.mark.unit
class TestUnionConfigValidation:
    def test_atlas_hemisphere_length_mismatch_raises(self):
        # length 3 hemisphere neither broadcasts (1) nor matches label count (2)
        with pytest.raises(ValueError, match="hemisphere"):
            AtlasROI(
                atlas_path="/a.annot", label=[17, 53], hemisphere=["lh", "rh", "lh"]
            )

    def test_atlas_single_hemisphere_broadcasts(self):
        # A single hemisphere is valid and broadcasts across all labels.
        roi = AtlasROI(atlas_path="/a.annot", label=[17, 53], hemisphere="lh")
        assert roi.label == [17, 53]

    def test_atlas_empty_label_raises(self):
        with pytest.raises(ValueError, match="label"):
            AtlasROI(atlas_path="/a.annot", label=[])

    def test_sphere_unequal_coords_raise(self):
        with pytest.raises(ValueError, match="equal length"):
            SphericalROI(x=[1, 2], y=[3], z=[5, 6])

    def test_sphere_bad_radius_length_raises(self):
        with pytest.raises(ValueError, match="radius"):
            SphericalROI(x=[1, 2], y=[3, 4], z=[5, 6], radius=[1, 2, 3])

    def test_subcortical_atlas_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="atlas_path"):
            SubcorticalROI(atlas_path=["/a.nii.gz", "/b.nii.gz"], label=[1, 2, 3])
