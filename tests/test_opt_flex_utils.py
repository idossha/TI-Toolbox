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

from tit.opt.config import (
    AtlasROI,
    FlexConfig,
    FlexElectrodeConfig,
    SphericalROI,
    SubcorticalROI,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    defaults = dict(
        subject_id="001",
        project_dir="/proj",
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
        import simnibs

        simnibs.mni2subject_coords = MagicMock(return_value=[11, 21, 31])

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(x=-42, y=-20, z=55, radius=10, use_mni=True),
        )
        configure_roi(opt, config)

        simnibs.mni2subject_coords.assert_called_once()
        assert roi_mock.roi_sphere_center == [11, 21, 31]

    def test_spherical_focality_everything_else(self):
        from tit.opt.flex.utils import configure_roi
        import simnibs

        simnibs.mni2subject_coords = MagicMock(return_value=[10, 20, 30])

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
        import simnibs

        simnibs.mni2subject_coords = MagicMock(return_value=[10, 20, 30])

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
        import simnibs

        call_count = [0]

        def mock_mni2subject(coords, subpath):
            call_count[0] += 1
            return [c + 1 for c in coords]

        simnibs.mni2subject_coords = mock_mni2subject

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

        assert call_count[0] == 2  # Both ROI and non-ROI transformed

    def test_zero_coords_warning(self):
        from tit.opt.flex.utils import configure_roi

        opt = MagicMock()
        roi_mock = MagicMock()
        opt.add_roi.return_value = roi_mock

        config = _make_config(
            roi=SphericalROI(x=0, y=0, z=0, radius=10, use_mni=False),
        )
        with patch("tit.opt.flex.utils.log") as mock_log:
            configure_roi(opt, config)
            mock_log.warning.assert_called_once()


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
