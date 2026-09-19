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


@pytest.mark.parametrize("config_type", [ExConfig, MExConfig])
def test_ex_mni_label_is_selected_before_the_warp(config_type, tmp_path, monkeypatch):
    """One label is warped as a binary mask, never the whole atlas.

    That is the same mask (same bytes, same cached warp) the ROI confirmation
    and flex use, and it costs one small block instead of the whole head.
    """
    import numpy as np

    saved = {}

    class _Image:
        affine = np.eye(4)
        dataobj = np.array([[[0, 11, 12]]])

    class _Nib:
        @staticmethod
        def load(path):
            return _Image()

        @staticmethod
        def save(image, path):
            saved["path"] = path
            saved["data"] = np.asarray(image.dataobj)

        @staticmethod
        def Nifti1Image(data, affine):
            return type("I", (), {"dataobj": data, "affine": affine})()

    monkeypatch.setitem(__import__("sys").modules, "nibabel", _Nib)
    prepare = MagicMock(return_value="/derived/label.nii.gz")
    monkeypatch.setattr("tit.opt.masks.prepare_mask", prepare)
    monkeypatch.setattr("tit.atlas.islands.cleaned_label_mask", lambda *a: None)
    out = str(tmp_path / "masks")
    targets = [config_type.AtlasROI("/mni.nii", label=11, atlas_space="mni")]
    entries = atlas_roi_entries(SimpleNamespace(roi_atlas=targets), "/m2m_s", out)
    assert entries == [("/derived/label.nii.gz", 1)]
    assert saved["data"].tolist() == [[[0, 1, 0]]]
    prepare.assert_called_once_with(
        saved["path"], "mni", "/m2m_s", out, binary=True
    )


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
        str(tmp_path / ".ti-toolbox/cache/masks/sub-s"),
        binary=True,
    )
    assert roi.mask_space == complement.mask_space == ["subject"]
    assert roi.mask_path == complement.mask_path == ["/derived/binary.nii"]
    assert roi.mask_value == complement.mask_value == [1]
    assert complement.mask_operator == ["difference"]


@pytest.mark.parametrize("kind,config_type", [("ex", ExConfig), ("mex", MExConfig)])
def test_missing_mask_rejected_before_engine_creation(kind, config_type, monkeypatch):
    import importlib

    module = importlib.import_module(f"tit.opt.{kind}.{kind}")
    engine = MagicMock()
    monkeypatch.setattr(
        module, "ExSearchEngine" if kind == "ex" else "MExSearchEngine", engine
    )
    config = SimpleNamespace(
        roi_atlas=[config_type.AtlasROI("/host/Downloads/missing-mask.nii.gz")]
    )
    runner = (
        module._run_ex_search_inner if kind == "ex" else module._run_m_ex_search_inner
    )
    with pytest.raises(ValueError, match="Import it through the NIfTI mask picker"):
        runner(config)
    engine.assert_not_called()


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_validation_and_plan_reject_host_only_masks(kind, tmp_path):
    from fastapi import HTTPException
    from tit.server.routes.validate import validate, ValidateRequest
    from tit.server.routes.plan import plan, PlanRequest

    data = {
        "subject_id": "s",
        "leadfield_hdf": "leadfield.hdf5",
        "roi_name": "mask",
        "roi_names": [],
        "roi_atlas": [{"atlas_path": str(tmp_path / "absent.nii"), "label": None}],
        "electrodes": {
            "_type": "PoolElectrodes",
            "electrodes": [f"E{i}" for i in range(8)],
        },
    }
    result = validate(kind, ValidateRequest(config=data))
    assert not result.ok
    assert result.errors[0].path == "roi_atlas"
    assert "not accessible in the container" in result.errors[0].message
    with pytest.raises(HTTPException) as error:
        plan(kind, PlanRequest(config=data))
    assert error.value.status_code == 422
    assert "not accessible in the container" in str(error.value.detail)


def test_existing_container_mask_path_is_accepted(tmp_path):
    from tit.opt.masks import validate_mask_paths

    path = tmp_path / "mask.nii"
    path.touch()
    validate_mask_paths(SimpleNamespace(roi_atlas=[ExConfig.AtlasROI(str(path))]))


@pytest.mark.parametrize("field", ["roi", "non_roi"])
def test_flex_whole_mask_preflight_identifies_field(field):
    from tit.opt.masks import validate_mask_paths

    config = SimpleNamespace(
        **{field: FlexConfig.SubcorticalROI("/host/absent.nii", None)}
    )
    with pytest.raises(
        ValueError, match=field + r"\.atlas_path: mask is not accessible"
    ):
        validate_mask_paths(config)
