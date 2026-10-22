"""A specific non-ROI is built from its own region type, not the ROI's.

The desktop flex form picks the non-ROI type independently of the ROI (its default non-ROI is
cortical whatever the ROI is), and SimNIBS's ``TesFlexOptimization`` evaluates each
``RegionOfInterest`` on its own points -- focality's ROC counts the fraction of each region above
threshold -- so a spherical ROI against a cortical non-ROI is a valid search. Before this fix the
builder cast ``config.non_roi`` to the ROI's type and crashed (``AttributeError``) at run time.

Expected values are read off the specs themselves (centres, label, ``subject_<hemi>``); the ROI
objects are plain attribute bags, not mocks, so an attribute the builder never set stays unset.
Tissues: a volume non-ROI inherits the ROI's tissues when the ROI is a volume too (unchanged
behaviour); against a surface ROI it uses its own.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tit.opt.config import FlexConfig
from tit.opt.flex.utils import configure_roi

SphericalROI = FlexConfig.SphericalROI
AtlasROI = FlexConfig.AtlasROI
SubcorticalROI = FlexConfig.SubcorticalROI


class _Opt:
    def __init__(self):
        self.rois = []

    def add_roi(self):
        self.rois.append(SimpleNamespace())
        return self.rois[-1]


def _non_roi(roi, non_roi) -> SimpleNamespace:
    opt = _Opt()
    configure_roi(
        opt,
        FlexConfig(
            subject_id="001",
            postproc="max_TI",
            current_mA=2.0,
            electrode=FlexConfig.ElectrodeConfig(),
            goal="focality",
            non_roi_method="specific",
            roi=roi,
            non_roi=non_roi,
        ),
    )
    assert len(opt.rois) == 2
    assert opt.rois[1].weight == -1
    return opt.rois[1]


def _tags(tissues: str):
    from tit.opt.flex.utils import _resolve_tissues

    return _resolve_tissues(tissues)


@pytest.fixture
def nifti(tmp_path):
    path = tmp_path / "atlas.nii.gz"
    path.write_text("fake")
    return str(path)


SPHERE = SphericalROI(x=-42, y=-20, z=55, radius=10)
CORTICAL = AtlasROI(atlas_path="/atlas/lh.aparc.annot", label=5, hemisphere="rh")


def test_sphere_roi_with_cortical_non_roi():
    non_roi = _non_roi(SPHERE, CORTICAL)
    assert (non_roi.method, non_roi.surface_type) == ("surface", "central")
    assert non_roi.mask_space == ["subject_rh"]
    assert non_roi.mask_path == ["/atlas/lh.aparc.annot"]
    assert non_roi.mask_value == [5]
    assert not hasattr(non_roi, "roi_sphere_center")


def test_cortical_roi_with_mni_sphere_non_roi():
    non_roi = _non_roi(CORTICAL, SphericalROI(x=1, y=2, z=3, radius=7, use_mni=True))
    assert (non_roi.method, non_roi.surface_type) == ("surface", "central")
    assert non_roi.roi_sphere_center == [1, 2, 3]
    assert non_roi.roi_sphere_radius == 7
    assert non_roi.roi_sphere_center_space == "mni"
    assert not hasattr(non_roi, "mask_path")


def test_cortical_roi_with_subcortical_non_roi_uses_its_own_tissues(nifti):
    non_roi = _non_roi(
        CORTICAL, SubcorticalROI(atlas_path=nifti, label=11, tissues="WM")
    )
    assert non_roi.method == "volume"
    assert non_roi.mask_path == [nifti]
    assert non_roi.mask_value == [11]
    assert non_roi.tissues == _tags("WM")


def test_surface_sphere_roi_with_volumetric_sphere_non_roi():
    non_roi = _non_roi(
        SPHERE,
        SphericalROI(x=1, y=2, z=3, radius=7, volumetric=True, tissues="both"),
    )
    assert non_roi.method == "volume"
    assert non_roi.tissues == _tags("both")
    assert non_roi.roi_sphere_center == [1, 2, 3]


def test_subcortical_roi_with_cortical_non_roi(nifti):
    non_roi = _non_roi(SubcorticalROI(atlas_path=nifti, label=11), CORTICAL)
    assert (non_roi.method, non_roi.surface_type) == ("surface", "central")
    assert non_roi.mask_space == ["subject_rh"]
    assert not hasattr(non_roi, "tissues")


def test_subcortical_roi_with_sphere_non_roi_inherits_roi_tissues(nifti):
    non_roi = _non_roi(
        SubcorticalROI(atlas_path=nifti, label=11, tissues="WM"),
        SphericalROI(x=1, y=2, z=3, radius=7, volumetric=True, tissues="GM"),
    )
    # Both are volumes: the non-ROI shares the ROI's tissues, as before this fix.
    assert non_roi.method == "volume"
    assert non_roi.tissues == _tags("WM")
    assert non_roi.roi_sphere_center == [1, 2, 3]


def test_subcortical_roi_with_surface_sphere_non_roi(nifti):
    non_roi = _non_roi(
        SubcorticalROI(atlas_path=nifti, label=11),
        SphericalROI(x=1, y=2, z=3, radius=7),
    )
    assert (non_roi.method, non_roi.surface_type) == ("surface", "central")
    assert not hasattr(non_roi, "tissues")


def test_desktop_wire_config_with_sphere_roi_and_default_cortical_non_roi():
    """The JSON the desktop sends (types.ts `roiToConfig`) through the runner's deserializer."""
    from tit.config_io import deserialize_config

    config = deserialize_config(
        FlexConfig,
        {
            "subject_id": "001",
            "goal": "focality",
            "postproc": "max_TI",
            "current_mA": 2.0,
            "electrode": {},
            "non_roi_method": "specific",
            "roi": {
                "_type": "SphericalROI",
                "x": [-42.0],
                "y": [-20.0],
                "z": [55.0],
                "radius": [10.0],
                "use_mni": False,
                "volumetric": False,
                "tissues": "GM",
            },
            "non_roi": {
                "_type": "AtlasROI",
                "atlas_path": ["/atlas/lh.aparc.annot"],
                "label": [5],
                "hemisphere": ["lh"],
            },
        },
    )
    opt = _Opt()
    configure_roi(opt, config)
    roi, non_roi = opt.rois
    assert roi.roi_sphere_center == [-42.0, -20.0, 55.0]
    assert non_roi.mask_space == ["subject_lh"]
    assert non_roi.mask_value == [5]
