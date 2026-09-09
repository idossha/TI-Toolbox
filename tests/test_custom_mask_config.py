"""New mask fields dispatch to preparation; legacy atlas targets remain subject-space."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from tit.opt.config import ExConfig, MExConfig, FlexConfig
from tit.opt.ex.roi import atlas_roi_entries


@pytest.mark.parametrize("config_type", [ExConfig, MExConfig])
def test_ex_mask_space_dispatch_and_legacy_default(config_type, monkeypatch):
    prepare = MagicMock(return_value="/derived/subject.nii")
    monkeypatch.setattr("tit.opt.masks.prepare_mask", prepare)
    targets = [
        config_type.AtlasROI("/native.nii"),
        config_type.AtlasROI("/mni.nii", atlas_space="mni"),
    ]
    assert atlas_roi_entries(
        SimpleNamespace(roi_atlas=targets), "/m2m_s", "/run/masks"
    ) == ["/native.nii", "/derived/subject.nii"]
    prepare.assert_called_once_with("/mni.nii", "mni", "/m2m_s", "/run/masks")


def test_flex_whole_mask_and_complement_share_prepared_geometry(tmp_path, monkeypatch):
    from tit import get_path_manager
    from tit.opt.flex.utils import configure_roi

    pm = get_path_manager(str(tmp_path))
    prepare = MagicMock(return_value="/derived/binary.nii")
    monkeypatch.setattr("tit.opt.masks.prepare_mask", prepare)
    roi, complement = SimpleNamespace(), SimpleNamespace()
    opt = SimpleNamespace(add_roi=MagicMock(side_effect=[roi, complement]))
    config = SimpleNamespace(
        subject_id="s",
        roi=FlexConfig.SubcorticalROI("/mask.nii", None, atlas_space="mni"),
        is_focality=True,
        non_roi_method="everything_else",
    )
    configure_roi(opt, config)
    prepare.assert_called_once_with(
        "/mask.nii",
        "mni",
        pm.m2m("s"),
        str(tmp_path / "derivatives/SimNIBS/sub-s/m2m_s/masks/.prepared"),
        binary=True,
    )
    assert roi.mask_space == complement.mask_space == ["subject"]
    assert roi.mask_path == complement.mask_path == ["/derived/binary.nii"]
    assert roi.mask_value == complement.mask_value == [1]
    assert complement.mask_operator == ["difference"]
